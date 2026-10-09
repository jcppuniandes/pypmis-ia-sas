"""Explicit, narrow Wave 3B provisioning for an existing migrated tenant.

Only Owner Capability permission catalog entries and grants to existing roles
are added. No roles, access assignments, memberships, source policies or live
Project assessments are created. API reads continue to use bootstrap=False.
"""

from __future__ import annotations

import argparse
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1._helpers import require_tenant_configurator
from app.database.session import SessionLocal
from app.domain.models import PermissionCatalog, ProjectMembership, SecurityRole, SecurityRolePermission, Tenant
from app.modules.enterprise_structure.constants import PERMISSION_SEED
from app.modules.enterprise_structure.permissions import (
    PROJECT_DEFINITION_ROLE_PERMISSIONS,
    require_enterprise_permission,
)
from app.modules.owner_capability.service import OwnerCapabilityService

OWNER_PERMISSION_SEED = tuple(row for row in PERMISSION_SEED if row[0].startswith("owner_capability."))
OWNER_PERMISSION_KEYS = frozenset(row[0] for row in OWNER_PERMISSION_SEED)
OWNER_CONFIGURATION_KEYS = frozenset(
    {"owner_capability.read", "owner_capability.admin.configure", "owner_capability.admin.publish"}
)


def _authorize(db: Session, tenant_id: int, actor_id: int) -> None:
    """Require existing tenant-wide configurator authority without seeding RBAC."""
    if db.scalar(select(Tenant.id).where(Tenant.id == tenant_id)) is None:
        raise HTTPException(404, detail="Tenant not found")
    for permission in (
        "owner_capability.admin.configure",
        "project_definition.admin.configure",
        "admin.enterprise_structure.manage",
    ):
        try:
            context = require_enterprise_permission(db, tenant_id, actor_id, permission, bootstrap=False)
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
        else:
            if context.organization_wide:
                return
    # Unlike the legacy helper, an empty tenant is never implicit authority.
    # A pre-existing can_configure membership is the only legacy fallback.
    membership = db.scalar(
        select(ProjectMembership.id).where(
            ProjectMembership.tenant_id == tenant_id,
            ProjectMembership.user_id == actor_id,
            ProjectMembership.can_configure.is_(True),
        )
    )
    if membership is None:
        raise HTTPException(403, detail="Existing tenant-wide configurator authority is required")
    require_tenant_configurator(db, tenant_id, actor_id)


def provision_owner_capability(db: Session, tenant_id: int, actor_id: int) -> dict:
    """Idempotently provision only the additive Owner catalog/grant/seed surface."""
    try:
        _authorize(db, tenant_id, actor_id)
        db.execute(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()).scalar_one()
        permissions = {
            row.key: row
            for row in db.scalars(select(PermissionCatalog).where(PermissionCatalog.key.in_(OWNER_PERMISSION_KEYS)))
        }
        added_permissions = 0
        for key, resource, action, description, risk_level in OWNER_PERMISSION_SEED:
            if key not in permissions:
                permission = PermissionCatalog(
                    key=key,
                    resource=resource,
                    action=action,
                    description=description,
                    risk_level=risk_level,
                    status="active",
                )
                db.add(permission)
                db.flush()
                permissions[key] = permission
                added_permissions += 1
        grants_by_role = {
            code: keys & OWNER_PERMISSION_KEYS for code, keys in PROJECT_DEFINITION_ROLE_PERMISSIONS.items()
        } | {"organization_admin": OWNER_PERMISSION_KEYS, "configuration_admin": OWNER_CONFIGURATION_KEYS}
        roles = db.scalars(
            select(SecurityRole).where(SecurityRole.tenant_id == tenant_id, SecurityRole.code.in_(grants_by_role))
        ).all()
        added_grants = 0
        for role in roles:
            existing = set(
                db.scalars(
                    select(SecurityRolePermission.permission_id).where(
                        SecurityRolePermission.tenant_id == tenant_id, SecurityRolePermission.role_id == role.id
                    )
                )
            )
            for key in grants_by_role[role.code]:
                if permissions[key].id not in existing:
                    db.add(
                        SecurityRolePermission(
                            tenant_id=tenant_id,
                            role_id=role.id,
                            permission_id=permissions[key].id,
                            granted_by_user_id=actor_id,
                        )
                    )
                    added_grants += 1
        db.flush()
        # This existing seed owns only the neutral DRAFT, Owner sequence and
        # seed audit event. Its commit atomically includes the additions above.
        configuration = OwnerCapabilityService(db, tenant_id, actor_id).ensure_seed()
        return {
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "permission_entries_added": added_permissions,
            "role_grants_added": added_grants,
            "configuration_id": configuration.id,
            "configuration_status": configuration.status,
            "roles_created": 0,
            "assignments_created": 0,
            "memberships_created": 0,
            "live_assessments_created": 0,
        }
    except Exception:
        db.rollback()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=int, required=True)
    parser.add_argument("--actor-id", type=int, required=True)
    args = parser.parse_args()
    if args.tenant_id <= 0 or args.actor_id <= 0:
        parser.error("tenant-id and actor-id must be positive existing identifiers")
    with SessionLocal() as db:
        print(json.dumps(provision_owner_capability(db, args.tenant_id, args.actor_id), sort_keys=True))


if __name__ == "__main__":
    main()
