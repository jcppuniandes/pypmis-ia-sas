import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { scheduleApi } from "./api";
import ScheduleManagerWorkspace from "./ScheduleManagerWorkspace";
import RegisterWorkspace from "./RegisterWorkspace";
import WbsWorkspace from "./WbsWorkspace";
import { wbsHierarchy } from "./wbsTree";
import ActivitiesWorkspace from "./ActivitiesWorkspace";
import MappingPanel from "./MappingPanel";
import BaselinesWorkspace from "./BaselinesWorkspace";
import ImportExportWorkspace from "./ImportExportWorkspace";
import ReferenceWorkspace from "./ReferenceWorkspace";
import HealthWorkspace from "./HealthWorkspace";
import ScheduleProfilesAdminView from "./ScheduleProfilesAdminView";
import {
  display,
  emptySnapshot,
  type ScheduleOverview,
  type ScheduleRegister,
  type ScheduleVersion,
  type WorkspaceProps,
} from "./types";

const register: ScheduleRegister = {
  id: 10,
  version: 3,
  schedule_code: "SCH-C",
  name: "Control Schedule",
  schedule_type: "CONTROL",
  status: "ACTIVE",
  current_version_id: null,
  baseline_version_id: null,
  calendar_basis: "CAL10",
  timezone: "America/Bogota",
};
const snapshot = {
  ...emptySnapshot(),
  project: { external_id: "P6-1", data_date: "2026-10-20", timezone: "America/Bogota" },
  wbs: [
    { external_id: "W1", code: "ROOT", name: "Schedule root" },
    { external_id: "W2", code: "AREA", name: "Area A", parent_external_id: "W1" },
  ],
  activities: [
    {
      external_id: "A1",
      code: "SLAB",
      name: "Install slab",
      activity_type: "Task Dependent",
      wbs_external_id: "W2",
      calendar_external_id: "CAL10",
      original_duration: 10,
      remaining_duration: 10,
      duration_unit: "HOUR",
      total_float: null,
      free_float: 0,
      critical: false,
    },
  ],
  calendars: [
    {
      external_id: "CAL10",
      name: "Ten hour shift",
      hours_per_day: 10,
      workweek: { Monday: ["07:00-17:00"] },
      exceptions: [{ date: "2026-12-25", work: false }],
    },
  ],
  relationships: [
    {
      external_id: "R1",
      predecessor_external_id: "A0",
      successor_external_id: "A1",
      relationship_type: "SF",
      lag: -2,
      lag_unit: "HOUR",
      is_external: true,
      resolution: "UNRESOLVED",
    },
  ],
  constraints: [{ activity_external_id: "A1", type: "Mandatory Finish", date: "2026-11-15" }],
  codes: [{ external_id: "C1", code: "CIVIL", name: "Civil discipline" }],
  code_assignments: [{ activity_external_id: "A1", code_external_id: "C1" }],
};
const version: ScheduleVersion = {
  id: 20,
  register_id: 10,
  revision: 1,
  version: 4,
  status: "STAGED",
  kind: "INITIAL",
  data_date: "2026-10-20",
  source_file_name: "control.xml",
  source_format: "P6_XML",
  source_hash: "a".repeat(64),
  snapshot_json: snapshot,
  validation_json: { can_accept: false, missing_mappings: ["A1"] },
  diff_json: { activities_added: ["A1"] },
  health_json: { negative_lags: 1 },
  mappings: [],
};
const data: ScheduleOverview = {
  context: { project_workspace_id: 77 },
  configuration: { schedule_types: ["CONTROL", "CONTRACT"], baseline_types: ["ORIGINAL", "CONTROL"] },
  allowed_actions: [],
  registers: [register],
  versions: [version],
  baselines: [],
  mappings: [],
  exports: [],
  period_associations: [],
  scope_items: [{ id: 30, scope_code: "SC-1", name: "Slab", scope_nature: "INSTALL", status: "APPROVED" }],
  plan_items: [
    { id: 40, code: "PLAN-A", name: "Sector A", status: "PUBLISHED" },
    { id: 41, code: "PLAN-B", name: "Sector B", status: "PUBLISHED" },
  ],
  derived_models: [],
  periods: [{ id: 50, period_code: "2026-10", cutoff_at: "2026-10-31T23:59:00-05:00", status: "OPEN" }],
};
const response = (body: unknown) => new Response(JSON.stringify(body));
const props = (actions: string[] = []): WorkspaceProps => ({
  data,
  register,
  selected: version,
  busy: false,
  command: vi.fn().mockResolvedValue({}),
  can: (action) => actions.includes(action),
});

