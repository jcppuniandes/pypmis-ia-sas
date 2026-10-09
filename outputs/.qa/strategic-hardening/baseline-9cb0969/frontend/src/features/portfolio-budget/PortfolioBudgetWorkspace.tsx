/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { BarChart3, CheckCircle2, Copy, GitBranch, GitCompare, RefreshCw, Snowflake, Target } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import "../portfolio-planning/portfolioPlanning.css";
import { portfolioBudgetApi } from "./api";
import type {
  BudgetPlanningOverview,
  BudgetScenario,
  ProjectDependency,
  ScenarioComparison,
  ScenarioProject,
  Waterline,
} from "./types";
import "./portfolioBudget.css";

type View = "overview" | "targets" | "scenarios" | "waterline" | "dependencies" | "comparison";

function money(value: string | number | null | undefined, currency = "") {
  const numeric = Number(value || 0);
  return `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(numeric)}${currency ? ` ${currency}` : ""}`;
}

function SummaryChips({ scenario }: { scenario: BudgetScenario }) {
  const summary = scenario.summary;
  return (
    <div className="budgetChips" aria-label="Scenario summary">
      <span>
        Target <strong>{money(summary.target_budget)}</strong>
      </span>
      <span>
        Demand <strong>{money(summary.selected_demand)}</strong>
      </span>
      <span>
        Variance <strong>{money(summary.variance)}</strong>
      </span>
      <span>
        Utilization <strong>{summary.utilization_percent}%</strong>
      </span>
      <span>
        Selected <strong>{summary.selected_count}</strong>
      </span>
      <span>
        CAPEX <strong>{money(summary.selected_capex)}</strong>
      </span>
      <span>
        EXPENSE <strong>{money(summary.selected_expense)}</strong>
      </span>
      <span>
        Unclassified <strong>{money(summary.selected_unclassified)}</strong>
      </span>
      <span className={summary.unmet_mandatory_count ? "blocked" : "ready"}>
        Unmet dependencies <strong>{summary.unmet_mandatory_count}</strong>
      </span>
      <span className={scenario.readiness.status.toLowerCase()}>
        Readiness <strong>{scenario.readiness.status}</strong>
      </span>
    </div>
  );
}

function ProjectRow({
  onApply,
  project,
  scenario,
}: {
  onApply: (project: ScenarioProject, state: string, reason: string) => Promise<void>;
  project: ScenarioProject;
  scenario: BudgetScenario;
}) {
  const [state, setState] = useState(project.selection_state);
  const [reason, setReason] = useState(project.forced_reason || "");
  const editable = ["DRAFT", "IN_REVIEW"].includes(scenario.status);
  return (
    <tr>
      <td>
        <select
          aria-label={`Selection state for ${project.project_name}`}
          disabled={!editable}
          onChange={(event) => setState(event.target.value as ScenarioProject["selection_state"])}
          value={state}
        >
          <option>SELECTED</option>
          <option>UNSELECTED</option>
          <option>FORCED_IN</option>
          <option>FORCED_OUT</option>
        </select>
      </td>
      <td>{project.portfolio_rank}</td>
      <td>{project.project_number}</td>
      <td>
        <strong>{project.project_name}</strong>
      </td>
      <td>{project.portfolio_evaluation_score}</td>
      <td>{project.strategic_alignment_score}</td>
      <td>{project.risk_bucket}</td>
      <td>{money(project.cost_value, project.currency)}</td>
      <td>{money(project.capex_amount, project.currency)}</td>
      <td>{money(project.expense_amount, project.currency)}</td>
      <td>{money(project.unclassified_amount, project.currency)}</td>
      <td>{project.dependency_status}</td>
      <td>{project.target_start || "N/A"}</td>
      <td>{project.target_finish || "N/A"}</td>
      <td>
        <input
          aria-label={`Forced reason for ${project.project_name}`}
          disabled={!editable || !state.startsWith("FORCED")}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Reason required for forced state"
          value={reason}
        />
      </td>
      <td>
        <button
          disabled={!editable || (state.startsWith("FORCED") && !reason.trim())}
          onClick={() => void onApply(project, state, reason)}
          type="button"
        >
          Apply
        </button>
      </td>
    </tr>
  );
}

