import { expect, type Page, test } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

// Real Chromium -> real API -> the SAME isolated PostgreSQL chain.
// This test never provisions records, patches states, mocks routes or records a
// decision. A missing upstream/downstream artifact is a failure, never a skip.
type Json = Record<string, unknown>;
type Stage = { stage: string; status: string; data: Json };
type Setup = Json & {
  tenant_id: number;
  tenant_slug: string;
  actors: Record<string, { id: number; email: string }>;
};
type Chain = Json & { setup?: Setup; stages?: Stage[]; blocker?: Json };
const evidenceRoot = resolve(
  process.env.E2E_STRATEGIC_EVIDENCE_ROOT || resolve(process.cwd(), "../outputs/.qa/strategic-uat-remediation")
);
const setupPath = process.env.E2E_STRATEGIC_FRESH_SETUP || resolve(evidenceRoot, "fresh-setup.json");
const chainPath = process.env.E2E_STRATEGIC_FRESH_CHAIN || resolve(evidenceRoot, "fresh-capital-owner-chain.json");
const resultPath = process.env.E2E_STRATEGIC_FRESH_BROWSER_RESULT || resolve(evidenceRoot, "fresh-browser-result.json");
const api = process.env.E2E_API_URL || "http://127.0.0.1:8840";
const password = process.env.E2E_STRATEGIC_FRESH_PASSWORD || "1234";

function readJson<T>(path: string): T {
  if (!existsSync(path)) throw new Error(`BLOCKED_MISSING_FRESH_ARTIFACT: ${path}`);
  return JSON.parse(readFileSync(path, "utf8")) as T;
}

function id(setup: Json, key: string): number {
  const value = Number(setup[key]);
  if (!Number.isSafeInteger(value) || value < 1) throw new Error(`BLOCKED_MISSING_FRESH_ID: ${key}`);
  return value;
}

function stage(chain: Chain, name: string): Json {
  const value = chain.stages?.find((item) => item.stage === name && item.status === "PASS");
  if (!value) {
    throw new Error(
      `BLOCKED_NO_COMPLETED_FRESH_CHAIN: missing ${name}; first blocker ${JSON.stringify(chain.blocker || {})}`
    );
  }
  return value.data;
}

test.use({ viewport: { width: 1440, height: 1000 }, trace: "retain-on-failure" });

