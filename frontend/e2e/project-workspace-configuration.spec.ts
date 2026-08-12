import { expect, test } from "@playwright/test";

test("Gate 05A configures PROJECT without materializing a Project Workspace", async ({ page }) => {
  const apiUrl = process.env.E2E_API_URL;
  if (apiUrl) {
    for (const localApiOrigin of ["http://localhost:8000", "http://127.0.0.1:8000"]) {
      await page.route(`${localApiOrigin}/**`, async (route) => {
        await route.continue({ url: route.request().url().replace(localApiOrigin, apiUrl) });
      });
    }
  }
  await page.goto("/login");
  await page.getByLabel("User").fill("admin");
  await page.getByLabel("Password").fill("1234");
  await page.getByRole("button", { name: /sign in/i }).click();

  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
  await page.getByRole("button", { name: /cambiar a admin mode/i }).click();
  const enterpriseStructure = page.getByRole("button", { name: /^enterprise structure$/i });
  if ((await enterpriseStructure.getAttribute("aria-expanded")) !== "true") {
    await enterpriseStructure.click();
  }
  await page.getByRole("button", { name: /^enterprise structure configuration/i }).click();

  await expect(page.getByRole("heading", { name: "Enterprise Structure Configuration" })).toBeVisible();
  await page.getByRole("button", { name: /project templates/i }).click();
  await expect(page.getByText("READY_FOR_PROJECT_CREATION_PROCESS")).toBeVisible();
  await expect(page.getByText("Portfolio / Program")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Revisiones configuradas" })).toBeVisible();
  await expect(page.getByRole("button", { name: /PYP-PRJ-GENERAL/i })).toBeVisible();

  await page.getByRole("button", { name: /previsualizar/i }).click();
  await expect(page.getByText(/^PYP-PRJ-\d{5}$/)).toBeVisible();
  await expect(page.getByText("No (preview)")).toBeVisible();
  await expect(page.getByRole("button", { name: /materializar|crear project/i })).toHaveCount(0);

  await page.getByRole("button", { name: /numbering rules/i }).click();
  await expect(page.getByText(/^PYP-PRJ-\d{5}$/)).toBeVisible();
  await expect(page.getByText("No consume secuencia")).toBeVisible();

  await page.getByRole("button", { name: /creation policies/i }).click();
  await expect(page.getByRole("heading", { name: "Project Creation Process" })).toBeVisible();
  await expect(page.getByText(/no crea, aprueba ni materializa/i)).toBeVisible();
});
