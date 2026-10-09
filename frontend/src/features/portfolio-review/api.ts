import { apiFetch, apiFetchWithResponse } from "../../api/client";
import { createIdempotencyKey } from "../capital-planning/api";
import type {
  PortfolioReviewAction,
  PortfolioReviewActionDraft,
  PortfolioReviewAllocationBucket,
  PortfolioReviewAllocationContext,
  PortfolioReviewBudgetResources,
  PortfolioReviewComparison,
  PortfolioReviewConclusion,
  PortfolioReviewConfiguration,
  PortfolioReviewConfigurationPreview,
  PortfolioReviewGateStatus,
  PortfolioReviewHistoryEvent,
  PortfolioReviewOptions,
  PortfolioReviewPage,
  PortfolioReviewProjectMatrix,
  PortfolioReviewProjectRow,
  PortfolioReviewReadiness,
  PortfolioReviewSession,
  PortfolioReviewSessionDraft,
  PortfolioReviewSnapshot,
  PortfolioReviewSnapshotSource,
  PortfolioReviewTrends,
} from "./types";

const root = "/api/v1/portfolio-reviews";
const actionRoot = "/api/v1/portfolio-review-actions";

const versionHeaders = (version: number) => ({ "If-Match": `"${version}"` });
const idempotencyHeaders = (key = createIdempotencyKey()) => ({ "Idempotency-Key": key });

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function numberValue(...values: unknown[]) {
  for (const value of values) {
    if (value !== null && value !== undefined && value !== "") {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  return 0;
}

function normalizeReadiness(value: unknown): PortfolioReviewReadiness {
  const item = record(value);
  const overall = String(item.overall ?? item.status ?? item.overall_review_readiness ?? "NOT_EVALUATED");
  return {
    overall,
    ready: Boolean(item.ready ?? item.is_ready ?? overall === "READY"),
    dimensions: record(
      item.components ?? item.dimensions ?? item.checks ?? item.readiness_by_dimension
    ) as PortfolioReviewReadiness["dimensions"],
    blockers: strings(item.blockers ?? item.blocking_issues),
    warnings: strings(item.warnings),
  };
}

function normalizeAction(value: unknown): PortfolioReviewAction {
  const item = record(value);
  return {
    ...(item as unknown as PortfolioReviewAction),
    id: numberValue(item.id, item.action_id),
    action_id: numberValue(item.action_id, item.id),
    review_session_id: numberValue(item.review_session_id, item.portfolio_review_session_id),
    subject_type: String(item.subject_type ?? "PORTFOLIO"),
    subject_id: (item.subject_id as string | number | null | undefined) ?? null,
    subject_key: item.subject_key == null ? null : String(item.subject_key),
    subject_name: item.subject_name == null ? null : String(item.subject_name),
    action_type: String(item.action_type ?? "OTHER_CONFIGURED_ACTION"),
    rationale: String(item.rationale ?? ""),
    priority: String(item.priority ?? "MEDIUM"),
    owner: item.owner == null ? (item.owner_name == null ? null : String(item.owner_name)) : String(item.owner),
    owner_user_id: item.owner_user_id == null ? null : numberValue(item.owner_user_id),
    due_date: item.due_date == null ? null : String(item.due_date),
    status: String(item.status ?? "OPEN"),
    requested_source_authority:
      item.requested_source_authority == null ? null : String(item.requested_source_authority),
    source_evidence_references: Array.isArray(item.source_evidence_references_json ?? item.source_evidence_references)
      ? ((item.source_evidence_references_json ?? item.source_evidence_references) as Array<Record<string, unknown>>)
      : [],
    execution_reference: item.execution_reference == null ? null : String(item.execution_reference),
    revision_version: numberValue(item.revision_version, item.version, 1),
    allowed_actions: strings(item.allowed_actions),
  };
}

function normalizeConclusion(value: unknown): PortfolioReviewConclusion {
  const item = record(value);
  return {
    ...(item as unknown as PortfolioReviewConclusion),
    id: numberValue(item.id) || undefined,
    conclusion_type: String(item.conclusion_type ?? "NO_MATERIAL_CHANGE"),
    rationale: String(item.rationale ?? ""),
    conditions: Array.isArray(item.conditions_json ?? item.conditions)
      ? ((item.conditions_json ?? item.conditions) as Array<Record<string, unknown>>)
      : [],
    recorded_by: (item.created_by_user_id ?? item.recorded_by) as number | string | null | undefined,
    recorded_at: item.created_at == null ? null : String(item.created_at),
    revision_version: numberValue(item.revision_version, 1),
  };
}

function normalizeSources(value: unknown): PortfolioReviewSnapshotSource[] {
  if (Array.isArray(value)) {
    return value.map((entry) => {
      const item = record(entry);
      return {
        ...(item as PortfolioReviewSnapshotSource),
        source_type: String(item.source_type ?? item.source ?? item.code ?? "SOURCE"),
        source_id: ((item.source_id ?? item.record_id) as string | number | null | undefined) ?? null,
        source_version: ((item.source_version ?? item.version) as string | number | null | undefined) ?? null,
        source_hash:
          item.source_hash == null ? (item.hash == null ? null : String(item.hash)) : String(item.source_hash),
        source_current: Boolean(item.source_current ?? item.current ?? true),
      };
    });
  }
  return Object.entries(record(value)).map(([sourceType, sourceValue]) => {
    const item = record(sourceValue);
    return {
      ...(item as PortfolioReviewSnapshotSource),
      source_type: sourceType,
      source_id: ((item.source_id ?? item.record_id) as string | number | null | undefined) ?? null,
      source_version: ((item.source_version ?? item.version) as string | number | null | undefined) ?? null,
      source_hash: item.source_hash == null ? (item.hash == null ? null : String(item.hash)) : String(item.source_hash),
      source_current: Boolean(item.source_current ?? item.current ?? true),
    };
  });
}

function normalizeSnapshot(value: unknown): PortfolioReviewSnapshot | null {
  if (!value || typeof value !== "object") return null;
  const item = record(value);
  const payload = record(item.payload_json ?? item.snapshot_json ?? item.snapshot ?? item.payload);
  return {
    ...(item as unknown as PortfolioReviewSnapshot),
    id: numberValue(item.id, item.snapshot_id) || undefined,
    snapshot_id: numberValue(item.snapshot_id, item.id) || undefined,
    snapshot_hash:
      item.snapshot_hash == null
        ? item.candidate_snapshot_hash == null
          ? item.hash == null
            ? null
            : String(item.hash)
          : String(item.candidate_snapshot_hash)
        : String(item.snapshot_hash),
    source_current: Boolean(item.source_current ?? item.is_current ?? true),
    source_as_of: (item.source_as_of ?? payload.source_as_of) as string | null | undefined,
    persisted: item.persisted == null ? undefined : Boolean(item.persisted),
    portfolio: record(item.portfolio ?? payload.portfolio),
    membership: record(item.membership ?? payload.membership),
    evaluation: record(item.evaluation ?? payload.evaluation),
    allocation: normalizeAllocation({
      ...record(item.allocation ?? payload.allocation),
      allocation_plan: item.allocation_plan ?? payload.allocation_plan,
    }),
    budget: record(item.budget ?? payload.budget),
    resources: record(item.resources ?? payload.resources),
    scenario_convergence: record(item.scenario_convergence ?? payload.scenario_convergence),
    gate: record(item.gate ?? payload.gate_context ?? payload.gate),
    risk_readiness: record(item.risk_readiness ?? payload.risk_readiness),
    summary: record(item.summary ?? payload.portfolio_summary ?? payload.summary),
    sources: normalizeSources(
      item.sources ?? item.source_references ?? item.source_index ?? item.source_index_json ?? payload.sources
    ),
    warnings: strings(item.warnings ?? item.warnings_json ?? payload.warnings),
    blockers: strings(item.blockers ?? item.blockers_json ?? payload.blockers),
    changes: Array.isArray(item.changes ?? item.deltas)
      ? ((item.changes ?? item.deltas) as PortfolioReviewSnapshot["changes"])
      : [],
    payload,
  };
}

function normalizeSession(value: unknown): PortfolioReviewSession {
  const item = record(value);
  const snapshot = normalizeSnapshot(item.snapshot ?? item.current_snapshot ?? item.snapshot_preview);
  return {
    ...(item as unknown as PortfolioReviewSession),
    id: numberValue(item.id, item.review_session_id),
    review_session_id: numberValue(item.review_session_id, item.id),
    review_number: String(item.review_number ?? item.session_number ?? `PRV-${numberValue(item.id)}`),
    portfolio_id: numberValue(item.portfolio_id, item.portfolio_workspace_id),
    portfolio_workspace_id: numberValue(item.portfolio_workspace_id, item.portfolio_id),
    portfolio_name:
      item.portfolio_name == null
        ? item.portfolio_workspace_name == null
          ? null
          : String(item.portfolio_workspace_name)
        : String(item.portfolio_name),
    planning_cycle_id: item.planning_cycle_id == null ? null : numberValue(item.planning_cycle_id),
    allocation_plan_id: item.allocation_plan_id == null ? null : numberValue(item.allocation_plan_id),
    review_type: String(item.review_type ?? "SCHEDULED"),
    review_date: String(item.review_date ?? item.planned_review_date ?? ""),
    review_period_start: item.review_period_start == null ? null : String(item.review_period_start),
    review_period_end: item.review_period_end == null ? null : String(item.review_period_end),
    next_planned_review_date: item.next_planned_review_date == null ? null : String(item.next_planned_review_date),
    status: String(item.status ?? "DRAFT"),
    agenda: Array.isArray(item.agenda)
      ? item.agenda.map((value) => {
          const agenda = record(value);
          return {
            ...agenda,
            code: String(agenda.code ?? ""),
            label: String(agenda.title ?? agenda.label ?? agenda.code ?? ""),
          } as PortfolioReviewSession["agenda"][number];
        })
      : [],
    conclusions: Array.isArray(item.conclusions) ? item.conclusions.map(normalizeConclusion) : [],
    snapshot_id:
      item.current_snapshot_id == null
        ? item.snapshot_id == null
          ? (snapshot?.id ?? null)
          : numberValue(item.snapshot_id)
        : numberValue(item.current_snapshot_id),
    snapshot_hash:
      item.current_snapshot_hash == null
        ? item.snapshot_hash == null
          ? (snapshot?.snapshot_hash ?? null)
          : String(item.snapshot_hash)
        : String(item.current_snapshot_hash),
    snapshot,
    readiness: normalizeReadiness(item.readiness ?? item.review_readiness),
    summary: record(item.summary ?? item.portfolio_summary ?? snapshot?.summary),
    actions: Array.isArray(item.actions) ? item.actions.map(normalizeAction) : [],
    source_current:
      item.source_current == null
        ? item.snapshot_stale == null
          ? Boolean(snapshot?.source_current ?? true)
          : !Boolean(item.snapshot_stale)
        : Boolean(item.source_current),
    revision_version: numberValue(item.revision_version, item.version, 1),
    allowed_actions: strings(item.allowed_actions),
  };
}

function normalizePage<T>(
  body:
    | T[]
    | { items?: T[]; results?: T[]; page?: number; page_size?: number; total?: number; next_cursor?: string | null },
  headerCursor: string | null,
  normalize: (value: T) => T
): PortfolioReviewPage<T> {
  const items = Array.isArray(body) ? body : (body.items ?? body.results ?? []);
  return {
    items: items.map(normalize),
    page: Array.isArray(body) ? 1 : (body.page ?? 1),
    pageSize: Array.isArray(body) ? body.length : (body.page_size ?? items.length),
    total: Array.isArray(body) ? body.length : (body.total ?? items.length),
    nextCursor: headerCursor ?? (Array.isArray(body) ? null : (body.next_cursor ?? null)),
  };
}

function query(values: Record<string, string | number | boolean | null | undefined>) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
  }
  return params.toString();
}

