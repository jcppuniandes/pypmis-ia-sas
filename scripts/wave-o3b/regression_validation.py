"""Relevant legacy PostgreSQL consumers plus inherited Contracts latency observation."""

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o3b-20261119/regression"


def historical_hashes():
    return {
        name: hashlib.sha256(
            (ROOT / "outputs/.qa/wave-o3a-20261118" / name).read_bytes()
        ).hexdigest()
        for name in ("consumer-performance.json", "release-decision.json")
    }


def main():
    started = datetime.now(UTC).isoformat()
    before = historical_hashes()
    expected = "postgresql+psycopg://o3b:o3b@127.0.0.1:5567/o3b"
    assert (
        os.environ.get("DATABASE_URL") == expected
        and os.environ.get("PYPMIS_TEST_DATABASE_URL") == expected
    )
    assert os.environ.get("PYPMIS_O3B_FIXTURE") == "disposable-only"
    os.environ["PYPMIS_O3A_FIXTURE"] = "disposable-only"
    sys.path.insert(0, str(ROOT / "backend"))
    os.chdir(ROOT / "backend")
    import pytest

    QA.mkdir(parents=True, exist_ok=True)
    # These cases do not write historical O3A evidence files. Their original
    # domain and API assertions remain intact, including duplicate prevention.
    result = pytest.main(
        [
            "tests/test_field_operations_consumers_release.py::test_field_progress_explicit_adoption_is_draft_and_idempotent",
            "tests/test_field_operations_consumers_release.py::test_native_consumers_do_not_cross_authority",
            "-q",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            "--junitxml=" + str(QA / "o3a-consumer-junit.xml"),
        ]
    )
    if result:
        raise SystemExit(result)
    import contracts_performance

    contracts_performance.main()
    after = historical_hashes()
    assert after == before, "Historical O3A release evidence must remain unchanged"
    contracts = json.loads(
        (ROOT / "outputs/.qa/wave-o3b-20261119/contracts-performance.json").read_text(
            "utf-8"
        )
    )
    assert contracts["before_hashes"] == contracts["after_hashes"]
    assert not contracts["read_mutations"]
    proof = {
        "status": "PASS",
        "started_at": started,
        "completed_at": datetime.now(UTC).isoformat(),
        "database": "o3b@127.0.0.1:5567/o3b",
        "ordinary_database_used": False,
        "legacy_native_api_tests": 2,
        "contracts_read_queries": 2,
        "samples_per_query": 3,
        "contracts_get_business_dml": 0,
        "contracts_observed_hashes_unchanged": True,
        "historical_o3a_before_hashes": before,
        "historical_o3a_after_hashes": after,
        "historical_o3a_overwritten": False,
    }
    (QA / "legacy-regression-proof.json").write_text(
        json.dumps(proof, indent=2), encoding="utf-8"
    )
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
