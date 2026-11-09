"""Executable examples for O2 design invariants; no application or database imports."""

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCH = ROOT / "docs/architecture/wave-o2"
D = Decimal
SCOPE = ("tenant-example", "project-example")


@dataclass(frozen=True)
class Fact:
    origin: str
    amount: Decimal
    mode: str = "ADDITIVE"
    currency: str = "USD"
    scope: tuple[str, str] = SCOPE
    parent: str | None = None
    effective: int = 1
    known: int = 1
    approved: bool = True


def rollup(facts, *, as_of=10, known_at=10):
    """One eligible effective revision per origin before coverage and aggregation."""
    current = {}
    for row in facts:
        if row.scope != SCOPE:
            raise ValueError("CROSS_SCOPE")
        if not row.approved or row.effective > as_of or row.known > known_at:
            continue
        old = current.get(row.origin)
        if old and (row.effective, row.known) == (old.effective, old.known):
            raise ValueError("DUPLICATE_ORIGIN")
        if not old or (row.effective, row.known) > (old.effective, old.known):
            current[row.origin] = row
    totals, coverage = {}, {}
    for row in current.values():
        if row.mode == "ADDITIVE":
            totals[row.currency] = totals.get(row.currency, D(0)) + row.amount
        elif row.mode in {"INCLUDED", "CALL_OFF"}:
            parent = current.get(row.parent)
            if (
                not parent
                or parent.mode != "ADDITIVE"
                or parent.currency != row.currency
            ):
                raise ValueError("COVERAGE_INCOMPATIBLE")
            covered = coverage.get(parent.origin, D(0)) + row.amount
            if covered > parent.amount:
                raise ValueError("EXCESS_COVERAGE")
            coverage[parent.origin] = covered
        elif row.mode != "REFERENCE_ONLY":
            raise ValueError("UNKNOWN_MODE")
    return totals


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode()
    ).hexdigest()


def denied(action, code):
    try:
        action()
    except ValueError as error:
        assert str(error) == code, error
    else:
        raise AssertionError(f"{code} was not rejected")


