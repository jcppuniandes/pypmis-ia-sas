import { expect, test, type Page } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

type SourcePin = {
  source_entity_type: string;
  source_entity_id: number;
  period_id: number;
  source_hash: string;
  adoption_id: number;
};

type ForecastPin = SourcePin & {
  consumer_version_id: number;
  signal_key: string;
  source_forecast_date: string;
};

type Fixture = {
  tenant_id: number;
  project_workspace_id: number;
  password: string;
  users: { manager: { email: string; password?: string } };
  progress: SourcePin;
  forecast: ForecastPin;
};

type Lookup = {
  source_type: string;
  source_id: number;
  source_version: number;
  source_hash: string;
  consumer_status: string;
  consumer_version_status: string | null;
  facts: { signals?: Record<string, string> };
};

type Decision = {
  id: number;
  tenant_id: number;
  project_workspace_id: number;
  consumer: string;
  source_entity_type: string;
  source_entity_id: number;
  source_hash: string;
  source_version: number;
  period_id: number;
  consumer_status: string;
  consumer_version_id: number | null;
  signal_key: string | null;
  source_forecast_date: string | null;
};

const api = "http://127.0.0.1:8860";
const base = "http://127.0.0.1:5520";
const fixturePath = process.env.E2E_CLOSE2_CONSUMER_FIXTURE;
const output = process.env.E2E_CLOSE2_CONSUMER_OUTPUT;

async function browserGet<T>(page: Page, url: string): Promise<T> {
  const result = await page.evaluate(async (url) => {
    const persisted = window.localStorage.getItem("pypmis_auth");
    if (!persisted) throw new Error("No authenticated application session");
    const auth = JSON.parse(persisted) as { state: { token: string } };
    const response = await window.fetch(url, {
      method: "GET",
      cache: "no-store",
      headers: { Authorization: `Bearer ${auth.state.token}` },
    });
    return { status: response.status, body: await response.json() };
  }, url);
  expect(result.status, new URL(url).pathname).toBe(200);
  return result.body as T;
}

