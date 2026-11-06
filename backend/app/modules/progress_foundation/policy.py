"""Decimal-only, deterministic Progress calculations and published policy defaults."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation, localcontext

TYPES = ["QUANTITY", "PHYSICAL", "SCHEDULE", "COST", "EARNED", "WEIGHTED", "MILESTONE"]
METHODS = [
    "QUANTITY_BASED",
    "WEIGHTED_COMPONENTS",
    "MILESTONE_BASED",
    "STEP_METHOD",
    "RULE_OF_CREDIT",
    "MANUAL_EXPERT_ASSESSMENT",
]
WEIGHTING_BASES = ["QUANTITY", "BUDGET", "LABOR_HOURS", "ENGINEERING_HOURS", "CONTRACT_VALUE", "MANUAL_APPROVED_WEIGHT"]
DEFAULT_PROFILE = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "effective_from": None,
    "effective_to": None,
    "allowed_progress_types": TYPES,
    "allowed_methods": METHODS,
    "default_method_by_scope_type": {
        "DELIVERABLE": "MILESTONE_BASED",
        "WORK": "QUANTITY_BASED",
        "SERVICE": "MANUAL_EXPERT_ASSESSMENT",
    },
    "methods_by_scope_nature": {
        "INSTALL": METHODS,
        "REMOVE": METHODS,
        "TEMPORARY": ["QUANTITY_BASED", "RULE_OF_CREDIT", "STEP_METHOD", "MILESTONE_BASED", "WEIGHTED_COMPONENTS"],
        "MAINTENANCE": [
            "STEP_METHOD",
            "MILESTONE_BASED",
            "RULE_OF_CREDIT",
            "WEIGHTED_COMPONENTS",
            "MANUAL_EXPERT_ASSESSMENT",
        ],
    },
    "package_methods": {
        "EWP": ["MILESTONE_BASED", "STEP_METHOD", "RULE_OF_CREDIT"],
        "PWP": ["MILESTONE_BASED", "STEP_METHOD"],
        "CWP": ["QUANTITY_BASED", "WEIGHTED_COMPONENTS"],
        "IWP": ["QUANTITY_BASED", "RULE_OF_CREDIT", "STEP_METHOD"],
        "TWP": ["MILESTONE_BASED", "STEP_METHOD"],
        "LOGISTICS": ["MILESTONE_BASED", "STEP_METHOD"],
        "TEMPORARY_WORKS": ["QUANTITY_BASED", "RULE_OF_CREDIT", "STEP_METHOD", "MILESTONE_BASED"],
        "SUPPORT": METHODS,
    },
    "denominator_rules": {
        "scope": "APPROVED_SCOPE_SNAPSHOT",
        "plan": "PUBLISHED_PLAN_ALLOCATION",
        "package": "APPROVED_EXPLICIT_ALLOCATION",
        "approved_basis": "PUBLISHED_RULE",
    },
    "weighting_rules": {
        "allowed_bases": WEIGHTING_BASES,
        "manual_weight_requires_approval": True,
        "no_mixed_basis": True,
    },
    "rule_of_credit_templates": {
        "INSTALLATION": [
            {"code": "SET", "name": "Set in position", "weight": "30"},
            {"code": "ALIGNED", "name": "Aligned", "weight": "20"},
            {"code": "CONNECTED", "name": "Connected", "weight": "30"},
            {"code": "TESTED", "name": "Tested", "weight": "20"},
        ]
    },
    "milestone_templates": {
        "ZERO_HUNDRED": ["100"],
        "FIFTY_FIFTY": ["50", "50"],
        "TEN_TWENTY_THIRTY_FORTY": ["10", "20", "30", "40"],
    },
    "evidence_requirements": {"all_measurements": True, "negative_correction": True},
    "approval_workflow": ["DRAFT", "SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED", "SUPERSEDED"],
    "tolerance": "0.000001",
    "rework_policy": {"enabled": True, "require_evidence": True},
    "negative_progress_policy": {"allow_corrections": True, "cumulative_min": "0", "require_reason": True},
    "period_policy": {
        "capture": ["OPEN"],
        "approval": ["OPEN", "REVIEW"],
        "review_requires_frozen_set": True,
        "closed_immutable": True,
    },
    "baseline_policy": {
        "control_account_coverage_percent": "0",
        "require_current_scope": True,
        "require_approved_sources": True,
        "block_stale": True,
        "effective_date_rule": "EXPLICIT_BUSINESS_EFFECTIVE_DATE",
    },
    "evm_policy": {
        "allowed_earned_sources": ["PHYSICAL", "QUANTITY", "MILESTONE"],
        "earned_source_priority": ["PHYSICAL", "QUANTITY", "MILESTONE"],
        "require_approved_bundle": True,
        "allow_overrun": False,
        "allow_currency_conversion": False,
    },
    "separation_of_duties": {
        "author_cannot_publish": True,
        "preparer_cannot_approve": True,
        "recorder_cannot_certify": True,
    },
}


def number(value):
    if isinstance(value, (float, bool)):
        raise ValueError("PROGRESS_DECIMAL_INPUT_REQUIRED")
    try:
        result = Decimal(str(value))
        if not result.is_finite() or abs(result) >= Decimal("10000000000000000"):
            raise ValueError("PROGRESS_DECIMAL_RANGE_INVALID")
        return result
    except (InvalidOperation, TypeError) as error:
        raise ValueError("PROGRESS_DECIMAL_INVALID") from error


def rounded(value):
    with localcontext() as context:
        context.prec = 50
        return number(value).quantize(Decimal("0.00000001"))


def percentage(numerator, denominator, *, allow_overrun=False):
    numerator, denominator = number(numerator), number(denominator)
    if numerator < 0 or denominator <= 0:
        raise ValueError("PROGRESS_QUANTITY_BASIS_INVALID")
    with localcontext() as context:
        context.prec = 50
        result = rounded(numerator * 100 / denominator)
    if result > 100 and not allow_overrun:
        raise ValueError("PROGRESS_BOUNDS_EXCEEDED")
    return result


def cost_progress_ratio(actual, budget):
    """Preserve expenditure variance without treating it as normal completion."""
    actual, budget = number(actual), number(budget)
    if budget <= 0:
        raise ValueError("COST_ZERO_DENOMINATOR")
    with localcontext() as context:
        context.prec = 50
        raw = rounded(actual / budget * 100)
    return (raw if 0 <= raw <= 100 else None), raw


def weighted_progress(components):
    if not components:
        raise ValueError("PROGRESS_COMPONENTS_REQUIRED")
    values = [(number(row["progress_value"]), number(row["weight"])) for row in components]
    if any(value < 0 or value > 100 or weight <= 0 for value, weight in values):
        raise ValueError("PROGRESS_COMPONENT_OR_WEIGHT_INVALID")
    with localcontext() as context:
        context.prec = 50
        total = sum(weight for _, weight in values)
        result = sum(value * weight for value, weight in values) / total
        return rounded(result), rounded(total)


def credit_progress(steps, completed, *, ordered=True):
    if not steps or len({row["code"] for row in steps}) != len(steps):
        raise ValueError("PROGRESS_RULE_STEPS_INVALID")
    weights = [number(row["weight"]) for row in steps]
    if any(weight <= 0 or weight > 100 for weight in weights) or sum(weights) != 100:
        raise ValueError("PROGRESS_RULE_WEIGHTS_MUST_TOTAL_100")
    codes = [row["code"] for row in steps]
    if len(completed) != len(set(completed)) or not set(completed) <= set(codes):
        raise ValueError("PROGRESS_RULE_COMPLETION_INVALID")
    if ordered and set(completed) != set(codes[: len(completed)]):
        raise ValueError("PROGRESS_RULE_SEQUENCE_REQUIRED")
    return rounded(sum(number(row["weight"]) for row in steps if row["code"] in completed))


def validate_profile(content):
    if set(content) != set(DEFAULT_PROFILE):
        raise ValueError("PROGRESS_PROFILE_KEYS_INVALID")
    for key, choices in (("allowed_progress_types", TYPES), ("allowed_methods", METHODS)):
        selected = content[key]
        if (
            not isinstance(selected, list)
            or not selected
            or len(set(selected)) != len(selected)
            or not set(selected) <= set(choices)
        ):
            raise ValueError("PROGRESS_PROFILE_CATALOG_INVALID")
    for key in (
        "approval_workflow",
        "denominator_rules",
        "evidence_requirements",
        "period_policy",
        "separation_of_duties",
    ):
        if content[key] != DEFAULT_PROFILE[key]:
            raise ValueError("PROGRESS_PROFILE_AUTHORITY_POLICY_IMMUTABLE")
    for nature, methods in content["methods_by_scope_nature"].items():
        if nature not in DEFAULT_PROFILE["methods_by_scope_nature"] or not methods or not set(methods) <= set(METHODS):
            raise ValueError("PROGRESS_NATURE_METHOD_INVALID")
    if set(content["methods_by_scope_nature"]) != set(DEFAULT_PROFILE["methods_by_scope_nature"]):
        raise ValueError("PROGRESS_NATURE_POLICY_REQUIRED")
    if not content["package_methods"] or any(
        not methods or not set(methods) <= set(METHODS) for methods in content["package_methods"].values()
    ):
        raise ValueError("PROGRESS_PACKAGE_METHOD_INVALID")
    if (
        not set(content["weighting_rules"]["allowed_bases"]) <= set(WEIGHTING_BASES)
        or not content["weighting_rules"]["allowed_bases"]
    ):
        raise ValueError("PROGRESS_WEIGHTING_BASIS_INVALID")
    if (
        content["weighting_rules"]["no_mixed_basis"] is not True
        or content["weighting_rules"]["manual_weight_requires_approval"] is not True
    ):
        raise ValueError("PROGRESS_WEIGHTING_GOVERNANCE_REQUIRED")
    if number(content["tolerance"]) < 0 or number(content["tolerance"]) > 1:
        raise ValueError("PROGRESS_TOLERANCE_INVALID")
    baseline = deepcopy(content["baseline_policy"])
    coverage = number(baseline.pop("control_account_coverage_percent"))
    expected_baseline = deepcopy(DEFAULT_PROFILE["baseline_policy"])
    expected_baseline.pop("control_account_coverage_percent")
    if not 0 <= coverage <= 100 or baseline != expected_baseline:
        raise ValueError("PROGRESS_BASELINE_POLICY_INVALID")
    if content["evm_policy"] != DEFAULT_PROFILE["evm_policy"]:
        raise ValueError("PROGRESS_EVM_AUTHORITY_POLICY_REQUIRED")
    for steps in content["rule_of_credit_templates"].values():
        credit_progress(steps, [])
    for weights in content["milestone_templates"].values():
        credit_progress([{"code": str(i), "weight": weight} for i, weight in enumerate(weights)], [])
    for key in ("rework_policy", "negative_progress_policy"):
        if set(content[key]) != set(DEFAULT_PROFILE[key]):
            raise ValueError("PROGRESS_CORRECTION_POLICY_INVALID")
    if (
        content["negative_progress_policy"]["cumulative_min"] != "0"
        or content["negative_progress_policy"]["require_reason"] is not True
        or content["rework_policy"]["require_evidence"] is not True
    ):
        raise ValueError("PROGRESS_CORRECTION_EVIDENCE_REQUIRED")
    if not isinstance(content["rework_policy"]["enabled"], bool) or not isinstance(
        content["negative_progress_policy"]["allow_corrections"], bool
    ):
        raise ValueError("PROGRESS_CORRECTION_POLICY_INVALID")
