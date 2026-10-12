import { expect, type APIResponse, type Locator, type Page, test } from "@playwright/test";

// Real Chromium -> real API -> disposable PostgreSQL. No intercepts or mocks.
const apiUrl = process.env.E2E_API_URL || "http://127.0.0.1:8816";
const baseUrl = process.env.E2E_BASE_URL || "http://127.0.0.1:5519";
const apiRoot = `${apiUrl}/api/v1/qra-foundation`;
const password = process.env.E2E_QRA_PASSWORD || "1234";
const authority = process.env.E2E_QRA_AUTHORITY_EMAIL || "qra.authority@demo.local";
type Json = Record<string, unknown>;
type GovernedRecord = Json & {
  id: number;
  number: string;
  version: number;
  status: string;
  hash: string;
  revision_version: number;
  aggregate_json: Json;
  snapshot_json: Json;
};
type Configuration = Json & { id: number; version: number; status: string; content_json: Json };
type ProjectOption = { id: number; name: string; code: string };

async function json<T>(response: APIResponse, status = 200): Promise<T> {
  expect(response.status(), await response.text()).toBe(status);
  return (await response.json()) as T;
}
async function login(page: Page, user: string) {
  await page.goto("/login");
  await page.getByLabel("User").fill(user);
  await page.getByLabel("Password").fill(password);
  const waiting = page.waitForResponse(
    (response) => response.url().includes("/api/v1/auth/login") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /sign in/i }).click();
  const token = (await json<{ access_token: string }>(await waiting)).access_token;
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
  return token;
}
async function expand(page: Page, name: string) {
  const button = page
    .getByRole("navigation", { name: "Control Flow" })
    .getByRole("button", { name, exact: true })
    .first();
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
}
async function openWorkspace(page: Page, projectId: number) {
  await page.goto("/app/strategy/qra-foundation");
  const workspace = page.getByRole("region", { name: "QRA Foundation workspace", exact: true });
  await expect(workspace).toBeVisible();
  await workspace.getByRole("combobox", { name: "Project Workspace", exact: true }).selectOption(String(projectId));
  await expect(workspace.getByRole("button", { name: "Create cost source assessment", exact: true })).toBeEnabled();
  return workspace;
}
async function mutation(page: Page, path: string, button: Locator, status = 200) {
  const waiting = page.waitForResponse(
    (response) => response.url().endsWith(path) && response.request().method() !== "GET",
    { timeout: 120_000 }
  );
  await button.click();
  return await json<Json>(await waiting, status);
}
async function selectDomain(workspace: Locator, domain: "cost" | "schedule" | "model") {
  await workspace
    .getByRole("navigation", { name: "QRA Foundation subviews", exact: true })
    .getByRole("button", {
      name:
        domain === "cost"
          ? "Cost Source Readiness"
          : domain === "schedule"
            ? "Schedule Source Readiness"
            : "Model Definition",
      exact: true,
    })
    .click();
}
async function selectRecord(workspace: Locator, id: number) {
  await workspace.getByRole("combobox", { name: "Selected governed record", exact: true }).selectOption(String(id));
}
async function fixtureProject(page: Page, headers: Record<string, string>) {
  const options = await json<{ projects: ProjectOption[] }>(await page.request.get(`${apiRoot}/options`, { headers }));
  const project = options.projects.find((item) => /QRA Foundation|QRA-PROJECT/.test(item.name + item.code));
  expect(
    project,
    "Provision the guarded disposable QRA Project before running the real browser acceptance"
  ).toBeTruthy();
  return project!;
}
test.use({ trace: "on" });
test.describe.serial("QRA Foundation real governed release", () => {
  test("USER cost/schedule/model lifecycle, independent source/model authority and frozen history", async ({
    page,
    browser,
  }) => {
    test.setTimeout(900_000);
    const token = await login(page, "admin");
    const headers = { Authorization: `Bearer ${token}` };
    const project = await fixtureProject(page, headers);
    await expand(page, "Enterprise Strategy Manager");
    await expand(page, "Business Case & Investment Development");
    await page
      .getByRole("navigation", { name: "Control Flow" })
      .getByRole("button", { name: "QRA", exact: true })
      .click();
    await expect(page).toHaveURL(/\/app\/strategy\/qra-foundation$/);
    const workspace = await openWorkspace(page, project.id);
    await expect(
      workspace.getByRole("button", { name: /Publish|Clone to DRAFT|Run simulation|Calculate contingency/i })
    ).toHaveCount(0);
    const contexts = await json<Json>(
      await page.request.get(`${apiRoot}/projects/${project.id}/contexts`, { headers })
    );
    expect(contexts).toHaveProperty("owner_capability");
    expect(contexts).toHaveProperty("risk_readiness");
    const sources = await json<{ items: Json[] }>(
      await page.request.get(`${apiRoot}/projects/${project.id}/cost-source-options`, { headers })
    );
    const source = sources.items.find((item) => item.kind === "CONTROL_ACCOUNTS");
    expect(
      source,
      "Canonical imported control-account values are context, requiring separate source qualification"
    ).toBeTruthy();
    const cost = (await mutation(
      page,
      `/api/v1/qra-foundation/projects/${project.id}/cost-assessments`,
      workspace.getByRole("button", { name: "Create cost source assessment", exact: true }),
      201
    )) as GovernedRecord;
    await workspace.getByRole("button", { name: "Edit cost source assessment", exact: true }).click();
    const editor = workspace.getByRole("article", { name: "QRA definition editor", exact: true });
    await editor.getByLabel("Source evidence quality", { exact: true }).selectOption("VERIFIED");
    await editor.getByLabel("Source confidence", { exact: true }).selectOption("HIGH");
    await editor.getByLabel("source_refs JSON", { exact: true }).fill(
      JSON.stringify([
        {
          kind: source!.kind,
          id: source!.id,
          reference: source!.reference,
          version: source!.version,
          hash: source!.hash,
        },
      ])
    );
    const costBasis = {
      source_identity: source!.reference,
      basis_date: new Date().toISOString().slice(0, 10),
      currency: "USD",
      estimate_basis: "BOE-QRA-FOUNDATION-001",
      estimate_class: "GOVERNED_PROJECT_CLASS",
      scope_coverage: 100,
      wbs_cbs_alignment: "CANONICAL_IMPORTED",
      quantity_basis: "Imported deterministic quantities",
      rate_basis: "Governed current rates",
      allowances: "NO_ALLOWANCE",
      escalation_basis: "CURRENT_BASIS_NO_ESCALATION",
      contingency_basis: "BASE_COST",
      exclusions: "NONE",
      assumptions: "Manual source qualification with references",
      total_amount: source!.amount,
      granularity: "CONTROL_ACCOUNT",
      structure: "CONTROL_ACCOUNT",
      evidence_refs: [{ reference: "BOE-QRA-FOUNDATION-001", version: "1" }],
    };
    await editor.getByLabel("basis JSON", { exact: true }).fill(JSON.stringify(costBasis));
    await editor
      .getByLabel("evidence_refs JSON", { exact: true })
      .fill(JSON.stringify([{ reference: "BOE-QRA-FOUNDATION-001", version: "1" }]));
    await mutation(
      page,
      `/api/v1/qra-foundation/cost-assessments/${cost.id}`,
      editor.getByRole("button", { name: "Save cost source assessment", exact: true })
    );
    const costPreview = await mutation(
      page,
      `/api/v1/qra-foundation/cost-assessments/${cost.id}/preview`,
      workspace.getByRole("button", { name: "Preview readiness", exact: true })
    );
    expect(costPreview.persisted).toBe(false);
    expect(costPreview.blockers).toEqual([]);
    const costItems = costPreview.population as Json[];
    expect(costItems.length).toBeGreaterThan(0);
    await mutation(
      page,
      `/api/v1/qra-foundation/cost-assessments/${cost.id}/submit`,
      workspace.getByRole("button", { name: "Submit for review", exact: true })
    );
    await expect(workspace.getByRole("button", { name: "Complete source assessment", exact: true })).toHaveCount(0);

    await selectDomain(workspace, "schedule");
    const scheduleSources = await json<{ items: Json[] }>(
      await page.request.get(`${apiRoot}/projects/${project.id}/schedule-source-options`, { headers })
    );
    const scheduleSource = scheduleSources.items.find((item) => item.metadata_available === true);
    expect(scheduleSource).toBeTruthy();
    const schedule = (await mutation(
      page,
      `/api/v1/qra-foundation/projects/${project.id}/schedule-assessments`,
      workspace.getByRole("button", { name: "Create schedule source assessment", exact: true }),
      201
    )) as GovernedRecord;
    await workspace.getByRole("button", { name: "Edit schedule source assessment", exact: true }).click();
    const scheduleEditor = workspace.getByRole("article", { name: "QRA definition editor", exact: true });
    await scheduleEditor.getByLabel("Source evidence quality", { exact: true }).selectOption("VERIFIED");
    await scheduleEditor.getByLabel("Source confidence", { exact: true }).selectOption("HIGH");
    await scheduleEditor.getByLabel("source_refs JSON", { exact: true }).fill(
      JSON.stringify([
        {
          kind: "SCHEDULE_IMPORT",
          id: scheduleSource!.id,
          reference: scheduleSource!.reference,
          version: scheduleSource!.version,
        },
      ])
    );
    await scheduleEditor.getByLabel("basis JSON", { exact: true }).fill(
      JSON.stringify({
        schedule_type: "CURRENT",
        scope_frozen: true,
        logic_current: true,
        uncertainty_classification: "EXPLICIT",
        eligible_activity_refs: ["A-MINE"],
        deterministic_activity_refs: ["A-START", "A-FINISH"],
        evidence_refs: [{ reference: "MANUAL-P6-XML-QRA-001" }],
      })
    );
    await scheduleEditor
      .getByLabel("evidence_refs JSON", { exact: true })
      .fill(JSON.stringify([{ reference: "MANUAL-P6-XML-QRA-001", version: "1" }]));
    await mutation(
      page,
      `/api/v1/qra-foundation/schedule-assessments/${schedule.id}`,
      scheduleEditor.getByRole("button", { name: "Save schedule source assessment", exact: true })
    );
    const schedulePreview = await mutation(
      page,
      `/api/v1/qra-foundation/schedule-assessments/${schedule.id}/preview`,
      workspace.getByRole("button", { name: "Preview readiness", exact: true })
    );
    expect(schedulePreview.persisted).toBe(false);
    expect(schedulePreview.blockers).toEqual([]);
    await mutation(
      page,
      `/api/v1/qra-foundation/schedule-assessments/${schedule.id}/submit`,
      workspace.getByRole("button", { name: "Submit for review", exact: true })
    );
    const independent = await browser.newContext({ baseURL: baseUrl });
    const reviewPage = await independent.newPage();
    const authorityToken = await login(reviewPage, authority);
    const authorityHeaders = { Authorization: `Bearer ${authorityToken}` };
    const reviewWorkspace = await openWorkspace(reviewPage, project.id);
    for (const [kind, id] of [
      ["cost", cost.id],
      ["schedule", schedule.id],
    ] as const) {
      await selectDomain(reviewWorkspace, kind);
      await selectRecord(reviewWorkspace, id);
      await mutation(
        reviewPage,
        `/api/v1/qra-foundation/${kind}-assessments/${id}/review`,
        reviewWorkspace.getByRole("button", { name: "Review definition", exact: true })
      );
      const completed = await mutation(
        reviewPage,
        `/api/v1/qra-foundation/${kind}-assessments/${id}/complete`,
        reviewWorkspace.getByRole("button", { name: "Complete source assessment", exact: true })
      );
      expect(completed.status).toBe("COMPLETED");
      expect(completed.hash).toMatch(/^[a-f0-9]{64}$/);
      const provider = await json<Json>(
        await reviewPage.request.get(`${apiRoot}/projects/${project.id}/${kind}-provider-evidence`, {
          headers: authorityHeaders,
        })
      );
      expect(provider.status).toBe("AVAILABLE");
      expect(provider.source_current).toBe(true);
      if (kind === "schedule") {
        const sections = reviewWorkspace.getByRole("navigation", {
          name: "Schedule Source Readiness sections",
          exact: true,
        });
        await sections.getByRole("button", { name: "Source Snapshot", exact: true }).click();
        await expect(reviewWorkspace.getByRole("article", { name: "QRA source lineage", exact: true })).toContainText(
          String(completed.hash)
        );
        for (const [label, field] of [
          ["Constraints / Lags", "negative_lags"],
          ["Open Ends", "missing_predecessors"],
        ] as const) {
          await sections.getByRole("button", { name: label, exact: true }).click();
          await expect(reviewWorkspace.getByRole("article", { name: `QRA ${label}`, exact: true })).toContainText(
            field
          );
        }
      }
    }
    await selectDomain(workspace, "model");
    await workspace.getByLabel("New model analysis type", { exact: true }).selectOption("INTEGRATED_COST_SCHEDULE_QRA");
    const model = (await mutation(
      page,
      `/api/v1/qra-foundation/projects/${project.id}/models`,
      workspace.getByRole("button", { name: "Create model definition", exact: true }),
      201
    )) as GovernedRecord;
    expect(model.number).toMatch(/^QRM-/);
    await workspace.getByRole("button", { name: "Edit model definition", exact: true }).click();
    const modelEditor = workspace.getByRole("article", { name: "QRA definition editor", exact: true });
    await modelEditor
      .getByLabel("Model purpose", { exact: true })
      .fill("Future integrated analysis definition only; no QraRun or result exists.");
    await modelEditor.getByLabel("Cost assessment ID", { exact: true }).fill(String(cost.id));
    await modelEditor.getByLabel("Schedule assessment ID", { exact: true }).fill(String(schedule.id));
    const evidence = [{ reference: "QRA-WORKSHOP-FOUNDATION-001", version: "1" }];
    const inputs: Json[] = costItems.map((item) => ({
      source_kind: "COST",
      source_item_ref: item.ref,
      mode: "UNCERTAIN",
      range_type: "MIN_MOST_LIKELY_MAX",
      values: { min: Number(item.amount) * 0.8, base: item.amount, max: Number(item.amount) * 1.3 },
      distribution_family: "TRIANGULAR",
      parameters: {},
      rationale: "Governed three-point estimate; calibration not claimed.",
      evidence_refs: evidence,
      range_source: "EXPERT_JUDGMENT",
      quality: "VERIFIED",
      unit: "USD",
      status: "VALIDATED",
    }));
    inputs.push({
      source_kind: "SCHEDULE",
      source_item_ref: "A-MINE",
      mode: "UNCERTAIN",
      range_type: "MIN_MOST_LIKELY_MAX",
      values: { min: 64, base: 80, max: 104 },
      distribution_family: "TRIANGULAR",
      parameters: {},
      rationale: "Imported hours form a deterministic base, with explicit governed workshop ranges.",
      evidence_refs: evidence,
      range_source: "EXPERT_JUDGMENT",
      quality: "VERIFIED",
      unit: "HOURS",
      status: "VALIDATED",
    });
    for (const ref of ["A-START", "A-FINISH"])
      inputs.push({
        source_kind: "SCHEDULE",
        source_item_ref: ref,
        mode: "DETERMINISTIC",
        values: {},
        parameters: {},
        rationale: "Imported milestone explicitly deterministic under approved policy, never silently omitted.",
        evidence_refs: evidence,
        quality: "VERIFIED",
        status: "VALIDATED",
      });
    await mutation(
      page,
      `/api/v1/qra-foundation/models/${model.id}/metadata`,
      modelEditor.getByRole("button", { name: "Save model definition", exact: true })
    );
    await workspace.getByRole("button", { name: "Edit input page", exact: true }).click();
    const inputEditor = workspace.getByRole("article", { name: "QRA paged input editor", exact: true });
    await inputEditor.getByLabel("Input page JSON", { exact: true }).fill(JSON.stringify(inputs));
    await mutation(
      page,
      `/api/v1/qra-foundation/models/${model.id}/inputs`,
      inputEditor.getByRole("button", { name: "Save input page", exact: true })
    );
    const definitionPreview = await mutation(
      page,
      `/api/v1/qra-foundation/models/${model.id}/preview`,
      workspace.getByRole("button", { name: "Preview readiness", exact: true })
    );
    expect(definitionPreview.persisted).toBe(false);
    expect(definitionPreview.blockers).toEqual([]);
    await mutation(
      page,
      `/api/v1/qra-foundation/models/${model.id}/submit`,
      workspace.getByRole("button", { name: "Submit for review", exact: true })
    );
    await expect(workspace.getByRole("button", { name: "Approve for analysis", exact: true })).toHaveCount(0);
    const submitted = await json<GovernedRecord>(await page.request.get(`${apiRoot}/models/${model.id}`, { headers }));
    const ownApproval = await page.request.post(`${apiRoot}/models/${model.id}/approve`, {
      headers: {
        ...headers,
        "If-Match": String(submitted.revision_version),
        "Idempotency-Key": `qra-own-approve-${Date.now()}`,
      },
      data: {},
    });
    expect([403, 409]).toContain(ownApproval.status());
    await selectDomain(reviewWorkspace, "model");
    await selectRecord(reviewWorkspace, model.id);
    await mutation(
      reviewPage,
      `/api/v1/qra-foundation/models/${model.id}/review`,
      reviewWorkspace.getByRole("button", { name: "Review definition", exact: true })
    );
    const approved = (await mutation(
      reviewPage,
      `/api/v1/qra-foundation/models/${model.id}/approve`,
      reviewWorkspace.getByRole("button", { name: "Approve for analysis", exact: true })
    )) as GovernedRecord;
    expect(approved.status).toBe("APPROVED_FOR_ANALYSIS");
    expect(approved.hash).toMatch(/^[a-f0-9]{64}$/);
    const current = await json<Json>(
      await reviewPage.request.get(`${apiRoot}/projects/${project.id}/model-readiness`, { headers: authorityHeaders })
    );
    expect(JSON.stringify(current)).toContain("READY_FOR_QRA_ANALYSIS");
    for (const forbidden of [
      "simulation_results",
      "p50",
      "p80",
      "p90",
      "contingency_amount",
      "probabilistic_completion_date",
    ])
      expect(approved).not.toHaveProperty(forbidden);
    const modelSections = reviewWorkspace.getByRole("navigation", { name: "Model Definition sections", exact: true });
    for (const [label, field] of [
      ["Methodology", "methodology"],
      ["Uncertainty Rules", "range_policies"],
      ["Distribution Rules", "distribution_families"],
      ["Correlation Rules", "NO_CORRELATION"],
      ["Governance / SoD", "separation_of_duties"],
      ["Validity", "valid_from"],
    ] as const) {
      await modelSections.getByRole("button", { name: label, exact: true }).click();
      await expect(reviewWorkspace.getByRole("article", { name: `QRA ${label}`, exact: true })).toContainText(field);
    }
    await reviewWorkspace
      .getByRole("navigation", { name: "QRA Foundation subviews", exact: true })
      .getByRole("button", { name: "History", exact: true })
      .click();
    await reviewWorkspace.getByLabel("History domain", { exact: true }).selectOption("model");
    await expect(reviewWorkspace.getByRole("article", { name: "QRA immutable history", exact: true })).toContainText(
      approved.hash
    );
    const historyBefore = await json<GovernedRecord>(
      await reviewPage.request.get(`${apiRoot}/models/${model.id}`, { headers: authorityHeaders })
    );
    await reviewWorkspace.getByRole("button", { name: "Refresh Preview", exact: true }).click();
    await expect(
      reviewWorkspace.getByRole("article", { name: "QRA non-persisted preview", exact: true })
    ).toContainText("persisted=false");
    const unchanged = await json<GovernedRecord>(
      await reviewPage.request.get(`${apiRoot}/models/${model.id}`, { headers: authorityHeaders })
    );
    expect(unchanged.hash).toBe(historyBefore.hash);
    expect(unchanged.snapshot_json).toEqual(historyBefore.snapshot_json);
    await independent.close();
  });

  test("ADMIN policy sections, tailoring/SoD, non-persisted preview, independent publication/archive and staleness", async ({
    page,
    browser,
  }) => {
    test.setTimeout(720_000);
    const token = await login(page, "admin");
    const headers = { Authorization: `Bearer ${token}` };
    const project = await fixtureProject(page, headers);
    const modelHistory = await json<{ items: GovernedRecord[] }>(
      await page.request.get(`${apiRoot}/projects/${project.id}/models`, { headers })
    );
    const historicalModel = modelHistory.items.find((row) => row.status === "APPROVED_FOR_ANALYSIS");
    expect(historicalModel).toBeTruthy();
    const frozenModel = await json<GovernedRecord>(
      await page.request.get(`${apiRoot}/models/${historicalModel!.id}`, { headers })
    );
    await page.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }).click();
    await page.goto("/app/admin/strategy/qra-methodology-source-readiness");
    const admin = page.getByRole("region", { name: "QRA Methodology & Source Readiness", exact: true });
    await expect(admin).toBeVisible();
    await expect(admin.getByRole("button", { name: "Approve for analysis", exact: true })).toHaveCount(0);
    const labels = [
      "General",
      "Analysis Types",
      "Cost Source Requirements",
      "Schedule Source Requirements",
      "Schedule Quality Rules",
      "Uncertainty Range Policies",
      "Distribution Families",
      "Distribution Rules",
      "Correlation Methods",
      "Correlation Rules",
      "Methodology Profiles",
      "Applicability",
      "FEL Stage Rules",
      "Gate Profile Rules",
      "Project Type Rules",
      "Governance Model Rules",
      "Risk / Complexity Rules",
      "Model Governance",
      "SoD",
      "Validity / Freshness",
      "Numbering",
      "Inheritance",
      "Review / Approval",
      "Preview",
      "History",
    ];
    const sectionNav = admin.getByRole("navigation", {
      name: "QRA Methodology & Source Readiness governed sections",
      exact: true,
    });
    for (const label of labels) await expect(sectionNav).toContainText(label);
    await admin.getByLabel("Workspace context for preview", { exact: true }).fill(String(project.id));
    const configuration = admin
      .locator("[data-configuration-id]")
      .filter({ has: page.getByRole("button", { name: "Clone to DRAFT", exact: true }) })
      .filter({ hasText: "QRA" })
      .first();
    const clone = (await mutation(
      page,
      `/api/v1/qra-foundation/admin/configurations/${await configuration.getAttribute("data-configuration-id")}/clone`,
      configuration.getByRole("button", { name: "Clone to DRAFT", exact: true }),
      201
    )) as Configuration;
    const draft = admin.locator(`[data-configuration-id="${clone.id}"]`);
    await draft.getByRole("button", { name: "Edit policy", exact: true }).click();
    const editor = admin.getByRole("region", { name: "Edit QRA Methodology & Source Readiness", exact: true });
    async function stage(label: string, value: unknown) {
      await editor
        .getByRole("navigation", { name: "Policy section editor", exact: true })
        .getByRole("button", { name: label, exact: true })
        .click();
      await editor
        .getByRole("textbox", { name: "Governed policy section JSON", exact: true })
        .fill(JSON.stringify(value));
    }
    const content = clone.content_json;
    await stage("Methodology Profiles", {
      ...(content.methodology as Json),
      name: "QRA independently governed browser methodology revision",
    });
    await stage("Analysis Types", ["COST_QRA", "SCHEDULE_QRA", "INTEGRATED_COST_SCHEDULE_QRA"]);
    await stage(
      "Cost Source Requirements",
      (content.cost_requirements as Json[]).map((item) => ({
        ...item,
        name: `${String(item.name || item.code)} — browser governed`,
      }))
    );
    await stage(
      "Schedule Source Requirements",
      (content.schedule_requirements as Json[]).map((item) => ({
        ...item,
        name: `${String(item.name || item.code)} — browser governed`,
      }))
    );
    await stage("Schedule Quality Rules", { ...(content.schedule_quality_rules as Json), maximum_negative_lags: 0 });
    await stage("Uncertainty Range Policies", content.range_policies);
    await stage("Distribution Families", content.distribution_families);
    await stage("Distribution Rules", content.distribution_families);
    await stage("Correlation Methods", content.correlation_methods);
    await stage("Correlation Rules", content.correlation_rules);
    await stage("FEL Stage Rules", ["FEL-3"]);
    await stage("Gate Profile Rules", ["PYP-FFA"]);
    await stage("Project Type Rules", ["MINING"]);
    await stage("Governance Model Rules", ["CAPITAL_OWNER"]);
    await stage("Model Governance", content.model_governance);
    await stage("SoD", content.separation_of_duties);
    await stage("Validity / Freshness", { ...(content.freshness as Json), maximum_source_age_days: 30 });
    await stage("Numbering", content.numbering);
    await stage("Inheritance", false);
    const excluded = await mutation(
      page,
      "/api/v1/qra-foundation/admin/preview",
      admin.getByRole("button", { name: "Preview persisted=false", exact: true })
    );
    expect(excluded.persisted).toBe(false);
    expect(excluded.applicable).toBe(false);
    expect(excluded.cost_requirements).toEqual([]);
    expect(excluded.schedule_requirements).toEqual([]);
    await stage("Inheritance", true);
    await stage("Review / Approval", content.model_governance);
    const preview = await mutation(
      page,
      "/api/v1/qra-foundation/admin/preview",
      admin.getByRole("button", { name: "Preview persisted=false", exact: true })
    );
    expect(preview.persisted).toBe(false);
    const saved = (await mutation(
      page,
      `/api/v1/qra-foundation/admin/configurations/${clone.id}`,
      editor.getByRole("button", { name: "Save DRAFT revision", exact: true })
    )) as Configuration;
    const selfPublish = await page.request.post(`${apiRoot}/admin/configurations/${clone.id}/publish`, {
      headers: { ...headers, "If-Match": String(saved.version), "Idempotency-Key": `qra-self-publish-${Date.now()}` },
      data: {},
    });
    expect([403, 409]).toContain(selfPublish.status());
    const independent = await browser.newContext({ baseURL: baseUrl });
    const reviewPage = await independent.newPage();
    const authorityToken = await login(reviewPage, authority);
    const authorityHeaders = { Authorization: `Bearer ${authorityToken}` };
    await reviewPage.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }).click();
    await reviewPage.goto("/app/admin/strategy/qra-methodology-source-readiness");
    const publisher = reviewPage.getByRole("region", { name: "QRA Methodology & Source Readiness", exact: true });
    const reviewed = publisher.locator(`[data-configuration-id="${clone.id}"]`);
    await mutation(
      reviewPage,
      `/api/v1/qra-foundation/admin/configurations/${clone.id}/publish`,
      reviewed.getByRole("button", { name: "Publish", exact: true })
    );
    const costCurrent = await json<Json>(
      await reviewPage.request.get(`${apiRoot}/projects/${project.id}/cost-readiness`, { headers: authorityHeaders })
    );
    const scheduleCurrent = await json<Json>(
      await reviewPage.request.get(`${apiRoot}/projects/${project.id}/schedule-readiness`, {
        headers: authorityHeaders,
      })
    );
    const modelCurrent = await json<Json>(
      await reviewPage.request.get(`${apiRoot}/projects/${project.id}/model-readiness`, { headers: authorityHeaders })
    );
    expect(JSON.stringify(costCurrent)).toContain("STALE");
    expect(JSON.stringify(scheduleCurrent)).toContain("STALE");
    expect(JSON.stringify(modelCurrent)).toContain("STALE");
    const unchanged = await json<GovernedRecord>(
      await reviewPage.request.get(`${apiRoot}/models/${frozenModel!.id}`, { headers: authorityHeaders })
    );
    expect(unchanged.hash).toBe(frozenModel!.hash);
    expect(unchanged.snapshot_json).toEqual(frozenModel!.snapshot_json);
    await reviewPage.getByRole("button", { name: "Cambiar a USER MODE", exact: true }).click();
    const staleWorkspace = await openWorkspace(reviewPage, project.id);
    await selectDomain(staleWorkspace, "model");
    await expect(
      staleWorkspace.getByRole("heading", { name: "Model definition readiness · STALE", exact: true })
    ).toBeVisible();
    await expect(staleWorkspace.getByRole("button", { name: "Approve for analysis", exact: true })).toHaveCount(0);
    await reviewPage.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }).click();
    await reviewPage.goto("/app/admin/strategy/qra-methodology-source-readiness");
    await expect(reviewed.getByRole("button", { name: "Archive", exact: true })).toBeEnabled();
    await mutation(
      reviewPage,
      `/api/v1/qra-foundation/admin/configurations/${clone.id}/archive`,
      reviewed.getByRole("button", { name: "Archive", exact: true })
    );
    await expect(reviewed).toContainText("archived");
    await reviewPage.getByRole("button", { name: "Cambiar a USER MODE", exact: true }).click();
    const refreshWorkspace = await openWorkspace(reviewPage, project.id);
    const frozenSources: Array<["cost" | "schedule" | "model", number]> = [
      ["cost", Number(frozenModel.cost_source_assessment_id)],
      ["schedule", Number(frozenModel.schedule_source_assessment_id)],
      ["model", frozenModel.id],
    ];
    for (const [kind, id] of frozenSources) {
      const collection = kind === "model" ? "models" : `${kind}-assessments`;
      const before = await json<GovernedRecord>(
        await reviewPage.request.get(`${apiRoot}/${collection}/${id}`, { headers: authorityHeaders })
      );
      await selectDomain(refreshWorkspace, kind);
      await selectRecord(refreshWorkspace, id);
      await refreshWorkspace.getByRole("button", { name: "Refresh Preview", exact: true }).click();
      await expect(
        refreshWorkspace.getByRole("article", { name: "QRA non-persisted preview", exact: true })
      ).toContainText("persisted=false");
      const successor = (await mutation(
        reviewPage,
        `/api/v1/qra-foundation/${collection}/${id}/refresh-apply`,
        refreshWorkspace.getByRole("button", { name: "Apply refresh as successor DRAFT", exact: true }),
        201
      )) as GovernedRecord;
      expect(successor.status).toBe("DRAFT");
      expect(successor.predecessor_id).toBe(id);
      expect(successor.version).toBe(before.version + 1);
      const historical = await json<GovernedRecord>(
        await reviewPage.request.get(`${apiRoot}/${collection}/${id}`, { headers: authorityHeaders })
      );
      expect(historical.hash).toBe(before.hash);
      expect(historical.snapshot_json).toEqual(before.snapshot_json);
    }
    await independent.close();
    const userContext = await browser.newContext({ baseURL: baseUrl });
    const userPage = await userContext.newPage();
    const userToken = await login(userPage, "qra.user@demo.local");
    const denied = await userPage.request.get(`${apiRoot}/admin/configurations`, {
      headers: { Authorization: `Bearer ${userToken}` },
    });
    expect(denied.status()).toBe(403);
    await expect(userPage.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true })).toBeDisabled();
    await userPage.goto("/app/admin/strategy/qra-methodology-source-readiness");
    await expect(userPage.getByRole("region", { name: "QRA Methodology & Source Readiness", exact: true })).toHaveCount(
      0
    );
    await userContext.close();
    const configContext = await browser.newContext({ baseURL: baseUrl });
    const configPage = await configContext.newPage();
    const configToken = await login(configPage, "qra.config@demo.local");
    const forbidden = await configPage.request.post(`${apiRoot}/models/1/approve`, {
      headers: {
        Authorization: `Bearer ${configToken}`,
        "If-Match": "1",
        "Idempotency-Key": `qra-config-live-${Date.now()}`,
      },
      data: {},
    });
    expect(forbidden.status()).toBe(403);
    await configContext.close();
  });
});
