import { expect, type Locator, type Page, test } from "@playwright/test";
import path from "node:path";

const evidenceDir = path.resolve(process.cwd(), "../docs/validation/gate07a-ba");

test.use({ viewport: { width: 1440, height: 900 } });

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("User").fill("admin");
  await page.getByLabel("Password").fill("1234");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
}

async function expand(button: Locator) {
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
}

async function openUserBusinessAnalysis(page: Page) {
  const userNavigation = page.getByRole("navigation", { name: /validation focus|control flow/i });
  await expand(userNavigation.getByRole("button", { name: "Enterprise Strategy Manager", exact: true }));
  const userModules = userNavigation.getByRole("group", { name: "Módulos de Enterprise Strategy Manager" });
  await expand(userModules.getByRole("button", { name: "Idea & Demand", exact: true }));
  await userModules.getByRole("button", { name: "Business Analysis & Options", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/strategy\/business-analysis-options$/);
  return page.getByRole("region", { name: "Business Analysis and Options" });
}

async function openAdminBusinessAnalysis(page: Page) {
  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  const adminNavigation = page.getByRole("navigation", { name: "Admin mode navigation" });
  await expand(adminNavigation.getByRole("button", { name: "Enterprise Strategy Manager", exact: true }));
  const adminModules = adminNavigation.getByRole("group", { name: "Módulos de Enterprise Strategy Manager" });
  await expand(adminModules.getByRole("button", { name: "Idea & Demand Configuration", exact: true }));
  await adminModules.getByRole("button", { name: "Business Analysis Configuration", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/admin\/strategy\/business-analysis-configuration$/);
  return page.getByRole("region", { name: "Business Analysis Configuration" });
}

const analysisOptions = {
  number_preview: "BA-00071",
  eligible_ideas: [
    {
      id: 17,
      idea_number: "IDEA-00017",
      title: "Modernize asset operations",
      owning_workspace_id: 1,
      can_start: true,
      blockers: [],
      governance_model: "CAPITAL_OWNER",
      business_analysis_required: true,
    },
  ],
  analysis_types: [{ code: "NEED", label: "Need" }],
  business_drivers: [{ code: "RELIABILITY", label: "Reliability" }],
  strategic_objectives: [{ code: "GROWTH", label: "Sustainable growth" }],
  option_types: [
    { code: "DO_NOTHING", label: "Do nothing" },
    { code: "NEW_CAPABILITY", label: "New capability" },
  ],
  evaluation_criteria: [
    { code: "VALUE", label: "Expected value", weight: 60 },
    { code: "FEASIBILITY", label: "Feasibility", weight: 40 },
  ],
  stakeholder_categories: [{ code: "OWNER", label: "Owner" }],
  value_dimensions: [{ code: "OPERATIONAL", label: "Operational" }],
};

const governedContent = {
  analysis_type: "NEED",
  statement: "Improve governed asset performance",
  background: "The accepted Idea identified fragmented asset controls.",
  business_context: "Enterprise reliability program",
  urgency_timing: "Decision required in the current planning cycle",
  consequences_no_action: "Operational disruption and avoidable cost",
  business_drivers: [{ code: "RELIABILITY", label: "Reliability" }],
  strategic_alignment: [{ objective_code: "GROWTH", contribution: "Supports sustainable growth" }],
  stakeholders: [{ name: "Operations" }],
  current_state: { summary: "Fragmented controls" },
  desired_outcomes: { business_outcomes: "Trusted asset performance" },
  expected_value: [{ dimension: "OPERATIONAL", narrative: "Improved reliability" }],
  assumptions: [{ statement: "Source data remains available" }],
  constraints: [{ statement: "Maintain service continuity" }],
  business_requirements: [{ statement: "End-to-end decision traceability" }],
  options: [
    {
      id: "do-nothing",
      name: "Do nothing",
      option_type: "DO_NOTHING",
      description: "Retain current fragmented controls",
      scope_concept: "No change",
      expected_benefits: "Avoid immediate implementation effort",
      rough_cost_range: null,
      rough_timeline: null,
      major_risks: [],
      major_dependencies: [],
      feasibility_notes: "Immediately feasible",
      strategic_fit: "Low",
      evaluation: [
        { criterion_code: "VALUE", rating: 1, weight: 60 },
        { criterion_code: "FEASIBILITY", rating: 5, weight: 40 },
      ],
    },
    {
      id: "target",
      name: "Target capability",
      option_type: "NEW_CAPABILITY",
      description: "Implement governed asset controls",
      scope_concept: "Phased governed rollout",
      expected_benefits: "Improved reliability and traceability",
      rough_cost_range: null,
      rough_timeline: null,
      major_risks: [],
      major_dependencies: [],
      feasibility_notes: "Feasible with staged adoption",
      strategic_fit: "Strong",
      evaluation: [
        { criterion_code: "VALUE", rating: 5, weight: 60 },
        { criterion_code: "FEASIBILITY", rating: 4, weight: 40 },
      ],
    },
  ],
  recommended_option_id: "target",
  recommendation_rationale: "Best governed value with acceptable delivery risk",
  key_trade_offs: [{ statement: "Higher initial effort for stronger controls" }],
  conditions: [{ statement: "Approve phased rollout" }],
  unresolved_concerns: [],
};

function allowedActions(status: string) {
  if (status === "DRAFT" || status === "RETURNED") return ["edit", "submit"];
  if (status === "SUBMITTED") return ["start_review"];
  if (status === "IN_REVIEW") return ["return", "complete"];
  if (status === "COMPLETED") return ["create_project_proposal", "new_revision"];
  return [];
}

test("Gate 07A-BA navigation keeps USER transactions and ADMIN configuration separated", async ({ page }) => {
  const pageErrors: string[] = [];
  const serverErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 500) serverErrors.push(`${response.status()} ${response.url()}`);
  });
  await login(page);

  const userWorkspace = await openUserBusinessAnalysis(page);
  await expect(userWorkspace.getByRole("heading", { name: "Business Analysis & Options" })).toBeVisible();
  await expect(userWorkspace.getByRole("button", { name: /New Business Analysis/ })).toBeVisible();
  await expect(userWorkspace.getByText("Configuration revisions")).toHaveCount(0);
  await page.screenshot({ path: path.join(evidenceDir, "gate07a-ba-user-business-analysis.png") });

  const adminWorkspace = await openAdminBusinessAnalysis(page);
  await expect(adminWorkspace.getByRole("heading", { name: "Business Analysis Configuration" })).toBeVisible();
  await expect(adminWorkspace.getByRole("button", { name: "Preview persisted=false" })).toBeVisible();
  await expect(adminWorkspace.getByText(/ADMIN surface never creates, submits, reviews or completes/)).toBeVisible();
  await expect(adminWorkspace.getByRole("button", { name: /New Business Analysis/ })).toHaveCount(0);
  await page.screenshot({ path: path.join(evidenceDir, "gate07a-ba-admin-configuration.png") });

  expect(pageErrors).toEqual([]);
  expect(serverErrors).toEqual([]);
});

