import { expect, type APIResponse, type Locator, type Page, test } from "@playwright/test";

// Supplemental release UAT against real Chromium -> API -> isolated PostgreSQL.
// No route mocks, fixture status patches, policy publication or live decisions.
const api = process.env.E2E_API_URL || "http://127.0.0.1:8830";
const password = process.env.E2E_QRA_PASSWORD || "1234";
type Json = Record<string, unknown>;
type Measurement = { operation: string; elapsed_ms: number; status: number; observation: string };

async function body<T>(response: APIResponse): Promise<T> {
  expect(response.status(), await response.text()).toBe(200);
  return (await response.json()) as T;
}

async function login(page: Page, user = "admin") {
  await page.goto("/login");
  await page.getByLabel("User", { exact: true }).fill(user);
  await page.getByLabel("Password", { exact: true }).fill(password);
  const response = page.waitForResponse(
    (result) => result.url().includes("/api/v1/auth/login") && result.request().method() === "POST"
  );
  await page.getByRole("button", { name: /sign in/i }).click();
  expect((await response).status()).toBe(200);
  const result = (await (await response).json()) as { access_token: string };
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
  return result.access_token;
}

async function expand(button: Locator) {
  await expect(button).toBeVisible();
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
  await expect(button).toHaveAttribute("aria-expanded", "true");
}

async function timedGet<T>(page: Page, token: string, endpoint: string, operation: string, timings: Measurement[]) {
  const started = performance.now();
  const response = await page.request.get(`${api}${endpoint}`, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 120_000,
  });
  const result = await body<T>(response);
  timings.push({
    operation,
    elapsed_ms: Math.round((performance.now() - started) * 1000) / 1000,
    status: response.status(),
    observation: "Single local request including JSON parsing; not an SLA, load test or percentile benchmark.",
  });
  return result;
}

