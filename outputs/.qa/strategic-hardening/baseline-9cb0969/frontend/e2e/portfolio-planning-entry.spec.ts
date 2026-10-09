import { expect, type Page, test } from "@playwright/test";

const apiUrl = process.env.E2E_API_URL || "http://localhost:8000";

async function login(page: Page, user: string) {
  await page.goto("/login");
  await page.getByLabel("User").fill(user);
  await page.getByLabel("Password").fill("1234");
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes("/api/v1/auth/login") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /sign in/i }).click();
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { access_token: string };
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
  return body.access_token;
}

async function openUserPlanningEntry(page: Page) {
  const macroprocess = page.getByRole("button", { name: /^enterprise strategy manager$/i });
  if ((await macroprocess.getAttribute("aria-expanded")) !== "true") await macroprocess.click();
  const portfolioManager = page.getByRole("button", { name: /^portfolio manager$/i });
  if ((await portfolioManager.getAttribute("aria-expanded")) !== "true") await portfolioManager.click();
  await page.getByRole("button", { name: /^strategic project planning entry$/i }).click();
  await expect(page.getByRole("heading", { name: "Strategic Project Planning Entry" })).toBeVisible();
}

async function openAdminPlanningConfiguration(page: Page) {
  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  const enterpriseStrategy = page.getByRole("button", { name: /^enterprise strategy manager$/i });
  if ((await enterpriseStrategy.getAttribute("aria-expanded")) !== "true") await enterpriseStrategy.click();
  await page.getByRole("button", { name: /^portfolio planning entry & membership$/i }).click();
  await expect(page.getByRole("heading", { name: "Portfolio Planning Entry & Membership" })).toBeVisible();
}

