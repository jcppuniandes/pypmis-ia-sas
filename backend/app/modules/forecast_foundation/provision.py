"""Explicit, administrator-scoped Forecast catalog adoption, never a GET side effect."""

import argparse
import json

from app.domain.models import SecurityEvent
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.forecast_foundation.permissions import ensure_forecast_permissions, require_forecast_schema


def provision_forecast_catalog(db, tenant_id, actor_id, *, reason):
    if len(reason.strip()) < 8:
        raise ValueError("An explicit reason of at least eight characters is required")
    require_forecast_schema(db)
    access = require_enterprise_permission(
        db,
        tenant_id,
        actor_id,
        "enterprise_structure.read",
        allowed_role_codes=frozenset({"organization_admin"}),
        bootstrap=False,
    )
    if not access.organization_wide:
        from fastapi import HTTPException

        raise HTTPException(403, detail={"code": "FORECAST_ADMIN_ORGANIZATION_SCOPE_REQUIRED"})
    ensure_forecast_permissions(db, tenant_id, actor_id)
    db.add(
        SecurityEvent(
            tenant_id=tenant_id,
            user_id=actor_id,
            event_type="forecast.FORECAST_CATALOG_PROVISIONED",
            outcome="success",
            target_type="ForecastFoundation",
            target_id=None,
            metadata_json={
                "reason": reason.strip(),
                "actor_roles_assigned": False,
                "source_write_permissions_added": False,
            },
        )
    )
    db.flush()


def main():
    from app.database.session import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True, type=int)
    parser.add_argument("--actor-id", required=True, type=int)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    if min(args.tenant_id, args.actor_id) < 1 or len(args.reason.strip()) < 8:
        parser.error("Positive identities and an explicit reason of at least eight characters are required")
    with SessionLocal() as db:
        provision_forecast_catalog(db, args.tenant_id, args.actor_id, reason=args.reason)
        db.commit()
    print(
        json.dumps(
            {
                "catalog_provisioned": True,
                "tenant_id": args.tenant_id,
                "actor_role_assignments_created": 0,
                "source_records_created": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
