"""Gate 07F acceptance coverage for derived Portfolio Analysis."""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, UserAccount
from app.main import app
from app.modules.portfolio_analysis.schemas import AnalysisFiltersIn
from app.modules.portfolio_analysis.service import DEFAULT_CONFIGURATION, PortfolioAnalysisService, _hash
from app.modules.portfolio_evaluation.schemas import CriterionRatingIn, EvaluationUpdateIn
from app.modules.portfolio_evaluation.service import (
    DEFAULT_CONFIGURATION as EVALUATION_CONFIGURATION,
)
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService
from app.modules.portfolio_planning.models import PortfolioProjectMembership


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _context() -> tuple[int, int, EnterpriseWorkspace]:
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        assert admin is not None
        parent = db.scalar(
            select(EnterpriseWorkspace)
            .where(
                EnterpriseWorkspace.tenant_id == admin.tenant_id,
                EnterpriseWorkspace.workspace_type_code == "enterprise",
            )
            .order_by(EnterpriseWorkspace.id)
        )
        if parent is None:
            suffix = uuid4().hex[:10]
            parent = EnterpriseWorkspace(
                tenant_id=admin.tenant_id,
                parent_id=None,
                workspace_type_code="enterprise",
                code=f"G07F-ENT-{suffix}",
                external_key=f"gate07f-enterprise-{suffix}",
                record_code=f"G07F.{suffix}",
                name="Gate 07F Test Enterprise",
                status="active",
                defaults_json={},
                sort_order=96,
                version=1,
                created_by_user_id=admin.id,
            )
            db.add(parent)
            db.commit()
            db.refresh(parent)
        return admin.tenant_id, admin.id, parent


