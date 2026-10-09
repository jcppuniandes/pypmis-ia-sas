from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import utc_now
from app.domain.models import BimModel

IFC_DIRECT_BROWSER_LIMIT_BYTES = 25 * 1024 * 1024
IFC_BACKEND_CACHE_REQUIRED_BYTES = 100 * 1024 * 1024
IFC_PROPERTY_SCAN_LIMIT_BYTES = 25 * 1024 * 1024
IFC_ENTITY_LABELS = {
    "IFCBEAM": "IfcBeam",
    "IFCBUILDING": "IfcBuilding",
    "IFCBUILDINGELEMENTPROXY": "IfcBuildingElementProxy",
    "IFCBUILDINGSTOREY": "IfcBuildingStorey",
    "IFCCOLUMN": "IfcColumn",
    "IFCCURTAINWALL": "IfcCurtainWall",
    "IFCDOOR": "IfcDoor",
    "IFCELEMENTQUANTITY": "IfcElementQuantity",
    "IFCFLOWSEGMENT": "IfcFlowSegment",
    "IFCFOOTING": "IfcFooting",
    "IFCMEMBER": "IfcMember",
    "IFCPLATE": "IfcPlate",
    "IFCPROPERTYSET": "IfcPropertySet",
    "IFCPROPERTYSINGLEVALUE": "IfcPropertySingleValue",
    "IFCROOF": "IfcRoof",
    "IFCSITE": "IfcSite",
    "IFCSLAB": "IfcSlab",
    "IFCSPACE": "IfcSpace",
    "IFCSTAIR": "IfcStair",
    "IFCWALL": "IfcWall",
    "IFCWALLSTANDARDCASE": "IfcWallStandardCase",
    "IFCWINDOW": "IfcWindow",
}


