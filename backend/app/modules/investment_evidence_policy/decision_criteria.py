"""Controlled Gate 07J decision-criterion contracts and evaluation.

Evidence classification (A/B/C) answers whether governed evidence is required.
This module answers a different question: whether a frozen value satisfies a
configured Gate decision criterion.  It deliberately contains no executable
expression language and never emits a formal Gate 07K outcome.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any

DECISION_CRITERION_TYPES = (
    "READINESS_CHECK",
    "MUST_MEET",
    "DECISION_HURDLE",
    "PRIORITIZATION",
    "SUCCESS_CRITERION",
)

# Public aliases keep the names used by the Gate 07J-EVID-2 contract while the
# longer internal names remain self-documenting.
CRITERION_TYPES = DECISION_CRITERION_TYPES

CONTROLLED_OPERATORS = (
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
)

CRITERION_RESULTS = (
    "SATISFIED",
    "NOT_SATISFIED",
    "NOT_APPLICABLE",
    "NOT_EVALUABLE",
    "STALE",
)

EVIDENCE_QUALITY_STATES = (
    "VALIDATED",
    "PARTIALLY_VALIDATED",
    "PRELIMINARY",
    "LOW_CONFIDENCE",
    "NOT_VALIDATED",
    "NOT_APPLICABLE",
    "NOT_AVAILABLE",
)
EVIDENCE_QUALITY_STATUSES = EVIDENCE_QUALITY_STATES

MANDATORY_CRITERION_TYPES = frozenset({"READINESS_CHECK", "MUST_MEET", "DECISION_HURDLE"})
READY_VALUES = frozenset({"READY", "VALID", "SATISFIED", "AVAILABLE", "PASS", "PASSED"})
FEL_LEVELS = {"FEL-0": 0, "FEL-1": 1, "FEL-2": 2, "FEL-3": 3, "FFA": 3}


def criterion(
    code: str,
    name: str,
    criterion_type: str,
    source_evidence_type: str,
    source_field: str,
    operator: str,
    expected_value: Any,
    *,
    blocking: bool,
    required: bool,
    scope: str = "EACH_PROJECT",
    order: int,
    project_types: list[str] | None = None,
    governance_models: list[str] | None = None,
    uncertainty_levels: list[str] | None = None,
    fel_stages: list[str] | None = None,
    project_sizes: list[str] | None = None,
    project_risks: list[str] | None = None,
    project_complexities: list[str] | None = None,
    weight: float | None = None,
    success_snapshot_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Build one serializable criterion without exposing an expression language."""

    return {
        "criterion_id": code,
        "criterion_code": code,
        "criterion_name": name,
        "criterion_type": criterion_type,
        "source_evidence_type": source_evidence_type,
        "source_field": source_field,
        "operator": operator,
        "expected_value": deepcopy(expected_value),
        "blocking": blocking,
        "required": required,
        "scope": scope,
        "weight": weight,
        "project_type_filter": project_types or ["*"],
        "governance_model_filter": governance_models or ["CAPITAL_OWNER"],
        "uncertainty_level_filter": uncertainty_levels or ["*"],
        "fel_stage_filter": fel_stages or ["*"],
        "project_size_filter": project_sizes or ["*"],
        "project_risk_filter": project_risks or ["*"],
        "project_complexity_filter": project_complexities or ["*"],
        "success_snapshot_fields": success_snapshot_fields or [],
        "status": "ACTIVE",
        "order": order,
    }


