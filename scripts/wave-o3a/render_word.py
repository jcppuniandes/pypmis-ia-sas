"""Use the packaged DOCX renderer with the exact native Word export."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    renderer, source, pdf, pages = sys.argv[1:]
    bridge_file = ROOT / "scripts/operational-master-architecture/render_word_export.py"
    spec = importlib.util.spec_from_file_location("o3a_word_pdf_bridge", bridge_file)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    bridge.OUT = Path(source).resolve().parent
    bridge.QA = ROOT / "outputs/.qa/wave-o3a-20261118"
    bridge.RENDERER = Path(renderer).resolve(strict=True)
    sys.argv = [str(bridge_file), source, pdf, pages]
    bridge.main()


if __name__ == "__main__":
    main()
