"""Small real IFC geometry sources for isolated Scope validation, never production."""

from __future__ import annotations

import argparse
import csv
from io import BytesIO
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from zipfile import ZIP_DEFLATED, ZipFile


def scope_xlsx() -> bytes:
    """A genuine editable Office XLSX package, used only as a browser fixture."""
    with (Path(__file__).parent / "fixtures/scope-foundation-items.csv").open(encoding="utf-8", newline="") as source:
        values = list(csv.reader(source))
    worksheet = Element("worksheet", xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main")
    data = SubElement(worksheet, "sheetData")
    for row_index, row_values in enumerate(values, 1):
        row = SubElement(data, "row", r=str(row_index))
        for column, value in enumerate(row_values):
            cell = SubElement(row, "c", r=f"{chr(65 + column)}{row_index}", t="inlineStr")
            SubElement(SubElement(cell, "is"), "t").text = value
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Controlled Scope" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr("xl/worksheets/sheet1.xml", tostring(worksheet, encoding="utf-8", xml_declaration=True))
    return stream.getvalue()


def scope_ifc(
    *,
    count: int = 2,
    duplicate_guid: bool = False,
    missing_guid: bool = False,
    negative_quantity: bool = False,
    units: bool = True,
    unsupported: bool = False,
    zone: str = "A",
    length: float = 2.0,
    placement_offset: float = 0.0,
) -> bytes:
    import ifcopenshell
    import ifcopenshell.api.aggregate
    import ifcopenshell.api.context
    import ifcopenshell.api.geometry
    import ifcopenshell.api.pset
    import ifcopenshell.api.root
    import ifcopenshell.api.spatial
    import ifcopenshell.api.unit

    model = ifcopenshell.file(schema="IFC4")
    project = ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="Isolated O1B-A Source")
    project.GlobalId = ifcopenshell.guid.compress("0" * 31 + "1")
    if units:
        ifcopenshell.api.unit.assign_unit(
            model,
            units=[
                model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE"),
                model.create_entity("IfcSIUnit", UnitType="AREAUNIT", Name="SQUARE_METRE"),
                model.create_entity("IfcSIUnit", UnitType="VOLUMEUNIT", Name="CUBIC_METRE"),
            ],
        )
    context = ifcopenshell.api.context.add_context(model, context_type="Model")
    body = ifcopenshell.api.context.add_context(
        model, context_identifier="Body", context_type="Model", target_view="MODEL_VIEW", parent=context
    )
    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Isolated Site")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Isolated Building")
    level = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingStorey", name="L01")
    for number, entity in enumerate((site, building, level), 2):
        entity.GlobalId = ifcopenshell.guid.compress(f"{number:032x}")
    ifcopenshell.api.aggregate.assign_object(model, products=[site], relating_object=project)
    ifcopenshell.api.aggregate.assign_object(model, products=[building], relating_object=site)
    ifcopenshell.api.aggregate.assign_object(model, products=[level], relating_object=building)
    for index in range(count):
        product = ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcAnnotation" if unsupported else "IfcWall", name=f"Wall {index + 1}"
        )
        product.GlobalId = ifcopenshell.guid.compress(f"{100 if duplicate_guid else index + 100:032x}")
        if missing_guid and index == 0:
            product.GlobalId = ""
        if units:
            representation = ifcopenshell.api.geometry.add_wall_representation(
                model, context=body, length=length, height=3.0, thickness=0.2
            )
            ifcopenshell.api.geometry.assign_representation(model, product=product, representation=representation)
        product.ObjectPlacement = model.create_entity(
            "IfcLocalPlacement",
            RelativePlacement=model.create_entity(
                "IfcAxis2Placement3D",
                Location=model.create_entity(
                    "IfcCartesianPoint", Coordinates=(float(index * 3) + placement_offset, 0.0, 0.0)
                ),
            ),
        )
        ifcopenshell.api.spatial.assign_container(model, products=[product], relating_structure=level)
        pset = ifcopenshell.api.pset.add_pset(model, product=product, name="Pset_OperationalLocation")
        ifcopenshell.api.pset.edit_pset(
            model, pset=pset, properties={"Area": "North", "Zone": zone, "System": "Structural", "Discipline": "CIVIL"}
        )
        qto = ifcopenshell.api.pset.add_qto(model, product=product, name="Qto_WallBaseQuantities")
        ifcopenshell.api.pset.edit_qto(
            model, qto=qto, properties={"NetVolume": -1.0 if negative_quantity else length * 0.2 * 3.0}
        )
        material = model.create_entity("IfcMaterial", Name="Concrete C30")
        model.create_entity(
            "IfcRelAssociatesMaterial",
            GlobalId=ifcopenshell.guid.new(),
            RelatedObjects=[product],
            RelatingMaterial=material,
        )
    return model.to_string().encode("utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    args = parser.parse_args()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(scope_xlsx() if target.suffix.lower() == ".xlsx" else scope_ifc())
    print(target)
