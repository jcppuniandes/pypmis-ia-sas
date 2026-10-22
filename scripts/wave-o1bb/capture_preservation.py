"""Read-only normal database and canonical Project14 preservation evidence."""

import argparse
import importlib.util
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/validation/wave-o1bb-20261020"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("before", "after"))
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location(
        "schedule_preservation", ROOT / "scripts/wave-o1a/capture_preservation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observation = module.capture()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"preservation-{args.phase}.json"
    assert not target.exists(), "Never overwrite the original preservation proof"
    if args.phase == "after":
        before = json.loads((OUT / "preservation-before.json").read_text("utf-8"))[
            "observation"
        ]
        for key in (
            "canonical_id14_row_sha256",
            "project14_row_sha256",
            "project14_references",
        ):
            assert observation[key] == before[key], f"Preservation mismatch: {key}"
    value = {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "observation": observation,
    }
    target.write_text(json.dumps(value, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "phase": args.phase,
                "canonical_project14": observation["canonical_project14"],
                "canonical_sha256": observation["canonical_id14_row_sha256"],
                "read_only": True,
            }
        )
    )


if __name__ == "__main__":
    main()