def _portfolio(db, tenant_id: int, actor_id: int, parent: EnterpriseWorkspace) -> EnterpriseWorkspace:
    suffix = uuid4().hex[:10]
    portfolio = EnterpriseWorkspace(
        tenant_id=tenant_id,
        parent_id=parent.id,
        workspace_type_code="portfolio",
        code=f"G07F-PF-{suffix}",
        external_key=f"gate07f-portfolio-{suffix}",
        record_code=f"{parent.record_code}.G07F.{suffix}",
        name=f"Gate 07F Portfolio {suffix}",
        status="active",
        defaults_json={},
        sort_order=97,
        version=1,
        created_by_user_id=actor_id,
    )
    db.add(portfolio)
    db.flush()
    matrix = deepcopy(EVALUATION_CONFIGURATION)
    matrix["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    analysis = deepcopy(DEFAULT_CONFIGURATION)
    analysis["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    db.add_all(
        [
            AdminConfiguration(
                tenant_id=tenant_id,
                kind="portfolio_evaluation_configuration",
                code=f"gate07e-for-{suffix}",
                name="Gate 07E Matrix for Gate 07F",
                description="Isolated acceptance fixture.",
                status="published",
                revision=1,
                version=1,
                content_json=matrix,
                content_hash=_hash(matrix),
                created_by_user_id=actor_id,
            ),
            AdminConfiguration(
                tenant_id=tenant_id,
                kind="portfolio_analysis_configuration",
                code=f"gate07f-{suffix}",
                name="Gate 07F Analysis",
                description="Isolated acceptance fixture.",
                status="published",
                revision=1,
                version=1,
                content_json=analysis,
                content_hash=_hash(analysis),
                created_by_user_id=actor_id,
            ),
        ]
    )
    return portfolio


def _project(
    db,
    tenant_id: int,
    actor_id: int,
    parent: EnterpriseWorkspace,
    portfolio: EnterpriseWorkspace,
    *,
    name: str,
    currency: str = "COP",
    governance_model: str = "CAPITAL_OWNER",
) -> tuple[EnterpriseWorkspace, PortfolioProjectMembership]:
    suffix = uuid4().hex[:10]
    project = EnterpriseWorkspace(
        tenant_id=tenant_id,
        parent_id=parent.id,
        workspace_type_code="project",
        code=f"G07F-PRJ-{suffix}",
        external_key=f"gate07f-project-{suffix}",
        record_code=f"{parent.record_code}.G07F.PRJ.{suffix}",
        name=name,
        status="pending",
        defaults_json={},
        sort_order=98,
        version=1,
        created_by_user_id=actor_id,
    )
    db.add(project)
    db.flush()
    snapshot = {
        "project_workspace_id": project.id,
        "project_number": project.code,
        "project_name": name,
        "workspace_status": "pending",
        "planning_origin": "STRATEGIC_GATE",
        "planning_stage": "PORTFOLIO_AND_FEL_PLANNING",
        "strategic_objectives": [{"code": "GROWTH", "name": "Growth"}],
        "proposal_score": "82.0000",
        "rom_cost": "2500000",
        "currency": currency,
        "target_start": "2027-01-01",
        "target_finish": "2028-01-01",
        "expected_benefits": "Controlled Portfolio value",
        "risk_summary": [{"code": "R-1", "level": "medium"}],
    }
    planning_hash = _hash(snapshot)
    project.defaults_json = {
        "_project": {"governance_model": governance_model, "planning_origin": "STRATEGIC_GATE"},
        "_portfolio_planning": {
            "status": "READY_FOR_PORTFOLIO_PLANNING",
            "snapshot": snapshot,
            "planning_entry_hash": planning_hash,
            "blocking_issues": [],
        },
    }
    membership = PortfolioProjectMembership(
        tenant_id=tenant_id,
        portfolio_workspace_id=portfolio.id,
        project_workspace_id=project.id,
        membership_source="STRATEGIC_INTAKE",
        is_target_portfolio=True,
        status="ACTIVE",
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(membership)
    db.flush()
    return project, membership


def _complete(service: PortfolioEvaluationService, portfolio_id: int, project_id: int, rating: int):
    ratings = [
        CriterionRatingIn(
            criterion_code=str(item["code"]),
            rating=rating,
            evidence=f"G07F-EVIDENCE-{item['code']}",
            comment="Gate 07F source evaluation.",
        )
        for item in EVALUATION_CONFIGURATION["criteria"]
    ]
    started = service.start_evaluation(portfolio_id, project_id, f"g07f-start-{uuid4()}")
    updated = service.update_evaluation(
        started.id,
        started.revision_version,
        EvaluationUpdateIn(ratings=ratings, comments="Gate 07F source complete."),
    )
    return service.complete_evaluation(updated.id, updated.revision_version, f"g07f-complete-{uuid4()}")


def test_analysis_reuses_gate07e_rank_and_produces_map_scorecard_and_readiness() -> None:
    tenant_id, actor_id, parent = _context()
    with SessionLocal() as db:
        portfolio = _portfolio(db, tenant_id, actor_id, parent)
        projects = [
            _project(db, tenant_id, actor_id, parent, portfolio, name=f"Analysis Project {index}") for index in range(3)
        ]
        db.commit()
        evaluation = PortfolioEvaluationService(db, tenant_id, actor_id)
        for (project, _membership), rating in zip(projects, (5, 4, 3), strict=True):
            _complete(evaluation, portfolio.id, project.id, rating)

        service = PortfolioAnalysisService(db, tenant_id, actor_id)
        overview = service.overview(portfolio.id)

        assert [item.project_workspace_id for item in overview.dataset.rows] == [item[0].id for item in projects]
        assert [item.portfolio_rank for item in overview.dataset.rows] == [1, 2, 3]
        assert len(overview.investor_map.points) == 3
        assert len(overview.scorecard.rows) == 3
        assert overview.summary.rom_cost_total == 7500000
        assert overview.readiness.status == "READY"
        assert overview.readiness.final_output == "READY_FOR_PORTFOLIO_SCENARIO_PLANNING"
        assert overview.readiness.can_enter_budget_planning is True
        assert overview.readiness.can_enter_resource_planning is True
        assert "can_enter_portfolio_scenario_planning" in overview.readiness.allowed_actions


def test_currency_guardrail_disables_monetary_size_and_budget_branch_only() -> None:
    tenant_id, actor_id, parent = _context()
    with SessionLocal() as db:
        portfolio = _portfolio(db, tenant_id, actor_id, parent)
        first, _ = _project(db, tenant_id, actor_id, parent, portfolio, name="COP Project", currency="COP")
        second, _ = _project(db, tenant_id, actor_id, parent, portfolio, name="USD Project", currency="USD")
        db.commit()
        evaluation = PortfolioEvaluationService(db, tenant_id, actor_id)
        _complete(evaluation, portfolio.id, first.id, 5)
        _complete(evaluation, portfolio.id, second.id, 4)

        overview = PortfolioAnalysisService(db, tenant_id, actor_id).overview(portfolio.id)

        assert "MULTI_CURRENCY_NOT_NORMALIZED" in overview.dataset.warnings
        assert "ROM_COST_BUBBLE_SIZE_DISABLED" in overview.investor_map.warnings
        assert overview.investor_map.size_metric_applied is False
        assert overview.summary.rom_cost_total is None
        assert overview.readiness.can_enter_portfolio_scenario_planning is True
        assert overview.readiness.can_enter_budget_planning is False
        assert overview.readiness.can_enter_resource_planning is True


def test_filters_are_non_mutating_and_stale_source_hash_is_rejected() -> None:
    tenant_id, actor_id, parent = _context()
    with SessionLocal() as db:
        portfolio = _portfolio(db, tenant_id, actor_id, parent)
        first, membership = _project(db, tenant_id, actor_id, parent, portfolio, name="Filter Project")
        db.commit()
        _complete(PortfolioEvaluationService(db, tenant_id, actor_id), portfolio.id, first.id, 5)
        service = PortfolioAnalysisService(db, tenant_id, actor_id)
        before = service.dataset(portfolio.id)
        filtered = service.dataset(portfolio.id, AnalysisFiltersIn(project_type="NOT_PRESENT"))
        assert filtered.rows == []
        assert filtered.analysis_hash == before.analysis_hash

        membership.membership_source = "MANUAL"
        db.commit()
        with pytest.raises(HTTPException) as stale:
            service.preview(portfolio.id, AnalysisFiltersIn(), before.analysis_hash)
        assert stale.value.status_code == 412
        assert stale.value.detail["code"] == "STALE_PORTFOLIO_ANALYSIS_SOURCE"


def test_admin_draft_preview_is_nonpersistent_and_etag_is_enforced() -> None:
    tenant_id, actor_id, parent = _context()
    with SessionLocal() as db:
        portfolio = _portfolio(db, tenant_id, actor_id, parent)
        project, _ = _project(db, tenant_id, actor_id, parent, portfolio, name="Admin Preview Project")
        db.commit()
        _complete(PortfolioEvaluationService(db, tenant_id, actor_id), portfolio.id, project.id, 5)
        service = PortfolioAnalysisService(db, tenant_id, actor_id)
        published = db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == tenant_id,
                AdminConfiguration.kind == "portfolio_analysis_configuration",
                AdminConfiguration.status == "published",
                AdminConfiguration.content_json["scope"]["workspace_id"].as_integer() == portfolio.id,
            )
        )
        assert published is not None
        clone = service.clone_configuration(published.id, published.version)
        changed = deepcopy(clone.content_json)
        changed["investor_map"]["x_axis"] = "proposal_score"

        preview = service.configuration_preview(portfolio.id, clone.id, changed)

        assert preview.persisted is False
        assert preview.publishable is True
        assert preview.effective["investor_map"]["x_axis"] == "proposal_score"
        persisted = db.get(AdminConfiguration, clone.id)
        assert (
            persisted is not None and persisted.content_json["investor_map"]["x_axis"] == "portfolio_evaluation_score"
        )
        stale_version = clone.version
        updated = service.update_configuration(clone.id, stale_version, clone.name, clone.description, changed)
        with pytest.raises(HTTPException) as stale:
            service.update_configuration(clone.id, stale_version, clone.name, clone.description, changed)
        assert stale.value.status_code == 412
        published_clone = service.publish_configuration(updated.id, updated.version)
        assert published_clone.status == "published"


def test_invalid_metric_catalog_and_selection_semantics_are_rejected() -> None:
    tenant_id, actor_id, _parent = _context()
    with SessionLocal() as db:
        service = PortfolioAnalysisService(db, tenant_id, actor_id)
        invalid = deepcopy(DEFAULT_CONFIGURATION)
        invalid["investor_map"]["size"] = "project_name"
        issues = service._configuration_issues(invalid)
        assert "METRIC_NOT_ALLOWED_FOR_SIZE" in issues
        assert "BUBBLE_SIZE_METRIC_MUST_BE_NON_NEGATIVE" in issues

        forbidden = deepcopy(DEFAULT_CONFIGURATION)
        forbidden["selection"] = "FORCED_IN"
        assert "DOWNSTREAM_OR_SELECTION_CAPABILITY_NOT_ALLOWED_IN_GATE07F" in service._configuration_issues(forbidden)
