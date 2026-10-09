import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { INVESTMENT_DECISION_ADMIN_SECTIONS } from "./adminSections";
import InvestmentDecisionAdminView from "./InvestmentDecisionAdminView";
import InvestmentDecisionWorkspace from "./InvestmentDecisionWorkspace";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  preparations: vi.fn(),
  history: vi.fn(),
  configurations: vi.fn(),
  previewConfiguration: vi.fn(),
}));
vi.mock("./api", () => ({ investmentDecisionApi: mocks }));

const decision = {
  id: 77,
  decision_number: "IDEC-00001",
  investment_gate_preparation_id: 55,
  portfolio_workspace_id: 7,
  profile_code: "PYP-INV-SELECT",
  decision_round: 1,
  decision_scope_hash: "s".repeat(64),
  status: "READY_FOR_DECISION",
  outcome: null,
  title: "Investment selection",
  executive_summary: "Governed",
  rationale: "",
  conditions: [],
  hold_reason: null,
  recycle_target: null,
  source_preparation_hash: "p".repeat(64),
  source_package_hash: "k".repeat(64),
  source_profile_hash: "r".repeat(64),
  source_policy_hash: "e".repeat(64),
  decision_package_snapshot: { evidence_summary: { risk: "VALID" } },
  configuration_hash: "c".repeat(64),
  configuration_snapshot: {},
  authority_model: "SINGLE_DECISION_MAKER",
  authority: {},
  committee: {},
  quorum: {},
  voting_rule: { rule: "SIMPLE_MAJORITY" },
  checklist: [{ code: "package_reviewed", label: "Frozen package reviewed", blocking: true, acknowledged: true }],
  authorized_amount: null,
  authorized_currency: null,
  authorization_valid_until: null,
  decision_maker_user_id: 2,
  decided_at: null,
  decided_by: null,
  is_fid: false,
  full_funds_authorized: false,
  investment_authorized: false,
  can_activate_project: false,
  decision_hash: null,
  revision_version: 5,
  votes: [],
  readiness: {
    investment_decision_id: 77,
    readiness_status: "READY",
    source_current: true,
    package_frozen: true,
    exact_scope: true,
    checklist_complete: true,
    authority_valid: true,
    quorum_met: true,
    voting_rule_met: true,
    segregation_of_duties_valid: true,
    blockers: [],
    warnings: [],
    final_output: "READY_FOR_INVESTMENT_DECISION",
  },
  allowed_actions: ["can_view_decision", "can_decide"],
  authorization_output: { final_output: "INVESTMENT_DECISION_PENDING", is_fid: false, can_activate_project: false },
};

describe("Gate 07K Investment Decision / FID", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.list.mockResolvedValue([decision]);
    mocks.preparations.mockResolvedValue([
      {
        id: 55,
        preparation_number: "IGP-00001",
        name: "Package",
        profile_code: "PYP-INV-SELECT",
        status: "FROZEN",
        readiness_status: "READY",
        preparation_hash: "p".repeat(64),
      },
    ]);
    mocks.history.mockResolvedValue([
      {
        id: 1,
        event_type: "investment_decision.created",
        outcome: "success",
        metadata: {},
        occurred_at: "2026-08-31T00:00:00",
      },
    ]);
    mocks.configurations.mockResolvedValue([
      {
        id: 9,
        name: "Default Gate 07K",
        description: "Controlled",
        status: "draft",
        revision: 2,
        version: 1,
        content_hash: "c".repeat(64),
        content_json: {
          profiles: { "PYP-INV-SELECT": { go_is_fid: false }, "PYP-FFA": { go_is_fid: true } },
          outcomes: ["GO", "HOLD", "RECYCLE", "KILL"],
          authorization_output: { can_activate_project: false },
        },
      },
    ]);
    mocks.previewConfiguration.mockResolvedValue({ persisted: false, publishable: true });
  });

  it("shows all nine USER views and preserves the no-FID/no-activation boundary", async () => {
    render(<InvestmentDecisionWorkspace initialView="investment-decision-queue" token="token" />);
    expect(await screen.findByRole("heading", { name: "Investment Decision / FID" })).toBeInTheDocument();
    expect(screen.getByText("FID NO")).toBeInTheDocument();
    expect(screen.getByText("Project activation NO")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Investment Decision views" });
    expect(within(nav).getAllByRole("button")).toHaveLength(9);
    expect(
      screen.queryByRole("button", { name: /activate project|issue ntp|execute project/i })
    ).not.toBeInTheDocument();
  });

  it("renders the immutable authorization output separately", async () => {
    render(<InvestmentDecisionWorkspace initialView="investment-decision-output" token="token" />);
    expect(await screen.findByRole("heading", { name: "Authorization Output" })).toBeInTheDocument();
    expect(screen.getByText(/INVESTMENT_DECISION_PENDING/)).toBeInTheDocument();
    expect(screen.getByText(/"can_activate_project": false/)).toBeInTheDocument();
  });

  it("exposes all 20 ADMIN sections and non-persistent dry-run", async () => {
    const user = userEvent.setup();
    render(<InvestmentDecisionAdminView token="token" />);
    const admin = await screen.findByRole("region", { name: "Investment Decision / FID Governance" });
    const tabs = within(admin).getByRole("navigation", { name: "Investment Decision configuration sections" });
    expect(within(tabs).getAllByRole("button")).toHaveLength(20);
    INVESTMENT_DECISION_ADMIN_SECTIONS.forEach((label) =>
      expect(within(tabs).getByRole("button", { name: label })).toBeInTheDocument()
    );
    await user.click(within(admin).getByRole("button", { name: "Dry-run" }));
    await waitFor(() => expect(mocks.previewConfiguration).toHaveBeenCalled());
    expect(within(admin).getByRole("status")).toHaveTextContent("persisted=false");
  });
});
