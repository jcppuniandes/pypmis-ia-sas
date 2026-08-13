import "@testing-library/jest-dom";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/client";
import { enterpriseStructureApi } from "../api";
import type { ProjectWorkspaceInitialization, ProjectWorkspaceOverview } from "../types";
import ProjectWorkspaceLifecycle from "./ProjectWorkspaceLifecycle";

vi.mock("../api", () => ({
  enterpriseStructureApi: {
    projectWorkspaces: vi.fn(),
    projectWorkspaceOverview: vi.fn(),
    projectWorkspaceInitialization: vi.fn(),
    previewProjectWorkspaceInitialization: vi.fn(),
    transitionProjectWorkspace: vi.fn(),
  },
}));

const api = vi.mocked(enterpriseStructureApi);

const checklist = [
  {
    code: "workspace_identity_valid",
    status: "PASS" as const,
    message: "Identidad válida.",
    blocking: true,
    evidence: {},
  },
  {
    code: "optional_attributes_complete",
    status: "WARNING" as const,
    message: "Hay opcionales pendientes.",
    blocking: false,
    evidence: {},
  },
];

const initialization: ProjectWorkspaceInitialization = {
  result: "FOUND",
  persisted: false,
  initialization_id: null,
  workspace_id: 81,
  workspace_status: "pending",
  state: "NOT_STARTED",
  progress_percent: 50,
  blocker_count: 0,
  warning_count: 1,
  checklist,
  template_config_id: 41,
  template_code: "PYP-PRJ-GENERAL",
  template_revision: 3,
  modules: [{ module_key: "scope-manager", state: "INITIALIZED", configuration_container: "ready", evidence: {} }],
  defaults_applied: {},
  assignments: [],
  validation_hash: null,
  checklist_hash: "hash",
  revision_version: 1,
  started_at: null,
  ready_at: null,
  activated_at: null,
  activated_by_user_id: null,
  failure_code: null,
  failure_reason: null,
  mutation_count: 0,
};

const overview: ProjectWorkspaceOverview = {
  workspace_id: 81,
  project_name: "Project Atlas",
  project_number: "PYP-PRJ-00001",
  record_code: "01.03.02.01",
  status: "pending",
  parent_workspace: "Capital Portfolio",
  project_manager: "Ana PM",
  template: "PYP-PRJ-GENERAL",
  strategic_objectives: ["growth"],
  planned_start: null,
  planned_finish: null,
  currency: "COP",
  estimated_budget: null,
  enabled_modules: ["scope-manager"],
  initialization_state: "NOT_STARTED",
  initialization_progress_percent: 50,
  initialization_blocker_count: 0,
  initialization_warning_count: 1,
  blocking_issues: [],
  warnings: ["Hay opcionales pendientes."],
  template_revision: 3,
  module_states: {},
  activated_at: null,
  activated_by_user_id: null,
  initialization_revision_version: 1,
  can_initialize: true,
  can_activate: false,
};

