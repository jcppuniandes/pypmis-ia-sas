"""Canonical bundled DOCX renderer using a scoped native read-only Word PDF.

The dependency loader does not expose bundled LibreOffice on this host. Only
this process's exporter function is replaced; no managed dependency is edited.
"""

import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/business-uat-signoff-20261018"
QA = ROOT / "outputs/.qa/business-uat-signoff-20261018"
RENDERER = Path(
    "C:/Users/Ricardo/.codex/plugins/cache/openai-primary-runtime/"
    "documents/26.1015.12040/skills/documents/render_docx.py"
)


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: render_word_export.py DOCX WORD_PDF OUTPUT_DIR")
    docx, pdf, images = (Path(value).resolve() for value in sys.argv[1:])
    assert docx.is_relative_to(OUT) and docx.suffix == ".docx"
    assert pdf.is_relative_to(QA) and images.is_relative_to(QA)
    assert pdf.stem == docx.stem and pdf.is_file()
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    proof = json.loads(Path(str(pdf) + '.export.json').read_text(encoding='utf-8'))
    assert proof['input_docx_sha256'] == digest(docx)
    assert proof['output_pdf_sha256'] == digest(pdf)
    work = QA / "word-render-tmp"
    work.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(work)
    spec = importlib.util.spec_from_file_location("business_signoff_renderer", RENDERER)
    assert spec and spec.loader
    renderer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = renderer
    spec.loader.exec_module(renderer)

    def exported_pdf(*_args, **_kwargs):
        return str(pdf), "Native read-only Word export; bundled soffice unavailable"

    renderer.convert_to_pdf = exported_pdf
    sys.argv = [str(RENDERER), str(docx), "--output_dir", str(images), "--emit_pdf"]
    renderer.main()
    assert proof['input_docx_sha256'] == digest(docx)
    assert proof['output_pdf_sha256'] == digest(pdf)
    rendered = sorted(images.glob('page-*.png'))
    assert len(rendered) == proof['pages']
    metadata = {'input_docx_sha256': digest(docx), 'input_pdf_sha256': digest(pdf), 'pages': {page.name: digest(page) for page in rendered}}
    (images / 'render-provenance.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')


if __name__ == "__main__":
    main()
