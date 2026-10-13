import { expect, type APIResponse, type Locator, type Page, test } from "@playwright/test";

// Real Chromium -> real API -> isolated PostgreSQL -> actual Celery worker.
// No route interceptions, simulation in the browser or production fixture writes.
const apiUrl = process.env.E2E_API_URL || "http://127.0.0.1:8816";
const baseUrl = process.env.E2E_BASE_URL || "http://127.0.0.1:5519";
const apiRoot = `${apiUrl}/api/v1/qra-engine`;
const password = process.env.E2E_QRA_PASSWORD || "1234";
type Json = Record<string, unknown>;
type Run = Json & {
  id: number;
  run_number: string;
  status: string;
  revision_version: number;
  result_snapshot_hash: string;
  review_status: string;
};
async function json<T>(response: APIResponse, status = 200): Promise<T> {
  expect(response.status(), await response.text()).toBe(status);
  return (await response.json()) as T;
}
async function login(page: Page, user: string) {
  await page.goto("/login");
  await page.getByLabel("User").fill(user);
  await page.getByLabel("Password").fill(password);
  const waiting = page.waitForResponse(
    (response) => response.url().includes("/api/v1/auth/login") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /sign in/i }).click();
  const result = await json<{ access_token: string }>(await waiting);
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
  return result.access_token;
}
async function expand(page: Page, name: string) {
  const item = page
    .getByRole("navigation", { name: "Control Flow" })
    .getByRole("button", { name, exact: true })
    .first();
  if ((await item.getAttribute("aria-expanded")) !== "true") await item.click();
}
async function openEngine(page: Page, projectId: number) {
  await page.goto("/app/strategy/qra-runs");
  const workspace = page.getByRole("region", { name: "QRA Calculation Engine workspace", exact: true });
  await expect(workspace).toBeVisible();
  await workspace.getByRole("combobox", { name: "Project Workspace", exact: true }).selectOption(String(projectId));
  await expect(workspace.getByRole("combobox", { name: "Approved model", exact: true })).toBeEnabled();
  return workspace;
}
async function mutation(page: Page, path: string, button: Locator, status = 200): Promise<Run> {
  const waiting = page.waitForResponse(
    (response) => response.url().endsWith(path) && response.request().method() !== "GET",
    { timeout: 120_000 }
  );
  await button.click();
  return await json<Run>(await waiting, status);
}
async function createRun(page: Page, workspace: Locator, modelId: number, seed: number) {
  await workspace.getByRole("combobox", { name: "Approved model", exact: true }).selectOption(String(modelId));
  await workspace.getByLabel("PRNG seed", { exact: true }).fill(String(seed));
  const previewWaiting = page.waitForResponse(
    (response) => response.url().endsWith(`/models/${modelId}/preflight`) && response.request().method() === "GET"
  );
  await workspace.getByRole("button", { name: "Validate pre-run", exact: true }).click();
  const preview = await json<Json>(await previewWaiting);
  expect(preview.eligible).toBe(true);
  expect(preview.persisted).toBe(false);
  expect(preview.blockers).toEqual([]);
  return await mutation(
    page,
    `/api/v1/qra-engine/models/${modelId}/runs`,
    workspace.getByRole("button", { name: "Create governed run", exact: true }),
    201
  );
}
async function executeRun(page: Page, workspace: Locator, run: Run, token: string) {
  await mutation(
    page,
    `/api/v1/qra-engine/runs/${run.id}/execute`,
    workspace.getByRole("button", { name: "Execute approved run", exact: true })
  );
  await expect(workspace.getByRole("progressbar", { name: "Run iteration progress" })).toBeVisible();
  await expect
    .poll(
      async () => {
        const response = await page.request.get(`${apiRoot}/runs/${run.id}/status`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        return (await json<Run>(response)).status;
      },
      { timeout: 180_000, intervals: [500, 1000, 2000] }
    )
    .toBe("COMPLETED");
  const selected = workspace.getByRole("combobox", { name: "Selected QRA run", exact: true });
  await expect(selected).toHaveValue(String(run.id));
  await expect(selected.locator(`option[value="${run.id}"]`)).toContainText("COMPLETED", {
    timeout: 30_000,
  });
  const completed = await json<Run>(
    await page.request.get(`${apiRoot}/runs/${run.id}?summary=true`, { headers: { Authorization: `Bearer ${token}` } })
  );
  expect(completed.result_snapshot_hash).toMatch(/^[a-f0-9]{64}$/);
  return completed;
}
test.use({ trace: "on" });
test.describe.serial("QRA Wave 4 actual worker governed browser release", () => {
  test("read-only USER cannot execute or configure approved models", async ({ page }, testInfo) => {
    test.setTimeout(300_000);
    const token = await login(page, "qra.engine.reader@demo.local");
    const headers = { Authorization: `Bearer ${token}` };
    const options = await json<{ projects: Array<{ id: number; code: string; name: string }> }>(
      await page.request.get(`${apiUrl}/api/v1/qra-foundation/options`, { headers })
    );
    const project = options.projects.find((item) => /QRA Foundation|QRA-PROJECT/.test(item.name + item.code));
    expect(project).toBeTruthy();
    const workspace = await openEngine(page, project!.id);
    for (const name of [
      "Create governed run",
      "Execute approved run",
      "Cancel run",
      "Submit result for review",
      "Accept analysis evidence",
    ])
      await expect(workspace.getByRole("button", { name, exact: true })).toHaveCount(0);
    const models = await json<{ approved_models: Array<{ id: number }> }>(
      await page.request.get(`${apiRoot}/projects/${project!.id}/options`, { headers })
    );
    expect(models.approved_models[0]).toBeTruthy();
    const denied = await page.request.post(`${apiRoot}/models/${models.approved_models[0].id}/runs`, {
      headers: { ...headers, "Idempotency-Key": `qra-reader-denied-${Date.now()}` },
      data: { seed: 1, iterations: 1024 },
    });
    expect(denied.status()).toBe(403);
    await page.screenshot({ path: testInfo.outputPath("qra-engine-read-only.png"), fullPage: true });
    await workspace.screenshot({ path: testInfo.outputPath("qra-engine-read-only-focused.png") });
    await page.goto("/app/admin/strategy/qra-methodology-source-readiness");
    await expect(page.getByRole("region", { name: "QRA Methodology & Source Readiness", exact: true })).toHaveCount(0);
  });
  test("ADMIN execution governance uses the existing QRA methodology editor without a duplicate manager or run controls", async ({
    page,
  }, testInfo) => {
    test.setTimeout(300_000);
    const token = await login(page, "admin");
    const headers = { Authorization: `Bearer ${token}` };
    const projectOptions = await json<{ projects: Array<{ id: number; name: string; code: string }> }>(
      await page.request.get(`${apiUrl}/api/v1/qra-foundation/options`, { headers })
    );
    const project = process.env.E2E_QRA_ENGINE_PROJECT_ID
      ? projectOptions.projects.find((item) => item.id === Number(process.env.E2E_QRA_ENGINE_PROJECT_ID))
      : projectOptions.projects
          .filter((item) => /QRA Foundation|QRA-PROJECT/.test(item.name + item.code))
          .sort((a, b) => b.id - a.id)[0];
    expect(project).toBeTruthy();
    const options = await json<{ configuration: { id: number }; engine_policy: Json }>(
      await page.request.get(`${apiRoot}/projects/${project!.id}/options`, { headers })
    );
    await page.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }).click();
    await page.goto("/app/admin/strategy/qra-methodology-source-readiness");
    const admin = page.getByRole("region", { name: "QRA Methodology & Source Readiness", exact: true });
    await expect(admin).toBeVisible();
    await expect(
      admin.getByRole("navigation", { name: "QRA Methodology & Source Readiness governed sections", exact: true })
    ).toContainText("Execution Policy");
    await expect(
      admin.getByRole("button", { name: /Execute approved run|Accept analysis evidence|Create governed run/ })
    ).toHaveCount(0);
    const configuration = admin.locator(`[data-configuration-id="${options.configuration.id}"]`);
    const clone = await mutation(
      page,
      `/api/v1/qra-foundation/admin/configurations/${options.configuration.id}/clone`,
      configuration.getByRole("button", { name: "Clone to DRAFT", exact: true }),
      201
    );
    const draft = admin.locator(`[data-configuration-id="${clone.id}"]`);
    await draft.getByRole("button", { name: "Edit policy", exact: true }).click();
    const editor = admin.getByRole("region", { name: "Edit QRA Methodology & Source Readiness", exact: true });
    await editor
      .getByRole("navigation", { name: "Policy section editor", exact: true })
      .getByRole("button", { name: "Execution Policy", exact: true })
      .click();
    const field = editor.getByRole("textbox", { name: "Governed policy section JSON", exact: true });
    const policy = JSON.parse(await field.inputValue()) as Json;
    expect(policy.engine_version).toBe("wave4-qra-v1");
    expect(policy.schedule_method).toBe("NORMALIZED_ELAPSED_TIME_V1");
    const modified = { ...policy, histogram_bins: 14 };
    await field.fill(JSON.stringify(modified));
    const saved = await mutation(
      page,
      `/api/v1/qra-foundation/admin/configurations/${clone.id}`,
      editor.getByRole("button", { name: "Save DRAFT revision", exact: true })
    );
    expect((saved.content_json as Json).reserved_engine_settings).toEqual(modified);
    expect(saved.status).toBe("draft");
    const unchanged = await json<{ engine_policy: Json }>(
      await page.request.get(`${apiRoot}/projects/${project!.id}/options`, { headers })
    );
    expect(unchanged.engine_policy).toEqual(options.engine_policy);
    await page.screenshot({ path: testInfo.outputPath("qra-engine-admin-draft-policy.png"), fullPage: true });
    await draft.getByRole("button", { name: "Edit policy", exact: true }).click();
    await editor
      .getByRole("navigation", { name: "Policy section editor", exact: true })
      .getByRole("button", { name: "Execution Policy", exact: true })
      .click();
    await expect(field).toHaveValue(JSON.stringify(modified, null, 2));
    await editor.screenshot({ path: testInfo.outputPath("qra-engine-admin-draft-policy-focused.png") });
  });
  test("USER execution, reproducible cost results, schedule dates, comparison, cancellation and independent acceptance", async ({
    page,
    browser,
  }, testInfo) => {
    test.setTimeout(900_000);
    const token = await login(page, "admin");
    const headers = { Authorization: `Bearer ${token}` };
    const projectOptions = await json<{ projects: Array<{ id: number; name: string; code: string }> }>(
      await page.request.get(`${apiUrl}/api/v1/qra-foundation/options`, { headers })
    );
    const project = process.env.E2E_QRA_ENGINE_PROJECT_ID
      ? projectOptions.projects.find((item) => item.id === Number(process.env.E2E_QRA_ENGINE_PROJECT_ID))
      : projectOptions.projects
          .filter((item) => /QRA Foundation|QRA-PROJECT/.test(item.name + item.code))
          .sort((a, b) => b.id - a.id)[0];
    expect(
      project,
      "Provision isolated Wave4 approved Cost/Schedule models before the browser release gate"
    ).toBeTruthy();
    await expand(page, "Enterprise Strategy Manager");
    await expand(page, "Business Case & Investment Development");
    await expand(page, "QRA");
    await page
      .getByRole("navigation", { name: "Control Flow" })
      .getByRole("button", { name: "Runs", exact: true })
      .first()
      .click();
    await expect(page).toHaveURL(/\/app\/strategy\/qra-runs$/);
    const workspace = await openEngine(page, project!.id);
    await expect(
      workspace.getByRole("button", { name: /Publish|Clone to DRAFT|Approve FID|Edit methodology/i })
    ).toHaveCount(0);
    const options = await json<{
      approved_models: Array<{ id: number; analysis_type: string }>;
      no_new_admin_module_required: boolean;
    }>(await page.request.get(`${apiRoot}/projects/${project!.id}/options`, { headers }));
    expect(options.no_new_admin_module_required).toBe(true);
    const costModel = options.approved_models.find((item) => item.analysis_type === "COST_QRA");
    const scheduleModel = options.approved_models.find((item) => item.analysis_type === "SCHEDULE_QRA");
    expect(costModel).toBeTruthy();
    expect(scheduleModel).toBeTruthy();
    const first = await createRun(page, workspace, costModel!.id, 2026);
    const firstResult = await executeRun(page, workspace, first, token);
    await workspace
      .getByRole("navigation", { name: "QRA execution views", exact: true })
      .getByRole("button", { name: "Run Overview", exact: true })
      .click();
    await expect(workspace.getByRole("img", { name: "Simulated outcome histogram" })).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("qra-engine-completed-cost.png"), fullPage: true });
    await workspace
      .locator(".qraResultChart")
      .first()
      .screenshot({ path: testInfo.outputPath("qra-engine-cost-histogram.png") });
    for (const [section, table] of [
      ["Percentiles", "Backend-governed percentiles"],
      ["Sensitivity / Drivers", "Backend-governed sensitivity"],
    ] as const) {
      await workspace
        .getByRole("navigation", { name: "QRA execution views", exact: true })
        .getByRole("button", { name: section, exact: true })
        .click();
      await expect(workspace.getByRole("table", { name: table, exact: true })).toBeVisible();
    }
    await workspace
      .getByRole("navigation", { name: "QRA execution views", exact: true })
      .getByRole("button", { name: "Convergence", exact: true })
      .click();
    await expect(workspace.getByRole("article", { name: "QRA Convergence", exact: true })).toContainText(
      /CONVERGED|NOT_CONVERGED|NOT_EVALUATED/
    );
    const second = await createRun(page, workspace, costModel!.id, 2026);
    const secondResult = await executeRun(page, workspace, second, token);
    expect(secondResult.result_snapshot_hash).toBe(firstResult.result_snapshot_hash);
    expect(second.id).not.toBe(first.id);
    const third = await createRun(page, workspace, costModel!.id, 2027);
    const thirdResult = await executeRun(page, workspace, third, token);
    expect(thirdResult.result_snapshot_hash).not.toBe(firstResult.result_snapshot_hash);
    await workspace
      .getByRole("navigation", { name: "QRA execution views", exact: true })
      .getByRole("button", { name: "Run Comparison", exact: true })
      .click();
    await workspace.getByRole("combobox", { name: "Compare against run", exact: true }).selectOption(String(first.id));
    await workspace.getByRole("button", { name: "Compare governed runs", exact: true }).click();
    await expect(workspace.getByRole("article", { name: "QRA run selection", exact: true })).toContainText(
      '"compatible": true'
    );
    const schedule = await createRun(page, workspace, scheduleModel!.id, 2026);
    await executeRun(page, workspace, schedule, token);
    await workspace
      .getByRole("navigation", { name: "QRA execution views", exact: true })
      .getByRole("button", { name: "Schedule Results", exact: true })
      .click();
    await expect(workspace.getByRole("table", { name: "QRA milestone distributions", exact: true })).toContainText(
      "A-FINISH"
    );
    await workspace
      .getByRole("navigation", { name: "QRA execution views", exact: true })
      .getByRole("button", { name: "Percentiles", exact: true })
      .click();
    await expect(workspace.getByRole("table", { name: "Backend-governed percentiles", exact: true })).toContainText(
      "completion_date"
    );
    await page.screenshot({ path: testInfo.outputPath("qra-engine-completed-schedule.png"), fullPage: true });
    await workspace
      .getByRole("table", { name: "Backend-governed percentiles", exact: true })
      .screenshot({ path: testInfo.outputPath("qra-engine-schedule-percentiles.png") });
    const cancelled = await createRun(page, workspace, costModel!.id, 99);
    const cancelResult = await mutation(
      page,
      `/api/v1/qra-engine/runs/${cancelled.id}/cancel`,
      workspace.getByRole("button", { name: "Cancel run", exact: true })
    );
    expect(cancelResult.status).toBe("CANCELLED");
    const noFinal = await page.request.get(`${apiRoot}/runs/${cancelled.id}/summary`, { headers });
    expect(noFinal.status()).toBe(409);
    await workspace
      .getByRole("navigation", { name: "QRA execution views", exact: true })
      .getByRole("button", { name: "History", exact: true })
      .click();
    await workspace.getByRole("combobox", { name: "Selected QRA run", exact: true }).selectOption(String(first.id));
    await expect(workspace.getByRole("article", { name: "QRA History", exact: true })).toContainText(
      firstResult.result_snapshot_hash
    );
    await expect(workspace.getByRole("button", { name: "Accept analysis evidence", exact: true })).toHaveCount(0);

    const independent = await browser.newContext({ baseURL: baseUrl });
    const authorityPage = await independent.newPage();
    const authorityToken = await login(authorityPage, "qra.engine.authority@demo.local");
    const reviewer = await openEngine(authorityPage, project!.id);
    await reviewer.getByRole("combobox", { name: "Selected QRA run", exact: true }).selectOption(String(first.id));
    await reviewer
      .getByLabel("Run / review comments", { exact: true })
      .fill("Independent acceptance as analytical evidence; not investment approval.");
    await mutation(
      authorityPage,
      `/api/v1/qra-engine/runs/${first.id}/review`,
      reviewer.getByRole("button", { name: "Submit result for review", exact: true })
    );
    const accepted = await mutation(
      authorityPage,
      `/api/v1/qra-engine/runs/${first.id}/accept`,
      reviewer.getByRole("button", { name: "Accept analysis evidence", exact: true })
    );
    expect(accepted.review_status).toBe("ACCEPTED");
    await reviewer
      .getByRole("navigation", { name: "QRA execution views", exact: true })
      .getByRole("button", { name: "Evidence / Traceability", exact: true })
      .click();
    await expect(reviewer.getByRole("article", { name: "QRA Evidence / Traceability", exact: true })).toContainText(
      '"status": "AVAILABLE"'
    );
    const provider = await json<Json>(
      await authorityPage.request.get(`${apiRoot}/projects/${project!.id}/provider-evidence?analysis_type=COST_QRA`, {
        headers: { Authorization: `Bearer ${authorityToken}` },
      })
    );
    expect(provider.status).toBe("AVAILABLE");
    expect(provider.not_investment_approval).toBe(true);
    expect(provider.raw_samples).toBe("NOT_EXPOSED");
    await authorityPage.screenshot({
      path: testInfo.outputPath("qra-engine-independent-acceptance.png"),
      fullPage: true,
    });
    await reviewer
      .locator(".qraRunMetadata")
      .screenshot({ path: testInfo.outputPath("qra-engine-accepted-metadata.png") });
    await independent.close();
  });
});
