export type ResourcePeriod = {
  id: number;
  resource_role_key: string;
  resource_role_name: string;
  role_category: string;
  period_key: string;
  period_start: string;
  period_end: string;
  unit: "FTE" | "HOURS" | "CREW_EQUIVALENT";
  capacity_value?: string;
  demand_value?: string;
  source_reference: string;
  notes: string;
};

export type CapacityPlan = {
  id: number;
  portfolio_workspace_id: number;
  logical_code: string;
  plan_name: string;
  planning_horizon_start: string;
  planning_horizon_end: string;
  period_granularity: "YEAR" | "QUARTER" | "MONTH";
  status: "DRAFT" | "PUBLISHED" | "SUPERSEDED";
  plan_revision: number;
  source_reference: string;
  notes: string;
  capacity_hash: string;
  revision_version: number;
  periods: ResourcePeriod[];
};

export type DemandProfile = {
  id: number;
  project_workspace_id: number;
  logical_code: string;
  profile_name: string;
  status: "DRAFT" | "PUBLISHED" | "SUPERSEDED";
  profile_revision: number;
  source_type: string;
  source_reference: string;
  source_hash: string;
  as_of_date: string;
  planning_start: string;
  planning_finish: string;
  generation_method: string;
  approximation: boolean;
  demand_hash: string;
  revision_version: number;
  periods: ResourcePeriod[];
};

export type ResourceScenarioProject = {
  id: number;
  project_workspace_id: number;
  project_number: string;
  project_name: string;
  portfolio_evaluation_score: string;
  portfolio_rank: number;
  strategic_alignment_score: string;
  risk_score: string;
  risk_bucket: string;
  resource_demand_profile_id: number | null;
  source_project_start: string | null;
  source_project_finish: string | null;
  scenario_start: string | null;
  scenario_finish: string | null;
  schedule_shift_days: number;
  timing_method: "NO_SHIFT" | "SHIFT_START_KEEP_DURATION" | "CUSTOM_SCENARIO_DATES";
  selection_state: "SELECTED" | "UNSELECTED" | "FORCED_IN" | "FORCED_OUT";
  forced_reason: string | null;
  demand_covered: boolean;
  revision_version: number;
};

export type CapacityDemandCell = {
  resource_role_key: string;
  resource_role_name: string;
  role_category: string;
  period_key: string;
  period_start: string;
  period_end: string;
  unit: string;
  capacity: string;
  selected_demand: string;
  variance: string;
  utilization_percent: string | null;
  status: "AVAILABLE" | "AT_CAPACITY" | "OVERLOADED" | "NO_CAPACITY";
};

export type ResourceScenario = {
  id: number;
  portfolio_workspace_id: number;
  logical_code: string;
  scenario_name: string;
  description: string;
  status: "DRAFT" | "IN_REVIEW" | "FROZEN" | "SUPERSEDED" | "VOIDED";
  capacity_plan_id: number;
  capacity_plan_hash: string;
  source_analysis_hash: string;
  source_hash: string;
  scenario_hash: string;
  creation_mode: string;
  overload_policy: string;
  scenario_revision: number;
  revision_version: number;
  projects: ResourceScenarioProject[];
  heatmap: CapacityDemandCell[];
  summary: {
    selected_count: number;
    unselected_count: number;
    forced_in_count: number;
    forced_out_count: number;
    average_score: string | null;
    high_risk_count: number;
    overloaded_role_count: number;
    overloaded_period_count: number;
    peak_overload: string;
    peak_utilization: string | null;
    average_utilization: string | null;
    demand_coverage_percent: string;
  };
  readiness: {
    status: "READY" | "BLOCKED" | "STALE";
    source_current: boolean;
    demand_coverage_percent: string;
    warnings: string[];
    blockers: string[];
  };
  warnings: string[];
  blockers: string[];
  allowed_actions: string[];
};

export type ResourcePlanningOverview = {
  portfolio_workspace_id: number;
  gate07f: {
    final_output: string;
    analysis_hash: string;
    can_enter_budget_planning: boolean;
    can_enter_resource_planning: boolean;
    warnings: string[];
    blockers: string[];
  };
  active_capacity_plan: CapacityPlan | null;
  capacity_plans: CapacityPlan[];
  demand_profiles: DemandProfile[];
  scenarios: ResourceScenario[];
  readiness: {
    scenario_count: number;
    frozen_scenario_count: number;
    ready_scenario_count: number;
    demand_coverage: string;
    overloaded_scenario_count: number;
    warnings: string[];
    blockers: string[];
    resource_planning_hash: string;
    can_enter_resource_recommendation: boolean;
    allowed_actions: string[];
    final_output: string;
  };
  allowed_actions: string[];
  boundaries: string[];
};

export type ResourceScenarioComparison = {
  portfolio_workspace_id: number;
  scenarios: Array<Record<string, unknown>>;
  project_matrix: Array<Record<string, string | number | boolean | null>>;
  pairwise_delta: Record<string, unknown>;
  role_demand_delta: Array<Record<string, unknown>>;
  warnings: string[];
};

export type ResourceConfiguration = {
  id: number;
  code: string;
  name: string;
  description: string;
  status: "draft" | "published" | "superseded";
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash: string;
};
