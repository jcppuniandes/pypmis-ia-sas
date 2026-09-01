import { expect, type APIResponse, type Page, test } from "@playwright/test";

const apiUrl = process.env.E2E_API_URL || "http://localhost:8000";
const fixturePayload = process.env.E2E_GATE07E_FIXTURE;

type WorkspaceRef = { id: number; name: string; code: string };
type BudgetConfigurationRef = {
  id: number;
  name: string;
  code: string;
  revision: number;
  version: number;
  hash: string;
};
type Gate07GFixture = {
  index: number;
  main_portfolio: WorkspaceRef;
  projects: Record<"A" | "B" | "C", WorkspaceRef>;
  main_budget_configuration: BudgetConfigurationRef;
};
type FixtureBatch = { run_id: string; copies: Gate07GFixture[] };
type BudgetTarget = { id: number; status: string; revision_version: number; target_hash: string };
type BudgetScenario = {
  id: number;
  scenario_name: string;
  status: string;
  revision_version: number;
  scenario_hash: string;
  readiness: { status: string };
  projects: Array<{ project_workspace_id: number; selection_state: string }>;
};
type BudgetConfiguration = {
  id: number;
  name: string;
  description: string;
  status: "draft" | "published";
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
};
type ProjectDependency = {
  id: number;
  dependency_strength: "MANDATORY" | "OPTIONAL";
  description: string;
  status: "ACTIVE" | "INACTIVE";
  revision_version: number;
};

const batch = fixturePayload ? (JSON.parse(fixturePayload) as FixtureBatch) : null;

async function apiJson<T>(response: APIResponse, status = 200) {
  expect(response.status()).toBe(status);
  return (await response.json()) as T;
}

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("User").fill("admin");
  await page.getByLabel("Password").fill("1234");
  const loginResponse = page.waitForResponse(
    (response) => response.url().includes("/api/v1/auth/login") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /sign in/i }).click();
  const body = (await (await loginResponse).json()) as { access_token: string };
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
  return body.access_token;
}

async function expand(page: Page, name: RegExp) {
  const button = page.getByRole("button", { name });
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
}

async function openUserBudget(page: Page) {
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^portfolio manager$/i);
  await page.getByRole("button", { name: /^portfolio budget planning$/i }).click();
  await expect(page.getByRole("heading", { name: "Portfolio Budget Planning", exact: true })).toBeVisible();
}

async function openAdminBudget(page: Page) {
  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  await expand(page, /^enterprise strategy manager$/i);
  await page.getByRole("button", { name: /^portfolio budget planning configuration$/i }).click();
  await expect(
    page.getByRole("heading", { name: "Portfolio Budget Planning Configuration", exact: true })
  ).toBeVisible();
}

