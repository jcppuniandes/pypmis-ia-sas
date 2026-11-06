"""Copy schema only from a truly migrated O1B-D test DB into empty isolated DBs.

This is browser/test setup, never presented as empty-to-head migration proof.
No business data is exported or copied. Exact disposable Compose targets only.
"""

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "docker-compose.wave-o1bd.yml")]
TARGETS = {"browser-db": "o1bd_browser", "migration-db": "o1bd_migration"}


def sql(service, database, statement):
    return subprocess.check_output(
        COMPOSE
        + [
            "exec",
            "-T",
            service,
            "psql",
            "-U",
            "o1bd",
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
        sql("db", "o1bd", "SELECT version_num FROM alembic_version") == "20261104_0074"
    )
    assert (
        sql(
            target,
            database,
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'",
        )
        == "0"
    )
    schema = subprocess.check_output(
        COMPOSE
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
        COMPOSE
        + [
            "exec",
            "-T",
            target,
            "psql",
            "-U",
            "o1bd",
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
    sql(
        target,
        database,
        "INSERT INTO alembic_version(version_num) VALUES ('20261104_0074')",
    )
    assert sql(target, database, "SELECT count(*) FROM enterprise_workspaces") == "0"
    print(
        json.dumps(
            {
                "target": database,
                "schema_only": True,
                "business_data_copied": False,
                "source": "Actually migrated o1bd PostgreSQL",
                "head": "20261104_0074",
            }
        )
    )


if __name__ == "__main__":
    main()
