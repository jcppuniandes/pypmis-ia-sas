import { expect, type APIResponse, type Page, test } from "@playwright/test";

const apiUrl = process.env.E2E_API_URL || "http://localhost:8000";
const fixturePayload = process.env.E2E_GATE07E_FIXTURE;

type WorkspaceRef = { id: number; name: string; code: string };
type Gate07EFixture = {
  index: number;
  main_portfolio: WorkspaceRef;
  secondary_portfolio: WorkspaceRef;
  exclusion_portfolio: WorkspaceRef;
  no_matrix_portfolio: WorkspaceRef;
  projects: Record<"A" | "B" | "C", WorkspaceRef>;
  main_memberships: Record<string, { id: number; revision_version: number }>;
  secondary_membership: { id: number; revision_version: number };
  excluded_projects: Record<"CONTRACTOR" | "DIRECT" | "LEGACY", WorkspaceRef>;
  blocked_project: WorkspaceRef;
  no_matrix_project: WorkspaceRef;
  missing_membership_project: WorkspaceRef;
  main_configuration: {
    id: number;
    name: string;
    code: string;
    revision: number;
    version: number;
    hash: string;
  };
};

type FixtureBatch = { run_id: string; copies: Gate07EFixture[] };
type Evaluation = {
  id: number;
  evaluation_version: number;
  revision_version: number;
  status: string;
  normalized_score: string;
  strategic_alignment_score: string;
  risk_score: string;
  matrix_hash: string;
  source_snapshot_hash: string;
  matrix_snapshot: {
    criteria: Array<{ code: string; label: string; weight: number; evidence_required: boolean }>;
  };
  source_snapshot: Record<string, unknown>;
  allowed_actions: string[];
};

const batch = fixturePayload ? (JSON.parse(fixturePayload) as FixtureBatch) : null;

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("User").fill("admin");
  await page.getByLabel("Password").fill("1234");
  const loginResponse = page.waitForResponse(
    (response) => response.url().includes("/api/v1/auth/login") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /sign in/i }).click();
  const response = await loginResponse;
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { access_token: string };
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
  return body.access_token;
}

async function expand(page: Page, name: RegExp) {
  const button = page.getByRole("button", { name });
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
}

async function openUserEvaluation(page: Page) {
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^portfolio manager$/i);
  await page.getByRole("button", { name: /^portfolio evaluation$/i }).click();
  await expect(page.getByRole("heading", { name: "Portfolio Evaluation", exact: true })).toBeVisible();
}

async function openPrioritization(page: Page) {
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^portfolio manager$/i);
  await page.getByRole("button", { name: /^prioritization matrix$/i }).click();
  await expect(page.getByRole("heading", { name: "Prioritization Matrix", exact: true })).toBeVisible();
}

async function openAdminEvaluation(page: Page) {
  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  await expand(page, /^enterprise strategy manager$/i);
  await page.getByRole("button", { name: /^portfolio evaluation & prioritization$/i }).click();
  await expect(page.getByRole("heading", { name: "Portfolio Evaluation & Prioritization" })).toBeVisible();
}

async function choosePortfolio(page: Page, portfolio: WorkspaceRef) {
  const selector = page.getByLabel("Portfolio context");
  await selector.selectOption(String(portfolio.id));
  await expect(selector).toHaveValue(String(portfolio.id));
}

const ratingProfiles: Record<"A" | "B" | "C" | "SECONDARY", Record<string, number>> = {
  A: {
    "Strategic Alignment": 5,
    "Economic Value": 5,
    Benefits: 5,
    Risk: 5,
    Urgency: 5,
    "Organizational Capacity": 5,
    Dependencies: 5,
  },
  B: {
    "Strategic Alignment": 4,
    "Economic Value": 4,
    Benefits: 4,
    Risk: 4,
    Urgency: 4,
    "Organizational Capacity": 4,
    Dependencies: 4,
  },
  C: {
    "Strategic Alignment": 3,
    "Economic Value": 5,
    Benefits: 4,
    Risk: 4,
    Urgency: 4,
    "Organizational Capacity": 4,
    Dependencies: 5,
  },
  SECONDARY: {
    "Strategic Alignment": 3,
    "Economic Value": 3,
    Benefits: 3,
    Risk: 3,
    Urgency: 3,
    "Organizational Capacity": 3,
    Dependencies: 3,
  },
};

