import { expect, test } from "@playwright/test";

test("production readiness smoke covers login, integrated control and AWP", async ({ page }) => {
  const apiUrl = process.env.E2E_API_URL;
  if (apiUrl) {
    for (const localApiOrigin of ["http://localhost:8000", "http://127.0.0.1:8000"]) {
      await page.route(`${localApiOrigin}/**`, async (route) => {
        const nextUrl = route.request().url().replace(localApiOrigin, apiUrl);
        await route.continue({ url: nextUrl });
      });
    }
  }

  await page.goto("/login");
  await page.getByLabel("User").fill("admin");
  await page.getByLabel("Password").fill("1234");
  await page.getByRole("button", { name: /sign in/i }).click();

  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();

  // Use the guided shortcuts when they are enabled. In validation mode, follow
  // the same workflow through the macroprocess/module navigation.
  const guidedBusinessProcesses = page.getByRole("button", { name: /open business processes/i });
  if (await guidedBusinessProcesses.isVisible()) {
    await guidedBusinessProcesses.click();
  } else {
    const costManager = page.getByRole("button", { name: /^cost manager$/i });
    if ((await costManager.getAttribute("aria-expanded")) !== "true") {
      await costManager.click();
    }
    await page.getByRole("button", { name: /^fund\b/i }).click();
  }
  await expect(page.getByRole("heading", { name: /ai control auditor/i })).toBeVisible();
  await expect(page.getByText(/senior awp packaging advisor/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /create draft packages/i })).toBeVisible();

  const guidedAwpPackages = page.getByRole("button", { name: /open awp packages/i });
  if (await guidedAwpPackages.isVisible()) {
    await guidedAwpPackages.click();
  } else {
    const scopeManager = page.getByRole("button", { name: /^scope manager$/i });
    if ((await scopeManager.getAttribute("aria-expanded")) !== "true") {
      await scopeManager.click();
    }
    await page.getByRole("button", { name: /^work packages\b/i }).click();
  }
  await expect(page.getByRole("heading", { name: /^work packages$/i })).toBeVisible();
  await expect(page.getByText(/POC:/i).first()).toBeVisible();
});
