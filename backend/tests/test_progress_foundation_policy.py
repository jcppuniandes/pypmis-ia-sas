"""Deterministic, bounded Progress arithmetic and non-bypassable policy."""

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.progress_foundation.policy import (
    DEFAULT_PROFILE,
    cost_progress_ratio,
    credit_progress,
    number,
    percentage,
    validate_profile,
    weighted_progress,
)
from app.modules.progress_foundation.schemas import MeasurementIn
from app.modules.progress_foundation.service import ProgressFoundationService


def test_weighted_coverage_uses_components_instead_of_parent_scope_label():
    row = SimpleNamespace(
        method="WEIGHTED_COMPONENTS",
        source_snapshot={"scope_item_ids": [1], "component_coverage": [[1, "INSTALL"], [2, "REMOVE"]]},
    )
    assert ProgressFoundationService._coverage(row) == {(1, "INSTALL"), (2, "REMOVE")}


@pytest.mark.parametrize(
    "nature,phase,expected",
    [("INSTALL", "EXECUTE", "INSTALL"), ("REMOVE", "EXECUTE", "REMOVE"), ("TEMPORARY", "USE", "USE")],
)
def test_component_coverage_preserves_nature_and_canonical_execution_phase(nature, phase, expected):
    row = SimpleNamespace(
        method="QUANTITY_BASED", scope_nature=nature, phase=phase, source_snapshot={"scope_item_ids": [1]}
    )
    assert ProgressFoundationService._coverage(row) == {(1, expected)}


@pytest.mark.parametrize(
    "numerator,denominator,result",
    [("0", "10", "0"), ("10", "10", "100"), ("1", "3", "33.33333333"), ("0.00000001", "0.00000002", "50")],
)
def test_quantity_percentage_zero_full_and_decimal_precision(numerator, denominator, result):
    assert percentage(numerator, denominator) == Decimal(result)


@pytest.mark.parametrize("numerator,denominator", [("-1", "10"), ("1", "0"), ("1", "-10"), ("11", "10")])
def test_normal_percentage_bounds_and_invalid_denominator(numerator, denominator):
    with pytest.raises(ValueError):
        percentage(numerator, denominator)


def test_quantity_overrun_is_not_silently_capped():
    assert percentage("12", "10", allow_overrun=True) == 120


@pytest.mark.parametrize(
    "actual,budget,value,raw",
    [
        ("0", "100", "0", "0"),
        ("100", "100", "100", "100"),
        ("125", "100", None, "125"),
        ("-10", "100", None, "-10"),
    ],
)
def test_cost_ratio_is_separate_from_normal_completion_bounds(actual, budget, value, raw):
    result, ratio = cost_progress_ratio(actual, budget)
    assert result == (Decimal(value) if value is not None else None)
    assert ratio == Decimal(raw)


@pytest.mark.parametrize("budget", ["0", "-1"])
def test_cost_ratio_rejects_zero_or_negative_budget(budget):
    with pytest.raises(ValueError, match="COST_ZERO_DENOMINATOR"):
        cost_progress_ratio("1", budget)


@pytest.mark.parametrize("value", [0.1, True, "NaN", "Infinity", "-Infinity", "10000000000000000", "invalid"])
def test_canonical_number_rejects_float_nonfinite_boolean_and_range(value):
    with pytest.raises(ValueError):
        number(value)


def test_weighted_progress_uses_explicit_weights_once():
    value, total = weighted_progress([{"progress_value": "20", "weight": "1"}, {"progress_value": "80", "weight": "3"}])
    assert value == 65 and total == 4


@pytest.mark.parametrize(
    "components",
    [
        [],
        [{"progress_value": "10", "weight": "0"}],
        [{"progress_value": "10", "weight": "-1"}],
        [{"progress_value": "101", "weight": "1"}],
        [{"progress_value": "-1", "weight": "1"}],
    ],
)
def test_weighted_progress_denies_invalid_components_and_weights(components):
    with pytest.raises(ValueError):
        weighted_progress(components)


@pytest.mark.parametrize(
    "weights,completed,expected",
    [
        (["100"], [], 0),
        (["100"], ["0"], 100),
        (["50", "50"], ["0"], 50),
        (["10", "20", "30", "40"], ["0", "1", "2"], 60),
        (["30", "20", "30", "20"], ["0", "1"], 50),
    ],
)
def test_rule_of_credit_step_and_milestone_patterns(weights, completed, expected):
    steps = [{"code": str(index), "weight": weight} for index, weight in enumerate(weights)]
    assert credit_progress(steps, completed) == expected


@pytest.mark.parametrize(
    "weights,completed",
    [
        (["50", "49"], []),
        (["0", "100"], []),
        (["30", "20", "30", "20"], ["1"]),
        (["100"], ["unknown"]),
        (["100"], ["0", "0"]),
    ],
)
def test_credit_requires_normalized_distinct_ordered_steps(weights, completed):
    with pytest.raises(ValueError):
        credit_progress([{"code": str(index), "weight": weight} for index, weight in enumerate(weights)], completed)


def test_unordered_milestone_rule_is_explicit_not_assumed():
    assert credit_progress([{"code": "A", "weight": "50"}, {"code": "B", "weight": "50"}], ["B"], ordered=False) == 50


def test_default_progress_profile_is_valid_and_scope_nature_specific():
    validate_profile(deepcopy(DEFAULT_PROFILE))
    assert "QUANTITY_BASED" not in DEFAULT_PROFILE["methods_by_scope_nature"]["MAINTENANCE"]
    assert DEFAULT_PROFILE["package_methods"]["EWP"] != DEFAULT_PROFILE["package_methods"]["CWP"]


@pytest.mark.parametrize(
    "key",
    [
        "denominator_rules",
        "evidence_requirements",
        "period_policy",
        "separation_of_duties",
        "approval_workflow",
        "evm_policy",
    ],
)
def test_profile_cannot_relax_authority_or_separation(key):
    profile = deepcopy(DEFAULT_PROFILE)
    profile[key] = {} if isinstance(profile[key], dict) else []
    with pytest.raises(ValueError):
        validate_profile(profile)


@pytest.mark.parametrize("coverage", ["0", "40", "100"])
def test_control_account_coverage_is_policy_not_universal(coverage):
    profile = deepcopy(DEFAULT_PROFILE)
    profile["baseline_policy"]["control_account_coverage_percent"] = coverage
    validate_profile(profile)


@pytest.mark.parametrize("coverage", ["-1", "100.01"])
def test_control_account_coverage_bounds(coverage):
    profile = deepcopy(DEFAULT_PROFILE)
    profile["baseline_policy"]["control_account_coverage_percent"] = coverage
    with pytest.raises(ValueError):
        validate_profile(profile)


@pytest.mark.parametrize(
    "authority",
    [
        "source_domain",
        "denominator",
        "progress_value",
        "status",
        "approved_by",
        "scope_quantity",
        "budget_amount",
        "percent_complete",
    ],
)
def test_measurement_contract_rejects_computed_and_upstream_write_flags(authority):
    with pytest.raises(ValueError):
        MeasurementIn.model_validate(
            {
                "reason": "Governed test evidence",
                "code": "Q1",
                "name": "Quantity",
                "progress_type": "QUANTITY",
                "method": "QUANTITY_BASED",
                "source_reference": "FIELD",
                "period_id": 1,
                "measurement_date": "2026-10-21",
                "as_of": "2026-10-22",
                "numerator": "1",
                "unit": "m3",
                authority: "UNAUTHORIZED",
            }
        )
