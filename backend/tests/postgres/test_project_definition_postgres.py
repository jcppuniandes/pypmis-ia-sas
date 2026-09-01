"""Real PostgreSQL acceptance checks for Gate 07J-FEL."""

import pytest
from sqlalchemy import inspect
from tests.test_portfolio_convergence_gate07i import _fixture
from tests.test_project_definition_gate07j_fel import (
    _complete_current,
    _framework,
    _reviewer,
)

from app.database.session import engine
from app.modules.project_definition.schemas import StartFELIn
from app.modules.project_definition.service import ProjectDefinitionService

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL Gate 07J-FEL evidence required")


def test_gate07j_fel_postgresql_schema_and_governed_evidence_lifecycle() -> None:
    assert {
        "project_fel_statuses",
        "project_definition_assessments",
        "project_definition_actions",
    }.issubset(set(inspect(engine).get_table_names()))
    db, tenant_id, actor_id, _portfolio, projects, _budget, _resource = _fixture()
    try:
        framework = _framework(db, tenant_id, actor_id)
        service = ProjectDefinitionService(db, tenant_id, actor_id)
        project = projects[0]
        service.start_fel(
            project.id,
            StartFELIn(framework_configuration_id=framework.id, idempotency_key="postgres-gate07j-fel-start"),
        )
        _complete_current(service, project.id)
        evidence = service.investment_gate_evidence(project.id)
        assert evidence.can_supply_investment_gate_evidence is True
        submitted = service.submit_stage_review(
            project.id, service.fel_status(project.id).revision_version, "postgres-gate07j-fel-submit"
        )
        reviewer = _reviewer(db, tenant_id)
        next_stage = ProjectDefinitionService(db, tenant_id, reviewer.id).complete_stage(
            project.id, submitted.revision_version, "postgres-gate07j-fel-stage-complete"
        )
        assert next_stage.current_stage_code == "FEL-2"
        assert next_stage.status == "IN_STAGE"
    finally:
        db.close()
