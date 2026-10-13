"""Narrow existing-tenant engine permission provisioning without live evidence."""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from tests import test_owner_capability_bootstrap as baseline
from tests.test_qra_bootstrap import TABLE_MODELS

from app.bootstrap_qra_engine import QRA_ENGINE_PERMISSION_KEYS, provision_qra_engine
from app.database.session import Base
from app.domain.models import PermissionCatalog, SecurityRolePermission
from app.modules.enterprise_structure.permissions import PROJECT_DEFINITION_ROLE_PERMISSIONS


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[model.__table__ for model in TABLE_MODELS])
    with Session(engine) as session:
        yield session
    engine.dispose()


def _snapshot(db):
    return {model.__tablename__: baseline._rows(db, model) for model in TABLE_MODELS}


def test_engine_provision_only_new_permissions_existing_roles_and_idempotent_audit(db):
    tenant, actor = baseline._tenant(db)
    codes = set(PROJECT_DEFINITION_ROLE_PERMISSIONS) | {"organization_admin", "configuration_admin", "custom_role"}
    roles = {code: baseline._role(db, tenant, code) for code in sorted(codes)}
    db.commit()
    before = _snapshot(db)
    result = provision_qra_engine(db, tenant.id, actor.id)
    assert result["permission_entries_added"] == len(QRA_ENGINE_PERMISSION_KEYS) == 6
    assert result["configuration_changes"] == result["live_runs_created"] == 0
    assert result["roles_created"] == result["assignments_created"] == 0
    for code, role in roles.items():
        actual = set(
            db.scalars(
                select(PermissionCatalog.key)
                .join(SecurityRolePermission, SecurityRolePermission.permission_id == PermissionCatalog.id)
                .where(SecurityRolePermission.role_id == role.id, PermissionCatalog.key.in_(QRA_ENGINE_PERMISSION_KEYS))
            )
        )
        expected = (
            QRA_ENGINE_PERMISSION_KEYS
            if code == "organization_admin"
            else PROJECT_DEFINITION_ROLE_PERMISSIONS.get(code, frozenset()) & QRA_ENGINE_PERMISSION_KEYS
        )
        assert actual == expected
    after = _snapshot(db)
    assert all(
        before[name] == values
        for name, values in after.items()
        if name not in {"permission_catalog", "security_role_permissions", "security_events"}
    )
    again = provision_qra_engine(db, tenant.id, actor.id)
    assert again["permission_entries_added"] == again["role_grants_added"] == 0
    assert _snapshot(db) == after


@pytest.mark.parametrize(
    "scenario", ["empty-tenant", "workspace-only", "missing-tenant", "foreign-user", "inactive-user"]
)
def test_engine_provision_without_tenant_authority_has_no_writes(db, scenario):
    tenant, actor = baseline._tenant(db, can_configure=False, with_project=scenario != "empty-tenant")
    selected_tenant = tenant.id
    if scenario == "workspace-only":
        baseline._existing_authority(db, tenant, actor, scope="workspace")
    elif scenario == "missing-tenant":
        selected_tenant += 100
    elif scenario == "foreign-user":
        from app.domain.models import Tenant

        other = Tenant(name="Other", slug="other-engine")
        db.add(other)
        db.flush()
        selected_tenant = other.id
    elif scenario == "inactive-user":
        actor.status = "inactive"
    db.commit()
    before = _snapshot(db)
    with pytest.raises(HTTPException) as failure:
        provision_qra_engine(db, selected_tenant, actor.id)
    assert failure.value.status_code in {403, 404}
    assert _snapshot(db) == before


def test_engine_provision_missing_roles_does_not_create_roles_assignments_or_grants(db):
    tenant, actor = baseline._tenant(db)
    db.commit()
    before = _snapshot(db)
    result = provision_qra_engine(db, tenant.id, actor.id)
    assert result["role_grants_added"] == 0
    after = _snapshot(db)
    assert all(
        before[name] == after[name]
        for name in {"security_roles", "security_access_assignments", "project_memberships", "admin_configurations"}
    )
