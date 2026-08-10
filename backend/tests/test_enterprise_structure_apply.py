from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database.session import Base
from app.domain.models import (
    AdminConfiguration,
    EnterpriseWorkspace,
    PermissionCatalog,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityRole,
    SecurityRolePermission,
    Tenant,
    UserAccount,
)
from app.modules.enterprise_structure.constants import CATEGORY_SEED, WORKSPACE_TYPE_SEED
from app.modules.enterprise_structure.importer.apply import CORE_EVENT_TYPE, CoreApplyError, apply_core
from app.modules.enterprise_structure.importer.inventory import protected_source_hash
from app.modules.enterprise_structure.importer.parser import parse_configuration
from app.modules.enterprise_structure.models import (
    EnterpriseStrategicObjective,
    EnterpriseWorkspaceClassification,
    EnterpriseWorkspaceLink,
)

SOURCE = Path(__file__).parents[1] / "config" / "enterprise_structure.pyp_core_reconciled_review.yaml"
EXPECTED_HASH = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
FINAL_NAME = "P&P Ingeniería y Proyectos"
FINAL_SLUG = "pyp-ingenieria-proyectos"
ACTOR = "admin@demo.local"


@pytest.fixture
def session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'apply.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as db:
        _seed_gate02a_state(db)
    return factory


def _seed_gate02a_state(db: Session) -> None:
    tenant = Tenant(id=1, name="Demo Energy Infrastructure", slug="demo-energy", base_currency="COP")
    actor = UserAccount(
        id=1,
        tenant_id=1,
        email=ACTOR,
        full_name="Pypmis Admin",
        title="Tenant Administrator",
        status="active",
    )
    db.add_all([tenant, actor])
    db.flush()

    permission = PermissionCatalog(
        key="admin.enterprise_structure.manage",
        resource="enterprise_structure",
        action="manage",
        description="Manage Enterprise Structure",
        risk_level="high",
        status="active",
    )
    role = SecurityRole(
        tenant_id=1,
        code="organization_admin",
        name="Organization Administrator",
        description="",
        is_system=True,
        status="active",
    )
    db.add_all([permission, role])
    db.flush()
    db.add_all(
        [
            SecurityRolePermission(
                tenant_id=1,
                role_id=role.id,
                permission_id=permission.id,
                granted_by_user_id=actor.id,
            ),
            SecurityAccessAssignment(
                tenant_id=1,
                subject_type="user",
                user_id=actor.id,
                role_id=role.id,
                scope_type="organization",
                status="active",
                granted_by_user_id=actor.id,
            ),
        ]
    )
    for code in ("project-type", "property-type", "facility-type"):
        definition = CATEGORY_SEED[code]
        db.add(
            AdminConfiguration(
                tenant_id=1,
                kind="catalog",
                code=code,
                name=definition["name"],
                description=definition["description"],
                status="published",
                revision=1,
                version=1,
                content_json={
                    "applicable_types": definition["applicable_types"],
                    "items": definition["items"],
                },
                content_hash=f"{code}-hash",
                created_by_user_id=actor.id,
            )
        )

    for code, definition in WORKSPACE_TYPE_SEED.items():
        db.add(
            AdminConfiguration(
                tenant_id=1,
                kind="workspace_type",
                code=code,
                name=definition["name"],
                description=definition["description"],
                status="published",
                revision=1,
                version=1,
                content_json={
                    "allowed_children": definition["allowed_children"],
                    "can_be_root": definition["can_be_root"],
                    "required_categories": definition["required_categories"],
                    "required_fields": definition["required_fields"],
                },
                content_hash="type-hash",
                created_by_user_id=actor.id,
            )
        )
    db.add_all(
        [
            AdminConfiguration(
                tenant_id=1,
                kind="catalog",
                code="responsible-area",
                name="Responsible Areas",
                description="",
                status="published",
                revision=2,
                version=1,
                content_json={
                    "applicable_types": ["business-unit", "portfolio", "program", "project"],
                    "items": [
                        {"code": "consulting", "label": "Consulting"},
                        {"code": "pmo-aas", "label": "PMO aaS"},
                        {"code": "technology", "label": "Technology"},
                        {"code": "construction", "label": "Construction"},
                    ],
                },
                content_hash="responsible-hash",
                created_by_user_id=actor.id,
            ),
            AdminConfiguration(
                tenant_id=1,
                kind="catalog",
                code="strategic-objective",
                name="Strategic Objectives",
                description="",
                status="published",
                revision=1,
                version=1,
                content_json={
                    "applicable_types": ["portfolio", "program", "project"],
                    "items": [],
                },
                content_hash="objective-hash",
                created_by_user_id=actor.id,
            ),
        ]
    )
    db.add_all(
        [
            EnterpriseWorkspace(
                id=1,
                tenant_id=1,
                parent_id=None,
                workspace_type_code="enterprise",
                code="enterprise",
                external_key=None,
                record_code="01",
                name="P&P Ingenieria y Proyectos",
                status="active",
                defaults_json={"_enterprise": {"description": ""}},
                sort_order=0,
                version=3,
                created_by_user_id=actor.id,
            ),
            EnterpriseWorkspace(
                id=2,
                tenant_id=1,
                parent_id=1,
                workspace_type_code="business-unit",
                code="001",
                external_key=None,
                record_code="01.01",
                name="Gerencia de Construcciones",
                status="active",
                defaults_json={"_enterprise": {"description": ""}},
                sort_order=0,
                version=2,
                created_by_user_id=actor.id,
            ),
            EnterpriseWorkspace(
                id=3,
                tenant_id=1,
                parent_id=1,
                workspace_type_code="business-unit",
                code="002",
                external_key=None,
                record_code="01.02",
                name="Gerencia PMO aaS",
                status="active",
                defaults_json={"_enterprise": {"description": ""}},
                sort_order=0,
                version=1,
                created_by_user_id=actor.id,
            ),
        ]
    )


