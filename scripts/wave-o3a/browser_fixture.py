"""Prepare only governed upstream sources for the real O3A browser journey."""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o3a-20261118"
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))


def main():
    expected = "postgresql+psycopg://o3a:o3a@127.0.0.1:5564/o3a"
    if (
        os.getenv("DATABASE_URL") != expected
        or os.getenv("PYPMIS_O3A_FIXTURE") != "disposable-only"
    ):
        raise RuntimeError(
            "This helper only provisions the explicitly disposable O3A database"
        )
    target = QA / "browser-fixture.json"
    if target.exists():
        raise RuntimeError(
            "Existing browser fixture preserved; use its isolated tenant"
        )
    from app.database.session import SessionLocal
    from app.main import app
    from app.modules.procurement_foundation.materials_models import (
        ProcurementMaterialAllocation,
    )
    from fastapi.testclient import TestClient
    from sqlalchemy import select, text
    from tests.engineering_release_fixture import TODAY
    from tests.field_operations_release_fixture import setup

    QA.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db, TestClient(app) as client:
        assert (
            db.execute(text("select version_num from alembic_version")).scalar_one()
            == "20261118_0080"
        )
        f = setup(db, client, credentials=True, publish=False)
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
            "cwa_id": f.cwas[0]["id"],
            "document_id": f.document["id"],
            "attachment_id": f.attachment["id"],
            "ifc_id": f.ifc["id"],
            "material_allocation_id": allocation.id,
            "material_item_id": f.chain["material_requirement"]["material_item_id"],
            "vendor_id": f.chain["po"]["vendor_id"],
            "period_id": f.current_period["id"],
            "cbs_id": f.cost_cbs["id"],
            "cost_code_id": f.cost_code["id"],
            "control_account_id": f.cost_account["id"],
            "effective_at": TODAY.isoformat(),
            "created_at": datetime.now(UTC).isoformat(),
            "provisioning": "Real O1/O2A/O2B commands and AWP release; no Field facts precreated",
        }
        target.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    key: manifest[key]
                    for key in ("tenant_id", "project_workspace_id", "iwp_id")
                }
            )
        )


if __name__ == "__main__":
    main()
