"""Run CLOSE-2 real HTTP tests on the guarded disposable PostgreSQL database."""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import file_digest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2b-close2-20261112"
HEAD = "20261111_0078"
CASES = {
    "progress-lineage": ["test_procurement_close2_progress.py"],
    "forecast-sources": ["test_procurement_close2_forecast.py"],
    "auth-write": ["test_procurement_close2_auth.py"],
    "postgres": [
        "test_procurement_consumer_release.py",
        "test_procurement_consumer_sources.py",
    ],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=CASES)
    parser.add_argument("attempt")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", args.attempt):
        parser.error("Invalid attempt label")
    evidence = QA / args.suite / args.attempt
    freeze = QA / "release" / f"freeze-{args.attempt}.json"
    if not freeze.is_file() and not args.attempt.startswith("diag-"):
        raise RuntimeError("Final evidence requires a captured freeze")
    if freeze.is_file():
        from validate import snapshot

        frozen_source = json.loads(freeze.read_text("utf-8"))["source"]
        if frozen_source != snapshot():
            raise RuntimeError("Source does not match the final freeze")
    subprocess.run(
        ["git", "check-ignore", "-q", "--", str(evidence / "private")],
        cwd=ROOT,
        check=True,
    )
    url = os.getenv("PYPMIS_CLOSE2_CONSUMER_URL")
    if not url:
        raise SystemExit(
            "Set the disposable CLOSE2 consumer connection; never use the application DATABASE_URL."
        )
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    if (
        parsed.drivername,
        parsed.host,
        parsed.port,
        parsed.database,
        parsed.username,
        parsed.query,
    ) != (
        "postgresql+psycopg",
        "127.0.0.1",
        5558,
        "o2b_close_consumers",
        "o2b_close_migration",
        {},
    ):
        raise SystemExit("Connection does not match disposable CLOSE2 target")
    env = {
        key: value for key, value in os.environ.items() if not key.startswith("PYPMIS_")
    }
    env.update(
        DATABASE_URL=url,
        PYPMIS_TEST_DATABASE_URL=url,
        PYPMIS_O2B_CLOSE_FIXTURE="disposable-only",
        PYPMIS_CLOSE2_EVIDENCE=str(evidence),
        PYPMIS_PYTEST_RUNTIME_DIR=str(evidence / "runtime"),
        AUTO_CREATE_SCHEMA="false",
        SEED_DEMO_DATA="false",
        RATE_LIMIT_ENABLED="false",
        AUTH_SECRET_KEY="local-disposable-close2-test-fixture",
        ALLOWED_HOSTS="localhost,127.0.0.1,testserver",
    )
    from sqlalchemy import create_engine, text

    with create_engine(parsed).connect() as conn:
        row = conn.execute(
            text(
                "SELECT current_database(),current_user,current_setting('server_version'),"
                "(SELECT version_num FROM alembic_version)"
            )
        ).one()
        assert (
            row[0:2] == (parsed.database, parsed.username)
            and row[2].startswith("16.")
            and row[3] == HEAD
        )
    evidence.mkdir(parents=True, exist_ok=False)
    junit, log = evidence / "junit.xml", evidence / "pytest.log"
    started = datetime.now(UTC).isoformat()
    with log.open("xb") as stream:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-o",
                "addopts=",
                "-p",
                "no:cacheprovider",
                "--tb=short",
                f"--basetemp={evidence / 'temp'}",
                f"--junitxml={junit}",
                *(f"tests/{name}" for name in CASES[args.suite]),
            ],
            cwd=ROOT / "backend",
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
        )
    evidence_files = [junit, *evidence.glob("*.json")]
    payload = {
        "result": "PASS" if result.returncode == 0 else "FAIL",
        "started_at_utc": started,
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "alembic_head": HEAD,
        "postgres_version": row[2],
        "database": parsed.database,
        "exit_code": result.returncode,
        "evidence_sha256": {},
    }
    if freeze.is_file():
        payload["source_unchanged"] = snapshot() == frozen_source
        payload["freeze_sha256"] = file_digest(freeze.open("rb"), "sha256").hexdigest()
        if not payload["source_unchanged"]:
            payload["result"] = "FAIL"
    for file in evidence_files:
        if file.is_file():
            with file.open("rb") as stream:
                payload["evidence_sha256"][file.name] = file_digest(
                    stream, "sha256"
                ).hexdigest()
    (evidence / "consumer-proof.json").write_text(
        json.dumps(payload, indent=2), "utf-8"
    )
    print(f"{args.suite}: {payload['result']} ({evidence})")
    return int(payload["result"] != "PASS")


if __name__ == "__main__":
    sys.exit(main())
