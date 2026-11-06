"""Deterministic EVM and separate approved-physical overlay semantics."""

from decimal import Decimal

import pytest

from app.modules.progress_foundation.integration import approved_overlay_state
from app.modules.progress_foundation.integration_policy import earned_amount, evm_values, value, weighted_progress


@pytest.mark.parametrize(
    "percentage,expected", [("0", "0"), ("50", "50"), ("100", "100"), ("33.33333333", "33.33333333")]
)
def test_earned_value_from_budgeted_value_and_approved_percentage(percentage, expected):
    assert earned_amount("100", percentage) == Decimal(expected)


@pytest.mark.parametrize("percentage", ["-0.1", "100.00000001", "140"])
def test_earned_overrun_is_not_silently_capped(percentage):
    with pytest.raises(ValueError, match="EARNED_BASIS_OUT_OF_BOUNDS"):
        earned_amount("100", percentage)


def test_evm_cpi_spi_are_decimal_exact():
    result = evm_values("100", "80", "40")
    assert result["status"] == "COMPUTABLE"
    assert Decimal(result["cpi"]) == Decimal("2")
    assert Decimal(result["spi"]) == Decimal("0.8")


def test_zero_approved_earned_value_is_computable_not_missing_progress():
    result = evm_values("100", "0", "25")
    assert result["status"] == "COMPUTABLE"
    assert Decimal(result["ev"]) == Decimal(result["cpi"]) == Decimal(result["spi"]) == 0


@pytest.mark.parametrize(
    "pv,ev,ac,reason",
    [
        (None, "50", "20", "MISSING_PV"),
        ("100", None, "20", "MISSING_EV"),
        ("100", "50", None, "MISSING_AC"),
        ("0", "50", "20", "ZERO_PV_DENOMINATOR"),
        ("100", "50", "0", "ZERO_AC_DENOMINATOR"),
        ("100", "50", "-1", "NEGATIVE_AC"),
    ],
)
def test_evm_missing_or_incompatible_values_are_not_computable(pv, ev, ac, reason):
    result = evm_values(pv, ev, ac)
    assert result["status"] == "NOT_COMPUTABLE" and reason in result["reason_codes"]
    assert all(result[name] is None for name in ("pv", "ev", "ac", "cpi", "spi"))


@pytest.mark.parametrize(
    "reason",
    [
        "CURRENCY_MISMATCH",
        "PERIOD_AS_OF_MISMATCH",
        "BASELINE_BUNDLE_REQUIRES_REVIEW",
        "PROGRESS_SOURCE_REQUIRES_REVIEW",
    ],
)
def test_evm_compatibility_error_never_returns_plausible_total(reason):
    result = evm_values("100", "80", "40", errors=[reason])
    assert result["status"] == "NOT_COMPUTABLE" and result["ev"] is None
    assert result["source_values"]["ev"] == "80.00000000"


def test_weighted_progress_uses_explicit_common_basis():
    result = weighted_progress(
        [
            {"progress_value": "50", "weight": "1", "weighting_basis": "BUDGET"},
            {"progress_value": "100", "weight": "3", "weighting_basis": "BUDGET"},
        ]
    )
    assert result["status"] == "COMPUTABLE" and Decimal(result["progress_value"]) == Decimal("87.5")
    assert result["weighting_basis"] == "BUDGET"


@pytest.mark.parametrize(
    "weights,bases,reason",
    [
        ([0, 1], ["BUDGET", "BUDGET"], "POSITIVE_WEIGHT_REQUIRED"),
        ([-1, 1], ["QUANTITY", "QUANTITY"], "POSITIVE_WEIGHT_REQUIRED"),
        ([1, 1], ["BUDGET", "QUANTITY"], "WEIGHTING_BASIS_MISMATCH"),
    ],
)
def test_invalid_weight_or_mixed_basis_not_computable(weights, bases, reason):
    result = weighted_progress(
        [
            {"progress_value": "50", "weight": weight, "weighting_basis": basis}
            for weight, basis in zip(weights, bases, strict=True)
        ]
    )
    assert result["status"] == "NOT_COMPUTABLE" and reason in result["reason_codes"]


def test_empty_weighted_progress_is_not_zero_progress():
    assert weighted_progress([])["progress_value"] is None


@pytest.mark.parametrize("progress", ["-1", "100.00000001"])
def test_weighted_overrun_or_negative_not_normalized(progress):
    result = weighted_progress([{"progress_value": progress, "weight": "1", "weighting_basis": "BUDGET"}])
    assert result["status"] == "NOT_COMPUTABLE" and result["progress_value"] is None
    assert result["reason_codes"] == ["PROGRESS_OUT_OF_BOUNDS"]


@pytest.mark.parametrize("invalid", ["NaN", "Infinity", "-Infinity", "10000000000000000", "not-a-number"])
def test_nonfinite_or_unbounded_decimal_rejected(invalid):
    with pytest.raises(ValueError, match="PROGRESS_DECIMAL_RANGE_INVALID"):
        value(invalid)


@pytest.mark.parametrize(
    "nature,expected",
    [
        ("INSTALL", ["FUTURE_NOT_INSTALLED", "INSTALLATION", "INSTALLED"]),
        ("REMOVE", ["EXISTING", "REMOVAL", "REMOVED"]),
        ("MAINTENANCE", ["EXISTING_IN_SERVICE", "MAINTENANCE_INTERVENTION", "RESTORED_IN_SERVICE"]),
    ],
)
@pytest.mark.parametrize("percentage,index", [("0", 0), ("50", 1), ("100", 2)])
def test_approved_physical_overlay_not_schedule_state(nature, expected, percentage, index):
    result = approved_overlay_state(nature, [{"progress_value": percentage}])
    assert result["state"] == expected[index]


@pytest.mark.parametrize(
    "phase,percentage,state",
    [
        ("INSTALL", "0", "ABSENT_BEFORE_INSTALL"),
        ("INSTALL", "50", "TEMPORARY_INSTALLATION"),
        ("INSTALL", "100", "TEMPORARY_IN_USE"),
        ("USE", "50", "TEMPORARY_IN_USE"),
        ("REMOVE", "50", "TEMPORARY_REMOVAL"),
        ("REMOVE", "100", "ABSENT_AFTER_REMOVAL"),
    ],
)
def test_temporary_approved_phase_is_explicit(phase, percentage, state):
    assert (
        approved_overlay_state(
            "TEMPORARY", [{"phase": phase, "progress_value": percentage, "as_of": "2026-10-22", "revision": 1}]
        )["state"]
        == state
    )


def test_missing_or_ambiguous_approved_physical_state_not_inferred_from_readiness():
    assert approved_overlay_state("INSTALL", [])["state"] == "NOT_MEASURED"
    assert approved_overlay_state("INSTALL", [{"progress_value": "50"}] * 2)["state"] == "REQUIRES_REVIEW"
    assert (
        approved_overlay_state("TEMPORARY", [{"phase": "EXECUTE", "progress_value": "50"}])["state"]
        == "REQUIRES_REVIEW"
    )


def test_temporary_overlay_preserves_latest_dated_phase_and_rejects_ambiguous_credit():
    previous = {"phase": "REMOVE", "progress_value": "100", "as_of": "2026-10-21", "revision": 1}
    latest = {"phase": "INSTALL", "progress_value": "50", "as_of": "2026-10-22", "revision": 1}
    assert approved_overlay_state("TEMPORARY", [previous, latest])["state"] == "TEMPORARY_INSTALLATION"
    assert approved_overlay_state("TEMPORARY", [latest, latest])["state"] == "REQUIRES_REVIEW"
