"""Qualified QRA evidence policy, not a simulation or a second provider.

All inputs here are governed references already supplied by the existing policy,
Project context and QRA result contract. Unknown applicability never silently
turns a configured mandatory requirement off. No expression language, FX,
calendar conversion, probability interpolation or investment decision exists.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

QRA_EVIDENCE_TYPES = {"COST_QRA_RESULT": "COST_QRA", "SCHEDULE_QRA_RESULT": "SCHEDULE_QRA"}
QRA_ANALYSIS_TYPES = frozenset(QRA_EVIDENCE_TYPES.values())
SCHEDULE_CAPABILITIES = {
    "schedule_state": "NOT_STARTED",
    "remaining_duration": "SOURCE_DURATION",
    "calendar_mode": "NORMALIZED_ELAPSED_TIME_V1",
}
QRA_FILTERS = {
    "governance_model_filter": "governance_model",
    "project_type_filter": "project_type",
    "fel_stage_filter": "fel_stage",
    "project_size_filter": "project_size",
    "project_risk_filter": "project_risk",
    "project_complexity_filter": "project_complexity",
    "uncertainty_level_filter": "uncertainty_level",
}
SCHEDULE_LIMITATIONS = [
    "NORMALIZED_ELAPSED_TIME_ONLY_NO_DETAILED_P6_WORK_CALENDARS",
    "NOT_STARTED_ONLY_NO_ACTUAL_PROGRESS_OR_REMAINING_DURATION_MODEL",
]
NUMERIC_OPERATORS = {
    "EQUALS",
    "GREATER_THAN",
    "GREATER_THAN_OR_EQUAL",
    "LESS_THAN",
    "LESS_THAN_OR_EQUAL",
    "WITHIN_RANGE",
}


def is_qra_requirement(row: dict) -> bool:
    return row.get("evidence_type") in QRA_EVIDENCE_TYPES or "qra_policy" in row


def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def qra_policy_issues(row: dict) -> list[str]:
    if not is_qra_requirement(row):
        return []
    qra = row.get("qra_policy") or {}
    if not isinstance(qra, dict):
        return ["INVALID_QRA_POLICY_OBJECT"]
    issues = []
    analysis = qra.get("analysis_type")
    if analysis not in QRA_ANALYSIS_TYPES or QRA_EVIDENCE_TYPES.get(row.get("evidence_type")) != analysis:
        issues.append("QRA_ANALYSIS_TYPE_NOT_RELEASED_OR_MISMATCH")
    if row.get("provider_key") != "QRA_RESULT_PROVIDER":
        issues.append("QRA_SINGLE_QUALIFIED_PROVIDER_REQUIRED")
    if row.get("scope") not in {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"}:
        issues.append("QRA_PROJECT_SCOPE_REQUIRED")
    mode = qra.get("applicability")
    if mode not in {"REQUIRED", "CONDITIONAL", "NOT_REQUIRED", "NOT_APPLICABLE"}:
        issues.append("INVALID_QRA_APPLICABILITY")
    if mode in {"NOT_REQUIRED", "NOT_APPLICABLE"} and row.get("classification") != "C":
        issues.append("QRA_NOT_REQUIRED_REQUIRES_CLASS_C")
    if mode in {"REQUIRED", "CONDITIONAL"} and row.get("classification") == "C":
        issues.append("QRA_REQUIRED_CANNOT_USE_CLASS_C")
    if qra.get("analytical_readiness") not in {"READY_ONLY", "WARNINGS_ALLOWED"}:
        issues.append("INVALID_QRA_ANALYTICAL_READINESS_POLICY")
    if qra.get("convergence") not in {"REQUIRED", "WARNING_ALLOWED", "NOT_REQUIRED"}:
        issues.append("INVALID_QRA_CONVERGENCE_POLICY")
    if qra.get("scope_requirement") not in {"WHOLE_PROJECT", "PARTIAL_ALLOWED"}:
        issues.append("INVALID_QRA_SCOPE_REQUIREMENT")
    for key in QRA_FILTERS:
        values = qra.get(key, ["CAPITAL_OWNER"] if key == "governance_model_filter" else ["*"])
        if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v for v in values):
            issues.append(f"INVALID_QRA_CONTEXT_FILTER:{key}")
    if qra.get("freshness_days") is not None and (
        not isinstance(qra["freshness_days"], int)
        or isinstance(qra["freshness_days"], bool)
        or qra["freshness_days"] < 1
    ):
        issues.append("INVALID_QRA_FRESHNESS_DAYS")
    selected = qra.get("selected_percentiles", [])
    if (
        not isinstance(selected, list)
        or len(selected) > 25
        or any(_number(p) is None or not 0 < _number(p) < 100 for p in selected)
    ):
        issues.append("INVALID_QRA_SELECTED_PERCENTILES")
    band = qra.get("value_band")
    if band is not None:
        if not isinstance(band, dict):
            issues.append("INVALID_QRA_VALUE_BAND")
        else:
            if band.get("source") != "PROJECT_CREATION_ESTIMATED_BUDGET" or not band.get("currency"):
                issues.append("QRA_VALUE_BAND_GOVERNED_SOURCE_CURRENCY_REQUIRED")
            lower, upper = _number(band.get("minimum")), _number(band.get("maximum"))
            if (band.get("minimum") is not None and lower is None) or (
                band.get("maximum") is not None and upper is None
            ):
                issues.append("INVALID_QRA_VALUE_BAND")
            if lower is None and upper is None or lower is not None and upper is not None and lower > upper:
                issues.append("INVALID_QRA_VALUE_BAND")
    # Publication restricts the range to explicitly declared current engine
    # capabilities. An unsupported live Project still blocks; no external
    # evidence authority or automatic exemption is invented.
    if analysis == "SCHEDULE_QRA" and row.get("classification") == "A":
        if qra.get("capability_requirements") != SCHEDULE_CAPABILITIES:
            issues.append("MANDATORY_SCHEDULE_QRA_SUPPORTED_CAPABILITY_RANGE_REQUIRED")
    if qra.get("tail_convergence_required"):
        issues.append("QRA_TAIL_CONVERGENCE_NOT_RELEASED")
    return sorted(set(issues))


def qra_applicability(row: dict, context: dict) -> dict:
    qra = row.get("qra_policy") or {}
    mode = str(qra.get("applicability") or "NOT_REQUIRED")
    reasons = []
    outcome = mode
    if mode not in {"NOT_REQUIRED", "NOT_APPLICABLE"}:
        for key, field in QRA_FILTERS.items():
            allowed = {
                str(v).upper() for v in qra.get(key, ["CAPITAL_OWNER"] if key == "governance_model_filter" else ["*"])
            }
            if "*" in allowed:
                continue
            actual = str(context.get(field) or "UNSPECIFIED").upper()
            if actual in {"UNSPECIFIED", "UNCLASSIFIED", ""}:
                outcome = "NOT_EVALUABLE"
                reasons.append(f"GOVERNED_CONTEXT_MISSING:{field}")
            elif actual not in allowed:
                outcome = "NOT_APPLICABLE"
                reasons.append(f"OUTSIDE_CONFIGURED_QRA_CONTEXT:{field}")
                break
        band = qra.get("value_band")
        if band and outcome != "NOT_APPLICABLE":
            value = _number(context.get("estimated_budget"))
            if value is None or context.get("currency_code") != band.get("currency"):
                outcome = "NOT_EVALUABLE"
                reasons.append("QRA_VALUE_NOT_COMPARABLE_NO_SILENT_FX")
            elif (band.get("minimum") is not None and value < _number(band["minimum"])) or (
                band.get("maximum") is not None and value > _number(band["maximum"])
            ):
                outcome = "NOT_REQUIRED"
                reasons.append("OUTSIDE_CONFIGURED_VALUE_BAND")
        if outcome == "CONDITIONAL":
            outcome = "REQUIRED"
            reasons.append("CONFIGURED_GOVERNED_CONDITIONS_MATCHED")
    return {
        "outcome": outcome,
        "configured_outcome": mode,
        "analysis_type": qra.get("analysis_type"),
        "required": outcome in {"REQUIRED", "NOT_EVALUABLE"},
        "reasons": reasons or [f"PUBLISHED_POLICY_QRA_{outcome}"],
        "context": deepcopy(context),
        "capability_fit": "NOT_APPLICABLE" if outcome in {"NOT_APPLICABLE", "NOT_REQUIRED"} else "NOT_EVALUATED",
    }


def apply_qra_context(row: dict, context: dict) -> dict:
    result = deepcopy(row)
    result["qra_applicability"] = qra_applicability(row, context)
    if not result["qra_applicability"]["required"]:
        result.update(
            classification="C", required=False, blocking=False, provider_required=False, allow_manual_reference=False
        )
    return result


def qra_summary(value: dict, policy: dict) -> dict:
    """Whitelisted compact evidence: never histogram/CDF/sensitivity/samples."""
    keys = (
        "provider_key",
        "provider_contract_version",
        "analysis_type",
        "project_id",
        "run_id",
        "run_number",
        "model_definition_id",
        "model_version",
        "model_number",
        "model_hash",
        "run_hash",
        "trace_hash",
        "engine_version",
        "methodology_id",
        "methodology_revision",
        "methodology_hash",
        "accepted_review_id",
        "accepted_status",
        "acceptance_hash",
        "evidence_hash",
        "analysis_scope",
        "result_semantics",
        "target_probabilities",
        "convergence",
        "readiness",
        "analytical_readiness",
        "quality",
        "warnings",
        "blockers",
        "source_current",
        "as_of",
        "capability_fit",
        "tail_convergence_certified",
    )
    summary = {key: deepcopy(value[key]) for key in keys if key in value}
    selected = {_number(p) for p in policy.get("selected_percentiles", [])}
    summary["selected_percentiles"] = [
        deepcopy(p) for p in value.get("selected_percentiles", []) if _number(p.get("percentile")) in selected
    ][:25]
    summary["tail_convergence_certified"] = False
    summary["convergence_diagnostic_scope"] = "MEAN_ONLY_NOT_P80_P90_P95_OR_TAIL_CERTIFICATION"
    summary["not_investment_approval"] = True
    return summary


def qra_result_issues(row: dict, value: dict, *, now: datetime) -> list[str]:
    qra = row.get("qra_policy") or {}
    blockers = []
    if row.get("qra_applicability", {}).get("outcome") == "NOT_EVALUABLE":
        blockers.append("QRA_APPLICABILITY_NOT_EVALUABLE")
    if value.get("analysis_type") != qra.get("analysis_type"):
        blockers.append("QRA_ANALYSIS_TYPE_MISMATCH")
    if (
        qra.get("scope_requirement") == "WHOLE_PROJECT"
        and value.get("analysis_scope", {}).get("type") != "ENTIRE_PROJECT"
    ):
        blockers.append("QRA_SCOPE_MISMATCH")
    readiness = value.get("analytical_readiness") or value.get("readiness")
    allowed = {"READY", "READY_WITH_WARNINGS"} if qra.get("analytical_readiness") == "WARNINGS_ALLOWED" else {"READY"}
    if readiness not in allowed:
        blockers.append("QRA_ANALYTICAL_READINESS_NOT_MET")
    convergence = value.get("convergence", {}).get("status")
    if qra.get("convergence") == "REQUIRED" and convergence != "CONVERGED":
        blockers.append("QRA_CONVERGENCE_REQUIRED")
    if qra.get("analysis_type") == "SCHEDULE_QRA":
        calendar = value.get("result_semantics", {}).get("schedule_method")
        if calendar != "NORMALIZED_ELAPSED_TIME_V1":
            blockers.append("ENGINE_CAPABILITY_NOT_SUPPORTED")
    selected = {_number(p) for p in qra.get("selected_percentiles", [])}
    actual = {_number(p.get("percentile")) for p in value.get("selected_percentiles", [])}
    if selected - actual:
        blockers.append("QRA_CONFIGURED_PERCENTILE_NOT_IN_OUTPUT_CONTRACT")
    if qra.get("freshness_days") is not None:
        try:
            as_of = datetime.fromisoformat(str(value.get("as_of")).replace("Z", "+00:00"))
            as_of = as_of.astimezone(UTC).replace(tzinfo=None) if as_of.tzinfo else as_of
            comparable_now = now.astimezone(UTC).replace(tzinfo=None) if now.tzinfo else now
            if (comparable_now - as_of).total_seconds() > qra["freshness_days"] * 86400 or as_of > comparable_now:
                blockers.append("QRA_EVIDENCE_EXPIRED")
        except (TypeError, ValueError):
            blockers.append("QRA_FRESHNESS_NOT_EVALUABLE")
    return sorted(set(blockers))


def qra_criterion_issues(row: dict) -> list[str]:
    source = row.get("source_evidence_type")
    if source not in QRA_EVIDENCE_TYPES:
        return []
    qra = row.get("qra_criterion") or {}
    if not isinstance(qra, dict):
        return ["INVALID_QRA_CRITERION_OBJECT"]
    metric = qra.get("metric")
    issues = []
    if qra.get("analysis_type") != QRA_EVIDENCE_TYPES[source]:
        issues.append("QRA_CRITERION_ANALYSIS_TYPE_MISMATCH")
    if metric not in {"PERCENTILE", "TARGET_PROBABILITY", "ANALYTICAL_READINESS", "CONVERGENCE"}:
        issues.append("INVALID_QRA_CRITERION_METRIC")
    if metric in {"PERCENTILE", "TARGET_PROBABILITY"}:
        if row.get("operator") not in NUMERIC_OPERATORS:
            issues.append("INVALID_QRA_CRITERION_OPERATOR")
        target = qra.get("target") or {}
        if not isinstance(target, dict):
            return ["INVALID_QRA_CRITERION_TARGET_OBJECT"]
        target_values = target.get("value")
        target_values = target_values if isinstance(target_values, list) else [target_values]
        if target.get("source") != "GATE_CRITERION" or target.get("value") is None:
            issues.append("QRA_CRITERION_GOVERNED_TARGET_REQUIRED")
        if qra.get("analysis_type") == "COST_QRA":
            if not qra.get("currency") or target.get("currency") != qra.get("currency"):
                issues.append("QRA_CRITERION_CURRENCY_REQUIRED_NO_SILENT_FX")
            if any(_number(value) is None for value in target_values):
                issues.append("INVALID_QRA_CRITERION_COST_TARGET")
        else:
            if qra.get("unit") not in {"HOURS", "DAYS"} or qra.get("time_basis") != "NORMALIZED_ELAPSED_TIME_V1":
                issues.append("QRA_CRITERION_NORMALIZED_ELAPSED_TIME_REQUIRED")
            if target.get("time_basis") != qra.get("time_basis") or target.get("unit") != qra.get("unit"):
                issues.append("QRA_CRITERION_TARGET_TIME_BASIS_MISMATCH")
            for value in target_values:
                try:
                    datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                except (TypeError, ValueError):
                    issues.append("INVALID_QRA_CRITERION_DATE_TARGET")
        if metric == "PERCENTILE":
            p = _number(qra.get("percentile"))
            if p is None or not 0 < p < 100:
                issues.append("INVALID_QRA_CRITERION_PERCENTILE")
            if row.get("expected_value") != target.get("value"):
                issues.append("QRA_PERCENTILE_TARGET_THRESHOLD_MISMATCH")
        else:
            thresholds = row.get("expected_value")
            thresholds = thresholds if isinstance(thresholds, list) else [thresholds]
            if any(_number(value) is None or not 0 <= _number(value) <= 1 for value in thresholds):
                issues.append("QRA_PROBABILITY_THRESHOLD_MUST_BE_FRACTION_0_TO_1")
            if isinstance(target.get("value"), list):
                issues.append("QRA_PROBABILITY_STORED_TARGET_MUST_BE_SINGLE_VALUE")
    if row.get("operator") == "WITHIN_RANGE":
        limits = row.get("expected_value")
        if not isinstance(limits, list) or len(limits) != 2:
            issues.append("QRA_CONTROLLED_RANGE_REQUIRED")
        elif qra.get("analysis_type") == "COST_QRA" or metric == "TARGET_PROBABILITY":
            lower, upper = _number(limits[0]), _number(limits[1])
            if lower is None or upper is None or lower > upper:
                issues.append("INVALID_QRA_CONTROLLED_RANGE")
        else:
            try:
                bounds = [datetime.fromisoformat(str(value).replace("Z", "+00:00")) for value in limits]
                bounds = [
                    value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC) for value in bounds
                ]
                if bounds[0] > bounds[1]:
                    issues.append("INVALID_QRA_CONTROLLED_RANGE")
            except (TypeError, ValueError):
                issues.append("INVALID_QRA_CONTROLLED_RANGE")
    return sorted(set(issues))


def qra_criterion_value(configured: dict, source: dict) -> tuple[Any, dict, list[str]]:
    qra = configured.get("qra_criterion") or {}
    payload = source.get("source_payload") or {}
    metric = qra.get("metric")
    semantics = payload.get("result_semantics") or {}
    details = {
        "analysis_type": qra.get("analysis_type"),
        "metric": metric,
        "target": deepcopy(qra.get("target")),
        "run_id": payload.get("run_id"),
        "run_hash": payload.get("run_hash"),
        "acceptance_hash": payload.get("acceptance_hash"),
        "evidence_hash": source.get("source_hash"),
        "tail_convergence_certified": False,
        "convergence_diagnostic_scope": "MEAN_ONLY",
        "qra_applicability": deepcopy(source.get("qra_applicability") or {}),
    }
    if payload.get("analysis_type") != qra.get("analysis_type") or source.get("status") != "VALID":
        return None, details, ["QRA_CRITERION_SOURCE_INELIGIBLE"]
    if metric == "ANALYTICAL_READINESS":
        return payload.get("analytical_readiness") or payload.get("readiness"), details, []
    if metric == "CONVERGENCE":
        return payload.get("convergence", {}).get("status"), details, ["MEAN_CONVERGENCE_ONLY_NO_TAIL_CERTIFICATION"]
    if qra.get("analysis_type") == "COST_QRA":
        if qra.get("currency") != semantics.get("currency"):
            return None, details, ["QRA_CRITERION_CURRENCY_MISMATCH_NO_SILENT_FX"]
    elif qra.get("unit") != semantics.get("unit") or qra.get("time_basis") != semantics.get("schedule_method"):
        return None, details, ["QRA_CRITERION_TIME_BASIS_MISMATCH"]
    if metric == "PERCENTILE":
        details["percentile"] = qra.get("percentile")
        item = next(
            (
                p
                for p in payload.get("selected_percentiles", [])
                if _number(p.get("percentile")) == _number(qra.get("percentile"))
            ),
            None,
        )
        value = item.get("date") or item.get("completion_date") or item.get("value") if item else None
        return value, details, ["MEAN_CONVERGENCE_ONLY_NO_TAIL_CERTIFICATION"]
    target = qra.get("target") or {}
    key = (
        "probability_meeting_target_amount"
        if qra.get("analysis_type") == "COST_QRA"
        else "probability_meeting_target_date"
    )
    stored_target = (
        semantics.get("target_amount") if qra.get("analysis_type") == "COST_QRA" else semantics.get("target_date")
    )
    if qra.get("analysis_type") == "COST_QRA":
        compatible = _number(stored_target) == _number(target.get("value")) and _number(stored_target) is not None
    else:
        try:
            dates = [
                datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                for value in (stored_target, target.get("value"))
            ]
            dates = [value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC) for value in dates]
            compatible = dates[0] == dates[1]
        except (TypeError, ValueError, OverflowError):
            compatible = False
    if not compatible:
        return None, details, ["QRA_TARGET_PROVENANCE_VALUE_MISMATCH_NO_RECALCULATION"]
    probabilities = payload.get("target_probabilities", {})
    return probabilities.get(key), details, []
