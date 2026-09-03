/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Archive, CheckCircle2, FileCheck2, RefreshCw, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import "../portfolio-planning/portfolioPlanning.css";
import { investmentGatePreparationApi } from "./api";
import type {
  InvestmentGateEvidence,
  InvestmentGateOverview,
  InvestmentGatePreparation,
  ProjectReadiness,
} from "./types";
import "./investmentGatePreparation.css";

type View = "preparations" | "evidence" | "projects" | "conditions" | "history";
const views: Array<[View, string]> = [
  ["preparations", "Preparations"],
  ["evidence", "Evidence Package"],
  ["projects", "Project Readiness"],
  ["conditions", "Conditions"],
  ["history", "History"],
];

const gate07mEvidence = new Set(["BUSINESS_CASE_READINESS", "ECONOMIC_FINANCIAL_READINESS"]);

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
