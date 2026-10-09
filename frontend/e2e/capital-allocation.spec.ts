import { expect, type APIResponse, type Browser, type Page, test } from "@playwright/test";

const apiUrl = process.env.E2E_API_URL || "http://localhost:8000";

type LoginBody = { access_token: string };
type Configuration = {
  id: number;
  name: string;
  description: string;
  status: string;
  version: number;
  content_json: Record<string, unknown>;
};
type AllocationOptions = {
  scope_workspaces: Array<{ id: number; name: string; type?: string; workspace_type_code?: string }>;
};
type Cycle = { id: number; revision_version: number };
type CapitalPlanningOptions = {
  strategic_objectives: Array<{ code: string; label: string }>;
  sponsors: Array<{ id: number; name: string; email?: string }>;
};
type Demand = { id: number; demand_number: string; revision_version: number };
type Role = { id: number; code: string };
type User = { id: number; email: string };
type Assignment = { subject_id: number; role_code: string; status: string };
type SecurityOverview = { users: User[]; roles: Role[]; assignments: Assignment[] };

async function apiJson<T>(response: APIResponse, expectedStatus = 200) {
  expect(response.status(), await response.text()).toBe(expectedStatus);
  return (await response.json()) as T;
}

async function login(page: Page, email = "admin") {
  await page.goto("/login");
  await page.getByLabel("User").fill(email);
  await page.getByLabel("Password").fill("1234");
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes("/api/v1/auth/login") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /sign in/i }).click();
  const response = await responsePromise;
  expect(response.ok(), await response.text()).toBe(true);
  const body = (await response.json()) as LoginBody;
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
  return body.access_token;
}

async function expand(page: Page, name: RegExp, navigationLabel: string) {
  const navigation = page.getByRole("navigation", { name: navigationLabel });
  const button = navigation.getByRole("button", { name }).first();
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
}

async function publishWave2AConfiguration(page: Page, token: string, suffix: string) {
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  const options = await apiJson<CapitalPlanningOptions>(
    await page.request.get(`${apiUrl}/api/v1/capital-planning/options`, { headers })
  );
  const objective = options.strategic_objectives[0];
  const sponsor = options.sponsors[0];
  expect(objective, "A governed Strategic Objective is required").toBeTruthy();
  expect(sponsor, "An active sponsor is required").toBeTruthy();
  const configurations = await apiJson<Configuration[]>(
    await page.request.get(`${apiUrl}/api/v1/capital-planning/admin/configurations`, { headers })
  );
  const published = configurations.find((item) => item.status.toLowerCase() === "published");
  expect(published, "A published Capital Planning configuration is required").toBeTruthy();
  const draft = await apiJson<Configuration>(
    await page.request.post(`${apiUrl}/api/v1/capital-planning/admin/configurations/${published!.id}/clone`, {
      headers: { ...headers, "If-Match": `"${published!.version}"` },
    })
  );
  const buckets = [
    { code: "sustaining", name: "Sustaining Capital", active: true, display_order: 1 },
    { code: "growth", name: "Growth Capital", active: true, display_order: 2 },
    { code: "compliance", name: "Compliance Capital", active: true, display_order: 3 },
    { code: "efficiency", name: "Efficiency Capital", active: true, display_order: 4 },
  ];
  const currentPolicy = (published!.content_json.allocation_policy ?? {}) as Record<string, unknown>;
  const themeCode = `wave2a-${suffix}`;
  const content = {
    ...published!.content_json,
    themes: [{ code: themeCode, label: `Wave 2A ${suffix}`, strategic_objective_codes: [objective.code] }],
    drivers: [{ code: "resilience", label: "Resilience" }],
    categories: [{ code: "strategic", label: "Strategic" }],
    planning_horizons: [{ code: "near-term", label: "Near term" }],
    urgency_levels: [{ code: "high", label: "High" }],
    uncertainty_levels: [{ code: "conceptual", label: "Conceptual" }],
    strategic_capital_buckets: buckets,
    allocation_basis_options: ["PERCENTAGE", "INDICATIVE_AMOUNT", "PERCENTAGE_AND_AMOUNT"],
    allocation_policy: {
      ...currentPolicy,
      scope_types: ["enterprise", "business-unit", "portfolio"],
      eligible_demand_statuses: ["SUBMITTED", "IN_REVIEW", "ENDORSED"],
      percentage_total_required: "100.0000",
      percentage_tolerance: "0.0001",
      allow_unallocated_reserve: false,
      unclassified_max_percentage: "0",
      block_endorsement_when_unclassified_exceeds_tolerance: true,
      classification_modes: ["MANUAL", "THEME_DERIVED", "RULE_DERIVED"],
      closed_cycle_allows_new_plan: false,
    },
  };
  const updated = await apiJson<Configuration>(
    await page.request.put(`${apiUrl}/api/v1/capital-planning/admin/configurations/${draft.id}`, {
      headers: { ...headers, "If-Match": `"${draft.version}"` },
      data: {
        name: `Wave 2A E2E ${suffix}`,
        description: "Browser release configuration for Strategic Capital Buckets and allocation.",
        content_json: content,
      },
    })
  );
  const configured = await apiJson<Configuration>(
    await page.request.post(`${apiUrl}/api/v1/capital-planning/admin/configurations/${updated.id}/publish`, {
      headers: {
        ...headers,
        "If-Match": `"${updated.version}"`,
        "Idempotency-Key": `wave2a-config-${suffix}`,
      },
    })
  );
  return {
    configurationName: configured.name,
    objectiveCode: objective.code,
    sponsorId: sponsor.id,
    themeCode,
  };
}

