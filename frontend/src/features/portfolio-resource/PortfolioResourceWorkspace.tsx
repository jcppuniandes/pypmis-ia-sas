/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { BarChart3, CalendarClock, Copy, GitCompare, RefreshCw, Snowflake, UsersRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import "../portfolio-planning/portfolioPlanning.css";
import { portfolioResourceApi } from "./api";
import type {
  CapacityDemandCell,
  ResourcePlanningOverview,
  ResourceScenario,
  ResourceScenarioComparison,
  ResourceScenarioProject,
} from "./types";
import "./portfolioResource.css";

type View = "overview" | "capacity" | "demand" | "scenarios" | "comparison";

function number(value: string | number | null | undefined) {
  return new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 }).format(Number(value || 0));
}

function Heatmap({ cells }: { cells: CapacityDemandCell[] }) {
  if (!cells.length) return <p className="resourceEmpty">No role-period capacity/demand cells are available.</p>;
  const max = Math.max(...cells.map((cell) => Number(cell.capacity) || Number(cell.selected_demand) || 1));
  return (
    <div className="resourceAnalytics">
      <section>
        <h4>Role / Period Heatmap</h4>
        <div aria-label="Role Period Capacity Heatmap" className="resourceHeatmap" role="grid">
          {cells.map((cell) => (
            <article
              className={cell.status.toLowerCase()}
              key={`${cell.resource_role_key}-${cell.period_key}`}
              role="gridcell"
            >
              <span>{cell.resource_role_name}</span>
              <strong>{cell.period_key}</strong>
              <small>
                {number(cell.selected_demand)} / {number(cell.capacity)} {cell.unit}
              </small>
              <b>{cell.utilization_percent === null ? "N/A" : `${number(cell.utilization_percent)}%`}</b>
            </article>
          ))}
        </div>
      </section>
      <section>
        <h4>Capacity vs Demand Histogram</h4>
        <div aria-label="Capacity Demand Histogram" className="resourceHistogram">
          {cells.map((cell) => (
            <div key={`${cell.resource_role_key}-${cell.period_key}`}>
              <span>
                {cell.period_key} · {cell.resource_role_name}
              </span>
              <i className="capacity" style={{ width: `${Math.max(2, (Number(cell.capacity) / max) * 100)}%` }} />
              <i className="demand" style={{ width: `${Math.max(2, (Number(cell.selected_demand) / max) * 100)}%` }} />
            </div>
          ))}
        </div>
        <p className="resourceLegend">
          <i className="capacity" /> Capacity <i className="demand" /> Selected demand
        </p>
      </section>
    </div>
  );
}

function ScenarioProjectRow({
  project,
  scenario,
  onChanged,
  token,
}: {
  project: ResourceScenarioProject;
  scenario: ResourceScenario;
  onChanged: (scenario: ResourceScenario) => Promise<void>;
  token: string;
}) {
  const [state, setState] = useState(project.selection_state);
  const [reason, setReason] = useState(project.forced_reason || "");
  const [start, setStart] = useState(project.scenario_start || project.source_project_start || "");
  const [finish, setFinish] = useState(project.scenario_finish || project.source_project_finish || "");
  const editable = ["DRAFT", "IN_REVIEW"].includes(scenario.status);

  return (
    <tr>
      <td>
        <strong>{project.project_name}</strong>
        <small>{project.project_number}</small>
      </td>
      <td>{project.portfolio_rank}</td>
      <td>{project.portfolio_evaluation_score}</td>
      <td>{project.risk_bucket}</td>
      <td>{project.demand_covered ? "Covered" : "Missing"}</td>
      <td>
        <select disabled={!editable} value={state} onChange={(event) => setState(event.target.value as typeof state)}>
          <option>SELECTED</option>
          <option>UNSELECTED</option>
          <option>FORCED_IN</option>
          <option>FORCED_OUT</option>
        </select>
      </td>
      <td>
        <input
          disabled={!editable || !state.startsWith("FORCED")}
          placeholder="Governance reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
      </td>
      <td>
        <input disabled={!editable} type="date" value={start} onChange={(event) => setStart(event.target.value)} />
      </td>
      <td>
        <input disabled={!editable} type="date" value={finish} onChange={(event) => setFinish(event.target.value)} />
      </td>
      <td>{project.schedule_shift_days}</td>
      <td>
        <div className="resourceRowActions">
          <button
            disabled={!editable || (state.startsWith("FORCED") && !reason.trim())}
            onClick={() =>
              void portfolioResourceApi
                .selectProject(token, scenario, project.project_workspace_id, state, reason)
                .then(onChanged)
            }
            type="button"
          >
            Apply state
          </button>
          <button
            disabled={!editable || !start || !finish}
            onClick={() =>
              void portfolioResourceApi
                .adjustTiming(token, scenario, project.project_workspace_id, start, finish)
                .then(onChanged)
            }
            type="button"
          >
            <CalendarClock size={13} /> Shift
          </button>
        </div>
      </td>
    </tr>
  );
}

