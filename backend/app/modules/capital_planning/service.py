"""Application service for Strategic Capital Planning and Demand Wave 1."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, AdminNumberSequence, EnterpriseWorkspace, SecurityEvent, UserAccount
from app.modules.capital_planning.models import (
    CapitalDemandIdeaOrigin,
    CapitalPlanningCycle,
    CapitalPlanningCycleTheme,
    StrategicBucketClassification,
    StrategicCapitalAllocationCommand,
    StrategicCapitalAllocationLine,
    StrategicCapitalAllocationPlan,
    StrategicCapitalDemand,
    StrategicCapitalDemandObjective,
    StrategicCapitalDemandTheme,
)
from app.modules.capital_planning.schemas import (
    AllocationComparisonOut,
    AllocationLineIn,
    AllocationLineOut,
    AllocationLinesReplaceIn,
    AllocationOptionsOut,
    AllocationPlanCreate,
    AllocationPlanHistoryItemOut,
    AllocationPlanOut,
    AllocationPlanPageOut,
    AllocationPlanUpdate,
    AllocationPositionOut,
    BucketClassificationBatchOut,
    BucketClassificationIn,
    BucketClassificationOut,
    BucketClassificationsReplaceIn,
    BucketComparisonOut,
    CapitalPlanningOptionsOut,
    ConfigurationPreviewOut,
    CycleCreate,
    CycleOut,
    CyclePageOut,
    CycleSummaryOut,
    CycleUpdate,
    DemandCreate,
    DemandHistoryItemOut,
    DemandOut,
    DemandPageOut,
    DemandUpdate,
    IdeaOriginOut,
    OriginateIdeaIn,
)
from app.modules.enterprise_structure.models import EnterpriseStrategicObjective
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext, ensure_enterprise_permissions
from app.modules.idea_demand.models import Idea
from app.modules.idea_demand.schemas import IdeaCreate
from app.modules.idea_demand.service import IdeaDemandService
from app.modules.investment_decision.models import InvestmentDecision
from app.modules.investment_gate_preparation.models import InvestmentGatePreparation
from app.modules.portfolio_budget.models import PortfolioBudgetScenarioProject
from app.modules.portfolio_convergence.models import PortfolioConvergedAlternative, PortfolioScenarioConvergence
from app.modules.portfolio_planning.models import PortfolioProjectMembership
from app.modules.project_creation.models import ProjectCreationRequest

CONFIG_KIND = "capital_planning_configuration"
CYCLE_NUMBER_RULE = "capital_planning_cycle"
DEMAND_NUMBER_RULE = "strategic_capital_demand"
ALLOCATION_PLAN_NUMBER_RULE = "strategic_capital_allocation_plan"
OWNING_WORKSPACE_TYPES = frozenset({"enterprise", "business-unit", "portfolio"})
TERMINAL_DEMAND_STATES = frozenset({"ENDORSED", "CANCELLED", "SUPERSEDED"})
CYCLE_STATES = frozenset({"DRAFT", "OPEN", "IN_REVIEW", "CLOSED"})
DEMAND_STATES = frozenset(
    {"DRAFT", "SUBMITTED", "IN_REVIEW", "RETURNED", "ENDORSED", "DEFERRED", "CANCELLED", "SUPERSEDED"}
)
ALLOCATION_PLAN_STATES = frozenset(
    {"DRAFT", "SUBMITTED", "IN_REVIEW", "RETURNED", "ENDORSED", "SUPERSEDED", "CANCELLED"}
)
ALLOCATION_PLAN_LIFECYCLE = {
    "submit": ({"DRAFT", "RETURNED"}, "SUBMITTED"),
    "review": ({"SUBMITTED"}, "IN_REVIEW"),
    "return": ({"SUBMITTED", "IN_REVIEW"}, "RETURNED"),
    "endorse": ({"IN_REVIEW"}, "ENDORSED"),
}
SUPPORTED_DEMAND_REQUIRED_FIELDS = frozenset(
    {
        "name",
        "description",
        "planning_cycle_id",
        "theme_codes",
        "strategic_objective_codes",
        "business_or_asset_need",
        "strategic_driver",
        "demand_category",
        "urgency",
        "target_horizon",
        "sponsor_user_id",
        "owning_workspace_id",
        "location_context",
        "indicative_capital_need",
        "currency_code",
        "indicative_capital_range_low",
        "indicative_capital_range_high",
        "uncertainty_level",
        "potential_portfolio_id",
        "assumptions",
        "constraints",
        "dependencies",
    }
)
CYCLE_LIFECYCLE = {
    "open": ({"DRAFT"}, "OPEN"),
    "review": ({"OPEN"}, "IN_REVIEW"),
    "close": ({"IN_REVIEW"}, "CLOSED"),
}
DEMAND_LIFECYCLE = {
    "submit": ({"DRAFT", "RETURNED"}, "SUBMITTED"),
    "review": ({"SUBMITTED"}, "IN_REVIEW"),
    "return": ({"SUBMITTED", "IN_REVIEW"}, "RETURNED"),
    "endorse": ({"IN_REVIEW"}, "ENDORSED"),
    "defer": ({"SUBMITTED", "IN_REVIEW", "RETURNED"}, "DEFERRED"),
    "cancel": ({"DRAFT", "SUBMITTED", "IN_REVIEW", "RETURNED", "DEFERRED"}, "CANCELLED"),
}

DEFAULT_CONFIGURATION = {
    "workspace_id": None,
    "inherit_to_descendants": True,
    "inheritance": {
        "inherit_to_descendants": True,
        "supported_workspace_types": ["enterprise", "business-unit", "portfolio"],
    },
    # Production classifications are deliberately ADMIN-configured.  No
    # example values from the prompt are installed as business data.
    "themes": [],
    "drivers": [],
    "categories": [],
    "planning_horizons": [],
    "urgency_levels": [],
    "uncertainty_levels": [],
    "strategic_capital_buckets": [],
    "allocation_basis_options": ["PERCENTAGE", "INDICATIVE_AMOUNT", "PERCENTAGE_AND_AMOUNT"],
    "allocation_policy": {
        "scope_types": ["enterprise", "business-unit", "portfolio"],
        "eligible_demand_statuses": ["SUBMITTED", "IN_REVIEW", "ENDORSED"],
        "percentage_total_required": "100.0000",
        "percentage_tolerance": "0.0001",
        "allow_unallocated_reserve": False,
        "unclassified_max_percentage": "0",
        "block_endorsement_when_unclassified_exceeds_tolerance": True,
        "classification_modes": ["MANUAL", "THEME_DERIVED", "RULE_DERIVED"],
        "closed_cycle_allows_new_plan": False,
    },
    "required_fields": [
        "name",
        "planning_cycle_id",
        "business_or_asset_need",
        "strategic_driver",
        "target_horizon",
        "sponsor_user_id",
        "owning_workspace_id",
    ],
    "lifecycle_rules": {
        "planning_cycle": {
            action: {"enabled": True, "from": sorted(source), "to": target}
            for action, (source, target) in CYCLE_LIFECYCLE.items()
        },
        "capital_demand": {
            action: {"enabled": True, "from": sorted(source), "to": target}
            for action, (source, target) in DEMAND_LIFECYCLE.items()
        },
        "allocation_plan": {
            action: {"enabled": True, "from": sorted(source), "to": target}
            for action, (source, target) in ALLOCATION_PLAN_LIFECYCLE.items()
        },
    },
    # Capital Demand is upstream of Project creation.  This policy records
    # which eventual Project Types may consume a Demand without inventing a
    # Project or projecting a type onto the Demand itself.
    "project_type_applicability": ["*"],
    "separation_of_duties": {"author_cannot_endorse": True, "allocation_author_cannot_endorse": True},
    "governance_model_applicability": {
        "CAPITAL_OWNER": "DEMAND_ORIGIN_RECOMMENDED",
        "CONTRACTOR_DELIVERY": "DIRECT_IDEA_ALLOWED",
        "DIRECT_INTERNAL": "DIRECT_IDEA_ALLOWED",
        "LEGACY_UNCLASSIFIED": "HISTORICAL_COMPATIBILITY",
    },
    "numbering": {
        "cycle_prefix": "CPC",
        "cycle_padding": 4,
        "demand_prefix": "CD",
        "demand_padding": 6,
        "allocation_plan_prefix": "SCA",
        "allocation_plan_padding": 5,
        "separator": "-",
    },
}


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


class CapitalPlanningService:
    def __init__(
        self,
        db: Session,
        tenant_id: int,
        actor_id: int,
        context: EnterprisePermissionContext,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.context = context

    def ensure_seed(self) -> None:
        """Install configuration and numbering only; never create live records."""
        ensure_enterprise_permissions(self.db, self.tenant_id, self.actor_id)
        if self._latest_configuration("default") is None:
            self.db.add(
                AdminConfiguration(
                    tenant_id=self.tenant_id,
                    kind=CONFIG_KIND,
                    code="default",
                    name="Strategic Capital Planning and Demand",
                    description="Wave 1 governed default; reusable values require ADMIN publication.",
                    status="published",
                    revision=1,
                    version=1,
                    content_json=DEFAULT_CONFIGURATION,
                    content_hash=_hash(DEFAULT_CONFIGURATION),
                    published_at=utc_now(),
                    created_by_user_id=self.actor_id,
                )
            )
        for rule in (CYCLE_NUMBER_RULE, DEMAND_NUMBER_RULE, ALLOCATION_PLAN_NUMBER_RULE):
            sequence = self.db.scalar(
                select(AdminNumberSequence).where(
                    AdminNumberSequence.tenant_id == self.tenant_id,
                    AdminNumberSequence.rule_code == rule,
                    AdminNumberSequence.scope_key == "tenant",
                )
            )
            if sequence is None:
                self.db.add(
                    AdminNumberSequence(
                        tenant_id=self.tenant_id,
                        rule_code=rule,
                        scope_key="tenant",
                        next_value=1,
                        version=1,
                    )
                )
        self.db.commit()

    # ------------------------------------------------------------------
    # Shared options / effective configuration
    # ------------------------------------------------------------------
    def options(self, workspace_id: int | None = None) -> CapitalPlanningOptionsOut:
        workspace = self._workspace(workspace_id) if workspace_id is not None else None
        effective, source, _path = self._effective_configuration(workspace)
        objectives = list(
            self.db.scalars(
                select(EnterpriseStrategicObjective)
                .where(
                    EnterpriseStrategicObjective.tenant_id == self.tenant_id,
                    EnterpriseStrategicObjective.active.is_(True),
                )
                .order_by(EnterpriseStrategicObjective.name, EnterpriseStrategicObjective.id)
            ).all()
        )
        workspaces = self._authorized_workspaces()
        users = list(
            self.db.scalars(
                select(UserAccount)
                .where(UserAccount.tenant_id == self.tenant_id, UserAccount.status == "active")
                .order_by(UserAccount.full_name, UserAccount.id)
            ).all()
        )
        idea_service = IdeaDemandService(self.db, self.tenant_id, self.actor_id, self.context)
        idea_service.ensure_seed()
        idea_options = idea_service.options(workspace_id)
        cycle_numbering = self._numbering_settings(effective, "cycle")
        demand_numbering = self._numbering_settings(effective, "demand")
        return CapitalPlanningOptionsOut(
            cycle_number_preview=self._number_preview(CYCLE_NUMBER_RULE, **cycle_numbering),
            demand_number_preview=self._number_preview(DEMAND_NUMBER_RULE, **demand_numbering),
            themes=list(effective.get("themes") or []),
            demand_drivers=list(effective.get("drivers") or []),
            demand_categories=list(effective.get("categories") or []),
            planning_horizons=list(effective.get("planning_horizons") or []),
            urgency_levels=list(effective.get("urgency_levels") or []),
            uncertainty_levels=list(effective.get("uncertainty_levels") or []),
            strategic_objectives=[{"code": item.code, "label": item.name} for item in objectives],
            owning_workspaces=[self._workspace_option(item) for item in workspaces],
            potential_portfolios=[
                self._workspace_option(item) for item in workspaces if item.workspace_type_code == "portfolio"
            ],
            sponsors=[{"id": item.id, "name": item.full_name, "email": item.email} for item in users],
            idea_types=idea_options.idea_types,
            idea_categories=idea_options.categories,
            effective_configuration=effective,
            configuration_source=source,
        )

    # ------------------------------------------------------------------
    # Planning cycles
    # ------------------------------------------------------------------
    def create_cycle(self, payload: CycleCreate, idempotency_key: str) -> CycleOut:
        duplicate = self.db.scalar(
            select(CapitalPlanningCycle).where(
                CapitalPlanningCycle.tenant_id == self.tenant_id,
                CapitalPlanningCycle.create_idempotency_key == idempotency_key,
            )
        )
        if duplicate is not None:
            self._assert_same_request(
                duplicate.configuration_snapshot_json.get("create_request_hash"), _hash(payload.model_dump())
            )
            return self._cycle_out(duplicate)
        scope = self._workspace(payload.scope_workspace_id) if payload.scope_workspace_id else None
        if scope is not None:
            self._assert_owning_workspace(scope)
        if payload.responsible_organization_workspace_id:
            self._assert_owning_workspace(self._workspace(payload.responsible_organization_workspace_id))
        effective, source, _path = self._effective_configuration(scope)
        self._validate_theme_codes(payload.applicable_theme_codes, effective)
        numbering = self._numbering_settings(effective, "cycle")
        request_hash = _hash(payload.model_dump())
        record = CapitalPlanningCycle(
            tenant_id=self.tenant_id,
            cycle_number=self._reserve_number(CYCLE_NUMBER_RULE, **numbering),
            status="DRAFT",
            configuration_snapshot_json={
                "effective": effective,
                "source": source,
                "create_request_hash": request_hash,
            },
            configuration_hash=_hash(effective),
            create_idempotency_key=idempotency_key,
            created_by_user_id=self.actor_id,
            last_modified_by_user_id=self.actor_id,
            **self._cycle_values(payload),
        )
        try:
            self.db.add(record)
            self.db.flush()
            self._sync_cycle_themes(record.id, payload.applicable_theme_codes)
            self._event("capital_planning.cycle.created", "CapitalPlanningCycle", record.id, {"status": "DRAFT"})
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            duplicate = self.db.scalar(
                select(CapitalPlanningCycle).where(
                    CapitalPlanningCycle.tenant_id == self.tenant_id,
                    CapitalPlanningCycle.create_idempotency_key == idempotency_key,
                )
            )
            if duplicate is None:
                raise
            self._assert_same_request(duplicate.configuration_snapshot_json.get("create_request_hash"), request_hash)
            return self._cycle_out(duplicate)
        self.db.refresh(record)
        return self._cycle_out(record)

    def cycles(self, *, status: str = "", page: int = 1, page_size: int = 50) -> CyclePageOut:
        statement = select(CapitalPlanningCycle).where(CapitalPlanningCycle.tenant_id == self.tenant_id)
        statement = self._cycle_scope(statement)
        statuses = self._status_values(status, CYCLE_STATES)
        if statuses:
            statement = statement.where(CapitalPlanningCycle.status.in_(statuses))
        total = int(self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
        rows = list(
            self.db.scalars(
                statement.order_by(CapitalPlanningCycle.updated_at.desc(), CapitalPlanningCycle.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        counts = self._cycle_demand_counts([item.id for item in rows])
        return CyclePageOut(
            items=[self._cycle_out(item, counts.get(item.id, 0)) for item in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def cycle(self, cycle_id: int) -> CycleOut:
        return self._cycle_out(self._cycle(cycle_id))

    def update_cycle(self, cycle_id: int, payload: CycleUpdate, expected_version: int) -> CycleOut:
        record = self._cycle_for_update(cycle_id)
        self._check_version(record.revision_version, expected_version)
        if record.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "CYCLE_IMMUTABLE", "status": record.status})
        scope = self._workspace(payload.scope_workspace_id) if payload.scope_workspace_id else None
        effective, source, _path = self._effective_configuration(scope)
        self._validate_theme_codes(payload.applicable_theme_codes, effective)
        for key, value in self._cycle_values(payload).items():
            setattr(record, key, value)
        self._sync_cycle_themes(record.id, payload.applicable_theme_codes)
        record.configuration_snapshot_json = {"effective": effective, "source": source}
        record.configuration_hash = _hash(effective)
        self._touch(record)
        self._event("capital_planning.cycle.updated", "CapitalPlanningCycle", record.id, {"status": record.status})
        return self._commit_cycle(record)

    def transition_cycle(self, cycle_id: int, action: str, expected_version: int, idempotency_key: str) -> CycleOut:
        fields = {
            "open": ("open_idempotency_key", "opened_at"),
            "review": ("review_idempotency_key", "review_started_at"),
            "close": ("close_idempotency_key", "closed_at"),
        }
        if action not in fields:
            raise HTTPException(status_code=400, detail={"code": "INVALID_CYCLE_ACTION"})
        key_field, timestamp = fields[action]
        record = self._cycle_for_update(cycle_id)
        if getattr(record, key_field) == idempotency_key:
            return self._cycle_out(record)
        conflict = self.db.scalar(
            select(CapitalPlanningCycle.id).where(
                CapitalPlanningCycle.tenant_id == self.tenant_id,
                getattr(CapitalPlanningCycle, key_field) == idempotency_key,
            )
        )
        if conflict is not None:
            self._idempotency_conflict()
        self._check_version(record.revision_version, expected_version)
        effective = self._normalized_configuration(record.configuration_snapshot_json.get("effective") or {})
        allowed, target = self._lifecycle_transition(effective, "planning_cycle", action)
        if record.status not in allowed:
            raise HTTPException(
                status_code=409,
                detail={"code": "INVALID_CYCLE_TRANSITION", "from": record.status, "action": action},
            )
        state_before = record.status
        record.status = target
        setattr(record, key_field, idempotency_key)
        setattr(record, timestamp, utc_now())
        self._touch(record)
        self._event(
            f"capital_planning.cycle.{action}",
            "CapitalPlanningCycle",
            record.id,
            {"state_before": state_before, "state_after": target, "idempotency_key": idempotency_key},
        )
        return self._commit_cycle(record)

    # ------------------------------------------------------------------
    # Strategic Capital Demands
    # ------------------------------------------------------------------
    def create_demand(self, payload: DemandCreate, idempotency_key: str) -> DemandOut:
        request_hash = _hash(payload.model_dump())
        duplicate = self.db.scalar(
            select(StrategicCapitalDemand).where(
                StrategicCapitalDemand.tenant_id == self.tenant_id,
                StrategicCapitalDemand.create_idempotency_key == idempotency_key,
            )
        )
        if duplicate is not None:
            self._assert_same_request(duplicate.configuration_snapshot_json.get("create_request_hash"), request_hash)
            return self._demand_out(duplicate)
        cycle = self._cycle(payload.planning_cycle_id)
        if cycle.status not in {"OPEN", "IN_REVIEW"}:
            raise HTTPException(status_code=409, detail={"code": "PLANNING_CYCLE_NOT_OPEN", "status": cycle.status})
        workspace = self._workspace(payload.owning_workspace_id)
        self._assert_owning_workspace(workspace)
        effective, source, _path = self._effective_configuration(workspace)
        self._validate_demand(payload, cycle, effective)
        numbering = self._numbering_settings(effective, "demand")
        values = self._demand_values(payload)
        record = StrategicCapitalDemand(
            tenant_id=self.tenant_id,
            demand_number=self._reserve_number(DEMAND_NUMBER_RULE, **numbering),
            status="DRAFT",
            readiness_json={},
            configuration_snapshot_json={
                "effective": effective,
                "source": source,
                "create_request_hash": request_hash,
                "semantics": {"indicative_capital": "INDICATIVE_CAPITAL_NEED"},
            },
            configuration_hash=_hash(effective),
            create_idempotency_key=idempotency_key,
            created_by_user_id=self.actor_id,
            last_modified_by_user_id=self.actor_id,
            **values,
        )
        try:
            self.db.add(record)
            self.db.flush()
            self._sync_demand_links(record.id, payload.theme_codes, payload.strategic_objective_codes)
            record.readiness_json = self._readiness(record)
            record.demand_hash = _hash(self._demand_snapshot(record))
            self._event("capital_planning.demand.created", "StrategicCapitalDemand", record.id, {"status": "DRAFT"})
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            duplicate = self.db.scalar(
                select(StrategicCapitalDemand).where(
                    StrategicCapitalDemand.tenant_id == self.tenant_id,
                    StrategicCapitalDemand.create_idempotency_key == idempotency_key,
                )
            )
            if duplicate is None:
                raise
            self._assert_same_request(duplicate.configuration_snapshot_json.get("create_request_hash"), request_hash)
            return self._demand_out(duplicate)
        self.db.refresh(record)
        return self._demand_out(record)

    def demands(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        status: str = "",
        planning_cycle_id: int | None = None,
        theme_code: str = "",
        strategic_objective_code: str = "",
        driver: str = "",
        sponsor_user_id: int | None = None,
        owning_workspace_id: int | None = None,
        urgency: str = "",
        target_horizon: str = "",
        potential_portfolio_id: int | None = None,
        uncertainty_level: str = "",
        search: str = "",
        mine: bool = False,
    ) -> DemandPageOut:
        statement = self._filtered_demands_statement(
            status=status,
            planning_cycle_id=planning_cycle_id,
            theme_code=theme_code,
            strategic_objective_code=strategic_objective_code,
            driver=driver,
            sponsor_user_id=sponsor_user_id,
            owning_workspace_id=owning_workspace_id,
            urgency=urgency,
            target_horizon=target_horizon,
            potential_portfolio_id=potential_portfolio_id,
            uncertainty_level=uncertainty_level,
            search=search,
            mine=mine,
        )
        total = int(self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
        rows = list(
            self.db.scalars(
                statement.order_by(StrategicCapitalDemand.updated_at.desc(), StrategicCapitalDemand.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return DemandPageOut(items=self._demand_out_many(rows), total=total, page=page, page_size=page_size)

    def demand(self, demand_id: int) -> DemandOut:
        return self._demand_out(self._demand(demand_id))

    def update_demand(self, demand_id: int, payload: DemandUpdate, expected_version: int) -> DemandOut:
        record = self._demand_for_update(demand_id)
        self._check_version(record.revision_version, expected_version)
        if record.status not in {"DRAFT", "RETURNED"}:
            raise HTTPException(status_code=409, detail={"code": "DEMAND_IMMUTABLE", "status": record.status})
        if record.created_by_user_id != self.actor_id and "organization_admin" not in self.context.role_codes:
            raise HTTPException(status_code=403, detail={"code": "DEMAND_AUTHOR_REQUIRED"})
        cycle = self._cycle(payload.planning_cycle_id)
        workspace = self._workspace(payload.owning_workspace_id)
        effective, source, _path = self._effective_configuration(workspace)
        self._validate_demand(payload, cycle, effective)
        for key, value in self._demand_values(payload).items():
            setattr(record, key, value)
        self._sync_demand_links(record.id, payload.theme_codes, payload.strategic_objective_codes)
        record.status = "DRAFT"
        record.configuration_snapshot_json = {
            "effective": effective,
            "source": source,
            "semantics": {"indicative_capital": "INDICATIVE_CAPITAL_NEED"},
        }
        record.configuration_hash = _hash(effective)
        self._touch(record)
        record.readiness_json = self._readiness(record)
        record.demand_hash = _hash(self._demand_snapshot(record))
        self._event("capital_planning.demand.updated", "StrategicCapitalDemand", record.id, {"status": "DRAFT"})
        return self._commit_demand(record)

    def transition_demand(
        self,
        demand_id: int,
        action: str,
        expected_version: int,
        idempotency_key: str,
        reason: str = "",
    ) -> DemandOut:
        transitions = {
            "submit": ("submit_idempotency_key", "submitted_at"),
            "review": ("review_idempotency_key", "review_started_at"),
            "return": ("return_idempotency_key", "returned_at"),
            "endorse": ("endorse_idempotency_key", "endorsed_at"),
            "defer": ("defer_idempotency_key", "deferred_at"),
            "cancel": (
                "cancel_idempotency_key",
                "cancelled_at",
            ),
        }
        if action not in transitions:
            raise HTTPException(status_code=400, detail={"code": "INVALID_DEMAND_ACTION"})
        key_field, timestamp = transitions[action]
        record = self._demand_for_update(demand_id)
        if getattr(record, key_field) == idempotency_key:
            return self._demand_out(record)
        conflict = self.db.scalar(
            select(StrategicCapitalDemand.id).where(
                StrategicCapitalDemand.tenant_id == self.tenant_id,
                getattr(StrategicCapitalDemand, key_field) == idempotency_key,
            )
        )
        if conflict is not None:
            self._idempotency_conflict()
        self._check_version(record.revision_version, expected_version)
        effective = self._normalized_configuration(record.configuration_snapshot_json.get("effective") or {})
        allowed, target = self._lifecycle_transition(effective, "capital_demand", action)
        if record.status not in allowed:
            raise HTTPException(
                status_code=409,
                detail={"code": "INVALID_DEMAND_TRANSITION", "from": record.status, "action": action},
            )
        if action == "endorse":
            if effective.get("separation_of_duties", {}).get("author_cannot_endorse", True) and (
                record.created_by_user_id == self.actor_id
            ):
                raise HTTPException(status_code=409, detail={"code": "SOD_AUTHOR_CANNOT_ENDORSE"})
            readiness = self._readiness(record)
            if readiness.get("status") != "READY":
                raise HTTPException(
                    status_code=422,
                    detail={"code": "DEMAND_NOT_READY", "blocking_issues": readiness.get("blocking_issues", [])},
                )
            record.endorser_user_id = self.actor_id
        elif action == "review":
            record.reviewer_user_id = self.actor_id
        state_before = record.status
        record.status = target
        setattr(record, key_field, idempotency_key)
        setattr(record, timestamp, utc_now())
        self._touch(record)
        record.readiness_json = self._readiness(record)
        record.demand_hash = _hash(self._demand_snapshot(record))
        if action == "endorse":
            snapshot = self._demand_snapshot(record)
            record.endorsed_snapshot_json = snapshot
            record.endorsed_snapshot_hash = _hash(snapshot)
        self._event(
            f"capital_planning.demand.{action}",
            "StrategicCapitalDemand",
            record.id,
            {
                "state_before": state_before,
                "state_after": target,
                "reason": reason,
                "idempotency_key": idempotency_key,
                "endorsement_semantics": "NEED_RECOGNIZED_NOT_INVESTMENT_APPROVED" if action == "endorse" else None,
            },
        )
        return self._commit_demand(record)

    def originate_idea(
        self,
        demand_id: int,
        payload: OriginateIdeaIn,
        expected_version: int,
        idempotency_key: str,
    ) -> IdeaOriginOut:
        request_hash = _hash({"capital_demand_id": demand_id, "payload": payload.model_dump()})
        existing = self.db.scalar(
            select(CapitalDemandIdeaOrigin).where(
                CapitalDemandIdeaOrigin.tenant_id == self.tenant_id,
                CapitalDemandIdeaOrigin.origin_idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            # Re-apply row-level visibility before returning an idempotent
            # result; possession of a key must never bypass workspace scope.
            self._demand(demand_id)
            if existing.capital_demand_id != demand_id:
                self._idempotency_conflict()
            self._assert_same_request(existing.origin_request_hash, request_hash)
            return self._origin_out(existing, created=False)
        idea_service = IdeaDemandService(self.db, self.tenant_id, self.actor_id, self.context)
        # Bootstrap may commit configuration/numbering.  It is deliberately
        # completed before the source row is locked and ETag-revalidated.
        idea_service.ensure_seed()
        demand = self._demand_for_update(demand_id)
        self._check_version(demand.revision_version, expected_version)
        if demand.status != "ENDORSED" or not demand.endorsed_snapshot_hash:
            raise HTTPException(status_code=409, detail={"code": "DEMAND_NOT_ELIGIBLE_FOR_IDEA"})
        idea_options = idea_service.options(demand.owning_workspace_id)
        idea_type_options = [str(item.get("code")) for item in idea_options.idea_types if item.get("code")]
        category_options = [str(item.get("code")) for item in idea_options.categories if item.get("code")]
        categories = set(category_options)
        idea_type = payload.idea_type or (idea_type_options[0] if idea_type_options else "")
        category = payload.category or (
            demand.demand_category
            if demand.demand_category in categories
            else (category_options[0] if category_options else "")
        )
        if not idea_type or not category:
            raise HTTPException(status_code=409, detail={"code": "IDEA_CONFIGURATION_INCOMPLETE"})
        idea_payload = IdeaCreate(
            title=payload.title or demand.name,
            description=payload.description or demand.business_or_asset_need,
            idea_type=idea_type,
            category=category,
            expected_benefit=payload.expected_benefit
            or "Evaluate the governed capital need and shape solution options.",
            estimated_value=demand.indicative_capital_need,
            currency_code=demand.currency_code or "COP",
            owning_workspace_id=demand.owning_workspace_id,
            target_portfolio_workspace_id=demand.potential_portfolio_id,
            strategic_objective_codes=list(demand.strategic_objective_codes_json or []),
            attachment_refs=[],
        )
        # The lineage snapshot is the immutable endorsed Demand snapshot, not
        # a mutable projection of the newly-created Idea.  This keeps the hash
        # directly comparable across Demand, origin relation and Idea.
        origin_snapshot = dict(demand.endorsed_snapshot_json or {})
        origin_snapshot_hash = str(demand.endorsed_snapshot_hash)
        try:
            idea = idea_service.create_from_capital_demand_record(
                idea_payload,
                source_capital_demand_id=demand.id,
                source_snapshot_hash=origin_snapshot_hash,
            )
            origin = CapitalDemandIdeaOrigin(
                tenant_id=self.tenant_id,
                capital_demand_id=demand.id,
                idea_id=idea.id,
                source_demand_version=demand.revision_version,
                source_snapshot_json=origin_snapshot,
                source_snapshot_hash=origin_snapshot_hash,
                source_configuration_hash=demand.configuration_hash,
                origin_request_hash=request_hash,
                origin_idempotency_key=idempotency_key,
                originated_by_user_id=self.actor_id,
            )
            self.db.add(origin)
            self.db.flush()
            self._event(
                "capital_planning.demand.idea_originated",
                "StrategicCapitalDemand",
                demand.id,
                {
                    "idea_id": idea.id,
                    "idea_number": idea.idea_number,
                    "source_snapshot_hash": origin.source_snapshot_hash,
                    "idempotency_key": idempotency_key,
                    "side_effect_boundaries": ["NO_PROJECT", "NO_PORTFOLIO_MEMBERSHIP", "NO_BUDGET", "NO_FUNDING"],
                },
            )
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.db.scalar(
                select(CapitalDemandIdeaOrigin).where(
                    CapitalDemandIdeaOrigin.tenant_id == self.tenant_id,
                    CapitalDemandIdeaOrigin.origin_idempotency_key == idempotency_key,
                )
            )
            if existing is None:
                raise
            self._assert_same_request(existing.origin_request_hash, request_hash)
            if existing.capital_demand_id != demand_id:
                self._idempotency_conflict()
            return self._origin_out(existing, created=False)
        self.db.refresh(origin)
        return self._origin_out(origin, created=True)

    def origins(self, demand_id: int, *, page: int = 1, page_size: int = 50) -> list[IdeaOriginOut]:
        self._demand(demand_id)
        rows = list(
            self.db.scalars(
                select(CapitalDemandIdeaOrigin)
                .where(
                    CapitalDemandIdeaOrigin.tenant_id == self.tenant_id,
                    CapitalDemandIdeaOrigin.capital_demand_id == demand_id,
                )
                .order_by(CapitalDemandIdeaOrigin.originated_at.desc(), CapitalDemandIdeaOrigin.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        ideas = {
            item.id: item
            for item in self.db.scalars(
                select(Idea).where(
                    Idea.tenant_id == self.tenant_id,
                    Idea.id.in_([row.idea_id for row in rows]),
                )
            ).all()
        }
        return [self._origin_out(item, created=False, idea=ideas.get(item.idea_id)) for item in rows]

    def history(self, demand_id: int) -> list[DemandHistoryItemOut]:
        self._demand(demand_id)
        rows = list(
            self.db.scalars(
                select(SecurityEvent)
                .where(
                    SecurityEvent.tenant_id == self.tenant_id,
                    SecurityEvent.target_type == "StrategicCapitalDemand",
                    SecurityEvent.target_id == demand_id,
                )
                .order_by(SecurityEvent.occurred_at, SecurityEvent.id)
            ).all()
        )
        return [
            DemandHistoryItemOut(
                event_type=item.event_type,
                outcome=item.outcome,
                actor_user_id=item.user_id,
                metadata=item.metadata_json or {},
                occurred_at=item.occurred_at,
            )
            for item in rows
        ]

    def cycle_summary(self, cycle_id: int) -> CycleSummaryOut:
        self._cycle(cycle_id)
        rows = list(
            self.db.scalars(
                self._demand_scope(
                    select(StrategicCapitalDemand).where(
                        StrategicCapitalDemand.tenant_id == self.tenant_id,
                        StrategicCapitalDemand.planning_cycle_id == cycle_id,
                    )
                )
            ).all()
        )
        totals: dict[str, Decimal] = {}
        unpriced = 0
        for item in rows:
            if item.indicative_capital_need is None or not item.currency_code:
                unpriced += 1
            else:
                totals[item.currency_code] = totals.get(item.currency_code, Decimal("0")) + item.indicative_capital_need
        return CycleSummaryOut(
            cycle_id=cycle_id,
            demand_count=len(rows),
            status_counts=dict(Counter(item.status for item in rows)),
            theme_counts=dict(Counter(code for item in rows for code in (item.theme_codes_json or []))),
            driver_counts=dict(Counter(item.strategic_driver for item in rows if item.strategic_driver)),
            horizon_counts=dict(Counter(item.target_horizon for item in rows if item.target_horizon)),
            uncertainty_counts=dict(Counter(item.uncertainty_level for item in rows if item.uncertainty_level)),
            indicative_capital_totals_by_currency=totals,
            unpriced_demand_count=unpriced,
            normalization_warning=(
                "Totals remain grouped by currency; no governed FX normalization is applied."
                if len(totals) > 1
                else None
            ),
        )

    def demand_summary(
        self,
        *,
        status: str = "",
        planning_cycle_id: int | None = None,
        theme_code: str = "",
        strategic_objective_code: str = "",
        driver: str = "",
        sponsor_user_id: int | None = None,
        owning_workspace_id: int | None = None,
        urgency: str = "",
        target_horizon: str = "",
        potential_portfolio_id: int | None = None,
        uncertainty_level: str = "",
        search: str = "",
        mine: bool = False,
    ) -> CycleSummaryOut:
        """Return an unpaginated, currency-safe aggregate for a filtered queue."""

        statement = self._filtered_demands_statement(
            status=status,
            planning_cycle_id=planning_cycle_id,
            theme_code=theme_code,
            strategic_objective_code=strategic_objective_code,
            driver=driver,
            sponsor_user_id=sponsor_user_id,
            owning_workspace_id=owning_workspace_id,
            urgency=urgency,
            target_horizon=target_horizon,
            potential_portfolio_id=potential_portfolio_id,
            uncertainty_level=uncertainty_level,
            search=search,
            mine=mine,
        )
        rows = list(self.db.scalars(statement).all())
        totals: dict[str, Decimal] = {}
        unpriced = 0
        for item in rows:
            if item.indicative_capital_need is None or not item.currency_code:
                unpriced += 1
            else:
                totals[item.currency_code] = totals.get(item.currency_code, Decimal("0")) + item.indicative_capital_need
        return CycleSummaryOut(
            cycle_id=planning_cycle_id or 0,
            demand_count=len(rows),
            status_counts=dict(Counter(item.status for item in rows)),
            theme_counts=dict(Counter(code for item in rows for code in (item.theme_codes_json or []))),
            driver_counts=dict(Counter(item.strategic_driver for item in rows if item.strategic_driver)),
            horizon_counts=dict(Counter(item.target_horizon for item in rows if item.target_horizon)),
            uncertainty_counts=dict(Counter(item.uncertainty_level for item in rows if item.uncertainty_level)),
            indicative_capital_totals_by_currency=totals,
            unpriced_demand_count=unpriced,
            normalization_warning=(
                "Totals remain grouped by currency; no governed FX normalization is applied."
                if len(totals) > 1
                else None
            ),
        )

    # ------------------------------------------------------------------
    # Wave 2A Strategic Capital Allocation
    # ------------------------------------------------------------------
    def allocation_options(self, scope_workspace_id: int | None = None) -> AllocationOptionsOut:
        scope = self._workspace(scope_workspace_id) if scope_workspace_id else None
        effective, source, _path = self._effective_configuration(scope)
        workspaces = self._authorized_workspaces()
        cycles = list(
            self.db.scalars(
                self._cycle_scope(
                    select(CapitalPlanningCycle).where(
                        CapitalPlanningCycle.tenant_id == self.tenant_id,
                        CapitalPlanningCycle.status.in_(["OPEN", "IN_REVIEW"]),
                    )
                ).order_by(CapitalPlanningCycle.planning_horizon_start.desc(), CapitalPlanningCycle.id.desc())
            ).all()
        )
        numbering = self._numbering_settings(effective, "allocation_plan")
        return AllocationOptionsOut(
            allocation_plan_number_preview=self._number_preview(ALLOCATION_PLAN_NUMBER_RULE, **numbering),
            planning_cycles=[
                {
                    "id": item.id,
                    "cycle_number": item.cycle_number,
                    "name": item.name,
                    "status": item.status,
                    "planning_horizon_start": item.planning_horizon_start.isoformat(),
                    "planning_horizon_end": item.planning_horizon_end.isoformat(),
                    "scope_workspace_id": item.scope_workspace_id,
                }
                for item in cycles
            ],
            scope_workspaces=[self._workspace_option(item) for item in workspaces],
            portfolios=[self._workspace_option(item) for item in workspaces if item.workspace_type_code == "portfolio"],
            strategic_capital_buckets=deepcopy(effective.get("strategic_capital_buckets") or []),
            allocation_basis_options=list(effective.get("allocation_basis_options") or []),
            scope_types=list(dict(effective.get("allocation_policy") or {}).get("scope_types") or []),
            effective_configuration=effective,
            configuration_source=source,
        )

    def allocation_plans(
        self,
        *,
        planning_cycle_id: int | None = None,
        status: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> AllocationPlanPageOut:
        statement = self._allocation_plan_scope(
            select(StrategicCapitalAllocationPlan).where(StrategicCapitalAllocationPlan.tenant_id == self.tenant_id)
        )
        statuses = self._status_values(status, ALLOCATION_PLAN_STATES)
        if statuses:
            statement = statement.where(StrategicCapitalAllocationPlan.status.in_(statuses))
        if planning_cycle_id:
            statement = statement.where(StrategicCapitalAllocationPlan.planning_cycle_id == planning_cycle_id)
        total = int(self.db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0)
        rows = list(
            self.db.scalars(
                statement.order_by(
                    StrategicCapitalAllocationPlan.updated_at.desc(),
                    StrategicCapitalAllocationPlan.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return AllocationPlanPageOut(
            items=[self._allocation_plan_out(item) for item in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def allocation_plan(self, plan_id: int) -> AllocationPlanOut:
        return self._allocation_plan_out(self._allocation_plan(plan_id))

    def create_allocation_plan(self, payload: AllocationPlanCreate, idempotency_key: str) -> AllocationPlanOut:
        request_hash = _hash(payload.model_dump(mode="json"))
        duplicate = self.db.scalar(
            select(StrategicCapitalAllocationPlan).where(
                StrategicCapitalAllocationPlan.tenant_id == self.tenant_id,
                StrategicCapitalAllocationPlan.create_idempotency_key == idempotency_key,
            )
        )
        if duplicate is not None:
            self._assert_same_request(duplicate.source_context_json.get("create_request_hash"), request_hash)
            return self._allocation_plan_out(duplicate)
        cycle, scope, portfolio, effective, source = self._validate_allocation_plan_payload(payload)
        existing = self.db.scalar(
            select(StrategicCapitalAllocationPlan.id).where(
                StrategicCapitalAllocationPlan.tenant_id == self.tenant_id,
                StrategicCapitalAllocationPlan.planning_cycle_id == cycle.id,
                StrategicCapitalAllocationPlan.scope_workspace_id == scope.id,
                StrategicCapitalAllocationPlan.portfolio_workspace_id.is_(None)
                if portfolio is None
                else StrategicCapitalAllocationPlan.portfolio_workspace_id == portfolio.id,
                StrategicCapitalAllocationPlan.status.in_(["DRAFT", "SUBMITTED", "IN_REVIEW", "RETURNED", "ENDORSED"]),
            )
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail={"code": "ACTIVE_ALLOCATION_PLAN_ALREADY_EXISTS"})
        numbering = self._numbering_settings(effective, "allocation_plan")
        number = self._reserve_number(ALLOCATION_PLAN_NUMBER_RULE, **numbering)
        record = StrategicCapitalAllocationPlan(
            tenant_id=self.tenant_id,
            allocation_plan_number=number,
            logical_code=number,
            plan_revision=1,
            status="DRAFT",
            configuration_id=int(source["configuration_id"]),
            configuration_revision=int(source["revision"]),
            configuration_hash=str(source["content_hash"]),
            configuration_snapshot_json=deepcopy(effective),
            source_context_json={
                "create_request_hash": request_hash,
                "planning_cycle_configuration_hash": cycle.configuration_hash,
                "semantics": "STRATEGIC_ALLOCATION_NOT_BUDGET_FUNDING_RESOURCE_OR_FID",
            },
            create_idempotency_key=idempotency_key,
            created_by_user_id=self.actor_id,
            last_modified_by_user_id=self.actor_id,
            **self._allocation_plan_values(payload),
        )
        record.plan_hash = self._allocation_plan_hash(record, [])
        self.db.add(record)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(status_code=409, detail={"code": "ALLOCATION_PLAN_CONFLICT"}) from None
        self._event(
            "capital_planning.allocation_plan.created",
            "StrategicCapitalAllocationPlan",
            record.id,
            {
                "planning_cycle_id": cycle.id,
                "scope_workspace_id": scope.id,
                "portfolio_workspace_id": portfolio.id if portfolio else None,
            },
        )
        self.db.commit()
        self.db.refresh(record)
        return self._allocation_plan_out(record)

    def update_allocation_plan(
        self, plan_id: int, payload: AllocationPlanUpdate, expected_version: int
    ) -> AllocationPlanOut:
        record = self._allocation_plan_for_update(plan_id)
        self._check_version(record.revision_version, expected_version)
        self._assert_allocation_plan_mutable(record)
        _cycle, _scope, _portfolio, _effective, _source = self._validate_allocation_plan_payload(
            payload,
            expected_configuration_hash=record.configuration_hash,
        )
        for key, value in self._allocation_plan_values(payload).items():
            setattr(record, key, value)
        record.plan_hash = self._allocation_plan_hash(record, self._allocation_lines(record.id))
        self._touch_allocation_plan(record)
        self._event(
            "capital_planning.allocation_plan.updated",
            "StrategicCapitalAllocationPlan",
            record.id,
            {},
        )
        return self._commit_allocation_plan(record)

    def replace_allocation_lines(
        self, plan_id: int, payload: AllocationLinesReplaceIn, expected_version: int
    ) -> AllocationPlanOut:
        record = self._allocation_plan_for_update(plan_id)
        self._check_version(record.revision_version, expected_version)
        self._assert_allocation_plan_mutable(record)
        config = self._normalized_configuration(record.configuration_snapshot_json)
        normalized = self._validate_allocation_lines(record, payload.lines, config)
        self.db.execute(
            delete(StrategicCapitalAllocationLine).where(
                StrategicCapitalAllocationLine.tenant_id == self.tenant_id,
                StrategicCapitalAllocationLine.allocation_plan_id == record.id,
            )
        )
        rows: list[StrategicCapitalAllocationLine] = []
        for item in normalized:
            values = self._allocation_line_values(item)
            line = StrategicCapitalAllocationLine(
                tenant_id=self.tenant_id,
                allocation_plan_id=record.id,
                line_hash=_hash(values),
                **values,
            )
            self.db.add(line)
            rows.append(line)
        self.db.flush()
        record.plan_hash = self._allocation_plan_hash(record, rows)
        self._touch_allocation_plan(record)
        self._event(
            "capital_planning.allocation_plan.lines_replaced",
            "StrategicCapitalAllocationPlan",
            record.id,
            {
                "line_count": len(rows),
                "target_percentage_total": str(sum((item.target_percentage or Decimal("0")) for item in normalized)),
            },
        )
        return self._commit_allocation_plan(record)

    def classify_bucket(
        self,
        plan_id: int,
        payload: BucketClassificationIn,
        expected_version: int,
        idempotency_key: str,
    ) -> BucketClassificationOut:
        record = self._allocation_plan_for_update(plan_id)
        self._check_version(record.revision_version, expected_version)
        self._assert_allocation_plan_mutable(record)
        config = self._normalized_configuration(record.configuration_snapshot_json)
        self._bucket(config, payload.bucket_code)
        request_hash = _hash(payload.model_dump(mode="json"))
        duplicate = self.db.scalar(
            select(StrategicBucketClassification).where(
                StrategicBucketClassification.tenant_id == self.tenant_id,
                StrategicBucketClassification.idempotency_key == idempotency_key,
            )
        )
        if duplicate is not None:
            self._assert_same_request(duplicate.classification_hash, request_hash)
            return self._classification_out(duplicate)
        target_columns = self._classification_target(record, payload.target_type, payload.target_id)
        query = select(StrategicBucketClassification).where(
            StrategicBucketClassification.tenant_id == self.tenant_id,
            StrategicBucketClassification.allocation_plan_id == record.id,
        )
        target_column = {
            "DEMAND": StrategicBucketClassification.capital_demand_id,
            "PROJECT": StrategicBucketClassification.project_workspace_id,
            "PORTFOLIO_MEMBERSHIP": StrategicBucketClassification.portfolio_membership_id,
        }[payload.target_type]
        existing = self.db.scalar(query.where(target_column == payload.target_id).with_for_update())
        if existing is None:
            existing = StrategicBucketClassification(
                tenant_id=self.tenant_id,
                allocation_plan_id=record.id,
                bucket_code=payload.bucket_code,
                classification_source="MANUAL",
                rationale=payload.rationale,
                classification_hash=request_hash,
                idempotency_key=idempotency_key,
                classified_by_user_id=self.actor_id,
                **target_columns,
            )
            self.db.add(existing)
        else:
            existing.bucket_code = payload.bucket_code
            existing.classification_source = "MANUAL"
            existing.rationale = payload.rationale
            existing.classification_hash = request_hash
            existing.idempotency_key = idempotency_key
            existing.classified_by_user_id = self.actor_id
            existing.classified_at = utc_now()
            existing.revision_version += 1
        self.db.flush()
        self._touch_allocation_plan(record)
        record.plan_hash = self._allocation_plan_hash(record, self._allocation_lines(record.id))
        self._event(
            "capital_planning.bucket.classified",
            "StrategicBucketClassification",
            existing.id,
            {
                "allocation_plan_id": record.id,
                "target_type": payload.target_type,
                "target_id": payload.target_id,
                "bucket_code": payload.bucket_code,
            },
        )
        self.db.commit()
        self.db.refresh(existing)
        return self._classification_out(existing)

    def transition_allocation_plan(
        self,
        plan_id: int,
        action: str,
        expected_version: int,
        idempotency_key: str,
        reason: str = "",
    ) -> AllocationPlanOut:
        record = self._allocation_plan_for_update(plan_id)
        self._check_version(record.revision_version, expected_version)
        key_field = {
            "submit": "submit_idempotency_key",
            "review": "review_idempotency_key",
            "return": "return_idempotency_key",
            "endorse": "endorse_idempotency_key",
        }.get(action)
        if key_field is None:
            raise HTTPException(status_code=404, detail={"code": "ALLOCATION_PLAN_ACTION_NOT_FOUND"})
        config = self._normalized_configuration(record.configuration_snapshot_json)
        source_states, target = self._lifecycle_transition(config, "allocation_plan", action)
        prior_key = getattr(record, key_field)
        if prior_key:
            if prior_key == idempotency_key:
                if record.status == target:
                    return self._allocation_plan_out(record)
                self._idempotency_conflict()
            # RETURNED plans may traverse submit/review again.  The aggregate
            # stores the latest key per lifecycle action, while the immutable
            # SecurityEvent history preserves every prior traversal.  A new
            # key is therefore valid only when the current state is a legal
            # source for that action; otherwise it is a conflicting replay.
            if record.status not in source_states:
                self._idempotency_conflict()
        if record.status not in source_states:
            raise HTTPException(
                status_code=409,
                detail={"code": "INVALID_ALLOCATION_PLAN_TRANSITION", "status": record.status, "action": action},
            )
        if action == "submit":
            self._validate_allocation_lines(
                record, [self._allocation_line_in(item) for item in self._allocation_lines(record.id)], config
            )
        if action == "endorse":
            if (
                bool(dict(config.get("separation_of_duties") or {}).get("allocation_author_cannot_endorse", True))
                and record.created_by_user_id == self.actor_id
            ):
                raise HTTPException(status_code=409, detail={"code": "SOD_ALLOCATION_AUTHOR_CANNOT_ENDORSE"})
            comparison = self.allocation_comparison(record.id)
            policy = dict(config.get("allocation_policy") or {})
            if bool(policy.get("block_endorsement_when_unclassified_exceeds_tolerance", True)):
                allowed = Decimal(str(policy.get("unclassified_max_percentage", "0")))
                actual = Decimal("100") - comparison.classification_coverage_percentage
                if actual > allowed:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "UNCLASSIFIED_COVERAGE_EXCEEDS_POLICY",
                            "actual": str(actual),
                            "allowed": str(allowed),
                        },
                    )
        record.status = target
        setattr(record, key_field, idempotency_key)
        now = utc_now()
        if action == "submit":
            record.submitted_at = now
        elif action == "review":
            record.review_started_at = now
            record.reviewer_user_id = self.actor_id
        elif action == "return":
            record.returned_at = now
        elif action == "endorse":
            comparison = self.allocation_comparison(record.id)
            snapshot = self._allocation_plan_snapshot(record, comparison)
            record.endorsed_snapshot_json = snapshot
            record.endorsed_snapshot_hash = _hash(snapshot)
            record.endorsed_at = now
            record.endorser_user_id = self.actor_id
        self._touch_allocation_plan(record)
        self._event(
            f"capital_planning.allocation_plan.{action}",
            "StrategicCapitalAllocationPlan",
            record.id,
            {"from": sorted(source_states), "to": target, "reason": reason.strip()},
        )
        return self._commit_allocation_plan(record)

    def replace_bucket_classifications(
        self,
        plan_id: int,
        payload: BucketClassificationsReplaceIn,
        expected_version: int,
        idempotency_key: str,
    ) -> BucketClassificationBatchOut:
        request_hash = _hash(payload.model_dump(mode="json"))
        command = self.db.scalar(
            select(StrategicCapitalAllocationCommand).where(
                StrategicCapitalAllocationCommand.tenant_id == self.tenant_id,
                StrategicCapitalAllocationCommand.idempotency_key == idempotency_key,
            )
        )
        if command is not None:
            self._assert_same_request(command.request_hash, request_hash)
            if command.allocation_plan_id != plan_id or command.action != "REPLACE_CLASSIFICATIONS":
                self._idempotency_conflict()
            current_plan = self._allocation_plan(plan_id)
            current = list(
                self.db.scalars(
                    select(StrategicBucketClassification)
                    .where(
                        StrategicBucketClassification.tenant_id == self.tenant_id,
                        StrategicBucketClassification.allocation_plan_id == plan_id,
                    )
                    .order_by(StrategicBucketClassification.id)
                ).all()
            )
            return BucketClassificationBatchOut(
                allocation_plan=self._allocation_plan_out(current_plan),
                classifications=[self._classification_out(item) for item in current],
            )
        record = self._allocation_plan_for_update(plan_id)
        self._check_version(record.revision_version, expected_version)
        self._assert_allocation_plan_mutable(record)
        config = self._normalized_configuration(record.configuration_snapshot_json)
        validated: list[tuple[BucketClassificationIn, dict, str]] = []
        for item in payload.classifications:
            self._bucket(config, item.bucket_code)
            target = self._classification_target(record, item.target_type, item.target_id)
            validated.append((item, target, _hash(item.model_dump(mode="json"))))
        self.db.execute(
            delete(StrategicBucketClassification).where(
                StrategicBucketClassification.tenant_id == self.tenant_id,
                StrategicBucketClassification.allocation_plan_id == record.id,
            )
        )
        rows: list[StrategicBucketClassification] = []
        for index, (item, target, item_hash) in enumerate(validated, start=1):
            row = StrategicBucketClassification(
                tenant_id=self.tenant_id,
                allocation_plan_id=record.id,
                bucket_code=item.bucket_code,
                classification_source="MANUAL",
                rationale=item.rationale,
                classification_hash=item_hash,
                idempotency_key=f"{idempotency_key}:{index}",
                classified_by_user_id=self.actor_id,
                **target,
            )
            self.db.add(row)
            rows.append(row)
        self.db.flush()
        self._touch_allocation_plan(record)
        record.plan_hash = self._allocation_plan_hash(record, self._allocation_lines(record.id))
        command = StrategicCapitalAllocationCommand(
            tenant_id=self.tenant_id,
            allocation_plan_id=record.id,
            action="REPLACE_CLASSIFICATIONS",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            result_json={"classification_ids": [item.id for item in rows]},
            actor_user_id=self.actor_id,
        )
        self.db.add(command)
        self._event(
            "capital_planning.bucket.classifications_replaced",
            "StrategicCapitalAllocationPlan",
            record.id,
            {"classification_count": len(rows), "idempotency_key": idempotency_key},
        )
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            duplicate = self.db.scalar(
                select(StrategicCapitalAllocationCommand).where(
                    StrategicCapitalAllocationCommand.tenant_id == self.tenant_id,
                    StrategicCapitalAllocationCommand.idempotency_key == idempotency_key,
                )
            )
            if duplicate is None:
                raise
            self._assert_same_request(duplicate.request_hash, request_hash)
        self.db.refresh(record)
        current = list(
            self.db.scalars(
                select(StrategicBucketClassification)
                .where(
                    StrategicBucketClassification.tenant_id == self.tenant_id,
                    StrategicBucketClassification.allocation_plan_id == plan_id,
                )
                .order_by(StrategicBucketClassification.id)
            ).all()
        )
        return BucketClassificationBatchOut(
            allocation_plan=self._allocation_plan_out(record),
            classifications=[self._classification_out(item) for item in current],
        )

    def create_allocation_plan_revision(
        self, plan_id: int, expected_version: int, idempotency_key: str
    ) -> AllocationPlanOut:
        source_plan = self._allocation_plan_for_update(plan_id)
        self._check_version(source_plan.revision_version, expected_version)
        duplicate = self.db.scalar(
            select(StrategicCapitalAllocationPlan).where(
                StrategicCapitalAllocationPlan.tenant_id == self.tenant_id,
                StrategicCapitalAllocationPlan.revision_idempotency_key == idempotency_key,
            )
        )
        if duplicate is not None:
            return self._allocation_plan_out(duplicate)
        if source_plan.status != "ENDORSED":
            raise HTTPException(status_code=409, detail={"code": "ENDORSED_ALLOCATION_PLAN_REQUIRED"})
        scope = self._workspace(source_plan.scope_workspace_id)
        effective, configuration_source, _path = self._effective_configuration(scope)
        numbering = self._numbering_settings(effective, "allocation_plan")
        source_lines = self._allocation_lines(source_plan.id)
        source_classifications = list(
            self.db.scalars(
                select(StrategicBucketClassification).where(
                    StrategicBucketClassification.tenant_id == self.tenant_id,
                    StrategicBucketClassification.allocation_plan_id == source_plan.id,
                )
            ).all()
        )
        source_plan.status = "SUPERSEDED"
        source_plan.updated_at = utc_now()
        source_plan.revision_version += 1
        successor = StrategicCapitalAllocationPlan(
            tenant_id=self.tenant_id,
            allocation_plan_number=self._reserve_number(ALLOCATION_PLAN_NUMBER_RULE, **numbering),
            logical_code=source_plan.logical_code,
            plan_revision=source_plan.plan_revision + 1,
            name=source_plan.name,
            description=source_plan.description,
            planning_cycle_id=source_plan.planning_cycle_id,
            scope_workspace_id=source_plan.scope_workspace_id,
            portfolio_workspace_id=source_plan.portfolio_workspace_id,
            base_currency=source_plan.base_currency,
            allocation_basis=source_plan.allocation_basis,
            status="DRAFT",
            assumptions_json=deepcopy(source_plan.assumptions_json or []),
            constraints_json=deepcopy(source_plan.constraints_json or []),
            configuration_id=int(configuration_source["configuration_id"]),
            configuration_revision=int(configuration_source["revision"]),
            configuration_hash=str(configuration_source["content_hash"]),
            configuration_snapshot_json=deepcopy(effective),
            source_context_json={"supersedes_plan_id": source_plan.id, "source_plan_hash": source_plan.plan_hash},
            plan_hash="",
            create_idempotency_key=f"revision-create:{idempotency_key}",
            revision_idempotency_key=idempotency_key,
            created_by_user_id=self.actor_id,
            last_modified_by_user_id=self.actor_id,
        )
        self.db.add(successor)
        self.db.flush()
        copied_lines: list[StrategicCapitalAllocationLine] = []
        for line in source_lines:
            values = self._allocation_line_values(self._allocation_line_in(line))
            copied = StrategicCapitalAllocationLine(
                tenant_id=self.tenant_id,
                allocation_plan_id=successor.id,
                line_hash=_hash(values),
                **values,
            )
            self.db.add(copied)
            copied_lines.append(copied)
        for item in source_classifications:
            self.db.add(
                StrategicBucketClassification(
                    tenant_id=self.tenant_id,
                    allocation_plan_id=successor.id,
                    capital_demand_id=item.capital_demand_id,
                    project_workspace_id=item.project_workspace_id,
                    portfolio_membership_id=item.portfolio_membership_id,
                    bucket_code=item.bucket_code,
                    classification_source=item.classification_source,
                    rationale=item.rationale,
                    classification_hash=item.classification_hash,
                    idempotency_key=f"revision:{successor.id}:{item.id}:{idempotency_key}",
                    classified_by_user_id=self.actor_id,
                )
            )
        self.db.flush()
        successor.plan_hash = self._allocation_plan_hash(successor, copied_lines)
        self._event(
            "capital_planning.allocation_plan.revision_created",
            "StrategicCapitalAllocationPlan",
            successor.id,
            {"superseded_plan_id": source_plan.id, "plan_revision": successor.plan_revision},
        )
        self.db.commit()
        self.db.refresh(successor)
        return self._allocation_plan_out(successor)

    def allocation_comparison(self, plan_id: int) -> AllocationComparisonOut:
        record = self._allocation_plan(plan_id)
        config = self._normalized_configuration(record.configuration_snapshot_json)
        buckets = {
            str(item.get("code", "")).strip().lower(): item for item in config.get("strategic_capital_buckets", [])
        }
        lines = self._allocation_lines(record.id)
        manual = self._classification_maps(record.id)
        policy = dict(config.get("allocation_policy") or {})
        eligible_statuses = [str(item).upper() for item in policy.get("eligible_demand_statuses", [])]
        demand_rows = list(
            self.db.scalars(
                select(StrategicCapitalDemand).where(
                    StrategicCapitalDemand.tenant_id == self.tenant_id,
                    StrategicCapitalDemand.planning_cycle_id == record.planning_cycle_id,
                    StrategicCapitalDemand.status.in_(eligible_statuses or ["SUBMITTED", "IN_REVIEW", "ENDORSED"]),
                    StrategicCapitalDemand.owning_workspace_id.in_(
                        self._descendant_workspace_ids(record.scope_workspace_id)
                    ),
                )
            ).all()
        )
        positions: dict[str, dict[str, dict]] = {
            code: {kind: self._empty_position() for kind in ("demand", "portfolio", "recommended", "approved")}
            for code in buckets
        }
        unclassified = {kind: self._empty_position() for kind in ("demand", "portfolio", "recommended", "approved")}
        for demand in demand_rows:
            bucket_code, source = self._resolve_demand_bucket(demand, manual["demand"], buckets)
            target = positions.get(bucket_code, {}).get("demand") if bucket_code else None
            self._accumulate_position(
                target or unclassified["demand"],
                demand.indicative_capital_need,
                demand.currency_code,
                {"id": demand.id, "number": demand.demand_number, "name": demand.name, "classification_source": source},
            )
        project_context = self._project_context(record, manual, buckets)
        for item in project_context["current"]:
            target = positions.get(item["bucket_code"], {}).get("portfolio") if item["bucket_code"] else None
            self._accumulate_position(
                target or unclassified["portfolio"], item["amount"], item["currency"], item["detail"]
            )
        for item in project_context["recommended"]:
            target = positions.get(item["bucket_code"], {}).get("recommended") if item["bucket_code"] else None
            self._accumulate_position(
                target or unclassified["recommended"], item["amount"], item["currency"], item["detail"]
            )
        for item in project_context["approved"]:
            target = positions.get(item["bucket_code"], {}).get("approved") if item["bucket_code"] else None
            self._accumulate_position(
                target or unclassified["approved"], item["amount"], item["currency"], item["detail"]
            )
        totals = {
            kind: self._position_totals(positions, unclassified, kind)
            for kind in ("demand", "portfolio", "recommended", "approved")
        }
        line_by_bucket = {item.bucket_code: item for item in lines}
        result_rows: list[BucketComparisonOut] = []
        currencies: set[str] = set()
        for code, bucket in sorted(buckets.items(), key=lambda item: (int(item[1].get("display_order", 0)), item[0])):
            line = line_by_bucket.get(code)
            converted = {}
            for kind in ("demand", "portfolio", "recommended", "approved"):
                position = positions[code][kind]
                currencies.update(position["amount_by_currency"])
                converted[kind] = self._position_out(position, totals[kind], source=kind.upper())
            current = converted["demand"]
            target_pct = line.target_percentage if line else None
            variance_pct = (
                current.percentage - target_pct if current.percentage is not None and target_pct is not None else None
            )
            demand_amount = self._single_currency_amount(current.amount_by_currency, record.base_currency)
            variance_amount = (
                demand_amount - line.target_amount
                if demand_amount is not None and line and line.target_amount is not None
                else None
            )
            result_rows.append(
                BucketComparisonOut(
                    bucket_code=code,
                    bucket_name=str(bucket.get("name") or bucket.get("label") or code),
                    minimum_percentage=line.minimum_percentage if line else None,
                    target_percentage=target_pct,
                    maximum_percentage=line.maximum_percentage if line else None,
                    minimum_amount=line.minimum_amount if line else None,
                    target_amount=line.target_amount if line else None,
                    maximum_amount=line.maximum_amount if line else None,
                    target_currency=line.currency if line else None,
                    current_demand=converted["demand"],
                    current_portfolio=converted["portfolio"],
                    recommended=converted["recommended"],
                    approved=converted["approved"],
                    variance_vs_target_percentage=variance_pct,
                    variance_vs_target_amount=variance_amount,
                    status=self._allocation_status(line, current, policy),
                )
            )
        eligible_count = len(demand_rows)
        classified_count = sum(item["item_count"] for item in (positions[code]["demand"] for code in positions))
        coverage = (
            Decimal("100.00")
            if eligible_count == 0
            else (Decimal(classified_count) * Decimal("100") / Decimal(eligible_count)).quantize(Decimal("0.01"))
        )
        for kind in ("demand", "portfolio", "recommended", "approved"):
            currencies.update(unclassified[kind]["amount_by_currency"])
        multi_currency = len(currencies) > 1
        unclassified_out = {
            kind: self._position_out(value, totals[kind], source=f"UNCLASSIFIED_{kind.upper()}").model_dump(mode="json")
            for kind, value in unclassified.items()
        }
        source_payload = {
            "plan_hash": record.plan_hash,
            "configuration_hash": record.configuration_hash,
            "eligible_demand_ids": [item.id for item in demand_rows],
            "position_hashes": project_context["source_hashes"],
            "classification_hashes": manual["hashes"],
        }
        return AllocationComparisonOut(
            allocation_plan_id=record.id,
            allocation_plan_version=record.revision_version,
            allocation_plan_hash=record.plan_hash,
            configuration_hash=record.configuration_hash,
            population_definition={
                "eligible_demand_statuses": eligible_statuses,
                "planning_cycle_id": record.planning_cycle_id,
                "scope_workspace_id": record.scope_workspace_id,
            },
            classification_precedence=[
                "EXPLICIT_PROJECT_OR_MEMBERSHIP_CLASSIFICATION",
                "SOURCE_CAPITAL_DEMAND_CLASSIFICATION",
                "THEME_TO_BUCKET_DEFAULT",
                "UNCLASSIFIED",
            ],
            positions=result_rows,
            unclassified=unclassified_out,
            classification_coverage_percentage=coverage,
            multi_currency=multi_currency,
            normalization_warning="Amounts remain grouped by currency; no governed FX conversion is applied."
            if multi_currency
            else None,
            source_hash=_hash(source_payload),
            generated_at=utc_now(),
        )

    def allocation_plan_history(self, plan_id: int) -> list[AllocationPlanHistoryItemOut]:
        plan = self._allocation_plan(plan_id)
        records = list(
            self.db.scalars(
                select(SecurityEvent)
                .where(
                    SecurityEvent.tenant_id == self.tenant_id,
                    SecurityEvent.target_type.in_(["StrategicCapitalAllocationPlan", "StrategicBucketClassification"]),
                )
                .order_by(SecurityEvent.occurred_at.desc(), SecurityEvent.id.desc())
            ).all()
        )
        return [
            AllocationPlanHistoryItemOut(
                event_type=item.event_type,
                outcome=item.outcome,
                actor_user_id=item.user_id,
                metadata=deepcopy(item.metadata_json or {}),
                occurred_at=item.occurred_at,
            )
            for item in records
            if item.target_type == "StrategicCapitalAllocationPlan"
            and item.target_id == plan.id
            or item.target_type == "StrategicBucketClassification"
            and item.metadata_json.get("allocation_plan_id") == plan.id
        ]

    # ------------------------------------------------------------------
    # ADMIN configuration authority
    # ------------------------------------------------------------------
    def configurations(self) -> list[AdminConfiguration]:
        return list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(AdminConfiguration.tenant_id == self.tenant_id, AdminConfiguration.kind == CONFIG_KIND)
                .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
            ).all()
        )

    def configuration_preview(self, workspace_id: int | None) -> ConfigurationPreviewOut:
        workspace = self._workspace(workspace_id) if workspace_id else None
        effective, source, path = self._effective_configuration(workspace)
        return ConfigurationPreviewOut(
            owning_workspace_id=workspace_id,
            persisted=False,
            effective=effective,
            source=source,
            resolution_path=[self._workspace_option(item) for item in path],
        )

    def clone_configuration(
        self,
        configuration_id: int,
        expected_version: int,
        *,
        target_workspace_id: int | None = None,
    ) -> AdminConfiguration:
        source = self._configuration(configuration_id)
        self._check_version(source.version, expected_version)
        if source.status != "published":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_REQUIRED"})
        target_workspace = self._workspace(target_workspace_id) if target_workspace_id is not None else None
        if target_workspace is not None:
            self._assert_owning_workspace(target_workspace)
        target_code = f"workspace-{target_workspace.id}" if target_workspace else source.code
        revision = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(AdminConfiguration.revision), 0)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIG_KIND,
                        AdminConfiguration.code == target_code,
                    )
                )
                or 0
            )
            + 1
        )
        content = self._normalized_configuration(source.content_json)
        content["workspace_id"] = target_workspace.id if target_workspace else source.content_json.get("workspace_id")
        clone = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIG_KIND,
            code=target_code,
            name=f"{source.name} — {target_workspace.name}" if target_workspace else source.name,
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=content,
            content_hash=_hash(content),
            created_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._event(
            "capital_planning.configuration.cloned",
            "AdminConfiguration",
            clone.id,
            {
                "source_configuration_id": source.id,
                "target_workspace_id": target_workspace.id if target_workspace else None,
                "persisted": True,
            },
        )
        self.db.commit()
        self.db.refresh(clone)
        return clone

    def update_configuration(
        self, configuration_id: int, expected_version: int, *, name: str, description: str, content: dict
    ) -> AdminConfiguration:
        record = self._configuration(configuration_id)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "DRAFT_CONFIGURATION_REQUIRED"})
        self._validate_configuration(content, code=record.code)
        record.name = name.strip()
        record.description = description.strip()
        record.content_json = content
        record.content_hash = _hash(content)
        record.version += 1
        record.updated_at = utc_now()
        self._event("capital_planning.configuration.updated", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id)
        self._check_version(record.version, expected_version)
        if record.status == "published":
            return record
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "DRAFT_CONFIGURATION_REQUIRED"})
        self._validate_configuration(record.content_json, code=record.code)
        prior = list(
            self.db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIG_KIND,
                    AdminConfiguration.code == record.code,
                    AdminConfiguration.status == "published",
                )
            ).all()
        )
        for item in prior:
            item.status = "archived"
            item.version += 1
            item.updated_at = utc_now()
        record.status = "published"
        record.published_at = utc_now()
        record.version += 1
        record.updated_at = utc_now()
        self._event("capital_planning.configuration.published", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def archive_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id)
        self._check_version(record.version, expected_version)
        if record.status == "archived":
            return record
        if record.status == "published" and record.code == "default":
            raise HTTPException(status_code=409, detail={"code": "DEFAULT_CONFIGURATION_REPLACEMENT_REQUIRED"})
        record.status = "archived"
        record.version += 1
        record.updated_at = utc_now()
        self._event("capital_planning.configuration.archived", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    # ------------------------------------------------------------------
    # Private validation / mapping helpers
    # ------------------------------------------------------------------
    def _validate_allocation_plan_payload(
        self,
        payload: AllocationPlanCreate | AllocationPlanUpdate,
        *,
        expected_configuration_hash: str | None = None,
    ) -> tuple[CapitalPlanningCycle, EnterpriseWorkspace, EnterpriseWorkspace | None, dict, dict]:
        cycle = self._cycle(payload.planning_cycle_id)
        scope = self._workspace(payload.scope_workspace_id)
        self._assert_owning_workspace(scope)
        portfolio = self._workspace(payload.portfolio_workspace_id) if payload.portfolio_workspace_id else None
        if portfolio is not None and portfolio.workspace_type_code != "portfolio":
            raise HTTPException(status_code=422, detail={"code": "PORTFOLIO_WORKSPACE_REQUIRED"})
        if cycle.status == "CLOSED":
            raise HTTPException(status_code=409, detail={"code": "CLOSED_PLANNING_CYCLE"})
        if cycle.scope_workspace_id and scope.id not in self._descendant_workspace_ids(cycle.scope_workspace_id):
            raise HTTPException(status_code=422, detail={"code": "ALLOCATION_SCOPE_OUTSIDE_PLANNING_CYCLE"})
        effective, source, _path = self._effective_configuration(scope)
        if expected_configuration_hash is not None and source["content_hash"] != expected_configuration_hash:
            raise HTTPException(status_code=409, detail={"code": "ALLOCATION_PLAN_CONFIGURATION_STALE"})
        if scope.workspace_type_code not in set(
            dict(effective.get("allocation_policy") or {}).get("scope_types") or []
        ):
            raise HTTPException(status_code=422, detail={"code": "ALLOCATION_SCOPE_NOT_ALLOWED"})
        if str(payload.allocation_basis) not in set(effective.get("allocation_basis_options") or []):
            raise HTTPException(status_code=422, detail={"code": "ALLOCATION_BASIS_NOT_ALLOWED"})
        if not effective.get("strategic_capital_buckets"):
            raise HTTPException(status_code=409, detail={"code": "NO_PUBLISHED_STRATEGIC_CAPITAL_BUCKETS"})
        if payload.portfolio_workspace_id and scope.workspace_type_code == "portfolio" and scope.id != portfolio.id:
            raise HTTPException(status_code=422, detail={"code": "PORTFOLIO_SCOPE_MISMATCH"})
        return cycle, scope, portfolio, effective, source

    @staticmethod
    def _allocation_plan_values(payload: AllocationPlanCreate | AllocationPlanUpdate) -> dict:
        return {
            "name": payload.name,
            "description": payload.description,
            "planning_cycle_id": payload.planning_cycle_id,
            "scope_workspace_id": payload.scope_workspace_id,
            "portfolio_workspace_id": payload.portfolio_workspace_id,
            "base_currency": payload.base_currency,
            "allocation_basis": str(payload.allocation_basis),
            "assumptions_json": list(payload.assumptions),
            "constraints_json": list(payload.constraints),
        }

    def _validate_allocation_lines(
        self,
        plan: StrategicCapitalAllocationPlan,
        lines: list[AllocationLineIn],
        config: dict,
    ) -> list[AllocationLineIn]:
        if not lines:
            raise HTTPException(status_code=422, detail={"code": "ALLOCATION_LINES_REQUIRED"})
        bucket_codes = {
            str(item.get("code", "")).strip().lower()
            for item in config.get("strategic_capital_buckets", [])
            if item.get("active", True)
        }
        supplied_codes = [item.bucket_code for item in lines]
        unknown = sorted(set(supplied_codes) - bucket_codes)
        if unknown:
            raise HTTPException(
                status_code=422, detail={"code": "UNKNOWN_STRATEGIC_CAPITAL_BUCKET", "buckets": unknown}
            )
        if len(supplied_codes) != len(set(supplied_codes)):
            raise HTTPException(status_code=422, detail={"code": "DUPLICATE_STRATEGIC_CAPITAL_BUCKET"})
        percentage_basis = plan.allocation_basis in {"PERCENTAGE", "PERCENTAGE_AND_AMOUNT"}
        amount_basis = plan.allocation_basis in {"INDICATIVE_AMOUNT", "PERCENTAGE_AND_AMOUNT"}
        for line in lines:
            if percentage_basis and line.target_percentage is None:
                raise HTTPException(
                    status_code=422, detail={"code": "TARGET_PERCENTAGE_REQUIRED", "bucket": line.bucket_code}
                )
            if not percentage_basis and any(
                value is not None
                for value in (line.target_percentage, line.minimum_percentage, line.maximum_percentage)
            ):
                raise HTTPException(
                    status_code=422, detail={"code": "PERCENTAGE_NOT_ALLOWED_FOR_BASIS", "bucket": line.bucket_code}
                )
            if amount_basis and line.target_amount is None:
                raise HTTPException(
                    status_code=422, detail={"code": "TARGET_AMOUNT_REQUIRED", "bucket": line.bucket_code}
                )
            if not amount_basis and any(
                value is not None for value in (line.target_amount, line.minimum_amount, line.maximum_amount)
            ):
                raise HTTPException(
                    status_code=422, detail={"code": "AMOUNT_NOT_ALLOWED_FOR_BASIS", "bucket": line.bucket_code}
                )
            if amount_basis:
                currency = line.currency or plan.base_currency
                if not currency:
                    raise HTTPException(
                        status_code=422,
                        detail={"code": "ALLOCATION_LINE_CURRENCY_REQUIRED", "bucket": line.bucket_code},
                    )
                if plan.base_currency and currency != plan.base_currency:
                    raise HTTPException(
                        status_code=422,
                        detail={"code": "ALLOCATION_LINE_CURRENCY_MISMATCH", "bucket": line.bucket_code},
                    )
                line.currency = currency
            bucket = self._bucket(config, line.bucket_code)
            allowed_objectives = {str(value).strip().lower() for value in bucket.get("strategic_objective_codes", [])}
            if allowed_objectives and set(line.strategic_objective_codes) - allowed_objectives:
                raise HTTPException(
                    status_code=422, detail={"code": "OBJECTIVE_NOT_LINKED_TO_BUCKET", "bucket": line.bucket_code}
                )
        if percentage_basis:
            policy = dict(config.get("allocation_policy") or {})
            required = policy.get("percentage_total_required")
            if required is not None:
                total = sum((line.target_percentage or Decimal("0")) for line in lines)
                target = Decimal(str(required))
                tolerance = Decimal(str(policy.get("percentage_tolerance", "0.0001")))
                if bool(policy.get("allow_unallocated_reserve", False)):
                    invalid = total > target + tolerance
                else:
                    invalid = abs(total - target) > tolerance
                if invalid:
                    raise HTTPException(
                        status_code=422,
                        detail={
                            "code": "INVALID_TARGET_PERCENTAGE_TOTAL",
                            "actual": str(total),
                            "required": str(target),
                            "tolerance": str(tolerance),
                        },
                    )
        return lines

    @staticmethod
    def _allocation_line_values(item: AllocationLineIn) -> dict:
        return {
            "bucket_code": item.bucket_code,
            "target_percentage": item.target_percentage,
            "target_amount": item.target_amount,
            "minimum_percentage": item.minimum_percentage,
            "maximum_percentage": item.maximum_percentage,
            "minimum_amount": item.minimum_amount,
            "maximum_amount": item.maximum_amount,
            "currency": item.currency,
            "rationale": item.rationale.strip(),
            "strategic_objective_codes_json": list(item.strategic_objective_codes),
            "assumptions_json": list(item.assumptions),
            "constraints_json": list(item.constraints),
        }

    @staticmethod
    def _allocation_line_in(item: StrategicCapitalAllocationLine) -> AllocationLineIn:
        return AllocationLineIn(
            bucket_code=item.bucket_code,
            target_percentage=item.target_percentage,
            target_amount=item.target_amount,
            minimum_percentage=item.minimum_percentage,
            maximum_percentage=item.maximum_percentage,
            minimum_amount=item.minimum_amount,
            maximum_amount=item.maximum_amount,
            currency=item.currency,
            rationale=item.rationale,
            strategic_objective_codes=list(item.strategic_objective_codes_json or []),
            assumptions=list(item.assumptions_json or []),
            constraints=list(item.constraints_json or []),
        )

    @staticmethod
    def _bucket(config: dict, bucket_code: str) -> dict:
        normalized = bucket_code.strip().lower()
        bucket = next(
            (
                item
                for item in config.get("strategic_capital_buckets", [])
                if str(item.get("code", "")).strip().lower() == normalized and item.get("active", True)
            ),
            None,
        )
        if bucket is None:
            raise HTTPException(
                status_code=422, detail={"code": "UNKNOWN_STRATEGIC_CAPITAL_BUCKET", "bucket": normalized}
            )
        return bucket

    def _classification_target(self, plan: StrategicCapitalAllocationPlan, target_type: str, target_id: int) -> dict:
        if target_type == "DEMAND":
            demand = self._demand(target_id)
            if demand.planning_cycle_id != plan.planning_cycle_id:
                raise HTTPException(status_code=422, detail={"code": "DEMAND_OUTSIDE_ALLOCATION_PLAN_CYCLE"})
            if demand.owning_workspace_id not in self._descendant_workspace_ids(plan.scope_workspace_id):
                raise HTTPException(status_code=422, detail={"code": "DEMAND_OUTSIDE_ALLOCATION_PLAN_SCOPE"})
            return {"capital_demand_id": demand.id, "project_workspace_id": None, "portfolio_membership_id": None}
        if target_type == "PROJECT":
            project = self._workspace(target_id)
            if project.workspace_type_code != "project":
                raise HTTPException(status_code=422, detail={"code": "PROJECT_WORKSPACE_REQUIRED"})
            return {"capital_demand_id": None, "project_workspace_id": project.id, "portfolio_membership_id": None}
        membership = self.db.scalar(
            select(PortfolioProjectMembership).where(
                PortfolioProjectMembership.id == target_id,
                PortfolioProjectMembership.tenant_id == self.tenant_id,
                PortfolioProjectMembership.status == "ACTIVE",
            )
        )
        if (
            membership is None
            or plan.portfolio_workspace_id
            and membership.portfolio_workspace_id != plan.portfolio_workspace_id
        ):
            raise HTTPException(status_code=404, detail={"code": "PORTFOLIO_MEMBERSHIP_NOT_FOUND"})
        return {"capital_demand_id": None, "project_workspace_id": None, "portfolio_membership_id": membership.id}

    def _allocation_plan_snapshot(
        self, plan: StrategicCapitalAllocationPlan, comparison: AllocationComparisonOut
    ) -> dict:
        cycle = self._cycle(plan.planning_cycle_id)
        return {
            "allocation_plan_id": plan.id,
            "allocation_plan_number": plan.allocation_plan_number,
            "logical_code": plan.logical_code,
            "plan_revision": plan.plan_revision,
            "revision_version": plan.revision_version + 1,
            "status": "ENDORSED",
            "planning_cycle": {
                "id": cycle.id,
                "cycle_number": cycle.cycle_number,
                "name": cycle.name,
                "horizon_start": cycle.planning_horizon_start.isoformat(),
                "horizon_end": cycle.planning_horizon_end.isoformat(),
                "status": cycle.status,
            },
            "scope_workspace_id": plan.scope_workspace_id,
            "portfolio_workspace_id": plan.portfolio_workspace_id,
            "allocation_basis": plan.allocation_basis,
            "base_currency": plan.base_currency,
            "configuration_id": plan.configuration_id,
            "configuration_revision": plan.configuration_revision,
            "configuration_hash": plan.configuration_hash,
            "configuration_snapshot": deepcopy(plan.configuration_snapshot_json or {}),
            "lines": [
                self._allocation_line_in(item).model_dump(mode="json") for item in self._allocation_lines(plan.id)
            ],
            "classification_policy": deepcopy(
                dict(plan.configuration_snapshot_json or {}).get("allocation_policy") or {}
            ),
            "comparison": comparison.model_dump(mode="json"),
            "plan_hash": plan.plan_hash,
            "source_context": deepcopy(plan.source_context_json or {}),
            "future_periodic_portfolio_review_contract": {
                "allocation_plan_id": plan.id,
                "allocation_plan_version": plan.plan_revision,
                "allocation_plan_hash": plan.plan_hash,
                "comparison_source_hash": comparison.source_hash,
            },
        }

    def _allocation_plan_hash(
        self, plan: StrategicCapitalAllocationPlan, lines: list[StrategicCapitalAllocationLine]
    ) -> str:
        return _hash(
            {
                "logical_code": plan.logical_code,
                "plan_revision": plan.plan_revision,
                "name": plan.name,
                "description": plan.description,
                "planning_cycle_id": plan.planning_cycle_id,
                "scope_workspace_id": plan.scope_workspace_id,
                "portfolio_workspace_id": plan.portfolio_workspace_id,
                "base_currency": plan.base_currency,
                "allocation_basis": plan.allocation_basis,
                "assumptions": plan.assumptions_json or [],
                "constraints": plan.constraints_json or [],
                "configuration_hash": plan.configuration_hash,
                "lines": [
                    {
                        **self._allocation_line_values(self._allocation_line_in(item)),
                        "line_hash": item.line_hash,
                    }
                    for item in sorted(lines, key=lambda value: value.bucket_code)
                ],
            }
        )

    def _allocation_plan(self, plan_id: int) -> StrategicCapitalAllocationPlan:
        record = self.db.scalar(
            self._allocation_plan_scope(
                select(StrategicCapitalAllocationPlan).where(
                    StrategicCapitalAllocationPlan.id == plan_id,
                    StrategicCapitalAllocationPlan.tenant_id == self.tenant_id,
                )
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "STRATEGIC_CAPITAL_ALLOCATION_PLAN_NOT_FOUND"})
        return record

    def _allocation_plan_for_update(self, plan_id: int) -> StrategicCapitalAllocationPlan:
        record = self.db.scalar(
            self._allocation_plan_scope(
                select(StrategicCapitalAllocationPlan)
                .where(
                    StrategicCapitalAllocationPlan.id == plan_id,
                    StrategicCapitalAllocationPlan.tenant_id == self.tenant_id,
                )
                .with_for_update()
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "STRATEGIC_CAPITAL_ALLOCATION_PLAN_NOT_FOUND"})
        return record

    def _allocation_plan_scope(self, statement):
        if self.context.organization_wide:
            return statement
        allowed = list(self.context.workspace_ids)
        return statement.where(
            (StrategicCapitalAllocationPlan.created_by_user_id == self.actor_id)
            | (StrategicCapitalAllocationPlan.scope_workspace_id.in_(allowed) if allowed else False)
        )

    def _allocation_lines(self, plan_id: int) -> list[StrategicCapitalAllocationLine]:
        return list(
            self.db.scalars(
                select(StrategicCapitalAllocationLine)
                .where(
                    StrategicCapitalAllocationLine.tenant_id == self.tenant_id,
                    StrategicCapitalAllocationLine.allocation_plan_id == plan_id,
                )
                .order_by(StrategicCapitalAllocationLine.bucket_code, StrategicCapitalAllocationLine.id)
            ).all()
        )

    def _allocation_plan_out(self, record: StrategicCapitalAllocationPlan) -> AllocationPlanOut:
        cycle = self.db.get(CapitalPlanningCycle, record.planning_cycle_id)
        scope = self.db.get(EnterpriseWorkspace, record.scope_workspace_id)
        portfolio = (
            self.db.get(EnterpriseWorkspace, record.portfolio_workspace_id) if record.portfolio_workspace_id else None
        )
        if cycle is None or scope is None:
            raise HTTPException(status_code=409, detail={"code": "ALLOCATION_PLAN_CONTEXT_MISSING"})
        lines = self._allocation_lines(record.id)
        current = self._latest_configuration(f"workspace-{scope.id}") or self._latest_configuration("default")
        source_current = bool(current and current.content_hash == record.configuration_hash)
        readiness = self._allocation_readiness(record, lines)
        return AllocationPlanOut(
            id=record.id,
            allocation_plan_number=record.allocation_plan_number,
            logical_code=record.logical_code,
            plan_revision=record.plan_revision,
            name=record.name,
            description=record.description,
            planning_cycle_id=record.planning_cycle_id,
            planning_cycle_number=cycle.cycle_number,
            planning_cycle_name=cycle.name,
            scope_workspace_id=record.scope_workspace_id,
            scope_workspace_name=scope.name,
            scope_type=scope.workspace_type_code.upper().replace("-", "_"),
            portfolio_workspace_id=record.portfolio_workspace_id,
            portfolio_workspace_name=portfolio.name if portfolio else None,
            base_currency=record.base_currency,
            allocation_basis=record.allocation_basis,
            status=record.status,
            assumptions=list(record.assumptions_json or []),
            constraints=list(record.constraints_json or []),
            configuration_revision=record.configuration_revision,
            configuration_hash=record.configuration_hash,
            plan_hash=record.plan_hash,
            endorsed_snapshot_hash=record.endorsed_snapshot_hash,
            lines=[
                AllocationLineOut(
                    id=item.id,
                    line_hash=item.line_hash,
                    **self._allocation_line_in(item).model_dump(),
                )
                for item in lines
            ],
            readiness=readiness,
            source_current=source_current,
            created_by_user_id=record.created_by_user_id,
            reviewer_user_id=record.reviewer_user_id,
            endorser_user_id=record.endorser_user_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            submitted_at=record.submitted_at,
            review_started_at=record.review_started_at,
            endorsed_at=record.endorsed_at,
            revision_version=record.revision_version,
            allowed_actions=self._allocation_allowed_actions(record),
        )

    def _allocation_readiness(
        self, plan: StrategicCapitalAllocationPlan, lines: list[StrategicCapitalAllocationLine]
    ) -> dict:
        config = self._normalized_configuration(plan.configuration_snapshot_json)
        buckets = [item for item in config.get("strategic_capital_buckets", []) if item.get("active", True)]
        eligible = list(
            self.db.scalars(
                select(StrategicCapitalDemand.id).where(
                    StrategicCapitalDemand.tenant_id == self.tenant_id,
                    StrategicCapitalDemand.planning_cycle_id == plan.planning_cycle_id,
                    StrategicCapitalDemand.status.in_(
                        dict(config.get("allocation_policy") or {}).get("eligible_demand_statuses") or []
                    ),
                )
            ).all()
        )
        classified = set(
            self.db.scalars(
                select(StrategicBucketClassification.capital_demand_id).where(
                    StrategicBucketClassification.tenant_id == self.tenant_id,
                    StrategicBucketClassification.allocation_plan_id == plan.id,
                    StrategicBucketClassification.capital_demand_id.is_not(None),
                )
            ).all()
        )
        coverage = (
            Decimal("100")
            if not eligible
            else Decimal(len(classified & set(eligible))) * Decimal("100") / Decimal(len(eligible))
        )
        dimensions = {
            "BUCKET_COVERAGE": bool(lines)
            and {item.bucket_code for item in lines} <= {str(item.get("code", "")).lower() for item in buckets},
            "TARGET_ALLOCATION": bool(lines),
            "CLASSIFICATION_COVERAGE": str(coverage.quantize(Decimal("0.01"))),
            "CURRENCY_EVALUABILITY": bool(plan.base_currency) if plan.allocation_basis != "PERCENTAGE" else True,
            "STRATEGIC_ALIGNMENT": all(item.strategic_objective_codes_json is not None for item in lines),
        }
        blocking = [key for key, value in dimensions.items() if value is False]
        return {
            "status": "READY" if not blocking else "BLOCKED",
            "dimensions": dimensions,
            "blocking_issues": blocking,
            "semantics": "ALLOCATION_PLAN_READINESS_NOT_GATE07J_EVIDENCE",
        }

    def _allocation_allowed_actions(self, record: StrategicCapitalAllocationPlan) -> list[str]:
        roles = self.context.role_codes
        admin = "organization_admin" in roles
        author = admin or "capital_planning_allocation_author" in roles or "capital_planning_author" in roles
        reviewer = admin or "capital_planning_allocation_reviewer" in roles or "capital_planning_reviewer" in roles
        endorser = admin or "capital_planning_allocation_endorser" in roles or "capital_planning_endorser" in roles
        classifier = admin or "capital_planning_bucket_classifier" in roles or author
        actions: list[str] = []
        if record.status in {"DRAFT", "RETURNED"} and author:
            actions.extend(["edit", "replace_lines", "submit"])
            if classifier:
                actions.append("classify")
        if record.status == "SUBMITTED" and reviewer:
            actions.extend(["review", "return"])
        if record.status == "IN_REVIEW":
            if reviewer:
                actions.append("return")
            if endorser and record.created_by_user_id != self.actor_id:
                actions.append("endorse")
        if record.status == "ENDORSED" and author:
            actions.append("create_revision")
        return sorted(set(actions))

    @staticmethod
    def _assert_allocation_plan_mutable(record: StrategicCapitalAllocationPlan) -> None:
        if record.status not in {"DRAFT", "RETURNED"}:
            raise HTTPException(status_code=409, detail={"code": "ALLOCATION_PLAN_IMMUTABLE", "status": record.status})

    def _touch_allocation_plan(self, record: StrategicCapitalAllocationPlan) -> None:
        record.last_modified_by_user_id = self.actor_id
        record.updated_at = utc_now()
        record.revision_version += 1

    def _commit_allocation_plan(self, record: StrategicCapitalAllocationPlan) -> AllocationPlanOut:
        self.db.commit()
        self.db.refresh(record)
        return self._allocation_plan_out(record)

    @staticmethod
    def _classification_out(record: StrategicBucketClassification) -> BucketClassificationOut:
        if record.capital_demand_id is not None:
            target_type, target_id = "DEMAND", record.capital_demand_id
        elif record.project_workspace_id is not None:
            target_type, target_id = "PROJECT", record.project_workspace_id
        else:
            target_type, target_id = "PORTFOLIO_MEMBERSHIP", int(record.portfolio_membership_id or 0)
        return BucketClassificationOut(
            id=record.id,
            allocation_plan_id=record.allocation_plan_id,
            target_type=target_type,
            target_id=target_id,
            bucket_code=record.bucket_code,
            classification_source=record.classification_source,
            rationale=record.rationale,
            classification_hash=record.classification_hash,
            classified_by_user_id=record.classified_by_user_id,
            classified_at=record.classified_at,
            revision_version=record.revision_version,
        )

    def _classification_maps(self, plan_id: int) -> dict:
        rows = list(
            self.db.scalars(
                select(StrategicBucketClassification).where(
                    StrategicBucketClassification.tenant_id == self.tenant_id,
                    StrategicBucketClassification.allocation_plan_id == plan_id,
                )
            ).all()
        )
        return {
            "demand": {item.capital_demand_id: item.bucket_code for item in rows if item.capital_demand_id is not None},
            "project": {
                item.project_workspace_id: item.bucket_code for item in rows if item.project_workspace_id is not None
            },
            "membership": {
                item.portfolio_membership_id: item.bucket_code
                for item in rows
                if item.portfolio_membership_id is not None
            },
            "hashes": sorted(item.classification_hash for item in rows),
        }

    @staticmethod
    def _resolve_demand_bucket(
        demand: StrategicCapitalDemand, explicit: dict[int, str], buckets: dict[str, dict]
    ) -> tuple[str | None, str]:
        if demand.id in explicit:
            return explicit[demand.id], "EXPLICIT_DEMAND_CLASSIFICATION"
        candidates = {
            code
            for code, bucket in buckets.items()
            if set(demand.theme_codes_json or [])
            & {
                str(value).strip().lower()
                for value in bucket.get("applicable_theme_codes", bucket.get("theme_codes", []))
            }
        }
        if len(candidates) == 1:
            return next(iter(candidates)), "THEME_TO_BUCKET_DEFAULT"
        return None, "UNCLASSIFIED"

    def _project_context(self, plan: StrategicCapitalAllocationPlan, manual: dict, buckets: dict[str, dict]) -> dict:
        result = {"current": [], "recommended": [], "approved": [], "source_hashes": {}}
        if not plan.portfolio_workspace_id:
            return result
        memberships = list(
            self.db.scalars(
                select(PortfolioProjectMembership).where(
                    PortfolioProjectMembership.tenant_id == self.tenant_id,
                    PortfolioProjectMembership.portfolio_workspace_id == plan.portfolio_workspace_id,
                    PortfolioProjectMembership.status == "ACTIVE",
                )
            ).all()
        )
        project_ids = {item.project_workspace_id for item in memberships}
        requests = {
            item.materialized_workspace_id: item
            for item in self.db.scalars(
                select(ProjectCreationRequest).where(
                    ProjectCreationRequest.tenant_id == self.tenant_id,
                    ProjectCreationRequest.materialized_workspace_id.in_(project_ids or [-1]),
                )
            ).all()
            if item.materialized_workspace_id is not None
        }
        source_idea_ids = {item.source_idea_id for item in requests.values() if item.source_idea_id is not None}
        ideas = {
            item.id: item
            for item in self.db.scalars(
                select(Idea).where(Idea.tenant_id == self.tenant_id, Idea.id.in_(source_idea_ids or [-1]))
            ).all()
        }
        source_demand_ids = {item.source_capital_demand_id for item in ideas.values() if item.source_capital_demand_id}
        demands = {
            item.id: item
            for item in self.db.scalars(
                select(StrategicCapitalDemand).where(
                    StrategicCapitalDemand.tenant_id == self.tenant_id,
                    StrategicCapitalDemand.id.in_(source_demand_ids or [-1]),
                )
            ).all()
        }

        def resolve(project_id: int, membership_id: int | None = None) -> tuple[str | None, str]:
            if membership_id is not None and membership_id in manual["membership"]:
                return manual["membership"][membership_id], "EXPLICIT_PORTFOLIO_MEMBERSHIP_CLASSIFICATION"
            if project_id in manual["project"]:
                return manual["project"][project_id], "EXPLICIT_PROJECT_CLASSIFICATION"
            request = requests.get(project_id)
            idea = ideas.get(request.source_idea_id) if request and request.source_idea_id else None
            demand = demands.get(idea.source_capital_demand_id) if idea and idea.source_capital_demand_id else None
            if demand is not None:
                code, source = self._resolve_demand_bucket(demand, manual["demand"], buckets)
                if code:
                    return code, f"SOURCE_CAPITAL_DEMAND:{source}"
            return None, "UNCLASSIFIED"

        for membership in memberships:
            request = requests.get(membership.project_workspace_id)
            code, source = resolve(membership.project_workspace_id, membership.id)
            result["current"].append(
                {
                    "bucket_code": code,
                    "amount": request.estimated_budget if request else None,
                    "currency": request.currency_code if request else None,
                    "detail": {
                        "project_workspace_id": membership.project_workspace_id,
                        "portfolio_membership_id": membership.id,
                        "classification_source": source,
                    },
                }
            )
        convergence = self.db.scalar(
            select(PortfolioScenarioConvergence)
            .where(
                PortfolioScenarioConvergence.tenant_id == self.tenant_id,
                PortfolioScenarioConvergence.portfolio_workspace_id == plan.portfolio_workspace_id,
                PortfolioScenarioConvergence.status == "RECOMMENDED",
            )
            .order_by(PortfolioScenarioConvergence.recommended_at.desc(), PortfolioScenarioConvergence.id.desc())
            .limit(1)
        )
        if convergence is not None and convergence.recommended_alternative_id:
            alternative = self.db.scalar(
                select(PortfolioConvergedAlternative).where(
                    PortfolioConvergedAlternative.id == convergence.recommended_alternative_id,
                    PortfolioConvergedAlternative.tenant_id == self.tenant_id,
                )
            )
            if alternative and alternative.budget_scenario_id:
                rows = list(
                    self.db.scalars(
                        select(PortfolioBudgetScenarioProject).where(
                            PortfolioBudgetScenarioProject.tenant_id == self.tenant_id,
                            PortfolioBudgetScenarioProject.scenario_id == alternative.budget_scenario_id,
                            PortfolioBudgetScenarioProject.selection_state.in_(["SELECTED", "FORCED_IN"]),
                        )
                    ).all()
                )
                for item in rows:
                    code, source = resolve(item.project_workspace_id, item.portfolio_membership_id)
                    result["recommended"].append(
                        {
                            "bucket_code": code,
                            "amount": item.cost_value,
                            "currency": item.currency,
                            "detail": {
                                "project_workspace_id": item.project_workspace_id,
                                "budget_scenario_project_id": item.id,
                                "classification_source": source,
                            },
                        }
                    )
                result["source_hashes"]["recommended"] = convergence.recommendation_hash
        decisions = list(
            self.db.scalars(
                select(InvestmentDecision).where(
                    InvestmentDecision.tenant_id == self.tenant_id,
                    InvestmentDecision.portfolio_workspace_id == plan.portfolio_workspace_id,
                    InvestmentDecision.status == "DECIDED",
                    InvestmentDecision.outcome == "GO",
                    InvestmentDecision.profile_code == "PYP-FFA",
                    InvestmentDecision.is_fid.is_(True),
                    InvestmentDecision.full_funds_authorized.is_(True),
                    InvestmentDecision.investment_authorized.is_(True),
                )
            ).all()
        )
        for decision in decisions:
            preparation = self.db.get(InvestmentGatePreparation, decision.investment_gate_preparation_id)
            alternative = (
                self.db.get(PortfolioConvergedAlternative, preparation.recommended_alternative_id)
                if preparation
                else None
            )
            selected_rows = (
                list(
                    self.db.scalars(
                        select(PortfolioBudgetScenarioProject).where(
                            PortfolioBudgetScenarioProject.tenant_id == self.tenant_id,
                            PortfolioBudgetScenarioProject.scenario_id == alternative.budget_scenario_id,
                            PortfolioBudgetScenarioProject.selection_state.in_(["SELECTED", "FORCED_IN"]),
                        )
                    ).all()
                )
                if alternative and alternative.budget_scenario_id
                else []
            )
            total_cost = sum((item.cost_value for item in selected_rows), Decimal("0"))
            for item in selected_rows:
                code, source = resolve(item.project_workspace_id, item.portfolio_membership_id)
                amount = None
                if decision.authorized_amount is not None and total_cost > 0:
                    amount = (decision.authorized_amount * item.cost_value / total_cost).quantize(Decimal("0.01"))
                result["approved"].append(
                    {
                        "bucket_code": code,
                        "amount": amount,
                        "currency": decision.authorized_currency,
                        "detail": {
                            "project_workspace_id": item.project_workspace_id,
                            "investment_decision_id": decision.id,
                            "profile_code": decision.profile_code,
                            "classification_source": source,
                        },
                    }
                )
            if not selected_rows:
                result["approved"].append(
                    {
                        "bucket_code": None,
                        "amount": decision.authorized_amount,
                        "currency": decision.authorized_currency,
                        "detail": {
                            "investment_decision_id": decision.id,
                            "profile_code": decision.profile_code,
                            "classification_source": "UNCLASSIFIED",
                        },
                    }
                )
        result["source_hashes"]["approved"] = sorted(item.decision_hash for item in decisions if item.decision_hash)
        result["source_hashes"]["current_memberships"] = sorted(item.id for item in memberships)
        return result

    @staticmethod
    def _empty_position() -> dict:
        return {"amount_by_currency": defaultdict(Decimal), "item_count": 0, "drilldown": []}

    @staticmethod
    def _accumulate_position(position: dict, amount: Decimal | None, currency: str | None, detail: dict) -> None:
        position["item_count"] += 1
        position["drilldown"].append(detail)
        if amount is not None and currency:
            position["amount_by_currency"][currency] += Decimal(amount)

    @staticmethod
    def _position_totals(positions: dict, unclassified: dict, kind: str) -> dict[str, Decimal]:
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for values in [*(bucket[kind] for bucket in positions.values()), unclassified[kind]]:
            for currency, amount in values["amount_by_currency"].items():
                totals[currency] += amount
        return dict(totals)

    @staticmethod
    def _position_out(position: dict, totals: dict[str, Decimal], *, source: str) -> AllocationPositionOut:
        amounts = dict(position["amount_by_currency"])
        percentage = None
        if len(totals) == 1:
            currency, total = next(iter(totals.items()))
            if total > 0:
                percentage = (amounts.get(currency, Decimal("0")) * Decimal("100") / total).quantize(Decimal("0.0001"))
        return AllocationPositionOut(
            amount_by_currency=amounts,
            percentage=percentage,
            item_count=position["item_count"],
            evaluable=len(totals) <= 1,
            source=source,
            drilldown=deepcopy(position["drilldown"]),
        )

    @staticmethod
    def _single_currency_amount(amounts: dict[str, Decimal], currency: str | None) -> Decimal | None:
        if not amounts:
            return Decimal("0")
        if len(amounts) != 1:
            return None
        if currency and currency not in amounts:
            return None
        return next(iter(amounts.values()))

    @staticmethod
    def _allocation_status(
        line: StrategicCapitalAllocationLine | None, position: AllocationPositionOut, policy: dict
    ) -> str:
        if line is None or not position.evaluable:
            return "NOT_EVALUABLE"
        value = position.percentage
        if value is None:
            return "NOT_EVALUABLE"
        minimum = line.minimum_percentage
        maximum = line.maximum_percentage
        tolerance = Decimal(str(policy.get("percentage_tolerance", "0.0001")))
        if minimum is not None and value < minimum - tolerance:
            return "UNDER_TARGET"
        if maximum is not None and value > maximum + tolerance:
            return "OVER_TARGET"
        if minimum is None and maximum is None and line.target_percentage is not None:
            if value < line.target_percentage - tolerance:
                return "UNDER_TARGET"
            if value > line.target_percentage + tolerance:
                return "OVER_TARGET"
        return "WITHIN_RANGE"

    def _descendant_workspace_ids(self, root_id: int) -> list[int]:
        ids = {root_id}
        frontier = {root_id}
        while frontier:
            children = set(
                self.db.scalars(
                    select(EnterpriseWorkspace.id).where(
                        EnterpriseWorkspace.tenant_id == self.tenant_id,
                        EnterpriseWorkspace.parent_id.in_(frontier),
                    )
                ).all()
            )
            children -= ids
            if not children:
                break
            ids.update(children)
            frontier = children
        return sorted(ids)

    def _validate_demand(self, payload: DemandCreate | DemandUpdate, cycle: CapitalPlanningCycle, config: dict) -> None:
        if cycle.status not in {"OPEN", "IN_REVIEW"}:
            raise HTTPException(status_code=409, detail={"code": "PLANNING_CYCLE_NOT_OPEN", "status": cycle.status})
        self._validate_theme_codes(payload.theme_codes, config)
        if cycle.applicable_theme_codes_json and not set(payload.theme_codes).issubset(
            set(cycle.applicable_theme_codes_json)
        ):
            raise HTTPException(status_code=422, detail={"code": "THEME_NOT_APPLICABLE_TO_CYCLE"})
        valid_objectives = {
            str(code).strip().lower()
            for code in self.db.scalars(
                select(EnterpriseStrategicObjective.code).where(
                    EnterpriseStrategicObjective.tenant_id == self.tenant_id,
                    EnterpriseStrategicObjective.active.is_(True),
                )
            ).all()
        }
        if set(payload.strategic_objective_codes) - valid_objectives:
            raise HTTPException(status_code=422, detail={"code": "UNKNOWN_STRATEGIC_OBJECTIVE"})
        themes = {str(item.get("code", "")).strip().lower(): item for item in config.get("themes", [])}
        linked_objectives = {
            str(code).strip().lower()
            for theme_code in payload.theme_codes
            for code in themes.get(theme_code, {}).get("strategic_objective_codes", [])
        }
        if linked_objectives and not set(payload.strategic_objective_codes).issubset(linked_objectives):
            raise HTTPException(status_code=422, detail={"code": "OBJECTIVE_NOT_LINKED_TO_THEME"})
        self._validate_catalog_value(payload.strategic_driver, config.get("drivers", []), "UNKNOWN_DEMAND_DRIVER")
        self._validate_catalog_value(payload.demand_category, config.get("categories", []), "UNKNOWN_DEMAND_CATEGORY")
        self._validate_catalog_value(payload.target_horizon, config.get("planning_horizons", []), "UNKNOWN_HORIZON")
        self._validate_catalog_value(payload.urgency, config.get("urgency_levels", []), "UNKNOWN_URGENCY")
        self._validate_catalog_value(
            payload.uncertainty_level, config.get("uncertainty_levels", []), "UNKNOWN_UNCERTAINTY"
        )
        sponsor = self.db.scalar(
            select(UserAccount).where(
                UserAccount.id == payload.sponsor_user_id,
                UserAccount.tenant_id == self.tenant_id,
                UserAccount.status == "active",
            )
        )
        if sponsor is None:
            raise HTTPException(status_code=422, detail={"code": "SPONSOR_NOT_ACTIVE"})
        if payload.potential_portfolio_id:
            portfolio = self._workspace(payload.potential_portfolio_id)
            if portfolio.workspace_type_code != "portfolio":
                raise HTTPException(status_code=422, detail={"code": "POTENTIAL_PORTFOLIO_REQUIRED"})

    @staticmethod
    def _validate_catalog_value(value: str | None, items: list[dict], code: str) -> None:
        if not value or not items:
            return
        valid = {str(item.get("code", "")).strip().lower() for item in items}
        if value.strip().lower() not in valid:
            raise HTTPException(status_code=422, detail={"code": code})

    @staticmethod
    def _validate_theme_codes(codes: list[str], config: dict) -> None:
        configured = {str(item.get("code", "")).strip().lower() for item in config.get("themes", [])}
        if set(codes) - configured:
            raise HTTPException(status_code=422, detail={"code": "UNKNOWN_STRATEGIC_INVESTMENT_THEME"})

    @staticmethod
    def _validate_lifecycle_rules(
        lifecycle: dict,
        aggregate: str,
        canonical: dict[str, tuple[set[str], str]],
        valid_states: frozenset[str],
    ) -> None:
        rules = lifecycle.get(aggregate)
        if not isinstance(rules, dict) or set(rules) != set(canonical):
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_LIFECYCLE_ACTIONS", "aggregate": aggregate},
            )
        for action, (canonical_sources, canonical_target) in canonical.items():
            rule = rules[action]
            if not isinstance(rule, dict) or not isinstance(rule.get("enabled"), bool):
                raise HTTPException(
                    status_code=422,
                    detail={"code": "INVALID_LIFECYCLE_RULE", "aggregate": aggregate, "action": action},
                )
            sources = rule.get("from")
            target = rule.get("to")
            if (
                not isinstance(sources, list)
                or not sources
                or any(not isinstance(item, str) for item in sources)
                or not set(sources) <= valid_states
                or not set(sources) <= canonical_sources
                or target != canonical_target
            ):
                raise HTTPException(
                    status_code=422,
                    detail={"code": "UNSAFE_LIFECYCLE_RULE", "aggregate": aggregate, "action": action},
                )

    @staticmethod
    def _lifecycle_transition(config: dict, aggregate: str, action: str) -> tuple[set[str], str]:
        rules = dict(dict(config.get("lifecycle_rules") or {}).get(aggregate) or {})
        rule = dict(rules.get(action) or {})
        if not rule.get("enabled", False):
            raise HTTPException(
                status_code=409,
                detail={"code": "LIFECYCLE_ACTION_DISABLED", "aggregate": aggregate, "action": action},
            )
        return {str(item) for item in rule.get("from", [])}, str(rule.get("to") or "")

    @staticmethod
    def _field_present(value: object) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, dict)):
            return bool(value)
        # Numeric zero is a valid explicit indicative capital value.
        return True

    def _validate_configuration(self, content: dict, *, code: str | None = None) -> None:
        required_lists = (
            "themes",
            "drivers",
            "categories",
            "planning_horizons",
            "urgency_levels",
            "uncertainty_levels",
            "required_fields",
            "project_type_applicability",
            "strategic_capital_buckets",
            "allocation_basis_options",
        )
        if any(not isinstance(content.get(key), list) for key in required_lists):
            raise HTTPException(status_code=422, detail={"code": "INVALID_CAPITAL_PLANNING_CONFIGURATION"})
        for key in required_lists[:6]:
            codes = [str(item.get("code", "")).strip().lower() for item in content[key]]
            if any(not code for code in codes) or len(codes) != len(set(codes)):
                raise HTTPException(status_code=422, detail={"code": "DUPLICATE_OR_EMPTY_CATALOG_CODE", "catalog": key})
        required_fields = content["required_fields"]
        if any(not isinstance(field, str) or not field.strip() for field in required_fields):
            raise HTTPException(status_code=422, detail={"code": "INVALID_REQUIRED_FIELD"})
        normalized_fields = [field.strip() for field in required_fields]
        invalid_fields = sorted(set(normalized_fields) - SUPPORTED_DEMAND_REQUIRED_FIELDS)
        if invalid_fields:
            raise HTTPException(
                status_code=422,
                detail={"code": "UNSUPPORTED_REQUIRED_FIELD", "fields": invalid_fields},
            )
        if len(normalized_fields) != len(set(normalized_fields)):
            raise HTTPException(status_code=422, detail={"code": "DUPLICATE_REQUIRED_FIELD"})

        project_types = content["project_type_applicability"]
        if not project_types or any(not isinstance(item, str) or not item.strip() for item in project_types):
            raise HTTPException(status_code=422, detail={"code": "INVALID_PROJECT_TYPE_APPLICABILITY"})
        normalized_project_types = [str(item).strip().upper() for item in project_types]
        if "*" in normalized_project_types and len(normalized_project_types) != 1:
            raise HTTPException(status_code=422, detail={"code": "WILDCARD_PROJECT_TYPE_MUST_BE_EXCLUSIVE"})
        if len(normalized_project_types) != len(set(normalized_project_types)):
            raise HTTPException(status_code=422, detail={"code": "DUPLICATE_PROJECT_TYPE_APPLICABILITY"})

        basis_options = content["allocation_basis_options"]
        allowed_basis = {"PERCENTAGE", "INDICATIVE_AMOUNT", "PERCENTAGE_AND_AMOUNT"}
        if (
            not basis_options
            or any(not isinstance(item, str) for item in basis_options)
            or not set(basis_options) <= allowed_basis
            or len(basis_options) != len(set(basis_options))
        ):
            raise HTTPException(status_code=422, detail={"code": "INVALID_ALLOCATION_BASIS_OPTIONS"})

        buckets = content["strategic_capital_buckets"]
        bucket_codes = [str(item.get("code", "")).strip().lower() for item in buckets if isinstance(item, dict)]
        if (
            len(bucket_codes) != len(buckets)
            or any(not code for code in bucket_codes)
            or len(bucket_codes) != len(set(bucket_codes))
        ):
            raise HTTPException(status_code=422, detail={"code": "DUPLICATE_OR_EMPTY_BUCKET_CODE"})
        for bucket in buckets:
            if not str(bucket.get("name") or bucket.get("label") or "").strip():
                raise HTTPException(
                    status_code=422, detail={"code": "BUCKET_NAME_REQUIRED", "bucket": bucket.get("code")}
                )
            if "active" in bucket and not isinstance(bucket["active"], bool):
                raise HTTPException(
                    status_code=422, detail={"code": "INVALID_BUCKET_ACTIVE", "bucket": bucket.get("code")}
                )
            for collection in (
                "applicable_theme_codes",
                "theme_codes",
                "strategic_objective_codes",
                "governance_models",
                "project_types",
            ):
                if collection in bucket and not isinstance(bucket[collection], list):
                    raise HTTPException(
                        status_code=422,
                        detail={"code": "INVALID_BUCKET_MAPPING", "bucket": bucket.get("code"), "mapping": collection},
                    )

        allocation_policy = content.get("allocation_policy")
        if not isinstance(allocation_policy, dict):
            raise HTTPException(status_code=422, detail={"code": "INVALID_ALLOCATION_POLICY"})
        scope_types = allocation_policy.get("scope_types")
        if not isinstance(scope_types, list) or not scope_types or not set(scope_types) <= OWNING_WORKSPACE_TYPES:
            raise HTTPException(status_code=422, detail={"code": "INVALID_ALLOCATION_SCOPE_TYPES"})
        statuses = allocation_policy.get("eligible_demand_statuses")
        if not isinstance(statuses, list) or not statuses or not set(statuses) <= DEMAND_STATES:
            raise HTTPException(status_code=422, detail={"code": "INVALID_ELIGIBLE_DEMAND_STATUSES"})
        modes = allocation_policy.get("classification_modes")
        if not isinstance(modes, list) or not modes or not set(modes) <= {"MANUAL", "THEME_DERIVED", "RULE_DERIVED"}:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CLASSIFICATION_MODES"})
        try:
            percentage_total = Decimal(str(allocation_policy.get("percentage_total_required", "100")))
            percentage_tolerance = Decimal(str(allocation_policy.get("percentage_tolerance", "0")))
            unclassified_max = Decimal(str(allocation_policy.get("unclassified_max_percentage", "0")))
        except Exception as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_ALLOCATION_TOLERANCE"}) from exc
        if not Decimal("0") <= percentage_total <= Decimal("100") or percentage_tolerance < 0:
            raise HTTPException(status_code=422, detail={"code": "INVALID_ALLOCATION_PERCENTAGE_POLICY"})
        if not Decimal("0") <= unclassified_max <= Decimal("100"):
            raise HTTPException(status_code=422, detail={"code": "INVALID_UNCLASSIFIED_POLICY"})
        for key in (
            "allow_unallocated_reserve",
            "block_endorsement_when_unclassified_exceeds_tolerance",
            "closed_cycle_allows_new_plan",
        ):
            if not isinstance(allocation_policy.get(key), bool):
                raise HTTPException(status_code=422, detail={"code": "INVALID_ALLOCATION_POLICY_FLAG", "field": key})

        numbering = content.get("numbering")
        if not isinstance(numbering, dict):
            raise HTTPException(status_code=422, detail={"code": "INVALID_NUMBERING_POLICY"})
        separator = numbering.get("separator", "-")
        if separator not in {"", "-", "/", "_"}:
            raise HTTPException(status_code=422, detail={"code": "INVALID_NUMBERING_SEPARATOR"})
        for entity in ("cycle", "demand", "allocation_plan"):
            # ``allocation_plan`` was introduced additively in Wave 2A.  A
            # valid Wave 1 administrator payload may replace the complete
            # numbering object and therefore omit only these new keys.  Keep
            # that historical contract valid; effective configuration
            # normalization supplies the governed Wave 2A defaults at use.
            prefix = numbering.get(f"{entity}_prefix")
            padding = numbering.get(f"{entity}_padding")
            if entity == "allocation_plan":
                prefix = prefix or DEFAULT_CONFIGURATION["numbering"]["allocation_plan_prefix"]
                padding = (
                    padding if padding is not None else DEFAULT_CONFIGURATION["numbering"]["allocation_plan_padding"]
                )
            if not isinstance(prefix, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,11}", prefix.strip()) is None:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "INVALID_NUMBERING_PREFIX", "entity": entity},
                )
            if not isinstance(padding, int) or isinstance(padding, bool) or padding < 2 or padding > 12:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "INVALID_NUMBERING_PADDING", "entity": entity},
                )

        lifecycle = content.get("lifecycle_rules")
        if not isinstance(lifecycle, dict):
            raise HTTPException(status_code=422, detail={"code": "INVALID_LIFECYCLE_RULES"})
        self._validate_lifecycle_rules(lifecycle, "planning_cycle", CYCLE_LIFECYCLE, CYCLE_STATES)
        self._validate_lifecycle_rules(lifecycle, "capital_demand", DEMAND_LIFECYCLE, DEMAND_STATES)
        self._validate_lifecycle_rules(
            lifecycle,
            "allocation_plan",
            ALLOCATION_PLAN_LIFECYCLE,
            ALLOCATION_PLAN_STATES,
        )

        inheritance = content.get("inheritance")
        if not isinstance(inheritance, dict) or not isinstance(inheritance.get("inherit_to_descendants"), bool):
            raise HTTPException(status_code=422, detail={"code": "INVALID_INHERITANCE_POLICY"})
        workspace_types = inheritance.get("supported_workspace_types")
        if not isinstance(workspace_types, list) or set(workspace_types) != OWNING_WORKSPACE_TYPES:
            raise HTTPException(status_code=422, detail={"code": "INVALID_INHERITANCE_WORKSPACE_TYPES"})
        if not isinstance(content.get("inherit_to_descendants"), bool):
            raise HTTPException(status_code=422, detail={"code": "INVALID_INHERITANCE_POLICY"})
        if content["inherit_to_descendants"] != inheritance["inherit_to_descendants"]:
            raise HTTPException(status_code=422, detail={"code": "INHERITANCE_POLICY_MISMATCH"})
        workspace_id = content.get("workspace_id")
        if code == "default" and workspace_id is not None:
            raise HTTPException(status_code=422, detail={"code": "DEFAULT_CONFIGURATION_CANNOT_TARGET_WORKSPACE"})
        if code and code.startswith("workspace-"):
            expected_workspace_id = (
                int(code.removeprefix("workspace-")) if code.removeprefix("workspace-").isdigit() else None
            )
            if expected_workspace_id is None or workspace_id != expected_workspace_id:
                raise HTTPException(status_code=422, detail={"code": "WORKSPACE_CONFIGURATION_TARGET_MISMATCH"})
            workspace = self.db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.id == workspace_id,
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.workspace_type_code.in_(OWNING_WORKSPACE_TYPES),
                )
            )
            if workspace is None:
                raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION_WORKSPACE"})

        valid_objectives = {
            str(code).strip().lower()
            for code in self.db.scalars(
                select(EnterpriseStrategicObjective.code).where(
                    EnterpriseStrategicObjective.tenant_id == self.tenant_id,
                    EnterpriseStrategicObjective.active.is_(True),
                )
            ).all()
        }
        referenced = {
            str(code).strip().lower()
            for theme in content.get("themes", [])
            for code in theme.get("strategic_objective_codes", [])
        }
        if referenced - valid_objectives:
            raise HTTPException(status_code=422, detail={"code": "THEME_REFERENCES_UNKNOWN_OBJECTIVE"})
        configured_themes = {str(item.get("code", "")).strip().lower() for item in content.get("themes", [])}
        bucket_themes = {
            str(value).strip().lower()
            for bucket in buckets
            for value in bucket.get("applicable_theme_codes", bucket.get("theme_codes", []))
        }
        if bucket_themes - configured_themes:
            raise HTTPException(status_code=422, detail={"code": "BUCKET_REFERENCES_UNKNOWN_THEME"})
        bucket_objectives = {
            str(value).strip().lower() for bucket in buckets for value in bucket.get("strategic_objective_codes", [])
        }
        if bucket_objectives - valid_objectives:
            raise HTTPException(status_code=422, detail={"code": "BUCKET_REFERENCES_UNKNOWN_OBJECTIVE"})

    def _readiness(self, demand: StrategicCapitalDemand) -> dict:
        config = self._normalized_configuration(demand.configuration_snapshot_json.get("effective") or {})
        values = {
            "name": demand.name,
            "description": demand.description,
            "planning_cycle_id": demand.planning_cycle_id,
            "business_or_asset_need": demand.business_or_asset_need,
            "strategic_driver": demand.strategic_driver,
            "demand_category": demand.demand_category,
            "urgency": demand.urgency,
            "target_horizon": demand.target_horizon,
            "sponsor_user_id": demand.sponsor_user_id,
            "owning_workspace_id": demand.owning_workspace_id,
            "theme_codes": demand.theme_codes_json,
            "strategic_objective_codes": demand.strategic_objective_codes_json,
            "location_context": demand.location_context,
            "indicative_capital_need": demand.indicative_capital_need,
            "currency_code": demand.currency_code,
            "indicative_capital_range_low": demand.indicative_capital_range_low,
            "indicative_capital_range_high": demand.indicative_capital_range_high,
            "uncertainty_level": demand.uncertainty_level,
            "potential_portfolio_id": demand.potential_portfolio_id,
            "assumptions": demand.assumptions_json,
            "constraints": demand.constraints_json,
            "dependencies": demand.dependencies_json,
        }
        missing = [field for field in config.get("required_fields", []) if not self._field_present(values.get(field))]
        dimensions = {
            "STRATEGIC_ALIGNMENT": bool(demand.theme_codes_json or demand.strategic_objective_codes_json),
            "NEED_DEFINITION": bool(demand.business_or_asset_need.strip()),
            "SPONSOR": bool(demand.sponsor_user_id),
            "HORIZON": bool(demand.target_horizon),
            "INDICATIVE_CAPITAL": (demand.indicative_capital_need is None or bool(demand.currency_code)),
            "TRACEABILITY": bool(demand.planning_cycle_id and demand.owning_workspace_id),
        }
        blocking = [f"REQUIRED_FIELD:{field}" for field in missing]
        return {
            "status": "READY" if not blocking else "BLOCKED",
            "dimensions": dimensions,
            "blocking_issues": blocking,
            "semantics": "DEMAND_READINESS_NOT_GATE07J_EVIDENCE",
        }

    def _demand_snapshot(self, demand: StrategicCapitalDemand) -> dict:
        return {
            "demand_id": demand.id,
            "demand_number": demand.demand_number,
            "revision_version": demand.revision_version,
            "status": demand.status,
            "name": demand.name,
            "description": demand.description,
            "planning_cycle_id": demand.planning_cycle_id,
            "theme_codes": list(demand.theme_codes_json or []),
            "strategic_objective_codes": list(demand.strategic_objective_codes_json or []),
            "business_or_asset_need": demand.business_or_asset_need,
            "strategic_driver": demand.strategic_driver,
            "demand_category": demand.demand_category,
            "urgency": demand.urgency,
            "target_horizon": demand.target_horizon,
            "sponsor_user_id": demand.sponsor_user_id,
            "owning_workspace_id": demand.owning_workspace_id,
            "location_context": demand.location_context,
            "indicative_capital_need": str(demand.indicative_capital_need)
            if demand.indicative_capital_need is not None
            else None,
            "currency_code": demand.currency_code,
            "indicative_capital_range_low": str(demand.indicative_capital_range_low)
            if demand.indicative_capital_range_low is not None
            else None,
            "indicative_capital_range_high": str(demand.indicative_capital_range_high)
            if demand.indicative_capital_range_high is not None
            else None,
            "uncertainty_level": demand.uncertainty_level,
            "potential_portfolio_id": demand.potential_portfolio_id,
            "assumptions": list(demand.assumptions_json or []),
            "constraints": list(demand.constraints_json or []),
            "dependencies": list(demand.dependencies_json or []),
            "configuration_hash": demand.configuration_hash,
            "indicative_capital_semantics": "INDICATIVE_CAPITAL_NEED",
        }

    @staticmethod
    def _cycle_values(payload: CycleCreate | CycleUpdate) -> dict:
        return {
            "name": payload.name,
            "planning_horizon_start": payload.planning_horizon_start,
            "planning_horizon_end": payload.planning_horizon_end,
            "scope_workspace_id": payload.scope_workspace_id,
            "responsible_organization_workspace_id": payload.responsible_organization_workspace_id,
            "applicable_theme_codes_json": payload.applicable_theme_codes,
            "capital_basis_currency": payload.capital_basis_currency,
            "description": payload.description,
        }

    @staticmethod
    def _demand_values(payload: DemandCreate | DemandUpdate) -> dict:
        return {
            "name": payload.name,
            "description": payload.description,
            "planning_cycle_id": payload.planning_cycle_id,
            "theme_codes_json": payload.theme_codes,
            "strategic_objective_codes_json": payload.strategic_objective_codes,
            "business_or_asset_need": payload.business_or_asset_need,
            "strategic_driver": payload.strategic_driver.strip().lower(),
            "demand_category": payload.demand_category.strip().lower() if payload.demand_category else None,
            "urgency": payload.urgency.strip().lower() if payload.urgency else None,
            "target_horizon": payload.target_horizon.strip().lower(),
            "sponsor_user_id": payload.sponsor_user_id,
            "owning_workspace_id": payload.owning_workspace_id,
            "location_context": payload.location_context.strip() if payload.location_context else None,
            "indicative_capital_need": payload.indicative_capital_need,
            "currency_code": payload.currency_code,
            "indicative_capital_range_low": payload.indicative_capital_range_low,
            "indicative_capital_range_high": payload.indicative_capital_range_high,
            "uncertainty_level": payload.uncertainty_level.strip().lower() if payload.uncertainty_level else None,
            "potential_portfolio_id": payload.potential_portfolio_id,
            "assumptions_json": payload.assumptions,
            "constraints_json": payload.constraints,
            "dependencies_json": payload.dependencies,
        }

    @staticmethod
    def _status_values(raw: str, allowed: frozenset[str]) -> list[str]:
        values = sorted({item.strip().upper() for item in raw.split(",") if item.strip()})
        invalid = sorted(set(values) - allowed)
        if invalid:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_STATUS_FILTER", "invalid": invalid},
            )
        return values

    def _filtered_demands_statement(
        self,
        *,
        status: str = "",
        planning_cycle_id: int | None = None,
        theme_code: str = "",
        strategic_objective_code: str = "",
        driver: str = "",
        sponsor_user_id: int | None = None,
        owning_workspace_id: int | None = None,
        urgency: str = "",
        target_horizon: str = "",
        potential_portfolio_id: int | None = None,
        uncertainty_level: str = "",
        search: str = "",
        mine: bool = False,
    ):
        statement = self._demand_scope(
            select(StrategicCapitalDemand).where(StrategicCapitalDemand.tenant_id == self.tenant_id)
        )
        statuses = self._status_values(status, DEMAND_STATES)
        if statuses:
            statement = statement.where(StrategicCapitalDemand.status.in_(statuses))
        if mine:
            statement = statement.where(StrategicCapitalDemand.created_by_user_id == self.actor_id)
        if planning_cycle_id:
            statement = statement.where(StrategicCapitalDemand.planning_cycle_id == planning_cycle_id)
        if driver.strip():
            statement = statement.where(StrategicCapitalDemand.strategic_driver == driver.strip().lower())
        if sponsor_user_id:
            statement = statement.where(StrategicCapitalDemand.sponsor_user_id == sponsor_user_id)
        if owning_workspace_id:
            statement = statement.where(StrategicCapitalDemand.owning_workspace_id == owning_workspace_id)
        if urgency.strip():
            statement = statement.where(StrategicCapitalDemand.urgency == urgency.strip().lower())
        if target_horizon.strip():
            statement = statement.where(StrategicCapitalDemand.target_horizon == target_horizon.strip().lower())
        if potential_portfolio_id:
            statement = statement.where(StrategicCapitalDemand.potential_portfolio_id == potential_portfolio_id)
        if uncertainty_level.strip():
            statement = statement.where(StrategicCapitalDemand.uncertainty_level == uncertainty_level.strip().lower())
        if search.strip():
            term = f"%{search.strip().lower()}%"
            statement = statement.where(
                func.lower(StrategicCapitalDemand.demand_number).like(term)
                | func.lower(StrategicCapitalDemand.name).like(term)
            )
        if theme_code.strip():
            theme = theme_code.strip().lower()
            statement = statement.where(
                StrategicCapitalDemand.id.in_(
                    select(StrategicCapitalDemandTheme.capital_demand_id).where(
                        StrategicCapitalDemandTheme.tenant_id == self.tenant_id,
                        StrategicCapitalDemandTheme.theme_code == theme,
                    )
                )
            )
        if strategic_objective_code.strip():
            objective = strategic_objective_code.strip().lower()
            statement = statement.where(
                StrategicCapitalDemand.id.in_(
                    select(StrategicCapitalDemandObjective.capital_demand_id).where(
                        StrategicCapitalDemandObjective.tenant_id == self.tenant_id,
                        StrategicCapitalDemandObjective.objective_code == objective,
                    )
                )
            )
        return statement

    def _cycle(self, cycle_id: int) -> CapitalPlanningCycle:
        record = self.db.scalar(
            self._cycle_scope(
                select(CapitalPlanningCycle).where(
                    CapitalPlanningCycle.id == cycle_id,
                    CapitalPlanningCycle.tenant_id == self.tenant_id,
                )
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "CAPITAL_PLANNING_CYCLE_NOT_FOUND"})
        return record

    def _cycle_for_update(self, cycle_id: int) -> CapitalPlanningCycle:
        record = self.db.scalar(
            self._cycle_scope(
                select(CapitalPlanningCycle)
                .where(
                    CapitalPlanningCycle.id == cycle_id,
                    CapitalPlanningCycle.tenant_id == self.tenant_id,
                )
                .with_for_update()
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "CAPITAL_PLANNING_CYCLE_NOT_FOUND"})
        return record

    def _demand(self, demand_id: int) -> StrategicCapitalDemand:
        record = self.db.scalar(
            self._demand_scope(
                select(StrategicCapitalDemand).where(
                    StrategicCapitalDemand.id == demand_id,
                    StrategicCapitalDemand.tenant_id == self.tenant_id,
                )
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "STRATEGIC_CAPITAL_DEMAND_NOT_FOUND"})
        return record

    def _demand_for_update(self, demand_id: int) -> StrategicCapitalDemand:
        record = self.db.scalar(
            self._demand_scope(
                select(StrategicCapitalDemand)
                .where(
                    StrategicCapitalDemand.id == demand_id,
                    StrategicCapitalDemand.tenant_id == self.tenant_id,
                )
                .with_for_update()
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "STRATEGIC_CAPITAL_DEMAND_NOT_FOUND"})
        return record

    def _cycle_scope(self, statement):
        if self.context.organization_wide:
            return statement
        allowed = list(self.context.workspace_ids)
        return statement.where(
            (CapitalPlanningCycle.created_by_user_id == self.actor_id)
            | (CapitalPlanningCycle.scope_workspace_id.in_(allowed) if allowed else False)
        )

    def _demand_scope(self, statement):
        if self.context.organization_wide:
            return statement
        allowed = list(self.context.workspace_ids)
        return statement.where(
            (StrategicCapitalDemand.created_by_user_id == self.actor_id)
            | (StrategicCapitalDemand.sponsor_user_id == self.actor_id)
            | (StrategicCapitalDemand.owning_workspace_id.in_(allowed) if allowed else False)
        )

    def _workspace(self, workspace_id: int | None) -> EnterpriseWorkspace:
        if workspace_id is None:
            raise HTTPException(status_code=404, detail={"code": "WORKSPACE_NOT_FOUND"})
        record = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == workspace_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.status.in_(["active", "draft"]),
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "WORKSPACE_NOT_FOUND"})
        if not self.context.organization_wide and record.id not in self.context.workspace_ids:
            raise HTTPException(status_code=404, detail={"code": "WORKSPACE_NOT_FOUND"})
        return record

    @staticmethod
    def _assert_owning_workspace(workspace: EnterpriseWorkspace) -> None:
        if workspace.workspace_type_code not in OWNING_WORKSPACE_TYPES:
            raise HTTPException(status_code=422, detail={"code": "UPSTREAM_WORKSPACE_REQUIRED"})

    def _authorized_workspaces(self) -> list[EnterpriseWorkspace]:
        statement = select(EnterpriseWorkspace).where(
            EnterpriseWorkspace.tenant_id == self.tenant_id,
            EnterpriseWorkspace.workspace_type_code.in_(OWNING_WORKSPACE_TYPES),
            EnterpriseWorkspace.status.in_(["active", "draft"]),
        )
        if not self.context.organization_wide:
            statement = statement.where(EnterpriseWorkspace.id.in_(list(self.context.workspace_ids)))
        return list(self.db.scalars(statement.order_by(EnterpriseWorkspace.sort_order, EnterpriseWorkspace.name)).all())

    @staticmethod
    def _workspace_option(record: EnterpriseWorkspace) -> dict:
        return {"id": record.id, "code": record.code, "name": record.name, "type": record.workspace_type_code}

    def _effective_configuration(
        self, workspace: EnterpriseWorkspace | None
    ) -> tuple[dict, dict, list[EnterpriseWorkspace]]:
        default = self._latest_configuration("default")
        if default is None:
            raise HTTPException(status_code=409, detail={"code": "NO_PUBLISHED_CAPITAL_PLANNING_CONFIGURATION"})
        path = self._workspace_path(workspace)
        selected = default
        for item in path:
            candidate = self._latest_configuration(f"workspace-{item.id}")
            if candidate and (
                item.id == getattr(workspace, "id", None) or self._inherits_to_descendants(candidate.content_json)
            ):
                selected = candidate
        source = {
            "configuration_id": selected.id,
            "code": selected.code,
            "revision": selected.revision,
            "workspace_id": selected.content_json.get("workspace_id"),
            "content_hash": selected.content_hash,
        }
        return self._normalized_configuration(selected.content_json), source, path

    def _workspace_path(self, workspace: EnterpriseWorkspace | None) -> list[EnterpriseWorkspace]:
        path: list[EnterpriseWorkspace] = []
        seen: set[int] = set()
        cursor = workspace
        while cursor is not None and cursor.id not in seen:
            seen.add(cursor.id)
            path.append(cursor)
            cursor = self.db.get(EnterpriseWorkspace, cursor.parent_id) if cursor.parent_id else None
        return list(reversed(path))

    def _latest_configuration(self, code: str) -> AdminConfiguration | None:
        return self.db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIG_KIND,
                AdminConfiguration.code == code,
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
            .limit(1)
        )

    def _configuration(self, configuration_id: int) -> AdminConfiguration:
        record = self.db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.id == configuration_id,
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIG_KIND,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "CAPITAL_PLANNING_CONFIGURATION_NOT_FOUND"})
        return record

    @staticmethod
    def _normalized_configuration(content: dict) -> dict:
        """Add new governed defaults without rewriting historical published revisions."""

        normalized = deepcopy(DEFAULT_CONFIGURATION)
        supplied = deepcopy(content or {})
        for key, value in supplied.items():
            if key in {
                "numbering",
                "inheritance",
                "separation_of_duties",
                "governance_model_applicability",
                "allocation_policy",
            }:
                normalized[key] = {**dict(normalized.get(key) or {}), **dict(value or {})}
            elif key == "lifecycle_rules":
                lifecycle = deepcopy(normalized["lifecycle_rules"])
                for aggregate, rules in dict(value or {}).items():
                    if aggregate not in lifecycle or not isinstance(rules, dict):
                        lifecycle[aggregate] = deepcopy(rules)
                        continue
                    for action, rule in rules.items():
                        lifecycle[aggregate][action] = {
                            **dict(lifecycle[aggregate].get(action) or {}),
                            **dict(rule or {}),
                        }
                normalized[key] = lifecycle
            else:
                normalized[key] = value
        # Preserve the legacy top-level switch while making the structured
        # inheritance contract authoritative for all new revisions.
        if "inheritance" not in supplied and "inherit_to_descendants" in supplied:
            normalized["inheritance"]["inherit_to_descendants"] = bool(supplied["inherit_to_descendants"])
        if "inherit_to_descendants" not in supplied and "inheritance" in supplied:
            normalized["inherit_to_descendants"] = bool(normalized["inheritance"]["inherit_to_descendants"])
        return normalized

    @staticmethod
    def _inherits_to_descendants(content: dict) -> bool:
        inheritance = content.get("inheritance")
        if isinstance(inheritance, dict) and isinstance(inheritance.get("inherit_to_descendants"), bool):
            return inheritance["inherit_to_descendants"]
        return bool(content.get("inherit_to_descendants", True))

    @staticmethod
    def _numbering_settings(content: dict, entity: str) -> dict:
        normalized = CapitalPlanningService._normalized_configuration(content)
        numbering = dict(normalized["numbering"])
        return {
            "prefix": str(numbering[f"{entity}_prefix"]).strip(),
            "width": int(numbering[f"{entity}_padding"]),
            "separator": str(numbering.get("separator", "-")),
        }

    def _number_preview(self, rule: str, prefix: str, width: int, separator: str) -> str:
        sequence = self._sequence(rule)
        return f"{prefix}{separator}{sequence.next_value:0{width}d}"

    def _reserve_number(self, rule: str, prefix: str, width: int, separator: str) -> str:
        result = self.db.execute(
            update(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == rule,
                AdminNumberSequence.scope_key == "tenant",
            )
            .values(
                next_value=AdminNumberSequence.next_value + 1,
                version=AdminNumberSequence.version + 1,
                updated_at=utc_now(),
            )
            .returning(AdminNumberSequence.next_value)
        ).scalar_one()
        return f"{prefix}{separator}{int(result) - 1:0{width}d}"

    def _sequence(self, rule: str) -> AdminNumberSequence:
        record = self.db.scalar(
            select(AdminNumberSequence).where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == rule,
                AdminNumberSequence.scope_key == "tenant",
            )
        )
        if record is None:
            raise HTTPException(status_code=409, detail={"code": "CAPITAL_PLANNING_NUMBERING_NOT_INITIALIZED"})
        return record

    def _cycle_out(self, record: CapitalPlanningCycle, demand_count: int | None = None) -> CycleOut:
        if demand_count is None:
            demand_count = int(
                self.db.scalar(
                    select(func.count(StrategicCapitalDemand.id)).where(
                        StrategicCapitalDemand.tenant_id == self.tenant_id,
                        StrategicCapitalDemand.planning_cycle_id == record.id,
                    )
                )
                or 0
            )
        return CycleOut(
            id=record.id,
            cycle_number=record.cycle_number,
            name=record.name,
            planning_horizon_start=record.planning_horizon_start,
            planning_horizon_end=record.planning_horizon_end,
            status=record.status,
            scope_workspace_id=record.scope_workspace_id,
            responsible_organization_workspace_id=record.responsible_organization_workspace_id,
            applicable_theme_codes=list(record.applicable_theme_codes_json or []),
            capital_basis_currency=record.capital_basis_currency,
            description=record.description,
            configuration_hash=record.configuration_hash,
            demand_count=demand_count,
            created_by_user_id=record.created_by_user_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            opened_at=record.opened_at,
            review_started_at=record.review_started_at,
            closed_at=record.closed_at,
            revision_version=record.revision_version,
        )

    def _cycle_demand_counts(self, cycle_ids: list[int]) -> dict[int, int]:
        if not cycle_ids:
            return {}
        rows = self.db.execute(
            select(StrategicCapitalDemand.planning_cycle_id, func.count(StrategicCapitalDemand.id))
            .where(
                StrategicCapitalDemand.tenant_id == self.tenant_id,
                StrategicCapitalDemand.planning_cycle_id.in_(cycle_ids),
            )
            .group_by(StrategicCapitalDemand.planning_cycle_id)
        ).all()
        return {int(cycle_id): int(count) for cycle_id, count in rows}

    def _demand_out(self, record: StrategicCapitalDemand) -> DemandOut:
        return self._demand_out_many([record])[0]

    def _demand_out_many(self, records: list[StrategicCapitalDemand]) -> list[DemandOut]:
        if not records:
            return []
        cycle_ids = {item.planning_cycle_id for item in records}
        workspace_ids = {
            workspace_id
            for item in records
            for workspace_id in (item.owning_workspace_id, item.potential_portfolio_id)
            if workspace_id is not None
        }
        user_ids = {item.sponsor_user_id for item in records}
        demand_ids = [item.id for item in records]
        cycles = {
            item.id: item
            for item in self.db.scalars(
                select(CapitalPlanningCycle).where(CapitalPlanningCycle.id.in_(cycle_ids))
            ).all()
        }
        workspaces = {
            item.id: item
            for item in self.db.scalars(
                select(EnterpriseWorkspace).where(EnterpriseWorkspace.id.in_(workspace_ids))
            ).all()
        }
        users = {
            item.id: item for item in self.db.scalars(select(UserAccount).where(UserAccount.id.in_(user_ids))).all()
        }
        origins = {
            int(demand_id): int(count)
            for demand_id, count in self.db.execute(
                select(CapitalDemandIdeaOrigin.capital_demand_id, func.count(CapitalDemandIdeaOrigin.id))
                .where(
                    CapitalDemandIdeaOrigin.tenant_id == self.tenant_id,
                    CapitalDemandIdeaOrigin.capital_demand_id.in_(demand_ids),
                )
                .group_by(CapitalDemandIdeaOrigin.capital_demand_id)
            ).all()
        }
        result: list[DemandOut] = []
        for record in records:
            cycle = cycles[record.planning_cycle_id]
            workspace = workspaces[record.owning_workspace_id]
            portfolio = workspaces.get(record.potential_portfolio_id)
            sponsor = users.get(record.sponsor_user_id)
            result.append(
                DemandOut(
                    id=record.id,
                    demand_number=record.demand_number,
                    name=record.name,
                    description=record.description,
                    planning_cycle_id=record.planning_cycle_id,
                    planning_cycle_number=cycle.cycle_number,
                    planning_cycle_name=cycle.name,
                    theme_codes=list(record.theme_codes_json or []),
                    strategic_objective_codes=list(record.strategic_objective_codes_json or []),
                    business_or_asset_need=record.business_or_asset_need,
                    strategic_driver=record.strategic_driver,
                    demand_category=record.demand_category,
                    urgency=record.urgency,
                    target_horizon=record.target_horizon,
                    sponsor_user_id=record.sponsor_user_id,
                    sponsor_name=sponsor.full_name if sponsor else "Unknown",
                    owning_workspace_id=record.owning_workspace_id,
                    owning_workspace_name=workspace.name,
                    location_context=record.location_context,
                    indicative_capital_need=record.indicative_capital_need,
                    currency_code=record.currency_code,
                    indicative_capital_range_low=record.indicative_capital_range_low,
                    indicative_capital_range_high=record.indicative_capital_range_high,
                    uncertainty_level=record.uncertainty_level,
                    potential_portfolio_id=record.potential_portfolio_id,
                    potential_portfolio_name=portfolio.name if portfolio else None,
                    assumptions=list(record.assumptions_json or []),
                    constraints=list(record.constraints_json or []),
                    dependencies=list(record.dependencies_json or []),
                    status=record.status,
                    readiness=record.readiness_json or {},
                    ideas_originated=origins.get(record.id, 0),
                    configuration_hash=record.configuration_hash,
                    demand_hash=record.demand_hash,
                    endorsed_snapshot_hash=record.endorsed_snapshot_hash,
                    created_by_user_id=record.created_by_user_id,
                    reviewer_user_id=record.reviewer_user_id,
                    endorser_user_id=record.endorser_user_id,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                    submitted_at=record.submitted_at,
                    review_started_at=record.review_started_at,
                    endorsed_at=record.endorsed_at,
                    revision_version=record.revision_version,
                    allowed_actions=self._allowed_actions(record),
                )
            )
        return result

    def _origin_out(
        self,
        record: CapitalDemandIdeaOrigin,
        *,
        created: bool,
        idea: Idea | None = None,
    ) -> IdeaOriginOut:
        if idea is None:
            idea = self.db.scalar(select(Idea).where(Idea.id == record.idea_id, Idea.tenant_id == self.tenant_id))
        if idea is None:
            raise HTTPException(status_code=409, detail={"code": "ORIGIN_IDEA_MISSING"})
        return IdeaOriginOut(
            id=record.id,
            source_capital_demand_id=record.capital_demand_id,
            idea_id=record.idea_id,
            idea_number=idea.idea_number,
            source_demand_version=record.source_demand_version,
            source_snapshot_hash=record.source_snapshot_hash,
            source_configuration_hash=record.source_configuration_hash,
            originated_by=record.originated_by_user_id,
            originated_at=record.originated_at,
            created=created,
        )

    def _sync_cycle_themes(self, cycle_id: int, codes: list[str]) -> None:
        self.db.execute(
            delete(CapitalPlanningCycleTheme).where(
                CapitalPlanningCycleTheme.tenant_id == self.tenant_id,
                CapitalPlanningCycleTheme.planning_cycle_id == cycle_id,
            )
        )
        self.db.add_all(
            [
                CapitalPlanningCycleTheme(
                    tenant_id=self.tenant_id,
                    planning_cycle_id=cycle_id,
                    theme_code=code,
                )
                for code in codes
            ]
        )

    def _sync_demand_links(self, demand_id: int, theme_codes: list[str], objective_codes: list[str]) -> None:
        self.db.execute(
            delete(StrategicCapitalDemandTheme).where(
                StrategicCapitalDemandTheme.tenant_id == self.tenant_id,
                StrategicCapitalDemandTheme.capital_demand_id == demand_id,
            )
        )
        self.db.execute(
            delete(StrategicCapitalDemandObjective).where(
                StrategicCapitalDemandObjective.tenant_id == self.tenant_id,
                StrategicCapitalDemandObjective.capital_demand_id == demand_id,
            )
        )
        self.db.add_all(
            [
                StrategicCapitalDemandTheme(
                    tenant_id=self.tenant_id,
                    capital_demand_id=demand_id,
                    theme_code=code,
                )
                for code in theme_codes
            ]
            + [
                StrategicCapitalDemandObjective(
                    tenant_id=self.tenant_id,
                    capital_demand_id=demand_id,
                    objective_code=code,
                )
                for code in objective_codes
            ]
        )

    def _allowed_actions(self, record: StrategicCapitalDemand) -> list[str]:
        roles = self.context.role_codes
        # Organization-wide is a data scope, never an implicit duty grant.
        organization_admin = "organization_admin" in roles
        author = organization_admin or "capital_planning_author" in roles
        reviewer = organization_admin or "capital_planning_reviewer" in roles
        endorser = organization_admin or "capital_planning_endorser" in roles
        originator = organization_admin or "capital_planning_originator" in roles
        actions: list[str] = []
        if (
            record.status in {"DRAFT", "RETURNED"}
            and author
            and (organization_admin or record.created_by_user_id == self.actor_id)
        ):
            actions.extend(["edit", "submit", "cancel"])
        if record.status == "SUBMITTED":
            if reviewer:
                actions.extend(["review", "return", "defer"])
            if author and (organization_admin or record.created_by_user_id == self.actor_id):
                actions.append("cancel")
        if record.status == "IN_REVIEW":
            if reviewer:
                actions.extend(["return", "defer"])
            if endorser and record.created_by_user_id != self.actor_id:
                actions.append("endorse")
            if organization_admin:
                actions.append("cancel")
        if (
            record.status == "DEFERRED"
            and author
            and (organization_admin or record.created_by_user_id == self.actor_id)
        ):
            actions.append("cancel")
        if record.status == "ENDORSED" and originator:
            actions.append("originate_idea")
        return sorted(set(actions))

    @staticmethod
    def _check_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise HTTPException(
                status_code=412,
                detail={"code": "ETAG_MISMATCH", "expected": expected, "actual": actual},
            )

    @staticmethod
    def _assert_same_request(existing_hash: str | None, request_hash: str) -> None:
        if existing_hash != request_hash:
            CapitalPlanningService._idempotency_conflict()

    @staticmethod
    def _idempotency_conflict() -> None:
        raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_KEY_REUSED"})

    def _touch(self, record: CapitalPlanningCycle | StrategicCapitalDemand) -> None:
        record.last_modified_by_user_id = self.actor_id
        record.updated_at = utc_now()
        record.revision_version += 1

    def _commit_cycle(self, record: CapitalPlanningCycle) -> CycleOut:
        self.db.commit()
        self.db.refresh(record)
        return self._cycle_out(record)

    def _commit_demand(self, record: StrategicCapitalDemand) -> DemandOut:
        self.db.commit()
        self.db.refresh(record)
        return self._demand_out(record)

    def _event(self, event_type: str, target_type: str, target_id: int, metadata: dict) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type=target_type,
                target_id=target_id,
                metadata_json=metadata,
            )
        )
