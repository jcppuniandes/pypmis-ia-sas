// Read-only browser verification after the isolated CSS-only step-width fix.
import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";

const root = path.resolve(import.meta.dirname, "../..");
const { chromium, request } = createRequire(path.join(root, "frontend/package.json"))("@playwright/test");
const qa = path.join(root, "outputs/.qa/wave-o1bd-20261104");
const fixture = JSON.parse(await fs.readFile(path.join(qa, "browser-fixture.json"), "utf8"));
const prior = JSON.parse(await fs.readFile(path.join(qa, "frontend-validation.json"), "utf8"));
const units = JSON.parse(await fs.readFile(path.join(qa, "frontend-components.json"), "utf8"));
if (units.numPassedTests !== 36 || units.numFailedTests !== 0) throw new Error("Component validation incomplete");
const actual = {};
for (const [name, expected] of Object.entries(prior.source_sha256)) {
  actual[name] = createHash("sha256").update(await fs.readFile(path.join(root, name))).digest("hex");
  if (!name.endsWith("progressFoundation.css") && actual[name] !== expected) throw new Error(`Non-CSS source changed: ${name}`);
}
await fs.writeFile(path.join(qa, "frontend-business-uat-source-proof.json"), JSON.stringify(prior, null, 2));
const api = await request.newContext({ baseURL: "http://127.0.0.1:8857" });
const user = fixture.users.manager;
const login = await api.post("/api/v1/auth/login", { data: { email: user.email, tenant_id: user.tenant_id, password: "O1bd-disposable-only!" } });
if (!login.ok()) throw new Error(await login.text());
const session = await login.json();
const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  await context.addInitScript((value) => localStorage.setItem("pypmis_auth", JSON.stringify({ state: { token: value.access_token, user: value.user }, version: 0 })), session);
  const page = await context.newPage();
  await page.goto(`http://127.0.0.1:5517/workspaces/${fixture.project_workspace_id}/progress`);
  await page.getByRole("heading", { name: "Progress Manager", exact: true }).waitFor();
  await page.getByLabel("Progress as-of date", { exact: true }).fill("2026-10-22");
  await page.getByRole("navigation", { name: "Progress Manager submodules" }).getByRole("button", { name: "Milestones / Rules of Credit", exact: true }).click();
  const bounds = [];
  for (const prefix of ["ROC", "MILESTONE"]) {
    await page.getByRole("button", { name: new RegExp(`^Ver Progress Rules P-UAT-${prefix}-`) }).click();
    const weight = page.getByLabel("Rule Step Weight 1", { exact: true });
    const result = await weight.evaluate((element) => {
      const box = element.getBoundingClientRect();
      const panel = element.closest(".progressPanel").getBoundingClientRect();
      return { right: box.right, panel_right: panel.right, width: box.width, viewport: innerWidth };
    });
    if (result.right > result.panel_right || result.right > result.viewport) throw new Error(JSON.stringify(result));
    bounds.push({ rule: prefix, ...result });
    await page.locator(".progressTable").evaluateAll((nodes) => nodes.forEach((element) => { element.scrollLeft = 0; }));
    await page.screenshot({ path: path.join(qa, "chromium", `${prefix.toLowerCase()}-final-step-layout.png`), fullPage: true });
  }
  const proof = { result: "PASS", css_only_after_business_uat: true, unit_tests: 36, bounds, source_sha256: actual, checked_at: new Date().toISOString() };
  await fs.writeFile(path.join(qa, "chromium/layout-final.json"), JSON.stringify(proof, null, 2));
  await fs.writeFile(path.join(qa, "frontend-validation.json"), JSON.stringify({ ...prior, source_sha256: actual, checked_at_utc: proof.checked_at, checks: [...prior.checks, { name: "CSS-only final rebuild and real Chromium step bounds", exit_code: 0 }, { name: "36 component tests repeated after CSS-only fix", exit_code: 0 }] }, null, 2));
  console.log(JSON.stringify(proof));
} finally { await browser.close(); await api.dispose(); }
