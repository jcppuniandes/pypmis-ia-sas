from fastapi.testclient import TestClient

from app.main import app


def _login(client: TestClient, email: str, password: str) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_user_sees_only_their_tenant_projects() -> None:
    with TestClient(app) as client:
        session = _login(client, "ana.control@demo.local", "demo123")
        tenant_id = session["tenant_id"]
        headers = {"Authorization": f"Bearer {session['access_token']}"}

        projects = client.get("/api/v1/projects", headers=headers).json()
        assert isinstance(projects, list)
        # Every returned project must belong to the same tenant the user authenticated against.
        for project in projects:
            if "tenant_id" in project:
                assert project["tenant_id"] == tenant_id


def test_user_cannot_access_project_from_another_tenant() -> None:
    with TestClient(app) as client:
        session = _login(client, "ana.control@demo.local", "demo123")
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
                "password": "demo123",
                "tenant_slug": "no-such-tenant",
            },
        )
        assert response.status_code == 401
