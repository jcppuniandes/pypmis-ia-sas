"""Independent Cost OOXML checks; never author or repair deliverable content.

Adapts the validated O1B-B.1 verifier for 36 Word chapters and the 18 Cost
traceability sheets. Expected cell values come from the authoring run's separate
expected-tables.json, while native types, tables and links come from OOXML.
"""

import hashlib
import json
import math
import posixpath
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "outputs/.qa/wave-o1bc-20261022"
OUT = ROOT / "outputs/wave-o1bc-20261022"
DATA = ROOT / "docs/validation/wave-o1bc-20261022/package-data.json"
WORKBOOK = OUT / "P&Pmis_Wave_O1B_C_Cost_Foundation_Traceability.xlsx"
REPORT = OUT / "P&Pmis_Wave_O1B_C_Cost_Foundation_Technical_Report.docx"
REFERENCE = (
    ROOT
    / "outputs/wave-o1bb1-20261021/P&Pmis_Wave_O1B_B1_AWP_Readiness_4D_Technical_Report.docx"
)
EXPECTED_SHEETS = (
    "01_Requirements",
    "02_CBS",
    "03_Cost_Codes",
    "04_Control_Accounts",
    "05_Mappings",
    "06_APU_Rates",
    "07_Budget",
    "08_Cost_Baseline",
    "09_Phasing",
    "10_Commitments",
    "11_Actuals",
    "12_Accruals",
    "13_Currency",
    "14_Admin_User",
    "15_Security",
    "16_API",
    "17_Defects",
    "18_Release_Criteria",
)
NS = {
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}


def column_name(index):
    """One-based Excel column, including columns beyond Z."""
    result = ""
    while index:
        index, digit = divmod(index - 1, 26)
        result = chr(65 + digit) + result
    return result


def resolved_part(base, target):
    target = unquote(target.split("#", 1)[0])
    return (
        target.lstrip("/")
        if target.startswith("/")
        else posixpath.normpath(posixpath.join(base, target))
    )


def package_xml(archive):
    assert archive.testzip() is None, "ZIP CRC failure"
    names = archive.namelist()
    assert len(names) == len(set(names)), "Duplicate ZIP members"
    xmls = {
        name: ET.fromstring(archive.read(name))
        for name in names
        if name.endswith((".xml", ".rels"))
    }
    relationships = 0
    for name, node in xmls.items():
        if not name.endswith(".rels"):
            continue
        base = posixpath.dirname(posixpath.dirname(name))
        for relation in node:
            if relation.get("TargetMode") == "External":
                continue
            target = relation.get("Target")
            assert target, (name, "Relationship without Target")
            resolved = resolved_part(base, target)
            assert resolved in names, (name, target, "Broken relationship")
            relationships += 1
    return xmls, relationships


def cell_value(cell, shared):
    value = cell.findtext("s:v", default="", namespaces=NS)
    kind = cell.get("t", "n")
    if kind == "s":
        return shared[int(value)]
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.findall("s:is//s:t", NS))
    return value


