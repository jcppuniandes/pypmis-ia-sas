import { BarChart3, CheckCircle2, Clock3, FilePlus2, Layers3, RefreshCcw, Save, Send, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { strategicNodeForView } from "../enterprise-strategy/navigation/strategicNavigationBlueprint";
import { portfolioReviewApi } from "./api";
import type {
  PortfolioReviewAction,
  PortfolioReviewActionDraft,
  PortfolioReviewAllocationContext,
  PortfolioReviewBudgetResources,
  PortfolioReviewComparison,
  PortfolioReviewGateStatus,
  PortfolioReviewHistoryEvent,
  PortfolioReviewOptions,
  PortfolioReviewProjectMatrix,
  PortfolioReviewSession,
  PortfolioReviewSessionDraft,
  PortfolioReviewSnapshot,
  PortfolioReviewTrends,
} from "./types";
import "./portfolioReview.css";

type ReviewView =
  | "sessions"
  | "overview"
  | "snapshot"
  | "allocation"
  | "matrix"
  | "budget-resources"
  | "gate-fid"
  | "exceptions"
  | "conclusions"
  | "actions"
  | "history"
  | "trends";

const routeView: Record<string, ReviewView> = {
  "portfolio-review-sessions": "sessions",
  "portfolio-review-overview": "overview",
  "portfolio-review-snapshot": "snapshot",
  "portfolio-review-allocation": "allocation",
  "portfolio-review-project-matrix": "matrix",
  "portfolio-review-budget-resources": "budget-resources",
  "portfolio-review-gate-fid": "gate-fid",
  "portfolio-review-exceptions": "exceptions",
  "portfolio-review-conclusions": "conclusions",
  "portfolio-review-actions": "actions",
  "portfolio-review-history": "history",
  "portfolio-review-trends": "trends",
};

const reviewViews = (
  strategicNodeForView("portfolio-review-sessions", "user")?.trail.find(
    (item) => item.id === "periodic-portfolio-review"
  )?.children ?? []
)
  .map((item): [ReviewView, string] => [routeView[item.view], item.label])
  .filter(([view]) => Boolean(view));

const today = new Date().toISOString().slice(0, 10);

const emptyDraft: PortfolioReviewSessionDraft = {
  portfolio_id: 0,
  planning_cycle_id: null,
  allocation_plan_id: null,
  review_type: "SCHEDULED",
  review_date: today,
  planned_review_date: today,
  review_period_start: null,
  review_period_end: null,
  next_planned_review_date: null,
  title: "Periodic Portfolio Review",
  description: "",
  accountable_owner: "",
  chair: "",
  secretary: "",
};

const emptyActionDraft: PortfolioReviewActionDraft = {
  subject_type: "PORTFOLIO",
  subject_id: null,
  action_type: "HOLD_FOR_CAPACITY",
  rationale: "",
  priority: "MEDIUM",
  owner: "",
  due_date: null,
  requested_source_authority: null,
};

function actionAvailable(item: { allowed_actions?: string[] }, ...names: string[]) {
  const normalized = new Set(
    (item.allowed_actions ?? []).map((value) => value.toLowerCase().replace(/_/g, "-").replace(/^can-/, ""))
  );
  return names.some((name) => normalized.has(name.toLowerCase().replace(/_/g, "-").replace(/^can-/, "")));
}

function statusClass(value: string) {
  return `reviewStatus status-${value.toLowerCase().replace(/_/g, "-")}`;
}

function displayDate(value?: string | null) {
  if (!value) return "—";
  const parsed = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
}

function displayScalar(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length ? value.map(displayScalar).join(" · ") : "—";
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return entries.length
      ? entries.map(([key, item]) => `${key.replace(/_/g, " ")}: ${displayScalar(item)}`).join(" · ")
      : "—";
  }
  return String(value);
}

function shortHash(value?: string | null) {
  return value ? `${value.slice(0, 12)}${value.length > 12 ? "…" : ""}` : "—";
}

function amountByCurrency(value?: Record<string, string | number>) {
  const entries = Object.entries(value ?? {});
  if (!entries.length) return "—";
  return entries
    .map(
      ([currency, amount]) =>
        `${currency} ${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(Number(amount))}`
    )
    .join(" · ");
}

function openAction(action: PortfolioReviewAction) {
  return !["COMPLETED", "REJECTED", "CANCELLED"].includes(action.status);
}

