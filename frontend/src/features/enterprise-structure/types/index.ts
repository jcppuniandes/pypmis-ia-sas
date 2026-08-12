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
