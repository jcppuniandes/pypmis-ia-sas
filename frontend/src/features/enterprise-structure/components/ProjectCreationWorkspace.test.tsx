import "@testing-library/jest-dom";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/client";
import { enterpriseStructureApi } from "../api";
import type { ProjectCreationOptions, ProjectCreationRequest } from "../types";
import ProjectCreationWorkspace from "./ProjectCreationWorkspace";

vi.mock("../api", () => ({
  enterpriseStructureApi: {
    projectCreationOptions: vi.fn(),
    createProjectRequest: vi.fn(),
    previewProjectSource: vi.fn(),
    createProjectFromSource: vi.fn(),
    projectRequestPreview: vi.fn(),
    projectRequests: vi.fn(),
    transitionProjectRequest: vi.fn(),
    materializeProjectRequest: vi.fn(),
    projectWorkspaceOverview: vi.fn(),
    projectWorkspaceInitialization: vi.fn(),
    projectWorkspaces: vi.fn(),
    previewProjectWorkspaceInitialization: vi.fn(),
    transitionProjectWorkspace: vi.fn(),
  },
}));

const api = vi.mocked(enterpriseStructureApi);

const options: ProjectCreationOptions = {
  locations: [
    {
      id: 21,
      workspace_type_code: "portfolio",
      name: "Capital Portfolio",
      record_code: "001.001",
      path: ["P&P", "Enterprise", "Capital Portfolio"],
    },
  ],
  templates: [
    {
      id: 41,
      code: "PYP-PRJ-GENERAL",
      name: "Proyecto general",
      applicable_parent_types: ["portfolio", "program"],
      enabled_modules: ["scope-manager"],
    },
  ],
  managers: [{ id: 9, name: "Ana PM", email: "ana@example.com" }],
  strategic_objectives: [{ code: "growth", label: "Sustainable Growth" }],
  classifications: { region: [{ code: "andean", label: "Andean" }] },
  allowed_governance_models: [
    {
      code: "CAPITAL_OWNER",
      label: "Capital Owner",
      source_context_type: "STRATEGIC_GATE_DECISION",
    },
    {
      code: "CONTRACTOR_DELIVERY",
      label: "Contractor Delivery",
      source_context_type: "CONTRACT_AWARD",
    },
    {
      code: "DIRECT_INTERNAL",
      label: "Direct Internal",
      source_context_type: "DIRECT_AUTHORIZATION",
    },
  ],
  allowed_source_context_types: ["STRATEGIC_GATE_DECISION", "CONTRACT_AWARD", "DIRECT_AUTHORIZATION"],
  can_create_direct: true,
  can_create_from_contract: true,
  can_create_from_strategic_gate: true,
  blocked_reason: null,
};

const request: ProjectCreationRequest = {
  id: 7,
  request_number: "PCR-00007",
  state: "draft",
  requestor_user_id: 2,
  requestor_name: "Ricardo",
  governance_model: "DIRECT_INTERNAL",
  source_context_type: "DIRECT_AUTHORIZATION",
  source_context_id: null,
  source_external_key: "AUTH-001",
  idempotency_key: "AUTH-001",
  source_snapshot: { authorization_reference: "AUTH-001", sponsor: "COO" },
  source_hash: "source-hash",
  creation_policy_id: 90,
  creation_policy_revision: 1,
  creation_policy_hash: "policy-hash",
  parent_workspace_id: 21,
  parent_name: "Capital Portfolio",
  parent_record_code: "001.001",
  project_template_config_id: 41,
  template_code: "PYP-PRJ-GENERAL",
  template_name: "Proyecto general",
  project_name: "Project Atlas",
  description: "Controlled project",
  project_manager_user_id: 9,
  project_manager_name: "Ana PM",
  planned_start: "2026-09-01",
  planned_finish: "2027-08-31",
  currency_code: "COP",
  estimated_budget: "1000.00",
  project_type: null,
  project_phase: null,
  priority: null,
  country: "CO",
  region: null,
  strategic_objective_codes: ["growth"],
  revision_version: 1,
  decision_reason: null,
  failure_reason: null,
  approved_by_user_id: null,
  materialized_workspace_id: null,
  materialized_project_number: null,
  materialized_record_code: null,
  created_at: "2026-08-12T10:00:00Z",
  updated_at: "2026-08-12T10:00:00Z",
};

