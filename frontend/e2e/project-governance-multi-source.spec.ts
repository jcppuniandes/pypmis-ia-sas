import { expect, test } from "@playwright/test";

async function loginAsAdmin(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel("User").fill("admin");
  await page.getByLabel("Password").fill("1234");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
}

test("multi-source Project creation keeps one dynamic USER flow and three ADMIN policies", async ({ page }) => {
  await loginAsAdmin(page);

  await page.getByRole("button", { name: /cambiar a admin mode/i }).click();
  const adminEnterprise = page.getByRole("button", { name: /^enterprise structure$/i });
  if ((await adminEnterprise.getAttribute("aria-expanded")) !== "true") await adminEnterprise.click();
  await page.getByRole("button", { name: /^enterprise structure configuration/i }).click();
  await page.getByRole("button", { name: /creation policies/i }).click();

  await expect(page.getByText("READY_FOR_MULTI_SOURCE_PROJECT_CREATION")).toBeVisible();
  const policyTabs = page.getByRole("tablist", { name: "Modelos de gobierno" });
  await expect(policyTabs.getByRole("tab", { name: /Capital Owner/i })).toBeVisible();
  await expect(policyTabs.getByRole("tab", { name: /Contractor Delivery/i })).toBeVisible();
  await expect(policyTabs.getByRole("tab", { name: /Direct Internal/i })).toBeVisible();

  await page.getByRole("button", { name: /cambiar a user mode/i }).click();
  const userEnterprise = page.getByRole("button", { name: /enterprise structure & workspace manager/i });
  if ((await userEnterprise.getAttribute("aria-expanded")) !== "true") await userEnterprise.click();
  await page.getByRole("button", { name: /^enterprise explorer/i }).click();
  await page.getByRole("button", { name: /^create project$/i }).click();

  const models = page.getByRole("radiogroup", { name: "Modelo de gobierno" });
  await expect(models).toBeVisible();
  await expect(models.getByRole("radio", { name: /Direct Internal/i })).toBeChecked();
  await expect(page.getByLabel("Referencia de autorización")).toBeVisible();
  await expect(page.getByLabel("Patrocinador")).toBeVisible();

  await models.getByRole("radio", { name: /Contractor Delivery/i }).check();
  await expect(page.getByLabel("Cliente")).toBeVisible();
  await expect(page.getByLabel("Número de contrato")).toBeVisible();
  await expect(page.getByLabel("Alcance contractual")).toBeVisible();

  await models.getByRole("radio", { name: /Capital Owner/i }).check();
  await expect(page.getByText(/se crea desde Strategic Project Planning Entry/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /Guardar solicitud y previsualizar/i })).toBeDisabled();
});
