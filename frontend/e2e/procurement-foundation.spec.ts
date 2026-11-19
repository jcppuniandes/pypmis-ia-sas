import { expect, test, type BrowserContext, type Locator, type Page } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

type Row = Record<string, unknown>;
type Fixture = {
  project_workspace_id: number;
  tenant_id: number;
  password: string;
  users: Record<string, { email: string; tenant_id: number; password?: string }>;
  ifc_release_id: number;
  ifc_release_hash: string;
  pwp_id: number;
  iwp_id: number;
  document_id: number;
  attachment_id: number;
};
const manifest = process.env.E2E_O2B_FIXTURE;
const fixture = manifest ? (JSON.parse(readFileSync(manifest, "utf8")) as Fixture) : null;
const api = process.env.E2E_API_URL || "http://127.0.0.1:8860";
const base = process.env.E2E_BASE_URL || "http://127.0.0.1:5520";
const output = path.resolve(process.env.E2E_O2B_OUTPUT || "../outputs/.qa/wave-o2b/chromium");
const reason = "O2B isolated real-browser workflow validation";
const date = (days = 0) => new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
const button = (page: Page | Locator, name: string) => page.getByRole("button", { name, exact: true });
const field = (page: Page | Locator, label: string) => page.getByLabel(label, { exact: true });
const identity = (row: Row) => {
  expect(Number(row.id)).toBeGreaterThan(0);
  return Number(row.id);
};
const records = (value: unknown): Row[] => (Array.isArray(value) ? (value as Row[]) : []);

