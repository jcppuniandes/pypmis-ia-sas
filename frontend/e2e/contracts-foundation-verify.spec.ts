import { expect, test } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const manifest = process.env.E2E_O2C_FIXTURE;
const evidence = process.env.E2E_O2C_VERIFY_PROOF;

test("O2C settled UI preserves approved versions and partial certificate", async ({ browser, request }) => {
  test.skip(!manifest || !evidence, "Requires an already completed isolated O2C browser chain.");
  test.setTimeout(600_000);
  if (!manifest || !evidence) throw new Error("Missing isolated verification inputs");
  const fixture = JSON.parse(readFileSync(manifest, "utf8"));
  const previous = JSON.parse(readFileSync(evidence, "utf8"));
  expect(previous.result).toBe("PASS");
  expect(previous.observations.project_workspace_id).toBe(fixture.project_workspace_id);
  expect(fixture.project_workspace_id).not.toBe(14);
  const out = path.resolve(process.env.E2E_O2C_OUTPUT || "../outputs/.qa/wave-o2c-20261118/readonly-ui");
  mkdirSync(out, { recursive: true });
  const api = process.env.E2E_API_URL || "http://127.0.0.1:8862";
  const app = process.env.E2E_BASE_URL || "http://127.0.0.1:5522";
  expect(new URL(api).port).not.toBe("8000");
  expect(new URL(app).port).not.toBe("5173");
  const login = await request.post(`${api}/api/v1/auth/login`, {
    data: { email: fixture.users.approver, tenant_id: fixture.tenant_id, password: fixture.password },
  });
  expect(login.status()).toBe(200);
  const auth = await login.json();
  const context = await browser.newContext({ baseURL: app, viewport: { width: 1440, height: 1000 } });
  const observations: Record<string, unknown> = {};
  let passed = false;
  try {
    await context.addInitScript((value) => {
      localStorage.setItem(
        "pypmis_auth",
        JSON.stringify({ state: { token: value.access_token, user: value.user }, version: 0 })
      );
    }, auth);
    const page = await context.newPage();
    await page.goto(`/workspaces/${fixture.project_workspace_id}/contracts`);
    const nav = page.getByRole("navigation", { name: "Contracts Manager submodules" });
    await expect(nav).toBeVisible({ timeout: 180_000 });
    for (const [label, collection, identity, expected] of [
      ["Contracts", "contracts", previous.observations.contract_id, "EFFECTIVE"],
      ["Payment Certificates", "payment-certificates", previous.observations.certificate_id, "APPROVED"],
      ["Finance References", "finance-references", previous.observations.finance_reference_id, null],
    ] as const) {
      await nav.getByRole("button", { name: label, exact: true }).click();
      const area = page.getByRole("region", { name: label, exact: true });
      const row = area
        .getByRole("table", { name: label, exact: true })
        .locator(`tbody tr:has(td:first-child:text-is("${identity}"))`);
      const [response] = await Promise.all([
        page.waitForResponse((item) => new URL(item.url()).pathname.endsWith(`/${collection}/${identity}`)),
        row.getByRole("button", { name: /^Ver / }).click(),
      ]);
      expect(response.status()).toBe(200);
      const record = await response.json();
      const detail = area.getByRole("region", { name: "Detalle contractual" });
      if (expected) {
        expect(record.status).toBe(expected);
        await expect(detail).toContainText(expected);
      }
      if (collection === "contracts")
        expect(record.current_version_id).toBe(previous.observations.resulting_contract_version_id);
      if (collection === "payment-certificates") {
        expect(Number(record.net_amount)).toBeCloseTo(
          (Math.min(Number(fixture.progress_quantity), 1) / 2) * 100 * 0.9,
          8
        );
        await expect(detail).toContainText(String(Number(record.net_amount)));
      }
      if (collection === "finance-references") {
        expect(record.payment_status).toBe("UNPAID");
        await expect(detail).toContainText("UNPAID");
      }
      observations[collection] = { id: record.id, status: record.status, version: record.version };
      await page.screenshot({ path: path.join(out, `${collection}-settled.png`), fullPage: true });
    }
    await nav.getByRole("button", { name: "Contract Versions", exact: true }).click();
    const versions = page.getByRole("table", { name: "Contract Versions", exact: true });
    for (const identity of [
      previous.observations.initial_contract_version_id,
      previous.observations.resulting_contract_version_id,
    ]) {
      await expect(versions.locator(`tbody tr:has(td:first-child:text-is("${identity}"))`)).toBeVisible();
    }
    await page.screenshot({ path: path.join(out, "versions-settled.png"), fullPage: true });
    passed = true;
  } finally {
    writeFileSync(
      path.join(out, "readonly-verification.json"),
      JSON.stringify(
        {
          result: passed ? "PASS" : "FAIL",
          domain_mutations: 0,
          navigation_side_effects: "Normal workspace.open may update recent access and navigation audit only",
          observations,
        },
        null,
        2
      )
    );
    await context.close();
  }
});
