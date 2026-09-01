/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { AlertTriangle, BadgeCheck, ClipboardList, FileCheck2, History, RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import type { PortfolioProject } from "../portfolio-planning/types";
import { permitReadinessApi } from "./api";
import "./permitReadiness.css";
import type {
  PermitAssessment,
  PermitCondition,
  ProjectPermit,
  ProjectPermitReadiness,
  ProjectSetPermitReadiness,
} from "./types";

type PermitView = "mine" | "register" | "requirements" | "conditions" | "project" | "portfolio" | "history";
type PermitFilter = "ALL" | "MISSING" | "IN_PROCESS" | "CONDITIONAL" | "EXPIRING" | "BLOCKED";

const VIEW_BY_ROUTE: Record<string, PermitView> = {
  "permit-readiness-my": "mine",
  "permit-readiness-register": "register",
  "permit-readiness-requirements": "requirements",
  "permit-readiness-conditions": "conditions",
  "permit-readiness-project": "project",
  "permit-readiness-portfolio": "portfolio",
  "permit-readiness-history": "history",
};

const labels: Record<PermitView, string> = {
  mine: "My Permit Work",
  register: "Project Permit Register",
  requirements: "Permit Requirements",
  conditions: "Permit Conditions",
  project: "Project Permit Readiness",
  portfolio: "Project Set Permit Readiness",
  history: "History / Audit",
};

const filterLabels: Record<PermitFilter, string> = {
  ALL: "All",
  MISSING: "Missing",
  IN_PROCESS: "In process",
  CONDITIONAL: "Conditional",
  EXPIRING: "Expiring",
  BLOCKED: "Blocked",
};

export default function PermitReadinessWorkspace({ token, initialView }: { token: string; initialView?: string }) {
  const [view, setView] = useState<PermitView>(VIEW_BY_ROUTE[initialView || ""] || "project");
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [portfolioId, setPortfolioId] = useState(0);
  const [projects, setProjects] = useState<PortfolioProject[]>([]);
  const [projectId, setProjectId] = useState(0);
  const [permits, setPermits] = useState<ProjectPermit[]>([]);
  const [assessments, setAssessments] = useState<PermitAssessment[]>([]);
  const [conditions, setConditions] = useState<PermitCondition[]>([]);
  const [projectReadiness, setProjectReadiness] = useState<ProjectPermitReadiness | null>(null);
  const [portfolioReadiness, setPortfolioReadiness] = useState<ProjectSetPermitReadiness | null>(null);
  const [selectedPermitId, setSelectedPermitId] = useState(0);
  const [filter, setFilter] = useState<PermitFilter>("ALL");
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [evidence, setEvidence] = useState<Record<string, unknown> | null>(null);
  const [newType, setNewType] = useState("ENVIRONMENTAL_LICENSE");
  const [newRequirement, setNewRequirement] = useState("MINING_ENVIRONMENTAL_LICENSE");

  useEffect(() => setView(VIEW_BY_ROUTE[initialView || ""] || "project"), [initialView]);
  useEffect(() => {
    void portfolioPlanningApi.portfolioOptions(token).then((items) => {
      setPortfolios(items);
      setPortfolioId((current) => current || Number(items[0]?.id || 0));
    });
  }, [token]);
  useEffect(() => {
    if (!portfolioId) return;
    void portfolioPlanningApi.portfolioProjects(token, portfolioId).then((items) => {
      setProjects(items);
      setProjectId((current) =>
        items.some((item) => item.project_workspace_id === current) ? current : items[0]?.project_workspace_id || 0
      );
    });
  }, [portfolioId]);

  async function load(clearMessage = true) {
    if (!portfolioId) return;
    try {
      setPortfolioReadiness(await permitReadinessApi.portfolioReadiness(token, portfolioId));
      if (projectId) {
        const [permitRows, assessmentRows, readiness] = await Promise.all([
          permitReadinessApi.permits(token, projectId),
          permitReadinessApi.assessments(token, projectId),
          permitReadinessApi.projectReadiness(token, projectId),
        ]);
        setPermits(permitRows);
        setAssessments(assessmentRows);
        setProjectReadiness(readiness);
        const selected = permitRows.some((item) => item.id === selectedPermitId)
          ? selectedPermitId
          : permitRows[0]?.id || 0;
        setSelectedPermitId(selected);
        setConditions(selected ? await permitReadinessApi.conditions(token, selected) : []);
      }
      if (clearMessage) setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load Permit Readiness");
    }
  }

  useEffect(() => void load(), [portfolioId, projectId]);
  useEffect(() => {
    if (!selectedPermitId) return setConditions([]);
    void permitReadinessApi
      .conditions(token, selectedPermitId)
      .then(setConditions)
      .catch(() => setConditions([]));
  }, [selectedPermitId]);

  async function execute<T>(work: () => Promise<T>, success: string) {
    try {
      await work();
      await load(false);
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Permit action failed");
    }
  }

  const filteredPermits = useMemo(() => permits.filter((item) => matchesFilter(item, filter)), [permits, filter]);
  const selectedPermit = permits.find((item) => item.id === selectedPermitId) || null;
  const latestActive = assessments.find((item) => ["DRAFT", "IN_PROGRESS"].includes(item.status));

  return (
    <section aria-label="Permit Readiness" className="permitReadiness">
      <CompactModuleHeader
        description="Governs configured permit requirements, Project permits, normalized conditions and current Permit Readiness evidence for Gate 07J. It does not determine legal requirements, file with authorities, create FID or activate Projects."
        eyebrow="USER MODE · INVESTMENT GOVERNANCE · GATE 07J-PERMIT"
        metrics={[
          { label: "Required permits", value: projectReadiness?.required_count || 0 },
          {
            label: "Approved / conditional",
            value: `${projectReadiness?.approved_count || 0} / ${projectReadiness?.conditional_count || 0}`,
          },
          { label: "Readiness", value: portfolioReadiness?.readiness_status || "NOT STARTED" },
        ]}
        title="Permit Readiness"
      />

      <div className="permitToolbar">
        <nav aria-label="Permit Readiness views">
          {(Object.keys(labels) as PermitView[]).map((item) => (
            <button className={view === item ? "active" : ""} key={item} onClick={() => setView(item)} type="button">
              {labels[item]}
            </button>
          ))}
        </nav>
        <div className="permitSelectors">
          <label>
            Portfolio
            <select value={portfolioId} onChange={(event) => setPortfolioId(Number(event.target.value))}>
              {portfolios.map((item) => (
                <option key={Number(item.id)} value={Number(item.id)}>
                  {String(item.name)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Project
            <select value={projectId} onChange={(event) => setProjectId(Number(event.target.value))}>
              {projects.map((item) => (
                <option key={item.project_workspace_id} value={item.project_workspace_id}>
                  {item.project_name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {message ? (
        <div className="permitMessage" role="status">
          {message}
        </div>
      ) : null}

      {view === "mine" || view === "project" ? (
        <>
          <section className={`permitHero ${projectReadiness?.readiness_status === "READY" ? "ready" : "blocked"}`}>
            <div>
              <span>Final controlled output</span>
              <h3>READY_FOR_GOVERNED_PERMIT_EVIDENCE</h3>
              <p>
                Classification {projectReadiness?.permit_classification || "—"} ·{" "}
                {projectReadiness?.evidence_coverage_percent || 0}% evidence coverage · source{" "}
                {projectReadiness?.source_current ? "current" : "not current"}.
              </p>
            </div>
            {projectReadiness?.readiness_status === "READY" ? <ShieldCheck size={40} /> : <AlertTriangle size={40} />}
          </section>
          <div className="permitMetricGrid">
            <Metric icon={<ClipboardList />} label="Required" value={projectReadiness?.required_count || 0} />
            <Metric icon={<BadgeCheck />} label="Approved" value={projectReadiness?.approved_count || 0} />
            <Metric icon={<FileCheck2 />} label="Conditional" value={projectReadiness?.conditional_count || 0} />
            <Metric
              icon={<AlertTriangle />}
              label="Missing / blocked"
              value={(projectReadiness?.missing_count || 0) + (projectReadiness?.open_blocking_conditions || 0)}
            />
          </div>
          <IssueList blockers={projectReadiness?.blockers || []} warnings={projectReadiness?.warnings || []} />
          <div className="permitActions">
            <button
              onClick={() => execute(() => permitReadinessApi.startAssessment(token, projectId), "Assessment started.")}
              type="button"
            >
              Start assessment
            </button>
            <button
              disabled={!latestActive}
              onClick={() =>
                latestActive &&
                execute(
                  () => permitReadinessApi.completeAssessment(token, latestActive),
                  "Assessment completed and frozen."
                )
              }
              type="button"
            >
              Complete assessment
            </button>
            <button
              onClick={() =>
                permitReadinessApi
                  .refreshPreview(token, projectId)
                  .then(setPreview)
                  .catch((error) => setMessage(String(error)))
              }
              type="button"
            >
              <RefreshCw size={15} /> Refresh preview
            </button>
          </div>
          {preview ? <JsonPanel title="Non-persistent refresh preview" value={preview} /> : null}
        </>
      ) : null}

      {view === "register" ? (
        <section className="permitSurface">
          <header>
            <div>
              <span>Project source</span>
              <h3>Permit register</h3>
            </div>
            <strong>{filteredPermits.length}</strong>
          </header>
          <div className="permitFilterBar">
            {(Object.keys(filterLabels) as PermitFilter[]).map((item) => (
              <button
                className={filter === item ? "active" : ""}
                key={item}
                onClick={() => setFilter(item)}
                type="button"
              >
                {filterLabels[item]}
              </button>
            ))}
          </div>
          <table>
            <thead>
              <tr>
                <th>Permit</th>
                <th>Type / requirement</th>
                <th>Authority</th>
                <th>Status</th>
                <th>Valid until</th>
                <th>Next action</th>
              </tr>
            </thead>
            <tbody>
              {filteredPermits.map((item) => (
                <tr
                  className={selectedPermitId === item.id ? "selected" : ""}
                  key={item.id}
                  onClick={() => setSelectedPermitId(item.id)}
                >
                  <td>
                    <strong>{item.permit_number}</strong>
                    <small>{item.title}</small>
                  </td>
                  <td>
                    {item.permit_type_code}
                    <small>{item.requirement_key || "Unmapped"}</small>
                  </td>
                  <td>{item.issuing_authority || "—"}</td>
                  <td>
                    <Status value={item.status} />
                  </td>
                  <td>{item.valid_until || "—"}</td>
                  <td>{item.next_action || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="permitCreate">
            <select value={newType} onChange={(event) => setNewType(event.target.value)}>
              <option>ENVIRONMENTAL_LICENSE</option>
              <option>MINING_TITLE_OR_RIGHT</option>
              <option>WATER_USE_PERMIT</option>
              <option>CONSTRUCTION_PERMIT</option>
              <option>OTHER</option>
            </select>
            <input
              value={newRequirement}
              onChange={(event) => setNewRequirement(event.target.value)}
              aria-label="Requirement key"
            />
            <button
              onClick={() =>
                execute(
                  () =>
                    permitReadinessApi.createPermit(token, projectId, {
                      permit_type_code: newType,
                      requirement_key: newRequirement || null,
                      title: newRequirement || "Configured permit",
                      description: "",
                      issuing_authority: "",
                      status: "NOT_STARTED",
                      evidence_refs: [],
                    }),
                  "Permit created."
                )
              }
              type="button"
            >
              + New permit
            </button>
          </div>
        </section>
      ) : null}

      {view === "requirements" ? (
        <section className="permitSurface">
          <header>
            <div>
              <span>Contextual applicability</span>
              <h3>Effective permit requirements</h3>
            </div>
            <Status value={`CLASS ${projectReadiness?.permit_classification || "—"}`} />
          </header>
          <table>
            <thead>
              <tr>
                <th>Requirement</th>
                <th>Permit type</th>
                <th>Mapped permit</th>
                <th>Evidence</th>
                <th>Readiness</th>
              </tr>
            </thead>
            <tbody>
              {uniqueRequirements(permits).map((item) => (
                <tr key={item.requirement_key || item.permit_type_code}>
                  <td>{item.requirement_key || "Unmapped"}</td>
                  <td>{item.permit_type_code}</td>
                  <td>{item.permit_number}</td>
                  <td>{item.evidence_refs_json.length ? "Referenced" : "Missing"}</td>
                  <td>
                    <Status value={item.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {view === "conditions" ? (
        <section className="permitSurface">
          <header>
            <div>
              <span>{selectedPermit?.permit_number || "Select a permit"}</span>
              <h3>Normalized permit conditions</h3>
            </div>
            <strong>{conditions.length}</strong>
          </header>
          <select
            className="permitSelectRow"
            value={selectedPermitId}
            onChange={(event) => setSelectedPermitId(Number(event.target.value))}
          >
            {permits.map((item) => (
              <option key={item.id} value={item.id}>
                {item.permit_number} · {item.title}
              </option>
            ))}
          </select>
          <table>
            <thead>
              <tr>
                <th>Condition</th>
                <th>Type</th>
                <th>Blocking</th>
                <th>Owner</th>
                <th>Target</th>
                <th>Status</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {conditions.map((item) => (
                <tr key={item.id}>
                  <td>
                    <strong>{item.condition_key}</strong>
                    <small>{item.description}</small>
                  </td>
                  <td>{item.condition_type}</td>
                  <td>{item.blocking ? "Yes" : "No"}</td>
                  <td>{item.owner_id || "—"}</td>
                  <td>{item.target_date || "—"}</td>
                  <td>
                    <Status value={item.status} />
                  </td>
                  <td>{item.evidence_refs_json.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {view === "portfolio" ? (
        <section className="permitSurface">
          <header>
            <div>
              <span>Recommended Project Set</span>
              <h3>Contextual Class A coverage</h3>
            </div>
            <strong>{portfolioReadiness?.coverage_percent || 0}%</strong>
          </header>
          <table>
            <thead>
              <tr>
                <th>Project</th>
                <th>Type</th>
                <th>Class</th>
                <th>Required</th>
                <th>Approved</th>
                <th>Missing</th>
                <th>Conditions</th>
                <th>Coverage</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {portfolioReadiness?.project_readiness.map((row) => (
                <tr key={row.project_workspace_id}>
                  <td>{projectName(projects, row.project_workspace_id)}</td>
                  <td>{row.project_type_code}</td>
                  <td>{row.permit_classification}</td>
                  <td>{row.required_count}</td>
                  <td>{row.approved_count + row.conditional_count}</td>
                  <td>{row.missing_count}</td>
                  <td>{row.open_blocking_conditions}</td>
                  <td>{row.evidence_coverage_percent}%</td>
                  <td>
                    <Status value={row.readiness_status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="permitActions">
            <button
              onClick={() =>
                permitReadinessApi
                  .evidence(token, portfolioId)
                  .then(setEvidence)
                  .catch((error) => setMessage(String(error)))
              }
              type="button"
            >
              Inspect Gate 07J evidence
            </button>
          </div>
          {evidence ? <JsonPanel title="Investment Gate permit evidence" value={evidence} /> : null}
        </section>
      ) : null}

      {view === "history" ? (
        <section className="permitSurface">
          <header>
            <div>
              <span>Immutable snapshots</span>
              <h3>Assessment history</h3>
            </div>
            <History />
          </header>
          <table>
            <thead>
              <tr>
                <th>Assessment</th>
                <th>Version</th>
                <th>Gate</th>
                <th>As of</th>
                <th>Valid until</th>
                <th>Required</th>
                <th>Coverage</th>
                <th>Readiness</th>
                <th>Hash</th>
              </tr>
            </thead>
            <tbody>
              {assessments.map((item) => (
                <tr key={item.id}>
                  <td>{item.assessment_number}</td>
                  <td>{item.assessment_version}</td>
                  <td>{item.gate_profile_code}</td>
                  <td>{item.as_of_date.slice(0, 10)}</td>
                  <td>{item.valid_until.slice(0, 10)}</td>
                  <td>{item.required_permit_count}</td>
                  <td>{item.evidence_coverage_percent}%</td>
                  <td>
                    <Status value={item.readiness_status} />
                  </td>
                  <td>
                    <code>{item.permit_readiness_hash?.slice(0, 12) || "draft"}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
    </section>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: number | string }) {
  return (
    <article>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
function Status({ value }: { value: string }) {
  return <span className={`permitStatus ${value.toLowerCase().split(" ").join("-")}`}>{value}</span>;
}
function IssueList({ blockers, warnings }: { blockers: string[]; warnings: string[] }) {
  return (
    <div className="permitIssues">
      <article>
        <strong>Blockers</strong>
        {blockers.length ? blockers.map((item) => <span key={item}>{item}</span>) : <span>None</span>}
      </article>
      <article>
        <strong>Warnings</strong>
        {warnings.length ? warnings.map((item) => <span key={item}>{item}</span>) : <span>None</span>}
      </article>
    </div>
  );
}
function JsonPanel({ title, value }: { title: string; value: Record<string, unknown> }) {
  return (
    <details className="permitJson">
      <summary>{title}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
function projectName(projects: PortfolioProject[], id: number) {
  return projects.find((item) => item.project_workspace_id === id)?.project_name || `Project ${id}`;
}
function uniqueRequirements(permits: ProjectPermit[]) {
  return [
    ...new Map(permits.map((item) => [item.requirement_key || `${item.permit_type_code}-${item.id}`, item])).values(),
  ];
}
function matchesFilter(item: ProjectPermit, filter: PermitFilter) {
  if (filter === "ALL") return true;
  if (filter === "MISSING") return item.status === "NOT_STARTED";
  if (filter === "IN_PROCESS") return ["IN_PREPARATION", "SUBMITTED", "UNDER_REVIEW"].includes(item.status);
  if (filter === "CONDITIONAL") return item.status === "APPROVED_WITH_CONDITIONS";
  if (filter === "BLOCKED") return ["REJECTED", "SUSPENDED", "EXPIRED"].includes(item.status);
  if (!item.valid_until) return false;
  const days = (new Date(item.valid_until).getTime() - Date.now()) / 86400000;
  return days >= 0 && days <= 90;
}
