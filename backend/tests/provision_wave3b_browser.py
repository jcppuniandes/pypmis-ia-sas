"""Provision real actors and truthful source context only in disposable databases."""

from __future__ import annotations

import json
import os
from datetime import date
from uuid import uuid4

from sqlalchemy import select
from tests.test_capital_allocation_wave2a import _context, _user
from tests.test_commercial_strategy_gate07m_comm import _complete_strategy
from tests.test_owner_capability_wave3b import _fixture, _grant, _key

from app.core.security import hash_password
from app.core.time import utc_now
from app.database.seed import ensure_membership, seed_demo
from app.database.session import Base, SessionLocal, engine
from app.domain.models import AuthCredential, EnterpriseWorkspace, Project, UserAccount
from app.modules.basic_data.schemas import AssessmentActionIn, AssessmentCreateIn, ItemCreateIn, ItemValidateIn
from app.modules.basic_data.service import BasicDataService, _hash
from app.modules.commercial_strategy.service import CommercialStrategyService
from app.modules.portfolio_planning.models import PortfolioProjectMembership
from app.modules.portfolio_resource.models import (
    PortfolioResourceCapacityPlan,
    PortfolioResourceScenario,
    PortfolioResourceScenarioProject,
)


def prepare_source_contexts(db, fixture):
    """Real Basic/COMM workflows; explicit DRAFT resource context never pretends READY."""
    author, reviewer, project = fixture["author"], fixture["reviewer"], fixture["project"]
    basic = BasicDataService(db, author.tenant_id, author.id, _context(author, "project_definition_manager"))
    final = BasicDataService(db, reviewer.tenant_id, reviewer.id, _context(reviewer, "definition_reviewer"))
    for requirement in basic.requirements(project.id)["requirements"]:
        code = requirement["requirement_code"]
        item = basic.create_item(
            project.id,
            ItemCreateIn(
                requirement_code=code,
                availability="AVAILABLE",
                quality="VALIDATED",
                confidence="HIGH",
                source_type="STUDY_REFERENCE",
                source_reference=f"disposable-study:{code}",
                source_version="1",
                source_hash=_hash({"study": code, "version": 1}),
                source_date=utc_now().date(),
                evidence_refs=[{"reference": f"disposable-study:{code}", "version": "1"}],
            ),
            _key("context-basic-item"),
        )
        final.validate_item(
            item["id"],
            item["revision_version"],
            ItemValidateIn(validation_state="VALIDATED"),
            _key("context-basic-validation"),
        )
    assessment = basic.create_assessment(project.id, AssessmentCreateIn(), _key("context-basic-create"))
    assessment = basic.submit(
        assessment["id"], assessment["revision_version"], AssessmentActionIn(), _key("context-basic-submit")
    )
    basic_completed = final.complete(
        assessment["id"], assessment["revision_version"], AssessmentActionIn(), _key("context-basic-complete")
    )
    assert basic_completed["snapshot_json"]["readiness_status"] == "READY"
    commercial = CommercialStrategyService(db, author.tenant_id, author.id)
    commercial.ensure_seed()
    _complete_strategy(db, author, project, commercial)

    suffix = uuid4().hex[:10]
    portfolio = EnterpriseWorkspace(
        tenant_id=author.tenant_id,
        parent_id=fixture["enterprise"].id,
        workspace_type_code="portfolio",
        code=f"W3B-PORT-{suffix}",
        record_code=f"W3B.PORT.{suffix}",
        name="Wave 3B read-only resource context",
        status="active",
        defaults_json={},
        created_by_user_id=author.id,
    )
    db.add(portfolio)
    db.flush()
    membership = PortfolioProjectMembership(
        tenant_id=author.tenant_id,
        portfolio_workspace_id=portfolio.id,
        project_workspace_id=project.id,
        membership_source="DISPOSABLE_CONTEXT",
        status="ACTIVE",
        created_by=author.id,
        updated_by=author.id,
    )
    capacity = PortfolioResourceCapacityPlan(
        tenant_id=author.tenant_id,
        portfolio_workspace_id=portfolio.id,
        logical_code=f"W3B-CONTEXT-{suffix}",
        plan_name="Disposable context capacity, not capability",
        planning_horizon_start=date(2027, 1, 1),
        planning_horizon_end=date(2027, 12, 31),
        status="DRAFT",
        created_by=author.id,
        updated_by=author.id,
        source_reference="DISPOSABLE_FIXTURE_CONTEXT_ONLY",
        capacity_hash=_hash({"capacity": suffix}),
    )
    db.add_all([membership, capacity])
    db.flush()
    scenario = PortfolioResourceScenario(
        tenant_id=author.tenant_id,
        portfolio_workspace_id=portfolio.id,
        logical_code=f"W3B-CONTEXT-{suffix}",
        scenario_name="Wave 3B DRAFT resource context",
        status="DRAFT",
        capacity_plan_id=capacity.id,
        capacity_plan_hash=capacity.capacity_hash,
        source_analysis_hash=_hash({"analysis_context": suffix}),
        source_prioritization_hash=_hash({"priority_context": suffix}),
        membership_set_hash=_hash({"membership": membership.id}),
        evaluation_set_hash=_hash({"evaluation_context": suffix}),
        source_configuration_hash=_hash({"context": "resource-only"}),
        source_hash=_hash({"resource_source": suffix}),
        scenario_hash=_hash({"resource_scenario": suffix}),
        creation_mode="EMPTY",
        overload_policy="ALLOW_WITH_WARNING",
        created_by=author.id,
        updated_by=author.id,
        description="Typed disposable DRAFT source contract. No resource READY evidence is claimed.",
    )
    db.add(scenario)
    db.flush()
    db.add(
        PortfolioResourceScenarioProject(
            tenant_id=author.tenant_id,
            scenario_id=scenario.id,
            project_workspace_id=project.id,
            portfolio_membership_id=membership.id,
            project_number=project.code,
            project_name=project.name,
            portfolio_evaluation_score=0,
            portfolio_rank=1,
            strategic_alignment_score=0,
            risk_score=0,
            risk_bucket="UNASSESSED",
            gate07f_analysis_hash=scenario.source_analysis_hash,
            selection_state="UNSELECTED",
            row_hash=_hash({"project": project.id, "scenario": scenario.id}),
            updated_by=author.id,
        )
    )
    db.commit()
    return fixture["preparer"].contexts(project.id)


