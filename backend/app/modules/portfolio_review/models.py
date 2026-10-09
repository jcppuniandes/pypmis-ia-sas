"""Persistence for Wave 3A Periodic Portfolio Review.

The aggregate freezes compact, attributable read models from existing source
authorities.  It deliberately does not own Portfolio rank, Budget or Resource
scenarios, Gate decisions, FID, or Strategic Capital Allocation.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class PortfolioReviewSession(Base):
    """One formal governance review for one governed Portfolio."""

    __tablename__ = "portfolio_review_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    review_number: Mapped[str] = mapped_column(String(40), index=True)
    portfolio_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    scope_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    planning_cycle_id: Mapped[int | None] = mapped_column(ForeignKey("capital_planning_cycles.id"), index=True)
    allocation_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategic_capital_allocation_plans.id"), index=True
    )
    review_type: Mapped[str] = mapped_column(String(80), index=True)
    review_date: Mapped[date] = mapped_column(Date, index=True)
    review_period_start: Mapped[date | None] = mapped_column(Date)
    review_period_end: Mapped[date | None] = mapped_column(Date)
    actual_review_date: Mapped[date | None] = mapped_column(Date, index=True)
    next_planned_review_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    chair_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    secretary_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    agenda_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64), index=True)
    configuration_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    current_snapshot_id: Mapped[int | None] = mapped_column(Integer, index=True)
    current_snapshot_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    snapshot_frozen_at: Mapped[datetime | None] = mapped_column(DateTime)
    snapshot_frozen_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    completion_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    completion_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    create_idempotency_key: Mapped[str] = mapped_column(String(160))
    create_request_hash: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    last_modified_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    prepared_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    review_authority_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    prepared_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "review_number", name="uq_portfolio_review_number"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_portfolio_review_create_key"),
        CheckConstraint(
            "status IN ('DRAFT','PREPARING','READY_FOR_REVIEW','IN_REVIEW','STALE','RETURNED',"
            "'COMPLETED','CANCELLED','SUPERSEDED')",
            name="ck_portfolio_review_status",
        ),
        CheckConstraint(
            "review_period_end IS NULL OR review_period_start IS NULL OR review_period_end >= review_period_start",
            name="ck_portfolio_review_period",
        ),
        CheckConstraint(
            "status != 'COMPLETED' OR (completed_at IS NOT NULL AND completion_hash IS NOT NULL "
            "AND current_snapshot_hash IS NOT NULL)",
            name="ck_portfolio_review_completed",
        ),
        Index(
            "ix_portfolio_review_queue",
            "tenant_id",
            "portfolio_workspace_id",
            "status",
            "review_date",
            "id",
        ),
        Index(
            "ix_portfolio_review_history",
            "tenant_id",
            "portfolio_workspace_id",
            "completed_at",
            "id",
        ),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class PortfolioReviewSnapshot(Base):
    """Append-only evidence snapshot; the Session points to the current one."""

    __tablename__ = "portfolio_review_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    review_session_id: Mapped[int] = mapped_column(ForeignKey("portfolio_review_sessions.id"), index=True)
    snapshot_version: Mapped[int] = mapped_column(Integer)
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_index_json: Mapped[dict] = mapped_column(JSON, default=dict)
    readiness_json: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    blockers_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    freeze_idempotency_key: Mapped[str] = mapped_column(String(160))
    freeze_request_hash: Mapped[str] = mapped_column(String(64))
    frozen_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    frozen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "review_session_id", "snapshot_version", name="uq_portfolio_review_snapshot_version"
        ),
        UniqueConstraint("tenant_id", "freeze_idempotency_key", name="uq_portfolio_review_snapshot_freeze_key"),
        Index("ix_portfolio_review_snapshot_hash", "review_session_id", "snapshot_hash"),
    )


class PortfolioReviewConclusion(Base):
    __tablename__ = "portfolio_review_conclusions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    review_session_id: Mapped[int] = mapped_column(ForeignKey("portfolio_review_sessions.id"), index=True)
    conclusion_type: Mapped[str] = mapped_column(String(120), index=True)
    rationale: Mapped[str] = mapped_column(Text)
    conditions_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "review_session_id", "conclusion_type", name="uq_portfolio_review_conclusion_type"
        ),
        Index("ix_portfolio_review_conclusion_session", "review_session_id", "conclusion_type"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class PortfolioReviewAction(Base):
    """Governance instruction/request; never a hidden source-domain mutation."""

    __tablename__ = "portfolio_review_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    action_number: Mapped[str] = mapped_column(String(48), index=True)
    review_session_id: Mapped[int] = mapped_column(ForeignKey("portfolio_review_sessions.id"), index=True)
    subject_type: Mapped[str] = mapped_column(String(40), index=True)
    subject_id: Mapped[int | None] = mapped_column(Integer, index=True)
    subject_key: Mapped[str | None] = mapped_column(String(120))
    action_type: Mapped[str] = mapped_column(String(120), index=True)
    rationale: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(24), default="MEDIUM", index=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(24), default="OPEN", index=True)
    source_evidence_references_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    requested_source_authority: Mapped[str | None] = mapped_column(String(120), index=True)
    dispatch_status: Mapped[str] = mapped_column(String(32), default="NOT_REQUESTED", index=True)
    execution_reference: Mapped[str | None] = mapped_column(String(300))
    create_idempotency_key: Mapped[str] = mapped_column(String(160))
    create_request_hash: Mapped[str] = mapped_column(String(64))
    approve_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    approve_request_hash: Mapped[str | None] = mapped_column(String(64))
    dispatch_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    dispatch_request_hash: Mapped[str | None] = mapped_column(String(64))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    last_modified_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "action_number", name="uq_portfolio_review_action_number"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_portfolio_review_action_create_key"),
        UniqueConstraint("tenant_id", "approve_idempotency_key", name="uq_portfolio_review_action_approve_key"),
        UniqueConstraint("tenant_id", "dispatch_idempotency_key", name="uq_portfolio_review_action_dispatch_key"),
        CheckConstraint(
            "status IN ('OPEN','ACCEPTED','IN_PROGRESS','COMPLETED','REJECTED','CANCELLED')",
            name="ck_portfolio_review_action_status",
        ),
        CheckConstraint(
            "priority IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_portfolio_review_action_priority",
        ),
        CheckConstraint(
            "dispatch_status IN ('NOT_REQUESTED','REQUEST_RECORDED','EXECUTED_BY_GOVERNED_ADAPTER','FAILED')",
            name="ck_portfolio_review_action_dispatch_status",
        ),
        Index("ix_portfolio_review_action_queue", "tenant_id", "status", "due_date", "owner_user_id", "id"),
        Index("ix_portfolio_review_action_subject", "tenant_id", "subject_type", "subject_id", "status"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class PortfolioReviewCommand(Base):
    """Durable tenant-wide idempotency ledger for Wave 3A commands."""

    __tablename__ = "portfolio_review_commands"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    review_session_id: Mapped[int | None] = mapped_column(ForeignKey("portfolio_review_sessions.id"), index=True)
    review_action_id: Mapped[int | None] = mapped_column(ForeignKey("portfolio_review_actions.id"), index=True)
    command_type: Mapped[str] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    request_hash: Mapped[str] = mapped_column(String(64))
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_portfolio_review_command_key"),
        Index("ix_portfolio_review_command_scope", "tenant_id", "review_session_id", "command_type", "occurred_at"),
    )


@event.listens_for(PortfolioReviewSession, "before_update")
def _protect_terminal_review(_mapper, _connection, record: PortfolioReviewSession) -> None:
    state = inspect(record)
    previous = state.attrs.status.history.deleted[0] if state.attrs.status.history.deleted else record.status
    if previous in {"COMPLETED", "CANCELLED", "SUPERSEDED"} and any(
        attribute.history.has_changes() for attribute in state.attrs
    ):
        raise ValueError("Completed, cancelled and superseded Portfolio Reviews are immutable")


@event.listens_for(PortfolioReviewSession, "before_delete")
def _protect_review_delete(_mapper, _connection, _record: PortfolioReviewSession) -> None:
    raise ValueError("Portfolio Review Sessions cannot be physically deleted")


def _protect_snapshot(_mapper, _connection, _record: PortfolioReviewSnapshot) -> None:
    raise ValueError("Frozen Portfolio Review snapshots are immutable")


event.listen(PortfolioReviewSnapshot, "before_update", _protect_snapshot)
event.listen(PortfolioReviewSnapshot, "before_delete", _protect_snapshot)


def _protect_completed_conclusion(_mapper, connection, record: PortfolioReviewConclusion) -> None:
    status = connection.execute(
        PortfolioReviewSession.__table__.select()
        .with_only_columns(PortfolioReviewSession.status)
        .where(PortfolioReviewSession.id == record.review_session_id)
    ).scalar_one_or_none()
    if status in {"COMPLETED", "CANCELLED", "SUPERSEDED"}:
        raise ValueError("Conclusions of a terminal Portfolio Review are immutable")


event.listen(PortfolioReviewConclusion, "before_update", _protect_completed_conclusion)
event.listen(PortfolioReviewConclusion, "before_delete", _protect_completed_conclusion)