test.use({ trace: "on" });
test.describe.serial("Strategic final UAT supplemental real stack", () => {
  test("ADMIN Composition Rules resolves the reusable rule editor, with keyboard access and no Project creation form", async ({
    page,
  }, testInfo) => {
    await login(page);
    await page.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }).click();
    await page.goto("/app/admin/strategy/enterprise-workspace-structure");
    const surface = page.locator('[data-strategic-view="enterprise-workspace-structure"]');
    await expect(surface).toHaveAttribute("data-control-classification", "ADMIN_CONFIGURATION");
    await expect(
      surface.getByRole("heading", { name: "Enterprise Structure Configuration", exact: true })
    ).toBeVisible();
    await expect(surface.getByRole("button", { name: "Reglas de composición", exact: true })).toHaveClass(/active/);
    const allowed = surface.getByRole("group", { name: "Tipos hijo permitidos", exact: true });
    await expect(allowed).toBeVisible();
    expect(await allowed.getByRole("checkbox").count()).toBeGreaterThan(0);
    const maximumDepth = surface.getByRole("spinbutton", { name: "Profundidad máxima", exact: true });
    await maximumDepth.focus();
    await expect(maximumDepth).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(surface.getByRole("checkbox", { name: "Puede ser raíz", exact: true })).toBeFocused();
    await expect(surface.getByRole("button", { name: "Guardar regla", exact: true })).toBeVisible();
    await expect(
      surface.getByRole("button", { name: /Nuevo nodo|Create Project|Guardar solicitud y previsualizar/i })
    ).toHaveCount(0);
    await expect(surface.getByRole("radiogroup", { name: "Modelo de gobierno", exact: true })).toHaveCount(0);
    const breadcrumb = surface.getByRole("navigation", { name: "Strategic workflow breadcrumb", exact: true });
    await expect(breadcrumb).toContainText("Enterprise Foundation");
    await expect(breadcrumb.locator('[aria-current="page"]')).toHaveText(/Composition Rules/);
    await page.screenshot({ path: testInfo.outputPath("admin-composition-rules.png"), fullPage: true });
  });

  test("USER Review follows Scenario Convergence and remains keyboard navigable with contextual breadcrumb and mobile view", async ({
    page,
  }, testInfo) => {
    await login(page);
    const navigation = page.getByRole("navigation", { name: /validation focus|control flow/i });
    await expand(navigation.getByRole("button", { name: "Enterprise Strategy Manager", exact: true }));
    const modules = navigation.getByRole("group", { name: "Módulos de Enterprise Strategy Manager", exact: true });
    await expand(modules.getByRole("button", { name: "Portfolio Scenario Planning", exact: true }));
    const submodules = modules.getByRole("group", { name: "Submódulos de Portfolio Scenario Planning", exact: true });
    const direct = submodules.locator(":scope > .navigatorViewBranch > button");
    await expect(direct).toHaveText([
      "Budget Planning & Scenarios",
      "Resource Planning & Scenarios",
      "Scenario Convergence & Recommendation",
      "Periodic Portfolio Review",
    ]);
    const review = submodules.getByRole("button", { name: "Periodic Portfolio Review", exact: true });
    await review.focus();
    await expect(review).toBeFocused();
    const navigationStarted = performance.now();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/app\/strategy\/portfolio-review-sessions$/);
    const surface = page.locator('[data-strategic-view="portfolio-review-sessions"]');
    await expect(surface).toBeVisible();
    await testInfo.attach("local-navigation-measurement.json", {
      body: Buffer.from(
        JSON.stringify(
          {
            operation: "Keyboard activation of Periodic Portfolio Review",
            elapsed_ms: Math.round((performance.now() - navigationStarted) * 1000) / 1000,
            route: new URL(page.url()).pathname,
            observation: "Local keyboard action to visible route surface, not full data hydration or production SLA.",
          },
          null,
          2
        )
      ),
      contentType: "application/json",
    });
    await expect(surface).toHaveAttribute("data-control-classification", "USER_TRANSACTION");
    const breadcrumb = surface.getByRole("navigation", { name: "Strategic workflow breadcrumb", exact: true });
    await expect(breadcrumb).toContainText("Portfolio Scenario Planning");
    await expect(breadcrumb).toContainText("Periodic Portfolio Review");
    await expect(surface.getByRole("button", { name: /Publish policy|Edit policy/i })).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath("user-review-after-convergence.png"), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(breadcrumb.locator('[aria-current="page"]')).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("user-review-mobile.png"), fullPage: true });
  });

  test("non-configuring reader cannot enter ADMIN; generic ADMIN Project Workspace POST is rejected without creating a canonical Workspace", async ({
    page,
  }, testInfo) => {
    await login(page, "qra.evidence.reader@demo.local");
    await expect(page.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true })).toBeDisabled();
    await page.goto("/app/admin/strategy/enterprise-workspace-structure");
    await expect(page.getByRole("alert", { name: "Strategic configuration access denied", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Guardar regla", exact: true })).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath("reader-admin-denied.png"), fullPage: true });
    const token = await login(page);
    const headers = { Authorization: `Bearer ${token}` };
    const before = await body<{ nodes: Json[] }>(
      await page.request.get(`${api}/api/v1/enterprise-structure/overview`, { headers })
    );
    const rejected = await page.request.post(`${api}/api/v1/admin-configuration/workspaces`, {
      headers,
      data: {
        code: `UAT-GENERIC-DENIED-${Date.now()}`,
        name: "Must not create a Project Workspace through generic ADMIN",
        workspace_type_code: "project",
      },
    });
    expect(rejected.status(), await rejected.text()).toBe(409);
    const rejection = await rejected.json();
    expect(rejection.detail.code).toBe("PROJECT_CREATION_PROCESS_REQUIRED");
    const after = await body<{ nodes: Json[] }>(
      await page.request.get(`${api}/api/v1/enterprise-structure/overview`, { headers })
    );
    expect(after.nodes).toEqual(before.nodes);
    await testInfo.attach("generic-admin-project-negative.json", {
      body: Buffer.from(
        JSON.stringify(
          {
            status: rejected.status(),
            rejection,
            canonical_workspaces_before: before.nodes.length,
            canonical_workspaces_after: after.nodes.length,
            unchanged: true,
            boundary:
              "Canonical enterprise_workspaces only. Operational legacy /projects is outside this strategic UAT and remains untouched.",
          },
          null,
          2
        )
      ),
      contentType: "application/json",
    });
  });

  test("Explorer, Gate, BC, frozen history and policy dry-run retain real context and expose measured local read timings", async ({
    page,
  }, testInfo) => {
    test.setTimeout(360_000);
    const token = await login(page);
    const timings: Measurement[] = [];
    const preparations = await timedGet<Json[]>(
      page,
      token,
      "/api/v1/investment-gate-preparations",
      "Gate preparation register",
      timings
    );
    const frozen = preparations.find((item) => item.status === "FROZEN");
    expect(frozen).toBeTruthy();
    const portfolioId = Number(frozen!.portfolio_workspace_id);
    const cases = await timedGet<Json[]>(page, token, "/api/v1/business-cases", "Business Case register", timings);
    expect(cases.length).toBeGreaterThan(0);
    const caseId = Number(cases[0].id);
    const projectId = Number(cases[0].project_workspace_id);
    const notMeasured: string[] = [];
    for (const analysisType of ["COST_QRA", "SCHEDULE_QRA"]) {
      const provider = await timedGet<Json>(
        page,
        token,
        `/api/v1/qra-engine/projects/${projectId}/provider-evidence?analysis_type=${analysisType}`,
        `${analysisType} evidence resolution`,
        timings
      );
      expect(provider.status).toBe("AVAILABLE");
      expect(provider.project_id).toBe(projectId);
      expect(provider.analysis_type).toBe(analysisType);
    }
    const reviewRegister = await timedGet<{ items: Json[] }>(
      page,
      token,
      `/api/v1/portfolio-reviews?portfolio_workspace_id=${portfolioId}`,
      "Portfolio Review session register",
      timings
    );
    if (reviewRegister.items.length) {
      await timedGet<Json>(
        page,
        token,
        `/api/v1/portfolio-reviews/${reviewRegister.items[0].id}/project-matrix`,
        "Portfolio Review Project Matrix",
        timings
      );
    } else {
      notMeasured.push(
        "Portfolio Review Project Matrix: no existing session in the isolated fixture; no session invented by this read-only smoke."
      );
    }
    const historicalBc = await timedGet<Json[]>(
      page,
      token,
      `/api/v1/business-cases/${caseId}/revisions`,
      "Business Case historical revisions",
      timings
    );
    const policyBefore = await timedGet<Json[]>(
      page,
      token,
      "/api/v1/investment-evidence-policy/configurations",
      "Policy revision history",
      timings
    );
    await timedGet<Json>(page, token, "/api/v1/enterprise-structure/overview", "Enterprise Explorer", timings);
    await page.goto("/app/strategy/enterprise-explorer");
    await expect(page.getByRole("heading", { name: "Enterprise Explorer", exact: true })).toBeVisible();
    const search = page.getByRole("textbox", { name: "Buscar por código o nombre", exact: true });
    await search.focus();
    await expect(search).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("combobox", { name: "Filtrar por tipo", exact: true })).toBeFocused();
    await expect(page.getByRole("button", { name: "Create Project", exact: true })).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("enterprise-explorer-context.png"), fullPage: true });

    await timedGet<Json>(
      page,
      token,
      `/api/v1/portfolios/${portfolioId}/investment-gate-preparation`,
      "Gate Portfolio overview",
      timings
    );
    await page.goto("/app/strategy/investment-gate-preparation");
    const gate = page.getByRole("region", { name: "Investment Gate Preparation", exact: true });
    await expect(gate).toBeVisible();
    await gate.getByRole("combobox", { name: /^Portfolio/ }).selectOption(String(portfolioId));
    await gate.getByRole("combobox", { name: /^Preparation/ }).selectOption(String(frozen!.id));
    await expect(gate).toContainText("FROZEN");
    await gate.getByRole("button", { name: "Evidence Package", exact: true }).click();
    await page.screenshot({ path: testInfo.outputPath("gate-frozen-historical-read.png"), fullPage: true });

    await page.goto("/app/strategy/business-case-my");
    const business = page.getByRole("region", { name: "Business Case Manager", exact: true });
    await expect(business).toBeVisible();
    await business.getByRole("combobox", { name: /^Business Case/ }).selectOption(String(caseId));
    await business.getByRole("button", { name: "Sources & Evidence", exact: true }).click();
    await page.screenshot({ path: testInfo.outputPath("business-case-captured-sources.png"), fullPage: true });

    await page.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }).click();
    await page.goto("/app/admin/strategy/investment-decision-evidence-policy");
    const admin = page.getByRole("region", { name: "Evidence & Decision Policy", exact: true });
    await expect(admin).toBeVisible();
    const published =
      policyBefore.find(
        (item) =>
          item.status === "published" &&
          (item.content_json as Json).scope &&
          ((item.content_json as Json).scope as Json).workspace_id === portfolioId
      ) || policyBefore.find((item) => item.status === "published");
    expect(published).toBeTruthy();
    await admin.getByLabel("Policy revision", { exact: true }).selectOption(String(published!.id));
    await admin.getByLabel("Evidence policy Portfolio", { exact: true }).selectOption(String(portfolioId));
    await admin.getByLabel("Investment Gate Profile", { exact: true }).selectOption("PYP-FFA");
    const waiting = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/configurations/${published!.id}/preview`) && response.request().method() === "POST"
    );
    const started = performance.now();
    await admin
      .getByRole("group", { name: "Evidence policy actions", exact: true })
      .getByRole("button", { name: "Preview", exact: true })
      .click();
    const previewResponse = await waiting;
    expect(previewResponse.status()).toBe(200);
    const preview = (await previewResponse.json()) as Json;
    expect(preview.persisted).toBe(false);
    timings.push({
      operation: "Policy preview via actual UI",
      elapsed_ms: Math.round((performance.now() - started) * 1000) / 1000,
      status: previewResponse.status(),
      observation: "One local browser click -> API -> PostgreSQL dry-run response; persisted=false. Not an SLA.",
    });
    await expect(admin.getByRole("status")).toContainText("persisted=false");
    await admin.getByRole("button", { name: "History", exact: true }).click();
    await expect(admin).toContainText(String(published!.content_hash).slice(0, 18));
    await page.screenshot({ path: testInfo.outputPath("policy-historical-read-only.png"), fullPage: true });
    const policyAfter = await timedGet<Json[]>(
      page,
      token,
      "/api/v1/investment-evidence-policy/configurations",
      "Policy history after preview",
      timings
    );
    expect(policyAfter).toEqual(policyBefore);
    const preparationsAfter = await timedGet<Json[]>(
      page,
      token,
      "/api/v1/investment-gate-preparations",
      "Gate register after read-only UAT",
      timings
    );
    const frozenHistory = (rows: Json[]) =>
      rows
        .filter((item) => item.status === "FROZEN")
        .map((item) => ({
          id: item.id,
          status: item.status,
          revision_version: item.revision_version,
          preparation_hash: item.preparation_hash,
          preparation_source_hash: item.preparation_source_hash,
          profile_hash: item.profile_hash,
          source_snapshot: item.source_snapshot,
          evidence: item.evidence,
        }));
    // Active readiness may include evaluation timestamps. Compare immutable
    // captured historical packages rather than conflating that live projection
    // with a persisted mutation. Separate SQL guard tests verify zero DML.
    expect(frozenHistory(preparationsAfter)).toEqual(frozenHistory(preparations));
    const bcAfter = await timedGet<Json[]>(
      page,
      token,
      `/api/v1/business-cases/${caseId}/revisions`,
      "BC history after read-only UAT",
      timings
    );
    expect(bcAfter).toEqual(historicalBc);
    await testInfo.attach("local-read-measurements.json", {
      body: Buffer.from(
        JSON.stringify(
          {
            recorded_at_utc: new Date().toISOString(),
            api,
            base_url: process.env.E2E_BASE_URL,
            portfolio_id: portfolioId,
            historical_preparation_id: frozen!.id,
            business_case_id: caseId,
            policy_id: published!.id,
            measurements: timings,
            not_measured: notMeasured,
            history_unchanged: true,
            limitation:
              "Supplemental technical UAT; does not assert full Capital Owner lifecycle or human business acceptance.",
          },
          null,
          2
        )
      ),
      contentType: "application/json",
    });
  });
});
