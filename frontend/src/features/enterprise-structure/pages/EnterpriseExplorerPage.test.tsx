import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EnterpriseExplorerPage from "./EnterpriseExplorerPage";

const api = vi.hoisted(() => ({ explorer: vi.fn(), nodeDetail: vi.fn(), physicalCreationOptions: vi.fn() }));
vi.mock("../api", () => ({ enterpriseStructureApi: api }));
vi.mock("../components/EnterpriseTree", () => ({
  default: ({ onSelect }: { onSelect: (id: number) => void }) => (
    <button onClick={() => onSelect(16)} type="button">
      Select node
    </button>
  ),
}));
vi.mock("../components/NodeDetailPanel", () => ({ default: () => null }));
vi.mock("../components/StructureFilters", () => ({ default: () => null }));

function explorer(type: string, allowed: string[], status = "published") {
  return {
    tree: [],
    nodes: [{ id: 16 }],
    objectives: [],
    classifications: [],
    links: [],
    workspace_types: [{ code: type, status, revision: 1, content_json: { allowed_children: allowed } }],
    summary: { nodes: 1, projects: 1, facilities: 0, properties: 0, active: 1 },
  };
}

describe("Enterprise Explorer physical creation probes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.physicalCreationOptions.mockResolvedValue({ locations: [{ id: 16 }] });
  });

  async function select(type: string, allowed: string[], status = "published") {
    api.explorer.mockResolvedValue(explorer(type, allowed, status));
    api.nodeDetail.mockResolvedValue({
      node: { id: 16, name: "Selected node", workspace_type_code: type, status: "active" },
      path: [],
      classifications: [],
      links: [],
    });
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <EnterpriseExplorerPage token="real-user-token" />
      </MemoryRouter>
    );
    await waitFor(() => expect(api.explorer).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Select node" }));
    await waitFor(() => expect(api.nodeDetail).toHaveBeenCalledWith("real-user-token", 16));
  }

  it("does not probe physical privileges when the published Project type has no physical children", async () => {
    await select("project", []);
    await screen.findByRole("button", { name: "Project Overview" });
    expect(api.physicalCreationOptions).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Create Facility" })).not.toBeInTheDocument();
  });

  it("keeps the actual options eligibility check for the published allowed physical child only", async () => {
    await select("geographic-area", ["facility", "project"]);
    expect(await screen.findByRole("button", { name: "Create Facility" })).toBeInTheDocument();
    expect(api.physicalCreationOptions).toHaveBeenCalledTimes(1);
    expect(api.physicalCreationOptions).toHaveBeenCalledWith("real-user-token", "facility", 16);
    expect(screen.queryByRole("button", { name: "Create Property" })).not.toBeInTheDocument();
  });

  it("does not use draft child rules as authority to probe creation options", async () => {
    await select("project", ["facility"], "draft");
    await screen.findByRole("button", { name: "Project Overview" });
    expect(api.physicalCreationOptions).not.toHaveBeenCalled();
  });
});