test.describe("Gate 07G Portfolio Budget Planning browser release", () => {
  test.setTimeout(300_000);
  test.skip(!batch, "Requires the disposable E2E_GATE07E_FIXTURE payload after Gate 07E/07F completion");

  test("USER and ADMIN flows govern targets, alternative scenarios, comparison and readiness", async ({
    page,
  }, testInfo) => {
    const fixture = batch!.copies[testInfo.repeatEachIndex % batch!.copies.length];
    for (const localApiOrigin of ["http://localhost:8000", "http://127.0.0.1:8000"]) {
      await page.route(`${localApiOrigin}/**`, async (route) => {
        await route.continue({ url: route.request().url().replace(localApiOrigin, apiUrl) });
      });
    }
    const failedResponses: Array<{ status: number; url: string }> = [];
    const pageErrors: string[] = [];
    page.on("response", (response) => {
      if (response.url().includes("portfolio-budget") && response.status() >= 500) {
        failedResponses.push({ status: response.status(), url: response.url() });
      }
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));

    const token = await login(page);
    const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
    const analysis = await apiJson<{
      dataset: { analysis_hash: string };
      readiness: { can_enter_budget_planning: boolean };
    }>(await page.request.get(`${apiUrl}/api/v1/portfolios/${fixture.main_portfolio.id}/analysis`, { headers }));
    expect(analysis.readiness.can_enter_budget_planning).toBe(true);

    const target = await apiJson<BudgetTarget>(
      await page.request.post(`${apiUrl}/api/v1/portfolios/${fixture.main_portfolio.id}/budget-targets`, {
        headers,
        data: {
          planning_horizon_start: "2027-01-01",
          planning_horizon_end: "2028-12-31",
          period_granularity: "YEAR",
          budget_currency: "COP",
          total_budget_target: "5000000",
          periods: [
            { period_key: "2027", period_start: "2027-01-01", period_end: "2027-12-31", amount: "2500000" },
            { period_key: "2028", period_start: "2028-01-01", period_end: "2028-12-31", amount: "2500000" },
          ],
          source_reference: "Gate 07G browser management target",
          notes: "Disposable governed browser evidence",
          idempotency_key: `${batch!.run_id}-r${fixture.index}-target-create`,
        },
      }),
      200
    );
    expect(target.status).toBe("DRAFT");
    const publishedTarget = await apiJson<BudgetTarget>(
      await page.request.post(`${apiUrl}/api/v1/portfolio-budget-targets/${target.id}/publish`, {
        headers: { ...headers, "If-Match": `"${target.revision_version}"` },
        data: { idempotency_key: `${batch!.run_id}-r${fixture.index}-target-publish` },
      })
    );
    expect(publishedTarget.status).toBe("PUBLISHED");
    expect(publishedTarget.target_hash).toMatch(/^[a-f0-9]{64}$/);

    await openUserBudget(page);
    const budgetRegion = page.getByRole("region", { name: "Portfolio Budget Planning", exact: true });
    await budgetRegion
      .getByRole("combobox", { name: "Portfolio", exact: true })
      .selectOption(String(fixture.main_portfolio.id));
    await expect(budgetRegion.getByText("READY_FOR_PORTFOLIO_SCENARIO_PLANNING", { exact: true })).toBeVisible();
    await budgetRegion.getByRole("button", { name: /^targets$/i }).click();
    await expect(page.getByRole("region", { name: "Budget Targets" })).toContainText("5.000.000 COP");

    await budgetRegion.getByRole("button", { name: /^scenarios$/i }).click();
    const scenarioPanel = page.getByRole("region", { name: "Budget Scenarios" });
    await scenarioPanel.getByLabel("Name").fill("Priority Alternative");
    await scenarioPanel.getByLabel("Creation mode").selectOption("FROM_CURRENT_PRIORITY");
    await scenarioPanel.getByLabel("Time phasing").selectOption("UNPHASED");
    const firstResponsePromise = page.waitForResponse(
      (response) => response.url().endsWith("/budget-scenarios") && response.request().method() === "POST"
    );
    await scenarioPanel.getByRole("button", { name: "Create scenario" }).click();
    const first = (await (await firstResponsePromise).json()) as BudgetScenario;
    expect(first.projects).toHaveLength(3);
    expect(first.projects.filter((row) => row.selection_state === "SELECTED")).toHaveLength(2);
    await expect(page.getByRole("region", { name: "Budget Scenario Detail" })).toContainText("Priority Alternative");
    const freezeResponsePromise = page.waitForResponse((response) => response.url().endsWith(`/${first.id}/freeze`));
    await page
      .getByRole("region", { name: "Budget Scenario Detail" })
      .getByRole("button", { name: /^freeze$/i })
      .click();
    expect(((await (await freezeResponsePromise).json()) as BudgetScenario).status).toBe("FROZEN");

    await budgetRegion.getByRole("button", { name: /^waterline$/i }).click();
    const waterline = page.getByRole("region", { name: "Portfolio Budget Waterline" });
    await expect(waterline.getByRole("table", { name: "Waterline projects" })).toContainText(fixture.projects.A.name);
    await expect(waterline).toContainText("GATE07E_CONTEXTUAL_PORTFOLIO_RANK");

    await budgetRegion.getByRole("button", { name: /^dependencies$/i }).click();
    const dependencyRegion = page.getByRole("region", { name: "Project Dependencies" });
    await dependencyRegion.getByLabel("Predecessor").selectOption(String(fixture.projects.A.id));
    await dependencyRegion.getByLabel("Successor").selectOption(String(fixture.projects.B.id));
    const dependencyResponse = page.waitForResponse(
      (response) => response.url().endsWith("/project-dependencies") && response.request().method() === "POST"
    );
    await dependencyRegion.getByRole("button", { name: "Create dependency" }).click();
    const createdDependency = await apiJson<ProjectDependency>(await dependencyResponse);
    await expect(dependencyRegion.getByRole("table", { name: "Project dependency register" })).toContainText(
      "MANDATORY"
    );
    const dependencyRow = dependencyRegion
      .getByRole("table", { name: "Project dependency register" })
      .getByRole("row")
      .filter({ hasText: fixture.projects.A.name });
    await dependencyRow.getByRole("button", { name: "Edit" }).click();
    await dependencyRow.getByLabel(`Strength for dependency ${createdDependency.id}`).selectOption("OPTIONAL");
    await dependencyRow
      .getByLabel(`Description for dependency ${createdDependency.id}`)
      .fill("Optional browser-governed dependency");
    const dependencyUpdateResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/project-dependencies/${createdDependency.id}`) &&
        response.request().method() === "PUT"
    );
    await dependencyRow.getByRole("button", { name: "Save" }).click();
    expect((await apiJson<ProjectDependency>(await dependencyUpdateResponse)).dependency_strength).toBe("OPTIONAL");
    await expect(dependencyRow).toContainText("OPTIONAL");

    await budgetRegion.getByRole("button", { name: /^scenarios$/i }).click();

    await scenarioPanel.getByLabel("Name").fill("Manual Alternative");
    await scenarioPanel.getByLabel("Creation mode").selectOption("EMPTY");
    const secondResponsePromise = page.waitForResponse(
      (response) => response.url().endsWith("/budget-scenarios") && response.request().method() === "POST"
    );
    await scenarioPanel.getByRole("button", { name: "Create scenario" }).click();
    const second = (await (await secondResponsePromise).json()) as BudgetScenario;
    const detail = page.getByRole("region", { name: "Budget Scenario Detail" });
    await expect(detail).toContainText("Manual Alternative");
    const row = detail.getByRole("row").filter({ hasText: fixture.projects.C.name });
    await row.getByRole("combobox").selectOption("FORCED_IN");
    await row.getByPlaceholder("Reason required for forced state").fill("Board-mandated strategic commitment");
    const forceResponsePromise = page.waitForResponse((response) => response.url().includes("/selection"));
    await row.getByRole("button", { name: "Apply" }).click();
    const forced = (await (await forceResponsePromise).json()) as BudgetScenario;
    expect(forced.projects.find((item) => item.project_workspace_id === fixture.projects.C.id)?.selection_state).toBe(
      "FORCED_IN"
    );
    const frozenSecond = await apiJson<BudgetScenario>(
      await page.request.post(`${apiUrl}/api/v1/portfolio-budget-scenarios/${second.id}/freeze`, {
        headers: { ...headers, "If-Match": `"${forced.revision_version}"` },
        data: { idempotency_key: `${batch!.run_id}-r${fixture.index}-freeze-second` },
      })
    );
    expect(frozenSecond.status).toBe("FROZEN");
    expect(frozenSecond.readiness.status).toBe("READY");
    await budgetRegion.getByRole("button", { name: /refresh/i }).click();

    await budgetRegion.getByRole("button", { name: /^comparison$/i }).click();
    const comparison = page.getByRole("region", { name: "Scenario Comparison" });
    const scenarioChecks = comparison.getByRole("checkbox");
    await scenarioChecks.nth(0).check();
    await scenarioChecks.nth(1).check();
    const compareResponsePromise = page.waitForResponse((response) =>
      response.url().endsWith("/budget-scenarios/compare")
    );
    await comparison.getByRole("button", { name: "Compare selected" }).click();
    const compared = await apiJson<{ pairwise_delta: Record<string, unknown> }>(await compareResponsePromise);
    expect(compared.pairwise_delta).toBeTruthy();
    await expect(comparison.getByText("Pairwise delta")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`gate07g-user-${fixture.index}.png`), fullPage: true });

    const invalidForced = await page.request.post(
      `${apiUrl}/api/v1/portfolio-budget-scenarios/${second.id}/projects/${fixture.projects.A.id}/selection`,
      {
        headers: { ...headers, "If-Match": `"${frozenSecond.revision_version}"` },
        data: {
          selection_state: "FORCED_IN",
          forced_reason: null,
          period_profile: [],
          idempotency_key: `${batch!.run_id}-r${fixture.index}-invalid-force`,
        },
      }
    );
    expect(invalidForced.status()).toBe(422);

    await budgetRegion.getByRole("button", { name: /^dependencies$/i }).click();
    const activeDependencyRow = dependencyRegion
      .getByRole("table", { name: "Project dependency register" })
      .getByRole("row")
      .filter({ hasText: fixture.projects.A.name });
    const dependencyDeactivateResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/project-dependencies/${createdDependency.id}/deactivate`) &&
        response.request().method() === "POST"
    );
    await activeDependencyRow.getByRole("button", { name: "Deactivate" }).click();
    expect((await apiJson<ProjectDependency>(await dependencyDeactivateResponse)).status).toBe("INACTIVE");
    await expect(activeDependencyRow).toContainText("INACTIVE");

    await openAdminBudget(page);
    const admin = page.getByRole("region", { name: "Portfolio Budget Planning Configuration" });
    await admin.getByRole("button", { name: new RegExp(fixture.main_budget_configuration.name, "i") }).click();
    const actions = page.getByLabel("Portfolio Budget configuration actions");
    const cloneResponsePromise = page.waitForResponse((response) =>
      response.url().endsWith(`/portfolio-budget/admin/configurations/${fixture.main_budget_configuration.id}/clone`)
    );
    await actions.getByRole("button", { name: /^clone$/i }).click();
    const clone = (await (await cloneResponsePromise).json()) as BudgetConfiguration;
    expect(clone.status).toBe("draft");
    await page.getByLabel("Preview Portfolio").selectOption(String(fixture.main_portfolio.id));
    await page.getByLabel("Scenario max count").fill("5");
    const previewResponsePromise = page.waitForResponse((response) =>
      response.url().endsWith("/portfolio-budget/admin/configurations/preview")
    );
    await actions.getByRole("button", { name: /^preview$/i }).click();
    const preview = await apiJson<{ persisted: boolean; publishable: boolean }>(await previewResponsePromise);
    expect(preview).toEqual(expect.objectContaining({ persisted: false, publishable: true }));
    await expect(page.getByText(/persisted=false and no Target or Scenario was created/i)).toBeVisible();
    const saveResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/portfolio-budget/admin/configurations/${clone.id}`) &&
        response.request().method() === "PUT"
    );
    await actions.getByRole("button", { name: /^save$/i }).click();
    const saved = (await (await saveResponsePromise).json()) as BudgetConfiguration;
    expect(saved.version).toBe(clone.version + 1);
    const staleSave = await page.request.put(`${apiUrl}/api/v1/portfolio-budget/admin/configurations/${clone.id}`, {
      headers: { ...headers, "If-Match": `"${clone.version}"` },
      data: { name: clone.name, description: clone.description, content_json: saved.content_json },
    });
    expect(staleSave.status()).toBe(412);
    const publishResponsePromise = page.waitForResponse((response) =>
      response.url().endsWith(`/portfolio-budget/admin/configurations/${clone.id}/publish`)
    );
    await actions.getByRole("button", { name: /^publish$/i }).click();
    expect(((await (await publishResponsePromise).json()) as BudgetConfiguration).status).toBe("published");
    for (const forbidden of ["Scenario winner", "Resource allocation", "FID approval", "Funds assignment"]) {
      await expect(admin.getByRole("button", { name: new RegExp(forbidden, "i") })).toHaveCount(0);
    }
    await page.screenshot({ path: testInfo.outputPath(`gate07g-admin-${fixture.index}.png`), fullPage: true });

    const readiness = await apiJson<{ final_output: string; can_enter_budget_recommendation: boolean }>(
      await page.request.get(`${apiUrl}/api/v1/portfolios/${fixture.main_portfolio.id}/budget-planning/readiness`, {
        headers,
      })
    );
    expect(readiness).toEqual(
      expect.objectContaining({
        final_output: "READY_FOR_PORTFOLIO_BUDGET_RECOMMENDATION",
        can_enter_budget_recommendation: true,
      })
    );
    expect(failedResponses).toEqual([]);
    expect(pageErrors).toEqual([]);
  });
});
