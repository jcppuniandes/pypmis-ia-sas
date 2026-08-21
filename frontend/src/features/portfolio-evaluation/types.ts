export type CriterionRating = {
  criterion_code: string;
  rating: number;
  evidence: string;
  comment: string;
};

export type PortfolioEvaluation = {
  id: number;
  tenant_id: number;
  portfolio_workspace_id: number;
  portfolio_name: string;
  project_workspace_id: number;
  project_number: string;
  project_name: string;
  portfolio_membership_id: number;
  evaluation_version: number;
  status: "DRAFT" | "IN_PROGRESS" | "COMPLETED" | "SUPERSEDED" | "VOIDED";
  matrix_configuration_id: number;
  matrix_revision: number;
  matrix_hash: string;
  matrix_snapshot: {
    criteria?: Array<{ code: string; label: string; weight: number; evidence_required: boolean }>;
    scoring_scale?: { minimum: number; maximum: number; step: number };
    ranking_rules?: Record<string, unknown>;
    [key: string]: unknown;
  };
  source_snapshot: Record<string, unknown>;
  source_snapshot_hash: string;
  planning_entry_hash: string;
  ratings: CriterionRating[];
  score_components: Array<Record<string, unknown>>;
  normalized_score: string;
  strategic_alignment_score: string;
  risk_score: string;
  comments: string;
  evaluator_user_id: number;
  revision_version: number;
  started_at: string;
  completed_at: string | null;
  allowed_actions: string[];
  blocking_issues: string[];
};

export type EvaluationQueueItem = {
  portfolio_workspace_id: number;
  project_workspace_id: number;
  project_number: string;
  project_name: string;
  membership_id: number;
  queue: "TO_EVALUATE" | "IN_PROGRESS" | "COMPLETED" | "BLOCKED";
  eligible: boolean;
  blocking_issues: string[];
  allowed_actions: string[];
  latest_evaluation: PortfolioEvaluation | null;
};

export type PrioritizationItem = {
  rank: number;
  portfolio_workspace_id: number;
  project_workspace_id: number;
  project_number: string;
  project_name: string;
  evaluation_id: number;
  evaluation_version: number;
  normalized_score: string;
  strategic_alignment_score: string;
  risk_score: string;
  proposal_score: string | null;
  strategic_objectives: Array<Record<string, unknown>>;
  rom_cost: string | null;
  evaluation_status: string;
  completed_at: string;
  planned_finish: string | null;
};

export type Prioritization = {
  portfolio_workspace_id: number;
  generated_at: string;
  ranking_rules: Record<string, unknown>;
  matrix_hash: string;
  items: PrioritizationItem[];
};

export type PrioritizationReadiness = {
  portfolio_workspace_id: number;
  status: "READY" | "BLOCKED";
  eligible_project_count: number;
  completed_evaluation_count: number;
  in_progress_evaluation_count: number;
  blocked_project_count: number;
  coverage_percent: string;
  blocking_issues: string[];
  readiness_hash: string;
  can_enter_portfolio_analysis: boolean;
  final_output: "READY_FOR_PORTFOLIO_ANALYSIS" | "GATE07E_REWORK_REQUIRED";
};

export type EvaluationConfiguration = {
  id: number;
  kind: string;
  code: string;
  name: string;
  description: string;
  status: "draft" | "published";
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash: string;
};
