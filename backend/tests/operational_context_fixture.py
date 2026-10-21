"""Isolated O1A fixture factory shared by PostgreSQL tests and Chromium UAT.

Rows represent existing canonical lifecycle states; this factory does not claim
to exercise Project Creation or activation. Their real-flow regression suites
are run separately. No runtime tenant, reserved Project 14 or source is reused.
"""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import create_access_token
from app.domain.models import EnterpriseWorkspace, Project, SecurityAccessAssignment, SecurityRole, Tenant, UserAccount
from app.modules.operational_context.permissions import ensure_operational_permissions


def fixture_headers(user):
    token, _ = create_access_token(
        {"sub": str(user.id), "tenant_id": user.tenant_id, "email": user.email},
        get_settings().auth_secret_key,
        timedelta(hours=4),
    )
    return {"Authorization": f"Bearer {token}"}


def create_o1a_fixture(db, suffix=None):
    token = suffix or uuid4().hex[:12]
    tenant = Tenant(name=f"O1A Foundation {token}", slug=f"o1a-{token}")
    foreign_tenant = Tenant(name=f"O1A Foreign {token}", slug=f"o1a-foreign-{token}")
    db.add_all([tenant, foreign_tenant])
    db.flush()
    actors = {}
    role_codes = {
        "admin": "organization_admin",
        "publisher": "organization_admin",
        "manager": "project_controls_manager",
        "second_manager": "project_manager",
        "planner": "planner_scheduler",
        "cost_controller": "cost_controller",
        "progress_engineer": "progress_engineer",
        "executive": "executive_viewer",
        "project_admin": "project_administrator",
        "unassigned": None,
        "foreign": "operational_administrator",
    }
    for label in role_codes:
        actor = UserAccount(
            tenant_id=foreign_tenant.id if label == "foreign" else tenant.id,
            email=f"{label}-{token}@o1a.test",
            full_name=f"O1A {label.replace('_', ' ').title()}",
            status="active",
        )
        db.add(actor)
        db.flush()
        actors[label] = actor
    ensure_operational_permissions(db, tenant.id, actors["admin"].id)
    ensure_operational_permissions(db, foreign_tenant.id, actors["foreign"].id)
    root_id = 100_000_000 + uuid4().int % 100_000_000
    workspaces = {}
    for offset, label in enumerate(("direct", "contractor", "owner", "inactive", "other_project", "foreign")):
        governance = (
            "CONTRACTOR_DELIVERY"
            if label == "contractor"
            else "CAPITAL_OWNER"
            if label == "owner"
            else "DIRECT_INTERNAL"
        )
        source = {
            "authorization_reference": f"INT-{token}",
            "sponsor": "Isolated Internal Sponsor",
            "authorization_approved": True,
            "basic_scope": "O1A Foundation fixture",
            "authorization_effective_date": "2026-10-01",
        }
        if label == "contractor":
            source = {
                "client": "Isolated Client",
                "contract_number": f"CTR-{token}",
                "contractual_scope": "Delivery foundation",
                "mobilization_authorized": True,
                "notice_to_proceed_date": "2026-10-01",
            }
        if label == "owner":
            source = {}  # Owner intentionally starts blocked; genuine FID fixture is separate.
        row = EnterpriseWorkspace(
            id=root_id + offset,
            tenant_id=foreign_tenant.id if label == "foreign" else tenant.id,
            workspace_type_code="project",
            code=f"O1A-{label}-{token}",
            external_key=f"O1A-{label}-{token}",
            record_code=f"O1A.{token}.{offset}",
            name=f"O1A {label.title()} {token}",
            status="pending" if label == "inactive" else "active",
            version=1,
            created_by_user_id=actors["foreign"].id if label == "foreign" else actors["admin"].id,
            defaults_json={
                "_project": {"governance_model": governance, "project_type": "CONSTRUCTION", "source_snapshot": source}
            },
        )
        db.add(row)
        db.flush()
        workspaces[label] = row
    roles = {row.code: row for row in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant.id))}
    foreign_role = db.scalar(
        select(SecurityRole).where(
            SecurityRole.tenant_id == foreign_tenant.id, SecurityRole.code == "operational_administrator"
        )
    )
    for label, code in role_codes.items():
        if code is None:
            continue
        organization = label in {"admin", "publisher", "foreign"}
        role = foreign_role if label == "foreign" else roles[code]
        db.add(
            SecurityAccessAssignment(
                tenant_id=actors[label].tenant_id,
                subject_type="user",
                user_id=actors[label].id,
                role_id=role.id,
                scope_type="organization" if organization else "workspace",
                workspace_id=None if organization else workspaces["direct"].id,
                granted_by_user_id=actors["foreign"].id if label == "foreign" else actors["admin"].id,
                status="active",
            )
        )
    legacy_id = 1_000_000 + uuid4().int % 50_000_000
    legacy = {}
    for offset, label in enumerate(("primary", "second", "foreign", "superseded")):
        row = Project(
            id=legacy_id + offset,
            tenant_id=foreign_tenant.id if label == "foreign" else tenant.id,
            code=f"LEG-{label}-{token}",
            name=f"Legacy O1A {label}",
            status="superseded" if label == "superseded" else "draft",
            configuration={},
        )
        db.add(row)
        db.flush()
        legacy[label] = row
    db.commit()
    return SimpleNamespace(
        token=token,
        tenant=tenant,
        tenant_id=tenant.id,
        foreign_tenant=foreign_tenant,
        users=actors,
        workspaces=workspaces,
        legacy=legacy,
        project_workspace_id=workspaces["direct"].id,
        legacy_project_id=legacy["primary"].id,
        headers={label: fixture_headers(actor) for label, actor in actors.items()},
    )
