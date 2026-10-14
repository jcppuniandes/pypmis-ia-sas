export type EvidencePolicyConfiguration = {
  id: number;
  tenant_id: number;
  kind: string;
  code: string;
  name: string;
  description: string;
  status: "draft" | "published" | "superseded";
  revision: number;
  version: number;
  content_json: EvidencePolicyContent;
  content_hash: string;
  published_at?: string | null;
  effective_from?: string | null;
};

export type GateCriterionType =
  | "READINESS_CHECK"
  | "MUST_MEET"
  | "DECISION_HURDLE"
  | "PRIORITIZATION"
  | "SUCCESS_CRITERION";

export type GateCriterionOperator =
  | "EQUALS"
  | "NOT_EQUALS"
  | "GREATER_THAN"
  | "GREATER_THAN_OR_EQUAL"
  | "LESS_THAN"
  | "LESS_THAN_OR_EQUAL"
  | "IN"
  | "NOT_IN"
  | "IS_TRUE"
  | "IS_FALSE"
  | "IS_READY"
  | "IS_CURRENT"
  | "COVERAGE_AT_LEAST"
  | "WITHIN_RANGE";

export const QRA_EVIDENCE_TYPES = ["COST_QRA_RESULT", "SCHEDULE_QRA_RESULT"] as const;

export type QraEvidencePolicy = {
  analysis_type: "COST_QRA" | "SCHEDULE_QRA";
  applicability: "REQUIRED" | "CONDITIONAL" | "NOT_REQUIRED" | "NOT_APPLICABLE";
  governance_model_filter: string[];
  project_type_filter: string[];
  fel_stage_filter: string[];
  project_risk_filter: string[];
  project_complexity_filter: string[];
  uncertainty_level_filter: string[];
  value_band?: { source: "PROJECT_CREATION_ESTIMATED_BUDGET"; currency: string; minimum?: number; maximum?: number };
  analytical_readiness: "READY_ONLY" | "WARNINGS_ALLOWED";
  convergence: "REQUIRED" | "WARNING_ALLOWED" | "NOT_REQUIRED";
  scope_requirement: "WHOLE_PROJECT" | "PARTIAL_ALLOWED";
  freshness_days?: number | null;
  selected_percentiles?: number[];
  capability_requirements?: {
    schedule_state: "NOT_STARTED";
    remaining_duration: "SOURCE_DURATION";
    calendar_mode: "NORMALIZED_ELAPSED_TIME_V1";
  };
  bc_consistency_required: boolean;
};

export type GateDecisionCriterion = {
  criterion_id?: string | number;
  criterion_code: string;
  criterion_name?: string;
  criterion_type: GateCriterionType;
  gate_profile_code?: string;
  gate_profiles?: string[];
  fel_stage_applicability?: string[];
  project_type_applicability?: string[];
  governance_model_applicability?: string[];
  project_type_filter?: string[];
  governance_model_filter?: string[];
  uncertainty_level_filter?: string[];
  source_evidence_type: string;
  source_field?: string;
  operator: GateCriterionOperator | string;
  threshold?: unknown;
  expected_state?: unknown;
  expected_value?: unknown;
  scope?: string;
  success_snapshot_fields?: string[];
  blocking: boolean;
  required: boolean;
  weight?: number | null;
  effective_from?: string | null;
  version?: number;
  status?: string;
  rationale?: string;
  [key: string]: unknown;
};

export type EvidenceRequirement = {
  requirement_key: string;
  evidence_type: string;
  classification: "A" | "B" | "C";
  required: boolean;
  blocking: boolean;
  scope: "PORTFOLIO" | "PROJECT_SET" | "EACH_PROJECT" | "SELECTED_PROJECTS_ONLY";
  provider_key?: string | null;
  provider_required: boolean;
  validity_period_days?: number | null;
  coverage_requirement?: number | null;
  allow_manual_reference: boolean;
  manual_validation_required: boolean;
  rationale: string;
  order: number;
  qra_policy?: QraEvidencePolicy;
  qra_applicability?: Record<string, unknown>;
};

