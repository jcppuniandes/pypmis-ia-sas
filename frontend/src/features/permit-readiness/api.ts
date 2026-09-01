import { apiFetch } from "../../api/client";
import type {
  PermitAssessment,
  PermitCondition,
  PermitConfiguration,
  ProjectPermit,
  ProjectPermitReadiness,
  ProjectSetPermitReadiness,
} from "./types";

const key = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;

export const permitReadinessApi = {
  overview: (token: string) => apiFetch<Record<string, unknown>>("/api/v1/permit-readiness/overview", { token }),
  permits: (token: string, projectId: number) =>
    apiFetch<ProjectPermit[]>(`/api/v1/projects/${projectId}/permits`, { token }),
  createPermit: (token: string, projectId: number, payload: Record<string, unknown>) =>
    apiFetch<ProjectPermit>(`/api/v1/projects/${projectId}/permits`, {
      method: "POST",
      token,
      body: JSON.stringify({ ...payload, idempotency_key: key("permit") }),
    }),
  changeStatus: (token: string, permit: ProjectPermit, status: string) =>
    apiFetch<ProjectPermit>(`/api/v1/permits/${permit.id}/status`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${permit.revision_version}"` },
      body: JSON.stringify({ status, idempotency_key: key("permit-status") }),
    }),
  conditions: (token: string, permitId: number) =>
    apiFetch<PermitCondition[]>(`/api/v1/permits/${permitId}/conditions`, { token }),
  createCondition: (token: string, permitId: number, payload: Record<string, unknown>) =>
    apiFetch<PermitCondition>(`/api/v1/permits/${permitId}/conditions`, {
      method: "POST",
      token,
      body: JSON.stringify({ ...payload, idempotency_key: key("permit-condition") }),
    }),
  assessments: (token: string, projectId: number) =>
    apiFetch<PermitAssessment[]>(`/api/v1/projects/${projectId}/permit-readiness-assessments`, { token }),
  startAssessment: (token: string, projectId: number) =>
    apiFetch<PermitAssessment>(`/api/v1/projects/${projectId}/permit-readiness-assessments`, {
      method: "POST",
      token,
      body: JSON.stringify({ gate_profile_code: "PYP-FFA", idempotency_key: key("permit-assessment") }),
    }),
  completeAssessment: (token: string, assessment: PermitAssessment) =>
    apiFetch<PermitAssessment>(`/api/v1/permit-readiness-assessments/${assessment.id}/complete`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${assessment.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("permit-complete") }),
    }),
  projectReadiness: (token: string, projectId: number) =>
    apiFetch<ProjectPermitReadiness>(`/api/v1/projects/${projectId}/permit-readiness?gate_profile_code=PYP-FFA`, {
      token,
    }),
  refreshPreview: (token: string, projectId: number) =>
    apiFetch<Record<string, unknown>>(
      `/api/v1/projects/${projectId}/permit-readiness/refresh-preview?gate_profile_code=PYP-FFA`,
      { token }
    ),
  portfolioReadiness: (token: string, portfolioId: number) =>
    apiFetch<ProjectSetPermitReadiness>(
      `/api/v1/portfolios/${portfolioId}/permit-readiness?gate_profile_code=PYP-FFA`,
      { token }
    ),
  evidence: (token: string, portfolioId: number) =>
    apiFetch<Record<string, unknown>>(
      `/api/v1/portfolios/${portfolioId}/investment-gate-permit-evidence?gate_profile_code=PYP-FFA`,
      { token }
    ),
  configurations: (token: string) =>
    apiFetch<PermitConfiguration[]>("/api/v1/permit-readiness/admin/configurations", { token }),
  cloneConfiguration: (token: string, item: PermitConfiguration) =>
    apiFetch<PermitConfiguration>(`/api/v1/permit-readiness/admin/configurations/${item.id}/clone`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
  updateConfiguration: (token: string, item: PermitConfiguration, content: Record<string, unknown>) =>
    apiFetch<PermitConfiguration>(`/api/v1/permit-readiness/admin/configurations/${item.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${item.version}"` },
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: PermitConfiguration) =>
    apiFetch<PermitConfiguration>(`/api/v1/permit-readiness/admin/configurations/${item.id}/publish`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
  previewConfiguration: (
    token: string,
    item: PermitConfiguration,
    content: Record<string, unknown>,
    portfolioId: number
  ) =>
    apiFetch<Record<string, unknown>>("/api/v1/permit-readiness/admin/configurations/preview", {
      method: "POST",
      token,
      body: JSON.stringify({
        portfolio_workspace_id: portfolioId || null,
        configuration_id: item.id,
        gate_profile_code: "PYP-FFA",
        content_json: content,
      }),
    }),
};
