import { expect, type Locator, type Page, test } from "@playwright/test";

async function login(page: Page, user = "admin") {
  await page.goto("/login");
  await page.getByLabel("User").fill(user);
  await page.getByLabel("Password").fill("1234");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
}

async function expand(button: Locator) {
  await expect(button).toBeVisible();
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
  await expect(button).toHaveAttribute("aria-expanded", "true");
}

async function openPhase(page: Page, navigationName: RegExp, phaseName: string) {
  const navigation = page.getByRole("navigation", { name: navigationName });
  await expand(navigation.getByRole("button", { name: "Enterprise Strategy Manager", exact: true }));
  const modules = navigation.getByRole("group", { name: "Módulos de Enterprise Strategy Manager" });
  const phase = modules.locator(":scope > .navigatorModule > .navigatorModuleButton").filter({ hasText: phaseName });
  await expect(phase).toHaveCount(1);
  await expand(phase);
  return modules;
}

test("07M-BEN keeps USER Benefits Plans and ADMIN policy configuration separated", async ({ page }) => {
  await login(page);
  const userModules = await openPhase(page, /validation focus|control flow/i, "Business Case & Investment Development");
  await userModules.getByRole("button", { name: "Strategic Benefits Plan & Traceability", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/strategy\/strategic-benefits-my$/);

  const user = page.getByRole("region", { name: "Strategic Benefits Plan and Traceability" });
  await expect(user).toBeVisible();
  await expect(user.getByRole("navigation", { name: "Strategic Benefits views" }).getByRole("button")).toHaveCount(16);
  await expect(user.getByRole("group", { name: "Strategic Benefits queues" }).getByRole("button")).toHaveCount(8);
  await expect(user.getByRole("button", { name: /Publish|Archive|Clone/ })).toHaveCount(0);
  await expect(user).toContainText("Output is what the Project delivers");
  await expect(user).toContainText("actual KPI");

  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  const adminModules = await openPhase(page, /admin mode navigation/i, "Project Definition & Investment Case");
  await adminModules.getByRole("button", { name: "Benefits Configuration", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/admin\/strategy\/benefits-configuration$/);

  const admin = page.getByRole("region", { name: "Benefits Configuration" });
  await expect(admin).toBeVisible();
  await expect(
    admin.getByRole("navigation", { name: "Benefits configuration sections" }).getByRole("button")
  ).toHaveCount(23);
  await expect(admin.getByRole("button", { name: /^Submit$/ })).toHaveCount(0);
  await expect(admin.getByRole("button", { name: /^Complete$/ })).toHaveCount(0);
  await expect(admin).toContainText("cannot create, edit, assign owners, submit, review, complete or revise");
});

test("07M-BEN canonical deep routes preserve mode guards and optimized traceability", async ({ page }) => {
  await login(page, "camila.cost@demo.local");
  let traceabilityRequests = 0;
  page.on("request", (request) => {
    if (/\/strategic-benefits-plans\/\d+\/traceability/.test(request.url())) traceabilityRequests += 1;
  });

  await page.goto("/app/strategy/strategic-benefits-traceability");
  await expect(page).toHaveURL(/\/app\/strategy\/strategic-benefits-traceability$/);
  await expect(page.getByRole("navigation", { name: "Strategic workflow breadcrumb" })).toContainText("Traceability");
  await expect.poll(() => traceabilityRequests).toBeLessThanOrEqual(1);

  await page.goto("/app/admin/strategy/benefits-configuration");
  const denied = page.getByRole("alert", { name: "Strategic configuration access denied" });
  await expect(denied).toBeVisible();
  await expect(denied).toHaveAttribute("data-control-classification", "ADMIN_CONFIGURATION");
});

test("07M-BEN USER creates a governed Plan and completes Benefit, KPI, lineage, readiness and lifecycle evidence [contract-intercepted]", async ({
  page,
}) => {
  type JsonRecord = Record<string, unknown>;
  type Mutation = { action: string; idempotency?: boolean; ifMatch?: string; payload?: JsonRecord };

  let exists = false;
  let lifecycleStatus = "DRAFT";
  let revisionVersion = 1;
  let planDraft: JsonRecord = {
    overview_json: {},
    outputs_json: [],
    outcomes_json: [],
    assumptions_json: [],
    constraints_json: [],
    fel_stage_code: "FEL-2",
    reviewer_user_id: 22,
  };
  let benefit: JsonRecord | null = null;
  let measure: JsonRecord | null = null;
  const mutations: Mutation[] = [];

  const allowedActions = () => ({
    can_edit: lifecycleStatus === "DRAFT",
    can_add_benefit: lifecycleStatus === "DRAFT",
    can_edit_benefit: lifecycleStatus === "DRAFT",
    can_assign_owner: lifecycleStatus === "DRAFT",
    can_submit: lifecycleStatus === "DRAFT",
    can_start_review: lifecycleStatus === "SUBMITTED",
    can_return: lifecycleStatus === "IN_REVIEW",
    can_complete: lifecycleStatus === "IN_REVIEW",
    can_void: lifecycleStatus === "DRAFT",
    can_create_revision: lifecycleStatus === "COMPLETED",
    can_view_sources: true,
    can_refresh_preview: lifecycleStatus === "COMPLETED",
    can_refresh_apply: lifecycleStatus === "COMPLETED",
  });

  const versionRecord = () => ({
    id: 201,
    benefits_plan_id: 101,
    version_number: 1,
    version_purpose: "INITIAL_BENEFITS_PLAN",
    status: lifecycleStatus,
    ...structuredClone(planDraft),
    benefits: benefit
      ? [
          {
            ...structuredClone(benefit),
            measures: measure ? [structuredClone(measure)] : [],
            allowed_actions: allowedActions(),
          },
        ]
      : [],
    readiness_json: {},
    overall_benefits_readiness: lifecycleStatus === "COMPLETED" ? "READY" : "IN_PROGRESS",
    readiness_status: lifecycleStatus === "COMPLETED" ? "READY" : "IN_PROGRESS",
    readiness_warnings_json: [],
    readiness_blockers_json: lifecycleStatus === "COMPLETED" ? [] : ["LIFECYCLE_NOT_COMPLETED"],
    coverage: {
      benefit_definition_coverage: benefit ? 100 : 0,
      owner_coverage: benefit ? 100 : 0,
      baseline_coverage: measure ? 100 : 0,
      target_coverage: measure ? 100 : 0,
      traceability_coverage: benefit && measure ? 100 : 0,
    },
    source_references_json: {
      strategic_objective: { code: "STR-01" },
      need_opportunity: { reference: "NEED-501" },
      business_analysis: { reference: "BA-501" },
      recommended_option: { reference: "OPT-501" },
      business_case: { reference: "BC-501" },
    },
    source_hashes_json: { business_case: "source-hash" },
    source_current: true,
    configuration_current: true,
    configuration_id: 81,
    configuration_revision: 3,
    configuration_hash: "configuration-hash",
    source_bundle_hash: "source-bundle-hash",
    content_hash: "content-hash",
    benefit_set_hash: "benefit-set-hash",
    traceability_hash: "traceability-hash",
    benefits_plan_hash: "benefits-plan-hash",
    preparer_user_id: 11,
    reviewer_user_id: 22,
    revision_version: revisionVersion,
    allowed_actions: allowedActions(),
    can_supply_investment_gate_evidence: lifecycleStatus === "COMPLETED",
    created_at: "2026-09-17T10:00:00Z",
    updated_at: "2026-09-17T10:10:00Z",
  });

  const planRecord = () => ({
    id: 101,
    plan_number: "BPL-000101",
    project_workspace_id: 501,
    project_workspace_name: "North Interconnection",
    status: lifecycleStatus,
    current_version_id: 201,
    current_version: versionRecord(),
    configuration_id: 81,
    configuration_revision: 3,
    configuration_hash: "configuration-hash",
    configuration_source_workspace_id: 1,
    configuration_resolution_chain_json: [{ scope: "ENTERPRISE", id: 1 }],
    created_by: 11,
    updated_by: 11,
    revision_version: revisionVersion,
    allowed_actions: allowedActions(),
    final_output: lifecycleStatus === "COMPLETED" ? "READY_FOR_GOVERNED_BENEFITS_PLAN_EVIDENCE" : "IN_PROGRESS",
    next_process: lifecycleStatus === "COMPLETED" ? "ENHANCE_GATE07M_BC_WITH_FIVE_CASE_MODEL" : "COMPLETE_PLAN",
    created_at: "2026-09-17T10:00:00Z",
    updated_at: "2026-09-17T10:10:00Z",
  });

  const readinessRecord = () => ({
    benefits_plan_id: 101,
    version_id: 201,
    status: lifecycleStatus === "COMPLETED" ? "READY" : "IN_PROGRESS",
    overall_benefits_readiness: lifecycleStatus === "COMPLETED" ? "READY" : "IN_PROGRESS",
    dimensions: {
      PLAN_DEFINITION_READINESS: benefit ? "READY" : "BLOCKED",
      STRATEGIC_ALIGNMENT_READINESS: "READY",
      OUTPUT_READINESS: benefit ? "READY" : "BLOCKED",
      OUTCOME_READINESS: benefit ? "READY" : "BLOCKED",
      BENEFIT_DEFINITION_READINESS: benefit ? "READY" : "BLOCKED",
      BENEFIT_OWNER_READINESS: benefit ? "READY" : "BLOCKED",
      MEASURE_READINESS: measure ? "READY" : "BLOCKED",
      BASELINE_READINESS: measure ? "READY" : "BLOCKED",
      TARGET_READINESS: measure ? "READY" : "BLOCKED",
      EXPECTED_VALUE_READINESS: benefit ? "READY" : "BLOCKED",
      TRACEABILITY_READINESS: benefit && measure ? "READY" : "BLOCKED",
      SOURCE_CURRENCY_READINESS: "READY",
    },
    coverage: {
      benefit_definition_coverage: benefit ? 100 : 0,
      benefit_owner_coverage: benefit ? 100 : 0,
      measure_coverage: measure ? 100 : 0,
      baseline_coverage: measure ? 100 : 0,
      target_coverage: measure ? 100 : 0,
      traceability_coverage: benefit && measure ? 100 : 0,
    },
    warnings: [],
    blockers: lifecycleStatus === "COMPLETED" ? [] : ["Complete the governed lifecycle"],
    source_current: true,
    configuration_current: true,
    can_supply_investment_gate_evidence: lifecycleStatus === "COMPLETED",
    benefits_plan_hash: "benefits-plan-hash",
    source_bundle_hash: "source-bundle-hash",
    configuration_hash: "configuration-hash",
    persisted: true,
  });

  await page.route("**/api/v1/strategic-benefits-plans**", async (route) => {
    const request = route.request();
    const method = request.method();
    const pathname = new URL(request.url()).pathname;
    const headers = request.headers();
    const payload = request.postDataJSON() as JsonRecord | null;

    if (method === "GET" && pathname.endsWith("/options")) {
      await route.fulfill({
        status: 200,
        json: {
          version_purposes: ["INITIAL_BENEFITS_PLAN", "MATERIAL_CHANGE_UPDATE"],
          queues: ["mine", "draft", "in_review", "returned", "ready", "completed", "stale", "all_authorized"],
          readiness_states: ["NOT_STARTED", "IN_PROGRESS", "READY", "BLOCKED", "STALE"],
          provider_key: "BENEFITS_READINESS_PROVIDER",
          provider_status: "AVAILABLE",
          configuration_id: 81,
          configuration_revision: 3,
          configuration_hash: "configuration-hash",
          benefit_types: ["OPERATIONAL", "FINANCIAL", "REGULATORY"],
          benefit_categories: ["RELIABILITY", "EFFICIENCY"],
          measure_types: ["KPI"],
          units_of_measure: ["%", "hours"],
          measurement_frequencies: ["MONTHLY", "QUARTERLY"],
          measure_directions: ["INCREASE", "DECREASE"],
          owner_types: ["ORGANIZATIONAL_ROLE", "USER"],
          owner_acceptance_statuses: ["PENDING", "ACCEPTED"],
          benefit_directions: ["BENEFIT", "DISBENEFIT"],
        },
      });
      return;
    }
    if (method === "GET" && pathname === "/api/v1/strategic-benefits-plans") {
      await route.fulfill({
        status: 200,
        headers: { "X-Page-Limit": "50", "X-Result-Count": exists ? "1" : "0" },
        json: exists ? [planRecord()] : [],
      });
      return;
    }
    if (method === "POST" && pathname === "/api/v1/strategic-benefits-plans") {
      exists = true;
      mutations.push({
        action: "create-plan",
        idempotency: Boolean(headers["idempotency-key"]),
        payload: payload || undefined,
      });
      await route.fulfill({ status: 201, json: planRecord() });
      return;
    }
    if (method === "GET" && pathname.endsWith("/101/readiness")) {
      await route.fulfill({ status: 200, json: readinessRecord() });
      return;
    }
    if (method === "GET" && pathname.endsWith("/101/history")) {
      await route.fulfill({
        status: 200,
        json: [
          {
            version: versionRecord(),
            lifecycle_events: [{ event_type: "strategic_benefits_plan.created", occurred_at: "2026-09-17T10:00:00Z" }],
          },
        ],
      });
      return;
    }
    if (method === "GET" && pathname.endsWith("/101/traceability")) {
      const benefitRow = benefit || {};
      const measureRow = measure || {};
      await route.fulfill({
        status: 200,
        headers: { "X-Page-Limit": "50", "X-Result-Count": benefit ? "1" : "0" },
        json: benefit
          ? [
              {
                strategic_objectives: benefitRow.strategic_objective_refs,
                need_opportunity: benefitRow.source_need_reference,
                business_analysis: benefitRow.source_business_analysis_reference,
                recommended_option: { reference: "OPT-501" },
                project: { name: "North Interconnection" },
                business_case: benefitRow.source_business_case_reference,
                expected_outputs: benefitRow.expected_outputs,
                expected_outcomes: benefitRow.expected_outcomes,
                benefit_id: 301,
                benefit_number: "BEN-000301",
                benefit_name: benefitRow.benefit_name,
                measures: measure
                  ? [
                      {
                        code: measureRow.measure_code,
                        name: measureRow.measure_name,
                        baseline_status: measureRow.baseline_status,
                        baseline: measureRow.baseline_value,
                        target: measureRow.target_value,
                        target_date: measureRow.target_date,
                      },
                    ]
                  : [],
                owner: benefitRow.owner,
                target_dates: measure ? [String(measureRow.target_date)] : [],
                expected_value: benefitRow.expected_value,
                status: lifecycleStatus,
              },
            ]
          : [],
      });
      return;
    }
    if (method === "GET" && pathname.endsWith("/101")) {
      await route.fulfill({ status: 200, json: planRecord() });
      return;
    }
    if (method === "PUT" && pathname.endsWith("/101/versions/201")) {
      mutations.push({ action: "save-plan", ifMatch: headers["if-match"], payload: payload || undefined });
      planDraft = { ...planDraft, ...(payload || {}) };
      revisionVersion += 1;
      await route.fulfill({ status: 200, json: versionRecord() });
      return;
    }
    if (method === "POST" && pathname.endsWith("/101/versions/201/benefits")) {
      benefit = {
        ...(payload || {}),
        id: 301,
        benefit_number: "BEN-000301",
        identity_status: "ACTIVE",
        snapshot_id: 311,
        status: "ACTIVE",
        snapshot_hash: "benefit-snapshot-hash",
        revision_version: 1,
      };
      revisionVersion += 1;
      mutations.push({
        action: "add-benefit",
        idempotency: Boolean(headers["idempotency-key"]),
        ifMatch: headers["if-match"],
        payload: payload || undefined,
      });
      await route.fulfill({ status: 201, json: benefit });
      return;
    }
    if (method === "PUT" && pathname.endsWith("/101/versions/201/benefits/301")) {
      benefit = {
        ...(benefit || {}),
        ...(payload || {}),
        revision_version: Number(benefit?.revision_version || 1) + 1,
      };
      revisionVersion += 1;
      mutations.push({ action: "assign-owner", ifMatch: headers["if-match"], payload: payload || undefined });
      await route.fulfill({ status: 200, json: benefit });
      return;
    }
    if (method === "POST" && pathname.endsWith("/101/versions/201/benefits/301/measures")) {
      measure = {
        ...(payload || {}),
        id: 401,
        benefit_snapshot_id: 311,
        measure_hash: "measure-hash",
        created_at: "2026-09-17T10:05:00Z",
        updated_at: "2026-09-17T10:05:00Z",
        revision_version: 1,
      };
      revisionVersion += 1;
      mutations.push({
        action: "add-measure",
        idempotency: Boolean(headers["idempotency-key"]),
        ifMatch: headers["if-match"],
        payload: payload || undefined,
      });
      await route.fulfill({ status: 201, json: measure });
      return;
    }
    for (const [suffix, nextStatus, action] of [
      ["submit", "SUBMITTED", "submit"],
      ["start-review", "IN_REVIEW", "start-review"],
      ["complete", "COMPLETED", "complete"],
    ] as const) {
      if (method === "POST" && pathname.endsWith(`/101/versions/201/${suffix}`)) {
        mutations.push({
          action,
          idempotency: Boolean(headers["idempotency-key"]),
          ifMatch: headers["if-match"],
        });
        lifecycleStatus = nextStatus;
        revisionVersion += 1;
        await route.fulfill({ status: 200, json: versionRecord() });
        return;
      }
    }
    await route.fulfill({ status: 501, json: { detail: `Unmocked Benefits route ${method} ${pathname}` } });
  });

  await login(page);
  await page.goto("/app/strategy/strategic-benefits-my");
  const workspace = page.getByRole("region", { name: "Strategic Benefits Plan and Traceability" });
  await expect(workspace).toBeVisible();
  await workspace.getByLabel("Project Workspace ID").fill("501");
  await workspace.getByRole("button", { name: /Create Benefits Plan/ }).click();
  await expect(workspace.getByText("BPL-000101 · Version 1")).toBeVisible();

  await workspace.getByRole("button", { name: "Outputs", exact: true }).click();
  await workspace.getByLabel("Expected outputs").fill("New grid interconnection");
  await workspace.getByRole("button", { name: "Outcomes", exact: true }).click();
  await workspace.getByLabel("Expected outcomes").fill("Resilient regional supply");
  await workspace.getByRole("button", { name: /Save Plan/ }).click();
  await expect(workspace.getByRole("status")).toContainText("DRAFT saved under ETag control");

  await workspace.getByRole("button", { name: "Benefits Register", exact: true }).click();
  await workspace.getByLabel("Benefit name").fill("Improve service availability");
  await workspace
    .getByLabel("Benefit statement")
    .fill("Availability improves after the interconnection enters service");
  await workspace.getByLabel("Benefit description").fill("Reduce interruption hours for regional customers");
  await workspace.getByLabel("Benefit type").selectOption("OPERATIONAL");
  await workspace.getByLabel("Benefit category").selectOption("RELIABILITY");
  await workspace.getByLabel("Expected output links").fill("New grid interconnection");
  await workspace.getByLabel("Expected outcome links").fill("Resilient regional supply");
  await workspace.getByRole("button", { name: "Add Benefit", exact: true }).click();
  await expect(workspace.getByLabel("Stable Benefit identity")).toContainText("BEN-000301");

  await workspace.getByRole("button", { name: "Benefit Owners", exact: true }).click();
  await workspace.getByLabel("Owner reference").fill("OPS-DIRECTOR");
  await workspace.getByLabel("Owner type").selectOption("ORGANIZATIONAL_ROLE");
  await workspace.getByLabel("Accountability statement").fill("Own sustained service performance");
  await workspace.getByLabel("Owner acceptance status").selectOption("ACCEPTED");
  await workspace.getByRole("button", { name: "Save BEN-000301", exact: true }).click();
  await expect(workspace.getByRole("status")).toContainText("stable identity");

  await workspace.getByRole("button", { name: "Measures / KPIs", exact: true }).click();
  await workspace.getByLabel("Measure code").fill("KPI-AVAIL");
  await workspace.getByLabel("Measure name").fill("Service availability");
  await workspace.getByLabel("Definition").fill("Percentage of service availability in the measurement period");
  await workspace.getByLabel("Unit of measure").selectOption("%");
  await workspace.getByLabel("Baseline status").selectOption("KNOWN");
  await workspace.getByLabel("Baseline value").fill("97.2");
  await workspace.getByLabel("Baseline as-of date").fill("2026-06-30");
  await workspace.getByLabel("Baseline source").fill("Audited operations report");
  await workspace.getByLabel("Target value").fill("99.5");
  await workspace.getByLabel("Target date").fill("2028-12-31");
  await workspace.getByLabel("Target basis").fill("Approved reliability target");
  await workspace.getByLabel("Measurement method").fill("Monthly service records");
  await workspace.getByLabel("Measurement frequency").selectOption("MONTHLY");
  await workspace.getByRole("button", { name: "Add measure", exact: true }).click();
  await expect(workspace.getByRole("status")).toContainText("Measure added");

  await workspace.getByRole("button", { name: "Traceability", exact: true }).click();
  const traceability = workspace.getByRole("table");
  await expect(traceability).toContainText("BEN-000301");
  await expect(traceability).toContainText("New grid interconnection");
  await expect(traceability).toContainText("Resilient regional supply");
  await expect(traceability).toContainText("Service availability");
  await expect(traceability).toContainText("97.2");
  await expect(traceability).toContainText("99.5");
  await expect(traceability).toContainText("OPS-DIRECTOR");

  await workspace.getByRole("button", { name: "Readiness", exact: true }).click();
  await expect(workspace.getByText("Backend-owned Benefits Readiness")).toBeVisible();
  await expect(workspace.locator(".benefitsReadiness > div > article")).toHaveCount(12);
  await expect(workspace.getByText("traceability coverage")).toBeVisible();
  await workspace.getByRole("button", { name: "History", exact: true }).click();
  await expect(workspace.getByText("Version 1 · DRAFT")).toBeVisible();

  await workspace.getByRole("button", { name: "Submit", exact: true }).click();
  await expect(workspace.getByText("SUBMITTED", { exact: true }).first()).toBeVisible();
  await workspace.getByRole("button", { name: "Start review", exact: true }).click();
  await expect(workspace.getByText("IN_REVIEW", { exact: true }).first()).toBeVisible();
  await workspace.getByRole("button", { name: "Complete", exact: true }).click();
  await expect(workspace.getByText("COMPLETED", { exact: true }).first()).toBeVisible();
  await expect(workspace.getByRole("button", { name: /New revision/ })).toBeEnabled();

  expect(mutations.map(({ action }) => action)).toEqual([
    "create-plan",
    "save-plan",
    "add-benefit",
    "assign-owner",
    "add-measure",
    "submit",
    "start-review",
    "complete",
  ]);
  for (const action of ["create-plan", "add-benefit", "add-measure", "submit", "start-review", "complete"])
    expect(mutations.find((item) => item.action === action)?.idempotency).toBe(true);
  for (const action of [
    "save-plan",
    "add-benefit",
    "assign-owner",
    "add-measure",
    "submit",
    "start-review",
    "complete",
  ])
    expect(mutations.find((item) => item.action === action)?.ifMatch).toMatch(/^"\d+"$/);
  expect(mutations.find((item) => item.action === "save-plan")?.payload).toEqual(
    expect.objectContaining({
      outputs_json: [{ output_name: "New grid interconnection" }],
      outcomes_json: [{ outcome_name: "Resilient regional supply" }],
    })
  );
  expect(mutations.find((item) => item.action === "add-measure")?.payload).toEqual(
    expect.objectContaining({
      baseline_status: "KNOWN",
      baseline_value: "97.2",
      target_value: "99.5",
      target_date: "2028-12-31",
    })
  );
  await expect(workspace.getByRole("button", { name: /Publish|Archive|Clone/ })).toHaveCount(0);
});

test("07M-BEN ADMIN governs catalogs, rules, applicability, inheritance, numbering, SoD and revision lifecycle [contract-intercepted]", async ({
  page,
}) => {
  type JsonRecord = Record<string, unknown>;
  type Mutation = { action: string; ifMatch?: string; idempotency?: boolean };

  const baseContent: JsonRecord = {
    configuration_code: "BEN-CAPITAL",
    policy_description: "Capital Owner strategic Benefits policy",
    benefit_types: ["OPERATIONAL", "FINANCIAL"],
    benefit_categories: ["RELIABILITY"],
    measure_types: ["KPI"],
    units_of_measure: ["%"],
    measurement_frequencies: ["MONTHLY"],
    required_sections: ["BENEFITS_REGISTER", "MEASURES"],
    benefit_owner_requirements: { required: true, acceptance_required: true },
    baseline_requirements: { explicit_status_required: true, unknown_remains_null: true },
    target_requirements: { value_required: true, date_required: true },
    expected_value_rules: { description_required: true },
    required_fields: { benefit: ["benefit_name", "benefit_statement"] },
    readiness_rules: { required_dimensions: 12 },
    coverage_rules: { minimum_owner_coverage: 100, minimum_traceability_coverage: 100 },
    fel_gate_requirements: { FEL_2: ["OWNER", "MEASURE", "TARGET"] },
    project_type_overrides: [],
    enabled_by_governance_model: {
      CAPITAL_OWNER: true,
      CONTRACTOR_DELIVERY: false,
      DIRECT_INTERNAL: false,
      LEGACY_UNCLASSIFIED: false,
    },
    scope: { inherit_to_descendants: false },
    numbering: { plan_prefix: "BPL", benefit_prefix: "BEN", padding: 6 },
    separation_of_duties: { reviewer_must_differ_from_author: true },
  };
  let items: Array<JsonRecord> = [
    {
      id: 81,
      name: "Capital Owner Benefits Policy r1",
      description: "Published baseline",
      status: "PUBLISHED",
      revision: 1,
      version: 1,
      content_json: structuredClone(baseContent),
      configuration_hash: "published-hash",
    },
  ];
  let savedContent: JsonRecord | null = null;
  const mutations: Mutation[] = [];

  await page.route("**/api/v1/strategic-benefits-plans/admin/configurations**", async (route) => {
    const request = route.request();
    const method = request.method();
    const pathname = new URL(request.url()).pathname;
    const headers = request.headers();

    if (method === "GET" && pathname.endsWith("/admin/configurations")) {
      await route.fulfill({ status: 200, json: items });
      return;
    }
    if (method === "POST" && pathname.endsWith("/admin/configurations/effective-preview")) {
      mutations.push({ action: "preview" });
      await route.fulfill({
        status: 200,
        json: {
          persisted: false,
          configuration_id: 82,
          configuration_revision: 2,
          configuration_hash: "preview-hash",
          resolution_chain: ["TENANT", "ENTERPRISE", "BUSINESS_UNIT", "PORTFOLIO"],
          effective_content: request.postDataJSON(),
        },
      });
      return;
    }
    if (method === "POST" && pathname.endsWith("/admin/configurations/81/clone")) {
      mutations.push({
        action: "clone",
        ifMatch: headers["if-match"],
        idempotency: Boolean(headers["idempotency-key"]),
      });
      const draft = {
        ...items[0],
        id: 82,
        name: "Capital Owner Benefits Policy r2",
        description: "Controlled draft",
        status: "DRAFT",
        revision: 2,
        version: 1,
        content_json: structuredClone(baseContent),
        configuration_hash: "draft-hash",
      };
      items = [items[0], draft];
      await route.fulfill({ status: 201, json: draft });
      return;
    }
    if (method === "PUT" && pathname.endsWith("/admin/configurations/82")) {
      mutations.push({ action: "save", ifMatch: headers["if-match"] });
      const body = request.postDataJSON() as { content_json: JsonRecord };
      savedContent = structuredClone(body.content_json);
      items = items.map((item) =>
        item.id === 82 ? { ...item, version: 2, content_json: structuredClone(savedContent) } : item
      );
      await route.fulfill({ status: 200, json: items.find((item) => item.id === 82) });
      return;
    }
    if (method === "POST" && pathname.endsWith("/admin/configurations/82/publish")) {
      mutations.push({
        action: "publish",
        ifMatch: headers["if-match"],
        idempotency: Boolean(headers["idempotency-key"]),
      });
      items = items.map((item) =>
        item.id === 81
          ? { ...item, status: "ARCHIVED", version: 2 }
          : { ...item, status: "PUBLISHED", version: 3, configuration_hash: "published-r2-hash" }
      );
      await route.fulfill({ status: 200, json: items.find((item) => item.id === 82) });
      return;
    }
    if (method === "POST" && pathname.endsWith("/admin/configurations/82/archive")) {
      mutations.push({
        action: "archive",
        ifMatch: headers["if-match"],
        idempotency: Boolean(headers["idempotency-key"]),
      });
      items = items.map((item) => (item.id === 82 ? { ...item, status: "ARCHIVED", version: 4 } : item));
      await route.fulfill({ status: 200, json: items.find((item) => item.id === 82) });
      return;
    }
    await route.fulfill({ status: 501, json: { detail: `Unmocked Benefits ADMIN route ${method} ${pathname}` } });
  });

  await login(page);
  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  await page.goto("/app/admin/strategy/benefits-configuration");
  const admin = page.getByRole("region", { name: "Benefits Configuration" });
  await expect(admin).toBeVisible();
  await admin.getByRole("button", { name: "Clone", exact: true }).click();
  await expect(
    admin.getByRole("button", { name: /Capital Owner Benefits Policy r2.*Revision 2.*DRAFT/ })
  ).toBeVisible();
  await expect(admin.getByRole("button", { name: "Save draft", exact: true })).toBeEnabled();

  await admin.getByRole("button", { name: "Benefit Types", exact: true }).click();
  await admin.getByLabel("Benefit Types").fill("OPERATIONAL\nFINANCIAL\nREGULATORY");
  await admin.getByRole("button", { name: "Benefit Categories", exact: true }).click();
  await admin.getByLabel("Benefit Categories").fill("RELIABILITY\nEFFICIENCY");
  await admin.getByRole("button", { name: "KPI / Measure Types", exact: true }).click();
  await admin.getByLabel("KPI / Measure Types").fill("KPI\nMILESTONE");
  await admin.getByRole("button", { name: "Units of Measure", exact: true }).click();
  await admin.getByLabel("Units of Measure").fill("%\nhours\nUSD");

  for (const [section, value] of [
    ["Benefit Owner Requirements", { required: true, acceptance_required: true, accountability_statement: true }],
    ["Baseline Requirements", { explicit_status_required: true, unknown_remains_null: true, source_required: true }],
    ["Target Requirements", { value_required: true, date_required: true, basis_required: true }],
    ["Readiness Rules", { required_dimensions: 12, backend_owned: true }],
    ["Coverage Rules", { minimum_owner_coverage: 100, minimum_traceability_coverage: 100 }],
  ] as const) {
    await admin.getByRole("button", { name: section, exact: true }).click();
    await admin.getByLabel(section).fill(JSON.stringify(value, null, 2));
  }

  await admin.getByRole("button", { name: "Applicability", exact: true }).click();
  await expect(admin.getByRole("checkbox", { name: "CAPITAL_OWNER", exact: true })).toBeChecked();
  await admin.getByRole("checkbox", { name: "CONTRACTOR_DELIVERY", exact: true }).check();
  await admin.getByRole("button", { name: "Inheritance", exact: true }).click();
  await admin.getByRole("checkbox", { name: /Inherit published policy/ }).check();
  await admin.getByRole("button", { name: "Numbering", exact: true }).click();
  await admin.getByLabel("Plan prefix").fill("SBP");
  await admin.getByLabel("Benefit prefix").fill("BEN");
  await admin.getByLabel("Numbering padding").fill("7");
  await admin.getByRole("button", { name: "Review / SoD", exact: true }).click();
  await expect(admin.getByRole("checkbox", { name: /Author must differ/ })).toBeChecked();

  await admin.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(admin.getByRole("status")).toContainText("DRAFT saved under ETag control");
  await admin.getByRole("button", { name: "Preview", exact: true }).click();
  await admin.getByLabel("Project Workspace ID (optional)").fill("501");
  await admin.getByRole("button", { name: "Preview persisted=false", exact: true }).click();
  await expect(admin.getByRole("region", { name: "Benefits effective preview" })).toContainText("persisted=false");
  await expect(admin.getByRole("region", { name: "Benefits effective preview" })).toContainText("preview-hash");

  await admin.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(admin.getByRole("status")).toContainText("policy published");
  await expect(admin.getByRole("button", { name: "Archive", exact: true })).toBeEnabled();
  await admin.getByRole("button", { name: "Archive", exact: true }).click();
  await expect(admin.getByRole("status")).toContainText("policy archived");
  await expect(admin.getByText("ARCHIVED", { exact: true }).first()).toBeVisible();

  expect(savedContent).toEqual(
    expect.objectContaining({
      benefit_types: ["OPERATIONAL", "FINANCIAL", "REGULATORY"],
      benefit_categories: ["RELIABILITY", "EFFICIENCY"],
      measure_types: ["KPI", "MILESTONE"],
      units_of_measure: ["%", "hours", "USD"],
      benefit_owner_requirements: expect.objectContaining({ accountability_statement: true }),
      baseline_requirements: expect.objectContaining({ unknown_remains_null: true, source_required: true }),
      target_requirements: expect.objectContaining({ basis_required: true }),
      readiness_rules: { required_dimensions: 12, backend_owned: true },
      coverage_rules: { minimum_owner_coverage: 100, minimum_traceability_coverage: 100 },
      enabled_by_governance_model: expect.objectContaining({ CAPITAL_OWNER: true, CONTRACTOR_DELIVERY: true }),
      scope: { inherit_to_descendants: true },
      numbering: { plan_prefix: "SBP", benefit_prefix: "BEN", padding: 7 },
      separation_of_duties: { reviewer_must_differ_from_author: true },
    })
  );
  expect(mutations).toEqual([
    { action: "clone", ifMatch: '"1"', idempotency: true },
    { action: "save", ifMatch: '"1"' },
    { action: "preview" },
    { action: "publish", ifMatch: '"2"', idempotency: true },
    { action: "archive", ifMatch: '"3"', idempotency: true },
  ]);
  await expect(admin.getByRole("button", { name: /^Submit$/ })).toHaveCount(0);
  await expect(admin.getByRole("button", { name: /^Complete$/ })).toHaveCount(0);
  await expect(admin.getByRole("button", { name: /Create Benefits Plan|Add Benefit|Save measure/ })).toHaveCount(0);
});