export default function PortfolioResourceWorkspace({ token, portfolioId }: { token: string; portfolioId?: number }) {
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [selectedId, setSelectedId] = useState(portfolioId || 0);
  const [view, setView] = useState<View>("overview");
  const [overview, setOverview] = useState<ResourcePlanningOverview | null>(null);
  const [scenarioId, setScenarioId] = useState(0);
  const [comparisonIds, setComparisonIds] = useState<number[]>([]);
  const [comparison, setComparison] = useState<ResourceScenarioComparison | null>(null);
  const [message, setMessage] = useState("");
  const [capacityForm, setCapacityForm] = useState({
    name: "Strategic capacity baseline",
    start: "2027-01-01",
    finish: "2027-12-31",
    role: "PROJECT_MANAGER",
    roleName: "Project Manager",
    period: "2027",
    unit: "FTE",
    value: "2",
  });
  const [demandForm, setDemandForm] = useState({
    projectId: "",
    name: "Strategic resource demand",
    start: "2027-01-01",
    finish: "2027-12-31",
    role: "PROJECT_MANAGER",
    roleName: "Project Manager",
    period: "2027",
    unit: "FTE",
    value: "1",
  });
  const [scenarioName, setScenarioName] = useState("Capacity-balanced alternative");

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

  async function load(preferred?: ResourceScenario) {
    if (!selectedId) return;
    try {
      const result = await portfolioResourceApi.overview(token, selectedId);
      setOverview(result);
      setScenarioId((current) => preferred?.id || current || result.scenarios[0]?.id || 0);
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load Portfolio Resource Planning");
    }
  }
  useEffect(() => {
    void load();
  }, [selectedId]);

  const scenario = useMemo(
    () => overview?.scenarios.find((item) => item.id === scenarioId) || null,
    [overview, scenarioId]
  );

  async function createCapacity() {
    try {
      await portfolioResourceApi.createCapacity(token, selectedId, {
        plan_name: capacityForm.name,
        planning_horizon_start: capacityForm.start,
        planning_horizon_end: capacityForm.finish,
        period_granularity: "YEAR",
        source_reference: "Strategic workforce capacity",
        periods: [
          {
            resource_role_key: capacityForm.role,
            resource_role_name: capacityForm.roleName,
            role_category: "MANAGEMENT",
            period_key: capacityForm.period,
            period_start: capacityForm.start,
            period_end: capacityForm.finish,
            capacity_value: Number(capacityForm.value),
            unit: capacityForm.unit,
            source_reference: "Management capacity",
            notes: "",
          },
        ],
      });
      await load();
      setMessage("Capacity Plan DRAFT created. Publish explicitly after review.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create Capacity Plan");
    }
  }

  async function createDemand() {
    try {
      await portfolioResourceApi.createDemand(token, Number(demandForm.projectId), {
        profile_name: demandForm.name,
        source_type: "MANUAL_PORTFOLIO_PLANNING_PROFILE",
        source_reference: "Strategic resource estimate",
        as_of_date: new Date().toISOString().slice(0, 10),
        planning_start: demandForm.start,
        planning_finish: demandForm.finish,
        generation_method: "EXPLICIT_PERIOD_PROFILE",
        periods: [
          {
            resource_role_key: demandForm.role,
            resource_role_name: demandForm.roleName,
            role_category: "MANAGEMENT",
            period_key: demandForm.period,
            period_start: demandForm.start,
            period_end: demandForm.finish,
            demand_value: Number(demandForm.value),
            unit: demandForm.unit,
            source_reference: "Project demand estimate",
            notes: "",
          },
        ],
      });
      await load();
      setMessage("Project Resource Demand Profile DRAFT created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create Demand Profile");
    }
  }

  async function createScenario() {
    if (!overview?.active_capacity_plan) return;
    try {
      const result = await portfolioResourceApi.createScenario(token, selectedId, {
        scenario_name: scenarioName,
        capacity_plan_id: overview.active_capacity_plan.id,
        creation_mode: "FROM_CURRENT_PRIORITY",
        expected_analysis_hash: overview.gate07f.analysis_hash,
      });
      setScenarioId(result.id);
      setView("scenarios");
      await load(result);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create Resource Scenario");
    }
  }

  async function scenarioAction(action: "clone" | "freeze" | "refresh") {
    if (!scenario) return;
    try {
      if (action === "refresh") {
        const result = await portfolioResourceApi.refreshPreview(token, scenario.id);
        setMessage(`Source delta preview generated (persisted=${String(result.persisted)}).`);
        return;
      }
      const result =
        action === "clone"
          ? await portfolioResourceApi.cloneScenario(token, scenario)
          : await portfolioResourceApi.freezeScenario(token, scenario);
      await load(result);
      setMessage(`${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} scenario`);
    }
  }

  return (
    <section aria-label="Portfolio Resource Planning" className="portfolioResource">
      <CompactModuleHeader
        description="Strategic capacity, project demand and alternative resource scenarios by role and period. Gate 07H is parallel to Budget Planning; it does not allocate named people, level schedules, approve investment or create Funds/FID."
        eyebrow="USER MODE · ENTERPRISE STRATEGY MANAGER · PORTFOLIO MANAGER · GATE 07H"
        metrics={[
          { label: "Capacity", value: overview?.active_capacity_plan?.status || "PENDING" },
          { label: "Coverage", value: `${number(overview?.readiness.demand_coverage)}%` },
          { label: "Readiness", value: overview?.readiness.can_enter_resource_recommendation ? "READY" : "REWORK" },
        ]}
        title="Portfolio Resource Planning"
        tone="user"
      />
      <div className="resourceToolbar">
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
        <nav aria-label="Portfolio Resource Planning views">
          {(["overview", "capacity", "demand", "scenarios", "comparison"] as View[]).map((item) => (
            <button className={view === item ? "active" : ""} key={item} onClick={() => setView(item)} type="button">
              {item === "overview" ? (
                <BarChart3 size={14} />
              ) : item === "comparison" ? (
                <GitCompare size={14} />
              ) : (
                <UsersRound size={14} />
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
        <section aria-label="Resource Planning Overview" className="resourceOverview">
          <div className="resourceChips">
            <span>
              Gate 07F <strong>{overview.gate07f.final_output}</strong>
            </span>
            <span>
              Resource branch <strong>{overview.gate07f.can_enter_resource_planning ? "READY" : "BLOCKED"}</strong>
            </span>
            <span>
              Budget branch <strong>INDEPENDENT</strong>
            </span>
            <span>
              Overloaded scenarios <strong>{overview.readiness.overloaded_scenario_count}</strong>
            </span>
          </div>
          <article className="resourceReadiness">
            <span>Gate 07H output</span>
            <h3>{overview.readiness.final_output}</h3>
            <p>
              Ready frozen scenarios: {overview.readiness.ready_scenario_count}. This output is a controlled handoff; it
              is not resource allocation or investment approval.
            </p>
            {overview.readiness.blockers.map((item) => (
              <small key={item}>{item}</small>
            ))}
          </article>
          <div className="resourceBoundary">
            {overview.boundaries.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
          <Heatmap cells={scenario?.heatmap || overview.scenarios[0]?.heatmap || []} />
        </section>
      ) : null}

      {overview && view === "capacity" ? (
        <section aria-label="Resource Capacity Plans" className="resourceSurface">
          <header className="resourceSectionHeader">
            <div>
              <span>Governed role-period supply</span>
              <h3>Resource Capacity Plans</h3>
            </div>
          </header>
          <div className="resourceForm">
            <label>
              Plan name
              <input
                value={capacityForm.name}
                onChange={(event) => setCapacityForm({ ...capacityForm, name: event.target.value })}
              />
            </label>
            <label>
              Role key
              <input
                value={capacityForm.role}
                onChange={(event) => setCapacityForm({ ...capacityForm, role: event.target.value.toUpperCase() })}
              />
            </label>
            <label>
              Role name
              <input
                value={capacityForm.roleName}
                onChange={(event) => setCapacityForm({ ...capacityForm, roleName: event.target.value })}
              />
            </label>
            <label>
              Period
              <input
                value={capacityForm.period}
                onChange={(event) => setCapacityForm({ ...capacityForm, period: event.target.value })}
              />
            </label>
            <label>
              Unit
              <select
                value={capacityForm.unit}
                onChange={(event) => setCapacityForm({ ...capacityForm, unit: event.target.value })}
              >
                <option>FTE</option>
                <option>HOURS</option>
                <option>CREW_EQUIVALENT</option>
              </select>
            </label>
            <label>
              Capacity
              <input
                min="0"
                type="number"
                value={capacityForm.value}
                onChange={(event) => setCapacityForm({ ...capacityForm, value: event.target.value })}
              />
            </label>
            <button onClick={() => void createCapacity()} type="button">
              Create draft
            </button>
          </div>
          <div className="resourceCards">
            {overview.capacity_plans.map((plan) => (
              <article key={plan.id}>
                <span>
                  {plan.status} · revision {plan.plan_revision}
                </span>
                <strong>{plan.plan_name}</strong>
                <small>
                  {plan.periods.length} role-period rows · {plan.period_granularity}
                </small>
                {plan.status === "DRAFT" ? (
                  <button
                    onClick={() => void portfolioResourceApi.publishCapacity(token, plan).then(() => load())}
                    type="button"
                  >
                    Publish immutable revision
                  </button>
                ) : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {overview && view === "demand" ? (
        <section aria-label="Project Resource Demand" className="resourceSurface">
          <header className="resourceSectionHeader">
            <div>
              <span>Strategic demand — roles, not named people</span>
              <h3>Project Resource Demand</h3>
            </div>
          </header>
          <div className="resourceForm">
            <label>
              Project workspace ID
              <input
                min="1"
                type="number"
                value={demandForm.projectId}
                onChange={(event) => setDemandForm({ ...demandForm, projectId: event.target.value })}
              />
            </label>
            <label>
              Profile name
              <input
                value={demandForm.name}
                onChange={(event) => setDemandForm({ ...demandForm, name: event.target.value })}
              />
            </label>
            <label>
              Role key
              <input
                value={demandForm.role}
                onChange={(event) => setDemandForm({ ...demandForm, role: event.target.value.toUpperCase() })}
              />
            </label>
            <label>
              Unit
              <select
                value={demandForm.unit}
                onChange={(event) => setDemandForm({ ...demandForm, unit: event.target.value })}
              >
                <option>FTE</option>
                <option>HOURS</option>
                <option>CREW_EQUIVALENT</option>
              </select>
            </label>
            <label>
              Demand
              <input
                min="0"
                type="number"
                value={demandForm.value}
                onChange={(event) => setDemandForm({ ...demandForm, value: event.target.value })}
              />
            </label>
            <button disabled={!Number(demandForm.projectId)} onClick={() => void createDemand()} type="button">
              Create draft
            </button>
          </div>
          <div className="resourceGridScroll">
            <table aria-label="Project Resource Demand Profiles">
              <thead>
                <tr>
                  <th>Project</th>
                  <th>Profile</th>
                  <th>Source</th>
                  <th>Period</th>
                  <th>Role</th>
                  <th>Demand</th>
                  <th>Unit</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {overview.demand_profiles.flatMap((profile) =>
                  profile.periods.map((period) => (
                    <tr key={period.id}>
                      <td>{profile.project_workspace_id}</td>
                      <td>{profile.profile_name}</td>
                      <td>{profile.source_type}</td>
                      <td>{period.period_key}</td>
                      <td>{period.resource_role_name}</td>
                      <td>{number(period.demand_value)}</td>
                      <td>{period.unit}</td>
                      <td>{profile.status}</td>
                      <td>
                        {profile.status === "DRAFT" ? (
                          <button
                            onClick={() => void portfolioResourceApi.publishDemand(token, profile).then(() => load())}
                            type="button"
                          >
                            Publish
                          </button>
                        ) : (
                          "Immutable"
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {overview && view === "scenarios" ? (
        <section aria-label="Resource Scenarios" className="resourceSurface">
          <header className="resourceSectionHeader">
            <div>
              <span>Alternative strategic combinations</span>
              <h3>Resource Scenarios</h3>
            </div>
            <div className="resourceActions">
              <input
                aria-label="Resource Scenario name"
                value={scenarioName}
                onChange={(event) => setScenarioName(event.target.value)}
              />
              <button disabled={!overview.active_capacity_plan} onClick={() => void createScenario()} type="button">
                Create from priority
              </button>
            </div>
          </header>
          <div className="resourceScenarioTabs">
            {overview.scenarios.map((item) => (
              <button
                className={item.id === scenarioId ? "active" : ""}
                key={item.id}
                onClick={() => setScenarioId(item.id)}
                type="button"
              >
                <strong>{item.scenario_name}</strong>
                <span>
                  {item.status} · {item.readiness.status}
                </span>
              </button>
            ))}
          </div>
          {scenario ? (
            <>
              <div className="resourceChips">
                <span>
                  Selected <strong>{scenario.summary.selected_count}</strong>
                </span>
                <span>
                  Coverage <strong>{number(scenario.summary.demand_coverage_percent)}%</strong>
                </span>
                <span>
                  Overloaded periods <strong>{scenario.summary.overloaded_period_count}</strong>
                </span>
                <span>
                  Peak utilization{" "}
                  <strong>
                    {scenario.summary.peak_utilization ? `${number(scenario.summary.peak_utilization)}%` : "N/A"}
                  </strong>
                </span>
                <span className={scenario.readiness.status.toLowerCase()}>
                  Readiness <strong>{scenario.readiness.status}</strong>
                </span>
              </div>
              <div className="resourceActions">
                <button onClick={() => void scenarioAction("refresh")} type="button">
                  <RefreshCw size={14} /> Source delta
                </button>
                <button onClick={() => void scenarioAction("clone")} type="button">
                  <Copy size={14} /> Clone
                </button>
                <button
                  disabled={!scenario.allowed_actions.includes("can_freeze_resource_scenario")}
                  onClick={() => void scenarioAction("freeze")}
                  type="button"
                >
                  <Snowflake size={14} /> Freeze
                </button>
              </div>
              {scenario.blockers.map((item) => (
                <div className="resourceBlocker" key={item}>
                  {item}
                </div>
              ))}
              {scenario.warnings.map((item) => (
                <div className="resourceWarning" key={item}>
                  {item}
                </div>
              ))}
              <div className="resourceGridScroll">
                <table aria-label="Resource Scenario Project Grid">
                  <thead>
                    <tr>
                      <th>Project</th>
                      <th>Rank</th>
                      <th>Score</th>
                      <th>Risk</th>
                      <th>Demand</th>
                      <th>State</th>
                      <th>Reason</th>
                      <th>Start</th>
                      <th>Finish</th>
                      <th>Shift days</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scenario.projects.map((project) => (
                      <ScenarioProjectRow
                        key={project.id}
                        onChanged={async (result) => {
                          await load(result);
                        }}
                        project={project}
                        scenario={scenario}
                        token={token}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
              <Heatmap cells={scenario.heatmap} />
            </>
          ) : (
            <p className="resourceEmpty">Create a scenario after publishing capacity and project demand.</p>
          )}
        </section>
      ) : null}

      {overview && view === "comparison" ? (
        <section aria-label="Resource Scenario Comparison" className="resourceSurface">
          <header className="resourceSectionHeader">
            <div>
              <span>Controlled delta</span>
              <h3>Scenario Comparison</h3>
            </div>
          </header>
          <div className="resourceComparePicker">
            {overview.scenarios.map((item) => (
              <label key={item.id}>
                <input
                  checked={comparisonIds.includes(item.id)}
                  onChange={(event) =>
                    setComparisonIds((current) =>
                      event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id)
                    )
                  }
                  type="checkbox"
                />
                {item.scenario_name}
              </label>
            ))}
            <button
              disabled={comparisonIds.length < 2}
              onClick={() => void portfolioResourceApi.compare(token, selectedId, comparisonIds).then(setComparison)}
              type="button"
            >
              Compare selected
            </button>
          </div>
          {comparison ? (
            <div className="resourceComparison">
              <section>
                <h4>Scenario metrics</h4>
                <pre>{JSON.stringify(comparison.scenarios, null, 2)}</pre>
              </section>
              <section>
                <h4>Pairwise delta</h4>
                <pre>{JSON.stringify(comparison.pairwise_delta, null, 2)}</pre>
              </section>
              <section>
                <h4>Project matrix</h4>
                <pre>{JSON.stringify(comparison.project_matrix, null, 2)}</pre>
              </section>
              <section>
                <h4>Role demand delta</h4>
                <pre>{JSON.stringify(comparison.role_demand_delta, null, 2)}</pre>
              </section>
            </div>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
