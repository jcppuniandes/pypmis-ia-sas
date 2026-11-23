"""Initialize a new literal O3B container, never the application database."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o3b-20261119/database"
NAME = "pypmis-wave-o3b-validation"


def run(args, *, env=None):
    result = subprocess.run(
        args, cwd=ROOT / "backend", env=env, text=True, capture_output=True, check=False
    )
    with (QA / "commands.log").open("a", encoding="utf-8") as log:
        log.write(" ".join(args) + "\n" + result.stdout + result.stderr + "\n")
    if result.returncode:
        raise RuntimeError(result.stderr[-4000:] or result.stdout[-4000:])
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    resume = parser.parse_args().resume
    QA.mkdir(parents=True, exist_ok=True)
    if not resume:
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                NAME,
                "--label",
                "pypmis.scope=wave-o3b-disposable",
                "-e",
                "POSTGRES_DB=o3b",
                "-e",
                "POSTGRES_USER=o3b",
                "-e",
                "POSTGRES_PASSWORD=o3b",
                "-p",
                "127.0.0.1:5567:5432",
                "postgres:16-alpine",
            ]
        )
    info = json.loads(run(["docker", "inspect", NAME]))[0]
    assert info["Config"]["Labels"]["pypmis.scope"] == "wave-o3b-disposable"
    assert info["HostConfig"]["PortBindings"]["5432/tcp"] == [
        {"HostIp": "127.0.0.1", "HostPort": "5567"}
    ]
    for _ in range(40):
        result = subprocess.run(
            ["docker", "exec", NAME, "pg_isready", "-U", "o3b"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            break
        time.sleep(0.5)
    for attempt in range(40):
        try:
            count = run(
                [
                    "docker",
                    "exec",
                    NAME,
                    "psql",
                    "-X",
                    "-At",
                    "-U",
                    "o3b",
                    "-d",
                    "o3b",
                    "-c",
                    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'",
                ]
            ).strip()
            break
        except RuntimeError:
            if attempt == 39:
                raise
            time.sleep(0.5)
    assert count == "0", "Refuse to bootstrap a nonempty database"
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
            "-U",
            "o3b",
            "-d",
            "o3b",
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            "/tmp/bootstrap.sql",
        ]
    )
    env = os.environ | {
        "DATABASE_URL": "postgresql+psycopg://o3b:o3b@127.0.0.1:5567/o3b",
        "AUTO_CREATE_SCHEMA": "false",
        "SEED_DEMO_DATA": "false",
    }
    run([sys.executable, "-m", "alembic", "upgrade", "20261118_0080"], env=env)
    print("O3B disposable PostgreSQL initialized through actual Alembic 0080")


if __name__ == "__main__":
    main()
