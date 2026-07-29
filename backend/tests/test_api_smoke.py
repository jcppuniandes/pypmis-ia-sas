import hashlib
import json
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app

SECURE_PROD_SECRET = "s" * 64


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-Id"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_liveness_and_metrics_are_available() -> None:
    with TestClient(app) as client:
        live_response = client.get("/api/v1/health/live")
        metrics_response = client.get("/api/v1/ops/metrics")

    assert live_response.status_code == 200
    assert live_response.json()["status"] == "live"
    assert metrics_response.status_code == 200
    assert "pypmis_http_requests_total" in metrics_response.text


def test_production_settings_reject_insecure_defaults() -> None:
    settings = Settings(
        app_environment="production",
        auth_secret_key="change-me-before-production",
        allowed_hosts="pypmis.example.com,localhost,127.0.0.1",
        cors_origins="https://pypmis.example.com",
        docs_enabled=False,
    )

    with pytest.raises(RuntimeError, match="AUTH_SECRET_KEY"):
        settings.validate_for_runtime()


def test_production_settings_require_explicit_hosts_and_closed_docs() -> None:
    settings = Settings(
        app_environment="production",
        auth_secret_key=SECURE_PROD_SECRET,
        allowed_hosts="*",
        cors_origins="https://pypmis.example.com",
        docs_enabled=True,
    )

    with pytest.raises(RuntimeError, match="ALLOWED_HOSTS"):
        settings.validate_for_runtime()


def test_production_settings_require_oidc_metadata_when_enabled() -> None:
    settings = Settings(
        app_environment="production",
        auth_secret_key=SECURE_PROD_SECRET,
        allowed_hosts="pypmis.example.com",
        cors_origins="https://pypmis.example.com",
        docs_enabled=False,
        oidc_enabled=True,
        oidc_issuer_url="",
        oidc_client_id="",
    )

    with pytest.raises(RuntimeError, match="OIDC_ISSUER_URL"):
        settings.validate_for_runtime()


