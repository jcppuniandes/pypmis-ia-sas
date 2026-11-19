"""Seed empty, isolated O2B schemas from the validated O2A migration only."""

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "o2b_schema_query", ROOT / "scripts/wave-o1c/clone_upstream_schema.py"
)
assert SPEC and SPEC.loader
upstream = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upstream)
SOURCE = ["docker", "compose", "-f", str(ROOT / "docker-compose.wave-o2a.yml")]
TARGET = ["docker", "compose", "-f", str(ROOT / "docker-compose.wave-o2b.yml")]
TARGETS = {"db": "o2b", "browser-db": "o2b_browser", "migration-db": "o2b_migration"}
REVISION = "20261109_0076"


def main():
    assert (
        upstream.query(
            SOURCE, "db", "o2a", "o2a", "SELECT version_num FROM alembic_version"
        )
        == REVISION
    )
    for service, name in TARGETS.items():
        assert (
            upstream.query(
                TARGET,
                service,
                "o2b",
                name,
                "SELECT current_database() || '/' || current_user",
            )
            == f"{name}/o2b"
        )
        count = upstream.query(
            TARGET,
            service,
            "o2b",
            name,
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'",
        )
        assert count == "0", f"{name} is not empty"
    schema = subprocess.check_output(
        SOURCE
        + [
            "exec",
            "-T",
            "db",
            "pg_dump",
            "-U",
            "o2a",
            "-d",
            "o2a",
            "--schema-only",
            "--no-owner",
            "--no-privileges",
        ],
        cwd=ROOT,
    )
    for service, name in TARGETS.items():
        subprocess.run(
            TARGET
            + [
                "exec",
                "-T",
                service,
                "psql",
                "-X",
                "-U",
                "o2b",
                "-d",
                name,
                "-v",
                "ON_ERROR_STOP=1",
                "-q",
                "-1",
            ],
            cwd=ROOT,
            input=schema,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        upstream.query(
            TARGET,
            service,
            "o2b",
            name,
            f"INSERT INTO alembic_version(version_num) VALUES ('{REVISION}')",
        )
        assert (
            upstream.query(
                TARGET,
                service,
                "o2b",
                name,
                "SELECT count(*) FROM enterprise_workspaces",
            )
            == "0"
        )
        print(
            json.dumps(
                {
                    "database": name,
                    "baseline": REVISION,
                    "schema_only": True,
                    "business_records_copied": False,
                }
            )
        )


if __name__ == "__main__":
    main()
