from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.domain.models import AuthCredential, Tenant, UserAccount
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


def test_admin_can_manage_user_lifecycle_and_project_access() -> None:
    suffix = uuid4().hex[:8]
    email = f"iam.{suffix}@demo.local"
    first_password = f"Start-{suffix}"
    second_password = f"Reset-{suffix}"

    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _create_project(client, headers)
        create_response = client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "email": email,
                "full_name": "IAM Operator",
                "title": "Initial title",
                "password": first_password,
            },
        )
        assert create_response.status_code == 200
        user_id = create_response.json()["id"]

        assign_response = client.post(
            f"/api/v1/projects/{project_id}/team",
            headers=headers,
            json={"user_id": user_id, "role": "Planner"},
        )
        assert assign_response.status_code == 200
        assert assign_response.json()["membership"]["role"] == "Planner"

        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": first_password, "tenant_slug": "demo-energy"},
        )
        assert login_response.status_code == 200
        user_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}
        visible_projects = client.get("/api/v1/projects", headers=user_headers)
        assert visible_projects.status_code == 200
        assert [project["id"] for project in visible_projects.json()] == [project_id]

        update_response = client.patch(
            f"/api/v1/users/{user_id}",
            headers=headers,
            json={"full_name": "IAM Operator Updated", "title": "Access Coordinator"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["full_name"] == "IAM Operator Updated"
        assert update_response.json()["title"] == "Access Coordinator"

        reset_response = client.post(
            f"/api/v1/users/{user_id}/reset-password",
            headers=headers,
            json={"password": second_password},
        )
        assert reset_response.status_code == 200
        old_login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": first_password, "tenant_slug": "demo-energy"},
        )
        assert old_login.status_code == 401
        new_login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": second_password, "tenant_slug": "demo-energy"},
        )
        assert new_login.status_code == 200

        remove_access = client.delete(f"/api/v1/projects/{project_id}/team/{user_id}", headers=headers)
        assert remove_access.status_code == 200
        user_headers = {"Authorization": f"Bearer {new_login.json()['access_token']}"}
        visible_after_remove = client.get("/api/v1/projects", headers=user_headers)
        assert visible_after_remove.status_code == 200
        assert visible_after_remove.json() == []
        blocked_project = client.get(f"/api/v1/projects/{project_id}/team", headers=user_headers)
        assert blocked_project.status_code == 403

        deactivate_response = client.delete(f"/api/v1/users/{user_id}", headers=headers)
        assert deactivate_response.status_code == 200
        assert deactivate_response.json()["status"] == "inactive"
        inactive_login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": second_password, "tenant_slug": "demo-energy"},
        )
        assert inactive_login.status_code == 401


def test_active_user_can_bootstrap_first_project_for_empty_tenant() -> None:
    suffix = uuid4().hex[:8]
    tenant_slug = f"clean-{suffix}"
    email = f"bootstrap.{suffix}@demo.local"
    password = f"Bootstrap-{suffix}"

    db = SessionLocal()
    try:
        tenant = Tenant(name=f"Clean tenant {suffix}", slug=tenant_slug, base_currency="COP")
        db.add(tenant)
        db.flush()
        user = UserAccount(
            tenant_id=tenant.id,
            email=email,
            full_name="Bootstrap User",
            title="Control Manager",
            status="active",
        )
        db.add(user)
        db.flush()
        db.add(
            AuthCredential(
                tenant_id=tenant.id,
                user_id=user.id,
                provider="local",
                password_hash=hash_password(password),
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password, "tenant_slug": tenant_slug},
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        response = client.post(
            "/api/v1/projects",
            headers=headers,
            json={
                "code": f"CLEAN-{suffix}",
                "name": "Clean first project",
                "phase": "Planning",
                "currency": "USD",
                "calendar_base": "5x8",
                "owner": "Owner",
                "status": "draft",
                "configuration": {"funding_required": True, "control_level": "control_account"},
            },
        )
        projects = client.get("/api/v1/projects", headers=headers)

    assert response.status_code == 200
    assert projects.status_code == 200
    assert [project["code"] for project in projects.json()] == [f"CLEAN-{suffix}"]


def test_control_manager_can_delete_project_from_workspace() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        keep_project_id = _create_project(client, headers)
        delete_project_id = _create_project(client, headers)

        response = client.delete(f"/api/v1/projects/{delete_project_id}", headers=headers)
        projects = client.get("/api/v1/projects", headers=headers)
        deleted_dashboard = client.get(f"/api/v1/projects/{delete_project_id}/dashboard", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "project_id": delete_project_id}
    assert projects.status_code == 200
    project_ids = [project["id"] for project in projects.json()]
    assert keep_project_id in project_ids
    assert delete_project_id not in project_ids
    assert deleted_dashboard.status_code == 404


def test_project_delete_requires_configure_permission() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)
        project_id = _create_project(client, headers)
        planner_response = client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "email": f"planner.{uuid4().hex[:8]}@demo.local",
                "full_name": "Planner User",
                "title": "Planner",
                "password": "1234",
            },
        )
        assert planner_response.status_code == 200
        planner_id = planner_response.json()["id"]
        assign_response = client.post(
            f"/api/v1/projects/{project_id}/team",
            headers=headers,
            json={"user_id": planner_id, "role": "Planner"},
        )
        assert assign_response.status_code == 200
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": planner_response.json()["email"], "password": "1234", "tenant_slug": "demo-energy"},
        )
        assert login_response.status_code == 200
        planner_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        response = client.delete(f"/api/v1/projects/{project_id}", headers=planner_headers)
        projects = client.get("/api/v1/projects", headers=headers)

    assert response.status_code == 403
    assert any(project["id"] == project_id for project in projects.json())


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
