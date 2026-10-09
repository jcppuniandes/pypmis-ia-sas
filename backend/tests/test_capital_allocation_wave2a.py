"""Wave 2A acceptance coverage for strategic capital allocation.

The suite protects the domain boundary explicitly: Bucket classification and
Allocation Plans may read governed portfolio sources, but they must not rank a
project or mutate budget, resource, Gate07I recommendation, Gate07K/FID,
funding, or economic-financial authorities.  A standalone Capital Demand also
remains valid without a Project lineage.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text

from app.core.config import get_settings
from app.core.security import create_access_token
from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import (
    AdminConfiguration,
    EnterpriseWorkspace,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityRole,
    UserAccount,
)
from app.main import app
from app.modules.capital_planning.models import (
    StrategicBucketClassification,
    StrategicCapitalAllocationCommand,
    StrategicCapitalAllocationPlan,
)
from app.modules.capital_planning.router import ALLOCATION_AUTHOR_ROLES, BUCKET_CLASSIFY_ROLES, CONFIG_ROLES
from app.modules.capital_planning.schemas import (
    AllocationBasis,
    AllocationLineIn,
    AllocationLinesReplaceIn,
    AllocationPlanCreate,
    BucketClassificationIn,
    BucketClassificationsReplaceIn,
    CycleCreate,
    DemandCreate,
)
from app.modules.capital_planning.service import CONFIG_KIND, DEFAULT_CONFIGURATION, CapitalPlanningService
from app.modules.enterprise_structure.models import EnterpriseStrategicObjective
from app.modules.enterprise_structure.permissions import (
    EnterprisePermissionContext,
    ensure_enterprise_permissions,
    require_enterprise_permission,
)
from app.modules.idea_demand.models import Idea
from app.modules.investment_decision.models import InvestmentDecision
from app.modules.investment_gate_preparation.models import InvestmentGatePreparation
from app.modules.portfolio_budget.models import (
    PortfolioBudgetScenario,
    PortfolioBudgetScenarioProject,
    PortfolioBudgetTarget,
)
from app.modules.portfolio_convergence.models import (
    PortfolioConvergedAlternative,
    PortfolioScenarioConvergence,
)
from app.modules.portfolio_planning.models import PortfolioProjectMembership
from app.modules.project_creation.models import ProjectCreationRequest

BUCKETS = (
    ("sustain", "Sustain the base", "asset-integrity"),
    ("grow", "Grow capacity", "growth"),
    ("transform", "Transform operations", "digital"),
    ("comply", "Compliance and resilience", "compliance"),
)


def _context(user: UserAccount, *roles: str) -> EnterprisePermissionContext:
    return EnterprisePermissionContext(
        user=user,
        organization_wide=True,
        scope_unit_ids=frozenset(),
        workspace_ids=frozenset(),
        role_codes=frozenset(roles),
    )


def _user(db, tenant_id: int, label: str) -> UserAccount:
    record = UserAccount(
        tenant_id=tenant_id,
        email=f"wave2a-{label}-{uuid4().hex[:10]}@example.test",
        full_name=f"Wave 2A {label.title()}",
        title=label.title(),
        status="active",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _token_headers(user: UserAccount) -> dict[str, str]:
    token, _ = create_access_token(
        claims={"sub": user.id, "tenant_id": user.tenant_id, "email": user.email},
        secret_key=get_settings().auth_secret_key,
        expires_delta=timedelta(minutes=5),
    )
    return {"Authorization": f"Bearer {token}"}


def _foundation(db):
    admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
    assert admin is not None
    token = uuid4().hex[:10]
    workspace = EnterpriseWorkspace(
        tenant_id=admin.tenant_id,
        parent_id=None,
        workspace_type_code="enterprise",
        code=f"W2A-ENT-{token}",
        external_key=f"wave2a-ent-{token}",
        record_code=f"W2A.ENT.{token}",
        name="Wave 2A Capital Owner Enterprise",
        status="active",
        defaults_json={"governance_model": "CAPITAL_OWNER"},
        sort_order=1,
        version=1,
        created_by_user_id=admin.id,
    )
    objective = EnterpriseStrategicObjective(
        tenant_id=admin.tenant_id,
        code=f"wave2a-objective-{uuid4().hex[:8]}",
        name="Governed strategic capital balance",
        strategic_line="Capital allocation",
        priority="high",
        horizon="2030",
        responsible_area="Enterprise Strategy",
        active=True,
        description="Objective used by the Wave 2A acceptance path.",
        source_release_code="WAVE2A-TEST",
        created_by_user_id=admin.id,
    )
    db.add_all([workspace, objective])
    db.commit()
    db.refresh(workspace)
    db.refresh(objective)
    return admin, workspace, objective


def _publish_configuration(service: CapitalPlanningService, objective: EnterpriseStrategicObjective) -> None:
    service.ensure_seed()
    published = service.db.scalar(
        select(AdminConfiguration)
        .where(
            AdminConfiguration.tenant_id == service.tenant_id,
            AdminConfiguration.kind == CONFIG_KIND,
            AdminConfiguration.code == "default",
            AdminConfiguration.status == "published",
        )
        .order_by(AdminConfiguration.revision.desc())
    )
    assert published is not None
    draft = service.clone_configuration(published.id, published.version)
    content = deepcopy(DEFAULT_CONFIGURATION)
    theme_codes = sorted({item[2] for item in BUCKETS})
    content.update(
        {
            "themes": [
                {
                    "code": code,
                    "label": code.replace("-", " ").title(),
                    "strategic_objective_codes": [objective.code],
                }
                for code in theme_codes
            ],
            "drivers": [{"code": "strategy", "label": "Strategy"}],
            "categories": [{"code": "capital", "label": "Capital"}],
            "planning_horizons": [{"code": "2030", "label": "2030"}],
            "urgency_levels": [{"code": "planned", "label": "Planned"}],
            "uncertainty_levels": [{"code": "conceptual", "label": "Conceptual"}],
            "strategic_capital_buckets": [
                {
                    "code": code,
                    "name": name,
                    "description": f"Governed planning category: {name}.",
                    "active": True,
                    "display_order": index,
                    "applicable_theme_codes": [theme],
                    "strategic_objective_codes": [objective.code],
                }
                for index, (code, name, theme) in enumerate(BUCKETS, start=1)
            ],
        }
    )
    draft = service.update_configuration(
        draft.id,
        draft.version,
        name="Wave 2A controlled Bucket configuration",
        description="Four reusable strategic capital Buckets and allocation policy.",
        content=content,
    )
    service.publish_configuration(draft.id, draft.version)


def _cycle(service: CapitalPlanningService, workspace: EnterpriseWorkspace):
    result = service.create_cycle(
        CycleCreate(
            name="Wave 2A strategic capital cycle",
            planning_horizon_start=date(2027, 1, 1),
            planning_horizon_end=date(2030, 12, 31),
            scope_workspace_id=workspace.id,
            responsible_organization_workspace_id=workspace.id,
            applicable_theme_codes=[item[2] for item in BUCKETS],
            capital_basis_currency="COP",
            description="Governed allocation cycle.",
        ),
        f"wave2a-cycle-{uuid4()}",
    )
    return service.transition_cycle(result.id, "open", result.revision_version, f"wave2a-open-{uuid4()}")


def _demand_payload(
    cycle_id: int,
    workspace_id: int,
    sponsor_id: int,
    objective_code: str,
    *,
    theme: str,
    currency: str,
    amount: str,
) -> DemandCreate:
    return DemandCreate(
        name=f"Wave 2A {theme} need {currency} {uuid4().hex[:6]}",
        description="A governed strategic need before solution or investment selection.",
        planning_cycle_id=cycle_id,
        theme_codes=[theme],
        strategic_objective_codes=[objective_code],
        business_or_asset_need="Balance capital intent while preserving authority boundaries.",
        strategic_driver="strategy",
        demand_category="capital",
        urgency="planned",
        target_horizon="2030",
        sponsor_user_id=sponsor_id,
        owning_workspace_id=workspace_id,
        location_context="Enterprise",
        indicative_capital_need=Decimal(amount),
        currency_code=currency,
        uncertainty_level="conceptual",
        assumptions=["No exchange-rate normalization is implied."],
        constraints=["This is not an approved budget."],
        dependencies=["Governed downstream evaluation."],
    )


def _create_submitted_demand(service: CapitalPlanningService, payload: DemandCreate):
    demand = service.create_demand(payload, f"wave2a-demand-{uuid4()}")
    return service.transition_demand(
        demand.id,
        "submit",
        demand.revision_version,
        f"wave2a-demand-submit-{uuid4()}",
    )


def _allocation_payload(cycle_id: int, workspace_id: int) -> AllocationPlanCreate:
    return AllocationPlanCreate(
        name="Wave 2A strategic allocation plan",
        description="Indicative planning envelopes; not Budget, Funding, Resource or FID authority.",
        planning_cycle_id=cycle_id,
        scope_workspace_id=workspace_id,
        allocation_basis=AllocationBasis.PERCENTAGE,
        assumptions=["Demand positions are compared without currency conversion."],
        constraints=["Percentages express strategic intent only."],
    )


def _allocation_lines() -> AllocationLinesReplaceIn:
    return AllocationLinesReplaceIn(
        lines=[
            AllocationLineIn(
                bucket_code=code,
                target_percentage=Decimal("25"),
                minimum_percentage=Decimal("10"),
                maximum_percentage=Decimal("40"),
                rationale=f"Balanced strategic target for {name}.",
                strategic_objective_codes=[],
            )
            for code, name, _theme in BUCKETS
        ]
    )


def _authority_counts(db) -> dict[str, int]:
    """Regression sentinel for rank/budget/resource/Gate07I/Gate07K authorities."""

    candidates = (
        "portfolio_project_evaluations",  # rank/evaluation authority
        "portfolio_budget_targets",
        "portfolio_budget_scenarios",
        "portfolio_resource_capacity_plans",
        "portfolio_resource_scenarios",
        "portfolio_scenario_convergences",  # Gate07I recommendation authority
        "investment_decisions",  # Gate07K/FID authority
        "strategic_funding_sources",
        "funds",
        "funding_assignments",
        "economic_financial_models",
    )
    available = set(inspect(db.bind).get_table_names())
    return {
        table: int(db.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one())
        for table in candidates
        if table in available
    }


def _project_with_membership(
    db,
    *,
    author: UserAccount,
    enterprise: EnterpriseWorkspace,
    portfolio: EnterpriseWorkspace,
    template_configuration_id: int,
    label: str,
    amount: str,
    source_idea_id: int | None = None,
) -> tuple[EnterpriseWorkspace, PortfolioProjectMembership]:
    """Materialize the existing Project/Membership authorities for read-only comparison."""

    token = uuid4().hex[:10]
    project = EnterpriseWorkspace(
        tenant_id=author.tenant_id,
        parent_id=enterprise.id,
        workspace_type_code="project",
        code=f"W2A-PRJ-{token}",
        external_key=f"wave2a-project-{token}",
        record_code=f"{enterprise.record_code}.PRJ.{token}",
        name=f"Wave 2A {label}",
        status="active",
        defaults_json={"_project": {"governance_model": "CAPITAL_OWNER"}},
        sort_order=10,
        version=1,
        created_by_user_id=author.id,
    )
    db.add(project)
    db.flush()
    request = ProjectCreationRequest(
        tenant_id=author.tenant_id,
        request_number=f"W2A-REQ-{token}",
        state="materialized",
        requestor_user_id=author.id,
        parent_workspace_id=enterprise.id,
        project_template_config_id=template_configuration_id,
        project_name=project.name,
        description="Existing governed Project source consumed read-only by Wave 2A.",
        project_manager_user_id=author.id,
        currency_code="COP",
        estimated_budget=Decimal(amount),
        project_type="CAPITAL",
        governance_model="CAPITAL_OWNER",
        source_context_type="IDEA" if source_idea_id is not None else "STANDALONE",
        source_context_id=source_idea_id,
        source_idea_id=source_idea_id,
        source_snapshot_json={},
        materialized_workspace_id=project.id,
        materialized_project_number=project.code,
        materialized_record_code=project.record_code,
        last_modified_by_user_id=author.id,
    )
    membership = PortfolioProjectMembership(
        tenant_id=author.tenant_id,
        portfolio_workspace_id=portfolio.id,
        project_workspace_id=project.id,
        membership_source="STRATEGIC_INTAKE" if source_idea_id is not None else "MANUAL",
        is_target_portfolio=True,
        status="ACTIVE",
        created_by=author.id,
        updated_by=author.id,
    )
    db.add_all([request, membership])
    db.flush()
    return project, membership


def test_wave2a_percentage_multicurrency_unclassified_lifecycle_snapshot_and_revision() -> None:
    with TestClient(app):
        with SessionLocal() as db:
            author, workspace, objective = _foundation(db)
            reviewer = _user(db, author.tenant_id, "allocation-reviewer")
            endorser = _user(db, author.tenant_id, "allocation-endorser")
            author_service = CapitalPlanningService(
                db,
                author.tenant_id,
                author.id,
                _context(author, "capital_planning_allocation_author", "capital_planning_cycle_manager"),
            )
            _publish_configuration(author_service, objective)
            cycle = _cycle(author_service, workspace)
            cop = _create_submitted_demand(
                author_service,
                _demand_payload(
                    cycle.id,
                    workspace.id,
                    author.id,
                    objective.code,
                    theme="growth",
                    currency="COP",
                    amount="3000000",
                ),
            )
            usd = _create_submitted_demand(
                author_service,
                _demand_payload(
                    cycle.id,
                    workspace.id,
                    author.id,
                    objective.code,
                    theme="digital",
                    currency="USD",
                    amount="200000",
                ).model_copy(update={"theme_codes": ["digital", "compliance"]}),
            )
            before = _authority_counts(db)
            key = f"wave2a-plan-{uuid4()}"
            plan = author_service.create_allocation_plan(_allocation_payload(cycle.id, workspace.id), key)
            duplicate = author_service.create_allocation_plan(_allocation_payload(cycle.id, workspace.id), key)
            assert duplicate.id == plan.id

            invalid_lines = _allocation_lines()
            invalid_lines.lines[0].target_percentage = Decimal("24")
            with pytest.raises(HTTPException) as invalid_percentage:
                author_service.replace_allocation_lines(plan.id, invalid_lines, plan.revision_version)
            assert invalid_percentage.value.status_code == 422
            assert invalid_percentage.value.detail["code"] == "INVALID_TARGET_PERCENTAGE_TOTAL"

            plan = author_service.replace_allocation_lines(plan.id, _allocation_lines(), plan.revision_version)
            with pytest.raises(HTTPException) as stale_etag:
                author_service.replace_allocation_lines(plan.id, _allocation_lines(), plan.revision_version - 1)
            assert stale_etag.value.status_code == 412
            assert stale_etag.value.detail["code"] == "ETAG_MISMATCH"

            first_batch = BucketClassificationsReplaceIn(
                classifications=[
                    BucketClassificationIn(
                        target_type="DEMAND",
                        target_id=cop.id,
                        bucket_code="sustain",
                        rationale="Explicit primary classification overrides the growth theme default.",
                    )
                ]
            )
            batch_key = f"wave2a-classifications-{uuid4()}"
            classified = author_service.replace_bucket_classifications(
                plan.id,
                first_batch,
                plan.revision_version,
                batch_key,
            )
            plan = classified.allocation_plan
            retry = author_service.replace_bucket_classifications(
                plan.id,
                first_batch,
                plan.revision_version - 1,
                batch_key,
            )
            assert [item.id for item in retry.classifications] == [item.id for item in classified.classifications]

            comparison = author_service.allocation_comparison(plan.id)
            assert comparison.classification_coverage_percentage == Decimal("50.00")
            assert comparison.multi_currency is True
            assert comparison.normalization_warning
            assert comparison.unclassified["demand"]["item_count"] == 1
            sustain = next(item for item in comparison.positions if item.bucket_code == "sustain")
            grow = next(item for item in comparison.positions if item.bucket_code == "grow")
            assert sustain.current_demand.item_count == 1
            assert grow.current_demand.item_count == 0
            # Explicit classification wins and each Demand is accumulated once: no double_count.
            assert sum(item.current_demand.item_count for item in comparison.positions) == 1

            plan = author_service.transition_allocation_plan(
                plan.id, "submit", plan.revision_version, f"wave2a-submit-{uuid4()}"
            )
            review_service = CapitalPlanningService(
                db,
                author.tenant_id,
                reviewer.id,
                _context(reviewer, "capital_planning_allocation_reviewer"),
            )
            plan = review_service.transition_allocation_plan(
                plan.id, "review", plan.revision_version, f"wave2a-review-{uuid4()}"
            )
            endorser_service = CapitalPlanningService(
                db,
                author.tenant_id,
                endorser.id,
                _context(endorser, "capital_planning_allocation_endorser"),
            )
            with pytest.raises(HTTPException) as unclassified:
                endorser_service.transition_allocation_plan(
                    plan.id, "endorse", plan.revision_version, f"wave2a-endorse-blocked-{uuid4()}"
                )
            assert unclassified.value.status_code == 409
            assert unclassified.value.detail["code"] == "UNCLASSIFIED_COVERAGE_EXCEEDS_POLICY"

            plan = review_service.transition_allocation_plan(
                plan.id, "return", plan.revision_version, f"wave2a-return-{uuid4()}"
            )
            complete_batch = BucketClassificationsReplaceIn(
                classifications=[
                    first_batch.classifications[0],
                    BucketClassificationIn(
                        target_type="DEMAND",
                        target_id=usd.id,
                        bucket_code="transform",
                        rationale="Explicit primary classification for digital transformation.",
                    ),
                ]
            )
            plan = author_service.replace_bucket_classifications(
                plan.id,
                complete_batch,
                plan.revision_version,
                f"wave2a-classifications-complete-{uuid4()}",
            ).allocation_plan
            assert author_service.allocation_comparison(plan.id).classification_coverage_percentage == Decimal("100.00")
            plan = author_service.transition_allocation_plan(
                plan.id, "submit", plan.revision_version, f"wave2a-resubmit-{uuid4()}"
            )
            plan = review_service.transition_allocation_plan(
                plan.id, "review", plan.revision_version, f"wave2a-rereview-{uuid4()}"
            )
            with pytest.raises(HTTPException) as sod:
                author_service.transition_allocation_plan(
                    plan.id, "endorse", plan.revision_version, f"wave2a-self-endorse-{uuid4()}"
                )
            assert sod.value.status_code == 409
            assert sod.value.detail["code"] == "SOD_ALLOCATION_AUTHOR_CANNOT_ENDORSE"

            plan = endorser_service.transition_allocation_plan(
                plan.id, "endorse", plan.revision_version, f"wave2a-endorse-{uuid4()}"
            )
            assert plan.status == "ENDORSED"
            assert plan.endorsed_snapshot_hash and len(plan.endorsed_snapshot_hash) == 64
            stored = db.get(StrategicCapitalAllocationPlan, plan.id)
            assert stored is not None
            assert (
                stored.endorsed_snapshot_json["future_periodic_portfolio_review_contract"]["allocation_plan_hash"]
                == plan.plan_hash
            )
            with pytest.raises(HTTPException) as immutable:
                author_service.replace_allocation_lines(plan.id, _allocation_lines(), plan.revision_version)
            assert immutable.value.detail["code"] == "ALLOCATION_PLAN_IMMUTABLE"

            successor = author_service.create_allocation_plan_revision(
                plan.id,
                plan.revision_version,
                f"wave2a-revision-{uuid4()}",
            )
            assert successor.status == "DRAFT"
            assert successor.logical_code == plan.logical_code
            assert successor.plan_revision == plan.plan_revision + 1
            assert author_service.allocation_plan(plan.id).status == "SUPERSEDED"
            assert len(successor.lines) == len(BUCKETS)
            assert _authority_counts(db) == before

            history = author_service.allocation_plan_history(plan.id)
            assert {item.event_type for item in history} >= {
                "capital_planning.allocation_plan.created",
                "capital_planning.allocation_plan.endorse",
            }
            assert (
                db.scalar(
                    select(func.count(StrategicCapitalAllocationCommand.id)).where(
                        StrategicCapitalAllocationCommand.allocation_plan_id == plan.id
                    )
                )
                == 2
            )
            assert (
                db.scalar(
                    select(func.count(StrategicBucketClassification.id)).where(
                        StrategicBucketClassification.allocation_plan_id == successor.id
                    )
                )
                == 2
            )
            assert db.scalar(
                select(func.count(SecurityEvent.id)).where(
                    SecurityEvent.tenant_id == author.tenant_id,
                    SecurityEvent.target_type == "StrategicCapitalAllocationPlan",
                )
            )


def test_wave2a_project_membership_and_demand_lineage_classification_precedence() -> None:
    """Resolve existing Portfolio Projects without mutating their source authorities."""

    with TestClient(app):
        with SessionLocal() as db:
            author, enterprise, objective = _foundation(db)
            service = CapitalPlanningService(
                db,
                author.tenant_id,
                author.id,
                _context(author, "capital_planning_allocation_author", "capital_planning_cycle_manager"),
            )
            _publish_configuration(service, objective)
            cycle = _cycle(service, enterprise)
            source_demand = _create_submitted_demand(
                service,
                _demand_payload(
                    cycle.id,
                    enterprise.id,
                    author.id,
                    objective.code,
                    theme="digital",
                    currency="COP",
                    amount="3000000",
                ),
            )
            token = uuid4().hex[:10]
            portfolio = EnterpriseWorkspace(
                tenant_id=author.tenant_id,
                parent_id=enterprise.id,
                workspace_type_code="portfolio",
                code=f"W2A-PORT-{token}",
                external_key=f"wave2a-portfolio-{token}",
                record_code=f"{enterprise.record_code}.PORT.{token}",
                name="Wave 2A governed Portfolio",
                status="active",
                defaults_json={},
                sort_order=5,
                version=1,
                created_by_user_id=author.id,
            )
            db.add(portfolio)
            db.flush()
            source_idea = Idea(
                tenant_id=author.tenant_id,
                idea_number=f"W2A-IDEA-{token}",
                title="Demand-originated project lineage",
                description="Existing Demand to Idea lineage consumed read-only.",
                idea_type="capital",
                category="strategic-capital",
                expected_benefit="Preserve deterministic strategic classification.",
                estimated_value=source_demand.indicative_capital_need,
                currency_code="COP",
                owning_workspace_id=enterprise.id,
                target_portfolio_workspace_id=portfolio.id,
                source_capital_demand_id=source_demand.id,
                source_capital_demand_snapshot_hash=source_demand.demand_hash,
                strategic_objective_codes=[objective.code],
                requestor_user_id=author.id,
                owner_user_id=author.id,
                state="ACCEPTED",
                last_modified_by_user_id=author.id,
            )
            db.add(source_idea)
            db.flush()
            template = db.scalar(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == author.tenant_id,
                    AdminConfiguration.kind == CONFIG_KIND,
                    AdminConfiguration.code == "default",
                    AdminConfiguration.status == "published",
                )
                .order_by(AdminConfiguration.revision.desc())
            )
            assert template is not None
            project_explicit, membership_project_explicit = _project_with_membership(
                db,
                author=author,
                enterprise=enterprise,
                portfolio=portfolio,
                template_configuration_id=template.id,
                label="standalone Project classification",
                amount="1000000",
            )
            _membership_project, membership_explicit = _project_with_membership(
                db,
                author=author,
                enterprise=enterprise,
                portfolio=portfolio,
                template_configuration_id=template.id,
                label="standalone Membership classification",
                amount="2000000",
            )
            lineage_project, lineage_membership = _project_with_membership(
                db,
                author=author,
                enterprise=enterprise,
                portfolio=portfolio,
                template_configuration_id=template.id,
                label="Demand lineage classification",
                amount="3000000",
                source_idea_id=source_idea.id,
            )
            unclassified_project, unclassified_membership = _project_with_membership(
                db,
                author=author,
                enterprise=enterprise,
                portfolio=portfolio,
                template_configuration_id=template.id,
                label="standalone UNCLASSIFIED",
                amount="4000000",
            )
            db.commit()

            before = _authority_counts(db)
            plan = service.create_allocation_plan(
                _allocation_payload(cycle.id, enterprise.id).model_copy(
                    update={"portfolio_workspace_id": portfolio.id}
                ),
                f"wave2a-project-classification-{uuid4()}",
            )
            plan = service.replace_allocation_lines(plan.id, _allocation_lines(), plan.revision_version)
            classified = service.replace_bucket_classifications(
                plan.id,
                BucketClassificationsReplaceIn(
                    classifications=[
                        BucketClassificationIn(
                            target_type="PROJECT",
                            target_id=project_explicit.id,
                            bucket_code="grow",
                            rationale="Governed standalone Project cross-classification.",
                        ),
                        BucketClassificationIn(
                            target_type="PORTFOLIO_MEMBERSHIP",
                            target_id=membership_explicit.id,
                            bucket_code="sustain",
                            rationale="Governed Portfolio Membership cross-classification.",
                        ),
                    ]
                ),
                plan.revision_version,
                f"wave2a-project-classification-batch-{uuid4()}",
            )
            comparison = service.allocation_comparison(classified.allocation_plan.id)
            positions = {item.bucket_code: item for item in comparison.positions}

            assert positions["grow"].current_portfolio.item_count == 1
            assert positions["grow"].current_portfolio.amount_by_currency == {"COP": Decimal("1000000.00")}
            assert positions["sustain"].current_portfolio.item_count == 1
            assert positions["sustain"].current_portfolio.amount_by_currency == {"COP": Decimal("2000000.00")}
            assert positions["transform"].current_portfolio.item_count == 1
            assert positions["transform"].current_portfolio.amount_by_currency == {"COP": Decimal("3000000.00")}
            assert comparison.unclassified["portfolio"]["item_count"] == 1
            assert comparison.unclassified["portfolio"]["amount_by_currency"] == {"COP": "4000000.00"}

            grow_detail = positions["grow"].current_portfolio.drilldown[0]
            sustain_detail = positions["sustain"].current_portfolio.drilldown[0]
            lineage_detail = positions["transform"].current_portfolio.drilldown[0]
            unclassified_detail = comparison.unclassified["portfolio"]["drilldown"][0]
            assert grow_detail == {
                "project_workspace_id": project_explicit.id,
                "portfolio_membership_id": membership_project_explicit.id,
                "classification_source": "EXPLICIT_PROJECT_CLASSIFICATION",
            }
            assert sustain_detail["portfolio_membership_id"] == membership_explicit.id
            assert sustain_detail["classification_source"] == "EXPLICIT_PORTFOLIO_MEMBERSHIP_CLASSIFICATION"
            assert lineage_detail["project_workspace_id"] == lineage_project.id
            assert lineage_detail["portfolio_membership_id"] == lineage_membership.id
            assert lineage_detail["classification_source"] == "SOURCE_CAPITAL_DEMAND:THEME_TO_BUCKET_DEFAULT"
            assert unclassified_detail["project_workspace_id"] == unclassified_project.id
            assert unclassified_detail["portfolio_membership_id"] == unclassified_membership.id
            assert unclassified_detail["classification_source"] == "UNCLASSIFIED"

            # Each current Portfolio member contributes to exactly one primary Bucket or UNCLASSIFIED.
            assert (
                sum(item.current_portfolio.item_count for item in comparison.positions)
                + comparison.unclassified["portfolio"]["item_count"]
                == 4
            )
            assert "strategic_capital_bucket" not in project_explicit.defaults_json
            assert db.get(PortfolioProjectMembership, membership_explicit.id).status == "ACTIVE"
            assert _authority_counts(db) == before


def test_wave2a_versioned_bucket_configuration_archive_preserves_plan_snapshot() -> None:
    """Published Bucket revisions may retire without reinterpreting historical Plans."""

    with TestClient(app):
        with SessionLocal() as db:
            author, workspace, objective = _foundation(db)
            service = CapitalPlanningService(
                db,
                author.tenant_id,
                author.id,
                _context(
                    author,
                    "capital_planning_config_admin",
                    "capital_planning_allocation_author",
                    "capital_planning_cycle_manager",
                ),
            )
            _publish_configuration(service, objective)
            default_published = db.scalar(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == author.tenant_id,
                    AdminConfiguration.kind == CONFIG_KIND,
                    AdminConfiguration.code == "default",
                    AdminConfiguration.status == "published",
                )
                .order_by(AdminConfiguration.revision.desc())
            )
            assert default_published is not None

            workspace_draft = service.clone_configuration(
                default_published.id,
                default_published.version,
                target_workspace_id=workspace.id,
            )
            workspace_published = service.publish_configuration(workspace_draft.id, workspace_draft.version)
            assert workspace_published.status == "published"
            assert workspace_published.code == f"workspace-{workspace.id}"

            cycle = _cycle(service, workspace)
            plan = service.create_allocation_plan(
                _allocation_payload(cycle.id, workspace.id),
                f"wave2a-historical-configuration-{uuid4()}",
            )
            stored_plan = db.get(StrategicCapitalAllocationPlan, plan.id)
            assert stored_plan is not None
            original_configuration_id = stored_plan.configuration_id
            original_configuration_hash = stored_plan.configuration_hash
            original_snapshot = deepcopy(stored_plan.configuration_snapshot_json)
            original_bucket_name = next(
                item["name"] for item in original_snapshot["strategic_capital_buckets"] if item["code"] == "sustain"
            )

            successor_draft = service.clone_configuration(
                workspace_published.id,
                workspace_published.version,
                target_workspace_id=workspace.id,
            )
            successor_content = deepcopy(successor_draft.content_json)
            next(item for item in successor_content["strategic_capital_buckets"] if item["code"] == "sustain")[
                "name"
            ] = "Renamed only in the successor configuration"
            successor_draft = service.update_configuration(
                successor_draft.id,
                successor_draft.version,
                name="Wave 2A successor Bucket configuration",
                description="A new reusable revision must not rewrite the historical Plan snapshot.",
                content=successor_content,
            )
            successor_published = service.publish_configuration(successor_draft.id, successor_draft.version)
            db.refresh(workspace_published)
            assert workspace_published.status == "archived"
            assert successor_published.status == "published"
            assert successor_published.revision == workspace_published.revision + 1

            successor_archived = service.archive_configuration(successor_published.id, successor_published.version)
            assert successor_archived.status == "archived"
            db.refresh(stored_plan)
            assert stored_plan.configuration_id == original_configuration_id
            assert stored_plan.configuration_hash == original_configuration_hash
            assert stored_plan.configuration_snapshot_json == original_snapshot
            historical_comparison = service.allocation_comparison(plan.id)
            sustain = next(item for item in historical_comparison.positions if item.bucket_code == "sustain")
            assert sustain.bucket_name == original_bucket_name
            assert sustain.bucket_name != "Renamed only in the successor configuration"


def test_wave2a_reads_gate07i_recommendation_and_only_full_pyp_ffa_approval() -> None:
    """Gate07I and Gate07K remain read-only sources with their existing semantics."""

    with TestClient(app):
        with SessionLocal() as db:
            author, enterprise, objective = _foundation(db)
            service = CapitalPlanningService(
                db,
                author.tenant_id,
                author.id,
                _context(author, "capital_planning_allocation_author", "capital_planning_cycle_manager"),
            )
            _publish_configuration(service, objective)
            cycle = _cycle(service, enterprise)
            token = uuid4().hex[:10]
            portfolio = EnterpriseWorkspace(
                tenant_id=author.tenant_id,
                parent_id=enterprise.id,
                workspace_type_code="portfolio",
                code=f"W2A-SRC-PORT-{token}",
                external_key=f"wave2a-source-portfolio-{token}",
                record_code=f"{enterprise.record_code}.SRC.PORT.{token}",
                name="Wave 2A authoritative source Portfolio",
                status="active",
                defaults_json={},
                sort_order=20,
                version=1,
                created_by_user_id=author.id,
            )
            db.add(portfolio)
            db.flush()
            template = db.scalar(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == author.tenant_id,
                    AdminConfiguration.kind == CONFIG_KIND,
                    AdminConfiguration.code == "default",
                    AdminConfiguration.status == "published",
                )
                .order_by(AdminConfiguration.revision.desc())
            )
            assert template is not None
            project, membership = _project_with_membership(
                db,
                author=author,
                enterprise=enterprise,
                portfolio=portfolio,
                template_configuration_id=template.id,
                label="recommended and approved source Project",
                amount="1000000",
            )
            db.commit()

            plan = service.create_allocation_plan(
                _allocation_payload(cycle.id, enterprise.id).model_copy(
                    update={"portfolio_workspace_id": portfolio.id}
                ),
                f"wave2a-authoritative-positions-{uuid4()}",
            )
            plan = service.replace_allocation_lines(plan.id, _allocation_lines(), plan.revision_version)
            plan = service.replace_bucket_classifications(
                plan.id,
                BucketClassificationsReplaceIn(
                    classifications=[
                        BucketClassificationIn(
                            target_type="PROJECT",
                            target_id=project.id,
                            bucket_code="grow",
                            rationale="Explicit governed classification reused by each read-only position.",
                        )
                    ]
                ),
                plan.revision_version,
                f"wave2a-authoritative-classification-{uuid4()}",
            ).allocation_plan

            budget_target = PortfolioBudgetTarget(
                tenant_id=author.tenant_id,
                portfolio_workspace_id=portfolio.id,
                target_code=f"W2A-TARGET-{token}",
                target_revision=1,
                planning_horizon_start=date(2027, 1, 1),
                planning_horizon_end=date(2030, 12, 31),
                period_granularity="YEAR",
                budget_currency="COP",
                total_budget_target=Decimal("5000000"),
                source_reference="Wave 2A read-only adapter fixture",
                status="PUBLISHED",
                target_hash="1" * 64,
                created_by=author.id,
                updated_by=author.id,
            )
            db.add(budget_target)
            db.flush()
            scenario = PortfolioBudgetScenario(
                tenant_id=author.tenant_id,
                portfolio_workspace_id=portfolio.id,
                logical_code=f"W2A-SCENARIO-{token}",
                scenario_name="Gate07I recommended scenario source",
                scenario_code=f"REC-{token}",
                description="Authoritative source consumed without mutation.",
                status="FROZEN",
                analytical_status="UNDER_BUDGET",
                budget_target_id=budget_target.id,
                source_analysis_hash="2" * 64,
                source_prioritization_hash="3" * 64,
                membership_set_hash="4" * 64,
                evaluation_set_hash="5" * 64,
                source_configuration_hash="6" * 64,
                budget_target_hash=budget_target.target_hash,
                source_hash="7" * 64,
                scenario_hash="8" * 64,
                creation_mode="EMPTY",
                time_phasing_method="UNPHASED",
                created_by=author.id,
                updated_by=author.id,
            )
            db.add(scenario)
            db.flush()
            scenario_project = PortfolioBudgetScenarioProject(
                tenant_id=author.tenant_id,
                scenario_id=scenario.id,
                project_workspace_id=project.id,
                portfolio_membership_id=membership.id,
                project_number=project.code,
                project_name=project.name,
                portfolio_evaluation_score=Decimal("80"),
                portfolio_rank=1,
                strategic_alignment_score=Decimal("90"),
                risk_score=Decimal("20"),
                risk_bucket="LOW",
                gate07f_analysis_hash="9" * 64,
                cost_source_type="PROJECT_CREATION_REQUEST",
                cost_source_reference=str(project.id),
                cost_source_hash="a" * 64,
                cost_value=Decimal("1000000"),
                unclassified_amount=Decimal("1000000"),
                budget_breakdown_source="LEGACY_UNCLASSIFIED",
                currency="COP",
                cost_as_of_date=date(2026, 10, 1),
                expected_benefits="Governed source position.",
                project_type="CAPITAL",
                planning_stage="STRATEGIC",
                selection_state="SELECTED",
                row_hash="b" * 64,
                updated_by=author.id,
            )
            db.add(scenario_project)
            convergence = PortfolioScenarioConvergence(
                tenant_id=author.tenant_id,
                portfolio_workspace_id=portfolio.id,
                logical_code=f"W2A-CONVERGENCE-{token}",
                convergence_revision=1,
                name="Gate07I authoritative recommendation",
                description="Read-only Wave 2A source.",
                status="DRAFT",
                required_budget_branch=True,
                required_resource_branch=False,
                source_analysis_hash="c" * 64,
                source_membership_set_hash="d" * 64,
                source_evaluation_set_hash="e" * 64,
                budget_planning_hash=scenario.scenario_hash,
                configuration_id=template.id,
                configuration_revision=template.revision,
                configuration_hash=template.content_hash,
                convergence_source_hash="f" * 64,
                source_snapshot_json={},
                created_by=author.id,
                updated_by=author.id,
            )
            db.add(convergence)
            db.flush()
            alternative = PortfolioConvergedAlternative(
                tenant_id=author.tenant_id,
                convergence_id=convergence.id,
                alternative_name="Recommended selected Project set",
                budget_scenario_id=scenario.id,
                budget_scenario_hash=scenario.scenario_hash,
                alignment_status="ALIGNED",
                budget_feasibility="BUDGET_FEASIBLE",
                resource_feasibility="NOT_REQUIRED",
                feasibility_status="FEASIBLE",
                selected_project_set_hash="0" * 64,
                budget_summary_json={},
                resource_summary_json={},
                strategic_summary_json={},
                risk_summary_json={},
                project_matrix_json=[],
                forced_conflicts_json=[],
                warnings_json=[],
                blockers_json=[],
                alternative_hash="1" * 64,
                created_by=author.id,
                updated_by=author.id,
            )
            db.add(alternative)
            db.flush()
            convergence.recommended_alternative_id = alternative.id
            convergence.status = "RECOMMENDED"
            convergence.recommendation_reason = "Independent governed recommendation."
            convergence.recommendation_hash = "2" * 64
            convergence.recommended_by = author.id
            convergence.recommended_at = utc_now()
            db.flush()

            preparation = InvestmentGatePreparation(
                tenant_id=author.tenant_id,
                portfolio_workspace_id=portfolio.id,
                preparation_number=f"W2A-PREP-{token}",
                logical_code=f"W2A-PREP-{token}",
                revision=1,
                name="PYP-FFA governed preparation",
                description="Frozen package reused by Gate07K decisions.",
                investment_gate_profile_id=template.id,
                profile_code="PYP-FFA",
                profile_revision=template.revision,
                profile_hash=template.content_hash,
                source_convergence_id=convergence.id,
                source_convergence_revision=convergence.convergence_revision,
                source_recommendation_hash=convergence.recommendation_hash,
                recommended_alternative_id=alternative.id,
                recommended_project_set_hash=alternative.selected_project_set_hash,
                status="FROZEN",
                readiness_status="READY",
                source_snapshot_json={},
                evidence_summary_json={},
                conditions_json=[],
                warnings_json=[],
                blockers_json=[],
                preparation_source_hash="3" * 64,
                preparation_hash="4" * 64,
                created_by=author.id,
                updated_by=author.id,
                frozen_by=author.id,
                frozen_at=utc_now(),
            )
            db.add(preparation)
            db.flush()

            decision_common = {
                "tenant_id": author.tenant_id,
                "investment_gate_preparation_id": preparation.id,
                "portfolio_workspace_id": portfolio.id,
                "investment_gate_profile_id": template.id,
                "decision_scope_type": "EXACT_PROJECT_SET",
                "decision_scope_hash": alternative.selected_project_set_hash,
                "status": "DECIDED",
                "outcome": "GO",
                "executive_summary": "Controlled semantic source.",
                "rationale": "Exercise existing Gate07K authority semantics.",
                "conditions_json": [],
                "source_preparation_hash": preparation.preparation_hash,
                "source_package_hash": preparation.preparation_hash,
                "source_profile_hash": template.content_hash,
                "decision_package_snapshot_json": {},
                "configuration_id": template.id,
                "configuration_revision": template.revision,
                "configuration_hash": template.content_hash,
                "configuration_snapshot_json": template.content_json,
                "authority_model": "SINGLE_DECISION_MAKER",
                "authority_snapshot_json": {},
                "committee_snapshot_json": {},
                "quorum_snapshot_json": {},
                "voting_rule_snapshot_json": {},
                "checklist_snapshot_json": [],
                "decision_maker_user_id": author.id,
                "decided_at": utc_now(),
                "decided_by": author.id,
                "created_by": author.id,
                "updated_by": author.id,
            }
            selection_only = InvestmentDecision(
                **decision_common,
                decision_number=f"W2A-SELECT-{token}",
                profile_code="PYP-INV-SELECT",
                decision_round=1,
                title="Selection GO is not full approved capital",
                authorized_amount=Decimal("900000"),
                authorized_currency="COP",
                is_fid=False,
                full_funds_authorized=False,
                investment_authorized=True,
                decision_hash="5" * 64,
            )
            full_funds = InvestmentDecision(
                **decision_common,
                decision_number=f"W2A-FFA-{token}",
                profile_code="PYP-FFA",
                decision_round=1,
                title="PYP-FFA full capital authorization",
                authorized_amount=Decimal("600000"),
                authorized_currency="COP",
                is_fid=True,
                full_funds_authorized=True,
                investment_authorized=True,
                decision_hash="6" * 64,
            )
            db.add_all([selection_only, full_funds])
            db.commit()

            authoritative_state = {
                "convergence": (
                    convergence.status,
                    convergence.recommended_alternative_id,
                    convergence.recommendation_hash,
                ),
                "scenario": (scenario.status, scenario.scenario_hash),
                "decisions": {
                    item.profile_code: (
                        item.status,
                        item.is_fid,
                        item.full_funds_authorized,
                        item.investment_authorized,
                        item.decision_hash,
                    )
                    for item in (selection_only, full_funds)
                },
            }
            comparison = service.allocation_comparison(plan.id)
            grow = next(item for item in comparison.positions if item.bucket_code == "grow")
            assert grow.recommended.item_count == 1
            assert grow.recommended.amount_by_currency == {"COP": Decimal("1000000.00")}
            assert grow.recommended.drilldown[0]["budget_scenario_project_id"] == scenario_project.id
            assert grow.approved.item_count == 1
            assert grow.approved.amount_by_currency == {"COP": Decimal("600000.00")}
            assert grow.approved.drilldown[0]["investment_decision_id"] == full_funds.id
            assert grow.approved.drilldown[0]["profile_code"] == "PYP-FFA"
            assert selection_only.id not in {
                item["investment_decision_id"]
                for position in comparison.positions
                for item in position.approved.drilldown
            }

            db.refresh(convergence)
            db.refresh(scenario)
            db.refresh(selection_only)
            db.refresh(full_funds)
            assert authoritative_state == {
                "convergence": (
                    convergence.status,
                    convergence.recommended_alternative_id,
                    convergence.recommendation_hash,
                ),
                "scenario": (scenario.status, scenario.scenario_hash),
                "decisions": {
                    item.profile_code: (
                        item.status,
                        item.is_fid,
                        item.full_funds_authorized,
                        item.investment_authorized,
                        item.decision_hash,
                    )
                    for item in (selection_only, full_funds)
                },
            }


def test_wave2a_rejects_unknown_bucket_duplicate_target_and_idempotency_payload_drift() -> None:
    with TestClient(app):
        with SessionLocal() as db:
            author, workspace, objective = _foundation(db)
            service = CapitalPlanningService(
                db,
                author.tenant_id,
                author.id,
                _context(author, "capital_planning_allocation_author", "capital_planning_cycle_manager"),
            )
            _publish_configuration(service, objective)
            cycle = _cycle(service, workspace)
            demand = _create_submitted_demand(
                service,
                _demand_payload(
                    cycle.id,
                    workspace.id,
                    author.id,
                    objective.code,
                    theme="asset-integrity",
                    currency="COP",
                    amount="1000000",
                ),
            )
            key = f"wave2a-create-{uuid4()}"
            plan = service.create_allocation_plan(_allocation_payload(cycle.id, workspace.id), key)
            with pytest.raises(HTTPException) as drift:
                service.create_allocation_plan(
                    _allocation_payload(cycle.id, workspace.id).model_copy(update={"name": "Different request"}),
                    key,
                )
            assert drift.value.status_code == 409
            assert drift.value.detail["code"] == "IDEMPOTENCY_KEY_REUSED"

            with pytest.raises(HTTPException) as unknown:
                service.replace_allocation_lines(
                    plan.id,
                    AllocationLinesReplaceIn(
                        lines=[AllocationLineIn(bucket_code="unknown", target_percentage=Decimal("100"))]
                    ),
                    plan.revision_version,
                )
            assert unknown.value.detail["code"] == "UNKNOWN_STRATEGIC_CAPITAL_BUCKET"

            with pytest.raises(ValueError, match="one primary Bucket"):
                BucketClassificationsReplaceIn(
                    classifications=[
                        BucketClassificationIn(
                            target_type="DEMAND",
                            target_id=demand.id,
                            bucket_code="sustain",
                        ),
                        BucketClassificationIn(
                            target_type="DEMAND",
                            target_id=demand.id,
                            bucket_code="grow",
                        ),
                    ]
                )


def test_wave2a_http_contract_requires_idempotency_and_if_match_headers() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin", "password": "1234", "tenant_slug": "demo-energy"},
        )
        assert login.status_code == 200
        authorization = {"Authorization": f"Bearer {login.json()['access_token']}"}
        missing_key = client.post(
            "/api/v1/capital-planning/allocation-plans",
            headers=authorization,
            json={
                "name": "Header validation allocation",
                "description": "Must fail before mutation.",
                "planning_cycle_id": 1,
                "scope_workspace_id": 1,
                "allocation_basis": "PERCENTAGE",
            },
        )
        assert missing_key.status_code == 422
        assert any(item["loc"][-1] == "Idempotency-Key" for item in missing_key.json()["detail"])

        missing_etag = client.put(
            "/api/v1/capital-planning/allocation-plans/1/lines",
            headers=authorization,
            json={"lines": [{"bucket_code": "sustain", "target_percentage": "100"}]},
        )
        assert missing_etag.status_code == 422
        assert any(item["loc"][-1] == "If-Match" for item in missing_etag.json()["detail"])


def test_wave2a_admin_user_rbac_separates_bucket_configuration_from_live_allocation() -> None:
    with TestClient(app):
        with SessionLocal() as db:
            admin, _workspace, _objective = _foundation(db)
            allocation_author = _user(db, admin.tenant_id, "rbac-allocation-author")
            config_admin = _user(db, admin.tenant_id, "rbac-config-admin")
            ensure_enterprise_permissions(db, admin.tenant_id, admin.id)
            db.commit()
            roles = {
                item.code: item
                for item in db.scalars(
                    select(SecurityRole).where(
                        SecurityRole.tenant_id == admin.tenant_id,
                        SecurityRole.code.in_(["capital_planning_allocation_author", "capital_planning_config_admin"]),
                    )
                ).all()
            }
            assert set(roles) == {"capital_planning_allocation_author", "capital_planning_config_admin"}
            db.add_all(
                [
                    SecurityAccessAssignment(
                        tenant_id=admin.tenant_id,
                        subject_type="user",
                        user_id=allocation_author.id,
                        group_id=None,
                        role_id=roles["capital_planning_allocation_author"].id,
                        scope_type="organization",
                        status="active",
                        granted_by_user_id=admin.id,
                    ),
                    SecurityAccessAssignment(
                        tenant_id=admin.tenant_id,
                        subject_type="user",
                        user_id=config_admin.id,
                        group_id=None,
                        role_id=roles["capital_planning_config_admin"].id,
                        scope_type="organization",
                        status="active",
                        granted_by_user_id=admin.id,
                    ),
                ]
            )
            db.commit()

            author_context = require_enterprise_permission(
                db,
                admin.tenant_id,
                allocation_author.id,
                "capital_planning.bucket.classify",
                allowed_role_codes=BUCKET_CLASSIFY_ROLES,
            )
            assert author_context.role_codes == frozenset({"capital_planning_allocation_author"})
            require_enterprise_permission(
                db,
                admin.tenant_id,
                allocation_author.id,
                "capital_planning.allocation.create",
                allowed_role_codes=ALLOCATION_AUTHOR_ROLES,
            )
            with pytest.raises(HTTPException) as author_admin_denied:
                require_enterprise_permission(
                    db,
                    admin.tenant_id,
                    allocation_author.id,
                    "capital_planning.admin.bucket.configure",
                    allowed_role_codes=CONFIG_ROLES,
                )
            assert author_admin_denied.value.status_code == 403

            require_enterprise_permission(
                db,
                admin.tenant_id,
                config_admin.id,
                "capital_planning.admin.bucket.configure",
                allowed_role_codes=CONFIG_ROLES,
            )
            with pytest.raises(HTTPException) as config_live_denied:
                require_enterprise_permission(
                    db,
                    admin.tenant_id,
                    config_admin.id,
                    "capital_planning.allocation.create",
                    allowed_role_codes=ALLOCATION_AUTHOR_ROLES,
                )
            assert config_live_denied.value.status_code == 403
