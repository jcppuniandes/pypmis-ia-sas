"""Gate 07J acceptance coverage for Investment Gate Preparation."""

from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.test_portfolio_convergence_gate07i import _convergence, _fixture

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, UserAccount
from app.main import app
from app.modules.investment_gate_preparation.schemas import (
    EvidenceValidationIn,
    ManualEvidenceIn,
    PreparationCreateIn,
    PreparationUpdateIn,
)
from app.modules.investment_gate_preparation.service import (
    CONFIGURATION_KIND,
    DEFAULT_PROFILES,
    InvestmentGatePreparationService,
    _hash,
)
from app.modules.portfolio_convergence.schemas import RecommendationIn
from app.modules.portfolio_convergence.service import PortfolioConvergenceService


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _source(*, conditional: bool = False):
    db, tenant_id, actor_id, portfolio, projects, budget_scenario, resource_scenario = _fixture(conditional=conditional)
    service = PortfolioConvergenceService(db, tenant_id, actor_id)
    convergence = _convergence(service, portfolio.id, budget_scenario.id, resource_scenario.id)
    alternative = convergence.alternatives[0]
    convergence = service.submit_review(convergence.id, convergence.revision_version, f"gate07j-submit-{uuid4()}")
    convergence = service.recommend(
        convergence.id,
        convergence.revision_version,
        RecommendationIn(
            recommended_alternative_id=alternative.id,
            recommendation_reason="Governed source for Investment Gate Preparation acceptance.",
            risks_acknowledged=["Investment approval remains downstream."],
            decision_support_summary="Budget and resource branches are current, aligned and feasible.",
            idempotency_key=f"gate07j-recommend-{uuid4()}",
        ),
    )
    return db, tenant_id, actor_id, portfolio, projects, convergence


