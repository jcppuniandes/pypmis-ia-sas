"""Explicit O3B catalog provisioning; no assignments or operational records are created."""

import argparse
import json

from fastapi import HTTPException

from app.domain.models import SecurityEvent
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.quality.permissions import ensure_quality_permissions


def provision_quality_catalog(db, tenant_id, actor_id, *, reason):
    if min(tenant_id, actor_id) < 1 or not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 3000:
        raise ValueError("Positive identities and a reason of 8 to 3000 characters are required")
    access = require_enterprise_permission(
        db,
        tenant_id,
        actor_id,
        "enterprise_structure.read",
        allowed_role_codes=frozenset({"organization_admin"}),
        bootstrap=False,
    )
    if not access.organization_wide:
        raise HTTPException(403, detail={"code": "QUALITY_ORGANIZATION_SCOPE_REQUIRED"})
    ensure_quality_permissions(db, tenant_id, actor_id)
    db.add(
        SecurityEvent(
            tenant_id=tenant_id,
            user_id=actor_id,
            event_type="quality.permissions.provisioned",
            outcome="success",
            target_type="PermissionCatalog",
            metadata_json={
                "reason": reason.strip(),
                "actor_role_assignments_created": 0,
                "quality_records_created": 0,
                "project_bindings_created": 0,
            },
        )
    )
    db.flush()


def main():
    from app.database.session import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=int, required=True)
    parser.add_argument("--actor-id", type=int, required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    if min(args.tenant_id, args.actor_id) < 1 or not 8 <= len(args.reason.strip()) <= 3000:
        parser.error("Positive identities and a reason of 8 to 3000 characters are required")
    with SessionLocal() as db:
        provision_quality_catalog(db, args.tenant_id, args.actor_id, reason=args.reason)
        db.commit()
    print(json.dumps({"tenant_id": args.tenant_id, "catalog_provisioned": True, "actor_role_assignments_created": 0}))


if __name__ == "__main__":
    main()
