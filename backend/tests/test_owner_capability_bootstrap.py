"""Narrow explicit provisioning: existing authority, additive grants, no demo seed."""

from copy import deepcopy

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.bootstrap_owner_capability import (
    OWNER_CONFIGURATION_KEYS,
    OWNER_PERMISSION_KEYS,
    provision_owner_capability,
)
from app.core.time import utc_now
from app.database.session import Base
from app.domain.models import (
    AdminConfiguration,
    AdminNumberSequence,
    EnterpriseWorkspace,
    OrganizationUnit,
    PermissionCatalog,
    Project,
    ProjectMembership,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityGroup,
    SecurityGroupMember,
    SecurityRole,
    SecurityRolePermission,
    Tenant,
    UserAccount,
)
from app.modules.basic_data.models import BasicDataReadinessAssessment
from app.modules.enterprise_structure.permissions import PROJECT_DEFINITION_ROLE_PERMISSIONS
from app.modules.owner_capability.models import OwnerCapabilityAssessment, OwnerCapabilityCommand
from app.modules.owner_capability.service import (
    CONFIGURATION_KIND,
    DEFAULT_CONFIGURATION,
    NUMBER_RULE,
    OwnerCapabilityService,
    _hash,
)

TABLE_MODELS = (
    Tenant,
    UserAccount,
    Project,
    ProjectMembership,
    OrganizationUnit,
    SecurityGroup,
    SecurityGroupMember,
    PermissionCatalog,
    SecurityRole,
    SecurityRolePermission,
    SecurityAccessAssignment,
    AdminConfiguration,
    AdminNumberSequence,
    EnterpriseWorkspace,
    SecurityEvent,
    OwnerCapabilityAssessment,
    OwnerCapabilityCommand,
    BasicDataReadinessAssessment,
)


@pytest.fixture
def db():
    # No application lifespan, demo fixtures, production database or Docker.
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[model.__table__ for model in TABLE_MODELS])
    with Session(engine) as session:
        yield session
    engine.dispose()


def _rows(db, model, where=None):
    statement = select(model.__table__).order_by(model.__table__.c.id)
    if where is not None:
        statement = statement.where(where)
    return deepcopy([dict(row) for row in db.execute(statement).mappings()])


def _snapshot(db):
    return {model.__tablename__: _rows(db, model) for model in TABLE_MODELS}


def _tenant(db, *, can_configure=True, with_project=True):
    tenant = Tenant(name="Existing enterprise", slug="existing-enterprise")
    db.add(tenant)
    db.flush()
    actor = UserAccount(tenant_id=tenant.id, email="actor@example.test", full_name="Existing configurator")
    db.add(actor)
    db.flush()
    if with_project:
        project = Project(tenant_id=tenant.id, code="EXISTING", name="Existing legacy project")
        db.add(project)
        db.flush()
        db.add(
            ProjectMembership(
                tenant_id=tenant.id,
                project_id=project.id,
                user_id=actor.id,
                role="existing-role",
                can_configure=can_configure,
            )
        )
    db.commit()
    return tenant, actor


def _role(db, tenant, code):
    role = SecurityRole(tenant_id=tenant.id, code=code, name=code, description="Preserve this description")
    db.add(role)
    db.flush()
    return role


def _existing_authority(db, tenant, actor, *, scope="organization"):
    role = _role(db, tenant, "configuration_admin")
    permission = PermissionCatalog(
        key="admin.enterprise_structure.manage", resource="enterprise_structure", action="manage"
    )
    db.add(permission)
    db.flush()
    db.add_all(
        [
            SecurityRolePermission(
                tenant_id=tenant.id, role_id=role.id, permission_id=permission.id, granted_by_user_id=actor.id
            ),
            SecurityAccessAssignment(
                tenant_id=tenant.id,
                subject_type="user",
                user_id=actor.id,
                role_id=role.id,
                scope_type=scope,
                workspace_id=None,
                granted_by_user_id=actor.id,
            ),
        ]
    )
    db.commit()
    return role


