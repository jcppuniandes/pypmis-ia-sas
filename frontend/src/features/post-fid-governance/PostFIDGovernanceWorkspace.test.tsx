import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PostFIDGovernanceAdminView from "./PostFIDGovernanceAdminView";
import PostFIDGovernanceWorkspace from "./PostFIDGovernanceWorkspace";

const api = vi.hoisted(() => ({
  list: vi.fn(),
  evaluate: vi.fn(),
  previewRefresh: vi.fn(),
  refresh: vi.fn(),
  history: vi.fn(),
  handoff: vi.fn(),
  configurations: vi.fn(),
  previewConfiguration: vi.fn(),
  cloneConfiguration: vi.fn(),
  updateConfiguration: vi.fn(),
  publishConfiguration: vi.fn(),
}));

vi.mock("./api", () => ({ postFIDGovernanceApi: api }));

const project = {
  id: 31,
  investment_decision_id: 7,
  project_workspace_id: 14,
  project_number: "PRJ-0014",
  project_name: "Active baseline Project",
  project_type: "CAPITAL",
  governance_model: "CAPITAL_OWNER",
  project_state: "ACTIVE",
  workspace_status: "active",
  initialization_state: "ACTIVATED",
  fid_current: true,
  eligibility_round: 1,
  snapshot_eligibility_status: "NO_REACTIVATION_REQUIRED",
  eligibility_status: "NO_REACTIVATION_REQUIRED",
  final_output: "NO_REACTIVATION_REQUIRED",
  warnings: [],
  blockers: [],
  post_fid_conditions: [],
  open_activation_blockers: 0,
  open_commitment_conditions_count: 0,
  can_initialize: false,
  can_activate: false,
  next_allowed_process: "POST_FID_GOVERNANCE_COMPLETE",
  allowed_actions: ["can_view_post_fid", "can_view_history"],
  fid_decision_hash: "d".repeat(64),
  decision_package_hash: "p".repeat(64),
  condition_snapshot_hash: "c".repeat(64),
  eligibility_hash: "e".repeat(64),
  source_current: true,
  stale: false,
  persisted: true,
  evaluated_at: "2026-09-01T12:00:00",
  evaluated_by: 1,
  revision_version: 1,
};

const decision = {
  investment_decision_id: 7,
  decision_number: "IDEC-00007",
  title: "Full Funds Authorization",
  gate_profile: "PYP-FFA",
  status: "DECIDED",
  outcome: "GO",
  is_fid: true,
  post_fid_handoff: "READY_FOR_POST_FID_PROJECT_GOVERNANCE",
  final_output: "NO_REACTIVATION_REQUIRED",
  project_count: 1,
  projects: [project],
  next: "READY_TO_ENTER_OPERATIONAL_MACROPROCESSES_REVIEW",
};

const configuration = {
  id: 5,
  name: "Default Post-FID Project Governance",
  description: "Gate 07L policy",
  status: "published",
  revision: 1,
  version: 1,
  content_json: {
    applicable_gate_profiles: ["PYP-FFA"],
    applicable_governance_models: ["CAPITAL_OWNER"],
    handoff_rules: { delegate_initialization: true, delegate_activation: true },
  },
  content_hash: "f".repeat(64),
};

describe("Gate 07L Post-FID Project Governance", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.list.mockResolvedValue([decision]);
    api.evaluate.mockResolvedValue([project]);
    api.previewRefresh.mockResolvedValue({
      investment_decision_id: 7,
      deltas: [],
      projects: [project],
      persisted: false,
    });
    api.refresh.mockResolvedValue([project]);
    api.history.mockResolvedValue([]);
    api.configurations.mockResolvedValue([configuration]);
    api.previewConfiguration.mockResolvedValue({ persisted: false, project_eligibility: [project] });
  });

  it("renders the per-Project matrix and protects the active Project from reactivation", async () => {
    render(<PostFIDGovernanceWorkspace initialView="post-fid-eligibility-matrix" token="token" />);
    expect(await screen.findByRole("heading", { name: "Post-FID Project Governance" })).toBeInTheDocument();
    const table = await screen.findByRole("table");
    expect(within(table).getByText("PRJ-0014")).toBeInTheDocument();
    expect(within(table).getByText("NO_REACTIVATION_REQUIRED")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Prepare delegated activation/i })).not.toBeInTheDocument();
  });

  it("shows refresh Preview as persisted=false", async () => {
    render(<PostFIDGovernanceWorkspace token="token" />);
    fireEvent.click(await screen.findByRole("button", { name: /Refresh preview/i }));
    expect(await screen.findByRole("status")).toHaveTextContent(/persisted=false/i);
    expect(api.previewRefresh).toHaveBeenCalledWith("token", 7);
  });

  it("renders all ADMIN sections and a non-persistent dry-run", async () => {
    render(<PostFIDGovernanceAdminView token="token" />);
    expect(await screen.findByRole("heading", { name: "Post-FID Project Governance" })).toBeInTheDocument();
    const tabs = screen.getByRole("navigation", { name: "Post-FID configuration sections" });
    expect(within(tabs).getByRole("button", { name: "Activation Eligibility" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Dry-run/i }));
    expect(await screen.findByText(/persisted=false/i)).toBeInTheDocument();
  });
});
