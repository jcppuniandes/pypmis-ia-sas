/* eslint-disable react-hooks/exhaustive-deps, react-hooks/set-state-in-effect */
import { Copy, Database, Eye, Save, Send, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { portfolioPlanningApi } from "../portfolio-planning/api";
import { investmentEvidencePolicyApi } from "./api";
import type {
  EvidencePolicyConfiguration,
  EvidencePolicyContent,
  EvidencePolicyOverview,
  EvidencePolicyPreview,
  EvidenceRequirement,
  GateDecisionCriterion,
} from "./types";
import "./investmentEvidencePolicy.css";

const sections = [
  "Overview",
  "Evidence Policy",
  "Evidence Classes",
  "Provider Registry",
  "Gate Profiles",
  "Decision Criteria",
  "Criterion Types",
  "Criterion Applicability",
  "Thresholds / Expected States",
  "Readiness Rules",
  "Evidence Quality Rules",
  "Coverage Rules",
  "Freshness Rules",
  "Portfolio Context Rules",
  "Success Criteria Rules",
  "Project Type Overrides",
  "Governance Model Overrides",
  "FEL Stage Overrides",
  "Uncertainty / Complexity Tailoring",
  "Inheritance",
  "SoD",
  "Preview",
  "Publish",
  "History",
] as const;

type Section = (typeof sections)[number];

function parseContent(value: string): EvidencePolicyContent | null {
  try {
    return JSON.parse(value) as EvidencePolicyContent;
  } catch {
    return null;
  }
}

function classLabel(value: string) {
  if (value === "A") return "A · Governed source required";
  if (value === "B") return "B · Governed evidence sufficient";
  return "C · Not required";
}

const criterionTypeDescriptions: Record<string, string> = {
  READINESS_CHECK: "Confirms whether the frozen package can enter business evaluation.",
  MUST_MEET: "Mandatory or knockout condition; it is not an evidence class.",
  DECISION_HURDLE: "Controlled qualitative or quantitative minimum threshold.",
  PRIORITIZATION: "Consumes existing Portfolio authority without recalculating rank.",
  SUCCESS_CRITERION: "Candidate commitment for a future immutable FID snapshot.",
};

const defaultOperators = [
  "EQUALS",
  "NOT_EQUALS",
  "GREATER_THAN",
  "GREATER_THAN_OR_EQUAL",
  "LESS_THAN",
  "LESS_THAN_OR_EQUAL",
  "IN",
  "NOT_IN",
  "IS_TRUE",
  "IS_FALSE",
  "IS_READY",
  "IS_CURRENT",
  "COVERAGE_AT_LEAST",
];

function records(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    : [];
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function display(value: unknown): string {
  if (value == null || value === "") return "—";
  if (Array.isArray(value)) return value.map(display).join(", ") || "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function configuredCriteria(content: EvidencePolicyContent | null): GateDecisionCriterion[] {
  if (!content) return [];
  const direct = content.decision_criteria;
  if (Array.isArray(direct)) return direct;
  const policy = record(content.decision_criterion_policy);
  const byProfile = record(policy.criteria_by_profile);
  return Object.values(byProfile).flatMap((items) => records(items)) as GateDecisionCriterion[];
}

export default function InvestmentEvidencePolicyAdminView({ token }: { token: string }) {
  const [overview, setOverview] = useState<EvidencePolicyOverview | null>(null);
  const [selected, setSelected] = useState<EvidencePolicyConfiguration | null>(null);
  const [content, setContent] = useState("");
  const [section, setSection] = useState<Section>("Overview");
  const [portfolios, setPortfolios] = useState<Array<Record<string, unknown>>>([]);
  const [portfolioId, setPortfolioId] = useState(0);
  const [gateProfile, setGateProfile] = useState("PYP-FFA");
  const [projectType, setProjectType] = useState("COMMERCIAL");
  const [governanceModel, setGovernanceModel] = useState("CAPITAL_OWNER");
  const [preview, setPreview] = useState<EvidencePolicyPreview | null>(null);
  const [message, setMessage] = useState("");
  const parsed = useMemo(() => parseContent(content), [content]);

  const matrixRows = useMemo(() => {
    if (!parsed) return [];
    return Object.entries(parsed.gate_profiles || {}).flatMap(([profile, value]) =>
      (value.requirements || []).map((item) => ({ profile, ...item }))
    );
  }, [parsed]);
  const criteria = useMemo(() => configuredCriteria(parsed), [parsed]);
  const controlledOperators = useMemo(() => {
    if (preview?.controlled_operators?.length) return preview.controlled_operators;
    if (parsed?.controlled_operators?.length) return parsed.controlled_operators;
    if (parsed?.decision_criterion_policy?.controlled_operators?.length) {
      return parsed.decision_criterion_policy.controlled_operators;
    }
    return defaultOperators;
  }, [parsed, preview]);

  async function load(preferredId?: number) {
    const [nextOverview, portfolioOptions] = await Promise.all([
      investmentEvidencePolicyApi.overview(token),
      portfolioPlanningApi.portfolioOptions(token),
    ]);
    setOverview(nextOverview);
    setPortfolios(portfolioOptions);
    setPortfolioId((current) => current || Number(portfolioOptions[0]?.id || 0));
    const next =
      nextOverview.configurations.find((item) => item.id === preferredId) ||
      nextOverview.configurations.find((item) => item.status === "draft") ||
      nextOverview.configurations[0] ||
      null;
    setSelected(next);
    setContent(next ? JSON.stringify(next.content_json, null, 2) : "");
  }

  useEffect(() => {
    void load().catch((error) =>
      setMessage(error instanceof Error ? error.message : "Unable to load Investment Evidence Policy")
    );
  }, [token]);

  async function execute(action: "clone" | "clone-evid2" | "save" | "publish") {
    if (!selected) return;
    try {
      let result = selected;
      if (action === "clone") result = await investmentEvidencePolicyApi.clone(token, selected);
      if (action === "clone-evid2") result = await investmentEvidencePolicyApi.cloneGate07jEvid2(token, selected);
      if (action === "save") {
        if (!parsed) throw new Error("Policy JSON is invalid.");
        result = await investmentEvidencePolicyApi.save(token, selected, parsed);
      }
      if (action === "publish") result = await investmentEvidencePolicyApi.publish(token, selected);
      await load(result.id);
      setPreview(null);
      setMessage(`Evidence policy ${action} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Unable to ${action} evidence policy`);
    }
  }

  async function previewPolicy() {
    if (!selected || !parsed) return;
    try {
      const result = await investmentEvidencePolicyApi.preview(
        token,
        selected,
        portfolioId || null,
        gateProfile,
        parsed,
        projectType,
        governanceModel
      );
      setPreview(result);
      setSection("Preview");
      setMessage("Dry-run completed: persisted=false; no Preparation, Investment Decision or FID was created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to preview evidence policy");
    }
  }

  function renderMatrix(rows: Array<EvidenceRequirement & { profile?: string }>) {
    return (
      <div className="evidencePolicyTableWrap">
        <table className="evidencePolicyTable">
          <thead>
            <tr>
              <th>Evidence</th>
              <th>Gate Profile</th>
              <th>Class</th>
              <th>Required / Blocking</th>
              <th>Provider</th>
              <th>Scope</th>
              <th>Validity</th>
              <th>Coverage</th>
              <th>Manual evidence</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((item, index) => (
              <tr key={`${item.profile || gateProfile}-${item.requirement_key}-${index}`}>
                <td>
                  <strong>{item.evidence_type.replace(/_/g, " ")}</strong>
                  <small>{item.rationale}</small>
                </td>
                <td>{item.profile || gateProfile}</td>
                <td>
                  <span className={`evidenceClass evidenceClass${item.classification}`}>
                    {classLabel(item.classification)}
                  </span>
                </td>
                <td>{item.required ? (item.blocking ? "Required · Blocking" : "Required · Warning") : "No"}</td>
                <td>{item.provider_key || "Controlled manual evidence"}</td>
                <td>{item.scope}</td>
                <td>{item.validity_period_days ? `${item.validity_period_days} days` : "Contextual"}</td>
                <td>{item.coverage_requirement == null ? "—" : `${item.coverage_requirement}%`}</td>
                <td>{item.allow_manual_reference ? "Allowed · controlled" : "Not allowed"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  function renderCriteria(
    rows: GateDecisionCriterion[],
    mode: "definition" | "applicability" | "threshold" = "definition"
  ) {
    return (
      <div className="evidencePolicyTableWrap">
        <table aria-label={`Decision criteria ${mode}`} className="evidencePolicyTable decisionCriteriaTable">
          <thead>
            <tr>
              <th>Criterion</th>
              <th>Type</th>
              {mode === "applicability" ? (
                <>
                  <th>Gate / FEL</th>
                  <th>Project Type</th>
                  <th>Governance Model</th>
                </>
              ) : null}
              {mode !== "applicability" ? <th>Governed source</th> : null}
              {mode !== "applicability" ? <th>Field</th> : null}
              {mode !== "applicability" ? <th>Operator</th> : null}
              {mode !== "applicability" ? <th>Threshold / expected state</th> : null}
              <th>Required / Blocking</th>
              {mode === "definition" ? <th>Weight</th> : null}
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.map((item, index) => (
                <tr key={`${item.criterion_code}-${index}`}>
                  <td>
                    <strong>{item.criterion_name || item.criterion_code}</strong>
                    <small>{item.criterion_code}</small>
                  </td>
                  <td>
                    <span className={`criterionType criterionType${item.criterion_type}`}>{item.criterion_type}</span>
                  </td>
                  {mode === "applicability" ? (
                    <>
                      <td>
                        {display(item.gate_profiles || item.gate_profile_code)} ·{" "}
                        {display(item.fel_stage_applicability)}
                      </td>
                      <td>{display(item.project_type_applicability || item.project_type_filter)}</td>
                      <td>{display(item.governance_model_applicability || item.governance_model_filter)}</td>
                    </>
                  ) : null}
                  {mode !== "applicability" ? <td>{display(item.source_evidence_type)}</td> : null}
                  {mode !== "applicability" ? <td>{display(item.source_field)}</td> : null}
                  {mode !== "applicability" ? <td>{display(item.operator)}</td> : null}
                  {mode !== "applicability" ? (
                    <td>{display(item.threshold ?? item.expected_state ?? item.expected_value)}</td>
                  ) : null}
                  <td>{item.required ? (item.blocking ? "Required · Blocking" : "Required") : "Optional"}</td>
                  {mode === "definition" ? <td>{item.weight == null ? "N/A" : item.weight}</td> : null}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={mode === "applicability" ? 7 : mode === "definition" ? 8 : 7}>
                  No decision criteria are configured in this revision.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    );
  }

  function renderPolicyValue(title: string, value: unknown, note: string) {
    return (
      <>
        <div className="evidencePolicyCallout">
          <ShieldCheck size={20} />
          <div>
            <strong>{title}</strong>
            <span>{note}</span>
          </div>
        </div>
        <details open className="evidencePolicyJson">
          <summary>Governed configuration</summary>
          <pre>{JSON.stringify(value ?? {}, null, 2)}</pre>
        </details>
      </>
    );
  }

  function sectionContent() {
    if (!overview || !parsed) return <p>Loading controlled evidence policy…</p>;
    if (section === "Evidence Policy") return renderMatrix(matrixRows);
    if (section === "Evidence Classes") {
      return (
        <div className="evidencePolicyCards evidenceClassCards">
          {[
            ["A", "GOVERNED_SOURCE_REQUIRED", "A governed source is mandatory and its failure may block readiness."],
            ["B", "GOVERNED_EVIDENCE_SUFFICIENT", "Governed evidence is consumed according to the configured policy."],
            ["C", "NOT_REQUIRED", "The evidence does not block this applicable Gate context."],
          ].map(([code, name, description]) => (
            <article key={code}>
              <span>Evidence Class {code}</span>
              <h3>{name}</h3>
              <p>{description}</p>
            </article>
          ))}
          <article className="taxonomyBoundary">
            <span>Mandatory boundary</span>
            <h3>Evidence ≠ Criterion</h3>
            <p>A/B/C never becomes a decision criterion type or a formal GO/HOLD/RECYCLE/KILL outcome.</p>
          </article>
        </div>
      );
    }
    if (section === "Gate Profiles") {
      return (
        <div className="evidencePolicyCards">
          {Object.entries(parsed.gate_profiles).map(([code, profile]) => (
            <article key={code}>
              <span>Investment Gate Profile</span>
              <h3>{code}</h3>
              <b>{profile.requirements.length} governed matrix rows</b>
              <p>Conditions: {profile.allow_valid_with_conditions ? "allowed by policy" : "not allowed"}</p>
            </article>
          ))}
        </div>
      );
    }
    if (section === "Decision Criteria") return renderCriteria(criteria);
    if (section === "Criterion Applicability") return renderCriteria(criteria, "applicability");
    if (section === "Thresholds / Expected States") return renderCriteria(criteria, "threshold");
    if (section === "Criterion Types") {
      const taxonomy = preview?.decision_criterion_taxonomy?.length
        ? preview.decision_criterion_taxonomy
        : Object.keys(criterionTypeDescriptions);
      return (
        <>
          <div className="evidencePolicyCards criterionTypeCards">
            {taxonomy.map((item) => (
              <article key={item}>
                <span>Decision Criterion Type</span>
                <h3>{item}</h3>
                <p>{criterionTypeDescriptions[item] || "Governed criterion type returned by the policy."}</p>
              </article>
            ))}
          </div>
          <div className="controlledOperators" aria-label="Controlled decision criterion operators">
            <strong>Controlled operators</strong>
            <div>
              {controlledOperators.map((item) => (
                <code key={item}>{item}</code>
              ))}
            </div>
            <p>Free-form executable formulas are not supported.</p>
          </div>
        </>
      );
    }
    if (section === "Project Type Overrides") {
      return (
        <div className="evidencePolicyTableWrap">
          <table className="evidencePolicyTable">
            <thead>
              <tr>
                <th>Profile</th>
                <th>Project Type</th>
                <th>Evidence</th>
                <th>Resolution</th>
                <th>Provider</th>
                <th>Governance model</th>
                <th>Coverage</th>
                <th>Rationale</th>
              </tr>
            </thead>
            <tbody>
              {parsed.project_type_overrides.map((item, index) => (
                <tr key={index}>
                  <td>{String(item.gate_profile_code)}</td>
                  <td>{String((item.project_type_filter as string[])?.join(", "))}</td>
                  <td>{String(item.evidence_type)}</td>
                  <td>{String(item.classification)}</td>
                  <td>{String(item.provider_key || "—")}</td>
                  <td>{String((item.governance_model_filter as string[])?.join(", ") || "All")}</td>
                  <td>{item.coverage_requirement == null ? "—" : `${String(item.coverage_requirement)}%`}</td>
                  <td>{String(item.rationale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    if (section === "Provider Registry") {
      return (
        <div className="evidencePolicyTableWrap">
          <table className="evidencePolicyTable">
            <thead>
              <tr>
                <th>Evidence / Provider</th>
                <th>Source Module</th>
                <th>Contract</th>
                <th>Status</th>
                <th>Contract / availability</th>
                <th>Supported Scope</th>
                <th>Version</th>
                <th>Hash / Current / Readiness</th>
              </tr>
            </thead>
            <tbody>
              {overview.providers.map((item) => (
                <tr key={item.provider_key}>
                  <td>
                    <strong>{item.evidence_type}</strong>
                    <small>{item.provider_key}</small>
                  </td>
                  <td>{item.source_module}</td>
                  <td>{item.source_contract}</td>
                  <td>
                    <span className={`providerState ${item.status.toLowerCase()}`}>{item.status}</span>
                  </td>
                  <td>
                    <strong>{item.contract_status}</strong>
                    <small>
                      {item.availability} ·{" "}
                      {item.last_validation ? new Date(item.last_validation).toLocaleString() : "—"}
                    </small>
                  </td>
                  <td>
                    {[
                      item.supports_portfolio_scope && "Portfolio",
                      item.supports_project_set_scope && "Project Set",
                      item.supports_project_scope && "Project",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </td>
                  <td>{item.version}</td>
                  <td>
                    {item.supports_hash && item.supports_current_flag && item.supports_readiness
                      ? "Yes / Yes / Yes"
                      : "No / No / No"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    if (section === "Readiness Rules") {
      return renderPolicyValue(
        "Gate readiness rules",
        parsed.readiness_rules || parsed.blocking_policy,
        "Readiness confirms that the package can be evaluated. It never produces GO, HOLD, RECYCLE or KILL."
      );
    }
    if (section === "Evidence Quality Rules") {
      return renderPolicyValue(
        "Evidence quality is separate from readiness",
        parsed.evidence_quality_rules || parsed.decision_criterion_policy?.evidence_quality_states,
        "Quality and confidence remain governed metadata; the browser does not infer them."
      );
    }
    if (section === "Coverage Rules") {
      return renderPolicyValue(
        "Exact Project Set coverage",
        parsed.coverage_policy,
        "The required denominator is preserved; missing Projects are never hidden by averaging."
      );
    }
    if (section === "Freshness Rules") {
      return renderPolicyValue(
        "Source-current and freshness controls",
        parsed.freshness_rules || parsed.validity_policy,
        "Current provider hashes, effective policy and as-of dates are evaluated by the backend."
      );
    }
    if (section === "Portfolio Context Rules") {
      return renderPolicyValue(
        "Portfolio authority is consumed, not recreated",
        parsed.portfolio_context_rules || {
          portfolio_rank_authority: parsed.decision_criterion_policy?.portfolio_rank_authority || "PORTFOLIO",
        },
        "Rank, scenarios, budget and resources remain Portfolio-owned context for a governed human decision."
      );
    }
    if (section === "Success Criteria Rules") {
      return (
        <>
          {renderCriteria(
            criteria.filter((item) => item.criterion_type === "SUCCESS_CRITERION"),
            "threshold"
          )}
          {renderPolicyValue(
            "Immutable FID candidate snapshot",
            parsed.success_criteria_rules || {},
            "Gate 07J prepares candidates; Gate 07K freezes selected source references and values on formal decision."
          )}
        </>
      );
    }
    if (section === "Governance Model Overrides") {
      return renderPolicyValue(
        "Governance model applicability",
        parsed.governance_model_overrides || parsed.applicable_governance_models,
        "CAPITAL_OWNER requirements do not silently apply to CONTRACTOR_DELIVERY or DIRECT_INTERNAL."
      );
    }
    if (section === "FEL Stage Overrides") {
      return renderPolicyValue(
        "Progressive FEL maturity",
        parsed.fel_stage_overrides || parsed.decision_criterion_policy?.tailoring_dimensions || {},
        "Select remains stage-appropriate; FFA may apply the stricter published maturity policy."
      );
    }
    if (section === "Uncertainty / Complexity Tailoring") {
      return renderPolicyValue(
        "Tailoring dimensions",
        parsed.uncertainty_complexity_tailoring || parsed.decision_criterion_policy?.tailoring_dimensions || {},
        "Project type, risk, complexity and uncertainty applicability is configuration-driven."
      );
    }
    if (section === "Inheritance") {
      return renderPolicyValue(
        "Effective-dated inheritance",
        parsed.inheritance || parsed.decision_criterion_policy?.new_round_policy || {},
        "Historical rounds retain their frozen policy; a new round resolves policy under the configured rule."
      );
    }
    if (section === "SoD") {
      return renderPolicyValue(
        "Segregation of duties",
        parsed.segregation_of_duties || {},
        "Policy publishers cannot bypass Gate preparation or formal Gate 07K decision authority."
      );
    }
    if (section === "Preview") {
      if (!preview) return <p>Choose a Portfolio and Gate Profile, then run Preview.</p>;
      return (
        <>
          <div className="evidencePolicyCards">
            <article>
              <span>Persisted</span>
              <h3>{String(preview.persisted)}</h3>
            </article>
            <article>
              <span>Class A / B / C</span>
              <h3>{`${preview.class_A_count} / ${preview.class_B_count} / ${preview.class_C_count}`}</h3>
            </article>
            <article>
              <span>Missing required providers</span>
              <h3>{preview.missing_required_provider_count}</h3>
            </article>
            <article>
              <span>Decision Package eligibility</span>
              <h3>{preview.would_be_ready_for_investment_gate ? "READY" : "BLOCKED"}</h3>
            </article>
          </div>
          <div className="evidencePolicyCards gateStageCards">
            <article>
              <span>A · Gate Readiness</span>
              <h3>{preview.evidence_readiness_status || (preview.would_gate07j_be_ready ? "READY" : "BLOCKED")}</h3>
              <p>Evidence sufficiency, freshness, quality and exact coverage.</p>
            </article>
            <article>
              <span>B · Business Evaluation</span>
              <h3>{preview.business_evaluation_status || "PREVIEW"}</h3>
              <p>Must-meet criteria and decision hurdles over governed source values.</p>
            </article>
            <article>
              <span>C · Portfolio / Resource Context</span>
              <h3>{preview.portfolio_context_status || "CONTEXT"}</h3>
              <p>Consumes Portfolio rank and feasibility; it never computes a second rank.</p>
            </article>
            <article>
              <span>Gate 07K eligibility</span>
              <h3>
                {preview.decision_package_status || (preview.would_be_ready_for_investment_gate ? "READY" : "BLOCKED")}
              </h3>
              <p>READY means eligible for governed decision; it does not mean automatic GO.</p>
            </article>
          </div>
          <div className="evidencePolicyCards">
            {(["BUSINESS_CASE_READINESS", "ECONOMIC_FINANCIAL_READINESS"] as const).map((evidenceType) => (
              <article key={evidenceType}>
                <span>{evidenceType.replace(/_/g, " ")}</span>
                <h3>{((preview.effective_classifications || {})[evidenceType] || ["—"]).join(" / ")}</h3>
                <b>
                  Provider {(preview.source_availability || {})[evidenceType] || "NOT CONFIGURED"} · coverage{" "}
                  {(preview.required_coverage || {})[evidenceType] == null
                    ? "N/A"
                    : `${(preview.required_coverage || {})[evidenceType]}%`}
                </b>
                <p>
                  Readiness {((preview.source_readiness || {})[evidenceType] || ["NOT EVALUATED"]).join(", ")} · current{" "}
                  {((preview.source_current || {})[evidenceType] || []).map(String).join(", ") || "not evaluated"}
                </p>
              </article>
            ))}
          </div>
          <div className="evidencePolicyCallout danger">
            <strong>No silent fallback</strong>
            <span>{preview.blockers.join(" · ") || "No blocking provider gaps for this context."}</span>
          </div>
          {renderMatrix(preview.effective_matrix)}
          <h3 className="evidencePolicySubheading">Effective decision criteria</h3>
          {renderCriteria(preview.decision_criteria || criteria)}
          {(preview.criterion_validation_issues || []).length ? (
            <div className="evidencePolicyCallout danger">
              <strong>Criterion validation issues</strong>
              <span>{preview.criterion_validation_issues?.join(" · ")}</span>
            </div>
          ) : null}
          {(preview.missing_providers || []).length ? (
            <details className="evidencePolicyJson">
              <summary>Missing provider diagnostics</summary>
              <pre>{JSON.stringify(preview.missing_providers, null, 2)}</pre>
            </details>
          ) : null}
          <details open className="evidencePolicyJson">
            <summary>Deterministic next-development decision</summary>
            <pre>{JSON.stringify(preview.recommended_next_development, null, 2)}</pre>
          </details>
        </>
      );
    }
    if (section === "Publish") {
      return (
        <>
          <div className="evidencePolicyCallout">
            <Send size={20} />
            <div>
              <strong>DRAFT → PUBLISHED → ARCHIVED</strong>
              <span>
                Publication is effective-dated and immutable. It affects only newly applicable preparations; frozen
                historical packages retain their captured revision and hash.
              </span>
            </div>
          </div>
          <div className="evidencePolicyCards">
            <article>
              <span>Selected revision</span>
              <h3>{selected?.revision || "—"}</h3>
              <p>{selected?.status || "No policy selected"}</p>
            </article>
            <article>
              <span>Effective from</span>
              <h3>{display(parsed.effective_from || parsed.decision_criterion_policy?.effective_from)}</h3>
            </article>
            <article>
              <span>Formal decision authority</span>
              <h3>{parsed.decision_criterion_policy?.formal_decision_authority || "GATE07K"}</h3>
              <p>No automated GO/HOLD/RECYCLE/KILL.</p>
            </article>
            <article>
              <span>Unsafe expressions</span>
              <h3>
                {parsed.decision_criterion_policy?.unsafe_expression_execution === false ? "DISABLED" : "NOT ALLOWED"}
              </h3>
            </article>
          </div>
        </>
      );
    }
    if (section === "History") {
      return (
        <div className="evidencePolicyHistory">
          {overview.configurations.map((item) => (
            <article key={item.id}>
              <b>Revision {item.revision}</b>
              <span>{item.status}</span>
              <code>{item.content_hash.slice(0, 18)}…</code>
            </article>
          ))}
        </div>
      );
    }
    return (
      <>
        <div className="evidencePolicyCallout">
          <ShieldCheck size={20} />
          <div>
            <strong>Evidence classification and decision criteria stay separate</strong>
            <span>
              A/B/C governs source sufficiency. READINESS_CHECK, MUST_MEET, DECISION_HURDLE, PRIORITIZATION and
              SUCCESS_CRITERION govern evaluation. Gate 07K alone owns the formal decision.
            </span>
          </div>
        </div>
        <details open className="evidencePolicyJson">
          <summary>Controlled Evidence &amp; Decision Policy JSON</summary>
          <textarea
            aria-label="Evidence and Decision Policy JSON"
            disabled={selected?.status !== "draft"}
            onChange={(event) => setContent(event.target.value)}
            rows={30}
            value={content}
          />
        </details>
      </>
    );
  }

  return (
    <section aria-label="Evidence & Decision Policy" className="investmentEvidencePolicy">
      <CompactModuleHeader
        description="Governs the separate evidence A/B/C taxonomy, controlled decision criteria, progressive maturity, Portfolio context and success-criteria candidates consumed by Gate 07J."
        eyebrow="ADMIN MODE · ENTERPRISE STRATEGY MANAGER · INVESTMENT GOVERNANCE · GATE 07J-EVID-2"
        metrics={[
          { label: "Policy revisions", value: overview?.configurations.length || 0 },
          { label: "Providers", value: overview?.providers.length || 0 },
          { label: "Decision criteria", value: preview?.decision_criteria?.length ?? criteria.length },
          { label: "Blocking gaps", value: preview?.missing_required_provider_count ?? "Preview" },
        ]}
        title="Evidence & Decision Policy"
        tone="admin"
      />
      {message ? (
        <div className="evidencePolicyMessage" role="status">
          {message}
        </div>
      ) : null}
      <div className="evidencePolicyCommandBar">
        <label>
          Policy revision
          <select
            aria-label="Policy revision"
            value={selected?.id || 0}
            onChange={(event) => {
              const next = overview?.configurations.find((item) => item.id === Number(event.target.value)) || null;
              setSelected(next);
              setContent(next ? JSON.stringify(next.content_json, null, 2) : "");
              setPreview(null);
            }}
          >
            {(overview?.configurations || []).map((item) => (
              <option key={item.id} value={item.id}>{`rev ${item.revision} · ${item.status}`}</option>
            ))}
          </select>
        </label>
        <label>
          Portfolio
          <select
            aria-label="Evidence policy Portfolio"
            value={portfolioId}
            onChange={(event) => setPortfolioId(Number(event.target.value))}
          >
            <option value={0}>Configuration only</option>
            {portfolios.map((item) => (
              <option key={Number(item.id)} value={Number(item.id)}>
                {String(item.name)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Gate Profile
          <select
            aria-label="Investment Gate Profile"
            value={gateProfile}
            onChange={(event) => setGateProfile(event.target.value)}
          >
            <option value="PYP-INV-SELECT">PYP-INV-SELECT</option>
            <option value="PYP-FFA">PYP-FFA</option>
          </select>
        </label>
        <label>
          Project Type
          <select
            aria-label="Evidence policy Project Type"
            value={projectType}
            onChange={(event) => setProjectType(event.target.value)}
          >
            <option value="COMMERCIAL">COMMERCIAL</option>
            <option value="PUBLIC">PUBLIC / NON-REVENUE</option>
            <option value="MIXED">MIXED</option>
            <option value="INTERNAL">INTERNAL / COMPLIANCE</option>
          </select>
        </label>
        <label>
          Governance Model
          <select
            aria-label="Evidence policy Governance Model"
            value={governanceModel}
            onChange={(event) => setGovernanceModel(event.target.value)}
          >
            <option value="CAPITAL_OWNER">CAPITAL_OWNER</option>
            <option value="CONTRACTOR_DELIVERY">CONTRACTOR_DELIVERY</option>
            <option value="DIRECT_INTERNAL">DIRECT_INTERNAL</option>
          </select>
        </label>
        <label>
          Effective from
          <input
            aria-label="Evidence policy effective from"
            disabled={selected?.status !== "draft"}
            onChange={(event) => {
              if (!parsed) return;
              setContent(JSON.stringify({ ...parsed, effective_from: event.target.value || null }, null, 2));
            }}
            type="datetime-local"
            value={String(parsed?.effective_from || "").slice(0, 16)}
          />
        </label>
        <div aria-label="Evidence policy actions" className="evidencePolicyActions" role="group">
          <button
            disabled={!selected || selected.status !== "published"}
            onClick={() => void execute("clone-evid2")}
            title="Create the governed EVID-2 draft from a published policy"
            type="button"
          >
            <Copy size={15} /> Clone Gate07J-EVID-2 DRAFT
          </button>
          <button
            disabled={!selected || selected.status !== "published"}
            onClick={() => void execute("clone")}
            type="button"
          >
            <Copy size={15} /> Clone DRAFT
          </button>
          <button disabled={!selected || !parsed} onClick={() => void previewPolicy()} type="button">
            <Eye size={15} /> Preview
          </button>
          <button
            disabled={!selected || selected.status !== "draft" || !parsed}
            onClick={() => void execute("save")}
            type="button"
          >
            <Save size={15} /> Save
          </button>
          <button
            disabled={!selected || selected.status !== "draft" || !parsed}
            onClick={() => void execute("publish")}
            type="button"
          >
            <Send size={15} /> Publish
          </button>
        </div>
      </div>
      <nav aria-label="Investment evidence policy sections" className="evidencePolicyTabs">
        {sections.map((item) => (
          <button
            className={section === item ? "active" : ""}
            key={item}
            onClick={() => setSection(item)}
            type="button"
          >
            {item}
          </button>
        ))}
      </nav>
      <div className="evidencePolicySurface">
        <header>
          <div>
            <Database size={18} />
            <span>{section}</span>
          </div>
          <strong>{selected ? `rev ${selected.revision} · ${selected.status}` : "No policy"}</strong>
        </header>
        {sectionContent()}
      </div>
      <p className="evidencePolicyGuardrail">
        ADMIN configuration only: no Gate preparation transaction, no source-domain recalculation, no Portfolio
        reranking, no automated GO/HOLD/RECYCLE/KILL, no FID, Project activation or execution.
      </p>
    </section>
  );
}
