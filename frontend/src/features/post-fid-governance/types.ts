export type EligibilityStatus =
  | "READY_FOR_PROJECT_WORKSPACE_INITIALIZATION"
  | "READY_FOR_PROJECT_WORKSPACE_ACTIVATION"
  | "POST_FID_PROJECT_GOVERNANCE_BLOCKED"
  | "NO_REACTIVATION_REQUIRED"
  | "NOT_APPLICABLE"
  | "STALE";

export type PostFIDEligibility = {
  id: number | null;
  investment_decision_id: number;
  project_workspace_id: number;
  project_number: string;
  project_name: string;
  project_type: string;
  governance_model: string;
  project_state: string;
  workspace_status: string;
  initialization_state: string;
  fid_current: boolean;
  eligibility_round: number;
  snapshot_eligibility_status: EligibilityStatus;
  eligibility_status: EligibilityStatus;
  final_output: EligibilityStatus;
  warnings: string[];
  blockers: string[];
  post_fid_conditions: Array<Record<string, unknown>>;
  open_activation_blockers: number;
  open_commitment_conditions_count: number;
  can_initialize: boolean;
  can_activate: boolean;
  next_allowed_process: string;
  allowed_actions: string[];
  fid_decision_hash: string;
  decision_package_hash: string;
  condition_snapshot_hash: string;
  eligibility_hash: string;
  source_current: boolean;
  stale: boolean;
  persisted: boolean;
  evaluated_at: string | null;
  evaluated_by: number | null;
  revision_version: number;
};

export type PostFIDDecision = {
  investment_decision_id: number;
  decision_number: string;
  title: string;
  gate_profile: string;
  status: string;
  outcome: string | null;
  is_fid: boolean;
  post_fid_handoff: string | null;
  final_output: string;
  project_count: number;
  projects: PostFIDEligibility[];
  next: string;
};

export type PostFIDConfiguration = {
  id: number;
  name: string;
  description: string;
  status: string;
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash: string;
};

export type RefreshPreview = {
  investment_decision_id: number;
  deltas: Array<Record<string, unknown>>;
  projects: PostFIDEligibility[];
  persisted: false;
};
