"""Deterministic Decimal formula engine for Gate 07M-FIN.

All rates are decimal fractions (for example 0.12 = 12%). Cash-flow timing is
periodic with the first item at t=0. The engine deliberately has no live market
data, optimizer, transaction, or Monte Carlo dependency.
"""

from __future__ import annotations

from decimal import Decimal, getcontext

getcontext().prec = 34

ENGINE_VERSION = "PPMIS-FIN-1.0"
ZERO = Decimal("0")
ONE = Decimal("1")


class FinancialFormulaError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def decimal(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return ZERO
    return value if isinstance(value, Decimal) else Decimal(str(value))


def npv(rate: Decimal, cash_flows: list[Decimal]) -> Decimal:
    rate = decimal(rate)
    if rate <= Decimal("-1"):
        raise FinancialFormulaError("INVALID_DISCOUNT_RATE")
    return sum((decimal(value) / ((ONE + rate) ** index) for index, value in enumerate(cash_flows)), ZERO)


def irr(cash_flows: list[Decimal]) -> Decimal:
    flows = [decimal(value) for value in cash_flows]
    non_zero = [value for value in flows if value != ZERO]
    if not non_zero or not any(value < ZERO for value in non_zero) or not any(value > ZERO for value in non_zero):
        raise FinancialFormulaError("IRR_NOT_COMPUTABLE")
    sign_changes = sum(
        1 for left, right in zip(non_zero, non_zero[1:], strict=False) if (left < ZERO) != (right < ZERO)
    )
    if sign_changes > 1:
        raise FinancialFormulaError("IRR_NOT_UNIQUE")

    low = Decimal("-0.999999")
    high = Decimal("1")
    low_value = npv(low, flows)
    high_value = npv(high, flows)
    while low_value * high_value > ZERO and high < Decimal("1000000"):
        high *= Decimal("2")
        high_value = npv(high, flows)
    if low_value * high_value > ZERO:
        raise FinancialFormulaError("IRR_NOT_COMPUTABLE")
    for _ in range(220):
        mid = (low + high) / Decimal("2")
        value = npv(mid, flows)
        if abs(value) <= Decimal("0.000000000001"):
            return mid
        if low_value * value <= ZERO:
            high = mid
        else:
            low = mid
            low_value = value
    return (low + high) / Decimal("2")


def wacc(equity: Decimal, debt: Decimal, cost_equity: Decimal, cost_debt: Decimal, tax_rate: Decimal) -> Decimal:
    equity = decimal(equity)
    debt = decimal(debt)
    total = equity + debt
    if total <= ZERO:
        raise FinancialFormulaError("WACC_CAPITAL_STRUCTURE_MISSING")
    return (equity / total) * decimal(cost_equity) + (debt / total) * decimal(cost_debt) * (ONE - decimal(tax_rate))


def payback_period(cash_flows: list[Decimal], rate: Decimal | None = None) -> Decimal | None:
    cumulative = ZERO
    for index, raw in enumerate(cash_flows):
        value = decimal(raw)
        if rate is not None:
            value /= (ONE + decimal(rate)) ** index
        previous = cumulative
        cumulative += value
        if cumulative >= ZERO and index > 0:
            if value == ZERO:
                return Decimal(index)
            fraction = abs(previous) / abs(value)
            return Decimal(index - 1) + min(ONE, fraction)
    return None


def benefit_cost_ratio(rate: Decimal, benefits: list[Decimal], costs: list[Decimal]) -> Decimal | None:
    pv_costs = sum((abs(decimal(value)) / ((ONE + decimal(rate)) ** index) for index, value in enumerate(costs)), ZERO)
    if pv_costs == ZERO:
        return None
    pv_benefits = sum((decimal(value) / ((ONE + decimal(rate)) ** index) for index, value in enumerate(benefits)), ZERO)
    return pv_benefits / pv_costs


def dscr(cfads: Decimal, debt_service: Decimal) -> Decimal | None:
    debt_service = decimal(debt_service)
    return None if debt_service == ZERO else decimal(cfads) / debt_service


def llcr(cfads: list[Decimal], debt_discount_rate: Decimal, outstanding_debt: Decimal) -> Decimal | None:
    debt = decimal(outstanding_debt)
    return None if debt <= ZERO else npv(decimal(debt_discount_rate), [ZERO, *cfads]) / debt


def moic(contributions: Decimal, distributions: Decimal) -> Decimal | None:
    contributions = decimal(contributions)
    return None if contributions <= ZERO else decimal(distributions) / contributions


def straight_line_amortization(commitment: Decimal, periods: int, grace_periods: int = 0) -> list[Decimal]:
    commitment = decimal(commitment)
    if periods <= grace_periods or periods <= 0:
        raise FinancialFormulaError("INVALID_AMORTIZATION_HORIZON")
    payment = commitment / Decimal(periods - grace_periods)
    return [ZERO] * grace_periods + [payment] * (periods - grace_periods)
