"""Gate 07J-RISK acceptance tests for governed Risk Readiness."""

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
from app.modules.risk_readiness.models import RiskReadinessAssessment
from app.modules.risk_readiness.schemas import AssessmentActionIn, AssessmentCreateIn, RiskAcceptanceIn, RiskCreateIn
from app.modules.risk_readiness.service import (
    DEFAULT_CONFIGURATION,
    FINAL_OUTPUT,
    FINAL_RELEASE_STATUS,
    RiskReadinessService,
)


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _publish(service: RiskReadinessService) -> AdminConfiguration:
    seed = service.ensure_seed()
    if seed.status == "published":
        return seed
    if seed.status != "draft":
        seed = service.clone_configuration(seed.id, seed.version)
    return service.publish_configuration(seed.id, seed.version)


def _low_risk(service: RiskReadinessService, project_id: int, *, title: str = "Controlled low risk"):
    return service.create_risk(
        project_id,
        RiskCreateIn(
            title=title,
            description="A governed Project risk used for readiness validation.",
            risk_category="TECHNICAL",
            identified_date=date.today(),
            cause="Known technical uncertainty",
            event="Controlled event may occur",
            impact_description="Limited impact within tolerance",
            likelihood_before=2,
            impact_before=2,
            evidence_refs=[{"reference": "RISK-EVIDENCE-01"}],
            idempotency_key=f"risk-create-{uuid4()}",
        ),
    )


def _complete(service: RiskReadinessService, project_id: int):
    assessment = service.create_assessment(
        project_id,
        AssessmentCreateIn(idempotency_key=f"risk-assessment-{uuid4()}"),
    )
    return service.complete_assessment(
        assessment.id,
        assessment.revision_version,
        AssessmentActionIn(idempotency_key=f"risk-complete-{uuid4()}"),
    )


def test_project_and_project_set_happy_path_supply_current_governed_evidence() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        service = RiskReadinessService(db, tenant_id, actor_id)
        _publish(service)
        for project in projects:
            _low_risk(service, project.id, title=f"Controlled risk {project.id}")
            completed = _complete(service, project.id)
            assert completed.status == "COMPLETED"
            assert completed.readiness_status == "READY"
            assert completed.risk_readiness_hash

        aggregate = service.portfolio_readiness(portfolio.id)
        evidence = service.investment_gate_evidence(portfolio.id)
        assert aggregate.readiness_status == "READY"
        assert aggregate.coverage_percent == 100
        assert evidence.final_output == FINAL_OUTPUT
        assert evidence.provider_key == "RISK_READINESS_PROVIDER"
        assert evidence.source_current is True
        assert evidence.can_supply_investment_gate_evidence is True
        assert evidence.can_enter_fid is False
        assert evidence.project_source_references == [
            {
                "project_workspace_id": item.project_workspace_id,
                "assessment_id": item.assessment_id,
                "assessment_hash": item.assessment_hash,
                "risk_readiness_hash": item.risk_readiness_hash,
                "source_current": item.source_current,
                "readiness_status": item.readiness_status,
            }
            for item in aggregate.project_readiness
        ]
        assert {item["project_workspace_id"] for item in evidence.project_source_references} == {
            item.id for item in projects
        }
        assert all(item["assessment_id"] and item["risk_readiness_hash"] for item in evidence.project_source_references)
        assert service.overview().final_release_status == FINAL_RELEASE_STATUS
    finally:
        db.close()


def test_change_after_completion_makes_evidence_stale_until_reassessment() -> None:
    db, tenant_id, actor_id, _portfolio, projects, _convergence = _source()
    try:
        service = RiskReadinessService(db, tenant_id, actor_id)
        _publish(service)
        risk = _low_risk(service, projects[0].id)
        _complete(service, projects[0].id)
        service.change_status(risk.id, risk.revision_version, "MONITORING")
        readiness = service.project_readiness(projects[0].id)
        assert readiness.readiness_status == "STALE"
        assert readiness.source_current is False
        assert "STALE_RISK_SOURCE" in readiness.blockers
    finally:
        db.close()


