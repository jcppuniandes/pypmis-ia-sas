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

const configuration = {
  configuration_code: "PYP-RISK-READINESS",
  applicable_governance_models: ["CAPITAL_OWNER"],
  risk_categories: ["TECHNICAL", "COST", "PERMITTING", "HSE"],
  likelihood_scale: [1, 2, 3, 4, 5].map((value) => ({ value, label: `L${value}` })),
  impact_scale: [1, 2, 3, 4, 5].map((value) => ({ value, label: `I${value}` })),
  risk_matrix: Object.fromEntries(
    [1, 2, 3, 4, 5].flatMap((l) =>
      [1, 2, 3, 4, 5].map((i) => [
        `${l}x${i}`,
        l * i <= 4 ? "LOW" : l * i <= 9 ? "MODERATE" : l * i <= 16 ? "HIGH" : "CRITICAL",
      ])
    )
  ),
  rating_bands: ["LOW", "MODERATE", "HIGH", "CRITICAL"],
  owner_required_threshold: "HIGH",
  treatment_required_threshold: "HIGH",
  residual_assessment_threshold: "HIGH",
  acceptance_threshold: "HIGH",
  acceptance_authority: { HIGH: "EXECUTIVE_SPONSOR", CRITICAL: "INVESTMENT_COMMITTEE" },
  readiness_criteria: { no_unowned_high_critical: true },
  evidence_coverage_percent: 100,
  validity_days: 90,
  pyp_inv_select: { classification: "B", blocking: false, validity_days: 90 },
  pyp_ffa: { classification: "A", blocking: true, validity_days: 90 },
  inheritance: ["TENANT", "ENTERPRISE", "BUSINESS_UNIT", "PORTFOLIO"],
};