function expectedScore(profile: Record<string, number>) {
  const weights: Record<string, number> = {
    "Strategic Alignment": 25,
    "Economic Value": 20,
    Benefits: 15,
    Risk: 15,
    Urgency: 10,
    "Organizational Capacity": 10,
    Dependencies: 5,
  };
  return Object.entries(profile).reduce((total, [label, rating]) => total + ((rating - 1) / 4) * weights[label], 0);
}

async function fillEvaluation(page: Page, profile: Record<string, number>, evidencePrefix: string) {
  for (const [label, value] of Object.entries(profile)) {
    await page.getByLabel(`${label} rating`).fill(String(value));
    await page.getByLabel(`${label} evidence`).fill(`${evidencePrefix}-${label.replaceAll(" ", "-")}`);
    await page.getByLabel(`${label} comment`).fill(`Controlled ${label} browser evidence.`);
  }
  await page.getByLabel("Evaluation comments").fill(`${evidencePrefix} full browser evaluation.`);
}

async function completeFromCard(
  page: Page,
  project: WorkspaceRef,
  profile: Record<string, number>,
  evidencePrefix: string
) {
  const card = page.getByTestId(`portfolio-evaluation-project-${project.id}`);
  await expect(card).toBeVisible();
  const startResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes(`/projects/${project.id}/evaluations`) && response.request().method() === "POST"
  );
  await card.getByRole("button", { name: /^start$/i }).click();
  const startResponse = await startResponsePromise;
  expect(startResponse.status()).toBe(201);
  const started = (await startResponse.json()) as Evaluation;
  expect(started.allowed_actions).toEqual(expect.arrayContaining(["edit", "complete"]));
  await fillEvaluation(page, profile, evidencePrefix);

  const saveResponsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/portfolio-evaluations/${started.id}`) && response.request().method() === "PUT"
  );
  await page.getByRole("button", { name: /^save draft$/i }).click();
  const saveResponse = await saveResponsePromise;
  expect(saveResponse.ok()).toBeTruthy();
  expect(((await saveResponse.json()) as Evaluation).status).toBe("IN_PROGRESS");
  await expect(page.getByText("Evaluation draft saved with a new ETag.")).toBeVisible();

  const completeResponsePromise = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/portfolio-evaluations/${started.id}/complete`) && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /^complete$/i }).click();
  const completeResponse = await completeResponsePromise;
  expect(completeResponse.ok()).toBeTruthy();
  const completed = (await completeResponse.json()) as Evaluation;
  expect(completed.status).toBe("COMPLETED");
  expect(Number(completed.normalized_score)).toBe(expectedScore(profile));
  expect(completed.matrix_hash).toMatch(/^[a-f0-9]{64}$/);
  expect(completed.source_snapshot_hash).toMatch(/^[a-f0-9]{64}$/);
  expect(completed.allowed_actions).not.toEqual(expect.arrayContaining(["edit", "complete"]));
  await expect(page.getByLabel("Strategic Alignment rating")).toBeDisabled();
  await expect(page.getByText("Evaluation completed and frozen as an immutable snapshot.")).toBeVisible();
  return completed;
}

async function apiJson<T>(response: APIResponse, status = 200) {
  expect(response.status()).toBe(status);
  return (await response.json()) as T;
}