function position(value: unknown) {
  const item = record(value);
  return {
    percentage: (item.percentage as string | number | null | undefined) ?? null,
    amount: (item.amount as string | number | null | undefined) ?? null,
    amounts_by_currency: record(item.amounts_by_currency ?? item.amount_by_currency) as Record<string, string | number>,
    count: numberValue(item.count, item.item_count),
    evaluable: item.evaluable == null ? true : Boolean(item.evaluable),
  };
}

function normalizeAllocation(value: unknown): PortfolioReviewAllocationContext {
  const item = record(value);
  const comparison = record(item.comparison);
  const plan = record(item.allocation_plan);
  const content = Object.keys(comparison).length ? comparison : item;
  const rawBuckets = (content.buckets ?? content.positions ?? []) as unknown[];
  const unclassified = record(content.unclassified);
  const unclassifiedByPosition = Object.fromEntries(
    ["demand", "portfolio", "recommended", "approved"]
      .filter((key) => unclassified[key] != null)
      .map((key) => [key, position(unclassified[key])])
  );
  return {
    allocation_plan_id:
      (item.allocation_plan_id ?? plan.id) == null ? null : numberValue(item.allocation_plan_id, plan.id),
    allocation_plan_number:
      (item.allocation_plan_number ?? plan.allocation_plan_number ?? plan.plan_number) == null
        ? null
        : String(item.allocation_plan_number ?? plan.allocation_plan_number ?? plan.plan_number),
    allocation_plan_version:
      (item.allocation_plan_version ?? plan.revision_version ?? plan.version) == null
        ? null
        : numberValue(item.allocation_plan_version, plan.revision_version, plan.version),
    allocation_plan_hash:
      (item.allocation_plan_hash ?? plan.plan_hash ?? plan.hash) == null
        ? null
        : String(item.allocation_plan_hash ?? plan.plan_hash ?? plan.hash),
    source_current: Boolean(item.source_current ?? content.source_current ?? true),
    multi_currency: Boolean(item.multi_currency ?? content.multi_currency),
    normalization_warning:
      (item.normalization_warning ?? content.normalization_warning) == null
        ? null
        : String(item.normalization_warning ?? content.normalization_warning),
    buckets: rawBuckets.map((raw): PortfolioReviewAllocationBucket => {
      const bucket = record(raw);
      return {
        bucket_code: String(bucket.bucket_code ?? bucket.code ?? "UNCLASSIFIED"),
        bucket_name: String(bucket.bucket_name ?? bucket.name ?? bucket.bucket_code ?? "Unclassified"),
        target: position(
          bucket.target ?? {
            percentage: bucket.target_percentage,
            amount: bucket.target_amount,
            amount_by_currency:
              bucket.target_amount_by_currency ??
              (bucket.target_currency && bucket.target_amount != null
                ? { [String(bucket.target_currency)]: bucket.target_amount }
                : {}),
          }
        ),
        current_demand: position(bucket.current_demand),
        current_portfolio: position(bucket.current_portfolio),
        recommended: position(bucket.recommended),
        approved: position(bucket.approved),
        variance_percentage: (bucket.variance_percentage ?? bucket.variance_vs_target_percentage ?? null) as
          | string
          | number
          | null,
        variance_amount: (bucket.variance_amount ?? bucket.variance_vs_target_amount ?? null) as string | number | null,
        status: String(bucket.status ?? "NOT_EVALUATED"),
      };
    }),
    unclassified: position(unclassified.portfolio ?? unclassified),
    unclassified_by_position: unclassifiedByPosition,
    warnings: strings(item.warnings ?? content.warnings),
  };
}

