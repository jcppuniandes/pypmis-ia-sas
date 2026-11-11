"""Verify O2A's native Word/Excel content against the evaluated evidence."""

import hashlib
import importlib.util
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from docx import Document
from generate_report import REFERENCE, REFERENCE_SHA
from openpyxl import load_workbook
from report_content import chapters

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/wave-o2a-20261109"
QA = ROOT / "outputs/.qa/wave-o2a-20261109"
TITLE = "P&Pmis_Wave_O2A_Engineering_Foundation_"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    legacy_spec = importlib.util.spec_from_file_location(
        "o2a_relationship_verifier",
        ROOT / "scripts/wave-o1c/verify_native_artifacts.py",
    )
    assert legacy_spec and legacy_spec.loader
    legacy = importlib.util.module_from_spec(legacy_spec)
    legacy_spec.loader.exec_module(legacy)
    evidence = json.loads((QA / "release-evidence.json").read_text("utf-8"))
    expected_chapters = chapters(evidence)
    report = OUT / f"{TITLE}Technical_Report.docx"
    word = Document(report)
    assert [p.text for p in word.paragraphs if p.style.name == "Heading 1"] == [
        f"{index} {heading}" for index, (heading, _) in enumerate(expected_chapters, 1)
    ]
    assert all(
        body in {p.text for p in word.paragraphs} for _, body in expected_chapters
    )
    with ZipFile(report) as archive:
        _, word_relationships = legacy.package_xml(archive)
        assert b"PAGE" in archive.read("word/footer1.xml")
        root = ET.fromstring(archive.read("word/document.xml"))
        assert len(root.findall(f".//{W}sectPr")) == 1
        assert all(
            table.find(f"{W}tr/{W}trPr/{W}tblHeader") is not None
            for table in root.findall(f".//{W}tbl")
        )
    assert digest(REFERENCE) == REFERENCE_SHA
    with ZipFile(REFERENCE) as original, ZipFile(report) as final:
        assert original.namelist() == final.namelist()
        changed = {
            name
            for name in original.namelist()
            if original.read(name) != final.read(name)
        }
        assert (
            {"word/document.xml", "docProps/core.xml"}
            <= changed
            <= {"word/document.xml", "docProps/core.xml", "word/footer1.xml"}
        )
        preserved_parts = len(original.namelist()) - len(changed)

    workbook = OUT / f"{TITLE}Traceability.xlsx"
    with ZipFile(workbook) as archive:
        _, excel_relationships = legacy.package_xml(archive)
    specs = json.loads((QA / "traceability-data.json").read_text("utf-8"))
    excel = load_workbook(workbook)
    assert len(specs) == 15 and excel.sheetnames == [spec["name"] for spec in specs]
    compared = 0
    for spec in specs:
        sheet = excel[spec["name"]]
        assert sheet.freeze_panes == "A8" and sheet.sheet_view.showGridLines is False
        [table] = list(sheet.tables.values())
        assert table.autoFilter is not None and table.autoFilter.ref == table.ref
        for i, values in enumerate([spec["headers"], *spec["rows"]], 7):
            for j, expected in enumerate(values, 1):
                cell = sheet.cell(i, j)
                assert cell.data_type not in {"f", "e"}
                assert cell.value == expected, (
                    spec["name"],
                    cell.coordinate,
                    cell.value,
                    expected,
                )
                compared += 1
    excel.close()
    proof = {
        "word_sections": 36,
        "word_tables": len(word.tables),
        "report_sha256": digest(report),
        "workbook_sheets": 15,
        "workbook_compared_cells": compared,
        "workbook_sha256": digest(workbook),
        "word_internal_relationships_checked": word_relationships,
        "excel_internal_relationships_checked": excel_relationships,
        "template_reference_sha256": REFERENCE_SHA,
        "template_preserved_parts": preserved_parts,
    }
    (QA / "native-artifact-proof.json").write_text(
        json.dumps(proof, indent=2), encoding="utf-8"
    )
    print(json.dumps(proof))


if __name__ == "__main__":
    main()
