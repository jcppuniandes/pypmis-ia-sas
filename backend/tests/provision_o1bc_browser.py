"""Persist real upstream Cost prerequisites and independent disposable actors."""

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from tests.cost_release_fixture import create_cost_fixture

from app.core.security import hash_password
from app.database.session import SessionLocal, engine
from app.domain.models import AuthCredential, ProjectMembership
from app.main import app


def main():
    assert os.getenv("PYPMIS_O1BC_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql" and engine.url.database == "o1bc_browser"
    target = Path("/artifacts/browser-fixture.json")
    assert not target.exists(), "Reuse the persistent isolated actors"
    with TestClient(app) as client, SessionLocal() as db:
        f = create_cost_fixture(db, client)
        password_hash = hash_password("O1bc-disposable-only!")
        for label, user in f.users.items():
            db.add(
                AuthCredential(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    provider="local",
                    password_hash=password_hash,
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
            "legacy_project_id": f.legacy_project_id,
            "users": {
                label: {"id": user.id, "email": user.email, "tenant_id": user.tenant_id}
                for label, user in f.users.items()
            },
            "scope_items": f.scope_items,
            "plan_items": f.plan_items,
            "packages": [f.awp_package],
            "schedule_versions": [f.schedule_version],
            "periods": [f.period],
            "cost_profile": f.cost_profile,
            "fixture_scope": "Actual approved Scope, published Plan, AWP package, accepted imported Schedule, open O1A period; isolated actors. No business signoff.",
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {"fixture_created": True, "tenant_id": f.tenant_id, "project_workspace_id": f.project_workspace_id}
            )
        )


if __name__ == "__main__":
    main()