function renderView(view: "create" | "requests" | "review" | "workspaces" | "overview", workspaceId?: number) {
  return render(
    <ProjectCreationWorkspace onBack={vi.fn()} projectWorkspaceId={workspaceId} token="token" view={view} />
  );
}

describe("ProjectCreationWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.projectCreationOptions.mockResolvedValue(options);
    api.projectRequests.mockResolvedValue([]);
    api.projectWorkspaces.mockResolvedValue([]);
  });

  afterEach(() => cleanup());

  it("shows a controlled blocked state when no template is published", async () => {
    api.projectCreationOptions.mockResolvedValue({
      ...options,
      templates: [],
      blocked_reason: "NO_PUBLISHED_PROJECT_TEMPLATE",
    });
    renderView("create");
    expect(await screen.findByText("No hay una Project Template publicada y aplicable")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Guardar solicitud/ })).not.toBeInTheDocument();
  });

  it("renders eligible locations as a selectable enterprise tree", async () => {
    renderView("create");
    expect(await screen.findByRole("radiogroup", { name: "Ubicación del proyecto" })).toBeInTheDocument();
    expect(screen.getByText("P&P / Enterprise / Capital Portfolio · 001.001")).toBeInTheDocument();
  });

  it("uses governance independently from project type and requires the direct source", async () => {
    renderView("create");
    const save = await screen.findByRole("button", { name: /Guardar solicitud y previsualizar/ });
    expect(save).toBeDisabled();
    expect(screen.getByRole("radio", { name: /Direct Internal/ })).toBeChecked();
    fireEvent.change(screen.getByLabelText("Referencia de autorización"), { target: { value: "AUTH-001" } });
    fireEvent.change(screen.getByLabelText("Patrocinador"), { target: { value: "COO" } });
    expect(save).toBeEnabled();
  });

  it("creates a draft and displays a non-persistent preview", async () => {
    api.previewProjectSource.mockResolvedValue({
      governance_model: "DIRECT_INTERNAL",
      source_context_type: "DIRECT_AUTHORIZATION",
      source_context_id: null,
      source_external_key: "AUTH-001",
      source_hash: "source-hash",
      effective_policy: {},
      source_workspace_id: null,
      resolution_chain: ["tenant"],
      required_fields: [],
      optional_fields: [],
      required_source: ["authorization_reference", "sponsor"],
      initialization_requirements: [],
      activation_requirements: [],
      warnings: [],
      blockers: [],
      persisted: false,
    });
    api.createProjectFromSource.mockResolvedValue(request);
    api.projectRequestPreview.mockResolvedValue({
      allowed: true,
      issues: [],
      parent_workspace_id: 21,
      parent_name: "Capital Portfolio",
      parent_record_code: "001.001",
      projected_record_code: "001.001.001",
      projected_project_number: "PYP-PRJ-0001",
      inherited_classifications: [],
      selected_classifications: [],
      enabled_modules: ["scope-manager"],
      initial_workspace_status: "pending",
      template: {},
      creation_policy: {},
      governance_model: "DIRECT_INTERNAL",
      source_context_type: "DIRECT_AUTHORIZATION",
      effective_policy: {},
      policy_source_workspace_id: null,
      policy_resolution_chain: ["tenant"],
      required_fields: [],
      optional_fields: [],
      warnings: [],
      blockers: [],
      activation_readiness: "BLOCKED",
      persisted: false,
      notice: "Preview only - final number assigned at creation",
    });
    renderView("create");
    fireEvent.change(await screen.findByLabelText("Nombre del proyecto"), { target: { value: "Project Atlas" } });
    fireEvent.change(screen.getByLabelText("Referencia de autorización"), { target: { value: "AUTH-001" } });
    fireEvent.change(screen.getByLabelText("Patrocinador"), { target: { value: "COO" } });
    fireEvent.click(screen.getByRole("button", { name: /Guardar solicitud y previsualizar/ }));
    expect(await screen.findByText(/PCR-00007 · Project Atlas/)).toBeInTheDocument();
    expect(screen.getByText("PYP-PRJ-0001")).toBeInTheDocument();
    expect(screen.getByText(/no consume numeración/i)).toBeInTheDocument();
  });

  it("lists My Project Requests with lifecycle state", async () => {
    api.projectRequests.mockResolvedValue([request]);
    renderView("requests");
    expect(await screen.findByText("PCR-00007")).toBeInTheDocument();
    expect(screen.getByText("Borrador")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enviar" })).toBeInTheDocument();
  });

  it("starts review from the dedicated Review Queue", async () => {
    const submitted = { ...request, state: "submitted" as const, revision_version: 2 };
    api.projectRequests.mockResolvedValue([submitted]);
    api.transitionProjectRequest.mockResolvedValue({ ...submitted, state: "under_review", revision_version: 3 });
    renderView("review");
    fireEvent.click(await screen.findByRole("button", { name: "Iniciar revisión" }));
    await waitFor(() =>
      expect(api.transitionProjectRequest).toHaveBeenCalledWith("token", submitted, "start-review", undefined)
    );
  });

  it("shows a clear stale-version conflict", async () => {
    api.projectRequests.mockResolvedValue([request]);
    api.transitionProjectRequest.mockRejectedValue(
      new ApiError(409, JSON.stringify({ detail: { code: "REQUEST_VERSION_CONFLICT" } }))
    );
    renderView("requests");
    fireEvent.click(await screen.findByRole("button", { name: "Enviar" }));
    expect(await screen.findByText(/La solicitud cambió desde que la abrió/)).toBeInTheDocument();
  });

  it("renders Project Overview from the canonical workspace", async () => {
    api.projectWorkspaceOverview.mockResolvedValue({
      workspace_id: 81,
      project_name: "Project Atlas",
      project_number: "PYP-PRJ-0001",
      record_code: "001.001.001",
      status: "pending",
      parent_workspace: "Capital Portfolio",
      project_manager: "Ana PM",
      template: "PYP-PRJ-GENERAL",
      strategic_objectives: ["growth"],
      governance_model: "DIRECT_INTERNAL",
      governance_label: "Direct Internal",
      creation_source: "DIRECT_AUTHORIZATION",
      source_reference: "AUTH-001",
      source_snapshot: { authorization_reference: "AUTH-001", sponsor: "COO" },
      creation_policy: {},
      pending_reason: "INITIALIZATION_REQUIRED",
      planning_stage: "DIRECT_AUTHORIZATION",
      activation_readiness: "BLOCKED",
      planned_start: "2026-09-01",
      planned_finish: "2027-08-31",
      currency: "COP",
      estimated_budget: "1000.00",
      enabled_modules: ["scope-manager"],
      initialization_state: "NOT_STARTED",
      initialization_progress_percent: 0,
      initialization_blocker_count: 1,
      initialization_warning_count: 0,
      blocking_issues: ["Debe iniciar la inicialización"],
      warnings: [],
      template_revision: 1,
      module_states: {},
      activated_at: null,
      activated_by_user_id: null,
      initialization_revision_version: 1,
      can_initialize: true,
      can_activate: false,
    });
    api.projectWorkspaceInitialization.mockResolvedValue({
      result: "FOUND",
      persisted: false,
      initialization_id: null,
      workspace_id: 81,
      workspace_status: "pending",
      state: "NOT_STARTED",
      progress_percent: 94,
      blocker_count: 1,
      warning_count: 0,
      checklist: [
        {
          code: "template_snapshot_valid",
          status: "PASS",
          message: "La plantilla coincide.",
          blocking: true,
          evidence: {},
        },
      ],
      template_config_id: 41,
      template_code: "PYP-PRJ-GENERAL",
      template_revision: 1,
      modules: [
        {
          module_key: "scope-manager",
          state: "INITIALIZED",
          configuration_container: "ready",
          evidence: {},
        },
      ],
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
    });
    renderView("overview", 81);
    expect(
      await screen.findByText((_content, element) =>
        Boolean(element?.tagName === "SMALL" && element.textContent?.includes("PYP-PRJ-0001"))
      )
    ).toBeInTheDocument();
    expect(screen.getByText("scope-manager")).toBeInTheDocument();
  });
});
