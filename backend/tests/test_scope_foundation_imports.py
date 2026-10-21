"""Source ingestion is real IFC/XLSX parsing, independent of Scope approval."""

import hashlib
from io import BytesIO
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from tests.scope_foundation_fixture import scope_ifc

from app.modules.scope_foundation.imports import model_diff, parse_excel_source, parse_ifc_source


def _codes(result, level="errors"):
    return {finding["code"] for finding in result["validation"][level]}


def _xlsx(headers=None, rows=None, *, formula=False, sparse=False, external=False, duplicate_header=False):
    headers = headers or [
        "Scope Code",
        "Parent Scope Code",
        "Scope Name",
        "Scope Type",
        "Scope Nature",
        "Quantity",
        "Unit",
        "Source Reference",
    ]
    rows = rows or [["S-01", "", "Wall delivery", "WORK", "INSTALL", "12.5", "m3", "SOURCE-1"]]
    if duplicate_header:
        headers = [*headers, headers[0]]
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    sheet = Element("worksheet", xmlns=namespace)
    data = SubElement(sheet, "sheetData")
    for row_index, values in enumerate([headers, *rows], 1):
        physical = row_index + 5 if sparse and row_index > 1 else row_index
        row = SubElement(data, "row", r=str(physical))
        for column, value in enumerate(values):
            cell = SubElement(row, "c", r=f"{chr(65 + column)}{physical}", t="inlineStr")
            SubElement(SubElement(cell, "is"), "t").text = str(value)
            if formula and row_index > 1 and column == 5:
                SubElement(cell, "f").text = "1+2"
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", tostring(sheet))
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Controlled Scope" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        if external:
            archive.writestr("xl/externalLinks/externalLink1.xml", "external")
    return stream.getvalue()


def test_ifc_real_geometry_quantities_psets_materials_and_source_hash():
    content = scope_ifc()
    digest = hashlib.sha256(content).hexdigest()
    result = parse_ifc_source(content, "real-model.ifc")
    assert result["parser"] == "ifcopenshell"
    assert result["schema"] == "IFC4"
    assert result["validation"]["can_accept"]
    assert not result["validation"]["scope_approval_implied"]
    assert result["source_hash"] == digest
    assert hashlib.sha256(content).hexdigest() == digest
    walls = [obj for obj in result["objects"] if obj["ifc_class"] == "IfcWall"]
    assert len(walls) == 2
    assert walls[0]["guid"] != walls[1]["guid"]
    assert walls[0]["quantities"][0]["value"] == pytest.approx(1.2)
    assert walls[0]["quantities"][0]["unit"] == "m3"
    assert walls[0]["area"] == "North"
    assert walls[0]["zone"] == "A"
    assert walls[0]["system"] == "Structural"
    assert walls[0]["level"] == "L01"
    assert walls[0]["materials"] == ["Concrete C30"]
    assert walls[0]["geometry_reference"]["representation_id"]
    assert walls[0]["geometry_reference"]["source_geometry_unchanged"]


@pytest.mark.parametrize(
    "argument,code",
    [
        ({"duplicate_guid": True}, "DUPLICATE_GUID"),
        ({"missing_guid": True}, "MISSING_OBJECT_IDENTITY"),
        ({"negative_quantity": True}, "QUANTITY_EXTRACTION_ERROR"),
        ({"units": False}, "INVALID_MODEL_UNIT"),
    ],
)
def test_ifc_invalid_identity_units_and_quantities_are_reviewable_but_not_acceptable(argument, code):
    result = parse_ifc_source(scope_ifc(**argument), "candidate.ifc")
    assert code in _codes(result)
    assert not result["validation"]["can_accept"]
    assert result["source_hash"]


def test_ifc_unsupported_product_is_retained_and_explicitly_reported():
    result = parse_ifc_source(scope_ifc(unsupported=True), "candidate.ifc")
    assert "UNSUPPORTED_ENTITY_TYPE" in _codes(result, "warnings")
    assert any(obj["ifc_class"] == "IfcAnnotation" and not obj["supported"] for obj in result["objects"])


def test_ifc_version_diff_stable_guid_and_mapping_loss():
    previous = parse_ifc_source(scope_ifc(count=2), "v1.ifc")
    candidate = parse_ifc_source(scope_ifc(count=3), "v2.ifc", previous_objects=previous["objects"])
    assert len(candidate["diff"]["added"]) == 1
    assert candidate["diff"]["removed"] == []
    assert candidate["diff"]["modified"] == []
    mapped = [obj["guid"] for obj in previous["objects"] if obj["ifc_class"] == "IfcWall"]
    removed = parse_ifc_source(scope_ifc(count=1), "v3.ifc", previous_objects=previous["objects"], mapped_guids=mapped)
    assert len(removed["diff"]["removed"]) == 1
    assert len(removed["diff"]["mapping_impacts"]) == 1
    assert "MAPPING_BREAKAGE" in _codes(removed)
    assert "UNEXPECTED_OBJECT_LOSS" in _codes(removed, "warnings")


