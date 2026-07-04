from __future__ import annotations

import argparse
import importlib
import json
import multiprocessing
from pathlib import Path
from typing import Any


def convert_ifc_geometry(
    source_path: Path,
    output_path: Path,
    *,
    jobs: int | None = None,
    max_products: int = 20_000,
    max_triangles: int = 3_000_000,
) -> dict[str, int]:
    ifcopenshell = importlib.import_module("ifcopenshell")
    geom = getattr(ifcopenshell, "geom", None) or importlib.import_module("ifcopenshell.geom")
    model = ifcopenshell.open(str(source_path))
    settings = geom.settings()
    _set_ifc_geometry_option(settings, "USE_WORLD_COORDS", True)
    iterator = geom.iterator(settings, model, jobs or max(multiprocessing.cpu_count() - 1, 1))

    products: list[dict[str, Any]] = []
    triangle_count = 0
    if iterator.initialize():
        while True:
            shape = iterator.get()
            product = _shape_to_product(model, shape)
            if product:
                product_triangles = len(product["mesh"]["indices"]) // 3
                if triangle_count + product_triangles > max_triangles:
                    break
                products.append(product)
                triangle_count += product_triangles
            if len(products) >= max_products or not iterator.next():
                break

    artifact = {
        "version": 1,
        "engine": "ifcopenshell-geometry",
        "stats": {
            "product_count": len(products),
            "mesh_count": len(products),
            "triangle_count": triangle_count,
        },
        "products": products,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    return {
        "mesh_count": len(products),
        "product_count": len(products),
        "triangle_count": triangle_count,
    }


def _shape_to_product(model: Any, shape: Any) -> dict[str, Any] | None:
    geometry = getattr(shape, "geometry", None)
    vertices = _numeric_list(getattr(geometry, "verts", []))
    indices = _index_list(getattr(geometry, "faces", []))
    if len(vertices) < 9 or len(indices) < 3 or len(vertices) % 3 != 0 or len(indices) % 3 != 0:
        return None

    express_id = _safe_int(getattr(shape, "id", 0))
    element = _model_by_id(model, express_id)
    return {
        "express_id": express_id,
        "global_id": _clean_text(getattr(element, "GlobalId", "") or getattr(shape, "guid", "")),
        "ifc_class": _ifc_class(element),
        "name": _clean_text(getattr(element, "Name", "")),
        "mesh": {
            "vertices": vertices,
            "indices": indices,
        },
    }


def _set_ifc_geometry_option(settings: Any, option_name: str, value: object) -> None:
    option = getattr(settings, option_name, option_name)
    try:
        settings.set(option, value)
    except Exception:
        try:
            settings.set(option_name.lower().replace("_", "-"), value)
        except Exception:
            return


def _model_by_id(model: Any, express_id: int) -> Any:
    if not express_id or not hasattr(model, "by_id"):
        return None
    try:
        return model.by_id(express_id)
    except Exception:
        return None


def _ifc_class(element: Any) -> str:
    is_a = getattr(element, "is_a", None)
    if callable(is_a):
        try:
            return _clean_text(is_a())
        except Exception:
            return ""
    return ""


def _numeric_list(values: Any) -> list[float]:
    result: list[float] = []
    for value in values or []:
        try:
            result.append(round(float(value), 6))
        except (TypeError, ValueError):
            return []
    return result


def _index_list(values: Any) -> list[int]:
    result: list[int] = []
    for value in values or []:
        try:
            index = int(value)
        except (TypeError, ValueError):
            return []
        if index < 0:
            return []
        result.append(index)
    return result


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert IFC geometry into a Pypmis backend geometry cache artifact.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--jobs", default=None, type=int)
    parser.add_argument("--max-products", default=20_000, type=int)
    parser.add_argument("--max-triangles", default=3_000_000, type=int)
    args = parser.parse_args()
    convert_ifc_geometry(
        args.source,
        args.output,
        jobs=args.jobs,
        max_products=args.max_products,
        max_triangles=args.max_triangles,
    )


if __name__ == "__main__":
    main()

