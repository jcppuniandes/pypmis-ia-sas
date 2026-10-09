import { expect, type APIResponse, type Page, test } from "@playwright/test";

const apiUrl = process.env.E2E_API_URL || "http://localhost:8000";
const fixturePayload = process.env.E2E_GATE07E_FIXTURE;

type WorkspaceRef = { id: number; name: string; code: string };
type ConfigurationRef = { id: number; name: string; code: string; revision: number; version: number; hash: string };
type FundsFixture = {
  index: number;
  main_portfolio: WorkspaceRef;
  projects: Record<"A" | "B" | "C", WorkspaceRef>;
  excluded_projects: Record<"CONTRACTOR" | "DIRECT" | "LEGACY", WorkspaceRef>;
  funds_configuration: ConfigurationRef;
  funding_reviewer: { id: number; email: string; password: string };
};
type FixtureBatch = { run_id: string; copies: FundsFixture[] };
type Versioned = { id: number; revision_version: number; status: string };
type FundingSource = Versioned & {
  source_code: string;
  source_name: string;
  source_type: string;
  currency: string;
  restrictions: Record<string, unknown>;
  evidence_refs: Array<Record<string, unknown>>;
};
type Fund = Versioned & {
  fund_code: string;
  fund_name: string;
  currency: string;
  authorized_amount: number;
  assigned_amount: number;
  available_amount: number;
};
type Assignment = Versioned & {
  assignment_number: string;
  fund_id: number;
  amount: number;
  currency: string;
  period_start: string | null;
  period_end: string | null;
  period_profile: Array<Record<string, unknown>>;
  assignment_purpose: string;
  conditions: Array<Record<string, unknown>>;
  evidence_refs: Array<Record<string, unknown>>;
  warnings: string[];
};
type Readiness = {
  snapshot_id: number | null;
  source_convergence_id: number;
  source_recommendation_hash: string;
  recommended_project_set_hash: string;
  required_amount: number;
  required_currency: string;
  confirmed_funding_amount: number;
  reserved_funding_amount: number;
  funding_gap: number;
  confirmed_coverage_percent: number;
  potential_coverage_percent: number;
  restriction_summary: Record<string, unknown>;
  conditions_summary: Record<string, unknown>;
  warnings: string[];
  blockers: string[];
  funding_readiness_status: string;
  funding_readiness_hash: string;
  source_hash: string;
  source_current: boolean;
  can_supply_investment_gate_evidence: boolean;
  final_output: string;
};
type Overview = {
  portfolio_workspace_id: number;
  governance_model_applicable: boolean;
  active_funds: number;
  funding_sources: FundingSource[];
  funds: Fund[];
  assignments: Assignment[];
  readiness: Readiness | null;
};
type Convergence = Versioned & { alternatives: Array<{ id: number; feasibility_status: string }> };
type FundsConfiguration = {
  id: number;
  name: string;
  description: string;
  status: string;
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash: string;
};

const batch = fixturePayload ? (JSON.parse(fixturePayload) as FixtureBatch) : null;

async function apiJson<T>(response: APIResponse, status = 200) {
  const body = await response.text();
  expect(response.status(), body).toBe(status);
  return JSON.parse(body) as T;
}

function headers(token: string, version?: number) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
    ...(version ? { "If-Match": `"${version}"` } : {}),
  };
}

function idempotency(prefix: string, fixture: FundsFixture) {
  return `${batch!.run_id}-${prefix}-r${fixture.index}`;
}

function isoDay(offset: number) {
  const value = new Date();
  value.setUTCDate(value.getUTCDate() + offset);
  return value.toISOString().slice(0, 10);
}

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("User").fill("admin");
  await page.getByLabel("Password").fill("1234");
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes("/api/v1/auth/login") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /sign in/i }).click();
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  const session = (await response.json()) as { access_token: string };
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
  return session.access_token;
}

async function secondActorToken(page: Page, fixture: FundsFixture) {
  const response = await page.request.post(`${apiUrl}/api/v1/auth/login`, {
    data: { email: fixture.funding_reviewer.email, password: fixture.funding_reviewer.password },
  });
  return (await apiJson<{ access_token: string }>(response)).access_token;
}

async function expand(page: Page, name: RegExp) {
  const button = page.getByRole("button", { name });
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
}

async function openUserFunds(page: Page, submodule: RegExp, portfolio: WorkspaceRef) {
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^funds manager$/i);
  await page
    .getByRole("group", { name: "Submódulos de Funds Manager" })
    .getByRole("button", { name: submodule })
    .click();
  const workspace = page.getByRole("region", { name: "Funds Manager", exact: true });
  await expect(workspace).toBeVisible();
  await workspace.getByLabel("Portfolio").selectOption(String(portfolio.id));
  return workspace;
}