def _profile(db, tenant_id: int, actor_id: int, *, funding: bool = False) -> AdminConfiguration:
    content = deepcopy(DEFAULT_PROFILES["pyp-ffa" if funding else "pyp-inv-select"])
    code = f"gate07j-{uuid4().hex[:10]}"
    record = AdminConfiguration(
        tenant_id=tenant_id,
        kind=CONFIGURATION_KIND,
        code=code,
        name=f"Published {content['profile_code']}",
        description="Isolated Gate 07J acceptance profile.",
        status="published",
        revision=1,
        version=1,
        content_json=content,
        content_hash=_hash(content),
        created_by_user_id=actor_id,
        published_at=utc_now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _reviewer(db, tenant_id: int) -> UserAccount:
    record = UserAccount(
        tenant_id=tenant_id,
        email=f"gate07j-reviewer-{uuid4().hex[:10]}@example.test",
        full_name="Independent Evidence Reviewer",
        title="Investment Evidence Reviewer",
        status="active",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _preparation(service, portfolio_id: int, profile_id: int):
    return service.create(
        PreparationCreateIn(
            portfolio_workspace_id=portfolio_id,
            investment_gate_profile_id=profile_id,
            name="Investment selection evidence package",
            description="Governed preparation; no investment approval or FID authority.",
            idempotency_key=f"gate07j-create-{uuid4()}",
        )
    )


def _add_fel(service, preparation, project_id: int, *, fel_stage: str = "FEL-2"):
    return service.add_evidence(
        preparation.id,
        preparation.revision_version,
        ManualEvidenceIn(
            requirement_key="fel-stage-readiness",
            scope_type="EACH_PROJECT",
            scope_id=project_id,
            reference_id=f"FEL-ASSESSMENT-{project_id}",
            evidence_date=utc_now(),
            valid_until=utc_now() + timedelta(days=180),
            issuer="Project Definition Office",
            owner="Capital Projects Governance",
            summary="Approved reference to the governed FEL readiness assessment.",
            evidence_refs=[
                {
                    "fel_stage": fel_stage,
                    "assessment_id": f"FEL-{project_id}",
                    "evidence_hash": "a" * 64,
                }
            ],
            idempotency_key=f"gate07j-fel-{project_id}-{uuid4()}",
        ),
    )


def _validate_latest_fel(service, preparation, project_id: int):
    evidence = next(
        item
        for item in preparation.evidence
        if item.requirement_key == "fel-stage-readiness" and item.scope_id == project_id
    )
    return service.validate_evidence(
        evidence.id,
        preparation.revision_version,
        EvidenceValidationIn(
            decision="VALID",
            validation_note="Independent review confirms scope, validity and FEL maturity.",
            idempotency_key=f"gate07j-validate-{project_id}-{uuid4()}",
        ),
    )


def test_happy_path_freezes_decision_ready_package_without_fid_authority() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        profile = _profile(db, tenant_id, actor_id)
        reviewer = _reviewer(db, tenant_id)
        preparer = InvestmentGatePreparationService(db, tenant_id, actor_id)
        preparation = _preparation(preparer, portfolio.id, profile.id)
        for project in projects:
            preparation = _add_fel(preparer, preparation, project.id)
        validator = InvestmentGatePreparationService(db, tenant_id, reviewer.id)
        for project in projects:
            preparation = _validate_latest_fel(validator, preparation, project.id)
        readiness = validator.readiness(preparation.id)
        assert readiness.readiness_status == "READY"
        assert readiness.coverage_percent == 100
        assert readiness.can_enter_fid is False
        preparation = preparer.ready_for_review(
            preparation.id, preparation.revision_version, f"gate07j-ready-{uuid4()}"
        )
        preparation = validator.freeze(preparation.id, preparation.revision_version, f"gate07j-freeze-{uuid4()}")
        handoff = validator.handoff(preparation.id)
        assert preparation.status == "FROZEN"
        assert handoff.final_output == "READY_FOR_INVESTMENT_DECISION"
        assert handoff.can_enter_investment_decision is True
        assert handoff.can_enter_fid is False
        assert handoff.preparation_hash
    finally:
        db.close()


def test_full_funds_profile_blocks_when_funding_evidence_is_missing() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        profile = _profile(db, tenant_id, actor_id, funding=True)
        service = InvestmentGatePreparationService(db, tenant_id, actor_id)
        preparation = _preparation(service, portfolio.id, profile.id)
        for project in projects:
            preparation = _add_fel(service, preparation, project.id, fel_stage="FEL-3")
        readiness = service.readiness(preparation.id)
        assert "MISSING_FUNDING_READINESS" in readiness.blockers
        assert readiness.can_enter_fid is False
    finally:
        db.close()


def test_insufficient_fel_maturity_and_scope_mismatch_are_rejected() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        profile = _profile(db, tenant_id, actor_id)
        reviewer = _reviewer(db, tenant_id)
        preparer = InvestmentGatePreparationService(db, tenant_id, actor_id)
        preparation = _preparation(preparer, portfolio.id, profile.id)
        preparation = _add_fel(preparer, preparation, projects[0].id, fel_stage="FEL-1")
        validator = InvestmentGatePreparationService(db, tenant_id, reviewer.id)
        preparation = _validate_latest_fel(validator, preparation, projects[0].id)
        item = next(
            value
            for value in preparation.evidence
            if value.requirement_key == "fel-stage-readiness" and value.scope_id == projects[0].id
        )
        assert item.status == "INVALID"
        assert "INSUFFICIENT_FEL_MATURITY" in item.blockers
        with pytest.raises(HTTPException) as mismatch:
            preparer.add_evidence(
                preparation.id,
                preparation.revision_version,
                ManualEvidenceIn(
                    requirement_key="fel-stage-readiness",
                    scope_type="EACH_PROJECT",
                    scope_id=999999,
                    reference_id="OUTSIDE-SCOPE",
                    evidence_date=utc_now(),
                    issuer="Issuer",
                    owner="Owner",
                    summary="Evidence intentionally outside the selected project set.",
                    evidence_refs=[{"fel_stage": "FEL-2"}],
                    idempotency_key=f"gate07j-mismatch-{uuid4()}",
                ),
            )
        assert mismatch.value.detail["code"] == "EVIDENCE_SCOPE_MISMATCH"
    finally:
        db.close()


def test_sod_is_enforced_and_frozen_revision_is_immutable() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        profile = _profile(db, tenant_id, actor_id)
        service = InvestmentGatePreparationService(db, tenant_id, actor_id)
        preparation = _preparation(service, portfolio.id, profile.id)
        preparation = _add_fel(service, preparation, projects[0].id)
        evidence = next(
            item
            for item in preparation.evidence
            if item.requirement_key == "fel-stage-readiness" and item.scope_id == projects[0].id
        )
        with pytest.raises(HTTPException) as sod:
            service.validate_evidence(
                evidence.id,
                preparation.revision_version,
                EvidenceValidationIn(
                    decision="VALID",
                    validation_note="Self validation must be blocked by SOD.",
                    idempotency_key=f"gate07j-sod-{uuid4()}",
                ),
            )
        assert sod.value.detail["code"] == "EVIDENCE_VALIDATION_SOD_VIOLATION"

        reviewer = _reviewer(db, tenant_id)
        validator = InvestmentGatePreparationService(db, tenant_id, reviewer.id)
        for project in projects:
            if project.id != projects[0].id:
                preparation = _add_fel(service, preparation, project.id)
            preparation = _validate_latest_fel(validator, preparation, project.id)
        preparation = service.ready_for_review(preparation.id, preparation.revision_version, f"gate07j-ready-{uuid4()}")
        preparation = validator.freeze(preparation.id, preparation.revision_version, f"gate07j-freeze-{uuid4()}")
        with pytest.raises(HTTPException) as immutable:
            service.update(
                preparation.id,
                preparation.revision_version,
                PreparationUpdateIn(name="Forbidden frozen change"),
            )
        assert immutable.value.detail["code"] == "FROZEN_PREPARATION_IMMUTABLE"
        stored = db.scalar(select(AdminConfiguration).where(AdminConfiguration.id == profile.id))
        assert stored is not None
    finally:
        db.close()
