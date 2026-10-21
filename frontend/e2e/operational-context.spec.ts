import { expect, test, type Page } from "@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { performance } from "node:perf_hooks";

type Fixture = {
  tenant_id: number;
  tenant_slug: string;
  users: Record<string, { id: number; email: string; tenant_id: number }>;
  workspaces: Record<string, { id: number; external_key: string; name: string }>;
  legacy_project_id: number;
  fixture_scope: string;
};
type Session = { access_token: string; user: Record<string, unknown> };

const fixtureFile = process.env.E2E_O1A_FIXTURE;
const fixture = fixtureFile ? (JSON.parse(readFileSync(fixtureFile, "utf8")) as Fixture) : null;
const api = process.env.E2E_API_URL || "http://127.0.0.1:8851";
const output = path.resolve(process.env.E2E_O1A_OUTPUT || "../outputs/.qa/wave-o1a-20261019/chromium");

test.describe("Wave O1A real Chromium / isolated PostgreSQL", () => {
  test.use({ actionTimeout: 30_000, navigationTimeout: 60_000 });
  test.skip(!fixture, "Requires an explicitly provisioned isolated PostgreSQL O1A fixture.");

  test("ADMIN profile, canonical USER binding and period lifecycle, and direct-route authorization", async ({
    browser,
    request,
  }) => {
    test.setTimeout(420_000);
    expect(api).toMatch(/^http:\/\/(127\.0\.0\.1|localhost):8851$/);
    expect(fixture!.fixture_scope).toContain("Real PG");
    mkdirSync(output, { recursive: true });
    const evidence: Record<string, unknown> = {
      started_at: new Date().toISOString(),
      fixture_tenant: fixture!.tenant_id,
      fixture_scope: fixture!.fixture_scope,
      authentication:
        "Real API login with explicit tenant_id, then legitimate issued session in pypmis_auth. Login UI has no tenant selector; no UI/API response mocks.",
      checks: [],
      local_observations: [],
    };
    const checks = evidence.checks as Array<{ code: string; result: string }>;
    const pages: Page[] = [];
    const mark = (code: string) => checks.push({ code, result: "PASS" });

    async function login(role: string) {
      const user = fixture!.users[role];
      const response = await request.post(`${api}/api/v1/auth/login`, {
        data: {
          tenant_id: user.tenant_id,
          email: user.email,
          password: "O1a-disposable-only!",
        },
      });
      expect(response.status(), await response.text()).toBe(200);
      return (await response.json()) as Session;
    }

    async function signedPage(role: string, route: string) {
      const session = await login(role);
      const context = await browser.newContext();
      await context.addInitScript((value) => {
        localStorage.setItem(
          "pypmis_auth",
          JSON.stringify({ state: { token: value.access_token, user: value.user }, version: 0 })
        );
      }, session);
      const page = await context.newPage();
      pages.push(page);
      await page.goto(route);
      return { page, session };
    }

    async function expand(page: Page, name: string) {
      const item = page.getByRole("button", { name, exact: true });
      await expect(item).toBeVisible();
      if ((await item.getAttribute("aria-expanded")) !== "true") await item.click();
    }

    async function adminProfiles(role: string) {
      const actor = await signedPage(role, "/app");
      const toggle = actor.page.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true });
      await expect(toggle).toBeEnabled();
      await toggle.click();
      await expand(actor.page, "Platform Administration");
      await expand(actor.page, "Process Configuration");
      await actor.page.getByRole("button", { name: "Process & Operational Configuration", exact: true }).click();
      await actor.page.getByRole("button", { name: "Operational Profiles", exact: true }).click();
      await expect(actor.page.getByRole("heading", { name: "Operational Profiles", exact: true })).toBeVisible();
      return actor;
    }

    async function command(page: Page, endpointSuffix: string, button: () => Promise<unknown>, expected = 200) {
      const pending = page.waitForResponse(
        (response) => response.url().endsWith(endpointSuffix) && ["POST", "PUT"].includes(response.request().method())
      );
      await button();
      const response = await pending;
      expect(response.status(), await response.text()).toBe(expected);
      return (await response.json()) as Record<string, unknown>;
    }

    const directId = fixture!.workspaces.direct.id;
    const route = `/workspaces/${directId}/operational-setup`;
    const runSuffix = Date.now();
    const profileCode = `O1A_BROWSER_${fixture!.tenant_slug}_${runSuffix}`;
    const periodCode = `O1A-2026-W43-${runSuffix}`;

    try {
      await expect
        .poll(
          async () => {
            try {
              return (await request.get(`${api}/api/v1/health/ready`, { timeout: 10_000 })).status();
            } catch {
              return 0;
            }
          },
          { timeout: 120_000, intervals: [2000, 5000, 10_000], message: "Isolated API readiness before any mutation" }
        )
        .toBe(200);
      await expect
        .poll(
          async () => {
            try {
              return (
                await request.get(process.env.E2E_BASE_URL || "http://127.0.0.1:5511", { timeout: 10_000 })
              ).status();
            } catch {
              return 0;
            }
          },
          {
            timeout: 120_000,
            intervals: [2000, 5000, 10_000],
            message: "Isolated Vite readiness before browser navigation",
          }
        )
        .toBe(200);
      const admin = await adminProfiles("admin");
      await admin.page.getByLabel("Código del perfil", { exact: true }).fill(profileCode);
      await admin.page.getByLabel("Nombre del perfil", { exact: true }).fill("O1A governed browser profile");
      const config = admin.page.getByRole("textbox", { name: "Configuración del perfil (JSON)", exact: true });
      await expect(config).toBeVisible();
      const content = JSON.parse(await config.inputValue({ timeout: 30_000 })) as Record<string, unknown>;
      content.effective_from = new Date(Date.now() - 60_000).toISOString();
      await config.fill(JSON.stringify(content, null, 2));
      const profile = await command(
        admin.page,
        "/api/v1/operational/admin/profiles",
        () => admin.page.getByRole("button", { name: "Crear perfil DRAFT", exact: true }).click(),
        201
      );
      evidence.profile_id = profile.id;
      evidence.profile_code = profileCode;
      mark("ADMIN_CREATE_PROFILE_UI");
      await admin.page.screenshot({ path: path.join(output, "01-admin-draft.png"), fullPage: true });

      const publisher = await adminProfiles("publisher");
      await publisher.page.getByRole("button", { name: `Ver perfil ${profileCode} revisión 1`, exact: true }).click();
      await publisher.page
        .getByLabel("Motivo de publicación / sucesor", { exact: true })
        .fill("Independent policy publication for O1A browser UAT");
      await command(publisher.page, `/api/v1/operational/admin/profiles/${profile.id}/publish`, () =>
        publisher.page.getByRole("button", { name: "Publicar perfil", exact: true }).click()
      );
      await expect(
        publisher.page.getByRole("textbox", { name: "Configuración del perfil (JSON)", exact: true })
      ).toBeDisabled();
      mark("ADMIN_INDEPENDENT_PUBLISH_UI_IMMUTABLE");
      await publisher.page.screenshot({ path: path.join(output, "02-admin-published.png"), fullPage: true });

      // Retried UAT runs preserve immutable fixture history. Select an already
      // authorized independent actor instead of deleting a previous binding or
      // disabling the configured separation-of-duties rule.
      const priorBindingResponse = await request.get(`${api}/api/v1/operational/projects/${directId}/binding`, {
        headers: { Authorization: `Bearer ${admin.session.access_token}` },
      });
      expect(priorBindingResponse.status()).toBe(200);
      const priorBinding = (await priorBindingResponse.json()) as { binding: { created_by: number } | null };
      const onboardingRole = priorBinding.binding
        ? priorBinding.binding.created_by === fixture!.users.admin.id
          ? "publisher"
          : "admin"
        : "project_admin";
      evidence.onboarding_actor = onboardingRole;
      const onboarding = await signedPage(onboardingRole, route);
      await expect(onboarding.page.getByRole("heading", { name: "Operational Setup", exact: true })).toBeVisible();
      await expect(
        onboarding.page
          .getByRole("region", { name: "Operational Setup", exact: true })
          .getByText(fixture!.workspaces.direct.external_key, { exact: true })
      ).toBeVisible();
      await expect(onboarding.page.getByText("DIRECT_INTERNAL", { exact: true }).first()).toBeVisible();
      await onboarding.page.getByText("Vinculación canónica ↔ legado · historial", { exact: true }).click();
      await onboarding.page
        .getByLabel("Legacy Project ID (opcional para reconciliar relación verificada)", { exact: true })
        .fill(String(fixture!.legacy_project_id));
      await onboarding.page
        .getByLabel("Motivo de reconciliación", { exact: true })
        .fill("Explicit independently verified canonical to legacy onboarding");
      await command(
        onboarding.page,
        `/api/v1/operational/projects/${directId}/binding/reconcile`,
        () => onboarding.page.getByRole("button", { name: "Reconciliar vinculación", exact: true }).click(),
        201
      );
      await expect(
        onboarding.page.locator("dd").filter({ hasText: new RegExp(`^${fixture!.legacy_project_id}$`) })
      ).toBeVisible();
      expect(directId).not.toBe(fixture!.legacy_project_id);
      mark("USER_CANONICAL_CONTEXT_AND_EXPLICIT_UNEQUAL_ID_BINDING_UI");
      await onboarding.page.screenshot({ path: path.join(output, "03-canonical-binding.png"), fullPage: true });

      const manager = await signedPage("manager", route);
      await expect(manager.page.getByRole("heading", { name: "Operational Setup", exact: true })).toBeVisible();
      await manager.page.getByText("Abrir periodo común de control", { exact: true }).click();
      await manager.page.getByLabel("Código del periodo", { exact: true }).fill(periodCode);
      await manager.page.getByLabel("Inicio", { exact: true }).fill("2026-10-19");
      await manager.page.getByLabel("Fin", { exact: true }).fill("2026-10-25");
      await manager.page.getByLabel("Cutoff ISO (con zona/offset)", { exact: true }).fill("2026-10-25T18:00:00-05:00");
      await manager.page.getByLabel("Zona horaria IANA", { exact: true }).fill("America/Bogota");
      await manager.page.getByLabel("P6 Data Date (independiente del cutoff)", { exact: true }).fill("2026-10-23");
      await manager.page
        .getByLabel("Motivo de apertura", { exact: true })
        .fill("Weekly O1A common control period opened through browser");
      const period = await command(
        manager.page,
        `/api/v1/operational/projects/${directId}/periods`,
        () => manager.page.getByRole("button", { name: "Abrir periodo", exact: true }).click(),
        201
      );
      evidence.period_id = period.id;
      mark("USER_OPEN_PERIOD_UI_EXPLICIT_TIMEZONE_CUTOFF_AND_INDEPENDENT_DATA_DATE");
      await manager.page
        .getByLabel("Motivo de transición / nueva revisión", { exact: true })
        .fill("Reconciled period header references for O1A UAT");
      await command(manager.page, `/api/v1/operational/projects/${directId}/periods/${period.id}/review`, () =>
        manager.page.getByRole("button", { name: `review ${periodCode} revision 1`, exact: true }).click()
      );
      await command(manager.page, `/api/v1/operational/projects/${directId}/periods/${period.id}/close`, () =>
        manager.page.getByRole("button", { name: `close ${periodCode} revision 1`, exact: true }).click()
      );
      await expect(
        manager.page.getByRole("button", { name: `publish ${periodCode} revision 1`, exact: true })
      ).toHaveCount(0);
      mark("USER_REVIEW_CLOSE_UI_AND_CLOSER_CANNOT_PUBLISH_SOD");

      const second = await signedPage("second_manager", route);
      await second.page
        .getByLabel("Motivo de transición / nueva revisión", { exact: true })
        .fill("Independent publication of immutable period header metadata");
      await command(second.page, `/api/v1/operational/projects/${directId}/periods/${period.id}/publish`, () =>
        second.page.getByRole("button", { name: `publish ${periodCode} revision 1`, exact: true }).click()
      );
      await expect(second.page.getByText("PUBLISHED", { exact: true })).toBeVisible();
      mark("USER_INDEPENDENT_PUBLISH_UI_HEADER_ONLY");
      await second.page.screenshot({ path: path.join(output, "04-published-period.png"), fullPage: true });
      await second.page
        .getByLabel("Motivo de transición / nueva revisión", { exact: true })
        .fill("Authorized late-data successor revision with immutable published parent");
      await command(
        second.page,
        `/api/v1/operational/projects/${directId}/periods/${period.id}/reopen`,
        () => second.page.getByRole("button", { name: `reopen ${periodCode} revision 1`, exact: true }).click(),
        200
      );
      await expect(second.page.getByText(`${periodCode} · r1`, { exact: true })).toBeVisible();
      await expect(second.page.getByText(`${periodCode} · r2`, { exact: false })).toBeVisible();
      await expect(second.page.getByText("PUBLISHED", { exact: true })).toBeVisible();
      mark("USER_REOPEN_REVISION_PRESERVES_PUBLISHED_HISTORY_UI");
      await second.page.screenshot({ path: path.join(output, "05-reopened-period-history.png"), fullPage: true });

      const executive = await signedPage("executive", route);
      await expect(executive.page.getByRole("heading", { name: "Operational Setup", exact: true })).toBeVisible();
      await expect(executive.page.getByRole("button", { name: "Abrir periodo", exact: true })).toHaveCount(0);
      await expect(executive.page.getByRole("button", { name: /^(review|close|publish|reopen) O1A-/ })).toHaveCount(0);
      await expect(executive.page.getByRole("button", { name: "Reconciliar vinculación", exact: true })).toHaveCount(0);
      mark("EXECUTIVE_READ_ONLY_UI");
      await executive.page.screenshot({ path: path.join(output, "06-executive-read-only.png"), fullPage: true });

      const auth = (session: Session) => ({
        Authorization: `Bearer ${session.access_token}`,
        "Idempotency-Key": `O1A-negative-${crypto.randomUUID()}`,
        "If-Match": '"1"',
      });
      const executiveWrite = await request.post(
        `${api}/api/v1/operational/projects/${directId}/periods/${period.id}/review`,
        { headers: auth(executive.session), data: { reason: "Forbidden executive mutation" } }
      );
      expect(executiveWrite.status()).toBe(403);
      const userAdmin = await request.get(`${api}/api/v1/operational/admin/profiles`, {
        headers: auth(manager.session),
      });
      expect(userAdmin.status()).toBe(403);
      const wrongProject = await request.get(
        `${api}/api/v1/operational/projects/${fixture!.workspaces.other_project.id}/context`,
        { headers: auth(manager.session) }
      );
      expect([403, 404]).toContain(wrongProject.status());
      const wrongTenant = await request.get(
        `${api}/api/v1/operational/projects/${fixture!.workspaces.foreign.id}/context`,
        { headers: auth(manager.session) }
      );
      expect([403, 404]).toContain(wrongTenant.status());
      const unauthorizedBind = await request.post(`${api}/api/v1/operational/projects/${directId}/binding/reconcile`, {
        headers: auth(executive.session),
        data: {
          legacy_project_id: fixture!.legacy_project_id,
          source: "CONTROLLED_RECONCILIATION",
          reason: "Forbidden executive reconciliation",
        },
      });
      expect(unauthorizedBind.status()).toBe(403);
      mark("DIRECT_API_EXECUTIVE_WRITE_ADMIN_POLICY_WRONG_PROJECT_TENANT_AND_BINDING_DENIED");

      const executiveApp = await signedPage("executive", "/app");
      await expect(executiveApp.page.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true })).toBeDisabled();
      mark("USER_ADMIN_MODE_ENTRY_DISABLED_UI");

      for (const model of ["contractor", "owner"]) {
        const actor = await signedPage("admin", `/workspaces/${fixture!.workspaces[model].id}/operational-setup`);
        await expect(actor.page.getByRole("heading", { name: "Operational Setup", exact: true })).toBeVisible();
        await expect(
          actor.page.getByText(model === "owner" ? "CAPITAL_OWNER" : "CONTRACTOR_DELIVERY", { exact: true }).first()
        ).toBeVisible();
        if (model === "owner")
          await expect(
            actor.page.getByText("CAPITAL_OWNER_CURRENT_INVESTMENT_AUTHORIZATION_REQUIRED", { exact: true })
          ).toBeVisible();
        await actor.page.screenshot({ path: path.join(output, `07-${model}-authorization.png`), fullPage: true });
      }
      mark("THREE_GOVERNANCE_ROUTES_VISIBLE_UI");

      const observations = evidence.local_observations as Array<Record<string, unknown>>;
      for (let sample = 0; sample < 5; sample += 1) {
        for (const [label, suffix] of [
          ["context_GET", "context"],
          ["binding_lookup", "binding"],
          ["authorization_resolution", "authorization"],
          ["period_list", "periods"],
          ["current_period_context", "context"],
        ]) {
          const started = performance.now();
          const result = await request.get(`${api}/api/v1/operational/projects/${directId}/${suffix}`, {
            headers: auth(manager.session),
          });
          await result.body();
          expect(result.status()).toBe(200);
          observations.push({
            label,
            sample: sample + 1,
            elapsed_ms: Math.round((performance.now() - started) * 100) / 100,
            status: result.status(),
            caveat: "Local isolated fixture, not a load test or production SLA.",
          });
        }
      }
      mark("LOCAL_NON_LOAD_OBSERVATIONS_FIVE_QUERY_PATHS");
      evidence.result = "PASS";
    } catch (error) {
      evidence.result = "FAIL";
      evidence.error = error instanceof Error ? error.message : String(error);
      for (let i = 0; i < pages.length; i += 1)
        await pages[i]
          .screenshot({ path: path.join(output, `failure-page-${i + 1}.png`), fullPage: true })
          .catch(() => undefined);
      throw error;
    } finally {
      evidence.finished_at = new Date().toISOString();
      writeFileSync(path.join(output, "browser-uat.json"), JSON.stringify(evidence, null, 2));
      for (const page of pages) await page.context().close();
    }
  });
});
