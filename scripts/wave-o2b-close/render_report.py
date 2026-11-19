"""Reuse the verified Word/PDF renderer on the staged closeout artifact."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o2b-close-20261111/artifacts"
BRIDGE = ROOT / "scripts/operational-master-architecture/render_word_export.py"


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit("usage: render_report.py RENDER_DOCX DOCX WORD_PDF OUTPUT_DIR")
    renderer, *args = sys.argv[1:]
    spec = importlib.util.spec_from_file_location("o2b_close_word_export", BRIDGE)
    assert spec and spec.loader
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    bridge.OUT = QA / "candidate"
    bridge.QA = QA
    bridge.RENDERER = Path(renderer).resolve(strict=True)
    sys.argv = [str(BRIDGE), *args]
    bridge.main()


if __name__ == "__main__":
    main()
