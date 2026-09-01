"""Gate 07J-PERMIT acceptance tests for governed Permit Readiness."""

from copy import deepcopy
from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from tests.test_investment_gate_preparation_gate07j import _source

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, SecurityEvent
from app.main import app
from app.modules.investment_evidence_policy.service import (
    DEFAULT_POLICY,
    PROVIDER_REGISTRY,
    InvestmentEvidencePolicyService,
)
from app.modules.permit_readiness.models import PermitReadinessAssessment
from app.modules.permit_readiness.schemas import (
    AssessmentActionIn,
    AssessmentCreateIn,
    ConditionCreateIn,
    PermitCreateIn,
    PermitStatusIn,
)
from app.modules.permit_readiness.service import (
    DEFAULT_CONFIGURATION,
    FINAL_OUTPUT,
    FINAL_RELEASE_STATUS,
    PermitReadinessService,
)


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _as_mining(project, *, geography: str = "CO-ANT") -> None:
    defaults = deepcopy(project.defaults_json or {})
    defaults["_project"] = {
        **dict(defaults.get("_project", {})),
        "governance_model": "CAPITAL_OWNER",
        "planning_origin": "STRATEGIC_GATE",
        "project_type_code": "MINING",
        "region_code": geography,
    }
    project.defaults_json = defaults


def _publish(service: PermitReadinessService) -> AdminConfiguration:
    seed = service.ensure_seed()
    if seed.status == "published":
        return seed
    if seed.status != "draft":
        seed = service.clone_configuration(seed.id, seed.version)
    return service.publish_configuration(seed.id, seed.version)


def _approved_permits(service: PermitReadinessService, project_id: int, *, condition: bool = False):
    records = []
    for requirement in DEFAULT_CONFIGURATION["requirements"]:
        status = "APPROVED_WITH_CONDITIONS" if condition and not records else "APPROVED"
        permit = service.create_permit(
            project_id,
            PermitCreateIn(
                permit_type_code=requirement["permit_type_code"],
                requirement_key=requirement["requirement_key"],
                title=requirement["description"],
                issuing_authority="Configured competent authority",
                status=status,
                application_reference=f"APP-{uuid4().hex[:10]}",
                application_date=date.today() - timedelta(days=60),
                approval_date=date.today() - timedelta(days=30),
                effective_from=date.today() - timedelta(days=30),
                valid_until=date.today() + timedelta(days=365),
                permit_identifier=f"AUTH-{uuid4().hex[:10]}",
                evidence_refs=[{"reference": f"PERMIT-EVIDENCE-{uuid4().hex[:8]}"}],
                idempotency_key=f"permit-create-{uuid4()}",
            ),
        )
        records.append(permit)
    return records


def _complete(service: PermitReadinessService, project_id: int):
    assessment = service.create_assessment(
        project_id,
        AssessmentCreateIn(gate_profile_code="PYP-FFA", idempotency_key=f"permit-assess-{uuid4()}"),
    )
    return service.complete_assessment(
        assessment.id,
        assessment.revision_version,
        AssessmentActionIn(idempotency_key=f"permit-complete-{uuid4()}"),
    )


def test_happy_path_project_and_project_set_supply_current_evidence() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        service = PermitReadinessService(db, tenant_id, actor_id)
        _publish(service)
        for project in projects:
            _as_mining(project)
        db.commit()
        for project in projects:
            _approved_permits(service, project.id)
            completed = _complete(service, project.id)
            assert completed.status == "COMPLETED"
            assert completed.readiness_status == "READY"
            assert completed.permit_readiness_hash

        aggregate = service.portfolio_readiness(portfolio.id)
        evidence = service.investment_gate_evidence(portfolio.id)
        assert aggregate.required_project_count == len(projects)
        assert aggregate.readiness_status == "READY"
        assert aggregate.coverage_percent == 100
        assert evidence.final_output == FINAL_OUTPUT
        assert evidence.provider_key == "PERMIT_READINESS_PROVIDER"
        assert evidence.can_supply_investment_gate_evidence is True
        assert evidence.can_enter_fid is False
        assert service.overview().final_release_status == FINAL_RELEASE_STATUS
        policy = InvestmentEvidencePolicyService(db, tenant_id, actor_id)
        requirement = next(
            item
            for item in policy._effective_matrix(deepcopy(DEFAULT_POLICY), "PYP-FFA", [projects[0]])
            if item["evidence_type"] == "PERMIT_READINESS"
        )
        contract = service._portfolio_projects(portfolio.id)
        governed, error = policy.resolve_governed_payload(
            requirement,
            {"portfolio_workspace_id": portfolio.id, "selected_project_set_hash": contract[1]},
            projects[0].id,
        )
        assert error is None
        assert governed and governed["source_module"] == "PERMIT_READINESS"
    finally:
        db.close()


