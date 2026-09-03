export type BusinessCaseRevision = {
  id: number;
  business_case_id: number;
  revision_number: number;
  revision_label: string;
  purpose: string;
  status: string;
  as_of_date: string;
  fel_stage_code: string | null;
  title: string;
  executive_summary: string;
  business_need: string;
  strategic_alignment_json: Array<Record<string, unknown>>;
  objectives_json: Array<Record<string, unknown>>;
  scope_json: Record<string, unknown>;
  alternatives_json: Array<Record<string, unknown>>;
  benefits_json: Array<Record<string, unknown>>;
  assumptions_json: Array<Record<string, unknown>>;
  constraints_json: Array<Record<string, unknown>>;
  delivery_json: Record<string, unknown>;
  unresolved_concerns_json: Array<Record<string, unknown>>;
  recommendation_json: Record<string, unknown>;
  source_references_json: Record<string, Record<string, unknown>>;
  source_hashes_json: Record<string, string>;
  source_snapshot_hash: string;
  economic_financial_model_id: number | null;
  economic_financial_model_version: number | null;
  economic_financial_model_hash: string | null;
  financial_model_status: "NOT_AVAILABLE" | "AVAILABLE" | "STALE";
  economic_financial_readiness: string | null;
  economic_financial_as_of_date: string | null;
  npv: string | null;
  irr: string | null;
  payback_period: string | null;
  benefit_cost_ratio: string | null;
  readiness_status: string;
  readiness_warnings_json: string[];
  readiness_blockers_json: string[];
  readiness_hash: string;
  material_change_status: string;
  content_hash: string;
  preparer_user_id: number;
  reviewer_user_id: number | null;
  revision_version: number;
  created_at: string;
  updated_at: string;
};

export type BusinessCase = {
  id: number;
  business_case_number: string;
  project_workspace_id: number;
  source_project_proposal_id: number | null;
  owning_workspace_id: number;
  owner_user_id: number;
  sponsor_user_id: number | null;
  status: string;
  current_revision_id: number | null;
  material_change_review_json: Record<string, unknown>;
  configuration_id: number;
  configuration_revision: number;
  configuration_hash: string;
  configuration_source_workspace_id: number | null;
  configuration_resolution_chain_json: Array<Record<string, unknown>>;
  revision_version: number;
  created_at: string;
  updated_at: string;
  current_revision: BusinessCaseRevision | null;
  final_output: string;
  next_process: string;
};

export type Readiness = {
  business_case_id: number;
  revision_id: number;
  status: string;
  warnings: string[];
  blockers: string[];
  source_current: boolean;
  readiness_hash: string;
  final_output: string;
  persisted: boolean;
};

export type RefreshPreview = {
  business_case_id: number;
  current_revision_id: number;
  source_changes: Array<Record<string, unknown>>;
  material_change_status: string;
  recommended_purpose: string;
  persisted: false;
};

export type DecisionSnapshot = {
  id: number;
  business_case_id: number;
  business_case_revision_id: number;
  snapshot_type: string;
  decision_reference_type: string | null;
  decision_reference_id: number | null;
  decision_reference_hash: string | null;
  revision_content_hash: string;
  source_snapshot_hash: string;
  snapshot_json: Record<string, unknown>;
  snapshot_hash: string;
  created_by: number;
  created_at: string;
};

export type BusinessCaseConfiguration = {
  id: number;
  name: string;
  description: string;
  status: string;
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash: string;
};
