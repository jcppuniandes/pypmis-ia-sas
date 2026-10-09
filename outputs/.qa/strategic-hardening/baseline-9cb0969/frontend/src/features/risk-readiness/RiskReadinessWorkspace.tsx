/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { AlertTriangle, ClipboardCheck, History, RefreshCw, ShieldCheck, Target } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import type { PortfolioProject } from "../portfolio-planning/types";
import { riskReadinessApi } from "./api";
import "./riskReadiness.css";
import type { PortfolioReadiness, ProjectReadiness, ProjectRisk, RiskAssessment } from "./types";

type RiskView = "mine" | "portfolio" | "register" | "assessments" | "treatments" | "residual" | "dashboard" | "history";
type RiskFilter =
  | "ALL"
  | "OPEN"
  | "HIGH_CRITICAL"
  | "NO_OWNER"
  | "NO_TREATMENT"
  | "OVERDUE"
  | "NEEDS_ACCEPTANCE"
  | "EXPIRED_EVIDENCE";

const VIEW_BY_ROUTE: Record<string, RiskView> = {
  "risk-readiness-my": "mine",
  "risk-readiness-portfolio": "portfolio",
  "risk-readiness-register": "register",
  "risk-readiness-assessments": "assessments",
  "risk-readiness-treatments": "treatments",
  "risk-readiness-residual": "residual",
  "risk-readiness-dashboard": "dashboard",
  "risk-readiness-history": "history",
};

const labels: Record<RiskView, string> = {
  mine: "My Risk Work",
  portfolio: "Project Set Readiness",
  register: "Project Risk Register",
  assessments: "Risk Assessments",
  treatments: "Treatments",
  residual: "Residual & Acceptance",
  dashboard: "Risk Readiness Dashboard",
  history: "History / Audit",
};

const filterLabels: Record<RiskFilter, string> = {
  ALL: "All",
  OPEN: "Open",
  HIGH_CRITICAL: "High / Critical",
  NO_OWNER: "No Owner",
  NO_TREATMENT: "No Treatment",
  OVERDUE: "Overdue",
  NEEDS_ACCEPTANCE: "Needs Acceptance",
  EXPIRED_EVIDENCE: "Expired Evidence",
};

const today = () => new Date().toISOString().slice(0, 10);

