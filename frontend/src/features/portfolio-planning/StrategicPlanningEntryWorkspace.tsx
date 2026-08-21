/* eslint-disable react-hooks/set-state-in-effect, react-hooks/exhaustive-deps */
import { ArrowRight, GitBranch, Layers3, RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "./api";
import type { PlanningOption, StrategicPlanningEntry, StrategicPlanningPreview } from "./types";
import "./portfolioPlanning.css";

function text(value: unknown, fallback = "—") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

export default function StrategicPlanningEntryWorkspace({ token }: { token: string }) {
  const [options, setOptions] = useState<PlanningOption[]>([]);
  const [decisionId, setDecisionId] = useState(0);
  const [preview, setPreview] = useState<StrategicPlanningPreview | null>(null);
  const [entry, setEntry] = useState<StrategicPlanningEntry | null>(null);
  const [parentId, setParentId] = useState(0);
  const [templateId, setTemplateId] = useState(0);
  const [managerId, setManagerId] = useState(0);
  const [projectType, setProjectType] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadOptions() {
    const items = await portfolioPlanningApi.options(token);
    setOptions(items);
    setDecisionId((current) => current || items[0]?.id || 0);
  }

  useEffect(() => {
    void loadOptions().catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load Gate 07D"));
  }, [token]);

  async function loadSelection(id = decisionId) {
    if (!id) return;
    setBusy(true);
    setMessage("");
    try {
      const selected = options.find((item) => item.id === id);
      if (selected?.project_creation_request_id) {
        setEntry(await portfolioPlanningApi.entry(token, id));
        setPreview(null);
      } else {
        const result = await portfolioPlanningApi.preview(token, id);
        setPreview(result);
        setEntry(null);
        setParentId(Number(result.default_project_parent?.id || result.allowed_project_parents[0]?.id || 0));
        setTemplateId(Number(result.suggested_template?.id || result.template_options[0]?.id || 0));
        setManagerId(Number(result.project_manager_candidate?.id || result.project_manager_options[0]?.id || 0));
        setProjectType(result.suggested_project_type || "");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load Strategic Planning Entry");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (decisionId) void loadSelection(decisionId);
  }, [decisionId]);

  async function createEntry() {
    if (!preview) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await portfolioPlanningApi.create(token, {
        strategic_gate_decision_id: decisionId,
        project_parent_workspace_id: parentId,
        project_template_config_id: templateId,
        project_manager_user_id: managerId,
        project_type: projectType,
        expected_decision_hash: preview.source_decision_hash,
        expected_readiness_hash: preview.source_readiness_hash,
      });
      setEntry(result);
      setPreview(null);
      setMessage("Strategic ProjectCreationRequest created. Gate 05B remains authoritative.");
      await loadOptions();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create the planning entry");
    } finally {
      setBusy(false);
    }
  }

  async function runAction(action: string) {
    if (!entry?.project_creation_request) return;
    setBusy(true);
    setMessage("");
    try {
      await portfolioPlanningApi.projectAction(token, entry.project_creation_request, action);
      setEntry(await portfolioPlanningApi.entry(token, decisionId));
      setMessage(`Gate 05B action completed: ${action}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to run ${action}`);
    } finally {
      setBusy(false);
    }
  }

  const lifecycleActions = useMemo(
    () =>
      [
        ["submit_creation_request", "submit", "Submit"],
        ["review_creation_request", "start-review", "Start review"],
        ["approve_creation_request", "approve", "Approve"],
        ["materialize", "materialize", "Materialize PENDING Project"],
      ].filter(([permission]) => entry?.allowed_actions.includes(permission)),
    [entry]
  );

  return (
    <section className="portfolioPlanning" aria-label="Strategic Project Planning Entry">
      <CompactModuleHeader
        description="Bridge an APPROVE Strategic Gate Decision into the existing governed Project creation process, a PENDING Project and its target Portfolio membership."
        eyebrow="USER MODE · ENTERPRISE STRATEGY MANAGER · PORTFOLIO MANAGER"
        metrics={[
          { label: "Eligible decisions", value: options.length },
          { label: "Stage", value: "Portfolio + FEL entry" },
          { label: "Execution", value: "Blocked" },
        ]}
        title="Strategic Project Planning Entry"
        tone="user"
      />

      <div className="planningToolbar">
        <label>
          <span>APPROVE Decision</span>
          <select
            aria-label="APPROVE Strategic Gate Decision"
            onChange={(event) => setDecisionId(Number(event.target.value))}
            value={decisionId}
          >
            {!options.length ? <option value={0}>No eligible decisions</option> : null}
            {options.map((item) => (
              <option key={item.id} value={item.id}>
                {item.decision_number} · {item.project_name} · {item.project_creation_request_state || "Not started"}
              </option>
            ))}
          </select>
        </label>
        <button
          className="planningSecondary"
          disabled={!decisionId || busy}
          onClick={() => void loadSelection()}
          type="button"
        >
          <RefreshCw size={15} /> Refresh source
        </button>
      </div>

      {message ? (
        <div className="planningMessage" role="status">
          {message}
        </div>
      ) : null}

      {preview ? (
        <div className="planningGrid">
          <article className="planningCard planningLineage">
            <header>
              <GitBranch size={18} />
              <h3>Gate 07C Input Contract</h3>
            </header>
            <dl>
              <div>
                <dt>Decision</dt>
                <dd>{text(preview.decision.decision_number)}</dd>
              </div>
              <div>
                <dt>Proposal</dt>
                <dd>{text(preview.proposal.proposal_number)}</dd>
              </div>
              <div>
                <dt>Idea</dt>
                <dd>{text(preview.source_idea.idea_number)}</dd>
              </div>
              <div>
                <dt>Target Portfolio</dt>
                <dd>{text(preview.target_portfolio?.name)}</dd>
              </div>
              <div>
                <dt>Project Number preview</dt>
                <dd>{text(preview.project_number_preview)}</dd>
              </div>
              <div>
                <dt>Record Code preview</dt>
                <dd>{text(preview.record_code_preview)}</dd>
              </div>
            </dl>
          </article>

          <article className="planningCard planningForm">
            <header>
              <Layers3 size={18} />
              <h3>Governed Project prefill</h3>
            </header>
            <label>
              <span>Project parent</span>
              <select
                aria-label="Project parent"
                value={parentId}
                onChange={(event) => setParentId(Number(event.target.value))}
              >
                {preview.allowed_project_parents.map((item) => (
                  <option key={String(item.id)} value={Number(item.id)}>
                    {text(item.name)} · {text(item.workspace_type_code)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Published Project template</span>
              <select
                aria-label="Published Project template"
                value={templateId}
                onChange={(event) => setTemplateId(Number(event.target.value))}
              >
                {preview.template_options.map((item) => (
                  <option key={String(item.id)} value={Number(item.id)}>
                    {text(item.name)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Project Manager</span>
              <select
                aria-label="Project Manager"
                value={managerId}
                onChange={(event) => setManagerId(Number(event.target.value))}
              >
                {preview.project_manager_options.map((item) => (
                  <option key={String(item.id)} value={Number(item.id)}>
                    {text(item.name)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Project Type</span>
              <input
                aria-label="Project Type"
                value={projectType}
                onChange={(event) => setProjectType(event.target.value)}
                placeholder="Select/configure a valid Project Type"
              />
            </label>
            <button
              className="planningPrimary"
              disabled={
                busy || !parentId || !templateId || !managerId || !projectType || preview.blocking_issues.length > 0
              }
              onClick={() => void createEntry()}
              type="button"
            >
              <ArrowRight size={16} /> Create ProjectCreationRequest
            </button>
          </article>

          <ReadinessCard
            label="Portfolio Evaluation Readiness"
            value={preview.portfolio_evaluation_readiness_preview}
          />
          <ReadinessCard label="Project Definition Readiness" value={preview.project_definition_readiness_preview} />
        </div>
      ) : null}

      {entry ? (
        <div className="planningGrid">
          <article className="planningCard planningStatus">
            <header>
              <ShieldCheck size={18} />
              <h3>Portfolio Planning Entry</h3>
            </header>
            <strong className={entry.status === "READY_FOR_PORTFOLIO_PLANNING" ? "ready" : "blocked"}>
              {entry.status}
            </strong>
            <p>PROJECT Workspace: {text(entry.project_workspace?.name, "Not materialized")}</p>
            <p>Workspace status: {text(entry.project_workspace?.status, "—")} · Execution remains blocked.</p>
            <div className="planningActions">
              {lifecycleActions.map(([, action, label]) => (
                <button key={action} disabled={busy} onClick={() => void runAction(action)} type="button">
                  {label}
                </button>
              ))}
            </div>
          </article>
          <article className="planningCard planningLineage">
            <header>
              <GitBranch size={18} />
              <h3>Complete lineage</h3>
            </header>
            <p>
              {text(entry.source_idea.idea_number)} → {text(entry.proposal.proposal_number)} →{" "}
              {text(entry.decision.decision_number)} → {text(entry.project_creation_request?.request_number)} →{" "}
              {text(entry.project_workspace?.code)}
            </p>
            <p>
              Target membership:{" "}
              {entry.portfolio_memberships.find((item) => item.is_target_portfolio)?.portfolio_name || "Pending"}
            </p>
            <p>Planning hash: {entry.planning_entry_hash?.slice(0, 20) || "Pending"}</p>
          </article>
          <ReadinessCard label="Portfolio Evaluation Readiness" value={entry.portfolio_evaluation_readiness} />
          <ReadinessCard label="Project Definition Readiness" value={entry.project_definition_readiness} />
          {entry.blocking_issues.length ? (
            <article className="planningCard planningIssues">
              <h3>Blocking issues</h3>
              {entry.blocking_issues.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </article>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function ReadinessCard({
  label,
  value,
}: {
  label: string;
  value: StrategicPlanningPreview["project_definition_readiness_preview"];
}) {
  return (
    <article className="planningCard readinessCard">
      <header>
        <ShieldCheck size={18} />
        <h3>{label}</h3>
      </header>
      <strong className={value.status === "READY" ? "ready" : "blocked"}>{value.status}</strong>
      <p>
        {value.available_source_data.length}/{value.required_source_data.length} prerequisite(s) available.
      </p>
      {value.suggested_definition_framework ? (
        <small>Framework hint: {value.suggested_definition_framework}</small>
      ) : null}
      {value.blocking_issues.map((item) => (
        <span key={item}>{item}</span>
      ))}
    </article>
  );
}
