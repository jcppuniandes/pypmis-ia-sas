import { expect, type APIResponse, type Page, test } from "@playwright/test";

const apiUrl = process.env.E2E_API_URL || "http://localhost:8000";
const fixturePayload = process.env.E2E_GATE07E_FIXTURE;

type WorkspaceRef = { id: number; name: string; code: string };
type ConfigurationRef = { id: number; name: string; code: string; revision: number; version: number; hash: string };
type Gate07JFixture = {
  index: number;
  projects: Record<"A" | "B" | "C", WorkspaceRef>;
  excluded_projects: Record<"CONTRACTOR" | "DIRECT" | "LEGACY", WorkspaceRef>;
  definition_configuration: ConfigurationRef;
  definition_reviewer: { id: number; email: string; password: string };
};
type FixtureBatch = { run_id: string; copies: Gate07JFixture[] };
type FELStatus = {
  id: number;
  current_stage_code: string;
  status: string;
  revision_version: number;
  effective_framework_hash: string;
  definition_source_hash: string;
};
type ElementResult = {
  element_key: string;
  category_key: string;
  name?: string;
  applicable: boolean;
  score: number;
  maturity_status: string;
  comment: string;
  evidence_refs: Array<Record<string, unknown>>;
  blocking: boolean;
  action_required: boolean;
};
type Assessment = {
  id: number;
  assessment_number: string;
  assessment_version: number;
  fel_stage_code: string;
  status: string;
  raw_score: number | null;
  normalized_score: number | null;
  maturity_level: string | null;
  threshold_status: string;
  element_results: ElementResult[];
  source_snapshot: { applicable_elements: Array<Record<string, unknown>> };
  assessment_hash: string | null;
  definition_source_hash: string;
  revision_version: number;
};
type DefinitionAction = { id: number; status: string; blocking: boolean; revision_version: number };
type Configuration = ConfigurationRef & {
  description: string;
  status: string;
  content_json: Record<string, unknown>;
  content_hash: string;
};

const batch = fixturePayload ? (JSON.parse(fixturePayload) as FixtureBatch) : null;

async function apiJson<T>(response: APIResponse, status = 200) {
  const body = await response.text();
  expect(response.status(), body).toBe(status);
  return JSON.parse(body) as T;
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

async function reviewerToken(page: Page, fixture: Gate07JFixture) {
  const response = await page.request.post(`${apiUrl}/api/v1/auth/login`, {
    data: { email: fixture.definition_reviewer.email, password: fixture.definition_reviewer.password },
  });
  return (await apiJson<{ access_token: string }>(response)).access_token;
}

async function expand(page: Page, name: RegExp) {
  const button = page.getByRole("button", { name });
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
}

async function openUserDefinition(page: Page) {
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^project definition \/ fel manager$/i);
  await page
    .getByRole("button", { name: /^project definition \/ fel manager$/i })
    .last()
    .click();
  await expect(page.getByRole("region", { name: "Project Definition / FEL Manager" })).toBeVisible();
}

async function openAdminDefinition(page: Page) {
  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  await expand(page, /^enterprise strategy manager$/i);
  await page.getByRole("button", { name: /^project definition \/ fel manager$/i }).click();
  await expect(page.getByRole("region", { name: "Project Definition / FEL Configuration" })).toBeVisible();
}

function headers(token: string, version?: number) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
    ...(version ? { "If-Match": `"${version}"` } : {}),
  };
}

function assessmentElements(assessment: Assessment, score: number, evidence = true): ElementResult[] {
  return assessment.source_snapshot.applicable_elements.map((item) => ({
    element_key: String(item.element_key),
    category_key: String(item.category_key),
    name: String(item.name || item.element_key),
    applicable: true,
    score,
    maturity_status: score >= 65 ? "READY" : "DEVELOPING",
    comment: "Controlled non-proprietary Gate 07J-FEL browser evidence.",
    evidence_refs: evidence ? [{ reference: `E2E-${String(item.element_key)}`, origin: "GOVERNED_SOURCE" }] : [],
    blocking: false,
    action_required: false,
  }));
}

