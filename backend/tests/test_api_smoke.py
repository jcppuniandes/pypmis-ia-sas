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
