export type ConfigurationVersion = {
  id: number;
  kind: string;
  code: string;
  name: string;
  description: string;
  status: "draft" | "published" | "archived";
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash: string;
  published_at: string | null;
};

export type EnterpriseNode = {
  id: number;
  parent_id: number | null;
  workspace_type_code: string;
  code: string;
  external_key: string | null;
  record_code: string;
  depth: number;
  name: string;
  description: string;
  organization_unit_id: number | null;
  responsible_user_id: number | null;
  region_code: string;
  valid_from: string | null;
  valid_to: string | null;
  status: "draft" | "active" | "inactive" | "archived";
  sort_order: number;
  version: number;
  created_at: string;
  updated_at: string;
};

export type EnterpriseTreeNode = EnterpriseNode & { children: EnterpriseTreeNode[] };

export type Classification = {
  id: number;
  workspace_id: number;
  category_set_code: string;
  category_item_code: string;
  created_at: string;
};

export type WorkspaceLink = {
  id: number;
  source_workspace_id: number;
  target_workspace_id: number;
  relationship_type: string;
  valid_from: string | null;
  valid_to: string | null;
  status: string;
  created_at: string;
};

export type CompositionRule = {
  parent_type_code: string;
  parent_type_name: string;
  configuration_id: number;
  revision: number;
  status: "draft" | "published";
  allowed_children: string[];
  max_depth: number | null;
  can_be_root: boolean;
  required_categories: string[];
  required_fields: string[];
};

export type CategoryItem = { code: string; label: string };

export type CoreRelease = {
  id: number;
  release_code: string;
  release_name: string;
  revision_number: number;
  revision_version: number;
  state: "draft" | "published" | "superseded" | "unpublished";
  previous_release_id: number | null;
  source_hash: string;
  canonical_hash: string;
  content_fingerprint: string;
  workspace_count: number;
  objective_count: number;
  classification_count: number;
  link_count: number;
  published_at: string | null;
  published_by: string | null;
};

export type RevisionClassification = {
  category_set_code: string;
  category_item_code: string;
};

export type RevisionWorkspace = {
  workspace_key: string;
  technical_id: number | null;
  parent_key: string | null;
  record_code: string;
  code: string;
  name: string;
  workspace_type_code: string;
  description: string;
  responsible_user_id: number | null;
  status: "draft" | "active" | "inactive" | "archived";
  sort_order: number;
  change_state: "add" | "modify" | "move" | "archive" | "classification" | "unchanged";
  classifications: RevisionClassification[];
};

export type RevisionValidation = {
  valid: boolean;
  errors: string[];
  conflicts: string[];
  checks: Record<string, boolean>;
  draft_hash: string;
  diff_hash: string;
  validated_at: string | null;
};

export type CoreRevision = CoreRelease & {
  base_content_fingerprint: string;
  created_at: string;
  created_by: string;
  updated_at: string;
  last_modified_by: string | null;
  validated_at: string | null;
  approved_at: string | null;
  approved_by: string | null;
  draft_hash: string;
  diff_hash: string;
  validation: RevisionValidation | null;
  workspaces: RevisionWorkspace[];
};

export type RevisionDiffItem = {
  action: "ADD" | "MODIFY" | "MOVE" | "ARCHIVE" | "CLASSIFICATION";
  workspace_key: string;
  old_record_code: string | null;
  new_record_code: string | null;
  workspace_type: string;
  name: string;
  parent_before: string | null;
  parent_after: string | null;
  classifications_before: RevisionClassification[];
  classifications_after: RevisionClassification[];
  status_before: string | null;
  status_after: string | null;
  affected_descendants: string[];
};

export type RevisionDiff = {
  release_id: number;
  draft_hash: string;
  diff_hash: string;
  summary: Record<string, number>;
  items: RevisionDiffItem[];
};

export type RecordCodePreview = {
  current_record_code: string | null;
  record_code: string;
  affected_descendants: Array<{ workspace_key: string; before: string; after: string }>;
};

export type EnterpriseStructureConfiguration = {
  workspace_types: ConfigurationVersion[];
  categories: ConfigurationVersion[];
  composition_rules: CompositionRule[];
  drafts: ConfigurationVersion[];
  tree: EnterpriseTreeNode[];
  classifications: Classification[];
  links: WorkspaceLink[];
  summary: Record<string, number>;
  published_release: CoreRelease | null;
  draft_release: CoreRevision | null;
};

export type EnterpriseExplorer = {
  tree: EnterpriseTreeNode[];
  nodes: EnterpriseNode[];
  workspace_types: ConfigurationVersion[];
  objectives: CategoryItem[];
  classifications: Classification[];
  links: WorkspaceLink[];
  summary: Record<string, number>;
  published_release: CoreRelease | null;
};

