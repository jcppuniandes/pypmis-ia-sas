"""Reuse the O1A read-only identity proof for the O1B-A increment."""

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/validation/wave-o1ba-20261020"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("before", "after"))
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location(
        "o1a_preservation", ROOT / "scripts/wave-o1a/capture_preservation.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observation = module.capture()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / f"preservation-{args.phase}.json"
    assert not target.exists(), "Never overwrite the original preservation proof"
    if args.phase == "after":
        before = json.loads((OUTPUT / "preservation-before.json").read_text("utf-8"))[
            "observation"
        ]
        for key in (
            "canonical_id14_row_sha256",
            "project14_row_sha256",
            "project14_references",
        ):
            assert observation[key] == before[key], f"Preservation mismatch: {key}"
    target.write_text(
        json.dumps(
            {
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "observation": observation,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
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
