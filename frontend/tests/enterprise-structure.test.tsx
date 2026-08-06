import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AdminEnterpriseStructurePage from "../src/features/enterprise-structure/pages/AdminEnterpriseStructurePage";
import EnterpriseExplorerPage from "../src/features/enterprise-structure/pages/EnterpriseExplorerPage";
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

function node(id: number, code: string, name: string, type: string, parentId: number | null): EnterpriseNode {
  return {
    id,
    parent_id: parentId,
    workspace_type_code: type,
    code,
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

const root = node(1, "ENT", "P&Pmis Enterprise", "enterprise", null);
const businessUnit = node(2, "BU-CO", "Colombia Business Unit", "business-unit", 1);
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
  it("places configuration in ADMIN MODE and Explorer in USER MODE", () => {
    const adminModule = ADMIN_MODE_NAVIGATION_BLUEPRINT.find((item) => item.key === "enterprise-structure");
    expect(adminModule?.submodules.map((item) => item.key)).toContain("enterprise-structure-configuration");

    const userModule = USER_MODE_NAVIGATION_BLUEPRINT.flatMap((item) => item.modules).find(
      (item) => item.key === "enterprise-structure-workspace-manager"
    );
    expect(userModule?.submodules).toEqual([{ key: "enterprise-explorer", label: "Enterprise Explorer" }]);
  });

  it("renders the governed ADMIN configuration with four functional tabs", async () => {
    const user = userEvent.setup();
    render(<AdminEnterpriseStructurePage canConfigure token="token" />);

    expect(await screen.findByRole("heading", { name: "Enterprise Structure Configuration" })).toBeInTheDocument();
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
    await user.click(await screen.findByRole("button", { name: /^Colombia Business Unit/i }));

    expect(await screen.findByRole("heading", { name: "Colombia Business Unit" })).toBeInTheDocument();
    expect(screen.getByLabelText("Filtrar por objetivo estratégico")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^tabla$/i }));
    expect(screen.getByRole("columnheader", { name: "Código" })).toBeInTheDocument();
    expect(enterpriseStructureApi.nodeDetail).toHaveBeenCalledWith("token", 2);
  });
});