def verify_workbook():
    expected = json.loads((QA / "workbook/expected-tables.json").read_text("utf-8"))
    assert tuple(row["sheet"] for row in expected) == EXPECTED_SHEETS
    compared, numeric, booleans, strings, blanks, tables = 0, 0, 0, 0, 0, 0
    with ZipFile(WORKBOOK) as archive:
        xmls, relationships = package_xml(archive)
        sheets = xmls["xl/workbook.xml"].findall("s:sheets/s:sheet", NS)
        assert tuple(row.get("name") for row in sheets) == EXPECTED_SHEETS
        rels = {
            row.get("Id"): row.get("Target")
            for row in xmls["xl/_rels/workbook.xml.rels"]
        }
        shared = [
            "".join(part.text or "" for part in row.findall(".//s:t", NS))
            for row in xmls.get("xl/sharedStrings.xml", [])
        ]
        for sheet, spec in zip(sheets, expected, strict=True):
            part = resolved_part("xl", rels[sheet.get("{" + NS["r"] + "}id")])
            node = xmls[part]
            pane = node.find("s:sheetViews/s:sheetView/s:pane", NS)
            assert pane is not None, (spec["sheet"], "No frozen pane")
            assert float(pane.get("ySplit", "0")) == 7, (
                spec["sheet"],
                "Seven header rows must remain frozen",
            )
            assert pane.get("state") in {"frozen", "frozenSplit"}
            actual = {}
            for cell in node.findall("s:sheetData/s:row/s:c", NS):
                assert cell.find("s:f", NS) is None, (
                    spec["sheet"],
                    "Unexpected formula",
                )
                assert cell.get("t") != "e", (spec["sheet"], "Excel error cell")
                actual[cell.get("r")] = cell
            headers = spec["headers"]
            assert headers and spec["rows"], (spec["sheet"], "Missing evidence rows")
            for row_index, values in enumerate([headers, *spec["rows"]], 7):
                assert len(values) == len(headers), (
                    spec["sheet"],
                    row_index,
                    "Ragged row",
                )
                for column, expected_value in enumerate(values, 1):
                    address = f"{column_name(column)}{row_index}"
                    cell = actual.get(address)
                    value = cell_value(cell, shared) if cell is not None else ""
                    kind = cell.get("t", "n") if cell is not None else None
                    location = (spec["sheet"], address)
                    if expected_value is None:
                        assert value == "", (*location, "Expected blank", value)
                        blanks += 1
                    elif isinstance(expected_value, bool):
                        assert kind == "b" and value == str(int(expected_value)), (
                            *location,
                            "Native Boolean mismatch",
                        )
                        booleans += 1
                    elif isinstance(expected_value, (int, float)):
                        assert kind == "n", (
                            *location,
                            "Number stored as nonnumeric",
                            kind,
                        )
                        assert math.isfinite(float(value)) and math.isclose(
                            float(value), expected_value, rel_tol=1e-12, abs_tol=1e-10
                        ), (*location, value, expected_value)
                        numeric += 1
                    else:
                        assert kind in {"s", "inlineStr", "str"}, (
                            *location,
                            "Text stored as nontext",
                            kind,
                        )
                        assert value == str(expected_value), (
                            *location,
                            value,
                            expected_value,
                        )
                        strings += 1
                    compared += 1
            parts = node.findall("s:tableParts/s:tablePart", NS)
            assert len(parts) == 1, (spec["sheet"], "Exactly one native table required")
            sheet_rels = posixpath.join(
                posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels"
            )
            table_relations = {entry.get("Id"): entry for entry in xmls[sheet_rels]}
            relation = table_relations[parts[0].get("{" + NS["r"] + "}id")]
            assert relation.get("Type", "").endswith("/table")
            table_part = resolved_part(posixpath.dirname(part), relation.get("Target"))
            table = xmls[table_part]
            bounds = f"A7:{column_name(len(headers))}{7 + len(spec['rows'])}"
            assert table.get("ref") == bounds, (spec["sheet"], "Table bounds mismatch")
            filtered = table.find("s:autoFilter", NS)
            assert filtered is not None and filtered.get("ref") == bounds
            columns = table.findall("s:tableColumns/s:tableColumn", NS)
            assert [column.get("name") for column in columns] == headers
            tables += 1
        native_tables = [
            name
            for name in xmls
            if name.startswith("xl/tables/") and name.endswith(".xml")
        ]
        assert len(native_tables) == tables == 18
    return {
        "sheets": 18,
        "native_filtered_tables": tables,
        "compared_cells": compared,
        "native_numeric_cells": numeric,
        "native_boolean_cells": booleans,
        "native_text_cells": strings,
        "blank_cells": blanks,
        "workbook_internal_relationships_checked": relationships,
    }


def verify_report():
    expected = json.loads(DATA.read_text("utf-8"))["chapters"]
    assert len(expected) == 36
    with ZipFile(REPORT) as archive:
        xmls, relationships = package_xml(archive)
        styles = {
            node.get("{" + NS["w"] + "}styleId"): node.find("w:name", NS).get(
                "{" + NS["w"] + "}val", ""
            )
            for node in xmls["word/styles.xml"].findall("w:style", NS)
            if node.find("w:name", NS) is not None
        }
        headings = []
        for paragraph in xmls["word/document.xml"].findall("w:body/w:p", NS):
            style = paragraph.find("w:pPr/w:pStyle", NS)
            if (
                style is not None
                and styles.get(style.get("{" + NS["w"] + "}val"), "").lower()
                == "heading 1"
            ):
                headings.append(
                    "".join(node.text or "" for node in paragraph.findall(".//w:t", NS))
                )
        assert headings == [
            f"{index} {title}" for index, (title, _) in enumerate(expected, 1)
        ], ("Word chapters must match all 36 evidence-backed headings", headings)
        with ZipFile(REFERENCE) as source:
            assert archive.namelist() == source.namelist(), (
                "Unexpected Word package parts"
            )
            changed = [
                name
                for name in source.namelist()
                if source.read(name) != archive.read(name)
            ]
            assert set(changed) == {"word/document.xml", "word/footer1.xml"}, (
                "Reference formatting parts changed",
                changed,
            )
            assert source.read("word/footer1.xml").replace(
                b"21 octubre 2026", b"23 octubre 2026"
            ) == archive.read("word/footer1.xml")
    manifest = json.loads((QA / "documents-build-manifest.json").read_text("utf-8"))
    assert (
        hashlib.sha256(REFERENCE.read_bytes()).hexdigest()
        == manifest["reference_sha256"]
    )
    assert hashlib.sha256(REPORT.read_bytes()).hexdigest() == manifest["output_sha256"]
    return {
        "word_heading1_sections": len(headings),
        "word_internal_relationships_checked": relationships,
        "retained_reference_parts": "PASS_DOCUMENT_BODY_AND_LITERAL_FOOTER_DATE_ONLY",
    }


def main():
    result = {
        "result": "PASS",
        **verify_workbook(),
        **verify_report(),
        "discrepancies": 0,
        "zip_crc_and_xml": "PASS",
        "formula_errors": 0,
        "broken_relationships": 0,
        "visual_review": "SEPARATE_RENDER_AND_HUMAN_INSPECTION_REQUIRED",
    }
    (QA / "native-artifact-verification.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
