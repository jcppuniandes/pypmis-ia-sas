"""Gate 07H governed strategic capacity, demand and Resource Scenario service."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.portfolio_analysis.schemas import (
    AnalysisFiltersIn,
    PortfolioAnalysisOverviewOut,
    PortfolioAnalysisRowOut,
)
from app.modules.portfolio_analysis.service import PortfolioAnalysisService
from app.modules.portfolio_resource.models import (
    PortfolioResourceCapacityPeriod,
    PortfolioResourceCapacityPlan,
    PortfolioResourceScenario,
    PortfolioResourceScenarioProject,
    ProjectResourceDemandPeriod,
    ProjectResourceDemandProfile,
)
from app.modules.portfolio_resource.schemas import (
    CapacityDemandCellOut,
    CapacityPeriodOut,
    CapacityPlanCreateIn,
    CapacityPlanOut,
    CapacityPlanUpdateIn,
    ConfigurationPreviewOut,
    DemandPeriodOut,
    DemandProfileCreateIn,
    DemandProfileOut,
    DemandProfileUpdateIn,
    PortfolioResourcePlanningReadinessOut,
    ResourcePlanningOverviewOut,
    ResourceRecommendationContractOut,
    ResourceScenarioCreateIn,
    ResourceScenarioOut,
    ResourceScenarioReadinessOut,
    ResourceScenarioSummaryOut,
    ResourceScenarioUpdateIn,
    ScenarioComparisonOut,
    ScenarioProjectOut,
    ScenarioRefreshPreviewOut,
    ScenarioSelectionIn,
    ScenarioTimingIn,
)

CONFIGURATION_KIND = "portfolio_resource_configuration"
DEFAULT_CODE = "gate07h-default"
READY_INPUT = "READY_FOR_PORTFOLIO_SCENARIO_PLANNING"
READY_OUTPUT = "READY_FOR_PORTFOLIO_RESOURCE_RECOMMENDATION"
REWORK_OUTPUT = "GATE07H_REWORK_REQUIRED"

DEFAULT_CONFIGURATION: dict[str, Any] = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "applicable_governance_models": ["CAPITAL_OWNER"],
    "resource_roles": [
        {"role_key": "PROJECT_MANAGER", "name": "Project Manager", "category": "MANAGEMENT", "unit": "FTE"},
        {"role_key": "SCHEDULER", "name": "Scheduler", "category": "PROJECT_CONTROLS", "unit": "FTE"},
        {"role_key": "COST_ENGINEER", "name": "Cost Engineer", "category": "PROJECT_CONTROLS", "unit": "FTE"},
        {"role_key": "BIM_COORDINATOR", "name": "BIM Coordinator", "category": "ENGINEERING", "unit": "FTE"},
    ],
    "allowed_units": ["FTE", "HOURS", "CREW_EQUIVALENT"],
    "default_unit": "FTE",
    "allowed_demand_source_types": [
        "PROJECT_RESOURCE_DEMAND_PROFILE",
        "PROJECT_DEFINITION_RESOURCE_ESTIMATE",
        "TEMPLATE_RESOURCE_PROFILE",
        "MANUAL_PORTFOLIO_PLANNING_PROFILE",
    ],
    "demand_source_preference": [
        "PROJECT_DEFINITION_RESOURCE_ESTIMATE",
        "PROJECT_RESOURCE_DEMAND_PROFILE",
        "TEMPLATE_RESOURCE_PROFILE",
        "MANUAL_PORTFOLIO_PLANNING_PROFILE",
    ],
    "required_demand_coverage_percent": 100,
    "period_granularity": "MONTH",
    "allowed_timing_methods": ["NO_SHIFT", "SHIFT_START_KEEP_DURATION", "CUSTOM_SCENARIO_DATES"],
    "default_timing_method": "NO_SHIFT",
    "overload_policy": "ALLOW_WITH_WARNING",
    "maximum_utilization_percent": 100,
    "maximum_overload_tolerance_percent": 0,
    "scenario_max_count": 20,
    "forced_reason_required": True,
    "capacity_publish_four_eyes": False,
    "scenario_creator_cannot_freeze": False,
    "controlled_constraints": [
        "ROLE_CAPACITY",
        "PERIOD_CAPACITY",
        "FORCED_IN_OUT",
        "MAXIMUM_UTILIZATION",
        "MAXIMUM_OVERLOAD_TOLERANCE",
        "MINIMUM_SCORE",
        "MAXIMUM_RISK",
    ],
    "readiness": {"minimum_frozen_scenarios": 1},
}


class PortfolioResourceService:
    def __init__(
        self,
        db: Session,
        tenant_id: int,
        actor_id: int,
        context: EnterprisePermissionContext | None = None,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.context = context

    def ensure_seed(self) -> None:
        existing = self.db.scalar(
            select(AdminConfiguration.id).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.code == DEFAULT_CODE,
            )
        )
        if existing is not None:
            return
        content = deepcopy(DEFAULT_CONFIGURATION)
        self.db.add(
            AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=CONFIGURATION_KIND,
                code=DEFAULT_CODE,
                name="Default Portfolio Resource Planning Configuration",
                description="Gate 07H starter policy. Review and publish before USER resource planning.",
                status="draft",
                revision=1,
                version=1,
                content_json=content,
                content_hash=_hash(content),
                created_by_user_id=self.actor_id,
            )
        )
        self._event("portfolio_resource.configuration_seeded_as_draft", "AdminConfiguration", None, {})
        self.db.commit()

    # Capacity Plans -------------------------------------------------
    def capacity_plans(self, portfolio_id: int) -> list[CapacityPlanOut]:
        self._portfolio(portfolio_id)
        return [self._capacity_out(item) for item in self._capacity_records(portfolio_id)]

    def capacity_plan(self, plan_id: int) -> CapacityPlanOut:
        return self._capacity_out(self._capacity(plan_id))

    def create_capacity_plan(self, portfolio_id: int, payload: CapacityPlanCreateIn) -> CapacityPlanOut:
        self._analysis(portfolio_id, require_resource=True)
        policy = self._policy(portfolio_id, require_published=True)
        replay = self.db.scalar(
            select(PortfolioResourceCapacityPlan).where(
                PortfolioResourceCapacityPlan.tenant_id == self.tenant_id,
                PortfolioResourceCapacityPlan.create_idempotency_key == payload.idempotency_key,
            )
        )
        if replay is not None:
            return self._capacity_out(replay)
        self._validate_capacity_payload(payload, policy)
        revision = int(
            self.db.scalar(
                select(func.coalesce(func.max(PortfolioResourceCapacityPlan.plan_revision), 0)).where(
                    PortfolioResourceCapacityPlan.tenant_id == self.tenant_id,
                    PortfolioResourceCapacityPlan.portfolio_workspace_id == portfolio_id,
                    PortfolioResourceCapacityPlan.logical_code == "RESOURCE-CAPACITY",
                )
            )
            or 0
        ) + 1
        record = PortfolioResourceCapacityPlan(
            tenant_id=self.tenant_id,
            portfolio_workspace_id=portfolio_id,
            logical_code="RESOURCE-CAPACITY",
            plan_name=payload.plan_name,
            planning_horizon_start=payload.planning_horizon_start,
            planning_horizon_end=payload.planning_horizon_end,
            period_granularity=payload.period_granularity,
            status="DRAFT",
            plan_revision=revision,
            source_reference=payload.source_reference,
            notes=payload.notes,
            create_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        self._replace_capacity_periods(record, payload.periods)
        record.capacity_hash = self._capacity_hash(record)
        self._event("portfolio_resource.capacity_plan_created", "PortfolioResourceCapacityPlan", record.id, {})
        self.db.commit()
        return self._capacity_out(record)

    def update_capacity_plan(
        self, plan_id: int, expected_version: int, payload: CapacityPlanUpdateIn
    ) -> CapacityPlanOut:
        record = self._capacity(plan_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "CAPACITY_PLAN_IMMUTABLE"})
        policy = self._policy(record.portfolio_workspace_id, require_published=True)
        self._validate_capacity_payload(payload, policy)
        record.plan_name = payload.plan_name
        record.planning_horizon_start = payload.planning_horizon_start
        record.planning_horizon_end = payload.planning_horizon_end
        record.period_granularity = payload.period_granularity
        record.source_reference = payload.source_reference
        record.notes = payload.notes
        record.updated_by = self.actor_id
        record.updated_at = utc_now()
        record.revision_version += 1
        self._replace_capacity_periods(record, payload.periods)
        record.capacity_hash = self._capacity_hash(record)
        self._event("portfolio_resource.capacity_plan_updated", "PortfolioResourceCapacityPlan", record.id, {})
        self.db.commit()
        return self._capacity_out(record)

    def publish_capacity_plan(self, plan_id: int, expected_version: int, idempotency_key: str) -> CapacityPlanOut:
        record = self._capacity(plan_id, lock=True)
        if record.publish_idempotency_key == idempotency_key and record.status == "PUBLISHED":
            return self._capacity_out(record)
        self._check_version(record.revision_version, expected_version)
        if record.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "CAPACITY_PLAN_NOT_DRAFT"})
        policy = self._policy(record.portfolio_workspace_id, require_published=True)
        if policy.get("capacity_publish_four_eyes") and record.created_by == self.actor_id:
            raise HTTPException(status_code=409, detail={"code": "FOUR_EYES_REQUIRED"})
        if not self._capacity_periods(record.id):
            raise HTTPException(status_code=422, detail={"code": "CAPACITY_PERIODS_REQUIRED"})
        for previous in self._capacity_records(record.portfolio_workspace_id):
            if previous.id != record.id and previous.status == "PUBLISHED" and previous.logical_code == record.logical_code:
                previous.status = "SUPERSEDED"
                previous.updated_by = self.actor_id
                previous.updated_at = utc_now()
                previous.revision_version += 1
        record.status = "PUBLISHED"
        record.capacity_hash = self._capacity_hash(record)
        record.publish_idempotency_key = idempotency_key
        record.published_at = utc_now()
        record.updated_at = utc_now()
        record.updated_by = self.actor_id
        record.revision_version += 1
        self._event("portfolio_resource.capacity_plan_published", "PortfolioResourceCapacityPlan", record.id, {})
        self.db.commit()
        return self._capacity_out(record)

    # Demand Profiles -----------------------------------------------
    def demand_profiles(self, project_id: int) -> list[DemandProfileOut]:
        self._project(project_id)
        return [self._demand_out(item) for item in self._demand_records(project_id)]

    def demand_profile(self, profile_id: int) -> DemandProfileOut:
        return self._demand_out(self._demand(profile_id))

    def create_demand_profile(self, project_id: int, payload: DemandProfileCreateIn) -> DemandProfileOut:
        self._project(project_id)
        replay = self.db.scalar(
            select(ProjectResourceDemandProfile).where(
                ProjectResourceDemandProfile.tenant_id == self.tenant_id,
                ProjectResourceDemandProfile.create_idempotency_key == payload.idempotency_key,
            )
        )
        if replay is not None:
            return self._demand_out(replay)
        policy = self._tenant_policy(require_published=True)
        self._validate_demand_payload(payload, policy)
        revision = int(
            self.db.scalar(
                select(func.coalesce(func.max(ProjectResourceDemandProfile.profile_revision), 0)).where(
                    ProjectResourceDemandProfile.tenant_id == self.tenant_id,
                    ProjectResourceDemandProfile.project_workspace_id == project_id,
                    ProjectResourceDemandProfile.logical_code == "RESOURCE-DEMAND",
                )
            )
            or 0
        ) + 1
        record = ProjectResourceDemandProfile(
            tenant_id=self.tenant_id,
            project_workspace_id=project_id,
            logical_code="RESOURCE-DEMAND",
            profile_name=payload.profile_name,
            status="DRAFT",
            profile_revision=revision,
            source_type=payload.source_type,
            source_reference=payload.source_reference,
            source_hash=_hash({"type": payload.source_type, "reference": payload.source_reference, "as_of": payload.as_of_date}),
            as_of_date=payload.as_of_date,
            planning_start=payload.planning_start,
            planning_finish=payload.planning_finish,
            generation_method=payload.generation_method,
            approximation=payload.generation_method != "EXPLICIT_PERIOD_PROFILE",
            create_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        self._replace_demand_periods(record, payload.periods)
        record.demand_hash = self._demand_hash(record)
        self._event("portfolio_resource.demand_profile_created", "ProjectResourceDemandProfile", record.id, {})
        self.db.commit()
        return self._demand_out(record)

    def update_demand_profile(
        self, profile_id: int, expected_version: int, payload: DemandProfileUpdateIn
    ) -> DemandProfileOut:
        record = self._demand(profile_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "DEMAND_PROFILE_IMMUTABLE"})
        self._validate_demand_payload(payload, self._tenant_policy(require_published=True))
        record.profile_name = payload.profile_name
        record.source_type = payload.source_type
        record.source_reference = payload.source_reference
        record.as_of_date = payload.as_of_date
        record.planning_start = payload.planning_start
        record.planning_finish = payload.planning_finish
        record.generation_method = payload.generation_method
        record.approximation = payload.generation_method != "EXPLICIT_PERIOD_PROFILE"
        record.source_hash = _hash({"type": payload.source_type, "reference": payload.source_reference, "as_of": payload.as_of_date})
        record.updated_by = self.actor_id
        record.updated_at = utc_now()
        record.revision_version += 1
        self._replace_demand_periods(record, payload.periods)
        record.demand_hash = self._demand_hash(record)
        self._event("portfolio_resource.demand_profile_updated", "ProjectResourceDemandProfile", record.id, {})
        self.db.commit()
        return self._demand_out(record)

    def publish_demand_profile(self, profile_id: int, expected_version: int, idempotency_key: str) -> DemandProfileOut:
        record = self._demand(profile_id, lock=True)
        if record.publish_idempotency_key == idempotency_key and record.status == "PUBLISHED":
            return self._demand_out(record)
        self._check_version(record.revision_version, expected_version)
        if record.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "DEMAND_PROFILE_NOT_DRAFT"})
        if not self._demand_periods(record.id):
            raise HTTPException(status_code=422, detail={"code": "DEMAND_PERIODS_REQUIRED"})
        for previous in self._demand_records(record.project_workspace_id):
            if previous.id != record.id and previous.status == "PUBLISHED" and previous.logical_code == record.logical_code:
                previous.status = "SUPERSEDED"
                previous.updated_by = self.actor_id
                previous.updated_at = utc_now()
                previous.revision_version += 1
        record.status = "PUBLISHED"
        record.demand_hash = self._demand_hash(record)
        record.publish_idempotency_key = idempotency_key
        record.published_at = utc_now()
        record.updated_at = utc_now()
        record.updated_by = self.actor_id
        record.revision_version += 1
        self._event("portfolio_resource.demand_profile_published", "ProjectResourceDemandProfile", record.id, {})
        self.db.commit()
        return self._demand_out(record)

    # Resource Scenarios --------------------------------------------
    def scenarios(self, portfolio_id: int) -> list[ResourceScenarioOut]:
        self._portfolio(portfolio_id)
        return [self._scenario_out(item) for item in self._scenario_records(portfolio_id)]

    def scenario(self, scenario_id: int) -> ResourceScenarioOut:
        return self._scenario_out(self._scenario(scenario_id))

    def create_scenario(self, portfolio_id: int, payload: ResourceScenarioCreateIn) -> ResourceScenarioOut:
        analysis = self._analysis(
            portfolio_id,
            require_resource=True,
            expected_hash=payload.expected_analysis_hash,
        )
        policy = self._policy(portfolio_id, require_published=True)
        replay = self.db.scalar(
            select(PortfolioResourceScenario).where(
                PortfolioResourceScenario.tenant_id == self.tenant_id,
                PortfolioResourceScenario.create_idempotency_key == payload.idempotency_key,
            )
        )
        if replay is not None:
            return self._scenario_out(replay)
        if len(self._scenario_records(portfolio_id)) >= int(policy.get("scenario_max_count", 20)):
            raise HTTPException(status_code=409, detail={"code": "RESOURCE_SCENARIO_LIMIT_REACHED"})
        capacity = self._capacity(payload.capacity_plan_id)
        if capacity.portfolio_workspace_id != portfolio_id or capacity.status != "PUBLISHED":
            raise HTTPException(status_code=422, detail={"code": "PUBLISHED_CAPACITY_PLAN_REQUIRED"})
        source: PortfolioResourceScenario | None = None
        if payload.creation_mode == "COPY_EXISTING_SCENARIO":
            source = self._scenario(payload.source_scenario_id)
            if source.portfolio_workspace_id != portfolio_id:
                raise HTTPException(status_code=422, detail={"code": "SCENARIO_PORTFOLIO_MISMATCH"})
        logical_code = f"RESOURCE-SCENARIO-{utc_now().strftime('%Y%m%d%H%M%S%f')}"
        record = PortfolioResourceScenario(
            tenant_id=self.tenant_id,
            portfolio_workspace_id=portfolio_id,
            logical_code=logical_code,
            scenario_name=payload.scenario_name,
            description=payload.description,
            status="DRAFT",
            capacity_plan_id=capacity.id,
            capacity_plan_hash=capacity.capacity_hash,
            source_analysis_hash=analysis.dataset.analysis_hash,
            source_prioritization_hash=analysis.dataset.source_prioritization_hash,
            membership_set_hash=analysis.dataset.membership_set_hash,
            evaluation_set_hash=analysis.dataset.evaluation_set_hash,
            source_configuration_hash=_hash(policy),
            source_hash="",
            creation_mode=payload.creation_mode,
            overload_policy=str(policy.get("overload_policy", "ALLOW_WITH_WARNING")),
            scenario_revision=1,
            create_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        if source is not None:
            self._copy_scenario_rows(source.id, record.id)
        else:
            self._snapshot_analysis_rows(
                record,
                analysis.dataset.rows,
                select_priority=payload.creation_mode == "FROM_CURRENT_PRIORITY",
            )
        rows = self._scenario_rows(record.id)
        record.source_hash = self._source_hash(record, capacity, rows)
        self._recalculate_scenario(record)
        self._event(
            "portfolio_resource.scenario_created",
            "PortfolioResourceScenario",
            record.id,
            {"mode": payload.creation_mode, "budget_dependency": False},
        )
        self.db.commit()
        return self._scenario_out(record)

    def update_scenario(
        self, scenario_id: int, expected_version: int, payload: ResourceScenarioUpdateIn
    ) -> ResourceScenarioOut:
        record = self._scenario(scenario_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_scenario_editable(record)
        record.scenario_name = payload.scenario_name
        record.description = payload.description
        record.status = payload.status
        self._touch_scenario(record)
        self._recalculate_scenario(record)
        self._event("portfolio_resource.scenario_updated", "PortfolioResourceScenario", record.id, {})
        self.db.commit()
        return self._scenario_out(record)

    def select_project(
        self,
        scenario_id: int,
        project_id: int,
        expected_version: int,
        payload: ScenarioSelectionIn,
    ) -> ResourceScenarioOut:
        record = self._scenario(scenario_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_scenario_editable(record)
        row = self.db.scalar(
            select(PortfolioResourceScenarioProject).where(
                PortfolioResourceScenarioProject.tenant_id == self.tenant_id,
                PortfolioResourceScenarioProject.scenario_id == record.id,
                PortfolioResourceScenarioProject.project_workspace_id == project_id,
            )
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Resource Scenario Project not found")
        if row.last_selection_idempotency_key == payload.idempotency_key:
            return self._scenario_out(record)
        row.selection_state = payload.selection_state
        row.forced_reason = payload.forced_reason.strip() if payload.forced_reason else None
        row.forced_authority_reference = payload.authority_reference
        row.last_selection_idempotency_key = payload.idempotency_key
        row.updated_by = self.actor_id
        row.updated_at = utc_now()
        row.revision_version += 1
        if payload.selection_state in {"FORCED_IN", "FORCED_OUT"}:
            row.forced_actor_id = self.actor_id
            row.forced_at = utc_now()
            self._event(
                f"portfolio_resource.project_{payload.selection_state.lower()}",
                "PortfolioResourceScenarioProject",
                row.id,
                {"reason": row.forced_reason, "authority_reference": payload.authority_reference},
            )
        else:
            row.forced_actor_id = None
            row.forced_at = None
            row.forced_authority_reference = None
        row.row_hash = self._row_hash(row)
        self._touch_scenario(record)
        self._recalculate_scenario(record)
        self._event("portfolio_resource.project_selection_updated", "PortfolioResourceScenarioProject", row.id, {})
        self.db.commit()
        return self._scenario_out(record)

    def adjust_timing(
        self,
        scenario_id: int,
        project_id: int,
        expected_version: int,
        payload: ScenarioTimingIn,
    ) -> ResourceScenarioOut:
        record = self._scenario(scenario_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_scenario_editable(record)
        row = self.db.scalar(
            select(PortfolioResourceScenarioProject).where(
                PortfolioResourceScenarioProject.tenant_id == self.tenant_id,
                PortfolioResourceScenarioProject.scenario_id == record.id,
                PortfolioResourceScenarioProject.project_workspace_id == project_id,
            )
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Resource Scenario Project not found")
        if row.last_timing_idempotency_key == payload.idempotency_key:
            return self._scenario_out(record)
        if payload.timing_method == "NO_SHIFT":
            row.scenario_start = row.source_project_start
            row.scenario_finish = row.source_project_finish
            row.schedule_shift_days = 0
        elif payload.timing_method == "SHIFT_START_KEEP_DURATION":
            if row.source_project_start is None or row.source_project_finish is None:
                raise HTTPException(status_code=422, detail={"code": "SOURCE_PROJECT_DATES_REQUIRED"})
            duration = row.source_project_finish - row.source_project_start
            row.scenario_start = payload.scenario_start
            row.scenario_finish = payload.scenario_start + duration
            row.schedule_shift_days = (payload.scenario_start - row.source_project_start).days
        else:
            row.scenario_start = payload.scenario_start
            row.scenario_finish = payload.scenario_finish
            row.schedule_shift_days = (
                (payload.scenario_start - row.source_project_start).days
                if payload.scenario_start and row.source_project_start
                else 0
            )
        row.timing_method = payload.timing_method
        row.last_timing_idempotency_key = payload.idempotency_key
        row.updated_by = self.actor_id
        row.updated_at = utc_now()
        row.revision_version += 1
        row.row_hash = self._row_hash(row)
        self._touch_scenario(record)
        self._recalculate_scenario(record)
        self._event(
            "portfolio_resource.scenario_timing_adjusted",
            "PortfolioResourceScenarioProject",
            row.id,
            {
                "timing_method": payload.timing_method,
                "schedule_shift_days": row.schedule_shift_days,
                "source_dates_unchanged": True,
            },
        )
        self.db.commit()
        return self._scenario_out(record)

    def clone_scenario(self, scenario_id: int, expected_version: int, idempotency_key: str) -> ResourceScenarioOut:
        source = self._scenario(scenario_id, lock=True)
        clone_key = f"resource-clone-{source.id}-{idempotency_key}"
        existing = self.db.scalar(
            select(PortfolioResourceScenario).where(
                PortfolioResourceScenario.tenant_id == self.tenant_id,
                PortfolioResourceScenario.create_idempotency_key == clone_key,
            )
        )
        if existing is not None:
            return self._scenario_out(existing)
        self._check_version(source.revision_version, expected_version)
        revision = int(
            self.db.scalar(
                select(func.max(PortfolioResourceScenario.scenario_revision)).where(
                    PortfolioResourceScenario.tenant_id == self.tenant_id,
                    PortfolioResourceScenario.portfolio_workspace_id == source.portfolio_workspace_id,
                    PortfolioResourceScenario.logical_code == source.logical_code,
                )
            )
            or source.scenario_revision
        ) + 1
        clone = PortfolioResourceScenario(
            tenant_id=self.tenant_id,
            portfolio_workspace_id=source.portfolio_workspace_id,
            logical_code=source.logical_code,
            scenario_name=f"{source.scenario_name} · revision {revision}",
            description=source.description,
            status="DRAFT",
            capacity_plan_id=source.capacity_plan_id,
            capacity_plan_hash=source.capacity_plan_hash,
            source_analysis_hash=source.source_analysis_hash,
            source_prioritization_hash=source.source_prioritization_hash,
            membership_set_hash=source.membership_set_hash,
            evaluation_set_hash=source.evaluation_set_hash,
            source_configuration_hash=source.source_configuration_hash,
            source_hash=source.source_hash,
            creation_mode="COPY_EXISTING_SCENARIO",
            overload_policy=source.overload_policy,
            scenario_revision=revision,
            create_idempotency_key=clone_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._copy_scenario_rows(source.id, clone.id)
        self._recalculate_scenario(clone)
        self._event("portfolio_resource.scenario_cloned", "PortfolioResourceScenario", clone.id, {"source_id": source.id})
        self.db.commit()
        return self._scenario_out(clone)

    def freeze_scenario(self, scenario_id: int, expected_version: int, idempotency_key: str) -> ResourceScenarioOut:
        record = self._scenario(scenario_id, lock=True)
        if record.freeze_idempotency_key == idempotency_key and record.status == "FROZEN":
            return self._scenario_out(record)
        self._check_version(record.revision_version, expected_version)
        self._assert_scenario_editable(record)
        policy = self._policy(record.portfolio_workspace_id, require_published=True)
        if policy.get("scenario_creator_cannot_freeze") and record.created_by == self.actor_id:
            raise HTTPException(status_code=409, detail={"code": "FOUR_EYES_REQUIRED"})
        readiness = self._scenario_readiness(record, historical=False)
        if readiness.status != "READY":
            raise HTTPException(status_code=409, detail={"code": "RESOURCE_SCENARIO_NOT_READY", "blockers": readiness.blockers})
        record.status = "FROZEN"
        record.freeze_idempotency_key = idempotency_key
        record.frozen_at = utc_now()
        self._touch_scenario(record)
        self._recalculate_scenario(record)
        self._event("portfolio_resource.scenario_frozen", "PortfolioResourceScenario", record.id, {"approval": False})
        self.db.commit()
        self._emit_readiness_change(record.portfolio_workspace_id)
        self.db.commit()
        return self._scenario_out(record)

    def void_scenario(self, scenario_id: int, expected_version: int, idempotency_key: str) -> ResourceScenarioOut:
        record = self._scenario(scenario_id, lock=True)
        if record.void_idempotency_key == idempotency_key and record.status == "VOIDED":
            return self._scenario_out(record)
        self._check_version(record.revision_version, expected_version)
        self._assert_scenario_editable(record)
        record.status = "VOIDED"
        record.void_idempotency_key = idempotency_key
        record.voided_at = utc_now()
        self._touch_scenario(record)
        self._event("portfolio_resource.scenario_voided", "PortfolioResourceScenario", record.id, {})
        self.db.commit()
        return self._scenario_out(record)

    def refresh_preview(self, scenario_id: int) -> ScenarioRefreshPreviewOut:
        record = self._scenario(scenario_id)
        if record.status not in {"DRAFT", "IN_REVIEW"}:
            raise HTTPException(status_code=409, detail={"code": "FROZEN_RESOURCE_SCENARIO_REFRESH_REJECTED"})
        preview, _ = self._refresh_delta(record)
        return preview

    def apply_refresh(
        self,
        scenario_id: int,
        expected_version: int,
        expected_source_hash: str,
        idempotency_key: str,
    ) -> ResourceScenarioOut:
        record = self._scenario(scenario_id, lock=True)
        if record.refresh_idempotency_key == idempotency_key:
            return self._scenario_out(record)
        self._check_version(record.revision_version, expected_version)
        self._assert_scenario_editable(record)
        preview, analysis = self._refresh_delta(record)
        if preview.proposed_source_hash != expected_source_hash:
            raise HTTPException(
                status_code=412,
                detail={
                    "code": "STALE_PORTFOLIO_RESOURCE_SOURCE",
                    "expected": expected_source_hash,
                    "actual": preview.proposed_source_hash,
                },
            )
        old_rows = {row.project_workspace_id: row for row in self._scenario_rows(record.id)}
        self.db.execute(
            delete(PortfolioResourceScenarioProject).where(
                PortfolioResourceScenarioProject.tenant_id == self.tenant_id,
                PortfolioResourceScenarioProject.scenario_id == record.id,
            )
        )
        self.db.flush()
        self._snapshot_analysis_rows(record, analysis.dataset.rows, select_priority=False)
        for row in self._scenario_rows(record.id):
            previous = old_rows.get(row.project_workspace_id)
            if previous is None:
                continue
            row.selection_state = previous.selection_state
            row.forced_reason = previous.forced_reason
            row.forced_actor_id = previous.forced_actor_id
            row.forced_at = previous.forced_at
            row.forced_authority_reference = previous.forced_authority_reference
            row.scenario_start = previous.scenario_start
            row.scenario_finish = previous.scenario_finish
            row.schedule_shift_days = previous.schedule_shift_days
            row.timing_method = previous.timing_method
            row.row_hash = self._row_hash(row)
        capacity = self._capacity(record.capacity_plan_id)
        record.capacity_plan_hash = capacity.capacity_hash
        record.source_analysis_hash = analysis.dataset.analysis_hash
        record.source_prioritization_hash = analysis.dataset.source_prioritization_hash
        record.membership_set_hash = analysis.dataset.membership_set_hash
        record.evaluation_set_hash = analysis.dataset.evaluation_set_hash
        record.source_hash = self._source_hash(record, capacity, self._scenario_rows(record.id))
        record.refresh_idempotency_key = idempotency_key
        self._touch_scenario(record)
        self._recalculate_scenario(record)
        self._event("portfolio_resource.scenario_source_refreshed", "PortfolioResourceScenario", record.id, {})
        self.db.commit()
        return self._scenario_out(record)

    def compare(self, portfolio_id: int, scenario_ids: list[int]) -> ScenarioComparisonOut:
        self._portfolio(portfolio_id)
        if not 2 <= len(scenario_ids) <= 5 or len(set(scenario_ids)) != len(scenario_ids):
            raise HTTPException(status_code=422, detail={"code": "COMPARE_REQUIRES_TWO_TO_FIVE_UNIQUE_SCENARIOS"})
        records = [self._scenario(item) for item in scenario_ids]
        if any(item.portfolio_workspace_id != portfolio_id for item in records):
            raise HTTPException(status_code=422, detail={"code": "SCENARIO_PORTFOLIO_MISMATCH"})
        outputs = [self._scenario_out(item) for item in records]
        summaries = [
            {
                "id": item.id,
                "scenario_name": item.scenario_name,
                "status": item.status,
                "selected_count": item.summary.selected_count,
                "average_score": item.summary.average_score,
                "high_risk_count": item.summary.high_risk_count,
                "overloaded_roles": item.summary.overloaded_role_count,
                "overloaded_periods": item.summary.overloaded_period_count,
                "peak_utilization": item.summary.peak_utilization,
                "average_utilization": item.summary.average_utilization,
                "planning_horizon": [
                    min((cell.period_start for cell in item.heatmap), default=None),
                    max((cell.period_end for cell in item.heatmap), default=None),
                ],
                "warnings": item.warnings,
                "blockers": item.blockers,
            }
            for item in outputs
        ]
        projects: dict[int, dict] = {}
        for item in outputs:
            for row in item.projects:
                projects.setdefault(
                    row.project_workspace_id,
                    {"project_workspace_id": row.project_workspace_id, "project_number": row.project_number},
                )[str(item.id)] = {
                    "selection_state": row.selection_state,
                    "scenario_start": row.scenario_start,
                    "scenario_finish": row.scenario_finish,
                }
        left, right = outputs[0], outputs[1]
        left_selected = {p.project_workspace_id for p in left.projects if self._included(p.selection_state)}
        right_selected = {p.project_workspace_id for p in right.projects if self._included(p.selection_state)}
        left_rows = {p.project_workspace_id: p for p in left.projects}
        right_rows = {p.project_workspace_id: p for p in right.projects}
        shifts = [
            {
                "project_workspace_id": project_id,
                "before": [left_rows[project_id].scenario_start, left_rows[project_id].scenario_finish],
                "after": [right_rows[project_id].scenario_start, right_rows[project_id].scenario_finish],
            }
            for project_id in sorted(left_rows.keys() & right_rows.keys())
            if (
                left_rows[project_id].scenario_start,
                left_rows[project_id].scenario_finish,
            )
            != (
                right_rows[project_id].scenario_start,
                right_rows[project_id].scenario_finish,
            )
        ]
        left_demand = {(c.resource_role_key, c.period_key, c.unit): c.selected_demand for c in left.heatmap}
        right_demand = {(c.resource_role_key, c.period_key, c.unit): c.selected_demand for c in right.heatmap}
        role_delta = [
            {
                "resource_role_key": key[0],
                "period_key": key[1],
                "unit": key[2],
                "before": left_demand.get(key, Decimal("0")),
                "after": right_demand.get(key, Decimal("0")),
                "delta": right_demand.get(key, Decimal("0")) - left_demand.get(key, Decimal("0")),
            }
            for key in sorted(left_demand.keys() | right_demand.keys())
        ]
        return ScenarioComparisonOut(
            portfolio_workspace_id=portfolio_id,
            scenarios=summaries,
            project_matrix=list(projects.values()),
            pairwise_delta={
                "projects_added": sorted(right_selected - left_selected),
                "projects_removed": sorted(left_selected - right_selected),
                "date_shifts": shifts,
                "peak_utilization_delta": _decimal_or_zero(right.summary.peak_utilization)
                - _decimal_or_zero(left.summary.peak_utilization),
                "overloaded_period_delta": right.summary.overloaded_period_count
                - left.summary.overloaded_period_count,
                "overloaded_role_delta": right.summary.overloaded_role_count - left.summary.overloaded_role_count,
            },
            role_demand_delta=role_delta,
            warnings=["COMPARISON_IS_ANALYTICAL_ONLY", "NO_WINNER_OR_RECOMMENDATION_INFERENCE"],
        )

    def readiness(self, portfolio_id: int) -> PortfolioResourcePlanningReadinessOut:
        analysis = self._analysis(portfolio_id, require_resource=False)
        plans = [item for item in self._capacity_records(portfolio_id) if item.status == "PUBLISHED"]
        records = self._scenario_records(portfolio_id)
        outputs = [self._scenario_out(item) for item in records]
        frozen = [item for item in outputs if item.status == "FROZEN"]
        ready = [item for item in frozen if item.readiness.status == "READY"]
        selected = [project for item in ready for project in item.projects if self._included(project.selection_state)]
        covered = [project for project in selected if project.demand_covered]
        coverage = _percent(len(covered), len(selected))
        blockers: list[str] = []
        warnings: list[str] = []
        if analysis.readiness.final_output != READY_INPUT or not analysis.readiness.can_enter_resource_planning:
            blockers.append("READY_FOR_PORTFOLIO_RESOURCE_PLANNING_REQUIRED")
        if not plans:
            blockers.append("PUBLISHED_CAPACITY_PLAN_REQUIRED")
        minimum = int(dict(self._policy(portfolio_id, require_published=False).get("readiness", {})).get("minimum_frozen_scenarios", 1))
        if len(ready) < minimum:
            blockers.append("READY_FROZEN_RESOURCE_SCENARIO_REQUIRED")
        if any(item.summary.overloaded_period_count for item in ready):
            warnings.append("RESOURCE_OVERLOAD_PRESENT")
        resource_hash = _hash(
            {
                "portfolio_workspace_id": portfolio_id,
                "analysis_hash": analysis.dataset.analysis_hash,
                "capacity_hashes": [item.capacity_hash for item in plans],
                "scenario_hashes": [item.scenario_hash for item in ready],
                "coverage": str(coverage),
            }
        )
        can_enter = not blockers
        return PortfolioResourcePlanningReadinessOut(
            portfolio_workspace_id=portfolio_id,
            capacity_plan_id=plans[0].id if plans else None,
            scenario_count=len(records),
            frozen_scenario_count=len(frozen),
            ready_scenario_count=len(ready),
            demand_coverage=coverage,
            overloaded_scenario_count=sum(item.summary.overloaded_period_count > 0 for item in ready),
            warnings=sorted(set(warnings)),
            blockers=sorted(set(blockers)),
            resource_planning_hash=resource_hash,
            can_enter_resource_recommendation=can_enter,
            allowed_actions=self._allowed_actions(analysis.readiness.can_enter_resource_planning, can_enter),
            final_output=READY_OUTPUT if can_enter else REWORK_OUTPUT,
        )

    def overview(self, portfolio_id: int) -> ResourcePlanningOverviewOut:
        analysis = self._analysis(portfolio_id, require_resource=False)
        plans = self.capacity_plans(portfolio_id)
        project_ids = {item.project_workspace_id for item in analysis.dataset.rows}
        demands = [
            self._demand_out(item)
            for item in self.db.scalars(
                select(ProjectResourceDemandProfile).where(
                    ProjectResourceDemandProfile.tenant_id == self.tenant_id,
                    ProjectResourceDemandProfile.project_workspace_id.in_(project_ids or {-1}),
                )
            ).all()
        ]
        published = next((item for item in plans if item.status == "PUBLISHED"), None)
        return ResourcePlanningOverviewOut(
            portfolio_workspace_id=portfolio_id,
            gate07f={
                "final_output": analysis.readiness.final_output,
                "analysis_hash": analysis.dataset.analysis_hash,
                "can_enter_budget_planning": analysis.readiness.can_enter_budget_planning,
                "can_enter_resource_planning": analysis.readiness.can_enter_resource_planning,
                "budget_branch_required": False,
                "warnings": analysis.readiness.warnings,
                "blockers": analysis.readiness.blockers,
            },
            active_capacity_plan=published,
            capacity_plans=plans,
            demand_profiles=demands,
            scenarios=self.scenarios(portfolio_id),
            readiness=self.readiness(portfolio_id),
            allowed_actions=self._allowed_actions(analysis.readiness.can_enter_resource_planning, False),
            boundaries=[
                "NO_NAMED_RESOURCE_ASSIGNMENT",
                "NO_RESOURCE_LEVELING",
                "NO_CPM_RESCHEDULING",
                "NO_BUDGET_MUTATION",
                "NO_FUNDS",
                "NO_FID",
                "NO_INITIALIZATION_OR_ACTIVATION",
            ],
        )

    def recommendation_contract(self, portfolio_id: int) -> ResourceRecommendationContractOut:
        result = self.readiness(portfolio_id)
        analysis = self._analysis(portfolio_id, require_resource=False)
        ready = [
            self._scenario_out(item)
            for item in self._scenario_records(portfolio_id)
            if item.status == "FROZEN" and self._scenario_readiness(item, historical=True).status == "READY"
        ]
        capacity = self._capacity(result.capacity_plan_id) if result.capacity_plan_id else None
        return ResourceRecommendationContractOut(
            portfolio_workspace_id=portfolio_id,
            resource_planning_hash=result.resource_planning_hash,
            capacity_plan_snapshot={
                "id": capacity.id,
                "revision": capacity.plan_revision,
                "hash": capacity.capacity_hash,
            }
            if capacity
            else {},
            ready_frozen_scenario_refs=[
                {"id": item.id, "logical_code": item.logical_code, "revision": item.scenario_revision}
                for item in ready
            ],
            scenario_hashes=[item.scenario_hash for item in ready],
            gate07f_analysis_hash=analysis.dataset.analysis_hash,
            membership_set_hash=analysis.dataset.membership_set_hash,
            evaluation_set_hash=analysis.dataset.evaluation_set_hash,
            demand_coverage=result.demand_coverage,
            overload_summary={
                "overloaded_scenario_count": result.overloaded_scenario_count,
                "overloaded_period_count": sum(item.summary.overloaded_period_count for item in ready),
            },
            warnings=result.warnings,
            blockers=result.blockers,
            final_output=result.final_output,
        )

    # AdminConfiguration reuse --------------------------------------
    def configurations(self) -> list[AdminConfiguration]:
        self.ensure_seed()
        return list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                )
                .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
            ).all()
        )

    def configuration_preview(
        self,
        portfolio_id: int | None,
        configuration_id: int | None,
        content_override: dict | None,
    ) -> ConfigurationPreviewOut:
        workspace = self._portfolio(portfolio_id) if portfolio_id else None
        record = self._configuration(configuration_id) if configuration_id else None
        effective = deepcopy(content_override if content_override is not None else record.content_json if record else DEFAULT_CONFIGURATION)
        issues = self._configuration_issues(effective)
        readiness_preview: dict | None = None
        warnings: list[str] = []
        blockers: list[str] = []
        if portfolio_id:
            analysis = self._analysis(portfolio_id, require_resource=False)
            readiness_preview = {
                "gate07f_final_output": analysis.readiness.final_output,
                "can_enter_resource_planning": analysis.readiness.can_enter_resource_planning,
                "budget_branch_required": False,
                "eligible_projects": len(analysis.dataset.rows),
                "required_demand_coverage_percent": effective.get("required_demand_coverage_percent"),
                "overload_policy": effective.get("overload_policy"),
            }
            if not analysis.readiness.can_enter_resource_planning:
                blockers.append("PORTFOLIO_RESOURCE_PLANNING_NOT_ELIGIBLE")
        if effective.get("overload_policy") == "ALLOW_WITH_WARNING":
            warnings.append("OVERLOADS_REMAIN_ANALYTICAL_WARNINGS")
        source = record or self._effective_configuration(workspace, published_only=True)
        return ConfigurationPreviewOut(
            portfolio_workspace_id=portfolio_id,
            path=[self._workspace_summary(item) for item in self._workspace_path(workspace)],
            effective=effective,
            source={
                "id": source.id,
                "code": source.code,
                "revision": source.revision,
                "status": source.status,
                "content_hash": source.content_hash,
            }
            if source
            else {"type": "starter-default", "status": "draft"},
            publishable=not issues,
            validation_issues=issues,
            readiness_preview=readiness_preview,
            warnings=sorted(set(warnings)),
            blockers=sorted(set(blockers)),
            persisted=False,
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id, lock=True)
        self._check_version(source.version, expected_version)
        revision = int(
            self.db.scalar(
                select(func.coalesce(func.max(AdminConfiguration.revision), 0)).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    AdminConfiguration.code == source.code,
                )
            )
            or 0
        ) + 1
        clone = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code=source.code,
            name=f"{source.name} · revision {revision}",
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=deepcopy(source.content_json),
            content_hash=source.content_hash,
            created_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._event("portfolio_resource.configuration_cloned", "AdminConfiguration", clone.id, {"source_id": source.id})
        self.db.commit()
        return clone

    def update_configuration(
        self,
        configuration_id: int,
        expected_version: int,
        name: str,
        description: str,
        content: dict,
    ) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_IMMUTABLE"})
        self._validate_configuration(content)
        record.name = name
        record.description = description
        record.content_json = deepcopy(content)
        record.content_hash = _hash(content)
        record.version += 1
        self._event("portfolio_resource.configuration_updated", "AdminConfiguration", record.id, {})
        self.db.commit()
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "CONFIGURATION_NOT_DRAFT"})
        self._validate_configuration(record.content_json)
        scope = dict(record.content_json.get("scope", {}))
        for previous in self.configurations():
            if (
                previous.id != record.id
                and previous.status == "published"
                and previous.code == record.code
                and dict(previous.content_json.get("scope", {})) == scope
            ):
                previous.status = "superseded"
                previous.version += 1
        record.status = "published"
        record.version += 1
        record.content_hash = _hash(record.content_json)
        self._event("portfolio_resource.configuration_published", "AdminConfiguration", record.id, {})
        self.db.commit()
        return record

    # Snapshot, aggregation and readiness ---------------------------
    def _snapshot_analysis_rows(
        self,
        scenario: PortfolioResourceScenario,
        rows: list[PortfolioAnalysisRowOut],
        *,
        select_priority: bool,
    ) -> None:
        for source in rows:
            profile = self._published_demand(source.project_workspace_id)
            state = "SELECTED" if select_priority else "UNSELECTED"
            row = PortfolioResourceScenarioProject(
                tenant_id=self.tenant_id,
                scenario_id=scenario.id,
                project_workspace_id=source.project_workspace_id,
                portfolio_membership_id=source.portfolio_membership_id,
                project_number=source.project_number,
                project_name=source.project_name,
                portfolio_evaluation_score=source.portfolio_evaluation_score,
                portfolio_rank=source.portfolio_rank,
                strategic_alignment_score=source.strategic_alignment_score,
                risk_score=source.risk_score,
                risk_bucket=source.risk_bucket,
                gate07f_analysis_hash=scenario.source_analysis_hash,
                resource_demand_profile_id=profile.id if profile else None,
                resource_demand_hash=profile.demand_hash if profile else "",
                source_project_start=source.target_start,
                source_project_finish=source.target_finish,
                scenario_start=source.target_start,
                scenario_finish=source.target_finish,
                schedule_shift_days=0,
                timing_method="NO_SHIFT",
                selection_state=state,
                row_hash="",
                updated_by=self.actor_id,
            )
            self.db.add(row)
            self.db.flush()
            row.row_hash = self._row_hash(row)

    def _copy_scenario_rows(self, source_id: int, target_id: int) -> None:
        for source in self._scenario_rows(source_id):
            row = PortfolioResourceScenarioProject(
                tenant_id=self.tenant_id,
                scenario_id=target_id,
                project_workspace_id=source.project_workspace_id,
                portfolio_membership_id=source.portfolio_membership_id,
                project_number=source.project_number,
                project_name=source.project_name,
                portfolio_evaluation_score=source.portfolio_evaluation_score,
                portfolio_rank=source.portfolio_rank,
                strategic_alignment_score=source.strategic_alignment_score,
                risk_score=source.risk_score,
                risk_bucket=source.risk_bucket,
                gate07f_analysis_hash=source.gate07f_analysis_hash,
                resource_demand_profile_id=source.resource_demand_profile_id,
                resource_demand_hash=source.resource_demand_hash,
                source_project_start=source.source_project_start,
                source_project_finish=source.source_project_finish,
                scenario_start=source.scenario_start,
                scenario_finish=source.scenario_finish,
                schedule_shift_days=source.schedule_shift_days,
                timing_method=source.timing_method,
                selection_state=source.selection_state,
                forced_reason=source.forced_reason,
                forced_actor_id=source.forced_actor_id,
                forced_at=source.forced_at,
                forced_authority_reference=source.forced_authority_reference,
                row_hash=source.row_hash,
                updated_by=self.actor_id,
            )
            self.db.add(row)
        self.db.flush()

    def _capacity_demand(self, scenario: PortfolioResourceScenario) -> tuple[list[CapacityDemandCellOut], list[str]]:
        capacity = self._capacity(scenario.capacity_plan_id)
        capacity_periods = self._capacity_periods(capacity.id)
        rows = [item for item in self._scenario_rows(scenario.id) if self._included(item.selection_state)]
        demand: dict[tuple[str, str, str], Decimal] = {}
        demand_meta: dict[tuple[str, str, str], tuple[str, str, date, date]] = {}
        issues: list[str] = []
        for row in rows:
            if row.resource_demand_profile_id is None:
                continue
            profile = self._demand(row.resource_demand_profile_id)
            for period in self._demand_periods(profile.id):
                shifted_start = period.period_start + timedelta(days=row.schedule_shift_days)
                shifted_end = period.period_end + timedelta(days=row.schedule_shift_days)
                matches = [
                    item
                    for item in capacity_periods
                    if item.resource_role_key == period.resource_role_key
                    and item.period_start <= shifted_start <= item.period_end
                ]
                if not matches:
                    key = (period.resource_role_key, period.period_key, period.unit)
                    demand[key] = demand.get(key, Decimal("0")) + Decimal(period.demand_value)
                    demand_meta[key] = (
                        period.resource_role_name,
                        period.role_category,
                        shifted_start,
                        shifted_end,
                    )
                    continue
                target = matches[0]
                if target.unit != period.unit:
                    issues.append(
                        f"UNIT_MISMATCH:{period.resource_role_key}:{target.period_key}:{target.unit}:{period.unit}"
                    )
                    continue
                key = (target.resource_role_key, target.period_key, target.unit)
                demand[key] = demand.get(key, Decimal("0")) + Decimal(period.demand_value)
        cells: list[CapacityDemandCellOut] = []
        seen: set[tuple[str, str, str]] = set()
        for period in capacity_periods:
            key = (period.resource_role_key, period.period_key, period.unit)
            selected = demand.get(key, Decimal("0"))
            capacity_value = Decimal(period.capacity_value)
            utilization = _ratio(selected, capacity_value)
            status = (
                "NO_CAPACITY_DEFINED"
                if capacity_value == 0 and selected > 0
                else "OVERLOADED"
                if selected > capacity_value
                else "AT_CAPACITY"
                if selected == capacity_value and capacity_value > 0
                else "AVAILABLE"
            )
            cells.append(
                CapacityDemandCellOut(
                    resource_role_key=period.resource_role_key,
                    resource_role_name=period.resource_role_name,
                    role_category=period.role_category,
                    period_key=period.period_key,
                    period_start=period.period_start,
                    period_end=period.period_end,
                    unit=period.unit,
                    capacity=capacity_value,
                    selected_demand=selected,
                    variance=capacity_value - selected,
                    utilization_percent=utilization,
                    status=status,
                )
            )
            seen.add(key)
        for key in sorted(demand.keys() - seen):
            name, category, start, finish = demand_meta[key]
            selected = demand[key]
            cells.append(
                CapacityDemandCellOut(
                    resource_role_key=key[0],
                    resource_role_name=name,
                    role_category=category,
                    period_key=key[1],
                    period_start=start,
                    period_end=finish,
                    unit=key[2],
                    capacity=Decimal("0"),
                    selected_demand=selected,
                    variance=-selected,
                    utilization_percent=None,
                    status="NO_CAPACITY_DEFINED",
                )
            )
        return sorted(cells, key=lambda item: (item.resource_role_key, item.period_start, item.period_key)), sorted(set(issues))

    def _scenario_out(self, record: PortfolioResourceScenario) -> ResourceScenarioOut:
        rows = self._scenario_rows(record.id)
        projects = [self._project_out(item) for item in rows]
        heatmap, unit_issues = self._capacity_demand(record)
        summary = self._summary(projects, heatmap)
        readiness = self._scenario_readiness(record, historical=record.status == "FROZEN", summary=summary, unit_issues=unit_issues)
        return ResourceScenarioOut(
            id=record.id,
            tenant_id=record.tenant_id,
            portfolio_workspace_id=record.portfolio_workspace_id,
            logical_code=record.logical_code,
            scenario_name=record.scenario_name,
            description=record.description,
            status=record.status,
            capacity_plan_id=record.capacity_plan_id,
            capacity_plan_hash=record.capacity_plan_hash,
            source_analysis_hash=record.source_analysis_hash,
            source_hash=record.source_hash,
            scenario_hash=record.scenario_hash,
            creation_mode=record.creation_mode,
            overload_policy=record.overload_policy,
            scenario_revision=record.scenario_revision,
            revision_version=record.revision_version,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_by=record.updated_by,
            updated_at=record.updated_at,
            frozen_at=record.frozen_at,
            voided_at=record.voided_at,
            projects=projects,
            heatmap=heatmap,
            summary=summary,
            readiness=readiness,
            warnings=readiness.warnings,
            blockers=readiness.blockers,
            allowed_actions=self._scenario_actions(record, readiness),
        )

    @staticmethod
    def _project_out(row: PortfolioResourceScenarioProject) -> ScenarioProjectOut:
        return ScenarioProjectOut(
            id=row.id,
            project_workspace_id=row.project_workspace_id,
            portfolio_membership_id=row.portfolio_membership_id,
            project_number=row.project_number,
            project_name=row.project_name,
            portfolio_evaluation_score=row.portfolio_evaluation_score,
            portfolio_rank=row.portfolio_rank,
            strategic_alignment_score=row.strategic_alignment_score,
            risk_score=row.risk_score,
            risk_bucket=row.risk_bucket,
            gate07f_analysis_hash=row.gate07f_analysis_hash,
            resource_demand_profile_id=row.resource_demand_profile_id,
            resource_demand_hash=row.resource_demand_hash,
            source_project_start=row.source_project_start,
            source_project_finish=row.source_project_finish,
            scenario_start=row.scenario_start,
            scenario_finish=row.scenario_finish,
            schedule_shift_days=row.schedule_shift_days,
            timing_method=row.timing_method,
            selection_state=row.selection_state,
            forced_reason=row.forced_reason,
            forced_actor_id=row.forced_actor_id,
            forced_at=row.forced_at,
            forced_authority_reference=row.forced_authority_reference,
            demand_covered=bool(row.resource_demand_profile_id and row.resource_demand_hash),
            revision_version=row.revision_version,
        )

    @staticmethod
    def _summary(
        projects: list[ScenarioProjectOut], heatmap: list[CapacityDemandCellOut]
    ) -> ResourceScenarioSummaryOut:
        selected = [item for item in projects if PortfolioResourceService._included(item.selection_state)]
        utilizations = [item.utilization_percent for item in heatmap if item.utilization_percent is not None]
        overloaded = [item for item in heatmap if item.status in {"OVERLOADED", "NO_CAPACITY_DEFINED"} and item.selected_demand > 0]
        covered = [item for item in selected if item.demand_covered]
        return ResourceScenarioSummaryOut(
            selected_count=len(selected),
            unselected_count=sum(item.selection_state == "UNSELECTED" for item in projects),
            forced_in_count=sum(item.selection_state == "FORCED_IN" for item in projects),
            forced_out_count=sum(item.selection_state == "FORCED_OUT" for item in projects),
            average_score=_average([Decimal(item.portfolio_evaluation_score) for item in selected]),
            high_risk_count=sum(item.risk_bucket == "HIGH" for item in selected),
            overloaded_role_count=len({item.resource_role_key for item in overloaded}),
            overloaded_period_count=len({(item.resource_role_key, item.period_key) for item in overloaded}),
            peak_overload=max((max(Decimal("0"), -item.variance) for item in overloaded), default=Decimal("0")),
            peak_utilization=max(utilizations, default=None),
            average_utilization=_average([Decimal(item) for item in utilizations]),
            demand_coverage_percent=_percent(len(covered), len(selected)),
        )

    def _scenario_readiness(
        self,
        record: PortfolioResourceScenario,
        *,
        historical: bool,
        summary: ResourceScenarioSummaryOut | None = None,
        unit_issues: list[str] | None = None,
    ) -> ResourceScenarioReadinessOut:
        heatmap, calculated_unit_issues = self._capacity_demand(record)
        projects = [self._project_out(item) for item in self._scenario_rows(record.id)]
        summary = summary or self._summary(projects, heatmap)
        unit_issues = unit_issues if unit_issues is not None else calculated_unit_issues
        policy = self._policy(record.portfolio_workspace_id, require_published=False)
        warnings: list[str] = []
        blockers: list[str] = []
        source_current = True
        if not historical:
            try:
                current = self._current_source_hash(record)
                source_current = current == record.source_hash
            except HTTPException:
                source_current = False
            if not source_current:
                blockers.append("STALE_PORTFOLIO_RESOURCE_SOURCE")
        else:
            warnings.append("FROZEN_HISTORICAL_SOURCE_PRESERVED")
        required = Decimal(str(policy.get("required_demand_coverage_percent", 100)))
        if summary.selected_count == 0:
            blockers.append("SELECTED_PROJECT_REQUIRED")
        if summary.demand_coverage_percent < required:
            blockers.append("INSUFFICIENT_RESOURCE_DEMAND_COVERAGE")
        blockers.extend(unit_issues)
        if any(
            item.selection_state in {"FORCED_IN", "FORCED_OUT"} and not (item.forced_reason or "").strip()
            for item in projects
        ):
            blockers.append("FORCED_REASON_REQUIRED")
        if any(
            item.scenario_start and item.scenario_finish and item.scenario_finish < item.scenario_start
            for item in projects
        ):
            blockers.append("INVALID_SCENARIO_DATES")
        if summary.overloaded_period_count:
            if record.overload_policy == "BLOCK_READY_STATE":
                blockers.append("RESOURCE_OVERLOAD_BLOCKS_READY_STATE")
            else:
                warnings.append("RESOURCE_OVERLOAD_PRESENT")
        if any(item.resource_demand_profile_id is None for item in projects if self._included(item.selection_state)):
            warnings.append("MISSING_DEMAND_NOT_FABRICATED")
        status = "STALE" if not source_current and not historical else "BLOCKED" if blockers else "READY"
        return ResourceScenarioReadinessOut(
            status=status,
            source_current=source_current,
            demand_coverage_percent=summary.demand_coverage_percent,
            warnings=sorted(set(warnings)),
            blockers=sorted(set(blockers)),
        )

    def _refresh_delta(
        self, record: PortfolioResourceScenario
    ) -> tuple[ScenarioRefreshPreviewOut, PortfolioAnalysisOverviewOut]:
        analysis = self._analysis(record.portfolio_workspace_id, require_resource=True)
        old = {item.project_workspace_id: item for item in self._scenario_rows(record.id)}
        current = {item.project_workspace_id: item for item in analysis.dataset.rows}
        demand_changes: list[dict] = []
        date_changes: list[dict] = []
        for project_id in sorted(old.keys() & current.keys()):
            before, after = old[project_id], current[project_id]
            profile = self._published_demand(project_id)
            new_hash = profile.demand_hash if profile else ""
            if before.resource_demand_hash != new_hash:
                demand_changes.append({"project_id": project_id, "before": before.resource_demand_hash, "after": new_hash})
            if before.source_project_start != after.target_start or before.source_project_finish != after.target_finish:
                date_changes.append(
                    {
                        "project_id": project_id,
                        "before": [before.source_project_start, before.source_project_finish],
                        "after": [after.target_start, after.target_finish],
                    }
                )
        proposed = self._source_hash_from_analysis(record, analysis)
        return (
            ScenarioRefreshPreviewOut(
                scenario_id=record.id,
                current_source_hash=record.source_hash,
                proposed_source_hash=proposed,
                projects_added=sorted(current.keys() - old.keys()),
                projects_removed=sorted(old.keys() - current.keys()),
                demand_profile_changes=demand_changes,
                date_changes=date_changes,
                persisted=False,
            ),
            analysis,
        )

    def _recalculate_scenario(self, record: PortfolioResourceScenario) -> None:
        rows = self._scenario_rows(record.id)
        heatmap, _ = self._capacity_demand(record)
        record.scenario_hash = _hash(
            {
                "source_hash": record.source_hash,
                "status": record.status,
                "capacity_plan_hash": record.capacity_plan_hash,
                "overload_policy": record.overload_policy,
                "rows": [
                    {
                        "project": item.project_workspace_id,
                        "selection": item.selection_state,
                        "timing": item.timing_method,
                        "scenario_dates": [item.scenario_start, item.scenario_finish],
                        "row_hash": item.row_hash,
                    }
                    for item in rows
                ],
                "capacity_demand": [item.model_dump(mode="json") for item in heatmap],
            }
        )

    # Validation and hashing ----------------------------------------
    def _analysis(
        self,
        portfolio_id: int,
        *,
        require_resource: bool,
        expected_hash: str | None = None,
    ) -> PortfolioAnalysisOverviewOut:
        analysis = PortfolioAnalysisService(self.db, self.tenant_id, self.actor_id, self.context).overview(
            portfolio_id, AnalysisFiltersIn()
        )
        if expected_hash is not None and analysis.dataset.analysis_hash != expected_hash:
            self._event(
                "portfolio_resource.stale_source_detected",
                "EnterpriseWorkspace",
                portfolio_id,
                {"expected": expected_hash, "actual": analysis.dataset.analysis_hash},
            )
            self.db.commit()
            raise HTTPException(
                status_code=412,
                detail={
                    "code": "STALE_PORTFOLIO_RESOURCE_SOURCE",
                    "expected": expected_hash,
                    "actual": analysis.dataset.analysis_hash,
                },
            )
        if require_resource and (
            analysis.readiness.final_output != READY_INPUT or not analysis.readiness.can_enter_resource_planning
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PORTFOLIO_RESOURCE_PLANNING_NOT_ELIGIBLE",
                    "warnings": analysis.readiness.warnings,
                    "blockers": analysis.readiness.blockers,
                    "budget_branch_required": False,
                },
            )
        return analysis

    def _validate_capacity_payload(self, payload, policy: dict) -> None:
        allowed_units = set(policy.get("allowed_units", []))
        if any(item.unit not in allowed_units for item in payload.periods):
            raise HTTPException(status_code=422, detail={"code": "CAPACITY_UNIT_NOT_ALLOWED"})
        keys = [(item.resource_role_key, item.period_key) for item in payload.periods]
        if len(keys) != len(set(keys)):
            raise HTTPException(status_code=422, detail={"code": "DUPLICATE_CAPACITY_ROLE_PERIOD"})
        if any(
            item.period_start < payload.planning_horizon_start or item.period_end > payload.planning_horizon_end
            for item in payload.periods
        ):
            raise HTTPException(status_code=422, detail={"code": "CAPACITY_PERIOD_OUTSIDE_HORIZON"})

    def _validate_demand_payload(self, payload, policy: dict) -> None:
        if payload.source_type not in set(policy.get("allowed_demand_source_types", [])):
            raise HTTPException(status_code=422, detail={"code": "DEMAND_SOURCE_TYPE_NOT_ALLOWED"})
        allowed_units = set(policy.get("allowed_units", []))
        if any(item.unit not in allowed_units for item in payload.periods):
            raise HTTPException(status_code=422, detail={"code": "DEMAND_UNIT_NOT_ALLOWED"})
        keys = [(item.resource_role_key, item.period_key) for item in payload.periods]
        if len(keys) != len(set(keys)):
            raise HTTPException(status_code=422, detail={"code": "DUPLICATE_DEMAND_ROLE_PERIOD"})
        if any(
            item.period_start < payload.planning_start or item.period_end > payload.planning_finish
            for item in payload.periods
        ):
            raise HTTPException(status_code=422, detail={"code": "DEMAND_PERIOD_OUTSIDE_HORIZON"})

    def _replace_capacity_periods(self, plan: PortfolioResourceCapacityPlan, periods) -> None:
        self.db.execute(
            delete(PortfolioResourceCapacityPeriod).where(
                PortfolioResourceCapacityPeriod.tenant_id == self.tenant_id,
                PortfolioResourceCapacityPeriod.capacity_plan_id == plan.id,
            )
        )
        for item in periods:
            self.db.add(
                PortfolioResourceCapacityPeriod(
                    tenant_id=self.tenant_id,
                    capacity_plan_id=plan.id,
                    **item.model_dump(),
                )
            )
        self.db.flush()

    def _replace_demand_periods(self, profile: ProjectResourceDemandProfile, periods) -> None:
        self.db.execute(
            delete(ProjectResourceDemandPeriod).where(
                ProjectResourceDemandPeriod.tenant_id == self.tenant_id,
                ProjectResourceDemandPeriod.demand_profile_id == profile.id,
            )
        )
        for item in periods:
            self.db.add(
                ProjectResourceDemandPeriod(
                    tenant_id=self.tenant_id,
                    demand_profile_id=profile.id,
                    **item.model_dump(),
                )
            )
        self.db.flush()

    def _capacity_hash(self, plan: PortfolioResourceCapacityPlan) -> str:
        return _hash(
            {
                "portfolio": plan.portfolio_workspace_id,
                "revision": plan.plan_revision,
                "horizon": [plan.planning_horizon_start, plan.planning_horizon_end],
                "granularity": plan.period_granularity,
                "source_reference": plan.source_reference,
                "periods": [
                    {
                        "role": item.resource_role_key,
                        "period": item.period_key,
                        "value": str(item.capacity_value),
                        "unit": item.unit,
                        "dates": [item.period_start, item.period_end],
                    }
                    for item in self._capacity_periods(plan.id)
                ],
            }
        )

    def _demand_hash(self, profile: ProjectResourceDemandProfile) -> str:
        return _hash(
            {
                "project": profile.project_workspace_id,
                "revision": profile.profile_revision,
                "source_hash": profile.source_hash,
                "generation_method": profile.generation_method,
                "dates": [profile.planning_start, profile.planning_finish],
                "periods": [
                    {
                        "role": item.resource_role_key,
                        "period": item.period_key,
                        "value": str(item.demand_value),
                        "unit": item.unit,
                        "dates": [item.period_start, item.period_end],
                    }
                    for item in self._demand_periods(profile.id)
                ],
            }
        )

    def _source_hash(
        self,
        scenario: PortfolioResourceScenario,
        capacity: PortfolioResourceCapacityPlan,
        rows: list[PortfolioResourceScenarioProject],
    ) -> str:
        return _hash(
            {
                "analysis_hash": scenario.source_analysis_hash,
                "prioritization_hash": scenario.source_prioritization_hash,
                "membership_set_hash": scenario.membership_set_hash,
                "evaluation_set_hash": scenario.evaluation_set_hash,
                "configuration_hash": scenario.source_configuration_hash,
                "capacity_plan_hash": capacity.capacity_hash,
                "demand_hashes": sorted((item.project_workspace_id, item.resource_demand_hash) for item in rows),
                "source_project_dates": sorted(
                    (item.project_workspace_id, item.source_project_start, item.source_project_finish) for item in rows
                ),
            }
        )

    def _source_hash_from_analysis(
        self, scenario: PortfolioResourceScenario, analysis: PortfolioAnalysisOverviewOut
    ) -> str:
        capacity = self._capacity(scenario.capacity_plan_id)
        demand_hashes = [
            (item.project_workspace_id, (self._published_demand(item.project_workspace_id) or _EmptyDemand()).demand_hash)
            for item in analysis.dataset.rows
        ]
        return _hash(
            {
                "analysis_hash": analysis.dataset.analysis_hash,
                "prioritization_hash": analysis.dataset.source_prioritization_hash,
                "membership_set_hash": analysis.dataset.membership_set_hash,
                "evaluation_set_hash": analysis.dataset.evaluation_set_hash,
                "configuration_hash": _hash(
                    self._policy(scenario.portfolio_workspace_id, require_published=False)
                ),
                "capacity_plan_hash": capacity.capacity_hash,
                "demand_hashes": sorted(demand_hashes),
                "source_project_dates": sorted(
                    (item.project_workspace_id, item.target_start, item.target_finish) for item in analysis.dataset.rows
                ),
            }
        )

    def _current_source_hash(self, scenario: PortfolioResourceScenario) -> str:
        analysis = self._analysis(scenario.portfolio_workspace_id, require_resource=False)
        return self._source_hash_from_analysis(scenario, analysis)

    @staticmethod
    def _row_hash(row: PortfolioResourceScenarioProject) -> str:
        return _hash(
            {
                "project": row.project_workspace_id,
                "rank": row.portfolio_rank,
                "score": str(row.portfolio_evaluation_score),
                "analysis_hash": row.gate07f_analysis_hash,
                "demand_hash": row.resource_demand_hash,
                "source_dates": [row.source_project_start, row.source_project_finish],
                "scenario_dates": [row.scenario_start, row.scenario_finish],
                "selection": row.selection_state,
                "forced_reason": row.forced_reason,
            }
        )

    # Persistence projections ---------------------------------------
    def _capacity_out(self, record: PortfolioResourceCapacityPlan) -> CapacityPlanOut:
        return CapacityPlanOut(
            id=record.id,
            tenant_id=record.tenant_id,
            portfolio_workspace_id=record.portfolio_workspace_id,
            logical_code=record.logical_code,
            plan_name=record.plan_name,
            planning_horizon_start=record.planning_horizon_start,
            planning_horizon_end=record.planning_horizon_end,
            period_granularity=record.period_granularity,
            status=record.status,
            plan_revision=record.plan_revision,
            source_reference=record.source_reference,
            notes=record.notes,
            capacity_hash=record.capacity_hash,
            revision_version=record.revision_version,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_by=record.updated_by,
            updated_at=record.updated_at,
            published_at=record.published_at,
            periods=[CapacityPeriodOut.model_validate(item) for item in self._capacity_periods(record.id)],
        )

    def _demand_out(self, record: ProjectResourceDemandProfile) -> DemandProfileOut:
        return DemandProfileOut(
            id=record.id,
            tenant_id=record.tenant_id,
            project_workspace_id=record.project_workspace_id,
            logical_code=record.logical_code,
            profile_name=record.profile_name,
            status=record.status,
            profile_revision=record.profile_revision,
            source_type=record.source_type,
            source_reference=record.source_reference,
            source_hash=record.source_hash,
            as_of_date=record.as_of_date,
            planning_start=record.planning_start,
            planning_finish=record.planning_finish,
            generation_method=record.generation_method,
            approximation=record.approximation,
            demand_hash=record.demand_hash,
            revision_version=record.revision_version,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_by=record.updated_by,
            updated_at=record.updated_at,
            published_at=record.published_at,
            periods=[DemandPeriodOut.model_validate(item) for item in self._demand_periods(record.id)],
        )

    def _capacity(self, plan_id: int | None, *, lock: bool = False) -> PortfolioResourceCapacityPlan:
        statement = select(PortfolioResourceCapacityPlan).where(
            PortfolioResourceCapacityPlan.id == plan_id,
            PortfolioResourceCapacityPlan.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Portfolio Resource Capacity Plan not found")
        self._assert_scope(record.portfolio_workspace_id)
        return record

    def _demand(self, profile_id: int | None, *, lock: bool = False) -> ProjectResourceDemandProfile:
        statement = select(ProjectResourceDemandProfile).where(
            ProjectResourceDemandProfile.id == profile_id,
            ProjectResourceDemandProfile.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Project Resource Demand Profile not found")
        self._assert_scope(record.project_workspace_id)
        return record

    def _scenario(self, scenario_id: int | None, *, lock: bool = False) -> PortfolioResourceScenario:
        statement = select(PortfolioResourceScenario).where(
            PortfolioResourceScenario.id == scenario_id,
            PortfolioResourceScenario.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Portfolio Resource Scenario not found")
        self._assert_scope(record.portfolio_workspace_id)
        return record

    def _capacity_records(self, portfolio_id: int) -> list[PortfolioResourceCapacityPlan]:
        return list(
            self.db.scalars(
                select(PortfolioResourceCapacityPlan)
                .where(
                    PortfolioResourceCapacityPlan.tenant_id == self.tenant_id,
                    PortfolioResourceCapacityPlan.portfolio_workspace_id == portfolio_id,
                )
                .order_by(PortfolioResourceCapacityPlan.plan_revision.desc())
            ).all()
        )

    def _capacity_periods(self, plan_id: int) -> list[PortfolioResourceCapacityPeriod]:
        return list(
            self.db.scalars(
                select(PortfolioResourceCapacityPeriod)
                .where(
                    PortfolioResourceCapacityPeriod.tenant_id == self.tenant_id,
                    PortfolioResourceCapacityPeriod.capacity_plan_id == plan_id,
                )
                .order_by(
                    PortfolioResourceCapacityPeriod.resource_role_key,
                    PortfolioResourceCapacityPeriod.period_start,
                )
            ).all()
        )

    def _demand_records(self, project_id: int) -> list[ProjectResourceDemandProfile]:
        return list(
            self.db.scalars(
                select(ProjectResourceDemandProfile)
                .where(
                    ProjectResourceDemandProfile.tenant_id == self.tenant_id,
                    ProjectResourceDemandProfile.project_workspace_id == project_id,
                )
                .order_by(ProjectResourceDemandProfile.profile_revision.desc())
            ).all()
        )

    def _demand_periods(self, profile_id: int) -> list[ProjectResourceDemandPeriod]:
        return list(
            self.db.scalars(
                select(ProjectResourceDemandPeriod)
                .where(
                    ProjectResourceDemandPeriod.tenant_id == self.tenant_id,
                    ProjectResourceDemandPeriod.demand_profile_id == profile_id,
                )
                .order_by(ProjectResourceDemandPeriod.resource_role_key, ProjectResourceDemandPeriod.period_start)
            ).all()
        )

    def _published_demand(self, project_id: int) -> ProjectResourceDemandProfile | None:
        return self.db.scalar(
            select(ProjectResourceDemandProfile)
            .where(
                ProjectResourceDemandProfile.tenant_id == self.tenant_id,
                ProjectResourceDemandProfile.project_workspace_id == project_id,
                ProjectResourceDemandProfile.status == "PUBLISHED",
            )
            .order_by(ProjectResourceDemandProfile.profile_revision.desc())
        )

    def _scenario_records(self, portfolio_id: int) -> list[PortfolioResourceScenario]:
        return list(
            self.db.scalars(
                select(PortfolioResourceScenario)
                .where(
                    PortfolioResourceScenario.tenant_id == self.tenant_id,
                    PortfolioResourceScenario.portfolio_workspace_id == portfolio_id,
                )
                .order_by(PortfolioResourceScenario.created_at.desc(), PortfolioResourceScenario.id.desc())
            ).all()
        )

    def _scenario_rows(self, scenario_id: int) -> list[PortfolioResourceScenarioProject]:
        return list(
            self.db.scalars(
                select(PortfolioResourceScenarioProject)
                .where(
                    PortfolioResourceScenarioProject.tenant_id == self.tenant_id,
                    PortfolioResourceScenarioProject.scenario_id == scenario_id,
                )
                .order_by(
                    PortfolioResourceScenarioProject.portfolio_rank,
                    PortfolioResourceScenarioProject.project_workspace_id,
                )
            ).all()
        )

    # Configuration inheritance and safeguards ----------------------
    def _configuration_issues(self, content: dict) -> list[str]:
        issues: list[str] = []
        if content.get("applicable_governance_models") != ["CAPITAL_OWNER"]:
            issues.append("CAPITAL_OWNER_ONLY_REQUIRED")
        allowed_units = set(content.get("allowed_units", []))
        if not allowed_units or not allowed_units <= {"FTE", "HOURS", "CREW_EQUIVALENT"}:
            issues.append("INVALID_CAPACITY_UNITS")
        if content.get("default_unit") not in allowed_units:
            issues.append("DEFAULT_UNIT_NOT_ALLOWED")
        if content.get("period_granularity") not in {"YEAR", "QUARTER", "MONTH"}:
            issues.append("INVALID_PERIOD_GRANULARITY")
        if content.get("overload_policy") not in {"ALLOW_WITH_WARNING", "BLOCK_READY_STATE"}:
            issues.append("INVALID_OVERLOAD_POLICY")
        coverage = content.get("required_demand_coverage_percent")
        if not isinstance(coverage, (int, float)) or not 0 <= coverage <= 100:
            issues.append("INVALID_DEMAND_COVERAGE")
        if not content.get("resource_roles"):
            issues.append("RESOURCE_ROLE_CATALOG_REQUIRED")
        serialized = json.dumps(content, sort_keys=True).lower()
        forbidden = {
            "named_resource",
            "employee",
            "person_assignment",
            "timesheet",
            "resource_leveling",
            "optimizer",
            "cpm_reschedule",
            "p6_activity",
            "funding_assignment",
            "investment_approval",
            "fid_approval",
            "budget_target_mutation",
        }
        if any(term in serialized for term in forbidden):
            issues.append("DOWNSTREAM_OR_OPERATIONAL_CAPABILITY_NOT_ALLOWED_IN_GATE07H")
        return sorted(set(issues))

    def _validate_configuration(self, content: dict) -> None:
        issues = self._configuration_issues(content)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION", "issues": issues})

    def _policy(self, portfolio_id: int, *, require_published: bool) -> dict:
        workspace = self._portfolio(portfolio_id)
        record = self._effective_configuration(workspace, published_only=True)
        if record is None:
            if require_published:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "PUBLISHED_PORTFOLIO_RESOURCE_CONFIGURATION_REQUIRED"},
                )
            return deepcopy(DEFAULT_CONFIGURATION)
        content = deepcopy(record.content_json or {})
        self._validate_configuration(content)
        return content

    def _tenant_policy(self, *, require_published: bool) -> dict:
        record = self._effective_configuration(None, published_only=True)
        if record is None:
            if require_published:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "PUBLISHED_PORTFOLIO_RESOURCE_CONFIGURATION_REQUIRED"},
                )
            return deepcopy(DEFAULT_CONFIGURATION)
        content = deepcopy(record.content_json or {})
        self._validate_configuration(content)
        return content

    def _effective_configuration(
        self, workspace: EnterpriseWorkspace | None, *, published_only: bool
    ) -> AdminConfiguration | None:
        records = list(
            self.db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    *([AdminConfiguration.status == "published"] if published_only else []),
                )
            ).all()
        )
        path = self._workspace_path(workspace) if workspace else []
        path_ids = {item.id: item for item in path}
        candidates: list[tuple[int, int, AdminConfiguration]] = []
        for record in records:
            scope = dict((record.content_json or {}).get("scope", {}))
            scope_type = str(scope.get("type") or "tenant")
            scope_id = scope.get("workspace_id")
            specificity = 0
            if scope_type != "tenant":
                if scope_id not in path_ids:
                    continue
                expected = {
                    "enterprise": "enterprise",
                    "business-unit": "business-unit",
                    "portfolio": "portfolio",
                }.get(scope_type)
                if expected and path_ids[int(scope_id)].workspace_type_code != expected:
                    continue
                specificity = {"enterprise": 1, "business-unit": 2, "portfolio": 3}.get(scope_type, 0)
            candidates.append((specificity, record.revision, record))
        return max(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None

    def _configuration(self, configuration_id: int | None, *, lock: bool = False) -> AdminConfiguration:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.id == configuration_id,
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Portfolio Resource configuration not found")
        return record

    # Workspace, actions and audit ----------------------------------
    def _portfolio(self, portfolio_id: int | None) -> EnterpriseWorkspace:
        workspace = self._workspace(portfolio_id)
        if workspace.workspace_type_code != "portfolio":
            raise HTTPException(status_code=422, detail={"code": "WORKSPACE_IS_NOT_PORTFOLIO"})
        return workspace

    def _project(self, project_id: int | None) -> EnterpriseWorkspace:
        workspace = self._workspace(project_id)
        if workspace.workspace_type_code != "project":
            raise HTTPException(status_code=422, detail={"code": "WORKSPACE_IS_NOT_PROJECT"})
        project_context = dict(dict(workspace.defaults_json or {}).get("_project", {}))
        governance = str(project_context.get("governance_model") or "").upper()
        if not governance and project_context.get("planning_origin") == "STRATEGIC_GATE":
            governance = "CAPITAL_OWNER"
        if governance != "CAPITAL_OWNER":
            raise HTTPException(status_code=409, detail={"code": "CAPITAL_OWNER_RESOURCE_PLANNING_REQUIRED"})
        return workspace

    def _workspace(self, workspace_id: int | None) -> EnterpriseWorkspace:
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == workspace_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
            )
        )
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        self._assert_scope(workspace.id)
        return workspace

    @staticmethod
    def _check_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise HTTPException(status_code=412, detail={"code": "ETAG_MISMATCH"})

    @staticmethod
    def _assert_scenario_editable(record: PortfolioResourceScenario) -> None:
        if record.status not in {"DRAFT", "IN_REVIEW"}:
            raise HTTPException(status_code=409, detail={"code": "FROZEN_RESOURCE_SCENARIO_IMMUTABLE"})

    def _touch_scenario(self, record: PortfolioResourceScenario) -> None:
        record.updated_at = utc_now()
        record.updated_by = self.actor_id
        record.revision_version += 1

    @staticmethod
    def _included(selection_state: str) -> bool:
        return selection_state in {"SELECTED", "FORCED_IN"}

    @staticmethod
    def _allowed_actions(can_enter: bool, can_recommend: bool) -> list[str]:
        actions = ["can_view_resource_planning", "can_compare_resource_scenarios"]
        if can_enter:
            actions.extend(
                [
                    "can_create_capacity_plan",
                    "can_publish_capacity_plan",
                    "can_create_demand_profile",
                    "can_publish_demand_profile",
                    "can_create_resource_scenario",
                    "can_edit_resource_scenario",
                    "can_clone_resource_scenario",
                    "can_freeze_resource_scenario",
                    "can_void_resource_scenario",
                    "can_force_in",
                    "can_force_out",
                    "can_adjust_scenario_timing",
                    "can_refresh_resource_scenario_source",
                ]
            )
        if can_recommend:
            actions.append("can_enter_resource_recommendation")
        return actions

    def _scenario_actions(
        self, record: PortfolioResourceScenario, readiness: ResourceScenarioReadinessOut
    ) -> list[str]:
        actions = ["can_view_resource_planning", "can_clone_resource_scenario", "can_compare_resource_scenarios"]
        if record.status in {"DRAFT", "IN_REVIEW"}:
            actions.extend(
                [
                    "can_edit_resource_scenario",
                    "can_void_resource_scenario",
                    "can_force_in",
                    "can_force_out",
                    "can_adjust_scenario_timing",
                    "can_refresh_resource_scenario_source",
                ]
            )
            if readiness.status == "READY":
                actions.append("can_freeze_resource_scenario")
        return actions

    def _assert_scope(self, workspace_id: int) -> None:
        if self.context is None or self.context.organization_wide:
            return
        if workspace_id not in self.context.workspace_ids:
            raise HTTPException(status_code=403, detail="Workspace is outside the authorized scope")

    def _workspace_path(self, workspace: EnterpriseWorkspace | None) -> list[EnterpriseWorkspace]:
        if workspace is None:
            return []
        path = [workspace]
        visited = {workspace.id}
        current = workspace
        while current.parent_id is not None:
            parent = self.db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id == current.parent_id,
                )
            )
            if parent is None or parent.id in visited:
                break
            path.append(parent)
            visited.add(parent.id)
            current = parent
        return list(reversed(path))

    @staticmethod
    def _workspace_summary(workspace: EnterpriseWorkspace) -> dict:
        return {
            "id": workspace.id,
            "code": workspace.code,
            "name": workspace.name,
            "workspace_type_code": workspace.workspace_type_code,
            "parent_id": workspace.parent_id,
        }

    def _emit_readiness_change(self, portfolio_id: int) -> None:
        readiness = self.readiness(portfolio_id)
        self._event(
            "portfolio_resource.readiness_evaluated",
            "EnterpriseWorkspace",
            portfolio_id,
            {"final_output": readiness.final_output, "hash": readiness.resource_planning_hash},
        )

    def _event(self, event_type: str, target_type: str, target_id: int | None, metadata: dict) -> None:
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


class _EmptyDemand:
    demand_hash = ""


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _average(values: list[Decimal]) -> Decimal | None:
    return (
        (sum(values, Decimal("0")) / Decimal(len(values))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if values
        else None
    )


def _percent(value: int, total: int) -> Decimal:
    return (
        (Decimal(value) * Decimal("100") / Decimal(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total
        else Decimal("0")
    )


def _ratio(demand: Decimal, capacity: Decimal) -> Decimal | None:
    if capacity == 0:
        return None
    return (demand * Decimal("100") / capacity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _decimal_or_zero(value: Decimal | None) -> Decimal:
    return Decimal(value) if value is not None else Decimal("0")
