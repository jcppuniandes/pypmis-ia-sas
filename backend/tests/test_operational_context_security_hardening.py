"""Independent policy publication must exclude the actual current author."""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from tests.operational_context_fixture import create_o1a_fixture

from app.database.session import SessionLocal
from app.domain.models import (
    AdminConfiguration,
    ProjectMembership,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityRole,
)
from app.main import app
from app.modules.operational_context.models import OperationalContextCommand
from app.modules.operational_context.service import DEFAULT_PROFILE

ROOT = "/api/v1/operational/admin/profiles"
REASON = {"reason": "Independent O1A policy security acceptance in disposable fixture"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as instance:
        yield instance


@pytest.fixture
def fixture(client):
    with SessionLocal() as db:
        result = create_o1a_fixture(db)
        role = db.scalar(
            select(SecurityRole).where(
                SecurityRole.tenant_id == result.tenant_id, SecurityRole.code == "organization_admin"
            )
        )
        db.add(
            SecurityAccessAssignment(
                tenant_id=result.tenant_id,
                subject_type="user",
                user_id=result.users["second_manager"].id,
                role_id=role.id,
                scope_type="organization",
                status="active",
                granted_by_user_id=result.users["admin"].id,
            )
        )
        db.commit()
        result.client, result.db = client, db
        yield result
        db.rollback()


def request(fixture, method, path="", *, actor="admin", payload=None, version=None):
    headers = {**fixture.headers[actor], "Idempotency-Key": f"o1a-policy-security-{uuid4()}"}
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    return fixture.client.request(method, ROOT + path, headers=headers, json=payload)


def create(fixture, *, sod=True):
    content = deepcopy(DEFAULT_PROFILE)
    content["separation_of_duties"]["author_cannot_publish"] = sod
    response = request(
        fixture,
        "POST",
        payload={
            "code": f"policy-sod-{uuid4().hex[:12]}",
            "name": "Independent current policy author",
            "content_json": content,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_current_policy_editor_cannot_self_publish_and_independent_actor_can(fixture):
    f = fixture
    row = create(f)
    content = deepcopy(row["content_json"])
    content["lookahead_default_days"] = 28
    changed = request(
        f,
        "PUT",
        f"/{row['id']}",
        actor="publisher",
        version=row["version"],
        payload={"name": row["name"], "content_json": content},
    )
    assert changed.status_code == 200, changed.text
    current = changed.json()
    assert current["version"] == row["version"] + 1
    for actor in ("publisher", "admin"):
        rejected = request(f, "POST", f"/{row['id']}/publish", actor=actor, version=current["version"], payload=REASON)
        assert rejected.status_code == 403, rejected.text
        assert rejected.json()["detail"]["code"] == "OPERATIONAL_PROFILE_PUBLICATION_SOD"
    f.db.expire_all()
    assert f.db.get(AdminConfiguration, row["id"]).status == "draft"
    receipt = f.db.scalar(
        select(OperationalContextCommand).where(
            OperationalContextCommand.tenant_id == f.tenant_id,
            OperationalContextCommand.command_type == "profile.update",
            OperationalContextCommand.result_json["id"].as_integer() == row["id"],
        )
    )
    assert receipt.actor_id == f.users["publisher"].id
    assert receipt.result_json["version"] == current["version"]
    event = f.db.scalar(
        select(SecurityEvent).where(
            SecurityEvent.tenant_id == f.tenant_id,
            SecurityEvent.target_id == row["id"],
            SecurityEvent.event_type == "operational.profile.updated",
        )
    )
    assert event.metadata_json["version"] == current["version"]
    assert event.metadata_json["content_hash"] == current["content_hash"]
    published = request(
        f, "POST", f"/{row['id']}/publish", actor="second_manager", version=current["version"], payload=REASON
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"


def test_current_profile_editor_provenance_fails_closed_when_version_has_no_receipt(fixture):
    f = fixture
    row = create(f)
    # Explicit isolated corruption case, not a real policy workflow or a fixture
    # bypass used as positive acceptance evidence.
    f.db.execute(text("UPDATE admin_configurations SET version=version+1 WHERE id=:id"), {"id": row["id"]})
    f.db.commit()
    rejected = request(
        f, "POST", f"/{row['id']}/publish", actor="publisher", version=row["version"] + 1, payload=REASON
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"]["code"] == "OPERATIONAL_PROFILE_EDITOR_PROVENANCE_REQUIRED"
    f.db.expire_all()
    assert f.db.get(AdminConfiguration, row["id"]).status == "draft"


def test_explicitly_disabled_publication_sod_preserves_configured_policy_behavior(fixture):
    f = fixture
    row = create(f, sod=False)
    published = request(f, "POST", f"/{row['id']}/publish", version=row["version"], payload=REASON)
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"


def test_generic_overview_excludes_operational_profiles_without_bypassing_dedicated_read_permission(fixture):
    f = fixture
    draft = create(f)
    published = create(f)
    response = request(
        f, "POST", f"/{published['id']}/publish", actor="publisher", version=published["version"], payload=REASON
    )
    assert response.status_code == 200, response.text
    f.db.add(
        ProjectMembership(
            tenant_id=f.tenant_id,
            project_id=f.legacy_project_id,
            user_id=f.users["unassigned"].id,
            role="Legacy Configurator",
            can_configure=True,
        )
    )
    f.db.commit()
    overview = f.client.get("/api/v1/admin-configuration/overview", headers=f.headers["unassigned"])
    assert overview.status_code == 200, overview.text
    assert overview.json()["configurations"], "Existing generic configuration remains available"
    assert all(row["kind"] != "operational_profile" for row in overview.json()["configurations"])
    assert not {draft["id"], published["id"]} & {row["id"] for row in overview.json()["configurations"]}
    dedicated = f.client.get(ROOT, headers=f.headers["unassigned"])
    assert dedicated.status_code == 403, dedicated.text
    authorized = f.client.get(ROOT, headers=f.headers["admin"])
    assert authorized.status_code == 200, authorized.text
    assert {row["id"] for row in authorized.json()["items"]} == {draft["id"], published["id"]}
    # An operator may still read the applicable PUBLISHED revision, not ADMIN
    # draft/history configuration, through its canonical scoped context.
    context = f.client.get(
        f"/api/v1/operational/projects/{f.project_workspace_id}/context", headers=f.headers["manager"]
    )
    assert context.status_code == 200, context.text
    assert context.json()["operational_profile"]["id"] == published["id"]
    assert "admin.configure" not in context.json()["allowed_actions"]


@pytest.mark.parametrize("change", ["owner_to_direct", "source_authorization", "legacy_reference", "remove_namespace"])
def test_generic_defaults_cannot_rewrite_canonical_project_authority(fixture, change):
    f = fixture
    f.db.add(
        ProjectMembership(
            tenant_id=f.tenant_id,
            project_id=f.legacy_project_id,
            user_id=f.users["unassigned"].id,
            role="Legacy Configurator",
            can_configure=True,
        )
    )
    f.db.commit()
    workspace = f.workspaces["owner" if change == "owner_to_direct" else "direct"]
    original = deepcopy(workspace.defaults_json)
    version = workspace.version
    values = deepcopy(original)
    if change == "owner_to_direct":
        values["_project"] = {
            "governance_model": "DIRECT_INTERNAL",
            "project_type": "CONSTRUCTION",
            "source_snapshot": {
                "authorization_approved": True,
                "authorization_reference": "FORGED-REFERENCE",
                "sponsor": "Forged Sponsor",
            },
        }
    elif change == "source_authorization":
        values["_project"]["source_snapshot"]["authorization_reference"] = "FORGED-REFERENCE"
    elif change == "legacy_reference":
        values["_project"]["operational_project_id"] = f.legacy_project_id
    else:
        values["_project"] = None
    rejected = f.client.put(
        f"/api/v1/admin-configuration/workspaces/{workspace.id}/defaults",
        headers=f.headers["unassigned"],
        json={"expected_version": version, "values": values},
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["detail"]["code"] == "PROJECT_WORKSPACE_METADATA_RESERVED"
    f.db.expire_all()
    assert workspace.defaults_json == original and workspace.version == version
    authorization = f.client.get(
        f"/api/v1/operational/projects/{workspace.id}/authorization", headers=f.headers["admin"]
    )
    assert authorization.status_code == 200, authorization.text
    assert authorization.json()["route"] == original["_project"]["governance_model"]
    if change == "owner_to_direct":
        assert not authorization.json()["authorized_for_operational_context"]


def test_generic_unrelated_defaults_preserve_reserved_project_metadata_when_omitted(fixture):
    f = fixture
    f.db.add(
        ProjectMembership(
            tenant_id=f.tenant_id,
            project_id=f.legacy_project_id,
            user_id=f.users["unassigned"].id,
            role="Legacy Configurator",
            can_configure=True,
        )
    )
    f.db.commit()
    workspace = f.workspaces["direct"]
    original = deepcopy(workspace.defaults_json["_project"])
    version = workspace.version
    response = f.client.put(
        f"/api/v1/admin-configuration/workspaces/{workspace.id}/defaults",
        headers=f.headers["unassigned"],
        json={"expected_version": version, "values": {"currency": "COP", "timezone": "America/Bogota"}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["defaults_json"]["_project"] == original
    assert response.json()["defaults_json"]["currency"] == "COP"
    assert response.json()["version"] == version + 1
    # The generic PATCH schema has no live defaults/Project-source field. Extra
    # JSON cannot create an alternate metadata mutation path.
    patch = f.client.patch(
        f"/api/v1/admin-configuration/workspaces/{workspace.id}",
        headers=f.headers["unassigned"],
        json={"expected_version": version + 1, "defaults_json": {"_project": {"governance_model": "CAPITAL_OWNER"}}},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["defaults_json"]["_project"] == original