async function createOpenCycle(page: Page, token: string, suffix: string, themeCode: string) {
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  const options = await apiJson<AllocationOptions>(
    await page.request.get(`${apiUrl}/api/v1/capital-planning/allocation-options`, { headers })
  );
  const enterprise = options.scope_workspaces.find(
    (item) => (item.type ?? item.workspace_type_code ?? "").replace("_", "-").toLowerCase() === "enterprise"
  );
  expect(enterprise, "An authorized Enterprise Workspace is required").toBeTruthy();
  const cycle = await apiJson<Cycle>(
    await page.request.post(`${apiUrl}/api/v1/capital-planning/cycles`, {
      headers: { ...headers, "Idempotency-Key": `wave2a-cycle-${suffix}` },
      data: {
        name: `Wave 2A Cycle ${suffix}`,
        planning_horizon_start: "2031-01-01",
        planning_horizon_end: "2031-12-31",
        scope_workspace_id: enterprise!.id,
        responsible_organization_workspace_id: enterprise!.id,
        applicable_theme_codes: [themeCode],
        capital_basis_currency: "COP",
        description: "Browser release Cycle for governed strategic allocation.",
      },
    }),
    201
  );
  await apiJson<Cycle>(
    await page.request.post(`${apiUrl}/api/v1/capital-planning/cycles/${cycle.id}/open`, {
      headers: {
        ...headers,
        "If-Match": `"${cycle.revision_version}"`,
        "Idempotency-Key": `wave2a-open-${suffix}`,
      },
    })
  );
  return { cycleId: cycle.id, workspaceId: enterprise!.id };
}

async function createSubmittedDemand(
  page: Page,
  token: string,
  suffix: string,
  context: { cycleId: number; workspaceId: number },
  configured: { objectiveCode: string; sponsorId: number; themeCode: string },
  currency: "COP" | "USD"
) {
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  const demand = await apiJson<Demand>(
    await page.request.post(`${apiUrl}/api/v1/capital-planning/demands`, {
      headers: { ...headers, "Idempotency-Key": `wave2a-demand-${currency}-${suffix}` },
      data: {
        name: `Wave 2A ${currency} Demand ${suffix}`,
        description: "Governed browser demand for strategic allocation validation.",
        planning_cycle_id: context.cycleId,
        theme_codes: [configured.themeCode],
        strategic_objective_codes: [configured.objectiveCode],
        business_or_asset_need: `Validate ${currency} demand classification without silent FX normalization.`,
        strategic_driver: "resilience",
        demand_category: "strategic",
        urgency: "high",
        target_horizon: "near-term",
        sponsor_user_id: configured.sponsorId,
        owning_workspace_id: context.workspaceId,
        location_context: "Browser release context",
        indicative_capital_need: currency === "COP" ? "2500000" : "250000",
        currency_code: currency,
        uncertainty_level: "conceptual",
        assumptions: ["Governed source remains available."],
        constraints: ["No implicit currency conversion."],
        dependencies: ["Published Bucket configuration."],
      },
    }),
    201
  );
  return apiJson<Demand>(
    await page.request.post(`${apiUrl}/api/v1/capital-planning/demands/${demand.id}/submit`, {
      headers: {
        ...headers,
        "If-Match": `"${demand.revision_version}"`,
        "Idempotency-Key": `wave2a-demand-submit-${currency}-${suffix}`,
      },
    })
  );
}

