"""Real O3A Alembic chain in a literal, disposable PostgreSQL container.

No existing container or application database is modified or removed. The
bootstrap is the retained pre-Alembic catalog fixture, not a metadata create_all
or an Alembic stamp. The 0080 downgrade is attempted only before Field data exist.
"""

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o3a-20261118/migration"
NAME = "pypmis-wave-o3a-migration-20261119"
LABEL = "wave-o3a-migration-disposable"
IDENTITY = "o3a_migration"
PORT = "5566"
HEAD = "20261118_0080"


def run(command, *, env=None):
    result = subprocess.run(
        command,
        cwd=ROOT / "backend",
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    with (QA / "commands.log").open("a", encoding="utf-8") as log:
        log.write(" ".join(command) + "\n" + result.stdout + "\n")
    if result.returncode:
        raise RuntimeError(
            f"Command failed with {result.returncode}: {result.stdout[-5000:]}"
        )
    return result.stdout


def sql(statement):
    return run(
        [
            "docker",
            "exec",
            NAME,
            "psql",
            "-X",
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            IDENTITY,
            "-d",
            IDENTITY,
            "-c",
            statement,
        ]
    ).strip()


def main():
    QA.mkdir(parents=True, exist_ok=False)
    started = datetime.now(UTC).isoformat()
    proof = {
        "result": "FAIL",
        "started_at_utc": started,
        "container": NAME,
        "loopback_port": int(PORT),
        "database": IDENTITY,
        "steps": [],
        "seed_or_backfill": False,
        "production_touched": False,
        "existing_data_deleted": False,
    }
    try:
        # Docker itself refuses this literal name if it already exists. There
        # is deliberately no rm, stop, prune, schema reset, stamp or force flag.
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                NAME,
                "--label",
                f"pypmis.scope={LABEL}",
                "-e",
                f"POSTGRES_DB={IDENTITY}",
                "-e",
                f"POSTGRES_USER={IDENTITY}",
                "-e",
                f"POSTGRES_PASSWORD={IDENTITY}",
                "-p",
                f"127.0.0.1:{PORT}:5432",
                "postgres:16-alpine",
            ]
        )
        details = json.loads(run(["docker", "inspect", NAME]))[0]
        assert details["Config"]["Labels"]["pypmis.scope"] == LABEL
        assert details["HostConfig"]["PortBindings"]["5432/tcp"] == [
            {"HostIp": "127.0.0.1", "HostPort": PORT}
        ]
        for _ in range(60):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    NAME,
                    "pg_isready",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    IDENTITY,
                ],
                capture_output=True,
                check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(
                "The disposable PostgreSQL container did not become ready"
            )
        assert (
            sql(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
            )
            == "0"
        )
        fixture = ROOT / "backend/tests/fixtures/o2b_close_pre_alembic_postgres.sql"
        run(["docker", "cp", str(fixture), f"{NAME}:/tmp/bootstrap.sql"])
        run(
            [
                "docker",
                "exec",
                NAME,
                "psql",
                "-X",
                "-q",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                IDENTITY,
                "-d",
                IDENTITY,
                "-f",
                "/tmp/bootstrap.sql",
            ]
        )
        env = dict(os.environ)
        env.update(
            DATABASE_URL=f"postgresql+psycopg://{IDENTITY}:{IDENTITY}@127.0.0.1:{PORT}/{IDENTITY}",
            AUTO_CREATE_SCHEMA="false",
            SEED_DEMO_DATA="false",
        )
        for action, revision in (
            ("upgrade", HEAD),
            ("downgrade", "20261113_0079"),
            ("upgrade", HEAD),
        ):
            run([sys.executable, "-m", "alembic", action, revision], env=env)
            actual = sql("SELECT version_num FROM alembic_version")
            assert actual == revision, (action, revision, actual)
            proof["steps"].append(
                {"action": action, "target": revision, "actual": actual}
            )
        assert sql("SELECT version_num FROM alembic_version") == HEAD
        guards = sql(
            "SELECT count(*) FROM pg_trigger WHERE tgname='tr_o3a_record_guard'"
        )
        consumer_guard = sql(
            "SELECT count(*) FROM pg_trigger WHERE tgname='tr_o3a_consumer_guard'"
        )
        assert guards == "17" and consumer_guard == "1"
        terminal = sql(
            "SELECT encode(tgargs,'escape') FROM pg_trigger "
            "WHERE tgname='tr_o3a_record_guard' AND tgrelid='field_constraint_observations'::regclass"
        )
        assert terminal.startswith("VERIFIED,REJECTED"), terminal
        tables = sql(
            "SELECT string_agg(tablename,',' ORDER BY tablename) FROM pg_tables "
            "WHERE schemaname='public' AND tablename LIKE 'field_%'"
        ).split(",")
        assert len(tables) == 17
        functions = sql(
            "SELECT count(*) FROM pg_proc WHERE proname IN ('o3a_record_guard','o3a_consumer_guard')"
        )
        assert functions == "2"
        proof.update(
            result="PASS",
            head=HEAD,
            record_guard_count=int(guards),
            consumer_guard_count=int(consumer_guard),
            constraint_observation_terminal_guard=terminal,
            field_tables=tables,
            pre_alembic_fixture=str(fixture.relative_to(ROOT)),
            migration_strategy="real upgrade chain no stamp no create_all",
        )
        print(
            f"Migration PASS: real chain to {HEAD}, downgrade to 0079, upgrade to 0080; 17 record guards + 1 consumer guard"
        )
    except Exception as error:
        proof["error"] = str(error)
        raise
    finally:
        proof["finished_at_utc"] = datetime.now(UTC).isoformat()
        (QA / "proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
