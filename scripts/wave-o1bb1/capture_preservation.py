"""Normal canonical Project14 read-only before/after evidence for O1B-B1."""

import argparse
import importlib.util
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/validation/wave-o1bb1-20261021"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("before", "after"))
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location(
        "preservation", ROOT / "scripts/wave-o1a/capture_preservation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observation = module.capture()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"preservation-{args.phase}.json"
    assert not target.exists(), "Preserve original observations"
    if args.phase == "after":
        before = json.loads((OUT / "preservation-before.json").read_text("utf-8"))[
            "observation"
        ]
        for key in (
            "canonical_id14_row_sha256",
            "project14_row_sha256",
            "project14_references",
        ):
            assert observation[key] == before[key], f"Preservation mismatch {key}"
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
                "canonical_sha256": observation["canonical_id14_row_sha256"],
                "read_only": True,
            }
        )
    )


if __name__ == "__main__":
    main()