test.describe("Gate 07J-FEL-H browser E2E release closeout", () => {
  test.setTimeout(300_000);
  test.skip(!batch, "Requires the disposable E2E_GATE07E_FIXTURE payload");

  test("USER and ADMIN lifecycles reach GATE07J_FEL_RELEASE_VALIDATED", async ({ page }, testInfo) => {
    const fixture = batch!.copies[testInfo.repeatEachIndex % batch!.copies.length];
    for (const localOrigin of ["http://localhost:8000", "http://127.0.0.1:8000"]) {
      await page.route(`${localOrigin}/**`, (route) =>
        route.continue({ url: route.request().url().replace(localOrigin, apiUrl) })
      );
    }

    const unexpectedResponses: Array<{ status: number; url: string }> = [];
    const consoleIssues: string[] = [];
    const pageErrors: string[] = [];
    page.on("response", (response) => {
      if (
        response.status() >= 400 &&
        /project-definition|definition-assessment|definition-action|fel-stage/.test(response.url())
      ) {
        unexpectedResponses.push({ status: response.status(), url: response.url() });
      }
    });
    page.on("console", (message) => {
      if (["error", "warning"].includes(message.type())) consoleIssues.push(`${message.type()}: ${message.text()}`);
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));

    const token = await login(page);
    const auth = headers(token);
    await openUserDefinition(page);
    const workspace = page.getByRole("region", { name: "Project Definition / FEL Manager" });
    const selector = workspace.getByLabel("Project Workspace");
    await selector.selectOption(String(fixture.projects.A.id));
    await expect(selector).toHaveValue(String(fixture.projects.A.id));
    await expect(workspace.getByText("FID = false")).toBeVisible();

    const startPromise = page.waitForResponse(
      (response) => response.url().endsWith(`/projects/${fixture.projects.A.id}/fel/start`) && response.ok()
    );
    await workspace.getByRole("button", { name: "Start FEL" }).click();
    const started = (await (await startPromise).json()) as FELStatus;
    expect(started).toEqual(expect.objectContaining({ current_stage_code: "FEL-1", status: "IN_STAGE" }));

    const assessmentPromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/projects/${fixture.projects.A.id}/definition-assessments`) &&
        response.request().method() === "POST" &&
        response.ok()
    );
    await workspace.getByRole("button", { name: "Start Assessment" }).click();
    const draft = (await (await assessmentPromise).json()) as Assessment;
    expect(draft.status).toBe("DRAFT");
    const scoreInputs = workspace.getByLabel(/^Score /);
    await expect(scoreInputs).toHaveCount(draft.source_snapshot.applicable_elements.length);
    for (let index = 0; index < (await scoreInputs.count()); index += 1) await scoreInputs.nth(index).fill("95");
    for (let index = 0; index < (await scoreInputs.count()); index += 1)
      await expect(scoreInputs.nth(index)).toHaveValue("95");

    const savePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/project-definition-assessments/${draft.id}`) &&
        response.request().method() === "PUT" &&
        response.ok()
    );
    await workspace.getByRole("button", { name: "Save Assessment" }).click();
    const saved = (await (await savePromise).json()) as Assessment;
    expect(saved.revision_version).toBe(draft.revision_version + 1);

    const actionPromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/projects/${fixture.projects.A.id}/definition-actions`) &&
        response.request().method() === "POST" &&
        response.ok()
    );
    await workspace.getByRole("button", { name: "Add Definition Action" }).click();
    const action = (await (await actionPromise).json()) as DefinitionAction;
    expect(action).toEqual(expect.objectContaining({ status: "OPEN", blocking: true }));

    const completePromise = page.waitForResponse(
      (response) => response.url().endsWith(`/project-definition-assessments/${draft.id}/complete`) && response.ok()
    );
    await workspace.getByRole("button", { name: "Complete Assessment" }).click();
    const completed = (await (await completePromise).json()) as Assessment;
    expect(completed.status).toBe("COMPLETED");
    expect(completed.normalized_score).toBe(95);
    expect(completed.threshold_status).toBe("EXCEEDS_REQUIRED");
    expect(completed.assessment_hash).toMatch(/^[a-f0-9]{64}$/);
    await expect(workspace.locator(".definitionReadiness h3")).toHaveText("BLOCKED");
    await expect(workspace.getByText("Open actions 1")).toBeVisible();

    await workspace.getByRole("button", { name: "Gaps & Actions" }).click();
    const resolvePromise = page.waitForResponse(
      (response) => response.url().endsWith(`/project-definition-actions/${action.id}`) && response.ok()
    );
    await workspace.getByRole("button", { name: "Resolve" }).click();
    expect(((await (await resolvePromise).json()) as DefinitionAction).status).toBe("RESOLVED");
    await expect(workspace.locator(".definitionReadiness h3")).toHaveText("READY");

    const evidenceResponse = await page.request.get(
      `${apiUrl}/api/v1/projects/${fixture.projects.A.id}/definition/investment-gate-evidence`,
      { headers: auth }
    );
    const evidence = await apiJson<Record<string, unknown>>(evidenceResponse);
    expect(evidence).toEqual(
      expect.objectContaining({
        source_module: "PROJECT_DEFINITION_FEL",
        evidence_origin: "GOVERNED_SOURCE",
        FEL_stage_code: "FEL-1",
        readiness_status: "READY",
        source_current: true,
        can_supply_investment_gate_evidence: true,
      })
    );
    expect(String(evidence.assessment_hash)).toMatch(/^[a-f0-9]{64}$/);
    expect(String(evidence.definition_readiness_hash)).toMatch(/^[a-f0-9]{64}$/);

    await workspace.getByRole("button", { name: "FEL Overview" }).click();
    const submitPromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/projects/${fixture.projects.A.id}/fel-stage/submit-review`) && response.ok()
    );
    await workspace.getByRole("button", { name: "Submit Stage Review" }).click();
    const submitted = (await (await submitPromise).json()) as FELStatus;
    expect(submitted.status).toBe("READY_FOR_STAGE_REVIEW");

    const sameActorReview = await page.request.post(
      `${apiUrl}/api/v1/projects/${fixture.projects.A.id}/fel-stage/complete`,
      {
        headers: headers(token, submitted.revision_version),
        data: { idempotency_key: `${batch!.run_id}-sod-negative-${fixture.index}`, note: "SOD negative" },
      }
    );
    expect(sameActorReview.status()).toBe(409);
    expect(JSON.stringify(await sameActorReview.json())).toContain("FEL_STAGE_REVIEW_SOD_VIOLATION");

    const reviewer = await reviewerToken(page, fixture);
    const validReview = await page.request.post(
      `${apiUrl}/api/v1/projects/${fixture.projects.A.id}/fel-stage/complete`,
      {
        headers: headers(reviewer, submitted.revision_version),
        data: { idempotency_key: `${batch!.run_id}-review-${fixture.index}`, note: "Independent FEL review" },
      }
    );
    const nextStage = await apiJson<FELStatus>(validReview);
    expect(nextStage).toEqual(expect.objectContaining({ current_stage_code: "FEL-2", status: "IN_STAGE" }));

    const staleRefresh = await page.request.post(
      `${apiUrl}/api/v1/projects/${fixture.projects.A.id}/definition/refresh`,
      {
        headers: headers(token, nextStage.revision_version),
        data: {
          expected_source_hash: "0".repeat(64),
          idempotency_key: `${batch!.run_id}-stale-source-${fixture.index}`,
        },
      }
    );
    expect(staleRefresh.status()).toBe(412);
    expect(JSON.stringify(await staleRefresh.json())).toContain("STALE_PROJECT_DEFINITION_SOURCE");

    await workspace.getByRole("button", { name: "Definition Assessments" }).click();
    const reevaluatePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/project-definition-assessments/${completed.id}/reevaluate`) && response.ok()
    );
    await workspace.getByRole("button", { name: "Start Reevaluation" }).click();
    const reevaluation = (await (await reevaluatePromise).json()) as Assessment;
    expect(reevaluation).toEqual(
      expect.objectContaining({ assessment_version: 2, fel_stage_code: "FEL-2", status: "DRAFT" })
    );
    await workspace.getByRole("button", { name: "History" }).click();
    await expect(workspace.getByText(completed.assessment_number)).toBeVisible();
    await workspace.getByRole("button", { name: "Maturity Trend" }).click();
    await expect(workspace.getByText(/FEL-1 .* PYP-E2E-/)).toBeVisible();

    const startB = await page.request.post(`${apiUrl}/api/v1/projects/${fixture.projects.B.id}/fel/start`, {
      headers: auth,
      data: {
        framework_configuration_id: fixture.definition_configuration.id,
        stage_code: "FEL-1",
        idempotency_key: `${batch!.run_id}-start-b-${fixture.index}`,
      },
    });
    await apiJson<FELStatus>(startB);
    const draftB = await apiJson<Assessment>(
      await page.request.post(`${apiUrl}/api/v1/projects/${fixture.projects.B.id}/definition-assessments`, {
        headers: auth,
        data: { idempotency_key: `${batch!.run_id}-assessment-b-${fixture.index}` },
      })
    );
    const missingEvidenceSaved = await apiJson<Assessment>(
      await page.request.put(`${apiUrl}/api/v1/project-definition-assessments/${draftB.id}`, {
        headers: headers(token, draftB.revision_version),
        data: { status: "IN_PROGRESS", element_results: assessmentElements(draftB, 95, false), evidence_refs: [] },
      })
    );
    const missingEvidence = await page.request.post(
      `${apiUrl}/api/v1/project-definition-assessments/${draftB.id}/complete`,
      {
        headers: headers(token, missingEvidenceSaved.revision_version),
        data: { idempotency_key: `${batch!.run_id}-missing-evidence-${fixture.index}` },
      }
    );
    expect(missingEvidence.status()).toBe(409);
    expect(JSON.stringify(await missingEvidence.json())).toContain("ASSESSMENT_INCOMPLETE");
    const lowSaved = await apiJson<Assessment>(
      await page.request.put(`${apiUrl}/api/v1/project-definition-assessments/${draftB.id}`, {
        headers: headers(token, missingEvidenceSaved.revision_version),
        data: { status: "IN_PROGRESS", element_results: assessmentElements(draftB, 10), evidence_refs: [] },
      })
    );
    const staleAssessment = await page.request.put(`${apiUrl}/api/v1/project-definition-assessments/${draftB.id}`, {
      headers: headers(token, missingEvidenceSaved.revision_version),
      data: { status: "IN_PROGRESS", element_results: assessmentElements(draftB, 20), evidence_refs: [] },
    });
    expect(staleAssessment.status()).toBe(412);
    expect(JSON.stringify(await staleAssessment.json())).toContain("ETAG_MISMATCH");
    const lowCompleted = await apiJson<Assessment>(
      await page.request.post(`${apiUrl}/api/v1/project-definition-assessments/${draftB.id}/complete`, {
        headers: headers(token, lowSaved.revision_version),
        data: { idempotency_key: `${batch!.run_id}-low-complete-${fixture.index}` },
      })
    );
    expect(lowCompleted.threshold_status).toBe("BELOW_REQUIRED");
    const belowReadiness = await apiJson<{ status: string; blockers: string[] }>(
      await page.request.get(`${apiUrl}/api/v1/projects/${fixture.projects.B.id}/definition-readiness`, {
        headers: auth,
      })
    );
    expect(belowReadiness).toEqual(
      expect.objectContaining({
        status: "BLOCKED",
        blockers: expect.arrayContaining(["MINIMUM_DEFINITION_MATURITY_NOT_MET"]),
      })
    );
    const completedEdit = await page.request.put(`${apiUrl}/api/v1/project-definition-assessments/${draftB.id}`, {
      headers: headers(token, lowCompleted.revision_version),
      data: { status: "IN_PROGRESS", element_results: assessmentElements(draftB, 95), evidence_refs: [] },
    });
    expect(completedEdit.status()).toBe(409);
    expect(JSON.stringify(await completedEdit.json())).toContain("COMPLETED_ASSESSMENT_IMMUTABLE");

    const stageSkip = await page.request.post(`${apiUrl}/api/v1/projects/${fixture.projects.C.id}/fel/start`, {
      headers: auth,
      data: {
        framework_configuration_id: fixture.definition_configuration.id,
        stage_code: "FEL-3",
        idempotency_key: `${batch!.run_id}-skip-${fixture.index}`,
      },
    });
    expect(stageSkip.status()).toBe(409);
    expect(JSON.stringify(await stageSkip.json())).toContain("FEL_STAGE_SKIP_REQUIRES_GOVERNED_BYPASS");
    for (const key of ["CONTRACTOR", "DIRECT"] as const) {
      const optional = await page.request.post(
        `${apiUrl}/api/v1/projects/${fixture.excluded_projects[key].id}/fel/start`,
        {
          headers: auth,
          data: {
            framework_configuration_id: fixture.definition_configuration.id,
            stage_code: "FEL-1",
            idempotency_key: `${batch!.run_id}-${key}-${fixture.index}`,
          },
        }
      );
      expect(optional.status()).toBe(409);
      const detail = JSON.stringify(await optional.json());
      expect(detail).toContain("PROJECT_DEFINITION_CAPABILITY_NOT_APPLICABLE");
      expect(detail).toContain('"contractor_delivery_required":false');
      expect(detail).toContain('"direct_internal_required":false');
    }

    const overviewBeforePreview = await apiJson<{ history: Assessment[] }>(
      await page.request.get(`${apiUrl}/api/v1/projects/${fixture.projects.A.id}/definition`, { headers: auth })
    );
    await openAdminDefinition(page);
    const admin = page.getByRole("region", { name: "Project Definition / FEL Configuration" });
    const publishedConfigurationButton = admin
      .locator(".definitionAdminGrid aside button")
      .filter({ hasText: fixture.definition_configuration.name })
      .filter({ hasText: `published · rev ${fixture.definition_configuration.revision}` });
    await expect(publishedConfigurationButton).toHaveCount(1);
    await publishedConfigurationButton.click();
    await expect(
      admin.getByRole("heading", { name: fixture.definition_configuration.name, exact: true })
    ).toBeVisible();
    await expect(admin.getByRole("button", { name: "Clone DRAFT" })).toBeEnabled();
    const clonePromise = page.waitForResponse(
      (response) =>
        response
          .url()
          .endsWith(`/project-definition/admin/configurations/${fixture.definition_configuration.id}/clone`) &&
        response.ok()
    );
    await admin.getByRole("button", { name: "Clone DRAFT" }).click();
    const clone = (await (await clonePromise).json()) as Configuration;
    expect(clone).toEqual(expect.objectContaining({ status: "draft", revision: 2, version: 1 }));
    await expect(admin.getByRole("status")).toHaveText(/configuration clone completed/i);
    await expect(admin.locator(".definitionSurface > header strong")).toHaveText("draft");

    const updatedContent = structuredClone(clone.content_json) as {
      thresholds: Record<string, number>;
      blocking_elements: string[];
      required_evidence: Array<Record<string, unknown>>;
      [key: string]: unknown;
    };
    updatedContent.thresholds["FEL-2"] = 70;
    updatedContent.blocking_elements = ["scope-basis-reference"];
    updatedContent.required_evidence = [
      {
        evidence_key: "scope-basis-reference",
        name: "Governed scope basis",
        stages: ["FEL-2"],
        required: true,
      },
    ];
    await admin.getByLabel("Project Definition Framework JSON").fill(JSON.stringify(updatedContent, null, 2));

    const previewPromise = page.waitForResponse((response) =>
      response.url().endsWith("/project-definition/admin/configurations/preview")
    );
    await admin.locator(".definitionActions").getByRole("button", { name: "Preview" }).click();
    const previewResponse = await previewPromise;
    expect(previewResponse.status()).toBe(200);
    const preview = (await previewResponse.json()) as Record<string, unknown>;
    expect(preview.persisted).toBe(false);
    expect(preview).toEqual(
      expect.objectContaining({
        PYP_INV_SELECT_readiness_preview: expect.objectContaining({ required_stage: "FEL-2", stage_available: true }),
        PYP_FFA_readiness_preview: expect.objectContaining({ funding_is_independent: true }),
      })
    );
    await expect(admin.getByText(/persisted=false/i)).toBeVisible();
    const overviewAfterPreview = await apiJson<{ history: Assessment[] }>(
      await page.request.get(`${apiUrl}/api/v1/projects/${fixture.projects.A.id}/definition`, { headers: auth })
    );
    expect(overviewAfterPreview.history.map((item) => item.id)).toEqual(
      overviewBeforePreview.history.map((item) => item.id)
    );

    const saveConfigurationPromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/project-definition/admin/configurations/${clone.id}`) &&
        response.request().method() === "PUT" &&
        response.ok()
    );
    await admin.getByRole("button", { name: "Save" }).click();
    const savedConfiguration = (await (await saveConfigurationPromise).json()) as Configuration;
    expect(savedConfiguration).toEqual(expect.objectContaining({ status: "draft", version: 2 }));
    expect(savedConfiguration.content_hash).not.toBe(fixture.definition_configuration.hash);
    await expect(admin.getByRole("status")).toHaveText(/configuration save completed/i);
    const staleConfiguration = await page.request.put(
      `${apiUrl}/api/v1/project-definition/admin/configurations/${clone.id}`,
      {
        headers: headers(token, clone.version),
        data: { name: clone.name, description: clone.description, content_json: updatedContent },
      }
    );
    expect(staleConfiguration.status()).toBe(412);
    expect(JSON.stringify(await staleConfiguration.json())).toContain("ETAG_MISMATCH");

    const publishPromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/project-definition/admin/configurations/${clone.id}/publish`) && response.ok()
    );
    await admin.locator(".definitionActions").getByRole("button", { name: "Publish", exact: true }).click();
    const published = (await (await publishPromise).json()) as Configuration;
    expect(published).toEqual(expect.objectContaining({ status: "published", revision: 2, version: 3 }));
    const immutablePublished = await page.request.put(
      `${apiUrl}/api/v1/project-definition/admin/configurations/${fixture.definition_configuration.id}`,
      {
        headers: headers(token, fixture.definition_configuration.version),
        data: { name: "Forbidden mutation", description: "", content_json: updatedContent },
      }
    );
    expect(immutablePublished.status()).toBe(409);
    expect(JSON.stringify(await immutablePublished.json())).toContain("PUBLISHED_CONFIGURATION_IMMUTABLE");
    const effective = await apiJson<Record<string, unknown>>(
      await page.request.post(`${apiUrl}/api/v1/project-definition/admin/configurations/preview`, {
        headers: auth,
        data: {
          project_workspace_id: fixture.projects.A.id,
          governance_model: "CAPITAL_OWNER",
          current_FEL_stage: "FEL-2",
        },
      })
    );
    expect(effective.persisted).toBe(false);
    expect(JSON.stringify(effective)).toContain(published.content_hash);

    for (const forbidden of [
      "Approve Investment",
      "Enter FID",
      "GO / HOLD / RECYCLE / KILL",
      "Create Funds",
      "Activate Project",
      "CPM",
      "P6",
    ]) {
      await expect(admin.getByText(forbidden, { exact: true })).toHaveCount(0);
    }
    await page.screenshot({ path: testInfo.outputPath(`gate07j-fel-h-run-${fixture.index}.png`), fullPage: true });

    expect(unexpectedResponses).toEqual([]);
    expect(consoleIssues).toEqual([]);
    expect(pageErrors).toEqual([]);
  });
});
