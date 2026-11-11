"""Prepare upstream authorities, CDE attachments and synthetic independent actors."""

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from tests.engineering_release_fixture import TODAY, create_engineering_fixture

from app.database.session import SessionLocal, engine
from app.main import app


def main():
    assert os.getenv("PYPMIS_O2A_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql" and engine.url.database == "o2a_browser"
    qa = Path(__file__).resolve().parents[2] / "outputs/.qa/wave-o2a-20261109"
    if Path("/artifacts").is_dir():
        qa = Path("/artifacts")
    target = qa / "browser-fixture.json"
    assert not target.exists(), "Do not replace an existing browser fixture"
    qa.mkdir(parents=True, exist_ok=True)
    with TestClient(app) as client, SessionLocal() as db:
        f = create_engineering_fixture(db, client, publish=False, credentials=True)
        packages = f.engineering_packages
        result = {
            "tenant_id": f.tenant_id,
            "project_workspace_id": f.project_workspace_id,
            "legacy_project_id": f.legacy_project_id,
            "as_of": TODAY.isoformat(),
            "password": f.password,
            "users": {
                label: {"email": user.email, "id": user.id, "tenant_id": user.tenant_id, "password": f.password}
                for label, user in f.users.items()
            },
            "scope_item_ids": [row["id"] for row in f.scope_items],
            "plan_item_ids": [row["id"] for row in f.plan_items],
            "ewp_ids": [row["id"] for row in packages["EWP"]],
            "cwp_ids": [row["id"] for row in packages["CWP"]],
            "iwp_ids": [row["id"] for row in packages["IWP"]],
            "ready_package_id": packages["EWP"][0]["id"],
            "cwa_ids": [row["id"] for row in f.cwas],
            "document_id": f.document["id"],
            "attachment_id": f.attachment["id"],
            "document_hash": f.attachment["sha256"],
            "successor_document_id": f.successor_document["id"],
            "successor_attachment_id": f.successor_attachment["id"],
            "current_schedule_version_id": f.current_schedule_version["id"],
            "activity_ids": list(f.activity_plans),
        }
        target.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "scope": "isolated-o2a",
                    "project_workspace_id": f.project_workspace_id,
                    "ewp_count": len(packages["EWP"]),
                    "cde_attachments": 2,
                }
            )
        )


if __name__ == "__main__":
    main()