test("Gate 07D full-stack USER and ADMIN release flow", async ({ page }) => {
  for (const localApiOrigin of ["http://localhost:8000", "http://127.0.0.1:8000"]) {
    await page.route(`${localApiOrigin}/**`, async (route) => {
      await route.continue({ url: route.request().url().replace(localApiOrigin, apiUrl) });
    });
  }
  const gateResponses: Array<{ status: number; url: string }> = [];
  const gateConsole: string[] = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    const url = response.url();
    if (
      (url.includes("strategic-project-planning") || url.includes("project-creation-requests")) &&
      response.status() >= 400
    ) {
      gateResponses.push({ status: response.status(), url });
    }
  });
  page.on("console", (message) => {
    if (
      ["error", "warning"].includes(message.type()) &&
      /gate\s*07d|portfolio.planning|strategic.project/i.test(message.text())
    ) {
      gateConsole.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await login(page, "admin");
  await openUserPlanningEntry(page);

  await expect(page.getByText("Portfolio + FEL entry")).toBeVisible();
  await expect(page.getByText("Blocked", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Gate 07C Input Contract" })).toBeVisible();
  await expect(page.getByText("Decision", { exact: true })).toBeVisible();
  await expect(page.getByText("Proposal", { exact: true })).toBeVisible();
  await expect(page.getByText("Idea", { exact: true })).toBeVisible();
  await expect(page.getByText("Target Portfolio", { exact: true })).toBeVisible();
  await expect(page.getByText("Project Number preview", { exact: true })).toBeVisible();
  await expect(page.getByText("Record Code preview", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Project parent")).not.toHaveValue("0");
  await expect(page.getByLabel("Published Project template")).not.toHaveValue("0");
  await expect(page.getByLabel("Project Manager", { exact: true })).not.toHaveValue("0");
  await page.getByLabel("Project Type").fill("capital");

  await page.getByRole("button", { name: /create projectcreationrequest/i }).click();
  await expect(page.getByText(/Strategic ProjectCreationRequest created/i)).toBeVisible();
  await page.getByRole("button", { name: /^submit$/i }).click();
  await expect(page.getByText(/Gate 05B action completed: submit/i)).toBeVisible();
  await page.getByRole("button", { name: /^start review$/i }).click();
  await expect(page.getByText(/Gate 05B action completed: start-review/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /^approve$/i })).toHaveCount(0);

  await page.getByRole("button", { name: "Logout" }).click();
  const approverToken = await login(page, "ana.control@demo.local");
  await openUserPlanningEntry(page);
  await page.getByRole("button", { name: /^approve$/i }).click();
  await expect(page.getByText(/Gate 05B action completed: approve/i)).toBeVisible();

  const materializeResponse = page.waitForResponse(
    (response) => response.url().includes("/materialize") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /materialize pending project/i }).click();
  const materialized = await materializeResponse;
  expect(materialized.ok()).toBeTruthy();
  const materializedBody = (await materialized.json()) as { materialized_workspace_id: number };
  const projectId = materializedBody.materialized_workspace_id;

  await expect(page.getByText("READY_FOR_PORTFOLIO_PLANNING", { exact: true })).toBeVisible();
  await expect(page.getByText(/Workspace status: pending/i)).toBeVisible();
  await expect(page.getByText(/Target membership:/i)).not.toContainText("Pending");
  await expect(page.getByText("READY", { exact: true })).toHaveCount(2);

  const authHeaders = { Authorization: `Bearer ${approverToken}` };
  const contextResponse = await page.request.get(`${apiUrl}/api/v1/workspaces/${projectId}/context`, {
    headers: authHeaders,
  });
  expect(contextResponse.ok()).toBeTruthy();
  const context = (await contextResponse.json()) as { navigator: Array<{ code: string }> };
  const navigator = context.navigator.map((item) => item.code);
  expect(navigator).toEqual(
    expect.arrayContaining([
      "overview",
      "strategic-context",
      "portfolio-memberships",
      "portfolio-planning-readiness",
      "project-definition-readiness",
    ])
  );
  expect(navigator).not.toEqual(expect.arrayContaining(["scope", "schedule", "cost"]));

  const membershipResponse = await page.request.get(`${apiUrl}/api/v1/projects/${projectId}/portfolio-memberships`, {
    headers: authHeaders,
  });
  expect(membershipResponse.ok()).toBeTruthy();
  const memberships = (await membershipResponse.json()) as Array<{
    is_target_portfolio: boolean;
    membership_source: string;
    status: string;
  }>;
  expect(memberships).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        is_target_portfolio: true,
        membership_source: "STRATEGIC_INTAKE",
        status: "ACTIVE",
      }),
    ])
  );

  const gate07dWorkspace = page.getByRole("region", { name: "Strategic Project Planning Entry", exact: true });
  await expect(gate07dWorkspace.getByRole("button", { name: /activate/i })).toHaveCount(0);
  for (const forbidden of [
    "Portfolio Candidate",
    "Prioritization Matrix",
    "Investor Map",
    "PDRI score",
    "FEL score",
    "FID controls",
  ]) {
    await expect(gate07dWorkspace.getByText(forbidden, { exact: false })).toHaveCount(0);
  }

  await openAdminPlanningConfiguration(page);
  await expect(page.getByText("STRATEGIC_INTAKE_ONLY", { exact: true })).toBeVisible();
  const cloneResponsePromise = page.waitForResponse(
    (response) => response.url().endsWith("/clone") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /^clone$/i }).click();
  const cloneResponse = await cloneResponsePromise;
  expect(cloneResponse.ok()).toBeTruthy();
  const clone = (await cloneResponse.json()) as {
    id: number;
    version: number;
    name: string;
    description: string;
    content_json: Record<string, unknown>;
  };
  await expect(page.getByLabel("Portfolio Planning configuration JSON")).toBeEnabled();
  await page.getByRole("button", { name: /^save$/i }).click();
  await expect(page.getByText(/Configuration save completed/i)).toBeVisible();

  const staleResponse = await page.request.put(
    `${apiUrl}/api/v1/strategic-project-planning/admin/configurations/${clone.id}`,
    {
      headers: { ...authHeaders, "Content-Type": "application/json", "If-Match": `"${clone.version}"` },
      data: { name: clone.name, description: clone.description, content_json: clone.content_json },
    }
  );
  expect(staleResponse.status()).toBe(412);
  await page.getByRole("button", { name: /^publish$/i }).click();
  await expect(page.getByText(/Configuration publish completed/i)).toBeVisible();

  expect(gateResponses).toEqual([]);
  expect(gateConsole).toEqual([]);
  expect(pageErrors).toEqual([]);
});
