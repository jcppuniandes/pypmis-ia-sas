from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field
from io import BytesIO, StringIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import utc_now
from app.domain.models import (
    WBS,
    BimModel,
    CostBreakdownStructure,
    FundingSource,
    QuantityTakeoffLine,
    QuantityTakeoffRun,
    WorkPackage,
)
from app.services.bim_quantity_rule_catalog import project_quantity_rule_catalog
from app.services.bim_quantity_rules import (
    evaluate_effective_quantity_rule,
    evaluate_quantity_rule,
    normalize_ifc_class,
    summarize_quantity_rules,
)


def _normalize_header(value: str) -> str:
    return re.sub(r"[\s_\-]+", " ", value.strip().lower()).strip()


HEADER_ALIASES = {
    "source_row_id": {"source_row_id", "source row", "row", "line", "linea"},
    "element_id": {"element_id", "element id", "ifc_id", "ifc id", "step_id", "step id"},
    "element_guid": {"element_guid", "element guid", "guid", "global_id", "global id", "ifc_guid", "ifc guid"},
    "ifc_class": {"ifc_class", "ifc class", "ifctype", "ifc type", "entity", "clase ifc"},
    "category": {"category", "categoria", "categoría"},
    "family": {"family", "familia"},
    "type_name": {"type", "type_name", "tipo"},
    "instance_name": {"instance", "instance_name", "ejemplar", "instancia", "name", "nombre"},
    "project_name": {"project", "project_name", "ifc project", "proyecto"},
    "site_name": {"site", "site_name", "ifc site", "sitio"},
    "building_name": {"building", "building_name", "edificio"},
    "storey": {"storey", "level", "nivel", "piso", "ifc building storey"},
    "system_name": {"system", "system_name", "sistema"},
    "zone_name": {"zone", "zone_name", "zona"},
    "assembly_name": {"assembly", "assembly_name", "ensamble", "conjunto"},
    "classification_system": {"classification_system", "classification system", "sistema clasificacion"},
    "classification_code": {
        "classification_code",
        "classification code",
        "codigo clasificacion",
        "código clasificación",
    },
    "quantity": {"quantity", "qty", "cantidad"},
    "unit": {"unit", "uom", "unidad"},
    "measurement_rule": {"measurement_rule", "measurement rule", "regla medicion", "regla medición", "quantity name"},
    "wbs_code": {"wbs_code", "wbs code", "wbs"},
    "cbs_code": {"cbs_code", "cbs code", "cbs"},
    "fbs_code": {"fbs_code", "fbs code", "fbs", "fund_code", "fund code"},
    "package_code": {"package_code", "package code", "package", "paquete", "cwp", "iwp"},
}

ALIAS_TO_FIELD = {
    _normalize_header(alias): field_name for field_name, aliases in HEADER_ALIASES.items() for alias in aliases
}

IFC_PRODUCT_CLASSES = {
    "IFCBEAM",
    "IFCBUILDINGELEMENTPROXY",
    "IFCCOLUMN",
    "IFCCOVERING",
    "IFCCURTAINWALL",
    "IFCDOOR",
    "IFCELEMENTASSEMBLY",
    "IFCFLOWFITTING",
    "IFCFLOWSEGMENT",
    "IFCFLOWTERMINAL",
    "IFCFOOTING",
    "IFCFURNISHINGELEMENT",
    "IFCMEMBER",
    "IFCPILE",
    "IFCPIPEFITTING",
    "IFCPIPESEGMENT",
    "IFCPLATE",
    "IFCRAILING",
    "IFCRAMP",
    "IFCROOF",
    "IFCSLAB",
    "IFCSPACE",
    "IFCSTAIR",
    "IFCWALL",
    "IFCWALLSTANDARDCASE",
    "IFCWINDOW",
}

IFC_TYPE_CLASSES = {
    "IFCBEAMTYPE",
    "IFCBUILDINGELEMENTPROXYTYPE",
    "IFCCOLUMNTYPE",
    "IFCCOVERINGTYPE",
    "IFCCURTAINWALLTYPE",
    "IFCDOORSTYLE",
    "IFCDOORTYPE",
    "IFCELEMENTASSEMBLYTYPE",
    "IFCFLOWFITTINGTYPE",
    "IFCFLOWSEGMENTTYPE",
    "IFCFLOWTERMINALTYPE",
    "IFCFOOTINGTYPE",
    "IFCFURNISHINGELEMENTTYPE",
    "IFCMEMBERTYPE",
    "IFCPILETYPE",
    "IFCPIPEFITTINGTYPE",
    "IFCPIPESEGMENTTYPE",
    "IFCPLATETYPE",
    "IFCRAILINGTYPE",
    "IFCRAMPTYPE",
    "IFCROOFTYPE",
    "IFCSLABTYPE",
    "IFCSPACETYPE",
    "IFCSTAIRTYPE",
    "IFCWALLTYPE",
    "IFCWINDOWSTYLE",
    "IFCWINDOWTYPE",
}

IFC_QUANTITY_UNITS = {
    "IFCQUANTITYAREA": "m2",
    "IFCQUANTITYCOUNT": "und",
    "IFCQUANTITYLENGTH": "m",
    "IFCQUANTITYVOLUME": "m3",
    "IFCQUANTITYWEIGHT": "kg",
}

