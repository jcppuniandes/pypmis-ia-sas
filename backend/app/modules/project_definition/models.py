"""Tenant-scoped persistence for Project Definition / FEL Manager."""

from datetime import datetime

from sqlalchemy import (
    JSON,
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


class ProjectDefinitionAssessment(Base):
    __tablename__ = "project_definition_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    assessment_number: Mapped[str] = mapped_column(String(120), index=True)
    assessment_version: Mapped[int] = mapped_column(Integer, default=1)
    framework_config_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    framework_code: Mapped[str] = mapped_column(String(120), index=True)
    framework_type: Mapped[str] = mapped_column(String(40))
    framework_version: Mapped[str] = mapped_column(String(80))
    framework_hash: Mapped[str] = mapped_column(String(64), index=True)
    fel_stage_code: Mapped[str] = mapped_column(String(40), index=True)
    assessment_date: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    as_of_date: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    raw_score: Mapped[float | None]
    normalized_score: Mapped[float | None]
    maturity_level: Mapped[str | None] = mapped_column(String(80))
    threshold_status: Mapped[str] = mapped_column(String(32), default="NOT_EVALUATED")
    category_results_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    element_results_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    blocking_items_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    actions_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_refs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    source_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    definition_source_hash: Mapped[str] = mapped_column(String(64), index=True)
    assessed_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    assessment_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    complete_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    reevaluate_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "assessment_number", name="uq_project_definition_assessment_number"),
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "assessment_version", name="uq_project_definition_assessment_version"
        ),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_project_definition_assessment_create_key"),
        UniqueConstraint("tenant_id", "complete_idempotency_key", name="uq_project_definition_assessment_complete_key"),
        UniqueConstraint(
            "tenant_id", "reevaluate_idempotency_key", name="uq_project_definition_assessment_reevaluate_key"
        ),
        CheckConstraint(
            "status IN ('DRAFT','IN_PROGRESS','COMPLETED','SUPERSEDED','VOIDED')",
            name="ck_project_definition_assessment_status",
        ),
        CheckConstraint(
            "framework_type IN ('CUSTOM','PDRI_COMPATIBLE','FEL_INDEX_COMPATIBLE')",
            name="ck_project_definition_framework_type",
        ),
        CheckConstraint(
            "threshold_status IN ('NOT_EVALUATED','BELOW_REQUIRED','MEETS_REQUIRED','EXCEEDS_REQUIRED')",
            name="ck_project_definition_threshold_status",
        ),
        Index("ix_project_definition_assessment_lookup", "tenant_id", "project_workspace_id", "fel_stage_code"),
        Index("ix_project_definition_assessment_history", "tenant_id", "project_workspace_id", "assessment_date"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class ProjectFELStatus(Base):
    __tablename__ = "project_fel_statuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    current_stage_code: Mapped[str] = mapped_column(String(40), default="FEL-1", index=True)
    status: Mapped[str] = mapped_column(String(32), default="NOT_STARTED", index=True)
    stage_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    target_stage_exit_date: Mapped[datetime | None] = mapped_column(DateTime)
    effective_framework_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    effective_framework_revision: Mapped[int] = mapped_column(Integer)
    effective_framework_hash: Mapped[str] = mapped_column(String(64), index=True)
    current_assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_definition_assessments.id"), index=True
    )
    latest_completed_assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_definition_assessments.id"), index=True
    )
    readiness_status: Mapped[str] = mapped_column(String(24), default="NOT_STARTED", index=True)
    definition_source_hash: Mapped[str] = mapped_column(String(64), index=True)
    review_submitted_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    review_submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    start_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    submit_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    complete_stage_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    return_stage_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    refresh_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", name="uq_project_fel_status_project"),
        UniqueConstraint("tenant_id", "start_idempotency_key", name="uq_project_fel_start_key"),
        UniqueConstraint("tenant_id", "submit_idempotency_key", name="uq_project_fel_submit_key"),
        UniqueConstraint("tenant_id", "complete_stage_idempotency_key", name="uq_project_fel_complete_stage_key"),
        UniqueConstraint("tenant_id", "return_stage_idempotency_key", name="uq_project_fel_return_stage_key"),
        UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_project_fel_refresh_key"),
        CheckConstraint(
            "status IN ('NOT_STARTED','IN_STAGE','READY_FOR_STAGE_REVIEW','STAGE_COMPLETED','BLOCKED')",
            name="ck_project_fel_status_lifecycle",
        ),
        CheckConstraint(
            "readiness_status IN ('READY','BLOCKED','STALE','NOT_STARTED')",
            name="ck_project_fel_readiness_status",
        ),
        Index("ix_project_fel_tenant_stage", "tenant_id", "current_stage_code", "status"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class ProjectDefinitionAction(Base):
    __tablename__ = "project_definition_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("project_definition_assessments.id"), index=True)
    element_key: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(220))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    target_date: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(24), default="OPEN", index=True)
    evidence_refs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    blocking: Mapped[bool] = mapped_column(default=True)
    audit_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_project_definition_action_create_key"),
        CheckConstraint(
            "status IN ('OPEN','IN_PROGRESS','RESOLVED','ACCEPTED_RISK','CANCELLED')",
            name="ck_project_definition_action_status",
        ),
        Index("ix_project_definition_action_lookup", "tenant_id", "project_workspace_id", "status"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


@event.listens_for(ProjectDefinitionAssessment, "before_update")
def _protect_completed_assessment(_mapper, _connection, record: ProjectDefinitionAssessment) -> None:
    state = inspect(record)
    previous = state.attrs.status.history.deleted[0] if state.attrs.status.history.deleted else record.status
    if previous in {"COMPLETED", "SUPERSEDED", "VOIDED"} and any(
        attribute.history.has_changes() for attribute in state.attrs
    ):
        raise ValueError("Completed, superseded and voided Project Definition Assessments are immutable")


@event.listens_for(ProjectDefinitionAssessment, "before_delete")
def _protect_assessment_delete(_mapper, _connection, _record: ProjectDefinitionAssessment) -> None:
    raise ValueError("Project Definition Assessments cannot be physically deleted")
