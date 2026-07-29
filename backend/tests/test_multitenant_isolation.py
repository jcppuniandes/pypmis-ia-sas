from fastapi.testclient import TestClient

from app.main import app


def _login(client: TestClient, email: str, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_user_sees_only_their_assigned_projects() -> None:
    with TestClient(app) as client:
        admin_session = _login(client, "admin", "1234")
        control_headers = {"Authorization": f"Bearer {admin_session['access_token']}"}
        all_visible_projects = client.get("/api/v1/projects", headers=control_headers).json()

        session = _login(client, "laura.contracts@demo.local", "1234")
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        projects = client.get("/api/v1/projects", headers=headers).json()
        laura_project_ids = {project["id"] for project in projects}
        restricted_project = next(project for project in all_visible_projects if project["id"] not in laura_project_ids)
        restricted_dashboard = client.get(f"/api/v1/projects/{restricted_project['id']}/dashboard", headers=headers)

        assert isinstance(projects, list)
        assert all(project["id"] != restricted_project["id"] for project in projects)
        assert restricted_dashboard.status_code == 403


def test_user_cannot_access_project_from_another_tenant() -> None:
    with TestClient(app) as client:
        session = _login(client, "ana.control@demo.local", "1234")
        headers = {"Authorization": f"Bearer {session['access_token']}"}

        # Project IDs in the billions are guaranteed to not exist in any tenant.
        response = client.get("/api/v1/projects/999999999/dashboard", headers=headers)
        assert response.status_code in (403, 404)


def test_login_rejects_user_from_wrong_tenant_slug() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "ana.control@demo.local",
                "password": "1234",
                "tenant_slug": "no-such-tenant",
            },
        )
        assert response.status_code == 401
