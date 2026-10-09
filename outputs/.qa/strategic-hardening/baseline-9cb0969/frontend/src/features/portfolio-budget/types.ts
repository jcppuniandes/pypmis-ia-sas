export type BudgetTargetPeriod = {
  id: number;
  period_key: string;
  period_start: string;
  period_end: string;
  amount: string;
  capex_amount: string | null;
  expense_amount: string | null;
};

export type BudgetTarget = {
  id: number;
  portfolio_workspace_id: number;
  target_code: string;
  target_revision: number;
  planning_horizon_start: string;
  planning_horizon_end: string;
  period_granularity: "YEAR" | "QUARTER" | "MONTH";
  budget_currency: string;
  total_budget_target: string;
  capex_budget_target: string | null;
  expense_budget_target: string | null;
  unallocated_budget_target: string;
  periods: BudgetTargetPeriod[];
  source_reference: string;
  notes: string;
  status: "DRAFT" | "PUBLISHED" | "SUPERSEDED";
  target_hash: string;
  revision_version: number;
};

export type ScenarioProject = {
  id: number;
  project_workspace_id: number;
  project_number: string;
  project_name: string;
  portfolio_evaluation_score: string;
  portfolio_rank: number;
  strategic_alignment_score: string;
  risk_score: string;
  risk_bucket: string;
  cost_value: string;
  capex_amount: string | null;
  expense_amount: string | null;
  unclassified_amount: string;
  budget_breakdown_source: string;
  currency: string;
  target_start: string | null;
  target_finish: string | null;
  strategic_objectives: Array<Record<string, unknown>>;
  selection_state: "SELECTED" | "UNSELECTED" | "FORCED_IN" | "FORCED_OUT";
  forced_reason: string | null;
  warnings: string[];
  dependency_status: string;
  unmet_dependency_count: number;
  dependency_details: Array<Record<string, unknown>>;
};

export type BudgetScenario = {
  id: number;
  portfolio_workspace_id: number;
  logical_code: string;
  scenario_name: string;
  scenario_code: string | null;
  description: string;
  status: "DRAFT" | "IN_REVIEW" | "FROZEN" | "SUPERSEDED" | "VOIDED";
  analytical_status: "WITHIN_BUDGET" | "OVER_BUDGET" | "UNDER_BUDGET";
  budget_target_id: number;
  source_analysis_hash: string;
  source_hash: string;
  scenario_hash: string;
  creation_mode: "EMPTY" | "FROM_CURRENT_PRIORITY" | "COPY_EXISTING_SCENARIO";
  time_phasing_method: "UNPHASED" | "LINEAR_BY_PROJECT_DATES" | "CUSTOM_PERIOD_PROFILE";
  scenario_revision: number;
  revision_version: number;
  projects: ScenarioProject[];
  summary: {
    selected_demand: string;
    target_budget: string;
    variance: string;
    utilization_percent: string;
    selected_count: number;
    unselected_count: number;
    forced_in_count: number;
    forced_out_count: number;
    average_evaluation_score: string | null;
    average_strategic_alignment: string | null;
    high_risk_count: number;
    analytical_status: string;
    selected_capex: string;
    selected_expense: string;
    selected_unclassified: string;
    capex_target: string | null;
    expense_target: string | null;
    unallocated_target: string;
    capex_variance: string | null;
    expense_variance: string | null;
    mandatory_dependency_count: number;
    unmet_mandatory_count: number;
    optional_dependency_warning_count: number;
    forced_dependency_conflict_count: number;
  };
  period_view: Array<{
    period_key: string;
    target: string | null;
    selected_demand: string;
    variance: string | null;
    approximation: boolean;
    capex_demand: string;
    expense_demand: string;
    unclassified_demand: string;
    capex_target: string | null;
    expense_target: string | null;
    capex_variance: string | null;
    expense_variance: string | null;
  }>;
  strategic_balance: Record<string, unknown>;
  readiness: { status: "READY" | "BLOCKED" | "STALE"; source_current: boolean; warnings: string[]; blockers: string[] };
  warnings: string[];
  blockers: string[];
  allowed_actions: string[];
  dependency_summary: Record<string, unknown>;
};

export type Waterline = {
  scenario_id: number;
  period_key: string;
  rank_source: string;
  target_budget: string;
  selected_demand: string;
  variance: string;
  analytical_status: string;
  alignment_status: string;
  waterline_position: number | null;
  projects: Array<{
    project_workspace_id: number;
    project_number: string;
    project_name: string;
    portfolio_rank: number;
    selection_state: ScenarioProject["selection_state"];
    budget_demand: string;
    cumulative_selected_demand: string;
    target_budget: string;
    waterline_side: string;
    forced_state: string | null;
    dependency_status: string;
    unmet_dependency_count: number;
    capex_amount: string | null;
    expense_amount: string | null;
    unclassified_amount: string;
    project_type: string;
    risk_bucket: string;
    strategic_objectives: Array<Record<string, unknown>>;
  }>;
  budget_breakdown: Record<string, string>;
  dependency_summary: Record<string, unknown>;
  allowed_actions: string[];
};

export type ProjectDependency = {
  id: number;
  predecessor_project_workspace_id: number;
  predecessor_project_number: string;
  predecessor_project_name: string;
  successor_project_workspace_id: number;
  successor_project_number: string;
  successor_project_name: string;
  dependency_type: string;
  dependency_strength: "MANDATORY" | "OPTIONAL";
  description: string;
  effective_from: string | null;
  effective_to: string | null;
  status: "ACTIVE" | "INACTIVE";
  source_reference: string | null;
  evidence_refs: Array<Record<string, unknown>>;
  revision_version: number;
};

export type BudgetPlanningOverview = {
  portfolio_workspace_id: number;
  gate07f: {
    final_output: string;
    analysis_hash: string;
    can_enter_budget_planning: boolean;
    can_enter_resource_planning: boolean;
    warnings: string[];
    blockers: string[];
  };
  active_target: BudgetTarget | null;
  targets: BudgetTarget[];
  scenarios: BudgetScenario[];
  readiness: {
    scenario_count: number;
    frozen_scenario_count: number;
    ready_scenario_count: number;
    budget_target_id: number | null;
    warnings: string[];
    blockers: string[];
    budget_planning_hash: string;
    can_enter_budget_recommendation: boolean;
    allowed_actions: string[];
    final_output: string;
  };
  allowed_actions: string[];
  boundaries: string[];
};

export type ScenarioComparison = {
  portfolio_workspace_id: number;
  scenarios: Array<Record<string, unknown>>;
  project_matrix: Array<Record<string, string | number>>;
  pairwise_delta: Record<string, unknown>;
  warnings: string[];
};

export type BudgetConfiguration = {
  id: number;
  code: string;
  name: string;
  description: string;
  status: "draft" | "published";
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash: string;
};
