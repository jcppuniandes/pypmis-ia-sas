import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import StrategicGateWorkspace from "./StrategicGateWorkspace";

const options = {
  decision_number_preview: "SGD-00002",
  eligible_proposals: [
    {
      id: 4,
      proposal_number: "PROP-00001",
      name: "Digital delivery platform",
      owning_workspace_id: 10,
      target_portfolio_workspace_id: 20,
      can_create: true,
      blockers: [],
    },
  ],
  users: [{ id: 1, name: "Admin", email: "admin@demo.local" }],
  gate_types: ["PROJECT_PROPOSAL_GATE"],
};

const decision = {
  id: 21,
  decision_number: "SGD-00001",
  context_type: "PROJECT_PROPOSAL",
  context_id: 4,
  project_proposal_id: 4,
  project_proposal_number: "PROP-00001",
  project_proposal_name: "Digital delivery platform",
  gate_type: "PROJECT_PROPOSAL_GATE",
  gate_round: 1,
  state: "IN_REVIEW",
  outcome: null,
  proposal_status_at_entry: "READY_FOR_STRATEGIC_GATE",
  proposal_readiness_status: "READY_FOR_STRATEGIC_GATE_DECISION",
  proposal_readiness_hash: "readiness-hash-1234567890",
  proposal_readiness_snapshot: { status: "READY_FOR_STRATEGIC_GATE_DECISION" },
  proposal_snapshot: { proposal_number: "PROP-00001", status: "READY_FOR_STRATEGIC_GATE" },
  source_idea_snapshot: { idea_number: "IDEA-00001", state: "ACCEPTED" },
  accepted_idea_evaluation_snapshot: { id: 3, total_score: "82.5" },
  proposal_evaluation_snapshot: { id: 9, total_score: "80.0" },
  source_idea_id: 1,
  accepted_idea_evaluation_id: 3,
  proposal_evaluation_id: 9,
  owning_workspace_id: 10,
  owning_workspace_name: "Enterprise",
  target_portfolio_workspace_id: 20,
  target_portfolio_name: "Capital Portfolio",
  strategic_objectives_snapshot: [{ code: "growth" }],
  proposal_score: "80.0000",
  proposal_evaluation_revision: 1,
  configuration_id: 31,
  configuration_revision: 1,
  configuration_hash: "config-hash",
  configuration_snapshot: { decision_authority: { mode: "SINGLE_DECISION_MAKER" } },
  decision_criteria_snapshot: [{ code: "strategic_fit", label: "Strategic Fit", weight: 20 }],
  decision_checklist_snapshot: [
    {
      code: "proposal_readiness_valid",
      label: "Proposal readiness is valid",
      status: "PASS",
      blocking: true,
      evidence: "readiness-hash",
    },
  ],
  conditions: [],
  evidence_refs: [{ reference: "SGD-EVIDENCE" }],
  decision_reason: "Strategic package prepared.",
  decision_comments: "",
  decision_maker_user_id: 1,
  decision_maker_name: "Admin",
  committee_snapshot: null,
  decision_hash: "",
  prepared_by_user_id: 1,
  prepared_by_name: "Admin",
  prepared_at: "2026-08-13T10:00:00Z",
  submitted_at: "2026-08-13T10:10:00Z",
  review_started_at: "2026-08-13T10:20:00Z",
  decided_at: null,
  deferred_until: null,
  voided_at: null,
  allowed_actions: ["decide", "return_to_preparer", "void"],
  revision_version: 3,
  created_at: "2026-08-13T10:00:00Z",
  updated_at: "2026-08-13T10:20:00Z",
};

const preview = {
  decision_number_preview: "SGD-00002",
  project_proposal: { id: 4, proposal_number: "PROP-00001", status: "READY_FOR_STRATEGIC_GATE" },
  source_idea: { id: 1, idea_number: "IDEA-00001", state: "ACCEPTED" },
  accepted_idea_evaluation: { id: 3, total_score: "82.5" },
  proposal_evaluation: { id: 9, total_score: "80.0" },
  readiness: { status: "READY_FOR_STRATEGIC_GATE_DECISION", readiness_hash: "ready-hash" },
  owning_workspace: { id: 10, name: "Enterprise" },
  target_portfolio: { id: 20, name: "Capital Portfolio" },
  strategic_objectives: [{ code: "growth" }],
  gate_type: "PROJECT_PROPOSAL_GATE",
  configuration: { id: 31, revision: 1 },
  decision_checklist: [],
  decision_criteria: [],
  authority: { mode: "SINGLE_DECISION_MAKER" },
  committee_policy: { enabled: false },
  blockers: [],
  warnings: [],
  persisted: false,
};

describe("StrategicGateWorkspace", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        let body: unknown = [decision];
        if (path.endsWith("/options")) body = options;
        else if (path.includes("portfolio-intake-readiness"))
          body = {
            status: "GATE07C_REWORK_REQUIRED",
            can_create_portfolio_candidate: false,
            strategic_gate_decision_id: 21,
            decision_number: "SGD-00001",
            outcome: null,
            project_proposal_id: 4,
            project_proposal_number: "PROP-00001",
            source_idea_id: 1,
            decision_hash: "",
            readiness_hash: "portfolio-hash",
            blockers: ["DECISION_NOT_DECIDED"],
            warnings: [],
          };
        else if (path.includes("/history")) body = [{ event_type: "strategic_gate.created" }];
        else if (path.endsWith("/preview") && init?.method === "POST") body = preview;
        return { ok: true, status: 200, json: async () => body } as Response;
      })
    );
  });

  it("renders queues, snapshots, checklist, authority, outcomes and Portfolio readiness", async () => {
    render(<StrategicGateWorkspace token="token" />);
    expect(await screen.findByRole("heading", { name: "Strategic Gate Decision" })).toBeInTheDocument();
    expect(await screen.findByText("SGD-00001 · PROP-00001")).toBeInTheDocument();
    expect(screen.getByText("READY_FOR_STRATEGIC_GATE_DECISION")).toBeInTheDocument();
    expect(screen.getByText(/Proposal readiness is valid/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "APPROVE" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "RETURN" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "REJECT" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "DEFER" })).toBeInTheDocument();
    expect(await screen.findByText(/can_create_portfolio_candidate = false/)).toBeInTheDocument();
  });

  it("previews a gate-ready Proposal without reserving an SGD number", async () => {
    render(<StrategicGateWorkspace token="token" />);
    await screen.findByText("SGD-00001 · PROP-00001");
    fireEvent.click(screen.getByRole("button", { name: /New Decision/ }));
    await waitFor(() => expect(screen.getByLabelText("Create Strategic Gate Decision")).toBeInTheDocument());
    fireEvent.change(screen.getByRole("combobox", { name: /Gate-ready Project Proposal/ }), {
      target: { value: "4" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Preview Decision" }));
    expect(
      await screen.findByText("Preview only. No Decision number or record has been reserved.")
    ).toBeInTheDocument();
    expect(screen.getByText("SGD-00002")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create DRAFT" })).toBeEnabled();
  });
});
