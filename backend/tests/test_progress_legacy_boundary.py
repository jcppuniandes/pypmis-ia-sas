"""Real isolated PostgreSQL boundaries; legacy values never become approved EV."""

import os

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from tests.progress_release_fixture import create_progress_fixture, request
from tests.test_progress_foundation_release import create
from tests.test_scope_foundation_release import success

from app.database.session import SessionLocal
from app.main import app
from app.modules.progress_foundation.legacy_boundary import (
    PROGRESS_WRITERS,
    canonical_progress_project,
    guard_legacy_progress_write,
)

pytestmark = pytest.mark.skipif(
    os.getenv("PYPMIS_O1BD_FIXTURE") != "disposable-only",
    reason="Dedicated O1B-D disposable PostgreSQL scenario required",
)


@pytest.fixture(scope="module")
def fixture():
    with TestClient(app) as client, SessionLocal() as db:
        f = create_progress_fixture(db, client)
        f.db = db
        endpoint = f"/api/v1/operational/projects/{f.project_workspace_id}/binding"
        binding = success(request(f, "GET", endpoint, actor="admin"))
        if binding["state"] != "ACTIVE":
            success(
                request(
                    f,
                    "POST",
                    endpoint,
                    actor="admin",
                    version=binding["version"],
                    payload={
                        "reason": "Explicit isolated Progress binding",
                        "legacy_project_id": f.legacy_project_id,
                        "source": "AUTHORIZED_ONBOARDING",
                    },
                ),
                201,
            )
        yield f
        db.rollback()


def test_get_does_not_adopt_and_explicit_command_does(fixture):
    f = fixture
    assert canonical_progress_project(f.db, f.tenant_id, f.legacy_project_id) is None
    success(request(f, "GET", "/overview"))
    assert canonical_progress_project(f.db, f.tenant_id, f.legacy_project_id) is None
    create(f)
    assert canonical_progress_project(f.db, f.tenant_id, f.legacy_project_id) == f.project_workspace_id
    assert canonical_progress_project(f.db, f.foreign_tenant.id, f.legacy_project_id) is None


@pytest.mark.parametrize("writer", sorted(PROGRESS_WRITERS))
def test_direct_legacy_writers_blocked_after_explicit_adoption(fixture, writer):
    f = fixture
    if canonical_progress_project(f.db, f.tenant_id, f.legacy_project_id) is None:
        create(f)
    with pytest.raises(HTTPException) as rejected:
        guard_legacy_progress_write(f.db, f.tenant_id, f.legacy_project_id, writer)
    assert rejected.value.status_code == 409
    assert rejected.value.detail["code"] == "CANONICAL_PROGRESS_AUTHORITY_REQUIRED"
    assert rejected.value.detail["candidate_only"] is True


def test_real_service_cycle_cannot_recalculate_legacy_ev_after_adoption(fixture):
    from app.services.control_core import ControlCoreService

    f = fixture
    if canonical_progress_project(f.db, f.tenant_id, f.legacy_project_id) is None:
        create(f)
    with pytest.raises(HTTPException) as rejected:
        ControlCoreService(f.db).run_project_cycle(f.tenant_id, f.legacy_project_id)
    assert rejected.value.detail["code"] == "CANONICAL_PROGRESS_AUTHORITY_REQUIRED"


def test_nonwriter_legacy_read_is_not_blocked(fixture):
    f = fixture
    guard_legacy_progress_write(f.db, f.tenant_id, f.legacy_project_id, "get_dashboard")


