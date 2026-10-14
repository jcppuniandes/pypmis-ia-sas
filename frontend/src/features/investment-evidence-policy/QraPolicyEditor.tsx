import type { EvidencePolicyContent, EvidenceRequirement, GateDecisionCriterion, QraEvidencePolicy } from "./types";
import "./qraEvidence.css";

import { QRA_EVIDENCE_TYPES } from "./types";

function defaultRequirement(type: (typeof QRA_EVIDENCE_TYPES)[number]): EvidenceRequirement {
  const analysis = type === "COST_QRA_RESULT" ? "COST_QRA" : "SCHEDULE_QRA";
  return {
    requirement_key: type.toLowerCase().replace(/_/g, "-"),
    evidence_type: type,
    classification: "C",
    required: false,
    blocking: false,
    scope: "EACH_PROJECT",
    provider_key: "QRA_RESULT_PROVIDER",
    provider_required: false,
    allow_manual_reference: false,
    manual_validation_required: false,
    rationale: "Contextual accepted/current QRA evidence; never an investment decision.",
    order: analysis === "COST_QRA" ? 170 : 180,
    qra_policy: {
      analysis_type: analysis,
      applicability: "NOT_REQUIRED",
      governance_model_filter: ["CAPITAL_OWNER"],
      project_type_filter: ["*"],
      fel_stage_filter: ["*"],
      project_risk_filter: ["*"],
      project_complexity_filter: ["*"],
      uncertainty_level_filter: ["*"],
      analytical_readiness: "WARNINGS_ALLOWED",
      convergence: "WARNING_ALLOWED",
      scope_requirement: "WHOLE_PROJECT",
      selected_percentiles: [50, 80, 90],
      bc_consistency_required: false,
      ...(analysis === "SCHEDULE_QRA"
        ? {
            capability_requirements: {
              schedule_state: "NOT_STARTED" as const,
              remaining_duration: "SOURCE_DURATION" as const,
              calendar_mode: "NORMALIZED_ELAPSED_TIME_V1" as const,
            },
          }
        : {}),
    },
  };
}