test.describe("O2B Procurement Materials and Logistics — real Chromium", () => {
  test.skip(!fixture, "Requires the isolated O2B PostgreSQL, real API and synthetic fixture");
  test.use({ actionTimeout: 45_000, navigationTimeout: 120_000 });
  test("technical demand to an accepted, allocated IWP without AWP release", async ({ browser, request }) => {
    test.setTimeout(1_500_000);
    if (!fixture) throw new Error("Missing disposable O2B fixture");
    const data = fixture;
    expect(api).toMatch(/^http:\/\/(127\.0\.0\.1|localhost):8860$/);
    expect(base).toMatch(/^http:\/\/(127\.0\.0\.1|localhost):5520\/?$/);
    expect(data.project_workspace_id).not.toBe(14);
    expect(data.project_workspace_id).toBeGreaterThan(0);
    mkdirSync(output, { recursive: true });
    const workspace = data.project_workspace_id;
    const root = `${api}/api/v1/procurement/projects/${workspace}`;
    const route = `/workspaces/${workspace}/procurement`;
    const awpRoot = `${api}/api/v1/awp/projects/${workspace}`;
    const run = Date.now().toString(36).toUpperCase();
    const checks: Array<{ code: string; result: string }> = [];
    const mutations: Array<{ step: string; status: number }> = [];
    const errors: Array<{ role: string; error: string }> = [];
    const observations: Row = { tenant_id: data.tenant_id, project_workspace_id: workspace, iwp_id: data.iwp_id };
    const timings: Array<{
      operation: string;
      route: string;
      samples_ms: number[];
      median_ms: number;
      record_count: number;
      response_json_bytes: number;
    }> = [];
    const sessions = new Map<string, { page: Page; token: string; context: BrowserContext }>();
    let stage = "admin-profile";
    let result = "FAIL";
    let lastPage: Page | undefined;
    const mark = (code: string) => checks.push({ code, result: "PASS" });
    const shot = async (page: Page, target: Locator, name: string) => {
      await target.scrollIntoViewIfNeeded();
      await page.screenshot({ path: path.join(output, `${name}.png`) });
    };
    async function session(role: string, admin = false, target = route) {
      const key = `${role}:${admin ? "admin" : target}`;
      const cached = sessions.get(key);
      if (cached) {
        lastPage = cached.page;
        return cached;
      }
      const user = data.users[role];
      expect(user, `synthetic ${role}`).toBeTruthy();
      const login = await request.post(`${api}/api/v1/auth/login`, {
        timeout: 120_000,
        data: { email: user.email, tenant_id: user.tenant_id, password: user.password ?? data.password },
      });
      expect(login.status(), `authentication: ${role}`).toBe(200);
      const auth = await login.json();
      const context = await browser.newContext({ baseURL: base, viewport: { width: 1440, height: 900 } });
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
      await page.goto(admin ? "/app" : target);
      if (admin) {
        const mode = button(page, "Cambiar a ADMIN MODE");
        await expect(mode).toBeEnabled({ timeout: 180_000 });
        await mode.click();
        for (const name of ["Platform Administration", "Process Configuration"]) {
          const item = button(page, name);
          if ((await item.getAttribute("aria-expanded")) !== "true") await item.click();
        }
        await button(page, "Process & Operational Configuration").click();
        await button(page, "Procurement Profiles").click();
      }
      const instance = { page, token: String(auth.access_token), context };
      sessions.set(key, instance);
      return instance;
    }
    const tab = (page: Page, name: string) =>
      button(page.getByRole("navigation", { name: "Vistas Procurement Manager" }), name).click();
    const panel = (page: Page, name: string) => page.getByRole("region", { name, exact: true });
    async function setValues(form: Locator, values: Record<string, string | number>) {
      for (const [key, value] of Object.entries(values)) {
        const element = field(form, key);
        if ((await element.evaluate((node) => node.tagName)) === "SELECT") await element.selectOption(String(value));
        else await element.fill(String(value));
      }
    }
    async function command(
      page: Page,
      form: Locator,
      label: string,
      suffix: string,
      expected = 200,
      motive = "Motivo de Procurement"
    ) {
      if (motive) await field(form, motive).fill(reason);
      const [response] = await Promise.all([
        page.waitForResponse(
          (item) => new URL(item.url()).pathname.endsWith(suffix) && ["POST", "PUT"].includes(item.request().method())
        ),
        button(form, label).click(),
      ]);
      mutations.push({ step: stage, status: response.status() });
      expect(response.status(), `${stage}: ${await response.text()}`).toBe(expected);
      const busy = page.locator(
        '[aria-label="Procurement Manager"], [aria-label="Procurement Profiles ADMIN"], [aria-label="Project Execution AWP"]'
      );
      if (await busy.count()) await expect(busy).toHaveAttribute("aria-busy", "false", { timeout: 45_000 });
      return (await response.json()) as Row;
    }
    async function create(
      page: Page,
      view: string,
      name: string,
      suffix: string,
      values: Record<string, string | number>
    ) {
      await tab(page, view);
      const area = panel(page, name);
      await button(area, `Nuevo registro · ${name}`).click();
      const label = `Crear · ${name}`;
      const form = area.getByRole("form", { name: label });
      await setValues(form, values);
      return command(page, form, label, suffix, 201);
    }
    async function selectRecord(page: Page, view: string, name: string, id: number) {
      await tab(page, view);
      const area = panel(page, name);
      const table = area.getByRole("table", { name, exact: true });
      const row = table.locator(`tbody tr:has(td:first-child:text-is("${id}"))`);
      await row.getByRole("button", { name: /^Ver / }).click();
      await expect(area.getByText(`Detalle · ${name} #${id}`, { exact: true })).toBeVisible();
      return area;
    }
    async function action(
      page: Page,
      view: string,
      name: string,
      id: number,
      label: string,
      suffix: string,
      values: Record<string, string | number> = {},
      expected = 200
    ) {
      const area = await selectRecord(page, view, name, id);
      await button(area, label).click();
      const confirm = `Confirmar · ${label}`;
      const form = area.getByRole("form", { name: confirm });
      await setValues(form, values);
      return command(page, form, confirm, suffix, expected);
    }
    async function read(token: string, suffix: string, source = root): Promise<Row> {
      const response = await request.get(`${source}${suffix}`, { headers: { Authorization: `Bearer ${token}` } });
      expect(response.status(), suffix).toBe(200);
      return (await response.json()) as Row;
    }
    async function map(page: Page, source: string, sourceId: number, target: string, targetId: number) {
      await tab(page, "Mappings");
      const area = panel(page, "Relaciones de Procurement");
      await setValues(area, { "Tipo de origen": source, "ID de origen": sourceId });
      await button(area, "Consultar vínculos del origen").click();
      const form = area.getByRole("form", { name: "Registrar vínculo" });
      await setValues(form, {
        "Tipo de destino del vínculo": target,
        "ID de destino del vínculo": targetId,
        "Acción del vínculo": "SET",
        "Fecha efectiva del vínculo": date(),
      });
      return command(page, form, "Registrar vínculo", "/mappings", 201);
    }
    const pack = "Procurement Packages";
    const packages = "Paquetes de Procurement";
    const requirement = "Requisitos de Procurement";
    const orders = "Órdenes de compra";
    const ifc = JSON.stringify({
      target_kind: "IFC_RELEASE",
      target_id: data.ifc_release_id,
      source_hash: data.ifc_release_hash,
    });
    const cde = JSON.stringify({ document_id: data.document_id, attachment_id: data.attachment_id });

    try {
      const admin = await session("admin", true);
      const adminPanel = panel(admin.page, "Procurement Profiles ADMIN");
      await button(adminPanel, "Nuevo perfil Procurement").click();
      const editor = panel(admin.page, "Editor de perfil Procurement");
      await setValues(editor, {
        "Código del perfil Procurement": `O2B_${run}`,
        "Nombre del perfil Procurement": "O2B isolated technical validation",
        "Ámbito del perfil Procurement": "workspace",
        "ID Workspace del perfil Procurement": workspace,
      });
      await field(editor, "Exigir liberación IFC de Ingeniería").check();
      const draft = await command(
        admin.page,
        editor,
        "Crear perfil Procurement",
        "/admin/profiles",
        201,
        "Motivo del perfil Procurement"
      );
      const profileId = identity(draft);
      await command(
        admin.page,
        editor.getByRole("form", { name: "Publicar perfil Procurement" }),
        "Publicar perfil Procurement",
        `/admin/profiles/${profileId}/publish`,
        403
      );
      await admin.context.close();
      const publisher = await session("procurement_publisher", true);
      await button(publisher.page, `Ver Perfiles Procurement O2B_${run}`).click();
      const publishForm = publisher.page.getByRole("form", { name: "Publicar perfil Procurement" });
      const profile = await command(
        publisher.page,
        publishForm,
        "Publicar perfil Procurement",
        `/admin/profiles/${profileId}/publish`
      );
      expect(profile.status).toBe("published");
      observations.profile_id = profileId;
      await shot(
        publisher.page,
        panel(publisher.page, "Editor de perfil Procurement").getByRole("heading", { level: 3 }),
        "01-admin-profile-published"
      );
      await publisher.context.close();
      mark("ADMIN_PROFILE_INDEPENDENT_PUBLICATION");

      stage = "register-and-technical-demand";
      const buyer = await session("buyer");
      const pkg = identity(
        await create(buyer.page, pack, packages, "/packages", {
          "Código del paquete": `PKG_${run}`,
          Título: "O2B real browser material package",
          "Tipo de compra": "MATERIAL",
          Categoría: "GENERAL",
          "Método de compra": "RFQ",
          "Necesario en sitio": date(5),
          "RFQ prevista": date(),
        })
      );
      observations.procurement_package_id = pkg;
      await map(buyer.page, "PACKAGE", pkg, "PWP", data.pwp_id);
      const req = identity(
        await create(buyer.page, "Requirements", requirement, "/requirements", {
          "Código del requisito": `REQ_${run}`,
          Descripción: "Material needed for installation",
          "Tipo de ítem": "MATERIAL",
          "Cantidad requerida": 10,
          UOM: "EA",
          "ID de paquete Procurement": pkg,
          "Necesario en sitio": date(5),
          "Referencia canónica de origen": ifc,
        })
      );
      await action(buyer.page, "Requirements", requirement, req, "Activar requisito", `/requirements/${req}/actions`);
      await action(
        buyer.page,
        pack,
        packages,
        pkg,
        "Agregar ítem al paquete",
        `/packages/${pkg}/items`,
        {
          "ID del requisito": req,
          Cantidad: 10,
          UOM: "EA",
        },
        201
      );
      await shot(
        buyer.page,
        panel(buyer.page, packages).getByRole("heading", { level: 4 }),
        "02-package-and-requirement"
      );
      mark("IFC_PINNED_REQUIREMENT_PACKAGE_PWP_DISTINCT");

      stage = "requisition";
      const reqId = identity(
        await create(buyer.page, "Requisitions", "Requisiciones", "/requisitions", {
          "Número de requisición": `PR_${run}`,
          "ID del paquete": pkg,
          Moneda: "USD",
          "Fecha de emisión": date(),
          "Fecha requerida": date(5),
          "Referencia CDE (document_id, attachment_id)": cde,
          "Número de línea 1": 1,
          "ID del requisito 1": req,
          "Descripción 1": "Site installation parts",
          "Cantidad 1": 10,
          "UOM 1": "EA",
          "Fecha requerida 1": date(5),
        })
      );
      await action(
        buyer.page,
        "Requisitions",
        "Requisiciones",
        reqId,
        "Enviar requisición",
        `/requisitions/${reqId}/actions`
      );
      const approver = await session("req_approver");
      expect(
        (
          await action(
            approver.page,
            "Requisitions",
            "Requisiciones",
            reqId,
            "Aprobar requisición",
            `/requisitions/${reqId}/actions`
          )
        ).status
      ).toBe("APPROVED");
      await shot(
        approver.page,
        panel(approver.page, "Requisiciones").getByRole("heading", { level: 4 }),
        "03-requisition"
      );
      await approver.context.close();
      mark("REQUISITION_DISTINCT_APPROVAL");

      stage = "sourcing-rfq-vendors";
      const cataloger = await session("admin");
      const vendors: number[] = [];
      for (const count of [1, 2]) {
        vendors.push(
          identity(
            await create(cataloger.page, "RFQ", "Proveedores", "/vendors", {
              "Código del proveedor": `V${count}_${run}`,
              "Razón social": `O2B isolated vendor ${count}`,
              "Nombre comercial": `Vendor ${count}`,
              "Identificación fiscal": `ID_${run}_${count}`,
              "País (ISO de dos letras)": "CO",
            })
          )
        );
      }
      await cataloger.context.close();
      const rfq = identity(
        await create(buyer.page, "RFQ", "RFQs", "/rfqs", {
          "Número de RFQ": `RFQ_${run}`,
          "ID del paquete": pkg,
          "ID de requisición": reqId,
          "Fecha de emisión": date(),
          "Fecha de cierre": date(2),
        })
      );
      for (const vendor of vendors)
        await action(
          buyer.page,
          "RFQ",
          "RFQs",
          rfq,
          "Invitar proveedor",
          `/rfqs/${rfq}/invitations`,
          { "ID del proveedor": vendor },
          201
        );
      const issuer = await session("rfq_issuer");
      expect((await action(issuer.page, "RFQ", "RFQs", rfq, "Emitir RFQ", `/rfqs/${rfq}/actions`)).status).toBe(
        "ISSUED"
      );
      await shot(issuer.page, panel(issuer.page, "RFQs").getByRole("heading", { level: 4 }), "04-rfq");
      mark("RFQ_TWO_INVITES_INDEPENDENT_ISSUANCE");

      stage = "bids-and-evaluations";
      const bids: number[] = [];
      for (const vendor of vendors)
        bids.push(
          identity(
            await create(buyer.page, "Bid Evaluation", "Ofertas", "/bids", {
              "ID de RFQ": rfq,
              "ID de proveedor": vendor,
              Moneda: "USD",
              "Valor ofertado": 100 + vendor,
              "Válida hasta": date(5),
              "Referencia CDE (document_id, attachment_id)": cde,
            })
          )
        );
      await shot(buyer.page, panel(buyer.page, "Ofertas").getByRole("table", { name: "Ofertas" }), "05-two-bids");
      await action(issuer.page, "RFQ", "RFQs", rfq, "Cerrar RFQ", `/rfqs/${rfq}/actions`);
      await issuer.context.close();
      for (const [role, type] of [
        ["technical", "TECHNICAL"],
        ["commercial", "COMMERCIAL"],
      ] as const) {
        const evaluator = await session(role);
        await create(evaluator.page, "Bid Evaluation", "Evaluaciones", "/evaluations", {
          "ID de oferta": bids[0],
          "Tipo de evaluación": type,
          Resultado: "ACCEPTED",
          Puntaje: 95,
          Recomendación: "RECOMMEND",
          ...(type === "TECHNICAL" ? { "Referencia de Ingeniería": ifc } : {}),
        });
        await shot(
          evaluator.page,
          panel(evaluator.page, "Evaluaciones").getByRole("heading", { level: 4 }),
          `06-evaluation-${role}`
        );
        await evaluator.context.close();
      }
      mark("BIDS_AND_EVALUATIONS_ARE_SEPARATE");

      stage = "award-and-po";
      const awarder = await session("award_approver");
      const award = identity(
        await create(awarder.page, "Awards", "Adjudicaciones", "/awards", {
          "ID de RFQ": rfq,
          "ID de oferta seleccionada": bids[0],
          "Referencia de aprobación": `AWD_${run}`,
        })
      );
      expect(records((await read(buyer.token, "/purchase-orders")).items)).toHaveLength(0);
      await shot(awarder.page, panel(awarder.page, "Adjudicaciones").getByRole("heading", { level: 4 }), "07-award");
      await awarder.context.close();
      const po = identity(
        await create(buyer.page, "Purchase Orders", orders, "/purchase-orders", {
          "Número de PO": `PO_${run}`,
          "ID de adjudicación": award,
          "ID del proveedor": vendors[0],
          "ID del paquete": pkg,
          Moneda: "USD",
          "Fecha de emisión": date(),
          "Fecha efectiva": date(),
          "Entrega prevista": date(5),
          "Número de línea 1": 1,
          "ID del requisito 1": req,
          "Descripción 1": "Parts",
          "Cantidad 1": 10,
          "UOM 1": "EA",
          "Precio unitario 1": 10,
          "Fecha solicitada 1": date(5),
        })
      );
      const poApprover = await session("po_approver");
      await action(poApprover.page, "Purchase Orders", orders, po, "Aprobar PO", `/purchase-orders/${po}/actions`);
      expect(
        (await action(poApprover.page, "Purchase Orders", orders, po, "Emitir PO", `/purchase-orders/${po}/actions`))
          .status
      ).toBe("ISSUED");
      const line = identity(records((await read(buyer.token, `/purchase-orders/${po}`)).lines)[0]);
      await shot(
        poApprover.page,
        panel(poApprover.page, orders).getByRole("heading", { level: 4 }),
        "08-purchase-order"
      );
      await poApprover.context.close();
      mark("AWARD_DOES_NOT_AUTO_CREATE_PO_INDEPENDENT_APPROVAL");

      stage = "physical-demand-expediting-inspection";
      const material = await session("material");
      const item = identity(
        await create(material.page, "Requirements", "Catálogo físico de materiales", "/material-items", {
          "Código de material": `ITEM_${run}`,
          Descripción: "Physical install item",
          UOM: "EA",
          "Categoría de material": "GENERAL",
        })
      );
      const demand = identity(
        await create(material.page, "Requirements", "Necesidades físicas de material", "/material-requirements", {
          "Código del requisito físico": `MAT_${run}`,
          "ID del material": item,
          "ID del requisito de Procurement": req,
          "Cantidad requerida": 10,
          UOM: "EA",
          "Necesario en sitio": date(5),
          "Tipo de referencia física": "MTO",
          "Evidencia MTO/BOM CDE (document_id, attachment_id)": cde,
        })
      );
      await map(buyer.page, "MATERIAL_REQUIREMENT", demand, "IWP", data.iwp_id);
      await create(material.page, "Vendor Progress / Expediting", "Hitos de fabricación", "/vendor-milestones", {
        "ID de línea PO": line,
        "Código del hito": "MANUFACTURED",
        "Fecha prevista": date(),
        "Fecha real": date(),
      });
      await create(material.page, "Vendor Progress / Expediting", "Eventos de expediting", "/expediting-events", {
        "ID de línea PO": line,
        "Tipo de evento": "FABRICATION_PROGRESS",
        "Fecha de observación": date(),
        "Porcentaje de fabricación": 100,
        Detalle: "Fabrication complete",
      });
      await shot(
        material.page,
        panel(material.page, "Eventos de expediting").getByRole("heading", { level: 4 }),
        "09-expediting"
      );
      const inspector = await session("inspector");
      const inspection = identity(
        await create(inspector.page, "Inspections", "Inspecciones", "/inspections", {
          "ID de línea PO": line,
          "Tipo de inspección": "FACTORY",
          "Fecha de inspección": date(),
        })
      );
      await inspector.context.close();
      const acceptor = await session("acceptor");
      expect(
        (
          await action(
            acceptor.page,
            "Inspections",
            "Inspecciones",
            inspection,
            "Decidir inspección",
            `/inspections/${inspection}/decision`,
            {
              "Resultado de inspección": "ACCEPTED",
              Detalle: "Conforming items",
              "Evidencia documental": cde,
            }
          )
        ).status
      ).toBe("ACCEPTED");
      await shot(
        acceptor.page,
        panel(acceptor.page, "Inspecciones").getByRole("heading", { level: 4 }),
        "10-inspection"
      );
      mark("PHYSICAL_REQUIREMENT_MILESTONE_INSPECTION_DISTINCT");

      stage = "shipment-and-receipt";
      const logistics = await session("logistician");
      const shipment = identity(
        await create(logistics.page, "Shipments", "Embarques", "/shipments", {
          "Número de embarque": `SHIP_${run}`,
          "ID de proveedor": vendors[0],
          Origen: "Factory",
          Destino: "Site",
          "Modo de transporte": "ROAD",
          "Arribo previsto": date(),
          "ID de línea PO 1": line,
          "ID del requisito físico 1": demand,
          "Cantidad 1": 10,
          "UOM 1": "EA",
        })
      );
      for (const status of ["READY_FOR_DISPATCH", "DISPATCHED", "IN_TRANSIT", "ARRIVED"]) {
        await action(
          logistics.page,
          "Shipments",
          "Embarques",
          shipment,
          "Registrar transición de embarque",
          `/shipments/${shipment}/transition`,
          {
            "Nuevo estado del embarque": status,
            "Fecha del evento": date(),
          }
        );
      }
      expect(records((await read(buyer.token, "/material-receipts")).items)).toHaveLength(0);
      const shipmentLine = identity(records((await read(buyer.token, `/shipments/${shipment}`)).lines)[0]);
      await shot(
        logistics.page,
        panel(logistics.page, "Embarques").getByRole("heading", { level: 4 }),
        "11-shipment-arrived-not-received"
      );
      await logistics.context.close();
      const receiver = await session("receiver");
      const receipt = identity(
        await create(receiver.page, "Material Receipts", "Recepciones de material", "/material-receipts", {
          "Número de recepción": `REC_${run}`,
          "ID de embarque": shipment,
          Ubicación: "Site",
          "Recepción UTC": new Date().toISOString().slice(0, 16),
          "Evidencia de recepción CDE": cde,
          "ID de línea de embarque 1": shipmentLine,
          "Cantidad 1": 10,
          "UOM 1": "EA",
        })
      );
      await receiver.context.close();
      const receiptLine = identity(records((await read(buyer.token, `/material-receipts/${receipt}`)).lines)[0]);
      const afterReceipt = await read(
        buyer.token,
        `/material-availability?work_package_id=${data.iwp_id}&as_of=${date()}`
      );
      expect(afterReceipt.status).not.toBe("READY");
      await action(
        acceptor.page,
        "Material Receipts",
        "Recepciones de material",
        receipt,
        "Clasificar recepción",
        `/material-receipts/${receipt}/acceptance`,
        {
          "ID de línea de recepción": receiptLine,
          "ID de inspección": inspection,
          "Cantidad aceptada": 10,
          "Cantidad rechazada": 0,
          "Cantidad en cuarentena": 0,
          Detalle: "Independent site acceptance",
        },
        201
      );
      await shot(
        acceptor.page,
        panel(acceptor.page, "Recepciones de material").getByRole("heading", { level: 4 }),
        "12-receipt-and-acceptance"
      );
      await acceptor.context.close();
      mark("ARRIVAL_RECEIPT_ACCEPTANCE_ARE_SEPARATE");

      stage = "availability-and-awp";
      await create(material.page, "Material Receipts", "Asignaciones físicas", "/material-allocations", {
        "ID de línea aceptada": receiptLine,
        "ID del requisito físico": demand,
        "ID del CWP o IWP": data.iwp_id,
        Cantidad: 10,
        UOM: "EA",
        "Fecha de asignación": date(),
        "Ubicación de origen": "Site",
      });
      await tab(material.page, "Material Availability");
      const availability = panel(material.page, "Disponibilidad y Readiness");
      await setValues(availability, {
        "ID del CWP o IWP para disponibilidad": data.iwp_id,
        "Fecha de corte de disponibilidad": date(),
      });
      await button(availability, "Consultar disponibilidad").click();
      await expect(availability.getByText("READY", { exact: true }).first()).toBeVisible();
      const assessedMaterial = await read(
        material.token,
        `/material-availability?work_package_id=${data.iwp_id}&as_of=${date()}`
      );
      expect(assessedMaterial.status).toBe("READY");
      observations.material_evidence_hash = assessedMaterial.evidence_hash;
      await shot(
        material.page,
        availability.getByText("READY", { exact: true }).first(),
        "13-material-availability-ready"
      );
      const awp = await session("awp_manager", false, `/workspaces/${workspace}/awp`);
      await button(awp.page.getByRole("navigation", { name: "AWP submodules" }), "Readiness").click();
      await field(awp.page, "Readiness Package").selectOption(String(data.iwp_id));
      const awpForm = awp.page.locator("form").filter({ has: button(awp.page, "Evaluar Package Readiness") });
      await field(awpForm, "Readiness as of").fill(date());
      await field(awp.page, "Motivo AWP").fill(reason);
      const assessed = await command(
        awp.page,
        awpForm,
        "Evaluar Package Readiness",
        `/packages/${data.iwp_id}/assess`,
        201,
        ""
      );
      const current = await read(awp.token, "/overview", awpRoot);
      const currentPackage = records(current.packages).find((row) => row.id === data.iwp_id);
      expect(currentPackage?.release_state).toBe("NOT_RELEASED");
      expect(assessed.source_hashes).toMatchObject({ material: assessedMaterial.evidence_hash });
      observations.awp_assessment_id = assessed.id;
      observations.awp_release_state = currentPackage?.release_state;
      observations.awp_readiness_state = assessed.readiness_state;
      await shot(
        awp.page,
        awp.page.getByRole("table", { name: "Workfront Readiness" }),
        "14-awp-consumed-not-released"
      );
      mark("MATERIAL_READY_CONSUMED_BY_AWP_NO_RELEASE");

      stage = "history-and-performance";
      await tab(buyer.page, "History");
      const history = panel(buyer.page, "Consulta History");
      await expect(history.getByRole("table", { name: "History" })).toBeVisible();
      await shot(buyer.page, history.getByRole("table", { name: "History" }), "15-history");
      const endpoints = [
        ["Procurement Register", "/status"],
        ["Procurement Package detail", `/packages/${pkg}`],
        ["RFQ queue", "/rfqs"],
        ["PO register", "/purchase-orders"],
        ["Expediting queue", "/expediting-events"],
        ["Shipment register", "/shipments"],
        ["Material Availability", `/material-availability?work_package_id=${data.iwp_id}&as_of=${date()}`],
        ["Procurement Look-Ahead", "/lookahead"],
      ];
      for (const [operation, endpoint] of endpoints) {
        const samples: number[] = [];
        let size = 0;
        let count = 0;
        for (let index = 0; index < 3; index++) {
          const start = performance.now();
          const data = await read(buyer.token, endpoint);
          samples.push(performance.now() - start);
          size = Buffer.byteLength(JSON.stringify(data), "utf8");
          count =
            typeof data.total === "number"
              ? data.total
              : Array.isArray(data.items)
                ? data.items.length
                : Array.isArray(data.requirements)
                  ? data.requirements.length
                  : 1;
        }
        timings.push({
          operation,
          route: endpoint,
          samples_ms: samples,
          median_ms: [...samples].sort((a, b) => a - b)[1],
          record_count: count,
          response_json_bytes: size,
        });
      }
      observations.register_size = records((await read(buyer.token, "/packages?limit=200")).items).length;
      expect(errors).toHaveLength(0);
      mark("HISTORY_AND_LOCAL_OBSERVATIONS");
      result = "PASS";
    } finally {
      if (result !== "PASS")
        await lastPage?.screenshot({ path: path.join(output, "failure.png") }).catch(() => undefined);
      writeFileSync(
        path.join(output, "browser-uat.json"),
        JSON.stringify(
          {
            result,
            stage,
            project_workspace_id: workspace,
            as_of_utc: date(),
            checks,
            observations,
            mutations,
            browser_errors: errors,
          },
          null,
          2
        )
      );
      writeFileSync(
        path.join(output, "performance.json"),
        JSON.stringify(
          {
            result: timings.length === 8 ? "MEASURED" : "PENDING",
            scope: "local isolated stack; not production SLA",
            register_size: observations.register_size ?? 0,
            operations: timings,
          },
          null,
          2
        )
      );
      for (const { context } of sessions.values()) await context.close();
    }
  });
});
