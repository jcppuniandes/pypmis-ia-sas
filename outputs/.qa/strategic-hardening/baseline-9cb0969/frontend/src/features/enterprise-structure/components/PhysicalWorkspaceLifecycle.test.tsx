import "@testing-library/jest-dom";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { enterpriseStructureApi } from "../api";
import type { PhysicalWorkspaceInitialization, PhysicalWorkspaceOverview } from "../types";
import PhysicalWorkspaceLifecycle from "./PhysicalWorkspaceLifecycle";

vi.mock("../api", () => ({
  enterpriseStructureApi: {
    physicalWorkspaces: vi.fn(),
    physicalWorkspaceOverview: vi.fn(),
    physicalWorkspaceInitialization: vi.fn(),
    previewPhysicalWorkspaceInitialization: vi.fn(),
    transitionPhysicalWorkspace: vi.fn(),
  },
}));

const api = vi.mocked(enterpriseStructureApi);

const initialization: PhysicalWorkspaceInitialization = {
  result: "FOUND",
  persisted: true,
  initialization_id: 5,
  workspace_id: 81,
  workspace_type_code: "property",
  workspace_name: "Property Atlas",
  workspace_status: "pending",
  business_number: "PYP-PROP-00001",
  record_code: "01.05",
  external_key: "urn:property:81",
  parent: "P&P",
  responsible: "Ana Responsible",
  state: "READY_FOR_ACTIVATION",
  progress_percent: 100,
  blocker_count: 0,
  warning_count: 1,
  common_checklist: [
    { code: "workspace_identity_valid", status: "PASS", message: "Identidad válida", blocking: true, evidence: {} },
  ],
  type_specific_checklist: [
    { code: "property_value_fields_valid", status: "WARNING", message: "Dato opcional", blocking: false, evidence: {} },
  ],
  template_config_id: 9,
  template_code: "PYP-PROP-GENERAL",
  template_revision: 2,
  template_content_hash: "a".repeat(64),
  attributes: { property_type: "general" },
  classifications: [{ category_set_code: "property-type", category_item_code: "general" }],
  enabled_modules: ["scope-manager"],
  planned_modules: ["asset-manager"],
  modules: [
    { module_key: "scope-manager", state: "READY", operational_module_created: false, planned: false, evidence: {} },
    { module_key: "asset-manager", state: "PLANNED", operational_module_created: false, planned: true, evidence: {} },
  ],
  defaults_applied: {},
  assignments: [],
  validation_hash: "b".repeat(64),
  checklist_hash: "c".repeat(64),
  revision_version: 2,
  started_at: "2026-08-13T10:00:00Z",
  ready_at: "2026-08-13T10:01:00Z",
  activated_at: null,
  activated_by_user_id: null,
  failure_code: null,
  failure_reason: null,
  mutation_count: 0,
};

const overview: PhysicalWorkspaceOverview = {
  workspace_id: 81,
  workspace_type_code: "property",
  workspace_name: "Property Atlas",
  business_number: "PYP-PROP-00001",
  record_code: "01.05",
  status: "pending",
  parent_workspace: "P&P",
  responsible: "Ana Responsible",
  template: "PYP-PROP-GENERAL",
  creation_request_id: 7,
  creation_request_number: "PWR-00007",
  created_at: "2026-08-13T09:00:00Z",
  attributes: {},
  classifications: [],
  enabled_modules: ["scope-manager"],
  planned_modules: ["asset-manager"],
  initialization_state: "READY_FOR_ACTIVATION",
  initialization_progress_percent: 100,
  initialization_blocker_count: 0,
  initialization_warning_count: 1,
  blocking_issues: [],
  warnings: ["property_value_fields_valid"],
  template_revision: 2,
  module_states: {},
  activated_at: null,
  activated_by_user_id: null,
  initialization_revision_version: 2,
  can_initialize: false,
  can_activate: true,
};

describe("PhysicalWorkspaceLifecycle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.physicalWorkspaceOverview.mockResolvedValue(overview);
    api.physicalWorkspaceInitialization.mockResolvedValue(initialization);
  });
  afterEach(cleanup);

  it("renders common/type checklists and READY/PLANNED modules", async () => {
    render(<PhysicalWorkspaceLifecycle token="token" workspaceId={81} />);
    expect(await screen.findByText("PROPERTY OVERVIEW")).toBeInTheDocument();
    expect(screen.getByText("Checklist común")).toBeInTheDocument();
    expect(screen.getByText("Checklist property")).toBeInTheDocument();
    expect(screen.getByText("workspace_identity_valid")).toBeInTheDocument();
    expect(screen.getByText("property_value_fields_valid")).toBeInTheDocument();
    expect(screen.getByText("Módulo futuro marcado PLANNED; no se creó persistencia operativa.")).toBeInTheDocument();
  });

  it("offers activation only when the backend capability permits it", async () => {
    api.transitionPhysicalWorkspace.mockResolvedValue({
      ...initialization,
      state: "ACTIVATED",
      workspace_status: "active",
    });
    render(<PhysicalWorkspaceLifecycle token="token" workspaceId={81} />);
    fireEvent.click(await screen.findByRole("button", { name: /Activate Physical Workspace/ }));
    await waitFor(() => expect(api.transitionPhysicalWorkspace).toHaveBeenCalledWith("token", 81, 2, "activate"));
  });

  it("lists and filters My Physical Workspaces", async () => {
    api.physicalWorkspaces.mockResolvedValue([
      {
        workspace_id: 81,
        workspace_type_code: "property",
        workspace_name: "Property Atlas",
        business_number: "PYP-PROP-00001",
        record_code: "01.05",
        workspace_status: "pending",
        initialization_state: "READY_FOR_ACTIVATION",
        parent: "P&P",
        responsible: "Ana Responsible",
        template_code: "PYP-PROP-GENERAL",
        blocker_count: 0,
        warning_count: 1,
        revision_version: 2,
        can_initialize: false,
        can_activate: true,
      },
    ]);
    render(<PhysicalWorkspaceLifecycle token="token" />);
    expect(await screen.findByText("Property Atlas")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Workspace Type"), { target: { value: "property" } });
    await waitFor(() => expect(api.physicalWorkspaces).toHaveBeenLastCalledWith("token", "workspace_type=property"));
  });
});
