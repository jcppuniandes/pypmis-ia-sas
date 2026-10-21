"""Use the existing packaged renderer bridge for native read-only Word export."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "scope_renderer_bridge",
    ROOT / "scripts/operational-master-architecture/render_word_export.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.OUT = ROOT / "outputs/wave-o1ba-20261020"
module.QA = ROOT / "outputs/.qa/wave-o1ba-20261020"

if __name__ == "__main__":
    module.main()
