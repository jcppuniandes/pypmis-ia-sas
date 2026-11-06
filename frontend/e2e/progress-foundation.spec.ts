import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const file = process.env.E2E_O1BD_FIXTURE;
const fixture = file ? JSON.parse(readFileSync(file, "utf8")) : null;
const api = process.env.E2E_API_URL || "http://127.0.0.1:8857";
const output = path.resolve(process.env.E2E_O1BD_OUTPUT || "../outputs/.qa/wave-o1bd-20261104/chromium");
const reason = "Controlled real Progress browser release validation";

test.describe("O1B-D real PostgreSQL Progress and Baseline Integration", () => {
  test.skip(!fixture, "Requires persistent disposable PostgreSQL upstream source chain and independent actors");
  test.use({ actionTimeout: 45_000, navigationTimeout: 120_000 });
  test("ADMIN publication and USER measurement, credit, EVM, period and stale baseline lifecycles", async ({
    browser,
    request,
  }) => {
    test.setTimeout(1_200_000);
    expect(api).toMatch(/^http:\/\/(127\.0\.0\.1|localhost):8857$/);
    mkdirSync(output, { recursive: true });
    const checks: Array<{ code: string; result: string }> = [];
    const observations: Array<{ label: string; elapsed_ms: number; status: number }> = [];
    const errors: string[] = [];
    const pages: Page[] = [];
    const project = Number(fixture.project_workspace_id);
    const root = `/api/v1/progress/projects/${project}`;
    const route = `/workspaces/${project}/progress`;
    const stamp = String(Date.now()).slice(-8);
    const code = (name: string) => `P-UAT-${name}-${stamp}`;
    const mark = (value: string) => checks.push({ code: value, result: "PASS" });
    const created: Record<string, unknown> = {};
    async function actor(role: string, initialRoute = route) {
      const user = fixture.users[role];
      expect(user, `Disposable actor ${role}`).toBeTruthy();
      const response = await request.post(`${api}/api/v1/auth/login`, {
        timeout: 120_000,
        data: { email: user.email, tenant_id: user.tenant_id, password: user.password || "O1bd-disposable-only!" },
      });
      expect(response.status(), await response.text()).toBe(200);
      const session = await response.json();
      const context = await browser.newContext();
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
      const response = await request.get(`${api}${base}${suffix}`, { headers: { Authorization: `Bearer ${token}` } });
      expect(response.status(), await response.text()).toBe(200);
      return response.json();
    }
    async function command(page: Page, suffix: string, action: () => Promise<unknown>, status = 200) {
      const start = performance.now();
      const pending = page.waitForResponse(
        (response) => response.url().endsWith(suffix) && ["POST", "PUT"].includes(response.request().method())
      );
      await action();
      const response = await pending;
      observations.push({ label: suffix, elapsed_ms: performance.now() - start, status: response.status() });
      expect(response.status(), await response.text()).toBe(status);
      await expect(page.locator("[aria-busy]").last()).toHaveAttribute("aria-busy", "false");
      return response.json();
    }
    async function fill(page: Page, label: string, value: unknown) {
      await page.getByLabel(label, { exact: true }).fill(String(value));
    }
    async function choose(page: Page, label: string, value: unknown) {
      await page.getByLabel(label, { exact: true }).selectOption(String(value));
    }
    async function tab(page: Page, name: string) {
      await page
        .getByRole("navigation", { name: "Progress Manager submodules" })
        .getByRole("button", { name, exact: true })
        .click();
    }
    async function refresh(page: Page) {
      const pending = page.waitForResponse(
        (response) => response.url().endsWith(`${root}/overview`) && response.request().method() === "GET"
      );
      await page.getByRole("button", { name: "Actualizar Progress", exact: true }).click();
      expect((await pending).status()).toBe(200);
      await expect(page.getByLabel("Progress Manager", { exact: true })).toHaveAttribute("aria-busy", "false");
    }
    async function context(page: Page, periodId: unknown) {
      await expect(page.getByRole("heading", { name: "Progress Manager", exact: true })).toBeVisible();
      await choose(page, "Progress Controls Period", periodId);
      await fill(page, "Progress as-of date", "2026-10-22");
      await fill(page, "Motivo Progress", reason);
    }
    async function openAdmin(role: string) {
      const user = await actor(role, "/app");
      await user.page.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }).click();
      for (const name of ["Platform Administration", "Process Configuration"]) {
        const button = user.page.getByRole("button", { name, exact: true });
        if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
      }
      await user.page.getByRole("button", { name: "Process & Operational Configuration", exact: true }).click();
      await user.page.getByRole("button", { name: "Progress Profiles", exact: true }).click();
      await expect(user.page.getByLabel("Progress Profiles configuration JSON", { exact: true })).not.toHaveValue("{}");
      return user;
    }
    async function selectMeasurement(page: Page, type: string, rowCode: string) {
      await tab(
        page,
        type === "MILESTONE"
          ? "Milestones / Rules of Credit"
          : type === "WEIGHTED"
            ? "Progress Overview"
            : type === "QUANTITY"
              ? "Quantity Progress"
              : "Physical Progress"
      );
      await page.getByRole("button", { name: `Ver ${type} measurements ${rowCode}`, exact: true }).click();
    }
    async function capture(
      page: Page,
      type: string,
      source: Record<string, unknown>,
      values: {
        numerator: string;
        unit: string;
        method?: string;
        phase?: string;
        weight?: string;
        rule?: number;
        step?: string;
        components?: Array<{ id: number; weight: string }>;
      }
    ) {
      await tab(
        page,
        type === "MILESTONE"
          ? "Milestones / Rules of Credit"
          : type === "WEIGHTED"
            ? "Progress Overview"
            : type === "QUANTITY"
              ? "Quantity Progress"
              : "Physical Progress"
      );
      await page.getByRole("button", { name: `Nueva medición ${type}`, exact: true }).click();
      const rowCode = code(type + String(source.scope_nature));
      for (const [label, value] of [
        [`${type} Code`, rowCode],
        [`${type} Name`, `Independent approved ${type} source`],
        [`${type} Source reference`, `FIELD-${rowCode}`],
        [`${type} Measurement date`, "2026-10-21"],
        [`${type} Numerator`, values.numerator],
        [`${type} Unit`, values.unit],
        [`${type} Weight`, values.weight || "1"],
        [`${type} Evidence reference`, `QA-FIELD-${rowCode}`],
      ])
        await fill(page, label, value);
      if (values.components?.length) await choose(page, `${type} Source Kind`, "PROJECT");
      else await choose(page, `${type} SCOPE`, source.id);
      await choose(page, `${type} Scope Nature`, source.scope_nature);
      await choose(page, `${type} Nature phase`, values.phase || "INSTALL");
      if (values.method) await choose(page, `${type} Method`, values.method);
      if (values.rule) await choose(page, `${type} Published rule`, values.rule);
      if (values.step) await page.getByLabel(`${type} Step ${values.step}`, { exact: true }).check();
      for (const component of values.components ?? [])
        await fill(page, `${type} Component ${component.id}`, component.weight);
      const row = await command(
        page,
        "/measurements",
        () => page.getByRole("button", { name: `Crear ${type} DRAFT`, exact: true }).click(),
        201
      );
      expect(row.code).toBe(rowCode);
      await command(page, `/measurements/${row.id}/transition`, () =>
        page.getByRole("button", { name: `Enviar ${type}`, exact: true }).click()
      );
      return row;
    }
    async function approve(page: Page, type: string, row: Record<string, unknown>) {
      await refresh(page);
      await selectMeasurement(page, type, String(row.code));
      await command(page, `/measurements/${row.id}/certify`, () =>
        page.getByRole("button", { name: `Certificar ${type}`, exact: true }).click()
      );
      await command(page, `/measurements/${row.id}/transition`, () =>
        page.getByRole("button", { name: `Revisar ${type}`, exact: true }).click()
      );
      const approved = await command(page, `/measurements/${row.id}/transition`, () =>
        page.getByRole("button", { name: `Aprobar ${type}`, exact: true }).click()
      );
      expect(approved.prepared_by).not.toBe(approved.approved_by);
      expect(approved.certified_by).not.toBe(approved.prepared_by);
      return approved;
    }
    try {
      const admin = await openAdmin("admin");
      const profileCode = code("POLICY");
      await fill(admin.page, "Progress Profiles Code", profileCode);
      await fill(
        admin.page,
        "Progress Profiles Name",
        "Independent Progress, ROC, evidence, weights and baseline policy"
      );
      const policy = JSON.parse(
        await admin.page.getByLabel("Progress Profiles configuration JSON", { exact: true }).inputValue()
      );
      expect(policy.allowed_progress_types).toHaveLength(7);
      expect(policy.allowed_methods).toHaveLength(6);
      expect(policy.rule_of_credit_templates.INSTALLATION.map((step: { weight: string }) => step.weight)).toEqual([
        "30",
        "20",
        "30",
        "20",
      ]);
      expect(policy.weighting_rules.allowed_bases).toContain("BUDGET");
      expect(policy.baseline_policy.require_approved_sources).toBe(true);
      policy.scope = { type: "workspace", workspace_id: project };
      await fill(admin.page, "Progress Profiles configuration JSON", JSON.stringify(policy, null, 2));
      await fill(admin.page, "Motivo Progress Profiles", reason);
      const profile = await command(
        admin.page,
        "/api/v1/progress/admin/profiles",
        () => admin.page.getByRole("button", { name: "Crear Progress Profiles DRAFT", exact: true }).click(),
        201
      );
      created.profile = profile.id;
      await fill(admin.page, "Motivo Progress Profiles", reason);
      await command(
        admin.page,
        `/${profile.id}/publish`,
        () => admin.page.getByRole("button", { name: "Publicar Progress Profiles", exact: true }).click(),
        403
      );
      mark("ADMIN_SELF_PUBLICATION_DENIED_AND_SEVEN_TYPES_SIX_METHODS");
      const publisherAdmin = await openAdmin("publisher");
      await publisherAdmin.page
        .getByRole("button", { name: `Ver Progress Profiles ${profileCode}`, exact: true })
        .click();
      await fill(publisherAdmin.page, "Motivo Progress Profiles", reason);
      const publishedPolicy = await command(publisherAdmin.page, `/${profile.id}/publish`, () =>
        publisherAdmin.page.getByRole("button", { name: "Publicar Progress Profiles", exact: true }).click()
      );
      expect(publishedPolicy.content_json.rule_of_credit_templates).toEqual(policy.rule_of_credit_templates);
      expect(publishedPolicy.content_json.weighting_rules).toEqual(policy.weighting_rules);
      expect(publishedPolicy.content_json.baseline_policy).toEqual(policy.baseline_policy);
      await expect(
        publisherAdmin.page.getByLabel("Progress Profiles configuration JSON", { exact: true })
      ).toBeDisabled();
      await publisherAdmin.page.screenshot({ path: path.join(output, "admin-progress-published.png"), fullPage: true });
      mark("ADMIN_POLICY_INDEPENDENT_PUBLICATION_IMMUTABLE_AND_SEPARATE_FROM_USER");
      await admin.page.context().close();
      await publisherAdmin.page.context().close();

      const recorder = await actor("cost_controller");
      const manager = await actor("manager");
      const publisher = await actor("publisher");
      const overview = await get(recorder.token, "/overview");
      const period = overview.periods.find(
        (row: Record<string, unknown>) => row.period_code === "PROGRESS-OCT" && row.status === "OPEN"
      );
      const install = overview.scope_items.find(
        (row: Record<string, unknown>) => row.scope_nature === "INSTALL" && row.status === "APPROVED"
      );
      const remove = overview.scope_items.find(
        (row: Record<string, unknown>) => row.scope_nature === "REMOVE" && row.status === "APPROVED"
      );
      expect(period && install && remove).toBeTruthy();
      expect(Number(install.quantity)).toBeGreaterThan(0);
      for (const page of [recorder.page, manager.page, publisher.page]) await context(page, period.id);
      await expect(
        recorder.page.getByRole("navigation", { name: "Progress Manager submodules" }).getByRole("button")
      ).toHaveCount(10);
      await expect(recorder.page.getByRole("button", { name: "Progress Profiles", exact: true })).toHaveCount(0);
      mark("CANONICAL_PROJECT_CONTEXT_EXPLICIT_PERIOD_ASOF_TEN_TABS_AND_ADMIN_USER_SEPARATION");
      const beforeSchedule = await get(recorder.token, "/schedule-progress?as_of=2026-10-22");
      const quantity = await capture(recorder.page, "QUANTITY", install, {
        numerator: String(Number(install.quantity) / 2),
        unit: String(install.unit),
      });
      expect(Number(quantity.progress_value)).toBe(50);
      expect(Number(quantity.denominator)).toBe(Number(install.quantity));
      await expect(recorder.page.getByRole("button", { name: "Certificar QUANTITY", exact: true })).toHaveCount(0);
      await approve(manager.page, "QUANTITY", quantity);
      created.quantity = quantity.id;
      await manager.page.screenshot({
        path: path.join(output, "quantity-certified-cumulative-and-period.png"),
        fullPage: true,
      });
      mark("QUANTITY_FROZEN_DENOMINATOR_CAPTURE_SUBMIT_INDEPENDENT_CERTIFICATION_REVIEW_APPROVAL");
      const physical = await capture(recorder.page, "PHYSICAL", install, {
        numerator: String(Number(install.quantity) / 2),
        unit: String(install.unit),
      });
      const approvedPhysical = await approve(manager.page, "PHYSICAL", physical);
      expect(Number(approvedPhysical.progress_value)).toBe(50);
      created.physical = physical.id;
      await expect(manager.page.getByRole("button", { name: "Crear sucesor PHYSICAL", exact: true })).toBeVisible();
      await expect(manager.page.getByRole("button", { name: "Guardar PHYSICAL DRAFT", exact: true })).toHaveCount(0);
      await manager.page.screenshot({ path: path.join(output, "physical-independent-approved.png"), fullPage: true });
      mark("PHYSICAL_APPROVED_IMMUTABILITY_SUCCESSOR_ONLY_NOT_P6_OR_COST");

      await tab(recorder.page, "Milestones / Rules of Credit");
      await fill(recorder.page, "Rule Code", code("ROC"));
      await fill(recorder.page, "Rule Name", "Removal independently credited steps");
      await recorder.page.getByLabel("Rule Nature REMOVE", { exact: true }).check();
      const rule = await command(
        recorder.page,
        "/rules",
        () => recorder.page.getByRole("button", { name: "Crear regla DRAFT", exact: true }).click(),
        201
      );
      await refresh(manager.page);
      await tab(manager.page, "Milestones / Rules of Credit");
      await manager.page.getByRole("button", { name: `Ver Progress Rules ${rule.code}`, exact: true }).click();
      await command(manager.page, `/rules/${rule.id}/publish`, () =>
        manager.page.getByRole("button", { name: "Publicar regla", exact: true }).click()
      );
      await expect(manager.page.getByLabel("Rule Step Weight 1", { exact: true })).toBeDisabled();
      await manager.page.screenshot({
        path: path.join(output, "rule-of-credit-published-immutable.png"),
        fullPage: true,
      });
      await refresh(recorder.page);
      const credited = await capture(recorder.page, "PHYSICAL", remove, {
        numerator: "0",
        unit: "%",
        method: "RULE_OF_CREDIT",
        phase: "REMOVE",
        weight: "3",
        rule: rule.id,
        step: "SET",
      });
      expect(Number(credited.progress_value)).toBe(30);
      await approve(manager.page, "PHYSICAL", credited);
      created.rule = rule.id;
      created.credited = credited.id;
      mark("RULE_OF_CREDIT_30_20_30_20_PUBLISHED_AND_REMOVE_PHASE_APPROVED");

      await tab(recorder.page, "Milestones / Rules of Credit");
      await recorder.page.getByRole("button", { name: "Nueva regla de crédito", exact: true }).click();
      await fill(recorder.page, "Rule Code", code("MILESTONE"));
      await fill(recorder.page, "Rule Name", "Governed zero hundred milestone");
      await choose(recorder.page, "Rule Method", "MILESTONE_BASED");
      await choose(recorder.page, "Rule Preset", "100");
      const milestoneRule = await command(
        recorder.page,
        "/rules",
        () => recorder.page.getByRole("button", { name: "Crear regla DRAFT", exact: true }).click(),
        201
      );
      await refresh(manager.page);
      await tab(manager.page, "Milestones / Rules of Credit");
      await manager.page.getByRole("button", { name: `Ver Progress Rules ${milestoneRule.code}`, exact: true }).click();
      await command(manager.page, `/rules/${milestoneRule.id}/publish`, () =>
        manager.page.getByRole("button", { name: "Publicar regla", exact: true }).click()
      );
      await refresh(recorder.page);
      const milestone = await capture(recorder.page, "MILESTONE", install, {
        numerator: "0",
        unit: "%",
        method: "MILESTONE_BASED",
        rule: milestoneRule.id,
        step: "STEP-1",
      });
      expect(Number(milestone.progress_value)).toBe(100);
      await approve(manager.page, "MILESTONE", milestone);
      created.milestone = milestone.id;
      await manager.page.screenshot({
        path: path.join(output, "milestone-independently-certified-approved.png"),
        fullPage: true,
      });
      mark("PROGRESS_MILESTONE_ZERO_HUNDRED_CERTIFIED_SEPARATE_FROM_SCHEDULE_DATES");

      await refresh(recorder.page);
      const weighted = await capture(recorder.page, "WEIGHTED", install, {
        numerator: "0",
        unit: "%",
        components: [
          { id: physical.id, weight: "1" },
          { id: credited.id, weight: "3" },
        ],
      });
      expect(Number(weighted.progress_value)).toBe(35);
      expect(weighted.scope_item_id).toBeNull();
      expect(weighted.plan_item_id).toBeNull();
      expect(weighted.work_package_id).toBeNull();
      expect(weighted.subject_key).toContain("PROJECT_DERIVED");
      await approve(manager.page, "WEIGHTED", weighted);
      created.weighted = weighted.id;
      await manager.page.screenshot({
        path: path.join(output, "weighted-explicit-source-weights-approved.png"),
        fullPage: true,
      });
      mark("WEIGHTED_PROJECT_DERIVED_APPROVED_COMPONENTS_EXPLICIT_WEIGHTS_NOT_UNWEIGHTED_MEAN");

      const beforeBundle = await get(recorder.token, "/overview");
      const scopeBaseline = beforeBundle.scope_baselines.find(
        (row: Record<string, unknown>) => row.id === fixture.scope_baseline.id && row.approved_by && row.approved_at
      );
      const scheduleBaseline = beforeBundle.schedule_baselines.find(
        (row: Record<string, unknown>) => row.id === fixture.schedule_baseline.id && row.status === "APPROVED_BASELINE"
      );
      const costBaseline = beforeBundle.cost_baselines.find(
        (row: Record<string, unknown>) => row.id === fixture.cost_baseline.id && row.status === "APPROVED"
      );
      expect(scopeBaseline && scheduleBaseline && costBaseline).toBeTruthy();
      await tab(recorder.page, "Baseline Integration");
      await fill(recorder.page, "Bundle Code", code("BUNDLE"));
      await fill(recorder.page, "Bundle Name", "Approved integrated project control references");
      await choose(recorder.page, "Bundle Scope Baseline", scopeBaseline.id);
      await choose(recorder.page, "Bundle Schedule Baseline", scheduleBaseline.id);
      await choose(recorder.page, "Bundle Cost Baseline", costBaseline.id);
      await fill(recorder.page, "Bundle Effective date", "2026-10-19");
      const bundle = await command(
        recorder.page,
        "/baseline-bundles",
        () => recorder.page.getByRole("button", { name: "Crear Baseline Bundle DRAFT", exact: true }).click(),
        201
      );
      await command(recorder.page, `/baseline-bundles/${bundle.id}/transition`, () =>
        recorder.page.getByRole("button", { name: "Revisar Baseline Bundle", exact: true }).click()
      );
      await refresh(manager.page);
      await tab(manager.page, "Baseline Integration");
      await manager.page.getByRole("button", { name: `Ver Baseline Bundles ${bundle.code}`, exact: true }).click();
      const approvedBundle = await command(manager.page, `/baseline-bundles/${bundle.id}/transition`, () =>
        manager.page.getByRole("button", { name: "Aprobar Baseline Bundle", exact: true }).click()
      );
      created.bundle = bundle.id;
      const frozenBundleHash = approvedBundle.content_hash;
      const bundleValidation = await get(manager.token, `/baseline-bundles/${bundle.id}/validate`);
      expect(bundleValidation.status).toBe("VALID");
      await expect(manager.page.getByText("Validación del bundle: VALID", { exact: true })).toBeVisible();
      await manager.page.screenshot({ path: path.join(output, "integrated-baseline-approved.png"), fullPage: true });
      mark("SCOPE_SCHEDULE_COST_PROFILE_IDENTITIES_FROZEN_IN_INDEPENDENT_APPROVED_BUNDLE");

      await tab(manager.page, "Earned Progress");
      await choose(manager.page, "EVM Baseline Bundle", bundle.id);
      await expect(manager.page.getByText("Resultado EVM: COMPUTABLE", { exact: true })).toBeVisible();
      const evm = await get(manager.token, `/evm?bundle_id=${bundle.id}&period_id=${period.id}&as_of=2026-10-22`);
      expect(evm.status).toBe("COMPUTABLE");
      expect(Number(evm.ev)).toBeGreaterThan(0);
      expect(Number(evm.ac)).toBeGreaterThan(0);
      expect(Number(evm.cpi)).toBeCloseTo(Number(evm.ev) / Number(evm.ac), 6);
      expect(
        evm.earned_lines.some((line: Record<string, unknown>) => line.measurement_id === physical.id)
      ).toBeTruthy();
      expect(evm.earned_lines.some((line: Record<string, unknown>) => line.measurement_id === quantity.id)).toBeFalsy();
      for (const line of evm.earned_lines)
        expect(Number(line.earned_value)).toBeCloseTo(
          (Number(line.budgeted_value) * Number(line.progress_value)) / 100,
          6
        );
      for (const name of ["Planned S Curve", "Approved Actual Progress Curve", "Earned Curve"])
        await expect(manager.page.getByRole("table", { name, exact: true })).toBeVisible();
      const savedEvm = await command(
        manager.page,
        "/evm/snapshots",
        () => manager.page.getByRole("button", { name: "Publicar snapshot EVM", exact: true }).click(),
        201
      );
      created.evm_snapshot = savedEvm.id;
      await manager.page.screenshot({ path: path.join(output, "earned-pv-ev-ac-and-curves.png"), fullPage: true });
      mark("COMPUTABLE_PV_EV_AC_CPI_SPI_APPROVED_PHYSICAL_PRIORITY_CURVES_AND_SNAPSHOT");
      await fill(manager.page, "EVM Requested currency", "EUR");
      await expect(manager.page.getByText("Resultado EVM: NOT_COMPUTABLE", { exact: true })).toBeVisible();
      const incompatible = await get(
        manager.token,
        `/evm?bundle_id=${bundle.id}&period_id=${period.id}&as_of=2026-10-22&currency=EUR`
      );
      expect(incompatible.reason_codes.length).toBeGreaterThan(0);
      for (const metric of ["pv", "ev", "ac", "cpi", "spi"]) expect(incompatible[metric]).toBeNull();
      await expect(manager.page.getByRole("button", { name: "Publicar snapshot EVM", exact: true })).toBeDisabled();
      mark("INCOMPATIBLE_CURRENCY_NOT_COMPUTABLE_WITH_REASONS_NO_PLAUSIBLE_ZERO");
      await fill(manager.page, "EVM Requested currency", "");

      await tab(manager.page, "Progress Overview");
      await choose(manager.page, "4D Progress Baseline Bundle", bundle.id);
      const overlay = await get(
        manager.token,
        `/four-d-overlay?bundle_id=${bundle.id}&period_id=${period.id}&as_of=2026-10-22`
      );
      expect(overlay.authority.ifc_mutated).toBe(false);
      expect(overlay.authority.schedule_mutated).toBe(false);
      expect(new Set(overlay.items.map((row: Record<string, unknown>) => row.scope_nature)).size).toBe(4);
      expect(
        overlay.items.some(
          (row: { approved_physical_state: { state: string } }) => row.approved_physical_state.state === "REMOVAL"
        )
      ).toBeTruthy();
      await expect(
        manager.page.getByRole("table", { name: "Schedule versus approved physical progress", exact: true })
      ).toBeVisible();
      await manager.page.screenshot({
        path: path.join(output, "progress-aggregation-4d-nature-comparison.png"),
        fullPage: true,
      });
      const afterSchedule = await get(manager.token, "/schedule-progress?as_of=2026-10-22");
      expect(afterSchedule).toEqual(beforeSchedule);
      mark("REAL_IFC_FOUR_NATURE_4D_VERSUS_APPROVED_PHYSICAL_NO_GEOMETRY_OR_DATE_MUTATION");
      await tab(manager.page, "Schedule Progress");
      await expect(manager.page.getByRole("table", { name: "SCHEDULE separate progress", exact: true })).toBeVisible();
      await manager.page.screenshot({
        path: path.join(output, "schedule-separate-source-projection.png"),
        fullPage: true,
      });
      await tab(manager.page, "Cost Progress");
      await expect(manager.page.getByRole("table", { name: "COST separate progress", exact: true })).toBeVisible();
      await manager.page.screenshot({
        path: path.join(output, "cost-separate-recognized-source-projection.png"),
        fullPage: true,
      });
      mark("SCHEDULE_COST_READ_PROJECTIONS_VISIBLE_NO_PHYSICAL_AUTOMATION");

      await tab(manager.page, "Period Review");
      await fill(manager.page, "Period Review notes", "Independent complete candidate set for controlled release");
      await command(manager.page, `/periods/${period.id}/transition`, () =>
        manager.page.getByRole("button", { name: "Congelar Progress para revisión", exact: true }).click()
      );
      await refresh(recorder.page);
      await tab(recorder.page, "Quantity Progress");
      await recorder.page.getByRole("button", { name: "Nueva medición QUANTITY", exact: true }).click();
      await expect(recorder.page.getByRole("button", { name: "Crear QUANTITY DRAFT", exact: true })).toBeDisabled();
      await recorder.page.context().close();
      await command(manager.page, `/periods/${period.id}/transition`, () =>
        manager.page.getByRole("button", { name: "Cerrar período Progress", exact: true }).click()
      );
      await command(
        manager.page,
        `/periods/${period.id}/transition`,
        () => manager.page.getByRole("button", { name: "Publicar período Progress", exact: true }).click(),
        403
      );
      await refresh(publisher.page);
      await tab(publisher.page, "Period Review");
      await command(publisher.page, `/periods/${period.id}/transition`, () =>
        publisher.page.getByRole("button", { name: "Publicar período Progress", exact: true }).click()
      );
      const frozenPeriod = await get(publisher.token, `/periods/${period.id}/review`);
      expect(frozenPeriod.period.status).toBe("PUBLISHED");
      expect(frozenPeriod.snapshot.candidate_snapshot_json.length).toBe(5);
      await publisher.page.screenshot({
        path: path.join(output, "period-frozen-closed-independently-published.png"),
        fullPage: true,
      });
      mark("PERIOD_REVIEW_CANDIDATES_FROZEN_CAPTURE_DISABLED_CLOSED_INDEPENDENTLY_PUBLISHED");
      await tab(publisher.page, "Progress History");
      await expect(publisher.page.getByRole("table", { name: "Progress History", exact: true })).toContainText(
        "PROGRESS_PERIOD_PUBLISHED"
      );
      await publisher.page.screenshot({
        path: path.join(output, "progress-history-visible-approval-lineage.png"),
        fullPage: true,
      });
      mark("SOURCE_AND_APPROVAL_HISTORY_VISIBLE");
      await publisher.page.context().close();

      const performanceTargets = [
        ["Progress overview", "/overview"],
        ["Quantity Progress", `/quantity-progress?period_id=${period.id}`],
        ["Physical Progress", `/physical-progress?period_id=${period.id}`],
        [
          "Physical aggregation",
          `/aggregation?progress_type=PHYSICAL&group_by=PROJECT&period_id=${period.id}&as_of=2026-10-22`,
        ],
        ["Period review", `/periods/${period.id}/review`],
        [
          "Weighted aggregation",
          `/aggregation?progress_type=WEIGHTED&group_by=PROJECT&period_id=${period.id}&as_of=2026-10-22`,
        ],
        ["Baseline bundle validation", `/baseline-bundles/${bundle.id}/validate`],
        ["EVM computable read", `/evm?bundle_id=${bundle.id}&period_id=${period.id}&as_of=2026-10-22`],
        ["4D Progress overlay", `/four-d-overlay?bundle_id=${bundle.id}&period_id=${period.id}&as_of=2026-10-22`],
      ];
      const performanceSamples: Array<{
        label: string;
        endpoint: string;
        samples_ms: number[];
        http_status: number[];
        result_status: unknown[];
      }> = [];
      const performanceRows: Array<[string, number, number, number, number]> = [];
      for (const [label, endpoint] of performanceTargets) {
        const samples: number[] = [];
        const statuses: number[] = [];
        const resultStatuses: unknown[] = [];
        for (let index = 0; index < 3; index++) {
          const started = performance.now();
          const response = await manager.page.request.get(`${api}${root}${endpoint}`, {
            headers: { Authorization: `Bearer ${manager.token}` },
          });
          const body = await response.json();
          samples.push(Number((performance.now() - started).toFixed(3)));
          statuses.push(response.status());
          resultStatuses.push(body.status ?? body.authority ?? body.period?.status ?? null);
          expect(response.status(), JSON.stringify(body)).toBe(200);
          if (label === "EVM computable read") expect(body.status).toBe("COMPUTABLE");
          if (label === "Baseline bundle validation") expect(body.status).toBe("VALID");
        }
        const orderedSamples = [...samples].sort((left, right) => left - right);
        performanceRows.push([label, samples.length, orderedSamples[0], orderedSamples[1], orderedSamples[2]]);
        performanceSamples.push({
          label,
          endpoint,
          samples_ms: samples,
          http_status: statuses,
          result_status: resultStatuses,
        });
      }
      const performanceContext = await get(manager.token, "/overview");
      writeFileSync(
        path.join(output, "performance.json"),
        JSON.stringify(
          {
            result: "OBSERVED_NOT_SLA",
            stage: "AFTER_PERIOD_PUBLICATION_BEFORE_PROFILE_DRIFT",
            measurement:
              "Sequential real authenticated Playwright browser-context HTTP reads; includes response JSON transfer and parsing. No business mocks, artificial delays or latency SLA assertions.",
            columns: ["operation", "samples", "min_ms", "median_ms", "max_ms"],
            rows: performanceRows,
            samples: performanceSamples,
            volumes: {
              project_workspace_id: project,
              measurements: performanceContext.measurements.length,
              quantity_measurements: performanceContext.measurements.filter(
                (row: Record<string, unknown>) => row.progress_type === "QUANTITY"
              ).length,
              physical_measurements: performanceContext.measurements.filter(
                (row: Record<string, unknown>) => row.progress_type === "PHYSICAL"
              ).length,
              weighted_measurements: performanceContext.measurements.filter(
                (row: Record<string, unknown>) => row.progress_type === "WEIGHTED"
              ).length,
              scope_items: performanceContext.scope_items.length,
              plan_items: performanceContext.plan_items.length,
              packages: performanceContext.packages.length,
              schedule_versions: performanceContext.schedule_versions.length,
              schedule_activities: beforeSchedule.items.length,
              scope_baselines: performanceContext.scope_baselines.length,
              schedule_baselines: performanceContext.schedule_baselines.length,
              cost_baselines: performanceContext.cost_baselines.length,
              periods: performanceContext.periods.length,
              control_accounts: performanceContext.control_accounts.length,
              overlay_items: overlay.items.length,
            },
            completed_at: new Date().toISOString(),
          },
          null,
          2
        )
      );
      mark("NINE_REAL_READ_OPERATIONS_THREE_SAMPLES_EACH_WITH_CONTEXT_VOLUMES_NOT_SLA");

      const driftAdmin = await openAdmin("admin");
      await driftAdmin.page.getByRole("button", { name: `Ver Progress Profiles ${profileCode}`, exact: true }).click();
      await fill(driftAdmin.page, "Motivo Progress Profiles", reason);
      const successor = await command(
        driftAdmin.page,
        `/${profile.id}/successor`,
        () => driftAdmin.page.getByRole("button", { name: "Crear Progress Profiles sucesor", exact: true }).click(),
        201
      );
      const revisedPolicy = JSON.parse(
        await driftAdmin.page.getByLabel("Progress Profiles configuration JSON", { exact: true }).inputValue()
      );
      revisedPolicy.tolerance = "0.000002";
      await fill(driftAdmin.page, "Progress Profiles configuration JSON", JSON.stringify(revisedPolicy, null, 2));
      await command(driftAdmin.page, `/${successor.id}`, () =>
        driftAdmin.page.getByRole("button", { name: "Guardar Progress Profiles borrador", exact: true }).click()
      );
      const driftPublisher = await openAdmin("publisher");
      await driftPublisher.page
        .getByRole("button", { name: `Ver Progress Profiles ${profileCode}`, exact: true })
        .last()
        .click();
      await fill(driftPublisher.page, "Motivo Progress Profiles", reason);
      await command(driftPublisher.page, `/${successor.id}/publish`, () =>
        driftPublisher.page.getByRole("button", { name: "Publicar Progress Profiles", exact: true }).click()
      );
      await driftAdmin.page.context().close();
      await driftPublisher.page.context().close();
      await refresh(manager.page);
      await tab(manager.page, "Baseline Integration");
      await manager.page.getByRole("button", { name: `Ver Baseline Bundles ${bundle.code}`, exact: true }).click();
      await expect(manager.page.getByText("Validación del bundle: BLOCK", { exact: true })).toBeVisible();
      await expect(manager.page.getByText("BUNDLE_SOURCE_DRIFT", { exact: true })).toBeVisible();
      const stale = await get(manager.token, `/baseline-bundles/${bundle.id}/validate`);
      expect(stale.effective_state).toBe("REQUIRES_REVIEW");
      const unchangedBundle = await get(manager.token, `/baseline-bundles/${bundle.id}`);
      expect(unchangedBundle.content_hash).toBe(frozenBundleHash);
      expect(stale.approved_bundle_mutated).toBe(false);
      await manager.page.screenshot({
        path: path.join(output, "baseline-stale-explicit-review-not-silent-rebaseline.png"),
        fullPage: true,
      });
      const unchangedPeriod = await get(manager.token, `/periods/${period.id}/review`);
      expect(unchangedPeriod.snapshot.content_hash).toBe(frozenPeriod.snapshot.content_hash);
      mark("PUBLISHED_POLICY_DRIFT_REQUIRES_REVIEW_FROZEN_BUNDLE_AND_PUBLISHED_PERIOD_UNCHANGED");
      expect(errors).toEqual([]);
      mark("ZERO_CHROMIUM_RUNTIME_ERRORS_NO_BUSINESS_RESPONSE_MOCKS");
      writeFileSync(
        path.join(output, "browser-uat.json"),
        JSON.stringify(
          {
            result: "PASS",
            checks,
            observations,
            performance: performanceRows,
            performance_observations_file: "performance.json",
            browser_errors: errors,
            project_workspace_id: project,
            created,
            evm,
            overlay,
            completed_at: new Date().toISOString(),
          },
          null,
          2
        )
      );
    } catch (error) {
      writeFileSync(
        path.join(output, "browser-uat-failure.json"),
        JSON.stringify(
          { result: "FAIL", checks, observations, browser_errors: errors, created, error: String(error) },
          null,
          2
        )
      );
      for (const [index, page] of pages.entries())
        if (!page.isClosed())
          await page
            .screenshot({ path: path.join(output, `failure-${index}.png`), fullPage: true })
            .catch(() => undefined);
      throw error;
    } finally {
      for (const page of pages) await page.context().close();
    }
  });
});