function ControlledSelect({
  label,
  values,
  value,
  disabled,
  onChange,
}: {
  label: string;
  values: string[];
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label>
      {label}
      <select aria-label={label} disabled={disabled} onChange={(event) => onChange(event.target.value)} value={value}>
        {Array.from(new Set([...values, value])).map((item) => (
          <option key={item} value={item}>
            {item === "*" ? "All governed values" : item}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function QraPolicyEditor({
  content,
  disabled,
  profile,
  onChange,
}: {
  content: EvidencePolicyContent;
  disabled: boolean;
  profile: string;
  onChange: (value: EvidencePolicyContent) => void;
}) {
  const requirements = content.gate_profiles[profile]?.requirements || [];
  function replace(type: string, requirement: EvidenceRequirement) {
    const existing = content.gate_profiles[profile];
    if (!existing) return;
    const present = requirements.some((item) => item.evidence_type === type);
    onChange({
      ...content,
      gate_profiles: {
        ...content.gate_profiles,
        [profile]: {
          ...existing,
          requirements: present
            ? requirements.map((item) => (item.evidence_type === type ? requirement : item))
            : [...requirements, requirement],
        },
      },
    });
  }
  function addCriterion(type: (typeof QRA_EVIDENCE_TYPES)[number]) {
    const analysis = type === "COST_QRA_RESULT" ? "COST_QRA" : "SCHEDULE_QRA";
    const newCriterion: GateDecisionCriterion = {
      criterion_code: `${profile}-${analysis}-PERCENTILE-${criteria.length + 1}`,
      criterion_name: `${analysis === "COST_QRA" ? "Cost" : "Schedule"} QRA governed evidence criterion`,
      criterion_type: "DECISION_HURDLE",
      source_evidence_type: type,
      source_field: "source_payload",
      scope: "EACH_PROJECT",
      gate_profiles: [profile],
      operator: "LESS_THAN_OR_EQUAL",
      expected_value: "",
      required: false,
      blocking: false,
      qra_criterion: {
        analysis_type: analysis,
        metric: "PERCENTILE",
        percentile: 80,
        target: {
          source: "GATE_CRITERION",
          value: "",
          ...(analysis === "COST_QRA" ? { currency: "" } : { unit: "DAYS", time_basis: "NORMALIZED_ELAPSED_TIME_V1" }),
        },
        ...(analysis === "COST_QRA" ? { currency: "" } : { unit: "DAYS", time_basis: "NORMALIZED_ELAPSED_TIME_V1" }),
      },
    };
    updateCriteria([...criteria, newCriterion]);
  }
  const criteria =
    content.decision_criterion_policy?.criteria_by_profile?.[profile] ||
    (content.decision_criteria || []).filter((item) => !item.gate_profiles || item.gate_profiles.includes(profile));
  function updateCriteria(next: GateDecisionCriterion[]) {
    onChange({
      ...content,
      decision_criterion_policy: {
        ...content.decision_criterion_policy,
        criteria_by_profile: { ...content.decision_criterion_policy?.criteria_by_profile, [profile]: next },
      },
    });
  }
  function updateCriterion(index: number, next: GateDecisionCriterion) {
    updateCriteria(criteria.map((item, position) => (position === index ? next : item)));
  }
  return (
    <section aria-label="Contextual QRA evidence policy" className="qraPolicyEditor">
      <div className="evidencePolicyCallout">
        <div>
          <strong>Contextual QRA Evidence ≠ Universal QRA Requirement</strong>
          <span>
            One QRA_RESULT_PROVIDER, separate Cost and Schedule requirements. Only accepted/current evidence is
            consumed. Integrated Cost-Schedule QRA is NOT RELEASED and cannot be required.
          </span>
          <span>
            Clone a published revision, edit DRAFT, preview, save and publish through the existing policy lifecycle.
          </span>
        </div>
      </div>
      {QRA_EVIDENCE_TYPES.map((type) => {
        const requirement = requirements.find((item) => item.evidence_type === type);
        const policy = requirement?.qra_policy;
        if (!requirement || !policy) {
          return (
            <article key={type}>
              <h3>{type === "COST_QRA_RESULT" ? "Cost QRA Result" : "Schedule QRA Result"}</h3>
              <p>No contextual requirement configured for {profile}. Existing published rules remain unchanged.</p>
              <button disabled={disabled} onClick={() => replace(type, defaultRequirement(type))} type="button">
                Add {type === "COST_QRA_RESULT" ? "Cost" : "Schedule"} QRA requirement
              </button>
            </article>
          );
        }
        const prefix = policy.analysis_type === "COST_QRA" ? "Cost QRA" : "Schedule QRA";
        const updatePolicy = (patch: Partial<QraEvidencePolicy>) =>
          replace(type, { ...requirement, qra_policy: { ...policy, ...patch } });
        return (
          <article key={type}>
            <h3>
              {prefix} Result · {profile}
            </h3>
            <p>Provider QRA_RESULT_PROVIDER · manual fallback not allowed · scope EACH_PROJECT</p>
            <div className="qraPolicyFields">
              <ControlledSelect
                disabled={disabled}
                label={`${prefix} applicability`}
                onChange={(value) => {
                  const applicability = value as QraEvidencePolicy["applicability"];
                  replace(type, {
                    ...requirement,
                    ...(value === "NOT_REQUIRED" || value === "NOT_APPLICABLE"
                      ? { classification: "C", required: false, blocking: false, provider_required: false }
                      : {}),
                    qra_policy: { ...policy, applicability },
                  });
                }}
                value={policy.applicability}
                values={["REQUIRED", "CONDITIONAL", "NOT_REQUIRED", "NOT_APPLICABLE"]}
              />
              <ControlledSelect
                disabled={disabled}
                label={`${prefix} evidence class`}
                onChange={(value) =>
                  replace(type, {
                    ...requirement,
                    classification: value as EvidenceRequirement["classification"],
                    required: value !== "C",
                    blocking: value === "A",
                    provider_required: value === "A",
                    allow_manual_reference: false,
                    qra_policy: {
                      ...policy,
                      applicability:
                        value === "C"
                          ? "NOT_REQUIRED"
                          : policy.applicability === "NOT_REQUIRED"
                            ? "REQUIRED"
                            : policy.applicability,
                    },
                  })
                }
                value={requirement.classification}
                values={["A", "B", "C"]}
              />
              {(
                [
                  [
                    "governance_model_filter",
                    "Governance Model",
                    ["CAPITAL_OWNER", "CONTRACTOR_DELIVERY", "DIRECT_INTERNAL", "LEGACY_UNCLASSIFIED", "*"],
                  ],
                  ["project_type_filter", "Project Type", ["*", "COMMERCIAL", "PUBLIC", "MIXED", "INTERNAL"]],
                  ["fel_stage_filter", "FEL Stage", ["*", "FEL1", "FEL2", "FEL3", "FEL-1", "FEL-2", "FEL-3"]],
                  ["project_risk_filter", "Risk", ["*", "LOW", "MEDIUM", "HIGH", "UNSPECIFIED"]],
                  ["project_complexity_filter", "Complexity", ["*", "LOW", "MEDIUM", "HIGH", "UNSPECIFIED"]],
                  ["uncertainty_level_filter", "Uncertainty", ["*", "LOW", "MEDIUM", "HIGH", "UNSPECIFIED"]],
                ] as const
              ).map(([key, label, values]) => (
                <label key={key}>
                  {prefix} {label}
                  <select
                    aria-label={`${prefix} ${label}`}
                    disabled={disabled}
                    multiple
                    onChange={(event) =>
                      updatePolicy({ [key]: Array.from(event.target.selectedOptions, (option) => option.value) })
                    }
                    value={policy[key]}
                  >
                    {Array.from(new Set([...values, ...policy[key]])).map((value) => (
                      <option key={value}>{value}</option>
                    ))}
                  </select>
                </label>
              ))}
              <ControlledSelect
                disabled={disabled}
                label={`${prefix} analytical readiness`}
                onChange={(value) =>
                  updatePolicy({ analytical_readiness: value as QraEvidencePolicy["analytical_readiness"] })
                }
                value={policy.analytical_readiness}
                values={["READY_ONLY", "WARNINGS_ALLOWED"]}
              />
              <ControlledSelect
                disabled={disabled}
                label={`${prefix} convergence`}
                onChange={(value) => updatePolicy({ convergence: value as QraEvidencePolicy["convergence"] })}
                value={policy.convergence}
                values={["REQUIRED", "WARNING_ALLOWED", "NOT_REQUIRED"]}
              />
              <ControlledSelect
                disabled={disabled}
                label={`${prefix} scope requirement`}
                onChange={(value) =>
                  updatePolicy({ scope_requirement: value as QraEvidencePolicy["scope_requirement"] })
                }
                value={policy.scope_requirement}
                values={["WHOLE_PROJECT", "PARTIAL_ALLOWED"]}
              />
              <label>
                {prefix} freshness days
                <input
                  aria-label={`${prefix} freshness days`}
                  disabled={disabled}
                  min={1}
                  type="number"
                  value={policy.freshness_days ?? ""}
                  onChange={(event) =>
                    updatePolicy({ freshness_days: event.target.value ? Number(event.target.value) : null })
                  }
                />
              </label>
              <label>
                {prefix} selected percentiles
                <select
                  aria-label={`${prefix} selected percentiles`}
                  disabled={disabled}
                  multiple
                  value={(policy.selected_percentiles || []).map(String)}
                  onChange={(event) =>
                    updatePolicy({
                      selected_percentiles: Array.from(event.target.selectedOptions, (option) => Number(option.value)),
                    })
                  }
                >
                  {Array.from(new Set([5, 10, 20, 50, 80, 90, 95, ...(policy.selected_percentiles || [])]))
                    .sort((a, b) => a - b)
                    .map((value) => (
                      <option key={value}>{value}</option>
                    ))}
                </select>
              </label>
              <label className="qraPolicyCheckbox">
                <input
                  aria-label={`${prefix} BC consistency required`}
                  disabled={disabled}
                  checked={policy.bc_consistency_required}
                  type="checkbox"
                  onChange={(event) => updatePolicy({ bc_consistency_required: event.target.checked })}
                />
                BC QRA reference must match Gate evidence
              </label>
              <label className="qraPolicyCheckbox">
                <input
                  aria-label={`${prefix} value band enabled`}
                  disabled={disabled}
                  checked={Boolean(policy.value_band)}
                  type="checkbox"
                  onChange={(event) => {
                    const next = { ...policy };
                    if (event.target.checked)
                      next.value_band = { source: "PROJECT_CREATION_ESTIMATED_BUDGET", currency: "" };
                    else delete next.value_band;
                    replace(type, { ...requirement, qra_policy: next });
                  }}
                />
                Governed estimated-budget value band (no FX)
              </label>
              {policy.value_band ? (
                <>
                  <label>
                    {prefix} value currency
                    <input
                      aria-label={`${prefix} value currency`}
                      disabled={disabled}
                      maxLength={3}
                      value={policy.value_band.currency}
                      onChange={(event) =>
                        updatePolicy({
                          value_band: { ...policy.value_band!, currency: event.target.value.toUpperCase() },
                        })
                      }
                    />
                  </label>
                  {(["minimum", "maximum"] as const).map((key) => (
                    <label key={key}>
                      {prefix} value {key}
                      <input
                        aria-label={`${prefix} value ${key}`}
                        disabled={disabled}
                        min={0}
                        type="number"
                        value={policy.value_band?.[key] ?? ""}
                        onChange={(event) =>
                          updatePolicy({
                            value_band: {
                              ...policy.value_band!,
                              [key]: event.target.value ? Number(event.target.value) : undefined,
                            },
                          })
                        }
                      />
                    </label>
                  ))}
                </>
              ) : null}
            </div>
            {policy.analysis_type === "SCHEDULE_QRA" ? (
              <p className="qraCapabilityNotice">
                Capability constraints: NOT_STARTED activities only; remaining duration = source duration;
                NORMALIZED_ELAPSED_TIME_V1. No actual progress, detailed P6 shifts/holidays or work-calendar conversion.
              </p>
            ) : null}
            <p className="qraCapabilityNotice">
              CONVERGED certifies mean stability only, not P90/P95 or tail convergence. Percentile output must exist in
              the approved methodology; no interpolation.
            </p>
            <button disabled={disabled} onClick={() => addCriterion(type)} type="button">
              Add {prefix} decision criterion
            </button>
          </article>
        );
      })}
      {criteria.map((criterion, index) => {
        const qra = criterion.qra_criterion as Record<string, unknown> | undefined;
        if (!qra || !(criterion.gate_profiles || [profile]).includes(profile)) return null;
        const target = (qra.target || {}) as Record<string, unknown>;
        const cost = qra.analysis_type === "COST_QRA";
        const label = `QRA criterion ${criterion.criterion_code}`;
        const updateQra = (patch: Record<string, unknown>) =>
          updateCriterion(index, { ...criterion, qra_criterion: { ...qra, ...patch } });
        return (
          <article aria-label={label} key={`${criterion.criterion_code}-${index}`}>
            <h3>{criterion.criterion_code}</h3>
            <div className="qraPolicyFields">
              <ControlledSelect
                disabled={disabled}
                label={`${label} metric`}
                value={String(qra.metric)}
                values={["PERCENTILE", "TARGET_PROBABILITY"]}
                onChange={(value) => updateQra({ metric: value })}
              />
              <ControlledSelect
                disabled={disabled}
                label={`${label} operator`}
                value={criterion.operator}
                values={[
                  "GREATER_THAN",
                  "GREATER_THAN_OR_EQUAL",
                  "LESS_THAN",
                  "LESS_THAN_OR_EQUAL",
                  "EQUALS",
                  "WITHIN_RANGE",
                ]}
                onChange={(value) => updateCriterion(index, { ...criterion, operator: value })}
              />
              {qra.metric === "PERCENTILE" ? (
                <label>
                  Percentile
                  <input
                    aria-label={`${label} percentile`}
                    disabled={disabled}
                    min={1}
                    max={99}
                    type="number"
                    value={Number(qra.percentile || 80)}
                    onChange={(event) => updateQra({ percentile: Number(event.target.value) })}
                  />
                </label>
              ) : null}
              <label>
                Governed target ({cost ? "amount" : "UTC date"})
                <input
                  aria-label={`${label} target`}
                  disabled={disabled}
                  type={cost ? "number" : "datetime-local"}
                  value={cost ? String(target.value ?? "") : String(target.value || "").slice(0, 16)}
                  onChange={(event) => {
                    const value = cost
                      ? event.target.value === ""
                        ? ""
                        : Number(event.target.value)
                      : event.target.value
                        ? `${event.target.value}:00Z`
                        : "";
                    updateCriterion(index, {
                      ...criterion,
                      ...(qra.metric === "PERCENTILE" ? { expected_value: value } : {}),
                      qra_criterion: { ...qra, target: { ...target, source: "GATE_CRITERION", value } },
                    });
                  }}
                />
              </label>
              {cost ? (
                <label>
                  Target currency
                  <input
                    aria-label={`${label} currency`}
                    disabled={disabled}
                    maxLength={3}
                    value={String(qra.currency || "")}
                    onChange={(event) =>
                      updateQra({
                        currency: event.target.value.toUpperCase(),
                        target: { ...target, currency: event.target.value.toUpperCase() },
                      })
                    }
                  />
                </label>
              ) : (
                <ControlledSelect
                  disabled={disabled}
                  label={`${label} elapsed unit`}
                  value={String(qra.unit || "DAYS")}
                  values={["HOURS", "DAYS"]}
                  onChange={(value) =>
                    updateQra({
                      unit: value,
                      target: { ...target, unit: value, time_basis: "NORMALIZED_ELAPSED_TIME_V1" },
                    })
                  }
                />
              )}
              {qra.metric === "TARGET_PROBABILITY" ? (
                <label>
                  Expected probability (0–1)
                  <input
                    aria-label={`${label} expected probability`}
                    disabled={disabled}
                    min={0}
                    max={1}
                    step={0.01}
                    type="number"
                    value={String(criterion.expected_value ?? "")}
                    onChange={(event) =>
                      updateCriterion(index, { ...criterion, expected_value: Number(event.target.value) })
                    }
                  />
                </label>
              ) : null}
              {criterion.operator === "WITHIN_RANGE" ? (
                <label>
                  Expected range (min, max)
                  <input
                    aria-label={`${label} expected range`}
                    disabled={disabled}
                    value={Array.isArray(criterion.expected_value) ? criterion.expected_value.join(", ") : ""}
                    onChange={(event) => {
                      const range = event.target.value
                        .split(",")
                        .map((value) =>
                          cost || qra.metric === "TARGET_PROBABILITY" ? Number(value.trim()) : value.trim()
                        );
                      updateCriterion(index, {
                        ...criterion,
                        expected_value: range,
                        ...(qra.metric === "PERCENTILE"
                          ? { qra_criterion: { ...qra, target: { ...target, value: range } } }
                          : {}),
                      });
                    }}
                  />
                </label>
              ) : null}
              <label className="qraPolicyCheckbox">
                <input
                  aria-label={`${label} blocking`}
                  disabled={disabled}
                  type="checkbox"
                  checked={criterion.blocking}
                  onChange={(event) =>
                    updateCriterion(index, {
                      ...criterion,
                      required: event.target.checked,
                      blocking: event.target.checked,
                    })
                  }
                />
                Required / blocking
              </label>
            </div>
            <p>
              Target provenance: GATE_CRITERION. Probability is read from the accepted run only when its frozen target
              matches; no new calculation, silent FX or work-calendar conversion.
            </p>
          </article>
        );
      })}
    </section>
  );
}
