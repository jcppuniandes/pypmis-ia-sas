"""Tenant-scoped strategic funding records for Gate 07J-FUND.

The legacy ``funding_sources`` table is the Project/FBS cost-control catalog.
Strategic capital funding deliberately uses ``strategic_funding_sources`` so
the two bounded contexts cannot be confused or joined implicitly.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class StrategicFundingSource(Base):
    __tablename__ = "strategic_funding_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    source_code: Mapped[str] = mapped_column(String(80), index=True)
    source_name: Mapped[str] = mapped_column(String(180))
    source_type: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    legal_entity_provider_reference: Mapped[str | None] = mapped_column(String(300))
    currency: Mapped[str] = mapped_column(String(8), index=True)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    restrictions_json: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_refs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    source_reference: Mapped[str | None] = mapped_column(String(300))
    source_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    activate_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    suspend_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    close_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "source_code", name="uq_strategic_funding_source_code"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_strategic_funding_source_create_key"),
        UniqueConstraint("tenant_id", "activate_idempotency_key", name="uq_strategic_funding_source_activate_key"),
        UniqueConstraint("tenant_id", "suspend_idempotency_key", name="uq_strategic_funding_source_suspend_key"),
        UniqueConstraint("tenant_id", "close_idempotency_key", name="uq_strategic_funding_source_close_key"),
        CheckConstraint(
            "status IN ('DRAFT','ACTIVE','SUSPENDED','CLOSED','ARCHIVED')",
            name="ck_strategic_funding_source_status",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_strategic_funding_source_dates",
        ),
        Index("ix_strategic_funding_source_tenant_status", "tenant_id", "status"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class Fund(Base):
    __tablename__ = "funds"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    fund_code: Mapped[str] = mapped_column(String(80), index=True)
    fund_name: Mapped[str] = mapped_column(String(180))
    funding_source_id: Mapped[int | None] = mapped_column(ForeignKey("strategic_funding_sources.id"), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    currency: Mapped[str] = mapped_column(String(8), index=True)
    authorized_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    available_from: Mapped[date | None] = mapped_column(Date)
    available_to: Mapped[date | None] = mapped_column(Date)
    period_granularity: Mapped[str] = mapped_column(String(16), default="TOTAL")
    authorized_amount_by_period_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    restrictions_json: Mapped[dict] = mapped_column(JSON, default=dict)
    applicable_workspace_scope_json: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_refs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    source_reference: Mapped[str | None] = mapped_column(String(300))
    fund_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    authorize_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    activate_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    suspend_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    close_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    authorized_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "fund_code", name="uq_fund_code"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_fund_create_key"),
        UniqueConstraint("tenant_id", "authorize_idempotency_key", name="uq_fund_authorize_key"),
        UniqueConstraint("tenant_id", "activate_idempotency_key", name="uq_fund_activate_key"),
        UniqueConstraint("tenant_id", "suspend_idempotency_key", name="uq_fund_suspend_key"),
        UniqueConstraint("tenant_id", "close_idempotency_key", name="uq_fund_close_key"),
        CheckConstraint("authorized_amount >= 0", name="ck_fund_authorized_non_negative"),
        CheckConstraint(
            "status IN ('DRAFT','AUTHORIZED','ACTIVE','SUSPENDED','EXHAUSTED','CLOSED','SUPERSEDED')",
            name="ck_fund_status",
        ),
        CheckConstraint(
            "period_granularity IN ('TOTAL','YEAR','QUARTER','MONTH')",
            name="ck_fund_period_granularity",
        ),
        CheckConstraint(
            "available_to IS NULL OR available_from IS NULL OR available_to >= available_from",
            name="ck_fund_dates",
        ),
        Index("ix_fund_tenant_status_currency", "tenant_id", "status", "currency"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class FundingAssignment(Base):
    __tablename__ = "funding_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    fund_id: Mapped[int] = mapped_column(ForeignKey("funds.id"), index=True)
    parent_assignment_id: Mapped[int | None] = mapped_column(ForeignKey("funding_assignments.id"), index=True)
    assignment_number: Mapped[str] = mapped_column(String(80), index=True)
    scope_type: Mapped[str] = mapped_column(String(32), index=True)
    portfolio_workspace_id: Mapped[int | None] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    project_workspace_id: Mapped[int | None] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    recommended_project_set_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    source_convergence_id: Mapped[int | None] = mapped_column(
        ForeignKey("portfolio_scenario_convergences.id"), index=True
    )
    source_recommendation_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    currency: Mapped[str] = mapped_column(String(8), index=True)
    normalized_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    normalized_currency: Mapped[str | None] = mapped_column(String(8))
    fx_source_reference: Mapped[str | None] = mapped_column(String(300))
    fx_as_of_date: Mapped[date | None] = mapped_column(Date)
    fx_hash: Mapped[str | None] = mapped_column(String(64))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    period_profile_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    assignment_purpose: Mapped[str] = mapped_column(Text, default="")
    eligibility_status: Mapped[str] = mapped_column(String(32), default="ELIGIBLE", index=True)
    conditions_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    evidence_refs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    assignment_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    reserve_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    confirm_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    release_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    cancel_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    prepared_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "assignment_number", name="uq_funding_assignment_number"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_funding_assignment_create_key"),
        UniqueConstraint("tenant_id", "reserve_idempotency_key", name="uq_funding_assignment_reserve_key"),
        UniqueConstraint("tenant_id", "confirm_idempotency_key", name="uq_funding_assignment_confirm_key"),
        UniqueConstraint("tenant_id", "release_idempotency_key", name="uq_funding_assignment_release_key"),
        UniqueConstraint("tenant_id", "cancel_idempotency_key", name="uq_funding_assignment_cancel_key"),
        CheckConstraint("amount > 0", name="ck_funding_assignment_positive_amount"),
        CheckConstraint(
            "status IN ('DRAFT','RESERVED','CONFIRMED','RELEASED','CANCELLED','EXPIRED')",
            name="ck_funding_assignment_status",
        ),
        CheckConstraint(
            "scope_type IN ('PORTFOLIO','PROJECT','RECOMMENDED_PROJECT_SET')",
            name="ck_funding_assignment_scope",
        ),
        CheckConstraint(
            "eligibility_status IN ('ELIGIBLE','CONDITIONALLY_ELIGIBLE','INELIGIBLE')",
            name="ck_funding_assignment_eligibility",
        ),
        CheckConstraint(
            "period_end IS NULL OR period_start IS NULL OR period_end >= period_start",
            name="ck_funding_assignment_dates",
        ),
        Index("ix_funding_assignment_scope_lookup", "tenant_id", "scope_type", "portfolio_workspace_id"),
        Index("ix_funding_assignment_fund_status", "tenant_id", "fund_id", "status"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class FundingReadinessSnapshot(Base):
    __tablename__ = "funding_readiness_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    scope_type: Mapped[str] = mapped_column(String(32), index=True)
    portfolio_workspace_id: Mapped[int | None] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    project_workspace_id: Mapped[int | None] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    source_convergence_id: Mapped[int | None] = mapped_column(
        ForeignKey("portfolio_scenario_convergences.id"), index=True
    )
    source_recommendation_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    recommended_project_set_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    budget_scenario_id: Mapped[int | None] = mapped_column(ForeignKey("portfolio_budget_scenarios.id"), index=True)
    budget_scenario_hash: Mapped[str | None] = mapped_column(String(64))
    funding_requirement_source: Mapped[dict] = mapped_column(JSON, default=dict)
    funding_requirement_hash: Mapped[str] = mapped_column(String(64), index=True)
    required_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    required_currency: Mapped[str] = mapped_column(String(8))
    confirmed_funding_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    reserved_funding_amount: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    funding_gap: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    confirmed_coverage_percent: Mapped[Decimal] = mapped_column(Numeric(9, 4))
    potential_coverage_percent: Mapped[Decimal] = mapped_column(Numeric(9, 4))
    project_coverage_summary_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    period_coverage_summary_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    restriction_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    conditions_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    configuration_hash: Mapped[str] = mapped_column(String(64), index=True)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    blockers_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), index=True)
    funding_readiness_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_current: Mapped[bool] = mapped_column(Boolean, default=True)
    can_supply_investment_gate_evidence: Mapped[bool] = mapped_column(Boolean, default=False)
    refresh_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    generated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_funding_readiness_refresh_key"),
        CheckConstraint(
            "scope_type IN ('PORTFOLIO','PROJECT')",
            name="ck_funding_readiness_scope",
        ),
        CheckConstraint(
            "status IN ('NOT_STARTED','READY','BLOCKED','STALE','EXPIRED')",
            name="ck_funding_readiness_status",
        ),
        CheckConstraint("required_amount >= 0", name="ck_funding_readiness_required_non_negative"),
        Index(
            "ix_funding_readiness_latest",
            "tenant_id",
            "portfolio_workspace_id",
            "project_workspace_id",
            "generated_at",
        ),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


@event.listens_for(StrategicFundingSource, "before_delete")
def _protect_funding_source_delete(_mapper, _connection, record: StrategicFundingSource) -> None:
    if record.status != "DRAFT":
        raise ValueError("Used or historical Funding Sources cannot be physically deleted")


@event.listens_for(Fund, "before_delete")
def _protect_fund_delete(_mapper, _connection, record: Fund) -> None:
    if record.status != "DRAFT":
        raise ValueError("Authorized or historical Funds cannot be physically deleted")


@event.listens_for(FundingReadinessSnapshot, "before_update")
def _protect_readiness_snapshot_update(_mapper, _connection, record: FundingReadinessSnapshot) -> None:
    if any(attribute.history.has_changes() for attribute in inspect(record).attrs):
        raise ValueError("Funding Readiness snapshots are immutable")


@event.listens_for(FundingReadinessSnapshot, "before_delete")
def _protect_readiness_snapshot_delete(_mapper, _connection, _record: FundingReadinessSnapshot) -> None:
    raise ValueError("Funding Readiness snapshots cannot be physically deleted")