test.describe("Gate 07E-H full browser release closeout", () => {
  test.setTimeout(300_000);
  test.skip(!batch, "Requires the disposable E2E_GATE07E_FIXTURE payload");

  test("USER and ADMIN flows reach FLOW_PASS with protected context", async ({ page }, testInfo) => {
    const fixture = batch!.copies[testInfo.repeatEachIndex % batch!.copies.length];
    for (const localApiOrigin of ["http://localhost:8000", "http://127.0.0.1:8000"]) {
      await page.route(`${localApiOrigin}/**`, async (route) => {
        await route.continue({ url: route.request().url().replace(localApiOrigin, apiUrl) });
      });
    }
    const failedResponses: Array<{ status: number; url: string }> = [];
    const gateConsole: string[] = [];
    const pageErrors: string[] = [];
    page.on("response", (response) => {
      if (response.url().includes("portfolio-evaluation") && response.status() >= 400) {
        failedResponses.push({ status: response.status(), url: response.url() });
      }
    });
    page.on("console", (message) => {
      if (
        ["error", "warning"].includes(message.type()) &&
        /gate\s*07e|portfolio.?evaluation|prioritization/i.test(message.text())
      ) {
        gateConsole.push(`${message.type()}: ${message.text()}`);
      }
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));

    const token = await login(page);
    const authHeaders = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
    await openUserEvaluation(page);
    await choosePortfolio(page, fixture.main_portfolio);

    const completed: Record<string, Evaluation> = {};
    for (const projectKey of ["A", "B", "C"] as const) {
      completed[projectKey] = await completeFromCard(
        page,
        fixture.projects[projectKey],
        ratingProfiles[projectKey],
        `${batch!.run_id}-R${fixture.index}-${projectKey}`
      );
    }
    expect(Number(completed.A.normalized_score)).toBeGreaterThan(Number(completed.B.normalized_score));
    expect(completed.B.normalized_score).toBe(completed.C.normalized_score);
    expect(Number(completed.B.strategic_alignment_score)).toBeGreaterThan(
      Number(completed.C.strategic_alignment_score)
    );

    await openPrioritization(page);
    await choosePortfolio(page, fixture.main_portfolio);
    const rows = (["A", "B", "C"] as const).map((key) =>
      page.getByTestId(`portfolio-prioritization-row-${fixture.projects[key].id}`)
    );
    for (let index = 0; index < rows.length; index += 1) {
      await expect(rows[index]).toBeVisible();
      await expect(rows[index]).toContainText(String(index + 1));
      await expect(rows[index]).toContainText(fixture.projects[["A", "B", "C"][index] as "A" | "B" | "C"].name);
      await expect(rows[index]).toContainText("COMPLETED");
      await expect(rows[index]).toContainText("Growth");
      await expect(rows[index]).toContainText("2500000");
    }
    await expect(page.getByText("READY_FOR_PORTFOLIO_ANALYSIS", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Métricas de Prioritization Matrix").getByText(/^100(?:\.00)?%$/)).toBeVisible();

    await openUserEvaluation(page);
    await choosePortfolio(page, fixture.main_portfolio);
    const projectACard = page.getByTestId(`portfolio-evaluation-project-${fixture.projects.A.id}`);
    const reevalResponsePromise = page.waitForResponse((response) =>
      response.url().endsWith(`/portfolio-evaluations/${completed.A.id}/reevaluate`)
    );
    await projectACard.getByRole("button", { name: /^reevaluate$/i }).click();
    const replacement = (await (await reevalResponsePromise).json()) as Evaluation;
    expect(replacement.evaluation_version).toBe(2);
    expect(replacement.status).toBe("DRAFT");
    const historicalResponse = await page.request.get(`${apiUrl}/api/v1/portfolio-evaluations/${completed.A.id}`, {
      headers: authHeaders,
    });
    const historical = await apiJson<Evaluation>(historicalResponse);
    expect(historical.status).toBe("SUPERSEDED");
    expect(historical.matrix_hash).toBe(completed.A.matrix_hash);
    expect(historical.source_snapshot_hash).toBe(completed.A.source_snapshot_hash);
    await fillEvaluation(page, ratingProfiles.A, `${batch!.run_id}-R${fixture.index}-A-V2`);
    const reevalCompletePromise = page.waitForResponse((response) =>
      response.url().endsWith(`/portfolio-evaluations/${replacement.id}/complete`)
    );
    await page.getByRole("button", { name: /^complete$/i }).click();
    const replacementCompleted = (await (await reevalCompletePromise).json()) as Evaluation;
    expect(replacementCompleted.status).toBe("COMPLETED");
    expect(replacementCompleted.evaluation_version).toBe(2);

    const secondaryStart = await page.request.post(
      `${apiUrl}/api/v1/portfolios/${fixture.secondary_portfolio.id}/projects/${fixture.projects.A.id}/evaluations`,
      {
        headers: authHeaders,
        data: { idempotency_key: `${batch!.run_id}-secondary-start-${fixture.index}` },
      }
    );
    const secondaryDraft = await apiJson<Evaluation>(secondaryStart, 201);
    const missingCriteria = await page.request.post(
      `${apiUrl}/api/v1/portfolio-evaluations/${secondaryDraft.id}/complete`,
      {
        headers: { ...authHeaders, "If-Match": `"${secondaryDraft.revision_version}"` },
        data: { idempotency_key: `${batch!.run_id}-missing-criteria-${fixture.index}` },
      }
    );
    expect(missingCriteria.status()).toBe(422);
    const invalidRatings = [
      {
        criterion_code: "strategic_alignment",
        rating: 6,
        evidence: "OUT-OF-RANGE",
        comment: "Controlled negative test",
      },
    ];
    const outOfRange = await page.request.put(`${apiUrl}/api/v1/portfolio-evaluations/${secondaryDraft.id}`, {
      headers: { ...authHeaders, "If-Match": `"${secondaryDraft.revision_version}"` },
      data: { ratings: invalidRatings, comments: "Controlled negative test" },
    });
    expect(outOfRange.status()).toBe(422);
    invalidRatings[0].rating = 3;
    invalidRatings[0].evidence = "";
    const missingEvidence = await page.request.put(`${apiUrl}/api/v1/portfolio-evaluations/${secondaryDraft.id}`, {
      headers: { ...authHeaders, "If-Match": `"${secondaryDraft.revision_version}"` },
      data: { ratings: invalidRatings, comments: "Controlled negative test" },
    });
    expect(missingEvidence.status()).toBe(422);

    await openUserEvaluation(page);
    await choosePortfolio(page, fixture.secondary_portfolio);
    await page.getByRole("button", { name: /^refresh$/i }).click();
    const secondaryCard = page.getByTestId(`portfolio-evaluation-project-${fixture.projects.A.id}`);
    await secondaryCard.getByRole("button", { name: /^open v1$/i }).click();
    await fillEvaluation(page, ratingProfiles.SECONDARY, `${batch!.run_id}-R${fixture.index}-SECONDARY`);
    const secondarySavePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/portfolio-evaluations/${secondaryDraft.id}`) && response.request().method() === "PUT"
    );
    await page.getByRole("button", { name: /^save draft$/i }).click();
    const secondarySaved = (await (await secondarySavePromise).json()) as Evaluation;
    const staleEvaluation = await page.request.put(`${apiUrl}/api/v1/portfolio-evaluations/${secondaryDraft.id}`, {
      headers: { ...authHeaders, "If-Match": `"${secondaryDraft.revision_version}"` },
      data: {
        ratings: secondarySaved.matrix_snapshot.criteria.map((criterion) => ({
          criterion_code: criterion.code,
          rating: 3,
          evidence: `STALE-${criterion.code}`,
          comment: "Stale logical session",
        })),
        comments: "Stale logical session",
      },
    });
    expect(staleEvaluation.status()).toBe(412);
    const secondaryCompletePromise = page.waitForResponse((response) =>
      response.url().endsWith(`/portfolio-evaluations/${secondaryDraft.id}/complete`)
    );
    await page.getByRole("button", { name: /^complete$/i }).click();
    const secondaryCompleted = (await (await secondaryCompletePromise).json()) as Evaluation;
    expect(secondaryCompleted.normalized_score).not.toBe(replacementCompleted.normalized_score);

    await openPrioritization(page);
    await choosePortfolio(page, fixture.secondary_portfolio);
    await expect(page.getByTestId(`portfolio-prioritization-row-${fixture.projects.A.id}`)).toContainText(
      secondaryCompleted.normalized_score
    );
    const removeMembership = await page.request.post(
      `${apiUrl}/api/v1/projects/${fixture.projects.A.id}/portfolio-memberships/${fixture.secondary_membership.id}/remove`,
      {
        headers: { ...authHeaders, "If-Match": `"${fixture.secondary_membership.revision_version}"` },
      }
    );
    expect(removeMembership.ok()).toBeTruthy();
    await page.getByRole("button", { name: /^refresh$/i }).click();
    await expect(page.getByTestId(`portfolio-prioritization-row-${fixture.projects.A.id}`)).toHaveCount(0);
    const preservedSecondary = await page.request.get(
      `${apiUrl}/api/v1/portfolio-evaluations/${secondaryCompleted.id}`,
      { headers: authHeaders }
    );
    expect((await apiJson<Evaluation>(preservedSecondary)).status).toBe("COMPLETED");

    await openUserEvaluation(page);
    await choosePortfolio(page, fixture.exclusion_portfolio);
    for (const [key, blocker] of [
      ["CONTRACTOR", "GOVERNANCE_MODEL_CONTRACTOR_DELIVERY_NOT_APPLICABLE"],
      ["DIRECT", "GOVERNANCE_MODEL_DIRECT_INTERNAL_NOT_APPLICABLE"],
      ["LEGACY", "GOVERNANCE_MODEL_LEGACY_NOT_APPLICABLE"],
    ] as const) {
      const project = fixture.excluded_projects[key];
      const card = page.getByTestId(`portfolio-evaluation-project-${project.id}`);
      await expect(card).toContainText(blocker);
      await expect(card.getByRole("button", { name: /^start$/i })).toHaveCount(0);
      const blockedStart = await page.request.post(
        `${apiUrl}/api/v1/portfolios/${fixture.exclusion_portfolio.id}/projects/${project.id}/evaluations`,
        { headers: authHeaders, data: { idempotency_key: `${batch!.run_id}-${key}-${fixture.index}` } }
      );
      expect(blockedStart.status()).toBe(422);
      expect(JSON.stringify(await blockedStart.json())).toContain(blocker);
    }
    const blockedPlanningStart = await page.request.post(
      `${apiUrl}/api/v1/portfolios/${fixture.exclusion_portfolio.id}/projects/${fixture.blocked_project.id}/evaluations`,
      { headers: authHeaders, data: { idempotency_key: `${batch!.run_id}-blocked-${fixture.index}` } }
    );
    expect(blockedPlanningStart.status()).toBe(422);
    expect(JSON.stringify(await blockedPlanningStart.json())).toContain("READY_FOR_PORTFOLIO_PLANNING_REQUIRED");
    const noMatrixStart = await page.request.post(
      `${apiUrl}/api/v1/portfolios/${fixture.no_matrix_portfolio.id}/projects/${fixture.no_matrix_project.id}/evaluations`,
      { headers: authHeaders, data: { idempotency_key: `${batch!.run_id}-no-matrix-${fixture.index}` } }
    );
    expect(noMatrixStart.status()).toBe(422);
    expect(JSON.stringify(await noMatrixStart.json())).toContain("PUBLISHED_EVALUATION_MATRIX_REQUIRED");
    const missingMembershipStart = await page.request.post(
      `${apiUrl}/api/v1/portfolios/${fixture.main_portfolio.id}/projects/${fixture.missing_membership_project.id}/evaluations`,
      { headers: authHeaders, data: { idempotency_key: `${batch!.run_id}-no-membership-${fixture.index}` } }
    );
    expect(missingMembershipStart.status()).toBe(422);
    expect(JSON.stringify(await missingMembershipStart.json())).toContain("ACTIVE_PORTFOLIO_MEMBERSHIP_REQUIRED");

    const evaluationIdsBeforePreview = await page.request.get(
      `${apiUrl}/api/v1/portfolios/${fixture.main_portfolio.id}/evaluations?queue=ALL_AUTHORIZED`,
      { headers: authHeaders }
    );
    const beforePreview = await apiJson<Array<{ latest_evaluation: Evaluation | null }>>(evaluationIdsBeforePreview);
    await openAdminEvaluation(page);
    const adminWorkspace = page.getByRole("region", {
      name: "Portfolio Evaluation and Prioritization Configuration",
    });
    const configurationActions = page.getByLabel("Portfolio Evaluation configuration actions");
    await page.getByTestId(`portfolio-evaluation-configuration-${fixture.main_configuration.id}`).click();
    await expect(
      adminWorkspace.getByRole("heading", { name: fixture.main_configuration.name, exact: true })
    ).toBeVisible();
    const cloneButton = configurationActions.getByRole("button", { name: /^clone$/i });
    await expect(cloneButton).toBeEnabled();
    const cloneResponsePromise = page.waitForResponse((response) =>
      response.url().endsWith(`/configurations/${fixture.main_configuration.id}/clone`)
    );
    await cloneButton.click();
    const clone = (await (await cloneResponsePromise).json()) as {
      id: number;
      name: string;
      description: string;
      status: string;
      revision: number;
      version: number;
      content_json: Record<string, unknown>;
      content_hash: string;
    };
    expect(clone.status).toBe("draft");
    expect(clone.revision).toBe(fixture.main_configuration.revision + 1);
    await expect(page.getByTestId(`portfolio-evaluation-configuration-${clone.id}`)).toHaveClass(/active/);

    const updatedContent = structuredClone(clone.content_json) as {
      criteria: Array<{ code: string; weight: number }>;
      [key: string]: unknown;
    };
    updatedContent.criteria.find((item) => item.code === "strategic_alignment")!.weight = 24;
    updatedContent.criteria.find((item) => item.code === "economic")!.weight = 21;
    await page.getByLabel("Portfolio Evaluation configuration JSON").fill(JSON.stringify(updatedContent, null, 2));
    const previewResponsePromise = page.waitForResponse((response) =>
      response.url().endsWith("/portfolio-evaluation/admin/configurations/preview")
    );
    await configurationActions.getByRole("button", { name: /^preview$/i }).click();
    const draftPreview = (await (await previewResponsePromise).json()) as {
      publishable: boolean;
      effective: typeof updatedContent;
      source: { id: number; preview: boolean; hash: string };
    };
    expect(draftPreview.publishable).toBeTruthy();
    expect(draftPreview.source).toEqual(expect.objectContaining({ id: clone.id, preview: true }));
    expect(draftPreview.effective.criteria[0].weight).toBe(24);

    const saveResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/portfolio-evaluation/admin/configurations/${clone.id}`) &&
        response.request().method() === "PUT"
    );
    await configurationActions.getByRole("button", { name: /^save$/i }).click();
    const saved = (await (await saveResponsePromise).json()) as typeof clone;
    expect(saved.version).toBe(clone.version + 1);
    expect(saved.content_hash).not.toBe(fixture.main_configuration.hash);
    const staleAdminUpdate = await page.request.put(
      `${apiUrl}/api/v1/portfolio-evaluation/admin/configurations/${clone.id}`,
      {
        headers: { ...authHeaders, "If-Match": `"${clone.version}"` },
        data: { name: clone.name, description: clone.description, content_json: updatedContent },
      }
    );
    expect(staleAdminUpdate.status()).toBe(412);
    expect(JSON.stringify(await staleAdminUpdate.json())).toContain("ETAG_MISMATCH");

    const publishResponsePromise = page.waitForResponse((response) =>
      response.url().endsWith(`/portfolio-evaluation/admin/configurations/${clone.id}/publish`)
    );
    await configurationActions.getByRole("button", { name: /^publish$/i }).click();
    const published = (await (await publishResponsePromise).json()) as typeof clone;
    expect(published.status).toBe("published");
    expect(published.revision).toBe(clone.revision);
    const effectiveResponse = await page.request.post(
      `${apiUrl}/api/v1/portfolio-evaluation/admin/configurations/preview`,
      { headers: authHeaders, data: { workspace_id: fixture.main_portfolio.id } }
    );
    const effective = await apiJson<{
      source: { id: number; revision: number; hash: string };
      path: Array<{ id: number }>;
      effective: typeof updatedContent;
    }>(effectiveResponse);
    expect(effective.source).toEqual(
      expect.objectContaining({ id: published.id, revision: published.revision, hash: published.content_hash })
    );
    expect(effective.path.map((item) => item.id)).toContain(fixture.main_portfolio.id);
    expect(effective.effective.criteria[0].weight).toBe(24);
    const configurationsResponse = await page.request.get(
      `${apiUrl}/api/v1/portfolio-evaluation/admin/configurations`,
      { headers: authHeaders }
    );
    const configurations =
      await apiJson<Array<{ id: number; content_hash: string; status: string }>>(configurationsResponse);
    expect(configurations.find((item) => item.id === fixture.main_configuration.id)).toEqual(
      expect.objectContaining({ content_hash: fixture.main_configuration.hash, status: "published" })
    );
    const afterPreviewResponse = await page.request.get(
      `${apiUrl}/api/v1/portfolios/${fixture.main_portfolio.id}/evaluations?queue=ALL_AUTHORIZED`,
      { headers: authHeaders }
    );
    const afterPreview = await apiJson<Array<{ latest_evaluation: Evaluation | null }>>(afterPreviewResponse);
    expect(afterPreview.map((item) => item.latest_evaluation?.id)).toEqual(
      beforePreview.map((item) => item.latest_evaluation?.id)
    );

    for (const forbidden of [
      "FID approval",
      "Budget selection",
      "Resource selection",
      "PDRI score",
      "FEL score",
      "Project Activation",
      "manual global rank",
    ]) {
      await expect(adminWorkspace.getByText(forbidden, { exact: false })).toHaveCount(0);
    }
    await page.screenshot({ path: testInfo.outputPath(`gate07e-h-run-${fixture.index}.png`), fullPage: true });

    expect(failedResponses).toEqual([]);
    expect(gateConsole).toEqual([]);
    expect(pageErrors).toEqual([]);
  });
});
