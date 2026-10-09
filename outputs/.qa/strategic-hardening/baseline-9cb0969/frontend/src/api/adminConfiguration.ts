import { apiFetch } from "./client";
import type {
  AdminConfigurationKind,
  AdminConfigurationOverview,
  AdminConfigurationRecord,
  EnterpriseWorkspace,
  NumberingResult,
  WorkspaceEffectiveConfiguration,
  WorkspaceModuleSetting,
} from "../types";

const root = "/api/v1/admin-configuration";

export const adminConfiguration = {
  overview: (token: string) => apiFetch<AdminConfigurationOverview>(`${root}/overview`, { token }),

  createConfiguration: (
    token: string,
    data: {
      kind: AdminConfigurationKind;
      code: string;
      name: string;
      description: string;
      content_json: Record<string, unknown>;
    }
  ) =>
    apiFetch<AdminConfigurationRecord>(`${root}/configurations`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  publishConfiguration: (token: string, configurationId: number) =>
    apiFetch<AdminConfigurationRecord>(`${root}/configurations/${configurationId}/publish`, {
      method: "POST",
      token,
    }),

  cloneConfiguration: (token: string, configurationId: number) =>
    apiFetch<AdminConfigurationRecord>(`${root}/configurations/${configurationId}/clone`, {
      method: "POST",
      token,
    }),

  createWorkspace: (
    token: string,
    data: { code: string; name: string; workspace_type_code: string; parent_id: number | null }
  ) =>
    apiFetch<EnterpriseWorkspace>(`${root}/workspaces`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  updateWorkspaceDefaults: (
    token: string,
    workspaceId: number,
    data: { values: Record<string, unknown>; expected_version: number }
  ) =>
    apiFetch<EnterpriseWorkspace>(`${root}/workspaces/${workspaceId}/defaults`, {
      method: "PUT",
      token,
      body: JSON.stringify(data),
    }),

  setWorkspaceModule: (
    token: string,
    workspaceId: number,
    moduleKey: string,
    data: { enabled: boolean; expected_version?: number }
  ) =>
    apiFetch<WorkspaceModuleSetting>(`${root}/workspaces/${workspaceId}/modules/${moduleKey}`, {
      method: "PUT",
      token,
      body: JSON.stringify(data),
    }),

  effectiveWorkspace: (token: string, workspaceId: number) =>
    apiFetch<WorkspaceEffectiveConfiguration>(`${root}/workspaces/${workspaceId}/effective`, { token }),

  previewNumber: (token: string, ruleCode: string, scopeKey: string) =>
    apiFetch<NumberingResult>(`${root}/numbering/${ruleCode}/preview`, {
      method: "POST",
      token,
      body: JSON.stringify({ scope_key: scopeKey }),
    }),

  issueNumber: (token: string, ruleCode: string, scopeKey: string) =>
    apiFetch<NumberingResult>(`${root}/numbering/${ruleCode}/next`, {
      method: "POST",
      token,
      body: JSON.stringify({ scope_key: scopeKey }),
    }),
};
