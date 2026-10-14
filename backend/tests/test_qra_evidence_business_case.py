"""Five Case projection consumes frozen QRA references, never a simulation."""

from copy import deepcopy
from unittest.mock import MagicMock

from tests.test_business_case_gate07m_bc_5c import _case, _ffa_references, _revision

from app.modules.business_case.service import BusinessCaseService, _case_sources
from app.modules.investment_evidence_policy.service import InvestmentEvidencePolicyService


def _summary(kind="cost"):
    return {
        "provider_key": "QRA_RESULT_PROVIDER",
        "run_id": 501 if kind == "cost" else 502,
        "run_number": "QRR-000501" if kind == "cost" else "QRR-000502",
        "analysis_type": "COST_QRA" if kind == "cost" else "SCHEDULE_QRA",
        "accepted_status": "ACCEPTED",
        "acceptance_hash": "a" * 64,
        "run_hash": "r" * 64,
        "model_hash": "m" * 64,
        "engine_version": "wave4-qra-v1",
        "source_current": True,
        "readiness": "READY_WITH_WARNINGS",
        "analytical_readiness": "READY_WITH_WARNINGS",
        "convergence": {"status": "CONVERGED"},
        "tail_convergence_certified": False,
        "as_of": "2026-10-12T12:00:00",
        "selected_percentiles": [{"percentile": 80, "value": 1234}],
        "target_probabilities": {},
        "result_semantics": {"currency": "USD"} if kind == "cost" else {"unit": "HOURS"},
        "warnings": ["MEAN_CONVERGENCE_ONLY_NO_TAIL_CERTIFICATION"],
        "blockers": [],
    }


def _qualified_refs():
    refs, hashes = _ffa_references()
    refs["_qra_evidence"] = {
        "schema_version": "1.0",
        "policy_ref": {"policy_id": 91, "policy_revision": 2, "policy_hash": "p" * 64},
        "requirements": [
            {"source": "cost_qra_result", "classification": "A", "blocking": True},
            {"source": "schedule_qra_result", "classification": "A", "blocking": True},
        ],
    }
    for kind in ("cost", "schedule"):
        source = f"{kind}_qra_result"
        refs[source] = {**_summary(kind), "id": _summary(kind)["run_id"], "status": "AVAILABLE"}
        hashes[source] = "a" * 64
    return refs, hashes


def test_new_five_case_maps_cost_and_schedule_without_modifying_deterministic_fin():
    service = BusinessCaseService(MagicMock(), 1, 1)
    refs, hashes = _qualified_refs()
    revision = _revision(refs, hashes)
    before = deepcopy(revision.source_references_json)
    service._source_bundle = MagicMock(side_effect=AssertionError("historical read fetched current source"))
    contract = service._five_case_contract(_case(), revision)
    assert revision.source_references_json == before
    assert contract["five_case_readiness_json"]["overall_business_case_readiness"] == "READY"
    for case_key, source in (
        ("economic_case", "cost_qra_result"),
        ("financial_case", "cost_qra_result"),
        ("management_case", "schedule_qra_result"),
    ):
        row = next(
            r for r in contract["source_evidence_matrix_json"] if r["case"] == case_key and r["source_key"] == source
        )
        assert row["qra_summary"]["accepted_status"] == "ACCEPTED"
        assert row["qra_summary"]["tail_convergence_certified"] is False
        assert row["blocking"] is True
    assert (
        contract["five_case_json"]["financial_case"]["source_references"]["economic_financial_model"]
        == refs["economic_financial_model"]
    )
    service._source_bundle.assert_not_called()


def test_historical_five_case_hash_and_rows_are_not_reinterpreted_from_new_qra():
    service = BusinessCaseService(MagicMock(), 1, 1)
    refs, hashes = _ffa_references()
    revision = _revision(refs, hashes)
    before = service._five_case_contract(_case(), revision)
    service._qra_source_bundle = MagicMock(side_effect=AssertionError("historical QRA lookup"))
    after = service._five_case_contract(_case(), revision)
    assert before == after
    assert not any("qra_result" in row["source_key"] for row in after["source_evidence_matrix_json"])
    assert "cost_qra_result" not in _case_sources("financial_case", refs)


