from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_process_flow_board_shows_clean_project_bpm_readiness() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_response = client.post(
            "/api/v1/projects",
            headers=headers,
            json={
                "code": f"BPM-{suffix}",
                "name": "BPM controlled project",
                "phase": "Planning",
                "currency": "USD",
                "calendar_base": "5x8 Colombia",
                "owner": "Owner PMO",
                "status": "authorized",
                "authorization_ref": f"AFE-BPM-{suffix}",
                "configuration": {"funding_required": True, "control_level": "control_account"},
            },
        )
        project_id = project_response.json()["id"]

        board_response = client.get(f"/api/v1/projects/{project_id}/process-flow-board", headers=headers)

    assert project_response.status_code == 200
    assert board_response.status_code == 200
    board = board_response.json()
    assert board["project_id"] == project_id
    assert board["overall_status"] == "blocked"
    assert board["completion_percent"] < 50

    lanes = {lane["key"]: lane for lane in board["lanes"]}
    assert {"owner", "project_controls", "planning", "cost_funding", "awp_construction"}.issubset(lanes)

    owner_items = {item["key"]: item for item in lanes["owner"]["items"]}
    assert owner_items["project_authorization"]["status"] == "complete"
    assert "authorization reference" in owner_items["project_authorization"]["evidence"].lower()

    controls_items = {item["key"]: item for item in lanes["project_controls"]["items"]}
    assert controls_items["operational_setup"]["status"] == "blocked"
    assert controls_items["role_matrix"]["status"] == "review_required"
    assert "Client role matrix" in controls_items["role_matrix"]["acceptance_criteria"][0]

    planning_items = {item["key"]: item for item in lanes["planning"]["items"]}
    assert planning_items["activity_sheet"]["status"] == "blocked"
    assert planning_items["wbs_sheet"]["status"] == "blocked"

    funding_items = {item["key"]: item for item in lanes["cost_funding"]["items"]}
    assert funding_items["fbs_funding"]["status"] == "blocked"
    assert funding_items["cbs_cost_codes"]["status"] == "blocked"

    awp_items = {item["key"]: item for item in lanes["awp_construction"]["items"]}
    assert awp_items["bim_quantity_takeoff"]["status"] == "blocked"
    assert awp_items["bim_quantity_takeoff"]["target_view"] == "quantity-takeoff"
    assert "BIM/IFC or Excel" in awp_items["bim_quantity_takeoff"]["next_action"]


def test_process_flow_board_advances_after_setup_activity_sheet_and_funding() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_response = client.post(
            "/api/v1/projects",
            headers=headers,
            json={
                "code": f"BPM-ACT-{suffix}",
                "name": "BPM active controls project",
                "phase": "Planning",
                "currency": "USD",
                "calendar_base": "5x8 Colombia",
                "owner": "Owner PMO",
                "status": "authorized",
                "authorization_ref": f"AFE-BPM-ACT-{suffix}",
                "configuration": {"funding_required": True, "control_level": "control_account"},
            },
        )
        project_id = project_response.json()["id"]
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
        activity_response = client.post(
            f"/api/v1/projects/{project_id}/activity-sheets/get-data",
            headers=headers,
            files={"file": ("baseline.xml", _p6_xml(), "application/xml")},
        )
        funding_response = client.post(
            f"/api/v1/projects/{project_id}/fbs",
            headers=headers,
            json={
                "code": f"FUND-BPM-{suffix}",
                "source_of_funds": "Owner equity",
                "funding_type": "AFE",
                "authorization_ref": f"AFE-FUND-{suffix}",
                "approved_amount": 10_000,
                "currency": "USD",
                "status": "approved",
            },
        )

        board_response = client.get(f"/api/v1/projects/{project_id}/process-flow-board", headers=headers)

    assert setup_response.status_code == 200
    assert activity_response.status_code == 200
    assert funding_response.status_code == 200
    assert board_response.status_code == 200
    board = board_response.json()
    assert board["completion_percent"] >= 50

    lanes = {lane["key"]: lane for lane in board["lanes"]}
    controls_items = {item["key"]: item for item in lanes["project_controls"]["items"]}
    planning_items = {item["key"]: item for item in lanes["planning"]["items"]}
    funding_items = {item["key"]: item for item in lanes["cost_funding"]["items"]}

    assert controls_items["operational_setup"]["status"] == "complete"
    assert planning_items["activity_sheet"]["status"] == "complete"
    assert planning_items["wbs_sheet"]["status"] == "complete"
    assert funding_items["fbs_funding"]["status"] == "complete"
    assert funding_items["cbs_cost_codes"]["status"] in {"complete", "review_required"}