export type EnterpriseNodeDetail = {
  node: EnterpriseNode;
  path: EnterpriseNode[];
  classifications: Classification[];
  links: WorkspaceLink[];
};

export type ConfigurationValidation = {
  valid: boolean;
  issues: string[];
  warnings: string[];
  configuration_ids: number[];
};

export type PublicationResult = ConfigurationValidation & { published: ConfigurationVersion[] };

export type NodePayload = {
  code: string;
  name: string;
  workspace_type_code: string;
  parent_id: number | null;
  description: string;
  region_code: string;
  status: EnterpriseNode["status"];
  sort_order: number;
};

export type ExplorerFilters = {
  search: string;
  workspace_type: string;
  business_unit_id: string;
  strategic_objective: string;
  region: string;
  status: string;
};

export type ProjectParentOption = {
  id: number;
  name: string;
  workspace_type_code: "portfolio" | "program";
  record_code: string;
  status: string;
};

export type ProjectConfiguration = {
  project_type: ConfigurationVersion;
  templates: ConfigurationVersion[];
  numbering_rule: ConfigurationVersion;
  creation_policy: ConfigurationVersion;
  classification_sets: ConfigurationVersion[];
  available_modules: ConfigurationVersion[];
  parent_options: ProjectParentOption[];
  allowed_parent_types: string[];
  summary: Record<string, number>;
  gate_status: "READY_FOR_PROJECT_CREATION_PROCESS" | "GATE05A_REWORK_REQUIRED";
  gate_05b_contract: Record<string, unknown>;
};

export type ProjectPreview = {
  allowed: boolean;
  parent: ProjectParentOption;
  template_code: string;
  projected_record_code: string;
  projected_project_number: string;
  inherited_classifications: Array<{
    category_set_code: string;
    category_item_code: string;
    source: string;
  }>;
  enabled_modules: string[];
  initial_status: string;
  issues: string[];
  persisted: false;
};

export type PhysicalParentOption = {
  id: number;
  name: string;
  workspace_type_code: string;
  record_code: string;
  status: string;
};

export type PhysicalConfiguration = {
  workspace_types: ConfigurationVersion[];
  composition_rules: Record<string, string[]>;
  templates: ConfigurationVersion[];
  numbering_rules: ConfigurationVersion[];
  creation_policies: ConfigurationVersion[];
  available_modules: ConfigurationVersion[];
  parent_options: PhysicalParentOption[];
  relationship_contract: Array<{ source: string; target: string; relationship_type: string }>;
  summary: Record<string, number>;
  gate_status: "READY_FOR_PHYSICAL_WORKSPACE_CREATION_PROCESSES" | "GATE06A_REWORK_REQUIRED";
  exclusions: Record<string, unknown>;
};

export type PhysicalPreview = {
  allowed: boolean;
  workspace_type_code: string;
  parent: PhysicalParentOption;
  template_code: string | null;
  projected_record_code: string;
  projected_business_number: string | null;
  applicable_classifications: string[];
  enabled_modules: string[];
  planned_modules: string[];
  initial_status: string;
  issues: string[];
  warnings: string[];
  persisted: false;
};

export type PhysicalWorkspaceCreationState = ProjectCreationState;

export type PhysicalClassificationValue = {
  category_set_code: string;
  category_item_code: string;
};

export type PhysicalWorkspaceRequestPayload = {
  workspace_type_code: "property" | "facility" | "warehouse";
  parent_workspace_id: number;
  template_config_id: number;
  workspace_name: string;
  description: string;
  responsible_user_id: number;
  attributes: Record<string, unknown>;
  classifications: PhysicalClassificationValue[];
};

export type PhysicalWorkspaceCreationRequest = PhysicalWorkspaceRequestPayload & {
  id: number;
  request_number: string;
  state: PhysicalWorkspaceCreationState;
  requestor_user_id: number;
  requestor_name: string;
  parent_name: string;
  parent_record_code: string;
  template_code: string;
  template_name: string;
  responsible_name: string;
  revision_version: number;
  decision_reason: string | null;
  failure_reason: string | null;
  approved_by_user_id: number | null;
  materialized_workspace_id: number | null;
  materialized_business_number: string | null;
  materialized_record_code: string | null;
  created_at: string;
  updated_at: string;
};

