"""Real browser actors over isolated PG; no mock routes or production records."""

import json
import os
from pathlib import Path

from sqlalchemy import select
from tests.operational_context_fixture import create_o1a_fixture

from app.core.security import hash_password
from app.database.session import SessionLocal, engine
from app.domain.models import AuthCredential, PermissionCatalog, ProjectMembership, SecurityRole, SecurityRolePermission
from app.modules.enterprise_structure.permissions import ensure_enterprise_permissions


def main():
    assert os.getenv("PYPMIS_O1A_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql" and engine.url.database == "o1a"
    manifest = Path("/artifacts/browser-fixture.json")
    assert not manifest.exists(), "Use existing browser fixture; do not overwrite identity proof"
    with SessionLocal() as db:
        fixture = create_o1a_fixture(db)
        for label, user in fixture.users.items():
            db.add(
                AuthCredential(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    provider="local",
                    password_hash=hash_password("O1a-disposable-only!"),
                    is_active=True,
                )
            )
            if label == "foreign":
                continue
            db.add(
                ProjectMembership(
                    tenant_id=fixture.tenant_id,
                    project_id=fixture.legacy_project_id,
                    user_id=user.id,
                    role="Control Manager" if label in {"admin", "publisher"} else "Executive Viewer",
                    can_configure=label in {"admin", "publisher"},
                    can_capture_progress=label in {"admin", "publisher", "manager", "second_manager"},
                    can_capture_cost=label in {"admin", "publisher", "manager", "second_manager"},
                )
            )
        db.flush()
        ensure_enterprise_permissions(db, fixture.tenant_id, fixture.users["admin"].id)
        keys = {
            "workspace.open",
            "workspace.home.read",
            "workspace.navigator.read",
            "workspace.recent.read",
            "workspace.recent.write",
        }
        permissions = list(db.scalars(select(PermissionCatalog).where(PermissionCatalog.key.in_(keys))))
        assert len(permissions) == len(keys)
        for role in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == fixture.tenant_id)):
            if role.code not in {
                "project_manager",
                "project_controls_manager",
                "executive_viewer",
                "planner_scheduler",
                "project_administrator",
            }:
                continue
            existing = set(
                db.scalars(
                    select(SecurityRolePermission.permission_id).where(SecurityRolePermission.role_id == role.id)
                )
            )
            for permission in permissions:
                if permission.id not in existing:
                    db.add(
                        SecurityRolePermission(
                            tenant_id=fixture.tenant_id,
                            role_id=role.id,
                            permission_id=permission.id,
                            granted_by_user_id=fixture.users["admin"].id,
                        )
                    )
        db.commit()
        result = {
            "tenant_id": fixture.tenant_id,
            "tenant_slug": fixture.tenant.slug,
            "users": {
                key: {"id": value.id, "email": value.email, "tenant_id": value.tenant_id}
                for key, value in fixture.users.items()
            },
            "workspaces": {
                key: {"id": value.id, "external_key": value.external_key, "name": value.name}
                for key, value in fixture.workspaces.items()
            },
            "legacy_project_id": fixture.legacy_project_id,
            "fixture_scope": "Existing canonical lifecycle states; not lifecycle creation proof. Real PG, credentials and RBAC.",
        }
        manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {"fixture_created": True, "tenant_id": fixture.tenant_id, "workspace_id": fixture.project_workspace_id}
            )
        )


if __name__ == "__main__":
    main()