def test_process_flow_board_tracks_bim_quantity_takeoff_mapping() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_response = client.post(
            "/api/v1/projects",
            headers=headers,
            json={
                "code": f"BPM-QTO-{suffix}",
                "name": "BPM quantity project",
                "phase": "Planning",
                "currency": "USD",
                "calendar_base": "5x8 Colombia",
                "owner": "Owner PMO",
                "status": "authorized",
                "authorization_ref": f"AFE-BPM-QTO-{suffix}",
                "configuration": {"funding_required": True, "control_level": "control_account"},
            },
        )
        project_id = project_response.json()["id"]
        wbs = client.post(
            f"/api/v1/projects/{project_id}/wbs",
            headers=headers,
            json={"code": f"QTO-WBS-{suffix}", "name": "Civil concrete", "level": 2, "status": "active"},
        ).json()
        cbs = client.post(
            f"/api/v1/projects/{project_id}/cbs",
            headers=headers,
            json={"code": f"QTO-CBS-{suffix}", "cost_category": "Concrete", "level": 2, "status": "active"},
        ).json()
        fbs = client.post(
            f"/api/v1/projects/{project_id}/fbs",
            headers=headers,
            json={
                "code": f"QTO-FBS-{suffix}",
                "source_of_funds": "Owner equity",
                "funding_type": "AFE",
                "authorization_ref": f"AFE-FUND-{suffix}",
                "approved_amount": 10_000,
                "currency": "USD",
                "status": "approved",
            },
        ).json()
        csv_content = (
            "element_guid,ifc_class,type,storey,system,quantity,unit,measurement_rule,wbs_code,cbs_code,fbs_code,package_code\n"
            f"GUID-001,IfcWall,Concrete wall,Nivel 1,Civil,12.5,m3,NetVolume,{wbs['code']},{cbs['code']},{fbs['code']},CWP-CIV-001\n"
            "GUID-002,IfcDoor,Door,Nivel 1,Architecture,3,und,Count,UNKNOWN-WBS,,UNKNOWN-FBS,CWP-ARQ-001\n"
        ).encode()
        upload_response = client.post(
            f"/api/v1/projects/{project_id}/quantity-takeoffs/import",
            headers=headers,
            files={"file": ("quantities.csv", csv_content, "text/csv")},
        )

        board_response = client.get(f"/api/v1/projects/{project_id}/process-flow-board", headers=headers)

    assert project_response.status_code == 200
    assert upload_response.status_code == 200
    assert board_response.status_code == 200
    board = board_response.json()
    awp_lane = next(lane for lane in board["lanes"] if lane["key"] == "awp_construction")
    awp_items = {item["key"]: item for item in awp_lane["items"]}
    qto_item = awp_items["bim_quantity_takeoff"]
    assert qto_item["status"] == "review_required"
    assert qto_item["target_view"] == "quantity-takeoff"
    assert "1 mapped" in qto_item["evidence"]
    assert "1 need mapping" in qto_item["evidence"]
    assert "Controlled physical quantity items" in qto_item["acceptance_criteria"][0]


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
    <ObjectId>10</ObjectId>
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
