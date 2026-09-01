import { expect, type APIResponse, type Page, test } from "@playwright/test";

const apiUrl = process.env.E2E_API_URL || "http://localhost:8000";
const fixturePayload = process.env.E2E_GATE07E_FIXTURE;

type WorkspaceRef = { id: number; name: string; code: string };
type AnalysisConfigurationRef = {
  id: number;
  name: string;
  code: string;
  revision: number;
  version: number;
  hash: string;
};
type Gate07FFixture = {
  index: number;
  main_portfolio: WorkspaceRef;
  projects: Record<"A" | "B" | "C", WorkspaceRef>;
  main_analysis_configuration: AnalysisConfigurationRef;
};
type FixtureBatch = { run_id: string; copies: Gate07FFixture[] };
type AnalysisOverview = {
  dataset: { rows: Array<{ project_workspace_id: number }>; analysis_hash: string; blockers: string[] };
  readiness: {
    status: string;
    final_output: string;
    can_enter_portfolio_scenario_planning: boolean;
  };
};
type AnalysisConfiguration = {
  id: number;
  name: string;
  description: string;
  status: "draft" | "published";
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash: string;
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

async function openUserAnalysis(page: Page) {
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^portfolio manager$/i);
  await page.getByRole("button", { name: /^portfolio analysis$/i }).click();
  await expect(page.getByRole("heading", { name: "Portfolio Analysis", exact: true })).toBeVisible();
}

async function openAdminAnalysis(page: Page) {
  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  await expand(page, /^enterprise strategy manager$/i);
  await page.getByRole("button", { name: /^portfolio analysis configuration$/i }).click();
  await expect(page.getByRole("heading", { name: "Portfolio Analysis Configuration", exact: true })).toBeVisible();
}

