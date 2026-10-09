import {
  CheckCircle2,
  ClipboardCheck,
  FileClock,
  Flag,
  Gavel,
  History,
  Plus,
  RefreshCw,
  ShieldCheck,
  UsersRound,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { strategicGateApi } from "./api";
import type {
  PortfolioIntakeReadiness,
  StrategicGateDecision,
  StrategicGateDraft,
  StrategicGateOptions,
  StrategicGateOutcome,
  StrategicGatePreview,
} from "./types";
import "./strategicGate.css";

const queues = [
  ["mine", "My Gate Decisions"],
  ["prepare", "Decisions to Prepare"],
  ["submitted", "Submitted"],
  ["review", "In Review"],
  ["decided", "Decided"],
  ["approved", "Approved for Portfolio Intake"],
  ["returned", "Returned"],
  ["rejected", "Rejected"],
  ["deferred", "Deferred"],
] as const;

function messageFrom(error: unknown) {
  if (!(error instanceof ApiError)) return error instanceof Error ? error.message : "Unexpected error";
  try {
    const parsed = JSON.parse(error.message) as { detail?: string | { reason?: string; message?: string } };
    return typeof parsed.detail === "string"
      ? parsed.detail
      : parsed.detail?.message || parsed.detail?.reason || error.message;
  } catch {
    return error.message;
  }
}

function draftFrom(item: StrategicGateDecision): StrategicGateDraft {
  return {
    decision_reason: item.decision_reason,
    decision_comments: item.decision_comments,
    decision_maker_user_id: item.decision_maker_user_id,
    conditions: item.conditions,
    evidence_refs: item.evidence_refs,
    committee: item.committee_snapshot,
  };
}

export default function StrategicGateWorkspace({ token, workspaceId }: { token: string; workspaceId?: number }) {
  const [records, setRecords] = useState<StrategicGateDecision[]>([]);
  const [selected, setSelected] = useState<StrategicGateDecision | null>(null);
  const [options, setOptions] = useState<StrategicGateOptions | null>(null);
  const [preview, setPreview] = useState<StrategicGatePreview | null>(null);
  const [readiness, setReadiness] = useState<PortfolioIntakeReadiness | null>(null);
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([]);
  const [queue, setQueue] = useState("");
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [proposalId, setProposalId] = useState(0);
  const [editing, setEditing] = useState<StrategicGateDraft | null>(null);
  const [decisionReason, setDecisionReason] = useState("");
  const [decisionComments, setDecisionComments] = useState("");
  const [deferredUntil, setDeferredUntil] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (queue) params.set(queue === "prepare" ? "queue" : "queue", queue);
    if (search.trim()) params.set("search", search.trim());
    if (workspaceId) params.set("owning_workspace_id", String(workspaceId));
    return params.toString();
  }, [queue, search, workspaceId]);

  const load = async (preferredId?: number) => {
    try {
      const [nextRecords, nextOptions] = await Promise.all([
        strategicGateApi.list(token, query),
        strategicGateApi.options(token),
      ]);
      setRecords(nextRecords);
      setOptions(nextOptions);
      const next = nextRecords.find((item) => item.id === (preferredId || selected?.id)) || nextRecords[0] || null;
      setSelected(next);
    } catch (error) {
      setMessage(messageFrom(error));
    }
  };

  useEffect(() => {
    const frame = window.setTimeout(() => void load(), 160);
    return () => window.clearTimeout(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, query]);

  useEffect(() => {
    if (!selected) {
      return;
    }
    let active = true;
    Promise.all([strategicGateApi.readiness(token, selected.id), strategicGateApi.history(token, selected.id)])
      .then(([nextReadiness, nextHistory]) => {
        if (!active) return;
        setReadiness(nextReadiness);
        setHistory(nextHistory);
      })
      .catch((error) => active && setMessage(messageFrom(error)));
    return () => {
      active = false;
    };
  }, [selected, token]);

  async function showPreview() {
    if (!proposalId) return;
    setBusy(true);
    try {
      setPreview(await strategicGateApi.preview(token, proposalId));
    } catch (error) {
      setMessage(messageFrom(error));
    } finally {
      setBusy(false);
    }
  }

  async function createDecision() {
    if (!proposalId) return;
    setBusy(true);
    try {
      const created = await strategicGateApi.create(token, proposalId);
      setCreating(false);
      setPreview(null);
      setMessage(`${created.decision_number} created as DRAFT.`);
      await load(created.id);
    } catch (error) {
      setMessage(messageFrom(error));
    } finally {
      setBusy(false);
    }
  }

  async function saveDraft() {
    if (!selected || !editing) return;
    setBusy(true);
    try {
      const updated = await strategicGateApi.update(token, selected, editing);
      setEditing(null);
      setMessage("Decision draft updated.");
      await load(updated.id);
    } catch (error) {
      setMessage(messageFrom(error));
    } finally {
      setBusy(false);
    }
  }

  async function action(name: string, body?: unknown) {
    if (!selected) return;
    setBusy(true);
    try {
      const updated = await strategicGateApi.action(token, selected, name, body);
      setMessage(`${updated.decision_number}: ${updated.state.replace(/_/g, " ")}`);
      await load(updated.id);
    } catch (error) {
      setMessage(messageFrom(error));
    } finally {
      setBusy(false);
    }
  }

  async function decide(outcome: StrategicGateOutcome) {
    if (!selected) return;
    if (!decisionReason.trim()) {
      setMessage("Decision reason is required.");
      return;
    }
    setBusy(true);
    try {
      const updated = await strategicGateApi.decide(
        token,
        selected,
        outcome,
        decisionReason,
        decisionComments,
        selected.conditions,
        deferredUntil
      );
      setDecisionReason("");
      setDecisionComments("");
      setDeferredUntil("");
      setMessage(`${updated.decision_number}: ${outcome} recorded.`);
      await load(updated.id);
    } catch (error) {
      setMessage(messageFrom(error));
    } finally {
      setBusy(false);
    }
  }

  const metrics = {
    active: records.filter((item) => ["DRAFT", "SUBMITTED", "IN_REVIEW"].includes(item.state)).length,
    review: records.filter((item) => item.state === "IN_REVIEW").length,
    approved: records.filter((item) => item.outcome === "APPROVE").length,
  };

  return (
    <section className="strategicGate" aria-label="Strategic Gate Decision">
      <CompactModuleHeader
        eyebrow="Enterprise Strategy Manager"
        title="Strategic Gate Decision"
        description="Register the formal APPROVE, RETURN, REJECT or DEFER outcome for a gate-ready Project Proposal. APPROVE means Portfolio Intake only."
        tone="user"
        metrics={[
          { label: "Visible", value: records.length },
          { label: "Active", value: metrics.active },
          { label: "In review", value: metrics.review },
          { label: "Portfolio intake", value: metrics.approved },
        ]}
        actions={
          <>
            <button className="gateSecondary" onClick={() => void load()} type="button">
              <RefreshCw size={16} /> Refresh
            </button>
            <button className="gatePrimary" onClick={() => setCreating(true)} type="button">
              <Plus size={16} /> New Decision
            </button>
          </>
        }
      />

      <nav className="gateQueues" aria-label="Strategic Gate Decision queues">
        {queues.map(([key, label]) => (
          <button className={queue === key ? "active" : ""} key={key} onClick={() => setQueue(key)} type="button">
            {label}
          </button>
        ))}
      </nav>

      <div className="gateToolbar">
        <input
          aria-label="Search Strategic Gate Decisions"
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search SGD number"
          value={search}
        />
        <span>{options ? `Next preview: ${options.decision_number_preview} (not reserved)` : ""}</span>
      </div>
      {message ? (
        <div className="gateMessage" role="alert">
          {message}
        </div>
      ) : null}

      <div className="gateWorkspaceGrid">
        <section className="gateRegister" aria-label="Strategic Gate Decision register">
          {records.length ? (
            records.map((item) => (
              <button
                className={selected?.id === item.id ? "gateRow selected" : "gateRow"}
                key={item.id}
                onClick={() => setSelected(item)}
                type="button"
              >
                <span className={`gateChip state-${item.state.toLowerCase()}`}>{item.outcome || item.state}</span>
                <strong>
                  {item.decision_number} · {item.project_proposal_number}
                </strong>
                <small>
                  Round {item.gate_round} · {item.owning_workspace_name}
                </small>
              </button>
            ))
          ) : (
            <div className="gateEmpty">
              <FileClock size={28} />
              <strong>No Decisions in this queue</strong>
            </div>
          )}
        </section>

        <article className="gateDetail" aria-label="Strategic Gate Decision detail">
          {selected ? (
            <>
              <header>
                <div>
                  <span>{selected.decision_number}</span>
                  <h3>{selected.project_proposal_name}</h3>
                </div>
                <span className={`gateChip state-${selected.state.toLowerCase()}`}>
                  {selected.outcome || selected.state.replace(/_/g, " ")}
                </span>
              </header>

              <div className="gateFacts">
                <article>
                  <Gavel size={17} />
                  <span>Gate Type</span>
                  <strong>{selected.gate_type}</strong>
                  <small>Round {selected.gate_round}</small>
                </article>
                <article>
                  <Flag size={17} />
                  <span>Proposal</span>
                  <strong>{selected.project_proposal_number}</strong>
                  <small>{selected.proposal_status_at_entry}</small>
                </article>
                <article>
                  <ShieldCheck size={17} />
                  <span>Owning Workspace</span>
                  <strong>{selected.owning_workspace_name}</strong>
                  <small>Target: {selected.target_portfolio_name || "Not assigned"}</small>
                </article>
                <article>
                  <UsersRound size={17} />
                  <span>Authority</span>
                  <strong>{selected.decision_maker_name || "Pending"}</strong>
                  <small>
                    {String(
                      selected.configuration_snapshot.decision_authority
                        ? (selected.configuration_snapshot.decision_authority as Record<string, unknown>).mode
                        : "Single maker"
                    )}
                  </small>
                </article>
              </div>

              <section className="gateReadinessBand">
                <CheckCircle2 size={20} />
                <div>
                  <strong>{selected.proposal_readiness_status}</strong>
                  <span>Entry hash {selected.proposal_readiness_hash.slice(0, 16)}…</span>
                </div>
                <small>Status and readiness remain distinct contracts.</small>
              </section>

              <div className="gateSections">
                <details open>
                  <summary>Overview</summary>
                  <p>{selected.decision_reason || "Decision rationale pending."}</p>
                  <p>{selected.decision_comments}</p>
                </details>
                <details>
                  <summary>Proposal Snapshot</summary>
                  <pre>{JSON.stringify(selected.proposal_snapshot, null, 2)}</pre>
                </details>
                <details>
                  <summary>Source Idea</summary>
                  <pre>{JSON.stringify(selected.source_idea_snapshot, null, 2)}</pre>
                </details>
                <details>
                  <summary>Proposal Evaluation</summary>
                  <p>
                    Score {selected.proposal_score || "N/A"} · revision {selected.proposal_evaluation_revision}
                  </p>
                  <pre>{JSON.stringify(selected.proposal_evaluation_snapshot, null, 2)}</pre>
                </details>
                <details open>
                  <summary>
                    <ClipboardCheck size={15} /> Checklist
                  </summary>
                  <div className="gateChecklist">
                    {selected.decision_checklist_snapshot.map((item) => (
                      <article className={item.status.toLowerCase()} key={item.code}>
                        <strong>
                          {item.status} · {item.label}
                        </strong>
                        <small>{item.evidence}</small>
                      </article>
                    ))}
                  </div>
                </details>
                <details>
                  <summary>Decision Criteria</summary>
                  <div className="gateCriteria">
                    {selected.decision_criteria_snapshot.map((item) => (
                      <span key={String(item.code)}>
                        {String(item.label)} · {String(item.weight)}%
                      </span>
                    ))}
                  </div>
                </details>
                <details>
                  <summary>Authority / Committee / Quorum</summary>
                  <pre>
                    {JSON.stringify(
                      selected.committee_snapshot || selected.configuration_snapshot.decision_authority,
                      null,
                      2
                    )}
                  </pre>
                </details>
                <details>
                  <summary>Conditions and Evidence</summary>
                  <p>
                    {selected.conditions.length} condition(s) · {selected.evidence_refs.length} evidence reference(s)
                  </p>
                </details>
                <details>
                  <summary>
                    <History size={15} /> History
                  </summary>
                  <p>{history.length} immutable audited event(s).</p>
                </details>
              </div>

              {selected.allowed_actions.includes("decide") ? (
                <section className="gateDecisionBox">
                  <h4>Formal Decision</h4>
                  <textarea
                    aria-label="Decision reason"
                    onChange={(event) => setDecisionReason(event.target.value)}
                    placeholder="Required decision reason"
                    value={decisionReason}
                  />
                  <textarea
                    aria-label="Decision comments"
                    onChange={(event) => setDecisionComments(event.target.value)}
                    placeholder="Decision comments"
                    value={decisionComments}
                  />
                  <input
                    aria-label="Deferred until"
                    onChange={(event) => setDeferredUntil(event.target.value)}
                    type="date"
                    value={deferredUntil}
                  />
                  <div>
                    {(["APPROVE", "RETURN", "REJECT", "DEFER"] as StrategicGateOutcome[]).map((outcome) => (
                      <button
                        className={`outcome-${outcome.toLowerCase()}`}
                        disabled={busy}
                        key={outcome}
                        onClick={() => void decide(outcome)}
                        type="button"
                      >
                        {outcome}
                      </button>
                    ))}
                  </div>
                </section>
              ) : null}

              <div className="gateActions">
                {selected.allowed_actions.includes("edit") && (
                  <button onClick={() => setEditing(draftFrom(selected))} type="button">
                    Edit draft
                  </button>
                )}
                {selected.allowed_actions.includes("submit") && (
                  <button disabled={busy} onClick={() => void action("submit")} type="button">
                    Submit
                  </button>
                )}
                {selected.allowed_actions.includes("start_review") && (
                  <button disabled={busy} onClick={() => void action("start-review")} type="button">
                    Start review
                  </button>
                )}
                {selected.allowed_actions.includes("return_to_preparer") && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void action("return-to-preparer", { reason: "Decision package requires additional preparation." })
                    }
                    type="button"
                  >
                    Return to preparer
                  </button>
                )}
                {selected.allowed_actions.includes("void") && (
                  <button className="danger" disabled={busy} onClick={() => void action("void")} type="button">
                    Void
                  </button>
                )}
                {selected.allowed_actions.includes("create_new_round") && (
                  <button disabled={busy} onClick={() => void action("new-round")} type="button">
                    Create new round
                  </button>
                )}
              </div>

              <section
                className={
                  readiness?.status === "READY_FOR_PORTFOLIO_INTAKE" ? "portfolioReadiness ready" : "portfolioReadiness"
                }
              >
                <Flag size={19} />
                <div>
                  <strong>Portfolio Intake Readiness</strong>
                  <span>{readiness?.status || "Not available"}</span>
                </div>
                <small>can_create_portfolio_candidate = false · no Project Workspace is created.</small>
              </section>
            </>
          ) : (
            <div className="gateEmpty">
              <FileClock size={28} />
              <strong>Select a Strategic Gate Decision</strong>
            </div>
          )}
        </article>
      </div>

      {creating && options ? (
        <div className="gateDrawerBackdrop">
          <section className="gateDrawer" aria-label="Create Strategic Gate Decision">
            <header>
              <div>
                <span>PROJECT PROPOSAL → STRATEGIC GATE</span>
                <h3>New Strategic Gate Decision</h3>
              </div>
              <button onClick={() => setCreating(false)} type="button">
                Close
              </button>
            </header>
            <label>
              <span>Gate-ready Project Proposal</span>
              <select
                onChange={(event) => {
                  setProposalId(Number(event.target.value));
                  setPreview(null);
                }}
                value={proposalId || ""}
              >
                <option value="">Select Proposal…</option>
                {options.eligible_proposals.map((item) => (
                  <option disabled={!item.can_create} key={item.id} value={item.id}>
                    {item.proposal_number} · {item.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="gateSecondary"
              disabled={!proposalId || busy}
              onClick={() => void showPreview()}
              type="button"
            >
              Preview Decision
            </button>
            {preview ? (
              <div className="gatePreview">
                <article>
                  <span>Number preview</span>
                  <strong>{preview.decision_number_preview}</strong>
                </article>
                <article>
                  <span>Proposal status</span>
                  <strong>{String(preview.project_proposal.status)}</strong>
                </article>
                <article>
                  <span>Readiness</span>
                  <strong>{String(preview.readiness.status)}</strong>
                </article>
                <article>
                  <span>Authority</span>
                  <strong>{String(preview.authority.mode)}</strong>
                </article>
                <p>
                  {preview.blockers.length
                    ? `Blocked: ${preview.blockers.join(" · ")}`
                    : "Preview only. No Decision number or record has been reserved."}
                </p>
              </div>
            ) : null}
            <footer>
              <button onClick={() => setCreating(false)} type="button">
                Cancel
              </button>
              <button
                className="gatePrimary"
                disabled={!preview || Boolean(preview.blockers.length) || busy}
                onClick={() => void createDecision()}
                type="button"
              >
                Create DRAFT
              </button>
            </footer>
          </section>
        </div>
      ) : null}

      {editing && selected ? (
        <div className="gateDrawerBackdrop">
          <section className="gateDrawer" aria-label="Edit Strategic Gate Decision">
            <header>
              <div>
                <span>{selected.decision_number}</span>
                <h3>Decision Preparation</h3>
              </div>
              <button onClick={() => setEditing(null)} type="button">
                Close
              </button>
            </header>
            <label>
              <span>Decision reason</span>
              <textarea
                onChange={(event) => setEditing({ ...editing, decision_reason: event.target.value })}
                value={editing.decision_reason}
              />
            </label>
            <label>
              <span>Preparation comments</span>
              <textarea
                onChange={(event) => setEditing({ ...editing, decision_comments: event.target.value })}
                value={editing.decision_comments}
              />
            </label>
            <label>
              <span>Decision Maker</span>
              <select
                onChange={(event) =>
                  setEditing({ ...editing, decision_maker_user_id: Number(event.target.value) || null })
                }
                value={editing.decision_maker_user_id || ""}
              >
                <option value="">Select authority…</option>
                {options?.users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.name}
                  </option>
                ))}
              </select>
            </label>
            <footer>
              <button onClick={() => setEditing(null)} type="button">
                Cancel
              </button>
              <button
                className="gatePrimary"
                disabled={busy || !editing.decision_reason.trim()}
                onClick={() => void saveDraft()}
                type="button"
              >
                Save draft
              </button>
            </footer>
          </section>
        </div>
      ) : null}
    </section>
  );
}
