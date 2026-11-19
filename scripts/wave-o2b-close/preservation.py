"""Repeat Project 14 preservation through the proven read-only observer."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "observer", ROOT / "scripts/wave-o1c/capture_preservation.py"
)
assert spec and spec.loader
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
observer.OUT = ROOT / "outputs/.qa/wave-o2b-close-20261111/project-14"

if __name__ == "__main__":
    observer.main()
