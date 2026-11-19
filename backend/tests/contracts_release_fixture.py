"""O2C isolated fixture on actual O1 and O2B domain chains."""

import json
import os
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from tests.engineering_release_fixture import TODAY, add_actor, request
from tests.o2b_close_isolation import is_close_consumer_database
from tests.progress_release_fixture import request as progress_request
from tests.test_procurement_consumer_release import create_governed_fixture
from tests.test_procurement_o2b_release import expect
from tests.test_progress_foundation_release import approve as approve_progress
from tests.test_progress_foundation_release import measurement_body

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.domain.models import AuthCredential, ProjectMembership, Tenant
from app.main import app
from app.modules.contracts_foundation.permissions import ensure_contracts_permissions
from app.modules.contracts_foundation.policy import DEFAULT_PROFILE

REASON = {"reason": "Controlled O2C validation in disposable project"}
ACTORS = {
    "contract_preparer": ("contracts_preparer", False),
    "contract_approver": ("contracts_approver", False),
    "contract_executor": ("contracts_executor", False),
    "contract_configurator": ("contracts_configurator", True),
    "contract_publisher": ("contracts_publisher", True),
}


def contract_root(f):
    return f"/api/v1/contracts/projects/{f.project_workspace_id}"


def setup(db, client, *, browser=False):
    assert os.getenv("PYPMIS_O2C_FIXTURE") == "disposable-only" and is_close_consumer_database(db)
    f = create_governed_fixture(db, client, credentials=browser)
    f.tenant_slug = db.get(Tenant, f.tenant_id).slug
    workspace = f.workspaces["direct"]
    workspace.defaults_json = {
        **workspace.defaults_json,
        "enabled_modules": [*workspace.defaults_json["enabled_modules"], "contracts"],
    }
    ensure_contracts_permissions(db, f.tenant_id, f.users["admin"].id)
    ensure_contracts_permissions(db, f.foreign_tenant.id, f.users["foreign"].id)
    for name, (role, organization) in ACTORS.items():
        add_actor(db, f, name, role, organization=organization)
        actor = f.users[name]
        db.add(
            ProjectMembership(
                tenant_id=f.tenant_id,
                project_id=f.legacy_project_id,
                user_id=actor.id,
                role="Executive Viewer",
                can_configure=organization,
                can_capture_progress=False,
                can_capture_cost=False,
            )
        )
        if browser:
            db.add(
                AuthCredential(
                    tenant_id=f.tenant_id,
                    user_id=actor.id,
                    provider="local",
                    password_hash=hash_password(f.password),
                    is_active=True,
                )
            )
    db.commit()
    if not browser:
        admin = "/api/v1/contracts/admin/profiles"
        profile = expect(
            request(
                f,
                "POST",
                admin,
                actor="contract_configurator",
                payload={**REASON, "code": "O2C-BASE", "name": "O2C isolated profile", "content_json": DEFAULT_PROFILE},
            ),
            201,
        )
        f.contract_profile = expect(
            request(
                f,
                "POST",
                f"{admin}/{profile['id']}/publish",
                actor="contract_publisher",
                version=profile["version"],
                payload=REASON,
            ),
            200,
        )
    return f


def ref_id(value):
    return value["id"] if isinstance(value, dict) else value


def payment_progress(f):
    existing = f.approved_quantity_progress
    cumulative = Decimal(existing["numerator"]) + Decimal(f.scope_items[0]["quantity"]) / 4
    return approve_progress(
        f,
        expect(
            progress_request(
                f,
                "POST",
                "/measurements",
                payload=measurement_body(
                    f,
                    period_id=f.current_period["id"],
                    measurement_date=TODAY.isoformat(),
                    as_of=TODAY.isoformat(),
                    numerator=str(cumulative),
                ),
            ),
            201,
        ),
    )


def main():
    target = Path(os.environ["E2E_O2C_FIXTURE"]).resolve()
    root = Path(__file__).resolve().parents[2] / "outputs/.qa/wave-o2c-20261113"
    assert target.is_relative_to(root) and "private" in target.parts and not target.exists()
    with SessionLocal() as db, TestClient(app) as client:
        f = setup(db, client, browser=True)
        progress = payment_progress(f)
        payload = {
            "tenant_id": f.tenant_id,
            "project_workspace_id": f.project_workspace_id,
            "tenant_slug": f.tenant_slug,
            "password": f.password,
            "users": {
                role: f.users[f"contract_{role}" if role != "cost" else "manager"].email
                for role in ("preparer", "approver", "executor", "cost", "configurator", "publisher")
            },
            "po_id": f.chain["po"]["id"],
            "vendor_id": f.chain["po"]["vendor_id"],
            "document_id": f.document["id"],
            "attachment_id": f.attachment["id"],
            "cbs_id": ref_id(f.cost_cbs),
            "cost_code_id": ref_id(f.cost_code),
            "control_account_id": ref_id(f.cost_account),
            "effective_at": TODAY.isoformat(),
            "scope_item_id": progress["scope_item_id"],
            "period_id": progress["period_id"],
            "progress_measurement_id": progress["id"],
            "progress_unit": progress["unit"],
            "progress_quantity": str(progress["period_quantity"]),
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)


if __name__ == "__main__":
    main()