def test_ifc_version_diff_modified_classification_and_growth():
    previous = parse_ifc_source(scope_ifc(count=1, zone="A"), "v1.ifc")
    candidate = parse_ifc_source(scope_ifc(count=5, zone="B"), "v2.ifc", previous_objects=previous["objects"])
    assert candidate["diff"]["modified"]
    assert "UNEXPECTED_OBJECT_GROWTH" in _codes(candidate, "warnings")


def test_ifc_express_id_is_version_local_not_cross_version_diff_identity():
    previous = [{"guid": "", "express_id": 20, "name": "Same display name"}]
    current = [{"guid": "", "express_id": 20, "name": "Same display name"}]
    result = model_diff(previous, current)
    assert result["identity_basis"] == "IFC_GUID_ONLY_ACROSS_VERSIONS"
    assert result["version_local_objects"] == [20]
    assert result["modified"] == result["removed"] == result["added"] == []


def test_ifc_placement_change_is_a_geometry_diff_without_quantity_change():
    previous = parse_ifc_source(scope_ifc(count=1), "v1.ifc")
    candidate = parse_ifc_source(
        scope_ifc(count=1, placement_offset=5.0), "v2.ifc", previous_objects=previous["objects"]
    )
    guid = next(obj["guid"] for obj in previous["objects"] if obj["ifc_class"] == "IfcWall")
    assert candidate["diff"]["modified"] == [guid]
    assert candidate["diff"]["added"] == candidate["diff"]["removed"] == []


def test_ifc_diff_database_object_projection_ignores_db_metadata_and_preserves_geometry_hash():
    previous = parse_ifc_source(scope_ifc(count=1), "v1.ifc")
    persisted = [
        {
            key: value
            for key, value in obj.items()
            if key not in {"description", "geometry_hash", "source_hash", "ifc_type", "supported", "is_spatial"}
        }
        for obj in previous["objects"]
    ]
    for obj in persisted:
        obj.update(id=1000 + obj["express_id"], tenant_id=122, project_workspace_id=1004, model_version_id=1, version=1)
    current = parse_ifc_source(scope_ifc(count=1), "v2.ifc", previous_objects=persisted)
    assert current["diff"]["modified"] == []


@pytest.mark.parametrize(
    "content,filename,code",
    [
        (b"bad", "bad.ifc", "IFC_CONTAINER_INVALID"),
        (b"", "empty.ifc", "EMPTY_SOURCE"),
        (b"bad", "bad.txt", "UNSUPPORTED_SOURCE_FORMAT"),
    ],
)
def test_ifc_invalid_sources_fail_closed(content, filename, code):
    result = parse_ifc_source(content, filename)
    assert code in _codes(result)
    assert not result["validation"]["can_accept"]


def test_excel_valid_template_literal_quantities_and_physical_row_lineage():
    content = _xlsx(sparse=True)
    result = parse_excel_source(content, "scope.xlsx")
    assert result["validation"]["can_accept"]
    assert result["worksheet"] == "Controlled Scope"
    assert result["rows"][0]["lineage"]["row_number"] == 7
    assert result["rows"][0]["lineage"]["source_row_id"] == "Controlled Scope!7"
    assert result["rows"][0]["quantity"] == 12.5
    assert result["rows"][0]["source_quantity"] == 12.5
    assert result["rows"][0]["unit"] == "m3"
    assert result["rows"][0]["source_revision"] == hashlib.sha256(content).hexdigest()
    assert result["validation"]["scope_approval_implied"] is False