def test_submitted_missing_rejected_suspended_and_expired_permits_block_ffa() -> None:
    db, tenant_id, actor_id, _portfolio, projects, _convergence = _source()
    try:
        service = PermitReadinessService(db, tenant_id, actor_id)
        _publish(service)
        project = projects[0]
        _as_mining(project)
        db.commit()
        records = _approved_permits(service, project.id)
        records[0].status = "SUBMITTED"
        records[1].status = "REJECTED"
        records[2].status = "SUSPENDED"
        db.commit()
        assessment = service.create_assessment(
            project.id,
            AssessmentCreateIn(gate_profile_code="PYP-FFA", idempotency_key=f"permit-blocked-{uuid4()}"),
        )
        assert assessment.readiness_status == "BLOCKED"
        assert assessment.rejected_count == 1
        assert assessment.suspended_count == 1
        assert any(item.startswith("PERMIT_NOT_APPROVED") for item in assessment.blockers_json)
        db.delete(assessment)
        db.commit()
        records[0].status = "APPROVED"
        records[0].valid_until = date.today() - timedelta(days=1)
        db.commit()
        expired = service.create_assessment(
            project.id,
            AssessmentCreateIn(gate_profile_code="PYP-FFA", idempotency_key=f"permit-expired-{uuid4()}"),
        )
        assert expired.expired_count == 1
        assert any(item.startswith("PERMIT_EXPIRED") for item in expired.blockers_json)
    finally:
        db.close()


def test_blocking_condition_blocks_and_nonblocking_condition_is_allowed() -> None:
    db, tenant_id, actor_id, _portfolio, projects, _convergence = _source()
    try:
        service = PermitReadinessService(db, tenant_id, actor_id)
        _publish(service)
        project = projects[0]
        _as_mining(project)
        db.commit()
        permits = _approved_permits(service, project.id, condition=True)
        service.create_condition(
            permits[0].id,
            ConditionCreateIn(
                condition_key="MONITORING_REPORT",
                description="Provide the configured periodic monitoring report.",
                blocking=False,
                status="OPEN",
                idempotency_key=f"permit-condition-{uuid4()}",
            ),
        )
        completed = _complete(service, project.id)
        assert completed.readiness_status == "READY"
        blocking = service.create_condition(
            permits[0].id,
            ConditionCreateIn(
                condition_key="PRESTART_APPROVAL",
                description="Configured pre-start condition must be satisfied.",
                blocking=True,
                status="OPEN",
                idempotency_key=f"permit-condition-{uuid4()}",
            ),
        )
        reassessment = service.reassess(
            completed.id,
            AssessmentActionIn(idempotency_key=f"permit-condition-reassess-{uuid4()}"),
        )
        assert reassessment.open_blocking_conditions_count == 1
        assert f"OPEN_BLOCKING_CONDITION:{blocking.condition_key}" in reassessment.blockers_json
    finally:
        db.close()


