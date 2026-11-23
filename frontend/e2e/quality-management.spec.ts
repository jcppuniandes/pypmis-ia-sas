import { test, expect, type Page, type Locator, type BrowserContext } from "@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

type Row = Record<string, any>;
const manifest = process.env.E2E_O3B_FIXTURE;
const data: Row | null = manifest ? JSON.parse(readFileSync(manifest, "utf8")) : null;
const api = process.env.E2E_API_URL ?? "http://127.0.0.1:8864";
const app = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5524";
const out = path.resolve(process.env.E2E_O3B_OUTPUT ?? "../outputs/.qa/wave-o3b-20261119/chromium");
const reason = "O3B validación real gobernada de calidad y decisiones nativas independientes";
const button = (scope: Page | Locator, name: string) => scope.getByRole("button", { name, exact: true });
const field = (scope: Page | Locator, name: string) => scope.getByLabel(name, { exact: true });
const form = (scope: Page | Locator, name: string) => scope.getByRole("form", { name, exact: true });
const instant = () => {
  const now = new Date();
  return new Date(now.valueOf() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
};

test.describe("O3B Quality Management real Chromium release gate", () => {
  test.skip(!data, "Requires explicitly disposable O3B upstream evidence and no precreated Quality facts");
  test.use({ actionTimeout: 45_000, navigationTimeout: 120_000 });
  test("ADMIN and USER lifecycle with inspections tests NCR rework acceptance and native consumers", async ({
    browser,
    request,
  }) => {
    test.setTimeout(1_800_000);
    if (!data) throw new Error("Missing isolated upstream fixture");
    expect(data.project_workspace_id).not.toBe(14);
    expect(new URL(api).port).toBe("8864");
    expect(new URL(app).port).toBe("5524");
    mkdirSync(out, { recursive: true });
    const contexts: BrowserContext[] = [];
    const steps: Row[] = [];
    const errors: Row[] = [];
    const observed: Row = {};
    const prefix = `/api/v1/quality/projects/${data.project_workspace_id}`;
    const route = `/workspaces/${data.project_workspace_id}/quality`;
    const document = `${data.document_id}:${data.attachment_id}`;
    const run = Date.now().toString(36).toUpperCase();
    let stage = "ADMIN";
    let lastPage: Page | undefined;
    let passed = false;
    async function session(role: string, target = route, admin = false) {
      const response = await request.post(`${api}/api/v1/auth/login`, {
        data: { tenant_id: data!.tenant_id, email: data!.users[role], password: data!.password },
        timeout: 120_000,
      });
      expect(response.status(), `Login ${role}`).toBe(200);
      const auth = await response.json();
      const context = await browser.newContext({ baseURL: app, viewport: { width: 1440, height: 1000 } });
      contexts.push(context);
      await context.addInitScript(
        (value) =>
          localStorage.setItem(
            "pypmis_auth",
            JSON.stringify({ state: { token: value.access_token, user: value.user }, version: 0 })
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
        await button(page, "Quality Management Profiles").click();
        await expect(page.getByRole("region", { name: "Quality Management Profiles", exact: true })).toBeVisible();
      } else if (target === route) {
        await expect(page.getByRole("navigation", { name: "Quality Manager submodules" })).toBeVisible({
          timeout: 180_000,
        });
      }
      return page;
    }
    async function fill(scope: Page | Locator, values: Row) {
      for (const [label, value] of Object.entries(values)) {
        const control = field(scope, label);
        const tag = await control.evaluate((element) => element.tagName);
        if (tag === "SELECT") {
          await expect(control.locator(`option[value="${String(value)}"]`)).toBeAttached();
          await control.selectOption(String(value));
        } else await control.fill(String(value));
      }
    }
    async function submit(page: Page, name: string, endpoint: string, status = 201) {
      lastPage = page;
      const control = form(page, name);
      await expect(control).toBeVisible();
      if (await field(control, "Motivo operacional").count()) await field(control, "Motivo operacional").fill(reason);
      const pending = page.waitForResponse(
        (response) => new URL(response.url()).pathname === endpoint && response.request().method() !== "GET",
        { timeout: 120_000 }
      );
      await button(control, name).click();
      const response = await pending;
      const row = await response.json();
      expect(response.status(), `${stage}/${name}: ${JSON.stringify(row)}`).toBe(status);
      steps.push({ stage, action: name, path: endpoint, status: response.status(), id: row.id });
      console.log(`${stage}: ${name} → ${row.id ?? response.status()}`);
      writeFileSync(path.join(out, "running.json"), JSON.stringify({ stage, steps, observed }, null, 2));
      return row;
    }
    async function selectRecord(page: Page, title: string, identity: number) {
      const row = page
        .getByRole("table", { name: title, exact: true })
        .locator("tbody tr")
        .filter({ has: page.locator(`td:first-child:text-is("${identity}")`) });
      await row.getByRole("button").click();
    }
    async function tab(page: Page, view: string) {
      await button(page.getByRole("navigation", { name: "Quality Manager submodules" }), view).click();
      await button(page, "Actualizar Quality").click();
    }
    async function create(
      page: Page,
      view: string,
      name: string,
      values: Row,
      endpoint: string,
      configure?: (panel: Locator) => Promise<void>
    ) {
      await tab(page, view);
      const panel = page.getByRole("region", { name: view, exact: true });
      await button(panel, "Nuevo registro Quality").click();
      await fill(form(page, name), values);
      if (configure) await configure(panel.locator(".qualityForm"));
      return submit(page, name, prefix + endpoint);
    }
    async function act(
      page: Page,
      view: string,
      row: Row,
      name: string,
      endpoint: string,
      configure?: (panel: Locator) => Promise<void>
    ) {
      await tab(page, view);
      await selectRecord(page, view, row.id);
      await button(page, `${name}…`).click();
      if (configure)
        await configure(page.getByRole("region", { name: "Registro Quality seleccionado" }).locator(".qualityForm"));
      return submit(page, name, `${prefix}${endpoint}/${row.id}/actions`, 200);
    }
    async function pin(scope: Locator, label: string, identity: number, kind?: string, native = false) {
      if (kind) await field(scope, `Tipo ${label}`).selectOption(kind);
      await field(scope, `ID ${label}`).fill(String(identity));
      await button(scope, `Consultar ${label}`).click();
      await button(scope, `${native ? "Usar" : "Fijar"} ${label}`).click();
    }
    async function evidence(scope: Locator, label = "Evidencia CDE") {
      await fill(scope, { [label]: document });
    }
    try {
      const admin = await session("quality_configurator", route, true);
      await button(admin, "Nuevo perfil Quality").click();
      await fill(form(admin, "Crear borrador Quality"), {
        "Código del perfil Quality": `BROWSER-${run}`,
        "Nombre del perfil Quality": "O3B Chromium Quality profile",
      });
      const profile = await submit(admin, "Crear borrador Quality", "/api/v1/quality/admin/profiles");
      observed.profile = profile.id;
      const publisher = await session("quality_publisher", route, true);
      await selectRecord(publisher, "Perfiles Quality", profile.id);
      await button(publisher, "Publicar perfil Quality…").click();
      await submit(publisher, "Publicar perfil Quality", `/api/v1/quality/admin/profiles/${profile.id}/publish`, 200);
      await expect(
        publisher.getByRole("heading", { name: "O3B Chromium Quality profile · PUBLISHED", exact: true })
      ).toBeVisible();
      await publisher.screenshot({ path: path.join(out, "01-admin-published.png") });
      stage = "PLAN_ITP";
      const reporter = await session("quality_reporter");
      const inspector = await session("quality_inspector");
      const reviewer = await session("quality_reviewer");
      const approver = await session("quality_approver");
      const manager = await session("quality_manager");
      const owner = await session("ncr_owner");
      let plan = await create(
        reporter,
        "Quality Plans",
        "Crear plan de calidad",
        {
          "Código del plan": `PLAN-${run}`,
          "Título del plan": "O3B actual project quality plan",
          "Alcance del plan": "Verified installation and receiving conformity",
          "Responsable ID": data.user_ids.quality_manager,
          "Vigente desde": data.effective_at,
        },
        "/plans",
        (scope) => evidence(scope)
      );
      plan = await act(reporter, "Quality Plans", plan, "Enviar plan", "/plans");
      plan = await act(approver, "Quality Plans", plan, "Aprobar plan", "/plans");
      let itp = await create(
        reporter,
        "ITP",
        "Crear ITP",
        {
          "Código ITP": `ITP-${run}`,
          "Título ITP": "O3B controlled installation ITP",
          "Plan de calidad": plan.id,
          Disciplina: "CIVIL",
          "Vigente desde": data.effective_at,
          "Ámbitos canónicos ITP": JSON.stringify([{ target_kind: "IWP", target_id: data.iwp_id }]),
        },
        "/itps",
        async (scope) => {
          await pin(scope, "Requisito Engineering", data.ifc_id, "IFC_RELEASE");
          await evidence(scope);
        }
      );
      observed.itp = itp.id;
      const item = await create(
        reporter,
        "ITP Control Points",
        "Crear punto de control ITP",
        {
          ITP: itp.id,
          "Código del punto": `HOLD-${run}`,
          Secuencia: "10",
          "Actividad inspeccionada": "Installed concrete quality",
          "Tipo de control": "HOLD",
          "Requisito técnico": "Current accepted IFC requirement",
          "Criterio de aceptación": "Structured conformity and strength controls must pass",
          "Parte responsable": "Quality inspector",
          "Parte testigo": "Owner",
          "Plantilla de checklist": "GENERAL",
          "Exige ensayo": "true",
          "Tipo de ensayo": "CONCRETE_STRENGTH",
          "Unidad de ensayo": "MPa",
          "Límite inferior de ensayo": "30",
          "Límite superior de ensayo": "80",
        },
        "/itp-items"
      );
      observed.itp_item = item.id;
      itp = await act(reporter, "ITP", itp, "Enviar ITP", "/itps");
      await act(approver, "ITP", itp, "Aprobar ITP", "/itps");
      async function inspection(result: string, code: string, reinspection?: { failed: Row; action: Row }) {
        const view = reinspection ? "Reinspections" : "Inspection Requests";
        let req = await create(
          reporter,
          view,
          reinspection ? "Solicitar reinspección" : "Crear solicitud de inspección",
          {
            "Número de solicitud": code,
            "Punto ITP": item.id,
            "Fecha de solicitud": instant(),
            "Fecha prevista": instant(),
            "Inspector ID": data!.user_ids.quality_inspector,
            "Cantidad objeto": "1",
            "Unidad objeto": data!.scope_unit,
            "Tipo de inspección": reinspection ? "REINSPECTION" : "GENERAL",
            ...(reinspection
              ? { "Inspección original": reinspection.failed.id, "Acción correctiva": reinspection.action.id }
              : {}),
          },
          "/inspection-requests",
          async (scope) => {
            await pin(scope, "Objeto inspeccionado", data!.production_id);
            await evidence(scope);
          }
        );
        req = await act(reporter, view, req, "Enviar solicitud", "/inspection-requests");
        req = await act(inspector, view, req, "Programar solicitud", "/inspection-requests");
        req = await act(inspector, view, req, "Iniciar inspección o ensayo", "/inspection-requests");
        let record = await create(
          inspector,
          "Inspections",
          "Registrar inspección",
          { "Número de registro": code, "Resultado declarado": result, "Fecha real de inspección": instant() },
          "/inspections",
          async (scope) => {
            await pin(scope, "Requisito Engineering", data!.ifc_id);
            await fill(scope, { "Solicitud de inspección": req.id });
            await field(scope, "CONFORMITY Resultado").selectOption(result);
            await field(scope, "CONFORMITY Evidencia CDE").selectOption(document);
            await evidence(scope);
          }
        );
        record = await act(inspector, "Inspections", record, "Enviar resultado", "/inspections");
        return act(reviewer, "Inspections", record, "Cerrar resultado", "/inspections");
      }
      stage = "INSPECTION_TEST";
      const pass = await inspection("PASS", `PASS-${run}`);
      observed.pass = pass.id;
      let testRequest = await create(
        reporter,
        "Test Requests",
        "Crear solicitud de ensayo",
        {
          "Número de solicitud": `TEST-${run}`,
          "Punto ITP": item.id,
          "Fecha de solicitud": instant(),
          "Fecha prevista": instant(),
          "Inspector ID": data.user_ids.quality_inspector,
          "Cantidad objeto": "1",
          "Unidad objeto": data.scope_unit,
          "Tipo de ensayo": "CONCRETE_STRENGTH",
          "Laboratorio Vendor ID": data.vendor_id,
        },
        "/test-requests",
        async (scope) => {
          await pin(scope, "Objeto inspeccionado", data.production_id);
          await evidence(scope);
        }
      );
      testRequest = await act(reporter, "Test Requests", testRequest, "Enviar solicitud", "/test-requests");
      testRequest = await act(inspector, "Test Requests", testRequest, "Programar solicitud", "/test-requests");
      testRequest = await act(inspector, "Test Requests", testRequest, "Iniciar inspección o ensayo", "/test-requests");
      let testRecord = await create(
        inspector,
        "Tests",
        "Registrar ensayo",
        {
          "Número de registro": `TEST-${run}`,
          "Resultado declarado": "PASS",
          "Fecha real de ensayo": instant(),
          Método: "Compression",
          Estándar: "ASTM C39",
          "Laboratorio Vendor ID": data.vendor_id,
        },
        "/tests",
        async (scope) => {
          await pin(scope, "Requisito Engineering", data.ifc_id);
          await fill(scope, { "Solicitud de ensayo": testRequest.id });
          await button(scope, "Añadir medición").click();
          await fill(scope, {
            "Medición 1 Código": "CUBE-1",
            "Medición 1 Valor numérico": "36",
            "Medición 1 Unidad": "MPa",
            "Medición 1 Límite inferior": "30",
            "Medición 1 Límite superior": "80",
            "Medición 1 Resultado": "PASS",
          });
          await button(scope, "Añadir medición").click();
          await fill(scope, {
            "Medición 2 Código": "CUBE-2",
            "Medición 2 Valor numérico": "38",
            "Medición 2 Unidad": "MPa",
            "Medición 2 Límite inferior": "30",
            "Medición 2 Límite superior": "80",
            "Medición 2 Resultado": "PASS",
          });
          await evidence(scope);
        }
      );
      testRecord = await act(inspector, "Tests", testRecord, "Enviar resultado", "/tests");
      testRecord = await act(reviewer, "Tests", testRecord, "Cerrar resultado", "/tests");
      observed.test = testRecord.id;
      async function release(inspectionRecord: Row) {
        await tab(approver, "Hold and Witness Decisions");
        const panel = approver.getByRole("region", { name: "Hold and Witness Decisions", exact: true });
        await fill(panel, { "Punto ITP ID": item.id });
        await pin(panel, "Objeto del punto ITP", data!.production_id);
        await fill(form(approver, "Decidir punto de control"), {
          "Decisión del punto": "RELEASED",
          "Inspección cerrada ID": inspectionRecord.id,
          "Ensayo cerrado ID": testRecord.id,
          "Evidencia CDE": document,
        });
        return submit(approver, "Decidir punto de control", prefix + "/control-point-decisions");
      }
      await release(pass);
      const acceptanceCode = `ACCEPT-${run}`;
      async function accept(supersedes?: Row) {
        // Governed facts retain microseconds but this UI captures whole seconds.
        const boundary = Math.floor(Date.now() / 1000);
        await expect.poll(() => Math.floor(Date.now() / 1000), { timeout: 4000 }).toBeGreaterThan(boundary);
        return create(
          approver,
          "Quality Acceptance",
          "Registrar aceptación de calidad",
          {
            "Código de aceptación": acceptanceCode,
            "ITP aplicable": itp.id,
            "Perfil de aceptación": "COMPLETE_CONTROLS",
            "Cantidad aceptada": "1",
            "Unidad aceptada": data!.scope_unit,
            "Fecha efectiva de aceptación": instant(),
            ...(supersedes ? { "Aceptación sustituida": supersedes.id } : {}),
          },
          "/acceptances",
          async (scope) => {
            await pin(scope, "Objeto inspeccionado", data!.production_id);
            await evidence(scope);
          }
        );
      }
      const accepted = await accept();
      observed.acceptance = accepted.id;
      await approver.screenshot({ path: path.join(out, "02-acceptance.png") });
      stage = "NCR_REWORK_REINSPECTION";
      const failed = await inspection("FAIL", `FAIL-${run}`);
      observed.failed = failed.id;
      let ncr = await create(
        reporter,
        "NCR",
        "Registrar NCR",
        {
          "Número NCR": `NCR-${run}`,
          "Título NCR": "Observed installation defect",
          "Descripción NCR": "Actual non-conformity requires governed correction",
          "Categoría NCR": "WORKMANSHIP",
          "Severidad NCR": "MEDIUM",
          "Responsable ID": data.user_ids.ncr_owner,
          "Inspección relacionada": failed.id,
          "Requisito incumplido": "Current IFC workmanship requirement",
          "Fecha de detección": instant(),
          "Vencimiento NCR": data.effective_at,
        },
        "/ncrs",
        async (scope) => {
          await pin(scope, "Objeto inspeccionado", data.production_id);
          await evidence(scope);
        }
      );
      ncr = await act(reporter, "NCR", ncr, "Emitir NCR", "/ncrs");
      ncr = await act(reviewer, "NCR", ncr, "Revisar NCR", "/ncrs");
      let disposition = await create(
        manager,
        "Dispositions",
        "Preparar disposición NCR",
        {
          NCR: ncr.id,
          "Código de disposición": `DISP-${run}`,
          "Tipo de disposición": "REWORK",
          "Descripción de disposición": "Rework the original installation and reinspect",
        },
        "/dispositions",
        (scope) => evidence(scope)
      );
      disposition = await act(approver, "Dispositions", disposition, "Aprobar disposición", "/dispositions");
      ncr = await act(manager, "NCR", ncr, "Aplicar disposición NCR", "/ncrs", (scope) =>
        fill(scope, { "Disposición aprobada": disposition.id })
      );
      let corrective = await create(
        owner,
        "Corrective Actions",
        "Registrar acción de calidad",
        {
          "Código de acción": `ACTION-${run}`,
          "Tipo de acción": "CORRECTIVE",
          NCR: ncr.id,
          "Descripción de acción": "Perform actual Field rework and independent verification",
          "Dueño ID": data.user_ids.ncr_owner,
          Vencimiento: data.effective_at,
        },
        "/corrective-actions",
        async (scope) => {
          await pin(scope, "Objeto inspeccionado", data.production_id);
          await evidence(scope);
        }
      );
      corrective = await act(owner, "Corrective Actions", corrective, "Iniciar acción", "/corrective-actions");
      // Corrections are actual Field commands under Field actors, after the Quality disposition.
      const fieldRoute = `/workspaces/${data.project_workspace_id}/field-operations`;
      const fieldPrefix = `/api/v1/field-operations/projects/${data.project_workspace_id}`;
      const fieldReporter = await session("field_reporter", fieldRoute);
      const supervisor = await session("field_approver", fieldRoute);
      async function fieldTab(page: Page, view: string) {
        await button(page.getByRole("navigation", { name: "Field Operations Manager submodules" }), view).click();
        await button(page, "Actualizar campo").click();
      }
      async function fieldCreate(
        view: string,
        name: string,
        values: Row,
        endpoint: string,
        configure?: (control: Locator) => Promise<void>
      ) {
        await fieldTab(fieldReporter, view);
        await button(fieldReporter, "Nuevo registro").click();
        const control = form(fieldReporter, name);
        await fill(control, values);
        if (configure) await configure(control);
        return submit(fieldReporter, name, fieldPrefix + endpoint);
      }
      const shift = await fieldCreate(
        "Shifts",
        "Abrir turno",
        {
          "Código del turno": `REWORK-SHIFT-${run}`,
          "Tipo de turno": "DAY",
          "Fecha del turno": new Date(Date.now() - 15 * 60_000).toISOString().slice(0, 10),
          "Inicio del turno": new Date(Date.now() - 15 * 60_000 - new Date().getTimezoneOffset() * 60000)
            .toISOString()
            .slice(0, 19),
          "Fin del turno": new Date(Date.now() + 2 * 60 * 60_000 - new Date().getTimezoneOffset() * 60000)
            .toISOString()
            .slice(0, 19),
          "Frente de trabajo": data.workfront_id,
          "Supervisor ID": data.user_ids.field_supervisor,
        },
        "/shifts"
      );
      let rework = await fieldCreate(
        "Rework",
        "Registrar retrabajo",
        {
          "Código de producción": `REWORK-${run}`,
          "Frente de trabajo": data.workfront_id,
          Turno: shift.id,
          "Elemento Scope": data.scope_item_id,
          "Plan item": data.plan_item_id,
          IWP: data.iwp_id,
          "Cantidad observada": "1",
          "Unidad de producción": data.scope_unit,
          "Fecha y hora de observación": instant(),
          "Referencia de origen": `NCR:${ncr.id}`,
          "Producción original": data.production_id,
          "Motivo de retrabajo": "QUALITY_REFERENCE",
          "Evidencia CDE": document,
        },
        "/rework",
        async (control) => {
          await pin(control, "Revisión IFC de ejecución", data.ifc_id, undefined, true);
          await pin(control, "Referencia de material", data.material_allocation_id, "MATERIAL_ALLOCATION", true);
        }
      );
      await fieldTab(supervisor, "Rework");
      await selectRecord(supervisor, "Rework", rework.id);
      await button(supervisor, "Aprobar retrabajo…").click();
      rework = await submit(supervisor, "Aprobar retrabajo", `${fieldPrefix}/rework/${rework.id}/actions`, 200);
      observed.rework = rework.id;
      corrective = await act(
        owner,
        "Corrective Actions",
        corrective,
        "Completar acción",
        "/corrective-actions",
        async (scope) => {
          await pin(scope, "Evidencia Field de corrección", rework.id, "FIELD_REWORK");
          await evidence(scope);
        }
      );
      const reinspected = await inspection("PASS", `REINSPECT-${run}`, { failed, action: corrective });
      observed.reinspection = reinspected.id;
      corrective = await act(
        reviewer,
        "Corrective Actions",
        corrective,
        "Verificar acción",
        "/corrective-actions",
        async (scope) => {
          await pin(scope, "Resultado verificado Quality", reinspected.id, "INSPECTION");
          await evidence(scope);
        }
      );
      await act(reviewer, "Corrective Actions", corrective, "Cerrar acción", "/corrective-actions");
      ncr = await act(owner, "NCR", ncr, "Confirmar corrección NCR", "/ncrs");
      ncr = await act(manager, "NCR", ncr, "Verificar NCR", "/ncrs");
      ncr = await act(approver, "NCR", ncr, "Cerrar NCR", "/ncrs");
      observed.ncr = ncr.id;
      await release(reinspected);
      const successor = await accept(accepted);
      observed.acceptance_successor = successor.id;
      await approver.screenshot({ path: path.join(out, "03-ncr-closed-successor.png") });
      stage = "READINESS_TRACE_MOBILE";
      await tab(inspector, "Readiness Evidence Assessments");
      const readinessPanel = inspector.getByRole("region", { name: "Readiness Evidence Assessments", exact: true });
      await fill(readinessPanel, { "ITP de evaluación ID": itp.id });
      await pin(readinessPanel, "Objeto de evaluación", data.production_id);
      const assessment = await submit(inspector, "Guardar evaluación Quality", prefix + "/readiness/assess");
      observed.assessment = assessment.id;
      expect(assessment.readiness_state).toBe("READY");
      await tab(reviewer, "Trace");
      await fill(reviewer, { "Tipo de entidad Quality": "NCR", "Entidad Quality ID": ncr.id });
      await button(reviewer, "Consultar Trace").click();
      await expect(reviewer.getByRole("table", { name: "Historial Quality" })).toBeVisible();
      await reviewer.screenshot({ path: path.join(out, "04-trace.png") });
      await inspector.setViewportSize({ width: 390, height: 844 });
      await tab(inspector, "Quality Readiness");
      await fill(inspector, { "ITP aplicable ID": itp.id, "Objeto Quality ID": data.production_id });
      await button(inspector, "Consultar Quality Readiness").click();
      await expect(
        inspector.getByRole("region", { name: "Quality Readiness", exact: true }).getByText("READY", { exact: true })
      ).toBeVisible();
      const width = await inspector.evaluate(() => ({
        viewport: innerWidth,
        scroll: document.documentElement.scrollWidth,
      }));
      expect(width.scroll).toBeLessThanOrEqual(width.viewport + 1);
      await inspector.screenshot({ path: path.join(out, "05-mobile-ready.png"), fullPage: true });
      stage = "NATIVE_CONSUMERS";
      const progress = await session("progress_engineer", `/workspaces/${data.project_workspace_id}/progress`);
      await button(progress, "Field Evidence").click();
      const fieldPanel = progress.getByRole("region", { name: "Field evidence consumer" });
      await fill(fieldPanel, { "Evidencia de campo ID": data.production_id });
      await button(fieldPanel, "Consultar origen de campo").click();
      await fill(form(progress, "Registrar decisión PROGRESS"), {
        "Decisión Progress": "PARTIAL_ADOPT",
        "Cantidad a adoptar": "1",
        "Período de Progress": data.period_id,
        "Código de medición borrador": `PROG-${run}`,
      });
      const native = await submit(
        progress,
        "Registrar decisión PROGRESS",
        `/api/v1/progress/projects/${data.project_workspace_id}/field-adoptions`
      );
      observed.progress_measurement = native.linked_entity_id;
      await button(progress, "Quality Evidence").click();
      const qualityPanel = progress.getByRole("region", { name: "Quality evidence consumer" });
      await fill(qualityPanel, { "Evidencia Quality ID": successor.id });
      await button(qualityPanel, "Consultar evidencia Quality").click();
      await fill(form(progress, "Registrar decisión Quality PROGRESS"), {
        "Decisión sobre evidencia Quality": "ADOPT",
        "Medición Progress pendiente ID": native.linked_entity_id,
      });
      const adopted = await submit(
        progress,
        "Registrar decisión Quality PROGRESS",
        `/api/v1/progress/projects/${data.project_workspace_id}/quality-adoptions`
      );
      expect(adopted.linked_entity_id).toBe(native.linked_entity_id);
      const awp = await session("awp_manager", `/workspaces/${data.project_workspace_id}/awp`);
      await button(awp, "Quality Evidence").click();
      const awpQuality = awp.getByRole("region", { name: "Quality evidence consumer" });
      await fill(awpQuality, { "Evidencia Quality ID": assessment.id });
      await button(awpQuality, "Consultar evidencia Quality").click();
      await fill(form(awp, "Registrar decisión Quality AWP"), {
        "Decisión sobre evidencia Quality": "ADOPT",
        "Paquete AWP a evaluar ID": data.iwp_id,
      });
      await submit(
        awp,
        "Registrar decisión Quality AWP",
        `/api/v1/awp/projects/${data.project_workspace_id}/quality-adoptions`
      );
      await awp.screenshot({ path: path.join(out, "06-awp-native-quality.png") });
      const contracts = await session("manager", `/workspaces/${data.project_workspace_id}/contracts`);
      await button(contracts, "Quality Evidence").click();
      const contractsQuality = contracts.getByRole("region", { name: "Quality evidence consumer" });
      await fill(contractsQuality, { "Evidencia Quality ID": ncr.id });
      await button(contractsQuality, "Consultar evidencia Quality").click();
      await expect(contractsQuality.getByText("QUALITY", { exact: true })).toBeVisible();
      expect(await contractsQuality.getByRole("form", { name: /Registrar decisión/ }).count()).toBe(0);
      await contracts.screenshot({ path: path.join(out, "07-contracts-readonly.png") });
      expect(errors).toEqual([]);
      passed = true;
    } finally {
      if (!passed && lastPage)
        await lastPage.screenshot({ path: path.join(out, "failure.png"), fullPage: true }).catch(() => {});
      writeFileSync(
        path.join(out, "summary.json"),
        JSON.stringify(
          {
            passed,
            stage,
            fixture: path.basename(manifest!),
            viewport: "1440x1000 and390x844",
            steps,
            observed,
            errors,
            finished_at: new Date().toISOString(),
          },
          null,
          2
        )
      );
      for (const context of contexts) await context.close();
    }
  });
});
