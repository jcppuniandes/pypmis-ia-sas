"""Persist actual B1 prerequisites, never mock business commands or normal data."""

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from tests.awp_browser_fixture import create_awp_browser_fixture

from app.core.security import hash_password
from app.database.session import SessionLocal, engine
from app.domain.models import AuthCredential, ProjectMembership
from app.main import app


def main():
    assert os.getenv("PYPMIS_O1BB1_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql" and engine.url.database == "o1bb1_browser"
    target = Path("/artifacts/browser-fixture.json")
    assert not target.exists(), "Reuse persistent identities"
    with TestClient(app) as client, SessionLocal() as db:
        f = create_awp_browser_fixture(db, client)
        for label, user in f.users.items():
            db.add(
                AuthCredential(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    provider="local",
                    password_hash=hash_password("O1bb1-disposable-only!"),
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
                label: {"id": user.id, "email": user.email, "tenant_id": user.tenant_id}
                for label, user in f.users.items()
            },
            "workspaces": {key: {"id": row.id, "name": row.name} for key, row in f.workspaces.items()},
            "model": f.model,
            "objects": f.objects,
            "scope_items": f.scope_items,
            "scope_baseline": f.scope_baseline,
            "plan_items": f.plan_items,
            "derived": f.derived,
            "schedule_register": f.schedule_register,
            "baseline_version": f.baseline_schedule_version,
            "current_version": f.current_schedule_version,
            "schedule_baseline": f.schedule_baseline,
            "activity_phases": f.activity_phases,
            "activity_plans": f.activity_plans,
            "fixture_scope": "Actual real IFC source, approved Scope, published Plan, Derived3D, imported XML Schedule and independent approval. Dedicated PostgreSQL. No business signoff.",
        }
        target.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {"fixture_created": True, "tenant_id": f.tenant_id, "project_workspace_id": f.project_workspace_id}
            )
        )


if __name__ == "__main__":
    main()