async function grantAllocationGovernanceRoles(page: Page, adminToken: string) {
  const headers = { Authorization: `Bearer ${adminToken}`, "Content-Type": "application/json" };
  const overview = await apiJson<SecurityOverview>(
    await page.request.get(`${apiUrl}/api/v1/organization-security/overview`, { headers })
  );
  const governedAssignments = [
    { email: "ana.control@demo.local", roleCode: "capital_planning_allocation_reviewer" },
    { email: "camila.cost@demo.local", roleCode: "capital_planning_allocation_endorser" },
  ];
  for (const { email, roleCode } of governedAssignments) {
    const user = overview.users.find((item) => item.email === email);
    expect(user, `The seeded governance actor ${email} is required`).toBeTruthy();
    const role = overview.roles.find((item) => item.code === roleCode);
    expect(role, `Missing governed role ${roleCode}`).toBeTruthy();
    const assigned = overview.assignments.some(
      (item) => item.subject_id === user!.id && item.role_code === roleCode && item.status === "active"
    );
    if (!assigned) {
      await apiJson(
        await page.request.post(`${apiUrl}/api/v1/organization-security/assignments`, {
          headers,
          data: {
            subject_type: "user",
            subject_id: user!.id,
            role_id: role!.id,
            scope_type: "organization",
            scope_unit_id: null,
          },
        }),
        201
      );
    }
  }
}

async function openAllocationWorkspace(page: Page) {
  await expand(page, /^enterprise strategy manager$/i, "Control Flow");
  await expand(page, /^strategic capital planning & demand$/i, "Control Flow");
  await page
    .getByRole("navigation", { name: "Control Flow" })
    .getByRole("button", { name: /^strategic capital allocation$/i })
    .click();
  await expect(page).toHaveURL(/\/app\/strategy\/strategic-capital-allocation$/);
}

