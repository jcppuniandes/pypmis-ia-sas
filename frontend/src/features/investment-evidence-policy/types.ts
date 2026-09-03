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
  would_gate07j_be_ready: boolean;
  would_be_ready_for_investment_gate: boolean;
  recommended_next_development: Record<string, unknown>;
  can_design_investment_decision_gate: boolean;
  can_enter_fid: false;
  persisted: false;
  final_output: string;
};
