import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PortfolioConvergenceAdminView from "./PortfolioConvergenceAdminView";
import PortfolioConvergenceWorkspace from "./PortfolioConvergenceWorkspace";

const mocks = vi.hoisted(() => ({
  overview: vi.fn(),
  create: vi.fn(),
  addAlternative: vi.fn(),
  compare: vi.fn(),
  submit: vi.fn(),
  returnToDraft: vi.fn(),
  recommend: vi.fn(),
  refreshPreview: vi.fn(),
  configurations: vi.fn(),
  previewConfiguration: vi.fn(),
  cloneConfiguration: vi.fn(),
  updateConfiguration: vi.fn(),
  publishConfiguration: vi.fn(),
  portfolioOptions: vi.fn(),
}));

vi.mock("./api", () => ({ portfolioConvergenceApi: mocks }));
vi.mock("../portfolio-planning/api", () => ({
  portfolioPlanningApi: { portfolioOptions: mocks.portfolioOptions },
}));

const alternative = {
  id: 301,
  convergence_id: 201,
  alternative_name: "Aligned baseline",
  budget_scenario_id: 101,
  resource_scenario_id: 102,
  alignment_status: "ALIGNED",
  budget_feasibility: "BUDGET_FEASIBLE",
  resource_feasibility: "RESOURCE_FEASIBLE",
  feasibility_status: "FEASIBLE",
  budget_summary: {},
  resource_summary: {},
  strategic_summary: { selected_project_ids: [11, 12] },
  risk_summary: {},
  project_matrix: [],
  forced_conflicts: [],
  warnings: [],
  blockers: [],
  alternative_hash: "a".repeat(64),
  revision_version: 1,
};
const convergence = {
  id: 201,
  portfolio_workspace_id: 71,
  convergence_revision: 1,
  name: "Executive convergence",
  description: "",
  status: "DRAFT",
  required_budget_branch: true,
  required_resource_branch: true,
  source_analysis_hash: "b".repeat(64),
  convergence_source_hash: "c".repeat(64),
  source_current: true,
  recommended_alternative_id: null,
  recommendation_reason: null,
  conditions: [],
  risks_acknowledged: [],
  decision_support_summary: null,
  recommendation_hash: null,
  recommended_at: null,
  warnings: [],
  blockers: [],
  revision_version: 2,
  alternatives: [alternative],
  allowed_actions: ["can_compare", "can_submit_review"],
};
const overview = {
  portfolio_workspace_id: 71,
  required_branches: { budget: true, resource: true },
  budget_contract: { budget_planning_hash: "d".repeat(64) },
  resource_contract: { resource_planning_hash: "e".repeat(64) },
  source_compatibility: { compatible: true },
  candidate_budget_scenarios: [{ id: 101, scenario_name: "Budget balanced" }],
  candidate_resource_scenarios: [{ id: 102, scenario_name: "Capacity balanced" }],
  convergences: [convergence],
  readiness: {
    portfolio_workspace_id: 71,
    convergence_id: 201,
    convergence_revision: 1,
    status: "BLOCKED",
    alternative_count: 1,
    recommended_alternative_id: null,
    source_current: true,
    warnings: [],
    blockers: ["FORMAL_PORTFOLIO_RECOMMENDATION_REQUIRED"],
    recommendation_hash: null,
    portfolio_recommendation_ready: false,
    can_enter_investment_gate_preparation: false,
    can_enter_fid: false,
    allowed_actions: ["can_submit_review"],
    final_output: "GATE07I_REWORK_REQUIRED",
  },
  boundaries: ["PORTFOLIO_RECOMMENDATION_IS_NOT_INVESTMENT_APPROVAL", "CAN_ENTER_FID_IS_ALWAYS_FALSE"],
};
const configurationContent = {
  scope: { type: "tenant", workspace_id: null },
  required_budget_branch: true,
  required_resource_branch: true,
  require_identical_project_sets: true,
  forced_conflict_is_blocker: true,
  allow_conditional_recommendation: false,
  recommender_sod_required: false,
};

describe("Portfolio Scenario Convergence Gate 07I", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.portfolioOptions.mockResolvedValue([{ id: 71, name: "Capital Portfolio" }]);
    mocks.overview.mockResolvedValue(overview);
    mocks.compare.mockResolvedValue({
      convergence_id: 201,
      alternatives: [],
      feasibility_matrix: [
        {
          alternative_id: 301,
          alternative: "Aligned baseline",
          budget: "BUDGET_FEASIBLE",
          resource: "RESOURCE_FEASIBLE",
          alignment: "ALIGNED",
          overall: "FEASIBLE",
        },
      ],
      project_matrix: [],
      pairwise_delta: {},
      warnings: ["NO_OPTIMIZER_OR_INVESTMENT_APPROVAL"],
    });
    mocks.configurations.mockResolvedValue([
      {
        id: 501,
        name: "Gate 07I Default",
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

  it("shows independent sources, formal readiness and never exposes an FID control", async () => {
    const user = userEvent.setup();
    render(<PortfolioConvergenceWorkspace portfolioId={71} token="token" />);
    expect(await screen.findByText("GATE07I_REWORK_REQUIRED")).toBeInTheDocument();
    expect(screen.getByText("can_enter_fid = false")).toBeInTheDocument();
    expect(screen.getByText("Gate 07G · Budget branch")).toBeInTheDocument();
    expect(screen.getByText("Gate 07H · Resource branch")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "alternatives" }));
    expect(await screen.findByText("Aligned baseline")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve investment|enter fid/i })).not.toBeInTheDocument();
  });

  it("previews ADMIN policy without persisting operational records", async () => {
    const user = userEvent.setup();
    render(<PortfolioConvergenceAdminView token="token" />);
    expect(
      await screen.findByRole("heading", { name: "Portfolio Scenario Convergence Configuration" })
    ).toBeInTheDocument();
    expect(screen.getByText("Require Gate 07G budget branch")).toBeInTheDocument();
    const actions = screen.getAllByRole("button").filter((item) => item.textContent?.includes("Preview"));
    await user.click(actions[0]);
    await waitFor(() => expect(mocks.previewConfiguration).toHaveBeenCalled());
    expect(
      await screen.findByText(/persisted=false; no convergence or recommendation was created/i)
    ).toBeInTheDocument();
    const section = screen.getByRole("region", { name: "Portfolio Scenario Convergence Configuration" });
    expect(within(section).queryByRole("button", { name: /approve investment|fid/i })).not.toBeInTheDocument();
  });
});