test.describe("Gate 07F Portfolio Analysis browser release closeout", () => {
  test.setTimeout(240_000);
  test.skip(!batch, "Requires the disposable E2E_GATE07E_FIXTURE payload after Gate 07E completion");

  test("USER and ADMIN flows preserve Gate 07E truth and reach Scenario Planning readiness", async ({
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
      if (response.url().includes("portfolio-analysis") && response.status() >= 500) {
        failedResponses.push({ status: response.status(), url: response.url() });
      }
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));

    const token = await login(page);
    const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
    await openUserAnalysis(page);
    const selector = page
      .getByRole("region", { name: "Portfolio Analysis", exact: true })
      .getByRole("combobox", { name: "Portfolio", exact: true });
    await selector.selectOption(String(fixture.main_portfolio.id));
    await expect(page.getByText("READY_FOR_PORTFOLIO_SCENARIO_PLANNING", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Portfolio Analysis Readiness")).toContainText("READY");

    const initialResponse = await page.request.get(
      `${apiUrl}/api/v1/portfolios/${fixture.main_portfolio.id}/analysis`,
      { headers }
    );
    const initial = await apiJson<AnalysisOverview>(initialResponse);
    expect(initial.dataset.rows).toHaveLength(3);
    expect(initial.dataset.rows.map((row) => row.project_workspace_id)).toEqual([
      fixture.projects.A.id,
      fixture.projects.B.id,
      fixture.projects.C.id,
    ]);
    expect(initial.dataset.analysis_hash).toMatch(/^[a-f0-9]{64}$/);
    expect(initial.dataset.blockers).toEqual([]);
    expect(initial.readiness).toEqual(
      expect.objectContaining({
        status: "READY",
        final_output: "READY_FOR_PORTFOLIO_SCENARIO_PLANNING",
        can_enter_portfolio_scenario_planning: true,
      })
    );

    await page.getByRole("button", { name: /^investor map$/i }).click();
    await expect(page.getByRole("img", { name: /3 Projects plotted in the Investor Map/i })).toBeVisible();
    await expect(page.getByLabel("Investor Map accessible Project list").getByRole("button")).toHaveCount(3);
    await page.getByTestId(`investor-map-project-${fixture.projects.A.id}`).click();
    await expect(page.getByRole("complementary", { name: "Project analysis detail" })).toContainText(
      fixture.projects.A.name
    );
    await page.getByRole("button", { name: "Close Project detail" }).click();

    await page.getByRole("button", { name: /^scorecard$/i }).click();
    const scorecard = page.getByRole("table");
    await expect(scorecard).toBeVisible();
    for (const project of Object.values(fixture.projects)) await expect(scorecard).toContainText(project.name);
    await expect(page.getByLabel("Analysis filters")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`gate07f-user-${fixture.index}.png`), fullPage: true });

    const filtered = await apiJson<AnalysisOverview>(
      await page.request.get(
        `${apiUrl}/api/v1/portfolios/${fixture.main_portfolio.id}/analysis?project_type=NOT_PRESENT`,
        { headers }
      )
    );
    expect(filtered.dataset.rows).toEqual([]);
    expect(filtered.dataset.analysis_hash).toBe(initial.dataset.analysis_hash);
    const stale = await page.request.post(`${apiUrl}/api/v1/portfolios/${fixture.main_portfolio.id}/analysis/preview`, {
      headers,
      data: { filters: {}, expected_analysis_hash: "0".repeat(64) },
    });
    expect(stale.status()).toBe(412);
    expect(JSON.stringify(await stale.json())).toContain("STALE_PORTFOLIO_ANALYSIS_SOURCE");

    await openAdminAnalysis(page);
    const admin = page.getByRole("region", { name: "Portfolio Analysis Configuration" });
    await page.getByTestId(`portfolio-analysis-configuration-${fixture.main_analysis_configuration.id}`).click();
    await expect(admin.getByRole("heading", { name: fixture.main_analysis_configuration.name })).toBeVisible();
    const actions = page.getByLabel("Portfolio Analysis configuration actions");
    const cloneResponsePromise = page.waitForResponse((response) =>
      response
        .url()
        .endsWith(`/portfolio-analysis/admin/configurations/${fixture.main_analysis_configuration.id}/clone`)
    );
    await actions.getByRole("button", { name: /^clone$/i }).click();
    const clone = (await (await cloneResponsePromise).json()) as AnalysisConfiguration;
    expect(clone.status).toBe("draft");
    await expect(page.getByTestId(`portfolio-analysis-configuration-${clone.id}`)).toHaveClass(/active/);
    await page.getByLabel("Preview Portfolio").selectOption(String(fixture.main_portfolio.id));
    await page.getByLabel("Vertical reference line").fill("71");

    const previewResponsePromise = page.waitForResponse((response) =>
      response.url().endsWith("/portfolio-analysis/admin/configurations/preview")
    );
    await actions.getByRole("button", { name: /^preview$/i }).click();
    const preview = (await (await previewResponsePromise).json()) as { persisted: boolean; publishable: boolean };
    expect(preview).toEqual(expect.objectContaining({ persisted: false, publishable: true }));
    await expect(page.getByText(/without persisting snapshot, rank, membership or evaluation data/i)).toBeVisible();
    const afterPreview = await apiJson<AnalysisOverview>(
      await page.request.get(`${apiUrl}/api/v1/portfolios/${fixture.main_portfolio.id}/analysis`, { headers })
    );
    expect(afterPreview.dataset.analysis_hash).toBe(initial.dataset.analysis_hash);

    const saveResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/portfolio-analysis/admin/configurations/${clone.id}`) &&
        response.request().method() === "PUT"
    );
    await actions.getByRole("button", { name: /^save$/i }).click();
    const saved = (await (await saveResponsePromise).json()) as AnalysisConfiguration;
    expect(saved.version).toBe(clone.version + 1);
    await expect(page.getByRole("status")).toContainText(/save completed/i);
    const staleSave = await page.request.put(`${apiUrl}/api/v1/portfolio-analysis/admin/configurations/${clone.id}`, {
      headers: { ...headers, "If-Match": `"${clone.version}"` },
      data: { name: clone.name, description: clone.description, content_json: saved.content_json },
    });
    expect(staleSave.status()).toBe(412);
    expect(JSON.stringify(await staleSave.json())).toContain("ETAG_MISMATCH");

    const publishResponsePromise = page.waitForResponse((response) =>
      response.url().endsWith(`/portfolio-analysis/admin/configurations/${clone.id}/publish`)
    );
    await actions.getByRole("button", { name: /^publish$/i }).click();
    const publishResponse = await publishResponsePromise;
    expect(publishResponse.ok()).toBeTruthy();
    const published = (await publishResponse.json()) as AnalysisConfiguration;
    expect(published.status).toBe("published");
    for (const forbidden of ["FID approval", "Budget selection", "Resource selection", "FORCED_IN", "SELECTED"]) {
      await expect(admin.getByText(forbidden, { exact: false })).toHaveCount(0);
    }
    await page.screenshot({ path: testInfo.outputPath(`gate07f-admin-${fixture.index}.png`), fullPage: true });

    expect(failedResponses).toEqual([]);
    expect(pageErrors).toEqual([]);
  });
});
