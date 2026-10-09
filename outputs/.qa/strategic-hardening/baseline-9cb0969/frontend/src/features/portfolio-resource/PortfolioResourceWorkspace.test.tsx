import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PortfolioResourceAdminView from "./PortfolioResourceAdminView";
import PortfolioResourceWorkspace from "./PortfolioResourceWorkspace";

const mocks = vi.hoisted(() => ({
  overview: vi.fn(),
  createCapacity: vi.fn(),
  publishCapacity: vi.fn(),
  createDemand: vi.fn(),
  publishDemand: vi.fn(),
  createScenario: vi.fn(),
  selectProject: vi.fn(),
  adjustTiming: vi.fn(),
  freezeScenario: vi.fn(),
  cloneScenario: vi.fn(),
  refreshPreview: vi.fn(),
  compare: vi.fn(),
  configurations: vi.fn(),
  previewConfiguration: vi.fn(),
  cloneConfiguration: vi.fn(),
  updateConfiguration: vi.fn(),
  publishConfiguration: vi.fn(),
  portfolioOptions: vi.fn(),
}));

vi.mock("./api", () => ({ portfolioResourceApi: mocks }));
vi.mock("../portfolio-planning/api", () => ({ portfolioPlanningApi: { portfolioOptions: mocks.portfolioOptions } }));

const period = {
  id: 1,
  resource_role_key: "PROJECT_MANAGER",
  resource_role_name: "Project Manager",
  role_category: "MANAGEMENT",
  period_key: "2027",
  period_start: "2027-01-01",
  period_end: "2027-12-31",
  unit: "FTE",
  source_reference: "Management",
  notes: "",
};
const capacity = {
  id: 11,
  portfolio_workspace_id: 71,
  logical_code: "RESOURCE-CAPACITY",
  plan_name: "Published capacity",
  planning_horizon_start: "2027-01-01",
  planning_horizon_end: "2027-12-31",
  period_granularity: "YEAR",
  status: "PUBLISHED",
  plan_revision: 1,
  source_reference: "Management",
  notes: "",
  capacity_hash: "a".repeat(64),
  revision_version: 2,
  periods: [{ ...period, capacity_value: "2.00" }],
};
const demand = {
  id: 21,
  project_workspace_id: 101,
  logical_code: "RESOURCE-DEMAND",
  profile_name: "Project demand",
  status: "PUBLISHED",
  profile_revision: 1,
  source_type: "PROJECT_RESOURCE_DEMAND_PROFILE",
  source_reference: "Estimate",
  source_hash: "b".repeat(64),
  as_of_date: "2026-08-25",
  planning_start: "2027-01-01",
  planning_finish: "2027-12-31",
  generation_method: "EXPLICIT_PERIOD_PROFILE",
  approximation: false,
  demand_hash: "c".repeat(64),
  revision_version: 2,
  periods: [{ ...period, demand_value: "3.00" }],
};
const project = {
  id: 31,
  project_workspace_id: 101,
  project_number: "PRJ-101",
  project_name: "Growth Project",
  portfolio_evaluation_score: "90.00",
  portfolio_rank: 1,
  strategic_alignment_score: "95.00",
  risk_score: "3.00",
  risk_bucket: "MEDIUM",
  resource_demand_profile_id: 21,
  source_project_start: "2027-01-01",
  source_project_finish: "2027-12-31",
  scenario_start: "2027-01-01",
  scenario_finish: "2027-12-31",
  schedule_shift_days: 0,
  timing_method: "NO_SHIFT",
  selection_state: "SELECTED",
  forced_reason: null,
  demand_covered: true,
  revision_version: 1,
};
const scenario = (id: number, name: string) => ({
  id,
  portfolio_workspace_id: 71,
  logical_code: `RSC-${id}`,
  scenario_name: name,
  description: "",
  status: "FROZEN",
  capacity_plan_id: 11,
  capacity_plan_hash: "a".repeat(64),
  source_analysis_hash: "d".repeat(64),
  source_hash: "e".repeat(64),
  scenario_hash: `${id}`.repeat(64).slice(0, 64),
  creation_mode: "FROM_CURRENT_PRIORITY",
  overload_policy: "ALLOW_WITH_WARNING",
  scenario_revision: 1,
  revision_version: 2,
  projects: [project],
  heatmap: [
    {
      resource_role_key: "PROJECT_MANAGER",
      resource_role_name: "Project Manager",
      role_category: "MANAGEMENT",
      period_key: "2027",
      period_start: "2027-01-01",
      period_end: "2027-12-31",
      unit: "FTE",
      capacity: "2.00",
      selected_demand: "3.00",
      variance: "-1.00",
      utilization_percent: "150.00",
      status: "OVERLOADED",
    },
  ],
  summary: {
    selected_count: 1,
    unselected_count: 0,
    forced_in_count: 0,
    forced_out_count: 0,
    average_score: "90.00",
    high_risk_count: 0,
    overloaded_role_count: 1,
    overloaded_period_count: 1,
    peak_overload: "1.00",
    peak_utilization: "150.00",
    average_utilization: "150.00",
    demand_coverage_percent: "100.00",
  },
  readiness: {
    status: "READY",
    source_current: true,
    demand_coverage_percent: "100.00",
    warnings: ["RESOURCE_CAPACITY_OVERLOAD"],
    blockers: [],
  },
  warnings: ["RESOURCE_CAPACITY_OVERLOAD"],
  blockers: [],
  allowed_actions: ["compare", "clone"],
});
const scenarios = [scenario(41, "Balanced alternative"), scenario(42, "Accelerated alternative")];
const overview = {
  portfolio_workspace_id: 71,
  gate07f: {
    final_output: "READY_FOR_PORTFOLIO_SCENARIO_PLANNING",
    analysis_hash: "d".repeat(64),
    can_enter_budget_planning: true,
    can_enter_resource_planning: true,
    warnings: [],
    blockers: [],
  },
  active_capacity_plan: capacity,
  capacity_plans: [capacity],
  demand_profiles: [demand],
  scenarios,
  readiness: {
    scenario_count: 2,
    frozen_scenario_count: 2,
    ready_scenario_count: 2,
    demand_coverage: "100.00",
    overloaded_scenario_count: 2,
    warnings: [],
    blockers: [],
    resource_planning_hash: "f".repeat(64),
    can_enter_resource_recommendation: true,
    allowed_actions: ["compare"],
    final_output: "READY_FOR_PORTFOLIO_RESOURCE_RECOMMENDATION",
  },
  allowed_actions: ["view", "compare"],
  boundaries: ["NO_NAMED_PERSON_ALLOCATION", "NO_SCHEDULE_LEVELING", "NO_SCENARIO_WINNER", "NO_FID", "NO_FUNDS"],
};
const configurationContent = {
  scope: { type: "tenant", workspace_id: null },
  applicable_governance_models: ["CAPITAL_OWNER"],
  resource_roles: [{ role_key: "PROJECT_MANAGER", name: "Project Manager", category: "MANAGEMENT", unit: "FTE" }],
  allowed_units: ["FTE", "HOURS", "CREW_EQUIVALENT"],
  default_unit: "FTE",
  required_demand_coverage_percent: 100,
  period_granularity: "MONTH",
  allowed_timing_methods: ["NO_SHIFT", "SHIFT_START_KEEP_DURATION", "CUSTOM_SCENARIO_DATES"],
  overload_policy: "ALLOW_WITH_WARNING",
  maximum_utilization_percent: 100,
  scenario_max_count: 20,
  controlled_constraints: ["ROLE_CAPACITY", "PERIOD_CAPACITY"],
};

