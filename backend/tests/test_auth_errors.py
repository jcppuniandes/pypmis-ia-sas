from fastapi.testclient import TestClient

from app.main import app


def test_missing_token_returns_401() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/projects")
    assert response.status_code == 401


def test_malformed_token_returns_401() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/projects", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401


def test_wrong_secret_token_returns_401() -> None:
    from datetime import timedelta

    from app.core.security import create_access_token

    token, _ = create_access_token(
        claims={"sub": 1, "tenant_id": 1, "email": "ana.control@demo.local"},
        secret_key="totally-different-secret-key-not-the-real-one",
        expires_delta=timedelta(minutes=5),
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_expired_token_returns_401() -> None:
    from datetime import timedelta

    from app.core.config import get_settings
    from app.core.security import create_access_token

    settings = get_settings()
    token, _ = create_access_token(
        claims={"sub": 1, "tenant_id": 1, "email": "ana.control@demo.local"},
        secret_key=settings.auth_secret_key,
        expires_delta=timedelta(seconds=-1),
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_login_rejects_unknown_credentials() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "wrong", "tenant_slug": "demo-energy"},
        )
    assert response.status_code == 401


def test_login_rejects_wrong_password() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "ana.control@demo.local", "password": "wrong-password", "tenant_slug": "demo-energy"},
        )
    assert response.status_code == 401


def test_accessing_nonexistent_project_returns_403_or_404() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "ana.control@demo.local", "password": "demo123", "tenant_slug": "demo-energy"},
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]

        response = client.get(
            "/api/v1/projects/99999/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code in (403, 404)
