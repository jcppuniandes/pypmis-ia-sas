import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { ForecastAssumption, ForecastComponent, ForecastDraft } from "../src/features/forecast-foundation/types";

type Actor = { id: number; email: string; tenant_id: number; password?: string };
type LookAheadActivity = {
  critical: boolean;
  near_critical: boolean | string;
  driving_predecessor: { state: string };
  plan_item_ids: number[];
  scope_item_ids: number[];
  work_package_ids: number[];
  readiness: { readiness_state: string }[];
  constraints: { code: string; status: string }[];
};
type Fixture = {
  project_workspace_id: number;
  legacy_project_id: number;
  tenant_id: number;
  password: string;
  users: Record<string, Actor>;
  forecast_payload: ForecastDraft;
  period_id: number;
  schedule_version_id: number;
  as_of: string;
  scope_items: unknown[];
  plan_items: unknown[];
  packages: unknown[];
  bundle: { id: number; content_hash: string };
  model: { id: number };
  schedule_version: { snapshot_json: { activities: unknown[]; relationships: unknown[] } };
};
const file = process.env.E2E_O1C_FIXTURE;
const fixture: Fixture | null = file ? JSON.parse(readFileSync(file, "utf8")) : null;
const api = process.env.E2E_API_URL || "http://127.0.0.1:8858";
const output = path.resolve(process.env.E2E_O1C_OUTPUT || "../outputs/.qa/wave-o1c-20261106/chromium");
const reason = "Controlled independent O1C real browser release validation";
const tabs = [
  "Forecast Overview",
  "ETC / EAC",
  "Time Forecast",
  "Milestones",
  "Resource Forecast",
  "Assumptions",
  "Variance & Trends",
  "S-Curves",
  "Project Controls Dashboard",
  "Executive Dashboard",
  "4-Week Look-Ahead",
  "Reporting History",
];
const references = {
  amount_assumption_code: "Amount",
  quantity_assumption_code: "Remaining quantity",
  rate_assumption_code: "Rate",
  productivity_assumption_code: "Forecast productivity",
  duration_assumption_code: "Remaining duration",
  trend_factor_assumption_code: "Trend factor",
  date_assumption_code: "Forecast date",
  crew_assumption_code: "Crew",
  planned_productivity_assumption_code: "Planned productivity",
  actual_productivity_assumption_code: "Actual productivity",
};

