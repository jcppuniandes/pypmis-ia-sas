"""Approved Wave 4 browser models and independent actors in a disposable DB.

The fixture uses real source-readiness/model approval and existing prerequisite
workflows. It never seeds production or produces synthetic completed runs.
"""

from __future__ import annotations

import json
import os

from sqlalchemy import select

from app.database.session import Base, SessionLocal, engine
from app.domain.models import Project, UserAccount


def main() -> None:
    if os.getenv("PYPMIS_QRA_ENGINE_BROWSER_FIXTURE") != "disposable-only" or (
        engine.dialect.name != "postgresql"
        or engine.url.database not in {"qra_foundation_browser", "qra_engine_browser"}
    ):
        raise RuntimeError("Wave 4 browser provisioning is restricted to explicitly disposable PostgreSQL")

    # Only imported after the database/environment guard.
    from tests.provision_qra_foundation_browser import credential
    from tests.test_capital_allocation_wave2a import _user
    from tests.test_owner_capability_wave3b import _grant
    from tests.test_qra_engine import _engine_fixture

    from app.database.seed import ensure_membership, seed_demo
    from app.modules.qra_foundation.models import QraModelDefinition

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_demo(db)
        existing = db.scalar(select(UserAccount).where(UserAccount.email == "qra.engine.authority@demo.local"))
        if existing is not None:
            models = db.scalars(
                select(QraModelDefinition)
                .where(
                    QraModelDefinition.tenant_id == existing.tenant_id,
                    QraModelDefinition.title.like("Approved Wave 4%"),
                )
                .order_by(QraModelDefinition.id)
            ).all()
            print(
                json.dumps(
                    {
                        "database": engine.url.database,
                        "fixture": "reused",
                        "project_workspace_id": models[0].project_workspace_id if models else None,
                    }
                ),
                flush=True,
            )
            return
        fixture = _engine_fixture(db, contexts=True)
        author, authority, workspace = fixture["author"], fixture["reviewer"], fixture["project"]
        credential(db, authority, "qra.engine.authority@demo.local", "QRA Engine Independent Analysis Authority")
        _grant(db, authority, "definition_reviewer")
        reader = _user(db, author.tenant_id, "qra-engine-reader")
        credential(db, reader, "qra.engine.reader@demo.local", "QRA Engine Read-only Project Actor")
        _grant(db, reader, "project_definition_viewer", scope_type="workspace", workspace_id=workspace.id)
        shell = db.scalar(select(Project).where(Project.tenant_id == author.tenant_id).order_by(Project.id))
        if shell is None:
            raise RuntimeError("Browser shell requires an existing disposable operational Project")
        for actor, role in ((authority, "Control Manager"), (reader, "Executive")):
            ensure_membership(db, author.tenant_id, shell.id, actor.id, role)
        db.commit()
        for model in fixture["models"].values():
            assert fixture["engine"].preflight(model["id"])["eligible"], (
                "Fixture must remain current after credential setup"
            )
        print(
            json.dumps(
                {
                    "database": engine.url.database,
                    "project_workspace_id": workspace.id,
                    "model_ids": {key: value["id"] for key, value in fixture["models"].items()},
                    "authority_email": authority.email,
                    "reader_email": reader.email,
                    "run_count": 0,
                    "source_authority": "IMPORTED_P6_XML_NO_WRITE_BACK",
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
