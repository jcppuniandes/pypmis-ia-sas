/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Camera, CheckCircle2, FilePlus2, RefreshCw, Save, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { businessCaseApi } from "./api";
import type { BusinessCase, BusinessCaseRevision, DecisionSnapshot, Readiness, RefreshPreview } from "./types";
import "./businessCase.css";

type View =
  | "mine"
  | "overview"
  | "revision"
  | "strategic"
  | "alternatives"
  | "benefits"
  | "definition"
  | "financial"
  | "budget-resources"
  | "funding"
  | "risk-permits"
  | "execution"
  | "assumptions"
  | "recommendation"
  | "readiness"
  | "material"
  | "snapshots"
  | "history";

const VIEW_BY_ROUTE: Record<string, View> = {
  "business-case-my": "mine",
  "business-case-overview": "overview",
  "business-case-current-revision": "revision",
  "business-case-strategic": "strategic",
  "business-case-alternatives": "alternatives",
  "business-case-benefits": "benefits",
  "business-case-project-definition": "definition",
  "business-case-financial": "financial",
  "business-case-budget-resources": "budget-resources",
  "business-case-funding": "funding",
  "business-case-risk-permits": "risk-permits",
  "business-case-execution": "execution",
  "business-case-assumptions": "assumptions",
  "business-case-recommendation": "recommendation",
  "business-case-readiness": "readiness",
  "business-case-material-changes": "material",
  "business-case-decision-snapshots": "snapshots",
  "business-case-history": "history",
};

const labels: Record<View, string> = {
  mine: "My Business Cases",
  overview: "Business Case Overview",
  revision: "Current Revision",
  strategic: "Strategic Case",
  alternatives: "Alternatives",
  benefits: "Benefits & Value",
  definition: "Project Definition",
  financial: "Economic & Financial Model",
  "budget-resources": "Budget / Resources",
  funding: "Funding",
  "risk-permits": "Risk / Permits",
  execution: "Execution Case",
  assumptions: "Assumptions & Constraints",
  recommendation: "Recommendation",
  readiness: "Business Case Readiness",
  material: "Material Changes",
  snapshots: "Decision Snapshots",
  history: "History / Audit",
};

