"""Reuse packaged rendering with native read-only Word PDF evidence."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "b1_renderer",
    ROOT / "scripts/operational-master-architecture/render_word_export.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.OUT = ROOT / "outputs/wave-o1bb1-20261021"
module.QA = ROOT / "outputs/.qa/wave-o1bb1-20261021"

if __name__ == "__main__":
    module.main()