def test_required_qra_missing_or_stale_blocks_new_case_but_does_not_patch_revision():
    service = BusinessCaseService(MagicMock(), 1, 1)
    refs, hashes = _qualified_refs()
    refs["cost_qra_result"]["source_current"] = False
    refs["cost_qra_result"]["blockers"] = ["SOURCE_STALE"]
    revision = _revision(refs, hashes)
    result = service._five_case_contract(_case(), revision)
    assert result["five_case_readiness_json"]["financial_case"] == "STALE"
    assert "FINANCIAL_CASE:SOURCE_STALE:cost_qra_result" in result["blockers"]
    assert revision.source_references_json["cost_qra_result"]["run_id"] == 501
    refs.pop("schedule_qra_result")
    hashes.pop("schedule_qra_result")
    missing = service._five_case_contract(_case(), _revision(refs, hashes))
    assert "MANAGEMENT_CASE:REQUIRED_SOURCE_MISSING:schedule_qra_result" in missing["blockers"]


def test_qra_source_bundle_uses_same_policy_provider_and_omits_optional_missing(monkeypatch):
    policy_ref = {"policy_id": 91, "policy_revision": 2, "policy_hash": "p" * 64}
    requirement = {
        "evidence_type": "COST_QRA_RESULT",
        "classification": "A",
        "blocking": True,
        "qra_applicability": {"outcome": "REQUIRED", "engine_capability_fit": "NOT_EVALUATED"},
        "qra_policy": {"analysis_type": "COST_QRA"},
    }
    resolver = MagicMock()
    resolver.qra_requirements_for_project.return_value = {"policy_ref": policy_ref, "requirements": [requirement]}
    summary = _summary()
    resolver.resolve_governed_payload.return_value = (
        {
            "qra_summary": summary,
            "qra_applicability": {"outcome": "REQUIRED", "engine_capability_fit": "SUPPORTED_WITH_LIMITATIONS"},
            "source_current": True,
            "evidence_hash": "a" * 64,
            "warnings": summary["warnings"],
            "blockers": [],
        },
        None,
    )
    monkeypatch.setattr(
        InvestmentEvidencePolicyService, "qra_requirements_for_project", resolver.qra_requirements_for_project
    )
    monkeypatch.setattr(InvestmentEvidencePolicyService, "resolve_governed_payload", resolver.resolve_governed_payload)
    service = BusinessCaseService(MagicMock(), 1, 1)
    refs, hashes = service._qra_source_bundle(701)
    assert refs["cost_qra_result"]["run_id"] == 501
    assert refs["cost_qra_result"]["policy_ref"] == policy_ref
    assert refs["cost_qra_result"]["classification"] == "A"
    assert refs["cost_qra_result"]["qra_applicability"] == {
        "outcome": "REQUIRED",
        "engine_capability_fit": "SUPPORTED_WITH_LIMITATIONS",
    }
    refs["cost_qra_result"]["qra_applicability"]["outcome"] = "EDITED_COPY"
    assert resolver.resolve_governed_payload.return_value[0]["qra_applicability"]["outcome"] == "REQUIRED"
    assert hashes["cost_qra_result"] == "a" * 64
    assert refs["cost_qra_result"]["not_probabilistic_fin"]
    resolver.resolve_governed_payload.assert_called_once_with(requirement, {}, 701)
    service._qra_source_bundle(701, portfolio_id=901)
    resolver.qra_requirements_for_project.assert_called_with(701, portfolio_id=901)
    resolver.resolve_governed_payload.return_value[0].pop("qra_applicability")
    fallback, _ = service._qra_source_bundle(701)
    assert fallback["cost_qra_result"]["qra_applicability"] == requirement["qra_applicability"]
    requirement.update(classification="B", blocking=False)
    resolver.resolve_governed_payload.return_value = (None, "QRA_ACCEPTED_RESULT_REQUIRED")
    refs, hashes = service._qra_source_bundle(701)
    assert "cost_qra_result" not in refs and "cost_qra_result" not in hashes
    assert refs["_qra_evidence"]["requirements"][0]["resolution_error"] == "QRA_ACCEPTED_RESULT_REQUIRED"


def test_no_qra_policy_or_class_c_leaves_legacy_bundle_untouched(monkeypatch):
    monkeypatch.setattr(
        InvestmentEvidencePolicyService,
        "qra_requirements_for_project",
        lambda *args: {"policy_ref": {}, "requirements": [{"classification": "C"}]},
    )
    assert BusinessCaseService(MagicMock(), 1, 1)._qra_source_bundle(701) == ({}, {})
