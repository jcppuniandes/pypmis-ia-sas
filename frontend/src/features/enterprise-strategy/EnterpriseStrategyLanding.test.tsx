import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { capitalPlanningApi } from "../capital-planning/api";
import { enterpriseStructureApi } from "../enterprise-structure/api";
import { ideaDemandApi } from "../idea-demand/api";
import EnterpriseStrategyLanding, { StrategicBreadcrumb } from "./EnterpriseStrategyLanding";

describe("Enterprise Strategy landing", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(enterpriseStructureApi, "explorer").mockResolvedValue({
      published_release: { id: 1 },
      nodes: [],
      tree: [],
      classifications: [],
      links: [],
      workspace_types: [],
      objectives: [],
      summary: {},
    } as never);
    vi.spyOn(ideaDemandApi, "options").mockResolvedValue({
      number_preview: "IDEA-00001",
      owning_workspaces: [{ id: 7, name: "Portfolio A", workspace_type_code: "portfolio" }],
      target_portfolios: [],
      strategic_objectives: [{ code: "OBJ-01", label: "Growth" }],
      users: [],
      idea_types: [],
      categories: [],
      screening_checklist: [],
      objective_selection: "required",
      configuration_source: { id: 11, status: "published" },
    });
    vi.spyOn(capitalPlanningApi, "options").mockResolvedValue({
      planning_cycles: [],
      themes: [],
      strategic_objectives: [{ code: "OBJ-01", label: "Growth" }],
      demand_drivers: [],
      demand_categories: [],
      planning_horizons: [],
      urgency_levels: [],
      uncertainty_levels: [],
      owning_workspaces: [{ id: 7, name: "Portfolio A", workspace_type_code: "portfolio" }],
      sponsors: [],
      potential_portfolios: [],
      configuration_source: { configuration_id: 21, status: "published" },
    });
  });

  it("separates Enterprise Foundation from the transactional flow and only exposes Create Idea when ready", async () => {
    const onNavigate = vi.fn();
    render(<EnterpriseStrategyLanding mode="user" onNavigate={onNavigate} token="token" />);

    const foundation = screen.getByRole("region", { name: "Enterprise Strategy Manager" });
    expect(within(foundation).getByText(/foundation \/ prerequisite/i)).toBeInTheDocument();
    expect(
      within(foundation).getByRole("heading", {
        name: "Business sequence from Capital Demand to investment governance",
      })
    ).toBeInTheDocument();
    expect(
      within(foundation).getByRole("heading", { name: "Strategic Capital Planning & Demand" })
    ).toBeInTheDocument();
    expect(within(foundation).getByRole("heading", { name: "Investment Origination & Shaping" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Parallel Budget and Resource scenario branches" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Investment evidence contributors" })).toBeInTheDocument();

    await waitFor(() => expect(within(foundation).getByText("READY")).toBeInTheDocument());
    fireEvent.click(within(foundation).getByRole("button", { name: /start capital planning/i }));
    expect(onNavigate).toHaveBeenCalledWith("capital-demand-pipeline");
  });

  it("renders the ADMIN lifecycle with the same phase order", async () => {
    render(<EnterpriseStrategyLanding mode="admin" onNavigate={() => undefined} token="token" />);
    await waitFor(() => expect(screen.getByText("READY")).toBeInTheDocument());
    const governanceCard = screen.getByRole("heading", { name: "Investment Governance" }).closest("article");
    expect(governanceCard).not.toBeNull();
  });

  it("renders the full deep-link breadcrumb", () => {
    render(<StrategicBreadcrumb mode="user" view="portfolio-scorecard" />);
    const breadcrumb = screen.getByRole("navigation", { name: "Strategic workflow breadcrumb" });
    expect(within(breadcrumb).getByText("Enterprise Strategy Manager")).toBeInTheDocument();
    expect(within(breadcrumb).getByText("Portfolio Planning & Review")).toBeInTheDocument();
    expect(within(breadcrumb).getByText("Portfolio Analysis")).toBeInTheDocument();
    expect(within(breadcrumb).getByText("Portfolio Scorecard")).toHaveAttribute("aria-current", "page");
  });
});
