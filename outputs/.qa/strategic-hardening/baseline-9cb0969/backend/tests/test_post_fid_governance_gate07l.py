"""Gate 07L acceptance coverage for post-FID eligibility and handoff."""

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from tests.test_investment_decision_gate07k import _decision_ready, _freeze_preparation, _maker
from tests.test_investment_gate_preparation_gate07j import _source

from app.main import app
from app.modules.investment_decision.schemas import DecisionDecideIn
from app.modules.investment_decision.service import InvestmentDecisionService
from app.modules.post_fid_governance.service import (
    BLOCKED,
    NO_REACTIVATION,
    NOT_APPLICABLE,
    READY_ACTIVATION,
    READY_INITIALIZATION,
    PostFIDGovernanceService,
)
from app.modules.project_workspace_initialization.models import ProjectWorkspaceInitialization


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _decision_stub(*, conditions=None):
    return SimpleNamespace(
        id=90001,
        decision_hash="d" * 64,
        source_package_hash="p" * 64,
        conditions_json=conditions or [],
        authorization_valid_until=None,
    )


def _service_and_project():
    db, tenant_id, actor_id, _portfolio, projects, _ = _source()
    service = PostFIDGovernanceService(db, tenant_id, actor_id)
    service.ensure_seed()
    service._decision_validity = lambda _decision, _config: (True, True, [], [])  # type: ignore[method-assign]
    return db, service, projects[0]


def test_project_state_routes_reuse_existing_initialization_state() -> None:
    db, service, project = _service_and_project()
    try:
        config = service._published_configuration()
        not_initialized = service._evaluate_project(_decision_stub(), project, config, persisted=False)
        assert not_initialized.eligibility_status == READY_INITIALIZATION
        initialization = ProjectWorkspaceInitialization(
            tenant_id=project.tenant_id,
            workspace_id=project.id,
            state="READY_FOR_ACTIVATION",
            template_config_id=config.id,
            template_code=config.code,
            template_revision=config.revision,
            last_modified_by_user_id=service.actor_id,
        )
        db.add(initialization)
        db.commit()
        initialized = service._evaluate_project(_decision_stub(), project, config, persisted=False)
        assert initialized.eligibility_status == READY_ACTIVATION
        project.status = "active"
        project.version += 1
        db.commit()
        active = service._evaluate_project(_decision_stub(), project, config, persisted=False)
        assert active.eligibility_status == NO_REACTIVATION
        assert active.can_initialize is False and active.can_activate is False
    finally:
        db.rollback()
        db.close()


def test_activation_blocker_and_commitment_only_semantics_are_separate() -> None:
    db, service, project = _service_and_project()
    try:
        config = service._published_configuration()
        blocked = service._evaluate_project(
            _decision_stub(
                conditions=[
                    {
                        "code": "ACT-01",
                        "status": "OPEN",
                        "blocking_for_activation": True,
                        "blocking_for_commitment": False,
                    }
                ]
            ),
            project,
            config,
            persisted=False,
        )
        assert blocked.eligibility_status == BLOCKED
        assert blocked.open_activation_blockers == 1
        commitment_only = service._evaluate_project(
            _decision_stub(
                conditions=[
                    {
                        "code": "COM-01",
                        "status": "OPEN",
                        "blocking_for_activation": False,
                        "blocking_for_commitment": True,
                    }
                ]
            ),
            project,
            config,
            persisted=False,
        )
        assert commitment_only.eligibility_status == READY_INITIALIZATION
        assert commitment_only.open_commitment_conditions_count == 1
        assert "OPEN_COMMITMENT_CONDITIONS" in commitment_only.warnings
    finally:
        db.rollback()
        db.close()


def test_contractor_and_direct_governance_models_remain_unaffected() -> None:
    db, service, project = _service_and_project()
    try:
        config = service._published_configuration()
        defaults = dict(project.defaults_json or {})
        metadata = dict(defaults.get("_project", {}))
        metadata["governance_model"] = "CONTRACTOR_DELIVERY"
        defaults["_project"] = metadata
        project.defaults_json = defaults
        result = service._evaluate_project(_decision_stub(), project, config, persisted=False)
        assert result.eligibility_status == NOT_APPLICABLE
        assert "GOVERNANCE_MODEL_CONTRACTOR_DELIVERY_UNAFFECTED" in result.warnings
    finally:
        db.rollback()
        db.close()


def test_valid_fid_persists_immutable_per_project_snapshots_idempotently() -> None:
    db, tenant_id, actor_id, reviewer_id, _portfolio, _projects, preparation = _freeze_preparation(funding=True)
    try:
        maker = _maker(db, tenant_id, "Independent Gate 07L FID Authority")
        decision = _decision_ready(db, tenant_id, actor_id, reviewer_id, preparation, maker.id)
        payload = DecisionDecideIn(
            outcome="GO",
            rationale="Authorize FID and hand off to controlled post-FID governance.",
            authorized_amount=Decimal("7500000.00"),
            authorized_currency="USD",
            idempotency_key=f"gate07l-fid-{uuid4()}",
        )
        decided = InvestmentDecisionService(db, tenant_id, maker.id).decide(
            decision.id, decision.revision_version, payload
        )
        service = PostFIDGovernanceService(db, tenant_id, actor_id)
        key = f"gate07l-evaluate-{uuid4()}"
        first = service.evaluate(decided.id, key, 1)
        duplicate = service.evaluate(decided.id, key, 1)
        assert first
        assert [item.id for item in duplicate] == [item.id for item in first]
        assert all(item.persisted for item in first)
        assert all(item.eligibility_status == READY_INITIALIZATION for item in first)
        assert all(item.can_initialize and not item.can_activate for item in first)
        assert all(item.fid_decision_hash == decided.decision_hash for item in first)
    finally:
        db.rollback()
        db.close()
