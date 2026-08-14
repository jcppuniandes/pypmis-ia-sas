import {
  ArrowRightCircle,
  BadgeDollarSign,
  CheckCircle2,
  ClipboardCheck,
  FileClock,
  Flag,
  Link2,
  Plus,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Target,
  UserRound,
} from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import ProposalGateDecisionsPanel from "../strategic-gate/ProposalGateDecisionsPanel";
import { projectProposalApi } from "./api";
import type { GateReadiness, ProjectProposal, ProposalDraft, ProposalOptions, ProposalPreview } from "./types";
import "./projectProposal.css";

const queues = [
  ["mine", "My Project Proposals"],
  ["", "All Authorized"],
  ["DRAFT", "Draft"],
  ["review", "To Review"],
  ["assigned", "Assigned to Me"],
  ["evaluation", "Under Evaluation"],
  ["gate", "Ready for Strategic Gate"],
  ["returned", "Returned"],
  ["cancelled", "Cancelled"],
] as const;

function errorMessage(error: unknown) {
  if (!(error instanceof ApiError)) return error instanceof Error ? error.message : "Unexpected error";
  try {
    const parsed = JSON.parse(error.message) as { detail?: string | { message?: string; reason?: string } };
    if (typeof parsed.detail === "string") return parsed.detail;
    return parsed.detail?.message || parsed.detail?.reason || error.message;
  } catch {
    return error.message;
  }
}

function draftFromProposal(proposal: ProjectProposal): ProposalDraft {
  return {
    name: proposal.name,
    business_need: proposal.business_need,
    business_justification: proposal.business_justification,
    project_objectives: proposal.project_objectives,
    preliminary_scope: proposal.preliminary_scope,
    out_of_scope: proposal.out_of_scope,
    expected_benefits: proposal.expected_benefits,
    benefit_owner_user_id: proposal.benefit_owner_user_id,
    rom_cost: proposal.rom_cost,
    currency_code: proposal.currency_code,
    preliminary_duration_days: proposal.preliminary_duration_days,
    target_start_date: proposal.target_start_date,
    target_finish_date: proposal.target_finish_date,
    key_risks: proposal.key_risks,
    assumptions: proposal.assumptions,
    constraints: proposal.constraints,
    strategic_objective_codes: proposal.strategic_objective_codes,
    target_portfolio_workspace_id: proposal.target_portfolio_workspace_id,
    sponsor_user_id: proposal.sponsor_user_id,
    proposal_owner_user_id: proposal.proposal_owner_user_id,
    attachment_refs: proposal.attachment_refs,
  };
}

function listText(items: Array<Record<string, unknown>>, key: string) {
  return items
    .map((item) => String(item[key] || item.label || ""))
    .filter(Boolean)
    .join("\n");
}

