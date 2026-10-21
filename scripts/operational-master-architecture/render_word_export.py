"""Canonical renderer bridge for native hidden read-only Word PDF export."""

import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/operational-master-architecture-20261019"
QA = ROOT / "outputs/.qa/operational-master-architecture-20261019"
RENDERER = Path(
    "C:/Users/Ricardo/.codex/plugins/cache/openai-primary-runtime/documents/26.1015.12040/skills/documents/render_docx.py"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: render_word_export.py DOCX WORD_PDF OUTPUT_DIR")
    docx, pdf, images = (Path(value).resolve() for value in sys.argv[1:])
    assert docx.is_relative_to(OUT) and docx.suffix == ".docx"
    assert pdf.is_relative_to(QA) and images.is_relative_to(QA)
    assert pdf.stem == docx.stem and pdf.is_file()
    proof = json.loads(Path(str(pdf) + ".export.json").read_text(encoding="utf-8"))
    assert proof["input_docx_sha256"] == digest(docx)
    assert proof["output_pdf_sha256"] == digest(pdf)
    work = QA / "word-render-tmp"
    work.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(work)
    spec = importlib.util.spec_from_file_location(
        "operational_architecture_renderer", RENDERER
    )
    assert spec and spec.loader
    renderer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = renderer
    spec.loader.exec_module(renderer)
    renderer.convert_to_pdf = lambda *_a, **_k: (
        str(pdf),
        "Native read-only Word export; bundled soffice unavailable",
    )
    sys.argv = [str(RENDERER), str(docx), "--output_dir", str(images), "--emit_pdf"]
    renderer.main()
    assert proof["input_docx_sha256"] == digest(docx)
    assert proof["output_pdf_sha256"] == digest(pdf)
    pages = sorted(images.glob("page-*.png"))
    assert len(pages) == proof["pages"]
    (images / "render-provenance.json").write_text(
        json.dumps(
            {
                "input_docx_sha256": digest(docx),
                "input_pdf_sha256": digest(pdf),
                "pages": {page.name: digest(page) for page in pages},
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
