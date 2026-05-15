from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.control_audit_agent import ControlAuditAgentService, FindingDraft


def test_unifier_priority_flow_covers_bp_sov_commitment_funding_and_recost() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_ready_project(client, headers, suffix)
        activity_sheet = _load_activity_sheet(client, headers, project_id)
        activity_sheet_id = activity_sheet["id"]

        account = client.get(f"/api/v1/projects/{project_id}/control-accounts", headers=headers).json()[0]
        wbs_rows = client.get(f"/api/v1/projects/{project_id}/wbs", headers=headers).json()
        wbs = next(row for row in wbs_rows if row["id"] == account["wbs_id"])
        cbs = client.post(
            f"/api/v1/projects/{project_id}/cbs",
            headers=headers,
            json={
                "code": "CBS-PLT-CIV-A100",
                "level": 3,
                "cost_category": "Civil",
                "description": "Imported activity CBS",
                "status": "active",
            },
        ).json()
        fbs = client.post(
            f"/api/v1/projects/{project_id}/fbs",
            headers=headers,
            json={
                "code": f"FBS-OWN-{suffix}",
                "source_of_funds": "Owner equity",
                "funding_type": "AFE",
                "authorization_ref": f"AFE-{suffix}",
                "approved_amount": 10_000,
                "currency": "USD",
                "status": "approved",
            },
        ).json()

        bp_fund_response = client.post(
            f"/api/v1/projects/{project_id}/business-processes/cbs-fund",
            headers=headers,
            json={
                "title": "Funding allocation by CBS",
                "line_items": [
                    {
                        "cbs_id": cbs["id"],
                        "funding_source_id": fbs["id"],
                        "control_account_id": account["id"],
                        "amount": 4_000,
                        "description": "Allocate owner funding to civil CBS",
                    }
                ],
            },
        )
        overfund_response = client.post(
            f"/api/v1/projects/{project_id}/business-processes/cbs-fund",
            headers=headers,
            json={
                "title": "Invalid overfund",
                "line_items": [
                    {
                        "cbs_id": cbs["id"],
                        "funding_source_id": fbs["id"],
                        "control_account_id": account["id"],
                        "amount": 99_000,
                    }
                ],
            },
        )
        bp_wbs_response = client.post(
            f"/api/v1/projects/{project_id}/business-processes/cbs-wbs",
            headers=headers,
            json={
                "title": "Budget by WBS and CBS",
                "line_items": [
                    {
                        "wbs_id": wbs["id"],
                        "cbs_id": cbs["id"],
                        "funding_source_id": fbs["id"],
                        "control_account_id": account["id"],
                        "amount": 2_500,
                        "quantity": 25,
                        "description": "Scope-cost transaction",
                    }
                ],
            },
        )
        cost_codes_response = client.get(f"/api/v1/projects/{project_id}/cost-codes", headers=headers)

        contract = client.post(
            f"/api/v1/projects/{project_id}/contracts",
            headers=headers,
            json={
                "funding_source_id": fbs["id"],
                "control_account_id": account["id"],
                "code": f"CTR-{suffix}",
                "title": "Civil works contract",
                "counterparty": "Civil Contractor",
                "contract_type": "Construction",
                "value": 1_500,
                "status": "active",
            },
        ).json()
        invalid_sov_response = client.post(
            f"/api/v1/projects/{project_id}/contracts/{contract['id']}/sov-lines",
            headers=headers,
            json={"line_no": "10", "description": "Missing CBS", "amount": 500},
        )
        sov_response = client.post(
            f"/api/v1/projects/{project_id}/contracts/{contract['id']}/sov-lines",
            headers=headers,
            json={
                "line_no": "10",
                "description": "Concrete foundations",
                "amount": 500,
                "cbs_id": cbs["id"],
                "wbs_id": wbs["id"],
                "control_account_id": account["id"],
            },
        )
        funding_line_response = client.post(
            f"/api/v1/projects/{project_id}/commitment-funding-lines",
            headers=headers,
            json={
                "contract_id": contract["id"],
                "sov_line_id": sov_response.json()["id"],
                "funding_source_id": fbs["id"],
                "amount": 500,
            },
        )

        rate_sheet_response = client.post(
            f"/api/v1/projects/{project_id}/rate-sheets",
            headers=headers,
            json={
                "code": f"RS-{suffix}",
                "name": "Controlled rate sheet",
                "status": "active",
                "line_items": [{"cbs_code": "CBS-PLT-CIV-A100", "multiplier": 1.2, "unit_rate": 120}],
            },
        )
        recost_response = client.post(
            f"/api/v1/projects/{project_id}/activity-sheets/{activity_sheet_id}/recost",
            headers=headers,
            json={"rate_sheet_id": rate_sheet_response.json()["id"]},
        )
        rows_response = client.get(
            f"/api/v1/projects/{project_id}/activity-sheets/{activity_sheet_id}/rows",
            headers=headers,
        )
        reconciliation_response = client.get(f"/api/v1/projects/{project_id}/reconciliation-report", headers=headers)

    assert bp_fund_response.status_code == 200
    assert bp_fund_response.json()["process_code"] == "BP-CBS-FUND"
    assert overfund_response.status_code == 409
    assert "funding" in overfund_response.text.lower()
    assert bp_wbs_response.status_code == 200
    assert bp_wbs_response.json()["process_code"] == "BP-CBS-WBS"
    assert any(item["cbs_id"] == cbs["id"] and item["budget"] == 2_500 for item in cost_codes_response.json())
    assert invalid_sov_response.status_code == 400
    assert "CBS" in invalid_sov_response.text
    assert sov_response.status_code == 200
    assert sov_response.json()["cbs_id"] == cbs["id"]
    assert funding_line_response.status_code == 200
    assert funding_line_response.json()["amount"] == 500
    assert rate_sheet_response.status_code == 200
    assert recost_response.status_code == 200
    assert recost_response.json()["updated_rows"] == 1
    assert rows_response.json()[0]["planned_cost"] == 3_000
    assert rows_response.json()[0]["planned_value"] == 1_500
    assert reconciliation_response.status_code == 200
    assert reconciliation_response.json()["rows"][0]["wbs_code"] == wbs["code"]