export default function RiskReadinessWorkspace({ token, initialView }: { token: string; initialView?: string }) {
  const [view, setView] = useState<RiskView>(VIEW_BY_ROUTE[initialView || ""] || "dashboard");
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [portfolioId, setPortfolioId] = useState(0);
  const [projects, setProjects] = useState<PortfolioProject[]>([]);
  const [projectId, setProjectId] = useState(0);
  const [risks, setRisks] = useState<ProjectRisk[]>([]);
  const [assessments, setAssessments] = useState<RiskAssessment[]>([]);
  const [projectReadiness, setProjectReadiness] = useState<ProjectReadiness | null>(null);
  const [portfolioReadiness, setPortfolioReadiness] = useState<PortfolioReadiness | null>(null);
  const [selectedRiskId, setSelectedRiskId] = useState(0);
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("ALL");
  const [message, setMessage] = useState("");
  const [title, setTitle] = useState("New project risk");
  const [category, setCategory] = useState("TECHNICAL");
  const [likelihood, setLikelihood] = useState(2);
  const [impact, setImpact] = useState(2);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [evidence, setEvidence] = useState<Record<string, unknown> | null>(null);

  useEffect(() => setView(VIEW_BY_ROUTE[initialView || ""] || "dashboard"), [initialView]);

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
      const portfolio = await riskReadinessApi.portfolioReadiness(token, portfolioId);
      setPortfolioReadiness(portfolio);
      if (projectId) {
        const [riskItems, assessmentItems, readiness] = await Promise.all([
          riskReadinessApi.risks(token, projectId),
          riskReadinessApi.assessments(token, projectId),
          riskReadinessApi.projectReadiness(token, projectId),
        ]);
        setRisks(riskItems);
        setAssessments(assessmentItems);
        setProjectReadiness(readiness);
        setSelectedRiskId((current) =>
          riskItems.some((item) => item.id === current) ? current : riskItems[0]?.id || 0
        );
      }
      if (clearMessage) setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load Risk Readiness");
    }
  }

  useEffect(() => void load(), [portfolioId, projectId]);

  const selectedRisk = useMemo(() => risks.find((item) => item.id === selectedRiskId) || null, [risks, selectedRiskId]);
  const filteredRisks = useMemo(() => risks.filter((item) => matchesRiskFilter(item, riskFilter)), [riskFilter, risks]);

  async function execute<T>(work: () => Promise<T>, success: string) {
    try {
      await work();
      await load(false);
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Risk action failed");
    }
  }

  const treatmentRows = risks.filter((item) => item.treatment_required);
  const residualRows = risks.filter((item) => item.residual_rating || item.residual_acceptance_required);

  return (
    <section aria-label="Risk Readiness" className="riskReadiness">
      <CompactModuleHeader
        description="Governs Project Risk, treatments, residual acceptance and current Risk Readiness evidence for Gate 07J. It does not implement ERM, Monte Carlo/QRA, Investment Decision, FID or Project activation."
        eyebrow="USER MODE · INVESTMENT GOVERNANCE · GATE 07J-RISK"
        metrics={[
          { label: "Active risks", value: projectReadiness?.active_risk_count || 0 },
          {
            label: "High / critical",
            value: `${projectReadiness?.high_count || 0} / ${projectReadiness?.critical_count || 0}`,
          },
          { label: "Readiness", value: portfolioReadiness?.readiness_status || "NOT STARTED" },
        ]}
        title="Risk Readiness"
      />

      <div className="riskToolbar">
        <nav aria-label="Risk Readiness views">
          {(Object.keys(labels) as RiskView[]).map((item) => (
            <button className={view === item ? "active" : ""} key={item} onClick={() => setView(item)} type="button">
              {labels[item]}
            </button>
          ))}
        </nav>
        <div className="riskSelectors">
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
        <div className="riskMessage" role="status">
          {message}
        </div>
      ) : null}

      {view === "dashboard" || view === "mine" ? (
        <>
          <section className={`riskHero ${portfolioReadiness?.readiness_status === "READY" ? "ready" : "blocked"}`}>
            <div>
              <span>Final controlled output</span>
              <h3>READY_FOR_GOVERNED_RISK_EVIDENCE</h3>
              <p>
                {portfolioReadiness?.coverage_percent || 0}% of the recommended Project Set has valid, current evidence.
              </p>
            </div>
            {portfolioReadiness?.readiness_status === "READY" ? <ShieldCheck size={40} /> : <AlertTriangle size={40} />}
          </section>
          <div className="riskMetricGrid">
            <article>
              <Target />
              <span>Required Projects</span>
              <strong>{portfolioReadiness?.required_project_count || 0}</strong>
            </article>
            <article>
              <ClipboardCheck />
              <span>Valid Projects</span>
              <strong>{portfolioReadiness?.valid_project_count || 0}</strong>
            </article>
            <article>
              <AlertTriangle />
              <span>Unaccepted residual</span>
              <strong>{portfolioReadiness?.aggregate_unaccepted_residual_count || 0}</strong>
            </article>
            <article>
              <History />
              <span>Stale / expired</span>
              <strong>
                {(portfolioReadiness?.stale_project_count || 0) + (portfolioReadiness?.expired_project_count || 0)}
              </strong>
            </article>
          </div>
          <IssueList blockers={portfolioReadiness?.blockers || []} warnings={portfolioReadiness?.warnings || []} />
        </>
      ) : null}

      {view === "portfolio" ? (
        <section className="riskSurface">
          <header>
            <div>
              <span>Recommended Project Set</span>
              <h3>Project readiness coverage</h3>
            </div>
            <strong>{portfolioReadiness?.coverage_percent || 0}%</strong>
          </header>
          <table>
            <thead>
              <tr>
                <th>Project</th>
                <th>Assessment Date</th>
                <th>High</th>
                <th>Critical</th>
                <th>No Owner</th>
                <th>No Treatment</th>
                <th>Overdue</th>
                <th>Residual Unaccepted</th>
                <th>Coverage</th>
                <th>Readiness</th>
              </tr>
            </thead>
            <tbody>
              {portfolioReadiness?.project_readiness.map((row) => (
                <tr key={row.project_workspace_id}>
                  <td>
                    {projects.find((item) => item.project_workspace_id === row.project_workspace_id)?.project_name ||
                      row.project_workspace_id}
                  </td>
                  <td>{row.as_of_date ? new Date(row.as_of_date).toLocaleDateString() : "Not assessed"}</td>
                  <td>{row.high_count}</td>
                  <td>{row.critical_count}</td>
                  <td>{row.unowned_high_critical_count}</td>
                  <td>{row.untreated_high_critical_count}</td>
                  <td>{row.overdue_treatment_count}</td>
                  <td>{row.unaccepted_residual_count}</td>
                  <td>{row.evidence_coverage}%</td>
                  <td>
                    <Status value={row.readiness_status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {view === "register" ? (
        <section className="riskSurface">
          <header>
            <div>
              <span>Project control source</span>
              <h3>Project Risk Register</h3>
            </div>
            <strong>{risks.length} risks</strong>
          </header>
          <form
            className="riskCreate"
            onSubmit={(event) => {
              event.preventDefault();
              void execute(
                () =>
                  riskReadinessApi.createRisk(token, projectId, {
                    title,
                    description: "",
                    risk_category: category,
                    identified_date: today(),
                    cause: "",
                    event: "",
                    impact_description: "",
                    likelihood_before: likelihood,
                    impact_before: impact,
                    treatment_required: likelihood * impact >= 10,
                    residual_acceptance_required: false,
                    evidence_refs: [{ type: "REGISTER_ENTRY", date: today() }],
                  }),
                "Risk created with controlled identifier."
              );
            }}
          >
            <label>
              Title
              <input value={title} onChange={(event) => setTitle(event.target.value)} />
            </label>
            <label>
              Category
              <select value={category} onChange={(event) => setCategory(event.target.value)}>
                {["TECHNICAL", "SCOPE", "SCHEDULE", "COST", "COMMERCIAL", "PERMITTING", "HSE", "OTHER"].map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label>
              Likelihood
              <input
                min={1}
                max={5}
                type="number"
                value={likelihood}
                onChange={(event) => setLikelihood(Number(event.target.value))}
              />
            </label>
            <label>
              Impact
              <input
                min={1}
                max={5}
                type="number"
                value={impact}
                onChange={(event) => setImpact(Number(event.target.value))}
              />
            </label>
            <button disabled={!projectId} type="submit">
              Create risk
            </button>
          </form>
          <div aria-label="Risk Register filters" className="riskFilters" role="group">
            {(Object.keys(filterLabels) as RiskFilter[]).map((item) => (
              <button
                aria-pressed={riskFilter === item}
                className={riskFilter === item ? "active" : ""}
                key={item}
                onClick={() => setRiskFilter(item)}
                type="button"
              >
                {filterLabels[item]}
              </button>
            ))}
          </div>
          <div className="riskSplit">
            <div className="riskTableWrap">
              <table>
                <thead>
                  <tr>
                    <th>Risk Number</th>
                    <th>Title</th>
                    <th>Category</th>
                    <th>Status</th>
                    <th>Owner</th>
                    <th>Inherent Rating</th>
                    <th>Treatment</th>
                    <th>Residual Rating</th>
                    <th>Acceptance</th>
                    <th>Due Date</th>
                    <th>Evidence</th>
                    <th>Warnings</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRisks.map((item) => (
                    <tr
                      className={selectedRiskId === item.id ? "selected" : ""}
                      key={item.id}
                      onClick={() => setSelectedRiskId(item.id)}
                    >
                      <td>{item.risk_number}</td>
                      <td>{item.title}</td>
                      <td>{item.risk_category}</td>
                      <td>{item.status}</td>
                      <td>{item.risk_owner_id || "Unassigned"}</td>
                      <td>
                        <Status value={item.inherent_rating || "NOT RATED"} />
                      </td>
                      <td>{item.treatment_status || "—"}</td>
                      <td>{item.residual_rating || "—"}</td>
                      <td>{item.accepted_at ? "Accepted" : item.residual_acceptance_required ? "Required" : "N/A"}</td>
                      <td>{item.due_date || item.target_treatment_date || "—"}</td>
                      <td>{item.evidence_refs_json.length}</td>
                      <td>{riskWarnings(item).join(" · ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <RiskDetail risk={selectedRisk} token={token} execute={execute} />
          </div>
        </section>
      ) : null}

      {view === "assessments" ? (
        <section className="riskSurface">
          <header>
            <div>
              <span>Versioned and immutable on completion</span>
              <h3>Risk Readiness Assessments</h3>
            </div>
            <button
              disabled={!projectId}
              onClick={() =>
                void execute(() => riskReadinessApi.startAssessment(token, projectId), "Assessment started.")
              }
              type="button"
            >
              Start assessment
            </button>
          </header>
          <table>
            <thead>
              <tr>
                <th>Assessment</th>
                <th>Version</th>
                <th>Status</th>
                <th>Readiness</th>
                <th>Active</th>
                <th>High</th>
                <th>Critical</th>
                <th>Valid until</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {assessments.map((item) => (
                <tr key={item.id}>
                  <td>{item.assessment_number}</td>
                  <td>{item.assessment_version}</td>
                  <td>{item.status}</td>
                  <td>
                    <Status value={item.readiness_status} />
                  </td>
                  <td>{item.total_active_risks}</td>
                  <td>{item.high_risk_count}</td>
                  <td>{item.critical_risk_count}</td>
                  <td>{new Date(item.valid_until).toLocaleDateString()}</td>
                  <td>
                    {item.status === "IN_PROGRESS" ? (
                      <button
                        onClick={() =>
                          void execute(
                            () => riskReadinessApi.completeAssessment(token, item),
                            "Assessment completed and frozen."
                          )
                        }
                        type="button"
                      >
                        Complete
                      </button>
                    ) : (
                      "Immutable"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <IssueList blockers={projectReadiness?.blockers || []} warnings={projectReadiness?.warnings || []} />
        </section>
      ) : null}

      {view === "treatments" ? <RiskRows title="Treatment control" rows={treatmentRows} mode="treatment" /> : null}
      {view === "residual" ? <RiskRows title="Residual & Acceptance" rows={residualRows} mode="residual" /> : null}

      {view === "history" ? (
        <section className="riskSurface">
          <header>
            <div>
              <span>Current-source control</span>
              <h3>History / Audit</h3>
            </div>
            <button
              onClick={() => void riskReadinessApi.refreshPreview(token, projectId).then(setPreview)}
              type="button"
            >
              <RefreshCw size={16} /> Refresh preview
            </button>
          </header>
          <p>
            Completed assessments are immutable. Changes in risks or the published configuration make the evidence STALE
            until a governed reassessment is completed.
          </p>
          {preview ? <pre>{JSON.stringify(preview, null, 2)}</pre> : null}
          <button onClick={() => void riskReadinessApi.evidence(token, portfolioId).then(setEvidence)} type="button">
            View Gate 07J evidence contract
          </button>
          {evidence ? <pre>{JSON.stringify(evidence, null, 2)}</pre> : null}
        </section>
      ) : null}

      <p className="riskBoundary">
        GATE07J_RISK_RELEASE_VALIDATED · Provider: RISK_READINESS_PROVIDER · can_enter_fid=false
      </p>
    </section>
  );
}

function Status({ value }: { value: string }) {
  return <span className={`riskStatus ${value.toLowerCase().replace(/_/g, "-")}`}>{value}</span>;
}

function riskWarnings(risk: ProjectRisk) {
  const warnings: string[] = [];
  if (["HIGH", "CRITICAL"].includes(risk.inherent_rating || "") && !risk.risk_owner_id) warnings.push("No owner");
  if (
    risk.treatment_required &&
    !(risk.treatment_strategy && risk.treatment_description && risk.treatment_owner_id && risk.target_treatment_date)
  )
    warnings.push("No treatment");
  if (
    risk.target_treatment_date &&
    risk.target_treatment_date < today() &&
    !["COMPLETED", "CANCELLED"].includes(risk.treatment_status || "")
  )
    warnings.push("Overdue");
  if (risk.residual_acceptance_required && !risk.accepted_at) warnings.push("Needs acceptance");
  if (hasExpiredEvidence(risk)) warnings.push("Expired evidence");
  return warnings;
}

function hasExpiredEvidence(risk: ProjectRisk) {
  return risk.evidence_refs_json.some((item) => {
    const validUntil = item.valid_until;
    return typeof validUntil === "string" && validUntil.slice(0, 10) < today();
  });
}

function matchesRiskFilter(risk: ProjectRisk, filter: RiskFilter) {
  const warnings = riskWarnings(risk);
  if (filter === "ALL") return true;
  if (filter === "OPEN") return !["CLOSED", "VOIDED"].includes(risk.status);
  if (filter === "HIGH_CRITICAL") return ["HIGH", "CRITICAL"].includes(risk.inherent_rating || "");
  if (filter === "NO_OWNER") return warnings.includes("No owner");
  if (filter === "NO_TREATMENT") return warnings.includes("No treatment");
  if (filter === "OVERDUE") return warnings.includes("Overdue");
  if (filter === "NEEDS_ACCEPTANCE") return warnings.includes("Needs acceptance");
  return warnings.includes("Expired evidence");
}

function IssueList({ blockers, warnings }: { blockers: string[]; warnings: string[] }) {
  if (!blockers.length && !warnings.length)
    return (
      <p className="riskClear">
        <ShieldCheck size={16} /> No readiness gaps in the current source.
      </p>
    );
  return (
    <div className="riskIssues">
      {blockers.map((item) => (
        <span className="blocker" key={item}>
          {item}
        </span>
      ))}
      {warnings.map((item) => (
        <span className="warning" key={item}>
          {item}
        </span>
      ))}
    </div>
  );
}

function RiskRows({ title, rows, mode }: { title: string; rows: ProjectRisk[]; mode: "treatment" | "residual" }) {
  return (
    <section className="riskSurface">
      <header>
        <div>
          <span>Governed Project Risk</span>
          <h3>{title}</h3>
        </div>
        <strong>{rows.length} items</strong>
      </header>
      <table>
        <thead>
          <tr>
            <th>Risk</th>
            <th>Owner</th>
            <th>{mode === "treatment" ? "Strategy" : "Residual"}</th>
            <th>{mode === "treatment" ? "Treatment status" : "Acceptance"}</th>
            <th>Due</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((item) => (
            <tr key={item.id}>
              <td>
                {item.risk_number} · {item.title}
              </td>
              <td>
                {mode === "treatment" ? item.treatment_owner_id || "Unassigned" : item.risk_owner_id || "Unassigned"}
              </td>
              <td>
                {mode === "treatment" ? (
                  item.treatment_strategy || "Not defined"
                ) : (
                  <Status value={item.residual_rating || "NOT RATED"} />
                )}
              </td>
              <td>
                {mode === "treatment" ? item.treatment_status || "OPEN" : item.accepted_at ? "Accepted" : "Pending"}
              </td>
              <td>{item.target_treatment_date || item.due_date || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function RiskDetail({
  risk,
  token,
  execute,
}: {
  risk: ProjectRisk | null;
  token: string;
  execute: <T>(work: () => Promise<T>, success: string) => Promise<void>;
}) {
  if (!risk)
    return (
      <aside className="riskDetail">
        <p>Select a risk to inspect its source, treatment and residual controls.</p>
      </aside>
    );
  const payload = {
    title: risk.title,
    description: risk.description,
    risk_category: risk.risk_category,
    identified_date: risk.identified_date,
    risk_owner_id: risk.risk_owner_id,
    cause: risk.cause,
    event: risk.event,
    impact_description: risk.impact_description,
    likelihood_before: risk.likelihood_before,
    impact_before: risk.impact_before,
    treatment_required: true,
    treatment_strategy: risk.treatment_strategy || "REDUCE",
    treatment_description: risk.treatment_description || "Controlled mitigation action",
    treatment_owner_id: risk.treatment_owner_id,
    target_treatment_date: risk.target_treatment_date || today(),
    treatment_status: risk.treatment_status || "IN_PROGRESS",
    likelihood_after: risk.likelihood_after || 2,
    impact_after: risk.impact_after || 2,
    residual_acceptance_required: risk.residual_acceptance_required,
    due_date: risk.due_date,
    source_reference: risk.source_reference,
    evidence_refs: risk.evidence_refs_json,
  };
  return (
    <aside className="riskDetail">
      <span>{risk.risk_number}</span>
      <h3>{risk.title}</h3>
      <p>
        {risk.cause || "No cause documented"} → {risk.event || "No event documented"} →{" "}
        {risk.impact_description || "No impact documented"}
      </p>
      <dl>
        <dt>Inherent</dt>
        <dd>{risk.inherent_rating || "Not rated"}</dd>
        <dt>Treatment</dt>
        <dd>{risk.treatment_description || "Not defined"}</dd>
        <dt>Residual</dt>
        <dd>{risk.residual_rating || "Not assessed"}</dd>
        <dt>Evidence</dt>
        <dd>{risk.evidence_refs_json.length} reference(s)</dd>
      </dl>
      {!["CLOSED", "VOIDED"].includes(risk.status) ? (
        <button
          onClick={() =>
            void execute(
              () => riskReadinessApi.updateRisk(token, risk, payload),
              "Treatment and residual assessment updated."
            )
          }
          type="button"
        >
          Prepare treatment
        </button>
      ) : null}
      {risk.residual_acceptance_required && !risk.accepted_at ? (
        <button
          onClick={() =>
            void execute(
              () =>
                riskReadinessApi.acceptResidual(
                  token,
                  risk,
                  "Residual risk reviewed and accepted.",
                  "EXECUTIVE_SPONSOR"
                ),
              "Residual risk accepted with authority."
            )
          }
          type="button"
        >
          Accept residual
        </button>
      ) : null}
    </aside>
  );
}
