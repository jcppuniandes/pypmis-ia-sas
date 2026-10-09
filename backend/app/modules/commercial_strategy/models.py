"""Persistence for governed Commercial & Contracting Strategy records.

The aggregate deliberately stores strategic commercial sections as a single
versioned JSON document.  Packages are commercial concepts, not procurement,
contract, vendor, commitment, or payment transactions.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
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


class CommercialContractingStrategy(Base):
    """Stable commercial-strategy identity; the Project Workspace is canonical."""

    __tablename__ = "commercial_contracting_strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    strategy_number: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    current_version_id: Mapped[int | None] = mapped_column(Integer, index=True)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64), index=True)
    configuration_source_workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("enterprise_workspaces.id"), index=True
    )
    configuration_resolution_chain_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    create_idempotency_key: Mapped[str] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", name="uq_commercial_strategy_project"),
        UniqueConstraint("tenant_id", "strategy_number", name="uq_commercial_strategy_number"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_commercial_strategy_create_key"),
        CheckConstraint(
            "status IN ('DRAFT','IN_REVIEW','COMPLETED','SUPERSEDED','VOIDED')",
            name="ck_commercial_strategy_status",
        ),
        Index("ix_commercial_strategy_queue", "tenant_id", "status", "updated_at", "id"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class CommercialStrategyVersion(Base):
    """Controlled mutable draft and immutable terminal commercial version."""

    __tablename__ = "commercial_strategy_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    commercial_strategy_id: Mapped[int] = mapped_column(ForeignKey("commercial_contracting_strategies.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    version_purpose: Mapped[str] = mapped_column(String(48), index=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    fel_stage_code: Mapped[str | None] = mapped_column(String(32), index=True)
    content_json: Mapped[dict] = mapped_column(JSON, default=dict)
    readiness_json: Mapped[dict] = mapped_column(JSON, default=dict)
    readiness_status: Mapped[str] = mapped_column(String(24), default="NOT_STARTED", index=True)
    readiness_warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    readiness_blockers_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_references_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_hashes_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_bundle_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    commercial_strategy_hash: Mapped[str] = mapped_column(String(64), index=True)
    preparer_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    reviewer_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    return_reason: Mapped[str | None] = mapped_column(Text)
    void_reason: Mapped[str | None] = mapped_column(Text)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    submit_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    review_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    return_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    complete_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    void_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    refresh_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "commercial_strategy_id", "version_number", name="uq_commercial_strategy_version"
        ),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_commercial_version_create_key"),
        UniqueConstraint("tenant_id", "submit_idempotency_key", name="uq_commercial_version_submit_key"),
        UniqueConstraint("tenant_id", "review_idempotency_key", name="uq_commercial_version_review_key"),
        UniqueConstraint("tenant_id", "return_idempotency_key", name="uq_commercial_version_return_key"),
        UniqueConstraint("tenant_id", "complete_idempotency_key", name="uq_commercial_version_complete_key"),
        UniqueConstraint("tenant_id", "void_idempotency_key", name="uq_commercial_version_void_key"),
        UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_commercial_version_refresh_key"),
        CheckConstraint("version_number > 0", name="ck_commercial_version_number"),
        CheckConstraint(
            "status IN ('DRAFT','IN_REVIEW','COMPLETED','SUPERSEDED','VOIDED')",
            name="ck_commercial_version_status",
        ),
        CheckConstraint(
            "readiness_status IN ('NOT_STARTED','IN_PROGRESS','READY','BLOCKED','STALE','NOT_APPLICABLE')",
            name="ck_commercial_version_readiness",
        ),
        Index(
            "ix_commercial_version_history",
            "tenant_id",
            "commercial_strategy_id",
            "version_number",
        ),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


@event.listens_for(CommercialStrategyVersion, "before_update")
def _protect_terminal_version(_mapper, _connection, target: CommercialStrategyVersion) -> None:
    state = inspect(target)
    previous = state.attrs.status.history.deleted[0] if state.attrs.status.history.deleted else target.status
    if previous not in {"COMPLETED", "SUPERSEDED", "VOIDED"}:
        return
    changed = {attribute.key for attribute in state.attrs if attribute.history.has_changes()}
    if previous == "COMPLETED" and target.status == "SUPERSEDED" and changed <= {"status", "updated_at"}:
        return
    if changed:
        raise ValueError("Terminal Commercial Strategy versions are immutable; create a new DRAFT version")


@event.listens_for(CommercialStrategyVersion, "before_delete")
def _protect_version_delete(_mapper, _connection, _target: CommercialStrategyVersion) -> None:
    raise ValueError("Commercial Strategy versions cannot be physically deleted")


@event.listens_for(CommercialContractingStrategy, "before_delete")
def _protect_strategy_delete(_mapper, _connection, _target: CommercialContractingStrategy) -> None:
    raise ValueError("Commercial Strategy identities cannot be physically deleted")
