import { apiFetch } from "../../api/client";
import type { PortfolioReadiness, ProjectReadiness, ProjectRisk, RiskAssessment, RiskConfiguration } from "./types";

const key = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;

export const riskReadinessApi = {
  overview: (token: string) => apiFetch<Record<string, unknown>>("/api/v1/risk-readiness/overview", { token }),
  risks: (token: string, projectId: number) =>
    apiFetch<ProjectRisk[]>(`/api/v1/projects/${projectId}/risks`, { token }),
  createRisk: (token: string, projectId: number, payload: Record<string, unknown>) =>
    apiFetch<ProjectRisk>(`/api/v1/projects/${projectId}/risks`, {
      method: "POST",
      token,
      body: JSON.stringify({ ...payload, idempotency_key: key("risk") }),
    }),
  updateRisk: (token: string, risk: ProjectRisk, payload: Record<string, unknown>) =>
    apiFetch<ProjectRisk>(`/api/v1/risks/${risk.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${risk.revision_version}"` },
      body: JSON.stringify(payload),
    }),
  changeStatus: (token: string, risk: ProjectRisk, status: string) =>
    apiFetch<ProjectRisk>(`/api/v1/risks/${risk.id}/status`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${risk.revision_version}"` },
      body: JSON.stringify({ status }),
    }),
  acceptResidual: (token: string, risk: ProjectRisk, comment: string, authority: string) =>
    apiFetch<ProjectRisk>(`/api/v1/risks/${risk.id}/accept-residual`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${risk.revision_version}"` },
      body: JSON.stringify({
        acceptance_comment: comment,
        acceptance_authority_level: authority,
        idempotency_key: key("accept"),
      }),
    }),
  assessments: (token: string, projectId: number) =>
    apiFetch<RiskAssessment[]>(`/api/v1/projects/${projectId}/risk-readiness-assessments`, { token }),
  startAssessment: (token: string, projectId: number) =>
    apiFetch<RiskAssessment>(`/api/v1/projects/${projectId}/risk-readiness-assessments`, {
      method: "POST",
      token,
      body: JSON.stringify({ idempotency_key: key("assessment") }),
    }),
  completeAssessment: (token: string, assessment: RiskAssessment) =>
    apiFetch<RiskAssessment>(`/api/v1/risk-readiness-assessments/${assessment.id}/complete`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${assessment.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("complete") }),
    }),
  projectReadiness: (token: string, projectId: number) =>
    apiFetch<ProjectReadiness>(`/api/v1/projects/${projectId}/risk-readiness`, { token }),
  refreshPreview: (token: string, projectId: number) =>
    apiFetch<Record<string, unknown>>(`/api/v1/projects/${projectId}/risk-readiness/refresh-preview`, { token }),
  portfolioReadiness: (token: string, portfolioId: number) =>
    apiFetch<PortfolioReadiness>(`/api/v1/portfolios/${portfolioId}/risk-readiness`, { token }),
  evidence: (token: string, portfolioId: number) =>
    apiFetch<Record<string, unknown>>(`/api/v1/portfolios/${portfolioId}/investment-gate-risk-evidence`, { token }),
  configurations: (token: string) =>
    apiFetch<RiskConfiguration[]>("/api/v1/risk-readiness/admin/configurations", { token }),
  cloneConfiguration: (token: string, item: RiskConfiguration) =>
    apiFetch<RiskConfiguration>(`/api/v1/risk-readiness/admin/configurations/${item.id}/clone`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
  updateConfiguration: (token: string, item: RiskConfiguration, content: Record<string, unknown>) =>
    apiFetch<RiskConfiguration>(`/api/v1/risk-readiness/admin/configurations/${item.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${item.version}"` },
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: RiskConfiguration) =>
    apiFetch<RiskConfiguration>(`/api/v1/risk-readiness/admin/configurations/${item.id}/publish`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
  previewConfiguration: (
    token: string,
    item: RiskConfiguration,
    content: Record<string, unknown>,
    portfolioId: number
  ) =>
    apiFetch<Record<string, unknown>>("/api/v1/risk-readiness/admin/configurations/preview", {
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
