"""Provision real upstream evidence only; Quality facts are created through Chromium."""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
QA = ROOT / "outputs/.qa/wave-o3b-20261119"


def main():
    expected = "postgresql+psycopg://o3b:o3b@127.0.0.1:5567/o3b"
    if (
        os.getenv("DATABASE_URL") != expected
        or os.getenv("PYPMIS_O3B_FIXTURE") != "disposable-only"
    ):
        raise RuntimeError("Only the explicitly disposable O3B database is allowed")
    target = QA / os.getenv("O3B_BROWSER_MANIFEST", "browser-fixture.json")
    if target.parent != QA or target.exists():
        raise RuntimeError(
            "An existing browser fixture is preserved; choose another manifest filename"
        )
    from app.database.session import SessionLocal
    from app.main import app
    from app.modules.contracts_foundation.permissions import (
        ensure_contracts_permissions,
    )
    from app.modules.procurement_foundation.materials_models import (
        ProcurementMaterialAllocation,
    )
    from fastapi.testclient import TestClient
    from sqlalchemy import select, text
    from tests.engineering_release_fixture import TODAY
    from tests.quality_release_fixture import setup

    QA.mkdir(exist_ok=True, parents=True)
    with SessionLocal() as db, TestClient(app) as client:
        assert (
            db.execute(text("select version_num from alembic_version")).scalar_one()
            == "20261120_0081"
        )
        f = setup(db, client, credentials=True, publish=False)
        workspace = f.workspaces["direct"]
        workspace.defaults_json = workspace.defaults_json | {
            "enabled_modules": [
                *workspace.defaults_json["enabled_modules"],
                "contracts",
            ]
        }
        ensure_contracts_permissions(db, f.tenant_id, f.users["admin"].id)
        db.commit()
        allocation = db.scalar(
            select(ProcurementMaterialAllocation).where(
                ProcurementMaterialAllocation.tenant_id == f.tenant_id,
                ProcurementMaterialAllocation.project_workspace_id
                == f.project_workspace_id,
            )
        )
        manifest = {
            "tenant_id": f.tenant_id,
            "project_workspace_id": f.project_workspace_id,
            "legacy_project_id": f.legacy_project_id,
            "password": f.password,
            "users": {name: user.email for name, user in f.users.items()},
            "user_ids": {name: user.id for name, user in f.users.items()},
            "scope_item_id": f.scope_items[0]["id"],
            "plan_item_id": f.plan_items[0]["id"],
            "scope_unit": f.scope_items[0]["unit"],
            "iwp_id": f.field_released_iwp["id"],
            "workfront_id": f.field_front["id"],
            "production_id": f.field_production["id"],
            "equipment_reference_id": f.field_equipment_ref["id"],
            "document_id": f.document["id"],
            "attachment_id": f.attachment["id"],
            "ifc_id": f.ifc["id"],
            "material_allocation_id": allocation.id,
            "material_receipt_line_id": allocation.receipt_line_id,
            "material_item_id": f.chain["material_requirement"]["material_item_id"],
            "vendor_id": f.chain["po"]["vendor_id"],
            "period_id": f.current_period["id"],
            "cbs_id": f.cost_cbs["id"],
            "cost_code_id": f.cost_code["id"],
            "control_account_id": f.cost_account["id"],
            "effective_at": TODAY.isoformat(),
            "created_at": datetime.now(UTC).isoformat(),
            "provisioning": "Actual governed O1/O2/O3A lifecycles with verified Production and approved DCR; no Quality facts or consumer decisions precreated",
        }
        target.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    key: manifest[key]
                    for key in ("tenant_id", "project_workspace_id", "production_id")
                }
            )
        )


if __name__ == "__main__":
    main()
