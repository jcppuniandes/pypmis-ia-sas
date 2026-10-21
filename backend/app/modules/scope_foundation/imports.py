"""Read-only governed source parsers for Scope; importing never approves Scope.

IFCOpenShell is the installed IFC engine already used by geometry services.
Existing takeoff XLSX token readers and IFC product support are reused, while
Scope-specific identity, unit, source-row, validation and diff rules live here.
No parser writes the source, a legacy takeoff, Scope items, or a baseline.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import posixpath
from collections import Counter
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from pathlib import PurePath
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from app.services.quantity_takeoff import IFC_PRODUCT_CLASSES, QuantityTakeoffService

MAX_SOURCE_BYTES = 40 * 1024 * 1024
MAX_XLSX_EXPANDED_BYTES = 80 * 1024 * 1024
MAX_SOURCE_ROWS = 20_000
MAX_BIM_OBJECTS = 40_000
DEFAULT_UNITS = ("m", "m2", "m3", "kg", "t", "ea", "h")
DEFAULT_NATURES = ("INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE")
SHEET_NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
HEADERS = {
    "scope_code": ("scope code", "scope_code", "codigo alcance", "código alcance"),
    "parent_scope_code": ("parent scope code", "parent_scope_code", "codigo padre", "código padre"),
    "name": ("scope name", "scope_name", "name", "nombre"),
    "description": ("description", "descripcion", "descripción"),
    "scope_type": ("scope type", "scope_type", "tipo de alcance"),
    "scope_nature": ("scope nature", "scope_nature", "nature", "naturaleza"),
    "discipline": ("discipline", "disciplina"),
    "area": ("area", "área"),
    "level": ("level", "nivel"),
    "zone": ("zone", "zona"),
    "system": ("system", "sistema"),
    "location": ("location", "ubicacion", "ubicación"),
    "quantity": ("quantity", "qty", "cantidad"),
    "unit": ("unit", "uom", "unidad"),
    "source_reference": ("source reference", "source_reference", "referencia fuente"),
    "source_row_id": ("source row id", "source_row_id", "row id"),
    "measurement_method": ("measurement method", "measurement_method", "metodo medicion"),
    "wbs_code": ("wbs code", "wbs_code"),
    "cbs_code": ("cbs code", "cbs_code"),
    "apu_code": ("apu code", "apu_code"),
    "package_code": ("package code", "package_code"),
    "contract_package": ("contract package", "contract_package"),
}
REQUIRED_FIELDS = {"scope_code", "name", "scope_nature", "quantity", "unit"}
FUTURE_FIELDS = {"wbs_code", "cbs_code", "apu_code", "package_code", "contract_package"}


def _normal(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _unit(value: Any) -> str:
    return str(value or "").strip().replace("²", "2").replace("³", "3")


def _codes(config: dict, key: str, default: tuple[str, ...]) -> set[str]:
    values = config.get(key, default)
    if isinstance(values, dict):
        return {str(key) for key, value in values.items() if value is not False}
    return {str(value.get("code", "")) if isinstance(value, dict) else str(value) for value in values}


def _json(value: Any) -> Any:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set):
        return [_json(item) for item in value]
    return str(value)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(_json(value), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _finding(code: str, message: str, **details: Any) -> dict:
    return {"code": code, "message": message, **details}


def _validation(errors: list[dict], warnings: list[dict]) -> dict:
    return {
        "errors": errors,
        "warnings": warnings,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "can_accept": not errors,
        "scope_approval_implied": False,
    }


def _source(content: bytes, filename: str) -> dict:
    return {
        "source_file_name": PurePath(filename.replace("\\", "/")).name,
        "source_hash": hashlib.sha256(content).hexdigest(),
        "source_size_bytes": len(content),
        "source_immutable": True,
    }


def _source_errors(content: bytes, filename: str, extensions: set[str]) -> list[dict]:
    errors = []
    if not content:
        errors.append(_finding("EMPTY_SOURCE", "Source is empty."))
    if len(content) > MAX_SOURCE_BYTES:
        errors.append(_finding("SOURCE_SIZE_LIMIT", "Source exceeds the 40 MiB synchronous import limit."))
    if PurePath(filename).suffix.lower() not in extensions:
        errors.append(_finding("UNSUPPORTED_SOURCE_FORMAT", "Unsupported source file extension."))
    return errors


def _ifc_unit(model: Any, unit_type: str, explicit: Any = None) -> dict:
    """Resolve source units without changing a quantity or assuming SI metres."""
    from ifcopenshell.util.unit import get_project_unit

    entity = explicit or get_project_unit(model, unit_type)
    implicit_power = {"AREAUNIT": 2, "VOLUMEUNIT": 3}.get(unit_type, 1)
    derived_from_length = False
    if entity is None and implicit_power > 1:
        entity = get_project_unit(model, "LENGTHUNIT")
        derived_from_length = entity is not None
    if entity is None:
        return {"code": "", "known": False, "basis": "MISSING_PROJECT_OR_QUANTITY_UNIT"}
    info = entity.get_info()
    name = str(info.get("Name") or "")
    prefix = str(info.get("Prefix") or "")
    conversion_basis = None
    if entity.is_a("IfcConversionBasedUnit"):
        factor = getattr(entity, "ConversionFactor", None)
        value = getattr(getattr(factor, "ValueComponent", None), "wrappedValue", None)
        if factor is None or not isinstance(value, int | float) or not math.isfinite(value) or value <= 0:
            return {"code": "", "known": False, "basis": "INVALID_CONVERSION_BASED_UNIT"}
        conversion_basis = {"factor": value, "unit_type": factor.UnitComponent.is_a(), "source_name": name}
        name_key = _normal(name).replace(" ", "")
        name = {
            "foot": "ft",
            "feet": "ft",
            "inch": "in",
            "squarefoot": "ft2",
            "squarefeet": "ft2",
            "cubicfoot": "ft3",
            "cubicfeet": "ft3",
            "tonne": "t",
            "hour": "h",
            "minute": "min",
        }.get(name_key, name)
    elif not entity.is_a("IfcSIUnit"):
        return {"code": name, "known": False, "basis": "UNRESOLVED_CONTEXT_DEPENDENT_UNIT"}
    power = implicit_power if derived_from_length else 1
    basic = {
        "METRE": "m",
        "METER": "m",
        "SQUARE_METRE": "m2",
        "CUBIC_METRE": "m3",
        "GRAM": "g",
        "SECOND": "s",
        "RADIAN": "rad",
        "STERADIAN": "sr",
    }.get(name.upper(), name)
    if prefix:
        prefixes = {"MILLI": "m", "CENTI": "c", "KILO": "k", "MICRO": "u", "DECI": "d"}
        basic = prefixes.get(prefix.upper(), prefix.lower()) + basic
    if power > 1:
        basic += str(power)
    return {
        "code": basic,
        "known": bool(basic),
        "basis": "PROJECT_LENGTH_POWER"
        if derived_from_length
        else "EXPLICIT_QUANTITY_UNIT"
        if explicit
        else "PROJECT_UNIT",
        "ifc_unit_id": entity.id(),
        "ifc_unit_type": entity.is_a(),
        "name": name,
        "prefix": prefix,
        "conversion_applied": False,
        "conversion_basis": conversion_basis,
    }


def _quantities(model: Any, product: Any, errors: list[dict], warnings: list[dict]) -> list[dict]:
    definitions = {
        "IfcQuantityLength": ("LengthValue", "LENGTHUNIT"),
        "IfcQuantityArea": ("AreaValue", "AREAUNIT"),
        "IfcQuantityVolume": ("VolumeValue", "VOLUMEUNIT"),
        "IfcQuantityWeight": ("WeightValue", "MASSUNIT"),
        "IfcQuantityTime": ("TimeValue", "TIMEUNIT"),
        "IfcQuantityCount": ("CountValue", "COUNTUNIT"),
    }
    result = []
    for relationship in getattr(product, "IsDefinedBy", ()) or ():
        definition = getattr(relationship, "RelatingPropertyDefinition", None)
        if definition is None or not definition.is_a("IfcElementQuantity"):
            continue
        pending = list(definition.Quantities or ())
        while pending:
            quantity = pending.pop(0)
            if quantity.is_a("IfcPhysicalComplexQuantity"):
                pending.extend(quantity.HasQuantities or ())
                continue
            specification = definitions.get(quantity.is_a())
            if not specification:
                warnings.append(
                    _finding(
                        "UNSUPPORTED_QUANTITY_TYPE",
                        "Quantity type is retained for review, not guessed.",
                        express_id=quantity.id(),
                        ifc_type=quantity.is_a(),
                    )
                )
                continue
            attribute, unit_type = specification
            value = getattr(quantity, attribute, None)
            if not isinstance(value, int | float) or not math.isfinite(value) or value < 0:
                errors.append(
                    _finding(
                        "QUANTITY_EXTRACTION_ERROR",
                        "IFC quantity must be finite and nonnegative.",
                        express_id=product.id(),
                        quantity_id=quantity.id(),
                        value=_json(value),
                    )
                )
            unit = {"code": "ea", "known": True, "basis": "IFC_COUNT", "conversion_applied": False}
            if unit_type != "COUNTUNIT":
                unit = _ifc_unit(model, unit_type, getattr(quantity, "Unit", None))
                if not unit["known"]:
                    errors.append(
                        _finding(
                            "INVALID_UNIT",
                            "Quantity has no known source unit.",
                            express_id=product.id(),
                            quantity_id=quantity.id(),
                        )
                    )
            result.append(
                {
                    "name": quantity.Name or quantity.is_a(),
                    "set_name": definition.Name or "",
                    "value": _json(value),
                    "unit": unit["code"],
                    "unit_basis": unit,
                    "source": "IFCELEMENTQUANTITY",
                    "express_id": quantity.id(),
                }
            )
    if not result:
        result.append(
            {
                "name": "ElementCount",
                "value": 1,
                "unit": "ea",
                "source": "OBJECT_COUNT",
                "unit_basis": {"basis": "OBJECT_COUNT", "conversion_applied": False},
            }
        )
        warnings.append(
            _finding(
                "NO_PUBLISHED_QUANTITY",
                "Only explicit object-count quantity is available; no geometric quantity is invented.",
                express_id=product.id(),
            )
        )
    return result


def _classification(product: Any) -> list[dict]:
    result = []
    for relationship in getattr(product, "HasAssociations", ()) or ():
        reference = getattr(relationship, "RelatingClassification", None)
        if reference is not None:
            result.append(
                {
                    "express_id": reference.id(),
                    "type": reference.is_a(),
                    "code": getattr(reference, "Identification", None) or getattr(reference, "ItemReference", "") or "",
                    "name": getattr(reference, "Name", "") or "",
                }
            )
    return result


def _property_location(properties: dict, key: str) -> str:
    for group in properties.values():
        if isinstance(group, dict):
            for name, value in group.items():
                if _normal(name) == key and value is not None:
                    return str(value)
    return ""


def _geometry_signature(product: Any) -> str:
    """Hash semantic source representation without version-local STEP numbers."""
    nodes = 0
    visiting: set[int] = set()

    def visit(value: Any, depth: int = 0) -> Any:
        nonlocal nodes
        if value is None or isinstance(value, str | int | float | bool):
            return _json(value)
        if isinstance(value, tuple | list):
            return [visit(item, depth + 1) for item in value]
        if not hasattr(value, "is_a"):
            return str(value)
        nodes += 1
        if depth > 80 or nodes > 100_000:
            raise ValueError("SOURCE_REPRESENTATION_LIMIT")
        key = value.id()
        if key and key in visiting:
            return {"cyclic_type": value.is_a()}
        if key:
            visiting.add(key)
        result = {"type": value.is_a()}
        for index in range(len(value)):
            result[value.attribute_name(index)] = visit(value[index], depth + 1)
        if key:
            visiting.remove(key)
        return result

    return _fingerprint(
        {
            "representation": visit(getattr(product, "Representation", None)),
            "placement": visit(getattr(product, "ObjectPlacement", None)),
        }
    )


def model_diff(
    previous_objects: list[dict] | None, objects: list[dict], mapped_guids: list[str] | set[str] | None = None
) -> dict:
    """GUID identity survives versions; ExpressID fallback is never cross-version authority."""
    previous = {str(obj.get("guid")): obj for obj in previous_objects or [] if obj.get("guid")}
    current = {str(obj.get("guid")): obj for obj in objects if obj.get("guid")}

    def meaning(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                key: meaning(value)
                for key, value in obj.items()
                if key
                not in {
                    "id",
                    "express_id",
                    "quantity_id",
                    "ifc_unit_id",
                    "representation_id",
                    "source_identity",
                    "source_hash",
                    "geometry_reference",
                    "source_fingerprint",
                }
            }
        if isinstance(obj, list):
            return [meaning(value) for value in obj]
        return obj

    def comparable(obj: dict) -> dict:
        fields = {
            key: obj.get(key)
            for key in (
                "guid",
                "ifc_class",
                "name",
                "properties",
                "quantities",
                "classification",
                "discipline",
                "level",
                "area",
                "zone",
                "system",
                "materials",
            )
        }
        reference = obj.get("geometry_reference") or {}
        fields["description"] = obj.get("description", reference.get("source_description", ""))
        fields["geometry_hash"] = obj.get("geometry_hash", reference.get("geometry_hash", ""))
        return meaning(fields)

    added = sorted(current.keys() - previous.keys())
    removed = sorted(previous.keys() - current.keys())
    modified = sorted(
        key
        for key in current.keys() & previous.keys()
        if _fingerprint(comparable(previous[key])) != _fingerprint(comparable(current[key]))
    )
    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "mapping_impacts": sorted(set(mapped_guids or []) - current.keys()),
        "previous_count": len(previous_objects or []),
        "current_count": len(objects),
        "identity_basis": "IFC_GUID_ONLY_ACROSS_VERSIONS",
        "version_local_objects": [obj["express_id"] for obj in objects if not obj.get("guid")],
    }


def parse_ifc_source(
    content: bytes,
    filename: str,
    config: dict | None = None,
    previous_objects: list[dict] | None = None,
    mapped_guids: list[str] | set[str] | None = None,
) -> dict:
    config = config or {}
    errors = _source_errors(content, filename, {".ifc"})
    warnings: list[dict] = []
    result = {
        **_source(content, filename),
        "source_type": "IFC",
        "schema": "",
        "objects": [],
        "object_count": 0,
        "units": {},
        "parser": "ifcopenshell",
        "parse_complete": False,
    }
    if errors:
        return {**result, "validation": _validation(errors, warnings), "diff": model_diff(previous_objects, [])}
    if (
        not content.lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"ISO-10303-21;")
        or b"FILE_SCHEMA" not in content[:100_000].upper()
    ):
        errors.append(
            _finding("IFC_CONTAINER_INVALID", "Source must be an IFC STEP exchange file with an explicit FILE_SCHEMA.")
        )
        return {**result, "validation": _validation(errors, warnings), "diff": model_diff(previous_objects, [])}
    try:
        import ifcopenshell
        from ifcopenshell.util.element import get_container, get_materials, get_psets

        text = content.decode("utf-8-sig")
        model = ifcopenshell.file.from_string(text)
        result["schema"] = model.schema
        products = model.by_type("IfcProduct")
        if not products:
            errors.append(_finding("EMPTY_IFC_MODEL", "IFC contains no BIM products for source-model review."))
        if len(products) > MAX_BIM_OBJECTS:
            errors.append(
                _finding("BIM_OBJECT_LIMIT", "Too many products for synchronous governed import.", count=len(products))
            )
            return {**result, "validation": _validation(errors, warnings), "diff": model_diff(previous_objects, [])}
        units = _ifc_unit(model, "LENGTHUNIT")
        result["units"] = units
        if not units["known"]:
            errors.append(
                _finding(
                    "INVALID_MODEL_UNIT", "IFC project has no known length unit; no global metre assumption is made."
                )
            )
        guids: Counter = Counter(str(getattr(product, "GlobalId", "") or "") for product in products)
        mappings = config.get("ifc_classification_mapping", config.get("ifc_classification_mapping_rules", {}))
        mappings = mappings if isinstance(mappings, dict) else {}
        supported = {str(item).upper() for item in config.get("supported_ifc_types", IFC_PRODUCT_CLASSES)}
        for product in products:
            guid = str(getattr(product, "GlobalId", "") or "").strip()
            identity = guid or f"EXPRESS:{product.id()}@{result['source_hash']}"
            if not guid:
                errors.append(
                    _finding(
                        "MISSING_OBJECT_IDENTITY",
                        "Product has no IFC GUID; ExpressID remains version-local and cannot silently replace it.",
                        express_id=product.id(),
                    )
                )
            elif (
                len(guid) != 22
                or guid[0] not in "0123"
                or any(
                    character not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$"
                    for character in guid
                )
            ):
                errors.append(
                    _finding(
                        "INVALID_GUID",
                        "Source GlobalId is not a valid compressed IFC GUID.",
                        guid=guid,
                        express_id=product.id(),
                    )
                )
            elif guids[guid] > 1:
                errors.append(
                    _finding(
                        "DUPLICATE_GUID",
                        "IFC GUID occurs more than once in this version.",
                        guid=guid,
                        express_id=product.id(),
                    )
                )
            properties = _json(get_psets(product, psets_only=True))
            container = get_container(product)
            kind = product.is_a()
            is_spatial = (
                product.is_a("IfcSpatialElement")
                if model.schema.startswith("IFC4")
                else product.is_a("IfcSpatialStructureElement")
            )
            is_supported = kind.upper() in supported or is_spatial
            if not is_supported:
                warnings.append(
                    _finding(
                        "UNSUPPORTED_ENTITY_TYPE",
                        "Source product is preserved but requires explicit Scope mapping review.",
                        ifc_type=kind,
                        express_id=product.id(),
                    )
                )
            classification_mapping = mappings.get(kind, mappings.get(kind.upper(), {}))
            classification_mapping = classification_mapping if isinstance(classification_mapping, dict) else {}
            groups = [
                getattr(getattr(rel, "RelatingGroup", None), "Name", "") or ""
                for rel in getattr(product, "HasAssignments", ()) or ()
            ]
            obj = {
                "source_identity": identity,
                "guid": guid,
                "express_id": product.id(),
                "ifc_class": kind,
                "ifc_type": kind,
                "name": str(product.Name or ""),
                "description": str(getattr(product, "Description", "") or ""),
                "properties": properties,
                "quantities": _quantities(model, product, errors, warnings),
                "classification": _classification(product),
                "discipline": str(
                    classification_mapping.get("discipline") or _property_location(properties, "discipline")
                ),
                "level": str(getattr(container, "Name", "") or _property_location(properties, "level")),
                "area": _property_location(properties, "area"),
                "zone": _property_location(properties, "zone"),
                "system": _property_location(properties, "system") or ", ".join(filter(None, groups)),
                "materials": [str(material.Name or "") for material in get_materials(product)],
                "geometry_reference": {
                    "source_hash": result["source_hash"],
                    "express_id": product.id(),
                    "guid": guid,
                    "representation_id": getattr(product, "Representation", None).id()
                    if getattr(product, "Representation", None)
                    else None,
                    "engine": "web-ifc/three",
                    "source_geometry_unchanged": True,
                },
                "geometry_hash": _geometry_signature(product),
                "source_hash": result["source_hash"],
                "supported": is_supported,
                "is_spatial": is_spatial,
                "scope_mapping_suggestion": classification_mapping,
            }
            obj["geometry_reference"]["geometry_hash"] = obj["geometry_hash"]
            obj["geometry_reference"]["source_description"] = obj["description"]
            obj["source_fingerprint"] = _fingerprint(obj)
            result["objects"].append(obj)
        result["object_count"] = len(result["objects"])
        result["parse_complete"] = True
    except Exception as exc:
        # Return reviewable failure staging without leaking a source file or an
        # internal path; never fall back to a name/regex-generated identity.
        errors.append(
            _finding(
                "IFC_PARSE_ERROR", "IFCOpenShell could not fully parse this source.", error_type=type(exc).__name__
            )
        )
    diff = model_diff(previous_objects, result["objects"], mapped_guids)
    if previous_objects is not None:
        old_count = len(previous_objects)
        loss = (old_count - result["object_count"]) / old_count if old_count else 0
        growth = (result["object_count"] - old_count) / old_count if old_count else 0
        if loss > float(config.get("model_loss_review_fraction", 0.1)):
            warnings.append(
                _finding("UNEXPECTED_OBJECT_LOSS", "Model object loss requires explicit review.", fraction=loss)
            )
        if growth > float(config.get("model_growth_review_fraction", 0.5)):
            warnings.append(
                _finding("UNEXPECTED_OBJECT_GROWTH", "Model object growth requires explicit review.", fraction=growth)
            )
    if diff["mapping_impacts"]:
        errors.append(
            _finding(
                "MAPPING_BREAKAGE",
                "Mapped IFC GUIDs are absent in the candidate version; reconcile mappings before acceptance.",
                guids=diff["mapping_impacts"],
            )
        )
    return {**result, "validation": _validation(errors, warnings), "diff": diff}


def _spreadsheet_rows(content: bytes, filename: str) -> tuple[list[str], list[tuple[int, list[str]]], str]:
    if PurePath(filename).suffix.lower() == ".csv":
        rows = []
        for index, row in enumerate(csv.reader(StringIO(content.decode("utf-8-sig")))):
            if index > MAX_SOURCE_ROWS:
                raise ValueError("SOURCE_ROW_LIMIT")
            if len(row) > 64:
                raise ValueError("SOURCE_COLUMN_LIMIT")
            rows.append(row)
        return (rows[0], list(enumerate(rows[1:], 2)), "CSV") if rows else ([], [], "CSV")
    with ZipFile(BytesIO(content)) as archive:
        if (
            len(archive.infolist()) > 1000
            or sum(info.file_size for info in archive.infolist()) > MAX_XLSX_EXPANDED_BYTES
        ):
            raise ValueError("XLSX_EXPANSION_LIMIT")
        if any("vbaproject" in name.lower() or "externallinks/" in name.lower() for name in archive.namelist()):
            raise ValueError("ACTIVE_WORKBOOK_CONTENT")
        sheet_name = "xl/worksheets/sheet1.xml"
        worksheet = "Sheet1"
        if "xl/workbook.xml" in archive.namelist() and "xl/_rels/workbook.xml.rels" in archive.namelist():
            book = ET.fromstring(archive.read("xl/workbook.xml"))
            first_sheet = book.find("s:sheets/s:sheet", SHEET_NS)
            if first_sheet is None:
                raise ValueError("MISSING_FIRST_WORKSHEET")
            worksheet = first_sheet.attrib.get("name", "Sheet1")
            relationship_id = first_sheet.attrib.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            )
            relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            relationship = next((entry for entry in relationships if entry.attrib.get("Id") == relationship_id), None)
            if relationship is None or relationship.attrib.get("TargetMode") == "External":
                raise ValueError("INVALID_WORKSHEET_RELATIONSHIP")
            target = relationship.attrib.get("Target", "")
            sheet_name = posixpath.normpath(target.lstrip("/") if target.startswith("/") else f"xl/{target}")
            if not sheet_name.startswith("xl/worksheets/"):
                raise ValueError("INVALID_WORKSHEET_RELATIONSHIP")
        if sheet_name not in archive.namelist():
            raise ValueError("MISSING_FIRST_WORKSHEET")
        xml = archive.read(sheet_name)
        tree = ET.fromstring(xml)
        if tree.findall(".//s:f", SHEET_NS):
            raise ValueError("FORMULA_SOURCE_NOT_SUPPORTED")
        cells = tree.findall(".//s:c", SHEET_NS)
        if len(cells) > MAX_SOURCE_ROWS * 64:
            raise ValueError("SOURCE_CELL_LIMIT")
        for cell in cells:
            reference = cell.attrib.get("r", "")
            letters = "".join(character for character in reference if character.isalpha()).upper()
            column = 0
            for letter in letters:
                column = column * 26 + ord(letter) - ord("A") + 1
            if not column or column > 64:
                raise ValueError("SOURCE_COLUMN_LIMIT")
        parser = QuantityTakeoffService(None)
        shared = parser._xlsx_shared_strings(archive)
        values = parser._xlsx_sheet_values(xml, shared)
        physical_rows = [
            int(row.attrib.get("r", index + 1))
            for index, row in enumerate(tree.findall(".//s:row", SHEET_NS))
            if row.findall("s:c", SHEET_NS)
        ]
        return (
            (values[0], list(zip(physical_rows[1:], values[1:], strict=True)), worksheet)
            if values
            else ([], [], worksheet)
        )


def parse_excel_source(
    content: bytes,
    filename: str,
    config: dict | None = None,
    field_mapping: dict[str, str] | None = None,
    existing_scope_codes: list[str] | set[str] | None = None,
) -> dict:
    config = config or {}
    errors = _source_errors(content, filename, {".xlsx", ".csv"})
    warnings: list[dict] = []
    result = {
        **_source(content, filename),
        "source_type": "EXCEL",
        "headers": [],
        "rows": [],
        "worksheet": "",
        "field_mapping": {},
    }
    if errors:
        return {**result, "validation": _validation(errors, warnings)}
    try:
        headers, source_rows, worksheet = _spreadsheet_rows(content, filename)
    except (BadZipFile, KeyError, UnicodeError, ET.ParseError, ValueError, csv.Error, IndexError) as exc:
        code = str(exc) if isinstance(exc, ValueError) and str(exc).isupper() else "INVALID_WORKBOOK"
        errors.append(
            _finding(
                code, "Workbook cannot be imported safely; use a plain XLSX or UTF-8 CSV with literal source values."
            )
        )
        return {**result, "validation": _validation(errors, warnings)}
    result.update(headers=headers, worksheet=worksheet)
    if len(source_rows) > MAX_SOURCE_ROWS:
        errors.append(_finding("SOURCE_ROW_LIMIT", "Workbook exceeds the 20,000-row synchronous import limit."))
        return {**result, "validation": _validation(errors, warnings)}
    aliases = {_normal(alias): field for field, options in HEADERS.items() for alias in options}
    explicit: dict[str, str] = {}
    for key, value in (field_mapping or {}).items():
        if value in HEADERS:
            explicit[_normal(key)] = value
        elif key in HEADERS:
            explicit[_normal(value)] = key
        else:
            errors.append(
                _finding("INVALID_FIELD_MAPPING", "Mapping target is not a Scope field.", source=key, target=value)
            )
    mapped: dict[int, str] = {}
    seen_headers: set[str] = set()
    for index, header in enumerate(headers):
        normalized = _normal(header)
        if not normalized:
            if any(index < len(values) and str(values[index]).strip() for _, values in source_rows):
                errors.append(_finding("UNNAMED_DATA_COLUMN", "Data column has no template header.", column=index + 1))
            continue
        if normalized in seen_headers:
            errors.append(_finding("DUPLICATE_HEADER", "Duplicate normalized workbook column header.", header=header))
        seen_headers.add(normalized)
        field = explicit.get(normalized) or aliases.get(normalized)
        if field:
            if field in mapped.values():
                errors.append(
                    _finding("DUPLICATE_FIELD_MAPPING", "Multiple columns map to one Scope field.", field=field)
                )
            mapped[index] = field
        elif normalized:
            warnings.append(
                _finding("UNMAPPED_COLUMN", "Unmapped source column is retained in source lineage only.", header=header)
            )
    for field in sorted(REQUIRED_FIELDS - set(mapped.values())):
        errors.append(_finding("MISSING_REQUIRED_HEADER", "Required Scope field has no source column.", field=field))
    result["field_mapping"] = {headers[index]: field for index, field in mapped.items()}
    if errors:
        return {**result, "validation": _validation(errors, warnings)}
    natures = _codes(config, "scope_natures", DEFAULT_NATURES)
    units = {_unit(value) for value in _codes(config, "units", DEFAULT_UNITS)}
    scope_types = _codes(config, "scope_types", ("DELIVERABLE", "WORK", "SERVICE"))
    existing = set(existing_scope_codes or [])
    code_rows: dict[str, int] = {}
    row_ids: dict[str, int] = {}
    fingerprints: dict[str, int] = {}
    for row_number, values in source_rows:
        if not any(str(value).strip() for value in values):
            continue
        raw = {
            str(header): str(values[index]).strip() if index < len(values) else ""
            for index, header in enumerate(headers)
        }
        normalized = {
            field: str(values[index]).strip() if index < len(values) else "" for index, field in mapped.items()
        }
        scope_code = normalized.get("scope_code", "")
        nature = normalized.get("scope_nature", "").upper()
        unit = _unit(normalized.get("unit", ""))
        scope_type = normalized.get("scope_type") or str(config.get("default_scope_type", "WORK"))
        for field in ("scope_code", "name", "scope_nature", "quantity", "unit"):
            if not normalized.get(field):
                errors.append(
                    _finding("MISSING_REQUIRED_VALUE", "Required Scope cell is empty.", row=row_number, field=field)
                )
        if scope_code in code_rows:
            errors.append(
                _finding(
                    "DUPLICATE_SCOPE_CODE",
                    "Scope code occurs twice in this candidate.",
                    row=row_number,
                    first_row=code_rows[scope_code],
                    scope_code=scope_code,
                )
            )
        code_rows[scope_code] = row_number
        if scope_code in existing:
            warnings.append(
                _finding(
                    "EXISTING_SCOPE_CODE",
                    "Existing Scope code requires an explicit revision modification; this import does not overwrite it.",
                    row=row_number,
                    scope_code=scope_code,
                )
            )
        if nature not in natures:
            errors.append(
                _finding(
                    "INVALID_SCOPE_NATURE",
                    "Scope Nature is not governed by the applicable profile.",
                    row=row_number,
                    value=nature,
                )
            )
        if unit not in units:
            errors.append(
                _finding(
                    "INVALID_UNIT",
                    "Source unit is not allowed; no silent conversion is applied.",
                    row=row_number,
                    value=unit,
                )
            )
        if scope_type not in scope_types:
            errors.append(
                _finding(
                    "INVALID_SCOPE_TYPE",
                    "Scope Type is not governed by the applicable profile.",
                    row=row_number,
                    value=scope_type,
                )
            )
        quantity = None
        try:
            amount = Decimal(normalized.get("quantity", ""))
            if not amount.is_finite() or amount < 0 or not math.isfinite(float(amount)):
                raise InvalidOperation
            quantity = float(amount)
        except (InvalidOperation, ValueError, OverflowError):
            errors.append(
                _finding(
                    "INVALID_QUANTITY",
                    "Quantity must be an unambiguous finite nonnegative decimal.",
                    row=row_number,
                    value=normalized.get("quantity"),
                )
            )
        row_id = normalized.get("source_row_id") or f"{worksheet}!{row_number}"
        if row_id in row_ids:
            errors.append(
                _finding(
                    "DUPLICATE_SOURCE_ROW",
                    "Source-row identifier is repeated.",
                    row=row_number,
                    first_row=row_ids[row_id],
                    source_row_id=row_id,
                )
            )
        row_ids[row_id] = row_number
        fingerprint = _fingerprint(raw)
        if fingerprint in fingerprints:
            errors.append(
                _finding(
                    "DUPLICATE_SOURCE_ROW",
                    "Source row content is repeated.",
                    row=row_number,
                    first_row=fingerprints[fingerprint],
                )
            )
        fingerprints[fingerprint] = row_number
        result["rows"].append(
            {
                **normalized,
                "scope_code": scope_code,
                "scope_type": scope_type,
                "scope_nature": nature,
                "quantity": quantity,
                "source_quantity": quantity,
                "current_quantity": quantity,
                "unit": unit,
                "source_type": "EXCEL",
                "source_reference": normalized.get("source_reference")
                or f"{result['source_file_name']}!{worksheet}!{row_number}",
                "source_revision": result["source_hash"],
                "measurement_method": normalized.get("measurement_method") or "SOURCE_DECLARED",
                "lineage": {
                    "source_hash": result["source_hash"],
                    "source_file_name": result["source_file_name"],
                    "worksheet": worksheet,
                    "row_number": row_number,
                    "source_row_id": row_id,
                    "row_hash": fingerprint,
                },
                "raw_data": raw,
                "future_mappings": {key: normalized[key] for key in FUTURE_FIELDS if normalized.get(key)},
                "future_mappings_active": False,
            }
        )
    if not result["rows"]:
        errors.append(_finding("EMPTY_SCOPE_CANDIDATE", "Workbook contains no Scope rows."))
    parents = {row["scope_code"]: row.get("parent_scope_code", "") for row in result["rows"]}
    for row in result["rows"]:
        parent = row.get("parent_scope_code", "")
        if parent and parent not in parents and parent not in existing:
            errors.append(
                _finding(
                    "MISSING_PARENT",
                    "Parent code is absent from this candidate and the existing project Scope.",
                    scope_code=row["scope_code"],
                    parent_scope_code=parent,
                )
            )
        seen: set[str] = set()
        current = row["scope_code"]
        while current in parents and parents[current]:
            if current in seen:
                errors.append(
                    _finding("SCOPE_HIERARCHY_CYCLE", "Scope hierarchy contains a cycle.", scope_code=row["scope_code"])
                )
                break
            seen.add(current)
            current = parents[current]
    return {**result, "validation": _validation(errors, warnings), "row_count": len(result["rows"])}
