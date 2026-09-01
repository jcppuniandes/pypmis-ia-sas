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

function decisionFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: 77,
    decision_number: "IDEC-00001",
    investment_gate_preparation_id: 55,
    portfolio_workspace_id: 7,
    profile_code: "PYP-INV-SELECT",
    decision_round: 1,
    decision_scope_hash: "s".repeat(64),
    status: "READY_FOR_DECISION",
    outcome: null,
    title: "Investment selection",
    executive_summary: "Governed",
    rationale: "",
    conditions: [],
    hold_reason: null,
    recycle_target: null,
    source_preparation_hash: "p".repeat(64),
    source_package_hash: "k".repeat(64),
    source_profile_hash: "r".repeat(64),
    source_policy_hash: "e".repeat(64),
    decision_package_snapshot: { evidence_summary: { risk: "VALID" } },
    configuration_hash: "c".repeat(64),
    configuration_snapshot: {},
    authority_model: "SINGLE_DECISION_MAKER",
    authority: {},
    committee: {},
    quorum: {},
    voting_rule: { rule: "SIMPLE_MAJORITY" },
    checklist: [{ code: "package_reviewed", label: "Frozen package reviewed", blocking: true, acknowledged: true }],
    authorized_amount: null,
    authorized_currency: null,
    authorization_valid_until: null,
    decision_maker_user_id: 2,
    decided_at: null,
    decided_by: null,
    is_fid: false,
    full_funds_authorized: false,
    investment_authorized: false,
    can_activate_project: false,
    decision_hash: null,
    revision_version: 5,
    votes: [],
    readiness: {
      investment_decision_id: 77,
      readiness_status: "READY",
      source_current: true,
      package_frozen: true,
      exact_scope: true,
      checklist_complete: true,
      authority_valid: true,
      quorum_met: true,
      voting_rule_met: true,
      segregation_of_duties_valid: true,
      blockers: [],
      warnings: [],
      final_output: "READY_FOR_INVESTMENT_DECISION",
    },
    allowed_actions: ["can_view_decision", "can_decide"],
    authorization_output: {
      final_output: "INVESTMENT_DECISION_PENDING",
      is_fid: false,
      full_funds_authorized: false,
      can_activate_project: false,
      can_issue_ntp: false,
      can_execute: false,
    },
    ...overrides,
  };
}

