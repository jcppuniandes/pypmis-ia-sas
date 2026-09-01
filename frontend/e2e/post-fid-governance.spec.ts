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

test("Gate 07L USER and ADMIN flows expose per-Project eligibility without lifecycle execution", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const activeProject = {
    id: 44,
    investment_decision_id: 77,
    project_workspace_id: 14,
    project_number: "PRJ-0014",
    project_name: "Active baseline Project",
    project_type: "CAPITAL",
    governance_model: "CAPITAL_OWNER",
    project_state: "ACTIVE",
    workspace_status: "active",
    initialization_state: "ACTIVATED",
    fid_current: true,
    eligibility_round: 1,
    snapshot_eligibility_status: "NO_REACTIVATION_REQUIRED",
    eligibility_status: "NO_REACTIVATION_REQUIRED",
    final_output: "NO_REACTIVATION_REQUIRED",
    warnings: [],
    blockers: [],
    post_fid_conditions: [],
    open_activation_blockers: 0,
    open_commitment_conditions_count: 0,
    can_initialize: false,
    can_activate: false,
    next_allowed_process: "POST_FID_GOVERNANCE_COMPLETE",
    allowed_actions: ["can_view_post_fid", "can_view_history"],
    fid_decision_hash: "d".repeat(64),
    decision_package_hash: "p".repeat(64),
    condition_snapshot_hash: "c".repeat(64),
    eligibility_hash: "e".repeat(64),
    source_current: true,
    stale: false,
    persisted: true,
    evaluated_at: "2026-09-01T12:00:00",
    evaluated_by: 1,
    revision_version: 1,
  };
  const initializationProject = {
    ...activeProject,
    id: 45,
    project_workspace_id: 15,
    project_number: "PRJ-0015",
    project_name: "FID Project pending initialization",
    project_state: "NOT_INITIALIZED",
    workspace_status: "pending",
    initialization_state: "NOT_STARTED",
    eligibility_status: "READY_FOR_PROJECT_WORKSPACE_INITIALIZATION",
    snapshot_eligibility_status: "READY_FOR_PROJECT_WORKSPACE_INITIALIZATION",
    final_output: "READY_FOR_PROJECT_WORKSPACE_INITIALIZATION",
    can_initialize: true,
    next_allowed_process: "READY_FOR_EXISTING_PROJECT_WORKSPACE_INITIALIZATION",
    allowed_actions: ["can_view_post_fid", "can_view_initialization_handoff"],
  };
  const activationProject = {
    ...activeProject,
    id: 46,
    project_workspace_id: 16,
    project_number: "PRJ-0016",
    project_name: "Initialized FID Project",
    project_state: "INITIALIZED_NOT_ACTIVE",
    workspace_status: "pending",
    initialization_state: "READY_FOR_ACTIVATION",
    eligibility_status: "READY_FOR_PROJECT_WORKSPACE_ACTIVATION",
    snapshot_eligibility_status: "READY_FOR_PROJECT_WORKSPACE_ACTIVATION",
    final_output: "READY_FOR_PROJECT_WORKSPACE_ACTIVATION",
    can_activate: true,
    next_allowed_process: "READY_FOR_EXISTING_PROJECT_WORKSPACE_ACTIVATION",
    allowed_actions: ["can_view_post_fid", "can_view_activation_handoff"],
  };
  const blockedProject = {
    ...activationProject,
    id: 47,
    project_workspace_id: 17,
    project_number: "PRJ-0017",
    project_name: "Blocked FID Project",
    eligibility_status: "POST_FID_PROJECT_GOVERNANCE_BLOCKED",
    snapshot_eligibility_status: "POST_FID_PROJECT_GOVERNANCE_BLOCKED",
    final_output: "POST_FID_PROJECT_GOVERNANCE_BLOCKED",
    blockers: ["OPEN_ACTIVATION_BLOCKER"],
    post_fid_conditions: [{ code: "FID-COND-01", type: "ACTIVATION_BLOCKER", status: "OPEN" }],
    open_activation_blockers: 1,
    can_activate: false,
    next_allowed_process: "POST_FID_GOVERNANCE_BLOCKED",
    allowed_actions: ["can_view_post_fid", "can_view_conditions", "can_view_history"],
  };
  const projects = [activeProject, initializationProject, activationProject, blockedProject];
  const decision = {
    investment_decision_id: 77,
    decision_number: "IDEC-00077",
    title: "Full Funds Authorization",
    gate_profile: "PYP-FFA",
    status: "DECIDED",
    outcome: "GO",
    is_fid: true,
    post_fid_handoff: "READY_FOR_POST_FID_PROJECT_GOVERNANCE",
    final_output: "NO_REACTIVATION_REQUIRED",
    project_count: projects.length,
    projects,
    next: "POST_FID_GOVERNANCE_COMPLETE",
  };
  const config = {
    id: 9,
    name: "Default Post-FID Project Governance",
    description: "Controlled policy",
    status: "draft",
    revision: 2,
    version: 1,
    content_hash: "f".repeat(64),
    content_json: {
      applicable_gate_profiles: ["PYP-FFA"],
      applicable_governance_models: ["CAPITAL_OWNER"],
      handoff_rules: {
        delegate_initialization: true,
        delegate_activation: true,
        automatic_initialization: false,
        automatic_activation: false,
      },
    },
  };
  await page.route("**/api/v1/post-fid-governance**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/admin/configurations")) return route.fulfill({ json: [config] });
    if (url.pathname.endsWith("/admin/configurations/preview")) {
      return route.fulfill({ json: { persisted: false, publishable: true, project_eligibility: projects } });
    }
    if (url.pathname.endsWith("/refresh/preview")) {
      return route.fulfill({ json: { investment_decision_id: 77, deltas: [], projects, persisted: false } });
    }
    if (url.pathname.endsWith("-handoff")) {
      return route.fulfill({
        json: {
          delegated_service: "ProjectWorkspaceInitializationService",
          delegated_endpoint: "/api/v1/project-workspaces/15/initialization/start",
        },
      });
    }
    return route.fulfill({ json: [decision] });
  });

  await login(page);
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^investment governance$/i);
  await page
    .getByRole("group", { name: "Submódulos de Investment Governance" })
    .getByRole("button", { name: "Project Eligibility Matrix" })
    .click();
  const user = page.getByRole("region", { name: "Post-FID Project Governance", exact: true });
  await expect(user.getByText("PRJ-0014")).toBeVisible();
  await expect(user.getByText("NO_REACTIVATION_REQUIRED")).toBeVisible();
  await expect(user.getByText("PRJ-0017")).toBeVisible();
  await expect(user.getByText("POST_FID_PROJECT_GOVERNANCE_BLOCKED")).toBeVisible();
  await expect(user.getByRole("button", { name: /initialize project|activate project|issue ntp/i })).toHaveCount(0);
  await user.getByRole("button", { name: "Initialization Handoff" }).click();
  await expect(user.getByText("PRJ-0015")).toBeVisible();
  await user.getByRole("button", { name: "Prepare delegated initialization contract" }).click();
  await expect(user.getByRole("status")).toContainText("ProjectWorkspaceInitializationService");
  await user.getByRole("button", { name: "Activation Handoff" }).click();
  await expect(user.getByText("PRJ-0016")).toBeVisible();
  await user.getByRole("button", { name: "Prepare delegated activation contract" }).click();
  await expect(user.getByRole("status")).toContainText("No lifecycle mutation executed by Gate 07L");
  await user.getByRole("button", { name: "Refresh preview" }).click();
  await expect(user.getByRole("status")).toContainText("persisted=false");

  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  await expand(page, /^enterprise strategy manager$/i);
  await page.getByRole("button", { name: /^post-fid project governance$/i }).click();
  const admin = page.getByRole("region", { name: "Post-FID Project Governance Configuration", exact: true });
  await expect(
    admin.getByRole("navigation", { name: "Post-FID configuration sections" }).getByRole("button")
  ).toHaveCount(14);
  await admin.getByRole("button", { name: "Dry-run" }).click();
  await expect(admin.getByRole("status")).toContainText("persisted=false");
  await expect(admin.getByRole("button", { name: /initialize project|activate project|issue ntp/i })).toHaveCount(0);
  expect(errors).toEqual([]);
});
