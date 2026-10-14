import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BusinessCaseAdminView from "./BusinessCaseAdminView";
import BusinessCaseWorkspace from "./BusinessCaseWorkspace";
import { BUSINESS_CASE_ADMIN_SECTIONS } from "./adminSections";

const api = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  revisions: vi.fn(),
  updateRevision: vi.fn(),
  submitReview: vi.fn(),
  complete: vi.fn(),
  createRevision: vi.fn(),
  readiness: vi.fn(),
  previewRefresh: vi.fn(),
  refresh: vi.fn(),
  snapshots: vi.fn(),
  createSnapshot: vi.fn(),
  configurations: vi.fn(),
  previewConfiguration: vi.fn(),
  cloneConfiguration: vi.fn(),
  updateConfiguration: vi.fn(),
  publishConfiguration: vi.fn(),
}));

vi.mock("./api", () => ({ businessCaseApi: api }));

const revision = {
  id: 11,
  business_case_id: 7,
  revision_number: 1,
  revision_label: "R1",
  purpose: "INITIAL_PROPOSAL",
  status: "DRAFT",
  as_of_date: "2026-09-02T12:00:00",
  fel_stage_code: "FEL2",
  title: "Regional interconnection",
  executive_summary: "Governed initial case",
  business_need: "Improve delivery reliability",
  strategic_alignment_json: [{ code: "STR-01" }],
  objectives_json: [{ description: "Increase reliability" }],
  scope_json: { in_scope: "New connection" },
  alternatives_json: [],
  benefits_json: [{ description: "Reduced outages" }],
  assumptions_json: [],
  constraints_json: [],
  delivery_json: { currency: "USD" },
  unresolved_concerns_json: [],
  recommendation_json: { status: "NOT_PREPARED", is_decision: false },
  five_case_json: {
    strategic_case: {
      question: "Why intervene?",
      summary: "The governed need and strategic alignment support intervention.",
      key_findings: [{ code: "STR-01" }],
      assumptions: [],
      warnings: [],
      blockers: [],
      case_conclusion: "Strategically justified",
      case_readiness: "READY",
    },
    economic_case: { summary: "Preferred option is referenced from BA.", case_readiness: "IN_PROGRESS" },
    commercial_case: { summary: "Commercial Strategy remains authoritative.", case_readiness: "BLOCKED" },
    financial_case: { summary: "FIN remains authoritative for metrics.", case_readiness: "NOT_STARTED" },
    management_case: { summary: "FEL and delivery evidence are referenced.", case_readiness: "IN_PROGRESS" },
  },
  five_case_readiness_json: {
    strategic_case: "READY",
    economic_case: "IN_PROGRESS",
    commercial_case: "BLOCKED",
    financial_case: "NOT_STARTED",
    management_case: "IN_PROGRESS",
    overall_business_case_readiness: "BLOCKED",
  },
  source_evidence_matrix_json: [
    {
      case: "strategic_case",
      source_module: "PROJECT_PROPOSAL",
      source_id: 3,
      source_version_id: 1,
      source_hash: "a".repeat(64),
      source_status: "READY_FOR_STRATEGIC_GATE",
      source_readiness: "READY",
      source_current: true,
      as_of_date: "2026-09-02T12:00:00",
      blocking: true,
    },
  ],
  gate_context_json: { gate_profile: "PYP-FFA", governance_model: "CAPITAL_OWNER" },
  source_current: true,
  five_case_hash: "1".repeat(64),
  source_bundle_hash: "2".repeat(64),
  business_case_hash: "3".repeat(64),
  legacy_layout: false,
  source_references_json: { proposal: { id: 3, status: "READY_FOR_STRATEGIC_GATE" } },
  source_hashes_json: { proposal: "a".repeat(64) },
  source_snapshot_hash: "b".repeat(64),
  economic_financial_model_id: null,
  economic_financial_model_version: null,
  economic_financial_model_hash: null,
  financial_model_status: "NOT_AVAILABLE",
  economic_financial_readiness: null,
  economic_financial_as_of_date: null,
  npv: null,
  irr: null,
  payback_period: null,
  benefit_cost_ratio: null,
  readiness_status: "NOT_STARTED",
  readiness_warnings_json: [],
  readiness_blockers_json: [],
  readiness_hash: "c".repeat(64),
  material_change_status: "NO_MATERIAL_CHANGE",
  content_hash: "d".repeat(64),
  preparer_user_id: 1,
  reviewer_user_id: null,
  revision_version: 1,
  created_at: "2026-09-02T12:00:00",
  updated_at: "2026-09-02T12:00:00",
};

