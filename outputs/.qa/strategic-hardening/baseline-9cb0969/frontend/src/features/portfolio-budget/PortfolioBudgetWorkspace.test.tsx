import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PortfolioBudgetAdminView from "./PortfolioBudgetAdminView";
import PortfolioBudgetWorkspace from "./PortfolioBudgetWorkspace";

const mocks = vi.hoisted(() => ({
  overview: vi.fn(),
  createTarget: vi.fn(),
  publishTarget: vi.fn(),
  createScenario: vi.fn(),
  selectProject: vi.fn(),
  freezeScenario: vi.fn(),
  cloneScenario: vi.fn(),
  refreshPreview: vi.fn(),
  compare: vi.fn(),
  waterline: vi.fn(),
  dependencies: vi.fn(),
  createDependency: vi.fn(),
  updateDependency: vi.fn(),
  deactivateDependency: vi.fn(),
  configurations: vi.fn(),
  previewConfiguration: vi.fn(),
  cloneConfiguration: vi.fn(),
  updateConfiguration: vi.fn(),
  publishConfiguration: vi.fn(),
  portfolioOptions: vi.fn(),
}));

vi.mock("./api", () => ({ portfolioBudgetApi: mocks }));
vi.mock("../portfolio-planning/api", () => ({ portfolioPlanningApi: { portfolioOptions: mocks.portfolioOptions } }));

const project = {
  id: 31,
  project_workspace_id: 101,
  project_number: "PRJ-101",
  project_name: "Growth Project",
  portfolio_evaluation_score: "90.0000",
  portfolio_rank: 1,
  strategic_alignment_score: "95.0000",
  risk_score: "3.0000",
  risk_bucket: "MEDIUM",
  cost_value: "2500000.00",
  capex_amount: "1500000.00",
  expense_amount: "500000.00",
  unclassified_amount: "500000.00",
  budget_breakdown_source: "PROJECT_GOVERNED_DATA",
  currency: "COP",
  target_start: "2027-01-01",
  target_finish: "2028-01-01",
  strategic_objectives: [{ code: "GROWTH", name: "Growth" }],
  selection_state: "SELECTED",
  forced_reason: null,
  warnings: [],
  dependency_status: "COMPLIANT",
  unmet_dependency_count: 0,
  dependency_details: [],
};

const target = {
  id: 11,
  portfolio_workspace_id: 71,
  target_code: "BUDGET-TARGET",
  target_revision: 1,
  planning_horizon_start: "2027-01-01",
  planning_horizon_end: "2028-12-31",
  period_granularity: "YEAR",
  budget_currency: "COP",
  total_budget_target: "5000000.00",
  capex_budget_target: "3000000.00",
  expense_budget_target: "1000000.00",
  unallocated_budget_target: "1000000.00",
  periods: [],
  source_reference: "Management target",
  notes: "",
  status: "PUBLISHED",
  target_hash: "a".repeat(64),
  revision_version: 2,
};

const scenario = (id: number, name: string) => ({
  id,
  portfolio_workspace_id: 71,
  logical_code: `SCN-${id}`,
  scenario_name: name,
  scenario_code: null,
  description: "",
  status: "FROZEN",
  analytical_status: "UNDER_BUDGET",
  budget_target_id: 11,
  source_analysis_hash: "b".repeat(64),
  source_hash: "c".repeat(64),
  scenario_hash: `${id}`.repeat(64).slice(0, 64),
  creation_mode: "FROM_CURRENT_PRIORITY",
  time_phasing_method: "UNPHASED",
  scenario_revision: 1,
  revision_version: 2,
  projects: [project],
  summary: {
    selected_demand: "2500000.00",
    target_budget: "5000000.00",
    variance: "2500000.00",
    utilization_percent: "50.00",
    selected_count: 1,
    unselected_count: 0,
    forced_in_count: 0,
    forced_out_count: 0,
    average_evaluation_score: "90.00",
    average_strategic_alignment: "95.00",
    high_risk_count: 0,
    analytical_status: "UNDER_BUDGET",
    selected_capex: "1500000.00",
    selected_expense: "500000.00",
    selected_unclassified: "500000.00",
    capex_target: "3000000.00",
    expense_target: "1000000.00",
    unallocated_target: "1000000.00",
    capex_variance: "1500000.00",
    expense_variance: "500000.00",
    mandatory_dependency_count: 1,
    unmet_mandatory_count: 0,
    optional_dependency_warning_count: 0,
    forced_dependency_conflict_count: 0,
  },
  period_view: [],
  strategic_balance: { GROWTH: { selected_count: 1 } },
  readiness: { status: "READY", source_current: true, warnings: [], blockers: [] },
  warnings: [],
  blockers: [],
  allowed_actions: ["compare", "clone"],
  dependency_summary: { unmet_mandatory_count: 0 },
});

const scenarios = [scenario(21, "Priority alternative"), scenario(22, "Conservative alternative")];
const overview = {
  portfolio_workspace_id: 71,
  gate07f: {
    final_output: "READY_FOR_PORTFOLIO_SCENARIO_PLANNING",
    analysis_hash: "b".repeat(64),
    can_enter_budget_planning: true,
    can_enter_resource_planning: true,
    warnings: [],
    blockers: [],
  },
  active_target: target,
  targets: [target],
  scenarios,
  readiness: {
    scenario_count: 2,
    frozen_scenario_count: 2,
    ready_scenario_count: 2,
    budget_target_id: 11,
    warnings: [],
    blockers: [],
    budget_planning_hash: "d".repeat(64),
    can_enter_budget_recommendation: true,
    allowed_actions: ["compare"],
    final_output: "READY_FOR_PORTFOLIO_BUDGET_RECOMMENDATION",
  },
  allowed_actions: ["view", "compare"],
  boundaries: ["NO_FUNDS", "NO_RESOURCE_PLANNING", "NO_SCENARIO_WINNER", "NO_FID"],
};

