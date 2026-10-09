import { apiFetch } from "../../api/client";
import { createIdempotencyKey } from "../capital-planning/api";
import { governancePolicyApi, type JsonRecord } from "../risk-governance/policyApi";

export type BasicDataItem = JsonRecord & {
  id: number;
  requirement_code: string;
  revision_version: number;
  availability: string;
  validation_state: string;
  quality: string;
  confidence: string;
  source_reference?: string | null;
};
export type BasicDataAssessment = JsonRecord & {
  id: number;
  assessment_number: string;
  assessment_version: number;
  status: string;
  revision_version: number;
  assessment_hash: string | null;
  snapshot_json: JsonRecord;
};
export type BasicDataOptions = {
  projects: Array<{ id: number; code: string; name: string }>;
  project_total?: number;
  page?: number;
  page_size?: number;
  quality_values: string[];
  confidence_values: string[];
  availability_values: string[];
  validation_values: string[];
  allowed_actions?: string[];
};
export type BasicDataPage<T> = { items: T[]; total: number; page: number; page_size: number };
const root = "/api/v1/basic-data";
function headers(version?: number) {
  return { "Idempotency-Key": createIdempotencyKey(), ...(version == null ? {} : { "If-Match": `"${version}"` }) };
}
export const basicDataApi = {
  ...governancePolicyApi(root),
  options: (token: string, search = "", page = 1) =>
    apiFetch<BasicDataOptions>(`${root}/options?page=${page}&page_size=100&search=${encodeURIComponent(search)}`, {
      token,
    }),
  requirements: (token: string, projectId: number) =>
    apiFetch<JsonRecord>(`${root}/projects/${projectId}/requirements`, { token }),
  items: (token: string, projectId: number, page = 1) =>
    apiFetch<BasicDataPage<BasicDataItem>>(`${root}/projects/${projectId}/items?page=${page}&page_size=25`, { token }),
  assessments: (token: string, projectId: number, page = 1) =>
    apiFetch<BasicDataPage<BasicDataAssessment>>(
      `${root}/projects/${projectId}/assessments?page=${page}&page_size=25`,
      { token }
    ),
  currentReadiness: (token: string, projectId: number) =>
    apiFetch<JsonRecord>(`${root}/projects/${projectId}/current-readiness`, { token }),
  createItem: (token: string, projectId: number, body: JsonRecord) =>
    apiFetch<BasicDataItem>(`${root}/projects/${projectId}/items`, {
      method: "POST",
      token,
      headers: headers(),
      body: JSON.stringify(body),
    }),
  updateItem: (token: string, item: BasicDataItem, body: JsonRecord) =>
    apiFetch<BasicDataItem>(`${root}/items/${item.id}`, {
      method: "PUT",
      token,
      headers: headers(item.revision_version),
      body: JSON.stringify(body),
    }),
  validateItem: (token: string, item: BasicDataItem, validationState = "VALIDATED") =>
    apiFetch<BasicDataItem>(`${root}/items/${item.id}/validate`, {
      method: "POST",
      token,
      headers: headers(item.revision_version),
      body: JSON.stringify({
        validation_state: validationState,
        comments: "Reviewed evidence reference and validation metadata.",
      }),
    }),
  createAssessment: (token: string, projectId: number) =>
    apiFetch<BasicDataAssessment>(`${root}/projects/${projectId}/assessments`, {
      method: "POST",
      token,
      headers: headers(),
      body: JSON.stringify({
        title: "Basic Data readiness assessment",
        comments: "Governed review of technical evidence.",
      }),
    }),
  assessment: (token: string, id: number) => apiFetch<BasicDataAssessment>(`${root}/assessments/${id}`, { token }),
  assessmentAction: (
    token: string,
    item: BasicDataAssessment,
    action: "preview" | "submit" | "complete" | "refresh-apply"
  ) =>
    apiFetch<JsonRecord>(`${root}/assessments/${item.id}/${action}`, {
      method: "POST",
      token,
      headers: headers(item.revision_version),
      body: JSON.stringify({ comments: "Reviewed against effective Basic Data policy." }),
    }),
  refreshPreview: (token: string, id: number) =>
    apiFetch<JsonRecord>(`${root}/assessments/${id}/refresh-preview`, { token }),
};
