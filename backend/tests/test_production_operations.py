from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


def test_project_role_matrix_lists_profiles_members_and_bp_policies() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _create_project(client, headers)
        policy_response = client.post(
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
        response = client.get(f"/api/v1/projects/{project_id}/role-matrix", headers=headers)

    assert policy_response.status_code == 200
    assert response.status_code == 200
    matrix = response.json()
    assert matrix["project_id"] == project_id
    assert matrix["role_count"] >= 10
    control_manager = next(row for row in matrix["entries"] if row["role"] == "Control Manager")
    assert control_manager["permissions"]["can_configure"] is True
    assert control_manager["assigned_user_count"] >= 1
    assert control_manager["assigned_users"][0]["email"] == "ana.control@demo.local"
    assert control_manager["business_process_actions"] == [
        {
            "process_code": "BP-CBS-WBS",
            "action": "approve_baseline",
            "required_role": "Control Manager",
            "permission_key": "can_approve_workflow",
            "status": "active",
        }
    ]
    workface_planner = next(row for row in matrix["entries"] if row["role"] == "Workface Planner")
    assert workface_planner["permissions"]["can_capture_progress"] is True
    assert workface_planner["business_process_actions"] == []


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ana.control@demo.local", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_project(client: TestClient, headers: dict[str, str]) -> int:
    suffix = uuid4().hex[:8]
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "code": f"OPS-{suffix}",
            "name": f"Production ops {suffix}",
            "phase": "Planning",
            "currency": "USD",
            "calendar_base": "5x8 Colombia",
            "owner": "Owner PMO",
            "status": "authorized",
            "configuration": {"funding_required": True, "control_level": "control_account"},
        },
    )
    assert response.status_code == 200
    return response.json()["id"]
