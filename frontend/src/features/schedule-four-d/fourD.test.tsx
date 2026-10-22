import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import FourDWorkspace from "./FourDWorkspace";
import { fourDApi, fourDQuery } from "./api";
import { fourDDateInput, itemVisual, shiftFourDDate } from "./visualStates";
import type { FourDItem, FourDView } from "./types";
import type { ScheduleOverview } from "../schedule-foundation/types";

vi.mock("./FourDGeometryView", () => ({ default: () => <div>Geometry projection unit port</div> }));
const item: FourDItem = {
  id: "scope:3:plan:5",
  scope_item_id: 3,
  scope_code: "S-1",
  name: "Slab",
  scope_nature: "INSTALL",
  plan_item_id: 5,
  plan_code: "PLAN-1",
  state: "IN_PROGRESS",
  semantic_state: "INSTALLATION",
  visible: true,
  visual_classes: ["IN_PROGRESS", "BLOCKED_BY_READINESS"],
  activities: [{ external_id: "A1", code: "INSTALL", name: "Install", phase: "EXECUTE", status: "In Progress" }],
  wbs: [{ external_id: "W1", code: "WBS-1", name: "Area A" }],
  packages: [{ id: 6, package_code: "IWP-1", package_type: "IWP" }],
  cwas: [],
  readiness: [],
  constraints: [],
  objects: [],
  derived_models: [],
  mapping_issues: [],
};
const view: FourDView = {
  version: 1,
  source: {
    kind: "CURRENT",
    schedule_version_id: 20,
    register_id: 10,
    baseline_id: null,
    data_date: "2026-10-20T08:00:00-05:00",
    timezone: "America/Bogota",
    content_hash: "source",
  },
  at: "2026-10-20T13:00:00+00:00",
  configuration: {},
  items: [item],
  sources: { current: [], baselines: [] },
  milestones: [{ external_id: "M1", name: "Start", date: "2026-10-19T08:00:00-05:00" }],
  timeline: { start: "2026-10-19", finish: "2026-10-30", data_date: "2026-10-20" },
  period_associations: [{ project_controls_period_id: 7 }],
  source_hashes: {},
  diagnostics: [],
  authority: { cpm_calculation_performed: false },
};
const schedule = {
  registers: [{ id: 10, current_version_id: 20 }],
  versions: [
    { id: 20, status: "ACCEPTED_CURRENT", revision: 2 },
    { id: 21, status: "STAGED", revision: 3 },
    { id: 22, status: "REJECTED", revision: 4 },
  ],
  baselines: [
    { id: 30, status: "APPROVED_BASELINE", baseline_type: "ORIGINAL" },
    { id: 31, status: "DRAFT", baseline_type: "CONTROL" },
  ],
} as ScheduleOverview;
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
describe("4D source fidelity and display", () => {
  it("uses explicit scalar query filters without sending empty values", () => {
    expect(fourDQuery({ source: "CURRENT", at: "2026-10-20", blocked: "true", wbs: "", activity: "A 1" })).toBe(
      "source=CURRENT&at=2026-10-20&blocked=true&activity=A+1"
    );
  });
  it("preserves hidden REMOVE/TEMPORARY even when blocked and styled", () => {
    const result = itemVisual(
      { ...item, visible: false, state: "REMOVED", visual_classes: ["REMOVED", "BLOCKED_BY_READINESS"] },
      { BLOCKED_BY_READINESS: { color: "#123456", opacity: 0.4 } }
    );
    expect(result).toEqual({ color: "#123456", opacity: 0.4, visible: false, semanticClass: "BLOCKED_BY_READINESS" });
  });
  it("does not let invalid color or opacity configure domain visibility", () => {
    expect(itemVisual(item, { BLOCKED_BY_READINESS: { color: "url(unsafe)", opacity: 7 } })).toMatchObject({
      visible: true,
      opacity: 1,
      color: "#e06b18",
    });
  });
  it("steps explicit date across month/year boundaries, never substitutes today", () => {
    expect(shiftFourDDate("2026-12-31", 1)).toBe("2027-01-01");
    expect(shiftFourDDate("2026-03-01", -1)).toBe("2026-02-28");
    expect(shiftFourDDate("", 1)).toBe("");
    expect(shiftFourDDate("2026-10-20T08:00", 1)).toBe("2026-10-21T08:00");
    expect(fourDDateInput("2026-10-20T13:00:00Z", "America/Bogota")).toBe("2026-10-20T08:00");
  });
  it("lists only accepted current and approved baselines, using actual Data Date", async () => {
    const query = vi.spyOn(fourDApi, "view").mockResolvedValue(view);
    render(<FourDWorkspace token="test" workspaceId={77} schedule={schedule} />);
    expect(await screen.findByRole("table", { name: "4D states and traceability" })).toBeInTheDocument();
    expect(screen.getByLabelText("Date 4D")).toHaveValue("2026-10-20T08:00");
    expect(screen.queryByRole("option", { name: /STAGED|REJECTED|DRAFT/ })).not.toBeInTheDocument();
    expect(query).toHaveBeenCalledWith(
      "test",
      77,
      expect.objectContaining({ source: "CURRENT", version_id: "20", at: "" })
    );
  });
  it("uses server filters for Package, WBS, Scope and Plan and exposes 16 filters", async () => {
    const query = vi.spyOn(fourDApi, "view").mockResolvedValue(view);
    render(<FourDWorkspace token="test" workspaceId={77} schedule={schedule} />);
    await screen.findByRole("table", { name: "4D states and traceability" });
    expect(screen.getAllByLabelText(/^Filter 4D /)).toHaveLength(16);
    fireEvent.change(screen.getByLabelText("Filter 4D Package"), { target: { value: "6" } });
    await waitFor(() =>
      expect(query).toHaveBeenLastCalledWith("test", 77, expect.objectContaining({ work_package_id: "6" }))
    );
  });
  it("requests traceability through the authorized source-aware GET port", async () => {
    vi.spyOn(fourDApi, "view").mockResolvedValue(view);
    const trace = vi
      .spyOn(fourDApi, "traceability")
      .mockResolvedValue({ ...view, traceability: { ifc_guid: "OriginalGUID", activity: "A1" } });
    render(<FourDWorkspace token="test" workspaceId={77} schedule={schedule} />);
    fireEvent.click(await screen.findByRole("button", { name: "Traceability S-1" }));
    await waitFor(() =>
      expect(trace).toHaveBeenCalledWith(
        "test",
        77,
        3,
        expect.objectContaining({ source: "CURRENT", version_id: "20" })
      )
    );
    expect(await screen.findByText(/OriginalGUID/)).toBeInTheDocument();
  });
  it("compares baseline/current on the same selected date without a write command", async () => {
    vi.spyOn(fourDApi, "view").mockResolvedValue(view);
    const query = vi.spyOn(fourDApi, "compare").mockResolvedValue({
      baseline: view,
      current: view,
      items: [
        {
          id: item.id,
          scope_item_id: 3,
          plan_item_id: 5,
          baseline_state: "COMPLETED",
          current_state: "IN_PROGRESS",
          variance_classification: "BEHIND_BASELINE",
        },
      ],
    });
    render(<FourDWorkspace token="test" workspaceId={77} schedule={schedule} />);
    await screen.findByRole("table", { name: "4D states and traceability" });
    fireEvent.click(screen.getByLabelText("Compare Baseline Current 4D"));
    await waitFor(() =>
      expect(query).toHaveBeenCalledWith(
        "test",
        77,
        expect.objectContaining({ version_id: "20", baseline_id: "30", at: "2026-10-20T13:00:00+00:00" })
      )
    );
    expect(await screen.findByText("BEHIND_BASELINE")).toBeInTheDocument();
  });
  it("blocks missing accepted sources instead of silently previewing staging", async () => {
    render(<FourDWorkspace token="test" workspaceId={77} schedule={{ ...schedule, versions: [], registers: [] }} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("No existe la fuente gobernada");
  });
});
