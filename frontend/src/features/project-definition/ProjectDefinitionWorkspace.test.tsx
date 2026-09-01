import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ProjectDefinitionWorkspace from "./ProjectDefinitionWorkspace";

vi.mock("./api", () => ({
  projectDefinitionApi: {
    overview: vi.fn().mockResolvedValue({
      projects: [
        {
          id: 33,
          code: "CAP-033",
          name: "Capital Project",
          status: "pending",
          project_type: "Industrial",
          governance_model: "CAPITAL_OWNER",
        },
      ],
      selected_project: {
        id: 33,
        code: "CAP-033",
        name: "Capital Project",
        status: "pending",
        project_type: "Industrial",
        governance_model: "CAPITAL_OWNER",
      },
      fel_status: {
        id: 7,
        project_workspace_id: 33,
        current_stage_code: "FEL-2",
        status: "IN_STAGE",
        effective_framework_id: 9,
        effective_framework_revision: 1,
        effective_framework_hash: "a".repeat(64),
        current_assessment_id: 11,
        latest_completed_assessment_id: 10,
        readiness_status: "READY",
        definition_source_hash: "b".repeat(64),
        revision_version: 3,
        allowed_actions: ["can_submit_stage_review"],
      },
      latest_assessment: {
        id: 10,
        project_workspace_id: 33,
        assessment_number: "PDA-CAP-033-002",
        assessment_version: 2,
        framework_code: "PYP-CUSTOM-DEFINITION",
        framework_type: "CUSTOM",
        framework_version: "1.0",
        fel_stage_code: "FEL-2",
        assessment_date: "2026-08-26T12:00:00",
        status: "COMPLETED",
        raw_score: 85,
        normalized_score: 85,
        maturity_level: "READY",
        threshold_status: "MEETS_REQUIRED",
        category_results: [],
        element_results: [],
        blocking_items: [],
        warnings: [],
        actions_summary: {},
        evidence_refs: [],
        source_snapshot: { applicable_elements: [] },
        definition_source_hash: "b".repeat(64),
        assessed_by: 2,
        completed_by: 2,
        assessment_hash: "c".repeat(64),
        revision_version: 2,
        allowed_actions: ["can_start_reevaluation"],
      },
      readiness: {
        status: "READY",
        project_workspace_id: 33,
        current_FEL_stage: "FEL-2",
        latest_completed_assessment_id: 10,
        framework_code: "PYP-CUSTOM-DEFINITION",
        framework_version: "1.0",
        assessment_hash: "c".repeat(64),
        maturity_level: "READY",
        threshold_status: "MEETS_REQUIRED",
        required_maturity: "ADEQUATE",
        required_stage: "FEL-2",
        required_maturity_met: true,
        blocking_item_count: 0,
        open_blocking_action_count: 0,
        evidence_coverage: 100,
        warnings: [],
        blockers: [],
        definition_readiness_hash: "d".repeat(64),
        source_current: true,
        can_supply_investment_gate_evidence: true,
      },
      actions: [],
      history: [],
      maturity_trend: [],
      framework: { framework_code: "PYP-CUSTOM-DEFINITION", framework_type: "CUSTOM" },
      boundaries: {
        investment_decision_created: false,
        fid_created: false,
        funds_created: false,
        project_activated: false,
      },
    }),
  },
}));

describe("ProjectDefinitionWorkspace", () => {
  beforeEach(() => vi.clearAllMocks());
  it("keeps FEL stage, maturity and Investment Gate evidence separate from FID", async () => {
    render(<ProjectDefinitionWorkspace token="token" />);
    await waitFor(() => expect(screen.getByText("Project Definition / FEL Manager")).toBeInTheDocument());
    expect(screen.getByText("FEL-2 / READY")).toBeInTheDocument();
    expect(screen.getByText("FID = false")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Definition Assessments" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /approve investment|enter fid|go|hold|kill/i })
    ).not.toBeInTheDocument();
  });
});
