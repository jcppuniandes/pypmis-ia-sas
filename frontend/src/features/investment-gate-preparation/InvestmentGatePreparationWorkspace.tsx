/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Archive, CheckCircle2, FileCheck2, RefreshCw, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import "../portfolio-planning/portfolioPlanning.css";
import { investmentGatePreparationApi } from "./api";
import type {
  CriterionEvaluationResult,
  InvestmentGateEvidence,
  InvestmentGateOverview,
  InvestmentGatePreparation,
  ProjectReadiness,
} from "./types";
import "./investmentGatePreparation.css";

type View = "preparations" | "matrix" | "evidence" | "projects" | "conditions" | "history";
const views: Array<[View, string]> = [
  ["preparations", "Preparations"],
  ["matrix", "Gate Matrix"],
  ["evidence", "Evidence Package"],
  ["projects", "Project Readiness"],
  ["conditions", "Conditions"],
  ["history", "History"],
];

const gate07mEvidence = new Set(["BUSINESS_CASE_READINESS", "ECONOMIC_FINANCIAL_READINESS"]);

const criterionTypeLabels: Record<string, string> = {
  READINESS_CHECK: "Readiness checks",
  MUST_MEET: "Must-meet criteria",
  DECISION_HURDLE: "Decision hurdles",
  PRIORITIZATION: "Portfolio context",
  SUCCESS_CRITERION: "Success criteria candidates",
};

function display(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "YES" : "NO";
  if (Array.isArray(value)) return value.map(display).join(", ") || "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function criterionStage(type: string): string {
  if (type === "READINESS_CHECK") return "Gate Readiness";
  if (type === "PRIORITIZATION") return "Portfolio / Resource Context";
  return "Business Evaluation";
}

function evaluationTone(value: unknown): string {
  const normalized = String(value || "NOT_EVALUATED")
    .toLowerCase()
    .split("_")
    .join("-");
  return `gateStatus gateStatus-${normalized}`;
}

function GateStageSummary({ preparation }: { preparation: InvestmentGatePreparation | null }) {
  const readiness = preparation?.readiness;
  const stages = [
    ["Evidence Readiness", readiness?.evidence_readiness_status || "NOT_EVALUATED"],
    ["Business Evaluation", readiness?.business_evaluation_status || "NOT_APPLICABLE"],
    ["Portfolio & Resource Context", readiness?.portfolio_context_status || "NOT_EVALUATED"],
    ["Decision Package", readiness?.decision_package_status || "NOT_READY_FOR_INVESTMENT_DECISION"],
  ];
  return (
    <section aria-label="Gate evaluation stages" className="gateStageSummary">
      {stages.map(([label, value]) => (
        <article key={label}>
          <span>{label}</span>
          <strong className={evaluationTone(value)}>{value}</strong>
        </article>
      ))}
      <p>READY means eligible for a governed Gate 07K decision; it never means automatic GO.</p>
    </section>
  );
}

function CriterionGroups({ criteria }: { criteria: CriterionEvaluationResult[] }) {
  return (
    <div aria-label="Decision criteria grouped by taxonomy" className="criterionGroups" role="group">
      {Object.entries(criterionTypeLabels).map(([type, label]) => {
        const rows = criteria.filter((item) => item.criterion_type === type);
        return (
          <section key={type}>
            <header>
              <h4>{label}</h4>
              <span>{rows.length}</span>
            </header>
            {rows.length ? (
              rows.map((item) => (
                <article key={String(item.criterion_id || item.criterion_code)}>
                  <div>
                    <strong>{item.criterion_name || item.criterion_code}</strong>
                    <small>{item.criterion_code}</small>
                  </div>
                  <b className={evaluationTone(item.result)}>{item.result}</b>
                  <span>
                    {item.required ? "Required" : "Advisory"} · {item.blocking ? "Blocking" : "Non-blocking"}
                  </span>
                </article>
              ))
            ) : (
              <p>No applicable criteria.</p>
            )}
          </section>
        );
      })}
    </div>
  );
}

