import { apiFetch } from "../../api/client";
import { createIdempotencyKey } from "../capital-planning/api";
import type { JsonRecord } from "../risk-governance/policyApi";

export type QraRun = JsonRecord & {
  id: number;
  project_id: number;
  run_number: string;
  model_id: number;
  analysis_type: string;
  status: string;
  revision_version: number;
  allowed_actions: string[];
  iterations_requested: number;
  iterations_completed: number;
};
export type QraRunPage = { items: QraRun[]; total: number; page: number; page_size: number };
export type QraApprovedModel = JsonRecord & {
  id: number;
  model_number?: string;
  number?: string;
  title: string;
  status: string;
  version: number;
  analysis_type: string;
};
export type QraModelPage = { items: QraApprovedModel[]; total: number; page: number; page_size: number };
export type QraEngineOptions = JsonRecord & {
  allowed_actions: string[];
  approved_models: QraApprovedModel[];
  engine_policy: JsonRecord;
};
export type QraRunAction = "execute" | "cancel" | "review" | "accept";
export const QRA_ENGINE_API_ROOT = "/api/v1/qra-engine";
export const qraEngineApi = {
  options: (token: string, projectId: number, signal?: AbortSignal) =>
    apiFetch<QraEngineOptions>(`${QRA_ENGINE_API_ROOT}/projects/${projectId}/options`, { token, signal }),
  models: (token: string, projectId: number, page = 1, signal?: AbortSignal) =>
    apiFetch<QraModelPage>(`${QRA_ENGINE_API_ROOT}/projects/${projectId}/approved-models?page=${page}&page_size=25`, {
      token,
      signal,
    }),
  runs: (token: string, projectId: number, page = 1, signal?: AbortSignal) =>
    apiFetch<QraRunPage>(`${QRA_ENGINE_API_ROOT}/projects/${projectId}/runs?page=${page}&page_size=25`, {
      token,
      signal,
    }),
  run: (token: string, id: number, signal?: AbortSignal) =>
    apiFetch<QraRun>(`${QRA_ENGINE_API_ROOT}/runs/${id}?summary=true`, { token, signal }),
  status: (token: string, id: number, signal?: AbortSignal) =>
    apiFetch<QraRun>(`${QRA_ENGINE_API_ROOT}/runs/${id}/status`, { token, signal }),
  preflight: (token: string, modelId: number) =>
    apiFetch<JsonRecord>(`${QRA_ENGINE_API_ROOT}/models/${modelId}/preflight`, { token }),
  create: (token: string, modelId: number, body: JsonRecord, key: string) =>
    apiFetch<QraRun>(`${QRA_ENGINE_API_ROOT}/models/${modelId}/runs`, {
      method: "POST",
      token,
      headers: { "Idempotency-Key": key },
      body: JSON.stringify(body),
    }),
  action: (token: string, run: QraRun, action: QraRunAction, comments: string) =>
    apiFetch<QraRun>(`${QRA_ENGINE_API_ROOT}/runs/${run.id}/${action}`, {
      method: "POST",
      token,
      headers: { "Idempotency-Key": createIdempotencyKey(), "If-Match": `"${run.revision_version}"` },
      body: JSON.stringify({ comments }),
    }),
  read: (token: string, id: number, section: string, signal?: AbortSignal, page = 1) =>
    apiFetch<JsonRecord>(`${QRA_ENGINE_API_ROOT}/runs/${id}/${section}?page=${page}&page_size=100`, { token, signal }),
  compare: (token: string, left: number, right: number) =>
    apiFetch<JsonRecord>(`${QRA_ENGINE_API_ROOT}/runs/compare?left_id=${left}&right_id=${right}`, { token }),
};
