export type WorkspaceIdentity = {
  tenant_id: number;
  workspace_id: number;
  workspace_type: "PROJECT" | "PROPERTY" | "FACILITY" | "WAREHOUSE";
  workspace_name: string;
  workspace_status: string;
  business_number: string;
  record_code: string;
  external_key: string;
};

export type WorkspaceReference = {
  workspace_id: number;
  workspace_type: string;
  workspace_name: string;
  business_number: string;
  record_code: string;
  status: string;
  navigable: boolean;
};

export type WorkspaceNavigatorItem = {
  code: string;
  label: string;
  route: string;
  state: "READY" | "PLANNED" | "DISABLED" | "HIDDEN";
  permission_key: string;
  read_only: boolean;
  reason: string;
};

export type WorkspaceContext = {
  active_context: {
    tenant_id: number;
    workspace_id: number;
    workspace_type: string;
    workspace_name: string;
    workspace_status: string;
    business_number: string;
    record_code: string;
    external_key: string;
    parent_workspace_id: number | null;
    parent_path: number[];
    template_code: string;
    template_revision: number | null;
    responsible_user_id: number | null;
    enabled_modules: string[];
    planned_modules: string[];
    workspace_permissions: string[];
    opened_at: string | null;
    last_route: string;
  };
  identity: WorkspaceIdentity;
  parent: WorkspaceReference | null;
  breadcrumb: WorkspaceReference[];
  template: { code: string; revision: number | null; content_hash: string };
  responsible: { user_id: number | null; name: string; email: string };
  enabled_modules: string[];
  planned_modules: string[];
  navigator: WorkspaceNavigatorItem[];
  permissions: Record<string, boolean>;
  allowed_actions: string[];
  home_configuration: Record<string, unknown>;
  version: number;
  etag: string;
};

export type WorkspaceHome = {
  workspace: WorkspaceIdentity;
  breadcrumb: WorkspaceReference[];
  responsible: WorkspaceContext["responsible"];
  status: string;
  enabled_modules: string[];
  planned_modules: string[];
  recent_activity: Array<Record<string, unknown>>;
  recent_documents: Array<Record<string, unknown>>;
  my_tasks: Array<Record<string, unknown>>;
  related_workspaces: WorkspaceReference[];
  allowed_actions: string[];
  capability_flags: Record<string, boolean>;
};

export type RecentWorkspace = {
  workspace_id: number;
  workspace_name: string;
  workspace_type: string;
  business_number: string;
  status: string;
  last_opened_at: string;
  last_route: string;
};

export type MyWorkspace = {
  workspace_id: number;
  workspace_name: string;
  workspace_type: string;
  business_number: string;
  record_code: string;
  status: string;
  responsible: string;
  parent: string;
  last_route: string;
};
