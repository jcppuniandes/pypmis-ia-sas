import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
} from "../src/features/enterprise-structure/types";

vi.mock("../src/features/enterprise-structure/api", () => ({
  enterpriseStructureApi: {
    configuration: vi.fn(),
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

afterEach(() => cleanup());

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(enterpriseStructureApi.configuration).mockResolvedValue(adminData);
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
      <EnterpriseTree
        nodes={adminData.tree}
        onSelect={() => undefined}
        selectedNodeId={null}
      />
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

  it("renders the governed ADMIN configuration with four functional tabs", async () => {
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

  it("renders USER Explorer filters, tree/table views and persisted node detail", async () => {
    const user = userEvent.setup();
    render(<EnterpriseExplorerPage token="token" />);

    await screen.findByRole("tree", { name: "Enterprise hierarchy" });
    expect(document.querySelector(".compactModuleHeader.user")).toBeInTheDocument();
    const businessUnitButton = (
      await screen.findByText("Colombia Business Unit", { selector: "strong" })
    ).closest("button");
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