def test_owner_cannot_accept_own_high_residual_and_etag_is_enforced() -> None:
    db, tenant_id, actor_id, _portfolio, projects, _convergence = _source()
    try:
        service = RiskReadinessService(db, tenant_id, actor_id)
        _publish(service)
        risk = service.create_risk(
            projects[0].id,
            RiskCreateIn(
                title="High residual authority test",
                risk_category="COST",
                identified_date=date.today(),
                risk_owner_id=actor_id,
                cause="Escalating input costs",
                event="Cost exposure materializes",
                impact_description="Portfolio affordability is affected",
                likelihood_before=4,
                impact_before=4,
                treatment_required=True,
                treatment_strategy="REDUCE",
                treatment_description="Apply indexed commercial controls.",
                treatment_owner_id=actor_id,
                target_treatment_date=date.today() + timedelta(days=30),
                treatment_status="IN_PROGRESS",
                likelihood_after=3,
                impact_after=4,
                residual_acceptance_required=True,
                evidence_refs=[{"reference": "COST-RISK-01"}],
                idempotency_key=f"risk-high-{uuid4()}",
            ),
        )
        with pytest.raises(HTTPException) as sod:
            service.accept_residual(
                risk.id,
                risk.revision_version,
                RiskAcceptanceIn(
                    acceptance_comment="Owner self-acceptance must not be allowed.",
                    acceptance_authority_level="EXECUTIVE_SPONSOR",
                    idempotency_key=f"accept-{uuid4()}",
                ),
            )
        assert sod.value.detail["code"] == "RISK_OWNER_CANNOT_ACCEPT_OWN_RESIDUAL"
        with pytest.raises(HTTPException) as stale:
            service.change_status(risk.id, risk.revision_version + 1, "UNDER_TREATMENT")
        assert stale.value.status_code == 412
        assert stale.value.detail["code"] == "ETAG_MISMATCH"
    finally:
        db.close()


def test_ffa_registry_is_available_without_changing_selection_class_b() -> None:
    db, tenant_id, actor_id, _portfolio, _projects, _convergence = _source()
    try:
        provider = PROVIDER_REGISTRY["RISK_READINESS_PROVIDER"]
        assert provider["status"] == "AVAILABLE"
        assert provider["source_module"] == "RISK_READINESS"
        service = InvestmentEvidencePolicyService(db, tenant_id, actor_id)
        ffa = next(
            item
            for item in service._effective_matrix(deepcopy(DEFAULT_POLICY), "PYP-FFA", [])
            if item["evidence_type"] == "RISK_READINESS"
        )
        selection = next(
            item
            for item in service._effective_matrix(deepcopy(DEFAULT_POLICY), "PYP-INV-SELECT", [])
            if item["evidence_type"] == "RISK_READINESS"
        )
        assert (ffa["classification"], ffa["blocking"], ffa["validity_period_days"]) == ("A", True, 90)
        assert ffa["allow_manual_reference"] is False
        assert selection["classification"] == "B"
        assert selection["blocking"] is False
        assert selection["validity_period_days"] == 90
    finally:
        db.close()


def test_configuration_preview_is_non_persistent_and_audit_events_exist() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        service = RiskReadinessService(db, tenant_id, actor_id)
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
        service.publish_configuration(draft.id, draft.version)
        events = set(
            db.scalars(
                select(SecurityEvent.event_type).where(
                    SecurityEvent.tenant_id == tenant_id,
                    SecurityEvent.event_type.like("risk_readiness.%"),
                )
            ).all()
        )
        assert {"risk_readiness.configuration_seeded", "risk_readiness.configuration_published"}.issubset(events)
    finally:
        db.close()


