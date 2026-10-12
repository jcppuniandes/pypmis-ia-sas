"""Separate execution and acceptance aggregates, never Foundation results."""

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


class QraRun(Base):
    __tablename__ = "qra_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    run_number: Mapped[str] = mapped_column(String(40))
    model_definition_id: Mapped[int] = mapped_column(ForeignKey("qra_model_definitions.id"), index=True)
    model_number: Mapped[str] = mapped_column(String(40))
    model_version: Mapped[int] = mapped_column(Integer)
    model_hash: Mapped[str] = mapped_column(String(64))
    analysis_type: Mapped[str] = mapped_column(String(40))
    engine_name: Mapped[str] = mapped_column(String(80), default="PPMIS_QRA_ENGINE")
    engine_version: Mapped[str] = mapped_column(String(80))
    formula_version: Mapped[str] = mapped_column(String(80))
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", index=True)
    seed: Mapped[str] = mapped_column(String(30))
    iterations_requested: Mapped[int] = mapped_column(Integer)
    iterations_completed: Mapped[int] = mapped_column(Integer, default=0)
    input_snapshot_hash: Mapped[str] = mapped_column(String(64))
    result_snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    trace_hash: Mapped[str | None] = mapped_column(String(64))
    # Large input JSON is explicitly deferred: list/status reads do not decode it.
    input_snapshot_json: Mapped[dict] = mapped_column(JSON, deferred=True)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict, deferred=True)
    runtime_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    failure_reason: Mapped[str | None] = mapped_column(String(240))
    title: Mapped[str] = mapped_column(String(240), default="Governed QRA Run")
    comments: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    execution_actor: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)
    dispatch_state: Mapped[str] = mapped_column(String(24), default="NOT_REQUESTED")
    task_id: Mapped[str | None] = mapped_column(String(100))
    revision_version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("tenant_id", "run_number", name="uq_qra_run_number"),
        UniqueConstraint("task_id", name="uq_qra_run_task"),
        CheckConstraint(
            "status IN ('QUEUED','VALIDATING','RUNNING','COMPLETED','FAILED','CANCELLED')", name="ck_qra_run_status"
        ),
        CheckConstraint("analysis_type IN ('COST_QRA','SCHEDULE_QRA')", name="ck_qra_run_analysis"),
        CheckConstraint(
            "iterations_requested > 0 AND iterations_completed >= 0 AND iterations_completed <= iterations_requested AND revision_version > 0",
            name="ck_qra_run_progress",
        ),
        CheckConstraint(
            "status != 'COMPLETED' OR (result_snapshot_hash IS NOT NULL AND trace_hash IS NOT NULL AND completed_at IS NOT NULL AND iterations_completed = iterations_requested)",
            name="ck_qra_run_completed",
        ),
        Index("ix_qra_run_history", "tenant_id", "project_workspace_id", "analysis_type", "id"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class QraRunReview(Base):
    """Review state is not part of the immutable execution/result payload."""

    __tablename__ = "qra_run_reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("qra_runs.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="IN_REVIEW")
    reviewed_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    accepted_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_comments: Mapped[str] = mapped_column(Text, default="")
    acceptance_comments: Mapped[str] = mapped_column(Text, default="")
    acceptance_hash: Mapped[str | None] = mapped_column(String(64))
    revision_version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("tenant_id", "run_id", name="uq_qra_run_review"),
        CheckConstraint("status IN ('IN_REVIEW','ACCEPTED')", name="ck_qra_run_review_status"),
        CheckConstraint(
            "status != 'ACCEPTED' OR (accepted_by IS NOT NULL AND accepted_at IS NOT NULL AND acceptance_hash IS NOT NULL)",
            name="ck_qra_run_review_accepted",
        ),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


_FROZEN_RUN_FIELDS = {
    "tenant_id",
    "project_workspace_id",
    "run_number",
    "model_definition_id",
    "model_number",
    "model_version",
    "model_hash",
    "analysis_type",
    "engine_name",
    "engine_version",
    "formula_version",
    "configuration_id",
    "configuration_revision",
    "configuration_hash",
    "seed",
    "iterations_requested",
    "input_snapshot_hash",
    "input_snapshot_json",
    "title",
    "comments",
    "created_by",
    "created_at",
}


@event.listens_for(QraRun, "before_update")
def _protect_run(_mapper, _connection, row):
    state = inspect(row)
    previous = state.attrs.status.history.deleted
    previous_status = previous[0] if previous else row.status
    changed = {attr.key for attr in state.attrs if attr.history.has_changes()}
    if previous_status == "COMPLETED" and changed:
        raise ValueError("Completed QRA run is immutable")
    if changed & _FROZEN_RUN_FIELDS:
        raise ValueError("Frozen QRA run input manifest is immutable")
    metadata_history = state.attrs.runtime_metadata.history
    if metadata_history.deleted:
        previous_metadata = metadata_history.deleted[0]
        if previous_metadata.get("worker_lease_seconds") != row.runtime_metadata.get("worker_lease_seconds"):
            raise ValueError("Frozen QRA worker lease is immutable")


@event.listens_for(QraRun, "before_delete")
def _protect_run_delete(_mapper, _connection, _row):
    raise ValueError("QRA run history cannot be deleted")


@event.listens_for(QraRunReview, "before_update")
def _protect_accepted_review(_mapper, _connection, row):
    state = inspect(row)
    history = state.attrs.status.history
    previous = history.deleted[0] if history.deleted else row.status
    if previous == "ACCEPTED" and any(attr.history.has_changes() for attr in state.attrs):
        raise ValueError("Accepted QRA result review is immutable")


@event.listens_for(QraRunReview, "before_delete")
def _protect_review_delete(_mapper, _connection, _row):
    raise ValueError("QRA review history cannot be deleted")
