"""Explicit isolated Scope actors; no runtime tenant or implicit GET provisioning."""

from sqlalchemy import select
from tests.operational_context_fixture import create_o1a_fixture, fixture_headers

from app.domain.models import SecurityAccessAssignment, SecurityRole, UserAccount
from app.modules.scope_foundation.permissions import ensure_scope_permissions


def create_scope_fixture(db):
    fixture = create_o1a_fixture(db)
    ensure_scope_permissions(db, fixture.tenant_id, fixture.users["admin"].id)
    ensure_scope_permissions(db, fixture.foreign_tenant.id, fixture.users["foreign"].id)
    for label in ("scope_manager", "bim_manager", "bim_coordinator", "construction_manager", "document_controller"):
        actor = UserAccount(
            tenant_id=fixture.tenant_id,
            email=f"{label}-{fixture.token}@o1ba.test",
            full_name=f"O1B-A {label}",
            status="active",
        )
        db.add(actor)
        db.flush()
        role = db.scalar(
            select(SecurityRole).where(SecurityRole.tenant_id == fixture.tenant_id, SecurityRole.code == label)
        )
        db.add(
            SecurityAccessAssignment(
                tenant_id=fixture.tenant_id,
                subject_type="user",
                user_id=actor.id,
                role_id=role.id,
                scope_type="workspace",
                workspace_id=fixture.project_workspace_id,
                granted_by_user_id=fixture.users["admin"].id,
                status="active",
            )
        )
        fixture.users[label] = actor
    db.commit()
    fixture.headers = {label: fixture_headers(actor) for label, actor in fixture.users.items()}
    return fixture
