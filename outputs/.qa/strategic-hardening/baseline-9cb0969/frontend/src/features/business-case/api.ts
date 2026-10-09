import { apiFetch } from "../../api/client";
import type {
  BusinessCase,
  BusinessCaseConfiguration,
  BusinessCaseRevision,
  DecisionSnapshot,
  Readiness,
  RefreshPreview,
} from "./types";

const key = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const businessCaseApi = {
  list: (token: string) => apiFetch<BusinessCase[]>("/api/v1/business-cases", { token }),
  create: (token: string, projectWorkspaceId: number, proposalId?: number) =>
    apiFetch<BusinessCase>("/api/v1/business-cases", {
      token,
      method: "POST",
      body: JSON.stringify({
        project_workspace_id: projectWorkspaceId,
        source_project_proposal_id: proposalId || null,
        idempotency_key: key("business-case-create"),
      }),
    }),
  revisions: (token: string, businessCaseId: number) =>
    apiFetch<BusinessCaseRevision[]>(`/api/v1/business-cases/${businessCaseId}/revisions`, { token }),
  updateRevision: (
    token: string,
    revision: BusinessCaseRevision,
    payload: Partial<{
      title: string;
      executive_summary: string;
      business_need: string;
      recommendation: Record<string, unknown>;
    }>
  ) =>
    apiFetch<BusinessCaseRevision>(`/api/v1/business-case-revisions/${revision.id}`, {
      token,
      method: "PUT",
      headers: { "If-Match": `"${revision.revision_version}"` },
      body: JSON.stringify(payload),
    }),
  submitReview: (token: string, revision: BusinessCaseRevision) =>
    apiFetch<BusinessCaseRevision>(`/api/v1/business-case-revisions/${revision.id}/submit-review`, {
      token,
      method: "POST",
      headers: { "If-Match": `"${revision.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("business-case-submit") }),
    }),
  complete: (token: string, revision: BusinessCaseRevision) =>
    apiFetch<BusinessCaseRevision>(`/api/v1/business-case-revisions/${revision.id}/complete`, {
      token,
      method: "POST",
      headers: { "If-Match": `"${revision.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("business-case-complete") }),
    }),
  createRevision: (token: string, businessCaseId: number, purpose: string) =>
    apiFetch<BusinessCaseRevision>(`/api/v1/business-cases/${businessCaseId}/revisions`, {
      token,
      method: "POST",
      body: JSON.stringify({ purpose, idempotency_key: key("business-case-revision") }),
    }),
  readiness: (token: string, businessCaseId: number) =>
    apiFetch<Readiness>(`/api/v1/business-cases/${businessCaseId}/readiness`, { token }),
  previewRefresh: (token: string, businessCaseId: number) =>
    apiFetch<RefreshPreview>(`/api/v1/business-cases/${businessCaseId}/refresh/preview`, {
      token,
      method: "POST",
      headers: { "Idempotency-Key": key("business-case-preview") },
    }),
  refresh: (token: string, item: BusinessCase) =>
    apiFetch<BusinessCaseRevision>(`/api/v1/business-cases/${item.id}/refresh`, {
      token,
      method: "POST",
      headers: { "If-Match": `"${item.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("business-case-refresh") }),
    }),
  snapshots: (token: string, businessCaseId: number) =>
    apiFetch<DecisionSnapshot[]>(`/api/v1/business-cases/${businessCaseId}/decision-snapshots`, { token }),
  createSnapshot: (token: string, item: BusinessCase, revision: BusinessCaseRevision) =>
    apiFetch<DecisionSnapshot>(`/api/v1/business-cases/${item.id}/decision-snapshots`, {
      token,
      method: "POST",
      body: JSON.stringify({
        business_case_revision_id: revision.id,
        snapshot_type: "OTHER_CONFIGURED_GATE",
        idempotency_key: key("business-case-snapshot"),
      }),
    }),
  configurations: (token: string) =>
    apiFetch<BusinessCaseConfiguration[]>("/api/v1/business-cases/admin/configurations", { token }),
  previewConfiguration: (
    token: string,
    configurationId: number,
    content: Record<string, unknown>,
    projectWorkspaceId?: number
  ) =>
    apiFetch<Record<string, unknown>>("/api/v1/business-cases/admin/configurations/preview", {
      token,
      method: "POST",
      body: JSON.stringify({
        project_workspace_id: projectWorkspaceId || null,
        configuration_id: configurationId,
        content_json: content,
      }),
    }),
  cloneConfiguration: (token: string, item: BusinessCaseConfiguration) =>
    apiFetch<BusinessCaseConfiguration>(`/api/v1/business-cases/admin/configurations/${item.id}/clone`, {
      token,
      method: "POST",
      headers: { "If-Match": `"${item.version}"` },
    }),
  updateConfiguration: (token: string, item: BusinessCaseConfiguration, content: Record<string, unknown>) =>
    apiFetch<BusinessCaseConfiguration>(`/api/v1/business-cases/admin/configurations/${item.id}`, {
      token,
      method: "PUT",
      headers: { "If-Match": `"${item.version}"` },
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: BusinessCaseConfiguration) =>
    apiFetch<BusinessCaseConfiguration>(`/api/v1/business-cases/admin/configurations/${item.id}/publish`, {
      token,
      method: "POST",
      headers: { "If-Match": `"${item.version}"` },
    }),
};
