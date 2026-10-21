export type OperationalCondition = string | Record<string, unknown>;

export type OperationalAuthorization = {
  authorized_for_operational_context: boolean;
  route: string;
  authority_source: string;
  authority_reference: string | number | null;
  as_of: string;
  blocking_conditions: OperationalCondition[];
  commitment_conditions: OperationalCondition[];
  warnings: OperationalCondition[];
  source_hash: string;
};

export type OperationalProfile = {
  id: number;
  code: string;
  name: string;
  status: "DRAFT" | "PUBLISHED";
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  allowed_actions?: string[];
};

export type OperationalPeriod = {
  id: number;
  period_code: string;
  period_start: string;
  period_end: string;
  cutoff_at: string;
  timezone: string;
  status: "OPEN" | "REVIEW" | "CLOSED" | "PUBLISHED";
  revision: number;
  version: number;
  schedule_data_date: string | null;
  source_configuration_revision: number | string;
  reopen_parent_id: number | null;
  notes: string;
  opened_by: number | null;
  closed_by: number | null;
  published_by: number | null;
  allowed_actions: string[];
};

export type OperationalBinding = {
  id: number;
  legacy_project_id: number;
  status: string;
  revision: number;
  version: number;
  reason: string;
  source: string;
  effective_from: string | null;
  effective_to: string | null;
};

export type OperationalProjectContext = {
  tenant_id: number;
  project_workspace_id: number;
  name: string;
  project_workspace_external_key: string;
  project_workspace_record_code: string;
  project_workspace_status: string;
  governance_model: string;
  project_type: string;
  authorization_route: string;
  activation_state: string;
  legacy_project_id: number | null;
  binding_state: string;
  binding_version: number;
  operational_profile: OperationalProfile | null;
  effective_policy_revision: number | string | null;
  current_reporting_period: OperationalPeriod | null;
  authorization: OperationalAuthorization;
  blocking_conditions: OperationalCondition[];
  warnings: OperationalCondition[];
  allowed_actions: string[];
};

export type BindingResult = {
  state: string;
  binding: OperationalBinding | null;
  history: OperationalBinding[];
};

export type PeriodDraft = {
  period_code: string;
  period_start: string;
  period_end: string;
  cutoff_at: string;
  timezone: string;
  schedule_data_date: string | null;
  reason: string;
  notes: string;
};