test.describe("O1C real PostgreSQL Forecast, Performance and Reporting", () => {
  test.skip(!fixture, "Requires disposable persistent PostgreSQL IFC/P6 lineage and independent real actors");
  test.use({ actionTimeout: 45_000, navigationTimeout: 120_000 });
  test("ADMIN policy, typed USER forecast, independent approval, published period and immutable factual report", async ({
    browser,
    request,
  }) => {
    test.setTimeout(1_200_000);
    if (!fixture) throw new Error("O1C fixture is required");
    expect(api).toMatch(/^http:\/\/(127\.0\.0\.1|localhost):8858$/);
    mkdirSync(output, { recursive: true });
    const checks: Array<{ code: string; result: string }> = [];
    const observations: Array<{ label: string; elapsed_ms: number; status: number }> = [];
    const timings: Array<{ operation: string; stage: string; samples_ms: number[]; statuses: number[] }> = [];
    const errors: string[] = [];
    const pages: Page[] = [];
    const created: Record<string, unknown> = {};
    const project = fixture.project_workspace_id;
    const root = `/api/v1/forecast/projects/${project}`;
    const perf = `/api/v1/performance/projects/${project}`;
    const reporting = `/api/v1/reporting/projects/${project}`;
    const progress = `/api/v1/progress/projects/${project}`;
    const route = `/workspaces/${project}/forecast`;
    const code = `FC-UAT-${String(Date.now()).slice(-9)}`;
    const mark = (value: string) => checks.push({ code: value, result: "PASS" });
    const save = (name: string, value: unknown) =>
      writeFileSync(path.join(output, name), JSON.stringify(value, null, 2));
    async function actor(role: string, initialRoute = route) {
      const user = fixture!.users[role];
      expect(user, `Disposable actor ${role}`).toBeTruthy();
      const response = await request.post(`${api}/api/v1/auth/login`, {
        timeout: 120_000,
        data: { email: user.email, tenant_id: user.tenant_id, password: user.password || fixture!.password },
      });
      expect(response.status(), await response.text()).toBe(200);
      const session = await response.json();
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      await context.addInitScript(
        (value) =>
          localStorage.setItem(
            "pypmis_auth",
            JSON.stringify({ state: { token: value.access_token, user: value.user }, version: 0 })
          ),
        session
      );
      const page = await context.newPage();
      pages.push(page);
      page.on("pageerror", (error) => errors.push(String(error)));
      await page.goto(initialRoute);
      return { page, token: String(session.access_token), user: session.user };
    }
    async function get(token: string, suffix: string, base = root) {
      const response = await request.get(`${api}${base}${suffix}`, {
        headers: { Authorization: `Bearer ${token}` },
        timeout: 120_000,
      });
      expect(response.status(), await response.text()).toBe(200);
      return response.json();
    }
    async function command(page: Page, suffix: string, action: () => Promise<unknown>, status = 200) {
      const started = performance.now();
      const pending = page.waitForResponse(
        (response) => response.url().endsWith(suffix) && ["POST", "PUT"].includes(response.request().method())
      );
      await action();
      const response = await pending;
      expect(response.status(), await response.text()).toBe(status);
      const result = await response.json();
      await expect(page.locator("[aria-busy]").last()).toHaveAttribute("aria-busy", "false");
      observations.push({ label: suffix, elapsed_ms: performance.now() - started, status: response.status() });
      return result;
    }
    async function fill(page: Page, label: string, value: unknown) {
      await page.getByLabel(label, { exact: true }).fill(String(value ?? ""));
    }
    async function choose(page: Page, label: string, value: unknown) {
      await page.getByLabel(label, { exact: true }).selectOption(String(value ?? ""));
    }
    async function tab(page: Page, name: string) {
      await page
        .getByRole("navigation", { name: "Forecast & Performance submodules" })
        .getByRole("button", { name, exact: true })
        .click();
    }
    async function select(page: Page, identity: number) {
      await expect(page.getByRole("heading", { name: "Forecast & Performance", exact: true })).toBeVisible();
      await choose(page, "Forecast Version", identity);
      await fill(page, "Motivo Forecast", reason);
      await expect(page.getByLabel("Forecast & Performance", { exact: true })).toHaveAttribute("aria-busy", "false");
      await tab(page, "Forecast Overview");
      await expect(page.getByLabel("Forecast Code", { exact: true })).toHaveValue(code);
    }
    async function shot(page: Page, name: string) {
      await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
    }
    async function openAdmin(role: string) {
      const value = await actor(role, "/app");
      await value.page.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }).click();
      for (const name of ["Platform Administration", "Process Configuration"]) {
        const button = value.page.getByRole("button", { name, exact: true });
        if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
      }
      await value.page.getByRole("button", { name: "Process & Operational Configuration", exact: true }).click();
      await value.page.getByRole("button", { name: "Forecast Profiles", exact: true }).click();
      await expect(value.page.getByLabel("Forecast Profiles configuration JSON", { exact: true })).not.toHaveValue(
        "{}"
      );
      return value;
    }
    async function assumption(page: Page, entry: ForecastAssumption) {
      for (const [label, value] of Object.entries({
        Code: entry.code,
        Name: entry.name,
        Kind: entry.kind,
        Value: entry.value,
        Unit: entry.unit,
        Currency: entry.currency,
        "Source reference": entry.source_reference,
        "Owner ID": entry.owner_id,
        "Effective date": entry.effective_date,
        "Evidence reference": entry.evidence_ref,
        Rationale: entry.rationale,
      }))
        await fill(page, `Assumption ${label}`, value);
      await choose(page, "Assumption Confidence", entry.confidence);
      await choose(page, "Assumption Status", entry.status);
      await page.getByRole("button", { name: "Añadir hipótesis al borrador", exact: true }).click();
      await expect(page.getByRole("table", { name: "Forecast Assumptions", exact: true })).toContainText(entry.code);
    }
    async function component(
      page: Page,
      entry: ForecastComponent,
      family: "cost_items" | "time_items" | "milestones" | "resource_items"
    ) {
      const titles = {
        cost_items: "Cost Forecast Components",
        time_items: "Time Forecast Components",
        milestones: "Forecast Milestones",
        resource_items: "Resource Forecast Components",
      };
      const tabNames = {
        cost_items: "ETC / EAC",
        time_items: "Time Forecast",
        milestones: "Milestones",
        resource_items: "Resource Forecast",
      };
      const title = titles[family];
      await tab(page, tabNames[family]);
      for (const [label, value] of Object.entries({
        Code: entry.code,
        Name: entry.name,
        Unit: entry.unit,
        Currency: entry.currency,
        "Activity external ID": entry.activity_external_id,
        "WBS external ID": entry.wbs_external_id,
      }))
        await fill(page, `${title} ${label}`, value);
      await choose(page, `${title} Method`, entry.method);
      for (const [key, label] of Object.entries({
        scope_item_id: "Scope",
        plan_item_id: "Plan",
        work_package_id: "Work Package",
        control_account_id: "Control Account",
        cbs_id: "CBS",
        cost_code_id: "Cost Code",
        schedule_version_id: "Schedule Version",
      })) {
        const value = entry[key as keyof ForecastComponent];
        if (value) await choose(page, `${title} ${label}`, value);
      }
      for (const [key, label] of Object.entries(references))
        if (entry.inputs[key]) await choose(page, `${title} ${label} assumption`, entry.inputs[key]);
      if (family === "cost_items") {
        await choose(page, `${title} ETC bucket`, entry.inputs.cost_bucket || "UNCOMMITTED");
        if (Array.isArray(entry.inputs.commitment_ids))
          await fill(page, `${title} Commitment IDs`, entry.inputs.commitment_ids.join(","));
        if (Array.isArray(entry.inputs.incurred_actual_ids))
          await fill(page, `${title} Recognized incurred Actual IDs`, entry.inputs.incurred_actual_ids.join(","));
      }
      if (family === "resource_items") {
        await choose(page, `${title} Resource Type`, entry.inputs.resource_type || "LABOR");
        await choose(page, `${title} Productivity basis`, entry.inputs.productivity_basis || "QUANTITY_PER_DAY");
      }
      if (family === "milestones")
        await choose(page, `${title} Milestone Type`, entry.inputs.milestone_type || "KEY_PROJECT");
      const dimensions = page.getByText("Dimensiones de agrupación y distribución Forecast", { exact: true });
      await dimensions.click();
      for (const key of ["area", "zone", "system", "discipline"] as const)
        if (entry[key]) await fill(page, `${title} ${key}`, entry[key]);
      if (entry.inputs.phase) await fill(page, `${title} Quantity phase`, entry.inputs.phase);
      if (family === "cost_items" && Array.isArray(entry.inputs.phasing))
        for (const point of entry.inputs.phasing as Array<{ date: string; amount: string }>) {
          await fill(page, `${title} Phase date`, point.date);
          await fill(page, `${title} Phase amount`, point.amount);
          await page.getByRole("button", { name: "Añadir fecha Forecast", exact: true }).click();
        }
      await page.getByRole("button", { name: "Añadir componente al borrador", exact: true }).click();
      await expect(page.getByRole("table", { name: title, exact: true })).toContainText(entry.code);
    }
    async function observe(token: string, operation: string, suffix: string, base: string) {
      const samples: number[] = [],
        statuses: number[] = [];
      for (let sample = 0; sample < 3; sample++) {
        const started = performance.now();
        const response = await request.get(`${api}${base}${suffix}`, {
          headers: { Authorization: `Bearer ${token}` },
          timeout: 120_000,
        });
        samples.push(performance.now() - started);
        statuses.push(response.status());
        expect(response.status(), await response.text()).toBe(200);
        await response.json();
      }
      timings.push({
        operation,
        stage: "After independent Forecast/period/report publication; sequential real HTTP reads",
        samples_ms: samples,
        statuses,
      });
    }
    try {
      const admin = await openAdmin("admin");
      const profileCode = `O1C-POLICY-${String(Date.now()).slice(-8)}`;
      const policy = JSON.parse(
        await admin.page.getByLabel("Forecast Profiles configuration JSON", { exact: true }).inputValue()
      );
      expect(policy.allowed_methods).toHaveLength(8);
      expect(policy.confidence_is_statistical).toBe(false);
      expect(policy.lookahead.default_horizon_days).toBe(28);
      expect(policy.lookahead.near_critical_threshold.unit).toBe("HOUR");
      expect(policy.reporting.narrative_sections).toContain("CONSTRAINTS_READINESS");
      policy.scope = { type: "workspace", workspace_id: project };
      policy.dashboard_thresholds.cpi_warning = "3.25";
      await fill(admin.page, "Forecast Profiles Code", profileCode);
      await fill(admin.page, "Forecast Profiles Name", "Governed Forecast policy, thresholds and report sections");
      await fill(admin.page, "Forecast Profiles configuration JSON", JSON.stringify(policy, null, 2));
      await fill(admin.page, "Motivo Forecast Profiles", reason);
      const profile = await command(
        admin.page,
        "/api/v1/forecast/admin/profiles",
        () => admin.page.getByRole("button", { name: "Crear Forecast Profiles DRAFT", exact: true }).click(),
        201
      );
      created.profile = profile.id;
      await command(
        admin.page,
        `/${profile.id}/publish`,
        () => admin.page.getByRole("button", { name: "Publicar Forecast Profiles", exact: true }).click(),
        403
      );
      mark("ADMIN_TYPED_POLICY_DEFAULTS_EIGHT_METHODS_THRESHOLDS_AND_AUTHOR_PUBLICATION_DENIED");
      const policyPublisher = await openAdmin("publisher");
      await policyPublisher.page
        .getByRole("button", { name: `Ver Forecast Profiles ${profileCode}`, exact: true })
        .click();
      await fill(policyPublisher.page, "Motivo Forecast Profiles", reason);
      const published = await command(policyPublisher.page, `/${profile.id}/publish`, () =>
        policyPublisher.page.getByRole("button", { name: "Publicar Forecast Profiles", exact: true }).click()
      );
      expect(published.content_json).toEqual(policy);
      await expect(
        policyPublisher.page.getByLabel("Forecast Profiles configuration JSON", { exact: true })
      ).toBeDisabled();
      await shot(policyPublisher.page, "admin-forecast-profile-published-immutable");
      mark("ADMIN_INDEPENDENT_PUBLICATION_IMMUTABLE_POLICY_NOT_LIVE_FORECAST");
      await admin.page.context().close();
      await policyPublisher.page.context().close();

      const recorder = await actor("cost_controller");
      const before = await get(recorder.token, "/overview");
      const payload = structuredClone(fixture.forecast_payload);
      payload.code = code;
      created.project_workspace_id = project;
      created.period_id = fixture.period_id;
      expect(before.context.project_workspace_id).toBe(project);
      expect(before.configuration.id).toBe(published.id);
      await expect(
        recorder.page.getByRole("navigation", { name: "Forecast & Performance submodules" }).getByRole("button")
      ).toHaveCount(12);
      await expect(recorder.page.getByRole("button", { name: "Forecast Profiles", exact: true })).toHaveCount(0);
      await fill(recorder.page, "Motivo Forecast", reason);
      for (const [label, value] of Object.entries({
        Code: code,
        Name: payload.name,
        "As-of": payload.as_of,
        Currency: payload.currency,
        "Confidence rationale": payload.confidence_rationale,
        "Data completeness": payload.data_completeness,
        "Assumption maturity": payload.assumption_maturity,
        "Evidence reference": payload.evidence_ref,
      }))
        await fill(recorder.page, `Forecast ${label}`, value);
      for (const [label, value] of Object.entries({
        "Baseline Bundle": payload.bundle_id,
        Period: payload.period_id,
        "Accepted Schedule": payload.schedule_version_id,
        Method: payload.method,
        Confidence: payload.confidence,
      }))
        await choose(recorder.page, `Forecast ${label}`, value);
      await tab(recorder.page, "Assumptions");
      for (const value of payload.assumptions) await assumption(recorder.page, value);
      mark("CANONICAL_CONTEXT_TWELVE_SUBMODULES_TYPED_ASSUMPTIONS_SOURCE_OWNER_UNIT_DATE_CONFIDENCE");
      for (const family of ["cost_items", "time_items", "milestones", "resource_items"] as const)
        for (const value of payload[family]) await component(recorder.page, value, family);
      const forecast = await command(
        recorder.page,
        "/versions",
        () => recorder.page.getByRole("button", { name: "Crear Forecast DRAFT", exact: true }).click(),
        201
      );
      created.forecast = forecast.id;
      expect(forecast.configuration_id).toBe(published.id);
      expect(forecast.input_json.assumptions).toHaveLength(payload.assumptions.length);
      expect(forecast.input_json.cost_items[0].inputs.phasing).toEqual(payload.cost_items[0].inputs.phasing);
      mark("TYPED_ETC_TIME_MILESTONE_RESOURCE_AND_EXPLICIT_FORECAST_PHASING_SAVED");
      let calculation = forecast;
      for (const operation of ["ETC calculation", "EAC calculation"]) {
        const samples: number[] = [],
          statuses: number[] = [];
        for (let sample = 0; sample < 3; sample++) {
          const previousVersion = calculation.version;
          calculation = await command(recorder.page, `/versions/${forecast.id}/calculate`, () =>
            recorder.page.getByRole("button", { name: "Calcular ETC y EAC", exact: true }).click()
          );
          expect(calculation.version).toBeGreaterThan(previousVersion);
          const observation = observations[observations.length - 1];
          samples.push(observation.elapsed_ms);
          statuses.push(observation.status);
        }
        timings.push({
          operation,
          stage:
            "DRAFT joint ETC/EAC browser command; same endpoint, separate three-sample batches with updated If-Match; includes response JSON and refresh",
          samples_ms: samples,
          statuses,
        });
      }
      expect(Number(calculation.result_json.cost.etc)).toBe(60);
      expect(Number(calculation.result_json.cost.eac)).toBe(85);
      expect(Number(calculation.result_json.cost.vac)).toBe(35);
      expect(calculation.result_json.cost.commitment_added_to_eac).toBe(false);
      expect(Number(calculation.result_json.resources.items[0].quantity)).toBe(6);
      expect(calculation.result_json.resources.items[0].unit).toBe("person-day");
      expect(calculation.result_json.time.items[0].activity_external_id).toBe("5001");
      expect(calculation.result_json.time.milestones[0].forecast_finish).toBe("2026-11-20");
      mark("BACKEND_ETC60_EAC85_VAC35_NO_COMMITMENT_DOUBLECOUNT_AND_RESOURCE6_PERSON_DAYS");
      await command(recorder.page, `/versions/${forecast.id}/transition`, () =>
        recorder.page.getByRole("button", { name: "Enviar Forecast a revisión", exact: true }).click()
      );
      await expect(recorder.page.getByRole("button", { name: "Aprobar Forecast", exact: true })).toHaveCount(0);
      // Open the independent actor after submission so its initial list is the actual review queue.
      const manager = await actor("manager");
      await select(manager.page, forecast.id);
      const approved = await command(manager.page, `/versions/${forecast.id}/transition`, () =>
        manager.page.getByRole("button", { name: "Aprobar Forecast", exact: true }).click()
      );
      expect(approved.status).toBe("APPROVED");
      expect(approved.prepared_by).not.toBe(approved.approved_by);
      await expect(manager.page.getByLabel("Forecast Name", { exact: true })).toBeDisabled();
      await expect(manager.page.getByRole("button", { name: "Guardar Forecast borrador", exact: true })).toHaveCount(0);
      mark("FORECAST_INDEPENDENT_REVIEW_APPROVAL_AND_IMMUTABLE_APPROVED_INPUTS");
      const approvedHash = approved.content_hash;
      for (const name of tabs.slice(0, 10)) {
        await tab(manager.page, name);
        if (name === "ETC / EAC")
          await expect(manager.page.getByRole("table", { name: "Forecast Cost Metrics", exact: true })).toContainText(
            "85"
          );
        if (name === "Resource Forecast")
          await expect(
            manager.page.getByRole("table", { name: "Resource Forecast Calculated Items", exact: true })
          ).toContainText("person-day");
        if (name === "Time Forecast")
          await expect(
            manager.page.getByRole("table", { name: "Time Forecast Calculated Items", exact: true })
          ).toContainText("5001");
        if (name === "Milestones")
          await expect(
            manager.page.getByRole("table", { name: "Forecast Milestones Calculated Items", exact: true })
          ).toContainText("2026-11-20");
        if (name === "Variance & Trends")
          await expect(
            manager.page.getByRole("table", { name: "Governed Variance Comparison", exact: true })
          ).toContainText("CALENDAR_DAY_DELTA_NOT_CPM");
        if (name === "S-Curves")
          await expect(
            manager.page.getByRole("table", { name: "FORECAST_COST Curve Points", exact: true })
          ).toContainText("60");
        if (name === "Executive Dashboard")
          await expect(
            manager.page.getByRole("table", { name: "Executive Dashboard Metrics", exact: true })
          ).toContainText("85");
        if (name === "Project Controls Dashboard") {
          const metrics = manager.page.getByRole("table", { name: "Project Controls Dashboard Metrics", exact: true });
          for (const name of ["PV", "EV", "AC", "CPI", "SPI", "EAC", "VAC"]) {
            const row = metrics.getByRole("row").filter({ has: manager.page.getByRole("cell", { name, exact: true }) });
            await expect(row.getByRole("cell").nth(1)).toHaveText(/^-?\d+(\.\d+)?$/);
          }
          await expect(
            manager.page.getByRole("table", { name: "Project Controls Dashboard Threshold Indicators", exact: true })
          ).toContainText("3.25");
        }
        await shot(manager.page, `user-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`);
      }
      mark("COST_TIME_MILESTONES_RESOURCES_VARIANCE_CURVES_AND_DASHBOARDS_VISIBLE_FROM_REAL_SOURCES");
      await tab(manager.page, "4-Week Look-Ahead");
      await expect(manager.page.getByLabel("Look-Ahead Horizon days", { exact: true })).toHaveValue("28");
      const lookaheadResponse = manager.page.waitForResponse(
        (response) => response.url().includes(`${perf}/lookahead?`) && response.request().method() === "GET"
      );
      await manager.page.getByRole("button", { name: "Ejecutar Look-Ahead", exact: true }).click();
      const lookahead = await (await lookaheadResponse).json();
      expect(lookahead.horizon_days).toBe(28);
      const activities: LookAheadActivity[] = lookahead.items;
      expect(activities.length).toBeGreaterThan(6);
      expect(activities.some((row) => row.driving_predecessor.state === "UNKNOWN")).toBe(true);
      expect(activities.some((row) => row.critical === true)).toBe(true);
      expect(activities.some((row) => row.near_critical === true)).toBe(true);
      const constrained = activities.find((row) =>
        row.constraints.some((constraint) => constraint.code === "O1C-OPEN-ACCESS" && constraint.status === "OPEN")
      );
      expect(constrained?.plan_item_ids.length).toBeGreaterThan(0);
      expect(constrained?.work_package_ids.length).toBeGreaterThan(0);
      expect(constrained?.scope_item_ids.length).toBeGreaterThan(0);
      expect(constrained?.readiness.length).toBeGreaterThan(0);
      const lookaheadTable = manager.page.getByRole("table", { name: "Look-Ahead Activities", exact: true });
      await expect(lookaheadTable).toContainText("UNKNOWN");
      await expect(lookaheadTable).toContainText("O1C-OPEN-ACCESS");
      await expect(lookaheadTable).toContainText(constrained!.readiness[0].readiness_state);
      await shot(manager.page, "lookahead-28-days-mapped-imported-float-unknown-driver");
      await command(
        manager.page,
        "/lookahead/snapshots",
        () => manager.page.getByRole("button", { name: "Guardar snapshot Look-Ahead", exact: true }).click(),
        201
      );
      await fill(manager.page, "Look-Ahead Horizon days", "14");
      await choose(manager.page, "Look-Ahead Group by", "AREA");
      const customPending = manager.page.waitForResponse(
        (response) => response.url().includes(`${perf}/lookahead?`) && response.url().includes("horizon_days=14")
      );
      await manager.page.getByRole("button", { name: "Ejecutar Look-Ahead", exact: true }).click();
      const custom = await (await customPending).json();
      expect(custom.horizon_days).toBe(14);
      expect(custom.group_by).toBe("AREA");
      expect(custom.authority.cpm_calculation_performed).toBe(false);
      expect(custom.authority.driver_inference_performed).toBe(false);
      mark(
        "FOUR_WEEK_LOOKAHEAD_CONFIGURABLE_GROUPED_WITH_MAPPING_READINESS_CONSTRAINTS_UNKNOWN_DRIVER_AND_EXPLICIT_SNAPSHOT"
      );

      await manager.page.goto(`/workspaces/${project}/progress`);
      await expect(manager.page.getByRole("heading", { name: "Progress Manager", exact: true })).toBeVisible();
      await choose(manager.page, "Progress Controls Period", fixture.period_id);
      await fill(manager.page, "Progress as-of date", fixture.as_of);
      await fill(manager.page, "Motivo Progress", reason);
      await manager.page
        .getByRole("navigation", { name: "Progress Manager submodules" })
        .getByRole("button", { name: "Period Review", exact: true })
        .click();
      await fill(
        manager.page,
        "Period Review notes",
        "Independent real source candidate set for immutable O1C period report"
      );
      await command(manager.page, `/periods/${fixture.period_id}/transition`, () =>
        manager.page.getByRole("button", { name: "Congelar Progress para revisión", exact: true }).click()
      );
      await command(manager.page, `/periods/${fixture.period_id}/transition`, () =>
        manager.page.getByRole("button", { name: "Cerrar período Progress", exact: true }).click()
      );
      await command(
        manager.page,
        `/periods/${fixture.period_id}/transition`,
        () => manager.page.getByRole("button", { name: "Publicar período Progress", exact: true }).click(),
        403
      );
      const publisher = await actor("publisher", `/workspaces/${project}/progress`);
      await expect(publisher.page.getByRole("heading", { name: "Progress Manager", exact: true })).toBeVisible();
      await choose(publisher.page, "Progress Controls Period", fixture.period_id);
      await fill(publisher.page, "Progress as-of date", fixture.as_of);
      await fill(publisher.page, "Motivo Progress", reason);
      await publisher.page
        .getByRole("navigation", { name: "Progress Manager submodules" })
        .getByRole("button", { name: "Period Review", exact: true })
        .click();
      await command(publisher.page, `/periods/${fixture.period_id}/transition`, () =>
        publisher.page.getByRole("button", { name: "Publicar período Progress", exact: true }).click()
      );
      const periodReview = await get(publisher.token, `/periods/${fixture.period_id}/review`, progress);
      expect(periodReview.period.status).toBe("PUBLISHED");
      await shot(publisher.page, "progress-existing-period-independently-published");
      mark("EXISTING_PROGRESS_PERIOD_FROZEN_CLOSED_AND_PUBLISHED_BY_INDEPENDENT_ACTOR");
      await publisher.page.goto(route);
      await select(publisher.page, forecast.id);
      await tab(publisher.page, "Reporting History");
      await fill(publisher.page, "Report Evidence reference", "O1C-BROWSER-INDEPENDENT-PUBLISHED-PERIOD-REPORT");
      const report = await command(
        publisher.page,
        `${reporting}/reports`,
        () => publisher.page.getByRole("button", { name: "Publicar reporte del período", exact: true }).click(),
        201
      );
      created.report = report.id;
      expect(report.status).toBe("PUBLISHED");
      expect(report.forecast_version_id).toBe(forecast.id);
      expect(Number(report.metrics_json.metrics.eac)).toBe(85);
      expect(report.narratives_json.length).toBeGreaterThanOrEqual(7);
      expect(report.narratives_json.every((row: { fact_references: string[] }) => row.fact_references.length > 0)).toBe(
        true
      );
      expect(report.source_refs_json).toBeTruthy();
      await expect(publisher.page.getByRole("table", { name: "Published Period Reports", exact: true })).toContainText(
        "PUBLISHED"
      );
      await shot(publisher.page, "report-published-factual-narrative-immutable-history");
      mark(
        "INDEPENDENT_REPORT_PUBLISHED_WITH_FROZEN_SCHEDULE_COST_PROGRESS_EVM_FORECAST_READINESS_AND_FACTUAL_NARRATIVE"
      );

      await manager.page.goto(route);
      await select(manager.page, forecast.id);
      await tab(manager.page, "Project Controls Dashboard");
      await expect(
        manager.page.getByRole("table", { name: "Project Controls Dashboard Metrics", exact: true })
      ).toBeVisible();
      const desktop = await manager.page.evaluate(() => ({
        width: innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        tables: document.querySelectorAll("table").length,
      }));
      expect(desktop.documentWidth).toBeLessThanOrEqual(desktop.width + 2);
      await shot(manager.page, "desktop-dashboard-layout");
      await manager.page.setViewportSize({ width: 390, height: 844 });
      const mobile = await manager.page.evaluate(() => ({
        width: innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        tables: document.querySelectorAll("table").length,
      }));
      expect(mobile.documentWidth).toBeLessThanOrEqual(mobile.width + 2);
      await shot(manager.page, "mobile-dashboard-layout");
      await manager.page.setViewportSize({ width: 1440, height: 1000 });
      save("layout.json", { result: "PASS", desktop, mobile });
      mark("DESKTOP_AND_MOBILE_COMPACT_LAYOUT_NO_DOCUMENT_HORIZONTAL_OVERFLOW");

      const query = `?forecast_version_id=${forecast.id}&period_id=${fixture.period_id}&as_of=${fixture.as_of}`;
      await observe(manager.token, "Forecast overview", "/overview", root);
      await observe(manager.token, "Time forecast", `/versions/${forecast.id}/calculation`, root);
      await observe(manager.token, "Resource forecast", `/versions/${forecast.id}/calculation`, root);
      await observe(manager.token, "Trends", "/trends", perf);
      await observe(manager.token, "S-Curves", `/curves${query}`, perf);
      await observe(manager.token, "Project dashboard", `/dashboard${query}`, perf);
      await observe(manager.token, "Executive dashboard", `/executive${query}`, perf);
      await observe(
        manager.token,
        "4-Week Look-Ahead",
        `/lookahead${query}&horizon_days=28&near_critical_unit=HOUR&near_critical_value=40`,
        perf
      );
      await observe(publisher.token, "Report snapshot", `/reports/${report.id}`, reporting);
      expect(timings).toHaveLength(11);
      expect(
        timings.every((row) => row.samples_ms.length === 3 && row.statuses.every((status) => status === 200))
      ).toBe(true);
      const performanceEvidence = {
        result: "PASS",
        observational_only: true,
        not_universal_sla: true,
        environment: {
          browser: "Real Chromium",
          database: "Isolated persistent PostgreSQL",
          api,
          api_workers: 1,
          sequencing: "One request/command at a time",
          project_workspace_id: project,
        },
        volumes: {
          activities: fixture.schedule_version.snapshot_json.activities.length,
          relationships: fixture.schedule_version.snapshot_json.relationships.length,
          scope_items: fixture.scope_items.length,
          plan_items: fixture.plan_items.length,
          packages: fixture.packages.length,
        },
        operations: timings.map((row) => {
          const sorted = [...row.samples_ms].sort((a, b) => a - b);
          return { ...row, min_ms: sorted[0], median_ms: sorted[1], max_ms: sorted[2] };
        }),
      };
      save("performance.json", performanceEvidence);
      const unchangedForecast = await get(manager.token, `/versions/${forecast.id}`);
      const unchangedReport = await get(publisher.token, `/reports/${report.id}`, reporting);
      const unchangedPeriod = await get(publisher.token, `/periods/${fixture.period_id}/review`, progress);
      expect(unchangedForecast.content_hash).toBe(approvedHash);
      expect(unchangedForecast.input_json).toEqual(approved.input_json);
      expect(unchangedReport.content_hash).toBe(report.content_hash);
      expect(unchangedReport.source_snapshot_json).toEqual(report.source_snapshot_json);
      expect(unchangedPeriod.snapshot).toEqual(periodReview.snapshot);
      const curves = await get(manager.token, `/curves${query}`, perf);
      expect(curves.series).toHaveLength(6);
      const trends = await get(manager.token, "/trends", perf);
      expect(trends.items.length).toBeGreaterThan(0);
      await tab(manager.page, "Variance & Trends");
      await expect(manager.page.getByRole("table", { name: "Published Period Trends", exact: true })).toContainText(
        "85"
      );
      await shot(manager.page, "published-report-trend-history");
      mark("ELEVEN_OPERATIONS_THREE_SEQUENTIAL_OBSERVATIONS_LARGER_CURRENT_FIXTURE_AND_FROZEN_SOURCE_READS");
      mark("APPROVED_FORECAST_AND_PUBLISHED_PERIOD_REPORT_HISTORY_IMMUTABLE_AFTER_DASHBOARD_READS");
      expect(errors).toEqual([]);
      save("browser-uat.json", {
        result: "PASS",
        checks,
        created,
        observations,
        browser_errors: errors,
        source_refs: report.source_refs_json,
        source_hashes: { forecast: approvedHash, report: report.content_hash, bundle: fixture.bundle.content_hash },
        fixture_scope: "Disposable technical UAT; no business acceptance or user production tenant writes",
        completed_at: new Date().toISOString(),
      });
    } catch (error) {
      save("browser-uat-failure.json", {
        result: "FAIL",
        checks,
        created,
        observations,
        timings,
        browser_errors: errors,
        error: String(error),
        completed_at: new Date().toISOString(),
      });
      for (let index = 0; index < pages.length; index++)
        if (!pages[index].isClosed()) await shot(pages[index], `failure-${index}`).catch(() => undefined);
      throw error;
    } finally {
      for (const page of pages) if (!page.isClosed()) await page.context().close();
    }
  });
});
