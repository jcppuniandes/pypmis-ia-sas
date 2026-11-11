"""Add a final read-only observation; never replace the original before/after."""

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/validation/wave-o2a-20261109"


def main():
    target = OUT / "preservation-closeout.json"
    assert not target.exists(), "Preserve the original observation"
    spec = importlib.util.spec_from_file_location(
        "o2a_closeout_observer", ROOT / "scripts/wave-o1a/capture_preservation.py"
    )
    assert spec and spec.loader
    observer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(observer)
    observation = observer.capture()
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
        "observation": observation,
    }
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "read_only": True,
                "canonical_sha256": observation["canonical_id14_row_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
