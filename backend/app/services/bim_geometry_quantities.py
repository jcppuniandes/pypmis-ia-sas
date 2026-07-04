from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import BimModel, QuantityTakeoffLine, QuantityTakeoffRun
from app.services.bim_models import BimModelService
from app.services.bim_quantity_rule_catalog import project_quantity_rule_catalog
from app.services.bim_quantity_rules import (
    evaluate_effective_quantity_rule,
    evaluate_quantity_rule,
    normalize_ifc_class,
)

AREA_CLASSES = {
    "IFCCURTAINWALL",
    "IFCPLATE",
    "IFCROOF",
    "IFCSLAB",
    "IFCSPACE",
    "IFCWALL",
    "IFCWALLSTANDARDCASE",
}
VOLUME_CLASSES = {"IFCBEAM", "IFCCOLUMN", "IFCFOOTING", "IFCPILE", "IFCSTAIR"}
LENGTH_CLASSES = {"IFCFLOWSEGMENT", "IFCMEMBER", "IFCPIPESEGMENT", "IFCRAILING"}


class BimGeometryQuantityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def process(
        self,
        tenant_id: int,
        project_id: int,
        run_id: int,
        model_id: int,
        *,
        apply: bool = False,
        line_ids: list[int] | None = None,
        replace_valid: bool = False,
        approved_by: str = "",
        approved_by_user_id: int | None = None,
    ) -> dict[str, Any]:
        run = self.db.scalar(
            select(QuantityTakeoffRun).where(
                QuantityTakeoffRun.tenant_id == tenant_id,
                QuantityTakeoffRun.project_id == project_id,
                QuantityTakeoffRun.id == run_id,
            )
        )
        if not run:
            raise HTTPException(status_code=404, detail="Quantity takeoff run not found")
        model = self.db.scalar(
            select(BimModel).where(
                BimModel.tenant_id == tenant_id,
                BimModel.project_id == project_id,
                BimModel.id == model_id,
            )
        )
        if not model:
            raise HTTPException(status_code=404, detail="BIM model not found")
        if run.bim_model_id != model.id:
            raise HTTPException(
                status_code=409,
                detail="Link the quantity takeoff to this BIM model revision before calculating geometry.",
            )
        if run.bim_revision_id and model.revision_id and run.bim_revision_id != model.revision_id:
            raise HTTPException(status_code=409, detail="The linked BIM revision no longer matches the selected model.")

        artifact_path = BimModelService.geometry_cache_path(model)
        if artifact_path is None:
            BimModelService(self.db).prepare_geometry_cache(tenant_id, project_id, model_id)
            artifact_path = BimModelService.geometry_cache_path(model)
        if artifact_path is None:
            raise HTTPException(status_code=409, detail="BIM geometry cache is not available")
        artifact = _load_artifact(artifact_path)
        product_index = _product_index(artifact)

        query = select(QuantityTakeoffLine).where(
            QuantityTakeoffLine.tenant_id == tenant_id,
            QuantityTakeoffLine.project_id == project_id,
            QuantityTakeoffLine.run_id == run_id,
        )
        selected_ids = sorted({int(line_id) for line_id in line_ids or [] if int(line_id) > 0})
        if selected_ids:
            query = query.where(QuantityTakeoffLine.id.in_(selected_ids))
        lines = list(self.db.scalars(query.order_by(QuantityTakeoffLine.id)).all())
        if selected_ids and len(lines) != len(selected_ids):
            raise HTTPException(status_code=404, detail="One or more quantity takeoff lines were not found")

        units = str(artifact.get("units") or model.units or "meters")
        quantity_catalog = project_quantity_rule_catalog(self.db, tenant_id, project_id)
        results: list[dict[str, Any]] = []
        applied_lines: list[QuantityTakeoffLine] = []
        approved_at = utc_now().isoformat()

        for line in lines:
            product = _match_product(product_index, line)
            current_rule = evaluate_effective_quantity_rule(line, quantity_catalog)
            current_quantity, current_unit = _effective_quantity(line)
            controlled = (line.raw_data or {}).get("controlled_measurement")
            approved_quantity = (
                float(controlled.get("quantity") or 0)
                if isinstance(controlled, dict) and controlled.get("status") == "approved"
                else None
            )
            approved_unit = (
                str(controlled.get("unit") or "")
                if isinstance(controlled, dict) and controlled.get("status") == "approved"
                else ""
            )
            base = {
                "line_id": line.id,
                "element_guid": line.element_guid,
                "ifc_class": line.ifc_class,
                "element_name": _element_name(line),
                "current_quantity": current_quantity,
                "current_unit": current_unit,
                "source_quantity": float(line.quantity or 0),
                "source_unit": line.unit,
                "approved_quantity": approved_quantity,
                "approved_unit": approved_unit,
                "geometry_quantity": 0.0,
                "geometry_unit": "",
                "measurement_rule": "",
                "difference": None,
                "difference_percent": None,
                "confidence": "Baja",
                "reason": "",
            }
            if not product:
                results.append(
                    {**base, "status": "unmatched", "reason": "No se encontro una malla IFC para la referencia."}
                )
                continue

            quantities = _mesh_quantities(product.get("mesh"), units)
            estimate = _primary_estimate(line.ifc_class or str(product.get("ifc_class") or ""), quantities)
            if not estimate or estimate["quantity"] <= 0:
                results.append(
                    {
                        **base,
                        "status": "invalid",
                        "reason": "La malla no produjo una cantidad geometrica positiva y coherente.",
                    }
                )
                continue

            difference = None
            difference_percent = None
            if _unit_key(line.unit) == _unit_key(estimate["unit"]):
                difference = round(estimate["quantity"] - float(line.quantity or 0), 6)
                if line.quantity:
                    difference_percent = round(difference / float(line.quantity) * 100, 3)

            should_replace = current_rule.get("status") != "valid" or replace_valid
            status = "ready" if should_replace else "compare"
            reason = (
                "Medicion dimensional calculada desde la malla IFC."
                if should_replace
                else "La cantidad actual es valida; la geometria se muestra solo para comparacion."
            )
            result = {
                **base,
                "status": status,
                "geometry_quantity": estimate["quantity"],
                "geometry_unit": estimate["unit"],
                "measurement_rule": estimate["measurement_rule"],
                "difference": difference,
                "difference_percent": difference_percent,
                "confidence": estimate["confidence"],
                "reason": reason,
            }
            if apply and should_replace:
                self._apply_measurement(
                    line,
                    estimate,
                    quantity_catalog,
                    artifact,
                    approved_at,
                    approved_by,
                    approved_by_user_id,
                    model_id,
                )
                applied_lines.append(line)
                result["status"] = "applied"
                result["reason"] = "Medicion geometrica aprobada y versionada."
                result["approved_quantity"] = estimate["quantity"]
                result["approved_unit"] = estimate["unit"]
            results.append(result)

        if applied_lines:
            run.version = int(run.version or 1) + 1
            run.updated_at = utc_now()
            self.db.flush()

        return {
            "model_id": model_id,
            "run_id": run_id,
            "revision_id": str(artifact.get("revision_id") or ""),
            "total_count": len(results),
            "matched_count": sum(1 for result in results if result["status"] not in {"unmatched"}),
            "ready_count": sum(1 for result in results if result["status"] == "ready"),
            "compare_count": sum(1 for result in results if result["status"] == "compare"),
            "applied_count": sum(1 for result in results if result["status"] == "applied"),
            "unmatched_count": sum(1 for result in results if result["status"] == "unmatched"),
            "invalid_count": sum(1 for result in results if result["status"] == "invalid"),
            "results": results,
        }

    @staticmethod
    def _apply_measurement(
        line: QuantityTakeoffLine,
        estimate: dict[str, Any],
        quantity_catalog: dict,
        artifact: dict[str, Any],
        approved_at: str,
        approved_by: str,
        approved_by_user_id: int | None,
        model_id: int,
    ) -> None:
        raw_data = dict(line.raw_data or {})
        previous = raw_data.get("controlled_measurement")
        history = list(raw_data.get("controlled_measurement_history") or [])
        next_version = int(previous.get("version", 0)) + 1 if isinstance(previous, dict) else 1
        if isinstance(previous, dict):
            history.insert(0, previous)
        measurement = {
            "approved_at": approved_at,
            "approved_by": approved_by,
            "approved_by_user_id": approved_by_user_id,
            "element_guid": line.element_guid,
            "geometry_revision_id": str(artifact.get("revision_id") or ""),
            "line_id": line.id,
            "measurement_rule": estimate["measurement_rule"],
            "model_id": model_id,
            "note": "Medicion geometrica masiva calculada desde la cache IFC backend.",
            "quantity": estimate["quantity"],
            "source": "Backend IFC geometry cache",
            "source_quantity": line.quantity,
            "source_unit": line.unit,
            "status": "approved",
            "unit": estimate["unit"],
            "version": next_version,
        }
        raw_data["controlled_measurement"] = measurement
        raw_data["controlled_measurement_history"] = history[:20]
        raw_data["quantity_rule"] = evaluate_quantity_rule(
            {
                "category": line.category,
                "ifc_class": line.ifc_class,
                "measurement_rule": estimate["measurement_rule"],
                "quantity": estimate["quantity"],
                "raw_data": raw_data,
                "unit": estimate["unit"],
                "validation_notes": "",
            },
            quantity_catalog,
        )
        line.raw_data = raw_data
        line.measurement_rule = estimate["measurement_rule"]
        notes = [
            note.strip()
            for note in str(line.validation_notes or "").split(";")
            if note.strip() and not note.strip().startswith("Controlled measurement approved")
        ]
        notes.append(f"Controlled measurement approved v{next_version} from Backend IFC geometry cache.")
        line.validation_notes = "; ".join(notes)
        line.updated_at = utc_now()


