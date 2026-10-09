import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AdminEnterpriseStructurePage from "../src/features/enterprise-structure/pages/AdminEnterpriseStructurePage";
import EnterpriseExplorerPage from "../src/features/enterprise-structure/pages/EnterpriseExplorerPage";
import CompactModuleHeader from "../src/features/enterprise-structure/components/CompactModuleHeader";
import EnterpriseTable from "../src/features/enterprise-structure/components/EnterpriseTable";
import EnterpriseTree from "../src/features/enterprise-structure/components/EnterpriseTree";
import { enterpriseStructureApi } from "../src/features/enterprise-structure/api";
import {
  ADMIN_MODE_NAVIGATION_BLUEPRINT,
  USER_MODE_NAVIGATION_BLUEPRINT,
} from "../src/navigation/applicationNavigation";
import type {
  ConfigurationVersion,
  EnterpriseExplorer,
  EnterpriseNode,
  EnterpriseStructureConfiguration,
  ProjectConfiguration,
} from "../src/features/enterprise-structure/types";

vi.mock("../src/features/enterprise-structure/api", () => ({
  enterpriseStructureApi: {
    configuration: vi.fn(),
    projectConfiguration: vi.fn(),
    previewProject: vi.fn(),
    createProjectTemplate: vi.fn(),
    updateProjectTemplate: vi.fn(),
    validateProjectTemplate: vi.fn(),
    publishProjectTemplate: vi.fn(),
    cloneProjectTemplate: vi.fn(),
    archiveProjectTemplate: vi.fn(),
    updateProjectNumbering: vi.fn(),
    updateProjectCreationPolicy: vi.fn(),
    updateProjectGovernancePolicy: vi.fn(),
    previewProjectGovernancePolicy: vi.fn(),
    createNode: vi.fn(),
    updateNode: vi.fn(),
    archiveNode: vi.fn(),
    addClassification: vi.fn(),
    removeClassification: vi.fn(),
    addLink: vi.fn(),
    removeLink: vi.fn(),
    cloneCategory: vi.fn(),
    updateCategory: vi.fn(),
    updateCompositionRule: vi.fn(),
    validate: vi.fn(),
    publish: vi.fn(),
    cloneRelease: vi.fn(),
    explorer: vi.fn(),
    nodeDetail: vi.fn(),
  },
}));

const timestamp = "2026-08-06T12:00:00Z";

function configuration(code: string, name: string, kind = "workspace_type"): ConfigurationVersion {
  return {
    id: Array.from(code).reduce((total, character) => total + character.charCodeAt(0), 0),
    kind,
    code,
    name,
    description: `${name} description`,
    status: "published",
    revision: 1,
    version: 1,
    content_json:
      kind === "catalog"
        ? { applicable_types: ["project"], items: [{ code: "growth", label: "Growth" }] }
        : { allowed_children: code === "enterprise" ? ["business-unit"] : [] },
    content_hash: "hash",
    published_at: timestamp,
  };
}

function node(
  id: number,
  code: string,
  recordCode: string,
  depth: number,
  name: string,
  type: string,
  parentId: number | null
): EnterpriseNode {
  return {
    id,
    parent_id: parentId,
    workspace_type_code: type,
    code,
    record_code: recordCode,
    depth,
    name,
    description: `${name} description`,
    organization_unit_id: null,
    responsible_user_id: null,
    region_code: "CO",
    valid_from: null,
    valid_to: null,
    status: "active",
    sort_order: id,
    version: 1,
    created_at: timestamp,
    updated_at: timestamp,
  };
}

const root = node(1, "ENT", "01", 0, "P&Pmis Enterprise", "enterprise", null);
const businessUnit = node(2, "BU-CO", "01.01", 1, "Colombia Business Unit", "business-unit", 1);
const types = [
  configuration("enterprise", "Enterprise"),
  configuration("business-unit", "Business Unit"),
  configuration("portfolio", "Portfolio"),
  configuration("program", "Program"),
  configuration("project", "Project"),
  configuration("property", "Property"),
  configuration("facility", "Facility"),
];

const adminData: EnterpriseStructureConfiguration = {
  workspace_types: types,
  categories: [configuration("strategic-objective", "Strategic Objectives", "catalog")],
  composition_rules: [
    {
      parent_type_code: "enterprise",
      parent_type_name: "Enterprise",
      configuration_id: 1,
      revision: 1,
      status: "published",
      allowed_children: ["business-unit"],
      max_depth: null,
      can_be_root: true,
      required_categories: [],
      required_fields: ["code", "name"],
    },
  ],
  drafts: [],
  tree: [{ ...root, children: [{ ...businessUnit, children: [] }] }],
  classifications: [],
  links: [],
  summary: { nodes: 2, active_nodes: 2, types: 7, categories: 1, drafts: 0, classifications: 0, links: 0 },
};

