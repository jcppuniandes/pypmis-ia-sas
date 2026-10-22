import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const file = process.env.E2E_O1BB1_FIXTURE;
const fixture = file ? JSON.parse(readFileSync(file, "utf8")) : null;
const api = process.env.E2E_API_URL || "http://127.0.0.1:8854";
const output = path.resolve(process.env.E2E_O1BB1_OUTPUT || "../outputs/.qa/wave-o1bb1-20261021/chromium");
const reason = "Controlled real B1 browser release validation";

test.describe("O1B-B1 actual AWP Readiness and 4D release", () => {
  test.skip(!fixture, "Dedicated real PostgreSQL actors and source prerequisites required");
  test.use({ actionTimeout: 40_000, navigationTimeout: 120_000 });
  test("ADMIN publish and independent USER release with original IFC 4D", async ({ browser, request }) => {
    test.setTimeout(900_000);
    expect(api).toMatch(/^http:\/\/(127\.0\.0\.1|localhost):8854$/);
    mkdirSync(output, { recursive: true });
    const checks: Array<{ code: string; result: string }> = [];
    const errors: string[] = [];
    const observations: Array<{ label: string; elapsed_ms: number; status: number }> = [];
    const pages: Page[] = [];
    const project = fixture.project_workspace_id;
    const awpRoute = `/workspaces/${project}/awp`;
    const mark = (code: string) => checks.push({ code, result: "PASS" });
    async function actor(role: string, route: string) {
      const user = fixture.users[role];
      const login = await request.post(`${api}/api/v1/auth/login`, {
        timeout: 120_000,
        data: { email: user.email, tenant_id: user.tenant_id, password: "O1bb1-disposable-only!" },
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
      page.on("pageerror", (error) => errors.push(String(error)));
      await page.goto(route);
      return { page, token: String(session.access_token), context };
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
    async function tab(page: Page, name: string) {
      await page.getByRole("navigation", { name: "AWP submodules" }).getByRole("button", { name, exact: true }).click();
    }
    async function openAdmin(role: string, title: string) {
      const user = await actor(role, "/app");
      await user.page.getByRole("button", { name: "Cambiar a ADMIN MODE", exact: true }).click();
      for (const name of ["Platform Administration", "Process Configuration"]) {
        const button = user.page.getByRole("button", { name, exact: true });
        if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
      }
      await user.page.getByRole("button", { name: "Process & Operational Configuration", exact: true }).click();
      await user.page.getByRole("button", { name: title, exact: true }).click();
      await expect(user.page.getByLabel(`${title} configuration JSON`, { exact: true })).not.toHaveValue("{}");
      return user;
    }
    try {
      for (const [title, prefix] of [
        ["AWP Profiles", "/api/v1/awp/admin/profiles"],
        ["4D State Profiles", "/api/v1/schedule/4d/admin/profiles"],
      ]) {
        const admin = await openAdmin("admin", title);
        const code = title === "AWP Profiles" ? "B1-AWP-UAT" : "B1-4D-UAT";
        const existing = await request.get(`${api}${prefix}`, { headers: { Authorization: `Bearer ${admin.token}` } });
        let profile = (await existing.json()).items.find((row: any) => row.code === code);
        if (!profile) {
          await admin.page.getByLabel(`${title} Code`, { exact: true }).fill(code);
          await admin.page.getByLabel(`${title} Name`, { exact: true }).fill(`B1 independent ${title}`);
          profile = await command(
            admin.page,
            prefix,
            () => admin.page.getByRole("button", { name: `Crear ${title} DRAFT`, exact: true }).click(),
            201
          );
          await admin.page.getByLabel(`Motivo ${title}`, { exact: true }).fill(reason);
          await command(
            admin.page,
            `/${profile.id}/publish`,
            () => admin.page.getByRole("button", { name: `Publicar ${title}`, exact: true }).click(),
            403
          );
          mark(`${title}_AUTHOR_CANNOT_PUBLISH`);
        }
        const publisher = await openAdmin("publisher", title);
        await publisher.page.getByRole("button", { name: `Ver ${title} ${code}`, exact: true }).click();
        if (profile.status !== "published") {
          await publisher.page.getByLabel(`Motivo ${title}`, { exact: true }).fill(reason);
          await command(publisher.page, `/${profile.id}/publish`, () =>
            publisher.page.getByRole("button", { name: `Publicar ${title}`, exact: true }).click()
          );
        }
        await expect(
          publisher.page.getByRole("table", { name: title }).getByRole("row").filter({ hasText: code })
        ).toContainText("PUBLISHED");
        mark(`${title}_ADMIN_INDEPENDENT_PUBLICATION`);
      }
      const planner = await actor("planner", awpRoute);
      await expect(planner.page.getByRole("heading", { name: "Project Execution / AWP", exact: true })).toBeVisible();
      await planner.page.getByLabel("Motivo AWP", { exact: true }).fill(reason);
      await planner.page.getByLabel("CWA code", { exact: true }).fill("B1-NORTH");
      await planner.page.getByLabel("CWA name", { exact: true }).fill("North construction work area");
      const cwa = await command(
        planner.page,
        "/cwas",
        () => planner.page.getByRole("button", { name: "Crear CWA", exact: true }).click(),
        201,
        "CWA creation"
      );
      mark("CWA_CONTAINER_CREATED");
      await tab(planner.page, "Work Packages");
      const packages: any[] = [];
      for (const [index, type] of ["CWP", "EWP", "PWP", "IWP", "TWP", "SUPPORT", "LOGISTICS"].entries()) {
        await planner.page.getByRole("button", { name: "Nuevo Work Package", exact: true }).click();
        await planner.page.getByLabel("Package code", { exact: true }).fill(`B1-${type}`);
        await planner.page.getByLabel("Package name", { exact: true }).fill(`Browser governed ${type}`);
        await planner.page.getByLabel("Package type", { exact: true }).selectOption(type);
        await planner.page.getByLabel("Package CWA", { exact: true }).selectOption(String(cwa.id));
        let pkg = await command(
          planner.page,
          "/packages",
          () => planner.page.getByRole("button", { name: "Crear Work Package", exact: true }).click(),
          201,
          "Package creation"
        );
        const scopeIndex = Math.min(index, 3);
        for (const [kind, targetId] of [
          ["SCOPE", fixture.scope_items[scopeIndex].id],
          ["PLAN", fixture.plan_items[scopeIndex].id],
        ] as const) {
          await planner.page.getByLabel("Package mapping kind", { exact: true }).selectOption(kind);
          await planner.page.getByLabel(`Mapping ${kind}`, { exact: true }).selectOption(String(targetId));
          await command(
            planner.page,
            `/packages/${pkg.id}/mappings`,
            () => planner.page.getByRole("button", { name: "Guardar Package mapping", exact: true }).click(),
            201,
            "Package mapping"
          );
        }
        const ids = Object.entries(fixture.activity_plans)
          .filter(([, plan]) => plan === fixture.plan_items[scopeIndex].id)
          .map(([id]) => id);
        for (const schedule of [fixture.baseline_version, fixture.current_version])
          for (const activityId of ids) {
            await planner.page.getByLabel("Package mapping kind", { exact: true }).selectOption("ACTIVITY");
            await planner.page
              .getByLabel("Mapping Schedule Version", { exact: true })
              .selectOption(String(schedule.id));
            await planner.page.getByLabel("Mapping Activity", { exact: true }).selectOption(activityId);
            await planner.page
              .getByLabel("Package Activity phase", { exact: true })
              .selectOption(fixture.activity_phases[activityId]);
            await command(
              planner.page,
              `/packages/${pkg.id}/mappings`,
              () => planner.page.getByRole("button", { name: "Guardar Package mapping", exact: true }).click(),
              201,
              "Package Activity mapping"
            );
          }
        packages.push(pkg);
      }
      mark("ALL_FIVE_BASE_TYPES_SUPPORT_LOGISTICS_AND_PHASED_MN_MAPPINGS");
      const focus = packages[0];
      await tab(planner.page, "Execution Constraints");
      await planner.page.getByLabel("Constraint code", { exact: true }).fill("B1-BLOCKER");
      await planner.page.getByLabel("Constraint title", { exact: true }).fill("Engineering hold before release");
      await planner.page.getByLabel("Constraint type", { exact: true }).selectOption("ENGINEERING");
      const constraint = await command(
        planner.page,
        "/constraints",
        () => planner.page.getByRole("button", { name: "Crear Execution Constraint", exact: true }).click(),
        201,
        "Constraint creation"
      );
      await planner.page.getByLabel("Constraint mapping kind", { exact: true }).selectOption("PACKAGE");
      await planner.page.getByLabel("Mapping PACKAGE", { exact: true }).selectOption(String(focus.id));
      await command(
        planner.page,
        `/constraints/${constraint.id}/mappings`,
        () => planner.page.getByRole("button", { name: "Guardar Constraint mapping", exact: true }).click(),
        201
      );
      await tab(planner.page, "Readiness");
      await planner.page.getByLabel("Readiness Package", { exact: true }).selectOption(String(focus.id));
      await planner.page.getByLabel("Readiness as of", { exact: true }).fill("2026-10-22");
      for (const dimension of ["ENGINEERING", "MATERIAL", "ACCESS"])
        await planner.page
          .getByLabel(`Readiness evidence ${dimension}`, { exact: true })
          .fill(`B1-evidence-${dimension}`);
      const blocked = await command(
        planner.page,
        `/packages/${focus.id}/assess`,
        () => planner.page.getByRole("button", { name: "Evaluar Package Readiness", exact: true }).click(),
        201,
        "Readiness assessment"
      );
      expect(blocked.readiness_state).toBe("NOT_READY");
      await expect(
        planner.page
          .getByRole("table", { name: "Workfront Readiness", exact: true })
          .getByRole("row")
          .filter({ hasText: "B1-CWP" })
      ).toContainText("SCHEDULED");
      mark("SCHEDULED_NOT_READY_BLOCKER");
      const manager = await actor("manager", awpRoute);
      await manager.page.getByLabel("Motivo AWP", { exact: true }).fill(reason);
      await tab(manager.page, "Execution Constraints");
      await manager.page.getByRole("button", { name: "Ver Constraint B1-BLOCKER", exact: true }).click();
      await manager.page.getByLabel("Constraint transition", { exact: true }).selectOption("CLEARED");
      await manager.page
        .getByLabel("Constraint clearance evidence", { exact: true })
        .fill("B1-independent-clearance-evidence");
      await command(manager.page, `/constraints/${constraint.id}/transition`, () =>
        manager.page.getByRole("button", { name: "Aplicar transición Constraint", exact: true }).click()
      );
      await planner.page.getByRole("button", { name: "Actualizar AWP", exact: true }).click();
      const ready = await command(
        planner.page,
        `/packages/${focus.id}/assess`,
        () => planner.page.getByRole("button", { name: "Evaluar Package Readiness", exact: true }).click(),
        201
      );
      expect(ready.readiness_state).toBe("READY");
      expect(ready.package.release_state).toBe("NOT_RELEASED");
      mark("CLEARED_READY_NOT_AUTORELEASED");
      for (const [user, status] of [
        [planner, "PLANNED"],
        [manager, "UNDER_REVIEW"],
      ] as const) {
        const refresh = user.page.waitForResponse(
          (response) => response.url().endsWith("/overview") && response.request().method() === "GET"
        );
        await user.page.getByRole("button", { name: "Actualizar AWP", exact: true }).click();
        await refresh;
        await tab(user.page, "Work Packages");
        await user.page.getByRole("button", { name: "Ver Package B1-CWP", exact: true }).click();
        await user.page.getByLabel("Package lifecycle action", { exact: true }).selectOption(status);
        await command(user.page, `/packages/${focus.id}/transition`, () =>
          user.page.getByRole("button", { name: "Aplicar estado Package", exact: true }).click()
        );
      }
      const releaser = await actor("second_manager", awpRoute);
      await releaser.page.getByLabel("Motivo AWP", { exact: true }).fill(reason);
      await tab(releaser.page, "Work Packages");
      await releaser.page.getByRole("button", { name: "Ver Package B1-CWP", exact: true }).click();
      await releaser.page.getByLabel("Package lifecycle action", { exact: true }).selectOption("READY");
      await command(releaser.page, `/packages/${focus.id}/transition`, () =>
        releaser.page.getByRole("button", { name: "Aplicar estado Package", exact: true }).click()
      );
      await tab(releaser.page, "Readiness");
      await releaser.page.getByLabel("Readiness Package", { exact: true }).selectOption(String(focus.id));
      const released = await command(releaser.page, `/packages/${focus.id}/release`, () =>
        releaser.page.getByRole("button", { name: "Release Package independiente", exact: true }).click()
      );
      expect(released.status).toBe("RELEASED");
      mark("INDEPENDENT_EXPLICIT_PACKAGE_RELEASE");
      // A distinct live blocker leaves a readiness overlay on MAINTENANCE; it does not edit P6.
      const overlayResponse = await request.post(`${api}/api/v1/awp/projects/${project}/constraints`, {
        headers: { Authorization: `Bearer ${planner.token}`, "Idempotency-Key": `overlay-${Date.now()}` },
        data: { reason, code: "B1-OVERLAY", title: "Live 4D access hold", constraint_type: "ACCESS", blocking: true },
      });
      expect(overlayResponse.status(), await overlayResponse.text()).toBe(201);
      const overlay = await overlayResponse.json();
      const mapped = await request.post(`${api}/api/v1/awp/projects/${project}/constraints/${overlay.id}/mappings`, {
        headers: {
          Authorization: `Bearer ${planner.token}`,
          "Idempotency-Key": `overlay-map-${Date.now()}`,
          "If-Match": `"${overlay.version}"`,
        },
        data: { reason, target_kind: "PACKAGE", target_id: packages[3].id },
      });
      expect(mapped.status(), await mapped.text()).toBe(201);
      const four = await actor("planner", `/workspaces/${project}/schedule-manager`);
      await four.page
        .getByRole("navigation", { name: "Schedule Manager submodules" })
        .getByRole("button", { name: "4D Model", exact: true })
        .click();
      await expect(four.page.getByRole("table", { name: "4D states and traceability", exact: true })).toBeVisible();
      await four.page.getByLabel("Date 4D", { exact: true }).fill("2026-10-23T12:00");
      await expect(four.page.getByRole("table", { name: "4D states and traceability", exact: true })).toContainText(
        "MAINTENANCE_INTERVENTION"
      );
      await expect(four.page.getByRole("table", { name: "4D states and traceability", exact: true })).toContainText(
        "TEMPORARY_IN_USE"
      );
      await expect(four.page.getByRole("table", { name: "4D states and traceability", exact: true })).toContainText(
        "BLOCKED_BY_READINESS"
      );
      await expect(four.page.locator("canvas")).toBeVisible();
      await expect(four.page.getByText(/mallas IFC reales/i)).toBeVisible();
      await expect
        .poll(async () => Number(await four.page.locator("canvas").getAttribute("data-mesh-count")))
        .toBeGreaterThan(0);
      await expect
        .poll(async () => Number(await four.page.locator("canvas").getAttribute("data-triangle-count")))
        .toBeGreaterThan(0);
      mark("FOUR_D_ORIGINAL_IFC_REAL_GEOMETRY_ALL_NATURES_READINESS_OVERLAY");
      await four.page.getByLabel("Source 4D", { exact: true }).selectOption("BASELINE");
      await expect(four.page.getByLabel("Data Date source context", { exact: true })).toContainText("2026-10-20");
      await four.page.getByLabel("Source 4D", { exact: true }).selectOption("CURRENT");
      await expect(four.page.getByLabel("Data Date source context", { exact: true })).toContainText("2026-10-22");
      await four.page.getByRole("button", { name: "AS OF DATA DATE", exact: true }).click();
      await four.page.getByLabel("Compare Baseline Current 4D", { exact: true }).check();
      await expect(four.page.getByLabel("4D Baseline Current comparison", { exact: true })).toBeVisible();
      mark("BASELINE_CURRENT_COMPARISON_EXPLICIT_DATA_DATE");
      await four.page.getByLabel("Filter 4D Scope Nature", { exact: true }).selectOption("MAINTENANCE");
      await expect(
        four.page.getByRole("table", { name: "4D states and traceability", exact: true }).getByRole("row")
      ).toHaveCount(2);
      await four.page
        .getByRole("button", { name: /^Traceability / })
        .first()
        .click();
      await expect(four.page.getByLabel("4D traceability panel", { exact: true })).toContainText(
        fixture.objects[3].guid
      );
      mark("FOUR_D_FILTER_AND_IFC_SCOPE_PLAN_PACKAGE_ACTIVITY_TRACEABILITY");
      await four.page.screenshot({ path: path.join(output, "four-d-final.png"), fullPage: true });
      expect(errors).toEqual([]);
      mark("NO_BROWSER_RUNTIME_ERRORS");
      writeFileSync(
        path.join(output, "browser-uat.json"),
        JSON.stringify(
          {
            result: "PASS",
            checks,
            observations,
            browser_errors: errors,
            project_workspace_id: project,
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

  test("additional timeline filters and actual geometry selection", async ({ browser, request }) => {
    test.setTimeout(240_000);
    const user = fixture.users.planner;
    const login = await request.post(`${api}/api/v1/auth/login`, {
      data: { email: user.email, tenant_id: user.tenant_id, password: "O1bb1-disposable-only!" },
    });
    expect(login.status()).toBe(200);
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
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(String(error)));
    const project = fixture.project_workspace_id;
    const proof: Array<{ code: string; result: string }> = [];
    const mark = (code: string) => proof.push({ code, result: "PASS" });
    async function settled() {
      await expect(page.getByLabel("4D Model", { exact: true })).toHaveAttribute("aria-busy", "false");
    }
    try {
      await page.goto(`/workspaces/${project}/schedule-manager`);
      await page
        .getByRole("navigation", { name: "Schedule Manager submodules" })
        .getByRole("button", { name: "4D Model", exact: true })
        .click();
      await expect(page.getByRole("table", { name: "4D states and traceability", exact: true })).toBeVisible();
      await settled();
      const date = page.getByLabel("Date 4D", { exact: true });
      await date.fill("2026-10-23T12:00");
      await settled();
      for (const [label, value] of [
        ["WBS", fixture.current_version.snapshot_json.wbs[0].external_id],
        ["Scope", fixture.scope_items[0].id],
        ["Plan", fixture.plan_items[0].id],
      ] as const) {
        const control = page.getByLabel(`Filter 4D ${label}`, { exact: true });
        await control.selectOption(String(value));
        await settled();
        const rows = page.getByRole("table", { name: "4D states and traceability", exact: true }).getByRole("row");
        await expect(rows).toHaveCount(label === "WBS" ? 5 : 2);
        await control.selectOption("");
        await settled();
        mark(`FOUR_D_BROWSER_FILTER_${label.toUpperCase()}`);
      }
      const response = await request.get(`${api}/api/v1/awp/projects/${project}/packages`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      const pkg = (await response.json()).items.find((row: any) => row.package_code === "B1-CWP");
      expect(pkg.status).toBe("RELEASED");
      await page.getByLabel("Filter 4D Package", { exact: true }).selectOption(String(pkg.id));
      await settled();
      await expect(
        page.getByRole("table", { name: "4D states and traceability", exact: true }).getByRole("row")
      ).toHaveCount(2);
      mark("FOUR_D_BROWSER_FILTER_PACKAGE");
      await expect
        .poll(async () => Number(await page.locator("canvas").getAttribute("data-visible-mesh-count")))
        .toBeGreaterThan(0);
      const box = await page.locator("canvas").boundingBox();
      expect(box).not.toBeNull();
      await page.locator("canvas").screenshot({ path: path.join(output, "four-d-before-pick.png") });
      // Camera retains the whole-source framing when filters change. Pick the
      // visible product using real canvas pointer events, not a response stub.
      // The upright filtered wall occupies only ~4% of the whole-model frame.
      // A 5% grid can straddle it without any intersection, so sample at 2%.
      for (const y of [0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7]) {
        for (const x of Array.from({ length: 21 }, (_, index) => 0.3 + index * 0.02)) {
          await page.locator("canvas").click({ position: { x: box!.width * x, y: box!.height * y } });
          if (await page.getByLabel("4D traceability panel", { exact: true }).isVisible()) break;
        }
        if (await page.getByLabel("4D traceability panel", { exact: true }).isVisible()) break;
      }
      await expect(page.getByLabel("4D traceability panel", { exact: true })).toContainText(fixture.objects[0].guid);
      mark("FOUR_D_ACTUAL_GEOMETRY_PICK_TRACEABILITY");
      await page.getByLabel("Filter 4D Package", { exact: true }).selectOption("");
      await settled();
      await page.getByRole("button", { name: "Paso adelante 4D", exact: true }).click();
      await expect(date).toHaveValue("2026-10-24T12:00");
      await settled();
      await page.getByRole("button", { name: "Paso atrás 4D", exact: true }).click();
      await expect(date).toHaveValue("2026-10-23T12:00");
      await settled();
      await page.getByLabel("Speed 4D", { exact: true }).selectOption("2");
      await page.getByRole("button", { name: "Play 4D", exact: true }).click();
      await expect(date).not.toHaveValue("2026-10-23T12:00");
      await page.getByRole("button", { name: "Pause 4D", exact: true }).click();
      await settled();
      await page.getByRole("button", { name: "AS OF DATA DATE", exact: true }).click();
      await expect(date).toHaveValue("2026-10-22T08:00");
      mark("FOUR_D_BROWSER_PLAY_PAUSE_SPEED_STEPS_AND_DATA_DATE");
      expect(errors).toEqual([]);
      const target = path.join(output, "browser-uat.json");
      const original = JSON.parse(readFileSync(target, "utf8"));
      original.additional_checks = proof;
      original.checks = [
        ...original.checks.filter(
          (row: any) =>
            !row.code.startsWith("FOUR_D_BROWSER_") && row.code !== "FOUR_D_ACTUAL_GEOMETRY_PICK_TRACEABILITY"
        ),
        ...proof,
      ];
      writeFileSync(target, JSON.stringify(original, null, 2));
      await page.screenshot({ path: path.join(output, "four-d-geometry-selection.png"), fullPage: true });
    } finally {
      await context.close();
    }
  });
});
