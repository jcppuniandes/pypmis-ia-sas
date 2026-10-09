"""Provision real actors only in the disposable Wave 2B browser database."""

from __future__ import annotations

import json
import os

from sqlalchemy import select
from tests.test_basic_data_wave2b import _fixture, _grant, _key, _user
from tests.test_capital_allocation_wave2a import _context
from tests.test_risk_governance_wave2b import _policy

from app.core.security import hash_password
from app.database.seed import ensure_membership, seed_demo
from app.database.session import Base, SessionLocal, engine
from app.domain.models import AdminConfiguration, AuthCredential, Project, UserAccount
from app.modules.risk_governance.service import CONFIGURATION_KIND, RiskGovernanceService


def _credential(db, actor, email, name):
    actor.email, actor.full_name = email, name
    db.add(
        AuthCredential(
            tenant_id=actor.tenant_id,
            user_id=actor.id,
            provider="local",
            password_hash=hash_password("1234"),
            is_active=True,
        )
    )
    db.commit()


def main() -> None:
    if os.getenv("PYPMIS_WAVE2B_BROWSER_FIXTURE") != "disposable-only" or (
        engine.dialect.name != "postgresql" or engine.url.database != "wave2b_browser"
    ):
        raise RuntimeError("Browser fixture is restricted to the disposable wave2b_browser database")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_demo(db)
        if db.scalar(select(UserAccount).where(UserAccount.email == "wave2b.authority@demo.local")):
            print(json.dumps({"database": engine.url.database, "fixture": "reused"}), flush=True)
            return
        fixture = _fixture(db, count=2, fel=True)
        author, authority = fixture["author"], fixture["reviewer"]
        _credential(db, authority, "wave2b.authority@demo.local", "Wave 2B Independent Authority")
        for role in ("configuration_admin", "definition_assessor", "definition_reviewer"):
            _grant(db, authority, role)
        user = _user(db, author.tenant_id, "wave2b-user")
        _credential(db, user, "wave2b.user@demo.local", "Wave 2B Evidence Preparer")
        _grant(db, user, "definition_assessor", workspace_id=fixture["project"].id)
        project = db.scalar(select(Project).where(Project.tenant_id == author.tenant_id).order_by(Project.id))
        if project is None:
            raise RuntimeError("Browser app shell requires an existing demo project")
        ensure_membership(db, author.tenant_id, project.id, authority.id, "Control Manager")
        ensure_membership(db, author.tenant_id, project.id, user.id, "Executive")
        db.commit()
        risk = RiskGovernanceService(db, author.tenant_id, author.id, _context(author, "configuration_admin"))
        risk.ensure_seed()
        template = db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == author.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.code == "default",
                AdminConfiguration.revision == 1,
            )
        )
        draft = risk.clone_configuration(
            template.id, template.version, _key("risk-clone"), target_workspace_id=fixture["enterprise"].id
        )
        draft = risk.update_configuration(
            draft.id,
            draft.version,
            name="Wave 2B governed risk policy",
            description="Disposable browser test policy",
            content=_policy(fixture["enterprise"].id, project_types=["MINING"]),
        )
        RiskGovernanceService(
            db, author.tenant_id, authority.id, _context(authority, "configuration_admin")
        ).publish_configuration(draft.id, draft.version, _key("risk-publish"))
        print(
            json.dumps(
                {
                    "database": engine.url.database,
                    "project_workspace_id": fixture["project"].id,
                    "configuration_id": fixture["configuration"]["id"],
                    "authority_email": authority.email,
                    "user_email": user.email,
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
