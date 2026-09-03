"""Gate 07M-FIN deterministic engine and governance contract tests."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from tests.test_business_case_gate07m import _fixture as business_case_fixture

from app.domain.models import UserAccount
from app.main import app
from app.modules.economic_financial_model.engine import (
    ENGINE_VERSION,
    FinancialFormulaError,
    benefit_cost_ratio,
    dscr,
    irr,
    llcr,
    moic,
    npv,
    payback_period,
    straight_line_amortization,
    wacc,
)
from app.modules.economic_financial_model.service import (
    DEFAULT_CONFIGURATION,
    NEXT_PROCESS,
    PROVIDER_KEY,
    READY_OUTPUT,
    EconomicFinancialModelService,
)
from app.modules.investment_evidence_policy.service import EVIDENCE_TYPES, PROVIDER_REGISTRY


def test_financial_formulas_are_decimal_deterministic() -> None:
    flows = [Decimal("-100"), Decimal("60"), Decimal("60")]
    assert npv(Decimal("0.10"), flows).quantize(Decimal("0.0001")) == Decimal("4.1322")
    assert irr(flows).quantize(Decimal("0.000001")) == Decimal("0.130662")
    assert payback_period(flows) == Decimal("1.666666666666666666666666666666667")
    assert benefit_cost_ratio(
        Decimal("0.10"), [Decimal("0"), Decimal("120")], [Decimal("100"), Decimal("0")]
    ) == Decimal("1.090909090909090909090909090909091")
    assert dscr(Decimal("150"), Decimal("100")) == Decimal("1.5")
    assert llcr([Decimal("60"), Decimal("60")], Decimal("0.10"), Decimal("100")).quantize(Decimal("0.0001")) == Decimal(
        "1.0413"
    )
    assert moic(Decimal("100"), Decimal("250")) == Decimal("2.5")
    assert wacc(Decimal("60"), Decimal("40"), Decimal("0.12"), Decimal("0.08"), Decimal("0.25")) == Decimal("0.096")
    assert straight_line_amortization(Decimal("100"), 5, 1) == [
        Decimal("0"),
        Decimal("25"),
        Decimal("25"),
        Decimal("25"),
        Decimal("25"),
    ]


def test_irr_pathologies_are_explicit_not_silently_fabricated() -> None:
    with pytest.raises(FinancialFormulaError, match="IRR_NOT_COMPUTABLE"):
        irr([Decimal("1"), Decimal("2")])
    with pytest.raises(FinancialFormulaError, match="IRR_NOT_UNIQUE"):
        irr([Decimal("-100"), Decimal("230"), Decimal("-132")])
    with pytest.raises(FinancialFormulaError, match="INVALID_DISCOUNT_RATE"):
        npv(Decimal("-1"), [Decimal("1")])


def test_release_contract_and_provider_are_available_without_policy_mutation() -> None:
    assert ENGINE_VERSION == "PPMIS-FIN-1.0"
    assert READY_OUTPUT == "READY_FOR_GOVERNED_ECONOMIC_FINANCIAL_EVIDENCE"
    assert NEXT_PROCESS == "UPDATE_GATE07J_EVID_FOR_BUSINESS_CASE_AND_ECONOMIC_FINANCIAL_READINESS"
    assert PROVIDER_KEY == "ECONOMIC_FINANCIAL_READINESS_PROVIDER"
    assert "ECONOMIC_FINANCIAL_READINESS" in EVIDENCE_TYPES
    provider = PROVIDER_REGISTRY[PROVIDER_KEY]
    assert provider["status"] == "AVAILABLE"
    assert provider["supports_project_scope"] is True


def test_configuration_requires_all_model_types_and_four_eyes() -> None:
    assert EconomicFinancialModelService._configuration_issues(DEFAULT_CONFIGURATION) == []
    invalid = dict(DEFAULT_CONFIGURATION)
    invalid["applicable_model_types"] = ["COMMERCIAL_PROJECT"]
    invalid["separation_of_duties"] = {"reviewer_must_differ_from_preparer": False}
    assert set(EconomicFinancialModelService._configuration_issues(invalid)) == {
        "ALL_GOVERNED_MODEL_TYPES_REQUIRED",
        "PREPARER_REVIEWER_SOD_REQUIRED",
    }


def test_model_input_validation_rejects_invalid_basis_horizon_and_type() -> None:
    valid = {
        "model_type": "COMMERCIAL_PROJECT",
        "cash_flow_basis": "NOMINAL",
        "periodicity": "ANNUAL",
        "model_start_date": __import__("datetime").date(2026, 1, 1),
        "model_end_date": __import__("datetime").date(2030, 12, 31),
        "construction_start": __import__("datetime").date(2026, 1, 1),
    }
    EconomicFinancialModelService._validate_version_values(valid)
    for field, value, code in (
        ("model_type", "TREASURY", "INVALID_MODEL_TYPE"),
        ("cash_flow_basis", "MIXED", "INVALID_CASH_FLOW_BASIS"),
        ("periodicity", "DAILY", "INVALID_PERIODICITY"),
    ):
        candidate = valid | {field: value}
        with pytest.raises(HTTPException) as captured:
            EconomicFinancialModelService._validate_version_values(candidate)
        assert captured.value.detail["code"] == code


def test_commercial_model_lifecycle_readiness_provider_and_immutability() -> None:
    with TestClient(app):
        pass
    db, actor, project, proposal, business_service = business_case_fixture()
    try:
        reviewer = UserAccount(
            tenant_id=actor.tenant_id,
            email=f"gate07m-fin-reviewer-{uuid4().hex[:10]}@example.test",
            full_name="Independent Financial Reviewer",
            title="Financial Model Reviewer",
            status="active",
        )
        db.add(reviewer)
        db.commit()
        case = business_service.create(
            project.id,
            proposal.id,
            None,
            None,
            f"gate07m-fin-case-{uuid4()}",
        )
        assert case.current_revision is not None
        submitted_case = business_service.submit_review(
            case.current_revision.id,
            case.current_revision.revision_version,
            f"gate07m-fin-case-submit-{uuid4()}",
        )
        completed_case = business_service.complete_revision(
            submitted_case.id,
            submitted_case.revision_version,
            f"gate07m-fin-case-complete-{uuid4()}",
            reviewer.id,
        )
        assert completed_case.readiness_status == "READY"

        service = EconomicFinancialModelService(db, actor.tenant_id, actor.id)
        created = service.create(
            {
                "project_workspace_id": project.id,
                "business_case_id": case.id,
                "model_type": "COMMERCIAL_PROJECT",
                "base_currency": "USD",
                "cash_flow_basis": "NOMINAL",
                "periodicity": "ANNUAL",
                "model_start_date": date(2026, 1, 1),
                "model_end_date": date(2027, 12, 31),
                "construction_start": date(2026, 1, 1),
                "operations_start": date(2027, 1, 1),
                "operations_end": date(2027, 12, 31),
                "terminal_date": date(2027, 12, 31),
                "idempotency_key": f"gate07m-fin-create-{uuid4()}",
            }
        )
        version = created.current_version
        assert version is not None
        service.upsert_assumption(
            version.id,
            version.revision_version,
            {
                "assumption_key": "project_discount_rate",
                "name": "Project discount rate",
                "category": "DISCOUNT_RATE",
                "numeric_value": Decimal("0.10"),
                "text_value": None,
                "unit": "RATE",
                "periodicity": "ANNUAL",
                "effective_from": None,
                "effective_to": None,
                "source": "GOVERNED_POLICY",
                "source_reference": "test-policy",
                "rationale": "Deterministic acceptance case",
                "is_override": False,
            },
        )
        version = service._version(version.id)
        for index, values in enumerate(
            (
                {"opex": Decimal("100"), "revenue": Decimal("0")},
                {"opex": Decimal("0"), "revenue": Decimal("120")},
            )
        ):
            service.upsert_period(
                version.id,
                version.revision_version,
                {
                    "period_index": index,
                    "period_label": f"FY{2026 + index}",
                    "period_start": date(2026 + index, 1, 1),
                    "period_end": date(2026 + index, 12, 31),
                    "currency": "USD",
                    "revenue": values["revenue"],
                    "economic_benefits": Decimal("0"),
                    "opex": values["opex"],
                    "taxes": Decimal("0"),
                    "working_capital_change": Decimal("0"),
                    "capex": Decimal("0"),
                    "debt_drawdown": Decimal("0"),
                    "interest": Decimal("0"),
                    "principal": Decimal("0"),
                    "equity_contribution": Decimal("0"),
                    "distribution": Decimal("0"),
                    "source_reference": "test-cash-flow",
                    "source_hash": "f" * 64,
                },
            )
            version = service._version(version.id)
        calculated = service.calculate(
            version.id,
            version.revision_version,
            f"gate07m-fin-calculate-{uuid4()}",
        )
        assert calculated.overall_readiness == "READY"
        assert calculated.project_financial_npv is not None
        assert calculated.project_irr is not None
        assert len(service.cash_flows(version.id)) == 2
        submitted = service.submit_review(
            calculated.id,
            calculated.revision_version,
            f"gate07m-fin-submit-{uuid4()}",
        )
        completed = service.complete(
            submitted.id,
            submitted.revision_version,
            f"gate07m-fin-complete-{uuid4()}",
            reviewer.id,
        )
        assert completed.status == "COMPLETED"
        assert service.readiness(created.id).final_output == READY_OUTPUT
        provider = service.provider_evidence(created.id)
        assert provider.can_supply_investment_gate_evidence is True
        assert provider.model_hash == completed.model_hash
        with pytest.raises(HTTPException) as captured:
            service.update_version(completed.id, completed.revision_version, {"base_currency": "COP"})
        assert captured.value.detail["code"] == "DRAFT_FIN_MODEL_VERSION_REQUIRED"
    finally:
        db.rollback()
        db.close()
