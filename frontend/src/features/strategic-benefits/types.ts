export type BenefitsPlanStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "IN_REVIEW"
  | "RETURNED"
  | "COMPLETED"
  | "SUPERSEDED"
  | "VOIDED";

export type BenefitsReadinessStatus = "NOT_STARTED" | "IN_PROGRESS" | "READY" | "BLOCKED" | "STALE" | "NOT_APPLICABLE";

export type BenefitsPlanQueue =
  | "mine"
  | "draft"
  | "in_review"
  | "returned"
  | "ready"
  | "completed"
  | "stale"
  | "all_authorized";

export type BenefitsAllowedAction =
  | "can_create"
  | "can_edit"
  | "can_add_benefit"
  | "can_edit_benefit"
  | "can_assign_owner"
  | "can_submit"
  | "can_start_review"
  | "can_return"
  | "can_complete"
  | "can_void"
  | "can_create_revision"
  | "can_view_sources"
  | "can_refresh_preview"
  | "can_refresh_apply";

export type BenefitsAllowedActions = string[] | Partial<Record<BenefitsAllowedAction | string, boolean>>;

export type BaselineStatus = "KNOWN" | "UNKNOWN";

export type BenefitsReference = Record<string, unknown>;

export type BenefitOwner = {
  owner_type: string | null;
  owner_user_id: number | null;
  owner_organization_unit_id: number | null;
  owner_security_role_id: number | null;
  owner_reference: string | null;
  effective_from: string | null;
  effective_to: string | null;
  accountability_statement: string;
  acceptance_status: string | null;
};

export type BenefitMeasure = {
  id: number;
  benefit_snapshot_id: number;
  measure_code: string;
  measure_name: string;
  definition: string;
  unit_of_measure: string;
  direction: string;
  is_primary: boolean;
  baseline_status: BaselineStatus;
  baseline_value: unknown | null;
  baseline_as_of_date: string | null;
  baseline_source: string | null;
  baseline_evidence_reference: string | null;
  baseline_confidence: string | null;
  target_value: unknown | null;
  target_date: string | null;
  target_basis: string | null;
  tolerance: BenefitsReference;
  measurement_method: string;
  measurement_frequency: string | null;
  data_source_description: string | null;
  measurement_owner_reference: BenefitsReference;
  measure_hash: string;
  created_at: string;
  updated_at: string;
  revision_version: number;
};

export type StrategicBenefit = {
  id: number;
  benefit_number: string;
  identity_status: string;
  snapshot_id: number;
  status: string;
  benefit_name: string;
  benefit_description: string;
  benefit_direction: "BENEFIT" | "DISBENEFIT" | string;
  benefit_type: string;
  benefit_category: string | null;
  strategic_objective_refs: Array<Record<string, unknown>>;
  source_need_reference: BenefitsReference;
  source_business_analysis_reference: BenefitsReference;
  source_project_proposal_reference: BenefitsReference;
  source_business_case_reference: BenefitsReference;
  expected_outputs: Array<Record<string, unknown>>;
  expected_outcomes: Array<Record<string, unknown>>;
  benefit_statement: string;
  owner: BenefitOwner;
  expected_value: BenefitsReference;
  monetizable_flag: boolean;
  dependencies: Array<Record<string, unknown>>;
  assumptions: Array<Record<string, unknown>>;
  constraints: Array<Record<string, unknown>>;
  risk_references: Array<Record<string, unknown>>;
  snapshot_hash: string;
  measures: BenefitMeasure[];
  revision_version: number;
  allowed_actions?: BenefitsAllowedActions;
};

