import { apiFetch } from "../../api/client";
import type {
  PortfolioIntakeReadiness,
  StrategicGateDecision,
  StrategicGateDraft,
  StrategicGateOptions,
  StrategicGateOutcome,
  StrategicGatePreview,
} from "./types";

const root = "/api/v1/strategic-gate-decisions";
const mutationHeaders = (item: StrategicGateDecision, key: string) => ({
  "If-Match": `"${item.revision_version}"`,
  "Idempotency-Key": `${key}-${item.id}-${item.revision_version}`,
});

export const strategicGateApi = {
  options: (token: string) => apiFetch<StrategicGateOptions>(`${root}/options`, { token }),
  list: (token: string, query = "") =>
    apiFetch<StrategicGateDecision[]>(`${root}${query ? `?${query}` : ""}`, { token }),
  get: (token: string, id: number) => apiFetch<StrategicGateDecision>(`${root}/${id}`, { token }),
  preview: (token: string, proposalId: number) =>
    apiFetch<StrategicGatePreview>(`${root}/preview`, {
      method: "POST",
      token,
      body: JSON.stringify({ project_proposal_id: proposalId }),
    }),
  previewFromProposal: (token: string, proposalId: number) =>
    apiFetch<StrategicGatePreview>(`/api/v1/project-proposals/${proposalId}/strategic-gate-decisions/preview`, {
      method: "POST",
      token,
    }),
  create: (token: string, proposalId: number) =>
    apiFetch<StrategicGateDecision>(root, {
      method: "POST",
      token,
      headers: { "Idempotency-Key": `create-proposal-${proposalId}` },
      body: JSON.stringify({ project_proposal_id: proposalId }),
    }),
  update: (token: string, item: StrategicGateDecision, payload: StrategicGateDraft) =>
    apiFetch<StrategicGateDecision>(`${root}/${item.id}`, {
      method: "PUT",
      token,
      headers: mutationHeaders(item, "update"),
      body: JSON.stringify(payload),
    }),
  action: (token: string, item: StrategicGateDecision, action: string, body?: unknown) =>
    apiFetch<StrategicGateDecision>(`${root}/${item.id}/${action}`, {
      method: "POST",
      token,
      headers: mutationHeaders(item, action),
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  decide: (
    token: string,
    item: StrategicGateDecision,
    outcome: StrategicGateOutcome,
    reason: string,
    comments: string,
    conditions: Array<Record<string, unknown>>,
    deferredUntil?: string
  ) =>
    apiFetch<StrategicGateDecision>(`${root}/${item.id}/decide`, {
      method: "POST",
      token,
      headers: mutationHeaders(item, `decide-${outcome}`),
      body: JSON.stringify({
        outcome,
        reason,
        comments,
        conditions,
        deferred_until: outcome === "DEFER" ? deferredUntil || null : null,
      }),
    }),
  history: (token: string, id: number) => apiFetch<Array<Record<string, unknown>>>(`${root}/${id}/history`, { token }),
  readiness: (token: string, id: number) =>
    apiFetch<PortfolioIntakeReadiness>(`${root}/${id}/portfolio-intake-readiness`, { token }),
  relatedToProposal: (token: string, proposalId: number) =>
    apiFetch<StrategicGateDecision[]>(`/api/v1/project-proposals/${proposalId}/strategic-gate-decisions`, {
      token,
    }),
  relatedToIdea: (token: string, ideaId: number) =>
    apiFetch<StrategicGateDecision[]>(`/api/v1/ideas/${ideaId}/strategic-gate-decisions`, { token }),
  configurations: (token: string) =>
    apiFetch<Array<Record<string, unknown>>>(`${root}/admin/configurations/list`, { token }),
  previewConfiguration: (token: string, proposalId: number) =>
    apiFetch<Record<string, unknown>>(`${root}/admin/configuration/preview`, {
      method: "POST",
      token,
      body: JSON.stringify({ project_proposal_id: proposalId }),
    }),
  cloneConfiguration: (token: string, item: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>(`${root}/admin/configurations/${String(item.id)}/clone`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${Number(item.version)}"` },
    }),
  updateConfiguration: (token: string, item: Record<string, unknown>, content: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>(`${root}/admin/configurations/${String(item.id)}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${Number(item.version)}"` },
      body: JSON.stringify({
        name: item.name,
        description: item.description || "",
        content_json: content,
      }),
    }),
  publishConfiguration: (token: string, item: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>(`${root}/admin/configurations/${String(item.id)}/publish`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${Number(item.version)}"` },
    }),
};