const record = {
  id: 7,
  business_case_number: "BC-00001",
  project_workspace_id: 14,
  source_project_proposal_id: 3,
  owning_workspace_id: 2,
  owner_user_id: 1,
  sponsor_user_id: 2,
  status: "DRAFT",
  current_revision_id: 11,
  material_change_review_json: {},
  configuration_id: 5,
  configuration_revision: 1,
  configuration_hash: "e".repeat(64),
  configuration_source_workspace_id: null,
  configuration_resolution_chain_json: [],
  revision_version: 1,
  created_at: "2026-09-02T12:00:00",
  updated_at: "2026-09-02T12:00:00",
  current_revision: revision,
  final_output: "BUSINESS_CASE_IN_PROGRESS",
  next_process: "COMPLETE_GOVERNED_BUSINESS_CASE",
};

const configuration = {
  id: 5,
  name: "Default Governed Business Case Policy",
  description: "Gate 07M-BC policy",
  status: "published",
  revision: 1,
  version: 1,
  content_json: {
    required_sections: ["title", "business_need", "objectives", "scope"],
    separation_of_duties: { reviewer_must_differ_from_preparer: true },
    mapping: { title: "proposal.name" },
  },
  content_hash: "f".repeat(64),
};

describe("Gate 07M-BC Business Case Manager", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.list.mockResolvedValue([record]);
    api.revisions.mockResolvedValue([revision]);
    api.readiness.mockResolvedValue({
      business_case_id: 7,
      revision_id: 11,
      status: "READY",
      warnings: [],
      blockers: [],
      source_current: true,
      readiness_hash: "c".repeat(64),
      final_output: "READY_FOR_GOVERNED_BUSINESS_CASE_EVIDENCE",
      persisted: false,
    });
    api.snapshots.mockResolvedValue([]);
    api.previewRefresh.mockResolvedValue({
      business_case_id: 7,
      current_revision_id: 11,
      source_changes: [],
      material_change_status: "NO_MATERIAL_CHANGE",
      recommended_purpose: "REVALIDATION",
      persisted: false,
    });
    api.configurations.mockResolvedValue([configuration]);
    api.previewConfiguration.mockResolvedValue({ persisted: false, validation_issues: [] });
  });

  it("renders governed lineage and the expected next boundary", async () => {
    render(<BusinessCaseWorkspace initialView="business-case-overview" token="token" />);
    expect(await screen.findByRole("heading", { name: "Business Case Manager" })).toBeInTheDocument();
    expect((await screen.findAllByText("BC-00001 · R1")).length).toBeGreaterThan(0);
    expect(screen.getByText("Output / NEXT").parentElement).toHaveTextContent("COMPLETE_GOVERNED_BUSINESS_CASE");
    expect(screen.getByRole("region", { name: "Five Case readiness summary" })).toHaveTextContent(
      "Strategic CaseREADY"
    );
    expect(screen.getByRole("navigation", { name: "Business Case views" }).querySelectorAll("button")).toHaveLength(10);
  });

  it("renders a governed Case and the normalized read-only evidence matrix", async () => {
    const onNavigate = vi.fn();
    render(<BusinessCaseWorkspace initialView="business-case-strategic" onNavigate={onNavigate} token="token" />);
    expect(await screen.findByText("Strategically justified")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Strategic Case source evidence" })).toHaveTextContent(
      "Project Proposal"
    );
    fireEvent.click(screen.getByRole("button", { name: "View Source Project Proposal" }));
    expect(onNavigate).toHaveBeenCalledWith("project-proposal");
  });

  it("shows compact QRA references in Five Case sources without any simulation or completed-revision mutation", async () => {
    const onNavigate = vi.fn();
    const summary = {
      analysis_type: "COST_QRA",
      project_id: 14,
      run_id: 16,
      run_number: "QRR-16",
      model_definition_id: 10,
      model_version: 3,
      run_hash: "e".repeat(64),
      accepted: true,
      source_current: true,
      readiness: "READY_WITH_WARNINGS",
      convergence: { status: "CONVERGED" },
      selected_percentiles: [{ percentile: 90, value: 1600000 }],
      target_probabilities: { probability_cost_at_or_below_target: 0.82 },
      warnings: ["POTENTIAL_OVERLAP_EXISTING_ALLOWANCE_OR_CONTINGENCY_REVIEW_REQUIRED"],
      blockers: [],
      as_of: "2026-10-12T10:00:00Z",
    };
    const completed = {
      ...revision,
      status: "COMPLETED",
      source_references_json: { ...revision.source_references_json, cost_qra_result: summary },
      source_evidence_matrix_json: [
        {
          case: "economic_case",
          source_module: "COST_QRA_RESULT",
          source_id: 16,
          version: 3,
          hash: "f".repeat(64),
          source_status: "AVAILABLE",
          source_current: true,
          readiness: "READY_WITH_WARNINGS",
          analysis_type: "COST_QRA",
          qra_summary: summary,
        },
      ],
    };
    api.list.mockResolvedValueOnce([{ ...record, status: "COMPLETED", current_revision: completed }]);
    api.revisions.mockResolvedValueOnce([completed]);
    render(<BusinessCaseWorkspace initialView="business-case-economic" onNavigate={onNavigate} token="token" />);
    const compact = await screen.findByRole("region", { name: "COST_QRA evidence summary" });
    expect(compact).toHaveTextContent("QRR-16");
    expect(compact).toHaveTextContent("1600000");
    expect(compact).toHaveTextContent("Tail-convergence limitation");
    const exactSource = "/app/strategy/qra-run-overview?project_id=14&run_id=16";
    expect(within(compact).getByRole("link", { name: "View QRA" })).toHaveAttribute("href", exactSource);
    const tableSource = screen.getByRole("link", { name: "View Source Cost Qra Result" });
    expect(tableSource).toHaveAttribute("href", exactSource);
    const sourceCells = within(tableSource.closest("tr")!).getAllByRole("cell");
    expect(sourceCells[2]).toHaveTextContent("QRR-16 / 3");
    expect(sourceCells[3]).toHaveTextContent("f".repeat(12));
    expect(sourceCells[3]).toHaveAttribute("title", "f".repeat(64));
    expect(sourceCells[4]).toHaveTextContent("READY_WITH_WARNINGS");
    expect(sourceCells[5]).toHaveTextContent("CURRENT");
    expect(sourceCells[6]).not.toHaveTextContent("—");
    expect(onNavigate).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /simulate|execute qra|run qra/i })).not.toBeInTheDocument();
    expect(api.updateRevision).not.toHaveBeenCalled();
  });

  it("shows refresh preview as non-persistent", async () => {
    render(<BusinessCaseWorkspace token="token" />);
    fireEvent.click(await screen.findByRole("button", { name: /Refresh preview/i }));
    expect(await screen.findByRole("status")).toHaveTextContent("persisted=false");
    expect(api.previewRefresh).toHaveBeenCalledWith("token", 7);
  });

  it("renders the extended ADMIN sections and executes a dry-run", async () => {
    render(<BusinessCaseAdminView token="token" />);
    const tabs = await screen.findByRole("navigation", { name: "Business Case configuration sections" });
    expect(within(tabs).getAllByRole("button")).toHaveLength(BUSINESS_CASE_ADMIN_SECTIONS.length);
    expect(within(tabs).getByRole("button", { name: "Case Applicability" })).toBeInTheDocument();
    expect(within(tabs).getByRole("button", { name: "Overall Readiness Rules" })).toBeInTheDocument();
    expect(within(tabs).getByRole("button", { name: "Material Change Rules" })).toBeInTheDocument();
    const previewButtons = screen.getAllByRole("button", { name: "Preview" });
    fireEvent.click(previewButtons[previewButtons.length - 1]);
    expect(await screen.findByRole("status")).toHaveTextContent("persisted=false");
  });
});