const explorerData: EnterpriseExplorer = {
  tree: adminData.tree,
  nodes: [root, businessUnit],
  workspace_types: types,
  objectives: [{ code: "growth", label: "Growth" }],
  classifications: [],
  links: [],
  summary: { nodes: 2, active: 2, properties: 0, facilities: 0, projects: 0 },
};

const projectType: ConfigurationVersion = {
  ...configuration("project", "Project"),
  content_json: {
    repeatable: true,
    user_mode_enabled: true,
    admin_configurable: true,
    template_supported: true,
    creation_process_supported: true,
    project_attributes: [
      { code: "name", label: "Nombre", type: "text", required: true },
      { code: "project_number", label: "Numero de proyecto", type: "text", read_only: true },
    ],
  },
};

const projectTemplate: ConfigurationVersion = {
  ...configuration("PYP-PRJ-GENERAL", "Proyecto general", "project_template"),
  status: "draft",
  content_json: {
    applicable_parent_types: ["portfolio", "program"],
    default_classifications: [],
    enabled_modules: ["scope-manager"],
    default_role_codes: [],
    default_group_codes: [],
    numbering_rule_code: "project-workspace",
    default_attributes: { currency: "COP" },
    creation_policy_code: "project-creation",
  },
};

const projectData: ProjectConfiguration = {
  project_type: projectType,
  templates: [projectTemplate],
  numbering_rule: {
    ...configuration("project-workspace", "Project Workspace Numbering", "numbering_rule"),
    content_json: { prefix: "PYP-PRJ", padding: 5, pattern: "{prefix}-{sequence:05d}" },
  },
  creation_policy: {
    ...configuration("project-creation", "Project Creation Policy", "creation_policy"),
    content_json: {
      allowed_parent_types: ["portfolio", "program"],
      template_required: true,
      project_manager_required: true,
      strategic_objective_required: true,
      approval_required: true,
      auto_project_number: true,
      auto_record_code: true,
      initial_status: "pending",
      activation_after_approval: true,
      materialization_after_approval: true,
    },
  },
  governance_models: [
    {
      governance_model: "CAPITAL_OWNER",
      label: "Capital Owner",
      configuration_id: 71,
      revision: 1,
      content_hash: "a".repeat(64),
      source_workspace_id: null,
      source_workspace_name: null,
      resolution_chain: ["tenant"],
      content: {
        template_required: true,
        project_manager_required: true,
        strategic_objective_required: true,
        portfolio_required: true,
        fel_required: true,
        approval_required: true,
      },
    },
    {
      governance_model: "CONTRACTOR_DELIVERY",
      label: "Contractor Delivery",
      configuration_id: 72,
      revision: 1,
      content_hash: "b".repeat(64),
      source_workspace_id: null,
      content: { contract_source_required: true, approval_required: true },
    },
    {
      governance_model: "DIRECT_INTERNAL",
      label: "Direct Internal",
      configuration_id: 73,
      revision: 1,
      content_hash: "c".repeat(64),
      source_workspace_id: null,
      content: { approval_required: true },
    },
  ],
  classification_sets: [configuration("strategic-objective", "Strategic Objectives", "catalog")],
  available_modules: [configuration("scope-manager", "Scope Manager", "module_definition")],
  parent_options: [
    { id: 10, name: "Strategic Portfolio", workspace_type_code: "portfolio", record_code: "01.01", status: "active" },
  ],
  allowed_parent_types: ["portfolio", "program"],
  summary: {
    templates: 1,
    draft_templates: 1,
    published_templates: 0,
    classification_proposals: 3,
    available_modules: 1,
    eligible_parents: 1,
  },
  gate_status: "READY_FOR_PROJECT_CREATION_PROCESS",
  gate_05b_contract: { workspace_table: "enterprise_workspaces", materialization_endpoint: null },
  multi_source_status: "READY_FOR_MULTI_SOURCE_PROJECT_CREATION",
};

