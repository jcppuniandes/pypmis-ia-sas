import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ProjectProposalWorkspace from "./ProjectProposalWorkspace";

const options = {
  number_preview: "PROP-00002",
  eligible_ideas: [
    {
      id: 8,
      idea_number: "IDEA-00008",
      title: "Digital delivery",
      owning_workspace_id: 10,
      can_create: true,
      blockers: [],
    },
  ],
  owning_workspaces: [{ id: 10, name: "Enterprise", workspace_type_code: "enterprise" }],
  target_portfolios: [{ id: 20, name: "Capital Portfolio", workspace_type_code: "portfolio" }],
  strategic_objectives: [{ code: "growth", label: "Growth" }],
  users: [{ id: 1, name: "Admin", email: "admin@demo.local" }],
};

const proposal = {
  id: 4,
  proposal_number: "PROP-00001",
  source_idea_id: 8,
  source_idea_number: "IDEA-00008",
  source_idea_title: "Digital delivery",
  accepted_idea_evaluation_id: 5,
  owning_workspace_id: 10,
  owning_workspace_name: "Enterprise",
  target_portfolio_workspace_id: 20,
  name: "Digital delivery platform",
  business_need: "Improve controlled digital delivery.",
  business_justification: "Increase predictability and enterprise visibility.",
  project_objectives: [{ code: "growth", statement: "Growth" }],
  preliminary_scope: "Enterprise delivery platform foundation.",
  out_of_scope: "Final investment decision.",
  expected_benefits: "Faster trusted reporting.",
  benefit_owner_user_id: 1,
  rom_cost: "2400000.00",
  currency_code: "COP",
  preliminary_duration_days: 180,
  target_start_date: "2027-01-15",
  target_finish_date: "2027-07-14",
  key_risks: [{ risk: "Adoption" }],
  assumptions: [{ assumption: "Executive sponsorship" }],
  constraints: [{ constraint: "Strategic gate required" }],
  strategic_objective_codes: ["growth"],
  sponsor_user_id: 1,
  sponsor_name: "Admin",
  proposal_owner_user_id: 1,
  proposal_owner_name: "Admin",
  origin_idea_score: "82.5000",
  status: "EVALUATED",
  mapping_configuration_id: 11,
  mapping_revision: 1,
  mapping_hash: "mapping-hash",
  source_values_snapshot: {},
  mapped_values_snapshot: {},
  review: {
    checks: [
      {
        code: "business_need_complete",
        label: "Business need complete",
        status: "PASS",
        blocking: true,
        evidence: "Complete",
      },
    ],
  },
  attachment_refs: [],
  return_reason: null,
  returned_stage: null,
  evaluations: [
    {
      id: 9,
      evaluation_version: 1,
      matrix_configuration_id: 12,
      matrix_revision: 1,
      matrix_hash: "matrix-hash",
      criteria_snapshot_json: [],
      ratings_json: [],
      total_score: "80.0000",
      recommendation: "PROCEED_TO_GATE",
      comments: "Complete",
      evaluator_user_id: 1,
      created_at: "2026-08-13T10:00:00Z",
    },
  ],
  allowed_actions: ["mark_gate_ready", "return"],
  revision_version: 7,
  created_at: "2026-08-13T10:00:00Z",
  updated_at: "2026-08-13T11:00:00Z",
};

const preview = {
  proposal_number_preview: "PROP-00002",
  source_idea: { id: 8, idea_number: "IDEA-00008", title: "Digital delivery", status: "ACCEPTED" },
  accepted_evaluation: { id: 5, version: 1, score: "82.5000" },
  mapping: { configuration_id: 11, revision: 1, hash: "mapping-hash" },
  mapped_fields: { name: "Digital delivery platform" },
  owning_workspace: { id: 10, name: "Enterprise" },
  target_portfolio: { id: 20, name: "Capital Portfolio" },
  strategic_objectives: [{ code: "growth", label: "Growth" }],
  required_fields: ["name"],
  review_checklist: [],
  policy: { max_active_proposals_per_idea: 1 },
  evaluation_matrix: { configuration_id: 12, revision: 1, criteria: [] },
  blockers: [],
  warnings: [],
  persisted: false,
};

describe("ProjectProposalWorkspace", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        let body: unknown = [proposal];
        if (path.endsWith("/options")) body = options;
        else if (path.includes("/gate-readiness"))
          body = {
            project_proposal_id: 4,
            status: "READY_FOR_STRATEGIC_GATE_DECISION",
            can_enter_strategic_gate: true,
            source_idea_id: 8,
            accepted_idea_evaluation_id: 5,
            proposal_evaluation_id: 9,
            proposal_score: "80.0000",
            owning_workspace_id: 10,
            target_portfolio_workspace_id: 20,
            strategic_objectives: ["growth"],
            sponsor: { id: 1, name: "Admin" },
            proposal_owner: { id: 1, name: "Admin" },
            blockers: [],
            warnings: [],
            readiness_hash: "ready-hash",
          };
        else if (path.includes("/history")) body = [];
        else if (path.endsWith("/preview") && init?.method === "POST") body = preview;
        return { ok: true, status: 200, json: async () => body } as Response;
      })
    );
  });

  it("renders queues, readonly source, review, evaluation and Gate readiness", async () => {
    render(<ProjectProposalWorkspace token="token" />);
    expect(await screen.findByRole("heading", { name: "Project Proposal" })).toBeInTheDocument();
    expect(await screen.findByText("PROP-00001 · Digital delivery platform")).toBeInTheDocument();
    expect(screen.getByText("Source Idea · read only")).toBeInTheDocument();
    expect(screen.getByText("Business Case")).toBeInTheDocument();
    expect(screen.getByText("Review Checklist")).toBeInTheDocument();
    expect(screen.getByText("Proposal Evaluation")).toBeInTheDocument();
    expect(
      await screen.findByText("Eligible for the next controlled strategic gate; this is not approval.")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Mark gate ready/ })).toBeInTheDocument();
  });

  it("previews an accepted Idea without reserving its Proposal number", async () => {
    render(<ProjectProposalWorkspace token="token" />);
    await screen.findByText("PROP-00001 · Digital delivery platform");
    fireEvent.click(screen.getByRole("button", { name: /New Proposal/ }));
    await waitFor(() => expect(screen.getByLabelText("Create Project Proposal")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Preview mapping" }));
    expect(await screen.findByText("Preview only; no number or record has been reserved.")).toBeInTheDocument();
    expect(screen.getByText("PROP-00002")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create DRAFT" })).toBeEnabled();
  });
});