export type PhysicalWorkspaceCreationOptions = {
  workspace_types: Array<{ code: "property" | "facility" | "warehouse"; name: string; domain_description: string }>;
  selected_workspace_type: string | null;
  locations: Array<{
    id: number;
    workspace_type_code: string;
    name: string;
    record_code: string;
    path: string[];
  }>;
  templates: Array<{
    id: number;
    code: string;
    name: string;
    workspace_type_code: string;
    applicable_parent_types: string[];
    enabled_modules: string[];
  }>;
  responsibles: Array<{ id: number; name: string; email: string }>;
  dynamic_attributes: Array<{
    code: string;
    label: string;
    input_type: string;
    required: boolean;
    read_only: boolean;
    options: CategoryItem[];
  }>;
  classifications: Record<string, CategoryItem[]>;
  creation_policy: Record<string, unknown> | null;
  blocked_reason: string | null;
};

export type PhysicalWorkspaceRequestPreview = {
  allowed: boolean;
  issues: string[];
  warnings: string[];
  workspace_type: Record<string, unknown>;
  parent: Record<string, unknown>;
  parent_record_code: string;
  projected_record_code: string;
  projected_business_number: string;
  template: Record<string, unknown>;
  creation_policy: Record<string, unknown>;
  applicable_classifications: string[];
  selected_classifications: PhysicalClassificationValue[];
  enabled_modules: string[];
  planned_modules: string[];
  initial_workspace_status: string;
  persisted: false;
};

export type PhysicalWorkspaceOverview = {
  workspace_id: number;
  workspace_type_code: "property" | "facility" | "warehouse";
  workspace_name: string;
  business_number: string;
  record_code: string;
  status: string;
  parent_workspace: string;
  responsible: string;
  template: string;
  creation_request_id: number | null;
  creation_request_number: string;
  created_at: string;
  attributes: Record<string, unknown>;
  classifications: PhysicalClassificationValue[];
  enabled_modules: string[];
  planned_modules: string[];
  initialization_state: ProjectWorkspaceInitializationState;
  initialization_progress_percent: number;
  initialization_blocker_count: number;
  initialization_warning_count: number;
  blocking_issues: string[];
  warnings: string[];
  template_revision: number | null;
  module_states: Record<string, PhysicalWorkspaceModuleReadiness>;
  activated_at: string | null;
  activated_by_user_id: number | null;
  initialization_revision_version: number;
  can_initialize: boolean;
  can_activate: boolean;
};

export type PhysicalWorkspaceModuleReadiness = {
  module_key: string;
  state: string;
  operational_module_created: boolean;
  planned: boolean;
  evidence: Record<string, unknown>;
};

export type PhysicalWorkspaceInitialization = {
  result: string;
  persisted: boolean;
  initialization_id: number | null;
  workspace_id: number;
  workspace_type_code: "property" | "facility" | "warehouse";
  workspace_name: string;
  workspace_status: string;
  business_number: string;
  record_code: string;
  external_key: string;
  parent: string;
  responsible: string;
  state: ProjectWorkspaceInitializationState;
  progress_percent: number;
  blocker_count: number;
  warning_count: number;
  common_checklist: ProjectWorkspaceChecklistItem[];
  type_specific_checklist: ProjectWorkspaceChecklistItem[];
  template_config_id: number | null;
  template_code: string;
  template_revision: number | null;
  template_content_hash: string;
  attributes: Record<string, unknown>;
  classifications: PhysicalClassificationValue[];
  enabled_modules: string[];
  planned_modules: string[];
  modules: PhysicalWorkspaceModuleReadiness[];
  defaults_applied: Record<string, unknown>;
  assignments: Array<Record<string, unknown>>;
  validation_hash: string | null;
  checklist_hash: string | null;
  revision_version: number;
  started_at: string | null;
  ready_at: string | null;
  activated_at: string | null;
  activated_by_user_id: number | null;
  failure_code: string | null;
  failure_reason: string | null;
  mutation_count: number;
};

export type PhysicalWorkspaceListItem = {
  workspace_id: number;
  workspace_type_code: "property" | "facility" | "warehouse";
  workspace_name: string;
  business_number: string;
  record_code: string;
  workspace_status: string;
  initialization_state: ProjectWorkspaceInitializationState;
  parent: string;
  responsible: string;
  template_code: string;
  blocker_count: number;
  warning_count: number;
  revision_version: number;
  can_initialize: boolean;
  can_activate: boolean;
};

export type ProjectTemplatePayload = {
  code: string;
  name: string;
  description: string;
  applicable_parent_types: string[];
  default_classifications: Array<{ category_set_code: string; category_item_code: string }>;
  enabled_modules: string[];
  default_role_codes: string[];
  default_group_codes: string[];
  numbering_rule_code: string;
  default_attributes: Record<string, unknown>;
  creation_policy_code: string;
};

export type ProjectCreationState =
  | "draft"
  | "submitted"
  | "under_review"
  | "returned"
  | "rejected"
  | "approved"
  | "materializing"
  | "created"
  | "failed"
  | "cancelled";

