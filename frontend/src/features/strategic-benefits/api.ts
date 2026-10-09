import { apiFetch, apiFetchWithResponse } from "../../api/client";
import type {
  BenefitMeasure,
  BenefitsConfiguration,
  BenefitsOptions,
  BenefitsPlanHistory,
  BenefitsPlanQueue,
  BenefitsPlanVersion,
  BenefitsReadiness,
  BenefitsRefreshPreview,
  BenefitsTraceabilityPage,
  BenefitsTraceabilityRow,
  StrategicBenefit,
  StrategicBenefitsPlan,
} from "./types";

const root = "/api/v1/strategic-benefits-plans";
const versionHeaders = (version: number) => ({ "If-Match": `"${version}"` });
const idempotencyHeaders = () => ({ "Idempotency-Key": crypto.randomUUID() });

export type BenefitsPlanPage = {
  items: StrategicBenefitsPlan[];
  nextCursor: string | null;
  pageLimit: number;
  resultCount: number;
};

type ListQuery = {
  queue?: BenefitsPlanQueue;
  projectWorkspaceId?: number;
  search?: string;
  cursor?: string | null;
  limit?: number;
};

function queryString(query: ListQuery) {
  const params = new URLSearchParams();
  if (query.queue) params.set("queue", query.queue);
  if (query.projectWorkspaceId) params.set("project_workspace_id", String(query.projectWorkspaceId));
  if (query.search) params.set("search", query.search);
  if (query.cursor) params.set("cursor", query.cursor);
  params.set("limit", String(query.limit ?? 50));
  return params.toString();
}

function pageFromResponse<T>(
  data: T[] | { items: T[] },
  response: Response,
  fallbackLimit: number
): { items: T[]; nextCursor: string | null; pageLimit: number; resultCount: number } {
  const items = Array.isArray(data) ? data : data.items;
  return {
    items,
    nextCursor: response.headers.get("X-Next-Cursor"),
    pageLimit: Number(response.headers.get("X-Page-Limit") || fallbackLimit),
    resultCount: Number(response.headers.get("X-Result-Count") || items.length),
  };
}

export type BenefitsPlanVersionUpdate = Pick<
  BenefitsPlanVersion,
  "overview_json" | "outputs_json" | "outcomes_json" | "assumptions_json" | "constraints_json"
> & {
  fel_stage_code?: string | null;
  reviewer_user_id?: number | null;
};

export type BenefitWrite = Omit<
  StrategicBenefit,
  | "allowed_actions"
  | "benefit_number"
  | "id"
  | "identity_status"
  | "measures"
  | "revision_version"
  | "snapshot_hash"
  | "snapshot_id"
  | "status"
>;

export type MeasureWrite = Omit<
  BenefitMeasure,
  "benefit_snapshot_id" | "created_at" | "id" | "measure_hash" | "revision_version" | "updated_at"
>;

