import { expect, test, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const manifest = process.env.E2E_O2A_FIXTURE;
const fixture = manifest ? JSON.parse(readFileSync(manifest, "utf8")) : null;
const api = process.env.E2E_API_URL || "http://127.0.0.1:8859";
const output = path.resolve(process.env.E2E_O2A_OUTPUT || "../outputs/.qa/wave-o2a-20261109/chromium");
const reason = "O2A isolated real-browser technical release validation";
const type = "UAT_DRAWING";
const discipline = "UAT_MECHANICAL";
const asOf = () => new Date().toISOString().slice(0, 10);

test.describe("O2A Engineering Foundation — actual browser lifecycle", () => {
  test.skip(!fixture, "Requires isolated PostgreSQL Engineering fixture and real API services");
  test.use({ actionTimeout: 35_000, navigationTimeout: 90_000 });

  test("independent configuration, CDE and EWP mapping, review, IFC and AWP consumption", async ({
    browser,
    request,
  }) => {
    test.setTimeout(900_000);
    expect(api).toMatch(/^http:\/\/(127\.0\.0\.1|localhost):8859$/);
    expect(process.env.E2E_BASE_URL).toMatch(/^http:\/\/(127\.0\.0\.1|localhost):5519\/?$/);
    mkdirSync(output, { recursive: true });
    const project = fixture.project_workspace_id;
    const root = `${api}/api/v1/engineering/projects/${project}`;
    const route = `/workspaces/${project}/engineering`;
    const run = Date.now().toString(36).toUpperCase();
    const profileCode = `O2A_UAT_${run}`;
    const deliverableCode = `ENG_UAT_${run}`;
    const checks: Array<{ code: string; result: string }> = [];
    const mutations: Array<{ step: string; status: number }> = [];
    const browserErrors: Array<{ role: string; error: string }> = [];
    const observations: Record<string, unknown> = {};
    const timings: Array<{ operation: string; route: string; samples_ms: number[]; median_ms: number }> = [];
    let stage = "admin-create-profile";
    let result = "FAIL";
    let lastPage: Page | undefined;
    const mark = (code: string) => checks.push({ code, result: "PASS" });
    const proof = (page: Page, name: string) => page.screenshot({ path: path.join(output, `${name}.png`) });

    async function actor(role: string, target = route) {
      const user = fixture.users[role];
      const login = await request.post(`${api}/api/v1/auth/login`, {
        timeout: 120_000,
        data: { email: user.email, tenant_id: user.tenant_id, password: user.password ?? fixture.password },
      });
      expect(login.status(), `login ${role}`).toBe(200);
      const session = await login.json();
      const context = await browser.newContext({
        baseURL: process.env.E2E_BASE_URL,
        viewport: { width: 1440, height: 900 },
      });
      await context.addInitScript(
        (value) =>
          localStorage.setItem(
            "pypmis_auth",
            JSON.stringify({ state: { token: value.access_token, user: value.user }, version: 0 })
          ),
        session
      );
      const page = await context.newPage();
      lastPage = page;
      page.on("pageerror", (error) => browserErrors.push({ role, error: String(error) }));
      await page.goto(target);
      return { page, context, token: String(session.access_token) };
    }

    const button = (page: Page, name: string) => page.getByRole("button", { name, exact: true });
    const field = (page: Page, name: string) => page.getByLabel(name, { exact: true });
    const choose = (page: Page, label: string, value: string | number) =>
      field(page, label).selectOption(String(value));
    const fill = (page: Page, label: string, value = reason) => field(page, label).fill(value);
    const tab = (page: Page, name: string) =>
      page
        .getByRole("navigation", { name: "Vistas Engineering Manager" })
        .getByRole("button", { name, exact: true })
        .click();

    async function command(page: Page, suffix: string, label: string, status = 200) {
      const [response] = await Promise.all([
        page.waitForResponse(
          (item) => new URL(item.url()).pathname.endsWith(suffix) && ["POST", "PUT"].includes(item.request().method())
        ),
        button(page, label).click(),
      ]);
      mutations.push({ step: stage, status: response.status() });
      expect(response.status(), `${stage}: ${await response.text()}`).toBe(status);
      const busy = page.locator('[aria-label="Engineering Manager"], [aria-label="Engineering Profiles ADMIN"]');
      if (await busy.count()) await expect(busy).toHaveAttribute("aria-busy", "false", { timeout: 30_000 });
      return response.json();
    }

    async function admin(role: string) {
      const session = await actor(role, "/app");
      const mode = button(session.page, "Cambiar a ADMIN MODE");
      // Legacy dashboard bootstrap also runs before ADMIN MODE becomes accessible.
      // Cold container/ORM startup is not an Engineering performance sample.
      await expect(mode).toBeEnabled({ timeout: 180_000 });
      await mode.click();
      for (const name of ["Platform Administration", "Process Configuration"]) {
        const item = button(session.page, name);
        if ((await item.getAttribute("aria-expanded")) !== "true") await item.click();
      }
      await button(session.page, "Process & Operational Configuration").click();
      await button(session.page, "Engineering Profiles").click();
      await expect(session.page.getByRole("region", { name: "Engineering Profiles ADMIN" })).toBeVisible();
      return session;
    }

    async function openDeliverable(page: Page) {
      await button(page, `Ver Entregables ${deliverableCode}`).click();
    }

    async function decide(page: Page, revision: number, action: string) {
      await choose(page, "Decisión de revisión", action);
      await fill(page, "Motivo de decisión de revisión", `${reason}: ${action}`);
      return command(page, `/revisions/${revision}/review-action`, "Registrar decisión de revisión");
    }

    async function read(token: string, suffix: string) {
      const response = await request.get(`${root}${suffix}`, { headers: { Authorization: `Bearer ${token}` } });
      expect(response.status(), suffix).toBe(200);
      return response.json();
    }

    try {
      const configuration = await admin("admin");
      const page = configuration.page;
      await button(page, "Nuevo perfil Engineering").click();
      await fill(page, "Código del perfil Engineering", profileCode);
      await fill(page, "Nombre del perfil Engineering", `Engineering O2A ${run}`);
      await choose(page, "Ámbito del perfil", "workspace");
      await fill(page, "ID Workspace del perfil", String(project));
      await fill(page, "Horizonte Engineering (días)", "28");
      await fill(page, "Agregar código de tipos de entregable", type);
      await button(page, "Agregar tipos de entregable").click();
      await fill(page, "Agregar código de disciplinas", discipline);
      await button(page, "Agregar disciplinas").click();
      for (const label of [
        "Exigir verificación técnica",
        "Exigir documento antes de enviar",
        "Separar aprobador y liberador IFC",
      ]) {
        await field(page, label).check();
      }
      await fill(page, "Motivo del perfil Engineering");
      const profile = await command(page, "/engineering/admin/profiles", "Crear perfil Engineering", 201);
      expect(profile.status).toBe("draft");
      observations.profile_id = profile.id;
      mark("ADMIN_PROFILE_DRAFT_CREATED_WITH_CONTROLLED_CATALOGS");
      stage = "admin-self-publish-denied";
      await fill(page, "Motivo de publicación o sucesión");
      const selfPublished = await command(page, `/profiles/${profile.id}/publish`, "Publicar perfil Engineering", 403);
      expect(selfPublished.detail.code).toBe("ENGINEERING_PROFILE_PUBLICATION_SOD");
      mark("ADMIN_SELF_PUBLICATION_DENIED_BY_SERVER");
      await configuration.context.close();

      stage = "admin-independent-publish";
      const publishing = await admin("publisher");
      await button(publishing.page, `Ver Perfiles Engineering ${profileCode}`).click();
      await fill(publishing.page, "Motivo de publicación o sucesión");
      const published = await command(
        publishing.page,
        `/profiles/${profile.id}/publish`,
        "Publicar perfil Engineering"
      );
      expect(published.status).toBe("published");
      await expect(field(publishing.page, "Nombre del perfil Engineering")).toBeDisabled();
      await proof(publishing.page, "01-admin-profile-published");
      mark("ADMIN_INDEPENDENT_PUBLISH_IMMUTABLE");
      await publishing.context.close();

      stage = "user-create-deliverable";
      const preparing = await actor("preparer");
      const user = preparing.page;
      await button(user, "Nuevo entregable").click();
      await fill(user, "Código de entregable", deliverableCode);
      await fill(user, "Título de entregable", "O2A synthetic approved engineering drawing");
      await choose(user, "Tipo de entregable", type);
      await choose(user, "Disciplina", discipline);
      await fill(user, "Responsable técnico", "O2A Synthetic Design Team");
      await fill(user, "Fecha planificada", asOf());
      await fill(user, "Fecha pronosticada", asOf());
      await fill(user, "Referencia de origen", "O2A-CHROMIUM-SYNTHETIC");
      await fill(user, "Motivo de Ingeniería");
      const deliverable = await command(user, "/deliverables", "Crear entregable", 201);
      const deliverableId = Number(deliverable.id);
      observations.deliverable_id = deliverableId;
      await openDeliverable(user);
      await tab(user, "Revisions");
      stage = "user-create-revision";
      await button(user, "Nueva revisión").click();
      await fill(user, "Código de revisión", "A");
      await choose(user, "Propósito de emisión", "FOR_CONSTRUCTION");
      await fill(user, "Emisión planificada de revisión", asOf());
      await fill(user, "Emisión pronosticada de revisión", asOf());
      await fill(user, "Descripción de revisión", "Initial synthetic technical submission");
      await fill(user, "Motivo de revisión");
      const revision = await command(user, `/deliverables/${deliverableId}/revisions`, "Crear revisión", 201);
      const revisionId = Number(revision.id);
      observations.revision_id = revisionId;
      mark("REGISTER_AND_REVISION_REAL_UI");

      stage = "user-link-real-cde";
      await choose(user, "Adjunto CDE existente", `${fixture.document_id}:${fixture.attachment_id}`);
      await fill(user, "Motivo de vínculo CDE");
      const linked = await command(user, `/revisions/${revisionId}/document`, "Vincular documento CDE");
      expect(JSON.stringify(linked)).toContain(fixture.document_hash);
      observations.document_hash = fixture.document_hash;
      mark("CDE_ATTACHMENT_PINNED_BY_REAL_HASH");

      stage = "user-map-authoritative-targets";
      for (const [kind, id] of [
        ["SCOPE", fixture.scope_item_ids[0]],
        ["PLAN", fixture.plan_item_ids[0]],
        ["EWP", fixture.ewp_ids[0]],
      ]) {
        await choose(user, "Tipo de destino Engineering", kind);
        await choose(user, "Destino Engineering", `${id}::`);
        await fill(user, "Motivo del enlace");
        await command(user, `/revisions/${revisionId}/mappings`, "Agregar enlace Engineering", 201);
      }
      await expect(user.getByRole("table", { name: "Mapeos Engineering" })).toContainText("EWP");
      await proof(user, "02-revision-cde-and-mappings");
      mark("SCOPE_PLAN_EWP_MAPPINGS_REAL_UI");

      stage = "user-submit-technical-review";
      await tab(user, "Reviews & Approvals");
      expect((await decide(user, revisionId, "submit")).review_status).toBe("SUBMITTED");
      await preparing.context.close();

      stage = "reviewer-comment-and-return";
      const reviewing = await actor("reviewer");
      await openDeliverable(reviewing.page);
      await tab(reviewing.page, "Reviews & Approvals");
      await decide(reviewing.page, revisionId, "start");
      await choose(reviewing.page, "Disciplina del comentario", discipline);
      await fill(reviewing.page, "Categoría del comentario", "TECHNICAL");
      await fill(
        reviewing.page,
        "Texto del comentario técnico",
        "Confirm the design dimensions in the controlled description."
      );
      await fill(reviewing.page, "Motivo del comentario");
      const comment = await command(
        reviewing.page,
        `/revisions/${revisionId}/comments`,
        "Registrar comentario técnico",
        201
      );
      expect((await decide(reviewing.page, revisionId, "request_changes")).status).toBe("CHANGES_REQUESTED");
      await proof(reviewing.page, "03-review-comment-and-correction");
      await reviewing.context.close();

      stage = "preparer-respond-and-revise";
      const correction = await actor("preparer");
      await openDeliverable(correction.page);
      await tab(correction.page, "Reviews & Approvals");
      await button(correction.page, `Ver Comentarios Engineering ${comment.id}`).click();
      await choose(correction.page, "Acción sobre comentario", "respond");
      await fill(correction.page, "Respuesta al comentario", "Dimensions verified and revision description updated.");
      await fill(correction.page, "Motivo de respuesta o cierre");
      await command(correction.page, `/review-comments/${comment.id}/transition`, "Registrar respuesta o cierre");
      await tab(correction.page, "Revisions");
      await button(correction.page, "Editar revisión seleccionada").click();
      await fill(
        correction.page,
        "Descripción de revisión",
        "Revised controlled description: design dimensions verified."
      );
      await fill(correction.page, "Motivo de revisión");
      const revised = await command(correction.page, `/revisions/${revisionId}`, "Guardar revisión");
      expect(revised.content_hash).not.toBe(revision.content_hash);
      await correction.context.close();

      stage = "reviewer-close-comment";
      const closing = await actor("reviewer");
      await openDeliverable(closing.page);
      await tab(closing.page, "Reviews & Approvals");
      await button(closing.page, `Ver Comentarios Engineering ${comment.id}`).click();
      await choose(closing.page, "Acción sobre comentario", "close");
      await fill(closing.page, "Motivo de respuesta o cierre");
      expect(
        (await command(closing.page, `/review-comments/${comment.id}/transition`, "Registrar respuesta o cierre"))
          .status
      ).toBe("CLOSED");
      await closing.context.close();

      stage = "round-two-and-independent-approval";
      const resubmit = await actor("preparer");
      await openDeliverable(resubmit.page);
      await tab(resubmit.page, "Reviews & Approvals");
      await decide(resubmit.page, revisionId, "submit");
      await resubmit.context.close();
      const accept = await actor("reviewer");
      await openDeliverable(accept.page);
      await tab(accept.page, "Reviews & Approvals");
      await decide(accept.page, revisionId, "start");
      expect((await decide(accept.page, revisionId, "accept")).review_status).toBe("ACCEPTED");
      await accept.context.close();
      const checker = await actor("checker");
      await openDeliverable(checker.page);
      await tab(checker.page, "Reviews & Approvals");
      expect((await decide(checker.page, revisionId, "check")).checked_by).toBe(fixture.users.checker.id);
      await checker.context.close();
      const approval = await actor("approver");
      await openDeliverable(approval.page);
      await tab(approval.page, "Reviews & Approvals");
      const approved = await decide(approval.page, revisionId, "approve");
      expect(approved.status).toBe("APPROVED");
      await tab(approval.page, "IFC Release");
      await expect(button(approval.page, "Liberar IFC explícitamente")).toHaveCount(0);
      await approval.context.close();
      mark("TWO_ROUNDS_COMMENT_RESPONSE_CLOSE_AND_INDEPENDENT_CHECK_APPROVAL");

      stage = "independent-explicit-ifc";
      const releasing = await actor("releaser");
      await openDeliverable(releasing.page);
      await tab(releasing.page, "IFC Release");
      await fill(releasing.page, "Fecha efectiva IFC", asOf());
      await fill(releasing.page, "Referencia de liberación IFC", `IFC-UAT-${run}`);
      await fill(releasing.page, "Motivo de liberación IFC");
      const released = await command(
        releasing.page,
        `/revisions/${revisionId}/ifc-release`,
        "Liberar IFC explícitamente",
        201
      );
      expect(released.status).toBe("APPROVED");
      expect(released.ifc_release_status).toBe("CURRENT_IFC");
      expect(released.release.release_hash).toMatch(/^[a-f0-9]{64}$/);
      observations.release_hash = released.release.release_hash;
      await proof(releasing.page, "04-independent-ifc-release");
      mark("IFC_EXPLICIT_SEPARATE_ACTOR_AND_RELEASE_HASH");

      stage = "engineering-readiness-then-awp";
      const ewp = Number(fixture.ready_package_id);
      await tab(releasing.page, "Engineering Readiness");
      await choose(releasing.page, "Paquete para Engineering Readiness", ewp);
      await fill(releasing.page, "Fecha de corte Ingeniería", asOf());
      const readiness = releasing.page.getByRole("region", { name: "Engineering Readiness", exact: true });
      await expect(readiness.getByText("ELIGIBLE", { exact: true }).first()).toBeVisible({ timeout: 30_000 });
      const ready = await read(releasing.token, `/readiness?work_package_id=${ewp}&as_of=${asOf()}`);
      expect(ready.status).toBe("ELIGIBLE");
      expect(
        ready.sources.some((source: { release_hash: string }) => source.release_hash === released.release.release_hash)
      ).toBe(true);
      observations.engineering_evidence_hash = ready.evidence_hash;
      await proof(releasing.page, "05-engineering-readiness-provider");
      const awp = await actor("awp_manager", `/workspaces/${project}/awp`);
      await awp.page
        .getByRole("navigation", { name: "AWP submodules" })
        .getByRole("button", { name: "Readiness", exact: true })
        .click();
      await choose(awp.page, "Readiness Package", ewp);
      await fill(awp.page, "Readiness as of", asOf());
      await fill(awp.page, "Motivo AWP");
      const assessed = await command(awp.page, `/packages/${ewp}/assess`, "Evaluar Package Readiness", 201);
      expect(assessed.source_hashes.engineering).toBe(ready.evidence_hash);
      expect(assessed.package.release_state).toBe("NOT_RELEASED");
      observations.awp_assessment_id = assessed.id;
      observations.awp_readiness_state = assessed.readiness_state;
      observations.awp_release_state = assessed.package.release_state;
      await proof(awp.page, "06-awp-provider-consumed-no-release");
      await awp.context.close();
      mark("GOVERNED_ENGINEERING_EVIDENCE_CONSUMED_BY_AWP_NO_PACKAGE_RELEASE");

      stage = "immutability-and-read-timing";
      await tab(releasing.page, "History");
      const historyTable = releasing.page.getByRole("table", { name: "Historial Engineering" });
      const releaseEvent = historyTable
        .getByRole("row")
        .filter({ has: releasing.page.getByRole("cell", { name: "ENGINEERING_IFC_RELEASED", exact: true }) })
        .filter({ has: releasing.page.getByRole("cell", { name: String(released.release.id), exact: true }) });
      for (let page = 0; page < 5; page++) {
        await expect(historyTable).toBeVisible();
        if (await releaseEvent.count()) break;
        const next = releasing.page
          .getByRole("region", { name: "History", exact: true })
          .getByRole("button", { name: "Siguiente página", exact: true });
        if (!(await next.isVisible())) break;
        await next.click();
      }
      await expect(releaseEvent).toHaveCount(1);
      await proof(releasing.page, "07-immutable-history");
      const before = await read(releasing.token, `/revisions/${revisionId}`);
      const auth = { Authorization: `Bearer ${preparing.token}` };
      const denied = await request.put(`${root}/revisions/${revisionId}`, {
        headers: { ...auth, "Idempotency-Key": randomUUID(), "If-Match": `"${before.version}"` },
        data: {
          revision_code: before.revision_code,
          purpose_of_issue: before.purpose_of_issue,
          description: "This terminal revision edit must not persist",
          reason,
        },
      });
      expect(denied.status(), await denied.text()).toBe(409);
      const sampleCount = 20;
      for (let index = 1; index <= sampleCount; index++) {
        const additional = await request.post(`${root}/deliverables`, {
          headers: { ...auth, "Idempotency-Key": randomUUID() },
          data: {
            code: `${deliverableCode}_${index}`,
            title: `O2A synthetic volume ${index}`,
            deliverable_type: type,
            discipline,
            responsible_party: "O2A Synthetic Design Team",
            planned_issue_date: asOf(),
            current_forecast_date: asOf(),
            reason,
          },
        });
        expect(additional.status(), await additional.text()).toBe(201);
      }
      observations.synthetic_additional_deliverables = sampleCount;
      const register = await read(releasing.token, "/deliverables?limit=50");
      observations.register_size = register.items.length;
      const history = await read(releasing.token, "/history?limit=100");
      for (const [operation, suffix] of [
        ["Deliverable Register", "/deliverables?limit=50"],
        ["Revision history", `/deliverables/${deliverableId}/revisions?limit=50`],
        ["Review queue (status projection)", `/status?as_of=${asOf()}`],
        ["IFC release queue (status projection)", `/status?as_of=${asOf()}`],
        ["EWP mapping", `/revisions/${revisionId}/mappings`],
        ["Engineering Readiness", `/readiness?work_package_id=${ewp}&as_of=${asOf()}`],
        ["Engineering Look-Ahead", `/lookahead?as_of=${asOf()}&horizon_days=28`],
      ]) {
        const samples_ms = [];
        for (let iteration = 0; iteration < 3; iteration++) {
          const start = performance.now();
          await read(releasing.token, suffix);
          samples_ms.push(Math.round(performance.now() - start));
        }
        timings.push({ operation, route: suffix, samples_ms, median_ms: [...samples_ms].sort((a, b) => a - b)[1] });
      }
      expect(await read(releasing.token, `/revisions/${revisionId}`)).toEqual(before);
      expect(await read(releasing.token, "/history?limit=100")).toEqual(history);
      await releasing.context.close();
      mark("APPROVED_REVISION_IMMUTABLE_AND_READS_DO_NOT_MUTATE_HISTORY");
      expect(browserErrors).toEqual([]);
      result = "PASS";
    } finally {
      if (result !== "PASS" && lastPage && !lastPage.isClosed())
        await proof(lastPage, "failure").catch(() => undefined);
      writeFileSync(
        path.join(output, "browser-uat.json"),
        JSON.stringify(
          {
            result,
            stage,
            project_workspace_id: project,
            as_of_utc: asOf(),
            checks,
            observations,
            mutations,
            browser_errors: browserErrors,
          },
          null,
          2
        )
      );
      writeFileSync(
        path.join(output, "performance.json"),
        JSON.stringify(
          {
            result: timings.length === 7 ? "MEASURED" : "INCOMPLETE",
            scope: "Local isolated synthetic measurement; not an SLA",
            register_size: observations.register_size ?? null,
            operations: timings,
          },
          null,
          2
        )
      );
    }
  });
});
