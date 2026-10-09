from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_activity_sheet_get_data_requires_ready_project_operational_setup() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]

        project_response = client.post(
            "/api/v1/projects",
            headers=headers,
            json={
                "code": f"OPS-{suffix}",
                "name": "Operational setup project",
                "phase": "Planning",
                "currency": "USD",
                "calendar_base": "5x8 Colombia",
                "owner": "Owner PMO",
                "status": "authorized",
                "authorization_ref": f"AFE-OPS-{suffix}",
            },
        )
        project_id = project_response.json()["id"]

        blocked_response = client.post(
            f"/api/v1/projects/{project_id}/activity-sheets/get-data",
            headers=headers,
            files={"file": ("baseline.xml", _p6_xml(), "application/xml")},
        )

        setup_response = client.put(
            f"/api/v1/projects/{project_id}/operational-setup",
            headers=headers,
            json={
                "project_number": f"PRJ-{suffix}",
                "setup_template": "Capital Project Controls Template",
                "attribute_form": "Project Attribute Form",
                "permissions_configured": True,
                "modules_configured": True,
                "cost_sheet_ready": True,
                "funding_sheet_ready": True,
                "p6_mapping_ready": True,
                "status": "ready",
            },
        )
        allowed_response = client.post(
            f"/api/v1/projects/{project_id}/activity-sheets/get-data",
            headers=headers,
            files={"file": ("baseline.xml", _p6_xml(), "application/xml")},
        )
        sheets_response = client.get(f"/api/v1/projects/{project_id}/activity-sheets", headers=headers)
        activity_sheet_id = allowed_response.json()["id"] if allowed_response.status_code == 200 else 0
        rows_response = client.get(
            f"/api/v1/projects/{project_id}/activity-sheets/{activity_sheet_id}/rows",
            headers=headers,
        )
        wbs_sheet_response = client.get(
            f"/api/v1/projects/{project_id}/activity-sheets/{activity_sheet_id}/wbs-sheet",
            headers=headers,
        )
        wbs_response = client.get(f"/api/v1/projects/{project_id}/wbs", headers=headers)
        cbs_response = client.get(f"/api/v1/projects/{project_id}/cbs", headers=headers)

    assert project_response.status_code == 200
    assert blocked_response.status_code == 409
    assert "operational setup" in blocked_response.text.lower()
    assert setup_response.status_code == 200
    setup_payload = setup_response.json()
    assert setup_payload["readiness_status"] == "ready"
    assert setup_payload["project_number"].startswith("PRJ-")
    assert allowed_response.status_code == 200
    activity_sheet = allowed_response.json()
    assert activity_sheet["source_file_name"] == "baseline.xml"
    assert activity_sheet["row_count"] == 1
    assert activity_sheet["status"] == "validated"
    assert sheets_response.status_code == 200
    assert any(sheet["id"] == activity_sheet["id"] for sheet in sheets_response.json())
    assert rows_response.status_code == 200
    row = rows_response.json()[0]
    assert row["planned_cost"] == 2500
    assert row["planned_value"] == 1250
    assert row["planned_percent"] == 50
    assert row["cbs_code"] == "CBS-OPS-OBRAS-CIVILES-PLANTA-EARTH"
    assert "A100" not in row["cbs_code"]
    assert row["control_account_code"] == "CA-OPS-OBRAS-CIVILES-PLANTA"
    assert row["mapping_status"] == "mapped"
    assert cbs_response.status_code == 200
    cbs_by_code = {item["code"]: item for item in cbs_response.json()}
    assert cbs_by_code["CBS-OPS-OBRAS-CIVILES-PLANTA-EARTH"]["cost_category"] == "Earthworks"
    assert cbs_by_code["CBS-OPS-OBRAS-CIVILES-PLANTA-EARTH"]["status"] == "draft"
    assert wbs_sheet_response.status_code == 200
    wbs_rows_by_code = {item["wbs_code"]: item for item in wbs_sheet_response.json()}
    assert wbs_rows_by_code["PLT"]["wbs_name"] == "Proyecto Piloto"
    assert wbs_rows_by_code["PLT"]["activity_count"] == 1
    assert wbs_rows_by_code["PLT"]["control_account_count"] == 1
    assert wbs_rows_by_code["PLT"]["planned_cost"] == 2500
    assert wbs_rows_by_code["PLT"]["planned_value"] == 1250
    assert wbs_rows_by_code["PLT"]["needs_review_count"] == 0
    assert wbs_rows_by_code["PLT-CIV"]["wbs_name"] == "Obras civiles planta"
    assert wbs_rows_by_code["PLT-CIV"]["activity_count"] == 1
    assert wbs_rows_by_code["PLT-CIV"]["control_account_count"] == 1
    assert wbs_rows_by_code["PLT-CIV"]["planned_cost"] == 2500
    assert wbs_rows_by_code["PLT-CIV"]["planned_value"] == 1250
    assert wbs_rows_by_code["PLT-CIV"]["needs_review_count"] == 0
    assert wbs_response.status_code == 200
    wbs_by_code = {row["code"]: row for row in wbs_response.json()}
    assert "PLT" in wbs_by_code
    assert wbs_by_code["PLT-CIV"]["parent_id"] == wbs_by_code["PLT"]["id"]
    assert wbs_by_code["PLT-CIV"]["level"] == wbs_by_code["PLT"]["level"] + 1


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ana.control@demo.local", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _p6_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<Project xmlns="http://xmlns.oracle.com/Primavera/P6/V19/API/BusinessObjects">
  <DataDate>2026-03-11T17:00:00</DataDate>
  <WBS>
    <ObjectId>9</ObjectId>
    <Code>PLT</Code>
    <Name>Proyecto Piloto</Name>
  </WBS>
  <WBS>
    <ObjectId>10</ObjectId>
    <ParentObjectId>9</ParentObjectId>
    <Code>PLT-CIV</Code>
    <Name>Obras civiles planta</Name>
  </WBS>
  <Activity>
    <ObjectId>100</ObjectId>
    <Id>A100</Id>
    <Name>Excavacion area planta</Name>
    <WBSObjectId>10</WBSObjectId>
    <PlannedStartDate>2026-03-01T08:00:00</PlannedStartDate>
    <PlannedFinishDate>2026-03-21T17:00:00</PlannedFinishDate>
    <TotalFloatDuration>PT16H</TotalFloatDuration>
  </Activity>
  <ResourceAssignment>
    <ActivityObjectId>100</ActivityObjectId>
    <PlannedCost>2500</PlannedCost>
  </ResourceAssignment>
</Project>
"""
