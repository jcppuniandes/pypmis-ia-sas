import "@testing-library/jest-dom";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../api/client";
import { enterpriseStructureApi } from "../api";
import type {
  PhysicalWorkspaceCreationOptions,
  PhysicalWorkspaceCreationRequest,
  PhysicalWorkspaceRequestPreview,
} from "../types";
import PhysicalWorkspaceCreationWorkspace from "./PhysicalWorkspaceCreationWorkspace";

vi.mock("../api", () => ({
  enterpriseStructureApi: {
    physicalCreationOptions: vi.fn(),
    createPhysicalWorkspaceRequest: vi.fn(),
    physicalWorkspaceRequestPreview: vi.fn(),
    physicalWorkspaceRequests: vi.fn(),
    transitionPhysicalWorkspaceRequest: vi.fn(),
    materializePhysicalWorkspaceRequest: vi.fn(),
    physicalWorkspaceOverview: vi.fn(),
  },
}));

const api = vi.mocked(enterpriseStructureApi);

const options: PhysicalWorkspaceCreationOptions = {
  workspace_types: [
    { code: "property", name: "Property", domain_description: "Real Estate" },
    { code: "facility", name: "Facility", domain_description: "" },
    { code: "warehouse", name: "Warehouse", domain_description: "" },
  ],
  selected_workspace_type: "property",
  locations: [{ id: 1, workspace_type_code: "enterprise", name: "P&P", record_code: "01", path: ["P&P"] }],
  templates: [
    {
      id: 41,
      code: "PYP-PROP-GENERAL",
      name: "Property general",
      workspace_type_code: "property",
      applicable_parent_types: ["enterprise"],
      enabled_modules: ["scope-manager"],
    },
  ],
  responsibles: [{ id: 9, name: "Ana Responsible", email: "ana@example.com" }],
  dynamic_attributes: [
    {
      code: "property_type",
      label: "Property Type",
      input_type: "classification",
      required: false,
      read_only: false,
      options: [{ code: "general", label: "General" }],
    },
    {
      code: "address",
      label: "Address",
      input_type: "text",
      required: false,
      read_only: false,
      options: [],
    },
  ],
  classifications: { "property-type": [{ code: "general", label: "General" }] },
  creation_policy: { code: "physical-property-creation" },
  blocked_reason: null,
};

const request: PhysicalWorkspaceCreationRequest = {
  id: 7,
  request_number: "PWR-00007",
  workspace_type_code: "property",
  state: "draft",
  requestor_user_id: 2,
  requestor_name: "Ricardo",
  parent_workspace_id: 1,
  parent_name: "P&P",
  parent_record_code: "01",
  template_config_id: 41,
  template_code: "PYP-PROP-GENERAL",
  template_name: "Property general",
  workspace_name: "Property Atlas",
  description: "Controlled property",
  responsible_user_id: 9,
  responsible_name: "Ana Responsible",
  attributes: { property_type: "general" },
  classifications: [{ category_set_code: "property-type", category_item_code: "general" }],
  revision_version: 1,
  decision_reason: null,
  failure_reason: null,
  approved_by_user_id: null,
  materialized_workspace_id: null,
  materialized_business_number: null,
  materialized_record_code: null,
  created_at: "2026-08-12T10:00:00Z",
  updated_at: "2026-08-12T10:00:00Z",
};

const preview: PhysicalWorkspaceRequestPreview = {
  allowed: true,
  issues: [],
  warnings: [],
  workspace_type: { code: "property" },
  parent: { id: 1 },
  parent_record_code: "01",
  projected_record_code: "01.05",
  projected_business_number: "PYP-PROP-00001",
  template: { code: "PYP-PROP-GENERAL" },
  creation_policy: { code: "physical-property-creation" },
  applicable_classifications: ["property-type"],
  selected_classifications: [{ category_set_code: "property-type", category_item_code: "general" }],
  enabled_modules: ["scope-manager"],
  planned_modules: ["Overview"],
  initial_workspace_status: "pending",
  persisted: false,
};

function renderView(view: "create" | "requests" | "review" | "overview", workspaceId?: number) {
  return render(
    <PhysicalWorkspaceCreationWorkspace onBack={vi.fn()} token="token" view={view} workspaceId={workspaceId} />
  );
}

describe("PhysicalWorkspaceCreationWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.physicalCreationOptions.mockResolvedValue(options);
    api.physicalWorkspaceRequests.mockResolvedValue([]);
  });
  afterEach(() => cleanup());

  it("shows only PROPERTY, FACILITY and WAREHOUSE in the type picker", async () => {
    renderView("create");
    expect(await screen.findByRole("button", { name: /Property/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Facility/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Warehouse/ })).toBeInTheDocument();
    expect(screen.queryByText("REGION")).not.toBeInTheDocument();
    expect(screen.queryByText("ASSET")).not.toBeInTheDocument();
  });

  it("renders the backend-provided location picker and dynamic attributes", async () => {
    renderView("create");
    expect(await screen.findByRole("radiogroup", { name: "Workspace Location Picker" })).toBeInTheDocument();
    expect(screen.getByLabelText("Property Type")).toBeInTheDocument();
    expect(screen.getByLabelText("Address")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Asignado en Materialization")).toBeDisabled();
  });

  it("blocks the intake when templates remain DRAFT", async () => {
    api.physicalCreationOptions.mockResolvedValue({
      ...options,
      templates: [],
      blocked_reason: "NO_PUBLISHED_PHYSICAL_WORKSPACE_TEMPLATE",
    });
    renderView("create");
    expect(await screen.findByText("No hay un Physical Template publicado y aplicable")).toBeInTheDocument();
    expect(screen.getByText(/no las publica automáticamente/i)).toBeInTheDocument();
  });

  it("creates one parametrized draft and renders non-persistent preview", async () => {
    api.createPhysicalWorkspaceRequest.mockResolvedValue(request);
    api.physicalWorkspaceRequestPreview.mockResolvedValue(preview);
    renderView("create");
    fireEvent.change(await screen.findByLabelText("Workspace Name"), { target: { value: "Property Atlas" } });
    fireEvent.click(screen.getByRole("button", { name: /Crear borrador y previsualizar/ }));
    expect(await screen.findByText(/PWR-00007 · Property Atlas/)).toBeInTheDocument();
    expect(screen.getByText("PYP-PROP-00001")).toBeInTheDocument();
    expect(screen.getByText(/no consume Business Number/i)).toBeInTheDocument();
  });

  it("lists My Physical Workspace Requests", async () => {
    api.physicalWorkspaceRequests.mockResolvedValue([request]);
    renderView("requests");
    expect(await screen.findByText("PWR-00007 · PROPERTY")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enviar" })).toBeInTheDocument();
  });

  it("starts review from Physical Workspace Review Queue", async () => {
    const submitted = { ...request, state: "submitted" as const, revision_version: 2 };
    api.physicalWorkspaceRequests.mockResolvedValue([submitted]);
    api.transitionPhysicalWorkspaceRequest.mockResolvedValue({
      ...submitted,
      state: "under_review",
      revision_version: 3,
    });
    renderView("review");
    fireEvent.click(await screen.findByRole("button", { name: "Iniciar revisión" }));
    await waitFor(() =>
      expect(api.transitionPhysicalWorkspaceRequest).toHaveBeenCalledWith("token", submitted, "start-review", undefined)
    );
  });

  it("surfaces a stale If-Match conflict", async () => {
    api.physicalWorkspaceRequests.mockResolvedValue([request]);
    api.transitionPhysicalWorkspaceRequest.mockRejectedValue(
      new ApiError(409, JSON.stringify({ detail: { code: "PHYSICAL_WORKSPACE_REQUEST_VERSION_CONFLICT" } }))
    );
    renderView("requests");
    fireEvent.click(await screen.findByRole("button", { name: "Enviar" }));
    expect(await screen.findByText(/La solicitud cambió/)).toBeInTheDocument();
  });

  it("renders a generic Physical Workspace Overview", async () => {
    api.physicalWorkspaceOverview.mockResolvedValue({
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
      created_at: "2026-08-12T10:00:00Z",
      attributes: { address: "Bogotá" },
      classifications: [{ category_set_code: "property-type", category_item_code: "general" }],
      enabled_modules: ["scope-manager"],
      planned_modules: ["Overview"],
    });
    renderView("overview", 81);
    expect(await screen.findByText("PROPERTY OVERVIEW")).toBeInTheDocument();
    expect(screen.getByText("PYP-PROP-00001")).toBeInTheDocument();
    expect(screen.getByText("Bogotá")).toBeInTheDocument();
  });
});
