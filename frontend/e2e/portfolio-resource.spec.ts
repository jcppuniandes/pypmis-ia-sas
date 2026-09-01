import { expect, type APIResponse, type Page, test } from "@playwright/test";

const apiUrl = process.env.E2E_API_URL || "http://localhost:8000";
const fixturePayload = process.env.E2E_GATE07E_FIXTURE;

type WorkspaceRef = { id: number; name: string; code: string };
type Gate07HFixture = { index: number; main_portfolio: WorkspaceRef; projects: Record<"A" | "B" | "C", WorkspaceRef> };
type FixtureBatch = { run_id: string; copies: Gate07HFixture[] };
type ResourceConfiguration = {
  id: number;
  name: string;
  description: string;
  status: "draft" | "published" | "superseded";
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
};
type CapacityPlan = { id: number; status: string; revision_version: number; capacity_hash: string };
type DemandProfile = { id: number; status: string; revision_version: number; demand_hash: string };
type ResourceScenario = {
  id: number;
  scenario_name: string;
  status: string;
  revision_version: number;
  scenario_hash: string;
  readiness: { status: string };
  projects: Array<{ project_workspace_id: number; selection_state: string }>;
};

const batch = fixturePayload ? (JSON.parse(fixturePayload) as FixtureBatch) : null;

async function apiJson<T>(response: APIResponse, status = 200) {
  if (response.status() !== status) {
    throw new Error(`Expected HTTP ${status}, received ${response.status()}: ${await response.text()}`);
  }
  return (await response.json()) as T;
}

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("User").fill("admin");
  await page.getByLabel("Password").fill("1234");
  const response = page.waitForResponse(
    (item) => item.url().includes("/api/v1/auth/login") && item.request().method() === "POST"
  );
  await page.getByRole("button", { name: /sign in/i }).click();
  const body = (await (await response).json()) as { access_token: string };
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
  return body.access_token;
}

async function expand(page: Page, name: RegExp) {
  const button = page.getByRole("button", { name });
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
}

async function openUserResource(page: Page) {
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^portfolio manager$/i);
  await page.getByRole("button", { name: /^portfolio resource planning$/i }).click();
  await expect(page.getByRole("heading", { name: "Portfolio Resource Planning", exact: true })).toBeVisible();
}

async function openAdminResource(page: Page) {
  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  await expand(page, /^enterprise strategy manager$/i);
  await page.getByRole("button", { name: /^portfolio resource planning configuration$/i }).click();
  await expect(
    page.getByRole("heading", { name: "Portfolio Resource Planning Configuration", exact: true })
  ).toBeVisible();
}