def test_committed_legacy_source_returns_success_without_recalculating_canonical_progress():
    """Characterize existing legacy source rows, not new canonical approvals."""
    from datetime import date

    from sqlalchemy import func, select

    from app.domain.models import (
        KPI,
        WBS,
        ControlAccount,
        ImportStatus,
        ProjectMembership,
        ScheduleImport,
        ScheduleSource,
    )
    from app.modules.cost_foundation.legacy_boundary import canonical_cost_project
    from app.modules.progress_foundation.models import ProgressMeasurement
    from app.services.control_core import ControlCoreService

    with TestClient(app) as client, SessionLocal() as db:
        f = create_progress_fixture(db, client, prepare_integrated=False)
        f.db = db
        endpoint = f"/api/v1/operational/projects/{f.project_workspace_id}/binding"
        binding = success(request(f, "GET", endpoint, actor="admin"))
        if binding["state"] != "ACTIVE":
            success(
                request(
                    f,
                    "POST",
                    endpoint,
                    actor="admin",
                    version=binding["version"],
                    payload={
                        "reason": "Isolated legacy source boundary binding",
                        "legacy_project_id": f.legacy_project_id,
                        "source": "AUTHORIZED_ONBOARDING",
                    },
                ),
                201,
            )
        create(f)
        assert canonical_cost_project(db, f.tenant_id, f.legacy_project_id) is None
        assert canonical_progress_project(db, f.tenant_id, f.legacy_project_id) == f.project_workspace_id
        base = {"tenant_id": f.tenant_id, "project_id": f.legacy_project_id}
        membership = db.scalar(
            select(ProjectMembership).where(
                ProjectMembership.tenant_id == f.tenant_id,
                ProjectMembership.project_id == f.legacy_project_id,
                ProjectMembership.user_id == f.users["admin"].id,
            )
        )
        if membership is None:
            db.add(
                ProjectMembership(**base, user_id=f.users["admin"].id, role="Control Manager", can_capture_cost=True)
            )
        else:
            membership.can_capture_cost = True
        wbs = WBS(**base, code="LEGACY-SOURCE-WBS", name="Existing legacy candidate work")
        db.add(wbs)
        db.flush()
        account = ControlAccount(
            **base,
            wbs_id=wbs.id,
            code="LEGACY-SOURCE-CA",
            name="Existing account",
            responsible="Existing owner",
            discipline="Construction",
            budget=100,
            forecast=100,
        )
        db.add_all(
            [
                account,
                ScheduleImport(
                    **base,
                    source=ScheduleSource.p6_xml,
                    file_name="existing-legacy-source.xml",
                    status=ImportStatus.validated,
                    quality_score=90,
                ),
            ]
        )
        db.commit()
        before_kpi = db.scalar(
            select(func.count())
            .select_from(KPI)
            .where(KPI.tenant_id == f.tenant_id, KPI.project_id == f.legacy_project_id)
        )
        before_progress = db.scalar(
            select(func.count()).select_from(ProgressMeasurement).where(ProgressMeasurement.tenant_id == f.tenant_id)
        )
        result = success(
            request(
                f,
                "POST",
                f"/api/v1/projects/{f.legacy_project_id}/cost-records",
                actor="admin",
                payload={
                    "control_account_id": account.id,
                    "source": "invoice",
                    "amount": 10,
                    "incurred_on": date(2026, 10, 22).isoformat(),
                    "description": "Legacy candidate source, not approved EV",
                },
            )
        )
        assert result["amount"] == 10
        assert ControlCoreService(db).run_legacy_projection_if_unadopted(f.tenant_id, f.legacy_project_id) is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(KPI)
                .where(KPI.tenant_id == f.tenant_id, KPI.project_id == f.legacy_project_id)
            )
            == before_kpi
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(ProgressMeasurement)
                .where(ProgressMeasurement.tenant_id == f.tenant_id)
            )
            == before_progress
        )


@pytest.mark.parametrize(
    "endpoint",
    [
        "create_cost_record",
        "create_payment_certificate",
        "update_payment_certificate",
        "create_warehouse_receipt",
        "update_warehouse_receipt",
    ],
)
def test_all_postcommit_source_hooks_use_noncompeting_projection_adapter(endpoint):
    import ast
    import inspect

    from app.api.v1 import router

    tree = ast.parse(inspect.getsource(getattr(router, endpoint)))
    calls = [
        node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "run_legacy_projection_if_unadopted" in calls
    assert "run_project_cycle" not in calls


@pytest.mark.parametrize(
    "status,code,skip",
    [
        (409, "CANONICAL_PROGRESS_AUTHORITY_REQUIRED", True),
        (403, "CANONICAL_PROGRESS_AUTHORITY_REQUIRED", False),
        (409, "OTHER_CONFLICT", False),
        (500, "OTHER_FAILURE", False),
    ],
)
def test_postcommit_projection_race_skips_only_the_nonmutating_progress_guard(monkeypatch, status, code, skip):
    from app.modules.progress_foundation import legacy_boundary
    from app.services.control_core import ControlCoreService

    monkeypatch.setattr(legacy_boundary, "canonical_progress_project", lambda *_args: None)

    def race(_self, _tenant_id, _project_id):
        raise HTTPException(status_code=status, detail={"code": code})

    monkeypatch.setattr(ControlCoreService, "run_project_cycle", race)
    service = ControlCoreService(object())
    if skip:
        assert service.run_legacy_projection_if_unadopted(1, 99) is None
    else:
        with pytest.raises(HTTPException) as denied:
            service.run_legacy_projection_if_unadopted(1, 99)
        assert denied.value.status_code == status and denied.value.detail["code"] == code
