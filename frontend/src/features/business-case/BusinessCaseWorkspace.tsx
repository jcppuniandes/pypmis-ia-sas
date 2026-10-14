/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { AlertTriangle, Camera, CheckCircle2, ExternalLink, FilePlus2, RefreshCw, Save, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ControlFlowView } from "../../navigation/applicationNavigation";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import QraEvidenceSummary from "../investment-evidence-policy/QraEvidenceSummary";
import { qraEvidenceSourceHref } from "../investment-evidence-policy/qraSourceLink";
import { businessCaseApi } from "./api";
import type {
  BusinessCase,
  BusinessCaseRevision,
  BusinessCaseSourceEvidence,
  DecisionSnapshot,
  FiveCaseModel,
  FiveCaseSection,
  Readiness,
  RefreshPreview,
} from "./types";
import "./businessCase.css";

type View =
  | "overview"
  | "strategic"
  | "economic"
  | "commercial"
  | "financial"
  | "management"
  | "sources"
  | "readiness"
  | "snapshots"
  | "history";
type CaseView = Extract<View, "strategic" | "economic" | "commercial" | "financial" | "management">;
type CaseKey = `${CaseView}_case`;

const VIEW_BY_ROUTE: Record<string, View> = {
  "business-case-my": "overview",
  "business-case-overview": "overview",
  "business-case-economic": "economic",
  "business-case-commercial": "commercial",
  "business-case-management": "management",
  "business-case-sources-evidence": "sources",
  "business-case-current-revision": "overview",
  "business-case-strategic": "strategic",
  "business-case-alternatives": "economic",
  "business-case-benefits": "strategic",
  "business-case-project-definition": "management",
  "business-case-financial": "financial",
  "business-case-budget-resources": "financial",
  "business-case-funding": "financial",
  "business-case-risk-permits": "management",
  "business-case-execution": "management",
  "business-case-assumptions": "management",
  "business-case-recommendation": "economic",
  "business-case-readiness": "readiness",
  "business-case-material-changes": "readiness",
  "business-case-decision-snapshots": "snapshots",
  "business-case-history": "history",
};

const labels: Record<View, string> = {
  overview: "Overview",
  strategic: "Strategic Case",
  economic: "Economic Case",
  commercial: "Commercial Case",
  financial: "Financial Case",
  management: "Management Case",
  sources: "Sources & Evidence",
  readiness: "Readiness",
  snapshots: "Decision Snapshots",
  history: "History",
};

const CASE_DEFINITIONS: Record<CaseView, { question: string; key: CaseKey; sourceHints: string[] }> = {
  strategic: {
    key: "strategic_case",
    question: "Why should the organization intervene and how is the investment strategically justified?",
    sourceHints: ["IDEA", "STRATEG", "BUSINESS_ANALYSIS", "PROPOSAL", "BENEFIT"],
  },
  economic: {
    key: "economic_case",
    question: "Which option provides the best overall value considering cost, benefits and risk?",
    sourceHints: ["BUSINESS_ANALYSIS", "OPTION", "BENEFIT", "ECONOMIC", "FINANCIAL", "RISK"],
  },
  commercial: {
    key: "commercial_case",
    question: "Can the preferred option be procured and commercially structured?",
    sourceHints: ["COMMERCIAL", "CONTRACT"],
  },
  financial: {
    key: "financial_case",
    question: "Can the organization afford and finance the investment?",
    sourceHints: ["BUDGET", "FUND", "ECONOMIC", "FINANCIAL", "BENEFIT"],
  },
  management: {
    key: "management_case",
    question: "Can the organization deliver and govern the investment successfully?",
    sourceHints: ["FEL", "DEFINITION", "RESOURCE", "RISK", "PERMIT", "BENEFIT", "COMMERCIAL", "CONTRACT"],
  },
};

