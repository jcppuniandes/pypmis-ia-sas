import { expect, type APIResponse, type Locator, type Page, test } from "@playwright/test";

// Real Chromium + real API + disposable PostgreSQL. No intercepted/mocked responses.
const apiUrl = process.env.E2E_API_URL || "http://127.0.0.1:8815";
const baseUrl = process.env.E2E_BASE_URL || "http://127.0.0.1:5518";
const preparer = process.env.E2E_WAVE3B_PREPARER_EMAIL || "admin";
const authority = process.env.E2E_WAVE3B_AUTHORITY_EMAIL || "wave3b.authority@demo.local";
const userOnly = process.env.E2E_WAVE3B_USER_EMAIL || "wave3b.user@demo.local";
const password = process.env.E2E_WAVE3B_PASSWORD || "1234";
type Assessment = {
  id: number;
  status: string;
  assessment_number: string;
  assessment_hash: string;
  revision_version: number;
  snapshot_json: Record<string, unknown>;
};
type Configuration = {
  id: number;
  name: string;
  status: string;
  version: number;
  content_json: Record<string, unknown>;
};

async function json<T>(response: APIResponse, expected = 200): Promise<T> {
  expect(response.status(), await response.text()).toBe(expected);
  return (await response.json()) as T;
}
async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("User").fill(email);
  await page.getByLabel("Password").fill(password);
  const waiting = page.waitForResponse(
    (response) => response.url().includes("/api/v1/auth/login") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /sign in/i }).click();
  const result = await json<{ access_token: string }>(await waiting);
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
  return result.access_token;
}
async function expand(page: Page, name: string, navigation = "Control Flow") {
  const button = page.getByRole("navigation", { name: navigation }).getByRole("button", { name, exact: true }).first();
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
}
async function openOwner(page: Page) {
  await expand(page, "Enterprise Strategy Manager");
  await expand(page, "Business Case & Investment Development");
  await page
    .getByRole("navigation", { name: "Control Flow" })
    .getByRole("button", { name: "Owner Capability Readiness", exact: true })
    .click();
  await expect(page).toHaveURL(/\/app\/strategy\/owner-capability-readiness$/);
  return page.getByRole("region", { name: "Owner Capability Readiness workspace", exact: true });
}
async function mutation(page: Page, path: string, button: Locator, expected = 200) {
  const waiting = page.waitForResponse(
    (response) => response.url().endsWith(path) && response.request().method() !== "GET",
    { timeout: 120_000 }
  );
  await button.click();
  return await json<Record<string, unknown>>(await waiting, expected);
}

