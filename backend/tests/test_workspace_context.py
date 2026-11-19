"""Gate 06D unit/integration acceptance coverage on the shared test database."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.domain.models import (
    AuthCredential,
    EnterpriseWorkspace,
    PermissionCatalog,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityRole,
    SecurityRolePermission,
    Tenant,
    UserAccount,
    WorkspaceModuleSetting,
)
from app.main import app
from app.modules.cost_foundation.permissions import ensure_cost_permissions
from app.modules.enterprise_structure.permissions import WORKSPACE_OPERATION_PERMISSIONS, ensure_enterprise_permissions
from app.modules.enterprise_structure.service import EnterpriseStructureService
from app.modules.schedule_foundation.permissions import ensure_schedule_permissions
from app.modules.scope_foundation.permissions import ensure_scope_permissions
from app.modules.workspace_context.models import RecentWorkspace

PROJECT_MODULES = {
    "scope-manager": ("Scope Manager", "scope_foundation.read"),
    "schedule-manager": ("Schedule Manager", "schedule_foundation.read"),
    "cost": ("Cost Manager", "cost.read"),
}


def _login(client: TestClient, email: str, tenant_slug: str = "demo-energy") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "1234", "tenant_slug": tenant_slug},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="module")
def gate06d():
    created_workspace_ids: list[int] = []
    with TestClient(app) as client:
        admin_headers = _login(client, "admin")
        with SessionLocal() as db:
            admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            assert admin is not None
            ensure_enterprise_permissions(db, admin.tenant_id, admin.id)
            EnterpriseStructureService(db, admin.tenant_id, admin.id).ensure_seed()
            # Provision the actual O1 module duties. The previous synthetic
            # workspace.cost.read grant no longer controls the Cost Manager route.
            ensure_scope_permissions(db, admin.tenant_id, admin.id)
            ensure_schedule_permissions(db, admin.tenant_id, admin.id)
            ensure_cost_permissions(db, admin.tenant_id, admin.id)
            restricted_role = SecurityRole(
                tenant_id=admin.tenant_id,
                code=f"gate06d_scope_{uuid4().hex[:8]}",
                name="Gate 06D Scope Only",
                description="Scoped navigation with Scope read and no Cost or Schedule read.",
                is_system=False,
                status="active",
            )
            db.add(restricted_role)
            db.flush()
            scope_only_keys = WORKSPACE_OPERATION_PERMISSIONS | {"scope_foundation.read"}
            scope_only_permissions = db.scalars(
                select(PermissionCatalog).where(PermissionCatalog.key.in_(scope_only_keys))
            ).all()
            assert {permission.key for permission in scope_only_permissions} == scope_only_keys
            for permission in scope_only_permissions:
                db.add(
                    SecurityRolePermission(
                        tenant_id=admin.tenant_id,
                        role_id=restricted_role.id,
                        permission_id=permission.id,
                        granted_by_user_id=admin.id,
                    )
                )
            roles = {
                item.code: item
                for item in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == admin.tenant_id)).all()
            }
            root = db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == admin.tenant_id,
                    EnterpriseWorkspace.parent_id.is_(None),
                )
            )
            assert root is not None
            users: dict[str, UserAccount] = {}
            emails: dict[str, str] = {}
            headers: dict[str, dict[str, str]] = {"admin": admin_headers}
            for name in ("full", "project", "scope_only", "facility", "no_access"):
                email = f"gate06d-{name}-{uuid4().hex[:6]}@demo.local"
                user = UserAccount(
                    tenant_id=admin.tenant_id,
                    email=email,
                    full_name=f"Gate 06D {name.title()}",
                    status="active",
                )
                db.add(user)
                db.flush()
                db.add(
                    AuthCredential(
                        tenant_id=admin.tenant_id,
                        user_id=user.id,
                        provider="local",
                        password_hash=hash_password("1234"),
                        is_active=True,
                    )
                )
                users[name] = user
                emails[name] = email
                headers[name] = {}

            workspaces: dict[str, EnterpriseWorkspace] = {}
            for index, (type_code, status) in enumerate(
                [
                    ("project", "active"),
                    ("property", "active"),
                    ("facility", "active"),
                    ("warehouse", "active"),
                    ("property", "pending"),
                    ("facility", "pending"),
                    ("warehouse", "pending"),
                    ("project", "archived"),
                ],
                start=1,
            ):
                key = f"{type_code}_{status}"
                if key in workspaces:
                    key = f"{key}_{index}"
                enabled = ["scope-manager", "schedule-manager", "cost-manager"] if type_code == "project" else []
                planned = {
                    "facility": ["Asset Manager", "Maintenance", "Space", "Utilities"],
                    "warehouse": ["Inventory", "Receipts", "Issues", "Transfers"],
                }.get(type_code, [])
                workspace = EnterpriseWorkspace(
                    tenant_id=admin.tenant_id,
                    parent_id=root.id,
                    workspace_type_code=type_code,
                    code=f"G06D-{type_code[:3].upper()}-{index}",
                    external_key=f"G06D-{uuid4().hex}",
                    record_code=f"{root.record_code}.G06D.{index:02d}",
                    name=f"Gate 06D {type_code.title()} {status.title()}",
                    status=status,
                    defaults_json={
                        "business_number": f"G06D-{type_code.upper()}-{index:03d}",
                        "template_code": f"G06D-{type_code.upper()}-TEMPLATE",
                        "template_revision": 1,
                        "responsible_user_id": users["facility"].id if type_code != "project" else users["project"].id,
                        "project_manager_user_id": users["project"].id if type_code == "project" else None,
                        "enabled_modules": enabled,
                        "planned_modules": planned,
                    },
                    sort_order=100 + index,
                    version=1,
                    created_by_user_id=admin.id,
                )
                db.add(workspace)
                db.flush()
                workspaces[key] = workspace
                created_workspace_ids.append(workspace.id)
                for module_key in enabled:
                    db.add(
                        WorkspaceModuleSetting(
                            tenant_id=admin.tenant_id,
                            workspace_id=workspace.id,
                            module_key=module_key,
                            enabled=True,
                            updated_by_user_id=admin.id,
                        )
                    )

            for user_name, role_code, workspace_keys in [
                ("full", "organization_admin", []),
                ("project", "project_manager", ["project_active"]),
                ("scope_only", restricted_role.code, ["project_active"]),
                ("facility", "physical_workspace_responsible", ["facility_active"]),
                ("no_access", "viewer", []),
            ]:
                if user_name == "full":
                    scope_type = "organization"
                    db.add(
                        SecurityAccessAssignment(
                            tenant_id=admin.tenant_id,
                            subject_type="user",
                            user_id=users[user_name].id,
                            role_id=roles[role_code].id,
                            scope_type=scope_type,
                            status="active",
                            granted_by_user_id=admin.id,
                        )
                    )
                for workspace_key in workspace_keys:
                    db.add(
                        SecurityAccessAssignment(
                            tenant_id=admin.tenant_id,
                            subject_type="user",
                            user_id=users[user_name].id,
                            role_id=roles[role_code].id,
                            scope_type="workspace",
                            workspace_id=workspaces[workspace_key].id,
                            status="active",
                            granted_by_user_id=admin.id,
                        )
                    )
            db.commit()
            ids = {key: item.id for key, item in workspaces.items()}
            tenant_id = admin.tenant_id
            cross_tenant = Tenant(name="Gate 06D Cross Tenant", slug=f"gate06d-{uuid4().hex[:8]}")
            db.add(cross_tenant)
            db.flush()
            cross_email = f"gate06d-cross-{uuid4().hex[:6]}@example.test"
            cross_user = UserAccount(
                tenant_id=cross_tenant.id,
                email=cross_email,
                full_name="Gate 06D Cross Tenant User",
                status="active",
            )
            db.add(cross_user)
            db.flush()
            db.add(
                AuthCredential(
                    tenant_id=cross_tenant.id,
                    user_id=cross_user.id,
                    provider="local",
                    password_hash=hash_password("1234"),
                    is_active=True,
                )
            )
            ensure_enterprise_permissions(db, cross_tenant.id, cross_user.id)
            db.commit()
            cross_slug = cross_tenant.slug
        for name, email in emails.items():
            headers[name] = _login(client, email)
        headers["cross_tenant"] = _login(client, cross_email, cross_slug)
        try:
            yield client, headers, ids, tenant_id
        finally:
            with SessionLocal() as db:
                db.query(SecurityEvent).filter(
                    SecurityEvent.tenant_id == tenant_id,
                    SecurityEvent.target_id.in_(created_workspace_ids or [-1]),
                ).delete(synchronize_session=False)
                db.query(RecentWorkspace).filter(
                    RecentWorkspace.tenant_id == tenant_id,
                    RecentWorkspace.workspace_id.in_(created_workspace_ids or [-1]),
                ).delete(synchronize_session=False)
                db.query(WorkspaceModuleSetting).filter(
                    WorkspaceModuleSetting.tenant_id == tenant_id,
                    WorkspaceModuleSetting.workspace_id.in_(created_workspace_ids or [-1]),
                ).delete(synchronize_session=False)
                db.query(SecurityAccessAssignment).filter(
                    SecurityAccessAssignment.tenant_id == tenant_id,
                    SecurityAccessAssignment.workspace_id.in_(created_workspace_ids or [-1]),
                ).delete(synchronize_session=False)
                db.query(EnterpriseWorkspace).filter(
                    EnterpriseWorkspace.tenant_id == tenant_id,
                    EnterpriseWorkspace.id.in_(created_workspace_ids or [-1]),
                ).delete(synchronize_session=False)
                db.commit()


def test_project_property_facility_and_warehouse_contexts(gate06d):
    client, headers, ids, _tenant_id = gate06d
    expected = {
        "project_active": {
            "Home",
            "Overview",
            "Project Definition / FEL",
            "Project Funding",
            "Investment Gate Preparation evidence linkage",
            "Operational Setup",
            "Scope Manager",
            "Schedule Manager",
            "Cost Manager",
            "Documents",
            "Reports",
        },
        "property_active": {"Home", "Overview", "Real Estate Information", "Documents", "Related Workspaces"},
        "facility_active": {"Home", "Overview", "Documents", "Asset Manager", "Maintenance", "Space", "Utilities"},
        "warehouse_active": {"Home", "Overview", "Documents", "Inventory", "Receipts", "Issues", "Transfers"},
    }
    for key, labels in expected.items():
        response = client.get(f"/api/v1/workspaces/{ids[key]}/context", headers=headers["full"])
        assert response.status_code == 200, response.text
        payload = response.json()
        assert {item["label"] for item in payload["navigator"]} == labels
        assert payload["identity"]["workspace_type"] == key.split("_")[0].upper()
        assert payload["breadcrumb"][-1]["workspace_id"] == ids[key]
        assert response.headers["etag"]
        if key == "project_active":
            modules = {item["code"]: item for item in payload["navigator"]}
            for code, (label, permission) in PROJECT_MODULES.items():
                assert modules[code]["label"] == label
                assert modules[code]["permission_key"] == permission
                assert modules[code]["route"] == f"/workspaces/{ids[key]}/{code}"


def test_open_home_recent_last_route_and_security_events(gate06d):
    client, headers, ids, tenant_id = gate06d
    workspace_id = ids["project_active"]
    opened = client.post(
        f"/api/v1/workspaces/{workspace_id}/open",
        headers=headers["project"],
        json={"route": f"/workspaces/{workspace_id}/home"},
    )
    assert opened.status_code == 200, opened.text
    home = client.get(f"/api/v1/workspaces/{workspace_id}/home", headers=headers["project"])
    assert home.status_code == 200
    assert home.json()["recent_documents"] == []
    route_endpoint = f"/api/v1/workspaces/{workspace_id}/last-route"
    scope_route = f"/workspaces/{workspace_id}/scope-manager"
    last_route = client.put(
        route_endpoint,
        headers=headers["project"],
        json={"route": scope_route},
    )
    assert last_route.status_code == 200
    assert last_route.json()["last_route"] == scope_route
    for retired in ("scope", "schedule"):
        stale_route = client.put(
            route_endpoint,
            headers=headers["project"],
            json={"route": f"/workspaces/{workspace_id}/{retired}"},
        )
        assert stale_route.status_code == 409
        assert stale_route.json()["detail"] == "WORKSPACE_ROUTE_NOT_OPERATIONAL"
    recent = client.get("/api/v1/workspaces/recent", headers=headers["project"])
    assert recent.status_code == 200
    assert recent.json()[0]["last_route"] == scope_route
    with SessionLocal() as db:
        persisted = db.scalar(
            select(RecentWorkspace).where(
                RecentWorkspace.tenant_id == tenant_id,
                RecentWorkspace.workspace_id == workspace_id,
            )
        )
        assert persisted is not None and persisted.last_route == scope_route
        event_types = set(
            db.scalars(select(SecurityEvent.event_type).where(SecurityEvent.target_id == workspace_id)).all()
        )
        assert {"workspace.opened", "workspace.context_loaded"} & event_types


def test_workspace_access_filtering_switching_and_no_leakage(gate06d):
    client, headers, ids, _tenant_id = gate06d
    project_id = ids["project_active"]
    facility_id = ids["facility_active"]
    assert client.get(f"/api/v1/workspaces/{project_id}/context", headers=headers["project"]).status_code == 200
    denied = client.get(f"/api/v1/workspaces/{facility_id}/context", headers=headers["project"])
    assert denied.status_code == 403
    assert client.get("/api/v1/workspaces", headers=headers["project"]).json()[0]["workspace_id"] == project_id
    switched = client.post(
        f"/api/v1/workspaces/{facility_id}/open",
        headers=headers["full"],
        json={"route": f"/workspaces/{facility_id}/home"},
    )
    assert switched.status_code == 200
    assert switched.json()["identity"]["workspace_id"] == facility_id
    assert switched.json()["identity"]["workspace_name"] != "Gate 06D Project Active"
    project_context = client.get(f"/api/v1/workspaces/{project_id}/context", headers=headers["full"]).json()
    assert project_context["etag"] != switched.json()["etag"]
    assert project_context["active_context"]["workspace_id"] == project_id


def test_module_permission_filtering_and_disabled_module_denial(gate06d):
    client, headers, ids, tenant_id = gate06d
    project_id = ids["project_active"]
    project_context = client.get(f"/api/v1/workspaces/{project_id}/context", headers=headers["scope_only"])
    assert project_context.status_code == 200
    visible = {item["code"] for item in project_context.json()["navigator"]}
    assert visible & PROJECT_MODULES.keys() == {"scope-manager"}
    modules = f"/api/v1/workspaces/{project_id}/modules"
    for code in ("cost", "schedule-manager"):
        denied = client.get(f"{modules}/{code}", headers=headers["scope_only"])
        assert denied.status_code == 403
        assert denied.json()["detail"] == "MODULE_DISABLED_OR_PERMISSION_DENIED"
    allowed = client.get(f"{modules}/scope-manager", headers=headers["scope_only"])
    assert allowed.status_code == 200
    assert allowed.json()["data_scope"] == {"tenant_id": tenant_id, "workspace_id": project_id}
    for code in PROJECT_MODULES:
        module = client.get(f"{modules}/{code}", headers=headers["full"])
        assert module.status_code == 200
        assert module.json()["module"]["code"] == code
    for code in ("scope", "schedule"):
        assert client.get(f"{modules}/{code}", headers=headers["full"]).status_code == 403

    # Workspace settings are independent of the actor's native permission.
    archived_id = ids["project_archived"]
    archived_cost = f"/api/v1/workspaces/{archived_id}/modules/cost"
    assert client.get(archived_cost, headers=headers["full"]).status_code == 200
    with SessionLocal() as db:
        setting = db.scalar(
            select(WorkspaceModuleSetting).where(
                WorkspaceModuleSetting.tenant_id == tenant_id,
                WorkspaceModuleSetting.workspace_id == archived_id,
                WorkspaceModuleSetting.module_key == "cost-manager",
            )
        )
        assert setting is not None
        setting.enabled = False
        db.commit()
        try:
            disabled = client.get(archived_cost, headers=headers["full"])
            assert disabled.status_code == 403
            assert disabled.json()["detail"] == "MODULE_DISABLED_OR_PERMISSION_DENIED"
        finally:
            setting.enabled = True
            db.commit()


def test_pending_archived_planned_disabled_and_direct_url_guards(gate06d):
    client, headers, ids, _tenant_id = gate06d
    pending_id = ids["facility_pending"]
    pending = client.get(f"/api/v1/workspaces/{pending_id}/context", headers=headers["full"])
    assert pending.status_code == 200
    assert {item["code"] for item in pending.json()["navigator"]} == {"home", "overview"}
    assert (
        client.get(f"/api/v1/workspaces/{pending_id}/modules/asset-manager", headers=headers["full"]).status_code == 403
    )
    facility_id = ids["facility_active"]
    planned = client.get(f"/api/v1/workspaces/{facility_id}/modules/asset-manager", headers=headers["full"])
    assert planned.status_code == 409
    archived = client.get(f"/api/v1/workspaces/{ids['project_archived']}/context", headers=headers["full"])
    assert archived.status_code == 200
    assert all(item["read_only"] for item in archived.json()["navigator"])
    tampered = client.put(
        f"/api/v1/workspaces/{facility_id}/last-route",
        headers=headers["full"],
        json={"route": f"/workspaces/{ids['project_active']}/scope-manager"},
    )
    assert tampered.status_code == 422


def test_invalid_workspace_type_cross_tenant_and_permission_denial(gate06d):
    client, headers, ids, _tenant_id = gate06d
    assert (
        client.get(f"/api/v1/workspaces/{ids['project_active']}/context", headers=headers["no_access"]).status_code
        == 403
    )
    with SessionLocal() as db:
        full_user = db.scalar(select(UserAccount).where(UserAccount.email.like("gate06d-full-%")))
        assert full_user is not None
        unsupported = EnterpriseWorkspace(
            tenant_id=full_user.tenant_id,
            workspace_type_code="site",
            code=f"G06D-SITE-{uuid4().hex[:4]}",
            external_key=f"G06D-SITE-{uuid4().hex}",
            record_code=f"G06D.SITE.{uuid4().hex[:5]}",
            name="Gate 06D Unsupported Site",
            status="active",
            defaults_json={},
            created_by_user_id=full_user.id,
        )
        db.add(unsupported)
        db.commit()
        unsupported_id = unsupported.id
        unsupported_tenant_id = unsupported.tenant_id
    assert client.get(f"/api/v1/workspaces/{unsupported_id}/context", headers=headers["full"]).status_code == 422
    assert client.get("/api/v1/workspaces/999999/context", headers=headers["full"]).status_code == 404
    assert (
        client.get(
            f"/api/v1/workspaces/{ids['project_active']}/context",
            headers=headers["cross_tenant"],
        ).status_code
        == 404
    )
    with SessionLocal() as db:
        db.query(SecurityEvent).filter(
            SecurityEvent.tenant_id == unsupported_tenant_id,
            SecurityEvent.target_id == unsupported_id,
        ).delete(synchronize_session=False)
        db.query(EnterpriseWorkspace).filter(EnterpriseWorkspace.id == unsupported_id).delete(synchronize_session=False)
        db.commit()
