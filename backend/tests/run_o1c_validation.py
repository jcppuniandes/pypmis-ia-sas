"""One disposable O1C validation with upstream regression and fresh-source proof."""

import argparse
import hashlib
import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from tests.run_o1bd_validation import PROGRESS, REGRESSION, ROOT, source_hashes

BACKEND_ROOT = Path(__file__).resolve().parents[1]

FORECAST = (
    "test_forecast_foundation_policy.py",
    "test_forecast_foundation_release.py",
    "test_forecast_reporting_policy.py",
    "test_forecast_reporting_release.py",
    "test_forecast_foundation_migration.py",
    "test_forecast_startup.py",
)
UPSTREAM = tuple(name for name in PROGRESS if name != "test_progress_foundation_migration.py") + REGRESSION


def validation_sources():
    if (ROOT / ".git").exists():
        return source_hashes()
    # The isolated CI service binds only the backend at /app, without Git metadata.
    assert BACKEND_ROOT == Path("/app") and Path("/artifacts").is_dir()
    return {
        "backend/" + path.relative_to(BACKEND_ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for folder in ("app", "alembic", "tests")
        for path in sorted((BACKEND_ROOT / folder).rglob("*"))
        if path.is_file() and path.suffix in {".py", ".json", ".xml", ".xer", ".csv"}
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("forecast", "regression", "all"))
    mode = parser.parse_args().mode
    assert os.getenv("PYPMIS_O1C_FIXTURE") == "disposable-only"
    url = os.environ["PYPMIS_TEST_DATABASE_URL"]
    assert url.endswith("/o1c") and ("@127.0.0.1:5550/" in url or "@db:5432/" in url)
    qa = Path("/artifacts") if Path("/artifacts").is_dir() else ROOT / "outputs/.qa/wave-o1c-20261106"
    qa.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PYPMIS_PYTEST_RUNTIME_DIR", str(qa / (mode + "-runtime-final")))
    before = validation_sources()
    started = datetime.now(UTC).isoformat()
    import pytest

    paths = FORECAST + UPSTREAM if mode == "all" else FORECAST if mode == "forecast" else UPSTREAM
    junit = qa / (
        "o1c-all-junit.xml"
        if mode == "all"
        else "forecast-final-junit.xml"
        if mode == "forecast"
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
                *(str(BACKEND_ROOT / "tests" / name) for name in paths),
            ]
        )
    )
    after = validation_sources()
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
        for subset in ("forecast", "regression"):
            selected = [
                node
                for node in cases
                if node.get("classname", "").rsplit(".", 1)[-1].startswith("test_forecast_") == (subset == "forecast")
            ]
            document = ET.Element("testsuites")
            suite = ET.SubElement(document, "testsuite", name=subset, tests=str(len(selected)))
            for node in selected:
                suite.append(deepcopy(node))
            ET.ElementTree(document).write(
                qa / ("forecast-final-junit.xml" if subset == "forecast" else "regression-junit.xml"),
                encoding="utf-8",
                xml_declaration=True,
            )
            (qa / (subset + "-source-proof.json")).write_text(
                json.dumps(
                    {**proof, "mode": subset, "combined_junit_sha256": hashlib.sha256(junit.read_bytes()).hexdigest()},
                    indent=2,
                ),
                encoding="utf-8",
            )
    if before != after:
        raise SystemExit("Validation sources changed; freeze and repeat the final suite")
    raise SystemExit(result)


if __name__ == "__main__":
    main()