def starter_criteria(gate_profile_code: str) -> list[dict[str, Any]]:
    """Return proportional starter criteria for Select or FFA.

    The criteria consume provider values.  They do not recalculate Business
    Case, FIN, Benefits, FEL, Commercial, Funding, Risk, Permit, or Portfolio
    logic.
    """

    ffa = gate_profile_code == "PYP-FFA"
    minimum_fel = "FEL-3" if ffa else "FEL-2"
    rows = [
        criterion(
            "BC-SOURCE-CURRENT",
            "Business Case source is current",
            "READINESS_CHECK",
            "BUSINESS_CASE_READINESS",
            "source_current",
            "IS_CURRENT",
            True,
            blocking=True,
            required=True,
            order=10,
        ),
        criterion(
            "FEL-SOURCE-CURRENT",
            "Project Definition source is current",
            "READINESS_CHECK",
            "PROJECT_DEFINITION_READINESS",
            "source_current",
            "IS_CURRENT",
            True,
            blocking=True,
            required=True,
            order=20,
        ),
        criterion(
            "BC-FIVE-CASE-READINESS",
            "Stage-appropriate Five Case readiness",
            "MUST_MEET",
            "BUSINESS_CASE_READINESS",
            "source_payload.five_case_readiness.overall_business_case_readiness",
            "IS_READY",
            "READY",
            blocking=True,
            required=True,
            order=30,
        ),
        criterion(
            "FEL-MINIMUM-STAGE",
            f"Minimum definition maturity {minimum_fel}",
            "MUST_MEET",
            "PROJECT_DEFINITION_READINESS",
            "source_payload.FEL_stage_code",
            "GREATER_THAN_OR_EQUAL",
            minimum_fel,
            blocking=True,
            required=True,
            order=40,
        ),
        criterion(
            "PORTFOLIO-RECOMMENDATION-CONTEXT",
            "Portfolio recommendation is available",
            "PRIORITIZATION",
            "PORTFOLIO_CONTEXT",
            "portfolio_recommendation_ready",
            "IS_TRUE",
            True,
            blocking=False,
            required=True,
            scope="PORTFOLIO",
            order=90,
        ),
        criterion(
            "BENEFIT-TARGET-COMMITMENTS",
            "Benefits targets available for decision accountability",
            "SUCCESS_CRITERION",
            "BENEFITS_PLAN_READINESS",
            "source_payload.target_coverage",
            "COVERAGE_AT_LEAST",
            100,
            blocking=False,
            required=ffa,
            order=100,
            success_snapshot_fields=[
                "benefit_snapshots",
                "benefits_plan_id",
                "plan_version_id",
                "benefits_plan_hash",
                "as_of_date",
            ],
        ),
    ]
    if ffa:
        rows[2]["criterion_name"] = "All required Five Cases are READY"
        rows.extend(
            [
                criterion(
                    "FIN-READINESS",
                    "Economic and financial model is READY",
                    "MUST_MEET",
                    "ECONOMIC_FINANCIAL_READINESS",
                    "readiness_status",
                    "IS_READY",
                    "READY",
                    blocking=True,
                    required=True,
                    order=50,
                ),
                criterion(
                    "COMMERCIAL-READINESS",
                    "Commercial strategy is READY",
                    "MUST_MEET",
                    # The canonical evidence type predates the governed
                    # Commercial provider.  Keep the type stable and reuse the
                    # exact provider key rather than creating a second row.
                    "CONTRACTING_STRATEGY_READINESS",
                    "readiness_status",
                    "IS_READY",
                    "READY",
                    blocking=True,
                    required=True,
                    order=60,
                ),
                criterion(
                    "BENEFIT-OWNER-COVERAGE",
                    "Benefit Owner coverage is complete",
                    "MUST_MEET",
                    "BENEFITS_PLAN_READINESS",
                    "source_payload.benefit_owner_coverage",
                    "COVERAGE_AT_LEAST",
                    100,
                    blocking=True,
                    required=True,
                    order=70,
                ),
                criterion(
                    "FIN-NPV-HURDLE",
                    "Configured project financial NPV hurdle",
                    "DECISION_HURDLE",
                    "ECONOMIC_FINANCIAL_READINESS",
                    "source_payload.project_financial_npv",
                    "GREATER_THAN_OR_EQUAL",
                    0,
                    blocking=False,
                    required=False,
                    project_types=["COMMERCIAL", "REVENUE", "COMMERCIAL_PROJECT", "MIXED", "MIXED_PROJECT"],
                    order=80,
                ),
            ]
        )
    return sorted(rows, key=lambda item: int(item["order"]))