def _load_artifact(path: Path) -> dict[str, Any]:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="BIM geometry cache artifact is not readable") from exc
    if not isinstance(artifact.get("products"), list):
        raise HTTPException(status_code=422, detail="BIM geometry cache has no product list")
    return artifact


def _product_index(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for product in artifact.get("products", []):
        if not isinstance(product, dict):
            continue
        global_id = str(product.get("global_id") or "").strip()
        express_id = _safe_int(product.get("express_id"))
        for key in (global_id, f"#{express_id}" if express_id else "", str(express_id) if express_id else ""):
            if key:
                index[key.upper()] = product
    return index


def _match_product(index: dict[str, dict[str, Any]], line: QuantityTakeoffLine) -> dict[str, Any] | None:
    for key in (line.element_guid, line.element_id, line.source_row_id.split(":", 1)[0]):
        normalized = str(key or "").strip().upper()
        if normalized in index:
            return index[normalized]
        if normalized.isdigit() and f"#{normalized}" in index:
            return index[f"#{normalized}"]
    return None


def _mesh_quantities(mesh: Any, units: str) -> dict[str, float]:
    if not isinstance(mesh, dict):
        return {}
    vertices = mesh.get("vertices")
    indices = mesh.get("indices")
    if not isinstance(vertices, list) or not isinstance(indices, list) or len(vertices) < 9 or len(indices) < 3:
        return {}
    points = [
        (float(vertices[index]), float(vertices[index + 1]), float(vertices[index + 2]))
        for index in range(0, len(vertices) - 2, 3)
    ]
    if not points:
        return {}
    raw_max_dimension = max(
        max(point[axis] for point in points) - min(point[axis] for point in points) for axis in range(3)
    )
    scale = _coordinate_scale(units, raw_max_dimension)
    points = [(x * scale, y * scale, z * scale) for x, y, z in points]
    minimum = tuple(min(point[axis] for point in points) for axis in range(3))
    maximum = tuple(max(point[axis] for point in points) for axis in range(3))
    origin = tuple((minimum[axis] + maximum[axis]) / 2 for axis in range(3))
    normal_areas: dict[tuple[int, int, int], float] = defaultdict(float)
    signed_volume = 0.0

    for offset in range(0, len(indices) - 2, 3):
        try:
            a = _subtract(points[int(indices[offset])], origin)
            b = _subtract(points[int(indices[offset + 1])], origin)
            c = _subtract(points[int(indices[offset + 2])], origin)
        except (IndexError, TypeError, ValueError):
            continue
        cross = _cross(_subtract(b, a), _subtract(c, a))
        cross_length = _length(cross)
        if cross_length <= 0:
            continue
        area = cross_length / 2
        normal = tuple(abs(component / cross_length) for component in cross)
        normal_key = tuple(int(round(component * 20)) for component in normal)
        normal_areas[normal_key] += area
        signed_volume += _dot(a, _cross(b, c)) / 6

    dimensions = [maximum[axis] - minimum[axis] for axis in range(3)]
    bbox_volume = dimensions[0] * dimensions[1] * dimensions[2]
    volume = abs(signed_volume)
    closed_mesh = volume > max(bbox_volume * 1e-8, 1e-10)
    dominant_face_area = max(normal_areas.values(), default=0.0)
    if closed_mesh:
        dominant_face_area /= 2
    return {
        "area": _round_quantity(dominant_face_area),
        "length": _round_quantity(max(dimensions)),
        "volume": _round_quantity(volume),
    }


def _primary_estimate(ifc_class: str, quantities: dict[str, float]) -> dict[str, Any] | None:
    normalized = normalize_ifc_class(ifc_class)
    if normalized in AREA_CLASSES:
        key, unit, rule = "area", "m2", "GeometryMeshArea"
    elif normalized in VOLUME_CLASSES:
        key, unit, rule = "volume", "m3", "GeometryMeshVolume"
    elif normalized in LENGTH_CLASSES:
        key, unit, rule = "length", "m", "GeometryMeshLength"
    else:
        key, unit, rule = "length", "m", "GeometryMeshLength"
    quantity = float(quantities.get(key) or 0)
    if not math.isfinite(quantity) or quantity <= 0:
        return None
    return {
        "confidence": "Media",
        "measurement_rule": rule,
        "quantity": quantity,
        "unit": unit,
    }


def _effective_quantity(line: QuantityTakeoffLine) -> tuple[float, str]:
    controlled = (line.raw_data or {}).get("controlled_measurement")
    if isinstance(controlled, dict) and controlled.get("status") == "approved":
        return float(controlled.get("quantity") or line.quantity or 0), str(controlled.get("unit") or line.unit or "")
    return float(line.quantity or 0), line.unit


def _element_name(line: QuantityTakeoffLine) -> str:
    return " / ".join(value for value in (line.category, line.family, line.type_name) if value) or line.ifc_class


def _coordinate_scale(units: str, max_dimension: float) -> float:
    normalized = "".join(character for character in str(units or "").lower() if character.isalnum())
    if normalized in {"mm", "milli", "millimeter", "millimeters", "millimetre", "millimetres"}:
        return 1.0 if max_dimension < 100 else 0.001
    if normalized in {"cm", "centi", "centimeter", "centimeters", "centimetre", "centimetres"}:
        return 1.0 if max_dimension < 100 else 0.01
    return 1.0


def _subtract(left: tuple[float, float, float], right: tuple[float, float, float]) -> tuple[float, float, float]:
    return left[0] - right[0], left[1] - right[1], left[2] - right[2]


def _cross(left: tuple[float, float, float], right: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _dot(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _length(value: tuple[float, float, float]) -> float:
    return math.sqrt(_dot(value, value))


def _round_quantity(value: float) -> float:
    return round(value, 3)


def _unit_key(unit: str) -> str:
    normalized = str(unit or "").strip().lower().replace(" ", "")
    return {"und": "ea", "unidad": "ea", "u": "ea", "un": "ea"}.get(normalized, normalized)


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
