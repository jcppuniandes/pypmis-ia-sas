"""Narrow additive QRA provisioning reuses existing tenant authority."""

from copy import deepcopy

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from tests import test_owner_capability_bootstrap as baseline

from app.bootstrap_qra_foundation import QRA_CONFIGURATION_KEYS, QRA_PERMISSION_KEYS, provision_qra_foundation
from app.database.session import Base
from app.domain.models import AdminConfiguration, AdminNumberSequence, PermissionCatalog, SecurityRolePermission
from app.modules.enterprise_structure.permissions import PROJECT_DEFINITION_ROLE_PERMISSIONS
from app.modules.qra_foundation.models import (
    CostSourceReadinessAssessment,
    QraCommand,
    QraModelDefinition,
    ScheduleSourceReadinessAssessment,
)
from app.modules.qra_foundation.service import CONFIGURATION_KIND, DEFAULT_CONFIGURATION, QraFoundationService

TABLE_MODELS = baseline.TABLE_MODELS + (
    CostSourceReadinessAssessment,
    ScheduleSourceReadinessAssessment,
    QraModelDefinition,
    QraCommand,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[model.__table__ for model in TABLE_MODELS])
    with Session(engine) as session:
        yield session
    engine.dispose()


def snapshot(db):
    return {model.__tablename__: baseline._rows(db, model) for model in TABLE_MODELS}


def test_provision_only_adds_qra_catalog_existing_role_grants_and_neutral_draft(db):
    tenant, actor = baseline._tenant(db)
    codes = set(PROJECT_DEFINITION_ROLE_PERMISSIONS) | {"organization_admin", "configuration_admin", "custom_role"}
    roles = {code: baseline._role(db, tenant, code) for code in sorted(codes)}
    source = baseline._configuration(
        db, tenant, actor, kind="owner_capability_readiness_configuration", code="unchanged"
    )
    db.add(AdminNumberSequence(tenant_id=tenant.id, rule_code="owner_capability_assessment", next_value=83, version=4))
    db.commit()
    before = snapshot(db)
    result = provision_qra_foundation(db, tenant.id, actor.id)
    assert result["permission_entries_added"] == len(QRA_PERMISSION_KEYS) == 16
    assert result["configuration_status"] == "draft"
    for key in (
        "roles_created",
        "assignments_created",
        "memberships_created",
        "live_assessments_created",
        "live_models_created",
    ):
        assert result[key] == 0
    config = db.get(AdminConfiguration, result["configuration_id"])
    assert config.content_json == DEFAULT_CONFIGURATION
    assert config.content_json["cost_requirements"] == config.content_json["schedule_requirements"] == []
    assert config.published_at is None
    for code, role in roles.items():
        actual = set(
            db.scalars(
                select(PermissionCatalog.key)
                .join(SecurityRolePermission, SecurityRolePermission.permission_id == PermissionCatalog.id)
                .where(SecurityRolePermission.role_id == role.id, PermissionCatalog.key.in_(QRA_PERMISSION_KEYS))
            )
        )
        expected = PROJECT_DEFINITION_ROLE_PERMISSIONS.get(code, frozenset()) & QRA_PERMISSION_KEYS
        if code == "organization_admin":
            expected = QRA_PERMISSION_KEYS
        elif code == "configuration_admin":
            expected = QRA_CONFIGURATION_KEYS
        assert actual == expected
    after = snapshot(db)
    changed = {
        "permission_catalog",
        "security_role_permissions",
        "admin_configurations",
        "admin_number_sequences",
        "security_events",
    }
    assert all(before[name] == rows for name, rows in after.items() if name not in changed)
    assert baseline._rows(db, AdminConfiguration, AdminConfiguration.id == source.id) == before["admin_configurations"]
    assert (
        baseline._rows(db, AdminNumberSequence, AdminNumberSequence.rule_code == "owner_capability_assessment")
        == before["admin_number_sequences"]
    )
    again = provision_qra_foundation(db, tenant.id, actor.id)
    assert again["permission_entries_added"] == again["role_grants_added"] == 0
    assert snapshot(db) == after


@pytest.mark.parametrize(
    "scenario", ["empty-tenant", "workspace-only", "missing-tenant", "foreign-user", "inactive-user"]
)
def test_missing_or_wrong_authority_does_not_write(db, scenario):
    tenant, actor = baseline._tenant(db, can_configure=False, with_project=scenario != "empty-tenant")
    selected_tenant = tenant.id
    if scenario == "workspace-only":
        baseline._existing_authority(db, tenant, actor, scope="workspace")
    elif scenario == "missing-tenant":
        selected_tenant += 100
    elif scenario == "foreign-user":
        from app.domain.models import Tenant

        other = Tenant(name="Other", slug="other")
        db.add(other)
        db.flush()
        selected_tenant = other.id
    elif scenario == "inactive-user":
        actor.status = "inactive"
    db.commit()
    before = snapshot(db)
    with pytest.raises(HTTPException) as error:
        provision_qra_foundation(db, selected_tenant, actor.id)
    assert error.value.status_code in {403, 404}
    assert snapshot(db) == before


def test_existing_org_config_authority_no_membership_needed(db):
    tenant, actor = baseline._tenant(db, with_project=False)
    baseline._existing_authority(db, tenant, actor)
    before = snapshot(db)
    result = provision_qra_foundation(db, tenant.id, actor.id)
    assert result["permission_entries_added"] == 16
    assert result["role_grants_added"] == 3
    for name in ("security_roles", "security_access_assignments", "project_memberships", "security_group_members"):
        assert snapshot(db)[name] == before[name]


def test_missing_roles_are_not_created_or_assigned(db):
    tenant, actor = baseline._tenant(db)
    before = snapshot(db)
    result = provision_qra_foundation(db, tenant.id, actor.id)
    assert result["role_grants_added"] == 0
    for name in ("security_roles", "security_access_assignments", "project_memberships", "security_role_permissions"):
        assert snapshot(db)[name] == before[name]


def test_seed_failure_atomically_rolls_back_catalog_and_grants(db, monkeypatch):
    tenant, actor = baseline._tenant(db)
    baseline._role(db, tenant, "organization_admin")
    db.commit()
    before = deepcopy(snapshot(db))

    def fail(_service):
        raise RuntimeError("forced QRA seed failure")

    monkeypatch.setattr(QraFoundationService, "ensure_seed", fail)
    with pytest.raises(RuntimeError, match="forced QRA seed failure"):
        provision_qra_foundation(db, tenant.id, actor.id)
    assert snapshot(db) == before


def test_existing_published_methodology_is_never_reset(db):
    tenant, actor = baseline._tenant(db)
    existing = baseline._configuration(db, tenant, actor, kind=CONFIGURATION_KIND, code="default")
    db.commit()
    before = baseline._rows(db, AdminConfiguration)
    result = provision_qra_foundation(db, tenant.id, actor.id)
    assert result["configuration_id"] == existing.id
    assert result["configuration_status"] == "published"
    assert baseline._rows(db, AdminConfiguration) == before
