import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PortfolioAnalysisAdminView from "./PortfolioAnalysisAdminView";
import PortfolioAnalysisWorkspace from "./PortfolioAnalysisWorkspace";

const mocks = vi.hoisted(() => ({
  overview: vi.fn(),
  projectDetail: vi.fn(),
  configurations: vi.fn(),
  previewConfiguration: vi.fn(),
  cloneConfiguration: vi.fn(),
  updateConfiguration: vi.fn(),
  publishConfiguration: vi.fn(),
  portfolioOptions: vi.fn(),
}));

vi.mock("./api", () => ({ portfolioAnalysisApi: mocks }));
vi.mock("../portfolio-planning/api", () => ({ portfolioPlanningApi: { portfolioOptions: mocks.portfolioOptions } }));

const row = {
  portfolio_workspace_id: 71,
  project_workspace_id: 101,
  portfolio_membership_id: 201,
  project_number: "PRJ-101",
  project_name: "Growth Project",
  project_type: "Expansion",
  governance_model: "CAPITAL_OWNER",
  workspace_status: "pending",
  planning_stage: "PORTFOLIO_PLANNING",
  strategic_objectives: [{ code: "GROWTH", name: "Growth" }],
  proposal_score: "82.0000",
  portfolio_evaluation_score: "90.0000",
  portfolio_rank: 1,
  strategic_alignment_score: "100.0000",
  risk_score: "4.0000",
  risk_bucket: "HIGH",
  priority_bucket: "HIGH",
  rom_cost: "2500000",
  currency: "COP",
  target_start: "2027-01-01",
  target_finish: "2028-01-01",
  planned_duration_days: 365,
  expected_benefits: "Capacity growth",
  risk_summary: [],
  sponsor: null,
  project_manager: null,
  membership_source: "STRATEGIC_INTAKE",
  evaluation_id: 301,
  evaluation_version: 1,
  evaluation_date: "2026-08-25T10:00:00Z",
  planning_entry_hash: "a".repeat(64),
  evaluation_hash: "b".repeat(64),
  prioritization_hash: "c".repeat(64),
};

const configurationContent = {
  scope: { type: "tenant", workspace_id: null },
  applicable_governance_models: ["CAPITAL_OWNER"],
  metric_catalog: [
    {
      metric_key: "portfolio_evaluation_score",
      label: "Portfolio Evaluation Score",
      allowed_for_x_axis: true,
      allowed_for_y_axis: true,
      allowed_for_size: true,
      allowed_for_color: false,
    },
    {
      metric_key: "strategic_alignment_score",
      label: "Strategic Alignment",
      allowed_for_x_axis: true,
      allowed_for_y_axis: true,
      allowed_for_size: true,
      allowed_for_color: false,
    },
    {
      metric_key: "rom_cost",
      label: "ROM Cost",
      allowed_for_x_axis: true,
      allowed_for_y_axis: true,
      allowed_for_size: true,
      allowed_for_color: false,
    },
    {
      metric_key: "risk_bucket",
      label: "Risk Bucket",
      allowed_for_x_axis: false,
      allowed_for_y_axis: false,
      allowed_for_size: false,
      allowed_for_color: true,
    },
  ],
  investor_map: {
    x_axis: "portfolio_evaluation_score",
    y_axis: "strategic_alignment_score",
    size: "rom_cost",
    color: "risk_bucket",
    reference_lines: [
      { axis: "x", value: 70, label: "Portfolio score reference" },
      { axis: "y", value: 70, label: "Strategic alignment reference" },
    ],
  },
  scorecard: { columns: ["portfolio_rank", "project_number", "project_name"], default_sort: [] },
};

