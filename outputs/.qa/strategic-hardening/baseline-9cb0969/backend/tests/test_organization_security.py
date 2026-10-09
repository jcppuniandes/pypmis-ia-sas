from fastapi.testclient import TestClient

from app.main import app


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_overview_bootstraps_level_one_security_catalog() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/organization-security/overview", headers=_admin_headers(client))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["organization"]["code"] == "DEMO_ENERGY"
    assert {item["key"] for item in payload["permissions"]} >= {
        "organization.read",
        "group.manage",
        "role.manage",
        "access.manage",
    }
    assert {item["code"] for item in payload["roles"]} >= {
        "organization_admin",
        "security_admin",
        "user_manager",
        "auditor",
        "viewer",
    }
    assert any(item["role_code"] == "organization_admin" for item in payload["assignments"])


def test_organization_unit_tree_rejects_cycles() -> None:
    with TestClient(app) as client:
        headers = _admin_headers(client)
        parent = client.post(
            "/api/v1/organization-security/units",
            headers=headers,
            json={"code": "OPS", "name": "Operations", "unit_type": "division"},
        )
        assert parent.status_code == 201, parent.text
        child = client.post(
            "/api/v1/organization-security/units",
            headers=headers,
            json={
                "code": "OPS-CO",
                "name": "Colombia Operations",
                "unit_type": "department",
                "parent_id": parent.json()["id"],
            },
        )
        assert child.status_code == 201, child.text

        cycle = client.patch(
            f"/api/v1/organization-security/units/{parent.json()['id']}",
            headers=headers,
            json={"parent_id": child.json()["id"], "expected_version": parent.json()["version"]},
        )

    assert cycle.status_code == 409
    assert "cycle" in cycle.text.lower()


def test_group_role_assignment_effective_access_and_revoke() -> None:
    with TestClient(app) as client:
        headers = _admin_headers(client)
        overview = client.get("/api/v1/organization-security/overview", headers=headers).json()
        user = overview["users"][0]
        viewer_role = next(item for item in overview["roles"] if item["code"] == "viewer")

        group = client.post(
            "/api/v1/organization-security/groups",
            headers=headers,
            json={"code": "AUDIT-READERS", "name": "Audit Readers", "description": "Read-only reviewers"},
        )
        assert group.status_code == 201, group.text
        member = client.post(
            f"/api/v1/organization-security/groups/{group.json()['id']}/members/{user['id']}",
            headers=headers,
        )
        assert member.status_code == 200, member.text
        assert user["id"] in member.json()["member_ids"]

        assignment = client.post(
            "/api/v1/organization-security/assignments",
            headers=headers,
            json={
                "subject_type": "group",
                "subject_id": group.json()["id"],
                "role_id": viewer_role["id"],
                "scope_type": "organization",
            },
        )
        assert assignment.status_code == 201, assignment.text
        effective = client.get(
            f"/api/v1/organization-security/effective/{user['id']}",
            headers=headers,
        )
        assert effective.status_code == 200, effective.text
        assert "organization.read" in effective.json()["permission_keys"]
        assert any(item["subject_type"] == "group" for item in effective.json()["assignments"])

        revoked = client.delete(
            f"/api/v1/organization-security/assignments/{assignment.json()['id']}",
            headers=headers,
        )

    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == "revoked"


def test_tenant_scoping_rejects_unknown_records() -> None:
    with TestClient(app) as client:
        headers = _admin_headers(client)
        response = client.post(
            "/api/v1/organization-security/groups/999999/members/999999",
            headers=headers,
        )

    assert response.status_code == 404
