import { chromium } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.E2E_BASE_URL || "http://127.0.0.1:5173";
const outputPath = process.argv[2] ? path.resolve(process.argv[2]) : null;

async function timed(label, action) {
  const startedAt = performance.now();
  await action();
  return { label, duration_ms: Number((performance.now() - startedAt).toFixed(1)) };
}

async function login(page) {
  await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("User").fill("admin");
  await page.getByLabel("Password").fill("1234");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.getByRole("region", { name: /project workspace and control flow/i }).waitFor();
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
const failures = [];
page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
page.on("response", (response) => {
  if (response.status() >= 500) failures.push(`${response.status()} ${response.url()}`);
});

try {
  await login(page);
  const measurements = [];

  measurements.push(
    await timed("strategic_navigation_render", async () => {
      const navigation = page.getByRole("navigation", { name: /validation focus|control flow/i });
      const macroprocess = navigation.getByRole("button", {
        name: "Enterprise Strategy Manager",
        exact: true,
      });
      if ((await macroprocess.getAttribute("aria-expanded")) !== "true") await macroprocess.click();
      await navigation.getByRole("group", { name: "Módulos de Enterprise Strategy Manager" }).waitFor();
    })
  );

  measurements.push(
    await timed("enterprise_strategy_landing_render", async () => {
      const navigation = page.getByRole("navigation", { name: /validation focus|control flow/i });
      await navigation.getByRole("button", { name: "Foundation Status", exact: true }).click();
      await page.getByRole("region", { name: "Enterprise Strategy Manager" }).waitFor();
    })
  );

  measurements.push(
    await timed("business_analysis_first_page_render", async () => {
      await page.goto(`${baseUrl}/app/strategy/business-analysis-options`, { waitUntil: "domcontentloaded" });
      await page.getByRole("region", { name: "Business Analysis and Options" }).waitFor();
    })
  );

  measurements.push(
    await timed("gate07j_evidence_view_render", async () => {
      await page.goto(`${baseUrl}/app/strategy/investment-decision-evidence`, { waitUntil: "domcontentloaded" });
      await page.locator("#control-flow-content").waitFor();
    })
  );

  const result = {
    measured_at: new Date().toISOString(),
    base_url: baseUrl,
    viewport: { width: 1440, height: 900 },
    measurements,
    failures,
  };
  const serialized = `${JSON.stringify(result, null, 2)}\n`;
  if (outputPath) {
    await fs.mkdir(path.dirname(outputPath), { recursive: true });
    await fs.writeFile(outputPath, serialized, "utf8");
  }
  process.stdout.write(serialized);
  if (failures.length) process.exitCode = 1;
} finally {
  await browser.close();
}
