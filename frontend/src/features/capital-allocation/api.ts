import { apiFetch, apiFetchWithResponse } from "../../api/client";
import { createIdempotencyKey } from "../capital-planning/api";
import type {
  StrategicAllocationComparison,
  StrategicAllocationLine,
  StrategicAllocationOptions,
  StrategicAllocationPage,
  StrategicAllocationPlan,
  StrategicAllocationPlanDraft,
  StrategicBucketClassification,
} from "./types";

const root = "/api/v1/capital-planning";
const versionHeaders = (version: number) => ({ "If-Match": `"${version}"` });
const idempotencyHeaders = (key = createIdempotencyKey()) => ({ "Idempotency-Key": key });

type RawAllocationOptions = {
  planning_cycles?: StrategicAllocationOptions["planning_cycles"];
  scope_workspaces?: StrategicAllocationOptions["workspaces"];
  portfolios?: StrategicAllocationOptions["portfolios"];
  strategic_capital_buckets?: StrategicAllocationOptions["buckets"];
  allocation_basis_options?: StrategicAllocationOptions["allocation_basis_options"];
  scope_types?: StrategicAllocationOptions["scope_options"];
  effective_configuration?: Record<string, unknown>;
};

type RawHistoryEvent = {
  event_type: string;
  outcome: string;
  actor_user_id: number | null;
  metadata?: Record<string, unknown>;
  occurred_at: string;
};

type RawAllocationPlan = Omit<StrategicAllocationPlan, "portfolio_id" | "portfolio_name" | "scope_type"> & {
  portfolio_id?: number | null;
  portfolio_name?: string | null;
  plan_revision: number;
  scope_type: string;
  portfolio_workspace_id: number | null;
  portfolio_workspace_name: string | null;
};

type RawPosition = {
  amount_by_currency?: Record<string, string | number>;
  percentage?: string | number | null;
  item_count?: number;
  evaluable?: boolean;
  source?: string;
  drilldown?: Array<Record<string, unknown>>;
};

type RawBucketComparison = {
  bucket_code: string;
  bucket_name: string;
  minimum_percentage?: string | number | null;
  target_percentage?: string | number | null;
  maximum_percentage?: string | number | null;
  minimum_amount?: string | number | null;
  target_amount?: string | number | null;
  maximum_amount?: string | number | null;
  target_currency?: string | null;
  current_demand: RawPosition;
  current_portfolio: RawPosition;
  recommended: RawPosition;
  approved: RawPosition;
  variance_vs_target_percentage?: string | number | null;
  variance_vs_target_amount?: string | number | null;
  status: string;
};

type RawComparison = {
  allocation_plan_id: number;
  allocation_plan_version?: number;
  population_definition?: Record<string, unknown>;
  classification_precedence?: string[];
  positions?: RawBucketComparison[];
  unclassified?: Record<string, RawPosition>;
  classification_coverage_percentage?: string | number;
  multi_currency?: boolean;
  normalization_warning?: string | null;
  generated_at?: string;
};

function normalizePlan(value: RawAllocationPlan | StrategicAllocationPlan): StrategicAllocationPlan {
  const raw = value as RawAllocationPlan;
  return {
    ...value,
    plan_revision: raw.plan_revision ?? value.plan_revision ?? 1,
    portfolio_workspace_id: raw.portfolio_workspace_id ?? value.portfolio_workspace_id ?? value.portfolio_id ?? null,
    portfolio_workspace_name:
      raw.portfolio_workspace_name ?? value.portfolio_workspace_name ?? value.portfolio_name ?? null,
    portfolio_id: raw.portfolio_workspace_id ?? value.portfolio_id ?? null,
    portfolio_name: raw.portfolio_workspace_name ?? value.portfolio_name ?? null,
    scope_type: (raw.scope_type || "ENTERPRISE")
      .toUpperCase()
      .replace(/-/g, "_") as StrategicAllocationPlan["scope_type"],
    readiness: value.readiness
      ? {
          ...value.readiness,
          overall:
            value.readiness.overall ?? String((value.readiness as Record<string, unknown>).status ?? "NOT_EVALUATED"),
          blockers:
            value.readiness.blockers ??
            ((value.readiness as Record<string, unknown>).blocking_issues as string[] | undefined) ??
            [],
        }
      : undefined,
    allowed_actions: value.allowed_actions ?? [],
    lines: value.lines ?? [],
  };
}

