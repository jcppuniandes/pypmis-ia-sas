import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import FundsManagerAdminView from "./FundsManagerAdminView";
import FundsManagerWorkspace from "./FundsManagerWorkspace";

const mocks = vi.hoisted(() => ({
  overview: vi.fn(),
  refreshPreview: vi.fn(),
  evidence: vi.fn(),
  configurations: vi.fn(),
  previewConfiguration: vi.fn(),
  portfolioOptions: vi.fn(),
}));

vi.mock("./api", () => ({ fundsManagerApi: mocks }));
vi.mock("../portfolio-planning/api", () => ({
  portfolioPlanningApi: { portfolioOptions: mocks.portfolioOptions },
}));

const readiness = {
  snapshot_id: 901,
  tenant_id: 1,
  scope_type: "PORTFOLIO",
  portfolio_workspace_id: 71,
  project_workspace_id: null,
  source_convergence_id: 301,
  source_recommendation_hash: "1".repeat(64),
  recommended_project_set_hash: "2".repeat(64),
  budget_scenario_id: 401,
  budget_scenario_hash: "3".repeat(64),
  funding_requirement_source: { type: "GATE07I_RECOMMENDED_ALTERNATIVE" },
  funding_requirement_hash: "4".repeat(64),
  required_amount: 10_000_000,
  required_currency: "COP",
  confirmed_funding_amount: 10_000_000,
  reserved_funding_amount: 0,
  funding_gap: 0,
  confirmed_coverage_percent: 100,
  potential_coverage_percent: 100,
  project_coverage_summary: [],
  period_coverage_summary: [],
  restriction_summary: { status: "ELIGIBLE" },
  conditions_summary: { status: "CONTROLLED", open_blocking: 0 },
  warnings: [],
  blockers: [],
  funding_readiness_status: "READY",
  funding_readiness_hash: "5".repeat(64),
  source_hash: "6".repeat(64),
  source_current: true,
  can_supply_investment_gate_evidence: true,
  allowed_actions: ["can_supply_investment_gate_evidence"],
  final_output: "READY_FOR_GOVERNED_FUNDING_EVIDENCE",
};

describe("Gate 07J-FUND Funds Manager", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.portfolioOptions.mockResolvedValue([{ id: 71, name: "Capital Portfolio" }]);
    mocks.overview.mockResolvedValue({
      portfolio_workspace_id: 71,
      governance_model_applicable: true,
      active_funds: 1,
      comparable_currency: "COP",
      authorized_funding: 10_000_000,
      confirmed_assigned: 10_000_000,
      reserved_assigned: 0,
      available_funding: 0,
      funding_gap: 0,
      coverage_percent: 100,
      funding_readiness: "READY",
      funding_sources: [],
      funds: [],
      assignments: [],
      readiness,
      boundaries: [
        "BUDGET_IS_NOT_FUNDING",
        "FUNDING_AVAILABLE_IS_NOT_INVESTMENT_APPROVED",
        "NO_TREASURY_ACCOUNTING_COMMITMENTS_OR_PAYMENTS",
        "NO_FID_PROJECT_INITIALIZATION_ACTIVATION_OR_EXECUTION",
      ],
    });
    mocks.refreshPreview.mockResolvedValue({ persisted: false, proposed_source_hash: readiness.source_hash });
    mocks.evidence.mockResolvedValue({
      source_module: "FUNDS_MANAGER",
      evidence_type: "FUNDING_READINESS",
      can_supply_investment_gate_evidence: true,
    });
    mocks.configurations.mockResolvedValue([
      {
        id: 701,
        name: "Gate 07J-FUND Default",
        description: "Governed funding policy",
        status: "draft",
        revision: 1,
        version: 1,
        content_json: {
          scope: { type: "tenant", workspace_id: null },
          minimum_confirmed_coverage_percent: 100,
          minimum_potential_coverage_percent: 100,
          reserved_counts_toward_readiness: false,
          conditional_funds_count_toward_readiness: false,
          require_each_project_coverage: false,
          require_period_coverage: false,
          open_condition_is_blocker: true,
          fund_creator_cannot_authorize: true,
        },
        content_hash: "7".repeat(64),
      },
    ]);
    mocks.previewConfiguration.mockResolvedValue({
      persisted: false,
      publishable: true,
      gate07j_funding_evidence_preview: { source_module: "FUNDS_MANAGER" },
    });
  });

  it("shows governed readiness without Investment, Treasury or payment controls", async () => {
    const user = userEvent.setup();
    render(<FundsManagerWorkspace initialView="funds-readiness" token="token" />);
    expect(await screen.findByRole("heading", { name: "Funding Readiness" })).toBeInTheDocument();
    expect(await screen.findByText("YES")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /refresh preview/i }));
    await waitFor(() => expect(mocks.refreshPreview).toHaveBeenCalledWith("token", 71));
    await user.click(screen.getByRole("button", { name: /open gate 07j evidence/i }));
    expect(await screen.findByText(/FUNDS_MANAGER/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve investment|enter fid|payment/i })).not.toBeInTheDocument();
  });

  it("previews ADMIN policy without persisting Funds, Assignments or readiness", async () => {
    const user = userEvent.setup();
    render(<FundsManagerAdminView token="token" />);
    const admin = await screen.findByRole("region", { name: "Funds Manager Configuration" });
    await user.click(within(admin).getByRole("button", { name: "Preview" }));
    await waitFor(() => expect(mocks.previewConfiguration).toHaveBeenCalled());
    expect(within(admin).getByRole("status")).toHaveTextContent("persisted=false");
    expect(within(admin).queryByRole("button", { name: /approve investment|fid|payment/i })).not.toBeInTheDocument();
  });
});