def _apply(
    db: Session,
    source_hash: str,
    *,
    actor_email: str = ACTOR,
    failure_injection: str | None = None,
):
    return apply_core(
        db,
        parse_configuration(SOURCE),
        source_file=SOURCE,
        tenant_code="demo-energy",
        expected_hash=EXPECTED_HASH,
        expected_source_hash=source_hash,
        actor_email=actor_email,
        approved_tenant_name=FINAL_NAME,
        approved_tenant_slug=FINAL_SLUG,
        failure_injection=failure_injection,
    )


def _source_hash(factory: sessionmaker) -> str:
    with factory() as db:
        return protected_source_hash(db)


def test_apply_preserves_ids_creates_core_and_is_idempotent(session_factory) -> None:
    source_hash = _source_hash(session_factory)
    with session_factory.begin() as db:
        first = _apply(db, source_hash)

    assert first.summary == {
        "adopt": 3,
        "create": 44,
        "workspace_create": 11,
        "objective_create": 7,
        "classification_create": 26,
        "tenant_update": 1,
        "update": 0,
        "unchanged": 0,
        "conflict": 0,
    }
    assert first.adopted_ids == {"ENT-PYP": 1, "BU-PYP-PMO": 3, "BU-PYP-CONST": 2}
    with session_factory() as db:
        tenant = db.get(Tenant, 1)
        workspaces = list(db.scalars(select(EnterpriseWorkspace).order_by(EnterpriseWorkspace.record_code)).all())
        by_key = {item.external_key: item for item in workspaces}
        assert (tenant.name, tenant.slug, tenant.base_currency) == (FINAL_NAME, FINAL_SLUG, "COP")
        assert len(workspaces) == 14
        assert by_key["ENT-PYP"].id == 1
        assert by_key["BU-PYP-PMO"].id == 3
        assert by_key["BU-PYP-CONST"].id == 2
        assert by_key["BU-PYP-CONST"].record_code == "01.04"
        assert by_key["BU-PYP-CONS"].record_code == "01.01"
        assert len({item.record_code for item in workspaces}) == 14
        assert db.scalar(select(func.count()).select_from(EnterpriseStrategicObjective)) == 7
        assert db.scalar(select(func.count()).select_from(EnterpriseWorkspaceClassification)) == 26
        assert db.scalar(select(func.count()).select_from(EnterpriseWorkspaceLink)) == 0
        first_versions = {item.id: item.version for item in workspaces}

    with session_factory.begin() as db:
        second = _apply(db, source_hash)

    assert second.idempotent_replay is True
    assert second.summary["adopt"] == 0
    assert second.summary["create"] == 0
    assert second.summary["update"] == 0
    assert second.summary["conflict"] == 0
    assert second.summary["unchanged"] == 47
    with session_factory() as db:
        workspaces = list(db.scalars(select(EnterpriseWorkspace)).all())
        assert {item.id: item.version for item in workspaces} == first_versions
        assert db.scalar(select(func.count()).select_from(EnterpriseStrategicObjective)) == 7
        assert db.scalar(select(func.count()).select_from(EnterpriseWorkspaceClassification)) == 26
        events = list(db.scalars(select(SecurityEvent).where(SecurityEvent.event_type == CORE_EVENT_TYPE)).all())
        assert len(events) == 2
        assert events[0].metadata_json["created_workspace_ids"] == first.created_workspace_ids
        assert events[1].metadata_json["idempotent_replay"] is True


