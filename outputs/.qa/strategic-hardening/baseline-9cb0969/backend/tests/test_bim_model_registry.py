from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_bim_model_upload_lists_and_serves_ifc_source_without_takeoff() -> None:
    ifc_content = _minimal_ifc()
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, f"BIM-{suffix}")

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/bim-models",
            headers=headers,
            files={"file": ("wellness-center.ifc", BytesIO(ifc_content), "application/octet-stream")},
        )
        model = upload_response.json()
        list_response = client.get(f"/api/v1/projects/{project_id}/bim-models", headers=headers)
        source_response = client.get(
            f"/api/v1/projects/{project_id}/bim-models/{model.get('id', 0)}/source",
            headers=headers,
        )

    assert upload_response.status_code == 200
    assert model["source_file_name"] == "wellness-center.ifc"
    assert model["source_type"] == "ifc"
    assert model["status"] == "uploaded"
    assert model["source_size_bytes"] == len(ifc_content)
    assert len(model["source_sha256"]) == 64
    assert model["revision_id"].startswith(f"IFC-M{model['id']}-")
    assert model["model_identity"]["viewer_engine"] == "web-ifc"
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [model["id"]]
    assert source_response.status_code == 200
    assert source_response.content == ifc_content
    assert "wellness-center.ifc" in source_response.headers["content-disposition"]


def test_bim_model_viewer_manifest_exposes_cache_strategy_and_class_summary() -> None:
    ifc_content = _ifc_with_properties()
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, f"BIM-MANIFEST-{suffix}")

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/bim-models",
            headers=headers,
            files={"file": ("properties.ifc", BytesIO(ifc_content), "application/octet-stream")},
        )
        model_id = upload_response.json()["id"]
        manifest_response = client.get(
            f"/api/v1/projects/{project_id}/bim-models/{model_id}/viewer-manifest",
            headers=headers,
        )

    assert upload_response.status_code == 200
    assert manifest_response.status_code == 200
    manifest = manifest_response.json()
    assert manifest["revision_id"].startswith(f"IFC-M{model_id}-")
    assert manifest["geometry_strategy"] == "direct_browser"
    assert manifest["cache_status"] == "metadata_manifest_ready"
    assert manifest["property_index"]["scan_status"] == "complete"
    assert manifest["property_index"]["property_sets"] == 1
    assert manifest["property_index"]["quantity_sets"] == 1
    assert {"ifc_class": "IfcBuildingElementProxy", "count": 1} in manifest["class_summary"]


def test_bim_model_element_properties_resolve_ifc_psets_quantities_type_and_material() -> None:
    ifc_content = _ifc_with_properties()
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, f"BIM-PROPS-{suffix}")

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/bim-models",
            headers=headers,
            files={"file": ("properties.ifc", BytesIO(ifc_content), "application/octet-stream")},
        )
        model_id = upload_response.json()["id"]
        properties_response = client.get(
            f"/api/v1/projects/{project_id}/bim-models/{model_id}/element-properties",
            headers=headers,
            params={"element_key": "0ZRuQHuvw8SOaxTest001"},
        )

    assert upload_response.status_code == 200
    assert properties_response.status_code == 200
    properties = properties_response.json()
    assert properties["found"] is True
    assert properties["global_id"] == "0ZRuQHuvw8SOaxTest001"
    assert properties["name"] == "Concrete Column"
    assert properties["type_name"] == "Column Type 40x40"
    assert properties["materials"] == ["Concrete C30"]
    assert properties["property_sets"][0]["name"] == "Pset_Concrete"
    assert {"name": "Reference", "value": "COL-01", "type": "IfcPropertySingleValue"} in properties["property_sets"][0][
        "properties"
    ]
    assert {"name": "FireRating", "value": "2h", "type": "IfcPropertySingleValue"} in properties["property_sets"][0][
        "properties"
    ]
    assert {
        "name": "GrossVolume",
        "set_name": "Qto_ColumnBaseQuantities",
        "source": "IFCELEMENTQUANTITY",
        "step_id": "#41",
        "unit": "m3",
        "value": 12.5,
    } in properties["quantities"]


