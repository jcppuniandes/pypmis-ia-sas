"""Gate 07J-FUND governed strategic Funds and Funding Readiness service."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, AdminNumberSequence, EnterpriseWorkspace, SecurityEvent
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.funds_manager.models import (
    Fund,
    FundingAssignment,
    FundingReadinessSnapshot,
    StrategicFundingSource,
)
from app.modules.funds_manager.schemas import (
    ConfigurationPreviewOut,
    FundCreateIn,
    FundingAssignmentCreateIn,
    FundingAssignmentOut,
    FundingOverviewOut,
    FundingReadinessOut,
    FundingRefreshPreviewOut,
    FundingSourceCreateIn,
    FundingSourceOut,
    FundOut,
    InvestmentGateFundingEvidenceOut,
)
from app.modules.portfolio_budget.models import PortfolioBudgetScenarioProject
from app.modules.portfolio_budget.service import PortfolioBudgetService
from app.modules.portfolio_convergence.service import PortfolioConvergenceService
from app.modules.portfolio_planning.models import PortfolioProjectMembership

CONFIGURATION_KIND = "funds_manager_configuration"
DEFAULT_CODE = "gate07j-fund-default"
READY_OUTPUT = "READY_FOR_GOVERNED_FUNDING_EVIDENCE"
REWORK_OUTPUT = "GATE07J_FUND_REWORK_REQUIRED"

SOURCE_TYPES = {
    "CORPORATE_CAPEX",
    "OPERATING_CASH",
    "DEBT_FACILITY",
    "BANK_LOAN",
    "BOND",
    "GRANT",
    "GOVERNMENT_APPROPRIATION",
    "JV_CONTRIBUTION",
    "PARTNER_CONTRIBUTION",
    "DEVELOPMENT_BANK",
    "OTHER",
}

DEFAULT_CONFIGURATION: dict[str, Any] = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "applicable_governance_models": ["CAPITAL_OWNER"],
    "allowed_source_types": sorted(SOURCE_TYPES),
    "allowed_assignment_scopes": ["PORTFOLIO", "PROJECT", "RECOMMENDED_PROJECT_SET"],
    "fund_lifecycle_states": ["DRAFT", "AUTHORIZED", "ACTIVE", "SUSPENDED", "EXHAUSTED", "CLOSED", "SUPERSEDED"],
    "assignment_lifecycle_states": ["DRAFT", "RESERVED", "CONFIRMED", "RELEASED", "CANCELLED", "EXPIRED"],
    "reserved_counts_toward_readiness": False,
    "conditional_funds_count_toward_readiness": False,
    "open_condition_is_blocker": True,
    "minimum_confirmed_coverage_percent": 100,
    "minimum_potential_coverage_percent": 100,
    "require_each_project_coverage": False,
    "minimum_project_coverage_percent": 100,
    "require_period_coverage": False,
    "minimum_period_coverage_percent": 100,
    "expiry_horizon_days": 30,
    "currency_policy": {"require_common_currency": True, "allow_governed_normalized_amount": True, "fx_engine": False},
    "allow_reserved_overbooking": True,
    "allow_confirmed_over_allocation": False,
    "fund_creator_cannot_authorize": True,
    "assignment_preparer_cannot_confirm": False,
    "restriction_catalog": [
        "project_types",
        "strategic_objectives",
        "business_units",
        "portfolio_ids",
        "project_ids",
        "geographies",
        "eligible_cost_categories",
        "maximum_amount",
        "minimum_co_funding",
        "environmental_social_conditions",
        "sponsor_conditions",
    ],
    "condition_statuses": ["OPEN", "EVIDENCE_PROVIDED", "SATISFIED", "WAIVED", "EXPIRED"],
    "investment_gate_compatibility": {
        "PYP-INV-SELECT": {"funding_readiness_required": False, "reserved_may_count": True},
        "PYP-FFA": {"funding_readiness_required": True, "confirmed_coverage_percent": 100},
    },
    "numbering": {"source_prefix": "FSRC", "fund_prefix": "FUND", "assignment_prefix": "FASN"},
}


class FundsManagerService:
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

    # Configuration bootstrap -------------------------------------
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
                name="Default Funds & Funding Readiness Configuration",
                description="Gate 07J-FUND starter policy. Review and publish before governed readiness is supplied.",
                status="draft",
                revision=1,
                version=1,
                content_json=content,
                content_hash=_hash(content),
                created_by_user_id=self.actor_id,
            )
        )
        self._event("funds.configuration_seeded_as_draft", "AdminConfiguration", None, {})
        self.db.commit()

    # Funding Sources ---------------------------------------------
    def funding_sources(self) -> list[FundingSourceOut]:
        records = list(
            self.db.scalars(
                select(StrategicFundingSource)
                .where(StrategicFundingSource.tenant_id == self.tenant_id)
                .order_by(StrategicFundingSource.source_code)
            ).all()
        )
        return [self._source_out(item) for item in records]

    def funding_source(self, source_id: int) -> FundingSourceOut:
        return self._source_out(self._source(source_id))

    def create_funding_source(self, payload: FundingSourceCreateIn) -> FundingSourceOut:
        retry = self.db.scalar(
            select(StrategicFundingSource).where(
                StrategicFundingSource.tenant_id == self.tenant_id,
                StrategicFundingSource.create_idempotency_key == payload.idempotency_key,
            )
        )
        if retry is not None:
            return self._source_out(retry)
        policy = self._policy(None, require_published=True)
        if payload.source_type not in set(policy.get("allowed_source_types", [])):
            raise HTTPException(status_code=422, detail={"code": "FUNDING_SOURCE_TYPE_NOT_ALLOWED"})
        code = (payload.source_code or self._next_number("funding-source", "source_prefix", "FSRC")).strip().upper()
        record = StrategicFundingSource(
            tenant_id=self.tenant_id,
            source_code=code,
            source_name=payload.source_name.strip(),
            source_type=payload.source_type,
            description=payload.description.strip(),
            legal_entity_provider_reference=_clean(payload.legal_entity_provider_reference),
            currency=payload.currency,
            status="DRAFT",
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            restrictions_json=deepcopy(payload.restrictions),
            evidence_refs_json=deepcopy(payload.evidence_refs),
            source_reference=_clean(payload.source_reference),
            revision_version=1,
            create_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        record.source_hash = self._source_hash(record)
        self.db.add(record)
        self.db.flush()
        self._event("funding_source.created", "StrategicFundingSource", record.id, {"source_code": code})
        self.db.commit()
        self.db.refresh(record)
        return self._source_out(record)

    def update_funding_source(self, source_id: int, expected_version: int, payload) -> FundingSourceOut:
        record = self._source(source_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status not in {"DRAFT", "ACTIVE", "SUSPENDED"}:
            raise HTTPException(status_code=409, detail={"code": "HISTORICAL_FUNDING_SOURCE_IMMUTABLE"})
        policy = self._policy(None, require_published=True)
        if payload.source_type not in set(policy.get("allowed_source_types", [])):
            raise HTTPException(status_code=422, detail={"code": "FUNDING_SOURCE_TYPE_NOT_ALLOWED"})
        if record.currency != payload.currency and self._source_has_assignments(record.id):
            raise HTTPException(status_code=409, detail={"code": "USED_FUNDING_SOURCE_CURRENCY_IMMUTABLE"})
        for key in (
            "source_name",
            "source_type",
            "description",
            "legal_entity_provider_reference",
            "currency",
            "effective_from",
            "effective_to",
            "source_reference",
        ):
            setattr(record, key, getattr(payload, key))
        record.restrictions_json = deepcopy(payload.restrictions)
        record.evidence_refs_json = deepcopy(payload.evidence_refs)
        self._touch(record)
        record.source_hash = self._source_hash(record)
        self._event("funding_source.updated", "StrategicFundingSource", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._source_out(record)

    def transition_funding_source(
        self, source_id: int, expected_version: int, action: str, idempotency_key: str
    ) -> FundingSourceOut:
        key_field = {
            "activate": "activate_idempotency_key",
            "suspend": "suspend_idempotency_key",
            "close": "close_idempotency_key",
        }[action]
        retry = self.db.scalar(
            select(StrategicFundingSource).where(
                StrategicFundingSource.tenant_id == self.tenant_id,
                getattr(StrategicFundingSource, key_field) == idempotency_key,
            )
        )
        if retry is not None:
            return self._source_out(retry)
        record = self._source(source_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        transitions = {
            "activate": ({"DRAFT", "SUSPENDED"}, "ACTIVE"),
            "suspend": ({"ACTIVE"}, "SUSPENDED"),
            "close": ({"ACTIVE", "SUSPENDED"}, "CLOSED"),
        }
        allowed, target = transitions[action]
        if record.status not in allowed:
            raise HTTPException(status_code=409, detail={"code": "INVALID_FUNDING_SOURCE_TRANSITION"})
        if action == "activate" and record.effective_to and record.effective_to < date.today():
            raise HTTPException(status_code=409, detail={"code": "FUNDING_SOURCE_EXPIRED"})
        record.status = target
        setattr(record, key_field, idempotency_key)
        self._touch(record)
        record.source_hash = self._source_hash(record)
        self._event(
            f"funding_source.{action}{'d' if action.endswith('e') else 'ed'}", "StrategicFundingSource", record.id, {}
        )
        self.db.commit()
        self.db.refresh(record)
        return self._source_out(record)

    # Funds --------------------------------------------------------
    def funds(self) -> list[FundOut]:
        records = list(
            self.db.scalars(select(Fund).where(Fund.tenant_id == self.tenant_id).order_by(Fund.fund_code)).all()
        )
        return [self._fund_out(item) for item in records]

    def fund(self, fund_id: int) -> FundOut:
        return self._fund_out(self._fund(fund_id))

    def create_fund(self, payload: FundCreateIn) -> FundOut:
        retry = self.db.scalar(
            select(Fund).where(Fund.tenant_id == self.tenant_id, Fund.create_idempotency_key == payload.idempotency_key)
        )
        if retry is not None:
            return self._fund_out(retry)
        source = self._source(payload.funding_source_id) if payload.funding_source_id else None
        if source and source.currency != payload.currency:
            raise HTTPException(status_code=422, detail={"code": "FUND_SOURCE_CURRENCY_MISMATCH"})
        code = (payload.fund_code or self._next_number("fund", "fund_prefix", "FUND")).strip().upper()
        record = Fund(
            tenant_id=self.tenant_id,
            fund_code=code,
            fund_name=payload.fund_name.strip(),
            funding_source_id=payload.funding_source_id,
            description=payload.description.strip(),
            currency=payload.currency,
            authorized_amount=payload.authorized_amount,
            available_from=payload.available_from,
            available_to=payload.available_to,
            period_granularity=payload.period_granularity,
            authorized_amount_by_period_json=_jsonable(payload.authorized_amount_by_period),
            status="DRAFT",
            restrictions_json=deepcopy(payload.restrictions),
            applicable_workspace_scope_json=deepcopy(payload.applicable_workspace_scope),
            evidence_refs_json=deepcopy(payload.evidence_refs),
            source_reference=_clean(payload.source_reference),
            revision_version=1,
            create_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        record.fund_hash = self._fund_hash(record, source)
        self.db.add(record)
        self.db.flush()
        self._event("fund.created", "Fund", record.id, {"fund_code": code})
        self.db.commit()
        self.db.refresh(record)
        return self._fund_out(record)

    def update_fund(self, fund_id: int, expected_version: int, payload) -> FundOut:
        record = self._fund(fund_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "AUTHORIZED_FUND_IMMUTABLE"})
        source = self._source(payload.funding_source_id) if payload.funding_source_id else None
        if source and source.currency != payload.currency:
            raise HTTPException(status_code=422, detail={"code": "FUND_SOURCE_CURRENCY_MISMATCH"})
        for key in (
            "fund_name",
            "funding_source_id",
            "description",
            "currency",
            "authorized_amount",
            "available_from",
            "available_to",
            "period_granularity",
            "source_reference",
        ):
            setattr(record, key, getattr(payload, key))
        record.authorized_amount_by_period_json = _jsonable(payload.authorized_amount_by_period)
        record.restrictions_json = deepcopy(payload.restrictions)
        record.applicable_workspace_scope_json = deepcopy(payload.applicable_workspace_scope)
        record.evidence_refs_json = deepcopy(payload.evidence_refs)
        self._touch(record)
        record.fund_hash = self._fund_hash(record, source)
        self._event("fund.updated", "Fund", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._fund_out(record)

    def transition_fund(self, fund_id: int, expected_version: int, action: str, idempotency_key: str) -> FundOut:
        key_field = {
            "authorize": "authorize_idempotency_key",
            "activate": "activate_idempotency_key",
            "suspend": "suspend_idempotency_key",
            "close": "close_idempotency_key",
        }[action]
        retry = self.db.scalar(
            select(Fund).where(Fund.tenant_id == self.tenant_id, getattr(Fund, key_field) == idempotency_key)
        )
        if retry is not None:
            return self._fund_out(retry)
        record = self._fund(fund_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        policy = self._policy(None, require_published=True)
        transitions = {
            "authorize": ({"DRAFT"}, "AUTHORIZED"),
            "activate": ({"AUTHORIZED", "SUSPENDED"}, "ACTIVE"),
            "suspend": ({"ACTIVE"}, "SUSPENDED"),
            "close": ({"AUTHORIZED", "ACTIVE", "SUSPENDED", "EXHAUSTED"}, "CLOSED"),
        }
        allowed, target = transitions[action]
        if record.status not in allowed:
            raise HTTPException(status_code=409, detail={"code": "INVALID_FUND_TRANSITION"})
        source = self._source(record.funding_source_id) if record.funding_source_id else None
        if action in {"authorize", "activate"} and source and source.status != "ACTIVE":
            raise HTTPException(status_code=409, detail={"code": "ACTIVE_FUNDING_SOURCE_REQUIRED"})
        if action == "authorize" and policy.get("fund_creator_cannot_authorize") and record.created_by == self.actor_id:
            raise HTTPException(status_code=409, detail={"code": "FUND_AUTHORIZATION_FOUR_EYES_REQUIRED"})
        if action == "activate" and record.available_to and record.available_to < date.today():
            raise HTTPException(status_code=409, detail={"code": "FUND_EXPIRED"})
        record.status = target
        setattr(record, key_field, idempotency_key)
        if action == "authorize":
            record.authorized_by = self.actor_id
            record.authorized_at = utc_now()
        self._touch(record)
        record.fund_hash = self._fund_hash(record, source)
        self._event(f"fund.{action}{'d' if action.endswith('e') else 'ed'}", "Fund", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._fund_out(record)

    # Funding Assignments -----------------------------------------
    def funding_assignments(
        self,
        *,
        portfolio_id: int | None = None,
        project_id: int | None = None,
        fund_id: int | None = None,
    ) -> list[FundingAssignmentOut]:
        statement = select(FundingAssignment).where(FundingAssignment.tenant_id == self.tenant_id)
        if portfolio_id is not None:
            statement = statement.where(FundingAssignment.portfolio_workspace_id == portfolio_id)
        if project_id is not None:
            statement = statement.where(FundingAssignment.project_workspace_id == project_id)
        if fund_id is not None:
            statement = statement.where(FundingAssignment.fund_id == fund_id)
        records = list(self.db.scalars(statement.order_by(FundingAssignment.assignment_number)).all())
        return [self._assignment_out(item) for item in records]

    def funding_assignment(self, assignment_id: int) -> FundingAssignmentOut:
        return self._assignment_out(self._assignment(assignment_id))

    def create_funding_assignment(self, payload: FundingAssignmentCreateIn) -> FundingAssignmentOut:
        retry = self.db.scalar(
            select(FundingAssignment).where(
                FundingAssignment.tenant_id == self.tenant_id,
                FundingAssignment.create_idempotency_key == payload.idempotency_key,
            )
        )
        if retry is not None:
            return self._assignment_out(retry)
        policy = self._policy(payload.portfolio_workspace_id, require_published=True)
        if payload.scope_type not in set(policy.get("allowed_assignment_scopes", [])):
            raise HTTPException(status_code=422, detail={"code": "FUNDING_ASSIGNMENT_SCOPE_NOT_ALLOWED"})
        fund = self._fund(payload.fund_id, lock=True)
        if fund.status not in {"AUTHORIZED", "ACTIVE"}:
            raise HTTPException(status_code=409, detail={"code": "AUTHORIZED_FUND_REQUIRED"})
        if fund.currency != payload.currency:
            raise HTTPException(status_code=422, detail={"code": "ASSIGNMENT_FUND_CURRENCY_MISMATCH"})
        parent = self._assignment(payload.parent_assignment_id) if payload.parent_assignment_id else None
        if parent and (parent.fund_id != fund.id or parent.tenant_id != self.tenant_id):
            raise HTTPException(status_code=422, detail={"code": "PARENT_ASSIGNMENT_FUND_MISMATCH"})
        self._validate_assignment_targets(payload)
        if payload.scope_type == "RECOMMENDED_PROJECT_SET":
            contract = self._requirement_contract(payload.portfolio_workspace_id)
            if (
                payload.source_convergence_id != contract["convergence_id"]
                or payload.source_recommendation_hash != contract["recommendation_hash"]
                or payload.recommended_project_set_hash != contract["selected_project_set_hash"]
            ):
                raise HTTPException(status_code=412, detail={"code": "STALE_PORTFOLIO_RECOMMENDATION"})
        code = self._next_number("funding-assignment", "assignment_prefix", "FASN")
        record = FundingAssignment(
            tenant_id=self.tenant_id,
            fund_id=fund.id,
            parent_assignment_id=payload.parent_assignment_id,
            assignment_number=code,
            scope_type=payload.scope_type,
            portfolio_workspace_id=payload.portfolio_workspace_id,
            project_workspace_id=payload.project_workspace_id,
            recommended_project_set_hash=payload.recommended_project_set_hash,
            source_convergence_id=payload.source_convergence_id,
            source_recommendation_hash=payload.source_recommendation_hash,
            amount=payload.amount,
            currency=payload.currency,
            normalized_amount=payload.normalized_amount,
            normalized_currency=payload.normalized_currency,
            fx_source_reference=_clean(payload.fx_source_reference),
            fx_as_of_date=payload.fx_as_of_date,
            fx_hash=payload.fx_hash,
            period_start=payload.period_start,
            period_end=payload.period_end,
            period_profile_json=_jsonable(payload.period_profile),
            status="DRAFT",
            assignment_purpose=payload.assignment_purpose.strip(),
            eligibility_status="ELIGIBLE",
            conditions_json=deepcopy(payload.conditions),
            evidence_refs_json=deepcopy(payload.evidence_refs),
            revision_version=1,
            create_idempotency_key=payload.idempotency_key,
            prepared_by=self.actor_id,
            updated_by=self.actor_id,
        )
        record.assignment_hash = self._assignment_hash(record)
        self.db.add(record)
        self.db.flush()
        self._event("funding_assignment.created", "FundingAssignment", record.id, {"assignment_number": code})
        self.db.commit()
        self.db.refresh(record)
        return self._assignment_out(record)

    def update_funding_assignment(self, assignment_id: int, expected_version: int, payload) -> FundingAssignmentOut:
        record = self._assignment(assignment_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status not in {"DRAFT", "RESERVED"}:
            raise HTTPException(status_code=409, detail={"code": "HISTORICAL_FUNDING_ASSIGNMENT_IMMUTABLE"})
        record.amount = payload.amount
        record.period_start = payload.period_start
        record.period_end = payload.period_end
        record.period_profile_json = _jsonable(payload.period_profile)
        record.assignment_purpose = payload.assignment_purpose.strip()
        record.conditions_json = deepcopy(payload.conditions)
        record.evidence_refs_json = deepcopy(payload.evidence_refs)
        self._touch(record)
        record.assignment_hash = self._assignment_hash(record)
        self._event("funding_assignment.updated", "FundingAssignment", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._assignment_out(record)

    def transition_funding_assignment(
        self, assignment_id: int, expected_version: int, action: str, idempotency_key: str
    ) -> FundingAssignmentOut:
        key_field = {
            "reserve": "reserve_idempotency_key",
            "confirm": "confirm_idempotency_key",
            "release": "release_idempotency_key",
            "cancel": "cancel_idempotency_key",
        }[action]
        retry = self.db.scalar(
            select(FundingAssignment).where(
                FundingAssignment.tenant_id == self.tenant_id,
                getattr(FundingAssignment, key_field) == idempotency_key,
            )
        )
        if retry is not None:
            return self._assignment_out(retry)
        record = self._assignment(assignment_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        fund = self._fund(record.fund_id, lock=True)
        policy = self._policy(record.portfolio_workspace_id, require_published=True)
        transitions = {
            "reserve": ({"DRAFT"}, "RESERVED"),
            "confirm": ({"DRAFT", "RESERVED"}, "CONFIRMED"),
            "release": ({"RESERVED", "CONFIRMED"}, "RELEASED"),
            "cancel": ({"DRAFT", "RESERVED"}, "CANCELLED"),
        }
        allowed, target = transitions[action]
        if record.status not in allowed:
            raise HTTPException(status_code=409, detail={"code": "INVALID_FUNDING_ASSIGNMENT_TRANSITION"})
        if action in {"reserve", "confirm"} and fund.status != "ACTIVE":
            raise HTTPException(status_code=409, detail={"code": "ACTIVE_FUND_REQUIRED"})
        if action == "confirm":
            if policy.get("assignment_preparer_cannot_confirm") and record.prepared_by == self.actor_id:
                raise HTTPException(status_code=409, detail={"code": "ASSIGNMENT_CONFIRMATION_FOUR_EYES_REQUIRED"})
            if not policy.get("allow_confirmed_over_allocation", False):
                active_other = self._assigned_amount(fund.id, exclude_assignment_id=record.id)
                if active_other + Decimal(record.amount) > Decimal(fund.authorized_amount):
                    raise HTTPException(status_code=409, detail={"code": "FUND_AVAILABLE_AMOUNT_EXCEEDED"})
            record.confirmed_by = self.actor_id
            record.confirmed_at = utc_now()
        if action == "reserve" and not policy.get("allow_reserved_overbooking", True):
            active_other = self._assigned_amount(fund.id, exclude_assignment_id=record.id)
            if active_other + Decimal(record.amount) > Decimal(fund.authorized_amount):
                raise HTTPException(status_code=409, detail={"code": "FUND_AVAILABLE_AMOUNT_EXCEEDED"})
        record.status = target
        setattr(record, key_field, idempotency_key)
        self._touch(record)
        record.assignment_hash = self._assignment_hash(record)
        event_by_action = {
            "reserve": "funding_assignment.reserved",
            "confirm": "funding_assignment.confirmed",
            "release": "funding_assignment.released",
            "cancel": "funding_assignment.cancelled",
        }
        self._event(event_by_action[action], "FundingAssignment", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._assignment_out(record)

    # Overview, coverage and governed evidence --------------------
    def overview(self, portfolio_id: int | None = None) -> FundingOverviewOut:
        if portfolio_id is not None:
            self._portfolio(portfolio_id)
        readiness: FundingReadinessOut | None = None
        applicable = True
        if portfolio_id is not None:
            applicable = self._capital_owner_applicable(portfolio_id)
            if applicable:
                try:
                    readiness = self.readiness(portfolio_id)
                except HTTPException:
                    readiness = None
        sources = self.funding_sources()
        funds = self.funds()
        assignments = (
            self.funding_assignments(portfolio_id=portfolio_id) if portfolio_id else self.funding_assignments()
        )
        currencies = {item.currency for item in funds if item.status in {"AUTHORIZED", "ACTIVE"}}
        comparable = next(iter(currencies)) if len(currencies) == 1 else None
        active_funds = [item for item in funds if item.status == "ACTIVE"]
        authorized = sum((item.authorized_amount for item in active_funds), Decimal("0")) if comparable else None
        confirmed = (
            sum((item.amount for item in assignments if item.status == "CONFIRMED"), Decimal("0"))
            if comparable
            else None
        )
        reserved = (
            sum((item.amount for item in assignments if item.status == "RESERVED"), Decimal("0"))
            if comparable
            else None
        )
        available = sum((item.available_amount for item in active_funds), Decimal("0")) if comparable else None
        return FundingOverviewOut(
            portfolio_workspace_id=portfolio_id,
            governance_model_applicable=applicable,
            active_funds=len(active_funds),
            comparable_currency=comparable,
            authorized_funding=authorized,
            confirmed_assigned=confirmed,
            reserved_assigned=reserved,
            available_funding=available,
            funding_gap=readiness.funding_gap if readiness else None,
            coverage_percent=readiness.confirmed_coverage_percent if readiness else None,
            funding_readiness=readiness.funding_readiness_status if readiness else "NOT_STARTED",
            funding_sources=sources,
            funds=funds,
            assignments=assignments,
            readiness=readiness,
            boundaries=[
                "BUDGET_IS_NOT_FUNDING",
                "FUNDING_AVAILABLE_IS_NOT_INVESTMENT_APPROVED",
                "NO_TREASURY_ACCOUNTING_COMMITMENTS_OR_PAYMENTS",
                "NO_FID_PROJECT_INITIALIZATION_ACTIVATION_OR_EXECUTION",
            ],
        )

    def readiness(self, portfolio_id: int, project_id: int | None = None) -> FundingReadinessOut:
        derived = self._derive_readiness(portfolio_id, project_id=project_id)
        latest = self._latest_snapshot(portfolio_id, project_id)
        if latest is None:
            return derived
        if latest.source_hash != derived.source_hash:
            warnings = sorted(set(derived.warnings + ["STALE_FUNDING_SOURCE"]))
            blockers = sorted(set(derived.blockers + ["STALE_FUNDING_SOURCE"]))
            return derived.model_copy(
                update={
                    "snapshot_id": latest.id,
                    "warnings": warnings,
                    "blockers": blockers,
                    "funding_readiness_status": "STALE",
                    "source_current": False,
                    "can_supply_investment_gate_evidence": False,
                    "final_output": REWORK_OUTPUT,
                }
            )
        return self._snapshot_out(latest, source_current=True)

    def coverage(self, portfolio_id: int) -> FundingReadinessOut:
        return self.readiness(portfolio_id)

    def project_funding(self, project_id: int) -> FundingOverviewOut:
        project = self._project(project_id)
        portfolio_id = self._portfolio_ancestor(project)
        project_assignments = self.funding_assignments(project_id=project_id)
        if self._governance_model(project) != "CAPITAL_OWNER":
            overview = self.overview(None)
            return overview.model_copy(
                update={
                    "portfolio_workspace_id": portfolio_id,
                    "governance_model_applicable": False,
                    "assignments": project_assignments,
                    "readiness": None,
                    "funding_gap": None,
                    "coverage_percent": None,
                    "funding_readiness": "NOT_APPLICABLE",
                }
            )
        overview = self.overview(portfolio_id)
        if not overview.governance_model_applicable:
            return overview.model_copy(update={"assignments": project_assignments})
        project_readiness = self.readiness(portfolio_id, project_id=project_id)
        return overview.model_copy(
            update={
                "assignments": project_assignments,
                "readiness": project_readiness,
                "funding_gap": project_readiness.funding_gap,
                "coverage_percent": project_readiness.confirmed_coverage_percent,
                "funding_readiness": project_readiness.funding_readiness_status,
            }
        )

    def refresh_preview(self, portfolio_id: int) -> FundingRefreshPreviewOut:
        proposed = self._derive_readiness(portfolio_id)
        latest = self._latest_snapshot(portfolio_id, None)
        old_snapshot = dict(latest.source_snapshot_json or {}) if latest else {}
        new_snapshot = self._source_snapshot_payload(portfolio_id, proposed)
        fund_changes = _diff_records(old_snapshot.get("funds", []), new_snapshot.get("funds", []), "id", "hash")
        assignment_changes = _diff_records(
            old_snapshot.get("assignments", []), new_snapshot.get("assignments", []), "id", "hash"
        )
        requirement_changes = []
        old_requirement = dict(old_snapshot.get("requirement", {}))
        new_requirement = dict(new_snapshot.get("requirement", {}))
        if old_requirement != new_requirement:
            requirement_changes.append({"before": old_requirement or None, "after": new_requirement})
        coverage_before = (
            {
                "confirmed": str(latest.confirmed_funding_amount),
                "reserved": str(latest.reserved_funding_amount),
                "gap": str(latest.funding_gap),
            }
            if latest
            else {}
        )
        coverage_after = {
            "confirmed": str(proposed.confirmed_funding_amount),
            "reserved": str(proposed.reserved_funding_amount),
            "gap": str(proposed.funding_gap),
        }
        self._event(
            "funding_readiness.refresh_previewed",
            "EnterpriseWorkspace",
            portfolio_id,
            {"persisted": False, "proposed_source_hash": proposed.source_hash},
        )
        return FundingRefreshPreviewOut(
            portfolio_workspace_id=portfolio_id,
            current_source_hash=latest.source_hash if latest else None,
            proposed_source_hash=proposed.source_hash,
            source_current=bool(latest and latest.source_hash == proposed.source_hash),
            fund_changes=fund_changes,
            assignment_changes=assignment_changes,
            requirement_changes=requirement_changes,
            coverage_changes={"before": coverage_before, "after": coverage_after},
            project_set_changes=_list_delta(
                old_requirement.get("selected_project_ids", []), new_requirement.get("selected_project_ids", [])
            ),
            period_gaps=[item for item in proposed.period_coverage_summary if Decimal(str(item.get("gap", 0))) > 0],
            restriction_changes=[]
            if latest and latest.restriction_summary_json == proposed.restriction_summary
            else [
                {
                    "before": dict(latest.restriction_summary_json or {}) if latest else {},
                    "after": proposed.restriction_summary,
                }
            ],
            condition_changes=[]
            if latest and latest.conditions_summary_json == proposed.conditions_summary
            else [
                {
                    "before": dict(latest.conditions_summary_json or {}) if latest else {},
                    "after": proposed.conditions_summary,
                }
            ],
            expiry_changes=[warning for warning in proposed.warnings if "EXPIR" in warning],
            warnings=proposed.warnings,
            blockers=proposed.blockers,
            persisted=False,
        )

    def refresh(
        self,
        portfolio_id: int,
        expected_source_hash: str,
        idempotency_key: str,
    ) -> FundingReadinessOut:
        retry = self.db.scalar(
            select(FundingReadinessSnapshot).where(
                FundingReadinessSnapshot.tenant_id == self.tenant_id,
                FundingReadinessSnapshot.refresh_idempotency_key == idempotency_key,
            )
        )
        if retry is not None:
            return self._snapshot_out(retry, source_current=True)
        derived = self._derive_readiness(portfolio_id)
        if derived.source_hash != expected_source_hash:
            raise HTTPException(
                status_code=412,
                detail={
                    "code": "STALE_FUNDING_SOURCE",
                    "expected_source_hash": expected_source_hash,
                    "current_source_hash": derived.source_hash,
                },
            )
        snapshot_payload = self._source_snapshot_payload(portfolio_id, derived)
        record = FundingReadinessSnapshot(
            tenant_id=self.tenant_id,
            scope_type=derived.scope_type,
            portfolio_workspace_id=derived.portfolio_workspace_id,
            project_workspace_id=derived.project_workspace_id,
            source_convergence_id=derived.source_convergence_id,
            source_recommendation_hash=derived.source_recommendation_hash,
            recommended_project_set_hash=derived.recommended_project_set_hash,
            budget_scenario_id=derived.budget_scenario_id,
            budget_scenario_hash=derived.budget_scenario_hash,
            funding_requirement_source=deepcopy(derived.funding_requirement_source),
            funding_requirement_hash=derived.funding_requirement_hash,
            required_amount=derived.required_amount,
            required_currency=derived.required_currency,
            confirmed_funding_amount=derived.confirmed_funding_amount,
            reserved_funding_amount=derived.reserved_funding_amount,
            funding_gap=derived.funding_gap,
            confirmed_coverage_percent=derived.confirmed_coverage_percent,
            potential_coverage_percent=derived.potential_coverage_percent,
            project_coverage_summary_json=deepcopy(derived.project_coverage_summary),
            period_coverage_summary_json=deepcopy(derived.period_coverage_summary),
            restriction_summary_json=deepcopy(derived.restriction_summary),
            conditions_summary_json=deepcopy(derived.conditions_summary),
            source_snapshot_json=snapshot_payload,
            source_hash=derived.source_hash,
            configuration_hash=str(snapshot_payload["configuration_hash"]),
            warnings_json=deepcopy(derived.warnings),
            blockers_json=deepcopy(derived.blockers),
            status=derived.funding_readiness_status,
            funding_readiness_hash=derived.funding_readiness_hash,
            source_current=True,
            can_supply_investment_gate_evidence=derived.can_supply_investment_gate_evidence,
            refresh_idempotency_key=idempotency_key,
            revision_version=1,
            generated_by=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        self._event(
            "funding_readiness.refreshed",
            "FundingReadinessSnapshot",
            record.id,
            {"status": record.status, "funding_readiness_hash": record.funding_readiness_hash},
        )
        self.db.commit()
        self.db.refresh(record)
        return self._snapshot_out(record, source_current=True)

    def investment_gate_evidence(self, portfolio_id: int) -> InvestmentGateFundingEvidenceOut:
        readiness = self.readiness(portfolio_id)
        restriction_status = str(readiness.restriction_summary.get("status") or "ELIGIBLE")
        open_blocking = int(readiness.conditions_summary.get("open_blocking", 0))
        return InvestmentGateFundingEvidenceOut(
            scope_type=readiness.scope_type,
            portfolio_workspace_id=readiness.portfolio_workspace_id,
            project_workspace_id=readiness.project_workspace_id,
            source_recommendation_hash=readiness.source_recommendation_hash,
            recommended_project_set_hash=readiness.recommended_project_set_hash,
            funding_requirement_source=readiness.funding_requirement_source,
            funding_requirement_hash=readiness.funding_requirement_hash,
            required_amount=readiness.required_amount,
            required_currency=readiness.required_currency,
            confirmed_funding_amount=readiness.confirmed_funding_amount,
            reserved_funding_amount=readiness.reserved_funding_amount,
            confirmed_coverage_percent=readiness.confirmed_coverage_percent,
            potential_coverage_percent=readiness.potential_coverage_percent,
            project_coverage=readiness.project_coverage_summary,
            period_coverage=readiness.period_coverage_summary,
            restriction_status=restriction_status,
            open_blocking_conditions=open_blocking,
            funding_readiness_status=readiness.funding_readiness_status,
            funding_readiness_hash=readiness.funding_readiness_hash,
            source_current=readiness.source_current,
            can_supply_investment_gate_evidence=readiness.can_supply_investment_gate_evidence,
            snapshot_id=readiness.snapshot_id,
        )

    # AdminConfiguration reuse ------------------------------------
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
        fund_assumptions: list[dict] | None = None,
    ) -> ConfigurationPreviewOut:
        workspace = self._portfolio(portfolio_id) if portfolio_id else None
        record = self._configuration(configuration_id) if configuration_id else None
        effective = deepcopy(
            content_override
            if content_override is not None
            else record.content_json
            if record
            else DEFAULT_CONFIGURATION
        )
        issues = self._configuration_issues(effective)
        requirement = None
        eligible_funds: list[dict] = []
        eligible_assignments: list[dict] = []
        currency = {"status": "NOT_EVALUATED"}
        confirmed: Decimal | None = None
        potential: Decimal | None = None
        project_coverage: list[dict] = []
        period_coverage: list[dict] = []
        restrictions: dict = {}
        conditions: dict = {}
        warnings: list[str] = []
        blockers: list[str] = []
        evidence_preview = None
        if portfolio_id and not issues:
            try:
                derived = self._derive_readiness(portfolio_id, policy_override=effective)
                requirement = derived.funding_requirement_source | {
                    "required_amount": str(derived.required_amount),
                    "required_currency": derived.required_currency,
                    "hash": derived.funding_requirement_hash,
                }
                eligible_funds = [
                    {
                        "id": item.id,
                        "code": item.fund_code,
                        "currency": item.currency,
                        "available": str(item.available_amount),
                    }
                    for item in self.funds()
                    if item.status == "ACTIVE"
                ] + list(fund_assumptions or [])
                eligible_assignments = [
                    {"id": item.id, "number": item.assignment_number, "status": item.status, "amount": str(item.amount)}
                    for item in self.funding_assignments(portfolio_id=portfolio_id)
                    if item.status in {"RESERVED", "CONFIRMED"}
                ]
                currency = {
                    "status": "COMPARABLE" if "CURRENCY_NOT_COMPARABLE" not in derived.blockers else "NOT_COMPARABLE",
                    "required_currency": derived.required_currency,
                }
                confirmed = derived.confirmed_coverage_percent
                potential = derived.potential_coverage_percent
                project_coverage = derived.project_coverage_summary
                period_coverage = derived.period_coverage_summary
                restrictions = derived.restriction_summary
                conditions = derived.conditions_summary
                warnings = derived.warnings
                blockers = derived.blockers
                evidence_preview = self._evidence_preview(derived)
            except HTTPException as exc:
                blockers.append(_detail_code(exc, "FUNDING_REQUIREMENT_UNAVAILABLE"))
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
            funding_requirement=requirement,
            eligible_active_funds=eligible_funds,
            eligible_assignments=eligible_assignments,
            currency_compatibility=currency,
            confirmed_coverage_preview=confirmed,
            potential_coverage_preview=potential,
            project_coverage=project_coverage,
            period_coverage=period_coverage,
            restrictions=restrictions,
            conditions=conditions,
            warnings=sorted(set(warnings)),
            blockers=sorted(set(blockers)),
            gate07j_funding_evidence_preview=evidence_preview,
            validation_issues=issues,
            publishable=not issues,
            persisted=False,
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id, lock=True)
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
        self._event("funds.configuration_cloned", "AdminConfiguration", clone.id, {})
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
        record.updated_at = utc_now()
        self._event("funds.configuration_updated", "AdminConfiguration", record.id, {})
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
        record.published_at = utc_now()
        record.version += 1
        record.content_hash = _hash(record.content_json)
        self._event("funds.configuration_published", "AdminConfiguration", record.id, {})
        self.db.commit()
        return record

    # Readiness engine --------------------------------------------
    def _derive_readiness(
        self,
        portfolio_id: int,
        *,
        project_id: int | None = None,
        policy_override: dict | None = None,
    ) -> FundingReadinessOut:
        self._portfolio(portfolio_id)
        if not self._capital_owner_applicable(portfolio_id):
            raise HTTPException(status_code=409, detail={"code": "CAPITAL_OWNER_FUNDING_NOT_REQUIRED"})
        policy = (
            deepcopy(policy_override)
            if policy_override is not None
            else self._policy(portfolio_id, require_published=True)
        )
        requirement = self._funding_requirement(portfolio_id, project_id=project_id)
        required = Decimal(str(requirement["required_amount"]))
        required_currency = str(requirement["required_currency"]).upper()
        selected_project_ids = list(requirement.get("selected_project_ids", []))
        records = self._coverage_assignment_records(portfolio_id, project_id=project_id)
        confirmed = Decimal("0")
        reserved = Decimal("0")
        warnings: list[str] = []
        blockers: list[str] = []
        ineligible = 0
        conditional = 0
        expired = 0
        open_conditions = 0
        open_blocking = 0
        contributions: list[dict] = []
        project_confirmed: dict[int, Decimal] = {}
        project_reserved: dict[int, Decimal] = {}
        period_confirmed: dict[str, Decimal] = {}
        period_reserved: dict[str, Decimal] = {}
        today = date.today()

        for assignment in records:
            fund = self._fund(assignment.fund_id)
            source = self._source(fund.funding_source_id) if fund.funding_source_id else None
            assignment_warnings: list[str] = []
            is_expired = bool(
                (fund.available_to and fund.available_to < today)
                or (assignment.period_end and assignment.period_end < today)
                or (source and source.effective_to and source.effective_to < today)
            )
            if is_expired:
                expired += 1
                assignment_warnings.append("FUNDING_ASSIGNMENT_EXPIRED")
                warnings.append("EXPIRED_FUNDING_NOT_COUNTED")
                continue
            if fund.status != "ACTIVE" or (source and source.status != "ACTIVE"):
                assignment_warnings.append("FUND_OR_SOURCE_NOT_ACTIVE")
                warnings.append("INACTIVE_FUNDING_NOT_COUNTED")
                continue
            eligibility, reasons = self._eligibility(
                assignment,
                fund,
                source,
                portfolio_id,
                selected_project_ids,
            )
            if eligibility == "INELIGIBLE":
                ineligible += 1
                warnings.extend(reasons or ["INELIGIBLE_FUNDING_ASSIGNMENT"])
                continue
            conditions = list(assignment.conditions_json or [])
            open_items = [
                item for item in conditions if str(item.get("status") or "OPEN").upper() not in {"SATISFIED", "WAIVED"}
            ]
            blocking_items = [item for item in open_items if bool(item.get("blocking", True))]
            open_conditions += len(open_items)
            open_blocking += len(blocking_items)
            if blocking_items and policy.get("open_condition_is_blocker", True):
                blockers.append("OPEN_BLOCKING_FUNDING_CONDITION")
                continue
            if eligibility == "CONDITIONALLY_ELIGIBLE" or open_items:
                conditional += 1
                if not policy.get("conditional_funds_count_toward_readiness", False):
                    warnings.append("CONDITIONAL_FUNDING_NOT_COUNTED")
                    continue
            comparable = self._comparable_amount(assignment, required_currency)
            if comparable is None:
                warnings.append("CURRENCY_NOT_COMPARABLE")
                blockers.append("CURRENCY_NOT_COMPARABLE")
                continue
            # Child assignments explain distribution. Their parent already
            # contributes the governed amount to aggregate coverage.
            aggregate_contribution = Decimal("0") if assignment.parent_assignment_id else comparable
            if assignment.status == "CONFIRMED":
                confirmed += aggregate_contribution
            elif assignment.status == "RESERVED":
                reserved += aggregate_contribution
            else:
                continue
            if assignment.project_workspace_id:
                target = project_confirmed if assignment.status == "CONFIRMED" else project_reserved
                target[assignment.project_workspace_id] = (
                    target.get(assignment.project_workspace_id, Decimal("0")) + comparable
                )
            for item in self._assignment_period_profile(assignment, comparable):
                target = period_confirmed if assignment.status == "CONFIRMED" else period_reserved
                key = str(item["period_key"])
                target[key] = target.get(key, Decimal("0")) + Decimal(str(item["amount"]))
            contributions.append(
                {
                    "assignment_id": assignment.id,
                    "assignment_number": assignment.assignment_number,
                    "status": assignment.status,
                    "amount": str(comparable),
                    "aggregate_contribution": str(aggregate_contribution),
                    "eligibility": eligibility,
                    "warnings": assignment_warnings,
                    "parent_assignment_id": assignment.parent_assignment_id,
                }
            )

        confirmed_coverage = _percent(confirmed, required)
        potential = confirmed + reserved
        potential_coverage = _percent(potential, required)
        readiness_basis = potential if policy.get("reserved_counts_toward_readiness", False) else confirmed
        gap = max(Decimal("0"), required - readiness_basis)
        if confirmed_coverage < Decimal(str(policy.get("minimum_confirmed_coverage_percent", 100))):
            blockers.append("INSUFFICIENT_CONFIRMED_FUNDING")
        if potential_coverage < Decimal(str(policy.get("minimum_potential_coverage_percent", 100))):
            blockers.append("INSUFFICIENT_POTENTIAL_FUNDING")

        project_summary = self._project_coverage(
            requirement,
            project_confirmed,
            project_reserved,
        )
        if policy.get("require_each_project_coverage"):
            threshold = Decimal(str(policy.get("minimum_project_coverage_percent", 100)))
            if any(Decimal(str(item["coverage_percent"])) < threshold for item in project_summary):
                blockers.append("INSUFFICIENT_PROJECT_FUNDING_COVERAGE")

        period_summary = self._period_coverage(
            requirement,
            period_confirmed,
            period_reserved,
        )
        if policy.get("require_period_coverage"):
            threshold = Decimal(str(policy.get("minimum_period_coverage_percent", 100)))
            if not period_summary or any(Decimal(str(item["coverage_percent"])) < threshold for item in period_summary):
                blockers.append("INSUFFICIENT_PERIOD_FUNDING_COVERAGE")

        restriction_summary = {
            "status": "INELIGIBLE"
            if ineligible and not contributions
            else "CONDITIONALLY_ELIGIBLE"
            if conditional
            else "ELIGIBLE",
            "ineligible_assignments": ineligible,
            "conditional_assignments": conditional,
            "eligible_contributions": len(contributions),
        }
        conditions_summary = {
            "open": open_conditions,
            "open_blocking": open_blocking,
            "status": "BLOCKED" if open_blocking and policy.get("open_condition_is_blocker", True) else "CONTROLLED",
        }
        if expired and gap > 0:
            status = "EXPIRED"
            blockers.append("REQUIRED_FUNDING_EXPIRED")
        elif blockers:
            status = "BLOCKED"
        else:
            status = "READY"

        source_snapshot = {
            "requirement": requirement,
            "configuration_hash": _hash(policy),
            "funds": [{"id": item.id, "hash": item.fund_hash, "status": item.status} for item in self._fund_records()],
            "sources": [
                {"id": item.id, "hash": item.source_hash, "status": item.status} for item in self._source_records()
            ],
            "assignments": [{"id": item.id, "hash": item.assignment_hash, "status": item.status} for item in records],
            "contributions": contributions,
        }
        source_hash = _hash(source_snapshot)
        readiness_hash = _hash(
            {
                "source_hash": source_hash,
                "requirement_hash": requirement["funding_requirement_hash"],
                "confirmed": confirmed,
                "reserved": reserved,
                "gap": gap,
                "project_coverage": project_summary,
                "period_coverage": period_summary,
                "restrictions": restriction_summary,
                "conditions": conditions_summary,
                "status": status,
            }
        )
        can_supply = status == "READY"
        return FundingReadinessOut(
            tenant_id=self.tenant_id,
            scope_type="PROJECT" if project_id else "PORTFOLIO",
            portfolio_workspace_id=portfolio_id,
            project_workspace_id=project_id,
            source_convergence_id=requirement.get("source_convergence_id"),
            source_recommendation_hash=requirement.get("source_recommendation_hash"),
            recommended_project_set_hash=requirement.get("recommended_project_set_hash"),
            budget_scenario_id=requirement.get("budget_scenario_id"),
            budget_scenario_hash=requirement.get("budget_scenario_hash"),
            funding_requirement_source=deepcopy(requirement["source"]),
            funding_requirement_hash=requirement["funding_requirement_hash"],
            required_amount=required,
            required_currency=required_currency,
            confirmed_funding_amount=confirmed,
            reserved_funding_amount=reserved,
            funding_gap=gap,
            confirmed_coverage_percent=confirmed_coverage,
            potential_coverage_percent=potential_coverage,
            project_coverage_summary=project_summary,
            period_coverage_summary=period_summary,
            restriction_summary=restriction_summary,
            conditions_summary=conditions_summary,
            warnings=sorted(set(warnings)),
            blockers=sorted(set(blockers)),
            funding_readiness_status=status,
            funding_readiness_hash=readiness_hash,
            source_hash=source_hash,
            source_current=True,
            can_supply_investment_gate_evidence=can_supply,
            allowed_actions=[
                "can_view_funds",
                "can_view_funding_readiness",
                "can_refresh_funding_readiness",
                *(["can_supply_investment_gate_evidence"] if can_supply else []),
            ],
            final_output=READY_OUTPUT if can_supply else REWORK_OUTPUT,
        )

    def _funding_requirement(self, portfolio_id: int, *, project_id: int | None = None) -> dict:
        contract = self._requirement_contract(portfolio_id)
        budget_ref = contract.get("budget_scenario_ref")
        if not budget_ref:
            raise HTTPException(status_code=409, detail={"code": "GOVERNED_BUDGET_REQUIREMENT_REQUIRED"})
        scenario_id = int(budget_ref["id"])
        PortfolioBudgetService(self.db, self.tenant_id, self.actor_id, self.context).scenario(scenario_id)
        selected_ids = list(contract.get("selected_project_set_reference", []))
        rows = list(
            self.db.scalars(
                select(PortfolioBudgetScenarioProject).where(
                    PortfolioBudgetScenarioProject.tenant_id == self.tenant_id,
                    PortfolioBudgetScenarioProject.scenario_id == scenario_id,
                    PortfolioBudgetScenarioProject.project_workspace_id.in_(selected_ids or [-1]),
                )
            ).all()
        )
        if project_id is not None:
            rows = [item for item in rows if item.project_workspace_id == project_id]
            selected_ids = [project_id]
        currencies = {str(item.currency).upper() for item in rows}
        if len(currencies) != 1:
            raise HTTPException(status_code=409, detail={"code": "FUNDING_REQUIREMENT_CURRENCY_NOT_COMPARABLE"})
        required_amount = sum((Decimal(item.cost_value) for item in rows), Decimal("0"))
        if project_id is None:
            summary_amount = Decimal(
                str(contract.get("budget_feasibility_summary", {}).get("selected_demand", required_amount))
            )
            if summary_amount >= 0:
                required_amount = summary_amount
        period_profile: dict[str, Decimal] = {}
        project_requirements: list[dict] = []
        for item in rows:
            project_requirements.append(
                {
                    "project_workspace_id": item.project_workspace_id,
                    "project_number": item.project_number,
                    "project_name": item.project_name,
                    "required_amount": str(Decimal(item.cost_value)),
                    "currency": item.currency,
                }
            )
            for period in list(item.period_profile_json or []):
                key = str(period.get("period_key") or period.get("period") or "TOTAL")
                period_profile[key] = period_profile.get(key, Decimal("0")) + Decimal(str(period.get("amount", 0)))
        source = {
            "type": "GATE07I_RECOMMENDED_ALTERNATIVE",
            "id": contract["recommended_alternative_id"],
            "hash": contract["recommendation_hash"],
            "budget_scenario_id": scenario_id,
            "budget_scenario_hash": budget_ref.get("hash"),
        }
        requirement_hash = _hash(
            {
                "source": source,
                "required_amount": required_amount,
                "required_currency": next(iter(currencies)),
                "selected_project_ids": selected_ids,
                "project_requirements": project_requirements,
                "period_profile": period_profile,
            }
        )
        return {
            "source": source,
            "source_convergence_id": contract["convergence_id"],
            "source_recommendation_hash": contract["recommendation_hash"],
            "recommended_project_set_hash": contract["selected_project_set_hash"],
            "budget_scenario_id": scenario_id,
            "budget_scenario_hash": budget_ref.get("hash"),
            "required_amount": required_amount,
            "required_currency": next(iter(currencies)),
            "selected_project_ids": selected_ids,
            "project_requirements": project_requirements,
            "period_profile": [
                {"period_key": key, "required_amount": str(value)} for key, value in sorted(period_profile.items())
            ],
            "funding_requirement_hash": requirement_hash,
        }

    def _project_coverage(
        self,
        requirement: dict,
        confirmed: dict[int, Decimal],
        reserved: dict[int, Decimal],
    ) -> list[dict]:
        rows: list[dict] = []
        for item in requirement.get("project_requirements", []):
            project_id = int(item["project_workspace_id"])
            required = Decimal(str(item["required_amount"]))
            confirmed_amount = confirmed.get(project_id, Decimal("0"))
            reserved_amount = reserved.get(project_id, Decimal("0"))
            rows.append(
                {
                    **item,
                    "confirmed_funding": str(confirmed_amount),
                    "reserved_funding": str(reserved_amount),
                    "gap": str(max(Decimal("0"), required - confirmed_amount)),
                    "coverage_percent": str(_percent(confirmed_amount, required)),
                    "status": "COVERED" if confirmed_amount >= required else "GAP",
                }
            )
        return rows

    def _period_coverage(
        self,
        requirement: dict,
        confirmed: dict[str, Decimal],
        reserved: dict[str, Decimal],
    ) -> list[dict]:
        rows: list[dict] = []
        for item in requirement.get("period_profile", []):
            key = str(item["period_key"])
            required = Decimal(str(item["required_amount"]))
            confirmed_amount = confirmed.get(key, Decimal("0"))
            reserved_amount = reserved.get(key, Decimal("0"))
            rows.append(
                {
                    "period_key": key,
                    "required_amount": str(required),
                    "confirmed_funding": str(confirmed_amount),
                    "reserved_funding": str(reserved_amount),
                    "gap": str(max(Decimal("0"), required - confirmed_amount)),
                    "coverage_percent": str(_percent(confirmed_amount, required)),
                }
            )
        return rows

    def _coverage_assignment_records(
        self, portfolio_id: int, *, project_id: int | None = None
    ) -> list[FundingAssignment]:
        statement = select(FundingAssignment).where(
            FundingAssignment.tenant_id == self.tenant_id,
            FundingAssignment.status.in_(["RESERVED", "CONFIRMED"]),
        )
        records = list(self.db.scalars(statement.order_by(FundingAssignment.id)).all())
        contract = self._requirement_contract(portfolio_id)
        selected = set(contract.get("selected_project_set_reference", []))
        result: list[FundingAssignment] = []
        for item in records:
            if item.scope_type == "PORTFOLIO" and item.portfolio_workspace_id == portfolio_id and project_id is None:
                result.append(item)
            elif item.scope_type == "RECOMMENDED_PROJECT_SET" and item.portfolio_workspace_id == portfolio_id:
                if item.recommended_project_set_hash == contract.get(
                    "selected_project_set_hash"
                ) and item.source_recommendation_hash == contract.get("recommendation_hash"):
                    result.append(item)
            elif item.scope_type == "PROJECT" and item.project_workspace_id in selected:
                if project_id is None or item.project_workspace_id == project_id:
                    result.append(item)
        return result

    def _eligibility(
        self,
        assignment: FundingAssignment,
        fund: Fund,
        source: StrategicFundingSource | None,
        portfolio_id: int,
        selected_project_ids: list[int],
    ) -> tuple[str, list[str]]:
        reasons: list[str] = []
        scope = dict(fund.applicable_workspace_scope_json or {})
        portfolio_ids = {int(item) for item in scope.get("portfolio_ids", [])}
        project_ids = {int(item) for item in scope.get("project_ids", [])}
        if portfolio_ids and portfolio_id not in portfolio_ids:
            reasons.append("FUND_PORTFOLIO_SCOPE_INELIGIBLE")
        if assignment.project_workspace_id and project_ids and assignment.project_workspace_id not in project_ids:
            reasons.append("FUND_PROJECT_SCOPE_INELIGIBLE")
        restrictions = _merge_restrictions(source.restrictions_json if source else {}, fund.restrictions_json)
        restricted_portfolios = {int(item) for item in restrictions.get("portfolio_ids", [])}
        if restricted_portfolios and portfolio_id not in restricted_portfolios:
            reasons.append("PORTFOLIO_RESTRICTION_MISMATCH")
        target_ids = [assignment.project_workspace_id] if assignment.project_workspace_id else selected_project_ids
        projects = list(
            self.db.scalars(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id.in_(target_ids or [-1]),
                    EnterpriseWorkspace.workspace_type_code == "project",
                )
            ).all()
        )
        allowed_types = {str(item).upper() for item in restrictions.get("project_types", [])}
        if allowed_types and any(self._project_type(item) not in allowed_types for item in projects):
            reasons.append("PROJECT_TYPE_RESTRICTION_MISMATCH")
        allowed_geographies = {str(item).upper() for item in restrictions.get("geographies", [])}
        if allowed_geographies and any(self._project_geography(item) not in allowed_geographies for item in projects):
            reasons.append("GEOGRAPHY_RESTRICTION_MISMATCH")
        maximum = restrictions.get("maximum_amount")
        if maximum is not None and Decimal(assignment.amount) > Decimal(str(maximum)):
            reasons.append("FUNDING_MAXIMUM_AMOUNT_EXCEEDED")
        conditional = bool(restrictions.get("conditional")) or any(
            str(item.get("status") or "OPEN").upper() not in {"SATISFIED", "WAIVED"}
            for item in list(assignment.conditions_json or [])
        )
        if reasons:
            return "INELIGIBLE", reasons
        if conditional:
            return "CONDITIONALLY_ELIGIBLE", ["CONDITIONAL_FUNDING"]
        return "ELIGIBLE", []

    @staticmethod
    def _comparable_amount(assignment: FundingAssignment, required_currency: str) -> Decimal | None:
        if assignment.currency.upper() == required_currency.upper():
            return Decimal(assignment.amount)
        if (
            assignment.normalized_amount is not None
            and str(assignment.normalized_currency or "").upper() == required_currency.upper()
            and assignment.fx_source_reference
            and assignment.fx_as_of_date
            and assignment.fx_hash
        ):
            return Decimal(assignment.normalized_amount)
        return None

    @staticmethod
    def _assignment_period_profile(assignment: FundingAssignment, amount: Decimal) -> list[dict]:
        profile = list(assignment.period_profile_json or [])
        if profile:
            return profile
        if assignment.period_start:
            return [{"period_key": str(assignment.period_start.year), "amount": str(amount)}]
        return []

    # Output mappers ----------------------------------------------
    def _source_out(self, record: StrategicFundingSource) -> FundingSourceOut:
        actions = ["can_view_funds"]
        if record.status in {"DRAFT", "ACTIVE", "SUSPENDED"}:
            actions.append("can_edit_funding_source")
        if record.status in {"DRAFT", "SUSPENDED"}:
            actions.append("can_activate_funding_source")
        if record.status == "ACTIVE":
            actions.append("can_suspend_funding_source")
        if record.status in {"ACTIVE", "SUSPENDED"}:
            actions.append("can_close_funding_source")
        return FundingSourceOut(
            id=record.id,
            tenant_id=record.tenant_id,
            source_code=record.source_code,
            source_name=record.source_name,
            source_type=record.source_type,
            description=record.description,
            legal_entity_provider_reference=record.legal_entity_provider_reference,
            currency=record.currency,
            status=record.status,
            effective_from=record.effective_from,
            effective_to=record.effective_to,
            restrictions=deepcopy(record.restrictions_json or {}),
            evidence_refs=deepcopy(record.evidence_refs_json or []),
            source_reference=record.source_reference,
            source_hash=record.source_hash,
            revision_version=record.revision_version,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_by=record.updated_by,
            updated_at=record.updated_at,
            allowed_actions=actions,
        )

    def _fund_out(self, record: Fund) -> FundOut:
        assigned = self._assigned_amount(record.id)
        confirmed = self._assigned_amount(record.id, statuses={"CONFIRMED"})
        reserved = self._assigned_amount(record.id, statuses={"RESERVED"})
        available = max(Decimal("0"), Decimal(record.authorized_amount) - assigned)
        source = self._source(record.funding_source_id) if record.funding_source_id else None
        period_authorized = list(record.authorized_amount_by_period_json or [])
        assigned_by_period = self._fund_period_assignments(record.id)
        available_by_period = []
        for item in period_authorized:
            key = str(item.get("period_key") or item.get("period") or "TOTAL")
            authorized_amount = Decimal(str(item.get("amount", 0)))
            assigned_amount = assigned_by_period.get(key, Decimal("0"))
            available_by_period.append(
                {"period_key": key, "amount": str(max(Decimal("0"), authorized_amount - assigned_amount))}
            )
        actions = ["can_view_funds"]
        if record.status == "DRAFT":
            actions.extend(["can_edit_fund", "can_authorize_fund"])
        if record.status in {"AUTHORIZED", "SUSPENDED"}:
            actions.append("can_activate_fund")
        if record.status == "ACTIVE":
            actions.append("can_suspend_fund")
        if record.status in {"AUTHORIZED", "ACTIVE", "SUSPENDED", "EXHAUSTED"}:
            actions.append("can_close_fund")
        return FundOut(
            id=record.id,
            tenant_id=record.tenant_id,
            fund_code=record.fund_code,
            fund_name=record.fund_name,
            funding_source_id=record.funding_source_id,
            funding_source_name=source.source_name if source else None,
            description=record.description,
            currency=record.currency,
            authorized_amount=Decimal(record.authorized_amount),
            assigned_amount=assigned,
            confirmed_assigned_amount=confirmed,
            reserved_assigned_amount=reserved,
            available_amount=available,
            available_from=record.available_from,
            available_to=record.available_to,
            period_granularity=record.period_granularity,
            authorized_amount_by_period=period_authorized,
            assigned_amount_by_period=[
                {"period_key": key, "amount": str(value)} for key, value in sorted(assigned_by_period.items())
            ],
            available_amount_by_period=available_by_period,
            status=record.status,
            restrictions=deepcopy(record.restrictions_json or {}),
            applicable_workspace_scope=deepcopy(record.applicable_workspace_scope_json or {}),
            evidence_refs=deepcopy(record.evidence_refs_json or []),
            source_reference=record.source_reference,
            fund_hash=record.fund_hash,
            revision_version=record.revision_version,
            authorized_by=record.authorized_by,
            authorized_at=record.authorized_at,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_by=record.updated_by,
            updated_at=record.updated_at,
            allowed_actions=actions,
        )

    def _assignment_out(self, record: FundingAssignment) -> FundingAssignmentOut:
        fund = self._fund(record.fund_id)
        warnings: list[str] = []
        if record.parent_assignment_id:
            warnings.append("SUB_ALLOCATION_NOT_DOUBLE_COUNTED")
        if (
            record.period_end
            and record.period_end < date.today()
            and record.status not in {"RELEASED", "CANCELLED", "EXPIRED"}
        ):
            warnings.append("ASSIGNMENT_EXPIRED")
        actions = ["can_view_funds"]
        if record.status in {"DRAFT", "RESERVED"}:
            actions.append("can_edit_funding_assignment")
        if record.status == "DRAFT":
            actions.extend(["can_reserve_funding", "can_confirm_funding", "can_cancel_funding_assignment"])
        if record.status == "RESERVED":
            actions.extend(["can_confirm_funding", "can_release_funding", "can_cancel_funding_assignment"])
        if record.status == "CONFIRMED":
            actions.append("can_release_funding")
        return FundingAssignmentOut(
            id=record.id,
            tenant_id=record.tenant_id,
            fund_id=record.fund_id,
            fund_code=fund.fund_code,
            parent_assignment_id=record.parent_assignment_id,
            assignment_number=record.assignment_number,
            scope_type=record.scope_type,
            portfolio_workspace_id=record.portfolio_workspace_id,
            project_workspace_id=record.project_workspace_id,
            recommended_project_set_hash=record.recommended_project_set_hash,
            source_convergence_id=record.source_convergence_id,
            source_recommendation_hash=record.source_recommendation_hash,
            amount=Decimal(record.amount),
            currency=record.currency,
            normalized_amount=Decimal(record.normalized_amount) if record.normalized_amount is not None else None,
            normalized_currency=record.normalized_currency,
            fx_source_reference=record.fx_source_reference,
            fx_as_of_date=record.fx_as_of_date,
            fx_hash=record.fx_hash,
            period_start=record.period_start,
            period_end=record.period_end,
            period_profile=deepcopy(record.period_profile_json or []),
            status=record.status,
            assignment_purpose=record.assignment_purpose,
            eligibility_status=record.eligibility_status,
            conditions=deepcopy(record.conditions_json or []),
            evidence_refs=deepcopy(record.evidence_refs_json or []),
            assignment_hash=record.assignment_hash,
            coverage_contribution=Decimal("0") if record.parent_assignment_id else Decimal(record.amount),
            warnings=warnings,
            revision_version=record.revision_version,
            prepared_by=record.prepared_by,
            confirmed_by=record.confirmed_by,
            confirmed_at=record.confirmed_at,
            created_at=record.created_at,
            updated_by=record.updated_by,
            updated_at=record.updated_at,
            allowed_actions=actions,
        )

    def _snapshot_out(self, record: FundingReadinessSnapshot, *, source_current: bool) -> FundingReadinessOut:
        status = record.status if source_current else "STALE"
        blockers = list(record.blockers_json or [])
        warnings = list(record.warnings_json or [])
        if not source_current:
            blockers.append("STALE_FUNDING_SOURCE")
            warnings.append("STALE_FUNDING_SOURCE")
        can_supply = bool(record.can_supply_investment_gate_evidence and source_current and status == "READY")
        return FundingReadinessOut(
            snapshot_id=record.id,
            tenant_id=record.tenant_id,
            scope_type=record.scope_type,
            portfolio_workspace_id=record.portfolio_workspace_id,
            project_workspace_id=record.project_workspace_id,
            source_convergence_id=record.source_convergence_id,
            source_recommendation_hash=record.source_recommendation_hash,
            recommended_project_set_hash=record.recommended_project_set_hash,
            budget_scenario_id=record.budget_scenario_id,
            budget_scenario_hash=record.budget_scenario_hash,
            funding_requirement_source=deepcopy(record.funding_requirement_source or {}),
            funding_requirement_hash=record.funding_requirement_hash,
            required_amount=Decimal(record.required_amount),
            required_currency=record.required_currency,
            confirmed_funding_amount=Decimal(record.confirmed_funding_amount),
            reserved_funding_amount=Decimal(record.reserved_funding_amount),
            funding_gap=Decimal(record.funding_gap),
            confirmed_coverage_percent=Decimal(record.confirmed_coverage_percent),
            potential_coverage_percent=Decimal(record.potential_coverage_percent),
            project_coverage_summary=deepcopy(record.project_coverage_summary_json or []),
            period_coverage_summary=deepcopy(record.period_coverage_summary_json or []),
            restriction_summary=deepcopy(record.restriction_summary_json or {}),
            conditions_summary=deepcopy(record.conditions_summary_json or {}),
            warnings=sorted(set(warnings)),
            blockers=sorted(set(blockers)),
            funding_readiness_status=status,
            funding_readiness_hash=record.funding_readiness_hash,
            source_hash=record.source_hash,
            source_current=source_current,
            can_supply_investment_gate_evidence=can_supply,
            allowed_actions=[
                "can_view_funds",
                "can_view_funding_readiness",
                "can_refresh_funding_readiness",
                *(["can_supply_investment_gate_evidence"] if can_supply else []),
            ],
            final_output=READY_OUTPUT if can_supply else REWORK_OUTPUT,
        )

    def _evidence_preview(self, readiness: FundingReadinessOut) -> dict:
        return {
            "source_module": "FUNDS_MANAGER",
            "evidence_type": "FUNDING_READINESS",
            "funding_readiness_status": readiness.funding_readiness_status,
            "funding_readiness_hash": readiness.funding_readiness_hash,
            "source_current": readiness.source_current,
            "can_supply_investment_gate_evidence": readiness.can_supply_investment_gate_evidence,
            "persisted": False,
        }

    def _source_snapshot_payload(self, portfolio_id: int, readiness: FundingReadinessOut) -> dict:
        return _jsonable(
            {
                "portfolio_workspace_id": portfolio_id,
                "configuration_hash": self._current_configuration_hash(portfolio_id),
                "requirement": self._funding_requirement(portfolio_id),
                "sources": [
                    {"id": item.id, "hash": item.source_hash, "status": item.status} for item in self._source_records()
                ],
                "funds": [
                    {"id": item.id, "hash": item.fund_hash, "status": item.status} for item in self._fund_records()
                ],
                "assignments": [
                    {"id": item.id, "hash": item.assignment_hash, "status": item.status}
                    for item in self._coverage_assignment_records(portfolio_id)
                ],
                "readiness_hash": readiness.funding_readiness_hash,
            }
        )

    # Configuration inheritance ----------------------------------
    def _configuration_issues(self, content: dict) -> list[str]:
        issues: list[str] = []
        if list(content.get("applicable_governance_models", [])) != ["CAPITAL_OWNER"]:
            issues.append("CAPITAL_OWNER_ONLY_REQUIRED")
        if not set(content.get("allowed_source_types", [])) <= SOURCE_TYPES:
            issues.append("INVALID_FUNDING_SOURCE_TYPES")
        if not set(content.get("allowed_assignment_scopes", [])) <= {"PORTFOLIO", "PROJECT", "RECOMMENDED_PROJECT_SET"}:
            issues.append("INVALID_FUNDING_ASSIGNMENT_SCOPES")
        for key in (
            "minimum_confirmed_coverage_percent",
            "minimum_potential_coverage_percent",
            "minimum_project_coverage_percent",
            "minimum_period_coverage_percent",
        ):
            value = content.get(key)
            if not isinstance(value, (int, float)) or value < 0 or value > 100:
                issues.append(f"INVALID_{key.upper()}")
        currency = dict(content.get("currency_policy", {}))
        if currency.get("fx_engine") is not False:
            issues.append("FX_ENGINE_NOT_ALLOWED")
        serialized = json.dumps(content, sort_keys=True).lower()
        forbidden = {
            "approve_investment",
            "execute_fid",
            "go_hold_recycle_kill",
            "bank_account",
            "general_ledger",
            "payment_execution",
            "project_activation",
            "project_initialization",
            "accounting_engine",
            "treasury_engine",
        }
        if any(item in serialized for item in forbidden):
            issues.append("DOWNSTREAM_FINANCIAL_OR_FID_CAPABILITY_NOT_ALLOWED")
        return sorted(set(issues))

    def _validate_configuration(self, content: dict) -> None:
        issues = self._configuration_issues(content)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION", "issues": issues})

    def _policy(self, portfolio_id: int | None, *, require_published: bool) -> dict:
        workspace = self._portfolio(portfolio_id) if portfolio_id else None
        record = self._effective_configuration(workspace, published_only=True)
        if record is None:
            if require_published:
                raise HTTPException(status_code=409, detail={"code": "PUBLISHED_FUNDS_CONFIGURATION_REQUIRED"})
            return deepcopy(DEFAULT_CONFIGURATION)
        content = deepcopy(record.content_json or {})
        self._validate_configuration(content)
        return content

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
            raise HTTPException(status_code=404, detail="Funds Manager configuration not found")
        return record

    def _current_configuration_hash(self, portfolio_id: int) -> str:
        record = self._effective_configuration(self._portfolio(portfolio_id), published_only=True)
        if record is None:
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_FUNDS_CONFIGURATION_REQUIRED"})
        return record.content_hash

    # Persistence/workspace helpers -------------------------------
    def _source(self, source_id: int | None, *, lock: bool = False) -> StrategicFundingSource:
        statement = select(StrategicFundingSource).where(
            StrategicFundingSource.id == source_id,
            StrategicFundingSource.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Funding Source not found")
        return record

    def _source_records(self) -> list[StrategicFundingSource]:
        return list(
            self.db.scalars(
                select(StrategicFundingSource)
                .where(StrategicFundingSource.tenant_id == self.tenant_id)
                .order_by(StrategicFundingSource.id)
            ).all()
        )

    def _fund(self, fund_id: int | None, *, lock: bool = False) -> Fund:
        statement = select(Fund).where(Fund.id == fund_id, Fund.tenant_id == self.tenant_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Fund not found")
        return record

    def _fund_records(self) -> list[Fund]:
        return list(self.db.scalars(select(Fund).where(Fund.tenant_id == self.tenant_id).order_by(Fund.id)).all())

    def _assignment(self, assignment_id: int | None, *, lock: bool = False) -> FundingAssignment:
        statement = select(FundingAssignment).where(
            FundingAssignment.id == assignment_id,
            FundingAssignment.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Funding Assignment not found")
        return record

    def _latest_snapshot(self, portfolio_id: int, project_id: int | None) -> FundingReadinessSnapshot | None:
        statement = select(FundingReadinessSnapshot).where(
            FundingReadinessSnapshot.tenant_id == self.tenant_id,
            FundingReadinessSnapshot.portfolio_workspace_id == portfolio_id,
        )
        if project_id is None:
            statement = statement.where(FundingReadinessSnapshot.project_workspace_id.is_(None))
        else:
            statement = statement.where(FundingReadinessSnapshot.project_workspace_id == project_id)
        return self.db.scalar(
            statement.order_by(FundingReadinessSnapshot.generated_at.desc(), FundingReadinessSnapshot.id.desc())
        )

    def _portfolio(self, portfolio_id: int | None) -> EnterpriseWorkspace:
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == portfolio_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
            )
        )
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        if workspace.workspace_type_code != "portfolio":
            raise HTTPException(status_code=422, detail={"code": "WORKSPACE_IS_NOT_PORTFOLIO"})
        self._assert_scope(workspace.id)
        return workspace

    def _project(self, project_id: int | None) -> EnterpriseWorkspace:
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == project_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
            )
        )
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        if workspace.workspace_type_code != "project":
            raise HTTPException(status_code=422, detail={"code": "WORKSPACE_IS_NOT_PROJECT"})
        self._assert_scope(workspace.id)
        return workspace

    def _portfolio_ancestor(self, project: EnterpriseWorkspace) -> int:
        membership = self.db.scalar(
            select(PortfolioProjectMembership)
            .where(
                PortfolioProjectMembership.tenant_id == self.tenant_id,
                PortfolioProjectMembership.project_workspace_id == project.id,
                PortfolioProjectMembership.status == "ACTIVE",
            )
            .order_by(
                PortfolioProjectMembership.is_target_portfolio.desc(),
                PortfolioProjectMembership.id,
            )
        )
        if membership is not None:
            return membership.portfolio_workspace_id
        for item in reversed(self._workspace_path(project)):
            if item.workspace_type_code == "portfolio":
                return item.id
        raise HTTPException(status_code=409, detail={"code": "PROJECT_PORTFOLIO_REQUIRED"})

    def _capital_owner_applicable(self, portfolio_id: int) -> bool:
        projects = list(
            self.db.scalars(
                select(EnterpriseWorkspace)
                .join(
                    PortfolioProjectMembership,
                    PortfolioProjectMembership.project_workspace_id == EnterpriseWorkspace.id,
                )
                .where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.workspace_type_code == "project",
                    PortfolioProjectMembership.tenant_id == self.tenant_id,
                    PortfolioProjectMembership.portfolio_workspace_id == portfolio_id,
                    PortfolioProjectMembership.status == "ACTIVE",
                )
            ).all()
        )
        return not projects or any(self._governance_model(item) == "CAPITAL_OWNER" for item in projects)

    @staticmethod
    def _governance_model(project: EnterpriseWorkspace) -> str:
        context = dict(dict(project.defaults_json or {}).get("_project", {}))
        value = str(context.get("governance_model") or "").upper()
        if not value and context.get("planning_origin") == "STRATEGIC_GATE":
            return "CAPITAL_OWNER"
        return value or "LEGACY"

    @staticmethod
    def _project_type(project: EnterpriseWorkspace) -> str:
        context = dict(dict(project.defaults_json or {}).get("_project", {}))
        return str(context.get("project_type_code") or context.get("project_type") or "UNCLASSIFIED").upper()

    @staticmethod
    def _project_geography(project: EnterpriseWorkspace) -> str:
        context = dict(dict(project.defaults_json or {}).get("_project", {}))
        return str(context.get("country") or context.get("region") or "UNCLASSIFIED").upper()

    def _requirement_contract(self, portfolio_id: int | None) -> dict:
        if portfolio_id is None:
            raise HTTPException(status_code=422, detail={"code": "PORTFOLIO_REQUIRED"})
        contract = PortfolioConvergenceService(
            self.db, self.tenant_id, self.actor_id, self.context
        ).preparation_contract(portfolio_id)
        return contract.model_dump(mode="json")

    def _validate_assignment_targets(self, payload: FundingAssignmentCreateIn) -> None:
        if payload.portfolio_workspace_id:
            self._portfolio(payload.portfolio_workspace_id)
        if payload.project_workspace_id:
            project = self._project(payload.project_workspace_id)
            if payload.portfolio_workspace_id and self._portfolio_ancestor(project) != payload.portfolio_workspace_id:
                raise HTTPException(status_code=422, detail={"code": "PROJECT_OUTSIDE_ASSIGNMENT_PORTFOLIO"})

    def _source_has_assignments(self, source_id: int) -> bool:
        fund_ids = select(Fund.id).where(Fund.tenant_id == self.tenant_id, Fund.funding_source_id == source_id)
        return bool(
            self.db.scalar(
                select(func.count(FundingAssignment.id)).where(
                    FundingAssignment.tenant_id == self.tenant_id,
                    FundingAssignment.fund_id.in_(fund_ids),
                )
            )
        )

    def _assigned_amount(
        self,
        fund_id: int,
        *,
        statuses: set[str] | None = None,
        exclude_assignment_id: int | None = None,
    ) -> Decimal:
        statuses = statuses or {"RESERVED", "CONFIRMED"}
        statement = select(func.coalesce(func.sum(FundingAssignment.amount), 0)).where(
            FundingAssignment.tenant_id == self.tenant_id,
            FundingAssignment.fund_id == fund_id,
            FundingAssignment.status.in_(statuses),
            FundingAssignment.parent_assignment_id.is_(None),
        )
        if exclude_assignment_id:
            statement = statement.where(FundingAssignment.id != exclude_assignment_id)
        return Decimal(self.db.scalar(statement) or 0)

    def _fund_period_assignments(self, fund_id: int) -> dict[str, Decimal]:
        records = list(
            self.db.scalars(
                select(FundingAssignment).where(
                    FundingAssignment.tenant_id == self.tenant_id,
                    FundingAssignment.fund_id == fund_id,
                    FundingAssignment.status.in_(["RESERVED", "CONFIRMED"]),
                    FundingAssignment.parent_assignment_id.is_(None),
                )
            ).all()
        )
        result: dict[str, Decimal] = {}
        for record in records:
            for item in self._assignment_period_profile(record, Decimal(record.amount)):
                key = str(item.get("period_key") or item.get("period") or "TOTAL")
                result[key] = result.get(key, Decimal("0")) + Decimal(str(item.get("amount", 0)))
        return result

    def _next_number(self, rule_code: str, prefix_key: str, fallback_prefix: str) -> str:
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
        configuration = self._effective_configuration(None, published_only=True)
        prefix = str(
            ((configuration.content_json if configuration else DEFAULT_CONFIGURATION).get("numbering", {})).get(
                prefix_key, fallback_prefix
            )
        ).upper()
        return f"{prefix}-{value:05d}"

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
        }

    def _assert_scope(self, workspace_id: int) -> None:
        if self.context is None or self.context.organization_wide:
            return
        if workspace_id not in self.context.workspace_ids:
            raise HTTPException(status_code=403, detail="Workspace is outside the authorized scope")

    @staticmethod
    def _check_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise HTTPException(
                status_code=412,
                detail={"code": "ETAG_MISMATCH", "current": actual, "provided": expected},
            )

    def _touch(self, record) -> None:
        record.updated_by = self.actor_id
        record.updated_at = utc_now()
        record.revision_version += 1

    def _event(self, event_type: str, target_type: str, target_id: int | None, metadata: dict) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type=target_type,
                target_id=target_id,
                metadata_json=_jsonable(metadata),
            )
        )

    @staticmethod
    def _source_hash(record: StrategicFundingSource) -> str:
        return _hash(
            {
                "id": record.id,
                "code": record.source_code,
                "name": record.source_name,
                "type": record.source_type,
                "currency": record.currency,
                "status": record.status,
                "effective": [record.effective_from, record.effective_to],
                "restrictions": record.restrictions_json,
                "evidence": record.evidence_refs_json,
                "reference": record.source_reference,
                "revision": record.revision_version,
            }
        )

    @staticmethod
    def _fund_hash(record: Fund, source: StrategicFundingSource | None) -> str:
        return _hash(
            {
                "id": record.id,
                "code": record.fund_code,
                "source_hash": source.source_hash if source else None,
                "currency": record.currency,
                "authorized": record.authorized_amount,
                "periods": record.authorized_amount_by_period_json,
                "status": record.status,
                "dates": [record.available_from, record.available_to],
                "restrictions": record.restrictions_json,
                "scope": record.applicable_workspace_scope_json,
                "evidence": record.evidence_refs_json,
                "revision": record.revision_version,
            }
        )

    @staticmethod
    def _assignment_hash(record: FundingAssignment) -> str:
        return _hash(
            {
                "id": record.id,
                "fund_id": record.fund_id,
                "parent_id": record.parent_assignment_id,
                "number": record.assignment_number,
                "scope": [
                    record.scope_type,
                    record.portfolio_workspace_id,
                    record.project_workspace_id,
                    record.recommended_project_set_hash,
                ],
                "source": [record.source_convergence_id, record.source_recommendation_hash],
                "amount": record.amount,
                "currency": record.currency,
                "normalized": [
                    record.normalized_amount,
                    record.normalized_currency,
                    record.fx_source_reference,
                    record.fx_as_of_date,
                    record.fx_hash,
                ],
                "period": [record.period_start, record.period_end, record.period_profile_json],
                "status": record.status,
                "conditions": record.conditions_json,
                "evidence": record.evidence_refs_json,
                "revision": record.revision_version,
            }
        )


def _hash(value: Any) -> str:
    payload = json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date,)):
        return value.isoformat()
    return value


def _percent(amount: Decimal, required: Decimal) -> Decimal:
    if required <= 0:
        return Decimal("100.0000")
    return ((amount / required) * Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _clean(value: str | None) -> str | None:
    normalized = value.strip() if value else ""
    return normalized or None


def _merge_restrictions(*items: dict) -> dict:
    merged: dict = {}
    for item in items:
        for key, value in dict(item or {}).items():
            if key in merged and isinstance(merged[key], list) and isinstance(value, list):
                merged[key] = sorted(set(merged[key]) & set(value))
            else:
                merged[key] = deepcopy(value)
    return merged


def _detail_code(exc: HTTPException, fallback: str) -> str:
    if isinstance(exc.detail, dict):
        return str(exc.detail.get("code") or fallback)
    return fallback


def _diff_records(before: list[dict], after: list[dict], id_key: str, hash_key: str) -> list[dict]:
    old = {item.get(id_key): item for item in before}
    new = {item.get(id_key): item for item in after}
    changes: list[dict] = []
    for identity in sorted(set(old) | set(new), key=lambda value: str(value)):
        if identity not in old:
            changes.append({"id": identity, "change": "ADDED", "after": new[identity]})
        elif identity not in new:
            changes.append({"id": identity, "change": "REMOVED", "before": old[identity]})
        elif old[identity].get(hash_key) != new[identity].get(hash_key):
            changes.append({"id": identity, "change": "CHANGED", "before": old[identity], "after": new[identity]})
    return changes


def _list_delta(before: list, after: list) -> list[dict]:
    before_set = set(before)
    after_set = set(after)
    return [
        *[{"change": "ADDED", "value": item} for item in sorted(after_set - before_set)],
        *[{"change": "REMOVED", "value": item} for item in sorted(before_set - after_set)],
    ]
