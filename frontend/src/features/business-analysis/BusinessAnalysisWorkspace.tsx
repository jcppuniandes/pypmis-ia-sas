import {
  ArrowRight,
  CheckCircle2,
  ClipboardList,
  FileClock,
  GitBranch,
  History,
  Plus,
  RefreshCw,
  RotateCcw,
  Scale,
  Send,
  Target,
  UsersRound,
} from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { businessAnalysisApi } from "./api";
import type {
  BusinessAnalysis,
  BusinessAnalysisContent,
  BusinessAnalysisOption,
  BusinessAnalysisOptions,
  BusinessAnalysisReadiness,
} from "./types";
import "./businessAnalysis.css";

const queues = [
  ["mine", "My Analyses"],
  ["draft", "Draft"],
  ["submitted", "Submitted"],
  ["review", "In Review"],
  ["returned", "Returned"],
  ["ready", "Ready for Proposal"],
  ["completed", "Completed"],
  ["", "All Authorized"],
] as const;

const sections = [
  "Source Idea",
  "Need / Opportunity",
  "Business Drivers",
  "Strategic Alignment",
  "Stakeholders",
  "Current State",
  "Desired Outcomes",
  "Expected Value",
  "Assumptions",
  "Constraints",
  "Business Requirements",
  "Options Evaluation",
  "Recommended Option",
  "Readiness",
  "History",
];

function errorMessage(error: unknown) {
  if (!(error instanceof ApiError)) return error instanceof Error ? error.message : "Unexpected error";
  try {
    const parsed = JSON.parse(error.message) as { detail?: string | { reason?: string; blockers?: string[] } };
    if (typeof parsed.detail === "string") return parsed.detail;
    return [parsed.detail?.reason, ...(parsed.detail?.blockers || [])].filter(Boolean).join(" · ") || error.message;
  } catch {
    return error.message;
  }
}

function recordsToLines(items: Array<Record<string, unknown>>, key: string) {
  return items
    .map((item) => String(item[key] || item.label || item.name || ""))
    .filter(Boolean)
    .join("\n");
}

function linesToRecords(value: string, key: string) {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => ({ [key]: item }));
}

function newOption(options: BusinessAnalysisOptions): BusinessAnalysisOption {
  const id = crypto.randomUUID();
  return {
    id,
    name: "New option",
    option_type: options.option_types[0]?.code || "OTHER",
    description: "Describe the alternative.",
    scope_concept: "",
    expected_benefits: "",
    rough_cost_range: null,
    rough_timeline: null,
    major_risks: [],
    major_dependencies: [],
    feasibility_notes: "",
    strategic_fit: "",
    evaluation: options.evaluation_criteria.map((criterion) => ({
      criterion_code: criterion.code,
      rating: 3,
      weight: criterion.weight,
      comment: "",
    })),
  };
}

function statusLabel(value: string) {
  return value.replace(/_/g, " ");
}

