"""Run unchanged functional release suites on dedicated PostgreSQL databases at the frozen head."""

import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from chromium_gate import BACKEND, ROOT, digest, git, run, snapshot, utc, write

QA = ROOT / "outputs/.qa/wave-o2b-close-20261111/postgres-regression"
SUITES = {
    "o1": (
        "o1c",
        5550,
        (
            "test_workspace_context.py",
            "test_operational_context_foundation.py",
            "test_operational_context_security_hardening.py",
            "test_operational_context_legacy_reads.py",
            "test_operational_context_legacy_configuration_guard.py",
            "test_operational_context_characterization.py",
            "test_scope_foundation_imports.py",
            "test_scope_foundation_release.py",
            "test_awp_policy.py",
            "test_awp_release.py",
            "test_schedule_foundation_exchange.py",
            "test_schedule_foundation_policy.py",
            "test_schedule_foundation_release.py",
            "test_schedule_four_d_state.py",
            "test_schedule_four_d_release.py",
            "test_schedule_parser.py",
            "test_cost_financial_policy.py",
            "test_cost_financial_release.py",
            "test_cost_foundation_policy.py",
            "test_cost_foundation_release.py",
            "test_cost_legacy_boundary.py",
            "test_cost_startup.py",
            "test_progress_foundation_policy.py",
            "test_progress_foundation_release.py",
            "test_progress_integration_policy.py",
            "test_progress_integration_release.py",
            "test_progress_legacy_boundary.py",
            "test_progress_startup.py",
            "test_forecast_foundation_policy.py",
            "test_forecast_foundation_release.py",
            "test_forecast_reporting_policy.py",
            "test_forecast_reporting_release.py",
            "test_forecast_startup.py",
        ),
    ),
    "o2a": (
        "o2a",
        5552,
        (
            "test_engineering_core_policy.py",
            "test_engineering_integration_policy.py",
            "test_engineering_foundation_release.py",
            "test_engineering_consumers_release.py",
        ),
    ),
    "o2b": (
        "o2b",
        5555,
        (
            "test_procurement_material_availability.py",
            "test_procurement_sourcing_policy.py",
            "test_procurement_o2b_release.py",
        ),
    ),
}


def sources():
    path = Path(__file__).resolve()
    return {**snapshot(), path.relative_to(ROOT).as_posix(): digest(path)}


def database_identity(env):
    code = (
        "from sqlalchemy import create_engine,text; import os,json; "
        "c=create_engine(os.environ['DATABASE_URL']).connect(); "
        "q=c.execute(text(\"SELECT current_database(),current_user,current_setting('server_version'),"
        '(SELECT version_num FROM alembic_version)")); print(json.dumps(list(q.one())))'
    )
    return json.loads(
        subprocess.check_output(
            [sys.executable, "-c", code], cwd=BACKEND, env=env, text=True
        )
    )


