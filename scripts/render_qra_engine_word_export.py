"""Canonical DOCX rasterizer with only the unavailable soffice boundary replaced.

The Windows bundle has no soffice. Use a scoped read-only native Word PDF export;
never run the user's installed desktop LibreOffice or modify managed skill files.
"""

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "outputs" / ".qa" / "qra-engine"
RENDERER = Path(
    "C:/Users/Ricardo/.codex/plugins/cache/openai-primary-runtime/documents/"
    "26.1011.11113/skills/documents/render_docx.py"
)

if len(sys.argv) != 4:
    raise SystemExit("usage: render_qra_engine_word_export.py DOCX EXPORTED_PDF OUTPUT_DIR")
docx, exported_pdf, output_dir = map(lambda item: Path(item).resolve(), sys.argv[1:])
if not docx.is_relative_to(ROOT / "outputs") or docx.suffix != ".docx":
    raise ValueError("Expected task DOCX under outputs")
if not exported_pdf.is_relative_to(QA) or not output_dir.is_relative_to(QA):
    raise ValueError("Expected private Wave4 QA paths")
if exported_pdf.stem != docx.stem or not exported_pdf.is_file():
    raise ValueError("Expected existing matching Word export")
task_temp = QA / "word-render-tmp"
task_temp.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(task_temp)
spec = importlib.util.spec_from_file_location("canonical_qra_docx_renderer", RENDERER)
renderer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = renderer
spec.loader.exec_module(renderer)


def use_word_pdf(doc_path, user_profile, convert_tmp_dir, stem, verbose=False):
    return str(exported_pdf), "Read-only native Word export; bundled soffice unavailable."


renderer.convert_to_pdf = use_word_pdf
sys.argv = [str(RENDERER), str(docx), "--output_dir", str(output_dir), "--emit_pdf"]
renderer.main()
