from fastapi.testclient import TestClient

from app.main import app


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_overview_bootstraps_versioned_foundation() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/admin-configuration/overview", headers=_admin_headers(client))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["summary"]["published"] >= 9
    assert {item["code"] for item in payload["configurations"] if item["kind"] == "workspace_type"} >= {
        "portfolio",
        "program",
        "project",
    }
    assert payload["workspaces"][0]["defaults_json"]["currency"] == "COP"


def test_published_configuration_is_immutable_and_cloneable() -> None:
    with TestClient(app) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin-configuration/configurations",
            headers=headers,
            json={
                "kind": "catalog",
                "code": "priority-test",
                "name": "Priority Test",
                "content_json": {"items": [{"code": "high", "label": "High"}]},
            },
        )
        assert created.status_code == 201, created.text
        published = client.post(
            f"/api/v1/admin-configuration/configurations/{created.json()['id']}/publish",
            headers=headers,
        )
        assert published.status_code == 200, published.text
        assert len(published.json()["content_hash"]) == 64

        rejected_update = client.patch(
            f"/api/v1/admin-configuration/configurations/{created.json()['id']}",
            headers=headers,
            json={"name": "Changed"},
        )
        clone = client.post(
            f"/api/v1/admin-configuration/configurations/{created.json()['id']}/clone",
            headers=headers,
        )

    assert rejected_update.status_code == 409
    assert clone.status_code == 201, clone.text
    assert clone.json()["revision"] == 2
    assert clone.json()["status"] == "draft"


def test_workspace_hierarchy_inheritance_and_cycle_guard() -> None:
    with TestClient(app) as client:
        headers = _admin_headers(client)
        overview = client.get("/api/v1/admin-configuration/overview", headers=headers).json()
        root = overview["workspaces"][0]
        program = client.post(
            "/api/v1/admin-configuration/workspaces",
            headers=headers,
            json={
                "code": "program-test",
                "name": "Program Test",
                "workspace_type_code": "program",
                "parent_id": root["id"],
            },
        )
        assert program.status_code == 201, program.text
        project = client.post(
            "/api/v1/admin-configuration/workspaces",
            headers=headers,
            json={
                "code": "project-test",
                "name": "Project Test",
                "workspace_type_code": "project",
                "parent_id": program.json()["id"],
            },
        )
        assert project.status_code == 201, project.text
        updated_defaults = client.put(
            f"/api/v1/admin-configuration/workspaces/{program.json()['id']}/defaults",
            headers=headers,
            json={"values": {"calendar": "5x8", "currency": "USD"}},
        )
        assert updated_defaults.status_code == 200, updated_defaults.text
        effective = client.get(
            f"/api/v1/admin-configuration/workspaces/{project.json()['id']}/effective",
            headers=headers,
        )
        cycle = client.patch(
            f"/api/v1/admin-configuration/workspaces/{program.json()['id']}",
            headers=headers,
            json={"parent_id": project.json()["id"], "expected_version": updated_defaults.json()["version"]},
        )

    assert effective.status_code == 200, effective.text
    assert effective.json()["defaults"]["currency"] == "USD"
    assert effective.json()["defaults"]["timezone"] == "America/Bogota"
    assert cycle.status_code == 409


def test_module_dependencies_and_numbering_sequence() -> None:
    with TestClient(app) as client:
        headers = _admin_headers(client)
        workspace = client.get("/api/v1/admin-configuration/overview", headers=headers).json()["workspaces"][0]
        blocked = client.put(
            f"/api/v1/admin-configuration/workspaces/{workspace['id']}/modules/cost-manager",
            headers=headers,
            json={"enabled": True},
        )
        scope = client.put(
            f"/api/v1/admin-configuration/workspaces/{workspace['id']}/modules/scope-manager",
            headers=headers,
            json={"enabled": True},
        )
        cost = client.put(
            f"/api/v1/admin-configuration/workspaces/{workspace['id']}/modules/cost-manager",
            headers=headers,
            json={"enabled": True},
        )
        first = client.post(
            "/api/v1/admin-configuration/numbering/workspace/next",
            headers=headers,
            json={"scope_key": "test"},
        )
        second = client.post(
            "/api/v1/admin-configuration/numbering/workspace/next",
            headers=headers,
            json={"scope_key": "test"},
        )

    assert blocked.status_code == 409
    assert scope.status_code == 200, scope.text
    assert cost.status_code == 200, cost.text
    assert first.json()["value"] == "WS-0001"
    assert second.json()["value"] == "WS-0002"
