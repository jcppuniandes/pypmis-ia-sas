import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const manifest = process.env.E2E_O1BB_FIXTURE;
const fixture = manifest ? JSON.parse(readFileSync(manifest, "utf8")) : null;
const api = process.env.E2E_API_URL || "http://127.0.0.1:8853";
const output = path.resolve(process.env.E2E_O1BB_OUTPUT || "../outputs/.qa/wave-o1bb-20261020/chromium");
const reason = "Isolated real Schedule browser release validation";

test.describe("O1B-B actual Schedule lifecycle and manual P6 exchange", () => {
  test.skip(!fixture, "Requires dedicated PostgreSQL actors and actual Scope prerequisites");
  test.use({ actionTimeout: 35_000, navigationTimeout: 90_000 });
  test("ADMIN configuration and independent USER acceptance and baseline", async ({ browser, request }) => {
    test.setTimeout(600_000);
    expect(api).toMatch(/^http:\/\/(127\.0\.0\.1|localhost):8853$/);
    mkdirSync(output, { recursive: true });
    const checks: Array<{ code: string; result: string }> = [];
    const observations: Array<{ label: string; elapsed_ms: number; status: number }> = [];
    const browserErrors: string[] = [];
    const pages: Page[] = [];
    const project = fixture.project_workspace_id;
    const route = `/workspaces/${project}/schedule-manager`;
    const root = `${api}/api/v1/schedule/projects/${project}`;
    const run = Date.now();
    const mark = (code: string) => checks.push({ code, result: "PASS" });
    async function actor(role: string, target: string) {
      const user = fixture.users[role];
      const login = await request.post(`${api}/api/v1/auth/login`, {
        timeout: 120_000, // Cold ORM/module loading is infrastructure startup, not a 35s product SLA.
        data: { email: user.email, tenant_id: user.tenant_id, password: "O1bb-disposable-only!" },
      });
      expect(login.status(), await login.text()).toBe(200);
      const session = await login.json();
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
      page.on("pageerror", (error) => browserErrors.push(String(error)));
      await page.goto(target);
      return { page, context, token: String(session.access_token) };
    }
    async function command(page: Page, suffix: string, action: () => Promise<unknown>, status = 200) {
      const pending = page.waitForResponse(
        (r) => r.url().endsWith(suffix) && ["POST", "PUT"].includes(r.request().method())
      );
      await action();
      const response = await pending;
      expect(response.status(), await response.text()).toBe(status);
      await expect(
        page.locator('[aria-label="Schedule Manager"], [aria-label="Schedule Profiles ADMIN"]').first()
      ).toHaveAttribute("aria-busy", "false");
      return response.json();
    }
    async function admin(role: string) {
      const user = await actor(role, "/app");
      await user.page.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }).click();
      for (const name of ["Platform Administration", "Process Configuration"]) {
        const button = user.page.getByRole("button", { name, exact: true });
        if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
      }
      await user.page.getByRole("button", { name: "Process & Operational Configuration", exact: true }).click();
      await user.page.getByRole("button", { name: "Schedule Profiles", exact: true }).click();
      await expect(user.page.getByRole("heading", { name: "Schedule Profiles", exact: true })).toBeVisible();
      return user;
    }
    async function tab(page: Page, name: string) {
      await page
        .getByRole("navigation", { name: "Schedule Manager submodules" })
        .getByRole("button", { name, exact: true })
        .click();
    }
    async function selectRegister(page: Page, registerId: number, versionId?: number) {
      await page.getByLabel("Schedule Register activo", { exact: true }).selectOption(String(registerId));
      if (versionId) await page.getByLabel("Schedule Version activa", { exact: true }).selectOption(String(versionId));
    }
    async function mapAll(page: Page, snapshot: any) {
      for (const [label, collection, kind] of [
        ["WBS", "wbs", "WBS"],
        ["Activities", "activities", "Activity"],
      ] as const) {
        await tab(page, label);
        for (const object of snapshot[collection]) {
          await page.getByRole("button", { name: `Inspeccionar ${kind} ${object.code}`, exact: true }).click();
          for (const plan of fixture.plan_items)
            await page.getByLabel(`Mapear Plan Item ${plan.code}`, { exact: true }).check();
          await page.getByLabel("Motivo mapping", { exact: true }).fill(reason);
          await command(
            page,
            "/mappings",
            () => page.getByRole("button", { name: "Guardar mapping Schedule M:N", exact: true }).click(),
            201
          );
        }
      }
    }
    async function validateReviewAccept(page: Page, role: string) {
      await tab(page, "Import / Export");
      await page.getByLabel("Motivo revisión Schedule", { exact: true }).fill(reason);
      if (role === "admin") {
        await command(page, "/validate", () =>
          page.getByRole("button", { name: "Validar Schedule Version", exact: true }).click()
        );
      } else {
        await command(page, "/review", () =>
          page.getByRole("button", { name: "Revisar Schedule Version", exact: true }).click()
        );
        await command(page, "/accept", () =>
          page.getByRole("button", { name: "Aceptar Schedule Current", exact: true }).click()
        );
      }
    }
    try {
      const creator = await admin("admin");
      const profileResponse = await request.get(`${api}/api/v1/schedule/admin/profiles`, {
        headers: { Authorization: `Bearer ${creator.token}` },
      });
      expect(profileResponse.status()).toBe(200);
      const profiles = await profileResponse.json();
      const publishedProfile = profiles.items.find(
        (profile: any) =>
          profile.status.toUpperCase() === "PUBLISHED" && profile.name === "Schedule isolated governed source policy"
      );
      const code = publishedProfile?.code ?? `O1BB-UI-${run}`;
      if (!publishedProfile) {
        await creator.page.getByLabel("Schedule Profile Code", { exact: true }).fill(code);
        await creator.page
          .getByLabel("Schedule Profile Name", { exact: true })
          .fill("Schedule isolated governed source policy");
        const config = JSON.parse(
          await creator.page.getByLabel("Schedule Profile configuration JSON", { exact: true }).inputValue()
        );
        config.quality_thresholds.external_links = "WARN"; // Explicit UAT policy; never a product-default relaxation.
        await creator.page
          .getByLabel("Schedule Profile configuration JSON", { exact: true })
          .fill(JSON.stringify(config));
        await command(
          creator.page,
          "/schedule/admin/profiles",
          () => creator.page.getByRole("button", { name: "Crear Schedule Profile DRAFT", exact: true }).click(),
          201
        );
      } else {
        expect(publishedProfile.content_json.quality_thresholds.external_links).toBe("WARN");
      }
      const publisher = await admin("publisher");
      await publisher.page.getByRole("button", { name: `Ver Schedule Profile ${code}`, exact: true }).click();
      if (!publishedProfile) {
        await publisher.page.getByLabel("Motivo Schedule Profile", { exact: true }).fill(reason);
        await command(publisher.page, "/publish", () =>
          publisher.page.getByRole("button", { name: "Publicar Schedule Profile", exact: true }).click()
        );
        mark("ADMIN_PUBLISHED_SCHEDULE_POLICY_INDEPENDENT_ACTOR");
      } else {
        await expect(
          publisher.page.getByRole("button", { name: "Publicar Schedule Profile", exact: true })
        ).toHaveCount(0);
        mark("ADMIN_PROFILE_REUSED");
      }

      await creator.page.goto(route);
      await expect(creator.page.getByRole("heading", { name: "Schedule Manager", exact: true })).toBeVisible();
      await creator.page.getByLabel("Schedule Code", { exact: true }).fill(`SCH-UI-${run}`);
      await creator.page
        .getByLabel("Schedule Name", { exact: true })
        .fill("Actual XML and XER governed control schedule");
      await creator.page.getByLabel("Schedule Type", { exact: true }).selectOption("CONTROL");
      await creator.page.getByLabel("Motivo Schedule Register", { exact: true }).fill(reason);
      const register = await command(
        creator.page,
        "/registers",
        () => creator.page.getByRole("button", { name: "Crear Schedule Register", exact: true }).click(),
        201
      );
      mark("USER_CANONICAL_SCHEDULE_REGISTER_CREATED");
      await tab(creator.page, "Import / Export");
      await creator.page
        .getByLabel("Archivo P6 XML o XER", { exact: true })
        .setInputFiles(path.resolve("../backend/tests/fixtures/schedule-foundation-p6.xml"));
      await creator.page.getByLabel("Tipo import Schedule", { exact: true }).selectOption("INITIAL");
      await creator.page.getByLabel("Motivo import Schedule", { exact: true }).fill(reason);
      const initial = await command(
        creator.page,
        "/imports",
        () => creator.page.getByRole("button", { name: "Importar P6 a staging", exact: true }).click(),
        201
      );
      expect(initial.status).toBe("STAGED");
      await expect(creator.page.getByText(`Data Date ${initial.data_date}`, { exact: true })).toBeVisible();
      mark("XML_REAL_UPLOAD_STAGING_VALIDATION_DIFF_DATA_DATE_SOURCE_HASH");
      await mapAll(creator.page, initial.snapshot_json);
      mark("WBS_TREE_AND_ACTIVITY_PLAN_MANY_TO_MANY_SCOPE_TRACEABILITY");
      await tab(creator.page, "Calendars");
      const calendarsTable = creator.page.getByRole("table", { name: "Schedule Calendars", exact: true });
      await expect(calendarsTable.getByRole("cell", { name: "10", exact: true })).toHaveCount(2);
      await expect(calendarsTable.getByRole("cell", { name: "6", exact: true })).toHaveCount(1);
      await expect(calendarsTable).toContainText("2026-12-25");
      await tab(creator.page, "Relationships");
      const relationshipsTable = creator.page.getByRole("table", { name: "Schedule Relationships", exact: true });
      for (const relation of ["FS", "SS", "FF", "SF"])
        await expect(relationshipsTable.getByRole("cell", { name: relation, exact: true }).first()).toBeVisible();
      await expect(relationshipsTable.getByRole("cell", { name: "-1", exact: true })).toBeVisible();
      await tab(creator.page, "Codes & Constraints");
      await expect(creator.page.getByRole("table", { name: "Schedule Constraints", exact: true })).toContainText(
        "Mandatory Finish"
      );
      await expect(creator.page.getByRole("table", { name: "Activity Codes", exact: true })).toContainText("CIVIL");
      const healthQuery = creator.page.waitForResponse(
        (response) => response.url().endsWith(`/versions/${initial.id}/health`) && response.request().method() === "GET"
      );
      await tab(creator.page, "Schedule Health");
      expect((await healthQuery).status()).toBe(200);
      await expect(creator.page.getByText(/quality_is_not_cpm/)).toBeVisible();
      await expect(creator.page.locator(".scheduleDetails pre").first()).toContainText('"can_accept": true');
      await creator.page.screenshot({ path: path.join(output, "schedule-health.png"), fullPage: true });
      mark("CALENDARS_SIGNED_LAGS_FOUR_RELATIONS_CONSTRAINTS_CODES_HEALTH_VISIBLE");
      await validateReviewAccept(creator.page, "admin");
      await publisher.page.goto(route);
      await selectRegister(publisher.page, register.id, initial.id);
      await validateReviewAccept(publisher.page, "publisher");
      mark("CURRENT_ACCEPTED_BY_INDEPENDENT_REVIEWER");
      await creator.page.reload(); // The independent reviewer changed the version in another browser session.
      await selectRegister(creator.page, register.id, initial.id);
      await tab(creator.page, "Baselines");
      await creator.page.getByLabel("Baseline Type", { exact: true }).selectOption("CONTROL");
      await creator.page.getByLabel("Motivo Baseline Schedule", { exact: true }).fill(reason);
      await command(
        creator.page,
        "/baselines",
        () => creator.page.getByRole("button", { name: "Preparar Schedule Baseline Candidate", exact: true }).click(),
        201
      );
      await creator.page.getByLabel("Motivo transición Baseline", { exact: true }).fill(reason);
      await command(creator.page, "/submit", () =>
        creator.page.getByRole("button", { name: /Enviar Schedule Baseline #/ }).click()
      );
      await publisher.page.reload();
      await selectRegister(publisher.page, register.id, initial.id);
      await tab(publisher.page, "Baselines");
      await publisher.page.getByLabel("Motivo transición Baseline", { exact: true }).fill(reason);
      await command(publisher.page, "/review", () =>
        publisher.page.getByRole("button", { name: /Revisar Schedule Baseline #/ }).click()
      );
      const approved = await command(publisher.page, "/approve", () =>
        publisher.page.getByRole("button", { name: /Aprobar Schedule Baseline #/ }).click()
      );
      mark("BASELINE_SUBMITTED_REVIEWED_AND_INDEPENDENTLY_APPROVED");
      await tab(publisher.page, "Import / Export");
      await publisher.page.getByLabel("Motivo export Schedule", { exact: true }).fill(reason);
      const exported = await command(
        publisher.page,
        "/exports",
        () => publisher.page.getByRole("button", { name: "Generar P6 XML y manifest", exact: true }).click(),
        201
      );
      const download = publisher.page.waitForEvent("download");
      await publisher.page.getByRole("button", { name: `Descargar P6 XML #${exported.id}`, exact: true }).click();
      const downloaded = await download;
      const saved = path.join(output, "actual-export.xml");
      await downloaded.saveAs(saved);
      expect(readFileSync(saved, "utf8")).toContain("APIBusinessObjects");
      expect(exported.manifest_json.full_p6_parity).toBe(false);
      const manifestDownload = publisher.page.waitForEvent("download");
      await publisher.page.getByRole("button", { name: `Descargar manifest #${exported.id}`, exact: true }).click();
      const savedManifest = path.join(output, "actual-export-manifest.json");
      await (await manifestDownload).saveAs(savedManifest);
      expect(JSON.parse(readFileSync(savedManifest, "utf8"))).toEqual(exported.manifest_json);
      mark("ACTUAL_XML_DOWNLOAD_MANIFEST_NO_FULL_P6_PARITY_CLAIM");

      await creator.page.reload();
      await selectRegister(creator.page, register.id, initial.id);
      await tab(creator.page, "Import / Export");
      await creator.page
        .getByLabel("Archivo P6 XML o XER", { exact: true })
        .setInputFiles(path.resolve("../backend/tests/fixtures/schedule-foundation-p6.xer"));
      await creator.page.getByLabel("Tipo import Schedule", { exact: true }).selectOption("UPDATE");
      await creator.page.getByLabel("Motivo import Schedule", { exact: true }).fill(reason);
      const xer = await command(
        creator.page,
        "/imports",
        () => creator.page.getByRole("button", { name: "Importar P6 a staging", exact: true }).click(),
        201
      );
      expect(xer.status).toBe("STAGED");
      await creator.page.getByLabel("Motivo revisión Schedule", { exact: true }).fill(reason);
      await command(creator.page, "/reject", () =>
        creator.page.getByRole("button", { name: "Rechazar Schedule Version", exact: true }).click()
      );
      mark("NATIVE_XER_REAL_UPLOAD_RECONCILIATION_AND_CONTROLLED_REJECTION");

      const changed = readFileSync(saved, "utf8")
        .replaceAll("2026-10-20T08:00:00", "2026-10-27T08:00:00")
        .replace("<RemainingDuration>20</RemainingDuration>", "<RemainingDuration>17</RemainingDuration>");
      const updatedPath = path.join(output, "updated-exchange.xml");
      writeFileSync(updatedPath, changed);
      await creator.page.getByLabel("Schedule Version activa", { exact: true }).selectOption(String(initial.id));
      await creator.page.getByLabel("Archivo P6 XML o XER", { exact: true }).setInputFiles(updatedPath);
      await creator.page.getByLabel("Motivo import Schedule", { exact: true }).fill(reason);
      const updated = await command(
        creator.page,
        "/imports",
        () => creator.page.getByRole("button", { name: "Importar P6 a staging", exact: true }).click(),
        201
      );
      expect(updated.diff_json.data_date.changed).toBe(true);
      await mapAll(creator.page, updated.snapshot_json);
      await validateReviewAccept(creator.page, "admin");
      await publisher.page.reload();
      await selectRegister(publisher.page, register.id, updated.id);
      await publisher.page.getByLabel("Schedule Version activa", { exact: true }).selectOption(String(updated.id));
      await validateReviewAccept(publisher.page, "publisher");
      await tab(publisher.page, "Baselines");
      await publisher.page.screenshot({ path: path.join(output, "baseline-current-distinct.png"), fullPage: true });
      const overviewResponse = await request.get(`${root}/overview`, {
        headers: { Authorization: `Bearer ${publisher.token}` },
      });
      expect(overviewResponse.status()).toBe(200);
      const overview = await overviewResponse.json();
      const current = overview.registers.find((row: any) => row.id === register.id);
      const baseline = overview.baselines.find((row: any) => row.id === approved.id);
      expect(current.current_version_id).toBe(updated.id);
      expect(current.baseline_version_id).toBe(initial.id);
      expect(baseline.content_hash).toBe(approved.content_hash);
      expect(overview.versions.find((row: any) => row.id === initial.id).status).toBe("SUPERSEDED");
      expect(overview.versions.find((row: any) => row.id === xer.id).status).toBe("REJECTED");
      mark("XML_REIMPORT_UPDATED_CURRENT_PRESERVES_IMMUTABLE_BASELINE_AND_HISTORY");
      const reader = await actor("executive", route);
      await selectRegister(reader.page, register.id, updated.id);
      await expect(reader.page.getByRole("table", { name: "Schedule Register", exact: true })).toBeVisible();
      await expect(reader.page.getByRole("button", { name: "Crear Schedule Register", exact: true })).toHaveCount(0);
      await tab(reader.page, "Activities");
      await reader.page.getByRole("button", { name: "Inspeccionar Activity A100", exact: true }).click();
      await expect(reader.page.getByRole("checkbox")).toHaveCount(0);
      await tab(reader.page, "Import / Export");
      await expect(reader.page.getByLabel("Archivo P6 XML o XER", { exact: true })).toHaveCount(0);
      await expect(reader.page.getByRole("button", { name: "Aceptar Schedule Current", exact: true })).toHaveCount(0);
      await reader.page.screenshot({ path: path.join(output, "schedule-reader-readonly.png"), fullPage: true });
      mark("EXECUTIVE_READONLY_ROLE_SEES_SCHEDULE_WITHOUT_WRITER_CONTROLS");
      await reader.context.close();
      for (const [label, suffix] of [
        ["schedule_register_load", "/registers"],
        ["wbs_tree_load", `/versions/${updated.id}/wbs`],
        ["activity_list", `/versions/${updated.id}/activities`],
        ["mapping_query", `/versions/${updated.id}/mappings`],
        ["schedule_health_query", `/versions/${updated.id}/health`],
      ]) {
        const started = performance.now();
        const response = await request.get(root + suffix, { headers: { Authorization: `Bearer ${publisher.token}` } });
        expect(response.status()).toBe(200);
        observations.push({
          label,
          elapsed_ms: Number((performance.now() - started).toFixed(2)),
          status: response.status(),
        });
      }
      expect(browserErrors).toEqual([]);
      writeFileSync(
        path.join(output, "browser-uat.json"),
        JSON.stringify(
          {
            result: "PASS",
            checks,
            observations,
            browser_errors: browserErrors,
            completed_at: new Date().toISOString(),
            project_workspace_id: project,
            tenant_id: fixture.tenant_id,
            register_id: register.id,
            initial_version_id: initial.id,
            updated_version_id: updated.id,
            baseline_id: baseline.id,
            baseline_hash: baseline.content_hash,
            authentication: "Actual login, API and PostgreSQL; no response mocks",
            p6_application_roundtrip_verified: false,
          },
          null,
          2
        )
      );
      await creator.context.close();
      await publisher.context.close();
    } catch (error) {
      for (const [index, page] of pages.entries()) {
        if (!page.isClosed())
          await page
            .screenshot({ path: path.join(output, `failure-page-${index}.png`), fullPage: true })
            .catch(() => undefined);
      }
      writeFileSync(
        path.join(output, "browser-uat.json"),
        JSON.stringify(
          { result: "FAIL", checks, observations, browser_errors: browserErrors, error: String(error) },
          null,
          2
        )
      );
      throw error;
    }
  });
});
