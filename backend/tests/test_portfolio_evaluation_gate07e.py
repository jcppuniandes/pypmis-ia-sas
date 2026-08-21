"""Gate 07E acceptance coverage for scoring, ranking and applicability."""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, UserAccount
from app.main import app
from app.modules.portfolio_evaluation.models import PortfolioProjectEvaluation
from app.modules.portfolio_evaluation.schemas import CriterionRatingIn, EvaluationUpdateIn
from app.modules.portfolio_evaluation.service import DEFAULT_CONFIGURATION, PortfolioEvaluationService, _hash
from app.modules.portfolio_planning.models import PortfolioProjectMembership


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _workspace_context() -> tuple[int, int, EnterpriseWorkspace]:
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
                code=f"G07E-ENT-{suffix}",
                external_key=f"gate07e-enterprise-{suffix}",
                record_code=f"G07E.{suffix}",
                name="Gate 07E Test Enterprise",
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


def _portfolio(db, tenant_id: int, actor_id: int, parent: EnterpriseWorkspace, name: str) -> EnterpriseWorkspace:
    suffix = uuid4().hex[:10]
    record = EnterpriseWorkspace(
        tenant_id=tenant_id,
        parent_id=parent.id,
        workspace_type_code="portfolio",
        code=f"G07E-PF-{suffix}",
        external_key=f"gate07e-portfolio-{suffix}",
        record_code=f"{parent.record_code}.G07E.{suffix}",
        name=name,
        status="active",
        defaults_json={},
        sort_order=97,
        version=1,
        created_by_user_id=actor_id,
    )
    db.add(record)
    db.flush()
    content = deepcopy(DEFAULT_CONFIGURATION)
    content["scope"] = {"type": "portfolio", "workspace_id": record.id}
    configuration = AdminConfiguration(
        tenant_id=tenant_id,
        kind="portfolio_evaluation_configuration",
        code=f"gate07e-{suffix}",
        name=f"Matrix {name}",
        description="Published only by this isolated acceptance fixture.",
        status="published",
        revision=1,
        version=1,
        content_json=content,
        content_hash=_hash(content),
        created_by_user_id=actor_id,
    )
    db.add(configuration)
    return record


def _project(
    db,
    tenant_id: int,
    actor_id: int,
    parent: EnterpriseWorkspace,
    portfolio: EnterpriseWorkspace,
    *,
    governance_model: str = "CAPITAL_OWNER",
    name: str = "Gate 07E Project",
) -> tuple[EnterpriseWorkspace, PortfolioProjectMembership]:
    suffix = uuid4().hex[:10]
    snapshot = {
        "project_workspace_id": 0,
        "project_number": f"G07E-PRJ-{suffix}",
        "project_name": name,
        "workspace_status": "pending",
        "planning_origin": "STRATEGIC_GATE",
        "planning_stage": "PORTFOLIO_AND_FEL_PLANNING",
        "strategic_gate_decision": {"id": 700, "decision_number": f"SGD-{suffix}"},
        "project_proposal": {"id": 701, "proposal_number": f"PROP-{suffix}"},
        "source_idea": {"id": 702, "idea_number": f"IDEA-{suffix}"},
        "target_portfolio": {"id": portfolio.id, "name": portfolio.name},
        "strategic_objectives": [{"code": "GROWTH", "name": "Growth"}],
        "proposal_score": "80.0000",
        "rom_cost": "2500000",
        "target_start": "2027-01-01",
        "target_finish": "2028-01-01",
        "expected_benefits": "Controlled capacity increase",
        "risk_summary": [{"code": "R-1", "level": "medium"}],
    }
    project = EnterpriseWorkspace(
        tenant_id=tenant_id,
        parent_id=parent.id,
        workspace_type_code="project",
        code=f"G07E-PRJ-{suffix}",
        external_key=f"gate07e-project-{suffix}",
        record_code=f"{parent.record_code}.G07E.PRJ.{suffix}",
        name=name,
        status="pending",
        defaults_json={},
        sort_order=98,
        version=1,
        created_by_user_id=actor_id,
    )
    db.add(project)
    db.flush()
    snapshot["project_workspace_id"] = project.id
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


def _ratings(value: int) -> list[CriterionRatingIn]:
    return [
        CriterionRatingIn(
            criterion_code=str(item["code"]),
            rating=value,
            evidence=f"EVIDENCE-{item['code']}",
            comment="Controlled Gate 07E acceptance evidence.",
        )
        for item in DEFAULT_CONFIGURATION["criteria"]
    ]


def _complete(service: PortfolioEvaluationService, portfolio_id: int, project_id: int, value: int):
    started = service.start_evaluation(portfolio_id, project_id, f"start-{uuid4()}")
    updated = service.update_evaluation(
        started.id,
        started.revision_version,
        EvaluationUpdateIn(ratings=_ratings(value), comments="Gate 07E evaluation complete."),
    )
    return service.complete_evaluation(updated.id, updated.revision_version, f"complete-{uuid4()}")


