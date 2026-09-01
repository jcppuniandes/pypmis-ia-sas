import { apiFetch } from "../../api/client";
import type {
  BudgetConfiguration,
  BudgetPlanningOverview,
  BudgetScenario,
  BudgetTarget,
  ProjectDependency,
  ScenarioComparison,
  Waterline,
} from "./types";

const key = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const portfolioBudgetApi = {
  overview: (token: string, portfolioId: number) =>
    apiFetch<BudgetPlanningOverview>(`/api/v1/portfolios/${portfolioId}/budget-planning`, { token }),
  createTarget: (
    token: string,
    portfolioId: number,
    payload: {
      planning_horizon_start: string;
      planning_horizon_end: string;
      budget_currency: string;
      total_budget_target: number;
      capex_budget_target?: number | null;
      expense_budget_target?: number | null;
      source_reference: string;
    }
  ) =>
    apiFetch<BudgetTarget>(`/api/v1/portfolios/${portfolioId}/budget-targets`, {
      method: "POST",
      token,
      body: JSON.stringify({ ...payload, period_granularity: "YEAR", periods: [], idempotency_key: key("target") }),
    }),
  publishTarget: (token: string, target: BudgetTarget) =>
    apiFetch<BudgetTarget>(`/api/v1/portfolio-budget-targets/${target.id}/publish`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${target.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("target-publish") }),
    }),
  createScenario: (
    token: string,
    portfolioId: number,
    payload: {
      scenario_name: string;
      budget_target_id: number;
      creation_mode: string;
      time_phasing_method: string;
      expected_analysis_hash: string;
      source_scenario_id?: number;
    }
  ) =>
    apiFetch<BudgetScenario>(`/api/v1/portfolios/${portfolioId}/budget-scenarios`, {
      method: "POST",
      token,
      body: JSON.stringify({ ...payload, description: "", idempotency_key: key("scenario") }),
    }),
  selectProject: (
    token: string,
    scenario: BudgetScenario,
    projectId: number,
    selectionState: string,
    forcedReason: string
  ) =>
    apiFetch<BudgetScenario>(`/api/v1/portfolio-budget-scenarios/${scenario.id}/projects/${projectId}/selection`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${scenario.revision_version}"` },
      body: JSON.stringify({
        selection_state: selectionState,
        forced_reason: forcedReason || null,
        period_profile: [],
        idempotency_key: key("selection"),
      }),
    }),
  freezeScenario: (token: string, scenario: BudgetScenario) =>
    apiFetch<BudgetScenario>(`/api/v1/portfolio-budget-scenarios/${scenario.id}/freeze`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${scenario.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("freeze") }),
    }),
  cloneScenario: (token: string, scenario: BudgetScenario) =>
    apiFetch<BudgetScenario>(`/api/v1/portfolio-budget-scenarios/${scenario.id}/clone`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${scenario.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("clone") }),
    }),
  refreshPreview: (token: string, scenarioId: number) =>
    apiFetch<Record<string, unknown>>(`/api/v1/portfolio-budget-scenarios/${scenarioId}/refresh/preview`, {
      method: "POST",
      token,
    }),
  compare: (token: string, portfolioId: number, scenarioIds: number[]) =>
    apiFetch<ScenarioComparison>(`/api/v1/portfolios/${portfolioId}/budget-scenarios/compare`, {
      method: "POST",
      token,
      body: JSON.stringify({ scenario_ids: scenarioIds }),
    }),
  waterline: (token: string, scenarioId: number, periodKey?: string) =>
    apiFetch<Waterline>(
      `/api/v1/portfolio-budget-scenarios/${scenarioId}/waterline${periodKey ? `?period_key=${encodeURIComponent(periodKey)}` : ""}`,
      { token }
    ),
  dependencies: (token: string, portfolioId: number) =>
    apiFetch<ProjectDependency[]>(`/api/v1/portfolios/${portfolioId}/project-dependencies`, { token }),
  createDependency: (
    token: string,
    portfolioId: number,
    payload: {
      predecessor_project_workspace_id: number;
      successor_project_workspace_id: number;
      dependency_type: string;
      dependency_strength: string;
      description: string;
      effective_from?: string | null;
      effective_to?: string | null;
      source_reference?: string | null;
    }
  ) =>
    apiFetch<ProjectDependency>(`/api/v1/portfolios/${portfolioId}/project-dependencies`, {
      method: "POST",
      token,
      body: JSON.stringify({ ...payload, evidence_refs: [], idempotency_key: key("dependency") }),
    }),
  updateDependency: (
    token: string,
    dependency: ProjectDependency,
    payload: {
      dependency_type: string;
      dependency_strength: string;
      description: string;
      effective_from: string | null;
      effective_to: string | null;
      source_reference: string | null;
    }
  ) =>
    apiFetch<ProjectDependency>(`/api/v1/project-dependencies/${dependency.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${dependency.revision_version}"` },
      body: JSON.stringify({ ...payload, evidence_refs: dependency.evidence_refs || [] }),
    }),
  deactivateDependency: (token: string, dependency: ProjectDependency) =>
    apiFetch<ProjectDependency>(`/api/v1/project-dependencies/${dependency.id}/deactivate`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${dependency.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("dependency-deactivate") }),
    }),
  configurations: (token: string) =>
    apiFetch<BudgetConfiguration[]>("/api/v1/portfolio-budget/admin/configurations", { token }),
  previewConfiguration: (
    token: string,
    portfolioWorkspaceId: number | undefined,
    configurationId: number,
    contentJson: Record<string, unknown>
  ) =>
    apiFetch<Record<string, unknown>>("/api/v1/portfolio-budget/admin/configurations/preview", {
      method: "POST",
      token,
      body: JSON.stringify({
        portfolio_workspace_id: portfolioWorkspaceId || null,
        configuration_id: configurationId,
        content_json: contentJson,
        target_assumptions: null,
      }),
    }),
  cloneConfiguration: (token: string, item: BudgetConfiguration) =>
    apiFetch<BudgetConfiguration>(`/api/v1/portfolio-budget/admin/configurations/${item.id}/clone`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
  updateConfiguration: (token: string, item: BudgetConfiguration, content: Record<string, unknown>) =>
    apiFetch<BudgetConfiguration>(`/api/v1/portfolio-budget/admin/configurations/${item.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${item.version}"` },
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: BudgetConfiguration) =>
    apiFetch<BudgetConfiguration>(`/api/v1/portfolio-budget/admin/configurations/${item.id}/publish`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
};
