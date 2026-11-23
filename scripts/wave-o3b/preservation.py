"""Independent read-only Project 14 observation for O3B."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "o3b_preservation", ROOT / "scripts/wave-o2c/preservation.py"
)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
observer.OUT = ROOT / "outputs/.qa/wave-o3b-20261119/project-14"
if __name__ == "__main__":
    observer.main()