export default function PortfolioReviewWorkspace({ initialView, token }: { initialView?: string; token: string }) {
  const [activeView, setActiveView] = useState<ReviewView>(routeView[initialView ?? ""] ?? "sessions");
  const [sessions, setSessions] = useState<PortfolioReviewSession[]>([]);
  const [selected, setSelected] = useState<PortfolioReviewSession | null>(null);
  const [options, setOptions] = useState<PortfolioReviewOptions | null>(null);
  const [actionQueue, setActionQueue] = useState<PortfolioReviewAction[]>([]);
  const [snapshotPreview, setSnapshotPreview] = useState<PortfolioReviewSnapshot | null>(null);
  const [allocation, setAllocation] = useState<PortfolioReviewAllocationContext | null>(null);
  const [matrix, setMatrix] = useState<PortfolioReviewProjectMatrix | null>(null);
  const [budgetResources, setBudgetResources] = useState<PortfolioReviewBudgetResources | null>(null);
  const [gateStatus, setGateStatus] = useState<PortfolioReviewGateStatus | null>(null);
  const [history, setHistory] = useState<PortfolioReviewHistoryEvent[]>([]);
  const [comparison, setComparison] = useState<PortfolioReviewComparison | null>(null);
  const [trends, setTrends] = useState<PortfolioReviewTrends | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [draft, setDraft] = useState<PortfolioReviewSessionDraft>(emptyDraft);
  const [actionDraft, setActionDraft] = useState<PortfolioReviewActionDraft>(emptyActionDraft);
  const [conclusionType, setConclusionType] = useState("PORTFOLIO_BALANCED");
  const [conclusionRationale, setConclusionRationale] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [portfolioFilter, setPortfolioFilter] = useState("");
  const [matrixFilters, setMatrixFilters] = useState<MatrixFilters>({
    bucket: "",
    gate_status: "",
    action_owner: "",
    rank_min: "",
    rank_max: "",
    project_type: "",
    fid_status: "",
    budget_status: "",
    resource_status: "",
    review_action: "",
    blocked: false,
    stale: false,
    unclassified: false,
  });
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [transitionReason, setTransitionReason] = useState("");
  const [replacementId, setReplacementId] = useState("");

  const loadSupportingViews = useCallback(
    async (session: PortfolioReviewSession, availableSessions: PortfolioReviewSession[]) => {
      const previous = availableSessions
        .filter(
          (item) =>
            item.id !== session.id &&
            item.status === "COMPLETED" &&
            item.portfolio_id === session.portfolio_id &&
            item.review_date <= session.review_date
        )
        .sort((first, second) => String(second.review_date).localeCompare(String(first.review_date)))[0];
      const results = await Promise.allSettled([
        portfolioReviewApi.allocation(token, session.id),
        portfolioReviewApi.projectMatrix(token, session.id, { page: 1, page_size: 100 }),
        portfolioReviewApi.budgetResources(token, session.id),
        portfolioReviewApi.gateStatus(token, session.id),
        portfolioReviewApi.history(token, session.id),
        portfolioReviewApi.trends(token, session.portfolio_id),
        previous && session.status === "COMPLETED"
          ? portfolioReviewApi.compare(token, session.id, previous.id)
          : Promise.resolve(null),
        portfolioReviewApi.listActions(token, session.id),
      ]);
      setAllocation(results[0].status === "fulfilled" ? results[0].value : null);
      setMatrix(results[1].status === "fulfilled" ? results[1].value : null);
      setBudgetResources(results[2].status === "fulfilled" ? results[2].value : null);
      setGateStatus(results[3].status === "fulfilled" ? results[3].value : null);
      setHistory(results[4].status === "fulfilled" ? results[4].value : []);
      setTrends(results[5].status === "fulfilled" ? results[5].value : null);
      setComparison(results[6].status === "fulfilled" ? results[6].value : null);
      if (results[7].status === "fulfilled") {
        const actions = results[7].value;
        setActionQueue(actions);
        if (session.status !== "COMPLETED") {
          setSelected((current) => (current?.id === session.id ? { ...current, actions } : current));
        }
      }
    },
    [token]
  );

  const openSession = useCallback(
    async (candidate: PortfolioReviewSession, availableSessions = sessions) => {
      setBusy(true);
      setMessage("");
      try {
        const current = await portfolioReviewApi.readSession(token, candidate.id);
        setSelected(current);
        setSnapshotPreview(null);
        await loadSupportingViews(current, availableSessions);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "The Portfolio Review Session could not be opened.");
      } finally {
        setBusy(false);
      }
    },
    [loadSupportingViews, sessions, token]
  );

  const load = useCallback(async () => {
    setBusy(true);
    setMessage("");
    try {
      const page = await portfolioReviewApi.listSessions(token, {
        portfolio_id: portfolioFilter,
        status: statusFilter,
        page: 1,
        page_size: 100,
      });
      setSessions(page.items);
      const retained = page.items.find((item) => item.id === selected?.id) ?? page.items[0] ?? null;
      if (retained) {
        const current = await portfolioReviewApi.readSession(token, retained.id);
        setSelected(current);
        await loadSupportingViews(current, page.items);
      } else {
        setSelected(null);
        setAllocation(null);
        setMatrix(null);
        setBudgetResources(null);
        setGateStatus(null);
        setHistory([]);
        setComparison(null);
        setTrends(null);
        setActionQueue([]);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Portfolio Review Sessions could not be loaded.");
    } finally {
      setBusy(false);
    }
  }, [loadSupportingViews, portfolioFilter, selected?.id, statusFilter, token]);

  useEffect(() => {
    // The server owns filtering, pagination and source aggregation.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    // Selection is retained inside load and must not restart the request after it resolves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, portfolioFilter, statusFilter]);

  useEffect(() => {
    let cancelled = false;
    void portfolioReviewApi
      .options(token, showCreate ? draft.portfolio_id || null : (selected?.portfolio_id ?? null))
      .then((value) => {
        if (cancelled) return;
        setOptions(value);
        setDraft((current) =>
          value.review_types.some((item) => item.code === current.review_type)
            ? current
            : { ...current, review_type: value.review_types[0]?.code ?? "" }
        );
        setConclusionType((current) =>
          value.conclusion_types.some((item) => item.code === current)
            ? current
            : (value.conclusion_types[0]?.code ?? "")
        );
        setActionDraft((current) =>
          value.action_types.some((item) => item.code === current.action_type)
            ? current
            : { ...current, action_type: value.action_types[0]?.code ?? "" }
        );
      })
      .catch(() => {
        if (!cancelled) setOptions(null);
      });
    return () => {
      cancelled = true;
    };
  }, [token, selected?.portfolio_id, draft.portfolio_id, showCreate]);

  useEffect(() => {
    // A canonical deep link reuses this outlet instance.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setActiveView(routeView[initialView ?? ""] ?? "sessions");
  }, [initialView]);

  async function createSession() {
    if (!draft.portfolio_id || !draft.review_date) {
      setMessage("Portfolio Workspace and review date are required.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const created = await portfolioReviewApi.createSession(token, {
        ...draft,
        portfolio_workspace_id: draft.portfolio_id,
      });
      const nextSessions = [created, ...sessions];
      setSessions(nextSessions);
      setSelected(created);
      setDraft(emptyDraft);
      setShowCreate(false);
      setActiveView("overview");
      await loadSupportingViews(created, nextSessions);
      setMessage(`${created.review_number} created as a governed DRAFT.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Portfolio Review Session creation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function applySession(next: PortfolioReviewSession, success: string) {
    const nextSessions = sessions.map((item) => (item.id === next.id ? next : item));
    setSessions(nextSessions);
    setSelected(next);
    await loadSupportingViews(next, nextSessions);
    setMessage(success);
  }

  async function saveAgenda(agenda: PortfolioReviewSession["agenda"]) {
    if (!selected) return;
    setBusy(true);
    try {
      const next = await portfolioReviewApi.updateSession(token, selected, {
        agenda: agenda.map((item) => ({
          code: item.code,
          title: item.label,
          status: item.status ?? "NOT_STARTED",
          notes: item.notes ?? "",
        })),
      });
      await applySession(next, "Review agenda preparation saved with version control.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Agenda preparation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function lifecycle(action: "prepare" | "freeze" | "start" | "complete") {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      let next = selected;
      if (action === "prepare") next = await portfolioReviewApi.prepare(token, selected);
      if (action === "freeze") next = await portfolioReviewApi.freezeSnapshot(token, selected);
      if (action === "start") next = await portfolioReviewApi.startReview(token, selected);
      if (action === "complete") next = await portfolioReviewApi.complete(token, selected, {});
      setSnapshotPreview(null);
      await applySession(next, `Portfolio Review lifecycle action ${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Portfolio Review lifecycle action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function previewSnapshot() {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      const preview = await portfolioReviewApi.snapshotPreview(token, selected);
      setSnapshotPreview(preview);
      setActiveView("snapshot");
      setMessage("Snapshot Preview refreshed with persisted=false; no historical evidence was changed.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Snapshot Preview could not be generated.");
    } finally {
      setBusy(false);
    }
  }

  async function transitionReview(transition: "return" | "cancel" | "supersede") {
    if (!selected || transitionReason.trim().length < 3) {
      setMessage("A lifecycle transition requires a reason of at least 3 characters.");
      return;
    }
    setBusy(true);
    try {
      const next = await portfolioReviewApi.transition(token, selected, transition, {
        reason: transitionReason.trim(),
        replacement_review_session_id: transition === "supersede" && replacementId ? Number(replacementId) : null,
      });
      setSnapshotPreview(null);
      await applySession(next, `Review ${transition} recorded with governed rationale.`);
      setTransitionReason("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Review transition failed.");
    } finally {
      setBusy(false);
    }
  }

  async function saveConclusion() {
    if (!selected || !conclusionRationale.trim()) {
      setMessage("A governed conclusion requires rationale.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      await portfolioReviewApi.createConclusion(token, selected, {
        conclusion_type: conclusionType,
        rationale: conclusionRationale.trim(),
        conditions: [],
      });
      const next = await portfolioReviewApi.readSession(token, selected.id);
      setConclusionRationale("");
      await applySession(next, "Portfolio-level conclusion recorded without issuing a Project Gate decision.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Conclusion could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function createAction() {
    if (!selected || !actionDraft.rationale.trim() || !actionDraft.owner_user_id) {
      setMessage("Action rationale and owner user ID are required.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const createdAction = await portfolioReviewApi.createAction(token, selected, actionDraft);
      const current = await portfolioReviewApi.readSession(token, selected.id);
      const actions = await portfolioReviewApi.listActions(token, selected.id);
      const next = { ...current, actions };
      setSelected(next);
      setActionQueue(actions);
      setSessions((items) => items.map((item) => (item.id === next.id ? next : item)));
      setActionDraft(emptyActionDraft);
      setMessage(
        `${createdAction.action_type} recorded as a governance instruction/request; no source-authority record was silently mutated.`
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Portfolio Review Action could not be created.");
    } finally {
      setBusy(false);
    }
  }

  async function mutateAction(
    action: PortfolioReviewAction,
    operation: "approve" | "dispatch" | "status",
    status?: string
  ) {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      let updated = action;
      if (operation === "approve") updated = await portfolioReviewApi.approveAction(token, action);
      if (operation === "dispatch") updated = await portfolioReviewApi.dispatchAction(token, action);
      if (operation === "status") updated = await portfolioReviewApi.updateAction(token, action, { status });
      setActionQueue((items) => items.map((item) => (item.id === updated.id ? updated : item)));
      if (selected.status !== "COMPLETED") {
        setSelected({
          ...selected,
          actions: selected.actions.map((item) => (item.id === updated.id ? updated : item)),
        });
      }
      setMessage(
        operation === "dispatch"
          ? "Governed dispatch requested through the source-authority boundary. No direct cross-domain write was made."
          : `Action ${operation} completed.`
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Portfolio Review Action update failed.");
    } finally {
      setBusy(false);
    }
  }

  async function applyMatrixFilters(page = 1) {
    if (!selected) return;
    setBusy(true);
    try {
      setMatrix(
        await portfolioReviewApi.projectMatrix(token, selected.id, {
          bucket: matrixFilters.bucket,
          gate_status: matrixFilters.gate_status,
          action_owner_user_id: matrixFilters.action_owner ? Number(matrixFilters.action_owner) : undefined,
          rank_min: matrixFilters.rank_min ? Number(matrixFilters.rank_min) : undefined,
          rank_max: matrixFilters.rank_max ? Number(matrixFilters.rank_max) : undefined,
          project_type: matrixFilters.project_type,
          fid_status: matrixFilters.fid_status,
          budget_status: matrixFilters.budget_status,
          resource_status: matrixFilters.resource_status,
          review_action: matrixFilters.review_action,
          blocked: matrixFilters.blocked || undefined,
          stale: matrixFilters.stale || undefined,
          unclassified: matrixFilters.unclassified || undefined,
          page,
          page_size: 100,
        })
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Project Matrix filter failed.");
    } finally {
      setBusy(false);
    }
  }

  const overdueActions = useMemo(
    () =>
      selected?.status === "COMPLETED"
        ? Number(selected.summary.overdue_action_count ?? 0)
        : (selected?.actions ?? []).filter((action) => action.due_date && action.due_date < today && openAction(action))
            .length,
    [selected]
  );

  return (
    <section aria-label="Periodic Portfolio Review workspace" className="portfolioReview">
      <CompactModuleHeader
        eyebrow="USER MODE / Enterprise Strategy Manager / Portfolio Planning & Review"
        title="Periodic Portfolio Review"
        description="Govern the Portfolio collectively through recurring, auditable Sessions. Frozen evidence is consumed read-only; Project rank, Budget, Resource scenarios, Gate decisions and FID remain with their source authorities."
        metrics={[
          { label: "Review Sessions", value: sessions.length },
          { label: "Selected status", value: selected?.status ?? "—" },
          { label: "Open actions", value: selected?.actions.filter(openAction).length ?? 0 },
          { label: "Overdue", value: overdueActions },
        ]}
      />

      <div className="reviewBoundary" role="note">
        <ShieldCheck aria-hidden="true" size={18} />
        <span>
          Portfolio Review ≠ Project Gate. Gate07K HOLD ≠ HOLD_FOR_CAPACITY. This review does not rank Projects or
          approve Budget; REQUEST_REASSESSMENT never recalculates rank.
        </span>
      </div>

      {message ? (
        <div className="reviewMessage" role="status">
          {message}
        </div>
      ) : null}

      <section aria-label="Portfolio Review Session selector" className="reviewSelector">
        <label>
          Portfolio ID
          <input
            min="1"
            onChange={(event) => setPortfolioFilter(event.target.value)}
            placeholder="All authorized"
            type="number"
            value={portfolioFilter}
          />
        </label>
        <label>
          Status
          <select onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}>
            <option value="">All statuses</option>
            {[
              "DRAFT",
              "PREPARING",
              "READY_FOR_REVIEW",
              "IN_REVIEW",
              "STALE",
              "COMPLETED",
              "RETURNED",
              "CANCELLED",
              "SUPERSEDED",
            ].map((status) => (
              <option key={status}>{status}</option>
            ))}
          </select>
        </label>
        <label className="reviewSessionSelect">
          Review Session
          <select
            aria-label="Review Session"
            onChange={(event) => {
              const session = sessions.find((item) => item.id === Number(event.target.value));
              if (session) void openSession(session);
            }}
            value={selected?.id ?? ""}
          >
            {!sessions.length ? <option value="">No Sessions</option> : null}
            {sessions.map((session) => (
              <option key={session.id} value={session.id}>
                {session.review_number} · {session.review_type} · {session.status}
              </option>
            ))}
          </select>
        </label>
        <button className="reviewSecondary" disabled={busy} onClick={() => void load()} type="button">
          <RefreshCcw aria-hidden="true" size={14} /> Refresh
        </button>
        <button className="reviewPrimary" disabled={busy} onClick={() => setShowCreate(true)} type="button">
          <FilePlus2 aria-hidden="true" size={14} /> New Review Session
        </button>
      </section>

      <nav aria-label="Periodic Portfolio Review views" className="reviewTabs">
        {reviewViews.map(([key, label]) => (
          <button
            aria-current={activeView === key ? "page" : undefined}
            className={activeView === key ? "active" : ""}
            key={key}
            onClick={() => setActiveView(key)}
            type="button"
          >
            {label}
          </button>
        ))}
      </nav>

      {!selected ? (
        <section className="reviewEmpty">
          <Layers3 aria-hidden="true" size={24} />
          <h3>No Portfolio Review Session selected</h3>
          <p>Create a governed DRAFT for one Portfolio. This does not create a Project Gate or scenario.</p>
        </section>
      ) : (
        <>
          <SessionHeader session={selected} />
          <section aria-label="Portfolio Review lifecycle actions" className="reviewLifecycle">
            {actionAvailable(selected, "prepare") ? (
              <button disabled={busy} onClick={() => void lifecycle("prepare")} type="button">
                <Save aria-hidden="true" size={14} /> Prepare package
              </button>
            ) : null}
            {actionAvailable(selected, "snapshot-preview", "refresh-snapshot-preview", "preview") ? (
              <button disabled={busy} onClick={() => void previewSnapshot()} type="button">
                <RefreshCcw aria-hidden="true" size={14} /> Refresh Snapshot Preview
              </button>
            ) : null}
            {actionAvailable(selected, "freeze-snapshot", "freeze") ? (
              <button disabled={busy} onClick={() => void lifecycle("freeze")} type="button">
                <Layers3 aria-hidden="true" size={14} /> Freeze Snapshot
              </button>
            ) : null}
            {actionAvailable(selected, "start-review", "conduct") ? (
              <button disabled={busy} onClick={() => void lifecycle("start")} type="button">
                <Clock3 aria-hidden="true" size={14} /> Start Review
              </button>
            ) : null}
            {actionAvailable(selected, "complete") ? (
              <button className="complete" disabled={busy} onClick={() => void lifecycle("complete")} type="button">
                <CheckCircle2 aria-hidden="true" size={14} /> Complete Review
              </button>
            ) : null}
          </section>
          {["return", "cancel", "supersede"].some((action) => actionAvailable(selected, action)) ? (
            <section className="reviewMatrixFilters" aria-label="Controlled Review transitions">
              <label>
                Lifecycle reason
                <input
                  value={transitionReason}
                  onChange={(event) => setTransitionReason(event.target.value)}
                  minLength={3}
                />
              </label>
              {actionAvailable(selected, "supersede") ? (
                <label>
                  Replacement Review Session ID
                  <input
                    type="number"
                    min="1"
                    value={replacementId}
                    onChange={(event) => setReplacementId(event.target.value)}
                  />
                </label>
              ) : null}
              {(["return", "cancel", "supersede"] as const)
                .filter((action) => actionAvailable(selected, action))
                .map((action) => (
                  <button
                    key={action}
                    type="button"
                    disabled={busy || transitionReason.trim().length < 3}
                    onClick={() => void transitionReview(action)}
                  >
                    {action === "return"
                      ? "Return for preparation"
                      : action === "cancel"
                        ? "Cancel Review"
                        : "Supersede Review"}
                  </button>
                ))}
            </section>
          ) : null}

          {activeView === "sessions" ? (
            <Sessions sessions={sessions} selectedId={selected.id} onOpen={openSession} />
          ) : null}
          {activeView === "overview" ? <Overview session={selected} /> : null}
          {activeView === "overview" && actionAvailable(selected, "edit") ? (
            <AgendaEditor
              key={`${selected.id}-${selected.revision_version}`}
              session={selected}
              disabled={busy}
              onSave={(agenda) => void saveAgenda(agenda)}
            />
          ) : null}
          {activeView === "snapshot" ? <Snapshot session={selected} preview={snapshotPreview} /> : null}
          {activeView === "allocation" ? <Allocation context={allocation} /> : null}
          {activeView === "matrix" ? (
            <ProjectMatrix
              filters={matrixFilters}
              matrix={matrix}
              onApply={() => void applyMatrixFilters()}
              onFilters={setMatrixFilters}
              onPage={(page) => void applyMatrixFilters(page)}
              busy={busy}
            />
          ) : null}
          {activeView === "budget-resources" ? <BudgetResources context={budgetResources} /> : null}
          {activeView === "gate-fid" ? <GateFid context={gateStatus} /> : null}
          {activeView === "exceptions" ? (
            <Exceptions
              budgetResources={budgetResources}
              gateStatus={gateStatus}
              preview={snapshotPreview}
              session={selected}
            />
          ) : null}
          {activeView === "conclusions" ? (
            <Conclusions
              conclusionRationale={conclusionRationale}
              conclusionType={conclusionType}
              disabled={busy || !actionAvailable(selected, "record-conclusion")}
              types={options?.conclusion_types ?? []}
              onRationale={setConclusionRationale}
              onSave={() => void saveConclusion()}
              onType={setConclusionType}
              session={selected}
            />
          ) : null}
          {activeView === "actions" ? (
            <Actions
              draft={actionDraft}
              disabled={busy || !actionAvailable(selected, "create-action")}
              busy={busy}
              actions={actionQueue}
              types={options?.action_types ?? []}
              onCreate={() => void createAction()}
              onDraft={setActionDraft}
              onMutate={(action, operation, status) => void mutateAction(action, operation, status)}
              session={selected}
            />
          ) : null}
          {activeView === "history" ? <History comparison={comparison} events={history} session={selected} /> : null}
          {activeView === "trends" ? <Trends trends={trends} /> : null}
        </>
      )}

      {showCreate ? (
        <div className="reviewDrawerBackdrop" role="presentation">
          <form
            aria-label="New Portfolio Review Session form"
            className="reviewDrawer"
            onSubmit={(event) => {
              event.preventDefault();
              void createSession();
            }}
          >
            <header>
              <div>
                <span>Governed Portfolio Review</span>
                <h3>New Review Session</h3>
              </div>
              <button onClick={() => setShowCreate(false)} type="button">
                Close
              </button>
            </header>
            <div className="reviewFormGrid">
              <label>
                Portfolio Workspace ID
                <input
                  min="1"
                  onChange={(event) => setDraft((item) => ({ ...item, portfolio_id: Number(event.target.value) }))}
                  required
                  type="number"
                  value={draft.portfolio_id || ""}
                />
              </label>
              <label>
                Review type
                <select
                  onChange={(event) => setDraft((item) => ({ ...item, review_type: event.target.value }))}
                  value={draft.review_type}
                >
                  {(options?.review_types ?? []).map(({ code, label }) => (
                    <option key={code} value={code}>
                      {label ?? code}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Planned review date
                <input
                  onChange={(event) =>
                    setDraft((item) => ({
                      ...item,
                      review_date: event.target.value,
                      planned_review_date: event.target.value,
                    }))
                  }
                  required
                  type="date"
                  value={draft.review_date}
                />
              </label>
              <label>
                Next planned review
                <input
                  onChange={(event) =>
                    setDraft((item) => ({ ...item, next_planned_review_date: event.target.value || null }))
                  }
                  type="date"
                  value={draft.next_planned_review_date ?? ""}
                />
              </label>
              <label>
                Review period start
                <input
                  onChange={(event) =>
                    setDraft((item) => ({ ...item, review_period_start: event.target.value || null }))
                  }
                  type="date"
                  value={draft.review_period_start ?? ""}
                />
              </label>
              <label>
                Review period end
                <input
                  onChange={(event) => setDraft((item) => ({ ...item, review_period_end: event.target.value || null }))}
                  type="date"
                  value={draft.review_period_end ?? ""}
                />
              </label>
              <label>
                Planning Cycle ID
                <input
                  min="1"
                  onChange={(event) =>
                    setDraft((item) => ({
                      ...item,
                      planning_cycle_id: event.target.value ? Number(event.target.value) : null,
                    }))
                  }
                  type="number"
                  value={draft.planning_cycle_id ?? ""}
                />
              </label>
              <label>
                Allocation Plan ID
                <input
                  min="1"
                  onChange={(event) =>
                    setDraft((item) => ({
                      ...item,
                      allocation_plan_id: event.target.value ? Number(event.target.value) : null,
                    }))
                  }
                  type="number"
                  value={draft.allocation_plan_id ?? ""}
                />
              </label>
              <label>
                Review title
                <input
                  onChange={(event) => setDraft((item) => ({ ...item, title: event.target.value }))}
                  value={draft.title ?? ""}
                />
              </label>
              <label>
                Chair user ID
                <input
                  min="1"
                  onChange={(event) =>
                    setDraft((item) => ({
                      ...item,
                      chair_user_id: event.target.value ? Number(event.target.value) : null,
                    }))
                  }
                  placeholder="Current user by default"
                  type="number"
                  value={draft.chair_user_id ?? ""}
                />
              </label>
            </div>
            <div className="reviewAuthorityNote">
              <ShieldCheck aria-hidden="true" size={18} />
              This creates only a Review Session. It does not create a Budget/Resource scenario, change rank, or issue a
              Gate/FID decision.
            </div>
            <footer>
              <button onClick={() => setShowCreate(false)} type="button">
                Cancel
              </button>
              <button className="reviewPrimary" disabled={busy} type="submit">
                Create governed DRAFT
              </button>
            </footer>
          </form>
        </div>
      ) : null}
    </section>
  );
}

function SessionHeader({ session }: { session: PortfolioReviewSession }) {
  return (
    <section aria-label="Selected Portfolio Review Session" className="reviewSessionHeader">
      <div>
        <span>{session.review_type}</span>
        <h2>{session.review_number}</h2>
        <p>
          {session.portfolio_name ?? `Portfolio ${session.portfolio_id}`} · review {displayDate(session.review_date)}
        </p>
      </div>
      <div className="reviewSessionMeta">
        <b className={statusClass(session.status)}>{session.status}</b>
        <span>Revision {session.revision_version}</span>
        <span>Snapshot {shortHash(session.snapshot_hash)}</span>
        <span className={session.source_current ? "sourceCurrent" : "sourceStale"}>
          {session.source_current ? "SOURCE CURRENT" : "SOURCE STALE"}
        </span>
      </div>
    </section>
  );
}

function Sessions({
  onOpen,
  selectedId,
  sessions,
}: {
  onOpen: (session: PortfolioReviewSession) => Promise<void>;
  selectedId: number;
  sessions: PortfolioReviewSession[];
}) {
  return (
    <section aria-label="Review Calendar and Sessions" className="reviewSurface">
      <header className="reviewSurfaceHeader">
        <div>
          <span>Governance cadence</span>
          <h3>Review Calendar / Sessions</h3>
        </div>
        <Clock3 aria-hidden="true" size={20} />
      </header>
      <div className="reviewTableWrap">
        <table aria-label="Portfolio Review Sessions">
          <thead>
            <tr>
              <th>Review</th>
              <th>Portfolio</th>
              <th>Type</th>
              <th>Planned</th>
              <th>Completed</th>
              <th>Next review</th>
              <th>Status</th>
              <th>Open actions</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {sessions.map((session) => (
              <tr className={session.id === selectedId ? "selected" : ""} key={session.id}>
                <td>{session.review_number}</td>
                <td>{session.portfolio_name ?? session.portfolio_id}</td>
                <td>{session.review_type}</td>
                <td>{displayDate(session.planned_review_date ?? session.review_date)}</td>
                <td>{displayDate(session.completed_at ?? session.actual_review_date)}</td>
                <td>{displayDate(session.next_planned_review_date)}</td>
                <td>
                  <span className={statusClass(session.status)}>{session.status}</span>
                </td>
                <td>{session.actions.filter((item) => item.status !== "COMPLETED").length}</td>
                <td>
                  <button onClick={() => void onOpen(session)} type="button">
                    Open
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Overview({ session }: { session: PortfolioReviewSession }) {
  const summary = session.summary;
  return (
    <section aria-label="Portfolio Review overview" className="reviewSurface">
      <header className="reviewSurfaceHeader">
        <div>
          <span>Portfolio-level governance</span>
          <h3>Overview</h3>
        </div>
        <ShieldCheck aria-hidden="true" size={20} />
      </header>
      <div className="reviewMetricGrid">
        {[
          ["Portfolio size", summary.portfolio_size ?? summary.project_count],
          ["Blocked Projects", summary.blocked_project_count ?? summary.projects_with_blockers],
          [
            "Open actions",
            summary.open_action_count ?? session.actions.filter((item) => item.status !== "COMPLETED").length,
          ],
          ["Overdue actions", summary.overdue_action_count],
          [
            "Gate ready",
            summary.gate_ready_count ??
              (summary.gate_status_distribution as Record<string, unknown> | undefined)?.READY,
          ],
          [
            "FID",
            summary.fid_count ?? (summary.fid_status_distribution as Record<string, unknown> | undefined)?.FID_GRANTED,
          ],
        ].map(([label, value]) => (
          <article key={String(label)}>
            <span>{String(label)}</span>
            <strong>{displayScalar(value)}</strong>
          </article>
        ))}
      </div>
      <div className="reviewSplit">
        <article>
          <h4>Review readiness</h4>
          <strong className={statusClass(session.readiness.overall)}>{session.readiness.overall}</strong>
          <RecordGrid value={session.readiness.dimensions} />
        </article>
        <article>
          <h4>Agenda readiness</h4>
          <div className="reviewAgenda">
            {session.agenda.length ? (
              session.agenda.map((item) => (
                <div key={item.code}>
                  <span>{item.label}</span>
                  <b className={statusClass(item.status ?? (item.required ? "REQUIRED" : "OPTIONAL"))}>
                    {item.status ?? (item.required ? "REQUIRED" : "OPTIONAL")}
                  </b>
                </div>
              ))
            ) : (
              <p>No agenda items were returned by the effective policy.</p>
            )}
          </div>
        </article>
      </div>
      <AlertLists blockers={session.readiness.blockers} warnings={session.readiness.warnings} />
      <h4>Frozen Portfolio summary</h4>
      <RecordGrid value={summary} />
    </section>
  );
}

function AgendaEditor({
  session,
  disabled,
  onSave,
}: {
  session: PortfolioReviewSession;
  disabled: boolean;
  onSave: (agenda: PortfolioReviewSession["agenda"]) => void;
}) {
  const [agenda, setAgenda] = useState(session.agenda);
  return (
    <form
      aria-label="Prepare Portfolio Review agenda"
      className="reviewSurface"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(agenda);
      }}
    >
      <h3>Prepare agenda</h3>
      {agenda.map((item, index) => (
        <div className="reviewMatrixFilters" key={item.code}>
          <label>
            {item.label} status
            <select
              disabled={disabled}
              value={item.status ?? "NOT_STARTED"}
              onChange={(event) =>
                setAgenda((items) =>
                  items.map((entry, position) =>
                    position === index ? { ...entry, status: event.target.value } : entry
                  )
                )
              }
            >
              <option>NOT_STARTED</option>
              <option>IN_PROGRESS</option>
              <option>READY</option>
              <option>REVIEWED</option>
              <option>NOT_APPLICABLE</option>
            </select>
          </label>
          <label>
            {item.label} notes
            <input
              disabled={disabled}
              value={item.notes ?? ""}
              onChange={(event) =>
                setAgenda((items) =>
                  items.map((entry, position) => (position === index ? { ...entry, notes: event.target.value } : entry))
                )
              }
            />
          </label>
        </div>
      ))}
      <button disabled={disabled || !agenda.length} type="submit">
        Save agenda preparation
      </button>
    </form>
  );
}

function Snapshot({ session, preview }: { session: PortfolioReviewSession; preview: PortfolioReviewSnapshot | null }) {
  const snapshot = preview ?? session.snapshot;
  return (
    <section aria-label="Portfolio Review Snapshot" className="reviewSurface">
      <header className="reviewSurfaceHeader">
        <div>
          <span>Immutable evidence contract</span>
          <h3>Portfolio Snapshot</h3>
        </div>
        <Layers3 aria-hidden="true" size={20} />
      </header>
      {preview ? (
        <div className="reviewPreviewFlag">Snapshot Preview · persisted={String(preview.persisted ?? false)}</div>
      ) : null}
      {!snapshot ? (
        <EmptyData text="No frozen snapshot or preview is available." />
      ) : (
        <>
          <div className="reviewSnapshotFacts">
            <article>
              <span>Snapshot hash</span>
              <strong title={snapshot.snapshot_hash ?? ""}>{shortHash(snapshot.snapshot_hash)}</strong>
            </article>
            <article>
              <span>As of</span>
              <strong>{displayDate(snapshot.source_as_of ?? snapshot.generated_at ?? snapshot.frozen_at)}</strong>
            </article>
            <article>
              <span>Source status</span>
              <strong className={snapshot.source_current ? "sourceCurrent" : "sourceStale"}>
                {snapshot.source_current ? "CURRENT" : "STALE"}
              </strong>
            </article>
            <article>
              <span>Persistence</span>
              <strong>{snapshot.persisted === false ? "PREVIEW ONLY" : "FROZEN"}</strong>
            </article>
          </div>
          <div className="reviewTableWrap">
            <table aria-label="Snapshot source lineage">
              <thead>
                <tr>
                  <th>Source authority</th>
                  <th>Identity</th>
                  <th>Version</th>
                  <th>Hash</th>
                  <th>As of</th>
                  <th>Current</th>
                </tr>
              </thead>
              <tbody>
                {snapshot.sources.map((source, index) => (
                  <tr key={`${source.source_type}-${index}`}>
                    <td>{source.source_type}</td>
                    <td>{displayScalar(source.source_id)}</td>
                    <td>{displayScalar(source.source_version)}</td>
                    <td title={source.source_hash ?? ""}>{shortHash(source.source_hash)}</td>
                    <td>{displayDate(source.as_of)}</td>
                    <td>
                      <span className={source.source_current === false ? "sourceStale" : "sourceCurrent"}>
                        {source.source_current === false ? "STALE" : "CURRENT"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {snapshot.changes?.length ? (
            <section aria-label="Snapshot Preview changes" className="reviewChangeList">
              <h4>Changes since the current frozen evidence</h4>
              {snapshot.changes.map((change, index) => (
                <article key={`${change.source_type ?? change.category}-${index}`}>
                  <b>{change.label ?? change.category ?? change.source_type ?? "Source change"}</b>
                  <span>
                    {change.change_type ?? "CHANGED"}
                    {change.material ? " · MATERIAL" : ""}
                  </span>
                  <small>
                    {displayScalar(change.before)} → {displayScalar(change.after)}
                  </small>
                </article>
              ))}
            </section>
          ) : null}
          <AlertLists blockers={snapshot.blockers} warnings={snapshot.warnings} />
        </>
      )}
      <p className="reviewGuardrail">
        Completed snapshots are displayed from their immutable historical payload; live sources are never used to
        reinterpret them.
      </p>
    </section>
  );
}

function Allocation({ context }: { context: PortfolioReviewAllocationContext | null }) {
  return (
    <section aria-label="Portfolio Review Strategic Allocation" className="reviewSurface">
      <header className="reviewSurfaceHeader">
        <div>
          <span>Wave 2A read model</span>
          <h3>Strategic Allocation</h3>
        </div>
        <BarChart3 aria-hidden="true" size={20} />
      </header>
      {!context ? (
        <EmptyData text="No allocation context is available for this Review snapshot." />
      ) : (
        <>
          <div className="reviewReadOnlyBanner">
            Read-only Wave 2A positions · Plan {context.allocation_plan_number ?? context.allocation_plan_id ?? "—"} ·{" "}
            {context.source_current ? "SOURCE CURRENT" : "SOURCE STALE"}
          </div>
          {context.normalization_warning ? <div className="reviewWarning">{context.normalization_warning}</div> : null}
          <div className="reviewTableWrap">
            <table aria-label="Strategic Allocation positions">
              <thead>
                <tr>
                  <th>Bucket</th>
                  <th>Target</th>
                  <th>Current Demand</th>
                  <th>Current Portfolio</th>
                  <th>Recommended</th>
                  <th>Approved</th>
                  <th>Variance</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {context.buckets.map((bucket) => (
                  <tr key={bucket.bucket_code}>
                    <td>
                      <strong>{bucket.bucket_name}</strong>
                      <small>{bucket.bucket_code}</small>
                    </td>
                    <td>
                      {displayScalar(bucket.target.percentage)}%
                      <small>{amountByCurrency(bucket.target.amounts_by_currency)}</small>
                    </td>
                    <td>
                      {displayScalar(bucket.current_demand.percentage)}%
                      <small>{amountByCurrency(bucket.current_demand.amounts_by_currency)}</small>
                    </td>
                    <td>
                      {displayScalar(bucket.current_portfolio.percentage)}%
                      <small>{amountByCurrency(bucket.current_portfolio.amounts_by_currency)}</small>
                    </td>
                    <td>
                      {displayScalar(bucket.recommended.percentage)}%
                      <small>{amountByCurrency(bucket.recommended.amounts_by_currency)}</small>
                    </td>
                    <td>
                      {displayScalar(bucket.approved.percentage)}%
                      <small>{amountByCurrency(bucket.approved.amounts_by_currency)}</small>
                    </td>
                    <td>{displayScalar(bucket.variance_percentage)}%</td>
                    <td>
                      <span className={statusClass(bucket.status)}>{bucket.status}</span>
                    </td>
                  </tr>
                ))}
                {(Object.keys(context.unclassified_by_position ?? {}).length
                  ? Object.entries(context.unclassified_by_position ?? {})
                  : [["Current Portfolio", context.unclassified] as const]
                ).map(([name, position]) => (
                  <tr className="unclassified" key={name}>
                    <td>
                      <strong>UNCLASSIFIED</strong>
                      <small>{name}</small>
                    </td>
                    <td colSpan={4}>{amountByCurrency(position.amounts_by_currency)}</td>
                    <td>{position.count ?? 0} items</td>
                    <td colSpan={2}>
                      {position.evaluable === false ? "NOT_EVALUABLE · " : ""}Preserved · no silent exclusion
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="reviewGuardrail">
            This view consumes Target, Current Demand, Current Portfolio, Recommended, Approved and Variance. It cannot
            edit an Allocation Plan or move a Project between Buckets.
          </p>
        </>
      )}
    </section>
  );
}

type MatrixFilters = {
  bucket: string;
  gate_status: string;
  action_owner: string;
  unclassified: boolean;
  blocked: boolean;
  stale: boolean;
  rank_min: string;
  rank_max: string;
  project_type: string;
  fid_status: string;
  budget_status: string;
  resource_status: string;
  review_action: string;
};

function ProjectMatrix({
  filters,
  matrix,
  onApply,
  onFilters,
  onPage,
  busy,
}: {
  filters: MatrixFilters;
  matrix: PortfolioReviewProjectMatrix | null;
  onApply: () => void;
  onFilters: (value: MatrixFilters) => void;
  onPage: (page: number) => void;
  busy: boolean;
}) {
  return (
    <section aria-label="Portfolio Review Project Matrix" className="reviewSurface">
      <header className="reviewSurfaceHeader">
        <div>
          <span>Backend-owned paged read model</span>
          <h3>Project Matrix</h3>
        </div>
        <Layers3 aria-hidden="true" size={20} />
      </header>
      <div className="reviewMatrixFilters">
        <label>
          Bucket
          <input onChange={(event) => onFilters({ ...filters, bucket: event.target.value })} value={filters.bucket} />
        </label>
        <label>
          Gate status
          <input
            onChange={(event) => onFilters({ ...filters, gate_status: event.target.value })}
            value={filters.gate_status}
          />
        </label>
        <label>
          Action owner
          <input
            onChange={(event) => onFilters({ ...filters, action_owner: event.target.value })}
            value={filters.action_owner}
          />
        </label>
        <label className="checkbox">
          <input
            checked={filters.unclassified}
            onChange={(event) => onFilters({ ...filters, unclassified: event.target.checked })}
            type="checkbox"
          />{" "}
          UNCLASSIFIED only
        </label>
        {(
          [
            ["rank_min", "Minimum rank"],
            ["rank_max", "Maximum rank"],
            ["project_type", "Project type"],
            ["fid_status", "FID status"],
            ["budget_status", "Budget status"],
            ["resource_status", "Resource status"],
            ["review_action", "Review action"],
          ] as const
        ).map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              type={key.startsWith("rank") ? "number" : "text"}
              min={key.startsWith("rank") ? 1 : undefined}
              value={filters[key]}
              onChange={(event) => onFilters({ ...filters, [key]: event.target.value })}
            />
          </label>
        ))}
        <label className="checkbox">
          <input
            type="checkbox"
            checked={filters.blocked}
            onChange={(event) => onFilters({ ...filters, blocked: event.target.checked })}
          />{" "}
          Blocked only
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={filters.stale}
            onChange={(event) => onFilters({ ...filters, stale: event.target.checked })}
          />{" "}
          Stale only
        </label>
        <button onClick={onApply} type="button">
          Apply server filters
        </button>
      </div>
      {!matrix ? (
        <EmptyData text="No Project Matrix is available for this snapshot." />
      ) : (
        <>
          <p>{matrix.total} active Portfolio Projects · one backend request · stable pagination</p>
          <div className="reviewTableWrap wideTable">
            <table aria-label="Portfolio Review Project Matrix rows">
              <thead>
                <tr>
                  <th>Project</th>
                  <th>Rank</th>
                  <th>Bucket</th>
                  <th>Allocation variance</th>
                  <th>Budget</th>
                  <th>Resources</th>
                  <th>Gate / readiness</th>
                  <th>Investment Decision</th>
                  <th>FID</th>
                  <th>Risk / readiness</th>
                  <th>Recommendation</th>
                  <th>Approved context</th>
                  <th>Portfolio action</th>
                  <th>Owner / due</th>
                </tr>
              </thead>
              <tbody>
                {matrix.items.map((row) => (
                  <tr key={String(row.project_id)}>
                    <td>
                      <strong>{row.project_name}</strong>
                      <small>{row.project_number ?? row.project_id}</small>
                    </td>
                    <td>{displayScalar(row.portfolio_rank)}</td>
                    <td>{row.strategic_bucket ?? "UNCLASSIFIED"}</td>
                    <td>{displayScalar(row.allocation_variance_contribution)}</td>
                    <td>{displayScalar(row.budget_status)}</td>
                    <td>{displayScalar(row.resource_status)}</td>
                    <td>
                      {displayScalar(row.gate_stage)}
                      <small>{displayScalar(row.gate_readiness)}</small>
                    </td>
                    <td>{displayScalar(row.investment_decision)}</td>
                    <td>{displayScalar(row.fid_status)}</td>
                    <td>{displayScalar(row.risk_readiness)}</td>
                    <td>{displayScalar(row.recommended_status)}</td>
                    <td>{amountByCurrency(row.approved_amounts_by_currency)}</td>
                    <td>
                      {row.review_actions?.length
                        ? row.review_actions.map((action) => (
                            <div key={action.id}>
                              {action.action_type} · {action.status}
                            </div>
                          ))
                        : displayScalar(row.review_action)}
                    </td>
                    <td>
                      {row.review_actions?.length ? (
                        row.review_actions.map((action) => (
                          <div key={action.id}>
                            {action.owner ?? action.owner_user_id ?? "—"}
                            <small>{displayDate(action.due_date)}</small>
                          </div>
                        ))
                      ) : (
                        <>
                          {displayScalar(row.action_owner)}
                          <small>{displayDate(row.action_due_date)}</small>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="reviewMatrixFilters" aria-label="Project Matrix pagination">
            <button disabled={busy || matrix.page <= 1} type="button" onClick={() => onPage(matrix.page - 1)}>
              Previous page
            </button>
            <span>
              Page {matrix.page} of {Math.max(1, Math.ceil(matrix.total / Math.max(1, matrix.pageSize)))}
            </span>
            <button
              disabled={busy || matrix.page * matrix.pageSize >= matrix.total}
              type="button"
              onClick={() => onPage(matrix.page + 1)}
            >
              Next page
            </button>
          </div>
        </>
      )}
      <p className="reviewGuardrail">
        Portfolio Rank is displayed read-only. This matrix never creates a review rank, adjusted rank, Budget scenario
        or Resource scenario.
      </p>
    </section>
  );
}

function BudgetResources({ context }: { context: PortfolioReviewBudgetResources | null }) {
  return (
    <section aria-label="Portfolio Review Budget and Resources" className="reviewSurface">
      <header className="reviewSurfaceHeader">
        <div>
          <span>Source-authority evidence</span>
          <h3>Budget & Resources</h3>
        </div>
        <BarChart3 aria-hidden="true" size={20} />
      </header>
      {!context ? (
        <EmptyData text="No Budget/Resource context is available for this snapshot." />
      ) : (
        <>
          <div className="reviewSplit">
            <article>
              <h4>Budget scenario · read only</h4>
              <RecordGrid value={context.budget} />
            </article>
            <article>
              <h4>Resource scenario · read only</h4>
              <RecordGrid value={context.resources} />
            </article>
          </div>
          <article className="reviewCompatibility">
            <h4>Compatibility</h4>
            <RecordGrid value={context.compatibility} />
          </article>
          <AlertLists blockers={context.blockers} warnings={context.warnings} />
        </>
      )}
      <p className="reviewGuardrail">
        REBALANCE_CAPITAL and REBALANCE_RESOURCES are governance requests. They do not edit Budget or Resource Scenario
        records here.
      </p>
    </section>
  );
}

function GateFid({ context }: { context: PortfolioReviewGateStatus | null }) {
  return (
    <section aria-label="Portfolio Review Gate and FID Status" className="reviewSurface">
      <header className="reviewSurfaceHeader">
        <div>
          <span>Gate07J / Gate07K read-only evidence</span>
          <h3>Gate / FID Status</h3>
        </div>
        <ShieldCheck aria-hidden="true" size={20} />
      </header>
      <div className="reviewGateBoundary">
        <strong>Investment Decision Status</strong>
        <span>is separate from</span>
        <strong>Portfolio Governance Action</strong>
        <b>Gate07K HOLD ≠ HOLD_FOR_CAPACITY</b>
      </div>
      {!context ? (
        <EmptyData text="No Gate/FID context is available for this snapshot." />
      ) : (
        <>
          <RecordGrid value={context.summary} />
          <h4>Gate preparation · read only</h4>
          <RecordGrid value={context.preparation ?? {}} />
          {context.projects.length ? (
            <div className="reviewTableWrap">
              <table aria-label="Gate and FID project status">
                <thead>
                  <tr>
                    <th>Project</th>
                    <th>Gate preparation</th>
                    <th>Investment decision</th>
                    <th>FID</th>
                    <th>Conditions</th>
                  </tr>
                </thead>
                <tbody>
                  {context.projects.map((raw, index) => {
                    const row = raw as Record<string, unknown>;
                    return (
                      <tr key={String(row.project_id ?? index)}>
                        <td>
                          {displayScalar(
                            row.project_name ?? row.project_number ?? row.project_id ?? row.decision_number
                          )}
                          <small>
                            {row.project_workspace_ids ? `Projects: ${displayScalar(row.project_workspace_ids)}` : ""}
                          </small>
                        </td>
                        <td>
                          {displayScalar(
                            row.gate_readiness ?? row.gate07j_status ?? context.preparation?.readiness_status
                          )}
                        </td>
                        <td>{displayScalar(row.investment_decision ?? row.gate07k_decision ?? row.outcome)}</td>
                        <td>
                          {displayScalar(
                            row.fid_status ??
                              row.fid ??
                              (row.is_fid == null ? null : row.is_fid ? "FID_GRANTED" : "NOT_FID")
                          )}
                        </td>
                        <td>{displayScalar(row.conditions)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
          <AlertLists blockers={context.blockers} warnings={context.warnings} />
        </>
      )}
      <p className="reviewGuardrail">
        REQUEST_GATE_REVALIDATION records a request only. This surface cannot issue RECYCLE, HOLD, GO, KILL or FID.
      </p>
    </section>
  );
}

function Exceptions({
  budgetResources,
  gateStatus,
  preview,
  session,
}: {
  budgetResources: PortfolioReviewBudgetResources | null;
  gateStatus: PortfolioReviewGateStatus | null;
  preview: PortfolioReviewSnapshot | null;
  session: PortfolioReviewSession;
}) {
  const warnings = [
    ...session.readiness.warnings,
    ...(session.snapshot?.warnings ?? []),
    ...(preview?.warnings ?? []),
    ...(budgetResources?.warnings ?? []),
    ...(gateStatus?.warnings ?? []),
  ];
  const blockers = [
    ...session.readiness.blockers,
    ...(session.snapshot?.blockers ?? []),
    ...(preview?.blockers ?? []),
    ...(budgetResources?.blockers ?? []),
    ...(gateStatus?.blockers ?? []),
  ];
  return (
    <section aria-label="Portfolio Review Exceptions" className="reviewSurface">
      <header className="reviewSurfaceHeader">
        <div>
          <span>Policy-driven alerts</span>
          <h3>Exceptions</h3>
        </div>
        <ShieldCheck aria-hidden="true" size={20} />
      </header>
      {!session.source_current ? (
        <div className="reviewExceptionCritical">
          <b>STALE REVIEW CONTEXT</b>
          <span>
            A governed re-freeze may be required before completion; the existing historical payload is unchanged.
          </span>
        </div>
      ) : null}
      <AlertLists blockers={[...new Set(blockers)]} warnings={[...new Set(warnings)]} />
      {!warnings.length && !blockers.length ? <EmptyData text="No policy warning or blocker was returned." /> : null}
      <p className="reviewGuardrail">Thresholds raise agenda flags; they never automate an investment decision.</p>
    </section>
  );
}

function Conclusions({
  conclusionRationale,
  conclusionType,
  disabled,
  onRationale,
  onSave,
  onType,
  session,
  types,
}: {
  conclusionRationale: string;
  conclusionType: string;
  disabled: boolean;
  onRationale: (value: string) => void;
  onSave: () => void;
  onType: (value: string) => void;
  session: PortfolioReviewSession;
  types: Array<{ code: string; label?: string }>;
}) {
  return (
    <section aria-label="Portfolio Review Conclusions" className="reviewSurface">
      <header className="reviewSurfaceHeader">
        <div>
          <span>Portfolio-level outcome</span>
          <h3>Conclusions</h3>
        </div>
        <CheckCircle2 aria-hidden="true" size={20} />
      </header>
      <div className="reviewConclusionList">
        {session.conclusions.length ? (
          session.conclusions.map((item, index) => (
            <article key={`${item.conclusion_type}-${index}`}>
              <b>{item.conclusion_type}</b>
              <p>{item.rationale}</p>
              {item.conditions?.length ? <small>Conditions: {displayScalar(item.conditions)}</small> : null}
            </article>
          ))
        ) : (
          <EmptyData text="No Portfolio-level conclusion has been recorded." />
        )}
      </div>
      <form
        className="reviewInlineForm"
        onSubmit={(event) => {
          event.preventDefault();
          onSave();
        }}
      >
        <label>
          Conclusion type
          <select disabled={disabled} onChange={(event) => onType(event.target.value)} value={conclusionType}>
            {types.map(({ code, label }) => (
              <option key={code} value={code}>
                {label ?? code}
              </option>
            ))}
          </select>
        </label>
        <label className="wide">
          Rationale
          <textarea
            disabled={disabled}
            onChange={(event) => onRationale(event.target.value)}
            rows={3}
            value={conclusionRationale}
          />
        </label>
        <button disabled={disabled} type="submit">
          <Save aria-hidden="true" size={14} /> Record conclusion
        </button>
      </form>
      <p className="reviewGuardrail">
        These conclusions describe the Portfolio as a whole. They are not Project Gate outcomes.
      </p>
    </section>
  );
}

function Actions({
  draft,
  disabled,
  onCreate,
  onDraft,
  onMutate,
  session,
  actions,
  busy,
  types,
}: {
  draft: PortfolioReviewActionDraft;
  disabled: boolean;
  onCreate: () => void;
  onDraft: (value: PortfolioReviewActionDraft) => void;
  onMutate: (action: PortfolioReviewAction, operation: "approve" | "dispatch" | "status", status?: string) => void;
  session: PortfolioReviewSession;
  actions: PortfolioReviewAction[];
  busy: boolean;
  types: Array<{ code: string; label?: string }>;
}) {
  const [queueFilter, setQueueFilter] = useState("OPEN");
  const [ownerFilter, setOwnerFilter] = useState("");
  const [subjectFilter, setSubjectFilter] = useState("");
  const [subjectIdFilter, setSubjectIdFilter] = useState("");
  const dueSoon = new Date(new Date(today).getTime() + 7 * 86400000).toISOString().slice(0, 10);
  const filteredActions = actions.filter((action) => {
    if (ownerFilter && String(action.owner_user_id) !== ownerFilter) return false;
    if (subjectFilter && action.subject_type !== subjectFilter) return false;
    if (subjectIdFilter && String(action.subject_key ?? action.subject_id) !== subjectIdFilter) return false;
    if (queueFilter === "OPEN") return openAction(action);
    if (queueFilter === "OVERDUE") return openAction(action) && Boolean(action.due_date && action.due_date < today);
    if (queueFilter === "DUE_SOON")
      return openAction(action) && Boolean(action.due_date && action.due_date >= today && action.due_date <= dueSoon);
    return !queueFilter || action.status === queueFilter;
  });
  return (
    <section aria-label="Portfolio Review Actions" className="reviewSurface">
      <header className="reviewSurfaceHeader">
        <div>
          <span>Governance instruction / request queue</span>
          <h3>Actions</h3>
        </div>
        <Send aria-hidden="true" size={20} />
      </header>
      <form
        className="reviewActionForm"
        onSubmit={(event) => {
          event.preventDefault();
          onCreate();
        }}
      >
        <label>
          Action type
          <select
            disabled={disabled}
            onChange={(event) => onDraft({ ...draft, action_type: event.target.value })}
            value={draft.action_type}
          >
            {types.map(({ code, label }) => (
              <option key={code} value={code}>
                {label ?? code}
              </option>
            ))}
          </select>
        </label>
        <label>
          Subject type
          <select
            disabled={disabled}
            onChange={(event) =>
              onDraft({ ...draft, subject_type: event.target.value, subject_id: null, subject_key: null })
            }
            value={draft.subject_type}
          >
            <option>PORTFOLIO</option>
            <option>PROJECT</option>
            <option>BUCKET</option>
            <option>PORTFOLIO_MEMBERSHIP</option>
          </select>
        </label>
        {draft.subject_type === "BUCKET" ? (
          <label>
            Bucket code
            <input
              disabled={disabled}
              value={draft.subject_key ?? ""}
              onChange={(event) => onDraft({ ...draft, subject_key: event.target.value, subject_id: null })}
              required
            />
          </label>
        ) : (
          <label>
            Subject ID
            <input
              disabled={disabled}
              min="1"
              onChange={(event) =>
                onDraft({ ...draft, subject_id: event.target.value ? Number(event.target.value) : null })
              }
              type="number"
              value={draft.subject_id ?? ""}
            />
          </label>
        )}
        <label>
          Priority
          <select
            disabled={disabled}
            onChange={(event) => onDraft({ ...draft, priority: event.target.value })}
            value={draft.priority}
          >
            <option>LOW</option>
            <option>MEDIUM</option>
            <option>HIGH</option>
            <option>CRITICAL</option>
          </select>
        </label>
        <label>
          Owner user ID
          <input
            disabled={disabled}
            min="1"
            onChange={(event) =>
              onDraft({ ...draft, owner_user_id: event.target.value ? Number(event.target.value) : null })
            }
            required
            type="number"
            value={draft.owner_user_id ?? ""}
          />
        </label>
        <label>
          Due date
          <input
            disabled={disabled}
            onChange={(event) => onDraft({ ...draft, due_date: event.target.value || null })}
            type="date"
            value={draft.due_date ?? ""}
          />
        </label>
        <label className="wide">
          Rationale
          <textarea
            disabled={disabled}
            onChange={(event) => onDraft({ ...draft, rationale: event.target.value })}
            required
            rows={3}
            value={draft.rationale}
          />
        </label>
        <button disabled={disabled} type="submit">
          <Send aria-hidden="true" size={14} /> Create governance request
        </button>
      </form>
      {session.status === "COMPLETED" ? (
        <p className="reviewReadOnlyBanner">
          Follow-up actions remain live after Review completion. Historical actions at close remain frozen in the
          Session snapshot.
        </p>
      ) : null}
      <div className="reviewMatrixFilters" aria-label="Portfolio Review Action queue filters">
        <label>
          Queue
          <select value={queueFilter} onChange={(event) => setQueueFilter(event.target.value)}>
            <option value="">All actions</option>
            <option value="OPEN">Open actions</option>
            <option value="DUE_SOON">Due soon (7 days)</option>
            <option value="OVERDUE">Overdue</option>
            <option value="COMPLETED">Completed</option>
            <option value="REJECTED">Rejected</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
        </label>
        <label>
          Filter owner user ID
          <input type="number" min="1" value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)} />
        </label>
        <label>
          Filter subject
          <select value={subjectFilter} onChange={(event) => setSubjectFilter(event.target.value)}>
            <option value="">All subjects</option>
            <option>PORTFOLIO</option>
            <option>PROJECT</option>
            <option>BUCKET</option>
            <option>PORTFOLIO_MEMBERSHIP</option>
          </select>
        </label>
        <label>
          Filter subject ID / Bucket code
          <input type="text" value={subjectIdFilter} onChange={(event) => setSubjectIdFilter(event.target.value)} />
        </label>
      </div>
      <div className="reviewActionQueue">
        {filteredActions.length ? (
          filteredActions.map((action) => (
            <article key={action.id}>
              <header>
                <div>
                  <span>
                    {action.subject_type} ·{" "}
                    {displayScalar(action.subject_name ?? action.subject_key ?? action.subject_id)}
                  </span>
                  <h4>{action.action_type}</h4>
                </div>
                <b className={statusClass(action.status)}>{action.status}</b>
              </header>
              <p>{action.rationale}</p>
              <div className="reviewActionMeta">
                <span>Priority {action.priority}</span>
                <span>Owner {action.owner ?? action.owner_user_id ?? "—"}</span>
                <span>Due {displayDate(action.due_date)}</span>
                <span>Source authority {action.requested_source_authority ?? "request only"}</span>
              </div>
              <footer>
                <select
                  aria-label={`${action.action_type} action status`}
                  disabled={busy || !actionAvailable(action, "update")}
                  onChange={(event) => onMutate(action, "status", event.target.value)}
                  value={action.status}
                >
                  <option>{action.status}</option>
                  {["OPEN", "ACCEPTED"].includes(action.status) ? <option>REJECTED</option> : null}
                  {["ACCEPTED", "IN_PROGRESS"].includes(action.status) ? (
                    <>
                      {action.status === "ACCEPTED" ? <option>IN_PROGRESS</option> : null}
                      <option>COMPLETED</option>
                    </>
                  ) : null}
                  {openAction(action) ? <option>CANCELLED</option> : null}
                </select>
                {actionAvailable(action, "approve") ? (
                  <button disabled={busy} onClick={() => onMutate(action, "approve")} type="button">
                    Approve request
                  </button>
                ) : null}
                {actionAvailable(action, "dispatch") ? (
                  <button disabled={busy} onClick={() => onMutate(action, "dispatch")} type="button">
                    Dispatch via authority adapter
                  </button>
                ) : null}
              </footer>
            </article>
          ))
        ) : (
          <EmptyData text="No Portfolio Review Actions have been recorded." />
        )}
      </div>
      <div className="reviewActionSemantics" role="note">
        <b>Authority boundary</b>
        <span>HOLD_FOR_CAPACITY does not create Gate07K HOLD.</span>
        <span>REQUEST_REASSESSMENT does not recalculate rank.</span>
        <span>REBALANCE_CAPITAL does not edit a Budget Scenario.</span>
        <span>MOVE_BETWEEN_BUCKETS remains a request unless a governed Wave 2A adapter is explicitly dispatched.</span>
      </div>
    </section>
  );
}

function History({
  comparison,
  events,
  session,
}: {
  comparison: PortfolioReviewComparison | null;
  events: PortfolioReviewHistoryEvent[];
  session: PortfolioReviewSession;
}) {
  return (
    <section aria-label="Portfolio Review History" className="reviewSurface">
      <header className="reviewSurfaceHeader">
        <div>
          <span>Immutable audit</span>
          <h3>History & period comparison</h3>
        </div>
        <Clock3 aria-hidden="true" size={20} />
      </header>
      {session.status === "COMPLETED" ? (
        <div className="reviewReadOnlyBanner">
          Completed Review · snapshot, conclusions and historical actions are immutable.
        </div>
      ) : null}
      <div className="reviewSplit">
        <article>
          <h4>Session events</h4>
          <div className="reviewTimeline">
            {events.length ? (
              events.map((event, index) => (
                <div key={`${event.event_type}-${index}`}>
                  <span>{displayDate(event.occurred_at)}</span>
                  <b>{event.event_type}</b>
                  <small>
                    {displayScalar(event.from_status)} → {displayScalar(event.to_status)} ·{" "}
                    {event.actor_name ?? "System"}
                  </small>
                </div>
              ))
            ) : (
              <p>No history events were returned.</p>
            )}
          </div>
        </article>
        <article>
          <h4>Current vs previous completed Review</h4>
          {comparison ? (
            <>
              <p>
                {comparison.current_review_number ?? comparison.current_review_id} vs{" "}
                {comparison.previous_review_number ?? comparison.previous_review_id}
              </p>
              <RecordGrid value={comparison.deltas} />
              <AlertLists blockers={[]} warnings={comparison.warnings} />
            </>
          ) : (
            <p>No previous completed Review is available for comparison.</p>
          )}
        </article>
      </div>
      <p className="reviewGuardrail">
        Period comparison reads both historical snapshots. It does not recalculate an old Review from current rules.
      </p>
    </section>
  );
}

function Trends({ trends }: { trends: PortfolioReviewTrends | null }) {
  return (
    <section aria-label="Portfolio Review Trends" className="reviewSurface">
      <header className="reviewSurfaceHeader">
        <div>
          <span>Observed review points only</span>
          <h3>Trends</h3>
        </div>
        <BarChart3 aria-hidden="true" size={20} />
      </header>
      {!trends?.items.length ? (
        <EmptyData text="No completed Review trend points are available." />
      ) : (
        <div className="reviewTableWrap">
          <table aria-label="Portfolio Review trend points">
            <thead>
              <tr>
                <th>Review</th>
                <th>Date</th>
                <th>Allocation variance</th>
                <th>UNCLASSIFIED</th>
                <th>Projects</th>
                <th>Blocked</th>
                <th>Resource overloads</th>
                <th>Open actions</th>
                <th>FID progression</th>
              </tr>
            </thead>
            <tbody>
              {trends.items.map((point, index) => (
                <tr key={String(point.review_id ?? index)}>
                  <td>{point.review_number ?? point.review_id}</td>
                  <td>{displayDate(point.review_date)}</td>
                  <td>{displayScalar(point.allocation_variance)}</td>
                  <td>{displayScalar(point.unclassified_exposure)}</td>
                  <td>{displayScalar(point.portfolio_count)}</td>
                  <td>{displayScalar(point.blocked_project_count)}</td>
                  <td>{displayScalar(point.resource_overload_count)}</td>
                  <td>{displayScalar(point.open_action_count)}</td>
                  <td>{displayScalar(point.fid_count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <AlertLists blockers={[]} warnings={trends?.warnings ?? []} />
      <p className="reviewGuardrail">
        Trend points come only from completed Reviews; no artificial interpolation is applied.
      </p>
    </section>
  );
}

function RecordGrid({ value }: { value: Record<string, unknown> }) {
  const entries = Object.entries(value);
  if (!entries.length) return <p className="reviewMuted">No governed summary values were returned.</p>;
  return (
    <dl className="reviewRecordGrid">
      {entries.map(([key, item]) => (
        <div key={key}>
          <dt>{key.replace(/_/g, " ")}</dt>
          <dd>{displayScalar(item)}</dd>
        </div>
      ))}
    </dl>
  );
}

function AlertLists({ blockers, warnings }: { blockers: string[]; warnings: string[] }) {
  if (!blockers.length && !warnings.length) return null;
  return (
    <div className="reviewAlerts">
      {blockers.length ? (
        <section className="blockers">
          <h4>Blockers</h4>
          {blockers.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </section>
      ) : null}
      {warnings.length ? (
        <section className="warnings">
          <h4>Warnings</h4>
          {warnings.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </section>
      ) : null}
    </div>
  );
}

function EmptyData({ text }: { text: string }) {
  return (
    <div className="reviewEmpty compact">
      <Layers3 aria-hidden="true" size={20} />
      <p>{text}</p>
    </div>
  );
}
