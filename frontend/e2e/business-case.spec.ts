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

test("Gate 07M-BC-5C USER and ADMIN expose Five Case synthesis without duplicating sources", async ({ page }) => {
  const revision = {
    id: 11,
    business_case_id: 7,
    revision_number: 1,
    revision_label: "R1",
    purpose: "INITIAL_PROPOSAL",
    status: "COMPLETED",
    as_of_date: "2026-09-02T12:00:00",
    fel_stage_code: "FEL2",
    title: "Regional interconnection",
    executive_summary: "Governed case",
    business_need: "Improve reliability",
    strategic_alignment_json: [{ code: "STR-01" }],
    objectives_json: [{ description: "Improve reliability" }],
    scope_json: { in_scope: "Connection" },
    alternatives_json: [],
    benefits_json: [{ description: "Reduced outages" }],
    assumptions_json: [],
    constraints_json: [],
    delivery_json: { currency: "USD" },
    unresolved_concerns_json: [],
    recommendation_json: { status: "PREPARED", is_decision: false },
    five_case_json: {
      strategic_case: {
        question: "Why should the organization intervene?",
        summary: "The current need aligns with the governed strategic objective.",
        key_findings: [{ code: "STR-01" }],
        assumptions: [],
        warnings: [],
        blockers: [],
        case_conclusion: "Strategically justified",
        case_readiness: "READY",
      },
      economic_case: {
        summary: "The preferred option is referenced from Business Analysis.",
        case_readiness: "READY",
      },
      commercial_case: {
        summary: "The governed Commercial Strategy is referenced read-only.",
        case_readiness: "READY",
      },
      financial_case: {
        summary: "The governed FIN model remains the metric authority.",
        case_readiness: "READY",
      },
      management_case: {
        summary: "FEL, resources, risk and permit evidence support deliverability.",
        warnings: ["OWNER_CAPABILITY_NOT_AVAILABLE"],
        case_readiness: "READY",
      },
    },
    five_case_readiness_json: {
      strategic_case: "READY",
      economic_case: "READY",
      commercial_case: "READY",
      financial_case: "READY",
      management_case: "READY",
      overall_business_case_readiness: "READY",
    },
    source_evidence_matrix_json: [
      {
        case: "strategic_case",
        source_module: "PROJECT_PROPOSAL",
        source_id: 3,
        source_version_id: 1,
        source_hash: "a".repeat(64),
        source_status: "READY",
        source_readiness: "READY",
        source_current: true,
        as_of_date: "2026-09-02T12:00:00",
        blocking: true,
      },
      {
        case: "commercial_case",
        source_module: "COMMERCIAL_CONTRACTING_STRATEGY",
        source_id: 8,
        source_version_id: 2,
        source_hash: "9".repeat(64),
        source_status: "COMPLETED",
        source_readiness: "READY",
        source_current: true,
        as_of_date: "2026-09-02T12:00:00",
        blocking: true,
      },
    ],
    gate_context_json: { gate_profile: "PYP-FFA", governance_model: "CAPITAL_OWNER" },
    source_current: true,
    five_case_hash: "1".repeat(64),
    source_bundle_hash: "2".repeat(64),
    business_case_hash: "3".repeat(64),
    legacy_layout: false,
    source_references_json: { proposal: { id: 3, status: "READY" } },
    source_hashes_json: { proposal: "a".repeat(64) },
    source_snapshot_hash: "b".repeat(64),
    economic_financial_model_id: null,
    economic_financial_model_version: null,
    economic_financial_model_hash: null,
    financial_model_status: "NOT_AVAILABLE",
    economic_financial_readiness: null,
    economic_financial_as_of_date: null,
    npv: null,
    irr: null,
    payback_period: null,
    benefit_cost_ratio: null,
    readiness_status: "READY",
    readiness_warnings_json: [],
    readiness_blockers_json: [],
    readiness_hash: "c".repeat(64),
    material_change_status: "NO_MATERIAL_CHANGE",
    content_hash: "d".repeat(64),
    preparer_user_id: 2,
    reviewer_user_id: 3,
    revision_version: 3,
    created_at: "2026-09-02T12:00:00",
    updated_at: "2026-09-02T13:00:00",
  };
  const businessCase = {
    id: 7,
    business_case_number: "BC-00001",
    project_workspace_id: 14,
    source_project_proposal_id: 3,
    owning_workspace_id: 2,
    owner_user_id: 2,
    sponsor_user_id: 3,
    status: "ACTIVE",
    current_revision_id: 11,
    material_change_review_json: {},
    configuration_id: 5,
    configuration_revision: 1,
    configuration_hash: "e".repeat(64),
    configuration_source_workspace_id: null,
    configuration_resolution_chain_json: [],
    revision_version: 3,
    created_at: "2026-09-02T12:00:00",
    updated_at: "2026-09-02T13:00:00",
    current_revision: revision,
    final_output: "READY_FOR_GOVERNED_FIVE_CASE_BUSINESS_CASE_EVIDENCE",
    next_process: "READY_FOR_INVESTMENT_EVIDENCE_POLICY_EVALUATION",
  };
  const config = {
    id: 5,
    name: "Default Governed Business Case Policy",
    description: "Controlled policy",
    status: "draft",
    revision: 2,
    version: 1,
    content_hash: "f".repeat(64),
    content_json: {
      required_sections: ["title", "business_need", "objectives", "scope"],
      separation_of_duties: { reviewer_must_differ_from_preparer: true },
      mapping: { title: "proposal.name" },
      five_case: {
        enabled_governance_models: ["CAPITAL_OWNER"],
        required_cases_by_stage: {
          FFA: ["strategic_case", "economic_case", "commercial_case", "financial_case", "management_case"],
        },
      },
    },
  };
  await page.route("**/api/v1/business-cases**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/admin/configurations")) return route.fulfill({ json: [config] });
    if (path.endsWith("/admin/configurations/preview")) {
      return route.fulfill({ json: { persisted: false, validation_issues: [], publishable: true } });
    }
    if (path.endsWith("/readiness")) {
      return route.fulfill({
        json: {
          business_case_id: 7,
          revision_id: 11,
          status: "READY",
          warnings: [],
          blockers: [],
          source_current: true,
          readiness_hash: "c".repeat(64),
          final_output: "READY_FOR_GOVERNED_BUSINESS_CASE_EVIDENCE",
          persisted: true,
        },
      });
    }
    if (path.endsWith("/revisions")) return route.fulfill({ json: [revision] });
    if (path.endsWith("/decision-snapshots")) return route.fulfill({ json: [] });
    if (path.endsWith("/refresh/preview")) {
      return route.fulfill({
        json: {
          business_case_id: 7,
          current_revision_id: 11,
          source_changes: [],
          material_change_status: "NO_MATERIAL_CHANGE",
          recommended_purpose: "REVALIDATION",
          persisted: false,
        },
      });
    }
    return route.fulfill({ json: [businessCase] });
  });

  await login(page);
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^project definition & investment case$/i);
  await expand(page, /^business case manager$/i);
  await page
    .getByRole("group", { name: "Submódulos de Business Case Manager" })
    .getByRole("button", { name: "Strategic Case" })
    .click();
  const user = page.getByRole("region", { name: "Business Case Manager", exact: true });
  await expect(user).toContainText("Strategically justified");
  await expect(user.getByRole("region", { name: "Strategic Case source evidence" })).toContainText("Project Proposal");
  await page
    .getByRole("group", { name: "Submódulos de Business Case Manager" })
    .getByRole("button", { name: "Commercial Case" })
    .click();
  await expect(user).toContainText("Commercial Strategy is referenced read-only");
  await page
    .getByRole("group", { name: "Submódulos de Business Case Manager" })
    .getByRole("button", { name: "Sources & Evidence" })
    .click();
  await expect(user).toContainText("Governed source records are read-only");
  await expect(user).toContainText("Commercial Contracting Strategy");

  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^project definition & investment case$/i);
  await page.getByRole("button", { name: /^business case manager$/i }).click();
  const admin = page.getByRole("region", { name: "Business Case Manager Configuration", exact: true });
  const adminSections = admin.getByRole("navigation", { name: "Business Case configuration sections" });
  await expect(adminSections.getByRole("button", { name: "Case Applicability" })).toBeVisible();
  await expect(adminSections.getByRole("button", { name: "Overall Readiness Rules" })).toBeVisible();
  await expect(adminSections.getByRole("button", { name: "Management Case Requirements" })).toBeVisible();
  await admin.getByRole("button", { name: "Preview", exact: true }).last().click();
  await expect(admin.getByRole("status")).toContainText("persisted=false");
  await expect(admin).toContainText("Live source mutation");
  await expect(admin).toContainText("DISABLED");
});
