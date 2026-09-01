"""Gate 07J-EVID acceptance tests for A/B/C policy semantics."""

from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.test_investment_gate_preparation_gate07j import _preparation, _profile, _reviewer, _source

from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, SecurityEvent
from app.main import app
from app.modules.investment_evidence_policy.service import (
    CONFIGURATION_KIND,
    DEFAULT_POLICY,
    InvestmentEvidencePolicyService,
)
from app.modules.investment_gate_preparation.schemas import EvidenceValidationIn, ManualEvidenceIn
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


@pytest.fixture(autouse=True)
def _isolate_published_policy():
    """Do not let a published test policy reinterpret unrelated Gate 07J tests."""

    def deactivate() -> None:
        with SessionLocal() as db:
            for record in db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    AdminConfiguration.status == "published",
                )
            ).all():
                record.status = "superseded"
                record.version += 1
            db.commit()

    deactivate()
    yield
    deactivate()


def _policy(service: InvestmentEvidencePolicyService) -> AdminConfiguration:
    service.ensure_seed()
    records = service.configurations()
    draft = next((item for item in records if item.status == "draft"), None)
    if draft is not None:
        return draft
    source = records[0]
    return service.clone_configuration(source.id, source.version)


def test_contextual_matrix_has_no_silent_fallback_and_mixed_project_types() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        first_context = dict(dict(projects[0].defaults_json or {}).get("_project", {}))
        first_context.update(project_type="MINING", governance_model="CAPITAL_OWNER")
        projects[0].defaults_json = {**dict(projects[0].defaults_json or {}), "_project": first_context}
        second_context = dict(dict(projects[1].defaults_json or {}).get("_project", {}))
        second_context.update(project_type="BUILDING", governance_model="CAPITAL_OWNER")
        projects[1].defaults_json = {**dict(projects[1].defaults_json or {}), "_project": second_context}
        db.commit()

        service = InvestmentEvidencePolicyService(db, tenant_id, actor_id)
        record = _policy(service)
        preview = service.preview(
            portfolio_id=portfolio.id,
            gate_profile_code="PYP-FFA",
            project_ids=[],
            configuration_id=record.id,
            content_override=record.content_json,
        )
        risk = next(item for item in preview.effective_matrix if item["evidence_type"] == "RISK_READINESS")
        mining_permit = next(
            item
            for item in preview.effective_matrix
            if item["evidence_type"] == "PERMIT_READINESS" and item["project_workspace_id"] == projects[0].id
        )
        building_permit = next(
            item
            for item in preview.effective_matrix
            if item["evidence_type"] == "PERMIT_READINESS" and item["project_workspace_id"] == projects[1].id
        )
        assert risk["classification"] == "A"
        assert risk["gap_status"] == "NONE"
        assert mining_permit["classification"] == "A"
        assert building_permit["classification"] == "B"
        assert "SOURCE_STALE" in preview.blockers
        assert preview.persisted is False
        assert preview.can_enter_fid is False
        assert preview.recommended_next_development == {"next": "READY_TO_DESIGN_GATE07K"}

        selection = service.preview(
            portfolio_id=portfolio.id,
            gate_profile_code="PYP-INV-SELECT",
            project_ids=[],
            configuration_id=record.id,
            content_override=record.content_json,
        )
        land = next(item for item in selection.effective_matrix if item["evidence_type"] == "LAND_ACCESS_READINESS")
        assert land["classification"] == "C"
        assert land["required"] is False
        assert land["blocking"] is False
    finally:
        db.close()


def test_provider_contract_validation_and_exact_gap_groups() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        service = InvestmentEvidencePolicyService(db, tenant_id, actor_id)
        assert service.validate_provider_contract(
            {
                "evidence_type": "RISK_READINESS",
                "scope": "PROJECT_SET",
                "readiness_status": "READY",
                "source_current": True,
                "as_of_date": utc_now().isoformat(),
                "warnings": [],
                "blockers": [],
            }
        ) == ["evidence_hash", "evidence_hash:empty"]
        groups = service.gap_analysis(deepcopy(DEFAULT_POLICY), "PYP-FFA", projects)
        assert list(groups) == [
            "AVAILABLE GOVERNED SOURCES",
            "MISSING GOVERNED SOURCES",
            "GOVERNED EVIDENCE SUFFICIENT",
            "NOT REQUIRED",
        ]
        assert "RISK_READINESS" in groups["AVAILABLE GOVERNED SOURCES"]
        assert "CONTRACTING_STRATEGY_READINESS" in groups["GOVERNED EVIDENCE SUFFICIENT"]
    finally:
        db.close()


