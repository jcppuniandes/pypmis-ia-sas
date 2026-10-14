import { expect, type APIResponse, type Locator, type Page, type Response, test } from "@playwright/test";

// Real Chromium -> isolated API/PostgreSQL. No route interception or simulated
// provider result. Actual Cost/Schedule calculations occurred in fixture setup.
const api = process.env.E2E_API_URL || "http://127.0.0.1:8830";
const password = process.env.E2E_QRA_PASSWORD || "1234";
type Json = Record<string, unknown>;
type Revision = Json & { id: number; revision_version: number; status: string; content_hash: string };
type Policy = Json & { id: number; version: number; status: string; content_json: Json; content_hash: string };
type Preparation = Revision & {
  portfolio_workspace_id: number;
  investment_gate_profile_id: number;
  preparation_hash: string;
  evidence: Json[];
  source_snapshot: { evidence_policy: { policy_id: number } };
};
let portfolioId = 0;
let projectId = 0;
let caseId = 0;
let profileId = 0;
let baselinePolicyId = 0;
let historical: Preparation;
let published: Policy;
let frozen: Preparation;
let preparedGate: Preparation | undefined;
const key = (action: string) => `qra-evidence-browser-${action}-${Date.now()}`;
async function body<T>(response: APIResponse | Response, status = 200): Promise<T> {
  expect(response.status(), await response.text()).toBe(status);
  return (await response.json()) as T;
}
async function login(page: Page, user = "admin") {
  await expect
    .poll(
      async () => {
        try {
          return (await page.request.get(`${api}/api/v1/health/ready`, { timeout: 5000 })).status();
        } catch {
          return 0;
        }
      },
      { timeout: 120_000, intervals: [1000, 2000] }
    )
    .toBe(200);
  await page.goto("/login");
  await page.getByLabel("User").fill(user);
  await page.getByLabel("Password").fill(password);
  const waiting = page.waitForResponse(
    (response) => response.url().includes("/api/v1/auth/login") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /sign in/i }).click();
  const result = await body<{ access_token: string }>(await waiting);
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
  return result.access_token;
}
async function mutation<T>(page: Page, endpoint: string, button: Locator, status = 200) {
  const waiting = page.waitForResponse(
    (response) => response.url().endsWith(endpoint) && response.request().method() !== "GET"
  );
  await button.click();
  return await body<T>(await waiting, status);
}
async function discover(page: Page, token: string) {
  const headers = { Authorization: `Bearer ${token}` };
  const preparations = await body<Preparation[]>(
    await page.request.get(`${api}/api/v1/investment-gate-preparations`, { headers })
  );
  historical = preparations.find((row) => row.status === "FROZEN")!;
  expect(historical).toBeTruthy();
  portfolioId = historical.portfolio_workspace_id;
  profileId = historical.investment_gate_profile_id;
  const policies = await body<Policy[]>(
    await page.request.get(`${api}/api/v1/investment-evidence-policy/configurations`, { headers })
  );
  const active = policies.filter((row) => {
    if (row.status !== "published") return false;
    const scope = row.content_json.scope as { type: string; workspace_id?: number };
    return scope.type === "tenant" || (scope.type === "portfolio" && scope.workspace_id === portfolioId);
  });
  const scoped = active.filter((row) => (row.content_json.scope as { type: string }).type === "portfolio");
  const source = scoped.length ? scoped : active;
  // An isolated fixture must expose one current governed source. Historical
  // packages may intentionally retain an older SUPERSEDED policy revision.
  expect(source).toHaveLength(1);
  baselinePolicyId = source[0].id;
  const cases = await body<Array<{ id: number; project_workspace_id: number; current_revision: Revision }>>(
    await page.request.get(`${api}/api/v1/business-cases`, { headers })
  );
  caseId = cases[0].id;
  projectId = cases[0].project_workspace_id;
  // Retry-safe fixture recovery follows the real author/reviewer lifecycle;
  // it never patches a COMPLETED record, a readiness flag or a source hash.
  let pending = cases[0].current_revision;
  if (pending.status === "DRAFT" || pending.status === "IN_REVIEW") {
    if (pending.status === "DRAFT") {
      pending = await body<Revision>(
        await page.request.post(`${api}/api/v1/business-case-revisions/${pending.id}/submit-review`, {
          headers: { ...headers, "If-Match": `"${pending.revision_version}"` },
          data: { idempotency_key: key("fixture-recover-submit") },
        })
      );
    }
    const reviewer = await body<{ access_token: string }>(
      await page.request.post(`${api}/api/v1/auth/login`, {
        data: { email: "qra.evidence.reviewer@demo.local", password },
      })
    );
    pending = await body<Revision>(
      await page.request.post(`${api}/api/v1/business-case-revisions/${pending.id}/complete`, {
        headers: { Authorization: `Bearer ${reviewer.access_token}`, "If-Match": `"${pending.revision_version}"` },
        data: { idempotency_key: key("fixture-recover-complete") },
      })
    );
    expect(pending.status).toBe("COMPLETED");
  }
}
async function openGate(page: Page, preparationId: number) {
  await page.goto("/app/strategy/investment-gate-preparation");
  const gate = page.getByRole("region", { name: "Investment Gate Preparation", exact: true });
  await expect(gate).toBeVisible();
  await gate.getByRole("combobox", { name: /^Portfolio/ }).selectOption(String(portfolioId));
  await gate.getByRole("combobox", { name: /^Preparation/ }).selectOption(String(preparationId));
  return gate;
}
async function createIndependentlyReviewedGateDraft(page: Page, authorToken: string, reviewerToken: string) {
  const headers = { Authorization: `Bearer ${authorToken}` };
  const created = await body<Preparation>(
    await page.request.post(`${api}/api/v1/investment-gate-preparations`, {
      headers,
      data: {
        portfolio_workspace_id: portfolioId,
        investment_gate_profile_id: profileId,
        name: "Contextual QRA browser new FFA preparation",
        idempotency_key: key("gate-create"),
      },
    })
  );
  let preparation = created;
  // The serial workflow prepares its normal API draft after BC completion.
  // Preserve VALID FEL/Risk providers and independently validate only the
  // existing manual Class B requirements. Never provide QRA Class A manually.
  for (const item of preparation.evidence.filter(
    (row) => row.classification === "B" && row.blocking && row.status !== "VALID"
  )) {
    preparation = await body<Preparation>(
      await page.request.post(`${api}/api/v1/investment-gate-preparations/${created.id}/evidence`, {
        headers: { ...headers, "If-Match": `"${preparation.revision_version}"` },
        data: {
          requirement_key: item.requirement_key,
          scope_type: item.scope_type,
          scope_id: item.scope_id,
          reference_id: key("controlled-manual"),
          evidence_date: new Date().toISOString(),
          issuer: "Disposable independent authority",
          owner: "Portfolio governance",
          summary: "Explicit current independently validated Class B evidence, never QRA Class A.",
          evidence_refs: [{ reference: "DISPOSABLE-B-GOVERNANCE" }],
          idempotency_key: key("manual-create"),
        },
      })
    );
    const submitted = preparation.evidence.find((row) => row.id === item.id)!;
    preparation = await body<Preparation>(
      await page.request.post(`${api}/api/v1/investment-gate-evidence/${submitted.id}/validate`, {
        headers: { Authorization: `Bearer ${reviewerToken}`, "If-Match": `"${preparation.revision_version}"` },
        data: {
          decision: "VALID",
          validation_note: "Independent review of scope, authority and currentness.",
          idempotency_key: key("manual-validate"),
        },
      })
    );
  }
  expect(preparation.status).toBe("IN_PREPARATION");
  return preparation;
}
function evidenceText(value: unknown): string {
  if (value == null || value === "") return "NOT CAPTURED";
  if (typeof value === "boolean") return value ? "YES" : "NO";
  if (Array.isArray(value)) return value.map(evidenceText).join(" · ") || "None";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
async function assertCapturedSummary(page: Page, summary: Locator, source: Json) {
  expect(source.provider_key).toBe("QRA_RESULT_PROVIDER");
  expect(source.classification).toBe("A");
  expect(source.analysis_scope).toBeTruthy();
  expect((source.selected_percentiles as Json[]).length).toBeGreaterThan(0);
  const convergence = source.convergence as Json;
  const applicability = source.qra_applicability as Json;
  expect(applicability.capability_fit).toBe(
    source.analysis_type === "SCHEDULE_QRA" ? "SUPPORTED_WITH_LIMITATIONS" : "SUPPORTED"
  );
  for (const [label, value] of [
    ["Provider", source.provider_key],
    ["Evidence class", source.classification],
    ["Engine capability fit", applicability.capability_fit],
    ["Analysis type", source.analysis_type],
    ["Scope", source.analysis_scope],
    ["Convergence", source.convergence_status || convergence.status],
    ["Analytical readiness", source.analytical_readiness || source.readiness],
  ]) {
    const field = summary.locator("dl > div").filter({ has: page.getByText(String(label), { exact: true }) });
    await expect(field.locator("dd")).toHaveText(evidenceText(value));
  }
  const numbers = summary.locator(".qraEvidenceNumbers");
  await expect(
    numbers
      .locator("div")
      .filter({ has: page.getByText("Selected percentiles", { exact: true }) })
      .locator("span")
  ).toHaveText(evidenceText(source.selected_percentiles));
  await expect(
    numbers
      .locator("div")
      .filter({ has: page.getByText("Target probabilities", { exact: true }) })
      .locator("span")
  ).toHaveText(evidenceText(source.target_probabilities));
  await expect(summary.locator("p").filter({ has: page.getByText("Warnings:", { exact: true }) })).toHaveText(
    `Warnings: ${evidenceText(source.warnings || [])}`
  );
  await expect(summary.locator("p").filter({ has: page.getByText("Blockers:", { exact: true }) })).toHaveText(
    `Blockers: ${evidenceText(source.blockers || [])}`
  );
}
async function assertSourceLink(page: Page, summary: Locator, analysisType: string, token: string, navigate = false) {
  const link = summary.getByRole("link", { name: "View QRA", exact: true });
  await expect(link).toBeVisible();
  const href = await link.getAttribute("href");
  expect(href).toBeTruthy();
  const target = new URL(href!, "http://127.0.0.1:5533");
  expect(target.searchParams.get("project_id")).toBe(String(projectId));
  const runId = Number(target.searchParams.get("run_id"));
  expect(runId).toBeGreaterThan(0);
  const run = await body<Json>(
    await page.request.get(`${api}/api/v1/qra-engine/runs/${runId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
  );
  expect(run.project_id).toBe(projectId);
  expect(run.analysis_type).toBe(analysisType);
  expect(run.status).toBe("COMPLETED");
  expect(run.review_status).toBe("ACCEPTED");
  if (navigate) {
    // A real modified link click opens the source in the same user's context.
    // Preserve the parent snapshot instead of reloading its expensive overview
    // after every analytical reference read. No authority or timeout is changed.
    const opening = page.context().waitForEvent("page");
    await link.click({ modifiers: ["ControlOrMeta"] });
    const sourcePage = await opening;
    try {
      await expect(sourcePage).toHaveURL(
        (url) =>
          url.searchParams.get("project_id") === String(projectId) && url.searchParams.get("run_id") === String(runId)
      );
      const engine = sourcePage.getByRole("region", { name: "QRA Calculation Engine workspace", exact: true });
      await expect(engine).toBeVisible();
      await expect(engine.getByRole("combobox", { name: /^Project Workspace/ })).toHaveValue(String(projectId));
      await expect(engine.getByRole("combobox", { name: /^Selected QRA run/ })).toHaveValue(String(runId));
      await expect(engine).toContainText(String(run.run_number));
      await expect(engine).toContainText(analysisType);
      await expect(engine).toContainText("ACCEPTED");
    } finally {
      await sourcePage.close();
    }
    await expect(summary).toBeVisible();
  }
}

test.use({ trace: "on" });
test.describe.serial("Contextual QRA evidence real strategic stack", () => {
  test("ADMIN clones/configures Cost and Schedule QRA, previews without persistence and publishes a new revision", async ({
    page,
  }, testInfo) => {
    test.setTimeout(300_000);
    const token = await login(page);
    await discover(page, token);
    await page.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }).click();
    await page.goto("/app/admin/strategy/investment-decision-evidence-policy");
    const admin = page.getByRole("region", { name: "Evidence & Decision Policy", exact: true });
    await expect(admin).toBeVisible();
    await admin.getByLabel("Policy revision", { exact: true }).selectOption(String(baselinePolicyId));
    const clone = await mutation<Policy>(
      page,
      `/api/v1/investment-evidence-policy/configurations/${baselinePolicyId}/clone`,
      admin.getByRole("button", { name: "Clone DRAFT", exact: true })
    );
    await admin.getByLabel("Evidence policy Portfolio", { exact: true }).selectOption(String(portfolioId));
    await admin.getByLabel("Investment Gate Profile", { exact: true }).selectOption("PYP-FFA");
    await admin.getByRole("button", { name: "QRA Applicability", exact: true }).click();
    for (const prefix of ["Cost QRA", "Schedule QRA"]) {
      const addRequirement = admin.getByRole("button", { name: `Add ${prefix} requirement`, exact: true });
      if (await addRequirement.count()) await addRequirement.click();
      await admin.getByLabel(`${prefix} applicability`, { exact: true }).selectOption("REQUIRED");
      const evidenceClass = admin.getByLabel(`${prefix} evidence class`, { exact: true });
      for (const classification of ["A", "B", "C", "A"]) {
        await evidenceClass.selectOption(classification);
        await expect(evidenceClass).toHaveValue(classification);
        await expect(admin.getByLabel(`${prefix} applicability`, { exact: true })).toHaveValue(
          classification === "C" ? "NOT_REQUIRED" : "REQUIRED"
        );
      }
      await admin.getByLabel(`${prefix} Governance Model`, { exact: true }).selectOption(["CAPITAL_OWNER"]);
      await admin.getByLabel(`${prefix} Project Type`, { exact: true }).selectOption(["COMMERCIAL"]);
      await admin.getByLabel(`${prefix} FEL Stage`, { exact: true }).selectOption(["FEL-3"]);
      const convergence = admin.getByLabel(`${prefix} convergence`, { exact: true });
      for (const requirement of ["REQUIRED", "WARNING_ALLOWED"]) {
        await convergence.selectOption(requirement);
        await expect(convergence).toHaveValue(requirement);
      }
      const scope = admin.getByLabel(`${prefix} scope requirement`, { exact: true });
      for (const requirement of ["PARTIAL_ALLOWED", "WHOLE_PROJECT"]) {
        await scope.selectOption(requirement);
        await expect(scope).toHaveValue(requirement);
      }
      await admin.getByLabel(`${prefix} analytical readiness`, { exact: true }).selectOption("WARNINGS_ALLOWED");
      await admin.getByLabel(`${prefix} selected percentiles`, { exact: true }).selectOption(["50", "80", "90"]);
    }
    await admin.getByLabel("Cost QRA applicability", { exact: true }).selectOption("CONDITIONAL");
    await admin.getByLabel("Cost QRA Risk", { exact: true }).selectOption(["HIGH"]);
    await admin.getByLabel("Cost QRA value band enabled", { exact: true }).check();
    await admin.getByLabel("Cost QRA value currency", { exact: true }).fill("USD");
    await admin.getByLabel("Cost QRA value minimum", { exact: true }).fill("50000000");
    await admin.getByRole("button", { name: "Add Cost QRA decision criterion", exact: true }).click();
    const newCriterion = admin.getByRole("article", { name: /^QRA criterion / }).last();
    // Exercise governed probability editing without inventing a target in the
    // accepted fixture run. Restore the actual blocking percentile hurdle
    // before Save; numeric probability evaluation is covered by backend tests.
    await newCriterion.getByLabel(/^QRA criterion .* metric$/).selectOption("TARGET_PROBABILITY");
    await newCriterion.getByLabel(/^QRA criterion .* expected probability$/).fill("0.8");
    await newCriterion.getByLabel(/^QRA criterion .* operator$/).selectOption("GREATER_THAN_OR_EQUAL");
    await expect(newCriterion.getByLabel(/^QRA criterion .* metric$/)).toHaveValue("TARGET_PROBABILITY");
    await expect(newCriterion.getByLabel(/^QRA criterion .* expected probability$/)).toHaveValue("0.8");
    await newCriterion.getByLabel(/^QRA criterion .* metric$/).selectOption("PERCENTILE");
    await newCriterion.getByLabel(/^QRA criterion .* operator$/).selectOption("LESS_THAN_OR_EQUAL");
    await newCriterion.getByLabel(/^QRA criterion .* target$/).fill("1000000000");
    await newCriterion.getByLabel(/^QRA criterion .* currency$/).fill("USD");
    await newCriterion.getByLabel(/^QRA criterion .* percentile$/).fill("90");
    await newCriterion.getByLabel(/^QRA criterion .* blocking$/).check();
    const saved = await mutation<Policy>(
      page,
      `/api/v1/investment-evidence-policy/configurations/${clone.id}`,
      admin.getByRole("button", { name: "Save", exact: true })
    );
    const savedProfiles = saved.content_json.gate_profiles as Record<string, { requirements: Json[] }>;
    const savedRequirements = savedProfiles["PYP-FFA"].requirements.filter(
      (row) => row.provider_key === "QRA_RESULT_PROVIDER"
    );
    expect(savedRequirements).toHaveLength(2);
    for (const row of savedRequirements) {
      expect(row.classification).toBe("A");
      expect(row.allow_manual_reference).toBe(false);
      expect(row.qra_policy).toMatchObject({ convergence: "WARNING_ALLOWED", scope_requirement: "WHOLE_PROJECT" });
    }
    const preview = await mutation<Json>(
      page,
      `/api/v1/investment-evidence-policy/configurations/${clone.id}/preview`,
      admin
        .getByRole("group", { name: "Evidence policy actions", exact: true })
        .getByRole("button", { name: "Preview", exact: true })
    );
    expect(preview.persisted).toBe(false);
    const matrix = preview.effective_matrix as Json[];
    expect(matrix.filter((row) => row.provider_key === "QRA_RESULT_PROVIDER")).toHaveLength(2);
    const qraCriteria = (preview.decision_criteria as Json[]).filter((row) => row.qra_criterion);
    expect(qraCriteria.length).toBeGreaterThan(0);
    for (const criterion of qraCriteria) {
      const evaluations = criterion.preview_evaluations as Json[];
      expect(evaluations.length).toBeGreaterThan(0);
      expect(evaluations.every((item) => item.result === "SATISFIED")).toBe(true);
    }
    await expect(admin.getByRole("button", { name: /simulate|Execute approved run|Create governed run/i })).toHaveCount(
      0
    );
    await expect(admin.getByRole("status")).toContainText("persisted=false");
    await page.screenshot({ path: testInfo.outputPath("qra-policy-preview.png"), fullPage: true });
    published = await mutation<Policy>(
      page,
      `/api/v1/investment-evidence-policy/configurations/${saved.id}/publish`,
      admin
        .getByRole("group", { name: "Evidence policy actions", exact: true })
        .getByRole("button", { name: "Publish", exact: true })
    );
    expect(published.status).toBe("published");
    await admin.getByRole("button", { name: "History", exact: true }).click();
    await expect(admin).toContainText(published.content_hash.slice(0, 18));
    const history = await body<Policy[]>(
      await page.request.get(`${api}/api/v1/investment-evidence-policy/configurations`, {
        headers: { Authorization: `Bearer ${token}` },
      })
    );
    expect(history.find((item) => item.id === published.id)?.content_hash).toBe(published.content_hash);
    const unchanged = await body<Preparation>(
      await page.request.get(`${api}/api/v1/investment-gate-preparations/${historical.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
    );
    expect(unchanged.preparation_hash).toBe(historical.preparation_hash);
  });

  test("USER Business Case refresh creates a successor with accepted Cost/Schedule references and keeps historical revisions", async ({
    page,
    browser,
  }, testInfo) => {
    test.setTimeout(300_000);
    const token = await login(page);
    if (!caseId) await discover(page, token);
    const headers = { Authorization: `Bearer ${token}` };
    const old = await body<Revision[]>(
      await page.request.get(`${api}/api/v1/business-cases/${caseId}/revisions`, { headers })
    );
    await page.goto("/app/strategy/business-case-my");
    const business = page.getByRole("region", { name: "Business Case Manager", exact: true });
    await expect(business).toBeVisible();
    await business.getByRole("combobox", { name: /^Business Case/ }).selectOption(String(caseId));
    const preview = await mutation<Json>(
      page,
      `/api/v1/business-cases/${caseId}/refresh/preview`,
      business.getByRole("button", { name: "Refresh preview", exact: true })
    );
    expect(preview.persisted).toBe(false);
    const created = await mutation<Revision>(
      page,
      `/api/v1/business-cases/${caseId}/refresh`,
      business.getByRole("button", { name: "Create revision", exact: true })
    );
    expect(created.status).toBe("DRAFT");
    await business.getByRole("button", { name: "Sources & Evidence", exact: true }).click();
    const sourceReferences = created.source_references_json as Record<string, Json>;
    for (const type of ["COST_QRA", "SCHEDULE_QRA"]) {
      const summaries = business.getByRole("region", { name: `${type} evidence summary`, exact: true });
      // Cost is referenced in both Economic and Financial Cases; Schedule is
      // referenced in Management. These are projections of the same source.
      await expect(summaries).toHaveCount(type === "COST_QRA" ? 2 : 1);
      const source = sourceReferences[type === "COST_QRA" ? "cost_qra_result" : "schedule_qra_result"];
      const summaryRows = await summaries.all();
      for (const [index, summary] of summaryRows.entries()) {
        await expect(summary).toBeVisible();
        await expect(summary).toContainText("ACCEPTED");
        await expect(summary).toContainText("CURRENT");
        await assertCapturedSummary(page, summary, source);
        await assertSourceLink(page, summary, type, token, index === 0);
      }
    }
    await expect(
      business.getByRole("button", { name: /simulate|Execute approved run|Create governed run/i })
    ).toHaveCount(0);
    const submitted = await mutation<Revision>(
      page,
      `/api/v1/business-case-revisions/${created.id}/submit-review`,
      business.getByRole("button", { name: "Submit", exact: true })
    );
    const reviewerContext = await browser.newContext({ baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:5533" });
    const reviewerPage = await reviewerContext.newPage();
    const reviewerToken = await login(reviewerPage, "qra.evidence.reviewer@demo.local");
    await body<Revision>(
      await page.request.post(`${api}/api/v1/business-case-revisions/${submitted.id}/complete`, {
        headers: { Authorization: `Bearer ${reviewerToken}`, "If-Match": `"${submitted.revision_version}"` },
        data: { idempotency_key: key("bc-complete") },
      })
    );
    await reviewerContext.close();
    const after = await body<Revision[]>(
      await page.request.get(`${api}/api/v1/business-cases/${caseId}/revisions`, { headers })
    );
    for (const revision of old)
      expect(after.find((item) => item.id === revision.id)?.content_hash).toBe(revision.content_hash);
    await page.reload();
    await expect(business).toBeVisible();
    await business.getByRole("combobox", { name: /^Business Case/ }).selectOption(String(caseId));
    await business.getByRole("button", { name: "Sources & Evidence", exact: true }).click();
    await expect(business).toContainText("COMPLETED");
    const sourceHashes = created.source_hashes_json as Record<string, string>;
    for (const kind of ["cost", "schedule"]) {
      const source = sourceReferences[`${kind}_qra_result`];
      const rows = business.getByRole("row").filter({
        has: page.locator(`a[href$="run_id=${Number(source.run_id)}"]`),
      });
      await expect(rows).toHaveCount(kind === "cost" ? 2 : 1);
      for (const row of await rows.all()) {
        const cells = row.getByRole("cell");
        await expect(cells.nth(2)).toHaveText(`${source.run_number} / ${source.model_version}`);
        await expect(cells.nth(3)).toHaveAttribute("title", sourceHashes[`${kind}_qra_result`]);
        await expect(cells.nth(4)).toHaveText(String(source.readiness || source.analytical_readiness));
        await expect(cells.nth(5)).toHaveText("CURRENT");
        await expect(cells.nth(6)).not.toHaveText("—");
      }
    }
    await page.screenshot({ path: testInfo.outputPath("qra-business-case-source-reference.png"), fullPage: true });
    // Continue the same real serial workflow using the completed BC source.
    // Setup remains normal author/reviewer API activity, not a fixture patch.
    // Keeping it here avoids charging the full setup to the visual Gate test;
    // all test deadlines and all Gate/FID authorities remain unchanged.
    preparedGate = await createIndependentlyReviewedGateDraft(page, token, reviewerToken);
  });

  test("USER Gate displays separate accepted/current results, forbids manual Class A and freezes a compact package without simulation", async ({
    page,
    browser,
  }, testInfo) => {
    test.setTimeout(300_000);
    const token = await login(page);
    const headers = { Authorization: `Bearer ${token}` };
    expect(preparedGate).toBeTruthy();
    const preparation = preparedGate!;
    expect(preparation.status).toBe("IN_PREPARATION");
    const reviewerContext = await browser.newContext({ baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:5533" });
    const reviewerPage = await reviewerContext.newPage();
    await login(reviewerPage, "qra.evidence.reviewer@demo.local");
    const readiness = await body<Json>(
      await page.request.get(`${api}/api/v1/investment-gate-preparations/${preparation.id}/readiness`, { headers })
    );
    expect(readiness.blockers).toEqual([]);
    expect(readiness.readiness_status).toBe("READY");
    const mandatoryQraCriteria = (readiness.criterion_evaluations as Json[]).filter(
      (row) => row.qra_evidence && row.required && row.blocking
    );
    expect(mandatoryQraCriteria.length).toBeGreaterThan(0);
    expect(mandatoryQraCriteria.every((row) => row.result === "SATISFIED")).toBe(true);
    const gate = await openGate(page, preparation.id);
    await gate.getByRole("button", { name: "Evidence Package", exact: true }).click();
    for (const type of ["COST_QRA", "SCHEDULE_QRA"]) {
      const summary = gate.getByRole("region", { name: `${type} evidence summary`, exact: true });
      await expect(summary).toBeVisible();
      await expect(summary).toContainText("ACCEPTED");
      await expect(summary).toContainText("CURRENT");
      await expect(summary).toContainText("Tail-convergence limitation");
      const row = preparation.evidence.find((item) => item.evidence_type === `${type}_RESULT`)!;
      expect(row).toBeTruthy();
      expect(row.classification).toBe("A");
      await assertCapturedSummary(page, summary, { ...(row.qra_summary as Json), classification: row.classification });
      await assertSourceLink(page, summary, type, token, true);
    }
    await expect(gate.getByRole("region", { name: "SCHEDULE_QRA evidence summary", exact: true })).toContainText(
      "normalized elapsed time"
    );
    await expect(gate.getByRole("button", { name: /simulate|Execute approved run|Create governed run/i })).toHaveCount(
      0
    );
    const forbidden = await page.request.post(`${api}/api/v1/investment-gate-preparations/${preparation.id}/evidence`, {
      headers: { ...headers, "If-Match": `"${preparation.revision_version}"` },
      data: {
        requirement_key: "cost-qra-result",
        scope_type: "EACH_PROJECT",
        scope_id: projectId,
        reference_id: "manual-qra",
        evidence_date: new Date().toISOString(),
        issuer: "Tester issuer",
        owner: "Tester owner",
        summary: "Must not substitute provider for Class A QRA",
        evidence_refs: [],
        idempotency_key: key("qra-manual-denied"),
      },
    });
    expect(forbidden.status()).toBe(409);
    expect((await forbidden.json()).detail.code).toBe("MANUAL_REFERENCE_NOT_ALLOWED");
    await page.screenshot({ path: testInfo.outputPath("qra-user-gate-evidence.png"), fullPage: true });
    await gate.getByRole("button", { name: "Preparations", exact: true }).click();
    const ready = await mutation<Preparation>(
      page,
      `/api/v1/investment-gate-preparations/${preparation.id}/ready-for-review`,
      gate.getByRole("button", { name: "Ready for review", exact: true })
    );
    expect(ready.status).toBe("READY_FOR_REVIEW");
    const reviewedGate = await openGate(reviewerPage, preparation.id);
    await reviewedGate.getByRole("button", { name: "Preparations", exact: true }).click();
    frozen = await mutation<Preparation>(
      reviewerPage,
      `/api/v1/investment-gate-preparations/${preparation.id}/freeze`,
      reviewedGate.getByRole("button", { name: "Freeze package", exact: true })
    );
    expect(frozen.status).toBe("FROZEN");
    const json = JSON.stringify(frozen);
    expect(json).not.toContain('"histogram"');
    expect(json).not.toContain('"cdf"');
    expect(json).not.toContain('"sensitivity"');
    await reviewerPage.screenshot({ path: testInfo.outputPath("qra-user-frozen-gate.png"), fullPage: true });
    await reviewerContext.close();
  });

  test("read-only USER, wrong-project QRA and author-publisher SoD are denied; Integrated DRAFT validation preserves history", async ({
    page,
  }, testInfo) => {
    test.setTimeout(180_000);
    const userToken = await login(page, "qra.evidence.reader@demo.local");
    const denied = await page.request.put(`${api}/api/v1/investment-evidence-policy/configurations/${published.id}`, {
      headers: { Authorization: `Bearer ${userToken}`, "If-Match": `"${published.version}"` },
      data: { name: "Unauthorized edit", description: "Forbidden", content_json: published.content_json },
    });
    expect(denied.status()).toBe(403);
    await page.goto("/app/admin/strategy/investment-decision-evidence-policy");
    await expect(page.getByRole("region", { name: "Evidence & Decision Policy", exact: true })).toHaveCount(0);
    const adminToken = await login(page);
    const headers = { Authorization: `Bearer ${adminToken}` };
    const permittedProvider = await body<Json>(
      await page.request.get(
        `${api}/api/v1/qra-engine/projects/${projectId}/provider-evidence?analysis_type=COST_QRA`,
        {
          headers,
        }
      )
    );
    expect(permittedProvider.status).toBe("AVAILABLE");
    expect(permittedProvider.project_id).toBe(projectId);
    const wrongProject = await page.request.get(
      `${api}/api/v1/qra-engine/projects/${projectId + 1000000}/provider-evidence?analysis_type=COST_QRA`,
      { headers }
    );
    expect([403, 404]).toContain(wrongProject.status());
    const clone = await body<Policy>(
      await page.request.post(`${api}/api/v1/investment-evidence-policy/configurations/${published.id}/clone`, {
        headers: { ...headers, "If-Match": `"${published.version}"` },
      })
    );
    const content = structuredClone(clone.content_json);
    const profiles = content.gate_profiles as Record<string, { requirements: Json[] }>;
    const qra = profiles["PYP-FFA"].requirements.find((row) => row.evidence_type === "COST_QRA_RESULT")!;
    (qra.qra_policy as Json).analysis_type = "INTEGRATED_COST_SCHEDULE_QRA";
    const rejected = await page.request.put(`${api}/api/v1/investment-evidence-policy/configurations/${clone.id}`, {
      headers: { ...headers, "If-Match": `"${clone.version}"` },
      data: { name: "Unsupported integrated Class A", description: "Negative validation only", content_json: content },
    });
    expect(rejected.status()).toBe(422);
    const sodContent = structuredClone(clone.content_json);
    sodContent.sod = { ...(sodContent.sod as Json), author_must_differ_from_publisher: true };
    const sodDraft = await body<Policy>(
      await page.request.put(`${api}/api/v1/investment-evidence-policy/configurations/${clone.id}`, {
        headers: { ...headers, "If-Match": `"${clone.version}"` },
        data: {
          name: "Disposable policy author-publisher SoD negative",
          description: "Negative validation only",
          content_json: sodContent,
        },
      })
    );
    const forbiddenPublish = await page.request.post(
      `${api}/api/v1/investment-evidence-policy/configurations/${sodDraft.id}/publish`,
      {
        headers: { ...headers, "If-Match": `"${sodDraft.version}"` },
      }
    );
    expect(forbiddenPublish.status()).toBe(403);
    expect((await forbiddenPublish.json()).detail.code).toBe("POLICY_AUTHOR_PUBLISHER_SOD_VIOLATION");
    const configurations = await body<Policy[]>(
      await page.request.get(`${api}/api/v1/investment-evidence-policy/configurations`, { headers })
    );
    const unchangedDraft = configurations.find((item) => item.id === sodDraft.id)!;
    expect(unchangedDraft).toBeTruthy();
    expect(unchangedDraft.status).toBe("draft");
    expect(unchangedDraft.version).toBe(sodDraft.version);
    expect(unchangedDraft.content_hash).toBe(sodDraft.content_hash);
    const currentHistorical = await body<Preparation>(
      await page.request.get(`${api}/api/v1/investment-gate-preparations/${historical.id}`, { headers })
    );
    const currentFrozen = await body<Preparation>(
      await page.request.get(`${api}/api/v1/investment-gate-preparations/${frozen.id}`, { headers })
    );
    expect(currentHistorical.preparation_hash).toBe(historical.preparation_hash);
    expect(currentFrozen.preparation_hash).toBe(frozen.preparation_hash);
    await page.screenshot({ path: testInfo.outputPath("qra-evidence-direct-route-security.png"), fullPage: true });
  });
});