test("CLOSE-2 operational Progress and Forecast read real adopted references in Chromium", async ({
  browser,
  request,
}) => {
  test.skip(!fixturePath || !output, "Requires isolated CLOSE-2 browser evidence");
  test.setTimeout(300_000);
  if (!fixturePath || !output) throw new Error("Missing isolated CLOSE-2 fixture or output");
  expect(process.env.E2E_API_URL).toBe(api);
  expect(process.env.E2E_BASE_URL).toBe(base);
  const fixture = JSON.parse(readFileSync(fixturePath, "utf8")) as Fixture;
  const { tenant_id, project_workspace_id, progress, forecast } = fixture;
  expect(project_workspace_id).toBeGreaterThan(14);
  expect(progress.source_entity_type).toBe("RECEIPT");
  expect(forecast.source_entity_type).toBe("MILESTONE_FORECAST");
  const user = fixture.users.manager;
  const login = await request.post(`${api}/api/v1/auth/login`, {
    data: { email: user.email, tenant_id, password: user.password ?? fixture.password },
    timeout: 120_000,
  });
  expect(login.status()).toBe(200);
  const session = await login.json();
  const context = await browser.newContext({ baseURL: base, viewport: { width: 1440, height: 1000 } });
  try {
    await context.addInitScript(
      (auth) =>
        localStorage.setItem(
          "pypmis_auth",
          JSON.stringify({ state: { token: auth.access_token, user: auth.user }, version: 0 })
        ),
      session
    );
    const page = await context.newPage();
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const route = `/workspaces/${project_workspace_id}`;
    const [opened] = await Promise.all([
      page.waitForResponse(
        (response) => response.url() === `${api}/api/v1${route}/open` && response.request().method() === "POST",
        { timeout: 120_000 }
      ),
      page.goto(`${route}/home`),
    ]);
    expect(opened.status()).toBe(200);
    const { identity, navigator } = await opened.json();
    expect(identity).toMatchObject({ tenant_id, workspace_id: project_workspace_id, workspace_type: "PROJECT" });
    for (const module of ["progress", "forecast"]) {
      expect(navigator).toContainEqual(expect.objectContaining({ code: module, state: "READY" }));
    }

    async function openConsumer(module: "progress" | "forecast", label: string) {
      const target = page.locator(".workspaceNavigator").getByRole("button", { name: new RegExp(`^${label} READY$`) });
      const root = `${api}/api/v1/${module}/projects/${project_workspace_id}`;
      const [overview] = await Promise.all([
        page.waitForResponse(
          (response) => response.url() === root + "/overview" && response.request().method() === "GET",
          { timeout: 120_000 }
        ),
        target.click(),
      ]);
      expect(overview.status()).toBe(200);
      await expect(page).toHaveURL(`${base}${route}/${module}`);
      await expect(target).toHaveAttribute("aria-current", "page");
      const region = page.getByRole("region", { name: label, exact: true });
      await expect(region).toBeVisible();
      await expect(region.getByRole("heading", { name: label, exact: true })).toBeVisible();
      return root + "/procurement-adoptions";
    }

    async function inspectReference(module: "progress" | "forecast", root: string, pin: SourcePin | ForecastPin) {
      const query = new URLSearchParams({
        source_entity_type: pin.source_entity_type,
        source_entity_id: String(pin.source_entity_id),
        period_id: String(pin.period_id),
      });
      if ("consumer_version_id" in pin) {
        query.set("consumer_version_id", String(pin.consumer_version_id));
        query.set("signal_key", pin.signal_key);
      }
      const lookup = await browserGet<Lookup>(page, `${root}/lookup?${query}`);
      expect(lookup).toMatchObject({
        source_type: pin.source_entity_type,
        source_id: pin.source_entity_id,
        source_hash: pin.source_hash,
        consumer_status: "ADOPTED",
      });
      expect(lookup.source_version).toBeGreaterThan(0);
      const history = await browserGet<{ items: Decision[] }>(page, root);
      const decision = history.items.find((item) => item.id === pin.adoption_id);
      expect(decision).toMatchObject({
        id: pin.adoption_id,
        tenant_id,
        project_workspace_id,
        consumer: module.toUpperCase(),
        source_entity_type: pin.source_entity_type,
        source_entity_id: pin.source_entity_id,
        source_hash: pin.source_hash,
        source_version: lookup.source_version,
        period_id: pin.period_id,
        consumer_status: "ADOPTED",
      });
      if ("consumer_version_id" in pin) {
        expect(lookup.consumer_version_status).toBe("DRAFT");
        expect(lookup.facts.signals?.[pin.signal_key]).toBe(pin.source_forecast_date);
        expect(decision).toMatchObject({
          consumer_version_id: pin.consumer_version_id,
          signal_key: pin.signal_key,
          source_forecast_date: pin.source_forecast_date,
        });
      }
      return { adoption_id: pin.adoption_id, source_hash: pin.source_hash, source_version: lookup.source_version };
    }

    const progressRoot = await openConsumer("progress", "Progress Manager");
    await page.getByLabel("Progress Controls Period", { exact: true }).selectOption(String(progress.period_id));
    const progressProof = await inspectReference("progress", progressRoot, progress);
    await page.screenshot({ path: path.join(output, "progress-consumer-context.png") });
    const forecastRoot = await openConsumer("forecast", "Forecast & Performance");
    await page.getByLabel("Forecast Version", { exact: true }).selectOption(String(forecast.consumer_version_id));
    await expect(page.getByRole("region", { name: "Forecast & Performance", exact: true })).toHaveAttribute(
      "aria-busy",
      "false"
    );
    const forecastProof = await inspectReference("forecast", forecastRoot, forecast);
    await page.screenshot({ path: path.join(output, "forecast-consumer-context.png") });
    expect(errors).toEqual([]);
    writeFileSync(
      path.join(output, "consumer-browser-proof.json"),
      JSON.stringify(
        {
          result: "PASS",
          tenant_id,
          project_workspace_id,
          progress: progressProof,
          forecast: { ...forecastProof, source_forecast_date: forecast.source_forecast_date },
          boundary: "Native module navigation; browser session GET for lookup and history; no consumer write",
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
