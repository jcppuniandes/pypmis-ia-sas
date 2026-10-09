"""Explicit additive policy provisioning for an existing, migrated tenant."""

from __future__ import annotations

import argparse

from app.database.session import SessionLocal
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.service import PortfolioReviewService


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
            "portfolio_review.admin.configure",
            allowed_role_codes=frozenset({"organization_admin"}),
        )
        PortfolioReviewService(db, args.tenant_id, context.user.id, context).ensure_seed()
        print(f"WAVE3A_POLICY_PROVISIONED tenant={args.tenant_id}; live_reviews_created=0")


if __name__ == "__main__":
    main()
