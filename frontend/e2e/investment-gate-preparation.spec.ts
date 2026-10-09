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

test.describe("Gate 07J Investment Gate Preparation browser", () => {
  test("USER package and ADMIN dry-run preserve decision and FID boundaries", async ({ page }) => {
    test.setTimeout(180_000);
    const readiness = {
      preparation_id: 801,
      status: "IN_PREPARATION",
      readiness_status: "BLOCKED",
      source_current: true,
      required_requirement_count: 5,
      valid_requirement_count: 4,
      required_project_count: 1,
      valid_project_count: 0,
      blocked_project_count: 1,
      coverage_percent: 0,
      category_summary: {},
      evidence_coverage: {
        BUSINESS_CASE_READINESS: { required: 1, valid: 1, coverage_percent: 100, status: "VALID" },
        ECONOMIC_FINANCIAL_READINESS: { required: 1, valid: 1, coverage_percent: 100, status: "VALID" },
      },
      evidence_readiness_status: "BLOCKED",
      business_evaluation_status: "READY",
      portfolio_context_status: "CONSTRAINED",
      decision_package_status: "NOT_READY_FOR_INVESTMENT_DECISION",
      criterion_evaluations: [],
      unresolved_mandatory_criteria: [],
      cross_source_consistency: [],
      success_criteria_candidates: [],
      criterion_policy: { policy_revision: 4 },
      warnings: [],
      blockers: ["MISSING_DEFINITION_READINESS"],
      investment_gate_preparation_ready: false,
      can_enter_investment_decision: false,
      can_enter_fid: false,
      final_output: "GATE07J_REWORK_REQUIRED",
    };
    const preparation = {
      id: 801,
      tenant_id: 1,
      portfolio_workspace_id: 71,
      preparation_number: "IGP-CAPITAL-0001",
      logical_code: "INVESTMENT-GATE-PREPARATION",
      revision: 1,
      name: "Investment selection evidence package",
      description: "Governed browser evidence",
      investment_gate_profile_id: 901,
      profile_code: "PYP-INV-SELECT",
      profile_revision: 1,
      profile_hash: "a".repeat(64),
      source_convergence_id: 201,
      source_convergence_revision: 1,
      source_recommendation_hash: "b".repeat(64),
      recommended_alternative_id: 301,
      recommended_project_set_hash: "c".repeat(64),
      status: "IN_PREPARATION",
      readiness_status: "BLOCKED",
      source_snapshot: { selected_project_ids: [33], project_contexts: [{ fel_stage: "FEL-2" }] },
      evidence_summary: {},
      criterion_policy_snapshot: { policy_revision: 4, policy_hash: "7".repeat(64) },
      criterion_evaluations: [
        {
          criterion_code: "BC-MUST-01",
          criterion_name: "Strategic case accepted",
          criterion_type: "MUST_MEET",
          source_reference: { evidence_type: "BUSINESS_CASE_READINESS" },
          source_value: "READY",
          operator: "IS_READY",
          threshold_or_expected_value: "READY",
          result: "SATISFIED",
          blocking: true,
          required: true,
          policy_revision: 4,
        },
        {
          criterion_code: "BEN-SUCCESS-01",
          criterion_name: "Reliability uplift",
          criterion_type: "SUCCESS_CRITERION",
          source_reference: { evidence_type: "BENEFITS_READINESS" },
          source_value: "12%",
          operator: "GREATER_THAN_OR_EQUAL",
          threshold_or_expected_value: "10%",
          result: "SATISFIED",
          blocking: false,
          required: false,
          policy_revision: 4,
        },
      ],
      portfolio_context_snapshot: {
        rank_authority: "PORTFOLIO",
        governed_rank: 2,
        resource_constrained: true,
      },
      success_criteria_candidates: [
        { criterion_code: "BEN-SUCCESS-01", criterion_name: "Reliability uplift", result: "SATISFIED" },
      ],
      conditions: [],
      warnings: [],
      blockers: ["MISSING_DEFINITION_READINESS"],
      preparation_source_hash: "d".repeat(64),
      preparation_hash: null,
      revision_version: 2,
      created_by: 1,
      created_at: "2026-08-26T12:00:00",
      updated_by: 1,
      updated_at: "2026-08-26T12:00:00",
      frozen_by: null,
      frozen_at: null,
      voided_at: null,
      evidence: [
        {
          id: 809,
          preparation_id: 801,
          requirement_key: "business-case-readiness",
          evidence_type: "BUSINESS_CASE_READINESS",
          classification: "A",
          blocking: true,
          provider_key: "BUSINESS_CASE_READINESS_PROVIDER",
          coverage_requirement: 100,
          scope_type: "EACH_PROJECT",
          scope_id: 33,
          evidence_revision: 1,
          evidence_origin: "GOVERNED_SOURCE",
          source_module: "BUSINESS_CASE_MANAGER",
          source_record_id: "22",
          source_hash: "f".repeat(64),
          scope_reference_hash: "c".repeat(64),
          status: "VALID",
          evidence_date: "2026-09-03T00:00:00Z",
          valid_until: null,
          issuer: null,
          owner: null,
          summary: "Governed Business Case BC-0033 revision 3; readiness READY.",
          evidence_refs: [{ business_case_number: "BC-0033", business_case_hash: "f".repeat(64) }],
          submitted_by: null,
          submitted_at: null,
          validated_by: null,
          validated_at: "2026-09-03T00:00:00Z",
          validation_note: null,
          warnings: [],
          blockers: [],
          source_current: true,
          source_readiness_status: "READY",
          evidence_quality: "HIGH",
          evidence_confidence: "HIGH",
          quality_origin: "PROVIDER",
          source_version: 3,
          as_of: "2026-09-03T00:00:00Z",
          resolution_status: "VALID",
          revision_version: 1,
        },
        {
          id: 810,
          preparation_id: 801,
          requirement_key: "economic-financial-readiness",
          evidence_type: "ECONOMIC_FINANCIAL_READINESS",
          classification: "B",
          blocking: false,
          provider_key: "ECONOMIC_FINANCIAL_READINESS_PROVIDER",
          coverage_requirement: 100,
          scope_type: "EACH_PROJECT",
          scope_id: 33,
          evidence_revision: 1,
          evidence_origin: "GOVERNED_SOURCE",
          source_module: "ECONOMIC_FINANCIAL_MODEL",
          source_record_id: "44",
          source_hash: "9".repeat(64),
          scope_reference_hash: "c".repeat(64),
          status: "VALID",
          evidence_date: "2026-09-03T00:00:00Z",
          valid_until: null,
          issuer: null,
          owner: null,
          summary: "Governed COMMERCIAL economic-financial model; funding reconciliation MATCHED.",
          evidence_refs: [{ model_version_id: 44, model_hash: "9".repeat(64) }],
          submitted_by: null,
          submitted_at: null,
          validated_by: null,
          validated_at: "2026-09-03T00:00:00Z",
          validation_note: null,
          warnings: [],
          blockers: [],
          source_current: true,
          source_readiness_status: "READY",
          evidence_quality: "ACCEPTABLE",
          evidence_confidence: "MEDIUM",
          quality_origin: "PROVIDER",
          source_version: 2,
          as_of: "2026-09-03T00:00:00Z",
          resolution_status: "VALID",
          revision_version: 1,
        },
        {
          id: 811,
          preparation_id: 801,
          requirement_key: "fel-stage-readiness",
          evidence_type: "FEL_STAGE_READINESS",
          classification: "A",
          blocking: true,
          provider_key: null,
          coverage_requirement: 100,
          scope_type: "EACH_PROJECT",
          scope_id: 33,
          evidence_revision: 1,
          evidence_origin: "MANUAL_REFERENCE",
          source_module: null,
          source_record_id: null,
          source_hash: null,
          scope_reference_hash: "c".repeat(64),
          status: "MISSING",
          evidence_date: null,
          valid_until: null,
          issuer: null,
          owner: null,
          summary: "Required evidence is not available from a governed source.",
          evidence_refs: [],
          submitted_by: null,
          submitted_at: null,
          validated_by: null,
          validated_at: null,
          validation_note: null,
          warnings: [],
          blockers: [],
          source_current: null,
          source_readiness_status: null,
          resolution_status: "MISSING",
          revision_version: 1,
        },
      ],
      readiness,
      allowed_actions: ["can_edit_preparation", "can_add_evidence", "can_clone_preparation"],
    };

    await page.route("**/api/v1/strategic-project-planning/portfolio-options", (route) =>
      route.fulfill({ json: [{ id: 71, name: "Capital Portfolio" }] })
    );
    await page.route("**/api/v1/portfolios/71/investment-gate-preparation", (route) =>
      route.fulfill({
        json: {
          portfolio_workspace_id: 71,
          governance_eligible: true,
          source_contract: { final_output: "READY_FOR_INVESTMENT_GATE_PREPARATION" },
          profiles: [{ id: 901, profile_code: "PYP-INV-SELECT", name: "Investment Selection Preparation" }],
          preparations: [preparation],
          boundaries: ["NO_INVESTMENT_DECISION", "CAN_ENTER_FID_IS_ALWAYS_FALSE"],
        },
      })
    );
    await page.route("**/api/v1/investment-gate-preparations/801/project-readiness", (route) =>
      route.fulfill({
        json: {
          preparation_id: 801,
          required_project_count: 1,
          valid_project_count: 0,
          blocked_project_count: 1,
          coverage_percent: 0,
          projects: [
            {
              project_id: 33,
              required_count: 1,
              valid_count: 0,
              missing_requirements: ["fel-stage-readiness"],
              status: "BLOCKED",
            },
          ],
        },
      })
    );
    await page.route("**/api/v1/investment-gate-preparation/admin/configurations", (route) =>
      route.fulfill({
        json: [
          {
            id: 901,
            name: "Investment Selection Preparation",
            description: "",
            status: "draft",
            revision: 1,
            version: 1,
            content_json: {
              profile_code: "PYP-INV-SELECT",
              gate_purpose: "INVESTMENT_SELECTION",
              applicable_governance_models: ["CAPITAL_OWNER"],
              required_FEL_stage: "FEL-2",
              project_coverage_threshold_percent: 100,
              requirements: [],
            },
            content_hash: "e".repeat(64),
          },
        ],
      })
    );
    await page.route("**/api/v1/investment-gate-preparation/admin/configurations/preview", (route) =>
      route.fulfill({ json: { persisted: false, publishable: true, validation_issues: [], blockers: [] } })
    );

    await login(page);
    await expand(page, /^enterprise strategy manager$/i);
    await expand(page, /^investment governance$/i);
    await page
      .getByRole("group", { name: "Submódulos de Investment Governance" })
      .getByRole("button", { name: /^investment gate preparation$/i })
      .click();
    const workspace = page.getByRole("region", { name: "Investment Gate Preparation", exact: true });
    await expect(workspace.getByText("GATE07J_REWORK_REQUIRED")).toBeVisible();
    await expect(workspace.getByText("can_enter_fid = false")).toBeVisible();
    await expect(workspace.getByRole("region", { name: "Gate evaluation stages" })).toContainText(
      "Business EvaluationREADY"
    );
    await workspace.getByRole("button", { name: "Gate Matrix" }).click();
    const matrix = workspace.getByRole("table", { name: "Gate evidence and decision criteria matrix" });
    await expect(matrix).toContainText("Evidence Class A");
    await expect(matrix).toContainText("MUST_MEET");
    await expect(matrix).toContainText("HIGH");
    await expect(matrix).toContainText("Confidence HIGH");
    await expect(matrix).toContainText("10%");
    await expect(workspace.getByRole("group", { name: "Decision criteria grouped by taxonomy" })).toContainText(
      "Success criteria candidates"
    );
    await expect(workspace.getByRole("region", { name: "Frozen Portfolio context" })).toContainText("PORTFOLIO");
    await workspace.getByRole("button", { name: "Evidence Package" }).click();
    await expect(workspace.getByText("fel-stage-readiness")).toBeVisible();
    await expect(workspace.getByText("Business Case Readiness", { exact: true })).toBeVisible();
    await expect(workspace.getByText("Economic / Financial Readiness", { exact: true })).toBeVisible();
    await workspace.getByText("View Business Case source").click();
    await expect(workspace.getByText("BUSINESS_CASE_READINESS_PROVIDER")).toBeVisible();
    await workspace.getByText("View Economic / Financial source").click();
    await expect(workspace.getByText("ECONOMIC_FINANCIAL_READINESS_PROVIDER")).toBeVisible();
    await workspace.getByRole("button", { name: "Project Readiness" }).click();
    await expect(workspace.getByText("Project #33")).toBeVisible();
    await expect(workspace.getByRole("button", { name: /approve investment|enter fid|go|hold|kill/i })).toHaveCount(0);

    await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
    await expect(page.getByRole("navigation", { name: "Admin mode navigation" })).toBeVisible();
    await expand(page, /^enterprise strategy manager$/i);
    await expand(page, /^investment governance$/i);
    await page
      .getByRole("group", { name: "Submódulos de Investment Governance" })
      .getByRole("button", { name: /^investment gate preparation$/i })
      .click();
    const admin = page.getByRole("region", { name: "Investment Gate Preparation Configuration" });
    await admin.getByRole("button", { name: "Preview" }).click();
    await expect(admin.getByText(/persisted=false; no preparation, decision or fid was created/i)).toBeVisible();
    await expect(admin.getByRole("button", { name: /approve investment|enter fid|go|hold|kill/i })).toHaveCount(0);
  });
});
