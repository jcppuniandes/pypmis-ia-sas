import { expect, type Page, test } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

type Evidence = {
  portfolio: { id: number; code: string; name: string };
  project: { id: number; code: string };
  funding: { sources: Array<{ key: string; source_id: number }> };
  business_case: { id: number; hash: string; fin_hash: string; status: string; readiness: string };
  financial_model: { id: number; hash: string; status: string; readiness: string };
  gate07j: { preparation_id: number; hash: string };
  gate07k: { decision_id: number; decision_hash: string; source_package_hash: string };
  gate07l: { eligibility_status: string };
  negative_fin_stale: {
    recovery: {
      funding_readiness_hash: string;
      financial_model_hash: string;
      provider_readiness: string;
    };
  };
};

const evidencePath = process.env.E2E_GATE07M_FID_EVIDENCE;
if (!evidencePath) throw new Error("E2E_GATE07M_FID_EVIDENCE is required");
const evidence = JSON.parse(readFileSync(evidencePath, "utf8")) as Evidence;
const apiUrl = process.env.E2E_API_URL || "http://127.0.0.1:18000";
const resultPath = process.env.E2E_GATE07M_FID_BROWSER_RESULT;

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("User").fill("admin");
  await page.getByLabel("Password").fill("1234");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
}

async function expand(page: Page, name: RegExp) {
  const button = page.locator("button[aria-expanded]").filter({ hasText: name }).first();
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
}

async function openSubmodule(page: Page, moduleName: RegExp, groupName: string, submoduleName: string) {
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, moduleName);
  await page
    .getByRole("group", { name: `Submódulos de ${groupName}` })
    .getByRole("button", { name: submoduleName, exact: true })
    .click();
}

test.describe.configure({ mode: "serial" });

