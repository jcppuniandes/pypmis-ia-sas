"""Real PostgreSQL acceptance checks for Gate 07H Portfolio Resource Planning."""

from uuid import uuid4

import pytest
from sqlalchemy import inspect, select
from tests.test_portfolio_resource_gate07h import _capacity, _demand, _fixture, _scenario

from app.database.session import engine
from app.domain.models import SecurityEvent
from app.modules.portfolio_resource.schemas import ScenarioSelectionIn, ScenarioTimingIn
from app.modules.portfolio_resource.service import PortfolioResourceService

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL Gate 07H evidence required")


def test_gate07h_postgresql_schema_and_governed_resource_lifecycle() -> None:
    tables = set(inspect(engine).get_table_names())
    assert {
        "portfolio_resource_capacity_plans",
        "portfolio_resource_capacity_periods",
        "project_resource_demand_profiles",
        "project_resource_demand_periods",
        "portfolio_resource_scenarios",
        "portfolio_resource_scenario_projects",
    }.issubset(tables)

    db, tenant_id, actor_id, portfolio, projects, _ = _fixture(projects=2)
    try:
        service = PortfolioResourceService(db, tenant_id, actor_id)
        capacity = _capacity(service, portfolio.id, capacity="1.0")
        for project in projects:
            _demand(service, project.id)
        scenario = _scenario(service, portfolio.id, capacity.id)

        forced = service.select_project(
            scenario.id,
            projects[0].id,
            scenario.revision_version,
            ScenarioSelectionIn(
                selection_state="FORCED_IN",
                forced_reason="Approved strategic resource obligation",
                authority_reference="BOARD-2026-07H",
                idempotency_key=f"pg-resource-force-{uuid4()}",
            ),
        )
        shifted = service.adjust_timing(
            forced.id,
            projects[0].id,
            forced.revision_version,
            ScenarioTimingIn(
                timing_method="SHIFT_START_KEEP_DURATION",
                scenario_start="2028-01-01",
                idempotency_key=f"pg-resource-shift-{uuid4()}",
            ),
        )
        frozen = service.freeze_scenario(shifted.id, shifted.revision_version, f"pg-resource-freeze-{uuid4()}")

        assert frozen.status == "FROZEN"
        assert frozen.projects[0].forced_reason == "Approved strategic resource obligation"
        assert frozen.projects[0].schedule_shift_days > 0
        assert frozen.summary.demand_coverage_percent == 100
        event_types = set(
            db.scalars(
                select(SecurityEvent.event_type).where(
                    SecurityEvent.tenant_id == tenant_id,
                    SecurityEvent.event_type.in_(
                        [
                            "portfolio_resource.project_forced_in",
                            "portfolio_resource.scenario_timing_adjusted",
                            "portfolio_resource.scenario_frozen",
                        ]
                    ),
                )
            )
        )
        assert event_types == {
            "portfolio_resource.project_forced_in",
            "portfolio_resource.scenario_timing_adjusted",
            "portfolio_resource.scenario_frozen",
        }
    finally:
        db.close()
