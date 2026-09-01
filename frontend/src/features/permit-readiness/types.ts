export interface ProjectPermit {
  id: number;
  project_workspace_id: number;
  permit_number: string;
  permit_type_code: string;
  requirement_key: string | null;
  title: string;
  issuing_authority: string;
  jurisdiction: string | null;
  status: string;
  application_reference: string | null;
  valid_until: string | null;
  permit_identifier: string | null;
  evidence_refs_json: Array<Record<string, unknown>>;
  responsible_user_id: number | null;
  next_action: string | null;
  target_date: string | null;
  revision_version: number;
}

export interface PermitCondition {
  id: number;
  permit_id: number;
  condition_key: string;
  description: string;
  condition_type: string;
  blocking: boolean;
  owner_id: number | null;
  target_date: string | null;
  status: string;
  evidence_refs_json: Array<Record<string, unknown>>;
  revision_version: number;
}

export interface PermitAssessment {
  id: number;
  assessment_number: string;
  assessment_version: number;
  as_of_date: string;
  valid_until: string;
  gate_profile_code: string;
  project_type_code: string;
  status: string;
  required_permit_count: number;
  approved_count: number;
  approved_with_conditions_count: number;
  missing_count: number;
  rejected_count: number;
  suspended_count: number;
  expired_count: number;
  open_blocking_conditions_count: number;
  evidence_coverage_percent: number;
  warnings_json: string[];
  blockers_json: string[];
  readiness_status: string;
  permit_readiness_hash: string | null;
  revision_version: number;
}

export interface ProjectPermitReadiness {
  project_workspace_id: number;
  project_type_code: string;
  permit_classification: string;
  gate_profile: string;
  assessment_id: number | null;
  assessment_hash: string | null;
  as_of_date: string | null;
  valid_until: string | null;
  required_count: number;
  approved_count: number;
  conditional_count: number;
  missing_count: number;
  rejected_count: number;
  suspended_count: number;
  expired_count: number;
  open_blocking_conditions: number;
  evidence_coverage_percent: number;
  warnings: string[];
  blockers: string[];
  readiness_status: string;
  permit_readiness_hash: string | null;
  source_current: boolean;
  allowed_actions: Record<string, boolean>;
}

export interface ProjectSetPermitReadiness {
  portfolio_workspace_id: number;
  recommended_project_set_hash: string;
  required_project_count: number;
  valid_project_count: number;
  blocked_project_count: number;
  stale_project_count: number;
  expired_project_count: number;
  coverage_percent: number;
  aggregate_required_permit_count: number;
  aggregate_approved_count: number;
  aggregate_conditional_count: number;
  aggregate_missing_count: number;
  aggregate_rejected_count: number;
  aggregate_suspended_count: number;
  aggregate_expired_count: number;
  aggregate_blocking_condition_count: number;
  warnings: string[];
  blockers: string[];
  readiness_status: string;
  permit_readiness_hash: string;
  project_readiness: ProjectPermitReadiness[];
}

export interface PermitConfiguration {
  id: number;
  name: string;
  description: string;
  status: string;
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash: string;
}
