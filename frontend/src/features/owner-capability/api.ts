import { apiFetch } from "../../api/client";
import { createIdempotencyKey } from "../capital-planning/api";
import { governancePolicyApi, type JsonRecord } from "../risk-governance/policyApi";

export type OwnerCapabilityPage<T> = { items: T[]; total: number; page: number; page_size: number };
export type OwnerCapabilityAssessment = JsonRecord & {
  id: number;
  assessment_number: string;
  assessment_version: number;
  status: string;
  revision_version: number;
  assessment_hash: string | null;
  aggregate_json: { items: JsonRecord[]; gaps: JsonRecord[]; mitigations: JsonRecord[] };
  snapshot_json: JsonRecord;
  allowed_actions: string[];
};
export type OwnerCapabilityOptions = {
  projects: Array<{ id: number; code: string; name: string }>;
  project_total?: number;
  page?: number;
  page_size?: number;
  quality_values?: string[];
  confidence_values?: string[];
  allowed_actions?: string[];
};
const root = "/api/v1/owner-capability";
function commandHeaders(version?: number) {
  return {
    "Idempotency-Key": createIdempotencyKey(),
    ...(version == null ? {} : { "If-Match": `"${version}"` }),
  };
}
export const ownerCapabilityApi = {
  ...governancePolicyApi(root),
  options: (token: string, search = "", page = 1) =>
    apiFetch<OwnerCapabilityOptions>(
      `${root}/options?page=${page}&page_size=100&search=${encodeURIComponent(search)}`,
      {
        token,
      }
    ),
  requirements: (token: string, projectId: number) =>
    apiFetch<JsonRecord>(`${root}/projects/${projectId}/requirements`, { token }),
  contexts: (token: string, projectId: number) =>
    apiFetch<JsonRecord>(`${root}/projects/${projectId}/contexts`, { token }),
  assessments: (token: string, projectId: number, page = 1) =>
    apiFetch<OwnerCapabilityPage<OwnerCapabilityAssessment>>(
      `${root}/projects/${projectId}/assessments?page=${page}&page_size=25`,
      { token }
    ),
  assessment: (token: string, id: number) =>
    apiFetch<OwnerCapabilityAssessment>(`${root}/assessments/${id}`, { token }),
  currentReadiness: (token: string, projectId: number) =>
    apiFetch<JsonRecord>(`${root}/projects/${projectId}/current-readiness`, { token }),
  createAssessment: (token: string, projectId: number) =>
    apiFetch<OwnerCapabilityAssessment>(`${root}/projects/${projectId}/assessments`, {
      method: "POST",
      token,
      headers: commandHeaders(),
      body: JSON.stringify({ title: "Owner Capability assessment", comments: "Owner-side organizational capability." }),
    }),
  updateAssessment: (token: string, item: OwnerCapabilityAssessment, body: JsonRecord) =>
    apiFetch<OwnerCapabilityAssessment>(`${root}/assessments/${item.id}`, {
      method: "PUT",
      token,
      headers: commandHeaders(item.revision_version),
      body: JSON.stringify(body),
    }),
  assessmentAction: (
    token: string,
    item: OwnerCapabilityAssessment,
    action: "preview" | "submit" | "review" | "complete" | "refresh-apply"
  ) =>
    apiFetch<JsonRecord>(`${root}/assessments/${item.id}/${action}`, {
      method: "POST",
      token,
      headers: commandHeaders(item.revision_version),
      body: JSON.stringify({ comments: "Reviewed against the captured Owner Capability framework." }),
    }),
  refreshPreview: (token: string, id: number) =>
    apiFetch<JsonRecord>(`${root}/assessments/${id}/refresh-preview`, { token }),
  createMitigation: (token: string, assessment: OwnerCapabilityAssessment, body: JsonRecord) =>
    apiFetch<OwnerCapabilityAssessment>(`${root}/assessments/${assessment.id}/mitigations`, {
      method: "POST",
      token,
      headers: commandHeaders(assessment.revision_version),
      body: JSON.stringify(body),
    }),
  updateMitigation: (token: string, assessment: OwnerCapabilityAssessment, id: string, body: JsonRecord) =>
    apiFetch<OwnerCapabilityAssessment>(`${root}/assessments/${assessment.id}/mitigations/${encodeURIComponent(id)}`, {
      method: "PUT",
      token,
      headers: commandHeaders(assessment.revision_version),
      body: JSON.stringify(body),
    }),
};