test.use({ trace: "on" });
test.describe("Wave 3B real governed Owner Capability Readiness", () => {
  test("USER assesses maturity, evidence, gaps and mitigation, independent review and immutable history", async ({
    page,
    browser,
  }) => {
    test.setTimeout(720_000);
    const token = await login(page, preparer);
    const headers = { Authorization: `Bearer ${token}` };
    const options = await json<{ projects: Array<{ id: number; name: string; code: string }> }>(
      await page.request.get(`${apiUrl}/api/v1/owner-capability/options`, { headers })
    );
    const project = options.projects.find((item) => /wave.?3b/i.test(item.name + item.code));
    expect(project, "Provision dedicated Wave 3B Project Workspace").toBeTruthy();
    const workspace = await openOwner(page);
    await workspace.getByRole("combobox", { name: "Project Workspace", exact: true }).selectOption(String(project!.id));
    await expect(workspace.getByRole("button", { name: /Clone to DRAFT|Publish/ })).toHaveCount(0);
    const requirements = await json<{ requirements: Array<{ requirement_code: string; name: string }> }>(
      await page.request.get(`${apiUrl}/api/v1/owner-capability/projects/${project!.id}/requirements`, { headers })
    );
    expect(requirements.requirements.length).toBeGreaterThan(0);
    await workspace.getByRole("button", { name: "Requirements", exact: true }).click();
    const created = (await mutation(
      page,
      `/api/v1/owner-capability/projects/${project!.id}/assessments`,
      workspace.getByRole("button", { name: "Create capability assessment", exact: true }),
      201
    )) as unknown as Assessment;
    expect(created.assessment_number).toMatch(/^OCA-/);
    const draftProvider = await json<{ status: string; source_current: boolean }>(
      await page.request.get(`${apiUrl}/api/v1/owner-capability/projects/${project!.id}/provider-evidence`, { headers })
    );
    expect(draftProvider.status).toBe("NOT_AVAILABLE");
    expect(draftProvider.source_current).toBe(false);
    const sourceContexts = await json<{
      commercial: { status: string; hash: string };
      resources: { scenarios: Array<{ status: string }> };
      basic_data: { status: string };
      fel_pdri: { fel_stage: string };
    }>(await page.request.get(`${apiUrl}/api/v1/owner-capability/projects/${project!.id}/contexts`, { headers }));
    expect(sourceContexts.commercial.status).toBe("COMPLETED");
    expect(sourceContexts.commercial.hash).toBeTruthy();
    expect(sourceContexts.resources.scenarios[0].status).toBe("DRAFT");
    expect(sourceContexts.basic_data.status).toBe("READY");
    expect(sourceContexts.fel_pdri.fel_stage).toBe("FEL-3");
    await workspace.getByRole("button", { name: "Capability Assessment", exact: true }).click();
    for (const requirement of requirements.requirements) {
      await workspace.getByRole("button", { name: "Add capability item", exact: true }).click();
      const editor = workspace.getByRole("article", { name: "Owner Capability item editor", exact: true });
      await editor
        .getByRole("combobox", { name: "Requirement", exact: true })
        .selectOption(requirement.requirement_code);
      for (const field of ["Current maturity", "Evidence quality"]) {
        const select = editor.getByRole("combobox", { name: field, exact: true });
        const values = await select
          .locator("option")
          .evaluateAll((items) => items.map((item) => (item as HTMLOptionElement).value));
        expect(values.length, `Configured ${field} values`).toBeGreaterThan(0);
        await select.selectOption(values.at(-1)!);
      }
      await editor.getByRole("combobox", { name: "Confidence", exact: true }).selectOption("HIGH");
      await editor
        .getByLabel("Rationale", { exact: true })
        .fill("Owner governance mechanism independently evidenced; capability is not a staffing total.");
      await editor.getByLabel("Responsible function", { exact: true }).fill("Owner investment governance");
      await editor
        .getByLabel("Evidence reference", { exact: true })
        .fill(`CHARTER-W3B-${requirement.requirement_code}`);
      await editor.getByLabel("Evidence version", { exact: true }).fill("1");
      await editor.getByLabel("Evidence hash", { exact: true }).fill("a".repeat(64));
      await editor.getByLabel("Source date", { exact: true }).fill(new Date().toISOString().slice(0, 10));
      await mutation(
        page,
        `/api/v1/owner-capability/assessments/${created.id}`,
        editor.getByRole("button", { name: "Save capability item", exact: true })
      );
      await expect(workspace).toContainText(`CHARTER-W3B-${requirement.requirement_code}`);
    }
    await workspace.getByRole("button", { name: "Gaps", exact: true }).click();
    await workspace.getByRole("button", { name: "Add capability gap", exact: true }).click();
    const gapEditor = workspace.getByRole("article", { name: "Owner Capability gap editor", exact: true });
    await gapEditor.getByLabel("Gap", { exact: true }).fill("Owner assurance evidence requires documented closure");
    await gapEditor.getByRole("combobox", { name: "Severity", exact: true }).selectOption("CRITICAL");
    await gapEditor.getByLabel("Blocking gap", { exact: true }).check();
    await gapEditor.getByLabel("Action owner", { exact: true }).fill("Assurance function");
    await mutation(
      page,
      `/api/v1/owner-capability/assessments/${created.id}`,
      gapEditor.getByRole("button", { name: "Save capability gap", exact: true })
    );
    await workspace.getByRole("button", { name: "Preview assessment", exact: true }).click();
    const preview = workspace.getByRole("article", { name: "Owner Capability assessment preview", exact: true });
    await expect(preview).toContainText("persisted=false");
    await expect(preview).toContainText("BLOCKED");
    await workspace
      .getByRole("button", { name: `Edit ${requirements.requirements[0].requirement_code}`, exact: true })
      .click();
    await gapEditor.getByRole("combobox", { name: "Status", exact: true }).selectOption("CLOSED");
    await gapEditor.getByLabel("Closure evidence", { exact: true }).fill("OWNER-ASSURANCE-CLOSURE-W3B");
    await mutation(
      page,
      `/api/v1/owner-capability/assessments/${created.id}`,
      gapEditor.getByRole("button", { name: "Save capability gap", exact: true })
    );
    await workspace.getByRole("button", { name: "Mitigation Plan", exact: true }).click();
    await workspace.getByRole("button", { name: "Add mitigation", exact: true }).click();
    const mitigation = workspace.getByRole("article", { name: "Owner Capability mitigation editor", exact: true });
    await mitigation
      .getByLabel("Action", { exact: true })
      .fill("Retain independent specialist support for governance continuity");
    await mitigation.getByLabel("Approach", { exact: true }).fill("EXTERNAL_SPECIALIST");
    await mitigation.getByLabel("Action owner", { exact: true }).fill("Owner commercial governance");
    await mitigation.getByLabel("Evidence reference", { exact: true }).fill("SPECIALIST-ARRANGEMENT-W3B");
    await mutation(
      page,
      `/api/v1/owner-capability/assessments/${created.id}/mitigations`,
      mitigation.getByRole("button", { name: "Save mitigation", exact: true }),
      201
    );
    await expect(workspace).toContainText("PROPOSED");
    for (const view of [
      "Dimension Summary",
      "Evidence",
      "Resource Context",
      "Commercial Context",
      "FEL / PDRI Context",
      "Readiness",
      "History",
    ]) {
      await workspace.getByRole("button", { name: view, exact: true }).click();
      await expect(workspace).toContainText(
        view.includes("Context")
          ? `Read-only ${view}`
          : view === "History"
            ? "Immutable assessment history"
            : view === "Dimension Summary"
              ? "Backend-owned dimension readiness"
              : view === "Evidence"
                ? "CHARTER-W3B"
                : "OVERALL_OWNER_CAPABILITY_READINESS"
      );
    }
    const submitted = await mutation(
      page,
      `/api/v1/owner-capability/assessments/${created.id}/submit`,
      workspace.getByRole("button", { name: "Submit assessment", exact: true })
    );
    expect(submitted.status).toBe("IN_REVIEW");
    await expect(workspace.getByRole("button", { name: "Complete assessment", exact: true })).toHaveCount(0);
    const reviewContext = await browser.newContext({ baseURL: baseUrl });
    const reviewerPage = await reviewContext.newPage();
    const reviewerToken = await login(reviewerPage, authority);
    const reviewer = await openOwner(reviewerPage);
    await reviewer.getByRole("combobox", { name: "Project Workspace", exact: true }).selectOption(String(project!.id));
    await reviewer.getByRole("combobox", { name: "Assessment", exact: true }).selectOption(String(created.id));
    await mutation(
      reviewerPage,
      `/api/v1/owner-capability/assessments/${created.id}/review`,
      reviewer.getByRole("button", { name: "Review assessment", exact: true })
    );
    const completed = (await mutation(
      reviewerPage,
      `/api/v1/owner-capability/assessments/${created.id}/complete`,
      reviewer.getByRole("button", { name: "Complete assessment", exact: true })
    )) as unknown as Assessment;
    expect(completed.status).toBe("COMPLETED");
    expect(completed.assessment_hash).toMatch(/^[a-f0-9]{64}$/);
    await reviewer.getByRole("button", { name: "Readiness", exact: true }).click();
    await expect(reviewer).toContainText(
      `Coverage ${requirements.requirements.length} satisfied / ${requirements.requirements.length} required`
    );
    const current = await json<{ status: string; source_current: boolean }>(
      await reviewerPage.request.get(`${apiUrl}/api/v1/owner-capability/projects/${project!.id}/current-readiness`, {
        headers: { Authorization: `Bearer ${reviewerToken}` },
      })
    );
    expect(current.status).toBe("READY");
    expect(current.source_current).toBe(true);
    const provider = await json<{
      status: string;
      source_current: boolean;
      evidence_hash: string;
      assessment_id: number;
    }>(
      await reviewerPage.request.get(`${apiUrl}/api/v1/owner-capability/projects/${project!.id}/provider-evidence`, {
        headers: { Authorization: `Bearer ${reviewerToken}` },
      })
    );
    expect(provider.status).toBe("AVAILABLE");
    expect(provider.source_current).toBe(true);
    expect(provider.evidence_hash).toBe(completed.assessment_hash);
    expect(provider.assessment_id).toBe(completed.id);
    await reviewer.getByRole("button", { name: "Refresh Preview", exact: true }).click();
    await expect(
      reviewer.getByRole("article", { name: "Owner Capability assessment preview", exact: true })
    ).toContainText("persisted=false");
    const historical = await json<Assessment>(
      await reviewerPage.request.get(`${apiUrl}/api/v1/owner-capability/assessments/${created.id}`, {
        headers: { Authorization: `Bearer ${reviewerToken}` },
      })
    );
    expect(historical.snapshot_json).toEqual(completed.snapshot_json);
    expect(historical.assessment_hash).toBe(completed.assessment_hash);
    await reviewContext.close();
  });

  test("ADMIN configures inherited framework with SoD, clone/publish/archive, stale projection and USER route security", async ({
    page,
    browser,
  }) => {
    test.setTimeout(720_000);
    const adminToken = await login(page, preparer);
    const headers = { Authorization: `Bearer ${adminToken}` };
    const projects = await json<{ projects: Array<{ id: number; name: string; code: string }> }>(
      await page.request.get(`${apiUrl}/api/v1/owner-capability/options`, { headers })
    );
    const project = projects.projects.find((row) => /wave.?3b/i.test(row.name + row.code));
    expect(project).toBeTruthy();
    await page.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }).click();
    await expand(page, "Enterprise Strategy Manager", "Admin mode navigation");
    await expand(page, "Project Definition & Investment Case", "Admin mode navigation");
    await page
      .getByRole("navigation", { name: "Admin mode navigation" })
      .getByRole("button", { name: "Owner Capability Readiness Configuration", exact: true })
      .click();
    const admin = page.getByRole("region", { name: "Owner Capability Readiness Configuration", exact: true });
    await expect(admin).toBeVisible();
    await expect(
      admin.getByRole("button", { name: /Create capability assessment|Submit assessment|Complete assessment/ })
    ).toHaveCount(0);
    await admin.getByLabel("Workspace context for preview", { exact: true }).fill(String(project!.id));
    for (const label of [
      "General",
      "Capability Framework",
      "Dimensions",
      "Requirements",
      "Maturity Scale",
      "Evidence Quality",
      "Applicability",
      "FEL Stage Rules",
      "Gate Profile Rules",
      "Project Type Rules",
      "Governance Model Rules",
      "Complexity Rules",
      "Risk Rules",
      "Uncertainty Rules",
      "Commercial Strategy Rules",
      "Blocking Rules",
      "Coverage Rules",
      "Mitigation Acceptance Rules",
      "Freshness",
      "Numbering",
      "Inheritance",
      "Review / SoD",
      "Preview",
      "History",
    ]) {
      await expect(
        admin.getByRole("navigation", {
          name: "Owner Capability Readiness Configuration governed sections",
          exact: true,
        })
      ).toContainText(label);
    }
    await admin.getByRole("button", { name: "Preview persisted=false", exact: true }).click();
    await expect(admin.getByRole("article", { name: "Effective configuration preview", exact: true })).toContainText(
      "persisted=false"
    );
    const source = admin
      .locator("[data-configuration-id]")
      .filter({ has: page.getByRole("button", { name: "Clone to DRAFT", exact: true }) })
      .filter({ hasText: "Mining Owner capability" })
      .first();
    const clonedWait = page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/owner-capability/admin/configurations/") && response.url().endsWith("/clone")
    );
    await source.getByRole("button", { name: "Clone to DRAFT", exact: true }).click();
    const cloned = await json<Configuration>(await clonedWait, 201);
    const draft = admin.locator(`[data-configuration-id="${cloned.id}"]`);
    await draft.getByRole("button", { name: "Edit policy", exact: true }).click();
    const editor = admin.getByRole("region", { name: "Edit Owner Capability Readiness Configuration", exact: true });
    async function stage(label: string, value: unknown) {
      await editor
        .getByRole("navigation", { name: "Policy section editor", exact: true })
        .getByRole("button", { name: label, exact: true })
        .click();
      await editor
        .getByRole("textbox", { name: "Governed policy section JSON", exact: true })
        .fill(JSON.stringify(value));
    }
    const configured = cloned.content_json.requirements as Array<Record<string, unknown>>;
    expect(configured.length).toBeGreaterThan(0);
    const framework = {
      ...(cloned.content_json.framework as Record<string, unknown>),
      name: "Browser-validated Owner governance framework",
    };
    const dimensions = (cloned.content_json.dimensions as Array<Record<string, unknown>>).map((row) => ({
      ...row,
      description: "Independently configured Owner capability dimension",
    }));
    const maturityScale = (cloned.content_json.maturity_scale as Array<Record<string, unknown>>).map((row) => ({
      ...row,
      name: `Owner ${String(row.name)}`,
      description: "Configured maturity; not evidence confidence",
    }));
    const qualityScale = (cloned.content_json.evidence_quality_scale as Array<Record<string, unknown>>).map((row) => ({
      ...row,
      name: `Evidence ${String(row.name)}`,
      description: "Configured evidence quality; confidence remains independent",
    }));
    const tailoredRequirements = configured.map((row, index) => ({
      ...row,
      name: `${String(row.name)} — independently governed browser revision`,
      blocking: index === 0,
      stage_rules: { "FEL-2": { minimum_maturity: "INITIAL" }, "FEL-3": { minimum_maturity: "IMPLEMENTED" } },
      complexity_rules: { HIGH: { minimum_maturity: "EFFECTIVE" } },
    }));
    const mitigationAcceptance = {
      ...(cloned.content_json.mitigation_acceptance_rules as Record<string, unknown>),
      accepted_mitigation_sufficient: true,
      allowed_approaches: ["EXTERNAL_SPECIALIST"],
      required_statuses: ["IMPLEMENTED", "CLOSED"],
      require_closure_evidence: true,
    };
    const reviewPolicy = { preparer_cannot_complete: true, author_cannot_publish: true };
    await stage("Capability Framework", framework);
    await stage("Dimensions", dimensions);
    await stage("Maturity Scale", maturityScale);
    await stage("Evidence Quality", qualityScale);
    await stage("Project Type Rules", ["MINING", "INFRASTRUCTURE", "INDUSTRIAL"]);
    await stage("Governance Model Rules", ["CAPITAL_OWNER"]);
    await stage("Requirements", tailoredRequirements);
    await stage("FEL Stage Rules", tailoredRequirements);
    await stage("Complexity Rules", tailoredRequirements);
    await stage("Blocking Rules", tailoredRequirements);
    await stage("Coverage Rules", {
      ...(cloned.content_json.coverage_rules as Record<string, unknown>),
      minimum_percent: 100,
    });
    await stage("Mitigation Acceptance Rules", mitigationAcceptance);
    await stage("Inheritance", false);
    const noInheritance = await mutation(
      page,
      "/api/v1/owner-capability/admin/preview",
      admin.getByRole("button", { name: "Preview persisted=false", exact: true })
    );
    expect(noInheritance.persisted).toBe(false);
    expect(noInheritance.readiness).toMatchObject({ readiness_status: "NOT_APPLICABLE", coverage: { required: 0 } });
    await stage("Inheritance", true);
    await stage("Review / SoD", reviewPolicy);
    const previewResult = await mutation(
      page,
      "/api/v1/owner-capability/admin/preview",
      admin.getByRole("button", { name: "Preview persisted=false", exact: true })
    );
    expect(previewResult.persisted).toBe(false);
    const stagedPolicy = previewResult.effective_configuration as Record<string, unknown>;
    expect(stagedPolicy.framework).toEqual(framework);
    expect(stagedPolicy.requirements).toEqual(tailoredRequirements);
    expect((previewResult.readiness as Record<string, unknown>).coverage).toMatchObject({
      required: tailoredRequirements.length,
    });
    await expect(admin.getByRole("article", { name: "Effective configuration preview", exact: true })).toContainText(
      "persisted=false"
    );
    const saved = (await mutation(
      page,
      `/api/v1/owner-capability/admin/configurations/${cloned.id}`,
      editor.getByRole("button", { name: "Save DRAFT revision", exact: true })
    )) as unknown as Configuration;
    expect(saved.content_json.framework).toEqual(framework);
    expect(saved.content_json.dimensions).toEqual(dimensions);
    expect(saved.content_json.maturity_scale).toEqual(maturityScale);
    expect(saved.content_json.evidence_quality_scale).toEqual(qualityScale);
    expect(saved.content_json.requirements).toEqual(tailoredRequirements);
    expect(saved.content_json.mitigation_acceptance_rules).toEqual(mitigationAcceptance);
    expect(saved.content_json.inherit_to_descendants).toBe(true);
    expect(saved.content_json.scope).toEqual(cloned.content_json.scope);
    expect(saved.content_json.separation_of_duties).toEqual(reviewPolicy);
    for (const response of [
      await page.request.post(`${apiUrl}/api/v1/admin-configuration/configurations/${cloned.id}/clone`, { headers }),
      await page.request.patch(`${apiUrl}/api/v1/admin-configuration/configurations/${cloned.id}`, {
        headers,
        data: { name: "Bypass" },
      }),
      await page.request.post(`${apiUrl}/api/v1/admin-configuration/configurations/${cloned.id}/publish`, { headers }),
    ]) {
      expect(response.status(), await response.text()).toBe(409);
      expect((await response.json()).detail.code).toBe("GOVERNED_CONFIGURATION_API_REQUIRED");
    }
    const selfPublish = await page.request.post(
      `${apiUrl}/api/v1/owner-capability/admin/configurations/${cloned.id}/publish`,
      {
        headers: {
          ...headers,
          "If-Match": String(saved.version),
          "Idempotency-Key": `wave3b-selfpublish-${Date.now()}`,
        },
        data: {},
      }
    );
    expect([403, 409]).toContain(selfPublish.status());
    const reviewContext = await browser.newContext({ baseURL: baseUrl });
    const reviewerPage = await reviewContext.newPage();
    const authorityToken = await login(reviewerPage, authority);
    await reviewerPage.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }).click();
    await reviewerPage.goto("/app/admin/strategy/owner-capability-configuration");
    const publisher = reviewerPage.getByRole("region", {
      name: "Owner Capability Readiness Configuration",
      exact: true,
    });
    const published = publisher.locator(`[data-configuration-id="${cloned.id}"]`);
    const publishedResult = await mutation(
      reviewerPage,
      `/api/v1/owner-capability/admin/configurations/${cloned.id}/publish`,
      published.getByRole("button", { name: "Publish", exact: true })
    );
    const effective = await json<{
      configuration: { id: number; version: number; lineage: Array<{ id: number; scope: unknown }> };
      requirements: Array<{ minimum_maturity: string }>;
    }>(
      await reviewerPage.request.get(`${apiUrl}/api/v1/owner-capability/projects/${project!.id}/requirements`, {
        headers: { Authorization: `Bearer ${authorityToken}` },
      })
    );
    expect(effective.configuration.id).toBe(cloned.id);
    expect(effective.configuration.version).toBe(publishedResult.version);
    expect(effective.configuration.lineage).toEqual(
      expect.arrayContaining([expect.objectContaining({ id: cloned.id, scope: cloned.content_json.scope })])
    );
    expect(effective.requirements.every((row) => row.minimum_maturity === "EFFECTIVE")).toBe(true);
    const authorityHeaders = { Authorization: `Bearer ${authorityToken}` };
    const history = await json<{ items: Assessment[] }>(
      await page.request.get(`${apiUrl}/api/v1/owner-capability/projects/${project!.id}/assessments`, { headers })
    );
    const completed = history.items.find((row) => row.status === "COMPLETED");
    expect(completed, "The USER lifecycle must supply immutable history for the ADMIN staleness check").toBeTruthy();
    if (completed) {
      const current = await json<{ status: string }>(
        await reviewerPage.request.get(`${apiUrl}/api/v1/owner-capability/projects/${project!.id}/current-readiness`, {
          headers: authorityHeaders,
        })
      );
      expect(current.status).toBe("STALE");
      const historical = await json<Assessment>(
        await reviewerPage.request.get(`${apiUrl}/api/v1/owner-capability/assessments/${completed.id}`, {
          headers: authorityHeaders,
        })
      );
      expect(historical.snapshot_json).toEqual(completed.snapshot_json);
      expect(historical.assessment_hash).toBe(completed.assessment_hash);
    }
    await mutation(
      reviewerPage,
      `/api/v1/owner-capability/admin/configurations/${cloned.id}/archive`,
      published.getByRole("button", { name: "Archive", exact: true })
    );
    await expect(published).toContainText("archived");
    await reviewContext.close();
    const userContext = await browser.newContext({ baseURL: baseUrl });
    const userPage = await userContext.newPage();
    const userToken = await login(userPage, userOnly);
    await expect(userPage.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true })).toBeDisabled();
    await userPage.goto("/app/admin/strategy/owner-capability-configuration");
    await expect(
      userPage.getByRole("region", { name: "Owner Capability Readiness Configuration", exact: true })
    ).toHaveCount(0);
    const denied = await userPage.request.get(`${apiUrl}/api/v1/owner-capability/admin/configurations`, {
      headers: { Authorization: `Bearer ${userToken}` },
    });
    expect(denied.status()).toBe(403);
    await userContext.close();
  });
});
