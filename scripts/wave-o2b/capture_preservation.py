"""Wave-specific evidence from the established read-only Project 14 observer."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "o2b_preservation", ROOT / "scripts/wave-o1c/capture_preservation.py"
)
assert SPEC and SPEC.loader
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)
observer.OUT = ROOT / "docs/validation/wave-o2b"

if __name__ == "__main__":
    observer.main()
