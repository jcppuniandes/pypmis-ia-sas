/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { BarChart3, CircleDot, Filter, RefreshCw, Table2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import "../portfolio-planning/portfolioPlanning.css";
import { portfolioAnalysisApi } from "./api";
import type { AnalysisFilters, InvestorMapPoint, PortfolioAnalysisOverview, ProjectAnalysisDetail } from "./types";
import "./portfolioAnalysis.css";

type View = "overview" | "investor-map" | "scorecard";

const colors = ["#0f8f8a", "#2f73b7", "#d17a00", "#8b5fbf", "#a63d40", "#4d7c0f"];

function metricLabel(overview: PortfolioAnalysisOverview, key: string) {
  return overview.dataset.metric_catalog.find((item) => item.metric_key === key)?.label || key.replace(/_/g, " ");
}

function pointColor(value: string) {
  if (value === "HIGH") return "#c2413b";
  if (value === "MEDIUM") return "#d17a00";
  if (value === "LOW") return "#0f8f8a";
  let sum = 0;
  for (const character of value) sum += character.charCodeAt(0);
  return colors[sum % colors.length];
}

function InvestorMapView({
  onSelect,
  overview,
}: {
  onSelect: (point: InvestorMapPoint) => void;
  overview: PortfolioAnalysisOverview;
}) {
  const map = overview.investor_map;
  const points = map.points
    .filter((item) => item.x !== null && item.y !== null)
    .map((item) => ({
      ...item,
      x: Number(item.x),
      y: Number(item.y),
      z: Math.max(1, Number(item.bubble_size)),
    }));
  return (
    <section aria-label="Investor Map" className="analysisSurface">
      <header className="analysisSectionHeader">
        <div>
          <span>Comparative visualization</span>
          <h3>Investor Map</h3>
        </div>
        <div className="analysisEncoding" aria-label="Investor Map encoding">
          <span>X · {metricLabel(overview, map.x_metric)}</span>
          <span>Y · {metricLabel(overview, map.y_metric)}</span>
          <span>
            Size · {map.size_metric_applied && map.size_metric ? metricLabel(overview, map.size_metric) : "Fixed"}
          </span>
          <span>Color · {metricLabel(overview, map.color_metric)}</span>
        </div>
      </header>
      {map.warnings.map((warning) => (
        <div className="analysisWarning" key={warning} role="status">
          {warning}
        </div>
      ))}
      <div className="investorMapChart" role="img" aria-label={`${points.length} Projects plotted in the Investor Map`}>
        <ResponsiveContainer height={420} width="100%">
          <ScatterChart margin={{ bottom: 28, left: 12, right: 24, top: 24 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="x" name={metricLabel(overview, map.x_metric)} type="number" />
            <YAxis dataKey="y" name={metricLabel(overview, map.y_metric)} type="number" />
            <ZAxis dataKey="z" range={[70, 420]} type="number" />
            <Tooltip
              cursor={{ strokeDasharray: "3 3" }}
              formatter={(value, name) => [String(value), String(name)]}
              labelFormatter={(_label, payload) => String(payload?.[0]?.payload?.project_name || "Project")}
            />
            {map.reference_lines.map((line) =>
              line.axis === "x" ? (
                <ReferenceLine key={`x-${line.label}`} label={line.label} stroke="#64748b" x={line.value} />
              ) : (
                <ReferenceLine key={`y-${line.label}`} label={line.label} stroke="#64748b" y={line.value} />
              )
            )}
            <Scatter data={points} name="Projects">
              {points.map((point) => (
                <Cell fill={pointColor(point.color)} key={point.project_workspace_id} />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <div className="analysisPointList" aria-label="Investor Map accessible Project list">
        {map.points.map((point) => (
          <button
            data-testid={`investor-map-project-${point.project_workspace_id}`}
            key={point.project_workspace_id}
            onClick={() => onSelect(point)}
            type="button"
          >
            <CircleDot color={pointColor(point.color)} size={15} />
            <strong>#{point.portfolio_rank}</strong>
            <span>{point.project_number}</span>
            <small>{point.project_name}</small>
          </button>
        ))}
      </div>
      <p className="analysisAccessibilityNote">
        The Scorecard contains the same core Project information and remains the accessible analytical alternative to
        the chart.
      </p>
    </section>
  );
}

function ScorecardView({
  onSelect,
  overview,
}: {
  onSelect: (projectId: number) => void;
  overview: PortfolioAnalysisOverview;
}) {
  const [sort, setSort] = useState<{ key: string; direction: "asc" | "desc" }>({
    key: "portfolio_rank",
    direction: "asc",
  });
  const rows = useMemo(() => {
    return [...overview.scorecard.rows].sort((first, second) => {
      const a = first[sort.key];
      const b = second[sort.key];
      if (a === b) return 0;
      if (a === null || a === undefined) return 1;
      if (b === null || b === undefined) return -1;
      const numeric = Number(a) - Number(b);
      const result = Number.isNaN(numeric) ? String(a).localeCompare(String(b)) : numeric;
      return sort.direction === "asc" ? result : -result;
    });
  }, [overview.scorecard.rows, sort]);
  return (
    <section aria-label="Portfolio Scorecard" className="analysisSurface">
      <header className="analysisSectionHeader">
        <div>
          <span>Accessible analytical table</span>
          <h3>Portfolio Scorecard</h3>
        </div>
        <strong>{rows.length} Projects</strong>
      </header>
      <div className="scorecardScroll">
        <table>
          <thead>
            <tr>
              {overview.scorecard.columns.map((column) => (
                <th key={column} scope="col">
                  <button
                    aria-label={`Sort by ${metricLabel(overview, column)}`}
                    onClick={() =>
                      setSort((current) => ({
                        key: column,
                        direction: current.key === column && current.direction === "asc" ? "desc" : "asc",
                      }))
                    }
                    type="button"
                  >
                    {metricLabel(overview, column)}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                data-testid={`portfolio-scorecard-project-${row.project_workspace_id}`}
                key={Number(row.project_workspace_id)}
                onClick={() => onSelect(Number(row.project_workspace_id))}
              >
                {overview.scorecard.columns.map((column) => (
                  <td key={column}>
                    {row[column] === null || row[column] === undefined || row[column] === ""
                      ? "N/A"
                      : String(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function OverviewView({ overview }: { overview: PortfolioAnalysisOverview }) {
  const summary = overview.summary;
  return (
    <section aria-label="Portfolio Analysis Overview" className="analysisOverview">
      <div className="analysisSummaryGrid">
        <article>
          <span>Eligible Projects</span>
          <strong>{summary.eligible_projects}</strong>
        </article>
        <article>
          <span>Average score</span>
          <strong>{summary.average_portfolio_score || "N/A"}</strong>
        </article>
        <article>
          <span>High priority</span>
          <strong>{summary.high_priority_count}</strong>
        </article>
        <article>
          <span>High risk</span>
          <strong>{summary.high_risk_count}</strong>
        </article>
        <article>
          <span>ROM coverage</span>
          <strong>{summary.rom_cost_coverage_percent}%</strong>
        </article>
        <article>
          <span>Analysis readiness</span>
          <strong>{overview.readiness.status}</strong>
        </article>
      </div>
      <div className="analysisDistributionGrid">
        {Object.entries(summary.distributions).map(([name, items]) => (
          <article key={name}>
            <h3>{name.replace(/_/g, " ")}</h3>
            {items.map((item) => (
              <div key={item.key}>
                <span>{item.key}</span>
                <strong>{item.count}</strong>
              </div>
            ))}
            {!items.length ? <small>No governed source values.</small> : null}
          </article>
        ))}
      </div>
      <section className="analysisReadiness" aria-label="Portfolio Analysis Readiness">
        <header>
          <span>Gate 07F output</span>
          <strong>{overview.readiness.final_output}</strong>
        </header>
        <div>
          <span>
            Scenario Planning · {overview.readiness.can_enter_portfolio_scenario_planning ? "READY" : "BLOCKED"}
          </span>
          <span>Budget branch · {overview.readiness.can_enter_budget_planning ? "READY" : "BLOCKED"}</span>
          <span>Resource branch · {overview.readiness.can_enter_resource_planning ? "READY" : "BLOCKED"}</span>
        </div>
        {overview.readiness.blockers.map((item) => (
          <small key={item}>{item}</small>
        ))}
      </section>
    </section>
  );
}

export default function PortfolioAnalysisWorkspace({
  token,
  portfolioId,
  initialView = "overview",
}: {
  token: string;
  portfolioId?: number;
  initialView?: View;
}) {
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [selectedId, setSelectedId] = useState(portfolioId || 0);
  const [view, setView] = useState<View>(initialView);
  const [filters, setFilters] = useState<AnalysisFilters>({});
  const [overview, setOverview] = useState<PortfolioAnalysisOverview | null>(null);
  const [detail, setDetail] = useState<ProjectAnalysisDetail | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

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

  async function load() {
    if (!selectedId) return;
    setBusy(true);
    try {
      setOverview(await portfolioAnalysisApi.overview(token, selectedId, filters));
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load Portfolio Analysis");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void load();
  }, [selectedId, filters.project_type, filters.strategic_objective, filters.risk_bucket, filters.priority_bucket]);

  async function openDetail(projectId: number) {
    try {
      setDetail(await portfolioAnalysisApi.projectDetail(token, selectedId, projectId));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to open Project analysis detail");
    }
  }

  const projectTypes = useMemo(
    () => Array.from(new Set((overview?.dataset.rows || []).map((item) => item.project_type).filter(Boolean))).sort(),
    [overview?.dataset.rows]
  );
  const objectives = useMemo(
    () =>
      Array.from(
        new Set(
          (overview?.dataset.rows || []).flatMap((item) =>
            item.strategic_objectives.map((objective) => String(objective.code || objective.name || "")).filter(Boolean)
          )
        )
      ).sort(),
    [overview?.dataset.rows]
  );

  return (
    <section aria-label="Portfolio Analysis" className="portfolioAnalysis">
      <CompactModuleHeader
        description="Derived comparison of eligible CAPITAL_OWNER Projects. Gate 07E score and contextual rank remain read-only sources; no selection, Budget, Resource or FID decision is created."
        eyebrow="USER MODE · ENTERPRISE STRATEGY MANAGER · PORTFOLIO MANAGER · GATE 07F"
        metrics={[
          { label: "Projects", value: overview?.summary.eligible_projects || 0 },
          { label: "Analysis", value: overview?.readiness.status || "BLOCKED" },
          { label: "Output", value: overview?.readiness.can_enter_portfolio_scenario_planning ? "READY" : "REWORK" },
        ]}
        title="Portfolio Analysis"
        tone="user"
      />
      <div className="analysisToolbar">
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
        <nav aria-label="Portfolio Analysis views">
          {(["overview", "investor-map", "scorecard"] as View[]).map((item) => (
            <button className={view === item ? "active" : ""} key={item} onClick={() => setView(item)} type="button">
              {item === "overview" ? (
                <BarChart3 size={15} />
              ) : item === "investor-map" ? (
                <CircleDot size={15} />
              ) : (
                <Table2 size={15} />
              )}
              {item.replace("-", " ")}
            </button>
          ))}
        </nav>
        <button aria-label="Reload Portfolio Analysis" disabled={busy} onClick={() => void load()} type="button">
          <RefreshCw size={15} /> Refresh
        </button>
      </div>
      <section aria-label="Analysis filters" className="analysisFilters">
        <Filter size={16} />
        <label>
          Project Type
          <select
            value={filters.project_type || ""}
            onChange={(event) =>
              setFilters((current) => ({ ...current, project_type: event.target.value || undefined }))
            }
          >
            <option value="">All</option>
            {projectTypes.map((item) => (
              <option key={item!}>{item}</option>
            ))}
          </select>
        </label>
        <label>
          Strategic Objective
          <select
            value={filters.strategic_objective || ""}
            onChange={(event) =>
              setFilters((current) => ({ ...current, strategic_objective: event.target.value || undefined }))
            }
          >
            <option value="">All</option>
            {objectives.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </label>
        <label>
          Risk Bucket
          <select
            value={filters.risk_bucket || ""}
            onChange={(event) =>
              setFilters((current) => ({ ...current, risk_bucket: event.target.value || undefined }))
            }
          >
            <option value="">All</option>
            <option>HIGH</option>
            <option>MEDIUM</option>
            <option>LOW</option>
          </select>
        </label>
        <label>
          Priority Bucket
          <select
            value={filters.priority_bucket || ""}
            onChange={(event) =>
              setFilters((current) => ({ ...current, priority_bucket: event.target.value || undefined }))
            }
          >
            <option value="">All</option>
            <option>HIGH</option>
            <option>MEDIUM</option>
            <option>LOW</option>
          </select>
        </label>
        <button onClick={() => setFilters({})} type="button">
          <X size={14} /> Reset
        </button>
      </section>
      {message ? (
        <div className="planningMessage" role="status">
          {message}
        </div>
      ) : null}
      {overview ? (
        view === "overview" ? (
          <OverviewView overview={overview} />
        ) : view === "investor-map" ? (
          <InvestorMapView overview={overview} onSelect={(point) => void openDetail(point.project_workspace_id)} />
        ) : (
          <ScorecardView overview={overview} onSelect={(projectId) => void openDetail(projectId)} />
        )
      ) : (
        <article className="analysisEmpty">
          <strong>{busy ? "Loading Portfolio Analysis…" : "No Portfolio Analysis available"}</strong>
          <span>A published Gate 07F configuration and READY_FOR_PORTFOLIO_ANALYSIS source are required.</span>
        </article>
      )}
      {detail ? (
        <aside aria-label="Project analysis detail" className="analysisDrawer">
          <header>
            <div>
              <span>{detail.row.project_number}</span>
              <h3>{detail.row.project_name}</h3>
            </div>
            <button aria-label="Close Project detail" onClick={() => setDetail(null)} type="button">
              <X size={17} />
            </button>
          </header>
          <dl>
            <div>
              <dt>Portfolio rank</dt>
              <dd>{detail.row.portfolio_rank}</dd>
            </div>
            <div>
              <dt>Evaluation score</dt>
              <dd>{detail.row.portfolio_evaluation_score}</dd>
            </div>
            <div>
              <dt>Strategic alignment</dt>
              <dd>{detail.row.strategic_alignment_score}</dd>
            </div>
            <div>
              <dt>Risk</dt>
              <dd>
                {detail.row.risk_score} · {detail.row.risk_bucket}
              </dd>
            </div>
            <div>
              <dt>ROM Cost</dt>
              <dd>
                {detail.row.rom_cost || "N/A"} {detail.row.currency || ""}
              </dd>
            </div>
            <div>
              <dt>Evaluation version</dt>
              <dd>v{detail.row.evaluation_version}</dd>
            </div>
          </dl>
          <details>
            <summary>Evaluation history</summary>
            <pre>{JSON.stringify(detail.evaluation_history, null, 2)}</pre>
          </details>
          <details>
            <summary>Strategic context</summary>
            <pre>{JSON.stringify(detail.strategic_context, null, 2)}</pre>
          </details>
          <details>
            <summary>Membership</summary>
            <pre>{JSON.stringify(detail.membership, null, 2)}</pre>
          </details>
          <details>
            <summary>Planning Entry</summary>
            <pre>{JSON.stringify(detail.planning_entry, null, 2)}</pre>
          </details>
        </aside>
      ) : null}
    </section>
  );
}