def test_production_settings_reject_auto_create_schema() -> None:
    settings = Settings(
        app_environment="production",
        auth_secret_key=SECURE_PROD_SECRET,
        allowed_hosts="pypmis.example.com",
        cors_origins="https://pypmis.example.com",
        docs_enabled=False,
        auto_create_schema=True,
    )

    with pytest.raises(RuntimeError, match="AUTO_CREATE_SCHEMA"):
        settings.validate_for_runtime()


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
        providers_response = client.get("/api/v1/auth/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["user"]["email"] == "admin@demo.local"
    assert payload["user"]["full_name"] == "Pypmis Admin"
    assert providers_response.status_code == 200
    assert providers_response.json()["local"]["enabled"] is True
    assert providers_response.json()["oidc"]["enabled"] is False


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
                "period_label": f"2099-{suffix}",
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
                "funding_source_id": funding["id"],
                "control_account_id": control_account_id,
                "code": f"CON-TEST-{suffix}",
                "title": "Pilot commitment contract",
                "counterparty": "Test Contractor",
                "contract_type": "Services",
                "value": 6000,
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
        warehouse_receipt_response = client.post(
            f"/api/v1/projects/{project_id}/warehouse-receipts",
            headers=headers,
            json={
                "control_account_id": control_account_id,
                "contract_id": contract["id"],
                "purchase_order_id": purchase_order_response.json()["id"],
                "receipt_no": f"GRN-TEST-{suffix}",
                "description": "Pilot warehouse receipt",
                "received_quantity": 2,
                "unit_cost": 875,
                "received_value": 1750,
                "status": "accepted",
            },
        )
        rfq_response = client.post(
            f"/api/v1/projects/{project_id}/rfq-packages",
            headers=headers,
            json={
                "control_account_id": control_account_id,
                "package_no": f"RFQ-TEST-{suffix}",
                "title": "Pilot RFQ package",
                "scope_summary": "Bid package for pilot validation.",
                "procurement_method": "RFQ",
                "status": "issued",
                "budget_amount": 20000,
            },
        )
        rfq_bid_response = client.post(
            f"/api/v1/projects/{project_id}/rfq-packages/{rfq_response.json()['id']}/bids",
            headers=headers,
            json={
                "bidder_name": f"Pilot Bidder {suffix}",
                "bid_amount": 18500,
                "technical_score": 86,
                "commercial_score": 90,
                "schedule_score": 78,
                "risk_score": 82,
                "status": "received",
            },
        )
        summary_response = client.get(f"/api/v1/projects/{project_id}/cost-manager-summary", headers=headers)
        dashboard_response = client.get(f"/api/v1/projects/{project_id}/dashboard", headers=headers)

    assert funding_response.status_code == 200
    assert funding_update_response.status_code == 200
    assert funding_update_response.json()["version"] == funding["version"] + 1
    assert funding_stale_response.status_code == 409
    assert cash_flow_response.status_code == 200
    assert contract_response.status_code == 200
    assert purchase_order_response.status_code == 200
    assert payment_certificate_response.status_code == 200
    assert warehouse_receipt_response.status_code == 200
    assert rfq_response.status_code == 200
    assert rfq_bid_response.status_code == 200
    assert summary_response.status_code == 200
    assert dashboard_response.status_code == 200
    assert summary_response.json()["total_funding"] >= funding_update_response.json()["amount"]
    assert (
        summary_response.json()["total_incurred_from_payment_certificates"]
        >= payment_certificate_response.json()["certified_amount"]
    )
    assert (
        summary_response.json()["total_incurred_from_warehouse_receipts"]
        >= warehouse_receipt_response.json()["received_value"]
    )
    assert summary_response.json()["total_contract_commitments"] >= contract_response.json()["value"]
    assert (
        summary_response.json()["total_purchase_order_commitments"]
        >= purchase_order_response.json()["committed_amount"]
    )
    assert dashboard_response.json()["rfq_summary"]["bids_received"] >= 1


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
        attachment_response = client.post(
            f"/api/v1/projects/{project_id}/documents/{document['id']}/attachments",
            headers=headers,
            files={"file": (f"DOC-TEST-{suffix}.pdf", b"%PDF-1.4\npilot evidence\n", "application/pdf")},
        )
        zip_payload = BytesIO()
        with ZipFile(zip_payload, "w") as archive:
            archive.writestr(f"daily-report-{suffix}.txt", "field report")
            archive.writestr(f"schedule-fragment-{suffix}.xml", "<Project />")
        zip_response = client.post(
            f"/api/v1/projects/{project_id}/documents/{document['id']}/attachments",
            headers=headers,
            files={"file": (f"DOC-TEST-{suffix}.zip", zip_payload.getvalue(), "application/zip")},
        )
        download_response = client.get(
            f"/api/v1/projects/{project_id}/documents/{document['id']}/attachments/{attachment_response.json()[0]['id']}/download",
            headers=headers,
        )
        dashboard_response = client.get(f"/api/v1/projects/{project_id}/dashboard", headers=headers)

    assert document_response.status_code == 200
    assert update_response.status_code == 200
    assert update_response.json()["version"] == document["version"] + 1
    assert stale_response.status_code == 409
    assert review_response.status_code == 200
    assert transmittal_response.status_code == 200
    assert mail_response.status_code == 200
    assert attachment_response.status_code == 200
    assert attachment_response.json()[0]["sha256"]
    assert attachment_response.json()[0]["scan_status"] == "clean"
    assert zip_response.status_code == 200
    assert len(zip_response.json()) == 2
    assert download_response.status_code == 200
    assert download_response.content.startswith(b"%PDF")
    assert dashboard_response.json()["document_control_summary"]["transmittals_sent"] >= 1
    assert len(dashboard_response.json()["document_attachments"]) >= 3


def test_document_attachment_upload_rejects_unsafe_payloads() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _first_project_id(client, headers)
        suffix = uuid4().hex[:8]

        document_response = client.post(
            f"/api/v1/projects/{project_id}/documents",
            headers=headers,
            json={
                "document_number": f"DOC-SAFE-{suffix}",
                "revision": "A",
                "linked_entity_type": "ControlAccount",
                "linked_entity_id": 1,
                "title": "Pilot unsafe upload guard document",
                "doc_type": "Evidence",
                "discipline": "Project Controls",
                "organization": "Pilot Team",
                "status": "current",
                "review_status": "not_started",
                "confidentiality": "project",
                "file_name": f"DOC-SAFE-{suffix}.pdf",
                "uri": f"edms://pilot/safe/{suffix}",
            },
        )
        document = document_response.json()
        executable_response = client.post(
            f"/api/v1/projects/{project_id}/documents/{document['id']}/attachments",
            headers=headers,
            files={"file": (f"malware-{suffix}.exe", b"MZ", "application/octet-stream")},
        )

        unsafe_zip_payload = BytesIO()
        with ZipFile(unsafe_zip_payload, "w") as archive:
            archive.writestr("../escape.txt", "unsafe path")
        unsafe_zip_response = client.post(
            f"/api/v1/projects/{project_id}/documents/{document['id']}/attachments",
            headers=headers,
            files={"file": (f"unsafe-path-{suffix}.zip", unsafe_zip_payload.getvalue(), "application/zip")},
        )

        inner_zip_payload = BytesIO()
        with ZipFile(inner_zip_payload, "w") as archive:
            archive.writestr("inner.txt", "nested")
        nested_zip_payload = BytesIO()
        with ZipFile(nested_zip_payload, "w") as archive:
            archive.writestr("nested.zip", inner_zip_payload.getvalue())
        nested_zip_response = client.post(
            f"/api/v1/projects/{project_id}/documents/{document['id']}/attachments",
            headers=headers,
            files={"file": (f"nested-{suffix}.zip", nested_zip_payload.getvalue(), "application/zip")},
        )
        eicar_response = client.post(
            f"/api/v1/projects/{project_id}/documents/{document['id']}/attachments",
            headers=headers,
            files={
                "file": (
                    f"eicar-{suffix}.txt",
                    b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!",
                    "text/plain",
                )
            },
        )

    assert document_response.status_code == 200
    assert executable_response.status_code == 400
    assert "not allowed" in executable_response.json()["detail"]
    assert unsafe_zip_response.status_code == 400
    assert "Unsafe ZIP member path" in unsafe_zip_response.json()["detail"]
    assert nested_zip_response.status_code == 400
    assert "Nested ZIP" in nested_zip_response.json()["detail"]
    assert eicar_response.status_code == 400
    assert "failed antivirus scan" in eicar_response.json()["detail"]


def test_document_attachments_reject_non_member_access() -> None:
    with TestClient(app) as client:
        control_manager_headers = _auth_headers(client)
        projects = client.get("/api/v1/projects", headers=control_manager_headers).json()
        secondary_project = next(project for project in projects if project["code"] == "REF-TURN-002")
        suffix = uuid4().hex[:8]

        document_response = client.post(
            f"/api/v1/projects/{secondary_project['id']}/documents",
            headers=control_manager_headers,
            json={
                "document_number": f"DOC-SEC-{suffix}",
                "revision": "A",
                "linked_entity_type": "ControlAccount",
                "linked_entity_id": 1,
                "title": "Pilot member boundary document",
                "doc_type": "Evidence",
                "discipline": "Project Controls",
                "organization": "Pilot Team",
                "status": "current",
                "review_status": "not_started",
                "confidentiality": "project",
                "file_name": f"DOC-SEC-{suffix}.pdf",
                "uri": f"edms://pilot/member-boundary/{suffix}",
            },
        )
        document = document_response.json()
        attachment_response = client.post(
            f"/api/v1/projects/{secondary_project['id']}/documents/{document['id']}/attachments",
            headers=control_manager_headers,
            files={"file": (f"DOC-SEC-{suffix}.pdf", b"%PDF-1.4\nrestricted evidence\n", "application/pdf")},
        )
        attachment = attachment_response.json()[0]

        non_member_headers = _auth_headers_for(client, "laura.contracts@demo.local")
        list_response = client.get(
            f"/api/v1/projects/{secondary_project['id']}/document-attachments",
            headers=non_member_headers,
        )
        download_response = client.get(
            f"/api/v1/projects/{secondary_project['id']}/documents/{document['id']}/attachments/{attachment['id']}/download",
            headers=non_member_headers,
        )
        anonymous_download_response = client.get(
            f"/api/v1/projects/{secondary_project['id']}/documents/{document['id']}/attachments/{attachment['id']}/download",
        )

    assert document_response.status_code == 200
    assert attachment_response.status_code == 200
    assert list_response.status_code == 403
    assert download_response.status_code == 403
    assert anonymous_download_response.status_code == 401


def test_restricted_document_attachments_require_privileged_role() -> None:
    with TestClient(app) as client:
        control_manager_headers = _auth_headers(client)
        project_id = _first_project_id(client, control_manager_headers)
        suffix = uuid4().hex[:8]

        document_response = client.post(
            f"/api/v1/projects/{project_id}/documents",
            headers=control_manager_headers,
            json={
                "document_number": f"DOC-REST-{suffix}",
                "revision": "A",
                "linked_entity_type": "ControlAccount",
                "linked_entity_id": 1,
                "title": "Pilot restricted document",
                "doc_type": "Evidence",
                "discipline": "Project Controls",
                "organization": "Pilot Team",
                "status": "current",
                "review_status": "not_started",
                "confidentiality": "restricted",
                "file_name": f"DOC-REST-{suffix}.pdf",
                "uri": f"edms://pilot/restricted/{suffix}",
            },
        )
        document = document_response.json()
        attachment_response = client.post(
            f"/api/v1/projects/{project_id}/documents/{document['id']}/attachments",
            headers=control_manager_headers,
            files={"file": (f"DOC-REST-{suffix}.pdf", b"%PDF-1.4\nrestricted\n", "application/pdf")},
        )
        attachment = attachment_response.json()[0]

        executive_headers = _auth_headers_for(client, "direccion@demo.local")
        executive_project_list_response = client.get(
            f"/api/v1/projects/{project_id}/document-attachments",
            headers=executive_headers,
        )
        executive_document_list_response = client.get(
            f"/api/v1/projects/{project_id}/documents/{document['id']}/attachments",
            headers=executive_headers,
        )
        executive_download_response = client.get(
            f"/api/v1/projects/{project_id}/documents/{document['id']}/attachments/{attachment['id']}/download",
            headers=executive_headers,
        )
        executive_dashboard_response = client.get(f"/api/v1/projects/{project_id}/dashboard", headers=executive_headers)

    assert document_response.status_code == 200
    assert attachment_response.status_code == 200
    assert executive_project_list_response.status_code == 200
    assert all(item["document_id"] != document["id"] for item in executive_project_list_response.json())
    assert executive_document_list_response.status_code == 403
    assert executive_download_response.status_code == 403
    assert executive_dashboard_response.status_code == 200
    assert all(item["id"] != document["id"] for item in executive_dashboard_response.json()["documents"])
    assert all(
        item["document_id"] != document["id"] for item in executive_dashboard_response.json()["document_attachments"]
    )


def test_project_audit_logs_are_queryable_and_membership_scoped() -> None:
    with TestClient(app) as client:
        control_manager_headers = _auth_headers(client)
        projects = client.get("/api/v1/projects", headers=control_manager_headers).json()
        primary_project = next(project for project in projects if project["code"] == "CTRL-DEMO-001")
        secondary_project = next(project for project in projects if project["code"] == "REF-TURN-002")
        suffix = uuid4().hex[:8]

        funding_response = client.post(
            f"/api/v1/projects/{primary_project['id']}/funding-sources",
            headers=control_manager_headers,
            json={
                "code": f"AUDIT-FUND-{suffix}",
                "name": "Audit trail pilot funding",
                "amount": 1000,
                "currency": "USD",
                "status": "approved",
            },
        )
        audit_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/audit-logs?limit=5",
            headers=control_manager_headers,
        )

        non_member_headers = _auth_headers_for(client, "laura.contracts@demo.local")
        restricted_audit_response = client.get(
            f"/api/v1/projects/{secondary_project['id']}/audit-logs",
            headers=non_member_headers,
        )
        anonymous_audit_response = client.get(f"/api/v1/projects/{primary_project['id']}/audit-logs")

    assert funding_response.status_code == 200
    assert audit_response.status_code == 200
    assert len(audit_response.json()) >= 1
    assert audit_response.json()[0]["action"] == "create_funding_source"
    assert restricted_audit_response.status_code == 403
    assert anonymous_audit_response.status_code == 401


