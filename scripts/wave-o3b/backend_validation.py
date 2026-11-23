"""Bounded final O3B validation against the named disposable PostgreSQL only."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o3b-20261119"
URL = "postgresql+psycopg://o3b:o3b@127.0.0.1:5567/o3b"
POLICY = [
    "awp_policy",
    "contracts_core_policy",
    "contracts_security_policy",
    "cost_financial_policy",
    "cost_foundation_policy",
    "engineering_core_policy",
    "engineering_integration_policy",
    "field_operations_consumer_policy",
    "field_operations_core_policy",
    "forecast_foundation_policy",
    "forecast_reporting_policy",
    "procurement_sourcing_policy",
    "progress_foundation_policy",
    "progress_integration_policy",
    "quality_execution_policy",
    "schedule_foundation_policy",
    "quality_source_policy",
    "quality_consumer_policy",
]


def snapshot():
    paths = list((ROOT / "backend/app/modules/quality").glob("*.py"))
    paths += list((ROOT / "backend/tests").glob("*quality*.py"))
    paths += [
        ROOT / "backend/app/modules" / name / "service.py"
        for name in ("awp", "progress_foundation")
    ]
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", choices=("policy", "postgres"))
    parser.add_argument("--cut", required=True)
    args = parser.parse_args()
    target = QA / args.cut
    assert target.parent == QA
    target.mkdir(exist_ok=False)
    before = snapshot()
    env = os.environ | {
        "DATABASE_URL": URL,
        "PYPMIS_TEST_DATABASE_URL": URL,
        "PYPMIS_O3B_FIXTURE": "disposable-only",
        "AUTO_CREATE_SCHEMA": "false",
        "SEED_DEMO_DATA": "false",
        "RATE_LIMIT_ENABLED": "false",
        "LOG_LEVEL": "WARNING",
        "DOCUMENT_STORAGE_PATH": str(target / "document-storage"),
        "O3B_CORE_CUT": args.cut + "-core",
    }
    files = (
        [f"tests/test_{name}.py" for name in POLICY]
        if args.suite == "policy"
        else [
            "tests/test_quality_core_release.py",
            "tests/test_quality_execution_release.py",
            "tests/test_quality_consumer_release.py",
        ]
    )
    junit = target / "junit.xml"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
        f"--junitxml={junit}",
        *files,
    ]
    started = datetime.now(UTC).isoformat()
    with (target / "run.log").open("x", encoding="utf-8") as output:
        result = subprocess.run(
            command,
            cwd=ROOT / "backend",
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            check=False,
        )
    unchanged = before == snapshot()
    cases = list(ET.parse(junit).iter("testcase")) if junit.exists() else []
    counts = {
        "tests": len(cases),
        "failures": sum(case.find("failure") is not None for case in cases),
        "errors": sum(case.find("error") is not None for case in cases),
        "skipped": sum(case.find("skipped") is not None for case in cases),
    }
    proof = {
        "status": "PASS"
        if result.returncode == 0
        and unchanged
        and counts["tests"]
        and not any(counts[key] for key in ("failures", "errors", "skipped"))
        else "FAIL",
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "suite": args.suite,
        "database": "o3b@127.0.0.1:5567/o3b",
        "ordinary_database_used": False,
        "exit_code": result.returncode,
        "counts": counts,
        "source_unchanged": unchanged,
        "source_sha256": before,
    }
    (target / "result.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in proof.items() if key != "source_sha256"}
        ),
        flush=True,
    )
    if proof["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