async function openAdminFunds(page: Page) {
  const toggle = page.getByRole("button", { name: "Cambiar a ADMIN MODE" });
  if (await toggle.isVisible()) await toggle.click();
  await expand(page, /^enterprise strategy manager$/i);
  await page.getByRole("button", { name: /^funds manager configuration$/i }).click();
  const workspace = page.getByRole("region", { name: "Funds Manager Configuration", exact: true });
  await expect(workspace).toBeVisible();
  return workspace;
}

async function ensureRecommendation(page: Page, token: string, fixture: FundsFixture) {
  const portfolioId = fixture.main_portfolio.id;
  const auth = headers(token);
  const current = await page.request.get(
    `${apiUrl}/api/v1/portfolios/${portfolioId}/investment-gate-preparation-contract`,
    { headers: auth }
  );
  if (current.ok()) return apiJson<Record<string, unknown>>(current);
  const budgetScenarios = await apiJson<Array<Record<string, unknown>>>(
    await page.request.get(`${apiUrl}/api/v1/portfolios/${portfolioId}/budget-scenarios`, { headers: auth })
  );
  const resourceScenarios = await apiJson<Array<Record<string, unknown>>>(
    await page.request.get(`${apiUrl}/api/v1/portfolios/${portfolioId}/resource-scenarios`, { headers: auth })
  );
  const budget = budgetScenarios.find((item) => String(item.status).toUpperCase() === "FROZEN");
  const resource = resourceScenarios.find((item) => String(item.status).toUpperCase() === "FROZEN");
  expect(budget, "A frozen Gate 07G scenario is required").toBeTruthy();
  expect(resource, "A frozen Gate 07H scenario is required").toBeTruthy();
  let convergence = await apiJson<Convergence>(
    await page.request.post(`${apiUrl}/api/v1/portfolios/${portfolioId}/scenario-convergences`, {
      headers: auth,
      data: {
        name: `Gate 07J-FUND H ${batch!.run_id} R${fixture.index}`,
        description: "Governed source contract for Funds Manager release closeout.",
        idempotency_key: idempotency("fund-convergence", fixture),
      },
    })
  );
  convergence = await apiJson<Convergence>(
    await page.request.post(`${apiUrl}/api/v1/portfolio-scenario-convergences/${convergence.id}/alternatives`, {
      headers: headers(token, convergence.revision_version),
      data: {
        alternative_name: "Funding closeout governed alternative",
        budget_scenario_id: Number(budget!.id),
        resource_scenario_id: Number(resource!.id),
        idempotency_key: idempotency("fund-alternative", fixture),
      },
    })
  );
  expect(convergence.alternatives[0].feasibility_status).toBe("FEASIBLE");
  convergence = await apiJson<Convergence>(
    await page.request.post(`${apiUrl}/api/v1/portfolio-scenario-convergences/${convergence.id}/submit-review`, {
      headers: headers(token, convergence.revision_version),
      data: { idempotency_key: idempotency("fund-submit", fixture) },
    })
  );
  convergence = await apiJson<Convergence>(
    await page.request.post(`${apiUrl}/api/v1/portfolio-scenario-convergences/${convergence.id}/recommend`, {
      headers: headers(token, convergence.revision_version),
      data: {
        recommended_alternative_id: convergence.alternatives[0].id,
        recommendation_reason: "Aligned governed recommendation for Funding Readiness closeout.",
        risks_acknowledged: ["Investment Decision and FID remain downstream."],
        decision_support_summary: "Budget and resource sources remain aligned without investment approval.",
        idempotency_key: idempotency("fund-recommend", fixture),
      },
    })
  );
  expect(convergence.status).toBe("RECOMMENDED");
  return apiJson<Record<string, unknown>>(
    await page.request.get(`${apiUrl}/api/v1/portfolios/${portfolioId}/investment-gate-preparation-contract`, {
      headers: auth,
    })
  );
}

async function createSourceAndFund(
  page: Page,
  token: string,
  reviewerToken: string,
  fixture: FundsFixture,
  key: string,
  currency: string,
  amount: number,
  restrictions: Record<string, unknown> = {}
) {
  const source = await apiJson<FundingSource>(
    await page.request.post(`${apiUrl}/api/v1/funding-sources`, {
      headers: headers(token),
      data: {
        source_name: `${batch!.run_id} ${key} source R${fixture.index}`,
        source_type: "CORPORATE_CAPEX",
        currency,
        effective_from: isoDay(-1),
        effective_to: isoDay(365),
        restrictions: {},
        evidence_refs: [{ reference: `${key}-SOURCE-EVIDENCE` }],
        idempotency_key: idempotency(`${key}-source`, fixture),
      },
    })
  );
  const activeSource = await apiJson<FundingSource>(
    await page.request.post(`${apiUrl}/api/v1/funding-sources/${source.id}/activate`, {
      headers: headers(token, source.revision_version),
      data: { idempotency_key: idempotency(`${key}-source-activate`, fixture) },
    })
  );
  let fund = await apiJson<Fund>(
    await page.request.post(`${apiUrl}/api/v1/funds`, {
      headers: headers(token),
      data: {
        fund_name: `${batch!.run_id} ${key} fund R${fixture.index}`,
        funding_source_id: activeSource.id,
        currency,
        authorized_amount: amount,
        available_from: isoDay(-1),
        available_to: isoDay(365),
        period_granularity: "TOTAL",
        restrictions,
        evidence_refs: [{ reference: `${key}-FUND-EVIDENCE` }],
        idempotency_key: idempotency(`${key}-fund`, fixture),
      },
    })
  );
  fund = await apiJson<Fund>(
    await page.request.post(`${apiUrl}/api/v1/funds/${fund.id}/authorize`, {
      headers: headers(reviewerToken, fund.revision_version),
      data: { idempotency_key: idempotency(`${key}-fund-authorize`, fixture) },
    })
  );
  return apiJson<Fund>(
    await page.request.post(`${apiUrl}/api/v1/funds/${fund.id}/activate`, {
      headers: headers(token, fund.revision_version),
      data: { idempotency_key: idempotency(`${key}-fund-activate`, fixture) },
    })
  );
}