describe("Portfolio Resource Planning Gate 07H", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.portfolioOptions.mockResolvedValue([{ id: 71, name: "Capital Portfolio" }]);
    mocks.overview.mockResolvedValue(overview);
    mocks.compare.mockResolvedValue({
      portfolio_workspace_id: 71,
      scenarios: [{ scenario_name: "Balanced alternative" }, { scenario_name: "Accelerated alternative" }],
      project_matrix: [{ project_number: "PRJ-101" }],
      pairwise_delta: { overloaded_period_delta: 0 },
      role_demand_delta: [{ role: "PROJECT_MANAGER", delta: "0.00" }],
      warnings: [],
    });
    mocks.configurations.mockResolvedValue([
      {
        id: 501,
        code: "gate07h-default",
        name: "Gate 07H Default",
        description: "",
        status: "draft",
        revision: 1,
        version: 1,
        content_json: configurationContent,
        content_hash: "g".repeat(64),
      },
    ]);
    mocks.previewConfiguration.mockResolvedValue({ persisted: false, publishable: true });
  });

  it("shows readiness, strategic overload analytics and comparison without operational allocation", async () => {
    const user = userEvent.setup();
    render(<PortfolioResourceWorkspace portfolioId={71} token="token" />);
    expect(await screen.findByText("READY_FOR_PORTFOLIO_RESOURCE_RECOMMENDATION")).toBeInTheDocument();
    expect(screen.getByText("NO_NAMED_PERSON_ALLOCATION")).toBeInTheDocument();
    expect(screen.getByRole("grid", { name: "Role Period Capacity Heatmap" })).toHaveTextContent("150%");
    await user.click(screen.getByRole("button", { name: /scenarios/i }));
    expect(await screen.findByRole("table", { name: "Resource Scenario Project Grid" })).toHaveTextContent(
      "Growth Project"
    );
    await user.click(screen.getByRole("button", { name: /comparison/i }));
    const comparison = await screen.findByRole("region", { name: "Resource Scenario Comparison" });
    const checks = within(comparison).getAllByRole("checkbox");
    await user.click(checks[0]);
    await user.click(checks[1]);
    await user.click(within(comparison).getByRole("button", { name: "Compare selected" }));
    await waitFor(() => expect(mocks.compare).toHaveBeenCalledWith("token", 71, [41, 42]));
    expect(await within(comparison).findByText("Role demand delta")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /assign person|level schedule|winner|fund|fid/i })
    ).not.toBeInTheDocument();
  });

  it("provides structured ADMIN policy fields and a non-persistent preview", async () => {
    const user = userEvent.setup();
    render(<PortfolioResourceAdminView token="token" />);
    expect(
      await screen.findByRole("heading", { name: "Portfolio Resource Planning Configuration" })
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Default Unit")).toHaveValue("FTE");
    expect(screen.getByLabelText("Overload Policy")).toHaveValue("ALLOW_WITH_WARNING");
    const actions = screen.getByLabelText("Portfolio Resource configuration actions");
    await user.click(within(actions).getByRole("button", { name: "Preview" }));
    await waitFor(() => expect(mocks.previewConfiguration).toHaveBeenCalled());
    expect(
      await screen.findByText(/persisted=false and no capacity, demand or scenario record was created/i)
    ).toBeInTheDocument();
  });
});