IFC_TAKEOFF_RELATION_CLASSES = {
    "IFCBUILDING",
    "IFCBUILDINGSTOREY",
    "IFCELEMENTQUANTITY",
    "IFCPROJECT",
    "IFCRELCONTAINEDINSPATIALSTRUCTURE",
    "IFCRELDEFINESBYPROPERTIES",
    "IFCRELDEFINESBYTYPE",
    "IFCSITE",
}

IFC_TAKEOFF_ENTITY_CLASSES = (
    IFC_PRODUCT_CLASSES | IFC_TYPE_CLASSES | set(IFC_QUANTITY_UNITS) | IFC_TAKEOFF_RELATION_CLASSES
)

IFC_CLASS_DISPLAY_NAMES = {
    "IFCBUILDINGELEMENTPROXY": "IfcBuildingElementProxy",
    "IFCCURTAINWALL": "IfcCurtainWall",
    "IFCFLOWFITTING": "IfcFlowFitting",
    "IFCFLOWSEGMENT": "IfcFlowSegment",
    "IFCFLOWTERMINAL": "IfcFlowTerminal",
    "IFCFURNISHINGELEMENT": "IfcFurnishingElement",
    "IFCWALLSTANDARDCASE": "IfcWallStandardCase",
}

IFC_TAKEOFF_MAX_BYTES = 100 * 1024 * 1024
IFC_TAKEOFF_MAX_MB = IFC_TAKEOFF_MAX_BYTES // (1024 * 1024)


@dataclass
class NormalizedQuantityLine:
    source_row_id: str = ""
    element_id: str = ""
    element_guid: str = ""
    ifc_class: str = ""
    category: str = ""
    family: str = ""
    type_name: str = ""
    instance_name: str = ""
    project_name: str = ""
    site_name: str = ""
    building_name: str = ""
    storey: str = ""
    system_name: str = ""
    zone_name: str = ""
    assembly_name: str = ""
    classification_system: str = ""
    classification_code: str = ""
    quantity: float = 0
    unit: str = ""
    measurement_rule: str = ""
    wbs_code: str = ""
    cbs_code: str = ""
    fbs_code: str = ""
    package_code: str = ""
    validation_notes: list[str] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)