async function createAssignment(
  page: Page,
  token: string,
  fixture: FundsFixture,
  contract: Record<string, unknown>,
  fund: Fund,
  amount: number,
  key: string,
  options: {
    currency?: string;
    scope?: "PORTFOLIO" | "PROJECT" | "RECOMMENDED_PROJECT_SET";
    projectId?: number;
    parentId?: number;
    periodEnd?: string;
    conditions?: Array<Record<string, unknown>>;
  } = {}
) {
  const scope = options.scope || "RECOMMENDED_PROJECT_SET";
  const data: Record<string, unknown> = {
    fund_id: fund.id,
    parent_assignment_id: options.parentId,
    scope_type: scope,
    portfolio_workspace_id: fixture.main_portfolio.id,
    project_workspace_id: options.projectId,
    amount,
    currency: options.currency || fund.currency,
    period_start: options.periodEnd && options.periodEnd < isoDay(0) ? undefined : isoDay(-1),
    period_end: options.periodEnd || isoDay(365),
    period_profile: [],
    assignment_purpose: `${key} governed lifecycle evidence.`,
    conditions: options.conditions || [],
    evidence_refs: [{ reference: `${key}-ASSIGNMENT-EVIDENCE` }],
    idempotency_key: idempotency(`${key}-assignment`, fixture),
  };
  if (scope === "RECOMMENDED_PROJECT_SET") {
    data.recommended_project_set_hash = contract.selected_project_set_hash;
    data.source_convergence_id = contract.convergence_id;
    data.source_recommendation_hash = contract.recommendation_hash;
  }
  if (scope === "PORTFOLIO") delete data.project_workspace_id;
  if (scope === "PROJECT") {
    delete data.recommended_project_set_hash;
    delete data.source_convergence_id;
    delete data.source_recommendation_hash;
  }
  return apiJson<Assignment>(
    await page.request.post(`${apiUrl}/api/v1/funding-assignments`, { headers: headers(token), data })
  );
}

async function transitionAssignment(
  page: Page,
  token: string,
  fixture: FundsFixture,
  assignment: Assignment,
  action: "reserve" | "confirm" | "release" | "cancel",
  key: string
) {
  return apiJson<Assignment>(
    await page.request.post(`${apiUrl}/api/v1/funding-assignments/${assignment.id}/${action}`, {
      headers: headers(token, assignment.revision_version),
      data: { idempotency_key: idempotency(key, fixture) },
    })
  );
}

async function readiness(page: Page, token: string, portfolioId: number) {
  return apiJson<Readiness>(
    await page.request.get(`${apiUrl}/api/v1/portfolios/${portfolioId}/funding/readiness`, {
      headers: headers(token),
    })
  );
}

