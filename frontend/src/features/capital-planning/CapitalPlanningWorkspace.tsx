/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect -- route synchronization and governed remote reloads intentionally update local view state */
import { CalendarRange, CircleDollarSign, History, Lightbulb, ListFilter, Plus, Send, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ControlFlowView } from "../../navigation/applicationNavigation";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { ideaDemandApi } from "../idea-demand/api";
import type { IdeaOptions } from "../idea-demand/types";
import { capitalPlanningApi, createIdempotencyKey } from "./api";
import type {
  CapitalDemandIdeaOrigin,
  CapitalDemandFilters,
  CapitalPlanningCycle,
  CapitalPlanningCycleDraft,
  CapitalPlanningCycleSummary,
  CapitalPlanningOptions,
  StrategicCapitalDemand,
  StrategicCapitalDemandDraft,
} from "./types";
import "./capitalPlanning.css";

type WorkspaceView = "cycles" | "pipeline" | "my" | "review" | "endorsed" | "history";

const VIEW_BY_ROUTE: Partial<Record<ControlFlowView, WorkspaceView>> = {
  "capital-planning-cycles": "cycles",
  "capital-demand-pipeline": "pipeline",
  "capital-demand-my": "my",
  "capital-demand-review": "review",
  "capital-demand-endorsed": "endorsed",
  "capital-demand-history": "history",
};

const ROUTE_BY_VIEW: Record<WorkspaceView, ControlFlowView> = {
  cycles: "capital-planning-cycles",
  pipeline: "capital-demand-pipeline",
  my: "capital-demand-my",
  review: "capital-demand-review",
  endorsed: "capital-demand-endorsed",
  history: "capital-demand-history",
};

const EMPTY_CYCLE: CapitalPlanningCycleDraft = {
  name: "",
  planning_horizon_start: "",
  planning_horizon_end: "",
  scope_workspace_id: null,
  responsible_organization_workspace_id: null,
  applicable_theme_codes: [],
  capital_basis_currency: null,
  description: "",
};

const EMPTY_DEMAND: StrategicCapitalDemandDraft = {
  name: "",
  description: "",
  planning_cycle_id: 0,
  theme_codes: [],
  strategic_objective_codes: [],
  business_or_asset_need: "",
  strategic_driver: "",
  demand_category: "",
  urgency: "",
  target_horizon: "",
  sponsor_user_id: null,
  owning_workspace_id: 0,
  location_context: "",
  indicative_capital_need: null,
  indicative_capital_range_low: null,
  indicative_capital_range_high: null,
  currency_code: null,
  uncertainty_level: null,
  potential_portfolio_id: null,
  assumptions: [],
  constraints: [],
  dependencies: [],
};

const tabs: Array<{ key: WorkspaceView; label: string }> = [
  { key: "cycles", label: "Planning Cycles" },
  { key: "pipeline", label: "Capital Demand Pipeline" },
  { key: "my", label: "My Demands" },
  { key: "review", label: "Demands in Review" },
  { key: "endorsed", label: "Endorsed Demands" },
  { key: "history", label: "Demand History" },
];

const EMPTY_FILTERS: CapitalDemandFilters = {
  search: "",
  planning_cycle_id: "",
  status: "",
  theme: "",
  strategic_objective: "",
  bucket_code: "",
  driver: "",
  sponsor_user_id: "",
  owning_workspace_id: "",
  urgency: "",
  target_horizon: "",
  potential_portfolio_id: "",
  uncertainty_level: "",
  mine: "",
};

function linesToList(value: string) {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function listToLines(value: string[]) {
  return value.join("\n");
}

function number(value: string | number | null | undefined) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(Number(value || 0));
}

function statusClass(value: string) {
  return `capitalStatus status-${value.toLowerCase().replace(/_/g, "-")}`;
}

function allowed(demand: StrategicCapitalDemand, ...actions: string[]) {
  return actions.some((action) => demand.allowed_actions?.includes(action));
}

function MultiCurrencySummary({ summary }: { summary: CapitalPlanningCycleSummary | null }) {
  const totals = Object.entries(summary?.indicative_capital_totals_by_currency ?? {});

  return (
    <section aria-label="Indicative capital need summary" className="capitalCurrencySummary">
      <header>
        <CircleDollarSign aria-hidden="true" size={18} />
        <div>
          <strong>Indicative Capital Need</strong>
          <span>Planning context only — not approved Budget, allocation, Funding or FIN.</span>
        </div>
      </header>
      <div>
        {totals.length ? (
          totals.map(([currency, total]) => (
            <article key={currency}>
              <span>{currency}</span>
              <strong>{number(total)}</strong>
            </article>
          ))
        ) : (
          <p>No indicative capital values in this view.</p>
        )}
      </div>
      {summary?.normalization_warning || totals.length > 1 ? (
        <p className="capitalCurrencyWarning" role="status">
          {summary?.normalization_warning ||
            "Multiple currencies are shown separately. No currency normalization or silent aggregation was applied."}
        </p>
      ) : null}
    </section>
  );
}

