"""Reproducible tests with explicit disposable identity and recorded provenance."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2c-20261118"
BACKEND = ROOT / "backend"
URL = "postgresql+psycopg://o2c:o2c@127.0.0.1:5561/o2c"
UNITS = (
    "test_workspace_context.py",
    "test_awp_policy.py",
    "test_cost_financial_policy.py",
    "test_cost_foundation_policy.py",
    "test_engineering_core_policy.py",
    "test_engineering_integration_policy.py",
    "test_forecast_foundation_policy.py",
    "test_forecast_reporting_policy.py",
    "test_procurement_consumer_sources.py",
    "test_procurement_sourcing_policy.py",
    "test_progress_foundation_policy.py",
    "test_progress_integration_policy.py",
    "test_scope_foundation_imports.py",
    "test_contracts_core_policy.py",
)
PG = ("test_contracts_foundation_release.py",)
SCHEDULE = ("test_schedule_foundation_policy.py",)


def digest():
    paths = [
        path
        for folder in ("backend/app", "backend/alembic", "frontend/src")
        for path in (ROOT / folder).rglob("*")
        if path.is_file() and path.suffix in {".py", ".sql", ".ts", ".tsx", ".css"}
    ]
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=("unit", "core", "schedule"))
    parser.add_argument("attempt")
    args = parser.parse_args()
    if not args.attempt.replace("-", "").isalnum():
        raise RuntimeError("Use a unique literal attempt")
    folder = QA / f"{args.suite}-{args.attempt}"
    folder.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    env.update(
        PYPMIS_PYTEST_RUNTIME_DIR=str(folder / "runtime"),
        LOG_LEVEL="WARNING",
        RATE_LIMIT_ENABLED="false",
        DOCUMENT_STORAGE_PATH=str(QA / "api-storage"),
    )
    if args.suite != "unit":
        env.update(
            PYPMIS_TEST_DATABASE_URL=URL,
            DATABASE_URL=URL,
            PYPMIS_O2C_FIXTURE="disposable-only",
            PYPMIS_O2C_PERFORMANCE=str(QA / "performance-final.json"),
            PYPMIS_O2C_SCENARIO=str(folder / "scenario.json"),
        )
    else:
        env.pop("PYPMIS_TEST_DATABASE_URL", None)
        env.pop("PYPMIS_O2C_FIXTURE", None)
    before = digest()
    files = {"core": PG, "schedule": SCHEDULE, "unit": UNITS}[args.suite]
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
        "-q",
        *[f"tests/{name}" for name in files],
        "--tb=short",
        f"--junitxml={folder / 'junit.xml'}",
    ]
    started = datetime.now(UTC).isoformat()
    with (folder / "run.log").open("x", encoding="utf-8") as log:
        result = subprocess.run(
            command, cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT
        )
    after = digest()
    (folder / "proof.json").write_text(
        json.dumps(
            {
                "suite": args.suite,
                "started_at_utc": started,
                "completed_at_utc": datetime.now(UTC).isoformat(),
                "command": command,
                "exit_code": result.returncode,
                "source_stable": before == after,
                "source_before_sha256": before,
                "source_after_sha256": after,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"{args.suite}: exit={result.returncode}; source_stable={before == after}; {folder}"
    )
    print((folder / "run.log").read_text("utf-8")[-5000:])
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