test.describe("Gate 07J-FUND-H lifecycle browser E2E release closeout", () => {
  test.setTimeout(480_000);
  test.skip(!batch, "Requires the disposable E2E_GATE07E_FIXTURE payload");

  test("USER and ADMIN real flows reach GATE07J_FUND_RELEASE_VALIDATED", async ({ page }, testInfo) => {
    const fixture = batch!.copies[testInfo.repeatEachIndex % batch!.copies.length];
    for (const localOrigin of ["http://localhost:8000", "http://127.0.0.1:8000"]) {
      await page.route(`${localOrigin}/**`, (route) =>
        route.continue({ url: route.request().url().replace(localOrigin, apiUrl) })
      );
    }
    const unexpectedResponses: string[] = [];
    const pageErrors: string[] = [];
    const consoleWarnings: string[] = [];
    let controlledConflictCount = 0;
    page.on("pageerror", (error) => pageErrors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "warning" || message.type() === "error") consoleWarnings.push(message.text());
    });
    page.on("response", (response) => {
      if (response.status() >= 400 && response.url().includes("/api/v1/")) {
        const controlled =
          response.status() === 409 &&
          (/\/funds\/\d+\/authorize$/.test(response.url()) ||
            /\/funding-assignments\/\d+\/confirm$/.test(response.url()));
        if (controlled) controlledConflictCount += 1;
        if (!controlled)
          unexpectedResponses.push(`${response.status()} ${response.request().method()} ${response.url()}`);
      }
    });

    const token = await login(page);
    const reviewer = await secondActorToken(page, fixture);
    const contract = await ensureRecommendation(page, token, fixture);
    const portfolioId = fixture.main_portfolio.id;

    let workspace = await openUserFunds(page, /^funding sources$/i, fixture.main_portfolio);
    const sourceName = `${batch!.run_id} UI source R${fixture.index}`;
    await workspace.getByLabel("Name").fill(sourceName);
    await workspace.getByLabel("Type").selectOption("CORPORATE_CAPEX");
    await workspace.getByLabel("Currency").fill("COP");
    const sourceResponse = page.waitForResponse(
      (response) => response.url().endsWith("/api/v1/funding-sources") && response.request().method() === "POST"
    );
    await workspace.getByRole("button", { name: "Create Funding Source" }).click();
    let source = await apiJson<FundingSource>(await sourceResponse);
    expect(source.status).toBe("DRAFT");
    source = await apiJson<FundingSource>(
      await page.request.put(`${apiUrl}/api/v1/funding-sources/${source.id}`, {
        headers: headers(token, source.revision_version),
        data: {
          source_name: source.source_name,
          source_type: source.source_type,
          description: "Governed browser source with lifecycle evidence.",
          legal_entity_provider_reference: "P&Pmis Enterprise",
          currency: source.currency,
          effective_from: isoDay(-1),
          effective_to: isoDay(365),
          restrictions: {},
          evidence_refs: [{ reference: "BOARD-CAPEX-E2E" }],
          source_reference: "CAPEX-AUTHORITY-E2E",
        },
      })
    );
    await page.reload();
    workspace = await openUserFunds(page, /^funding sources$/i, fixture.main_portfolio);
    const sourceCard = workspace.getByTestId(`funding-source-${source.id}`);
    await expect(sourceCard).toContainText(source.source_code);
    await expect(sourceCard).toContainText("CORPORATE_CAPEX");
    await expect(sourceCard).toContainText("1 evidence ref(s)");
    await sourceCard.getByRole("button", { name: "Activate" }).click();
    await expect(sourceCard).toContainText("ACTIVE");

    await workspace.getByRole("button", { name: "funds", exact: true }).click();
    const initial = await apiJson<Overview>(
      await page.request.get(`${apiUrl}/api/v1/portfolios/${portfolioId}/funding`, { headers: headers(token) })
    );
    const required = Number(initial.readiness!.required_amount);
    const capacity = Math.ceil(required * 1.2);
    const fundName = `${batch!.run_id} UI fund R${fixture.index}`;
    await workspace.getByLabel("Name").fill(fundName);
    await workspace.getByLabel("Funding Source").selectOption(String(source.id));
    await workspace.getByLabel("Authorized amount").fill(String(capacity));
    const fundResponse = page.waitForResponse(
      (response) => response.url().endsWith("/api/v1/funds") && response.request().method() === "POST"
    );
    await workspace.getByRole("button", { name: "Create Fund" }).click();
    let fund = (await (await fundResponse).json()) as Fund;
    expect(fund.status).toBe("DRAFT");
    fund = await apiJson<Fund>(
      await page.request.put(`${apiUrl}/api/v1/funds/${fund.id}`, {
        headers: headers(token, fund.revision_version),
        data: {
          fund_name: fund.fund_name,
          funding_source_id: source.id,
          description: "Governed browser Fund with dates and evidence.",
          currency: "COP",
          authorized_amount: capacity,
          available_from: isoDay(-1),
          available_to: isoDay(365),
          period_granularity: "TOTAL",
          authorized_amount_by_period: [],
          restrictions: {},
          applicable_workspace_scope: { portfolio_ids: [portfolioId] },
          evidence_refs: [{ reference: "FUND-AUTHORITY-E2E" }],
          source_reference: "FUND-COMMITTEE-E2E",
        },
      })
    );
    await page.reload();
    workspace = await openUserFunds(page, /^funds$/i, fixture.main_portfolio);
    let fundCard = workspace.getByTestId(`fund-${fund.id}`);
    await expect(fundCard).toContainText("1 evidence ref(s)");
    const sameActorAuthorization = page.waitForResponse((response) =>
      response.url().endsWith(`/api/v1/funds/${fund.id}/authorize`)
    );
    await fundCard.getByRole("button", { name: "Authorize" }).click();
    expect((await sameActorAuthorization).status()).toBe(409);
    fund = await apiJson<Fund>(
      await page.request.post(`${apiUrl}/api/v1/funds/${fund.id}/authorize`, {
        headers: headers(reviewer, fund.revision_version),
        data: { idempotency_key: idempotency("ui-fund-authorize", fixture) },
      })
    );
    await page.reload();
    workspace = await openUserFunds(page, /^funds$/i, fixture.main_portfolio);
    fundCard = workspace.getByTestId(`fund-${fund.id}`);
    await fundCard.getByRole("button", { name: "Activate" }).click();
    await expect(fundCard).toContainText("ACTIVE");

    await workspace.getByRole("button", { name: "assignments", exact: true }).click();
    await workspace.getByTestId("funding-assignment-fund").selectOption(String(fund.id));
    await workspace.getByTestId("funding-assignment-amount").fill(String(required));
    const assignmentResponse = page.waitForResponse(
      (response) => response.url().endsWith("/api/v1/funding-assignments") && response.request().method() === "POST"
    );
    await workspace.getByRole("button", { name: "Create Assignment" }).click();
    let assignment = await apiJson<Assignment>(await assignmentResponse);
    const stableNumber = assignment.assignment_number;
    const assignmentRow = workspace.getByTestId(`funding-assignment-${assignment.id}`);
    await assignmentRow.getByRole("button", { name: "Reserve" }).click();
    await expect(assignmentRow).toContainText("RESERVED");
    assignment = await apiJson<Assignment>(
      await page.request.get(`${apiUrl}/api/v1/funding-assignments/${assignment.id}`, { headers: headers(token) })
    );
    expect(assignment.assignment_number).toBe(stableNumber);
    const sameActorConfirmation = page.waitForResponse((response) =>
      response.url().endsWith(`/api/v1/funding-assignments/${assignment.id}/confirm`)
    );
    await workspace.getByTestId(`funding-assignment-${assignment.id}`).getByRole("button", { name: "Confirm" }).click();
    expect((await sameActorConfirmation).status()).toBe(409);
    const confirmKey = idempotency("ui-assignment-confirm", fixture);
    assignment = await apiJson<Assignment>(
      await page.request.post(`${apiUrl}/api/v1/funding-assignments/${assignment.id}/confirm`, {
        headers: headers(reviewer, assignment.revision_version),
        data: { idempotency_key: confirmKey },
      })
    );
    const confirmationReplay = await apiJson<Assignment>(
      await page.request.post(`${apiUrl}/api/v1/funding-assignments/${assignment.id}/confirm`, {
        headers: headers(reviewer, assignment.revision_version - 1),
        data: { idempotency_key: confirmKey },
      })
    );
    expect(confirmationReplay.id).toBe(assignment.id);

    await page.reload();
    workspace = await openUserFunds(page, /^funding assignments$/i, fixture.main_portfolio);
    await expect(workspace.getByTestId(`funding-assignment-${assignment.id}`)).toContainText("CONFIRMED");
    await workspace.getByRole("button", { name: "readiness", exact: true }).click();
    await expect(workspace.getByTestId("funding-readiness-status")).toHaveText("READY");
    await workspace.getByRole("button", { name: "Refresh Preview" }).click();
    await expect(workspace.getByRole("status")).toContainText("persisted=false");
    await workspace.getByRole("button", { name: "Apply Refresh" }).click();
    await expect(workspace.getByRole("status")).toContainText("snapshot refreshed");
    expect((await readiness(page, token, portfolioId)).final_output).toBe("READY_FOR_GOVERNED_FUNDING_EVIDENCE");
    await workspace.getByRole("button", { name: "Open Gate 07J evidence" }).click();
    await expect(workspace.locator("pre")).toContainText('"source_module": "FUNDS_MANAGER"');
    await expect(workspace.locator("pre")).toContainText('"requirement_type": "FUNDING_READINESS"');
    await expect(workspace.locator("pre")).toContainText('"evidence_origin": "GOVERNED_SOURCE"');
    await workspace.getByRole("button", { name: "coverage", exact: true }).click();
    await expect(workspace.getByTestId("funding-coverage-confirmed")).toContainText(required.toLocaleString("en-US"));
    await expect(workspace.getByTestId("funding-coverage-gap")).toContainText("COP 0");
    const ready = await readiness(page, token, portfolioId);
    expect(Number(ready.confirmed_funding_amount)).toBe(required);
    expect(Number(ready.funding_gap)).toBe(0);
    expect(ready.source_current).toBe(true);

    await workspace.getByRole("button", { name: "assignments", exact: true }).click();
    const releasedResponse = page.waitForResponse((response) =>
      response.url().endsWith(`/api/v1/funding-assignments/${assignment.id}/release`)
    );
    await workspace.getByTestId(`funding-assignment-${assignment.id}`).getByRole("button", { name: "Release" }).click();
    assignment = await apiJson<Assignment>(await releasedResponse);
    expect(assignment.status).toBe("RELEASED");
    const releasedOverview = await apiJson<Overview>(
      await page.request.get(`${apiUrl}/api/v1/portfolios/${portfolioId}/funding`, { headers: headers(token) })
    );
    expect(Number(releasedOverview.funds.find((item) => item.id === fund.id)!.available_amount)).toBe(capacity);
    expect(releasedOverview.readiness!.funding_readiness_status).toBe("STALE");
    const blockedPreview = await apiJson<{ proposed_source_hash: string; persisted: boolean }>(
      await page.request.post(`${apiUrl}/api/v1/portfolios/${portfolioId}/funding/readiness/refresh/preview`, {
        headers: headers(token),
      })
    );
    const blockedAfterRelease = await apiJson<Readiness>(
      await page.request.post(`${apiUrl}/api/v1/portfolios/${portfolioId}/funding/readiness/refresh`, {
        headers: headers(token),
        data: {
          expected_source_hash: blockedPreview.proposed_source_hash,
          idempotency_key: idempotency("release-refresh", fixture),
        },
      })
    );
    expect(blockedAfterRelease.funding_readiness_status).toBe("BLOCKED");

    const partialFund = await createSourceAndFund(page, token, reviewer, fixture, "partial", "COP", required);
    let partial70 = await createAssignment(page, token, fixture, contract, partialFund, required * 0.7, "partial70");
    partial70 = await transitionAssignment(page, reviewer, fixture, partial70, "confirm", "partial70-confirm");
    let partial20 = await createAssignment(page, token, fixture, contract, partialFund, required * 0.2, "partial20");
    partial20 = await transitionAssignment(page, token, fixture, partial20, "reserve", "partial20-reserve");
    let derived = await readiness(page, token, portfolioId);
    expect(Number(derived.confirmed_coverage_percent)).toBeCloseTo(70, 3);
    expect(Number(derived.potential_coverage_percent)).toBeCloseTo(90, 3);
    expect(Number(derived.funding_gap)).toBeCloseTo(required * 0.3, 2);
    partial70 = await transitionAssignment(page, token, fixture, partial70, "release", "partial70-release");
    partial20 = await transitionAssignment(page, token, fixture, partial20, "release", "partial20-release");

    const usdFund = await createSourceAndFund(page, token, reviewer, fixture, "currency", "USD", required);
    let usd = await createAssignment(page, token, fixture, contract, usdFund, required, "currency", {
      currency: "USD",
    });
    usd = await transitionAssignment(page, reviewer, fixture, usd, "confirm", "currency-confirm");
    derived = await readiness(page, token, portfolioId);
    expect(derived.blockers).toContain("CURRENCY_NOT_COMPARABLE");
    usd = await transitionAssignment(page, token, fixture, usd, "release", "currency-release");

    const restrictedFund = await createSourceAndFund(page, token, reviewer, fixture, "restriction", "COP", required, {
      portfolio_ids: [portfolioId + 999_999],
    });
    let restricted = await createAssignment(page, token, fixture, contract, restrictedFund, required, "restriction");
    restricted = await transitionAssignment(page, reviewer, fixture, restricted, "confirm", "restriction-confirm");
    derived = await readiness(page, token, portfolioId);
    expect(Number(derived.restriction_summary.ineligible_assignments)).toBe(1);
    expect(derived.warnings).toContain("PORTFOLIO_RESTRICTION_MISMATCH");
    restricted = await transitionAssignment(page, token, fixture, restricted, "release", "restriction-release");

    const conditionFund = await createSourceAndFund(page, token, reviewer, fixture, "condition", "COP", required);
    let conditioned = await createAssignment(page, token, fixture, contract, conditionFund, required, "condition", {
      conditions: [{ code: "BOARD_CONSENT", status: "OPEN", blocking: true }],
    });
    conditioned = await transitionAssignment(page, token, fixture, conditioned, "reserve", "condition-reserve");
    derived = await readiness(page, token, portfolioId);
    expect(Number(derived.conditions_summary.open_blocking)).toBe(1);
    expect(derived.blockers).toContain("OPEN_BLOCKING_FUNDING_CONDITION");
    conditioned = await apiJson<Assignment>(
      await page.request.put(`${apiUrl}/api/v1/funding-assignments/${conditioned.id}`, {
        headers: headers(token, conditioned.revision_version),
        data: {
          amount: required,
          period_start: conditioned.period_start,
          period_end: conditioned.period_end,
          period_profile: conditioned.period_profile,
          assignment_purpose: conditioned.assignment_purpose,
          conditions: [{ code: "BOARD_CONSENT", status: "SATISFIED", blocking: true }],
          evidence_refs: conditioned.evidence_refs,
        },
      })
    );
    conditioned = await transitionAssignment(page, reviewer, fixture, conditioned, "confirm", "condition-confirm");
    derived = await readiness(page, token, portfolioId);
    expect(Number(derived.conditions_summary.open_blocking)).toBe(0);
    conditioned = await transitionAssignment(page, token, fixture, conditioned, "release", "condition-release");

    const expiryFund = await createSourceAndFund(page, token, reviewer, fixture, "expiry", "COP", required);
    let expired = await createAssignment(page, token, fixture, contract, expiryFund, required, "expiry", {
      periodEnd: isoDay(-1),
    });
    expired = await transitionAssignment(page, reviewer, fixture, expired, "confirm", "expiry-confirm");
    const expiredHistory = await apiJson<Assignment>(
      await page.request.get(`${apiUrl}/api/v1/funding-assignments/${expired.id}`, { headers: headers(token) })
    );
    expect(expiredHistory.status).toBe("CONFIRMED");
    expect(expiredHistory.warnings).toContain("ASSIGNMENT_EXPIRED");
    derived = await readiness(page, token, portfolioId);
    expect(derived.warnings).toContain("EXPIRED_FUNDING_NOT_COUNTED");
    expired = await transitionAssignment(page, token, fixture, expired, "release", "expiry-release");

    const overFund = await createSourceAndFund(page, token, reviewer, fixture, "over", "COP", required);
    let over70a = await createAssignment(page, token, fixture, contract, overFund, required * 0.7, "over70a");
    over70a = await transitionAssignment(page, reviewer, fixture, over70a, "confirm", "over70a-confirm");
    let over70b = await createAssignment(page, token, fixture, contract, overFund, required * 0.7, "over70b");
    const overAllocation = await page.request.post(`${apiUrl}/api/v1/funding-assignments/${over70b.id}/confirm`, {
      headers: headers(reviewer, over70b.revision_version),
      data: { idempotency_key: idempotency("over70b-confirm", fixture) },
    });
    expect(overAllocation.status()).toBe(409);
    expect(JSON.stringify(await overAllocation.json())).toContain("FUND_AVAILABLE_AMOUNT_EXCEEDED");
    over70a = await transitionAssignment(page, token, fixture, over70a, "release", "over70a-release");
    over70b = await transitionAssignment(page, token, fixture, over70b, "cancel", "over70b-cancel");

    const hierarchyFund = await createSourceAndFund(page, token, reviewer, fixture, "hierarchy", "COP", required * 2);
    let parent = await createAssignment(page, token, fixture, contract, hierarchyFund, required, "parent", {
      scope: "PORTFOLIO",
    });
    const duplicateParent = await createAssignment(page, token, fixture, contract, hierarchyFund, required, "parent", {
      scope: "PORTFOLIO",
    });
    expect(duplicateParent.id).toBe(parent.id);
    parent = await transitionAssignment(page, reviewer, fixture, parent, "confirm", "parent-confirm");
    let child60 = await createAssignment(page, token, fixture, contract, hierarchyFund, required * 0.6, "child60", {
      scope: "PROJECT",
      projectId: fixture.projects.A.id,
      parentId: parent.id,
    });
    child60 = await transitionAssignment(page, reviewer, fixture, child60, "confirm", "child60-confirm");
    let child40 = await createAssignment(page, token, fixture, contract, hierarchyFund, required * 0.4, "child40", {
      scope: "PROJECT",
      projectId: fixture.projects.B.id,
      parentId: parent.id,
    });
    child40 = await transitionAssignment(page, reviewer, fixture, child40, "confirm", "child40-confirm");
    derived = await readiness(page, token, portfolioId);
    expect(Number(derived.confirmed_funding_amount)).toBe(required);
    child60 = await transitionAssignment(page, token, fixture, child60, "release", "child60-release");
    child40 = await transitionAssignment(page, token, fixture, child40, "release", "child40-release");
    parent = await transitionAssignment(page, token, fixture, parent, "release", "parent-release");

    const contractor = await apiJson<Overview>(
      await page.request.get(`${apiUrl}/api/v1/projects/${fixture.excluded_projects.CONTRACTOR.id}/funding`, {
        headers: headers(token),
      })
    );
    expect(contractor.governance_model_applicable).toBe(false);
    expect(contractor.readiness).toBeNull();

    const countsBeforePreview = {
      sources: (
        await apiJson<FundingSource[]>(
          await page.request.get(`${apiUrl}/api/v1/funding-sources`, { headers: headers(token) })
        )
      ).length,
      funds: (await apiJson<Fund[]>(await page.request.get(`${apiUrl}/api/v1/funds`, { headers: headers(token) })))
        .length,
      assignments: (
        await apiJson<Assignment[]>(
          await page.request.get(`${apiUrl}/api/v1/funding-assignments?portfolio_id=${portfolioId}`, {
            headers: headers(token),
          })
        )
      ).length,
      snapshot: (await readiness(page, token, portfolioId)).snapshot_id,
    };

    const admin = await openAdminFunds(page);
    const policyButton = admin
      .locator(".fundsAdminGrid aside button")
      .filter({ hasText: fixture.funds_configuration.name });
    await expect(policyButton).toHaveCount(1);
    await policyButton.evaluate((element: HTMLButtonElement) => element.click());
    await expect(admin.locator(".fundsSurface header h3")).toHaveText(fixture.funds_configuration.name);
    const cloneButton = admin.getByRole("button", { name: "Clone", exact: true });
    await expect(cloneButton).toBeEnabled();
    const cloneResponse = page.waitForResponse((response) =>
      response.url().endsWith(`/api/v1/funds/admin/configurations/${fixture.funds_configuration.id}/clone`)
    );
    await cloneButton.evaluate((element: HTMLButtonElement) => element.click());
    const draft = await apiJson<FundsConfiguration>(await cloneResponse);
    expect(draft.status).toBe("draft");
    await expect(admin.getByRole("status")).toContainText("configuration clone completed");
    await admin.getByLabel("Minimum confirmed coverage %").fill("95");
    await admin.getByText("Reserved counts toward readiness").click();
    await admin.getByText("Require period coverage").click();
    await admin.getByText("Open condition is blocker").click();
    await admin.getByText("Advanced controlled JSON").click();
    const jsonEditor = admin.getByLabel("Funds Manager configuration JSON");
    const edited = JSON.parse(await jsonEditor.inputValue()) as Record<string, unknown>;
    edited.currency_policy = {
      require_common_currency: true,
      allow_governed_normalized_amount: true,
      fx_engine: false,
    };
    edited.restriction_catalog = [...((edited.restriction_catalog as string[]) || []), "release_closeout_rule"];
    await jsonEditor.fill(JSON.stringify(edited, null, 2));
    await admin.getByLabel("Preview Portfolio").selectOption(String(portfolioId));
    const previewResponse = page.waitForResponse((response) =>
      response.url().endsWith("/api/v1/funds/admin/configurations/preview")
    );
    await admin
      .getByRole("button", { name: "Preview", exact: true })
      .evaluate((element: HTMLButtonElement) => element.click());
    const preview = await apiJson<Record<string, unknown>>(await previewResponse);
    expect(preview.persisted).toBe(false);
    expect(preview).toEqual(
      expect.objectContaining({
        currency_compatibility: expect.any(Object),
        restrictions: expect.any(Object),
        conditions: expect.any(Object),
        gate07j_funding_evidence_preview: expect.any(Object),
      })
    );
    const countsAfterPreview = {
      sources: (
        await apiJson<FundingSource[]>(
          await page.request.get(`${apiUrl}/api/v1/funding-sources`, { headers: headers(token) })
        )
      ).length,
      funds: (await apiJson<Fund[]>(await page.request.get(`${apiUrl}/api/v1/funds`, { headers: headers(token) })))
        .length,
      assignments: (
        await apiJson<Assignment[]>(
          await page.request.get(`${apiUrl}/api/v1/funding-assignments?portfolio_id=${portfolioId}`, {
            headers: headers(token),
          })
        )
      ).length,
      snapshot: (await readiness(page, token, portfolioId)).snapshot_id,
    };
    expect(countsAfterPreview).toEqual(countsBeforePreview);

    const saveResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/v1/funds/admin/configurations/${draft.id}`) &&
        response.request().method() === "PUT"
    );
    await admin
      .getByRole("button", { name: "Save", exact: true })
      .evaluate((element: HTMLButtonElement) => element.click());
    const saved = await apiJson<FundsConfiguration>(await saveResponse);
    expect(saved.status).toBe("draft");
    expect(saved.version).toBe(draft.version + 1);
    await expect(admin.getByRole("status")).toContainText("configuration save completed");
    const staleSave = await page.request.put(`${apiUrl}/api/v1/funds/admin/configurations/${draft.id}`, {
      headers: headers(token, draft.version),
      data: { name: draft.name, description: draft.description, content_json: draft.content_json },
    });
    expect(staleSave.status()).toBe(412);
    expect(JSON.stringify(await staleSave.json())).toContain("ETAG_MISMATCH");
    const publishResponse = page.waitForResponse((response) =>
      response.url().endsWith(`/api/v1/funds/admin/configurations/${draft.id}/publish`)
    );
    await admin
      .getByRole("button", { name: "Publish", exact: true })
      .evaluate((element: HTMLButtonElement) => element.click());
    const published = await apiJson<FundsConfiguration>(await publishResponse);
    expect(published.status).toBe("published");
    const effective = await apiJson<Record<string, unknown>>(
      await page.request.post(`${apiUrl}/api/v1/funds/admin/configurations/preview`, {
        headers: headers(token),
        data: { portfolio_workspace_id: portfolioId, configuration_id: null, content_json: null, fund_assumptions: [] },
      })
    );
    expect(effective.source).toEqual(expect.objectContaining({ id: published.id, revision: published.revision }));
    expect(JSON.stringify(effective.path)).toContain(fixture.main_portfolio.code);
    await expect(admin.getByRole("button", { name: /approve investment|enter fid|go|hold|kill/i })).toHaveCount(0);

    expect(pageErrors).toEqual([]);
    expect(controlledConflictCount).toBe(2);
    expect(
      consoleWarnings.filter((message) => !message.includes("server responded with a status of 409 (Conflict)"))
    ).toEqual([]);
    expect(unexpectedResponses).toEqual([]);
    testInfo.annotations.push({ type: "release", description: "FLOW_PASS GATE07J_FUND_RELEASE_VALIDATED" });
    await page.screenshot({ path: testInfo.outputPath("gate07j-fund-h-flow-pass.png"), fullPage: true });
  });
});