export type BenefitsPlanVersion = {
  id: number;
  benefits_plan_id: number;
  version_number: number;
  version_purpose: string;
  status: BenefitsPlanStatus;
  fel_stage_code: string | null;
  overview_json: Record<string, unknown>;
  outputs_json: Array<Record<string, unknown>>;
  outcomes_json: Array<Record<string, unknown>>;
  assumptions_json: Array<Record<string, unknown>>;
  constraints_json: Array<Record<string, unknown>>;
  benefits: StrategicBenefit[];
  readiness_json: Record<string, unknown>;
  overall_benefits_readiness?: BenefitsReadinessStatus;
  readiness_status: BenefitsReadinessStatus;
  readiness_warnings_json: string[];
  readiness_blockers_json: string[];
  coverage: Record<string, unknown>;
  source_references_json: Record<string, unknown>;
  source_hashes_json: Record<string, string>;
  source_current: boolean;
  configuration_id: number;
  configuration_revision: number;
  configuration_hash: string;
  source_bundle_hash: string;
  content_hash?: string;
  benefit_set_hash?: string;
  traceability_hash?: string;
  benefits_plan_hash?: string;
  preparer_user_id: number;
  reviewer_user_id?: number | null;
  revision_version: number;
  allowed_actions?: BenefitsAllowedActions;
  can_supply_investment_gate_evidence?: boolean;
  return_reason?: string | null;
  void_reason?: string | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
  submitted_at?: string | null;
  review_started_at?: string | null;
  returned_at?: string | null;
  completed_by?: number | null;
  voided_at?: string | null;
};

export type StrategicBenefitsPlan = {
  id: number;
  plan_number: string;
  project_workspace_id: number;
  project_workspace_name?: string;
  status: BenefitsPlanStatus;
  current_version_id?: number | null;
  current_version: BenefitsPlanVersion | null;
  configuration_id: number;
  configuration_revision: number;
  configuration_hash: string;
  configuration_source_workspace_id?: number | null;
  configuration_resolution_chain_json?: Array<Record<string, unknown>>;
  created_by?: number;
  updated_by?: number;
  revision_version: number;
  allowed_actions: BenefitsAllowedActions;
  final_output?: string;
  next_process?: string;
  created_at: string;
  updated_at: string;
};

export type BenefitsReadiness = {
  benefits_plan_id: number;
  version_id: number;
  status: BenefitsReadinessStatus;
  overall_benefits_readiness?: BenefitsReadinessStatus;
  dimensions: Record<string, BenefitsReadinessStatus>;
  coverage: Record<string, number>;
  warnings: string[];
  blockers: string[];
  source_current: boolean;
  configuration_current: boolean;
  can_supply_investment_gate_evidence: boolean;
  benefits_plan_hash: string;
  source_bundle_hash: string;
  configuration_hash: string;
  persisted?: boolean;
};

export type BenefitsTraceabilityRow = {
  strategic_objectives: BenefitsReference[];
  need_opportunity: BenefitsReference;
  business_analysis: BenefitsReference;
  recommended_option: BenefitsReference;
  project: BenefitsReference;
  business_case: BenefitsReference;
  expected_outputs: BenefitsReference[];
  expected_outcomes: BenefitsReference[];
  benefit_id: number;
  benefit_number: string;
  benefit_name: string;
  measures: Array<{
    code?: string;
    name?: string;
    baseline_status?: BaselineStatus;
    baseline?: unknown;
    target?: unknown;
    target_date?: string | null;
  }>;
  owner: BenefitOwner;
  target_dates: string[];
  expected_value: BenefitsReference;
  status: string;
};

export type BenefitsTraceabilityPage = {
  items: BenefitsTraceabilityRow[];
  nextCursor: string | null;
  pageLimit: number;
  resultCount: number;
};

export type BenefitsRefreshPreview = {
  persisted: false;
  source_delta: Array<Record<string, unknown>>;
  benefit_delta: Array<Record<string, unknown>>;
  owner_delta: Array<Record<string, unknown>>;
  measure_delta: Array<Record<string, unknown>>;
  target_delta: Array<Record<string, unknown>>;
  policy_delta: Array<Record<string, unknown>>;
  readiness_delta: Record<string, unknown>;
  warnings: string[];
  blockers: string[];
};

export type BenefitsPlanHistory = {
  version: BenefitsPlanVersion;
  lifecycle_events: Array<Record<string, unknown>>;
};

export type BenefitsConfiguration = {
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

export type BenefitsOptions = {
  version_purposes: string[];
  queues: string[];
  readiness_states: string[];
  provider_key: string;
  provider_status: string;
  configuration_id: number;
  configuration_revision: number;
  configuration_hash: string;
  benefit_types: string[];
  benefit_categories: string[];
  measure_types?: string[];
  units_of_measure: string[];
  measurement_frequencies: string[];
  measure_directions: string[];
  owner_types?: string[];
  owner_acceptance_statuses?: string[];
  benefit_directions?: string[];
};
