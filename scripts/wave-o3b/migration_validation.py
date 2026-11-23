"""Validate the real 0081 round trip on the literal empty O3B disposable database."""

import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o3b-20261119/migration"
URL = "postgresql+psycopg://o3b:o3b@127.0.0.1:5567/o3b"
REVISION = "20261120_0081"


def main():
    info = json.loads(
        subprocess.check_output(
            ["docker", "inspect", "pypmis-wave-o3b-validation"], text=True
        )
    )[0]
    assert info["Config"]["Labels"]["pypmis.scope"] == "wave-o3b-disposable"
    assert info["HostConfig"]["PortBindings"]["5432/tcp"] == [
        {"HostIp": "127.0.0.1", "HostPort": "5567"}
    ]
    spec = importlib.util.spec_from_file_location(
        "quality_migration",
        ROOT / "backend/alembic/versions/20261120_0081_quality_management.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(URL)
    QA.mkdir(parents=True, exist_ok=True)
    with engine.connect() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == REVISION
        for table in migration.TABLES:
            assert db.scalar(text(f"SELECT count(*) FROM {table}")) == 0, (
                "Never downgrade populated governed facts"
            )
        triggers = db.execute(
            text(
                "SELECT event_object_table,trigger_name FROM information_schema.triggers WHERE trigger_name LIKE 'tr_o3b_%' GROUP BY event_object_table,trigger_name ORDER BY 1,2"
            )
        ).all()
        assert len(triggers) == 19
    env = os.environ | {
        "DATABASE_URL": URL,
        "AUTO_CREATE_SCHEMA": "false",
        "SEED_DEMO_DATA": "false",
    }
    results = []
    for direction, revision in (("downgrade", "20261118_0080"), ("upgrade", REVISION)):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", direction, revision],
            cwd=ROOT / "backend",
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        (QA / f"{direction}.log").write_text(
            result.stdout + result.stderr, encoding="utf-8"
        )
        assert result.returncode == 0, result.stderr[-4000:]
        with engine.connect() as db:
            current = db.scalar(text("SELECT version_num FROM alembic_version"))
            assert current == revision
            count = db.scalar(
                text(
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'quality_%'"
                )
            )
            assert count == (0 if direction == "downgrade" else 17)
        results.append(
            {
                "direction": direction,
                "revision": current,
                "quality_tables": count,
                "status": "PASS",
            }
        )
    proof = {
        "status": "PASS",
        "database": "o3b@127.0.0.1:5567/o3b",
        "checked_at": datetime.now(UTC).isoformat(),
        "initial_upgrade": REVISION,
        "empty_round_trip": results,
        "scoped_guarded_tables": len(migration.TABLES),
        "guard_triggers": len(triggers),
        "ordinary_database_used": False,
    }
    (QA / "round-trip.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