test("Gate 07J-RISK USER and ADMIN flows expose governed evidence without FID controls", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const readiness = {
    project_workspace_id: 101,
    assessment_id: 801,
    assessment_hash: "a".repeat(64),
    as_of_date: new Date().toISOString(),
    valid_until: new Date(Date.now() + 90 * 86_400_000).toISOString(),
    active_risk_count: 1,
    high_count: 0,
    critical_count: 0,
    unowned_high_critical_count: 0,
    untreated_high_critical_count: 0,
    overdue_treatment_count: 0,
    unaccepted_residual_count: 0,
    evidence_coverage: 100,
    warnings: [],
    blockers: [],
    readiness_status: "READY",
    risk_readiness_hash: "b".repeat(64),
    source_current: true,
    allowed_actions: {},
  };
  const risk = {
    id: 901,
    project_workspace_id: 101,
    risk_number: "RSK-00001",
    title: "Controlled technical interface",
    description: "Governed risk",
    risk_category: "TECHNICAL",
    status: "MONITORING",
    identified_date: "2026-08-30",
    risk_owner_id: 1,
    cause: "Interface uncertainty",
    event: "Interface mismatch",
    impact_description: "Limited rework",
    likelihood_before: 2,
    impact_before: 2,
    inherent_rating: "LOW",
    treatment_required: false,
    treatment_strategy: null,
    treatment_description: null,
    treatment_owner_id: null,
    target_treatment_date: null,
    treatment_status: null,
    likelihood_after: null,
    impact_after: null,
    residual_rating: null,
    residual_acceptance_required: false,
    accepted_by: null,
    accepted_at: null,
    acceptance_comment: null,
    acceptance_authority_level: null,
    due_date: null,
    source_reference: null,
    evidence_refs_json: [{ reference: "RISK-EVIDENCE-01" }],
    revision_version: 1,
  };
  let configurations = [
    {
      id: 701,
      name: "Risk Readiness Configuration",
      description: "Controlled policy",
      status: "draft",
      revision: 1,
      version: 1,
      content_json: configuration,
      content_hash: "c".repeat(64),
    },
  ];

  await page.route("**/api/v1/strategic-project-planning/portfolio-options", (route) =>
    route.fulfill({ json: [{ id: 71, name: "Capital Portfolio" }] })
  );
  await page.route("**/api/v1/portfolios/71/projects", (route) =>
    route.fulfill({ json: [{ project_workspace_id: 101, project_name: "Project Alpha" }] })
  );
  await page.route("**/api/v1/projects/101/risks", (route) => route.fulfill({ json: [risk] }));
  await page.route("**/api/v1/projects/101/risk-readiness-assessments", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/projects/101/risk-readiness", (route) => route.fulfill({ json: readiness }));
  await page.route("**/api/v1/portfolios/71/risk-readiness", (route) =>
    route.fulfill({
      json: {
        portfolio_workspace_id: 71,
        recommended_project_set_hash: "d".repeat(64),
        required_project_count: 1,
        valid_project_count: 1,
        blocked_project_count: 0,
        stale_project_count: 0,
        expired_project_count: 0,
        coverage_percent: 100,
        aggregate_high_count: 0,
        aggregate_critical_count: 0,
        aggregate_unaccepted_residual_count: 0,
        warnings: [],
        blockers: [],
        readiness_status: "READY",
        risk_readiness_hash: "e".repeat(64),
        project_readiness: [readiness],
      },
    })
  );
  await page.route("**/api/v1/risk-readiness/admin/configurations", (route) => route.fulfill({ json: configurations }));
  await page.route("**/api/v1/risk-readiness/admin/configurations/preview", (route) =>
    route.fulfill({
      json: {
        configuration: { id: 701, status: "draft" },
        gate_profile_code: "PYP-FFA",
        project_readiness: [readiness],
        portfolio_readiness: { readiness_status: "READY" },
        effective_policy: configuration,
        warnings: [],
        blockers: [],
        would_be_ready: true,
        gate07j_evidence_preview: { provider_key: "RISK_READINESS_PROVIDER" },
        persisted: false,
        can_enter_fid: false,
      },
    })
  );
  await page.route("**/api/v1/risk-readiness/admin/configurations/701", async (route) => {
    configurations = [{ ...configurations[0], version: 2 }];
    await route.fulfill({ json: configurations[0] });
  });
  await page.route("**/api/v1/risk-readiness/admin/configurations/701/publish", async (route) => {
    configurations = [{ ...configurations[0], version: 3, status: "published" }];
    await route.fulfill({ json: configurations[0] });
  });

  await login(page);
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^investment governance$/i);
  await page
    .getByRole("group", { name: "Submódulos de Investment Governance" })
    .getByRole("button", { name: "Project Risk Register" })
    .click();
  const user = page.getByRole("region", { name: "Risk Readiness", exact: true });
  await expect(user.getByRole("heading", { name: "Risk Readiness" })).toBeVisible();
  await expect(user.getByRole("columnheader", { name: "Inherent Rating" })).toBeVisible();
  await expect(user.getByRole("columnheader", { name: "Acceptance" })).toBeVisible();
  await expect(user.getByText("RSK-00001").first()).toBeVisible();

  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  await expand(page, /^enterprise strategy manager$/i);
  await page.getByRole("button", { name: /^risk readiness configuration$/i }).click();
  const admin = page.getByRole("region", { name: "Risk Readiness Configuration", exact: true });
  await expect(admin.getByRole("button", { name: "Risk Matrix" })).toBeVisible();
  await admin.getByRole("button", { name: "Gate Compatibility" }).click();
  await expect(admin.getByText("Class A · 90d · blocking")).toBeVisible();
  await admin.getByRole("button", { name: "Preview" }).click();
  await expect(admin.getByRole("status")).toContainText("persisted=false");
  await expect(
    admin.getByRole("button", { name: /^(approve investment|enter fid|go|hold|kill)$/i })
  ).toHaveCount(0);
  expect(errors).toEqual([]);
});
