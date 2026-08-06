"""Compatibility contract for the ADMIN MODE foundation before Nivel 2A extraction."""

from fastapi.testclient import TestClient

from app.main import app


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_configuration_overview_contract_is_stable() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/admin-configuration/overview", headers=_admin_headers(client))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == {"configurations", "workspaces", "module_settings", "summary"}
    assert set(payload["summary"]) == {"published", "drafts", "workspaces", "active_modules"}
    assert payload["configurations"]
    assert {
        "id",
        "kind",
        "code",
        "name",
        "description",
        "status",
        "revision",
        "version",
        "content_json",
        "content_hash",
        "published_at",
        "created_by_user_id",
        "created_at",
        "updated_at",
    } <= set(payload["configurations"][0])
    assert {
        "id",
        "parent_id",
        "workspace_type_code",
        "code",
        "name",
        "status",
        "defaults_json",
        "sort_order",
        "version",
    } == set(payload["workspaces"][0])


def test_admin_configuration_error_contract_is_stable() -> None:
    with TestClient(app) as client:
        headers = _admin_headers(client)
        overview = client.get("/api/v1/admin-configuration/overview", headers=headers).json()
        published = next(item for item in overview["configurations"] if item["status"] == "published")
        response = client.patch(
            f"/api/v1/admin-configuration/configurations/{published['id']}",
            headers=headers,
            json={"name": "Must remain immutable", "expected_version": published["version"]},
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "Published configuration is immutable; clone it to create a draft"}
