"""Real PostgreSQL evidence for Wave 2A strategic capital allocation."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text

from app.database.session import SessionLocal, engine
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent, UserAccount
from app.main import app
from app.modules.capital_planning.models import (
    StrategicBucketClassification,
    StrategicCapitalAllocationLine,
    StrategicCapitalAllocationPlan,
)
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
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Wave 2A release evidence requires PYPMIS_TEST_DATABASE_URL with PostgreSQL",
)

BUCKETS = (
    ("sustain", "Sustain", "asset-integrity"),
    ("grow", "Grow", "growth"),
    ("transform", "Transform", "digital"),
    ("comply", "Compliance", "compliance"),
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
        email=f"wave2a-pg-{label}-{uuid4().hex[:10]}@example.test",
        full_name=f"Wave 2A PostgreSQL {label.title()}",
        title=label.title(),
        status="active",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


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
    content.update(
        {
            "themes": [
                {
                    "code": code,
                    "label": code.replace("-", " ").title(),
                    "strategic_objective_codes": [objective.code],
                }
                for code in sorted({item[2] for item in BUCKETS})
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
                    "active": True,
                    "display_order": order,
                    "applicable_theme_codes": [theme],
                    "strategic_objective_codes": [objective.code],
                }
                for order, (code, name, theme) in enumerate(BUCKETS, start=1)
            ],
        }
    )
    draft = service.update_configuration(
        draft.id,
        draft.version,
        name="Wave 2A PostgreSQL configuration",
        description="Disposable release configuration.",
        content=content,
    )
    service.publish_configuration(draft.id, draft.version)


def _demand(
    service: CapitalPlanningService,
    *,
    cycle_id: int,
    workspace_id: int,
    sponsor_id: int,
    objective_code: str,
    themes: list[str],
    currency: str,
    amount: str,
):
    payload = DemandCreate(
        name=f"PostgreSQL capital need {currency} {uuid4().hex[:6]}",
        description="Governed need before solution selection.",
        planning_cycle_id=cycle_id,
        theme_codes=themes,
        strategic_objective_codes=[objective_code],
        business_or_asset_need="Balance strategic capital intent.",
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
        assumptions=["No currency conversion."],
        constraints=["Not approved budget."],
        dependencies=["Governed evaluation."],
    )
    demand = service.create_demand(payload, f"wave2a-pg-demand-{uuid4()}")
    return service.transition_demand(
        demand.id,
        "submit",
        demand.revision_version,
        f"wave2a-pg-demand-submit-{uuid4()}",
    )


def _authority_counts(db) -> dict[str, int]:
    # No rank/budget/resource/Gate07I/Gate07K/FID authority may be mutated.
    candidates = (
        "portfolio_project_evaluations",
        "portfolio_budget_targets",
        "portfolio_budget_scenarios",
        "portfolio_resource_capacity_plans",
        "portfolio_resource_scenarios",
        "portfolio_scenario_convergences",
        "investment_decisions",
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


def test_wave2a_postgres_schema_indexes_and_constraints() -> None:
    inspector = inspect(engine)
    tables = {
        "strategic_capital_allocation_plans",
        "strategic_capital_allocation_lines",
        "strategic_bucket_classifications",
        "strategic_capital_allocation_commands",
    }
    assert tables.issubset(inspector.get_table_names())
    assert all(len(item["name"]) <= 63 for table in tables for item in inspector.get_indexes(table))
    line_unique = {item["name"] for item in inspector.get_unique_constraints("strategic_capital_allocation_lines")}
    assert "uq_capital_allocation_line_bucket" in line_unique
    command_unique = {
        item["name"] for item in inspector.get_unique_constraints("strategic_capital_allocation_commands")
    }
    assert "uq_capital_allocation_command_key" in command_unique


def test_wave2a_postgres_governed_lifecycle_multicurrency_and_side_effect_boundaries() -> None:
    with TestClient(app):
        with SessionLocal() as db:
            author = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            assert author is not None
            reviewer = _user(db, author.tenant_id, "reviewer")
            endorser = _user(db, author.tenant_id, "endorser")
            token = uuid4().hex[:10]
            workspace = EnterpriseWorkspace(
                tenant_id=author.tenant_id,
                parent_id=None,
                workspace_type_code="enterprise",
                code=f"W2A-PG-ENT-{token}",
                external_key=f"wave2a-pg-ent-{token}",
                record_code=f"W2A.PG.ENT.{token}",
                name="Wave 2A PostgreSQL Enterprise",
                status="active",
                defaults_json={"governance_model": "CAPITAL_OWNER"},
                sort_order=1,
                version=1,
                created_by_user_id=author.id,
            )
            objective = EnterpriseStrategicObjective(
                tenant_id=author.tenant_id,
                code=f"wave2a-pg-{uuid4().hex[:8]}",
                name="PostgreSQL allocation objective",
                strategic_line="Capital allocation",
                priority="high",
                horizon="2030",
                responsible_area="Enterprise Strategy",
                active=True,
                description="Disposable Wave 2A objective.",
                source_release_code="WAVE2A-PG",
                created_by_user_id=author.id,
            )
            db.add_all([workspace, objective])
            db.commit()
            db.refresh(workspace)
            db.refresh(objective)
            service = CapitalPlanningService(
                db,
                author.tenant_id,
                author.id,
                _context(author, "capital_planning_allocation_author", "capital_planning_cycle_manager"),
            )
            _publish_configuration(service, objective)
            cycle = service.create_cycle(
                CycleCreate(
                    name="Wave 2A PostgreSQL cycle",
                    planning_horizon_start=date(2027, 1, 1),
                    planning_horizon_end=date(2030, 12, 31),
                    scope_workspace_id=workspace.id,
                    responsible_organization_workspace_id=workspace.id,
                    applicable_theme_codes=[item[2] for item in BUCKETS],
                    capital_basis_currency="COP",
                ),
                f"wave2a-pg-cycle-{uuid4()}",
            )
            cycle = service.transition_cycle(
                cycle.id,
                "open",
                cycle.revision_version,
                f"wave2a-pg-cycle-open-{uuid4()}",
            )
            cop = _demand(
                service,
                cycle_id=cycle.id,
                workspace_id=workspace.id,
                sponsor_id=author.id,
                objective_code=objective.code,
                themes=["growth"],
                currency="COP",
                amount="4000000",
            )
            usd = _demand(
                service,
                cycle_id=cycle.id,
                workspace_id=workspace.id,
                sponsor_id=author.id,
                objective_code=objective.code,
                themes=["digital", "compliance"],
                currency="USD",
                amount="250000",
            )
            before = _authority_counts(db)
            plan = service.create_allocation_plan(
                AllocationPlanCreate(
                    name="Wave 2A PostgreSQL allocation",
                    description="Strategic intent, not Budget/Funding/Resource/FID authority.",
                    planning_cycle_id=cycle.id,
                    scope_workspace_id=workspace.id,
                    allocation_basis=AllocationBasis.PERCENTAGE,
                ),
                f"wave2a-pg-plan-{uuid4()}",
            )
            plan = service.replace_allocation_lines(
                plan.id,
                AllocationLinesReplaceIn(
                    lines=[
                        AllocationLineIn(bucket_code=code, target_percentage=Decimal("25"))
                        for code, _name, _theme in BUCKETS
                    ]
                ),
                plan.revision_version,
            )
            comparison = service.allocation_comparison(plan.id)
            assert comparison.classification_coverage_percentage == Decimal("50.00")
            assert comparison.multi_currency is True
            assert comparison.unclassified["demand"]["item_count"] == 1
            plan = service.replace_bucket_classifications(
                plan.id,
                BucketClassificationsReplaceIn(
                    classifications=[
                        BucketClassificationIn(
                            target_type="DEMAND",
                            target_id=cop.id,
                            bucket_code="grow",
                            rationale="Explicit governed primary classification.",
                        ),
                        BucketClassificationIn(
                            target_type="DEMAND",
                            target_id=usd.id,
                            bucket_code="transform",
                            rationale="Explicit governed primary classification.",
                        ),
                    ]
                ),
                plan.revision_version,
                f"wave2a-pg-classify-{uuid4()}",
            ).allocation_plan
            comparison = service.allocation_comparison(plan.id)
            assert comparison.classification_coverage_percentage == Decimal("100.00")
            assert sum(item.current_demand.item_count for item in comparison.positions) == 2  # no double_count
            assert len(comparison.source_hash) == 64

            plan = service.transition_allocation_plan(
                plan.id,
                "submit",
                plan.revision_version,
                f"wave2a-pg-submit-{uuid4()}",
            )
            reviewer_service = CapitalPlanningService(
                db,
                author.tenant_id,
                reviewer.id,
                _context(reviewer, "capital_planning_allocation_reviewer"),
            )
            plan = reviewer_service.transition_allocation_plan(
                plan.id,
                "review",
                plan.revision_version,
                f"wave2a-pg-review-{uuid4()}",
            )
            endorser_service = CapitalPlanningService(
                db,
                author.tenant_id,
                endorser.id,
                _context(endorser, "capital_planning_allocation_endorser"),
            )
            plan = endorser_service.transition_allocation_plan(
                plan.id,
                "endorse",
                plan.revision_version,
                f"wave2a-pg-endorse-{uuid4()}",
            )
            assert plan.status == "ENDORSED"
            assert plan.endorsed_snapshot_hash and len(plan.endorsed_snapshot_hash) == 64
            assert _authority_counts(db) == before
            assert (
                db.scalar(
                    select(func.count(StrategicCapitalAllocationLine.id)).where(
                        StrategicCapitalAllocationLine.allocation_plan_id == plan.id
                    )
                )
                == 4
            )
            assert (
                db.scalar(
                    select(func.count(StrategicBucketClassification.id)).where(
                        StrategicBucketClassification.allocation_plan_id == plan.id
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
            stored = db.get(StrategicCapitalAllocationPlan, plan.id)
            assert stored is not None
            assert stored.endorsed_snapshot_json["comparison"]["source_hash"] == comparison.source_hash
