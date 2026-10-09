"""Legacy tenant configuration cannot bypass Wave 2B governed policy APIs."""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from tests.test_capital_allocation_wave2a import _token_headers

from app.api.v1.routers.admin_configuration import router as legacy_router
from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, SecurityEvent, UserAccount
from app.main import app
from app.modules.basic_data.service import DEFAULT_CONFIGURATION as BASIC_POLICY
from app.modules.risk_governance.service import DEFAULT_CONFIGURATION as RISK_POLICY

KINDS = (
    ("risk_governance_policy", "/api/v1/risk-governance/admin/configurations", RISK_POLICY),
    ("basic_data_readiness_configuration", "/api/v1/basic-data/admin/configurations", BASIC_POLICY),
)
BASE = "/api/v1/admin-configuration/configurations"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as started:
        yield started


def _admin(db):
    admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
    assert admin is not None
    return admin, _token_headers(admin)


def _rejected(response, kind, dedicated_api):
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "GOVERNED_CONFIGURATION_API_REQUIRED"
    assert detail["configuration_kind"] == kind and detail["dedicated_api"] == dedicated_api


@pytest.mark.parametrize("kind,dedicated_api,policy", KINDS)
def test_wave2b_legacy_clone_patch_publish_never_mutate_governed_policies_in_any_state(
    client, kind, dedicated_api, policy
):
    with SessionLocal() as db:
        admin, headers = _admin(db)
        for state in ("draft", "published", "archived"):
            record = AdminConfiguration(
                tenant_id=admin.tenant_id,
                kind=kind,
                code=f"legacy-guard-{uuid4().hex}",
                name="Governed policy authority guard",
                description="HTTP security fixture",
                status=state,
                revision=1,
                version=1,
                content_json=deepcopy(policy),
                content_hash="a" * 64,
                created_by_user_id=admin.id,
                published_at=utc_now() if state != "draft" else None,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            before = {
                column.key: deepcopy(getattr(record, column.key)) for column in AdminConfiguration.__table__.columns
            }
            policy_count = db.scalar(select(func.count()).select_from(AdminConfiguration))
            audit_count = db.scalar(select(func.count()).select_from(SecurityEvent))
            writes = []

            def detect_write(_connection, _cursor, statement, _parameters, _context, _many, _writes=writes):
                if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                    _writes.append(statement)

            event.listen(db.get_bind(), "before_cursor_execute", detect_write)
            try:
                _rejected(client.post(f"{BASE}/{record.id}/clone", headers=headers), kind, dedicated_api)
                _rejected(
                    client.patch(
                        f"{BASE}/{record.id}",
                        headers=headers,
                        json={
                            "name": "Bypass attempt",
                            "content_json": {"separation_of_duties": {"preparer_cannot_publish": False}},
                            "expected_version": 1,
                        },
                    ),
                    kind,
                    dedicated_api,
                )
                # No If-Match or idempotency header is needed by the old route:
                # the route itself must reject entry to this governed aggregate.
                _rejected(client.post(f"{BASE}/{record.id}/publish", headers=headers), kind, dedicated_api)
            finally:
                event.remove(db.get_bind(), "before_cursor_execute", detect_write)
            db.expire(record)
            assert {
                column.key: getattr(record, column.key) for column in AdminConfiguration.__table__.columns
            } == before
            assert db.scalar(select(func.count()).select_from(AdminConfiguration)) == policy_count
            assert db.scalar(select(func.count()).select_from(SecurityEvent)) == audit_count
            assert writes == []


@pytest.mark.parametrize("kind,dedicated_api,policy", KINDS)
@pytest.mark.parametrize("normalized_alias", [False, True])
def test_wave2b_legacy_create_rejects_governed_kinds_and_normalized_aliases(
    client, kind, dedicated_api, policy, normalized_alias
):
    with SessionLocal() as db:
        admin, headers = _admin(db)
        before_count = db.scalar(select(func.count()).select_from(AdminConfiguration))
        response = client.post(
            BASE,
            headers=headers,
            json={
                "kind": f" {kind.upper().replace('_', '-')} " if normalized_alias else kind,
                "code": f"legacy-create-{uuid4().hex}",
                "name": "Attempted policy creation",
                "content_json": deepcopy(policy),
            },
        )
        _rejected(response, kind, dedicated_api)
        assert db.scalar(select(func.count()).select_from(AdminConfiguration)) == before_count


def test_wave2b_legacy_reads_and_catalog_lifecycle_remain_compatible(client):
    with SessionLocal() as db:
        _actor, headers = _admin(db)
        overview = client.get("/api/v1/admin-configuration/overview", headers=headers)
        assert overview.status_code == 200, overview.text
        assert {kind for kind, _api, _policy in KINDS} <= {row["kind"] for row in overview.json()["configurations"]}
        created = client.post(
            BASE,
            headers=headers,
            json={
                "kind": "catalog",
                "code": f"legacy-compatible-{uuid4().hex}",
                "name": "Legacy compatible catalog",
                "content_json": {"items": [{"code": "safe", "label": "Safe legacy catalog"}]},
            },
        )
        assert created.status_code == 201, created.text
        record_id = created.json()["id"]
        edited = client.patch(
            f"{BASE}/{record_id}", headers=headers, json={"name": "Edited catalog", "expected_version": 1}
        )
        assert edited.status_code == 200 and edited.json()["name"] == "Edited catalog", edited.text
        published = client.post(f"{BASE}/{record_id}/publish", headers=headers)
        assert published.status_code == 200 and published.json()["status"] == "published", published.text
        cloned = client.post(f"{BASE}/{record_id}/clone", headers=headers)
        assert cloned.status_code == 201 and cloned.json()["status"] == "draft", cloned.text
        assert cloned.json()["revision"] == 2


def test_wave2b_legacy_configuration_mutation_inventory_requires_guard_for_future_commands():
    mutating = {
        (method, route.path)
        for route in legacy_router.routes
        for method in route.methods
        if method in {"POST", "PUT", "PATCH", "DELETE"} and route.path.startswith("/admin-configuration/configurations")
    }
    assert mutating == {
        ("POST", "/admin-configuration/configurations"),
        ("PATCH", "/admin-configuration/configurations/{configuration_id}"),
        ("POST", "/admin-configuration/configurations/{configuration_id}/publish"),
        ("POST", "/admin-configuration/configurations/{configuration_id}/clone"),
    }, "Any future legacy policy mutation must preserve the dedicated authority guard."
