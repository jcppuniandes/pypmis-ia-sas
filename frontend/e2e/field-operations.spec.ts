import { test, expect, type Page, type Locator, type BrowserContext } from "@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

type Row = Record<string, any>;
const manifest = process.env.E2E_O3A_FIXTURE;
const data: Row | null = manifest ? JSON.parse(readFileSync(manifest, "utf8")) : null;
const api = process.env.E2E_API_URL ?? "http://127.0.0.1:8863";
const app = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5523";
const out = path.resolve(process.env.E2E_O3A_OUTPUT ?? "../outputs/.qa/wave-o3a-20261118/chromium");
const reason = "O3A validación gobernada real de campo y consumo independiente";
const button = (scope: Page | Locator, name: string) => scope.getByRole("button", { name, exact: true });
const field = (scope: Page | Locator, name: string) => scope.getByLabel(name, { exact: true });
const form = (scope: Page | Locator, name: string) => scope.getByRole("form", { name, exact: true });

test.describe("O3A Field Operations real Chromium release gate", () => {
  test.skip(!data, "Requires explicitly disposable O3A real-domain upstream fixture");
  test.use({ actionTimeout: 45_000, navigationTimeout: 120_000 });
  test("ADMIN profile and USER field chain with native consumer decisions", async ({ browser, request }) => {
    test.setTimeout(1_500_000);
    if (!data) throw new Error("Missing isolated fixture");
    expect(data.project_workspace_id).not.toBe(14);
    expect(new URL(api).port).toBe("8863");
    expect(new URL(app).port).toBe("5523");
    mkdirSync(out, { recursive: true });
    const contexts: BrowserContext[] = [];
    const steps: Row[] = [];
    const errors: Row[] = [];
    const observed: Row = {};
    let stage = "admin";
    let lastPage: Page | undefined;
    let passed = false;
    const prefix = `/api/v1/field-operations/projects/${data.project_workspace_id}`;
    const route = `/workspaces/${data.project_workspace_id}/field-operations`;
    const effective = data.effective_at;
    const now = new Date();
    const instant = new Date(now.valueOf() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
    const document = `${data.document_id}:${data.attachment_id}`;
    const run = Date.now().toString(36).toUpperCase();
    async function session(role: string, target = route, admin = false) {
      const response = await request.post(`${api}/api/v1/auth/login`, {
        data: { tenant_id: data!.tenant_id, email: data!.users[role], password: data!.password },
        timeout: 120_000,
      });
      expect(response.status(), `Real login ${role}`).toBe(200);
      const auth = await response.json();
      const context = await browser.newContext({ baseURL: app, viewport: { width: 1440, height: 960 } });
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
      page.on("pageerror", (error) => errors.push({ role, message: error.message }));
      await page.goto(admin ? "/app" : target);
      if (admin) {
        await button(page, "Cambiar a ADMIN MODE").click({ timeout: 180_000 });
        for (const name of ["Platform Administration", "Process Configuration"]) {
          const group = button(page, name);
          if ((await group.getAttribute("aria-expanded")) !== "true") await group.click();
        }
        await button(page, "Process & Operational Configuration").click();
        await button(page, "Field Operations Profiles").click();
        await expect(page.getByRole("region", { name: "Field Operations Profiles", exact: true })).toBeVisible();
      } else if (target === route) {
        await expect(page.getByRole("navigation", { name: "Field Operations Manager submodules" })).toBeVisible({
          timeout: 180_000,
        });
      }
      return page;
    }
    async function fill(scope: Page | Locator, values: Record<string, string | number>) {
      for (const [label, value] of Object.entries(values)) {
        const control = field(scope, label);
        const tag = await control.evaluate((element) => element.tagName);
        if (tag === "SELECT") await control.selectOption(String(value));
        else await control.fill(String(value));
      }
    }
    async function submit(page: Page, name: string, routePath: string, expected = 201) {
      lastPage = page;
      const control = form(page, name);
      const reasonField = field(control, "Motivo operacional");
      if (await reasonField.count()) await reasonField.fill(reason);
      const response = page.waitForResponse(
        (r) => new URL(r.url()).pathname === routePath && r.request().method() !== "GET",
        { timeout: 120_000 }
      );
      await button(control, name).click();
      const result = await response;
      const row = await result.json();
      expect(result.status(), `${stage}/${name}: ${JSON.stringify(row)}`).toBe(expected);
      steps.push({ stage, action: name, path: routePath, status: result.status(), id: row.id });
      return row;
    }
    async function tab(page: Page, name: string) {
      await button(page.getByRole("navigation", { name: "Field Operations Manager submodules" }), name).click();
    }
    async function create(
      page: Page,
      view: string,
      name: string,
      values: Row,
      endpoint: string,
      configure?: (scope: Locator) => Promise<void>
    ) {
      lastPage = page;
      await tab(page, view);
      await button(page, "Nuevo registro").click();
      const control = form(page, name);
      await fill(control, values);
      if (configure) await configure(control);
      return submit(page, name, prefix + endpoint);
    }
    async function act(page: Page, view: string, row: Row, name: string, endpoint: string) {
      lastPage = page;
      await tab(page, view);
      await button(page, `Ver ${view} ${row.id}`).click();
      await button(page, `${name}…`).click();
      return submit(page, name, `${prefix}${endpoint}/${row.id}/actions`, 200);
    }
    async function pin(control: Locator, name: string, identity: number, kind?: string) {
      if (kind) await field(control, `Tipo ${name}`).selectOption(kind);
      await field(control, `ID ${name}`).fill(String(identity));
      await button(control, `Consultar ${name}`).click();
      await button(control, `Usar ${name}`).click();
    }
    try {
      const admin = await session("field_configurator", route, true);
      await expect(admin.getByRole("table", { name: "Perfiles de campo" })).toBeVisible();
      const published = admin
        .getByRole("table", { name: "Perfiles de campo" })
        .locator("tbody tr")
        .filter({ hasText: /published/i });
      let draft: Row;
      if (await published.count()) {
        const existing = published.first();
        const existingId = await existing.locator("td").first().innerText();
        await existing.getByRole("button").click();
        await button(admin, "Crear sucesor…").click();
        draft = await submit(admin, "Crear sucesor", `/api/v1/field-operations/admin/profiles/${existingId}/successor`);
      } else {
        await button(admin, "Nuevo perfil de campo").click();
        await fill(form(admin, "Crear borrador de campo"), {
          "Código del perfil de campo": `BROWSER-${run}`,
          "Nombre del perfil de campo": "O3A Chromium controlled profile",
          "Motivo del perfil de campo": reason,
        });
        draft = await submit(admin, "Crear borrador de campo", "/api/v1/field-operations/admin/profiles");
      }
      await fill(form(admin, "Guardar borrador de campo"), {
        "Nombre del perfil de campo": "O3A Chromium controlled profile",
        "Motivo del perfil de campo": reason,
        "Política de producción": JSON.stringify({
          require_released_iwp: true,
          require_engineering_ifc: true,
          require_material_ready: true,
          require_daily_report_approval_for_consumption: true,
          allowed_non_iwp_reasons: [
            "ENABLING_WORKS",
            "EMERGENCY_WORK",
            "SURVEY",
            "TEMPORARY_WORKS",
            "SUPPORT_ACTIVITY",
            "CORRECTIVE_WORK",
            "NON_IWP_ACTIVITY",
          ],
        }),
      });
      const profile = await submit(
        admin,
        "Guardar borrador de campo",
        `/api/v1/field-operations/admin/profiles/${draft.id}`,
        200
      );
      observed.profile = profile.id;
      const publisher = await session("field_publisher", route, true);
      const profileRow = publisher
        .getByRole("table", { name: "Perfiles de campo" })
        .locator("tbody tr")
        .filter({ has: publisher.locator(`td:first-child:text-is("${profile.id}")`) });
      await profileRow.getByRole("button").click();
      await button(publisher, "Publicar perfil…").click();
      await submit(publisher, "Publicar perfil", `/api/v1/field-operations/admin/profiles/${profile.id}/publish`, 200);
      await expect(
        publisher.getByRole("heading", { name: "O3A Chromium controlled profile · PUBLISHED", exact: true })
      ).toBeVisible();
      await publisher.screenshot({ path: path.join(out, "01-published-profile.png") });
      stage = "field";
      const [reporter, supervisor, approver] = await Promise.all([
        session("field_reporter"),
        session("field_supervisor"),
        session("field_approver"),
      ]);
      const front = await create(
        reporter,
        "Workfronts",
        "Crear frente de trabajo",
        {
          "Código del frente": `FRONT-${run}`,
          "Título del frente": "O3A Browser installation front",
          "Ubicación canónica": data.scope_item_id,
          CWA: data.cwa_id,
          IWP: data.iwp_id,
          "Responsable ID": data.user_ids.field_supervisor,
          "Inicio previsto": effective,
          "Fin previsto": effective,
        },
        "/workfronts"
      );
      await act(supervisor, "Workfronts", front, "Activar frente", "/workfronts");
      observed.workfront = front.id;
      const shift = await create(
        reporter,
        "Shifts",
        "Abrir turno",
        {
          "Código del turno": `SHIFT-${run}`,
          "Tipo de turno": "DAY",
          "Fecha del turno": effective,
          "Inicio del turno": `${effective}T00:00`,
          "Fin del turno": `${effective}T23:59`,
          "Frente de trabajo": front.id,
          "Supervisor ID": data.user_ids.field_supervisor,
        },
        "/shifts"
      );
      observed.shift = shift.id;
      const crew = await create(
        reporter,
        "Crews",
        "Registrar cuadrilla",
        {
          "Código de cuadrilla": `CREW-${run}`,
          "Descripción de cuadrilla": "Crew observed on site",
          Oficio: "CIVIL",
          "Proveedor Procurement ID": data.vendor_id,
          "Supervisor ID": data.user_ids.field_supervisor,
        },
        "/crews"
      );
      const equipment = await create(
        reporter,
        "Equipment References",
        "Vincular referencia de equipo",
        {
          "Sistema maestro": "EXTERNAL_ASSET_REFERENCE",
          "Identidad externa del equipo": `EQ-${run}`,
          "Descripción del equipo": "External equipment operational reference",
          "Tipo de equipo": "EXTERNAL_EQUIPMENT",
        },
        "/equipment-references"
      );
      observed.labor = (
        await create(
          reporter,
          "Labor",
          "Registrar uso de mano de obra",
          {
            "Código del uso": `LAB-${run}`,
            Turno: shift.id,
            "Frente de trabajo": front.id,
            Cuadrilla: crew.id,
            Oficio: "CIVIL",
            "Número de personas": 2,
            "Horas regulares": "8",
            "Horas extra": "1",
            "Horas productivas": "7",
            "Horas no productivas": "2",
          },
          "/labor"
        )
      ).id;
      observed.equipment = (
        await create(
          reporter,
          "Equipment Usage",
          "Registrar uso de equipo",
          {
            "Código del uso": `EQUS-${run}`,
            Turno: shift.id,
            "Frente de trabajo": front.id,
            "Referencia de equipo": equipment.id,
            "Tipo de uso de equipo": "PRODUCTION",
            "Horas operativas": "6",
            "Horas inactivas": "1",
            "Horas en espera": "1",
            "Horas fuera de servicio": "0",
          },
          "/equipment"
        )
      ).id;
      await create(
        reporter,
        "Conditions",
        "Registrar condiciones de campo",
        {
          "Código de condición": `COND-${run}`,
          "Fecha de condición": effective,
          Turno: shift.id,
          "Frente de trabajo": front.id,
          "Ubicación de condición": data.scope_item_id,
          "Condición meteorológica": "CLEAR",
          "Condición de acceso": "AVAILABLE",
          "Condiciones del sitio": "Access observed and available",
          "Fuente de observación": "Field supervisor",
        },
        "/conditions"
      );
      const report = await create(
        reporter,
        "Daily Reports",
        "Crear reporte diario",
        {
          "Número de reporte": `DCR-${run}`,
          "Fecha del reporte": effective,
          Turno: shift.id,
          "Parte reportante": "Construction site supervision",
          "Adjuntos CDE": document,
        },
        "/daily-reports"
      );
      observed.report = report.id;
      const production = await create(
        reporter,
        "Production Records",
        "Registrar producción observada",
        {
          "Código de producción": `PROD-${run}`,
          "Frente de trabajo": front.id,
          Turno: shift.id,
          "Reporte diario": report.id,
          "Elemento Scope": data.scope_item_id,
          "Plan item": data.plan_item_id,
          IWP: data.iwp_id,
          "Cantidad observada": "2",
          "Cantidad planificada": "3",
          "Unidad de producción": data.scope_unit,
          "Tipo de producción": "INSTALLED",
          "Fecha y hora de observación": instant,
          "Referencia de origen": "Browser observed installation with real CDE evidence",
          "Evidencia CDE": document,
        },
        "/production",
        async (control) => {
          await pin(control, "Revisión IFC de ejecución", data.ifc_id);
          await pin(control, "Referencia de material", data.material_allocation_id, "MATERIAL_ALLOCATION");
        }
      );
      observed.production = production.id;
      await act(supervisor, "Production Records", production, "Verificar producción", "/production");
      const event = await create(
        reporter,
        "Field Events",
        "Registrar evento de campo",
        {
          "Código del evento": `EVENT-${run}`,
          "Frente de trabajo": front.id,
          Turno: shift.id,
          "Tipo de evento": "ACCESS_ISSUE",
          "Fecha y hora del evento": instant,
          "Título del evento": "Observed temporary access issue",
          "Descripción del evento": "Facts only with no contractual decision",
          "Evidencia CDE": document,
        },
        "/events"
      );
      observed.event = event.id;
      const instruction = await create(
        reporter,
        "Site Instructions",
        "Preparar instrucción de sitio",
        {
          "Número de instrucción": `INS-${run}`,
          "Tipo de instrucción": "GENERAL",
          "Fecha de instrucción": effective,
          Emisor: "Site supervision",
          Receptor: "Field contractor",
          "Frente de trabajo": front.id,
          "Scope relacionado": data.scope_item_id,
          "IWP relacionado": data.iwp_id,
          "Descripción de instrucción": "Operational coordination only no change order",
          "Evidencia CDE": document,
        },
        "/instructions"
      );
      const issuer = await session("field_instruction_issuer");
      observed.instruction = (
        await act(issuer, "Site Instructions", instruction, "Emitir instrucción", "/instructions")
      ).id;
      const constraint = await create(
        reporter,
        "Constraints Observed",
        "Registrar restricción observada",
        {
          "Código de observación": `CON-${run}`,
          "Tipo de restricción observada": "ACCESS",
          "Frente de trabajo": front.id,
          "IWP observado": data.iwp_id,
          "Fecha de observación": effective,
          "Descripción de restricción": "Observed access coordination constraint",
          "Evidencia CDE": document,
        },
        "/constraints"
      );
      observed.constraint = constraint.id;
      await act(supervisor, "Constraints Observed", constraint, "Verificar observación", "/constraints");
      observed.material_consumption = (
        await create(
          reporter,
          "Material Consumption",
          "Registrar material consumido",
          {
            "Código de consumo": `CONS-${run}`,
            "Producción verificada": production.id,
            "Material Procurement": data.material_item_id,
            "Fecha de consumo": effective,
            "Cantidad consumida": "1",
            "Unidad de material": "EA",
            "Evidencia CDE": document,
          },
          "/material-consumption",
          async (control) => {
            await pin(control, "Asignación material", data.material_allocation_id);
          }
        )
      ).id;
      await act(reporter, "Daily Reports", report, "Enviar reporte", "/daily-reports");
      await act(supervisor, "Daily Reports", report, "Revisar reporte", "/daily-reports");
      await act(approver, "Daily Reports", report, "Aprobar reporte", "/daily-reports");
      await expect(
        approver
          .getByRole("region", { name: "Hecho de campo seleccionado" })
          .locator("dd")
          .filter({ hasText: /^APPROVED$/ })
      ).toBeVisible();
      await approver.screenshot({ path: path.join(out, "02-approved-daily-report.png") });
      await act(reporter, "Shifts", shift, "Enviar turno", "/shifts");
      await act(approver, "Shifts", shift, "Aprobar turno", "/shifts");
      await act(approver, "Shifts", shift, "Cerrar turno", "/shifts");
      await tab(reporter, "History");
      await expect(reporter.getByRole("table", { name: "History", exact: true })).toBeVisible();
      await reporter.screenshot({ path: path.join(out, "03-field-history.png") });
      await tab(reporter, "Field Readiness");
      await fill(reporter, { "Frente de trabajo ID": front.id });
      await button(reporter, "Consultar Field Readiness").click();
      await expect(reporter.getByRole("table", { name: "Field Readiness", exact: true })).toBeVisible();
      await reporter.screenshot({ path: path.join(out, "08-field-readiness.png") });
      await tab(reporter, "Field Look-Ahead");
      await expect(reporter.getByRole("table", { name: "Frentes del horizonte", exact: true })).toBeVisible();
      await reporter.screenshot({ path: path.join(out, "09-field-lookahead.png") });
      await tab(reporter, "Trace");
      await fill(reporter, { "Tipo de entidad de campo": "PRODUCTION", "ID de entidad de campo": production.id });
      await button(reporter, "Consultar Trace").click();
      await expect(reporter.getByRole("table", { name: "Historial del hecho", exact: true })).toBeVisible();
      await reporter.screenshot({ path: path.join(out, "10-field-trace.png") });
      stage = "native-progress";
      const progress = await session("manager", `/workspaces/${data.project_workspace_id}/progress`);
      await button(progress, "Field Evidence").click();
      await fill(progress, { "Evidencia de campo ID": production.id });
      await button(progress, "Consultar origen de campo").click();
      const decision = form(progress, "Registrar decisión PROGRESS");
      await fill(decision, {
        "Decisión Progress": "ADOPT",
        "Cantidad a adoptar": "2",
        "Período de Progress": data.period_id,
        "Código de medición borrador": `FIELD-${run}`,
      });
      const adoption = await submit(
        progress,
        "Registrar decisión PROGRESS",
        `/api/v1/progress/projects/${data.project_workspace_id}/field-adoptions`
      );
      observed.progress_adoption = adoption.id;
      observed.measurement = adoption.linked_entity_id;
      await progress.screenshot({ path: path.join(out, "04-native-progress-adoption.png") });
      stage = "native-awp";
      const awp = await session("awp_manager", `/workspaces/${data.project_workspace_id}/awp`);
      await button(awp, "Field Evidence").click();
      await fill(awp, { "Evidencia de campo ID": constraint.id });
      await button(awp, "Consultar origen de campo").click();
      await fill(form(awp, "Registrar decisión AWP"), {
        "Decisión AWP": "ADOPT",
        "Tipo de restricción AWP": "ACCESS",
        "Código de restricción AWP": `FLD-${run}`,
      });
      observed.awp_adoption = (
        await submit(awp, "Registrar decisión AWP", `/api/v1/awp/projects/${data.project_workspace_id}/field-adoptions`)
      ).id;
      await awp.screenshot({ path: path.join(out, "05-native-awp-constraint.png") });
      stage = "native-cost";
      const cost = await session("cost_controller", `/workspaces/${data.project_workspace_id}/cost`);
      await button(cost, "Field Evidence").click();
      await fill(cost, { "Evidencia de campo ID": observed.labor });
      await button(cost, "Consultar origen de campo").click();
      await fill(form(cost, "Registrar decisión COST"), {
        "Decisión Cost": "ADOPT",
        "CBS de Cost": data.cbs_id,
        "Cost Code": data.cost_code_id,
        "Control Account": data.control_account_id,
      });
      observed.cost_adoption = (
        await submit(
          cost,
          "Registrar decisión COST",
          `/api/v1/cost/projects/${data.project_workspace_id}/field-adoptions`
        )
      ).id;
      await cost.screenshot({ path: path.join(out, "06-native-cost-evidence.png") });
      stage = "mobile";
      await reporter.setViewportSize({ width: 390, height: 844 });
      await tab(reporter, "Workfronts");
      await expect(button(reporter, "Nuevo registro")).toBeVisible();
      await reporter.screenshot({ path: path.join(out, "07-mobile-field.png") });
      expect(errors).toEqual([]);
      passed = true;
    } finally {
      if (!passed && lastPage)
        await lastPage.screenshot({ path: path.join(out, "failure.png"), fullPage: true }).catch(() => {});
      writeFileSync(
        path.join(out, "journey.json"),
        JSON.stringify({ passed, stage, steps, observed, errors }, null, 2)
      );
      for (const context of contexts) await context.close();
    }
  });
});
