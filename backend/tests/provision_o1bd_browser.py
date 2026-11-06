"""Persist real upstream Progress prerequisites and independent disposable actors."""

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from tests.progress_release_fixture import create_progress_fixture

from app.core.security import hash_password
from app.database.session import SessionLocal, engine
from app.domain.models import AuthCredential, ProjectMembership
from app.main import app


def main():
    assert os.getenv("PYPMIS_O1BD_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql" and engine.url.database == "o1bd_browser"
    target = Path("/artifacts/browser-fixture.json")
    assert not target.exists(), "Reuse the persistent isolated actors"
    with TestClient(app) as client, SessionLocal() as db:
        f = create_progress_fixture(db, client, real_model=True, publish_profile=False)
        password_hash = hash_password("O1bd-disposable-only!")
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
            "packages": f.packages,
            "schedule_versions": [f.schedule_version],
            "periods": [f.period],
            "cost_profile": f.cost_profile,
            "scope_baseline": f.scope_baseline,
            "schedule_baseline": f.schedule_baseline,
            "cost_baseline": f.cost_baseline,
            "cost_budget": f.cost_budget,
            "cost_account": f.cost_account,
            "cost_actual": f.cost_actual,
            "cost_mappings": f.cost_mappings,
            "four_d_profile": f.four_d_profile,
            "model": f.model,
            "derived": f.derived,
            "activity_plans": f.activity_plans,
            "activity_phases": f.activity_phases,
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
