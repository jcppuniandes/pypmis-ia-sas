"""Tenant-scoped persistence for Project Permits and Permit Readiness."""

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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base

PERMIT_STATUSES = (
    "NOT_STARTED",
    "IN_PREPARATION",
    "SUBMITTED",
    "UNDER_REVIEW",
    "APPROVED",
    "APPROVED_WITH_CONDITIONS",
    "REJECTED",
    "SUSPENDED",
    "EXPIRED",
    "CANCELLED",
    "NOT_REQUIRED",
)


class ProjectPermit(Base):
    __tablename__ = "project_permits"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    permit_number: Mapped[str] = mapped_column(String(40))
    permit_type_code: Mapped[str] = mapped_column(String(80), index=True)
    requirement_key: Mapped[str | None] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    issuing_authority: Mapped[str] = mapped_column(String(240), default="")
    jurisdiction: Mapped[str | None] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(32), default="NOT_STARTED", index=True)
    application_reference: Mapped[str | None] = mapped_column(String(240))
    application_date: Mapped[date | None] = mapped_column(Date)
    approval_date: Mapped[date | None] = mapped_column(Date)
    effective_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date, index=True)
    permit_identifier: Mapped[str | None] = mapped_column(String(240))
    evidence_refs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    source_reference: Mapped[str | None] = mapped_column(String(300))
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    next_action: Mapped[str | None] = mapped_column(Text)
    target_date: Mapped[date | None] = mapped_column(Date, index=True)
    renewal_of_permit_id: Mapped[int | None] = mapped_column(ForeignKey("project_permits.id"), index=True)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    status_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "permit_number", name="uq_project_permit_number"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_project_permit_create_key"),
        UniqueConstraint("tenant_id", "status_idempotency_key", name="uq_project_permit_status_key"),
        CheckConstraint(
            "status IN ('NOT_STARTED','IN_PREPARATION','SUBMITTED','UNDER_REVIEW','APPROVED',"
            "'APPROVED_WITH_CONDITIONS','REJECTED','SUSPENDED','EXPIRED','CANCELLED','NOT_REQUIRED')",
            name="ck_project_permit_status",
        ),
        CheckConstraint(
            "valid_until IS NULL OR effective_from IS NULL OR valid_until >= effective_from",
            name="ck_project_permit_validity",
        ),
        CheckConstraint(
            "approval_date IS NULL OR application_date IS NULL OR approval_date >= application_date",
            name="ck_project_permit_approval_date",
        ),
        CheckConstraint(
            "renewal_of_permit_id IS NULL OR renewal_of_permit_id != id", name="ck_permit_not_self_renewal"
        ),
        Index("ix_project_permit_tenant_project_status", "tenant_id", "project_workspace_id", "status"),
        Index(
            "ix_project_permit_readiness_scan",
            "tenant_id",
            "project_workspace_id",
            "requirement_key",
            "valid_until",
        ),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class PermitCondition(Base):
    __tablename__ = "permit_conditions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    permit_id: Mapped[int] = mapped_column(ForeignKey("project_permits.id"), index=True)
    condition_key: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    condition_type: Mapped[str] = mapped_column(String(80), default="OTHER")
    blocking: Mapped[bool] = mapped_column(default=False, index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    target_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(32), default="OPEN", index=True)
    evidence_refs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    source_reference: Mapped[str | None] = mapped_column(String(300))
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "permit_id", "condition_key", name="uq_permit_condition_key"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_permit_condition_create_key"),
        CheckConstraint(
            "status IN ('OPEN','EVIDENCE_PROVIDED','SATISFIED','WAIVED','EXPIRED')",
            name="ck_permit_condition_status",
        ),
        Index("ix_permit_condition_scan", "tenant_id", "permit_id", "blocking", "status"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class PermitReadinessAssessment(Base):
    __tablename__ = "permit_readiness_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    assessment_number: Mapped[str] = mapped_column(String(40))
    assessment_version: Mapped[int] = mapped_column(Integer, default=1)
    as_of_date: Mapped[datetime] = mapped_column(DateTime)
    valid_until: Mapped[datetime] = mapped_column(DateTime, index=True)
    gate_profile_code: Mapped[str] = mapped_column(String(80), index=True)
    project_type_code: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(24), default="IN_PROGRESS", index=True)
    requirement_set_hash: Mapped[str] = mapped_column(String(64), index=True)
    permit_register_hash: Mapped[str] = mapped_column(String(64), index=True)
    permit_source_hash: Mapped[str] = mapped_column(String(64), index=True)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64), index=True)
    required_permit_count: Mapped[int] = mapped_column(Integer, default=0)
    approved_count: Mapped[int] = mapped_column(Integer, default=0)
    approved_with_conditions_count: Mapped[int] = mapped_column(Integer, default=0)
    submitted_count: Mapped[int] = mapped_column(Integer, default=0)
    under_review_count: Mapped[int] = mapped_column(Integer, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    suspended_count: Mapped[int] = mapped_column(Integer, default=0)
    expired_count: Mapped[int] = mapped_column(Integer, default=0)
    open_blocking_conditions_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_coverage_percent: Mapped[float] = mapped_column(default=0)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    blockers_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    readiness_status: Mapped[str] = mapped_column(String(16), default="BLOCKED", index=True)
    permit_readiness_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    assessed_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    complete_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    reassessment_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    refresh_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "assessment_number", name="uq_permit_readiness_assessment_number"),
        UniqueConstraint(
            "tenant_id",
            "project_workspace_id",
            "gate_profile_code",
            "assessment_version",
            name="uq_permit_readiness_project_profile_version",
        ),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_permit_readiness_create_key"),
        UniqueConstraint("tenant_id", "complete_idempotency_key", name="uq_permit_readiness_complete_key"),
        UniqueConstraint("tenant_id", "reassessment_idempotency_key", name="uq_permit_readiness_reassess_key"),
        UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_permit_readiness_refresh_key"),
        CheckConstraint(
            "status IN ('DRAFT','IN_PROGRESS','COMPLETED','SUPERSEDED','VOIDED')",
            name="ck_permit_readiness_assessment_status",
        ),
        CheckConstraint(
            "readiness_status IN ('NOT_STARTED','READY','BLOCKED','STALE','EXPIRED')",
            name="ck_permit_readiness_status",
        ),
        CheckConstraint(
            "status != 'COMPLETED' OR (completed_by IS NOT NULL AND completed_at IS NOT NULL "
            "AND permit_readiness_hash IS NOT NULL)",
            name="ck_permit_readiness_completed",
        ),
        CheckConstraint(
            "evidence_coverage_percent >= 0 AND evidence_coverage_percent <= 100",
            name="ck_permit_readiness_coverage",
        ),
        Index(
            "uq_permit_readiness_active_project_profile",
            "tenant_id",
            "project_workspace_id",
            "gate_profile_code",
            unique=True,
            postgresql_where=text("status IN ('DRAFT','IN_PROGRESS')"),
            sqlite_where=text("status IN ('DRAFT','IN_PROGRESS')"),
        ),
        Index(
            "ix_permit_readiness_tenant_project_status",
            "tenant_id",
            "project_workspace_id",
            "status",
        ),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


@event.listens_for(PermitReadinessAssessment, "before_update")
def _protect_completed_assessment(_mapper, _connection, record: PermitReadinessAssessment) -> None:
    state = inspect(record)
    previous = state.attrs.status.history.deleted[0] if state.attrs.status.history.deleted else record.status
    if previous in {"COMPLETED", "SUPERSEDED", "VOIDED"} and any(
        attribute.history.has_changes() for attribute in state.attrs
    ):
        raise ValueError("Completed, superseded and voided Permit Readiness Assessments are immutable")


@event.listens_for(PermitReadinessAssessment, "before_delete")
def _protect_assessment_delete(_mapper, _connection, record: PermitReadinessAssessment) -> None:
    if record.status in {"COMPLETED", "SUPERSEDED", "VOIDED"}:
        raise ValueError("Completed, superseded and voided Permit Readiness Assessments cannot be deleted")
