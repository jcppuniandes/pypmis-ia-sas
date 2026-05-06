from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-Id"]


def test_readiness_checks_dependencies() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["database"] == "ok"
    assert payload["checks"]["redis"] == "ok"


def test_login_returns_bearer_token() -> None:
    with TestClient(app) as client:
        response = _login(client)

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["user"]["email"] == "ana.control@demo.local"


def test_projects_rejects_missing_token() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/projects")

    assert response.status_code == 401


def test_projects_and_dashboard_accept_token() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        projects_response = client.get("/api/v1/projects", headers=headers)
        assert projects_response.status_code == 200
        projects = projects_response.json()
        assert len(projects) >= 1

        dashboard_response = client.get(f"/api/v1/projects/{projects[0]['id']}/dashboard", headers=headers)

    assert dashboard_response.status_code == 200
    dashboard = dashboard_response.json()
    assert dashboard["project"]["id"] == projects[0]["id"]
    assert dashboard["project_kpi"]["bac"] >= 0
    assert dashboard["cost_manager_summary"]["total_bac"] >= 0
    assert len(dashboard["cost_sheet"]) >= 1
    assert dashboard["document_control_summary"]["total_documents"] >= 1


def test_pilot_readiness_scores_project_phases() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _first_project_id(client, headers)
        response = client.get(f"/api/v1/projects/{project_id}/pilot-readiness", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == project_id
    assert payload["status"] in {"ready", "pilot_candidate", "needs_preparation"}
    assert payload["score"] >= 60
    assert {item["phase"] for item in payload["items"]} == {"Fase 1", "Fase 2", "Fase 3", "Fase 4", "Fase 5", "Fase 6"}


def test_project_control_plan_can_be_updated_with_version() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _first_project_id(client, headers)
        plan_response = client.get(f"/api/v1/projects/{project_id}/control-plan", headers=headers)
        plan = plan_response.json()

        update_response = client.put(
            f"/api/v1/projects/{project_id}/control-plan",
            headers=headers,
            json={
                "reporting_cadence": "Weekly pilot steering",
                "status": "active",
                "expected_version": plan["version"],
            },
        )
        stale_response = client.put(
            f"/api/v1/projects/{project_id}/control-plan",
            headers=headers,
            json={
                "reporting_cadence": "Stale cadence",
                "expected_version": plan["version"],
            },
        )

    assert plan_response.status_code == 200
    assert plan["control_strategy"]
    assert update_response.status_code == 200
    assert update_response.json()["version"] == plan["version"] + 1
    assert stale_response.status_code == 409


def test_cost_manager_records_can_be_created_and_versioned() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _first_project_id(client, headers)
        suffix = uuid4().hex[:8]
        accounts_response = client.get(f"/api/v1/projects/{project_id}/control-accounts", headers=headers)
        control_account_id = accounts_response.json()[0]["id"]

        funding_response = client.post(
            f"/api/v1/projects/{project_id}/funding-sources",
            headers=headers,
            json={
                "code": f"TEST-FUND-{suffix}",
                "name": "Pilot test funding",
                "amount": 12345,
                "currency": "USD",
                "status": "approved",
            },
        )
        funding = funding_response.json()
        funding_update_response = client.patch(
            f"/api/v1/projects/{project_id}/funding-sources/{funding['id']}",
            headers=headers,
            json={"amount": 14000, "expected_version": funding["version"]},
        )
        funding_stale_response = client.patch(
            f"/api/v1/projects/{project_id}/funding-sources/{funding['id']}",
            headers=headers,
            json={"amount": 15000, "expected_version": funding["version"]},
        )

        cash_flow_response = client.post(
            f"/api/v1/projects/{project_id}/cash-flow",
            headers=headers,
            json={
                "period_label": f"2099-{suffix[:2]}",
                "planned_inflow": 1000,
                "planned_outflow": 700,
                "actual_inflow": 900,
                "actual_outflow": 750,
                "forecast_outflow": 800,
            },
        )
        contract_response = client.post(
            f"/api/v1/projects/{project_id}/contracts",
            headers=headers,
            json={
                "control_account_id": control_account_id,
                "code": f"CON-TEST-{suffix}",
                "title": "Pilot commitment contract",
                "counterparty": "Test Contractor",
                "contract_type": "Services",
                "value": 23000,
                "status": "active",
            },
        )
        contract = contract_response.json()
        purchase_order_response = client.post(
            f"/api/v1/projects/{project_id}/purchase-orders",
            headers=headers,
            json={
                "control_account_id": control_account_id,
                "contract_id": contract["id"],
                "po_number": f"PO-TEST-{suffix}",
                "description": "Pilot purchase order commitment",
                "vendor": "Test Vendor",
                "committed_amount": 7000,
                "status": "issued",
            },
        )
        payment_certificate_response = client.post(
            f"/api/v1/projects/{project_id}/payment-certificates",
            headers=headers,
            json={
                "control_account_id": control_account_id,
                "contract_id": contract["id"],
                "purchase_order_id": purchase_order_response.json()["id"],
                "certificate_no": f"AP-TEST-{suffix}",
                "period_label": "2099-01",
                "certified_amount": 5000,
                "retained_amount": 250,
                "status": "certified",
            },
        )
        summary_response = client.get(f"/api/v1/projects/{project_id}/cost-manager-summary", headers=headers)

    assert funding_response.status_code == 200
    assert funding_update_response.status_code == 200
    assert funding_update_response.json()["version"] == funding["version"] + 1
    assert funding_stale_response.status_code == 409
    assert cash_flow_response.status_code == 200
    assert contract_response.status_code == 200
    assert purchase_order_response.status_code == 200
    assert payment_certificate_response.status_code == 200
    assert summary_response.status_code == 200
    assert summary_response.json()["total_funding"] >= funding_update_response.json()["amount"]
    assert summary_response.json()["total_incurred_from_payment_certificates"] >= payment_certificate_response.json()["certified_amount"]
    assert summary_response.json()["total_contract_commitments"] >= contract_response.json()["value"]
    assert summary_response.json()["total_purchase_order_commitments"] >= purchase_order_response.json()["committed_amount"]


def test_document_control_register_transmittal_mail_and_review() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _first_project_id(client, headers)
        suffix = uuid4().hex[:8]

        document_response = client.post(
            f"/api/v1/projects/{project_id}/documents",
            headers=headers,
            json={
                "document_number": f"DOC-TEST-{suffix}",
                "revision": "A",
                "linked_entity_type": "ControlAccount",
                "linked_entity_id": 1,
                "title": "Pilot controlled test document",
                "doc_type": "Drawing",
                "discipline": "Project Controls",
                "organization": "Pilot Team",
                "status": "current",
                "review_status": "not_started",
                "confidentiality": "project",
                "file_name": f"DOC-TEST-{suffix}.pdf",
                "uri": f"edms://pilot/{suffix}",
            },
        )
        document = document_response.json()
        update_response = client.patch(
            f"/api/v1/projects/{project_id}/documents/{document['id']}",
            headers=headers,
            json={"review_status": "in_review", "expected_version": document["version"]},
        )
        stale_response = client.patch(
            f"/api/v1/projects/{project_id}/documents/{document['id']}",
            headers=headers,
            json={"review_status": "approved", "expected_version": document["version"]},
        )
        review_response = client.post(
            f"/api/v1/projects/{project_id}/documents/{document['id']}/reviews",
            headers=headers,
            json={"reviewer_role": "Project Controls", "review_status": "outstanding", "comments": "Pilot review"},
        )
        transmittal_response = client.post(
            f"/api/v1/projects/{project_id}/document-transmittals",
            headers=headers,
            json={
                "transmittal_no": f"TR-TEST-{suffix}",
                "subject": "Pilot controlled document transmittal",
                "purpose": "for_review",
                "recipient_org": "Owner",
                "recipient_contact": "Document Control",
                "document_ids": [document["id"]],
            },
        )
        mail_response = client.post(
            f"/api/v1/projects/{project_id}/project-mail",
            headers=headers,
            json={
                "mail_no": f"MAIL-TEST-{suffix}",
                "mail_type": "review_comment",
                "subject": "Please review pilot document",
                "to_role": "Project Controls",
                "document_id": document["id"],
                "body": "Controlled review request.",
            },
        )
        dashboard_response = client.get(f"/api/v1/projects/{project_id}/dashboard", headers=headers)

    assert document_response.status_code == 200
    assert update_response.status_code == 200
    assert update_response.json()["version"] == document["version"] + 1
    assert stale_response.status_code == 409
    assert review_response.status_code == 200
    assert transmittal_response.status_code == 200
    assert mail_response.status_code == 200
    assert dashboard_response.json()["document_control_summary"]["transmittals_sent"] >= 1


def test_project_routes_reject_authenticated_non_members() -> None:
    with TestClient(app) as client:
        control_manager_headers = _auth_headers(client)
        projects = client.get("/api/v1/projects", headers=control_manager_headers).json()
        secondary_project = next(project for project in projects if project["code"] == "REF-TURN-002")

        contract_manager_headers = _auth_headers_for(client, "laura.contracts@demo.local")
        response = client.get(f"/api/v1/projects/{secondary_project['id']}/wbs", headers=contract_manager_headers)

    assert response.status_code == 403


def test_collaborative_updates_reject_stale_versions() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _first_project_id(client, headers)
        accounts_response = client.get(f"/api/v1/projects/{project_id}/control-accounts", headers=headers)
        account = accounts_response.json()[0]

        update_response = client.patch(
            f"/api/v1/projects/{project_id}/control-accounts/{account['id']}",
            headers=headers,
            json={"responsible": "Pilot Responsible", "expected_version": account["version"]},
        )
        stale_response = client.patch(
            f"/api/v1/projects/{project_id}/control-accounts/{account['id']}",
            headers=headers,
            json={"responsible": "Stale Responsible", "expected_version": account["version"]},
        )

    assert update_response.status_code == 200
    assert update_response.json()["version"] == account["version"] + 1
    assert stale_response.status_code == 409


def test_control_cycle_job_can_be_enqueued() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        projects_response = client.get("/api/v1/projects", headers=headers)
        project_id = projects_response.json()[0]["id"]
        response = client.post(f"/api/v1/projects/{project_id}/control-cycle/jobs", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["queue"] == "control-core"
    assert payload["task_id"]


def _first_project_id(client: TestClient, headers: dict[str, str]) -> int:
    response = client.get("/api/v1/projects", headers=headers)
    assert response.status_code == 200
    projects = response.json()
    assert projects
    return int(projects[0]["id"])


def _login(client: TestClient):
    return _login_as(client, "ana.control@demo.local")


def _login_as(client: TestClient, email: str):
    return client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "demo123",
            "tenant_slug": "demo-energy",
        },
    )


def _auth_headers(client: TestClient) -> dict[str, str]:
    return _auth_headers_for(client, "ana.control@demo.local")


def _auth_headers_for(client: TestClient, email: str) -> dict[str, str]:
    response = _login_as(client, email)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
