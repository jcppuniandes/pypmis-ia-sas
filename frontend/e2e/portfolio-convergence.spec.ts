import { expect, type Page, test } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("User").fill("admin");
  await page.getByLabel("Password").fill("1234");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
}

async function expand(page: Page, name: RegExp) {
  const button = page.getByRole("button", { name });
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
}

test.describe("Gate 07I Portfolio Scenario Convergence browser", () => {
  test("USER recommendation and ADMIN dry-run preserve the FID boundary", async ({ page }) => {
    test.setTimeout(180_000);
    let version = 1;
    let status = "DRAFT";
    let alternatives: Array<Record<string, unknown>> = [];
    let recommendedAlternativeId: number | null = null;
    const convergence = () => ({
      id: 201,
      tenant_id: 1,
      portfolio_workspace_id: 71,
      logical_code: "PORTFOLIO-CONVERGENCE",
      convergence_revision: 1,
      name: "Executive scenario convergence",
      description: "Governed browser evidence",
      status,
      required_budget_branch: true,
      required_resource_branch: true,
      source_analysis_hash: "a".repeat(64),
      source_membership_set_hash: "b".repeat(64),
      source_evaluation_set_hash: "c".repeat(64),
      budget_planning_hash: "d".repeat(64),
      resource_planning_hash: "e".repeat(64),
      configuration_id: 501,
      configuration_revision: 1,
      configuration_hash: "f".repeat(64),
      convergence_source_hash: "0".repeat(64),
      source_current: true,
      recommended_alternative_id: recommendedAlternativeId,
      recommendation_reason: recommendedAlternativeId ? "Aligned governed recommendation for preparation." : null,
      conditions: [],
      risks_acknowledged: recommendedAlternativeId ? ["FID remains downstream"] : [],
      decision_support_summary: recommendedAlternativeId ? "Both branches remain aligned and feasible." : null,
      recommendation_hash: recommendedAlternativeId ? "9".repeat(64) : null,
      recommended_by: recommendedAlternativeId ? 1 : null,
      recommended_at: recommendedAlternativeId ? "2026-08-26T12:00:00" : null,
      warnings: [],
      blockers: [],
      revision_version: version,
      created_by: 1,
      created_at: "2026-08-26T10:00:00",
      updated_by: 1,
      updated_at: "2026-08-26T12:00:00",
      voided_at: null,
      alternatives,
      allowed_actions: status === "DRAFT" ? ["can_add_alternative", "can_submit_review"] : ["can_recommend"],
    });
    const overview = () => ({
      portfolio_workspace_id: 71,
      required_branches: { budget: true, resource: true },
      budget_contract: { budget_planning_hash: "d".repeat(64) },
      resource_contract: { resource_planning_hash: "e".repeat(64) },
      source_compatibility: { compatible: true, analysis_hash: "a".repeat(64), warnings: [], blockers: [] },
      candidate_budget_scenarios: [
        { id: 101, scenario_name: "Budget balanced" },
        { id: 103, scenario_name: "Budget accelerated" },
      ],
      candidate_resource_scenarios: [
        { id: 102, scenario_name: "Capacity balanced" },
        { id: 104, scenario_name: "Capacity accelerated" },
      ],
      convergences: version > 1 || alternatives.length || status !== "DRAFT" ? [convergence()] : [],
      readiness: {
        portfolio_workspace_id: 71,
        convergence_id: version > 1 ? 201 : null,
        convergence_revision: version > 1 ? 1 : null,
        status: status === "RECOMMENDED" ? "READY" : "BLOCKED",
        alternative_count: alternatives.length,
        recommended_alternative_id: recommendedAlternativeId,
        source_current: true,
        warnings: [],
        blockers: status === "RECOMMENDED" ? [] : ["FORMAL_PORTFOLIO_RECOMMENDATION_REQUIRED"],
        recommendation_hash: recommendedAlternativeId ? "9".repeat(64) : null,
        portfolio_recommendation_ready: status === "RECOMMENDED",
        can_enter_investment_gate_preparation: status === "RECOMMENDED",
        can_enter_fid: false,
        allowed_actions: [],
        final_output: status === "RECOMMENDED" ? "READY_FOR_INVESTMENT_GATE_PREPARATION" : "GATE07I_REWORK_REQUIRED",
      },
      boundaries: ["PORTFOLIO_RECOMMENDATION_IS_NOT_INVESTMENT_APPROVAL", "CAN_ENTER_FID_IS_ALWAYS_FALSE"],
    });

    await page.route("**/api/v1/strategic-project-planning/portfolio-options", (route) =>
      route.fulfill({ json: [{ id: 71, name: "Capital Portfolio" }] })
    );
    await page.route("**/api/v1/portfolios/71/scenario-convergence", (route) => route.fulfill({ json: overview() }));
    await page.route("**/api/v1/portfolios/71/scenario-convergences", async (route) => {
      version = 2;
      await route.fulfill({ json: convergence(), headers: { ETag: `"${version}"` } });
    });
    await page.route("**/api/v1/portfolio-scenario-convergences/201/alternatives", async (route) => {
      const data = route.request().postDataJSON() as Record<string, unknown>;
      version += 1;
      const id = 300 + alternatives.length + 1;
      alternatives = [
        ...alternatives,
        {
          id,
          convergence_id: 201,
          alternative_name: data.alternative_name,
          budget_scenario_id: data.budget_scenario_id,
          budget_scenario_hash: "1".repeat(64),
          resource_scenario_id: data.resource_scenario_id,
          resource_scenario_hash: "2".repeat(64),
          alignment_status: "ALIGNED",
          budget_feasibility: "BUDGET_FEASIBLE",
          resource_feasibility: "RESOURCE_FEASIBLE",
          feasibility_status: "FEASIBLE",
          selected_project_set_hash: "3".repeat(64),
          budget_summary: {},
          resource_summary: {},
          strategic_summary: { selected_project_ids: [11, 12] },
          risk_summary: {},
          project_matrix: [],
          forced_conflicts: [],
          warnings: [],
          blockers: [],
          alternative_hash: "4".repeat(64),
          revision_version: 1,
          created_by: 1,
          created_at: "2026-08-26T10:00:00",
          updated_at: "2026-08-26T10:00:00",
        },
      ];
      await route.fulfill({ json: convergence() });
    });
    await page.route("**/api/v1/portfolio-scenario-convergences/201/compare", (route) =>
      route.fulfill({
        json: {
          convergence_id: 201,
          alternatives: [],
          feasibility_matrix: alternatives.map((item) => ({
            alternative_id: item.id,
            alternative: item.alternative_name,
            budget: "BUDGET_FEASIBLE",
            resource: "RESOURCE_FEASIBLE",
            alignment: "ALIGNED",
            overall: "FEASIBLE",
          })),
          project_matrix: [{ project_workspace_id: 11, "301": { budget_included: true, resource_included: true } }],
          pairwise_delta: { projects_differing: [] },
          warnings: ["NO_OPTIMIZER_OR_INVESTMENT_APPROVAL"],
        },
      })
    );
    await page.route("**/api/v1/portfolio-scenario-convergences/201/submit-review", (route) => {
      status = "IN_REVIEW";
      version += 1;
      return route.fulfill({ json: convergence() });
    });
    await page.route("**/api/v1/portfolio-scenario-convergences/201/recommend", (route) => {
      status = "RECOMMENDED";
      recommendedAlternativeId = 301;
      version += 1;
      return route.fulfill({ json: convergence() });
    });
    await page.route("**/api/v1/portfolio-convergence/admin/configurations", (route) =>
      route.fulfill({
        json: [
          {
            id: 501,
            name: "Gate 07I Default",
            description: "",
            status: "draft",
            revision: 1,
            version: 1,
            content_json: {
              scope: { type: "tenant", workspace_id: null },
              required_budget_branch: true,
              required_resource_branch: true,
              require_identical_project_sets: true,
              forced_conflict_is_blocker: true,
              allow_conditional_recommendation: false,
              recommender_sod_required: false,
            },
            content_hash: "8".repeat(64),
          },
        ],
      })
    );
    await page.route("**/api/v1/portfolio-convergence/admin/configurations/preview", (route) =>
      route.fulfill({ json: { persisted: false, publishable: true, validation_issues: [] } })
    );

    await login(page);
    await expand(page, /^enterprise strategy manager$/i);
    await expand(page, /^portfolio manager$/i);
    await page.getByRole("button", { name: /^portfolio scenario convergence$/i }).click();
    const workspace = page.getByRole("region", { name: "Portfolio Scenario Convergence", exact: true });
    await expect(workspace.getByText("Gate 07G · Budget branch")).toBeVisible();
    await expect(workspace.getByText("Gate 07H · Resource branch")).toBeVisible();
    await workspace.getByRole("button", { name: /create governed convergence/i }).click();
    await workspace.getByRole("button", { name: "alternatives" }).click();
    await workspace.getByRole("button", { name: "Add alternative" }).click();
    await workspace.getByLabel("Name").fill("Aligned accelerated alternative");
    await workspace.getByLabel("Budget scenario").selectOption("103");
    await workspace.getByLabel("Resource scenario").selectOption("104");
    await workspace.getByRole("button", { name: "Add alternative" }).click();
    await workspace.getByRole("button", { name: /compare 2/i }).click();
    await expect(workspace.getByText("Alternative comparison")).toBeVisible();
    await workspace.getByRole("button", { name: "alternatives" }).click();
    await workspace.getByRole("button", { name: /submit for review/i }).click();
    await workspace.getByRole("button", { name: "recommendation" }).click();
    await workspace.getByLabel("Recommendation reason").fill("Aligned governed recommendation for preparation.");
    await workspace.getByLabel("Risks acknowledged").fill("FID remains downstream");
    await workspace.getByLabel("Decision-support summary").fill("Both branches remain aligned and feasible.");
    await workspace.getByRole("button", { name: /record formal recommendation/i }).click();
    await workspace.getByRole("button", { name: "overview" }).click();
    await expect(workspace.getByText("READY_FOR_INVESTMENT_GATE_PREPARATION")).toBeVisible();
    await expect(workspace.getByText("can_enter_fid = false")).toBeVisible();
    await expect(workspace.getByRole("button", { name: /approve investment|enter fid/i })).toHaveCount(0);

    await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
    await expand(page, /^enterprise strategy manager$/i);
    await page.getByRole("button", { name: /^portfolio scenario convergence configuration$/i }).click();
    const admin = page.getByRole("region", { name: "Portfolio Scenario Convergence Configuration" });
    await admin.getByRole("button", { name: "Preview" }).click();
    await expect(admin.getByText(/persisted=false; no convergence or recommendation was created/i)).toBeVisible();
    await expect(admin.getByRole("button", { name: /approve investment|fid/i })).toHaveCount(0);
  });
});
