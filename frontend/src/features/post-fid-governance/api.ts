import { apiFetch } from "../../api/client";
import type { PostFIDConfiguration, PostFIDDecision, PostFIDEligibility, RefreshPreview } from "./types";

const key = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const postFIDGovernanceApi = {
  list: (token: string) => apiFetch<PostFIDDecision[]>("/api/v1/post-fid-governance", { token }),
  get: (token: string, decisionId: number) =>
    apiFetch<PostFIDDecision>(`/api/v1/post-fid-governance/${decisionId}`, { token }),
  evaluate: (token: string, decisionId: number, version = 1) =>
    apiFetch<PostFIDEligibility[]>(`/api/v1/post-fid-governance/${decisionId}/evaluate`, {
      token,
      method: "POST",
      headers: { "If-Match": `"${version}"` },
      body: JSON.stringify({ idempotency_key: key("post-fid-evaluate") }),
    }),
  previewRefresh: (token: string, decisionId: number) =>
    apiFetch<RefreshPreview>(`/api/v1/post-fid-governance/${decisionId}/refresh/preview`, {
      token,
      method: "POST",
      headers: { "Idempotency-Key": key("post-fid-preview") },
    }),
  refresh: (token: string, decisionId: number, version = 1) =>
    apiFetch<PostFIDEligibility[]>(`/api/v1/post-fid-governance/${decisionId}/refresh`, {
      token,
      method: "POST",
      headers: { "If-Match": `"${version}"` },
      body: JSON.stringify({ idempotency_key: key("post-fid-refresh") }),
    }),
  history: (token: string, decisionId: number) =>
    apiFetch<Array<Record<string, unknown>>>(`/api/v1/post-fid-governance/${decisionId}/history`, { token }),
  handoff: (token: string, item: PostFIDEligibility, kind: "initialization" | "activation") =>
    apiFetch<Record<string, unknown>>(
      `/api/v1/post-fid-governance/${item.investment_decision_id}/projects/${item.project_workspace_id}/${kind}-handoff`,
      { token, headers: { "Idempotency-Key": key(`post-fid-${kind}-handoff`) } }
    ),
  configurations: (token: string) =>
    apiFetch<PostFIDConfiguration[]>("/api/v1/post-fid-governance/admin/configurations", { token }),
  previewConfiguration: (
    token: string,
    configurationId: number,
    content: Record<string, unknown>,
    investmentDecisionId?: number
  ) =>
    apiFetch<Record<string, unknown>>("/api/v1/post-fid-governance/admin/configurations/preview", {
      token,
      method: "POST",
      body: JSON.stringify({
        configuration_id: configurationId,
        investment_decision_id: investmentDecisionId || null,
        content_json: content,
      }),
    }),
  cloneConfiguration: (token: string, item: PostFIDConfiguration) =>
    apiFetch<PostFIDConfiguration>(`/api/v1/post-fid-governance/admin/configurations/${item.id}/clone`, {
      token,
      method: "POST",
      headers: { "If-Match": `"${item.version}"` },
    }),
  updateConfiguration: (token: string, item: PostFIDConfiguration, content: Record<string, unknown>) =>
    apiFetch<PostFIDConfiguration>(`/api/v1/post-fid-governance/admin/configurations/${item.id}`, {
      token,
      method: "PUT",
      headers: { "If-Match": `"${item.version}"` },
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: PostFIDConfiguration) =>
    apiFetch<PostFIDConfiguration>(`/api/v1/post-fid-governance/admin/configurations/${item.id}/publish`, {
      token,
      method: "POST",
      headers: { "If-Match": `"${item.version}"` },
    }),
};
