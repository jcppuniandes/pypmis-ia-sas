import { expect, type APIResponse, type Browser, type Page, test } from "@playwright/test";

const apiUrl = process.env.E2E_API_URL || "http://localhost:8000";

type LoginBody = { access_token: string };
type Role = { id: number; code: string };
type User = { id: number; email: string };
type Assignment = { subject_id: number; role_code: string; status: string };
type SecurityOverview = { users: User[]; roles: Role[]; assignments: Assignment[] };
type Configuration = {
  id: number;
  name: string;
  description: string;
  status: string;
  version: number;
  content_json: Record<string, unknown>;
};
type Options = {
  strategic_objectives: Array<{ code: string; label: string }>;
  owning_workspaces: Array<{ id: number; name: string }>;
  sponsors: Array<{ id: number; name: string; email?: string }>;
};

async function apiJson<T>(response: APIResponse, expectedStatus = 200) {
  expect(response.status(), await response.text()).toBe(expectedStatus);
  return (await response.json()) as T;
}

async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("User").fill(email);
  await page.getByLabel("Password").fill("1234");
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes("/api/v1/auth/login") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /sign in/i }).click();
  const response = await responsePromise;
  expect(response.ok(), await response.text()).toBe(true);
  const body = (await response.json()) as LoginBody;
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
  return body.access_token;
}

async function expand(page: Page, name: RegExp) {
  const button = page.getByRole("button", { name }).first();
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
}

async function openCapitalPlanning(page: Page, destination: "pipeline" | "review" = "pipeline") {
  await expand(page, /^enterprise strategy manager$/i);
  await expand(page, /^strategic capital planning & demand$/i);
  await page
    .getByRole("button", {
      name: destination === "pipeline" ? /^capital demand pipeline$/i : /^demands in review$/i,
    })
    .click();
  await expect(page.getByRole("heading", { name: "Strategic Capital Planning & Demand", exact: true })).toBeVisible();
}

async function openCapitalPlanningAdmin(page: Page) {
  await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
  await expect(page).toHaveURL(/\/app$/);
  const navigation = page.getByRole("navigation", { name: "Admin mode navigation" });
  await expand(page, /^enterprise strategy manager$/i);
  const modules = navigation.getByRole("group", { name: "Módulos de Enterprise Strategy Manager" });
  const phase = modules.locator(":scope > .navigatorModule > .navigatorModuleButton").filter({
    hasText: "Strategic Capital Planning & Demand Configuration",
  });
  await expect(phase).toHaveCount(1);
  if ((await phase.getAttribute("aria-expanded")) !== "true") await phase.click();
  const submodules = modules.getByRole("group", {
    name: "Submódulos de Strategic Capital Planning & Demand Configuration",
  });
  await submodules
    .getByRole("button", { name: "Strategic Capital Planning & Demand Configuration", exact: true })
    .click();
  await expect(page).toHaveURL(/\/app\/admin\/strategy\/capital-planning-configuration$/);
  await expect(
    page.getByRole("heading", { name: "Strategic Capital Planning & Demand Configuration", exact: true })
  ).toBeVisible();
}

async function grantReviewerRoles(page: Page, adminToken: string) {
  const headers = { Authorization: `Bearer ${adminToken}`, "Content-Type": "application/json" };
  // Capital Planning installs its permission/role catalog without creating live records.
  await apiJson(await page.request.get(`${apiUrl}/api/v1/capital-planning/options`, { headers }));
  const overview = await apiJson<SecurityOverview>(
    await page.request.get(`${apiUrl}/api/v1/organization-security/overview`, { headers })
  );
  const reviewer = overview.users.find((item) => item.email === "ana.control@demo.local");
  expect(reviewer).toBeTruthy();
  for (const roleCode of ["capital_planning_reviewer", "capital_planning_endorser", "capital_planning_originator"]) {
    const role = overview.roles.find((item) => item.code === roleCode);
    expect(role, `Missing governed role ${roleCode}`).toBeTruthy();
    const alreadyAssigned = overview.assignments.some(
      (item) => item.subject_id === reviewer!.id && item.role_code === roleCode && item.status === "active"
    );
    if (!alreadyAssigned) {
      await apiJson(
        await page.request.post(`${apiUrl}/api/v1/organization-security/assignments`, {
          headers,
          data: {
            subject_type: "user",
            subject_id: reviewer!.id,
            role_id: role!.id,
            scope_type: "organization",
            scope_unit_id: null,
          },
        }),
        201
      );
    }
  }
}

