"""Gate 07M-EVID policy update contract and scale tests."""

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.investment_evidence_policy.service import (
    DEFAULT_POLICY,
    PROVIDER_REGISTRY,
    InvestmentEvidencePolicyService,
    gate07m_evid_policy_update,
)
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService


def _row(matrix: list[dict], evidence_type: str) -> dict:
    return next(item for item in matrix if item["evidence_type"] == evidence_type)


def test_gate07m_provider_registration_and_contextual_policy() -> None:
    service = InvestmentEvidencePolicyService(MagicMock(), 1, 1)
    assert PROVIDER_REGISTRY["BUSINESS_CASE_READINESS_PROVIDER"]["status"] == "AVAILABLE"
    assert PROVIDER_REGISTRY["ECONOMIC_FINANCIAL_READINESS_PROVIDER"]["status"] == "AVAILABLE"

    selection = service._effective_matrix(deepcopy(DEFAULT_POLICY), "PYP-INV-SELECT", [])
    selection_bc = _row(selection, "BUSINESS_CASE_READINESS")
    selection_fin = _row(selection, "ECONOMIC_FINANCIAL_READINESS")
    assert (selection_bc["classification"], selection_bc["blocking"]) == ("A", True)
    assert (selection_fin["classification"], selection_fin["blocking"]) == ("B", False)

    ffa = service._effective_matrix(deepcopy(DEFAULT_POLICY), "PYP-FFA", [])
    assert (
        _row(ffa, "BUSINESS_CASE_READINESS")["classification"],
        _row(ffa, "BUSINESS_CASE_READINESS")["blocking"],
    ) == (
        "A",
        True,
    )
    assert (
        _row(ffa, "ECONOMIC_FINANCIAL_READINESS")["classification"],
        _row(ffa, "ECONOMIC_FINANCIAL_READINESS")["blocking"],
    ) == (
        "A",
        True,
    )

    public = service._effective_matrix(
        deepcopy(DEFAULT_POLICY),
        "PYP-FFA",
        [],
        preview_project_type="PUBLIC",
        preview_governance_model="CAPITAL_OWNER",
    )
    assert _row(public, "ECONOMIC_FINANCIAL_READINESS")["required_readiness_dimensions"] == ["ECONOMIC_READINESS"]
    internal = service._effective_matrix(
        deepcopy(DEFAULT_POLICY),
        "PYP-FFA",
        [],
        preview_project_type="INTERNAL",
        preview_governance_model="CAPITAL_OWNER",
    )
    assert _row(internal, "ECONOMIC_FINANCIAL_READINESS")["classification"] == "C"
    contractor = service._effective_matrix(
        deepcopy(DEFAULT_POLICY),
        "PYP-FFA",
        [],
        preview_project_type="COMMERCIAL",
        preview_governance_model="CONTRACTOR_DELIVERY",
    )
    assert _row(contractor, "ECONOMIC_FINANCIAL_READINESS")["classification"] == "C"


def test_business_case_provider_detects_stale_fin_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    db.scalar.return_value = None
    service = InvestmentEvidencePolicyService(db, 1, 1)
    revision = SimpleNamespace(
        id=22,
        status="COMPLETED",
        revision_number=3,
        purpose="GATE_UPDATE",
        as_of_date=datetime(2026, 9, 3),
        fel_stage_code="FEL-3",
        unresolved_concerns_json=[],
        recommendation_json={"selected_alternative": "ALT-1"},
        source_snapshot_hash="a" * 64,
        content_hash="b" * 64,
        economic_financial_model_hash="c" * 64,
        material_change_status="CURRENT",
    )
    case = SimpleNamespace(
        id=9,
        business_case_number="BC-0009",
        current_revision=revision,
    )
    readiness = SimpleNamespace(status="READY", warnings=[], blockers=[], source_current=True)
    monkeypatch.setattr(
        "app.modules.investment_evidence_policy.service.BusinessCaseService.by_project",
        lambda *_args, **_kwargs: case,
    )
    monkeypatch.setattr(
        "app.modules.investment_evidence_policy.service.BusinessCaseService.readiness",
        lambda *_args, **_kwargs: readiness,
    )
    monkeypatch.setattr(
        "app.modules.investment_evidence_policy.service.EconomicFinancialModelService.by_project",
        lambda *_args, **_kwargs: SimpleNamespace(id=31),
    )
    monkeypatch.setattr(
        "app.modules.investment_evidence_policy.service.EconomicFinancialModelService.provider_evidence",
        lambda *_args, **_kwargs: SimpleNamespace(model_hash="d" * 64),
    )

    payload = service._provider_payload(
        "BUSINESS_CASE_READINESS_PROVIDER",
        {"portfolio_workspace_id": 7},
        "EACH_PROJECT",
        41,
    )
    assert payload is not None
    assert payload["readiness_status"] == "STALE"
    assert payload["source_current"] is False
    assert "BUSINESS_CASE_FIN_REFERENCE_STALE" in payload["blockers"]
    assert payload["evidence_refs"][0]["business_case_hash"] == "b" * 64


