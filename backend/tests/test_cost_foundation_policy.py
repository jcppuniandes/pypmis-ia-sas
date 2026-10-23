"""Pure cost calculations are explicit Decimal, exact and authority-neutral."""

from datetime import date
from decimal import Decimal

import pytest

from app.modules.cost_foundation.policy import DEFAULT_PROFILE, aggregate_money, apu_total, spread_cost
from app.modules.cost_foundation.schemas import BudgetLineIn, MappingIn, RateIn


@pytest.mark.parametrize(
    "method", ["LINEAR", "FRONT_LOADED", "BACK_LOADED", "MILESTONE_BASED", "ACTIVITY_BASED", "CURVE_BASED"]
)
@pytest.mark.parametrize("amount", ["0", "100", "100.12345678"])
def test_spread_exact_sum(method, amount):
    spread = spread_cost(amount, date(2026, 10, 1), date(2026, 10, 3), method, weights=[1, 2, 1])
    assert sum(Decimal(r["amount"]) for r in spread) == Decimal(amount)
    assert all(Decimal(r["amount"]) >= 0 for r in spread)


def test_front_back_order_is_explicit():
    front = spread_cost(100, date(2026, 10, 1), date(2026, 10, 3), "FRONT_LOADED")
    back = spread_cost(100, date(2026, 10, 1), date(2026, 10, 3), "BACK_LOADED")
    assert Decimal(front[0]["amount"]) > Decimal(front[-1]["amount"])
    assert Decimal(back[0]["amount"]) < Decimal(back[-1]["amount"])


def test_tiny_spread_rounding_cannot_create_negative_residual():
    spread = spread_cost("0.00000060", date(2026, 1, 1), date(2026, 4, 10), "LINEAR")
    assert len(spread) == 100 and all(Decimal(r["amount"]) >= 0 for r in spread)
    assert sum(Decimal(r["amount"]) for r in spread) == Decimal("0.00000060")


def test_manual_spread_exact_reconciliation():
    result = spread_cost(
        100,
        date(2026, 10, 1),
        date(2026, 10, 3),
        "MANUAL",
        [{"date": "2026-10-01", "amount": "33.33"}, {"date": "2026-10-03", "amount": "66.67"}],
    )
    assert result[-1]["amount"] == "66.67000000"


@pytest.mark.parametrize(
    "spread",
    [
        [{"date": "2026-10-01", "amount": "1"}],
        [{"date": "2026-10-04", "amount": "100"}],
        [{"date": "2026-10-01", "amount": "50"}, {"date": "2026-10-01", "amount": "50"}],
        [{"date": "2026-10-01", "amount": "-1"}, {"date": "2026-10-02", "amount": "101"}],
    ],
)
def test_manual_spread_rejects_wrong_sum_dates_duplicates_negative(spread):
    with pytest.raises(ValueError):
        spread_cost(100, date(2026, 10, 1), date(2026, 10, 3), "MANUAL", spread)


@pytest.mark.parametrize("weights", [[], [1], [0, 0, 0], [-1, 1, 1]])
def test_curve_requires_nonnegative_exact_days(weights):
    with pytest.raises(ValueError):
        spread_cost(100, date(2026, 10, 1), date(2026, 10, 3), "CURVE_BASED", weights=weights)


def test_single_currency_aggregation_and_mixed_without_fx():
    assert (
        aggregate_money([{"currency": "USD", "amount": "0.1"}, {"currency": "USD", "amount": "0.2"}])["amount"]
        == "0.30000000"
    )
    result = aggregate_money([{"currency": "USD", "amount": 1}, {"currency": "COP", "amount": 4000}])
    assert result["status"] == "NO_AGGREGATION" and result["amount"] is None


def test_explicit_immutable_fx_basis():
    fx = {
        "id": 1,
        "from_currency": "COP",
        "to_currency": "USD",
        "rate": "0.00025",
        "status": "PUBLISHED",
        "effective_from": "2026-01-01",
        "effective_to": "2027-01-01",
        "source_reference": "CENTRAL_BANK",
    }
    rows = [{"currency": "USD", "amount": 1}, {"currency": "COP", "amount": 4000}]
    result = aggregate_money(rows, "USD", [fx], "2026-10-22")
    assert result["amount"] == "2.00000000" and result["conversions"][0]["fx_id"] == 1
    assert aggregate_money(rows, "USD", [fx], "2027-01-01")["status"] == "NO_AGGREGATION"
    assert aggregate_money(rows, "USD", [fx, fx], "2026-10-22")["status"] == "NO_AGGREGATION"


def test_apu_noncompounding_factors_and_decimal_components():
    result = apu_total(
        [
            {"quantity_per_unit": "2", "rate_snapshot": {"amount": "10.25"}},
            {"quantity_per_unit": "0.2", "rate_snapshot": {"amount": "0.1"}},
        ],
        [{"percentage": "10"}, {"percentage": "5"}],
    )
    assert result == Decimal("23.59800000")


def test_default_policy_reserve_boundary_and_no_full_forecast():
    assert DEFAULT_PROFILE["reserve_rules"]["inside_control_baseline"] is False
    assert DEFAULT_PROFILE["contingency_rules"]["inside_control_baseline"] is True
    assert DEFAULT_PROFILE["accrual_policy"] == "DEFERRED_WITH_CONTRACT"
    assert all(DEFAULT_PROFILE["separation_of_duties"].values())


@pytest.mark.parametrize(
    "model,body",
    [
        (
            RateIn,
            {
                "code": "R",
                "name": "Rate",
                "resource_type": "LABOR",
                "unit": "h",
                "amount": "NaN",
                "currency": "USD",
                "effective_from": "2026-01-01",
                "source_reference": "quote",
                "reason": "unit validation",
            },
        ),
        (
            MappingIn,
            {
                "source_kind": "SCOPE",
                "source_id": 1,
                "allocation_basis": "QUANTITY",
                "quantity_basis": "SCOPE",
                "effective_revision": "1",
                "source_reference": "scope",
                "percentage": 101,
                "reason": "mapping validation",
            },
        ),
        (
            BudgetLineIn,
            {
                "line_code": "L",
                "description": "Candidate",
                "quantity": -1,
                "unit": "m",
                "rate": 1,
                "currency": "USD",
                "reason": "cost validation",
            },
        ),
    ],
)
def test_invalid_money_and_allocation_rejected(model, body):
    with pytest.raises(ValueError):
        model(**body)