class QuantityTakeoffService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def import_file(
        self,
        tenant_id: int,
        project_id: int,
        filename: str,
        content: bytes,
        bim_model_id: int | None = None,
    ) -> QuantityTakeoffRun:
        if not content:
            raise HTTPException(status_code=400, detail="Quantity source file is empty")
        source_type = self._source_type(filename)
        if source_type in {"csv", "xlsx", "xls"}:
            parsed_lines = self._parse_spreadsheet(source_type, content)
        elif source_type == "ifc":
            self._validate_ifc_takeoff_size(content)
            parsed_lines = self._parse_ifc(content)
        else:
            raise HTTPException(status_code=400, detail="Unsupported quantity source file")
        if not parsed_lines:
            raise HTTPException(status_code=400, detail="No quantity rows were found")
        source_sha256 = hashlib.sha256(content).hexdigest()
        linked_model = self._linked_model(
            tenant_id,
            project_id,
            source_type,
            source_sha256,
            bim_model_id,
        )

        wbs_by_code = {
            item.code: item
            for item in self.db.scalars(
                select(WBS).where(WBS.tenant_id == tenant_id, WBS.project_id == project_id)
            ).all()
        }
        cbs_by_code = {
            item.code: item
            for item in self.db.scalars(
                select(CostBreakdownStructure).where(
                    CostBreakdownStructure.tenant_id == tenant_id,
                    CostBreakdownStructure.project_id == project_id,
                )
            ).all()
        }
        fbs_by_code = {
            item.code: item
            for item in self.db.scalars(
                select(FundingSource).where(
                    FundingSource.tenant_id == tenant_id,
                    FundingSource.project_id == project_id,
                )
            ).all()
        }
        work_package_by_code = {
            item.code: item
            for item in self.db.scalars(
                select(WorkPackage).where(
                    WorkPackage.tenant_id == tenant_id,
                    WorkPackage.project_id == project_id,
                )
            ).all()
        }
        wbs_codes = set(wbs_by_code)
        cbs_codes = set(cbs_by_code)
        fbs_codes = set(fbs_by_code)

        run = QuantityTakeoffRun(
            tenant_id=tenant_id,
            project_id=project_id,
            bim_model_id=linked_model.id if linked_model else None,
            source_file_name=filename,
            source_type=source_type,
            source_sha256=source_sha256,
            bim_revision_id=linked_model.revision_id if linked_model else "",
            model_linked_at=utc_now() if linked_model else None,
            status="needs_mapping",
            row_count=len(parsed_lines),
            total_quantity=round(sum(line.quantity for line in parsed_lines), 6),
        )
        self.db.add(run)
        self.db.flush()
        if source_type == "ifc":
            self._persist_ifc_source(tenant_id, project_id, run.id, filename, content)

        quantity_rule_catalog = project_quantity_rule_catalog(self.db, tenant_id, project_id)
        quantity_rule_summary = summarize_quantity_rules(parsed_lines, quantity_rule_catalog)
        mapped_count = 0
        for line in parsed_lines:
            quantity_rule = evaluate_quantity_rule(line, quantity_rule_catalog)
            mapping_status, notes = self._mapping_status(line, wbs_codes, cbs_codes, fbs_codes, quantity_rule)
            if mapping_status == "mapped":
                mapped_count += 1
            raw_data = dict(line.raw_data or {})
            raw_data["quantity_rule"] = quantity_rule
            raw_data["quantity_calculation"] = _quantity_calculation_for(line, quantity_rule)
            wbs = wbs_by_code.get(line.wbs_code)
            cbs = cbs_by_code.get(line.cbs_code)
            fbs = fbs_by_code.get(line.fbs_code)
            work_package = work_package_by_code.get(line.package_code)
            raw_data["control_code_refs"] = {
                "cbs_id": cbs.id if cbs else None,
                "fbs_id": fbs.id if fbs else None,
                "wbs_id": wbs.id if wbs else None,
                "work_package_id": work_package.id if work_package else None,
            }
            db_line = QuantityTakeoffLine(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run.id,
                source_row_id=line.source_row_id,
                element_id=line.element_id,
                element_guid=line.element_guid,
                ifc_class=line.ifc_class,
                category=line.category,
                family=line.family,
                type_name=line.type_name,
                instance_name=line.instance_name,
                project_name=line.project_name,
                site_name=line.site_name,
                building_name=line.building_name,
                storey=line.storey,
                system_name=line.system_name,
                zone_name=line.zone_name,
                assembly_name=line.assembly_name,
                classification_system=line.classification_system,
                classification_code=line.classification_code,
                quantity=line.quantity,
                unit=line.unit,
                measurement_rule=line.measurement_rule,
                wbs_code=line.wbs_code,
                cbs_code=line.cbs_code,
                fbs_code=line.fbs_code,
                package_code=line.package_code,
                wbs_id=wbs.id if wbs else None,
                cbs_id=cbs.id if cbs else None,
                fbs_id=fbs.id if fbs else None,
                work_package_id=work_package.id if work_package else None,
                mapping_status=mapping_status,
                validation_notes="; ".join(notes),
                raw_data=raw_data,
            )
            self.db.add(db_line)

        run.mapped_line_count = mapped_count
        run.unmapped_line_count = len(parsed_lines) - mapped_count
        run.status = "mapped" if run.unmapped_line_count == 0 else "needs_mapping"
        run.validation_summary = (
            f"{run.row_count} quantity line(s): {run.mapped_line_count} mapped, "
            f"{run.unmapped_line_count} need mapping. "
            f"Quantity rules: {quantity_rule_summary['valid']} valid, "
            f"{quantity_rule_summary['review']} review, {quantity_rule_summary['blocked']} blocked."
        )
        self.db.flush()
        return run

    def link_model(
        self,
        tenant_id: int,
        project_id: int,
        run_id: int,
        model_id: int,
        expected_version: int | None = None,
    ) -> QuantityTakeoffRun:
        run = self.db.scalar(
            select(QuantityTakeoffRun).where(
                QuantityTakeoffRun.tenant_id == tenant_id,
                QuantityTakeoffRun.project_id == project_id,
                QuantityTakeoffRun.id == run_id,
            )
        )
        if not run:
            raise HTTPException(status_code=404, detail="Quantity takeoff run not found")
        if expected_version is not None and run.version != expected_version:
            raise HTTPException(status_code=409, detail="Quantity takeoff run was updated by another user")
        model = self._linked_model(
            tenant_id,
            project_id,
            run.source_type,
            run.source_sha256,
            model_id,
            source_file_name=run.source_file_name,
        )
        if not model:
            raise HTTPException(status_code=404, detail="BIM model not found")
        run.bim_model_id = model.id
        run.bim_revision_id = model.revision_id
        run.model_linked_at = utc_now()
        run.version = int(run.version or 1) + 1
        run.updated_at = utc_now()
        self.db.flush()
        return run

    def _linked_model(
        self,
        tenant_id: int,
        project_id: int,
        source_type: str,
        source_sha256: str,
        model_id: int | None,
        *,
        source_file_name: str = "",
    ) -> BimModel | None:
        query = select(BimModel).where(
            BimModel.tenant_id == tenant_id,
            BimModel.project_id == project_id,
        )
        if model_id:
            query = query.where(BimModel.id == model_id)
        elif source_type == "ifc":
            query = query.where(BimModel.source_sha256 == source_sha256)
        else:
            return None
        model = self.db.scalar(query.order_by(BimModel.created_at.desc(), BimModel.id.desc()))
        if not model:
            if model_id:
                raise HTTPException(status_code=404, detail="BIM model not found")
            return None
        if source_type == "ifc":
            if source_sha256 and model.source_sha256 and source_sha256 != model.source_sha256:
                raise HTTPException(
                    status_code=409,
                    detail="The selected BIM revision does not match the IFC quantity source hash.",
                )
            if not source_sha256 and Path(source_file_name).name.casefold() != model.source_file_name.casefold():
                raise HTTPException(
                    status_code=409,
                    detail="Legacy IFC takeoff can only be linked to a model with the same source file name.",
                )
        return model

    def recalculate_rules(self, tenant_id: int, project_id: int, run_id: int) -> dict:
        run = self.db.scalar(
            select(QuantityTakeoffRun).where(
                QuantityTakeoffRun.tenant_id == tenant_id,
                QuantityTakeoffRun.project_id == project_id,
                QuantityTakeoffRun.id == run_id,
            )
        )
        if not run:
            raise HTTPException(status_code=404, detail="Quantity takeoff run not found")

        lines = list(
            self.db.scalars(
                select(QuantityTakeoffLine)
                .where(
                    QuantityTakeoffLine.tenant_id == tenant_id,
                    QuantityTakeoffLine.project_id == project_id,
                    QuantityTakeoffLine.run_id == run_id,
                )
                .order_by(QuantityTakeoffLine.id)
            ).all()
        )
        catalog = project_quantity_rule_catalog(self.db, tenant_id, project_id)
        counts = {"blocked": 0, "review": 0, "valid": 0}
        impacts: list[dict] = []
        affected_classes: set[str] = set()
        now = utc_now()

        for line in lines:
            raw_data = dict(line.raw_data or {})
            previous_rule = raw_data.get("quantity_rule", {})
            previous = previous_rule if isinstance(previous_rule, dict) else {}
            current = evaluate_effective_quantity_rule(line, catalog)
            status = str(current.get("status", "review"))
            if status in counts:
                counts[status] += 1

            notes = _replace_quantity_rule_note(line.validation_notes, current)
            line.validation_notes = "; ".join(notes)
            line.mapping_status = "mapped" if not notes else "needs_mapping"
            line.updated_at = now
            changed = _quantity_rule_changed(previous, current)
            if changed:
                affected_classes.add(line.ifc_class or line.category or "Clase IFC pendiente")
                impacts.append(
                    {
                        "line_id": line.id,
                        "element_guid": line.element_guid,
                        "ifc_class": line.ifc_class,
                        "previous_status": str(previous.get("status", "")),
                        "new_status": status,
                        "previous_measure": str(previous.get("expected_measure", "")),
                        "new_measure": str(current.get("expected_measure", "")),
                        "previous_units": list(previous.get("expected_units", [])),
                        "new_units": list(current.get("expected_units", [])),
                        "mapping_status": line.mapping_status,
                    }
                )
            raw_data["quantity_rule"] = current
            raw_data["quantity_rule_recalculation"] = {
                "changed": changed,
                "current": current,
                "previous": previous,
                "recalculated_at": now.isoformat(),
            }
            line.raw_data = raw_data

        run.mapped_line_count = sum(1 for line in lines if line.mapping_status == "mapped")
        run.unmapped_line_count = len(lines) - run.mapped_line_count
        run.status = "mapped" if run.unmapped_line_count == 0 else "needs_mapping"
        run.version = int(run.version or 1) + 1
        run.updated_at = now
        gate = "blocked" if counts["blocked"] else "review" if counts["review"] else "ready"
        run.validation_summary = (
            f"{run.row_count} quantity line(s): {run.mapped_line_count} mapped, "
            f"{run.unmapped_line_count} need mapping. "
            f"Quantity rules recalculated: {counts['valid']} valid, "
            f"{counts['review']} review, {counts['blocked']} blocked."
        )
        self.db.flush()
        return {
            "project_id": project_id,
            "run_id": run_id,
            "total_lines": len(lines),
            "changed_line_count": len(impacts),
            "valid_count": counts["valid"],
            "review_count": counts["review"],
            "blocked_count": counts["blocked"],
            "cost_rollup_gate": gate,
            "affected_classes": sorted(affected_classes),
            "impacts": impacts[:50],
        }

    def ensure_source_identity(self, run: QuantityTakeoffRun) -> bool:
        if run.source_sha256 or run.source_type != "ifc":
            return False
        path = self.ifc_source_path(run)
        if path is None:
            return False
        run.source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        run.updated_at = utc_now()
        self.db.flush()
        return True

    @classmethod
    def ifc_source_path(cls, run: QuantityTakeoffRun) -> Path | None:
        if run.source_type != "ifc":
            return None
        root = Path(get_settings().document_storage_path).resolve()
        relative_path = cls._ifc_source_relative_path(run.tenant_id, run.project_id, run.id, run.source_file_name)
        path = (root / relative_path).resolve()
        if not _is_relative_to(path, root) or not path.exists():
            return None
        return path

    def _source_type(self, filename: str) -> str:
        extension = Path(filename or "").suffix.lower().lstrip(".")
        if extension == "ifc":
            return "ifc"
        if extension in {"csv", "xlsx", "xls"}:
            return extension
        return ""

    def _validate_ifc_takeoff_size(self, content: bytes) -> None:
        if len(content) <= IFC_TAKEOFF_MAX_BYTES:
            return
        raise HTTPException(
            status_code=413,
            detail=(
                f"The synchronous BIM takeoff service accepts prepared IFC quantity export files up to "
                f"{IFC_TAKEOFF_MAX_MB} MB. Upload an IFC with published Quantity Sets or an Excel/CSV takeoff; "
                "heavier coordination models belong to the async web-ifc viewer path."
            ),
        )

    def _persist_ifc_source(self, tenant_id: int, project_id: int, run_id: int, filename: str, content: bytes) -> Path:
        root = Path(get_settings().document_storage_path).resolve()
        relative_path = self._ifc_source_relative_path(tenant_id, project_id, run_id, filename)
        path = (root / relative_path).resolve()
        if not _is_relative_to(path, root):
            raise HTTPException(status_code=400, detail="Invalid IFC storage path")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    @staticmethod
    def _ifc_source_relative_path(tenant_id: int, project_id: int, run_id: int, filename: str) -> Path:
        return (
            Path("bim-ifc")
            / f"tenant-{tenant_id}"
            / f"project-{project_id}"
            / f"run-{run_id}"
            / _safe_storage_filename(filename or "model.ifc")
        )

    def _parse_spreadsheet(self, source_type: str, content: bytes) -> list[NormalizedQuantityLine]:
        rows = self._csv_rows(content) if source_type == "csv" else self._xlsx_rows(content)
        parsed: list[NormalizedQuantityLine] = []
        for row_index, row in enumerate(rows, start=1):
            normalized = self._normalize_row(row)
            if not any(normalized.values()):
                continue
            parsed.append(self._line_from_row(row_index, normalized, row))
        return parsed

    def _csv_rows(self, content: bytes) -> list[dict[str, str]]:
        text = content.decode("utf-8-sig")
        return [dict(row) for row in csv.DictReader(StringIO(text))]

    def _xlsx_rows(self, content: bytes) -> list[dict[str, str]]:
        try:
            with ZipFile(BytesIO(content)) as archive:
                shared_strings = self._xlsx_shared_strings(archive)
                sheet_name = "xl/worksheets/sheet1.xml"
                if sheet_name not in archive.namelist():
                    sheet_candidates = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/"))
                    if not sheet_candidates:
                        return []
                    sheet_name = sheet_candidates[0]
                values = self._xlsx_sheet_values(archive.read(sheet_name), shared_strings)
        except BadZipFile as exc:
            raise HTTPException(status_code=400, detail="Invalid XLSX quantity file") from exc
        if not values:
            return []
        headers = [str(value).strip() for value in values[0]]
        rows: list[dict[str, str]] = []
        for row in values[1:]:
            row_dict = {
                headers[index]: str(row[index]).strip() if index < len(row) else "" for index in range(len(headers))
            }
            if any(row_dict.values()):
                rows.append(row_dict)
        return rows

    def _xlsx_shared_strings(self, archive: ZipFile) -> list[str]:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        strings: list[str] = []
        for item in root.findall("s:si", namespace):
            strings.append("".join(text.text or "" for text in item.findall(".//s:t", namespace)))
        return strings

    def _xlsx_sheet_values(self, sheet_xml: bytes, shared_strings: list[str]) -> list[list[str]]:
        root = ET.fromstring(sheet_xml)
        namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rows: list[list[str]] = []
        for row in root.findall(".//s:row", namespace):
            values_by_column: dict[int, str] = {}
            for cell in row.findall("s:c", namespace):
                cell_ref = cell.attrib.get("r", "")
                column_index = _cell_column_index(cell_ref)
                cell_type = cell.attrib.get("t", "")
                if cell_type == "inlineStr":
                    value = "".join(text.text or "" for text in cell.findall(".//s:t", namespace))
                else:
                    value_node = cell.find("s:v", namespace)
                    value = value_node.text if value_node is not None and value_node.text is not None else ""
                    if cell_type == "s" and value:
                        value = shared_strings[int(value)] if int(value) < len(shared_strings) else ""
                values_by_column[column_index] = value
            if values_by_column:
                max_column = max(values_by_column)
                rows.append([values_by_column.get(index, "") for index in range(1, max_column + 1)])
        return rows

    def _normalize_row(self, row: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for header, value in row.items():
            field_name = ALIAS_TO_FIELD.get(_normalize_header(header or ""))
            if field_name:
                normalized[field_name] = str(value or "").strip()
        return normalized

    def _line_from_row(
        self,
        row_index: int,
        normalized: dict[str, str],
        raw_row: dict[str, str],
    ) -> NormalizedQuantityLine:
        quantity = _parse_float(normalized.get("quantity", "0"))
        notes: list[str] = []
        if "quantity" not in normalized or not str(normalized.get("quantity", "")).strip():
            notes.append("Missing quantity")
        return NormalizedQuantityLine(
            source_row_id=normalized.get("source_row_id") or str(row_index),
            element_id=normalized.get("element_id", ""),
            element_guid=normalized.get("element_guid", ""),
            ifc_class=normalized.get("ifc_class", ""),
            category=normalized.get("category", ""),
            family=normalized.get("family", ""),
            type_name=normalized.get("type_name", ""),
            instance_name=normalized.get("instance_name", ""),
            project_name=normalized.get("project_name", ""),
            site_name=normalized.get("site_name", ""),
            building_name=normalized.get("building_name", ""),
            storey=normalized.get("storey", ""),
            system_name=normalized.get("system_name", ""),
            zone_name=normalized.get("zone_name", ""),
            assembly_name=normalized.get("assembly_name", ""),
            classification_system=normalized.get("classification_system", ""),
            classification_code=normalized.get("classification_code", ""),
            quantity=quantity,
            unit=normalized.get("unit", ""),
            measurement_rule=normalized.get("measurement_rule", ""),
            wbs_code=normalized.get("wbs_code", ""),
            cbs_code=normalized.get("cbs_code", ""),
            fbs_code=normalized.get("fbs_code", ""),
            package_code=normalized.get("package_code", ""),
            validation_notes=notes,
            raw_data=dict(raw_row),
        )

    def _parse_ifc(self, content: bytes) -> list[NormalizedQuantityLine]:
        text = content.decode("utf-8", errors="ignore")
        entities = _parse_ifc_entities(text)
        project_name = _first_entity_name(entities, "IFCPROJECT")
        site_name = _first_entity_name(entities, "IFCSITE")
        building_name = _first_entity_name(entities, "IFCBUILDING")
        products: dict[str, tuple[str, list[str]]] = {
            ref: (entity_name, args)
            for ref, (entity_name, args) in entities.items()
            if entity_name in IFC_PRODUCT_CLASSES
        }
        type_details_by_ref = _ifc_type_details(entities)
        storey_by_ref = {
            ref: _clean_ifc_arg(args[2]) if len(args) > 2 else ""
            for ref, (entity_name, args) in entities.items()
            if entity_name == "IFCBUILDINGSTOREY"
        }
        element_storey: dict[str, str] = {}
        element_type_ref: dict[str, str] = {}
        quantity_sets: dict[str, list[tuple[str, float, str]]] = {}
        for ref, (entity_name, args) in entities.items():
            if entity_name in IFC_QUANTITY_UNITS:
                name = _clean_ifc_arg(args[0]) if args else entity_name
                quantity_sets[ref] = [
                    (name, _parse_float(args[3] if len(args) > 3 else "0"), IFC_QUANTITY_UNITS[entity_name])
                ]
            elif entity_name == "IFCELEMENTQUANTITY":
                refs = _arg_refs(_last_list_arg(args))
                quantities: list[tuple[str, float, str]] = []
                for quantity_ref in refs:
                    quantities.extend(quantity_sets.get(quantity_ref, []))
                quantity_sets[ref] = quantities
            elif entity_name == "IFCRELCONTAINEDINSPATIALSTRUCTURE":
                related_refs = _arg_refs(_first_list_arg(args))
                storey_ref = _last_ref_arg(args)
                storey_name = storey_by_ref.get(storey_ref, "")
                for element_ref in related_refs:
                    element_storey[element_ref] = storey_name
            elif entity_name == "IFCRELDEFINESBYTYPE":
                related_refs = _arg_refs(_first_list_arg(args))
                type_ref = _last_ref_arg(args)
                if type_ref:
                    for element_ref in related_refs:
                        element_type_ref[element_ref] = type_ref

        element_quantities: dict[str, list[tuple[str, float, str]]] = {}
        for entity_name, args in entities.values():
            if entity_name != "IFCRELDEFINESBYPROPERTIES":
                continue
            related_refs = _arg_refs(_first_list_arg(args))
            property_ref = _last_ref_arg(args)
            quantities = quantity_sets.get(property_ref, [])
            for element_ref in related_refs:
                element_quantities.setdefault(element_ref, []).extend(quantities)

        lines: list[NormalizedQuantityLine] = []
        for element_ref in sorted(products, key=lambda value: int(value.lstrip("#"))):
            entity_name, args = products[element_ref]
            type_ref = element_type_ref.get(element_ref, "")
            type_details = type_details_by_ref.get(type_ref, {})
            product_type_label = _clean_ifc_arg(args[4]) if len(args) > 4 else ""
            type_label = type_details.get("type_label", "") or product_type_label
            family, type_name = _split_family_type(type_label)
            family = type_details.get("family", "") or family
            type_name = type_details.get("type_name", "") or type_name
            predefined_type = type_details.get("predefined_type", "")
            category = _constructive_category(entity_name, type_label, predefined_type)
            published_quantities = element_quantities.get(element_ref) or []
            quantities = published_quantities or [("ElementCount", 1.0, "ea")]
            for quantity_name, quantity_value, unit in quantities:
                notes = [] if published_quantities else ["No published IFC quantity found"]
                raw_data = {
                    "ifc_entity_ref": element_ref,
                    "ifc_entity": entity_name,
                }
                if type_ref:
                    raw_data.update(
                        {
                            "ifc_type_ref": type_ref,
                            "ifc_type_entity": type_details.get("type_entity", ""),
                            "ifc_type_name": type_label,
                            "ifc_predefined_type": predefined_type,
                            "ifc_constructive_category": category,
                        }
                    )
                lines.append(
                    NormalizedQuantityLine(
                        source_row_id=f"{element_ref}:{quantity_name}",
                        element_id=element_ref,
                        element_guid=_clean_ifc_arg(args[0]) if args else "",
                        ifc_class=_format_ifc_class(entity_name),
                        category=category,
                        family=family,
                        type_name=type_name,
                        instance_name=_clean_ifc_arg(args[2]) if len(args) > 2 else "",
                        project_name=project_name,
                        site_name=site_name,
                        building_name=building_name,
                        storey=element_storey.get(element_ref, ""),
                        quantity=quantity_value,
                        unit=unit,
                        measurement_rule=quantity_name,
                        validation_notes=notes,
                        raw_data=raw_data,
                    )
                )
        return lines

    def _mapping_status(
        self,
        line: NormalizedQuantityLine,
        wbs_codes: set[str],
        cbs_codes: set[str],
        fbs_codes: set[str],
        quantity_rule: dict | None = None,
    ) -> tuple[str, list[str]]:
        notes = list(line.validation_notes)
        if quantity_rule and quantity_rule.get("status") == "blocked":
            findings = "; ".join(str(item) for item in quantity_rule.get("findings", []))
            notes.append(f"Quantity rule blocked: {findings}")
        if not line.wbs_code:
            notes.append("Missing WBS")
        elif line.wbs_code not in wbs_codes:
            notes.append(f"Unknown WBS {line.wbs_code}")
        if not line.cbs_code:
            notes.append("Missing CBS")
        elif line.cbs_code not in cbs_codes:
            notes.append(f"Unknown CBS {line.cbs_code}")
        if not line.fbs_code:
            notes.append("Missing FBS")
        elif line.fbs_code not in fbs_codes:
            notes.append(f"Unknown FBS {line.fbs_code}")
        if not line.package_code:
            notes.append("Missing package")
        if line.quantity <= 0:
            notes.append("Quantity must be greater than zero")
        return ("mapped" if not notes else "needs_mapping", notes)


def _quantity_calculation_for(line: NormalizedQuantityLine, quantity_rule: dict) -> dict[str, object]:
    source = str(quantity_rule.get("source") or _quantity_source_for(line))
    confidence = str(quantity_rule.get("confidence") or "Media")
    rule_status = str(quantity_rule.get("status") or "")
    is_fallback_count = source == "Conteo fallback"
    is_usable = rule_status != "blocked" and not is_fallback_count
    fallback = _geometry_fallback_for(line.ifc_class or line.category)
    calculation: dict[str, object] = {
        "confidence": confidence,
        "measurement_rule": line.measurement_rule,
        "method": _quantity_calculation_method(source, is_usable),
        "recommended_quantity": line.quantity if is_usable else None,
        "recommended_unit": line.unit if is_usable else "",
        "source": source,
        "source_quantity": line.quantity,
        "source_unit": line.unit,
        "status": "usable" if is_usable else "requires_controlled_measurement" if is_fallback_count else "blocked",
    }
    if fallback:
        calculation["fallback_basis"] = fallback["basis"]
        calculation["fallback_rule"] = fallback["rule"]
        calculation["fallback_unit"] = fallback["unit"]
    return calculation


def _quantity_calculation_method(source: str, is_usable: bool) -> str:
    if source == "IFC Quantity Set publicado":
        return "Published IFC Quantity Set"
    if source == "Plantilla Excel/CSV controlada" and is_usable:
        return "Controlled spreadsheet quantity"
    return "Element count fallback"


def _quantity_source_for(line: NormalizedQuantityLine) -> str:
    notes = "; ".join(line.validation_notes).lower()
    if line.measurement_rule.lower() == "elementcount" or "no published ifc quantity" in notes:
        return "Conteo fallback"
    if line.raw_data.get("ifc_entity"):
        return "IFC Quantity Set publicado"
    return "Plantilla Excel/CSV controlada"


def _geometry_fallback_for(ifc_class: str) -> dict[str, str]:
    normalized = normalize_ifc_class(ifc_class)
    area_classes = {"IFCCURTAINWALL", "IFCPLATE", "IFCROOF", "IFCSLAB", "IFCSPACE", "IFCWALL", "IFCWALLSTANDARDCASE"}
    volume_classes = {"IFCBEAM", "IFCCOLUMN", "IFCFOOTING", "IFCPILE", "IFCSTAIR"}
    length_classes = {"IFCFLOWSEGMENT", "IFCMEMBER", "IFCPIPESEGMENT", "IFCRAILING"}
    if normalized in area_classes:
        return {"basis": "two largest IFC bounding-box dimensions", "rule": "GeometryAreaBBox", "unit": "m2"}
    if normalized in volume_classes:
        return {"basis": "IFC bounding-box volume", "rule": "GeometryVolumeBBox", "unit": "m3"}
    if normalized in length_classes:
        return {"basis": "largest IFC bounding-box dimension", "rule": "GeometryLengthBBox", "unit": "m"}
    return {}


def _quantity_rule_changed(previous: dict, current: dict) -> bool:
    return any(
        previous.get(field) != current.get(field)
        for field in ("accepted_rules", "expected_measure", "expected_units", "rule_source", "status")
    )


def _replace_quantity_rule_note(validation_notes: str, quantity_rule: dict) -> list[str]:
    notes = [
        note.strip()
        for note in str(validation_notes or "").split(";")
        if note.strip() and not note.strip().startswith("Quantity rule blocked:")
    ]
    if quantity_rule.get("status") == "blocked":
        findings = "; ".join(str(item) for item in quantity_rule.get("findings", []))
        notes.append(f"Quantity rule blocked: {findings}")
    return notes


def _parse_float(value: object) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    text = text.replace("$", "").replace(" ", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return round(float(text), 6)
    except ValueError:
        return 0.0


def _cell_column_index(cell_ref: str) -> int:
    letters = "".join(char for char in cell_ref if char.isalpha()).upper()
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return index or 1


def _ifc_type_details(entities: dict[str, tuple[str, list[str]]]) -> dict[str, dict[str, str]]:
    details: dict[str, dict[str, str]] = {}
    for ref, (entity_name, args) in entities.items():
        if entity_name not in IFC_TYPE_CLASSES:
            continue
        type_label = _clean_ifc_arg(args[2]) if len(args) > 2 else ""
        if not type_label and len(args) > 8:
            type_label = _clean_ifc_arg(args[8])
        family, type_name = _split_family_type(type_label)
        details[ref] = {
            "type_entity": entity_name,
            "type_label": type_label,
            "family": family,
            "type_name": type_name,
            "predefined_type": _last_enum_arg(args),
        }
    return details


def _split_family_type(label: str) -> tuple[str, str]:
    text = " ".join((label or "").split())
    if not text:
        return "", ""
    if ":" not in text:
        return "", text
    family, type_name = text.split(":", 1)
    return family.strip(), type_name.strip()


def _last_enum_arg(args: list[str]) -> str:
    for arg in reversed(args):
        value = arg.strip()
        if re.fullmatch(r"\.[A-Z0-9_]+\.", value, flags=re.IGNORECASE):
            return value.strip(".").upper()
    return ""


def _constructive_category(entity_name: str, type_label: str, predefined_type: str) -> str:
    normalized_entity = entity_name.upper()
    normalized_type = (type_label or "").upper()
    normalized_predefined = (predefined_type or "").upper()

    if normalized_entity == "IFCMEMBER":
        if normalized_predefined == "MULLION" or "MULLION" in normalized_type:
            return "Montante de fachada"
        if any(token in normalized_type for token in ("BEAM", "VIGA", "JOIST", "PURLIN")):
            return "Viga / miembro estructural"
        return "Miembro estructural a revisar"
    if normalized_entity == "IFCPLATE":
        if normalized_predefined == "CURTAIN_PANEL" or any(
            token in normalized_type for token in ("CURTAIN", "PANEL", "GLAZED")
        ):
            return "Panel de fachada"
        return "Placa"
    if normalized_entity == "IFCSLAB":
        if normalized_predefined == "ROOF" or "ROOF" in normalized_type:
            return "Cubierta"
        if normalized_predefined in {"FLOOR", "BASESLAB", "LANDING"} or any(
            token in normalized_type for token in ("FLOOR", "SLAB", "LOSA")
        ):
            return "Losa / piso"
        return "Losa"

    labels = {
        "IFCBEAM": "Viga",
        "IFCBUILDINGELEMENTPROXY": "Elemento BIM generico",
        "IFCCOLUMN": "Columna",
        "IFCCOVERING": "Acabado / recubrimiento",
        "IFCCURTAINWALL": "Muro cortina / fachada",
        "IFCDOOR": "Puerta",
        "IFCELEMENTASSEMBLY": "Ensamble constructivo",
        "IFCFLOWFITTING": "Accesorio MEP",
        "IFCFLOWSEGMENT": "Tramo MEP",
        "IFCFLOWTERMINAL": "Terminal MEP",
        "IFCFOOTING": "Cimentacion",
        "IFCFURNISHINGELEMENT": "Mobiliario",
        "IFCPILE": "Pilote",
        "IFCPIPEFITTING": "Accesorio de tuberia",
        "IFCPIPESEGMENT": "Tuberia",
        "IFCRAILING": "Baranda",
        "IFCRAMP": "Rampa",
        "IFCROOF": "Cubierta",
        "IFCSPACE": "Espacio",
        "IFCSTAIR": "Escalera",
        "IFCWALL": "Muro",
        "IFCWALLSTANDARDCASE": "Muro",
        "IFCWINDOW": "Ventana",
    }
    return labels.get(normalized_entity, _format_ifc_class(entity_name))


def _safe_storage_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not name:
        name = "model.ifc"
    if not name.lower().endswith(".ifc"):
        name = f"{name}.ifc"
    return name[:180]


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _parse_ifc_entities(text: str) -> dict[str, tuple[str, list[str]]]:
    entities: dict[str, tuple[str, list[str]]] = {}
    entity_names = "|".join(sorted(re.escape(name) for name in IFC_TAKEOFF_ENTITY_CLASSES))
    pattern = re.compile(rf"#(\d+)\s*=\s*({entity_names})\s*\((.*?)\);", re.IGNORECASE | re.DOTALL)
    for match in pattern.finditer(text):
        ref = f"#{match.group(1)}"
        entity_name = match.group(2).upper()
        entities[ref] = (entity_name, _split_step_args(match.group(3)))
    return entities


def _split_step_args(args: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False
    index = 0
    while index < len(args):
        char = args[index]
        if char == "'":
            current.append(char)
            if index + 1 < len(args) and args[index + 1] == "'":
                current.append(args[index + 1])
                index += 2
                continue
            in_string = not in_string
        elif not in_string and char == "(":
            depth += 1
            current.append(char)
        elif not in_string and char == ")":
            depth -= 1
            current.append(char)
        elif not in_string and char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current).strip())
    return parts


def _clean_ifc_arg(value: str) -> str:
    value = value.strip()
    if value in {"", "$", "*"}:
        return ""
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    return value


def _arg_refs(value: str) -> list[str]:
    return [f"#{match}" for match in re.findall(r"#(\d+)", value or "")]


def _first_list_arg(args: list[str]) -> str:
    for arg in args:
        if arg.strip().startswith("("):
            return arg
    return ""


def _last_list_arg(args: list[str]) -> str:
    for arg in reversed(args):
        if arg.strip().startswith("("):
            return arg
    return ""


def _last_ref_arg(args: list[str]) -> str:
    for arg in reversed(args):
        refs = _arg_refs(arg)
        if refs:
            return refs[-1]
    return ""


def _first_entity_name(entities: dict[str, tuple[str, list[str]]], entity_type: str) -> str:
    for entity_name, args in entities.values():
        if entity_name == entity_type:
            return _clean_ifc_arg(args[2]) if len(args) > 2 else ""
    return ""


def _format_ifc_class(entity_name: str) -> str:
    if entity_name.upper() in IFC_CLASS_DISPLAY_NAMES:
        return IFC_CLASS_DISPLAY_NAMES[entity_name.upper()]
    suffix = entity_name.upper().removeprefix("IFC")
    return "Ifc" + "".join(part.capitalize() for part in suffix.split("_"))