def decision_criterion_policy(source: dict[str, Any]) -> dict[str, Any]:
    """Return the criterion layer, kept separate from A/B/C evidence matrices."""

    configured = deepcopy(source.get("decision_criterion_policy") or {})
    configured.setdefault("policy_code", "PYP-GATE-DECISION-CRITERIA")
    configured.setdefault("effective_from", source.get("effective_from"))
    configured.setdefault("criterion_types", list(DECISION_CRITERION_TYPES))
    configured.setdefault("controlled_operators", list(CONTROLLED_OPERATORS))
    configured.setdefault("evidence_quality_states", list(EVIDENCE_QUALITY_STATES))
    configured.setdefault("unsafe_expression_execution", False)
    configured.setdefault("formal_decision_authority", "GATE07K")
    configured.setdefault("portfolio_rank_authority", "PORTFOLIO")
    configured.setdefault("criteria_by_profile", {})
    for profile_code in ("PYP-INV-SELECT", "PYP-FFA"):
        configured["criteria_by_profile"].setdefault(profile_code, starter_criteria(profile_code))
    configured.setdefault(
        "tailoring_dimensions",
        [
            "GATE_PROFILE",
            "FEL_STAGE",
            "PROJECT_TYPE",
            "GOVERNANCE_MODEL",
            "PROJECT_SIZE",
            "PROJECT_RISK",
            "PROJECT_COMPLEXITY",
            "UNCERTAINTY_LEVEL",
        ],
    )
    configured.setdefault("new_round_policy", "CURRENT_EFFECTIVE_POLICY_REQUIRES_NEW_GATE07J_PREPARATION")
    return configured


def validate_criterion_policy(source: dict[str, Any], evidence_types: set[str]) -> list[str]:
    policy = decision_criterion_policy(source)
    issues: list[str] = []
    if set(policy.get("criterion_types", [])) != set(DECISION_CRITERION_TYPES):
        issues.append("INVALID_DECISION_CRITERION_TAXONOMY")
    if set(policy.get("controlled_operators", [])) - set(CONTROLLED_OPERATORS):
        issues.append("UNSAFE_OR_UNKNOWN_CRITERION_OPERATOR")
    if policy.get("unsafe_expression_execution") is not False:
        issues.append("UNSAFE_EXPRESSION_EXECUTION_NOT_ALLOWED")
    for profile_code in ("PYP-INV-SELECT", "PYP-FFA"):
        rows = list(policy.get("criteria_by_profile", {}).get(profile_code, []))
        if not rows:
            issues.append(f"MISSING_DECISION_CRITERIA:{profile_code}")
            continue
        keys: set[str] = set()
        for row in rows:
            code = str(row.get("criterion_code") or row.get("criterion_id") or "")
            if not code or code in keys:
                issues.append(f"INVALID_DECISION_CRITERION_CODE:{profile_code}")
            keys.add(code)
            if row.get("criterion_type") not in DECISION_CRITERION_TYPES:
                issues.append(f"INVALID_DECISION_CRITERION_TYPE:{profile_code}:{code}")
            if row.get("operator") not in CONTROLLED_OPERATORS:
                issues.append(f"INVALID_DECISION_CRITERION_OPERATOR:{profile_code}:{code}")
            source_type = str(row.get("source_evidence_type") or "")
            if source_type != "PORTFOLIO_CONTEXT" and source_type not in evidence_types:
                issues.append(f"UNKNOWN_CRITERION_SOURCE:{profile_code}:{code}")
            if not row.get("source_field"):
                issues.append(f"CRITERION_SOURCE_FIELD_REQUIRED:{profile_code}:{code}")
            if row.get("criterion_type") == "PRIORITIZATION" and row.get("weight") is not None:
                issues.append(f"NO_GATE_DOUBLE_SCORING:{profile_code}:{code}")
    return sorted(set(issues))


