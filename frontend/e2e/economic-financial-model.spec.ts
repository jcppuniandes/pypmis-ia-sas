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

test("Gate 07M-FIN exposes governed USER and ADMIN workspaces", async ({ page }) => {
  const version = {
    id: 21,
    model_id: 9,
    version_number: 1,
    version_label: "V1",
    purpose: "INITIAL_FEASIBILITY",
    status: "COMPLETED",
    model_type: "COMMERCIAL_PROJECT",
    base_currency: "USD",
    cash_flow_basis: "NOMINAL",
    periodicity: "ANNUAL",
    as_of_date: "2026-09-02T12:00:00",
    source_references_json: { business_case: { id: 7, revision_id: 11 } },
    source_hashes_json: { business_case: "a".repeat(64) },
    source_current: true,
    total_investment_requirement: "1000000",
    total_model_financing: "1000000",
    governed_funding_assigned: "1000000",
    funding_gap: "0",
    funding_reconciliation_status: "RECONCILED",
    project_financial_npv: "245000",
    project_irr: "0.178",
    economic_npv: "310000",
    economic_irr: "0.201",
    benefit_cost_ratio: "1.43",
    simple_payback: "4.2",
    equity_irr: "0.224",
    moic: "2.1",
    minimum_dscr: "1.35",
    average_dscr: "1.52",
    llcr: "1.71",
    debt_to_equity: "0.67",
    overall_readiness: "READY",
    warnings_json: [],
    blockers_json: [],
    model_hash: "b".repeat(64),
    calculation_engine_version: "PPMIS-FIN-1.0",
    revision_version: 7,
  };
  const model = {
    id: 9,
    model_number: "EFM-000009",
    project_workspace_id: 14,
    business_case_id: 7,
    owner_user_id: 2,
    status: "ACTIVE",
    current_version_id: 21,
    revision_version: 2,
    current_version: version,
    final_output: "READY_FOR_GOVERNED_ECONOMIC_FINANCIAL_EVIDENCE",
    next_process: "UPDATE_GATE07J_EVID_FOR_BUSINESS_CASE_AND_ECONOMIC_FINANCIAL_READINESS",
  };
  const configuration = {
    id: 5,
    name: "Default Economic & Financial Model Policy",
    description: "Controlled Gate 07M-FIN policy",
    status: "draft",
    revision: 2,
    version: 1,
    content_hash: "c".repeat(64),
    content_json: {
      applicable_model_types: ["COMMERCIAL_PROJECT", "NON_REVENUE_PROJECT", "PUBLIC_ECONOMIC_APPRAISAL", "MIXED"],
      required_metrics: { COMMERCIAL_PROJECT: ["PROJECT_FINANCIAL_NPV", "PROJECT_IRR"] },
      required_assumptions: { COMMERCIAL_PROJECT: ["project_discount_rate"] },
      separation_of_duties: { reviewer_must_differ_from_preparer: true },
    },
  };
  await page.route("**/api/v1/economic-financial-models**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/admin/configurations")) return route.fulfill({ json: [configuration] });
    if (path.endsWith("/admin/configurations/preview"))
      return route.fulfill({ json: { persisted: false, readiness_preview: "READY", blockers: [] } });
    if (path.endsWith("/readiness"))
      return route.fulfill({
        json: {
          model_id: 9,
          model_version_id: 21,
          status: "READY",
          dimensions: { FINANCIAL_MODEL_READINESS: "READY" },
          warnings: [],
          blockers: [],
          source_current: true,
          readiness_hash: "d".repeat(64),
          final_output: model.final_output,
          persisted: true,
        },
      });
    return route.fulfill({ json: [model] });
  });

  await login(page);
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^economic & financial model$/i);
  await page
    .getByRole("group", { name: "Submódulos de Economic & Financial Model" })
    .getByRole("button", { name: "Overview" })
    .click();
  const user = page.getByRole("region", { name: "Economic & Financial Model", exact: true });
  await expect(user).toContainText("EFM-000009");
  await expect(user).toContainText("COMMERCIAL_PROJECT");
  await expect(user).toContainText("245000");
  await expect(user.getByRole("button", { name: "Complete" })).toBeDisabled();

  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  await expand(page, /^enterprise strategy manager$/i);
  await page.getByRole("button", { name: /^economic & financial model$/i }).click();
  const admin = page.getByRole("region", { name: "Economic & Financial Model Configuration", exact: true });
  await expect(
    admin.getByRole("navigation", { name: "Economic financial configuration sections" }).getByRole("button")
  ).toHaveCount(45);
  await admin.getByLabel("Economic financial configuration JSON").fill(JSON.stringify(configuration.content_json));
  await admin.getByText("Project Workspace ID").locator("input").fill("14");
  await admin.getByRole("button", { name: "Preview" }).last().click();
  await expect(admin.getByRole("status")).toContainText("persisted=false");
});