export const portfolioReviewApi = {
  options: (token: string, portfolioId?: number | null) =>
    apiFetch<PortfolioReviewOptions>(`${root}/options${portfolioId ? `?portfolio_workspace_id=${portfolioId}` : ""}`, {
      token,
    }),
  listSessions: async (
    token: string,
    filters: {
      portfolio_id?: number | string;
      status?: string;
      review_type?: string;
      page?: number;
      page_size?: number;
    } = {}
  ) => {
    const { portfolio_id, ...remaining } = filters;
    const search = query({ ...remaining, portfolio_workspace_id: portfolio_id });
    const result = await apiFetchWithResponse<
      | PortfolioReviewSession[]
      | {
          items?: PortfolioReviewSession[];
          results?: PortfolioReviewSession[];
          page?: number;
          page_size?: number;
          total?: number;
          next_cursor?: string | null;
        }
    >(`${root}${search ? `?${search}` : ""}`, { token });
    return normalizePage(
      result.data,
      result.response.headers?.get("X-Next-Cursor") ?? null,
      (item) => normalizeSession(item) as PortfolioReviewSession
    );
  },
  createSession: (token: string, payload: PortfolioReviewSessionDraft, idempotencyKey = createIdempotencyKey()) =>
    apiFetch<PortfolioReviewSession>(root, {
      method: "POST",
      token,
      headers: idempotencyHeaders(idempotencyKey),
      body: JSON.stringify(payload),
    }).then(normalizeSession),
  readSession: (token: string, sessionId: number) =>
    apiFetch<PortfolioReviewSession>(`${root}/${sessionId}`, { token }).then(normalizeSession),
  updateSession: (token: string, session: PortfolioReviewSession, payload: Record<string, unknown>) =>
    apiFetch<PortfolioReviewSession>(`${root}/${session.id}`, {
      method: "PUT",
      token,
      headers: versionHeaders(session.revision_version),
      body: JSON.stringify(payload),
    }).then(normalizeSession),
  prepare: (token: string, session: PortfolioReviewSession) =>
    apiFetch<PortfolioReviewSession>(`${root}/${session.id}/prepare`, {
      method: "POST",
      token,
      headers: versionHeaders(session.revision_version),
    }).then(normalizeSession),
  snapshotPreview: (token: string, session: PortfolioReviewSession) =>
    apiFetch<PortfolioReviewSnapshot>(`${root}/${session.id}/snapshot-preview`, {
      method: "POST",
      token,
      headers: versionHeaders(session.revision_version),
    }).then((value) => normalizeSnapshot(value) as PortfolioReviewSnapshot),
  freezeSnapshot: async (token: string, session: PortfolioReviewSession, idempotencyKey = createIdempotencyKey()) => {
    await apiFetch<PortfolioReviewSnapshot>(`${root}/${session.id}/freeze-snapshot`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(session.revision_version), ...idempotencyHeaders(idempotencyKey) },
      body: JSON.stringify({ reason: "Periodic Portfolio Review governed freeze" }),
    });
    return apiFetch<PortfolioReviewSession>(`${root}/${session.id}`, { token }).then(normalizeSession);
  },
  startReview: (token: string, session: PortfolioReviewSession) =>
    apiFetch<PortfolioReviewSession>(`${root}/${session.id}/start-review`, {
      method: "POST",
      token,
      headers: versionHeaders(session.revision_version),
    }).then(normalizeSession),
  complete: (
    token: string,
    session: PortfolioReviewSession,
    payload: Record<string, unknown> = {},
    idempotencyKey = createIdempotencyKey()
  ) =>
    apiFetch<PortfolioReviewSession>(`${root}/${session.id}/complete`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(session.revision_version), ...idempotencyHeaders(idempotencyKey) },
      body: JSON.stringify(payload),
    }).then(normalizeSession),
  transition: (
    token: string,
    session: PortfolioReviewSession,
    transition: "return" | "cancel" | "supersede",
    payload: { reason: string; replacement_review_session_id?: number | null },
    idempotencyKey = createIdempotencyKey()
  ) =>
    apiFetch<PortfolioReviewSession>(`${root}/${session.id}/${transition}`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(session.revision_version), ...idempotencyHeaders(idempotencyKey) },
      body: JSON.stringify(payload),
    }).then(normalizeSession),
  projectMatrix: async (
    token: string,
    sessionId: number,
    filters: Record<string, string | number | boolean | null | undefined> = {}
  ): Promise<PortfolioReviewProjectMatrix> => {
    const search = query(filters);
    const result = await apiFetchWithResponse<
      PortfolioReviewProjectRow[] | (Partial<PortfolioReviewProjectMatrix> & { results?: PortfolioReviewProjectRow[] })
    >(`${root}/${sessionId}/project-matrix${search ? `?${search}` : ""}`, { token });
    const page = normalizePage(
      result.data as
        | PortfolioReviewProjectRow[]
        | {
            items?: PortfolioReviewProjectRow[];
            results?: PortfolioReviewProjectRow[];
            page?: number;
            page_size?: number;
            total?: number;
            next_cursor?: string | null;
          },
      result.response.headers?.get("X-Next-Cursor") ?? null,
      (value) => {
        const item = record(value);
        const approved = record(item.approved_amount_context);
        const actions = Array.isArray(item.review_actions) ? item.review_actions.map(normalizeAction) : [];
        return {
          ...item,
          project_id: (item.project_workspace_id ?? item.project_id) as number | string,
          project_number: (item.project_code ?? item.project_number) as string | null | undefined,
          project_name: String(item.project_name ?? ""),
          review_actions: actions,
          approved_amounts_by_currency:
            item.approved_amounts_by_currency ??
            (approved.currency && approved.amount != null ? { [String(approved.currency)]: approved.amount } : {}),
        } as PortfolioReviewProjectRow;
      }
    );
    const metadata = Array.isArray(result.data) ? {} : result.data;
    return { ...metadata, ...page } as PortfolioReviewProjectMatrix;
  },
  allocation: (token: string, sessionId: number) =>
    apiFetch<PortfolioReviewAllocationContext>(`${root}/${sessionId}/allocation`, { token }).then(normalizeAllocation),
  budgetResources: (token: string, sessionId: number) =>
    apiFetch<PortfolioReviewBudgetResources>(`${root}/${sessionId}/budget-resources`, { token }).then((value) => ({
      ...value,
      budget: record(value.budget),
      resources: record(value.resources),
      compatibility: record(value.compatibility),
      source_current: Boolean(value.source_current ?? true),
      warnings: strings(value.warnings),
      blockers: strings(value.blockers),
    })),
  gateStatus: (token: string, sessionId: number) =>
    apiFetch<PortfolioReviewGateStatus>(`${root}/${sessionId}/gate-status`, { token }).then((value) => ({
      ...value,
      summary: record(value.summary ?? (value as unknown as Record<string, unknown>).distribution),
      preparation: record(value.preparation ?? (value as unknown as Record<string, unknown>).gate_preparation),
      projects: Array.isArray(value.projects)
        ? value.projects
        : Array.isArray((value as unknown as Record<string, unknown>).investment_decisions)
          ? ((value as unknown as Record<string, unknown>).investment_decisions as Array<Record<string, unknown>>)
          : [],
      source_current: Boolean(value.source_current ?? true),
      warnings: strings(value.warnings),
      blockers: strings(value.blockers),
    })),
  history: (token: string, sessionId: number) =>
    apiFetch<PortfolioReviewHistoryEvent[] | { items: PortfolioReviewHistoryEvent[] }>(`${root}/${sessionId}/history`, {
      token,
    }).then((value) =>
      (Array.isArray(value) ? value : (value.items ?? [])).map((event) => ({
        ...event,
        detail: event.detail ?? ((event as unknown as Record<string, unknown>).metadata as Record<string, unknown>),
        actor_name:
          event.actor_name ??
          ((event as unknown as Record<string, unknown>).actor_user_id == null
            ? null
            : `User ${(event as unknown as Record<string, unknown>).actor_user_id}`),
      }))
    ),
  compare: (token: string, sessionId: number, otherSessionId: number) =>
    apiFetch<PortfolioReviewComparison>(`${root}/${sessionId}/compare/${otherSessionId}`, { token }).then((value) => ({
      ...value,
      current_review_id: numberValue(value.current_review_id, sessionId),
      previous_review_id: numberValue(
        value.previous_review_id,
        (value as unknown as Record<string, unknown>).other_review_id,
        otherSessionId
      ),
      deltas: record(value.deltas),
      warnings: strings(value.warnings),
    })),
  trends: (token: string, portfolioId?: number | null) =>
    apiFetch<PortfolioReviewTrends | PortfolioReviewTrends["items"]>(
      `${root}/trends${portfolioId ? `?portfolio_workspace_id=${portfolioId}` : ""}`,
      { token }
    ).then((value) =>
      Array.isArray(value)
        ? { items: value, warnings: [] }
        : {
            ...value,
            items: (
              value.items ??
              ((value as unknown as Record<string, unknown>).points as PortfolioReviewTrends["items"] | undefined) ??
              []
            ).map((point) => ({
              ...point,
              review_id: numberValue(point.review_id, point.review_session_id),
              portfolio_count: numberValue(point.portfolio_count, point.portfolio_project_count),
              open_action_count: numberValue(point.open_action_count, point.open_action_count_at_close),
            })),
            warnings: strings(value.warnings),
          }
    ),
  listActions: async (token: string, sessionId: number) => {
    const actions: PortfolioReviewAction[] = [];
    let page = 1;
    while (true) {
      const body = await apiFetch<
        PortfolioReviewAction[] | { items?: PortfolioReviewAction[]; total?: number; page?: number; page_size?: number }
      >(`${actionRoot}?review_session_id=${sessionId}&page=${page}&page_size=250`, { token });
      const items = Array.isArray(body) ? body : (body.items ?? []);
      actions.push(...items.map(normalizeAction));
      if (Array.isArray(body) || !items.length || actions.length >= (body.total ?? actions.length)) return actions;
      page += 1;
    }
  },
  createConclusion: (token: string, session: PortfolioReviewSession, payload: PortfolioReviewConclusion) =>
    apiFetch<PortfolioReviewConclusion>(`${root}/${session.id}/conclusions`, {
      method: "POST",
      token,
      headers: versionHeaders(session.revision_version),
      body: JSON.stringify({
        conclusion_type: payload.conclusion_type,
        rationale: payload.rationale,
        conditions: payload.conditions ?? [],
      }),
    }).then(normalizeConclusion),
  createAction: (
    token: string,
    session: PortfolioReviewSession,
    payload: PortfolioReviewActionDraft,
    idempotencyKey = createIdempotencyKey()
  ) =>
    apiFetch<PortfolioReviewAction>(`${root}/${session.id}/actions`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(session.revision_version), ...idempotencyHeaders(idempotencyKey) },
      body: JSON.stringify(payload),
    }).then(normalizeAction),
  updateAction: (token: string, action: PortfolioReviewAction, payload: Record<string, unknown>) =>
    apiFetch<PortfolioReviewAction>(`${actionRoot}/${action.id}`, {
      method: "PUT",
      token,
      headers: versionHeaders(action.revision_version),
      body: JSON.stringify(payload),
    }).then(normalizeAction),
  approveAction: (token: string, action: PortfolioReviewAction, idempotencyKey = createIdempotencyKey()) =>
    apiFetch<PortfolioReviewAction>(`${actionRoot}/${action.id}/approve`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(action.revision_version), ...idempotencyHeaders(idempotencyKey) },
    }).then(normalizeAction),
  dispatchAction: (token: string, action: PortfolioReviewAction, idempotencyKey = createIdempotencyKey()) =>
    apiFetch<PortfolioReviewAction>(`${actionRoot}/${action.id}/dispatch`, {
      method: "POST",
      token,
      headers: { ...versionHeaders(action.revision_version), ...idempotencyHeaders(idempotencyKey) },
    }).then(normalizeAction),
  configurations: (token: string) =>
    apiFetch<PortfolioReviewConfiguration[]>(`${root}/admin/configurations`, { token }),
  previewConfiguration: (
    token: string,
    portfolioId: number | null,
    configurationId?: number | null,
    content?: Record<string, unknown>
  ) =>
    apiFetch<PortfolioReviewConfigurationPreview>(`${root}/admin/preview`, {
      method: "POST",
      token,
      body: JSON.stringify({
        portfolio_id: portfolioId,
        portfolio_workspace_id: portfolioId,
        configuration_id: configurationId ?? null,
        content_json: content,
      }),
    }),
  cloneConfiguration: (token: string, item: PortfolioReviewConfiguration, targetWorkspaceId: number | null = null) =>
    apiFetch<PortfolioReviewConfiguration>(`${root}/admin/configurations/${item.id}/clone`, {
      method: "POST",
      token,
      headers: versionHeaders(item.version),
      body: JSON.stringify({ target_workspace_id: targetWorkspaceId }),
    }),
  updateConfiguration: (token: string, item: PortfolioReviewConfiguration, content: Record<string, unknown>) =>
    apiFetch<PortfolioReviewConfiguration>(`${root}/admin/configurations/${item.id}`, {
      method: "PUT",
      token,
      headers: versionHeaders(item.version),
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: PortfolioReviewConfiguration) =>
    apiFetch<PortfolioReviewConfiguration>(`${root}/admin/configurations/${item.id}/publish`, {
      method: "POST",
      token,
      headers: versionHeaders(item.version),
    }),
  archiveConfiguration: (token: string, item: PortfolioReviewConfiguration) =>
    apiFetch<PortfolioReviewConfiguration>(`${root}/admin/configurations/${item.id}/archive`, {
      method: "POST",
      token,
      headers: versionHeaders(item.version),
    }),
};
