/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { GitCompareArrows, RefreshCw, Send, ShieldCheck, Split, Workflow } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import "../portfolio-planning/portfolioPlanning.css";
import { portfolioConvergenceApi } from "./api";
import type { ConvergenceComparison, ConvergenceOverview, ScenarioConvergence } from "./types";
import "./portfolioConvergence.css";

type View = "overview" | "alternatives" | "comparison" | "recommendation" | "history";

const shortHash = (value: unknown) => String(value || "—").slice(0, 12);

export default function PortfolioConvergenceWorkspace({ token, portfolioId }: { token: string; portfolioId?: number }) {
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [selectedId, setSelectedId] = useState(portfolioId || 0);
  const [overview, setOverview] = useState<ConvergenceOverview | null>(null);
  const [convergenceId, setConvergenceId] = useState(0);
  const [view, setView] = useState<View>("overview");
  const [name, setName] = useState("Executive scenario convergence");
  const [alternativeName, setAlternativeName] = useState("Aligned portfolio alternative");
  const [budgetId, setBudgetId] = useState(0);
  const [resourceId, setResourceId] = useState(0);
  const [compareIds, setCompareIds] = useState<number[]>([]);
  const [comparison, setComparison] = useState<ConvergenceComparison | null>(null);
  const [recommendedAlternativeId, setRecommendedAlternativeId] = useState(0);
  const [reason, setReason] = useState("");
  const [risks, setRisks] = useState("");
  const [summary, setSummary] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (portfolioId) {
      setSelectedId(portfolioId);
      return;
    }
    void portfolioPlanningApi.portfolioOptions(token).then((items) => {
      setPortfolios(items);
      setSelectedId((current) => current || Number(items[0]?.id || 0));
    });
  }, [portfolioId, token]);

  async function load(preferred?: ScenarioConvergence) {
    if (!selectedId) return;
    try {
      const result = await portfolioConvergenceApi.overview(token, selectedId);
      setOverview(result);
      const activeId = preferred?.id || convergenceId || result.convergences[0]?.id || 0;
      setConvergenceId(activeId);
      const active = preferred || result.convergences.find((item) => item.id === activeId);
      setRecommendedAlternativeId((current) => current || active?.alternatives[0]?.id || 0);
      setBudgetId((current) => current || Number(result.candidate_budget_scenarios[0]?.id || 0));
      setResourceId((current) => current || Number(result.candidate_resource_scenarios[0]?.id || 0));
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load Scenario Convergence");
    }
  }

  useEffect(() => {
    void load();
  }, [selectedId]);

  const convergence = useMemo(
    () => overview?.convergences.find((item) => item.id === convergenceId) || null,
    [overview, convergenceId]
  );

  async function create() {
    try {
      const result = await portfolioConvergenceApi.create(token, selectedId, name);
      setConvergenceId(result.id);
      setView("alternatives");
      await load(result);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create convergence");
    }
  }

  async function addAlternative() {
    if (!convergence) return;
    try {
      const result = await portfolioConvergenceApi.addAlternative(
        token,
        convergence,
        alternativeName,
        overview?.required_branches.budget ? budgetId : null,
        overview?.required_branches.resource ? resourceId : null
      );
      setCompareIds(result.alternatives.map((item) => item.id).slice(0, 2));
      setRecommendedAlternativeId(result.alternatives[0]?.id || 0);
      await load(result);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to add converged alternative");
    }
  }

  async function compare() {
    if (!convergence || compareIds.length < 2) return;
    try {
      setComparison(await portfolioConvergenceApi.compare(token, convergence.id, compareIds));
      setView("comparison");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to compare alternatives");
    }
  }

  async function lifecycle(action: "submit" | "return" | "refresh") {
    if (!convergence) return;
    try {
      if (action === "refresh") {
        const preview = await portfolioConvergenceApi.refreshPreview(token, convergence.id);
        setMessage(`Refresh preview generated; persisted=${String(preview.persisted)}.`);
        return;
      }
      const result =
        action === "submit"
          ? await portfolioConvergenceApi.submit(token, convergence)
          : await portfolioConvergenceApi.returnToDraft(token, convergence);
      await load(result);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} convergence`);
    }
  }

  async function recommend() {
    if (!convergence) return;
    try {
      const result = await portfolioConvergenceApi.recommend(
        token,
        convergence,
        recommendedAlternativeId,
        reason,
        risks,
        summary
      );
      await load(result);
      setMessage("Formal Portfolio recommendation recorded. This is not investment approval or FID.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to record recommendation");
    }
  }

  const readiness = overview?.readiness;
  return (
    <section aria-label="Portfolio Scenario Convergence" className="portfolioConvergence">
      <CompactModuleHeader
        description="Converges governed Gate 07G budget scenarios and Gate 07H resource scenarios into auditable decision-support alternatives. It produces a Portfolio recommendation, never investment approval or FID."
        eyebrow="USER MODE · ENTERPRISE STRATEGY MANAGER · PORTFOLIO MANAGER · GATE 07I"
        metrics={[
          { label: "Sources", value: overview?.source_compatibility.compatible ? "ALIGNED" : "REWORK" },
          { label: "Alternatives", value: readiness?.alternative_count || 0 },
          { label: "Readiness", value: readiness?.portfolio_recommendation_ready ? "READY" : "REWORK" },
        ]}
        title="Portfolio Scenario Convergence & Recommendation"
      />

      <div className="convergenceToolbar">
        <nav aria-label="Scenario convergence views">
          {(["overview", "alternatives", "comparison", "recommendation", "history"] as View[]).map((item) => (
            <button className={view === item ? "active" : ""} key={item} onClick={() => setView(item)} type="button">
              {item}
            </button>
          ))}
        </nav>
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
        <label>
          Convergence revision
          <select value={convergenceId} onChange={(event) => setConvergenceId(Number(event.target.value))}>
            <option value={0}>New convergence</option>
            {overview?.convergences.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · r{item.convergence_revision}
              </option>
            ))}
          </select>
        </label>
      </div>

      {message ? (
        <div className="planningMessage" role="status">
          {message}
        </div>
      ) : null}

      {view === "overview" ? (
        <div className="convergenceOverview">
          <section className="convergenceReadiness">
            <span>Final controlled output</span>
            <h3>{readiness?.final_output || "GATE07I_REWORK_REQUIRED"}</h3>
            <div className="convergenceChips">
              <b className={readiness?.source_current ? "ready" : "stale"}>
                Sources {readiness?.source_current ? "current" : "stale"}
              </b>
              <b>Investment gate preparation: {readiness?.can_enter_investment_gate_preparation ? "READY" : "NO"}</b>
              <b className="blocked">can_enter_fid = false</b>
            </div>
            {readiness?.blockers.map((item) => (
              <p className="convergenceBlocker" key={item}>
                {item}
              </p>
            ))}
          </section>
          <div className="sourceBranches">
            <article>
              <Split size={20} />
              <span>Gate 07G · Budget branch</span>
              <strong>{overview?.required_branches.budget ? "REQUIRED" : "OPTIONAL"}</strong>
              <small>{overview?.candidate_budget_scenarios.length || 0} ready frozen scenario(s)</small>
              <code>{shortHash(overview?.budget_contract?.budget_planning_hash)}</code>
            </article>
            <article>
              <Workflow size={20} />
              <span>Gate 07H · Resource branch</span>
              <strong>{overview?.required_branches.resource ? "REQUIRED" : "OPTIONAL"}</strong>
              <small>{overview?.candidate_resource_scenarios.length || 0} ready frozen scenario(s)</small>
              <code>{shortHash(overview?.resource_contract?.resource_planning_hash)}</code>
            </article>
          </div>
          {!convergence ? (
            <section className="convergenceCreate">
              <label>
                Convergence name
                <input value={name} onChange={(event) => setName(event.target.value)} />
              </label>
              <button disabled={!selectedId || name.trim().length < 3} onClick={() => void create()} type="button">
                <GitCompareArrows size={15} /> Create governed convergence
              </button>
            </section>
          ) : null}
          <div className="convergenceBoundaries">
            {overview?.boundaries.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
        </div>
      ) : null}

      {view === "alternatives" ? (
        <section className="convergenceSurface">
          <header>
            <div>
              <span>Governed pairings</span>
              <h3>Converged alternatives</h3>
            </div>
            <button
              disabled={!convergence || convergence.status !== "DRAFT"}
              onClick={() => void lifecycle("refresh")}
              type="button"
            >
              <RefreshCw size={14} /> Source refresh preview
            </button>
          </header>
          {convergence?.status === "DRAFT" ? (
            <div className="alternativeForm">
              <label>
                Name
                <input value={alternativeName} onChange={(event) => setAlternativeName(event.target.value)} />
              </label>
              {overview?.required_branches.budget ? (
                <label>
                  Budget scenario
                  <select value={budgetId} onChange={(event) => setBudgetId(Number(event.target.value))}>
                    {overview.candidate_budget_scenarios.map((item) => (
                      <option key={Number(item.id)} value={Number(item.id)}>
                        {String(item.scenario_name || item.id)}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              {overview?.required_branches.resource ? (
                <label>
                  Resource scenario
                  <select value={resourceId} onChange={(event) => setResourceId(Number(event.target.value))}>
                    {overview.candidate_resource_scenarios.map((item) => (
                      <option key={Number(item.id)} value={Number(item.id)}>
                        {String(item.scenario_name || item.id)}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <button onClick={() => void addAlternative()} type="button">
                Add alternative
              </button>
            </div>
          ) : null}
          <div className="alternativeCards">
            {convergence?.alternatives.map((item) => (
              <article className={item.feasibility_status.toLowerCase()} key={item.id}>
                <label>
                  <input
                    checked={compareIds.includes(item.id)}
                    onChange={(event) =>
                      setCompareIds((current) =>
                        event.target.checked ? [...current, item.id].slice(-5) : current.filter((id) => id !== item.id)
                      )
                    }
                    type="checkbox"
                  />{" "}
                  Compare
                </label>
                <span>{item.alternative_name}</span>
                <strong>{item.feasibility_status}</strong>
                <small>
                  {item.alignment_status} · budget {item.budget_feasibility} · resource {item.resource_feasibility}
                </small>
                {item.blockers.map((blocker) => (
                  <em key={blocker}>{blocker}</em>
                ))}
              </article>
            ))}
          </div>
          <div className="convergenceActions">
            <button disabled={compareIds.length < 2} onClick={() => void compare()} type="button">
              <GitCompareArrows size={14} /> Compare 2–5
            </button>
            <button
              disabled={!convergence || convergence.status !== "DRAFT" || !convergence.alternatives.length}
              onClick={() => void lifecycle("submit")}
              type="button"
            >
              <Send size={14} /> Submit for review
            </button>
            <button
              disabled={!convergence || convergence.status !== "IN_REVIEW"}
              onClick={() => void lifecycle("return")}
              type="button"
            >
              Return to DRAFT
            </button>
          </div>
        </section>
      ) : null}

      {view === "comparison" ? (
        <section className="convergenceSurface">
          <header>
            <div>
              <span>Decision support</span>
              <h3>Alternative comparison</h3>
            </div>
          </header>
          {comparison ? (
            <>
              <div className="comparisonMatrix">
                {comparison.feasibility_matrix.map((row) => (
                  <article key={String(row.alternative_id)}>
                    <strong>{String(row.alternative)}</strong>
                    <span>{String(row.alignment)}</span>
                    <b>{String(row.overall)}</b>
                    <small>
                      Budget {String(row.budget)} · Resource {String(row.resource)}
                    </small>
                  </article>
                ))}
              </div>
              <details>
                <summary>Pairwise deltas and project matrix</summary>
                <pre>
                  {JSON.stringify(
                    { pairwise_delta: comparison.pairwise_delta, project_matrix: comparison.project_matrix },
                    null,
                    2
                  )}
                </pre>
              </details>
            </>
          ) : (
            <p>Select 2–5 alternatives from the Alternatives view.</p>
          )}
        </section>
      ) : null}

      {view === "recommendation" ? (
        <section className="convergenceSurface recommendationPanel">
          <header>
            <div>
              <span>Formal governed output</span>
              <h3>Portfolio recommendation</h3>
            </div>
            <ShieldCheck size={25} />
          </header>
          {convergence?.status === "RECOMMENDED" ? (
            <div className="recommendationEvidence">
              <strong>RECOMMENDED · alternative #{convergence.recommended_alternative_id}</strong>
              <p>{convergence.recommendation_reason}</p>
              <small>{convergence.recommendation_hash}</small>
              <b>Not investment approval · can_enter_fid=false</b>
            </div>
          ) : (
            <div className="recommendationForm">
              <label>
                Recommended alternative
                <select
                  value={recommendedAlternativeId}
                  onChange={(event) => setRecommendedAlternativeId(Number(event.target.value))}
                >
                  {convergence?.alternatives.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.alternative_name} · {item.feasibility_status}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Recommendation reason
                <textarea value={reason} onChange={(event) => setReason(event.target.value)} />
              </label>
              <label>
                Risks acknowledged
                <textarea value={risks} onChange={(event) => setRisks(event.target.value)} />
              </label>
              <label>
                Decision-support summary
                <textarea value={summary} onChange={(event) => setSummary(event.target.value)} />
              </label>
              <button
                disabled={
                  convergence?.status !== "IN_REVIEW" || reason.length < 10 || risks.length < 3 || summary.length < 10
                }
                onClick={() => void recommend()}
                type="button"
              >
                <ShieldCheck size={15} /> Record formal recommendation
              </button>
            </div>
          )}
        </section>
      ) : null}

      {view === "history" ? (
        <section className="convergenceSurface">
          <header>
            <div>
              <span>Immutable revisions</span>
              <h3>Recommendation history</h3>
            </div>
          </header>
          <div className="historyList">
            {overview?.convergences.map((item) => (
              <button
                className={item.id === convergenceId ? "active" : ""}
                key={item.id}
                onClick={() => setConvergenceId(item.id)}
                type="button"
              >
                <strong>
                  r{item.convergence_revision} · {item.name}
                </strong>
                <span>
                  {item.status} · source {shortHash(item.convergence_source_hash)}
                </span>
                <small>{item.recommended_at || "No recommendation recorded"}</small>
              </button>
            ))}
          </div>
        </section>
      ) : null}
    </section>
  );
}
