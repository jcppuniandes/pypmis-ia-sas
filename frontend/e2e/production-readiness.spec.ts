import { expect, test } from "@playwright/test";

test("production readiness smoke covers login, integrated control and AWP", async ({ page }) => {
  const apiUrl = process.env.E2E_API_URL;
  if (apiUrl) {
    await page.route("http://localhost:8000/**", async (route) => {
      const nextUrl = route.request().url().replace("http://localhost:8000", apiUrl);
      await route.continue({ url: nextUrl });
    });
  }

  await page.goto("/login");
  await page.getByLabel("User").fill("admin");
  await page.getByLabel("Password").fill("1234");
  await page.getByRole("button", { name: /sign in/i }).click();

  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();

  // The guided rail exposes integrated control as "Open Business processes"
  // and the AWP register as "Open AWP packages".
  await page.getByRole("button", { name: /open business processes/i }).click();
  await expect(page.getByRole("heading", { name: /ai control auditor/i })).toBeVisible();
  await expect(page.getByText(/senior awp packaging advisor/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /create draft packages/i })).toBeVisible();

  await page.getByRole("button", { name: /open awp packages/i }).click();
  await expect(page.getByRole("heading", { name: /awp minimum register/i })).toBeVisible();
  await expect(page.getByText(/POC:/i).first()).toBeVisible();
});
