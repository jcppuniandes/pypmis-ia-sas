import { apiFetch } from "../../api/client";
import { createIdempotencyKey } from "../capital-planning/api";
import { governancePolicyApi, type JsonRecord } from "../risk-governance/policyApi";

export type QraKind = "cost" | "schedule" | "model";
export type QraRecord = JsonRecord & {
  id: number;
  project_id: number;
  number: string;
  model_number?: string;
  version: number;
  title: string;
  status: string;
  revision_version: number;
  hash: string | null;
  aggregate_json: JsonRecord;
  snapshot_json: JsonRecord;
  allowed_actions: string[];
};
export type QraPage = { items: QraRecord[]; total: number; page: number; page_size: number };
export type QraItemPage = {
  items: JsonRecord[];
  total: number;
  page: number;
  page_size: number;
  hash?: string | null;
  historical?: boolean;
};
export type QraOptions = {
  projects: Array<{ id: number; code: string; name: string }>;
  project_total?: number;
  page?: number;
  page_size?: number;
  allowed_actions: string[];
  analysis_types: string[];
  quality_values?: string[];
  confidence_values?: string[];
};
export const QRA_API_ROOT = "/api/v1/qra-foundation";
const collection = (kind: QraKind) => (kind === "model" ? "models" : `${kind}-assessments`);
const headers = (item?: QraRecord) => ({
  "Idempotency-Key": createIdempotencyKey(),
  ...(item ? { "If-Match": `"${item.revision_version}"` } : {}),
});
export const qraFoundationApi = {
  ...governancePolicyApi(QRA_API_ROOT),
  options: (token: string, search = "", page = 1) =>
    apiFetch<QraOptions>(`${QRA_API_ROOT}/options?page=${page}&page_size=100&search=${encodeURIComponent(search)}`, {
      token,
    }),
  requirements: (token: string, projectId: number) =>
    apiFetch<JsonRecord>(`${QRA_API_ROOT}/projects/${projectId}/requirements`, { token }),
  contexts: (token: string, projectId: number) =>
    apiFetch<JsonRecord>(`${QRA_API_ROOT}/projects/${projectId}/contexts`, { token }),
  sourceOptions: (token: string, projectId: number, kind: "cost" | "schedule", page = 1) =>
    apiFetch<JsonRecord>(`${QRA_API_ROOT}/projects/${projectId}/${kind}-source-options?page=${page}&page_size=100`, {
      token,
    }),
  records: (token: string, projectId: number, kind: QraKind, page = 1) =>
    apiFetch<QraPage>(`${QRA_API_ROOT}/projects/${projectId}/${collection(kind)}?page=${page}&page_size=25`, {
      token,
    }),
  record: (token: string, kind: QraKind, id: number, summary = false) =>
    apiFetch<QraRecord>(`${QRA_API_ROOT}/${collection(kind)}/${id}${summary ? "?summary=true" : ""}`, { token }),
  recordItems: (token: string, kind: QraKind, id: number, page = 1) =>
    apiFetch<QraItemPage>(`${QRA_API_ROOT}/${collection(kind)}/${id}/items?page=${page}&page_size=25`, { token }),
  readiness: (token: string, projectId: number, kind: QraKind) =>
    apiFetch<JsonRecord>(`${QRA_API_ROOT}/projects/${projectId}/${kind}-readiness?summary=true`, { token }),
  create: (token: string, projectId: number, kind: QraKind, body: JsonRecord) =>
    apiFetch<QraRecord>(`${QRA_API_ROOT}/projects/${projectId}/${collection(kind)}`, {
      method: "POST",
      token,
      headers: headers(),
      body: JSON.stringify(body),
    }),
  update: (token: string, kind: QraKind, item: QraRecord, body: JsonRecord) =>
    apiFetch<QraRecord>(`${QRA_API_ROOT}/${collection(kind)}/${item.id}`, {
      method: "PUT",
      token,
      headers: headers(item),
      body: JSON.stringify(body),
    }),
  action: (
    token: string,
    kind: QraKind,
    item: QraRecord,
    action: "preview" | "submit" | "review" | "complete" | "approve" | "refresh-apply",
    comments: string
  ) =>
    apiFetch<JsonRecord>(`${QRA_API_ROOT}/${collection(kind)}/${item.id}/${action}`, {
      method: "POST",
      token,
      headers: headers(item),
      body: JSON.stringify({ comments }),
    }),
  refreshPreview: (token: string, kind: QraKind, id: number) =>
    apiFetch<JsonRecord>(`${QRA_API_ROOT}/${collection(kind)}/${id}/refresh-preview`, { token }),
};
