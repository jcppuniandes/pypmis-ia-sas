"""Independent read-only OOXML verification of the saved deliverables."""

import json
import posixpath
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from docx import Document

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1ba-20261020"
OUT = ROOT / "outputs/wave-o1ba-20261020"
NS = {
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def main():
    expected = json.loads((QA / "workbook/expected-tables.json").read_text("utf-8"))
    cells_compared = blanks = tables = 0
    book = OUT / "P&Pmis_Wave_O1B_A_Scope_Foundation_Traceability.xlsx"
    with ZipFile(book) as archive:
        assert archive.testzip() is None
        xmls = {
            name: ET.fromstring(archive.read(name))
            for name in archive.namelist()
            if name.endswith((".xml", ".rels"))
        }
        workbook = xmls["xl/workbook.xml"]
        sheets = workbook.findall("s:sheets/s:sheet", NS)
        assert [sheet.get("name") for sheet in sheets] == [
            row["sheet"] for row in expected
        ]
        assert all(sheet.get("state", "visible") == "visible" for sheet in sheets)
        rels = {
            row.get("Id"): row.get("Target")
            for row in xmls["xl/_rels/workbook.xml.rels"]
        }
        shared = [
            "".join(row.itertext()) for row in xmls.get("xl/sharedStrings.xml", [])
        ]
        for sheet, spec in zip(sheets, expected, strict=True):
            target = rels[sheet.get("{" + NS["r"] + "}id")]
            part = (
                target.lstrip("/")
                if target.startswith("/")
                else posixpath.normpath(posixpath.join("xl", target))
            )
            node = xmls[part]
            assert node.find("s:sheetViews/s:sheetView/s:pane", NS) is not None
            actual = {}
            for cell in node.findall("s:sheetData/s:row/s:c", NS):
                assert cell.find("s:f", NS) is None and cell.get("t") != "e", (
                    "Unexpected formula/error in static traceability"
                )
                value = cell.findtext("s:v", default="", namespaces=NS)
                actual[cell.get("r")] = (
                    shared[int(value)]
                    if cell.get("t") == "s"
                    else "".join(cell.find("s:is", NS).itertext())
                    if cell.get("t") == "inlineStr"
                    else value
                )
            for row_index, values in enumerate([spec["headers"], *spec["rows"]], 7):
                for col_index, expected_value in enumerate(values):
                    coordinate = f"{chr(65 + col_index)}{row_index}"
                    value = actual.get(coordinate, "")
                    if expected_value is None:
                        assert value == "", (spec["sheet"], coordinate, value)
                        blanks += 1
                    elif isinstance(expected_value, (int, float)):
                        assert float(value) == expected_value, (
                            spec["sheet"],
                            coordinate,
                        )
                    else:
                        assert value == str(expected_value), (
                            spec["sheet"],
                            coordinate,
                            value,
                            expected_value,
                        )
                    cells_compared += 1
        for name, node in xmls.items():
            if name.startswith("xl/tables/") and name.endswith(".xml"):
                assert node.find("s:autoFilter", NS) is not None
                tables += 1
            if name.endswith(".rels"):
                base = posixpath.dirname(posixpath.dirname(name))
                for rel in node:
                    if rel.get("TargetMode") == "External":
                        continue
                    target = rel.get("Target")
                    resolved = (
                        target.lstrip("/")
                        if target.startswith("/")
                        else posixpath.normpath(posixpath.join(base, target))
                    )
                    assert resolved in archive.namelist(), (name, target)
        assert tables == 14
    docx = OUT / "P&Pmis_Wave_O1B_A_Scope_Foundation_Technical_Report.docx"
    with ZipFile(docx) as archive:
        assert archive.testzip() is None
        for name in archive.namelist():
            if name.endswith((".xml", ".rels")):
                ET.fromstring(archive.read(name))
    document = Document(docx)
    headings = [p.text for p in document.paragraphs if p.style.name == "Heading 1"]
    assert len(headings) == 28 and all(
        text.startswith(str(i) + " ") for i, text in enumerate(headings, 1)
    )
    result = {
        "result": "PASS",
        "sheets": 14,
        "native_filtered_tables": tables,
        "compared_cells": cells_compared,
        "intentional_blank_metric_cells": blanks,
        "discrepancies": 0,
        "word_heading1_sections": len(headings),
        "zip_crc_and_xml_parse": "PASS",
        "formula_error_cells": 0,
        "broken_internal_relationships": 0,
    }
    (QA / "native-artifact-verification.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
