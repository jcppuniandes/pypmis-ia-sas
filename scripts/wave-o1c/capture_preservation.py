"""Read-only Project 14 and upstream source preservation for Wave O1C."""

import argparse
import importlib.util
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/validation/wave-o1c-20261106"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("before", "after"))
    phase = parser.parse_args().phase
    spec = importlib.util.spec_from_file_location(
        "upstream_preservation", ROOT / "scripts/wave-o1a/capture_preservation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observation = module.capture()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"preservation-{phase}.json"
    assert not target.exists(), "Preserve the original observation"
    if phase == "after":
        before = json.loads((OUT / "preservation-before.json").read_text("utf-8"))[
            "observation"
        ]
        for key in (
            "canonical_id14_row_sha256",
            "project14_row_sha256",
            "project14_references",
        ):
            assert before[key] == observation[key], key
    result = {
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "baseline_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "observation": observation,
    }
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "phase": phase,
                "canonical_sha256": observation["canonical_id14_row_sha256"],
                "read_only": True,
            }
        )
    )


if __name__ == "__main__":
    main()