function planPayload(payload: StrategicAllocationPlanDraft) {
  return {
    name: payload.name,
    description: payload.description,
    planning_cycle_id: payload.planning_cycle_id,
    scope_workspace_id: payload.scope_workspace_id,
    portfolio_workspace_id: payload.scope_type === "PORTFOLIO" ? payload.portfolio_id : null,
    base_currency: payload.base_currency,
    allocation_basis: payload.allocation_basis,
    assumptions: payload.assumptions ?? [],
    constraints: payload.constraints ?? [],
  };
}

function normalizePosition(position: RawPosition = {}) {
  return {
    percentage: position.percentage ?? null,
    amount: null,
    amounts_by_currency: position.amount_by_currency ?? {},
    amount_by_currency: position.amount_by_currency ?? {},
    evaluable: position.evaluable ?? true,
    item_count: position.item_count ?? 0,
  };
}

function classificationFromDrilldown(
  item: Record<string, unknown>,
  bucketCode: string | null,
  source: string
): StrategicBucketClassification {
  const demandId = item.demand_id ?? item.capital_demand_id;
  const explicitTargetType = String(item.target_type ?? "").toUpperCase();
  const hasDemandIdentity =
    (demandId !== undefined && demandId !== null) ||
    (item.demand_number !== undefined && item.demand_number !== null) ||
    (item.number !== undefined && item.number !== null);
  const targetType = (
    ["DEMAND", "PROJECT", "PORTFOLIO_MEMBERSHIP"].includes(explicitTargetType)
      ? explicitTargetType
      : hasDemandIdentity
        ? "DEMAND"
        : item.portfolio_membership_id !== undefined
          ? "PORTFOLIO_MEMBERSHIP"
          : "PROJECT"
  ) as "DEMAND" | "PROJECT" | "PORTFOLIO_MEMBERSHIP";
  const targetId = Number(
    item.target_id ??
      (targetType === "DEMAND"
        ? (demandId ?? item.id)
        : targetType === "PORTFOLIO_MEMBERSHIP"
          ? (item.portfolio_membership_id ?? item.id)
          : (item.project_workspace_id ?? item.id)) ??
      0
  );
  return {
    demand_id: targetType === "DEMAND" ? targetId : null,
    demand_number: String(item.demand_number ?? item.number ?? "") || null,
    demand_name: String(item.demand_name ?? item.name ?? "") || null,
    project_workspace_id: targetType === "PROJECT" ? targetId : null,
    project_name: targetType === "PROJECT" ? String(item.project_name ?? item.name ?? "") || null : null,
    target_type: targetType,
    target_id: targetId,
    bucket_code: bucketCode,
    classification_source: String(item.classification_source ?? item.resolution_source ?? source),
    resolution_source: String(item.resolution_source ?? item.classification_source ?? source),
    rationale: String(item.rationale ?? ""),
    indicative_capital_need: (item.indicative_capital_need ?? item.amount ?? null) as string | number | null,
    currency_code: String(item.currency_code ?? item.currency ?? "") || null,
    classified: Boolean(bucketCode),
  };
}