def test_bim_model_geometry_cache_uses_configured_converter_and_serves_artifact(tmp_path, monkeypatch) -> None:
    converter = tmp_path / "fake_ifc_converter.py"
    converter.write_text(
        """
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--source", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
Path(args.output).write_text(json.dumps({
    "version": 1,
    "engine": "fake-ifc-converter",
    "products": [{
        "express_id": 20,
        "global_id": "0ZRuQHuvw8SOaxTest001",
        "ifc_class": "IfcBuildingElementProxy",
        "name": "Concrete Column",
        "mesh": {
            "vertices": [0, 0, 0, 1, 0, 0, 0, 1, 0],
            "indices": [0, 1, 2]
        }
    }]
}))
""",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "BIM_GEOMETRY_CONVERTER_COMMAND",
        f"python {converter} --source {{source}} --output {{output}}",
    )
    get_settings.cache_clear()

    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, f"BIM-CACHE-{suffix}")
        upload_response = client.post(
            f"/api/v1/projects/{project_id}/bim-models",
            headers=headers,
            files={"file": ("geometry.ifc", BytesIO(_ifc_with_properties()), "application/octet-stream")},
        )
        model_id = upload_response.json()["id"]
        cache_response = client.post(
            f"/api/v1/projects/{project_id}/bim-models/{model_id}/viewer-cache",
            headers=headers,
        )
        artifact_response = client.get(
            f"/api/v1/projects/{project_id}/bim-models/{model_id}/geometry-cache",
            headers=headers,
        )
        manifest_response = client.get(
            f"/api/v1/projects/{project_id}/bim-models/{model_id}/viewer-manifest",
            headers=headers,
        )

    get_settings.cache_clear()

    assert upload_response.status_code == 200
    assert cache_response.status_code == 200
    assert cache_response.json()["status"] == "ready"
    assert cache_response.json()["mesh_count"] == 1
    assert artifact_response.status_code == 200
    assert artifact_response.json()["products"][0]["global_id"] == "0ZRuQHuvw8SOaxTest001"
    assert manifest_response.json()["cache_status"] == "geometry_cache_ready"
    assert manifest_response.json()["geometry_strategy"] == "backend_cache"


def test_bim_model_geometry_cache_reports_missing_server_converter(monkeypatch) -> None:
    monkeypatch.setenv("BIM_GEOMETRY_CONVERTER_COMMAND", "")
    get_settings.cache_clear()
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, f"BIM-NOCACHE-{suffix}")
        upload_response = client.post(
            f"/api/v1/projects/{project_id}/bim-models",
            headers=headers,
            files={"file": ("geometry.ifc", BytesIO(_ifc_with_properties()), "application/octet-stream")},
        )
        model_id = upload_response.json()["id"]
        cache_response = client.post(
            f"/api/v1/projects/{project_id}/bim-models/{model_id}/viewer-cache",
            headers=headers,
        )

    assert upload_response.status_code == 200
    assert cache_response.status_code == 409
    assert "converter" in cache_response.json()["detail"].lower()
    get_settings.cache_clear()


def test_bim_model_upload_records_metric_length_units_from_ifc_header() -> None:
    ifc_content = b"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#10=IFCPROJECT('PROJECTGUID',$,'Wellness Center',$,$,$,$,$,$);
#20=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);
ENDSEC;
END-ISO-10303-21;
"""
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, f"BIM-UNITS-{suffix}")

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/bim-models",
            headers=headers,
            files={"file": ("metric.ifc", BytesIO(ifc_content), "application/octet-stream")},
        )

    assert upload_response.status_code == 200
    assert upload_response.json()["units"] == "millimeters"


def test_bim_model_upload_records_ifc_site_georeference() -> None:
    ifc_content = b"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#10=IFCPROJECT('PROJECTGUID',$,'Geo Project',$,$,$,$,$,$);
#20=IFCSITE('SITEGUID',$,'Main Site',$,$,$,$,$,.ELEMENT.,(4,38,24,0),(-74,5,12,0),2600.5,$,$);
#30=IFCPROJECTEDCRS('EPSG:3116',$,'MAGNA-SIRGAS / Colombia Bogota zone',$,$,$,$);
#31=IFCMAPCONVERSION($,#30,1000.25,2000.5,15.0,1.0,0.0,1.0);
ENDSEC;
END-ISO-10303-21;
"""
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, f"BIM-GEO-{suffix}")

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/bim-models",
            headers=headers,
            files={"file": ("geo.ifc", BytesIO(ifc_content), "application/octet-stream")},
        )

    assert upload_response.status_code == 200
    georef = upload_response.json()["model_identity"]["georeferencing"]
    assert georef["source"] == "IFCSITE"
    assert round(georef["latitude_decimal"], 6) == 4.64
    assert round(georef["longitude_decimal"], 6) == -74.086667
    assert georef["elevation"] == 2600.5
    assert georef["projected_crs"] == "EPSG:3116"
    assert georef["map_conversion"]["eastings"] == 1000.25
    assert georef["map_conversion"]["northings"] == 2000.5


