from __future__ import annotations

from io import BytesIO
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_forensic_dossier_import_creates_claim_analysis_records() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _create_project(client, headers, uuid4().hex[:8])

        dossier = (
            "Contract notice issued for delayed access to work fronts. "
            "The event caused 18 days of delay on the critical path and COP 25000000 additional cost. "
            "Evidence includes correspondence, schedule update and cost backup."
        ).encode("utf-8")
        response = client.post(
            f"/api/v1/projects/{project_id}/claims/forensic-runs",
            headers=headers,
            data={"mode": "review"},
            files=[("files", ("claim-dossier.txt", BytesIO(dossier), "text/plain"))],
        )
        dashboard_response = client.get(f"/api/v1/projects/{project_id}/dashboard", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["mode"] == "review"
    assert payload["source_files"] == ["claim-dossier.txt"]
    assert payload["readiness_score"] > 0
    assert len(payload["created_claims"]) >= 1
    assert len(payload["created_entitlement_items"]) >= 5
    assert len(payload["created_impact_analyses"]) >= 1
    assert len(payload["created_notices"]) >= 1
    assert dashboard_response.status_code == 200
    summary = dashboard_response.json()["claims_forensic_summary"]
    assert summary["total_claims"] >= 1
    assert summary["impact_analyses"] >= 1
    assert summary["total_claimed_cost"] >= 25000000
    assert summary["total_schedule_impact_days"] >= 18


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": "ana.control@demo.local", "password": "1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_project(client: TestClient, headers: dict[str, str], suffix: str) -> int:
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "code": f"CLM-{suffix}",
            "name": f"Proyecto Claims {suffix}",
            "phase": "Execution",
            "currency": "COP",
            "calendar_base": "5x8 Colombia",
            "owner": "Owner",
            "status": "authorized",
            "authorization_date": "2026-06-01",
            "authorization_ref": f"AFE-CLM-{suffix}",
            "configuration": {"claims_forensic_enabled": True},
            "start_date": "2026-06-01",
            "finish_date": "2026-12-31",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]