function normalizeComparison(value: RawComparison): StrategicAllocationComparison {
  const positions = value.positions ?? [];
  const classifications = positions.flatMap((position) =>
    (position.current_demand.drilldown ?? []).map((item) =>
      classificationFromDrilldown(item, position.bucket_code, position.current_demand.source ?? "DEMAND")
    )
  );
  const unclassifiedDemand = value.unclassified?.demand ?? {};
  const unclassifiedDrilldown = unclassifiedDemand.drilldown ?? [];
  classifications.push(...unclassifiedDrilldown.map((item) => classificationFromDrilldown(item, null, "UNCLASSIFIED")));
  return {
    allocation_plan_id: value.allocation_plan_id,
    generated_at: value.generated_at,
    population_definition: value.population_definition
      ? JSON.stringify(value.population_definition)
      : "Backend-governed eligible Capital Demand population.",
    classification_precedence: value.classification_precedence ?? [],
    evaluable: !value.multi_currency,
    warnings: value.normalization_warning ? [value.normalization_warning] : [],
    unclassified: {
      ...normalizePosition(unclassifiedDemand),
      count: Number(unclassifiedDemand.item_count ?? 0),
    },
    buckets: positions.map((position) => ({
      bucket_code: position.bucket_code,
      bucket_name: position.bucket_name,
      target: {
        percentage: position.target_percentage ?? null,
        amount: position.target_amount ?? null,
        amounts_by_currency:
          position.target_amount !== null && position.target_amount !== undefined && position.target_currency
            ? { [position.target_currency]: position.target_amount }
            : {},
        evaluable: true,
        item_count: 1,
      },
      current_demand: normalizePosition(position.current_demand),
      current_portfolio: normalizePosition(position.current_portfolio),
      recommended: normalizePosition(position.recommended),
      approved: normalizePosition(position.approved),
      variance_percentage: position.variance_vs_target_percentage ?? null,
      variance_amount: position.variance_vs_target_amount ?? null,
      status: position.status,
      drilldown: {
        demands: position.current_demand.drilldown ?? [],
        portfolio_projects: position.current_portfolio.drilldown ?? [],
        recommended_projects: position.recommended.drilldown ?? [],
        approved_projects: position.approved.drilldown ?? [],
      },
    })),
    classifications,
    readiness: {
      overall: Number(value.classification_coverage_percentage ?? 0) >= 100 ? "READY" : "ATTENTION",
      ready: Number(value.classification_coverage_percentage ?? 0) >= 100,
      classification_coverage_percentage: value.classification_coverage_percentage ?? 0,
      dimensions: {
        CLASSIFICATION_COVERAGE: value.classification_coverage_percentage ?? 0,
        CURRENCY_EVALUABILITY: value.multi_currency ? "NOT_EVALUABLE" : "EVALUABLE",
      },
      warnings: value.normalization_warning ? [value.normalization_warning] : [],
    },
  };
}

async function listPage<T>(token: string, path: string): Promise<StrategicAllocationPage<T>> {
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

function queryString(values: Record<string, string | number | null | undefined>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== null && value !== undefined && value !== "") query.set(key, String(value));
  }
  return query.toString();
}

