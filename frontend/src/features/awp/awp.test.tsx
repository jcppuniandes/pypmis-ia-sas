import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AwpWorkspace from "./AwpWorkspace";
import PackagesPanel from "./PackagesPanel";
import ConstraintsPanel from "./ConstraintsPanel";
import ReadinessPanel from "./ReadinessPanel";
import GovernedProfilesAdminView from "./GovernedProfilesAdminView";
import { awpApi, governedProfilesApi } from "./api";
import type { AwpOverview } from "./types";

const overview: AwpOverview = {
  version: 1,
  context: {},
  configuration: {
    content_json: {
      package_types: ["EWP", "IWP", "CUSTOM_SUPPORT"],
      readiness_requirements: { IWP: { required_dimensions: ["ENGINEERING", "ACCESS"] } },
    },
  },
  allowed_actions: [
    "read",
    "cwa.manage",
    "package.edit",
    "package.review",
    "mapping.edit",
    "constraint.raise",
    "constraint.clear",
    "readiness.assess",
    "package.release",
  ],
  cwas: [{ id: 1, version: 1, code: "AREA-A", name: "Area A", status: "ACTIVE" }],
  packages: [
    {
      id: 2,
      version: 7,
      status: "UNDER_REVIEW",
      package_code: "IWP-1",
      name: "Installation",
      package_type: "IWP",
      cwa_id: 1,
      release_state: "NOT_RELEASED",
    },
  ],
  mappings: [],
  effective_mappings: [],
  dependencies: [],
  constraints: [
    {
      id: 4,
      version: 3,
      status: "OPEN",
      code: "ENG-1",
      title: "Drawing not approved",
      constraint_type: "ENGINEERING",
      blocking: true,
    },
  ],
  constraint_mappings: [],
  assessments: [],
  current_readiness: {
    "2": {
      work_package_id: 2,
      readiness_state: "NOT_READY",
      blocking_constraints: [4],
      stale: false,
      dimensions: { ENGINEERING: { state: "BLOCKED" } },
    },
  },
  scope_items: [{ id: 8, scope_code: "S-1", name: "Slab" }],
  current_scope_item_ids: [8],
  plan_items: [{ id: 9, code: "PLAN-1", name: "Sector", status: "PUBLISHED" }],
  schedule_versions: [],
};
const props = (data = overview) => ({
  data,
  busy: false,
  reason: "Controlled change in isolated test",
  can: (action: string) => data.allowed_actions.includes(action),
  command: vi.fn().mockResolvedValue({}),
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
describe("AWP canonical project presentation", () => {
  it("has separate CWA/packages/execution constraint/readiness navigation and no CPM authority", async () => {
    vi.spyOn(awpApi, "overview").mockResolvedValue(overview);
    render(<AwpWorkspace token="test" workspaceId={77} />);
    expect(await screen.findByRole("navigation", { name: "AWP submodules" })).toBeInTheDocument();
    expect(screen.getByText(/ExecutionConstraint ≠ P6 ScheduleConstraint/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Work Packages" }));
    expect(screen.getByRole("table", { name: "Work Packages" })).toBeInTheDocument();
  });
  it("shows configured package extensions rather than a second hardcoded catalog", () => {
    render(<PackagesPanel {...props()} />);
    expect(screen.getByRole("option", { name: "CUSTOM_SUPPORT" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "LOGISTICS" })).not.toBeInTheDocument();
  });
  it("maps published Plan to existing Package with its own ETag and explicit phase", async () => {
    const panel = props();
    render(<PackagesPanel {...panel} />);
    fireEvent.click(screen.getByRole("button", { name: "Ver Package IWP-1" }));
    fireEvent.change(screen.getByLabelText("Mapping PLAN"), { target: { value: "9" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar Package mapping" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith(
        "/packages/2/mappings",
        expect.objectContaining({ target_kind: "PLAN", target_id: 9, phase: "EXECUTE", action: "SET" }),
        7
      )
    );
  });
  it("renders mandatory dimensions from published policy and excludes unsupported evidence keys", () => {
    render(<ReadinessPanel {...props()} />);
    expect(screen.getAllByText("MANDATORY")).toHaveLength(2);
    expect(screen.queryByLabelText("Readiness evidence PROCUREMENT")).not.toBeInTheDocument();
    expect(screen.getByText("MATERIAL / PROCUREMENT")).toBeInTheDocument();
    expect(screen.getByText("RESOURCE / EQUIPMENT")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Release Package independiente" })).toBeDisabled();
  });
  it("submits explicit as-of and evidence separately from independent release", async () => {
    const panel = props();
    render(<ReadinessPanel {...panel} />);
    fireEvent.change(screen.getByLabelText("Readiness as of"), { target: { value: "2026-10-21" } });
    fireEvent.change(screen.getByLabelText("Readiness evidence ENGINEERING"), {
      target: { value: "DRAWING-APPROVED-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Evaluar Package Readiness" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith(
        "/packages/2/assess",
        expect.objectContaining({ as_of: "2026-10-21", evidence_json: { ENGINEERING: "DRAWING-APPROVED-1" } }),
        7
      )
    );
    expect(panel.command).toHaveBeenCalledTimes(1);
  });
  it("does not permit release when readiness source hashes are stale", () => {
    const data = { ...overview, current_readiness: { "2": { readiness_state: "READY", stale: true } } };
    render(<ReadinessPanel {...props(data)} />);
    expect(screen.getByRole("button", { name: "Release Package independiente" })).toBeDisabled();
    expect(screen.getByText("STALE · reevaluar")).toBeInTheDocument();
  });
  it("clears only by explicit command containing evidence and version", async () => {
    const panel = props();
    render(<ConstraintsPanel {...panel} />);
    fireEvent.click(screen.getByRole("button", { name: "Ver Constraint ENG-1" }));
    fireEvent.change(screen.getByLabelText("Constraint clearance evidence"), {
      target: { value: "DRAWING-RELEASE-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Aplicar transición Constraint" }));
    await waitFor(() =>
      expect(panel.command).toHaveBeenCalledWith(
        "/constraints/4/transition",
        expect.objectContaining({ status: "CLEARED", evidence_reference: "DRAWING-RELEASE-1" }),
        3
      )
    );
  });
  it("publishes configuration through governed feature API without user project writes", async () => {
    const profile = {
      id: 11,
      version: 2,
      revision: 1,
      code: "AWP-PROFILE",
      name: "AWP",
      status: "draft",
      content_json: {},
    };
    vi.spyOn(governedProfilesApi, "list").mockResolvedValue({
      items: [profile],
      default_content: {},
      allowed_actions: ["admin.configure", "admin.publish"],
    });
    const command = vi.spyOn(governedProfilesApi, "command").mockResolvedValue(profile);
    render(<GovernedProfilesAdminView token="test" kind="awp" />);
    fireEvent.click(await screen.findByRole("button", { name: "Ver AWP Profiles AWP-PROFILE" }));
    fireEvent.change(screen.getByLabelText("Motivo AWP Profiles"), {
      target: { value: "Publish independently reviewed policy" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Publicar AWP Profiles" }));
    await waitFor(() =>
      expect(command).toHaveBeenCalledWith(
        "test",
        "/api/v1/awp/admin/profiles",
        "/11/publish",
        { reason: "Publish independently reviewed policy" },
        expect.any(String),
        2,
        "POST"
      )
    );
  });
});
