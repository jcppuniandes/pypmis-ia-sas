import { apiFetch } from "../../api/client";
import type {
  FinancialConfiguration,
  FinancialInput,
  FinancialModel,
  FinancialModelVersion,
  FinancialReadiness,
} from "./types";

const idempotency = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const economicFinancialModelApi = {
  list: (token: string) => apiFetch<FinancialModel[]>("/api/v1/economic-financial-models", { token }),
  create: (token: string, projectWorkspaceId: number, businessCaseId: number) =>
    apiFetch<FinancialModel>("/api/v1/economic-financial-models", {
      token,
      method: "POST",
      body: JSON.stringify({
        project_workspace_id: projectWorkspaceId,
        business_case_id: businessCaseId,
        model_type: "COMMERCIAL_PROJECT",
        base_currency: "USD",
        cash_flow_basis: "NOMINAL",
        periodicity: "ANNUAL",
        model_start_date: "2026-01-01",
        model_end_date: "2035-12-31",
        construction_start: "2026-01-01",
        operations_start: "2028-01-01",
        operations_end: "2035-12-31",
        idempotency_key: idempotency("fin-model-create"),
      }),
    }),
  assumptions: (token: string, versionId: number) =>
    apiFetch<FinancialInput[]>(`/api/v1/economic-financial-model-versions/${versionId}/assumptions`, { token }),
  periods: (token: string, versionId: number) =>
    apiFetch<FinancialInput[]>(`/api/v1/economic-financial-model-versions/${versionId}/periods`, { token }),
  instruments: (token: string, versionId: number) =>
    apiFetch<FinancialInput[]>(`/api/v1/economic-financial-model-versions/${versionId}/financing-instruments`, {
      token,
    }),
  investors: (token: string, versionId: number) =>
    apiFetch<FinancialInput[]>(`/api/v1/economic-financial-model-versions/${versionId}/investors`, { token }),
  scenarios: (token: string, versionId: number) =>
    apiFetch<FinancialInput[]>(`/api/v1/economic-financial-model-versions/${versionId}/scenarios`, { token }),
  cashFlows: (token: string, versionId: number) =>
    apiFetch<FinancialInput[]>(`/api/v1/economic-financial-model-versions/${versionId}/cash-flows`, { token }),
  metrics: (token: string, versionId: number) =>
    apiFetch<FinancialInput[]>(`/api/v1/economic-financial-model-versions/${versionId}/metrics`, { token }),
  readiness: (token: string, modelId: number) =>
    apiFetch<FinancialReadiness>(`/api/v1/economic-financial-models/${modelId}/readiness`, { token }),
  calculate: (token: string, version: FinancialModelVersion) =>
    apiFetch<FinancialModelVersion>(`/api/v1/economic-financial-model-versions/${version.id}/calculate`, {
      token,
      method: "POST",
      headers: { "If-Match": `"${version.revision_version}"` },
      body: JSON.stringify({ idempotency_key: idempotency("fin-calculate") }),
    }),
  submit: (token: string, version: FinancialModelVersion) =>
    apiFetch<FinancialModelVersion>(`/api/v1/economic-financial-model-versions/${version.id}/submit-review`, {
      token,
      method: "POST",
      headers: { "If-Match": `"${version.revision_version}"` },
      body: JSON.stringify({ idempotency_key: idempotency("fin-submit") }),
    }),
  complete: (token: string, version: FinancialModelVersion) =>
    apiFetch<FinancialModelVersion>(`/api/v1/economic-financial-model-versions/${version.id}/complete`, {
      token,
      method: "POST",
      headers: { "If-Match": `"${version.revision_version}"` },
      body: JSON.stringify({ idempotency_key: idempotency("fin-complete") }),
    }),
  configurations: (token: string) =>
    apiFetch<FinancialConfiguration[]>("/api/v1/economic-financial-models/admin/configurations", { token }),
  previewConfiguration: (
    token: string,
    configurationId: number,
    content: Record<string, unknown>,
    projectWorkspaceId: number,
    businessCaseId?: number
  ) =>
    apiFetch<Record<string, unknown>>("/api/v1/economic-financial-models/admin/configurations/preview", {
      token,
      method: "POST",
      body: JSON.stringify({
        project_workspace_id: projectWorkspaceId,
        business_case_id: businessCaseId || null,
        configuration_id: configurationId,
        content_json: content,
      }),
    }),
  cloneConfiguration: (token: string, item: FinancialConfiguration) =>
    apiFetch<FinancialConfiguration>(`/api/v1/economic-financial-models/admin/configurations/${item.id}/clone`, {
      token,
      method: "POST",
      headers: { "If-Match": `"${item.version}"` },
    }),
  updateConfiguration: (token: string, item: FinancialConfiguration, content: Record<string, unknown>) =>
    apiFetch<FinancialConfiguration>(`/api/v1/economic-financial-models/admin/configurations/${item.id}`, {
      token,
      method: "PUT",
      headers: { "If-Match": `"${item.version}"` },
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: FinancialConfiguration) =>
    apiFetch<FinancialConfiguration>(`/api/v1/economic-financial-models/admin/configurations/${item.id}/publish`, {
      token,
      method: "POST",
      headers: { "If-Match": `"${item.version}"` },
    }),
};
