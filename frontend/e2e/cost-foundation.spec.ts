import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const file = process.env.E2E_O1BC_FIXTURE;
const fixture = file ? JSON.parse(readFileSync(file, "utf8")) : null;
const api = process.env.E2E_API_URL || "http://127.0.0.1:8856";
const output = path.resolve(process.env.E2E_O1BC_OUTPUT || "../outputs/.qa/wave-o1bc-20261022/chromium");
const reason = "Controlled real Cost browser release validation";

test.describe("O1B-C real PostgreSQL Cost Foundation release", () => {
  test.skip(!fixture, "Requires dedicated disposable PostgreSQL source chain and independent actors");
  test.use({ actionTimeout: 45_000, navigationTimeout: 120_000 });
  test("ADMIN policy and independent USER Scope-first Budget Cost Baseline lifecycle", async ({ browser, request }) => {
    test.setTimeout(1_200_000);
    expect(api).toMatch(/^http:\/\/(127\.0\.0\.1|localhost):8856$/);
    mkdirSync(output, { recursive: true });
    const checks: Array<{ code: string; result: string }> = [];
    const observations: Array<{ label: string; elapsed_ms: number; status: number }> = [];
    const errors: string[] = [];
    const pages: Page[] = [];
    const project = fixture.project_workspace_id;
    const costRoute = `/workspaces/${project}/cost`;
    const stamp = String(Date.now()).slice(-8);
    const code = (label: string) => `C-UAT-${label}-${stamp}`;
    const mark = (value: string) => checks.push({ code: value, result: "PASS" });
    async function actor(role: string, route = costRoute) {
      const user = fixture.users[role];
      expect(user, `Fixture actor ${role}`).toBeTruthy();
      const response = await request.post(`${api}/api/v1/auth/login`, {
        timeout: 120_000,
        data: { email: user.email, tenant_id: user.tenant_id, password: user.password || "O1bc-disposable-only!" },
      });
      expect(response.status(), await response.text()).toBe(200);
      const session = await response.json();
      const context = await browser.newContext();
      await context.addInitScript(
        (value) =>
          localStorage.setItem(
            "pypmis_auth",
            JSON.stringify({ state: { token: value.access_token, user: value.user }, version: 0 })
          ),
        session
      );
      const page = await context.newPage();
      pages.push(page);
      page.on("pageerror", (error) => errors.push(String(error)));
      await page.goto(route);
      return { page, token: String(session.access_token), user: session.user };
    }
    async function command(page: Page, suffix: string, action: () => Promise<unknown>, status = 200, label = suffix) {
      const start = performance.now();
      const pending = page.waitForResponse(
        (response) => response.url().endsWith(suffix) && ["POST", "PUT"].includes(response.request().method())
      );
      await action();
      const response = await pending;
      observations.push({ label, elapsed_ms: performance.now() - start, status: response.status() });
      expect(response.status(), await response.text()).toBe(status);
      await expect(page.locator("[aria-busy]").last()).toHaveAttribute("aria-busy", "false");
      return response.json();
    }
    async function fill(page: Page, label: string, value: string | number) {
      await page.getByLabel(label, { exact: true }).fill(String(value));
    }
    async function choose(page: Page, label: string, value: string | number) {
      await page.getByLabel(label, { exact: true }).selectOption(String(value));
    }
    async function tab(page: Page, name: string) {
      await page
        .getByRole("navigation", { name: "Cost Manager submodules" })
        .getByRole("button", { name, exact: true })
        .click();
    }
    async function refresh(page: Page) {
      await page.getByRole("button", { name: "Actualizar Cost", exact: true }).click();
      await expect(page.getByLabel("Cost Manager", { exact: true })).toHaveAttribute("aria-busy", "false");
    }
    async function openAdmin(role: string) {
      const user = await actor(role, "/app");
      await user.page.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }).click();
      for (const name of ["Platform Administration", "Process Configuration"]) {
        const button = user.page.getByRole("button", { name, exact: true });
        if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
      }
      await user.page.getByRole("button", { name: "Process & Operational Configuration", exact: true }).click();
      await user.page.getByRole("button", { name: "Cost Profiles", exact: true }).click();
      await expect(user.page.getByLabel("Cost Profiles configuration JSON", { exact: true })).not.toHaveValue("{}");
      return user;
    }
    try {
      const admin = await openAdmin("admin");
      const profileCode = code("POLICY");
      await fill(admin.page, "Cost Profiles Code", profileCode);
      await fill(admin.page, "Cost Profiles Name", "Cost scope-first rate currency reserve and inclusion policy");
      const policy = JSON.parse(
        await admin.page.getByLabel("Cost Profiles configuration JSON", { exact: true }).inputValue()
      );
      policy.scope = { type: "workspace", workspace_id: project };
      await fill(admin.page, "Cost Profiles configuration JSON", JSON.stringify(policy, null, 2));
      const profile = await command(
        admin.page,
        "/api/v1/cost/admin/profiles",
        () => admin.page.getByRole("button", { name: "Crear Cost Profiles DRAFT", exact: true }).click(),
        201
      );
      await fill(admin.page, "Motivo Cost Profiles", reason);
      await command(
        admin.page,
        `/${profile.id}/publish`,
        () => admin.page.getByRole("button", { name: "Publicar Cost Profiles", exact: true }).click(),
        403
      );
      mark("ADMIN_AUTHOR_SELF_PUBLICATION_DENIED");
      const publisherAdmin = await openAdmin("publisher");
      await publisherAdmin.page.getByRole("button", { name: `Ver Cost Profiles ${profileCode}`, exact: true }).click();
      await fill(publisherAdmin.page, "Motivo Cost Profiles", reason);
      await command(publisherAdmin.page, `/${profile.id}/publish`, () =>
        publisherAdmin.page.getByRole("button", { name: "Publicar Cost Profiles", exact: true }).click()
      );
      mark("ADMIN_COST_RATE_CURRENCY_POLICY_INDEPENDENT_PUBLICATION");
      await admin.page.context().close();
      await publisherAdmin.page.context().close();

      const preparer = await actor("cost_controller");
      await expect(preparer.page.getByRole("heading", { name: "Cost Manager", exact: true })).toBeVisible();
      await fill(preparer.page, "Motivo Cost", reason);
      const upstreamResponse = await request.get(`${api}/api/v1/cost/projects/${project}/overview`, {
        headers: { Authorization: `Bearer ${preparer.token}` },
      });
      expect(upstreamResponse.status(), await upstreamResponse.text()).toBe(200);
      const upstream = await upstreamResponse.json();
      const scope = upstream.scope_items.find((row: any) => row.status === "APPROVED");
      const plan = upstream.plan_items.find((row: any) => row.status === "PUBLISHED");
      const pkg = upstream.packages[0];
      const schedule = upstream.schedule_versions.find((row: any) => row.status === "ACCEPTED_CURRENT");
      const period = upstream.periods.find((row: any) => row.status === "OPEN");
      expect(scope && plan && pkg && schedule && period).toBeTruthy();
      mark("CANONICAL_PROJECT_UPSTREAM_SCOPE_PLAN_PACKAGE_SCHEDULE_PERIOD_REUSED");

      await fill(preparer.page, "CBS Code", code("CBS"));
      await fill(preparer.page, "CBS Name", "Browser Cost structure independent from WBS");
      const cbs = await command(
        preparer.page,
        "/cbs",
        () => preparer.page.getByRole("button", { name: "Crear CBS", exact: true }).click(),
        201,
        "CBS creation"
      );
      await tab(preparer.page, "Cost Codes");
      await fill(preparer.page, "Cost Codes Code", code("LABOR"));
      await fill(preparer.page, "Cost Codes Name", "Browser labor code");
      const costCode = await command(
        preparer.page,
        "/cost-codes",
        () => preparer.page.getByRole("button", { name: "Crear Cost Codes", exact: true }).click(),
        201
      );
      await tab(preparer.page, "Control Accounts");
      await fill(preparer.page, "Control Accounts Code", code("CA"));
      await fill(preparer.page, "Control Accounts Name", "Browser responsibility account");
      await fill(preparer.page, "Control Account Owner User ID", preparer.user.id);
      const account = await command(
        preparer.page,
        "/control-accounts",
        () => preparer.page.getByRole("button", { name: "Crear Control Accounts", exact: true }).click(),
        201
      );
      mark("CBS_COST_CODE_CONTROL_ACCOUNT_CREATED");
      for (const [kind, target] of [
        ["SCOPE", scope.id],
        ["PLAN", plan.id],
        ["PACKAGE", pkg.id],
      ] as const) {
        await choose(preparer.page, "Cost Mapping Source Kind", kind);
        await choose(preparer.page, `Cost Mapping ${kind}`, target);
        await choose(preparer.page, "Cost Mapping CBS", cbs.id);
        await choose(preparer.page, "Cost Mapping Cost Code", costCode.id);
        await choose(preparer.page, "Cost Mapping Control Account", account.id);
        await fill(preparer.page, "Cost Mapping source_reference", `BROWSER-${kind}-${stamp}`);
        await command(
          preparer.page,
          "/mappings",
          () => preparer.page.getByRole("button", { name: "Guardar Cost Mapping", exact: true }).click(),
          201
        );
      }
      mark("EXPLICIT_SCOPE_PLAN_PACKAGE_MN_COST_MAPPINGS");

      await tab(preparer.page, "APU / Rates");
      const effectiveFrom = "2026-10-01";
      for (const [label, value] of [
        ["Rate code", code("RATE")],
        ["Rate name", "Browser labor source"],
        ["Rate amount", "20"],
        ["Rate currency", "USD"],
        ["Rate unit", "h"],
        ["Rate effective_from", effectiveFrom],
        ["Rate source_reference", `RATE-SOURCE-${stamp}`],
      ])
        await fill(preparer.page, label, value);
      const rate = await command(
        preparer.page,
        "/rates",
        () => preparer.page.getByRole("button", { name: "Crear Rate DRAFT", exact: true }).click(),
        201
      );
      const publisher = await actor("publisher");
      await fill(publisher.page, "Motivo Cost", reason);
      await tab(publisher.page, "APU / Rates");
      await publisher.page.getByRole("button", { name: `Ver Cost Rates ${rate.code}`, exact: true }).click();
      await command(publisher.page, `/rates/${rate.id}/publish`, () =>
        publisher.page.getByRole("button", { name: "Publicar Rate independiente", exact: true }).click()
      );
      await refresh(preparer.page);
      for (const [label, value] of [
        ["APU code", code("APU")],
        ["APU name", "Browser scope unit assembly"],
        ["APU unit", scope.unit],
        ["APU currency", "USD"],
        ["APU effective_from", effectiveFrom],
        ["APU source_reference", `APU-SOURCE-${stamp}`],
      ])
        await fill(preparer.page, label, value);
      await choose(preparer.page, "APU Component 1 Rate", rate.id);
      await fill(preparer.page, "APU Component 1 Quantity", "1.5");
      const apu = await command(
        preparer.page,
        "/apus",
        () => preparer.page.getByRole("button", { name: "Crear APU DRAFT", exact: true }).click(),
        201,
        "APU build-up"
      );
      await refresh(publisher.page);
      await publisher.page.getByRole("button", { name: `Ver Cost APU ${apu.code}`, exact: true }).click();
      await command(publisher.page, `/apus/${apu.id}/publish`, () =>
        publisher.page.getByRole("button", { name: "Publicar APU independiente", exact: true }).click()
      );
      mark("VERSIONED_EFFECTIVE_DATED_RATE_APU_INDEPENDENT_PUBLICATION");
      await publisher.page.context().close();

      await refresh(preparer.page);
      await tab(preparer.page, "Budget");
      await fill(preparer.page, "Budget code", code("BUDGET"));
      await fill(preparer.page, "Budget name", "Browser scope-first original Budget");
      await fill(preparer.page, "Budget Pricing Date", "2026-10-22");
      const budget = await command(
        preparer.page,
        "/budgets",
        () => preparer.page.getByRole("button", { name: "Crear Budget DRAFT", exact: true }).click(),
        201
      );
      await fill(preparer.page, "Budget Candidate Line Code", code("LINE"));
      await choose(preparer.page, "Budget Candidate Scope", scope.id);
      await choose(preparer.page, "Budget Candidate APU", apu.id);
      await choose(preparer.page, "Budget Candidate CBS", cbs.id);
      await choose(preparer.page, "Budget Candidate Cost Code", costCode.id);
      await choose(preparer.page, "Budget Candidate Control Account", account.id);
      await choose(preparer.page, "Budget Candidate Plan", plan.id);
      await choose(preparer.page, "Budget Candidate Work Package", pkg.id);
      const line = await command(
        preparer.page,
        `/budgets/${budget.id}/candidate-from-scope`,
        () =>
          preparer.page.getByRole("button", { name: "Construir Budget Candidate desde Scope", exact: true }).click(),
        201
      );
      expect(line.scope_item_id).toBe(scope.id);
      expect(line.apu_id).toBe(apu.id);
      mark("APPROVED_SCOPE_QUANTITY_X_PUBLISHED_APU_CANDIDATE_ONLY");
      await command(preparer.page, `/budgets/${budget.id}/transition`, () =>
        preparer.page.getByRole("button", { name: "Enviar Budget", exact: true }).click()
      );
      const manager = await actor("manager");
      await fill(manager.page, "Motivo Cost", reason);
      await tab(manager.page, "Budget");
      await choose(manager.page, "Selected Budget", budget.id);
      await command(manager.page, `/budgets/${budget.id}/transition`, () =>
        manager.page.getByRole("button", { name: "Revisar Budget", exact: true }).click()
      );
      const approver = await actor("second_manager");
      await fill(approver.page, "Motivo Cost", reason);
      await tab(approver.page, "Budget");
      await choose(approver.page, "Selected Budget", budget.id);
      await command(approver.page, `/budgets/${budget.id}/transition`, () =>
        approver.page.getByRole("button", { name: "Aprobar Budget independiente", exact: true }).click()
      );
      await expect(
        approver.page
          .getByRole("table", { name: "Budget Versions", exact: true })
          .getByRole("row")
          .filter({ hasText: budget.code })
      ).toContainText("APPROVED");
      mark("BUDGET_SUBMIT_REVIEW_INDEPENDENT_APPROVE_IMMUTABLE_HISTORY");
      await approver.page.context().close();

      await refresh(preparer.page);
      await tab(preparer.page, "Cost Baseline");
      await fill(preparer.page, "Cost Baseline Code", code("BASELINE"));
      await choose(preparer.page, "Cost Baseline Budget", budget.id);
      const baseline = await command(
        preparer.page,
        "/baselines",
        () => preparer.page.getByRole("button", { name: "Crear Cost Baseline Candidate", exact: true }).click(),
        201
      );
      await tab(preparer.page, "Cost Phasing");
      await choose(preparer.page, "Phasing Cost Baseline", baseline.id);
      await choose(preparer.page, "Phasing Budget Line", line.id);
      await choose(preparer.page, "Cost Phasing Method", "ACTIVITY_BASED");
      await choose(preparer.page, "Phasing Schedule Version", schedule.id);
      const activity =
        schedule.snapshot_json.activities.find((row: any) => !row.is_milestone) || schedule.snapshot_json.activities[0];
      await choose(preparer.page, "Phasing Activity", activity.external_id);
      await choose(preparer.page, "Phasing Project Controls Period", period.id);
      await command(
        preparer.page,
        `/baselines/${baseline.id}/phase`,
        () => preparer.page.getByRole("button", { name: "Distribuir Cost Baseline", exact: true }).click(),
        201
      );
      await refresh(manager.page);
      await tab(manager.page, "Cost Baseline");
      await manager.page.getByRole("button", { name: `Ver Cost Baselines ${baseline.code}`, exact: true }).click();
      await command(manager.page, `/baselines/${baseline.id}/approve`, () =>
        manager.page.getByRole("button", { name: "Aprobar Cost Baseline independiente", exact: true }).click()
      );
      await expect(
        manager.page
          .getByRole("table", { name: "Cost Baselines", exact: true })
          .getByRole("row")
          .filter({ hasText: baseline.code })
      ).toContainText("APPROVED");
      mark("SCHEDULE_AUTHORITY_PHASING_COST_BASELINE_INDEPENDENT_APPROVAL");

      await tab(preparer.page, "Actuals");
      const actualDate = String(period.period_start).slice(0, 10);
      for (const [label, value] of [
        ["Actual source_reference", code("ACTUAL")],
        ["Actual posting_date", actualDate],
        ["Actual recognition_date", actualDate],
        ["Actual amount", "25"],
        ["Actual evidence_ref", `DISPOSABLE-UAT-COST-EVIDENCE-${stamp}`],
      ])
        await fill(preparer.page, label, value);
      await choose(preparer.page, "Actual Period", period.id);
      await choose(preparer.page, "Actual Control Account", account.id);
      const actual = await command(
        preparer.page,
        "/actuals",
        () => preparer.page.getByRole("button", { name: "Importar Actual candidato", exact: true }).click(),
        201
      );
      await refresh(manager.page);
      await tab(manager.page, "Actuals");
      await manager.page.getByRole("button", { name: `Ver Actual Cost ${actual.id}`, exact: true }).click();
      await command(manager.page, `/actuals/${actual.id}/decision`, () =>
        manager.page.getByRole("button", { name: "Reconocer Actual independiente", exact: true }).click()
      );
      mark("SOURCE_UNIQUE_ACTUAL_IMPORT_AND_INDEPENDENT_RECOGNITION");

      const commitmentView = preparer.page.waitForResponse(
        (response) => response.url().endsWith("/commitments/reconciliation") && response.request().method() === "GET"
      );
      await tab(preparer.page, "Commitments");
      expect((await commitmentView).status()).toBe(200);
      await expect(preparer.page.getByRole("table", { name: "Commitment References", exact: true })).toBeVisible();
      await expect(preparer.page.getByText("Net Commitment", { exact: true })).toBeVisible();
      await expect(preparer.page.getByText(/INCLUDED y CALL_OFF/)).toBeVisible();
      mark("COMMITMENT_RECONCILIATION_PROJECTION_NOT_LEGAL_AUTHORITY");
      await tab(preparer.page, "Accruals");
      await expect(preparer.page.getByText("DEFERRED_WITH_CONTRACT", { exact: true })).toBeVisible();
      mark("ACCRUAL_CONTRACT_EXPLICIT_NO_FAKE_MUTATIONS");
      const summaryView = preparer.page.waitForResponse(
        (response) => response.url().endsWith("/financial-overview") && response.request().method() === "GET"
      );
      const cashView = preparer.page.waitForResponse(
        (response) => response.url().endsWith("/cash-flow") && response.request().method() === "GET"
      );
      await tab(preparer.page, "Cost Overview");
      expect((await summaryView).status()).toBe(200);
      expect((await cashView).status()).toBe(200);
      await expect(preparer.page.getByRole("table", { name: "Cost Cash Flow", exact: true })).toBeVisible();
      await expect(preparer.page.getByText(/EAC = Actual reconocido/)).toBeVisible();
      mark("COST_OVERVIEW_CASH_FLOW_ETC_EAC_BOUNDARIES");
      await preparer.page.getByText("Historial Cost · fuentes y aprobaciones", { exact: true }).click();
      await expect(preparer.page.getByRole("table", { name: "Cost History", exact: true })).toContainText(
        "BUDGET_APPROVED"
      );
      mark("BUDGET_BASELINE_APPROVAL_HISTORY_VISIBLE");
      await preparer.page.screenshot({ path: path.join(output, "cost-overview-and-history.png"), fullPage: true });
      await manager.page.screenshot({ path: path.join(output, "cost-actual-recognized.png"), fullPage: true });
      expect(errors).toEqual([]);
      mark("ZERO_BROWSER_RUNTIME_ERRORS");
      writeFileSync(
        path.join(output, "browser-uat.json"),
        JSON.stringify(
          {
            result: "PASS",
            checks,
            observations,
            browser_errors: errors,
            project_workspace_id: project,
            created: {
              profile: profile.id,
              cbs: cbs.id,
              cost_code: costCode.id,
              account: account.id,
              rate: rate.id,
              apu: apu.id,
              budget: budget.id,
              line: line.id,
              baseline: baseline.id,
              actual: actual.id,
            },
            completed_at: new Date().toISOString(),
          },
          null,
          2
        )
      );
    } catch (error) {
      writeFileSync(
        path.join(output, "browser-uat-failure.json"),
        JSON.stringify({ result: "FAIL", checks, observations, browser_errors: errors, error: String(error) }, null, 2)
      );
      for (const [index, page] of pages.entries())
        if (!page.isClosed())
          await page
            .screenshot({ path: path.join(output, `failure-${index}.png`), fullPage: true })
            .catch(() => undefined);
      throw error;
    } finally {
      for (const page of pages) await page.context().close();
    }
  });
});