async function publishWave1Configuration(page: Page, adminToken: string, suffix: string) {
  const headers = { Authorization: `Bearer ${adminToken}`, "Content-Type": "application/json" };
  const options = await apiJson<Options>(
    await page.request.get(`${apiUrl}/api/v1/capital-planning/options`, { headers })
  );
  expect(options.strategic_objectives.length).toBeGreaterThan(0);
  expect(options.owning_workspaces.length).toBeGreaterThan(0);
  const objective = options.strategic_objectives[0];
  const configurations = await apiJson<Configuration[]>(
    await page.request.get(`${apiUrl}/api/v1/capital-planning/admin/configurations`, { headers })
  );
  const published = configurations.find((item) => item.status.toLowerCase() === "published");
  expect(published).toBeTruthy();
  const draft = await apiJson<Configuration>(
    await page.request.post(`${apiUrl}/api/v1/capital-planning/admin/configurations/${published!.id}/clone`, {
      headers: { ...headers, "If-Match": `"${published!.version}"` },
    })
  );
  const themeCode = `wave1-${suffix}`;
  const content = {
    ...published!.content_json,
    themes: [{ code: themeCode, label: `Wave 1 ${suffix}`, strategic_objective_codes: [objective.code] }],
    drivers: [{ code: "compliance", label: "Compliance" }],
    categories: [{ code: "sustaining", label: "Sustaining" }],
    planning_horizons: [{ code: "near", label: "Near term" }],
    urgency_levels: [{ code: "high", label: "High" }],
    uncertainty_levels: [{ code: "medium", label: "Medium" }],
    required_fields: [
      "name",
      "planning_cycle_id",
      "business_or_asset_need",
      "strategic_driver",
      "target_horizon",
      "sponsor_user_id",
      "owning_workspace_id",
      "theme_codes",
      "strategic_objective_codes",
    ],
    separation_of_duties: { author_cannot_endorse: true },
  };
  const updated = await apiJson<Configuration>(
    await page.request.put(`${apiUrl}/api/v1/capital-planning/admin/configurations/${draft.id}`, {
      headers: { ...headers, "If-Match": `"${draft.version}"` },
      data: { name: draft.name, description: draft.description, content_json: content },
    })
  );
  await apiJson<Configuration>(
    await page.request.post(`${apiUrl}/api/v1/capital-planning/admin/configurations/${updated.id}/publish`, {
      headers: { ...headers, "If-Match": `"${updated.version}"` },
    })
  );
  return { options, objective, themeCode, themeLabel: `Wave 1 ${suffix}` };
}