@pytest.mark.parametrize("nature", ["INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"])
def test_excel_each_scope_nature_has_independent_semantics(nature):
    result = parse_excel_source(
        _xlsx(rows=[["S-01", "", "Intervention", "WORK", nature, "3", "ea", "SRC"]]), "source.xlsx"
    )
    assert result["validation"]["can_accept"]
    assert result["rows"][0]["scope_nature"] == nature


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("Scope Nature", "BUILD_WHATEVER", "INVALID_SCOPE_NATURE"),
        ("Unit", "unknown", "INVALID_UNIT"),
        ("Quantity", "NaN", "INVALID_QUANTITY"),
        ("Quantity", "Infinity", "INVALID_QUANTITY"),
        ("Quantity", "-3", "INVALID_QUANTITY"),
        ("Quantity", "1,000", "INVALID_QUANTITY"),
        ("Parent Scope Code", "absent", "MISSING_PARENT"),
        ("Scope Type", "COST_BASELINE", "INVALID_SCOPE_TYPE"),
    ],
)
def test_excel_invalid_governed_values_block_candidate(field, value, code):
    headers = [
        "Scope Code",
        "Parent Scope Code",
        "Scope Name",
        "Scope Type",
        "Scope Nature",
        "Quantity",
        "Unit",
        "Source Reference",
    ]
    row = ["S-01", "", "Intervention", "WORK", "INSTALL", "3", "ea", "SRC"]
    row[headers.index(field)] = value
    result = parse_excel_source(_xlsx(headers=headers, rows=[row]), "source.xlsx")
    assert code in _codes(result)
    assert not result["validation"]["can_accept"]


def test_excel_invalid_headers_mapping_and_duplicate_header():
    result = parse_excel_source(_xlsx(headers=["code", "label"], rows=[["S", "Test"]]), "source.xlsx")
    assert "MISSING_REQUIRED_HEADER" in _codes(result)
    duplicate = parse_excel_source(_xlsx(duplicate_header=True), "source.xlsx")
    assert "DUPLICATE_HEADER" in _codes(duplicate)
    assert "DUPLICATE_FIELD_MAPPING" in _codes(duplicate)


def test_excel_duplicate_scope_code_source_row_and_cycle_detection():
    row = ["S-01", "", "Intervention", "WORK", "INSTALL", "3", "ea", "SRC"]
    result = parse_excel_source(_xlsx(rows=[row, row]), "source.xlsx")
    assert {"DUPLICATE_SCOPE_CODE", "DUPLICATE_SOURCE_ROW"} <= _codes(result)
    cyclic = parse_excel_source(_xlsx(rows=[["S-01", "S-02", *row[2:]], ["S-02", "S-01", *row[2:]]]), "source.xlsx")
    assert "SCOPE_HIERARCHY_CYCLE" in _codes(cyclic)


def test_excel_field_mapping_existing_parent_future_apu_mapping_stays_inactive():
    headers = ["Code", "Parent", "Title", "Nature", "Qty", "UOM", "APU Code"]
    result = parse_excel_source(
        _xlsx(headers=headers, rows=[["S-01", "ROOT", "Concrete", "INSTALL", "2", "m³", "APU-3"]]),
        "source.xlsx",
        field_mapping={"Code": "scope_code", "Parent": "parent_scope_code", "Title": "name"},
        existing_scope_codes={"ROOT"},
    )
    assert result["validation"]["can_accept"]
    assert result["rows"][0]["unit"] == "m3"
    assert result["rows"][0]["quantity"] == 2
    assert result["rows"][0]["future_mappings"] == {"apu_code": "APU-3"}
    assert not result["rows"][0]["future_mappings_active"]


@pytest.mark.parametrize(
    "option,code",
    [({"formula": True}, "FORMULA_SOURCE_NOT_SUPPORTED"), ({"external": True}, "ACTIVE_WORKBOOK_CONTENT")],
)
def test_excel_formulas_and_external_links_not_imported_as_literal_scope(option, code):
    result = parse_excel_source(_xlsx(**option), "source.xlsx")
    assert code in _codes(result)


def test_excel_repeat_parser_is_deterministic_no_approval_or_scope_side_effects():
    content = _xlsx()
    first = parse_excel_source(content, "source.xlsx")
    second = parse_excel_source(content, "source.xlsx")
    assert first == second
    assert first["source_immutable"]
    assert not first["validation"]["scope_approval_implied"]


def test_excel_csv_fixture_valid_without_any_ifc_source():
    content = (Path(__file__).parent / "fixtures/scope-foundation-items.csv").read_bytes()
    result = parse_excel_source(content, "scope-items.csv")
    assert result["validation"]["can_accept"]
    assert result["row_count"] == 4
    assert {row["scope_nature"] for row in result["rows"]} == {"INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"}


@pytest.mark.parametrize("filename,content", [("bad.xlsx", b"bad"), ("old.xls", b"bad"), ("empty.xlsx", b"")])
def test_excel_invalid_formats_and_empty_sources_are_reviewable_failure(filename, content):
    result = parse_excel_source(content, filename)
    assert result["validation"]["error_count"]
    assert not result["validation"]["can_accept"]
