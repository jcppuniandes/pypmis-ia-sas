"""Use the canonical skill PNG renderer with an existing read-only Word PDF.

The bundled dependency loader does not expose LibreOffice on this host. The
PDF bridge changes only this process's exporter function, never a managed file.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/strategic-final-uat"
OUTPUT = ROOT / "outputs/strategic-final-uat-20261014"
RENDERER = Path(
    "C:/Users/Ricardo/.codex/plugins/cache/openai-primary-runtime/"
    "documents/26.1013.11914/skills/documents/render_docx.py"
)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: render_word_export.py DOCX EXPORTED_PDF OUTPUT_DIR")
    docx, pdf, output_dir = (Path(value).resolve() for value in sys.argv[1:])
    if not docx.is_relative_to(OUTPUT) or docx.suffix != ".docx":
        raise ValueError("Expected scoped strategic UAT DOCX")
    if not pdf.is_relative_to(QA) or not output_dir.is_relative_to(QA):
        raise ValueError("Expected scoped private strategic UAT QA paths")
    if pdf.stem != docx.stem or not pdf.is_file():
        raise ValueError("Expected completed matching read-only Word PDF export")
    task_temp = QA / "word-render-tmp"
    task_temp.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(task_temp)
    spec = importlib.util.spec_from_file_location(
        "canonical_strategic_uat_renderer", RENDERER
    )
    if spec is None or spec.loader is None:
        raise ValueError("Canonical packaged renderer unavailable")
    renderer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = renderer
    spec.loader.exec_module(renderer)

    def use_exported_pdf(*_args: object, **_kwargs: object) -> tuple[str, str]:
        return str(
            pdf
        ), "Scoped read-only native Word export; bundled soffice unavailable"

    renderer.convert_to_pdf = use_exported_pdf
    sys.argv = [str(RENDERER), str(docx), "--output_dir", str(output_dir), "--emit_pdf"]
    renderer.main()


if __name__ == "__main__":
    main()
