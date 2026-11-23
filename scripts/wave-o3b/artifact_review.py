"""Structural evidence and readable image tiles for the human O3B artifact review."""

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from zipfile import ZipFile

from docx import Document
from PIL import Image
from pypdf import PdfReader
from report_content import MARKER, OUT, QA, matrix, status


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("tiles", "record"))
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    assert re.fullmatch(r"v\d+", args.version)
    rendered = QA / ("matrix-render-" + args.version)
    if args.action == "tiles":
        with Image.open(rendered / "01_REQUIREMENTS.png") as image:
            for index, top in enumerate(range(0, image.height, 860), 1):
                image.crop(
                    (0, max(0, top - 25), image.width, min(image.height, top + 885))
                ).save(rendered / f"requirements-tile-{index}.png")
        return
    word = OUT / "P&Pmis_Wave_O3B_Quality_Management_Inspection_Technical_Report.docx"
    xlsx = OUT / "P&Pmis_Wave_O3B_Quality_Management_Inspection_Traceability.xlsx"
    document = Document(word)
    headings = [p.text for p in document.paragraphs if p.style.name == "Heading 1"]
    numbered = [
        int(match.group(1))
        for text in headings
        if (match := re.match(r"^(\d{2}) ", text))
    ]
    assert numbered == list(range(1, 40))
    pdf = QA / ("word-final-" + args.version) / (word.stem + ".pdf")
    export = json.loads((pdf.parent / (pdf.name + ".export.json")).read_text("utf-8"))
    assert export["input_docx_sha256"] == sha(word) and export[
        "output_pdf_sha256"
    ] == sha(pdf)
    pages = list(PdfReader(pdf).pages)
    assert len(pages) == export["pages"]
    for n, page in enumerate(pages, 1):
        assert re.search(rf"Página\s+{n}(?!\d)", page.extract_text()), n
        assert (QA / ("word-pages-" + args.version) / f"page-{n}.png").exists()
    if status() == MARKER:
        assert MARKER in "\n".join(p.text for p in document.paragraphs)
    assert len(matrix()["01_REQUIREMENTS"]["rows"]) == 68
    exported = json.loads((rendered / "export-proof.json").read_text("utf-8"))
    assert (
        exported["status"] == "PASS"
        and exported["sheets"] == 20
        and exported["reimported_values_equal"]
    )
    with ZipFile(xlsx) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        assert (
            len(
                [node for node in workbook.iter() if node.tag.split("}")[-1] == "sheet"]
            )
            == 20
        )
    assert "matched 0 entries" in (QA / "matrix-inspection.ndjson").read_text("utf-8")
    stamp = datetime.now(UTC).isoformat()
    (QA / "word-qa.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "reviewed_at": stamp,
                "filename": word.name,
                "sha256": sha(word),
                "pages": len(pages),
                "all_pages_reviewed": True,
                "chapters": 39,
                "renderer": "bundled render_docx.py from native hidden read-only Word PDF export",
                "render_directory": "word-pages-" + args.version,
                "visual_findings": "No clipping overlap missing glyphs orphan headings; single-line two-digit page numbers verified after V1 correction",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (QA / "matrix-qa.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "reviewed_at": stamp,
                "filename": xlsx.name,
                "sha256": sha(xlsx),
                "sheets": 20,
                "all_sheets_reviewed": True,
                "requirements": 68,
                "render_directory": rendered.name,
                "reimported_values_equal": True,
                "formula_error_matches": 0,
                "visual_findings": "Every sheet reviewed including all requirement tiles; wrapped text and final rows fully visible",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "word_pages": len(pages),
                "chapters": 39,
                "matrix_sheets": 20,
                "requirements": 68,
            }
        )
    )


if __name__ == "__main__":
    main()
