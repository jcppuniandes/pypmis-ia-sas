import { apiFetch, apiFetchWithResponse } from "../../api/client";
import type {
  CapitalDemandIdeaOrigin,
  CapitalPlanningConfiguration,
  CapitalPlanningConfigurationPreview,
  CapitalPlanningCycle,
  CapitalPlanningCycleDraft,
  CapitalPlanningCycleSummary,
  CapitalDemandFilters,
  CapitalPlanningOptions,
  CapitalPlanningPage,
  StrategicCapitalDemand,
  StrategicCapitalDemandDraft,
} from "./types";

const root = "/api/v1/capital-planning";
const versionHeaders = (version: number) => ({ "If-Match": `"${version}"` });

export function createIdempotencyKey() {
  const webCrypto = globalThis.crypto;
  if (typeof webCrypto?.randomUUID === "function") return webCrypto.randomUUID();

  const bytes = new Uint8Array(16);
  if (typeof webCrypto?.getRandomValues === "function") {
    webCrypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) bytes[index] = Math.floor(Math.random() * 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex
    .slice(8, 10)
    .join("")}-${hex.slice(10).join("")}`;
}

const idempotencyHeaders = (key: string = createIdempotencyKey()) => ({ "Idempotency-Key": key });

function filterQuery(filters: CapitalDemandFilters) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
  return params.toString();
}

async function listPage<T>(token: string, path: string): Promise<CapitalPlanningPage<T>> {
  const result = await apiFetchWithResponse<
    T[] | { items: T[]; next_cursor?: string | null; page?: number; page_size?: number; total?: number }
  >(path, { token });
  const body = result.data;
  return {
    items: Array.isArray(body) ? body : body.items,
    nextCursor:
      result.response.headers?.get("X-Next-Cursor") ?? (Array.isArray(body) ? null : (body.next_cursor ?? null)),
    page: Array.isArray(body) ? 1 : (body.page ?? 1),
    pageSize: Array.isArray(body) ? body.length : (body.page_size ?? body.items.length),
    total: Array.isArray(body) ? body.length : (body.total ?? body.items.length),
  };
}

type RawOptions = Partial<CapitalPlanningOptions> & {
  drivers?: CapitalPlanningOptions["demand_drivers"];
  categories?: CapitalPlanningOptions["demand_categories"];
  horizons?: CapitalPlanningOptions["planning_horizons"];
  workspaces?: CapitalPlanningOptions["owning_workspaces"];
  portfolios?: CapitalPlanningOptions["potential_portfolios"];
  effective_configuration?: Record<string, unknown>;
};

export const capitalPlanningApi = {
  options: async (token: string, workspaceId?: number): Promise<CapitalPlanningOptions> => {
    const value = await apiFetch<RawOptions>(
      `${root}/options${workspaceId ? `?owning_workspace_id=${workspaceId}` : ""}`,
      { token }
    );
    return {
      ...value,
      planning_cycles: value.planning_cycles ?? [],
      demand_drivers: value.demand_drivers ?? value.drivers ?? [],
      demand_categories: value.demand_categories ?? value.categories ?? [],
      planning_horizons: value.planning_horizons ?? value.horizons ?? [],
      owning_workspaces: value.owning_workspaces ?? value.workspaces ?? [],
      potential_portfolios: value.potential_portfolios ?? value.portfolios ?? [],
      themes: value.themes ?? [],
      strategic_objectives: value.strategic_objectives ?? [],
      urgency_levels: value.urgency_levels ?? [],
      uncertainty_levels: value.uncertainty_levels ?? [],
      sponsors: value.sponsors ?? [],
      configuration_source: value.configuration_source ?? value.effective_configuration ?? {},
    };
  },
  listCycles: (token: string, query = "") =>
    listPage<CapitalPlanningCycle>(token, `${root}/cycles${query ? `?${query}` : ""}`),
  createCycle: (token: string, payload: CapitalPlanningCycleDraft, idempotencyKey: string = createIdempotencyKey()) =>
    apiFetch<CapitalPlanningCycle>(`${root}/cycles`, {
      method: "POST",
      token,
      headers: idempotencyHeaders(idempotencyKey),
      body: JSON.stringify(payload),
    }),
  updateCycle: (token: string, cycle: CapitalPlanningCycle, payload: CapitalPlanningCycleDraft) =>
    apiFetch<CapitalPlanningCycle>(`${root}/cycles/${cycle.id}`, {
      method: "PUT",
      token,
      headers: versionHeaders(cycle.revision_version),
      body: JSON.stringify(payload),
    }),
  closeCycle: (token: string, cycle: CapitalPlanningCycle, idempotencyKey: string = createIdempotencyKey()) =>
    apiFetch<CapitalPlanningCycle>(`${root}/cycles/${cycle.id}/close`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(cycle.revision_version), ...idempotencyHeaders(idempotencyKey) },
    }),
  openCycle: (token: string, cycle: CapitalPlanningCycle, idempotencyKey: string = createIdempotencyKey()) =>
    apiFetch<CapitalPlanningCycle>(`${root}/cycles/${cycle.id}/open`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(cycle.revision_version), ...idempotencyHeaders(idempotencyKey) },
    }),
  startCycleReview: (token: string, cycle: CapitalPlanningCycle, idempotencyKey: string = createIdempotencyKey()) =>
    apiFetch<CapitalPlanningCycle>(`${root}/cycles/${cycle.id}/review/start`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(cycle.revision_version), ...idempotencyHeaders(idempotencyKey) },
    }),
  cycleSummary: (token: string, cycleId: number) =>
    apiFetch<CapitalPlanningCycleSummary>(`${root}/cycles/${cycleId}/summary`, { token }),
  demandSummary: (token: string, filters: CapitalDemandFilters) =>
    apiFetch<CapitalPlanningCycleSummary>(`${root}/demands/summary?${filterQuery(filters)}`, { token }),
  listDemands: (token: string, query = "") =>
    listPage<StrategicCapitalDemand>(token, `${root}/demands${query ? `?${query}` : ""}`),
  createDemand: (
    token: string,
    payload: StrategicCapitalDemandDraft,
    idempotencyKey: string = createIdempotencyKey()
  ) =>
    apiFetch<StrategicCapitalDemand>(`${root}/demands`, {
      method: "POST",
      token,
      headers: idempotencyHeaders(idempotencyKey),
      body: JSON.stringify(payload),
    }),
  updateDemand: (token: string, demand: StrategicCapitalDemand, payload: StrategicCapitalDemandDraft) =>
    apiFetch<StrategicCapitalDemand>(`${root}/demands/${demand.id}`, {
      method: "PUT",
      token,
      headers: versionHeaders(demand.revision_version),
      body: JSON.stringify(payload),
    }),
  actionDemand: (
    token: string,
    demand: StrategicCapitalDemand,
    action: string,
    body?: unknown,
    idempotencyKey: string = createIdempotencyKey()
  ) =>
    apiFetch<StrategicCapitalDemand>(`${root}/demands/${demand.id}/${action}`, {
      method: "POST",
      token,
      headers: {
        ...versionHeaders(demand.revision_version),
        ...idempotencyHeaders(idempotencyKey),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  originateIdea: (
    token: string,
    demand: StrategicCapitalDemand,
    idempotencyKey: string,
    payload: Record<string, unknown> = {}
  ) =>
    apiFetch<CapitalDemandIdeaOrigin>(`${root}/demands/${demand.id}/originate-idea`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(demand.revision_version), ...idempotencyHeaders(idempotencyKey) },
      body: JSON.stringify(payload),
    }),
  originatedIdeas: (token: string, demandId: number) =>
    apiFetch<CapitalDemandIdeaOrigin[]>(`${root}/demands/${demandId}/originated-ideas`, { token }),
  history: (token: string, demandId: number) =>
    apiFetch<Array<Record<string, unknown>>>(`${root}/demands/${demandId}/history`, { token }),
  configurations: (token: string) =>
    apiFetch<CapitalPlanningConfiguration[]>(`${root}/admin/configurations`, { token }),
  previewConfiguration: (token: string, owningWorkspaceId: number | null) =>
    apiFetch<CapitalPlanningConfigurationPreview>(`${root}/admin/preview`, {
      method: "POST",
      token,
      body: JSON.stringify({ owning_workspace_id: owningWorkspaceId }),
    }),
  cloneConfiguration: (token: string, item: CapitalPlanningConfiguration, targetWorkspaceId: number | null = null) =>
    apiFetch<CapitalPlanningConfiguration>(`${root}/admin/configurations/${item.id}/clone`, {
      method: "POST",
      token,
      headers: versionHeaders(item.version),
      body: JSON.stringify({ target_workspace_id: targetWorkspaceId }),
    }),
  updateConfiguration: (token: string, item: CapitalPlanningConfiguration, content: Record<string, unknown>) =>
    apiFetch<CapitalPlanningConfiguration>(`${root}/admin/configurations/${item.id}`, {
      method: "PUT",
      token,
      headers: versionHeaders(item.version),
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: CapitalPlanningConfiguration) =>
    apiFetch<CapitalPlanningConfiguration>(`${root}/admin/configurations/${item.id}/publish`, {
      method: "POST",
      token,
      headers: versionHeaders(item.version),
    }),
  archiveConfiguration: (token: string, item: CapitalPlanningConfiguration) =>
    apiFetch<CapitalPlanningConfiguration>(`${root}/admin/configurations/${item.id}/archive`, {
      method: "POST",
      token,
      headers: versionHeaders(item.version),
    }),
};
