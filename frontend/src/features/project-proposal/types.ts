export type ProjectProposalState =
  | "DRAFT"
  | "SUBMITTED"
  | "UNDER_REVIEW"
  | "RETURNED"
  | "UNDER_EVALUATION"
  | "EVALUATED"
  | "READY_FOR_STRATEGIC_GATE_DECISION"
  | "CANCELLED"
  | "ARCHIVED";

export type ProjectProposalEvaluation = {
  id: number;
  evaluation_version: number;
  matrix_configuration_id: number;
  matrix_revision: number;
  matrix_hash: string;
  criteria_snapshot_json: Array<{ code: string; label: string; weight: number }>;
  ratings_json: Array<Record<string, unknown>>;
  total_score: string;
  recommendation: string;
  comments: string;
  evaluator_user_id: number;
  created_at: string;
};

export type ProjectProposal = {
  id: number;
  proposal_number: string;
  source_idea_id: number;
  source_idea_number: string;
  source_idea_title: string;
  accepted_idea_evaluation_id: number;
  owning_workspace_id: number;
  owning_workspace_name: string;
  target_portfolio_workspace_id: number | null;
  name: string;
  business_need: string;
  business_justification: string;
  project_objectives: Array<Record<string, unknown>>;
  preliminary_scope: string;
  out_of_scope: string;
  expected_benefits: string;
  benefit_owner_user_id: number | null;
  rom_cost: string | null;
  currency_code: string;
  preliminary_duration_days: number | null;
  target_start_date: string | null;
  target_finish_date: string | null;
  key_risks: Array<Record<string, unknown>>;
  assumptions: Array<Record<string, unknown>>;
  constraints: Array<Record<string, unknown>>;
  strategic_objective_codes: string[];
  sponsor_user_id: number;
  sponsor_name: string;
  proposal_owner_user_id: number;
  proposal_owner_name: string;
  origin_idea_score: string | null;
  status: ProjectProposalState;
  mapping_configuration_id: number;
  mapping_revision: number;
  mapping_hash: string;
  source_values_snapshot: Record<string, unknown>;
  mapped_values_snapshot: Record<string, unknown>;
  review: {
    checks?: Array<{
      code: string;
      label: string;
      status: "PASS" | "FAIL" | "WARNING";
      blocking: boolean;
      evidence: string;
    }>;
  };
  attachment_refs: Array<Record<string, unknown>>;
  return_reason: string | null;
  returned_stage: string | null;
  evaluations: ProjectProposalEvaluation[];
  allowed_actions: string[];
  revision_version: number;
  created_at: string;
  updated_at: string;
};

export type ProposalPreview = {
  proposal_number_preview: string;
  source_idea: Record<string, unknown>;
  accepted_evaluation: Record<string, unknown>;
  mapping: Record<string, unknown>;
  mapped_fields: Record<string, unknown>;
  owning_workspace: Record<string, unknown>;
  target_portfolio: Record<string, unknown> | null;
  strategic_objectives: Array<{ code: string; label: string }>;
  required_fields: string[];
  review_checklist: Array<Record<string, unknown>>;
  policy: Record<string, unknown>;
  evaluation_matrix: {
    configuration_id: number;
    revision: number;
    criteria: Array<{ code: string; label: string; weight: number }>;
  };
  blockers: string[];
  warnings: string[];
  persisted: boolean;
};

export type ProposalOptions = {
  number_preview: string;
  eligible_ideas: Array<{
    id: number;
    idea_number: string;
    title: string;
    owning_workspace_id: number;
    can_create: boolean;
    blockers: string[];
  }>;
  owning_workspaces: Array<Record<string, string | number>>;
  target_portfolios: Array<Record<string, string | number>>;
  strategic_objectives: Array<{ code: string; label: string }>;
  users: Array<{ id: number; name: string; email: string }>;
};

export type GateReadiness = {
  project_proposal_id: number;
  status: string;
  can_enter_strategic_gate: boolean;
  source_idea_id: number;
  accepted_idea_evaluation_id: number;
  proposal_evaluation_id: number | null;
  proposal_score: string | null;
  owning_workspace_id: number;
  target_portfolio_workspace_id: number | null;
  strategic_objectives: string[];
  sponsor: Record<string, unknown>;
  proposal_owner: Record<string, unknown>;
  blockers: string[];
  warnings: string[];
  readiness_hash: string;
};

export type ProposalDraft = {
  name: string;
  business_need: string;
  business_justification: string;
  project_objectives: Array<Record<string, unknown>>;
  preliminary_scope: string;
  out_of_scope: string;
  expected_benefits: string;
  benefit_owner_user_id: number | null;
  rom_cost: string | null;
  currency_code: string;
  preliminary_duration_days: number | null;
  target_start_date: string | null;
  target_finish_date: string | null;
  key_risks: Array<Record<string, unknown>>;
  assumptions: Array<Record<string, unknown>>;
  constraints: Array<Record<string, unknown>>;
  strategic_objective_codes: string[];
  target_portfolio_workspace_id: number | null;
  sponsor_user_id: number;
  proposal_owner_user_id: number;
  attachment_refs: Array<Record<string, unknown>>;
};
