import { expect, type Locator, type Page, test } from "@playwright/test";

async function login(page: Page, user = "admin") {
  await page.goto("/login");
  await page.getByLabel("User").fill(user);
  await page.getByLabel("Password").fill("1234");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
}

async function openStrategicPhase(page: Page, navigationName: RegExp, phaseName: string) {
  const navigation = page.getByRole("navigation", { name: navigationName });
  await expand(navigation.getByRole("button", { name: "Enterprise Strategy Manager", exact: true }));
  const modules = navigation.getByRole("group", { name: "Módulos de Enterprise Strategy Manager" });
  const phaseButton = modules.locator(":scope > .navigatorModule > .navigatorModuleButton").filter({
    hasText: phaseName,
  });
  await expect(phaseButton).toHaveCount(1);
  await expand(phaseButton);
  return modules;
}

async function expand(button: Locator) {
  await expect(button).toBeVisible();
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
  await expect(button).toHaveAttribute("aria-expanded", "true");
}

const userPhases = [
  "Enterprise Foundation",
  "Idea & Demand",
  "Project Proposal",
  "Strategic Gate",
  "Portfolio Planning & Review",
  "Portfolio Scenario Planning",
  "Business Case & Investment Development",
  "Investment Governance",
];

test("USER and ADMIN strategic navigation follows the business workflow", async ({ page }) => {
  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];
  const requestFailures: string[] = [];
  const serverErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) =>
    requestFailures.push(`${request.method()} ${request.url()} ${request.failure()?.errorText || "failed"}`)
  );
  page.on("response", (response) => {
    if (response.status() >= 500) serverErrors.push(`${response.status()} ${response.url()}`);
  });
  await login(page);

  const userNavigation = page.getByRole("navigation", { name: /validation focus|control flow/i });
  await expand(userNavigation.getByRole("button", { name: "Enterprise Strategy Manager", exact: true }));
  const userModuleGroup = userNavigation.getByRole("group", { name: "Módulos de Enterprise Strategy Manager" });
  await expect(userModuleGroup.locator(":scope > .navigatorModule > button")).toHaveCount(8);
  await expect(userModuleGroup.locator(":scope > .navigatorModule > button")).toHaveText(
    userPhases.map((item) => new RegExp(item))
  );
  await expect(userModuleGroup.getByRole("button", { name: "Enterprise Foundation", exact: true })).toContainText(
    "Foundation / prerequisite"
  );
  await expect(userModuleGroup.getByRole("button", { name: "Idea & Demand", exact: true })).toContainText(
    "Start of strategic workflow"
  );

  await userModuleGroup.getByRole("button", { name: "Foundation Status", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/strategy\/enterprise-strategy-overview$/);
  const landing = page.getByRole("region", { name: "Enterprise Strategy Manager" });
  await expect(landing.getByRole("region", { name: "Parallel Budget and Resource scenario branches" })).toBeVisible();
  await expect(landing.getByRole("region", { name: "Investment evidence contributors" })).toBeVisible();

  await userModuleGroup.getByRole("button", { name: "Portfolio Planning & Review", exact: true }).click();
  await userModuleGroup.getByRole("button", { name: "Portfolio Analysis", exact: true }).click();
  await userModuleGroup.getByRole("button", { name: "Portfolio Scorecard", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/strategy\/portfolio-scorecard$/);
  await expect(page.getByRole("navigation", { name: "Strategic workflow breadcrumb" })).toContainText(
    "Portfolio Scorecard"
  );

  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("button", { name: "Cambiar a USER MODE" })).toBeVisible();
  const adminNavigation = page.getByRole("navigation", { name: "Admin mode navigation" });
  await expand(adminNavigation.getByRole("button", { name: "Enterprise Strategy Manager", exact: true }));
  const adminModules = adminNavigation.getByRole("group", { name: "Módulos de Enterprise Strategy Manager" });
  await expand(adminModules.getByRole("button", { name: "Investment Governance", exact: true }));
  const governance = adminModules.getByRole("group", { name: "Submódulos de Investment Governance" });
  const governanceControls = governance.getByRole("button");
  await expect(governanceControls).toHaveCount(4);
  await expect(governanceControls).toHaveText([
    "Investment Decision Evidence Policy",
    "Investment Gate Preparation",
    "Investment Decision / FID",
    "Post-FID Project Governance",
  ]);

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
  expect(requestFailures).toEqual([]);
  expect(serverErrors).toEqual([]);
});

test("strategic landing preserves workflow order on tablet and mobile", async ({ page }) => {
  await login(page);
  const navigation = page.getByRole("navigation", { name: /validation focus|control flow/i });
  await expand(navigation.getByRole("button", { name: "Enterprise Strategy Manager", exact: true }));
  await navigation.getByRole("button", { name: "Foundation Status", exact: true }).click();

  for (const viewport of [
    { width: 820, height: 1000 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    const landing = page.getByRole("region", { name: "Enterprise Strategy Manager" });
    await expect(landing.getByRole("heading", { name: "Enterprise Foundation" })).toBeVisible();
    await expect(landing.getByRole("heading", { name: "Idea & Demand" })).toBeVisible();
    await expect(landing.getByRole("region", { name: "Parallel Budget and Resource scenario branches" })).toBeVisible();
  }
});

test("strategic modes do not expose controls owned by the opposite responsibility", async ({ page }) => {
  await login(page);

  const userModules = await openStrategicPhase(page, /validation focus|control flow/i, "Idea & Demand");
  await userModules.getByRole("button", { name: "Business Analysis & Options", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/strategy\/business-analysis-options$/);
  const userSurface = page.locator('[data-control-classification="USER_TRANSACTION"]');
  await expect(userSurface).toBeVisible();
  await expect(userSurface.getByRole("button", { name: /Edit policy|Publish policy|Configure/i })).toHaveCount(0);

  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  const adminModules = await openStrategicPhase(page, /admin mode navigation/i, "Idea & Demand Configuration");
  await adminModules.getByRole("button", { name: "Business Analysis Configuration", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/admin\/strategy\/business-analysis-configuration$/);
  const adminSurface = page.locator('[data-control-classification="ADMIN_CONFIGURATION"]');
  await expect(adminSurface).toBeVisible();
  for (const forbiddenAction of ["Create analysis", "Submit", "Start review", "Complete", "Enter FID"]) {
    await expect(adminSurface.getByRole("button", { name: forbiddenAction, exact: true })).toHaveCount(0);
  }
});

test("direct ADMIN route is denied when the membership lacks can_configure", async ({ page }) => {
  await login(page, "camila.cost@demo.local");
  const toggle = page.getByRole("button", { name: "Cambiar a ADMIN MODE" });
  await expect(toggle).toBeDisabled();

  await page.goto("/app/admin/strategy/business-analysis-configuration");
  const denied = page.getByRole("alert", { name: "Strategic configuration access denied" });
  await expect(denied).toBeVisible();
  await expect(denied).toHaveAttribute("data-control-classification", "ADMIN_CONFIGURATION");
  await expect(denied.getByText("Configuration access required")).toBeVisible();
});
