"""Explicit, narrow QRA provisioning for a migrated existing tenant.

Adds only the QRA permission catalog, grants to already existing canonical
roles, and a neutral DRAFT methodology/number sequences. It never creates
Project evidence, memberships, roles or assignments, or seeds other domains.
"""

from __future__ import annotations

import argparse
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bootstrap_owner_capability import _authorize as authorize_existing_configurator
from app.database.session import SessionLocal
from app.domain.models import PermissionCatalog, SecurityRole, SecurityRolePermission, Tenant
from app.modules.enterprise_structure.constants import PERMISSION_SEED
from app.modules.enterprise_structure.permissions import (
    PROJECT_DEFINITION_ROLE_PERMISSIONS,
    require_enterprise_permission,
)
from app.modules.qra_foundation.service import QraFoundationService

QRA_PERMISSION_SEED = tuple(
    row for row in PERMISSION_SEED if row[0].startswith("qra_") and not row[0].startswith("qra_run.")
)
QRA_PERMISSION_KEYS = frozenset(row[0] for row in QRA_PERMISSION_SEED)
QRA_CONFIGURATION_KEYS = frozenset(
    {
        "qra_foundation.read",
        "qra_methodology.admin.configure",
        "qra_methodology.admin.publish",
    }
)


def _authorize(db: Session, tenant_id: int, actor_id: int) -> None:
    if db.scalar(select(Tenant.id).where(Tenant.id == tenant_id)) is None:
        raise HTTPException(404, detail="Tenant not found")
    try:
        context = require_enterprise_permission(
            db, tenant_id, actor_id, "qra_methodology.admin.configure", bootstrap=False
        )
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
    else:
        if context.organization_wide:
            return
    # Reuse the validated narrow existing-authority check; empty tenants and
    # workspace-only grants are not implicit tenant-wide provisioning rights.
    authorize_existing_configurator(db, tenant_id, actor_id)


def provision_qra_foundation(db: Session, tenant_id: int, actor_id: int) -> dict:
    try:
        _authorize(db, tenant_id, actor_id)
        db.execute(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()).scalar_one()
        permissions = {
            row.key: row
            for row in db.scalars(select(PermissionCatalog).where(PermissionCatalog.key.in_(QRA_PERMISSION_KEYS)))
        }
        added_permissions = 0
        for key, resource, action, description, risk_level in QRA_PERMISSION_SEED:
            if key not in permissions:
                row = PermissionCatalog(
                    key=key,
                    resource=resource,
                    action=action,
                    description=description,
                    risk_level=risk_level,
                    status="active",
                )
                db.add(row)
                db.flush()
                permissions[key] = row
                added_permissions += 1
        grants_by_role = {
            code: keys & QRA_PERMISSION_KEYS for code, keys in PROJECT_DEFINITION_ROLE_PERMISSIONS.items()
        } | {"organization_admin": QRA_PERMISSION_KEYS, "configuration_admin": QRA_CONFIGURATION_KEYS}
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
        configuration = QraFoundationService(db, tenant_id, actor_id).ensure_seed()
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
            "live_models_created": 0,
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
        print(json.dumps(provision_qra_foundation(db, args.tenant_id, args.actor_id), sort_keys=True))


if __name__ == "__main__":
    main()
