"""Persistent isolated Schedule UAT actors with actual Scope prerequisite commands."""

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from tests.schedule_release_fixture import create_schedule_fixture

from app.core.security import hash_password
from app.database.session import SessionLocal, engine
from app.domain.models import AuthCredential, ProjectMembership
from app.main import app


def main():
    assert os.getenv("PYPMIS_O1BB_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql" and engine.url.database == "o1bb"
    target = Path("/artifacts/browser-fixture.json")
    assert not target.exists(), "Reuse the existing isolated browser identities"
    with TestClient(app) as client, SessionLocal() as db:
        f = create_schedule_fixture(db, client)
        for label, user in f.users.items():
            db.add(
                AuthCredential(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    provider="local",
                    password_hash=hash_password("O1bb-disposable-only!"),
                    is_active=True,
                )
            )
            if label != "foreign":
                db.add(
                    ProjectMembership(
                        tenant_id=f.tenant_id,
                        project_id=f.legacy_project_id,
                        user_id=user.id,
                        role="Control Manager" if label in {"admin", "publisher"} else "Executive Viewer",
                        can_configure=label in {"admin", "publisher"},
                        can_capture_progress=False,
                        can_capture_cost=False,
                    )
                )
        db.commit()
        result = {
            "tenant_id": f.tenant_id,
            "project_workspace_id": f.project_workspace_id,
            "users": {
                key: {"id": user.id, "email": user.email, "tenant_id": user.tenant_id} for key, user in f.users.items()
            },
            "workspaces": {
                key: {"id": workspace.id, "name": workspace.name} for key, workspace in f.workspaces.items()
            },
            "scope_items": f.scope_items,
            "scope_baseline": f.scope_baseline,
            "plan_items": f.plan_items,
            "fixture_scope": "Dedicated PostgreSQL canonical fixture. Real O1A profiles, Scope approval and Plan publication. No business signoff claimed.",
        }
        target.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"fixture_created": True, "tenant_id": f.tenant_id, "workspace_id": f.project_workspace_id}))


if __name__ == "__main__":
    main()