test.describe("Wave 1 Strategic Capital Planning browser release", () => {
  test.setTimeout(300_000);

  test("runs the real governed Cycle → Demand → endorsement → explicit Idea origin path", async ({ browser, page }) => {
    const suffix = `${Date.now()}`.slice(-8);
    const cycleName = `Wave 1 Cycle ${suffix}`;
    const demandName = `North terminal need ${suffix}`;
    const adminToken = await login(page, "admin");
    await grantReviewerRoles(page, adminToken);
    const configured = await publishWave1Configuration(page, adminToken, suffix);

    await openCapitalPlanning(page);
    const userSurface = page.locator('[data-control-classification="USER_TRANSACTION"]');
    await expect(userSurface).toBeVisible();
    for (const forbiddenAdminAction of [
      "Preview effective configuration",
      "Clone to DRAFT",
      "Edit governed sections",
      "Publish",
      "Archive",
    ]) {
      await expect(userSurface.getByRole("button", { name: forbiddenAdminAction, exact: true })).toHaveCount(0);
    }
    const workspaceNav = page.getByRole("navigation", { name: "Capital Planning workspace views" });
    await workspaceNav.getByRole("button", { name: "Planning Cycles" }).click();
    await page.getByRole("button", { name: "New Planning Cycle" }).click();
    const cycleForm = page.getByRole("form", { name: "New Planning Cycle form" });
    await cycleForm.getByLabel("Name").fill(cycleName);
    await cycleForm.getByLabel("Horizon start").fill("2027-01-01");
    await cycleForm.getByLabel("Horizon end").fill("2027-12-31");
    await cycleForm.getByLabel("Scope Workspace").selectOption(String(configured.options.owning_workspaces[0].id));
    await cycleForm
      .getByLabel("Responsible organization")
      .selectOption(String(configured.options.owning_workspaces[0].id));
    await cycleForm.getByLabel(configured.themeLabel).check();
    await cycleForm.getByLabel("Capital basis currency (optional)").fill("COP");
    const cycleResponsePromise = page.waitForResponse(
      (response) => response.url().endsWith("/api/v1/capital-planning/cycles") && response.request().method() === "POST"
    );
    await cycleForm.getByRole("button", { name: "Create cycle" }).click();
    const cycleResponse = await cycleResponsePromise;
    expect(cycleResponse.ok(), await cycleResponse.text()).toBe(true);
    const createdCycle = (await cycleResponse.json()) as { id: number };
    const cycleCard = page.getByRole("heading", { name: cycleName }).locator("..");
    await cycleCard.getByRole("button", { name: "Open governed cycle" }).click();
    await expect(cycleCard.getByText("OPEN", { exact: true })).toBeVisible();

    await workspaceNav.getByRole("button", { name: "Capital Demand Pipeline" }).click();
    await page.getByRole("button", { name: "New Capital Demand" }).click();
    const demandForm = page.getByRole("form", { name: "New Capital Demand form" });
    await demandForm.getByLabel("Demand name").fill(demandName);
    await demandForm
      .getByLabel("Business / asset need")
      .fill("Restore asset integrity before terminal capacity and compliance are constrained.");
    await demandForm.getByLabel("Planning Cycle").selectOption(String(createdCycle.id));
    await demandForm.getByLabel("Owning Workspace").selectOption(String(configured.options.owning_workspaces[0].id));
    await demandForm.getByLabel("Strategic Investment Theme").selectOption(configured.themeCode);
    await demandForm.getByLabel("Strategic Objective").selectOption(configured.objective.code);
    await demandForm.getByLabel("Strategic driver").selectOption("compliance");
    await demandForm.getByLabel("Category").selectOption("sustaining");
    await demandForm.getByLabel("Sponsor").selectOption(String(configured.options.sponsors[0].id));
    await demandForm.getByLabel("Target horizon").selectOption("near");
    await demandForm.getByLabel("Urgency").selectOption("high");
    await demandForm.getByLabel("Uncertainty").selectOption("medium");
    await demandForm.getByLabel("Location context").fill("North terminal");
    await demandForm.getByLabel("Indicative Capital Need").fill("1250000");
    await demandForm.getByLabel("Currency").fill("COP");
    await demandForm.getByLabel("Assumptions (one per line)").fill("Access remains available\nPermit approved");
    await demandForm.getByLabel("Constraints (one per line)").fill("Shutdown window");
    await demandForm.getByLabel("Dependencies (one per line)").fill("Integrity study");
    const demandResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v1/capital-planning/demands") && response.request().method() === "POST"
    );
    await demandForm.getByRole("button", { name: "Create governed need" }).click();
    const demandResponse = await demandResponsePromise;
    expect(demandResponse.ok(), await demandResponse.text()).toBe(true);
    const createdDemand = (await demandResponse.json()) as { id: number };
    await expect(page.getByRole("heading", { name: demandName })).toBeVisible();
    await page.getByRole("button", { name: "Edit Demand" }).click();
    const editForm = page.getByRole("form", { name: "Edit Capital Demand form" });
    const revisedNeed = "Restore governed asset integrity before terminal capacity and compliance are constrained.";
    await editForm.getByLabel("Business / asset need").fill(revisedNeed);
    await editForm.getByLabel("Location context").fill("North terminal / governed revision");
    const updateResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/v1/capital-planning/demands/${createdDemand.id}`) &&
        response.request().method() === "PUT"
    );
    await editForm.getByRole("button", { name: "Save governed need" }).click();
    const updateResponse = await updateResponsePromise;
    expect(updateResponse.ok(), await updateResponse.text()).toBe(true);
    const demandDetail = page.getByRole("region", { name: "Capital Demand detail" });
    await expect(demandDetail.getByText(revisedNeed)).toBeVisible();
    await page.getByRole("button", { name: /Submit/ }).click();
    await expect(demandDetail.getByText("SUBMITTED", { exact: true })).toBeVisible();

    const reviewerContext = await (browser as Browser).newContext();
    const reviewerPage = await reviewerContext.newPage();
    const reviewerToken = await login(reviewerPage, "ana.control@demo.local");
    await openCapitalPlanning(reviewerPage, "review");
    await reviewerPage.getByRole("button", { name: new RegExp(demandName, "i") }).click();
    const historyPanel = reviewerPage.getByRole("region", { name: "Capital Demand history" });
    for (const eventType of [
      "capital_planning.demand.created",
      "capital_planning.demand.updated",
      "capital_planning.demand.submit",
    ]) {
      await expect(historyPanel.getByText(eventType, { exact: true })).toBeVisible();
    }
    await reviewerPage.getByRole("button", { name: "Start review" }).click();
    const reviewerDemandDetail = reviewerPage.getByRole("region", { name: "Capital Demand detail" });
    await expect(reviewerDemandDetail.getByText("IN_REVIEW", { exact: true })).toBeVisible();
    const endorseResponsePromise = reviewerPage.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/v1/capital-planning/demands/${createdDemand.id}/endorse`) &&
        response.request().method() === "POST"
    );
    await reviewerPage.getByRole("button", { name: "Endorse need" }).click();
    const endorseResponse = await endorseResponsePromise;
    expect(endorseResponse.ok(), await endorseResponse.text()).toBe(true);
    expect((await endorseResponse.json()) as { status: string }).toMatchObject({ status: "ENDORSED" });
    const reviewerWorkspaceNav = reviewerPage.getByRole("navigation", { name: "Capital Planning workspace views" });
    await reviewerWorkspaceNav.getByRole("button", { name: "Endorsed Demands" }).click();
    await reviewerPage.getByRole("button", { name: new RegExp(demandName, "i") }).click();
    await expect(
      reviewerPage.getByRole("region", { name: "Capital Demand detail" }).getByText("ENDORSED", { exact: true })
    ).toBeVisible();
    await reviewerPage.getByRole("button", { name: "Originate Idea" }).click();
    const ideaForm = reviewerPage.getByRole("form", { name: "Originate Idea form" });
    await ideaForm.getByLabel("Expected benefit").fill("Reduced integrity and compliance exposure");
    const originResponsePromise = reviewerPage.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/v1/capital-planning/demands/${createdDemand.id}/originate-idea`) &&
        response.request().method() === "POST"
    );
    await ideaForm.getByRole("button", { name: "Originate governed Idea" }).click();
    const originResponse = await originResponsePromise;
    expect(originResponse.ok(), await originResponse.text()).toBe(true);
    const origin = (await originResponse.json()) as { idea_number: string; source_snapshot_hash: string };
    await expect(reviewerPage.getByText(new RegExp(`Idea originated: ${origin.idea_number}`))).toBeVisible();
    await expect(reviewerPage.getByText(origin.idea_number, { exact: true })).toBeVisible();
    expect(origin.source_snapshot_hash).toMatch(/^[a-f0-9]{64}$/);

    const reviewerHeaders = { Authorization: `Bearer ${reviewerToken}` };
    const origins = await apiJson<Array<{ idea_id: number; source_snapshot_hash: string }>>(
      await reviewerPage.request.get(`${apiUrl}/api/v1/capital-planning/demands/${createdDemand.id}/originated-ideas`, {
        headers: reviewerHeaders,
      })
    );
    expect(origins).toHaveLength(1);
    expect(origins[0].source_snapshot_hash).toBe(origin.source_snapshot_hash);
    const history = await apiJson<Array<{ event_type: string }>>(
      await reviewerPage.request.get(`${apiUrl}/api/v1/capital-planning/demands/${createdDemand.id}/history`, {
        headers: reviewerHeaders,
      })
    );
    expect(history.map((event) => event.event_type)).toEqual(
      expect.arrayContaining([
        "capital_planning.demand.created",
        "capital_planning.demand.updated",
        "capital_planning.demand.submit",
        "capital_planning.demand.review",
        "capital_planning.demand.endorse",
        "capital_planning.demand.idea_originated",
      ])
    );
    await reviewerPage.getByRole("button", { name: "Open Idea Lifecycle" }).click();
    await expect(reviewerPage).toHaveURL(/\/app\/strategy\/idea-lifecycle$/);
    await expect(reviewerPage.getByRole("heading", { name: "Idea Lifecycle", exact: true })).toBeVisible();
    await reviewerContext.close();
  });

  test("governs configuration through ADMIN UI without exposing live Capital Planning actions", async ({ page }) => {
    const suffix = `admin-${`${Date.now()}`.slice(-8)}`;
    const adminToken = await login(page, "admin");
    const configured = await publishWave1Configuration(page, adminToken, suffix);
    await openCapitalPlanningAdmin(page);

    const adminSurface = page.locator('[data-control-classification="ADMIN_CONFIGURATION"]');
    await expect(adminSurface).toBeVisible();
    for (const forbiddenAction of [
      "New Planning Cycle",
      "New Capital Demand",
      "Submit",
      "Start review",
      "Endorse need",
      "Originate Idea",
    ]) {
      await expect(adminSurface.getByRole("button", { name: forbiddenAction, exact: true })).toHaveCount(0);
    }

    const scope = adminSurface.getByRole("region", { name: "Capital Planning ADMIN scope" });
    for (const governedSection of [
      "Strategic Investment Themes",
      "Demand Drivers",
      "Demand Categories",
      "Planning Horizons",
      "Urgency Levels",
      "Uncertainty Levels",
      "Required Fields",
      "Lifecycle Rules",
      "Project Type Applicability",
      "Review / Separation of Duties",
      "Governance Model Applicability",
      "Numbering",
      "Inheritance",
      "Clone / Preview / Publish / Archive",
    ]) {
      await expect(scope.getByText(governedSection, { exact: true })).toBeVisible();
    }

    const previewResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v1/capital-planning/admin/preview") && response.request().method() === "POST"
    );
    const targetWorkspaceId = configured.options.owning_workspaces[0].id;
    await adminSurface
      .getByLabel("Workspace context for effective inheritance preview")
      .fill(String(targetWorkspaceId));
    await adminSurface.getByRole("button", { name: "Preview effective configuration" }).click();
    const previewResponse = await previewResponsePromise;
    expect(previewResponse.ok(), await previewResponse.text()).toBe(true);
    await expect(adminSurface.getByText("persisted=false", { exact: true })).toBeVisible();
    await expect(
      adminSurface.getByText(/No live Planning Cycle, Demand, Idea, Project, Budget or Funding record/)
    ).toBeVisible();

    const publishedCard = adminSurface.locator(".capitalAdminGrid article:has(.status-published)");
    await expect(publishedCard).toHaveCount(1);

    const archiveResponsePromise = page.waitForResponse(
      (response) =>
        /\/api\/v1\/capital-planning\/admin\/configurations\/\d+\/archive$/.test(response.url()) &&
        response.request().method() === "POST"
    );
    await publishedCard.getByRole("button", { name: "Archive" }).click();
    const archiveResponse = await archiveResponsePromise;
    expect(archiveResponse.status()).toBe(409);
    await expect(
      adminSurface.getByRole("status").filter({ hasText: "DEFAULT_CONFIGURATION_REPLACEMENT_REQUIRED" })
    ).toBeVisible();

    const cloneResponsePromise = page.waitForResponse(
      (response) =>
        /\/api\/v1\/capital-planning\/admin\/configurations\/\d+\/clone$/.test(response.url()) &&
        response.request().method() === "POST"
    );
    await publishedCard.getByRole("button", { name: "Clone to DRAFT" }).click();
    const cloneResponse = await cloneResponsePromise;
    expect(cloneResponse.ok(), await cloneResponse.text()).toBe(true);
    const cloned = (await cloneResponse.json()) as { id: number; revision: number };
    const draftCard = adminSurface
      .locator(".capitalAdminGrid article")
      .filter({ hasText: `Revision ${cloned.revision}` });
    await expect(draftCard.locator(".status-draft")).toBeVisible();

    await draftCard.getByRole("button", { name: "Edit governed sections" }).click();
    const editor = adminSurface.getByRole("region", { name: "Edit Capital Planning configuration" });
    await expect(editor).toBeVisible();
    const sectionNavigation = editor.getByRole("navigation", { name: "Capital Planning configuration sections" });
    await sectionNavigation.getByRole("button", { name: "Demand Drivers", exact: true }).click();
    const driversEditor = editor.getByLabel(/Demand Drivers — governed JSON fragment/);
    await expect(driversEditor).toHaveValue(/compliance/);
    await driversEditor.fill(JSON.stringify([{ code: "compliance", label: `Compliance governed ${suffix}` }], null, 2));
    await editor.getByRole("button", { name: "Apply section to DRAFT" }).click();
    await expect(adminSurface.getByRole("status").filter({ hasText: "Demand Drivers staged" })).toBeVisible();

    const saveResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/v1/capital-planning/admin/configurations/${cloned.id}`) &&
        response.request().method() === "PUT"
    );
    await editor.getByRole("button", { name: "Save DRAFT revision" }).click();
    const saveResponse = await saveResponsePromise;
    expect(saveResponse.ok(), await saveResponse.text()).toBe(true);
    const saved = (await saveResponse.json()) as {
      content_json: { drivers: Array<{ code: string; label: string }> };
    };
    expect(saved.content_json.drivers).toEqual([{ code: "compliance", label: `Compliance governed ${suffix}` }]);
    await expect(editor).toBeHidden();

    const savedDraftCard = adminSurface.locator(".capitalAdminGrid article").filter({
      hasText: `Revision ${cloned.revision}`,
    });
    const publishResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/v1/capital-planning/admin/configurations/${cloned.id}/publish`) &&
        response.request().method() === "POST"
    );
    await savedDraftCard.getByRole("button", { name: "Publish" }).click();
    const publishResponse = await publishResponsePromise;
    expect(publishResponse.ok(), await publishResponse.text()).toBe(true);
    await expect(savedDraftCard.locator(".status-published")).toBeVisible();
    await expect(savedDraftCard.getByText(`workspace-${targetWorkspaceId}`, { exact: true })).toBeVisible();
    await expect(adminSurface.locator(".capitalAdminGrid .status-published")).toHaveCount(2);

    const inheritedPreviewResponsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/v1/capital-planning/admin/preview") && response.request().method() === "POST"
    );
    await adminSurface.getByRole("button", { name: "Preview effective configuration" }).click();
    const inheritedPreviewResponse = await inheritedPreviewResponsePromise;
    expect(inheritedPreviewResponse.ok(), await inheritedPreviewResponse.text()).toBe(true);
    const inheritedPreview = (await inheritedPreviewResponse.json()) as {
      persisted: boolean;
      source: { code: string };
      effective: { drivers: Array<{ code: string; label: string }> };
    };
    expect(inheritedPreview.persisted).toBe(false);
    expect(inheritedPreview.source.code).toBe(`workspace-${targetWorkspaceId}`);
    expect(inheritedPreview.effective.drivers).toEqual([
      { code: "compliance", label: `Compliance governed ${suffix}` },
    ]);
  });
});
