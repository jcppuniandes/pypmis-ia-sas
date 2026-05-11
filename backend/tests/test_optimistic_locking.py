import pytest
from fastapi.testclient import TestClient

from app.main import app


def _login(client: TestClient) -> tuple[str, int]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "ana.control@demo.local", "password": "demo123", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    return data["access_token"], data["tenant_id"]


def test_control_plan_update_rejects_stale_version() -> None:
    with TestClient(app) as client:
        token, _ = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        projects = client.get("/api/v1/projects", headers=headers).json()
        assert projects, "Seed data should include at least one project"
        project_id = projects[0]["id"]

        plan = client.get(f"/api/v1/projects/{project_id}/control-plan", headers=headers)
        if plan.status_code != 200:
            pytest.skip("Control plan endpoint not available for seed project")

        current_version = plan.json()["version"]

        # Correct version — accepted
        ok = client.put(
            f"/api/v1/projects/{project_id}/control-plan",
            headers=headers,
            json={"reporting_cadence": "weekly", "expected_version": current_version},
        )
        assert ok.status_code == 200, ok.text

        # Stale version — rejected with 409
        stale = client.put(
            f"/api/v1/projects/{project_id}/control-plan",
            headers=headers,
            json={"reporting_cadence": "monthly", "expected_version": current_version},
        )
        assert stale.status_code == 409, stale.text


def test_control_plan_update_with_future_version_is_rejected() -> None:
    with TestClient(app) as client:
        token, _ = _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        projects = client.get("/api/v1/projects", headers=headers).json()
        if not projects:
            pytest.skip("No seed projects available")
        project_id = projects[0]["id"]

        plan = client.get(f"/api/v1/projects/{project_id}/control-plan", headers=headers)
        if plan.status_code != 200:
            pytest.skip("Control plan endpoint not available")

        current_version = plan.json()["version"]

        response = client.put(
            f"/api/v1/projects/{project_id}/control-plan",
            headers=headers,
            json={"reporting_cadence": "weekly", "expected_version": current_version + 100},
        )
        assert response.status_code == 409, response.text