test("one fresh Capital Owner chain remains navigable from Idea to FID and Post-FID without browser business mutations", async ({
  page,
}, testInfo) => {
  test.setTimeout(480_000);
  const visits: Json[] = [];
  const requests: Json[] = [];
  const errors: string[] = [];
  const httpErrors: string[] = [];
  const browserWrites: string[] = [];
  const navigationWrites: Json[] = [];
  const navigationResponses: Json[] = [];
  let allowedNavigationPath: string | null = null;
  let allowedWorkspaceRoute: string | null = null;
  let current = "ARTIFACT_PREFLIGHT";
  const result: Json = {
    status: "BLOCKED",
    proof:
      "Authenticated real-browser traversal of one separately materialized fresh chain; not browser creation of every lifecycle record.",
    login_boundary:
      "The current login form has no tenant selector. Real tenant-scoped /auth/login is used; its actual session is hydrated into the existing auth store. No mocked login or fabricated token.",
    api_url: api,
    base_url: testInfo.project.use.baseURL,
    human_signoff: "PENDING_NOT_ASSUMED",
    visits,
    requests,
    runtime_errors: errors,
    http_errors: httpErrors,
    browser_business_writes: browserWrites,
    navigation_metadata_writes: navigationWrites,
    navigation_metadata_responses: navigationResponses,
  };
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (new URL(response.url()).pathname === allowedNavigationPath && response.request().method() === "POST") {
      navigationResponses.push({ path: allowedNavigationPath, status: response.status() });
    }
    if (response.url().includes("/api/v1/") && response.status() >= 400) {
      httpErrors.push(`${response.status()} ${new URL(response.url()).pathname}`);
    }
  });
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/") && !["GET", "HEAD", "OPTIONS"].includes(request.method())) {
      const path = new URL(request.url()).pathname;
      if (
        request.method() === "POST" &&
        path === allowedNavigationPath &&
        request.postDataJSON()?.route === allowedWorkspaceRoute
      ) {
        navigationWrites.push({
          method: request.method(),
          path,
          route: allowedWorkspaceRoute,
          scope: "Existing UI RecentWorkspace / workspace.opened metadata only",
        });
        return;
      }
      browserWrites.push(`${request.method()} ${new URL(request.url()).pathname}`);
    }
  });
  try {
    // Refuse operational/default ports even if someone accidentally reuses the
    // command against localhost:5173. This artifact is disposable UAT only.
    expect(["localhost", "127.0.0.1"]).toContain(new URL(api).hostname);
    expect(new URL(api).port).toBe("8840");
    expect(new URL(String(testInfo.project.use.baseURL)).port).toBe("5543");
    const chain = existsSync(chainPath) ? readJson<Chain>(chainPath) : {};
    const setup = chain.setup || readJson<Setup>(setupPath);
    const author = setup.actors.author;
    expect(author?.id, "Fresh author, not demo admin, is required").toBeGreaterThan(0);
    expect(author.email).not.toBe("admin@demo.local");
    const ideaId = id(setup, "idea_id");
    const analysisId = id(setup, "analysis_id");
    const proposalId = id(setup, "proposal_id");
    const strategicGateId = id(setup, "strategic_gate_id");
    const projectId = id(setup, "project_id");
    const portfolioId = id(setup, "portfolio_id");
    result.identity = {
      tenant_id: setup.tenant_id,
      actor_id: author.id,
      idea_id: ideaId,
      analysis_id: analysisId,
      proposal_id: proposalId,
      strategic_gate_id: strategicGateId,
      project_id: projectId,
      portfolio_id: portfolioId,
    };
    current = "TENANT_SCOPED_AUTHENTICATION";
    const login = await page.request.post(`${api}/api/v1/auth/login`, {
      data: { email: author.email, password, tenant_slug: setup.tenant_slug },
    });
    expect(login.status(), "Real tenant-scoped authentication must succeed").toBe(200);
    const session = (await login.json()) as { access_token: string; tenant_id: number; user: Json };
    expect(session.tenant_id).toBe(setup.tenant_id);
    expect(session.user.id).toBe(author.id);
    // Bearer credentials remain in memory and private Playwright traces only;
    // they are never written into result JSON or visible DOM screenshots.
    const headers = { Authorization: `Bearer ${session.access_token}` };
    await page.addInitScript(
      ({ token, user }) => {
        localStorage.setItem("pypmis_auth", JSON.stringify({ state: { token, user }, version: 0 }));
      },
      { token: session.access_token, user: session.user }
    );

    async function get<T>(path: string): Promise<T> {
      const started = performance.now();
      const response = await page.request.get(`${api}${path}`, { headers, timeout: 120_000 });
      requests.push({ path, status: response.status(), elapsed_ms: Math.round(performance.now() - started) });
      expect(response.status(), `Real API read failed at ${path}: ${await response.text()}`).toBe(200);
      return (await response.json()) as T;
    }

    async function visit(view: string, name: string) {
      await page.goto(`/app/strategy/${view}`);
      const surface = page.locator(`[data-strategic-view="${view}"]`);
      try {
        await expect(surface).toBeVisible();
      } catch (error) {
        if (await page.getByRole("heading", { name: "Create your first project", exact: true }).isVisible()) {
          throw new Error(
            `BLOCKED_STRATEGIC_UI_REQUIRES_LEGACY_PROJECT: ${view}; authenticated fresh tenant has a canonical Project but App returned the operational first-project screen before the strategic outlet`
          );
        }
        throw error;
      }
      const crumb = surface.getByRole("navigation", { name: "Strategic workflow breadcrumb", exact: true });
      await expect(crumb.locator('[aria-current="page"]')).toBeVisible();
      visits.push({ stage: current, view, name, path: new URL(page.url()).pathname });
      return surface;
    }

    async function screenshot(name: string) {
      await page.screenshot({ path: testInfo.outputPath(`${name}.png`), fullPage: true });
    }

    current = "IDEA";
    const idea = await get<Json>(`/api/v1/ideas/${ideaId}`);
    expect(idea.state).toBe("ACCEPTED");
    await visit("idea-lifecycle", "Idea Lifecycle");
    const ideas = page.getByRole("region", { name: "Idea Lifecycle", exact: true });
    await ideas.getByRole("textbox", { name: "Search ideas", exact: true }).fill(String(idea.idea_number));
    await ideas
      .getByRole("region", { name: "Idea register", exact: true })
      .getByRole("button")
      .filter({ hasText: String(idea.idea_number) })
      .click();
    await expect(ideas.getByRole("complementary", { name: "Idea detail", exact: true })).toContainText(
      String(idea.idea_number)
    );
    const relatedProposals = await get<Json[]>(`/api/v1/ideas/${ideaId}/project-proposals`);
    const linkedProposal = relatedProposals.find((item) => item.id === proposalId);
    expect(linkedProposal, "Actual linked Proposal must be visible after asynchronous hydration").toBeTruthy();
    await expect(ideas.locator(".ideaProposalLink")).toContainText(String(linkedProposal!.proposal_number));
    await screenshot("01-fresh-idea");

    current = "BUSINESS_ANALYSIS";
    const analysis = await get<Json>(`/api/v1/business-analyses/${analysisId}`);
    expect(analysis.source_idea_id).toBe(ideaId);
    expect(analysis.status).toBe("COMPLETED");
    await visit("business-analysis-options", "Business Analysis & Options");
    const ba = page.getByRole("region", { name: "Business Analysis and Options", exact: true });
    await ba
      .getByRole("textbox", { name: "Search Business Analysis", exact: true })
      .fill(String(analysis.analysis_number));
    await ba
      .getByRole("region", { name: "Business Analysis register", exact: true })
      .getByRole("button")
      .filter({ hasText: String(analysis.analysis_number) })
      .click();
    await expect(ba.getByRole("article", { name: "Business Analysis detail", exact: true })).toContainText(
      String(idea.idea_number)
    );
    const analysisReadiness = await get<Json>(`/api/v1/business-analyses/${analysisId}/readiness`);
    await expect(
      ba.getByRole("region", { name: "Business Analysis readiness", exact: true }).locator("strong")
    ).toHaveText(String(analysisReadiness.status));
    await screenshot("02-fresh-analysis");

    current = "PROJECT_PROPOSAL";
    const proposal = await get<Json>(`/api/v1/project-proposals/${proposalId}`);
    expect(proposal.source_idea_id).toBe(ideaId);
    expect(proposal.source_business_analysis_id).toBe(analysisId);
    await visit("project-proposal", "Project Proposals");
    const proposals = page.getByRole("region", { name: "Project Proposal", exact: true });
    await proposals
      .getByRole("textbox", { name: "Search Project Proposals", exact: true })
      .fill(String(proposal.proposal_number));
    await proposals
      .getByRole("region", { name: "Project Proposal register", exact: true })
      .getByRole("button")
      .filter({ hasText: String(proposal.proposal_number) })
      .click();
    await expect(proposals.getByRole("article", { name: "Project Proposal detail", exact: true })).toContainText(
      `Business Analysis ${analysisId}`
    );
    const proposalReadiness = await get<Json>(`/api/v1/project-proposals/${proposalId}/gate-readiness`);
    await expect(proposals.locator(".proposalReadiness")).toContainText(String(proposalReadiness.status));
    if (String(proposal.status).startsWith("STRATEGIC_GATE_")) {
      await expect(
        proposals.getByRole("region", { name: "Recorded Strategic Gate outcome", exact: true })
      ).toContainText(String(proposal.status));
      await expect(proposals.locator(".proposalReadiness")).toContainText(
        "Current Strategic Gate re-entry eligibility"
      );
    }
    const proposalDecisions = await get<Json[]>(`/api/v1/project-proposals/${proposalId}/strategic-gate-decisions`);
    const linkedDecision = proposalDecisions.find((item) => item.id === strategicGateId);
    expect(linkedDecision, "Selected Proposal must retain its actual Strategic Gate decision").toBeTruthy();
    await expect(
      proposals.getByRole("region", { name: "Strategic Gate Decisions for Proposal", exact: true })
    ).toContainText(String(linkedDecision!.decision_number));
    await screenshot("03-fresh-proposal");

    current = "STRATEGIC_GATE";
    const strategic = await get<Json>(`/api/v1/strategic-gate-decisions/${strategicGateId}`);
    expect(strategic.project_proposal_id).toBe(proposalId);
    expect(strategic.outcome).toBe("APPROVE");
    await visit("strategic-gate-decision", "Strategic Gate Decision");
    const gate = page.getByRole("region", { name: "Strategic Gate Decision", exact: true });
    await gate
      .getByRole("textbox", { name: "Search Strategic Gate Decisions", exact: true })
      .fill(String(strategic.decision_number));
    await gate
      .getByRole("region", { name: "Strategic Gate Decision register", exact: true })
      .getByRole("button")
      .filter({ hasText: String(strategic.decision_number) })
      .click();
    await expect(gate.getByRole("article", { name: "Strategic Gate Decision detail", exact: true })).toContainText(
      String(proposal.proposal_number)
    );
    const intakeReadiness = await get<Json>(
      `/api/v1/strategic-gate-decisions/${strategicGateId}/portfolio-intake-readiness`
    );
    await expect(gate.locator(".portfolioReadiness")).toContainText(String(intakeReadiness.status));
    result.hydrated_upstream_readiness = {
      business_analysis: analysisReadiness.status,
      project_proposal: proposalReadiness.status,
      strategic_intake: intakeReadiness.status,
      source: "Actual read-only API statuses reflected in the UI; no READY value inferred or manufactured.",
    };
    await screenshot("04-fresh-strategic-gate");

    current = "CANONICAL_PROJECT_AND_PORTFOLIO";
    const projectBefore = await get<Json>(`/api/v1/project-workspaces/${projectId}/overview`);
    expect(projectBefore.workspace_id).toBe(projectId);
    expect(projectBefore.governance_model).toBe("CAPITAL_OWNER");
    await visit("enterprise-explorer", "Enterprise Explorer / canonical Project Overview");
    await page
      .getByRole("textbox", { name: "Buscar por código o nombre", exact: true })
      .fill(String(projectBefore.project_name));
    await page
      .locator(".enterpriseTreeSelect")
      .filter({ hasText: String(projectBefore.project_name) })
      .click();
    await page.getByRole("button", { name: "Project Overview", exact: true }).click();
    await expect(page.locator(".projectOverviewCard")).toContainText(String(projectBefore.project_number));
    await screenshot("05a-fresh-canonical-project-overview");
    await visit("portfolio-projects", "Portfolio Projects");
    const portfolio = page.getByRole("region", { name: "Portfolio Projects", exact: true });
    await portfolio.getByRole("combobox", { name: "Portfolio", exact: true }).selectOption(String(portfolioId));
    await expect(portfolio).toContainText(String(projectBefore.project_number));
    await expect(portfolio).toContainText(String(proposal.proposal_number));
    await screenshot("05-fresh-project-portfolio");

    current = "DOWNSTREAM_CHAIN_PREFLIGHT";
    if (chain.backend_chain !== "PASS") {
      // Partial evidence may inspect real COMPLETED sources and the actual
      // blocked DRAFT package. It never substitutes them for a frozen package,
      // suppresses the failure below, creates evidence or records a FID.
      const completed = chain.stages?.find(
        (item) => item.stage === "COMMERCIAL_BENEFITS_FINAL_FIVE_CASE" && item.status === "PASS"
      );
      if (completed) {
        current = "PARTIAL_COMPLETED_BUSINESS_CASE_READ";
        const finalRevision = completed.data.business_case as Json;
        const caseId = id(finalRevision, "business_case_id");
        const cases = await get<Json[]>("/api/v1/business-cases");
        const businessCase = cases.find((item) => item.id === caseId);
        expect(businessCase!.project_workspace_id).toBe(projectId);
        expect((businessCase!.current_revision as Json).id).toBe(finalRevision.id);
        expect(finalRevision.status).toBe("COMPLETED");
        const caseReadiness = await get<Json>(`/api/v1/business-cases/${caseId}/readiness`);
        expect(caseReadiness.status).toBe("READY");
        expect(caseReadiness.source_current).toBe(true);
        const revisionsBefore = await get<Json[]>(`/api/v1/business-cases/${caseId}/revisions`);
        await visit("business-case-my", "Business Case Manager / current Five Case sources");
        const business = page.getByRole("region", { name: "Business Case Manager", exact: true });
        await business.getByRole("combobox", { name: /^Business Case/ }).selectOption(String(caseId));
        await expect(business.locator(".businessCaseSurface > header b")).toHaveText("COMPLETED · READY");
        await business.getByRole("button", { name: "Sources & Evidence", exact: true }).click();
        await expect(business.locator(".businessCaseSurface > header b")).toHaveText("COMPLETED · READY");
        await screenshot("06-fresh-completed-five-case-current-sources");
        result.partial_business_case = {
          id: caseId,
          revision_id: finalRevision.id,
          status: "COMPLETED",
          readiness: caseReadiness.status,
          source_current: caseReadiness.source_current,
          revision_hash: finalRevision.content_hash,
        };
        Object.assign(result.identity as Json, {
          business_case_id: caseId,
          business_case_revision_id: finalRevision.id,
        });

        current = "PARTIAL_ACTUAL_BLOCKED_GATE_READ";
        const overviewBefore = await get<Json>(`/api/v1/portfolios/${portfolioId}/investment-gate-preparation`);
        const matching = (overviewBefore.preparations as Json[]).filter((item) => {
          const captured = item.source_snapshot as Json;
          return (
            item.portfolio_workspace_id === portfolioId &&
            Array.isArray(captured.selected_project_ids) &&
            captured.selected_project_ids.includes(projectId)
          );
        });
        expect(matching, "Exactly one current package must belong to this actual Portfolio/Project chain").toHaveLength(
          1
        );
        const preparation = matching[0];
        const readiness = preparation.readiness as Json;
        expect(preparation.status).toBe("DRAFT");
        expect(readiness.readiness_status).toBe("BLOCKED");
        expect(readiness.source_current).toBe(true);
        expect(readiness.can_enter_investment_decision).toBe(false);
        expect(readiness.can_enter_fid).toBe(false);
        expect((readiness.blockers as string[]).length).toBeGreaterThan(0);
        await visit("investment-gate-preparation", "Investment Gate Preparation / actual blocked DRAFT");
        const preparationView = page.getByRole("region", { name: "Investment Gate Preparation", exact: true });
        await preparationView.getByRole("combobox", { name: /^Portfolio/ }).selectOption(String(portfolioId));
        await preparationView.getByRole("combobox", { name: /^Preparation/ }).selectOption(String(preparation.id));
        await expect(preparationView.locator(".gateFacts")).toContainText("DRAFT");
        await expect(preparationView.locator(".gateReadiness")).toContainText(String(readiness.final_output));
        await expect(preparationView.locator(".gateReadiness")).toContainText("Decision entry NO");
        await expect(preparationView.getByRole("button", { name: "Freeze package", exact: true })).toBeDisabled();
        await screenshot("07a-fresh-actual-blocked-draft-gate");
        await preparationView.getByRole("button", { name: "Evidence Package", exact: true }).click();
        await expect(preparationView).toContainText("Business Case Readiness");
        await screenshot("07b-fresh-actual-governed-evidence-blocked");
        result.partial_gate = {
          id: preparation.id,
          status: preparation.status,
          readiness: readiness.readiness_status,
          source_current: readiness.source_current,
          required_requirement_count: readiness.required_requirement_count,
          valid_requirement_count: readiness.valid_requirement_count,
          coverage_percent: readiness.coverage_percent,
          blockers: readiness.blockers,
          can_enter_investment_decision: readiness.can_enter_investment_decision,
          can_enter_fid: readiness.can_enter_fid,
          frozen: false,
        };
        Object.assign(result.identity as Json, { preparation_id: preparation.id });
        expect(await get<Json[]>(`/api/v1/business-cases/${caseId}/revisions`)).toEqual(revisionsBefore);
        const overviewAfter = await get<Json>(`/api/v1/portfolios/${portfolioId}/investment-gate-preparation`);
        expect((overviewAfter.preparations as Json[]).find((item) => item.id === preparation.id)).toEqual(preparation);
        expect(await get<Json>(`/api/v1/project-workspaces/${projectId}/overview`)).toEqual(projectBefore);
        expect(browserWrites).toEqual([]);
        result.partial_read_only_preservation = "PASS_FOR_SELECTED_PROJECT_BC_REVISIONS_AND_DRAFT_GATE";
      }
      current = "DOWNSTREAM_CHAIN_PREFLIGHT_NO_FID";
      throw new Error(
        `BLOCKED_NO_COMPLETED_FRESH_CHAIN_NO_FID: ${JSON.stringify(chain.blocker || { reason: "Backend current chain not completed" })}`
      );
    }
    expect(chain.database_dialect).toBe("postgresql");
    expect(chain.head).toBe("20261011_0068");
    const final = stage(chain, "COMMERCIAL_BENEFITS_FINAL_FIVE_CASE");
    const finalRevision = final.business_case as Json;
    const caseId = id(finalRevision, "business_case_id");
    const preparationId = id(stage(chain, "A27_A29_GATE_PREPARATION_FREEZE").preparation as Json, "id");
    const fidId = id(stage(chain, "A30_FID"), "id");
    const historicalPostFid = stage(chain, "A31_POST_FID") as unknown as Json[];
    const initialEligibility = historicalPostFid.find((item) => item.project_workspace_id === projectId);
    expect(initialEligibility).toBeTruthy();
    expect(initialEligibility!.eligibility_status).toBe("READY_FOR_PROJECT_WORKSPACE_INITIALIZATION");
    expect(initialEligibility!.workspace_status).toBe("pending");
    expect(initialEligibility!.can_activate).toBe(false);
    const initialized = stage(chain, "PROJECT_INITIALIZED_NOT_ACTIVATED");
    expect(initialized.workspace_id).toBe(projectId);
    expect(initialized.state).toBe("READY_FOR_ACTIVATION");
    expect(initialized.workspace_status).toBe("pending");
    const activation = stage(chain, "PROJECT_WORKSPACE_INITIALIZATION_ACTIVATION");
    expect(activation.initialize_actor_id).toBe(id(setup, "initializer_id"));
    expect(activation.activate_actor_id).toBe(id(setup, "activator_id"));
    expect(activation.initialize_actor_id).not.toBe(activation.activate_actor_id);
    expect((activation.activated as Json).workspace_id).toBe(projectId);
    expect((activation.activated as Json).state).toBe("ACTIVATED");
    expect((activation.activated as Json).workspace_status).toBe("active");
    expect((activation.activated as Json).activated_by_user_id).toBe(activation.activate_actor_id);
    expect(projectBefore.status).toBe("active");
    expect(projectBefore.initialization_state).toBe("ACTIVATED");
    Object.assign(result.identity as Json, { business_case_id: caseId, preparation_id: preparationId, fid_id: fidId });

    current = "FINAL_FIVE_CASE_BUSINESS_CASE";
    const casesBefore = await get<Json[]>("/api/v1/business-cases");
    const businessCase = casesBefore.find((item) => item.id === caseId);
    expect(businessCase, "Final BC aggregate must be from this Project, not the first register row").toBeTruthy();
    expect(businessCase!.project_workspace_id).toBe(projectId);
    expect((businessCase!.current_revision as Json).id).toBe(finalRevision.id);
    const revisionsBefore = await get<Json[]>(`/api/v1/business-cases/${caseId}/revisions`);
    expect(
      revisionsBefore.some((item) => item.id !== finalRevision.id),
      "FEL-1 predecessor history remains available"
    ).toBe(true);
    await visit("business-case-my", "Business Case Manager");
    const business = page.getByRole("region", { name: "Business Case Manager", exact: true });
    await business.getByRole("combobox", { name: /^Business Case/ }).selectOption(String(caseId));
    await business.getByRole("button", { name: "Sources & Evidence", exact: true }).click();
    await expect(business.locator(".businessCaseSurface > header b")).toHaveText("COMPLETED · READY");
    const caseReadiness = await get<Json>(`/api/v1/business-cases/${caseId}/readiness`);
    expect(caseReadiness.status).toBe("READY");
    expect(caseReadiness.source_current).toBe(true);
    for (const source of (businessCase!.current_revision as Json).source_evidence_matrix_json as Json[]) {
      const name = String(source.source_module)
        .replace(/_JSON$/i, "")
        .toLowerCase()
        .replace(/_/g, " ")
        .replace(/\b\w/g, (letter) => letter.toUpperCase());
      const rows = business
        .locator(".businessCaseEvidenceTable tbody tr")
        .filter({ has: page.getByText(name, { exact: true }) });
      expect(await rows.count(), `Captured matrix source ${name} must render`).toBeGreaterThan(0);
      for (const row of await rows.all()) {
        const cells = row.getByRole("cell");
        if (source.hash) await expect(cells.nth(3)).toHaveAttribute("title", String(source.hash));
        await expect(cells.nth(4)).toHaveText(
          String(source.source_readiness ?? source.readiness ?? source.source_status ?? "NOT_AVAILABLE")
        );
        await expect(cells.nth(5)).toHaveText(
          source.available === false
            ? "NOT AVAILABLE"
            : source.source_current === false
              ? "STALE"
              : source.source_current === true
                ? "CURRENT"
                : "NOT EVALUATED"
        );
      }
    }
    await screenshot("06-fresh-final-five-case-sources");

    current = "FROZEN_GATE07J";
    const gateBefore = await get<Json>(`/api/v1/portfolios/${portfolioId}/investment-gate-preparation`);
    const preparation = (gateBefore.preparations as Json[]).find((item) => item.id === preparationId);
    expect(preparation, "Frozen package must belong to the selected Portfolio/Project chain").toBeTruthy();
    expect(preparation!.portfolio_workspace_id).toBe(portfolioId);
    expect(preparation!.tenant_id).toBe(setup.tenant_id);
    expect(preparation!.status).toBe("FROZEN");
    const readiness = preparation!.readiness as Json;
    expect(readiness.readiness_status).toBe("READY");
    expect(readiness.source_current).toBe(true);
    expect(readiness.coverage_percent).toBe(100);
    expect(readiness.valid_project_count).toBe(1);
    expect(readiness.blocked_project_count).toBe(0);
    expect((preparation!.source_snapshot as Json).selected_project_ids).toEqual([projectId]);
    const classBTypes = [
      "PERMIT_READINESS",
      "CONTRACTING_STRATEGY_READINESS",
      "EXECUTION_PLAN_READINESS",
      "SCHEDULE_MATURITY",
    ];
    const classB = (preparation!.evidence as Json[]).filter((item) => classBTypes.includes(String(item.evidence_type)));
    expect(classB).toHaveLength(4);
    for (const item of classB) {
      expect(item.classification).toBe("B");
      expect(item.evidence_origin).toBe("MANUAL_REFERENCE");
      expect(item.scope_type).toBe("EACH_PROJECT");
      expect(item.scope_id).toBe(projectId);
      expect(item.status).toBe("VALID");
      expect(item.resolution_status).toBe("VALID");
      expect(item.source_record_id).toBeTruthy();
      expect(Number(item.submitted_by)).toBeGreaterThan(0);
      expect(Number(item.validated_by)).toBeGreaterThan(0);
      expect(item.validated_by).not.toBe(item.submitted_by);
      expect(item.submitted_at).toBeTruthy();
      expect(item.validated_at).toBeTruthy();
      expect(item.validation_note).toBeTruthy();
      expect((item.evidence_refs as Json[]).length).toBeGreaterThan(0);
      expect(item.scope_reference_hash).toBe(preparation!.recommended_project_set_hash);
    }
    await visit("investment-gate-preparation", "Investment Gate Preparation");
    const preparationView = page.getByRole("region", { name: "Investment Gate Preparation", exact: true });
    await preparationView.getByRole("combobox", { name: /^Portfolio/ }).selectOption(String(portfolioId));
    await preparationView.getByRole("combobox", { name: /^Preparation/ }).selectOption(String(preparationId));
    await expect(preparationView).toContainText("FROZEN");
    await preparationView.getByRole("button", { name: "Evidence Package", exact: true }).click();
    await expect(preparationView).toContainText("Business Case Readiness");
    for (const item of classB) {
      const card = preparationView
        .locator(".evidenceGrid > article")
        .filter({ has: page.getByText(String(item.requirement_key), { exact: true }) });
      await expect(card).toHaveCount(1);
      await expect(card.locator(":scope > div").first().locator("b")).toHaveText("VALID");
      await expect(card).toContainText(`Class B · Blocking · EACH_PROJECT #${projectId}`);
    }
    await screenshot("07-fresh-frozen-evidence-package");
    result.controlled_class_b = classB.map((item) => ({
      evidence_id: item.id,
      requirement_key: item.requirement_key,
      scope_id: item.scope_id,
      reference_id: item.source_record_id,
      status: item.status,
      resolution_status: item.resolution_status,
      submitted_by: item.submitted_by,
      validated_by: item.validated_by,
      scope_reference_hash: item.scope_reference_hash,
    }));
    result.gate_readiness = readiness;

    current = "GATE07K_FFA_GO_FID";
    const decisions = await get<Json[]>("/api/v1/investment-decisions");
    const decision = decisions.find((item) => item.id === fidId);
    expect(decision).toBeTruthy();
    expect(decision!.investment_gate_preparation_id).toBe(preparationId);
    expect(decision!.portfolio_workspace_id).toBe(portfolioId);
    expect(decision!.profile_code).toBe("PYP-FFA");
    expect(decision!.status).toBe("DECIDED");
    expect(decision!.outcome).toBe("GO");
    expect(decision!.is_fid).toBe(true);
    expect(decision!.full_funds_authorized).toBe(true);
    expect(decision!.can_activate_project).toBe(false);
    expect(decision!.source_preparation_hash).toBe(preparation!.preparation_hash);
    await visit("investment-decision-output", "Investment Decision / FID");
    const fid = page.getByRole("region", { name: "Investment Decision / FID", exact: true });
    await fid.getByRole("combobox", { name: "Decision", exact: true }).selectOption(String(fidId));
    await expect(fid.getByText("FID YES", { exact: true })).toBeVisible();
    await expect(fid.getByText("Project activation NO", { exact: true })).toBeVisible();
    await fid.getByRole("button", { name: "Authorization Output", exact: true }).click();
    await expect(fid.locator("pre")).toContainText('"full_funds_authorized": true');
    await expect(fid.locator("pre")).toContainText('"can_activate_project": false');
    await screenshot("08-fresh-fid-no-operational-activation");

    current = "POST_FID_ELIGIBILITY";
    await visit("post-fid-eligibility-matrix", "Post-FID Project Governance");
    const post = page.getByRole("region", { name: "Post-FID Project Governance", exact: true });
    await post.getByRole("combobox", { name: "Investment Decision / FID", exact: true }).selectOption(String(fidId));
    await expect(post).toContainText(String(projectBefore.project_number));
    const postData = await get<Json>(`/api/v1/post-fid-governance/${fidId}`);
    const eligibility = (postData.projects as Json[]).find((item) => item.project_workspace_id === projectId);
    expect(eligibility, "Post-FID must reference the same canonical Project").toBeTruthy();
    expect(eligibility!.fid_current).toBe(true);
    expect(eligibility!.eligibility_status).toBe("NO_REACTIVATION_REQUIRED");
    expect(eligibility!.can_activate).toBe(false);
    expect(eligibility!.workspace_status).toBe("active");
    expect(eligibility!.initialization_state).toBe("ACTIVATED");
    await expect(post).toContainText(String(eligibility!.eligibility_status));
    await screenshot("09-fresh-post-fid-eligibility");
    result.governed_initialization_activation = {
      historical_post_fid: initialEligibility,
      initialized_without_activation: initialized,
      initializer_id: activation.initialize_actor_id,
      activator_id: activation.activate_actor_id,
      activated: activation.activated,
      current_post_fid: eligibility,
      current_project_status: projectBefore.status,
      current_initialization_state: projectBefore.initialization_state,
      evidence_source:
        "Separate real backend lifecycle stages and current read-only API; no browser command or inferred activation.",
    };

    current = "ACTIVATED_WORKSPACE_HOME_ROUTING";
    const workspaceContextBefore = await get<Json>(`/api/v1/workspaces/${projectId}/context`);
    expect((workspaceContextBefore.identity as Json).workspace_id).toBe(projectId);
    expect((workspaceContextBefore.identity as Json).workspace_status).toBe("ACTIVE");
    const homeNavigation = (workspaceContextBefore.navigator as Json[]).find((item) => item.code === "home");
    expect(homeNavigation).toBeTruthy();
    expect(homeNavigation!.state).toBe("READY");
    allowedNavigationPath = `/api/v1/workspaces/${projectId}/open`;
    allowedWorkspaceRoute = `/workspaces/${projectId}/home`;
    const opened = page.waitForResponse(
      (response) => new URL(response.url()).pathname === allowedNavigationPath && response.request().method() === "POST"
    );
    await page.goto(allowedWorkspaceRoute);
    expect((await opened).status(), "Existing UI workspace open metadata must remain scoped and successful").toBe(200);
    const operational = page.locator(".workspaceOperationalShell");
    await expect(operational).toBeVisible();
    await expect(operational.locator(".workspaceHeader h1")).toHaveText(String(projectBefore.project_name));
    await expect(operational.locator(".workspaceHeader")).toContainText(String(projectBefore.project_number));
    await expect(operational.locator(".workspaceHeader")).toContainText("ACTIVE");
    await expect(operational.getByRole("heading", { name: String(homeNavigation!.label), exact: true })).toBeVisible();
    expect(navigationWrites.length).toBeGreaterThan(0);
    await screenshot("10-fresh-governed-active-workspace-home");
    result.operational_workspace_routing = {
      workspace_id: projectId,
      route: allowedWorkspaceRoute,
      status: "PASS",
      metadata_boundary:
        "Only the existing UI POST to this exact Workspace open endpoint updates RecentWorkspace and navigation SecurityEvent; no business lifecycle command.",
    };

    current = "READ_ONLY_PRESERVATION";
    expect(await get<Json[]>(`/api/v1/business-cases/${caseId}/revisions`)).toEqual(revisionsBefore);
    const gateAfter = await get<Json>(`/api/v1/portfolios/${portfolioId}/investment-gate-preparation`);
    expect((gateAfter.preparations as Json[]).find((item) => item.id === preparationId)).toEqual(preparation);
    expect(await get<Json>(`/api/v1/project-workspaces/${projectId}/overview`)).toEqual(projectBefore);
    expect((await get<Json[]>("/api/v1/investment-decisions")).find((item) => item.id === fidId)).toEqual(decision);
    expect(await get<Json>(`/api/v1/post-fid-governance/${fidId}`)).toEqual(postData);
    expect(errors).toEqual([]);
    expect(httpErrors).toEqual([]);
    expect(browserWrites, "Browser traversal must not mutate business records").toEqual([]);
    expect(navigationResponses).toHaveLength(navigationWrites.length);
    expect(navigationResponses.every((item) => item.status === 200)).toBe(true);
    result.status = "PASS";
    result.scope =
      "Same-record browser navigation plus read-only API lineage checks; lifecycle creation is separately proven by the backend chain. Only the existing selected-Workspace open UI metadata POST is permitted and recorded separately.";
  } catch (error) {
    result.status = String(error).includes("BLOCKED_") ? "BLOCKED" : "FAIL";
    result.blocker = { stage: current, detail: error instanceof Error ? error.message : String(error) };
    if (page.url().startsWith("http")) {
      await page.screenshot({ path: testInfo.outputPath("first-blocker.png"), fullPage: true }).catch(() => undefined);
    }
    throw error;
  } finally {
    result.finished_at = new Date().toISOString();
    mkdirSync(dirname(resultPath), { recursive: true });
    writeFileSync(resultPath, JSON.stringify(result, null, 2), "utf8");
    await testInfo.attach("fresh-browser-result.json", {
      body: Buffer.from(JSON.stringify(result, null, 2)),
      contentType: "application/json",
    });
  }
});