test("Gate 07A-BA USER lifecycle reaches READY_FOR_PROJECT_PROPOSAL through the UI [contract-intercepted]", async ({
  page,
}) => {
  let exists = false;
  let status = "DRAFT";
  let version = 1;
  let content = structuredClone(governedContent);
  const mutations: Array<{ action: string; ifMatch?: string; idempotency?: boolean }> = [];
  const history: Array<Record<string, unknown>> = [];

  const record = () => ({
    id: 71,
    analysis_number: "BA-00071",
    source_idea_id: 17,
    source_idea_number: "IDEA-00017",
    source_idea_title: "Modernize asset operations",
    source_idea_evaluation_id: 5,
    owning_workspace_id: 1,
    owning_workspace_name: "Enterprise",
    supersedes_analysis_id: null,
    status,
    title: "Business Analysis for Modernize asset operations",
    content,
    recommended_option_id: content.recommended_option_id,
    readiness: {},
    source_idea_hash: "source-hash",
    configuration_id: 9,
    configuration_revision: 2,
    configuration_hash: "configuration-hash",
    review: status === "IN_REVIEW" || status === "COMPLETED" ? { reviewer_user_id: 2 } : {},
    completion_hash: status === "COMPLETED" ? "completion-hash" : "",
    revision_version: version,
    created_by_user_id: 1,
    reviewer_user_id: status === "IN_REVIEW" || status === "COMPLETED" ? 2 : null,
    allowed_actions: allowedActions(status),
    created_at: "2026-09-10T10:00:00Z",
    updated_at: "2026-09-10T10:10:00Z",
    submitted_at: ["SUBMITTED", "IN_REVIEW", "COMPLETED"].includes(status) ? "2026-09-10T10:05:00Z" : null,
    review_started_at: ["IN_REVIEW", "COMPLETED"].includes(status) ? "2026-09-10T10:06:00Z" : null,
    completed_at: status === "COMPLETED" ? "2026-09-10T10:10:00Z" : null,
  });

  await page.route("**/api/v1/business-analyses**", async (route) => {
    const request = route.request();
    const method = request.method();
    const pathname = new URL(request.url()).pathname;
    const headers = request.headers();

    if (method === "GET" && pathname.endsWith("/options")) {
      await route.fulfill({ status: 200, json: analysisOptions });
      return;
    }
    if (method === "GET" && pathname === "/api/v1/business-analyses") {
      await route.fulfill({ status: 200, json: exists ? [record()] : [] });
      return;
    }
    if (method === "POST" && pathname === "/api/v1/business-analyses") {
      exists = true;
      history.push({ event_type: "business_analysis.created", occurred_at: "2026-09-10T10:00:00Z" });
      mutations.push({ action: "create", idempotency: Boolean(headers["idempotency-key"]) });
      await route.fulfill({ status: 201, json: record() });
      return;
    }
    if (method === "PUT" && pathname.endsWith("/71")) {
      mutations.push({ action: "update", ifMatch: headers["if-match"] });
      content = request.postDataJSON();
      version += 1;
      history.push({ event_type: "business_analysis.updated", occurred_at: "2026-09-10T10:02:00Z" });
      await route.fulfill({ status: 200, json: record() });
      return;
    }
    if (method === "POST" && pathname.endsWith("/71/submit")) {
      mutations.push({ action: "submit", ifMatch: headers["if-match"] });
      status = "SUBMITTED";
      version += 1;
      history.push({ event_type: "business_analysis.submitted", occurred_at: "2026-09-10T10:05:00Z" });
      await route.fulfill({ status: 200, json: record() });
      return;
    }
    if (method === "POST" && pathname.endsWith("/71/start-review")) {
      mutations.push({ action: "start-review", ifMatch: headers["if-match"] });
      status = "IN_REVIEW";
      version += 1;
      history.push({ event_type: "business_analysis.review_started", occurred_at: "2026-09-10T10:06:00Z" });
      await route.fulfill({ status: 200, json: record() });
      return;
    }
    if (method === "POST" && pathname.endsWith("/71/complete")) {
      mutations.push({ action: "complete", ifMatch: headers["if-match"] });
      status = "COMPLETED";
      version += 1;
      history.push({ event_type: "business_analysis.completed", occurred_at: "2026-09-10T10:10:00Z" });
      await route.fulfill({ status: 200, json: record() });
      return;
    }
    if (method === "GET" && pathname.endsWith("/71/readiness")) {
      const ready = status === "COMPLETED";
      await route.fulfill({
        status: 200,
        json: {
          business_analysis_id: 71,
          status: ready ? "READY" : "BLOCKED",
          ready,
          output: ready ? "READY_FOR_PROJECT_PROPOSAL" : null,
          blockers: ready ? [] : ["BUSINESS_ANALYSIS_NOT_COMPLETED"],
          warnings: [],
          source_idea_hash: "source-hash",
          current_source_idea_hash: "source-hash",
          configuration_hash: "configuration-hash",
          readiness_hash: ready ? "ready-hash" : "blocked-hash",
        },
      });
      return;
    }
    if (method === "GET" && pathname.endsWith("/71/history")) {
      await route.fulfill({ status: 200, json: history });
      return;
    }
    await route.fulfill({ status: 501, json: { detail: `Unmocked BA route ${method} ${pathname}` } });
  });

  await login(page);
  const workspace = await openUserBusinessAnalysis(page);
  await workspace.getByRole("button", { name: /New Business Analysis/ }).click();
  const createDrawer = page.getByRole("region", { name: "Start Business Analysis" });
  await expect(createDrawer.getByLabel("Eligible accepted Idea")).toHaveValue("17");
  await createDrawer.getByRole("button", { name: "Create draft" }).click();

  await expect(workspace.getByText("BA-00071", { exact: false }).first()).toBeVisible();
  await workspace.getByRole("button", { name: "Edit analysis" }).click();
  const editor = page.getByRole("form", { name: "Edit Business Analysis" });
  await editor.getByLabel("Statement").fill("Improve governed asset performance with traceable controls");
  await expect(editor.getByLabel("Recommended option")).toHaveValue("target");
  await editor.getByRole("button", { name: "Save governed draft" }).click();

  await workspace.getByRole("button", { name: "Submit", exact: true }).click();
  await expect(workspace.getByRole("button", { name: "Start review" })).toBeVisible();
  await workspace.getByRole("button", { name: "Start review" }).click();
  await expect(workspace.getByRole("button", { name: "Complete", exact: true })).toBeVisible();
  await workspace.getByRole("button", { name: "Complete", exact: true }).click();

  await expect(workspace.getByText("READY_FOR_PROJECT_PROPOSAL")).toBeVisible();
  await expect(workspace.getByRole("link", { name: /Open Project Proposal/ })).toHaveAttribute(
    "href",
    "/app/strategy/project-proposal"
  );
  await expect(workspace.getByRole("button", { name: "New material revision" })).toBeVisible();
  expect(mutations).toEqual([
    { action: "create", idempotency: true },
    { action: "update", ifMatch: '"1"' },
    { action: "submit", ifMatch: '"2"' },
    { action: "start-review", ifMatch: '"3"' },
    { action: "complete", ifMatch: '"4"' },
  ]);
});