export type EvidencePolicyContent = {
  policy_code: string;
  policy_name: string;
  applicable_governance_models: string[];
  gate_profiles: Record<string, { allow_valid_with_conditions: boolean; requirements: EvidenceRequirement[] }>;
  project_type_overrides: Array<Record<string, unknown>>;
  effective_from?: string | null;
  blocking_policy: Record<string, unknown>;
  validity_policy: Record<string, unknown>;
  coverage_policy: Record<string, unknown>;
  decision_criteria?: GateDecisionCriterion[];
  decision_criterion_policy?: {
    policy_code?: string;
    effective_from?: string | null;
    criterion_types?: string[];
    controlled_operators?: string[];
    evidence_quality_states?: string[];
    unsafe_expression_execution?: boolean;
    formal_decision_authority?: string;
    portfolio_rank_authority?: string;
    criteria_by_profile?: Record<string, GateDecisionCriterion[]>;
    tailoring_dimensions?: string[] | Record<string, unknown>;
    new_round_policy?: Record<string, unknown>;
    [key: string]: unknown;
  };
  criterion_types?: string[] | Record<string, unknown>;
  controlled_operators?: string[];
  criterion_applicability?: Record<string, unknown>;
  evidence_quality_rules?: Record<string, unknown>;
  freshness_rules?: Record<string, unknown>;
  portfolio_context_rules?: Record<string, unknown>;
  success_criteria_rules?: Record<string, unknown>;
  governance_model_overrides?: Array<Record<string, unknown>>;
  fel_stage_overrides?: Array<Record<string, unknown>>;
  uncertainty_complexity_tailoring?: Record<string, unknown> | Array<Record<string, unknown>>;
  inheritance?: Record<string, unknown>;
  segregation_of_duties?: Record<string, unknown>;
  [key: string]: unknown;
};

export type EvidenceProvider = {
  provider_key: string;
  evidence_type: string;
  source_module: string;
  source_contract: string;
  status: "AVAILABLE" | "UNAVAILABLE" | "RESERVED";
  availability: string;
  contract_status: string;
  last_validation: string | null;
  version: string;
  supports_portfolio_scope: boolean;
  supports_project_scope: boolean;
  supports_project_set_scope: boolean;
  supports_hash: boolean;
  supports_current_flag: boolean;
  supports_readiness: boolean;
  notes: string;
  contract_valid: boolean;
  contract_issues: string[];
  compatible_evidence_types?: string[];
  analysis_types?: string[];
};

export type MissingProvider = {
  evidence_type: string;
  gate_profile: string;
  project_type: string | null;
  classification: "A";
  blocking: boolean;
  provider: string | null;
  provider_status: string;
  gap_status: string;
  recommended_action: string;
};

export type EvidencePolicyOverview = {
  configurations: EvidencePolicyConfiguration[];
  providers: EvidenceProvider[];
  missing_providers: MissingProvider[];
  required_adr_decisions: Array<Record<string, unknown>>;
  allowed_actions: string[];
  boundaries: string[];
  release_contract: Record<string, unknown>;
};

export type EvidencePolicyPreview = {
  policy: Record<string, unknown>;
  gate_profile_code: string;
  portfolio_workspace_id: number | null;
  project_contexts: Array<Record<string, unknown>>;
  effective_matrix: Array<EvidenceRequirement & Record<string, unknown>>;
  provider_registry_snapshot: EvidenceProvider[];
  current_evidence_status: Array<Record<string, unknown>>;
  missing_providers: MissingProvider[];
  available_provider_count: number;
  missing_required_provider_count: number;
  class_A_count: number;
  class_B_count: number;
  class_C_count: number;
  blocking_missing_sources: string[];
  warnings: string[];
  blockers: string[];
  effective_classifications: Record<string, string[]>;
  required_coverage: Record<string, number | null>;
  source_availability: Record<string, string>;
  source_readiness: Record<string, string[]>;
  source_current: Record<string, boolean[]>;
  decision_criterion_policy?: Record<string, unknown>;
  decision_criteria?: GateDecisionCriterion[];
  criterion_validation_issues?: string[];
  decision_criterion_taxonomy?: string[];
  controlled_operators?: string[];
  evidence_quality_states?: string[];
  evidence_readiness_status?: string;
  business_evaluation_status?: string;
  portfolio_context_status?: string;
  decision_package_status?: string;
  portfolio_context_snapshot?: Record<string, unknown>;
  success_criteria_candidates?: Array<Record<string, unknown>>;
  would_gate07j_be_ready: boolean;
  would_be_ready_for_investment_gate: boolean;
  recommended_next_development: Record<string, unknown>;
  can_design_investment_decision_gate: boolean;
  can_enter_fid: false;
  persisted: false;
  final_output: string;
};