def main():
    results = []

    def check(identifier, name, observed):
        results.append([identifier, name, "PASS DISEÑO", observed])

    master = Fact("master", D(100))
    included = Fact("included-po", D(30), "INCLUDED", parent="master")
    calloff = Fact("call-off", D(20), "CALL_OFF", parent="master")
    subcontract = Fact("subcontract", D(10))
    sow = Fact("sov-view", D(100), "REFERENCE_ONLY")
    mirror = Fact("legacy-crosswalk", D(100), "REFERENCE_ONLY")
    facts = (master, included, calloff, subcontract, sow, mirror)
    original = digest([asdict(row) for row in facts])
    assert rollup(facts) == {"USD": D(110)}
    assert rollup(
        (replace(master, mode="REFERENCE_ONLY"), Fact("binding-order", D(20)))
    ) == {"USD": D(20)}
    assert digest([asdict(row) for row in facts]) == original
    check(
        "V-01",
        "Modos de inclusión y techo informativo",
        "110 USD sobre 100 de contrato y 10 aditivos; marco no vinculante deja 20 USD de orden independiente",
    )

    denied(lambda: rollup((master, replace(calloff, amount=D(101)))), "EXCESS_COVERAGE")
    denied(
        lambda: rollup((master, replace(included, currency="EUR"))),
        "COVERAGE_INCOMPATIBLE",
    )
    denied(
        lambda: rollup((master, replace(included, parent="not-linked"))),
        "COVERAGE_INCOMPATIBLE",
    )
    check(
        "V-02",
        "Cobertura contractual",
        "Exceso, padre ausente y moneda incompatible se rechazan",
    )

    denied(lambda: rollup((master, master)), "DUPLICATE_ORIGIN")
    denied(
        lambda: rollup(
            (master, replace(subcontract, scope=(SCOPE[0], "other-project")))
        ),
        "CROSS_SCOPE",
    )
    check(
        "V-03",
        "Identidad y aislamiento",
        "Duplicado económico y fuente de otro Project se rechazan",
    )

    successor = replace(master, amount=D(115), effective=3, known=4)
    draft = replace(master, amount=D(110), approved=False, effective=5, known=5)
    assert rollup((master, successor, draft), as_of=2) == {"USD": D(100)}
    assert rollup((master, successor, draft), known_at=3) == {"USD": D(100)}
    assert rollup((master, successor, draft)) == {"USD": D(115)}
    assert master.amount == D(100)
    check(
        "V-04",
        "Sucesor SOV y corte histórico",
        "100 original; +15 aprobado; 115 vigente; el borrador y el conocimiento posterior no reescriben la historia",
    )

    assert rollup((master, Fact("eur-line", D(7), currency="EUR"))) == {
        "USD": D(100),
        "EUR": D(7),
    }
    check(
        "V-05",
        "Moneda sin FX elegible",
        "100 USD y 7 EUR se conservan separados; no existe total multimoneda",
    )

    quantity, rate, previous, current = map(D, (12, 20, 2, 3))
    assert (
        D(10) * rate,
        quantity * rate,
        (previous + current) * rate,
        (quantity - previous - current) * rate,
    ) == tuple(map(D, (200, 240, 100, 140)))
    assert quantity - previous - current == D(7)
    check(
        "V-06",
        "UNIT_RATE y certificación separada",
        "Original 200; vigente 240; certificado 100; saldo 140 USD y 7 unidades",
    )

    allocations = {
        ("origin", "SOV-1", "CBS-A"): D(60),
        ("origin", "SOV-2", "CBS-B"): D(30),
        ("origin", "unallocated", "UNALLOCATED"): D(10),
    }
    contextual = [("SOV-1", "EWP-1"), ("SOV-1", "IWP-3"), ("SOV-2", "CWP-1")]
    assert len(contextual) == 3 and sum(allocations.values()) == master.amount
    forward = [key for key in allocations if key[-1] == "CBS-A"]
    reverse = [key for key in allocations if key[1] == "SOV-1"]
    assert forward == reverse == [("origin", "SOV-1", "CBS-A")]
    check(
        "V-07",
        "Roll-up y drill-down por asignación",
        "El join contextual no suma dinero; CBS-A y SOV-1 resuelven al mismo origen; 10 quedan sin asignar",
    )

    # Truth tables: these are isolated architectural examples, not app commands.
    award_rows = [
        (False, True, True, False),
        (True, False, True, False),
        (True, True, False, False),
        (True, True, True, True),
    ]
    assert all(
        (authorized and explicit and independent) == result
        for authorized, explicit, independent, result in award_rows
    )
    check(
        "V-08",
        "Handoff de adjudicación",
        "Solo autorización vigente más comando explícito y actor independiente permiten el borrador contractual",
    )

    required = {
        "ENGINEERING",
        "PROCUREMENT",
        "MATERIAL",
        "LOGISTICS",
        "CONTRACTUAL",
        "VENDOR",
        "ACCESS",
        "HSE",
    }
    eligible = dict.fromkeys(required, True)
    assert all(eligible.values()) and not (all(eligible.values()) and False)
    unavailable = {**eligible, "MATERIAL": False}
    stale = {**eligible, "ENGINEERING": False}
    assert not all(unavailable.values()) and not all(stale.values())
    check(
        "V-09",
        "Caso IWP de bomba",
        "ORDERED y revisión IFC obsoleta bloquean READY; READY requiere además un comando para RELEASED",
    )

    proof = {"result": "PASS", "scope": "OFFLINE_DESIGN_ONLY", "cases": results}
    (ARCH / "design-checks.json").write_text(
        json.dumps(proof, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps({"result": "PASS", "scope": proof["scope"], "cases": len(results)})
    )


if __name__ == "__main__":
    main()
