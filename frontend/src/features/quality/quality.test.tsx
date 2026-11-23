import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import QualityManagerWorkspace from "./QualityManagerWorkspace";
import QualityProfilesAdminView from "./QualityProfilesAdminView";
import QualityCommandForm, { SourceControl } from "./QualityForms";
import QualityConsumerPanel from "./QualityConsumerPanel";
import { LotLinksPanel, ReadinessAssessmentPanel } from "./QualitySupportPanels";
import { entities } from "./views";
import { permits, type Row, type Scope } from "./api";

const send = (value: Row, status = 200) => new Response(JSON.stringify(value), { status });
const base = "/api/v1/quality/projects/27";
const environment = { token: "quality", base, profile: null, revision: 0 };
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
describe("Quality authority and frozen operator forms", () => {
  it("retries the same source lookup after a recoverable failure without requiring another identity", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(send({ detail: { code: "TEMPORARILY_UNAVAILABLE" } }, 503))
      .mockResolvedValue(
        send({ source_type: "FIELD_PRODUCTION", source_id: 41, source_version: 2, source_hash: "b".repeat(64) })
      );
    vi.stubGlobal("fetch", fetcher);
    render(
      <SourceControl
        field={{ key: "subject", label: "Objeto", types: ["FIELD_PRODUCTION"] }}
        value={undefined}
        change={vi.fn()}
        environment={environment}
        asOf=""
      />
    );
    fireEvent.change(screen.getByLabelText("ID Objeto"), { target: { value: "41" } });
    fireEvent.click(screen.getByRole("button", { name: "Consultar Objeto" }));
    fireEvent.click(await screen.findByRole("button", { name: "Reintentar lectura" }));
    await screen.findByRole("button", { name: "Fijar Objeto" });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it("does not infer native consumer permissions from Quality permissions", () => {
    expect(permits(["quality.inspection.perform"], "inspection.perform")).toBe(true);
    expect(permits(["progress.capture"], "capture")).toBe(false);
  });
  it("uses canonical inspection requests for reinspection and the actual proposed disposition status", () => {
    expect(entities.Reinspections.path).toBe("/inspection-requests");
    expect(entities.Reinspections.reinspectionOnly).toBe(true);
    expect(entities.Dispositions.actions?.find((action) => action.name === "Aprobar disposición")?.states).toEqual([
      "PROPOSED",
    ]);
  });
  it("preserves all Quality views but no writes for an archived workspace", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("/configuration")
          ? send({ profile: { code: "QC", content_json: {} }, allowed_actions: ["read", "plan.edit"] })
          : send({ items: [] })
      )
    );
    render(<QualityManagerWorkspace token="quality" workspaceId={27} readOnly />);
    const navigation = await screen.findByRole("navigation", { name: "Quality Manager submodules" });
    fireEvent.click(within(navigation).getByRole("button", { name: "Quality Plans" }));
    await screen.findByRole("table", { name: "Quality Plans" });
    expect(screen.queryByRole("button", { name: "Nuevo registro Quality" })).not.toBeInTheDocument();
    expect(screen.getByText(/Workspace archivado/)).toBeVisible();
  });
  it("captures a structured checklist from the request frozen template rather than the current profile", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("/document-targets")
          ? send({ items: [{ document_id: 10, attachment_id: 11, document_number: "CDE-10", revision: "A" }] })
          : url.endsWith("/inspection-requests/4")
            ? send({
                id: 4,
                checklist_template: {
                  code: "FROZEN-V1",
                  template_hash: "a".repeat(64),
                  items: [
                    {
                      code: "CHECK-1",
                      label: "Frozen check",
                      response_type: "PASS_FAIL_NA",
                      required: true,
                      evidence_required: true,
                      allow_na: false,
                    },
                  ],
                },
              })
            : send({ items: [{ id: 4, request_number: "REQ-4", status: "IN_INSPECTION" }] })
      )
    );
    const submit = vi.fn(async () => ({ id: 8 }));
    render(
      <QualityCommandForm
        label="Registrar inspección"
        spec={{ capture: "inspection", fields: [{ key: "record_number", label: "Registro", required: true }] }}
        environment={{ ...environment, profile: { checklist_templates: [{ code: "NEW-V9" }] } }}
        busy={false}
        submit={submit}
      />
    );
    await screen.findByRole("option", { name: /REQ-4/ });
    fireEvent.change(screen.getByLabelText("Solicitud de inspección"), { target: { value: "4" } });
    await screen.findByLabelText("CHECK-1 Resultado");
    expect(screen.queryByText("NEW-V9")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("CHECK-1 Resultado"), { target: { value: "PASS" } });
    await screen.findByRole("option", { name: /CDE-10/ });
    fireEvent.change(screen.getByLabelText("CHECK-1 Evidencia CDE"), { target: { value: "10:11" } });
    fireEvent.change(screen.getByLabelText("Registro"), { target: { value: "INS-1" } });
    fireEvent.change(screen.getByLabelText("Motivo operacional"), {
      target: { value: "Verified against frozen template" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Registrar inspección" }));
    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith(
        expect.objectContaining({
          request_id: 4,
          checklist_responses: [
            {
              item_code: "CHECK-1",
              response_code: "PASS",
              evidence_references: [{ document_id: 10, attachment_id: 11 }],
            },
          ],
        })
      )
    );
  });
  it("requires explicit external source pin selection and keeps canonical identity aliases", async () => {
    const fetcher = vi.fn(async () =>
      send({
        source_type: "FIELD_PRODUCTION",
        source_entity_id: 41,
        source_version: 2,
        source_hash: "b".repeat(64),
        subject_key: "FIELD_PRODUCTION:41",
      })
    );
    vi.stubGlobal("fetch", fetcher);
    const submit = vi.fn(async () => ({ id: 3 }));
    render(
      <QualityCommandForm
        label="Crear evidencia"
        spec={{ pins: [{ key: "subject_reference", label: "Objeto", types: ["FIELD_PRODUCTION"], required: true }] }}
        environment={environment}
        busy={false}
        submit={submit}
      />
    );
    fireEvent.change(screen.getByLabelText("ID Objeto"), { target: { value: "41" } });
    fireEvent.click(screen.getByRole("button", { name: "Consultar Objeto" }));
    fireEvent.click(await screen.findByRole("button", { name: "Fijar Objeto" }));
    fireEvent.change(screen.getByLabelText("Motivo operacional"), { target: { value: "Canonical source pinned" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear evidencia" }));
    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith({
        reason: "Canonical source pinned",
        subject_reference: {
          source_type: "FIELD_PRODUCTION",
          source_id: 41,
          source_version: 2,
          source_hash: "b".repeat(64),
        },
      })
    );
  });
  it("protects published Quality profiles and exposes only controlled succession", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        send({
          items: [{ id: 3, code: "QC", name: "Quality profile", status: "published", version: 2, content_json: {} }],
          default_content: {},
          allowed_actions: ["admin.configure", "admin.publish"],
        })
      )
    );
    render(<QualityProfilesAdminView token="quality" />);
    fireEvent.click(await screen.findByRole("button", { name: "Ver Perfiles Quality QC" }));
    expect(screen.getByRole("button", { name: "Crear sucesor Quality…" })).toBeVisible();
    expect(screen.queryByRole("form", { name: "Guardar borrador Quality" })).not.toBeInTheDocument();
  });
  it("refreshes the native parent only after a successful explicit Quality decision", async () => {
    const native = "/api/v1/progress/projects/27/quality-adoptions";
    const source = {
      source_domain: "QUALITY",
      source_entity_type: "ACCEPTANCE",
      source_entity_id: 51,
      source_version: 2,
      source_hash: "a".repeat(64),
      observed_at: "2026-11-19T15:00:00Z",
      version: 0,
      consumer_allowed_actions: ["progress.capture"],
    };
    const fetcher = vi.fn(async (url: string, init?: RequestInit) =>
      url.includes("/lookup")
        ? send(source)
        : init?.method === "POST"
          ? send({ id: 4, decision: "ADOPT" }, 201)
          : send({ items: [] })
    );
    vi.stubGlobal("fetch", fetcher);
    const refresh = vi.fn(async () => {});
    render(<QualityConsumerPanel token="progress" workspaceId={27} onCommitted={refresh} />);
    fireEvent.change(screen.getByLabelText("Evidencia Quality ID"), { target: { value: "51" } });
    fireEvent.click(screen.getByRole("button", { name: "Consultar evidencia Quality" }));
    const form = await screen.findByRole("form", { name: "Registrar decisión Quality PROGRESS" });
    fireEvent.change(within(form).getByLabelText("Decisión sobre evidencia Quality"), { target: { value: "ADOPT" } });
    fireEvent.change(within(form).getByLabelText("Medición Progress pendiente ID"), { target: { value: "21" } });
    fireEvent.change(within(form).getByLabelText("Motivo operacional"), {
      target: { value: "Independent native decision" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Registrar decisión Quality PROGRESS" }));
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    const mutation = fetcher.mock.calls.find(([, init]) => init?.method === "POST");
    expect(mutation?.[0]).toBe(native);
    expect(mutation?.[1]?.headers).toMatchObject({ "If-Match": '"0"', "Idempotency-Key": expect.any(String) });
    expect(JSON.parse(String(mutation?.[1]?.body))).toMatchObject({
      measurement_id: 21,
      decision: "ADOPT",
      source_entity_id: 51,
      source_hash: "a".repeat(64),
    });
  });
  it("uses the server readiness stream version and keeps consult separate from explicit persistence", async () => {
    const command = vi.fn(async () => ({ id: 19 }));
    const fetcher = vi.fn(async (url: string) =>
      url.includes("/source?")
        ? send({
            source_type: "FIELD_PRODUCTION",
            source_id: 41,
            source_version: 2,
            source_hash: "b".repeat(64),
            subject_key: "PRODUCTION:41",
          })
        : send({ items: [], version: 7 })
    );
    vi.stubGlobal("fetch", fetcher);
    const scope: Scope = {
      token: "quality",
      base,
      workspaceId: 27,
      profile: null,
      can: (duty) => duty === "readiness.assess",
      command,
      reload: vi.fn(),
      busy: false,
      error: "",
      message: "",
      revision: 0,
    };
    render(<ReadinessAssessmentPanel scope={scope} />);
    fireEvent.change(screen.getByLabelText("ITP de evaluación ID"), { target: { value: "6" } });
    fireEvent.change(screen.getByLabelText("ID Objeto de evaluación"), { target: { value: "41" } });
    fireEvent.click(screen.getByRole("button", { name: "Consultar Objeto de evaluación" }));
    fireEvent.click(await screen.findByRole("button", { name: "Fijar Objeto de evaluación" }));
    const form = await screen.findByRole("form", { name: "Guardar evaluación Quality" });
    expect(command).not.toHaveBeenCalled();
    expect(
      fetcher.mock.calls.some(([url]) => url.includes("itp_id=6") && url.includes("subject_key=PRODUCTION%3A41"))
    ).toBe(true);
    fireEvent.change(within(form).getByLabelText("Motivo operacional"), {
      target: { value: "Explicit readiness evidence assessment" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Guardar evaluación Quality" }));
    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("/readiness/assess", expect.objectContaining({ itp_id: 6 }), 7)
    );
  });
  it("preserves the previous lot link and typed identities on an append-only successor", async () => {
    const command = vi.fn(async () => ({ id: 21 }));
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("/document-targets")
          ? send({ items: [{ document_id: 10, attachment_id: 11, document_number: "CDE-10", revision: "A" }] })
          : url.includes("/source?")
            ? send({
                source_type: url.includes("MATERIAL_RECEIPT_LINE") ? "MATERIAL_RECEIPT_LINE" : "FIELD_PRODUCTION",
                source_id: url.includes("MATERIAL_RECEIPT_LINE") ? 30 : 41,
                source_version: 2,
                source_hash: "c".repeat(64),
              })
            : send({ items: [], version: 4, latest_id: 17 })
      )
    );
    const scope: Scope = {
      token: "quality",
      base,
      workspaceId: 27,
      profile: null,
      can: () => true,
      command,
      reload: vi.fn(),
      busy: false,
      error: "",
      message: "",
      revision: 0,
    };
    render(<LotLinksPanel scope={scope} />);
    for (const [label, id] of [
      ["Línea de recepción", "30"],
      ["Producción Field", "41"],
    ]) {
      fireEvent.change(screen.getByLabelText(`ID ${label}`), { target: { value: id } });
      fireEvent.click(screen.getByRole("button", { name: `Consultar ${label}` }));
      fireEvent.click(await screen.findByRole("button", { name: `Fijar ${label}` }));
    }
    const form = await screen.findByRole("form", { name: "Registrar vínculo material producción" });
    fireEvent.change(within(form).getByLabelText("Lote"), { target: { value: "LOT-QC-7" } });
    await screen.findByRole("option", { name: /CDE-10/ });
    fireEvent.change(within(form).getByLabelText("Evidencia CDE"), { target: { value: "10:11" } });
    fireEvent.change(within(form).getByLabelText("Motivo operacional"), {
      target: { value: "Corrected material lot association" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Registrar vínculo material producción" }));
    await waitFor(() =>
      expect(command).toHaveBeenCalledWith(
        "/lot-links",
        expect.objectContaining({ supersedes_id: 17, lot_identifiers: { lot: "LOT-QC-7" } }),
        4
      )
    );
  });
});
