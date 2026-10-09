"""Explicit additive Risk Governance configuration provisioning."""

import argparse

from app.database.session import SessionLocal
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.risk_governance.service import RiskGovernanceService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=int, required=True)
    parser.add_argument("--actor-id", type=int, required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        context = require_enterprise_permission(
            db,
            args.tenant_id,
            args.actor_id,
            "risk_governance.admin.configure",
            allowed_role_codes=frozenset({"organization_admin"}),
        )
        RiskGovernanceService(db, args.tenant_id, args.actor_id, context).ensure_seed()
        print(f"WAVE2B_RISK_POLICY_PROVISIONED tenant={args.tenant_id}; project_risk_transactions_created=0")


if __name__ == "__main__":
    main()
