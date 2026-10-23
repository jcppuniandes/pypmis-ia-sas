"""Economic-origin reconciliation and explicit monetary contracts without a DB."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.cost_foundation.financial_schemas import ActualAdjustmentIn, CommitmentIn, EACReferenceIn
from app.modules.cost_foundation.financials import (
    actual_history_balanced,
    aggregate_original_money,
    fx_date_is_effective,
    money,
    reconcile_obligations,
)


def obligation(kind="CONTRACT", amount="100", origin="ROOT", mode="ADDITIVE", **changes):
    return {
        "id": 1,
        "status": "VERIFIED",
        "source_type": kind,
        "amount": amount,
        "currency": "USD",
        "economic_origin": origin,
        "parent_economic_origin": None,
        "inclusion_mode": mode,
        **changes,
    }


@pytest.mark.parametrize("kind", ["CONTRACT", "PO", "SUBCONTRACT", "CONTRACT_CHANGE_ORDER"])
def test_independent_obligation_once(kind):
    result = reconcile_obligations([obligation(kind)])
    assert result["net_commitment"] == "100.00000000"
    assert result["authority"] == "READ_MODEL_NOT_CONTRACTUAL_AUTHORITY"


@pytest.mark.parametrize("mode", ["INCLUDED", "CALL_OFF", "REFERENCE_ONLY"])
def test_contract_with_non_additive_po_does_not_double_count(mode):
    result = reconcile_obligations(
        [obligation(), obligation("PO", "40", mode=mode, parent_economic_origin="ROOT", id=2)]
    )
    assert result["net_commitment"] == "100.00000000"
    assert result["items"][1]["net_contribution"] == "0"


def test_contract_plus_explicit_additive_po():
    result = reconcile_obligations([obligation(), obligation("PO", "40", origin="PO-INCREMENT", id=2)])
    assert result["net_commitment"] == "140.00000000"


def test_approved_change_delta_not_whole_contract_again():
    result = reconcile_obligations(
        [obligation(), obligation("CONTRACT_CHANGE_ORDER", "15", origin="CO-1", parent_economic_origin="ROOT", id=2)]
    )
    assert result["net_commitment"] == "115.00000000"


def test_same_economic_origin_twice_fails_closed():
    result = reconcile_obligations([obligation(), obligation("PO", "100", id=2)])
    assert result["net_commitment"] is None
    assert result["status"] == "RECONCILIATION_REQUIRED"
    assert result["issues"][0]["code"] == "DUPLICATE_ECONOMIC_ORIGIN"


@pytest.mark.parametrize(
    "status,expected", [("PROPOSED", "100.00000000"), ("REJECTED", "100.00000000"), ("VERIFIED", "120.00000000")]
)
def test_refresh_effective_only_after_independent_verification(status, expected):
    old = obligation(id=1, source_revision="1")
    successor = obligation(id=2, amount="120", supersedes_id=1, source_revision="2", status=status)
    result = reconcile_obligations([old, successor])
    assert result["net_commitment"] == expected
    assert result["issues"] == []
    assert old["status"] == "VERIFIED" and old["amount"] == "100"


def test_chain_refresh_does_not_reintroduce_historical_parent():
    result = reconcile_obligations(
        [
            obligation(id=1),
            obligation(id=2, amount="120", supersedes_id=1),
            obligation(id=3, amount="130", supersedes_id=2),
        ]
    )
    assert result["net_commitment"] == "130.00000000"
    assert [row["status"] for row in result["items"]] == ["SUPERSEDED_PROJECTION", "SUPERSEDED_PROJECTION", "VERIFIED"]


@pytest.mark.parametrize("mode", ["INCLUDED", "CALL_OFF"])
def test_missing_economic_parent_is_not_zero_with_success(mode):
    result = reconcile_obligations([obligation("PO", mode=mode, parent_economic_origin="ABSENT")])
    assert result["status"] == "RECONCILIATION_REQUIRED" and result["net_commitment"] is None


def test_calloff_total_cannot_exceed_contract_ceiling():
    result = reconcile_obligations(
        [
            obligation(),
            obligation("PO", "60", mode="CALL_OFF", parent_economic_origin="ROOT", id=2),
            obligation("PO", "60", mode="CALL_OFF", parent_economic_origin="ROOT", id=3),
        ]
    )
    assert result["issues"][0]["code"] == "CALL_OFF_EXCEEDS_PARENT"


def test_included_child_currency_not_assumed_convertible():
    result = reconcile_obligations(
        [obligation(), obligation("PO", "20", mode="INCLUDED", parent_economic_origin="ROOT", currency="COP")]
    )
    assert result["issues"][0]["code"] == "PARENT_CURRENCY_MISMATCH"


def test_included_po_cannot_exceed_parent_obligation():
    result = reconcile_obligations(
        [obligation(), obligation("PO", "150", mode="INCLUDED", parent_economic_origin="ROOT", id=2)]
    )
    assert result["status"] == "RECONCILIATION_REQUIRED" and result["net_commitment"] is None
    assert result["issues"][0]["code"] == "INCLUDED_AMOUNT_EXCEEDS_PARENT"


@pytest.mark.parametrize("status", ["PROPOSED", "REJECTED", "SOURCE_STALE"])
def test_unverified_reference_never_contributes(status):
    result = reconcile_obligations([obligation(status=status)])
    assert result["by_currency"] == {} and result["net_commitment"] is None


def test_two_currencies_no_silent_net():
    result = reconcile_obligations([obligation(), obligation("PO", origin="COP-1", currency="COP")])
    assert result["status"] == "NO_AGGREGATION" and result["net_commitment"] is None
    assert result["by_currency"] == {"COP": "100.00000000", "USD": "100.00000000"}


def test_actual_adjustment_is_delta_not_replacement_double_add():
    result = aggregate_original_money([{"amount": "100", "currency": "USD"}, {"amount": "-10", "currency": "USD"}])
    assert result["amount"] == "90.00000000"


def test_actual_multi_currency_no_aggregate():
    result = aggregate_original_money([{"amount": "100", "currency": "USD"}, {"amount": "500", "currency": "COP"}])
    assert result["status"] == "NO_AGGREGATION" and result["amount"] is None


def test_decimal_exactness():
    assert money("0.1") + money("0.2") == Decimal("0.30000000")


@pytest.mark.parametrize(
    "day,expected",
    [(date(2026, 1, 1), True), (date(2026, 1, 31), True), (date(2026, 2, 1), False), (date(2025, 12, 31), False)],
)
def test_fx_effective_interval_matches_core_half_open(day, expected):
    assert fx_date_is_effective(date(2026, 1, 1), date(2026, 2, 1), day) is expected


def test_adjustment_cannot_make_historical_actual_negative_despite_positive_current_total():
    deltas = [{"amount": "100", "recognition_date": "2026-10-25"}, {"amount": "-150", "recognition_date": "2026-10-23"}]
    assert actual_history_balanced("100", "2026-10-22", deltas) is False


def test_same_day_adjustments_evaluated_as_one_recognition_day():
    deltas = [{"amount": "100", "recognition_date": "2026-10-23"}, {"amount": "-150", "recognition_date": "2026-10-23"}]
    assert actual_history_balanced("100", "2026-10-22", deltas) is True


def test_eac_reference_requires_explicit_commitment_inclusion_and_acceptance():
    with pytest.raises(ValidationError):
        EACReferenceIn(etc_amount="10", currency="USD", method="BOTTOM_UP", as_of="2026-10-22")
    row = EACReferenceIn(
        etc_amount="10",
        currency="USD",
        method="COMMITMENT_BASED",
        as_of="2026-10-22",
        includes_commitments=True,
        acceptance_reference="APPROVED-FORECAST-EXTERNAL",
    )
    assert row.includes_commitments is True


def test_commitment_contract_cannot_silently_invent_new_legal_kind():
    with pytest.raises(ValidationError):
        CommitmentIn(
            reason="Controlled reconciliation",
            source_system="ERP",
            source_type="INVOICE",
            source_reference="1",
            source_revision="1",
            source_hash="a" * 64,
            source_document="approved external doc",
            source_approval_status="APPROVED",
            economic_origin="1",
            inclusion_mode="ADDITIVE",
            amount="100",
            currency="USD",
            effective_date="2026-10-22",
        )


def test_adjustment_contract_accepts_negative_without_allowing_zero_original():
    row = ActualAdjustmentIn(
        reason="Independent reversal reference",
        source_system="ERP",
        source_reference="ADJ1",
        posting_date="2026-10-22",
        recognition_date="2026-10-22",
        period_id=1,
        amount="-10",
        currency="USD",
        evidence_ref="document:adjustment",
    )
    assert row.amount < 0
