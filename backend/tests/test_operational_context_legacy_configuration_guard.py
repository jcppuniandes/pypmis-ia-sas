"""Legacy tenant configuration cannot bypass granular O1A ADMIN policy commands."""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.operational_context_fixture import create_o1a_fixture

from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, ProjectMembership
from app.main import app
from app.modules.basic_data.service import _hash
from app.modules.operational_context.service import DEFAULT_PROFILE


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as instance:
        yield instance


@pytest.fixture
def fixture(client):
    with SessionLocal() as db:
        result = create_o1a_fixture(db)
        # This actor can pass the existing legacy tenant-configurator check, but
        # intentionally has no O1A organization ADMIN role/permission.
        db.add(
            ProjectMembership(
                tenant_id=result.tenant_id,
                project_id=result.legacy_project_id,
                user_id=result.users["unassigned"].id,
                role="Legacy Configurator",
                can_configure=True,
            )
        )
        db.commit()
        result.client, result.db = client, db
        response = client.post(
            "/api/v1/operational/admin/profiles",
            headers={**result.headers["admin"], "Idempotency-Key": f"guard-profile-{uuid4()}"},
            json={
                "code": f"guard-{uuid4().hex[:12]}",
                "name": "O1A policy authority guard",
                "content_json": deepcopy(DEFAULT_PROFILE),
            },
        )
        assert response.status_code == 201, response.text
        result.profile = response.json()
        yield result
        db.rollback()


def _snapshot(f):
    f.db.expire_all()
    rows = f.db.scalars(
        select(AdminConfiguration)
        .where(AdminConfiguration.tenant_id == f.tenant_id, AdminConfiguration.kind == "operational_profile")
        .order_by(AdminConfiguration.id)
    ).all()
    return _hash(
        [{column.name: getattr(row, column.name) for column in AdminConfiguration.__table__.columns} for row in rows]
    )


@pytest.mark.parametrize("command", ["create", "edit", "publish", "clone"])
def test_generic_admin_routes_cannot_bypass_operational_profile_governance(fixture, command):
    f = fixture
    if command == "clone":
        published = f.client.post(
            f"/api/v1/operational/admin/profiles/{f.profile['id']}/publish",
            headers={
                **f.headers["publisher"],
                "If-Match": f'"{f.profile["version"]}"',
                "Idempotency-Key": f"guard-publish-{uuid4()}",
            },
            json={"reason": "Independent authorized publication for isolated guard proof"},
        )
        assert published.status_code == 200, published.text
        f.profile = published.json()
    before = _snapshot(f)
    base = "/api/v1/admin-configuration/configurations"
    headers = f.headers["unassigned"]
    if command == "create":
        response = f.client.post(
            base,
            headers=headers,
            json={
                "kind": "operational_profile",
                "code": f"bypass-{uuid4().hex[:12]}",
                "name": "Forbidden generic creation",
                "content_json": deepcopy(DEFAULT_PROFILE),
            },
        )
    elif command == "edit":
        response = f.client.patch(
            f"{base}/{f.profile['id']}",
            headers=headers,
            json={"name": "Forbidden generic edit", "expected_version": f.profile["version"]},
        )
    else:
        response = f.client.post(f"{base}/{f.profile['id']}/{command}", headers=headers)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "GOVERNED_CONFIGURATION_API_REQUIRED"
    assert response.json()["detail"]["dedicated_api"] == "/api/v1/operational/admin/profiles"
    assert _snapshot(f) == before, "Rejected generic commands must not create/edit/publish policy revisions"


def test_legacy_configurator_cannot_edit_through_dedicated_operational_admin_api(fixture):
    f = fixture
    before = _snapshot(f)
    response = f.client.put(
        f"/api/v1/operational/admin/profiles/{f.profile['id']}",
        headers={
            **f.headers["unassigned"],
            "If-Match": f'"{f.profile["version"]}"',
            "Idempotency-Key": f"guard-denied-{uuid4()}",
        },
        json={"name": "Forbidden dedicated edit", "content_json": deepcopy(DEFAULT_PROFILE)},
    )
    assert response.status_code == 403, response.text
    assert _snapshot(f) == before