test.describe("Gate 07H Portfolio Resource Planning browser release", () => {
  test.setTimeout(300_000);
  test.skip(!batch, "Requires disposable Gate 07E/07F fixture payload");

  test("USER and ADMIN flows govern capacity, demand, alternatives, overload and readiness", async ({
    page,
  }, testInfo) => {
    const fixture = batch!.copies[testInfo.repeatEachIndex % batch!.copies.length];
    for (const localApiOrigin of ["http://localhost:8000", "http://127.0.0.1:8000"]) {
      await page.route(`${localApiOrigin}/**`, async (route) =>
        route.continue({ url: route.request().url().replace(localApiOrigin, apiUrl) })
      );
    }
    const failedResponses: Array<{ status: number; url: string }> = [];
    const pageErrors: string[] = [];
    page.on("response", (response) => {
      if (response.url().includes("portfolio-resource") && response.status() >= 500)
        failedResponses.push({ status: response.status(), url: response.url() });
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));

    const token = await login(page);
    const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
    const configurations = await apiJson<ResourceConfiguration[]>(
      await page.request.get(`${apiUrl}/api/v1/portfolio-resource/admin/configurations`, { headers })
    );
    let published = configurations.find((item) => item.status === "published");
    if (!published) {
      const draft = configurations.find((item) => item.status === "draft");
      expect(draft).toBeTruthy();
      published = await apiJson<ResourceConfiguration>(
        await page.request.post(`${apiUrl}/api/v1/portfolio-resource/admin/configurations/${draft!.id}/publish`, {
          headers: { ...headers, "If-Match": `"${draft!.version}"` },
        })
      );
    }

    const capacityDraft = await apiJson<CapacityPlan>(
      await page.request.post(`${apiUrl}/api/v1/portfolios/${fixture.main_portfolio.id}/resource-capacity-plans`, {
        headers,
        data: {
          plan_name: "Gate 07H browser capacity",
          planning_horizon_start: "2027-01-01",
          planning_horizon_end: "2027-12-31",
          period_granularity: "YEAR",
          source_reference: "Strategic workforce plan",
          notes: "Disposable browser evidence",
          periods: [
            {
              resource_role_key: "PROJECT_MANAGER",
              resource_role_name: "Project Manager",
              role_category: "MANAGEMENT",
              period_key: "2027",
              period_start: "2027-01-01",
              period_end: "2027-12-31",
              capacity_value: "2",
              unit: "FTE",
              source_reference: "Management capacity",
              notes: "",
            },
          ],
          idempotency_key: `${batch!.run_id}-r${fixture.index}-resource-capacity`,
        },
      })
    );
    const capacity = await apiJson<CapacityPlan>(
      await page.request.post(`${apiUrl}/api/v1/portfolio-resource-capacity-plans/${capacityDraft.id}/publish`, {
        headers: { ...headers, "If-Match": `"${capacityDraft.revision_version}"` },
        data: { idempotency_key: `${batch!.run_id}-r${fixture.index}-resource-capacity-publish` },
      })
    );
    expect(capacity.status).toBe("PUBLISHED");
    expect(capacity.capacity_hash).toMatch(/^[a-f0-9]{64}$/);

    for (const project of Object.values(fixture.projects)) {
      const draft = await apiJson<DemandProfile>(
        await page.request.post(`${apiUrl}/api/v1/projects/${project.id}/resource-demand-profiles`, {
          headers,
          data: {
            profile_name: `${project.name} strategic demand`,
            source_type: "PROJECT_RESOURCE_DEMAND_PROFILE",
            source_reference: "Project definition estimate",
            as_of_date: "2026-08-25",
            planning_start: "2027-01-01",
            planning_finish: "2027-12-31",
            generation_method: "EXPLICIT_PERIOD_PROFILE",
            periods: [
              {
                resource_role_key: "PROJECT_MANAGER",
                resource_role_name: "Project Manager",
                role_category: "MANAGEMENT",
                period_key: "2027",
                period_start: "2027-01-01",
                period_end: "2027-12-31",
                demand_value: "1",
                unit: "FTE",
                source_reference: "Project estimate",
                notes: "",
              },
            ],
            idempotency_key: `${batch!.run_id}-r${fixture.index}-resource-demand-${project.id}`,
          },
        })
      );
      const profile = await apiJson<DemandProfile>(
        await page.request.post(`${apiUrl}/api/v1/project-resource-demand-profiles/${draft.id}/publish`, {
          headers: { ...headers, "If-Match": `"${draft.revision_version}"` },
          data: { idempotency_key: `${batch!.run_id}-r${fixture.index}-resource-demand-publish-${project.id}` },
        })
      );
      expect(profile.status).toBe("PUBLISHED");
      expect(profile.demand_hash).toMatch(/^[a-f0-9]{64}$/);
    }

    await openUserResource(page);
    const resource = page.getByRole("region", { name: "Portfolio Resource Planning", exact: true });
    await resource
      .getByRole("combobox", { name: "Portfolio", exact: true })
      .selectOption(String(fixture.main_portfolio.id));
    await expect(resource.getByText("READY_FOR_PORTFOLIO_SCENARIO_PLANNING", { exact: true })).toBeVisible();
    await resource.getByRole("button", { name: /^capacity$/i }).click();
    await expect(page.getByRole("region", { name: "Resource Capacity Plans" })).toContainText(
      "Gate 07H browser capacity"
    );
    await resource.getByRole("button", { name: /^demand$/i }).click();
    await expect(page.getByRole("table", { name: "Project Resource Demand Profiles" })).toContainText(
      "Project Manager"
    );
    await resource.getByRole("button", { name: /^scenarios$/i }).click();
    const scenarioName = resource.getByLabel("Resource Scenario name");
    await scenarioName.fill("Resource balanced alternative");
    const createResponse = page.waitForResponse(
      (response) => response.url().endsWith("/resource-scenarios") && response.request().method() === "POST"
    );
    await resource.getByRole("button", { name: "Create from priority" }).click();
    const first = (await (await createResponse).json()) as ResourceScenario;
    expect(first.projects).toHaveLength(3);
    await expect(page.getByRole("grid", { name: "Role Period Capacity Heatmap" })).toContainText("150%");
    const frozen = await apiJson<ResourceScenario>(
      await page.request.post(`${apiUrl}/api/v1/portfolio-resource-scenarios/${first.id}/freeze`, {
        headers: { ...headers, "If-Match": `"${first.revision_version}"` },
        data: { idempotency_key: `${batch!.run_id}-r${fixture.index}-resource-freeze` },
      })
    );
    expect(frozen.status).toBe("FROZEN");
    expect(frozen.readiness.status).toBe("READY");
    const clone = await apiJson<ResourceScenario>(
      await page.request.post(`${apiUrl}/api/v1/portfolio-resource-scenarios/${first.id}/clone`, {
        headers: { ...headers, "If-Match": `"${frozen.revision_version}"` },
        data: { idempotency_key: `${batch!.run_id}-r${fixture.index}-resource-clone` },
      })
    );
    const frozenClone = await apiJson<ResourceScenario>(
      await page.request.post(`${apiUrl}/api/v1/portfolio-resource-scenarios/${clone.id}/freeze`, {
        headers: { ...headers, "If-Match": `"${clone.revision_version}"` },
        data: { idempotency_key: `${batch!.run_id}-r${fixture.index}-resource-clone-freeze` },
      })
    );
    expect(frozenClone.status).toBe("FROZEN");
    const overviewRefresh = page.waitForResponse((response) =>
      response.url().endsWith(`/portfolios/${fixture.main_portfolio.id}/resource-planning`)
    );
    await resource.getByRole("button", { name: /refresh/i }).click();
    await overviewRefresh;
    await resource.getByRole("button", { name: /^comparison$/i }).click();
    const comparison = page.getByRole("region", { name: "Resource Scenario Comparison" });
    await expect(comparison.getByRole("checkbox")).toHaveCount(2);
    await comparison.getByRole("checkbox").nth(0).check();
    await comparison.getByRole("checkbox").nth(1).check();
    await expect(comparison.getByRole("button", { name: "Compare selected" })).toBeEnabled();
    await comparison.getByRole("button", { name: "Compare selected" }).click();
    await expect(comparison.getByText("Role demand delta")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath(`gate07h-user-${fixture.index}.png`), fullPage: true });

    await openAdminResource(page);
    const admin = page.getByRole("region", { name: "Portfolio Resource Planning Configuration" });
    await admin.getByRole("button", { name: new RegExp(published!.name, "i") }).click();
    const actions = page.getByLabel("Portfolio Resource configuration actions");
    const cloneConfigResponse = page.waitForResponse((response) =>
      response.url().endsWith(`/portfolio-resource/admin/configurations/${published!.id}/clone`)
    );
    await actions.getByRole("button", { name: /^clone$/i }).click();
    const configClone = (await (await cloneConfigResponse).json()) as ResourceConfiguration;
    await page.getByLabel("Preview Portfolio").selectOption(String(fixture.main_portfolio.id));
    await page.getByLabel("Demand coverage percentage").fill("90");
    const previewResponse = page.waitForResponse((response) =>
      response.url().endsWith("/portfolio-resource/admin/configurations/preview")
    );
    await actions.getByRole("button", { name: /^preview$/i }).click();
    expect(await apiJson<{ persisted: boolean; publishable: boolean }>(await previewResponse)).toEqual(
      expect.objectContaining({ persisted: false, publishable: true })
    );
    await expect(
      page.getByText(/persisted=false and no capacity, demand or scenario record was created/i)
    ).toBeVisible();
    const saveResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/portfolio-resource/admin/configurations/${configClone.id}`) &&
        response.request().method() === "PUT"
    );
    await actions.getByRole("button", { name: /^save$/i }).click();
    const saved = (await (await saveResponse).json()) as ResourceConfiguration;
    const stale = await page.request.put(`${apiUrl}/api/v1/portfolio-resource/admin/configurations/${configClone.id}`, {
      headers: { ...headers, "If-Match": `"${configClone.version}"` },
      data: { name: saved.name, description: saved.description, content_json: saved.content_json },
    });
    expect(stale.status()).toBe(412);
    for (const forbidden of [
      "Named person allocation",
      "Schedule leveling",
      "Scenario winner",
      "FID approval",
      "Funds assignment",
    ])
      await expect(admin.getByRole("button", { name: new RegExp(forbidden, "i") })).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath(`gate07h-admin-${fixture.index}.png`), fullPage: true });
    const readiness = await apiJson<{ final_output: string; can_enter_resource_recommendation: boolean }>(
      await page.request.get(`${apiUrl}/api/v1/portfolios/${fixture.main_portfolio.id}/resource-planning/readiness`, {
        headers,
      })
    );
    expect(readiness).toEqual(
      expect.objectContaining({
        final_output: "READY_FOR_PORTFOLIO_RESOURCE_RECOMMENDATION",
        can_enter_resource_recommendation: true,
      })
    );
    expect(failedResponses).toEqual([]);
    expect(pageErrors).toEqual([]);
  });
});