def test_unifier_hardening_covers_policies_versioned_lines_exports_and_recost_history() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_ready_project(client, headers, suffix)
        activity_sheet = _load_activity_sheet(client, headers, project_id)
        account = client.get(f"/api/v1/projects/{project_id}/control-accounts", headers=headers).json()[0]
        wbs_rows = client.get(f"/api/v1/projects/{project_id}/wbs", headers=headers).json()
        wbs = next(row for row in wbs_rows if row["id"] == account["wbs_id"])
        cbs = client.post(
            f"/api/v1/projects/{project_id}/cbs",
            headers=headers,
            json={
                "code": f"CBS-PLT-CIV-A100-{suffix}",
                "level": 3,
                "cost_category": "Civil",
                "description": "Hardening CBS",
                "status": "active",
            },
        ).json()
        fbs = client.post(
            f"/api/v1/projects/{project_id}/fbs",
            headers=headers,
            json={
                "code": f"FBS-HARD-{suffix}",
                "source_of_funds": "Owner equity",
                "funding_type": "AFE",
                "authorization_ref": f"AFE-HARD-{suffix}",
                "approved_amount": 10_000,
                "currency": "USD",
                "status": "approved",
            },
        ).json()
        bp_response = client.post(
            f"/api/v1/projects/{project_id}/business-processes/cbs-wbs",
            headers=headers,
            json={
                "title": "Hardening BP",
                "line_items": [
                    {
                        "wbs_id": wbs["id"],
                        "cbs_id": cbs["id"],
                        "funding_source_id": fbs["id"],
                        "control_account_id": account["id"],
                        "amount": 2_500,
                        "quantity": 25,
                        "description": "Initial controlled line",
                    }
                ],
            },
        )
        bp = bp_response.json()
        line_items_response = client.get(
            f"/api/v1/projects/{project_id}/business-processes/{bp['id']}/line-items",
            headers=headers,
        )
        line = line_items_response.json()[0]
        stale_edit_response = client.patch(
            f"/api/v1/projects/{project_id}/business-process-line-items/{line['id']}",
            headers=headers,
            json={"amount": 2_600, "description": "Stale edit", "expected_version": line["version"] - 1},
        )
        edit_response = client.patch(
            f"/api/v1/projects/{project_id}/business-process-line-items/{line['id']}",
            headers=headers,
            json={"amount": 2_750, "description": "Approved edit", "expected_version": line["version"]},
        )
        revisions_response = client.get(
            f"/api/v1/projects/{project_id}/business-process-line-items/{line['id']}/revisions",
            headers=headers,
        )

        restrictive_policy = client.post(
            f"/api/v1/projects/{project_id}/business-process-policies",
            headers=headers,
            json={
                "process_code": "BP-CBS-WBS",
                "action": "approve_baseline",
                "required_role": "Contract Manager",
                "permission_key": "can_approve_workflow",
                "status": "active",
            },
        )
        denied_approval = client.post(
            f"/api/v1/projects/{project_id}/workflow-instances/{bp['id']}/actions",
            headers=headers,
            json={"action": "approve_baseline", "expected_version": bp["version"]},
        )
        permissive_policy = client.post(
            f"/api/v1/projects/{project_id}/business-process-policies",
            headers=headers,
            json={
                "process_code": "BP-CBS-WBS",
                "action": "approve_baseline",
                "required_role": "Control Manager",
                "permission_key": "can_approve_workflow",
                "status": "active",
            },
        )
        approved = client.post(
            f"/api/v1/projects/{project_id}/workflow-instances/{bp['id']}/actions",
            headers=headers,
            json={"action": "approve_baseline", "expected_version": bp["version"]},
        )

        rate_sheet = client.post(
            f"/api/v1/projects/{project_id}/rate-sheets",
            headers=headers,
            json={
                "code": f"RS-HARD-{suffix}",
                "name": "Hardening rate sheet",
                "status": "active",
                "line_items": [{"cbs_code": "CBS-PLT-CIV-A100", "multiplier": 1.1, "unit_rate": 100}],
            },
        ).json()
        recost_response = client.post(
            f"/api/v1/projects/{project_id}/activity-sheets/{activity_sheet['id']}/recost",
            headers=headers,
            json={"rate_sheet_id": rate_sheet["id"]},
        )
        recost_runs_response = client.get(
            f"/api/v1/projects/{project_id}/activity-sheets/{activity_sheet['id']}/recost-runs",
            headers=headers,
        )
        xlsx_export = client.get(
            f"/api/v1/projects/{project_id}/reconciliation-report/export?format=xlsx",
            headers=headers,
        )
        pdf_export = client.get(
            f"/api/v1/projects/{project_id}/reconciliation-report/export?format=pdf",
            headers=headers,
        )

    assert bp_response.status_code == 200
    assert line_items_response.status_code == 200
    assert line["amount"] == 2_500
    assert line["version"] == 1
    assert stale_edit_response.status_code == 409
    assert edit_response.status_code == 200
    assert edit_response.json()["amount"] == 2_750
    assert edit_response.json()["version"] == 2
    assert revisions_response.status_code == 200
    assert revisions_response.json()[0]["previous_amount"] == 2_500
    assert restrictive_policy.status_code == 200
    assert denied_approval.status_code == 403
    assert permissive_policy.status_code == 200
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert recost_response.status_code == 200
    assert recost_runs_response.status_code == 200
    assert recost_runs_response.json()[0]["updated_rows"] == 1
    assert xlsx_export.status_code == 200
    assert xlsx_export.content.startswith(b"PK")
    assert pdf_export.status_code == 200
    assert pdf_export.content.startswith(b"%PDF")


