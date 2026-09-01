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

const readiness = {
  project_workspace_id: 101,
  project_type_code: "MINING",
  permit_classification: "A",
  gate_profile: "PYP-FFA",
  assessment_id: 801,
  assessment_hash: "a".repeat(64),
  as_of_date: new Date().toISOString(),
  valid_until: new Date(Date.now() + 180 * 86_400_000).toISOString(),
  required_count: 1,
  approved_count: 0,
  conditional_count: 1,
  missing_count: 0,
  rejected_count: 0,
  suspended_count: 0,
  expired_count: 0,
  open_blocking_conditions: 0,
  evidence_coverage_percent: 100,
  warnings: [],
  blockers: [],
  readiness_status: "READY",
  permit_readiness_hash: "b".repeat(64),
  source_current: true,
  allowed_actions: {},
};

const configuration = {
  configuration_code: "PYP-PERMIT-READINESS",
  applicable_governance_models: ["CAPITAL_OWNER"],
  permit_types: [{ code: "ENVIRONMENTAL_LICENSE", name: "Environmental License", authority_type: "CONFIGURED" }],
  requirements: [
    {
      requirement_key: "MINING_ENVIRONMENTAL_LICENSE",
      permit_type_code: "ENVIRONMENTAL_LICENSE",
      applicable_project_types: ["MINING"],
      applicable_geographies: ["*"],
      applicable_gate_profiles: ["PYP-FFA"],
      blocking: true,
    },
  ],
  qualifying_statuses: { "PYP-FFA": ["APPROVED", "APPROVED_WITH_CONDITIONS"] },
  condition_policy: "BLOCK_ONLY_ON_BLOCKING_CONDITIONS",
  evidence_coverage_percent: 100,
  class_a_project_coverage_percent: 100,
  validity_days: 180,
  inheritance: ["TENANT", "ENTERPRISE", "BUSINESS_UNIT", "PORTFOLIO"],
  separation_of_duties: {},
};

test("Gate 07J-PERMIT USER and ADMIN flows expose governed evidence without regulatory or FID controls", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const permit = {
    id: 901,
    project_workspace_id: 101,
    permit_number: "PRM-00001",
    permit_type_code: "ENVIRONMENTAL_LICENSE",
    requirement_key: "MINING_ENVIRONMENTAL_LICENSE",
    title: "Environmental licence",
    issuing_authority: "Configured authority",
    jurisdiction: "CO-ANT",
    status: "APPROVED_WITH_CONDITIONS",
    application_reference: "APP-01",
    valid_until: "2027-08-31",
    permit_identifier: "AUTH-01",
    evidence_refs_json: [{ reference: "EVID-01" }],
    responsible_user_id: 1,
    next_action: "Monitor condition",
    target_date: "2026-09-30",
    revision_version: 1,
  };
  const configRecord = {
    id: 701,
    name: "Permit Readiness Configuration",
    description: "Controlled policy",
    status: "draft",
    revision: 1,
    version: 1,
    content_json: configuration,
    content_hash: "c".repeat(64),
  };

  await page.route("**/api/v1/strategic-project-planning/portfolio-options", (route) =>
    route.fulfill({ json: [{ id: 71, name: "Capital Portfolio" }] })
  );
  await page.route("**/api/v1/portfolios/71/projects", (route) =>
    route.fulfill({ json: [{ project_workspace_id: 101, project_name: "Mine Expansion" }] })
  );
  await page.route("**/api/v1/projects/101/permits", (route) => route.fulfill({ json: [permit] }));
  await page.route("**/api/v1/permits/901/conditions", (route) =>
    route.fulfill({
      json: [
        {
          id: 811,
          permit_id: 901,
          condition_key: "MONITORING_REPORT",
          description: "Periodic report",
          condition_type: "MONITORING",
          blocking: false,
          owner_id: 1,
          target_date: "2026-09-30",
          status: "OPEN",
          evidence_refs_json: [],
          revision_version: 1,
        },
      ],
    })
  );
  await page.route("**/api/v1/projects/101/permit-readiness-assessments", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/projects/101/permit-readiness?**", (route) => route.fulfill({ json: readiness }));
  await page.route("**/api/v1/portfolios/71/permit-readiness?**", (route) =>
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
        aggregate_required_permit_count: 1,
        aggregate_approved_count: 0,
        aggregate_conditional_count: 1,
        aggregate_missing_count: 0,
        aggregate_rejected_count: 0,
        aggregate_suspended_count: 0,
        aggregate_expired_count: 0,
        aggregate_blocking_condition_count: 0,
        warnings: [],
        blockers: [],
        readiness_status: "READY",
        permit_readiness_hash: "e".repeat(64),
        project_readiness: [readiness],
      },
    })
  );
  await page.route("**/api/v1/permit-readiness/admin/configurations", (route) =>
    route.fulfill({ json: [configRecord] })
  );
  await page.route("**/api/v1/permit-readiness/admin/configurations/preview", (route) =>
    route.fulfill({
      json: { persisted: false, can_enter_fid: false, gate07j_evidence: { provider_key: "PERMIT_READINESS_PROVIDER" } },
    })
  );

  await login(page);
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^investment governance$/i);
  await page
    .getByRole("group", { name: "Submódulos de Investment Governance" })
    .getByRole("button", { name: "Project Permit Register" })
    .click();
  const user = page.getByRole("region", { name: "Permit Readiness", exact: true });
  await expect(user.getByRole("heading", { name: "Permit Readiness" })).toBeVisible();
  await expect(user.getByRole("columnheader", { name: "Type / requirement" })).toBeVisible();
  await expect(user.getByText("PRM-00001")).toBeVisible();

  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  await expand(page, /^enterprise strategy manager$/i);
  await page.getByRole("button", { name: /^permit readiness configuration$/i }).click();
  const admin = page.getByRole("region", { name: "Permit Readiness Configuration", exact: true });
  await expect(admin.getByRole("button", { name: "Provider Contract" })).toBeVisible();
  await admin.getByRole("button", { name: "Provider Contract" }).click();
  await expect(admin.getByText("AVAILABLE")).toBeVisible();
  await admin.getByRole("button", { name: "Dry-run" }).click();
  await expect(admin.getByRole("status")).toContainText("persisted=false");
  await expect(
    admin.getByRole("button", { name: /^(file with authority|approve investment|enter fid)$/i })
  ).toHaveCount(0);
  expect(errors).toEqual([]);
});