const configurationContent = {
  scope: { type: "tenant", workspace_id: null },
  applicable_governance_models: ["CAPITAL_OWNER"],
  budget_currency_policy: { budget_currency: "COP", fx_conversion: false },
  period_granularity: "YEAR",
  allowed_time_phasing_methods: ["UNPHASED", "LINEAR_BY_PROJECT_DATES", "CUSTOM_PERIOD_PROFILE"],
  scenario_max_count: 20,
  required_cost_coverage_percent: 100,
  controlled_constraints: ["TOTAL_BUDGET", "PERIOD_BUDGET"],
};

describe("Portfolio Budget Planning Gate 07G", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.portfolioOptions.mockResolvedValue([{ id: 71, name: "Capital Portfolio" }]);
    mocks.overview.mockResolvedValue(overview);
    mocks.dependencies.mockResolvedValue([]);
    mocks.waterline.mockResolvedValue({
      scenario_id: 21,
      period_key: "TOTAL",
      rank_source: "GATE07E_CONTEXTUAL_PORTFOLIO_RANK",
      target_budget: "5000000.00",
      selected_demand: "2500000.00",
      variance: "2500000.00",
      analytical_status: "UNDER_BUDGET",
      alignment_status: "GATE07G_A_OPC_ALIGNMENT_VALIDATED",
      waterline_position: null,
      projects: [
        {
          ...project,
          project_type: "Expansion",
          budget_demand: project.cost_value,
          cumulative_selected_demand: project.cost_value,
          target_budget: "5000000.00",
          waterline_side: "ABOVE_OR_AT",
          forced_state: null,
        },
      ],
      budget_breakdown: {},
      dependency_summary: {},
      allowed_actions: [],
    });
    mocks.compare.mockResolvedValue({
      portfolio_workspace_id: 71,
      scenarios: [{ scenario_name: "Priority alternative" }, { scenario_name: "Conservative alternative" }],
      project_matrix: [{ project_number: "PRJ-101" }],
      pairwise_delta: { budget_delta: "0.00" },
      warnings: [],
    });
    mocks.configurations.mockResolvedValue([
      {
        id: 501,
        code: "gate07g-default",
        name: "Gate 07G Default",
        description: "",
        status: "draft",
        revision: 1,
        version: 1,
        content_json: configurationContent,
        content_hash: "e".repeat(64),
      },
    ]);
    mocks.previewConfiguration.mockResolvedValue({ persisted: false, publishable: true });
  });

  it("shows readiness, governed alternatives and a two-scenario comparison without downstream decisions", async () => {
    const user = userEvent.setup();
    render(<PortfolioBudgetWorkspace portfolioId={71} token="token" />);

    expect(await screen.findByText("READY_FOR_PORTFOLIO_BUDGET_RECOMMENDATION")).toBeInTheDocument();
    expect(screen.getByText("NO_FUNDS")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /scenarios/i }));
    expect(await screen.findByRole("table", { name: "Scenario Project Selection Grid" })).toHaveTextContent(
      "Growth Project"
    );
    await user.click(screen.getByRole("button", { name: /^waterline$/i }));
    expect(await screen.findByRole("table", { name: "Waterline projects" })).toHaveTextContent("Growth Project");
    expect(screen.getByText(/does not persist a new ranking/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^dependencies$/i }));
    expect(await screen.findByRole("region", { name: "Project Dependencies" })).toBeInTheDocument();
    expect(screen.getByText(/Selections are never auto-corrected/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /comparison/i }));
    const comparison = await screen.findByRole("region", { name: "Scenario Comparison" });
    const checks = within(comparison).getAllByRole("checkbox");
    await user.click(checks[0]);
    await user.click(checks[1]);
    await user.click(within(comparison).getByRole("button", { name: "Compare selected" }));
    await waitFor(() => expect(mocks.compare).toHaveBeenCalledWith("token", 71, [21, 22]));
    expect(await within(comparison).findByText("Pairwise delta")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /winner|fund|fid|resource allocation/i })).not.toBeInTheDocument();
  });

  it("provides structured ADMIN policy fields and a non-persistent Preview", async () => {
    const user = userEvent.setup();
    render(<PortfolioBudgetAdminView token="token" />);

    expect(await screen.findByRole("heading", { name: "Portfolio Budget Planning Configuration" })).toBeInTheDocument();
    expect(screen.getByLabelText("Budget Currency")).toHaveValue("COP");
    expect(screen.getByLabelText("Scenario max count")).toHaveValue(20);
    expect(screen.getByLabelText("Waterline visible")).toBeChecked();
    expect(screen.getByLabelText("Dependency evaluation")).toBeChecked();
    expect(screen.getByLabelText("Mandatory unmet policy")).toHaveValue("BLOCK_FREEZE");
    const actions = screen.getByLabelText("Portfolio Budget configuration actions");
    await user.click(within(actions).getByRole("button", { name: "Preview" }));
    await waitFor(() => expect(mocks.previewConfiguration).toHaveBeenCalled());
    expect(await screen.findByText(/persisted=false and no Target or Scenario was created/i)).toBeInTheDocument();
  });
});