afterEach(() => cleanup());

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(enterpriseStructureApi.configuration).mockResolvedValue(adminData);
  vi.mocked(enterpriseStructureApi.projectConfiguration).mockResolvedValue(projectData);
  vi.mocked(enterpriseStructureApi.previewProject).mockResolvedValue({
    allowed: true,
    parent: projectData.parent_options[0],
    template_code: "PYP-PRJ-GENERAL",
    projected_record_code: "01.01.01",
    projected_project_number: "PYP-PRJ-00001",
    inherited_classifications: [
      { category_set_code: "strategic-objective", category_item_code: "growth", source: "parent" },
    ],
    enabled_modules: ["scope-manager"],
    initial_status: "pending",
    issues: [],
    persisted: false,
  });
  vi.mocked(enterpriseStructureApi.explorer).mockResolvedValue(explorerData);
  vi.mocked(enterpriseStructureApi.nodeDetail).mockResolvedValue({
    node: businessUnit,
    path: [root, businessUnit],
    classifications: [],
    links: [],
  });
});

describe("Nivel 2A Enterprise Structure", () => {
  it("reuses compact metric chips and actions through CompactModuleHeader", () => {
    render(
      <CompactModuleHeader
        actions={<button type="button">Add</button>}
        description="Compact description"
        eyebrow="ADMIN MODE"
        metrics={[{ label: "Nodes", value: 3 }]}
        title="Shared header"
      />
    );

    expect(screen.getByRole("heading", { name: "Shared header" })).toBeInTheDocument();
    expect(screen.getByLabelText("Métricas de Shared header")).toHaveClass("compactHeaderMetrics");
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
  });

  it("shows record codes and derives tree indentation from depth", () => {
    const { container } = render(
      <EnterpriseTree nodes={adminData.tree} onSelect={() => undefined} selectedNodeId={null} />
    );
    const rows = container.querySelectorAll<HTMLElement>(".enterpriseTreeRow");

    const nestedRecordCode = screen.getByText("01.01");
    expect(nestedRecordCode).toHaveClass("enterpriseRecordCode");
    expect(nestedRecordCode.closest("small")?.querySelector("em.active")).toHaveTextContent("active");
    expect(rows[0].style.paddingLeft).toBe("12px");
    expect(rows[1].style.paddingLeft).toBe("30px");
  });

  it("orders the table by numeric record code and hides USER actions", () => {
    const tenth = { ...businessUnit, id: 10, code: "BU-10", record_code: "01.10", name: "Tenth" };
    const second = { ...businessUnit, id: 3, code: "BU-02", record_code: "01.02", name: "Second" };
    render(<EnterpriseTable nodes={[tenth, second]} onSelect={() => undefined} />);
    const rows = screen.getAllByRole("row");

    expect(within(rows[1]).getByText("01.02")).toBeInTheDocument();
    expect(within(rows[2]).getByText("01.10")).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Actions" })).not.toBeInTheDocument();
  });

  it("exposes node actions only when the table is in ADMIN context", () => {
    render(<EnterpriseTable admin nodes={[businessUnit]} onSelect={() => undefined} />);

    expect(screen.getByRole("columnheader", { name: "Actions" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Editar" })).toBeInTheDocument();
  });

  it("places configuration in ADMIN MODE and Explorer in USER MODE", () => {
    const adminModule = ADMIN_MODE_NAVIGATION_BLUEPRINT.find((item) => item.key === "enterprise-structure");
    expect(adminModule?.submodules.map((item) => item.key)).toContain("enterprise-structure-configuration");

    const userModule = USER_MODE_NAVIGATION_BLUEPRINT.flatMap((item) => item.modules).find(
      (item) => item.key === "enterprise-structure-workspace-manager"
    );
    expect(userModule?.submodules).toEqual([{ key: "enterprise-explorer", label: "Enterprise Explorer" }]);
  });

  it("adds only the Facility Manager and Property Manager macroprocesses from the workbook", () => {
    const facility = USER_MODE_NAVIGATION_BLUEPRINT.find((item) => item.key === "facility-manager");
    const property = USER_MODE_NAVIGATION_BLUEPRINT.find((item) => item.key === "property-manager");

    expect(facility?.label).toBe("Facility Manager");
    expect(facility?.modules.map((item) => item.label)).toEqual([
      "Asset Manager",
      "Maintenance Manager",
      "Condition Assessment Manager",
    ]);
    expect(property?.modules.map((item) => item.label)).toEqual([
      "Lease Manager",
      "Property Transaction Manager",
      "Property Information Manager",
      "Property Utilities Manager",
    ]);
    expect(property?.modules.flatMap((item) => item.submodules).map((item) => item.label)).toEqual([
      "Lease",
      "Lease Contact",
      "Lease Invoice",
      "Lease Payment",
      "Lease Termination",
      "Prospective Property",
      "Prospective Selection",
      "Prospective Disposition",
      "Prospective Creation",
      "Deed",
      "Easements",
      "Parcels",
      "Property Tax",
      "Property Payments",
      "Energy Meter",
      "Water Meter",
    ]);
    expect(USER_MODE_NAVIGATION_BLUEPRINT.filter((item) => item.key === "facility-manager")).toHaveLength(1);
    expect(USER_MODE_NAVIGATION_BLUEPRINT.filter((item) => item.key === "property-manager")).toHaveLength(1);
    expect(USER_MODE_NAVIGATION_BLUEPRINT.some((item) => item.key === "facilities-asset-manager")).toBe(false);
  });

  it("renders the governed ADMIN configuration with all functional tabs", async () => {
    const user = userEvent.setup();
    render(<AdminEnterpriseStructurePage canConfigure token="token" />);

    expect(await screen.findByRole("heading", { name: "Enterprise Structure Configuration" })).toBeInTheDocument();
    expect(document.querySelector(".compactModuleHeader.admin")).toBeInTheDocument();
    expect(screen.getByText("01.01")).toBeInTheDocument();
    expect(screen.getByLabelText("Record Code autogenerado")).toHaveAttribute("readonly");
    expect(screen.getByRole("tree", { name: "Enterprise hierarchy" })).toBeInTheDocument();
    expect(screen.getByText("Colombia Business Unit")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /tipos y categorías/i }));
    expect(await screen.findByRole("heading", { name: "Siete tipos de workspace" })).toBeInTheDocument();
    expect(screen.getByText("Strategic Objectives")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /reglas de composición/i }));
    expect(screen.getByText("Tipos hijo permitidos")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^publicación$/i }));
    expect(screen.getByRole("button", { name: /validar/i })).toBeInTheDocument();
  });

  it("configures PROJECT, templates, allowed parents, attributes and readonly preview outputs", async () => {
    const user = userEvent.setup();
    render(<AdminEnterpriseStructurePage canConfigure token="token" />);

    await user.click(await screen.findByRole("button", { name: /project templates/i }));
    expect(await screen.findByText("READY_FOR_PROJECT_CREATION_PROCESS")).toBeInTheDocument();
    expect(screen.getByText("Portfolio / Program")).toBeInTheDocument();
    expect(screen.getByText("Numero de proyecto")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Revisiones configuradas" })).toBeInTheDocument();
    expect(screen.getByText("PYP-PRJ-GENERAL")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /previsualizar/i }));
    expect(await screen.findByText("01.01.01")).toBeInTheDocument();
    expect(screen.getByText("PYP-PRJ-00001")).toBeInTheDocument();
    expect(screen.getByText("No (preview)")).toBeInTheDocument();
    expect(enterpriseStructureApi.previewProject).toHaveBeenCalledWith("token", 10, projectTemplate.id);
  });

  it("exposes Numbering Rules and Creation Policies without a materialize action", async () => {
    const user = userEvent.setup();
    render(<AdminEnterpriseStructurePage canConfigure token="token" />);

    await user.click(await screen.findByRole("button", { name: /numbering rules/i }));
    expect(await screen.findByText("PYP-PRJ-00001")).toBeInTheDocument();
    expect(screen.getByText("No consume secuencia")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /creation policies/i }));
    expect(await screen.findByRole("heading", { name: "Project Creation Process" })).toBeInTheDocument();
    expect(screen.getByText(/no crea, aprueba ni materializa/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /materializar|crear project/i })).not.toBeInTheDocument();
  });

  it("renders USER Explorer filters, tree/table views and persisted node detail", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <EnterpriseExplorerPage token="token" />
      </MemoryRouter>
    );

    await screen.findByRole("tree", { name: "Enterprise hierarchy" });
    expect(document.querySelector(".compactModuleHeader.user")).toBeInTheDocument();
    const businessUnitButton = (await screen.findByText("Colombia Business Unit", { selector: "strong" })).closest(
      "button"
    );
    expect(businessUnitButton).not.toBeNull();
    await user.click(businessUnitButton!);

    expect(await screen.findByRole("heading", { name: "Colombia Business Unit" })).toBeInTheDocument();
    expect(screen.getByLabelText("Filtrar por objetivo estratégico")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^tabla$/i }));
    expect(screen.getByRole("columnheader", { name: "Record Code" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Actions" })).not.toBeInTheDocument();
    expect(enterpriseStructureApi.nodeDetail).toHaveBeenCalledWith("token", 2);
  });
});
