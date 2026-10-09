import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CapitalPlanningWorkspace from "./CapitalPlanningWorkspace";
import type { CapitalPlanningOptions, StrategicCapitalDemand } from "./types";

const mocks = vi.hoisted(() => ({
  listCycles: vi.fn(),
  listDemands: vi.fn(),
  options: vi.fn(),
  demandSummary: vi.fn(),
  originatedIdeas: vi.fn(),
  history: vi.fn(),
  actionDemand: vi.fn(),
  createDemand: vi.fn(),
  updateDemand: vi.fn(),
  createCycle: vi.fn(),
  openCycle: vi.fn(),
  startCycleReview: vi.fn(),
  closeCycle: vi.fn(),
  originateIdea: vi.fn(),
  ideaOptions: vi.fn(),
}));

vi.mock("./api", () => ({
  createIdempotencyKey: () => "workspace-test-idempotency-key",
  capitalPlanningApi: {
    listCycles: mocks.listCycles,
    listDemands: mocks.listDemands,
    options: mocks.options,
    demandSummary: mocks.demandSummary,
    originatedIdeas: mocks.originatedIdeas,
    history: mocks.history,
    actionDemand: mocks.actionDemand,
    createDemand: mocks.createDemand,
    updateDemand: mocks.updateDemand,
    createCycle: mocks.createCycle,
    openCycle: mocks.openCycle,
    startCycleReview: mocks.startCycleReview,
    closeCycle: mocks.closeCycle,
    originateIdea: mocks.originateIdea,
  },
}));

vi.mock("../idea-demand/api", () => ({
  ideaDemandApi: { options: mocks.ideaOptions },
}));

const cycle = {
  id: 7,
  cycle_number: "CPC-00007",
  name: "FY27 capital cycle",
  planning_horizon_start: "2027-01-01",
  planning_horizon_end: "2027-12-31",
  status: "OPEN" as const,
  scope_workspace_id: 11,
  responsible_organization_workspace_id: 11,
  applicable_theme_codes: ["reliability"],
  capital_basis_currency: "COP",
  description: "Governed FY27 cycle",
  demand_count: 31,
  revision_version: 2,
};

const demand: StrategicCapitalDemand = {
  id: 41,
  demand_number: "CD-00041",
  name: "North terminal reliability",
  description: "Governed need",
  planning_cycle_id: 7,
  planning_cycle_number: "CPC-00007",
  planning_cycle_name: "FY27 capital cycle",
  theme_codes: ["reliability"],
  strategic_objective_codes: ["asset-integrity"],
  business_or_asset_need: "Restore asset integrity before capacity is constrained.",
  strategic_driver: "compliance",
  demand_category: "sustaining",
  urgency: "high",
  target_horizon: "near",
  sponsor_user_id: 3,
  sponsor_name: "Executive Sponsor",
  owning_workspace_id: 11,
  owning_workspace_name: "P&P Enterprise",
  location_context: "North terminal",
  indicative_capital_need: "1250000",
  indicative_capital_range_low: "1000000",
  indicative_capital_range_high: "1500000",
  currency_code: "COP",
  uncertainty_level: "medium",
  potential_portfolio_id: null,
  potential_portfolio_name: null,
  assumptions: ["Access remains available"],
  constraints: ["Shutdown window"],
  dependencies: ["Integrity study"],
  status: "DRAFT",
  readiness: { status: "READY", ready: true },
  ideas_originated: 0,
  allowed_actions: ["edit", "submit"],
  revision_version: 4,
  created_at: "2026-09-29T10:00:00Z",
  updated_at: "2026-09-29T10:00:00Z",
};

const options: CapitalPlanningOptions = {
  planning_cycles: [cycle],
  themes: [{ code: "reliability", label: "Reliability" }],
  strategic_objectives: [{ code: "asset-integrity", label: "Asset Integrity" }],
  demand_drivers: [{ code: "compliance", label: "Compliance" }],
  demand_categories: [{ code: "sustaining", label: "Sustaining" }],
  planning_horizons: [{ code: "near", label: "Near term" }],
  urgency_levels: [{ code: "high", label: "High" }],
  uncertainty_levels: [{ code: "medium", label: "Medium" }],
  owning_workspaces: [{ id: 11, name: "P&P Enterprise", workspace_type_code: "enterprise" }],
  sponsors: [{ id: 3, name: "Executive Sponsor" }],
  potential_portfolios: [],
};

const summary = {
  cycle_id: 7,
  demand_count: 31,
  status_counts: { DRAFT: 22, ENDORSED: 9 },
  theme_counts: { reliability: 31 },
  driver_counts: { compliance: 31 },
  horizon_counts: { near: 31 },
  uncertainty_counts: { medium: 31 },
  indicative_capital_totals_by_currency: { COP: "1250000", USD: "500000" },
  unpriced_demand_count: 0,
  normalization_warning: "Currencies remain separate.",
};

