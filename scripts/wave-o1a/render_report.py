"""Reuse the canonical packaged renderer bridge; no runtime package edits."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "o1a_renderer_bridge",
    ROOT / "scripts/operational-master-architecture/render_word_export.py",
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.OUT = ROOT / "outputs/wave-o1a-20261019"
module.QA = ROOT / "outputs/.qa/wave-o1a-20261019"

if __name__ == "__main__":
    module.main()