test.describe("Wave 2A Strategic Capital Allocation Chromium browser release", () => {
  test.setTimeout(300_000);

  test("keeps ADMIN Bucket configuration separate and creates a governed USER Allocation Plan", async ({
    browser,
    page,
  }) => {
    const suffix = `${Date.now()}`.slice(-8);
    const planName = `Wave 2A Allocation ${suffix}`;
    const token = await login(page);
    const configured = await publishWave2AConfiguration(page, token, suffix);
    const context = await createOpenCycle(page, token, suffix, configured.themeCode);
    const copDemand = await createSubmittedDemand(page, token, suffix, context, configured, "COP");
    const usdDemand = await createSubmittedDemand(page, token, suffix, context, configured, "USD");
    await grantAllocationGovernanceRoles(page, token);

    await openAllocationWorkspace(page);
    const userSurface = page.getByRole("region", { name: "Strategic Capital Allocation workspace" });
    await expect(userSurface.getByRole("heading", { name: "Strategic Capital Allocation", exact: true })).toBeVisible();
    await expect(userSurface).toContainText("does not rank Projects or approve Budget, Funding, resources or FID");
    await expect(userSurface.getByRole("button", { name: /Publish|Archive|Clone to DRAFT/i })).toHaveCount(0);

    await userSurface.getByRole("button", { name: "New Allocation Plan" }).click();
    const form = page.getByRole("form", { name: "New Strategic Capital Allocation Plan form" });
    await form.getByLabel("Plan name").fill(planName);
    await form.getByLabel("Planning Cycle").selectOption(String(context.cycleId));
    await form.getByLabel("Scope Workspace").selectOption(String(context.workspaceId));
    const createResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v1/capital-planning/allocation-plans") && response.request().method() === "POST"
    );
    await form.getByRole("button", { name: "Create governed DRAFT" }).click();
    expect((await createResponse).status()).toBe(201);
    await expect(userSurface.getByText(planName, { exact: true })).toBeVisible();

    const targets: Record<string, string> = {
      sustaining: "40",
      growth: "30",
      compliance: "20",
      efficiency: "10",
    };
    for (const [code, value] of Object.entries(targets)) {
      await userSurface.getByLabel(`${code} target percentage`).fill(value);
    }
    await expect(userSurface.getByText("Target total 100%", { exact: true })).toBeVisible();
    const saveResponse = page.waitForResponse(
      (response) =>
        /\/api\/v1\/capital-planning\/allocation-plans\/\d+\/lines$/.test(response.url()) &&
        response.request().method() === "PUT"
    );
    await userSurface.getByRole("button", { name: "Save target allocation" }).click();
    expect((await saveResponse).ok()).toBe(true);
    await expect(userSurface.getByRole("status")).toContainText("not approved Budget or Funding");

    await userSurface.getByRole("button", { name: "Classification", exact: true }).click();
    const classificationTable = userSurface.getByRole("table", { name: "Strategic Bucket classifications" });
    await classificationTable.getByLabel(`${copDemand.demand_number} primary Bucket`).selectOption("sustaining");
    await classificationTable.getByLabel(`${usdDemand.demand_number} primary Bucket`).selectOption("growth");
    await classificationTable
      .getByLabel(`${copDemand.demand_number} classification rationale`)
      .fill("Explicit governed COP primary Bucket.");
    await classificationTable
      .getByLabel(`${usdDemand.demand_number} classification rationale`)
      .fill("Explicit governed USD primary Bucket.");
    const classificationResponse = page.waitForResponse(
      (response) =>
        /\/api\/v1\/capital-planning\/allocation-plans\/\d+\/classifications$/.test(response.url()) &&
        response.request().method() === "PUT"
    );
    await userSurface.getByRole("button", { name: "Save primary classifications" }).click();
    expect((await classificationResponse).ok()).toBe(true);
    await userSurface.getByRole("button", { name: "Overview", exact: true }).click();
    await expect(userSurface.getByText(/remain grouped by currency/i)).toBeVisible();
    for (const view of [
      "Demand Position",
      "Portfolio Position",
      "Recommended Position",
      "Approved Position",
      "Variance",
    ]) {
      await userSurface.getByRole("button", { name: view, exact: true }).click();
      await expect(userSurface.getByRole("region", { name: view })).toBeVisible();
    }

    const submitResponse = page.waitForResponse(
      (response) =>
        /\/api\/v1\/capital-planning\/allocation-plans\/\d+\/submit$/.test(response.url()) &&
        response.request().method() === "POST"
    );
    await userSurface.getByRole("button", { name: "Submit plan" }).click();
    expect((await submitResponse).ok()).toBe(true);
    await expect(
      userSurface.getByRole("region", { name: "Selected Allocation Plan" }).getByText("SUBMITTED", { exact: true })
    ).toBeVisible();

    const reviewerContext = await (browser as Browser).newContext();
    const reviewerPage = await reviewerContext.newPage();
    await login(reviewerPage, "ana.control@demo.local");
    await openAllocationWorkspace(reviewerPage);
    const reviewerSurface = reviewerPage.getByRole("region", { name: "Strategic Capital Allocation workspace" });
    const planSelect = reviewerSurface.getByLabel("Allocation Plan", { exact: true });
    const planOption = planSelect.locator("option").filter({ hasText: planName });
    await planSelect.selectOption((await planOption.getAttribute("value"))!);
    const reviewResponse = reviewerPage.waitForResponse(
      (response) =>
        /\/api\/v1\/capital-planning\/allocation-plans\/\d+\/review\/start$/.test(response.url()) &&
        response.request().method() === "POST"
    );
    await reviewerSurface.getByRole("button", { name: "Start review" }).click();
    expect((await reviewResponse).ok()).toBe(true);

    await reviewerPage.reload();
    const refreshedReviewerSurface = reviewerPage.getByRole("region", {
      name: "Strategic Capital Allocation workspace",
    });
    const refreshedReviewerPlanSelect = refreshedReviewerSurface.getByLabel("Allocation Plan", { exact: true });
    const refreshedReviewerOption = refreshedReviewerPlanSelect.locator("option").filter({ hasText: planName });
    await refreshedReviewerPlanSelect.selectOption((await refreshedReviewerOption.getAttribute("value"))!);
    await expect(
      refreshedReviewerSurface
        .getByRole("region", { name: "Selected Allocation Plan" })
        .getByText("IN_REVIEW", { exact: true })
    ).toBeVisible();
    await reviewerContext.close();

    const endorserContext = await (browser as Browser).newContext();
    const endorserPage = await endorserContext.newPage();
    await login(endorserPage, "camila.cost@demo.local");
    await openAllocationWorkspace(endorserPage);
    let endorserSurface = endorserPage.getByRole("region", { name: "Strategic Capital Allocation workspace" });
    const endorserPlanSelect = endorserSurface.getByLabel("Allocation Plan", { exact: true });
    const endorserPlanOption = endorserPlanSelect.locator("option").filter({ hasText: planName });
    await endorserPlanSelect.selectOption((await endorserPlanOption.getAttribute("value"))!);
    const endorseResponse = endorserPage.waitForResponse(
      (response) =>
        /\/api\/v1\/capital-planning\/allocation-plans\/\d+\/endorse$/.test(response.url()) &&
        response.request().method() === "POST"
    );
    await endorserSurface.getByRole("button", { name: "Endorse strategic plan" }).click();
    expect((await endorseResponse).ok()).toBe(true);

    await endorserPage.reload();
    endorserSurface = endorserPage.getByRole("region", { name: "Strategic Capital Allocation workspace" });
    const endorsedPlanSelect = endorserSurface.getByLabel("Allocation Plan", { exact: true });
    const endorsedPlanOption = endorsedPlanSelect.locator("option").filter({ hasText: planName });
    await endorsedPlanSelect.selectOption((await endorsedPlanOption.getAttribute("value"))!);
    await expect(
      endorserSurface.getByRole("region", { name: "Selected Allocation Plan" }).getByText("ENDORSED", { exact: true })
    ).toBeVisible();
    await endorserSurface.getByRole("button", { name: "History" }).click();
    const history = endorserSurface.getByRole("region", { name: "Strategic Allocation history" });
    await expect(history).toContainText("Immutable audit and revision history");
    await expect(history).toContainText("capital_planning.allocation_plan.endorse");
    await endorserContext.close();

    await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
    await expect(page).toHaveURL(/\/app$/);
    await expand(page, /^enterprise strategy manager$/i, "Admin mode navigation");
    await expand(page, /^strategic capital planning & demand configuration$/i, "Admin mode navigation");
    await page
      .getByRole("navigation", { name: "Admin mode navigation" })
      .getByRole("button", { name: /^strategic capital buckets$/i })
      .click();
    await expect(page).toHaveURL(/\/app\/admin\/strategy\/strategic-capital-bucket-configuration$/);
    const adminSurface = page.getByRole("region", { name: "Strategic Capital Buckets configuration" });
    await expect(adminSurface.getByRole("heading", { name: "Strategic Capital Buckets", exact: true })).toBeVisible();
    await expect(adminSurface).toContainText("This surface never edits a live Allocation Plan");
    await expect(adminSurface.getByRole("button", { name: /New Allocation Plan|Submit plan|Endorse/i })).toHaveCount(0);
    for (const governedSection of [
      "Bucket Catalog",
      "Strategic Purpose",
      "Theme Mapping",
      "Strategic Objective Mapping",
      "Allocation Basis",
      "Min / Target / Max Rules",
      "Tolerance Rules",
      "Classification Policy",
      "Unclassified Policy",
      "Planning Cycle Applicability",
      "Portfolio Applicability",
      "Governance Model",
      "Project Type",
      "Inheritance",
      "Numbering",
      "Review / SoD",
    ]) {
      await expect(adminSurface.getByText(governedSection, { exact: true })).toBeVisible();
    }
    const workspaceCode = `workspace-${context.workspaceId}`;
    await adminSurface
      .getByLabel("Workspace context for effective inheritance preview")
      .fill(String(context.workspaceId));
    await adminSurface.getByRole("button", { name: "Preview effective configuration" }).click();
    await expect(adminSurface.getByText("persisted=false", { exact: true })).toBeVisible();

    const publishedCard = adminSurface
      .locator("article")
      .filter({ hasText: configured.configurationName })
      .filter({ hasText: /PUBLISHED/i })
      .first();
    await publishedCard.getByRole("button", { name: "Clone to DRAFT" }).click();
    const draftCard = adminSurface.locator("article").filter({ hasText: workspaceCode }).filter({ hasText: /DRAFT/i });
    await expect(draftCard).toBeVisible();
    await draftCard.getByRole("button", { name: "Publish" }).click();
    const workspacePublishedCard = adminSurface
      .locator("article")
      .filter({ hasText: workspaceCode })
      .filter({ hasText: /PUBLISHED/i });
    await expect(workspacePublishedCard).toBeVisible();
    await workspacePublishedCard.getByRole("button", { name: "Archive" }).click();
    await expect(
      adminSurface
        .locator("article")
        .filter({ hasText: workspaceCode })
        .filter({ hasText: /ARCHIVED/i })
    ).toBeVisible();
  });
});