export default function BusinessAnalysisWorkspace({ token, workspaceId }: { token: string; workspaceId?: number }) {
  const [records, setRecords] = useState<BusinessAnalysis[]>([]);
  const [options, setOptions] = useState<BusinessAnalysisOptions | null>(null);
  const [selected, setSelected] = useState<BusinessAnalysis | null>(null);
  const [readiness, setReadiness] = useState<BusinessAnalysisReadiness | null>(null);
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([]);
  const [queue, setQueue] = useState("mine");
  const [search, setSearch] = useState("");
  const [sourceIdeaId, setSourceIdeaId] = useState(0);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<BusinessAnalysisContent | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (queue) params.set("queue", queue);
    if (search.trim()) params.set("search", search.trim());
    if (workspaceId) params.set("owning_workspace_id", String(workspaceId));
    params.set("limit", "50");
    return params.toString();
  }, [queue, search, workspaceId]);

  async function load(preferredId?: number, cursor?: string) {
    setMessage("");
    try {
      const pageQuery = new URLSearchParams(query);
      if (cursor) pageQuery.set("cursor", cursor);
      const [page, available] = await Promise.all([
        businessAnalysisApi.listPage(token, pageQuery.toString()),
        businessAnalysisApi.options(token),
      ]);
      const items = page.items;
      setRecords((current) =>
        cursor ? [...current, ...items.filter((item) => !current.some((existing) => existing.id === item.id))] : items
      );
      setNextCursor(page.nextCursor);
      setOptions(available);
      setSourceIdeaId((current) => current || available.eligible_ideas.find((idea) => idea.can_start)?.id || 0);
      setSelected((current) => {
        if (cursor && current) return current;
        return items.find((item) => item.id === (preferredId || current?.id)) || items[0] || null;
      });
    } catch (error) {
      setMessage(errorMessage(error));
    }
  }

  async function loadMore() {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      await load(undefined, nextCursor);
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    const frame = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, token]);

  useEffect(() => {
    if (!selected) {
      const frame = window.setTimeout(() => {
        setReadiness(null);
        setHistory([]);
      }, 0);
      return () => window.clearTimeout(frame);
    }
    let active = true;
    Promise.all([businessAnalysisApi.readiness(token, selected.id), businessAnalysisApi.history(token, selected.id)])
      .then(([nextReadiness, nextHistory]) => {
        if (!active) return;
        setReadiness(nextReadiness);
        setHistory(nextHistory);
      })
      .catch((error) => active && setMessage(errorMessage(error)));
    return () => {
      active = false;
    };
  }, [selected, token]);

  async function createAnalysis() {
    if (!sourceIdeaId) return;
    setBusy(true);
    try {
      const created = await businessAnalysisApi.create(token, sourceIdeaId);
      setCreating(false);
      await load(created.id);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!selected || !editing) return;
    setBusy(true);
    try {
      const updated = await businessAnalysisApi.update(token, selected, editing);
      setEditing(null);
      await load(updated.id);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function action(name: string, body?: unknown) {
    if (!selected) return;
    setBusy(true);
    try {
      const updated =
        name === "new-revision"
          ? await businessAnalysisApi.newRevision(token, selected)
          : await businessAnalysisApi.action(token, selected, name, body);
      await load(updated.id);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  function updateOption(index: number, patch: Partial<BusinessAnalysisOption>) {
    if (!editing) return;
    setEditing({
      ...editing,
      options: editing.options.map((option, optionIndex) => (optionIndex === index ? { ...option, ...patch } : option)),
    });
  }

  const metrics = {
    draft: records.filter((item) => ["DRAFT", "RETURNED"].includes(item.status)).length,
    review: records.filter((item) => ["SUBMITTED", "IN_REVIEW"].includes(item.status)).length,
    ready: records.filter((item) => item.status === "COMPLETED").length,
  };

  return (
    <section className="baWorkspace" aria-label="Business Analysis and Options">
      <CompactModuleHeader
        eyebrow="USER MODE / Enterprise Strategy Manager / Idea & Demand"
        title="Business Analysis & Options"
        description="Define the business need, compare alternatives and complete a governed recommendation before Project Proposal."
        tone="user"
        metrics={[
          { label: "Visible", value: records.length },
          { label: "Draft", value: metrics.draft },
          { label: "In review", value: metrics.review },
          { label: "Ready", value: metrics.ready },
        ]}
        actions={
          <>
            <button className="baSecondary" onClick={() => void load()} type="button">
              <RefreshCw size={16} /> Refresh
            </button>
            <button className="baPrimary" onClick={() => setCreating(true)} type="button">
              <Plus size={16} /> New Business Analysis
            </button>
          </>
        }
      />

      <nav className="baQueues" aria-label="Business Analysis queues">
        {queues.map(([key, label]) => (
          <button className={queue === key ? "active" : ""} key={label} onClick={() => setQueue(key)} type="button">
            {label}
          </button>
        ))}
      </nav>

      <div className="baToolbar">
        <input
          aria-label="Search Business Analysis"
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search number or title"
          value={search}
        />
        <span>{options ? `Next preview ${options.number_preview} · preview does not reserve a number` : ""}</span>
      </div>
      {message ? (
        <div className="baMessage" role="alert">
          {message}
        </div>
      ) : null}

      <div className="baGrid">
        <section className="baRegister" aria-label="Business Analysis register">
          {records.length ? (
            records.map((analysis) => (
              <button
                className={selected?.id === analysis.id ? "baRow selected" : "baRow"}
                key={analysis.id}
                onClick={() => setSelected(analysis)}
                type="button"
              >
                <span className={`baState state-${analysis.status.toLowerCase()}`}>{statusLabel(analysis.status)}</span>
                <strong>
                  {analysis.analysis_number} · {analysis.source_idea_title}
                </strong>
                <small>
                  {analysis.owning_workspace_name} · {analysis.source_idea_number}
                </small>
              </button>
            ))
          ) : (
            <div className="baEmpty">
              <FileClock size={28} />
              <strong>No analyses in this queue</strong>
            </div>
          )}
          {nextCursor ? (
            <button className="baLoadMore" disabled={loadingMore} onClick={() => void loadMore()} type="button">
              {loadingMore ? "Loading…" : "Load more analyses"}
            </button>
          ) : null}
        </section>

        <article className="baDetail" aria-label="Business Analysis detail">
          {selected ? (
            <>
              <header className="baDetailHeader">
                <div>
                  <span>{selected.analysis_number}</span>
                  <h3>{selected.title}</h3>
                  <small>
                    Source {selected.source_idea_number} · configuration r{selected.configuration_revision}
                  </small>
                </div>
                <span className={`baState state-${selected.status.toLowerCase()}`}>{statusLabel(selected.status)}</span>
              </header>

              <nav className="baSections" aria-label="Business Analysis record sections">
                {sections.map((section) => (
                  <a href={`#ba-${section.toLowerCase().replace(/[^a-z]+/g, "-")}`} key={section}>
                    {section}
                  </a>
                ))}
              </nav>

              <div className="baFacts">
                <article id="ba-source-idea">
                  <GitBranch size={17} />
                  <span>Source Idea</span>
                  <strong>{selected.source_idea_number}</strong>
                  <small>{selected.source_idea_title}</small>
                </article>
                <article id="ba-need-opportunity">
                  <Target size={17} />
                  <span>Need / Opportunity</span>
                  <strong>{selected.content.analysis_type}</strong>
                  <small>{selected.content.statement}</small>
                </article>
                <article id="ba-business-drivers">
                  <ClipboardList size={17} />
                  <span>Business Drivers</span>
                  <strong>{selected.content.business_drivers.length}</strong>
                  <small>{recordsToLines(selected.content.business_drivers, "label") || "Pending"}</small>
                </article>
                <article id="ba-strategic-alignment">
                  <Target size={17} />
                  <span>Strategic Alignment</span>
                  <strong>{selected.content.strategic_alignment.length}</strong>
                  <small>Existing Strategic Objectives referenced</small>
                </article>
                <article id="ba-stakeholders">
                  <UsersRound size={17} />
                  <span>Stakeholders</span>
                  <strong>{selected.content.stakeholders.length}</strong>
                  <small>{recordsToLines(selected.content.stakeholders, "name") || "Pending"}</small>
                </article>
                <article id="ba-current-state">
                  <FileClock size={17} />
                  <span>Current State</span>
                  <strong>{String(selected.content.current_state.summary || "Pending")}</strong>
                </article>
                <article id="ba-desired-outcomes">
                  <CheckCircle2 size={17} />
                  <span>Desired Outcomes</span>
                  <strong>{String(selected.content.desired_outcomes.business_outcomes || "Pending")}</strong>
                </article>
                <article id="ba-expected-value">
                  <Scale size={17} />
                  <span>Expected Value</span>
                  <strong>{selected.content.expected_value.length} dimension(s)</strong>
                  <small>Preliminary value only; no full financial model</small>
                </article>
                <article id="ba-assumptions">
                  <ClipboardList size={17} />
                  <span>Assumptions</span>
                  <strong>{selected.content.assumptions.length}</strong>
                </article>
                <article id="ba-constraints">
                  <ClipboardList size={17} />
                  <span>Constraints</span>
                  <strong>{selected.content.constraints.length}</strong>
                </article>
                <article id="ba-business-requirements">
                  <ClipboardList size={17} />
                  <span>Business Requirements</span>
                  <strong>{selected.content.business_requirements.length}</strong>
                  <small>High-level appraisal needs</small>
                </article>
              </div>

              <section className="baOptions" id="ba-options-evaluation">
                <header>
                  <div>
                    <span>Options Evaluation</span>
                    <h4>Alternative solutions</h4>
                  </div>
                  <strong>{selected.content.options.length} option(s)</strong>
                </header>
                <div>
                  {selected.content.options.map((option) => (
                    <article
                      className={selected.recommended_option_id === option.id ? "recommended" : ""}
                      key={option.id}
                    >
                      <span>{option.option_type}</span>
                      <h4>{option.name}</h4>
                      <p>{option.description}</p>
                      <small>
                        {option.evaluation.length} criterion rating(s)
                        {selected.recommended_option_id === option.id ? " · RECOMMENDED" : ""}
                      </small>
                    </article>
                  ))}
                </div>
              </section>

              <section className="baRecommendation" id="ba-recommended-option">
                <ArrowRight size={19} />
                <div>
                  <span>Recommended Option</span>
                  <strong>
                    {selected.content.options.find((item) => item.id === selected.recommended_option_id)?.name ||
                      "Pending selection"}
                  </strong>
                  <p>{selected.content.recommendation_rationale || "Recommendation rationale pending."}</p>
                </div>
              </section>

              <section className="baReadiness" id="ba-readiness" aria-label="Business Analysis readiness">
                <div>
                  <span>Readiness</span>
                  <strong>{readiness?.status || "Checking"}</strong>
                  <small>{readiness?.output || "Project Proposal remains blocked"}</small>
                </div>
                <div>
                  {readiness?.blockers.map((blocker) => (
                    <span key={blocker}>{statusLabel(blocker)}</span>
                  ))}
                </div>
              </section>

              <div className="baActions">
                {selected.allowed_actions.includes("edit") ? (
                  <button disabled={busy} onClick={() => setEditing(structuredClone(selected.content))} type="button">
                    Edit analysis
                  </button>
                ) : null}
                {selected.allowed_actions.includes("submit") ? (
                  <button className="baPrimary" disabled={busy} onClick={() => void action("submit")} type="button">
                    <Send size={15} /> Submit
                  </button>
                ) : null}
                {selected.allowed_actions.includes("void") ? (
                  <button
                    disabled={busy}
                    onClick={() => {
                      const reason = window.prompt("Reason for voiding this Business Analysis");
                      if (reason?.trim()) void action("void", { reason: reason.trim() });
                    }}
                    type="button"
                  >
                    Void analysis
                  </button>
                ) : null}
                {selected.allowed_actions.includes("start_review") ? (
                  <button disabled={busy} onClick={() => void action("start-review")} type="button">
                    Start review
                  </button>
                ) : null}
                {selected.allowed_actions.includes("return") ? (
                  <button
                    disabled={busy}
                    onClick={() => void action("return", { reason: "Additional analysis evidence is required" })}
                    type="button"
                  >
                    <RotateCcw size={15} /> Return
                  </button>
                ) : null}
                {selected.allowed_actions.includes("complete") ? (
                  <button className="baPrimary" disabled={busy} onClick={() => void action("complete")} type="button">
                    <CheckCircle2 size={15} /> Complete
                  </button>
                ) : null}
                {selected.allowed_actions.includes("new_revision") ? (
                  <button disabled={busy} onClick={() => void action("new-revision")} type="button">
                    New material revision
                  </button>
                ) : null}
                {readiness?.ready ? (
                  <a className="baLinkButton" href="/app/strategy/project-proposal">
                    Open Project Proposal <ArrowRight size={15} />
                  </a>
                ) : null}
              </div>

              <section className="baHistory" id="ba-history">
                <header>
                  <History size={17} />
                  <strong>History</strong>
                </header>
                {history.map((item, index) => (
                  <p key={`${String(item.event_type)}-${index}`}>
                    <strong>{statusLabel(String(item.event_type || "event"))}</strong>
                    <span>{new Date(String(item.occurred_at)).toLocaleString()}</span>
                  </p>
                ))}
              </section>
            </>
          ) : (
            <div className="baEmpty">
              <GitBranch size={30} />
              <strong>Select a Business Analysis</strong>
            </div>
          )}
        </article>
      </div>

      {creating && options ? (
        <div className="baDrawerBackdrop" role="presentation">
          <section className="baDrawer" aria-label="Start Business Analysis">
            <header>
              <div>
                <span>Idea & Demand</span>
                <h3>Start Business Analysis</h3>
              </div>
              <button onClick={() => setCreating(false)} type="button">
                Close
              </button>
            </header>
            <label>
              <span>Eligible accepted Idea</span>
              <select value={sourceIdeaId || ""} onChange={(event) => setSourceIdeaId(Number(event.target.value))}>
                <option value="">Select…</option>
                {options.eligible_ideas.map((idea) => (
                  <option disabled={!idea.can_start} key={idea.id} value={idea.id}>
                    {idea.idea_number} · {idea.title}
                    {idea.can_start ? "" : ` · ${idea.blockers.join(", ")}`}
                  </option>
                ))}
              </select>
            </label>
            <p>
              The analysis will snapshot the accepted Idea, its evaluation and the effective published configuration.
            </p>
            <footer>
              <button onClick={() => setCreating(false)} type="button">
                Cancel
              </button>
              <button
                className="baPrimary"
                disabled={busy || !sourceIdeaId}
                onClick={() => void createAnalysis()}
                type="button"
              >
                Create draft
              </button>
            </footer>
          </section>
        </div>
      ) : null}

      {editing && selected && options ? (
        <div className="baDrawerBackdrop">
          <form className="baDrawer baEditor" onSubmit={save} aria-label="Edit Business Analysis">
            <header>
              <div>
                <span>{selected.analysis_number} · DRAFT</span>
                <h3>Business Analysis sections</h3>
              </div>
              <button onClick={() => setEditing(null)} type="button">
                Close
              </button>
            </header>
            <div className="baEditorScroll">
              <fieldset>
                <legend>Need Problem or Opportunity</legend>
                <label>
                  <span>Analysis type</span>
                  <select
                    value={editing.analysis_type}
                    onChange={(event) => setEditing({ ...editing, analysis_type: event.target.value })}
                  >
                    {options.analysis_types.map((item) => (
                      <option key={item.code} value={item.code}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Statement</span>
                  <textarea
                    required
                    minLength={3}
                    value={editing.statement}
                    onChange={(event) => setEditing({ ...editing, statement: event.target.value })}
                  />
                </label>
                <label>
                  <span>Background</span>
                  <textarea
                    value={editing.background}
                    onChange={(event) => setEditing({ ...editing, background: event.target.value })}
                  />
                </label>
                <label>
                  <span>Business context</span>
                  <textarea
                    value={editing.business_context}
                    onChange={(event) => setEditing({ ...editing, business_context: event.target.value })}
                  />
                </label>
                <div className="baFormGrid">
                  <label>
                    <span>Urgency and timing</span>
                    <textarea
                      value={editing.urgency_timing}
                      onChange={(event) => setEditing({ ...editing, urgency_timing: event.target.value })}
                    />
                  </label>
                  <label>
                    <span>Consequences of no action</span>
                    <textarea
                      value={editing.consequences_no_action}
                      onChange={(event) => setEditing({ ...editing, consequences_no_action: event.target.value })}
                    />
                  </label>
                </div>
              </fieldset>
              <fieldset>
                <legend>Business Drivers</legend>
                <div className="baChecks">
                  {options.business_drivers.map((driver) => {
                    const checked = editing.business_drivers.some((item) => item.code === driver.code);
                    return (
                      <label key={driver.code}>
                        <input
                          checked={checked}
                          onChange={(event) =>
                            setEditing({
                              ...editing,
                              business_drivers: event.target.checked
                                ? [...editing.business_drivers, driver]
                                : editing.business_drivers.filter((item) => item.code !== driver.code),
                            })
                          }
                          type="checkbox"
                        />
                        {driver.label}
                      </label>
                    );
                  })}
                </div>
              </fieldset>
              <fieldset>
                <legend>Stakeholders and alignment</legend>
                <label>
                  <span>Stakeholders one per line</span>
                  <textarea
                    value={recordsToLines(editing.stakeholders, "name")}
                    onChange={(event) =>
                      setEditing({ ...editing, stakeholders: linesToRecords(event.target.value, "name") })
                    }
                  />
                </label>
                <label>
                  <span>Strategic alignment contribution</span>
                  <textarea
                    value={recordsToLines(editing.strategic_alignment, "contribution")}
                    onChange={(event) =>
                      setEditing({
                        ...editing,
                        strategic_alignment: linesToRecords(event.target.value, "contribution"),
                      })
                    }
                  />
                </label>
              </fieldset>
              <fieldset>
                <legend>Current State and Desired Outcomes</legend>
                <label>
                  <span>Current situation</span>
                  <textarea
                    value={String(editing.current_state.summary || "")}
                    onChange={(event) =>
                      setEditing({
                        ...editing,
                        current_state: { ...editing.current_state, summary: event.target.value },
                      })
                    }
                  />
                </label>
                <label>
                  <span>Business outcomes</span>
                  <textarea
                    value={String(editing.desired_outcomes.business_outcomes || "")}
                    onChange={(event) =>
                      setEditing({
                        ...editing,
                        desired_outcomes: { ...editing.desired_outcomes, business_outcomes: event.target.value },
                      })
                    }
                  />
                </label>
                <label>
                  <span>Expected value one dimension per line</span>
                  <textarea
                    value={recordsToLines(editing.expected_value, "narrative")}
                    onChange={(event) =>
                      setEditing({ ...editing, expected_value: linesToRecords(event.target.value, "narrative") })
                    }
                  />
                </label>
              </fieldset>
              <fieldset>
                <legend>Assumptions Constraints and Business Requirements</legend>
                <div className="baFormGrid">
                  <label>
                    <span>Assumptions</span>
                    <textarea
                      value={recordsToLines(editing.assumptions, "statement")}
                      onChange={(event) =>
                        setEditing({ ...editing, assumptions: linesToRecords(event.target.value, "statement") })
                      }
                    />
                  </label>
                  <label>
                    <span>Constraints</span>
                    <textarea
                      value={recordsToLines(editing.constraints, "statement")}
                      onChange={(event) =>
                        setEditing({ ...editing, constraints: linesToRecords(event.target.value, "statement") })
                      }
                    />
                  </label>
                </div>
                <label>
                  <span>High-level business requirements</span>
                  <textarea
                    value={recordsToLines(editing.business_requirements, "statement")}
                    onChange={(event) =>
                      setEditing({ ...editing, business_requirements: linesToRecords(event.target.value, "statement") })
                    }
                  />
                </label>
              </fieldset>
              <fieldset>
                <legend>Options and Evaluation</legend>
                <button
                  className="baSecondary"
                  onClick={() => setEditing({ ...editing, options: [...editing.options, newOption(options)] })}
                  type="button"
                >
                  <Plus size={14} /> Add option
                </button>
                {editing.options.map((option, index) => (
                  <article className="baOptionEditor" key={option.id}>
                    <div className="baFormGrid">
                      <label>
                        <span>Option name</span>
                        <input
                          value={option.name}
                          onChange={(event) => updateOption(index, { name: event.target.value })}
                        />
                      </label>
                      <label>
                        <span>Option type</span>
                        <select
                          value={option.option_type}
                          onChange={(event) => updateOption(index, { option_type: event.target.value })}
                        >
                          {options.option_types.map((item) => (
                            <option key={item.code} value={item.code}>
                              {item.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <label>
                      <span>Description</span>
                      <textarea
                        value={option.description}
                        onChange={(event) => updateOption(index, { description: event.target.value })}
                      />
                    </label>
                    <div className="baFormGrid">
                      <label>
                        <span>Scope concept</span>
                        <textarea
                          value={option.scope_concept}
                          onChange={(event) => updateOption(index, { scope_concept: event.target.value })}
                        />
                      </label>
                      <label>
                        <span>Expected benefits</span>
                        <textarea
                          value={option.expected_benefits}
                          onChange={(event) => updateOption(index, { expected_benefits: event.target.value })}
                        />
                      </label>
                    </div>
                    <div className="baRatings">
                      {options.evaluation_criteria.map((criterion) => {
                        const current = option.evaluation.find((item) => item.criterion_code === criterion.code);
                        return (
                          <label key={criterion.code}>
                            <span>
                              {criterion.label} · {criterion.weight}%
                            </span>
                            <select
                              value={Number(current?.rating || 3)}
                              onChange={(event) =>
                                updateOption(index, {
                                  evaluation: option.evaluation.map((item) =>
                                    item.criterion_code === criterion.code
                                      ? { ...item, rating: Number(event.target.value) }
                                      : item
                                  ),
                                })
                              }
                            >
                              {[1, 2, 3, 4, 5].map((rating) => (
                                <option key={rating} value={rating}>
                                  {rating}
                                </option>
                              ))}
                            </select>
                          </label>
                        );
                      })}
                    </div>
                    <button
                      className="baDanger"
                      onClick={() =>
                        setEditing({
                          ...editing,
                          options: editing.options.filter((_, optionIndex) => optionIndex !== index),
                          recommended_option_id:
                            editing.recommended_option_id === option.id ? null : editing.recommended_option_id,
                        })
                      }
                      type="button"
                    >
                      Remove option
                    </button>
                  </article>
                ))}
              </fieldset>
              <fieldset>
                <legend>Recommendation and Conditions</legend>
                <label>
                  <span>Recommended option</span>
                  <select
                    value={editing.recommended_option_id || ""}
                    onChange={(event) => setEditing({ ...editing, recommended_option_id: event.target.value || null })}
                  >
                    <option value="">Select…</option>
                    {editing.options.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Recommendation rationale</span>
                  <textarea
                    value={editing.recommendation_rationale}
                    onChange={(event) => setEditing({ ...editing, recommendation_rationale: event.target.value })}
                  />
                </label>
                <div className="baFormGrid">
                  <label>
                    <span>Key trade-offs</span>
                    <textarea
                      value={recordsToLines(editing.key_trade_offs, "statement")}
                      onChange={(event) =>
                        setEditing({ ...editing, key_trade_offs: linesToRecords(event.target.value, "statement") })
                      }
                    />
                  </label>
                  <label>
                    <span>Conditions</span>
                    <textarea
                      value={recordsToLines(editing.conditions, "statement")}
                      onChange={(event) =>
                        setEditing({ ...editing, conditions: linesToRecords(event.target.value, "statement") })
                      }
                    />
                  </label>
                </div>
                <label>
                  <span>Unresolved concerns</span>
                  <textarea
                    value={recordsToLines(editing.unresolved_concerns, "statement")}
                    onChange={(event) =>
                      setEditing({
                        ...editing,
                        unresolved_concerns: linesToRecords(event.target.value, "statement").map((item) => ({
                          ...item,
                          blocking: true,
                          accepted: false,
                        })),
                      })
                    }
                  />
                </label>
              </fieldset>
            </div>
            <footer>
              <button onClick={() => setEditing(null)} type="button">
                Cancel
              </button>
              <button className="baPrimary" disabled={busy} type="submit">
                Save governed draft
              </button>
            </footer>
          </form>
        </div>
      ) : null}
    </section>
  );
}
