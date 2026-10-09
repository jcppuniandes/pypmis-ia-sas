export type CommercialStrategyStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "IN_REVIEW"
  | "RETURNED"
  | "COMPLETED"
  | "SUPERSEDED"
  | "VOIDED";

export type CommercialReadinessStatus =
  | "NOT_STARTED"
  | "IN_PROGRESS"
  | "READY"
  | "BLOCKED"
  | "STALE"
  | "NOT_APPLICABLE";

export type CommercialStrategyQueue =
  | "mine"
  | "draft"
  | "in_review"
  | "returned"
  | "ready"
  | "completed"
  | "stale"
  | "all_authorized";

export type CommercialStrategyAllowedActions =
  | string[]
  | Partial<
      Record<
        | "can_create"
        | "can_edit"
        | "can_submit"
        | "can_start_review"
        | "can_return"
        | "can_complete"
        | "can_void"
        | "can_create_revision"
        | "can_view_source"
        | "can_refresh_preview",
        boolean
      >
    >;

export type CommercialPackage = {
  id?: number | string;
  package_code: string;
  package_name: string;
  package_type: string;
  scope_summary: string;
  interface_summary: string;
  estimated_value_band?: string | null;
  currency?: string | null;
  anticipated_procurement_approach: string;
  anticipated_contracting_model: string;
  planned_market_window?: string | null;
  key_dependencies: string[];
  critical_interfaces: string[];
  market_risk: string;
  commercial_risk: string;
  status: string;
};

export type CommercialRiskAllocation = {
  id?: number | string;
  risk_reference?: string | null;
  commercial_risk_category: string;
  risk_description: string;
  preferred_owner: string;
  allocation_rationale: string;
  transferability: string;
  pricing_implication: string;
  contractual_treatment: string;
  insurance_or_security_requirement?: string | null;
  residual_concern: string;
  status: string;
};

export type CommercialStrategyContent = {
  commercial_context: string;
  procurement_approach: string;
  procurement_rationale: string;
  packaging_strategy_summary: string;
  packages: CommercialPackage[];
  contracting_model: string;
  contracting_model_rationale: string;
  market_assessment: {
    overall_score: number;
    summary?: string;
    criteria?: Record<string, string | number | null>;
  };
  supply_chain_constraints: Array<Record<string, unknown>>;
  risk_allocations: CommercialRiskAllocation[];
  payment_mechanism: string;
  payment_mechanism_rationale: string;
  incentive_strategy: {
    mechanism: string;
    philosophy: string;
  };
  guarantees_securities_strategy: Record<string, unknown>;
  commercial_assumptions: Array<Record<string, unknown>>;
  commercial_constraints: Array<Record<string, unknown>>;
  dependencies: Array<Record<string, unknown>>;
  legal_regulatory_considerations: Array<Record<string, unknown>>;
  alternatives: Array<Record<string, unknown>>;
  recommendation: {
    recommended_procurement_approach: string;
    recommended_packaging_strategy: string;
    recommended_contracting_model: string;
    recommended_payment_mechanism: string;
    recommended_incentive_strategy: string;
    rationale: string;
    tradeoffs: string[];
    commercial_recommendation_status: string;
  };
  conditions_open_issues: Array<Record<string, unknown>>;
  [key: string]: unknown;
};

export type CommercialStrategyVersion = {
  id: number;
  commercial_strategy_id: number;
  version_number: number;
  version_purpose: string;
  fel_stage_code: string | null;
  status: CommercialStrategyStatus;
  content_json: CommercialStrategyContent;
  readiness_json: Record<string, string>;
  readiness_dimensions?: Record<string, CommercialReadinessStatus>;
  overall_commercial_readiness?: CommercialReadinessStatus;
  readiness_status?: CommercialReadinessStatus;
  readiness_warnings?: string[];
  readiness_blockers?: string[];
  readiness_warnings_json: string[];
  readiness_blockers_json: string[];
  warnings?: string[];
  blockers?: string[];
  source_references_json: Record<string, unknown>;
  source_hashes_json: Record<string, unknown>;
  source_current: boolean;
  configuration_id: number;
  configuration_revision: number;
  configuration_hash: string;
  source_bundle_hash: string;
  commercial_strategy_hash?: string;
  content_hash?: string;
  revision_version: number;
  reviewer_user_id?: number | null;
  preparer_user_id: number;
  return_reason?: string | null;
  void_reason?: string | null;
  allowed_actions: Partial<Record<string, boolean>>;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
};

export type CommercialContractingStrategy = {
  id: number;
  strategy_number: string;
  project_workspace_id: number;
  project_workspace_name?: string;
  owning_workspace_id?: number;
  current_version_id?: number | null;
  current_version: CommercialStrategyVersion | null;
  status?: CommercialStrategyStatus;
  allowed_actions: CommercialStrategyAllowedActions;
  revision_version: number;
  created_at: string;
  updated_at: string;
  final_output?: string;
  next_process?: string;
};

export type CommercialStrategyReadiness = {
  commercial_strategy_id: number;
  version_id: number;
  status: CommercialReadinessStatus;
  overall_commercial_readiness?: CommercialReadinessStatus;
  dimensions: Record<string, CommercialReadinessStatus>;
  warnings: string[];
  blockers: string[];
  source_current: boolean;
  configuration_current?: boolean;
  can_supply_investment_gate_evidence?: boolean;
  commercial_strategy_hash: string;
  source_bundle_hash: string;
  configuration_hash: string;
  persisted?: boolean;
};

export type CommercialRefreshPreview = {
  persisted: false;
  source_delta: Array<Record<string, unknown>>;
  policy_delta: Array<Record<string, unknown>>;
  readiness_delta: Record<string, unknown>;
  warnings: string[];
  blockers: string[];
};

export type CommercialStrategyHistory = {
  version: CommercialStrategyVersion;
  lifecycle_events: Array<Record<string, unknown>>;
};

export type CommercialStrategyConfiguration = {
  id: number;
  name: string;
  description: string;
  status: "DRAFT" | "PUBLISHED" | "ARCHIVED" | "draft" | "published" | "archived";
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  configuration_hash?: string;
  content_hash?: string;
};

export type CommercialStrategyOptions = {
  version_purposes: string[];
  readiness_states: string[];
  queues: string[];
  provider_key: string;
  provider_status: string;
  configuration_id: number;
  configuration_revision: number;
  configuration_hash: string;
  operational_procurement_excluded: boolean;
  procurement_approaches: string[];
  contracting_models: string[];
  package_types: string[];
  risk_allocation_categories: string[];
  payment_mechanisms: string[];
  incentive_mechanisms: string[];
  market_assessment_criteria: string[];
  supply_chain_criteria: string[];
};
