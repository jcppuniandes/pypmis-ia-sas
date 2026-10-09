# ruff: noqa: I001
"""Prepare or apply the controlled Gate 07M-EVID policy update.

Default behavior is a read-only dry run. Use ``--apply`` to clone, update and
publish the current tenant policy through the domain service lifecycle.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select

from app.database.session import SessionLocal
from app.domain.models import Tenant, UserAccount
from app.modules.investment_evidence_policy.service import (
    InvestmentEvidencePolicyService,
    _hash,
    gate07m_evid_policy_update,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--tenant-id", type=int)
    parser.add_argument("--actor-id", type=int)
    args = parser.parse_args()

    with SessionLocal() as db:
        tenant = (
            db.scalar(select(Tenant).where(Tenant.id == args.tenant_id))
            if args.tenant_id
            else db.scalar(select(Tenant))
        )
        if tenant is None:
            raise SystemExit("No tenant is available")
        actor = (
            db.scalar(
                select(UserAccount).where(
                    UserAccount.id == args.actor_id, UserAccount.tenant_id == tenant.id
                )
            )
            if args.actor_id
            else db.scalar(
                select(UserAccount)
                .where(UserAccount.tenant_id == tenant.id)
                .order_by(UserAccount.id)
            )
        )
        if actor is None:
            raise SystemExit("No actor is available for the tenant")
        service = InvestmentEvidencePolicyService(db, tenant.id, actor.id)
        service.ensure_seed()
        records = service.configurations()
        source = next((item for item in records if item.status == "published"), None)
        if source is None:
            source = next((item for item in records if item.status == "draft"), None)
        if source is None:
            raise SystemExit("No Investment Evidence Policy configuration is available")
        content = gate07m_evid_policy_update(source.content_json)
        service._validate_policy(content)
        result = {
            "mode": "apply" if args.apply else "dry-run",
            "tenant_id": tenant.id,
            "actor_id": actor.id,
            "source_policy_id": source.id,
            "source_revision": source.revision,
            "source_status": source.status,
            "source_hash": source.content_hash,
            "proposed_hash": _hash(content),
            "migration_head_required": "20260902_0058",
            "new_schema_required": False,
        }
        if args.apply:
            draft = (
                service.clone_configuration(source.id, source.version)
                if source.status == "published"
                else source
            )
            draft = service.update_configuration(
                draft.id,
                draft.version,
                draft.name,
                "Gate 07M-EVID controlled Business Case and Economic/Financial evidence policy update.",
                content,
            )
            published = service.publish_configuration(draft.id, draft.version)
            result.update(
                policy_id=published.id,
                policy_revision=published.revision,
                policy_hash=published.content_hash,
                effective_from=published.content_json.get("effective_from"),
                release_status=published.content_json.get("release_status"),
            )
        else:
            result["validation"] = "PASS"
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