def evaluate_criteria(
    criteria: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    portfolio_context: dict[str, Any],
    project_contexts: list[dict[str, Any]],
    *,
    policy_revision: int | None,
    policy_hash: str,
    evaluated_at: str,
) -> list[dict[str, Any]]:
    """Evaluate criteria deterministically against already-governed values."""

    results: list[dict[str, Any]] = []
    contexts = {
        int(item["project_workspace_id"]): item for item in project_contexts if item.get("project_workspace_id")
    }
    for configured in sorted(criteria, key=lambda item: int(item.get("order", 0))):
        source_type = str(configured.get("source_evidence_type") or "")
        source_rows = (
            [{"source_payload": portfolio_context, "scope_id": None, "source_hash": portfolio_context.get("hash")}]
            if source_type == "PORTFOLIO_CONTEXT"
            else [item for item in evidence if item.get("evidence_type") == source_type]
        )
        if not source_rows:
            source_rows = [None]
        for source in source_rows:
            scope_id = source.get("scope_id") if source else None
            context = contexts.get(int(scope_id)) if scope_id is not None else None
            applicable = _criterion_applicable(configured, context)
            actual = _value_at(source or {}, str(configured.get("source_field") or "")) if source else None
            result = _criterion_result(configured, source, actual, applicable)
            results.append(
                {
                    "criterion_id": configured.get("criterion_id") or configured.get("criterion_code"),
                    "criterion_code": configured.get("criterion_code") or configured.get("criterion_id"),
                    "criterion_name": configured.get("criterion_name"),
                    "criterion_type": configured.get("criterion_type"),
                    "source_reference": {
                        "evidence_type": source_type,
                        "scope_id": scope_id,
                        "source_record_id": source.get("source_record_id") if source else None,
                        "source_hash": source.get("source_hash") if source else None,
                        "quality": source.get("evidence_quality") if source else None,
                        "quality_origin": source.get("quality_origin") if source else None,
                    },
                    "source_value": deepcopy(actual),
                    "operator": configured.get("operator"),
                    "threshold_or_expected_value": deepcopy(configured.get("expected_value")),
                    "result": result,
                    "blocking": bool(configured.get("blocking")),
                    "required": bool(configured.get("required")),
                    "weight": configured.get("weight"),
                    "evaluated_at": evaluated_at,
                    "policy_revision": policy_revision,
                    "policy_hash": policy_hash,
                }
            )
    return results


