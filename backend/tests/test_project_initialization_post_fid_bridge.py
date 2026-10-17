"""The real FID/07L authority bridges to 05C without rewriting creation history."""

from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from tests.test_investment_decision_gate07k import _decision_ready, _freeze_preparation, _maker

from app.core.time import utc_now
from app.main import app
from app.modules.investment_decision.models import InvestmentDecision
from app.modules.investment_decision.schemas import DecisionDecideIn
from app.modules.investment_decision.service import InvestmentDecisionService
from app.modules.investment_gate_preparation.models import InvestmentGatePreparation
from app.modules.post_fid_governance.service import READY_ACTIVATION, READY_INITIALIZATION, PostFIDGovernanceService
from app.modules.project_workspace_initialization.governance import post_fid_lifecycle_authorization
from app.modules.project_workspace_initialization.models import ProjectWorkspaceInitialization


@pytest.fixture(scope="module")
def governed():
    with TestClient(app):
        db, tenant, author, reviewer, _portfolio, projects, preparation = _freeze_preparation(funding=True)
        try:
            maker = _maker(db, tenant, "Independent initialization bridge FID authority")
            decision = _decision_ready(db, tenant, author, reviewer, preparation, maker.id)
            decided = InvestmentDecisionService(db, tenant, maker.id).decide(
                decision.id,
                decision.revision_version,
                DecisionDecideIn(
                    outcome="GO",
                    rationale="UAT real FID, never automatic initialization or activation.",
                    authorized_amount=Decimal("7500000.00"),
                    authorized_currency="USD",
                    idempotency_key=f"init-bridge-fid-{uuid4()}",
                ),
            )
            post = PostFIDGovernanceService(db, tenant, author)
            certificates = post.evaluate(decided.id, f"init-bridge-evaluate-{uuid4()}", 1)
            assert all(item.eligibility_status == READY_INITIALIZATION for item in certificates)
            yield SimpleNamespace(
                db=db,
                tenant=tenant,
                author=author,
                post=post,
                project=projects[0],
                decision=db.get(InvestmentDecision, decided.id),
                preparation=db.get(InvestmentGatePreparation, preparation.id),
                certificate=post._latest(decided.id, projects[0].id),
            )
        finally:
            db.rollback()
            db.close()


def _authorize(g, **kwargs):
    return post_fid_lifecycle_authorization(g.db, g.tenant, g.author, g.project, **kwargs)


def test_real_fid_bridge_is_read_only_and_frozen_history_is_preserved(governed):
    g = governed
    creation_before = deepcopy(g.project.defaults_json)
    package_before = deepcopy(g.decision.decision_package_snapshot_json)
    frozen_before = (g.preparation.preparation_hash, deepcopy(g.preparation.source_snapshot_json))
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.strip().split()[0].upper())

    event.listen(g.db.bind, "before_cursor_execute", capture)
    try:
        allowed, evidence = _authorize(g)
    finally:
        event.remove(g.db.bind, "before_cursor_execute", capture)
    assert allowed and evidence["investment_decision_id"] == g.decision.id
    assert evidence["fid_decision_hash"] == g.decision.decision_hash
    assert not {"INSERT", "UPDATE", "DELETE"}.intersection(statements)
    assert g.project.defaults_json == creation_before
    assert g.decision.decision_package_snapshot_json == package_before
    assert (g.preparation.preparation_hash, g.preparation.source_snapshot_json) == frozen_before
    assert g.project.status == "pending"
    assert not _authorize(g, for_activation=True)[0]


@pytest.mark.parametrize("state", ["INITIALIZING", "BLOCKED"])
def test_initialization_own_state_transition_does_not_revoke_valid_handoff(governed, state):
    g = governed
    config = g.post._published_configuration()
    initialization = ProjectWorkspaceInitialization(
        tenant_id=g.tenant,
        workspace_id=g.project.id,
        state=state,
        template_config_id=config.id,
        template_code=config.code,
        template_revision=config.revision,
        last_modified_by_user_id=g.author,
    )
    g.db.add(initialization)
    g.db.flush()
    try:
        assert _authorize(g)[0]
        assert not _authorize(g, for_activation=True)[0]
    finally:
        g.db.rollback()


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("is_fid", False),
        ("full_funds_authorized", False),
        ("investment_authorized", False),
        ("outcome", "HOLD"),
        ("source_package_hash", "0" * 64),
        ("decision_hash", "0" * 64),
        ("authorization_valid_until", utc_now() - timedelta(days=1)),
    ],
)
def test_invalid_or_expired_fid_never_authorizes(governed, monkeypatch, field, invalid_value):
    g = governed
    with monkeypatch.context() as scoped:
        scoped.setattr(g.decision, field, invalid_value)
        assert not _authorize(g)[0]
        assert not _authorize(g, for_activation=True)[0]
    g.db.rollback()


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("source_current", False),
        ("blockers_json", ["OPEN_ACTIVATION_BLOCKERS"]),
        ("condition_snapshot_hash", "0" * 64),
        ("configuration_hash", "0" * 64),
        ("fid_decision_hash", "0" * 64),
        ("decision_package_hash", "0" * 64),
        ("eligibility_status", "STALE"),
        ("eligible_for_initialization", False),
    ],
)
def test_stale_or_ineligible_post_fid_snapshot_never_authorizes(governed, monkeypatch, field, invalid_value):
    g = governed
    with monkeypatch.context() as scoped:
        scoped.setattr(g.certificate, field, invalid_value)
        assert not _authorize(g)[0]
    g.db.rollback()


def test_wrong_tenant_wrong_project_and_missing_persisted_handoff_fail_closed(governed):
    g = governed
    assert not post_fid_lifecycle_authorization(g.db, g.tenant + 10000, g.author, g.project)[0]
    outside = SimpleNamespace(id=-1, tenant_id=g.tenant, workspace_type_code="project")
    assert not post_fid_lifecycle_authorization(g.db, g.tenant, g.author, outside)[0]


def test_activation_needs_separate_current_persisted_post_fid_activation_handoff(governed):
    g = governed
    config = g.post._published_configuration()
    initialization = ProjectWorkspaceInitialization(
        tenant_id=g.tenant,
        workspace_id=g.project.id,
        state="READY_FOR_ACTIVATION",
        template_config_id=config.id,
        template_code=config.code,
        template_revision=config.revision,
        last_modified_by_user_id=g.author,
    )
    g.db.add(initialization)
    g.db.commit()
    try:
        assert not _authorize(g, for_activation=True)[0]
        old_evidence = _authorize(g)[1]
        refreshed = g.post.refresh(g.decision.id, f"init-bridge-refresh-{uuid4()}", 1)
        selected = next(item for item in refreshed if item.project_workspace_id == g.project.id)
        assert selected.eligibility_status == READY_ACTIVATION
        assert selected.can_activate and not selected.can_initialize
        allowed, evidence = _authorize(g, for_activation=True)
        assert allowed and evidence == old_evidence
        assert g.project.status == "pending"
    finally:
        g.db.rollback()
