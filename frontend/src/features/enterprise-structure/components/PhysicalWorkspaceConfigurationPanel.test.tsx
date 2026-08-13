import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PhysicalWorkspaceConfigurationPanel from "./PhysicalWorkspaceConfigurationPanel";

const {
  physicalConfiguration,
  previewPhysicalWorkspace,
  updatePhysicalComposition,
  updatePhysicalNumbering,
  updatePhysicalCreationPolicy,
} = vi.hoisted(() => ({
  physicalConfiguration: vi.fn(),
  previewPhysicalWorkspace: vi.fn(),
  updatePhysicalComposition: vi.fn(),
  updatePhysicalNumbering: vi.fn(),
  updatePhysicalCreationPolicy: vi.fn(),
}));

vi.mock("../api", () => ({
  enterpriseStructureApi: {
    physicalConfiguration,
    previewPhysicalWorkspace,
    updatePhysicalComposition,
    updatePhysicalNumbering,
    updatePhysicalCreationPolicy,
  },
}));

const type = (code: string, extra: Record<string, unknown> = {}) => ({
  id: code.length,
  kind: "workspace_type",
  code,
  name: code === "property" ? "Property" : code,
  description: code === "property" ? "Real Estate Workspace" : `${code} definition`,
  status: "published",
  revision: 1,
  version: 1,
  content_hash: "a".repeat(64),
  published_at: "2026-08-12T00:00:00Z",
  content_json: {
    repeatable: true,
    hierarchical_record_code: true,
    admin_configurable: true,
    user_mode_enabled: code !== "linear-asset",
    template_supported: code !== "linear-asset",
    workspace_attributes: [`${code} Name`, "Country", "Address"],
    ...extra,
  },
});

const configuration = {
  workspace_types: [
    type("region"),
    type("district"),
    type("site"),
    type("property", { business_numbering: true, domain_description: "Real Estate" }),
    type("facility", { business_numbering: true }),
    type("warehouse", { business_numbering: true }),
    type("linear-asset", { reserved: true, active: false, creation_process_supported: false }),
  ],
  composition_rules: {
    enterprise: ["region", "site", "property", "facility", "warehouse"],
    region: ["district", "site", "property", "facility", "warehouse"],
    district: ["site", "property", "facility", "warehouse"],
    site: ["property", "facility", "warehouse"],
    property: ["facility", "warehouse"],
    facility: ["warehouse"],
    warehouse: [],
  },
  templates: [
    {
      ...type("PYP-PROP-GENERAL"),
      id: 70,
      kind: "physical_template",
      status: "draft",
      content_json: { workspace_type_code: "property" },
    },
  ],
  numbering_rules: [
    {
      ...type("physical-property"),
      id: 80,
      kind: "numbering_rule",
      code: "physical-property",
      content_json: { prefix: "PYP-PROP", padding: 5, configuration_version: "gate-06a-v1.0" },
    },
  ],
  creation_policies: [
    {
      ...type("physical-property-creation"),
      id: 90,
      kind: "creation_policy",
      status: "draft",
      content_json: { workspace_type_code: "property", template_required: true, configuration_only: true },
    },
  ],
  available_modules: [],
  parent_options: [
    { id: 1, name: "Enterprise", workspace_type_code: "enterprise", record_code: "01", status: "active" },
  ],
  relationship_contract: [{ source: "project", target: "property", relationship_type: "LOCATED_AT" }],
  summary: { active_types: 6, reserved_types: 1, draft_templates: 5, draft_policies: 3, real_instances: 0 },
  gate_status: "READY_FOR_PHYSICAL_WORKSPACE_CREATION_PROCESSES",
  exclusions: { asset_is_workspace_type: false, linear_asset_creatable: false },
};

