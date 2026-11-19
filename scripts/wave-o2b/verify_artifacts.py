"""Check the native final Word and Excel files against their authoring evidence."""

import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from docx.oxml.ns import qn
from evidence import OUT, QA
from generate_report import REFERENCE, REPORT
from openpyxl import load_workbook


def digest(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def main(word, workbook):
    word_proof = json.loads((word / "render-provenance.json").read_text("utf-8"))
    assert word_proof["input_docx_sha256"] == digest(REPORT)
    assert all(digest(word / name) == sha for name, sha in word_proof["pages"].items())
    doc, reference = Document(REPORT), Document(REFERENCE)
    headings = [
        paragraph.text
        for paragraph in doc.paragraphs
        if paragraph.style.name == "Heading 1"
    ]
    assert [int(heading.split(maxsplit=1)[0]) for heading in headings] == list(
        range(1, 40)
    )
    assert len(doc.sections) == len(reference.sections) == 1
    assert doc.sections[0]._sectPr.xml == reference.sections[0]._sectPr.xml
    assert all(
        row.rows[0]._tr.trPr.find(qn("w:tblHeader")) is not None for row in doc.tables
    )
    assert doc.paragraphs[0]._p.xpath(".//wp:docPr")[0].get("descr")
    with ZipFile(REPORT) as authored, ZipFile(REFERENCE) as retained:
        assert set(authored.namelist()) == set(retained.namelist())
        assert {
            name
            for name in authored.namelist()
            if authored.read(name) != retained.read(name)
        } <= {
            "docProps/core.xml",
            "word/document.xml",
            "word/footer1.xml",
        }
        assert b"PAGE" in authored.read("word/footer1.xml")

    data = QA / "traceability-data.json"
    specs = json.loads(data.read_text("utf-8"))
    target = OUT / "P&Pmis_Wave_O2B_Procurement_Materials_Logistics_Traceability.xlsx"
    proof = json.loads((workbook / "render-provenance.json").read_text("utf-8"))
    assert proof["traceability_data_sha256"] == digest(data) and proof[
        "workbook_sha256"
    ] == digest(target)
    assert all(digest(workbook / name) == sha for name, sha in proof["images"].items())
    assert {entry["sheet"] for entry in proof["previews"]} == {
        spec["name"] for spec in specs
    }
    native = load_workbook(target, read_only=False, data_only=False)
    try:
        assert (
            native.sheetnames == [spec["name"] for spec in specs] and len(specs) == 17
        )
        for spec in specs:
            sheet = native[spec["name"]]
            observed = list(sheet.iter_rows(min_row=7, values_only=True))
            assert observed == [
                tuple(row) for row in [spec["headers"], *spec["rows"]]
            ], spec["name"]
            assert len(sheet.tables) == 1 and not sheet.sheet_view.showGridLines
            assert all(cell.data_type != "e" for row in sheet for cell in row)
        assert len(specs[1]["rows"]) == 52
    finally:
        native.close()
    print(
        json.dumps(
            {
                "word_sections": len(headings),
                "word_pages": len(word_proof["pages"]),
                "workbook_sheets": len(specs),
                "workbook_renders": len(proof["images"]),
            }
        )
    )


if __name__ == "__main__":
    assert len(sys.argv) == 3, (
        "usage: verify_artifacts.py WORD_PAGE_DIR WORKBOOK_PREVIEW_DIR"
    )
    main(*(Path(arg) for arg in sys.argv[1:]))
