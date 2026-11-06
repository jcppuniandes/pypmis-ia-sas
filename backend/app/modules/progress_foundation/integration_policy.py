"""Pure Decimal integrated progress and EVM calculations with explicit missingness."""

from decimal import Decimal, InvalidOperation, localcontext

QUANTUM = Decimal("0.00000001")
ZERO = Decimal(0)
HUNDRED = Decimal(100)
EARNED_SOURCES = {"PHYSICAL", "QUANTITY", "MILESTONE"}


def value(number):
    try:
        result = Decimal(str(number))
        if not result.is_finite() or abs(result) >= Decimal("1e16"):
            raise ValueError("PROGRESS_DECIMAL_RANGE_INVALID")
        with localcontext() as context:
            context.prec = 48
            return result.quantize(QUANTUM)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("PROGRESS_DECIMAL_RANGE_INVALID") from error


def weighted_progress(inputs):
    if not inputs:
        return {"status": "NOT_COMPUTABLE", "reason_codes": ["APPROVED_PROGRESS_REQUIRED"], "progress_value": None}
    weights = [value(row["weight"]) for row in inputs]
    if any(weight <= ZERO for weight in weights):
        return {"status": "NOT_COMPUTABLE", "reason_codes": ["POSITIVE_WEIGHT_REQUIRED"], "progress_value": None}
    bases = {row["weighting_basis"] for row in inputs}
    if len(bases) != 1:
        return {"status": "NOT_COMPUTABLE", "reason_codes": ["WEIGHTING_BASIS_MISMATCH"], "progress_value": None}
    if any(not ZERO <= value(row["progress_value"]) <= HUNDRED for row in inputs):
        return {"status": "NOT_COMPUTABLE", "reason_codes": ["PROGRESS_OUT_OF_BOUNDS"], "progress_value": None}
    with localcontext() as context:
        context.prec = 48
        numerator = sum(
            (value(row["progress_value"]) * weight for row, weight in zip(inputs, weights, strict=True)), ZERO
        )
        denominator = sum(weights, ZERO)
        return {
            "status": "COMPUTABLE",
            "reason_codes": [],
            "progress_value": str((numerator / denominator).quantize(QUANTUM)),
            "numerator": str(numerator),
            "denominator": str(denominator),
            "weighting_basis": next(iter(bases)),
        }


def evm_values(pv, ev, ac, *, errors=()):
    reasons = list(dict.fromkeys(errors))
    inputs = {
        "pv": None if pv is None else str(value(pv)),
        "ev": None if ev is None else str(value(ev)),
        "ac": None if ac is None else str(value(ac)),
    }
    for name, number in inputs.items():
        if number is None:
            reasons.append(f"MISSING_{name.upper()}")
        elif value(number) < ZERO:
            reasons.append(f"NEGATIVE_{name.upper()}")
    if pv is not None and value(pv) == ZERO:
        reasons.append("ZERO_PV_DENOMINATOR")
    if ac is not None and value(ac) == ZERO:
        reasons.append("ZERO_AC_DENOMINATOR")
    if reasons:
        return {
            "status": "NOT_COMPUTABLE",
            "reason_codes": list(dict.fromkeys(reasons)),
            "pv": None,
            "ev": None,
            "ac": None,
            "cpi": None,
            "spi": None,
            "source_values": inputs,
        }
    with localcontext() as context:
        context.prec = 48
        return {
            "status": "COMPUTABLE",
            "reason_codes": [],
            **inputs,
            "cpi": str((value(ev) / value(ac)).quantize(QUANTUM)),
            "spi": str((value(ev) / value(pv)).quantize(QUANTUM)),
            "source_values": inputs,
        }


def earned_amount(budget_amount, approved_percentage):
    budget, progress = value(budget_amount), value(approved_percentage)
    if budget < ZERO or not ZERO <= progress <= HUNDRED:
        raise ValueError("EARNED_BASIS_OUT_OF_BOUNDS")
    with localcontext() as context:
        context.prec = 48
        return (budget * progress / HUNDRED).quantize(QUANTUM)