test("Gate 07M-FID uses the real localhost stack for happy, negative and historical paths", async ({
  page,
  request,
}) => {
  test.setTimeout(180_000);
  const pageErrors: string[] = [];
  const consoleProblems: string[] = [];
  const unexpectedResponses: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (entry) => {
    if (["error", "warning"].includes(entry.type())) consoleProblems.push(`${entry.type()}: ${entry.text()}`);
  });
  page.on("response", (response) => {
    if (response.status() >= 400) unexpectedResponses.push(`${response.status()} ${response.url()}`);
  });

  await login(page);

  await openSubmodule(page, /^business case manager$/i, "Business Case Manager", "Business Case Readiness");
  const businessCase = page.getByRole("region", { name: "Business Case Manager", exact: true });
  await expect(businessCase).toContainText(evidence.business_case.status);
  await expect(businessCase).toContainText(evidence.business_case.readiness);
  await businessCase.getByRole("button", { name: "Economic & Financial Model", exact: true }).click();
  await expect(businessCase.locator("pre")).toContainText(evidence.negative_fin_stale.recovery.financial_model_hash);

  await openSubmodule(page, /^economic & financial model$/i, "Economic & Financial Model", "Readiness");
  const financial = page.getByRole("region", { name: "Economic & Financial Model", exact: true });
  await expect(financial).toContainText(evidence.financial_model.status);
  await expect(financial).toContainText(evidence.negative_fin_stale.recovery.provider_readiness);
  await financial.getByRole("button", { name: "Source Lineage", exact: true }).click();
  await expect(financial.locator("pre")).toContainText(evidence.negative_fin_stale.recovery.funding_readiness_hash);

  await openSubmodule(page, /^portfolio manager$/i, "Portfolio Manager", "Investment Gate Preparation");
  const preparation = page.getByRole("region", { name: "Investment Gate Preparation", exact: true });
  await preparation.getByRole("combobox", { name: /^Portfolio/ }).selectOption(String(evidence.portfolio.id));
  await preparation
    .getByRole("combobox", { name: /^Preparation/ })
    .selectOption(String(evidence.gate07j.preparation_id));
  await preparation.getByRole("button", { name: "Evidence Package", exact: true }).click();
  const bcRow = preparation.locator("article").filter({ hasText: "Business Case Readiness" });
  const finRow = preparation.locator("article").filter({ hasText: "Economic / Financial Readiness" });
  await expect(bcRow).toContainText("Class A");
  await expect(bcRow).toContainText("VALID");
  await bcRow.getByText("View Business Case source").click();
  await expect(bcRow.locator("pre")).toContainText(evidence.business_case.hash);
  await expect(finRow).toContainText("Class A");
  await expect(finRow).toContainText("VALID");
  await finRow.getByText("View Economic / Financial source").click();
  await expect(finRow.locator("pre")).toContainText(evidence.financial_model.hash);

  await preparation.getByRole("button", { name: "Preparations", exact: true }).click();
  const preparationSelector = preparation.getByRole("combobox", { name: /^Preparation/ });
  await preparationSelector.selectOption("0");
  const createPreparation = preparation.getByRole("button", { name: "Create governed preparation" });
  await expect(createPreparation).toBeEnabled();
  await createPreparation.click();
  await expect(preparation.getByText("Evidence requirements and references", { exact: true })).toBeVisible();
  await expect(preparationSelector).not.toHaveValue("0");
  const negativePreparationId = Number(await preparationSelector.inputValue());
  expect(negativePreparationId).toBeGreaterThan(0);

  await openSubmodule(page, /^investment governance$/i, "Investment Governance", "Decision Queue");
  const decision = page.getByRole("region", { name: "Investment Decision / FID", exact: true });
  await decision.locator(".decisionControls select").first().selectOption(String(evidence.gate07k.decision_id));
  await expect(decision.getByText("FID YES")).toBeVisible();
  await expect(decision.getByText("Project activation NO")).toBeVisible();
  await expect(decision).toContainText(evidence.gate07k.source_package_hash.slice(0, 14));
  await decision.getByRole("button", { name: "Authorization Output", exact: true }).click();
  await expect(decision.locator("pre")).toContainText('"full_funds_authorized": true');
  await expect(decision.locator("pre")).toContainText('"can_activate_project": false');

  await openSubmodule(page, /^investment governance$/i, "Investment Governance", "Project Eligibility Matrix");
  const postFid = page.getByRole("region", { name: "Post-FID Project Governance", exact: true });
  await postFid.getByLabel("Investment Decision / FID").selectOption(String(evidence.gate07k.decision_id));
  await expect(postFid).toContainText(evidence.gate07l.eligibility_status);
  await expect(postFid).toContainText(evidence.project.code);

  const authState = await page.evaluate(() => JSON.parse(localStorage.getItem("pypmis_auth") || "{}").state);
  const token = String(authState.token);
  const sponsor = evidence.funding.sources.find((item) => item.key === "SPONSOR");
  expect(sponsor).toBeTruthy();
  const sourceResponse = await request.get(`${apiUrl}/api/v1/funding-sources/${sponsor!.source_id}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(sourceResponse.ok()).toBeTruthy();
  const source = (await sourceResponse.json()) as { revision_version: number };
  const suspendResponse = await request.post(`${apiUrl}/api/v1/funding-sources/${sponsor!.source_id}/suspend`, {
    headers: { Authorization: `Bearer ${token}`, "If-Match": `"${source.revision_version}"` },
    data: { idempotency_key: `gate07m-browser-stale-${Date.now()}` },
  });
  expect(suspendResponse.ok()).toBeTruthy();

  const preparationOverviewResponse = await request.get(
    `${apiUrl}/api/v1/portfolios/${evidence.portfolio.id}/investment-gate-preparation`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  expect(preparationOverviewResponse.ok()).toBeTruthy();
  const preparationOverview = (await preparationOverviewResponse.json()) as {
    preparations: Array<{ id: number; revision_version: number }>;
  };
  const negativePreparation = preparationOverview.preparations.find((item) => item.id === negativePreparationId);
  expect(negativePreparation).toBeTruthy();
  const refreshPreviewResponse = await request.post(
    `${apiUrl}/api/v1/investment-gate-preparations/${negativePreparationId}/refresh/preview`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  expect(refreshPreviewResponse.ok()).toBeTruthy();
  const refreshPreview = (await refreshPreviewResponse.json()) as { proposed_source_hash: string };
  const refreshApplyResponse = await request.post(
    `${apiUrl}/api/v1/investment-gate-preparations/${negativePreparationId}/refresh`,
    {
      headers: {
        Authorization: `Bearer ${token}`,
        "If-Match": `"${negativePreparation!.revision_version}"`,
      },
      data: {
        expected_source_hash: refreshPreview.proposed_source_hash,
        idempotency_key: `gate07m-browser-refresh-${Date.now()}`,
      },
    }
  );
  expect(refreshApplyResponse.ok()).toBeTruthy();

  await openSubmodule(page, /^portfolio manager$/i, "Portfolio Manager", "Investment Gate Preparation");
  await preparation.getByRole("combobox", { name: /^Portfolio/ }).selectOption(String(evidence.portfolio.id));
  await preparation.getByRole("combobox", { name: /^Preparation/ }).selectOption(String(negativePreparationId));
  await preparation.getByRole("button", { name: "Evidence Package", exact: true }).click();
  await expect(preparation.getByText("Economic / Financial Readiness", { exact: true })).toBeVisible();
  const staleFinRow = preparation.locator("article").filter({ hasText: "Economic / Financial Readiness" });
  await expect(staleFinRow).toContainText(/STALE|INVALID/);
  await expect(preparation.getByText(/GATE07J_REWORK_REQUIRED|BLOCKED/).first()).toBeVisible();

  await openSubmodule(page, /^investment governance$/i, "Investment Governance", "Decision History");
  await decision.locator(".decisionControls select").first().selectOption(String(evidence.gate07k.decision_id));
  await expect(decision.getByText("FID YES")).toBeVisible();
  await decision.getByRole("button", { name: "Investment Decision Package", exact: true }).click();
  await expect(decision.locator("pre")).toContainText(evidence.financial_model.hash);

  expect(pageErrors).toEqual([]);
  expect(consoleProblems).toEqual([]);
  expect(unexpectedResponses).toEqual([]);
  if (resultPath) {
    writeFileSync(
      resolve(resultPath),
      JSON.stringify(
        {
          status: "PASS",
          base_url: test.info().project.use.baseURL,
          happy_path: true,
          negative_fin_stale: true,
          historical_fid: true,
          source_drilldown: true,
          page_errors: pageErrors,
          console_problems: consoleProblems,
          unexpected_responses: unexpectedResponses,
        },
        null,
        2
      )
    );
  }
});
