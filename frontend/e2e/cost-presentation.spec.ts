import { expect, test } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const fixtureFile = process.env.E2E_O1BC_FIXTURE;
const fixture = fixtureFile ? JSON.parse(readFileSync(fixtureFile, "utf8")) : null;
const api = process.env.E2E_API_URL || "http://127.0.0.1:8856";
const output = path.resolve(process.env.E2E_O1BC_OUTPUT || "../outputs/.qa/wave-o1bc-20261022/chromium");

test("Cost read-only visual verification after governed lifecycle", async ({ browser, request }) => {
  test.skip(!fixture, "Requires completed isolated real business UAT");
  test.setTimeout(240_000);
  expect(api).toMatch(/^http:\/\/(127\.0\.0\.1|localhost):8856$/);
  const original = readFileSync(path.join(output, "browser-uat.json"), "utf8");
  expect(JSON.parse(original).result).toBe("PASS");
  const user = fixture.users.cost_controller;
  const response = await request.post(`${api}/api/v1/auth/login`, {
    data: { email: user.email, tenant_id: user.tenant_id, password: user.password || "O1bc-disposable-only!" },
  });
  expect(response.status()).toBe(200);
  const session = await response.json();
  const context = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
  await context.addInitScript(
    (value) =>
      localStorage.setItem(
        "pypmis_auth",
        JSON.stringify({ state: { token: value.access_token, user: value.user }, version: 0 })
      ),
    session
  );
  const page = await context.newPage();
  const errors: string[] = [];
  const businessWrites: string[] = [];
  page.on("pageerror", (error) => errors.push(String(error)));
  page.on("request", (request) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method()) && request.url().includes("/api/v1/cost/"))
      businessWrites.push(request.url());
  });
  const measurements: unknown[] = [];
  try {
    await page.goto(`/workspaces/${fixture.project_workspace_id}/cost`);
    await expect(page.getByRole("heading", { name: "Cost Manager", exact: true })).toBeVisible();
    const tabs = page.getByRole("navigation", { name: "Cost Manager submodules" });
    for (const name of ["Budget", "Cost Baseline", "Actuals"]) {
      await tabs.getByRole("button", { name, exact: true }).click();
      await expect(
        page.getByRole("table", {
          name: name === "Budget" ? "Budget Versions" : name === "Cost Baseline" ? "Cost Baselines" : "Actual Cost",
          exact: true,
        })
      ).toBeVisible();
      if (name === "Actuals")
        await page.screenshot({ path: path.join(output, "cost-actual-recognized-final.png"), fullPage: true });
    }
    const summary = page.waitForResponse((response) => response.url().endsWith("/financial-overview"));
    await tabs.getByRole("button", { name: "Cost Overview", exact: true }).click();
    expect((await summary).status()).toBe(200);
    await expect(page.getByRole("table", { name: "Cost Cash Flow", exact: true })).toContainText("USD");
    for (const width of [1280, 900]) {
      await page.setViewportSize({ width, height: 1000 });
      const layout = await page.evaluate(() => ({
        viewport: window.innerWidth,
        page: document.documentElement.scrollWidth,
        cards: [...document.querySelectorAll(".costFacts > div")].map((element) => ({
          width: element.clientWidth,
          scroll: element.scrollWidth,
          text: element.textContent,
        })),
      }));
      measurements.push(layout);
      expect(layout.page).toBeLessThanOrEqual(layout.viewport + 1);
      for (const card of layout.cards) expect(card.scroll, String(card.text)).toBeLessThanOrEqual(card.width + 1);
      await page.screenshot({ path: path.join(output, `cost-overview-final-${width}.png`), fullPage: true });
    }
    expect(errors).toEqual([]);
    expect(businessWrites).toEqual([]);
    expect(readFileSync(path.join(output, "browser-uat.json"), "utf8")).toBe(original);
    writeFileSync(
      path.join(output, "visual-check.json"),
      JSON.stringify(
        {
          result: "PASS",
          project_workspace_id: fixture.project_workspace_id,
          business_mutations: businessWrites,
          browser_errors: errors,
          measurements,
          original_business_uat_preserved: true,
          completed_at: new Date().toISOString(),
        },
        null,
        2
      )
    );
  } finally {
    await context.close();
  }
});