export type ProjectRequestPayload = {
  parent_workspace_id: number;
  project_template_config_id: number;
  project_name: string;
  description: string;
  project_manager_user_id: number;
  planned_start: string | null;
  planned_finish: string | null;
  currency_code: string;
  estimated_budget: string | null;
  project_type: string | null;
  project_phase: string | null;
  priority: string | null;
  country: string | null;
  region: string | null;
  strategic_objective_codes: string[];
};

export type ProjectCreationRequest = ProjectRequestPayload & {
  id: number;
  request_number: string;
  state: ProjectCreationState;
  requestor_user_id: number;
  requestor_name: string;
  parent_name: string;
  parent_record_code: string;
  template_code: string;
  template_name: string;
  project_manager_name: string;
  revision_version: number;
  decision_reason: string | null;
  failure_reason: string | null;
  approved_by_user_id: number | null;
  materialized_workspace_id: number | null;
  materialized_project_number: string | null;
  materialized_record_code: string | null;
  created_at: string;
  updated_at: string;
};

export type ProjectLocationOption = {
  id: number;
  workspace_type_code: "portfolio" | "program";
  name: string;
  record_code: string;
  path: string[];
};

export type ProjectCreationOptions = {
  locations: ProjectLocationOption[];
  templates: Array<{
    id: number;
    code: string;
    name: string;
    applicable_parent_types: string[];
    enabled_modules: string[];
  }>;
  managers: Array<{ id: number; name: string; email: string }>;
  strategic_objectives: CategoryItem[];
  classifications: Record<string, CategoryItem[]>;
  blocked_reason: string | null;
};

export type ProjectRequestPreview = {
  allowed: boolean;
  issues: string[];
  parent_workspace_id: number;
  parent_name: string;
  parent_record_code: string;
  projected_record_code: string;
  projected_project_number: string;
  inherited_classifications: Array<Record<string, string>>;
  selected_classifications: Array<Record<string, string>>;
  enabled_modules: string[];
  initial_workspace_status: string;
  template: Record<string, unknown>;
  creation_policy: Record<string, unknown>;
  persisted: false;
  notice: string;
};

export type ProjectWorkspaceOverview = {
  workspace_id: number;
  project_name: string;
  project_number: string;
  record_code: string;
  status: string;
  parent_workspace: string;
  project_manager: string;
  template: string;
  strategic_objectives: string[];
  planned_start: string | null;
  planned_finish: string | null;
  currency: string;
  estimated_budget: string | null;
  enabled_modules: string[];
  initialization_state: ProjectWorkspaceInitializationState;
  initialization_progress_percent: number;
  initialization_blocker_count: number;
  initialization_warning_count: number;
  blocking_issues: string[];
  warnings: string[];
  template_revision: number | null;
  module_states: Record<string, string>;
  activated_at: string | null;
  activated_by_user_id: number | null;
  initialization_revision_version: number;
  can_initialize: boolean;
  can_activate: boolean;
};

export type ProjectWorkspaceInitializationState =
  | "NOT_STARTED"
  | "INITIALIZING"
  | "BLOCKED"
  | "READY_FOR_ACTIVATION"
  | "ACTIVATED"
  | "FAILED";

export type ProjectWorkspaceChecklistItem = {
  code: string;
  status: "PASS" | "FAIL" | "WARNING";
  message: string;
  blocking: boolean;
  evidence: Record<string, unknown>;
};

export type ProjectWorkspaceInitialization = {
  result: string;
  persisted: boolean;
  initialization_id: number | null;
  workspace_id: number;
  workspace_status: string;
  state: ProjectWorkspaceInitializationState;
  progress_percent: number;
  blocker_count: number;
  warning_count: number;
  checklist: ProjectWorkspaceChecklistItem[];
  template_config_id: number | null;
  template_code: string;
  template_revision: number | null;
  modules: Array<{
    module_key: string;
    state: string;
    configuration_container: string;
    evidence: Record<string, unknown>;
  }>;
  defaults_applied: Record<string, unknown>;
  assignments: Array<Record<string, unknown>>;
  validation_hash: string | null;
  checklist_hash: string | null;
  revision_version: number;
  started_at: string | null;
  ready_at: string | null;
  activated_at: string | null;
  activated_by_user_id: number | null;
  failure_code: string | null;
  failure_reason: string | null;
  mutation_count: number;
};

export type ProjectWorkspaceListItem = {
  workspace_id: number;
  project_name: string;
  project_number: string;
  record_code: string;
  workspace_status: string;
  initialization_state: ProjectWorkspaceInitializationState;
  template_code: string;
  project_manager: string;
  blocker_count: number;
  warning_count: number;
  revision_version: number;
  can_initialize: boolean;
  can_activate: boolean;
};