test("Gate 07A-BA ADMIN configuration completes clone, edit, preview and publish [contract-intercepted]", async ({
  page,
}) => {
  const baseContent = {
    evaluation_matrix: {
      criteria: [
        { code: "VALUE", label: "Expected value", weight: 60 },
        { code: "FEASIBILITY", label: "Feasibility", weight: 40 },
      ],
    },
    required_fields: ["statement", "business_drivers", "options", "recommended_option_id"],
  };
  let items: Array<Record<string, unknown>> = [
    {
      id: 9,
      kind: "business_analysis_configuration",
      name: "Business Analysis Policy r1",
      description: "Published baseline",
      status: "published",
      revision: 1,
      version: 1,
      content_json: structuredClone(baseContent),
    },
  ];
  let savedContent: Record<string, unknown> | null = null;
  const mutations: Array<{ action: string; ifMatch?: string }> = [];

  await page.route("**/api/v1/business-analyses**", async (route) => {
    const request = route.request();
    const method = request.method();
    const pathname = new URL(request.url()).pathname;
    const headers = request.headers();

    if (method === "GET" && pathname.endsWith("/admin/configurations")) {
      await route.fulfill({ status: 200, json: items });
      return;
    }
    if (method === "POST" && pathname.endsWith("/admin/configurations/9/clone")) {
      mutations.push({ action: "clone", ifMatch: headers["if-match"] });
      const draft = {
        ...items[0],
        id: 10,
        name: "Business Analysis Policy r2",
        description: "Controlled draft revision",
        status: "draft",
        revision: 2,
        version: 1,
        content_json: structuredClone(baseContent),
      };
      items = [items[0], draft];
      await route.fulfill({ status: 201, json: draft });
      return;
    }
    if (method === "PUT" && pathname.endsWith("/admin/configurations/10")) {
      mutations.push({ action: "edit", ifMatch: headers["if-match"] });
      const body = request.postDataJSON() as { content_json: Record<string, unknown> };
      savedContent = body.content_json;
      items = items.map((item) =>
        item.id === 10 ? { ...item, version: 2, content_json: structuredClone(savedContent) } : item
      );
      await route.fulfill({ status: 200, json: items[1] });
      return;
    }
    if (method === "POST" && pathname.endsWith("/admin/configuration/preview")) {
      mutations.push({ action: "preview" });
      await route.fulfill({
        status: 200,
        json: {
          persisted: false,
          source: { id: 10, revision: 2, scope: "enterprise" },
          validation: { valid: true, blockers: [], warnings: [] },
          effective_content: savedContent,
        },
      });
      return;
    }
    if (method === "POST" && pathname.endsWith("/admin/configurations/10/publish")) {
      mutations.push({ action: "publish", ifMatch: headers["if-match"] });
      items = items.map((item) =>
        item.id === 9
          ? { ...item, status: "archived", version: 2 }
          : { ...item, status: "published", version: 3, content_json: structuredClone(savedContent) }
      );
      await route.fulfill({ status: 200, json: items[1] });
      return;
    }
    await route.fulfill({ status: 501, json: { detail: `Unmocked BA route ${method} ${pathname}` } });
  });

  await login(page);
  const workspace = await openAdminBusinessAnalysis(page);
  const publishedCard = workspace.locator(".baAdminGrid > article").filter({ hasText: "Business Analysis Policy r1" });
  await publishedCard.getByRole("button", { name: "Clone draft" }).click();

  const draftCard = workspace.locator(".baAdminGrid > article").filter({ hasText: "Business Analysis Policy r2" });
  await expect(draftCard.getByText("Revision 2")).toBeVisible();
  await draftCard.getByRole("button", { name: "Edit policy" }).click();
  const editor = page.getByRole("region", { name: "Edit Business Analysis configuration" });
  await editor.getByRole("button", { name: "Evaluation Matrix", exact: true }).click();
  await editor.getByLabel("Weight VALUE").fill("50");
  await editor.getByLabel("Weight FEASIBILITY").fill("30");
  await editor.getByRole("button", { name: "Add evaluation criterion" }).click();
  await editor.getByLabel("Criterion code 3").fill("RISK");
  await editor.getByLabel("Criterion label RISK").fill("Risk exposure");
  await editor.getByLabel("Weight RISK").fill("20");
  await editor.getByRole("button", { name: "Required Fields", exact: true }).click();
  await editor
    .getByLabel("Required Fields")
    .fill("statement\nbusiness_drivers\nstrategic_alignment\noptions\nrecommended_option_id\nrecommendation_rationale");
  await expect(editor.getByLabel("Advanced configuration JSON read only")).toHaveCount(1);
  await expect(editor.getByLabel("Governed configuration JSON")).toHaveCount(0);
  const updatedContent = {
    evaluation_matrix: {
      criteria: [
        { code: "VALUE", label: "Expected value", weight: 50 },
        { code: "FEASIBILITY", label: "Feasibility", weight: 30 },
        { code: "RISK", label: "Risk exposure", weight: 20 },
      ],
    },
    required_fields: [
      "statement",
      "business_drivers",
      "strategic_alignment",
      "options",
      "recommended_option_id",
      "recommendation_rationale",
    ],
  };
  await editor.getByRole("button", { name: "Save draft" }).click();

  await workspace.getByRole("button", { name: "Preview persisted=false" }).click();
  await expect(workspace.getByText("VALID", { exact: true })).toBeVisible();
  await expect(workspace.getByText(/Revision 2 · persisted false/)).toBeVisible();
  await draftCard.getByRole("button", { name: "Publish" }).click();
  await expect(draftCard.getByText("published", { exact: true })).toBeVisible();
  await expect(draftCard.getByRole("button", { name: "Publish" })).toHaveCount(0);

  expect(savedContent).toEqual(updatedContent);
  expect(mutations).toEqual([
    { action: "clone", ifMatch: '"1"' },
    { action: "edit", ifMatch: '"1"' },
    { action: "preview" },
    { action: "publish", ifMatch: '"2"' },
  ]);
  await expect(workspace.getByRole("button", { name: "Submit" })).toHaveCount(0);
  await expect(workspace.getByRole("button", { name: "Complete" })).toHaveCount(0);
});