const SOURCE_ROUTES: Array<[string[], ControlFlowView]> = [
  [["QRA"], "qra-run-overview"],
  [["STRATEGIC_OBJECTIVE", "IDEA"], "idea-lifecycle"],
  [["BUSINESS_ANALYSIS", "OPTION"], "business-analysis-options"],
  [["PROJECT_PROPOSAL", "PROPOSAL"], "project-proposal"],
  [["STRATEGIC_BENEFIT", "BENEFIT"], "strategic-benefits-overview"],
  [["COMMERCIAL", "CONTRACT"], "commercial-strategy-overview"],
  [["PROJECT_DEFINITION", "FEL"], "project-definition-fel"],
  [["BUDGET"], "portfolio-budget-planning"],
  [["RESOURCE"], "portfolio-resource-planning"],
  [["FUND"], "funds-overview"],
  [["ECONOMIC_FINANCIAL", "FINANCIAL_MODEL", "FIN"], "financial-model-overview"],
  [["RISK"], "risk-readiness-my"],
  [["PERMIT"], "permit-readiness-my"],
  [["INVESTMENT_DECISION"], "investment-decision-package"],
];

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asText(value: unknown, fallback = "Not available") {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function asList(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  const record = asRecord(value);
  return Object.keys(record).length ? Object.entries(record).map(([name, detail]) => ({ name, detail })) : [];
}

function sourceName(value: string) {
  return value
    .replace(/_JSON$/i, "")
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function sourceRoute(source: BusinessCaseSourceEvidence): ControlFlowView | null {
  const normalized = `${source.source_module || ""}`.toUpperCase();
  return SOURCE_ROUTES.find(([hints]) => hints.some((hint) => normalized.includes(hint)))?.[1] ?? null;
}

function qraSourceSummary(source: BusinessCaseSourceEvidence, revision?: BusinessCaseRevision) {
  const key =
    source.analysis_type === "SCHEDULE_QRA" || String(source.source_module).toUpperCase().includes("SCHEDULE")
      ? "schedule_qra_result"
      : "cost_qra_result";
  return source.qra_summary || revision?.source_references_json[key] || (source as Record<string, unknown>);
}

function normalizedSources(revision: BusinessCaseRevision): BusinessCaseSourceEvidence[] {
  if (Array.isArray(revision.source_evidence_matrix_json) && revision.source_evidence_matrix_json.length) {
    return revision.source_evidence_matrix_json;
  }
  return Object.entries(revision.source_references_json || {})
    .filter(([name]) => !name.startsWith("_"))
    .map(([name, raw]) => {
      const source = asRecord(raw);
      const readiness = source.readiness ?? source.readiness_status ?? source.status;
      const current = source.source_current ?? source.current;
      return {
        source_module: asText(source.source_module, name.toUpperCase()),
        source_id: (source.source_id ?? source.id ?? source.reference_id ?? null) as string | number | null,
        source_version_id: (source.source_version_id ?? source.version_id ?? source.version ?? null) as
          | string
          | number
          | null,
        source_hash: asText(source.source_hash ?? source.hash ?? revision.source_hashes_json?.[name], ""),
        source_status: asText(source.status, "NOT_AVAILABLE"),
        source_readiness: asText(readiness, "NOT_AVAILABLE"),
        as_of_date: asText(source.as_of_date, ""),
        source_current: typeof current === "boolean" ? current : !String(readiness || "").includes("STALE"),
        blocking: Boolean(source.blocking),
        ...(source.analysis_type
          ? { analysis_type: source.analysis_type as "COST_QRA" | "SCHEDULE_QRA", qra_summary: source }
          : {}),
      };
    });
}

function fiveCaseModel(revision: BusinessCaseRevision): FiveCaseModel {
  return revision.five_case_json || {};
}

function readinessMap(revision: BusinessCaseRevision) {
  return asRecord(revision.five_case_readiness_json);
}

function caseReadiness(revision: BusinessCaseRevision, view: CaseView, payload: FiveCaseSection) {
  const key = CASE_DEFINITIONS[view].key;
  const readiness = readinessMap(revision);
  return asText(
    payload.case_readiness ??
      payload.readiness ??
      readiness[key] ??
      readiness[`${key}_readiness`] ??
      readiness[`${key.toUpperCase()}_READINESS`],
    "NOT_STARTED"
  );
}

function sourcesForCase(sources: BusinessCaseSourceEvidence[], view: CaseView) {
  const definition = CASE_DEFINITIONS[view];
  return sources.filter((source) => {
    const namedCase = `${source.case || ""}`.toLowerCase().replace(/[^a-z]/g, "");
    if (namedCase) return namedCase.includes(view);
    const module = `${source.source_module || ""}`.toUpperCase();
    if (source.analysis_type || module.includes("QRA")) {
      return source.analysis_type === "SCHEDULE_QRA"
        ? view === "management"
        : view === "economic" || view === "financial";
    }
    return definition.sourceHints.some((hint) => module.includes(hint));
  });
}

function legacyCasePayload(revision: BusinessCaseRevision, view: CaseView): FiveCaseSection {
  if (view === "strategic") {
    return {
      summary: revision.executive_summary || revision.business_need,
      key_findings: [...revision.strategic_alignment_json, ...revision.objectives_json, ...revision.benefits_json],
      assumptions: revision.assumptions_json,
      conclusion: revision.business_need,
    };
  }
  if (view === "economic") {
    return {
      summary: asText(revision.recommendation_json.summary, "Legacy option and recommendation synthesis"),
      key_findings: revision.alternatives_json,
      assumptions: revision.assumptions_json,
      conclusion: asText(revision.recommendation_json.conclusion ?? revision.recommendation_json.status),
    };
  }
  if (view === "commercial") {
    return {
      summary: "Commercial evidence is consumed from its governed source when available.",
      conclusion: "No independent procurement or contracting transaction is performed here.",
    };
  }
  if (view === "financial") {
    return {
      summary:
        "Financial evidence is referenced from Budget, Funding and the governed FIN model; no metric is recalculated.",
      key_findings: {
        model_status: revision.financial_model_status,
        model_id: revision.economic_financial_model_id,
        model_version: revision.economic_financial_model_version,
        npv: revision.npv,
        irr: revision.irr,
        payback_period: revision.payback_period,
        benefit_cost_ratio: revision.benefit_cost_ratio,
      },
      conclusion: asText(revision.economic_financial_readiness, revision.financial_model_status),
    };
  }
  return {
    summary:
      "Delivery and governance evidence is synthesized from FEL, Resources, Risk, Permits, Benefits and Commercial sources.",
    key_findings: { scope: revision.scope_json, delivery: revision.delivery_json },
    assumptions: revision.assumptions_json,
    warnings: ["Owner Capability is NOT_AVAILABLE until a governed provider exists."],
    conclusion: asText(
      revision.recommendation_json.management_conclusion,
      "Progressive maturity applies by FEL and Gate."
    ),
  };
}

function readableDate(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
}

function EvidenceTable({
  onNavigate,
  rows,
  revision,
}: {
  onNavigate?: (view: ControlFlowView) => void;
  rows: BusinessCaseSourceEvidence[];
  revision?: BusinessCaseRevision;
}) {
  return (
    <>
      <div className="businessCaseTableWrap">
        <table className="businessCaseEvidenceTable">
          <thead>
            <tr>
              <th>Case</th>
              <th>Source module</th>
              <th>ID / Version</th>
              <th>Hash</th>
              <th>Readiness</th>
              <th>Current</th>
              <th>As-of</th>
              <th>Blocking</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.map((source, index) => {
                const route = sourceRoute(source);
                const qra =
                  route === "qra-run-overview" || source.analysis_type ? qraSourceSummary(source, revision) : null;
                const rawQraRow = qra ? asRecord(source) : {};
                const qraHref = qra ? qraEvidenceSourceHref(qra) : undefined;
                const sourceId = qra
                  ? asText(qra.run_number || qra.qra_run_number || qra.run_id || source.source_id, "—")
                  : (source.source_id ?? "—");
                const sourceVersion = qra
                  ? asText(qra.model_version ?? qra.version ?? source.source_version_id ?? rawQraRow.version, "—")
                  : (source.source_version_id ?? "—");
                const sourceHash = qra
                  ? asText(
                      source.source_hash || rawQraRow.hash || qra.evidence_hash || qra.acceptance_hash || qra.run_hash,
                      ""
                    )
                  : source.source_hash;
                const sourceReadiness = qra
                  ? asText(
                      source.source_readiness ||
                        rawQraRow.readiness ||
                        qra.readiness ||
                        qra.analytical_readiness ||
                        source.source_status,
                      "NOT_AVAILABLE"
                    )
                  : source.source_readiness || source.source_status || "NOT_AVAILABLE";
                const qraCurrent =
                  source.source_current === false || qra?.source_current === false || qra?.current === false
                    ? false
                    : source.source_current === true || qra?.source_current === true || qra?.current === true
                      ? true
                      : undefined;
                const sourceCurrent = qra
                  ? qraCurrent === false
                    ? "STALE"
                    : qraCurrent === true
                      ? "CURRENT"
                      : "NOT EVALUATED"
                  : source.source_current === false
                    ? "STALE"
                    : "CURRENT";
                const sourceAsOf = qra
                  ? asText(source.as_of_date || qra.as_of_date || qra.as_of, "")
                  : source.as_of_date;
                return (
                  <tr key={`${source.case}-${source.source_module}-${source.source_id}-${index}`}>
                    <td>{source.case ? sourceName(source.case) : "Cross-case"}</td>
                    <td>{sourceName(source.source_module || "Unknown source")}</td>
                    <td>
                      {sourceId} / {sourceVersion}
                    </td>
                    <td title={sourceHash || undefined}>{sourceHash?.slice(0, 12) || "—"}</td>
                    <td>{sourceReadiness}</td>
                    <td>{sourceCurrent}</td>
                    <td>{readableDate(sourceAsOf)}</td>
                    <td>{source.blocking ? "YES" : "NO"}</td>
                    <td>
                      {qraHref ? (
                        <a
                          aria-label={`View Source ${sourceName(source.source_module || "Unknown source")}`}
                          href={qraHref}
                        >
                          <ExternalLink size={13} /> View Source
                        </a>
                      ) : (
                        <button
                          aria-label={`View Source ${sourceName(source.source_module || "Unknown source")}`}
                          disabled={!route || !onNavigate}
                          onClick={() => route && onNavigate?.(route)}
                          type="button"
                        >
                          <ExternalLink size={13} /> View Source
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={9}>No governed source evidence is available for this revision.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="businessCaseQraSources">
        {rows
          .filter((source) => source.analysis_type || String(source.source_module).toUpperCase().includes("QRA"))
          .map((source, index) => {
            const summary = qraSourceSummary(source, revision);
            return (
              <QraEvidenceSummary
                key={`${source.source_id}-${index}`}
                summary={summary}
                applicability={asRecord(summary.qra_applicability || summary.applicability)}
                onView={onNavigate ? () => onNavigate("qra-run-overview") : undefined}
              />
            );
          })}
      </div>
    </>
  );
}

function DataList({ empty, title, value }: { empty: string; title: string; value: unknown }) {
  const rows = asList(value);
  return (
    <article className="businessCaseDetailCard">
      <h4>{title}</h4>
      {rows.length ? <pre>{JSON.stringify(value, null, 2)}</pre> : <p>{empty}</p>}
    </article>
  );
}

function FiveCasePanel({
  onNavigate,
  revision,
  sources,
  view,
}: {
  onNavigate?: (view: ControlFlowView) => void;
  revision: BusinessCaseRevision;
  sources: BusinessCaseSourceEvidence[];
  view: CaseView;
}) {
  const definition = CASE_DEFINITIONS[view];
  const model = fiveCaseModel(revision);
  const persisted = model[definition.key];
  const payload = persisted || legacyCasePayload(revision, view);
  const evidence = sourcesForCase(sources, view);
  const warnings = payload.warnings || [];
  const blockers = payload.blockers || [];
  return (
    <div className="businessCaseCaseLayout">
      <article className="businessCaseQuestion">
        <span>Case question</span>
        <h4>{payload.question || definition.question}</h4>
        <p>{payload.summary || "No governed synthesis is available for this Case."}</p>
        {!persisted ? <small>Legacy compatibility layout · source data remains read-only</small> : null}
      </article>
      <div className="businessCaseReadinessBanner" data-readiness={caseReadiness(revision, view, payload)}>
        <span>Case readiness</span>
        <b>{caseReadiness(revision, view, payload)}</b>
      </div>
      <DataList
        empty="No governed findings recorded."
        title="Key findings"
        value={payload.key_findings ?? payload.findings}
      />
      <DataList empty="No Case-specific assumptions recorded." title="Assumptions" value={payload.assumptions} />
      <article className="businessCaseDetailCard">
        <h4>Warnings</h4>
        {warnings.length ? (
          <ul>
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        ) : (
          <p>None</p>
        )}
      </article>
      <article className="businessCaseDetailCard blockerCard">
        <h4>Blockers</h4>
        {blockers.length ? (
          <ul>
            {blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        ) : (
          <p>None</p>
        )}
      </article>
      <article className="businessCaseConclusion">
        <span>Case conclusion</span>
        <p>{payload.case_conclusion || payload.conclusion || "Not concluded"}</p>
      </article>
      <section className="businessCaseCaseEvidence" aria-label={`${labels[view]} source evidence`}>
        <h4>Key source evidence</h4>
        <EvidenceTable onNavigate={onNavigate} revision={revision} rows={evidence} />
      </section>
    </div>
  );
}

export default function BusinessCaseWorkspace({
  token,
  initialView,
  onNavigate,
}: {
  token: string;
  initialView?: string;
  onNavigate?: (view: ControlFlowView) => void;
}) {
  const [view, setView] = useState<View>(VIEW_BY_ROUTE[initialView || ""] || "overview");
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
  const sources = useMemo(() => (revision ? normalizedSources(revision) : []), [revision]);

  const metrics = useMemo(
    () => [
      { label: "Business Cases", value: records.length },
      { label: "Ready", value: records.filter((item) => item.final_output.startsWith("READY_")).length },
      {
        label: "Five Case",
        value: revision?.legacy_layout === false || revision?.five_case_json ? "Structured" : "Legacy compatible",
      },
      {
        label: "Source current",
        value: readiness?.source_current === false || revision?.source_current === false ? "STALE" : "CURRENT",
      },
    ],
    [records, revision, readiness]
  );

  async function load(preferredId?: number) {
    const rows = await businessCaseApi.list(token);
    setRecords(rows);
    setSelectedId(preferredId || rows[0]?.id || 0);
  }

  useEffect(() => setView(VIEW_BY_ROUTE[initialView || ""] || "overview"), [initialView]);
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

  const caseStatuses = revision
    ? (Object.keys(CASE_DEFINITIONS) as CaseView[]).map((caseView) => {
        const definition = CASE_DEFINITIONS[caseView];
        const payload = fiveCaseModel(revision)[definition.key] || legacyCasePayload(revision, caseView);
        return { label: labels[caseView], status: caseReadiness(revision, caseView, payload) };
      })
    : [];

  return (
    <section aria-label="Business Case Manager" className="businessCase">
      <CompactModuleHeader
        description="Longitudinal governed Business Case with Five Case synthesis, source lineage, policy-owned readiness and immutable decision snapshots."
        eyebrow="USER MODE · ENTERPRISE STRATEGY MANAGER · GATE 07M-BC-5C"
        metrics={metrics}
        title="Business Case Manager"
      />
      {message ? (
        <div className="businessCaseMessage" role="status">
          {message}
        </div>
      ) : null}
      <nav aria-label="Business Case views" className="businessCaseTabs userTabs">
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
          {view === "overview" ? (
            <>
              <div className="businessCaseFacts">
                <article>
                  <span>Business Case / revision</span>
                  <b>
                    {selected.business_case_number} · {revision.revision_label}
                  </b>
                </article>
                <article>
                  <span>Purpose / project</span>
                  <b>
                    {revision.purpose}
                    <br />
                    Project {selected.project_workspace_id}
                  </b>
                </article>
                <article>
                  <span>FEL / Gate context</span>
                  <b>
                    {revision.fel_stage_code || "NOT_AVAILABLE"}
                    <br />
                    {asText(revision.gate_context_json?.gate_profile)}
                  </b>
                </article>
                <article>
                  <span>Overall readiness</span>
                  <b>{readiness?.status || revision.readiness_status}</b>
                </article>
                <article>
                  <span>Source-current</span>
                  <b>
                    {readiness?.source_current === false || revision.source_current === false ? "STALE" : "CURRENT"}
                  </b>
                </article>
                <article>
                  <span>Material change</span>
                  <b>{revision.material_change_status}</b>
                </article>
                <article>
                  <span>Decision snapshots</span>
                  <b>{snapshots.length}</b>
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
              <section aria-label="Five Case readiness summary" className="businessCaseReadinessGrid">
                {caseStatuses.map((item) => (
                  <article key={item.label}>
                    <span>{item.label}</span>
                    <b>{item.status}</b>
                  </article>
                ))}
              </section>
              <details className="businessCaseRevisionEditor" open={revision.status === "DRAFT"}>
                <summary>Revision narrative</summary>
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
                      rows={4}
                      value={editor.executive_summary}
                      onChange={(event) => setEditor({ ...editor, executive_summary: event.target.value })}
                    />
                  </label>
                  <label>
                    Business need
                    <textarea
                      disabled={revision.status !== "DRAFT"}
                      rows={4}
                      value={editor.business_need}
                      onChange={(event) => setEditor({ ...editor, business_need: event.target.value })}
                    />
                  </label>
                </div>
              </details>
            </>
          ) : ["strategic", "economic", "commercial", "financial", "management"].includes(view) ? (
            <FiveCasePanel onNavigate={onNavigate} revision={revision} sources={sources} view={view as CaseView} />
          ) : view === "sources" ? (
            <section aria-label="Sources and Evidence matrix">
              <p className="businessCaseReadOnlyNotice">
                Governed source records are read-only in Business Case Manager. IDs, versions and hashes preserve
                lineage.
              </p>
              <EvidenceTable onNavigate={onNavigate} revision={revision} rows={sources} />
            </section>
          ) : view === "readiness" ? (
            <div className="businessCaseReadinessView">
              <section className="businessCaseReadinessGrid">
                {caseStatuses.map((item) => (
                  <article key={item.label}>
                    <span>{item.label}</span>
                    <b>{item.status}</b>
                  </article>
                ))}
                <article>
                  <span>Overall Business Case</span>
                  <b>{readiness?.status || revision.readiness_status}</b>
                </article>
              </section>
              <DataList
                empty="No readiness warnings."
                title="Warnings"
                value={readiness?.warnings || revision.readiness_warnings_json}
              />
              <DataList
                empty="No readiness blockers."
                title="Blockers"
                value={readiness?.blockers || revision.readiness_blockers_json}
              />
              <article className="businessCaseConclusion">
                <span>Source current</span>
                <p>{readiness?.source_current === false ? "STALE · revalidation required" : "CURRENT"}</p>
              </article>
            </div>
          ) : view === "snapshots" ? (
            <div className="businessCaseSnapshotList">
              {snapshots.length ? (
                snapshots.map((snapshot) => (
                  <article key={snapshot.id}>
                    <b>{snapshot.snapshot_type}</b>
                    <span>{readableDate(snapshot.created_at)}</span>
                    <code>{snapshot.snapshot_hash}</code>
                    <details>
                      <summary>Frozen evidence</summary>
                      <pre>{JSON.stringify(snapshot.snapshot_json, null, 2)}</pre>
                    </details>
                  </article>
                ))
              ) : (
                <p>No immutable decision snapshots have been captured.</p>
              )}
            </div>
          ) : (
            <div className="businessCaseHistoryList">
              {revisions.map((item) => (
                <article key={item.id}>
                  <b>
                    {item.revision_label} · {item.purpose}
                  </b>
                  <span>
                    {item.status} · {readableDate(item.as_of_date)}
                  </span>
                  <code>{item.content_hash}</code>
                </article>
              ))}
            </div>
          )}
        </section>
      ) : null}

      {preview ? (
        <section className="businessCaseSurface">
          <h3>Refresh preview · persisted=false</h3>
          <p>
            Source hash, readiness and Five Case deltas are recommendations only until a successor DRAFT is created.
          </p>
          <pre>{JSON.stringify(preview, null, 2)}</pre>
        </section>
      ) : null}
      <p className="businessCaseGuardrail">
        <AlertTriangle size={15} /> Integration-only boundary: source records stay read-only; this module does not
        recalculate FIN metrics, execute procurement, issue FID or mutate the Project lifecycle.
      </p>
    </section>
  );
}