def test_bim_model_source_download_is_scoped_to_project() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, f"BIM-A-{suffix}")
        other_project_id = _create_project(client, headers, f"BIM-B-{suffix}")

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/bim-models",
            headers=headers,
            files={"file": ("model.ifc", BytesIO(_minimal_ifc()), "application/octet-stream")},
        )
        model_id = upload_response.json().get("id", 0)
        source_response = client.get(
            f"/api/v1/projects/{other_project_id}/bim-models/{model_id}/source",
            headers=headers,
        )

    assert upload_response.status_code == 200
    assert source_response.status_code == 404


def test_bim_model_upload_rejects_non_ifc_files() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_project(client, headers, f"BIM-XLS-{suffix}")

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/bim-models",
            headers=headers,
            files={"file": ("quantities.csv", BytesIO(b"quantity,unit\n1,ea"), "text/csv")},
        )

    assert upload_response.status_code == 400
    assert "IFC" in upload_response.json()["detail"]


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ana.control@demo.local", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_project(client: TestClient, headers: dict[str, str], suffix: str) -> int:
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "code": f"{suffix}",
            "name": "BIM coordination project",
            "phase": "Planning",
            "currency": "USD",
            "calendar_base": "5x8 Colombia",
            "owner": "Owner PMO",
            "status": "authorized",
            "authorization_ref": f"AFE-{suffix}",
        },
    )
    assert response.status_code == 200
    return int(response.json()["id"])


def _minimal_ifc() -> bytes:
    return b"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#10=IFCPROJECT('PROJECTGUID',$,'Wellness Center',$,$,$,$,$,$);
ENDSEC;
END-ISO-10303-21;
"""


def _ifc_with_properties() -> bytes:
    return b"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#10=IFCPROJECT('PROJECTGUID',$,'Wellness Center',$,$,$,$,$,$);
#20=IFCBUILDINGELEMENTPROXY('0ZRuQHuvw8SOaxTest001',$,'Concrete Column',$,$,$,$,$,$);
#21=IFCBUILDINGELEMENTPROXYTYPE('TYPEGUID',$,'Column Type 40x40',$,$,$,$,$,.USERDEFINED.);
#22=IFCRELDEFINESBYTYPE('RELTYPE',$,$,$,(#20),#21);
#30=IFCPROPERTYSET('PSETGUID',$,'Pset_Concrete',$,(#31,#32));
#31=IFCPROPERTYSINGLEVALUE('Reference',$,IFCLABEL('COL-01'),$);
#32=IFCPROPERTYSINGLEVALUE('FireRating',$,IFCLABEL('2h'),$);
#40=IFCELEMENTQUANTITY('QTOGUID',$,'Qto_ColumnBaseQuantities',$,$,(#41,#42));
#41=IFCQUANTITYVOLUME('GrossVolume',$,$,12.5,$);
#42=IFCQUANTITYAREA('GrossSurfaceArea',$,$,18.25,$);
#50=IFCRELDEFINESBYPROPERTIES('RELPROP',$,$,$,(#20),#30);
#51=IFCRELDEFINESBYPROPERTIES('RELQTO',$,$,$,(#20),#40);
#60=IFCMATERIAL('Concrete C30');
#61=IFCRELASSOCIATESMATERIAL('RELMAT',$,$,$,(#20),#60);
ENDSEC;
END-ISO-10303-21;
"""