const overview = {
  dataset: {
    portfolio_workspace_id: 71,
    generated_at: "2026-08-25T10:00:00Z",
    metric_catalog: [
      { metric_key: "portfolio_evaluation_score", label: "Portfolio Evaluation Score" },
      { metric_key: "strategic_alignment_score", label: "Strategic Alignment" },
      { metric_key: "rom_cost", label: "ROM Cost" },
      { metric_key: "risk_bucket", label: "Risk Bucket" },
      { metric_key: "portfolio_rank", label: "Portfolio Rank" },
      { metric_key: "project_number", label: "Project Number" },
      { metric_key: "project_name", label: "Project Name" },
    ],
    rows: [row],
    filters_applied: {},
    source_prioritization_hash: "c".repeat(64),
    membership_set_hash: "d".repeat(64),
    evaluation_set_hash: "e".repeat(64),
    configuration_hash: "f".repeat(64),
    analysis_hash: "1".repeat(64),
    warnings: [],
    blockers: [],
  },
  investor_map: {
    portfolio_workspace_id: 71,
    x_metric: "portfolio_evaluation_score",
    y_metric: "strategic_alignment_score",
    size_metric: "rom_cost",
    color_metric: "risk_bucket",
    size_metric_applied: true,
    reference_lines: configurationContent.investor_map.reference_lines,
    points: [
      {
        project_workspace_id: 101,
        project_number: "PRJ-101",
        project_name: "Growth Project",
        portfolio_rank: 1,
        x: 90,
        y: 100,
        bubble_size: "2500000",
        bubble_size_source: "2500000",
        color: "HIGH",
        tooltip: {},
      },
    ],
    analysis_hash: "1".repeat(64),
    warnings: [],
  },
  scorecard: {
    portfolio_workspace_id: 71,
    columns: ["portfolio_rank", "project_number", "project_name"],
    default_sort: [{ metric_key: "portfolio_rank", direction: "asc" }],
    rows: [{ project_workspace_id: 101, portfolio_rank: 1, project_number: "PRJ-101", project_name: "Growth Project" }],
    analysis_hash: "1".repeat(64),
    warnings: [],
  },
  summary: {
    eligible_projects: 1,
    evaluated_projects: 1,
    average_portfolio_score: "90.00",
    high_priority_count: 1,
    high_risk_count: 1,
    rom_cost_coverage_percent: "100.00",
    rom_cost_total: "2500000",
    rom_cost_currency: "COP",
    distributions: { project_type: [{ key: "Expansion", count: 1 }] },
  },
  readiness: {
    portfolio_workspace_id: 71,
    status: "READY",
    analysis_hash: "1".repeat(64),
    source_prioritization_hash: "c".repeat(64),
    membership_set_hash: "d".repeat(64),
    evaluation_set_hash: "e".repeat(64),
    configuration_hash: "f".repeat(64),
    eligible_project_count: 1,
    metric_coverage: {},
    warnings: [],
    blockers: [],
    allowed_actions: ["can_view_portfolio_analysis", "can_enter_portfolio_scenario_planning"],
    can_enter_budget_planning: true,
    can_enter_resource_planning: true,
    can_enter_portfolio_scenario_planning: true,
    final_output: "READY_FOR_PORTFOLIO_SCENARIO_PLANNING",
  },
};

describe("Portfolio Analysis Gate 07F", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.portfolioOptions.mockResolvedValue([{ id: 71, name: "Capital Portfolio" }]);
    mocks.overview.mockResolvedValue(overview);
    mocks.projectDetail.mockResolvedValue({
      row,
      evaluation_history: [{ id: 301, version: 1, status: "COMPLETED" }],
      strategic_context: {},
      membership: {},
      planning_entry: {},
    });
    mocks.configurations.mockResolvedValue([
      {
        id: 501,
        kind: "portfolio_analysis_configuration",
        code: "gate07f-default",
        name: "Gate 07F Default",
        description: "",
        status: "draft",
        revision: 1,
        version: 1,
        content_json: configurationContent,
        content_hash: "f".repeat(64),
      },
    ]);
    mocks.previewConfiguration.mockResolvedValue({ persisted: false, publishable: true });
  });

  it("provides Overview, accessible Investor Map, Scorecard and read-only Project drilldown", async () => {
    const user = userEvent.setup();
    render(<PortfolioAnalysisWorkspace portfolioId={71} token="token" />);

    expect(await screen.findByText("READY_FOR_PORTFOLIO_SCENARIO_PLANNING")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /investor map/i }));
    expect(await screen.findByRole("img", { name: /1 Projects plotted/i })).toBeInTheDocument();
    expect(screen.getByText(/Scorecard contains the same core Project information/i)).toBeInTheDocument();
    await user.click(screen.getByTestId("investor-map-project-101"));
    expect(await screen.findByRole("complementary", { name: "Project analysis detail" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close Project detail" }));
    await user.click(screen.getByRole("button", { name: /scorecard/i }));
    expect(await screen.findByRole("table")).toHaveTextContent("PRJ-101");
    expect(screen.queryByRole("button", { name: /FID|FORCED_IN|SELECTED|FUNDED/ })).not.toBeInTheDocument();
  });

  it("exposes governed ADMIN selectors and a non-persistent Preview action", async () => {
    const user = userEvent.setup();
    render(<PortfolioAnalysisAdminView token="token" />);

    expect(await screen.findByRole("heading", { name: "Portfolio Analysis Configuration" })).toBeInTheDocument();
    expect(screen.getByLabelText("X Axis")).toHaveValue("portfolio_evaluation_score");
    expect(screen.getByLabelText("Bubble Size")).toHaveValue("rom_cost");
    const actions = screen.getByLabelText("Portfolio Analysis configuration actions");
    await user.click(within(actions).getByRole("button", { name: "Preview" }));
    await waitFor(() => expect(mocks.previewConfiguration).toHaveBeenCalled());
    expect(await screen.findByText(/without persisting snapshot, rank, membership or evaluation/i)).toBeInTheDocument();
    expect(actions).toBeInTheDocument();
  });
});