describe("ProjectWorkspaceLifecycle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.projectWorkspaceOverview.mockResolvedValue(overview);
    api.projectWorkspaceInitialization.mockResolvedValue(initialization);
    api.projectWorkspaces.mockResolvedValue([]);
  });
  afterEach(() => cleanup());

  it("shows workspace and initialization states independently", async () => {
    render(<ProjectWorkspaceLifecycle token="token" workspaceId={81} />);
    expect(await screen.findByText("Project Atlas")).toBeInTheDocument();
    expect(screen.getByText("pending")).toBeInTheDocument();
    expect(screen.getByText("No iniciada")).toBeInTheDocument();
  });

  it("shows template revision and progress", async () => {
    render(<ProjectWorkspaceLifecycle token="token" workspaceId={81} />);
    expect(await screen.findByText(/PYP-PRJ-GENERAL/)).toHaveTextContent("r3");
    expect(screen.getByText("50%")).toBeInTheDocument();
  });

  it("renders the backend checklist", async () => {
    render(<ProjectWorkspaceLifecycle token="token" workspaceId={81} />);
    expect(await screen.findByText("workspace_identity_valid")).toBeInTheDocument();
    expect(screen.getByText("optional_attributes_complete")).toBeInTheDocument();
  });

  it("marks blocking checks", async () => {
    render(<ProjectWorkspaceLifecycle token="token" workspaceId={81} />);
    expect(await screen.findByText("Blocking")).toBeInTheDocument();
  });

  it("shows the minimal module container", async () => {
    render(<ProjectWorkspaceLifecycle token="token" workspaceId={81} />);
    expect(await screen.findByText("scope-manager")).toBeInTheDocument();
    expect(screen.getByText(/sin configuración operativa profunda/i)).toBeInTheDocument();
  });

  it("requests a nonpersistent preview", async () => {
    api.previewProjectWorkspaceInitialization.mockResolvedValue({ ...initialization, result: "PREVIEW" });
    render(<ProjectWorkspaceLifecycle token="token" workspaceId={81} />);
    fireEvent.click(await screen.findByRole("button", { name: "Initialization Preview" }));
    await waitFor(() => expect(api.previewProjectWorkspaceInitialization).toHaveBeenCalledWith("token", 81));
    expect(await screen.findByText("Cerrar preview")).toBeInTheDocument();
  });

  it("starts initialization with If-Match version", async () => {
    api.transitionProjectWorkspace.mockResolvedValue({
      ...initialization,
      persisted: true,
      state: "READY_FOR_ACTIVATION",
      revision_version: 2,
    });
    render(<ProjectWorkspaceLifecycle token="token" workspaceId={81} />);
    fireEvent.click(await screen.findByRole("button", { name: "Start Initialization" }));
    await waitFor(() => expect(api.transitionProjectWorkspace).toHaveBeenCalledWith("token", 81, 1, "start"));
  });

  it("hides activation until backend capability and ready state", async () => {
    render(<ProjectWorkspaceLifecycle token="token" workspaceId={81} />);
    await screen.findByText("Project Atlas");
    expect(screen.queryByRole("button", { name: "Activate Project Workspace" })).not.toBeInTheDocument();
  });

  it("shows activation for an authorized ready workspace", async () => {
    api.projectWorkspaceOverview.mockResolvedValue({
      ...overview,
      can_initialize: false,
      can_activate: true,
      initialization_state: "READY_FOR_ACTIVATION",
    });
    api.projectWorkspaceInitialization.mockResolvedValue({
      ...initialization,
      persisted: true,
      state: "READY_FOR_ACTIVATION",
      revision_version: 4,
    });
    render(<ProjectWorkspaceLifecycle token="token" workspaceId={81} />);
    expect(await screen.findByRole("button", { name: "Activate Project Workspace" })).toBeInTheDocument();
  });

  it("activates with the current revision", async () => {
    api.projectWorkspaceOverview.mockResolvedValue({
      ...overview,
      can_initialize: false,
      can_activate: true,
      initialization_state: "READY_FOR_ACTIVATION",
    });
    api.projectWorkspaceInitialization.mockResolvedValue({
      ...initialization,
      persisted: true,
      state: "READY_FOR_ACTIVATION",
      revision_version: 4,
    });
    api.transitionProjectWorkspace.mockResolvedValue({
      ...initialization,
      persisted: true,
      state: "ACTIVATED",
      workspace_status: "active",
      revision_version: 5,
    });
    render(<ProjectWorkspaceLifecycle token="token" workspaceId={81} />);
    fireEvent.click(await screen.findByRole("button", { name: "Activate Project Workspace" }));
    await waitFor(() => expect(api.transitionProjectWorkspace).toHaveBeenCalledWith("token", 81, 4, "activate"));
  });

  it("renders My Project Workspaces inventory", async () => {
    api.projectWorkspaces.mockResolvedValue([
      {
        workspace_id: 81,
        project_name: "Project Atlas",
        project_number: "PYP-PRJ-00001",
        record_code: "01.03.02.01",
        workspace_status: "pending",
        initialization_state: "NOT_STARTED",
        template_code: "PYP-PRJ-GENERAL",
        project_manager: "Ana PM",
        blocker_count: 0,
        warning_count: 1,
        revision_version: 1,
        can_initialize: true,
        can_activate: false,
      },
    ]);
    render(<ProjectWorkspaceLifecycle token="token" />);
    expect(await screen.findByText("Project Atlas")).toBeInTheDocument();
    expect(screen.getByText("PYP-PRJ-00001")).toBeInTheDocument();
  });

  it("filters the inventory by pending status", async () => {
    render(<ProjectWorkspaceLifecycle token="token" />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "pending" } });
    await waitFor(() => expect(api.projectWorkspaces).toHaveBeenCalledWith("token", "pending"));
  });

  it("opens a workspace from inventory", async () => {
    api.projectWorkspaces.mockResolvedValue([
      {
        workspace_id: 81,
        project_name: "Project Atlas",
        project_number: "PYP-PRJ-00001",
        record_code: "01.03.02.01",
        workspace_status: "pending",
        initialization_state: "NOT_STARTED",
        template_code: "PYP-PRJ-GENERAL",
        project_manager: "Ana PM",
        blocker_count: 0,
        warning_count: 1,
        revision_version: 1,
        can_initialize: true,
        can_activate: false,
      },
    ]);
    render(<ProjectWorkspaceLifecycle token="token" />);
    fireEvent.click(await screen.findByRole("button", { name: "Abrir" }));
    expect(await screen.findByText("Initialization Checklist")).toBeInTheDocument();
  });

  it("shows a friendly stale-version conflict", async () => {
    api.transitionProjectWorkspace.mockRejectedValue(
      new ApiError(409, JSON.stringify({ detail: { code: "PROJECT_WORKSPACE_VERSION_CONFLICT" } }))
    );
    render(<ProjectWorkspaceLifecycle token="token" workspaceId={81} />);
    fireEvent.click(await screen.findByRole("button", { name: "Start Initialization" }));
    expect(await screen.findByText(/El workspace cambió/)).toBeInTheDocument();
  });

  it("shows activated state without mutation actions", async () => {
    api.projectWorkspaceOverview.mockResolvedValue({
      ...overview,
      status: "active",
      initialization_state: "ACTIVATED",
      can_initialize: false,
      can_activate: false,
      project_manager: "",
      currency: "",
      template: "",
      template_revision: null,
      activated_at: null,
    });
    api.projectWorkspaceInitialization.mockResolvedValue({
      ...initialization,
      persisted: false,
      state: "ACTIVATED",
      workspace_status: "active",
      progress_percent: 100,
      template_code: "",
      template_revision: null,
      activated_at: null,
    });
    render(<ProjectWorkspaceLifecycle token="token" workspaceId={81} />);
    expect(await screen.findByText("Workspace operativo")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start Initialization" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Initialization Preview" })).not.toBeInTheDocument();
    expect(screen.getByText("Sin snapshot histórico")).toBeInTheDocument();
    expect(screen.getByText("Activo (registro histórico)")).toBeInTheDocument();
  });
});