def test_capital_owner_scoring_is_deterministic_and_completed_snapshot_is_immutable() -> None:
    tenant_id, actor_id, parent = _workspace_context()
    with SessionLocal() as db:
        portfolio = _portfolio(db, tenant_id, actor_id, parent, "Gate 07E Capital Portfolio")
        project, _membership = _project(db, tenant_id, actor_id, parent, portfolio)
        db.commit()
        completed = _complete(PortfolioEvaluationService(db, tenant_id, actor_id), portfolio.id, project.id, 5)
        assert completed.status == "COMPLETED"
        assert str(completed.normalized_score) == "100.0000"
        assert len(completed.score_components) == 7
        persisted = db.get(PortfolioProjectEvaluation, completed.id)
        assert persisted is not None
        persisted.comments = "Forbidden mutation"
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
        db.rollback()


def test_contractor_and_legacy_projects_are_blocked_by_default() -> None:
    tenant_id, actor_id, parent = _workspace_context()
    with SessionLocal() as db:
        portfolio = _portfolio(db, tenant_id, actor_id, parent, "Gate 07E Applicability Portfolio")
        contractor, _membership = _project(
            db,
            tenant_id,
            actor_id,
            parent,
            portfolio,
            governance_model="CONTRACTOR_DELIVERY",
            name="Contractor Delivery Project",
        )
        legacy, _membership = _project(
            db,
            tenant_id,
            actor_id,
            parent,
            portfolio,
            governance_model="",
            name="Legacy Project",
        )
        defaults = dict(legacy.defaults_json)
        defaults["_project"] = {}
        legacy.defaults_json = defaults
        direct, _membership = _project(
            db,
            tenant_id,
            actor_id,
            parent,
            portfolio,
            governance_model="DIRECT_INTERNAL",
            name="Direct Internal Project",
        )
        db.commit()
        service = PortfolioEvaluationService(db, tenant_id, actor_id)
        for project, blocker in (
            (contractor, "GOVERNANCE_MODEL_CONTRACTOR_DELIVERY_NOT_APPLICABLE"),
            (direct, "GOVERNANCE_MODEL_DIRECT_INTERNAL_NOT_APPLICABLE"),
            (legacy, "GOVERNANCE_MODEL_LEGACY_NOT_APPLICABLE"),
        ):
            with pytest.raises(HTTPException) as blocked:
                service.start_evaluation(portfolio.id, project.id, f"blocked-{uuid4()}")
            assert blocked.value.status_code == 422
            assert blocker in blocked.value.detail["blocking_issues"]


def test_contextual_ranking_is_deterministic_and_inactive_membership_is_excluded() -> None:
    tenant_id, actor_id, parent = _workspace_context()
    with SessionLocal() as db:
        portfolio = _portfolio(db, tenant_id, actor_id, parent, "Gate 07E Ranking Portfolio")
        projects = [
            _project(db, tenant_id, actor_id, parent, portfolio, name=f"Rank Project {index}") for index in range(3)
        ]
        db.commit()
        service = PortfolioEvaluationService(db, tenant_id, actor_id)
        completed = [
            _complete(service, portfolio.id, project.id, value)
            for (project, _membership), value in zip(projects, (3, 5, 4), strict=True)
        ]
        ranking = service.prioritization(portfolio.id)
        assert [item.project_workspace_id for item in ranking.items] == [
            projects[1][0].id,
            projects[2][0].id,
            projects[0][0].id,
        ]
        assert [item.rank for item in ranking.items] == [1, 2, 3]
        readiness = service.readiness(portfolio.id)
        assert readiness.can_enter_portfolio_analysis is True
        assert readiness.final_output == "READY_FOR_PORTFOLIO_ANALYSIS"
        membership = projects[1][1]
        membership.status = "INACTIVE"
        membership.updated_by = actor_id
        db.commit()
        recomputed = service.prioritization(portfolio.id)
        assert completed[1].id not in {item.evaluation_id for item in recomputed.items}


