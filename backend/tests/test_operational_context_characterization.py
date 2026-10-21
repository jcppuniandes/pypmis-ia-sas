"""O1A pre-change characterization of existing legacy/canonical boundaries.

The fixture is a rollback-only isolated test tenant, never Project 14. Tests
deliberately invoke existing query functions, not the legacy dashboard GET that
can calculate and persist control metrics. PostgreSQL is used when supplied by
PYPMIS_TEST_DATABASE_URL; SQLite runs are characterization only, not release proof.
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1 import router as legacy
from app.api.v1._helpers import require_membership, require_permission, require_project
from app.api.v1.routers import projects as scope
from app.database.session import Base, engine
from app.domain.models import (
    WBS,
    Activity,
    ControlAccount,
    CostRecord,
    CostSource,
    EnterpriseWorkspace,
    ProgressRecord,
    Project,
    ProjectMembership,
    QuantityTakeoffLine,
    QuantityTakeoffRun,
    Tenant,
    UserAccount,
)
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.project_creation.governance import DEFAULT_GOVERNANCE_POLICIES, ProjectGovernanceModel
from app.modules.qra_foundation.adapters import SourceAdapters
from app.modules.workspace_context.service import WorkspaceOperationalContextService


@pytest.fixture
def legacy_fixture():
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)
    with Session(engine) as db:
        transaction = db.begin()
        token = uuid4().hex[:12]
        tenant = Tenant(name=f"O1A characterization {token}", slug=f"o1a-characterize-{token}")
        other_tenant = Tenant(name=f"O1A other {token}", slug=f"o1a-other-{token}")
        db.add_all([tenant, other_tenant])
        db.flush()
        user = UserAccount(tenant_id=tenant.id, email=f"member-{token}@test.invalid", full_name="O1A member")
        outsider = UserAccount(tenant_id=tenant.id, email=f"outsider-{token}@test.invalid", full_name="O1A outsider")
        db.add_all([user, outsider])
        db.flush()
        # Deliberately separate numeric namespaces and exclude reserved ID 14.
        legacy_id = 1_000_000 + uuid4().int % 50_000_000
        project = Project(
            id=legacy_id, tenant_id=tenant.id, code=f"LEG-{token}", name="Legacy characterization", status="draft"
        )
        workspace = EnterpriseWorkspace(
            id=legacy_id + 100_000_000,
            tenant_id=tenant.id,
            workspace_type_code="project",
            code=f"WS-{token}",
            record_code=f"O1A.{token}",
            external_key=f"O1A-WS-{token}",
            name="Canonical characterization",
            status="active",
            created_by_user_id=user.id,
            defaults_json={"_project": {"governance_model": "DIRECT_INTERNAL"}},
        )
        db.add_all([project, workspace])
        db.flush()
        membership = ProjectMembership(
            tenant_id=tenant.id,
            project_id=project.id,
            user_id=user.id,
            role="Executive Viewer",
            can_capture_progress=False,
            can_capture_cost=False,
            can_configure=False,
        )
        wbs = WBS(tenant_id=tenant.id, project_id=project.id, code="O1A-WBS", name="Existing source")
        db.add_all([membership, wbs])
        db.flush()
        account = ControlAccount(
            tenant_id=tenant.id,
            project_id=project.id,
            wbs_id=wbs.id,
            code="O1A-CA",
            name="Existing account",
            responsible="Existing owner",
            discipline="Civil",
        )
        run = QuantityTakeoffRun(tenant_id=tenant.id, project_id=project.id, source_file_name="characterization.csv")
        db.add_all([account, run])
        db.flush()
        db.add_all(
            [
                Activity(
                    tenant_id=tenant.id,
                    project_id=project.id,
                    control_account_id=account.id,
                    code="O1A-A",
                    name="Existing activity",
                ),
                CostRecord(
                    tenant_id=tenant.id,
                    project_id=project.id,
                    control_account_id=account.id,
                    source=CostSource.invoice,
                    amount=12.5,
                    incurred_on=date(2026, 10, 1),
                    description="Existing source cost",
                ),
                ProgressRecord(
                    tenant_id=tenant.id,
                    project_id=project.id,
                    control_account_id=account.id,
                    physical_percent=20,
                    quantity_installed=2,
                    labor_hours=3,
                    reported_on=date(2026, 10, 1),
                ),
                QuantityTakeoffLine(
                    tenant_id=tenant.id,
                    project_id=project.id,
                    run_id=run.id,
                    quantity=5,
                    unit="m2",
                    element_id="O1A-IFC-1",
                ),
            ]
        )
        db.flush()
        yield SimpleNamespace(
            db=db,
            tenant=tenant,
            other_tenant=other_tenant,
            user=user,
            outsider=outsider,
            project=project,
            workspace=workspace,
            membership=membership,
            run=run,
        )
        if transaction.is_active:
            transaction.rollback()


def test_legacy_lookup_is_tenant_scoped_without_id_equality(legacy_fixture):
    f = legacy_fixture
    assert f.project.id != f.workspace.id and 14 not in {f.project.id, f.workspace.id}
    assert require_project(f.db, f.tenant.id, f.project.id).id == f.project.id
    with pytest.raises(HTTPException) as denied:
        require_project(f.db, f.other_tenant.id, f.project.id)
    assert denied.value.status_code == 404
    with pytest.raises(HTTPException) as canonical_is_not_legacy:
        require_project(f.db, f.tenant.id, f.workspace.id)
    assert canonical_is_not_legacy.value.status_code == 404


def test_existing_legacy_reads_preserve_scope_schedule_cost_progress(legacy_fixture):
    f = legacy_fixture
    kwargs = {"db": f.db, "tenant_id": f.tenant.id, "user_id": f.user.id, "project_id": f.project.id}
    assert [row.code for row in legacy.list_wbs(**kwargs)] == ["O1A-WBS"]
    assert [row.code for row in legacy.list_activities(**kwargs)] == ["O1A-A"]
    assert [row.amount for row in legacy.list_cost_records(**kwargs)] == [12.5]
    assert [row.physical_percent for row in legacy.list_progress_records(**kwargs)] == [20]
    assert [row.quantity for row in scope.list_quantity_takeoff_lines(run_id=f.run.id, **kwargs)] == [5]


@pytest.mark.parametrize(
    "query", [legacy.list_wbs, legacy.list_activities, legacy.list_cost_records, legacy.list_progress_records]
)
def test_existing_operational_reads_require_project_membership(legacy_fixture, query):
    f = legacy_fixture
    with pytest.raises(HTTPException) as denied:
        query(f.project.id, db=f.db, tenant_id=f.tenant.id, user_id=f.outsider.id)
    assert denied.value.status_code == 403


def test_existing_membership_does_not_grant_material_permissions(legacy_fixture):
    f = legacy_fixture
    member = require_membership(f.db, f.tenant.id, f.project.id, f.user.id)
    for permission in ("can_configure", "can_capture_cost", "can_capture_progress", "can_approve_workflow"):
        with pytest.raises(HTTPException) as denied:
            require_permission(member, permission, "Denied by characterized legacy RBAC")
        assert denied.value.status_code == 403


def test_existing_explicit_source_adapter_never_guesses_name_code_or_numeric_id(legacy_fixture):
    f = legacy_fixture
    adapter = SourceAdapters(f.db, f.tenant.id)
    f.project.name, f.project.code = f.workspace.name, f.workspace.code
    assert adapter.operational_project(f.workspace) is None
    f.workspace.defaults_json = {"_project": {"operational_project_id": f.project.id}}
    f.db.flush()
    assert adapter.operational_project(f.workspace).id == f.project.id
    assert SourceAdapters(f.db, f.other_tenant.id).operational_project(f.workspace) is None


def test_canonical_workspace_query_keeps_workspace_namespace(legacy_fixture):
    f = legacy_fixture
    context = EnterprisePermissionContext(f.user, False, frozenset(), frozenset({f.workspace.id}), frozenset())
    service = WorkspaceOperationalContextService(f.db, f.tenant.id, f.user.id, context)
    before = f.db.scalar(select(func.count()).select_from(Project))
    assert service._workspace(f.workspace.id).external_key == f.workspace.external_key
    assert service._has_workspace_access(f.workspace.id)
    assert not service._has_workspace_access(f.project.id)
    assert f.db.scalar(select(func.count()).select_from(Project)) == before


def test_non_owner_governance_does_not_require_owner_fid():
    for model in (ProjectGovernanceModel.CONTRACTOR_DELIVERY, ProjectGovernanceModel.DIRECT_INTERNAL):
        policy = DEFAULT_GOVERNANCE_POLICIES[model]
        assert not policy["fid_required_for_creation"]
        assert not policy["portfolio_required"]
        assert not policy["fel_required"]
    assert (
        "investment_execution_authorized"
        in DEFAULT_GOVERNANCE_POLICIES[ProjectGovernanceModel.CAPITAL_OWNER]["activation_requirements"]
    )
