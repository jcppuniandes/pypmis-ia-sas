"""Deterministic Decimal projection policy; no CPM or upstream state writer."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation

METHODS = (
    "BOTTOM_UP",
    "QUANTITY_RATE",
    "ACTIVITY_REMAINING_DURATION",
    "PRODUCTIVITY_BASED",
    "COMMITMENT_BASED",
    "CONTROL_ACCOUNT",
    "TREND_BASED",
    "MANUAL_GOVERNED",
)
ZERO = Decimal("0")
QUANTUM = Decimal("0.00000001")
DEFAULT_PROFILE = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "effective_from": None,
    "effective_to": None,
    "allowed_methods": list(METHODS),
    "confidence_scale": {
        "LOW": "Limited corroboration",
        "MEDIUM": "Owner corroborated",
        "HIGH": "Independently corroborated",
    },
    "confidence_is_statistical": False,
    "currencies": ["USD", "COP", "EUR"],
    "allow_allowance": True,
    "allow_manual_finish": True,
    "allow_published_period_successor": True,
    "approval_requires_computable_cost": True,
    "approval_requires_assessed_completeness": True,
    "require_confirmed_assumptions": True,
    "separation_of_duties": {
        "preparer_cannot_approve": True,
        "last_material_editor_cannot_approve": True,
        "author_cannot_publish": True,
    },
    "resource_types": [
        "LABOR",
        "EQUIPMENT",
        "CREW",
        "ENGINEERING_HOURS",
        "CONSTRUCTION_HOURS",
        "PROJECT_CONTROLS_HOURS",
    ],
    "variance_basis": "APPROVED_COST_BASELINE",
    "lookahead": {
        "default_horizon_days": 28,
        "maximum_horizon_days": 366,
        "include_overdue": True,
        "exclude_milestones": True,
        "default_top_n": None,
        "near_critical_threshold": {"value": "40", "unit": "HOUR"},
        "group_by": "PARENT_WBS",
    },
    "reporting": {
        "require_published_period": True,
        "publisher_not_forecast_preparer": True,
        "publisher_not_forecast_approver": True,
        "require_progress_snapshot": True,
        "require_evm_snapshot": True,
        "require_readiness_assessments": True,
        "narrative_sections": [
            "EXECUTIVE_SUMMARY",
            "SCHEDULE",
            "CRITICAL_NEAR_CRITICAL",
            "COST",
            "PROGRESS",
            "FORECAST",
            "CONSTRAINTS_READINESS",
            "MITIGATION_ACTIONS",
        ],
        "allow_republish": True,
    },
    "dashboard_thresholds": {"cpi_warning": "1", "spi_warning": "1", "finish_variance_warning_days": 0},
    "s_curve_series": [
        "PLANNED_PROGRESS",
        "APPROVED_ACTUAL_PROGRESS",
        "EARNED_VALUE",
        "PLANNED_VALUE",
        "ACTUAL_COST",
        "FORECAST_COST",
    ],
    "trend_metrics": [
        "forecast_finish",
        "eac",
        "etc",
        "vac",
        "physical_progress",
        "spi",
        "cpi",
        "readiness",
        "open_constraints",
    ],
}


def number(value, *, nonnegative=True, positive=False):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or abs(result) >= Decimal("10000000000000000"):
            raise ValueError("FORECAST_DECIMAL_RANGE_INVALID")
        if nonnegative and result < ZERO or positive and result <= ZERO:
            raise ValueError("FORECAST_POSITIVE_BASIS_REQUIRED")
        rounded = result.quantize(QUANTUM)
        if positive and rounded <= ZERO:
            raise ValueError("FORECAST_POSITIVE_BASIS_REQUIRED")
        return rounded
    except (InvalidOperation, TypeError) as error:
        raise ValueError("FORECAST_DECIMAL_INVALID") from error


def validate_profile(content):
    if not isinstance(content, dict) or set(content) != set(DEFAULT_PROFILE):
        raise ValueError("FORECAST_PROFILE_FIELDS_INVALID")
    for name in ("scope", "confidence_scale", "separation_of_duties", "lookahead", "reporting", "dashboard_thresholds"):
        if not isinstance(content[name], dict) or set(content[name]) != set(DEFAULT_PROFILE[name]):
            raise ValueError("FORECAST_PROFILE_SECTION_FIELDS_INVALID:" + name)
    for name in ("allowed_methods", "currencies", "resource_types", "s_curve_series", "trend_metrics"):
        values = content[name]
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(v, str) for v in values)
            or len(values) != len(set(values))
        ):
            raise ValueError("FORECAST_PROFILE_UNIQUE_LIST_REQUIRED:" + name)
    if not set(content["allowed_methods"]).issubset(METHODS):
        raise ValueError("FORECAST_METHODS_INVALID")
    if (
        set(content["confidence_scale"]) != {"LOW", "MEDIUM", "HIGH"}
        or content["confidence_is_statistical"] is not False
        or any(not isinstance(value, str) or not value.strip() for value in content["confidence_scale"].values())
    ):
        raise ValueError("FORECAST_QUALITATIVE_CONFIDENCE_REQUIRED")
    if any(not 3 <= len(c) <= 8 or not c.isascii() or not c.isalpha() or c.upper() != c for c in content["currencies"]):
        raise ValueError("FORECAST_CURRENCIES_INVALID")
    for name in (
        "allow_allowance",
        "allow_manual_finish",
        "allow_published_period_successor",
        "approval_requires_computable_cost",
        "approval_requires_assessed_completeness",
        "require_confirmed_assumptions",
        "inherit_to_descendants",
    ):
        if not isinstance(content[name], bool):
            raise ValueError("FORECAST_POLICY_BOOLEAN_REQUIRED")
    if content["variance_basis"] != "APPROVED_COST_BASELINE":
        raise ValueError("FORECAST_EXPLICIT_APPROVED_BASELINE_REQUIRED")
    for name in ("resource_types", "s_curve_series", "trend_metrics"):
        if not set(content[name]).issubset(DEFAULT_PROFILE[name]):
            raise ValueError("FORECAST_PROFILE_LIST_VALUES_INVALID:" + name)
    horizon = content["lookahead"]
    if any(type(horizon[key]) is not int for key in ("default_horizon_days", "maximum_horizon_days")):
        raise ValueError("FORECAST_LOOKAHEAD_HORIZON_INVALID")
    if not 1 <= horizon["default_horizon_days"] <= horizon["maximum_horizon_days"] <= 366:
        raise ValueError("FORECAST_LOOKAHEAD_HORIZON_INVALID")
    if not isinstance(horizon["near_critical_threshold"], dict) or set(horizon["near_critical_threshold"]) != {
        "value",
        "unit",
    }:
        raise ValueError("FORECAST_FLOAT_UNIT_REQUIRED")
    if horizon["near_critical_threshold"]["unit"] not in {"HOUR", "DAY"}:
        raise ValueError("FORECAST_FLOAT_UNIT_REQUIRED")
    number(horizon["near_critical_threshold"]["value"])
    if any(type(horizon[key]) is not bool for key in ("include_overdue", "exclude_milestones")):
        raise ValueError("FORECAST_LOOKAHEAD_BOOLEAN_REQUIRED")
    if horizon["default_top_n"] is not None and (
        type(horizon["default_top_n"]) is not int or not 1 <= horizon["default_top_n"] <= 10000
    ):
        raise ValueError("FORECAST_LOOKAHEAD_TOP_N_INVALID")
    if horizon["group_by"] not in {"PARENT_WBS", "AREA", "CWA", "PACKAGE", "ZONE", "SYSTEM", "DISCIPLINE"}:
        raise ValueError("FORECAST_LOOKAHEAD_GROUPING_INVALID")
    for name in ("cpi_warning", "spi_warning"):
        number(content["dashboard_thresholds"][name], positive=True)
    if type(content["dashboard_thresholds"]["finish_variance_warning_days"]) is not int:
        raise ValueError("FORECAST_VARIANCE_THRESHOLD_DAYS_REQUIRED")
    reporting = content["reporting"]
    if any(type(value) is not bool for name, value in reporting.items() if name != "narrative_sections"):
        raise ValueError("FORECAST_REPORTING_BOOLEAN_REQUIRED")
    sections = reporting["narrative_sections"]
    if (
        not isinstance(sections, list)
        or not sections
        or any(not isinstance(value, str) for value in sections)
        or len(sections) != len(set(sections))
        or not set(sections).issubset(DEFAULT_PROFILE["reporting"]["narrative_sections"])
    ):
        raise ValueError("FORECAST_REPORTING_NARRATIVE_SECTIONS_INVALID")
    if reporting["require_published_period"] is not True:
        raise ValueError("FORECAST_REPORT_PUBLISHED_PERIOD_REQUIRED")
    if not isinstance(content["separation_of_duties"], dict) or not all(
        isinstance(v, bool) for v in content["separation_of_duties"].values()
    ):
        raise ValueError("FORECAST_SOD_INVALID")
    return deepcopy(content)


def cost_value(
    method,
    *,
    amount=None,
    quantity=None,
    rate=None,
    duration=None,
    productivity=None,
    daily_rate=None,
    commitment_remaining=None,
    prior_etc=None,
    trend_factor=None,
):
    """Inputs are resolved, attributed assumptions or compatible source facts."""
    if method not in METHODS:
        raise ValueError("FORECAST_METHOD_INVALID")
    if method in {"BOTTOM_UP", "MANUAL_GOVERNED", "CONTROL_ACCOUNT"}:
        return number(amount)
    if method == "QUANTITY_RATE":
        return number(number(quantity) * number(rate))
    if method == "ACTIVITY_REMAINING_DURATION":
        return number(number(duration) * number(daily_rate))
    if method == "PRODUCTIVITY_BASED":
        return number(number(quantity) / number(productivity, positive=True) * number(daily_rate))
    if method == "COMMITMENT_BASED":
        return number(commitment_remaining)
    return number(number(prior_etc) * number(trend_factor, positive=True))


def eac_values(actual, etc, bac, *, reasons=()):
    issues = list(dict.fromkeys(reasons))
    if actual is None:
        issues.append("RECOGNIZED_ACTUAL_REQUIRED")
    if etc is None:
        issues.append("FORECAST_ETC_REQUIRED")
    if bac is None:
        issues.append("APPROVED_BASELINE_BAC_REQUIRED")
    if issues:
        return {
            "status": "NOT_COMPUTABLE",
            "reason_codes": list(dict.fromkeys(issues)),
            "actual": None,
            "etc": None,
            "eac": None,
            "bac": None,
            "vac": None,
        }
    ac, remaining, approved = number(actual), number(etc), number(bac)
    eac = number(ac + remaining)
    return {
        "status": "COMPUTABLE",
        "reason_codes": [],
        "actual": str(ac),
        "etc": str(remaining),
        "eac": str(eac),
        "bac": str(approved),
        "vac": str(number(approved - eac, nonnegative=False)),
    }


def resource_value(quantity, productivity, basis, *, crew_size=None):
    remaining, productivity = number(quantity), number(productivity, positive=True)
    if basis == "HOURS_PER_UNIT":
        hours = number(remaining * productivity)
        return {"quantity": str(hours), "unit": "h", "duration_days": None}
    if basis == "QUANTITY_PER_DAY":
        days = number(remaining / productivity)
        if crew_size is None:
            return {"quantity": str(days), "unit": "day", "duration_days": str(days)}
        return {
            "quantity": str(number(days * number(crew_size, positive=True))),
            "unit": "person-day",
            "duration_days": str(days),
        }
    raise ValueError("FORECAST_PRODUCTIVITY_UNIT_BASIS_REQUIRED")
