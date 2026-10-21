"""Explicit, audited catalog provisioning by an existing organization admin."""

import argparse
import json

from app.database.session import SessionLocal
from app.domain.models import SecurityEvent
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.operational_context.permissions import ensure_operational_permissions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True, type=int)
    parser.add_argument("--actor-id", required=True, type=int)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    if args.tenant_id < 1 or args.actor_id < 1 or len(args.reason.strip()) < 3:
        parser.error("Positive tenant/actor and an explicit reason are required")
    with SessionLocal() as db:
        context = require_enterprise_permission(
            db,
            args.tenant_id,
            args.actor_id,
            "enterprise_structure.read",
            allowed_role_codes=frozenset({"organization_admin"}),
            bootstrap=False,
        )
        if not context.organization_wide:
            parser.error("Existing organization administrator scope is required")
        ensure_operational_permissions(db, args.tenant_id, args.actor_id)
        db.add(
            SecurityEvent(
                tenant_id=args.tenant_id,
                user_id=args.actor_id,
                event_type="operational.permissions.provisioned",
                outcome="success",
                target_type="PermissionCatalog",
                metadata_json={
                    "reason": args.reason.strip(),
                    "actor_role_assignments_created": 0,
                    "project_bindings_created": 0,
                },
            )
        )
        db.commit()
    print(
        json.dumps(
            {
                "tenant_id": args.tenant_id,
                "catalog_provisioned": True,
                "actor_role_assignments_created": 0,
                "project_bindings_created": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
