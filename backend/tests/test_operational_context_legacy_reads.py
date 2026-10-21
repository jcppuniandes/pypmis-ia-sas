"""Legacy ADMIN bootstrap queries cannot bypass the canonical write boundary."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from tests.operational_context_fixture import create_o1a_fixture

from app.core.time import utc_now
from app.database.session import SessionLocal, engine
from app.domain.models import KPI, ProjectMembership
from app.main import app


@pytest.fixture
def fixture():
    with TestClient(app) as client, SessionLocal() as db:
        fixture = create_o1a_fixture(db)
        db.add(
            ProjectMembership(
                tenant_id=fixture.tenant_id,
                project_id=fixture.legacy_project_id,
                user_id=fixture.users["admin"].id,
                role="Control Manager",
                can_configure=True,
            )
        )
        db.commit()
        fixture.client, fixture.db = client, db
        yield fixture


def read_without_write(fixture):
    writes = []

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            writes.append(statement.split()[0])

    event.listen(engine, "before_cursor_execute", observe)
    try:
        response = fixture.client.get(
            f"/api/v1/projects/{fixture.legacy_project_id}/dashboard", headers=fixture.headers["admin"]
        )
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert response.status_code == 200, response.text
    assert writes == [], "Legacy GET must not generate KPI/snapshot/forecast/plan or bootstrap data"
    return response.json()


def test_dashboard_without_cycle_is_read_only_before_binding_and_admin_onboarding(fixture):
    data = read_without_write(fixture)
    assert data["project_kpi_is_persisted"] is False
    assert data["project_kpi"]["id"] == 0 and data["project_kpi"]["period"] == "NOT_GENERATED"
    assert data["control_plan"] is None
    assert data["control_snapshots"] == [] and data["forecast_scenarios"] == []


def test_dashboard_with_kpi_but_without_history_reads_existing_value_without_regeneration(fixture):
    row = KPI(
        tenant_id=fixture.tenant_id,
        project_id=fixture.legacy_project_id,
        control_account_id=None,
        period="EXISTING_LEGACY",
        pv=100,
        ev=80,
        ac=90,
        spi=0.8,
        cpi=0.889,
        sv=-20,
        cv=-10,
        bac=120,
        eac=135,
        etc=45,
        vac=-15,
        created_at=utc_now(),
    )
    fixture.db.add(row)
    fixture.db.commit()
    row_id = row.id
    data = read_without_write(fixture)
    assert data["project_kpi_is_persisted"] is True
    assert data["project_kpi"]["id"] == row_id and data["project_kpi"]["ev"] == 80
    fixture.db.expire_all()
    assert fixture.db.scalar(select(KPI.id).where(KPI.id == row_id)) == row_id
    assert data["control_snapshots"] == [] and data["forecast_scenarios"] == []