export default function ProjectProposalWorkspace({ token, workspaceId }: { token: string; workspaceId?: number }) {
  const [records, setRecords] = useState<ProjectProposal[]>([]);
  const [options, setOptions] = useState<ProposalOptions | null>(null);
  const [selected, setSelected] = useState<ProjectProposal | null>(null);
  const [queue, setQueue] = useState(workspaceId ? "" : "mine");
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [sourceIdeaId, setSourceIdeaId] = useState(0);
  const [preview, setPreview] = useState<ProposalPreview | null>(null);
  const [editing, setEditing] = useState<ProposalDraft | null>(null);
  const [readiness, setReadiness] = useState<GateReadiness | null>(null);
  const [history, setHistory] = useState<Array<Record<string, unknown>>>([]);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (workspaceId) params.set("owning_workspace_id", String(workspaceId));
    if (["DRAFT"].includes(queue)) params.set("status", queue);
    else if (queue) params.set("queue", queue);
    if (search.trim()) params.set("search", search.trim());
    return params.toString();
  }, [queue, search, workspaceId]);

  async function load(preferredId?: number) {
    setMessage("");
    try {
      const [items, available] = await Promise.all([
        projectProposalApi.list(token, query),
        projectProposalApi.options(token),
      ]);
      setRecords(items);
      setOptions(available);
      setSourceIdeaId((current) => current || available.eligible_ideas.find((idea) => idea.can_create)?.id || 0);
      setSelected((current) => items.find((item) => item.id === (preferredId || current?.id)) || items[0] || null);
    } catch (error) {
      setMessage(errorMessage(error));
    }
  }

  useEffect(() => {
    const frame = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, token]);

  useEffect(() => {
    if (!selected) {
      return;
    }
    let active = true;
    Promise.all([projectProposalApi.readiness(token, selected.id), projectProposalApi.history(token, selected.id)])
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

  async function showPreview() {
    if (!sourceIdeaId) return;
    setBusy(true);
    try {
      setPreview(await projectProposalApi.preview(token, sourceIdeaId));
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function createProposal() {
    if (!sourceIdeaId || preview?.blockers.length) return;
    setBusy(true);
    try {
      const created = await projectProposalApi.create(token, sourceIdeaId);
      setCreating(false);
      setPreview(null);
      await load(created.id);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function saveProposal(event: FormEvent) {
    event.preventDefault();
    if (!selected || !editing) return;
    setBusy(true);
    try {
      const updated = await projectProposalApi.update(token, selected, editing);
      setEditing(null);
      await load(updated.id);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function action(path: string, body?: unknown) {
    if (!selected) return;
    setBusy(true);
    try {
      const updated = await projectProposalApi.action(token, selected, path, body);
      await load(updated.id);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function completeEvaluation() {
    if (!selected) return;
    setBusy(true);
    try {
      const sourcePreview = await projectProposalApi.preview(token, selected.source_idea_id);
      const updated = await projectProposalApi.action(token, selected, "complete-evaluation", {
        ratings: sourcePreview.evaluation_matrix.criteria.map((criterion) => ({
          criterion_code: criterion.code,
          rating: 4,
          comment: "Validated in controlled Proposal evaluation",
        })),
        comments: "Project Proposal evaluation completed.",
      });
      await load(updated.id);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  const metrics = {
    open: records.filter(
      (item) =>
        ![
          "CANCELLED",
          "ARCHIVED",
          "READY_FOR_STRATEGIC_GATE",
          "STRATEGIC_GATE_APPROVED",
          "STRATEGIC_GATE_REJECTED",
        ].includes(item.status)
    ).length,
    review: records.filter((item) => ["SUBMITTED", "UNDER_REVIEW"].includes(item.status)).length,
    ready: records.filter((item) => item.status === "READY_FOR_STRATEGIC_GATE").length,
  };

  return (
    <section className="proposalLifecycle" aria-label="Project Proposal">
      <CompactModuleHeader
        eyebrow="Enterprise Strategy Manager / Idea & Demand Manager"
        title="Project Proposal"
        description="Develop an accepted Idea into a governed strategic business case without creating a Project Workspace."
        tone="user"
        metrics={[
          { label: "Visible", value: records.length },
          { label: "Open", value: metrics.open },
          { label: "To review", value: metrics.review },
          { label: "Gate ready", value: metrics.ready },
        ]}
        actions={
          <>
            <button className="proposalSecondary" onClick={() => void load()} type="button">
              <RefreshCw size={16} /> Refresh
            </button>
            <button className="proposalPrimary" onClick={() => setCreating(true)} type="button">
              <Plus size={16} /> New Proposal
            </button>
          </>
        }
      />

      <nav className="proposalQueues" aria-label="Project Proposal queues">
        {queues.map(([key, label]) => (
          <button className={queue === key ? "active" : ""} key={label} onClick={() => setQueue(key)} type="button">
            {label}
          </button>
        ))}
      </nav>

      <div className="proposalToolbar">
        <input
          aria-label="Search Project Proposals"
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search number or name"
          value={search}
        />
        <span>{options?.number_preview ? `Next preview: ${options.number_preview} (not reserved)` : ""}</span>
      </div>
      {message ? (
        <div className="proposalMessage" role="alert">
          {message}
        </div>
      ) : null}

      <div className="proposalWorkspaceGrid">
        <section className="proposalRegister" aria-label="Project Proposal register">
          {records.length ? (
            records.map((proposal) => (
              <button
                className={selected?.id === proposal.id ? "proposalRow selected" : "proposalRow"}
                key={proposal.id}
                onClick={() => setSelected(proposal)}
                type="button"
              >
                <span className={`proposalState state-${proposal.status.toLowerCase()}`}>
                  {proposal.status.replace(/_/g, " ")}
                </span>
                <strong>
                  {proposal.proposal_number} · {proposal.name}
                </strong>
                <small>
                  {proposal.owning_workspace_name} · Source {proposal.source_idea_number}
                </small>
              </button>
            ))
          ) : (
            <div className="proposalEmpty">
              <FileClock size={28} />
              <strong>No Project Proposals in this queue</strong>
            </div>
          )}
        </section>

        <article className="proposalDetail" aria-label="Project Proposal detail">
          {selected ? (
            <>
              <header>
                <div>
                  <span>{selected.proposal_number}</span>
                  <h3>{selected.name}</h3>
                </div>
                <span className={`proposalState state-${selected.status.toLowerCase()}`}>
                  {selected.status.replace(/_/g, " ")}
                </span>
              </header>

              <div className="proposalFacts">
                <article>
                  <Link2 size={17} />
                  <span>Source Idea</span>
                  <strong>{selected.source_idea_number}</strong>
                  <small>{selected.source_idea_title}</small>
                </article>
                <article>
                  <UserRound size={17} />
                  <span>Proposal Owner</span>
                  <strong>{selected.proposal_owner_name}</strong>
                  <small>Sponsor: {selected.sponsor_name}</small>
                </article>
                <article>
                  <Target size={17} />
                  <span>Strategic context</span>
                  <strong>{selected.owning_workspace_name}</strong>
                  <small>{selected.strategic_objective_codes.join(", ")}</small>
                </article>
                <article>
                  <BadgeDollarSign size={17} />
                  <span>ROM Cost</span>
                  <strong>{selected.rom_cost ? `${selected.currency_code} ${selected.rom_cost}` : "Pending"}</strong>
                  <small>
                    {selected.preliminary_duration_days
                      ? `${selected.preliminary_duration_days} days`
                      : "Duration pending"}
                  </small>
                </article>
              </div>

              <section className="proposalSource">
                <div>
                  <strong>Source Idea · read only</strong>
                  <span>
                    Accepted evaluation #{selected.accepted_idea_evaluation_id} · Origin score{" "}
                    {selected.origin_idea_score || "N/A"}
                  </span>
                </div>
                <button type="button">View Source Idea</button>
              </section>

              <div className="proposalSections">
                <section>
                  <h4>Business Case</h4>
                  <strong>Business need</strong>
                  <p>{selected.business_need}</p>
                  <strong>Business justification</strong>
                  <p>{selected.business_justification}</p>
                </section>
                <section>
                  <h4>Scope</h4>
                  <strong>Preliminary scope</strong>
                  <p>{selected.preliminary_scope}</p>
                  <strong>Out of scope</strong>
                  <p>{selected.out_of_scope || "Not defined"}</p>
                </section>
                <section>
                  <h4>Benefits</h4>
                  <p>{selected.expected_benefits}</p>
                </section>
                <section>
                  <h4>ROM Cost / Dates</h4>
                  <p>
                    {selected.rom_cost ? `${selected.currency_code} ${selected.rom_cost}` : "ROM pending"} ·{" "}
                    {selected.target_start_date || "Start pending"} → {selected.target_finish_date || "Finish pending"}
                  </p>
                </section>
                <section>
                  <h4>Risks</h4>
                  <p>{listText(selected.key_risks, "risk") || "No risks documented"}</p>
                </section>
                <section>
                  <h4>Assumptions / Constraints</h4>
                  <p>{listText(selected.assumptions, "assumption") || "No assumptions documented"}</p>
                  <p>{listText(selected.constraints, "constraint") || "No constraints documented"}</p>
                </section>
              </div>

              <section className="proposalReview">
                <h4>
                  <ClipboardCheck size={17} /> Review Checklist
                </h4>
                <div>
                  {selected.review.checks?.length ? (
                    selected.review.checks.map((item) => (
                      <article className={item.status.toLowerCase()} key={item.code}>
                        <span>{item.status === "PASS" ? <CheckCircle2 size={15} /> : <RotateCcw size={15} />}</span>
                        <strong>{item.label}</strong>
                        <small>{item.evidence}</small>
                      </article>
                    ))
                  ) : (
                    <p>Review has not started.</p>
                  )}
                </div>
              </section>

              <section className="proposalEvaluation">
                <h4>
                  <ShieldCheck size={17} /> Proposal Evaluation
                </h4>
                {selected.evaluations.length ? (
                  selected.evaluations.map((evaluation) => (
                    <article key={evaluation.id}>
                      <span>Version {evaluation.evaluation_version}</span>
                      <strong>
                        {evaluation.total_score} · {evaluation.recommendation}
                      </strong>
                      <small>Matrix revision {evaluation.matrix_revision}</small>
                    </article>
                  ))
                ) : (
                  <p>No Proposal evaluation has been completed.</p>
                )}
              </section>

              <section
                className={readiness?.can_enter_strategic_gate ? "proposalReadiness ready" : "proposalReadiness"}
              >
                <Flag size={19} />
                <div>
                  <strong>Gate Readiness</strong>
                  <span>{readiness?.status || "Loading readiness…"}</span>
                </div>
                <small>
                  {readiness?.blockers.length
                    ? readiness.blockers.join(" · ")
                    : "Eligible for the next controlled strategic gate; this is not approval."}
                </small>
              </section>

              <ProposalGateDecisionsPanel proposal={selected} token={token} />

              <div className="proposalActions">
                {selected.allowed_actions.includes("edit") && (
                  <button disabled={busy} onClick={() => setEditing(draftFromProposal(selected))} type="button">
                    Edit business case
                  </button>
                )}
                {selected.allowed_actions.includes("submit") && (
                  <button disabled={busy} onClick={() => void action("submit")} type="button">
                    <ArrowRightCircle size={15} /> Submit
                  </button>
                )}
                {selected.allowed_actions.includes("start_review") && (
                  <button disabled={busy} onClick={() => void action("start-review")} type="button">
                    Start review
                  </button>
                )}
                {selected.allowed_actions.includes("start_evaluation") && (
                  <button disabled={busy} onClick={() => void action("start-evaluation")} type="button">
                    Start evaluation
                  </button>
                )}
                {selected.allowed_actions.includes("complete_evaluation") && (
                  <button disabled={busy} onClick={() => void completeEvaluation()} type="button">
                    Complete evaluation
                  </button>
                )}
                {selected.allowed_actions.includes("mark_gate_ready") && (
                  <button className="gate" disabled={busy} onClick={() => void action("mark-gate-ready")} type="button">
                    <Flag size={15} /> Mark gate ready
                  </button>
                )}
                {selected.allowed_actions.includes("return") && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void action("return", { reason: "Additional business case information is required" })
                    }
                    type="button"
                  >
                    Return
                  </button>
                )}
                {selected.allowed_actions.includes("cancel") && (
                  <button className="danger" disabled={busy} onClick={() => void action("cancel")} type="button">
                    Cancel
                  </button>
                )}
              </div>

              <details className="proposalTrace">
                <summary>Attachments and History</summary>
                <p>
                  {selected.attachment_refs.length} attachment reference(s) · {history.length} audited event(s)
                </p>
              </details>
            </>
          ) : (
            <div className="proposalEmpty">
              <FileClock size={28} />
              <strong>Select a Project Proposal</strong>
            </div>
          )}
        </article>
      </div>

      {creating && options ? (
        <div className="proposalDrawerBackdrop">
          <section className="proposalDrawer" aria-label="Create Project Proposal">
            <header>
              <div>
                <span>ACCEPTED IDEA → PROJECT PROPOSAL</span>
                <h3>New Project Proposal</h3>
              </div>
              <button
                onClick={() => {
                  setCreating(false);
                  setPreview(null);
                }}
                type="button"
              >
                Close
              </button>
            </header>
            <label>
              <span>Source Idea</span>
              <select
                value={sourceIdeaId || ""}
                onChange={(event) => {
                  setSourceIdeaId(Number(event.target.value));
                  setPreview(null);
                }}
              >
                <option value="">Select accepted Idea…</option>
                {options.eligible_ideas.map((idea) => (
                  <option disabled={!idea.can_create} key={idea.id} value={idea.id}>
                    {idea.idea_number} · {idea.title}
                    {idea.can_create ? "" : " · BLOCKED"}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="proposalSecondary"
              disabled={!sourceIdeaId || busy}
              onClick={() => void showPreview()}
              type="button"
            >
              Preview mapping
            </button>
            {preview ? (
              <div className="proposalPreview">
                <div>
                  <span>Number preview</span>
                  <strong>{preview.proposal_number_preview}</strong>
                </div>
                <div>
                  <span>Owning Workspace</span>
                  <strong>{String(preview.owning_workspace.name)}</strong>
                </div>
                <div>
                  <span>Mapping revision</span>
                  <strong>{String(preview.mapping.revision)}</strong>
                </div>
                <div>
                  <span>Accepted score</span>
                  <strong>{String(preview.accepted_evaluation.score)}</strong>
                </div>
                <p>
                  <strong>Mapped name:</strong> {String(preview.mapped_fields.name)}
                </p>
                {preview.blockers.length ? (
                  <p className="blocked">Blocked: {preview.blockers.join(" · ")}</p>
                ) : (
                  <p className="readyText">Preview only; no number or record has been reserved.</p>
                )}
              </div>
            ) : null}
            <footer>
              <button
                onClick={() => {
                  setCreating(false);
                  setPreview(null);
                }}
                type="button"
              >
                Cancel
              </button>
              <button
                className="proposalPrimary"
                disabled={!preview || Boolean(preview.blockers.length) || busy}
                onClick={() => void createProposal()}
                type="button"
              >
                Create DRAFT
              </button>
            </footer>
          </section>
        </div>
      ) : null}

      {editing && selected && options ? (
        <div className="proposalDrawerBackdrop">
          <form
            className="proposalDrawer proposalEditDrawer"
            onSubmit={saveProposal}
            aria-label="Edit Project Proposal"
          >
            <header>
              <div>
                <span>{selected.proposal_number}</span>
                <h3>Business Case & Scope</h3>
              </div>
              <button onClick={() => setEditing(null)} type="button">
                Close
              </button>
            </header>
            <label>
              <span>Name</span>
              <input
                required
                minLength={3}
                value={editing.name}
                onChange={(event) => setEditing({ ...editing, name: event.target.value })}
              />
            </label>
            <label>
              <span>Business need</span>
              <textarea
                required
                value={editing.business_need}
                onChange={(event) => setEditing({ ...editing, business_need: event.target.value })}
              />
            </label>
            <label>
              <span>Business justification</span>
              <textarea
                required
                value={editing.business_justification}
                onChange={(event) => setEditing({ ...editing, business_justification: event.target.value })}
              />
            </label>
            <label>
              <span>Preliminary scope</span>
              <textarea
                required
                value={editing.preliminary_scope}
                onChange={(event) => setEditing({ ...editing, preliminary_scope: event.target.value })}
              />
            </label>
            <label>
              <span>Out of scope</span>
              <textarea
                value={editing.out_of_scope}
                onChange={(event) => setEditing({ ...editing, out_of_scope: event.target.value })}
              />
            </label>
            <label>
              <span>Expected benefits</span>
              <textarea
                required
                value={editing.expected_benefits}
                onChange={(event) => setEditing({ ...editing, expected_benefits: event.target.value })}
              />
            </label>
            <div className="proposalFormGrid">
              <label>
                <span>ROM cost</span>
                <input
                  min="0"
                  type="number"
                  value={editing.rom_cost || ""}
                  onChange={(event) => setEditing({ ...editing, rom_cost: event.target.value || null })}
                />
              </label>
              <label>
                <span>Currency</span>
                <input
                  value={editing.currency_code}
                  onChange={(event) => setEditing({ ...editing, currency_code: event.target.value })}
                />
              </label>
              <label>
                <span>Duration days</span>
                <input
                  min="1"
                  type="number"
                  value={editing.preliminary_duration_days || ""}
                  onChange={(event) =>
                    setEditing({
                      ...editing,
                      preliminary_duration_days: event.target.value ? Number(event.target.value) : null,
                    })
                  }
                />
              </label>
              <label>
                <span>Target Portfolio</span>
                <select
                  value={editing.target_portfolio_workspace_id || ""}
                  onChange={(event) =>
                    setEditing({
                      ...editing,
                      target_portfolio_workspace_id: event.target.value ? Number(event.target.value) : null,
                    })
                  }
                >
                  <option value="">None</option>
                  {options.target_portfolios.map((item) => (
                    <option key={String(item.id)} value={Number(item.id)}>
                      {String(item.name)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="proposalFormGrid">
              <label>
                <span>Sponsor</span>
                <select
                  value={editing.sponsor_user_id}
                  onChange={(event) => setEditing({ ...editing, sponsor_user_id: Number(event.target.value) })}
                >
                  {options.users.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Proposal Owner</span>
                <select
                  value={editing.proposal_owner_user_id}
                  onChange={(event) => setEditing({ ...editing, proposal_owner_user_id: Number(event.target.value) })}
                >
                  {options.users.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              <span>Key risks (one per line)</span>
              <textarea
                value={listText(editing.key_risks, "risk")}
                onChange={(event) =>
                  setEditing({
                    ...editing,
                    key_risks: event.target.value
                      .split("\n")
                      .filter(Boolean)
                      .map((risk) => ({ risk, response: "To define" })),
                  })
                }
              />
            </label>
            <label>
              <span>Assumptions (one per line)</span>
              <textarea
                value={listText(editing.assumptions, "assumption")}
                onChange={(event) =>
                  setEditing({
                    ...editing,
                    assumptions: event.target.value
                      .split("\n")
                      .filter(Boolean)
                      .map((assumption) => ({ assumption })),
                  })
                }
              />
            </label>
            <label>
              <span>Constraints (one per line)</span>
              <textarea
                value={listText(editing.constraints, "constraint")}
                onChange={(event) =>
                  setEditing({
                    ...editing,
                    constraints: event.target.value
                      .split("\n")
                      .filter(Boolean)
                      .map((constraint) => ({ constraint })),
                  })
                }
              />
            </label>
            <fieldset>
              <legend>Strategic Objectives</legend>
              {options.strategic_objectives.map((objective) => (
                <label className="proposalCheck" key={objective.code}>
                  <input
                    checked={editing.strategic_objective_codes.includes(objective.code)}
                    onChange={(event) =>
                      setEditing({
                        ...editing,
                        strategic_objective_codes: event.target.checked
                          ? [...editing.strategic_objective_codes, objective.code]
                          : editing.strategic_objective_codes.filter((code) => code !== objective.code),
                      })
                    }
                    type="checkbox"
                  />
                  {objective.label}
                </label>
              ))}
            </fieldset>
            <footer>
              <button onClick={() => setEditing(null)} type="button">
                Cancel
              </button>
              <button className="proposalPrimary" disabled={busy} type="submit">
                Save DRAFT
              </button>
            </footer>
          </form>
        </div>
      ) : null}
    </section>
  );
}
