"""Focused Gate07M-BC-5C tests for the additive Five Case contract."""

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.business_case.service import DEFAULT_CONFIGURATION, BusinessCaseService


def _case() -> SimpleNamespace:
    return SimpleNamespace(
        id=71,
        project_workspace_id=701,
        source_project_proposal_id=41,
        configuration_id=17,
        configuration_hash="c" * 64,
    )


def _references(*, governance_model: str = "CAPITAL_OWNER") -> dict:
    policy = deepcopy(DEFAULT_CONFIGURATION["five_case"])
    return {
        "_five_case": {
            "schema_version": "1.0",
            "integration_layer": True,
            "source_authority_preserved": True,
            "configuration_id": 17,
            "configuration_hash": "c" * 64,
            "policy": policy,
            "gate_context": {
                "project_workspace_id": 701,
                "project_type": "CAPITAL",
                "governance_model": governance_model,
                "gate_profile": "PYP-INV-SELECT",
                "fel_stage": "FEL-2",
                "policy_stage": "FEL-2",
                "revision_purpose": "FEL_2_UPDATE",
                "as_of_date": "2026-09-17T12:00:00",
            },
        },
        "proposal": {"id": 41, "status": "READY_FOR_STRATEGIC_GATE", "source_current": True},
        "business_analysis": {
            "id": 51,
            "status": "COMPLETED",
            "readiness": "READY",
            "recommended_option_id": "ALT-1",
            "recommended_option_current": True,
            "source_current": True,
        },
        "benefits": {
            "id": 61,
            "version": 2,
            "status": "COMPLETED",
            "readiness": "READY",
            "source_current": True,
        },
        "commercial_strategy": {
            "id": 62,
            "version": 3,
            "status": "COMPLETED",
            "readiness": "READY",
            "source_current": True,
            "procurement_approach": "COMPETITIVE",
            "contracting_model": "EPC",
        },
        "fel": {"id": 63, "stage": "FEL-2", "readiness": "READY", "source_current": True},
    }


def _hashes() -> dict[str, str]:
    return {
        "proposal": "1" * 64,
        "business_analysis": "2" * 64,
        "benefits": "3" * 64,
        "commercial_strategy": "4" * 64,
        "fel": "5" * 64,
    }


def _ffa_references() -> tuple[dict, dict[str, str]]:
    refs = _references()
    refs["_five_case"]["gate_context"].update(
        {"fel_stage": "FFA", "policy_stage": "FFA", "revision_purpose": "FFA_UPDATE"}
    )
    refs.update(
        {
            "budget": {"id": 64, "status": "FROZEN", "readiness": "READY", "source_current": True},
            "funding": {"id": 65, "status": "READY", "readiness": "READY", "source_current": True},
            "economic_financial_model": {
                "id": 66,
                "status": "COMPLETED",
                "readiness": "READY",
                "source_current": True,
            },
            "risk": {"id": 67, "status": "READY", "readiness": "READY", "source_current": True},
            "resource": {"id": 68, "status": "FROZEN", "readiness": "READY", "source_current": True},
            "permit": {"id": 69, "status": "READY", "readiness": "READY", "source_current": True},
        }
    )
    hashes = _hashes()
    for offset, key in enumerate(
        ("budget", "funding", "economic_financial_model", "risk", "resource", "permit"), start=6
    ):
        hashes[key] = str(offset) * 64
    return refs, hashes


