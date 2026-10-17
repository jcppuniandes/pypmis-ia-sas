"""Real current lifecycle and fail-closed negatives after canonical activation.

The positive fixture reuses the current modern source journey and normal
Class B/FID/07L/05C commands. Negative tampering remains unflushed in the private
pytest-owned SQLite invocation; it never touches the persistent UAT chain.
"""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from tests.helpers.strategic_legacy_fid_current_fixture import prepare_current_fid_sources
from tests.strategic_capital_owner_full_e2e_current import finish_investment_lifecycle, service

from app.database.session import SessionLocal
from app.domain.models import SecurityEvent
from app.main import app
from app.modules.investment_decision.models import InvestmentDecision
from app.modules.investment_decision.service import InvestmentDecisionService
from app.modules.investment_gate_preparation.models import InvestmentGatePreparation
from app.modules.portfolio_convergence.models import PortfolioScenarioConvergence
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService
from app.modules.post_fid_governance.models import PostFIDProjectEligibility
from app.modules.post_fid_governance.service import NO_REACTIVATION, PostFIDGovernanceService
from app.modules.project_workspace_initialization.models import ProjectWorkspaceInitialization


def stored(record):
    return deepcopy({column.name: getattr(record, column.name) for column in record.__table__.columns})


@pytest.fixture(scope="module")
def governed():
    with TestClient(app), SessionLocal() as db:
        prepared = prepare_current_fid_sources(db)
        setup, project = prepared["setup"], prepared["project"]
        events = []
        finish_investment_lifecycle(
            db,
            setup,
            prepared["configs"],
            project,
            prepared["portfolio"],
            {field: getattr(project, field) for field in ("id", "code", "external_key", "record_code")},
            lambda stage, data: events.append({"stage": stage, "data": data}),
            lambda _stage: None,
        )
        tail = events[-1]["data"]
        assert tail["activated"]["state"] == "ACTIVATED"
        assert tail["post_fid_final"][0]["eligibility_status"] == NO_REACTIVATION
        decision = db.get(InvestmentDecision, next(item["data"]["id"] for item in events if item["stage"] == "A30_FID"))
        preparation = db.get(InvestmentGatePreparation, decision.investment_gate_preparation_id)
        certificate = db.scalar(
            select(PostFIDProjectEligibility).where(
                PostFIDProjectEligibility.investment_decision_id == decision.id,
                PostFIDProjectEligibility.eligibility_status == "READY_FOR_PROJECT_WORKSPACE_ACTIVATION",
            )
        )
        initialization = db.scalar(
            select(ProjectWorkspaceInitialization).where(ProjectWorkspaceInitialization.workspace_id == project.id)
        )
        activation_event = db.scalar(
            select(SecurityEvent).where(
                SecurityEvent.tenant_id == setup["tenant_id"],
                SecurityEvent.target_id == project.id,
                SecurityEvent.event_type == "project_workspace.activated",
            )
        )
        fid = service(InvestmentDecisionService, db, setup["tenant_id"], setup["actor_id"], "investment_decision.read")
        db.autoflush = False
        Path("/artifacts/current-lifecycle-checkpoints.json").write_text(json.dumps(events, indent=2, default=str))
        yield SimpleNamespace(
            db=db,
            setup=setup,
            project=project,
            decision=decision,
            preparation=preparation,
            certificate=certificate,
            initialization=initialization,
            activation_event=activation_event,
            fid=fid,
            convergence=db.get(PortfolioScenarioConvergence, preparation.source_convergence_id),
        )
        db.rollback()


