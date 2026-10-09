import { apiFetch, apiFetchWithResponse } from "../../api/client";
import type {
  CommercialContractingStrategy,
  CommercialRefreshPreview,
  CommercialStrategyConfiguration,
  CommercialStrategyContent,
  CommercialStrategyHistory,
  CommercialStrategyOptions,
  CommercialStrategyQueue,
  CommercialStrategyReadiness,
  CommercialStrategyVersion,
} from "./types";

const root = "/api/v1/commercial-strategies";
const versionHeaders = (version: number) => ({ "If-Match": `"${version}"` });
const idempotencyHeaders = () => ({ "Idempotency-Key": crypto.randomUUID() });

export type CommercialStrategyPage = {
  items: CommercialContractingStrategy[];
  nextCursor: string | null;
  pageLimit: number;
  resultCount: number;
};

type ListQuery = {
  queue?: CommercialStrategyQueue;
  projectWorkspaceId?: number;
  search?: string;
  cursor?: string | null;
  limit?: number;
};

function queryString(query: ListQuery) {
  const params = new URLSearchParams();
  if (query.queue) params.set("queue", query.queue);
  if (query.projectWorkspaceId) params.set("project_workspace_id", String(query.projectWorkspaceId));
  if (query.search) params.set("search", query.search);
  if (query.cursor) params.set("cursor", query.cursor);
  params.set("limit", String(query.limit ?? 50));
  return params.toString();
}

function itemsFromResponse(data: CommercialContractingStrategy[] | { items: CommercialContractingStrategy[] }) {
  return Array.isArray(data) ? data : data.items;
}

export const commercialStrategyApi = {
  options: (token: string, projectWorkspaceId?: number) =>
    apiFetch<CommercialStrategyOptions>(
      `${root}/options${projectWorkspaceId ? `?project_workspace_id=${projectWorkspaceId}` : ""}`,
      { token }
    ),
  listPage: async (token: string, query: ListQuery = {}): Promise<CommercialStrategyPage> => {
    const result = await apiFetchWithResponse<
      CommercialContractingStrategy[] | { items: CommercialContractingStrategy[] }
    >(`${root}?${queryString(query)}`, { token });
    const items = itemsFromResponse(result.data);
    return {
      items,
      nextCursor: result.response.headers?.get("X-Next-Cursor") ?? null,
      pageLimit: Number(result.response.headers?.get("X-Page-Limit") || query.limit || 50),
      resultCount: Number(result.response.headers?.get("X-Result-Count") || items.length),
    };
  },
  detail: (token: string, strategyId: number) =>
    apiFetch<CommercialContractingStrategy>(`${root}/${strategyId}`, { token }),
  byProject: (token: string, projectWorkspaceId: number) =>
    apiFetch<CommercialContractingStrategy>(`/api/v1/projects/${projectWorkspaceId}/commercial-strategy`, { token }),
  create: (token: string, projectWorkspaceId: number, versionPurpose: string) =>
    apiFetch<CommercialContractingStrategy>(root, {
      method: "POST",
      token,
      headers: idempotencyHeaders(),
      body: JSON.stringify({ project_workspace_id: projectWorkspaceId, version_purpose: versionPurpose }),
    }),
  update: (
    token: string,
    strategy: CommercialContractingStrategy,
    version: CommercialStrategyVersion,
    content: CommercialStrategyContent,
    felStageCode?: string | null,
    reviewerUserId?: number | null
  ) =>
    apiFetch<CommercialStrategyVersion>(`${root}/${strategy.id}/versions/${version.id}`, {
      method: "PUT",
      token,
      headers: versionHeaders(version.revision_version),
      body: JSON.stringify({
        content_json: content,
        fel_stage_code: felStageCode || null,
        reviewer_user_id: reviewerUserId || null,
      }),
    }),
  lifecycle: (
    token: string,
    strategy: CommercialContractingStrategy,
    version: CommercialStrategyVersion,
    action: "submit" | "start-review" | "return" | "complete" | "void",
    reason?: string
  ) =>
    apiFetch<CommercialStrategyVersion>(`${root}/${strategy.id}/versions/${version.id}/${action}`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(version.revision_version), ...idempotencyHeaders() },
      body: reason ? JSON.stringify({ reason }) : undefined,
    }),
  newRevision: (token: string, strategy: CommercialContractingStrategy, versionPurpose: string) =>
    apiFetch<CommercialStrategyVersion>(`${root}/${strategy.id}/new-revision`, {
      method: "POST",
      token,
      headers: idempotencyHeaders(),
      body: JSON.stringify({ version_purpose: versionPurpose }),
    }),
  readiness: (token: string, strategyId: number) =>
    apiFetch<CommercialStrategyReadiness>(`${root}/${strategyId}/readiness`, { token }),
  history: (token: string, strategyId: number) =>
    apiFetch<CommercialStrategyHistory[]>(`${root}/${strategyId}/history`, { token }),
  refreshPreview: (token: string, strategyId: number) =>
    apiFetch<CommercialRefreshPreview>(`${root}/${strategyId}/refresh-preview`, {
      method: "POST",
      token,
      headers: idempotencyHeaders(),
    }),
  refreshApply: (token: string, strategy: CommercialContractingStrategy) =>
    apiFetch<CommercialStrategyVersion>(`${root}/${strategy.id}/refresh-apply`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(strategy.revision_version), ...idempotencyHeaders() },
    }),
  providerEvidence: (token: string, projectWorkspaceId: number) =>
    apiFetch<Record<string, unknown>>(`/api/v1/projects/${projectWorkspaceId}/commercial-readiness-evidence`, {
      token,
    }),
  configurations: (token: string) =>
    apiFetch<CommercialStrategyConfiguration[]>(`${root}/admin/configurations`, { token }),
  effectivePreview: (
    token: string,
    projectWorkspaceId: number,
    configurationId?: number,
    content?: Record<string, unknown>
  ) =>
    apiFetch<Record<string, unknown>>(`${root}/admin/configurations/effective-preview`, {
      method: "POST",
      token,
      body: JSON.stringify({
        project_workspace_id: projectWorkspaceId || null,
        configuration_id: configurationId || null,
        content_json: content || null,
      }),
    }),
  cloneConfiguration: (token: string, item: CommercialStrategyConfiguration) =>
    apiFetch<CommercialStrategyConfiguration>(`${root}/admin/configurations/${item.id}/clone`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(item.version), ...idempotencyHeaders() },
    }),
  updateConfiguration: (token: string, item: CommercialStrategyConfiguration, content: Record<string, unknown>) =>
    apiFetch<CommercialStrategyConfiguration>(`${root}/admin/configurations/${item.id}`, {
      method: "PUT",
      token,
      headers: versionHeaders(item.version),
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: CommercialStrategyConfiguration) =>
    apiFetch<CommercialStrategyConfiguration>(`${root}/admin/configurations/${item.id}/publish`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(item.version), ...idempotencyHeaders() },
    }),
  archiveConfiguration: (token: string, item: CommercialStrategyConfiguration) =>
    apiFetch<CommercialStrategyConfiguration>(`${root}/admin/configurations/${item.id}/archive`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(item.version), ...idempotencyHeaders() },
    }),
};
