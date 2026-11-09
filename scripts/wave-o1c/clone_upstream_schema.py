"""Reuse the migrated O1B-D schema only in verified-empty O1C databases."""

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ["docker", "compose", "-f", str(ROOT / "docker-compose.wave-o1bd.yml")]
TARGET = ["docker", "compose", "-f", str(ROOT / "docker-compose.wave-o1c.yml")]
TARGETS = {"db": "o1c", "browser-db": "o1c_browser", "migration-db": "o1c_migration"}


def query(command, service, user, database, statement):
    return subprocess.check_output(
        command
        + [
            "exec",
            "-T",
            service,
            "psql",
            "-U",
            user,
            "-d",
            database,
            "-v",
            "ON_ERROR_STOP=1",
            "-Atc",
            statement,
        ],
        cwd=ROOT,
        text=True,
    ).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=tuple(TARGETS))
    target = parser.parse_args().target
    database = TARGETS[target]
    assert (
        query(SOURCE, "db", "o1bd", "o1bd", "SELECT version_num FROM alembic_version")
        == "20261104_0074"
    )
    assert (
        query(
            TARGET,
            target,
            "o1c",
            database,
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'",
        )
        == "0"
    )
    schema = subprocess.check_output(
        SOURCE
        + [
            "exec",
            "-T",
            "db",
            "pg_dump",
            "-U",
            "o1bd",
            "-d",
            "o1bd",
            "--schema-only",
            "--no-owner",
            "--no-privileges",
        ],
        cwd=ROOT,
    )
    subprocess.run(
        TARGET
        + [
            "exec",
            "-T",
            target,
            "psql",
            "-U",
            "o1c",
            "-d",
            database,
            "-v",
            "ON_ERROR_STOP=1",
            "-q",
        ],
        cwd=ROOT,
        input=schema,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    query(
        TARGET,
        target,
        "o1c",
        database,
        "INSERT INTO alembic_version(version_num) VALUES ('20261104_0074')",
    )
    assert (
        query(
            TARGET,
            target,
            "o1c",
            database,
            "SELECT count(*) FROM enterprise_workspaces",
        )
        == "0"
    )
    print(
        json.dumps(
            {
                "database": database,
                "schema_only": True,
                "business_data_copied": False,
                "head": "20261104_0074",
                "source": "Previously migrated isolated O1BD database",
            }
        )
    )


if __name__ == "__main__":
    main()