def test_effective_matrix_scales_to_one_thousand_projects() -> None:
    service = InvestmentEvidencePolicyService(MagicMock(), 1, 1)
    projects = [
        SimpleNamespace(
            id=index,
            code=f"P-{index:04d}",
            name=f"Project {index}",
            defaults_json={
                "_project": {
                    "project_type": "COMMERCIAL" if index % 2 else "PUBLIC",
                    "governance_model": "CAPITAL_OWNER",
                }
            },
        )
        for index in range(1, 1001)
    ]
    matrix = service._effective_matrix(deepcopy(DEFAULT_POLICY), "PYP-FFA", projects)
    business_cases = [item for item in matrix if item["evidence_type"] == "BUSINESS_CASE_READINESS"]
    financial_models = [item for item in matrix if item["evidence_type"] == "ECONOMIC_FINANCIAL_READINESS"]
    assert len(business_cases) == 1000
    assert len(financial_models) == 1000
    assert all(item["classification"] == "A" and item["coverage_requirement"] == 100 for item in business_cases)
    assert all(item["classification"] == "A" and item["coverage_requirement"] == 100 for item in financial_models)


def test_policy_change_diff_preserves_explicit_refresh_boundary() -> None:
    current = {
        "policy_id": 1,
        "policy_revision": 1,
        "policy_hash": "old",
        "requirements": [],
    }
    proposed = {
        "policy_id": 2,
        "policy_revision": 2,
        "policy_hash": "new",
        "requirements": deepcopy(DEFAULT_POLICY["gate_profiles"]["PYP-FFA"]["requirements"]),
    }
    changes = InvestmentGatePreparationService._policy_changes(current, proposed)
    assert changes["changed"] is True
    assert changes["requires_explicit_refresh"] is True
    assert "business-case-readiness" in changes["requirement_changes"]
    assert "economic-financial-readiness" in changes["requirement_changes"]


def test_controlled_update_preserves_unrelated_policy_rules() -> None:
    legacy = deepcopy(DEFAULT_POLICY)
    legacy["tenant_extension"] = {"keep": True}
    legacy["gate_profiles"]["PYP-FFA"]["requirements"] = [
        item
        for item in legacy["gate_profiles"]["PYP-FFA"]["requirements"]
        if item["evidence_type"] not in {"BUSINESS_CASE_READINESS", "ECONOMIC_FINANCIAL_READINESS"}
    ]
    updated = gate07m_evid_policy_update(legacy)
    assert updated["tenant_extension"] == {"keep": True}
    rows = {item["evidence_type"]: item for item in updated["gate_profiles"]["PYP-FFA"]["requirements"]}
    assert rows["BUSINESS_CASE_READINESS"]["classification"] == "A"
    assert rows["ECONOMIC_FINANCIAL_READINESS"]["classification"] == "A"
    assert len([item for item in rows if item == "BUSINESS_CASE_READINESS"]) == 1
    assert len([item for item in rows if item == "ECONOMIC_FINANCIAL_READINESS"]) == 1