def _configuration(db, tenant, actor, *, kind, code, content=None):
    content = content or {"unchanged": ["existing", "source"]}
    row = AdminConfiguration(
        tenant_id=tenant.id,
        kind=kind,
        code=code,
        name="Existing published configuration",
        status="published",
        revision=7,
        version=12,
        content_json=content,
        content_hash=_hash(content),
        created_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    return row


def test_idempotent_provision_preserves_roles_memberships_sources_and_live_history(db):
    tenant, actor = _tenant(db)
    codes = set(PROJECT_DEFINITION_ROLE_PERMISSIONS) | {"organization_admin", "configuration_admin", "custom_role"}
    roles = {code: _role(db, tenant, code) for code in sorted(codes)}
    existing_permission = PermissionCatalog(key="custom.existing", resource="custom", action="existing")
    db.add(existing_permission)
    db.flush()
    db.add(
        SecurityRolePermission(
            tenant_id=tenant.id,
            role_id=roles["custom_role"].id,
            permission_id=existing_permission.id,
            granted_by_user_id=actor.id,
        )
    )
    db.add(
        SecurityAccessAssignment(
            tenant_id=tenant.id,
            subject_type="user",
            user_id=actor.id,
            role_id=roles["custom_role"].id,
            scope_type="organization",
            granted_by_user_id=actor.id,
        )
    )
    source = _configuration(db, tenant, actor, kind="basic_data_readiness_configuration", code="existing")
    existing_owner = _configuration(db, tenant, actor, kind=CONFIGURATION_KIND, code="custom-owner")
    workspace = EnterpriseWorkspace(
        tenant_id=tenant.id,
        workspace_type_code="PROJECT",
        code="EXISTING-PROJECT",
        record_code="EXISTING-PROJECT",
        name="Existing canonical project",
        created_by_user_id=actor.id,
    )
    db.add(workspace)
    db.flush()
    common = {
        "tenant_id": tenant.id,
        "project_workspace_id": workspace.id,
        "assessment_number": "EXISTING-000001",
        "configuration_revision": 7,
        "configuration_hash": source.content_hash,
        "created_by": actor.id,
        "completed_by": actor.id,
        "completed_at": utc_now(),
        "assessment_hash": "f" * 64,
        "status": "COMPLETED",
        "snapshot_json": {"preserve": "immutable historical evidence"},
    }
    db.add(BasicDataReadinessAssessment(**common, configuration_id=source.id))
    db.add(OwnerCapabilityAssessment(**common, configuration_id=existing_owner.id, reviewed_by=actor.id))
    db.add(
        OwnerCapabilityCommand(
            tenant_id=tenant.id,
            idempotency_key="existing-command",
            command_type="existing",
            request_hash="e" * 64,
            result_json={"preserve": True},
            actor_id=actor.id,
        )
    )
    db.add(AdminNumberSequence(tenant_id=tenant.id, rule_code="basic_data_assessment", next_value=53, version=4))
    db.commit()
    before = _snapshot(db)

    result = provision_owner_capability(db, tenant.id, actor.id)
    assert result["permission_entries_added"] == 9
    assert len(OWNER_PERMISSION_KEYS) == 9
    assert result["configuration_status"] == "draft"
    for key in ("roles_created", "assignments_created", "memberships_created", "live_assessments_created"):
        assert result[key] == 0
    permissions = {row.key: row for row in db.scalars(select(PermissionCatalog))}
    assert set(permissions) == OWNER_PERMISSION_KEYS | {"custom.existing"}
    expected_count = 0
    for code, role in roles.items():
        actual = set(
            db.scalars(
                select(PermissionCatalog.key)
                .join(SecurityRolePermission, SecurityRolePermission.permission_id == PermissionCatalog.id)
                .where(SecurityRolePermission.role_id == role.id, PermissionCatalog.key.in_(OWNER_PERMISSION_KEYS))
            )
        )
        expected = PROJECT_DEFINITION_ROLE_PERMISSIONS.get(code, frozenset()) & OWNER_PERMISSION_KEYS
        if code == "organization_admin":
            expected = OWNER_PERMISSION_KEYS
        if code == "configuration_admin":
            expected = OWNER_CONFIGURATION_KEYS
        assert actual == expected
        expected_count += len(expected)
    assert result["role_grants_added"] == expected_count

    after = _snapshot(db)
    for model in TABLE_MODELS:
        if model not in (
            PermissionCatalog,
            SecurityRolePermission,
            AdminConfiguration,
            AdminNumberSequence,
            SecurityEvent,
        ):
            assert after[model.__tablename__] == before[model.__tablename__]
    assert (
        _rows(db, PermissionCatalog, ~PermissionCatalog.key.in_(OWNER_PERMISSION_KEYS)) == before["permission_catalog"]
    )
    assert (
        _rows(db, SecurityRolePermission, SecurityRolePermission.permission_id == existing_permission.id)
        == before["security_role_permissions"]
    )
    assert (
        _rows(db, AdminConfiguration, AdminConfiguration.id.in_([source.id, existing_owner.id]))
        == before["admin_configurations"]
    )
    assert (
        _rows(db, AdminNumberSequence, AdminNumberSequence.rule_code != NUMBER_RULE) == before["admin_number_sequences"]
    )
    neutral = db.get(AdminConfiguration, result["configuration_id"])
    assert neutral.content_json == DEFAULT_CONFIGURATION
    assert neutral.content_json["dimensions"] == neutral.content_json["requirements"] == []
    assert neutral.published_at is None
    sequence = db.scalar(select(AdminNumberSequence).where(AdminNumberSequence.rule_code == NUMBER_RULE))
    assert (sequence.scope_key, sequence.next_value, sequence.version) == ("tenant", 1, 1)
    assert len(after["security_events"]) == 1
    assert after["security_events"][0]["event_type"] == "owner_capability.config.seeded"

    second = provision_owner_capability(db, tenant.id, actor.id)
    assert second["permission_entries_added"] == second["role_grants_added"] == 0
    assert second["configuration_id"] == result["configuration_id"]
    assert _snapshot(db) == after


def test_active_user_in_empty_tenant_has_no_implicit_authority(db):
    tenant, actor = _tenant(db, with_project=False)
    before = _snapshot(db)
    with pytest.raises(HTTPException) as error:
        provision_owner_capability(db, tenant.id, actor.id)
    assert error.value.status_code == 403
    assert _snapshot(db) == before


def test_workspace_scoped_configuration_permission_cannot_provision_tenant(db):
    tenant, actor = _tenant(db, can_configure=False)
    _existing_authority(db, tenant, actor, scope="workspace")
    before = _snapshot(db)
    with pytest.raises(HTTPException) as error:
        provision_owner_capability(db, tenant.id, actor.id)
    assert error.value.status_code == 403
    assert _snapshot(db) == before


def test_existing_organization_authority_works_without_legacy_project_membership(db):
    tenant, actor = _tenant(db, with_project=False)
    _existing_authority(db, tenant, actor)
    before = _snapshot(db)
    result = provision_owner_capability(db, tenant.id, actor.id)
    assert result["permission_entries_added"] == 9
    assert result["role_grants_added"] == 3
    for model in (SecurityRole, SecurityAccessAssignment, ProjectMembership, SecurityGroupMember):
        assert _rows(db, model) == before[model.__tablename__]
    assert _rows(db, OwnerCapabilityAssessment) == _rows(db, OwnerCapabilityCommand) == []


def test_does_not_create_missing_system_roles_or_auto_assign_admin(db):
    tenant, actor = _tenant(db)
    before = _snapshot(db)
    result = provision_owner_capability(db, tenant.id, actor.id)
    assert result["permission_entries_added"] == 9
    assert result["role_grants_added"] == 0
    for model in (
        SecurityRole,
        SecurityRolePermission,
        SecurityAccessAssignment,
        ProjectMembership,
        SecurityGroupMember,
    ):
        assert _rows(db, model) == before[model.__tablename__]


@pytest.mark.parametrize("invalid", ["missing-tenant", "foreign-user", "inactive-user"])
def test_invalid_actor_or_tenant_is_rejected_before_writes(db, invalid):
    tenant, actor = _tenant(db)
    selected_tenant = tenant.id
    if invalid == "missing-tenant":
        selected_tenant += 100
    elif invalid == "foreign-user":
        other = Tenant(name="Other", slug="other")
        db.add(other)
        db.flush()
        selected_tenant = other.id
    else:
        actor.status = "inactive"
    db.commit()
    before = _snapshot(db)
    with pytest.raises(HTTPException) as error:
        provision_owner_capability(db, selected_tenant, actor.id)
    assert error.value.status_code == 404
    assert _snapshot(db) == before


def test_seed_failure_rolls_back_all_catalog_and_grant_additions(db, monkeypatch):
    tenant, actor = _tenant(db)
    _role(db, tenant, "organization_admin")
    db.commit()
    before = _snapshot(db)

    def fail(_service):
        raise RuntimeError("forced seed failure")

    monkeypatch.setattr(OwnerCapabilityService, "ensure_seed", fail)
    with pytest.raises(RuntimeError, match="forced seed failure"):
        provision_owner_capability(db, tenant.id, actor.id)
    assert _snapshot(db) == before


def test_existing_published_owner_default_and_sequence_are_not_reset(db):
    tenant, actor = _tenant(db)
    existing = _configuration(db, tenant, actor, kind=CONFIGURATION_KIND, code="default")
    db.add(AdminNumberSequence(tenant_id=tenant.id, rule_code=NUMBER_RULE, next_value=39, version=8))
    db.commit()
    configurations = _rows(db, AdminConfiguration)
    sequences = _rows(db, AdminNumberSequence)
    result = provision_owner_capability(db, tenant.id, actor.id)
    assert result["configuration_id"] == existing.id
    assert result["configuration_status"] == "published"
    assert _rows(db, AdminConfiguration) == configurations
    assert _rows(db, AdminNumberSequence) == sequences
    assert _rows(db, SecurityEvent) == []
