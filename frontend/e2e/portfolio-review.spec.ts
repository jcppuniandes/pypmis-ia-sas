import { expect, type APIResponse, type Page, test } from "@playwright/test";

// Dedicated Wave 3A PostgreSQL fixture and servers; no route interception or API mocks.
const apiUrl = process.env.E2E_API_URL || "http://127.0.0.1:8813";
const preparerEmail = process.env.E2E_WAVE3A_PREPARER_EMAIL || "admin";
const authorityEmail = process.env.E2E_WAVE3A_AUTHORITY_EMAIL || "wave3a.authority@demo.local";
const password = process.env.E2E_WAVE3A_PASSWORD || "1234";
type Review = {
  id: number;
  review_number: string;
  status: string;
  revision_version: number;
  snapshot: {
    snapshot_hash: string;
    snapshot_json: Record<string, unknown>;
    source_index_json: Record<string, unknown>;
  };
  actions: Array<Record<string, unknown>>;
  conclusions: Array<Record<string, unknown>>;
};
type Options = {
  portfolios: Array<{ id: number; code: string; name: string }>;
  allocation_plans: Array<{ id: number; portfolio_workspace_id: number | null; planning_cycle_id: number }>;
  users: Array<{ id: number; email: string }>;
};

async function json<T>(response: APIResponse, status = 200): Promise<T> {
  expect(response.status(), await response.text()).toBe(status);
  return (await response.json()) as T;
}
async function login(page: Page, email = "admin") {
  await page.goto("/login");
  await page.getByLabel("User").fill(email);
  await page.getByLabel("Password").fill(password);
  const waiting = page.waitForResponse(
    (response) => response.url().includes("/api/v1/auth/login") && response.request().method() === "POST"
  );
  await page.getByRole("button", { name: /sign in/i }).click();
  const response = await waiting;
  expect(response.ok(), await response.text()).toBe(true);
  const body = (await response.json()) as { access_token: string };
  await expect(page.getByRole("region", { name: /project workspace and control flow/i })).toBeVisible();
  return body.access_token;
}
async function expand(page: Page, name: RegExp, navigationLabel: string) {
  const button = page.getByRole("navigation", { name: navigationLabel }).getByRole("button", { name }).first();
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
}
async function reviewNavigation(page: Page) {
  await expand(page, /^enterprise strategy manager$/i, "Control Flow");
  await expand(page, /^portfolio planning & review$/i, "Control Flow");
  await expand(page, /^periodic portfolio review$/i, "Control Flow");
  await page
    .getByRole("navigation", { name: "Control Flow" })
    .getByRole("button", { name: "Review Calendar / Sessions", exact: true })
    .click();
  await expect(page).toHaveURL(/\/app\/strategy\/portfolio-review-sessions$/);
}

test.use({ trace: "on" });

