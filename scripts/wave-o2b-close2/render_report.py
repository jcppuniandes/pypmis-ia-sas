"""Use the canonical DOCX renderer on a read-only Word PDF export."""

import importlib.util
import sys
from pathlib import Path

from update_report import OUTPUT, QA, ROOT


def main():
    renderer, pdf, pages = sys.argv[1:]
    source = ROOT / "scripts/operational-master-architecture/render_word_export.py"
    spec = importlib.util.spec_from_file_location("word_renderer", source)
    assert spec and spec.loader
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    bridge.OUT = OUTPUT.parent
    bridge.QA = QA / "artifacts"
    bridge.RENDERER = Path(renderer).resolve(strict=True)
    sys.argv = [str(source), str(OUTPUT), pdf, pages]
    bridge.main()


if __name__ == "__main__":
    main()
