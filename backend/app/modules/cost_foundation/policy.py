"""Deterministic Decimal cost policy; no inferred progress, treasury or FX."""

from datetime import timedelta
from decimal import ROUND_DOWN, Decimal, InvalidOperation

PHASING_METHODS = [
    "LINEAR",
    "FRONT_LOADED",
    "BACK_LOADED",
    "MILESTONE_BASED",
    "ACTIVITY_BASED",
    "MANUAL",
    "CURVE_BASED",
]
CATEGORIES = [
    "LABOR",
    "MATERIAL",
    "EQUIPMENT",
    "SUBCONTRACT",
    "ENGINEERING",
    "PROCUREMENT",
    "CONSTRUCTION",
    "TEMPORARY_WORKS",
    "LOGISTICS",
    "INDIRECTS",
    "OVERHEADS",
    "CONTINGENCY",
]
DEFAULT_PROFILE = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "effective_from": None,
    "effective_to": None,
    "cbs_templates": [],
    "cost_code_categories": CATEGORIES,
    "control_account_rules": {"owner_required": True, "one_account_per_wbs": False},
    "apu_categories": ["LABOR", "MATERIAL", "EQUIPMENT", "SUBCONTRACT", "OTHER"],
    "resource_types": ["LABOR", "MATERIAL", "EQUIPMENT", "SUBCONTRACT", "OTHER"],
    "units": ["m", "m2", "m3", "kg", "t", "ea", "h", "day", "ls"],
    "currencies": ["USD", "COP", "EUR"],
    "fx_policy": {"allow_conversion": True, "source_required": True, "missing_conversion": "NO_AGGREGATION"},
    "budget_types": ["ORIGINAL", "CURRENT", "APPROVED_CHANGE"],
    "baseline_types": ["ORIGINAL", "CURRENT"],
    "phasing_methods": PHASING_METHODS,
    "contingency_rules": {"inside_control_baseline": True, "level": "PROJECT_OR_PACKAGE"},
    "reserve_rules": {"inside_control_baseline": False, "level": "PROJECT", "owner_only": True},
    "commitment_inclusion_modes": ["INCLUDED", "CALL_OFF", "ADDITIVE", "REFERENCE_ONLY"],
    "actual_source_types": ["CONTROLLED_MANUAL", "ACCOUNTING_IMPORT", "ERP_REFERENCE", "APPROVED_INVOICE_RECOGNITION"],
    "accrual_policy": "DEFERRED_WITH_CONTRACT",
    "etc_methods": ["BOTTOM_UP", "QUANTITY_RATE", "COMMITMENT_BASED", "PRODUCTIVITY_BASED", "STATISTICAL", "MANUAL"],
    "budget_approval_workflow": ["DRAFT", "SUBMITTED", "UNDER_REVIEW", "APPROVED"],
    "separation_of_duties": {
        "author_cannot_publish": True,
        "rate_editor_cannot_publish": True,
        "budget_preparer_cannot_approve": True,
        "baseline_preparer_cannot_approve": True,
        "actual_importer_cannot_approve": True,
    },
}
BUDGET_LIFECYCLE = {
    "DRAFT": {"SUBMITTED"},
    "SUBMITTED": {"UNDER_REVIEW", "REJECTED"},
    "UNDER_REVIEW": {"APPROVED", "REJECTED"},
}


def money(value):
    result = Decimal(str(value)).quantize(Decimal("0.00000001"))
    if not result.is_finite() or abs(result) >= Decimal("10000000000000000"):
        raise InvalidOperation("COST_AMOUNT_OUT_OF_RANGE")
    return result


