import { expect, test } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

type Manifest = {
  tenant_id: number;
  project_workspace_id: number;
  password: string;
  users: Record<string, { email: string; password?: string }>;
};

const wave = process.env.E2E_O2B_CLOSE_WAVE;
const o2a = wave === "o2a";
const settings = o2a
  ? { apiPort: 8859, frontPort: 5519, module: "engineering", label: "Engineering Manager", role: "releaser" }
  : { apiPort: 8860, frontPort: 5520, module: "procurement", label: "Procurement Manager", role: "buyer" };
const fixturePath = o2a ? process.env.E2E_O2A_FIXTURE : process.env.E2E_O2B_FIXTURE;
const output = o2a ? process.env.E2E_O2A_OUTPUT : process.env.E2E_O2B_OUTPUT;

test("G01 project operational context preserves tenant and project identity in Chromium", async ({
  browser,
  request,
}) => {
  test.skip(!["o2a", "o2b"].includes(wave ?? "") || !fixturePath || !output, "Requires isolated closeout evidence");
  test.setTimeout(300_000);
  if (!fixturePath || !output) throw new Error("Missing isolated closeout fixture or output");
  const api = `http://127.0.0.1:${settings.apiPort}`;
  const base = `http://127.0.0.1:${settings.frontPort}`;
  expect(process.env.E2E_API_URL).toBe(api);
  expect(process.env.E2E_BASE_URL).toBe(base);
  const fixture = JSON.parse(readFileSync(fixturePath, "utf8")) as Manifest;
  const { tenant_id, project_workspace_id } = fixture;
  expect(project_workspace_id).toBeGreaterThan(0);
  expect(project_workspace_id).not.toBe(14);
  const user = fixture.users[settings.role];
  const login = await request.post(`${api}/api/v1/auth/login`, {
    data: { email: user.email, tenant_id, password: user.password ?? fixture.password },
    timeout: 120_000,
  });
  expect(login.status()).toBe(200);
  const auth = await login.json();
  const context = await browser.newContext({ baseURL: base, viewport: { width: 1440, height: 900 } });
  try {
    await context.addInitScript(
      (session) =>
        localStorage.setItem(
          "pypmis_auth",
          JSON.stringify({ state: { token: session.access_token, user: session.user }, version: 0 })
        ),
      auth
    );
    const page = await context.newPage();
    const root = `/workspaces/${project_workspace_id}`;
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const [opened] = await Promise.all([
      page.waitForResponse(
        (response) => response.url() === `${api}/api/v1${root}/open` && response.request().method() === "POST",
        { timeout: 120_000 }
      ),
      page.goto(`${root}/home`),
    ]);
    expect(opened.status()).toBe(200);
    const { identity, navigator } = await opened.json();
    expect(identity).toMatchObject({ tenant_id, workspace_id: project_workspace_id, workspace_type: "PROJECT" });
    expect(identity.workspace_status.toUpperCase()).toBe("ACTIVE");
    expect(navigator).toContainEqual(expect.objectContaining({ code: settings.module, state: "READY" }));
    await expect(page.getByRole("heading", { name: identity.workspace_name, exact: true }).first()).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Workspace Breadcrumb" })).toContainText(identity.workspace_name);
    await expect(page.getByRole("combobox", { name: "Switch Workspace" })).toHaveValue(String(project_workspace_id));
    const target = page
      .locator(".workspaceNavigator")
      .getByRole("button", { name: new RegExp(`^${settings.label} READY$`) });
    await expect(target).toBeEnabled();
    await target.click();
    await expect(page).toHaveURL(`${base}${root}/${settings.module}`);
    await expect(page.getByRole("region", { name: settings.label, exact: true })).toBeVisible();
    await expect(target).toHaveAttribute("aria-current", "page");
    expect(errors).toEqual([]);
    await page.screenshot({ path: path.join(output, "project-operational-context.png") });
    writeFileSync(
      path.join(output, "project-context.json"),
      JSON.stringify(
        {
          result: "PASS",
          tenant_id,
          project_workspace_id,
          navigation: settings.module,
          workspace_type: identity.workspace_type,
        },
        null,
        2
      ),
      { flag: "wx" }
    );
  } finally {
    await context.close();
  }
});
