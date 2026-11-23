import { test, expect, type Page, type Locator, type BrowserContext } from "@playwright/test";
import { createHash } from "node:crypto";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

type Row = Record<string, any>;
const fixture = process.env.E2E_O3B_FIXTURE;
const previousPath = process.env.E2E_O3B_PREVIOUS_SEGMENT;
const data: Row | null = fixture ? JSON.parse(readFileSync(fixture, "utf8")) : null;
const previousBytes = previousPath ? readFileSync(previousPath) : null;
const previous: Row | null = previousBytes ? JSON.parse(previousBytes.toString("utf8")) : null;
const api = process.env.E2E_API_URL ?? "http://127.0.0.1:8864";
const app = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5524";
const out = path.resolve(process.env.E2E_O3B_OUTPUT ?? "../outputs/.qa/wave-o3b-20261119/chromium-closeout");
const reason = "O3B cierre Chromium sobre la misma cadena persistente y decisiones nativas explícitas";
const button = (scope: Page | Locator, name: string) => scope.getByRole("button", { name, exact: true });
const field = (scope: Page | Locator, name: string) => scope.getByLabel(name, { exact: true });
const form = (scope: Page | Locator, name: string) => scope.getByRole("form", { name, exact: true });

test.describe("O3B persisted browser lifecycle closeout", () => {
  test.skip(
    !data || !previous,
    "Requires the actual persisted Chromium lifecycle segment, not precreated Quality facts"
  );
  test.use({ actionTimeout: 45_000, navigationTimeout: 120_000 });
  test("continues readiness trace mobile and explicit Progress AWP Contracts decisions on the same chain", async ({
    browser,
    request,
  }) => {
    test.setTimeout(900_000);
    if (!data || !previous || !previousBytes) throw new Error("Missing actual browser lifecycle evidence");
    expect(new URL(api).port).toBe("8864");
    expect(new URL(app).port).toBe("5524");
    expect(data.tenant_id).toBe(29);
    expect(data.project_workspace_id).toBe(169729974);
    expect(previous.fixture).toBe(path.basename(fixture!));
    expect(["READINESS_TRACE_MOBILE", "NATIVE_PROGRESS", "NATIVE_AWP", "NATIVE_CONTRACTS"]).toContain(previous.stage);
    expect(previous.observed.acceptance_successor).toBe(6);
    expect(previous.steps.every((step: Row) => step.status >= 200 && step.status < 300)).toBe(true);
    mkdirSync(out, { recursive: true });
    const oldHash = createHash("sha256").update(previousBytes).digest("hex");
    const route = `/workspaces/${data.project_workspace_id}/quality`;
    const root = `/api/v1/quality/projects/${data.project_workspace_id}`;
    const contexts: BrowserContext[] = [];
    const tokens = new Map<string, string>();
    const steps: Row[] = [];
    const errors: Row[] = [];
    const observed: Row = { ...previous.observed };
    const diagnostics: Row = {};
    let stage = "PERSISTED_CHAIN_REVALIDATION";
    let lastPage: Page | undefined;
    let passed = false;
    async function session(role: string, target = route) {
      const response = await request.post(`${api}/api/v1/auth/login`, {
        data: { tenant_id: data!.tenant_id, email: data!.users[role], password: data!.password },
        timeout: 120_000,
      });
      expect(response.status(), `Actual scoped login ${role}`).toBe(200);
      const auth = await response.json();
      tokens.set(role, auth.access_token);
      const context = await browser.newContext({ baseURL: app, viewport: { width: 1440, height: 1000 } });
      contexts.push(context);
      await context.addInitScript(
        (value) =>
          localStorage.setItem(
            "pypmis_auth",
            JSON.stringify({ state: { token: value.access_token, user: value.user }, version: 0 })
          ),
        auth
      );
      const page = await context.newPage();
      lastPage = page;
      page.on("pageerror", (error) => errors.push({ role, message: error.message }));
      await page.goto(target);
      if (target === route)
        await expect(page.getByRole("navigation", { name: "Quality Manager submodules" })).toBeVisible({
          timeout: 180_000,
        });
      return page;
    }
    async function read(role: string, endpoint: string) {
      const response = await request.get(api + endpoint, {
        headers: { Authorization: `Bearer ${tokens.get(role)}` },
        timeout: 120_000,
      });
      const value = await response.json();
      expect(response.status(), `Read only diagnostic ${endpoint}: ${JSON.stringify(value)}`).toBe(200);
      return value;
    }
    async function fill(scope: Page | Locator, values: Row) {
      for (const [name, value] of Object.entries(values)) {
        const control = field(scope, name);
        const tag = await control.evaluate((element) => element.tagName);
        if (tag === "SELECT") {
          await expect(control.locator(`option[value="${String(value)}"]`)).toBeAttached();
          await control.selectOption(String(value));
        } else await control.fill(String(value));
      }
    }
    async function submit(page: Page, name: string, endpoint: string) {
      lastPage = page;
      const control = form(page, name);
      await expect(control).toBeVisible();
      await field(control, "Motivo operacional").fill(reason);
      const pending = page.waitForResponse(
        (response) => new URL(response.url()).pathname === endpoint && response.request().method() === "POST",
        { timeout: 120_000 }
      );
      await button(control, name).click();
      const response = await pending;
      const value = await response.json();
      expect(response.status(), `${stage}/${name}: ${JSON.stringify(value)}`).toBe(201);
      steps.push({ stage, action: name, path: endpoint, status: response.status(), id: value.id });
      console.log(`${stage}: ${name} → ${value.id}`);
      writeFileSync(path.join(out, "running.json"), JSON.stringify({ stage, steps, observed }, null, 2));
      return value;
    }
    async function tab(page: Page, view: string) {
      await button(page.getByRole("navigation", { name: "Quality Manager submodules" }), view).click();
      await button(page, "Actualizar Quality").click();
    }
    try {
      const inspector = await session("quality_inspector");
      const acceptance = await read("quality_inspector", root + `/acceptances/${observed.acceptance_successor}`);
      const failed = await read("quality_inspector", root + `/inspections/${observed.failed}`);
      const reinspected = await read("quality_inspector", root + `/inspections/${observed.reinspection}`);
      const ncr = await read("quality_inspector", root + `/ncrs/${observed.ncr}`);
      expect(acceptance.source_state).toBe("CURRENT");
      expect(acceptance.supersedes_id).toBe(observed.acceptance);
      expect(failed.result).toBe("FAIL");
      expect(failed.status).toBe("CLOSED");
      expect(reinspected.result).toBe("PASS");
      expect(reinspected.status).toBe("CLOSED");
      expect(ncr.status).toBe("CLOSED");
      diagnostics.persisted_chain = {
        acceptance_id: acceptance.id,
        acceptance_state: acceptance.source_state,
        supersedes_id: acceptance.supersedes_id,
        ncr_status: ncr.status,
        failed_id: failed.id,
        failed_result: failed.result,
        reinspection_id: reinspected.id,
        reinspection_result: reinspected.result,
      };
      stage = "READINESS_TRACE_MOBILE";
      await tab(inspector, "Readiness Evidence Assessments");
      const panel = inspector.getByRole("region", { name: "Readiness Evidence Assessments", exact: true });
      await fill(panel, { "ITP de evaluación ID": observed.itp, "ID Objeto de evaluación": data.production_id });
      await button(panel, "Consultar Objeto de evaluación").click();
      await button(panel, "Fijar Objeto de evaluación").click();
      const assessment = observed.assessment
        ? (await read("quality_inspector", root + `/readiness/assessments?itp_id=${observed.itp}`)).items.find(
            (item: Row) => item.id === observed.assessment
          )
        : await submit(inspector, "Guardar evaluación Quality", root + "/readiness/assess");
      expect(assessment, "Retain the existing actual Chromium readiness assessment on continuation").toBeTruthy();
      expect(assessment.readiness_state).toBe("READY");
      observed.assessment = assessment.id;
      await inspector.screenshot({ path: path.join(out, "04-readiness-assessment.png") });
      const reviewer = await session("quality_reviewer");
      await tab(reviewer, "Trace");
      await fill(reviewer, { "Tipo de entidad Quality": "NCR", "Entidad Quality ID": observed.ncr });
      await button(reviewer, "Consultar Trace").click();
      await expect(reviewer.getByRole("table", { name: "Historial Quality" })).toBeVisible();
      await expect(reviewer.getByRole("table", { name: "Historial Quality" }).locator("tbody tr")).not.toHaveCount(0);
      await reviewer.screenshot({ path: path.join(out, "05-trace.png") });
      await inspector.setViewportSize({ width: 390, height: 844 });
      await tab(inspector, "Quality Readiness");
      await fill(inspector, { "ITP aplicable ID": observed.itp, "Objeto Quality ID": data.production_id });
      await button(inspector, "Consultar Quality Readiness").click();
      const readyPanel = inspector.getByRole("region", { name: "Quality Readiness", exact: true });
      await expect(readyPanel.getByText("READY", { exact: true })).toBeVisible();
      await expect(
        readyPanel.getByRole("table", { name: "Controles Quality" }).getByText("CUMPLE", { exact: true })
      ).toBeVisible();
      diagnostics.mobile = await inspector.evaluate(() => ({
        viewport: innerWidth,
        scroll: document.documentElement.scrollWidth,
      }));
      expect(diagnostics.mobile.scroll).toBeLessThanOrEqual(diagnostics.mobile.viewport + 1);
      await inspector.screenshot({ path: path.join(out, "06-mobile-ready.png"), fullPage: true });
      stage = "NATIVE_PROGRESS";
      const progress = await session("progress_engineer", `/workspaces/${data.project_workspace_id}/progress`);
      const progressBefore = await read(
        "progress_engineer",
        `/api/v1/progress/projects/${data.project_workspace_id}/overview`
      );
      diagnostics.progress_before = {
        ids: progressBefore.measurements.map((row: Row) => row.id),
        count: progressBefore.measurements.length,
      };
      await button(progress, "Field Evidence").click();
      const fieldPanel = progress.getByRole("region", { name: "Field evidence consumer" });
      await fill(fieldPanel, { "Evidencia de campo ID": data.production_id });
      await button(fieldPanel, "Consultar origen de campo").click();
      await fill(form(progress, "Registrar decisión PROGRESS"), {
        "Decisión Progress": "PARTIAL_ADOPT",
        "Cantidad a adoptar": "1",
        "Período de Progress": data.period_id,
        "Código de medición borrador": `O3B-SUFFIX-${Date.now().toString(36)}`,
      });
      const native = await submit(
        progress,
        "Registrar decisión PROGRESS",
        `/api/v1/progress/projects/${data.project_workspace_id}/field-adoptions`
      );
      observed.progress_measurement = native.linked_entity_id;
      const afterField = await read(
        "progress_engineer",
        `/api/v1/progress/projects/${data.project_workspace_id}/overview`
      );
      expect(afterField.measurements.length).toBe(progressBefore.measurements.length + 1);
      const measurement = afterField.measurements.find((row: Row) => row.id === native.linked_entity_id);
      expect(measurement.status).toBe("DRAFT");
      await button(progress, "Quality Evidence").click();
      const qualityPanel = progress.getByRole("region", { name: "Quality evidence consumer" });
      await fill(qualityPanel, { "Evidencia Quality ID": observed.acceptance_successor });
      await button(qualityPanel, "Consultar evidencia Quality").click();
      await fill(form(progress, "Registrar decisión Quality PROGRESS"), {
        "Decisión sobre evidencia Quality": "ADOPT",
        "Medición Progress pendiente ID": native.linked_entity_id,
      });
      const adopted = await submit(
        progress,
        "Registrar decisión Quality PROGRESS",
        `/api/v1/progress/projects/${data.project_workspace_id}/quality-adoptions`
      );
      expect(adopted.linked_entity_id).toBe(native.linked_entity_id);
      observed.progress_decision = adopted.id;
      const progressAfter = await read(
        "progress_engineer",
        `/api/v1/progress/projects/${data.project_workspace_id}/overview`
      );
      expect(progressAfter.measurements).toHaveLength(afterField.measurements.length);
      const bound = progressAfter.measurements.find((row: Row) => row.id === native.linked_entity_id);
      expect(bound.status).toBe("DRAFT");
      expect(bound.numerator).toEqual(measurement.numerator);
      for (const original of progressBefore.measurements) {
        const current = progressAfter.measurements.find((row: Row) => row.id === original.id);
        for (const key of ["status", "numerator", "period_id", "source_reference"])
          expect(current[key]).toEqual(original[key]);
      }
      diagnostics.progress_after = {
        count: progressAfter.measurements.length,
        id: bound.id,
        status: bound.status,
        numerator: bound.numerator,
        quality_created_quantity: false,
      };
      await progress.screenshot({ path: path.join(out, "07-progress-native-quality.png") });
      stage = "NATIVE_AWP";
      const awp = await session("awp_manager", `/workspaces/${data.project_workspace_id}/awp`);
      const awpBefore = await read("awp_manager", `/api/v1/awp/projects/${data.project_workspace_id}/overview`);
      const oldPackage = awpBefore.packages.find((row: Row) => row.id === data.iwp_id);
      await button(awp, "Quality Evidence").click();
      const awpPanel = awp.getByRole("region", { name: "Quality evidence consumer" });
      await fill(awpPanel, { "Evidencia Quality ID": assessment.id });
      await button(awpPanel, "Consultar evidencia Quality").click();
      await fill(form(awp, "Registrar decisión Quality AWP"), {
        "Decisión sobre evidencia Quality": "ADOPT",
        "Paquete AWP a evaluar ID": data.iwp_id,
      });
      const awpDecision = await submit(
        awp,
        "Registrar decisión Quality AWP",
        `/api/v1/awp/projects/${data.project_workspace_id}/quality-adoptions`
      );
      observed.awp_decision = awpDecision.id;
      const awpAfter = await read("awp_manager", `/api/v1/awp/projects/${data.project_workspace_id}/overview`);
      const newPackage = awpAfter.packages.find((row: Row) => row.id === data.iwp_id);
      for (const key of ["status", "release_state", "released_by", "released_at"])
        expect(newPackage[key]).toEqual(oldPackage[key]);
      expect(awpAfter.constraints).toEqual(awpBefore.constraints);
      diagnostics.awp = {
        package_id: data.iwp_id,
        release_state_before: oldPackage.release_state,
        release_state_after: newPackage.release_state,
        constraints_unchanged: true,
        quality_decision_id: awpDecision.id,
      };
      await awp.screenshot({ path: path.join(out, "08-awp-native-quality.png") });
      stage = "NATIVE_CONTRACTS";
      const contracts = await session("manager", `/workspaces/${data.project_workspace_id}/contracts`);
      await button(contracts, "Quality Evidence").click();
      const contractsPanel = contracts.getByRole("region", { name: "Quality evidence consumer" });
      await fill(contractsPanel, { "Tipo de evidencia Quality": "NCR", "Evidencia Quality ID": observed.ncr });
      await button(contractsPanel, "Consultar evidencia Quality").click();
      await expect(contractsPanel.getByText("QUALITY", { exact: true })).toBeVisible();
      expect(await contractsPanel.getByRole("form", { name: /Registrar decisión/ }).count()).toBe(0);
      diagnostics.contracts = { source_entity_type: "NCR", source_entity_id: observed.ncr, information_only: true };
      await contracts.screenshot({ path: path.join(out, "09-contracts-readonly.png") });
      expect(errors).toEqual([]);
      expect(createHash("sha256").update(readFileSync(previousPath!)).digest("hex")).toBe(oldHash);
      passed = true;
    } finally {
      if (!passed && lastPage)
        await lastPage.screenshot({ path: path.join(out, "failure.png"), fullPage: true }).catch(() => {});
      const result = {
        passed,
        stage,
        fixture: path.basename(fixture!),
        previous_segment: {
          path: previousPath,
          sha256: oldHash,
          original_run_passed: previous.passed,
          accepted_successful_steps: previous.steps.length,
          interruption:
            previous.stage === "READINESS_TRACE_MOBILE"
              ? "Harness missing reason before async form render; no rollback or recreation of actual Quality facts"
              : previous.stage === "NATIVE_PROGRESS"
                ? "Harness incorrectly expected zero prior Progress measurements; the fixture retained two. No rollback or recreation of Quality facts"
                : `Previous Chromium segment interrupted at ${previous.stage}; successful commands and persisted Quality facts retained`,
        },
        segments: [
          "ADMIN through accepted NCR remediation in previous Chromium run",
          "Readiness trace mobile and native consumers in this Chromium continuation",
        ],
        steps: [...previous.steps, ...steps],
        continuation_steps: steps,
        observed,
        diagnostics,
        errors: [...previous.errors, ...errors],
        finished_at: new Date().toISOString(),
      };
      writeFileSync(path.join(out, "summary.json"), JSON.stringify(result, null, 2));
      for (const context of contexts) await context.close();
    }
  });
});