test("Gate 07K USER and ADMIN browser flow preserves FID and downstream boundaries", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const decision = {
    id: 77,
    decision_number: "IDEC-00001",
    investment_gate_preparation_id: 55,
    portfolio_workspace_id: 7,
    profile_code: "PYP-INV-SELECT",
    decision_round: 1,
    decision_scope_hash: "s".repeat(64),
    status: "READY_FOR_DECISION",
    outcome: null,
    title: "Investment selection",
    executive_summary: "Governed",
    rationale: "",
    conditions: [],
    hold_reason: null,
    recycle_target: null,
    source_preparation_hash: "p".repeat(64),
    source_package_hash: "k".repeat(64),
    source_profile_hash: "r".repeat(64),
    source_policy_hash: "e".repeat(64),
    decision_package_snapshot: { evidence_summary: { risk: "VALID" } },
    configuration_hash: "c".repeat(64),
    configuration_snapshot: {},
    authority_model: "SINGLE_DECISION_MAKER",
    authority: {},
    committee: {},
    quorum: {},
    voting_rule: { rule: "SIMPLE_MAJORITY" },
    checklist: [{ code: "package_reviewed", label: "Frozen package reviewed", blocking: true, acknowledged: true }],
    authorized_amount: null,
    authorized_currency: null,
    authorization_valid_until: null,
    decision_maker_user_id: 2,
    decided_at: null,
    decided_by: null,
    is_fid: false,
    full_funds_authorized: false,
    investment_authorized: false,
    can_activate_project: false,
    decision_hash: null,
    revision_version: 5,
    votes: [],
    readiness: {
      investment_decision_id: 77,
      readiness_status: "READY",
      source_current: true,
      package_frozen: true,
      exact_scope: true,
      checklist_complete: true,
      authority_valid: true,
      quorum_met: true,
      voting_rule_met: true,
      segregation_of_duties_valid: true,
      blockers: [],
      warnings: [],
      final_output: "READY_FOR_INVESTMENT_DECISION",
    },
    allowed_actions: ["can_view_decision", "can_decide"],
    authorization_output: {
      final_output: "INVESTMENT_DECISION_PENDING",
      is_fid: false,
      full_funds_authorized: false,
      can_activate_project: false,
      can_issue_ntp: false,
      can_execute: false,
    },
  };
  const config = {
    id: 9,
    name: "Default Investment Decision / FID Governance",
    description: "Controlled policy",
    status: "draft",
    revision: 2,
    version: 1,
    content_hash: "c".repeat(64),
    content_json: {
      profiles: {
        "PYP-INV-SELECT": { go_is_fid: false },
        "PYP-FFA": { go_is_fid: true },
      },
      outcomes: ["GO", "HOLD", "RECYCLE", "KILL"],
      authorization_output: { can_activate_project: false },
    },
  };

  await page.route("**/api/v1/investment-decisions**", (route) => route.fulfill({ json: [decision] }));
  await page.route("**/api/v1/investment-gate-preparations", (route) =>
    route.fulfill({
      json: [
        {
          id: 55,
          preparation_number: "IGP-00001",
          name: "Frozen package",
          profile_code: "PYP-INV-SELECT",
          status: "FROZEN",
          readiness_status: "READY",
          preparation_hash: "p".repeat(64),
        },
      ],
    })
  );
  await page.route("**/api/v1/investment-decision/admin/configurations", (route) => route.fulfill({ json: [config] }));
  await page.route("**/api/v1/investment-decision/admin/configurations/preview", (route) =>
    route.fulfill({ json: { persisted: false, publishable: true } })
  );

  await login(page);
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^investment governance$/i);
  await page
    .getByRole("group", { name: "Submódulos de Investment Governance" })
    .getByRole("button", { name: "Decision Queue" })
    .click();
  const user = page.getByRole("region", { name: "Investment Decision / FID", exact: true });
  await expect(user.getByText("FID NO")).toBeVisible();
  await expect(user.getByText("Project activation NO")).toBeVisible();
  await user.getByRole("button", { name: "Authorization Output" }).click();
  await expect(user.getByText(/"can_activate_project": false/)).toBeVisible();
  await expect(user.getByRole("button", { name: /activate project|issue ntp|execute project/i })).toHaveCount(0);

  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  await expand(page, /^enterprise strategy manager$/i);
  await page.getByRole("button", { name: /^investment decision \/ fid governance$/i }).click();
  const admin = page.getByRole("region", { name: "Investment Decision / FID Governance", exact: true });
  await expect(
    admin.getByRole("navigation", { name: "Investment Decision configuration sections" }).getByRole("button")
  ).toHaveCount(20);
  await admin.getByRole("button", { name: "Dry-run" }).click();
  await expect(admin.getByRole("status")).toContainText("persisted=false");
  await expect(admin.getByRole("button", { name: /activate project|issue ntp|execute project/i })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("Gate 07K browser renders FID, alternate outcomes, quorum and stale evidence safely", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const ffa = decisionFixture({
    id: 80,
    decision_number: "IDEC-00080",
    profile_code: "PYP-FFA",
    status: "DECIDED",
    outcome: "GO",
    is_fid: true,
    full_funds_authorized: true,
    investment_authorized: true,
    authorization_output: {
      final_output: "FINAL_INVESTMENT_DECISION_GO",
      post_fid_handoff: "READY_FOR_POST_FID_PROJECT_GOVERNANCE",
      is_fid: true,
      can_activate_project: false,
      can_issue_ntp: false,
      can_execute: false,
    },
  });
  const held = decisionFixture({
    id: 81,
    decision_number: "IDEC-00081",
    status: "DECIDED",
    outcome: "HOLD",
    authorization_output: {
      final_output: "INVESTMENT_SELECTION_HELD",
      is_fid: false,
      can_activate_project: false,
    },
  });
  const committee = decisionFixture({
    id: 82,
    decision_number: "IDEC-00082",
    authority_model: "COMMITTEE",
    committee: { chair_user_id: 9, members: [{ user_id: 9, voting_right: true }] },
    quorum: { minimum_member_count: 2, chair_required: true },
    readiness: {
      investment_decision_id: 82,
      readiness_status: "BLOCKED",
      source_current: true,
      package_frozen: true,
      exact_scope: true,
      checklist_complete: true,
      authority_valid: true,
      quorum_met: false,
      voting_rule_met: false,
      segregation_of_duties_valid: true,
      blockers: ["QUORUM_NOT_MET", "VOTING_RULE_NOT_MET"],
      warnings: [],
      final_output: "INVESTMENT_DECISION_REWORK_REQUIRED",
    },
  });
  const stale = decisionFixture({
    id: 83,
    decision_number: "IDEC-00083",
    readiness: {
      investment_decision_id: 83,
      readiness_status: "STALE",
      source_current: false,
      package_frozen: true,
      exact_scope: true,
      checklist_complete: true,
      authority_valid: true,
      quorum_met: true,
      voting_rule_met: true,
      segregation_of_duties_valid: true,
      blockers: ["PACKAGE_HASH_MISMATCH"],
      warnings: [],
      final_output: "INVESTMENT_DECISION_REWORK_REQUIRED",
    },
  });

  await page.route("**/api/v1/investment-decisions**", (route) =>
    route.fulfill({ json: [ffa, held, committee, stale] })
  );
  await page.route("**/api/v1/investment-gate-preparations", (route) => route.fulfill({ json: [] }));
  await login(page);
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^investment governance$/i);
  await page
    .getByRole("group", { name: "Submódulos de Investment Governance" })
    .getByRole("button", { name: "Decision Queue" })
    .click();

  const user = page.getByRole("region", { name: "Investment Decision / FID", exact: true });
  await expect(user.getByText("FID YES")).toBeVisible();
  await expect(user.getByText("Project activation NO")).toBeVisible();

  await user.getByRole("button", { name: "Authorization Output" }).click();
  await expect(user.getByText(/FINAL_INVESTMENT_DECISION_GO/)).toBeVisible();
  await expect(user.getByText(/READY_FOR_POST_FID_PROJECT_GOVERNANCE/)).toBeVisible();
  const decisionSelect = user.locator(".decisionControls select").first();
  await decisionSelect.selectOption("81");
  await expect(user.getByText(/INVESTMENT_SELECTION_HELD/)).toBeVisible();

  await user.getByRole("button", { name: "Committee / Votes" }).click();
  await decisionSelect.selectOption("82");
  await expect(user.getByText("NOT MET")).toBeVisible();
  await expect(user.getByRole("button", { name: "Vote GO" })).toBeDisabled();

  await user.getByRole("button", { name: "Decision Queue" }).click();
  await decisionSelect.selectOption("83");
  await expect(user.getByText("STALE")).toBeVisible();
  await expect(user.getByRole("button", { name: /activate project|issue ntp|execute project/i })).toHaveCount(0);
  expect(errors).toEqual([]);
});