export const strategicAllocationApi = {
  options: async (token: string, workspaceId?: number | null) => {
    const value = await apiFetch<RawAllocationOptions>(
      `${root}/allocation-options${workspaceId ? `?scope_workspace_id=${workspaceId}` : ""}`,
      { token }
    );
    return {
      planning_cycles: value.planning_cycles ?? [],
      workspaces: (value.scope_workspaces ?? []).map((workspace) => ({
        ...workspace,
        workspace_type_code: (workspace.workspace_type_code ?? workspace.type ?? "").toUpperCase().replace(/-/g, "_"),
      })),
      portfolios: value.portfolios ?? [],
      buckets: (value.strategic_capital_buckets ?? []).map((bucket) => {
        const raw = bucket as StrategicAllocationOptions["buckets"][number] & { code?: string; name?: string };
        return {
          ...raw,
          bucket_code: raw.bucket_code ?? raw.code ?? "",
          bucket_name: raw.bucket_name ?? raw.name ?? raw.bucket_code ?? raw.code ?? "Unnamed Bucket",
        };
      }),
      allocation_basis_options: value.allocation_basis_options ?? ["PERCENTAGE"],
      scope_options: (value.scope_types ?? ["ENTERPRISE", "BUSINESS_UNIT", "PORTFOLIO"]).map((item) =>
        item.toUpperCase().replace(/-/g, "_")
      ) as StrategicAllocationOptions["scope_options"],
      policy: value.effective_configuration ?? {},
    } satisfies StrategicAllocationOptions;
  },
  listPlans: (
    token: string,
    filters: { planning_cycle_id?: number | string; status?: string; page?: number; page_size?: number } = {}
  ) =>
    listPage<RawAllocationPlan>(
      token,
      `${root}/allocation-plans${queryString(filters) ? `?${queryString(filters)}` : ""}`
    ).then((page) => ({ ...page, items: page.items.map(normalizePlan) })),
  createPlan: async (token: string, payload: StrategicAllocationPlanDraft, idempotencyKey = createIdempotencyKey()) =>
    normalizePlan(
      await apiFetch<RawAllocationPlan>(`${root}/allocation-plans`, {
        method: "POST",
        token,
        headers: idempotencyHeaders(idempotencyKey),
        body: JSON.stringify(planPayload(payload)),
      })
    ),
  readPlan: async (token: string, planId: number) =>
    normalizePlan(await apiFetch<RawAllocationPlan>(`${root}/allocation-plans/${planId}`, { token })),
  updatePlan: async (token: string, plan: StrategicAllocationPlan, payload: StrategicAllocationPlanDraft) =>
    normalizePlan(
      await apiFetch<RawAllocationPlan>(`${root}/allocation-plans/${plan.id}`, {
        method: "PUT",
        token,
        headers: versionHeaders(plan.revision_version),
        body: JSON.stringify(planPayload(payload)),
      })
    ),
  replaceLines: async (token: string, plan: StrategicAllocationPlan, lines: StrategicAllocationLine[]) =>
    normalizePlan(
      await apiFetch<RawAllocationPlan>(`${root}/allocation-plans/${plan.id}/lines`, {
        method: "PUT",
        token,
        headers: versionHeaders(plan.revision_version),
        body: JSON.stringify({ lines }),
      })
    ),
  action: (
    token: string,
    plan: StrategicAllocationPlan,
    action: "submit" | "return" | "endorse" | "review/start",
    payload: Record<string, unknown> = {},
    idempotencyKey = createIdempotencyKey()
  ) =>
    apiFetch<RawAllocationPlan>(`${root}/allocation-plans/${plan.id}/${action}`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(plan.revision_version), ...idempotencyHeaders(idempotencyKey) },
      body: JSON.stringify(payload),
    }).then(normalizePlan),
  newRevision: (token: string, plan: StrategicAllocationPlan, idempotencyKey = createIdempotencyKey()) =>
    apiFetch<RawAllocationPlan>(`${root}/allocation-plans/${plan.id}/revisions`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(plan.revision_version), ...idempotencyHeaders(idempotencyKey) },
    }).then(normalizePlan),
  replaceClassifications: (
    token: string,
    plan: StrategicAllocationPlan,
    classifications: StrategicBucketClassification[],
    idempotencyKey = createIdempotencyKey()
  ) =>
    apiFetch<{ allocation_plan: RawAllocationPlan; classifications: StrategicBucketClassification[] }>(
      `${root}/allocation-plans/${plan.id}/classifications`,
      {
        method: "PUT",
        token,
        headers: { ...versionHeaders(plan.revision_version), ...idempotencyHeaders(idempotencyKey) },
        body: JSON.stringify({
          classifications: classifications.flatMap((classification) => {
            const targetId =
              classification.target_id ?? classification.demand_id ?? classification.project_workspace_id;
            if (!targetId || !classification.bucket_code) return [];
            return [
              {
                target_type: classification.target_type ?? (classification.demand_id ? "DEMAND" : "PROJECT"),
                target_id: targetId,
                bucket_code: classification.bucket_code,
                rationale: classification.rationale ?? "",
              },
            ];
          }),
        }),
      }
    ).then((result) => normalizePlan(result.allocation_plan)),
  comparison: async (token: string, planId: number) =>
    normalizeComparison(await apiFetch<RawComparison>(`${root}/allocation-plans/${planId}/comparison`, { token })),
  history: (token: string, planId: number) =>
    apiFetch<RawHistoryEvent[]>(`${root}/allocation-plans/${planId}/history`, { token }).then((events) =>
      events.map((event) => ({
        event_type: event.event_type,
        occurred_at: event.occurred_at,
        actor_name:
          typeof event.metadata?.actor_name === "string"
            ? event.metadata.actor_name
            : event.actor_user_id
              ? `User ${event.actor_user_id}`
              : null,
        from_status:
          typeof event.metadata?.from_status === "string"
            ? event.metadata.from_status
            : Array.isArray(event.metadata?.from)
              ? String(event.metadata.from.join(" / "))
              : null,
        to_status: typeof event.metadata?.to === "string" ? event.metadata.to : null,
        detail: { outcome: event.outcome, ...(event.metadata ?? {}) },
      }))
    ),
};