describe("CapitalPlanningWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.listCycles.mockResolvedValue({ items: [cycle], page: 1, pageSize: 100, total: 1, nextCursor: null });
    mocks.listDemands.mockResolvedValue({ items: [demand], page: 1, pageSize: 25, total: 31, nextCursor: null });
    mocks.options.mockResolvedValue(options);
    mocks.demandSummary.mockResolvedValue(summary);
    mocks.ideaOptions.mockResolvedValue({ idea_types: [], categories: [] });
    mocks.originatedIdeas.mockResolvedValue([]);
    mocks.history.mockResolvedValue([]);
    mocks.actionDemand.mockResolvedValue({ ...demand, status: "SUBMITTED", revision_version: 5 });
  });

  it("uses server-side filtering, accurate summary metrics and page-level Idea labeling", async () => {
    const user = userEvent.setup();
    render(<CapitalPlanningWorkspace token="token" />);

    expect((await screen.findAllByText("CD-00041")).length).toBeGreaterThan(0);
    expect(screen.getByText("9", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("Ideas on this page")).toBeInTheDocument();
    expect(screen.getByText("Currencies remain separate.")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Driver"), "compliance");
    await user.click(screen.getByRole("button", { name: "Apply server filters" }));

    await waitFor(() =>
      expect(mocks.listDemands).toHaveBeenLastCalledWith("token", expect.stringContaining("driver=compliance"))
    );
    expect(mocks.demandSummary).toHaveBeenLastCalledWith("token", expect.objectContaining({ driver: "compliance" }));
  });

  it("sends an idempotency key for every governed Demand transition", async () => {
    const user = userEvent.setup();
    render(<CapitalPlanningWorkspace token="token" />);
    expect((await screen.findAllByText("CD-00041")).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /Submit/ }));

    await waitFor(() => expect(mocks.actionDemand).toHaveBeenCalledTimes(1));
    expect(mocks.actionDemand).toHaveBeenCalledWith(
      "token",
      expect.objectContaining({ id: 41, revision_version: 4 }),
      "submit",
      undefined,
      expect.any(String)
    );
  });

  it("preserves assumptions, constraints and dependencies as governed arrays when editing", async () => {
    const user = userEvent.setup();
    mocks.updateDemand.mockResolvedValue({ ...demand, revision_version: 5 });
    render(<CapitalPlanningWorkspace token="token" />);
    expect((await screen.findAllByText("CD-00041")).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Edit Demand" }));
    const form = screen.getByRole("form", { name: "Edit Capital Demand form" });
    expect(form).toBeInTheDocument();
    expect(screen.getByDisplayValue("Access remains available")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Shutdown window")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Integrity study")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Assumptions (one per line)"), {
      target: { value: "Access remains available\nPermit approved" },
    });
    await user.click(screen.getByRole("button", { name: "Save governed need" }));

    await waitFor(() => expect(mocks.updateDemand).toHaveBeenCalledTimes(1));
    expect(mocks.updateDemand).toHaveBeenCalledWith(
      "token",
      expect.objectContaining({ id: 41 }),
      expect.objectContaining({
        assumptions: ["Access remains available", "Permit approved"],
        constraints: ["Shutdown window"],
        dependencies: ["Integrity study"],
      })
    );
  });

  it("refreshes originated Idea lineage after the selected Demand keeps the same id", async () => {
    const user = userEvent.setup();
    const endorsedDemand = {
      ...demand,
      status: "ENDORSED" as const,
      allowed_actions: ["originate_idea"],
      revision_version: 7,
    };
    const originatedIdea = {
      idea_id: 99,
      idea_number: "IDEA-00099",
      idea_title: "North terminal reliability",
      source_snapshot_hash: "a".repeat(64),
    };
    mocks.listDemands.mockResolvedValue({
      items: [endorsedDemand],
      page: 1,
      pageSize: 25,
      total: 1,
      nextCursor: null,
    });
    mocks.ideaOptions.mockResolvedValue({
      idea_types: [{ code: "investment", label: "Investment" }],
      categories: [{ code: "risk", label: "Risk reduction" }],
    });
    mocks.originateIdea.mockResolvedValue({ ...originatedIdea, created: true });
    mocks.originatedIdeas.mockResolvedValueOnce([]).mockResolvedValue([originatedIdea]);

    render(<CapitalPlanningWorkspace initialView="capital-demand-endorsed" token="token" />);
    expect((await screen.findAllByText("CD-00041")).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Originate Idea" }));
    await user.click(screen.getByRole("button", { name: "Originate governed Idea" }));

    await waitFor(() => expect(mocks.originateIdea).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("IDEA-00099", { exact: true })).toBeVisible();
    expect(mocks.originatedIdeas.mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});
