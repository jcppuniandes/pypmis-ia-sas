"""Focused Gate 07J-EVID-2 decision-criteria acceptance coverage."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, Tenant, UserAccount
from app.main import app
from app.modules.investment_decision.service import InvestmentDecisionService
from app.modules.investment_evidence_policy.decision_criteria import (
    CONTROLLED_OPERATORS,
    DECISION_CRITERION_TYPES,
    _operator_satisfied,
    decision_criterion_policy,
    evaluate_criteria,
    starter_criteria,
    validate_criterion_policy,
)
from app.modules.investment_evidence_policy.service import (
    CONFIGURATION_KIND,
    DEFAULT_POLICY,
    EVIDENCE_TYPES,
    InvestmentEvidencePolicyService,
    _hash,
)
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def test_taxonomy_is_separate_from_evidence_class_and_operators_are_allowlisted() -> None:
    policy = decision_criterion_policy(deepcopy(DEFAULT_POLICY))

    assert tuple(policy["criterion_types"]) == DECISION_CRITERION_TYPES
    assert tuple(policy["controlled_operators"]) == CONTROLLED_OPERATORS
    assert set(DECISION_CRITERION_TYPES).isdisjoint({"A", "B", "C"})
    assert policy["unsafe_expression_execution"] is False
    assert (
        validate_criterion_policy(
            {**deepcopy(DEFAULT_POLICY), "decision_criterion_policy": policy}, set(EVIDENCE_TYPES)
        )
        == []
    )

    unsafe = deepcopy(DEFAULT_POLICY)
    unsafe["decision_criterion_policy"] = deepcopy(policy)
    unsafe["decision_criterion_policy"]["unsafe_expression_execution"] = True
    unsafe["decision_criterion_policy"]["criteria_by_profile"]["PYP-FFA"][0]["operator"] = (
        "__import__('os').system('whoami')"
    )
    issues = validate_criterion_policy(unsafe, set(EVIDENCE_TYPES))
    assert "UNSAFE_EXPRESSION_EXECUTION_NOT_ALLOWED" in issues
    assert any(item.startswith("INVALID_DECISION_CRITERION_OPERATOR:PYP-FFA:") for item in issues)
    assert _operator_satisfied("__import__('os').system('whoami')", 1, 1) is False


def test_select_is_proportional_while_ffa_is_strict_and_does_not_double_rank() -> None:
    select_rows = starter_criteria("PYP-INV-SELECT")
    ffa_rows = starter_criteria("PYP-FFA")

    assert len(select_rows) < len(ffa_rows)
    assert not any(item["criterion_code"] == "FIN-READINESS" for item in select_rows)
    assert any(
        item["criterion_code"] == "FIN-READINESS"
        and item["criterion_type"] == "MUST_MEET"
        and item["blocking"]
        and item["required"]
        for item in ffa_rows
    )
    prioritization = [item for item in ffa_rows if item["criterion_type"] == "PRIORITIZATION"]
    assert prioritization
    assert all(item["scope"] == "PORTFOLIO" and item["weight"] is None for item in prioritization)


def test_evaluator_uses_governed_values_and_keeps_quality_separate_from_readiness() -> None:
    criterion = next(item for item in starter_criteria("PYP-FFA") if item["criterion_code"] == "FIN-READINESS")
    evidence = [
        {
            "evidence_type": "ECONOMIC_FINANCIAL_READINESS",
            "scope_id": 42,
            "source_record_id": 9001,
            "source_hash": "a" * 64,
            "source_current": True,
            "status": "VALID",
            "readiness_status": "READY",
            "evidence_quality": "PRELIMINARY",
            "quality_origin": "SOURCE_PROVIDER",
            "source_payload": {"project_financial_npv": "1250000"},
        }
    ]

    result = evaluate_criteria(
        [criterion],
        evidence,
        {},
        [
            {
                "project_workspace_id": 42,
                "project_type": "COMMERCIAL",
                "governance_model": "CAPITAL_OWNER",
            }
        ],
        policy_revision=7,
        policy_hash="b" * 64,
        evaluated_at="2026-09-18T12:00:00Z",
    )[0]

    assert result["result"] == "SATISFIED"
    assert result["source_reference"]["quality"] == "PRELIMINARY"
    assert result["source_reference"]["quality_origin"] == "SOURCE_PROVIDER"
    assert result["policy_revision"] == 7


def test_legacy_published_policy_is_not_silently_reinterpreted(monkeypatch: pytest.MonkeyPatch) -> None:
    legacy = deepcopy(DEFAULT_POLICY)
    legacy.pop("decision_criterion_policy", None)
    record = SimpleNamespace(
        id=73,
        revision=4,
        content_hash=_hash(legacy),
        content_json=legacy,
    )
    project = SimpleNamespace(id=101)
    service = InvestmentEvidencePolicyService(None, tenant_id=1, actor_id=1)
    monkeypatch.setattr(service, "_portfolio", lambda _portfolio_id: SimpleNamespace(id=9))
    monkeypatch.setattr(service, "_effective_configuration", lambda _workspace: record)
    monkeypatch.setattr(service, "_projects", lambda _ids: [project])
    monkeypatch.setattr(service, "_effective_matrix", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(service, "providers", lambda: [])
    monkeypatch.setattr(
        service,
        "_project_context",
        lambda _project: {"project_workspace_id": project.id},
    )

    snapshot = service.published_snapshot(9, "PYP-INV-SELECT", [project.id])

    assert snapshot is not None
    assert snapshot["decision_criterion_policy"] == {}
    assert "decision_criterion_policy" not in legacy


def test_dedicated_evid2_clone_is_idempotent_and_preserves_source_policy() -> None:
    with SessionLocal() as db:
        tenant = db.scalar(select(Tenant).order_by(Tenant.id))
        assert tenant is not None
        actor = db.scalar(select(UserAccount).where(UserAccount.tenant_id == tenant.id).order_by(UserAccount.id))
        assert actor is not None
        code = f"gate07j-evid2-{uuid4().hex[:12]}"
        content = deepcopy(DEFAULT_POLICY)
        content.pop("decision_criterion_policy", None)
        source = AdminConfiguration(
            tenant_id=tenant.id,
            kind=CONFIGURATION_KIND,
            code=code,
            name="Legacy evidence policy",
            description="Source policy retained during the additive EVID-2 clone.",
            status="published",
            revision=1,
            version=1,
            content_json=content,
            content_hash=_hash(content),
            published_at=utc_now(),
            created_by_user_id=actor.id,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        service = InvestmentEvidencePolicyService(db, tenant.id, actor.id)

        first = service.clone_gate07j_evid2_configuration(source.id, source.version)
        try:
            duplicate = service.clone_gate07j_evid2_configuration(source.id, source.version)

            assert duplicate.id == first.id
            assert first.status == "draft"
            assert first.content_json["policy_update"] == "GATE07J_EVID_2"
            assert first.content_json["_gate07j_evid2"]["source_policy_hash"] == source.content_hash
            assert first.content_json["decision_criterion_policy"]
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(AdminConfiguration)
                    .where(
                        AdminConfiguration.tenant_id == tenant.id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                        AdminConfiguration.code == code,
                        AdminConfiguration.status == "draft",
                    )
                )
                == 1
            )
        finally:
            # The module test DB is shared. Do not let this isolated published
            # source become the effective policy for later Gate 07J scenarios.
            source.status = "superseded"
            db.commit()


def test_dedicated_evid2_clone_requires_a_published_source() -> None:
    with SessionLocal() as db:
        tenant = db.scalar(select(Tenant).order_by(Tenant.id))
        assert tenant is not None
        actor = db.scalar(select(UserAccount).where(UserAccount.tenant_id == tenant.id).order_by(UserAccount.id))
        assert actor is not None
        content = deepcopy(DEFAULT_POLICY)
        source = AdminConfiguration(
            tenant_id=tenant.id,
            kind=CONFIGURATION_KIND,
            code=f"gate07j-evid2-draft-{uuid4().hex[:12]}",
            name="Mutable draft source",
            description="A mutable draft must not become an EVID-2 baseline.",
            status="draft",
            revision=1,
            version=1,
            content_json=content,
            content_hash=_hash(content),
            created_by_user_id=actor.id,
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        with pytest.raises(HTTPException) as raised:
            InvestmentEvidencePolicyService(db, tenant.id, actor.id).clone_gate07j_evid2_configuration(
                source.id, source.version
            )

        assert raised.value.status_code == 409
        assert raised.value.detail["code"] == "PUBLISHED_POLICY_REQUIRED"


def test_ffa_cross_source_mismatch_blocks_while_select_only_warns() -> None:
    rows = [
        {
            "evidence_type": "BUSINESS_CASE_READINESS",
            "scope_id": 14,
            "source_hash": "b" * 64,
            "source_payload": {
                "source_hashes": {
                    "economic_financial_model": "1" * 64,
                    "benefits": "2" * 64,
                }
            },
        },
        {
            "evidence_type": "ECONOMIC_FINANCIAL_READINESS",
            "scope_id": 14,
            "source_hash": "9" * 64,
            "source_payload": {},
        },
        {
            "evidence_type": "BENEFITS_PLAN_READINESS",
            "scope_id": 14,
            "source_hash": "2" * 64,
            "source_payload": {},
        },
    ]

    consistency = InvestmentGatePreparationService._cross_source_consistency(rows)
    assert any(
        item["source_key"] == "economic_financial_model" and item["status"] == "MISMATCH" for item in consistency
    )
    assert any(item["source_key"] == "benefits" and item["status"] == "CONSISTENT" for item in consistency)
    ffa_blockers, ffa_warnings = InvestmentGatePreparationService._cross_source_findings("PYP-FFA", consistency)
    select_blockers, select_warnings = InvestmentGatePreparationService._cross_source_findings(
        "PYP-INV-SELECT", consistency
    )
    assert ffa_blockers == ["CROSS_SOURCE_MISMATCH:economic_financial_model"]
    assert ffa_warnings == []
    assert select_blockers == []
    assert select_warnings == ["CROSS_SOURCE_REVIEW:economic_financial_model"]


def test_gate07k_go_guard_rejects_unsatisfied_required_criteria() -> None:
    package = {
        "preparation": {
            "evidence_readiness_status": "READY",
            "decision_package_status": "READY_FOR_INVESTMENT_DECISION",
        },
        "criterion_evaluations": [
            {
                "criterion_code": "FIN-READINESS",
                "criterion_type": "MUST_MEET",
                "required": True,
                "blocking": True,
                "result": "NOT_SATISFIED",
            },
            {
                "criterion_code": "PORTFOLIO-RECOMMENDATION-CONTEXT",
                "criterion_type": "PRIORITIZATION",
                "required": True,
                "blocking": False,
                "result": "NOT_EVALUABLE",
            },
        ],
    }

    blockers = InvestmentDecisionService._criterion_guardrail_blockers(package)

    assert blockers == ["MUST_MEET:FIN-READINESS:NOT_SATISFIED"]
    assert (
        InvestmentDecisionService._criterion_guardrail_blockers(
            {
                **package,
                "criterion_evaluations": [
                    {
                        "criterion_code": "FIN-READINESS",
                        "criterion_type": "MUST_MEET",
                        "required": True,
                        "blocking": True,
                        "result": "SATISFIED",
                    }
                ],
            }
        )
        == []
    )