def spread_cost(amount, start, finish, method, manual=(), weights=()):
    """Exact sum preservation, inclusive dates, explicit manual/curve basis."""
    amount = money(amount)
    if finish < start or (finish - start).days > 10000:
        raise ValueError("COST_PHASING_WINDOW_INVALID")
    days = (finish - start).days + 1
    if method == "MANUAL":
        result = [{"date": str(row["date"]), "amount": str(money(row["amount"]))} for row in manual]
        if (
            not result
            or len({r["date"] for r in result}) != len(result)
            or any(not str(start) <= r["date"] <= str(finish) or Decimal(r["amount"]) < 0 for r in result)
            or sum(Decimal(r["amount"]) for r in result) != amount
        ):
            raise ValueError("COST_MANUAL_SPREAD_MUST_RECONCILE")
        return sorted(result, key=lambda r: r["date"])
    if method == "MILESTONE_BASED":
        return [{"date": str(finish), "amount": str(amount)}]
    if method == "CURVE_BASED":
        basis = [Decimal(str(w)) for w in weights]
        if len(basis) != days or any(w < 0 for w in basis) or sum(basis) <= 0:
            raise ValueError("COST_CURVE_WEIGHTS_INVALID")
    elif method == "FRONT_LOADED":
        basis = [Decimal(days - n) for n in range(days)]
    elif method == "BACK_LOADED":
        basis = [Decimal(n + 1) for n in range(days)]
    elif method in {"LINEAR", "ACTIVITY_BASED"}:
        basis = [Decimal(1)] * days
    else:
        raise ValueError("COST_PHASING_METHOD_INVALID")
    total = sum(basis)
    amounts = [(amount * w / total).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN) for w in basis]
    amounts[-1] += amount - sum(amounts)
    return [{"date": str(start + timedelta(days=n)), "amount": str(value)} for n, value in enumerate(amounts)]


def apu_total(components, factors):
    direct = sum(
        (Decimal(str(c["quantity_per_unit"])) * Decimal(str(c["rate_snapshot"]["amount"])) for c in components),
        Decimal(0),
    )
    return money(direct * (Decimal(1) + sum((Decimal(str(f["percentage"])) for f in factors), Decimal(0)) / 100))


def aggregate_money(items, target_currency=None, fx_rates=(), conversion_date=None):
    """Never assume currency or conversion; explicit immutable FX only."""
    totals = {}
    for item in items:
        totals[item["currency"]] = totals.get(item["currency"], Decimal(0)) + Decimal(str(item["amount"]))
    if not totals:
        return {
            "status": "AGGREGATED",
            "currency": target_currency,
            "amount": "0",
            "by_currency": {},
            "conversions": [],
        }
    if len(totals) == 1 and (target_currency is None or target_currency in totals):
        currency = next(iter(totals))
        return {
            "status": "AGGREGATED",
            "currency": currency,
            "amount": str(money(totals[currency])),
            "by_currency": {k: str(money(v)) for k, v in totals.items()},
            "conversions": [],
        }
    converted, lineage = Decimal(0), []
    for currency, amount in totals.items():
        if currency == target_currency:
            converted += amount
            continue
        candidates = [
            r
            for r in fx_rates
            if r.get("from_currency") == currency
            and r.get("to_currency") == target_currency
            and r.get("status") == "PUBLISHED"
            and conversion_date
            and str(r["effective_from"]) <= str(conversion_date)
            and (not r.get("effective_to") or str(conversion_date) < str(r["effective_to"]))
        ]
        if len(candidates) != 1:
            return {
                "status": "NO_AGGREGATION",
                "currency": None,
                "amount": None,
                "by_currency": {k: str(money(v)) for k, v in totals.items()},
                "conversions": [],
            }
        rate = candidates[0]
        converted += amount * Decimal(str(rate["rate"]))
        lineage.append(
            {
                "fx_id": rate.get("id"),
                "source": rate.get("source_reference"),
                "conversion_date": str(conversion_date),
                "basis": rate,
            }
        )
    return {
        "status": "AGGREGATED",
        "currency": target_currency,
        "amount": str(money(converted)),
        "by_currency": {k: str(money(v)) for k, v in totals.items()},
        "conversions": lineage,
    }
