"""HTTP boundary coverage for Wave 1 ADMIN and USER responsibilities."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.domain.models import (
    AuthCredential,
    SecurityAccessAssignment,
    SecurityRole,
    UserAccount,
)
from app.main import app


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _actor_with_role(role_code: str, label: str) -> str:
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        assert admin is not None
        role = db.scalar(
            select(SecurityRole).where(
                SecurityRole.tenant_id == admin.tenant_id,
                SecurityRole.code == role_code,
            )
        )
        assert role is not None, f"Wave 1 role {role_code} was not installed"
        email = f"wave1-http-{label}-{uuid4().hex[:8]}@demo.local"
        actor = UserAccount(
            tenant_id=admin.tenant_id,
            email=email,
            full_name=f"Wave 1 {label}",
            title=label,
            status="active",
        )
        db.add(actor)
        db.flush()
        db.add_all(
            [
                AuthCredential(
                    tenant_id=admin.tenant_id,
                    user_id=actor.id,
                    provider="local",
                    password_hash=hash_password("1234"),
                    is_active=True,
                ),
                SecurityAccessAssignment(
                    tenant_id=admin.tenant_id,
                    subject_type="user",
                    user_id=actor.id,
                    group_id=None,
                    role_id=role.id,
                    scope_type="organization",
                    status="active",
                    granted_by_user_id=admin.id,
                ),
            ]
        )
        db.commit()
        return email


def test_wave1_http_routes_enforce_admin_user_separation() -> None:
    with TestClient(app) as client:
        admin_headers = _login(client, "admin")
        # Installs the Wave 1 permission and role catalog without creating live records.
        seeded = client.get("/api/v1/capital-planning/options", headers=admin_headers)
        assert seeded.status_code == 200, seeded.text

        author_headers = _login(client, _actor_with_role("capital_planning_author", "author"))
        assert client.get("/api/v1/capital-planning/options", headers=author_headers).status_code == 200
        denied_admin = client.get(
            "/api/v1/capital-planning/admin/configurations",
            headers=author_headers,
        )
        assert denied_admin.status_code == 403, denied_admin.text

        config_headers = _login(
            client,
            _actor_with_role("capital_planning_config_admin", "configuration-administrator"),
        )
        allowed_admin = client.get(
            "/api/v1/capital-planning/admin/configurations",
            headers=config_headers,
        )
        assert allowed_admin.status_code == 200, allowed_admin.text
        denied_live_mutation = client.post(
            "/api/v1/capital-planning/demands",
            headers={**config_headers, "Idempotency-Key": f"wave1-denied-{uuid4()}"},
            json={
                "name": "Denied configuration-only demand",
                "description": "Must be rejected before any USER transaction mutates state.",
                "planning_cycle_id": 1,
                "theme_codes": [],
                "strategic_objective_codes": [],
                "business_or_asset_need": "Validate direct-route role separation.",
                "strategic_driver": "governance",
                "target_horizon": "near-term",
                "sponsor_user_id": 1,
                "owning_workspace_id": 1,
                "assumptions": [],
                "constraints": [],
                "dependencies": [],
            },
        )
        assert denied_live_mutation.status_code == 403, denied_live_mutation.text
