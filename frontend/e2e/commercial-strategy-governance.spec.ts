import { expect, type Locator, type Page, test } from "@playwright/test";

async function login(page: Page, user = "admin") {
  await page.goto("/login");
  await page.getByLabel("User").fill(user);
  await page.getByLabel("Password").fill("1234");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
}

async function expand(button: Locator) {
  await expect(button).toBeVisible();
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
  await expect(button).toHaveAttribute("aria-expanded", "true");
}

async function openPhase(page: Page, navigationName: RegExp, phaseName: string) {
  const navigation = page.getByRole("navigation", { name: navigationName });
  await expand(navigation.getByRole("button", { name: "Enterprise Strategy Manager", exact: true }));
  const modules = navigation.getByRole("group", { name: "Módulos de Enterprise Strategy Manager" });
  const phase = modules.locator(":scope > .navigatorModule > .navigatorModuleButton").filter({ hasText: phaseName });
  await expect(phase).toHaveCount(1);
  await expand(phase);
  return modules;
}

test("07M-COMM keeps USER transactions and ADMIN policy configuration separated", async ({ page }) => {
  await login(page);

  const userModules = await openPhase(page, /validation focus|control flow/i, "Business Case & Investment Development");
  await userModules.getByRole("button", { name: "Commercial & Contracting Strategy", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/strategy\/commercial-strategy-my$/);

  const user = page.getByRole("region", { name: "Commercial and Contracting Strategy" });
  await expect(user).toBeVisible();
  await expect(user.getByRole("navigation", { name: "Commercial Strategy views" }).getByRole("button")).toHaveCount(14);
  await expect(user.getByRole("group", { name: "Commercial Strategy queues" }).getByRole("button")).toHaveCount(8);
  await expect(user.getByRole("button", { name: /Publish|Archive|Clone/ })).toHaveCount(0);
  await expect(user).toContainText("never creates a Tender, Bid, Vendor, Contract");

  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  const adminModules = await openPhase(page, /admin mode navigation/i, "Project Definition & Investment Case");
  await adminModules.getByRole("button", { name: "Commercial Strategy Configuration", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/admin\/strategy\/commercial-strategy-configuration$/);

  const admin = page.getByRole("region", { name: "Commercial Strategy Configuration" });
  await expect(admin).toBeVisible();
  await expect(admin.getByRole("navigation", { name: "Commercial Strategy configuration sections" }).getByRole("button")).toHaveCount(20);
  await expect(admin.getByRole("button", { name: /^Submit$/ })).toHaveCount(0);
  await expect(admin.getByRole("button", { name: /^Complete$/ })).toHaveCount(0);
  await expect(admin).toContainText("cannot create, edit, submit, review or complete a live Project Commercial Strategy");
});

test("07M-COMM canonical deep routes preserve mode guards", async ({ page }) => {
  await login(page, "camila.cost@demo.local");
  await page.goto("/app/strategy/commercial-strategy-risk-allocation");
  await expect(page).toHaveURL(/\/app\/strategy\/commercial-strategy-risk-allocation$/);
  await expect(page.getByRole("navigation", { name: "Strategic workflow breadcrumb" })).toContainText(
    "Risk Allocation"
  );

  await page.goto("/app/admin/strategy/commercial-strategy-configuration");
  const denied = page.getByRole("alert", { name: "Strategic configuration access denied" });
  await expect(denied).toBeVisible();
  await expect(denied).toHaveAttribute("data-control-classification", "ADMIN_CONFIGURATION");
});