@pytest.mark.parametrize("failure_injection", ["after_workspaces", "after_classifications"])
def test_apply_rolls_back_completely_on_failure(session_factory, failure_injection: str) -> None:
    source_hash = _source_hash(session_factory)
    with pytest.raises(CoreApplyError, match="INJECTED_FAILURE"):
        with session_factory.begin() as db:
            _apply(db, source_hash, failure_injection=failure_injection)
    with session_factory() as db:
        tenant = db.get(Tenant, 1)
        assert (tenant.name, tenant.slug) == ("Demo Energy Infrastructure", "demo-energy")
        assert db.scalar(select(func.count()).select_from(EnterpriseWorkspace)) == 3
        assert db.scalar(select(func.count()).select_from(EnterpriseStrategicObjective)) == 0
        assert db.scalar(select(func.count()).select_from(EnterpriseWorkspaceClassification)) == 0
        assert db.scalar(select(func.count()).select_from(SecurityEvent).where(SecurityEvent.event_type == CORE_EVENT_TYPE)) == 0


def test_apply_rejects_wrong_input_hash_without_mutation(session_factory) -> None:
    source_hash = _source_hash(session_factory)
    with pytest.raises(CoreApplyError, match="INPUT_HASH_MISMATCH"):
        with session_factory.begin() as db:
            apply_core(
                db,
                parse_configuration(SOURCE),
                source_file=SOURCE,
                tenant_code="demo-energy",
                expected_hash="0" * 64,
                expected_source_hash=source_hash,
                actor_email=ACTOR,
                approved_tenant_name=FINAL_NAME,
                approved_tenant_slug=FINAL_SLUG,
            )
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(EnterpriseWorkspace)) == 3


def test_apply_rejects_changed_snapshot_and_unauthorized_actor(session_factory) -> None:
    with pytest.raises(CoreApplyError, match="SOURCE_SNAPSHOT_CHANGED"):
        with session_factory.begin() as db:
            _apply(db, "f" * 64)

    source_hash = _source_hash(session_factory)
    with session_factory.begin() as db:
        assignment = db.scalar(select(SecurityAccessAssignment).where(SecurityAccessAssignment.user_id == 1))
        db.delete(assignment)
    changed_hash = _source_hash(session_factory)
    assert changed_hash == source_hash
    with pytest.raises(CoreApplyError, match="ACTOR_NOT_AUTHORIZED"):
        with session_factory.begin() as db:
            _apply(db, changed_hash)


def test_apply_rejects_missing_actor(session_factory) -> None:
    source_hash = _source_hash(session_factory)
    with pytest.raises(CoreApplyError, match="ACTOR_NOT_FOUND"):
        with session_factory.begin() as db:
            _apply(db, source_hash, actor_email="missing@example.com")
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(EnterpriseWorkspace)) == 3
        assert db.scalar(select(func.count()).select_from(SecurityEvent).where(SecurityEvent.event_type == CORE_EVENT_TYPE)) == 0


def test_apply_blocks_cross_tenant_adoption(session_factory) -> None:
    with session_factory.begin() as db:
        db.add(Tenant(id=2, name="Other", slug="other", base_currency="USD"))
        db.get(EnterpriseWorkspace, 3).tenant_id = 2
    source_hash = _source_hash(session_factory)
    with pytest.raises(CoreApplyError, match="DRY_RUN_INVALID|CROSS_TENANT_ADOPTION"):
        with session_factory.begin() as db:
            _apply(db, source_hash)