def test_control_audit_agent_flags_missing_bp_policy_and_pending_recost() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_ready_project(client, headers, suffix)
        _load_activity_sheet(client, headers, project_id)
        account = client.get(f"/api/v1/projects/{project_id}/control-accounts", headers=headers).json()[0]
        wbs_rows = client.get(f"/api/v1/projects/{project_id}/wbs", headers=headers).json()
        wbs = next(row for row in wbs_rows if row["id"] == account["wbs_id"])
        cbs = client.post(
            f"/api/v1/projects/{project_id}/cbs",
            headers=headers,
            json={
                "code": f"CBS-AUD-{suffix}",
                "level": 3,
                "cost_category": "Civil",
                "description": "Audit agent CBS",
                "status": "active",
            },
        ).json()
        fbs = client.post(
            f"/api/v1/projects/{project_id}/fbs",
            headers=headers,
            json={
                "code": f"FBS-AUD-{suffix}",
                "source_of_funds": "Owner equity",
                "funding_type": "AFE",
                "authorization_ref": f"AFE-AUD-{suffix}",
                "approved_amount": 10_000,
                "currency": "USD",
                "status": "approved",
            },
        ).json()
        client.post(
            f"/api/v1/projects/{project_id}/business-processes/cbs-wbs",
            headers=headers,
            json={
                "title": "Audited BP without configured policy",
                "line_items": [
                    {
                        "wbs_id": wbs["id"],
                        "cbs_id": cbs["id"],
                        "funding_source_id": fbs["id"],
                        "control_account_id": account["id"],
                        "amount": 2_500,
                        "quantity": 25,
                        "description": "Line pending policy audit",
                    }
                ],
            },
        )
        client.post(
            f"/api/v1/projects/{project_id}/rate-sheets",
            headers=headers,
            json={
                "code": f"RS-AUD-{suffix}",
                "name": "Audit rate sheet",
                "status": "active",
                "line_items": [{"cbs_code": cbs["code"], "multiplier": 1.05, "unit_rate": 100}],
            },
        )

        run_response = client.post(f"/api/v1/projects/{project_id}/agents/control-audit/run", headers=headers)
        history_response = client.get(f"/api/v1/projects/{project_id}/agents/control-audit/runs", headers=headers)

    assert run_response.status_code == 200
    run = run_response.json()
    assert run["agent_code"] == "control_audit"
    assert run["status"] == "completed"
    assert run["score"] < 100
    categories = {finding["category"] for finding in run["findings"]}
    assert "bp_policy" in categories
    assert "recost" in categories
    assert history_response.status_code == 200
    assert history_response.json()[0]["id"] == run["id"]


