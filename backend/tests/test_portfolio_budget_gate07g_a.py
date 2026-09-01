"""Gate 07G-A acceptance coverage for OPC budget-alignment enhancements."""

from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from tests.test_portfolio_budget_gate07g import _fixture, _target

from app.main import app
from app.modules.portfolio_budget.schemas import (
    BudgetScenarioCreateIn,
    ProjectDependencyCreateIn,
    ScenarioSelectionIn,
)
from app.modules.portfolio_budget.service import PortfolioBudgetService


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _scenario(service: PortfolioBudgetService, portfolio_id: int, target_id: int, analysis_hash: str):
    return service.create_scenario(
        portfolio_id,
        BudgetScenarioCreateIn(
            scenario_name="07G-A alignment",
            budget_target_id=target_id,
            creation_mode="FROM_CURRENT_PRIORITY",
            time_phasing_method="UNPHASED",
            expected_analysis_hash=analysis_hash,
            idempotency_key=f"07ga-scenario-{uuid4()}",
        ),
    )


def test_waterline_reuses_rank_and_exposes_governed_budget_breakdown() -> None:
    db, tenant_id, actor_id, portfolio, projects, _excluded = _fixture()
    try:
        service = PortfolioBudgetService(db, tenant_id, actor_id)
        analysis = service._analysis(portfolio.id, require_budget=True)
        source_cost = next(
            row.rom_cost for row in analysis.dataset.rows if row.project_workspace_id == projects[0][0].id
        )
        project = projects[0][0]
        defaults = deepcopy(project.defaults_json or {})
        defaults["planning_budget_breakdown"] = {
            "capex_amount": str(source_cost * Decimal("0.6")),
            "expense_amount": str(source_cost * Decimal("0.2")),
            "source_reference": "FIN-CONTROL-2027",
        }
        project.defaults_json = defaults
        db.commit()

        target = _target(service, portfolio.id)
        scenario = _scenario(service, portfolio.id, target.id, analysis.dataset.analysis_hash)
        waterline = service.waterline(scenario.id)

        assert [item.portfolio_rank for item in waterline.projects] == [1, 2, 3]
        assert waterline.rank_source == "GATE07E_CONTEXTUAL_PORTFOLIO_RANK"
        assert waterline.alignment_status == "GATE07G_A_OPC_ALIGNMENT_VALIDATED"
        first = next(item for item in scenario.projects if item.project_workspace_id == project.id)
        assert first.capex_amount is not None
        assert first.expense_amount is not None
        assert first.capex_amount + first.expense_amount + first.unclassified_amount == first.cost_value
        assert waterline.budget_breakdown["unclassified"] >= 0
    finally:
        db.close()


def test_dependency_graph_blocks_freeze_and_rejects_cycles_idempotently() -> None:
    db, tenant_id, actor_id, portfolio, projects, _excluded = _fixture()
    try:
        service = PortfolioBudgetService(db, tenant_id, actor_id)
        target = _target(service, portfolio.id)
        analysis = service._analysis(portfolio.id, require_budget=True)
        scenario = _scenario(service, portfolio.id, target.id, analysis.dataset.analysis_hash)
        predecessor = projects[0][0]
        successor = projects[1][0]
        key = f"dependency-{uuid4()}"
        payload = ProjectDependencyCreateIn(
            predecessor_project_workspace_id=predecessor.id,
            successor_project_workspace_id=successor.id,
            dependency_type="PREREQUISITE",
            dependency_strength="MANDATORY",
            description="Successor requires predecessor",
            idempotency_key=key,
        )
        dependency = service.create_project_dependency(portfolio.id, payload)
        retry = service.create_project_dependency(portfolio.id, payload)
        assert retry.id == dependency.id

        scenario = service.select_project(
            scenario.id,
            predecessor.id,
            scenario.revision_version,
            ScenarioSelectionIn(
                selection_state="FORCED_OUT",
                forced_reason="Governed deferral",
                idempotency_key=f"force-out-{uuid4()}",
            ),
        )
        evaluated = service.scenario_dependencies(scenario.id)
        assert evaluated.summary["unmet_mandatory_count"] == 1
        assert "UNMET_MANDATORY_PROJECT_DEPENDENCY" in evaluated.blockers
        with pytest.raises(HTTPException) as blocked:
            service.freeze_scenario(scenario.id, scenario.revision_version, f"freeze-{uuid4()}")
        assert blocked.value.detail["code"] == "BUDGET_SCENARIO_NOT_READY"

        with pytest.raises(HTTPException) as cycle:
            service.create_project_dependency(
                portfolio.id,
                ProjectDependencyCreateIn(
                    predecessor_project_workspace_id=successor.id,
                    successor_project_workspace_id=predecessor.id,
                    dependency_type="PREREQUISITE",
                    dependency_strength="MANDATORY",
                    idempotency_key=f"cycle-{uuid4()}",
                ),
            )
        assert cycle.value.detail["code"] == "PROJECT_DEPENDENCY_CYCLE"
    finally:
        db.close()


def test_forced_conflict_and_transitive_unmet_dependency_are_derived() -> None:
    db, tenant_id, actor_id, portfolio, projects, _excluded = _fixture()
    try:
        service = PortfolioBudgetService(db, tenant_id, actor_id)
        target = _target(service, portfolio.id)
        analysis = service._analysis(portfolio.id, require_budget=True)
        scenario = _scenario(service, portfolio.id, target.id, analysis.dataset.analysis_hash)
        first, second, third = (item[0] for item in projects[:3])
        for predecessor, successor in ((first, second), (second, third)):
            service.create_project_dependency(
                portfolio.id,
                ProjectDependencyCreateIn(
                    predecessor_project_workspace_id=predecessor.id,
                    successor_project_workspace_id=successor.id,
                    dependency_strength="MANDATORY",
                    idempotency_key=f"chain-{uuid4()}",
                ),
            )
        scenario = service.select_project(
            scenario.id,
            first.id,
            scenario.revision_version,
            ScenarioSelectionIn(
                selection_state="FORCED_OUT",
                forced_reason="Controlled exclusion",
                idempotency_key=f"force-out-{uuid4()}",
            ),
        )
        scenario = service.select_project(
            scenario.id,
            second.id,
            scenario.revision_version,
            ScenarioSelectionIn(
                selection_state="FORCED_IN",
                forced_reason="Strategic commitment",
                idempotency_key=f"force-in-{uuid4()}",
            ),
        )
        scenario = service.select_project(
            scenario.id,
            third.id,
            scenario.revision_version,
            ScenarioSelectionIn(selection_state="SELECTED", idempotency_key=f"select-{uuid4()}"),
        )
        evaluated = service.scenario_dependencies(scenario.id)
        assert evaluated.summary["forced_dependency_conflict_count"] == 1
        third_result = next(item for item in evaluated.projects if item["project_workspace_id"] == third.id)
        assert any(item["issue"] == "TRANSITIVE_UNMET_DEPENDENCY" for item in third_result["details"])
    finally:
        db.close()