def test_published_policy_snapshots_gate07j_and_class_a_rejects_manual_fallback() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        policy_service = InvestmentEvidencePolicyService(db, tenant_id, actor_id)
        policy = _policy(policy_service)
        policy = policy_service.publish_configuration(policy.id, policy.version)
        profile = _profile(db, tenant_id, actor_id, funding=True)
        gate = InvestmentGatePreparationService(db, tenant_id, actor_id)
        preparation = _preparation(gate, portfolio.id, profile.id)

        snapshot = dict(preparation.source_snapshot.get("evidence_policy") or {})
        assert snapshot["policy_id"] == policy.id
        assert snapshot["policy_revision"] == policy.revision
        assert snapshot["policy_hash"] == policy.content_hash
        risk = next(item for item in preparation.evidence if item.evidence_type == "RISK_READINESS")
        assert risk.status == "STALE"
        assert "SOURCE_STALE" in risk.blockers
        with pytest.raises(HTTPException) as forbidden:
            gate.add_evidence(
                preparation.id,
                preparation.revision_version,
                ManualEvidenceIn(
                    requirement_key=risk.requirement_key,
                    scope_type="PROJECT_SET",
                    reference_id="MANUAL-RISK-CANNOT-SUBSTITUTE",
                    evidence_date=utc_now(),
                    issuer="Risk Committee",
                    owner="Portfolio Governance",
                    summary="This controlled document must not replace a Class A provider.",
                    evidence_refs=[],
                    idempotency_key=f"risk-manual-{uuid4()}",
                ),
            )
        assert forbidden.value.detail["code"] == "MANUAL_REFERENCE_NOT_ALLOWED"
        assert "EVIDENCE_STALE" in gate.readiness(preparation.id).blockers
    finally:
        db.close()


def test_class_b_requires_validation_and_stale_etag_is_rejected() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        policy_service = InvestmentEvidencePolicyService(db, tenant_id, actor_id)
        policy = _policy(policy_service)
        policy_service.publish_configuration(policy.id, policy.version)
        profile = _profile(db, tenant_id, actor_id)
        preparer = InvestmentGatePreparationService(db, tenant_id, actor_id)
        preparation = _preparation(preparer, portfolio.id, profile.id)
        permit = next(
            item
            for item in preparation.evidence
            if item.evidence_type == "PERMIT_READINESS" and item.scope_id == projects[0].id
        )
        preparation = preparer.add_evidence(
            preparation.id,
            preparation.revision_version,
            ManualEvidenceIn(
                requirement_key=permit.requirement_key,
                scope_type="EACH_PROJECT",
                scope_id=projects[0].id,
                reference_id="PERMIT-REGISTER-01",
                evidence_date=utc_now(),
                valid_until=utc_now() + timedelta(days=90),
                issuer="Permitting Authority",
                owner="Project Governance",
                summary="Controlled permit readiness reference for independent validation.",
                evidence_refs=[{"document": "PERMIT-REGISTER-01", "version": "1"}],
                idempotency_key=f"permit-submit-{uuid4()}",
            ),
        )
        submitted = next(item for item in preparation.evidence if item.id == permit.id)
        assert submitted.status == "SUBMITTED"
        reviewer = _reviewer(db, tenant_id)
        validator = InvestmentGatePreparationService(db, tenant_id, reviewer.id)
        preparation = validator.validate_evidence(
            submitted.id,
            preparation.revision_version,
            EvidenceValidationIn(
                decision="VALID",
                validation_note="Scope, issuer, validity and reference were independently validated.",
                idempotency_key=f"permit-validate-{uuid4()}",
            ),
        )
        assert next(item for item in preparation.evidence if item.id == permit.id).status == "VALID"

        draft = policy_service.clone_configuration(policy.id, policy.version)
        stale_version = draft.version
        updated = policy_service.update_configuration(
            draft.id, draft.version, draft.name, draft.description, deepcopy(draft.content_json)
        )
        with pytest.raises(HTTPException) as stale:
            policy_service.update_configuration(
                updated.id, stale_version, updated.name, updated.description, deepcopy(updated.content_json)
            )
        assert stale.value.status_code == 412
        assert stale.value.detail["code"] == "ETAG_MISMATCH"
        events = set(
            db.scalars(
                select(SecurityEvent.event_type).where(
                    SecurityEvent.tenant_id == tenant_id,
                    SecurityEvent.event_type.like("investment_evidence_policy.%"),
                )
            ).all()
        )
        assert {
            "investment_evidence_policy.published",
            "investment_evidence_policy.cloned",
            "investment_evidence_policy.updated",
        }.issubset(events)
    finally:
        db.close()


