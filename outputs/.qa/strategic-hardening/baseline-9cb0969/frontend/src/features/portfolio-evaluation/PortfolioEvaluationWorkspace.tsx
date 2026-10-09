/* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
import { CheckCircle2, ClipboardCheck, ListOrdered, Play, RefreshCw, RotateCcw, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import "../portfolio-planning/portfolioPlanning.css";
import { portfolioEvaluationApi } from "./api";
import type {
  CriterionRating,
  EvaluationQueueItem,
  PortfolioEvaluation,
  Prioritization,
  PrioritizationReadiness,
} from "./types";
import "./portfolioEvaluation.css";

type View = "evaluation" | "prioritization";

const queues = ["ALL_AUTHORIZED", "TO_EVALUATE", "IN_PROGRESS", "COMPLETED", "BLOCKED"] as const;

function EvaluationEditor({
  evaluation,
  onChanged,
  token,
}: {
  evaluation: PortfolioEvaluation;
  onChanged: (value: PortfolioEvaluation) => void;
  token: string;
}) {
  const criteria = evaluation.matrix_snapshot.criteria || [];
  const scale = evaluation.matrix_snapshot.scoring_scale || { minimum: 1, maximum: 5, step: 1 };
  const [ratings, setRatings] = useState<CriterionRating[]>(evaluation.ratings);
  const [comments, setComments] = useState(evaluation.comments);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    setRatings(evaluation.ratings);
    setComments(evaluation.comments);
  }, [evaluation.id, evaluation.revision_version]);

  function ratingFor(code: string): CriterionRating {
    return (
      ratings.find((item) => item.criterion_code === code) || {
        criterion_code: code,
        rating: scale.minimum,
        evidence: "",
        comment: "",
      }
    );
  }

  function patchRating(code: string, patch: Partial<CriterionRating>) {
    setRatings((current) => {
      const next = current.filter((item) => item.criterion_code !== code);
      return [...next, { ...ratingFor(code), ...patch }];
    });
  }

  async function save() {
    setBusy(true);
    try {
      const result = await portfolioEvaluationApi.update(token, evaluation, ratings, comments);
      onChanged(result);
      setMessage("Evaluation draft saved with a new ETag.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save evaluation");
    } finally {
      setBusy(false);
    }
  }

  async function complete() {
    setBusy(true);
    try {
      const saved = await portfolioEvaluationApi.update(token, evaluation, ratings, comments);
      const result = await portfolioEvaluationApi.complete(token, saved);
      onChanged(result);
      setMessage("Evaluation completed and frozen as an immutable snapshot.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to complete evaluation");
    } finally {
      setBusy(false);
    }
  }

  const editable = evaluation.allowed_actions.includes("edit");
  return (
    <section
      className="evaluationEditor"
      aria-label="Portfolio evaluation form"
      data-testid={`portfolio-evaluation-editor-${evaluation.id}`}
    >
      <header>
        <div>
          <span>
            {evaluation.project_number} · Version {evaluation.evaluation_version}
          </span>
          <h3>{evaluation.project_name}</h3>
        </div>
        <strong className={evaluation.status === "COMPLETED" ? "ready" : "blocked"}>{evaluation.status}</strong>
      </header>
      <div className="evaluationCriteria">
        {criteria.map((criterion) => {
          const value = ratingFor(criterion.code);
          return (
            <article key={criterion.code}>
              <header>
                <strong>{criterion.label}</strong>
                <span>{criterion.weight}%</span>
              </header>
              <label>
                Rating
                <input
                  aria-label={`${criterion.label} rating`}
                  disabled={!editable}
                  max={scale.maximum}
                  min={scale.minimum}
                  onChange={(event) => patchRating(criterion.code, { rating: Number(event.target.value) })}
                  step={scale.step}
                  type="number"
                  value={value.rating}
                />
              </label>
              <label>
                Evidence {criterion.evidence_required ? "· required" : ""}
                <input
                  aria-label={`${criterion.label} evidence`}
                  disabled={!editable}
                  onChange={(event) => patchRating(criterion.code, { evidence: event.target.value })}
                  value={value.evidence}
                />
              </label>
              <label>
                Comment
                <input
                  aria-label={`${criterion.label} comment`}
                  disabled={!editable}
                  onChange={(event) => patchRating(criterion.code, { comment: event.target.value })}
                  value={value.comment}
                />
              </label>
            </article>
          );
        })}
      </div>
      <label className="evaluationComments">
        Evaluation comments
        <textarea
          disabled={!editable}
          onChange={(event) => setComments(event.target.value)}
          rows={3}
          value={comments}
        />
      </label>
      {message ? (
        <div className="planningMessage" role="status">
          {message}
        </div>
      ) : null}
      <div className="planningActions">
        <button disabled={busy || !editable} onClick={() => void save()} type="button">
          <Save size={15} /> Save draft
        </button>
        <button
          className="planningPrimary"
          disabled={busy || !evaluation.allowed_actions.includes("complete")}
          onClick={() => void complete()}
          type="button"
        >
          <CheckCircle2 size={15} /> Complete
        </button>
      </div>
      {evaluation.status === "COMPLETED" ? (
        <div className="evaluationScore">
          <span>Normalized score</span>
          <strong>{evaluation.normalized_score}</strong>
          <small>Matrix {evaluation.matrix_hash.slice(0, 12)}</small>
        </div>
      ) : null}
    </section>
  );
}

export default function PortfolioEvaluationWorkspace({
  token,
  portfolioId,
  projectId,
  view = "evaluation",
}: {
  token: string;
  portfolioId?: number;
  projectId?: number;
  view?: View;
}) {
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [selectedId, setSelectedId] = useState(portfolioId || 0);
  const [queue, setQueue] = useState<(typeof queues)[number]>("ALL_AUTHORIZED");
  const [items, setItems] = useState<EvaluationQueueItem[]>([]);
  const [ranking, setRanking] = useState<Prioritization | null>(null);
  const [readiness, setReadiness] = useState<PrioritizationReadiness | null>(null);
  const [selected, setSelected] = useState<PortfolioEvaluation | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (portfolioId) {
      setSelectedId(portfolioId);
      return;
    }
    void Promise.all([
      portfolioPlanningApi.portfolioOptions(token),
      projectId ? portfolioPlanningApi.memberships(token, projectId) : Promise.resolve([]),
    ])
      .then(([options, memberships]) => {
        setPortfolios(options);
        const activeMembership = memberships.find((item) => item.status === "ACTIVE");
        setSelectedId((current) => current || activeMembership?.portfolio_workspace_id || Number(options[0]?.id || 0));
      })
      .catch(() => setMessage("Unable to load authorized Portfolios."));
  }, [token, portfolioId]);

  async function load() {
    if (!selectedId) return;
    try {
      if (view === "evaluation") {
        const result = await portfolioEvaluationApi.queue(token, selectedId, queue);
        setItems(projectId ? result.filter((item) => item.project_workspace_id === projectId) : result);
      } else {
        const [nextRanking, nextReadiness] = await Promise.all([
          portfolioEvaluationApi.prioritization(token, selectedId),
          portfolioEvaluationApi.readiness(token, selectedId),
        ]);
        setRanking(nextRanking);
        setReadiness(nextReadiness);
      }
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load Gate 07E data");
    }
  }

  useEffect(() => {
    void load();
  }, [selectedId, queue, view, projectId]);

  const queueCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    items.forEach((item) => {
      counts[item.queue] = (counts[item.queue] || 0) + 1;
    });
    return counts;
  }, [items]);

  async function start(item: EvaluationQueueItem) {
    try {
      const result = await portfolioEvaluationApi.start(token, selectedId, item.project_workspace_id);
      setSelected(result);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to start evaluation");
    }
  }

  async function reevaluate(evaluation: PortfolioEvaluation) {
    try {
      const result = await portfolioEvaluationApi.reevaluate(token, evaluation);
      setSelected(result);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to start reevaluation");
    }
  }

  return (
    <section
      className="portfolioEvaluation"
      aria-label={view === "evaluation" ? "Portfolio Evaluation" : "Prioritization Matrix"}
    >
      <CompactModuleHeader
        description={
          view === "evaluation"
            ? "Controlled Project scoring in an active Portfolio membership context. Completed versions remain immutable. No global candidate entity is used."
            : "Derived, deterministic ranking per Portfolio. No global candidate and no manual rank override are used."
        }
        eyebrow="USER MODE · PORTFOLIO MANAGER · GATE 07E"
        metrics={
          view === "evaluation"
            ? [
                { label: "Authorized", value: items.length },
                { label: "In progress", value: queueCounts.IN_PROGRESS || 0 },
                { label: "Completed", value: queueCounts.COMPLETED || 0 },
              ]
            : [
                { label: "Ranked", value: ranking?.items.length || 0 },
                { label: "Coverage", value: `${readiness?.coverage_percent || 0}%` },
                { label: "Analysis", value: readiness?.can_enter_portfolio_analysis ? "READY" : "BLOCKED" },
              ]
        }
        title={view === "evaluation" ? "Portfolio Evaluation" : "Prioritization Matrix"}
        tone="user"
      />
      <div className="planningToolbar">
        <label>
          <span>Portfolio context</span>
          <select
            aria-label="Portfolio context"
            disabled={Boolean(portfolioId)}
            onChange={(event) => setSelectedId(Number(event.target.value))}
            value={selectedId}
          >
            {portfolioId ? <option value={portfolioId}>Active Portfolio</option> : null}
            {portfolios.map((item) => (
              <option key={String(item.id)} value={Number(item.id)}>
                {String(item.name)} · {String(item.record_code)}
              </option>
            ))}
          </select>
        </label>
        <button className="planningSecondary" onClick={() => void load()} type="button">
          <RefreshCw size={15} /> Refresh
        </button>
      </div>
      {message ? (
        <div className="planningMessage" role="status">
          {message}
        </div>
      ) : null}
      {view === "evaluation" ? (
        <>
          <nav className="evaluationQueues" aria-label="Evaluation queues">
            {queues.map((item) => (
              <button
                aria-pressed={queue === item}
                className={queue === item ? "active" : ""}
                key={item}
                onClick={() => setQueue(item)}
                type="button"
              >
                {item.replace(/_/g, " ")}
              </button>
            ))}
          </nav>
          <div className="evaluationWorkspaceGrid">
            <div className="evaluationQueueList">
              {items.map((item) => (
                <article
                  className="planningCard"
                  data-testid={`portfolio-evaluation-project-${item.project_workspace_id}`}
                  key={item.membership_id}
                >
                  <header>
                    <ClipboardCheck size={18} />
                    <div>
                      <span>{item.project_number}</span>
                      <h3>{item.project_name}</h3>
                    </div>
                    <strong className={item.eligible ? "ready" : "blocked"}>{item.queue}</strong>
                  </header>
                  {item.blocking_issues.map((issue) => (
                    <small className="evaluationBlocker" key={issue}>
                      {issue}
                    </small>
                  ))}
                  <div className="planningActions">
                    {!item.latest_evaluation && item.allowed_actions.includes("start") ? (
                      <button className="planningPrimary" onClick={() => void start(item)} type="button">
                        <Play size={14} /> Start
                      </button>
                    ) : null}
                    {item.latest_evaluation ? (
                      <button onClick={() => setSelected(item.latest_evaluation)} type="button">
                        <ClipboardCheck size={14} /> Open v{item.latest_evaluation.evaluation_version}
                      </button>
                    ) : null}
                    {item.latest_evaluation?.allowed_actions.includes("reevaluate") ? (
                      <button onClick={() => void reevaluate(item.latest_evaluation!)} type="button">
                        <RotateCcw size={14} /> Reevaluate
                      </button>
                    ) : null}
                  </div>
                </article>
              ))}
              {!items.length ? (
                <article className="planningEmpty">
                  <ClipboardCheck size={28} />
                  <strong>No authorized evaluations in this queue</strong>
                  <span>Eligibility remains backend-derived from Gate 07D and active membership.</span>
                </article>
              ) : null}
            </div>
            {selected ? (
              <EvaluationEditor
                evaluation={selected}
                onChanged={(value) => {
                  setSelected(value);
                  void load();
                }}
                token={token}
              />
            ) : (
              <article className="planningEmpty">
                <ClipboardCheck size={28} />
                <strong>Select an evaluation</strong>
                <span>Ratings, comments and evidence are recorded per criterion.</span>
              </article>
            )}
          </div>
        </>
      ) : (
        <>
          <section className="prioritizationReadiness">
            <article>
              <span>Eligible</span>
              <strong>{readiness?.eligible_project_count || 0}</strong>
            </article>
            <article>
              <span>Completed</span>
              <strong>{readiness?.completed_evaluation_count || 0}</strong>
            </article>
            <article>
              <span>Coverage</span>
              <strong>{readiness?.coverage_percent || 0}%</strong>
            </article>
            <article>
              <span>Final output</span>
              <strong>{readiness?.final_output || "GATE07E_REWORK_REQUIRED"}</strong>
            </article>
          </section>
          <div className="prioritizationTable" role="table" aria-label="Portfolio prioritization ranking">
            <div className="prioritizationRow header" role="row">
              <span>Rank</span>
              <span>Project</span>
              <span>Score</span>
              <span>Strategic</span>
              <span>Risk</span>
              <span>Proposal</span>
              <span>Objectives</span>
              <span>ROM cost</span>
              <span>Status / date</span>
              <span>Version</span>
            </div>
            {ranking?.items.map((item) => (
              <div
                className="prioritizationRow"
                data-testid={`portfolio-prioritization-row-${item.project_workspace_id}`}
                key={item.evaluation_id}
                role="row"
              >
                <strong>
                  <ListOrdered size={15} /> {item.rank}
                </strong>
                <span>
                  {item.project_number}
                  <small>{item.project_name}</small>
                </span>
                <strong>{item.normalized_score}</strong>
                <span>{item.strategic_alignment_score}</span>
                <span>{item.risk_score}</span>
                <span>{item.proposal_score || "N/A"}</span>
                <span>
                  {item.strategic_objectives.length
                    ? item.strategic_objectives
                        .map((objective) => String(objective.name || objective.code || ""))
                        .filter(Boolean)
                        .join(", ")
                    : "N/A"}
                </span>
                <span>{item.rom_cost || "N/A"}</span>
                <span>
                  {item.evaluation_status}
                  <small>{new Date(item.completed_at).toLocaleDateString()}</small>
                </span>
                <span>v{item.evaluation_version}</span>
              </div>
            ))}
          </div>
          {!ranking?.items.length ? (
            <article className="planningEmpty">
              <ListOrdered size={28} />
              <strong>No completed evaluations to rank</strong>
              <span>Ranking is contextual and excludes inactive memberships.</span>
            </article>
          ) : null}
        </>
      )}
    </section>
  );
}
