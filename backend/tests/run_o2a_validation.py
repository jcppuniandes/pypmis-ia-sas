"""Run O2A against disposable PostgreSQL and bind the result to source hashes."""

import json
import os
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

from tests.run_o1bd_validation import ROOT, source_hashes

CASES = (
    "test_engineering_core_policy.py",
    "test_engineering_integration_policy.py",
    "test_engineering_foundation_release.py",
    "test_engineering_foundation_migration.py",
    "test_engineering_consumers_release.py",
    "test_awp_policy.py",
    "test_forecast_foundation_policy.py",
    "test_forecast_reporting_policy.py",
    "test_progress_foundation_policy.py",
    "test_progress_integration_policy.py",
    "test_schedule_four_d_state.py",
)


def main():
    assert os.environ.get("PYPMIS_O2A_FIXTURE") == "disposable-only"
    assert os.environ["DATABASE_URL"] == os.environ["PYPMIS_TEST_DATABASE_URL"]
    for variable, port, name in (
        ("PYPMIS_TEST_DATABASE_URL", 5552, "o2a"),
        ("PYPMIS_O2A_MIGRATION_DATABASE_URL", 5553, "o2a_migration"),
    ):
        url = urlsplit(os.environ[variable])
        assert (url.scheme, url.hostname, url.port, url.path) == ("postgresql+psycopg", "127.0.0.1", port, f"/{name}")

    qa = ROOT / "outputs/.qa/wave-o2a-20261109"
    qa.mkdir(parents=True, exist_ok=True)
    before = source_hashes()
    started = datetime.now(UTC).isoformat()
    import pytest

    result = int(
        pytest.main(
            [
                "-o",
                "addopts=",
                "--no-cov",
                "-q",
                "-p",
                "no:cacheprovider",
                "--tb=short",
                "--maxfail=6",
                f"--basetemp={qa / f'pg-test-{uuid4().hex[:8]}'}",
                f"--junitxml={qa / 'final-postgres-junit.xml'}",
                *(str(ROOT / "backend/tests" / case) for case in CASES),
            ]
        )
    )
    after = source_hashes()
    proof = {
        "started_at": started,
        "completed_at": datetime.now(UTC).isoformat(),
        "pytest_exit_code": result,
        "source_unchanged_during_validation": before == after,
        "source_sha256": after,
        "changed_during_validation": sorted(
            name for name in before.keys() | after.keys() if before.get(name) != after.get(name)
        ),
    }
    (qa / "postgres-source-proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    if before != after:
        raise SystemExit("O2A source changed during the run; freeze and rerun")
    raise SystemExit(result)


if __name__ == "__main__":
    main()
