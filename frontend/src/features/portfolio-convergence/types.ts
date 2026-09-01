export type ConvergedAlternative = {
  id: number;
  convergence_id: number;
  alternative_name: string;
  budget_scenario_id: number | null;
  resource_scenario_id: number | null;
  alignment_status: "ALIGNED" | "PARTIALLY_ALIGNED" | "MISALIGNED";
  budget_feasibility: string;
  resource_feasibility: string;
  feasibility_status: "FEASIBLE" | "CONDITIONAL" | "INFEASIBLE" | "BLOCKED" | "STALE";
  budget_summary: Record<string, unknown>;
  resource_summary: Record<string, unknown>;
  strategic_summary: Record<string, unknown>;
  risk_summary: Record<string, unknown>;
  project_matrix: Array<Record<string, unknown>>;
  forced_conflicts: Array<Record<string, unknown>>;
  warnings: string[];
  blockers: string[];
  alternative_hash: string;
  revision_version: number;
};

export type ScenarioConvergence = {
  id: number;
  portfolio_workspace_id: number;
  convergence_revision: number;
  name: string;
  description: string;
  status: "DRAFT" | "IN_REVIEW" | "RECOMMENDED" | "SUPERSEDED" | "VOIDED";
  required_budget_branch: boolean;
  required_resource_branch: boolean;
  source_analysis_hash: string;
  convergence_source_hash: string;
  source_current: boolean;
  recommended_alternative_id: number | null;
  recommendation_reason: string | null;
  conditions: string[];
  risks_acknowledged: string[];
  decision_support_summary: string | null;
  recommendation_hash: string | null;
  recommended_at: string | null;
  warnings: string[];
  blockers: string[];
  revision_version: number;
  alternatives: ConvergedAlternative[];
  allowed_actions: string[];
};

export type RecommendationReadiness = {
  portfolio_workspace_id: number;
  convergence_id: number | null;
  convergence_revision: number | null;
  status: string;
  alternative_count: number;
  recommended_alternative_id: number | null;
  source_current: boolean;
  warnings: string[];
  blockers: string[];
  recommendation_hash: string | null;
  portfolio_recommendation_ready: boolean;
  can_enter_investment_gate_preparation: boolean;
  can_enter_fid: false;
  allowed_actions: string[];
  final_output: string;
};

export type ConvergenceOverview = {
  portfolio_workspace_id: number;
  required_branches: { budget: boolean; resource: boolean };
  budget_contract: Record<string, unknown> | null;
  resource_contract: Record<string, unknown> | null;
  source_compatibility: Record<string, unknown>;
  candidate_budget_scenarios: Array<Record<string, unknown>>;
  candidate_resource_scenarios: Array<Record<string, unknown>>;
  convergences: ScenarioConvergence[];
  readiness: RecommendationReadiness;
  boundaries: string[];
};

export type ConvergenceComparison = {
  convergence_id: number;
  alternatives: Array<Record<string, unknown>>;
  feasibility_matrix: Array<Record<string, unknown>>;
  project_matrix: Array<Record<string, unknown>>;
  pairwise_delta: Record<string, unknown>;
  warnings: string[];
};

export type ConvergenceConfiguration = {
  id: number;
  name: string;
  description: string;
  status: string;
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash: string;
};