def test_same_project_can_have_independent_evaluation_and_rank_in_two_portfolios() -> None:
    tenant_id, actor_id, parent = _workspace_context()
    with SessionLocal() as db:
        first = _portfolio(db, tenant_id, actor_id, parent, "Gate 07E Portfolio A")
        second = _portfolio(db, tenant_id, actor_id, parent, "Gate 07E Portfolio B")
        project, _membership = _project(db, tenant_id, actor_id, parent, first, name="Multi-Portfolio Project")
        second_membership = PortfolioProjectMembership(
            tenant_id=tenant_id,
            portfolio_workspace_id=second.id,
            project_workspace_id=project.id,
            membership_source="MANUAL",
            is_target_portfolio=False,
            status="ACTIVE",
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(second_membership)
        db.commit()
        service = PortfolioEvaluationService(db, tenant_id, actor_id)
        first_result = _complete(service, first.id, project.id, 5)
        second_result = _complete(service, second.id, project.id, 3)
        assert first_result.normalized_score != second_result.normalized_score
        assert service.prioritization(first.id).items[0].evaluation_id == first_result.id
        assert service.prioritization(second.id).items[0].evaluation_id == second_result.id


def test_reevaluation_creates_a_new_version_and_preserves_history() -> None:
    tenant_id, actor_id, parent = _workspace_context()
    with SessionLocal() as db:
        portfolio = _portfolio(db, tenant_id, actor_id, parent, "Gate 07E History Portfolio")
        project, _membership = _project(db, tenant_id, actor_id, parent, portfolio)
        db.commit()
        service = PortfolioEvaluationService(db, tenant_id, actor_id)
        completed = _complete(service, portfolio.id, project.id, 4)
        replacement = service.reevaluate(completed.id, f"reevaluate-{uuid4()}")
        assert replacement.evaluation_version == completed.evaluation_version + 1
        assert replacement.status == "DRAFT"
        historical = db.get(PortfolioProjectEvaluation, completed.id)
        assert historical is not None and historical.status == "SUPERSEDED"


def test_tie_break_uses_planned_finish_and_projects_source_fields() -> None:
    tenant_id, actor_id, parent = _workspace_context()
    with SessionLocal() as db:
        portfolio = _portfolio(db, tenant_id, actor_id, parent, "Gate 07E Planned Finish Portfolio")
        later, _membership = _project(db, tenant_id, actor_id, parent, portfolio, name="Later Finish")
        earlier, _membership = _project(db, tenant_id, actor_id, parent, portfolio, name="Earlier Finish")
        for project, target_finish in ((later, "2029-12-31"), (earlier, "2028-01-01")):
            defaults = deepcopy(project.defaults_json)
            snapshot = defaults["_portfolio_planning"]["snapshot"]
            snapshot["target_finish"] = target_finish
            defaults["_portfolio_planning"]["planning_entry_hash"] = _hash(snapshot)
            project.defaults_json = defaults
        db.commit()
        service = PortfolioEvaluationService(db, tenant_id, actor_id)
        _complete(service, portfolio.id, later.id, 4)
        _complete(service, portfolio.id, earlier.id, 4)

        ranking = service.prioritization(portfolio.id)

        assert [item.project_workspace_id for item in ranking.items] == [earlier.id, later.id]
        assert [item.planned_finish.isoformat() for item in ranking.items if item.planned_finish] == [
            "2028-01-01",
            "2029-12-31",
        ]
        assert ranking.items[0].proposal_score == 80
        assert ranking.items[0].rom_cost == 2500000
        assert ranking.items[0].strategic_objectives == [{"code": "GROWTH", "name": "Growth"}]


def test_admin_preview_accepts_unsaved_draft_without_persisting_it_and_stale_etag_is_rejected() -> None:
    tenant_id, actor_id, parent = _workspace_context()
    with SessionLocal() as db:
        portfolio = _portfolio(db, tenant_id, actor_id, parent, "Gate 07E Admin Preview Portfolio")
        db.commit()
        service = PortfolioEvaluationService(db, tenant_id, actor_id)
        published = db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == tenant_id,
                AdminConfiguration.kind == "portfolio_evaluation_configuration",
                AdminConfiguration.status == "published",
                AdminConfiguration.content_json["scope"]["workspace_id"].as_integer() == portfolio.id,
            )
        )
        assert published is not None
        clone = service.clone_configuration(published.id, published.version)
        changed = deepcopy(clone.content_json)
        changed["criteria"][0]["weight"] = 24
        changed["criteria"][1]["weight"] = 21

        preview = service.configuration_preview(portfolio.id, clone.id, changed)

        assert preview.publishable is True
        assert preview.effective["criteria"][0]["weight"] == 24
        assert preview.source["preview"] is True
        persisted = db.get(AdminConfiguration, clone.id)
        assert persisted is not None and persisted.content_json["criteria"][0]["weight"] == 25
        stale_version = clone.version
        updated = service.update_configuration(clone.id, stale_version, clone.name, clone.description, changed)
        with pytest.raises(HTTPException) as stale:
            service.update_configuration(clone.id, stale_version, clone.name, clone.description, changed)
        assert stale.value.status_code == 412
        service.publish_configuration(updated.id, updated.version)
        effective = service.configuration_preview(portfolio.id)
        assert effective.source["revision"] == clone.revision
        assert effective.effective["criteria"][0]["weight"] == 24