class BimModelService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_ifc_model(
        self,
        tenant_id: int,
        project_id: int,
        user_id: int,
        filename: str,
        content: bytes,
    ) -> BimModel:
        if not content:
            raise HTTPException(status_code=400, detail="IFC model file is empty")
        if not filename.lower().endswith(".ifc"):
            raise HTTPException(status_code=400, detail="Only IFC model files can be registered for BIM coordination")

        metadata = _ifc_metadata(content)
        source_sha256 = hashlib.sha256(content).hexdigest()
        model_identity = {
            "project_name": metadata["project_name"],
            "site_name": metadata["site_name"],
            "building_name": metadata["building_name"],
            "viewer_engine": "web-ifc",
            "source": "ifc",
            "upload_size_mb": round(len(content) / (1024 * 1024), 3),
        }
        if metadata["georeferencing"]:
            model_identity["georeferencing"] = metadata["georeferencing"]

        model = BimModel(
            tenant_id=tenant_id,
            project_id=project_id,
            source_file_name=Path(filename).name or "model.ifc",
            source_type="ifc",
            source_sha256=source_sha256,
            source_size_bytes=len(content),
            status="uploaded",
            schema=metadata["schema"],
            units=metadata["units"],
            element_count=int(metadata["element_count"]),
            storey_count=int(metadata["storey_count"]),
            model_identity=model_identity,
            created_by_user_id=user_id,
        )
        self.db.add(model)
        self.db.flush()
        model.revision_id = f"IFC-M{model.id}-{source_sha256[:12]}"
        model_identity["source_sha256"] = source_sha256
        model_identity["revision_id"] = model.revision_id
        model.model_identity = model_identity
        path = self._persist_source(model, content)
        model.source_storage_path = str(path.relative_to(self._storage_root()))
        artifact_path = self._persist_viewer_manifest(model, content, metadata)
        model.viewer_artifact_path = str(artifact_path.relative_to(self._storage_root()))
        self.db.flush()
        return model

    def viewer_manifest(self, tenant_id: int, project_id: int, model_id: int) -> dict[str, Any]:
        model = self._get_model(tenant_id, project_id, model_id)
        artifact_path = self.viewer_artifact_path(model)
        if artifact_path:
            try:
                return json.loads(artifact_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                artifact_path.unlink(missing_ok=True)

        source_path = self.source_path(model)
        if source_path is None:
            raise HTTPException(status_code=404, detail="Stored IFC model source file not found")
        content = source_path.read_bytes()
        metadata = _ifc_metadata(content)
        artifact_path = self._persist_viewer_manifest(model, content, metadata)
        model.viewer_artifact_path = str(artifact_path.relative_to(self._storage_root()))
        self.db.flush()
        return json.loads(artifact_path.read_text(encoding="utf-8"))

    def element_properties(
        self,
        tenant_id: int,
        project_id: int,
        model_id: int,
        element_key: str,
    ) -> dict[str, Any]:
        model = self._get_model(tenant_id, project_id, model_id)
        source_path = self.source_path(model)
        if source_path is None:
            raise HTTPException(status_code=404, detail="Stored IFC model source file not found")
        content = source_path.read_bytes()
        return _ifc_element_properties(content, model, element_key)

    def prepare_geometry_cache(self, tenant_id: int, project_id: int, model_id: int) -> dict[str, Any]:
        settings = get_settings()
        command_template = settings.bim_geometry_converter_command.strip()
        if not command_template:
            raise HTTPException(status_code=409, detail="BIM geometry converter is not configured on this server")

        model = self._get_model(tenant_id, project_id, model_id)
        source_path = self.source_path(model)
        if source_path is None:
            raise HTTPException(status_code=404, detail="Stored IFC model source file not found")

        content = source_path.read_bytes()
        source_sha256 = hashlib.sha256(content).hexdigest()
        output_path = self._geometry_cache_storage_path(model)
        pending_path = output_path.with_suffix(".pending.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pending_path.unlink(missing_ok=True)

        _run_geometry_converter(
            command_template,
            source_path,
            pending_path,
            model,
            settings.bim_geometry_converter_timeout_seconds,
        )
        artifact = _validate_geometry_cache_artifact(pending_path)
        products = artifact["products"]
        stats = artifact["stats"]
        summary = {
            "status": "ready",
            "model_id": model.id,
            "project_id": model.project_id,
            "source_sha256": source_sha256,
            "revision_id": f"IFC-M{model.id}-{source_sha256[:12]}-GEOM",
            "engine": artifact["engine"],
            "storage_path": str(output_path.relative_to(self._storage_root())),
            "product_count": len(products),
            "mesh_count": stats["mesh_count"],
            "triangle_count": stats["triangle_count"],
            "generated_at": utc_now().isoformat(),
        }
        normalized_artifact = {
            "version": 1,
            "model_id": model.id,
            "project_id": model.project_id,
            "source_file_name": model.source_file_name,
            "source_sha256": source_sha256,
            "revision_id": summary["revision_id"],
            "engine": artifact["engine"],
            "schema": model.schema,
            "units": model.units,
            "generated_at": summary["generated_at"],
            "stats": {
                "product_count": len(products),
                "mesh_count": stats["mesh_count"],
                "triangle_count": stats["triangle_count"],
            },
            "products": products,
        }
        output_path.write_text(json.dumps(normalized_artifact, indent=2, sort_keys=True), encoding="utf-8")
        pending_path.unlink(missing_ok=True)

        identity = dict(model.model_identity or {})
        identity["geometry_cache"] = summary
        model.model_identity = identity
        metadata = _ifc_metadata(content)
        artifact_path = self._persist_viewer_manifest(model, content, metadata)
        model.viewer_artifact_path = str(artifact_path.relative_to(self._storage_root()))
        self.db.flush()
        return summary

    def geometry_cache(self, tenant_id: int, project_id: int, model_id: int) -> Path:
        model = self._get_model(tenant_id, project_id, model_id)
        path = self.geometry_cache_path(model)
        if path is None:
            raise HTTPException(status_code=404, detail="BIM geometry cache artifact not found")
        return path

    def delete_model(self, tenant_id: int, project_id: int, model_id: int) -> None:
        model = self._get_model(tenant_id, project_id, model_id, not_found_detail="BIM model not found")
        for path in (self.source_path(model), self.viewer_artifact_path(model), self.geometry_cache_path(model)):
            if path and path.exists():
                path.unlink()
        self.db.delete(model)
        self.db.flush()

    def ensure_revision_identity(self, model: BimModel) -> bool:
        if model.source_sha256 and model.revision_id and not model.revision_id.endswith("-LEGACY"):
            return False
        path = self.source_path(model)
        if path is None:
            return False
        source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        model.source_sha256 = source_sha256
        model.revision_id = f"IFC-M{model.id}-{source_sha256[:12]}"
        identity = dict(model.model_identity or {})
        identity["source_sha256"] = source_sha256
        identity["revision_id"] = model.revision_id
        model.model_identity = identity
        model.updated_at = utc_now()
        self.db.flush()
        return True

    def _get_model(
        self,
        tenant_id: int,
        project_id: int,
        model_id: int,
        not_found_detail: str = "BIM model not found",
    ) -> BimModel:
        model = self.db.scalar(
            select(BimModel).where(
                BimModel.tenant_id == tenant_id,
                BimModel.project_id == project_id,
                BimModel.id == model_id,
            )
        )
        if not model:
            raise HTTPException(status_code=404, detail=not_found_detail)
        return model

    @classmethod
    def source_path(cls, model: BimModel) -> Path | None:
        return cls._stored_path(model.source_storage_path)

    @classmethod
    def viewer_artifact_path(cls, model: BimModel) -> Path | None:
        return cls._stored_path(model.viewer_artifact_path)

    @classmethod
    def geometry_cache_path(cls, model: BimModel) -> Path | None:
        identity = model.model_identity if isinstance(model.model_identity, dict) else {}
        cache = identity.get("geometry_cache") if isinstance(identity.get("geometry_cache"), dict) else {}
        return cls._stored_path(str(cache.get("storage_path", "")))

    @classmethod
    def _stored_path(cls, relative_storage_path: str) -> Path | None:
        if not relative_storage_path:
            return None
        root = cls._storage_root()
        path = (root / relative_storage_path).resolve()
        if not _is_relative_to(path, root) or not path.exists():
            return None
        return path

    def _persist_source(self, model: BimModel, content: bytes) -> Path:
        root = self._storage_root()
        path = (
            root
            / "bim-models"
            / f"tenant-{model.tenant_id}"
            / f"project-{model.project_id}"
            / f"model-{model.id}"
            / _safe_storage_filename(model.source_file_name)
        ).resolve()
        if not _is_relative_to(path, root):
            raise HTTPException(status_code=400, detail="Invalid BIM model storage path")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _persist_viewer_manifest(self, model: BimModel, content: bytes, metadata: dict[str, object]) -> Path:
        root = self._storage_root()
        path = (
            root
            / "bim-models"
            / f"tenant-{model.tenant_id}"
            / f"project-{model.project_id}"
            / f"model-{model.id}"
            / "viewer_manifest.json"
        ).resolve()
        if not _is_relative_to(path, root):
            raise HTTPException(status_code=400, detail="Invalid BIM model artifact path")
        manifest = _ifc_viewer_manifest(content, model, metadata)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _geometry_cache_storage_path(self, model: BimModel) -> Path:
        root = self._storage_root()
        path = (
            root
            / "bim-models"
            / f"tenant-{model.tenant_id}"
            / f"project-{model.project_id}"
            / f"model-{model.id}"
            / "geometry_cache.json"
        ).resolve()
        if not _is_relative_to(path, root):
            raise HTTPException(status_code=400, detail="Invalid BIM geometry cache path")
        return path

    @staticmethod
    def _storage_root() -> Path:
        return Path(get_settings().document_storage_path).resolve()


def _ifc_metadata(content: bytes) -> dict[str, object]:
    text = content[: min(len(content), 2_000_000)].decode("utf-8", errors="ignore")
    schema = _match_first(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", text)
    project_name = _match_ifc_name("IFCPROJECT", text)
    site_name = _match_ifc_name("IFCSITE", text)
    building_name = _match_ifc_name("IFCBUILDING", text)
    unit_name = _ifc_length_unit(text)
    georeferencing = _ifc_georeferencing(text)
    element_count = len(re.findall(r"#\d+\s*=\s*IFC[A-Z0-9]*\(", text, flags=re.IGNORECASE))
    storey_count = len(re.findall(r"#\d+\s*=\s*IFCBUILDINGSTOREY\(", text, flags=re.IGNORECASE))
    return {
        "building_name": building_name,
        "element_count": element_count,
        "georeferencing": georeferencing,
        "project_name": project_name,
        "schema": schema,
        "site_name": site_name,
        "storey_count": storey_count,
        "units": unit_name,
    }


def _ifc_viewer_manifest(content: bytes, model: BimModel, metadata: dict[str, object]) -> dict[str, Any]:
    text = _decode_ifc_for_index(content)
    entities = _parse_ifc_entities(text)
    products = _ifc_product_records(entities)
    class_counts: dict[str, int] = {}
    for product in products:
        ifc_class = str(product["ifc_class"])
        class_counts[ifc_class] = class_counts.get(ifc_class, 0) + 1

    source_size = len(content)
    strategy = _viewer_geometry_strategy(source_size)
    warnings: list[str] = []
    if source_size > IFC_PROPERTY_SCAN_LIMIT_BYTES:
        warnings.append("Property index is partial because the IFC is larger than the synchronous scan limit.")
    if source_size > IFC_BACKEND_CACHE_REQUIRED_BYTES:
        warnings.append("Backend geometry cache is required for commercial use with this file size.")
    source_sha256 = hashlib.sha256(content).hexdigest()
    geometry_cache = _model_geometry_cache(model)
    cache_ready = geometry_cache.get("status") == "ready" and geometry_cache.get("source_sha256") == source_sha256

    return {
        "model_id": model.id,
        "project_id": model.project_id,
        "source_file_name": model.source_file_name,
        "source_size_bytes": source_size,
        "source_sha256": source_sha256,
        "revision_id": f"IFC-M{model.id}-{source_sha256[:12]}",
        "engine": "web-ifc/three",
        "cache_status": "geometry_cache_ready" if cache_ready else "metadata_manifest_ready",
        "geometry_strategy": "backend_cache" if cache_ready else strategy,
        "geometry_cache": geometry_cache,
        "schema": metadata.get("schema", ""),
        "units": metadata.get("units", ""),
        "project_name": metadata.get("project_name", ""),
        "site_name": metadata.get("site_name", ""),
        "building_name": metadata.get("building_name", ""),
        "georeferencing": metadata.get("georeferencing", {}),
        "product_count": len(products),
        "storey_count": metadata.get("storey_count", 0),
        "class_summary": [
            {"ifc_class": ifc_class, "count": count}
            for ifc_class, count in sorted(class_counts.items(), key=lambda item: (-item[1], item[0]))[:40]
        ],
        "property_index": {
            "scan_status": "partial" if source_size > IFC_PROPERTY_SCAN_LIMIT_BYTES else "complete",
            "scan_limit_bytes": IFC_PROPERTY_SCAN_LIMIT_BYTES,
            "indexed_products": len(products),
            "property_sets": sum(1 for entity, _ in entities.values() if entity.upper() == "IFCPROPERTYSET"),
            "quantity_sets": sum(1 for entity, _ in entities.values() if entity.upper() == "IFCELEMENTQUANTITY"),
            "type_relations": sum(1 for entity, _ in entities.values() if entity.upper() == "IFCRELDEFINESBYTYPE"),
        },
        "limits": {
            "direct_browser_bytes": IFC_DIRECT_BROWSER_LIMIT_BYTES,
            "backend_cache_required_bytes": IFC_BACKEND_CACHE_REQUIRED_BYTES,
        },
        "warnings": warnings,
    }


def _model_geometry_cache(model: BimModel) -> dict[str, Any]:
    identity = model.model_identity if isinstance(model.model_identity, dict) else {}
    cache = identity.get("geometry_cache") if isinstance(identity.get("geometry_cache"), dict) else {}
    return dict(cache)


def _run_geometry_converter(
    command_template: str,
    source_path: Path,
    output_path: Path,
    model: BimModel,
    timeout_seconds: int,
) -> None:
    rendered_command = command_template.format(
        source=str(source_path),
        output=str(output_path),
        model_id=model.id,
        project_id=model.project_id,
    )
    # POSIX splitting eats Windows path backslashes (C:\a\b -> C:ab), so the
    # converter subprocess never finds its script when running on Windows.
    args = shlex.split(rendered_command, posix=os.name != "nt")
    if not args:
        raise HTTPException(status_code=409, detail="BIM geometry converter command is empty")
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            check=False,
            text=True,
            timeout=max(timeout_seconds, 1),
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=409, detail=f"BIM geometry converter executable was not found: {args[0]}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="BIM geometry converter timed out") from exc
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "converter returned a non-zero exit code").strip()
        raise HTTPException(status_code=502, detail=f"BIM geometry converter failed: {details[:400]}")
    if not output_path.exists():
        raise HTTPException(status_code=502, detail="BIM geometry converter did not create the expected artifact")


def _validate_geometry_cache_artifact(path: Path) -> dict[str, Any]:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="BIM geometry cache artifact is not valid JSON") from exc
    products = artifact.get("products")
    if not isinstance(products, list):
        raise HTTPException(status_code=422, detail="BIM geometry cache artifact must include a products list")

    mesh_count = 0
    triangle_count = 0
    for index, product in enumerate(products):
        if not isinstance(product, dict):
            raise HTTPException(status_code=422, detail=f"BIM geometry product {index} is not an object")
        mesh = product.get("mesh")
        if not isinstance(mesh, dict):
            continue
        vertices = mesh.get("vertices")
        indices = mesh.get("indices")
        if not isinstance(vertices, list) or not isinstance(indices, list):
            raise HTTPException(status_code=422, detail=f"BIM geometry product {index} has invalid mesh arrays")
        if len(vertices) % 3 != 0 or len(indices) % 3 != 0:
            raise HTTPException(status_code=422, detail=f"BIM geometry product {index} has incomplete mesh coordinates")
        if not all(isinstance(value, int | float) for value in vertices):
            raise HTTPException(status_code=422, detail=f"BIM geometry product {index} has non-numeric vertices")
        if not all(isinstance(value, int) and value >= 0 for value in indices):
            raise HTTPException(status_code=422, detail=f"BIM geometry product {index} has invalid triangle indices")
        mesh_count += 1
        triangle_count += len(indices) // 3

    return {
        "engine": str(artifact.get("engine") or "external_ifc_converter"),
        "products": products,
        "stats": {"mesh_count": mesh_count, "triangle_count": triangle_count},
    }


def _ifc_element_properties(content: bytes, model: BimModel, element_key: str) -> dict[str, Any]:
    text = _decode_ifc_for_index(content)
    entities = _parse_ifc_entities(text)
    product = _find_ifc_product(entities, element_key)
    base_response: dict[str, Any] = {
        "model_id": model.id,
        "lookup_key": element_key,
        "scan_status": "partial" if len(content) > IFC_PROPERTY_SCAN_LIMIT_BYTES else "complete",
        "scan_limit_bytes": IFC_PROPERTY_SCAN_LIMIT_BYTES,
    }
    if not product:
        return {
            **base_response,
            "found": False,
            "step_id": "",
            "global_id": "",
            "ifc_class": "",
            "name": "",
            "type_name": "",
            "predefined_type": "",
            "property_sets": [],
            "quantities": [],
            "materials": [],
            "classifications": [],
        }

    type_ref, type_details = _ifc_type_for_product(entities, str(product["step_id"]))
    property_sets, quantities = _ifc_property_sets_for_product(entities, str(product["step_id"]), type_ref)
    return {
        **base_response,
        "found": True,
        "step_id": product["step_id"],
        "global_id": product["global_id"],
        "ifc_class": product["ifc_class"],
        "name": product["name"],
        "type_name": type_details.get("type_name") or product["type_name"],
        "predefined_type": type_details.get("predefined_type") or product["predefined_type"],
        "property_sets": property_sets,
        "quantities": quantities,
        "materials": _ifc_materials_for_product(entities, str(product["step_id"])),
        "classifications": _ifc_classifications_for_product(entities, str(product["step_id"])),
    }


def _viewer_geometry_strategy(source_size_bytes: int) -> str:
    if source_size_bytes > IFC_BACKEND_CACHE_REQUIRED_BYTES:
        return "backend_cache_required"
    if source_size_bytes > IFC_DIRECT_BROWSER_LIMIT_BYTES:
        return "browser_limited_cache_recommended"
    return "direct_browser"


def _decode_ifc_for_index(content: bytes) -> str:
    return content[: min(len(content), IFC_PROPERTY_SCAN_LIMIT_BYTES)].decode("utf-8", errors="ignore")


def _parse_ifc_entities(text: str) -> dict[str, tuple[str, list[str]]]:
    entities: dict[str, tuple[str, list[str]]] = {}
    for match in re.finditer(r"(#\d+)\s*=\s*(IFC[A-Z0-9_]+)\s*\((.*?)\);", text, flags=re.IGNORECASE | re.DOTALL):
        entities[match.group(1).upper()] = (match.group(2).upper(), _split_ifc_args(match.group(3)))
    return entities


def _ifc_product_records(entities: dict[str, tuple[str, list[str]]]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for ref, (entity, args) in entities.items():
        if not _is_ifc_product_entity(entity, args):
            continue
        records.append(
            {
                "step_id": ref,
                "global_id": _clean_ifc_value(args[0]),
                "ifc_class": _format_ifc_class(entity),
                "name": _clean_ifc_value(args[2]) if len(args) > 2 else "",
                "type_name": _clean_ifc_value(args[4]) if len(args) > 4 else "",
                "predefined_type": _first_ifc_enum(args),
            }
        )
    return records


def _is_ifc_product_entity(entity: str, args: list[str]) -> bool:
    if len(args) < 3 or not _clean_ifc_value(args[0]):
        return False
    excluded_prefixes = (
        "IFCACTOR",
        "IFCAPPLICATION",
        "IFCAXIS",
        "IFCCARTESIAN",
        "IFCCLASSIFICATION",
        "IFCCONNECTION",
        "IFCCOLOUR",
        "IFCCONTEXT",
        "IFCCURVE",
        "IFCDERIVED",
        "IFCDIMENSION",
        "IFCDIRECTION",
        "IFCDOCUMENT",
        "IFCGEOMETRIC",
        "IFCLOCALPLACEMENT",
        "IFCMATERIAL",
        "IFCMEASURE",
        "IFCOWNERHISTORY",
        "IFCPERSON",
        "IFCPRESENTATION",
        "IFCPROJECT",
        "IFCPROPERTY",
        "IFCQUANTITY",
        "IFCREL",
        "IFCREPRESENTATION",
        "IFCSIUNIT",
        "IFCSHAPE",
        "IFCSTYLE",
        "IFCUNIT",
    )
    return not entity.startswith(excluded_prefixes)


def _find_ifc_product(entities: dict[str, tuple[str, list[str]]], element_key: str) -> dict[str, str] | None:
    normalized = element_key.strip()
    if not normalized:
        return None
    lookup = normalized.upper()
    if lookup.isdigit():
        lookup = f"#{lookup}"
    records = _ifc_product_records(entities)
    for product in records:
        if lookup in {product["step_id"].upper(), product["global_id"].upper()}:
            return product
    return None


def _ifc_type_for_product(
    entities: dict[str, tuple[str, list[str]]],
    product_ref: str,
) -> tuple[str, dict[str, str]]:
    for entity, args in entities.values():
        if entity.upper() != "IFCRELDEFINESBYTYPE" or len(args) < 6:
            continue
        if product_ref.upper() not in _ifc_refs(args[4]):
            continue
        type_ref = _normalize_ifc_ref(args[5])
        type_entity, type_args = entities.get(type_ref, ("", []))
        return type_ref, {
            "ifc_type_entity": _format_ifc_class(type_entity),
            "type_name": _clean_ifc_value(type_args[2]) if len(type_args) > 2 else "",
            "predefined_type": _first_ifc_enum(type_args),
        }
    return "", {}


def _ifc_property_sets_for_product(
    entities: dict[str, tuple[str, list[str]]],
    product_ref: str,
    type_ref: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    property_set_refs: list[str] = []
    for entity, args in entities.values():
        if entity.upper() != "IFCRELDEFINESBYPROPERTIES" or len(args) < 6:
            continue
        if product_ref.upper() in _ifc_refs(args[4]):
            property_set_refs.append(_normalize_ifc_ref(args[5]))

    if type_ref and type_ref in entities:
        _, type_args = entities[type_ref]
        for arg in type_args:
            for ref in _ifc_refs(arg):
                ref_entity = entities.get(ref, ("", []))[0].upper()
                if ref_entity in {"IFCPROPERTYSET", "IFCELEMENTQUANTITY"}:
                    property_set_refs.append(ref)

    property_sets: list[dict[str, Any]] = []
    quantities: list[dict[str, Any]] = []
    for pset_ref in _unique_refs(property_set_refs):
        entity, args = entities.get(pset_ref, ("", []))
        if entity.upper() == "IFCPROPERTYSET":
            property_sets.append(_ifc_property_set_payload(pset_ref, args, entities))
        elif entity.upper() == "IFCELEMENTQUANTITY":
            quantities.extend(_ifc_quantity_set_payload(pset_ref, args, entities))
    return property_sets, quantities


def _ifc_property_set_payload(ref: str, args: list[str], entities: dict[str, tuple[str, list[str]]]) -> dict[str, Any]:
    properties: list[dict[str, str]] = []
    for prop_ref in _ifc_refs(args[4] if len(args) > 4 else ""):
        entity, prop_args = entities.get(prop_ref, ("", []))
        if not entity.upper().startswith("IFCPROPERTY"):
            continue
        properties.append(
            {
                "name": _clean_ifc_value(prop_args[0]) if prop_args else entity,
                "value": _ifc_property_value(entity, prop_args),
                "type": _format_ifc_class(entity),
            }
        )
    return {
        "step_id": ref,
        "name": _clean_ifc_value(args[2]) if len(args) > 2 else "Property Set",
        "properties": properties,
    }


def _ifc_quantity_set_payload(
    ref: str,
    args: list[str],
    entities: dict[str, tuple[str, list[str]]],
) -> list[dict[str, Any]]:
    quantity_set = _clean_ifc_value(args[2]) if len(args) > 2 else "Quantity Set"
    quantities: list[dict[str, Any]] = []
    quantity_refs = _ifc_refs(next((arg for arg in reversed(args) if _ifc_refs(arg)), ""))
    for quantity_ref in quantity_refs:
        entity, quantity_args = entities.get(quantity_ref, ("", []))
        if not entity.upper().startswith("IFCQUANTITY"):
            continue
        quantities.append(
            {
                "step_id": quantity_ref,
                "set_name": quantity_set,
                "name": _clean_ifc_value(quantity_args[0]) if quantity_args else _format_ifc_class(entity),
                "value": _parse_ifc_float(quantity_args[3]) if len(quantity_args) > 3 else None,
                "unit": _quantity_unit_for_entity(entity),
                "source": "IFCELEMENTQUANTITY",
            }
        )
    return quantities


def _ifc_materials_for_product(entities: dict[str, tuple[str, list[str]]], product_ref: str) -> list[str]:
    materials: list[str] = []
    for entity, args in entities.values():
        if entity.upper() != "IFCRELASSOCIATESMATERIAL" or len(args) < 6:
            continue
        if product_ref.upper() not in _ifc_refs(args[4]):
            continue
        materials.extend(_ifc_material_names(entities, _normalize_ifc_ref(args[5]), set()))
    return sorted(set(materials))


def _ifc_material_names(
    entities: dict[str, tuple[str, list[str]]],
    ref: str,
    visited: set[str],
) -> list[str]:
    if ref in visited:
        return []
    visited.add(ref)
    entity, args = entities.get(ref, ("", []))
    if entity.upper() == "IFCMATERIAL":
        return [_clean_ifc_value(args[0]) if args else ref]
    names: list[str] = []
    for arg in args:
        for child_ref in _ifc_refs(arg):
            names.extend(_ifc_material_names(entities, child_ref, visited))
    return names


def _ifc_classifications_for_product(
    entities: dict[str, tuple[str, list[str]]], product_ref: str
) -> list[dict[str, str]]:
    classifications: list[dict[str, str]] = []
    for entity, args in entities.values():
        if entity.upper() != "IFCRELASSOCIATESCLASSIFICATION" or len(args) < 6:
            continue
        if product_ref.upper() not in _ifc_refs(args[4]):
            continue
        class_ref = _normalize_ifc_ref(args[5])
        class_entity, class_args = entities.get(class_ref, ("", []))
        classifications.append(
            {
                "step_id": class_ref,
                "type": _format_ifc_class(class_entity),
                "code": _clean_ifc_value(class_args[1]) if len(class_args) > 1 else "",
                "name": _clean_ifc_value(class_args[2]) if len(class_args) > 2 else "",
            }
        )
    return classifications


def _ifc_property_value(entity: str, args: list[str]) -> str:
    if entity.upper() == "IFCPROPERTYSINGLEVALUE" and len(args) > 2:
        return _clean_ifc_value(args[2])
    if len(args) > 2:
        return _clean_ifc_value(args[2])
    return ""


def _clean_ifc_value(value: str) -> str:
    raw = value.strip()
    if not raw or raw == "$":
        return ""
    wrapped = re.match(r"IFC[A-Z0-9_]+\s*\((.*)\)$", raw, flags=re.IGNORECASE | re.DOTALL)
    if wrapped:
        parts = _split_ifc_args(wrapped.group(1))
        return _clean_ifc_value(parts[0]) if parts else ""
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1].strip()
    if raw.startswith(".") and raw.endswith("."):
        return raw.strip(".")
    return raw


def _first_ifc_enum(args: list[str]) -> str:
    for arg in reversed(args):
        value = _clean_ifc_value(arg)
        if value and re.fullmatch(r"[A-Z][A-Z0-9_]*", value):
            return value
    return ""


def _quantity_unit_for_entity(entity: str) -> str:
    normalized = entity.upper()
    if "AREA" in normalized:
        return "m2"
    if "VOLUME" in normalized:
        return "m3"
    if "LENGTH" in normalized or "WIDTH" in normalized or "HEIGHT" in normalized:
        return "m"
    if "COUNT" in normalized:
        return "ea"
    if "WEIGHT" in normalized:
        return "kg"
    if "TIME" in normalized:
        return "h"
    return ""


def _ifc_refs(value: str) -> list[str]:
    return [ref.upper() for ref in re.findall(r"#\d+", value)]


def _normalize_ifc_ref(value: str) -> str:
    refs = _ifc_refs(value)
    return refs[0] if refs else value.strip().upper()


def _unique_refs(refs: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            ordered.append(ref)
    return ordered


def _format_ifc_class(entity_name: str) -> str:
    if not entity_name:
        return ""
    normalized = entity_name.upper()
    if normalized in IFC_ENTITY_LABELS:
        return IFC_ENTITY_LABELS[normalized]
    if normalized.startswith("IFC"):
        return "Ifc" + normalized[3:].title().replace("_", "")
    return normalized.title()


def _ifc_length_unit(text: str) -> str:
    match = re.search(
        r"IFCSIUNIT\s*\(\s*\*?\s*,\s*\.LENGTHUNIT\.\s*,\s*(?:\.([A-Z]+)\.|\$)\s*,\s*\.([A-Z]+)\.",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    prefix = (match.group(1) or "").upper()
    unit_name = (match.group(2) or "").upper()
    if unit_name not in {"METRE", "METER"}:
        return ""
    if prefix == "MILLI":
        return "millimeters"
    if prefix == "CENTI":
        return "centimeters"
    return "meters"


def _ifc_georeferencing(text: str) -> dict[str, object]:
    georef = _ifc_site_georeference(text)
    projected_crs = _ifc_projected_crs(text)
    map_conversion = _ifc_map_conversion(text)
    if projected_crs:
        georef["projected_crs"] = projected_crs
    if map_conversion:
        georef["map_conversion"] = map_conversion
    return georef


def _ifc_site_georeference(text: str) -> dict[str, object]:
    args = _ifc_entity_args("IFCSITE", text)
    if len(args) < 12:
        return {}
    latitude = _parse_ifc_angle(args[9])
    longitude = _parse_ifc_angle(args[10])
    elevation = _parse_ifc_float(args[11])
    if latitude is None and longitude is None and elevation is None:
        return {}
    georef: dict[str, object] = {"source": "IFCSITE"}
    if latitude is not None:
        georef["latitude_decimal"] = latitude
    if longitude is not None:
        georef["longitude_decimal"] = longitude
    if elevation is not None:
        georef["elevation"] = elevation
    return georef


def _ifc_projected_crs(text: str) -> str:
    args = _ifc_entity_args("IFCPROJECTEDCRS", text)
    if not args:
        return ""
    return _strip_ifc_string(args[0])


def _ifc_map_conversion(text: str) -> dict[str, float]:
    args = _ifc_entity_args("IFCMAPCONVERSION", text)
    if len(args) < 8:
        return {}
    fields = {
        "eastings": _parse_ifc_float(args[2]),
        "northings": _parse_ifc_float(args[3]),
        "orthogonal_height": _parse_ifc_float(args[4]),
        "x_axis_abscissa": _parse_ifc_float(args[5]),
        "x_axis_ordinate": _parse_ifc_float(args[6]),
        "scale": _parse_ifc_float(args[7]),
    }
    return {key: value for key, value in fields.items() if value is not None}


def _ifc_entity_args(entity_name: str, text: str) -> list[str]:
    match = re.search(rf"{entity_name}\s*\((.*?)\);", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    return _split_ifc_args(match.group(1))


def _split_ifc_args(body: str) -> list[str]:
    args: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False
    for char in body:
        if char == "'":
            in_string = not in_string
        elif not in_string:
            if char == "(":
                depth += 1
            elif char == ")":
                depth = max(0, depth - 1)
            elif char == "," and depth == 0:
                args.append("".join(current).strip())
                current = []
                continue
        current.append(char)
    if current or body.endswith(","):
        args.append("".join(current).strip())
    return args


def _parse_ifc_angle(value: str) -> float | None:
    raw = value.strip()
    if not raw or raw == "$":
        return None
    parts = [_parse_ifc_float(part) for part in raw.strip("()").split(",")]
    numeric_parts = [part for part in parts if part is not None]
    if not numeric_parts:
        return None
    sign = -1 if numeric_parts[0] < 0 else 1
    degrees = abs(numeric_parts[0])
    minutes = abs(numeric_parts[1]) if len(numeric_parts) > 1 else 0
    seconds = abs(numeric_parts[2]) if len(numeric_parts) > 2 else 0
    millionth_seconds = abs(numeric_parts[3]) if len(numeric_parts) > 3 else 0
    return sign * (degrees + minutes / 60 + seconds / 3600 + millionth_seconds / 3_600_000_000)


def _parse_ifc_float(value: str) -> float | None:
    raw = value.strip()
    if not raw or raw == "$":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _strip_ifc_string(value: str) -> str:
    raw = value.strip()
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1].strip()
    return "" if raw == "$" else raw


def _match_ifc_name(entity_name: str, text: str) -> str:
    pattern = rf"{entity_name}\s*\(\s*'[^']*'\s*,\s*[^,]*,\s*'([^']*)'"
    return _match_first(pattern, text)


def _match_first(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


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
