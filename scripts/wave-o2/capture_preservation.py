"""Snapshot the existing application and Project 14 without writing to the database."""

import argparse
import hashlib
import importlib.util
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2-20261109"
ARCH = ROOT / "docs/architecture/wave-o2"
VALIDATION = ROOT / "docs/validation"
BASELINES = {
    "wave-o1a-20261019": "WAVE_O1A_OPERATIONAL_FOUNDATION_RELEASE_VALIDATED",
    "wave-o1ba-20261020": "WAVE_O1B_A_SCOPE_FOUNDATION_RELEASE_VALIDATED",
    "wave-o1bb-20261020": "WAVE_O1B_B_SCHEDULE_FOUNDATION_RELEASE_VALIDATED",
    "wave-o1bb1-20261021": "WAVE_O1B_B1_AWP_READINESS_4D_RELEASE_VALIDATED",
    "wave-o1bc-20261022": "WAVE_O1B_C_COST_FOUNDATION_RELEASE_VALIDATED",
    "wave-o1bd-20261104": "WAVE_O1B_D_PROGRESS_AND_BASELINE_INTEGRATION_RELEASE_VALIDATED",
    "wave-o1c-20261106": "WAVE_O1C_FORECAST_PERFORMANCE_REPORTING_RELEASE_VALIDATED",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text("utf-8-sig"))


def observe():
    spec = importlib.util.spec_from_file_location(
        "o1a_read_only", ROOT / "scripts/wave-o1a/capture_preservation.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    values = module.capture()
    assert values["read_only"] and values["canonical_project14"]
    values.pop("product_source_sha256")
    tracked_and_untracked = (
        subprocess.check_output(
            [
                "git",
                "ls-files",
                "-co",
                "--exclude-standard",
                "-z",
                "--",
                "backend/app",
                "backend/alembic",
                "backend/tests",
                "frontend/src",
                "frontend/e2e",
                ".github/workflows",
            ],
            cwd=ROOT,
        )
        .decode("utf-8")
        .split("\0")
    )
    files = sorted(set(tracked_and_untracked) - {""})
    values["application_source_sha256"] = {
        name: sha(ROOT / name) for name in files if (ROOT / name).is_file()
    }
    values["head"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["before", "after"])
    phase = parser.parse_args().phase
    QA.mkdir(parents=True, exist_ok=True)
    current = observe()
    observed_at = datetime.now(UTC).isoformat()
    target = QA / f"preservation-{phase}.json"
    assert not target.exists(), target
    if phase == "after":
        prior = read(QA / "preservation-before.json")
        assert current == prior["observation"], (
            "Project 14 or application sources changed"
        )
        releases = []
        for directory, expected in BASELINES.items():
            manifest = VALIDATION / directory / "release-manifest.json"
            assert read(manifest)["release_state"] == expected, directory
            releases.append(
                {"directory": directory, "state": expected, "sha256": sha(manifest)}
            )
        latest = VALIDATION / "wave-o1c-20261106"
        latest_manifest = read(latest / "release-manifest.json")
        assert latest_manifest["release_state"] == BASELINES[latest.name]
        upstream = read(latest / "preservation-after.json")["observation"]
        for key in (
            "canonical_id14_row_sha256",
            "project14_row_sha256",
            "project14_references",
        ):
            assert current[key] == upstream[key], key
        o1c_sources = read(latest / "source-manifest.json")
        changed = {
            name: expected
            for name, expected in o1c_sources.items()
            if not (ROOT / name).is_file() or sha(ROOT / name) != expected
        }
        assert not changed, changed
        result = {
            "result": "PASS",
            "mode": "READ_ONLY_ARCHITECTURE",
            "before_utc": prior["observed_at_utc"],
            "after_utc": observed_at,
            "head": current["head"],
            "canonical_project14_sha256": current["canonical_id14_row_sha256"],
            "legacy_project14_sha256": current["project14_row_sha256"],
            "legacy_reference_tables": len(current["project14_references"]),
            "application_files_unchanged": len(current["application_source_sha256"]),
            "o1c_manifest_files_matched": len(o1c_sources),
            "o1_baselines": releases,
        }
        (ARCH / "preservation.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
    target.write_text(
        json.dumps({"observed_at_utc": observed_at, "observation": current}, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "phase": phase,
                "read_only": True,
                "project14": current["canonical_id14_row_sha256"],
                "application_files": len(current["application_source_sha256"]),
            }
        )
    )


if __name__ == "__main__":
    main()