def test_control_audit_agent_creates_awp_draft_packages_from_control_accounts() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        suffix = uuid4().hex[:8]
        project_id = _create_ready_project(client, headers, suffix)
        _load_activity_sheet(client, headers, project_id)
        before_packages = client.get(f"/api/v1/projects/{project_id}/work-packages", headers=headers).json()
        before_ids = {package["id"] for package in before_packages}

        run_response = client.post(
            f"/api/v1/projects/{project_id}/agents/control-audit/awp-draft-packages",
            headers=headers,
        )
        after_packages_response = client.get(f"/api/v1/projects/{project_id}/work-packages", headers=headers)
        constraints_response = client.get(f"/api/v1/projects/{project_id}/work-package-constraints", headers=headers)
        repeat_response = client.post(
            f"/api/v1/projects/{project_id}/agents/control-audit/awp-draft-packages",
            headers=headers,
        )
        final_packages_response = client.get(f"/api/v1/projects/{project_id}/work-packages", headers=headers)

    assert run_response.status_code == 200
    run = run_response.json()
    assert run["agent_code"] == "control_audit"
    assert run["status"] == "completed"
    assert "draft AWP" in run["summary"]
    assert "Senior AWP Packaging Advisor" in run["summary"]
    categories = {finding["category"] for finding in run["findings"]}
    assert "awp_packaging" in categories
    assert after_packages_response.status_code == 200
    after_packages = after_packages_response.json()
    created_packages = [package for package in after_packages if package["id"] not in before_ids]
    created_types = {package["package_type"] for package in created_packages}
    assert {"CWA", "CWP", "IWP"} <= created_types
    assert all(package["readiness_status"] == "constraint_review" for package in created_packages)
    cwp_ids = {package["id"] for package in created_packages if package["package_type"] == "CWP"}
    assert any(package["package_type"] == "IWP" and package["parent_id"] in cwp_ids for package in created_packages)
    assert constraints_response.status_code == 200
    constraints = constraints_response.json()
    assert any(constraint["constraint_type"] == "Engineering Documents" for constraint in constraints)
    assert any(constraint["constraint_type"] == "Materials" for constraint in constraints)
    assert repeat_response.status_code == 200
    assert len(final_packages_response.json()) == len(after_packages)


def test_control_audit_agent_appends_optional_low_cost_synthesis() -> None:
    settings = SimpleNamespace(
        ai_provider="claude",
        anthropic_api_key="sk-ant-test",
        ai_model="claude-haiku-4-5-20251001",
        ai_max_tokens=256,
        ai_timeout_seconds=15,
    )
    service = ControlAuditAgentService(MagicMock(), settings=settings)
    findings = [
        FindingDraft(
            severity="high",
            category="bp_policy",
            title="BP-CBS-WBS approval policy is not configured",
            evidence="Missing active approve_baseline policy.",
            recommendation="Configure BP Permissions.",
            owner_role="Control Manager",
        )
    ]

    with patch("app.services.control_audit_agent.generate_control_agent_synthesis", return_value="Close BP policy first."):
        summary = service._summary_with_optional_synthesis("Control Audit Agent found 1 finding.", findings)

    assert "Control Audit Agent found 1 finding." in summary
    assert "Model synthesis: Close BP policy first." in summary


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
            "code": f"UNI-{suffix}",
            "name": "Unifier priority project",
            "phase": "Planning",
            "currency": "USD",
            "calendar_base": "5x8 Colombia",
            "owner": "Owner PMO",
            "status": "authorized",
            "authorization_ref": f"AFE-UNI-{suffix}",
        },
    )
    assert response.status_code == 200
    project_id = response.json()["id"]
    setup_response = client.put(
        f"/api/v1/projects/{project_id}/operational-setup",
        headers=headers,
        json={
            "project_number": f"UNI-{suffix}",
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