def test_real_current_chain_remains_current_after_separate_canonical_activation(governed):
    g = governed
    before = {
        name: stored(getattr(g, name))
        for name in ("project", "decision", "preparation", "certificate", "initialization", "convergence")
    }
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.lstrip().split()[0].upper())

    event.listen(g.db.bind, "before_cursor_execute", capture)
    try:
        g.fid._assert_current(g.decision)
        post = PostFIDGovernanceService(g.db, g.setup["tenant_id"], g.setup["actor_id"], g.fid.context)
        applicable, current, blockers, _warnings = post._decision_validity(g.decision, post._published_configuration())
        assert applicable and current and not blockers
    finally:
        event.remove(g.db.bind, "before_cursor_execute", capture)
    assert not {"INSERT", "UPDATE", "DELETE"}.intersection(statements)
    assert g.project.status == "active" and g.initialization.state == "ACTIVATED"
    assert g.initialization.started_by_user_id != g.initialization.activated_by_user_id
    assert before == {name: stored(getattr(g, name)) for name in before}
    queue = PortfolioEvaluationService(g.db, g.setup["tenant_id"], g.setup["actor_id"], g.fid.context).evaluation_queue(
        g.setup["portfolio_id"]
    )
    assert len(queue) == 1 and not queue[0].eligible
    assert queue[0].blocking_issues == ["PROJECT_STATUS_PENDING_REQUIRED"]


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("initialization", "state", "READY_FOR_ACTIVATION"),
        ("initialization", "started_by_user_id", None),
        ("initialization", "activated_at", None),
        ("initialization", "ready_at", None),
        ("initialization", "validation_hash", "0" * 64),
        ("initialization", "checklist_hash", "0" * 64),
        ("certificate", "source_current", False),
        ("certificate", "eligible_for_activation", False),
        ("certificate", "blockers_json", ["OPEN_ACTIVATION_BLOCKERS"]),
        ("certificate", "project_workspace_id", -1),
        ("certificate", "investment_decision_id", -1),
        ("certificate", "condition_snapshot_hash", "0" * 64),
        ("certificate", "configuration_hash", "0" * 64),
        ("certificate", "fid_decision_hash", "0" * 64),
        ("certificate", "decision_package_hash", "0" * 64),
        ("certificate", "eligibility_hash", "0" * 64),
        ("decision", "is_fid", False),
        ("decision", "decision_hash", "0" * 64),
        ("decision", "source_package_hash", "0" * 64),
        ("decision", "conditions_json", [{"code": "NEW", "blocking_for_activation": True}]),
        ("decision", "decision_scope_hash", "0" * 64),
        ("decision", "configuration_hash", "0" * 64),
        ("preparation", "profile_hash", "0" * 64),
        ("convergence", "convergence_source_hash", "0" * 64),
        ("convergence", "recommendation_hash", "0" * 64),
        ("convergence", "source_analysis_hash", "0" * 64),
        ("convergence", "budget_planning_hash", "0" * 64),
        ("convergence", "resource_planning_hash", "0" * 64),
    ],
)
def test_tampered_materials_certificates_or_authority_fail_closed(governed, monkeypatch, target, field, value):
    g = governed
    with monkeypatch.context() as patch:
        patch.setattr(getattr(g, target), field, value)
        with pytest.raises(HTTPException):
            g.fid._assert_current(g.decision)
    g.db.rollback()


def test_same_actor_initialization_activation_is_not_canonical(governed, monkeypatch):
    g = governed
    with monkeypatch.context() as patch:
        patch.setattr(g.initialization, "activated_by_user_id", g.initialization.started_by_user_id)
        with pytest.raises(HTTPException):
            g.fid._assert_current(g.decision)
    g.db.rollback()


def test_post_fid_evaluator_is_not_an_additional_activation_sod_restriction(governed, monkeypatch):
    g = governed
    with monkeypatch.context() as patch:
        patch.setattr(g.certificate, "evaluated_by", g.initialization.activated_by_user_id)
        g.fid._assert_current(g.decision)
    g.db.rollback()


@pytest.mark.parametrize("validator", ["absent", "activator"])
def test_no_extra_sod_or_separate_validate_requirement_is_added(governed, monkeypatch, validator):
    g = governed
    with monkeypatch.context() as patch:
        patch.setattr(
            g.initialization,
            "validated_by_user_id",
            None if validator == "absent" else g.initialization.activated_by_user_id,
        )
        g.fid._assert_current(g.decision)
    g.db.rollback()


def test_actual_last_modifier_cannot_be_the_activator(governed, monkeypatch):
    g = governed
    with monkeypatch.context() as patch:
        patch.setattr(g.initialization, "last_modified_by_user_id", g.initialization.activated_by_user_id)
        with pytest.raises(HTTPException):
            g.fid._assert_current(g.decision)
    g.db.rollback()


def test_manual_active_status_without_matching_activation_event_is_not_authority(governed, monkeypatch):
    g = governed
    with monkeypatch.context() as patch:
        patch.setattr(g.activation_event, "metadata_json", {"workspace_id": g.project.id, "initialization_id": -1})
        with pytest.raises(HTTPException):
            g.fid._assert_current(g.decision)
    g.db.rollback()


@pytest.mark.parametrize(("target", "field"), [("project", "version"), ("initialization", "revision_version")])
def test_any_later_version_change_cannot_be_assumed_to_be_only_activation(governed, monkeypatch, target, field):
    g = governed
    record = getattr(g, target)
    with monkeypatch.context() as patch:
        patch.setattr(record, field, getattr(record, field) + 1)
        with pytest.raises(HTTPException):
            g.fid._assert_current(g.decision)
    g.db.rollback()


def test_an_obsolete_decision_round_is_not_resurrected(governed):
    g = governed
    # Adversarial read-only predecessor: the actual later DECIDED row remains
    # the persisted authority. No terminal state is inserted or rewritten.
    predecessor = SimpleNamespace(**stored(g.decision))
    predecessor.id = -1
    predecessor.decision_round = g.decision.decision_round - 1
    with pytest.raises(HTTPException):
        g.fid._assert_current(predecessor)
