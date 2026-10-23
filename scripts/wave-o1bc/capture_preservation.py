"""Read-only normal Project14 observation for O1B-C validation."""

import argparse
import importlib.util
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/validation/wave-o1bc-20261022"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("before", "after"))
    phase = parser.parse_args().phase
    spec = importlib.util.spec_from_file_location(
        "preservation", ROOT / "scripts/wave-o1a/capture_preservation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observation = module.capture()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"preservation-{phase}.json"
    assert not target.exists(), "Keep the original observation"
    if phase == "after":
        before = json.loads((OUT / "preservation-before.json").read_text("utf-8"))[
            "observation"
        ]
        for key in (
            "canonical_id14_row_sha256",
            "project14_row_sha256",
            "project14_references",
        ):
            assert observation[key] == before[key], f"Preservation mismatch {key}"
    target.write_text(
        json.dumps(
            {
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "baseline_head": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "observation": observation,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
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
