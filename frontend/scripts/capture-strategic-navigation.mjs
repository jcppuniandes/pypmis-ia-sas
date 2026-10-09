import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

const baseURL = process.env.E2E_BASE_URL || "http://localhost:5173";
const outputDirectory = path.resolve(process.argv[2] || "../docs/validation/strategic-navigation-v2");
const captureVariant = process.env.CAPTURE_VARIANT || "current";

await mkdir(outputDirectory, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });

try {
  await page.goto(`${baseURL}/login`);
  await page.getByLabel("User").fill("admin");
  await page.getByLabel("Password").fill("1234");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.getByRole("region", { name: /project workspace and control flow/i }).waitFor();

  const userNavigation = page.getByRole("navigation", { name: /validation focus|control flow/i });
  const userStrategy = userNavigation.getByRole("button", { name: "Enterprise Strategy Manager", exact: true });
  if ((await userStrategy.getAttribute("aria-expanded")) !== "true") await userStrategy.click();
  if (captureVariant !== "baseline") {
    await userNavigation.getByRole("button", { name: "Foundation Status", exact: true }).click();
    await page.getByRole("region", { name: "Enterprise Strategy Manager" }).waitFor();
  }
  await page.screenshot({ path: path.join(outputDirectory, "user-mode-desktop.png"), fullPage: true });

  await page.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }).click();
  const adminNavigation = page.getByRole("navigation", { name: "Admin mode navigation" });
  const adminStrategy = adminNavigation.getByRole("button", { name: "Enterprise Strategy Manager", exact: true });
  if ((await adminStrategy.getAttribute("aria-expanded")) !== "true") await adminStrategy.click();
  await page.screenshot({ path: path.join(outputDirectory, "admin-mode-desktop.png"), fullPage: true });
} finally {
  await browser.close();
}
