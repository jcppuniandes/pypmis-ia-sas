export type ConfigurationVersion = {
  id: number;
  kind: string;
  code: string;
  name: string;
  description: string;
  status: "draft" | "published";
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

export type EnterpriseStructureConfiguration = {
  workspace_types: ConfigurationVersion[];
  categories: ConfigurationVersion[];
  composition_rules: CompositionRule[];
  drafts: ConfigurationVersion[];
  tree: EnterpriseTreeNode[];
  classifications: Classification[];
  links: WorkspaceLink[];
  summary: Record<string, number>;
};

export type EnterpriseExplorer = {
  tree: EnterpriseTreeNode[];
  nodes: EnterpriseNode[];
  workspace_types: ConfigurationVersion[];
  objectives: CategoryItem[];
  classifications: Classification[];
  links: WorkspaceLink[];
  summary: Record<string, number>;
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
