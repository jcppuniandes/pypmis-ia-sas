"""Immutable eligibility snapshots for Gate 07L Post-FID governance."""

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
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base

ELIGIBILITY_STATUSES = (
    "READY_FOR_PROJECT_WORKSPACE_INITIALIZATION",
    "READY_FOR_PROJECT_WORKSPACE_ACTIVATION",
    "POST_FID_PROJECT_GOVERNANCE_BLOCKED",
    "NO_REACTIVATION_REQUIRED",
    "NOT_APPLICABLE",
    "STALE",
)


class PostFIDProjectEligibility(Base):
    """An immutable evaluation of one canonical Project Workspace."""

    __tablename__ = "post_fid_project_eligibilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    investment_decision_id: Mapped[int] = mapped_column(ForeignKey("investment_decisions.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    eligibility_round: Mapped[int] = mapped_column(Integer)
    fid_decision_hash: Mapped[str] = mapped_column(String(64), index=True)
    decision_package_hash: Mapped[str] = mapped_column(String(64), index=True)
    project_state_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    condition_snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    eligibility_status: Mapped[str] = mapped_column(String(64), index=True)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    blockers_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    eligible_for_initialization: Mapped[bool] = mapped_column(Boolean, default=False)
    eligible_for_activation: Mapped[bool] = mapped_column(Boolean, default=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    evaluated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    source_current: Mapped[bool] = mapped_column(Boolean, default=True)
    eligibility_hash: Mapped[str] = mapped_column(String(64), index=True)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    configuration_hash: Mapped[str] = mapped_column(String(64), index=True)
    operation_type: Mapped[str] = mapped_column(String(32), default="EVALUATE")
    operation_key: Mapped[str] = mapped_column(String(160))
    operation_payload_hash: Mapped[str] = mapped_column(String(64))
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "investment_decision_id",
            "project_workspace_id",
            "eligibility_round",
            name="uq_post_fid_eligibility_round",
        ),
        UniqueConstraint(
            "tenant_id",
            "investment_decision_id",
            "project_workspace_id",
            "operation_key",
            name="uq_post_fid_eligibility_operation",
        ),
        CheckConstraint(
            "eligibility_status IN ("
            + ",".join(f"'{value}'" for value in ELIGIBILITY_STATUSES)
            + ")",
            name="ck_post_fid_eligibility_status",
        ),
        CheckConstraint(
            "NOT (eligible_for_initialization AND eligible_for_activation)",
            name="ck_post_fid_single_handoff",
        ),
        Index(
            "ix_post_fid_eligibility_latest",
            "tenant_id",
            "investment_decision_id",
            "project_workspace_id",
            "eligibility_round",
        ),
        Index(
            "ix_post_fid_eligibility_queue",
            "tenant_id",
            "eligibility_status",
            "evaluated_at",
        ),
    )


def _immutable(_mapper, _connection, _target: PostFIDProjectEligibility) -> None:
    raise ValueError("Post-FID eligibility snapshots are immutable")


event.listen(PostFIDProjectEligibility, "before_update", _immutable)
event.listen(PostFIDProjectEligibility, "before_delete", _immutable)
