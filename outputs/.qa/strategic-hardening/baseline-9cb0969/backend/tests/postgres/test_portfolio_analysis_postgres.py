"""Real PostgreSQL acceptance checks for Gate 07F derived Portfolio Analysis."""

import pytest
from sqlalchemy import inspect, select
from tests.test_portfolio_analysis_gate07f import _complete, _context, _portfolio, _project

from app.database.session import SessionLocal, engine
from app.domain.models import AdminConfiguration
from app.modules.portfolio_analysis.schemas import AnalysisFiltersIn
from app.modules.portfolio_analysis.service import PortfolioAnalysisService
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL Gate 07F evidence required")


def test_gate07f_is_deterministic_and_adds_no_snapshot_schema() -> None:
    assert "portfolio_analysis_snapshots" not in inspect(engine).get_table_names()
    tenant_id, actor_id, parent = _context()
    with SessionLocal() as db:
        portfolio = _portfolio(db, tenant_id, actor_id, parent)
        projects = [
            _project(db, tenant_id, actor_id, parent, portfolio, name=f"PostgreSQL Analysis {index}")
            for index in range(3)
        ]
        db.commit()
        evaluation = PortfolioEvaluationService(db, tenant_id, actor_id)
        for (project, _membership), rating in zip(projects, (5, 4, 3), strict=True):
            _complete(evaluation, portfolio.id, project.id, rating)

        service = PortfolioAnalysisService(db, tenant_id, actor_id)
        first = service.overview(portfolio.id)
        second = service.overview(portfolio.id)
        filtered = service.dataset(portfolio.id, AnalysisFiltersIn(project_type="NOT_PRESENT"))

        assert first.dataset.analysis_hash == second.dataset.analysis_hash == filtered.analysis_hash
        assert [row.portfolio_rank for row in first.dataset.rows] == [1, 2, 3]
        assert filtered.rows == []
        assert first.readiness.final_output == "READY_FOR_PORTFOLIO_SCENARIO_PLANNING"


def test_gate07f_keeps_portfolios_isolated_and_applies_currency_guardrail() -> None:
    tenant_id, actor_id, parent = _context()
    with SessionLocal() as db:
        mixed = _portfolio(db, tenant_id, actor_id, parent)
        separate = _portfolio(db, tenant_id, actor_id, parent)
        cop, _ = _project(db, tenant_id, actor_id, parent, mixed, name="COP Project", currency="COP")
        usd, _ = _project(db, tenant_id, actor_id, parent, mixed, name="USD Project", currency="USD")
        other, _ = _project(
            db, tenant_id, actor_id, parent, separate, name="Separate Portfolio Project", currency="COP"
        )
        db.commit()
        evaluation = PortfolioEvaluationService(db, tenant_id, actor_id)
        _complete(evaluation, mixed.id, cop.id, 5)
        _complete(evaluation, mixed.id, usd.id, 4)
        _complete(evaluation, separate.id, other.id, 3)

        service = PortfolioAnalysisService(db, tenant_id, actor_id)
        mixed_overview = service.overview(mixed.id)
        separate_overview = service.overview(separate.id)

        assert {row.project_workspace_id for row in mixed_overview.dataset.rows} == {cop.id, usd.id}
        assert [row.project_workspace_id for row in separate_overview.dataset.rows] == [other.id]
        assert mixed_overview.dataset.analysis_hash != separate_overview.dataset.analysis_hash
        assert "MULTI_CURRENCY_NOT_NORMALIZED" in mixed_overview.dataset.warnings
        assert mixed_overview.investor_map.size_metric_applied is False
        assert mixed_overview.summary.rom_cost_total is None
        assert mixed_overview.readiness.can_enter_budget_planning is False
        assert mixed_overview.readiness.can_enter_resource_planning is True
        assert mixed_overview.readiness.can_enter_portfolio_scenario_planning is True


def test_gate07f_admin_preview_does_not_persist_configuration_or_analysis_rows() -> None:
    tenant_id, actor_id, parent = _context()
    with SessionLocal() as db:
        portfolio = _portfolio(db, tenant_id, actor_id, parent)
        project, _ = _project(db, tenant_id, actor_id, parent, portfolio, name="Preview Source Project")
        db.commit()
        _complete(PortfolioEvaluationService(db, tenant_id, actor_id), portfolio.id, project.id, 5)
        service = PortfolioAnalysisService(db, tenant_id, actor_id)
        record = db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == tenant_id,
                AdminConfiguration.kind == "portfolio_analysis_configuration",
                AdminConfiguration.status == "published",
                AdminConfiguration.content_json["scope"]["workspace_id"].as_integer() == portfolio.id,
            )
        )
        assert record is not None
        version_before = record.version
        hash_before = service.dataset(portfolio.id).analysis_hash

        preview = service.configuration_preview(portfolio.id, record.id, record.content_json)

        db.refresh(record)
        assert preview.persisted is False
        assert record.version == version_before
        assert service.dataset(portfolio.id).analysis_hash == hash_before
        assert "portfolio_analysis_snapshots" not in inspect(engine).get_table_names()
