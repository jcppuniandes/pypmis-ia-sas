"""Clone only the validated 0075 schema into three verified-empty O2A databases."""

import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "o1c_clone", ROOT / "scripts/wave-o1c/clone_upstream_schema.py"
)
assert SPEC and SPEC.loader
upstream = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upstream)
SOURCE = ["docker", "compose", "-f", str(ROOT / "docker-compose.wave-o1c.yml")]
TARGET = ["docker", "compose", "-f", str(ROOT / "docker-compose.wave-o2a.yml")]
TARGETS = {"db": "o2a", "browser-db": "o2a_browser", "migration-db": "o2a_migration"}
REVISION = "20261106_0075"


def main():
    assert (
        upstream.query(
            SOURCE, "db", "o1c", "o1c", "SELECT version_num FROM alembic_version"
        )
        == REVISION
    )
    for service, name in TARGETS.items():
        assert (
            upstream.query(
                TARGET,
                service,
                "o2a",
                name,
                "SELECT current_database() || '/' || current_user",
            )
            == f"{name}/o2a"
        )
        assert (
            upstream.query(
                TARGET,
                service,
                "o2a",
                name,
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'",
            )
            == "0"
        ), f"{name} is not empty"
    schema = subprocess.check_output(
        SOURCE
        + [
            "exec",
            "-T",
            "db",
            "pg_dump",
            "-U",
            "o1c",
            "-d",
            "o1c",
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
                "o2a",
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
            "o2a",
            name,
            f"INSERT INTO alembic_version(version_num) VALUES ('{REVISION}')",
        )
        assert (
            upstream.query(
                TARGET,
                service,
                "o2a",
                name,
                "SELECT count(*) FROM enterprise_workspaces",
            )
            == "0"
        )
        print(
            json.dumps(
                {
                    "database": name,
                    "schema_only": True,
                    "baseline": REVISION,
                    "business_records_copied": False,
                }
            )
        )


if __name__ == "__main__":
    main()
