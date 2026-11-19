"""Reuse the read-only Project 14 observer with an independent O3A evidence cut."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "o3a_preservation", ROOT / "scripts/wave-o2c/preservation.py"
)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
observer.OUT = ROOT / "outputs/.qa/wave-o3a-20261118/project-14"
if __name__ == "__main__":
    observer.main()
