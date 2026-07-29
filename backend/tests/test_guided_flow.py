from uuid import uuid4

from fastapi.testclient import TestClient

from app.domain.models import ScheduleImport, Tenant
from app.main import app


def test_tenant_and_schedule_import_guided_metadata_defaults() -> None:
    tenant = Tenant(name="P&P MIS SAS", slug="pypmis")
    schedule_import = ScheduleImport(
        tenant_id=1,
        project_id=1,
        source="p6_xer",
        file_name="baseline.xer",
        status="validated",
    )

    assert tenant.base_currency == "COP"
    assert schedule_import.detected_currency == ""
    assert schedule_import.currency_confidence == "unknown"
    assert schedule_import.currency_source == ""
    assert schedule_import.currency_confirmed is False
    assert schedule_import.total_imported_cost == 0
    assert schedule_import.cost_loaded_activity_count == 0
    assert schedule_import.cost_loaded_activity_percent == 0
    assert schedule_import.cost_source_summary == {}


def test_guided_flow_reports_cost_currency_next_action() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _create_ready_project(client, headers, uuid4().hex[:8])
        _load_activity_sheet(client, headers, project_id)

        response = client.get(f"/api/v1/projects/{project_id}/guided-flow", headers=headers)

    assert response.status_code == 200
    flow = response.json()
    assert flow["tenant"]["slug"] == "demo-energy"
    assert flow["tenant"]["base_currency"] == "COP"
    assert flow["project"]["id"] == project_id
    assert flow["cost_currency_gate"]["detected_currency"] in {"COP", "USD"}
    assert flow["cost_currency_gate"]["cost_loaded_activity_count"] >= 1
    assert flow["cost_currency_gate"]["total_imported_cost"] > 0
    assert all(step["key"] != "tenant" for step in flow["steps"])
    assert any(step["key"] == "baseline" and step["state"] in {"blocked", "ready"} for step in flow["steps"])
    assert flow["next_action"]["key"]


def test_confirm_schedule_currency_updates_import_and_project() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _create_ready_project(client, headers, uuid4().hex[:8])
        activity_sheet = _load_activity_sheet(client, headers, project_id)
        schedule_import_id = activity_sheet["schedule_import_id"]

        response = client.post(
            f"/api/v1/projects/{project_id}/schedule-imports/{schedule_import_id}/confirm-currency",
            headers=headers,
            json={"currency": "USD"},
        )
        flow_response = client.get(f"/api/v1/projects/{project_id}/guided-flow", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["currency_confirmed"] is True
    assert payload["detected_currency"] == "USD"
    assert flow_response.status_code == 200
    assert flow_response.json()["cost_currency_gate"]["currency_confirmed"] is True


def test_guided_flow_cost_gate_uses_latest_import_activity_count() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _create_ready_project(client, headers, uuid4().hex[:8])
        first_response = client.post(
            f"/api/v1/projects/{project_id}/activity-sheets/get-data",
            headers=headers,
            files={"file": ("baseline-without-cost.xml", _p6_xml_without_cost(), "application/xml")},
        )
        second_response = client.post(
            f"/api/v1/projects/{project_id}/activity-sheets/get-data",
            headers=headers,
            files={"file": ("baseline-with-cost.xml", _p6_xml(), "application/xml")},
        )

        flow_response = client.get(f"/api/v1/projects/{project_id}/guided-flow", headers=headers)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert flow_response.status_code == 200
    flow = flow_response.json()
    gate = flow["cost_currency_gate"]
    assert gate["schedule_import_id"] == second_response.json()["schedule_import_id"]
    assert gate["cost_loaded_activity_count"] == 1
    assert gate["missing_cost_activity_count"] == 0
    assert gate["cost_loaded_activity_percent"] == 100
    assert next(step for step in flow["steps"] if step["key"] == "schedule")["summary"] == "1 activities imported"


def test_dashboard_exposes_dcma_schedule_quality_metrics() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _create_ready_project(client, headers, uuid4().hex[:8])
        _load_activity_sheet(client, headers, project_id)

        response = client.get(f"/api/v1/projects/{project_id}/dashboard", headers=headers)

    assert response.status_code == 200
    metrics = {metric["key"]: metric for metric in response.json()["schedule_quality_metrics"]}
    assert metrics["dcma_logic"]["label"] == "Logic"
    assert metrics["dcma_logic"]["standard"] == "DCMA 01"
    assert metrics["dcma_logic"]["status"] == "fail"
    assert metrics["dcma_logic"]["item_count"] == 1
    assert metrics["dcma_leads"]["item_count"] == 0
    assert metrics["dcma_high_float"]["percent"] == 0
    assert all("threshold" in metric for metric in metrics.values())


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ana.control@demo.local", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_ready_project(client: TestClient, headers: dict[str, str], suffix: str) -> int:
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "code": f"GF-{suffix}",
            "name": "Guided flow project",
            "phase": "Planning",
            "currency": "COP",
            "calendar_base": "5x8 Colombia",
            "owner": "Owner PMO",
            "status": "authorized",
            "authorization_ref": f"AFE-GF-{suffix}",
        },
    )
    assert response.status_code == 200
    project_id = response.json()["id"]
    setup_response = client.put(
        f"/api/v1/projects/{project_id}/operational-setup",
        headers=headers,
        json={
            "project_number": f"GF-{suffix}",
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
    assert setup_response.status_code == 200
    return project_id


def _load_activity_sheet(client: TestClient, headers: dict[str, str], project_id: int) -> dict[str, object]:
    response = client.post(
        f"/api/v1/projects/{project_id}/activity-sheets/get-data",
        headers=headers,
        files={"file": ("baseline.xml", _p6_xml(), "application/xml")},
    )
    assert response.status_code == 200
    return response.json()


def _p6_xml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<Project xmlns="http://xmlns.oracle.com/Primavera/P6/V19/API/BusinessObjects">
  <DataDate>2026-03-11T17:00:00</DataDate>
  <Currency>USD</Currency>
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


def _p6_xml_without_cost() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<Project xmlns="http://xmlns.oracle.com/Primavera/P6/V19/API/BusinessObjects">
  <DataDate>2026-03-10T17:00:00</DataDate>
  <Currency>USD</Currency>
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
</Project>
"""
