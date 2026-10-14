"""Actual FFA/BC/FID and QRA evidence browser fixture, disposable PostgreSQL only."""

import json
import os
from pathlib import Path

from sqlalchemy import inspect, select, text

from app.database.session import Base, SessionLocal, engine
from app.domain.models import UserAccount


def main():
    if os.getenv("PYPMIS_QRA_EVIDENCE_BROWSER_FIXTURE") != "disposable-only" or (
        engine.dialect.name != "postgresql" or engine.url.database != "qra_evidence_browser"
    ):
        raise RuntimeError("Evidence browser provisioning requires explicitly disposable PostgreSQL")

    # Imports and all mutations happen only after the restrictive DB guard.
    from alembic import command
    from alembic.config import Config
    from tests.provision_qra_foundation_browser import credential
    from tests.qra_evidence_fixture import evidence_fixture
    from tests.test_capital_allocation_wave2a import _user
    from tests.test_owner_capability_wave3b import _grant

    from app.database.seed import ensure_membership, seed_demo
    from app.domain.models import Project

    Base.metadata.create_all(
        engine,
        tables=[table for table in Base.metadata.sorted_tables if table.name not in {"qra_runs", "qra_run_reviews"}],
    )
    with engine.connect() as connection:
        current = (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            if inspect(connection).has_table("alembic_version")
            else None
        )
        if current is None and inspect(connection).has_table("qra_runs"):
            raise RuntimeError("An unversioned engine schema is not a valid migrated browser baseline")
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    if current is None:
        command.stamp(config, "20261009_0067")
    command.upgrade(config, "head")
    with SessionLocal() as db:
        seed_demo(db)
        marker = db.scalar(select(UserAccount).where(UserAccount.email == "qra.evidence.reviewer@demo.local"))
        if marker is not None:
            print(json.dumps({"fixture": "reused", "database": engine.url.database}), flush=True)
            return
        f = evidence_fixture(db)
        credential(db, f["reviewer"], "qra.evidence.reviewer@demo.local", "QRA Evidence Independent Reviewer")
        reader = _user(db, f["author"].tenant_id, "qra-evidence-reader")
        credential(db, reader, "qra.evidence.reader@demo.local", "QRA Evidence Read-only Actor")
        for role in ("investment_gate_preparation_viewer", "business_case_viewer", "project_definition_viewer"):
            _grant(db, reader, role)
        shell = db.scalar(select(Project).where(Project.tenant_id == f["author"].tenant_id).order_by(Project.id))
        for actor, role in ((f["reviewer"], "Control Manager"), (reader, "Executive")):
            ensure_membership(db, f["author"].tenant_id, shell.id, actor.id, role)
        db.commit()
        for kind in ("cost", "schedule"):
            evidence = f["engine"].provider_evidence(f["project"].id, f"{kind.upper()}_QRA")
            assert evidence["status"] == "AVAILABLE" and evidence["source_current"]
        print(
            json.dumps(
                {
                    "database": engine.url.database,
                    "fixture": "actual_service_stack",
                    "project_workspace_id": f["project"].id,
                    "portfolio_workspace_id": f["portfolio"].id,
                    "profile_id": f["profile"].id,
                    "baseline_policy_id": f["baseline_policy"].id,
                    "baseline_bc_id": f["business_case"].id,
                    "historical_preparation_id": f["historical_preparation"].id,
                    "run_ids": {kind: run["id"] for kind, run in f["runs"].items()},
                    "run_execution": "ACTUAL_KERNEL_AND_WORKER_SERVICE_BROKER_DISPATCH_OMITTED_DURING_TEST_SETUP",
                    "gate_never_executes_qra": True,
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
