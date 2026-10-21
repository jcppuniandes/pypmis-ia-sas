"""O1A Owner authorization with real current-source FID and activation commands.

This is an opt-in disposable PostgreSQL proof. Controlled Class B source
references are explicit UAT fixtures, not production evidence or human sign-off.
The default historical SQLite helper boundary remains unchanged.
"""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from tests.helpers.strategic_legacy_fid_current_fixture import prepare_current_fid_sources
from tests.operational_context_fixture import fixture_headers
from tests.strategic_capital_owner_full_e2e_current import finish_investment_lifecycle

from app.database.session import SessionLocal, engine
from app.domain.models import SecurityAccessAssignment, SecurityRole, UserAccount
from app.main import app
from app.modules.investment_decision.models import InvestmentDecision
from app.modules.operational_context.permissions import ensure_operational_permissions
from app.modules.post_fid_governance.models import PostFIDProjectEligibility
from app.modules.project_workspace_initialization.models import ProjectWorkspaceInitialization


@pytest.fixture(scope="module", params=[False, True], ids=["owner-current-fid", "owner-open-commitment-condition"])
def governed_owner(request):
    if engine.dialect.name != "postgresql" or os.getenv("PYPMIS_O1A_FIXTURE") != "disposable-only":
        pytest.skip("Real Owner source journey requires explicitly disposable O1A PostgreSQL")
    assert engine.url.database == "o1a"
    condition_case = bool(request.param)
    with TestClient(app) as client, SessionLocal() as db:
        # Isolated test ID allocation keeps all governed fixtures away from the
        # protected runtime Project ID 14; no existing Project row is rewritten.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "SELECT setval('enterprise_workspaces_id_seq', GREATEST((SELECT last_value FROM enterprise_workspaces_id_seq), 1000), true)"
                )
            )
        prepared = prepare_current_fid_sources(db, isolated_o1a_postgres=True)
        setup, project = prepared["setup"], prepared["project"]
        assert project.id != 14
        stages = []
        conditions = (
            [
                {
                    "code": "O1A-COM-01",
                    "status": "OPEN",
                    "blocking_for_activation": False,
                    "blocking_for_commitment": True,
                    "description": "Controlled UAT condition: separate authority required before commitments.",
                }
            ]
            if condition_case
            else []
        )
        finish_investment_lifecycle(
            db,
            setup,
            prepared["configs"],
            project,
            prepared["portfolio"],
            {field: getattr(project, field) for field in ("id", "code", "external_key", "record_code")},
            lambda stage, data: stages.append({"stage": stage, "data": data}),
            lambda _stage: None,
            operational_conditions=conditions,
        )
        decision_id = next(item["data"]["id"] for item in stages if item["stage"] == "A30_FID")
        decision = db.get(InvestmentDecision, decision_id)
        initialization = db.scalar(
            select(ProjectWorkspaceInitialization).where(ProjectWorkspaceInitialization.workspace_id == project.id)
        )
        certificate = db.scalar(
            select(PostFIDProjectEligibility)
            .where(
                PostFIDProjectEligibility.tenant_id == setup["tenant_id"],
                PostFIDProjectEligibility.project_workspace_id == project.id,
            )
            .order_by(PostFIDProjectEligibility.id.desc())
        )
        assert project.status == "active" and initialization.state == "ACTIVATED"
        assert initialization.started_by_user_id != initialization.activated_by_user_id
        assert decision.status == "DECIDED" and decision.is_fid and decision.full_funds_authorized
        assert certificate.source_current
        ensure_operational_permissions(db, setup["tenant_id"], setup["admin_author_id"])
        role = db.scalar(
            select(SecurityRole).where(
                SecurityRole.tenant_id == setup["tenant_id"], SecurityRole.code == "executive_viewer"
            )
        )
        reader = db.get(UserAccount, setup["actor_id"])
        db.add(
            SecurityAccessAssignment(
                tenant_id=setup["tenant_id"],
                subject_type="user",
                user_id=reader.id,
                role_id=role.id,
                scope_type="workspace",
                workspace_id=project.id,
                status="active",
                granted_by_user_id=setup["admin_author_id"],
            )
        )
        db.commit()
        headers = fixture_headers(reader)
        statements = []

        def capture(_connection, _cursor, statement, _parameters, _context, _many):
            statements.append(statement.lstrip().split()[0].upper())

        event.listen(engine, "before_cursor_execute", capture)
        try:
            response = client.get(f"/api/v1/operational/projects/{project.id}/authorization", headers=headers)
            assert response.status_code == 200, response.text
            result = response.json()
            context = client.get(f"/api/v1/operational/projects/{project.id}/context", headers=headers)
            assert context.status_code == 200, context.text
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        evidence = {
            "engine": "PostgreSQL",
            "fixture": "DISPOSABLE_O1A_GOVERNED_CURRENT_SOURCE_JOURNEY",
            "evidence_classification": "UAT_CONTROLLED_CLASS_B_NOT_PRODUCTION_ACCEPTANCE",
            "tenant_id": setup["tenant_id"],
            "project_workspace_id": project.id,
            "project_external_key": project.external_key,
            "fid_decision_id": decision.id,
            "fid_hash": decision.decision_hash,
            "post_fid_eligibility_id": certificate.id,
            "initialization_id": initialization.id,
            "initializer": initialization.started_by_user_id,
            "activator": initialization.activated_by_user_id,
            "condition_case": condition_case,
            "authorization": result,
            "business_writes_in_new_authorization_and_context_get": sorted(
                {"INSERT", "UPDATE", "DELETE"} & set(statements)
            ),
            "stages": [item["stage"] for item in stages],
            "human_signoff": "PENDING_NOT_ASSUMED",
        }
        destination = Path("/artifacts") / f"owner-authorization-{'commitment' if condition_case else 'current'}.json"
        destination.write_text(json.dumps(evidence, indent=2, default=str) + "\n", encoding="utf-8")
        yield {
            "decision": result,
            "context": context.json(),
            "condition_case": condition_case,
            "statements": statements,
        }
        db.rollback()


def test_owner_operational_entry_requires_genuine_current_fid_and_canonical_activation(governed_owner):
    g = governed_owner
    assert g["decision"]["route"] == "CAPITAL_OWNER"
    assert g["decision"]["authorized_for_operational_context"], g["decision"]
    assert g["decision"]["authority_source"] == "GATE07K_FID_AND_GATE07L"
    assert g["decision"]["authority_reference"] and g["decision"]["source_hash"]
    assert g["context"]["activation_state"] == "ACTIVE"


def test_owner_active_never_defaults_commitment_authority_and_keeps_conditions(governed_owner):
    g = governed_owner
    assert not g["decision"]["commitment_authorized"]
    assert "ACTIVE_IS_NOT_COMMITMENT_AUTHORITY" in g["decision"]["warnings"]
    conditions = g["decision"]["commitment_conditions"]
    if g["condition_case"]:
        assert any(row.get("code") == "O1A-COM-01" and row.get("blocking_for_commitment") for row in conditions)
    else:
        assert conditions == []
    assert not {"INSERT", "UPDATE", "DELETE"} & set(g["statements"])