test.describe("Wave 3A real Chromium and PostgreSQL release", () => {
  test("two actors conduct real Reviews and ADMIN publishes scoped policy", async ({ page, browser }) => {
    test.setTimeout(720_000);
    const token = await login(page, preparerEmail);
    const headers = { Authorization: `Bearer ${token}` };
    const options = await json<Options>(
      await page.request.get(`${apiUrl}/api/v1/portfolio-reviews/options`, { headers })
    );
    const portfolio = process.env.E2E_WAVE3A_PORTFOLIO_ID
      ? options.portfolios.find((item) => item.id === Number(process.env.E2E_WAVE3A_PORTFOLIO_ID))
      : options.portfolios.find((item) => /wave.?3a/i.test(item.name + item.code));
    expect(portfolio, "Provision a dedicated Wave 3A PostgreSQL browser fixture").toBeTruthy();
    const plan = process.env.E2E_WAVE3A_ALLOCATION_PLAN_ID
      ? options.allocation_plans.find((item) => item.id === Number(process.env.E2E_WAVE3A_ALLOCATION_PLAN_ID))
      : options.allocation_plans.find((item) => item.portfolio_workspace_id === portfolio!.id);
    expect(plan, "A real endorsed Wave 2A Allocation Plan is required").toBeTruthy();
    const authority = options.users.find((item) => item.email === authorityEmail);
    expect(authority, "A separate active authority is required for SoD").toBeTruthy();
    await reviewNavigation(page);
    const workspace = page.getByRole("region", { name: "Periodic Portfolio Review workspace" });
    await expect(workspace).toContainText("Portfolio Review ≠ Project Gate");
    await expect(workspace.getByRole("button", { name: /Clone to DRAFT|Publish/i })).toHaveCount(0);
    const authorityContext = await browser.newContext({ baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:5516" });
    const authorityPage = await authorityContext.newPage();
    const authorityToken = await login(authorityPage, authorityEmail);
    await reviewNavigation(authorityPage);
    const authorityWorkspace = authorityPage.getByRole("region", { name: "Periodic Portfolio Review workspace" });
    const completed: Review[] = [];
    for (const [index, date] of ["2026-09-05", "2026-10-05"].entries()) {
      await workspace.getByRole("button", { name: "New Review Session" }).click();
      const form = page.getByRole("form", { name: "New Portfolio Review Session form" });
      for (const [label, value] of [
        ["Portfolio Workspace ID", portfolio!.id],
        ["Planning Cycle ID", plan!.planning_cycle_id],
        ["Allocation Plan ID", plan!.id],
        ["Chair user ID", authority!.id],
      ]) {
        await form.getByLabel(String(label)).fill(String(value));
      }
      await form.getByLabel("Review type").selectOption("QUARTERLY");
      await form.getByLabel("Planned review date").fill(date);
      const waiting = page.waitForResponse(
        (response) => response.url().endsWith("/api/v1/portfolio-reviews") && response.request().method() === "POST"
      );
      await form.getByRole("button", { name: "Create governed DRAFT" }).click();
      const response = await waiting;
      expect(response.status(), await response.text()).toBe(201);
      const created = (await response.json()) as Review;
      await expect(workspace.getByRole("heading", { name: created.review_number, exact: true })).toBeVisible();
      await workspace.getByRole("button", { name: "Prepare package" }).click();
      await workspace.getByRole("button", { name: "Refresh Snapshot Preview" }).click();
      await expect(workspace.getByText("Snapshot Preview · persisted=false", { exact: true })).toBeVisible();
      await expect(workspace.getByRole("table", { name: "Snapshot source lineage" })).toContainText(
        "STRATEGIC_ALLOCATION"
      );
      await workspace.getByRole("button", { name: "Freeze Snapshot" }).click();
      await expect(workspace.getByRole("region", { name: "Selected Portfolio Review Session" })).toContainText(
        "READY_FOR_REVIEW"
      );
      const frozen = await json<Review>(
        await page.request.get(`${apiUrl}/api/v1/portfolio-reviews/${created.id}`, { headers })
      );
      expect(frozen.snapshot.snapshot_hash).toMatch(/^[a-f0-9]{64}$/);
      expect(frozen.snapshot.source_index_json).toHaveProperty("STRATEGIC_ALLOCATION");
      await authorityWorkspace.getByRole("button", { name: "Refresh", exact: true }).click();
      await authorityWorkspace.getByLabel("Review Session", { exact: true }).selectOption(String(created.id));
      const starting = authorityPage.waitForResponse(
        (response) =>
          response.url().endsWith(`/api/v1/portfolio-reviews/${created.id}/start-review`) &&
          response.request().method() === "POST",
        { timeout: 120_000 }
      );
      await authorityWorkspace.getByRole("button", { name: "Start Review" }).click();
      expect((await json<Review>(await starting)).status).toBe("IN_REVIEW");
      await expect(authorityWorkspace.getByRole("region", { name: "Selected Portfolio Review Session" })).toContainText(
        "IN_REVIEW"
      );
      await workspace.getByRole("button", { name: "Refresh", exact: true }).click();
      await expect(workspace.getByRole("region", { name: "Selected Portfolio Review Session" })).toContainText(
        "IN_REVIEW"
      );
      for (const [view, region] of [
        ["Strategic Allocation", "Portfolio Review Strategic Allocation"],
        ["Project Matrix", "Portfolio Review Project Matrix"],
        ["Budget & Resources", "Portfolio Review Budget and Resources"],
        ["Gate / FID Status", "Portfolio Review Gate and FID Status"],
        ["Exceptions", "Portfolio Review Exceptions"],
      ]) {
        await workspace.getByRole("button", { name: view, exact: true }).click();
        await expect(workspace.getByRole("region", { name: region, exact: true })).toBeVisible();
      }
      await workspace.getByRole("button", { name: "Strategic Allocation", exact: true }).click();
      await expect(workspace.getByRole("table", { name: "Strategic Allocation positions" })).toContainText(
        "UNCLASSIFIED"
      );
      await workspace.getByRole("button", { name: "Project Matrix", exact: true }).click();
      const matrix = await json<{ items: Array<{ project_workspace_id: number; project_code: string }> }>(
        await page.request.get(`${apiUrl}/api/v1/portfolio-reviews/${created.id}/project-matrix`, { headers })
      );
      expect(matrix.items.length).toBeGreaterThanOrEqual(2);
      await expect(workspace.getByRole("table", { name: "Portfolio Review Project Matrix rows" })).toContainText(
        matrix.items[0].project_code
      );
      if (index === 1) {
        await workspace.getByRole("button", { name: "Actions", exact: true }).click();
        const actions = workspace.getByRole("region", { name: "Portfolio Review Actions", exact: true });
        for (const actionType of ["HOLD_FOR_CAPACITY", "REQUEST_REASSESSMENT", "REBALANCE_CAPITAL"]) {
          await actions.getByRole("combobox", { name: "Action type", exact: true }).selectOption(actionType);
          await actions.getByRole("combobox", { name: "Subject type", exact: true }).selectOption("PROJECT");
          await actions.getByLabel("Subject ID", { exact: true }).fill(String(matrix.items[0].project_workspace_id));
          await actions.getByLabel("Owner user ID", { exact: true }).fill(String(authority!.id));
          await actions.getByLabel("Rationale", { exact: true }).fill(`Wave 3A request-only ${actionType}.`);
          await actions.getByRole("button", { name: "Create governance request" }).click();
          await expect(actions.getByRole("heading", { name: actionType, exact: true })).toBeVisible();
        }
        const after = await json<Review>(
          await page.request.get(`${apiUrl}/api/v1/portfolio-reviews/${created.id}`, { headers })
        );
        expect(after.snapshot.source_index_json).toEqual(frozen.snapshot.source_index_json);
        expect(after.actions).toHaveLength(3);
        await expect(workspace.getByRole("button", { name: "Complete Review" })).toHaveCount(0);
      }
      await authorityWorkspace.getByRole("button", { name: "Refresh", exact: true }).click();
      await authorityWorkspace.getByRole("button", { name: "Conclusions", exact: true }).click();
      const conclusions = authorityWorkspace.getByRole("region", { name: "Portfolio Review Conclusions" });
      await conclusions.getByLabel("Conclusion type").selectOption("RESOURCE_CONSTRAINED");
      const rationale = `Real frozen evidence and Portfolio sequencing for ${date}.`;
      await conclusions.getByLabel("Rationale").fill(rationale);
      await conclusions.getByRole("button", { name: "Record conclusion" }).click();
      await expect(conclusions).toContainText(rationale);
      const completing = authorityPage.waitForResponse(
        (response) =>
          response.url().endsWith(`/api/v1/portfolio-reviews/${created.id}/complete`) &&
          response.request().method() === "POST",
        { timeout: 120_000 }
      );
      await authorityWorkspace.getByRole("button", { name: "Complete Review" }).click();
      expect((await json<Review>(await completing)).status).toBe("COMPLETED");
      await expect(authorityWorkspace.getByRole("region", { name: "Selected Portfolio Review Session" })).toContainText(
        "COMPLETED"
      );
      const closed = await json<Review>(
        await authorityPage.request.get(`${apiUrl}/api/v1/portfolio-reviews/${created.id}`, {
          headers: { Authorization: `Bearer ${authorityToken}` },
        })
      );
      expect(closed.snapshot.snapshot_hash).toBe(frozen.snapshot.snapshot_hash);
      expect(closed.conclusions).toHaveLength(1);
      completed.push(closed);
      await workspace.getByRole("button", { name: "Refresh", exact: true }).click();
    }
    await workspace.getByRole("button", { name: "History", exact: true }).click();
    await expect(workspace).toContainText(
      "Completed Review · snapshot, conclusions and historical actions are immutable."
    );
    await expect(workspace).toContainText(`${completed[1].id} vs ${completed[0].id}`);
    await workspace.getByRole("button", { name: "Trends", exact: true }).click();
    await expect(workspace.getByRole("table", { name: "Portfolio Review trend points" })).toContainText(
      completed[0].review_number
    );
    await authorityContext.close();
    await page.getByRole("button", { name: "Cambiar a ADMIN MODE" }).click();
    await expand(page, /^enterprise strategy manager$/i, "Admin mode navigation");
    await expand(page, /^portfolio planning & review configuration$/i, "Admin mode navigation");
    await page
      .getByRole("navigation", { name: "Admin mode navigation" })
      .getByRole("button", { name: /^periodic portfolio review$/i })
      .click();
    await expect(page).toHaveURL(/\/app\/admin\/strategy\/portfolio-review-configuration$/);
    const admin = page.getByRole("region", { name: "Periodic Portfolio Review configuration" });
    for (const section of [
      "Review Types",
      "Cadence",
      "Agenda Template",
      "Required Snapshot Sources",
      "Review Readiness",
      "Action Types",
      "Thresholds / Alerts",
      "Bucket Variance Rules",
      "Unclassified Exposure",
      "Budget Context Rules",
      "Resource Context Rules",
      "Gate Context Rules",
      "Committee / Authority",
      "Review / SoD",
      "Inheritance",
      "Preview",
      "History",
    ]) {
      await expect(admin.getByText(section, { exact: true })).toBeVisible();
    }
    await admin.getByLabel("Portfolio context for effective preview").fill(String(portfolio!.id));
    await admin.getByRole("button", { name: "Preview effective configuration" }).click();
    await expect(admin.getByText("persisted=false", { exact: true })).toBeVisible();
    await admin.getByLabel("Target Workspace for clone").fill(String(portfolio!.id));
    const cloning = page.waitForResponse((response) => /\/admin\/configurations\/\d+\/clone$/.test(response.url()));
    await admin.getByRole("button", { name: "Clone to DRAFT" }).first().click();
    const cloneResponse = await cloning;
    expect(cloneResponse.ok(), await cloneResponse.text()).toBe(true);
    const draft = (await cloneResponse.json()) as { name: string };
    const revisions = admin.getByRole("complementary", { name: "Portfolio Review configuration revisions" });
    const card = revisions.locator("article").filter({ hasText: draft.name }).filter({ hasText: "draft" }).last();
    await card.getByRole("button", { name: "Edit governed sections" }).click();
    const editor = page.getByRole("region", { name: "Edit Portfolio Review configuration" });
    await editor.getByRole("button", { name: "Review / SoD", exact: true }).click();
    await expect(editor.getByLabel("Portfolio Review configuration JSON")).toHaveValue(/preparer_cannot_complete/);
    await editor.getByRole("button", { name: "Save DRAFT revision" }).click();
    await expect(editor).toHaveCount(0);
    await revisions
      .locator("article")
      .filter({ hasText: draft.name })
      .filter({ hasText: "draft" })
      .last()
      .getByRole("button", { name: "Publish", exact: true })
      .click();
    await revisions
      .locator("article")
      .filter({ hasText: draft.name })
      .filter({ hasText: "published" })
      .last()
      .getByRole("button", { name: "Archive", exact: true })
      .click();
    await expect(admin).toContainText("configuration archive completed.");
    await expect(
      admin.getByRole("button", { name: /New Review Session|Freeze Snapshot|Complete Review/i })
    ).toHaveCount(0);
  });
  test("direct ADMIN route denies a USER without configuration permission", async ({ page }) => {
    await login(page, authorityEmail);
    await expect(page.getByRole("button", { name: "Cambiar a ADMIN MODE" })).toBeDisabled();
    await page.goto("/app/admin/strategy/portfolio-review-configuration");
    const denied = page.getByRole("alert", { name: "Strategic configuration access denied" });
    await expect(denied).toBeVisible();
    await expect(denied).toHaveAttribute("data-control-classification", "ADMIN_CONFIGURATION");
  });
});
