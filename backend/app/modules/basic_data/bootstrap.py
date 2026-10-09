"""Explicit additive provisioning; no live Basic Data or source-domain writes."""

import argparse

from app.database.session import SessionLocal
from app.modules.basic_data.service import BasicDataService
from app.modules.enterprise_structure.permissions import require_enterprise_permission


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=int, required=True)
    parser.add_argument("--actor-id", type=int, required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        context = require_enterprise_permission(db, args.tenant_id, args.actor_id, "basic_data.admin.configure")
        BasicDataService(db, args.tenant_id, args.actor_id, context).ensure_seed()
        print(f"WAVE2B_BASIC_DATA_PROVISIONED tenant={args.tenant_id}; live_items_created=0; assessments_created=0")


if __name__ == "__main__":
    main()