def read_junit(path):
    cases = list(ET.parse(path).iter("testcase")) if path.is_file() else []
    statuses = {"total": len(cases), "passed": 0, "failed": 0, "error": 0, "skipped": 0}
    modules = set()
    for case in cases:
        modules.add(case.get("classname", "").split(".")[-1] + ".py")
        if case.find("failure") is not None:
            statuses["failed"] += 1
        elif case.find("error") is not None:
            statuses["error"] += 1
        elif case.find("skipped") is not None:
            statuses["skipped"] += 1
        else:
            statuses["passed"] += 1
    return statuses, modules


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=SUITES)
    parser.add_argument("attempt")
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", args.attempt):
        parser.error("attempt must be a short lowercase label")
    database, port, files = SUITES[args.suite]
    url = f"postgresql+psycopg://{database}:disposable-{database}@127.0.0.1:{port}/{database}"
    evidence = QA / args.suite / args.attempt
    if subprocess.run(
        ["git", "check-ignore", "-q", "--", str(evidence / "runtime")],
        cwd=ROOT,
        check=False,
    ).returncode:
        raise RuntimeError(
            "Refusing to leave disposable artifacts outside Git-ignored QA storage"
        )
    # Do not inherit URLs or opt-ins for destructive migration fixtures.
    env = {
        **{
            name: value
            for name, value in os.environ.items()
            if not name.startswith("PYPMIS_")
        },
        "DATABASE_URL": url,
        "PYPMIS_TEST_DATABASE_URL": url,
        "AUTO_CREATE_SCHEMA": "false",
        "SEED_DEMO_DATA": "false",
        "AUTH_SECRET_KEY": f"wave-close-disposable-regression-{database}",
        "ALLOWED_HOSTS": "localhost,127.0.0.1,testserver",
        "RATE_LIMIT_ENABLED": "false",
        f"PYPMIS_{database.upper()}_FIXTURE": "disposable-only",
        "PYPMIS_PYTEST_RUNTIME_DIR": str(evidence / "runtime"),
    }
    expected = args.expected_head
    heads = subprocess.check_output(
        [sys.executable, "-m", "alembic", "heads"], cwd=BACKEND, env=env, text=True
    )
    if re.findall(r"^([^\s]+).*\(head\)", heads, re.MULTILINE) != [expected]:
        raise RuntimeError(
            "Repository Alembic head does not match the freeze; nothing migrated"
        )
    old = database_identity(env)
    if old[:2] != [database, database] or not old[2].startswith("16."):
        raise RuntimeError("Unexpected disposable database identity; nothing migrated")
    if any(not (BACKEND / "tests" / file).is_file() for file in files):
        raise RuntimeError("An existing functional regression test is missing")
    evidence.mkdir(parents=True, exist_ok=False)
    before = sources()
    commit = git("rev-parse", "HEAD").strip()
    started = utc()
    migration = evidence / "migration.log"
    if run(
        [sys.executable, "-m", "alembic", "upgrade", expected], BACKEND, env, migration
    ):
        raise RuntimeError(
            "Isolated regression database upgrade failed; see migration.log"
        )
    migrated = database_identity(env)
    if migrated != [database, database, old[2], expected]:
        raise RuntimeError(
            "Dedicated regression database did not reach the frozen head"
        )
    junit = evidence / "junit.xml"
    pytest_log = evidence / "pytest.log"
    exit_code = run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "--no-cov",
            "-q",
            "-p",
            "no:cacheprovider",
            "--tb=short",
            f"--basetemp={evidence / 'temp'}",
            f"--junitxml={junit}",
            *(str(BACKEND / "tests" / file) for file in files),
        ],
        BACKEND,
        env,
        pytest_log,
    )
    final_database = database_identity(env)
    after = sources()
    unchanged = before == after and git("rev-parse", "HEAD").strip() == commit
    statuses, modules = read_junit(junit)
    missing = sorted(set(files) - modules)
    passed = (
        exit_code == 0
        and statuses["passed"] > 0
        and statuses["passed"] == statuses["total"]
        and not missing
    )
    passed = passed and final_database == migrated and unchanged
    write(
        evidence / "postgres-source-proof.json",
        {
            "result": "PASS" if passed else "FAIL",
            "scope": f"wave-o2b-close/g01/{args.suite}",
            "git_commit": commit,
            "alembic_head": expected,
            "isolated_database": database,
            "isolated_port": port,
            "postgres_version": final_database[2],
            "initial_alembic_revision": old[3],
            "alembic_head_unchanged_during_tests": final_database == migrated,
            "source_unchanged": unchanged,
            "source_sha256": before,
            "pytest_exit_code": exit_code,
            "status_counts": statuses,
            "missing_required_test_modules": missing,
            "artifact_sha256": {
                file.name: digest(file)
                for file in (migration, pytest_log, junit)
                if file.is_file()
            },
            "started_at_utc": started,
            "finished_at_utc": utc(),
        },
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
