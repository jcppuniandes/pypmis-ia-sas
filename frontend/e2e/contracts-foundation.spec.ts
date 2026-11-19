import { expect, test, type BrowserContext, type Locator, type Page } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";

type Row = Record<string, unknown>;
type Role = "preparer" | "approver" | "executor" | "cost" | "configurator" | "publisher";
type Fixture = {
  tenant_id: number;
  project_workspace_id: number;
  password: string;
  users: Record<Role, string>;
  po_id: number;
  vendor_id: number;
  document_id: number;
  attachment_id: number;
  cbs_id: number;
  cost_code_id: number;
  control_account_id: number;
  period_id: number;
  scope_item_id: number;
  progress_measurement_id: number;
  progress_unit: string;
  progress_quantity: string;
  effective_at: string;
};
const manifest = process.env.E2E_O2C_FIXTURE;
const fixture = manifest ? (JSON.parse(readFileSync(manifest, "utf8")) as Fixture) : null;
const api = process.env.E2E_API_URL || "http://127.0.0.1:8862";
const app = process.env.E2E_BASE_URL || "http://127.0.0.1:5522";
const out = path.resolve(process.env.E2E_O2C_OUTPUT || "../outputs/.qa/wave-o2c/chromium");
const reason = "O2C validación aislada con API, PostgreSQL y Chromium reales";
const id = (row: Row) => Number(row.id);
const field = (page: Page | Locator, label: string) => page.getByLabel(label, { exact: true });
const button = (page: Page | Locator, name: string) => page.getByRole("button", { name, exact: true });
const panel = (page: Page, name: string) => page.getByRole("region", { name, exact: true });
const tableRow = (table: Locator, identity: number) =>
  table.locator(`tbody tr:has(td:first-child:text-is("${identity}"))`);
const form = (page: Page | Locator, name: string) => page.getByRole("form", { name, exact: true });
const date = (days: number, origin: string) =>
  new Date(Date.parse(origin) + days * 86400000).toISOString().slice(0, 10);