def test_critical_owner_treatment_residual_evidence_and_overdue_rules_block_readiness() -> None:
    db, tenant_id, actor_id, _portfolio, projects, _convergence = _source()
    try:
        service = RiskReadinessService(db, tenant_id, actor_id)
        _publish(service)
        critical = service.create_risk(
            projects[0].id,
            RiskCreateIn(
                title="Uncontrolled critical exposure",
                risk_category="TECHNICAL",
                identified_date=date.today(),
                likelihood_before=5,
                impact_before=5,
                treatment_required=True,
                evidence_refs=[],
                idempotency_key=f"risk-critical-{uuid4()}",
            ),
        )
        overdue = service.create_risk(
            projects[0].id,
            RiskCreateIn(
                title="Overdue high treatment",
                risk_category="COST",
                identified_date=date.today(),
                risk_owner_id=actor_id,
                likelihood_before=4,
                impact_before=4,
                treatment_required=True,
                treatment_strategy="REDUCE",
                treatment_description="Mitigate the controlled exposure.",
                treatment_owner_id=actor_id,
                target_treatment_date=date.today() - timedelta(days=1),
                treatment_status="IN_PROGRESS",
                likelihood_after=2,
                impact_after=2,
                evidence_refs=[{"reference": "TREATMENT-EVIDENCE-01"}],
                idempotency_key=f"risk-overdue-{uuid4()}",
            ),
        )
        assessment = service.create_assessment(
            projects[0].id,
            AssessmentCreateIn(idempotency_key=f"risk-blockers-{uuid4()}"),
        )
        blockers = set(assessment.blockers_json)
        assert f"HIGH_CRITICAL_OWNER_REQUIRED:{critical.risk_number}" in blockers
        assert f"TREATMENT_REQUIRED:{critical.risk_number}" in blockers
        assert f"RESIDUAL_ASSESSMENT_REQUIRED:{critical.risk_number}" in blockers
        assert "RISK_EVIDENCE_COVERAGE_BELOW_THRESHOLD" in blockers
        assert f"OVERDUE_TREATMENT:{overdue.risk_number}" in blockers
        with pytest.raises(HTTPException) as blocked:
            service.complete_assessment(
                assessment.id,
                assessment.revision_version,
                AssessmentActionIn(idempotency_key=f"risk-blocked-complete-{uuid4()}"),
            )
        assert blocked.value.detail["code"] == "RISK_READINESS_BLOCKED"
    finally:
        db.close()


def test_expired_completed_assessment_cannot_supply_current_evidence() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        service = RiskReadinessService(db, tenant_id, actor_id)
        _publish(service)
        for project in projects:
            _low_risk(service, project.id, title=f"Expiry control {project.id}")
            completed = _complete(service, project.id)
            db.execute(
                update(RiskReadinessAssessment)
                .where(RiskReadinessAssessment.id == completed.id)
                .values(valid_until=utc_now() - timedelta(days=1))
            )
            db.commit()
        readiness = service.project_readiness(projects[0].id)
        evidence = service.investment_gate_evidence(portfolio.id)
        assert readiness.readiness_status == "EXPIRED"
        assert readiness.source_current is False
        assert "RISK_READINESS_EXPIRED" in readiness.blockers
        assert evidence.can_supply_investment_gate_evidence is False
    finally:
        db.close()


def test_project_set_missing_project_is_not_averaged_away() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        service = RiskReadinessService(db, tenant_id, actor_id)
        _publish(service)
        assert len(projects) >= 2
        _low_risk(service, projects[0].id, title="Only covered Project")
        _complete(service, projects[0].id)
        aggregate = service.portfolio_readiness(portfolio.id)
        assert aggregate.required_project_count == len(projects)
        assert aggregate.valid_project_count == 1
        assert aggregate.coverage_percent < 100
        assert aggregate.readiness_status == "BLOCKED"
        assert "RISK_READINESS_COVERAGE_BELOW_100" in aggregate.blockers
    finally:
        db.close()
