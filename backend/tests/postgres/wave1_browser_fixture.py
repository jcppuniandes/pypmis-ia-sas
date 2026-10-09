"""Seed only the enterprise context required by the disposable Wave 1 browser run."""

from __future__ import annotations

from sqlalchemy import select

from app.database.session import SessionLocal
from app.domain.models import EnterpriseWorkspace, UserAccount
from app.modules.enterprise_structure.models import EnterpriseStrategicObjective


def seed_wave1_browser_foundation() -> None:
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        if admin is None:
            raise RuntimeError("The demo administrator must exist before the Wave 1 browser foundation is seeded")

        workspace = db.scalar(
            select(EnterpriseWorkspace)
            .where(
                EnterpriseWorkspace.tenant_id == admin.tenant_id,
                EnterpriseWorkspace.workspace_type_code == "enterprise",
                EnterpriseWorkspace.status == "active",
            )
            .order_by(EnterpriseWorkspace.id)
        )
        if workspace is None:
            workspace = EnterpriseWorkspace(
                tenant_id=admin.tenant_id,
                parent_id=None,
                workspace_type_code="enterprise",
                code="WAVE1-BROWSER-ENTERPRISE",
                external_key="wave1-browser-enterprise",
                record_code="WAVE1.BROWSER.ENTERPRISE",
                name="Wave 1 Browser Capital Owner Enterprise",
                status="active",
                defaults_json={"governance_model": "CAPITAL_OWNER"},
                sort_order=1,
                version=1,
                created_by_user_id=admin.id,
            )
            db.add(workspace)

        objective = db.scalar(
            select(EnterpriseStrategicObjective).where(
                EnterpriseStrategicObjective.tenant_id == admin.tenant_id,
                EnterpriseStrategicObjective.code == "wave1-browser-objective",
            )
        )
        if objective is None:
            db.add(
                EnterpriseStrategicObjective(
                    tenant_id=admin.tenant_id,
                    code="wave1-browser-objective",
                    name="Governed asset integrity and compliance",
                    strategic_line="Strategic Capital Planning",
                    priority="high",
                    horizon="2030",
                    responsible_area="Enterprise Strategy",
                    active=True,
                    description="Disposable strategic objective for real Chromium release validation.",
                    source_release_code="WAVE1-BROWSER",
                    created_by_user_id=admin.id,
                )
            )
        db.commit()


if __name__ == "__main__":
    seed_wave1_browser_foundation()
