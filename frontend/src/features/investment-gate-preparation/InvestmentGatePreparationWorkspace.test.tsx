import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import InvestmentGatePreparationWorkspace from "./InvestmentGatePreparationWorkspace";

vi.mock("../portfolio-planning/api", () => ({
  portfolioPlanningApi: { portfolioOptions: vi.fn().mockResolvedValue([{ id: 71, name: "Capital Portfolio" }]) },
}));

vi.mock("./api", () => ({
  investmentGatePreparationApi: {
    overview: vi.fn().mockResolvedValue({
      portfolio_workspace_id: 71,
      governance_eligible: true,
      source_contract: { final_output: "READY_FOR_INVESTMENT_GATE_PREPARATION" },
      profiles: [{ id: 8, profile_code: "PYP-INV-SELECT", name: "Investment Selection Preparation" }],
      preparations: [
        {
          id: 81,
          portfolio_workspace_id: 71,
          preparation_number: "IGP-PF-0001",
          revision: 1,
          name: "Investment selection evidence package",
          description: "",
          investment_gate_profile_id: 8,
          profile_code: "PYP-INV-SELECT",
          profile_revision: 1,
          profile_hash: "a".repeat(64),
          status: "IN_PREPARATION",
          readiness_status: "BLOCKED",
          source_snapshot: { selected_project_ids: [33], project_contexts: [{ fel_stage: "FEL-2" }] },
          evidence_summary: {},
          criterion_policy_snapshot: { policy_revision: 4, policy_hash: "d".repeat(64) },
          criterion_evaluations: [
            {
              criterion_code: "BC-MUST-01",
              criterion_name: "Strategic case accepted",
              criterion_type: "MUST_MEET",
              source_reference: { evidence_type: "BUSINESS_CASE_READINESS" },
              source_value: "READY",
              operator: "IS_READY",
              threshold_or_expected_value: "APPROVED",
              result: "SATISFIED",
              blocking: true,
              required: true,
              policy_revision: 4,
            },
            {
              criterion_code: "BEN-SUCCESS-01",
              criterion_name: "Reliability uplift",
              criterion_type: "SUCCESS_CRITERION",
              source_reference: { evidence_type: "BENEFITS_READINESS" },
              source_value: "12%",
              operator: "IS_READY",
              result: "SATISFIED",
              blocking: false,
              required: false,
              policy_revision: 4,
            },
          ],
          portfolio_context_snapshot: { rank_authority: "PORTFOLIO", resource_constrained: true },
          success_criteria_candidates: [
            { criterion_code: "BEN-SUCCESS-01", criterion_name: "Reliability uplift", result: "SATISFIED" },
          ],
          conditions: [],
          warnings: [],
          blockers: ["MISSING_DEFINITION_READINESS"],
          preparation_source_hash: "b".repeat(64),
          preparation_hash: null,
          revision_version: 4,
          allowed_actions: ["can_edit_preparation"],
          evidence: [
            {
              id: 91,
              preparation_id: 81,
              requirement_key: "fel-stage-readiness",
              evidence_type: "FEL_STAGE_READINESS",
              scope_type: "EACH_PROJECT",
              scope_id: 33,
              evidence_origin: "MANUAL_REFERENCE",
              status: "MISSING",
              source_record_id: null,
              scope_reference_hash: "c".repeat(64),
              evidence_date: null,
              valid_until: null,
              issuer: null,
              owner: null,
              summary: "Required evidence is not available.",
              evidence_refs: [],
              validation_note: null,
              warnings: [],
              blockers: [],
              classification: "A",
              blocking: true,
              provider_key: "GATE07J_FEL_PROJECT_DEFINITION",
              coverage_requirement: 100,
              source_current: true,
              source_readiness_status: "BLOCKED",
              evidence_quality: "ACCEPTABLE",
              evidence_confidence: "MEDIUM",
              quality_origin: "PROVIDER",
              source_version: 3,
              as_of: "2026-09-18T00:00:00Z",
              resolution_status: "MISSING",
              revision_version: 1,
            },
          ],
          readiness: {
            preparation_id: 81,
            status: "IN_PREPARATION",
            readiness_status: "BLOCKED",
            source_current: true,
            required_requirement_count: 5,
            valid_requirement_count: 4,
            required_project_count: 1,
            valid_project_count: 0,
            blocked_project_count: 1,
            coverage_percent: 0,
            category_summary: {},
            evidence_coverage: {},
            evidence_readiness_status: "BLOCKED",
            business_evaluation_status: "READY",
            portfolio_context_status: "CONSTRAINED",
            decision_package_status: "NOT_READY_FOR_INVESTMENT_DECISION",
            criterion_evaluations: [],
            unresolved_mandatory_criteria: [],
            success_criteria_candidates: [],
            criterion_policy: {},
            warnings: [],
            blockers: ["MISSING_DEFINITION_READINESS"],
            investment_gate_preparation_ready: false,
            can_enter_investment_decision: false,
            can_enter_fid: false,
            final_output: "GATE07J_REWORK_REQUIRED",
          },
        },
      ],
      boundaries: ["No investment approval", "No FID"],
    }),
    projectReadiness: vi.fn().mockResolvedValue({
      preparation_id: 81,
      required_project_count: 1,
      valid_project_count: 0,
      blocked_project_count: 1,
      coverage_percent: 0,
      projects: [
        {
          project_id: 33,
          required_count: 1,
          valid_count: 0,
          missing_requirements: ["fel-stage-readiness"],
          status: "BLOCKED",
        },
      ],
    }),
  },
}));

describe("InvestmentGatePreparationWorkspace", () => {
  beforeEach(() => vi.clearAllMocks());
  it("shows governed readiness, evidence navigation and the explicit FID safeguard", async () => {
    render(<InvestmentGatePreparationWorkspace token="token" />);
    await waitFor(() => expect(screen.getByText("Investment Gate Preparation")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Evidence Package" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Project Readiness" })).toBeInTheDocument();
    expect(screen.getByText("can_enter_fid = false")).toBeInTheDocument();
    expect(screen.getByText("GATE07J_REWORK_REQUIRED")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Gate evaluation stages" })).toHaveTextContent(
      "Portfolio & Resource Context"
    );
  });

  it("shows the compact evidence/criteria matrix with quality separate from readiness", async () => {
    const user = userEvent.setup();
    render(<InvestmentGatePreparationWorkspace token="token" />);
    await screen.findByRole("heading", { name: "Investment Gate Preparation" });
    await user.click(screen.getByRole("button", { name: "Gate Matrix" }));
    const matrix = screen.getByRole("table", { name: "Gate evidence and decision criteria matrix" });
    expect(matrix).toHaveTextContent("Evidence Class A");
    expect(matrix).toHaveTextContent("MUST_MEET");
    expect(matrix).toHaveTextContent("ACCEPTABLE");
    expect(matrix).toHaveTextContent("Confidence MEDIUM");
    expect(matrix).toHaveTextContent("APPROVED");
    expect(screen.getByRole("group", { name: "Decision criteria grouped by taxonomy" })).toHaveTextContent(
      "Success criteria candidates"
    );
    expect(screen.getByRole("region", { name: "Frozen Portfolio context" })).toHaveTextContent("PORTFOLIO");
  });
});
