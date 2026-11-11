"""Preserve Project 14 using the existing strictly read-only O1A observer."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "o2a_preservation", ROOT / "scripts/wave-o1c/capture_preservation.py"
)
assert SPEC and SPEC.loader
upstream = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upstream)
upstream.OUT = ROOT / "docs/validation/wave-o2a-20261109"

if __name__ == "__main__":
    upstream.main()
