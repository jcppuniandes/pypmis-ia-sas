"""Final UAT: legacy ADMIN commands cannot bypass Project lifecycle authority.

These denial tests use a non-persistent session double: no operational DB access,
seed, startup, DML or migration is needed to reproduce the command boundary.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.deps import get_tenant_id, get_user_id
from app.api.v1.routers import admin_configuration as legacy
from app.database.session import get_db
from app.domain.schemas import EnterpriseWorkspaceCreate, EnterpriseWorkspaceUpdate
from app.modules.enterprise_structure.schemas import EnterpriseNodeCreate, EnterpriseNodeUpdate
from app.modules.enterprise_structure.service import EnterpriseStructureService
from app.modules.project_creation.entrypoint_guard import (
    require_governed_project_activation,
    require_non_project_admin_creation,
)


@pytest.mark.parametrize("type_code", ["project", "PROJECT", "  ProJect  "])
def test_legacy_admin_cannot_create_project_before_any_dml(monkeypatch, type_code):
    db = Mock()
    # If the command reaches add(), it has crossed the governed boundary.
    db.add.side_effect = AssertionError("PROJECT_DML_REACHED")
    monkeypatch.setattr(legacy, "require_tenant_configurator", lambda *_: SimpleNamespace(id=1))
    monkeypatch.setattr(legacy, "_published_configuration", lambda *_: SimpleNamespace(code="project", content_json={}))
    monkeypatch.setattr(legacy, "_next_workspace_record_code", lambda *_: "UAT-001")

    with pytest.raises(HTTPException) as caught:
        legacy.create_workspace(
            EnterpriseWorkspaceCreate(code="uat-project", name="UAT Project", workspace_type_code=type_code),
            db=db,
            tenant_id=1,
            user_id=1,
        )

    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "PROJECT_CREATION_PROCESS_REQUIRED"
    assert caught.value.detail["dedicated_api"] == "/api/v1/project-creation-requests"
    for operation in ("add", "flush", "commit", "execute"):
        getattr(db, operation).assert_not_called()


def test_legacy_admin_checks_resolved_project_taxonomy_before_any_dml(monkeypatch):
    """Check the published type too; a resolver alias must not evade the guard."""
    db = Mock()
    db.add.side_effect = AssertionError("PROJECT_DML_REACHED")
    monkeypatch.setattr(legacy, "require_tenant_configurator", lambda *_: SimpleNamespace(id=1))
    monkeypatch.setattr(legacy, "_published_configuration", lambda *_: SimpleNamespace(code="PROJECT", content_json={}))
    monkeypatch.setattr(legacy, "_next_workspace_record_code", lambda *_: "UAT-001")

    with pytest.raises(HTTPException) as caught:
        legacy.create_workspace(
            EnterpriseWorkspaceCreate(code="uat-project", name="UAT Project", workspace_type_code="resolved-alias"),
            db=db,
            tenant_id=1,
            user_id=1,
        )
    assert caught.value.detail["code"] == "PROJECT_CREATION_PROCESS_REQUIRED"
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("type_code", ["project", "PROJECT", "  ProJect  ", "resolved-alias"])
def test_enterprise_node_creation_cannot_materialize_project(monkeypatch, type_code):
    db = Mock()
    service = EnterpriseStructureService(db, tenant_id=1, actor_id=1)
    monkeypatch.setattr(service, "_ensure_core_editable", lambda: None)
    monkeypatch.setattr(service.repository, "workspace_by_code", lambda _: None)
    monkeypatch.setattr(service, "_published_type", lambda _: SimpleNamespace(code="project", content_json={}))
    with pytest.raises(HTTPException) as caught:
        service.create_node(EnterpriseNodeCreate(code="uat-project", name="UAT Project", workspace_type_code=type_code))
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "PROJECT_CREATION_PROCESS_REQUIRED"
    for operation in ("add", "flush", "commit", "execute"):
        getattr(db, operation).assert_not_called()


def test_enterprise_admin_cannot_activate_existing_project(monkeypatch):
    db = Mock()
    service = EnterpriseStructureService(db, tenant_id=1, actor_id=1)
    workspace = SimpleNamespace(id=9, workspace_type_code="project", status="pending_initialization", version=2)
    monkeypatch.setattr(service, "_ensure_core_editable", lambda: None)
    monkeypatch.setattr(service, "_workspace", lambda _: workspace)
    with pytest.raises(HTTPException) as caught:
        service.update_node(9, EnterpriseNodeUpdate(status="active", expected_version=2))
    assert caught.value.detail["code"] == "PROJECT_WORKSPACE_LIFECYCLE_REQUIRED"
    assert workspace.status == "pending_initialization"
    db.commit.assert_not_called()


@pytest.mark.parametrize(
    "type_code", ["enterprise", "business-unit", "portfolio", "program", "facility", "property", "warehouse"]
)
def test_project_guard_preserves_other_workspace_types(type_code):
    require_non_project_admin_creation(type_code)


def test_legacy_admin_http_project_creation_returns_governed_conflict(monkeypatch):
    """Exercise JSON routing without app startup, a seed, or a real DB."""
    db = Mock()
    monkeypatch.setattr(legacy, "require_tenant_configurator", lambda *_: SimpleNamespace(id=1))
    isolated_app = FastAPI()
    isolated_app.include_router(legacy.router, prefix="/api/v1")
    isolated_app.dependency_overrides[get_db] = lambda: db
    isolated_app.dependency_overrides[get_tenant_id] = lambda: 1
    isolated_app.dependency_overrides[get_user_id] = lambda: 1
    with TestClient(isolated_app) as client:
        response = client.post(
            "/api/v1/admin-configuration/workspaces",
            json={"code": "uat-project", "name": "UAT Project", "workspace_type_code": "PROJECT"},
        )
    assert response.status_code == 409
    assert response.json()["detail"]["dedicated_api"] == "/api/v1/project-creation-requests"
    for operation in ("add", "flush", "commit", "execute"):
        getattr(db, operation).assert_not_called()


@pytest.mark.parametrize("stored_type", ["project", "PROJECT", "  Project "])
def test_legacy_admin_cannot_activate_existing_project(monkeypatch, stored_type):
    db = Mock()
    workspace = SimpleNamespace(id=9, workspace_type_code=stored_type, status="initialized", version=2)
    monkeypatch.setattr(legacy, "require_tenant_configurator", lambda *_: SimpleNamespace(id=1))
    monkeypatch.setattr(legacy, "_workspace", lambda *_: workspace)
    monkeypatch.setattr(legacy, "_event", Mock())

    with pytest.raises(HTTPException) as caught:
        legacy.update_workspace(
            9, EnterpriseWorkspaceUpdate(status="active", expected_version=2), db=db, tenant_id=1, user_id=1
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "PROJECT_WORKSPACE_LIFECYCLE_REQUIRED"
    assert workspace.status == "initialized"
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("requested", ["inactive", "archived", "pending", "initialized"])
@pytest.mark.parametrize("entrypoint", ["legacy", "enterprise"])
def test_admin_cannot_change_project_lifecycle_in_either_direction(monkeypatch, requested, entrypoint):
    db = Mock()
    workspace = SimpleNamespace(id=9, workspace_type_code="project", status="active", version=2)
    if entrypoint == "legacy":
        monkeypatch.setattr(legacy, "require_tenant_configurator", lambda *_: SimpleNamespace(id=1))
        monkeypatch.setattr(legacy, "_workspace", lambda *_: workspace)

        def command():
            return legacy.update_workspace(
                9, EnterpriseWorkspaceUpdate(status=requested, expected_version=2), db=db, tenant_id=1, user_id=1
            )
    else:
        service = EnterpriseStructureService(db, tenant_id=1, actor_id=1)
        monkeypatch.setattr(service, "_ensure_core_editable", lambda: None)
        monkeypatch.setattr(service, "_workspace", lambda _: workspace)

        def command():
            return service.update_node(9, EnterpriseNodeUpdate(status=requested, expected_version=2))

    with pytest.raises(HTTPException) as caught:
        command()
    assert caught.value.status_code == 409
    assert caught.value.detail["dedicated_api"] == "/api/v1/project-workspaces/9/initialization"
    assert workspace.status == "active"
    for operation in ("add", "flush", "commit", "execute"):
        getattr(db, operation).assert_not_called()


@pytest.mark.parametrize("requested", [None, "active", " ACTIVE "])
def test_project_same_status_or_omitted_status_is_not_a_lifecycle_change(requested):
    require_governed_project_activation("PROJECT", "active", requested, 9)


def test_enterprise_delete_cannot_archive_a_project(monkeypatch):
    db = Mock()
    service = EnterpriseStructureService(db, tenant_id=1, actor_id=1)
    workspace = SimpleNamespace(id=9, workspace_type_code="project", status="active", version=2)
    monkeypatch.setattr(service, "_ensure_core_editable", lambda: None)
    monkeypatch.setattr(service, "_workspace", lambda _: workspace)
    with pytest.raises(HTTPException) as caught:
        service.archive_node(9)
    assert caught.value.detail["code"] == "PROJECT_WORKSPACE_LIFECYCLE_REQUIRED"
    assert workspace.status == "active"
    db.commit.assert_not_called()
