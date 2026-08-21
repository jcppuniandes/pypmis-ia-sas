import { apiFetch } from "../../api/client";
import type {
  PlanningCreatePayload,
  PlanningOption,
  PlanningReadiness,
  PortfolioMembership,
  PortfolioProject,
  StrategicPlanningEntry,
  StrategicPlanningPreview,
} from "./types";

const root = "/api/v1/strategic-project-planning";

export const portfolioPlanningApi = {
  options: (token: string) => apiFetch<PlanningOption[]>(`${root}/options`, { token }),
  portfolioOptions: (token: string) => apiFetch<Array<Record<string, unknown>>>(`${root}/portfolio-options`, { token }),
  preview: (token: string, decisionId: number) =>
    apiFetch<StrategicPlanningPreview>(`${root}/preview`, {
      method: "POST",
      token,
      body: JSON.stringify({ strategic_gate_decision_id: decisionId }),
    }),
  create: (token: string, payload: PlanningCreatePayload) =>
    apiFetch<StrategicPlanningEntry>(root, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),
  entry: (token: string, decisionId: number) => apiFetch<StrategicPlanningEntry>(`${root}/${decisionId}`, { token }),
  projectAction: (token: string, request: { id: number; revision_version: number }, action: string) =>
    apiFetch<Record<string, unknown>>(`/api/v1/project-creation-requests/${request.id}/${action}`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${request.revision_version}"` },
    }),
  portfolioProjects: (token: string, portfolioId: number) =>
    apiFetch<PortfolioProject[]>(`/api/v1/portfolios/${portfolioId}/projects`, { token }),
  memberships: (token: string, projectId: number) =>
    apiFetch<PortfolioMembership[]>(`/api/v1/projects/${projectId}/portfolio-memberships`, { token }),
  projectReadiness: (token: string, projectId: number) =>
    apiFetch<StrategicPlanningEntry>(`/api/v1/projects/${projectId}/portfolio-planning-readiness`, { token }),
  portfolioEvaluationReadiness: (token: string, projectId: number) =>
    apiFetch<PlanningReadiness>(`/api/v1/projects/${projectId}/portfolio-evaluation-readiness`, { token }),
  projectDefinitionReadiness: (token: string, projectId: number) =>
    apiFetch<PlanningReadiness>(`/api/v1/projects/${projectId}/project-definition-readiness`, { token }),
  configurations: (token: string) =>
    apiFetch<Array<Record<string, unknown>>>(`${root}/admin/configurations`, { token }),
  cloneConfiguration: (token: string, item: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>(`${root}/admin/configurations/${String(item.id)}/clone`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${String(item.version)}"` },
    }),
  updateConfiguration: (token: string, item: Record<string, unknown>, content: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>(`${root}/admin/configurations/${String(item.id)}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${String(item.version)}"` },
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
      headers: { "If-Match": `"${String(item.version)}"` },
    }),
};
