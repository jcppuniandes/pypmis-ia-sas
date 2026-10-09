import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import StrategicPlanningEntryWorkspace from "./StrategicPlanningEntryWorkspace";

const option = {
  id: 71,
  decision_number: "SGD-00071",
  project_proposal_id: 31,
  proposal_number: "PROP-00031",
  project_name: "New processing train",
  target_portfolio_workspace_id: 12,
  target_portfolio_name: "Growth Portfolio",
  outcome: "APPROVE",
  readiness_status: "READY_FOR_PORTFOLIO_INTAKE",
  project_creation_request_id: null,
  project_creation_request_state: null,
  project_workspace_id: null,
};

const readiness = {
  status: "BLOCKED",
  can_enter: false,
  required_source_data: ["active_portfolio_membership"],
  available_source_data: [],
  blocking_issues: ["ACTIVE_PORTFOLIO_MEMBERSHIP_REQUIRED"],
  warnings: ["No score is calculated by Gate 07D."],
  project_type: "industrial",
  suggested_definition_framework: "PDRI_INDUSTRIAL_REFERENCE",
};

const preview = {
  decision: { id: 71, decision_number: "SGD-00071", outcome: "APPROVE" },
  proposal: { id: 31, proposal_number: "PROP-00031", name: "New processing train" },
  source_idea: { id: 11, idea_number: "IDEA-00011" },
  target_portfolio: {
    id: 12,
    name: "Growth Portfolio",
    code: "PORT-GROWTH",
    record_code: "001.003",
    workspace_type_code: "portfolio",
    status: "active",
    version: 2,
  },
  project_name: "New processing train",
  project_number_preview: "PRJ-00042",
  record_code_preview: "001.003.004",
  allowed_project_parents: [
    {
      id: 12,
      name: "Growth Portfolio",
      workspace_type_code: "portfolio",
      record_code: "001.003",
    },
  ],
  default_project_parent: {
    id: 12,
    name: "Growth Portfolio",
    workspace_type_code: "portfolio",
    record_code: "001.003",
  },
  strategic_objectives: [{ code: "growth", name: "Growth" }],
  suggested_project_type: "industrial",
  suggested_template: { id: 51, code: "industrial-project", name: "Industrial Project" },
  template_options: [{ id: 51, code: "industrial-project", name: "Industrial Project" }],
  project_manager_required: true,
  project_manager_candidate: { id: 1, name: "Portfolio Lead", email: "lead@example.test" },
  project_manager_options: [{ id: 1, name: "Portfolio Lead", email: "lead@example.test" }],
  mapped_fields: { business_need: "Increase throughput" },
  portfolio_planning_entry_preview: { workspace_status: "pending" },
  portfolio_evaluation_readiness_preview: readiness,
  project_definition_readiness_preview: {
    ...readiness,
    status: "READY",
    can_enter: true,
    blocking_issues: [],
    required_source_data: ["project_type"],
    available_source_data: ["project_type"],
  },
  creation_policy: {
    project_creation_process: "GATE_05B",
    initial_workspace_status: "pending",
    initialization: false,
    activation: false,
    four_eyes_preserved: true,
  },
  source_decision_hash: "d".repeat(64),
  source_readiness_hash: "r".repeat(64),
  configuration: { code: "default", revision: 1 },
  blocking_issues: [],
  warnings: [],
  persisted: false,
};

describe("StrategicPlanningEntryWorkspace", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const body = path.endsWith("/options") && !init?.method ? [option] : preview;
        return { ok: true, status: 200, json: async () => body } as Response;
      })
    );
  });

  it("shows Gate 07C lineage and governed Gate 05B prefill without execution controls", async () => {
    render(<StrategicPlanningEntryWorkspace token="token" />);

    expect(await screen.findByRole("heading", { name: "Strategic Project Planning Entry" })).toBeInTheDocument();
    expect(await screen.findByText("Gate 07C Input Contract")).toBeInTheDocument();
    expect(screen.getByText("SGD-00071")).toBeInTheDocument();
    expect(screen.getByText("PROP-00031")).toBeInTheDocument();
    expect(screen.getByText("IDEA-00011")).toBeInTheDocument();
    expect(screen.getByText("Growth Portfolio")).toBeInTheDocument();
    expect(screen.getByLabelText("Published Project template")).toHaveValue("51");
    expect(screen.getByRole("button", { name: /Create ProjectCreationRequest/ })).toBeEnabled();
    expect(screen.queryByText(/PortfolioCandidate/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Activate/ })).not.toBeInTheDocument();
  });
});
