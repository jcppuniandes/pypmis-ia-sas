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

const requirement = (evidenceType: string, classification: "A" | "B" | "C", provider?: string) => ({
  requirement_key: evidenceType.toLowerCase().replace(/_/g, "-"),
  evidence_type: evidenceType,
  classification,
  required: classification !== "C",
  blocking: classification === "A",
  scope: ["PERMIT_READINESS", "BUSINESS_CASE_READINESS", "ECONOMIC_FINANCIAL_READINESS"].includes(evidenceType)
    ? "EACH_PROJECT"
    : "PROJECT_SET",
  provider_key: provider || null,
  provider_required: classification === "A",
  validity_period_days: classification === "C" ? null : 180,
  coverage_requirement: ["PERMIT_READINESS", "BUSINESS_CASE_READINESS", "ECONOMIC_FINANCIAL_READINESS"].includes(
    evidenceType
  )
    ? 100
    : null,
  allow_manual_reference: classification === "B",
  manual_validation_required: classification === "B",
  rationale: `Controlled ${evidenceType} evidence.`,
  order: 10,
});

const content = {
  policy_code: "PYP-INVESTMENT-EVIDENCE",
  policy_name: "Investment Decision Evidence Policy",
  applicable_governance_models: ["CAPITAL_OWNER"],
  gate_profiles: {
    "PYP-INV-SELECT": {
      allow_valid_with_conditions: true,
      requirements: [
        requirement("BUSINESS_CASE_READINESS", "A", "BUSINESS_CASE_READINESS_PROVIDER"),
        requirement("ECONOMIC_FINANCIAL_READINESS", "B", "ECONOMIC_FINANCIAL_READINESS_PROVIDER"),
        requirement("RISK_READINESS", "B"),
        requirement("LAND_ACCESS_READINESS", "C"),
      ],
    },
    "PYP-FFA": {
      allow_valid_with_conditions: false,
      requirements: [
        requirement("PORTFOLIO_RECOMMENDATION", "A", "GATE07I_PORTFOLIO_RECOMMENDATION"),
        requirement("RISK_READINESS", "A", "RISK_READINESS_PROVIDER"),
        requirement("BUSINESS_CASE_READINESS", "A", "BUSINESS_CASE_READINESS_PROVIDER"),
        requirement("ECONOMIC_FINANCIAL_READINESS", "A", "ECONOMIC_FINANCIAL_READINESS_PROVIDER"),
        requirement("PERMIT_READINESS", "B"),
        requirement("CONTRACTING_STRATEGY_READINESS", "B"),
        requirement("EXECUTION_PLAN_READINESS", "B"),
      ],
    },
  },
  project_type_overrides: [
    {
      gate_profile_code: "PYP-FFA",
      project_type_filter: ["MINING"],
      governance_model_filter: ["CAPITAL_OWNER"],
      evidence_type: "PERMIT_READINESS",
      classification: "A",
      required: true,
      blocking: true,
      provider_key: "PERMIT_READINESS_PROVIDER",
      provider_required: true,
      allow_manual_reference: false,
      manual_validation_required: false,
      rationale: "Mining FFA requires governed permit readiness.",
    },
  ],
  blocking_policy: { class_A_failure: "BLOCK" },
  validity_policy: { no_global_expiration: true },
  coverage_policy: { do_not_average_missing_projects: true },
};

