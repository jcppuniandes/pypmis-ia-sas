export type BusinessAnalysisState =
  | "DRAFT"
  | "SUBMITTED"
  | "IN_REVIEW"
  | "RETURNED"
  | "COMPLETED"
  | "SUPERSEDED"
  | "VOIDED";

export type BusinessAnalysisOption = {
  id: string;
  name: string;
  option_type: string;
  description: string;
  scope_concept: string;
  expected_benefits: string;
  rough_cost_range: Record<string, unknown> | null;
  rough_timeline: Record<string, unknown> | null;
  major_risks: Array<Record<string, unknown>>;
  major_dependencies: Array<Record<string, unknown>>;
  feasibility_notes: string;
  strategic_fit: string;
  evaluation: Array<Record<string, unknown>>;
};

export type BusinessAnalysisContent = {
  analysis_type: string;
  statement: string;
  background: string;
  business_context: string;
  urgency_timing: string;
  consequences_no_action: string;
  business_drivers: Array<Record<string, unknown>>;
  strategic_alignment: Array<Record<string, unknown>>;
  stakeholders: Array<Record<string, unknown>>;
  current_state: Record<string, unknown>;
  desired_outcomes: Record<string, unknown>;
  expected_value: Array<Record<string, unknown>>;
  assumptions: Array<Record<string, unknown>>;
  constraints: Array<Record<string, unknown>>;
  business_requirements: Array<Record<string, unknown>>;
  options: BusinessAnalysisOption[];
  recommended_option_id: string | null;
  recommendation_rationale: string;
  key_trade_offs: Array<Record<string, unknown>>;
  conditions: Array<Record<string, unknown>>;
  unresolved_concerns: Array<Record<string, unknown>>;
};

export type BusinessAnalysis = {
  id: number;
  analysis_number: string;
  source_idea_id: number;
  source_idea_number: string;
  source_idea_title: string;
  source_idea_evaluation_id: number;
  owning_workspace_id: number;
  owning_workspace_name: string;
  supersedes_analysis_id: number | null;
  status: BusinessAnalysisState;
  title: string;
  content: BusinessAnalysisContent;
  recommended_option_id: string | null;
  readiness: Record<string, unknown>;
  source_idea_hash: string;
  configuration_id: number;
  configuration_revision: number;
  configuration_hash: string;
  review: Record<string, unknown>;
  completion_hash: string;
  revision_version: number;
  created_by_user_id: number;
  reviewer_user_id: number | null;
  allowed_actions: string[];
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  review_started_at: string | null;
  completed_at: string | null;
};

export type BusinessAnalysisOptions = {
  number_preview: string;
  eligible_ideas: Array<{
    id: number;
    idea_number: string;
    title: string;
    owning_workspace_id: number;
    can_start: boolean;
    blockers: string[];
    governance_model: string;
    business_analysis_required: boolean;
  }>;
  analysis_types: Array<{ code: string; label: string }>;
  business_drivers: Array<{ code: string; label: string }>;
  strategic_objectives: Array<{ code: string; label: string }>;
  option_types: Array<{ code: string; label: string }>;
  evaluation_criteria: Array<{ code: string; label: string; weight: number }>;
  stakeholder_categories: Array<{ code: string; label: string }>;
  value_dimensions: Array<{ code: string; label: string }>;
};

export type BusinessAnalysisReadiness = {
  business_analysis_id: number;
  status: "READY" | "BLOCKED" | "STALE";
  ready: boolean;
  output: string | null;
  blockers: string[];
  warnings: string[];
  source_idea_hash: string;
  current_source_idea_hash: string;
  configuration_hash: string;
  readiness_hash: string;
};
