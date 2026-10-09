export type CapitalPlanningCycleStatus = "DRAFT" | "OPEN" | "IN_REVIEW" | "CLOSED";

export type CapitalDemandStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "IN_REVIEW"
  | "RETURNED"
  | "ENDORSED"
  | "DEFERRED"
  | "CANCELLED"
  | "SUPERSEDED";

export type CapitalPlanningCycle = {
  id: number;
  cycle_number: string;
  name: string;
  planning_horizon_start: string;
  planning_horizon_end: string;
  status: CapitalPlanningCycleStatus;
  scope_workspace_id: number | null;
  scope_workspace_name?: string | null;
  responsible_organization_workspace_id: number | null;
  responsible_organization_name?: string | null;
  applicable_theme_codes: string[];
  capital_basis_currency: string | null;
  description: string;
  demand_count: number;
  revision_version: number;
  created_at?: string;
  updated_at?: string;
};

export type CapitalPlanningCycleDraft = {
  name: string;
  planning_horizon_start: string;
  planning_horizon_end: string;
  scope_workspace_id: number | null;
  responsible_organization_workspace_id: number | null;
  applicable_theme_codes: string[];
  capital_basis_currency: string | null;
  description: string;
};

export type CapitalDemandReadiness = {
  status?: string;
  ready?: boolean;
  overall?: string;
  blockers?: string[];
  warnings?: string[];
  dimensions?: Record<string, string | boolean | number>;
};

export type CapitalDemandIdeaOrigin = {
  id?: number;
  idea_id: number;
  idea_number: string;
  idea_title?: string;
  source_capital_demand_id?: number;
  capital_demand_id?: number;
  source_demand_version?: number;
  source_snapshot_hash: string;
  source_configuration_hash?: string;
  originated_at?: string;
  originated_by?: number | string;
  originated_by_user_id?: number;
  created?: boolean;
};

export type StrategicCapitalDemand = {
  id: number;
  demand_number: string;
  name: string;
  description: string;
  planning_cycle_id: number;
  planning_cycle_number?: string;
  planning_cycle_name?: string;
  theme_codes: string[];
  theme_labels?: string[];
  strategic_objective_codes: string[];
  strategic_objective_labels?: string[];
  business_or_asset_need: string;
  strategic_driver: string;
  demand_category: string;
  urgency: string;
  target_horizon: string;
  sponsor_user_id: number | null;
  sponsor_name?: string | null;
  owning_workspace_id: number;
  owning_workspace_name?: string;
  location_context: string;
  indicative_capital_need: string | null;
  indicative_capital_range_low: string | null;
  indicative_capital_range_high: string | null;
  currency_code: string | null;
  uncertainty_level: string | null;
  potential_portfolio_id: number | null;
  potential_portfolio_name?: string | null;
  strategic_bucket_code?: string | null;
  strategic_bucket_name?: string | null;
  strategic_bucket_source?: string | null;
  assumptions: string[];
  constraints: string[];
  dependencies: string[];
  status: CapitalDemandStatus;
  readiness: CapitalDemandReadiness;
  ideas_originated: number;
  originated_ideas?: CapitalDemandIdeaOrigin[];
  allowed_actions: string[];
  revision_version: number;
  created_at: string;
  updated_at: string;
  submitted_at?: string | null;
  endorsed_at?: string | null;
  demand_hash?: string;
};

export type StrategicCapitalDemandDraft = {
  name: string;
  description: string;
  planning_cycle_id: number;
  theme_codes: string[];
  strategic_objective_codes: string[];
  business_or_asset_need: string;
  strategic_driver: string;
  demand_category: string;
  urgency: string;
  target_horizon: string;
  sponsor_user_id: number | null;
  owning_workspace_id: number;
  location_context: string;
  indicative_capital_need: string | null;
  indicative_capital_range_low: string | null;
  indicative_capital_range_high: string | null;
  currency_code: string | null;
  uncertainty_level: string | null;
  potential_portfolio_id: number | null;
  assumptions: string[];
  constraints: string[];
  dependencies: string[];
};

export type CapitalPlanningCatalogItem = {
  code: string;
  label: string;
  description?: string;
};

export type CapitalPlanningOptions = {
  cycle_number_preview?: string;
  demand_number_preview?: string;
  planning_cycles: CapitalPlanningCycle[];
  themes: CapitalPlanningCatalogItem[];
  strategic_capital_buckets?: CapitalPlanningCatalogItem[];
  strategic_objectives: CapitalPlanningCatalogItem[];
  demand_drivers: CapitalPlanningCatalogItem[];
  demand_categories: CapitalPlanningCatalogItem[];
  planning_horizons: CapitalPlanningCatalogItem[];
  urgency_levels: CapitalPlanningCatalogItem[];
  uncertainty_levels: CapitalPlanningCatalogItem[];
  owning_workspaces: Array<{ id: number; name: string; workspace_type_code?: string }>;
  responsible_organizations?: Array<{ id: number; name: string }>;
  sponsors: Array<{ id: number; name: string; email?: string }>;
  potential_portfolios: Array<{ id: number; name: string }>;
  currencies?: CapitalPlanningCatalogItem[];
  configuration_source?: Record<string, unknown>;
};

export type CapitalPlanningCycleSummary = {
  cycle_id: number | null;
  demand_count: number;
  status_counts: Record<string, number>;
  theme_counts: Record<string, number>;
  driver_counts: Record<string, number>;
  horizon_counts: Record<string, number>;
  uncertainty_counts: Record<string, number>;
  indicative_capital_totals_by_currency: Record<string, string | number>;
  unpriced_demand_count?: number;
  normalization_warning?: string | null;
};

export type CapitalDemandFilters = {
  search: string;
  planning_cycle_id: string;
  status: string;
  theme: string;
  strategic_objective: string;
  bucket_code: string;
  driver: string;
  sponsor_user_id: string;
  owning_workspace_id: string;
  urgency: string;
  target_horizon: string;
  potential_portfolio_id: string;
  uncertainty_level: string;
  mine: "" | "true";
};

export type CapitalPlanningPage<T> = {
  items: T[];
  nextCursor: string | null;
  page: number;
  pageSize: number;
  total: number;
};

export type CapitalPlanningConfiguration = {
  id: number;
  code?: string;
  name: string;
  description: string;
  status: "draft" | "published" | "archived" | "DRAFT" | "PUBLISHED" | "ARCHIVED";
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash?: string;
};

export type CapitalPlanningConfigurationPreview = {
  persisted: false;
  owning_workspace_id: number | null;
  effective: Record<string, unknown>;
  source: Record<string, unknown>;
  resolution_path: Array<Record<string, unknown>>;
  [key: string]: unknown;
};
