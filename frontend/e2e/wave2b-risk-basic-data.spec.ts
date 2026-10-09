import { expect, type APIResponse, type Locator, type Page, test } from "@playwright/test";

// Real browser + backend + disposable PostgreSQL fixture. No API interception.
const apiUrl = process.env.E2E_API_URL || "http://127.0.0.1:8814";
const preparer = process.env.E2E_WAVE2B_PREPARER_EMAIL || "admin";
const authority = process.env.E2E_WAVE2B_AUTHORITY_EMAIL || "wave2b.authority@demo.local";
const userOnly = process.env.E2E_WAVE2B_USER_EMAIL || "wave2b.user@demo.local";
const password = process.env.E2E_WAVE2B_PASSWORD || "1234";
type Assessment = {
  id: number;
  status: string;
  assessment_number: string;
  assessment_hash: string;
  snapshot_json: Record<string, unknown>;
};
type Configuration = { id: number; name: string; status: string; content_json: Record<string, unknown> };
async function json<T>(response: APIResponse, expected = 200): Promise<T> {
  expect(response.status(), await response.text()).toBe(expected);
  return (await response.json()) as T;
}
async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("User").fill(email);
  await page.getByLabel("Password").fill(password);
  const waiting = page.waitForResponse(
    (response) => response.url().includes("/api/v1/auth/login") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /sign in/i }).click();
  const result = await json<{ access_token: string }>(await waiting);
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
  return result.access_token;
}
async function expand(page: Page, name: string, label = "Control Flow") {
  const button = page.getByRole("navigation", { name: label }).getByRole("button", { name, exact: true }).first();
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
}
async function openBasicData(page: Page) {
  await expand(page, "Enterprise Strategy Manager");
  await expand(page, "Business Case & Investment Development");
  await page
    .getByRole("navigation", { name: "Control Flow" })
    .getByRole("button", { name: "Basic Data Readiness", exact: true })
    .click();
  await expect(page).toHaveURL(/\/app\/strategy\/basic-data-readiness$/);
  return page.getByRole("region", { name: "Basic Data Readiness workspace" });
}
async function mutation(page: Page, path: string, button: Locator, expected = 200) {
  const waiting = page.waitForResponse(
    (response) => response.url().endsWith(path) && response.request().method() !== "GET",
    { timeout: 120_000 }
  );
  await button.click();
  return await json<Record<string, unknown>>(await waiting, expected);
}
test.use({ trace: "on" });
test.describe("Wave 2B real governed Risk policy and Basic Data", () => {
  test("USER maintains technical references, separate validation, assessment and immutable history", async ({
    page,
    browser,
  }) => {
    test.setTimeout(720_000);
    const token = await login(page, preparer);
    const headers = { Authorization: `Bearer ${token}` };
    const options = await json<{
      projects: Array<{ id: number; code: string; name: string }>;
      quality_values: string[];
      confidence_values: string[];
    }>(await page.request.get(`${apiUrl}/api/v1/basic-data/options`, { headers }));
    const project = process.env.E2E_WAVE2B_PROJECT_ID
      ? options.projects.find((item) => item.id === Number(process.env.E2E_WAVE2B_PROJECT_ID))
      : options.projects.find((item) => /wave.?2b/i.test(item.name + item.code));
    expect(project, "Provision dedicated Wave 2B Project Workspace fixture").toBeTruthy();
    const requirements = await json<{
      context: Record<string, unknown>;
      requirements: Array<{ requirement_code: string; name: string }>;
    }>(await page.request.get(`${apiUrl}/api/v1/basic-data/projects/${project!.id}/requirements`, { headers }));
    expect(requirements.requirements.length).toBeGreaterThan(0);
    const contextBefore = JSON.stringify(requirements.context);
    const workspace = await openBasicData(page);
    await workspace.getByRole("combobox", { name: "Project Workspace", exact: true }).selectOption(String(project!.id));
    await expect(workspace.getByRole("button", { name: /Clone to DRAFT|Publish/ })).toHaveCount(0);
    await workspace.getByRole("button", { name: "Requirements", exact: true }).click();
    await expect(workspace).toContainText(`exact denominator ${requirements.requirements.length}`);
    await workspace.getByRole("button", { name: "Basic Data Register", exact: true }).click();
    const existing = await json<{ items: Array<{ requirement_code: string }> }>(
      await page.request.get(`${apiUrl}/api/v1/basic-data/projects/${project!.id}/items?page_size=200`, { headers })
    );
    for (const requirement of requirements.requirements.filter(
      (item) => !existing.items.some((row) => row.requirement_code === item.requirement_code)
    )) {
      await workspace.getByRole("button", { name: "Add Basic Data item", exact: true }).click();
      const editor = workspace.getByRole("article", { name: "Basic Data item editor" });
      await editor
        .getByRole("combobox", { name: "Requirement", exact: true })
        .selectOption(requirement.requirement_code);
      await editor.getByRole("combobox", { name: "Availability", exact: true }).selectOption("AVAILABLE");
      const quality = options.quality_values.includes("VALIDATED")
        ? "VALIDATED"
        : options.quality_values.includes("VERIFIED")
          ? "VERIFIED"
          : options.quality_values.includes("ACCEPTABLE")
            ? "ACCEPTABLE"
            : options.quality_values.at(-1)!;
      await editor.getByRole("combobox", { name: "Quality", exact: true }).selectOption(quality);
      await editor.getByRole("combobox", { name: "Confidence", exact: true }).selectOption("HIGH");
      await editor.getByLabel("Evidence reference", { exact: true }).fill(`STUDY-W2B-${requirement.requirement_code}`);
      await editor.getByLabel("Source version", { exact: true }).fill("1");
      await editor.getByLabel("Source date", { exact: true }).fill(new Date().toISOString().slice(0, 10));
      await mutation(
        page,
        `/api/v1/basic-data/projects/${project!.id}/items`,
        editor.getByRole("button", { name: "Save Basic Data item" }),
        201
      );
      await expect(workspace).toContainText(`STUDY-W2B-${requirement.requirement_code}`);
    }
    const reviewContext = await browser.newContext({ baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:5517" });
    const reviewerPage = await reviewContext.newPage();
    const reviewerToken = await login(reviewerPage, authority);
    const reviewer = await openBasicData(reviewerPage);
    await reviewer.getByRole("combobox", { name: "Project Workspace", exact: true }).selectOption(String(project!.id));
    await reviewer.getByRole("button", { name: "Validation", exact: true }).click();
    for (const requirement of requirements.requirements) {
      await reviewer.getByRole("button", { name: `Validate ${requirement.requirement_code}`, exact: true }).click();
      await expect(reviewer).toContainText("Item validation recorded with reviewer metadata.");
    }
    await workspace.getByRole("button", { name: "Refresh current context", exact: true }).click();
    for (const view of ["Gaps", "Readiness", "FEL / PDRI Context", "Evidence Sources", "History"]) {
      await workspace.getByRole("button", { name: view, exact: true }).click();
      await expect(workspace).toContainText(
        view === "History"
          ? "Assessment history"
          : view === "FEL / PDRI Context"
            ? "Read-only FEL / PDRI Context"
            : view === "Gaps"
              ? "Critical gaps and blockers"
              : view === "Readiness"
                ? "OVERALL_BASIC_DATA_READINESS"
                : "STUDY-W2B"
      );
    }
    const created = (await mutation(
      page,
      `/api/v1/basic-data/projects/${project!.id}/assessments`,
      workspace.getByRole("button", { name: "Create readiness assessment" }),
      201
    )) as unknown as Assessment;
    await workspace.getByRole("button", { name: "Preview assessment" }).click();
    await expect(workspace.getByRole("article", { name: "Basic Data assessment preview" })).toContainText(
      "persisted=false"
    );
    const submitted = await mutation(
      page,
      `/api/v1/basic-data/assessments/${created.id}/submit`,
      workspace.getByRole("button", { name: "Submit assessment" })
    );
    expect(submitted.status).toBe("IN_REVIEW");
    await reviewer.getByRole("button", { name: "Refresh current context", exact: true }).click();
    await reviewer.getByRole("button", { name: "History", exact: true }).click();
    await reviewer.getByRole("combobox", { name: "Assessment", exact: true }).selectOption(String(created.id));
    const completed = (await mutation(
      reviewerPage,
      `/api/v1/basic-data/assessments/${created.id}/complete`,
      reviewer.getByRole("button", { name: "Complete assessment" })
    )) as unknown as Assessment;
    expect(completed.status).toBe("COMPLETED");
    expect(completed.assessment_hash).toMatch(/^[a-f0-9]{64}$/);
    await workspace.getByRole("button", { name: "Refresh current context", exact: true }).click();
    await expect(workspace).toContainText("COMPLETED");
    await workspace.getByRole("button", { name: "Refresh Preview", exact: true }).click();
    await expect(workspace.getByRole("article", { name: "Basic Data assessment preview" })).toContainText(
      "persisted=false"
    );
    const historical = await json<Assessment>(
      await page.request.get(`${apiUrl}/api/v1/basic-data/assessments/${created.id}`, { headers })
    );
    expect(historical.assessment_hash).toBe(completed.assessment_hash);
    expect(historical.snapshot_json).toEqual(completed.snapshot_json);
    const current = await json<{
      status: string;
      coverage: { required: number; satisfied: number };
      source_current: boolean;
    }>(
      await reviewerPage.request.get(`${apiUrl}/api/v1/basic-data/projects/${project!.id}/current-readiness`, {
        headers: { Authorization: `Bearer ${reviewerToken}` },
      })
    );
    expect(current.status).toBe("READY");
    expect(current.coverage.required).toBe(requirements.requirements.length);
    expect(current.coverage.satisfied).toBe(requirements.requirements.length);
    const contextAfter = await json<{ context: Record<string, unknown> }>(
      await page.request.get(`${apiUrl}/api/v1/basic-data/projects/${project!.id}/requirements`, { headers })
    );
    expect(JSON.stringify(contextAfter.context)).toBe(contextBefore);
    await reviewContext.close();
  });

  test("ADMIN configures both policies, backend preview, independent publish/archive, and USER route denies mutation", async ({
    page,
    browser,
  }) => {
    test.setTimeout(720_000);
    const adminToken = await login(page, preparer);
    await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
    const reviewContext = await browser.newContext({ baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:5517" });
    const reviewerPage = await reviewContext.newPage();
    await login(reviewerPage, authority);
    await reviewerPage.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
    for (const definition of [
      {
        root: "risk-governance",
        phase: "Enterprise Foundation",
        view: "risk-governance-configuration",
        label: "Risk Governance",
        title: "Risk Governance Configuration",
        groups: [
          "Risk Capacity",
          "Risk Appetite",
          "Risk Thresholds",
          "Threshold Types / Operators",
          "Applicability",
          "Effective From",
          "Inheritance",
          "Review / SoD",
        ],
      },
      {
        root: "basic-data",
        phase: "Project Definition & Investment Case",
        view: "basic-data-configuration",
        label: "Basic Data Readiness Configuration",
        title: "Basic Data Readiness Configuration",
        groups: [
          "Data Categories",
          "Requirements",
          "Project Type Rules",
          "FEL Stage Rules",
          "Gate Profile Rules",
          "Quality Rules",
          "Confidence Rules",
          "Freshness Rules",
          "Blocking Rules",
          "Coverage Rules",
          "Inheritance",
          "Review / SoD",
        ],
      },
    ]) {
      await expand(page, "Enterprise Strategy Manager", "Admin mode navigation");
      await expand(page, definition.phase, "Admin mode navigation");
      await page
        .getByRole("navigation", { name: "Admin mode navigation" })
        .getByRole("button", { name: definition.label, exact: true })
        .click();
      const admin = page.getByRole("region", { name: definition.title, exact: true });
      await expect(admin).toBeVisible();
      await expect(
        admin.getByRole("button", { name: /Add Basic Data item|Create readiness assessment|Complete assessment/ })
      ).toHaveCount(0);
      for (const group of definition.groups)
        await expect(admin.getByRole("navigation", { name: `${definition.title} governed sections` })).toContainText(
          group
        );
      await admin.getByRole("button", { name: "Preview persisted=false", exact: true }).click();
      await expect(admin.getByRole("article", { name: "Effective configuration preview" })).toContainText(
        "persisted=false"
      );
      const source = admin
        .locator("[data-configuration-id]")
        .filter({ has: page.getByRole("button", { name: "Clone to DRAFT", exact: true }) })
        .first();
      const clonedWaiting = page.waitForResponse(
        (response) =>
          response.url().includes(`/api/v1/${definition.root}/admin/configurations/`) &&
          response.url().endsWith("/clone")
      );
      await source.getByRole("button", { name: "Clone to DRAFT" }).click();
      const cloned = await json<Configuration>(await clonedWaiting, definition.root === "basic-data" ? 201 : 200);
      const draft = admin.locator(`[data-configuration-id="${cloned.id}"]`);
      await draft.getByRole("button", { name: "Edit policy", exact: true }).click();
      const editor = admin.getByRole("region", { name: `Edit ${definition.title}`, exact: true });
      async function stage(label: string, value: unknown) {
        await editor
          .getByRole("navigation", { name: "Policy section editor" })
          .getByRole("button", { name: label, exact: true })
          .click();
        await editor.getByRole("textbox", { name: "Governed policy section JSON" }).fill(JSON.stringify(value));
      }
      if (definition.root === "risk-governance") {
        await stage("Risk Dimensions", [{ code: "FINANCIAL", label: "Financial exposure", active: true }]);
        await stage("Risk Capacity", [
          {
            code: "CAP_FIN",
            dimension_code: "FINANCIAL",
            statement: "Governed capacity context for the browser fixture",
            rationale: "Policy only; no Project decision.",
          },
        ]);
        await stage("Risk Appetite", [
          {
            code: "APP_FIN",
            dimension_code: "FINANCIAL",
            statement: "Governed appetite context for the browser fixture",
            rationale: "Separate from Risk Readiness.",
          },
        ]);
        await stage("Risk Thresholds", [
          {
            code: "THR_FIN",
            label: "Exposure attention",
            dimension_code: "FINANCIAL",
            type: "QUANTITATIVE",
            operator: "LESS_THAN_OR_EQUAL",
            value: 10,
            unit: "fixture-units",
            rationale: "Deterministic context only.",
          },
        ]);
      } else {
        const configured = cloned.content_json.requirements as Array<Record<string, unknown>>;
        expect(configured.length).toBeGreaterThan(0);
        await stage(
          "Requirements",
          configured.map((requirement, index) =>
            index === 0
              ? { ...requirement, name: `${String(requirement.name)} — browser governed revision` }
              : requirement
          )
        );
        await stage("Coverage Rules", {
          ...(cloned.content_json.coverage_rules as Record<string, unknown>),
          minimum_percent: 100,
        });
      }
      await editor
        .getByRole("navigation", { name: "Policy section editor" })
        .getByRole("button", { name: "Review / SoD", exact: true })
        .click();
      await editor
        .getByRole("textbox", { name: "Governed policy section JSON" })
        .fill(
          JSON.stringify(
            definition.root === "risk-governance"
              ? { preparer_cannot_publish: true }
              : { preparer_cannot_complete: true, author_cannot_publish: true }
          )
        );
      const draftPreview = page.waitForResponse(
        (response) =>
          response.url().endsWith(`/api/v1/${definition.root}/admin/preview`) && response.request().method() === "POST"
      );
      await admin.getByRole("button", { name: "Preview persisted=false", exact: true }).click();
      expect((await json<{ persisted: boolean }>(await draftPreview)).persisted).toBe(false);
      await mutation(
        page,
        `/api/v1/${definition.root}/admin/configurations/${cloned.id}`,
        editor.getByRole("button", { name: "Save DRAFT revision" })
      );
      // Tenant-configurator rights must not bypass the dedicated policy authority.
      const legacyUrl = `${apiUrl}/api/v1/admin-configuration/configurations/${cloned.id}`;
      const legacyHeaders = { Authorization: `Bearer ${adminToken}` };
      for (const response of [
        await page.request.post(`${legacyUrl}/clone`, { headers: legacyHeaders }),
        await page.request.patch(legacyUrl, {
          headers: legacyHeaders,
          data: { name: "Unauthorized legacy revision" },
        }),
        await page.request.post(`${legacyUrl}/publish`, { headers: legacyHeaders }),
      ]) {
        expect(response.status(), await response.text()).toBe(409);
        expect((await response.json()).detail.code).toBe("GOVERNED_CONFIGURATION_API_REQUIRED");
      }
      await expect(draft).toContainText("draft");
      await reviewerPage.goto(`/app/admin/strategy/${definition.view}`);
      const publisher = reviewerPage.getByRole("region", { name: definition.title, exact: true });
      const publishCard = publisher.locator(`[data-configuration-id="${cloned.id}"]`);
      await mutation(
        reviewerPage,
        `/api/v1/${definition.root}/admin/configurations/${cloned.id}/publish`,
        publishCard.getByRole("button", { name: "Publish", exact: true })
      );
      await mutation(
        reviewerPage,
        `/api/v1/${definition.root}/admin/configurations/${cloned.id}/archive`,
        publishCard.getByRole("button", { name: "Archive", exact: true })
      );
      await expect(publishCard).toContainText("archived");
    }
    await reviewContext.close();
    const userContext = await browser.newContext({ baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:5517" });
    const userPage = await userContext.newPage();
    const userToken = await login(userPage, userOnly);
    await expect(userPage.getByRole("button", { name: "Cambiar a ADMIN MODE" })).toBeDisabled();
    for (const domain of ["risk-governance", "basic-data"]) {
      const view = domain === "risk-governance" ? "risk-governance-configuration" : "basic-data-configuration";
      await userPage.goto(`/app/admin/strategy/${view}`);
      await expect(userPage.getByRole("alert", { name: "Strategic configuration access denied" })).toBeVisible();
      const denied = await userPage.request.post(`${apiUrl}/api/v1/${domain}/admin/preview`, {
        headers: { Authorization: `Bearer ${userToken}` },
        data: {},
      });
      expect(denied.status()).toBe(403);
    }
    await userContext.close();
  });
});
