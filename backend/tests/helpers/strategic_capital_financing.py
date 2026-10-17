"""Payload-only reuse with real commands and independent reviewers for fresh UAT.

No fixtures, terminal inserts, published ORM configurations or fixed IDs.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from tests.test_gate07m_fid_e2e import FUNDING_PLAN, TOTAL_INVESTMENT

from app.modules.economic_financial_model.service import EconomicFinancialModelService
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.funds_manager.schemas import FundCreateIn, FundingAssignmentCreateIn, FundingSourceCreateIn
from app.modules.funds_manager.service import FundsManagerService
from app.modules.portfolio_analysis.service import _hash


def _ctx(db, tenant_id, actor_id, permission):
    return require_enterprise_permission(db, tenant_id, actor_id, permission, bootstrap=False)


def complete_funding(db, tenant_id, actor_id, reviewer_id, portfolio_id, project_id):
    assert actor_id != reviewer_id
    # Policies are published by the orchestrator without changing default SoD.
    service = FundsManagerService(db, tenant_id, actor_id, _ctx(db, tenant_id, actor_id, "funding_source.create"))
    reviewer = FundsManagerService(db, tenant_id, reviewer_id, _ctx(db, tenant_id, reviewer_id, "fund.authorize"))
    assignments = []
    for key, source_type, _instrument_type, amount in FUNDING_PLAN:
        source = service.create_funding_source(
            FundingSourceCreateIn(
                source_name=f"{key} governed source",
                source_type=source_type,
                currency="USD",
                effective_from=date(2027, 1, 1),
                effective_to=date(2030, 12, 31),
                evidence_refs=[{"reference": f"AUTH-{key}-2026"}],
                source_reference=f"Controlled source {key}",
                idempotency_key=f"fid-source-{key}-{uuid4()}",
            )
        )
        source = service.transition_funding_source(
            source.id,
            source.revision_version,
            "activate",
            f"fid-source-activate-{key}-{uuid4()}",
        )
        fund = service.create_fund(
            FundCreateIn(
                fund_name=f"{key} commercial commitment",
                funding_source_id=source.id,
                currency="USD",
                authorized_amount=amount,
                available_from=date(2027, 1, 1),
                available_to=date(2030, 12, 31),
                period_granularity="TOTAL",
                evidence_refs=[{"reference": f"FUND-{key}-AUTH"}],
                source_reference=f"Approved {key} funding",
                idempotency_key=f"fid-fund-{key}-{uuid4()}",
            )
        )
        fund = reviewer.transition_fund(
            fund.id,
            fund.revision_version,
            "authorize",
            f"fid-fund-authorize-{key}-{uuid4()}",
        )
        fund = service.transition_fund(
            fund.id,
            fund.revision_version,
            "activate",
            f"fid-fund-activate-{key}-{uuid4()}",
        )
        assignment = service.create_funding_assignment(
            FundingAssignmentCreateIn(
                fund_id=fund.id,
                scope_type="PROJECT",
                portfolio_workspace_id=portfolio_id,
                project_workspace_id=project_id,
                amount=amount,
                currency="USD",
                period_start=date(2027, 1, 1),
                period_end=date(2030, 12, 31),
                period_profile=[{"period_key": "2027", "amount": amount}],
                assignment_purpose=f"{key} share of the deterministic investment plan.",
                evidence_refs=[{"reference": f"ASSIGN-{key}-2026"}],
                idempotency_key=f"fid-assignment-{key}-{uuid4()}",
            )
        )
        assignment = reviewer.transition_funding_assignment(
            assignment.id,
            assignment.revision_version,
            "confirm",
            f"fid-assignment-confirm-{key}-{uuid4()}",
        )
        assignments.append(assignment)
    preview = service.refresh_preview(portfolio_id)
    readiness = service.refresh(
        portfolio_id,
        preview.proposed_source_hash,
        f"fid-funding-refresh-{uuid4()}",
    )
    assert readiness.required_amount == TOTAL_INVESTMENT
    assert readiness.confirmed_funding_amount == TOTAL_INVESTMENT
    assert readiness.confirmed_coverage_percent == 100
    assert readiness.can_supply_investment_gate_evidence is True
    return readiness, assignments


def complete_fin(
    db, tenant_id, actor_id, reviewer_id, project, case, budget_scenario_id, funding_readiness_id, assignments
):
    assert actor_id != reviewer_id
    financial = EconomicFinancialModelService(
        db, tenant_id, actor_id, _ctx(db, tenant_id, actor_id, "economic_financial_model.create")
    )
    financial.ensure_seed()
    model = financial.create(
        {
            "project_workspace_id": project.id,
            "business_case_id": case.id,
            "model_type": "COMMERCIAL_PROJECT",
            "base_currency": "USD",
            "cash_flow_basis": "NOMINAL",
            "periodicity": "ANNUAL",
            "model_start_date": date(2027, 1, 1),
            "model_end_date": date(2030, 12, 31),
            "construction_start": date(2027, 1, 1),
            "operations_start": date(2028, 1, 1),
            "operations_end": date(2030, 12, 31),
            "terminal_date": date(2030, 12, 31),
            "budget_scenario_id": budget_scenario_id,
            "funding_readiness_id": funding_readiness_id,
            "idempotency_key": f"fid-fin-model-{uuid4()}",
        }
    )
    version = model.current_version
    assert version is not None
    for key, value in {
        "project_discount_rate": Decimal("0.10"),
        "cost_of_equity": Decimal("0.14"),
        "cost_of_debt": Decimal("0.05"),
        "tax_rate": Decimal("0.25"),
        "inflation_rate": Decimal("0.03"),
    }.items():
        financial.upsert_assumption(
            version.id,
            version.revision_version,
            {
                "assumption_key": key,
                "name": key.replace("_", " ").title(),
                "category": "DISCOUNT_RATE" if "rate" in key else "GENERAL",
                "numeric_value": value,
                "text_value": None,
                "unit": "RATE",
                "periodicity": "ANNUAL",
                "effective_from": None,
                "effective_to": None,
                "source": "GOVERNED_POLICY",
                "source_reference": "PYP-FFA deterministic fixture",
                "rationale": "Controlled full-stack validation input.",
                "is_override": False,
            },
        )
        version = financial._version(version.id)
    period_values = (
        {
            "capex": "100000000",
            "revenue": "0",
            "opex": "0",
            "draw": "60000000",
            "interest": "0",
            "principal": "0",
            "equity": "35000000",
            "distribution": "0",
        },
        {
            "capex": "0",
            "revenue": "55000000",
            "opex": "15000000",
            "draw": "0",
            "interest": "3000000",
            "principal": "20000000",
            "equity": "0",
            "distribution": "5000000",
        },
        {
            "capex": "0",
            "revenue": "60000000",
            "opex": "15000000",
            "draw": "0",
            "interest": "2000000",
            "principal": "20000000",
            "equity": "0",
            "distribution": "15000000",
        },
        {
            "capex": "0",
            "revenue": "65000000",
            "opex": "15000000",
            "draw": "0",
            "interest": "1000000",
            "principal": "20000000",
            "equity": "0",
            "distribution": "50000000",
        },
    )
    for index, row in enumerate(period_values):
        year = 2027 + index
        financial.upsert_period(
            version.id,
            version.revision_version,
            {
                "period_index": index,
                "period_label": f"FY{year}",
                "period_start": date(year, 1, 1),
                "period_end": date(year, 12, 31),
                "currency": "USD",
                "revenue": Decimal(row["revenue"]),
                "economic_benefits": Decimal("0"),
                "opex": Decimal(row["opex"]),
                "taxes": Decimal("0"),
                "working_capital_change": Decimal("0"),
                "capex": Decimal(row["capex"]),
                "debt_drawdown": Decimal(row["draw"]),
                "interest": Decimal(row["interest"]),
                "principal": Decimal(row["principal"]),
                "equity_contribution": Decimal(row["equity"]),
                "distribution": Decimal(row["distribution"]),
                "source_reference": "Commercial cash-flow model",
                "source_hash": _hash(row),
            },
        )
        version = financial._version(version.id)

    instruments = {}
    for (key, _source_type, instrument_type, amount), assignment in zip(FUNDING_PLAN, assignments, strict=True):
        instrument = financial.create_instrument(
            version.id,
            version.revision_version,
            {
                "instrument_key": key,
                "name": f"{key} financing instrument",
                "instrument_type": instrument_type,
                "currency": "USD",
                "committed_amount": amount,
                "drawn_amount": amount if instrument_type in {"BANK_LOAN", "DEVELOPMENT_BANK_LOAN"} else Decimal("0"),
                "funding_assignment_id": assignment.id,
                "interest_basis": "FIXED" if instrument_type in {"BANK_LOAN", "DEVELOPMENT_BANK_LOAN"} else None,
                "fixed_rate": Decimal("0.05")
                if instrument_type == "BANK_LOAN"
                else (Decimal("0.03") if instrument_type == "DEVELOPMENT_BANK_LOAN" else None),
                "principal_grace_periods": 1,
                "interest_grace_periods": 0,
                "tenor_periods": 4 if instrument_type in {"BANK_LOAN", "DEVELOPMENT_BANK_LOAN"} else None,
                "drawdown_method": "CUSTOM",
                "amortization_method": "CUSTOM",
                "interest_during_construction": "CASH_PAY",
                "covenants_json": [],
                "idempotency_key": f"fid-instrument-{key}-{uuid4()}",
            },
        )
        instruments[key] = instrument
        version = financial._version(version.id)
    for key, investor_type, ownership in (
        ("SPONSOR", "SPONSOR", "57.142857"),
        ("EXTERNAL", "EXTERNAL_INSTITUTIONAL", "42.857143"),
    ):
        instrument = instruments[key]
        financial.create_investor(
            version.id,
            version.revision_version,
            {
                "financing_instrument_id": instrument.id,
                "investor_key": key,
                "name": f"{key} governed investor",
                "investor_type": investor_type,
                "committed_equity": instrument.committed_amount,
                "ownership_percent": Decimal(ownership),
                "preferred_return": Decimal("0.08"),
                "distribution_priority": 1 if key == "EXTERNAL" else 2,
                "capital_call_profile_json": [{"period": "2027", "amount": str(instrument.committed_amount)}],
                "distribution_profile_json": [{"period": "2030", "priority": 1 if key == "EXTERNAL" else 2}],
                "hurdle_rate": Decimal("0.12"),
                "idempotency_key": f"fid-investor-{key}-{uuid4()}",
            },
        )
        version = financial._version(version.id)
    calculated = financial.calculate(version.id, version.revision_version, f"fid-fin-calculate-{uuid4()}")
    assert calculated.overall_readiness == "READY"
    assert calculated.total_investment_requirement == TOTAL_INVESTMENT
    assert calculated.total_model_financing == TOTAL_INVESTMENT
    assert calculated.governed_funding_assigned == TOTAL_INVESTMENT
    assert calculated.funding_gap == 0
    assert calculated.project_financial_npv is not None
    assert calculated.project_irr is not None
    calculated = financial.submit_review(
        calculated.id,
        calculated.revision_version,
        f"fid-fin-submit-{uuid4()}",
    )
    independent = EconomicFinancialModelService(
        db,
        tenant_id,
        reviewer_id,
        _ctx(db, tenant_id, reviewer_id, "economic_financial_model.complete"),
    )
    completed = independent.complete(
        calculated.id,
        calculated.revision_version,
        f"fid-fin-complete-{uuid4()}",
        reviewer_id,
    )

    return model, completed, instruments
