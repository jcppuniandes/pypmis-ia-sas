"""Application service for Wave 3A Periodic Portfolio Review.

All source-domain integration in this module is read-only.  A Review Action is
an auditable governance instruction; dispatch records a request unless a future
explicit source-authority adapter is configured and implemented.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import (
    AdminConfiguration,
    AdminNumberSequence,
    EnterpriseWorkspace,
    SecurityEvent,
    Tenant,
    UserAccount,
)
from app.modules.capital_planning.models import (
    CapitalPlanningCycle,
    StrategicBucketClassification,
    StrategicCapitalAllocationPlan,
)
from app.modules.capital_planning.service import CapitalPlanningService
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext, ensure_enterprise_permissions
from app.modules.investment_decision.models import InvestmentDecision
from app.modules.investment_gate_preparation.models import InvestmentGatePreparation
from app.modules.portfolio_budget.models import PortfolioBudgetScenario, PortfolioBudgetScenarioProject
from app.modules.portfolio_convergence.models import PortfolioConvergedAlternative, PortfolioScenarioConvergence
from app.modules.portfolio_evaluation.models import PortfolioProjectEvaluation
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService
from app.modules.portfolio_planning.models import PortfolioProjectMembership
from app.modules.portfolio_resource.models import PortfolioResourceScenario, PortfolioResourceScenarioProject
from app.modules.portfolio_resource.service import PortfolioResourceService
from app.modules.portfolio_review.models import (
    PortfolioReviewAction,
    PortfolioReviewCommand,
    PortfolioReviewConclusion,
    PortfolioReviewSession,
    PortfolioReviewSnapshot,
)
from app.modules.portfolio_review.schemas import (
    ActionApprovalIn,
    ActionDispatchIn,
    CompleteReviewIn,
    PortfolioAllocationOut,
    PortfolioBudgetResourcesOut,
    PortfolioGateStatusOut,
    PortfolioReviewActionCreate,
    PortfolioReviewActionOut,
    PortfolioReviewActionPageOut,
    PortfolioReviewActionUpdate,
    PortfolioReviewComparisonOut,
    PortfolioReviewConclusionCreate,
    PortfolioReviewConclusionOut,
    PortfolioReviewConclusionUpdate,
    PortfolioReviewCreate,
    PortfolioReviewHistoryItemOut,
    PortfolioReviewOptionsOut,
    PortfolioReviewPageOut,
    PortfolioReviewSessionOut,
    PortfolioReviewSnapshotOut,
    PortfolioReviewTrendPointOut,
    PortfolioReviewTrendsOut,
    PortfolioReviewUpdate,
    ProjectMatrixPageOut,
    ProjectMatrixRowOut,
    ReviewConfigurationPreviewOut,
    ReviewTransitionIn,
    SnapshotCommandIn,
    SnapshotPreviewOut,
)
from app.modules.risk_readiness.models import RiskReadinessAssessment

CONFIGURATION_KIND = "portfolio_review_configuration"
DEFAULT_CONFIGURATION_CODE = "default"
REVIEW_NUMBER_RULE = "portfolio_review_session"
ACTION_NUMBER_RULE = "portfolio_review_action"

REVIEW_TERMINAL_STATES = frozenset({"COMPLETED", "CANCELLED", "SUPERSEDED"})
ACTION_TERMINAL_STATES = frozenset({"COMPLETED", "REJECTED", "CANCELLED"})
ACTION_TRANSITIONS: dict[str, frozenset[str]] = {
    "IN_PROGRESS": frozenset({"ACCEPTED"}),
    "COMPLETED": frozenset({"ACCEPTED", "IN_PROGRESS"}),
    "REJECTED": frozenset({"OPEN", "ACCEPTED"}),
    "CANCELLED": frozenset({"OPEN", "ACCEPTED", "IN_PROGRESS"}),
}
SOURCE_KEYS = frozenset(
    {
        "PORTFOLIO_MEMBERSHIP",
        "PORTFOLIO_RANK",
        "STRATEGIC_ALLOCATION",
        "BUDGET_SCENARIO",
        "RESOURCE_SCENARIO",
        "SCENARIO_RECOMMENDATION",
        "GATE_CONTEXT",
        "RISK_READINESS",
    }
)

DEFAULT_CONFIGURATION: dict[str, Any] = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "applicability": {
        "governance_models": ["CAPITAL_OWNER"],
        "portfolio_statuses": ["active", "pending"],
        "minimum_portfolio_size": 0,
    },
    "review_types": [
        {"code": "SCHEDULED", "label": "Scheduled", "active": True},
        {"code": "MONTHLY", "label": "Monthly", "active": True},
        {"code": "QUARTERLY", "label": "Quarterly", "active": True},
        {"code": "SEMIANNUAL", "label": "Semiannual", "active": True},
        {"code": "ANNUAL", "label": "Annual", "active": True},
        {"code": "AD_HOC", "label": "Ad hoc", "active": True},
        {"code": "EXCEPTION", "label": "Exception", "active": True},
    ],
    "cadence": {
        "default_type": "QUARTERLY",
        "frequency_days": 90,
        "late_after_days": 7,
    },
    "agenda_template": [
        {"code": "STRATEGIC_ALIGNMENT", "title": "Strategic Alignment", "required": True},
        {"code": "CAPITAL_ALLOCATION_BALANCE", "title": "Capital Allocation Balance", "required": True},
        {"code": "PORTFOLIO_PRIORITY", "title": "Portfolio Priority", "required": True},
        {"code": "BUDGET_POSITION", "title": "Budget Position", "required": False},
        {"code": "RESOURCE_CAPACITY", "title": "Resource Capacity", "required": False},
        {"code": "GATE_FID_STATUS", "title": "Gate / FID Status", "required": False},
        {"code": "RISK_READINESS", "title": "Risk / Readiness", "required": False},
        {"code": "EXCEPTIONS", "title": "Exceptions", "required": False},
        {"code": "PROJECTS_REQUIRING_DECISION", "title": "Projects Requiring Decision", "required": False},
        {"code": "PORTFOLIO_ACTIONS", "title": "Portfolio Actions", "required": True},
        {"code": "FOLLOW_UP_ACTIONS", "title": "Follow-up Actions", "required": False},
    ],
    "snapshot_policy": {
        "required_sources": ["PORTFOLIO_MEMBERSHIP"],
        "require_endorsed_allocation_when_selected": True,
        "require_frozen_budget_when_selected": True,
        "require_frozen_resource_when_selected": True,
        "require_recommended_convergence_when_selected": True,
        "stale_on_any_source_hash_change": True,
    },
    "source_freshness": {
        "gate_evidence_max_age_days": 90,
        "risk_readiness_max_age_days": 90,
    },
    "review_readiness": {
        "require_agenda_before_freeze": False,
        "minimum_conclusions_to_complete": 1,
        "block_complete_when_stale": True,
    },
    "conclusion_types": [
        {"code": "PORTFOLIO_BALANCED", "label": "Portfolio balanced", "active": True},
        {"code": "PORTFOLIO_REBALANCING_REQUIRED", "label": "Portfolio rebalancing required", "active": True},
        {"code": "CAPITAL_CONSTRAINED", "label": "Capital constrained", "active": True},
        {"code": "RESOURCE_CONSTRAINED", "label": "Resource constrained", "active": True},
        {"code": "STRATEGIC_MISALIGNMENT", "label": "Strategic misalignment", "active": True},
        {"code": "EXCESS_UNCLASSIFIED_EXPOSURE", "label": "Excess unclassified exposure", "active": True},
        {"code": "PORTFOLIO_REASSESSMENT_REQUIRED", "label": "Portfolio reassessment required", "active": True},
        {"code": "NO_MATERIAL_CHANGE", "label": "No material change", "active": True},
    ],
    "action_types": [
        {"code": "RETAIN_PRIORITY", "authority": "PORTFOLIO_REVIEW", "dispatch": "REQUEST_ONLY"},
        {"code": "ACCELERATE", "authority": "PORTFOLIO_REVIEW", "dispatch": "REQUEST_ONLY"},
        {"code": "DEFER", "authority": "PORTFOLIO_REVIEW", "dispatch": "REQUEST_ONLY"},
        {"code": "HOLD_FOR_CAPACITY", "authority": "PORTFOLIO_REVIEW", "dispatch": "REQUEST_ONLY"},
        {"code": "REQUEST_REASSESSMENT", "authority": "PORTFOLIO_EVALUATION", "dispatch": "REQUEST_ONLY"},
        {"code": "REMOVE_FROM_ACTIVE_PORTFOLIO", "authority": "PORTFOLIO_MEMBERSHIP", "dispatch": "REQUEST_ONLY"},
        {"code": "MOVE_BETWEEN_BUCKETS", "authority": "STRATEGIC_CAPITAL_ALLOCATION", "dispatch": "REQUEST_ONLY"},
        {"code": "REBALANCE_CAPITAL", "authority": "PORTFOLIO_BUDGET", "dispatch": "REQUEST_ONLY"},
        {"code": "REBALANCE_RESOURCES", "authority": "PORTFOLIO_RESOURCE", "dispatch": "REQUEST_ONLY"},
        {"code": "REQUEST_GATE_REVALIDATION", "authority": "INVESTMENT_GATE", "dispatch": "REQUEST_ONLY"},
        {"code": "REQUEST_BUSINESS_CASE_REVALIDATION", "authority": "BUSINESS_CASE", "dispatch": "REQUEST_ONLY"},
        {"code": "REQUEST_BENEFITS_REVALIDATION", "authority": "STRATEGIC_BENEFITS", "dispatch": "REQUEST_ONLY"},
        {"code": "OTHER_CONFIGURED_ACTION", "authority": "PORTFOLIO_REVIEW", "dispatch": "REQUEST_ONLY"},
    ],
    "action_applicability": {
        "subject_types": ["PORTFOLIO", "PROJECT", "PORTFOLIO_MEMBERSHIP", "BUCKET"],
        "priorities": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
    },
    "thresholds": {
        "bucket_variance_tolerance_percentage": "5.0",
        "unclassified_exposure_tolerance_percentage": "5.0",
        "resource_overload_threshold_percentage": "0",
        "stale_gate_evidence_tolerance_days": 90,
        "blocked_project_count": 1,
        "overdue_action_days": 0,
    },
    "authority": {"model": "SINGLE_PORTFOLIO_AUTHORITY", "quorum": 1, "voting_rule": "NOT_REQUIRED"},
    "separation_of_duties": {
        "preparer_cannot_complete": True,
        "action_creator_cannot_approve": True,
    },
    "numbering": {
        "review_prefix": "PRV",
        "review_padding": 6,
        "action_prefix": "PRA",
        "action_padding": 7,
        "separator": "-",
    },
}


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


class PortfolioReviewService:
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

    # ------------------------------------------------------------------
    # Seed / options
    # ------------------------------------------------------------------
    def ensure_seed(self) -> None:
        """Install reusable policy and numbering; never create a live Review."""
        # Serialize explicit tenant provisioning, not a side effect of a GET.
        self.db.scalar(select(Tenant).where(Tenant.id == self.tenant_id).with_for_update())
        ensure_enterprise_permissions(self.db, self.tenant_id, self.actor_id)
        existing = self.db.scalar(
            select(AdminConfiguration.id).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.code == DEFAULT_CONFIGURATION_CODE,
            )
        )
        if existing is None:
            self.db.add(
                AdminConfiguration(
                    tenant_id=self.tenant_id,
                    kind=CONFIGURATION_KIND,
                    code=DEFAULT_CONFIGURATION_CODE,
                    name="Periodic Portfolio Review",
                    description="Wave 3A reusable Portfolio governance policy; no live Review data.",
                    status="published",
                    revision=1,
                    version=1,
                    content_json=deepcopy(DEFAULT_CONFIGURATION),
                    content_hash=_hash(DEFAULT_CONFIGURATION),
                    published_at=utc_now(),
                    created_by_user_id=self.actor_id,
                )
            )
        for rule_code in (REVIEW_NUMBER_RULE, ACTION_NUMBER_RULE):
            sequence = self.db.scalar(
                select(AdminNumberSequence.id).where(
                    AdminNumberSequence.tenant_id == self.tenant_id,
                    AdminNumberSequence.rule_code == rule_code,
                    AdminNumberSequence.scope_key == "tenant",
                )
            )
            if sequence is None:
                self.db.add(
                    AdminNumberSequence(
                        tenant_id=self.tenant_id,
                        rule_code=rule_code,
                        scope_key="tenant",
                        next_value=1,
                        version=1,
                    )
                )
        self.db.commit()

    def options(self, portfolio_workspace_id: int | None = None) -> PortfolioReviewOptionsOut:
        portfolio = self._workspace(portfolio_workspace_id) if portfolio_workspace_id else None
        if portfolio is not None:
            self._assert_portfolio(portfolio)
            self._assert_scope(portfolio.id)
        effective, source, _path = self._effective_configuration(portfolio)
        portfolio_statement = select(EnterpriseWorkspace).where(
            EnterpriseWorkspace.tenant_id == self.tenant_id,
            EnterpriseWorkspace.workspace_type_code == "portfolio",
            EnterpriseWorkspace.status.in_(["active", "pending"]),
        )
        portfolio_statement = self._workspace_scope(portfolio_statement, EnterpriseWorkspace.id)
        portfolios = list(self.db.scalars(portfolio_statement.order_by(EnterpriseWorkspace.name)).all())
        allocation_statement = select(StrategicCapitalAllocationPlan).where(
            StrategicCapitalAllocationPlan.tenant_id == self.tenant_id,
            StrategicCapitalAllocationPlan.status == "ENDORSED",
        )
        allocation_statement = self._workspace_scope(
            allocation_statement,
            func.coalesce(
                StrategicCapitalAllocationPlan.portfolio_workspace_id,
                StrategicCapitalAllocationPlan.scope_workspace_id,
            ),
        )
        if portfolio is not None:
            allocation_statement = allocation_statement.where(
                or_(
                    StrategicCapitalAllocationPlan.portfolio_workspace_id == portfolio.id,
                    StrategicCapitalAllocationPlan.scope_workspace_id == portfolio.id,
                )
            )
        allocations = list(
            self.db.scalars(
                allocation_statement.order_by(
                    StrategicCapitalAllocationPlan.endorsed_at.desc(), StrategicCapitalAllocationPlan.id.desc()
                )
            ).all()
        )
        users = list(
            self.db.scalars(
                select(UserAccount)
                .where(UserAccount.tenant_id == self.tenant_id, UserAccount.status == "active")
                .order_by(UserAccount.full_name)
            ).all()
        )
        return PortfolioReviewOptionsOut(
            review_types=self._active_catalog(effective, "review_types"),
            conclusion_types=self._active_catalog(effective, "conclusion_types"),
            action_types=self._active_catalog(effective, "action_types"),
            agenda_template=deepcopy(list(effective.get("agenda_template") or [])),
            portfolios=[self._workspace_option(item) for item in portfolios],
            allocation_plans=[
                {
                    "id": item.id,
                    "code": item.allocation_plan_number,
                    "name": item.name,
                    "planning_cycle_id": item.planning_cycle_id,
                    "portfolio_workspace_id": item.portfolio_workspace_id,
                    "status": item.status,
                    "plan_hash": item.plan_hash,
                }
                for item in allocations
            ],
            users=[{"id": item.id, "name": item.full_name, "email": item.email} for item in users],
            effective_configuration=effective,
            configuration_source=source,
        )

    # ------------------------------------------------------------------
    # Review Session lifecycle
    # ------------------------------------------------------------------
    def list_sessions(
        self,
        *,
        portfolio_workspace_id: int | None = None,
        status: str | None = None,
        review_type: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PortfolioReviewPageOut:
        statement = select(PortfolioReviewSession).where(PortfolioReviewSession.tenant_id == self.tenant_id)
        statement = self._workspace_scope(statement, PortfolioReviewSession.portfolio_workspace_id)
        if portfolio_workspace_id is not None:
            self._assert_scope(portfolio_workspace_id)
            statement = statement.where(PortfolioReviewSession.portfolio_workspace_id == portfolio_workspace_id)
        status_filter = status.strip().upper() if status else None
        if status_filter:
            if status_filter == "STALE":
                statement = statement.where(PortfolioReviewSession.status.not_in(REVIEW_TERMINAL_STATES))
            else:
                statement = statement.where(PortfolioReviewSession.status == status_filter)
        if review_type:
            statement = statement.where(PortfolioReviewSession.review_type == review_type.strip().upper())
        if status_filter:
            # STALE is a derived read-model state, not an implicit write to the aggregate.
            candidates = list(
                self.db.scalars(
                    statement.order_by(PortfolioReviewSession.review_date.desc(), PortfolioReviewSession.id.desc())
                ).all()
            )
            mapped = [self._session_out(item) for item in candidates]
            matching = [item for item in mapped if item.effective_status == status_filter]
            return PortfolioReviewPageOut(
                items=matching[(page - 1) * page_size : page * page_size],
                total=len(matching),
                page=page,
                page_size=page_size,
            )
        total = int(self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
        rows = list(
            self.db.scalars(
                statement.order_by(PortfolioReviewSession.review_date.desc(), PortfolioReviewSession.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return PortfolioReviewPageOut(
            items=[self._session_out(item) for item in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def create_session(self, payload: PortfolioReviewCreate, idempotency_key: str) -> PortfolioReviewSessionOut:
        request_hash = _hash(payload.model_dump(mode="json"))
        replay = self._command_replay("CREATE_REVIEW", idempotency_key, request_hash)
        if replay is not None:
            return self._session_out(self._session(int(replay.result_json["review_session_id"])))
        duplicate = self.db.scalar(
            select(PortfolioReviewSession).where(
                PortfolioReviewSession.tenant_id == self.tenant_id,
                PortfolioReviewSession.create_idempotency_key == idempotency_key,
            )
        )
        if duplicate is not None:
            self._assert_same_request(duplicate.create_request_hash, request_hash)
            return self._session_out(duplicate)
        portfolio = self._workspace(payload.portfolio_workspace_id)
        self._assert_portfolio(portfolio)
        self._assert_scope(portfolio.id)
        self._assert_applicable_portfolio(portfolio)
        scope = self._workspace(payload.scope_workspace_id or portfolio.id)
        self._assert_scope_compatible(scope, portfolio)
        effective, source, _path = self._effective_configuration(portfolio)
        self._catalog_item(effective, "review_types", payload.review_type)
        chair_user_id = payload.chair_user_id or self.actor_id
        self._user(chair_user_id)
        if payload.secretary_user_id is not None:
            self._user(payload.secretary_user_id)
        cycle = self._cycle(payload.planning_cycle_id) if payload.planning_cycle_id else None
        plan = self._allocation_plan(payload.allocation_plan_id) if payload.allocation_plan_id else None
        self._assert_plan_compatibility(plan, portfolio, cycle)
        if cycle is None and plan is not None:
            cycle = self._cycle(plan.planning_cycle_id)
        agenda = [item.model_dump(mode="json") for item in payload.agenda] or self._default_agenda(effective)
        numbering = dict(effective.get("numbering") or {})
        review_number = self._reserve_number(
            REVIEW_NUMBER_RULE,
            prefix=str(numbering.get("review_prefix") or "PRV"),
            padding=int(numbering.get("review_padding") or 6),
            separator=str(numbering.get("separator") or "-"),
        )
        record = PortfolioReviewSession(
            tenant_id=self.tenant_id,
            review_number=review_number,
            portfolio_workspace_id=portfolio.id,
            scope_workspace_id=scope.id,
            planning_cycle_id=cycle.id if cycle else None,
            allocation_plan_id=plan.id if plan else None,
            review_type=payload.review_type,
            review_date=payload.review_date,
            review_period_start=payload.review_period_start,
            review_period_end=payload.review_period_end,
            next_planned_review_date=payload.next_planned_review_date,
            status="DRAFT",
            title=payload.title.strip() or f"Periodic Portfolio Review — {portfolio.name}",
            description=payload.description.strip(),
            chair_user_id=chair_user_id,
            secretary_user_id=payload.secretary_user_id,
            agenda_json=agenda,
            configuration_id=int(source["configuration_id"]),
            configuration_revision=int(source["revision"]),
            configuration_hash=str(source["content_hash"]),
            configuration_snapshot_json=deepcopy(effective),
            create_idempotency_key=idempotency_key,
            create_request_hash=request_hash,
            created_by_user_id=self.actor_id,
            last_modified_by_user_id=self.actor_id,
        )
        self.db.add(record)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(status_code=409, detail={"code": "PORTFOLIO_REVIEW_CONFLICT"}) from None
        self._event(
            "portfolio_review.session.created",
            "PortfolioReviewSession",
            record.id,
            {
                "portfolio_workspace_id": portfolio.id,
                "review_number": record.review_number,
                "authority_boundary": "PORTFOLIO_GOVERNANCE_NOT_PROJECT_GATE",
            },
        )
        self._record_command(
            "CREATE_REVIEW",
            idempotency_key,
            request_hash,
            review_session_id=record.id,
            result={"review_session_id": record.id},
        )
        self.db.commit()
        self.db.refresh(record)
        return self._session_out(record)

    def get_session(self, review_session_id: int) -> PortfolioReviewSessionOut:
        return self._session_out(self._session(review_session_id))

    def update_session(
        self, review_session_id: int, payload: PortfolioReviewUpdate, expected_version: int
    ) -> PortfolioReviewSessionOut:
        record = self._session(review_session_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_review_mutable(record)
        if record.status not in {"DRAFT", "PREPARING", "RETURNED", "READY_FOR_REVIEW", "IN_REVIEW", "STALE"}:
            raise HTTPException(status_code=409, detail={"code": "PORTFOLIO_REVIEW_NOT_EDITABLE"})
        values = payload.model_dump(exclude_unset=True)
        effective = self._normalized_configuration(record.configuration_snapshot_json)
        if "review_type" in values and values["review_type"] is not None:
            self._catalog_item(effective, "review_types", str(values["review_type"]))
        if "chair_user_id" in values and values["chair_user_id"] is not None:
            self._user(int(values["chair_user_id"]))
        if "secretary_user_id" in values and values["secretary_user_id"] is not None:
            self._user(int(values["secretary_user_id"]))
        if "allocation_plan_id" in values:
            plan = self._allocation_plan(values["allocation_plan_id"]) if values["allocation_plan_id"] else None
            cycle = self._cycle(record.planning_cycle_id) if record.planning_cycle_id else None
            portfolio = self._workspace(record.portfolio_workspace_id)
            self._assert_plan_compatibility(plan, portfolio, cycle)
        field_map = {
            "allocation_plan_id": "allocation_plan_id",
            "review_type": "review_type",
            "review_date": "review_date",
            "review_period_start": "review_period_start",
            "review_period_end": "review_period_end",
            "next_planned_review_date": "next_planned_review_date",
            "title": "title",
            "description": "description",
            "chair_user_id": "chair_user_id",
            "secretary_user_id": "secretary_user_id",
            "agenda": "agenda_json",
        }
        for payload_key, attribute in field_map.items():
            if payload_key not in values:
                continue
            value = values[payload_key]
            if payload_key == "agenda" and value is not None:
                value = [dict(item) for item in value]
            if payload_key in {"title", "description"} and value is not None:
                value = value.strip()
            setattr(record, attribute, value)
        if (
            record.review_period_start
            and record.review_period_end
            and record.review_period_end < record.review_period_start
        ):
            raise HTTPException(status_code=422, detail={"code": "INVALID_REVIEW_PERIOD"})
        self._touch_review(record)
        self._event("portfolio_review.session.updated", "PortfolioReviewSession", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._session_out(record)

    def prepare_session(self, review_session_id: int, expected_version: int) -> PortfolioReviewSessionOut:
        record = self._session(review_session_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status not in {"DRAFT", "RETURNED", "STALE"}:
            raise HTTPException(
                status_code=409,
                detail={"code": "INVALID_PORTFOLIO_REVIEW_TRANSITION", "status": record.status, "action": "prepare"},
            )
        record.status = "PREPARING"
        record.prepared_by_user_id = self.actor_id
        record.prepared_at = utc_now()
        self._touch_review(record)
        self._event("portfolio_review.session.preparing", "PortfolioReviewSession", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._session_out(record)

    def snapshot_preview(self, review_session_id: int, payload: SnapshotCommandIn | None = None) -> SnapshotPreviewOut:
        record = self._session(review_session_id)
        self._assert_review_mutable(record)
        candidate = self._build_snapshot(record)
        current = self._current_snapshot(record)
        changes = self._snapshot_changes(current.snapshot_json if current else None, candidate["snapshot"])
        stale = bool(current and current.source_index_json != candidate["source_index"])
        return SnapshotPreviewOut(
            review_session_id=record.id,
            candidate_snapshot_hash=candidate["snapshot_hash"],
            current_snapshot_id=current.id if current else None,
            current_snapshot_hash=current.snapshot_hash if current else None,
            source_current=not stale and bool(current),
            stale=stale,
            changes=changes,
            readiness=candidate["readiness"],
            warnings=candidate["warnings"],
            blockers=candidate["blockers"],
            source_index=candidate["source_index"],
            snapshot=candidate["snapshot"],
            generated_at=utc_now(),
        )

    def freeze_snapshot(
        self,
        review_session_id: int,
        payload: SnapshotCommandIn,
        expected_version: int,
        idempotency_key: str,
    ) -> PortfolioReviewSnapshotOut:
        request_hash = _hash({"review_session_id": review_session_id, **payload.model_dump(mode="json")})
        replay = self._command_replay("FREEZE_SNAPSHOT", idempotency_key, request_hash)
        if replay is not None:
            return self._snapshot_out(self._snapshot(int(replay.result_json["snapshot_id"])))
        record = self._session(review_session_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status not in {"PREPARING", "READY_FOR_REVIEW", "IN_REVIEW", "STALE"}:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "INVALID_PORTFOLIO_REVIEW_TRANSITION",
                    "status": record.status,
                    "action": "freeze_snapshot",
                },
            )
        candidate = self._build_snapshot(record)
        if candidate["blockers"]:
            raise HTTPException(
                status_code=409,
                detail={"code": "PORTFOLIO_REVIEW_NOT_READY", "blockers": candidate["blockers"]},
            )
        next_version = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(PortfolioReviewSnapshot.snapshot_version), 0)).where(
                        PortfolioReviewSnapshot.tenant_id == self.tenant_id,
                        PortfolioReviewSnapshot.review_session_id == record.id,
                    )
                )
                or 0
            )
            + 1
        )
        snapshot = PortfolioReviewSnapshot(
            tenant_id=self.tenant_id,
            review_session_id=record.id,
            snapshot_version=next_version,
            snapshot_json=candidate["snapshot"],
            source_index_json=candidate["source_index"],
            readiness_json=candidate["readiness"],
            warnings_json=candidate["warnings"],
            blockers_json=candidate["blockers"],
            snapshot_hash=candidate["snapshot_hash"],
            freeze_idempotency_key=idempotency_key,
            freeze_request_hash=request_hash,
            frozen_by_user_id=self.actor_id,
        )
        self.db.add(snapshot)
        self.db.flush()
        record.current_snapshot_id = snapshot.id
        record.current_snapshot_hash = snapshot.snapshot_hash
        record.snapshot_frozen_at = snapshot.frozen_at
        record.snapshot_frozen_by_user_id = self.actor_id
        selected_plan_id = dict(candidate["snapshot"].get("allocation_plan") or {}).get("id")
        if record.allocation_plan_id is None and selected_plan_id:
            record.allocation_plan_id = int(selected_plan_id)
        if record.status != "IN_REVIEW":
            record.status = "READY_FOR_REVIEW"
        self._touch_review(record)
        self._event(
            "portfolio_review.snapshot.frozen",
            "PortfolioReviewSession",
            record.id,
            {
                "snapshot_id": snapshot.id,
                "snapshot_hash": snapshot.snapshot_hash,
                "snapshot_version": snapshot.snapshot_version,
                "reason": payload.reason,
            },
        )
        self._record_command(
            "FREEZE_SNAPSHOT",
            idempotency_key,
            request_hash,
            review_session_id=record.id,
            result={"snapshot_id": snapshot.id, "review_session_id": record.id},
        )
        self.db.commit()
        self.db.refresh(snapshot)
        return self._snapshot_out(snapshot)

    def start_review(self, review_session_id: int, expected_version: int) -> PortfolioReviewSessionOut:
        record = self._session(review_session_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status != "READY_FOR_REVIEW":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "INVALID_PORTFOLIO_REVIEW_TRANSITION",
                    "status": record.status,
                    "action": "start_review",
                },
            )
        stale, _candidate = self._staleness(record)
        if stale:
            raise HTTPException(status_code=409, detail={"code": "PORTFOLIO_REVIEW_SNAPSHOT_STALE"})
        record.status = "IN_REVIEW"
        record.review_authority_user_id = self.actor_id
        record.review_started_at = utc_now()
        self._touch_review(record)
        self._event("portfolio_review.session.started", "PortfolioReviewSession", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._session_out(record)

    def complete_review(
        self,
        review_session_id: int,
        payload: CompleteReviewIn,
        expected_version: int,
        idempotency_key: str,
    ) -> PortfolioReviewSessionOut:
        request_hash = _hash({"review_session_id": review_session_id, **payload.model_dump(mode="json")})
        replay = self._command_replay("COMPLETE_REVIEW", idempotency_key, request_hash)
        if replay is not None:
            return self._session_out(self._session(int(replay.result_json["review_session_id"])))
        record = self._session(review_session_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status != "IN_REVIEW":
            raise HTTPException(
                status_code=409,
                detail={"code": "INVALID_PORTFOLIO_REVIEW_TRANSITION", "status": record.status, "action": "complete"},
            )
        config = self._normalized_configuration(record.configuration_snapshot_json)
        sod = dict(config.get("separation_of_duties") or {})
        if bool(sod.get("preparer_cannot_complete", True)) and record.prepared_by_user_id == self.actor_id:
            raise HTTPException(status_code=409, detail={"code": "SOD_REVIEW_PREPARER_CANNOT_COMPLETE"})
        stale, _candidate = self._staleness(record)
        if stale and bool(dict(config.get("review_readiness") or {}).get("block_complete_when_stale", True)):
            raise HTTPException(status_code=409, detail={"code": "PORTFOLIO_REVIEW_SNAPSHOT_STALE"})
        conclusions = self._conclusions(record.id)
        minimum = int(dict(config.get("review_readiness") or {}).get("minimum_conclusions_to_complete", 1))
        if len(conclusions) < minimum:
            raise HTTPException(
                status_code=409,
                detail={"code": "PORTFOLIO_REVIEW_CONCLUSIONS_REQUIRED", "minimum": minimum},
            )
        snapshot = self._current_snapshot(record)
        if snapshot is None:
            raise HTTPException(status_code=409, detail={"code": "PORTFOLIO_REVIEW_SNAPSHOT_REQUIRED"})
        actions = self._actions(record.id)
        completion = {
            "review_session_id": record.id,
            "review_number": record.review_number,
            "portfolio_workspace_id": record.portfolio_workspace_id,
            "review_date": str(payload.actual_review_date or record.review_date),
            "snapshot_id": snapshot.id,
            "snapshot_hash": snapshot.snapshot_hash,
            "configuration_id": record.configuration_id,
            "configuration_revision": record.configuration_revision,
            "configuration_hash": record.configuration_hash,
            "agenda": deepcopy(record.agenda_json or []),
            "conclusions": [self._conclusion_payload(item) for item in conclusions],
            "actions": [self._action_payload(item) for item in actions],
            "open_action_count": sum(item.status not in ACTION_TERMINAL_STATES for item in actions),
            "completion_note": payload.completion_note,
            "completed_by_user_id": self.actor_id,
        }
        record.completion_snapshot_json = completion
        record.completion_hash = _hash(completion)
        record.status = "COMPLETED"
        record.actual_review_date = payload.actual_review_date or record.review_date
        if payload.next_planned_review_date is not None:
            record.next_planned_review_date = payload.next_planned_review_date
        elif record.next_planned_review_date is None:
            record.next_planned_review_date = record.actual_review_date + timedelta(
                days=int(dict(config.get("cadence") or {}).get("frequency_days", 90))
            )
        record.review_authority_user_id = self.actor_id
        record.completed_at = utc_now()
        self._touch_review(record)
        self._event(
            "portfolio_review.session.completed",
            "PortfolioReviewSession",
            record.id,
            {
                "snapshot_hash": snapshot.snapshot_hash,
                "completion_hash": record.completion_hash,
                "open_action_count": completion["open_action_count"],
            },
        )
        self._record_command(
            "COMPLETE_REVIEW",
            idempotency_key,
            request_hash,
            review_session_id=record.id,
            result={"review_session_id": record.id, "completion_hash": record.completion_hash},
        )
        self.db.commit()
        self.db.refresh(record)
        return self._session_out(record)

    # ------------------------------------------------------------------
    # Conclusions and Actions
    # ------------------------------------------------------------------
    def transition_session(
        self,
        review_session_id: int,
        target: str,
        payload: ReviewTransitionIn,
        expected_version: int,
        idempotency_key: str,
    ) -> PortfolioReviewSessionOut:
        request_hash = _hash(
            {"review_session_id": review_session_id, "target": target, **payload.model_dump(mode="json")}
        )
        command = f"REVIEW_{target}"
        replay = self._command_replay(command, idempotency_key, request_hash)
        if replay is not None:
            return self._session_out(self._session(review_session_id))
        record = self._session(review_session_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_review_mutable(record)
        if target not in {"RETURNED", "CANCELLED", "SUPERSEDED"} or (
            target == "RETURNED" and record.status not in {"READY_FOR_REVIEW", "IN_REVIEW", "STALE"}
        ):
            raise HTTPException(status_code=409, detail={"code": "INVALID_PORTFOLIO_REVIEW_TRANSITION"})
        if target == "SUPERSEDED":
            replacement = self._session(payload.replacement_review_session_id or 0)
            if (
                replacement.id == record.id
                or replacement.portfolio_workspace_id != record.portfolio_workspace_id
                or (replacement.status in {"CANCELLED", "SUPERSEDED"})
            ):
                raise HTTPException(status_code=422, detail={"code": "REVIEW_REPLACEMENT_INCOMPATIBLE"})
        elif payload.replacement_review_session_id is not None:
            raise HTTPException(status_code=422, detail={"code": "REVIEW_REPLACEMENT_NOT_APPLICABLE"})
        record.status = target
        if target == "CANCELLED":
            record.cancelled_at = utc_now()
        self._touch_review(record)
        self._event(
            f"portfolio_review.session.{target.lower()}",
            "PortfolioReviewSession",
            record.id,
            {"reason": payload.reason, "replacement_review_session_id": payload.replacement_review_session_id},
        )
        self._record_command(
            command, idempotency_key, request_hash, review_session_id=record.id, result={"review_session_id": record.id}
        )
        self.db.commit()
        self.db.refresh(record)
        return self._session_out(record)

    def create_conclusion(
        self, review_session_id: int, payload: PortfolioReviewConclusionCreate, expected_version: int
    ) -> PortfolioReviewConclusionOut:
        record = self._session(review_session_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "PORTFOLIO_REVIEW_NOT_IN_REVIEW"})
        config = self._normalized_configuration(record.configuration_snapshot_json)
        self._catalog_item(config, "conclusion_types", payload.conclusion_type)
        conclusion = PortfolioReviewConclusion(
            tenant_id=self.tenant_id,
            review_session_id=record.id,
            conclusion_type=payload.conclusion_type,
            rationale=payload.rationale.strip(),
            conditions_json=deepcopy(payload.conditions),
            created_by_user_id=self.actor_id,
            updated_by_user_id=self.actor_id,
        )
        self.db.add(conclusion)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(status_code=409, detail={"code": "PORTFOLIO_REVIEW_CONCLUSION_EXISTS"}) from None
        self._touch_review(record)
        self._event(
            "portfolio_review.conclusion.recorded",
            "PortfolioReviewConclusion",
            conclusion.id,
            {"review_session_id": record.id, "conclusion_type": conclusion.conclusion_type},
        )
        self.db.commit()
        self.db.refresh(conclusion)
        return PortfolioReviewConclusionOut.model_validate(conclusion)

    def update_conclusion(
        self, conclusion_id: int, payload: PortfolioReviewConclusionUpdate, expected_version: int
    ) -> PortfolioReviewConclusionOut:
        conclusion = self._conclusion(conclusion_id)
        review = self._session(conclusion.review_session_id, lock=True)
        conclusion = self._conclusion(conclusion_id, lock=True)
        self._check_version(conclusion.revision_version, expected_version)
        if review.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "PORTFOLIO_REVIEW_NOT_IN_REVIEW"})
        config = self._normalized_configuration(review.configuration_snapshot_json)
        self._catalog_item(config, "conclusion_types", payload.conclusion_type)
        duplicate = self.db.scalar(
            select(PortfolioReviewConclusion.id).where(
                PortfolioReviewConclusion.tenant_id == self.tenant_id,
                PortfolioReviewConclusion.review_session_id == review.id,
                PortfolioReviewConclusion.conclusion_type == payload.conclusion_type,
                PortfolioReviewConclusion.id != conclusion.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail={"code": "PORTFOLIO_REVIEW_CONCLUSION_EXISTS"})
        conclusion.conclusion_type = payload.conclusion_type
        conclusion.rationale = payload.rationale.strip()
        conclusion.conditions_json = deepcopy(payload.conditions)
        conclusion.updated_by_user_id = self.actor_id
        conclusion.updated_at = utc_now()
        conclusion.revision_version += 1
        self._touch_review(review)
        self._event(
            "portfolio_review.conclusion.updated",
            "PortfolioReviewConclusion",
            conclusion.id,
            {"review_session_id": review.id, "conclusion_type": conclusion.conclusion_type},
        )
        self.db.commit()
        self.db.refresh(conclusion)
        return PortfolioReviewConclusionOut.model_validate(conclusion)

    def create_action(
        self,
        review_session_id: int,
        payload: PortfolioReviewActionCreate,
        expected_version: int,
        idempotency_key: str,
    ) -> PortfolioReviewActionOut:
        request_hash = _hash({"review_session_id": review_session_id, **payload.model_dump(mode="json")})
        replay = self._command_replay("CREATE_ACTION", idempotency_key, request_hash)
        if replay is not None:
            return self._action_out(self._action(int(replay.result_json["action_id"])))
        review = self._session(review_session_id, lock=True)
        self._check_version(review.revision_version, expected_version)
        if review.status not in {"PREPARING", "READY_FOR_REVIEW", "IN_REVIEW", "STALE"}:
            raise HTTPException(status_code=409, detail={"code": "PORTFOLIO_REVIEW_ACTION_NOT_ALLOWED"})
        config = self._normalized_configuration(review.configuration_snapshot_json)
        action_config = self._catalog_item(config, "action_types", payload.action_type)
        authority = str(action_config.get("authority") or "PORTFOLIO_REVIEW").upper()
        if payload.requested_source_authority and payload.requested_source_authority != authority:
            raise HTTPException(status_code=422, detail={"code": "REVIEW_ACTION_SOURCE_AUTHORITY_MISMATCH"})
        applicability = dict(config.get("action_applicability") or {})
        if payload.subject_type not in set(applicability.get("subject_types") or []):
            raise HTTPException(status_code=422, detail={"code": "REVIEW_ACTION_SUBJECT_NOT_APPLICABLE"})
        if payload.priority not in set(applicability.get("priorities") or []):
            raise HTTPException(status_code=422, detail={"code": "REVIEW_ACTION_PRIORITY_NOT_APPLICABLE"})
        self._validate_action_subject(review, payload.subject_type, payload.subject_id, payload.subject_key)
        self._user(payload.owner_user_id)
        numbering = dict(config.get("numbering") or {})
        action_number = self._reserve_number(
            ACTION_NUMBER_RULE,
            prefix=str(numbering.get("action_prefix") or "PRA"),
            padding=int(numbering.get("action_padding") or 7),
            separator=str(numbering.get("separator") or "-"),
        )
        action = PortfolioReviewAction(
            tenant_id=self.tenant_id,
            action_number=action_number,
            review_session_id=review.id,
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            subject_key=payload.subject_key.strip().lower() if payload.subject_key else None,
            action_type=payload.action_type,
            rationale=payload.rationale.strip(),
            priority=payload.priority,
            owner_user_id=payload.owner_user_id,
            due_date=payload.due_date,
            status="OPEN",
            source_evidence_references_json=deepcopy(payload.source_evidence_references),
            requested_source_authority=authority,
            dispatch_status="NOT_REQUESTED",
            create_idempotency_key=idempotency_key,
            create_request_hash=request_hash,
            created_by_user_id=self.actor_id,
            last_modified_by_user_id=self.actor_id,
        )
        self.db.add(action)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(status_code=409, detail={"code": "PORTFOLIO_REVIEW_ACTION_CONFLICT"}) from None
        self._touch_review(review)
        self._event(
            "portfolio_review.action.created",
            "PortfolioReviewAction",
            action.id,
            {
                "review_session_id": review.id,
                "action_type": action.action_type,
                "source_mutation_performed": False,
            },
        )
        self._record_command(
            "CREATE_ACTION",
            idempotency_key,
            request_hash,
            review_session_id=review.id,
            review_action_id=action.id,
            result={"action_id": action.id, "review_session_id": review.id},
        )
        self.db.commit()
        self.db.refresh(action)
        return self._action_out(action)

    def update_action(
        self, action_id: int, payload: PortfolioReviewActionUpdate, expected_version: int
    ) -> PortfolioReviewActionOut:
        action, review = self._locked_follow_up_action(action_id)
        self._check_version(action.revision_version, expected_version)
        if not self.context.role_codes & {"organization_admin", "portfolio_review_preparer"} and (
            action.owner_user_id != self.actor_id
        ):
            raise HTTPException(status_code=403, detail={"code": "REVIEW_ACTION_OWNER_SCOPE_DENIED"})
        if action.status in ACTION_TERMINAL_STATES:
            raise HTTPException(status_code=409, detail={"code": "PORTFOLIO_REVIEW_ACTION_IMMUTABLE"})
        values = payload.model_dump(exclude_unset=True)
        if "priority" in values and values["priority"] is not None:
            allowed = set(
                dict(
                    self._normalized_configuration(review.configuration_snapshot_json).get("action_applicability") or {}
                ).get("priorities")
                or []
            )
            if values["priority"] not in allowed:
                raise HTTPException(status_code=422, detail={"code": "REVIEW_ACTION_PRIORITY_NOT_APPLICABLE"})
        if "owner_user_id" in values and values["owner_user_id"] is not None:
            self._user(int(values["owner_user_id"]))
        if "status" in values and values["status"] is not None:
            target_status = str(getattr(values["status"], "value", values["status"]))
            if target_status == "ACCEPTED":
                raise HTTPException(status_code=409, detail={"code": "REVIEW_ACTION_APPROVAL_REQUIRED"})
            allowed_from = ACTION_TRANSITIONS.get(target_status)
            if allowed_from is None or action.status not in allowed_from:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "INVALID_REVIEW_ACTION_TRANSITION", "from": action.status, "to": target_status},
                )
            action.status = target_status
            if target_status == "COMPLETED":
                action.completed_at = utc_now()
        for field in ("rationale", "priority", "owner_user_id", "due_date"):
            if field in values and values[field] is not None:
                value = values[field].strip() if field == "rationale" else values[field]
                setattr(action, field, value)
        if "source_evidence_references" in values and values["source_evidence_references"] is not None:
            action.source_evidence_references_json = deepcopy(values["source_evidence_references"])
        action.last_modified_by_user_id = self.actor_id
        action.updated_at = utc_now()
        action.revision_version += 1
        self._event(
            "portfolio_review.action.updated",
            "PortfolioReviewAction",
            action.id,
            {
                "review_session_id": action.review_session_id,
                "status": action.status,
                "source_mutation_performed": False,
            },
        )
        self.db.commit()
        self.db.refresh(action)
        return self._action_out(action)

    def approve_action(
        self,
        action_id: int,
        payload: ActionApprovalIn,
        expected_version: int,
        idempotency_key: str,
    ) -> PortfolioReviewActionOut:
        request_hash = _hash({"action_id": action_id, **payload.model_dump(mode="json")})
        replay = self._command_replay("APPROVE_ACTION", idempotency_key, request_hash)
        if replay is not None:
            return self._action_out(self._action(int(replay.result_json["action_id"])))
        action, review = self._locked_follow_up_action(action_id)
        self._check_version(action.revision_version, expected_version)
        if action.status != "OPEN":
            raise HTTPException(status_code=409, detail={"code": "OPEN_REVIEW_ACTION_REQUIRED"})
        config = self._normalized_configuration(review.configuration_snapshot_json)
        if bool(dict(config.get("separation_of_duties") or {}).get("action_creator_cannot_approve", True)) and (
            action.created_by_user_id == self.actor_id
        ):
            raise HTTPException(status_code=409, detail={"code": "SOD_ACTION_CREATOR_CANNOT_APPROVE"})
        action.status = "ACCEPTED"
        action.approved_by_user_id = self.actor_id
        action.approved_at = utc_now()
        action.approve_idempotency_key = idempotency_key
        action.approve_request_hash = request_hash
        action.last_modified_by_user_id = self.actor_id
        action.updated_at = utc_now()
        action.revision_version += 1
        self._event(
            "portfolio_review.action.approved",
            "PortfolioReviewAction",
            action.id,
            {
                "review_session_id": action.review_session_id,
                "approval_note": payload.approval_note,
                "source_mutation_performed": False,
            },
        )
        self._record_command(
            "APPROVE_ACTION",
            idempotency_key,
            request_hash,
            review_session_id=action.review_session_id,
            review_action_id=action.id,
            result={"action_id": action.id},
        )
        self.db.commit()
        self.db.refresh(action)
        return self._action_out(action)

    def dispatch_action(
        self,
        action_id: int,
        payload: ActionDispatchIn,
        expected_version: int,
        idempotency_key: str,
    ) -> PortfolioReviewActionOut:
        request_hash = _hash({"action_id": action_id, **payload.model_dump(mode="json")})
        replay = self._command_replay("DISPATCH_ACTION", idempotency_key, request_hash)
        if replay is not None:
            return self._action_out(self._action(int(replay.result_json["action_id"])))
        action, _review = self._locked_follow_up_action(action_id)
        self._check_version(action.revision_version, expected_version)
        if action.status not in {"ACCEPTED", "IN_PROGRESS"}:
            raise HTTPException(status_code=409, detail={"code": "APPROVED_REVIEW_ACTION_REQUIRED"})
        if action.dispatch_status != "NOT_REQUESTED":
            raise HTTPException(status_code=409, detail={"code": "REVIEW_ACTION_ALREADY_DISPATCHED"})
        # Wave 3A intentionally has no implicit cross-domain commands.  The
        # auditable request is the integration boundary for a later adapter.
        action.dispatch_status = "REQUEST_RECORDED"
        action.execution_reference = f"PORTFOLIO_REVIEW_REQUEST:{action.action_number}"
        action.dispatched_at = utc_now()
        action.dispatch_idempotency_key = idempotency_key
        action.dispatch_request_hash = request_hash
        action.last_modified_by_user_id = self.actor_id
        action.updated_at = utc_now()
        action.revision_version += 1
        self._event(
            "portfolio_review.action.dispatch_requested",
            "PortfolioReviewAction",
            action.id,
            {
                "review_session_id": action.review_session_id,
                "action_type": action.action_type,
                "requested_source_authority": action.requested_source_authority,
                "dispatch_mode": "REQUEST_ONLY",
                "dispatch_note": payload.dispatch_note,
                "source_mutation_performed": False,
            },
        )
        self._record_command(
            "DISPATCH_ACTION",
            idempotency_key,
            request_hash,
            review_session_id=action.review_session_id,
            review_action_id=action.id,
            result={"action_id": action.id, "dispatch_mode": "REQUEST_ONLY"},
        )
        self.db.commit()
        self.db.refresh(action)
        return self._action_out(action)

    def list_actions(
        self,
        *,
        review_session_id: int | None = None,
        owner_user_id: int | None = None,
        status: str | None = None,
        subject_type: str | None = None,
        subject_id: int | None = None,
        overdue: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PortfolioReviewActionPageOut:
        statement = (
            select(PortfolioReviewAction)
            .join(PortfolioReviewSession, PortfolioReviewSession.id == PortfolioReviewAction.review_session_id)
            .where(
                PortfolioReviewAction.tenant_id == self.tenant_id,
                PortfolioReviewSession.tenant_id == self.tenant_id,
            )
        )
        statement = self._workspace_scope(statement, PortfolioReviewSession.portfolio_workspace_id)
        if review_session_id is not None:
            review = self._session(review_session_id)
            statement = statement.where(PortfolioReviewAction.review_session_id == review.id)
        if owner_user_id is not None:
            statement = statement.where(PortfolioReviewAction.owner_user_id == owner_user_id)
        if status:
            statement = statement.where(PortfolioReviewAction.status == status.strip().upper())
        if subject_type:
            statement = statement.where(PortfolioReviewAction.subject_type == subject_type.strip().upper())
        if subject_id is not None:
            statement = statement.where(PortfolioReviewAction.subject_id == subject_id)
        if overdue is True:
            statement = statement.where(
                PortfolioReviewAction.due_date < date.today(),
                PortfolioReviewAction.status.notin_(ACTION_TERMINAL_STATES),
            )
        elif overdue is False:
            statement = statement.where(
                or_(
                    PortfolioReviewAction.due_date.is_(None),
                    PortfolioReviewAction.due_date >= date.today(),
                    PortfolioReviewAction.status.in_(ACTION_TERMINAL_STATES),
                )
            )
        total = int(self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
        rows = list(
            self.db.scalars(
                statement.order_by(PortfolioReviewAction.due_date.asc().nullslast(), PortfolioReviewAction.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return PortfolioReviewActionPageOut(
            items=[self._action_out(item) for item in rows], total=total, page=page, page_size=page_size
        )

    # ------------------------------------------------------------------
    # Frozen backend read models
    # ------------------------------------------------------------------
    def project_matrix(
        self,
        review_session_id: int,
        *,
        bucket: str | None = None,
        rank_min: int | None = None,
        rank_max: int | None = None,
        project_type: str | None = None,
        gate_status: str | None = None,
        fid_status: str | None = None,
        budget_status: str | None = None,
        resource_status: str | None = None,
        review_action: str | None = None,
        action_owner_user_id: int | None = None,
        blocked: bool | None = None,
        stale: bool | None = None,
        unclassified: bool | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> ProjectMatrixPageOut:
        review = self._session(review_session_id)
        snapshot = self._required_snapshot(review)
        rows = [deepcopy(item) for item in list(snapshot.snapshot_json.get("project_matrix") or [])]
        if review.status == "COMPLETED":
            actions = list(dict(review.completion_snapshot_json or {}).get("actions") or [])
        else:
            actions = [self._action_payload(item) for item in self._actions(review.id)]
        by_project: dict[int, list[dict[str, Any]]] = defaultdict(list)
        by_membership: dict[int, list[dict[str, Any]]] = defaultdict(list)
        portfolio_actions: list[dict[str, Any]] = []
        for action in actions:
            subject_type = str(action.get("subject_type") or "")
            subject_id = action.get("subject_id")
            if subject_type == "PROJECT" and subject_id is not None:
                by_project[int(subject_id)].append(action)
            elif subject_type == "PORTFOLIO_MEMBERSHIP" and subject_id is not None:
                by_membership[int(subject_id)].append(action)
            elif subject_type == "PORTFOLIO":
                portfolio_actions.append(action)
        filtered: list[ProjectMatrixRowOut] = []
        for raw in rows:
            merged_actions = (
                by_project.get(int(raw["project_workspace_id"]), [])
                + by_membership.get(int(raw["membership_id"]), [])
                + portfolio_actions
            )
            raw["review_actions"] = merged_actions
            item = ProjectMatrixRowOut.model_validate(raw)
            if bucket and item.strategic_bucket.lower() != bucket.lower():
                continue
            if unclassified is True and item.strategic_bucket != "UNCLASSIFIED":
                continue
            if unclassified is False and item.strategic_bucket == "UNCLASSIFIED":
                continue
            if rank_min is not None and (item.portfolio_rank is None or item.portfolio_rank < rank_min):
                continue
            if rank_max is not None and (item.portfolio_rank is None or item.portfolio_rank > rank_max):
                continue
            if project_type and str(raw.get("project_type") or "").lower() != project_type.lower():
                continue
            if gate_status and item.gate_readiness.lower() != gate_status.lower():
                continue
            if fid_status and item.fid_status.lower() != fid_status.lower():
                continue
            if budget_status and item.budget_status.lower() != budget_status.lower():
                continue
            if resource_status and item.resource_status.lower() != resource_status.lower():
                continue
            if review_action and not any(
                str(action.get("action_type") or "").lower() == review_action.lower() for action in merged_actions
            ):
                continue
            if action_owner_user_id is not None and not any(
                int(action.get("owner_user_id") or 0) == action_owner_user_id for action in merged_actions
            ):
                continue
            if blocked is not None and item.blocked is not blocked:
                continue
            if stale is not None and item.stale is not stale:
                continue
            filtered.append(item)
        total = len(filtered)
        start = (page - 1) * page_size
        return ProjectMatrixPageOut(
            items=filtered[start : start + page_size],
            total=total,
            page=page,
            page_size=page_size,
            snapshot_hash=snapshot.snapshot_hash,
        )

    def allocation(self, review_session_id: int) -> PortfolioAllocationOut:
        review = self._session(review_session_id)
        snapshot = self._required_snapshot(review)
        allocation = dict(snapshot.snapshot_json.get("allocation") or {})
        plan = dict(snapshot.snapshot_json.get("allocation_plan") or {})
        return PortfolioAllocationOut(
            review_session_id=review.id,
            snapshot_hash=snapshot.snapshot_hash,
            allocation_plan=plan,
            comparison=allocation,
            multi_currency=bool(allocation.get("multi_currency", False)),
            normalization_warning=allocation.get("normalization_warning"),
        )

    def budget_resources(self, review_session_id: int) -> PortfolioBudgetResourcesOut:
        review = self._session(review_session_id)
        snapshot = self._required_snapshot(review)
        return PortfolioBudgetResourcesOut(
            review_session_id=review.id,
            snapshot_hash=snapshot.snapshot_hash,
            budget=deepcopy(dict(snapshot.snapshot_json.get("budget") or {})),
            resources=deepcopy(dict(snapshot.snapshot_json.get("resources") or {})),
        )

    def gate_status(self, review_session_id: int) -> PortfolioGateStatusOut:
        review = self._session(review_session_id)
        snapshot = self._required_snapshot(review)
        gate = dict(snapshot.snapshot_json.get("gate_context") or {})
        return PortfolioGateStatusOut(
            review_session_id=review.id,
            snapshot_hash=snapshot.snapshot_hash,
            gate_preparation=deepcopy(dict(gate.get("preparation") or {})),
            investment_decisions=deepcopy(list(gate.get("investment_decisions") or [])),
            distribution=deepcopy(dict(gate.get("distribution") or {})),
        )

    def history(self, review_session_id: int) -> list[PortfolioReviewHistoryItemOut]:
        review = self._session(review_session_id)
        actions = self._actions(review.id)
        action_ids = {item.id for item in actions}
        conclusions = self._conclusions(review.id)
        conclusion_ids = {item.id for item in conclusions}
        statement = select(SecurityEvent).where(SecurityEvent.tenant_id == self.tenant_id)
        if review.completed_at is not None:
            # A completed Review's audit view is bounded at completion.  Live
            # follow-up action events remain visible in the action queue only.
            statement = statement.where(SecurityEvent.occurred_at <= review.completed_at)
        events = list(
            self.db.scalars(statement.order_by(SecurityEvent.occurred_at.desc(), SecurityEvent.id.desc())).all()
        )
        selected = [
            item
            for item in events
            if (item.target_type == "PortfolioReviewSession" and item.target_id == review.id)
            or (item.target_type == "PortfolioReviewAction" and item.target_id in action_ids)
            or (item.target_type == "PortfolioReviewConclusion" and item.target_id in conclusion_ids)
        ]
        return [
            PortfolioReviewHistoryItemOut(
                event_type=item.event_type,
                outcome=item.outcome,
                actor_user_id=item.user_id,
                target_type=item.target_type,
                target_id=item.target_id,
                metadata=deepcopy(item.metadata_json or {}),
                occurred_at=item.occurred_at,
            )
            for item in selected
        ]

    def compare(self, review_session_id: int, other_review_session_id: int) -> PortfolioReviewComparisonOut:
        current = self._session(review_session_id)
        other = self._session(other_review_session_id)
        if current.portfolio_workspace_id != other.portfolio_workspace_id:
            raise HTTPException(status_code=422, detail={"code": "PORTFOLIO_REVIEW_SCOPE_MISMATCH"})
        if other.status != "COMPLETED":
            raise HTTPException(status_code=409, detail={"code": "COMPLETED_COMPARISON_REVIEW_REQUIRED"})
        current_snapshot = self._required_snapshot(current)
        other_snapshot = self._required_snapshot(other)
        deltas = self._period_deltas(
            current_snapshot.snapshot_json,
            other_snapshot.snapshot_json,
            dict(current.completion_snapshot_json or {}),
            dict(other.completion_snapshot_json or {}),
        )
        return PortfolioReviewComparisonOut(
            current_review_id=current.id,
            other_review_id=other.id,
            current_snapshot_hash=current_snapshot.snapshot_hash,
            other_snapshot_hash=other_snapshot.snapshot_hash,
            deltas=deltas,
        )

    def trends(self, portfolio_workspace_id: int) -> PortfolioReviewTrendsOut:
        portfolio = self._workspace(portfolio_workspace_id)
        self._assert_portfolio(portfolio)
        self._assert_scope(portfolio.id)
        reviews = list(
            self.db.scalars(
                select(PortfolioReviewSession)
                .where(
                    PortfolioReviewSession.tenant_id == self.tenant_id,
                    PortfolioReviewSession.portfolio_workspace_id == portfolio.id,
                    PortfolioReviewSession.status == "COMPLETED",
                    PortfolioReviewSession.current_snapshot_id.is_not(None),
                )
                .order_by(PortfolioReviewSession.actual_review_date, PortfolioReviewSession.id)
            ).all()
        )
        snapshot_ids = [int(item.current_snapshot_id) for item in reviews if item.current_snapshot_id is not None]
        snapshots = {
            item.id: item
            for item in self.db.scalars(
                select(PortfolioReviewSnapshot).where(
                    PortfolioReviewSnapshot.tenant_id == self.tenant_id,
                    PortfolioReviewSnapshot.id.in_(snapshot_ids or [-1]),
                )
            ).all()
        }
        points: list[PortfolioReviewTrendPointOut] = []
        for review in reviews:
            snapshot = snapshots.get(int(review.current_snapshot_id or 0))
            if snapshot is None:
                continue
            summary = dict(snapshot.snapshot_json.get("portfolio_summary") or {})
            allocation = dict(snapshot.snapshot_json.get("allocation") or {})
            completion = dict(review.completion_snapshot_json or {})
            points.append(
                PortfolioReviewTrendPointOut(
                    review_session_id=review.id,
                    review_number=review.review_number,
                    review_date=review.actual_review_date or review.review_date,
                    snapshot_hash=snapshot.snapshot_hash,
                    portfolio_project_count=int(summary.get("portfolio_size") or 0),
                    unclassified_exposure=deepcopy(dict(allocation.get("unclassified") or {})),
                    allocation_variance=deepcopy(dict(summary.get("allocation_variance") or {})),
                    budget_feasibility=str(summary.get("budget_feasibility") or "NOT_AVAILABLE"),
                    resource_feasibility=str(summary.get("resource_feasibility") or "NOT_AVAILABLE"),
                    blocked_project_count=int(summary.get("blocked_project_count") or 0),
                    open_action_count_at_close=int(completion.get("open_action_count") or 0),
                    fid_count=int(dict(summary.get("fid_status_distribution") or {}).get("FID_GRANTED") or 0),
                )
            )
        return PortfolioReviewTrendsOut(portfolio_workspace_id=portfolio.id, points=points)

    # ------------------------------------------------------------------
    # ADMIN configuration authority
    # ------------------------------------------------------------------
    def configurations(self) -> list[AdminConfiguration]:
        records = list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                )
                .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
            ).all()
        )
        return [item for item in records if self._configuration_visible(item)]

    def configuration_preview(
        self,
        portfolio_workspace_id: int | None,
        *,
        configuration_id: int | None = None,
        content: dict[str, Any] | None = None,
    ) -> ReviewConfigurationPreviewOut:
        portfolio = self._workspace(portfolio_workspace_id) if portfolio_workspace_id else None
        if portfolio is not None:
            self._assert_portfolio(portfolio)
            self._assert_scope(portfolio.id)
        effective, source, path = self._effective_configuration(portfolio)
        if configuration_id is not None:
            selected = self._configuration(configuration_id)
            target_id = dict(selected.content_json.get("scope") or {}).get("workspace_id")
            if target_id is not None and portfolio is not None and int(target_id) not in {item.id for item in path}:
                raise HTTPException(status_code=422, detail={"code": "CONFIGURATION_PREVIEW_SCOPE_MISMATCH"})
            effective = self._validate_configuration(
                content if content is not None else selected.content_json, code=selected.code
            )
            source = {
                "configuration_id": selected.id,
                "code": selected.code,
                "revision": selected.revision,
                "version": selected.version,
                "content_hash": _hash(effective),
                "status": selected.status,
            }
        elif content is not None:
            raise HTTPException(status_code=422, detail={"code": "CONFIGURATION_PREVIEW_ID_REQUIRED"})
        return ReviewConfigurationPreviewOut(
            portfolio_workspace_id=portfolio_workspace_id,
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
        target = self._workspace(target_workspace_id) if target_workspace_id else None
        if target is None:
            source_target = dict(source.content_json.get("scope") or {}).get("workspace_id")
            target = self._workspace(int(source_target)) if source_target is not None else None
        if target is not None:
            self._assert_scope(target.id)
        elif not self.context.organization_wide:
            raise HTTPException(status_code=403, detail={"code": "CONFIGURATION_TENANT_SCOPE_DENIED"})
        if target is not None and target.workspace_type_code not in {"enterprise", "business-unit", "portfolio"}:
            raise HTTPException(status_code=422, detail={"code": "PORTFOLIO_REVIEW_CONFIGURATION_SCOPE_INVALID"})
        target_code = f"workspace-{target.id}" if target else source.code
        revision = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(AdminConfiguration.revision), 0)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                        AdminConfiguration.code == target_code,
                    )
                )
                or 0
            )
            + 1
        )
        content = self._normalized_configuration(source.content_json)
        content["scope"] = {"type": "workspace" if target else "tenant", "workspace_id": target.id if target else None}
        clone = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code=target_code,
            name=f"{source.name} — {target.name}" if target else source.name,
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
            "portfolio_review.configuration.cloned",
            "AdminConfiguration",
            clone.id,
            {"source_configuration_id": source.id, "target_workspace_id": target.id if target else None},
        )
        self.db.commit()
        self.db.refresh(clone)
        return clone

    def update_configuration(
        self,
        configuration_id: int,
        expected_version: int,
        *,
        name: str,
        description: str,
        content: dict[str, Any],
    ) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._assert_configuration_mutable_scope(record)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "DRAFT_CONFIGURATION_REQUIRED"})
        normalized = self._validate_configuration(content, code=record.code)
        record.name = name.strip()
        record.description = description.strip()
        record.content_json = normalized
        record.content_hash = _hash(normalized)
        record.version += 1
        record.updated_at = utc_now()
        self._event("portfolio_review.configuration.updated", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        # Different Draft rows of one policy need a shared publication lock.
        self.db.scalar(select(Tenant.id).where(Tenant.id == self.tenant_id).with_for_update())
        record = self._configuration(configuration_id, lock=True)
        self._assert_configuration_mutable_scope(record)
        self._check_version(record.version, expected_version)
        if record.status == "published":
            return record
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "DRAFT_CONFIGURATION_REQUIRED"})
        normalized = self._validate_configuration(record.content_json, code=record.code)
        prior = list(
            self.db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    AdminConfiguration.code == record.code,
                    AdminConfiguration.status == "published",
                )
            ).all()
        )
        for item in prior:
            item.status = "archived"
            item.version += 1
            item.updated_at = utc_now()
        record.content_json = normalized
        record.content_hash = _hash(normalized)
        record.status = "published"
        record.published_at = utc_now()
        record.updated_at = utc_now()
        record.version += 1
        self._event("portfolio_review.configuration.published", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def archive_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._assert_configuration_mutable_scope(record)
        self._check_version(record.version, expected_version)
        if record.status == "archived":
            return record
        if record.code == DEFAULT_CONFIGURATION_CODE and record.status == "published":
            replacement = self.db.scalar(
                select(AdminConfiguration.id).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    AdminConfiguration.code == DEFAULT_CONFIGURATION_CODE,
                    AdminConfiguration.status == "published",
                    AdminConfiguration.id != record.id,
                )
            )
            if replacement is None:
                raise HTTPException(status_code=409, detail={"code": "DEFAULT_CONFIGURATION_REPLACEMENT_REQUIRED"})
        record.status = "archived"
        record.updated_at = utc_now()
        record.version += 1
        self._event("portfolio_review.configuration.archived", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    # ------------------------------------------------------------------
    # Read-only source adapters and snapshot construction
    # ------------------------------------------------------------------
    def _build_snapshot(self, review: PortfolioReviewSession) -> dict[str, Any]:
        portfolio = self._workspace(review.portfolio_workspace_id)
        config = self._normalized_configuration(review.configuration_snapshot_json)
        memberships = list(
            self.db.scalars(
                select(PortfolioProjectMembership)
                .where(
                    PortfolioProjectMembership.tenant_id == self.tenant_id,
                    PortfolioProjectMembership.portfolio_workspace_id == portfolio.id,
                    PortfolioProjectMembership.status == "ACTIVE",
                )
                .order_by(PortfolioProjectMembership.project_workspace_id, PortfolioProjectMembership.id)
            ).all()
        )
        project_ids = [item.project_workspace_id for item in memberships]
        projects = {
            item.id: item
            for item in self.db.scalars(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id.in_(project_ids or [-1]),
                )
            ).all()
        }
        membership_payload = [
            {
                "membership_id": item.id,
                "project_workspace_id": item.project_workspace_id,
                "membership_source": item.membership_source,
                "is_target_portfolio": item.is_target_portfolio,
                "status": item.status,
                "revision_version": item.revision_version,
                "effective_from": item.effective_from.isoformat(),
            }
            for item in memberships
        ]
        membership_hash = _hash(
            {
                "memberships": membership_payload,
                "projects": [
                    {**self._workspace_option(item), "project_type": (item.defaults_json or {}).get("project_type")}
                    for item in sorted(projects.values(), key=lambda item: item.id)
                ],
            }
        )

        ranking_items, ranking_hash = PortfolioEvaluationService(
            self.db, self.tenant_id, self.actor_id, self.context
        ).ranking_projection(portfolio.id)
        ranking_payload = [item.model_dump(mode="json") for item in ranking_items]
        ranking_by_project = {item.project_workspace_id: item for item in ranking_items}
        evaluation_ids = [item.evaluation_id for item in ranking_items]
        evaluations = {
            item.id: item
            for item in self.db.scalars(
                select(PortfolioProjectEvaluation).where(
                    PortfolioProjectEvaluation.tenant_id == self.tenant_id,
                    PortfolioProjectEvaluation.id.in_(evaluation_ids or [-1]),
                )
            ).all()
        }

        plan = self._snapshot_allocation_plan(review)
        allocation_plan: dict[str, Any] = {}
        allocation: dict[str, Any] = {}
        allocation_error: str | None = None
        if plan is not None:
            allocation_plan = {
                "id": plan.id,
                "allocation_plan_number": plan.allocation_plan_number,
                "logical_code": plan.logical_code,
                "plan_revision": plan.plan_revision,
                "planning_cycle_id": plan.planning_cycle_id,
                "scope_workspace_id": plan.scope_workspace_id,
                "portfolio_workspace_id": plan.portfolio_workspace_id,
                "status": plan.status,
                "base_currency": plan.base_currency,
                "allocation_basis": plan.allocation_basis,
                "revision_version": plan.revision_version,
                "plan_hash": plan.plan_hash,
                "configuration_revision": plan.configuration_revision,
                "configuration_hash": plan.configuration_hash,
                "endorsed_snapshot_hash": plan.endorsed_snapshot_hash,
            }
            try:
                comparison = CapitalPlanningService(
                    self.db, self.tenant_id, self.actor_id, self.context
                ).allocation_comparison(plan.id)
                allocation = comparison.model_dump(mode="json")
                # generated_at is presentation metadata, not source identity.
                allocation.pop("generated_at", None)
            except HTTPException as exc:
                allocation_error = str(dict(exc.detail).get("code") if isinstance(exc.detail, dict) else exc.detail)

        convergence = self.db.scalars(
            select(PortfolioScenarioConvergence)
            .where(
                PortfolioScenarioConvergence.tenant_id == self.tenant_id,
                PortfolioScenarioConvergence.portfolio_workspace_id == portfolio.id,
                PortfolioScenarioConvergence.status == "RECOMMENDED",
            )
            .order_by(PortfolioScenarioConvergence.recommended_at.desc(), PortfolioScenarioConvergence.id.desc())
        ).first()
        alternative = None
        if convergence is not None and convergence.recommended_alternative_id is not None:
            alternative = self.db.scalar(
                select(PortfolioConvergedAlternative).where(
                    PortfolioConvergedAlternative.tenant_id == self.tenant_id,
                    PortfolioConvergedAlternative.id == convergence.recommended_alternative_id,
                    PortfolioConvergedAlternative.convergence_id == convergence.id,
                )
            )
        convergence_payload = self._convergence_payload(convergence, alternative)

        budget_scenario = self._snapshot_budget_scenario(portfolio.id, alternative)
        budget_rows = (
            list(
                self.db.scalars(
                    select(PortfolioBudgetScenarioProject)
                    .where(
                        PortfolioBudgetScenarioProject.tenant_id == self.tenant_id,
                        PortfolioBudgetScenarioProject.scenario_id == budget_scenario.id,
                    )
                    .order_by(PortfolioBudgetScenarioProject.project_workspace_id)
                ).all()
            )
            if budget_scenario is not None
            else []
        )
        budget_payload = self._budget_payload(budget_scenario, budget_rows, alternative)
        budget_by_project = {item.project_workspace_id: item for item in budget_rows}

        resource_scenario = self._snapshot_resource_scenario(portfolio.id, alternative)
        resource_rows = (
            list(
                self.db.scalars(
                    select(PortfolioResourceScenarioProject)
                    .where(
                        PortfolioResourceScenarioProject.tenant_id == self.tenant_id,
                        PortfolioResourceScenarioProject.scenario_id == resource_scenario.id,
                    )
                    .order_by(PortfolioResourceScenarioProject.project_workspace_id)
                ).all()
            )
            if resource_scenario is not None
            else []
        )
        resource_payload = self._resource_payload(resource_scenario, resource_rows, alternative)
        resource_by_project = {item.project_workspace_id: item for item in resource_rows}

        gate_preparation = self.db.scalars(
            select(InvestmentGatePreparation)
            .where(
                InvestmentGatePreparation.tenant_id == self.tenant_id,
                InvestmentGatePreparation.portfolio_workspace_id == portfolio.id,
            )
            .order_by(InvestmentGatePreparation.updated_at.desc(), InvestmentGatePreparation.id.desc())
        ).first()
        decisions = list(
            self.db.scalars(
                select(InvestmentDecision)
                .where(
                    InvestmentDecision.tenant_id == self.tenant_id,
                    InvestmentDecision.portfolio_workspace_id == portfolio.id,
                    InvestmentDecision.status == "DECIDED",
                )
                .order_by(InvestmentDecision.decided_at.desc(), InvestmentDecision.id.desc())
            ).all()
        )
        gate_payload, decisions_by_project = self._gate_payload(gate_preparation, decisions, project_ids)

        risk_rows = list(
            self.db.scalars(
                select(RiskReadinessAssessment)
                .where(
                    RiskReadinessAssessment.tenant_id == self.tenant_id,
                    RiskReadinessAssessment.project_workspace_id.in_(project_ids or [-1]),
                    RiskReadinessAssessment.status == "COMPLETED",
                )
                .order_by(
                    RiskReadinessAssessment.project_workspace_id,
                    RiskReadinessAssessment.assessment_version.desc(),
                    RiskReadinessAssessment.id.desc(),
                )
            ).all()
        )
        risk_by_project: dict[int, RiskReadinessAssessment] = {}
        for item in risk_rows:
            risk_by_project.setdefault(item.project_workspace_id, item)

        classifications = (
            list(
                self.db.scalars(
                    select(StrategicBucketClassification).where(
                        StrategicBucketClassification.tenant_id == self.tenant_id,
                        StrategicBucketClassification.allocation_plan_id == plan.id,
                        or_(
                            StrategicBucketClassification.project_workspace_id.in_(project_ids or [-1]),
                            StrategicBucketClassification.portfolio_membership_id.in_(
                                [item.id for item in memberships] or [-1]
                            ),
                        ),
                    )
                ).all()
            )
            if plan is not None
            else []
        )
        bucket_by_project: dict[int, str] = {}
        membership_project = {item.id: item.project_workspace_id for item in memberships}
        for item in classifications:
            project_id = item.project_workspace_id or membership_project.get(int(item.portfolio_membership_id or 0))
            if project_id is not None:
                bucket_by_project[project_id] = item.bucket_code
        bucket_comparison = {str(item.get("bucket_code")): item for item in list(allocation.get("positions") or [])}
        recommended_matrix = self._recommended_matrix(alternative)
        active_actions = self._actions(review.id)
        actions_by_project: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for action in active_actions:
            if action.subject_type == "PROJECT" and action.subject_id is not None:
                actions_by_project[action.subject_id].append(self._action_payload(action))
            elif action.subject_type == "PORTFOLIO_MEMBERSHIP" and action.subject_id in membership_project:
                actions_by_project[membership_project[int(action.subject_id)]].append(self._action_payload(action))

        matrix: list[dict[str, Any]] = []
        for membership in memberships:
            project = projects.get(membership.project_workspace_id)
            if project is None:
                continue
            ranked = ranking_by_project.get(project.id)
            evaluation = evaluations.get(ranked.evaluation_id) if ranked else None
            budget_row = budget_by_project.get(project.id)
            resource_row = resource_by_project.get(project.id)
            project_decisions = decisions_by_project.get(project.id, [])
            latest_decision = project_decisions[0] if project_decisions else None
            risk = risk_by_project.get(project.id)
            bucket_code = bucket_by_project.get(project.id, "UNCLASSIFIED")
            bucket_variance = deepcopy(dict(bucket_comparison.get(bucket_code) or {}))
            recommended = dict(recommended_matrix.get(project.id) or {})
            budget_status = budget_row.selection_state if budget_row is not None else "NOT_AVAILABLE"
            resource_status = resource_row.selection_state if resource_row is not None else "NOT_AVAILABLE"
            gate_readiness = gate_preparation.readiness_status if gate_preparation is not None else "NOT_AVAILABLE"
            decision_outcome = latest_decision.outcome if latest_decision is not None else "NO_DECISION"
            fid_status = (
                "FID_GRANTED"
                if latest_decision is not None and latest_decision.is_fid
                else "NOT_FID"
                if latest_decision is not None
                else "NO_DECISION"
            )
            risk_status = risk.readiness_status if risk is not None else "NOT_AVAILABLE"
            blocked = any(
                value in {"BLOCKED", "INFEASIBLE", "STALE", "HOLD", "RECYCLE", "KILL"}
                for value in (gate_readiness, decision_outcome, risk_status)
            )
            matrix.append(
                {
                    "project_workspace_id": project.id,
                    "membership_id": membership.id,
                    "project_code": project.code,
                    "project_name": project.name,
                    "project_status": project.status,
                    "project_type": str((project.defaults_json or {}).get("project_type") or ""),
                    "portfolio_rank": ranked.rank if ranked else None,
                    "evaluation_id": ranked.evaluation_id if ranked else None,
                    "evaluation_version": ranked.evaluation_version if ranked else None,
                    "evaluation_hash": evaluation.source_snapshot_hash if evaluation else None,
                    "strategic_bucket": bucket_code,
                    "allocation_variance_contribution": {
                        "bucket_status": bucket_variance.get("status", "NOT_EVALUABLE"),
                        "variance_vs_target_percentage": bucket_variance.get("variance_vs_target_percentage"),
                        "variance_vs_target_amount": bucket_variance.get("variance_vs_target_amount"),
                        "source": "WAVE2A_COMPARISON",
                    },
                    "budget_status": budget_status,
                    "budget_context": self._budget_row_payload(budget_row),
                    "resource_status": resource_status,
                    "resource_context": self._resource_row_payload(resource_row),
                    "gate_stage": gate_preparation.profile_code if gate_preparation else "NOT_AVAILABLE",
                    "gate_readiness": gate_readiness,
                    "investment_decision": decision_outcome,
                    "fid_status": fid_status,
                    "risk_readiness": risk_status,
                    "risk_summary": self._risk_payload(risk),
                    "recommended_status": str(
                        recommended.get("recommendation")
                        or recommended.get("selection_state")
                        or recommended.get("status")
                        or "NOT_AVAILABLE"
                    ),
                    "approved_amount_context": {
                        "amount": str(latest_decision.authorized_amount)
                        if latest_decision and latest_decision.authorized_amount is not None
                        else None,
                        "currency": latest_decision.authorized_currency if latest_decision else None,
                        "decision_id": latest_decision.id if latest_decision else None,
                    },
                    "review_actions": actions_by_project.get(project.id, []),
                    "blocked": blocked,
                    "stale": gate_readiness == "STALE" or risk_status in {"STALE", "EXPIRED"},
                }
            )

        action_statuses = Counter(item.status for item in active_actions)
        overdue_actions = sum(
            item.due_date is not None
            and item.due_date
            < date.today() - timedelta(days=int(dict(config.get("thresholds") or {}).get("overdue_action_days", 0)))
            and item.status not in ACTION_TERMINAL_STATES
            for item in active_actions
        )
        portfolio_summary = {
            "portfolio_size": len(matrix),
            "projects_by_status": dict(Counter(item["project_status"] for item in matrix)),
            "projects_by_bucket": dict(Counter(item["strategic_bucket"] for item in matrix)),
            "capital_by_bucket": self._capital_by_bucket(allocation),
            "allocation_variance": self._allocation_variance_summary(allocation),
            "budget_feasibility": budget_payload.get("feasibility", "NOT_AVAILABLE"),
            "resource_feasibility": resource_payload.get("feasibility", "NOT_AVAILABLE"),
            "gate_status_distribution": dict(Counter(item["gate_readiness"] for item in matrix)),
            "fid_status_distribution": dict(Counter(item["fid_status"] for item in matrix)),
            "blocked_project_count": sum(bool(item["blocked"]) for item in matrix),
            "projects_requiring_reassessment": sum(
                action.action_type == "REQUEST_REASSESSMENT" and action.status not in ACTION_TERMINAL_STATES
                for action in active_actions
            ),
            "open_action_count": sum(item.status not in ACTION_TERMINAL_STATES for item in active_actions),
            "overdue_action_count": overdue_actions,
            "actions_by_status": dict(action_statuses),
        }

        now_sources = (
            [item.updated_at for item in memberships if item.updated_at is not None]
            + [
                item.updated_at
                for item in (plan, convergence, alternative, budget_scenario, resource_scenario, gate_preparation)
                if item is not None and getattr(item, "updated_at", None) is not None
            ]
            + [item.updated_at for item in risk_by_project.values()]
        )
        source_as_of = max(now_sources).isoformat() if now_sources else review.created_at.isoformat()

        source_index = {
            "PORTFOLIO_MEMBERSHIP": {
                "record_count": len(memberships),
                "hash": membership_hash,
                "source_current": bool(memberships),
                "as_of": max((item.updated_at for item in memberships), default=review.created_at).isoformat(),
            },
            "PORTFOLIO_RANK": {
                "record_count": len(ranking_items),
                "hash": ranking_hash,
                "source_current": bool(ranking_items),
                "as_of": max((item.completed_at for item in ranking_items), default=review.created_at).isoformat(),
            },
            "STRATEGIC_ALLOCATION": {
                "record_id": plan.id if plan else None,
                "version": plan.revision_version if plan else None,
                "hash": allocation.get("source_hash") or (plan.plan_hash if plan else ""),
                "status": plan.status if plan else "NOT_AVAILABLE",
                "source_current": bool(plan and plan.status == "ENDORSED" and allocation and allocation_error is None),
                "as_of": plan.updated_at.isoformat() if plan else None,
            },
            "BUDGET_SCENARIO": {
                "record_id": budget_scenario.id if budget_scenario else None,
                "version": budget_scenario.revision_version if budget_scenario else None,
                "hash": budget_scenario.scenario_hash if budget_scenario else "",
                "status": budget_scenario.status if budget_scenario else "NOT_AVAILABLE",
                "source_current": bool(budget_scenario and budget_scenario.status == "FROZEN"),
                "as_of": budget_scenario.updated_at.isoformat() if budget_scenario else None,
            },
            "RESOURCE_SCENARIO": {
                "record_id": resource_scenario.id if resource_scenario else None,
                "version": resource_scenario.revision_version if resource_scenario else None,
                "hash": resource_scenario.scenario_hash if resource_scenario else "",
                "status": resource_scenario.status if resource_scenario else "NOT_AVAILABLE",
                "source_current": bool(resource_scenario and resource_scenario.status == "FROZEN"),
                "as_of": resource_scenario.updated_at.isoformat() if resource_scenario else None,
            },
            "SCENARIO_RECOMMENDATION": {
                "record_id": convergence.id if convergence else None,
                "version": convergence.revision_version if convergence else None,
                "hash": convergence.recommendation_hash if convergence else "",
                "status": convergence.status if convergence else "NOT_AVAILABLE",
                "source_current": bool(convergence and convergence.status == "RECOMMENDED" and alternative),
                "as_of": convergence.updated_at.isoformat() if convergence else None,
            },
            "GATE_CONTEXT": {
                "record_id": gate_preparation.id if gate_preparation else None,
                "record_count": len(decisions) + int(gate_preparation is not None),
                "hash": _hash(gate_payload),
                "status": gate_preparation.status if gate_preparation else "NOT_AVAILABLE",
                "source_current": bool(
                    (gate_preparation is not None or decisions)
                    and (gate_preparation is None or gate_preparation.readiness_status not in {"STALE"})
                ),
                "as_of": max(
                    ([gate_preparation.updated_at] if gate_preparation else [])
                    + [item.decided_at for item in decisions if item.decided_at],
                    default=review.created_at,
                ).isoformat()
                if gate_preparation or decisions
                else None,
            },
            "RISK_READINESS": {
                "record_count": len(risk_by_project),
                "hash": _hash([self._risk_payload(item) for item in risk_by_project.values()]),
                "source_current": bool(risk_by_project)
                and all(item.readiness_status not in {"STALE", "EXPIRED"} for item in risk_by_project.values()),
                "as_of": max(
                    (item.updated_at for item in risk_by_project.values()), default=review.created_at
                ).isoformat(),
            },
        }
        policy = self._normalized_configuration(review.configuration_snapshot_json)
        freshness = dict(policy.get("source_freshness") or {})
        thresholds = dict(policy.get("thresholds") or {})
        for key, ages, max_age in (
            (
                "GATE_CONTEXT",
                [gate_preparation.updated_at]
                if gate_preparation
                else [item.decided_at for item in decisions if item.decided_at],
                min(
                    int(freshness.get("gate_evidence_max_age_days", 90)),
                    int(thresholds.get("stale_gate_evidence_tolerance_days", 90)),
                ),
            ),
            (
                "RISK_READINESS",
                [item.updated_at for item in risk_by_project.values()],
                int(freshness.get("risk_readiness_max_age_days", 90)),
            ),
        ):
            expired = any(utc_now() - age.replace(tzinfo=None) > timedelta(days=max_age) for age in ages)
            source_index[key]["source_current"] = bool(source_index[key]["source_current"]) and not expired
            source_index[key]["freshness_max_age_days"] = max_age
            source_index[key]["expired"] = expired
        portfolio_summary["alerts"] = self._threshold_alerts(policy, portfolio_summary, allocation)
        if resource_scenario is not None:
            # Reuse the existing read-only resource projection; no parallel engine.
            projection = PortfolioResourceService(self.db, self.tenant_id, self.actor_id, self.context).scenario(
                resource_scenario.id
            )
            resource_payload["summary"] = projection.summary.model_dump(mode="json")
            source_index["RESOURCE_SCENARIO"]["source_current"] = bool(
                source_index["RESOURCE_SCENARIO"]["source_current"] and projection.readiness.source_current
            )
            peak = projection.summary.peak_utilization
            if peak is not None and peak - Decimal("100") > Decimal(
                str(thresholds.get("resource_overload_threshold_percentage", 0))
            ):
                portfolio_summary["alerts"].append(
                    {
                        "code": "RESOURCE_OVERLOAD_THRESHOLD",
                        "severity": "WARNING",
                        "peak_utilization_percentage": str(peak),
                        "source": "PORTFOLIO_RESOURCE_READ_ONLY",
                    }
                )
        readiness, warnings, blockers = self._snapshot_readiness(
            review,
            source_index,
            membership_count=len(memberships),
            allocation_selected=plan is not None,
            allocation_error=allocation_error,
        )
        snapshot_payload = {
            "contract_version": "WAVE3A_PORTFOLIO_REVIEW_SNAPSHOT_V1",
            "authority_boundary": {
                "portfolio_review": "PORTFOLIO_GOVERNANCE_CONTEXT_AND_ACTIONS",
                "portfolio_rank": "PORTFOLIO_EVALUATION_READ_ONLY",
                "strategic_allocation": "WAVE2A_READ_ONLY",
                "budget": "PORTFOLIO_BUDGET_READ_ONLY",
                "resources": "PORTFOLIO_RESOURCE_READ_ONLY",
                "gate07i": "PORTFOLIO_CONVERGENCE_READ_ONLY",
                "gate07j": "INVESTMENT_GATE_PREPARATION_READ_ONLY",
                "gate07k_fid": "INVESTMENT_DECISION_READ_ONLY",
            },
            "review": {
                "id": review.id,
                "review_number": review.review_number,
                "review_type": review.review_type,
                "review_date": str(review.review_date),
                "period_start": str(review.review_period_start) if review.review_period_start else None,
                "period_end": str(review.review_period_end) if review.review_period_end else None,
            },
            "portfolio": self._workspace_option(portfolio),
            "planning_cycle_id": review.planning_cycle_id,
            "allocation_plan": allocation_plan,
            "configuration": {
                "id": review.configuration_id,
                "revision": review.configuration_revision,
                "hash": review.configuration_hash,
            },
            "source_as_of": source_as_of,
            "portfolio_membership": membership_payload,
            "portfolio_ranking": {"hash": ranking_hash, "items": ranking_payload},
            "allocation": allocation,
            "budget": budget_payload,
            "resources": resource_payload,
            "scenario_convergence": convergence_payload,
            "gate_context": gate_payload,
            "project_matrix": matrix,
            "portfolio_summary": portfolio_summary,
            "agenda": deepcopy(review.agenda_json or []),
            "warnings": warnings,
            "blockers": blockers,
        }
        return {
            "snapshot": snapshot_payload,
            "source_index": source_index,
            "readiness": readiness,
            "warnings": warnings,
            "blockers": blockers,
            "snapshot_hash": _hash(snapshot_payload),
        }

    def _snapshot_allocation_plan(self, review: PortfolioReviewSession) -> StrategicCapitalAllocationPlan | None:
        if review.allocation_plan_id is not None:
            plan = self._allocation_plan(review.allocation_plan_id)
            self._assert_plan_compatibility(
                plan,
                self._workspace(review.portfolio_workspace_id),
                self._cycle(review.planning_cycle_id) if review.planning_cycle_id else None,
            )
            return plan
        statement = select(StrategicCapitalAllocationPlan).where(
            StrategicCapitalAllocationPlan.tenant_id == self.tenant_id,
            StrategicCapitalAllocationPlan.status == "ENDORSED",
            or_(
                StrategicCapitalAllocationPlan.portfolio_workspace_id == review.portfolio_workspace_id,
                (StrategicCapitalAllocationPlan.portfolio_workspace_id.is_(None))
                & (StrategicCapitalAllocationPlan.scope_workspace_id == review.scope_workspace_id),
            ),
        )
        if review.planning_cycle_id is not None:
            statement = statement.where(StrategicCapitalAllocationPlan.planning_cycle_id == review.planning_cycle_id)
        statement = self._workspace_scope(
            statement,
            func.coalesce(
                StrategicCapitalAllocationPlan.portfolio_workspace_id,
                StrategicCapitalAllocationPlan.scope_workspace_id,
            ),
        )
        plan = self.db.scalars(
            statement.order_by(
                StrategicCapitalAllocationPlan.endorsed_at.desc(), StrategicCapitalAllocationPlan.id.desc()
            )
        ).first()
        self._assert_plan_compatibility(
            plan,
            self._workspace(review.portfolio_workspace_id),
            self._cycle(review.planning_cycle_id) if review.planning_cycle_id else None,
        )
        return plan

    def _snapshot_budget_scenario(
        self, portfolio_id: int, alternative: PortfolioConvergedAlternative | None
    ) -> PortfolioBudgetScenario | None:
        if alternative is not None and alternative.budget_scenario_id is not None:
            return self.db.scalar(
                select(PortfolioBudgetScenario).where(
                    PortfolioBudgetScenario.tenant_id == self.tenant_id,
                    PortfolioBudgetScenario.portfolio_workspace_id == portfolio_id,
                    PortfolioBudgetScenario.id == alternative.budget_scenario_id,
                )
            )
        return self.db.scalars(
            select(PortfolioBudgetScenario)
            .where(
                PortfolioBudgetScenario.tenant_id == self.tenant_id,
                PortfolioBudgetScenario.portfolio_workspace_id == portfolio_id,
                PortfolioBudgetScenario.status == "FROZEN",
            )
            .order_by(PortfolioBudgetScenario.frozen_at.desc(), PortfolioBudgetScenario.id.desc())
        ).first()

    def _snapshot_resource_scenario(
        self, portfolio_id: int, alternative: PortfolioConvergedAlternative | None
    ) -> PortfolioResourceScenario | None:
        if alternative is not None and alternative.resource_scenario_id is not None:
            return self.db.scalar(
                select(PortfolioResourceScenario).where(
                    PortfolioResourceScenario.tenant_id == self.tenant_id,
                    PortfolioResourceScenario.portfolio_workspace_id == portfolio_id,
                    PortfolioResourceScenario.id == alternative.resource_scenario_id,
                )
            )
        return self.db.scalars(
            select(PortfolioResourceScenario)
            .where(
                PortfolioResourceScenario.tenant_id == self.tenant_id,
                PortfolioResourceScenario.portfolio_workspace_id == portfolio_id,
                PortfolioResourceScenario.status == "FROZEN",
            )
            .order_by(PortfolioResourceScenario.frozen_at.desc(), PortfolioResourceScenario.id.desc())
        ).first()

    @staticmethod
    def _convergence_payload(
        convergence: PortfolioScenarioConvergence | None,
        alternative: PortfolioConvergedAlternative | None,
    ) -> dict[str, Any]:
        if convergence is None:
            return {"status": "NOT_AVAILABLE", "source_current": False}
        return {
            "id": convergence.id,
            "logical_code": convergence.logical_code,
            "convergence_revision": convergence.convergence_revision,
            "status": convergence.status,
            "revision_version": convergence.revision_version,
            "recommendation_hash": convergence.recommendation_hash,
            "recommended_alternative_id": convergence.recommended_alternative_id,
            "recommendation_reason": convergence.recommendation_reason,
            "conditions": deepcopy(convergence.conditions_json or []),
            "warnings": deepcopy(convergence.warnings_json or []),
            "blockers": deepcopy(convergence.blockers_json or []),
            "alternative": {
                "id": alternative.id,
                "alternative_name": alternative.alternative_name,
                "alternative_hash": alternative.alternative_hash,
                "alignment_status": alternative.alignment_status,
                "budget_feasibility": alternative.budget_feasibility,
                "resource_feasibility": alternative.resource_feasibility,
                "feasibility_status": alternative.feasibility_status,
                "selected_project_set_hash": alternative.selected_project_set_hash,
                "forced_conflicts": deepcopy(alternative.forced_conflicts_json or []),
            }
            if alternative is not None
            else None,
            "source_current": convergence.status == "RECOMMENDED" and alternative is not None,
        }

    @staticmethod
    def _budget_payload(
        scenario: PortfolioBudgetScenario | None,
        rows: list[PortfolioBudgetScenarioProject],
        alternative: PortfolioConvergedAlternative | None,
    ) -> dict[str, Any]:
        if scenario is None:
            return {"status": "NOT_AVAILABLE", "feasibility": "NOT_AVAILABLE", "projects": []}
        totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        capex: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        expense: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        selected_states = {"SELECTED", "FORCED_IN"}
        for item in rows:
            if item.selection_state not in selected_states:
                continue
            totals[item.currency] += Decimal(item.cost_value)
            capex[item.currency] += Decimal(item.capex_amount or 0)
            expense[item.currency] += Decimal(item.expense_amount or 0)
        return {
            "id": scenario.id,
            "logical_code": scenario.logical_code,
            "scenario_name": scenario.scenario_name,
            "scenario_revision": scenario.scenario_revision,
            "revision_version": scenario.revision_version,
            "status": scenario.status,
            "analytical_status": scenario.analytical_status,
            "feasibility": alternative.budget_feasibility if alternative else scenario.analytical_status,
            "budget_target_id": scenario.budget_target_id,
            "scenario_hash": scenario.scenario_hash,
            "membership_set_hash": scenario.membership_set_hash,
            "evaluation_set_hash": scenario.evaluation_set_hash,
            "selection_distribution": dict(Counter(item.selection_state for item in rows)),
            "totals_by_currency": {key: str(value) for key, value in sorted(totals.items())},
            "capex_by_currency": {key: str(value) for key, value in sorted(capex.items())},
            "expense_by_currency": {key: str(value) for key, value in sorted(expense.items())},
            "multi_currency": len(totals) > 1,
            "normalization_warning": "Amounts remain grouped by currency; no FX conversion is applied."
            if len(totals) > 1
            else None,
            "projects": [PortfolioReviewService._budget_row_payload(item) for item in rows],
        }

    @staticmethod
    def _budget_row_payload(row: PortfolioBudgetScenarioProject | None) -> dict[str, Any]:
        if row is None:
            return {}
        return {
            "scenario_project_id": row.id,
            "selection_state": row.selection_state,
            "portfolio_rank": row.portfolio_rank,
            "cost_value": str(row.cost_value),
            "capex_amount": str(row.capex_amount) if row.capex_amount is not None else None,
            "expense_amount": str(row.expense_amount) if row.expense_amount is not None else None,
            "unclassified_amount": str(row.unclassified_amount),
            "currency": row.currency,
            "cost_as_of_date": str(row.cost_as_of_date),
            "row_hash": row.row_hash,
            "warnings": deepcopy(row.warnings_json or []),
        }

    @staticmethod
    def _resource_payload(
        scenario: PortfolioResourceScenario | None,
        rows: list[PortfolioResourceScenarioProject],
        alternative: PortfolioConvergedAlternative | None,
    ) -> dict[str, Any]:
        if scenario is None:
            return {"status": "NOT_AVAILABLE", "feasibility": "NOT_AVAILABLE", "projects": []}
        return {
            "id": scenario.id,
            "logical_code": scenario.logical_code,
            "scenario_name": scenario.scenario_name,
            "scenario_revision": scenario.scenario_revision,
            "revision_version": scenario.revision_version,
            "status": scenario.status,
            "feasibility": alternative.resource_feasibility if alternative else "NOT_EVALUATED",
            "capacity_plan_id": scenario.capacity_plan_id,
            "capacity_plan_hash": scenario.capacity_plan_hash,
            "scenario_hash": scenario.scenario_hash,
            "membership_set_hash": scenario.membership_set_hash,
            "evaluation_set_hash": scenario.evaluation_set_hash,
            "overload_policy": scenario.overload_policy,
            "selection_distribution": dict(Counter(item.selection_state for item in rows)),
            "shifted_project_count": sum(item.schedule_shift_days != 0 for item in rows),
            "projects": [PortfolioReviewService._resource_row_payload(item) for item in rows],
        }

    @staticmethod
    def _resource_row_payload(row: PortfolioResourceScenarioProject | None) -> dict[str, Any]:
        if row is None:
            return {}
        return {
            "scenario_project_id": row.id,
            "selection_state": row.selection_state,
            "portfolio_rank": row.portfolio_rank,
            "resource_demand_profile_id": row.resource_demand_profile_id,
            "resource_demand_hash": row.resource_demand_hash,
            "source_project_start": str(row.source_project_start) if row.source_project_start else None,
            "source_project_finish": str(row.source_project_finish) if row.source_project_finish else None,
            "scenario_start": str(row.scenario_start) if row.scenario_start else None,
            "scenario_finish": str(row.scenario_finish) if row.scenario_finish else None,
            "schedule_shift_days": row.schedule_shift_days,
            "timing_method": row.timing_method,
            "row_hash": row.row_hash,
        }

    def _gate_payload(
        self,
        preparation: InvestmentGatePreparation | None,
        decisions: list[InvestmentDecision],
        portfolio_project_ids: list[int],
    ) -> tuple[dict[str, Any], dict[int, list[InvestmentDecision]]]:
        decisions_by_project: dict[int, list[InvestmentDecision]] = defaultdict(list)
        decision_payload: list[dict[str, Any]] = []
        for decision in decisions:
            scope_ids = sorted(self._extract_project_ids(decision.decision_package_snapshot_json))
            for project_id in scope_ids:
                if project_id in portfolio_project_ids:
                    decisions_by_project[project_id].append(decision)
            decision_payload.append(
                {
                    "id": decision.id,
                    "decision_number": decision.decision_number,
                    "profile_code": decision.profile_code,
                    "decision_round": decision.decision_round,
                    "status": decision.status,
                    "outcome": decision.outcome,
                    "is_fid": decision.is_fid,
                    "full_funds_authorized": decision.full_funds_authorized,
                    "investment_authorized": decision.investment_authorized,
                    "authorized_amount": str(decision.authorized_amount)
                    if decision.authorized_amount is not None
                    else None,
                    "authorized_currency": decision.authorized_currency,
                    "conditions": deepcopy(decision.conditions_json or []),
                    "decision_hash": decision.decision_hash,
                    "source_preparation_hash": decision.source_preparation_hash,
                    "project_workspace_ids": scope_ids,
                    "project_scope_inferred_from_portfolio": False,
                    "decided_at": decision.decided_at.isoformat() if decision.decided_at else None,
                }
            )
        preparation_payload = (
            {
                "id": preparation.id,
                "preparation_number": preparation.preparation_number,
                "profile_code": preparation.profile_code,
                "revision": preparation.revision,
                "revision_version": preparation.revision_version,
                "status": preparation.status,
                "readiness_status": preparation.readiness_status,
                "source_recommendation_hash": preparation.source_recommendation_hash,
                "preparation_source_hash": preparation.preparation_source_hash,
                "preparation_hash": preparation.preparation_hash,
                "evidence_summary": deepcopy(preparation.evidence_summary_json or {}),
                "warnings": deepcopy(preparation.warnings_json or []),
                "blockers": deepcopy(preparation.blockers_json or []),
            }
            if preparation is not None
            else {"status": "NOT_AVAILABLE", "readiness_status": "NOT_AVAILABLE"}
        )
        payload = {
            "preparation": preparation_payload,
            "investment_decisions": decision_payload,
            "distribution": {
                "decision_outcomes": dict(Counter(item.outcome or "NO_DECISION" for item in decisions)),
                "fid_status": {
                    "FID_GRANTED": sum(item.is_fid for item in decisions),
                    "NOT_FID": sum(not item.is_fid for item in decisions),
                },
            },
            "semantic_boundary": "GATE07K_HOLD_IS_NOT_PORTFOLIO_HOLD_FOR_CAPACITY",
        }
        return payload, decisions_by_project

    @staticmethod
    def _extract_project_ids(value: Any) -> set[int]:
        found: set[int] = set()

        def visit(item: Any, key: str = "") -> None:
            normalized = key.lower()
            if isinstance(item, dict):
                for child_key, child_value in item.items():
                    visit(child_value, str(child_key))
                return
            if isinstance(item, list):
                for child in item:
                    visit(child, key)
                return
            if isinstance(item, int) and normalized in {
                "project_workspace_id",
                "project_id",
                "project_workspace_ids",
                "project_ids",
            }:
                found.add(item)

        visit(value)
        return found

    @staticmethod
    def _risk_payload(record: RiskReadinessAssessment | None) -> dict[str, Any]:
        if record is None:
            return {}
        return {
            "id": record.id,
            "assessment_number": record.assessment_number,
            "assessment_version": record.assessment_version,
            "readiness_status": record.readiness_status,
            "risk_readiness_hash": record.risk_readiness_hash,
            "risk_register_hash": record.risk_register_hash,
            "total_active_risks": record.total_active_risks,
            "high_risk_count": record.high_risk_count,
            "critical_risk_count": record.critical_risk_count,
            "overdue_treatments": record.overdue_treatments,
            "risks_without_acceptance": record.risks_without_acceptance,
            "warnings": deepcopy(record.warnings_json or []),
            "blockers": deepcopy(record.blockers_json or []),
            "as_of_date": record.as_of_date.isoformat(),
            "valid_until": record.valid_until.isoformat(),
        }

    @staticmethod
    def _recommended_matrix(alternative: PortfolioConvergedAlternative | None) -> dict[int, dict[str, Any]]:
        if alternative is None:
            return {}
        result: dict[int, dict[str, Any]] = {}
        for item in list(alternative.project_matrix_json or []):
            if not isinstance(item, dict):
                continue
            project_id = item.get("project_workspace_id") or item.get("project_id")
            if isinstance(project_id, int):
                result[project_id] = deepcopy(item)
        return result

    @staticmethod
    def _capital_by_bucket(allocation: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for item in list(allocation.get("positions") or []):
            if not isinstance(item, dict):
                continue
            position = dict(item.get("current_portfolio") or {})
            result[str(item.get("bucket_code") or "UNCLASSIFIED")] = deepcopy(
                dict(position.get("amount_by_currency") or {})
            )
        return result

    @staticmethod
    def _allocation_variance_summary(allocation: dict[str, Any]) -> dict[str, Any]:
        return {
            str(item.get("bucket_code") or "UNCLASSIFIED"): {
                "status": item.get("status"),
                "variance_vs_target_percentage": item.get("variance_vs_target_percentage"),
                "variance_vs_target_amount": item.get("variance_vs_target_amount"),
            }
            for item in list(allocation.get("positions") or [])
            if isinstance(item, dict)
        }

    @staticmethod
    def _threshold_alerts(
        config: dict[str, Any], summary: dict[str, Any], allocation: dict[str, Any]
    ) -> list[dict[str, Any]]:
        thresholds = dict(config.get("thresholds") or {})
        alerts: list[dict[str, Any]] = []
        tolerance = Decimal(str(thresholds.get("bucket_variance_tolerance_percentage", 5)))
        for bucket, position in dict(summary.get("allocation_variance") or {}).items():
            value = position.get("variance_vs_target_percentage")
            if value is not None and abs(Decimal(str(value))) > tolerance:
                alerts.append(
                    {
                        "code": "BUCKET_VARIANCE_THRESHOLD",
                        "bucket_code": bucket,
                        "value": str(value),
                        "threshold": str(tolerance),
                        "severity": "WARNING",
                    }
                )
        exposure = dict(dict(allocation.get("unclassified") or {}).get("portfolio") or {}).get("percentage")
        if exposure is not None and Decimal(str(exposure)) > Decimal(
            str(thresholds.get("unclassified_exposure_tolerance_percentage", 5))
        ):
            alerts.append(
                {"code": "UNCLASSIFIED_EXPOSURE_THRESHOLD", "percentage": str(exposure), "severity": "WARNING"}
            )
        blocked = int(summary.get("blocked_project_count", 0))
        if blocked and blocked >= int(thresholds.get("blocked_project_count", 1)):
            alerts.append({"code": "BLOCKED_PROJECT_COUNT_THRESHOLD", "count": blocked, "severity": "WARNING"})
        if summary.get("overdue_action_count"):
            alerts.append({"code": "OVERDUE_ACTIONS", "count": summary["overdue_action_count"], "severity": "WARNING"})
        return alerts

    def _snapshot_readiness(
        self,
        review: PortfolioReviewSession,
        source_index: dict[str, dict[str, Any]],
        *,
        membership_count: int,
        allocation_selected: bool,
        allocation_error: str | None,
    ) -> tuple[dict[str, Any], list[str], list[str]]:
        config = self._normalized_configuration(review.configuration_snapshot_json)
        snapshot_policy = dict(config.get("snapshot_policy") or {})
        required = {str(item).upper() for item in snapshot_policy.get("required_sources") or []}
        warnings: list[str] = []
        blockers: list[str] = []
        for key, source in source_index.items():
            exists = bool(source.get("record_id") or source.get("record_count"))
            if key in required and not exists:
                blockers.append(f"Required source {key} is not available.")
            elif key in required and not bool(source.get("source_current")):
                blockers.append(f"Required source {key} is not current.")
            elif not exists:
                warnings.append(f"Optional source {key} is not available.")
            elif not bool(source.get("source_current")):
                warnings.append(f"Optional source {key} is stale or not in a governed terminal state.")
        if membership_count == 0:
            blockers.append("The Portfolio has no active membership to review.")
        if allocation_selected and bool(snapshot_policy.get("require_endorsed_allocation_when_selected", True)):
            allocation_source = source_index["STRATEGIC_ALLOCATION"]
            if not allocation_source.get("source_current"):
                blockers.append("The selected Strategic Allocation Plan must be ENDORSED and readable.")
        if allocation_error:
            blockers.append(f"Wave 2A allocation comparison is not available: {allocation_error}.")
        for key, flag, expected in (
            ("BUDGET_SCENARIO", "require_frozen_budget_when_selected", "FROZEN"),
            ("RESOURCE_SCENARIO", "require_frozen_resource_when_selected", "FROZEN"),
            ("SCENARIO_RECOMMENDATION", "require_recommended_convergence_when_selected", "RECOMMENDED"),
        ):
            source = source_index[key]
            if source.get("record_id") and bool(snapshot_policy.get(flag, True)) and not source.get("source_current"):
                blockers.append(f"Selected source {key} must be {expected} and current.")
        agenda_policy = dict(config.get("review_readiness") or {})
        required_agenda = {
            str(item.get("code") or "")
            for item in list(config.get("agenda_template") or [])
            if isinstance(item, dict) and item.get("required")
        }
        provided_agenda = {str(item.get("code") or "") for item in list(review.agenda_json or [])}
        agenda_ready = required_agenda <= provided_agenda
        if bool(agenda_policy.get("require_agenda_before_freeze", False)) and not agenda_ready:
            blockers.append("Required Portfolio Review agenda sections are missing.")
        components = {
            "SNAPSHOT_READINESS": "READY" if not blockers else "BLOCKED",
            "ALLOCATION_CONTEXT_READINESS": self._source_readiness(
                source_index["STRATEGIC_ALLOCATION"], required, "STRATEGIC_ALLOCATION"
            ),
            "PORTFOLIO_DATA_READINESS": "READY" if membership_count else "BLOCKED",
            "BUDGET_CONTEXT_READINESS": self._source_readiness(
                source_index["BUDGET_SCENARIO"], required, "BUDGET_SCENARIO"
            ),
            "RESOURCE_CONTEXT_READINESS": self._source_readiness(
                source_index["RESOURCE_SCENARIO"], required, "RESOURCE_SCENARIO"
            ),
            "GATE_CONTEXT_READINESS": self._source_readiness(source_index["GATE_CONTEXT"], required, "GATE_CONTEXT"),
            "AGENDA_READINESS": "READY" if agenda_ready else "BLOCKED",
        }
        components["OVERALL_REVIEW_READINESS"] = "READY" if not blockers else "BLOCKED"
        return (
            {
                "status": components["OVERALL_REVIEW_READINESS"],
                "components": components,
                "purpose": "PORTFOLIO_REVIEW_PACKAGE_READINESS_NOT_INVESTMENT_APPROVAL",
            },
            sorted(set(warnings)),
            sorted(set(blockers)),
        )

    @staticmethod
    def _source_readiness(source: dict[str, Any], required: set[str], key: str) -> str:
        exists = bool(source.get("record_id") or source.get("record_count"))
        if not exists:
            return "BLOCKED" if key in required else "NOT_REQUIRED"
        return "READY" if source.get("source_current") else "STALE"

    @staticmethod
    def _snapshot_changes(old: dict[str, Any] | None, new: dict[str, Any]) -> list[dict[str, Any]]:
        if old is None:
            return [{"category": "INITIAL_SNAPSHOT", "changed": True}]
        changes: list[dict[str, Any]] = []
        old_members = {int(item["project_workspace_id"]) for item in list(old.get("portfolio_membership") or [])}
        new_members = {int(item["project_workspace_id"]) for item in list(new.get("portfolio_membership") or [])}
        if old_members != new_members:
            changes.append(
                {
                    "category": "PORTFOLIO_MEMBERSHIP",
                    "added_project_ids": sorted(new_members - old_members),
                    "removed_project_ids": sorted(old_members - new_members),
                }
            )
        old_ranks = {
            int(item["project_workspace_id"]): item.get("rank")
            for item in list(dict(old.get("portfolio_ranking") or {}).get("items") or [])
        }
        new_ranks = {
            int(item["project_workspace_id"]): item.get("rank")
            for item in list(dict(new.get("portfolio_ranking") or {}).get("items") or [])
        }
        rank_changes = [
            {"project_workspace_id": project_id, "before": old_ranks.get(project_id), "after": rank}
            for project_id, rank in sorted(new_ranks.items())
            if old_ranks.get(project_id) != rank
        ]
        if rank_changes:
            changes.append({"category": "PORTFOLIO_RANK", "items": rank_changes})
        comparisons = (
            ("STRATEGIC_ALLOCATION", "allocation", "source_hash"),
            ("BUDGET_SCENARIO", "budget", "scenario_hash"),
            ("RESOURCE_SCENARIO", "resources", "scenario_hash"),
            ("SCENARIO_RECOMMENDATION", "scenario_convergence", "recommendation_hash"),
        )
        for category, section, key in comparisons:
            before = dict(old.get(section) or {}).get(key)
            after = dict(new.get(section) or {}).get(key)
            if before != after:
                changes.append({"category": category, "before": before, "after": after})
        old_gate = _hash(old.get("gate_context") or {})
        new_gate = _hash(new.get("gate_context") or {})
        if old_gate != new_gate:
            changes.append({"category": "GATE_STATUS", "before": old_gate, "after": new_gate})
        old_warnings = set(old.get("warnings") or [])
        new_warnings = set(new.get("warnings") or [])
        old_blockers = set(old.get("blockers") or [])
        new_blockers = set(new.get("blockers") or [])
        if new_warnings - old_warnings or new_blockers - old_blockers:
            changes.append(
                {
                    "category": "READINESS",
                    "new_warnings": sorted(new_warnings - old_warnings),
                    "new_blockers": sorted(new_blockers - old_blockers),
                }
            )
        return changes

    @staticmethod
    def _period_deltas(
        current: dict[str, Any],
        previous: dict[str, Any],
        current_completion: dict[str, Any],
        previous_completion: dict[str, Any],
    ) -> dict[str, Any]:
        current_members = {
            int(item["project_workspace_id"]) for item in list(current.get("portfolio_membership") or [])
        }
        previous_members = {
            int(item["project_workspace_id"]) for item in list(previous.get("portfolio_membership") or [])
        }
        current_ranks = {
            int(item["project_workspace_id"]): item.get("rank")
            for item in list(dict(current.get("portfolio_ranking") or {}).get("items") or [])
        }
        previous_ranks = {
            int(item["project_workspace_id"]): item.get("rank")
            for item in list(dict(previous.get("portfolio_ranking") or {}).get("items") or [])
        }
        rank_deltas = [
            {
                "project_workspace_id": project_id,
                "previous": previous_ranks.get(project_id),
                "current": current_ranks.get(project_id),
            }
            for project_id in sorted(current_members | previous_members)
            if previous_ranks.get(project_id) != current_ranks.get(project_id)
        ]
        current_summary = dict(current.get("portfolio_summary") or {})
        previous_summary = dict(previous.get("portfolio_summary") or {})
        current_actions = list(current_completion.get("actions") or [])
        previous_actions = list(previous_completion.get("actions") or [])
        return {
            "portfolio_membership": {
                "added_project_ids": sorted(current_members - previous_members),
                "removed_project_ids": sorted(previous_members - current_members),
                "current_count": len(current_members),
                "previous_count": len(previous_members),
            },
            "portfolio_rank": rank_deltas,
            "bucket_distribution": {
                "previous": deepcopy(dict(previous_summary.get("projects_by_bucket") or {})),
                "current": deepcopy(dict(current_summary.get("projects_by_bucket") or {})),
            },
            "target_variance": {
                "previous": deepcopy(dict(previous_summary.get("allocation_variance") or {})),
                "current": deepcopy(dict(current_summary.get("allocation_variance") or {})),
            },
            "budget_feasibility": {
                "previous": previous_summary.get("budget_feasibility", "NOT_AVAILABLE"),
                "current": current_summary.get("budget_feasibility", "NOT_AVAILABLE"),
            },
            "resource_feasibility": {
                "previous": previous_summary.get("resource_feasibility", "NOT_AVAILABLE"),
                "current": current_summary.get("resource_feasibility", "NOT_AVAILABLE"),
            },
            "gate_states": {
                "previous": deepcopy(dict(previous_summary.get("gate_status_distribution") or {})),
                "current": deepcopy(dict(current_summary.get("gate_status_distribution") or {})),
            },
            "fid_states": {
                "previous": deepcopy(dict(previous_summary.get("fid_status_distribution") or {})),
                "current": deepcopy(dict(current_summary.get("fid_status_distribution") or {})),
            },
            "actions": {
                "previous": dict(Counter(str(item.get("status") or "") for item in previous_actions)),
                "current": dict(Counter(str(item.get("status") or "") for item in current_actions)),
                "previous_open": int(previous_completion.get("open_action_count") or 0),
                "current_open": int(current_completion.get("open_action_count") or 0),
            },
        }

    # ------------------------------------------------------------------
    # Mapping and aggregate helpers
    # ------------------------------------------------------------------
    def _session_out(
        self, record: PortfolioReviewSession, *, calculate_staleness: bool = True
    ) -> PortfolioReviewSessionOut:
        snapshot = self._current_snapshot(record)
        historical_portfolio = dict(snapshot.snapshot_json.get("portfolio") or {}) if snapshot else {}
        portfolio = (
            None
            if record.status in REVIEW_TERMINAL_STATES and historical_portfolio
            else self._workspace(record.portfolio_workspace_id)
        )
        stale = False
        if calculate_staleness and snapshot is not None and record.status not in REVIEW_TERMINAL_STATES:
            stale, _candidate = self._staleness(record)
        if snapshot is None:
            snapshot_status = "NOT_FROZEN"
        elif record.status == "COMPLETED":
            snapshot_status = "FROZEN_HISTORICAL"
        elif stale:
            snapshot_status = "STALE"
        else:
            snapshot_status = "CURRENT"
        conclusions = [PortfolioReviewConclusionOut.model_validate(item) for item in self._conclusions(record.id)]
        if record.status == "COMPLETED":
            action_payload = list(dict(record.completion_snapshot_json or {}).get("actions") or [])
            action_summary = dict(Counter(str(item.get("status") or "") for item in action_payload))
            actions = [PortfolioReviewActionOut.model_validate(item) for item in action_payload]
        else:
            actions = [self._action_out(item) for item in self._actions(record.id)]
            action_summary = dict(Counter(item.status for item in actions))
        readiness = (
            deepcopy(snapshot.readiness_json)
            if snapshot is not None
            else {
                "status": "NOT_READY",
                "components": {"SNAPSHOT_READINESS": "NOT_STARTED", "OVERALL_REVIEW_READINESS": "NOT_READY"},
                "purpose": "PORTFOLIO_REVIEW_PACKAGE_READINESS_NOT_INVESTMENT_APPROVAL",
            }
        )
        if stale:
            readiness["status"] = "STALE"
            readiness.setdefault("components", {})["SNAPSHOT_READINESS"] = "STALE"
            readiness["components"]["OVERALL_REVIEW_READINESS"] = "STALE"
        summary = deepcopy(dict(snapshot.snapshot_json.get("portfolio_summary") or {})) if snapshot else {}
        summary["actions_by_status"] = action_summary
        summary["open_action_count"] = sum(item.status not in ACTION_TERMINAL_STATES for item in actions)
        summary["overdue_action_count"] = sum(item.overdue for item in actions)
        return PortfolioReviewSessionOut(
            id=record.id,
            review_number=record.review_number,
            portfolio_workspace_id=record.portfolio_workspace_id,
            portfolio_code=str(historical_portfolio.get("code")) if portfolio is None else portfolio.code,
            portfolio_name=str(historical_portfolio.get("name")) if portfolio is None else portfolio.name,
            scope_workspace_id=record.scope_workspace_id,
            planning_cycle_id=record.planning_cycle_id,
            allocation_plan_id=record.allocation_plan_id,
            review_type=record.review_type,
            review_date=record.review_date,
            review_period_start=record.review_period_start,
            review_period_end=record.review_period_end,
            actual_review_date=record.actual_review_date,
            next_planned_review_date=record.next_planned_review_date,
            status=record.status,
            effective_status="STALE" if stale else record.status,
            title=record.title,
            description=record.description,
            chair_user_id=record.chair_user_id,
            secretary_user_id=record.secretary_user_id,
            agenda=deepcopy(record.agenda_json or []),
            configuration_id=record.configuration_id,
            configuration_revision=record.configuration_revision,
            configuration_hash=record.configuration_hash,
            current_snapshot_id=record.current_snapshot_id,
            current_snapshot_hash=record.current_snapshot_hash,
            snapshot_status=snapshot_status,
            snapshot_stale=stale,
            source_current=snapshot is not None and not stale,
            readiness=readiness,
            conclusions=conclusions,
            action_summary=action_summary,
            snapshot={
                **self._snapshot_out(snapshot).model_dump(mode="json"),
                "source_current": not stale,
                "staleness_status": snapshot_status,
                "persisted": True,
            }
            if snapshot
            else None,
            summary=summary,
            actions=actions,
            cadence=self._cadence(record),
            created_by_user_id=record.created_by_user_id,
            prepared_by_user_id=record.prepared_by_user_id,
            review_authority_user_id=record.review_authority_user_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            prepared_at=record.prepared_at,
            review_started_at=record.review_started_at,
            completed_at=record.completed_at,
            revision_version=record.revision_version,
            allowed_actions=self._allowed_review_actions(record, stale),
        )

    def _allowed_review_actions(self, record: PortfolioReviewSession, stale: bool) -> list[str]:
        roles = self.context.role_codes
        admin = "organization_admin" in roles
        preparer = admin or bool(
            roles & {"portfolio_review_preparer", "portfolio_review_manager", "portfolio_review_action_owner"}
        )
        authority = admin or bool(roles & {"portfolio_review_authority", "portfolio_review_board_member"})
        action_approver = admin or "portfolio_review_action_approver" in roles or authority
        actions: list[str] = []
        if record.status in {"DRAFT", "PREPARING", "RETURNED", "READY_FOR_REVIEW", "STALE"} and preparer:
            actions.append("edit")
        if record.status in {"DRAFT", "RETURNED", "STALE"} and preparer:
            actions.append("prepare")
        if record.status in {"PREPARING", "READY_FOR_REVIEW", "IN_REVIEW", "STALE"} and preparer:
            actions.extend(["snapshot_preview", "freeze_snapshot", "create_action"])
        if record.status == "READY_FOR_REVIEW" and not stale and authority:
            actions.append("start_review")
        if record.status == "IN_REVIEW" and authority:
            actions.append("record_conclusion")
            if admin or "portfolio_review_authority" in roles:
                config = self._normalized_configuration(record.configuration_snapshot_json)
                sod = dict(config.get("separation_of_duties") or {})
                if not (
                    bool(sod.get("preparer_cannot_complete", True)) and record.prepared_by_user_id == self.actor_id
                ):
                    actions.append("complete")
        if record.status in {"READY_FOR_REVIEW", "IN_REVIEW"} and action_approver:
            actions.append("approve_action")
        if record.status not in REVIEW_TERMINAL_STATES and authority:
            actions.extend(["cancel", "supersede"])
            if record.status in {"READY_FOR_REVIEW", "IN_REVIEW", "STALE"}:
                actions.append("return")
        return sorted(set(actions))

    def _snapshot_out(self, record: PortfolioReviewSnapshot) -> PortfolioReviewSnapshotOut:
        return PortfolioReviewSnapshotOut.model_validate(record)

    def _action_out(self, record: PortfolioReviewAction) -> PortfolioReviewActionOut:
        roles = self.context.role_codes
        admin = "organization_admin" in roles
        updater = (
            admin
            or "portfolio_review_preparer" in roles
            or ("portfolio_review_action_owner" in roles and record.owner_user_id == self.actor_id)
        )
        approver = admin or bool(
            roles & {"portfolio_review_authority", "portfolio_review_board_member", "portfolio_review_action_approver"}
        )
        dispatcher = admin or bool(roles & {"portfolio_review_authority", "portfolio_review_action_dispatcher"})
        allowed: list[str] = []
        if record.status not in ACTION_TERMINAL_STATES and updater:
            allowed.append("update")
        if record.status == "OPEN" and approver and record.created_by_user_id != self.actor_id:
            allowed.append("approve")
        if record.status in {"ACCEPTED", "IN_PROGRESS"} and record.dispatch_status == "NOT_REQUESTED" and dispatcher:
            allowed.append("dispatch")
        return PortfolioReviewActionOut(
            id=record.id,
            action_number=record.action_number,
            review_session_id=record.review_session_id,
            subject_type=record.subject_type,
            subject_id=record.subject_id,
            subject_key=record.subject_key,
            action_type=record.action_type,
            rationale=record.rationale,
            priority=record.priority,
            owner_user_id=record.owner_user_id,
            due_date=record.due_date,
            status=record.status,
            source_evidence_references_json=deepcopy(record.source_evidence_references_json or []),
            requested_source_authority=record.requested_source_authority,
            dispatch_status=record.dispatch_status,
            execution_reference=record.execution_reference,
            created_by_user_id=record.created_by_user_id,
            approved_by_user_id=record.approved_by_user_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
            approved_at=record.approved_at,
            dispatched_at=record.dispatched_at,
            completed_at=record.completed_at,
            revision_version=record.revision_version,
            overdue=bool(
                record.due_date and record.due_date < date.today() and record.status not in ACTION_TERMINAL_STATES
            ),
            allowed_actions=allowed,
        )

    @staticmethod
    def _action_payload(record: PortfolioReviewAction) -> dict[str, Any]:
        return {
            "id": record.id,
            "action_number": record.action_number,
            "review_session_id": record.review_session_id,
            "subject_type": record.subject_type,
            "subject_id": record.subject_id,
            "subject_key": record.subject_key,
            "action_type": record.action_type,
            "rationale": record.rationale,
            "priority": record.priority,
            "owner_user_id": record.owner_user_id,
            "due_date": str(record.due_date) if record.due_date else None,
            "status": record.status,
            "source_evidence_references_json": deepcopy(record.source_evidence_references_json or []),
            "requested_source_authority": record.requested_source_authority,
            "dispatch_status": record.dispatch_status,
            "execution_reference": record.execution_reference,
            "source_mutation_performed": False,
            "created_by_user_id": record.created_by_user_id,
            "approved_by_user_id": record.approved_by_user_id,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "approved_at": record.approved_at.isoformat() if record.approved_at else None,
            "dispatched_at": record.dispatched_at.isoformat() if record.dispatched_at else None,
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
            "revision_version": record.revision_version,
            "overdue": bool(
                record.due_date and record.due_date < date.today() and record.status not in ACTION_TERMINAL_STATES
            ),
        }

    @staticmethod
    def _conclusion_payload(record: PortfolioReviewConclusion) -> dict[str, Any]:
        return {
            "id": record.id,
            "conclusion_type": record.conclusion_type,
            "rationale": record.rationale,
            "conditions": deepcopy(record.conditions_json or []),
            "created_by_user_id": record.created_by_user_id,
            "created_at": record.created_at.isoformat(),
            "revision_version": record.revision_version,
        }

    def _staleness(self, record: PortfolioReviewSession) -> tuple[bool, dict[str, Any] | None]:
        if record.status in REVIEW_TERMINAL_STATES:
            return False, None
        snapshot = self._current_snapshot(record)
        if snapshot is None:
            return False, None
        try:
            candidate = self._build_snapshot(record)
        except HTTPException:
            return True, None
        policy = dict(self._normalized_configuration(record.configuration_snapshot_json).get("snapshot_policy") or {})
        changed = snapshot.source_index_json != candidate["source_index"] or any(
            snapshot.snapshot_json.get(key) != candidate["snapshot"].get(key)
            for key in ("review", "portfolio", "agenda")
        )
        return bool(candidate["blockers"]) or (
            changed and bool(policy.get("stale_on_any_source_hash_change", True))
        ), candidate

    @staticmethod
    def _cadence(record: PortfolioReviewSession) -> dict[str, Any]:
        policy = dict(record.configuration_snapshot_json.get("cadence") or {})
        grace_days = int(policy.get("late_after_days", 7))
        completed = record.status == "COMPLETED"
        return {
            "planned_date": str(record.review_date),
            "actual_date": str(record.actual_review_date) if record.actual_review_date else None,
            "next_planned_date": str(record.next_planned_review_date) if record.next_planned_review_date else None,
            "late": not completed
            and record.status not in REVIEW_TERMINAL_STATES
            and date.today() > record.review_date + timedelta(days=grace_days),
            "frequency_days": int(policy.get("frequency_days", 90)),
            "late_after_days": grace_days,
        }

    # ------------------------------------------------------------------
    # Configuration resolution and validation
    # ------------------------------------------------------------------
    def _effective_configuration(
        self, workspace: EnterpriseWorkspace | None
    ) -> tuple[dict[str, Any], dict[str, Any], list[EnterpriseWorkspace]]:
        records = list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    AdminConfiguration.status == "published",
                )
                .order_by(AdminConfiguration.revision.desc(), AdminConfiguration.id.desc())
            ).all()
        )
        latest: dict[str, AdminConfiguration] = {}
        for item in records:
            latest.setdefault(item.code, item)
        path = self._workspace_path(workspace) if workspace else []
        selected = None
        for item in reversed(path):
            candidate = latest.get(f"workspace-{item.id}")
            if candidate is not None and (
                workspace is not None
                and item.id == workspace.id
                or bool(candidate.content_json.get("inherit_to_descendants", True))
            ):
                selected = candidate
                break
        selected = selected or latest.get(DEFAULT_CONFIGURATION_CODE)
        if selected is None:
            raise HTTPException(status_code=409, detail={"code": "PORTFOLIO_REVIEW_CONFIGURATION_REQUIRED"})
        effective = self._normalized_configuration(selected.content_json)
        return (
            effective,
            {
                "configuration_id": selected.id,
                "code": selected.code,
                "revision": selected.revision,
                "version": selected.version,
                "content_hash": selected.content_hash,
            },
            path,
        )

    @staticmethod
    def _normalized_configuration(content: dict[str, Any] | None) -> dict[str, Any]:
        def merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
            result = deepcopy(base)
            for key, value in override.items():
                if isinstance(value, dict) and isinstance(result.get(key), dict):
                    result[key] = merge(dict(result[key]), value)
                else:
                    result[key] = deepcopy(value)
            return result

        return merge(DEFAULT_CONFIGURATION, dict(content or {}))

    def _validate_configuration(self, content: dict[str, Any], *, code: str) -> dict[str, Any]:
        normalized = self._normalized_configuration(content)
        for section in (
            "scope",
            "applicability",
            "cadence",
            "snapshot_policy",
            "source_freshness",
            "review_readiness",
            "action_applicability",
            "thresholds",
            "authority",
            "separation_of_duties",
            "numbering",
        ):
            if not isinstance(normalized.get(section), dict):
                raise HTTPException(status_code=422, detail={"code": "INVALID_REVIEW_CONFIGURATION", "field": section})
        for catalog in ("review_types", "conclusion_types", "action_types"):
            rows = normalized.get(catalog)
            if not isinstance(rows, list) or not rows:
                raise HTTPException(status_code=422, detail={"code": "INVALID_REVIEW_CONFIGURATION", "field": catalog})
            codes = [str(item.get("code") or "").strip().upper() for item in rows if isinstance(item, dict)]
            if len(codes) != len(rows) or any(not item for item in codes) or len(codes) != len(set(codes)):
                raise HTTPException(
                    status_code=422, detail={"code": "INVALID_REVIEW_CONFIGURATION_CATALOG", "field": catalog}
                )
            for item, normalized_code in zip(rows, codes, strict=True):
                item["code"] = normalized_code
        agenda = normalized.get("agenda_template")
        if not isinstance(agenda, list):
            raise HTTPException(
                status_code=422, detail={"code": "INVALID_REVIEW_CONFIGURATION", "field": "agenda_template"}
            )
        agenda_codes = [str(item.get("code") or "").strip().upper() for item in agenda if isinstance(item, dict)]
        if len(agenda_codes) != len(agenda) or len(agenda_codes) != len(set(agenda_codes)):
            raise HTTPException(status_code=422, detail={"code": "INVALID_REVIEW_AGENDA_TEMPLATE"})
        for item, agenda_code in zip(agenda, agenda_codes, strict=True):
            item["code"] = agenda_code
        required_sources = {
            str(item).strip().upper()
            for item in dict(normalized.get("snapshot_policy") or {}).get("required_sources") or []
        }
        if not required_sources <= SOURCE_KEYS:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_REVIEW_REQUIRED_SOURCE", "values": sorted(required_sources - SOURCE_KEYS)},
            )
        normalized["snapshot_policy"]["required_sources"] = sorted(required_sources)
        numbering = dict(normalized.get("numbering") or {})
        for field in ("review_padding", "action_padding"):
            try:
                value = int(numbering.get(field))
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=422, detail={"code": "INVALID_REVIEW_NUMBERING", "field": field}
                ) from None
            if not 1 <= value <= 12:
                raise HTTPException(status_code=422, detail={"code": "INVALID_REVIEW_NUMBERING", "field": field})
            numbering[field] = value
        if (
            not str(numbering.get("review_prefix") or "").strip()
            or not str(numbering.get("action_prefix") or "").strip()
        ):
            raise HTTPException(status_code=422, detail={"code": "INVALID_REVIEW_NUMBERING_PREFIX"})
        normalized["numbering"] = numbering
        try:
            for section, fields in (
                ("review_readiness", ("minimum_conclusions_to_complete",)),
                ("applicability", ("minimum_portfolio_size",)),
                ("cadence", ("frequency_days", "late_after_days")),
                ("source_freshness", ("gate_evidence_max_age_days", "risk_readiness_max_age_days")),
                ("thresholds", ("stale_gate_evidence_tolerance_days", "blocked_project_count", "overdue_action_days")),
            ):
                for field in fields:
                    value = int(normalized[section][field])
                    if value < 0 or (field == "frequency_days" and value == 0):
                        raise ValueError(field)
                    normalized[section][field] = value
            for field in (
                "bucket_variance_tolerance_percentage",
                "unclassified_exposure_tolerance_percentage",
                "resource_overload_threshold_percentage",
            ):
                value = Decimal(str(normalized["thresholds"][field]))
                if not value.is_finite() or value < 0:
                    raise ValueError(field)
                normalized["thresholds"][field] = str(value)
        except (TypeError, ValueError, KeyError, InvalidOperation):
            raise HTTPException(status_code=422, detail={"code": "INVALID_REVIEW_POLICY_NUMBER"}) from None
        authority = dict(normalized.get("authority") or {})
        if authority != {"model": "SINGLE_PORTFOLIO_AUTHORITY", "quorum": 1, "voting_rule": "NOT_REQUIRED"}:
            raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_REVIEW_AUTHORITY_MODEL"})
        if any(item.get("dispatch", "REQUEST_ONLY") != "REQUEST_ONLY" for item in normalized["action_types"]):
            raise HTTPException(status_code=422, detail={"code": "REVIEW_ACTION_REQUEST_ONLY_REQUIRED"})
        applicability = dict(normalized.get("applicability") or {})
        if not applicability.get("governance_models"):
            raise HTTPException(status_code=422, detail={"code": "INVALID_REVIEW_APPLICABILITY"})
        scope = dict(normalized.get("scope") or {})
        if code == DEFAULT_CONFIGURATION_CODE and scope.get("workspace_id") is not None:
            raise HTTPException(status_code=422, detail={"code": "DEFAULT_CONFIGURATION_CANNOT_TARGET_WORKSPACE"})
        if code.startswith("workspace-"):
            expected = int(code.removeprefix("workspace-"))
            if int(scope.get("workspace_id") or 0) != expected:
                raise HTTPException(status_code=422, detail={"code": "CONFIGURATION_SCOPE_CODE_MISMATCH"})
        return normalized

    @staticmethod
    def _active_catalog(config: dict[str, Any], key: str) -> list[dict[str, Any]]:
        return [
            deepcopy(item)
            for item in list(config.get(key) or [])
            if isinstance(item, dict) and bool(item.get("active", True))
        ]

    def _catalog_item(self, config: dict[str, Any], key: str, code: str) -> dict[str, Any]:
        normalized = code.strip().upper()
        for item in self._active_catalog(config, key):
            if str(item.get("code") or "").upper() == normalized:
                return item
        raise HTTPException(
            status_code=422,
            detail={"code": "PORTFOLIO_REVIEW_CONFIGURED_VALUE_REQUIRED", "catalog": key, "value": normalized},
        )

    @staticmethod
    def _default_agenda(config: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "code": str(item.get("code") or "").upper(),
                "title": str(item.get("title") or item.get("label") or item.get("code") or ""),
                "status": "NOT_STARTED",
                "notes": "",
                "evidence_references": [],
                "required": bool(item.get("required", False)),
            }
            for item in list(config.get("agenda_template") or [])
            if isinstance(item, dict)
        ]

    # ------------------------------------------------------------------
    # Persistence lookup / scope / idempotency helpers
    # ------------------------------------------------------------------
    def _session(self, review_session_id: int, *, lock: bool = False) -> PortfolioReviewSession:
        statement = select(PortfolioReviewSession).where(
            PortfolioReviewSession.tenant_id == self.tenant_id,
            PortfolioReviewSession.id == review_session_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "PORTFOLIO_REVIEW_NOT_FOUND"})
        self._assert_scope(record.portfolio_workspace_id)
        return record

    def _snapshot(self, snapshot_id: int) -> PortfolioReviewSnapshot:
        record = self.db.scalar(
            select(PortfolioReviewSnapshot).where(
                PortfolioReviewSnapshot.tenant_id == self.tenant_id,
                PortfolioReviewSnapshot.id == snapshot_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "PORTFOLIO_REVIEW_SNAPSHOT_NOT_FOUND"})
        self._session(record.review_session_id)
        return record

    def _current_snapshot(self, review: PortfolioReviewSession) -> PortfolioReviewSnapshot | None:
        if review.current_snapshot_id is None:
            return None
        return self.db.scalar(
            select(PortfolioReviewSnapshot).where(
                PortfolioReviewSnapshot.tenant_id == self.tenant_id,
                PortfolioReviewSnapshot.id == review.current_snapshot_id,
                PortfolioReviewSnapshot.review_session_id == review.id,
            )
        )

    def _required_snapshot(self, review: PortfolioReviewSession) -> PortfolioReviewSnapshot:
        snapshot = self._current_snapshot(review)
        if snapshot is None:
            raise HTTPException(status_code=409, detail={"code": "PORTFOLIO_REVIEW_SNAPSHOT_REQUIRED"})
        return snapshot

    def _conclusion(self, conclusion_id: int, *, lock: bool = False) -> PortfolioReviewConclusion:
        statement = select(PortfolioReviewConclusion).where(
            PortfolioReviewConclusion.tenant_id == self.tenant_id,
            PortfolioReviewConclusion.id == conclusion_id,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "PORTFOLIO_REVIEW_CONCLUSION_NOT_FOUND"})
        self._session(record.review_session_id)
        return record

    def _conclusions(self, review_session_id: int) -> list[PortfolioReviewConclusion]:
        return list(
            self.db.scalars(
                select(PortfolioReviewConclusion)
                .where(
                    PortfolioReviewConclusion.tenant_id == self.tenant_id,
                    PortfolioReviewConclusion.review_session_id == review_session_id,
                )
                .order_by(PortfolioReviewConclusion.created_at, PortfolioReviewConclusion.id)
            ).all()
        )

    def _action(self, action_id: int, *, lock: bool = False) -> PortfolioReviewAction:
        statement = select(PortfolioReviewAction).where(
            PortfolioReviewAction.tenant_id == self.tenant_id,
            PortfolioReviewAction.id == action_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "PORTFOLIO_REVIEW_ACTION_NOT_FOUND"})
        self._session(record.review_session_id)
        return record

    def _locked_follow_up_action(self, action_id: int) -> tuple[PortfolioReviewAction, PortfolioReviewSession]:
        """Serialize action changes with closure; completed reviews retain follow-up."""
        action = self._action(action_id)
        review = self._session(action.review_session_id, lock=True)
        if review.status in {"CANCELLED", "SUPERSEDED"}:
            raise HTTPException(
                status_code=409,
                detail={"code": "PORTFOLIO_REVIEW_ACTION_PARENT_IMMUTABLE", "status": review.status},
            )
        return self._action(action_id, lock=True), review

    def _actions(self, review_session_id: int) -> list[PortfolioReviewAction]:
        return list(
            self.db.scalars(
                select(PortfolioReviewAction)
                .where(
                    PortfolioReviewAction.tenant_id == self.tenant_id,
                    PortfolioReviewAction.review_session_id == review_session_id,
                )
                .order_by(PortfolioReviewAction.created_at, PortfolioReviewAction.id)
            ).all()
        )

    def _workspace(self, workspace_id: int | None) -> EnterpriseWorkspace:
        record = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.id == workspace_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "ENTERPRISE_WORKSPACE_NOT_FOUND"})
        return record

    def _cycle(self, cycle_id: int | None) -> CapitalPlanningCycle:
        record = self.db.scalar(
            select(CapitalPlanningCycle).where(
                CapitalPlanningCycle.tenant_id == self.tenant_id,
                CapitalPlanningCycle.id == cycle_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "CAPITAL_PLANNING_CYCLE_NOT_FOUND"})
        return record

    def _allocation_plan(self, plan_id: int | None) -> StrategicCapitalAllocationPlan:
        record = self.db.scalar(
            select(StrategicCapitalAllocationPlan).where(
                StrategicCapitalAllocationPlan.tenant_id == self.tenant_id,
                StrategicCapitalAllocationPlan.id == plan_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "STRATEGIC_CAPITAL_ALLOCATION_PLAN_NOT_FOUND"})
        self._assert_scope(record.portfolio_workspace_id or record.scope_workspace_id)
        return record

    def _user(self, user_id: int) -> UserAccount:
        record = self.db.scalar(
            select(UserAccount).where(
                UserAccount.tenant_id == self.tenant_id,
                UserAccount.id == user_id,
                UserAccount.status == "active",
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "USER_NOT_FOUND"})
        return record

    def _configuration(self, configuration_id: int, *, lock: bool = False) -> AdminConfiguration:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
            AdminConfiguration.id == configuration_id,
        )
        record = self.db.scalar(statement.with_for_update() if lock else statement)
        if record is None or not self._configuration_visible(record):
            raise HTTPException(status_code=404, detail={"code": "PORTFOLIO_REVIEW_CONFIGURATION_NOT_FOUND"})
        return record

    def _configuration_visible(self, record: AdminConfiguration) -> bool:
        if self.context.organization_wide:
            return True
        target_id = dict(record.content_json.get("scope") or {}).get("workspace_id")
        if target_id is None:
            return record.status == "published"
        try:
            self._assert_scope(int(target_id))
            return True
        except HTTPException:
            if record.status != "published":
                return False
            return any(
                int(target_id) in {item.id for item in self._workspace_path(self._workspace(allowed))}
                for allowed in self.context.workspace_ids
            )

    def _assert_configuration_mutable_scope(self, record: AdminConfiguration) -> None:
        target_id = dict(record.content_json.get("scope") or {}).get("workspace_id")
        if target_id is not None:
            self._assert_scope(int(target_id))
        elif not self.context.organization_wide:
            raise HTTPException(status_code=403, detail={"code": "CONFIGURATION_TENANT_SCOPE_DENIED"})

    @staticmethod
    def _workspace_option(record: EnterpriseWorkspace) -> dict[str, Any]:
        return {
            "id": record.id,
            "code": record.code,
            "name": record.name,
            "workspace_type_code": record.workspace_type_code,
            "status": record.status,
            "parent_id": record.parent_id,
            "version": record.version,
        }

    def _workspace_path(self, workspace: EnterpriseWorkspace | None) -> list[EnterpriseWorkspace]:
        if workspace is None:
            return []
        path: list[EnterpriseWorkspace] = []
        current: EnterpriseWorkspace | None = workspace
        seen: set[int] = set()
        while current is not None:
            if current.id in seen:
                raise HTTPException(status_code=409, detail={"code": "WORKSPACE_HIERARCHY_CYCLE"})
            seen.add(current.id)
            path.append(current)
            current = self._workspace(current.parent_id) if current.parent_id is not None else None
        return list(reversed(path))

    def _assert_scope(self, workspace_id: int) -> None:
        if self.context.organization_wide:
            return
        if workspace_id in self.context.workspace_ids:
            return
        path_ids = {item.id for item in self._workspace_path(self._workspace(workspace_id))}
        if path_ids & set(self.context.workspace_ids):
            return
        raise HTTPException(status_code=403, detail={"code": "WORKSPACE_SCOPE_DENIED"})

    def _workspace_scope(self, statement, column):
        if self.context.organization_wide:
            return statement
        allowed = set(self.context.workspace_ids)
        if allowed:
            descendants: set[int] = set(allowed)
            workspaces = list(
                self.db.scalars(
                    select(EnterpriseWorkspace).where(EnterpriseWorkspace.tenant_id == self.tenant_id)
                ).all()
            )
            changed = True
            while changed:
                changed = False
                for item in workspaces:
                    if item.parent_id in descendants and item.id not in descendants:
                        descendants.add(item.id)
                        changed = True
            return statement.where(column.in_(descendants))
        return statement.where(column.in_([-1]))

    @staticmethod
    def _assert_portfolio(workspace: EnterpriseWorkspace) -> None:
        if workspace.workspace_type_code != "portfolio":
            raise HTTPException(status_code=422, detail={"code": "PORTFOLIO_WORKSPACE_REQUIRED"})

    def _assert_applicable_portfolio(self, portfolio: EnterpriseWorkspace) -> None:
        effective, _source, _path = self._effective_configuration(portfolio)
        applicability = dict(effective.get("applicability") or {})
        governance_model = str(
            (portfolio.defaults_json or {}).get("governance_model")
            or (portfolio.defaults_json or {}).get("governance_model_code")
            or "CAPITAL_OWNER"
        ).upper()
        if governance_model not in {str(item).upper() for item in applicability.get("governance_models") or []}:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "PORTFOLIO_REVIEW_GOVERNANCE_MODEL_NOT_APPLICABLE",
                    "governance_model": governance_model,
                },
            )
        statuses = {str(item).lower() for item in applicability.get("portfolio_statuses") or []}
        if statuses and portfolio.status.lower() not in statuses:
            raise HTTPException(status_code=422, detail={"code": "PORTFOLIO_REVIEW_STATUS_NOT_APPLICABLE"})
        minimum = int(applicability.get("minimum_portfolio_size", 0))
        count = int(
            self.db.scalar(
                select(func.count(PortfolioProjectMembership.id)).where(
                    PortfolioProjectMembership.tenant_id == self.tenant_id,
                    PortfolioProjectMembership.portfolio_workspace_id == portfolio.id,
                    PortfolioProjectMembership.status == "ACTIVE",
                )
            )
            or 0
        )
        if count < minimum:
            raise HTTPException(
                status_code=422, detail={"code": "PORTFOLIO_REVIEW_MINIMUM_SIZE_REQUIRED", "minimum": minimum}
            )

    def _assert_scope_compatible(self, scope: EnterpriseWorkspace, portfolio: EnterpriseWorkspace) -> None:
        if scope.id not in {item.id for item in self._workspace_path(portfolio)}:
            raise HTTPException(status_code=422, detail={"code": "PORTFOLIO_REVIEW_SCOPE_INCOMPATIBLE"})

    def _assert_plan_compatibility(
        self,
        plan: StrategicCapitalAllocationPlan | None,
        portfolio: EnterpriseWorkspace,
        cycle: CapitalPlanningCycle | None,
    ) -> None:
        # A cycle is an authority context even when no Allocation Plan is selected.
        # Ancestor/global cycles are valid for a scoped portfolio actor; requiring a
        # direct grant on that ancestor would incorrectly widen the permission model.
        if cycle is None and plan is not None:
            cycle = self._cycle(plan.planning_cycle_id)
        if cycle is not None and cycle.scope_workspace_id is not None:
            self._assert_scope_compatible(self._workspace(cycle.scope_workspace_id), portfolio)
        if plan is None:
            return
        if plan.portfolio_workspace_id is not None and plan.portfolio_workspace_id != portfolio.id:
            raise HTTPException(status_code=422, detail={"code": "ALLOCATION_PLAN_PORTFOLIO_MISMATCH"})
        self._assert_scope_compatible(self._workspace(plan.scope_workspace_id), portfolio)
        if cycle is not None and plan.planning_cycle_id != cycle.id:
            raise HTTPException(status_code=422, detail={"code": "ALLOCATION_PLAN_CYCLE_MISMATCH"})

    def _validate_action_subject(
        self, review: PortfolioReviewSession, subject_type: str, subject_id: int | None, subject_key: str | None = None
    ) -> None:
        if subject_type != "BUCKET" and subject_key is not None:
            raise HTTPException(status_code=422, detail={"code": "REVIEW_ACTION_SUBJECT_KEY_NOT_APPLICABLE"})
        if subject_type == "PORTFOLIO":
            if subject_id not in {None, review.portfolio_workspace_id}:
                raise HTTPException(status_code=422, detail={"code": "REVIEW_ACTION_PORTFOLIO_MISMATCH"})
            return
        if subject_type == "PROJECT":
            if subject_id is None:
                raise HTTPException(status_code=422, detail={"code": "REVIEW_ACTION_SUBJECT_ID_REQUIRED"})
            membership = self.db.scalar(
                select(PortfolioProjectMembership.id).where(
                    PortfolioProjectMembership.tenant_id == self.tenant_id,
                    PortfolioProjectMembership.portfolio_workspace_id == review.portfolio_workspace_id,
                    PortfolioProjectMembership.project_workspace_id == subject_id,
                    PortfolioProjectMembership.status == "ACTIVE",
                )
            )
            if membership is None:
                raise HTTPException(status_code=422, detail={"code": "REVIEW_ACTION_PROJECT_OUTSIDE_PORTFOLIO"})
            return
        if subject_type == "PORTFOLIO_MEMBERSHIP":
            if subject_id is None:
                raise HTTPException(status_code=422, detail={"code": "REVIEW_ACTION_SUBJECT_ID_REQUIRED"})
            membership = self.db.scalar(
                select(PortfolioProjectMembership.id).where(
                    PortfolioProjectMembership.tenant_id == self.tenant_id,
                    PortfolioProjectMembership.portfolio_workspace_id == review.portfolio_workspace_id,
                    PortfolioProjectMembership.id == subject_id,
                    PortfolioProjectMembership.status == "ACTIVE",
                )
            )
            if membership is None:
                raise HTTPException(status_code=422, detail={"code": "REVIEW_ACTION_MEMBERSHIP_OUTSIDE_PORTFOLIO"})
            return
        if subject_type == "BUCKET":
            snapshot = self._current_snapshot(review)
            if snapshot is None:
                raise HTTPException(status_code=422, detail={"code": "REVIEW_ACTION_BUCKET_SNAPSHOT_REQUIRED"})
            keys = {
                str(item.get("bucket_code") or "").lower()
                for item in dict(snapshot.snapshot_json.get("allocation") or {}).get("positions", [])
            }
            keys.add("unclassified")
            if subject_id is not None or not subject_key or subject_key.strip().lower() not in keys:
                raise HTTPException(status_code=422, detail={"code": "REVIEW_ACTION_BUCKET_OUTSIDE_SNAPSHOT"})
            return
        raise HTTPException(status_code=422, detail={"code": "REVIEW_ACTION_SUBJECT_TYPE_INVALID"})

    @staticmethod
    def _assert_review_mutable(record: PortfolioReviewSession) -> None:
        if record.status in REVIEW_TERMINAL_STATES:
            raise HTTPException(
                status_code=409,
                detail={"code": "PORTFOLIO_REVIEW_IMMUTABLE", "status": record.status},
            )

    def _reserve_number(self, rule_code: str, *, prefix: str, padding: int, separator: str) -> str:
        sequence = self.db.scalar(
            select(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == rule_code,
                AdminNumberSequence.scope_key == "tenant",
            )
            .with_for_update()
        )
        if sequence is None:
            sequence = AdminNumberSequence(
                tenant_id=self.tenant_id,
                rule_code=rule_code,
                scope_key="tenant",
                next_value=1,
                version=1,
            )
            self.db.add(sequence)
            self.db.flush()
        value = sequence.next_value
        sequence.next_value += 1
        sequence.version += 1
        sequence.updated_at = utc_now()
        return f"{prefix.strip().upper()}{separator}{value:0{padding}d}"

    def _command_replay(
        self, command_type: str, idempotency_key: str, request_hash: str
    ) -> PortfolioReviewCommand | None:
        record = self.db.scalar(
            select(PortfolioReviewCommand).where(
                PortfolioReviewCommand.tenant_id == self.tenant_id,
                PortfolioReviewCommand.idempotency_key == idempotency_key,
            )
        )
        if record is None:
            return None
        if record.command_type != command_type or record.request_hash != request_hash:
            raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_KEY_REUSED"})
        return record

    def _record_command(
        self,
        command_type: str,
        idempotency_key: str,
        request_hash: str,
        *,
        review_session_id: int | None = None,
        review_action_id: int | None = None,
        result: dict[str, Any],
    ) -> None:
        self.db.add(
            PortfolioReviewCommand(
                tenant_id=self.tenant_id,
                review_session_id=review_session_id,
                review_action_id=review_action_id,
                command_type=command_type,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                result_json=deepcopy(result),
                actor_user_id=self.actor_id,
            )
        )

    @staticmethod
    def _check_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise HTTPException(
                status_code=412,
                detail={"code": "ETAG_MISMATCH", "expected": expected, "actual": actual},
            )

    @staticmethod
    def _assert_same_request(actual_hash: str | None, expected_hash: str) -> None:
        if actual_hash != expected_hash:
            raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_KEY_REUSED"})

    def _touch_review(self, record: PortfolioReviewSession) -> None:
        record.last_modified_by_user_id = self.actor_id
        record.updated_at = utc_now()
        record.revision_version += 1

    def _event(self, event_type: str, target_type: str, target_id: int | None, metadata: dict[str, Any]) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type=target_type,
                target_id=target_id,
                metadata_json=deepcopy(metadata),
            )
        )