export const strategicBenefitsApi = {
  options: (token: string, projectWorkspaceId?: number) =>
    apiFetch<BenefitsOptions>(
      `${root}/options${projectWorkspaceId ? `?project_workspace_id=${projectWorkspaceId}` : ""}`,
      { token }
    ),
  listPage: async (token: string, query: ListQuery = {}): Promise<BenefitsPlanPage> => {
    const result = await apiFetchWithResponse<StrategicBenefitsPlan[] | { items: StrategicBenefitsPlan[] }>(
      `${root}?${queryString(query)}`,
      { token }
    );
    return pageFromResponse(result.data, result.response, query.limit ?? 50);
  },
  detail: (token: string, planId: number) => apiFetch<StrategicBenefitsPlan>(`${root}/${planId}`, { token }),
  byProject: (token: string, projectWorkspaceId: number) =>
    apiFetch<StrategicBenefitsPlan>(`/api/v1/projects/${projectWorkspaceId}/strategic-benefits-plan`, { token }),
  create: (token: string, projectWorkspaceId: number, versionPurpose: string) =>
    apiFetch<StrategicBenefitsPlan>(root, {
      method: "POST",
      token,
      headers: idempotencyHeaders(),
      body: JSON.stringify({ project_workspace_id: projectWorkspaceId, version_purpose: versionPurpose }),
    }),
  updateVersion: (
    token: string,
    plan: StrategicBenefitsPlan,
    version: BenefitsPlanVersion,
    payload: BenefitsPlanVersionUpdate
  ) =>
    apiFetch<BenefitsPlanVersion>(`${root}/${plan.id}/versions/${version.id}`, {
      method: "PUT",
      token,
      headers: versionHeaders(version.revision_version),
      body: JSON.stringify(payload),
    }),
  addBenefit: (token: string, plan: StrategicBenefitsPlan, version: BenefitsPlanVersion, payload: BenefitWrite) =>
    apiFetch<StrategicBenefit>(`${root}/${plan.id}/versions/${version.id}/benefits`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(version.revision_version), ...idempotencyHeaders() },
      body: JSON.stringify(payload),
    }),
  updateBenefit: (
    token: string,
    plan: StrategicBenefitsPlan,
    version: BenefitsPlanVersion,
    benefit: StrategicBenefit,
    payload: BenefitWrite
  ) =>
    apiFetch<StrategicBenefit>(`${root}/${plan.id}/versions/${version.id}/benefits/${benefit.id}`, {
      method: "PUT",
      token,
      headers: versionHeaders(version.revision_version),
      body: JSON.stringify(payload),
    }),
  addMeasure: (
    token: string,
    plan: StrategicBenefitsPlan,
    version: BenefitsPlanVersion,
    benefit: StrategicBenefit,
    payload: MeasureWrite
  ) =>
    apiFetch<BenefitMeasure>(`${root}/${plan.id}/versions/${version.id}/benefits/${benefit.id}/measures`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(version.revision_version), ...idempotencyHeaders() },
      body: JSON.stringify(payload),
    }),
  updateMeasure: (
    token: string,
    plan: StrategicBenefitsPlan,
    version: BenefitsPlanVersion,
    benefit: StrategicBenefit,
    measure: BenefitMeasure,
    payload: MeasureWrite
  ) =>
    apiFetch<BenefitMeasure>(
      `${root}/${plan.id}/versions/${version.id}/benefits/${benefit.id}/measures/${measure.id}`,
      {
        method: "PUT",
        token,
        headers: versionHeaders(version.revision_version),
        body: JSON.stringify(payload),
      }
    ),
  lifecycle: (
    token: string,
    plan: StrategicBenefitsPlan,
    version: BenefitsPlanVersion,
    action: "submit" | "start-review" | "return" | "complete" | "void",
    reason?: string
  ) =>
    apiFetch<BenefitsPlanVersion>(`${root}/${plan.id}/versions/${version.id}/${action}`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(version.revision_version), ...idempotencyHeaders() },
      body: reason ? JSON.stringify({ reason }) : undefined,
    }),
  newRevision: (token: string, plan: StrategicBenefitsPlan, versionPurpose: string) =>
    apiFetch<BenefitsPlanVersion>(`${root}/${plan.id}/new-revision`, {
      method: "POST",
      token,
      headers: idempotencyHeaders(),
      body: JSON.stringify({ version_purpose: versionPurpose }),
    }),
  readiness: (token: string, planId: number) => apiFetch<BenefitsReadiness>(`${root}/${planId}/readiness`, { token }),
  history: (token: string, planId: number) => apiFetch<BenefitsPlanHistory[]>(`${root}/${planId}/history`, { token }),
  traceabilityPage: async (
    token: string,
    planId: number,
    cursor?: string | null,
    limit = 50
  ): Promise<BenefitsTraceabilityPage> => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    const result = await apiFetchWithResponse<BenefitsTraceabilityRow[] | { items: BenefitsTraceabilityRow[] }>(
      `${root}/${planId}/traceability?${params}`,
      { token }
    );
    return pageFromResponse(result.data, result.response, limit);
  },
  refreshPreview: (token: string, planId: number) =>
    apiFetch<BenefitsRefreshPreview>(`${root}/${planId}/refresh-preview`, {
      method: "POST",
      token,
      headers: idempotencyHeaders(),
    }),
  refreshApply: (token: string, plan: StrategicBenefitsPlan) =>
    apiFetch<BenefitsPlanVersion>(`${root}/${plan.id}/refresh-apply`, {
      method: "POST",
      token,
      headers: {
        ...versionHeaders(plan.current_version?.revision_version ?? plan.revision_version),
        ...idempotencyHeaders(),
      },
    }),
  providerEvidence: (token: string, projectWorkspaceId: number) =>
    apiFetch<Record<string, unknown>>(`/api/v1/projects/${projectWorkspaceId}/benefits-readiness-evidence`, {
      token,
    }),
  configurations: (token: string) => apiFetch<BenefitsConfiguration[]>(`${root}/admin/configurations`, { token }),
  effectivePreview: (
    token: string,
    projectWorkspaceId: number,
    configurationId?: number,
    content?: Record<string, unknown>
  ) =>
    apiFetch<Record<string, unknown>>(`${root}/admin/configurations/effective-preview`, {
      method: "POST",
      token,
      body: JSON.stringify({
        project_workspace_id: projectWorkspaceId || null,
        configuration_id: configurationId || null,
        content_json: content || null,
      }),
    }),
  cloneConfiguration: (token: string, item: BenefitsConfiguration) =>
    apiFetch<BenefitsConfiguration>(`${root}/admin/configurations/${item.id}/clone`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(item.version), ...idempotencyHeaders() },
    }),
  updateConfiguration: (token: string, item: BenefitsConfiguration, content: Record<string, unknown>) =>
    apiFetch<BenefitsConfiguration>(`${root}/admin/configurations/${item.id}`, {
      method: "PUT",
      token,
      headers: versionHeaders(item.version),
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: BenefitsConfiguration) =>
    apiFetch<BenefitsConfiguration>(`${root}/admin/configurations/${item.id}/publish`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(item.version), ...idempotencyHeaders() },
    }),
  archiveConfiguration: (token: string, item: BenefitsConfiguration) =>
    apiFetch<BenefitsConfiguration>(`${root}/admin/configurations/${item.id}/archive`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(item.version), ...idempotencyHeaders() },
    }),
};
