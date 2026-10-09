import { apiFetch } from "../../api/client";
import type {
  CriterionRating,
  EvaluationConfiguration,
  EvaluationQueueItem,
  PortfolioEvaluation,
  Prioritization,
  PrioritizationReadiness,
} from "./types";

const idempotencyKey = (action: string, id: number) =>
  `${action}:${id}:${Date.now()}:${Math.random().toString(16).slice(2)}`;

export const portfolioEvaluationApi = {
  queue: (token: string, portfolioId: number, queue = "ALL_AUTHORIZED") =>
    apiFetch<EvaluationQueueItem[]>(
      `/api/v1/portfolios/${portfolioId}/evaluations?queue=${encodeURIComponent(queue)}`,
      { token }
    ),
  start: (token: string, portfolioId: number, projectId: number) =>
    apiFetch<PortfolioEvaluation>(`/api/v1/portfolios/${portfolioId}/projects/${projectId}/evaluations`, {
      method: "POST",
      token,
      body: JSON.stringify({ idempotency_key: idempotencyKey("start", projectId) }),
    }),
  get: (token: string, evaluationId: number) =>
    apiFetch<PortfolioEvaluation>(`/api/v1/portfolio-evaluations/${evaluationId}`, { token }),
  update: (token: string, evaluation: PortfolioEvaluation, ratings: CriterionRating[], comments: string) =>
    apiFetch<PortfolioEvaluation>(`/api/v1/portfolio-evaluations/${evaluation.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${evaluation.revision_version}"` },
      body: JSON.stringify({ ratings, comments }),
    }),
  complete: (token: string, evaluation: PortfolioEvaluation) =>
    apiFetch<PortfolioEvaluation>(`/api/v1/portfolio-evaluations/${evaluation.id}/complete`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${evaluation.revision_version}"` },
      body: JSON.stringify({ idempotency_key: idempotencyKey("complete", evaluation.id) }),
    }),
  reevaluate: (token: string, evaluation: PortfolioEvaluation) =>
    apiFetch<PortfolioEvaluation>(`/api/v1/portfolio-evaluations/${evaluation.id}/reevaluate`, {
      method: "POST",
      token,
      body: JSON.stringify({ idempotency_key: idempotencyKey("reevaluate", evaluation.id) }),
    }),
  prioritization: (token: string, portfolioId: number) =>
    apiFetch<Prioritization>(`/api/v1/portfolios/${portfolioId}/prioritization`, { token }),
  readiness: (token: string, portfolioId: number) =>
    apiFetch<PrioritizationReadiness>(`/api/v1/portfolios/${portfolioId}/prioritization/readiness`, { token }),
  configurations: (token: string) =>
    apiFetch<EvaluationConfiguration[]>("/api/v1/portfolio-evaluation/admin/configurations", { token }),
  previewConfiguration: (
    token: string,
    workspaceId?: number,
    configurationId?: number,
    contentJson?: Record<string, unknown>
  ) =>
    apiFetch<Record<string, unknown>>("/api/v1/portfolio-evaluation/admin/configurations/preview", {
      method: "POST",
      token,
      body: JSON.stringify({
        workspace_id: workspaceId || null,
        configuration_id: configurationId || null,
        content_json: contentJson,
      }),
    }),
  cloneConfiguration: (token: string, item: EvaluationConfiguration) =>
    apiFetch<EvaluationConfiguration>(`/api/v1/portfolio-evaluation/admin/configurations/${item.id}/clone`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
  updateConfiguration: (token: string, item: EvaluationConfiguration, content: Record<string, unknown>) =>
    apiFetch<EvaluationConfiguration>(`/api/v1/portfolio-evaluation/admin/configurations/${item.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${item.version}"` },
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: EvaluationConfiguration) =>
    apiFetch<EvaluationConfiguration>(`/api/v1/portfolio-evaluation/admin/configurations/${item.id}/publish`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
};
