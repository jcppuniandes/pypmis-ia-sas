import { apiFetch } from "../../api/client";
import type {
  CapacityPlan,
  DemandProfile,
  ResourceConfiguration,
  ResourcePlanningOverview,
  ResourceScenario,
  ResourceScenarioComparison,
} from "./types";

const key = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const portfolioResourceApi = {
  overview: (token: string, portfolioId: number) =>
    apiFetch<ResourcePlanningOverview>(`/api/v1/portfolios/${portfolioId}/resource-planning`, { token }),
  createCapacity: (
    token: string,
    portfolioId: number,
    payload: {
      plan_name: string;
      planning_horizon_start: string;
      planning_horizon_end: string;
      period_granularity: string;
      source_reference: string;
      periods: Array<Record<string, unknown>>;
    }
  ) =>
    apiFetch<CapacityPlan>(`/api/v1/portfolios/${portfolioId}/resource-capacity-plans`, {
      method: "POST",
      token,
      body: JSON.stringify({ ...payload, notes: "", idempotency_key: key("capacity") }),
    }),
  publishCapacity: (token: string, plan: CapacityPlan) =>
    apiFetch<CapacityPlan>(`/api/v1/portfolio-resource-capacity-plans/${plan.id}/publish`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${plan.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("capacity-publish") }),
    }),
  createDemand: (
    token: string,
    projectId: number,
    payload: {
      profile_name: string;
      source_type: string;
      source_reference: string;
      as_of_date: string;
      planning_start: string;
      planning_finish: string;
      generation_method: string;
      periods: Array<Record<string, unknown>>;
    }
  ) =>
    apiFetch<DemandProfile>(`/api/v1/projects/${projectId}/resource-demand-profiles`, {
      method: "POST",
      token,
      body: JSON.stringify({ ...payload, idempotency_key: key("resource-demand") }),
    }),
  publishDemand: (token: string, profile: DemandProfile) =>
    apiFetch<DemandProfile>(`/api/v1/project-resource-demand-profiles/${profile.id}/publish`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${profile.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("resource-demand-publish") }),
    }),
  createScenario: (
    token: string,
    portfolioId: number,
    payload: {
      scenario_name: string;
      capacity_plan_id: number;
      creation_mode: string;
      expected_analysis_hash: string;
    }
  ) =>
    apiFetch<ResourceScenario>(`/api/v1/portfolios/${portfolioId}/resource-scenarios`, {
      method: "POST",
      token,
      body: JSON.stringify({ ...payload, description: "", idempotency_key: key("resource-scenario") }),
    }),
  selectProject: (
    token: string,
    scenario: ResourceScenario,
    projectId: number,
    selectionState: string,
    forcedReason: string
  ) =>
    apiFetch<ResourceScenario>(`/api/v1/portfolio-resource-scenarios/${scenario.id}/projects/${projectId}/selection`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${scenario.revision_version}"` },
      body: JSON.stringify({
        selection_state: selectionState,
        forced_reason: forcedReason || null,
        authority_reference: null,
        idempotency_key: key("resource-selection"),
      }),
    }),
  adjustTiming: (token: string, scenario: ResourceScenario, projectId: number, start: string, finish: string) =>
    apiFetch<ResourceScenario>(`/api/v1/portfolio-resource-scenarios/${scenario.id}/projects/${projectId}/timing`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${scenario.revision_version}"` },
      body: JSON.stringify({
        timing_method: "CUSTOM_SCENARIO_DATES",
        scenario_start: start,
        scenario_finish: finish,
        idempotency_key: key("resource-timing"),
      }),
    }),
  freezeScenario: (token: string, scenario: ResourceScenario) =>
    apiFetch<ResourceScenario>(`/api/v1/portfolio-resource-scenarios/${scenario.id}/freeze`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${scenario.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("resource-freeze") }),
    }),
  cloneScenario: (token: string, scenario: ResourceScenario) =>
    apiFetch<ResourceScenario>(`/api/v1/portfolio-resource-scenarios/${scenario.id}/clone`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${scenario.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("resource-clone") }),
    }),
  refreshPreview: (token: string, scenarioId: number) =>
    apiFetch<Record<string, unknown>>(`/api/v1/portfolio-resource-scenarios/${scenarioId}/refresh/preview`, {
      method: "POST",
      token,
    }),
  compare: (token: string, portfolioId: number, scenarioIds: number[]) =>
    apiFetch<ResourceScenarioComparison>(`/api/v1/portfolios/${portfolioId}/resource-scenarios/compare`, {
      method: "POST",
      token,
      body: JSON.stringify({ scenario_ids: scenarioIds }),
    }),
  configurations: (token: string) =>
    apiFetch<ResourceConfiguration[]>("/api/v1/portfolio-resource/admin/configurations", { token }),
  previewConfiguration: (
    token: string,
    portfolioWorkspaceId: number | undefined,
    configurationId: number,
    contentJson: Record<string, unknown>
  ) =>
    apiFetch<Record<string, unknown>>("/api/v1/portfolio-resource/admin/configurations/preview", {
      method: "POST",
      token,
      body: JSON.stringify({
        portfolio_workspace_id: portfolioWorkspaceId || null,
        configuration_id: configurationId,
        content_json: contentJson,
      }),
    }),
  cloneConfiguration: (token: string, item: ResourceConfiguration) =>
    apiFetch<ResourceConfiguration>(`/api/v1/portfolio-resource/admin/configurations/${item.id}/clone`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
  updateConfiguration: (token: string, item: ResourceConfiguration, content: Record<string, unknown>) =>
    apiFetch<ResourceConfiguration>(`/api/v1/portfolio-resource/admin/configurations/${item.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${item.version}"` },
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: ResourceConfiguration) =>
    apiFetch<ResourceConfiguration>(`/api/v1/portfolio-resource/admin/configurations/${item.id}/publish`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
};
