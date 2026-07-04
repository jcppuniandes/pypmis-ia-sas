from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_project_quantity_rule_catalog_is_seeded_from_standard_bim_rules() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _create_project(client, headers, f"QRC-{uuid4().hex[:8]}")

        response = client.get(f"/api/v1/projects/{project_id}/bim-quantity-rules", headers=headers)

    assert response.status_code == 200, response.text
    rules = response.json()
    wall_rule = next(rule for rule in rules if rule["ifc_class"] == "IFCWALLSTANDARDCASE")

    assert wall_rule["element_label"] == "Muro"
    assert wall_rule["expected_measure"] == "area o volumen o longitud"
    assert wall_rule["expected_units"] == ["m2", "m3", "m"]
    assert wall_rule["rule_hint"] == "NetSideArea / NetVolume / NetLength"
    assert wall_rule["source"] == "system_default"
    assert wall_rule["status"] == "active"
    assert wall_rule["version"] == 1


def test_project_quantity_rule_catalog_updates_takeoff_audit_rules() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _create_project(client, headers, f"QRC-{uuid4().hex[:8]}")
        catalog = client.get(f"/api/v1/projects/{project_id}/bim-quantity-rules", headers=headers).json()
        wall_rule = next(rule for rule in catalog if rule["ifc_class"] == "IFCWALLSTANDARDCASE")

        update_response = client.put(
            f"/api/v1/projects/{project_id}/bim-quantity-rules/{wall_rule['id']}",
            headers=headers,
            json={
                "element_label": "Muro por unidad validada",
                "expected_measure": "conteo controlado",
                "rule_hint": "ElementCount",
                "expected_units": ["ea"],
                "allow_fallback_count": True,
                "status": "active",
                "expected_version": wall_rule["version"],
            },
        )

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoffs/import",
            headers=headers,
            files={
                "file": (
                    "custom-wall-rule.csv",
                    BytesIO(
                        b"element_guid,ifc_class,category,quantity,unit,measurement_rule\n"
                        b"GUID-WALL-001,IfcWallStandardCase,Muros,1,ea,Count\n"
                    ),
                    "text/csv",
                )
            },
        )
        run = upload_response.json()
        lines_response = client.get(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run.get('id', 0)}/lines",
            headers=headers,
        )

    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["version"] == wall_rule["version"] + 1
    assert update_response.json()["expected_units"] == ["ea"]
    assert upload_response.status_code == 200, upload_response.text
    assert lines_response.status_code == 200, lines_response.text
    line = lines_response.json()[0]
    quantity_rule = line["raw_data"]["quantity_rule"]
    assert quantity_rule["status"] == "valid"
    assert quantity_rule["expected_measure"] == "conteo controlado"
    assert quantity_rule["expected_units"] == ["ea"]
    assert quantity_rule["accepted_rules"] == ["ElementCount"]


def test_project_quantity_rule_recalculation_updates_existing_takeoff_lines() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _create_project(client, headers, f"QRC-{uuid4().hex[:8]}")
        wbs = client.post(
            f"/api/v1/projects/{project_id}/wbs",
            headers=headers,
            json={"code": "WBS-WALLS", "name": "Walls", "level": 2, "status": "active"},
        ).json()
        cbs = client.post(
            f"/api/v1/projects/{project_id}/cbs",
            headers=headers,
            json={"code": "CBS-WALLS", "cost_category": "Walls", "level": 2, "status": "active"},
        ).json()
        fbs = client.post(
            f"/api/v1/projects/{project_id}/fbs",
            headers=headers,
            json={
                "code": "FBS-WALLS",
                "name": "Wall funding",
                "source_of_funds": "Corporate Budget",
                "funding_type": "CAPEX",
                "authorization_ref": "AFE-WALLS",
                "amount": 100000,
                "currency": "USD",
                "status": "approved",
            },
        ).json()

        upload_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoffs/import",
            headers=headers,
            files={
                "file": (
                    "wall-before-rule-change.csv",
                    BytesIO(
                        b"element_guid,ifc_class,category,quantity,unit,measurement_rule,wbs_code,cbs_code,fbs_code,package_code\n"
                        + f"GUID-WALL-001,IfcWallStandardCase,Muros,1,ea,Count,{wbs['code']},{cbs['code']},{fbs['code']},CWP-WALLS\n".encode()
                    ),
                    "text/csv",
                )
            },
        )
        run = upload_response.json()
        blocked_lines = client.get(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run.get('id', 0)}/lines",
            headers=headers,
        ).json()
        catalog = client.get(f"/api/v1/projects/{project_id}/bim-quantity-rules", headers=headers).json()
        wall_rule = next(rule for rule in catalog if rule["ifc_class"] == "IFCWALLSTANDARDCASE")
        client.put(
            f"/api/v1/projects/{project_id}/bim-quantity-rules/{wall_rule['id']}",
            headers=headers,
            json={
                "element_label": "Muro por unidad validada",
                "expected_measure": "conteo controlado",
                "rule_hint": "ElementCount",
                "expected_units": ["ea"],
                "allow_fallback_count": True,
                "status": "active",
                "expected_version": wall_rule["version"],
            },
        )

        recalc_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run['id']}/recalculate-rules",
            headers=headers,
        )
        recalculated_lines = client.get(
            f"/api/v1/projects/{project_id}/quantity-takeoff-runs/{run['id']}/lines",
            headers=headers,
        ).json()

    assert upload_response.status_code == 200, upload_response.text
    assert blocked_lines[0]["raw_data"]["quantity_rule"]["status"] == "blocked"
    assert blocked_lines[0]["mapping_status"] == "needs_mapping"
    assert recalc_response.status_code == 200, recalc_response.text
    recalculation = recalc_response.json()
    assert recalculation["total_lines"] == 1
    assert recalculation["changed_line_count"] == 1
    assert recalculation["valid_count"] == 1
    assert recalculation["blocked_count"] == 0
    assert recalculation["cost_rollup_gate"] == "ready"
    assert recalculation["impacts"][0]["previous_status"] == "blocked"
    assert recalculation["impacts"][0]["new_status"] == "valid"
    assert recalculated_lines[0]["raw_data"]["quantity_rule"]["status"] == "valid"
    assert recalculated_lines[0]["raw_data"]["quantity_rule_recalculation"]["previous"]["status"] == "blocked"
    assert recalculated_lines[0]["mapping_status"] == "mapped"
    assert "Quantity rule blocked" not in recalculated_lines[0]["validation_notes"]


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ana.control@demo.local", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_project(client: TestClient, headers: dict[str, str], code: str) -> int:
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "code": code,
            "name": "Quantity rule catalog project",
            "phase": "Planning",
            "currency": "USD",
            "calendar_base": "5x8 Colombia",
            "owner": "Owner PMO",
            "status": "authorized",
            "authorization_ref": f"AFE-{code}",
        },
    )
    assert response.status_code == 200, response.text
    return int(response.json()["id"])
