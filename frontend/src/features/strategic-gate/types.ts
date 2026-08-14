export type StrategicGateState = "DRAFT" | "SUBMITTED" | "IN_REVIEW" | "DECIDED" | "VOIDED";
export type StrategicGateOutcome = "APPROVE" | "RETURN" | "REJECT" | "DEFER";

export type StrategicGateDecision = {
  id: number;
  decision_number: string;
  context_type: string;
  context_id: number;
  project_proposal_id: number;
  project_proposal_number: string;
  project_proposal_name: string;
  gate_type: string;
  gate_round: number;
  state: StrategicGateState;
  outcome: StrategicGateOutcome | null;
  proposal_status_at_entry: string;
  proposal_readiness_status: string;
  proposal_readiness_hash: string;
  proposal_readiness_snapshot: Record<string, unknown>;
  proposal_snapshot: Record<string, unknown>;
  source_idea_snapshot: Record<string, unknown>;
  accepted_idea_evaluation_snapshot: Record<string, unknown>;
  proposal_evaluation_snapshot: Record<string, unknown>;
  source_idea_id: number;
  accepted_idea_evaluation_id: number;
  proposal_evaluation_id: number;
  owning_workspace_id: number;
  owning_workspace_name: string;
  target_portfolio_workspace_id: number | null;
  target_portfolio_name: string | null;
  strategic_objectives_snapshot: Array<Record<string, unknown>>;
  proposal_score: string | null;
  proposal_evaluation_revision: number;
  configuration_id: number;
  configuration_revision: number;
  configuration_hash: string;
  configuration_snapshot: Record<string, unknown>;
  decision_criteria_snapshot: Array<Record<string, unknown>>;
  decision_checklist_snapshot: Array<{
    code: string;
    label: string;
    status: "PASS" | "FAIL" | "WARNING";
    blocking: boolean;
    evidence: string;
  }>;
  conditions: Array<Record<string, unknown>>;
  evidence_refs: Array<Record<string, unknown>>;
  decision_reason: string;
  decision_comments: string;
  decision_maker_user_id: number | null;
  decision_maker_name: string | null;
  committee_snapshot: Record<string, unknown> | null;
  decision_hash: string;
  prepared_by_user_id: number;
  prepared_by_name: string;
  prepared_at: string;
  submitted_at: string | null;
  review_started_at: string | null;
  decided_at: string | null;
  deferred_until: string | null;
  voided_at: string | null;
  allowed_actions: string[];
  revision_version: number;
  created_at: string;
  updated_at: string;
};

export type StrategicGatePreview = {
  decision_number_preview: string;
  project_proposal: Record<string, unknown>;
  source_idea: Record<string, unknown>;
  accepted_idea_evaluation: Record<string, unknown>;
  proposal_evaluation: Record<string, unknown>;
  readiness: Record<string, unknown> & { readiness_hash?: string; status?: string };
  owning_workspace: Record<string, unknown>;
  target_portfolio: Record<string, unknown> | null;
  strategic_objectives: Array<Record<string, unknown>>;
  gate_type: string;
  configuration: Record<string, unknown>;
  decision_checklist: StrategicGateDecision["decision_checklist_snapshot"];
  decision_criteria: Array<Record<string, unknown>>;
  authority: Record<string, unknown>;
  committee_policy: Record<string, unknown>;
  blockers: string[];
  warnings: string[];
  persisted: boolean;
};

export type StrategicGateOptions = {
  decision_number_preview: string;
  eligible_proposals: Array<{
    id: number;
    proposal_number: string;
    name: string;
    owning_workspace_id: number;
    target_portfolio_workspace_id: number | null;
    can_create: boolean;
    blockers: string[];
  }>;
  users: Array<{ id: number; name: string; email: string }>;
  gate_types: string[];
};

export type PortfolioIntakeReadiness = {
  status: string;
  can_create_portfolio_candidate: false;
  strategic_gate_decision_id: number;
  decision_number: string;
  outcome: string | null;
  project_proposal_id: number;
  project_proposal_number: string;
  source_idea_id: number;
  decision_hash: string;
  readiness_hash: string;
  blockers: string[];
  warnings: string[];
};

export type StrategicGateDraft = {
  decision_reason: string;
  decision_comments: string;
  decision_maker_user_id: number | null;
  conditions: Array<Record<string, unknown>>;
  evidence_refs: Array<Record<string, unknown>>;
  committee: Record<string, unknown> | null;
};
