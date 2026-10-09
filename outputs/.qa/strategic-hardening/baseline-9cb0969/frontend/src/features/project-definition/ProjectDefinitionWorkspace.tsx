/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { ClipboardCheck, History, Play, RefreshCw, Send, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { projectDefinitionApi } from "./api";
import type { DefinitionAssessment, DefinitionOverview, ElementResult } from "./types";
import "./projectDefinition.css";

const views = [
  "My Projects",
  "FEL Overview",
  "Definition Assessments",
  "Maturity Trend",
  "Gaps & Actions",
  "Evidence",
  "Stage Readiness",
  "History",
];

export default function ProjectDefinitionWorkspace({ token }: { token: string }) {
  const [data, setData] = useState<DefinitionOverview | null>(null);
  const [projectId, setProjectId] = useState(0);
  const [view, setView] = useState("FEL Overview");
  const [editing, setEditing] = useState<DefinitionAssessment | null>(null);
  const [elements, setElements] = useState<ElementResult[]>([]);
  const [evidence, setEvidence] = useState<Record<string, unknown> | null>(null);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");

  async function load(nextProjectId?: number) {
    const result = await projectDefinitionApi.overview(token, nextProjectId || projectId || undefined);
    setData(result);
    setMessage("");
    setProjectId(result.selected_project?.id || 0);
    const active = result.history.find((item) => ["DRAFT", "IN_PROGRESS"].includes(item.status)) || null;
    setEditing(active);
    if (active) setElements(assessmentElements(active));
  }
  useEffect(() => {
    void load().catch((error) =>
      setMessage(error instanceof Error ? error.message : "Unable to load Project Definition")
    );
  }, [token]);

  const readiness = data?.readiness;
  const latest = data?.latest_assessment;
  const metrics = useMemo(
    () => [
      { label: "FEL Stage", value: data?.fel_status?.current_stage_code || "NOT STARTED" },
      { label: "Maturity", value: readiness?.maturity_level || "—" },
      { label: "Threshold", value: readiness?.threshold_status || "NOT EVALUATED" },
      { label: "Readiness", value: readiness?.status || "NOT STARTED" },
    ],
    [data, readiness]
  );

  async function execute(action: string) {
    if (!projectId) return;
    try {
      if (action === "start-fel") await projectDefinitionApi.startFEL(token, projectId);
      if (action === "start-assessment") {
        await projectDefinitionApi.startAssessment(token, projectId);
        // Load the canonical draft before exposing the editable matrix.  Showing
        // local defaults first allowed this refresh to overwrite input typed by
        // a fast user while the request was still settling.
        await load(projectId);
        setView("Definition Assessments");
        setMessage("Project Definition action completed: start-assessment.");
        return;
      }
      if (action === "save" && editing) {
        const updated = await projectDefinitionApi.updateAssessment(token, editing, elements);
        setEditing(updated);
        setElements(assessmentElements(updated));
      }
      if (action === "complete" && editing) {
        // Always persist the matrix immediately before completion.  Comparing
        // only the number of rows misses score, evidence and blocker edits made
        // to an existing IN_PROGRESS assessment and could freeze stale values.
        const current = await projectDefinitionApi.updateAssessment(token, editing, elements);
        await projectDefinitionApi.completeAssessment(token, current);
        setEditing(null);
      }
      if (action === "reevaluate" && latest) await projectDefinitionApi.reevaluate(token, latest.id);
      if (action === "action" && (editing || latest)) {
        const current = editing || latest;
        await projectDefinitionApi.createAction(
          token,
          projectId,
          current!.id,
          elements[0]?.element_key || "general-gap"
        );
      }
      if (action === "submit" && data?.fel_status) {
        await projectDefinitionApi.stageTransition(token, projectId, data.fel_status, "submit-review");
      }
      if (action === "complete-stage" && data?.fel_status) {
        await projectDefinitionApi.stageTransition(token, projectId, data.fel_status, "complete");
      }
      if (action === "refresh") setPreview(await projectDefinitionApi.refreshPreview(token, projectId));
      if (action === "evidence") setEvidence(await projectDefinitionApi.investmentEvidence(token, projectId));
      setMessage(`Project Definition action completed: ${action}.`);
      await load(projectId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to execute ${action}`);
    }
  }

  return (
    <section aria-label="Project Definition / FEL Manager" className="projectDefinition">
      <CompactModuleHeader
        description="Governed FEL stages, definition assessments, maturity, evidence, gaps and readiness. Stage completion is not investment approval, FID or Project activation."
        eyebrow="USER MODE · ENTERPRISE STRATEGY MANAGER"
        metrics={metrics}
        title="Project Definition / FEL Manager"
        tone="user"
      />
      {message ? (
        <div className="definitionMessage" role="status">
          {message}
        </div>
      ) : null}
      <div className="definitionToolbar">
        <label>
          Project Workspace
          <select value={projectId} onChange={(event) => void load(Number(event.target.value))}>
            {!data?.projects.length ? <option value={0}>No Project Workspaces</option> : null}
            {data?.projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.code} · {project.name}
              </option>
            ))}
          </select>
        </label>
        <nav aria-label="Project Definition views">
          {views.map((item) => (
            <button className={view === item ? "active" : ""} key={item} onClick={() => setView(item)} type="button">
              {item}
            </button>
          ))}
        </nav>
      </div>
      <div className={`definitionReadiness ${(readiness?.status || "not-started").toLowerCase()}`}>
        <div>
          <span>PROJECT_DEFINITION_READINESS</span>
          <h3>{readiness?.status || "NOT_STARTED"}</h3>
        </div>
        <div className="definitionChips">
          <b>Evidence {readiness?.evidence_coverage || 0}%</b>
          <b>Blocking items {readiness?.blocking_item_count || 0}</b>
          <b>Open actions {readiness?.open_blocking_action_count || 0}</b>
          <b>Source {readiness?.source_current === false ? "STALE" : "CURRENT"}</b>
          <b className="boundary">FID = false</b>
        </div>
      </div>
      {view === "My Projects" ? <ProjectCards data={data} /> : null}
      {view === "FEL Overview" ? (
        <section className="definitionSurface">
          <header>
            <div>
              <span>FEL Stage Framework</span>
              <h3>{data?.fel_status?.current_stage_code || "FEL not started"}</h3>
            </div>
            <strong>{data?.fel_status?.status || "NOT_STARTED"}</strong>
          </header>
          <div className="definitionFacts">
            <article>
              <span>Framework</span>
              <b>{String(data?.framework?.framework_code || "No published framework")}</b>
              <small>{String(data?.framework?.framework_type || "CUSTOM")}</small>
            </article>
            <article>
              <span>Latest assessment</span>
              <b>{latest?.assessment_number || "—"}</b>
              <small>{latest?.status || "No assessment"}</small>
            </article>
            <article>
              <span>FEL Stage ≠ Maturity</span>
              <b>
                {data?.fel_status?.current_stage_code || "—"} / {readiness?.maturity_level || "—"}
              </b>
              <small>Tracked independently</small>
            </article>
            <article>
              <span>Governance</span>
              <b>{data?.selected_project?.governance_model || "—"}</b>
              <small>Contractor/Direct are optional by default</small>
            </article>
          </div>
          <div className="definitionActions">
            <button
              disabled={!projectId || Boolean(data?.fel_status)}
              onClick={() => void execute("start-fel")}
              type="button"
            >
              <Play size={15} /> Start FEL
            </button>
            <button
              disabled={!data?.fel_status || Boolean(editing)}
              onClick={() => void execute("start-assessment")}
              type="button"
            >
              <ClipboardCheck size={15} /> Start Assessment
            </button>
            <button disabled={!data?.fel_status} onClick={() => void execute("refresh")} type="button">
              <RefreshCw size={15} /> Refresh Preview
            </button>
            <button
              disabled={readiness?.status !== "READY" || data?.fel_status?.status !== "IN_STAGE"}
              onClick={() => void execute("submit")}
              type="button"
            >
              <Send size={15} /> Submit Stage Review
            </button>
            <button
              disabled={data?.fel_status?.status !== "READY_FOR_STAGE_REVIEW"}
              onClick={() => void execute("complete-stage")}
              type="button"
            >
              Complete Stage
            </button>
          </div>
          {preview ? <pre>{JSON.stringify(preview, null, 2)}</pre> : null}
        </section>
      ) : null}
      {view === "Definition Assessments" ? (
        <AssessmentPanel
          assessment={editing || latest}
          elements={elements}
          onElements={setElements}
          onAction={execute}
        />
      ) : null}
      {view === "Maturity Trend" ? <TrendPanel data={data?.maturity_trend || []} /> : null}
      {view === "Gaps & Actions" ? <ActionsPanel data={data} token={token} onReload={() => load(projectId)} /> : null}
      {view === "Evidence" ? (
        <section className="definitionSurface">
          <header>
            <div>
              <span>Governed source adapter</span>
              <h3>Investment Gate evidence contract</h3>
            </div>
            <button onClick={() => void execute("evidence")} type="button">
              Resolve evidence
            </button>
          </header>
          <pre>
            {JSON.stringify(
              evidence || { source_module: "PROJECT_DEFINITION_FEL", status: readiness?.status },
              null,
              2
            )}
          </pre>
        </section>
      ) : null}
      {view === "Stage Readiness" ? <ReadinessPanel readiness={readiness || null} /> : null}
      {view === "History" ? <HistoryPanel data={data?.history || []} /> : null}
      <p className="definitionGuardrail">
        STOP boundary: no Funds, Funding, Investment Decision, FID, GO/HOLD/RECYCLE/KILL, Project Initialization,
        Activation, Execution, CPM or P6 automation.
      </p>
    </section>
  );
}

function assessmentElements(assessment: DefinitionAssessment): ElementResult[] {
  if (assessment.element_results.length) return assessment.element_results;
  const definitions = (assessment.source_snapshot.applicable_elements || []) as Array<Record<string, unknown>>;
  return definitions.map((item) => ({
    element_key: String(item.element_key),
    category_key: String(item.category_key),
    name: String(item.name || item.element_key),
    applicable: true,
    score: 85,
    maturity_status: "READY",
    comment: "Governed definition assessment result.",
    evidence_refs: [{ reference: `${String(item.element_key)}-evidence`, origin: "GOVERNED_SOURCE" }],
    blocking: false,
    action_required: false,
  }));
}

function ProjectCards({ data }: { data: DefinitionOverview | null }) {
  return (
    <section className="definitionSurface">
      <header>
        <div>
          <span>Capability applicability</span>
          <h3>My Projects</h3>
        </div>
      </header>
      <div className="definitionFacts">
        {data?.projects.map((project) => (
          <article key={project.id}>
            <span>{project.code}</span>
            <b>{project.name}</b>
            <small>
              {project.governance_model} · {project.project_type || "OTHER"}
            </small>
          </article>
        ))}
      </div>
    </section>
  );
}

function AssessmentPanel({
  assessment,
  elements,
  onElements,
  onAction,
}: {
  assessment: DefinitionAssessment | null | undefined;
  elements: ElementResult[];
  onElements: (items: ElementResult[]) => void;
  onAction: (action: string) => void;
}) {
  if (!assessment)
    return (
      <section className="definitionSurface">
        <h3>No assessment started</h3>
        <p>Start FEL and create an assessment from FEL Overview.</p>
      </section>
    );
  return (
    <section className="definitionSurface">
      <header>
        <div>
          <span>
            {assessment.framework_type} · {assessment.framework_version}
          </span>
          <h3>{assessment.assessment_number}</h3>
        </div>
        <strong>{assessment.status}</strong>
      </header>
      <div className="assessmentMatrix">
        <div className="matrixHead">
          <b>Category</b>
          <b>Element</b>
          <b>Score / Maturity</b>
          <b>Evidence</b>
          <b>Blocking</b>
          <b>Comment</b>
        </div>
        {elements.map((item, index) => (
          <div className="matrixRow" key={item.element_key}>
            <span>{item.category_key}</span>
            <b>{item.name || item.element_key}</b>
            <input
              aria-label={`Score ${item.element_key}`}
              disabled={assessment.status === "COMPLETED"}
              type="number"
              value={item.score ?? ""}
              onChange={(event) =>
                onElements(
                  elements.map((entry, row) =>
                    row === index ? { ...entry, score: Number(event.target.value) } : entry
                  )
                )
              }
            />
            <span>{item.evidence_refs.length ? "Present" : "Missing"}</span>
            <input
              aria-label={`Blocking ${item.element_key}`}
              checked={item.blocking}
              disabled={assessment.status === "COMPLETED"}
              type="checkbox"
              onChange={(event) =>
                onElements(
                  elements.map((entry, row) => (row === index ? { ...entry, blocking: event.target.checked } : entry))
                )
              }
            />
            <input
              aria-label={`Comment ${item.element_key}`}
              disabled={assessment.status === "COMPLETED"}
              value={item.comment}
              onChange={(event) =>
                onElements(
                  elements.map((entry, row) => (row === index ? { ...entry, comment: event.target.value } : entry))
                )
              }
            />
          </div>
        ))}
      </div>
      <div className="definitionActions">
        <button disabled={assessment.status === "COMPLETED"} onClick={() => onAction("save")} type="button">
          Save Assessment
        </button>
        <button disabled={assessment.status === "COMPLETED"} onClick={() => onAction("complete")} type="button">
          Complete Assessment
        </button>
        <button disabled={assessment.status !== "COMPLETED"} onClick={() => onAction("reevaluate")} type="button">
          Start Reevaluation
        </button>
        <button onClick={() => onAction("action")} type="button">
          Add Definition Action
        </button>
      </div>
    </section>
  );
}

function TrendPanel({ data }: { data: Array<Record<string, unknown>> }) {
  return (
    <section className="definitionSurface">
      <header>
        <div>
          <span>Version-aware</span>
          <h3>
            <TrendingUp size={17} /> Definition Maturity Trend
          </h3>
        </div>
      </header>
      <div className="trendList">
        {data.map((item) => (
          <article key={String(item.assessment_id)}>
            <b>{String(item.assessment_date).slice(0, 10)}</b>
            <span>
              {String(item.FEL_stage)} · {String(item.framework)} v{String(item.framework_version)}
            </span>
            <strong>
              {String(item.score ?? "—")} / {String(item.maturity_level)}
            </strong>
            <small>
              Segment {String(item.trend_segment)} · {String(item.threshold_status)}
            </small>
          </article>
        ))}
      </div>
      {!data.length ? <p>No completed assessments.</p> : null}
    </section>
  );
}

function ActionsPanel({
  data,
  token,
  onReload,
}: {
  data: DefinitionOverview | null;
  token: string;
  onReload: () => Promise<void>;
}) {
  return (
    <section className="definitionSurface">
      <header>
        <div>
          <span>Definition gaps only</span>
          <h3>Gaps & Actions</h3>
        </div>
      </header>
      <div className="actionList">
        {data?.actions.map((action) => (
          <article key={action.id}>
            <div>
              <b>{action.title}</b>
              <small>
                {action.element_key} · {action.blocking ? "Blocking" : "Non-blocking"}
              </small>
            </div>
            <strong>{action.status}</strong>
            <button
              disabled={!["OPEN", "IN_PROGRESS"].includes(action.status)}
              onClick={() => void projectDefinitionApi.updateAction(token, action, "RESOLVED").then(onReload)}
              type="button"
            >
              Resolve
            </button>
          </article>
        ))}
      </div>
      {!data?.actions.length ? <p>No definition actions.</p> : null}
    </section>
  );
}

function ReadinessPanel({ readiness }: { readiness: DefinitionOverview["readiness"] }) {
  return (
    <section className="definitionSurface">
      <header>
        <div>
          <span>READY | BLOCKED | STALE | NOT_STARTED</span>
          <h3>Project Definition Readiness</h3>
        </div>
        <strong>{readiness?.status || "NOT_STARTED"}</strong>
      </header>
      <div className="definitionFacts">
        <article>
          <span>Required stage</span>
          <b>{readiness?.required_stage || "—"}</b>
        </article>
        <article>
          <span>Required maturity</span>
          <b>{readiness?.required_maturity || "—"}</b>
        </article>
        <article>
          <span>Evidence coverage</span>
          <b>{readiness?.evidence_coverage || 0}%</b>
        </article>
        <article>
          <span>Gate evidence</span>
          <b>{readiness?.can_supply_investment_gate_evidence ? "AVAILABLE" : "BLOCKED"}</b>
        </article>
      </div>
      <pre>
        {JSON.stringify(
          {
            blockers: readiness?.blockers || [],
            warnings: readiness?.warnings || [],
            definition_readiness_hash: readiness?.definition_readiness_hash,
          },
          null,
          2
        )}
      </pre>
    </section>
  );
}

function HistoryPanel({ data }: { data: DefinitionAssessment[] }) {
  return (
    <section className="definitionSurface">
      <header>
        <div>
          <span>Immutable completed records</span>
          <h3>
            <History size={17} /> Assessment History
          </h3>
        </div>
      </header>
      <div className="trendList">
        {data.map((item) => (
          <article key={item.id}>
            <b>{item.assessment_number}</b>
            <span>
              {item.fel_stage_code} · {item.framework_code}
            </span>
            <strong>{item.status}</strong>
            <small>{item.assessment_hash || "No completion hash"}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
