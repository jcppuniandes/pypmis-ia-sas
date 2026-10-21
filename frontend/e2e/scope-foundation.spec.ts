import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

type Fixture = {
  tenant_id: number;
  users: Record<string, { id: number; email: string; tenant_id: number }>;
  workspaces: Record<string, { id: number; name: string }>;
  fixture_scope: string;
};
const fixturePath = process.env.E2E_O1BA_FIXTURE;
const fixture = fixturePath ? (JSON.parse(readFileSync(fixturePath, "utf8")) as Fixture) : null;
const api = process.env.E2E_API_URL || "http://127.0.0.1:8852";
const output = path.resolve(process.env.E2E_O1BA_OUTPUT || "../outputs/.qa/wave-o1ba-20261020/chromium");
const sources = path.resolve("../outputs/.qa/wave-o1ba-20261020/fixtures");

test.describe("O1B-A real Scope sources and controlled execution decomposition", () => {
  test.skip(!fixture, "Requires explicitly provisioned isolated PostgreSQL actors");
  test.use({ actionTimeout: 35_000, navigationTimeout: 90_000 });
  test("ADMIN and USER full Scope foundation with immutable original IFC", async ({ browser, request }) => {
    test.setTimeout(600_000);
    expect(api).toMatch(/^http:\/\/(127\.0\.0\.1|localhost):8852$/);
    mkdirSync(output, { recursive: true });
    const checks: Array<{ code: string; result: string }> = [];
    const observations: Array<{ label: string; elapsed_ms: number; status: number }> = [];
    const evidence = {
      started_at: new Date().toISOString(),
      fixture_scope: fixture!.fixture_scope,
      authentication: "Actual tenant-specific API login and legitimate issued browser session; no response mocks",
      checks,
      observations,
    };
    const project = fixture!.workspaces.direct.id;
    const root = `${api}/api/v1/scope/projects/${project}`;
    const route = `/workspaces/${project}/scope-manager`;
    const reason = "Controlled isolated O1B-A browser validation";
    const mark = (code: string) => checks.push({ code, result: "PASS" });
    const run = Date.now();

    async function actor(role: string, target: string) {
      const user = fixture!.users[role];
      const response = await request.post(`${api}/api/v1/auth/login`, {
        data: { email: user.email, tenant_id: user.tenant_id, password: "O1ba-disposable-only!" },
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
      await page.goto(target);
      return { page, context, token: String(session.access_token) };
    }
    async function command(page: Page, suffix: string, action: () => Promise<unknown>, expected = 200) {
      const started = performance.now();
      const pending = page.waitForResponse(
        (response) => response.url().endsWith(suffix) && ["POST", "PUT"].includes(response.request().method())
      );
      await action();
      const response = await pending;
      expect(response.status(), await response.text()).toBe(expected);
      if (suffix === "/plan-items/transform" && response.request().postDataJSON().operation === "GROUP") {
        observations.push({
          label: "plan_item_grouping",
          elapsed_ms: Number((performance.now() - started).toFixed(2)),
          status: response.status(),
        });
      }
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
      await user.page.getByRole("button", { name: "Scope Profiles", exact: true }).click();
      await expect(user.page.getByRole("heading", { name: "Scope Profiles", exact: true })).toBeVisible();
      return user;
    }
    try {
      const creator = await admin("admin");
      const profileCode = `O1BA-BROWSER-${run}`;
      await creator.page.getByLabel("Scope Profile Code", { exact: true }).fill(profileCode);
      await creator.page
        .getByLabel("Scope Profile Name", { exact: true })
        .fill("Scope UAT independent governed profile");
      const profile = await command(
        creator.page,
        "/scope/admin/profiles",
        () => creator.page.getByRole("button", { name: "Crear Scope Profile DRAFT", exact: true }).click(),
        201
      );
      mark("ADMIN_PROFILE_CREATED_UI");
      const publisher = await admin("publisher");
      await publisher.page.getByRole("button", { name: `Ver Scope Profile ${profileCode}`, exact: true }).click();
      await publisher.page.getByLabel("Motivo Scope Profile", { exact: true }).fill(reason);
      await command(publisher.page, `/admin/profiles/${profile.id}/publish`, () =>
        publisher.page.getByRole("button", { name: "Publicar Scope Profile", exact: true }).click()
      );
      mark("ADMIN_INDEPENDENT_PROFILE_PUBLICATION_UI");

      const editor = await actor("admin", route);
      await expect(editor.page.getByRole("heading", { name: "Scope Manager", exact: true })).toBeVisible();
      await editor.page.getByLabel("Código del modelo", { exact: true }).fill(`MODEL-${run}`);
      await editor.page.getByLabel("Archivo IFC", { exact: true }).setInputFiles(path.join(sources, "real-scope.ifc"));
      await editor.page.getByLabel("Motivo de importación", { exact: true }).fill(reason);
      const model = await command(
        editor.page,
        "/models",
        () => editor.page.getByRole("button", { name: "Importar IFC a staging", exact: true }).click(),
        201
      );
      expect(model.validation_summary.can_accept).toBe(true);
      await command(editor.page, `/models/${model.id}/review`, () =>
        editor.page.getByRole("button", { name: "Revisar versión", exact: true }).click()
      );
      const reviewer = await actor("publisher", route);
      await reviewer.page.getByLabel("Motivo de revisión / aceptación", { exact: true }).fill(reason);
      await command(reviewer.page, `/models/${model.id}/accept`, () =>
        reviewer.page.getByRole("button", { name: "Aceptar versión", exact: true }).click()
      );
      await editor.page.getByRole("button", { name: "Actualizar", exact: true }).click();
      await expect(editor.page.getByLabel("Modelo y versión")).toContainText("ACCEPTED");
      await expect(editor.page.getByLabel("IFC viewer data basis")).toContainText(/[1-9]\d* mesh\(es\) \/ web-ifc/, {
        timeout: 90_000,
      });
      mark("USER_REAL_WEBIFC_GEOMETRY_RENDERED_FROM_CANONICAL_SOURCE");
      const wall = editor.page.getByRole("row").filter({ hasText: "Wall 1" });
      await wall.getByRole("button", { name: "Inspeccionar", exact: true }).click();
      await expect(editor.page.getByText("Properties · Wall 1", { exact: true })).toBeVisible();
      await editor.page.getByLabel("Seleccionar BIM Wall 1", { exact: true }).check();
      await editor.page.getByLabel("Seleccionar BIM Wall 2", { exact: true }).check();
      await editor.page.getByLabel("Scope Code desde BIM", { exact: true }).fill(`BIM-${run}`);
      await editor.page.getByLabel("Scope Name desde BIM", { exact: true }).fill("Wall installation governed Scope");
      await editor.page.getByLabel("Cantidad Scope", { exact: true }).fill("10");
      await editor.page.getByRole("combobox", { name: /^Medición fuente IFC/ }).selectOption("NetVolume");
      await editor.page.getByLabel("Unidad Scope", { exact: true }).fill("m3");
      const bimScope = await command(
        editor.page,
        "/items",
        () => editor.page.getByRole("button", { name: "Crear Scope desde selección BIM", exact: true }).click(),
        201
      );
      expect(bimScope.model_object_ids).toHaveLength(2);
      await editor.page.screenshot({ path: path.join(output, "01-model-and-properties.png"), fullPage: true });
      mark("USER_IFC_STAGING_REVIEW_ACCEPT_PROPERTIES_AND_SCOPE_MN_UI");

      await editor.page.getByRole("button", { name: "Scope Items", exact: true }).click();
      await editor.page
        .getByLabel("Archivo Excel Scope", { exact: true })
        .setInputFiles(path.join(sources, "scope-items.xlsx"));
      await editor.page.getByLabel("Motivo Excel", { exact: true }).fill(reason);
      const imported = await command(
        editor.page,
        "/excel-imports",
        () => editor.page.getByRole("button", { name: "Validar Excel y ver staging", exact: true }).click(),
        201
      );
      expect(imported.validation_summary.can_accept).toBe(true);
      await command(editor.page, `/excel-imports/${imported.id}/candidate`, () =>
        editor.page.getByRole("button", { name: "Crear candidato desde Excel", exact: true }).click()
      );
      const manualCode = `MAN-${run}`;
      await editor.page.getByLabel("Scope Code", { exact: true }).fill(manualCode);
      await editor.page.getByLabel("Scope Name", { exact: true }).fill("Manual temporary Scope");
      await editor.page.getByRole("combobox", { name: /^Scope Nature/ }).selectOption("TEMPORARY");
      await editor.page.getByLabel("Quantity", { exact: true }).fill("2");
      await editor.page.getByLabel("Unit", { exact: true }).fill("ea");
      await editor.page.getByLabel("Motivo Scope", { exact: true }).fill(reason);
      await command(
        editor.page,
        "/items",
        () => editor.page.getByRole("button", { name: "Crear Scope manual", exact: true }).click(),
        201
      );
      await editor.page.getByLabel("Revision Code", { exact: true }).fill(`REV-${run}`);
      await editor.page.getByLabel("Motivo revisión", { exact: true }).fill(reason);
      const revision = await command(
        editor.page,
        "/revisions",
        () => editor.page.getByRole("button", { name: "Preparar Scope Revision", exact: true }).click(),
        201
      );
      await command(editor.page, `/revisions/${revision.id}/submit`, () =>
        editor.page.getByRole("button", { name: "Enviar revisión", exact: true }).click()
      );
      await reviewer.page.getByRole("button", { name: "Actualizar", exact: true }).click();
      await reviewer.page.getByRole("button", { name: "Scope Items", exact: true }).click();
      await reviewer.page.getByLabel("Motivo revisión", { exact: true }).fill(reason);
      await command(reviewer.page, `/revisions/${revision.id}/review`, () =>
        reviewer.page.getByRole("button", { name: "Revisar Scope", exact: true }).click()
      );
      await command(reviewer.page, `/revisions/${revision.id}/approve`, () =>
        reviewer.page.getByRole("button", { name: "Aprobar Scope Baseline", exact: true }).click()
      );
      await editor.page.getByRole("button", { name: "Actualizar", exact: true }).click();
      await editor.page.screenshot({ path: path.join(output, "02-scope-baseline.png"), fullPage: true });
      mark("USER_NATIVE_EXCEL_CANDIDATE_MANUAL_NATURES_AND_APPROVED_BASELINE_UI");

      await editor.page.getByRole("button", { name: "Strategy & Path of Execution", exact: true }).click();
      await editor.page.getByLabel("Strategy Code", { exact: true }).fill(`STR-${run}`);
      await editor.page.getByLabel("Strategy Name", { exact: true }).fill("Area-based controlled execution");
      await editor.page.getByLabel("Motivo estrategia", { exact: true }).fill(reason);
      await editor.page.getByLabel("Path Code", { exact: true }).fill("NORTH");
      await editor.page.getByLabel("Path Name", { exact: true }).fill("North ordered execution");
      await editor.page.getByRole("button", { name: "Agregar Execution Path", exact: true }).click();
      await editor.page.getByRole("combobox", { name: /^Regla de segmentación/ }).selectOption("AREA");
      await editor.page.getByRole("button", { name: "Agregar regla", exact: true }).click();
      await command(
        editor.page,
        "/strategies",
        () => editor.page.getByRole("button", { name: "Crear Execution Strategy DRAFT", exact: true }).click(),
        201
      );
      await editor.page.screenshot({ path: path.join(output, "03-execution-strategy.png"), fullPage: true });
      mark("USER_EXECUTION_STRATEGY_PATH_AND_SEGMENTATION_RULE_UI");

      await editor.page.getByRole("button", { name: "Plan Items", exact: true }).click();
      await editor.page.getByLabel("Motivo Plan Item", { exact: true }).fill(reason);
      let plans = [];
      for (const [suffix, quantity] of [
        ["A", "4"],
        ["B", "6"],
      ]) {
        await editor.page.getByLabel("Plan Code", { exact: true }).fill(`PLAN-${run}-${suffix}`);
        await editor.page.getByLabel("Plan Name", { exact: true }).fill(`Wall package ${suffix}`);
        await editor.page.getByLabel(`Asignar cantidad BIM-${run}`, { exact: true }).fill(quantity);
        plans.push(
          await command(
            editor.page,
            "/plan-items",
            () => editor.page.getByRole("button", { name: "Crear Plan Item", exact: true }).click(),
            201
          )
        );
      }
      for (const [operation, amounts] of [
        ["GROUP", [10]],
        ["SPLIT", [5, 5]],
        ["RECOMPOSE", [10]],
      ] as const) {
        for (const checkbox of await editor.page.getByRole("checkbox", { name: /^Seleccionar Plan / }).all())
          await checkbox.uncheck();
        for (const plan of plans)
          await editor.page.getByLabel(`Seleccionar Plan ${plan.code}`, { exact: true }).check();
        await editor.page.getByRole("combobox", { name: /^Operación/ }).selectOption(operation);
        await editor.page.getByLabel("Motivo transformación", { exact: true }).fill(reason);
        await editor.page.getByLabel("Salidas de transformación JSON", { exact: true }).fill(
          JSON.stringify(
            amounts.map((amount, index) => ({
              code: `${operation}-${run}-${index}`,
              name: `${operation} package ${index}`,
              reason,
              model_object_ids: bimScope.model_object_ids,
              allocations: [{ scope_item_id: bimScope.id, quantity: amount, unit: "m3" }],
            }))
          )
        );
        const result = await command(
          editor.page,
          "/plan-items/transform",
          () => editor.page.getByRole("button", { name: "Aplicar transformación Plan Items", exact: true }).click(),
          201
        );
        plans = result.items;
      }
      for (const checkbox of await editor.page.getByRole("checkbox", { name: /^Seleccionar Plan / }).all())
        await checkbox.uncheck();
      await editor.page.getByLabel(`Seleccionar Plan ${plans[0].code}`, { exact: true }).check();
      await editor.page.getByLabel("Motivo representación derivada", { exact: true }).fill(reason);
      const derived = await command(
        editor.page,
        "/derived-models",
        () => editor.page.getByRole("button", { name: "Crear Derived 3D subset", exact: true }).click(),
        201
      );
      expect(derived.snapshot_json.physical_geometry_modified).toBe(false);
      await expect(editor.page.locator("canvas").first()).toBeVisible();
      await expect(editor.page.getByLabel("IFC viewer data basis")).toContainText(/[1-9]\d* mesh\(es\) \/ web-ifc/, {
        timeout: 90_000,
      });
      await editor.page.screenshot({ path: path.join(output, "04-plan-derived-subset.png"), fullPage: true });
      mark("USER_PLAN_ALLOCATION_GROUP_SPLIT_RECOMPOSE_DERIVED_SUBSET_UI");
      const source = await request.get(`${root}/models/${model.id}/source`, {
        headers: { Authorization: `Bearer ${editor.token}` },
      });
      expect(source.status()).toBe(200);
      expect(await source.body()).toEqual(readFileSync(path.join(sources, "real-scope.ifc")));
      mark("ORIGINAL_IFC_BYTES_UNCHANGED_AFTER_PLAN_AND_DERIVED_COMMANDS");

      const executive = await actor("executive", route);
      await expect(executive.page.getByRole("button", { name: "Importar IFC a staging", exact: true })).toHaveCount(0);
      const denied = await request.post(`${root}/items`, {
        headers: { Authorization: `Bearer ${executive.token}`, "Idempotency-Key": `denied-${run}` },
        data: { scope_code: "DENIED", name: "Not allowed", quantity: 1, unit: "ea", reason },
      });
      expect(denied.status()).toBe(403);
      const foreign = await actor("foreign", "/app");
      expect(
        (
          await request.get(`${root}/models/${model.id}/source`, {
            headers: { Authorization: `Bearer ${foreign.token}` },
          })
        ).status()
      ).toBe(404);
      mark("EXECUTIVE_READ_ONLY_AND_DIRECT_API_FOREIGN_TENANT_DENIAL");
      for (const [label, suffix] of [
        ["model_version_load", "/models"],
        ["bim_object_query", `/models/${model.id}/objects`],
        ["scope_item_list", "/items"],
        ["scope_hierarchy", "/items/hierarchy"],
        ["derived_model_query", "/derived-models"],
      ]) {
        for (let sample = 0; sample < 3; sample++) {
          const start = performance.now();
          const response = await request.get(root + suffix, { headers: { Authorization: `Bearer ${editor.token}` } });
          observations.push({
            label,
            elapsed_ms: Number((performance.now() - start).toFixed(2)),
            status: response.status(),
          });
          expect(response.status()).toBe(200);
        }
      }
      mark("LOCAL_QUERY_OBSERVATIONS_NOT_PRODUCTION_SLA");
      writeFileSync(
        path.join(output, "browser-uat.json"),
        JSON.stringify({ ...evidence, result: "PASS", finished_at: new Date().toISOString() }, null, 2)
      );
    } catch (error) {
      writeFileSync(
        path.join(output, "browser-uat.json"),
        JSON.stringify({ ...evidence, result: "FAIL", error: String(error) }, null, 2)
      );
      throw error;
    } finally {
      for (const context of browser.contexts()) await context.close();
    }
  });
});
