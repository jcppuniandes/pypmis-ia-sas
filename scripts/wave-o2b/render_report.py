"""Render the exact authored DOCX via the verified native Word PDF bridge."""

import importlib.util
import os
from pathlib import Path

from evidence import OUT, QA, ROOT

spec = importlib.util.spec_from_file_location(
    "o2b_word_export",
    ROOT / "scripts/operational-master-architecture/render_word_export.py",
)
assert spec and spec.loader
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
bridge.OUT = OUT
bridge.QA = QA
bridge.RENDERER = Path(os.environ["PYPMIS_O2B_DOCX_RENDERER"])

if __name__ == "__main__":
    bridge.main()
