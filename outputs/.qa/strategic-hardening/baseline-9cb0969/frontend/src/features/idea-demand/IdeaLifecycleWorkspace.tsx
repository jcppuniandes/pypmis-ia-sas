import { CheckCircle2, ClipboardCheck, Lightbulb, Plus, RefreshCw, Route, Scale, UserRound } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { projectProposalApi } from "../project-proposal/api";
import type { ProjectProposal, ProposalPreview } from "../project-proposal/types";
import { ideaDemandApi } from "./api";
import type { Idea, IdeaDraft, IdeaOptions } from "./types";
import "./ideaDemand.css";

const emptyDraft: IdeaDraft = {
  title: "",
  description: "",
  idea_type: "",
  category: "",
  expected_benefit: "",
  estimated_value: "",
  currency_code: "COP",
  owning_workspace_id: 0,
  target_portfolio_workspace_id: null,
  strategic_objective_codes: [],
  attachment_refs: [],
};

const queues = [
  ["mine", "My Ideas"],
  ["", "All Authorized"],
  ["screen", "To Screen"],
  ["assigned", "Assigned to Me"],
  ["evaluate", "To Evaluate"],
  ["decision", "Awaiting Decision"],
  ["ACCEPTED", "Accepted"],
  ["REJECTED", "Rejected"],
] as const;

function errorMessage(error: unknown) {
  if (!(error instanceof ApiError)) return error instanceof Error ? error.message : "Unexpected error";
  try {
    const parsed = JSON.parse(error.message) as { detail?: string | { message?: string } };
    return typeof parsed.detail === "string" ? parsed.detail : parsed.detail?.message || error.message;
  } catch {
    return error.message;
  }
}

