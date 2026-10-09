"""Wave 1 acceptance coverage for Strategic Capital Planning and Demand."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.database.session import SessionLocal
from app.domain.models import (
    AdminConfiguration,
    EnterpriseWorkspace,
    SecurityAccessAssignment,
    SecurityRole,
    UserAccount,
)
from app.main import app
from app.modules.capital_planning.models import CapitalDemandIdeaOrigin, StrategicCapitalDemand
from app.modules.capital_planning.router import AUTHOR_ROLES, CONFIG_ROLES
from app.modules.capital_planning.schemas import CycleCreate, DemandCreate, OriginateIdeaIn
from app.modules.capital_planning.service import CONFIG_KIND, DEFAULT_CONFIGURATION, CapitalPlanningService
from app.modules.enterprise_structure.models import EnterpriseStrategicObjective
from app.modules.enterprise_structure.permissions import (
    EnterprisePermissionContext,
    ensure_enterprise_permissions,
    require_enterprise_permission,
)
from app.modules.idea_demand.models import Idea
from app.modules.idea_demand.schemas import IdeaCreate
from app.modules.idea_demand.service import IdeaDemandService


def _context(user: UserAccount, *roles: str) -> EnterprisePermissionContext:
    return EnterprisePermissionContext(
        user=user,
        organization_wide=True,
        scope_unit_ids=frozenset(),
        workspace_ids=frozenset(),
        role_codes=frozenset(roles),
    )


def _user(db, tenant_id: int, label: str) -> UserAccount:
    user = UserAccount(
        tenant_id=tenant_id,
        email=f"wave1-{label}-{uuid4().hex[:10]}@example.test",
        full_name=f"Wave 1 {label.title()}",
        title=label.title(),
        status="active",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _foundation(db):
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
    if workspace is None:
        token = uuid4().hex[:10]
        workspace = EnterpriseWorkspace(
            tenant_id=author.tenant_id,
            parent_id=None,
            workspace_type_code="enterprise",
            code=f"WAVE1-ENT-{token}",
            external_key=f"wave1-ent-{token}",
            record_code=f"WAVE1.ENT.{token}",
            name="Wave 1 Capital Owner Enterprise",
            status="active",
            defaults_json={"governance_model": "CAPITAL_OWNER"},
            sort_order=1,
            version=1,
            created_by_user_id=author.id,
        )
        db.add(workspace)
        db.flush()
    objective = EnterpriseStrategicObjective(
        tenant_id=author.tenant_id,
        code=f"wave1-objective-{uuid4().hex[:8]}",
        name="Wave 1 governed growth",
        strategic_line="Capital planning",
        priority="high",
        horizon="2030",
        responsible_area="Enterprise Strategy",
        active=True,
        description="Strategic objective used by the Wave 1 acceptance path.",
        source_release_code="WAVE1-TEST",
        created_by_user_id=author.id,
    )
    db.add(objective)
    db.commit()
    db.refresh(objective)
    return author, workspace, objective


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
                    "code": "growth",
                    "label": "Governed growth",
                    "strategic_objective_codes": [objective.code],
                }
            ],
            "drivers": [{"code": "capacity", "label": "Capacity"}],
            "categories": [{"code": "renewal", "label": "Renewal"}],
            "planning_horizons": [{"code": "2030", "label": "2030"}],
            "urgency_levels": [{"code": "planned", "label": "Planned"}],
            "uncertainty_levels": [{"code": "conceptual", "label": "Conceptual"}],
        }
    )
    draft = service.update_configuration(
        draft.id,
        draft.version,
        name="Wave 1 controlled configuration",
        description="Acceptance configuration for capital planning.",
        content=content,
    )
    service.publish_configuration(draft.id, draft.version)


def _demand_payload(cycle_id: int, workspace_id: int, sponsor_id: int, objective_code: str, currency: str):
    return DemandCreate(
        name=f"Strategic capacity need {currency}",
        description="A governed need, not an approved solution or investment.",
        planning_cycle_id=cycle_id,
        theme_codes=["growth"],
        strategic_objective_codes=[objective_code],
        business_or_asset_need="Capacity must increase while preserving service continuity.",
        strategic_driver="capacity",
        demand_category="renewal",
        urgency="planned",
        target_horizon="2030",
        sponsor_user_id=sponsor_id,
        owning_workspace_id=workspace_id,
        location_context="Enterprise",
        indicative_capital_need="1000000.00",
        currency_code=currency,
        uncertainty_level="conceptual",
        assumptions=["Demand growth remains within the approved planning range."],
        constraints=["No investment approval is implied."],
        dependencies=["Governed Idea evaluation."],
    )


def _side_effect_counts(db) -> dict[str, int]:
    tables = (
        "projects",
        "portfolio_project_memberships",
        "project_proposals",
        "budgets",
        "funding_sources",
        "funds",
        "funding_assignments",
        "economic_financial_models",
    )
    available = set(db.bind.dialect.get_table_names(db.connection()))
    return {
        table: int(db.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one())
        for table in tables
        if table in available
    }


def test_wave1_lifecycle_atomic_origin_idempotency_sod_filters_and_boundaries() -> None:
    with TestClient(app):
        with SessionLocal() as db:
            author, workspace, objective = _foundation(db)
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

            cycle_payload = CycleCreate(
                name="Wave 1 strategic planning cycle",
                planning_horizon_start=date(2027, 1, 1),
                planning_horizon_end=date(2030, 12, 31),
                scope_workspace_id=workspace.id,
                responsible_organization_workspace_id=workspace.id,
                applicable_theme_codes=["growth"],
                capital_basis_currency="COP",
                description="Controlled planning horizon.",
            )
            cycle_key = f"wave1-cycle-{uuid4()}"
            cycle = author_service.create_cycle(cycle_payload, cycle_key)
            duplicate_cycle = author_service.create_cycle(cycle_payload, cycle_key)
            assert duplicate_cycle.id == cycle.id
            cycle = author_service.transition_cycle(cycle.id, "open", cycle.revision_version, f"open-{uuid4()}")

            demand_payload = _demand_payload(cycle.id, workspace.id, author.id, objective.code, "COP")
            demand = author_service.create_demand(demand_payload, f"demand-{uuid4()}")
            with pytest.raises(HTTPException) as stale:
                author_service.update_demand(demand.id, demand_payload, demand.revision_version + 99)
            assert stale.value.status_code == 412
            demand = author_service.transition_demand(demand.id, "submit", demand.revision_version, f"submit-{uuid4()}")
            review_service = CapitalPlanningService(
                db,
                author.tenant_id,
                reviewer.id,
                _context(reviewer, "capital_planning_reviewer"),
            )
            demand = review_service.transition_demand(demand.id, "review", demand.revision_version, f"review-{uuid4()}")
            with pytest.raises(HTTPException) as sod:
                author_service.transition_demand(
                    demand.id, "endorse", demand.revision_version, f"self-endorse-{uuid4()}"
                )
            assert sod.value.status_code == 409
            assert sod.value.detail["code"] == "SOD_AUTHOR_CANNOT_ENDORSE"

            endorser_service = CapitalPlanningService(
                db,
                author.tenant_id,
                endorser.id,
                _context(endorser, "capital_planning_endorser"),
            )
            ideas_before_endorse = int(
                db.scalar(select(func.count(Idea.id)).where(Idea.tenant_id == author.tenant_id)) or 0
            )
            demand = endorser_service.transition_demand(
                demand.id, "endorse", demand.revision_version, f"endorse-{uuid4()}"
            )
            assert demand.status == "ENDORSED"
            assert demand.endorser_user_id == endorser.id
            assert (
                int(db.scalar(select(func.count(Idea.id)).where(Idea.tenant_id == author.tenant_id)) or 0)
                == ideas_before_endorse
            )

            side_effects_before = _side_effect_counts(db)
            originator_service = CapitalPlanningService(
                db,
                author.tenant_id,
                originator.id,
                _context(originator, "capital_planning_originator"),
            )
            origin_key = f"originate-{uuid4()}"
            origin_payload = OriginateIdeaIn(expected_benefit="Validate solution options under Idea governance.")
            first = originator_service.originate_idea(demand.id, origin_payload, demand.revision_version, origin_key)
            retry = originator_service.originate_idea(demand.id, origin_payload, demand.revision_version, origin_key)
            second = originator_service.originate_idea(
                demand.id,
                OriginateIdeaIn(title="Alternative governed solution path"),
                demand.revision_version,
                f"originate-{uuid4()}",
            )
            assert first.created is True and retry.created is False
            assert retry.idea_id == first.idea_id
            assert second.idea_id != first.idea_id
            assert first.source_snapshot_hash == demand.endorsed_snapshot_hash
            assert side_effects_before == _side_effect_counts(db)
            assert (
                int(
                    db.scalar(
                        select(func.count(CapitalDemandIdeaOrigin.id)).where(
                            CapitalDemandIdeaOrigin.capital_demand_id == demand.id
                        )
                    )
                    or 0
                )
                == 2
            )
            linked_ideas = list(db.scalars(select(Idea).where(Idea.id.in_([first.idea_id, second.idea_id]))).all())
            assert all(item.source_capital_demand_id == demand.id for item in linked_ideas)
            assert all(
                item.source_capital_demand_snapshot_hash == demand.endorsed_snapshot_hash for item in linked_ideas
            )
            stored_origin = db.scalar(select(CapitalDemandIdeaOrigin).where(CapitalDemandIdeaOrigin.id == first.id))
            assert stored_origin is not None
            assert len(stored_origin.origin_request_hash) == 64
            assert stored_origin.source_snapshot_json["status"] == "ENDORSED"

            usd_demand = author_service.create_demand(
                _demand_payload(cycle.id, workspace.id, author.id, objective.code, "USD"),
                f"demand-{uuid4()}",
            )
            page = author_service.demands(status="ENDORSED,DRAFT", planning_cycle_id=cycle.id, page_size=1)
            assert page.total == 2
            assert len(page.items) == 1
            summary = author_service.demand_summary(status="ENDORSED,DRAFT", planning_cycle_id=cycle.id)
            assert summary.demand_count == 2
            assert summary.status_counts == {"ENDORSED": 1, "DRAFT": 1}
            assert set(summary.indicative_capital_totals_by_currency) == {"COP", "USD"}
            assert summary.normalization_warning
            assert author_service.demands(mine=True).total >= 2
            assert usd_demand.status == "DRAFT"
            with pytest.raises(HTTPException) as invalid_filter:
                author_service.demands(status="ENDORSED,NOT_A_STATE")
            assert invalid_filter.value.status_code == 422


def test_wave1_transition_requires_idempotency_header() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin", "password": "1234", "tenant_slug": "demo-energy"},
        )
        assert login.status_code == 200
        response = client.post(
            "/api/v1/capital-planning/demands/1/endorse",
            headers={"Authorization": f"Bearer {login.json()['access_token']}", "If-Match": '"1"'},
            json={"reason": "Should fail before mutation."},
        )
        assert response.status_code == 422
        assert any(item["loc"][-1] == "Idempotency-Key" for item in response.json()["detail"])


def test_wave1_config_and_user_duties_are_segregated_by_real_rbac() -> None:
    with TestClient(app):
        with SessionLocal() as db:
            admin, _workspace, _objective = _foundation(db)
            config_actor = _user(db, admin.tenant_id, "config-only")
            author = _user(db, admin.tenant_id, "author-only")
            ensure_enterprise_permissions(db, admin.tenant_id, admin.id)
            db.commit()
            roles = {
                item.code: item
                for item in db.scalars(
                    select(SecurityRole).where(
                        SecurityRole.tenant_id == admin.tenant_id,
                        SecurityRole.code.in_(["capital_planning_config_admin", "capital_planning_author"]),
                    )
                ).all()
            }
            assert set(roles) == {"capital_planning_config_admin", "capital_planning_author"}
            db.add_all(
                [
                    SecurityAccessAssignment(
                        tenant_id=admin.tenant_id,
                        subject_type="user",
                        user_id=config_actor.id,
                        group_id=None,
                        role_id=roles["capital_planning_config_admin"].id,
                        scope_type="organization",
                        status="active",
                        granted_by_user_id=admin.id,
                    ),
                    SecurityAccessAssignment(
                        tenant_id=admin.tenant_id,
                        subject_type="user",
                        user_id=author.id,
                        group_id=None,
                        role_id=roles["capital_planning_author"].id,
                        scope_type="organization",
                        status="active",
                        granted_by_user_id=admin.id,
                    ),
                ]
            )
            db.commit()

            config_context = require_enterprise_permission(
                db,
                admin.tenant_id,
                config_actor.id,
                "capital_planning.admin.configure",
                allowed_role_codes=CONFIG_ROLES,
            )
            assert config_context.role_codes == frozenset({"capital_planning_config_admin"})
            with pytest.raises(HTTPException) as config_user_mutation:
                require_enterprise_permission(
                    db,
                    admin.tenant_id,
                    config_actor.id,
                    "capital_planning.demand.create",
                    allowed_role_codes=AUTHOR_ROLES,
                )
            assert config_user_mutation.value.status_code == 403

            author_context = require_enterprise_permission(
                db,
                admin.tenant_id,
                author.id,
                "capital_planning.demand.create",
                allowed_role_codes=AUTHOR_ROLES,
            )
            assert author_context.role_codes == frozenset({"capital_planning_author"})
            with pytest.raises(HTTPException) as user_admin_route:
                require_enterprise_permission(
                    db,
                    admin.tenant_id,
                    author.id,
                    "capital_planning.admin.configure",
                    allowed_role_codes=CONFIG_ROLES,
                )
            assert user_admin_route.value.status_code == 403


def test_wave1_historical_ideas_remain_nullable() -> None:
    with TestClient(app):
        with SessionLocal() as db:
            author, workspace, objective = _foundation(db)
            context = _context(author, "idea_requestor")
            service = IdeaDemandService(db, author.tenant_id, author.id, context)
            service.ensure_seed()
            options = service.options(workspace.id)
            standalone = service.create(
                IdeaCreate(
                    title="Standalone historical-compatible Idea",
                    description="A direct Idea remains valid without reinterpretation or Capital Demand backfill.",
                    idea_type=options.idea_types[0]["code"],
                    category=options.categories[0]["code"],
                    expected_benefit="Preserve direct Idea compatibility where policy permits.",
                    owning_workspace_id=workspace.id,
                    strategic_objective_codes=[objective.code],
                )
            )
            assert standalone.source_capital_demand_id is None
            assert standalone.source_capital_demand_snapshot_hash is None
            assert db.scalar(select(func.count(StrategicCapitalDemand.id))) is not None


def test_wave1_admin_policy_drives_numbering_lifecycle_required_fields_and_inheritance() -> None:
    with TestClient(app):
        with SessionLocal() as db:
            admin, _existing_workspace, objective = _foundation(db)
            token = uuid4().hex[:8]
            enterprise = EnterpriseWorkspace(
                tenant_id=admin.tenant_id,
                parent_id=None,
                workspace_type_code="enterprise",
                code=f"W1-CFG-ENT-{token}",
                external_key=f"w1-cfg-ent-{token}",
                record_code=f"W1.CFG.ENT.{token}",
                name="Wave 1 configuration enterprise",
                status="active",
                defaults_json={"governance_model": "CAPITAL_OWNER"},
                sort_order=1,
                version=1,
                created_by_user_id=admin.id,
            )
            db.add(enterprise)
            db.flush()
            portfolio = EnterpriseWorkspace(
                tenant_id=admin.tenant_id,
                parent_id=enterprise.id,
                workspace_type_code="portfolio",
                code=f"W1-CFG-PORT-{token}",
                external_key=f"w1-cfg-port-{token}",
                record_code=f"W1.CFG.PORT.{token}",
                name="Wave 1 configuration portfolio",
                status="active",
                defaults_json={},
                sort_order=1,
                version=1,
                created_by_user_id=admin.id,
            )
            db.add(portfolio)
            db.commit()
            db.refresh(enterprise)
            db.refresh(portfolio)

            service = CapitalPlanningService(
                db,
                admin.tenant_id,
                admin.id,
                _context(admin, "organization_admin"),
            )
            service.ensure_seed()
            published = next(
                item for item in service.configurations() if item.code == "default" and item.status == "published"
            )
            override = service.clone_configuration(
                published.id,
                published.version,
                target_workspace_id=enterprise.id,
            )
            assert override.code == f"workspace-{enterprise.id}"
            content = deepcopy(override.content_json)
            content.update(
                {
                    "themes": [
                        {
                            "code": "growth",
                            "label": "Governed growth",
                            "strategic_objective_codes": [objective.code],
                        }
                    ],
                    "drivers": [{"code": "capacity", "label": "Capacity"}],
                    "categories": [{"code": "renewal", "label": "Renewal"}],
                    "planning_horizons": [{"code": "2030", "label": "2030"}],
                    "urgency_levels": [{"code": "planned", "label": "Planned"}],
                    "uncertainty_levels": [{"code": "conceptual", "label": "Conceptual"}],
                    "required_fields": ["name", "description", "business_or_asset_need"],
                    "project_type_applicability": ["MINING", "ENERGY"],
                    "numbering": {
                        "cycle_prefix": "PLAN",
                        "cycle_padding": 3,
                        "demand_prefix": "NEED",
                        "demand_padding": 5,
                        "separator": "/",
                    },
                }
            )
            content["lifecycle_rules"]["planning_cycle"]["review"]["enabled"] = False
            override = service.update_configuration(
                override.id,
                override.version,
                name=override.name,
                description="Workspace-scoped governed override.",
                content=content,
            )
            override = service.publish_configuration(override.id, override.version)

            preview = service.configuration_preview(portfolio.id)
            assert preview.persisted is False
            assert preview.source["code"] == f"workspace-{enterprise.id}"
            assert preview.effective["project_type_applicability"] == ["MINING", "ENERGY"]
            assert preview.effective["numbering"]["demand_prefix"] == "NEED"
            assert service.options(portfolio.id).cycle_number_preview.startswith("PLAN/")
            assert service.options(portfolio.id).demand_number_preview.startswith("NEED/")

            cycle = service.create_cycle(
                CycleCreate(
                    name="Configured planning cycle",
                    planning_horizon_start=date(2027, 1, 1),
                    planning_horizon_end=date(2030, 12, 31),
                    scope_workspace_id=portfolio.id,
                    responsible_organization_workspace_id=enterprise.id,
                    applicable_theme_codes=["growth"],
                    capital_basis_currency="COP",
                ),
                f"configured-cycle-{uuid4()}",
            )
            assert cycle.cycle_number.startswith("PLAN/")
            assert len(cycle.cycle_number.split("/")[1]) == 3
            cycle = service.transition_cycle(cycle.id, "open", cycle.revision_version, f"open-{uuid4()}")
            with pytest.raises(HTTPException) as disabled:
                service.transition_cycle(cycle.id, "review", cycle.revision_version, f"review-{uuid4()}")
            assert disabled.value.status_code == 409
            assert disabled.value.detail["code"] == "LIFECYCLE_ACTION_DISABLED"

            payload = _demand_payload(cycle.id, portfolio.id, admin.id, objective.code, "COP").model_copy(
                update={"description": ""}
            )
            demand = service.create_demand(payload, f"configured-demand-{uuid4()}")
            assert demand.demand_number.startswith("NEED/")
            assert len(demand.demand_number.split("/")[1]) == 5
            assert demand.readiness["status"] == "BLOCKED"
            assert "REQUIRED_FIELD:description" in demand.readiness["blocking_issues"]

            draft_cycle = service.create_cycle(
                CycleCreate(
                    name="Draft cycle cannot receive a Demand",
                    planning_horizon_start=date(2028, 1, 1),
                    planning_horizon_end=date(2031, 12, 31),
                    scope_workspace_id=portfolio.id,
                    applicable_theme_codes=["growth"],
                ),
                f"draft-cycle-{uuid4()}",
            )
            with pytest.raises(HTTPException) as draft_target:
                service.update_demand(
                    demand.id,
                    payload.model_copy(update={"planning_cycle_id": draft_cycle.id}),
                    demand.revision_version,
                )
            assert draft_target.value.detail["code"] == "PLANNING_CYCLE_NOT_OPEN"

            invalid = service.clone_configuration(override.id, override.version)
            invalid_content = deepcopy(invalid.content_json)
            invalid_content["required_fields"] = ["name", "not_a_demand_field"]
            with pytest.raises(HTTPException) as invalid_required:
                service.update_configuration(
                    invalid.id,
                    invalid.version,
                    name=invalid.name,
                    description=invalid.description,
                    content=invalid_content,
                )
            assert invalid_required.value.detail["code"] == "UNSUPPORTED_REQUIRED_FIELD"
