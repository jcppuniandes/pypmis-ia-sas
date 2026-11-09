// Real Chromium presentation recheck against the already published isolated O1C fixture.
// Run from the repository with: node scripts/wave-o1c/recheck_presentation.mjs
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repo = fileURLToPath(new URL("../../", import.meta.url));
const qa = path.join(repo, "outputs/.qa/wave-o1c-20261106");
const evidenceDirectory = path.join(qa, "chromium");
const require = createRequire(path.join(repo, "frontend/package.json"));
const { chromium, expect: baseExpect, request } = require("@playwright/test");
const expect = baseExpect.configure({ timeout: 60_000 });
const api = "http://127.0.0.1:8858";
const frontend = "http://127.0.0.1:5518";
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");
const fileDigest = (file) => digest(readFileSync(file));
const json = (file) =>
  JSON.parse(readFileSync(file, "utf8").replace(/^\uFEFF/, ""));

const fixture = json(path.join(qa, "browser-fixture.json"));
const businessEvidence = path.join(evidenceDirectory, "browser-uat.json");
const baselineEvidence = path.join(
  qa,
  "frontend-business-uat-source-proof.json",
);
const validationEvidence = path.join(qa, "frontend-validation.json");
const business = json(businessEvidence);
const baseline = json(baselineEvidence);
const validation = json(validationEvidence);
const inputEvidenceHashes = {
  business_uat_sha256: fileDigest(businessEvidence),
  business_source_proof_sha256: fileDigest(baselineEvidence),
  final_frontend_validation_sha256: fileDigest(validationEvidence),
};
assert.equal(
  business.result,
  "PASS",
  "Complete real business UAT must already have passed",
);
assert.deepEqual(business.browser_errors, []);
assert.equal(baseline.result, "PASS");
assert.equal(validation.result, "PASS");
assert.equal(validation.source_unchanged_during_validation, true);
assert.ok(
  validation.checks.length &&
    validation.checks.every((row) => row.exit_code === 0),
);

const oldSources = baseline.source_sha256;
const finalSources = validation.source_sha256;
assert.ok(Object.keys(finalSources).length, "No source inventory to validate");
assert.deepEqual(
  Object.keys(finalSources).sort(),
  Object.keys(oldSources).sort(),
  "Frontend inventory changed",
);
const approvedChanges = [
  "frontend/src/features/forecast-foundation/ReadPanels.tsx",
  "frontend/src/features/forecast-foundation/ReportingPanels.tsx",
  "frontend/src/features/forecast-foundation/forecastFoundation.css",
  "frontend/src/features/forecast-foundation/forecastFoundation.test.tsx",
].sort();
const changed = Object.keys(finalSources)
  .filter((file) => finalSources[file] !== oldSources[file])
  .sort();
assert.deepEqual(
  changed,
  approvedChanges,
  "Only the reviewed presentation files may differ from the business UAT",
);

function assertFreshSources() {
  for (const [file, hash] of Object.entries(finalSources)) {
    assert.ok(
      file.startsWith("frontend/") && !file.includes(".."),
      `Out-of-scope source: ${file}`,
    );
    assert.equal(
      fileDigest(path.join(repo, file)),
      hash,
      `Stale frontend evidence: ${file}`,
    );
  }
}
assertFreshSources();

const { project_workspace_id: project, forecast, report } = business.created;
assert.equal(project, fixture.project_workspace_id);
assert.notEqual(project, 14, "Never exercise Project 14");
assert.ok(
  [project, forecast, report].every((id) => Number.isSafeInteger(id) && id > 0),
);
assert.equal(business.created.period_id, fixture.period_id);
const manager = fixture.users.manager;
assert.ok(manager && manager.tenant_id === fixture.tenant_id);
const forecastRoot = `/api/v1/forecast/projects/${project}`;
const reportPath = `/api/v1/reporting/projects/${project}/reports/${report}`;
const moduleRoute = `/workspaces/${project}/forecast`;
const recentsRoute = `/api/v1/workspaces/${project}/open`;