function ScenarioDetail({
  onChanged,
  scenario,
  token,
}: {
  onChanged: (scenario?: BudgetScenario) => Promise<void>;
  scenario: BudgetScenario;
  token: string;
}) {
  const [message, setMessage] = useState("");
  const [refresh, setRefresh] = useState<Record<string, unknown> | null>(null);

  async function action(kind: "freeze" | "clone" | "refresh") {
    try {
      if (kind === "refresh") {
        setRefresh(await portfolioBudgetApi.refreshPreview(token, scenario.id));
        setMessage("Source refresh preview generated; no scenario rows were changed.");
        return;
      }
      const result =
        kind === "freeze"
          ? await portfolioBudgetApi.freezeScenario(token, scenario)
          : await portfolioBudgetApi.cloneScenario(token, scenario);
      await onChanged(result);
      setMessage(`${kind} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${kind} scenario`);
    }
  }

  async function apply(project: ScenarioProject, state: string, reason: string) {
    try {
      const result = await portfolioBudgetApi.selectProject(
        token,
        scenario,
        project.project_workspace_id,
        state,
        reason
      );
      await onChanged(result);
      setMessage("Scenario-only selection updated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to update selection");
    }
  }

  return (
    <section aria-label="Budget Scenario Detail" className="budgetSurface">
      <header className="budgetSectionHeader">
        <div>
          <span>Scenario detail</span>
          <h3>{scenario.scenario_name}</h3>
        </div>
        <div className="budgetActions">
          <button
            disabled={!scenario.allowed_actions.includes("can_refresh_budget_scenario_source")}
            onClick={() => void action("refresh")}
            type="button"
          >
            <RefreshCw size={14} /> Source delta
          </button>
          <button onClick={() => void action("clone")} type="button">
            <Copy size={14} /> Clone revision
          </button>
          <button
            disabled={!scenario.allowed_actions.includes("can_freeze_budget_scenario")}
            onClick={() => void action("freeze")}
            type="button"
          >
            <Snowflake size={14} /> Freeze
          </button>
        </div>
      </header>
      <SummaryChips scenario={scenario} />
      {message ? (
        <div className="planningMessage" role="status">
          {message}
        </div>
      ) : null}
      {scenario.warnings.map((item) => (
        <div className="budgetWarning" key={item}>
          {item}
        </div>
      ))}
      {scenario.blockers.map((item) => (
        <div className="budgetBlocker" key={item}>
          {item}
        </div>
      ))}
      <div className="budgetGridScroll">
        <table aria-label="Scenario Project Selection Grid">
          <thead>
            <tr>
              <th>Selection State</th>
              <th>Rank</th>
              <th>Project</th>
              <th>Name</th>
              <th>Score</th>
              <th>Alignment</th>
              <th>Risk</th>
              <th>Cost</th>
              <th>CAPEX</th>
              <th>EXPENSE</th>
              <th>Unclassified</th>
              <th>Dependency</th>
              <th>Start</th>
              <th>Finish</th>
              <th>Forced Reason</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {scenario.projects.map((project) => (
              <ProjectRow key={project.id} onApply={apply} project={project} scenario={scenario} />
            ))}
          </tbody>
        </table>
      </div>
      <div className="budgetSplit">
        <section>
          <h4>Portfolio Budget Demand by Period</h4>
          <table aria-label="Portfolio Budget Demand by Period">
            <thead>
              <tr>
                <th>Period</th>
                <th>Target</th>
                <th>Selected Demand</th>
                <th>Variance</th>
                <th>CAPEX</th>
                <th>EXPENSE</th>
                <th>Unclassified</th>
              </tr>
            </thead>
            <tbody>
              {scenario.period_view.map((period) => (
                <tr key={period.period_key}>
                  <td>
                    {period.period_key}
                    {period.approximation ? " · planning approximation" : ""}
                  </td>
                  <td>{money(period.target)}</td>
                  <td>{money(period.selected_demand)}</td>
                  <td>{money(period.variance)}</td>
                  <td>{money(period.capex_demand)}</td>
                  <td>{money(period.expense_demand)}</td>
                  <td>{money(period.unclassified_demand)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section>
          <h4>Strategic Balance</h4>
          <pre>{JSON.stringify(scenario.strategic_balance, null, 2)}</pre>
        </section>
      </div>
      {refresh ? (
        <details open>
          <summary>Source refresh delta · persisted=false</summary>
          <pre>{JSON.stringify(refresh, null, 2)}</pre>
        </details>
      ) : null}
    </section>
  );
}

function DependencyRow({
  dependency,
  onDeactivate,
  onUpdate,
}: {
  dependency: ProjectDependency;
  onDeactivate: (dependency: ProjectDependency) => Promise<void>;
  onUpdate: (
    dependency: ProjectDependency,
    payload: {
      dependency_type: string;
      dependency_strength: string;
      description: string;
      effective_from: string | null;
      effective_to: string | null;
      source_reference: string | null;
    }
  ) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [strength, setStrength] = useState(dependency.dependency_strength);
  const [description, setDescription] = useState(dependency.description);
  return (
    <tr>
      <td>
        {dependency.predecessor_project_number}
        <br />
        <small>{dependency.predecessor_project_name}</small>
      </td>
      <td>
        {dependency.successor_project_number}
        <br />
        <small>{dependency.successor_project_name}</small>
      </td>
      <td>{dependency.dependency_type}</td>
      <td>
        {editing ? (
          <select
            aria-label={`Strength for dependency ${dependency.id}`}
            value={strength}
            onChange={(event) => setStrength(event.target.value as ProjectDependency["dependency_strength"])}
          >
            <option>MANDATORY</option>
            <option>OPTIONAL</option>
          </select>
        ) : (
          dependency.dependency_strength
        )}
      </td>
      <td>
        {editing ? (
          <input
            aria-label={`Description for dependency ${dependency.id}`}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        ) : (
          dependency.description || "—"
        )}
      </td>
      <td>
        {dependency.effective_from || "Open"} → {dependency.effective_to || "Open"}
      </td>
      <td>{dependency.source_reference || "—"}</td>
      <td>{dependency.status}</td>
      <td>
        {editing ? (
          <button
            onClick={() =>
              void onUpdate(dependency, {
                dependency_type: dependency.dependency_type,
                dependency_strength: strength,
                description,
                effective_from: dependency.effective_from,
                effective_to: dependency.effective_to,
                source_reference: dependency.source_reference,
              }).then(() => setEditing(false))
            }
            type="button"
          >
            Save
          </button>
        ) : (
          <button disabled={dependency.status !== "ACTIVE"} onClick={() => setEditing(true)} type="button">
            Edit
          </button>
        )}
        <button disabled={dependency.status !== "ACTIVE"} onClick={() => void onDeactivate(dependency)} type="button">
          Deactivate
        </button>
      </td>
    </tr>
  );
}

export default function PortfolioBudgetWorkspace({ token, portfolioId }: { token: string; portfolioId?: number }) {
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [selectedId, setSelectedId] = useState(portfolioId || 0);
  const [view, setView] = useState<View>("overview");
  const [overview, setOverview] = useState<BudgetPlanningOverview | null>(null);
  const [selectedScenarioId, setSelectedScenarioId] = useState(0);
  const [comparisonIds, setComparisonIds] = useState<number[]>([]);
  const [comparison, setComparison] = useState<ScenarioComparison | null>(null);
  const [waterline, setWaterline] = useState<Waterline | null>(null);
  const [waterlinePeriod, setWaterlinePeriod] = useState("TOTAL");
  const [waterlineFilters, setWaterlineFilters] = useState({
    projectType: "ALL",
    risk: "ALL",
    selection: "ALL",
    budgetClass: "ALL",
    objective: "ALL",
  });
  const [dependencies, setDependencies] = useState<ProjectDependency[]>([]);
  const [message, setMessage] = useState("");
  const [targetForm, setTargetForm] = useState({
    start: "2027-01-01",
    finish: "2028-12-31",
    currency: "COP",
    total: "5000000",
    capex: "",
    expense: "",
    source: "Management target",
  });
  const [scenarioForm, setScenarioForm] = useState({
    name: "Priority-based draft",
    mode: "FROM_CURRENT_PRIORITY",
    time: "UNPHASED",
  });
  const [dependencyForm, setDependencyForm] = useState({
    predecessor: 0,
    successor: 0,
    type: "PREREQUISITE",
    strength: "MANDATORY",
    description: "",
    effectiveFrom: "",
    effectiveTo: "",
    source: "",
  });

  useEffect(() => {
    if (portfolioId) {
      setSelectedId(portfolioId);
      return;
    }
    void portfolioPlanningApi
      .portfolioOptions(token)
      .then((items) => {
        setPortfolios(items);
        setSelectedId((current) => current || Number(items[0]?.id || 0));
      })
      .catch(() => setMessage("Unable to load authorized Portfolios."));
  }, [portfolioId, token]);

  async function load(preferredScenario?: BudgetScenario) {
    if (!selectedId) return;
    try {
      const result = await portfolioBudgetApi.overview(token, selectedId);
      setOverview(result);
      setSelectedScenarioId((current) => preferredScenario?.id || current || result.scenarios[0]?.id || 0);
      setMessage("");
      if (preferredScenario || result.scenarios[0]) {
        const scenarioId = preferredScenario?.id || result.scenarios[0]?.id;
        if (scenarioId) setWaterline(await portfolioBudgetApi.waterline(token, scenarioId));
      }
      setDependencies(await portfolioBudgetApi.dependencies(token, selectedId));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load Portfolio Budget Planning");
    }
  }

  useEffect(() => {
    void load();
  }, [selectedId]);

  const selectedScenario = useMemo(
    () => overview?.scenarios.find((item) => item.id === selectedScenarioId) || null,
    [overview?.scenarios, selectedScenarioId]
  );
  const filteredWaterlineProjects = useMemo(() => {
    return (waterline?.projects || []).filter((project) => {
      const objectiveCodes = project.strategic_objectives.map((item) => String(item.code || item.name || ""));
      return (
        (waterlineFilters.projectType === "ALL" || project.project_type === waterlineFilters.projectType) &&
        (waterlineFilters.risk === "ALL" || project.risk_bucket === waterlineFilters.risk) &&
        (waterlineFilters.selection === "ALL" || project.selection_state === waterlineFilters.selection) &&
        (waterlineFilters.objective === "ALL" || objectiveCodes.includes(waterlineFilters.objective)) &&
        (waterlineFilters.budgetClass === "ALL" ||
          (waterlineFilters.budgetClass === "CAPEX" && Number(project.capex_amount || 0) > 0) ||
          (waterlineFilters.budgetClass === "EXPENSE" && Number(project.expense_amount || 0) > 0) ||
          (waterlineFilters.budgetClass === "UNCLASSIFIED" && Number(project.unclassified_amount || 0) > 0))
      );
    });
  }, [waterline, waterlineFilters]);

  async function createTarget() {
    if (!overview) return;
    try {
      await portfolioBudgetApi.createTarget(token, selectedId, {
        planning_horizon_start: targetForm.start,
        planning_horizon_end: targetForm.finish,
        budget_currency: targetForm.currency,
        total_budget_target: Number(targetForm.total),
        capex_budget_target: targetForm.capex ? Number(targetForm.capex) : null,
        expense_budget_target: targetForm.expense ? Number(targetForm.expense) : null,
        source_reference: targetForm.source,
      });
      await load();
      setMessage("Budget Target DRAFT created. Publish explicitly when reviewed.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create Budget Target");
    }
  }

  async function publishTarget(targetId: number) {
    const target = overview?.targets.find((item) => item.id === targetId);
    if (!target) return;
    try {
      await portfolioBudgetApi.publishTarget(token, target);
      await load();
      setMessage("Budget Target published as immutable revision.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to publish Budget Target");
    }
  }

  async function createScenario() {
    if (!overview?.active_target) return;
    try {
      const result = await portfolioBudgetApi.createScenario(token, selectedId, {
        scenario_name: scenarioForm.name,
        budget_target_id: overview.active_target.id,
        creation_mode: scenarioForm.mode,
        time_phasing_method: scenarioForm.time,
        expected_analysis_hash: overview.gate07f.analysis_hash,
      });
      setSelectedScenarioId(result.id);
      setView("scenarios");
      await load(result);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create Budget Scenario");
    }
  }

  async function compare() {
    if (comparisonIds.length < 2) return;
    try {
      setComparison(await portfolioBudgetApi.compare(token, selectedId, comparisonIds));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to compare scenarios");
    }
  }

  async function loadWaterline() {
    if (!selectedScenarioId) return;
    try {
      setWaterline(await portfolioBudgetApi.waterline(token, selectedScenarioId, waterlinePeriod));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load Waterline");
    }
  }

  async function createDependency() {
    if (!dependencyForm.predecessor || !dependencyForm.successor) return;
    try {
      await portfolioBudgetApi.createDependency(token, selectedId, {
        predecessor_project_workspace_id: dependencyForm.predecessor,
        successor_project_workspace_id: dependencyForm.successor,
        dependency_type: dependencyForm.type,
        dependency_strength: dependencyForm.strength,
        description: dependencyForm.description,
        effective_from: dependencyForm.effectiveFrom || null,
        effective_to: dependencyForm.effectiveTo || null,
        source_reference: dependencyForm.source || null,
      });
      setDependencies(await portfolioBudgetApi.dependencies(token, selectedId));
      await load();
      setMessage("Project dependency created. Scenario compliance was recalculated without changing selections.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create Project dependency");
    }
  }

  async function deactivateDependency(dependency: ProjectDependency) {
    try {
      await portfolioBudgetApi.deactivateDependency(token, dependency);
      setDependencies(await portfolioBudgetApi.dependencies(token, selectedId));
      await load();
      setMessage("Project dependency deactivated with audit trace.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to deactivate Project dependency");
    }
  }

  async function updateDependency(
    dependency: ProjectDependency,
    payload: Parameters<typeof portfolioBudgetApi.updateDependency>[2]
  ) {
    try {
      await portfolioBudgetApi.updateDependency(token, dependency, payload);
      setDependencies(await portfolioBudgetApi.dependencies(token, selectedId));
      await load();
      setMessage("Project dependency updated with optimistic concurrency control.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to update Project dependency");
    }
  }

  return (
    <section aria-label="Portfolio Budget Planning" className="portfolioBudget">
      <CompactModuleHeader
        description="Governed strategic Budget Targets and alternative Budget Scenarios. Gate 07E rank and Gate 07F analysis remain read-only; no Funds, Resource Planning, winner, investment approval or FID is created."
        eyebrow="USER MODE · ENTERPRISE STRATEGY MANAGER · PORTFOLIO MANAGER · GATE 07G"
        metrics={[
          {
            label: "Target",
            value: overview?.active_target
              ? money(overview.active_target.total_budget_target, overview.active_target.budget_currency)
              : "PENDING",
          },
          { label: "Scenarios", value: overview?.readiness.scenario_count || 0 },
          { label: "Readiness", value: overview?.readiness.can_enter_budget_recommendation ? "READY" : "REWORK" },
        ]}
        title="Portfolio Budget Planning"
        tone="user"
      />
      <div className="budgetToolbar">
        {!portfolioId ? (
          <label>
            Portfolio
            <select value={selectedId} onChange={(event) => setSelectedId(Number(event.target.value))}>
              {portfolios.map((item) => (
                <option key={Number(item.id)} value={Number(item.id)}>
                  {String(item.name)}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <nav aria-label="Portfolio Budget Planning views">
          {(["overview", "targets", "scenarios", "waterline", "dependencies", "comparison"] as View[]).map((item) => (
            <button
              className={view === item ? "active" : ""}
              key={item}
              onClick={() => {
                setView(item);
                if (item === "waterline") void loadWaterline();
              }}
              type="button"
            >
              {item === "overview" ? (
                <BarChart3 size={14} />
              ) : item === "targets" ? (
                <Target size={14} />
              ) : item === "comparison" ? (
                <GitCompare size={14} />
              ) : item === "dependencies" ? (
                <GitBranch size={14} />
              ) : item === "waterline" ? (
                <BarChart3 size={14} />
              ) : (
                <CheckCircle2 size={14} />
              )}
              {item}
            </button>
          ))}
        </nav>
        <button onClick={() => void load()} type="button">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>
      {message ? (
        <div className="planningMessage" role="status">
          {message}
        </div>
      ) : null}
      {overview && view === "overview" ? (
        <section className="budgetOverview" aria-label="Budget Planning Overview">
          <div className="budgetChips">
            <span>
              Gate 07F <strong>{overview.gate07f.final_output}</strong>
            </span>
            <span>
              Budget branch <strong>{overview.gate07f.can_enter_budget_planning ? "READY" : "BLOCKED"}</strong>
            </span>
            <span>
              Resource branch{" "}
              <strong>
                {overview.gate07f.can_enter_resource_planning ? "INDEPENDENT READY" : "INDEPENDENT PENDING"}
              </strong>
            </span>
            <span>
              Frozen <strong>{overview.readiness.frozen_scenario_count}</strong>
            </span>
          </div>
          <article className="budgetReadiness">
            <span>Gate 07G output</span>
            <h3>{overview.readiness.final_output}</h3>
            <p>
              Ready frozen scenarios: {overview.readiness.ready_scenario_count}. This output does not approve, fund or
              select a scenario.
            </p>
            {overview.readiness.blockers.map((item) => (
              <small key={item}>{item}</small>
            ))}
          </article>
          <div className="budgetBoundary">
            {overview.boundaries.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
        </section>
      ) : null}
      {overview && view === "targets" ? (
        <section className="budgetSurface" aria-label="Budget Targets">
          <header className="budgetSectionHeader">
            <div>
              <span>Governed revisions</span>
              <h3>Budget Targets</h3>
            </div>
          </header>
          <div className="budgetTargetForm">
            <label>
              Horizon start
              <input
                type="date"
                value={targetForm.start}
                onChange={(event) => setTargetForm({ ...targetForm, start: event.target.value })}
              />
            </label>
            <label>
              Horizon end
              <input
                type="date"
                value={targetForm.finish}
                onChange={(event) => setTargetForm({ ...targetForm, finish: event.target.value })}
              />
            </label>
            <label>
              Currency
              <input
                value={targetForm.currency}
                onChange={(event) => setTargetForm({ ...targetForm, currency: event.target.value.toUpperCase() })}
              />
            </label>
            <label>
              Total Budget Target
              <input
                min="0"
                type="number"
                value={targetForm.total}
                onChange={(event) => setTargetForm({ ...targetForm, total: event.target.value })}
              />
            </label>
            <label>
              CAPEX Target (optional)
              <input
                min="0"
                type="number"
                value={targetForm.capex}
                onChange={(event) => setTargetForm({ ...targetForm, capex: event.target.value })}
              />
            </label>
            <label>
              EXPENSE Target (optional)
              <input
                min="0"
                type="number"
                value={targetForm.expense}
                onChange={(event) => setTargetForm({ ...targetForm, expense: event.target.value })}
              />
            </label>
            <label>
              Source reference
              <input
                value={targetForm.source}
                onChange={(event) => setTargetForm({ ...targetForm, source: event.target.value })}
              />
            </label>
            <button onClick={() => void createTarget()} type="button">
              Create DRAFT
            </button>
          </div>
          <div className="budgetCardList">
            {overview.targets.map((target) => (
              <article key={target.id}>
                <span>
                  {target.status} · rev {target.target_revision}
                </span>
                <strong>{money(target.total_budget_target, target.budget_currency)}</strong>
                <small>
                  CAPEX {money(target.capex_budget_target, target.budget_currency)} · EXPENSE{" "}
                  {money(target.expense_budget_target, target.budget_currency)} · unallocated{" "}
                  {money(target.unallocated_budget_target, target.budget_currency)}
                </small>
                <small>
                  {target.planning_horizon_start} → {target.planning_horizon_end}
                </small>
                {target.status === "DRAFT" ? (
                  <button onClick={() => void publishTarget(target.id)} type="button">
                    Publish revision
                  </button>
                ) : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}
      {overview && view === "scenarios" ? (
        <>
          <section className="budgetSurface" aria-label="Budget Scenarios">
            <header className="budgetSectionHeader">
              <div>
                <span>Alternative combinations</span>
                <h3>Budget Scenarios</h3>
              </div>
            </header>
            <div className="budgetScenarioForm">
              <label>
                Name
                <input
                  value={scenarioForm.name}
                  onChange={(event) => setScenarioForm({ ...scenarioForm, name: event.target.value })}
                />
              </label>
              <label>
                Creation mode
                <select
                  value={scenarioForm.mode}
                  onChange={(event) => setScenarioForm({ ...scenarioForm, mode: event.target.value })}
                >
                  <option>EMPTY</option>
                  <option>FROM_CURRENT_PRIORITY</option>
                </select>
              </label>
              <label>
                Time phasing
                <select
                  value={scenarioForm.time}
                  onChange={(event) => setScenarioForm({ ...scenarioForm, time: event.target.value })}
                >
                  <option>UNPHASED</option>
                  <option>LINEAR_BY_PROJECT_DATES</option>
                  <option>CUSTOM_PERIOD_PROFILE</option>
                </select>
              </label>
              <button
                disabled={!overview.active_target || !overview.gate07f.can_enter_budget_planning}
                onClick={() => void createScenario()}
                type="button"
              >
                Create scenario
              </button>
            </div>
            <div className="budgetScenarioTabs">
              {overview.scenarios.map((scenario) => (
                <button
                  className={selectedScenarioId === scenario.id ? "active" : ""}
                  key={scenario.id}
                  onClick={() => setSelectedScenarioId(scenario.id)}
                  type="button"
                >
                  <strong>{scenario.scenario_name}</strong>
                  <span>
                    {scenario.status} · {scenario.analytical_status}
                  </span>
                </button>
              ))}
            </div>
          </section>
          {selectedScenario ? (
            <ScenarioDetail
              onChanged={async (scenario) => {
                if (scenario) setSelectedScenarioId(scenario.id);
                await load(scenario);
              }}
              scenario={selectedScenario}
              token={token}
            />
          ) : null}
        </>
      ) : null}
      {overview && view === "waterline" ? (
        <section className="budgetSurface" aria-label="Portfolio Budget Waterline">
          <header className="budgetSectionHeader">
            <div>
              <span>Derived view · {waterline?.rank_source || "Gate 07E rank"}</span>
              <h3>Waterline</h3>
            </div>
            <button disabled={!selectedScenarioId} onClick={() => void loadWaterline()} type="button">
              <RefreshCw size={14} /> Recalculate
            </button>
          </header>
          <div className="budgetScenarioTabs">
            {overview.scenarios.map((scenario) => (
              <button
                className={selectedScenarioId === scenario.id ? "active" : ""}
                key={scenario.id}
                onClick={() => {
                  setSelectedScenarioId(scenario.id);
                  setWaterlinePeriod("TOTAL");
                  void portfolioBudgetApi.waterline(token, scenario.id).then(setWaterline);
                }}
                type="button"
              >
                <strong>{scenario.scenario_name}</strong>
                <span>{scenario.status}</span>
              </button>
            ))}
          </div>
          {waterline ? (
            <>
              <div className="budgetWaterlineFilters" aria-label="Waterline filters">
                <label>
                  Period
                  <select
                    value={waterlinePeriod}
                    onChange={(event) => {
                      const period = event.target.value;
                      setWaterlinePeriod(period);
                      void portfolioBudgetApi.waterline(token, selectedScenarioId, period).then(setWaterline);
                    }}
                  >
                    <option value="TOTAL">TOTAL</option>
                    {selectedScenario?.period_view.map((period) => (
                      <option key={period.period_key}>{period.period_key}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Project Type
                  <select
                    value={waterlineFilters.projectType}
                    onChange={(event) => setWaterlineFilters({ ...waterlineFilters, projectType: event.target.value })}
                  >
                    <option>ALL</option>
                    {[...new Set(waterline.projects.map((project) => project.project_type).filter(Boolean))].map(
                      (item) => (
                        <option key={item}>{item}</option>
                      )
                    )}
                  </select>
                </label>
                <label>
                  Strategic Objective
                  <select
                    value={waterlineFilters.objective}
                    onChange={(event) => setWaterlineFilters({ ...waterlineFilters, objective: event.target.value })}
                  >
                    <option>ALL</option>
                    {[
                      ...new Set(
                        waterline.projects.flatMap((project) =>
                          project.strategic_objectives.map((item) => String(item.code || item.name || ""))
                        )
                      ),
                    ]
                      .filter(Boolean)
                      .map((item) => (
                        <option key={item}>{item}</option>
                      ))}
                  </select>
                </label>
                <label>
                  Risk Bucket
                  <select
                    value={waterlineFilters.risk}
                    onChange={(event) => setWaterlineFilters({ ...waterlineFilters, risk: event.target.value })}
                  >
                    <option>ALL</option>
                    {[...new Set(waterline.projects.map((project) => project.risk_bucket).filter(Boolean))].map(
                      (item) => (
                        <option key={item}>{item}</option>
                      )
                    )}
                  </select>
                </label>
                <label>
                  Selection State
                  <select
                    value={waterlineFilters.selection}
                    onChange={(event) => setWaterlineFilters({ ...waterlineFilters, selection: event.target.value })}
                  >
                    <option>ALL</option>
                    <option>SELECTED</option>
                    <option>UNSELECTED</option>
                    <option>FORCED_IN</option>
                    <option>FORCED_OUT</option>
                  </select>
                </label>
                <label>
                  Budget Class
                  <select
                    value={waterlineFilters.budgetClass}
                    onChange={(event) => setWaterlineFilters({ ...waterlineFilters, budgetClass: event.target.value })}
                  >
                    <option>ALL</option>
                    <option>CAPEX</option>
                    <option>EXPENSE</option>
                    <option>UNCLASSIFIED</option>
                  </select>
                </label>
              </div>
              <div className="budgetChips" aria-label="Waterline summary">
                <span>
                  Target <strong>{money(waterline.target_budget)}</strong>
                </span>
                <span>
                  Selected <strong>{money(waterline.selected_demand)}</strong>
                </span>
                <span>
                  Variance <strong>{money(waterline.variance)}</strong>
                </span>
                <span>
                  Position <strong>{waterline.waterline_position ?? "Not reached"}</strong>
                </span>
                <span>
                  Status <strong>{waterline.analytical_status}</strong>
                </span>
                <span>
                  Alignment <strong>{waterline.alignment_status}</strong>
                </span>
              </div>
              <div className="budgetGridScroll">
                <table aria-label="Waterline projects">
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Project</th>
                      <th>Selection</th>
                      <th>Demand</th>
                      <th>Cumulative</th>
                      <th>Waterline</th>
                      <th>CAPEX</th>
                      <th>EXPENSE</th>
                      <th>Unclassified</th>
                      <th>Dependency</th>
                      <th>Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredWaterlineProjects.map((project) => (
                      <tr
                        className={project.waterline_side === "BELOW" ? "belowWaterline" : ""}
                        key={project.project_workspace_id}
                      >
                        <td>{project.portfolio_rank}</td>
                        <td>
                          <strong>{project.project_number}</strong>
                          <br />
                          <small>{project.project_name}</small>
                        </td>
                        <td>
                          <details>
                            <summary>Inspect</summary>
                            <small>
                              Type: {project.project_type || "N/A"}
                              <br />
                              Risk: {project.risk_bucket}
                              <br />
                              Forced: {project.forced_state || "No"}
                            </small>
                          </details>
                        </td>
                        <td>{project.selection_state}</td>
                        <td>{money(project.budget_demand)}</td>
                        <td>
                          {money(project.cumulative_selected_demand)}
                          <progress
                            max={Number(project.target_budget) || 1}
                            value={Math.min(
                              Number(project.cumulative_selected_demand),
                              Number(project.target_budget) || 1
                            )}
                          />
                        </td>
                        <td>{project.waterline_side}</td>
                        <td>{money(project.capex_amount)}</td>
                        <td>{money(project.expense_amount)}</td>
                        <td>{money(project.unclassified_amount)}</td>
                        <td>
                          {project.dependency_status}
                          {project.unmet_dependency_count ? ` · ${project.unmet_dependency_count}` : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="budgetBoundary">
                This view reuses the contextual Gate 07E rank and calculates cumulative demand in memory; it does not
                persist a new ranking or select a winner.
              </p>
            </>
          ) : (
            <p>Select a scenario to calculate its Waterline.</p>
          )}
        </section>
      ) : null}
      {overview && view === "dependencies" ? (
        <section className="budgetSurface" aria-label="Project Dependencies">
          <header className="budgetSectionHeader">
            <div>
              <span>Transverse governed relation</span>
              <h3>Project Dependencies</h3>
            </div>
          </header>
          <div className="budgetDependencyForm">
            <label>
              Predecessor
              <select
                value={dependencyForm.predecessor}
                onChange={(event) => setDependencyForm({ ...dependencyForm, predecessor: Number(event.target.value) })}
              >
                <option value={0}>Select Project</option>
                {(selectedScenario?.projects || overview.scenarios[0]?.projects || []).map((project) => (
                  <option key={project.id} value={project.project_workspace_id}>
                    {project.project_number} · {project.project_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Successor
              <select
                value={dependencyForm.successor}
                onChange={(event) => setDependencyForm({ ...dependencyForm, successor: Number(event.target.value) })}
              >
                <option value={0}>Select Project</option>
                {(selectedScenario?.projects || overview.scenarios[0]?.projects || []).map((project) => (
                  <option key={project.id} value={project.project_workspace_id}>
                    {project.project_number} · {project.project_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Type
              <select
                value={dependencyForm.type}
                onChange={(event) => setDependencyForm({ ...dependencyForm, type: event.target.value })}
              >
                {[
                  "PREREQUISITE",
                  "ENABLING",
                  "SEQUENTIAL",
                  "SHARED_INFRASTRUCTURE",
                  "REGULATORY",
                  "FUNDING",
                  "OTHER",
                ].map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label>
              Strength
              <select
                value={dependencyForm.strength}
                onChange={(event) => setDependencyForm({ ...dependencyForm, strength: event.target.value })}
              >
                <option>MANDATORY</option>
                <option>OPTIONAL</option>
              </select>
            </label>
            <label>
              Description
              <input
                value={dependencyForm.description}
                onChange={(event) => setDependencyForm({ ...dependencyForm, description: event.target.value })}
              />
            </label>
            <label>
              Effective from
              <input
                type="date"
                value={dependencyForm.effectiveFrom}
                onChange={(event) => setDependencyForm({ ...dependencyForm, effectiveFrom: event.target.value })}
              />
            </label>
            <label>
              Effective to
              <input
                type="date"
                value={dependencyForm.effectiveTo}
                onChange={(event) => setDependencyForm({ ...dependencyForm, effectiveTo: event.target.value })}
              />
            </label>
            <label>
              Source reference
              <input
                value={dependencyForm.source}
                onChange={(event) => setDependencyForm({ ...dependencyForm, source: event.target.value })}
              />
            </label>
            <button
              disabled={
                !dependencyForm.predecessor ||
                !dependencyForm.successor ||
                dependencyForm.predecessor === dependencyForm.successor
              }
              onClick={() => void createDependency()}
              type="button"
            >
              Create dependency
            </button>
          </div>
          <div className="budgetGridScroll">
            <table aria-label="Project dependency register">
              <thead>
                <tr>
                  <th>Predecessor</th>
                  <th>Successor</th>
                  <th>Type</th>
                  <th>Strength</th>
                  <th>Description</th>
                  <th>Effective dates</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {dependencies.map((dependency) => (
                  <DependencyRow
                    dependency={dependency}
                    key={dependency.id}
                    onDeactivate={deactivateDependency}
                    onUpdate={updateDependency}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <p className="budgetBoundary">
            Mandatory unmet relations can block Freeze; optional relations remain warnings. Selections are never
            auto-corrected.
          </p>
        </section>
      ) : null}
      {overview && view === "comparison" ? (
        <section className="budgetSurface" aria-label="Scenario Comparison">
          <header className="budgetSectionHeader">
            <div>
              <span>2–5 analytical alternatives</span>
              <h3>Scenario Comparison</h3>
            </div>
            <button disabled={comparisonIds.length < 2} onClick={() => void compare()} type="button">
              Compare selected
            </button>
          </header>
          <div className="budgetComparePicker">
            {overview.scenarios.map((scenario) => (
              <label key={scenario.id}>
                <input
                  checked={comparisonIds.includes(scenario.id)}
                  disabled={!comparisonIds.includes(scenario.id) && comparisonIds.length >= 5}
                  onChange={(event) =>
                    setComparisonIds((current) =>
                      event.target.checked ? [...current, scenario.id] : current.filter((item) => item !== scenario.id)
                    )
                  }
                  type="checkbox"
                />
                {scenario.scenario_name} · {scenario.status}
              </label>
            ))}
          </div>
          {comparison ? (
            <>
              <div className="budgetGridScroll">
                <table>
                  <thead>
                    <tr>
                      {Object.keys(comparison.scenarios[0] || {}).map((key) => (
                        <th key={key}>{key.replace(/_/g, " ")}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.scenarios.map((scenario, index) => (
                      <tr key={index}>
                        {Object.keys(comparison.scenarios[0] || {}).map((key) => (
                          <td key={key}>{String(scenario[key] ?? "N/A")}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h4>Project-level comparison</h4>
              <pre>{JSON.stringify(comparison.project_matrix, null, 2)}</pre>
              <h4>Pairwise delta</h4>
              <pre>{JSON.stringify(comparison.pairwise_delta, null, 2)}</pre>
            </>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