export default function BusinessCaseWorkspace({ token, initialView }: { token: string; initialView?: string }) {
  const [view, setView] = useState<View>(VIEW_BY_ROUTE[initialView || ""] || "mine");
  const [records, setRecords] = useState<BusinessCase[]>([]);
  const [selectedId, setSelectedId] = useState(0);
  const [revisions, setRevisions] = useState<BusinessCaseRevision[]>([]);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [preview, setPreview] = useState<RefreshPreview | null>(null);
  const [snapshots, setSnapshots] = useState<DecisionSnapshot[]>([]);
  const [message, setMessage] = useState("");
  const [projectId, setProjectId] = useState("");
  const [proposalId, setProposalId] = useState("");
  const [editor, setEditor] = useState({ title: "", executive_summary: "", business_need: "" });
  const selected = records.find((item) => item.id === selectedId) || records[0] || null;
  const revision = selected?.current_revision || null;

  const metrics = useMemo(
    () => [
      { label: "Business Cases", value: records.length },
      { label: "Ready", value: records.filter((item) => item.final_output.startsWith("READY_")).length },
      {
        label: "Open revisions",
        value: records.filter((item) => item.current_revision?.status !== "COMPLETED").length,
      },
      { label: "Financial engine", value: "Not started" },
    ],
    [records]
  );

  async function load(preferredId?: number) {
    const rows = await businessCaseApi.list(token);
    setRecords(rows);
    setSelectedId(preferredId || rows[0]?.id || 0);
  }

  useEffect(() => setView(VIEW_BY_ROUTE[initialView || ""] || "mine"), [initialView]);
  useEffect(() => {
    void load().catch((error) => setMessage(error instanceof Error ? error.message : "Unable to load Business Cases"));
  }, [token]);
  useEffect(() => {
    if (!selected) {
      setRevisions([]);
      setReadiness(null);
      setSnapshots([]);
      return;
    }
    setEditor({
      title: revision?.title || "",
      executive_summary: revision?.executive_summary || "",
      business_need: revision?.business_need || "",
    });
    void Promise.all([
      businessCaseApi.revisions(token, selected.id),
      businessCaseApi.readiness(token, selected.id),
      businessCaseApi.snapshots(token, selected.id),
    ]).then(([revisionRows, readinessResult, snapshotRows]) => {
      setRevisions(revisionRows);
      setReadiness(readinessResult);
      setSnapshots(snapshotRows);
    });
  }, [selected?.id, selected?.current_revision_id]);

  async function create() {
    try {
      const result = await businessCaseApi.create(
        token,
        Number(projectId),
        proposalId ? Number(proposalId) : undefined
      );
      await load(result.id);
      setMessage(`${result.business_case_number} created from governed Project Proposal mapping.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Business Case creation failed");
    }
  }

  async function act(action: "save" | "submit" | "complete" | "new" | "preview" | "refresh" | "snapshot") {
    if (!selected || !revision) return;
    try {
      if (action === "save") await businessCaseApi.updateRevision(token, revision, editor);
      if (action === "submit") await businessCaseApi.submitReview(token, revision);
      if (action === "complete") await businessCaseApi.complete(token, revision);
      if (action === "new") await businessCaseApi.createRevision(token, selected.id, "REVALIDATION");
      if (action === "preview") {
        setPreview(await businessCaseApi.previewRefresh(token, selected.id));
        setMessage("Refresh preview completed with persisted=false.");
        return;
      }
      if (action === "refresh") await businessCaseApi.refresh(token, selected);
      if (action === "snapshot") await businessCaseApi.createSnapshot(token, selected, revision);
      await load(selected.id);
      setMessage(`Business Case action ${action} completed under ETag/idempotency controls.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action}`);
    }
  }

  const sourceForView = () => {
    if (!revision) return {};
    if (view === "strategic")
      return { strategic_alignment: revision.strategic_alignment_json, business_need: revision.business_need };
    if (view === "alternatives") return { alternatives: revision.alternatives_json };
    if (view === "benefits") return { benefits: revision.benefits_json };
    if (view === "definition") return revision.source_references_json.fel || { status: "NOT_AVAILABLE" };
    if (view === "financial")
      return {
        status: revision.financial_model_status,
        model_id: revision.economic_financial_model_id,
        version: revision.economic_financial_model_version,
        evidence_hash: revision.economic_financial_model_hash,
        readiness: revision.economic_financial_readiness,
        as_of_date: revision.economic_financial_as_of_date,
        npv: revision.npv,
        irr: revision.irr,
        payback_period: revision.payback_period,
        benefit_cost_ratio: revision.benefit_cost_ratio,
        note: "Gate 07M-FIN provides the governed model, readiness and immutable evidence contract.",
      };
    if (view === "budget-resources")
      return { budget: revision.source_references_json.budget, resources: revision.source_references_json.resource };
    if (view === "funding") return revision.source_references_json.funding || { status: "NOT_AVAILABLE" };
    if (view === "risk-permits")
      return { risk: revision.source_references_json.risk, permits: revision.source_references_json.permit };
    if (view === "execution") return revision.delivery_json;
    if (view === "assumptions")
      return {
        assumptions: revision.assumptions_json,
        constraints: revision.constraints_json,
        unresolved_concerns: revision.unresolved_concerns_json,
      };
    if (view === "recommendation") return revision.recommendation_json;
    if (view === "readiness") return readiness || {};
    if (view === "material") return preview || { material_change_status: revision.material_change_status };
    if (view === "snapshots") return { snapshots };
    if (view === "history") return { revisions, decision_snapshots: snapshots };
    return revision;
  };

  return (
    <section aria-label="Business Case Manager" className="businessCase">
      <CompactModuleHeader
        description="Longitudinal, governed Business Case revisions with source lineage, readiness, material-change review and immutable decision snapshots."
        eyebrow="USER MODE · ENTERPRISE STRATEGY MANAGER · GATE 07M-BC"
        metrics={metrics}
        title="Business Case Manager"
      />
      {message ? (
        <div className="businessCaseMessage" role="status">
          {message}
        </div>
      ) : null}
      <nav aria-label="Business Case views" className="businessCaseTabs">
        {(Object.keys(labels) as View[]).map((item) => (
          <button className={view === item ? "active" : ""} key={item} onClick={() => setView(item)} type="button">
            {labels[item]}
          </button>
        ))}
      </nav>
      <div className="businessCaseControls">
        <label>
          Business Case
          <select value={selected?.id || 0} onChange={(event) => setSelectedId(Number(event.target.value))}>
            {!records.length ? <option value={0}>No governed Business Cases</option> : null}
            {records.map((item) => (
              <option key={item.id} value={item.id}>
                {item.business_case_number} · {item.current_revision?.title}
              </option>
            ))}
          </select>
        </label>
        <button disabled={!revision || revision.status !== "DRAFT"} onClick={() => void act("save")} type="button">
          <Save size={15} /> Save
        </button>
        <button disabled={!revision || revision.status !== "DRAFT"} onClick={() => void act("submit")} type="button">
          <Send size={15} /> Submit
        </button>
        <button
          disabled={!revision || revision.status !== "IN_REVIEW"}
          onClick={() => void act("complete")}
          type="button"
        >
          <CheckCircle2 size={15} /> Complete
        </button>
        <button disabled={!revision || revision.status !== "COMPLETED"} onClick={() => void act("new")} type="button">
          <FilePlus2 size={15} /> New revision
        </button>
        <button disabled={!selected} onClick={() => void act("preview")} type="button">
          <RefreshCw size={15} /> Refresh preview
        </button>
        <button
          disabled={!preview || revision?.status !== "COMPLETED"}
          onClick={() => void act("refresh")}
          type="button"
        >
          <RefreshCw size={15} /> Create revision
        </button>
        <button
          disabled={!revision || revision.status !== "COMPLETED"}
          onClick={() => void act("snapshot")}
          type="button"
        >
          <Camera size={15} /> Decision snapshot
        </button>
      </div>

      {!records.length ? (
        <section className="businessCaseSurface createSurface">
          <h3>Create governed Business Case R1</h3>
          <p>The Project Proposal remains untouched; the mapping is persisted with its configuration hash.</p>
          <label>
            Project Workspace ID
            <input inputMode="numeric" value={projectId} onChange={(event) => setProjectId(event.target.value)} />
          </label>
          <label>
            Project Proposal ID (optional when linked)
            <input inputMode="numeric" value={proposalId} onChange={(event) => setProposalId(event.target.value)} />
          </label>
          <button disabled={!Number(projectId)} onClick={() => void create()} type="button">
            <FilePlus2 size={15} /> Create Business Case
          </button>
        </section>
      ) : null}

      {selected && revision ? (
        <section className="businessCaseSurface">
          <header>
            <div>
              <span>{labels[view]}</span>
              <h3>
                {selected.business_case_number} · {revision.revision_label}
              </h3>
            </div>
            <b>
              {revision.status} · {readiness?.status || revision.readiness_status}
            </b>
          </header>
          <div className="businessCaseFacts">
            <article>
              <span>Project Workspace</span>
              <b>{selected.project_workspace_id}</b>
            </article>
            <article>
              <span>Purpose</span>
              <b>{revision.purpose}</b>
            </article>
            <article>
              <span>FEL stage / as-of</span>
              <b>
                {revision.fel_stage_code || "NOT_AVAILABLE"}
                <br />
                {new Date(revision.as_of_date).toLocaleDateString()}
              </b>
            </article>
            <article>
              <span>Material change</span>
              <b>{revision.material_change_status}</b>
            </article>
            <article>
              <span>Output / NEXT</span>
              <b>
                {selected.final_output}
                <br />
                {selected.next_process}
              </b>
            </article>
          </div>
          {view === "revision" ? (
            <div className="businessCaseEditor">
              <label>
                Title
                <input
                  disabled={revision.status !== "DRAFT"}
                  value={editor.title}
                  onChange={(event) => setEditor({ ...editor, title: event.target.value })}
                />
              </label>
              <label>
                Executive summary
                <textarea
                  disabled={revision.status !== "DRAFT"}
                  rows={5}
                  value={editor.executive_summary}
                  onChange={(event) => setEditor({ ...editor, executive_summary: event.target.value })}
                />
              </label>
              <label>
                Business need
                <textarea
                  disabled={revision.status !== "DRAFT"}
                  rows={5}
                  value={editor.business_need}
                  onChange={(event) => setEditor({ ...editor, business_need: event.target.value })}
                />
              </label>
            </div>
          ) : view === "mine" || view === "overview" ? (
            <div className="businessCaseLineage">
              <h4>Source lineage</h4>
              {Object.entries(revision.source_references_json).map(([name, value]) => (
                <article key={name}>
                  <b>{name}</b>
                  <span>{String(value.status || value.readiness || "referenced")}</span>
                  <code>{revision.source_hashes_json[name]?.slice(0, 16)}</code>
                </article>
              ))}
            </div>
          ) : (
            <pre>{JSON.stringify(sourceForView(), null, 2)}</pre>
          )}
        </section>
      ) : null}
      {preview ? (
        <section className="businessCaseSurface">
          <h3>Refresh preview · persisted=false</h3>
          <pre>{JSON.stringify(preview, null, 2)}</pre>
        </section>
      ) : null}
      <p className="businessCaseGuardrail">
        STOP boundary: this release does not calculate NPV, IRR, payback or BCR; recommendations never become investment
        decisions or Project lifecycle mutations.
      </p>
    </section>
  );
}