export default function IdeaLifecycleWorkspace({ token, workspaceId }: { token: string; workspaceId?: number }) {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [options, setOptions] = useState<IdeaOptions | null>(null);
  const [queue, setQueue] = useState(workspaceId ? "" : "mine");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Idea | null>(null);
  const [draft, setDraft] = useState<IdeaDraft>({ ...emptyDraft, owning_workspace_id: workspaceId || 0 });
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [relatedProposals, setRelatedProposals] = useState<ProjectProposal[]>([]);
  const [proposalPreview, setProposalPreview] = useState<ProposalPreview | null>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (workspaceId) params.set("owning_workspace_id", String(workspaceId));
    if (queue === "ACCEPTED" || queue === "REJECTED") params.set("state", queue);
    else if (queue) params.set("queue", queue);
    if (search.trim()) params.set("search", search.trim());
    return params.toString();
  }, [queue, search, workspaceId]);

  async function load() {
    setMessage("");
    try {
      const [records, available] = await Promise.all([
        ideaDemandApi.list(token, query),
        ideaDemandApi.options(token, workspaceId),
      ]);
      setIdeas(records);
      setOptions(available);
      if (!draft.owning_workspace_id && available.owning_workspaces.length) {
        const initial = Number(available.owning_workspaces[0].id);
        setDraft((current) => ({
          ...current,
          owning_workspace_id: initial,
          idea_type: current.idea_type || available.idea_types[0]?.code || "",
          category: current.category || available.categories[0]?.code || "",
        }));
      }
      setSelected((current) => records.find((item) => item.id === current?.id) || records[0] || null);
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
    if (!selected || selected.state !== "ACCEPTED") {
      return;
    }
    let active = true;
    projectProposalApi
      .relatedToIdea(token, selected.id)
      .then((items) => active && setRelatedProposals(items))
      .catch((error) => active && setMessage(errorMessage(error)));
    return () => {
      active = false;
    };
  }, [selected, token]);

  async function createIdea(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const created = await ideaDemandApi.create(token, {
        ...draft,
        estimated_value: draft.estimated_value || (null as unknown as string),
      });
      setCreating(false);
      setDraft({ ...emptyDraft, owning_workspace_id: workspaceId || draft.owning_workspace_id });
      setSelected(created);
      await load();
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function action(path: string, body?: unknown) {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      const next = await ideaDemandApi.action(token, selected, path, body);
      setSelected(next);
      await load();
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function screenComplete() {
    if (!options) return;
    const checklist = Object.fromEntries(options.screening_checklist.map((item) => [item.code, true]));
    await action("screen", { checklist, notes: "Screening checklist completed" });
  }

  async function completeEvaluation() {
    if (!selected) return;
    const matrix = selected.evaluations[selected.evaluations.length - 1]?.matrix_snapshot_json;
    const criteria = matrix?.criteria || [
      { code: "strategic_alignment", label: "Strategic alignment", weight: 30 },
      { code: "value", label: "Expected value", weight: 25 },
      { code: "feasibility", label: "Feasibility", weight: 20 },
      { code: "risk", label: "Risk response", weight: 15 },
      { code: "urgency", label: "Urgency", weight: 10 },
    ];
    await action("evaluation/complete", {
      ratings: criteria.map((criterion: { code: string }) => ({
        criterion_code: criterion.code,
        rating: 4,
        comment: "Validated",
      })),
      comments: "Evaluation completed from the controlled matrix.",
    });
  }

  async function previewProjectProposal() {
    if (!selected) return;
    setBusy(true);
    try {
      setProposalPreview(await projectProposalApi.previewFromIdea(token, selected.id));
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function createProjectProposal() {
    if (!selected || proposalPreview?.blockers.length) return;
    setBusy(true);
    try {
      const created = await projectProposalApi.create(token, selected.id);
      setRelatedProposals(await projectProposalApi.relatedToIdea(token, selected.id));
      setProposalPreview(null);
      setMessage(`${created.proposal_number} created as DRAFT. Open Project Proposal to continue.`);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  const counts = {
    open: ideas.filter((item) => !["ACCEPTED", "REJECTED", "CANCELLED", "ARCHIVED"].includes(item.state)).length,
    accepted: ideas.filter((item) => item.state === "ACCEPTED").length,
    decision: ideas.filter((item) => item.state === "EVALUATED").length,
  };

  return (
    <section className="ideaLifecycle" aria-label="Idea Lifecycle">
      <CompactModuleHeader
        eyebrow="Enterprise Strategy Manager / Idea & Demand Manager"
        title="Idea Lifecycle"
        description="Register, screen, route, evaluate and decide enterprise demand with Workspace-scoped traceability."
        tone="user"
        metrics={[
          { label: "Visible", value: ideas.length },
          { label: "Open", value: counts.open },
          { label: "Awaiting decision", value: counts.decision },
          { label: "Accepted", value: counts.accepted },
        ]}
        actions={
          <>
            <button className="ideaSecondary" type="button" onClick={() => void load()} aria-label="Refresh ideas">
              <RefreshCw size={16} /> Refresh
            </button>
            <button className="ideaPrimary" type="button" onClick={() => setCreating(true)}>
              <Plus size={16} /> New Idea
            </button>
          </>
        }
      />

      <nav className="ideaQueues" aria-label="Idea queues">
        {queues.map(([key, label]) => (
          <button key={label} className={queue === key ? "active" : ""} onClick={() => setQueue(key)} type="button">
            {label}
          </button>
        ))}
      </nav>

      <div className="ideaToolbar">
        <input
          aria-label="Search ideas"
          placeholder="Search number or title"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <span>{options?.number_preview ? `Next preview: ${options.number_preview} (not reserved)` : ""}</span>
      </div>
      {message ? (
        <div className="ideaMessage" role="alert">
          {message}
        </div>
      ) : null}

      <div className="ideaWorkspaceGrid">
        <section className="ideaRegister" aria-label="Idea register">
          {ideas.length ? (
            ideas.map((idea) => (
              <button
                className={selected?.id === idea.id ? "ideaRow selected" : "ideaRow"}
                key={idea.id}
                onClick={() => setSelected(idea)}
                type="button"
              >
                <span className={`ideaState state-${idea.state.toLowerCase()}`}>{idea.state.replace(/_/g, " ")}</span>
                <strong>
                  {idea.idea_number} · {idea.title}
                </strong>
                <small>
                  {idea.owning_workspace_name} · {idea.idea_type} / {idea.category}
                </small>
              </button>
            ))
          ) : (
            <div className="ideaEmpty">
              <Lightbulb size={28} />
              <strong>No ideas in this queue</strong>
              <span>Create or select another queue.</span>
            </div>
          )}
        </section>

        <aside className="ideaDetail" aria-label="Idea detail">
          {selected ? (
            <>
              <header>
                <div>
                  <span>{selected.idea_number}</span>
                  <h3>{selected.title}</h3>
                </div>
                <span className={`ideaState state-${selected.state.toLowerCase()}`}>
                  {selected.state.replace(/_/g, " ")}
                </span>
              </header>
              <p>{selected.description}</p>
              <div className="ideaFacts">
                <article>
                  <Lightbulb size={16} />
                  <span>Benefit</span>
                  <strong>{selected.expected_benefit || "Pending"}</strong>
                </article>
                <article>
                  <UserRound size={16} />
                  <span>Owner</span>
                  <strong>{selected.owner_name || "Unassigned"}</strong>
                </article>
                <article>
                  <Route size={16} />
                  <span>Owning Workspace</span>
                  <strong>{selected.owning_workspace_name}</strong>
                </article>
                <article>
                  <Scale size={16} />
                  <span>Evaluation</span>
                  <strong>{selected.evaluations[selected.evaluations.length - 1]?.total_score || "Pending"}</strong>
                </article>
              </div>
              <section className="ideaObjectives">
                <strong>Strategic objectives</strong>
                <div>
                  {selected.strategic_objective_codes.length ? (
                    selected.strategic_objective_codes.map((code) => <span key={code}>{code}</span>)
                  ) : (
                    <em>Not classified</em>
                  )}
                </div>
              </section>
              {selected.state === "ACCEPTED" ? (
                <section className="ideaProposalLink">
                  <header>
                    <div>
                      <strong>Project Proposals</strong>
                      <span>{relatedProposals.length} related strategic record(s)</span>
                    </div>
                    <button
                      disabled={
                        busy || relatedProposals.some((item) => !["CANCELLED", "ARCHIVED"].includes(item.status))
                      }
                      onClick={() => void previewProjectProposal()}
                      type="button"
                    >
                      <Plus size={14} /> Create Project Proposal
                    </button>
                  </header>
                  {relatedProposals.map((proposal) => (
                    <article key={proposal.id}>
                      <span>{proposal.proposal_number}</span>
                      <strong>{proposal.name}</strong>
                      <small>{proposal.status.replace(/_/g, " ")}</small>
                    </article>
                  ))}
                  {proposalPreview ? (
                    <div className="ideaProposalPreview">
                      <span>
                        Preview · {proposalPreview.proposal_number_preview} · mapping revision{" "}
                        {String(proposalPreview.mapping.revision)}
                      </span>
                      <strong>{String(proposalPreview.mapped_fields.name)}</strong>
                      {proposalPreview.blockers.length ? (
                        <small>Blocked: {proposalPreview.blockers.join(" · ")}</small>
                      ) : (
                        <button disabled={busy} onClick={() => void createProjectProposal()} type="button">
                          Create DRAFT
                        </button>
                      )}
                    </div>
                  ) : null}
                </section>
              ) : null}
              <div className="ideaActions">
                {selected.allowed_actions.includes("submit") && (
                  <button disabled={busy} onClick={() => void action("submit")} type="button">
                    <CheckCircle2 size={15} /> Submit
                  </button>
                )}
                {selected.allowed_actions.includes("screen") && (
                  <button disabled={busy} onClick={() => void screenComplete()} type="button">
                    <ClipboardCheck size={15} /> Complete screening
                  </button>
                )}
                {selected.allowed_actions.includes("route") && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void action("route", { route_code: "default", notes: "Default deterministic route" })
                    }
                    type="button"
                  >
                    <Route size={15} /> Route
                  </button>
                )}
                {selected.allowed_actions.includes("assign_owner") && options && (
                  <select
                    aria-label="Assign Idea owner"
                    disabled={busy}
                    defaultValue=""
                    onChange={(event) =>
                      event.target.value && void action("assign-owner", { owner_user_id: Number(event.target.value) })
                    }
                  >
                    <option value="">Assign owner…</option>
                    {options.users.map((user) => (
                      <option key={user.id} value={user.id}>
                        {user.name}
                      </option>
                    ))}
                  </select>
                )}
                {selected.allowed_actions.includes("start_evaluation") && (
                  <button disabled={busy} onClick={() => void action("evaluation/start")} type="button">
                    Start evaluation
                  </button>
                )}
                {selected.allowed_actions.includes("complete_evaluation") && (
                  <button disabled={busy} onClick={() => void completeEvaluation()} type="button">
                    Complete evaluation
                  </button>
                )}
                {selected.allowed_actions.includes("accept") && (
                  <button
                    disabled={busy}
                    onClick={() => void action("accept", { reason: "Accepted after controlled evaluation" })}
                    type="button"
                  >
                    Accept
                  </button>
                )}
                {selected.allowed_actions.includes("reject") && (
                  <button
                    className="danger"
                    disabled={busy}
                    onClick={() => void action("reject", { reason: "Rejected after controlled evaluation" })}
                    type="button"
                  >
                    Reject
                  </button>
                )}
                {selected.allowed_actions.includes("return") && (
                  <button
                    disabled={busy}
                    onClick={() => void action("return", { reason: "Additional information is required" })}
                    type="button"
                  >
                    Return
                  </button>
                )}
              </div>
              {selected.evaluations.length ? (
                <section className="ideaEvaluationHistory">
                  <strong>Evaluation history</strong>
                  {selected.evaluations.map((evaluation) => (
                    <article key={evaluation.id}>
                      <span>Version {evaluation.evaluation_version}</span>
                      <strong>
                        {evaluation.total_score} · {evaluation.result}
                      </strong>
                      <small>Matrix revision {evaluation.matrix_revision}</small>
                    </article>
                  ))}
                </section>
              ) : null}
            </>
          ) : (
            <div className="ideaEmpty">
              <Lightbulb size={28} />
              <strong>Select an Idea</strong>
            </div>
          )}
        </aside>
      </div>

      {creating && options ? (
        <div className="ideaDrawerBackdrop" role="presentation">
          <form className="ideaDrawer" onSubmit={createIdea} aria-label="New Idea form">
            <header>
              <div>
                <span>Idea Lifecycle</span>
                <h3>New Idea</h3>
              </div>
              <button type="button" onClick={() => setCreating(false)}>
                Close
              </button>
            </header>
            <label>
              <span>Number preview</span>
              <input disabled value={options.number_preview} />
            </label>
            <label>
              <span>Title</span>
              <input
                required
                minLength={3}
                value={draft.title}
                onChange={(event) => setDraft({ ...draft, title: event.target.value })}
              />
            </label>
            <label>
              <span>Description</span>
              <textarea
                required
                minLength={3}
                value={draft.description}
                onChange={(event) => setDraft({ ...draft, description: event.target.value })}
              />
            </label>
            <div className="ideaFormGrid">
              <label>
                <span>Owning Workspace</span>
                <select
                  required
                  value={draft.owning_workspace_id || ""}
                  onChange={(event) => setDraft({ ...draft, owning_workspace_id: Number(event.target.value) })}
                >
                  <option value="">Select…</option>
                  {options.owning_workspaces.map((item) => (
                    <option key={String(item.id)} value={Number(item.id)}>
                      {String(item.name)} · {String(item.workspace_type_code)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Target Portfolio (optional)</span>
                <select
                  value={draft.target_portfolio_workspace_id || ""}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
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
              <label>
                <span>Idea type</span>
                <select
                  required
                  value={draft.idea_type}
                  onChange={(event) => setDraft({ ...draft, idea_type: event.target.value })}
                >
                  <option value="">Select…</option>
                  {options.idea_types.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Category</span>
                <select
                  required
                  value={draft.category}
                  onChange={(event) => setDraft({ ...draft, category: event.target.value })}
                >
                  <option value="">Select…</option>
                  {options.categories.map((item) => (
                    <option key={item.code} value={item.code}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              <span>Expected benefit</span>
              <textarea
                value={draft.expected_benefit}
                onChange={(event) => setDraft({ ...draft, expected_benefit: event.target.value })}
              />
            </label>
            <div className="ideaFormGrid">
              <label>
                <span>Estimated value</span>
                <input
                  min="0"
                  type="number"
                  value={draft.estimated_value}
                  onChange={(event) => setDraft({ ...draft, estimated_value: event.target.value })}
                />
              </label>
              <label>
                <span>Currency</span>
                <input
                  maxLength={8}
                  value={draft.currency_code}
                  onChange={(event) => setDraft({ ...draft, currency_code: event.target.value })}
                />
              </label>
            </div>
            <fieldset>
              <legend>Strategic objectives ({options.objective_selection})</legend>
              {options.strategic_objectives.map((objective) => (
                <label className="ideaCheck" key={objective.code}>
                  <input
                    type={options.objective_selection === "one" ? "radio" : "checkbox"}
                    checked={draft.strategic_objective_codes.includes(objective.code)}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        strategic_objective_codes: event.target.checked
                          ? options.objective_selection === "one"
                            ? [objective.code]
                            : [...draft.strategic_objective_codes, objective.code]
                          : draft.strategic_objective_codes.filter((code) => code !== objective.code),
                      })
                    }
                  />
                  {objective.label}
                </label>
              ))}
            </fieldset>
            <footer>
              <button type="button" onClick={() => setCreating(false)}>
                Cancel
              </button>
              <button className="ideaPrimary" disabled={busy} type="submit">
                {busy ? "Saving…" : "Create draft"}
              </button>
            </footer>
          </form>
        </div>
      ) : null}
    </section>
  );
}