def test_integration_manifest_and_exports_are_read_only_and_membership_scoped() -> None:
    with TestClient(app) as client:
        control_manager_headers = _auth_headers(client)
        projects = client.get("/api/v1/projects", headers=control_manager_headers).json()
        primary_project = next(project for project in projects if project["code"] == "CTRL-DEMO-001")
        secondary_project = next(project for project in projects if project["code"] == "REF-TURN-002")

        manifest_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-manifest",
            headers=control_manager_headers,
        )
        csv_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-export?dataset=cost_sheet&format=csv",
            headers=control_manager_headers,
        )
        json_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-export?dataset=document_attachments&format=json",
            headers=control_manager_headers,
        )
        package_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-package?datasets=cost_sheet,documents&format=both",
            headers=control_manager_headers,
        )
        workbook_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-workbook?datasets=cost_sheet,documents",
            headers=control_manager_headers,
        )
        token_create_response = client.post(
            f"/api/v1/projects/{primary_project['id']}/integration-tokens",
            headers=control_manager_headers,
            json={
                "name": "Smoke BI export token",
                "datasets": ["cost_sheet", "documents"],
                "formats": ["json", "csv", "both", "xlsx"],
                "expires_in_days": 7,
            },
        )
        integration_headers = {"Authorization": f"Bearer {token_create_response.json()['token']}"}
        token_manifest_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-manifest",
            headers=integration_headers,
        )
        token_package_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-package?datasets=cost_sheet,documents&format=both",
            headers=integration_headers,
        )
        token_workbook_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-workbook?datasets=cost_sheet,documents",
            headers=integration_headers,
        )
        token_forbidden_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-export?dataset=funding_sources&format=json",
            headers=integration_headers,
        )
        token_list_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-tokens",
            headers=control_manager_headers,
        )
        token_alerts_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-token-alerts?warning_days=14",
            headers=control_manager_headers,
        )
        token_revoke_response = client.post(
            f"/api/v1/projects/{primary_project['id']}/integration-tokens/{token_create_response.json()['id']}/revoke",
            headers=control_manager_headers,
        )
        revoked_token_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-export?dataset=cost_sheet&format=csv",
            headers=integration_headers,
        )
        downloads_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-downloads?limit=20",
            headers=control_manager_headers,
        )
        invalid_dataset_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-export?dataset=unknown&format=json",
            headers=control_manager_headers,
        )
        invalid_format_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-export?dataset=cost_sheet&format=xlsx",
            headers=control_manager_headers,
        )
        invalid_package_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-package?datasets=unknown&format=both",
            headers=control_manager_headers,
        )
        invalid_workbook_response = client.get(
            f"/api/v1/projects/{primary_project['id']}/integration-workbook?datasets=unknown",
            headers=control_manager_headers,
        )

        non_member_headers = _auth_headers_for(client, "laura.contracts@demo.local")
        restricted_manifest_response = client.get(
            f"/api/v1/projects/{secondary_project['id']}/integration-manifest",
            headers=non_member_headers,
        )
        restricted_export_response = client.get(
            f"/api/v1/projects/{secondary_project['id']}/integration-export?dataset=cost_sheet&format=csv",
            headers=non_member_headers,
        )
        restricted_package_response = client.get(
            f"/api/v1/projects/{secondary_project['id']}/integration-package?datasets=cost_sheet&format=csv",
            headers=non_member_headers,
        )
        restricted_workbook_response = client.get(
            f"/api/v1/projects/{secondary_project['id']}/integration-workbook?datasets=cost_sheet",
            headers=non_member_headers,
        )
        restricted_downloads_response = client.get(
            f"/api/v1/projects/{secondary_project['id']}/integration-downloads",
            headers=non_member_headers,
        )
        restricted_alerts_response = client.get(
            f"/api/v1/projects/{secondary_project['id']}/integration-token-alerts",
            headers=non_member_headers,
        )

    assert manifest_response.status_code == 200
    manifest = manifest_response.json()
    assert manifest["project"]["code"] == "CTRL-DEMO-001"
    dataset_keys = {dataset["key"] for dataset in manifest["datasets"]}
    assert {"cost_sheet", "documents", "document_attachments", "control_account_mappings"} <= dataset_keys
    assert next(dataset for dataset in manifest["datasets"] if dataset["key"] == "cost_sheet")["row_count"] >= 1
    assert csv_response.status_code == 200
    assert "control_account_code" in csv_response.text
    assert json_response.status_code == 200
    assert json_response.json()["dataset"] == "document_attachments"
    assert isinstance(json_response.json()["rows"], list)
    assert package_response.status_code == 200
    assert package_response.headers["x-package-sha256"] == hashlib.sha256(package_response.content).hexdigest()
    with ZipFile(BytesIO(package_response.content)) as archive:
        names = set(archive.namelist())
        assert "package_manifest.json" in names
        assert "datasets/cost_sheet.csv" in names
        assert "datasets/cost_sheet.json" in names
        assert "datasets/documents.csv" in names
        package_manifest = json.loads(archive.read("package_manifest.json"))
        cost_csv = archive.read("datasets/cost_sheet.csv")
    assert package_manifest["mode"] == "read_only"
    assert package_manifest["format"] == "both"
    assert {dataset["key"] for dataset in package_manifest["datasets"]} == {"cost_sheet", "documents"}
    assert any(file["sha256"] == hashlib.sha256(cost_csv).hexdigest() for file in package_manifest["files"])
    assert workbook_response.status_code == 200
    assert workbook_response.headers["x-workbook-sha256"] == hashlib.sha256(workbook_response.content).hexdigest()
    with ZipFile(BytesIO(workbook_response.content)) as workbook:
        workbook_names = set(workbook.namelist())
        assert "xl/workbook.xml" in workbook_names
        assert "xl/worksheets/sheet1.xml" in workbook_names
        assert "xl/worksheets/sheet2.xml" in workbook_names
        workbook_xml = workbook.read("xl/workbook.xml").decode("utf-8")
        summary_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "Summary" in workbook_xml
    assert "cost_sheet" in workbook_xml
    assert "control_account_code" in summary_xml
    assert token_create_response.status_code == 200
    created_token = token_create_response.json()
    assert created_token["token"].startswith("pypmis_it_")
    assert created_token["token_prefix"]
    assert created_token["datasets"] == ["cost_sheet", "documents"]
    assert "xlsx" in created_token["formats"]
    assert token_manifest_response.status_code == 200
    assert {dataset["key"] for dataset in token_manifest_response.json()["datasets"]} == {"cost_sheet", "documents"}
    assert token_package_response.status_code == 200
    assert (
        token_package_response.headers["x-package-sha256"] == hashlib.sha256(token_package_response.content).hexdigest()
    )
    assert token_workbook_response.status_code == 200
    assert (
        token_workbook_response.headers["x-workbook-sha256"]
        == hashlib.sha256(token_workbook_response.content).hexdigest()
    )
    assert token_forbidden_response.status_code == 403
    assert token_list_response.status_code == 200
    assert any(token["id"] == created_token["id"] for token in token_list_response.json())
    assert token_alerts_response.status_code == 200
    token_alerts = token_alerts_response.json()
    assert token_alerts["project_id"] == primary_project["id"]
    assert token_alerts["warning_days"] == 14
    assert token_alerts["expiring_count"] >= 1
    assert any(
        alert["id"] == created_token["id"] and alert["severity"] == "warning" and alert["days_to_expiry"] <= 14
        for alert in token_alerts["alerts"]
    )
    assert token_revoke_response.status_code == 200
    assert token_revoke_response.json()["status"] == "revoked"
    assert revoked_token_response.status_code == 401
    assert downloads_response.status_code == 200
    downloads = downloads_response.json()
    assert len(downloads) >= 4
    artifact_types = {download["artifact_type"] for download in downloads}
    assert {"export", "package", "workbook"} <= artifact_types
    assert any(download["file_name"].endswith(".xlsx") and download["sha256"] for download in downloads)
    assert any(download["integration_token_id"] == created_token["id"] for download in downloads)
    assert invalid_dataset_response.status_code == 400
    assert invalid_format_response.status_code == 400
    assert invalid_package_response.status_code == 400
    assert invalid_workbook_response.status_code == 400
    assert restricted_manifest_response.status_code == 403
    assert restricted_export_response.status_code == 403
    assert restricted_package_response.status_code == 403
    assert restricted_workbook_response.status_code == 403
    assert restricted_downloads_response.status_code == 403
    assert restricted_alerts_response.status_code == 403


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


