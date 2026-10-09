import { expect, type Page, test } from "@playwright/test";

const apiUrl = process.env.E2E_API_URL || "http://localhost:8000";

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

test("Gate 07E USER and ADMIN localhost release smoke", async ({ page }, testInfo) => {
  for (const localApiOrigin of ["http://localhost:8000", "http://127.0.0.1:8000"]) {
    await page.route(`${localApiOrigin}/**`, async (route) => {
      await route.continue({ url: route.request().url().replace(localApiOrigin, apiUrl) });
    });
  }
  const failedResponses: Array<{ status: number; url: string }> = [];
  const pageErrors: string[] = [];
  page.on("response", (response) => {
    if (response.url().includes("portfolio-evaluation") && response.status() >= 400) {
      failedResponses.push({ status: response.status(), url: response.url() });
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await login(page);
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^portfolio manager$/i);
  await page.getByRole("button", { name: /^portfolio evaluation$/i }).click();
  await expect(page.getByRole("heading", { name: "Portfolio Evaluation", exact: true })).toBeVisible();
  await expect(page.getByLabel("Portfolio context")).toBeVisible();
  await expect(page.getByRole("button", { name: "ALL AUTHORIZED", exact: true })).toBeVisible();
  await expect(page.getByText("No authorized evaluations in this queue")).toBeVisible();
  await expect(page.getByText(/global candidate entity is used/i)).toBeVisible();
  await expect(page.getByText("Portfolio Candidate", { exact: false })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("gate07e-user.png"), fullPage: true });

  await page.getByRole("button", { name: /^prioritization matrix$/i }).click();
  await expect(page.getByRole("heading", { name: "Prioritization Matrix", exact: true })).toBeVisible();
  await expect(page.getByRole("table", { name: "Portfolio prioritization ranking" })).toBeVisible();
  await expect(page.getByText("No completed evaluations to rank")).toBeVisible();
  await expect(page.getByText("GATE07E_REWORK_REQUIRED", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  await expand(page, /^enterprise strategy manager$/i);
  await page.getByRole("button", { name: /^portfolio evaluation & prioritization$/i }).click();
  await expect(page.getByRole("heading", { name: "Portfolio Evaluation & Prioritization", exact: true })).toBeVisible();
  await expect(page.getByText("DRAFT", { exact: true })).toBeVisible();
  await expect(page.getByText("Disabled", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Portfolio Evaluation configuration JSON")).toBeEnabled();
  await expect(
    page.getByRole("navigation", { name: "Portfolio Evaluation configuration sections" }).getByRole("button")
  ).toHaveCount(11);
  await page.screenshot({ path: testInfo.outputPath("gate07e-admin.png"), fullPage: true });

  expect(failedResponses).toEqual([]);
  expect(pageErrors).toEqual([]);
});
