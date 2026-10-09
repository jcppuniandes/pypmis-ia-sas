export type StrategicAllocationBasis = "PERCENTAGE" | "INDICATIVE_AMOUNT" | "PERCENTAGE_AND_AMOUNT";

export type StrategicAllocationScope = "ENTERPRISE" | "BUSINESS_UNIT" | "PORTFOLIO";

export type StrategicAllocationPlanStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "IN_REVIEW"
  | "RETURNED"
  | "ENDORSED"
  | "SUPERSEDED"
  | "CANCELLED";

export type StrategicCapitalBucket = {
  bucket_code: string;
  bucket_name: string;
  description?: string;
  strategic_purpose?: string;
  active?: boolean;
  display_order?: number;
};

export type StrategicAllocationLine = {
  id?: number;
  bucket_code: string;
  bucket_name?: string;
  target_percentage: string | number | null;
  target_amount: string | number | null;
  minimum_percentage: string | number | null;
  maximum_percentage: string | number | null;
  minimum_amount: string | number | null;
  maximum_amount: string | number | null;
  currency: string | null;
  rationale: string;
  strategic_objective_codes: string[];
  assumptions: string[];
  constraints: string[];
  priority_note?: string | null;
  line_hash?: string;
};

export type StrategicAllocationReadiness = {
  overall?: string;
  ready?: boolean;
  blockers?: string[];
  warnings?: string[];
  dimensions?: Record<string, string | boolean | number>;
  classification_coverage_percentage?: string | number | null;
};

export type StrategicAllocationPlan = {
  id: number;
  allocation_plan_id?: number;
  allocation_plan_number: string;
  name: string;
  description?: string;
  planning_cycle_id: number;
  planning_cycle_number?: string;
  planning_cycle_name?: string;
  scope_type: StrategicAllocationScope;
  scope_workspace_id: number;
  scope_workspace_name?: string | null;
  portfolio_id: number | null;
  portfolio_workspace_id?: number | null;
  portfolio_name?: string | null;
  portfolio_workspace_name?: string | null;
  base_currency: string | null;
  allocation_basis: StrategicAllocationBasis;
  status: StrategicAllocationPlanStatus;
  revision_version: number;
  plan_revision?: number;
  version?: number;
  configuration_revision?: number | null;
  configuration_hash?: string | null;
  source_current?: boolean;
  staleness_status?: string;
  lines: StrategicAllocationLine[];
  readiness?: StrategicAllocationReadiness;
  allowed_actions: string[];
  created_by?: number | string;
  created_at?: string;
  updated_at?: string;
  endorsed_at?: string | null;
};

export type StrategicAllocationPlanDraft = {
  name: string;
  description: string;
  planning_cycle_id: number;
  scope_type: StrategicAllocationScope;
  scope_workspace_id: number | null;
  portfolio_id: number | null;
  base_currency: string | null;
  allocation_basis: StrategicAllocationBasis;
  assumptions?: string[];
  constraints?: string[];
};

export type StrategicBucketClassification = {
  id?: number;
  demand_id?: number | null;
  demand_number?: string | null;
  demand_name?: string | null;
  project_workspace_id?: number | null;
  project_name?: string | null;
  portfolio_membership_id?: number | null;
  bucket_code: string | null;
  target_type?: "DEMAND" | "PROJECT" | "PORTFOLIO_MEMBERSHIP";
  target_id?: number;
  bucket_name?: string | null;
  resolution_source?: "EXPLICIT" | "DEMAND" | "THEME_DEFAULT" | "UNCLASSIFIED" | string;
  classification_source?: string;
  rationale?: string;
  indicative_capital_need?: string | number | null;
  currency_code?: string | null;
  classified?: boolean;
};

export type StrategicPositionValue = {
  percentage: string | number | null;
  amount: string | number | null;
  amounts_by_currency?: Record<string, string | number>;
  amount_by_currency?: Record<string, string | number>;
  evaluable?: boolean;
  item_count?: number;
};

export type StrategicBucketComparison = {
  bucket_code: string;
  bucket_name: string;
  target: StrategicPositionValue;
  current_demand: StrategicPositionValue;
  current_portfolio: StrategicPositionValue;
  recommended: StrategicPositionValue;
  approved: StrategicPositionValue;
  variance_percentage?: string | number | null;
  variance_amount?: string | number | null;
  status: "UNDER_TARGET" | "WITHIN_RANGE" | "OVER_TARGET" | "UNCLASSIFIED_EXPOSURE" | "NOT_EVALUABLE" | string;
  drilldown?: {
    demands?: Array<Record<string, unknown>>;
    portfolio_projects?: Array<Record<string, unknown>>;
    recommended_projects?: Array<Record<string, unknown>>;
    approved_projects?: Array<Record<string, unknown>>;
  };
};

export type StrategicAllocationComparison = {
  allocation_plan_id: number;
  allocation_plan_number?: string;
  generated_at?: string;
  population_definition?: string;
  classification_precedence?: string[];
  currencies?: string[];
  evaluable?: boolean;
  warnings?: string[];
  unclassified?: StrategicPositionValue & { count?: number };
  buckets: StrategicBucketComparison[];
  classifications?: StrategicBucketClassification[];
  readiness?: StrategicAllocationReadiness;
  frozen_snapshot_contract?: Record<string, unknown>;
};

export type StrategicAllocationHistoryEvent = {
  id?: number;
  event_type: string;
  occurred_at?: string;
  actor_name?: string | null;
  from_status?: string | null;
  to_status?: string | null;
  version?: number | null;
  detail?: Record<string, unknown>;
};

export type StrategicAllocationOptions = {
  planning_cycles: Array<{ id: number; cycle_number: string; name: string; status: string }>;
  workspaces: Array<{ id: number; name: string; workspace_type_code?: string; type?: string }>;
  portfolios: Array<{ id: number; name: string }>;
  buckets: StrategicCapitalBucket[];
  allocation_basis_options: StrategicAllocationBasis[];
  scope_options: StrategicAllocationScope[];
  demand_status_population?: string[];
  policy?: Record<string, unknown>;
};

export type StrategicAllocationPage<T> = {
  items: T[];
  nextCursor: string | null;
  page: number;
  pageSize: number;
  total: number;
};