describe("O1B-B frontend contracts — component tests are not real-browser release evidence", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });
  it("uses canonical Schedule Workspace routes without legacy Project fallback", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(response(data));
    await scheduleApi.overview("token", 77);
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/schedule/projects/77/overview");
    expect(fetch.mock.calls).toHaveLength(1);
  });
  it("uses If-Match and idempotency on material commands", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({}));
    await scheduleApi.command(
      "actor",
      77,
      "/versions/20/accept",
      { reason: "Independent acceptance" },
      "stable-key",
      4
    );
    expect(fetch.mock.calls[0][1]).toMatchObject({
      method: "POST",
      headers: { Authorization: "Bearer actor", "Idempotency-Key": "stable-key", "If-Match": '"4"' },
    });
  });
  it("uploads a genuine file to register staging with expected register version", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(response(version));
    const file = new File(["ERMHDR\tP6"], "source.xer");
    await scheduleApi.upload("actor", 77, 10, file, "Controlled source upload", "UPDATE", "upload-key", 3, 20);
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/schedule/projects/77/registers/10/imports");
    const options = fetch.mock.calls[0][1] as RequestInit;
    expect(options.headers).toMatchObject({ "If-Match": '"3"' });
    const body = options.body as FormData;
    expect(body.get("file")).toBe(file);
    expect(body.get("predecessor_version_id")).toBe("20");
  });
  it("shows coherent read-only submodules and no writer controls", async () => {
    vi.spyOn(scheduleApi, "overview").mockResolvedValue(data);
    render(<ScheduleManagerWorkspace token="reader" workspaceId={77} />);
    await screen.findByRole("table", { name: "Schedule Register" });
    expect(
      screen.getByRole("navigation", { name: "Schedule Manager submodules" }).querySelectorAll("button")
    ).toHaveLength(10);
    expect(screen.queryByRole("button", { name: "Crear Schedule Register" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Import / Export" }));
    expect(screen.queryByLabelText("Archivo P6 XML o XER")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aceptar Schedule Current" })).not.toBeInTheDocument();
  });
  it("creates a Schedule Register without guessing hours per day", async () => {
    const p = props(["register.edit"]);
    render(<RegisterWorkspace {...p} />);
    fireEvent.change(screen.getByLabelText("Schedule Code"), { target: { value: "NEW" } });
    fireEvent.change(screen.getByLabelText("Schedule Name"), { target: { value: "Contract schedule" } });
    fireEvent.change(screen.getByLabelText("Motivo Schedule Register"), { target: { value: "Controlled new stream" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear Schedule Register" }));
    expect(p.command).toHaveBeenCalledWith(
      "/registers",
      expect.objectContaining({
        schedule_code: "NEW",
        name: "Contract schedule",
        timezone: "America/Bogota",
        calendar_basis: "EXPLICIT_SOURCE",
      })
    );
    expect(p.command).not.toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ hours_per_day: 8 }));
  });
  it("creates a successor snapshot instead of editing existing WBS or approved data in place", async () => {
    const p = props(["version.edit"]);
    const original = JSON.stringify(snapshot);
    render(<RegisterWorkspace {...p} />);
    fireEvent.click(screen.getByText("Nueva versión manual o sucesora"));
    fireEvent.click(screen.getByRole("button", { name: "Preparar copia de versión seleccionada" }));
    fireEvent.change(screen.getByLabelText("Motivo nueva versión"), {
      target: { value: "Reviewed correction proposal" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Crear nueva Schedule Version" }));
    expect(p.command).toHaveBeenCalledWith(
      "/registers/10/versions",
      expect.objectContaining({ predecessor_version_id: 20, snapshot_json: snapshot }),
      3
    );
    expect(JSON.stringify(snapshot)).toBe(original);
  });
  it("keeps WBS hierarchy separate from Scope hierarchy and handles orphan source parents", () => {
    const tree = wbsHierarchy(snapshot.wbs);
    expect(tree.roots.map((row) => row.external_id)).toEqual(["W1"]);
    expect(tree.children("W1")[0].external_id).toBe("W2");
    expect(wbsHierarchy([{ external_id: "W3", parent_external_id: "EXTERNAL" }]).roots).toHaveLength(1);
    render(<WbsWorkspace {...props()} />);
    expect(screen.getByRole("tree", { name: "WBS hierarchy" })).toHaveTextContent("ROOT");
    expect(screen.getByRole("tree", { name: "WBS hierarchy" })).toHaveTextContent("AREA");
  });
  it("maps multiple Plan Items to an Activity with explicit reason and version", () => {
    const p = props(["mapping.edit"]);
    render(<MappingPanel {...p} targetKind="ACTIVITY" targetId="A1" />);
    fireEvent.click(screen.getByLabelText("Mapear Plan Item PLAN-A"));
    fireEvent.click(screen.getByLabelText("Mapear Plan Item PLAN-B"));
    fireEvent.change(screen.getByLabelText("Motivo mapping"), { target: { value: "Governed many to many mapping" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar mapping Schedule M:N" }));
    expect(p.command).toHaveBeenCalledWith(
      "/versions/20/mappings",
      expect.objectContaining({
        target_kind: "ACTIVITY",
        target_external_id: "A1",
        plan_item_ids: [40, 41],
        scope_item_ids: [],
      }),
      4
    );
  });
  it("maps WBS to approved Scope without silently creating Scope", () => {
    const p = props(["mapping.edit"]);
    render(<MappingPanel {...p} targetKind="WBS" targetId="W2" />);
    fireEvent.click(screen.getByLabelText("Mapear Scope Item SC-1"));
    fireEvent.change(screen.getByLabelText("Motivo mapping"), { target: { value: "Explicit direct scope mapping" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar mapping Schedule M:N" }));
    expect(p.command).toHaveBeenCalledWith(
      "/versions/20/mappings",
      expect.objectContaining({ scope_item_ids: [30], plan_item_ids: [], target_kind: "WBS" }),
      4
    );
    expect(p.command).not.toHaveBeenCalledWith("/items", expect.anything());
  });
  it("does not offer editing mappings of an accepted immutable version", () => {
    render(
      <MappingPanel
        {...props(["mapping.edit"])}
        selected={{ ...version, status: "ACCEPTED_CURRENT" }}
        targetKind="ACTIVITY"
        targetId="A1"
      />
    );
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText(/Una corrección requiere una nueva versión/)).toBeVisible();
  });
  it("does not offer Draft Plan Items or Scope outside the approved current baseline", () => {
    render(
      <MappingPanel
        {...props(["mapping.edit"])}
        targetKind="WBS"
        targetId="W2"
        data={{ ...data, current_scope_item_ids: [], plan_items: [{ ...data.plan_items[0], status: "DRAFT" }] }}
      />
    );
    expect(screen.getByLabelText("Mapear Plan Item PLAN-A")).toBeDisabled();
    expect(screen.queryByLabelText("Mapear Scope Item SC-1")).not.toBeInTheDocument();
  });
  it("respects a profile disabling direct Scope mappings", () => {
    render(
      <MappingPanel
        {...props(["mapping.edit"])}
        targetKind="WBS"
        targetId="W2"
        data={{ ...data, configuration: { content_json: { mapping_policy: { allow_direct_scope: false } } } }}
      />
    );
    expect(screen.queryByLabelText("Mapear Scope Item SC-1")).not.toBeInTheDocument();
    expect(screen.getByText(/no admite vínculos directos/)).toBeVisible();
  });
  it("loads existing mappings for explicit re-review and retains removal as an audit command", () => {
    const p = props(["mapping.edit"]);
    render(
      <MappingPanel
        {...p}
        selected={{
          ...version,
          mappings: [
            {
              target_kind: "ACTIVITY",
              target_external_id: "A1",
              plan_item_ids: [41],
              scope_item_ids: [],
              status: "REQUIRES_REVIEW",
            },
          ],
        }}
        targetKind="ACTIVITY"
        targetId="A1"
      />
    );
    expect(screen.getByLabelText("Mapear Plan Item PLAN-B")).toBeChecked();
    fireEvent.change(screen.getByLabelText("Motivo mapping"), {
      target: { value: "Explicit removal without deleting history" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Retirar mapping Schedule con trazabilidad" }));
    expect(p.command).toHaveBeenCalledWith(
      "/versions/20/mappings",
      {
        target_kind: "ACTIVITY",
        target_external_id: "A1",
        plan_item_ids: [],
        scope_item_ids: [],
        action: "REMOVE",
        reason: "Explicit removal without deleting history",
      },
      4
    );
  });
  it("preserves missing float as UNKNOWN and actual zero or false as source values", () => {
    expect(display(null)).toBe("UNKNOWN");
    expect(display(0)).toBe("0");
    expect(display(false)).toBe("false");
    render(<ActivitiesWorkspace {...props()} />);
    const table = screen.getByRole("table", { name: "Schedule Activities" });
    expect(table).toHaveTextContent("Total UNKNOWN");
    expect(table).toHaveTextContent("Free 0");
    expect(table).toHaveTextContent("Critical false");
  });
  it("preserves ten-hour calendar exceptions without an eight-hour conversion", () => {
    render(<ReferenceWorkspace {...props()} kind="Calendars" />);
    const table = screen.getByRole("table", { name: "Schedule Calendars" });
    expect(table).toHaveTextContent("10");
    expect(table).toHaveTextContent("2026-12-25");
    expect(table).not.toHaveTextContent("8");
  });
  it("shows SF and negative lag with external unresolved references", () => {
    render(<ReferenceWorkspace {...props()} kind="Relationships" />);
    const table = screen.getByRole("table", { name: "Schedule Relationships" });
    expect(table).toHaveTextContent("SF");
    expect(table).toHaveTextContent("-2");
    expect(table).toHaveTextContent("UNRESOLVED");
  });
  it("keeps Activity Codes and constraints as distinct source collections", () => {
    render(<ReferenceWorkspace {...props()} kind="Codes & Constraints" />);
    expect(screen.getByRole("table", { name: "Schedule Constraints" })).toHaveTextContent("Mandatory Finish");
    expect(screen.getByRole("table", { name: "Activity Codes" })).toHaveTextContent("CIVIL");
  });
  it("stages native P6 file without auto-accepting Current or Baseline", () => {
    const upload = vi.fn().mockResolvedValue(undefined);
    const p = props(["import"]);
    render(<ImportExportWorkspace {...p} upload={upload} download={vi.fn()} />);
    const file = new File(["<APIBusinessObjects/>"], "update.xml");
    fireEvent.change(screen.getByLabelText("Archivo P6 XML o XER"), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText("Motivo import Schedule"), {
      target: { value: "Reviewed controlled source" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Importar P6 a staging" }).closest("form")!);
    expect(upload).toHaveBeenCalledWith(file, "Reviewed controlled source", "UPDATE");
    expect(p.command).not.toHaveBeenCalled();
  });
  it("accepts Current only through the explicit reviewed-version command", () => {
    const p = props(["accept"]);
    render(
      <ImportExportWorkspace
        {...p}
        selected={{ ...version, status: "UNDER_REVIEW" }}
        upload={vi.fn()}
        download={vi.fn()}
      />
    );
    fireEvent.change(screen.getByLabelText("Motivo revisión Schedule"), {
      target: { value: "Independent reviewed acceptance" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Aceptar Schedule Current" }));
    expect(p.command).toHaveBeenCalledWith("/versions/20/accept", { reason: "Independent reviewed acceptance" }, 4);
  });
  it("generates only the supported XML export manifest rather than fake CSV roundtrip", () => {
    const p = props(["export"]);
    render(<ImportExportWorkspace {...p} upload={vi.fn()} download={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Export purpose"), { target: { value: "DRAFT_FOR_P6" } });
    fireEvent.change(screen.getByLabelText("Motivo export Schedule"), {
      target: { value: "Manual governed P6 exchange" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generar P6 XML y manifest" }));
    expect(p.command).toHaveBeenCalledWith(
      "/versions/20/exports",
      { format: "XML", purpose: "DRAFT_FOR_P6", reason: "Manual governed P6 exchange" },
      4
    );
  });
  it("uses governed baseline lifecycle independent from accepted Current", () => {
    const p = props(["baseline.approve"]);
    render(
      <BaselinesWorkspace
        {...p}
        data={{
          ...data,
          baselines: [
            {
              id: 60,
              version: 2,
              status: "UNDER_REVIEW",
              schedule_version_id: 20,
              register_id: 10,
              baseline_type: "ORIGINAL",
            },
          ],
        }}
      />
    );
    fireEvent.change(screen.getByLabelText("Motivo transición Baseline"), {
      target: { value: "Independent baseline approval" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Aprobar Schedule Baseline #60" }));
    expect(p.command).toHaveBeenCalledWith("/baselines/60/approve", { reason: "Independent baseline approval" }, 2);
  });
  it("does not expose mutation controls on an approved Baseline", () => {
    render(
      <BaselinesWorkspace
        {...props(["baseline.submit", "baseline.review", "baseline.approve"])}
        data={{
          ...data,
          baselines: [
            {
              id: 60,
              version: 4,
              status: "APPROVED_BASELINE",
              schedule_version_id: 20,
              register_id: 10,
              baseline_type: "ORIGINAL",
              content_hash: "immutable-hash",
            },
          ],
        }}
      />
    );
    expect(screen.getByRole("table", { name: "Schedule Baselines" })).toHaveTextContent("immutable-hash");
    expect(screen.queryByRole("button", { name: /Aprobar Schedule Baseline/ })).not.toBeInTheDocument();
  });
  it("associates period explicitly without forcing Data Date to cutoff", () => {
    const p = props(["period.associate"]);
    render(<BaselinesWorkspace {...p} selected={{ ...version, status: "ACCEPTED_CURRENT" }} />);
    fireEvent.change(screen.getByLabelText("Project Controls Period"), { target: { value: "50" } });
    fireEvent.change(screen.getByLabelText("Motivo asociación Period"), {
      target: { value: "Explicit reporting association" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Asociar Schedule Version a Period" }));
    expect(p.command).toHaveBeenCalledWith(
      "/versions/20/period-associations",
      { period_id: 50, reason: "Explicit reporting association" },
      4
    );
    expect(version.data_date).toBe("2026-10-20");
  });
  it("renders safely before a Schedule Profile has been bound", async () => {
    vi.spyOn(scheduleApi, "overview").mockResolvedValue({ ...data, configuration: null });
    render(<ScheduleManagerWorkspace token="reader" workspaceId={77} />);
    await screen.findByRole("table", { name: "Schedule Register" });
    fireEvent.click(screen.getByRole("button", { name: "Baselines" }));
    expect(screen.getByRole("heading", { name: /Baselines y Current/ })).toBeVisible();
  });
  it("gets float classification from a read-only server query without local CPM calculation", async () => {
    const query = vi.fn().mockResolvedValue([
      {
        ...snapshot.activities[0],
        total_float: 12,
        float_unit: "HOUR",
        near_critical: true,
        criticality_authority: "IMPORTED_P6_FLOAT_PROFILE_THRESHOLD",
      },
    ]);
    render(<ActivitiesWorkspace {...props()} query={query} />);
    await waitFor(() =>
      expect(screen.getByRole("table", { name: "Schedule Activities" })).toHaveTextContent("Near-critical true")
    );
    expect(query).toHaveBeenCalledWith(20);
    expect(screen.getByRole("table", { name: "Schedule Activities" })).toHaveTextContent(
      "IMPORTED_P6_FLOAT_PROFILE_THRESHOLD"
    );
  });
  it("refreshes health through a read-only query rather than mutating validation evidence", async () => {
    const query = vi.fn().mockResolvedValue({ status: "CURRENT", warnings: ["EXTERNAL_LINKS_UNRESOLVED"] });
    const p = props();
    render(<HealthWorkspace {...p} query={query} />);
    await screen.findByText(/EXTERNAL_LINKS_UNRESOLVED/);
    expect(query).toHaveBeenCalledWith(20);
    expect(p.command).not.toHaveBeenCalled();
    expect(version.health_json).toEqual({ negative_lags: 1 });
  });
  it("requires an explicit approved previous baseline when preparing a rebaseline", () => {
    const p = props(["baseline.prepare"]);
    render(
      <BaselinesWorkspace
        {...p}
        selected={{ ...version, status: "ACCEPTED_CURRENT" }}
        data={{
          ...data,
          baselines: [
            {
              id: 60,
              version: 4,
              status: "APPROVED_BASELINE",
              schedule_version_id: 20,
              register_id: 10,
              baseline_type: "ORIGINAL",
            },
          ],
        }}
      />
    );
    fireEvent.change(screen.getByLabelText("Baseline Type"), { target: { value: "CONTROL" } });
    fireEvent.change(screen.getByLabelText("Motivo Baseline Schedule"), {
      target: { value: "Approved successor preparation" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Preparar Schedule Baseline Candidate" }));
    expect(p.command).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Baseline anterior para sucesor"), { target: { value: "60" } });
    fireEvent.click(screen.getByRole("button", { name: "Preparar Schedule Baseline Candidate" }));
    expect(p.command).toHaveBeenCalledWith(
      "/versions/20/baselines",
      { baseline_type: "CONTROL", previous_baseline_id: 60, reason: "Approved successor preparation" },
      4
    );
  });
  it("uses native manifest fields and downloads the actual source file name", () => {
    const download = vi.fn();
    render(
      <ImportExportWorkspace
        {...props()}
        data={{
          ...data,
          exports: [
            { id: 70, schedule_version_id: 20, source_file_name: "actual-p6.xml", manifest_json: { format: "P6_XML" } },
          ],
        }}
        upload={vi.fn()}
        download={download}
      />
    );
    expect(screen.getByRole("table", { name: "Schedule export manifests" })).toHaveTextContent("P6_XML");
    fireEvent.click(screen.getByRole("button", { name: "Descargar P6 XML #70" }));
    expect(download).toHaveBeenCalledWith(70, "actual-p6.xml");
  });
  it("does not allow revalidation after independent review has begun", () => {
    render(
      <ImportExportWorkspace
        {...props(["validate", "accept"])}
        selected={{ ...version, status: "UNDER_REVIEW" }}
        upload={vi.fn()}
        download={vi.fn()}
      />
    );
    expect(screen.queryByRole("button", { name: "Validar Schedule Version" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aceptar Schedule Current" })).toBeVisible();
  });
  it("queries canonical activity classification and health without command headers", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(response({ items: snapshot.activities }))
      .mockResolvedValueOnce(response({ status: "PASS" }));
    expect(await scheduleApi.activities("reader", 77, 20)).toEqual(snapshot.activities);
    expect(await scheduleApi.health("reader", 77, 20)).toEqual({ status: "PASS" });
    expect(fetch.mock.calls.map((call) => call[0])).toEqual([
      "/api/v1/schedule/projects/77/versions/20/activities",
      "/api/v1/schedule/projects/77/versions/20/health",
    ]);
    expect(fetch.mock.calls.every((call) => !call[1]?.method || call[1]?.method === "GET")).toBe(true);
  });
  it("ADMIN creates Schedule Profile through its dedicated guarded API", async () => {
    vi.spyOn(scheduleApi, "profiles").mockResolvedValue({
      items: [],
      default_content: { schedule_types: ["CONTROL"] },
      allowed_actions: ["admin.configure"],
    });
    const write = vi.spyOn(scheduleApi, "profileCommand").mockResolvedValue({
      id: 1,
      version: 1,
      revision: 1,
      code: "PROF",
      name: "Schedule governance",
      status: "DRAFT",
      content_json: {},
    });
    render(<ScheduleProfilesAdminView token="admin" />);
    await screen.findByRole("button", { name: "Crear Schedule Profile DRAFT" });
    fireEvent.change(screen.getByLabelText("Schedule Profile Code"), { target: { value: "PROF" } });
    fireEvent.change(screen.getByLabelText("Schedule Profile Name"), { target: { value: "Schedule governance" } });
    fireEvent.click(screen.getByRole("button", { name: "Crear Schedule Profile DRAFT" }));
    await waitFor(() =>
      expect(write).toHaveBeenCalledWith(
        "admin",
        "",
        expect.objectContaining({ code: "PROF", content_json: { schedule_types: ["CONTROL"] } }),
        expect.any(String),
        undefined,
        "POST"
      )
    );
  });
});