describe("PhysicalWorkspaceConfigurationPanel", () => {
  beforeEach(() => {
    physicalConfiguration.mockResolvedValue(configuration);
    previewPhysicalWorkspace.mockResolvedValue({
      allowed: true,
      workspace_type_code: "property",
      parent: configuration.parent_options[0],
      template_code: "PYP-PROP-GENERAL",
      projected_record_code: "01.02",
      projected_business_number: "PYP-PROP-00001",
      applicable_classifications: ["property-type"],
      enabled_modules: [],
      planned_modules: ["Overview"],
      initial_status: "pending",
      issues: [],
      warnings: [],
      persisted: false,
    });
    updatePhysicalComposition.mockResolvedValue({ property: ["facility", "warehouse"] });
    updatePhysicalNumbering.mockResolvedValue(configuration.numbering_rules[0]);
    updatePhysicalCreationPolicy.mockResolvedValue(configuration.creation_policies[0]);
  });

  it("shows six active physical types, reserved LINEAR_ASSET and ASSET exclusion", async () => {
    render(<PhysicalWorkspaceConfigurationPanel canConfigure token="token" />);
    expect(await screen.findByText("READY_FOR_PHYSICAL_WORKSPACE_CREATION_PROCESSES")).toBeInTheDocument();
    expect(screen.getByText("REGION")).toBeInTheDocument();
    expect(screen.getByText("DISTRICT")).toBeInTheDocument();
    expect(screen.getByText("SITE")).toBeInTheDocument();
    expect(screen.getByText("PROPERTY")).toBeInTheDocument();
    expect(screen.getByText("FACILITY")).toBeInTheDocument();
    expect(screen.getByText("WAREHOUSE")).toBeInTheDocument();
    expect(screen.getByText("LINEAR_ASSET")).toBeInTheDocument();
    expect(screen.getByText("ASSET != Workspace Type")).toBeInTheDocument();
  });

  it("presents PROPERTY as Real Estate and parametrized attributes", async () => {
    render(<PhysicalWorkspaceConfigurationPanel canConfigure token="token" />);
    expect(await screen.findByText("PROPERTY = Real Estate")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Attributes" }));
    expect(screen.getByText("property Name")).toBeInTheDocument();
  });

  it("renders configurable composition matrix", async () => {
    render(<PhysicalWorkspaceConfigurationPanel canConfigure token="token" />);
    await screen.findByText("PROPERTY = Real Estate");
    fireEvent.click(screen.getByRole("button", { name: "Allowed Parents / Children" }));
    expect(screen.getByText("Matriz flexible")).toBeInTheDocument();
    expect(screen.getByText("Sin hijos")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar composicion" })).toBeEnabled();
  });

  it("persists numbering through the governed API", async () => {
    render(<PhysicalWorkspaceConfigurationPanel canConfigure token="token" />);
    await screen.findByText("PROPERTY = Real Estate");
    fireEvent.click(screen.getByRole("button", { name: "Numbering" }));
    fireEvent.click(screen.getByRole("button", { name: "Guardar numeracion" }));
    await waitFor(() => expect(updatePhysicalNumbering).toHaveBeenCalledWith("token", "property", 1, "PYP-PROP", 5));
  });

  it("executes a non-persistent preview", async () => {
    render(<PhysicalWorkspaceConfigurationPanel canConfigure token="token" />);
    await screen.findByText("PROPERTY = Real Estate");
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    fireEvent.click(screen.getByRole("button", { name: "Previsualizar" }));
    await waitFor(() => expect(previewPhysicalWorkspace).toHaveBeenCalled());
    expect(await screen.findByText("PYP-PROP-00001")).toBeInTheDocument();
    expect(screen.getByText("NO")).toBeInTheDocument();
  });

  it("disables preview for reserved LINEAR_ASSET", async () => {
    render(<PhysicalWorkspaceConfigurationPanel canConfigure token="token" />);
    await screen.findByText("PROPERTY = Real Estate");
    fireEvent.click(screen.getByText("LINEAR_ASSET"));
    expect(screen.getByText("LINEAR_ASSET reservado")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(screen.getByRole("button", { name: "Previsualizar" })).toBeDisabled();
  });
});