def test_awp_minimum_register_supports_taxonomy_governance_and_evidence() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _first_project_id(client, headers)
        suffix = uuid4().hex[:8]
        wbs_response = client.get(f"/api/v1/projects/{project_id}/wbs", headers=headers)
        wbs_id = wbs_response.json()[0]["id"]

        account_response = client.post(
            f"/api/v1/projects/{project_id}/control-accounts",
            headers=headers,
            json={
                "wbs_id": wbs_id,
                "code": f"CA-AWP-{suffix}",
                "name": "AWP minimum governance account",
                "responsible": "Project Controls",
                "discipline": "Construction",
                "cbs_code": f"CBS-AWP-{suffix}",
                "contract_ref": "CTR-AWP-01",
                "measurement_rule": "Physical percent by released IWP quantities.",
                "lifecycle_status": "active",
                "risk_ref": "R-AWP-01",
            },
        )
        account = account_response.json()

        cwa_response = client.post(
            f"/api/v1/projects/{project_id}/work-packages",
            headers=headers,
            json={
                "package_type": "CWA",
                "code": f"CWA-{suffix}",
                "title": "AWP test construction area",
                "path_of_construction": "Area release before workface packaging.",
                "release_required_on": "2026-06-01",
            },
        )
        cwa = cwa_response.json()
        cwp_response = client.post(
            f"/api/v1/projects/{project_id}/work-packages",
            headers=headers,
            json={
                "control_account_id": account["id"],
                "parent_id": cwa["id"],
                "package_type": "CWP",
                "code": f"CWP-{suffix}",
                "title": "AWP test construction work package",
                "path_of_construction": "Construction sequence for IWP release.",
                "release_required_on": "2026-06-08",
            },
        )
        cwp = cwp_response.json()
        twp_response = client.post(
            f"/api/v1/projects/{project_id}/work-packages",
            headers=headers,
            json={
                "control_account_id": account["id"],
                "parent_id": cwp["id"],
                "package_type": "TWP",
                "code": f"TWP-{suffix}",
                "title": "AWP test technical package",
                "path_of_construction": "Technical turnover before closeout.",
                "release_required_on": "2026-06-15",
            },
        )
        top_response = client.post(
            f"/api/v1/projects/{project_id}/work-packages",
            headers=headers,
            json={
                "control_account_id": account["id"],
                "parent_id": cwp["id"],
                "package_type": "TOP",
                "code": f"TOP-{suffix}",
                "title": "AWP test turnover package",
                "path_of_construction": "Turnover evidence package.",
                "release_required_on": "2026-06-20",
            },
        )
        invalid_parent_response = client.post(
            f"/api/v1/projects/{project_id}/work-packages",
            headers=headers,
            json={
                "parent_id": cwp["id"],
                "package_type": "CWA",
                "code": f"CWA-BAD-{suffix}",
                "title": "Invalid child area",
                "path_of_construction": "Invalid hierarchy.",
            },
        )

        constraint_response = client.post(
            f"/api/v1/projects/{project_id}/work-packages/{cwp['id']}/constraints",
            headers=headers,
            json={
                "constraint_type": "Document",
                "description": "Approved IFC drawing must be linked before workface release.",
                "owner_role": "Document Control",
                "required_by": "2026-06-05",
                "priority": "high",
                "evidence_ref": "DOC-AWP-IFC-001",
                "closure_note": "",
                "blocking": True,
            },
        )
        constraint = constraint_response.json()
        close_response = client.patch(
            f"/api/v1/projects/{project_id}/work-packages/{cwp['id']}/constraints/{constraint['id']}",
            headers=headers,
            json={
                "status": "closed",
                "evidence_ref": "DOC-AWP-IFC-001 Rev B",
                "closure_note": "IFC drawing approved and linked to package.",
                "expected_version": constraint["version"],
            },
        )
        dashboard_response = client.get(f"/api/v1/projects/{project_id}/dashboard", headers=headers)

    assert account_response.status_code == 200
    assert account["cbs_code"] == f"CBS-AWP-{suffix}"
    assert account["contract_ref"] == "CTR-AWP-01"
    assert account["measurement_rule"].startswith("Physical percent")
    assert account["lifecycle_status"] == "active"
    assert account["risk_ref"] == "R-AWP-01"
    assert cwa_response.status_code == 200
    assert cwp_response.status_code == 200
    assert twp_response.status_code == 200
    assert twp_response.json()["package_type"] == "TWP"
    assert top_response.status_code == 200
    assert top_response.json()["package_type"] == "TOP"
    assert top_response.json()["release_required_on"] == "2026-06-20"
    assert invalid_parent_response.status_code == 400
    assert constraint_response.status_code == 200
    assert constraint["priority"] == "high"
    assert constraint["evidence_ref"] == "DOC-AWP-IFC-001"
    assert close_response.status_code == 200
    assert close_response.json()["status"] == "closed"
    assert close_response.json()["closed_on"] is not None
    assert close_response.json()["closed_by"] == "Ana Martinez"
    assert close_response.json()["closure_note"] == "IFC drawing approved and linked to package."
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["awp_summary"]["twp_count"] >= 1
    assert dashboard_response.json()["awp_summary"]["top_count"] >= 1
    assert dashboard_response.json()["awp_summary"]["closure_evidence_count"] >= 1


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
    return _login_as(client, "admin")


def _login_as(client: TestClient, email: str):
    return client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "1234",
            "tenant_slug": "demo-energy",
        },
    )


def _auth_headers(client: TestClient) -> dict[str, str]:
    return _auth_headers_for(client, "ana.control@demo.local")


def _auth_headers_for(client: TestClient, email: str) -> dict[str, str]:
    response = _login_as(client, email)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
