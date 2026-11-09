"""Pure Decimal and policy contracts independent of transactional source writers."""

from copy import deepcopy
from decimal import Decimal

import pytest

from app.modules.forecast_foundation.policy import (
    DEFAULT_PROFILE,
    METHODS,
    cost_value,
    eac_values,
    number,
    resource_value,
    validate_profile,
)
from app.modules.forecast_foundation.schemas import AssumptionIn, ForecastIn


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "10000000000000000", "not-a-number", None])
def test_decimal_nonfinite_missing_and_unbounded_rejected(value):
    with pytest.raises(ValueError):
        number(value)


@pytest.mark.parametrize("value", ["0", "0.00000001", "12.45", "9999999.12345678"])
def test_decimal_numeric_eight_place_authority(value):
    assert number(value) == Decimal(value)


@pytest.mark.parametrize(
    "method,kwargs,expected",
    [
        ("BOTTOM_UP", {"amount": "17.25"}, "17.25"),
        ("MANUAL_GOVERNED", {"amount": "23"}, "23"),
        ("CONTROL_ACCOUNT", {"amount": "91"}, "91"),
        ("QUANTITY_RATE", {"quantity": "4", "rate": "25.5"}, "102"),
        ("ACTIVITY_REMAINING_DURATION", {"duration": "3", "daily_rate": "40"}, "120"),
        ("PRODUCTIVITY_BASED", {"quantity": "12", "productivity": "4", "daily_rate": "50"}, "150"),
        ("COMMITMENT_BASED", {"commitment_remaining": "75"}, "75"),
        ("TREND_BASED", {"prior_etc": "100", "trend_factor": "1.1"}, "110"),
    ],
)
def test_eight_explicit_forecast_methods(method, kwargs, expected):
    assert cost_value(method, **kwargs) == Decimal(expected)


@pytest.mark.parametrize("productivity", ["0", "-1", "NaN"])
def test_productivity_division_requires_positive_compatible_basis(productivity):
    with pytest.raises(ValueError):
        cost_value("PRODUCTIVITY_BASED", quantity="5", productivity=productivity, daily_rate="10")


def test_eac_actual_plus_etc_without_extra_commitment_term():
    result = eac_values("25", "75", "120")
    assert result == {
        "status": "COMPUTABLE",
        "reason_codes": [],
        "actual": "25.00000000",
        "etc": "75.00000000",
        "eac": "100.00000000",
        "bac": "120.00000000",
        "vac": "20.00000000",
    }


@pytest.mark.parametrize(
    "actual,etc,bac,reasons,expected",
    [
        (None, "10", "20", [], "RECOGNIZED_ACTUAL_REQUIRED"),
        ("5", None, "20", [], "FORECAST_ETC_REQUIRED"),
        ("5", "10", None, [], "APPROVED_BASELINE_BAC_REQUIRED"),
        ("5", "10", "20", ["CURRENCY_MISMATCH"], "CURRENCY_MISMATCH"),
        ("5", "10", "20", ["ASOF_MISMATCH"], "ASOF_MISMATCH"),
    ],
)
def test_not_computable_propagates_reason_without_plausible_zero(actual, etc, bac, reasons, expected):
    result = eac_values(actual, etc, bac, reasons=reasons)
    assert result["status"] == "NOT_COMPUTABLE" and expected in result["reason_codes"]
    assert all(result[key] is None for key in ("actual", "etc", "eac", "bac", "vac"))


def test_eac_real_zero_is_not_missing():
    result = eac_values("0", "0", "0")
    assert result["status"] == "COMPUTABLE" and Decimal(result["eac"]) == 0


@pytest.mark.parametrize(
    "basis,quantity,productivity,crew,expected,unit",
    [
        ("HOURS_PER_UNIT", "10", "2", None, "20", "h"),
        ("QUANTITY_PER_DAY", "10", "2", None, "5", "day"),
        ("QUANTITY_PER_DAY", "10", "2", "3", "15", "person-day"),
    ],
)
def test_productivity_resource_basis_is_explicit(basis, quantity, productivity, crew, expected, unit):
    result = resource_value(quantity, productivity, basis, crew_size=crew)
    assert Decimal(result["quantity"]) == Decimal(expected) and result["unit"] == unit


def test_resource_cross_unit_aggregation_is_not_implicit():
    with pytest.raises(ValueError, match="UNIT_BASIS"):
        resource_value("10", "2", "m3_or_m2")


def test_published_policy_declares_qualitative_not_statistical_confidence():
    assert validate_profile(DEFAULT_PROFILE) == DEFAULT_PROFILE
    changed = deepcopy(DEFAULT_PROFILE)
    changed["confidence_is_statistical"] = True
    with pytest.raises(ValueError, match="QUALITATIVE"):
        validate_profile(changed)


@pytest.mark.parametrize(
    "field,value",
    [
        ("allowed_methods", []),
        ("allowed_methods", ["LOCAL_CPM"]),
        ("variance_basis", "AMBIGUOUS_BUDGET"),
        ("allow_manual_finish", "true"),
    ],
)
def test_policy_invalid_authorities_and_methods_rejected(field, value):
    changed = deepcopy(DEFAULT_PROFILE)
    changed[field] = value
    with pytest.raises(ValueError):
        validate_profile(changed)


def test_policy_four_week_default_and_reporting_source_requirements():
    assert DEFAULT_PROFILE["lookahead"]["default_horizon_days"] == 28
    assert DEFAULT_PROFILE["reporting"]["require_published_period"] is True
    assert len(METHODS) == 8


def test_draft_defaults_do_not_claim_review_has_happened():
    assert ForecastIn.model_fields["data_completeness"].default == "NOT_ASSESSED"
    assert ForecastIn.model_fields["assumption_maturity"].default == "NOT_ASSESSED"
    assert AssumptionIn.model_fields["status"].default == "DRAFT"


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("lookahead", "include_overdue", "true"),
        ("lookahead", "maximum_horizon_days", 367),
        ("lookahead", "group_by", "UNKNOWN"),
        ("lookahead", "default_top_n", True),
        ("reporting", "publisher_not_forecast_preparer", "false"),
        ("reporting", "require_published_period", False),
        ("reporting", "narrative_sections", []),
        ("separation_of_duties", "preparer_cannot_approve", "false"),
        ("confidence_scale", "LOW", " "),
    ],
)
def test_nested_admin_policy_cannot_silently_accept_malformed_controls(section, key, value):
    changed = deepcopy(DEFAULT_PROFILE)
    changed[section][key] = value
    with pytest.raises(ValueError):
        validate_profile(changed)


def test_positive_rate_below_storage_precision_cannot_round_to_zero_divisor():
    with pytest.raises(ValueError, match="POSITIVE"):
        number("0.0000000001", positive=True)
