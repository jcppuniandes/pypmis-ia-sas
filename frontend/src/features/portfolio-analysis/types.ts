export type MetricDefinition = {
  metric_key: string;
  label: string;
  category: string;
  data_type: "NUMBER" | "DATE" | "CATEGORY" | "TEXT" | "SCORE";
  allowed_for_x_axis: boolean;
  allowed_for_y_axis: boolean;
  allowed_for_size: boolean;
  allowed_for_color: boolean;
  allowed_for_filter: boolean;
  allowed_for_scorecard: boolean;
  aggregation_support: string[];
  formatting: string;
  null_behavior: string;
  non_negative: boolean;
  currency_sensitive: boolean;
};

export type PortfolioAnalysisRow = {
  portfolio_workspace_id: number;
  project_workspace_id: number;
  portfolio_membership_id: number;
  project_number: string;
  project_name: string;
  project_type: string | null;
  governance_model: string;
  workspace_status: string;
  planning_stage: string | null;
  strategic_objectives: Array<Record<string, unknown>>;
  proposal_score: string | null;
  portfolio_evaluation_score: string;
  portfolio_rank: number;
  strategic_alignment_score: string;
  risk_score: string;
  risk_bucket: string;
  priority_bucket: string;
  rom_cost: string | null;
  currency: string | null;
  target_start: string | null;
  target_finish: string | null;
  planned_duration_days: number | null;
  expected_benefits: string | null;
  risk_summary: Array<Record<string, unknown>>;
  sponsor: string | null;
  project_manager: string | null;
  membership_source: string;
  evaluation_id: number;
  evaluation_version: number;
  evaluation_date: string;
  planning_entry_hash: string;
  evaluation_hash: string;
  prioritization_hash: string;
};

export type PortfolioAnalysisDataset = {
  portfolio_workspace_id: number;
  generated_at: string;
  metric_catalog: MetricDefinition[];
  rows: PortfolioAnalysisRow[];
  filters_applied: Record<string, unknown>;
  source_prioritization_hash: string;
  membership_set_hash: string;
  evaluation_set_hash: string;
  configuration_hash: string;
  analysis_hash: string;
  warnings: string[];
  blockers: string[];
};

export type InvestorMapPoint = {
  project_workspace_id: number;
  project_number: string;
  project_name: string;
  portfolio_rank: number;
  x: number | string | null;
  y: number | string | null;
  bubble_size: string;
  bubble_size_source: number | string | null;
  color: string;
  tooltip: Record<string, unknown>;
};

export type InvestorMap = {
  portfolio_workspace_id: number;
  x_metric: string;
  y_metric: string;
  size_metric: string | null;
  color_metric: string;
  size_metric_applied: boolean;
  reference_lines: Array<{ axis: "x" | "y"; value: number; label: string }>;
  points: InvestorMapPoint[];
  analysis_hash: string;
  warnings: string[];
};

export type PortfolioScorecard = {
  portfolio_workspace_id: number;
  columns: string[];
  default_sort: Array<{ metric_key: string; direction: "asc" | "desc" }>;
  rows: Array<Record<string, unknown>>;
  analysis_hash: string;
  warnings: string[];
};

export type AnalysisSummary = {
  eligible_projects: number;
  evaluated_projects: number;
  average_portfolio_score: string | null;
  high_priority_count: number;
  high_risk_count: number;
  rom_cost_coverage_percent: string;
  rom_cost_total: string | null;
  rom_cost_currency: string | null;
  distributions: Record<string, Array<{ key: string; count: number; overlap_possible?: boolean }>>;
};

export type AnalysisReadiness = {
  portfolio_workspace_id: number;
  status: "READY" | "BLOCKED";
  analysis_hash: string;
  source_prioritization_hash: string;
  membership_set_hash: string;
  evaluation_set_hash: string;
  configuration_hash: string;
  eligible_project_count: number;
  metric_coverage: Record<string, string>;
  warnings: string[];
  blockers: string[];
  allowed_actions: string[];
  can_enter_budget_planning: boolean;
  can_enter_resource_planning: boolean;
  can_enter_portfolio_scenario_planning: boolean;
  final_output: "READY_FOR_PORTFOLIO_SCENARIO_PLANNING" | "GATE07F_REWORK_REQUIRED";
};

export type PortfolioAnalysisOverview = {
  dataset: PortfolioAnalysisDataset;
  investor_map: InvestorMap;
  scorecard: PortfolioScorecard;
  summary: AnalysisSummary;
  readiness: AnalysisReadiness;
};

export type AnalysisFilters = {
  project_type?: string;
  strategic_objective?: string;
  risk_bucket?: string;
  priority_bucket?: string;
};

export type AnalysisConfiguration = {
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

export type ProjectAnalysisDetail = {
  row: PortfolioAnalysisRow;
  evaluation_history: Array<Record<string, unknown>>;
  strategic_context: Record<string, unknown>;
  membership: Record<string, unknown>;
  planning_entry: Record<string, unknown>;
};