test.describe("O2C Contracts Manager and explicit Cost adoption · real Chromium", () => {
  test.skip(!fixture, "Requires O2C isolated PostgreSQL, HTTP API and a provisioned real-domain fixture.");
  test.use({ actionTimeout: 45_000, navigationTimeout: 120_000 });
  test("published profile, procurement → contract → Cost → SOV → certification → change", async ({
    browser,
    request,
  }) => {
    test.setTimeout(1_500_000);
    if (!fixture) throw new Error("Missing O2C isolated fixture");
    const data = fixture;
    const workspace = data.project_workspace_id;
    expect(workspace).toBeGreaterThan(0);
    expect(workspace).not.toBe(14);
    expect(api).toMatch(/^http:\/\/(localhost|127\.0\.0\.1):\d+$/);
    expect(app).toMatch(/^http:\/\/(localhost|127\.0\.0\.1):\d+\/?$/);
    expect(new URL(app).port).not.toBe("5173");
    expect(new URL(api).port).not.toBe("8000");
    const route = `/workspaces/${workspace}/contracts`;
    const prefix = `/api/v1/contracts/projects/${workspace}`;
    const effective = data.effective_at.slice(0, 10);
    const availableProgress = Number(data.progress_quantity);
    expect(availableProgress).toBeGreaterThan(0);
    const applicationQuantity = Math.min(availableProgress, 1);
    const certificateQuantity = applicationQuantity / 2;
    const document = `${data.document_id}:${data.attachment_id}`;
    const run = Date.now().toString(36).toUpperCase();
    const steps: { stage: string; status: number; id: number; method: string }[] = [];
    const observations: Row = { project_workspace_id: workspace, tenant_id: data.tenant_id };
    const errors: { role: string; error: string }[] = [];
    const network: { role: string; path: string; status?: number; error?: string }[] = [];
    const authTokens: Partial<Record<Role, string>> = {};
    const contexts: BrowserContext[] = [];
    let stage = "profile";
    let passed = false;
    let lastPage: Page | undefined;
    mkdirSync(out, { recursive: true });
    const screenshot = (page: Page, name: string) => page.screenshot({ path: path.join(out, `${name}.png`) });
    async function session(role: Role, mode: "admin" | "operational" = "operational", target = route) {
      const email = data.users[role];
      expect(email).toBeTruthy();
      const login = await request.post(`${api}/api/v1/auth/login`, {
        timeout: 120_000,
        data: { email, tenant_id: data.tenant_id, password: data.password },
      });
      expect(login.status(), `login for ${role}`).toBe(200);
      const auth = await login.json();
      authTokens[role] = auth.access_token;
      const context = await browser.newContext({ baseURL: app, viewport: { width: 1440, height: 900 } });
      contexts.push(context);
      await context.addInitScript(
        (value) =>
          localStorage.setItem(
            "pypmis_auth",
            JSON.stringify({
              state: { token: value.access_token, user: value.user },
              version: 0,
            })
          ),
        auth
      );
      const page = await context.newPage();
      lastPage = page;
      page.on("pageerror", (error) => errors.push({ role, error: error.message }));
      page.on("response", (response) => {
        const path = new URL(response.url()).pathname;
        if (path.startsWith("/api/v1/workspaces/") || response.status() >= 400)
          network.push({ role, path, status: response.status() });
      });
      page.on("requestfailed", (failed) => {
        const path = new URL(failed.url()).pathname;
        if (path.startsWith("/api/")) network.push({ role, path, error: failed.failure()?.errorText });
      });
      await page.goto(mode === "admin" ? "/app" : target);
      if (mode === "admin") {
        await button(page, "Cambiar a ADMIN MODE").click({ timeout: 180_000 });
        for (const name of ["Platform Administration", "Process Configuration"]) {
          const group = button(page, name);
          if ((await group.getAttribute("aria-expanded")) !== "true") await group.click();
        }
        await button(page, "Process & Operational Configuration").click();
        await button(page, "Contract Profiles").click();
      } else if (target === route) {
        await expect(page.getByRole("navigation", { name: "Contracts Manager submodules" })).toBeVisible({
          timeout: 180_000,
        });
      }
      return page;
    }
    async function values(root: Locator, inputs: Record<string, string | number>) {
      for (const [label, value] of Object.entries(inputs)) {
        const control = field(root, label);
        const tag = await control.evaluate((node) => node.tagName);
        if (tag === "SELECT") await control.selectOption(String(value));
        else await control.fill(String(value));
      }
    }
    async function mutate(
      page: Page,
      editor: Locator,
      label: string,
      endpoint: string,
      expected: number,
      motive = "Motivo contractual"
    ) {
      if (motive) await field(editor, motive).fill(reason);
      const [response] = await Promise.all([
        page.waitForResponse(
          (item) => new URL(item.url()).pathname === endpoint && ["POST", "PUT"].includes(item.request().method())
        ),
        button(editor, label).click(),
      ]);
      const payload = await response.text();
      expect(response.status(), `${stage}: ${payload}`).toBe(expected);
      expect(await response.request().headerValue("idempotency-key")).toBeTruthy();
      const record = JSON.parse(payload) as Row;
      steps.push({ stage, status: response.status(), id: id(record), method: response.request().method() });
      return record;
    }
    async function activate(page: Page, tab: string) {
      await button(page.getByRole("navigation", { name: "Contracts Manager submodules" }), tab).click();
      return panel(page, tab);
    }
    async function selectRecord(page: Page, tab: string, identity: number) {
      const area = await activate(page, tab);
      await tableRow(area.getByRole("table", { name: tab, exact: true }), identity)
        .getByRole("button", { name: /^Ver / })
        .click();
      await expect(area.getByRole("region", { name: "Detalle contractual" })).toBeVisible();
      return area;
    }
    async function createForm(page: Page, tab: string, label: string) {
      const area = await activate(page, tab);
      await button(area, "Nuevo registro").click();
      return form(area, label);
    }
    async function transition(
      page: Page,
      tab: string,
      entity: string,
      identity: number,
      action: string,
      suffix = "/actions",
      fields: Record<string, string | number> = {}
    ) {
      const area = await selectRecord(page, tab, identity);
      await button(area, `${action}…`).click();
      const editor = form(area, action);
      await values(editor, fields);
      const record = await mutate(page, editor, action, `${prefix}/${entity}/${identity}${suffix}`, 200);
      if (typeof record.status === "string")
        await expect(area.getByRole("region", { name: "Detalle contractual" })).toContainText(record.status, {
          timeout: 180_000,
        });
      return record;
    }
    async function pinPO(editor: Locator) {
      await values(editor, { "Tipo de fuente Procurement": "PURCHASE_ORDER", "ID de fuente Procurement": data.po_id });
      await button(editor, "Consultar fuente Procurement").click();
      await button(editor, "Fijar fuente Procurement").click();
    }
    try {
      const config = await session("configurator", "admin");
      const existingProfile = Number(process.env.E2E_O2C_REUSE_PROFILE_ID ?? "0");
      if (existingProfile > 0) {
        const response = await request.get(`${api}/api/v1/contracts/admin/profiles`, {
          headers: { Authorization: `Bearer ${authTokens.configurator}` },
        });
        expect(response.status()).toBe(200);
        const profiles = (await response.json()).items as Row[];
        const published = profiles.find((item) => id(item) === existingProfile);
        expect(String(published?.status).toUpperCase()).toBe("PUBLISHED");
        const settings = published?.content_json as Row;
        expect(settings.contract_types).toContain("PURCHASE_ORDER_BASED_AGREEMENT");
        expect(settings.separation_of_duties).toBeTruthy();
        expect(!settings.effective_from || Date.parse(String(settings.effective_from)) <= Date.now()).toBe(true);
        expect(!settings.effective_to || Date.parse(String(settings.effective_to)) > Date.now()).toBe(true);
        await tableRow(config.getByRole("table", { name: "Perfiles contractuales" }), existingProfile)
          .getByRole("button", { name: /^Ver / })
          .click();
        await expect(config.getByRole("region", { name: "Perfil contractual seleccionado" })).toContainText(
          "PUBLISHED"
        );
        observations.profile_id = existingProfile;
        observations.profile_reused = true;
        await screenshot(config, "01-perfil-publicado-verificado");
      } else {
        await button(config, "Nuevo perfil contractual").click();
        const createProfile = form(config, "Crear borrador contractual");
        await values(createProfile, {
          "Código del perfil contractual": `O2C-${run}`,
          "Nombre del perfil contractual": `O2C ${run}`,
        });
        const profilePath = "/api/v1/contracts/admin/profiles";
        const draft = await mutate(
          config,
          createProfile,
          "Crear borrador contractual",
          profilePath,
          201,
          "Motivo del perfil contractual"
        );
        const publisher = await session("publisher", "admin");
        await tableRow(publisher.getByRole("table", { name: "Perfiles contractuales" }), id(draft))
          .getByRole("button", { name: /^Ver / })
          .click();
        await button(publisher, "Publicar perfil…").click();
        const published = await mutate(
          publisher,
          form(publisher, "Publicar perfil"),
          "Publicar perfil",
          `${profilePath}/${id(draft)}/publish`,
          200
        );
        expect(String(published.status).toUpperCase()).toBe("PUBLISHED");
        observations.profile_id = id(published);
        await screenshot(publisher, "01-perfil-publicado");
      }

      stage = "package";
      const preparer = await session("preparer");
      const packageForm = await createForm(preparer, "Contract Packages", "Crear paquete contractual");
      await values(packageForm, {
        "Código del paquete": `PK-${run}`,
        "Título del paquete": "O2C paquete validado",
        "Tipo de contrato": "PURCHASE_ORDER_BASED_AGREEMENT",
        "Modelo comercial": "UNIT_RATE",
        Moneda: "USD",
        "Valor estimado": "1000",
      });
      await pinPO(packageForm);
      const packageRecord = await mutate(preparer, packageForm, "Crear paquete contractual", `${prefix}/packages`, 201);
      observations.package_id = id(packageRecord);

      stage = "contract and controlled execution";
      const contractForm = await createForm(preparer, "Contracts", "Registrar contrato");
      await values(contractForm, {
        "Número de contrato": `CT-${run}`,
        "Paquete contractual": id(packageRecord),
        "Título del contrato": "Contrato O2C validado",
        "Proveedor Procurement (ID)": data.vendor_id,
        "Referencia rectora": "Instrumento fuente rastreado a PO",
        "Valor original": "1000",
        "Fecha efectiva": effective,
        Inicio: effective,
        "Terminación prevista": date(90, effective),
        "Referencia de términos": "CDE terms O2C",
        "Evidencia CDE": document,
      });
      await pinPO(contractForm);
      const contract = await mutate(preparer, contractForm, "Registrar contrato", `${prefix}/contracts`, 201);
      const contractId = id(contract);
      const version = Number(contract.current_version_id);
      observations.contract_id = contractId;
      observations.initial_contract_version_id = version;
      expect(version).toBeGreaterThan(0);
      const approver = await session("approver");
      expect((await transition(approver, "Contracts", "contracts", contractId, "Aprobar contrato")).status).toBe(
        "APPROVED"
      );
      const executor = await session("executor");
      expect(
        (
          await transition(executor, "Contracts", "contracts", contractId, "Registrar firma", "/actions", {
            "Fecha de firma": effective,
            "Documento firmado CDE": document,
          })
        ).status
      ).toBe("EXECUTED");
      expect((await transition(executor, "Contracts", "contracts", contractId, "Declarar efectivo")).status).toBe(
        "EFFECTIVE"
      );
      await screenshot(executor, "02-contrato-efectivo");

      stage = "commercial commitment";
      const commitmentForm = await createForm(preparer, "Commercial Commitments", "Registrar compromiso comercial");
      await values(commitmentForm, {
        "Código de compromiso": `CC-${run}`,
        Contrato: contractId,
        "Versión de contrato": version,
        "Importe comprometido": "1000",
        "Fecha efectiva": effective,
        "Base comercial": "Compromiso conforme al contrato efectivo",
      });
      const commitment = await mutate(
        preparer,
        commitmentForm,
        "Registrar compromiso comercial",
        `${prefix}/commitments`,
        201
      );
      const commitmentId = id(commitment);
      const approved = await transition(
        approver,
        "Commercial Commitments",
        "commitments",
        commitmentId,
        "Aprobar compromiso comercial",
        "/approve"
      );
      expect(approved.status).toBe("APPROVED");
      observations.commitment_id = commitmentId;
      await screenshot(approver, "03-compromiso-aprobado");

      stage = "native Cost adoption";
      const cost = await session(
        "cost",
        "operational",
        `/workspaces/${workspace}/cost?commercial_commitment_id=${commitmentId}`
      );
      const costPanel = panel(cost, "Commercial Adoption");
      const decision = form(costPanel, "Registrar decisión Cost");
      await field(cost, "Motivo Cost").fill(reason);
      await values(decision, {
        "Decisión Cost": "ADOPTED",
        "CBS de adopción": data.cbs_id,
        "Código de costo de adopción": data.cost_code_id,
        "Cuenta de control de adopción": data.control_account_id,
      });
      const adopted = await mutate(
        cost,
        decision,
        "Registrar decisión Cost",
        `/api/v1/cost/projects/${workspace}/commercial-commitment-adoptions`,
        201,
        ""
      );
      expect(adopted.consumer_status).toBe("ADOPTED");
      expect(adopted.source_hash).toBe(approved.source_hash);
      observations.cost_adoption_id = id(adopted);
      await expect(
        costPanel.getByRole("table", { name: "Decisiones de adopción comercial" }).getByRole("cell", {
          name: "ADOPTED",
          exact: true,
        })
      ).toBeVisible();
      await screenshot(cost, "04-adopcion-cost");

      stage = "published SOV";
      const sovForm = await createForm(preparer, "SOV", "Crear SOV");
      await values(sovForm, {
        Contrato: contractId,
        "Versión de contrato": version,
        "Código SOV": `SOV-${run}`,
        "Número de línea 1": "001",
        "Descripción de línea 1": "Valorización de avance de Scope aprobado",
        "Cantidad 1": "10",
        "Precio unitario 1": "100",
        "Unidad 1": data.progress_unit,
        "Vínculos de la línea 1": JSON.stringify([{ target_kind: "SCOPE", target_id: data.scope_item_id }]),
        "Regla de retención 1": "STANDARD",
      });
      const sov = await mutate(preparer, sovForm, "Crear SOV", `${prefix}/sovs`, 201);
      const sovId = id(sov);
      const publishedSov = await transition(approver, "SOV", "sovs", sovId, "Publicar SOV", "/publish");
      expect(publishedSov.status).toBe("PUBLISHED");
      const lines = (publishedSov.lines ?? sov.lines) as Row[];
      expect(lines).toHaveLength(1);
      const sovLineId = id(lines[0]);
      observations.sov_id = sovId;
      await screenshot(approver, "05-sov-publicada");

      stage = "approved Progress → payment application";
      const applicationForm = await createForm(preparer, "Payment Applications", "Presentar solicitud de pago");
      await values(applicationForm, {
        Contrato: contractId,
        "SOV publicado": sovId,
        "Número de solicitud": `APP-${run}`,
        "Período de control (ID)": data.period_id,
        "Fecha efectiva": effective,
        "Evidencia CDE": document,
        "Línea publicada SOV (ID) 1": sovLineId,
        "Medición aprobada de Progress 1": data.progress_measurement_id,
        "Cantidad solicitada 1": applicationQuantity,
      });
      const application = await mutate(
        preparer,
        applicationForm,
        "Presentar solicitud de pago",
        `${prefix}/payment-applications`,
        201
      );
      const applicationId = id(application);
      const applicationLineId = id((application.lines as Row[])[0]);
      observations.application_id = applicationId;
      expect(
        (await transition(approver, "Payment Applications", "payment-applications", applicationId, "Revisar solicitud"))
          .status
      ).toBe("REVIEWED");
      await screenshot(approver, "06-solicitud-revisada");

      stage = "certificate";
      const certForm = await createForm(preparer, "Payment Certificates", "Preparar certificado");
      await values(certForm, {
        "Solicitud revisada": applicationId,
        "Número de certificado": `CER-${run}`,
        "Fecha efectiva": effective,
        "Evidencia CDE": document,
        "Línea de solicitud (ID) 1": applicationLineId,
        "Cantidad certificada 1": certificateQuantity,
      });
      const certificate = await mutate(
        preparer,
        certForm,
        "Preparar certificado",
        `${prefix}/payment-certificates`,
        201
      );
      observations.certificate_id = id(certificate);
      const finalCertificate = await transition(
        approver,
        "Payment Certificates",
        "payment-certificates",
        id(certificate),
        "Aprobar certificado"
      );
      expect(finalCertificate.status).toBe("APPROVED");
      expect(Number(finalCertificate.net_amount)).toBeCloseTo(certificateQuantity * 100 * 0.9, 8);
      await screenshot(approver, "07-certificado-aprobado");

      stage = "external invoice reference without financial posting";
      const reference = await transition(
        executor,
        "Payment Certificates",
        "payment-certificates",
        id(certificate),
        "Vincular referencia externa Finance",
        "/finance-references",
        {
          "Sistema de origen": "O2C-UAT-EXTERNAL-REFERENCE",
          "Referencia de factura externa": `INV-${run}`,
          "Versión en origen": 1,
          "Hash en origen": createHash("sha256").update(`INV-${run}:1:UNPAID`).digest("hex"),
          "Importe de referencia": Number(finalCertificate.net_amount),
          "Referencia de estado": "REGISTERED",
          "Estado de pago externo": "UNPAID",
        }
      );
      observations.finance_reference_id = id(reference);
      const references = await activate(executor, "Finance References");
      await expect(
        tableRow(references.getByRole("table", { name: "Finance References", exact: true }), id(reference))
      ).toBeVisible();
      await screenshot(executor, "08-referencia-finance");

      stage = "change order and immutable version";
      const changeForm = await createForm(preparer, "Changes", "Registrar cambio potencial");
      await values(changeForm, {
        Contrato: contractId,
        "Versión base": version,
        "Número de cambio": `CHG-${run}`,
        "Tipo de cambio": "PRICE",
        "Descripción del cambio": "Incremento validado con evidencia de CDE",
        "Variación de valor": "50",
        "Variación de plazo (días)": 0,
        "Fecha efectiva": effective,
        "Evidencia CDE de cambio": document,
      });
      const change = await mutate(preparer, changeForm, "Registrar cambio potencial", `${prefix}/changes`, 201);
      observations.change_id = id(change);
      expect((await transition(preparer, "Changes", "changes", id(change), "Solicitar cambio")).status).toBe(
        "REQUESTED"
      );
      expect((await transition(approver, "Changes", "changes", id(change), "Poner cambio en revisión")).status).toBe(
        "UNDER_REVIEW"
      );
      const changed = await transition(
        approver,
        "Changes",
        "changes",
        id(change),
        "Aprobar orden de cambio",
        "/actions",
        { "Evidencia CDE de aprobación": document }
      );
      expect(changed.status).toBe("ORDER_APPROVED");
      expect(Number(changed.resulting_version_id)).not.toBe(version);
      observations.resulting_contract_version_id = changed.resulting_version_id;
      const versions = await activate(approver, "Contract Versions");
      const versionsTable = versions.getByRole("table", { name: "Contract Versions", exact: true });
      await expect(tableRow(versionsTable, version)).toBeVisible();
      await expect(tableRow(versionsTable, Number(changed.resulting_version_id))).toBeVisible();
      await screenshot(approver, "09-versiones-contractuales");
      await activate(approver, "History");
      await expect(approver.getByRole("table", { name: "History" })).toBeVisible();
      await screenshot(approver, "10-historial");
      expect(errors).toEqual([]);
      passed = true;
    } finally {
      if (!passed && lastPage) await screenshot(lastPage, "00-fallo").catch(() => {});
      writeFileSync(
        path.join(out, "o2c-browser-evidence.json"),
        JSON.stringify({ result: passed ? "PASS" : "FAIL", stage, steps, observations, errors, network }, null, 2)
      );
      for (const context of contexts) await context.close();
    }
  });
});
