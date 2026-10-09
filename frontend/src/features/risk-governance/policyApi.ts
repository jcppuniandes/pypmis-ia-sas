import { apiFetch } from "../../api/client";
import { createIdempotencyKey } from "../capital-planning/api";

export type JsonRecord = Record<string, unknown>;
export type GovernanceConfiguration = {
  id: number;
  code: string;
  name: string;
  description: string;
  status: string;
  revision: number;
  version: number;
  content_hash: string | null;
  content_json: JsonRecord;
  allowed_actions?: string[];
};

export function governancePolicyApi(root: string) {
  const versionHeaders = (item: GovernanceConfiguration) => ({
    "If-Match": `"${item.version}"`,
    "Idempotency-Key": createIdempotencyKey(),
  });
  return {
    configurations: (token: string) => apiFetch<GovernanceConfiguration[]>(`${root}/admin/configurations`, { token }),
    clone: (token: string, item: GovernanceConfiguration, targetWorkspaceId: number | null) =>
      apiFetch<GovernanceConfiguration>(`${root}/admin/configurations/${item.id}/clone`, {
        method: "POST",
        token,
        headers: versionHeaders(item),
        body: JSON.stringify(targetWorkspaceId === null ? {} : { target_workspace_id: targetWorkspaceId }),
      }),
    update: (token: string, item: GovernanceConfiguration, content: JsonRecord) =>
      apiFetch<GovernanceConfiguration>(`${root}/admin/configurations/${item.id}`, {
        method: "PUT",
        token,
        headers: versionHeaders(item),
        body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
      }),
    publish: (token: string, item: GovernanceConfiguration) =>
      apiFetch<GovernanceConfiguration>(`${root}/admin/configurations/${item.id}/publish`, {
        method: "POST",
        token,
        headers: versionHeaders(item),
      }),
    archive: (token: string, item: GovernanceConfiguration) =>
      apiFetch<GovernanceConfiguration>(`${root}/admin/configurations/${item.id}/archive`, {
        method: "POST",
        token,
        headers: versionHeaders(item),
      }),
    preview: (token: string, body: JsonRecord) =>
      apiFetch<JsonRecord>(`${root}/admin/preview`, { method: "POST", token, body: JSON.stringify(body) }),
  };
}

export const riskGovernanceApi = {
  ...governancePolicyApi("/api/v1/risk-governance"),
  effective: (token: string, workspaceId: number) =>
    apiFetch<JsonRecord>(`/api/v1/risk-governance/effective?workspace_id=${workspaceId}`, { token }),
};