def _revision(references: dict | None = None, hashes: dict[str, str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=81,
        business_case_id=71,
        source_references_json=deepcopy(references if references is not None else _references()),
        source_hashes_json=deepcopy(hashes if hashes is not None else _hashes()),
        source_snapshot_hash="6" * 64,
        content_hash="7" * 64,
        purpose="FEL_2_UPDATE",
        as_of_date=datetime(2026, 9, 17, 12, 0, 0),
        fel_stage_code="FEL-2",
        title="Governed investment",
        executive_summary="Governed summary",
        business_need="Governed need",
        strategic_alignment_json=[{"code": "STRAT-1"}],
        objectives_json=[{"description": "Deliver value"}],
        scope_json={"in_scope": "Investment"},
        alternatives_json=[{"id": "ALT-1"}],
        benefits_json=[{"description": "Benefit"}],
        assumptions_json=[],
        constraints_json=[],
        delivery_json={"approach": "stage gated"},
        unresolved_concerns_json=[],
        recommendation_json={"selected_alternative": "ALT-1"},
    )


def test_historical_five_case_is_derived_only_from_frozen_revision_data() -> None:
    service = BusinessCaseService(MagicMock(), 1, 1)
    service._source_bundle = MagicMock(side_effect=AssertionError("historical read queried live sources"))

    first = service._five_case_contract(_case(), _revision())
    second = service._five_case_contract(_case(), _revision())

    assert first == second
    assert first["legacy_layout"] is False
    assert first["five_case_readiness_json"]["overall_business_case_readiness"] == "READY"
    assert first["five_case_json"]["commercial_case"]["source_references"]["commercial_strategy"]["id"] == 62
    assert first["five_case_json"]["strategic_case"]["source_references"]["benefits"]["id"] == 61
    service._source_bundle.assert_not_called()


def test_rows_without_marker_stay_legacy_and_non_capital_is_not_strict_without_override() -> None:
    service = BusinessCaseService(MagicMock(), 1, 1)
    legacy = _revision(references={"proposal": {"id": 41}}, hashes={"proposal": "1" * 64})
    legacy_contract = service._five_case_contract(_case(), legacy)
    assert legacy_contract["legacy_layout"] is True
    assert legacy_contract["five_case_json"] == {}

    direct_refs = _references(governance_model="DIRECT_INTERNAL")
    direct = service._five_case_contract(_case(), _revision(direct_refs, _hashes()))
    assert direct["five_case_readiness_json"]["overall_business_case_readiness"] == "NOT_APPLICABLE"
    assert direct["blockers"] == []

    direct_refs["_five_case"]["policy"]["enabled_governance_models"].append("DIRECT_INTERNAL")
    explicitly_enabled = service._five_case_contract(_case(), _revision(direct_refs, _hashes()))
    assert explicitly_enabled["five_case_readiness_json"]["overall_business_case_readiness"] == "READY"


def test_refresh_preview_compares_union_groups_removed_sources_and_reports_readiness_delta() -> None:
    service = BusinessCaseService(MagicMock(), 1, 1)
    case = _case()
    current = _revision()
    new_refs = _references()
    new_refs.pop("commercial_strategy")
    new_refs.pop("_five_case")
    new_hashes = _hashes()
    new_hashes.pop("commercial_strategy")
    service._case = MagicMock(return_value=case)
    service._current_revision = MagicMock(return_value=current)
    service._source_bundle = MagicMock(return_value=(new_refs, new_hashes))
    service._snapshots = MagicMock(return_value=[])

    preview = service.refresh_preview(case.id, audit=False)

    removed = next(item for item in preview.source_changes if item["source"] == "commercial_strategy")
    assert removed["change_type"] == "REMOVED"
    assert removed["to"] is None
    assert preview.source_changes_by_case["commercial_case"] == [removed]
    assert preview.source_changes_by_case["management_case"] == [removed]
    assert preview.case_readiness_delta["commercial_case"] == {"from": "READY", "to": "BLOCKED"}
    assert "COMMERCIAL_CASE:REQUIRED_SOURCE_MISSING:commercial_strategy" in preview.new_blockers
    assert preview.five_case_delta["changed"] is True


@pytest.mark.parametrize(
    ("source", "mutation", "expected_case", "expected_status"),
    [
        ("benefits", {"source_current": False}, "strategic_case", "STALE"),
        ("commercial_strategy", {"readiness": "BLOCKED"}, "commercial_case", "BLOCKED"),
        (
            "economic_financial_model",
            {"readiness": "STALE", "source_current": False},
            "financial_case",
            "STALE",
        ),
        ("fel", {"readiness": "STALE", "source_current": False}, "management_case", "STALE"),
        (
            "business_analysis",
            {"recommended_option_current": False, "source_current": False},
            "economic_case",
            "STALE",
        ),
    ],
)
def test_required_five_case_source_failures_are_backend_owned(
    source: str,
    mutation: dict,
    expected_case: str,
    expected_status: str,
) -> None:
    service = BusinessCaseService(MagicMock(), 1, 1)
    refs, hashes = _ffa_references()
    refs[source].update(mutation)

    result = service._five_case_contract(_case(), _revision(refs, hashes))

    assert result["five_case_readiness_json"][expected_case] == expected_status
    assert result["five_case_readiness_json"]["overall_business_case_readiness"] == expected_status
    assert result["blockers"]


def test_missing_required_benefits_blocks_ffa_without_fabricating_source_evidence() -> None:
    service = BusinessCaseService(MagicMock(), 1, 1)
    refs, hashes = _ffa_references()
    refs.pop("benefits")
    hashes.pop("benefits")

    result = service._five_case_contract(_case(), _revision(refs, hashes))

    assert result["five_case_readiness_json"]["strategic_case"] == "BLOCKED"
    assert result["five_case_readiness_json"]["overall_business_case_readiness"] == "BLOCKED"
    strategic_rows = [
        item
        for item in result["source_evidence_matrix_json"]
        if item["case"] == "strategic_case" and item["source_key"] == "benefits"
    ]
    assert strategic_rows == [
        {
            "case": "strategic_case",
            "source_key": "benefits",
            "source_module": "STRATEGIC_BENEFITS_PLAN",
            "source_id": None,
            "version": None,
            "hash": None,
            "readiness": "NOT_AVAILABLE",
            "source_current": False,
            "as_of_date": None,
            "blocking": True,
            "available": False,
            "view_source": {"module": "STRATEGIC_BENEFITS_PLAN", "source_id": None},
        }
    ]
