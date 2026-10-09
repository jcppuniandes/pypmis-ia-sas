export type IdeaState =
  | "DRAFT"
  | "SUBMITTED"
  | "SCREENING"
  | "RETURNED"
  | "OWNER_ASSIGNED"
  | "UNDER_EVALUATION"
  | "EVALUATED"
  | "ACCEPTED"
  | "REJECTED"
  | "CANCELLED"
  | "ARCHIVED";

export type IdeaEvaluation = {
  id: number;
  evaluation_version: number;
  matrix_configuration_id: number;
  matrix_revision: number;
  matrix_snapshot_json: { criteria?: Array<{ code: string; label: string; weight: number }> };
  ratings_json: Array<{ criterion_code: string; rating: number; weight: number; comment?: string }>;
  total_score: string;
  result: string;
  comments: string;
  evaluator_user_id: number;
  created_at: string;
};

export type Idea = {
  id: number;
  idea_number: string;
  title: string;
  description: string;
  idea_type: string;
  category: string;
  expected_benefit: string;
  estimated_value: string | null;
  currency_code: string;
  owning_workspace_id: number;
  owning_workspace_name: string;
  target_portfolio_workspace_id: number | null;
  strategic_objective_codes: string[];
  requestor_user_id: number;
  requestor_name: string;
  owner_user_id: number | null;
  owner_name: string | null;
  state: IdeaState;
  screening: { checklist?: Record<string, boolean>; notes?: string };
  routing: Record<string, unknown>;
  attachment_refs: Array<Record<string, unknown>>;
  accepted_evaluation_id: number | null;
  decision_reason: string | null;
  readiness: Record<string, unknown>;
  evaluations: IdeaEvaluation[];
  allowed_actions: string[];
  revision_version: number;
  created_at: string;
  updated_at: string;
};

export type IdeaOptions = {
  number_preview: string;
  owning_workspaces: Array<Record<string, string | number>>;
  target_portfolios: Array<Record<string, string | number>>;
  strategic_objectives: Array<{ code: string; label: string }>;
  users: Array<{ id: number; name: string; email: string }>;
  idea_types: Array<{ code: string; label: string }>;
  categories: Array<{ code: string; label: string }>;
  screening_checklist: Array<{ code: string; label: string; blocking: boolean }>;
  objective_selection: string;
  configuration_source: Record<string, unknown>;
};

export type IdeaDraft = {
  title: string;
  description: string;
  idea_type: string;
  category: string;
  expected_benefit: string;
  estimated_value: string;
  currency_code: string;
  owning_workspace_id: number;
  target_portfolio_workspace_id: number | null;
  strategic_objective_codes: string[];
  attachment_refs: Array<Record<string, unknown>>;
};