def test_change_after_completion_makes_source_stale_and_expiry_is_honoured() -> None:
    db, tenant_id, actor_id, _portfolio, projects, _convergence = _source()
    try:
        service = PermitReadinessService(db, tenant_id, actor_id)
        _publish(service)
        project = projects[0]
        _as_mining(project)
        db.commit()
        permits = _approved_permits(service, project.id)
        completed = _complete(service, project.id)
        service.change_permit_status(
            permits[0].id,
            permits[0].revision_version,
            PermitStatusIn(status="SUSPENDED", idempotency_key=f"permit-status-{uuid4()}"),
        )
        stale = service.project_readiness(project.id)
        assert stale.readiness_status == "STALE"
        assert stale.source_current is False
        computed = service._compute(project, service._effective_content(project), utc_now(), "PYP-FFA")
        db.execute(
            update(PermitReadinessAssessment)
            .where(PermitReadinessAssessment.id == completed.id)
            .values(
                valid_until=utc_now() - timedelta(days=1),
                permit_source_hash=computed["permit_source_hash"],
            )
        )
        db.commit()
        assert service.project_readiness(project.id).readiness_status == "EXPIRED"
    finally:
        db.close()


def test_contextual_classification_preserves_class_b_and_elevates_mining_ffa() -> None:
    db, tenant_id, actor_id, _portfolio, projects, _convergence = _source()
    try:
        policy = InvestmentEvidencePolicyService(db, tenant_id, actor_id)
        selection = next(
            item
            for item in policy._effective_matrix(deepcopy(DEFAULT_POLICY), "PYP-INV-SELECT", projects)
            if item["evidence_type"] == "PERMIT_READINESS" and item.get("project_workspace_id") == projects[0].id
        )
        assert selection["classification"] == "B"
        _as_mining(projects[0])
        db.commit()
        mining = next(
            item
            for item in policy._effective_matrix(deepcopy(DEFAULT_POLICY), "PYP-FFA", [projects[0]])
            if item["evidence_type"] == "PERMIT_READINESS" and item.get("project_workspace_id") == projects[0].id
        )
        assert (mining["classification"], mining["blocking"], mining["provider_key"]) == (
            "A",
            True,
            "PERMIT_READINESS_PROVIDER",
        )
        assert mining["allow_manual_reference"] is False
        provider = PROVIDER_REGISTRY["PERMIT_READINESS_PROVIDER"]
        assert provider["status"] == "AVAILABLE"
        assert provider["source_module"] == "PERMIT_READINESS"
        assert policy._next_development([]) == {"next": "READY_TO_DESIGN_GATE07K"}
    finally:
        db.close()


def test_project_set_denominator_only_counts_contextual_class_a_projects() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        service = PermitReadinessService(db, tenant_id, actor_id)
        _publish(service)
        _as_mining(projects[0])
        db.commit()
        _approved_permits(service, projects[0].id)
        _complete(service, projects[0].id)
        aggregate = service.portfolio_readiness(portfolio.id)
        assert aggregate.required_project_count == 1
        assert aggregate.valid_project_count == 1
        assert aggregate.coverage_percent == 100
    finally:
        db.close()


def test_preview_nonpersistent_etag_and_audit_events() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        service = PermitReadinessService(db, tenant_id, actor_id)
        draft = service.ensure_seed()
        if draft.status != "draft":
            draft = service.clone_configuration(draft.id, draft.version)
        preview = service.admin_preview(
            portfolio_id=portfolio.id,
            project_ids=[project.id for project in projects],
            gate_profile_code="PYP-FFA",
            configuration_id=draft.id,
            content_override=deepcopy(DEFAULT_CONFIGURATION),
        )
        assert preview.persisted is False
        assert preview.can_enter_fid is False
        stale_version = draft.version
        service.publish_configuration(draft.id, draft.version)
        with pytest.raises(HTTPException) as stale:
            service.clone_configuration(draft.id, stale_version)
        assert stale.value.status_code == 412
        events = set(
            db.scalars(
                select(SecurityEvent.event_type).where(
                    SecurityEvent.tenant_id == tenant_id,
                    SecurityEvent.event_type.like("permit_readiness.%"),
                )
            ).all()
        )
        assert {
            "permit_readiness.configuration.seeded",
            "permit_readiness.configuration.published",
        }.issubset(events)
    finally:
        db.close()
