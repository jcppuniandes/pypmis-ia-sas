"""Persistent isolated actors for real Scope browser UAT, never production data."""

import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from tests.scope_release_fixture import create_scope_fixture

from app.core.security import hash_password
from app.database.session import SessionLocal, engine
from app.domain.models import AuthCredential, ProjectMembership
from app.modules.operational_context.schemas import ActionIn, ProfileCreateIn
from app.modules.operational_context.service import DEFAULT_PROFILE, OperationalContextService


def main():
    assert os.getenv("PYPMIS_O1BA_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql" and engine.url.database == "o1ba"
    target = Path(os.getenv("PYPMIS_O1BA_BROWSER_MANIFEST", "/artifacts/browser-fixture.json"))
    assert target.resolve().is_relative_to(Path("/artifacts")), "Keep private fixture evidence inside artifacts"
    assert not target.exists(), "Reuse existing browser actors; never overwrite their identity proof"
    with SessionLocal() as db:
        f = create_scope_fixture(db)
        for label, user in f.users.items():
            db.add(
                AuthCredential(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    provider="local",
                    password_hash=hash_password("O1ba-disposable-only!"),
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
        prepared = OperationalContextService(db, f.tenant_id, f.users["admin"].id).create_profile(
            ProfileCreateIn(
                code=f"O1BA-OP-{uuid4().hex[:8]}",
                name="O1B-A operational prerequisite",
                content_json=deepcopy(DEFAULT_PROFILE),
            ),
            f"op-create-{uuid4()}",
        )
        OperationalContextService(db, f.tenant_id, f.users["publisher"].id).publish_profile(
            prepared["id"],
            ActionIn(reason="Independent operational prerequisite for isolated Scope UAT"),
            prepared["version"],
            f"op-publish-{uuid4()}",
        )
        result = {
            "tenant_id": f.tenant_id,
            "tenant_slug": f.tenant.slug,
            "users": {
                key: {"id": value.id, "email": value.email, "tenant_id": value.tenant_id}
                for key, value in f.users.items()
            },
            "workspaces": {
                key: {"id": value.id, "external_key": value.external_key, "name": value.name}
                for key, value in f.workspaces.items()
            },
            "legacy_project_id": f.legacy_project_id,
            "fixture_scope": "Isolated existing canonical states, actual O1A prerequisite commands. Real PG, credentials and RBAC. No creation/activation or business signoff claimed.",
        }
        target.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"fixture_created": True, "tenant_id": f.tenant_id, "workspace_id": f.project_workspace_id}))


if __name__ == "__main__":
    main()