const http = await request.newContext({ baseURL: api, timeout: 120_000 });
let browser;
try {
  // Authentication and opening the exact isolated workspace are the only non-GETs.
  const login = await http.post("/api/v1/auth/login", {
    data: {
      email: manager.email,
      tenant_id: manager.tenant_id,
      password: manager.password || fixture.password,
    },
  });
  assert.equal(login.status(), 200, "Isolated manager authentication failed");
  const session = await login.json();
  assert.equal(session.user.id, manager.id);

  async function get(route) {
    const response = await http.get(route, {
      headers: { Authorization: `Bearer ${session.access_token}` },
    });
    assert.equal(response.status(), 200, `Read request failed: ${route}`);
    return response.json();
  }

  async function frozenState() {
    const version = await get(`${forecastRoot}/versions/${forecast}`);
    const publication = await get(reportPath);
    const history = await get(`${forecastRoot}/history`);
    return { version, publication, history };
  }

  const before = await frozenState();
  assert.equal(before.version.status, "APPROVED");
  assert.equal(before.publication.status, "PUBLISHED");
  assert.equal(before.publication.forecast_version_id, forecast);
  assert.equal(before.version.content_hash, business.source_hashes.forecast);
  assert.equal(before.publication.content_hash, business.source_hashes.report);
  const curves = await get(
    `/api/v1/performance/projects/${project}/curves?forecast_version_id=${forecast}`,
  );
  const actualCost = curves.series.find((item) => item.code === "ACTUAL_COST");
  assert.equal(actualCost.status, "COMPUTABLE");
  assert.equal(actualCost.currency, "USD");
  assert.equal(
    actualCost.points.length,
    1,
    "Fixture must exercise a real single-point series",
  );

  const forecastAuditIds = (row) => ({
    forecast:
      row.entity_type === "ForecastVersion"
        ? row.entity_id
        : row.snapshot_json?.forecast_version_id,
    actor: row.created_by,
  });
  const auditFacts = ["FORECAST_APPROVED", "REPORT_PUBLISHED"].map((event) => {
    const matches = before.history.items.filter(
      (row) =>
        row.event_type === event && forecastAuditIds(row).forecast === forecast,
    );
    assert.equal(matches.length, 1, `Expected one original event for ${event}`);
    const ids = forecastAuditIds(matches[0]);
    assert.ok(
      Number.isSafeInteger(ids.actor) && ids.actor > 0,
      `No actor reference for ${event}`,
    );
    return { event, ...ids };
  });
  assert.equal(auditFacts[0].actor, before.version.approved_by);
  assert.equal(auditFacts[1].actor, before.publication.published_by);

  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    serviceWorkers: "block",
  });
  await context.addInitScript((value) => {
    localStorage.setItem(
      "pypmis_auth",
      JSON.stringify({
        state: { token: value.access_token, user: value.user },
        version: 0,
      }),
    );
  }, session);
  const navigationRequests = [],
    blockedWrites = [],
    browserErrors = [];
  await context.route("**/*", (route) => {
    const req = route.request();
    const method = req.method();
    const url = new URL(req.url());
    if (["GET", "HEAD", "OPTIONS"].includes(method)) return route.continue();
    if (
      method === "POST" &&
      [api, frontend].includes(url.origin) &&
      url.pathname === recentsRoute
    ) {
      navigationRequests.push({ method, path: url.pathname });
      return route.continue();
    }
    blockedWrites.push({ method, path: url.pathname });
    return route.abort("blockedbyclient");
  });
  const page = await context.newPage();
  page.setDefaultTimeout(60_000);
  page.on("pageerror", (error) => browserErrors.push(error.message));
  await page.goto(`${frontend}${moduleRoute}`, { timeout: 120_000 });
  await expect(
    page.getByRole("heading", { name: "Forecast & Performance", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Forecast Version", { exact: true })
    .selectOption(String(forecast));
  await expect(page.getByLabel("Forecast Code", { exact: true })).toHaveValue(
    before.version.code,
  );
  await expect(
    page.getByLabel("Forecast Name", { exact: true }),
  ).toBeDisabled();

  const nav = page.getByRole("navigation", {
    name: "Forecast & Performance submodules",
  });
  const screenshots = {};
  async function screenshot(name) {
    const file = path.join(evidenceDirectory, `presentation-${name}.png`);
    await page.screenshot({
      path: file,
      fullPage: true,
      animations: "disabled",
    });
    screenshots[path.basename(file)] = fileDigest(file);
  }
  async function layout(panel) {
    const actions = page.locator(".forecastFoundation .forecastEditorActions");
    await expect(actions).toHaveCount(1);
    const measurements = await actions.evaluate((element) => {
      const sibling = element.previousElementSibling;
      const content = sibling?.getBoundingClientRect();
      const action = element.getBoundingClientRect();
      return {
        width: innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        position: getComputedStyle(element).position,
        contentBottom: content?.bottom,
        actionTop: action.top,
        priorElement: sibling?.tagName,
      };
    });
    assert.equal(
      measurements.position,
      "static",
      `${panel}: no sticky overlay`,
    );
    assert.equal(
      measurements.priorElement,
      "SECTION",
      `${panel}: expected rendered panel immediately before actions`,
    );
    assert.ok(
      measurements.actionTop >= measurements.contentBottom - 1,
      `${panel}: actions cover panel content`,
    );
    assert.ok(
      measurements.documentWidth <= measurements.width + 2,
      `${panel}: document has horizontal overflow`,
    );
    return measurements;
  }

  const viewports = {};
  for (const [name, width, height] of [
    ["desktop", 1440, 1000],
    ["mobile", 390, 844],
  ]) {
    await page.setViewportSize({ width, height });
    await nav
      .getByRole("button", { name: "Reporting History", exact: true })
      .click();
    const reports = page.getByRole("table", {
      name: "Published Period Reports",
      exact: true,
    });
    await reports
      .getByRole("button", {
        name: `Ver Published Period Reports ${report}`,
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("region", { name: "Reporting History", exact: true }),
    ).toContainText(before.publication.content_hash);
    const audit = page.getByRole("table", {
      name: "Forecast Audit History",
      exact: true,
    });
    await expect(
      audit.getByRole("columnheader", { name: "Forecast", exact: true }),
    ).toBeVisible();
    await expect(
      audit.getByRole("columnheader", { name: "Actor", exact: true }),
    ).toBeVisible();
    for (const fact of auditFacts) {
      const row = audit.getByRole("row").filter({
        has: page.getByRole("cell", { name: fact.event, exact: true }),
      });
      await expect(row).toHaveCount(1);
      await expect(row.getByRole("cell").nth(1)).toHaveText(
        String(fact.forecast),
      );
      await expect(row.getByRole("cell").nth(3)).toHaveText(String(fact.actor));
    }
    const reportingLayout = await layout("Reporting History");
    await audit
      .getByRole("columnheader", { name: "Actor", exact: true })
      .scrollIntoViewIfNeeded();
    await screenshot(`audit-${name}`);

    await nav.getByRole("button", { name: "S-Curves", exact: true }).click();
    const chart = page.getByRole("img", {
      name: "ACTUAL_COST S-Curve USD",
      exact: true,
    });
    await expect(chart).toBeVisible();
    await expect(chart.locator("circle")).toHaveCount(1);
    await expect(chart.locator("circle")).toBeVisible();
    await expect(chart.locator("polyline")).toHaveCount(0);
    const points = page.getByRole("table", {
      name: "ACTUAL_COST Curve Points",
      exact: true,
    });
    await expect(points.locator("tbody tr")).toHaveCount(1);
    await expect(
      points.locator("tbody tr").getByRole("cell").nth(2),
    ).toHaveText(String(actualCost.points[0].cumulative_value));
    const curveLayout = await layout("S-Curves");
    await screenshot(`single-point-curve-${name}`);

    await nav
      .getByRole("button", { name: "Project Controls Dashboard", exact: true })
      .click();
    await expect(
      page.getByRole("table", {
        name: "Project Controls Dashboard Metrics",
        exact: true,
      }),
    ).toBeVisible();
    const dashboardLayout = await layout("Project Controls Dashboard");
    await screenshot(`dashboard-actions-${name}`);
    viewports[name] = {
      width,
      height,
      documentWidth: Math.max(
        reportingLayout.documentWidth,
        curveLayout.documentWidth,
        dashboardLayout.documentWidth,
      ),
      panels: {
        reporting: reportingLayout,
        curves: curveLayout,
        dashboard: dashboardLayout,
      },
    };
  }

  const after = await frozenState();
  assert.deepEqual(
    after,
    before,
    "Presentation recheck modified approved data or the audit history",
  );
  assert.deepEqual(blockedWrites, [], "Browser attempted a business mutation");
  assert.deepEqual(browserErrors, [], "Unexpected Chromium page error");
  assertFreshSources();
  assert.deepEqual(inputEvidenceHashes, {
    business_uat_sha256: fileDigest(businessEvidence),
    business_source_proof_sha256: fileDigest(baselineEvidence),
    final_frontend_validation_sha256: fileDigest(validationEvidence),
  });
  const proof = {
    result: "PASS",
    scope: "READ_ONLY_PRESENTATION_RECHECK_REUSES_PASSED_BUSINESS_UAT",
    project_workspace_id: project,
    forecast_id: forecast,
    report_id: report,
    checked_at_utc: new Date().toISOString(),
    business_responses_mocked: false,
    business_write_attempts: blockedWrites,
    non_business_requests: [
      { method: "POST", path: "/api/v1/auth/login" },
      ...navigationRequests,
    ],
    browser_errors: browserErrors,
    frozen_content_hashes: {
      forecast: {
        before: before.version.content_hash,
        after: after.version.content_hash,
      },
      report: {
        before: before.publication.content_hash,
        after: after.publication.content_hash,
      },
      audit_history: {
        before: digest(JSON.stringify(before.history)),
        after: digest(JSON.stringify(after.history)),
      },
    },
    audit_facts: auditFacts,
    single_point_curve: {
      code: actualCost.code,
      currency: actualCost.currency,
      value: actualCost.points[0].cumulative_value,
    },
    ...viewports,
    screenshot_sha256: screenshots,
    presentation_changes_from_business_uat: changed,
    ...inputEvidenceHashes,
    source_sha256: finalSources,
  };
  const output = path.join(evidenceDirectory, "presentation-recheck.json");
  writeFileSync(output, JSON.stringify(proof, null, 2) + "\n");
  console.log(
    JSON.stringify({
      result: proof.result,
      screenshots: Object.keys(screenshots).length,
      evidence: output,
    }),
  );
} finally {
  try {
    await browser?.close();
  } finally {
    await http.dispose();
  }
}