function CycleSurface({
  cycles,
  busy,
  onTransition,
  onCreate,
}: {
  cycles: CapitalPlanningCycle[];
  busy: boolean;
  onTransition: (cycle: CapitalPlanningCycle, action: "open" | "review" | "close") => void;
  onCreate: () => void;
}) {
  return (
    <section aria-label="Capital Planning Cycles" className="capitalSurface">
      <header className="capitalSectionHeader">
        <div>
          <span>Governed planning horizon</span>
          <h3>Capital Planning Cycles</h3>
        </div>
        <button className="capitalPrimary" onClick={onCreate} type="button">
          <Plus aria-hidden="true" size={15} /> New Planning Cycle
        </button>
      </header>
      <div className="capitalCycleGrid">
        {cycles.map((cycle) => (
          <article key={cycle.id}>
            <header>
              <span>{cycle.cycle_number}</span>
              <b className={statusClass(cycle.status)}>{cycle.status}</b>
            </header>
            <h4>{cycle.name}</h4>
            <p>{cycle.description || "Governed period for capital need capture and endorsement."}</p>
            <dl>
              <div>
                <dt>Horizon</dt>
                <dd>
                  {cycle.planning_horizon_start} → {cycle.planning_horizon_end}
                </dd>
              </div>
              <div>
                <dt>Demands</dt>
                <dd>{cycle.demand_count}</dd>
              </div>
              <div>
                <dt>Capital basis</dt>
                <dd>{cycle.capital_basis_currency || "Not specified"}</dd>
              </div>
            </dl>
            {cycle.status === "DRAFT" ? (
              <button
                className="capitalSecondary"
                disabled={busy}
                onClick={() => onTransition(cycle, "open")}
                type="button"
              >
                Open governed cycle
              </button>
            ) : null}
            {cycle.status === "OPEN" ? (
              <button
                className="capitalSecondary"
                disabled={busy}
                onClick={() => onTransition(cycle, "review")}
                type="button"
              >
                Start cycle review
              </button>
            ) : null}
            {cycle.status === "IN_REVIEW" ? (
              <button
                className="capitalSecondary"
                disabled={busy}
                onClick={() => onTransition(cycle, "close")}
                type="button"
              >
                Close governed cycle
              </button>
            ) : null}
            {cycle.status === "CLOSED" ? <small>Closed history is immutable.</small> : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function DemandTable({
  demands,
  onSelect,
  selectedId,
}: {
  demands: StrategicCapitalDemand[];
  onSelect: (item: StrategicCapitalDemand) => void;
  selectedId: number | null;
}) {
  return (
    <div className="capitalTableScroll">
      <table aria-label="Strategic Capital Demand Pipeline">
        <thead>
          <tr>
            <th>Demand</th>
            <th>Planning Cycle</th>
            <th>Theme</th>
            <th>Strategic Objective</th>
            <th>Driver</th>
            <th>Sponsor</th>
            <th>Urgency</th>
            <th>Target Horizon</th>
            <th>Indicative Capital Need</th>
            <th>Uncertainty</th>
            <th>Potential Portfolio</th>
            <th>Status</th>
            <th>Ideas</th>
            <th>Last Updated</th>
          </tr>
        </thead>
        <tbody>
          {demands.map((demand) => (
            <tr
              aria-selected={selectedId === demand.id}
              className={selectedId === demand.id ? "selected" : ""}
              key={demand.id}
              onClick={() => onSelect(demand)}
            >
              <td>
                <button className="capitalDemandLink" onClick={() => onSelect(demand)} type="button">
                  <strong>{demand.demand_number}</strong>
                  <span>{demand.name}</span>
                </button>
              </td>
              <td>{demand.planning_cycle_name || demand.planning_cycle_number || demand.planning_cycle_id}</td>
              <td>{(demand.theme_labels?.length ? demand.theme_labels : demand.theme_codes).join(", ") || "—"}</td>
              <td>
                {(demand.strategic_objective_labels?.length
                  ? demand.strategic_objective_labels
                  : demand.strategic_objective_codes
                ).join(", ") || "—"}
              </td>
              <td>{demand.strategic_driver || "—"}</td>
              <td>{demand.sponsor_name || demand.sponsor_user_id || "—"}</td>
              <td>{demand.urgency || "—"}</td>
              <td>{demand.target_horizon || "—"}</td>
              <td>
                {demand.indicative_capital_need
                  ? `${demand.currency_code || ""} ${number(demand.indicative_capital_need)}`.trim()
                  : "—"}
              </td>
              <td>{demand.uncertainty_level || "—"}</td>
              <td>{demand.potential_portfolio_name || demand.potential_portfolio_id || "—"}</td>
              <td>
                <b className={statusClass(demand.status)}>{demand.status}</b>
              </td>
              <td>{demand.ideas_originated}</td>
              <td>{new Date(demand.updated_at).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!demands.length ? <p className="capitalEmpty">No Capital Demands match this governed view.</p> : null}
    </div>
  );
}

export default function CapitalPlanningWorkspace({
  initialView = "capital-demand-pipeline",
  onNavigate,
  token,
}: {
  initialView?: string;
  onNavigate?: (view: ControlFlowView) => void;
  token: string;
}) {
  const [view, setView] = useState<WorkspaceView>(VIEW_BY_ROUTE[initialView as ControlFlowView] ?? "pipeline");
  const [cycles, setCycles] = useState<CapitalPlanningCycle[]>([]);
  const [demands, setDemands] = useState<StrategicCapitalDemand[]>([]);
  const [options, setOptions] = useState<CapitalPlanningOptions | null>(null);
  const [ideaOptions, setIdeaOptions] = useState<IdeaOptions | null>(null);
  const [selected, setSelected] = useState<StrategicCapitalDemand | null>(null);
  const [origins, setOrigins] = useState<CapitalDemandIdeaOrigin[]>([]);
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([]);
  const [filters, setFilters] = useState<CapitalDemandFilters>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<CapitalDemandFilters>(EMPTY_FILTERS);
  const [summary, setSummary] = useState<CapitalPlanningCycleSummary | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [total, setTotal] = useState(0);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [creatingCycle, setCreatingCycle] = useState(false);
  const [creatingDemand, setCreatingDemand] = useState(false);
  const [editingDemand, setEditingDemand] = useState<StrategicCapitalDemand | null>(null);
  const [originating, setOriginating] = useState(false);
  const [originDraft, setOriginDraft] = useState({
    title: "",
    description: "",
    idea_type: "",
    category: "",
    expected_benefit: "",
  });
  const [cycleDraft, setCycleDraft] = useState(EMPTY_CYCLE);
  const [demandDraft, setDemandDraft] = useState(EMPTY_DEMAND);
  const originKeys = useRef<Record<number, string>>({});
  const demandActionKeys = useRef<Record<string, string>>({});
  const cycleActionKeys = useRef<Record<string, string>>({});

  const load = async (
    preferredId?: number,
    requestedPage = page,
    requestedFilters: CapitalDemandFilters = appliedFilters
  ) => {
    try {
      const viewStatus =
        view === "review"
          ? "SUBMITTED,IN_REVIEW,RETURNED"
          : view === "endorsed"
            ? "ENDORSED"
            : view === "history"
              ? "ENDORSED,DEFERRED,CANCELLED,SUPERSEDED"
              : requestedFilters.status;
      const effectiveFilters = {
        ...requestedFilters,
        status: viewStatus,
        mine: view === "my" ? "true" : requestedFilters.mine,
      };
      const params = new URLSearchParams({ page: String(requestedPage), page_size: String(pageSize) });
      for (const [key, value] of Object.entries(effectiveFilters)) if (value) params.set(key, value);
      const [cyclePage, demandPage, loadedOptions, loadedSummary, loadedIdeaOptions] = await Promise.all([
        capitalPlanningApi.listCycles(token, "page=1&page_size=100"),
        capitalPlanningApi.listDemands(token, params.toString()),
        capitalPlanningApi.options(token),
        capitalPlanningApi.demandSummary(token, effectiveFilters),
        ideaDemandApi.options(token),
      ]);
      setCycles(cyclePage.items);
      setDemands(demandPage.items);
      setOptions(loadedOptions);
      setIdeaOptions(loadedIdeaOptions);
      setSummary(loadedSummary);
      setPage(demandPage.page);
      setTotal(demandPage.total);
      setSelected(
        (current) =>
          demandPage.items.find((item) => item.id === (preferredId ?? current?.id)) ?? demandPage.items[0] ?? null
      );
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Capital Planning services are unavailable.");
    }
  };

  useEffect(() => {
    setView(VIEW_BY_ROUTE[initialView as ControlFlowView] ?? "pipeline");
  }, [initialView]);

  useEffect(() => {
    void load(undefined, 1, appliedFilters);
  }, [token, view]);

  useEffect(() => {
    if (!selected) {
      setOrigins([]);
      setHistory([]);
      return;
    }
    void Promise.all([
      capitalPlanningApi.originatedIdeas(token, selected.id),
      capitalPlanningApi.history(token, selected.id),
    ])
      .then(([loadedOrigins, loadedHistory]) => {
        setOrigins(loadedOrigins);
        setHistory(loadedHistory);
      })
      .catch(() => {
        setOrigins(selected.originated_ideas ?? []);
        setHistory([]);
      });
  }, [selected?.id, token]);

  const visibleDemands = demands;

  async function applyDemandFilters() {
    setAppliedFilters(filters);
    await load(undefined, 1, filters);
  }

  async function clearDemandFilters() {
    setFilters(EMPTY_FILTERS);
    setAppliedFilters(EMPTY_FILTERS);
    await load(undefined, 1, EMPTY_FILTERS);
  }

  async function mutateDemand(action: string, body?: unknown) {
    if (!selected) return;
    const keyName = `${selected.id}:${action}:${selected.revision_version}`;
    const idempotencyKey = (demandActionKeys.current[keyName] ??= createIdempotencyKey());
    setBusy(true);
    setMessage("");
    try {
      const result = await capitalPlanningApi.actionDemand(token, selected, action, body, idempotencyKey);
      delete demandActionKeys.current[keyName];
      await load(result.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Demand action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function originateIdea(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    const key = (originKeys.current[selected.id] ??= createIdempotencyKey());
    setBusy(true);
    setMessage("");
    try {
      const result = await capitalPlanningApi.originateIdea(token, selected, key, originDraft);
      delete originKeys.current[selected.id];
      setOriginating(false);
      setMessage(
        `${result.created ? "Idea originated" : "Idempotent retry resolved"}: ${result.idea_number}. No Project, Portfolio Membership, Budget or Funding record was created.`
      );
      await load(selected.id);
      const [loadedOrigins, loadedHistory] = await Promise.all([
        capitalPlanningApi.originatedIdeas(token, selected.id),
        capitalPlanningApi.history(token, selected.id),
      ]);
      setOrigins(loadedOrigins);
      setHistory(loadedHistory);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Idea origination failed.");
    } finally {
      setBusy(false);
    }
  }

  async function createCycle(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await capitalPlanningApi.createCycle(token, cycleDraft);
      setCreatingCycle(false);
      setCycleDraft(EMPTY_CYCLE);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Planning Cycle creation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function createDemand(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const result = editingDemand
        ? await capitalPlanningApi.updateDemand(token, editingDemand, demandDraft)
        : await capitalPlanningApi.createDemand(token, demandDraft);
      setCreatingDemand(false);
      setEditingDemand(null);
      setDemandDraft(EMPTY_DEMAND);
      await load(result.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Capital Demand creation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function transitionCycle(cycle: CapitalPlanningCycle, action: "open" | "review" | "close") {
    const keyName = `${cycle.id}:${action}:${cycle.revision_version}`;
    const idempotencyKey = (cycleActionKeys.current[keyName] ??= createIdempotencyKey());
    setBusy(true);
    try {
      if (action === "open") await capitalPlanningApi.openCycle(token, cycle, idempotencyKey);
      if (action === "review") await capitalPlanningApi.startCycleReview(token, cycle, idempotencyKey);
      if (action === "close") await capitalPlanningApi.closeCycle(token, cycle, idempotencyKey);
      delete cycleActionKeys.current[keyName];
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Planning Cycle transition failed.");
    } finally {
      setBusy(false);
    }
  }

  function openNewDemand() {
    setEditingDemand(null);
    setDemandDraft(EMPTY_DEMAND);
    setCreatingDemand(true);
  }

  function openDemandEditor(demand: StrategicCapitalDemand) {
    setEditingDemand(demand);
    setDemandDraft({
      name: demand.name,
      description: demand.description,
      planning_cycle_id: demand.planning_cycle_id,
      theme_codes: [...demand.theme_codes],
      strategic_objective_codes: [...demand.strategic_objective_codes],
      business_or_asset_need: demand.business_or_asset_need,
      strategic_driver: demand.strategic_driver,
      demand_category: demand.demand_category || "",
      urgency: demand.urgency || "",
      target_horizon: demand.target_horizon,
      sponsor_user_id: demand.sponsor_user_id,
      owning_workspace_id: demand.owning_workspace_id,
      location_context: demand.location_context || "",
      indicative_capital_need: demand.indicative_capital_need,
      indicative_capital_range_low: demand.indicative_capital_range_low,
      indicative_capital_range_high: demand.indicative_capital_range_high,
      currency_code: demand.currency_code,
      uncertainty_level: demand.uncertainty_level,
      potential_portfolio_id: demand.potential_portfolio_id,
      assumptions: [...demand.assumptions],
      constraints: [...demand.constraints],
      dependencies: [...demand.dependencies],
    });
    setCreatingDemand(true);
  }

  return (
    <section aria-label="Strategic Capital Planning and Demand" className="capitalPlanning">
      <CompactModuleHeader
        eyebrow="USER MODE / Enterprise Strategy Manager"
        title="Strategic Capital Planning & Demand"
        description="Govern capital needs before solution selection. A Capital Demand is not an Idea, Project, Budget, Funding assignment or FIN model."
        metrics={[
          { label: "Planning Cycles", value: cycles.length },
          { label: "Capital Demands", value: total },
          { label: "Endorsed Needs", value: summary?.status_counts.ENDORSED ?? 0 },
          { label: "Ideas on this page", value: demands.reduce((sum, item) => sum + item.ideas_originated, 0) },
        ]}
        tone="user"
      />
      <div className="capitalBoundary" role="note">
        <ShieldCheck aria-hidden="true" size={18} />
        <span>
          Endorsement recognizes a sufficiently defined capital need. It does not approve a solution, Project, Portfolio
          entry, capital, Budget, Funding or FID.
        </span>
      </div>
      {message ? (
        <div className="capitalMessage" role="status">
          {message}
        </div>
      ) : null}
      <nav aria-label="Capital Planning workspace views" className="capitalTabs">
        {tabs.map((tab) => (
          <button
            aria-current={view === tab.key ? "page" : undefined}
            className={view === tab.key ? "active" : ""}
            key={tab.key}
            onClick={() => {
              setView(tab.key);
              onNavigate?.(ROUTE_BY_VIEW[tab.key]);
            }}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {view === "cycles" ? (
        <CycleSurface
          busy={busy}
          cycles={cycles}
          onCreate={() => setCreatingCycle(true)}
          onTransition={(cycle, action) => void transitionCycle(cycle, action)}
        />
      ) : (
        <>
          <section className="capitalSurface">
            <header className="capitalSectionHeader">
              <div>
                <span>Strategic needs before solution selection</span>
                <h3>{tabs.find((item) => item.key === view)?.label}</h3>
              </div>
              <div className="capitalToolbar">
                <label>
                  <ListFilter aria-hidden="true" size={15} />
                  <input
                    aria-label="Search Capital Demands"
                    onChange={(event) => setFilters({ ...filters, search: event.target.value })}
                    placeholder="Search number, name, driver or sponsor"
                    value={filters.search}
                  />
                </label>
                <button className="capitalPrimary" onClick={openNewDemand} type="button">
                  <Plus aria-hidden="true" size={15} /> New Capital Demand
                </button>
              </div>
            </header>
            <section aria-label="Capital Demand server filters" className="capitalFilters">
              <label>
                Planning Cycle
                <select
                  onChange={(event) => setFilters({ ...filters, planning_cycle_id: event.target.value })}
                  value={filters.planning_cycle_id}
                >
                  <option value="">All</option>
                  {cycles.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.cycle_number} · {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Status
                <select
                  disabled={["review", "endorsed", "history"].includes(view)}
                  onChange={(event) => setFilters({ ...filters, status: event.target.value })}
                  value={filters.status}
                >
                  <option value="">All</option>
                  {[
                    "DRAFT",
                    "SUBMITTED",
                    "IN_REVIEW",
                    "RETURNED",
                    "ENDORSED",
                    "DEFERRED",
                    "CANCELLED",
                    "SUPERSEDED",
                  ].map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
              </label>
              <label>
                Theme
                <select
                  onChange={(event) => setFilters({ ...filters, theme: event.target.value })}
                  value={filters.theme}
                >
                  <option value="">All</option>
                  {options?.themes.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Strategic Objective
                <select
                  onChange={(event) => setFilters({ ...filters, strategic_objective: event.target.value })}
                  value={filters.strategic_objective}
                >
                  <option value="">All</option>
                  {options?.strategic_objectives.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Driver
                <select
                  onChange={(event) => setFilters({ ...filters, driver: event.target.value })}
                  value={filters.driver}
                >
                  <option value="">All</option>
                  {options?.demand_drivers.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Sponsor
                <select
                  onChange={(event) => setFilters({ ...filters, sponsor_user_id: event.target.value })}
                  value={filters.sponsor_user_id}
                >
                  <option value="">All</option>
                  {options?.sponsors.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Workspace
                <select
                  onChange={(event) => setFilters({ ...filters, owning_workspace_id: event.target.value })}
                  value={filters.owning_workspace_id}
                >
                  <option value="">All</option>
                  {options?.owning_workspaces.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Urgency
                <select
                  onChange={(event) => setFilters({ ...filters, urgency: event.target.value })}
                  value={filters.urgency}
                >
                  <option value="">All</option>
                  {options?.urgency_levels.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Horizon
                <select
                  onChange={(event) => setFilters({ ...filters, target_horizon: event.target.value })}
                  value={filters.target_horizon}
                >
                  <option value="">All</option>
                  {options?.planning_horizons.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Potential Portfolio
                <select
                  onChange={(event) => setFilters({ ...filters, potential_portfolio_id: event.target.value })}
                  value={filters.potential_portfolio_id}
                >
                  <option value="">All</option>
                  {options?.potential_portfolios.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Uncertainty
                <select
                  onChange={(event) => setFilters({ ...filters, uncertainty_level: event.target.value })}
                  value={filters.uncertainty_level}
                >
                  <option value="">All</option>
                  {options?.uncertainty_levels.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="capitalFilterActions">
                <button className="capitalPrimary" onClick={() => void applyDemandFilters()} type="button">
                  Apply server filters
                </button>
                <button className="capitalSecondary" onClick={() => void clearDemandFilters()} type="button">
                  Clear
                </button>
              </div>
            </section>
            <MultiCurrencySummary summary={summary} />
            <DemandTable demands={visibleDemands} onSelect={setSelected} selectedId={selected?.id ?? null} />
            <footer aria-label="Capital Demand pagination" className="capitalPagination">
              <span>
                Page {page} · {total} governed Demand(s) · {pageSize} per page
              </span>
              <div>
                <button
                  className="capitalSecondary"
                  disabled={page <= 1}
                  onClick={() => void load(undefined, page - 1, appliedFilters)}
                  type="button"
                >
                  Previous
                </button>
                <button
                  className="capitalSecondary"
                  disabled={page * pageSize >= total}
                  onClick={() => void load(undefined, page + 1, appliedFilters)}
                  type="button"
                >
                  Next
                </button>
              </div>
            </footer>
          </section>

          {selected ? (
            <section aria-label="Capital Demand detail" className="capitalDemandDetail">
              <header>
                <div>
                  <span>{selected.demand_number}</span>
                  <h3>{selected.name}</h3>
                  <p>{selected.business_or_asset_need}</p>
                </div>
                <b className={statusClass(selected.status)}>{selected.status}</b>
              </header>
              <div className="capitalDetailGrid">
                <article>
                  <span>Strategic driver</span>
                  <strong>{selected.strategic_driver || "Not defined"}</strong>
                </article>
                <article>
                  <span>Theme / Objectives</span>
                  <strong>{[...selected.theme_codes, ...selected.strategic_objective_codes].join(" · ") || "—"}</strong>
                </article>
                <article>
                  <span>Sponsor / Horizon</span>
                  <strong>
                    {selected.sponsor_name || selected.sponsor_user_id || "—"} · {selected.target_horizon || "—"}
                  </strong>
                </article>
                <article className="indicative">
                  <span>Indicative Capital Need — planning only</span>
                  <strong>
                    {selected.indicative_capital_need
                      ? `${selected.currency_code || ""} ${number(selected.indicative_capital_need)}`.trim()
                      : "Not provided"}
                  </strong>
                  <small>Not an approved Budget, allocation, Funding assignment or FIN model.</small>
                </article>
                <article>
                  <span>Readiness</span>
                  <strong>{selected.readiness?.overall || selected.readiness?.status || "Not assessed"}</strong>
                  {(selected.readiness?.blockers ?? []).map((item) => (
                    <small key={item}>{item}</small>
                  ))}
                </article>
                <article>
                  <span>Potential Portfolio — indicative only</span>
                  <strong>{selected.potential_portfolio_name || selected.potential_portfolio_id || "Not set"}</strong>
                  <small>No Portfolio Membership is created here.</small>
                </article>
              </div>
              <div aria-label="Capital Demand lifecycle actions" className="capitalActions">
                {allowed(selected, "edit") ? (
                  <button disabled={busy} onClick={() => openDemandEditor(selected)} type="button">
                    Edit Demand
                  </button>
                ) : null}
                {allowed(selected, "submit") ? (
                  <button disabled={busy} onClick={() => void mutateDemand("submit")} type="button">
                    <Send aria-hidden="true" size={14} /> Submit
                  </button>
                ) : null}
                {allowed(selected, "review", "start_review", "review/start") ? (
                  <button disabled={busy} onClick={() => void mutateDemand("review/start")} type="button">
                    Start review
                  </button>
                ) : null}
                {allowed(selected, "return") ? (
                  <button
                    disabled={busy}
                    onClick={() => void mutateDemand("return", { reason: "Additional need definition required" })}
                    type="button"
                  >
                    Return
                  </button>
                ) : null}
                {allowed(selected, "endorse") ? (
                  <button disabled={busy} onClick={() => void mutateDemand("endorse")} type="button">
                    Endorse need
                  </button>
                ) : null}
                {allowed(selected, "defer") ? (
                  <button
                    disabled={busy}
                    onClick={() => void mutateDemand("defer", { reason: "Deferred to a future planning horizon" })}
                    type="button"
                  >
                    Defer
                  </button>
                ) : null}
                {allowed(selected, "cancel") ? (
                  <button
                    disabled={busy}
                    onClick={() => void mutateDemand("cancel", { reason: "Capital need cancelled" })}
                    type="button"
                  >
                    Cancel
                  </button>
                ) : null}
                {allowed(selected, "originate_idea", "idea.originate", "originate-idea") ? (
                  <button
                    className="originate"
                    disabled={busy}
                    onClick={() => {
                      setOriginDraft({
                        title: selected.name,
                        description: selected.business_or_asset_need,
                        idea_type: ideaOptions?.idea_types[0]?.code || "",
                        category: ideaOptions?.categories[0]?.code || "",
                        expected_benefit: "",
                      });
                      setOriginating(true);
                    }}
                    type="button"
                  >
                    <Lightbulb aria-hidden="true" size={14} /> Originate Idea
                  </button>
                ) : null}
              </div>
              <div className="capitalTraceGrid">
                <section aria-label="Originated Ideas">
                  <h4>Originated Ideas</h4>
                  <p>One Demand may originate multiple governed Ideas through the existing Idea authority.</p>
                  {origins.map((origin) => (
                    <article key={`${origin.idea_id}-${origin.source_snapshot_hash}`}>
                      <div>
                        <strong>{origin.idea_number}</strong>
                        <span>{origin.idea_title || `Idea ${origin.idea_id}`}</span>
                      </div>
                      <small>Frozen source hash {origin.source_snapshot_hash.slice(0, 12)}…</small>
                      {onNavigate ? (
                        <button onClick={() => onNavigate("idea-lifecycle")} type="button">
                          Open Idea Lifecycle
                        </button>
                      ) : null}
                    </article>
                  ))}
                  {!origins.length ? <small>No Ideas have been explicitly originated from this Demand.</small> : null}
                </section>
                <section aria-label="Capital Demand history">
                  <h4>
                    <History aria-hidden="true" size={16} /> Demand History
                  </h4>
                  {history.slice(0, 8).map((event, index) => (
                    <article key={`${String(event.created_at || event.occurred_at || "event")}-${index}`}>
                      <strong>{String(event.action || event.event_type || event.status || "Demand event")}</strong>
                      <span>{String(event.created_at || event.occurred_at || "")}</span>
                    </article>
                  ))}
                  {!history.length ? <small>No history entries returned.</small> : null}
                </section>
              </div>
            </section>
          ) : null}
        </>
      )}

      {creatingCycle ? (
        <div className="capitalDrawerBackdrop" role="presentation">
          <form aria-label="New Planning Cycle form" className="capitalDrawer" onSubmit={createCycle}>
            <header>
              <div>
                <span>Governed planning period</span>
                <h3>New Planning Cycle</h3>
              </div>
              <button onClick={() => setCreatingCycle(false)} type="button">
                Close
              </button>
            </header>
            <label>
              Name
              <input
                minLength={3}
                onChange={(event) => setCycleDraft({ ...cycleDraft, name: event.target.value })}
                required
                value={cycleDraft.name}
              />
            </label>
            <div className="capitalFormGrid">
              <label>
                Horizon start
                <input
                  onChange={(event) => setCycleDraft({ ...cycleDraft, planning_horizon_start: event.target.value })}
                  required
                  type="date"
                  value={cycleDraft.planning_horizon_start}
                />
              </label>
              <label>
                Horizon end
                <input
                  onChange={(event) => setCycleDraft({ ...cycleDraft, planning_horizon_end: event.target.value })}
                  required
                  type="date"
                  value={cycleDraft.planning_horizon_end}
                />
              </label>
              <label>
                Scope Workspace
                <select
                  onChange={(event) =>
                    setCycleDraft({
                      ...cycleDraft,
                      scope_workspace_id: event.target.value ? Number(event.target.value) : null,
                    })
                  }
                  value={cycleDraft.scope_workspace_id || ""}
                >
                  <option value="">Tenant / enterprise default</option>
                  {options?.owning_workspaces.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Responsible organization
                <select
                  onChange={(event) =>
                    setCycleDraft({
                      ...cycleDraft,
                      responsible_organization_workspace_id: event.target.value ? Number(event.target.value) : null,
                    })
                  }
                  value={cycleDraft.responsible_organization_workspace_id || ""}
                >
                  <option value="">Not specified</option>
                  {options?.owning_workspaces.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Capital basis currency (optional)
                <input
                  maxLength={8}
                  onChange={(event) =>
                    setCycleDraft({ ...cycleDraft, capital_basis_currency: event.target.value.toUpperCase() || null })
                  }
                  value={cycleDraft.capital_basis_currency || ""}
                />
              </label>
            </div>
            <fieldset className="capitalCheckboxList">
              <legend>Applicable Strategic Investment Themes</legend>
              {options?.themes.map((item) => (
                <label key={item.code}>
                  <input
                    checked={cycleDraft.applicable_theme_codes.includes(item.code)}
                    onChange={(event) =>
                      setCycleDraft({
                        ...cycleDraft,
                        applicable_theme_codes: event.target.checked
                          ? [...cycleDraft.applicable_theme_codes, item.code]
                          : cycleDraft.applicable_theme_codes.filter((code) => code !== item.code),
                      })
                    }
                    type="checkbox"
                  />
                  {item.label}
                </label>
              ))}
              {!options?.themes.length ? (
                <small>Publish Themes in ADMIN MODE before constraining a cycle.</small>
              ) : null}
            </fieldset>
            <label>
              Description
              <textarea
                onChange={(event) => setCycleDraft({ ...cycleDraft, description: event.target.value })}
                value={cycleDraft.description}
              />
            </label>
            <footer>
              <button onClick={() => setCreatingCycle(false)} type="button">
                Cancel
              </button>
              <button className="capitalPrimary" disabled={busy} type="submit">
                <CalendarRange aria-hidden="true" size={15} /> Create cycle
              </button>
            </footer>
          </form>
        </div>
      ) : null}

      {creatingDemand ? (
        <div className="capitalDrawerBackdrop" role="presentation">
          <form
            aria-label={editingDemand ? "Edit Capital Demand form" : "New Capital Demand form"}
            className="capitalDrawer wide"
            onSubmit={createDemand}
          >
            <header>
              <div>
                <span>Governed need before solution selection</span>
                <h3>{editingDemand ? "Edit Strategic Capital Demand" : "New Strategic Capital Demand"}</h3>
              </div>
              <button
                onClick={() => {
                  setCreatingDemand(false);
                  setEditingDemand(null);
                }}
                type="button"
              >
                Close
              </button>
            </header>
            <label>
              Demand name
              <input
                minLength={3}
                onChange={(event) => setDemandDraft({ ...demandDraft, name: event.target.value })}
                required
                value={demandDraft.name}
              />
            </label>
            <label>
              Business / asset need
              <textarea
                minLength={3}
                onChange={(event) => setDemandDraft({ ...demandDraft, business_or_asset_need: event.target.value })}
                required
                value={demandDraft.business_or_asset_need}
              />
            </label>
            <div className="capitalFormGrid">
              <label>
                Planning Cycle
                <select
                  onChange={(event) =>
                    setDemandDraft({ ...demandDraft, planning_cycle_id: Number(event.target.value) })
                  }
                  required
                  value={demandDraft.planning_cycle_id || ""}
                >
                  <option value="">Select…</option>
                  {cycles
                    .filter((item) => item.status !== "CLOSED")
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.cycle_number} · {item.name}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Owning Workspace
                <select
                  onChange={(event) =>
                    setDemandDraft({ ...demandDraft, owning_workspace_id: Number(event.target.value) })
                  }
                  required
                  value={demandDraft.owning_workspace_id || ""}
                >
                  <option value="">Select…</option>
                  {options?.owning_workspaces.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Strategic Investment Theme
                <select
                  onChange={(event) => setDemandDraft({ ...demandDraft, theme_codes: [event.target.value] })}
                  required
                  value={demandDraft.theme_codes[0] || ""}
                >
                  <option value="">Select…</option>
                  {options?.themes.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Strategic Objective
                <select
                  onChange={(event) =>
                    setDemandDraft({ ...demandDraft, strategic_objective_codes: [event.target.value] })
                  }
                  required
                  value={demandDraft.strategic_objective_codes[0] || ""}
                >
                  <option value="">Select…</option>
                  {options?.strategic_objectives.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Strategic driver
                <select
                  onChange={(event) => setDemandDraft({ ...demandDraft, strategic_driver: event.target.value })}
                  required
                  value={demandDraft.strategic_driver}
                >
                  <option value="">Select…</option>
                  {options?.demand_drivers.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Category
                <select
                  onChange={(event) => setDemandDraft({ ...demandDraft, demand_category: event.target.value })}
                  value={demandDraft.demand_category}
                >
                  <option value="">Select…</option>
                  {options?.demand_categories.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Sponsor
                <select
                  onChange={(event) =>
                    setDemandDraft({
                      ...demandDraft,
                      sponsor_user_id: event.target.value ? Number(event.target.value) : null,
                    })
                  }
                  required
                  value={demandDraft.sponsor_user_id || ""}
                >
                  <option value="">Select…</option>
                  {options?.sponsors.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Target horizon
                <select
                  onChange={(event) => setDemandDraft({ ...demandDraft, target_horizon: event.target.value })}
                  required
                  value={demandDraft.target_horizon}
                >
                  <option value="">Select…</option>
                  {options?.planning_horizons.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Urgency
                <select
                  onChange={(event) => setDemandDraft({ ...demandDraft, urgency: event.target.value })}
                  value={demandDraft.urgency}
                >
                  <option value="">Select…</option>
                  {options?.urgency_levels.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Uncertainty
                <select
                  onChange={(event) =>
                    setDemandDraft({ ...demandDraft, uncertainty_level: event.target.value || null })
                  }
                  value={demandDraft.uncertainty_level || ""}
                >
                  <option value="">Not specified</option>
                  {options?.uncertainty_levels.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Potential Portfolio (indicative only)
                <select
                  onChange={(event) =>
                    setDemandDraft({
                      ...demandDraft,
                      potential_portfolio_id: event.target.value ? Number(event.target.value) : null,
                    })
                  }
                  value={demandDraft.potential_portfolio_id || ""}
                >
                  <option value="">Not specified</option>
                  {options?.potential_portfolios.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
                <small>No Portfolio Membership is created.</small>
              </label>
              <label>
                Location context
                <input
                  onChange={(event) => setDemandDraft({ ...demandDraft, location_context: event.target.value })}
                  value={demandDraft.location_context}
                />
              </label>
              <label>
                Indicative Capital Need
                <input
                  min="0"
                  onChange={(event) =>
                    setDemandDraft({ ...demandDraft, indicative_capital_need: event.target.value || null })
                  }
                  type="number"
                  value={demandDraft.indicative_capital_need || ""}
                />
                <small>Planning context only. Not approved Budget or Funding.</small>
              </label>
              <label>
                Indicative range low
                <input
                  min="0"
                  onChange={(event) =>
                    setDemandDraft({ ...demandDraft, indicative_capital_range_low: event.target.value || null })
                  }
                  type="number"
                  value={demandDraft.indicative_capital_range_low || ""}
                />
              </label>
              <label>
                Indicative range high
                <input
                  min="0"
                  onChange={(event) =>
                    setDemandDraft({ ...demandDraft, indicative_capital_range_high: event.target.value || null })
                  }
                  type="number"
                  value={demandDraft.indicative_capital_range_high || ""}
                />
              </label>
              <label>
                Currency
                <input
                  maxLength={8}
                  onChange={(event) =>
                    setDemandDraft({ ...demandDraft, currency_code: event.target.value.toUpperCase() || null })
                  }
                  value={demandDraft.currency_code || ""}
                />
              </label>
            </div>
            <label>
              Description
              <textarea
                onChange={(event) => setDemandDraft({ ...demandDraft, description: event.target.value })}
                value={demandDraft.description}
              />
            </label>
            <div className="capitalFormGrid">
              <label>
                Assumptions (one per line)
                <textarea
                  onChange={(event) => setDemandDraft({ ...demandDraft, assumptions: linesToList(event.target.value) })}
                  value={listToLines(demandDraft.assumptions)}
                />
              </label>
              <label>
                Constraints (one per line)
                <textarea
                  onChange={(event) => setDemandDraft({ ...demandDraft, constraints: linesToList(event.target.value) })}
                  value={listToLines(demandDraft.constraints)}
                />
              </label>
              <label>
                Dependencies (one per line)
                <textarea
                  onChange={(event) =>
                    setDemandDraft({ ...demandDraft, dependencies: linesToList(event.target.value) })
                  }
                  value={listToLines(demandDraft.dependencies)}
                />
              </label>
            </div>
            <footer>
              <button
                onClick={() => {
                  setCreatingDemand(false);
                  setEditingDemand(null);
                }}
                type="button"
              >
                Cancel
              </button>
              <button className="capitalPrimary" disabled={busy} type="submit">
                {editingDemand ? "Save governed need" : "Create governed need"}
              </button>
            </footer>
          </form>
        </div>
      ) : null}

      {originating && selected ? (
        <div className="capitalDrawerBackdrop" role="presentation">
          <form aria-label="Originate Idea form" className="capitalDrawer" onSubmit={originateIdea}>
            <header>
              <div>
                <span>{selected.demand_number} · explicit governed origin</span>
                <h3>Originate Idea</h3>
              </div>
              <button onClick={() => setOriginating(false)} type="button">
                Close
              </button>
            </header>
            <div className="capitalBoundary" role="note">
              This action calls the existing Idea authority and freezes the Demand version, configuration and source
              snapshot hash. It does not create a Project, Portfolio Membership, Budget or Funding record.
            </div>
            <label>
              Idea title
              <input
                minLength={3}
                onChange={(event) => setOriginDraft({ ...originDraft, title: event.target.value })}
                required
                value={originDraft.title}
              />
            </label>
            <label>
              Description
              <textarea
                minLength={3}
                onChange={(event) => setOriginDraft({ ...originDraft, description: event.target.value })}
                required
                value={originDraft.description}
              />
            </label>
            <div className="capitalFormGrid">
              <label>
                Governed Idea type
                <select
                  onChange={(event) => setOriginDraft({ ...originDraft, idea_type: event.target.value })}
                  required
                  value={originDraft.idea_type}
                >
                  <option value="">Select…</option>
                  {ideaOptions?.idea_types.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Governed Idea category
                <select
                  onChange={(event) => setOriginDraft({ ...originDraft, category: event.target.value })}
                  required
                  value={originDraft.category}
                >
                  <option value="">Select…</option>
                  {ideaOptions?.categories.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              Expected benefit
              <textarea
                onChange={(event) => setOriginDraft({ ...originDraft, expected_benefit: event.target.value })}
                value={originDraft.expected_benefit}
              />
            </label>
            <footer>
              <button onClick={() => setOriginating(false)} type="button">
                Cancel
              </button>
              <button className="capitalPrimary" disabled={busy} type="submit">
                <Lightbulb aria-hidden="true" size={14} /> Originate governed Idea
              </button>
            </footer>
          </form>
        </div>
      ) : null}
    </section>
  );
}
