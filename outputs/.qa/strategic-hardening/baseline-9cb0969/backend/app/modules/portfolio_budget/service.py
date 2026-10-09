"""Gate 07G governed Portfolio Budget Targets, Scenarios and comparison service."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
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
from app.modules.portfolio_budget.models import (
    PortfolioBudgetScenario,
    PortfolioBudgetScenarioProject,
    PortfolioBudgetTarget,
    PortfolioBudgetTargetPeriod,
    ProjectDependency,
)
from app.modules.portfolio_budget.schemas import (
    BudgetPlanningOverviewOut,
    BudgetRecommendationContractOut,
    BudgetScenarioCreateIn,
    BudgetScenarioOut,
    BudgetScenarioUpdateIn,
    BudgetTargetCreateIn,
    BudgetTargetOut,
    BudgetTargetUpdateIn,
    ConfigurationPreviewOut,
    PortfolioBudgetPlanningReadinessOut,
    ProjectDependencyCreateIn,
    ProjectDependencyOut,
    ProjectDependencyUpdateIn,
    ScenarioComparisonOut,
    ScenarioDependencyOut,
    ScenarioPeriodOut,
    ScenarioProjectOut,
    ScenarioReadinessOut,
    ScenarioRefreshPreviewOut,
    ScenarioSelectionIn,
    ScenarioSummaryOut,
    TargetPeriodOut,
    WaterlineOut,
    WaterlineProjectOut,
)
from app.modules.portfolio_planning.models import PortfolioProjectMembership

CONFIGURATION_KIND = "portfolio_budget_configuration"
DEFAULT_CODE = "gate07g-default"
READY_INPUT = "READY_FOR_PORTFOLIO_SCENARIO_PLANNING"
READY_OUTPUT = "READY_FOR_PORTFOLIO_BUDGET_RECOMMENDATION"
REWORK_OUTPUT = "GATE07G_REWORK_REQUIRED"
VALID_SELECTION_STATES = {"SELECTED", "UNSELECTED", "FORCED_IN", "FORCED_OUT"}
VALID_TIME_METHODS = {"UNPHASED", "LINEAR_BY_PROJECT_DATES", "CUSTOM_PERIOD_PROFILE"}

DEFAULT_CONFIGURATION: dict[str, Any] = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "applicable_governance_models": ["CAPITAL_OWNER"],
    "budget_currency_policy": {"mode": "FIXED", "budget_currency": "COP", "fx_conversion": False},
    "allowed_cost_source_types": ["GATE07F_ROM_COST"],
    "cost_source_preference": ["GATE07F_ROM_COST"],
    "required_cost_coverage_percent": 100,
    "allowed_time_phasing_methods": ["UNPHASED", "LINEAR_BY_PROJECT_DATES", "CUSTOM_PERIOD_PROFILE"],
    "default_time_phasing_method": "UNPHASED",
    "period_granularity": "YEAR",
    "period_targets_must_sum_total": True,
    "scenario_max_count": 20,
    "forced_reason_required": True,
    "target_publish_four_eyes": False,
    "scenario_creator_cannot_freeze": False,
    "controlled_constraints": [
        "TOTAL_BUDGET",
        "PERIOD_BUDGET",
        "FORCED_IN_OUT",
        "MINIMUM_SCORE",
        "MAXIMUM_RISK",
        "STRATEGIC_OBJECTIVE_COVERAGE",
    ],
    "scenario_states": ["DRAFT", "IN_REVIEW", "FROZEN", "SUPERSEDED", "VOIDED"],
    "selection_states": ["SELECTED", "UNSELECTED", "FORCED_IN", "FORCED_OUT"],
    "readiness": {
        "minimum_frozen_scenarios": 1,
        "require_single_currency": True,
        "require_complete_cost_coverage": True,
        "require_period_targets": False,
    },
    "waterline": {
        "show_waterline": True,
        "default_sort": "GATE07E_RANK",
        "show_cumulative_demand": True,
        "show_forced_states": True,
        "show_dependency_status": True,
        "show_capex_expense": True,
        "default_period_view": "TOTAL",
        "waterline_warning_policy": "DISPLAY",
    },
    "dependencies": {
        "enabled": True,
        "types": [
            "PREREQUISITE",
            "ENABLING",
            "SEQUENTIAL",
            "SHARED_INFRASTRUCTURE",
            "REGULATORY",
            "FUNDING",
            "OTHER",
        ],
        "strength_values": ["MANDATORY", "OPTIONAL"],
        "mandatory_unmet_policy": "BLOCK_FREEZE",
        "max_graph_depth": 100,
    },
    "capex_expense": {
        "enabled": True,
        "allow_unclassified": True,
        "require_target_breakdown": False,
    },
}


class PortfolioBudgetService:
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

    # ------------------------------------------------------------------
    # Configuration bootstrap
    # ------------------------------------------------------------------
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
                name="Default Portfolio Budget Planning Configuration",
                description="Gate 07G starter policy. Review and publish before USER budget planning.",
                status="draft",
                revision=1,
                version=1,
                content_json=content,
                content_hash=_hash(content),
                created_by_user_id=self.actor_id,
            )
        )
        self._event("portfolio_budget.configuration_seeded_as_draft", "AdminConfiguration", None, {})
        self.db.commit()

    # ------------------------------------------------------------------
    # Budget Targets
    # ------------------------------------------------------------------
    def targets(self, portfolio_id: int) -> list[BudgetTargetOut]:
        self._portfolio(portfolio_id)
        return [self._target_out(item) for item in self._target_records(portfolio_id)]

    def target(self, target_id: int) -> BudgetTargetOut:
        return self._target_out(self._target(target_id))

    def create_target(self, portfolio_id: int, payload: BudgetTargetCreateIn) -> BudgetTargetOut:
        existing = self.db.scalar(
            select(PortfolioBudgetTarget).where(
                PortfolioBudgetTarget.tenant_id == self.tenant_id,
                PortfolioBudgetTarget.create_idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            return self._target_out(existing)
        overview = self._analysis(portfolio_id, require_budget=True)
        policy = self._policy(portfolio_id, require_published=True)
        self._validate_target_payload(payload, policy, overview)
        revision = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(PortfolioBudgetTarget.target_revision), 0)).where(
                        PortfolioBudgetTarget.tenant_id == self.tenant_id,
                        PortfolioBudgetTarget.portfolio_workspace_id == portfolio_id,
                        PortfolioBudgetTarget.target_code == "BUDGET-TARGET",
                    )
                )
                or 0
            )
            + 1
        )
        record = PortfolioBudgetTarget(
            tenant_id=self.tenant_id,
            portfolio_workspace_id=portfolio_id,
            target_code="BUDGET-TARGET",
            target_revision=revision,
            planning_horizon_start=payload.planning_horizon_start,
            planning_horizon_end=payload.planning_horizon_end,
            period_granularity=payload.period_granularity,
            budget_currency=payload.budget_currency.upper(),
            total_budget_target=payload.total_budget_target,
            capex_budget_target=payload.capex_budget_target,
            expense_budget_target=payload.expense_budget_target,
            source_reference=payload.source_reference.strip(),
            notes=payload.notes.strip(),
            status="DRAFT",
            revision_version=1,
            create_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        self._replace_periods(record, payload.periods)
        record.target_hash = self._target_hash(record)
        self._event("portfolio_budget.target_created", "PortfolioBudgetTarget", record.id, {"revision": revision})
        self.db.commit()
        self.db.refresh(record)
        return self._target_out(record)

    def update_target(
        self,
        target_id: int,
        expected_version: int,
        payload: BudgetTargetUpdateIn,
    ) -> BudgetTargetOut:
        record = self._target(target_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_BUDGET_TARGET_IMMUTABLE"})
        overview = self._analysis(record.portfolio_workspace_id, require_budget=True)
        policy = self._policy(record.portfolio_workspace_id, require_published=True)
        self._validate_target_payload(payload, policy, overview)
        record.planning_horizon_start = payload.planning_horizon_start
        record.planning_horizon_end = payload.planning_horizon_end
        record.period_granularity = payload.period_granularity
        record.budget_currency = payload.budget_currency.upper()
        record.total_budget_target = payload.total_budget_target
        record.capex_budget_target = payload.capex_budget_target
        record.expense_budget_target = payload.expense_budget_target
        record.source_reference = payload.source_reference.strip()
        record.notes = payload.notes.strip()
        record.updated_by = self.actor_id
        record.updated_at = utc_now()
        record.revision_version += 1
        self._replace_periods(record, payload.periods)
        record.target_hash = self._target_hash(record)
        self._event("portfolio_budget.target_updated", "PortfolioBudgetTarget", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._target_out(record)

    def publish_target(self, target_id: int, expected_version: int, idempotency_key: str) -> BudgetTargetOut:
        previous_retry = self.db.scalar(
            select(PortfolioBudgetTarget).where(
                PortfolioBudgetTarget.tenant_id == self.tenant_id,
                PortfolioBudgetTarget.publish_idempotency_key == idempotency_key,
            )
        )
        if previous_retry is not None:
            return self._target_out(previous_retry)
        record = self._target(target_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "BUDGET_TARGET_NOT_DRAFT"})
        overview = self._analysis(record.portfolio_workspace_id, require_budget=True)
        policy = self._policy(record.portfolio_workspace_id, require_published=True)
        self._validate_target_record(record, policy, overview)
        if policy.get("target_publish_four_eyes") and record.created_by == self.actor_id:
            raise HTTPException(status_code=409, detail={"code": "TARGET_PUBLISH_FOUR_EYES_REQUIRED"})
        current = list(
            self.db.scalars(
                select(PortfolioBudgetTarget)
                .where(
                    PortfolioBudgetTarget.tenant_id == self.tenant_id,
                    PortfolioBudgetTarget.portfolio_workspace_id == record.portfolio_workspace_id,
                    PortfolioBudgetTarget.status == "PUBLISHED",
                    PortfolioBudgetTarget.id != record.id,
                )
                .with_for_update()
            ).all()
        )
        now = utc_now()
        for item in current:
            item.status = "SUPERSEDED"
            item.updated_at = now
            item.updated_by = self.actor_id
            item.revision_version += 1
        record.status = "PUBLISHED"
        record.publish_idempotency_key = idempotency_key
        record.published_at = now
        record.updated_at = now
        record.updated_by = self.actor_id
        record.revision_version += 1
        record.target_hash = self._target_hash(record)
        self._event("portfolio_budget.target_published", "PortfolioBudgetTarget", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._target_out(record)

    # ------------------------------------------------------------------
    # Budget Scenarios
    # ------------------------------------------------------------------
    def scenarios(self, portfolio_id: int) -> list[BudgetScenarioOut]:
        self._portfolio(portfolio_id)
        records = list(
            self.db.scalars(
                select(PortfolioBudgetScenario)
                .where(
                    PortfolioBudgetScenario.tenant_id == self.tenant_id,
                    PortfolioBudgetScenario.portfolio_workspace_id == portfolio_id,
                )
                .order_by(PortfolioBudgetScenario.created_at.desc(), PortfolioBudgetScenario.id.desc())
            ).all()
        )
        overview = self._analysis(portfolio_id, require_budget=False)
        return [self._scenario_out(item, overview=overview) for item in records]

    def scenario(self, scenario_id: int) -> BudgetScenarioOut:
        record = self._scenario(scenario_id)
        return self._scenario_out(record)

    def create_scenario(self, portfolio_id: int, payload: BudgetScenarioCreateIn) -> BudgetScenarioOut:
        existing = self.db.scalar(
            select(PortfolioBudgetScenario).where(
                PortfolioBudgetScenario.tenant_id == self.tenant_id,
                PortfolioBudgetScenario.create_idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            return self._scenario_out(existing)
        overview = self._analysis(portfolio_id, require_budget=True, expected_hash=payload.expected_analysis_hash)
        policy = self._policy(portfolio_id, require_published=True)
        target = self._target(payload.budget_target_id)
        if target.portfolio_workspace_id != portfolio_id or target.status != "PUBLISHED":
            raise HTTPException(status_code=422, detail={"code": "PUBLISHED_PORTFOLIO_BUDGET_TARGET_REQUIRED"})
        count = int(
            self.db.scalar(
                select(func.count(PortfolioBudgetScenario.id)).where(
                    PortfolioBudgetScenario.tenant_id == self.tenant_id,
                    PortfolioBudgetScenario.portfolio_workspace_id == portfolio_id,
                    PortfolioBudgetScenario.status.notin_(["SUPERSEDED", "VOIDED"]),
                )
            )
            or 0
        )
        if count >= int(policy.get("scenario_max_count") or 20):
            raise HTTPException(status_code=409, detail={"code": "BUDGET_SCENARIO_LIMIT_REACHED"})
        if payload.time_phasing_method not in set(policy.get("allowed_time_phasing_methods", [])):
            raise HTTPException(status_code=422, detail={"code": "TIME_PHASING_METHOD_NOT_ALLOWED"})
        now_token = utc_now().strftime("%Y%m%d%H%M%S%f")
        logical_code = payload.scenario_code or f"BUDGET-SCENARIO-{now_token}"
        record = PortfolioBudgetScenario(
            tenant_id=self.tenant_id,
            portfolio_workspace_id=portfolio_id,
            logical_code=logical_code,
            scenario_name=payload.scenario_name.strip(),
            scenario_code=payload.scenario_code,
            description=payload.description.strip(),
            status="DRAFT",
            analytical_status="UNDER_BUDGET",
            budget_target_id=target.id,
            source_analysis_hash=overview.dataset.analysis_hash,
            source_prioritization_hash=overview.dataset.source_prioritization_hash,
            membership_set_hash=overview.dataset.membership_set_hash,
            evaluation_set_hash=overview.dataset.evaluation_set_hash,
            source_configuration_hash=overview.dataset.configuration_hash,
            budget_target_hash=target.target_hash,
            source_hash="",
            scenario_hash="",
            creation_mode=payload.creation_mode,
            time_phasing_method=payload.time_phasing_method,
            scenario_revision=1,
            revision_version=1,
            create_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        if payload.creation_mode == "COPY_EXISTING_SCENARIO":
            source = self._scenario(payload.source_scenario_id or 0)
            if source.portfolio_workspace_id != portfolio_id:
                raise HTTPException(status_code=422, detail={"code": "SOURCE_SCENARIO_PORTFOLIO_MISMATCH"})
            self._copy_rows(source.id, record.id)
            record.source_hash = self._source_hash(record, target, self._scenario_rows(record.id))
        else:
            self._snapshot_analysis_rows(record, overview.dataset.rows, target, payload.creation_mode)
        self._recalculate_scenario(record)
        self._event(
            "portfolio_budget.scenario_created",
            "PortfolioBudgetScenario",
            record.id,
            {
                "creation_mode": payload.creation_mode,
                "label": "Priority-based draft" if payload.creation_mode == "FROM_CURRENT_PRIORITY" else "",
            },
        )
        self.db.commit()
        self.db.refresh(record)
        return self._scenario_out(record)

    def update_scenario(
        self,
        scenario_id: int,
        expected_version: int,
        payload: BudgetScenarioUpdateIn,
    ) -> BudgetScenarioOut:
        record = self._scenario(scenario_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_scenario_editable(record)
        policy = self._policy(record.portfolio_workspace_id, require_published=True)
        if payload.time_phasing_method not in set(policy.get("allowed_time_phasing_methods", [])):
            raise HTTPException(status_code=422, detail={"code": "TIME_PHASING_METHOD_NOT_ALLOWED"})
        record.scenario_name = payload.scenario_name.strip()
        record.scenario_code = payload.scenario_code
        record.description = payload.description.strip()
        record.status = payload.status
        record.time_phasing_method = payload.time_phasing_method
        self._touch_scenario(record)
        self._recalculate_scenario(record)
        self._event("portfolio_budget.scenario_updated", "PortfolioBudgetScenario", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._scenario_out(record)

    def select_project(
        self,
        scenario_id: int,
        project_id: int,
        expected_version: int,
        payload: ScenarioSelectionIn,
    ) -> BudgetScenarioOut:
        record = self._scenario(scenario_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_scenario_editable(record)
        row = self.db.scalar(
            select(PortfolioBudgetScenarioProject)
            .where(
                PortfolioBudgetScenarioProject.tenant_id == self.tenant_id,
                PortfolioBudgetScenarioProject.scenario_id == scenario_id,
                PortfolioBudgetScenarioProject.project_workspace_id == project_id,
            )
            .with_for_update()
        )
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_IN_BUDGET_SCENARIO"})
        if row.last_selection_idempotency_key == payload.idempotency_key:
            return self._scenario_out(record)
        policy = self._policy(record.portfolio_workspace_id, require_published=True)
        if (
            payload.selection_state in {"FORCED_IN", "FORCED_OUT"}
            and policy.get("forced_reason_required", True)
            and not (payload.forced_reason or "").strip()
        ):
            raise HTTPException(status_code=422, detail={"code": "FORCED_STATE_REASON_REQUIRED"})
        row.selection_state = payload.selection_state
        row.period_profile_json = deepcopy(payload.period_profile)
        if payload.selection_state in {"FORCED_IN", "FORCED_OUT"}:
            row.forced_reason = (payload.forced_reason or "").strip()
            row.forced_actor_id = self.actor_id
            row.forced_at = utc_now()
            row.forced_authority_reference = payload.authority_reference
            self._event(
                "portfolio_budget.project_forced_in"
                if payload.selection_state == "FORCED_IN"
                else "portfolio_budget.project_forced_out",
                "PortfolioBudgetScenarioProject",
                row.id,
                {"reason": row.forced_reason, "authority_reference": payload.authority_reference},
            )
        else:
            row.forced_reason = None
            row.forced_actor_id = None
            row.forced_at = None
            row.forced_authority_reference = None
        row.last_selection_idempotency_key = payload.idempotency_key
        row.updated_by = self.actor_id
        row.updated_at = utc_now()
        row.revision_version += 1
        row.row_hash = self._row_hash(row)
        self._touch_scenario(record)
        self._recalculate_scenario(record)
        self._event(
            "portfolio_budget.scenario_updated", "PortfolioBudgetScenario", record.id, {"project_id": project_id}
        )
        self.db.commit()
        self.db.refresh(record)
        return self._scenario_out(record)

    def clone_scenario(
        self,
        scenario_id: int,
        expected_version: int,
        idempotency_key: str,
    ) -> BudgetScenarioOut:
        retry = self.db.scalar(
            select(PortfolioBudgetScenario).where(
                PortfolioBudgetScenario.tenant_id == self.tenant_id,
                PortfolioBudgetScenario.clone_idempotency_key == idempotency_key,
            )
        )
        if retry is not None:
            return self._scenario_out(retry)
        source = self._scenario(scenario_id, lock=True)
        self._check_version(source.revision_version, expected_version)
        revision = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(PortfolioBudgetScenario.scenario_revision), 0)).where(
                        PortfolioBudgetScenario.tenant_id == self.tenant_id,
                        PortfolioBudgetScenario.portfolio_workspace_id == source.portfolio_workspace_id,
                        PortfolioBudgetScenario.logical_code == source.logical_code,
                    )
                )
                or 0
            )
            + 1
        )
        clone = PortfolioBudgetScenario(
            tenant_id=self.tenant_id,
            portfolio_workspace_id=source.portfolio_workspace_id,
            logical_code=source.logical_code,
            scenario_name=f"{source.scenario_name} · Rev {revision}",
            scenario_code=source.scenario_code,
            description=source.description,
            status="DRAFT",
            analytical_status=source.analytical_status,
            budget_target_id=source.budget_target_id,
            source_analysis_hash=source.source_analysis_hash,
            source_prioritization_hash=source.source_prioritization_hash,
            membership_set_hash=source.membership_set_hash,
            evaluation_set_hash=source.evaluation_set_hash,
            source_configuration_hash=source.source_configuration_hash,
            budget_target_hash=source.budget_target_hash,
            source_hash=source.source_hash,
            scenario_hash="",
            creation_mode="COPY_EXISTING_SCENARIO",
            time_phasing_method=source.time_phasing_method,
            scenario_revision=revision,
            revision_version=1,
            clone_idempotency_key=idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._copy_rows(source.id, clone.id)
        self._recalculate_scenario(clone)
        self._event("portfolio_budget.scenario_cloned", "PortfolioBudgetScenario", clone.id, {"source_id": source.id})
        self.db.commit()
        self.db.refresh(clone)
        return self._scenario_out(clone)

    def freeze_scenario(
        self,
        scenario_id: int,
        expected_version: int,
        idempotency_key: str,
    ) -> BudgetScenarioOut:
        retry = self.db.scalar(
            select(PortfolioBudgetScenario).where(
                PortfolioBudgetScenario.tenant_id == self.tenant_id,
                PortfolioBudgetScenario.freeze_idempotency_key == idempotency_key,
            )
        )
        if retry is not None:
            return self._scenario_out(retry)
        record = self._scenario(scenario_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_scenario_editable(record)
        policy = self._policy(record.portfolio_workspace_id, require_published=True)
        if policy.get("scenario_creator_cannot_freeze") and record.created_by == self.actor_id:
            raise HTTPException(status_code=409, detail={"code": "SCENARIO_FREEZE_FOUR_EYES_REQUIRED"})
        output = self._scenario_out(record)
        if output.readiness.status != "READY":
            raise HTTPException(
                status_code=409,
                detail={"code": "BUDGET_SCENARIO_NOT_READY", "blockers": output.readiness.blockers},
            )
        record.status = "FROZEN"
        record.freeze_idempotency_key = idempotency_key
        record.frozen_at = utc_now()
        self._touch_scenario(record)
        self._recalculate_scenario(record)
        self._event("portfolio_budget.scenario_frozen", "PortfolioBudgetScenario", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        self._emit_readiness_change(record.portfolio_workspace_id)
        self.db.commit()
        return self._scenario_out(record)

    def void_scenario(
        self,
        scenario_id: int,
        expected_version: int,
        idempotency_key: str,
    ) -> BudgetScenarioOut:
        retry = self.db.scalar(
            select(PortfolioBudgetScenario).where(
                PortfolioBudgetScenario.tenant_id == self.tenant_id,
                PortfolioBudgetScenario.void_idempotency_key == idempotency_key,
            )
        )
        if retry is not None:
            return self._scenario_out(retry)
        record = self._scenario(scenario_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_scenario_editable(record)
        record.status = "VOIDED"
        record.void_idempotency_key = idempotency_key
        record.voided_at = utc_now()
        self._touch_scenario(record)
        self._recalculate_scenario(record)
        self._event("portfolio_budget.scenario_voided", "PortfolioBudgetScenario", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._scenario_out(record)

    # ------------------------------------------------------------------
    # Explicit source refresh
    # ------------------------------------------------------------------
    def refresh_preview(self, scenario_id: int) -> ScenarioRefreshPreviewOut:
        record = self._scenario(scenario_id)
        self._assert_scenario_editable(record)
        preview, _overview = self._refresh_delta(record)
        self._event(
            "portfolio_budget.source_refresh_previewed",
            "PortfolioBudgetScenario",
            record.id,
            {"persisted": False, "proposed_source_hash": preview.proposed_source_hash},
        )
        self.db.commit()
        return preview

    def apply_refresh(
        self,
        scenario_id: int,
        expected_version: int,
        expected_source_hash: str,
        idempotency_key: str,
    ) -> BudgetScenarioOut:
        retry = self.db.scalar(
            select(PortfolioBudgetScenario).where(
                PortfolioBudgetScenario.tenant_id == self.tenant_id,
                PortfolioBudgetScenario.refresh_idempotency_key == idempotency_key,
            )
        )
        if retry is not None:
            return self._scenario_out(retry)
        record = self._scenario(scenario_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_scenario_editable(record)
        preview, overview = self._refresh_delta(record)
        if preview.proposed_source_hash != expected_source_hash:
            raise HTTPException(
                status_code=412,
                detail={
                    "code": "STALE_PORTFOLIO_BUDGET_SOURCE",
                    "expected": expected_source_hash,
                    "actual": preview.proposed_source_hash,
                },
            )
        previous = {item.project_workspace_id: item for item in self._scenario_rows(record.id)}
        self.db.execute(
            delete(PortfolioBudgetScenarioProject).where(
                PortfolioBudgetScenarioProject.tenant_id == self.tenant_id,
                PortfolioBudgetScenarioProject.scenario_id == record.id,
            )
        )
        target = self._target(record.budget_target_id)
        self._snapshot_analysis_rows(record, overview.dataset.rows, target, "EMPTY", previous)
        record.source_analysis_hash = overview.dataset.analysis_hash
        record.source_prioritization_hash = overview.dataset.source_prioritization_hash
        record.membership_set_hash = overview.dataset.membership_set_hash
        record.evaluation_set_hash = overview.dataset.evaluation_set_hash
        record.source_configuration_hash = overview.dataset.configuration_hash
        record.budget_target_hash = target.target_hash
        record.source_hash = preview.proposed_source_hash
        record.refresh_idempotency_key = idempotency_key
        self._touch_scenario(record)
        self._recalculate_scenario(record)
        self._event("portfolio_budget.source_refresh_applied", "PortfolioBudgetScenario", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._scenario_out(record)

    # ------------------------------------------------------------------
    # Comparison, readiness and downstream contract
    # ------------------------------------------------------------------
    def compare(self, portfolio_id: int, scenario_ids: list[int]) -> ScenarioComparisonOut:
        records = [self._scenario(item) for item in scenario_ids]
        if any(item.portfolio_workspace_id != portfolio_id for item in records):
            raise HTTPException(status_code=422, detail={"code": "BUDGET_SCENARIO_PORTFOLIO_MISMATCH"})
        outputs = [self._scenario_out(item) for item in records]
        projects: dict[int, dict] = {}
        for output in outputs:
            for row in output.projects:
                item = projects.setdefault(
                    row.project_workspace_id,
                    {
                        "project_workspace_id": row.project_workspace_id,
                        "project_number": row.project_number,
                        "project_name": row.project_name,
                    },
                )
                item[str(output.id)] = row.selection_state
        first, second = outputs[0], outputs[1]
        first_selected = {row.project_workspace_id for row in first.projects if self._included(row.selection_state)}
        second_selected = {row.project_workspace_id for row in second.projects if self._included(row.selection_state)}
        pairwise = {
            "from_scenario_id": first.id,
            "to_scenario_id": second.id,
            "projects_added": sorted(second_selected - first_selected),
            "projects_removed": sorted(first_selected - second_selected),
            "budget_delta": second.summary.selected_demand - first.summary.selected_demand,
            "score_delta": (second.summary.average_evaluation_score or Decimal("0"))
            - (first.summary.average_evaluation_score or Decimal("0")),
            "risk_delta": second.summary.high_risk_count - first.summary.high_risk_count,
            "objective_coverage_delta": len(second.strategic_balance.get("objectives", []))
            - len(first.strategic_balance.get("objectives", [])),
            "capex_delta": second.summary.selected_capex - first.summary.selected_capex,
            "expense_delta": second.summary.selected_expense - first.summary.selected_expense,
            "unclassified_delta": second.summary.selected_unclassified - first.summary.selected_unclassified,
            "unmet_dependency_delta": second.summary.unmet_mandatory_count - first.summary.unmet_mandatory_count,
        }
        self._event(
            "portfolio_budget.scenarios_compared", "EnterpriseWorkspace", portfolio_id, {"scenario_ids": scenario_ids}
        )
        self.db.commit()
        return ScenarioComparisonOut(
            portfolio_workspace_id=portfolio_id,
            scenarios=[
                {
                    "id": item.id,
                    "scenario_name": item.scenario_name,
                    "status": item.status,
                    "selected_count": item.summary.selected_count,
                    "total_demand": item.summary.selected_demand,
                    "target_budget": item.summary.target_budget,
                    "variance": item.summary.variance,
                    "utilization_percent": item.summary.utilization_percent,
                    "average_evaluation_score": item.summary.average_evaluation_score,
                    "average_strategic_alignment": item.summary.average_strategic_alignment,
                    "high_risk_count": item.summary.high_risk_count,
                    "selected_capex": item.summary.selected_capex,
                    "selected_expense": item.summary.selected_expense,
                    "selected_unclassified": item.summary.selected_unclassified,
                    "unmet_mandatory_dependencies": item.summary.unmet_mandatory_count,
                    "forced_dependency_conflicts": item.summary.forced_dependency_conflict_count,
                    "strategic_objective_coverage": len(item.strategic_balance.get("objectives", [])),
                    "planning_horizon": self._planning_horizon(item.budget_target_id),
                    "warnings": item.warnings,
                    "blockers": item.blockers,
                }
                for item in outputs
            ],
            project_matrix=sorted(
                projects.values(), key=lambda item: (item["project_number"], item["project_workspace_id"])
            ),
            pairwise_delta=pairwise,
            warnings=["COMPARISON_IS_ANALYTICAL_ONLY", "NO_SCENARIO_WINNER_OR_FID_CREATED"],
        )

    def waterline(self, scenario_id: int, period_key: str | None = None) -> WaterlineOut:
        record = self._scenario(scenario_id)
        rows = self._scenario_rows(record.id)
        target = self._target(record.budget_target_id)
        dependencies = self._dependency_evaluation(record, rows)
        selected_period = period_key or "TOTAL"
        target_budget = Decimal(target.total_budget_target)
        if selected_period != "TOTAL":
            period = next(
                (item for item in self._period_view(record, rows, target) if item.period_key == selected_period),
                None,
            )
            if period is None:
                raise HTTPException(status_code=404, detail={"code": "WATERLINE_PERIOD_NOT_FOUND"})
            target_budget = Decimal(period.target or 0)
        cumulative = Decimal("0")
        selected_capex = Decimal("0")
        selected_expense = Decimal("0")
        selected_unclassified = Decimal("0")
        position: int | None = None
        projects: list[WaterlineProjectOut] = []
        for row in rows:
            demand, capex, expense, unclassified = self._waterline_row_amounts(record, row, target, selected_period)
            if self._included(row.selection_state):
                cumulative += demand
                selected_capex += capex
                selected_expense += expense
                selected_unclassified += unclassified
                if position is None and cumulative >= target_budget:
                    position = row.portfolio_rank
            dep = dependencies["projects"].get(row.project_workspace_id, {})
            projects.append(
                WaterlineProjectOut(
                    project_workspace_id=row.project_workspace_id,
                    project_number=row.project_number,
                    project_name=row.project_name,
                    portfolio_rank=row.portfolio_rank,
                    selection_state=row.selection_state,
                    budget_demand=demand,
                    cumulative_selected_demand=cumulative,
                    target_budget=target_budget,
                    waterline_side=(
                        "UNREACHED"
                        if position is None
                        else "ABOVE_OR_AT"
                        if row.portfolio_rank <= position
                        else "BELOW"
                    ),
                    forced_state=row.selection_state if row.selection_state.startswith("FORCED") else None,
                    dependency_status=str(dep.get("status") or "NOT_APPLICABLE"),
                    unmet_dependency_count=int(dep.get("unmet_count") or 0),
                    capex_amount=capex if row.capex_amount is not None else None,
                    expense_amount=expense if row.expense_amount is not None else None,
                    unclassified_amount=unclassified,
                    project_type=row.project_type,
                    risk_bucket=row.risk_bucket,
                    strategic_objectives=list(row.strategic_objectives_json or []),
                )
            )
        if position is not None:
            projects = [
                item.model_copy(
                    update={"waterline_side": "ABOVE_OR_AT" if item.portfolio_rank <= position else "BELOW"}
                )
                for item in projects
            ]
        return WaterlineOut(
            scenario_id=record.id,
            period_key=selected_period,
            target_budget=target_budget,
            selected_demand=cumulative,
            variance=target_budget - cumulative,
            analytical_status=(
                "OVER_BUDGET"
                if cumulative > target_budget
                else "WITHIN_BUDGET"
                if cumulative == target_budget
                else "UNDER_BUDGET"
            ),
            alignment_status=(
                "GATE07G_A_OPC_ALIGNMENT_REWORK_REQUIRED"
                if dependencies["blockers"]
                else "GATE07G_A_OPC_ALIGNMENT_VALIDATED"
            ),
            waterline_position=position,
            projects=projects,
            budget_breakdown={
                "capex": selected_capex,
                "expense": selected_expense,
                "unclassified": selected_unclassified,
            },
            dependency_summary=dependencies["summary"],
            allowed_actions=[
                "can_view_waterline",
                "can_view_project_dependencies",
                "can_view_dependency_status",
                "can_view_capex_expense_breakdown",
            ],
        )

    def _waterline_row_amounts(
        self,
        scenario: PortfolioBudgetScenario,
        row: PortfolioBudgetScenarioProject,
        target: PortfolioBudgetTarget,
        period_key: str,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        total = Decimal(row.cost_value)
        capex = Decimal(row.capex_amount or 0)
        expense = Decimal(row.expense_amount or 0)
        unclassified = Decimal(row.unclassified_amount)
        if period_key in {"TOTAL", "UNPHASED"}:
            return total, capex, expense, unclassified
        if scenario.time_phasing_method == "CUSTOM_PERIOD_PROFILE":
            profile = next(
                (item for item in row.period_profile_json or [] if str(item.get("period_key")) == period_key),
                {},
            )
            period_total = Decimal(str(profile.get("amount") or 0))
            period_capex = Decimal(str(profile.get("capex_amount") or 0))
            period_expense = Decimal(str(profile.get("expense_amount") or 0))
            period_unclassified = Decimal(
                str(profile.get("unclassified_amount") or (period_total - period_capex - period_expense))
            )
            return period_total, period_capex, period_expense, period_unclassified
        periods = self._period_records(target.id) or self._generated_periods(target)
        applicable = [
            item
            for item in periods
            if row.target_start is not None
            and row.target_finish is not None
            and item.period_end >= row.target_start
            and item.period_start <= row.target_finish
        ]
        if not applicable or period_key not in {item.period_key for item in applicable}:
            return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")
        divisor = Decimal(len(applicable))
        return total / divisor, capex / divisor, expense / divisor, unclassified / divisor

    def project_dependencies(self, portfolio_id: int) -> list[ProjectDependencyOut]:
        project_ids = self._portfolio_project_ids(portfolio_id)
        if not project_ids:
            return []
        records = list(
            self.db.scalars(
                select(ProjectDependency)
                .where(
                    ProjectDependency.tenant_id == self.tenant_id,
                    or_(
                        ProjectDependency.predecessor_project_workspace_id.in_(project_ids),
                        ProjectDependency.successor_project_workspace_id.in_(project_ids),
                    ),
                )
                .order_by(ProjectDependency.status, ProjectDependency.id)
            ).all()
        )
        workspace_ids = {
            workspace_id
            for item in records
            for workspace_id in (
                item.predecessor_project_workspace_id,
                item.successor_project_workspace_id,
            )
        }
        workspaces = {
            item.id: item
            for item in self.db.scalars(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id.in_(workspace_ids),
                )
            ).all()
        }
        return [self._dependency_out(item, workspaces) for item in records]

    def project_dependency(self, dependency_id: int) -> ProjectDependencyOut:
        return self._dependency_out(self._dependency(dependency_id))

    def create_project_dependency(self, portfolio_id: int, payload: ProjectDependencyCreateIn) -> ProjectDependencyOut:
        self._portfolio(portfolio_id)
        retry = self.db.scalar(
            select(ProjectDependency).where(
                ProjectDependency.tenant_id == self.tenant_id,
                ProjectDependency.create_idempotency_key == payload.idempotency_key,
            )
        )
        if retry is not None:
            return self._dependency_out(retry)
        predecessor = self._project_workspace(payload.predecessor_project_workspace_id)
        successor = self._project_workspace(payload.successor_project_workspace_id)
        portfolio_projects = set(self._portfolio_project_ids(portfolio_id))
        if predecessor.id not in portfolio_projects or successor.id not in portfolio_projects:
            raise HTTPException(status_code=422, detail={"code": "DEPENDENCY_PROJECT_OUTSIDE_PORTFOLIO"})
        duplicate = self.db.scalar(
            select(ProjectDependency.id).where(
                ProjectDependency.tenant_id == self.tenant_id,
                ProjectDependency.predecessor_project_workspace_id == predecessor.id,
                ProjectDependency.successor_project_workspace_id == successor.id,
                ProjectDependency.dependency_type == payload.dependency_type,
                ProjectDependency.status == "ACTIVE",
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail={"code": "ACTIVE_PROJECT_DEPENDENCY_ALREADY_EXISTS"})
        if payload.dependency_strength == "MANDATORY" and self._creates_dependency_cycle(predecessor.id, successor.id):
            raise HTTPException(status_code=409, detail={"code": "PROJECT_DEPENDENCY_CYCLE"})
        record = ProjectDependency(
            tenant_id=self.tenant_id,
            predecessor_project_workspace_id=predecessor.id,
            successor_project_workspace_id=successor.id,
            dependency_type=payload.dependency_type,
            dependency_strength=payload.dependency_strength,
            description=payload.description.strip(),
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            status="ACTIVE",
            source_reference=payload.source_reference,
            evidence_refs_json=deepcopy(payload.evidence_refs),
            create_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
            revision_version=1,
        )
        self.db.add(record)
        self.db.flush()
        self._event("project_dependency.created", "ProjectDependency", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._dependency_out(record)

    def update_project_dependency(
        self, dependency_id: int, expected_version: int, payload: ProjectDependencyUpdateIn
    ) -> ProjectDependencyOut:
        record = self._dependency(dependency_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status != "ACTIVE":
            raise HTTPException(status_code=409, detail={"code": "INACTIVE_PROJECT_DEPENDENCY_IMMUTABLE"})
        duplicate = self.db.scalar(
            select(ProjectDependency.id).where(
                ProjectDependency.tenant_id == self.tenant_id,
                ProjectDependency.predecessor_project_workspace_id == record.predecessor_project_workspace_id,
                ProjectDependency.successor_project_workspace_id == record.successor_project_workspace_id,
                ProjectDependency.dependency_type == payload.dependency_type,
                ProjectDependency.status == "ACTIVE",
                ProjectDependency.id != record.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail={"code": "ACTIVE_PROJECT_DEPENDENCY_ALREADY_EXISTS"})
        if payload.dependency_strength == "MANDATORY" and self._creates_dependency_cycle(
            record.predecessor_project_workspace_id,
            record.successor_project_workspace_id,
            exclude_dependency_id=record.id,
        ):
            raise HTTPException(status_code=409, detail={"code": "PROJECT_DEPENDENCY_CYCLE"})
        record.dependency_type = payload.dependency_type
        record.dependency_strength = payload.dependency_strength
        record.description = payload.description.strip()
        record.effective_from = payload.effective_from
        record.effective_to = payload.effective_to
        record.source_reference = payload.source_reference
        record.evidence_refs_json = deepcopy(payload.evidence_refs)
        record.updated_by = self.actor_id
        record.updated_at = utc_now()
        record.revision_version += 1
        self._event("project_dependency.updated", "ProjectDependency", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._dependency_out(record)

    def deactivate_project_dependency(
        self, dependency_id: int, expected_version: int, idempotency_key: str
    ) -> ProjectDependencyOut:
        retry = self.db.scalar(
            select(ProjectDependency).where(
                ProjectDependency.tenant_id == self.tenant_id,
                ProjectDependency.deactivate_idempotency_key == idempotency_key,
            )
        )
        if retry is not None:
            return self._dependency_out(retry)
        record = self._dependency(dependency_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status != "ACTIVE":
            raise HTTPException(status_code=409, detail={"code": "PROJECT_DEPENDENCY_NOT_ACTIVE"})
        record.status = "INACTIVE"
        record.deactivate_idempotency_key = idempotency_key
        record.updated_by = self.actor_id
        record.updated_at = utc_now()
        record.revision_version += 1
        self._event("project_dependency.deactivated", "ProjectDependency", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._dependency_out(record)

    def scenario_dependencies(self, scenario_id: int) -> ScenarioDependencyOut:
        record = self._scenario(scenario_id)
        evaluated = self._dependency_evaluation(record, self._scenario_rows(record.id))
        return ScenarioDependencyOut(
            scenario_id=record.id,
            summary=evaluated["summary"],
            projects=list(evaluated["projects"].values()),
            warnings=evaluated["warnings"],
            blockers=evaluated["blockers"],
        )

    def readiness(self, portfolio_id: int) -> PortfolioBudgetPlanningReadinessOut:
        overview = self._analysis(portfolio_id, require_budget=False)
        targets = self._target_records(portfolio_id)
        active = next((item for item in targets if item.status == "PUBLISHED"), None)
        records = list(
            self.db.scalars(
                select(PortfolioBudgetScenario).where(
                    PortfolioBudgetScenario.tenant_id == self.tenant_id,
                    PortfolioBudgetScenario.portfolio_workspace_id == portfolio_id,
                    PortfolioBudgetScenario.status != "VOIDED",
                )
            ).all()
        )
        outputs = [self._scenario_out(item, overview=overview) for item in records]
        frozen = [item for item in outputs if item.status == "FROZEN"]
        ready = [item for item in frozen if item.readiness.status == "READY"]
        warnings = sorted({warning for item in outputs for warning in item.warnings})
        blockers: list[str] = []
        if overview.readiness.final_output != READY_INPUT or not overview.readiness.can_enter_budget_planning:
            blockers.append("READY_FOR_PORTFOLIO_SCENARIO_PLANNING_WITH_BUDGET_REQUIRED")
            blockers.extend(overview.readiness.blockers)
            if not overview.readiness.can_enter_budget_planning:
                blockers.extend(overview.readiness.warnings)
        if active is None:
            blockers.append("PUBLISHED_BUDGET_TARGET_REQUIRED")
        minimum = int(
            self._policy(portfolio_id, require_published=False).get("readiness", {}).get("minimum_frozen_scenarios", 1)
        )
        if len(ready) < minimum:
            blockers.append("READY_FROZEN_BUDGET_SCENARIO_REQUIRED")
        planning_hash = _hash(
            {
                "portfolio_workspace_id": portfolio_id,
                "analysis_hash": overview.dataset.analysis_hash,
                "budget_target_hash": active.target_hash if active else None,
                "ready_scenarios": sorted((item.id, item.scenario_hash) for item in ready),
            }
        )
        can_enter = not blockers
        actions = self._allowed_actions(can_enter)
        return PortfolioBudgetPlanningReadinessOut(
            portfolio_workspace_id=portfolio_id,
            scenario_count=len(records),
            frozen_scenario_count=len(frozen),
            ready_scenario_count=len(ready),
            budget_target_id=active.id if active else None,
            warnings=warnings,
            blockers=sorted(set(blockers)),
            budget_planning_hash=planning_hash,
            can_enter_budget_recommendation=can_enter,
            allowed_actions=actions,
            final_output=READY_OUTPUT if can_enter else REWORK_OUTPUT,
        )

    def overview(self, portfolio_id: int) -> BudgetPlanningOverviewOut:
        analysis = self._analysis(portfolio_id, require_budget=False)
        targets = self.targets(portfolio_id)
        active = next((item for item in targets if item.status == "PUBLISHED"), None)
        scenarios = self.scenarios(portfolio_id)
        readiness = self.readiness(portfolio_id)
        return BudgetPlanningOverviewOut(
            portfolio_workspace_id=portfolio_id,
            gate07f={
                "final_output": analysis.readiness.final_output,
                "analysis_hash": analysis.dataset.analysis_hash,
                "can_enter_budget_planning": analysis.readiness.can_enter_budget_planning,
                "can_enter_resource_planning": analysis.readiness.can_enter_resource_planning,
                "warnings": analysis.readiness.warnings,
                "blockers": analysis.readiness.blockers,
            },
            active_target=active,
            targets=targets,
            scenarios=scenarios,
            readiness=readiness,
            allowed_actions=self._allowed_actions(readiness.can_enter_budget_recommendation),
            boundaries=[
                "STRATEGIC_BUDGET_PLANNING_NOT_PROJECT_COST_CONTROL",
                "NO_FUNDS_OR_FUNDING_ASSIGNMENT",
                "NO_RESOURCE_PLANNING",
                "NO_SCENARIO_WINNER_OR_INVESTMENT_APPROVAL",
                "NO_FID_INITIALIZATION_ACTIVATION_OR_EXECUTION",
            ],
        )

    def recommendation_contract(self, portfolio_id: int) -> BudgetRecommendationContractOut:
        readiness = self.readiness(portfolio_id)
        analysis = self._analysis(portfolio_id, require_budget=False)
        target = self._target(readiness.budget_target_id) if readiness.budget_target_id else None
        scenarios = self.scenarios(portfolio_id)
        ready = [item for item in scenarios if item.status == "FROZEN" and item.readiness.status == "READY"]
        return BudgetRecommendationContractOut(
            portfolio_workspace_id=portfolio_id,
            budget_planning_hash=readiness.budget_planning_hash,
            budget_target_snapshot=self._target_out(target).model_dump(mode="json") if target else {},
            ready_frozen_scenario_refs=[
                {
                    "id": item.id,
                    "logical_code": item.logical_code,
                    "revision": item.scenario_revision,
                    "scenario_hash": item.scenario_hash,
                }
                for item in ready
            ],
            scenario_hashes=[item.scenario_hash for item in ready],
            analysis_hash=analysis.dataset.analysis_hash,
            membership_set_hash=analysis.dataset.membership_set_hash,
            evaluation_set_hash=analysis.dataset.evaluation_set_hash,
            warnings=readiness.warnings,
            blockers=readiness.blockers,
            final_output=readiness.final_output,
        )

    # ------------------------------------------------------------------
    # ADMIN configuration
    # ------------------------------------------------------------------
    def configurations(self) -> list[AdminConfiguration]:
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
        target_assumptions: dict | None,
    ) -> ConfigurationPreviewOut:
        workspace = self._portfolio(portfolio_id) if portfolio_id else None
        selected = self._configuration(configuration_id) if configuration_id else None
        if selected is None:
            selected = (
                self._effective_configuration(workspace, published_only=True) if workspace else self._tenant_published()
            )
        if selected is None:
            selected = self.db.scalar(
                select(AdminConfiguration)
                .where(AdminConfiguration.tenant_id == self.tenant_id, AdminConfiguration.kind == CONFIGURATION_KIND)
                .order_by(AdminConfiguration.revision.desc())
            )
        content = self._merged_configuration(
            content_override
            if content_override is not None
            else selected.content_json
            if selected
            else DEFAULT_CONFIGURATION
        )
        issues = self._configuration_issues(content)
        count = 0
        coverage = Decimal("0")
        currency_status = "NOT_EVALUATED"
        warnings: list[str] = []
        blockers: list[str] = []
        waterline_preview: dict = {
            "enabled": bool(dict(content.get("waterline", {})).get("show_waterline", True)),
            "rank_source": "GATE07E_CONTEXTUAL_PORTFOLIO_RANK",
            "persisted": False,
        }
        dependency_preview: dict = {
            "enabled": bool(dict(content.get("dependencies", {})).get("enabled", True)),
            "mandatory_unmet_policy": dict(content.get("dependencies", {})).get(
                "mandatory_unmet_policy", "BLOCK_FREEZE"
            ),
            "persisted": False,
        }
        budget_breakdown_preview: dict = {
            "enabled": bool(dict(content.get("capex_expense", {})).get("enabled", True)),
            "allow_unclassified": bool(dict(content.get("capex_expense", {})).get("allow_unclassified", True)),
            "target_assumptions": deepcopy(target_assumptions or {}),
            "persisted": False,
        }
        if portfolio_id:
            analysis = self._analysis(portfolio_id, require_budget=False)
            count = len(analysis.dataset.rows)
            with_cost = sum(item.rom_cost is not None and bool(item.currency) for item in analysis.dataset.rows)
            coverage = _percent(with_cost, count)
            currency_status = "SINGLE_CURRENCY" if analysis.readiness.can_enter_budget_planning else "BLOCKED"
            warnings = analysis.readiness.warnings
            blockers = analysis.readiness.blockers
            scenario = self.db.scalar(
                select(PortfolioBudgetScenario)
                .where(
                    PortfolioBudgetScenario.tenant_id == self.tenant_id,
                    PortfolioBudgetScenario.portfolio_workspace_id == portfolio_id,
                    PortfolioBudgetScenario.status != "VOIDED",
                )
                .order_by(PortfolioBudgetScenario.updated_at.desc(), PortfolioBudgetScenario.id.desc())
            )
            if scenario is not None:
                derived = self.waterline(scenario.id)
                waterline_preview.update(
                    {
                        "scenario_id": scenario.id,
                        "target_budget": derived.target_budget,
                        "selected_demand": derived.selected_demand,
                        "variance": derived.variance,
                        "waterline_position": derived.waterline_position,
                        "forced_states": sum(item.forced_state is not None for item in derived.projects),
                    }
                )
                dependency_preview.update(derived.dependency_summary)
                budget_breakdown_preview.update(derived.budget_breakdown)
        self._event(
            "portfolio_budget.configuration_previewed",
            "AdminConfiguration",
            selected.id if selected else None,
            {"portfolio_workspace_id": portfolio_id, "persisted": False},
        )
        self.db.commit()
        return ConfigurationPreviewOut(
            portfolio_workspace_id=portfolio_id,
            path=[self._workspace_summary(item) for item in self._workspace_path(workspace)] if workspace else [],
            effective_policy=content,
            source={
                "configuration_id": selected.id if selected else None,
                "revision": selected.revision if selected else 0,
                "hash": _hash(content),
                "source_workspace_id": dict(content.get("scope", {})).get("workspace_id"),
                "resolution_chain": [item.id for item in self._workspace_path(workspace)] if workspace else [],
            },
            eligible_project_count=count,
            cost_coverage_percent=coverage,
            currency_status=currency_status,
            time_phasing_capability=list(content.get("allowed_time_phasing_methods", [])),
            warnings=warnings,
            blockers=blockers,
            validation_issues=issues,
            publishable=not issues,
            persisted=False,
            waterline_preview=waterline_preview,
            dependency_preview=dependency_preview,
            budget_breakdown_preview=budget_breakdown_preview,
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id)
        self._check_version(source.version, expected_version)
        revision = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(AdminConfiguration.revision), 0)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                        AdminConfiguration.code == source.code,
                    )
                )
                or 0
            )
            + 1
        )
        clone = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code=source.code,
            name=source.name,
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=deepcopy(source.content_json or {}),
            content_hash=source.content_hash or _hash(source.content_json),
            created_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._event("portfolio_budget.configuration_cloned", "AdminConfiguration", clone.id, {"source_id": source.id})
        self.db.commit()
        self.db.refresh(clone)
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
        record.name = name.strip()
        record.description = description.strip()
        record.content_json = deepcopy(content)
        record.content_hash = _hash(content)
        record.version += 1
        record.updated_at = utc_now()
        self._event("portfolio_budget.configuration_updated", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_IMMUTABLE"})
        self._validate_configuration(dict(record.content_json or {}))
        record.status = "published"
        record.content_hash = _hash(record.content_json)
        record.published_at = utc_now()
        record.updated_at = record.published_at
        record.version += 1
        self._event("portfolio_budget.configuration_published", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    # ------------------------------------------------------------------
    # Builders and calculations
    # ------------------------------------------------------------------
    def _snapshot_analysis_rows(
        self,
        scenario: PortfolioBudgetScenario,
        rows: list[PortfolioAnalysisRowOut],
        target: PortfolioBudgetTarget,
        creation_mode: str,
        previous: dict[int, PortfolioBudgetScenarioProject] | None = None,
    ) -> None:
        remaining = Decimal(target.total_budget_target)
        project_ids = [item.project_workspace_id for item in rows]
        workspaces = {
            item.id: item
            for item in self.db.scalars(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id.in_(project_ids),
                )
            ).all()
        }
        for item in sorted(rows, key=lambda row: (row.portfolio_rank, row.project_workspace_id)):
            cost = Decimal(item.rom_cost or 0)
            capex, expense, unclassified, breakdown_source = self._budget_breakdown(
                workspaces.get(item.project_workspace_id), cost
            )
            selection = "UNSELECTED"
            old = (previous or {}).get(item.project_workspace_id)
            if old is not None:
                selection = old.selection_state
            elif creation_mode == "FROM_CURRENT_PRIORITY" and cost <= remaining:
                selection = "SELECTED"
                remaining -= cost
            cost_hash = _hash(
                {
                    "planning_entry_hash": item.planning_entry_hash,
                    "evaluation_hash": item.evaluation_hash,
                    "value": str(cost),
                    "currency": item.currency,
                    "breakdown": (capex, expense, unclassified, breakdown_source),
                }
            )
            row = PortfolioBudgetScenarioProject(
                tenant_id=self.tenant_id,
                scenario_id=scenario.id,
                project_workspace_id=item.project_workspace_id,
                portfolio_membership_id=item.portfolio_membership_id,
                project_number=item.project_number,
                project_name=item.project_name,
                portfolio_evaluation_score=item.portfolio_evaluation_score,
                portfolio_rank=item.portfolio_rank,
                strategic_alignment_score=item.strategic_alignment_score,
                risk_score=item.risk_score,
                risk_bucket=item.risk_bucket,
                gate07f_analysis_hash=scenario.source_analysis_hash,
                cost_source_type="GATE07F_ROM_COST",
                cost_source_reference=f"portfolio-evaluation:{item.evaluation_id}",
                cost_source_hash=cost_hash,
                cost_value=cost,
                capex_amount=capex,
                expense_amount=expense,
                unclassified_amount=unclassified,
                budget_breakdown_source=breakdown_source,
                currency=item.currency or target.budget_currency,
                cost_as_of_date=item.evaluation_date.date(),
                target_start=item.target_start,
                target_finish=item.target_finish,
                strategic_objectives_json=deepcopy(item.strategic_objectives),
                risk_summary_json=deepcopy(item.risk_summary),
                expected_benefits=item.expected_benefits or "",
                project_type=item.project_type or "",
                planning_stage=item.planning_stage or "",
                selection_state=selection,
                forced_reason=old.forced_reason if old and selection in {"FORCED_IN", "FORCED_OUT"} else None,
                forced_actor_id=old.forced_actor_id if old and selection in {"FORCED_IN", "FORCED_OUT"} else None,
                forced_at=old.forced_at if old and selection in {"FORCED_IN", "FORCED_OUT"} else None,
                forced_authority_reference=old.forced_authority_reference if old else None,
                period_profile_json=deepcopy(old.period_profile_json if old else []),
                warnings_json=[],
                row_hash="",
                revision_version=1,
                updated_by=self.actor_id,
            )
            row.row_hash = self._row_hash(row)
            self.db.add(row)
        self.db.flush()
        scenario.source_hash = self._source_hash(scenario, target, self._scenario_rows(scenario.id))

    def _copy_rows(self, source_id: int, target_id: int) -> None:
        for item in self._scenario_rows(source_id):
            row = PortfolioBudgetScenarioProject(
                tenant_id=self.tenant_id,
                scenario_id=target_id,
                project_workspace_id=item.project_workspace_id,
                portfolio_membership_id=item.portfolio_membership_id,
                project_number=item.project_number,
                project_name=item.project_name,
                portfolio_evaluation_score=item.portfolio_evaluation_score,
                portfolio_rank=item.portfolio_rank,
                strategic_alignment_score=item.strategic_alignment_score,
                risk_score=item.risk_score,
                risk_bucket=item.risk_bucket,
                gate07f_analysis_hash=item.gate07f_analysis_hash,
                cost_source_type=item.cost_source_type,
                cost_source_reference=item.cost_source_reference,
                cost_source_hash=item.cost_source_hash,
                cost_value=item.cost_value,
                capex_amount=item.capex_amount,
                expense_amount=item.expense_amount,
                unclassified_amount=item.unclassified_amount,
                budget_breakdown_source=item.budget_breakdown_source,
                currency=item.currency,
                cost_as_of_date=item.cost_as_of_date,
                target_start=item.target_start,
                target_finish=item.target_finish,
                strategic_objectives_json=deepcopy(item.strategic_objectives_json or []),
                risk_summary_json=deepcopy(item.risk_summary_json or []),
                expected_benefits=item.expected_benefits,
                project_type=item.project_type,
                planning_stage=item.planning_stage,
                selection_state=item.selection_state,
                forced_reason=item.forced_reason,
                forced_actor_id=item.forced_actor_id,
                forced_at=item.forced_at,
                forced_authority_reference=item.forced_authority_reference,
                period_profile_json=deepcopy(item.period_profile_json or []),
                warnings_json=deepcopy(item.warnings_json or []),
                row_hash=item.row_hash,
                revision_version=1,
                updated_by=self.actor_id,
            )
            self.db.add(row)
        self.db.flush()

    def _scenario_out(
        self,
        record: PortfolioBudgetScenario,
        *,
        overview: PortfolioAnalysisOverviewOut | None = None,
    ) -> BudgetScenarioOut:
        rows = self._scenario_rows(record.id)
        target = self._target(record.budget_target_id)
        dependencies = self._dependency_evaluation(record, rows)
        summary = self._summary(rows, target, dependencies["summary"])
        current = overview or self._analysis(record.portfolio_workspace_id, require_budget=False)
        proposed_source = self._source_hash_from_analysis(record, target, current)
        source_current = proposed_source == record.source_hash
        if not source_current and rows and all(item.budget_breakdown_source == "LEGACY_UNCLASSIFIED" for item in rows):
            source_current = self._legacy_source_hash_from_analysis(record, target, current) == record.source_hash
        warnings: list[str] = []
        blockers: list[str] = []
        warnings.extend(dependencies["warnings"])
        blockers.extend(dependencies["blockers"])
        if summary.analytical_status == "OVER_BUDGET":
            warnings.append("SCENARIO_OVER_BUDGET")
        if not source_current:
            blockers.append("STALE_PORTFOLIO_BUDGET_SOURCE")
        currencies = {item.currency for item in rows}
        if currencies != {target.budget_currency}:
            blockers.append("SCENARIO_CURRENCY_MISMATCH")
        if any(item.cost_value is None for item in rows):
            blockers.append("SCENARIO_COST_COVERAGE_INCOMPLETE")
        if any(item.selection_state in {"FORCED_IN", "FORCED_OUT"} and not item.forced_reason for item in rows):
            blockers.append("FORCED_STATE_REASON_REQUIRED")
        if record.time_phasing_method == "LINEAR_BY_PROJECT_DATES" and any(
            self._included(item.selection_state) and (item.target_start is None or item.target_finish is None)
            for item in rows
        ):
            blockers.append("PROJECT_DATES_REQUIRED_FOR_LINEAR_PHASING")
        if record.time_phasing_method == "CUSTOM_PERIOD_PROFILE" and any(
            self._included(item.selection_state) and not item.period_profile_json for item in rows
        ):
            blockers.append("CUSTOM_PERIOD_PROFILE_REQUIRED")
        status = "STALE" if not source_current else "BLOCKED" if blockers else "READY"
        allowed = self._allowed_actions(False)
        if record.status in {"DRAFT", "IN_REVIEW"}:
            allowed.extend(
                [
                    "can_edit_budget_scenario",
                    "can_refresh_budget_scenario_source",
                    "can_freeze_budget_scenario",
                    "can_void_budget_scenario",
                ]
            )
        allowed.extend(["can_clone_budget_scenario", "can_compare_budget_scenarios"])
        return BudgetScenarioOut(
            id=record.id,
            tenant_id=record.tenant_id,
            portfolio_workspace_id=record.portfolio_workspace_id,
            logical_code=record.logical_code,
            scenario_name=record.scenario_name,
            scenario_code=record.scenario_code,
            description=record.description,
            status=record.status,
            analytical_status=summary.analytical_status,
            budget_target_id=record.budget_target_id,
            source_analysis_hash=record.source_analysis_hash,
            source_prioritization_hash=record.source_prioritization_hash,
            membership_set_hash=record.membership_set_hash,
            evaluation_set_hash=record.evaluation_set_hash,
            source_configuration_hash=record.source_configuration_hash,
            budget_target_hash=record.budget_target_hash,
            source_hash=record.source_hash,
            scenario_hash=record.scenario_hash,
            creation_mode=record.creation_mode,
            time_phasing_method=record.time_phasing_method,
            scenario_revision=record.scenario_revision,
            revision_version=record.revision_version,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_by=record.updated_by,
            updated_at=record.updated_at,
            frozen_at=record.frozen_at,
            voided_at=record.voided_at,
            projects=[
                self._project_out(item, dependencies["projects"].get(item.project_workspace_id)) for item in rows
            ],
            summary=summary,
            period_view=self._period_view(record, rows, target),
            strategic_balance=self._strategic_balance(rows),
            readiness=ScenarioReadinessOut(
                status=status,
                source_current=source_current,
                warnings=sorted(set(warnings)),
                blockers=sorted(set(blockers)),
            ),
            warnings=sorted(set(warnings)),
            blockers=sorted(set(blockers)),
            allowed_actions=sorted(set(allowed)),
            dependency_summary=dependencies["summary"],
        )

    def _summary(
        self,
        rows: list[PortfolioBudgetScenarioProject],
        target: PortfolioBudgetTarget,
        dependency_summary: dict | None = None,
    ) -> ScenarioSummaryOut:
        selected = [item for item in rows if self._included(item.selection_state)]
        demand = sum((Decimal(item.cost_value) for item in selected), Decimal("0"))
        budget = Decimal(target.total_budget_target)
        variance = budget - demand
        utilization = (
            (demand * Decimal("100") / budget).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if budget
            else Decimal("0")
        )
        analytical = "OVER_BUDGET" if demand > budget else "WITHIN_BUDGET" if demand == budget else "UNDER_BUDGET"
        scores = [Decimal(item.portfolio_evaluation_score) for item in selected]
        alignment = [Decimal(item.strategic_alignment_score) for item in selected]
        selected_capex = sum((Decimal(item.capex_amount or 0) for item in selected), Decimal("0"))
        selected_expense = sum((Decimal(item.expense_amount or 0) for item in selected), Decimal("0"))
        selected_unclassified = sum((Decimal(item.unclassified_amount) for item in selected), Decimal("0"))
        capex_target = Decimal(target.capex_budget_target) if target.capex_budget_target is not None else None
        expense_target = Decimal(target.expense_budget_target) if target.expense_budget_target is not None else None
        dependency_summary = dependency_summary or {}
        return ScenarioSummaryOut(
            selected_demand=demand,
            target_budget=budget,
            variance=variance,
            utilization_percent=utilization,
            selected_count=len(selected),
            unselected_count=sum(item.selection_state == "UNSELECTED" for item in rows),
            forced_in_count=sum(item.selection_state == "FORCED_IN" for item in rows),
            forced_out_count=sum(item.selection_state == "FORCED_OUT" for item in rows),
            average_evaluation_score=_average(scores),
            average_strategic_alignment=_average(alignment),
            high_risk_count=sum(item.risk_bucket == "HIGH" for item in selected),
            analytical_status=analytical,
            selected_capex=selected_capex,
            selected_expense=selected_expense,
            selected_unclassified=selected_unclassified,
            capex_target=capex_target,
            expense_target=expense_target,
            unallocated_target=budget - Decimal(capex_target or 0) - Decimal(expense_target or 0),
            capex_variance=capex_target - selected_capex if capex_target is not None else None,
            expense_variance=expense_target - selected_expense if expense_target is not None else None,
            mandatory_dependency_count=int(dependency_summary.get("mandatory_dependency_count") or 0),
            unmet_mandatory_count=int(dependency_summary.get("unmet_mandatory_count") or 0),
            optional_dependency_warning_count=int(dependency_summary.get("optional_dependency_warning_count") or 0),
            forced_dependency_conflict_count=int(dependency_summary.get("forced_dependency_conflict_count") or 0),
        )

    def _period_view(
        self,
        scenario: PortfolioBudgetScenario,
        rows: list[PortfolioBudgetScenarioProject],
        target: PortfolioBudgetTarget,
    ) -> list[ScenarioPeriodOut]:
        selected = [item for item in rows if self._included(item.selection_state)]
        periods = self._period_records(target.id)
        if scenario.time_phasing_method == "UNPHASED":
            demand = sum((Decimal(item.cost_value) for item in selected), Decimal("0"))
            capex = sum((Decimal(item.capex_amount or 0) for item in selected), Decimal("0"))
            expense = sum((Decimal(item.expense_amount or 0) for item in selected), Decimal("0"))
            unclassified = sum((Decimal(item.unclassified_amount) for item in selected), Decimal("0"))
            return [
                ScenarioPeriodOut(
                    period_key="UNPHASED",
                    target=Decimal(target.total_budget_target),
                    selected_demand=demand,
                    variance=Decimal(target.total_budget_target) - demand,
                    capex_demand=capex,
                    expense_demand=expense,
                    unclassified_demand=unclassified,
                    capex_target=target.capex_budget_target,
                    expense_target=target.expense_budget_target,
                    capex_variance=(
                        Decimal(target.capex_budget_target) - capex if target.capex_budget_target is not None else None
                    ),
                    expense_variance=(
                        Decimal(target.expense_budget_target) - expense
                        if target.expense_budget_target is not None
                        else None
                    ),
                )
            ]
        if not periods:
            periods = self._generated_periods(target)
        demand_by_period = {item.period_key: Decimal("0") for item in periods}
        capex_by_period = {item.period_key: Decimal("0") for item in periods}
        expense_by_period = {item.period_key: Decimal("0") for item in periods}
        unclassified_by_period = {item.period_key: Decimal("0") for item in periods}
        if scenario.time_phasing_method == "CUSTOM_PERIOD_PROFILE":
            for row in selected:
                for item in row.period_profile_json or []:
                    key = str(item.get("period_key") or "")
                    if key in demand_by_period:
                        total = Decimal(str(item.get("amount") or 0))
                        capex = Decimal(str(item.get("capex_amount") or 0))
                        expense = Decimal(str(item.get("expense_amount") or 0))
                        unclassified = Decimal(str(item.get("unclassified_amount") or (total - capex - expense)))
                        if capex + expense + unclassified != total or min(capex, expense, unclassified) < 0:
                            raise HTTPException(status_code=422, detail={"code": "PERIOD_PROFILE_BREAKDOWN_MISMATCH"})
                        demand_by_period[key] += total
                        capex_by_period[key] += capex
                        expense_by_period[key] += expense
                        unclassified_by_period[key] += unclassified
        else:
            for row in selected:
                applicable = [
                    period
                    for period in periods
                    if row.target_start is not None
                    and row.target_finish is not None
                    and period.period_end >= row.target_start
                    and period.period_start <= row.target_finish
                ]
                if not applicable:
                    continue
                share = Decimal(row.cost_value) / Decimal(len(applicable))
                capex_share = Decimal(row.capex_amount or 0) / Decimal(len(applicable))
                expense_share = Decimal(row.expense_amount or 0) / Decimal(len(applicable))
                unclassified_share = Decimal(row.unclassified_amount) / Decimal(len(applicable))
                for period in applicable:
                    demand_by_period[period.period_key] += share
                    capex_by_period[period.period_key] += capex_share
                    expense_by_period[period.period_key] += expense_share
                    unclassified_by_period[period.period_key] += unclassified_share
        return [
            ScenarioPeriodOut(
                period_key=item.period_key,
                target=Decimal(item.amount),
                selected_demand=demand_by_period[item.period_key].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                variance=(Decimal(item.amount) - demand_by_period[item.period_key]).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ),
                approximation=scenario.time_phasing_method == "LINEAR_BY_PROJECT_DATES",
                capex_demand=capex_by_period[item.period_key].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                expense_demand=expense_by_period[item.period_key].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                unclassified_demand=unclassified_by_period[item.period_key].quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ),
                capex_target=item.capex_amount,
                expense_target=item.expense_amount,
                capex_variance=(
                    (Decimal(item.capex_amount) - capex_by_period[item.period_key]).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    if item.capex_amount is not None
                    else None
                ),
                expense_variance=(
                    (Decimal(item.expense_amount) - expense_by_period[item.period_key]).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    if item.expense_amount is not None
                    else None
                ),
            )
            for item in periods
        ]

    def _strategic_balance(self, rows: list[PortfolioBudgetScenarioProject]) -> dict:
        selected = [item for item in rows if self._included(item.selection_state)]
        objectives: Counter[str] = Counter()
        for row in selected:
            for item in row.strategic_objectives_json or []:
                objectives[str(item.get("code") or item.get("name") or "UNCLASSIFIED")] += 1
        return {
            "objectives": [{"key": key, "project_count": count} for key, count in sorted(objectives.items())],
            "objective_count_note": "Project counts may overlap across N:M objectives; monetary totals are not duplicated.",
            "project_types": _counter(item.project_type or "UNCLASSIFIED" for item in selected),
            "risk_buckets": _counter(item.risk_bucket for item in selected),
            "score_distribution": _counter(
                _score_bucket(Decimal(item.portfolio_evaluation_score)) for item in selected
            ),
        }

    def _refresh_delta(
        self,
        record: PortfolioBudgetScenario,
    ) -> tuple[ScenarioRefreshPreviewOut, PortfolioAnalysisOverviewOut]:
        overview = self._analysis(record.portfolio_workspace_id, require_budget=True)
        target = self._target(record.budget_target_id)
        old = {item.project_workspace_id: item for item in self._scenario_rows(record.id)}
        current = {item.project_workspace_id: item for item in overview.dataset.rows}
        rank_changes: list[dict] = []
        score_changes: list[dict] = []
        cost_changes: list[dict] = []
        date_changes: list[dict] = []
        for project_id in sorted(old.keys() & current.keys()):
            before, after = old[project_id], current[project_id]
            if before.portfolio_rank != after.portfolio_rank:
                rank_changes.append(
                    {"project_id": project_id, "before": before.portfolio_rank, "after": after.portfolio_rank}
                )
            if Decimal(before.portfolio_evaluation_score) != Decimal(after.portfolio_evaluation_score):
                score_changes.append(
                    {
                        "project_id": project_id,
                        "before": before.portfolio_evaluation_score,
                        "after": after.portfolio_evaluation_score,
                    }
                )
            if Decimal(before.cost_value) != Decimal(after.rom_cost or 0) or before.currency != after.currency:
                cost_changes.append(
                    {
                        "project_id": project_id,
                        "before": str(before.cost_value),
                        "after": str(after.rom_cost),
                        "currency": after.currency,
                    }
                )
            if before.target_start != after.target_start or before.target_finish != after.target_finish:
                date_changes.append(
                    {
                        "project_id": project_id,
                        "before": [before.target_start, before.target_finish],
                        "after": [after.target_start, after.target_finish],
                    }
                )
        proposed = self._source_hash_from_analysis(record, target, overview)
        return (
            ScenarioRefreshPreviewOut(
                scenario_id=record.id,
                current_source_hash=record.source_hash,
                proposed_source_hash=proposed,
                projects_added=sorted(current.keys() - old.keys()),
                projects_removed=sorted(old.keys() - current.keys()),
                rank_changes=rank_changes,
                score_changes=score_changes,
                cost_changes=cost_changes,
                date_changes=date_changes,
                persisted=False,
            ),
            overview,
        )

    def _recalculate_scenario(self, record: PortfolioBudgetScenario) -> None:
        rows = self._scenario_rows(record.id)
        target = self._target(record.budget_target_id)
        summary = self._summary(rows, target)
        record.analytical_status = summary.analytical_status
        record.scenario_hash = _hash(
            {
                "source_hash": record.source_hash,
                "status": record.status,
                "time_phasing_method": record.time_phasing_method,
                "rows": [
                    {
                        "project": item.project_workspace_id,
                        "selection": item.selection_state,
                        "forced_reason": item.forced_reason,
                        "row_hash": item.row_hash,
                        "period_profile": item.period_profile_json,
                    }
                    for item in rows
                ],
            }
        )

    # ------------------------------------------------------------------
    # Validation and persistence helpers
    # ------------------------------------------------------------------
    def _analysis(
        self,
        portfolio_id: int,
        *,
        require_budget: bool,
        expected_hash: str | None = None,
    ) -> PortfolioAnalysisOverviewOut:
        analysis = PortfolioAnalysisService(self.db, self.tenant_id, self.actor_id, self.context).overview(
            portfolio_id,
            AnalysisFiltersIn(),
        )
        if expected_hash is not None and analysis.dataset.analysis_hash != expected_hash:
            self._event(
                "portfolio_budget.stale_source_detected",
                "EnterpriseWorkspace",
                portfolio_id,
                {"expected": expected_hash, "actual": analysis.dataset.analysis_hash},
            )
            self.db.commit()
            raise HTTPException(
                status_code=412,
                detail={
                    "code": "STALE_PORTFOLIO_BUDGET_SOURCE",
                    "expected": expected_hash,
                    "actual": analysis.dataset.analysis_hash,
                },
            )
        if require_budget and (
            analysis.readiness.final_output != READY_INPUT or not analysis.readiness.can_enter_budget_planning
        ):
            code = (
                "MULTI_CURRENCY_NOT_NORMALIZED"
                if "MULTI_CURRENCY_NOT_NORMALIZED" in analysis.readiness.warnings
                else "PORTFOLIO_BUDGET_PLANNING_NOT_ELIGIBLE"
            )
            raise HTTPException(
                status_code=409,
                detail={"code": code, "warnings": analysis.readiness.warnings, "blockers": analysis.readiness.blockers},
            )
        return analysis

    def _validate_target_payload(self, payload, policy: dict, overview: PortfolioAnalysisOverviewOut) -> None:
        configured = str(dict(policy.get("budget_currency_policy", {})).get("budget_currency") or "").upper()
        currency = payload.budget_currency.upper()
        if configured and currency != configured:
            raise HTTPException(
                status_code=422, detail={"code": "BUDGET_CURRENCY_POLICY_MISMATCH", "expected": configured}
            )
        if currency not in {item.currency for item in overview.dataset.rows}:
            raise HTTPException(status_code=422, detail={"code": "BUDGET_CURRENCY_NOT_PRESENT_IN_SOURCE"})
        periods = payload.periods
        if len({item.period_key for item in periods}) != len(periods):
            raise HTTPException(status_code=422, detail={"code": "DUPLICATE_BUDGET_TARGET_PERIOD"})
        if any(
            item.period_start < payload.planning_horizon_start or item.period_end > payload.planning_horizon_end
            for item in periods
        ):
            raise HTTPException(status_code=422, detail={"code": "BUDGET_TARGET_PERIOD_OUTSIDE_HORIZON"})
        if policy.get("period_targets_must_sum_total", True) and periods:
            if sum((item.amount for item in periods), Decimal("0")) != payload.total_budget_target:
                raise HTTPException(status_code=422, detail={"code": "PERIOD_TARGET_TOTAL_MISMATCH"})
        capex_target = Decimal(payload.capex_budget_target or 0)
        expense_target = Decimal(payload.expense_budget_target or 0)
        breakdown_policy = dict(policy.get("capex_expense", {}))
        if breakdown_policy.get("require_target_breakdown") and (
            payload.capex_budget_target is None or payload.expense_budget_target is None
        ):
            raise HTTPException(status_code=422, detail={"code": "BUDGET_TARGET_BREAKDOWN_REQUIRED"})
        if capex_target + expense_target > Decimal(payload.total_budget_target):
            raise HTTPException(status_code=422, detail={"code": "BUDGET_TARGET_BREAKDOWN_TOTAL_MISMATCH"})
        if periods:
            period_capex = sum((Decimal(item.capex_amount or 0) for item in periods), Decimal("0"))
            period_expense = sum((Decimal(item.expense_amount or 0) for item in periods), Decimal("0"))
            if payload.capex_budget_target is not None and period_capex != capex_target:
                raise HTTPException(status_code=422, detail={"code": "PERIOD_CAPEX_TARGET_TOTAL_MISMATCH"})
            if payload.expense_budget_target is not None and period_expense != expense_target:
                raise HTTPException(status_code=422, detail={"code": "PERIOD_EXPENSE_TARGET_TOTAL_MISMATCH"})

    def _validate_target_record(
        self, record: PortfolioBudgetTarget, policy: dict, overview: PortfolioAnalysisOverviewOut
    ) -> None:
        class Payload:
            planning_horizon_start = record.planning_horizon_start
            planning_horizon_end = record.planning_horizon_end
            budget_currency = record.budget_currency
            total_budget_target = Decimal(record.total_budget_target)
            capex_budget_target = (
                Decimal(record.capex_budget_target) if record.capex_budget_target is not None else None
            )
            expense_budget_target = (
                Decimal(record.expense_budget_target) if record.expense_budget_target is not None else None
            )
            periods = self._period_records(record.id)

        self._validate_target_payload(Payload(), policy, overview)

    def _replace_periods(self, target: PortfolioBudgetTarget, periods) -> None:
        self.db.execute(
            delete(PortfolioBudgetTargetPeriod).where(
                PortfolioBudgetTargetPeriod.tenant_id == self.tenant_id,
                PortfolioBudgetTargetPeriod.budget_target_id == target.id,
            )
        )
        for item in periods:
            self.db.add(
                PortfolioBudgetTargetPeriod(
                    tenant_id=self.tenant_id,
                    budget_target_id=target.id,
                    period_key=item.period_key,
                    period_start=item.period_start,
                    period_end=item.period_end,
                    amount=item.amount,
                    capex_amount=item.capex_amount,
                    expense_amount=item.expense_amount,
                )
            )
        self.db.flush()

    def _target_hash(self, target: PortfolioBudgetTarget) -> str:
        return _hash(
            {
                "portfolio_workspace_id": target.portfolio_workspace_id,
                "revision": target.target_revision,
                "horizon": [target.planning_horizon_start, target.planning_horizon_end],
                "granularity": target.period_granularity,
                "currency": target.budget_currency,
                "total": str(target.total_budget_target),
                "capex_target": str(target.capex_budget_target) if target.capex_budget_target is not None else None,
                "expense_target": (
                    str(target.expense_budget_target) if target.expense_budget_target is not None else None
                ),
                "periods": [
                    {
                        "key": item.period_key,
                        "start": item.period_start,
                        "end": item.period_end,
                        "amount": str(item.amount),
                        "capex_amount": str(item.capex_amount) if item.capex_amount is not None else None,
                        "expense_amount": str(item.expense_amount) if item.expense_amount is not None else None,
                    }
                    for item in self._period_records(target.id)
                ],
                "source_reference": target.source_reference,
            }
        )

    @staticmethod
    def _budget_breakdown(
        workspace: EnterpriseWorkspace | None, cost: Decimal
    ) -> tuple[Decimal | None, Decimal | None, Decimal, str]:
        """Read an explicitly governed split; never infer CAPEX/EXPENSE from the total."""
        payload = dict((workspace.defaults_json or {}).get("planning_budget_breakdown", {})) if workspace else {}
        if not payload:
            return None, None, cost, "UNCLASSIFIED_SOURCE"
        capex = Decimal(str(payload["capex_amount"])) if payload.get("capex_amount") is not None else None
        expense = Decimal(str(payload["expense_amount"])) if payload.get("expense_amount") is not None else None
        if Decimal(capex or 0) < 0 or Decimal(expense or 0) < 0:
            raise HTTPException(status_code=422, detail={"code": "NEGATIVE_BUDGET_BREAKDOWN_NOT_ALLOWED"})
        classified = Decimal(capex or 0) + Decimal(expense or 0)
        if classified > cost:
            raise HTTPException(status_code=422, detail={"code": "BUDGET_BREAKDOWN_TOTAL_MISMATCH"})
        return capex, expense, cost - classified, str(payload.get("source_reference") or "PROJECT_GOVERNED_DATA")

    def _source_hash(
        self,
        scenario: PortfolioBudgetScenario,
        target: PortfolioBudgetTarget,
        rows: list[PortfolioBudgetScenarioProject],
    ) -> str:
        return _hash(
            {
                "analysis_hash": scenario.source_analysis_hash,
                "membership_set_hash": scenario.membership_set_hash,
                "evaluation_set_hash": scenario.evaluation_set_hash,
                "prioritization_hash": scenario.source_prioritization_hash,
                "budget_target_hash": target.target_hash,
                "cost_sources": sorted((item.project_workspace_id, item.cost_source_hash) for item in rows),
            }
        )

    def _source_hash_from_analysis(
        self,
        scenario: PortfolioBudgetScenario,
        target: PortfolioBudgetTarget,
        overview: PortfolioAnalysisOverviewOut,
    ) -> str:
        project_ids = [item.project_workspace_id for item in overview.dataset.rows]
        workspaces = {
            item.id: item
            for item in self.db.scalars(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id.in_(project_ids),
                )
            ).all()
        }
        cost_sources = [
            (
                item.project_workspace_id,
                _hash(
                    {
                        "planning_entry_hash": item.planning_entry_hash,
                        "evaluation_hash": item.evaluation_hash,
                        "value": str(Decimal(item.rom_cost or 0)),
                        "currency": item.currency,
                        "breakdown": self._budget_breakdown(
                            workspaces.get(item.project_workspace_id), Decimal(item.rom_cost or 0)
                        ),
                    }
                ),
            )
            for item in overview.dataset.rows
        ]
        return _hash(
            {
                "analysis_hash": overview.dataset.analysis_hash,
                "membership_set_hash": overview.dataset.membership_set_hash,
                "evaluation_set_hash": overview.dataset.evaluation_set_hash,
                "prioritization_hash": overview.dataset.source_prioritization_hash,
                "budget_target_hash": target.target_hash,
                "cost_sources": sorted(cost_sources),
            }
        )

    @staticmethod
    def _legacy_source_hash_from_analysis(
        scenario: PortfolioBudgetScenario,
        target: PortfolioBudgetTarget,
        overview: PortfolioAnalysisOverviewOut,
    ) -> str:
        cost_sources = [
            (
                item.project_workspace_id,
                _hash(
                    {
                        "planning_entry_hash": item.planning_entry_hash,
                        "evaluation_hash": item.evaluation_hash,
                        "value": str(Decimal(item.rom_cost or 0)),
                        "currency": item.currency,
                    }
                ),
            )
            for item in overview.dataset.rows
        ]
        return _hash(
            {
                "analysis_hash": overview.dataset.analysis_hash,
                "membership_set_hash": overview.dataset.membership_set_hash,
                "evaluation_set_hash": overview.dataset.evaluation_set_hash,
                "prioritization_hash": overview.dataset.source_prioritization_hash,
                "budget_target_hash": target.target_hash,
                "cost_sources": sorted(cost_sources),
            }
        )

    def _row_hash(self, row: PortfolioBudgetScenarioProject) -> str:
        return _hash(
            {
                "project_workspace_id": row.project_workspace_id,
                "rank": row.portfolio_rank,
                "score": str(row.portfolio_evaluation_score),
                "analysis_hash": row.gate07f_analysis_hash,
                "cost_source_hash": row.cost_source_hash,
                "cost": str(row.cost_value),
                "capex": str(row.capex_amount) if row.capex_amount is not None else None,
                "expense": str(row.expense_amount) if row.expense_amount is not None else None,
                "unclassified": str(row.unclassified_amount),
                "breakdown_source": row.budget_breakdown_source,
                "currency": row.currency,
                "dates": [row.target_start, row.target_finish],
                "selection": row.selection_state,
                "forced_reason": row.forced_reason,
            }
        )

    def _target_out(self, record: PortfolioBudgetTarget) -> BudgetTargetOut:
        return BudgetTargetOut(
            id=record.id,
            tenant_id=record.tenant_id,
            portfolio_workspace_id=record.portfolio_workspace_id,
            target_code=record.target_code,
            target_revision=record.target_revision,
            planning_horizon_start=record.planning_horizon_start,
            planning_horizon_end=record.planning_horizon_end,
            period_granularity=record.period_granularity,
            budget_currency=record.budget_currency,
            total_budget_target=record.total_budget_target,
            capex_budget_target=record.capex_budget_target,
            expense_budget_target=record.expense_budget_target,
            unallocated_budget_target=(
                Decimal(record.total_budget_target)
                - Decimal(record.capex_budget_target or 0)
                - Decimal(record.expense_budget_target or 0)
            ),
            periods=[TargetPeriodOut.model_validate(item) for item in self._period_records(record.id)],
            source_reference=record.source_reference,
            notes=record.notes,
            status=record.status,
            target_hash=record.target_hash,
            revision_version=record.revision_version,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_by=record.updated_by,
            updated_at=record.updated_at,
            published_at=record.published_at,
        )

    @staticmethod
    def _project_out(row: PortfolioBudgetScenarioProject, dependency: dict | None = None) -> ScenarioProjectOut:
        dependency = dependency or {}
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
            cost_source_type=row.cost_source_type,
            cost_source_reference=row.cost_source_reference,
            cost_source_hash=row.cost_source_hash,
            cost_value=row.cost_value,
            capex_amount=row.capex_amount,
            expense_amount=row.expense_amount,
            unclassified_amount=row.unclassified_amount,
            budget_breakdown_source=row.budget_breakdown_source,
            currency=row.currency,
            cost_as_of_date=row.cost_as_of_date,
            target_start=row.target_start,
            target_finish=row.target_finish,
            strategic_objectives=list(row.strategic_objectives_json or []),
            risk_summary=list(row.risk_summary_json or []),
            expected_benefits=row.expected_benefits,
            project_type=row.project_type,
            planning_stage=row.planning_stage,
            selection_state=row.selection_state,
            forced_reason=row.forced_reason,
            forced_actor_id=row.forced_actor_id,
            forced_at=row.forced_at,
            forced_authority_reference=row.forced_authority_reference,
            period_profile=list(row.period_profile_json or []),
            warnings=list(row.warnings_json or []),
            dependency_status=str(dependency.get("status") or "NOT_APPLICABLE"),
            unmet_dependency_count=int(dependency.get("unmet_count") or 0),
            dependency_details=list(dependency.get("details") or []),
            row_hash=row.row_hash,
            revision_version=row.revision_version,
        )

    def _generated_periods(self, target: PortfolioBudgetTarget) -> list[PortfolioBudgetTargetPeriod]:
        if target.period_granularity != "YEAR":
            return []
        years = list(range(target.planning_horizon_start.year, target.planning_horizon_end.year + 1))
        share = Decimal(target.total_budget_target) / Decimal(len(years)) if years else Decimal("0")
        return [
            PortfolioBudgetTargetPeriod(
                id=-(index + 1),
                tenant_id=self.tenant_id,
                budget_target_id=target.id,
                period_key=str(year),
                period_start=max(date(year, 1, 1), target.planning_horizon_start),
                period_end=min(date(year, 12, 31), target.planning_horizon_end),
                amount=share,
            )
            for index, year in enumerate(years)
        ]

    def _planning_horizon(self, target_id: int) -> dict:
        target = self._target(target_id)
        return {
            "start": target.planning_horizon_start,
            "end": target.planning_horizon_end,
            "granularity": target.period_granularity,
        }

    def _touch_scenario(self, record: PortfolioBudgetScenario) -> None:
        record.updated_by = self.actor_id
        record.updated_at = utc_now()
        record.revision_version += 1

    @staticmethod
    def _assert_scenario_editable(record: PortfolioBudgetScenario) -> None:
        if record.status not in {"DRAFT", "IN_REVIEW"}:
            raise HTTPException(status_code=409, detail={"code": "FROZEN_BUDGET_SCENARIO_IMMUTABLE"})

    @staticmethod
    def _included(selection_state: str) -> bool:
        return selection_state in {"SELECTED", "FORCED_IN"}

    def _allowed_actions(self, can_enter: bool) -> list[str]:
        roles = self.context.role_codes if self.context else frozenset({"organization_admin"})
        actions = [
            "can_view_budget_planning",
            "can_compare_budget_scenarios",
            "can_view_waterline",
            "can_view_project_dependencies",
            "can_view_dependency_status",
            "can_view_capex_expense_breakdown",
        ]
        if roles & {"organization_admin", "portfolio_budget_planner"}:
            actions.extend(
                [
                    "can_create_budget_target",
                    "can_publish_budget_target",
                    "can_create_budget_scenario",
                    "can_edit_budget_scenario",
                    "can_clone_budget_scenario",
                    "can_freeze_budget_scenario",
                    "can_void_budget_scenario",
                    "can_force_in",
                    "can_force_out",
                    "can_refresh_budget_scenario_source",
                    "can_create_project_dependency",
                    "can_edit_project_dependency",
                    "can_deactivate_project_dependency",
                ]
            )
        if can_enter:
            actions.append("can_enter_budget_recommendation")
        return sorted(set(actions))

    def _portfolio_project_ids(self, portfolio_id: int) -> list[int]:
        self._portfolio(portfolio_id)
        return list(
            self.db.scalars(
                select(PortfolioProjectMembership.project_workspace_id).where(
                    PortfolioProjectMembership.tenant_id == self.tenant_id,
                    PortfolioProjectMembership.portfolio_workspace_id == portfolio_id,
                    PortfolioProjectMembership.status == "ACTIVE",
                )
            ).all()
        )

    def _project_workspace(self, project_id: int) -> EnterpriseWorkspace:
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.id == project_id,
            )
        )
        if workspace is None:
            raise HTTPException(status_code=404, detail="Project Workspace not found")
        if workspace.workspace_type_code.lower() != "project":
            raise HTTPException(status_code=422, detail={"code": "DEPENDENCY_ENDPOINT_MUST_BE_PROJECT"})
        return workspace

    def _dependency(self, dependency_id: int, *, lock: bool = False) -> ProjectDependency:
        statement = select(ProjectDependency).where(
            ProjectDependency.tenant_id == self.tenant_id,
            ProjectDependency.id == dependency_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Project Dependency not found")
        return record

    def _dependency_out(
        self,
        record: ProjectDependency,
        workspaces: dict[int, EnterpriseWorkspace] | None = None,
    ) -> ProjectDependencyOut:
        predecessor = (
            workspaces.get(record.predecessor_project_workspace_id)
            if workspaces is not None
            else self._project_workspace(record.predecessor_project_workspace_id)
        )
        successor = (
            workspaces.get(record.successor_project_workspace_id)
            if workspaces is not None
            else self._project_workspace(record.successor_project_workspace_id)
        )
        if predecessor is None or successor is None:
            raise HTTPException(status_code=409, detail={"code": "PROJECT_DEPENDENCY_ENDPOINT_MISSING"})
        if predecessor.workspace_type_code.lower() != "project" or successor.workspace_type_code.lower() != "project":
            raise HTTPException(status_code=409, detail={"code": "DEPENDENCY_ENDPOINT_MUST_BE_PROJECT"})
        return ProjectDependencyOut(
            id=record.id,
            tenant_id=record.tenant_id,
            predecessor_project_workspace_id=predecessor.id,
            predecessor_project_number=predecessor.record_code,
            predecessor_project_name=predecessor.name,
            successor_project_workspace_id=successor.id,
            successor_project_number=successor.record_code,
            successor_project_name=successor.name,
            dependency_type=record.dependency_type,
            dependency_strength=record.dependency_strength,
            description=record.description,
            effective_from=record.effective_from,
            effective_to=record.effective_to,
            status=record.status,
            source_reference=record.source_reference,
            evidence_refs=list(record.evidence_refs_json or []),
            revision_version=record.revision_version,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_by=record.updated_by,
            updated_at=record.updated_at,
        )

    def _active_dependencies(self, project_ids: set[int]) -> list[ProjectDependency]:
        if not project_ids:
            return []
        today = date.today()
        return list(
            self.db.scalars(
                select(ProjectDependency).where(
                    ProjectDependency.tenant_id == self.tenant_id,
                    ProjectDependency.status == "ACTIVE",
                    ProjectDependency.predecessor_project_workspace_id.in_(project_ids),
                    ProjectDependency.successor_project_workspace_id.in_(project_ids),
                    or_(ProjectDependency.effective_from.is_(None), ProjectDependency.effective_from <= today),
                    or_(ProjectDependency.effective_to.is_(None), ProjectDependency.effective_to >= today),
                )
            ).all()
        )

    def _creates_dependency_cycle(
        self,
        predecessor_id: int,
        successor_id: int,
        *,
        exclude_dependency_id: int | None = None,
    ) -> bool:
        records = list(
            self.db.scalars(
                select(ProjectDependency).where(
                    ProjectDependency.tenant_id == self.tenant_id,
                    ProjectDependency.status == "ACTIVE",
                    ProjectDependency.dependency_strength == "MANDATORY",
                    *([ProjectDependency.id != exclude_dependency_id] if exclude_dependency_id is not None else []),
                )
            ).all()
        )
        outgoing: dict[int, set[int]] = {}
        for item in records:
            outgoing.setdefault(item.predecessor_project_workspace_id, set()).add(item.successor_project_workspace_id)
        pending = [successor_id]
        visited: set[int] = set()
        while pending:
            current = pending.pop()
            if current == predecessor_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            pending.extend(outgoing.get(current, set()) - visited)
        return False

    def _dependency_evaluation(
        self, scenario: PortfolioBudgetScenario, rows: list[PortfolioBudgetScenarioProject]
    ) -> dict:
        row_by_id = {item.project_workspace_id: item for item in rows}
        policy = self._policy(scenario.portfolio_workspace_id, require_published=False)
        dependency_policy = dict(policy.get("dependencies", {}))
        if not dependency_policy.get("enabled", True):
            return {
                "summary": {
                    "mandatory_dependency_count": 0,
                    "unmet_mandatory_count": 0,
                    "optional_dependency_warning_count": 0,
                    "forced_dependency_conflict_count": 0,
                    "evaluation_source": "DISABLED_BY_GOVERNED_CONFIGURATION",
                    "persisted": False,
                },
                "projects": {
                    project_id: {
                        "project_workspace_id": project_id,
                        "project_number": row.project_number,
                        "project_name": row.project_name,
                        "selection_state": row.selection_state,
                        "status": "NOT_APPLICABLE",
                        "unmet_count": 0,
                        "details": [],
                    }
                    for project_id, row in row_by_id.items()
                },
                "warnings": [],
                "blockers": [],
            }
        dependencies = self._active_dependencies(set(row_by_id))
        incoming: dict[int, list[ProjectDependency]] = {}
        for item in dependencies:
            incoming.setdefault(item.successor_project_workspace_id, []).append(item)
        result: dict[int, dict] = {}
        optional_count = 0
        forced_conflicts = 0
        unmet_count = 0
        for project_id, row in row_by_id.items():
            details: list[dict] = []
            if self._included(row.selection_state):
                for edge in incoming.get(project_id, []):
                    predecessor = row_by_id[edge.predecessor_project_workspace_id]
                    if self._included(predecessor.selection_state):
                        continue
                    issue = (
                        "OPTIONAL_DEPENDENCY_WARNING" if edge.dependency_strength == "OPTIONAL" else "UNMET_DEPENDENCY"
                    )
                    if (
                        edge.dependency_strength == "MANDATORY"
                        and row.selection_state == "FORCED_IN"
                        and predecessor.selection_state == "FORCED_OUT"
                    ):
                        issue = "FORCED_DEPENDENCY_CONFLICT"
                        forced_conflicts += 1
                    if edge.dependency_strength == "OPTIONAL":
                        optional_count += 1
                    else:
                        unmet_count += 1
                    details.append(
                        {
                            "dependency_id": edge.id,
                            "issue": issue,
                            "strength": edge.dependency_strength,
                            "predecessor_project_workspace_id": predecessor.project_workspace_id,
                            "predecessor_project_number": predecessor.project_number,
                            "predecessor_selection_state": predecessor.selection_state,
                        }
                    )
                direct_missing = {
                    item["predecessor_project_workspace_id"] for item in details if item["strength"] == "MANDATORY"
                }
                visited: set[int] = set()
                pending = [
                    edge.predecessor_project_workspace_id
                    for edge in incoming.get(project_id, [])
                    if edge.dependency_strength == "MANDATORY"
                    and self._included(row_by_id[edge.predecessor_project_workspace_id].selection_state)
                ]
                while pending:
                    current = pending.pop()
                    if current in visited:
                        continue
                    visited.add(current)
                    for edge in incoming.get(current, []):
                        if edge.dependency_strength != "MANDATORY":
                            continue
                        predecessor = row_by_id[edge.predecessor_project_workspace_id]
                        if self._included(predecessor.selection_state):
                            pending.append(predecessor.project_workspace_id)
                        elif predecessor.project_workspace_id not in direct_missing:
                            details.append(
                                {
                                    "dependency_id": edge.id,
                                    "issue": "TRANSITIVE_UNMET_DEPENDENCY",
                                    "strength": "MANDATORY",
                                    "predecessor_project_workspace_id": predecessor.project_workspace_id,
                                    "predecessor_project_number": predecessor.project_number,
                                    "predecessor_selection_state": predecessor.selection_state,
                                }
                            )
                            direct_missing.add(predecessor.project_workspace_id)
                            unmet_count += 1
            mandatory_issues = [item for item in details if item["strength"] == "MANDATORY"]
            optional_issues = [item for item in details if item["strength"] == "OPTIONAL"]
            result[project_id] = {
                "project_workspace_id": project_id,
                "project_number": row.project_number,
                "project_name": row.project_name,
                "selection_state": row.selection_state,
                "status": (
                    "NOT_APPLICABLE"
                    if not self._included(row.selection_state)
                    else "UNMET"
                    if mandatory_issues
                    else "OPTIONAL_WARNING"
                    if optional_issues
                    else "MET"
                    if incoming.get(project_id)
                    else "NOT_APPLICABLE"
                ),
                "unmet_count": len(mandatory_issues),
                "details": details,
            }
        summary = {
            "mandatory_dependency_count": sum(item.dependency_strength == "MANDATORY" for item in dependencies),
            "unmet_mandatory_count": unmet_count,
            "optional_dependency_warning_count": optional_count,
            "forced_dependency_conflict_count": forced_conflicts,
            "evaluation_source": "DERIVED_FROM_ACTIVE_PROJECT_DEPENDENCIES",
            "persisted": False,
        }
        warnings = []
        blockers = []
        if optional_count:
            warnings.append("OPTIONAL_PROJECT_DEPENDENCY_NOT_SELECTED")
        if forced_conflicts:
            warnings.append("FORCED_PROJECT_DEPENDENCY_CONFLICT")
        if unmet_count and dependency_policy.get("mandatory_unmet_policy", "BLOCK_FREEZE") == "BLOCK_FREEZE":
            blockers.append("UNMET_MANDATORY_PROJECT_DEPENDENCY")
        elif unmet_count:
            warnings.append("UNMET_MANDATORY_PROJECT_DEPENDENCY")
        return {
            "summary": summary,
            "projects": result,
            "warnings": sorted(set(warnings)),
            "blockers": sorted(set(blockers)),
        }

    def _emit_readiness_change(self, portfolio_id: int) -> None:
        result = self.readiness(portfolio_id)
        self._event(
            "portfolio_budget.readiness_changed",
            "EnterpriseWorkspace",
            portfolio_id,
            {"final_output": result.final_output, "budget_planning_hash": result.budget_planning_hash},
        )

    # ------------------------------------------------------------------
    # Configuration validation/inheritance and lookups
    # ------------------------------------------------------------------
    def _configuration_issues(self, content: dict) -> list[str]:
        content = self._merged_configuration(content)
        issues: list[str] = []
        scope = dict(content.get("scope", {}))
        if scope.get("type", "tenant") not in {"tenant", "enterprise", "business-unit", "portfolio"}:
            issues.append("INVALID_CONFIGURATION_SCOPE")
        if scope.get("type", "tenant") != "tenant" and not scope.get("workspace_id"):
            issues.append("SCOPED_CONFIGURATION_WORKSPACE_REQUIRED")
        if list(content.get("applicable_governance_models", [])) != ["CAPITAL_OWNER"]:
            issues.append("GATE07G_ONLY_SUPPORTS_CAPITAL_OWNER")
        currency = dict(content.get("budget_currency_policy", {}))
        if currency.get("mode") != "FIXED" or not str(currency.get("budget_currency") or "").strip():
            issues.append("SINGLE_GOVERNED_BUDGET_CURRENCY_REQUIRED")
        if currency.get("fx_conversion") not in {False, None}:
            issues.append("FX_CONVERSION_NOT_ALLOWED_IN_GATE07G")
        cost_types = list(content.get("allowed_cost_source_types", []))
        if not cost_types or any(
            item
            not in {"GATE07F_ROM_COST", "GOVERNED_PORTFOLIO_PLANNING_ESTIMATE", "APPROVED_PROJECT_DEFINITION_ESTIMATE"}
            for item in cost_types
        ):
            issues.append("INVALID_COST_SOURCE_POLICY")
        methods = list(content.get("allowed_time_phasing_methods", []))
        if not methods or not set(methods) <= VALID_TIME_METHODS:
            issues.append("INVALID_TIME_PHASING_POLICY")
        if content.get("default_time_phasing_method") not in methods:
            issues.append("DEFAULT_TIME_PHASING_NOT_ALLOWED")
        if content.get("period_granularity") not in {"YEAR", "QUARTER", "MONTH"}:
            issues.append("INVALID_PERIOD_GRANULARITY")
        try:
            if not (1 <= int(content.get("scenario_max_count", 0)) <= 20):
                raise ValueError
            if not (0 <= Decimal(str(content.get("required_cost_coverage_percent", 0))) <= 100):
                raise ValueError
        except Exception:
            issues.append("INVALID_BUDGET_POLICY_LIMIT")
        if set(content.get("selection_states", [])) != VALID_SELECTION_STATES:
            issues.append("INVALID_SCENARIO_SELECTION_STATES")
        waterline = dict(content.get("waterline", {}))
        if waterline.get("default_sort", "GATE07E_RANK") != "GATE07E_RANK":
            issues.append("WATERLINE_MUST_REUSE_GATE07E_RANK")
        if waterline.get("waterline_warning_policy", "DISPLAY") not in {"DISPLAY", "HIDE"}:
            issues.append("INVALID_WATERLINE_WARNING_POLICY")
        dependencies = dict(content.get("dependencies", {}))
        valid_dependency_types = {
            "PREREQUISITE",
            "ENABLING",
            "SEQUENTIAL",
            "SHARED_INFRASTRUCTURE",
            "REGULATORY",
            "FUNDING",
            "OTHER",
        }
        if not set(dependencies.get("types", [])) <= valid_dependency_types:
            issues.append("INVALID_PROJECT_DEPENDENCY_TYPES")
        if set(dependencies.get("strength_values", [])) != {"MANDATORY", "OPTIONAL"}:
            issues.append("INVALID_PROJECT_DEPENDENCY_STRENGTH_VALUES")
        if dependencies.get("mandatory_unmet_policy", "BLOCK_FREEZE") not in {"BLOCK_FREEZE", "WARN"}:
            issues.append("INVALID_MANDATORY_DEPENDENCY_POLICY")
        try:
            if not (1 <= int(dependencies.get("max_graph_depth", 100)) <= 500):
                raise ValueError
        except Exception:
            issues.append("INVALID_PROJECT_DEPENDENCY_GRAPH_DEPTH")
        breakdown = dict(content.get("capex_expense", {}))
        if breakdown.get("allow_unclassified", True) is not True:
            issues.append("UNCLASSIFIED_BUDGET_MUST_REMAIN_AVAILABLE")
        serialized = json.dumps(content, ensure_ascii=False).lower()
        forbidden = {
            "recommended_scenario_id",
            "selected_scenario_id",
            "approved_scenario_id",
            "investment_approved",
            "execution_authorized",
            "funding_source",
            "funding_assignment",
            "resource_optimization",
            "fid_approver",
            "arbitrary_formula",
        }
        if any(term in serialized for term in forbidden):
            issues.append("DOWNSTREAM_CAPABILITY_NOT_ALLOWED_IN_GATE07G")
        return sorted(set(issues))

    def _validate_configuration(self, content: dict) -> None:
        issues = self._configuration_issues(content)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION", "issues": issues})

    def _policy(self, portfolio_id: int, *, require_published: bool) -> dict:
        record = self._effective_configuration(self._portfolio(portfolio_id), published_only=True)
        if record is None:
            if require_published:
                raise HTTPException(
                    status_code=409, detail={"code": "PUBLISHED_PORTFOLIO_BUDGET_CONFIGURATION_REQUIRED"}
                )
            return deepcopy(DEFAULT_CONFIGURATION)
        content = self._merged_configuration(record.content_json or {})
        self._validate_configuration(content)
        return content

    @staticmethod
    def _merged_configuration(content: dict) -> dict:
        merged = deepcopy(DEFAULT_CONFIGURATION)
        for key, value in deepcopy(content or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
        return merged

    def _effective_configuration(
        self,
        workspace: EnterpriseWorkspace | None,
        *,
        published_only: bool,
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
                expected = {"enterprise": "enterprise", "business-unit": "business-unit", "portfolio": "portfolio"}.get(
                    scope_type
                )
                if expected and path_ids[int(scope_id)].workspace_type_code != expected:
                    continue
                specificity = {"enterprise": 1, "business-unit": 2, "portfolio": 3}.get(scope_type, 0)
            candidates.append((specificity, record.revision, record))
        return max(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None

    def _tenant_published(self) -> AdminConfiguration | None:
        return self._effective_configuration(None, published_only=True)

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
            raise HTTPException(status_code=404, detail="Portfolio Budget configuration not found")
        return record

    def _portfolio(self, portfolio_id: int | None) -> EnterpriseWorkspace:
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == portfolio_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
            )
        )
        if workspace is None:
            raise HTTPException(status_code=404, detail="Portfolio Workspace not found")
        if workspace.workspace_type_code != "portfolio":
            raise HTTPException(status_code=422, detail={"code": "WORKSPACE_IS_NOT_PORTFOLIO"})
        self._assert_scope(workspace.id)
        return workspace

    def _target(self, target_id: int | None, *, lock: bool = False) -> PortfolioBudgetTarget:
        statement = select(PortfolioBudgetTarget).where(
            PortfolioBudgetTarget.id == target_id,
            PortfolioBudgetTarget.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Portfolio Budget Target not found")
        self._assert_scope(record.portfolio_workspace_id)
        return record

    def _scenario(self, scenario_id: int | None, *, lock: bool = False) -> PortfolioBudgetScenario:
        statement = select(PortfolioBudgetScenario).where(
            PortfolioBudgetScenario.id == scenario_id,
            PortfolioBudgetScenario.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Portfolio Budget Scenario not found")
        self._assert_scope(record.portfolio_workspace_id)
        return record

    def _target_records(self, portfolio_id: int) -> list[PortfolioBudgetTarget]:
        return list(
            self.db.scalars(
                select(PortfolioBudgetTarget)
                .where(
                    PortfolioBudgetTarget.tenant_id == self.tenant_id,
                    PortfolioBudgetTarget.portfolio_workspace_id == portfolio_id,
                )
                .order_by(PortfolioBudgetTarget.target_revision.desc())
            ).all()
        )

    def _period_records(self, target_id: int) -> list[PortfolioBudgetTargetPeriod]:
        return list(
            self.db.scalars(
                select(PortfolioBudgetTargetPeriod)
                .where(
                    PortfolioBudgetTargetPeriod.tenant_id == self.tenant_id,
                    PortfolioBudgetTargetPeriod.budget_target_id == target_id,
                )
                .order_by(PortfolioBudgetTargetPeriod.period_start, PortfolioBudgetTargetPeriod.period_key)
            ).all()
        )

    def _scenario_rows(self, scenario_id: int) -> list[PortfolioBudgetScenarioProject]:
        return list(
            self.db.scalars(
                select(PortfolioBudgetScenarioProject)
                .where(
                    PortfolioBudgetScenarioProject.tenant_id == self.tenant_id,
                    PortfolioBudgetScenarioProject.scenario_id == scenario_id,
                )
                .order_by(
                    PortfolioBudgetScenarioProject.portfolio_rank, PortfolioBudgetScenarioProject.project_workspace_id
                )
            ).all()
        )

    @staticmethod
    def _check_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise HTTPException(status_code=412, detail={"code": "ETAG_MISMATCH"})

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


def _counter(values) -> list[dict]:
    return [{"key": key, "count": count} for key, count in sorted(Counter(values).items())]


def _score_bucket(value: Decimal) -> str:
    return "HIGH" if value >= 75 else "MEDIUM" if value >= 50 else "LOW"