def success_criteria_candidates(
    criteria: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    evaluated_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Freeze references and target values without duplicating Benefit identities."""

    candidates: list[dict[str, Any]] = []
    satisfied_codes = {item["criterion_code"] for item in evaluated_results if item["result"] == "SATISFIED"}
    for configured in criteria:
        if configured.get("criterion_type") != "SUCCESS_CRITERION":
            continue
        code = str(configured.get("criterion_code") or configured.get("criterion_id"))
        if code not in satisfied_codes:
            continue
        source_type = str(configured.get("source_evidence_type"))
        for item in evidence:
            if item.get("evidence_type") != source_type:
                continue
            source = deepcopy(item.get("source_payload") or {})
            snapshots = list(source.get("benefit_snapshots") or [])
            if snapshots:
                for benefit in snapshots:
                    measures = list(benefit.get("measures") or []) or [{}]
                    for measure in measures:
                        candidates.append(
                            {
                                "criterion_code": code,
                                "stable_source_identity": benefit.get("benefit_number") or benefit.get("benefit_id"),
                                "source": source_type,
                                "source_id": source.get("benefits_plan_id"),
                                "source_version": source.get("plan_version_id"),
                                "source_hash": source.get("benefits_plan_hash") or item.get("source_hash"),
                                "metric_or_kpi": measure.get("measure_code"),
                                "baseline": deepcopy(measure.get("baseline_value")),
                                "target": deepcopy(measure.get("target_value") or benefit.get("expected_value")),
                                "target_date": measure.get("target_date"),
                                "unit": dict(measure.get("target_value") or {}).get("unit"),
                                "condition": None,
                                "as_of": source.get("as_of_date") or item.get("as_of_date"),
                            }
                        )
                continue
            candidates.append(
                {
                    "criterion_code": code,
                    "stable_source_identity": item.get("source_record_id"),
                    "source": source_type,
                    "source_id": item.get("source_record_id"),
                    "source_version": None,
                    "source_hash": item.get("source_hash"),
                    "metric_or_kpi": configured.get("source_field"),
                    "baseline": None,
                    "target": deepcopy(configured.get("expected_value")),
                    "target_date": None,
                    "unit": None,
                    "condition": None,
                    "as_of": item.get("as_of_date"),
                }
            )
    return candidates


def _criterion_applicable(configured: dict[str, Any], context: dict[str, Any] | None) -> bool:
    if configured.get("status", "ACTIVE") != "ACTIVE":
        return False
    if context is None:
        return True
    filters = (
        ("project_type_filter", str(context.get("project_type") or "UNCLASSIFIED").upper()),
        ("governance_model_filter", str(context.get("governance_model") or "LEGACY").upper()),
        ("uncertainty_level_filter", str(context.get("uncertainty_level") or "UNSPECIFIED").upper()),
        ("fel_stage_filter", str(context.get("fel_stage") or "UNSPECIFIED").upper()),
        ("project_size_filter", str(context.get("project_size") or "UNSPECIFIED").upper()),
        ("project_risk_filter", str(context.get("project_risk") or "UNSPECIFIED").upper()),
        ("project_complexity_filter", str(context.get("project_complexity") or "UNSPECIFIED").upper()),
    )
    for key, value in filters:
        allowed = {str(item).upper() for item in configured.get(key, ["*"])}
        if allowed and "*" not in allowed and value not in allowed:
            return False
    return True


def _criterion_result(configured: dict[str, Any], source: dict[str, Any] | None, actual: Any, applicable: bool) -> str:
    if not applicable:
        return "NOT_APPLICABLE"
    if source is None:
        return "NOT_EVALUABLE"
    if source.get("source_current") is False or source.get("status") == "STALE":
        return "STALE"
    if actual is None:
        return "NOT_EVALUABLE"
    return (
        "SATISFIED"
        if _operator_satisfied(str(configured.get("operator")), actual, configured.get("expected_value"))
        else "NOT_SATISFIED"
    )


def _operator_satisfied(operator: str, actual: Any, expected: Any) -> bool:
    if operator == "IS_TRUE":
        return actual is True
    if operator == "IS_FALSE":
        return actual is False
    if operator in {"IS_READY", "IS_CURRENT"}:
        return actual is True if operator == "IS_CURRENT" else str(actual).upper() in READY_VALUES
    if operator == "EQUALS":
        return actual == expected
    if operator == "NOT_EQUALS":
        return actual != expected
    if operator == "IN":
        return actual in (expected if isinstance(expected, list | tuple | set) else [expected])
    if operator == "NOT_IN":
        return actual not in (expected if isinstance(expected, list | tuple | set) else [expected])
    left, right = _comparable(actual), _comparable(expected)
    if left is None or right is None:
        return False
    if operator == "GREATER_THAN":
        return left > right
    if operator in {"GREATER_THAN_OR_EQUAL", "COVERAGE_AT_LEAST"}:
        return left >= right
    if operator == "LESS_THAN":
        return left < right
    if operator == "LESS_THAN_OR_EQUAL":
        return left <= right
    return False


def _comparable(value: Any) -> Decimal | None:
    normalized = str(value).upper()
    if normalized in FEL_LEVELS:
        return Decimal(FEL_LEVELS[normalized])
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _value_at(source: dict[str, Any], path: str) -> Any:
    current: Any = source
    for part in path.split("."):
        if not part:
            continue
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current
