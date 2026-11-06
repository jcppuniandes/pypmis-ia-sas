"""One isolated validation process with source freshness proof and no global coverage."""

import argparse
import hashlib
import json
import os
import subprocess
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

PROGRESS = (
    "test_progress_foundation_policy.py",
    "test_progress_foundation_release.py",
    "test_progress_integration_policy.py",
    "test_progress_integration_release.py",
    "test_progress_foundation_migration.py",
    "test_progress_startup.py",
    "test_progress_legacy_boundary.py",
)
REGRESSION = (
    "test_scope_foundation_imports.py",
    "test_scope_foundation_release.py",
    "test_schedule_foundation_exchange.py",
    "test_schedule_foundation_policy.py",
    "test_schedule_foundation_release.py",
    "test_schedule_four_d_release.py",
    "test_schedule_four_d_state.py",
    "test_schedule_parser.py",
    "test_awp_policy.py",
    "test_awp_release.py",
    "test_cost_financial_policy.py",
    "test_cost_financial_release.py",
    "test_cost_foundation_policy.py",
    "test_cost_foundation_release.py",
    "test_cost_legacy_boundary.py",
    "test_cost_startup.py",
)
ROOT = Path(__file__).resolve().parents[2]


def source_hashes():
    files = subprocess.check_output(
        ["git", "ls-files", "-co", "--exclude-standard", "--", "backend/app", "backend/alembic", "backend/tests"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in sorted(set(files))
        if (ROOT / name).is_file() and Path(name).suffix in {".py", ".json", ".xml", ".xer", ".csv"}
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("progress", "regression", "all"))
    mode = parser.parse_args().mode
    assert os.getenv("PYPMIS_O1BD_FIXTURE") == "disposable-only"
    url = os.environ["PYPMIS_TEST_DATABASE_URL"]
    assert url.endswith("/o1bd") and ("@127.0.0.1:5548/" in url or "@db:5432/" in url)
    qa = Path("/artifacts") if Path("/artifacts").is_dir() else ROOT / "outputs/.qa/wave-o1bd-20261104"
    qa.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PYPMIS_PYTEST_RUNTIME_DIR", str(qa / (mode + "-runtime-final")))
    before = source_hashes()
    started = datetime.now(UTC).isoformat()
    import pytest

    paths = PROGRESS + REGRESSION if mode == "all" else PROGRESS if mode == "progress" else REGRESSION
    junit = qa / (
        "o1bd-all-junit.xml"
        if mode == "all"
        else "progress-final-junit.xml"
        if mode == "progress"
        else "regression-junit.xml"
    )
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
                "--maxfail=5",
                "--basetemp=" + str(qa / (mode + "-temp-final")),
                "--junitxml=" + str(junit),
                *(str(ROOT / "backend/tests" / name) for name in paths),
            ]
        )
    )
    after = source_hashes()
    proof = {
        "mode": mode,
        "started_at": started,
        "completed_at": datetime.now(UTC).isoformat(),
        "pytest_exit_code": result,
        "source_unchanged_during_validation": before == after,
        "source_sha256": after,
        "changed_during_validation": [name for name in set(before) | set(after) if before.get(name) != after.get(name)],
    }
    (qa / (mode + "-source-proof.json")).write_text(json.dumps(proof, indent=2), encoding="utf-8")
    if mode == "all":
        cases = ET.parse(junit).findall(".//testcase")
        for subset in ("progress", "regression"):
            selected = [
                node
                for node in cases
                if node.get("classname", "").rsplit(".", 1)[-1].startswith("test_progress_") == (subset == "progress")
            ]
            document = ET.Element("testsuites")
            suite = ET.SubElement(document, "testsuite", name=subset, tests=str(len(selected)))
            for node in selected:
                suite.append(deepcopy(node))
            ET.ElementTree(document).write(
                qa / ("progress-final-junit.xml" if subset == "progress" else "regression-junit.xml"),
                encoding="utf-8",
                xml_declaration=True,
            )
            subset_proof = {
                **proof,
                "mode": subset,
                "combined_junit_sha256": hashlib.sha256(junit.read_bytes()).hexdigest(),
            }
            (qa / (subset + "-source-proof.json")).write_text(json.dumps(subset_proof, indent=2), encoding="utf-8")
    if before != after:
        raise SystemExit("Validation source changed during the run; freeze sources and rerun")
    raise SystemExit(result)


if __name__ == "__main__":
    main()
