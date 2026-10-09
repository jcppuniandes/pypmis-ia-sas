import { apiFetch } from "../../api/client";
import type {
  ConvergenceComparison,
  ConvergenceConfiguration,
  ConvergenceOverview,
  ScenarioConvergence,
} from "./types";

const key = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const portfolioConvergenceApi = {
  overview: (token: string, portfolioId: number) =>
    apiFetch<ConvergenceOverview>(`/api/v1/portfolios/${portfolioId}/scenario-convergence`, { token }),
  create: (token: string, portfolioId: number, name: string) =>
    apiFetch<ScenarioConvergence>(`/api/v1/portfolios/${portfolioId}/scenario-convergences`, {
      method: "POST",
      token,
      body: JSON.stringify({
        name,
        description: "Governed budget and resource scenario convergence.",
        idempotency_key: key("convergence"),
      }),
    }),
  addAlternative: (
    token: string,
    convergence: ScenarioConvergence,
    name: string,
    budgetScenarioId: number | null,
    resourceScenarioId: number | null
  ) =>
    apiFetch<ScenarioConvergence>(`/api/v1/portfolio-scenario-convergences/${convergence.id}/alternatives`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${convergence.revision_version}"` },
      body: JSON.stringify({
        alternative_name: name,
        budget_scenario_id: budgetScenarioId,
        resource_scenario_id: resourceScenarioId,
        idempotency_key: key("converged-alternative"),
      }),
    }),
  compare: (token: string, convergenceId: number, alternativeIds: number[]) =>
    apiFetch<ConvergenceComparison>(`/api/v1/portfolio-scenario-convergences/${convergenceId}/compare`, {
      method: "POST",
      token,
      body: JSON.stringify({ alternative_ids: alternativeIds }),
    }),
  submit: (token: string, convergence: ScenarioConvergence) =>
    apiFetch<ScenarioConvergence>(`/api/v1/portfolio-scenario-convergences/${convergence.id}/submit-review`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${convergence.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("convergence-submit") }),
    }),
  returnToDraft: (token: string, convergence: ScenarioConvergence) =>
    apiFetch<ScenarioConvergence>(`/api/v1/portfolio-scenario-convergences/${convergence.id}/return-to-draft`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${convergence.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("convergence-return") }),
    }),
  recommend: (
    token: string,
    convergence: ScenarioConvergence,
    alternativeId: number,
    reason: string,
    risks: string,
    summary: string
  ) =>
    apiFetch<ScenarioConvergence>(`/api/v1/portfolio-scenario-convergences/${convergence.id}/recommend`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${convergence.revision_version}"` },
      body: JSON.stringify({
        recommended_alternative_id: alternativeId,
        recommendation_reason: reason,
        conditions: [],
        risks_acknowledged: risks
          .split("\n")
          .map((item) => item.trim())
          .filter(Boolean),
        decision_support_summary: summary,
        idempotency_key: key("portfolio-recommendation"),
      }),
    }),
  refreshPreview: (token: string, convergenceId: number) =>
    apiFetch<Record<string, unknown>>(`/api/v1/portfolio-scenario-convergences/${convergenceId}/refresh-preview`, {
      method: "POST",
      token,
    }),
  configurations: (token: string) =>
    apiFetch<ConvergenceConfiguration[]>("/api/v1/portfolio-convergence/admin/configurations", { token }),
  previewConfiguration: (
    token: string,
    portfolioId: number | null,
    configurationId: number,
    content: Record<string, unknown>
  ) =>
    apiFetch<Record<string, unknown>>("/api/v1/portfolio-convergence/admin/configurations/preview", {
      method: "POST",
      token,
      body: JSON.stringify({
        portfolio_workspace_id: portfolioId,
        configuration_id: configurationId,
        content_json: content,
      }),
    }),
  cloneConfiguration: (token: string, item: ConvergenceConfiguration) =>
    apiFetch<ConvergenceConfiguration>(`/api/v1/portfolio-convergence/admin/configurations/${item.id}/clone`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
  updateConfiguration: (token: string, item: ConvergenceConfiguration, content: Record<string, unknown>) =>
    apiFetch<ConvergenceConfiguration>(`/api/v1/portfolio-convergence/admin/configurations/${item.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${item.version}"` },
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: ConvergenceConfiguration) =>
    apiFetch<ConvergenceConfiguration>(`/api/v1/portfolio-convergence/admin/configurations/${item.id}/publish`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
};