function GateMatrix({ preparation }: { preparation: InvestmentGatePreparation }) {
  const criteria = preparation.criterion_evaluations || preparation.readiness.criterion_evaluations || [];
  return (
    <>
      <div className="gateMatrixWrap">
        <table aria-label="Gate evidence and decision criteria matrix" className="gateMatrix">
          <thead>
            <tr>
              <th>Category</th>
              <th>Evidence / Criterion</th>
              <th>Class / Type</th>
              <th>Source</th>
              <th>Version</th>
              <th>Status</th>
              <th>Readiness</th>
              <th>Quality / Confidence</th>
              <th>Current / Stale</th>
              <th>Coverage</th>
              <th>Threshold / Expected</th>
              <th>Actual Result</th>
              <th>Blocking</th>
              <th>As-of</th>
              <th>Source detail</th>
            </tr>
          </thead>
          <tbody>
            {preparation.evidence.map((item) => (
              <tr key={`evidence-${item.id}`}>
                <td>Gate Readiness</td>
                <td>
                  <strong>{item.requirement_key}</strong>
                  <small>{item.evidence_type}</small>
                </td>
                <td>Evidence Class {item.classification || "—"}</td>
                <td>{item.provider_key || item.evidence_origin}</td>
                <td>{display(item.source_version)}</td>
                <td>
                  <span className={evaluationTone(item.resolution_status || item.status)}>
                    {item.resolution_status || item.status}
                  </span>
                </td>
                <td>{item.source_readiness_status || item.resolution_status || item.status}</td>
                <td>
                  <span>{item.evidence_quality || "NOT AVAILABLE"}</span>
                  <small>Confidence {display(item.evidence_confidence)}</small>
                </td>
                <td>{item.source_current == null ? "NOT EVALUATED" : item.source_current ? "CURRENT" : "STALE"}</td>
                <td>{item.coverage_requirement == null ? "N/A" : `${item.coverage_requirement}%`}</td>
                <td>N/A</td>
                <td>{item.summary || item.resolution_status}</td>
                <td>{item.blocking ? "YES" : "NO"}</td>
                <td>{item.as_of || item.evidence_date || "—"}</td>
                <td>
                  <details>
                    <summary>View source</summary>
                    <pre>{JSON.stringify(item.evidence_refs, null, 2)}</pre>
                  </details>
                </td>
              </tr>
            ))}
            {criteria.map((item) => (
              <tr key={`criterion-${String(item.criterion_id || item.criterion_code)}`}>
                <td>{criterionStage(item.criterion_type)}</td>
                <td>
                  <strong>{item.criterion_name || item.criterion_code}</strong>
                  <small>{item.criterion_code}</small>
                </td>
                <td>{item.criterion_type}</td>
                <td>{display(item.source_reference)}</td>
                <td>Policy {display(item.policy_revision)}</td>
                <td>
                  <span className={evaluationTone(item.result)}>{item.result}</span>
                </td>
                <td>{item.result}</td>
                <td>Governed source metadata</td>
                <td>{item.result === "STALE" ? "STALE" : "CURRENT / SEE SOURCE"}</td>
                <td>N/A</td>
                <td>{display(item.threshold_or_expected_value ?? item.threshold ?? item.expected_value)}</td>
                <td>{display(item.source_value)}</td>
                <td>{item.blocking ? "YES" : "NO"}</td>
                <td>{item.evaluated_at || "—"}</td>
                <td>
                  <small>Operator {item.operator || "—"}</small>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <CriterionGroups criteria={criteria} />
    </>
  );
}

function GovernedContext({ preparation }: { preparation: InvestmentGatePreparation }) {
  const context = record(preparation.portfolio_context_snapshot);
  const candidates = preparation.success_criteria_candidates || preparation.readiness.success_criteria_candidates || [];
  const projectContexts = Array.isArray(preparation.source_snapshot.project_contexts)
    ? preparation.source_snapshot.project_contexts
    : Array.isArray(record(preparation.source_snapshot.evidence_policy).project_contexts)
      ? (record(preparation.source_snapshot.evidence_policy).project_contexts as unknown[])
      : [];
  return (
    <div className="gateContextLayout">
      <section aria-label="Gate scope and maturity" className="gateContextPanel">
        <header>
          <h4>Gate scope and FEL maturity</h4>
        </header>
        <dl>
          <div>
            <dt>Gate Profile</dt>
            <dd>{preparation.profile_code}</dd>
          </div>
          <div>
            <dt>Project / Project Set</dt>
            <dd>{display(preparation.source_snapshot.selected_project_ids)}</dd>
          </div>
          <div>
            <dt>FEL Stage</dt>
            <dd>{display(projectContexts.map((item) => record(item).fel_stage))}</dd>
          </div>
          <div>
            <dt>Policy revision</dt>
            <dd>{display(record(preparation.criterion_policy_snapshot).policy_revision)}</dd>
          </div>
        </dl>
      </section>
      <section aria-label="Frozen Portfolio context" className="gateContextPanel">
        <header>
          <h4>Portfolio & Resource Context</h4>
        </header>
        <dl>
          {Object.entries(context).map(([key, value]) => (
            <div key={key}>
              <dt>{key.split("_").join(" ")}</dt>
              <dd>{display(value)}</dd>
            </div>
          ))}
        </dl>
        {!Object.keys(context).length ? <p>No Portfolio context is available for this preparation.</p> : null}
      </section>
      <section aria-label="Success criteria candidates" className="gateContextPanel">
        <header>
          <h4>Success criteria candidates</h4>
          <span>{candidates.length}</span>
        </header>
        {candidates.length ? (
          candidates.map((item, index) => (
            <article key={String(item.criterion_id || item.criterion_code || index)}>
              <strong>{display(item.criterion_name || item.criterion_code || `Candidate ${index + 1}`)}</strong>
              <span>{display(item.result || item.status)}</span>
              <small>{display(item.source_reference || item.source_value)}</small>
            </article>
          ))
        ) : (
          <p>No success criteria candidates are applicable.</p>
        )}
      </section>
      <section aria-label="Gate warnings and blockers" className="gateContextPanel">
        <header>
          <h4>Warnings, blockers and stale sources</h4>
        </header>
        <div className="gateIssueColumns">
          <div>
            <b>Blockers</b>
            {preparation.readiness.blockers.length ? (
              preparation.readiness.blockers.map((item) => <span key={item}>{item}</span>)
            ) : (
              <span>None</span>
            )}
          </div>
          <div>
            <b>Warnings</b>
            {preparation.readiness.warnings.length ? (
              preparation.readiness.warnings.map((item) => <span key={item}>{item}</span>)
            ) : (
              <span>None</span>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function EvidenceSourceDetails({ item }: { item: InvestmentGateEvidence }) {
  if (!gate07mEvidence.has(item.evidence_type)) return null;
  const sourceLabel = item.evidence_type === "BUSINESS_CASE_READINESS" ? "Business Case" : "Economic / Financial";
  return (
    <details className="gateEvidenceSource">
      <summary>View {sourceLabel} source</summary>
      <dl>
        <div>
          <dt>Classification</dt>
          <dd>{item.classification || "—"}</dd>
        </div>
        <div>
          <dt>Provider</dt>
          <dd>{item.provider_key || "—"}</dd>
        </div>
        <div>
          <dt>Readiness</dt>
          <dd>{item.source_readiness_status || item.resolution_status}</dd>
        </div>
        <div>
          <dt>Current</dt>
          <dd>{item.source_current == null ? "Not evaluated" : item.source_current ? "YES" : "NO"}</dd>
        </div>
        <div>
          <dt>Coverage</dt>
          <dd>{item.coverage_requirement == null ? "N/A" : `${item.coverage_requirement}%`}</dd>
        </div>
      </dl>
      <pre>{JSON.stringify(item.evidence_refs, null, 2)}</pre>
    </details>
  );
}

export default function InvestmentGatePreparationWorkspace({
  token,
  portfolioId,
}: {
  token: string;
  portfolioId?: number;
}) {
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [selectedId, setSelectedId] = useState(portfolioId || 0);
  const [overview, setOverview] = useState<InvestmentGateOverview | null>(null);
  const [preparationId, setPreparationId] = useState(0);
  const [view, setView] = useState<View>("preparations");
  const [name, setName] = useState("Investment selection evidence package");
  const [profileId, setProfileId] = useState(0);
  const [felStage, setFelStage] = useState("FEL-2");
  const [projectReadiness, setProjectReadiness] = useState<ProjectReadiness | null>(null);
  const [handoff, setHandoff] = useState<Record<string, unknown> | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (portfolioId) {
      setSelectedId(portfolioId);
      return;
    }
    void portfolioPlanningApi.portfolioOptions(token).then((items) => {
      setPortfolios(items);
      setSelectedId((current) => current || Number(items[0]?.id || 0));
    });
  }, [portfolioId, token]);

  async function load(preferred?: InvestmentGatePreparation) {
    if (!selectedId) return;
    try {
      const result = await investmentGatePreparationApi.overview(token, selectedId);
      setOverview(result);
      const activeId = preferred?.id || preparationId || result.preparations[0]?.id || 0;
      setPreparationId(activeId);
      setProfileId((current) => current || Number(result.profiles[0]?.id || 0));
      if (activeId) setProjectReadiness(await investmentGatePreparationApi.projectReadiness(token, activeId));
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load Investment Gate Preparation");
    }
  }

  useEffect(() => {
    void load();
  }, [selectedId]);

  const preparation = useMemo(
    () => overview?.preparations.find((item) => item.id === preparationId) || null,
    [overview, preparationId]
  );

  async function create() {
    try {
      const result = await investmentGatePreparationApi.create(token, selectedId, profileId, name);
      setPreparationId(result.id);
      setView("evidence");
      await load(result);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create preparation");
    }
  }

  async function replace(result: Promise<InvestmentGatePreparation>, success: string) {
    try {
      const next = await result;
      await load(next);
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Controlled action failed");
    }
  }

  async function previewRefresh() {
    if (!preparation) return;
    try {
      const result = await investmentGatePreparationApi.refreshPreview(token, preparation.id);
      setMessage(`Refresh preview generated; persisted=${String(result.persisted)}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to preview refresh");
    }
  }

  async function loadHandoff() {
    if (!preparation) return;
    try {
      setHandoff(await investmentGatePreparationApi.handoff(token, preparation.id));
      setMessage("Frozen package handoff loaded. This is not an investment decision or FID.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load handoff");
    }
  }

  const readiness = preparation?.readiness;
  return (
    <section aria-label="Investment Gate Preparation" className="investmentGatePreparation">
      <CompactModuleHeader
        description="Assembles a controlled, current and auditable evidence package from a governed Portfolio recommendation. It prepares a downstream decision; it never approves investment, FID or funds."
        eyebrow="USER MODE · ENTERPRISE STRATEGY MANAGER · PORTFOLIO MANAGER · GATE 07J"
        metrics={[
          { label: "Governance", value: overview?.governance_eligible ? "CAPITAL OWNER" : "BLOCKED" },
          { label: "Coverage", value: `${readiness?.coverage_percent || 0}%` },
          { label: "Readiness", value: readiness?.readiness_status || "NOT STARTED" },
        ]}
        title="Investment Gate Preparation"
      />

      <div className="gatePreparationToolbar">
        <nav aria-label="Investment gate preparation views">
          {views.map(([key, label]) => (
            <button className={view === key ? "active" : ""} key={key} onClick={() => setView(key)} type="button">
              {label}
            </button>
          ))}
        </nav>
        <label>
          Portfolio
          <select value={selectedId} onChange={(event) => setSelectedId(Number(event.target.value))}>
            {portfolios.map((item) => (
              <option key={Number(item.id)} value={Number(item.id)}>
                {String(item.name)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Preparation
          <select value={preparationId} onChange={(event) => setPreparationId(Number(event.target.value))}>
            <option value={0}>New preparation</option>
            {overview?.preparations.map((item) => (
              <option key={item.id} value={item.id}>
                {item.preparation_number} · r{item.revision}
              </option>
            ))}
          </select>
        </label>
      </div>

      {message ? (
        <div className="planningMessage" role="status">
          {message}
        </div>
      ) : null}

      <section className={`gateReadiness ${readiness?.readiness_status?.toLowerCase() || "blocked"}`}>
        <div>
          <span>Controlled output</span>
          <h3>{readiness?.final_output || "GATE07J_REWORK_REQUIRED"}</h3>
        </div>
        <div className="gateReadinessFlags">
          <b>Source {readiness?.source_current ? "CURRENT" : "STALE"}</b>
          <b>Decision entry {readiness?.can_enter_investment_decision ? "READY" : "NO"}</b>
          <b className="prohibited">can_enter_fid = false</b>
        </div>
      </section>

      <GateStageSummary preparation={preparation} />

      {view === "preparations" ? (
        <section className="gateSurface">
          <header>
            <div>
              <span>Governed package</span>
              <h3>Preparation control</h3>
            </div>
            <Archive size={23} />
          </header>
          {!preparation ? (
            <div className="gateCreate">
              <label>
                Profile
                <select value={profileId} onChange={(event) => setProfileId(Number(event.target.value))}>
                  {overview?.profiles.map((item) => (
                    <option key={Number(item.id)} value={Number(item.id)}>
                      {String(item.profile_code)} · {String(item.name)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Preparation name
                <input value={name} onChange={(event) => setName(event.target.value)} />
              </label>
              <button
                disabled={!profileId || !overview?.governance_eligible}
                onClick={() => void create()}
                type="button"
              >
                Create governed preparation
              </button>
            </div>
          ) : (
            <>
              <div className="gateFacts">
                <article>
                  <span>Preparation</span>
                  <strong>{preparation.preparation_number}</strong>
                  <small>{preparation.name}</small>
                </article>
                <article>
                  <span>Profile</span>
                  <strong>{preparation.profile_code}</strong>
                  <small>rev {preparation.profile_revision}</small>
                </article>
                <article>
                  <span>Status</span>
                  <strong>{preparation.status}</strong>
                  <small>version {preparation.revision_version}</small>
                </article>
                <article>
                  <span>Evidence</span>
                  <strong>
                    {readiness?.valid_requirement_count}/{readiness?.required_requirement_count}
                  </strong>
                  <small>requirement types valid</small>
                </article>
              </div>
              <div className="gateActions">
                <button onClick={() => void previewRefresh()} type="button">
                  <RefreshCw size={14} /> Preview refresh
                </button>
                <button
                  disabled={!preparation.allowed_actions.includes("can_submit_for_readiness_review")}
                  onClick={() =>
                    void replace(
                      investmentGatePreparationApi.transition(token, preparation, "ready-for-review"),
                      "Submitted for readiness review."
                    )
                  }
                  type="button"
                >
                  Ready for review
                </button>
                <button
                  disabled={!preparation.allowed_actions.includes("can_freeze_preparation")}
                  onClick={() =>
                    void replace(
                      investmentGatePreparationApi.transition(token, preparation, "freeze"),
                      "Decision-ready package frozen."
                    )
                  }
                  type="button"
                >
                  Freeze package
                </button>
                <button disabled={preparation.status !== "FROZEN"} onClick={() => void loadHandoff()} type="button">
                  Load handoff
                </button>
              </div>
              {handoff ? <pre className="gateHandoff">{JSON.stringify(handoff, null, 2)}</pre> : null}
            </>
          )}
          <div className="gateBoundaries">
            {overview?.boundaries.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
        </section>
      ) : null}

      {view === "evidence" ? (
        <section className="gateSurface">
          <header>
            <div>
              <span>Current evidence package</span>
              <h3>Evidence requirements and references</h3>
            </div>
            <FileCheck2 size={23} />
          </header>
          <div className="evidenceGrid">
            {preparation?.evidence.map((item) => (
              <article
                className={`${item.status.toLowerCase()} ${gate07mEvidence.has(item.evidence_type) ? "gate07mEvidence" : ""}`}
                key={item.id}
              >
                <div>
                  <strong>
                    {item.evidence_type === "BUSINESS_CASE_READINESS"
                      ? "Business Case Readiness"
                      : item.evidence_type === "ECONOMIC_FINANCIAL_READINESS"
                        ? "Economic / Financial Readiness"
                        : item.requirement_key}
                  </strong>
                  <b>{item.resolution_status || item.status}</b>
                </div>
                <span>
                  Class {item.classification || "—"} · {item.blocking ? "Blocking" : "Non-blocking"} · {item.scope_type}
                  {item.scope_id ? ` #${item.scope_id}` : ""}
                </span>
                <div className="evidenceMetadata" aria-label={`Evidence quality ${item.requirement_key}`}>
                  <span>
                    Readiness <b>{item.source_readiness_status || item.resolution_status || item.status}</b>
                  </span>
                  <span>
                    Quality <b>{item.evidence_quality || "NOT AVAILABLE"}</b>
                  </span>
                  <span>
                    Confidence <b>{display(item.evidence_confidence)}</b>
                  </span>
                  <span>
                    Currency{" "}
                    <b>{item.source_current == null ? "NOT EVALUATED" : item.source_current ? "CURRENT" : "STALE"}</b>
                  </span>
                </div>
                <small>{item.summary}</small>
                <EvidenceSourceDetails item={item} />
                {item.evidence_origin === "MANUAL_REFERENCE" && item.scope_id ? (
                  <div className="evidenceActions">
                    <select
                      aria-label={`FEL stage ${item.scope_id}`}
                      value={felStage}
                      onChange={(event) => setFelStage(event.target.value)}
                    >
                      <option>FEL-1</option>
                      <option>FEL-2</option>
                      <option>FEL-3</option>
                    </select>
                    <button
                      disabled={!preparation || preparation.status === "FROZEN"}
                      onClick={() =>
                        void replace(
                          investmentGatePreparationApi.addFelEvidence(
                            token,
                            preparation,
                            item.scope_id!,
                            felStage,
                            `FEL-ASSESSMENT-${item.scope_id}`
                          ),
                          "Manual FEL reference submitted."
                        )
                      }
                      type="button"
                    >
                      Submit reference
                    </button>
                    <button
                      disabled={item.status !== "SUBMITTED"}
                      onClick={() =>
                        void replace(
                          investmentGatePreparationApi.validateEvidence(token, preparation!, item.id),
                          "Evidence validated by current reviewer."
                        )
                      }
                      type="button"
                    >
                      Validate
                    </button>
                    <button
                      disabled={item.status === "MISSING"}
                      onClick={() =>
                        void replace(
                          investmentGatePreparationApi.removeEvidence(token, preparation!, item.id),
                          "Manual evidence reference removed."
                        )
                      }
                      type="button"
                    >
                      Remove
                    </button>
                  </div>
                ) : null}
                {item.blockers.map((blocker) => (
                  <em key={blocker}>{blocker}</em>
                ))}
                {item.warnings.map((warning) => (
                  <em className="warning" key={warning}>
                    {warning}
                  </em>
                ))}
              </article>
            ))}
          </div>
          {readiness?.evidence_coverage ? (
            <details className="gateEvidenceSource">
              <summary>Class A coverage controls</summary>
              <pre>{JSON.stringify(readiness.evidence_coverage, null, 2)}</pre>
            </details>
          ) : null}
        </section>
      ) : null}

      {view === "matrix" && preparation ? (
        <section className="gateSurface">
          <header>
            <div>
              <span>Evidence, criteria and governed context</span>
              <h3>Gate evaluation matrix</h3>
            </div>
            <FileCheck2 size={23} />
          </header>
          <p className="gateMatrixNotice">
            Evidence Class A/B/C and decision-criterion taxonomy are independent. Results support a human Gate 07K
            decision and never calculate GO, HOLD, RECYCLE or KILL.
          </p>
          <GateMatrix preparation={preparation} />
          <GovernedContext preparation={preparation} />
        </section>
      ) : null}

      {view === "projects" ? (
        <section className="gateSurface">
          <header>
            <div>
              <span>Coverage control</span>
              <h3>Selected-project readiness matrix</h3>
            </div>
            <CheckCircle2 size={23} />
          </header>
          <div className="projectReadinessGrid">
            {projectReadiness?.projects.map((item) => (
              <article key={String(item.project_id)}>
                <strong>Project #{String(item.project_id)}</strong>
                <b>{String(item.status)}</b>
                <span>
                  {String(item.valid_count)}/{String(item.required_count)} valid
                </span>
                <small>
                  {Array.isArray(item.missing_requirements) ? item.missing_requirements.join(", ") || "Complete" : ""}
                </small>
              </article>
            ))}
          </div>
          <p>
            <b>{projectReadiness?.coverage_percent || 0}%</b> project evidence coverage; blocked projects:{" "}
            {projectReadiness?.blocked_project_count || 0}.
          </p>
        </section>
      ) : null}

      {view === "conditions" ? (
        <section className="gateSurface">
          <header>
            <div>
              <span>Inherited recommendation conditions</span>
              <h3>Preparation resolution tracking</h3>
            </div>
            <ShieldAlert size={23} />
          </header>
          <div className="conditionList">
            {preparation?.conditions.length ? (
              preparation.conditions.map((item, index) => (
                <article key={String(item.condition_id || index)}>
                  <strong>{String(item.original_text)}</strong>
                  <span>{String(item.preparation_status)}</span>
                  <button
                    disabled={preparation.status === "FROZEN"}
                    onClick={() =>
                      void replace(
                        investmentGatePreparationApi.updateCondition(
                          token,
                          preparation,
                          index,
                          "RESOLVED_FOR_PREPARATION"
                        ),
                        "Condition marked resolved for preparation; original text retained."
                      )
                    }
                    type="button"
                  >
                    Resolve for preparation
                  </button>
                </article>
              ))
            ) : (
              <p>No inherited recommendation conditions.</p>
            )}
          </div>
        </section>
      ) : null}

      {view === "history" ? (
        <section className="gateSurface">
          <header>
            <div>
              <span>Immutable lineage</span>
              <h3>Preparation revisions</h3>
            </div>
          </header>
          <div className="gateHistory">
            {overview?.preparations.map((item) => (
              <button
                className={item.id === preparationId ? "active" : ""}
                key={item.id}
                onClick={() => setPreparationId(item.id)}
                type="button"
              >
                <strong>{item.preparation_number}</strong>
                <span>
                  {item.status} · {item.profile_code}
                </span>
                <small>{item.preparation_hash || item.preparation_source_hash}</small>
              </button>
            ))}
          </div>
        </section>
      ) : null}
    </section>
  );
}