def _credential(db, actor, email, name):
    actor.email, actor.full_name = email, name
    db.add(
        AuthCredential(
            tenant_id=actor.tenant_id,
            user_id=actor.id,
            provider="local",
            password_hash=hash_password("1234"),
            is_active=True,
        )
    )
    db.commit()


def main() -> None:
    if os.getenv("PYPMIS_WAVE3B_BROWSER_FIXTURE") != "disposable-only" or (
        engine.dialect.name != "postgresql" or engine.url.database != "wave3b_browser"
    ):
        raise RuntimeError("Browser provisioning is restricted to disposable wave3b_browser PostgreSQL")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_demo(db)
        if db.scalar(select(UserAccount).where(UserAccount.email == "wave3b.authority@demo.local")):
            print(json.dumps({"database": engine.url.database, "fixture": "reused"}), flush=True)
            return
        fixture = _fixture(db, count=2, fel=True)
        author, authority, workspace = fixture["author"], fixture["reviewer"], fixture["project"]
        workspace.code, workspace.name = f"W3B-PROJECT-{workspace.id}", "Wave 3B Owner capability Project"
        db.commit()
        contexts = prepare_source_contexts(db, fixture)
        assert contexts["commercial"]["status"] == "COMPLETED"
        assert contexts["resources"]["status"] == "AVAILABLE"
        _credential(db, authority, "wave3b.authority@demo.local", "Wave 3B Independent Authority")
        for role in ("configuration_admin", "definition_assessor", "definition_reviewer"):
            _grant(db, authority, role)
        user = _user(db, author.tenant_id, "wave3b-user")
        _credential(db, user, "wave3b.user@demo.local", "Wave 3B Project-scoped preparer")
        _grant(db, user, "definition_assessor", scope_type="workspace", workspace_id=workspace.id)
        project = db.scalar(select(Project).where(Project.tenant_id == author.tenant_id).order_by(Project.id))
        if project is None:
            raise RuntimeError("The app shell requires an existing demo operational Project")
        ensure_membership(db, author.tenant_id, project.id, authority.id, "Control Manager")
        ensure_membership(db, author.tenant_id, project.id, user.id, "Executive")
        db.commit()
        print(
            json.dumps(
                {
                    "database": engine.url.database,
                    "project_workspace_id": workspace.id,
                    "configuration_id": fixture["configuration"]["id"],
                    "authority_email": authority.email,
                    "user_email": user.email,
                    "resource_context": "DRAFT_ONLY",
                    "basic_data_context": "READY",
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
