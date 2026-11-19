"""Persist a fresh, empty-Procurement isolated browser scenario."""

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from tests.engineering_release_fixture import TODAY
from tests.procurement_release_fixture import create_procurement_fixture

from app.database.session import SessionLocal, engine
from app.main import app


def main():
    assert os.getenv("PYPMIS_O2B_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql" and engine.url.database == "o2b_browser" and engine.url.username == "o2b"
    directory = Path(os.environ.get("PYPMIS_O2B_ARTIFACT_DIR", "/artifacts"))
    if not directory.is_dir():
        directory = Path(__file__).resolve().parents[2] / "outputs/.qa/wave-o2b"
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / "browser-fixture.json"
    assert not file.exists(), "Preserve the original browser fixture"
    with TestClient(app) as client, SessionLocal() as db:
        f = create_procurement_fixture(db, client, publish=False, credentials=True)
        manifest = {
            "project_workspace_id": f.project_workspace_id,
            "tenant_id": f.tenant_id,
            "password": f.password,
            "users": {
                name: {"id": row.id, "email": row.email, "tenant_id": row.tenant_id, "password": f.password}
                for name, row in f.users.items()
            },
            "ifc_release_id": f.ifc["id"],
            "ifc_release_hash": f.ifc["release_hash"],
            "engineering_revision_id": f.engineering_revision["id"],
            "engineering_revision_hash": f.engineering_revision["content_hash"],
            "pwp_id": f.pwp["id"],
            "iwp_id": f.iwp["id"],
            "cwp_id": f.engineering_packages["CWP"][0]["id"],
            "document_id": f.document["id"],
            "attachment_id": f.attachment["id"],
            "as_of": TODAY.isoformat(),
            "legacy_project_id": f.legacy_project_id,
            "procurement_profile": f.policy,
        }
        with file.open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2)
    print(json.dumps({"project_workspace_id": manifest["project_workspace_id"], "isolated": True}))


if __name__ == "__main__":
    main()
