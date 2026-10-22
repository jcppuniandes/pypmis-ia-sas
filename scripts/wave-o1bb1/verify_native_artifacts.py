"""Independent native OOXML cell, feature, relationship and document checks."""

import json
import math
import posixpath
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from docx import Document

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1bb1-20261021"
OUT = ROOT / "outputs/wave-o1bb1-20261021"
NS = {
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def main():
    expected = json.loads((QA / "workbook/expected-tables.json").read_text("utf-8"))
    cells, tables = 0, 0
    with ZipFile(
        OUT / "P&Pmis_Wave_O1B_B1_AWP_Readiness_4D_Traceability.xlsx"
    ) as archive:
        assert archive.testzip() is None
        xmls = {
            name: ET.fromstring(archive.read(name))
            for name in archive.namelist()
            if name.endswith((".xml", ".rels"))
        }
        sheets = xmls["xl/workbook.xml"].findall("s:sheets/s:sheet", NS)
        assert [row.get("name") for row in sheets] == [
            row["sheet"] for row in expected
        ] and len(sheets) == 15
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
                assert cell.find("s:f", NS) is None and cell.get("t") != "e"
                value = cell.findtext("s:v", default="", namespaces=NS)
                actual[cell.get("r")] = (
                    shared[int(value)]
                    if cell.get("t") == "s"
                    else "".join(cell.find("s:is", NS).itertext())
                    if cell.get("t") == "inlineStr"
                    else value
                )
            for row_index, values in enumerate([spec["headers"], *spec["rows"]], 7):
                for column, expected_value in enumerate(values):
                    address = f"{chr(65 + column)}{row_index}"
                    value = actual.get(address, "")
                    if expected_value is None:
                        assert value == "", (spec["sheet"], address)
                    elif isinstance(expected_value, (int, float)):
                        assert math.isclose(
                            float(value), expected_value, rel_tol=1e-12, abs_tol=1e-10
                        )
                    else:
                        assert value == str(expected_value), (
                            spec["sheet"],
                            address,
                            value,
                            expected_value,
                        )
                    cells += 1
        for name, node in xmls.items():
            if name.startswith("xl/tables/") and name.endswith(".xml"):
                assert node.find("s:autoFilter", NS) is not None
                tables += 1
            if name.endswith(".rels"):
                base = posixpath.dirname(posixpath.dirname(name))
                for relation in node:
                    if relation.get("TargetMode") == "External":
                        continue
                    target = relation.get("Target")
                    resolved = (
                        target.lstrip("/")
                        if target.startswith("/")
                        else posixpath.normpath(posixpath.join(base, target))
                    )
                    assert resolved in archive.namelist(), (name, target)
        assert tables == 15
    docx = OUT / "P&Pmis_Wave_O1B_B1_AWP_Readiness_4D_Technical_Report.docx"
    with ZipFile(docx) as archive:
        assert archive.testzip() is None
        for name in archive.namelist():
            if name.endswith((".xml", ".rels")):
                ET.fromstring(archive.read(name))
    document = Document(docx)
    headings = [
        row.text for row in document.paragraphs if row.style.name == "Heading 1"
    ]
    assert len(headings) == 32 and all(
        row.startswith(str(index) + " ") for index, row in enumerate(headings, 1)
    )
    result = {
        "result": "PASS",
        "sheets": 15,
        "native_filtered_tables": tables,
        "compared_cells": cells,
        "discrepancies": 0,
        "word_heading1_sections": 32,
        "zip_crc_and_xml": "PASS",
        "formula_errors": 0,
        "broken_relationships": 0,
    }
    (QA / "native-artifact-verification.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
