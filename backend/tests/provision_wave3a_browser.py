"""Provision only the disposable PostgreSQL database for real Chromium tests."""

from __future__ import annotations

import json
import os

from sqlalchemy import select
from tests.test_portfolio_review_wave3a import _assign, _fixture

from app.core.security import hash_password
from app.database.seed import ensure_membership, seed_demo
from app.database.session import Base, SessionLocal, engine
from app.domain.models import AuthCredential, Project, UserAccount


def ensure_authority_project_access(db, authority: UserAccount) -> None:
    """Expose the normal app shell without granting ADMIN configuration rights."""
    if os.getenv("PYPMIS_WAVE3A_BROWSER_FIXTURE") != "disposable-only" or (
        engine.dialect.name != "postgresql" or engine.url.database != "wave3a_browser"
    ):
        raise RuntimeError("Project access is restricted to the disposable Wave 3A browser fixture")
    if authority.email != "wave3a.authority@demo.local":
        raise RuntimeError("Project access is restricted to the Wave 3A browser authority")
    project = db.scalar(select(Project).where(Project.tenant_id == authority.tenant_id).order_by(Project.id))
    if project is None:
        raise RuntimeError("The browser authority requires an existing seeded Project")
    ensure_membership(db, authority.tenant_id, project.id, authority.id, "Executive")
    db.commit()


def main() -> None:
    if os.getenv("PYPMIS_WAVE3A_BROWSER_FIXTURE") != "disposable-only" or (
        engine.dialect.name != "postgresql" or engine.url.database != "wave3a_browser"
    ):
        raise RuntimeError("Browser fixture is restricted to the disposable wave3a_browser database")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_demo(db)
        existing = db.scalar(select(UserAccount).where(UserAccount.email == "wave3a.authority@demo.local"))
        if existing is not None:
            ensure_authority_project_access(db, existing)
            print(json.dumps({"database": engine.url.database, "fixture": "reused"}), flush=True)
            return
        fixture = _fixture(db)
        author, authority = fixture["author"], fixture["authority"]
        authority.email = "wave3a.authority@demo.local"
        authority.full_name = "Wave 3A Portfolio Authority"
        db.add(
            AuthCredential(
                tenant_id=authority.tenant_id,
                user_id=authority.id,
                provider="local",
                password_hash=hash_password("1234"),
                is_active=True,
            )
        )
        db.commit()
        _assign(db, author, authority, "portfolio_review_authority")
        ensure_authority_project_access(db, authority)
        print(
            json.dumps(
                {
                    "database": engine.url.database,
                    "portfolio_workspace_id": fixture["portfolio"].id,
                    "allocation_plan_id": fixture["plan"].id,
                    "planning_cycle_id": fixture["cycle"].id,
                    "authority_email": authority.email,
                    "authority_user_id": authority.id,
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
