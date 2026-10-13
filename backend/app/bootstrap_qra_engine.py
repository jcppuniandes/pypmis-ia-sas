"""Provision only six execution permissions on already existing tenant roles.

No demo fixture, role/assignment creation, source, model, run or configuration
publication is authorized by this explicit migrated-tenant operation.
"""

import argparse
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bootstrap_qra_foundation import _authorize
from app.database.session import SessionLocal
from app.domain.models import PermissionCatalog, SecurityEvent, SecurityRole, SecurityRolePermission, Tenant
from app.modules.enterprise_structure.constants import PERMISSION_SEED
from app.modules.enterprise_structure.permissions import PROJECT_DEFINITION_ROLE_PERMISSIONS

QRA_ENGINE_PERMISSION_SEED = tuple(row for row in PERMISSION_SEED if row[0].startswith("qra_run."))
QRA_ENGINE_PERMISSION_KEYS = frozenset(row[0] for row in QRA_ENGINE_PERMISSION_SEED)


def provision_qra_engine(db: Session, tenant_id: int, actor_id: int) -> dict:
    try:
        _authorize(db, tenant_id, actor_id)
        db.execute(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()).scalar_one()
        permissions = {
            row.key: row
            for row in db.scalars(
                select(PermissionCatalog).where(PermissionCatalog.key.in_(QRA_ENGINE_PERMISSION_KEYS))
            )
        }
        added_permissions = 0
        for key, resource, action, description, risk_level in QRA_ENGINE_PERMISSION_SEED:
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
        grants = {code: keys & QRA_ENGINE_PERMISSION_KEYS for code, keys in PROJECT_DEFINITION_ROLE_PERMISSIONS.items()}
        grants["organization_admin"] = QRA_ENGINE_PERMISSION_KEYS
        added_grants = 0
        for role in db.scalars(
            select(SecurityRole).where(SecurityRole.tenant_id == tenant_id, SecurityRole.code.in_(grants))
        ):
            existing = set(
                db.scalars(
                    select(SecurityRolePermission.permission_id).where(
                        SecurityRolePermission.tenant_id == tenant_id, SecurityRolePermission.role_id == role.id
                    )
                )
            )
            for key in grants[role.code]:
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
        if added_permissions or added_grants:
            db.add(
                SecurityEvent(
                    tenant_id=tenant_id,
                    user_id=actor_id,
                    event_type="qra.engine.provisioned",
                    target_type="Tenant",
                    target_id=tenant_id,
                    metadata_json={
                        "permission_entries_added": added_permissions,
                        "role_grants_added": added_grants,
                        "no_live_evidence": True,
                    },
                )
            )
        db.commit()
        return {
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "permission_entries_added": added_permissions,
            "role_grants_added": added_grants,
            "roles_created": 0,
            "assignments_created": 0,
            "configuration_changes": 0,
            "live_runs_created": 0,
        }
    except Exception:
        db.rollback()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=int, required=True)
    parser.add_argument("--actor-id", type=int, required=True)
    args = parser.parse_args()
    if args.tenant_id <= 0 or args.actor_id <= 0:
        parser.error("Expected positive existing tenant/actor identities")
    with SessionLocal() as db:
        print(json.dumps(provision_qra_engine(db, args.tenant_id, args.actor_id), sort_keys=True))


if __name__ == "__main__":
    main()
