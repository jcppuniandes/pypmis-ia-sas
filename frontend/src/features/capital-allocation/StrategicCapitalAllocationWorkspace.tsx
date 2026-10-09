import {
  ArchiveRestore,
  BarChart3,
  CheckCircle2,
  Clock3,
  FilePlus2,
  Layers3,
  RefreshCcw,
  Save,
  Send,
  ShieldCheck,
  Tags,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { strategicAllocationApi } from "./api";
import type {
  StrategicAllocationComparison,
  StrategicAllocationHistoryEvent,
  StrategicAllocationLine,
  StrategicAllocationOptions,
  StrategicAllocationPlan,
  StrategicAllocationPlanDraft,
  StrategicBucketClassification,
  StrategicBucketComparison,
  StrategicPositionValue,
} from "./types";
import "./strategicCapitalAllocation.css";

type AllocationView =
  | "overview"
  | "target"
  | "demand"
  | "portfolio"
  | "recommended"
  | "approved"
  | "variance"
  | "classification"
  | "readiness"
  | "history";

const views: Array<[AllocationView, string]> = [
  ["overview", "Overview"],
  ["target", "Target Allocation"],
  ["demand", "Demand Position"],
  ["portfolio", "Portfolio Position"],
  ["recommended", "Recommended Position"],
  ["approved", "Approved Position"],
  ["variance", "Variance"],
  ["classification", "Classification"],
  ["readiness", "Readiness"],
  ["history", "History"],
];

const emptyDraft: StrategicAllocationPlanDraft = {
  name: "",
  description: "",
  planning_cycle_id: 0,
  scope_type: "ENTERPRISE",
  scope_workspace_id: null,
  portfolio_id: null,
  base_currency: null,
  allocation_basis: "PERCENTAGE",
};

function asNumber(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatValue(value: string | number | null | undefined, suffix = "") {
  const numeric = asNumber(value);
  return numeric === null
    ? "—"
    : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(numeric)}${suffix}`;
}

function statusClass(status: string) {
  return `allocationStatus status-${status.toLowerCase().replace(/_/g, "-")}`;
}

function actionAvailable(plan: StrategicAllocationPlan, ...names: string[]) {
  const allowed = new Set(plan.allowed_actions.map((item) => item.toLowerCase().replace(/_/g, "-")));
  return names.some((name) => allowed.has(name.toLowerCase().replace(/_/g, "-")));
}

function defaultLines(options: StrategicAllocationOptions): StrategicAllocationLine[] {
  return options.buckets
    .filter((bucket) => bucket.active !== false)
    .sort((first, second) => (first.display_order ?? 0) - (second.display_order ?? 0))
    .map((bucket) => ({
      bucket_code: bucket.bucket_code,
      bucket_name: bucket.bucket_name,
      target_percentage: null,
      target_amount: null,
      minimum_percentage: null,
      maximum_percentage: null,
      minimum_amount: null,
      maximum_amount: null,
      currency: null,
      rationale: "",
      strategic_objective_codes: [],
      assumptions: [],
      constraints: [],
    }));
}

export default function StrategicCapitalAllocationWorkspace({
  initialView,
  token,
}: {
  initialView?: string;
  token: string;
}) {
  const [activeView, setActiveView] = useState<AllocationView>(
    initialView === "strategic-capital-allocation-history" ? "history" : "overview"
  );
  const [plans, setPlans] = useState<StrategicAllocationPlan[]>([]);
  const [selected, setSelected] = useState<StrategicAllocationPlan | null>(null);
  const [options, setOptions] = useState<StrategicAllocationOptions | null>(null);
  const [comparison, setComparison] = useState<StrategicAllocationComparison | null>(null);
  const [history, setHistory] = useState<StrategicAllocationHistoryEvent[]>([]);
  const [lines, setLines] = useState<StrategicAllocationLine[]>([]);
  const [classifications, setClassifications] = useState<StrategicBucketClassification[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [draft, setDraft] = useState<StrategicAllocationPlanDraft>(emptyDraft);
  const [filterCycle, setFilterCycle] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const loadPlanContext = useCallback(
    async (plan: StrategicAllocationPlan) => {
      const current = await strategicAllocationApi.readPlan(token, plan.id);
      setSelected(current);
      setLines(current.lines?.length ? current.lines : options ? defaultLines(options) : []);
      const [comparisonResult, historyResult] = await Promise.allSettled([
        strategicAllocationApi.comparison(token, current.id),
        strategicAllocationApi.history(token, current.id),
      ]);
      if (comparisonResult.status === "fulfilled") {
        setComparison(comparisonResult.value);
        setClassifications(comparisonResult.value.classifications ?? []);
      } else {
        setComparison(null);
        setClassifications([]);
      }
      setHistory(historyResult.status === "fulfilled" ? historyResult.value : []);
    },
    [options, token]
  );

  const load = useCallback(async () => {
    setBusy(true);
    setMessage("");
    try {
      const [optionResult, planResult] = await Promise.all([
        strategicAllocationApi.options(token),
        strategicAllocationApi.listPlans(token, {
          planning_cycle_id: filterCycle,
          status: filterStatus,
          page: 1,
          page_size: 100,
        }),
      ]);
      setOptions(optionResult);
      setPlans(planResult.items);
      const retained = planResult.items.find((item) => item.id === selected?.id) ?? planResult.items[0] ?? null;
      if (retained) {
        const current = await strategicAllocationApi.readPlan(token, retained.id);
        setSelected(current);
        setLines(current.lines?.length ? current.lines : defaultLines(optionResult));
        const [comparisonResult, historyResult] = await Promise.allSettled([
          strategicAllocationApi.comparison(token, current.id),
          strategicAllocationApi.history(token, current.id),
        ]);
        if (comparisonResult.status === "fulfilled") {
          setComparison(comparisonResult.value);
          setClassifications(comparisonResult.value.classifications ?? []);
        } else {
          setComparison(null);
          setClassifications([]);
        }
        setHistory(historyResult.status === "fulfilled" ? historyResult.value : []);
      } else {
        setSelected(null);
        setComparison(null);
        setHistory([]);
        setLines([]);
        setClassifications([]);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Strategic allocation data could not be loaded.");
    } finally {
      setBusy(false);
    }
  }, [filterCycle, filterStatus, selected?.id, token]);

  useEffect(() => {
    // The governed remote view must reload when its server-side filters change.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    // Selection is retained by load but must not restart the request after it resolves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, filterCycle, filterStatus]);

  useEffect(() => {
    // The same outlet instance may be reused when the canonical navigation view changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setActiveView(initialView === "strategic-capital-allocation-history" ? "history" : "overview");
  }, [initialView]);

  const targetTotal = useMemo(
    () => lines.reduce((sum, line) => sum + (asNumber(line.target_percentage) ?? 0), 0),
    [lines]
  );
  const unclassifiedCount = comparison?.unclassified?.count ?? comparison?.unclassified?.item_count ?? 0;
  const editable = Boolean(selected && ["DRAFT", "RETURNED"].includes(selected.status));
  const scopeWorkspaces = useMemo(() => {
    if (!options) return [];
    return options.workspaces.filter(
      (workspace) =>
        (workspace.workspace_type_code ?? workspace.type ?? "").toUpperCase().replace(/-/g, "_") === draft.scope_type
    );
  }, [draft.scope_type, options]);

  async function selectPlan(plan: StrategicAllocationPlan) {
    setBusy(true);
    setMessage("");
    try {
      await loadPlanContext(plan);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Allocation Plan could not be opened.");
    } finally {
      setBusy(false);
    }
  }

  async function createPlan() {
    if (!draft.name.trim() || !draft.planning_cycle_id || !draft.scope_workspace_id) {
      setMessage("Name, Planning Cycle and Scope Workspace are required.");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const created = await strategicAllocationApi.createPlan(token, draft);
      setShowCreate(false);
      setDraft(emptyDraft);
      setPlans((current) => [created, ...current]);
      await loadPlanContext(created);
      setActiveView("target");
      setMessage(`${created.allocation_plan_number} created as a governed DRAFT.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Allocation Plan creation failed.");
    } finally {
      setBusy(false);
    }
  }

  function updateLine(index: number, key: keyof StrategicAllocationLine, value: unknown) {
    setLines((current) => current.map((line, lineIndex) => (lineIndex === index ? { ...line, [key]: value } : line)));
  }

  async function saveLines() {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      const updated = await strategicAllocationApi.replaceLines(token, selected, lines);
      setSelected(updated);
      setLines(updated.lines);
      setMessage(
        "Target allocation saved. Amounts remain strategic planning envelopes, not approved Budget or Funding."
      );
      setComparison(await strategicAllocationApi.comparison(token, updated.id));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Target allocation could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function saveClassifications() {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      const updated = await strategicAllocationApi.replaceClassifications(token, selected, classifications);
      setSelected(updated);
      const current = await strategicAllocationApi.comparison(token, updated.id);
      setComparison(current);
      setClassifications(current.classifications ?? []);
      setMessage(
        "Primary Bucket classifications saved without changing Ideas, Projects, rank or Portfolio membership."
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Classification could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function runAction(action: "submit" | "return" | "endorse" | "review/start") {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      const updated = await strategicAllocationApi.action(token, selected, action);
      setSelected(updated);
      setPlans((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setHistory(await strategicAllocationApi.history(token, updated.id));
      setMessage(`Lifecycle action ${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Lifecycle action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function createRevision() {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      const revision = await strategicAllocationApi.newRevision(token, selected);
      setPlans((current) => [revision, ...current]);
      await loadPlanContext(revision);
      setActiveView("target");
      setMessage(`Successor revision ${revision.revision_version} created; the endorsed snapshot remains immutable.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Successor revision could not be created.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Strategic Capital Allocation workspace" className="strategicAllocation">
      <CompactModuleHeader
        eyebrow="USER MODE / Enterprise Strategy Manager"
        title="Strategic Capital Allocation"
        description="Govern Bucket-level strategic allocation intent. This surface does not rank Projects or approve Budget, Funding, resources or FID."
        metrics={[
          { label: "Allocation Plans", value: plans.length },
          { label: "Selected status", value: selected?.status ?? "—" },
          { label: "Unclassified", value: unclassifiedCount },
        ]}
      />
      <div className="allocationBoundary" role="note">
        <ShieldCheck aria-hidden="true" size={18} />
        <span>
          Strategic allocation is planning intent only. TARGET, CURRENT DEMAND, CURRENT PORTFOLIO, RECOMMENDED and
          APPROVED are distinct backend-derived positions; amounts are never silently normalized across currencies.
        </span>
      </div>
      {message ? (
        <div className="allocationMessage" role="status">
          {message}
        </div>
      ) : null}

      <section aria-label="Allocation Plan selector" className="allocationSelector">
        <label>
          Planning Cycle
          <select onChange={(event) => setFilterCycle(event.target.value)} value={filterCycle}>
            <option value="">All cycles</option>
            {options?.planning_cycles.map((cycle) => (
              <option key={cycle.id} value={cycle.id}>
                {cycle.cycle_number} · {cycle.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select onChange={(event) => setFilterStatus(event.target.value)} value={filterStatus}>
            <option value="">All statuses</option>
            {(["DRAFT", "SUBMITTED", "IN_REVIEW", "RETURNED", "ENDORSED", "SUPERSEDED", "CANCELLED"] as const).map(
              (value) => (
                <option key={value}>{value}</option>
              )
            )}
          </select>
        </label>
        <label className="allocationPlanSelect">
          Allocation Plan
          <select
            aria-label="Allocation Plan"
            onChange={(event) => {
              const plan = plans.find((item) => item.id === Number(event.target.value));
              if (plan) void selectPlan(plan);
            }}
            value={selected?.id ?? ""}
          >
            {!plans.length ? <option value="">No plans</option> : null}
            {plans.map((plan) => (
              <option key={plan.id} value={plan.id}>
                {plan.allocation_plan_number} · {plan.name} · {plan.status}
              </option>
            ))}
          </select>
        </label>
        <button className="allocationSecondary" disabled={busy} onClick={() => void load()} type="button">
          <RefreshCcw aria-hidden="true" size={14} /> Refresh
        </button>
        <button className="allocationPrimary" disabled={busy} onClick={() => setShowCreate(true)} type="button">
          <FilePlus2 aria-hidden="true" size={14} /> New Allocation Plan
        </button>
      </section>

      <nav aria-label="Strategic Capital Allocation views" className="allocationTabs">
        {views.map(([key, label]) => (
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
        <section className="allocationEmpty">
          <Layers3 aria-hidden="true" size={24} />
          <h3>No Allocation Plan selected</h3>
          <p>Create a DRAFT against an existing Capital Planning Cycle. No live Project or Budget record is created.</p>
        </section>
      ) : (
        <>
          <PlanHeader plan={selected} />
          <section aria-label="Allocation Plan lifecycle actions" className="allocationActions">
            {actionAvailable(selected, "submit") ? (
              <button disabled={busy} onClick={() => void runAction("submit")} type="button">
                <Send aria-hidden="true" size={14} /> Submit plan
              </button>
            ) : null}
            {actionAvailable(selected, "review", "start-review", "review/start") ? (
              <button disabled={busy} onClick={() => void runAction("review/start")} type="button">
                <Clock3 aria-hidden="true" size={14} /> Start review
              </button>
            ) : null}
            {actionAvailable(selected, "return") ? (
              <button disabled={busy} onClick={() => void runAction("return")} type="button">
                Return plan
              </button>
            ) : null}
            {actionAvailable(selected, "endorse") ? (
              <button className="endorse" disabled={busy} onClick={() => void runAction("endorse")} type="button">
                <CheckCircle2 aria-hidden="true" size={14} /> Endorse strategic plan
              </button>
            ) : null}
            {selected.status === "ENDORSED" ? (
              <button disabled={busy} onClick={() => void createRevision()} type="button">
                <ArchiveRestore aria-hidden="true" size={14} /> Create successor revision
              </button>
            ) : null}
          </section>

          {activeView === "overview" ? <Overview plan={selected} comparison={comparison} /> : null}
          {activeView === "target" ? (
            <TargetAllocation
              editable={editable}
              lines={lines}
              onChange={updateLine}
              onSave={() => void saveLines()}
              plan={selected}
              targetTotal={targetTotal}
            />
          ) : null}
          {activeView === "classification" ? (
            <Classification
              buckets={options?.buckets ?? []}
              classifications={classifications}
              editable={editable}
              onChange={setClassifications}
              onSave={() => void saveClassifications()}
              precedence={comparison?.classification_precedence ?? []}
            />
          ) : null}
          {activeView === "readiness" ? <Readiness plan={selected} comparison={comparison} /> : null}
          {activeView === "history" ? <History events={history} plan={selected} /> : null}
          {(["demand", "portfolio", "recommended", "approved", "variance"] as AllocationView[]).includes(activeView) ? (
            <ComparisonTable comparison={comparison} view={activeView} />
          ) : null}
        </>
      )}

      {showCreate ? (
        <div className="allocationDrawerBackdrop" role="presentation">
          <form
            aria-label="New Strategic Capital Allocation Plan form"
            className="allocationDrawer"
            onSubmit={(event) => {
              event.preventDefault();
              void createPlan();
            }}
          >
            <header>
              <div>
                <span>USER live planning record</span>
                <h3>New Strategic Capital Allocation Plan</h3>
              </div>
              <button onClick={() => setShowCreate(false)} type="button">
                Close
              </button>
            </header>
            <div className="allocationFormGrid">
              <label>
                Plan name
                <input
                  onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
                  required
                  value={draft.name}
                />
              </label>
              <label>
                Planning Cycle
                <select
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, planning_cycle_id: Number(event.target.value) }))
                  }
                  required
                  value={draft.planning_cycle_id || ""}
                >
                  <option value="">Select governed cycle</option>
                  {options?.planning_cycles.map((cycle) => (
                    <option key={cycle.id} value={cycle.id}>
                      {cycle.cycle_number} · {cycle.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Planning scope
                <select
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      scope_type: event.target.value as StrategicAllocationPlanDraft["scope_type"],
                      scope_workspace_id: null,
                      portfolio_id: null,
                    }))
                  }
                  value={draft.scope_type}
                >
                  {(options?.scope_options?.length
                    ? options.scope_options
                    : ["ENTERPRISE", "BUSINESS_UNIT", "PORTFOLIO"]
                  ).map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
              {draft.scope_type !== "PORTFOLIO" ? (
                <label>
                  Scope Workspace
                  <select
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        scope_workspace_id: event.target.value ? Number(event.target.value) : null,
                      }))
                    }
                    required
                    value={draft.scope_workspace_id ?? ""}
                  >
                    <option value="">Select governed Workspace</option>
                    {scopeWorkspaces.map((workspace) => (
                      <option key={workspace.id} value={workspace.id}>
                        {workspace.name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <label>
                  Portfolio Workspace
                  <select
                    onChange={(event) =>
                      setDraft((current) => ({
                        ...current,
                        scope_workspace_id: event.target.value ? Number(event.target.value) : null,
                        portfolio_id: event.target.value ? Number(event.target.value) : null,
                      }))
                    }
                    required
                    value={draft.portfolio_id ?? ""}
                  >
                    <option value="">Select Portfolio</option>
                    {scopeWorkspaces.map((portfolio) => (
                      <option key={portfolio.id} value={portfolio.id}>
                        {portfolio.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label>
                Allocation basis
                <select
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      allocation_basis: event.target.value as StrategicAllocationPlanDraft["allocation_basis"],
                    }))
                  }
                  value={draft.allocation_basis}
                >
                  {(options?.allocation_basis_options?.length
                    ? options.allocation_basis_options
                    : ["PERCENTAGE", "INDICATIVE_AMOUNT", "PERCENTAGE_AND_AMOUNT"]
                  ).map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
              <label>
                Base currency (optional)
                <input
                  maxLength={3}
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, base_currency: event.target.value.toUpperCase() || null }))
                  }
                  placeholder="COP"
                  value={draft.base_currency ?? ""}
                />
              </label>
              <label className="wide">
                Description / assumptions
                <textarea
                  onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))}
                  value={draft.description}
                />
              </label>
            </div>
            <aside>
              An indicative amount is a strategic planning envelope only. It does not approve Budget, Funding or an
              executable CAPEX allocation.
            </aside>
            <footer>
              <button className="allocationPrimary" disabled={busy} type="submit">
                Create governed DRAFT
              </button>
            </footer>
          </form>
        </div>
      ) : null}
    </section>
  );
}

function PlanHeader({ plan }: { plan: StrategicAllocationPlan }) {
  return (
    <section aria-label="Selected Allocation Plan" className="allocationPlanHeader">
      <div>
        <span>{plan.allocation_plan_number}</span>
        <h3>{plan.name}</h3>
        <p>{plan.description || "Governed strategic allocation intent."}</p>
      </div>
      <dl>
        <div>
          <dt>Status</dt>
          <dd className={statusClass(plan.status)}>{plan.status}</dd>
        </div>
        <div>
          <dt>Cycle</dt>
          <dd>{plan.planning_cycle_number || plan.planning_cycle_name || plan.planning_cycle_id}</dd>
        </div>
        <div>
          <dt>Scope</dt>
          <dd>{plan.scope_type}</dd>
        </div>
        <div>
          <dt>Basis</dt>
          <dd>{plan.allocation_basis}</dd>
        </div>
        <div>
          <dt>Revision</dt>
          <dd>{plan.revision_version}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>{plan.source_current === false ? "STALE" : plan.staleness_status || "CURRENT"}</dd>
        </div>
      </dl>
    </section>
  );
}

function Overview({
  comparison,
  plan,
}: {
  comparison: StrategicAllocationComparison | null;
  plan: StrategicAllocationPlan;
}) {
  const evaluable = comparison?.buckets.filter((item) => item.status !== "NOT_EVALUABLE").length ?? 0;
  return (
    <section aria-label="Allocation overview" className="allocationSurface">
      <header>
        <div>
          <span>Canonical comparison</span>
          <h3>Target → current → recommended → approved</h3>
        </div>
        <BarChart3 aria-hidden="true" size={22} />
      </header>
      <div className="allocationMetrics">
        <article>
          <span>Configured Buckets</span>
          <strong>{plan.lines.length}</strong>
          <small>Reusable strategic categories, not Project ranks.</small>
        </article>
        <article>
          <span>Evaluable Buckets</span>
          <strong>{evaluable}</strong>
          <small>Currency-compatible source positions.</small>
        </article>
        <article>
          <span>Unclassified exposure</span>
          <strong>{comparison?.unclassified?.count ?? comparison?.unclassified?.item_count ?? 0}</strong>
          <small>Never dropped from the governed denominator.</small>
        </article>
        <article>
          <span>Configuration snapshot</span>
          <strong>{plan.configuration_hash ? plan.configuration_hash.slice(0, 10) : "Pending"}</strong>
          <small>{plan.status === "ENDORSED" ? "Frozen and historically readable." : "Frozen on endorsement."}</small>
        </article>
      </div>
      <div className="allocationDefinitions">
        <article>
          <b>TARGET</b>
          <span>Allocation Plan target.</span>
        </article>
        <article>
          <b>CURRENT DEMAND</b>
          <span>Eligible Capital Demand pipeline.</span>
        </article>
        <article>
          <b>CURRENT PORTFOLIO</b>
          <span>Active Portfolio position.</span>
        </article>
        <article>
          <b>RECOMMENDED</b>
          <span>Selected Portfolio recommendation.</span>
        </article>
        <article>
          <b>APPROVED</b>
          <span>Formal authorized investment only.</span>
        </article>
      </div>
      {comparison?.warnings?.length ? (
        <ul className="allocationWarnings">
          {comparison.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function TargetAllocation({
  editable,
  lines,
  onChange,
  onSave,
  plan,
  targetTotal,
}: {
  editable: boolean;
  lines: StrategicAllocationLine[];
  onChange: (index: number, key: keyof StrategicAllocationLine, value: unknown) => void;
  onSave: () => void;
  plan: StrategicAllocationPlan;
  targetTotal: number;
}) {
  return (
    <section aria-label="Target Allocation" className="allocationSurface">
      <header>
        <div>
          <span>Strategic intent / {plan.allocation_basis}</span>
          <h3>Min / target / max by Bucket</h3>
          <p>Percentages are never silently normalized. Amounts are indicative envelopes, not approved Budget.</p>
        </div>
        <strong className={Math.abs(targetTotal - 100) < 0.001 ? "validTotal" : "warningTotal"}>
          Target total {formatValue(targetTotal, "%")}
        </strong>
      </header>
      <div className="allocationTableScroll">
        <table aria-label="Strategic target allocation lines">
          <thead>
            <tr>
              <th>Bucket</th>
              <th>Min %</th>
              <th>Target %</th>
              <th>Max %</th>
              <th>Target amount</th>
              <th>Currency</th>
              <th>Rationale</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line, index) => (
              <tr key={line.bucket_code}>
                <td>
                  <b>{line.bucket_code}</b>
                  <span>{line.bucket_name}</span>
                </td>
                {(["minimum_percentage", "target_percentage", "maximum_percentage"] as const).map((key) => (
                  <td key={key}>
                    <input
                      aria-label={`${line.bucket_code} ${key.replace(/_/g, " ")}`}
                      disabled={!editable}
                      min="0"
                      onChange={(event) => onChange(index, key, event.target.value || null)}
                      step="0.01"
                      type="number"
                      value={line[key] ?? ""}
                    />
                  </td>
                ))}
                <td>
                  <input
                    aria-label={`${line.bucket_code} target amount`}
                    disabled={!editable}
                    min="0"
                    onChange={(event) => onChange(index, "target_amount", event.target.value || null)}
                    step="0.01"
                    type="number"
                    value={line.target_amount ?? ""}
                  />
                </td>
                <td>
                  <input
                    aria-label={`${line.bucket_code} currency`}
                    disabled={!editable}
                    maxLength={3}
                    onChange={(event) => onChange(index, "currency", event.target.value.toUpperCase() || null)}
                    value={line.currency ?? plan.base_currency ?? ""}
                  />
                </td>
                <td>
                  <input
                    aria-label={`${line.bucket_code} rationale`}
                    disabled={!editable}
                    onChange={(event) => onChange(index, "rationale", event.target.value)}
                    value={line.rationale}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editable ? (
        <footer>
          <button className="allocationPrimary" onClick={onSave} type="button">
            <Save aria-hidden="true" size={14} /> Save target allocation
          </button>
        </footer>
      ) : (
        <footer>
          <span>Endorsed/superseded content is immutable. Create a successor revision for material change.</span>
        </footer>
      )}
    </section>
  );
}

function positionFor(row: StrategicBucketComparison, view: AllocationView): StrategicPositionValue {
  if (view === "demand") return row.current_demand;
  if (view === "portfolio") return row.current_portfolio;
  if (view === "recommended") return row.recommended;
  if (view === "approved") return row.approved;
  return row.target;
}

function currencyBreakdown(value: StrategicPositionValue) {
  const values = Object.entries(value.amounts_by_currency ?? {});
  return values.length ? values.map(([currency, amount]) => `${currency} ${formatValue(amount)}`).join(" · ") : "—";
}

function ComparisonTable({
  comparison,
  view,
}: {
  comparison: StrategicAllocationComparison | null;
  view: AllocationView;
}) {
  const label = views.find(([key]) => key === view)?.[1] ?? "Comparison";
  return (
    <section aria-label={label} className="allocationSurface">
      <header>
        <div>
          <span>Backend-generated read model</span>
          <h3>{label}</h3>
          <p>
            {comparison?.population_definition ||
              "The backend owns classification precedence, eligibility and no-double-counting."}
          </p>
        </div>
      </header>
      {!comparison ? (
        <p className="allocationEmpty">Comparison is not available for this Plan.</p>
      ) : (
        <div className="allocationTableScroll">
          <table aria-label={`${label} by Strategic Capital Bucket`}>
            <thead>
              <tr>
                <th>Bucket</th>
                {view === "variance" ? (
                  <>
                    <th>Target %</th>
                    <th>Demand %</th>
                    <th>Portfolio %</th>
                    <th>Recommended %</th>
                    <th>Approved %</th>
                    <th>Variance</th>
                  </>
                ) : (
                  <>
                    <th>Position %</th>
                    <th>Amount</th>
                    <th>Currency detail</th>
                    <th>Items</th>
                  </>
                )}
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {comparison.buckets.map((row) => {
                const position = positionFor(row, view);
                return (
                  <tr key={row.bucket_code}>
                    <td>
                      <b>{row.bucket_code}</b>
                      <span>{row.bucket_name}</span>
                    </td>
                    {view === "variance" ? (
                      <>
                        <td>{formatValue(row.target.percentage, "%")}</td>
                        <td>{formatValue(row.current_demand.percentage, "%")}</td>
                        <td>{formatValue(row.current_portfolio.percentage, "%")}</td>
                        <td>{formatValue(row.recommended.percentage, "%")}</td>
                        <td>{formatValue(row.approved.percentage, "%")}</td>
                        <td>{formatValue(row.variance_percentage, "%")}</td>
                      </>
                    ) : (
                      <>
                        <td>{formatValue(position.percentage, "%")}</td>
                        <td>{formatValue(position.amount)}</td>
                        <td>{currencyBreakdown(position)}</td>
                        <td>{position.item_count ?? 0}</td>
                      </>
                    )}
                    <td>
                      <span className={statusClass(row.status)}>{row.status}</span>
                    </td>
                  </tr>
                );
              })}
              {view === "demand" && comparison.unclassified ? (
                <tr className="unclassified">
                  <td>
                    <b>UNCLASSIFIED</b>
                    <span>Explicit governed exposure</span>
                  </td>
                  <td>{formatValue(comparison.unclassified.percentage, "%")}</td>
                  <td>{formatValue(comparison.unclassified.amount)}</td>
                  <td>{currencyBreakdown(comparison.unclassified)}</td>
                  <td>{comparison.unclassified.count ?? comparison.unclassified.item_count ?? 0}</td>
                  <td>
                    <span className={statusClass("UNCLASSIFIED_EXPOSURE")}>UNCLASSIFIED_EXPOSURE</span>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Classification({
  buckets,
  classifications,
  editable,
  onChange,
  onSave,
  precedence,
}: {
  buckets: Array<{ bucket_code: string; bucket_name: string; active?: boolean }>;
  classifications: StrategicBucketClassification[];
  editable: boolean;
  onChange: (value: StrategicBucketClassification[]) => void;
  onSave: () => void;
  precedence: string[];
}) {
  return (
    <section aria-label="Demand and Project Bucket classification" className="allocationSurface">
      <header>
        <div>
          <span>One primary Bucket / no double counting</span>
          <h3>Classification</h3>
          <p>
            Precedence:{" "}
            {precedence.length ? precedence.join(" → ") : "explicit → source Demand → Theme default → UNCLASSIFIED"}
          </p>
        </div>
        <Tags aria-hidden="true" size={22} />
      </header>
      {!classifications.length ? (
        <p className="allocationEmpty">No eligible Capital Demands or standalone Project contexts are available.</p>
      ) : (
        <div className="allocationTableScroll">
          <table aria-label="Strategic Bucket classifications">
            <thead>
              <tr>
                <th>Record</th>
                <th>Amount / currency</th>
                <th>Primary Bucket</th>
                <th>Resolution source</th>
                <th>Rationale</th>
              </tr>
            </thead>
            <tbody>
              {classifications.map((item, index) => (
                <tr key={`${item.demand_id ?? "project"}-${item.project_workspace_id ?? index}`}>
                  <td>
                    <b>{item.demand_number || item.project_name || `Context ${index + 1}`}</b>
                    <span>{item.demand_name}</span>
                  </td>
                  <td>
                    {formatValue(item.indicative_capital_need)} {item.currency_code || ""}
                  </td>
                  <td>
                    <select
                      aria-label={`${item.demand_number || item.project_name || `Context ${index + 1}`} primary Bucket`}
                      disabled={!editable}
                      onChange={(event) =>
                        onChange(
                          classifications.map((entry, entryIndex) =>
                            entryIndex === index
                              ? {
                                  ...entry,
                                  bucket_code: event.target.value || null,
                                  classification_source: event.target.value ? "MANUAL" : "UNCLASSIFIED",
                                }
                              : entry
                          )
                        )
                      }
                      value={item.bucket_code ?? ""}
                    >
                      <option value="">UNCLASSIFIED</option>
                      {buckets
                        .filter((bucket) => bucket.active !== false)
                        .map((bucket) => (
                          <option key={bucket.bucket_code} value={bucket.bucket_code}>
                            {bucket.bucket_code} · {bucket.bucket_name}
                          </option>
                        ))}
                    </select>
                  </td>
                  <td>{item.resolution_source || item.classification_source || "UNCLASSIFIED"}</td>
                  <td>
                    <input
                      aria-label={`${item.demand_number || item.project_name || `Context ${index + 1}`} classification rationale`}
                      disabled={!editable}
                      onChange={(event) =>
                        onChange(
                          classifications.map((entry, entryIndex) =>
                            entryIndex === index ? { ...entry, rationale: event.target.value } : entry
                          )
                        )
                      }
                      value={item.rationale ?? ""}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editable && classifications.length ? (
        <footer>
          <button className="allocationPrimary" onClick={onSave} type="button">
            <Save aria-hidden="true" size={14} /> Save primary classifications
          </button>
        </footer>
      ) : null}
    </section>
  );
}

function Readiness({
  plan,
  comparison,
}: {
  plan: StrategicAllocationPlan;
  comparison: StrategicAllocationComparison | null;
}) {
  const readiness = comparison?.readiness ?? plan.readiness;
  return (
    <section aria-label="Allocation Plan readiness" className="allocationSurface">
      <header>
        <div>
          <span>Lightweight planning readiness / not Gate07J evidence</span>
          <h3>{readiness?.overall || "NOT_EVALUATED"}</h3>
        </div>
        <ShieldCheck aria-hidden="true" size={22} />
      </header>
      <div className="allocationReadiness">
        {Object.entries(readiness?.dimensions ?? {}).map(([key, value]) => (
          <article key={key}>
            <span>{key.replace(/_/g, " ")}</span>
            <strong>{String(value)}</strong>
          </article>
        ))}
      </div>
      {readiness?.blockers?.length ? (
        <section>
          <h4>Blockers</h4>
          <ul>
            {readiness.blockers.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {readiness?.warnings?.length ? (
        <section>
          <h4>Warnings</h4>
          <ul>
            {readiness.warnings.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}

function History({ events, plan }: { events: StrategicAllocationHistoryEvent[]; plan: StrategicAllocationPlan }) {
  return (
    <section aria-label="Strategic Allocation history" className="allocationSurface">
      <header>
        <div>
          <span>Immutable audit and revision history</span>
          <h3>{plan.allocation_plan_number} history</h3>
          <p>
            Endorsed snapshots keep their Bucket definitions, target allocation, Cycle, scope, policy and source hashes.
          </p>
        </div>
        <Clock3 aria-hidden="true" size={22} />
      </header>
      <div className="allocationHistory">
        {events.length ? (
          events.map((event, index) => (
            <article key={event.id ?? `${event.event_type}-${index}`}>
              <span>{event.occurred_at ? new Date(event.occurred_at).toLocaleString() : `Event ${index + 1}`}</span>
              <b>{event.event_type}</b>
              <small>
                {event.from_status && event.to_status
                  ? `${event.from_status} → ${event.to_status}`
                  : event.actor_name || "Governed system event"}
              </small>
            </article>
          ))
        ) : (
          <p className="allocationEmpty">No history events were returned.</p>
        )}
      </div>
    </section>
  );
}
