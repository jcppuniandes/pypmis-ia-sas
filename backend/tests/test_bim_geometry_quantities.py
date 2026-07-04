from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.services.bim_models import BimModelService


def test_bulk_geometry_measurement_previews_and_applies_dimensional_ifc_quantities(
    tmp_path: Path,
    monkeypatch,
) -> None:
    artifact_path = tmp_path / "geometry_cache.json"
    artifact_path.write_text(
        json.dumps(
            {
                "version": 1,
                "engine": "test-geometry",
                "units": "meters",
                "revision_id": "IFC-TEST-GEOMETRY",
                "stats": {"product_count": 1, "mesh_count": 1, "triangle_count": 12},
                "products": [
                    {
                        "express_id": 50,
                        "global_id": "GUID-SLAB-001",
                        "ifc_class": "IfcSlab",
                        "name": "Losa maciza",
                        "mesh": _box_mesh(3.0, 2.0, 0.2),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(BimModelService, "geometry_cache_path", classmethod(lambda cls, model: artifact_path))

    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _create_project(client, headers)
        model_response = client.post(
            f"/api/v1/projects/{project_id}/bim-models",
            headers=headers,
            files={"file": ("model.ifc", BytesIO(_minimal_ifc()), "application/octet-stream")},
        )
        takeoff_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoffs/import",
            headers=headers,
            data={"bim_model_id": str(model_response.json()["id"])},
            files={
                "file": (
                    "quantities.csv",
                    BytesIO(
                        b"element_guid,element_id,ifc_class,category,quantity,unit,measurement_rule\n"
                        b"GUID-SLAB-001,#50,IfcSlab,Losa,1,ea,ElementCount\n"
                    ),
                    "text/csv",
                )
            },
        )
        model_id = model_response.json()["id"]
        run_id = takeoff_response.json()["id"]
        assert takeoff_response.json()["bim_model_id"] == model_id
        assert takeoff_response.json()["source_sha256"]
        assert takeoff_response.json()["bim_revision_id"] == model_response.json()["revision_id"]

        preview_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run_id}/geometry-measurements",
            headers=headers,
            json={"model_id": model_id, "apply": False},
        )
        apply_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run_id}/geometry-measurements",
            headers=headers,
            json={"model_id": model_id, "apply": True},
        )
        lines_response = client.get(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run_id}/lines",
            headers=headers,
        )

    assert model_response.status_code == 200
    assert takeoff_response.status_code == 200
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["ready_count"] == 1
    assert preview["applied_count"] == 0
    assert preview["unmatched_count"] == 0
    assert preview["results"][0]["status"] == "ready"
    assert preview["results"][0]["measurement_rule"] == "GeometryMeshArea"
    assert preview["results"][0]["geometry_quantity"] == 6.0
    assert preview["results"][0]["geometry_unit"] == "m2"
    assert preview["results"][0]["current_quantity"] == 1.0
    assert preview["results"][0]["current_unit"] == "ea"

    assert apply_response.status_code == 200, apply_response.text
    applied = apply_response.json()
    assert applied["applied_count"] == 1
    assert applied["results"][0]["status"] == "applied"
    assert applied["results"][0]["source_quantity"] == 1.0
    assert applied["results"][0]["source_unit"] == "ea"
    assert applied["results"][0]["approved_quantity"] == 6.0
    assert applied["results"][0]["approved_unit"] == "m2"

    line = lines_response.json()[0]
    controlled = line["raw_data"]["controlled_measurement"]
    assert controlled["measurement_rule"] == "GeometryMeshArea"
    assert controlled["quantity"] == 6.0
    assert controlled["unit"] == "m2"
    assert controlled["source"] == "Backend IFC geometry cache"
    assert line["raw_data"]["quantity_rule"]["status"] == "valid"


def test_bulk_geometry_measurement_rejects_a_different_ifc_model() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _create_project(client, headers)
        model_response = client.post(
            f"/api/v1/projects/{project_id}/bim-models",
            headers=headers,
            files={"file": ("geometry-model.ifc", BytesIO(_minimal_ifc()), "application/octet-stream")},
        )
        takeoff_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoffs/import",
            headers=headers,
            files={
                "file": (
                    "quantity-source.ifc",
                    BytesIO(_minimal_ifc().replace(b"GUID-SLAB-001", b"GUID-SLAB-XYZ")),
                    "application/octet-stream",
                )
            },
        )

        response = client.put(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{takeoff_response.json()['id']}/bim-model",
            headers=headers,
            json={"model_id": model_response.json()["id"], "expected_version": takeoff_response.json()["version"]},
        )

    assert response.status_code == 409
    assert "source hash" in response.json()["detail"]


def _box_mesh(x: float, y: float, z: float) -> dict[str, list[float] | list[int]]:
    vertices = [
        0, 0, 0,
        x, 0, 0,
        x, y, 0,
        0, y, 0,
        0, 0, z,
        x, 0, z,
        x, y, z,
        0, y, z,
    ]
    indices = [
        0, 2, 1, 0, 3, 2,
        4, 5, 6, 4, 6, 7,
        0, 1, 5, 0, 5, 4,
        1, 2, 6, 1, 6, 5,
        2, 3, 7, 2, 7, 6,
        3, 0, 4, 3, 4, 7,
    ]
    return {"vertices": vertices, "indices": indices}


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": "ana.control@demo.local", "password": "1234"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_project(client: TestClient, headers: dict[str, str]) -> int:
    suffix = uuid4().hex[:8]
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "code": f"GEO-{suffix}",
            "name": f"Geometry Project {suffix}",
            "status": "authorized",
            "currency": "COP",
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def _minimal_ifc() -> bytes:
    return b"""ISO-10303-21;
HEADER;
FILE_SCHEMA(('IFC4X3'));
ENDSEC;
DATA;
#10=IFCPROJECT('PROJECTGUID',$,'Geometry Project',$,$,$,$,$,$);
#50=IFCSLAB('GUID-SLAB-001',$,'Losa maciza',$,$,$,$,$,$);
ENDSEC;
END-ISO-10303-21;
"""
