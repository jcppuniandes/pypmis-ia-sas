"""Real PostgreSQL release evidence for Wave 1 Capital Planning.

This suite exercises the governed happy path against PostgreSQL, including a
concurrent retry of ``Originate Idea``.  Migration reversibility is covered by
the companion migration test that uses an independent disposable database.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text

from app.database.session import SessionLocal, engine
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, UserAccount
from app.main import app
from app.modules.capital_planning.models import CapitalDemandIdeaOrigin, StrategicCapitalDemand
from app.modules.capital_planning.schemas import CycleCreate, DemandCreate, OriginateIdeaIn
from app.modules.capital_planning.service import CONFIG_KIND, DEFAULT_CONFIGURATION, CapitalPlanningService
from app.modules.enterprise_structure.models import EnterpriseStrategicObjective
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.idea_demand.models import Idea
from app.modules.idea_demand.service import IdeaDemandService

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="Wave 1 release evidence requires PYPMIS_TEST_DATABASE_URL with PostgreSQL",
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
        email=f"wave1-pg-{label}-{uuid4().hex[:10]}@example.test",
        full_name=f"Wave 1 PostgreSQL {label.title()}",
        title=label.title(),
        status="active",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _publish_configuration(
    service: CapitalPlanningService,
    objective: EnterpriseStrategicObjective,
) -> None:
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
                    "code": "asset-integrity",
                    "label": "Asset integrity",
                    "strategic_objective_codes": [objective.code],
                }
            ],
            "drivers": [{"code": "compliance", "label": "Compliance"}],
            "categories": [{"code": "sustaining", "label": "Sustaining"}],
            "planning_horizons": [{"code": "near", "label": "Near term"}],
            "urgency_levels": [{"code": "high", "label": "High"}],
            "uncertainty_levels": [{"code": "conceptual", "label": "Conceptual"}],
        }
    )
    draft = service.update_configuration(
        draft.id,
        draft.version,
        name="Wave 1 PostgreSQL release configuration",
        description="Disposable governed release evidence.",
        content=content,
    )
    service.publish_configuration(draft.id, draft.version)


def _demand_payload(
    cycle_id: int,
    workspace_id: int,
    sponsor_id: int,
    objective_code: str,
    currency: str,
) -> DemandCreate:
    return DemandCreate(
        name=f"PostgreSQL governed need {currency} {uuid4().hex[:6]}",
        description="A strategic need before solution selection.",
        planning_cycle_id=cycle_id,
        theme_codes=["asset-integrity"],
        strategic_objective_codes=[objective_code],
        business_or_asset_need="Restore asset integrity before capacity and compliance are constrained.",
        strategic_driver="compliance",
        demand_category="sustaining",
        urgency="high",
        target_horizon="near",
        sponsor_user_id=sponsor_id,
        owning_workspace_id=workspace_id,
        location_context="North terminal",
        indicative_capital_need=Decimal("1250000.00"),
        currency_code=currency,
        uncertainty_level="conceptual",
        assumptions=["Access remains available."],
        constraints=["A shutdown window is required."],
        dependencies=["Complete the integrity study."],
    )


def _side_effect_counts(db) -> dict[str, int]:
    candidates = (
        "projects",
        "portfolio_project_memberships",
        "project_proposals",
        "budgets",
        "funding_sources",
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


def _originate_concurrently(
    tenant_id: int,
    actor_id: int,
    demand_id: int,
    demand_version: int,
    idempotency_key: str,
) -> tuple[int, bool, str]:
    with SessionLocal() as db:
        actor = db.get(UserAccount, actor_id)
        assert actor is not None
        service = CapitalPlanningService(
            db,
            tenant_id,
            actor_id,
            _context(actor, "capital_planning_originator"),
        )
        result = service.originate_idea(
            demand_id,
            OriginateIdeaIn(expected_benefit="Shape governed solution options."),
            demand_version,
            idempotency_key,
        )
        return result.idea_id, result.created, result.source_snapshot_hash


def test_wave1_postgres_schema_indexes_and_nullable_historical_lineage() -> None:
    inspector = inspect(engine)
    assert {
        "capital_planning_cycles",
        "capital_planning_cycle_themes",
        "strategic_capital_demands",
        "strategic_capital_demand_themes",
        "strategic_capital_demand_objectives",
        "capital_demand_idea_origins",
    }.issubset(inspector.get_table_names())
    assert all(len(item["name"]) <= 63 for item in inspector.get_indexes("capital_planning_cycles"))
    demand_indexes = {item["name"] for item in inspector.get_indexes("strategic_capital_demands")}
    assert {"ix_strategic_capital_demand_queue", "ix_strategic_capital_demand_cycle_status"}.issubset(demand_indexes)
    idea_columns = {item["name"]: item for item in inspector.get_columns("ideas")}
    assert idea_columns["source_capital_demand_id"]["nullable"] is True
    assert idea_columns["source_capital_demand_snapshot_hash"]["nullable"] is True


def test_wave1_postgres_happy_path_concurrent_retry_and_side_effect_boundaries() -> None:
    with TestClient(app):
        with SessionLocal() as db:
            author = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            assert author is not None
            workspace = db.scalar(
                select(EnterpriseWorkspace)
                .where(
                    EnterpriseWorkspace.tenant_id == author.tenant_id,
                    EnterpriseWorkspace.workspace_type_code.in_(["enterprise", "business-unit", "portfolio"]),
                    EnterpriseWorkspace.status == "active",
                )
                .order_by(EnterpriseWorkspace.id)
            )
            if workspace is None or (workspace.defaults_json or {}).get("governance_model") != "CAPITAL_OWNER":
                token = uuid4().hex[:10]
                workspace = EnterpriseWorkspace(
                    tenant_id=author.tenant_id,
                    parent_id=None,
                    workspace_type_code="enterprise",
                    code=f"WAVE1-PG-ENT-{token}",
                    external_key=f"wave1-pg-ent-{token}",
                    record_code=f"WAVE1.PG.ENT.{token}",
                    name="Wave 1 PostgreSQL Capital Owner Enterprise",
                    status="active",
                    defaults_json={"governance_model": "CAPITAL_OWNER"},
                    sort_order=1,
                    version=1,
                    created_by_user_id=author.id,
                )
                db.add(workspace)
                db.flush()
            assert (workspace.defaults_json or {}).get("governance_model") == "CAPITAL_OWNER"
            objective = EnterpriseStrategicObjective(
                tenant_id=author.tenant_id,
                code=f"wave1-pg-{uuid4().hex[:8]}",
                name="PostgreSQL governed capital alignment",
                strategic_line="Capital planning",
                priority="high",
                horizon="2030",
                responsible_area="Enterprise Strategy",
                active=True,
                description="Disposable Wave 1 PostgreSQL objective.",
                source_release_code="WAVE1-PG",
                created_by_user_id=author.id,
            )
            db.add(objective)
            db.commit()
            db.refresh(objective)
            reviewer = _user(db, author.tenant_id, "reviewer")
            endorser = _user(db, author.tenant_id, "endorser")
            originator = _user(db, author.tenant_id, "originator")

            author_service = CapitalPlanningService(
                db,
                author.tenant_id,
                author.id,
                _context(author, "capital_planning_author", "capital_planning_cycle_manager"),
            )
            _publish_configuration(author_service, objective)
            cycle = author_service.create_cycle(
                CycleCreate(
                    name="Wave 1 PostgreSQL planning cycle",
                    planning_horizon_start=date(2027, 1, 1),
                    planning_horizon_end=date(2030, 12, 31),
                    scope_workspace_id=workspace.id,
                    responsible_organization_workspace_id=workspace.id,
                    applicable_theme_codes=["asset-integrity"],
                    capital_basis_currency="COP",
                    description="Disposable CAPITAL_OWNER release cycle.",
                ),
                f"wave1-pg-cycle-{uuid4()}",
            )
            cycle = author_service.transition_cycle(
                cycle.id,
                "open",
                cycle.revision_version,
                f"wave1-pg-open-{uuid4()}",
            )
            demand = author_service.create_demand(
                _demand_payload(cycle.id, workspace.id, author.id, objective.code, "COP"),
                f"wave1-pg-demand-{uuid4()}",
            )
            demand = author_service.transition_demand(
                demand.id,
                "submit",
                demand.revision_version,
                f"wave1-pg-submit-{uuid4()}",
            )
            review_service = CapitalPlanningService(
                db,
                author.tenant_id,
                reviewer.id,
                _context(reviewer, "capital_planning_reviewer"),
            )
            demand = review_service.transition_demand(
                demand.id,
                "review",
                demand.revision_version,
                f"wave1-pg-review-{uuid4()}",
            )
            ideas_before_endorse = int(
                db.scalar(select(func.count(Idea.id)).where(Idea.tenant_id == author.tenant_id)) or 0
            )
            endorser_service = CapitalPlanningService(
                db,
                author.tenant_id,
                endorser.id,
                _context(endorser, "capital_planning_endorser"),
            )
            demand = endorser_service.transition_demand(
                demand.id,
                "endorse",
                demand.revision_version,
                f"wave1-pg-endorse-{uuid4()}",
            )
            assert demand.status == "ENDORSED"
            assert demand.endorser_user_id != demand.created_by_user_id
            assert (
                int(db.scalar(select(func.count(Idea.id)).where(Idea.tenant_id == author.tenant_id)) or 0)
                == ideas_before_endorse
            )
            side_effects_before = _side_effect_counts(db)

            # Bootstrap the existing Idea authority before starting concurrent
            # origin requests, so only the business transaction is contested.
            IdeaDemandService(
                db,
                author.tenant_id,
                originator.id,
                _context(originator, "capital_planning_originator"),
            ).ensure_seed()
            db.commit()
            demand_id = demand.id
            demand_version = demand.revision_version
            snapshot_hash = demand.endorsed_snapshot_hash
            tenant_id = author.tenant_id
            originator_id = originator.id
            workspace_id = workspace.id
            objective_id = objective.id
            cycle_id = cycle.id

        origin_key = f"wave1-pg-origin-{uuid4()}"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _index: _originate_concurrently(
                        tenant_id,
                        originator_id,
                        demand_id,
                        demand_version,
                        origin_key,
                    ),
                    range(2),
                )
            )

        with SessionLocal() as db:
            idea_ids = {item[0] for item in results}
            assert len(idea_ids) == 1
            assert sorted(item[1] for item in results) == [False, True]
            assert {item[2] for item in results} == {snapshot_hash}
            assert (
                int(
                    db.scalar(
                        select(func.count(CapitalDemandIdeaOrigin.id)).where(
                            CapitalDemandIdeaOrigin.capital_demand_id == demand_id,
                            CapitalDemandIdeaOrigin.origin_idempotency_key == origin_key,
                        )
                    )
                    or 0
                )
                == 1
            )
            assert int(db.scalar(select(func.count(Idea.id)).where(Idea.id.in_(idea_ids))) or 0) == 1

            actor = db.get(UserAccount, originator_id)
            assert actor is not None
            originator_service = CapitalPlanningService(
                db,
                tenant_id,
                originator_id,
                _context(actor, "capital_planning_originator"),
            )
            second = originator_service.originate_idea(
                demand_id,
                OriginateIdeaIn(title="Alternative governed solution path"),
                demand_version,
                f"wave1-pg-origin-{uuid4()}",
            )
            assert second.idea_id not in idea_ids
            assert (
                int(
                    db.scalar(
                        select(func.count(CapitalDemandIdeaOrigin.id)).where(
                            CapitalDemandIdeaOrigin.capital_demand_id == demand_id
                        )
                    )
                    or 0
                )
                == 2
            )
            assert side_effects_before == _side_effect_counts(db)

            author = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            assert author is not None
            workspace = db.get(EnterpriseWorkspace, workspace_id)
            objective = db.get(EnterpriseStrategicObjective, objective_id)
            assert workspace is not None and objective is not None
            author_service = CapitalPlanningService(
                db,
                tenant_id,
                author.id,
                _context(author, "capital_planning_author", "capital_planning_cycle_manager"),
            )
            author_service.create_demand(
                _demand_payload(cycle_id, workspace.id, author.id, objective.code, "USD"),
                f"wave1-pg-demand-{uuid4()}",
            )
            summary = author_service.demand_summary(
                planning_cycle_id=cycle_id,
                status="ENDORSED,DRAFT",
            )
            assert set(summary.indicative_capital_totals_by_currency) == {"COP", "USD"}
            assert summary.normalization_warning

            origin = db.scalar(select(CapitalDemandIdeaOrigin).where(CapitalDemandIdeaOrigin.idea_id.in_(idea_ids)))
            idea = db.get(Idea, next(iter(idea_ids)))
            assert origin is not None and idea is not None
            assert origin.source_snapshot_hash == snapshot_hash
            assert idea.source_capital_demand_id == demand_id
            assert idea.source_capital_demand_snapshot_hash == snapshot_hash
            assert db.scalar(
                select(func.count(StrategicCapitalDemand.id)).where(StrategicCapitalDemand.tenant_id == tenant_id)
            )