test.describe("Gate 07J-EVID Investment Decision Evidence Policy browser", () => {
  test("ADMIN clone, preview, ETag recovery and publish preserve the FID boundary", async ({ page }) => {
    test.setTimeout(180_000);
    const browserErrors: string[] = [];
    const unexpectedResponses: string[] = [];
    page.on("pageerror", (error) => browserErrors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error" && !message.text().includes("status of 412")) browserErrors.push(message.text());
    });
    page.on("response", (response) => {
      if (
        response.url().includes("/api/v1/investment-evidence-policy") &&
        response.status() >= 400 &&
        response.status() !== 412
      ) {
        unexpectedResponses.push(`${response.status()} ${response.url()}`);
      }
    });
    let configurations = [
      {
        id: 701,
        tenant_id: 1,
        kind: "investment_evidence_policy",
        code: "pyp-investment-decision-evidence-policy",
        name: "Investment Decision Evidence Policy",
        description: "Published controlled policy",
        status: "published",
        revision: 1,
        version: 2,
        content_json: content,
        content_hash: "a".repeat(64),
      },
    ];
    const providers = [
      {
        provider_key: "GATE07I_PORTFOLIO_RECOMMENDATION",
        evidence_type: "PORTFOLIO_RECOMMENDATION",
        source_module: "PORTFOLIO_SCENARIO_CONVERGENCE",
        source_contract: "InvestmentGatePreparationContractOut",
        supports_portfolio_scope: true,
        supports_project_scope: false,
        supports_project_set_scope: true,
        supports_hash: true,
        supports_current_flag: true,
        supports_readiness: true,
        status: "AVAILABLE",
        availability: "AVAILABLE",
        contract_status: "VALID",
        last_validation: "2026-09-03T00:00:00Z",
        version: "1.0",
        notes: "Validated Gate 07I contract",
        contract_valid: true,
        contract_issues: [],
      },
      {
        provider_key: "RISK_READINESS_PROVIDER",
        evidence_type: "RISK_READINESS",
        source_module: "RESERVED",
        source_contract: "Not implemented",
        supports_portfolio_scope: true,
        supports_project_scope: true,
        supports_project_set_scope: true,
        supports_hash: false,
        supports_current_flag: false,
        supports_readiness: false,
        status: "UNAVAILABLE",
        availability: "UNAVAILABLE",
        contract_status: "INVALID",
        last_validation: null,
        version: "1.0",
        notes: "Provider required; engine outside this gate",
        contract_valid: false,
        contract_issues: ["PROVIDER_UNAVAILABLE"],
      },
      ...[
        ["BUSINESS_CASE_READINESS_PROVIDER", "BUSINESS_CASE_READINESS", "BUSINESS_CASE_MANAGER"],
        ["ECONOMIC_FINANCIAL_READINESS_PROVIDER", "ECONOMIC_FINANCIAL_READINESS", "ECONOMIC_FINANCIAL_MODEL"],
      ].map(([provider_key, evidence_type, source_module]) => ({
        provider_key,
        evidence_type,
        source_module,
        source_contract: "ProviderEvidenceOut",
        supports_portfolio_scope: false,
        supports_project_scope: true,
        supports_project_set_scope: true,
        supports_hash: true,
        supports_current_flag: true,
        supports_readiness: true,
        status: "AVAILABLE",
        availability: "AVAILABLE",
        contract_status: "VALID",
        last_validation: "2026-09-03T00:00:00Z",
        version: "1.0",
        notes: "Gate 07M governed provider",
        contract_valid: true,
        contract_issues: [],
      })),
    ];
    const gaps = [
      {
        evidence_type: "RISK_READINESS",
        gate_profile: "PYP-FFA",
        project_type: null,
        classification: "A",
        blocking: true,
        provider: "RISK_READINESS_PROVIDER",
        provider_status: "UNAVAILABLE",
        gap_status: "PROVIDER_MISSING",
        recommended_action: "BUILD_MISSING_GOVERNED_PROVIDER",
      },
    ];
    const decisionCriterionPolicy = {
      policy_code: "GATE07J-EVID-2",
      effective_from: "2026-09-20T00:00:00Z",
      controlled_operators: ["IS_READY", "GREATER_THAN_OR_EQUAL"],
      evidence_quality_states: ["HIGH", "ACCEPTABLE", "LOW", "NOT_AVAILABLE"],
      unsafe_expression_execution: false,
      formal_decision_authority: "GATE07K",
      portfolio_rank_authority: "PORTFOLIO",
      criteria_by_profile: {
        "PYP-FFA": [
          {
            criterion_code: "BC-MUST-01",
            criterion_name: "Business Case strategic case",
            criterion_type: "MUST_MEET",
            source_evidence_type: "BUSINESS_CASE_READINESS",
            source_field: "source_readiness_status",
            operator: "IS_READY",
            expected_state: "READY",
            required: true,
            blocking: true,
          },
        ],
      },
    };
    let usedDedicatedClone = false;
    let staleOnce = true;

    await page.route("**/api/v1/strategic-project-planning/portfolio-options", (route) =>
      route.fulfill({ json: [{ id: 71, name: "Capital Portfolio" }] })
    );
    await page.route("**/api/v1/investment-evidence-policy/overview", (route) =>
      route.fulfill({
        json: {
          configurations,
          providers,
          missing_providers: gaps,
          required_adr_decisions: [],
          allowed_actions: [],
          boundaries: ["NO_CLASS_A_TO_CLASS_B_FALLBACK", "NO_INVESTMENT_DECISION_OR_FID"],
        },
      })
    );
    await page.route("**/api/v1/investment-evidence-policy/configurations/701/clone-gate07j-evid2", async (route) => {
      usedDedicatedClone = true;
      const draft = {
        ...configurations[0],
        id: 702,
        revision: 2,
        version: 1,
        status: "draft",
        content_json: { ...content, decision_criterion_policy: decisionCriterionPolicy },
      };
      configurations = [draft, configurations[0]];
      await route.fulfill({ json: draft });
    });
    await page.route("**/api/v1/investment-evidence-policy/configurations/702/preview", (route) =>
      route.fulfill({
        json: {
          policy: { id: 702, revision: 2, hash: "b".repeat(64), status: "draft" },
          gate_profile_code: "PYP-FFA",
          portfolio_workspace_id: 71,
          project_contexts: [{ project_workspace_id: 101, project_type: "MINING", governance_model: "CAPITAL_OWNER" }],
          effective_matrix: content.gate_profiles["PYP-FFA"].requirements,
          provider_registry_snapshot: providers,
          current_evidence_status: [],
          missing_providers: gaps,
          available_provider_count: 1,
          missing_required_provider_count: 1,
          class_A_count: 2,
          class_B_count: 3,
          class_C_count: 0,
          blocking_missing_sources: ["RISK_READINESS"],
          warnings: [],
          blockers: ["SOURCE_PROVIDER_MISSING"],
          effective_classifications: {
            BUSINESS_CASE_READINESS: ["A"],
            ECONOMIC_FINANCIAL_READINESS: ["A"],
          },
          required_coverage: { BUSINESS_CASE_READINESS: 100, ECONOMIC_FINANCIAL_READINESS: 100 },
          source_availability: {
            BUSINESS_CASE_READINESS: "AVAILABLE",
            ECONOMIC_FINANCIAL_READINESS: "AVAILABLE",
          },
          source_readiness: {
            BUSINESS_CASE_READINESS: ["READY"],
            ECONOMIC_FINANCIAL_READINESS: ["READY"],
          },
          source_current: { BUSINESS_CASE_READINESS: [true], ECONOMIC_FINANCIAL_READINESS: [true] },
          decision_criterion_policy: decisionCriterionPolicy,
          decision_criteria: decisionCriterionPolicy.criteria_by_profile["PYP-FFA"],
          criterion_validation_issues: [],
          decision_criterion_taxonomy: [
            "READINESS_CHECK",
            "MUST_MEET",
            "DECISION_HURDLE",
            "PRIORITIZATION",
            "SUCCESS_CRITERION",
          ],
          controlled_operators: decisionCriterionPolicy.controlled_operators,
          evidence_quality_states: decisionCriterionPolicy.evidence_quality_states,
          would_gate07j_be_ready: false,
          would_be_ready_for_investment_gate: false,
          recommended_next_development: {
            next: "BUILD_MISSING_GOVERNED_PROVIDER",
            provider: "RISK_READINESS_PROVIDER",
          },
          can_design_investment_decision_gate: false,
          can_enter_fid: false,
          persisted: false,
          final_output: "READY_FOR_BUSINESS_CASE_AND_ECONOMIC_FINANCIAL_GATE_EVIDENCE",
        },
      })
    );
    await page.route("**/api/v1/investment-evidence-policy/configurations/702", async (route) => {
      if (route.request().method() !== "PUT") return route.fallback();
      if (staleOnce) {
        staleOnce = false;
        return route.fulfill({ status: 412, json: { detail: { code: "ETAG_MISMATCH" } } });
      }
      configurations[0] = { ...configurations[0], version: 2 };
      return route.fulfill({ json: configurations[0] });
    });
    await page.route("**/api/v1/investment-evidence-policy/configurations/702/publish", async (route) => {
      configurations[0] = { ...configurations[0], version: 3, status: "published", content_hash: "c".repeat(64) };
      await route.fulfill({ json: configurations[0] });
    });

    await login(page);
    await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
    await expect(page.getByRole("navigation", { name: "Admin mode navigation" })).toBeVisible();
    await expand(page, /^enterprise strategy manager$/i);
    await expand(page, /^investment governance$/i);
    await page
      .getByRole("group", { name: "Submódulos de Investment Governance" })
      .getByRole("button", { name: /^evidence & decision policy$/i })
      .click();
    const admin = page.getByRole("region", { name: "Evidence & Decision Policy" });
    await expect(admin.getByRole("heading", { name: "Evidence & Decision Policy" })).toBeVisible();

    await admin.getByRole("button", { name: "Clone Gate07J-EVID-2 DRAFT" }).click();
    await expect(admin.getByLabel("Policy revision")).toHaveValue("702");
    expect(usedDedicatedClone).toBe(true);
    await admin.getByRole("button", { name: "Evidence Policy" }).click();
    await expect(admin.getByText("A · Governed source required").first()).toBeVisible();
    await admin.getByRole("button", { name: "Decision Criteria" }).click();
    await expect(admin.getByRole("cell", { name: "MUST_MEET" })).toBeVisible();
    await expect(admin.getByText("BC-MUST-01")).toBeVisible();
    await admin.getByRole("button", { name: "Project Type Overrides" }).click();
    await expect(admin.getByRole("cell", { name: "MINING", exact: true })).toBeVisible();

    await admin.getByRole("button", { name: "Preview", exact: true }).first().click();
    await expect(admin.getByRole("status")).toContainText("persisted=false");
    await expect(admin.getByText("SOURCE_PROVIDER_MISSING")).toBeVisible();
    await expect(admin.getByText(/RISK_READINESS_PROVIDER/).last()).toBeVisible();
    await expect(admin.getByText("BUSINESS CASE READINESS", { exact: true }).first()).toBeVisible();
    await expect(admin.getByText("ECONOMIC FINANCIAL READINESS", { exact: true }).first()).toBeVisible();
    await expect(admin.getByRole("heading", { name: "false" })).toBeVisible();

    await admin.getByRole("button", { name: "Save" }).click();
    await expect(admin.getByRole("status")).toContainText("ETAG_MISMATCH");
    await admin.getByRole("button", { name: "Save" }).click();
    await expect(admin.getByRole("status")).toContainText("save completed");
    await admin
      .getByRole("group", { name: "Evidence policy actions" })
      .getByRole("button", { name: "Publish" })
      .click();
    await expect(admin.getByRole("status")).toContainText("publish completed");
    await expect(
      admin.getByRole("button", { name: /approve investment|enter fid|\bgo\b|\bhold\b|\bkill\b/i })
    ).toHaveCount(0);
    expect(browserErrors).toEqual([]);
    expect(unexpectedResponses).toEqual([]);
  });
});
