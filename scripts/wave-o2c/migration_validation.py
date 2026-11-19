"""Exercise the real migration chain in a newly created disposable container."""

import json
import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2c-20261118/migration"
NAME = "pypmis-wave-o2c-migration-20261118"


def run(command, *, env=None, expected=0):
    result = subprocess.run(
        command,
        cwd=ROOT / "backend",
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    with (QA / "commands.log").open("a", encoding="utf-8") as log:
        log.write(" ".join(command) + "\n" + result.stdout + "\n")
    if result.returncode != expected:
        raise RuntimeError(result.stdout[-4000:])
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    resume = parser.parse_args().resume
    QA.mkdir(parents=True, exist_ok=resume)
    # New literal name and loopback port. Never import or seed the normal application DB.
    if not resume:
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                NAME,
                "--label",
                "pypmis.scope=wave-o2c-migration",
                "-e",
                "POSTGRES_DB=o2c_migration",
                "-e",
                "POSTGRES_USER=o2c_migration",
                "-e",
                "POSTGRES_PASSWORD=o2c_migration",
                "-p",
                "127.0.0.1:5563:5432",
                "postgres:16-alpine",
            ]
        )
    details = json.loads(run(["docker", "inspect", NAME]))[0]
    assert details["Config"]["Labels"]["pypmis.scope"] == "wave-o2c-migration"
    assert details["HostConfig"]["PortBindings"]["5432/tcp"] == [
        {"HostIp": "127.0.0.1", "HostPort": "5563"}
    ]
    for _ in range(40):
        status = subprocess.run(
            [
                "docker",
                "exec",
                NAME,
                "pg_isready",
                "-h",
                "127.0.0.1",
                "-U",
                "o2c_migration",
            ],
            capture_output=True,
        )
        if status.returncode == 0:
            break
        # The helper runs in its own PTY; only short database-readiness waits.
        import time

        time.sleep(0.5)
    count = run(
        [
            "docker",
            "exec",
            NAME,
            "psql",
            "-X",
            "-At",
            "-U",
            "o2c_migration",
            "-d",
            "o2c_migration",
            "-c",
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'",
        ]
    ).strip()
    assert count == "0", "Refusing to bootstrap a nonempty database"
    run(
        [
            "docker",
            "cp",
            str(ROOT / "backend/tests/fixtures/o2b_close_pre_alembic_postgres.sql"),
            f"{NAME}:/tmp/bootstrap.sql",
        ]
    )
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
            "o2c_migration",
            "-d",
            "o2c_migration",
            "-f",
            "/tmp/bootstrap.sql",
        ]
    )
    env = dict(os.environ)
    env.update(
        DATABASE_URL="postgresql+psycopg://o2c_migration:o2c_migration@127.0.0.1:5563/o2c_migration",
        AUTO_CREATE_SCHEMA="false",
        SEED_DEMO_DATA="false",
    )
    steps = []
    for action, revision in (
        ("upgrade", "20261111_0078"),
        ("upgrade", "20261113_0079"),
        ("downgrade", "20261111_0078"),
        ("upgrade", "20261113_0079"),
    ):
        run([sys.executable, "-m", "alembic", action, revision], env=env)
        steps.append(f"{action} {revision}")
    head = run(
        [
            "docker",
            "exec",
            NAME,
            "psql",
            "-X",
            "-At",
            "-U",
            "o2c_migration",
            "-d",
            "o2c_migration",
            "-c",
            "SELECT version_num FROM alembic_version",
        ]
    ).strip()
    assert head == "20261113_0079"
    guard_count = run(
        [
            "docker",
            "exec",
            NAME,
            "psql",
            "-X",
            "-At",
            "-U",
            "o2c_migration",
            "-d",
            "o2c_migration",
            "-c",
            "SELECT count(*) FROM pg_trigger WHERE tgname='tr_o2c_record_guard'",
        ]
    ).strip()
    assert guard_count == "17"
    (QA / "proof.json").write_text(
        json.dumps(
            {
                "result": "PASS",
                "observed_at_utc": datetime.now(UTC).isoformat(),
                "container": NAME,
                "head": head,
                "record_guard_count": int(guard_count),
                "steps": steps,
                "seed_or_backfill": False,
                "production_touched": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"Migration PASS: {len(steps)} steps, {guard_count} guarded tables, head {head}"
    )


if __name__ == "__main__":
    main()