def test_existing_frozen_preparation_is_not_reinterpreted_after_policy_publish() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        for record in db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.status == "published",
            )
        ).all():
            record.status = "superseded"
            record.version += 1
        db.commit()
        profile = _profile(db, tenant_id, actor_id)
        gate = InvestmentGatePreparationService(db, tenant_id, actor_id)
        preparation = _preparation(gate, portfolio.id, profile.id)
        assert preparation.source_snapshot.get("evidence_policy") is None
        original_source_hash = preparation.preparation_source_hash
        original_evidence = [(item.requirement_key, item.status) for item in preparation.evidence]

        policy_service = InvestmentEvidencePolicyService(db, tenant_id, actor_id)
        policy = _policy(policy_service)
        policy_service.publish_configuration(policy.id, policy.version)
        unchanged = gate.preparation(preparation.id)
        assert unchanged.preparation_source_hash == original_source_hash
        assert unchanged.source_snapshot.get("evidence_policy") is None
        assert [(item.requirement_key, item.status) for item in unchanged.evidence] == original_evidence
    finally:
        db.close()


def test_class_a_stale_source_blocks_without_manual_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
    db, tenant_id, actor_id, _portfolio, _projects, _convergence = _source()
    try:
        service = InvestmentEvidencePolicyService(db, tenant_id, actor_id)
        requirement = deepcopy(DEFAULT_POLICY["gate_profiles"]["PYP-FFA"]["requirements"][0])

        def stale_payload(*_args, **_kwargs):
            return {
                "evidence_type": "PORTFOLIO_RECOMMENDATION",
                "scope": "PORTFOLIO",
                "readiness_status": "READY",
                "source_current": False,
                "evidence_hash": "f" * 64,
                "as_of_date": utc_now().isoformat(),
                "warnings": [],
                "blockers": [],
            }

        monkeypatch.setattr(service, "_provider_payload", stale_payload)
        payload, error = service.resolve_governed_payload(requirement, {}, None)
        assert payload is not None
        assert error == "SOURCE_STALE"
        assert requirement["classification"] == "A"
        assert requirement["allow_manual_reference"] is False
    finally:
        db.close()


def test_non_capital_owner_project_set_is_not_made_mandatory() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        for project in projects:
            context = dict(dict(project.defaults_json or {}).get("_project", {}))
            context.update(project_type="BUILDING", governance_model="DIRECT_INTERNAL")
            project.defaults_json = {**dict(project.defaults_json or {}), "_project": context}
        db.commit()

        service = InvestmentEvidencePolicyService(db, tenant_id, actor_id)
        record = _policy(service)
        preview = service.preview(
            portfolio_id=portfolio.id,
            gate_profile_code="PYP-FFA",
            project_ids=[project.id for project in projects],
            configuration_id=record.id,
            content_override=record.content_json,
        )
        assert preview.blockers == []
        assert preview.missing_required_provider_count == 0
        assert {item["classification"] for item in preview.effective_matrix} == {"C"}
        assert all(not item["required"] and not item["blocking"] for item in preview.effective_matrix)
    finally:
        db.close()
