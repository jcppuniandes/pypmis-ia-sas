from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_project_can_be_created_with_authorization_and_control_configuration() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]

        response = client.post(
            "/api/v1/projects",
            headers=headers,
            json={
                "code": f"INT-{suffix}",
                "name": "Integrated control project",
                "phase": "Planning",
                "currency": "USD",
                "calendar_base": "5x8 Colombia",
                "owner": "Owner PMO",
                "status": "authorized",
                "authorization_date": "2026-05-12",
                "authorization_ref": "AFE-INT-001",
                "configuration": {"control_level": "control_account", "funding_required": True},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == f"INT-{suffix}"
    assert payload["calendar_base"] == "5x8 Colombia"
    assert payload["owner"] == "Owner PMO"
    assert payload["status"] == "authorized"
    assert payload["authorization_ref"] == "AFE-INT-001"
    assert payload["configuration"]["funding_required"] is True


def test_integrated_control_matrix_enforces_funding_and_reports_traceability() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _first_project_id(client, headers)
        suffix = uuid4().hex[:8]

        wbs_response = client.post(
            f"/api/v1/projects/{project_id}/wbs",
            headers=headers,
            json={
                "code": f"1.5.3-{suffix}",
                "name": "Obras civiles planta",
                "level": 3,
                "description": "Civil works for plant area",
                "dictionary": "Scope, deliverables and acceptance criteria for civil works.",
                "responsible": "Project Controls",
                "status": "active",
            },
        )
        wbs = wbs_response.json()

        fbs_response = client.post(
            f"/api/v1/projects/{project_id}/fbs",
            headers=headers,
            json={
                "code": f"FBS-OWN-{suffix}",
                "source_of_funds": "Owner equity",
                "funding_type": "AFE",
                "authorization_ref": f"AFE-{suffix}",
                "usage_restrictions": "Civil works only",
                "approved_amount": 10_000,
                "currency": "USD",
                "status": "approved",
                "usage_rules": "Commitments require available funding before award.",
            },
        )
        fbs = fbs_response.json()

        cbs_response = client.post(
            f"/api/v1/projects/{project_id}/cbs",
            headers=headers,
            json={
                "code": f"4000-{suffix}",
                "level": 2,
                "cost_category": "MO",
                "description": "Labor cost element",
                "status": "active",
            },
        )
        cbs = cbs_response.json()

        account_response = client.post(
            f"/api/v1/projects/{project_id}/control-accounts",
            headers=headers,
            json={
                "wbs_id": wbs["id"],
                "code": f"CA-PLT-CIV-{suffix}",
                "name": "Civil works control account",
                "responsible": "Construction Manager",
                "discipline": "Civil",
                "cbs_code": cbs["code"],
                "measurement_rule": "Physical percent by installed quantities.",
                "scope": "Civil works in plant area",
                "budget": 9_500,
                "forecast": 9_750,
                "lifecycle_status": "active",
            },
        )
        account = account_response.json()

        missing_fbs_response = client.post(
            f"/api/v1/projects/{project_id}/contracts",
            headers=headers,
            json={
                "control_account_id": account["id"],
                "code": f"CTR-NOFBS-{suffix}",
                "title": "Contract without funding",
                "counterparty": "Civil Contractor",
                "contract_type": "Services",
                "value": 1_000,
                "status": "active",
            },
        )
        contract_response = client.post(
            f"/api/v1/projects/{project_id}/contracts",
            headers=headers,
            json={
                "funding_source_id": fbs["id"],
                "control_account_id": account["id"],
                "code": f"CTR-CIV-{suffix}",
                "title": "Civil commitment contract",
                "counterparty": "Civil Contractor",
                "contract_type": "Services",
                "value": 9_000,
                "status": "active",
            },
        )
        overcommit_response = client.post(
            f"/api/v1/projects/{project_id}/purchase-orders",
            headers=headers,
            json={
                "funding_source_id": fbs["id"],
                "control_account_id": account["id"],
                "contract_id": contract_response.json()["id"],
                "po_number": f"PO-OVER-{suffix}",
                "description": "Over available funding",
                "vendor": "Civil Vendor",
                "committed_amount": 2_000,
                "status": "issued",
            },
        )
        cost_code_response = client.post(
            f"/api/v1/projects/{project_id}/cost-codes",
            headers=headers,
            json={
                "code": f"MIN-1.5.3-CA-PLT-CIV-{suffix}-4000",
                "wbs_id": wbs["id"],
                "control_account_id": account["id"],
                "cbs_id": cbs["id"],
                "fbs_id": fbs["id"],
                "contract_ref": f"CTR-CIV-{suffix}",
                "budget": 9_500,
                "funds_available": 1_000,
                "commitments": 9_000,
                "actual_costs": 0,
                "forecast": 9_750,
                "status": "active",
            },
        )
        availability_response = client.get(
            f"/api/v1/projects/{project_id}/funding-availability-check",
            headers=headers,
            params={"funding_source_id": fbs["id"], "requested_amount": 1_000},
        )
        matrix_response = client.get(f"/api/v1/projects/{project_id}/integrated-control-matrix", headers=headers)
        forecast_response = client.get(f"/api/v1/projects/{project_id}/forecast-vs-funding-report", headers=headers)

    assert wbs_response.status_code == 200
    assert fbs_response.status_code == 200
    assert fbs["approved_amount"] == 10_000
    assert fbs["funds_available"] == 10_000
    assert cbs_response.status_code == 200
    assert account_response.status_code == 200
    assert missing_fbs_response.status_code == 400
    assert "FBS" in missing_fbs_response.text
    assert contract_response.status_code == 200
    assert contract_response.json()["funding_source_id"] == fbs["id"]
    assert overcommit_response.status_code == 409
    assert "funding" in overcommit_response.text.lower()
    assert cost_code_response.status_code == 200
    assert availability_response.status_code == 200
    assert availability_response.json()["funds_available"] == 1_000
    assert availability_response.json()["is_available"] is True
    assert matrix_response.status_code == 200
    row = next(item for item in matrix_response.json() if item["cost_code"] == cost_code_response.json()["code"])
    assert row["project_code"]
    assert row["fbs_code"] == fbs["code"]
    assert row["wbs_code"] == wbs["code"]
    assert row["control_account_code"] == account["code"]
    assert row["cbs_code"] == cbs["code"]
    assert row["committed"] == 9_000
    assert row["balance"] == 1_000
    assert forecast_response.status_code == 200
    report_row = next(item for item in forecast_response.json()["rows"] if item["fbs_code"] == fbs["code"])
    assert report_row["forecast"] == 9_750
    assert report_row["forecast_vs_available"] == -8_750


def test_baseline_approval_and_financial_closeout_update_integrated_states() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _first_project_id(client, headers)
        suffix = uuid4().hex[:8]

        fbs_response = client.post(
            f"/api/v1/projects/{project_id}/fbs",
            headers=headers,
            json={
                "code": f"FBS-CLOSE-{suffix}",
                "source_of_funds": "Public funding",
                "funding_type": "Vigencia",
                "authorization_ref": f"VIG-{suffix}",
                "approved_amount": 5_000,
                "currency": "USD",
                "status": "approved",
            },
        )
        fbs = fbs_response.json()
        account = client.get(f"/api/v1/projects/{project_id}/control-accounts", headers=headers).json()[0]
        contract_response = client.post(
            f"/api/v1/projects/{project_id}/contracts",
            headers=headers,
            json={
                "funding_source_id": fbs["id"],
                "control_account_id": account["id"],
                "code": f"CTR-CLOSE-{suffix}",
                "title": "Closeout commitment",
                "counterparty": "Closeout Contractor",
                "contract_type": "Services",
                "value": 2_000,
                "status": "active",
            },
        )
        baseline_response = client.post(f"/api/v1/projects/{project_id}/baseline-approval", headers=headers)
        closeout_report_response = client.get(
            f"/api/v1/projects/{project_id}/closeout-report",
            headers=headers,
            params={"funding_source_id": fbs["id"]},
        )
        closeout_response = client.post(
            f"/api/v1/projects/{project_id}/financial-closeout",
            headers=headers,
            params={"funding_source_id": fbs["id"]},
        )

    assert fbs_response.status_code == 200
    assert contract_response.status_code == 200
    assert baseline_response.status_code == 200
    assert baseline_response.json()["project_status"] == "baseline_approved"
    assert closeout_report_response.status_code == 200
    assert closeout_report_response.json()["unused_balance"] == 3_000
    assert closeout_response.status_code == 200
    assert closeout_response.json()["funding_status"] == "closed"
    assert closeout_response.json()["closed_commitments"] >= 1


def test_fbs_balance_matches_available_after_executed_costs() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _first_project_id(client, headers)
        suffix = uuid4().hex[:8]

        fbs_response = client.post(
            f"/api/v1/projects/{project_id}/fbs",
            headers=headers,
            json={
                "code": f"FBS-BAL-{suffix}",
                "source_of_funds": "Owner equity",
                "funding_type": "AFE",
                "authorization_ref": f"AFE-BAL-{suffix}",
                "approved_amount": 5_000,
                "currency": "USD",
                "status": "approved",
            },
        )
        fbs = fbs_response.json()
        account = client.get(f"/api/v1/projects/{project_id}/control-accounts", headers=headers).json()[0]
        contract_response = client.post(
            f"/api/v1/projects/{project_id}/contracts",
            headers=headers,
            json={
                "funding_source_id": fbs["id"],
                "control_account_id": account["id"],
                "code": f"CTR-BAL-{suffix}",
                "title": "Balance commitment",
                "counterparty": "Balance Contractor",
                "contract_type": "Services",
                "value": 2_000,
                "status": "active",
            },
        )
        certificate_response = client.post(
            f"/api/v1/projects/{project_id}/payment-certificates",
            headers=headers,
            json={
                "contract_id": contract_response.json()["id"],
                "control_account_id": account["id"],
                "certificate_no": f"CERT-BAL-{suffix}",
                "period_label": "2026-05",
                "certified_amount": 500,
                "status": "certified",
            },
        )
        list_response = client.get(f"/api/v1/projects/{project_id}/fbs", headers=headers)

    assert fbs_response.status_code == 200
    assert contract_response.status_code == 200
    assert certificate_response.status_code == 200
    refreshed = next(item for item in list_response.json() if item["id"] == fbs["id"])
    assert refreshed["funds_committed"] == 2_000
    assert refreshed["funds_executed"] == 500
    assert refreshed["funds_available"] == 2_500
    assert refreshed["balance"] == 2_500


def _first_project_id(client: TestClient, headers: dict[str, str]) -> int:
    # These tests need the seeded demo project: it already has an ingested
    # schedule, so the control-data gate (409 without source schedule) is open.
    # Other test modules create projects whose codes sort before it, so picking
    # projects[0] is order-dependent across the full suite.
    response = client.get("/api/v1/projects", headers=headers)
    assert response.status_code == 200
    projects = response.json()
    demo = next((project for project in projects if project["code"] == "CTRL-DEMO-001"), None)
    assert demo, "Seeded demo project CTRL-DEMO-001 not found"
    return int(demo["id"])


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ana.control@demo.local", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
