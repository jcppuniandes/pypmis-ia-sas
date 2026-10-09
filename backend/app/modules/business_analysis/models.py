"""Persistent Business Analysis aggregate and immutable revision snapshots."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class BusinessAnalysis(Base):
    __tablename__ = "business_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    analysis_number: Mapped[str] = mapped_column(String(40), index=True)
    source_idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id"), index=True)
    source_idea_evaluation_id: Mapped[int] = mapped_column(ForeignKey("idea_evaluations.id"), index=True)
    owning_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    supersedes_analysis_id: Mapped[int | None] = mapped_column(ForeignKey("business_analyses.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="DRAFT", index=True)
    title: Mapped[str] = mapped_column(String(220))
    content_json: Mapped[dict] = mapped_column(JSON, default=dict)
    recommended_option_id: Mapped[str | None] = mapped_column(String(80))
    readiness_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_idea_hash: Mapped[str] = mapped_column(String(64))
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64))
    review_json: Mapped[dict] = mapped_column(JSON, default=dict)
    completion_hash: Mapped[str] = mapped_column(String(64), default="")
    idempotency_key: Mapped[str] = mapped_column(String(120))
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    reviewer_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("tenant_id", "analysis_number", name="uq_business_analysis_tenant_number"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_business_analysis_idempotency"),
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','IN_REVIEW','RETURNED','COMPLETED','SUPERSEDED','VOIDED')",
            name="ck_business_analysis_status",
        ),
        Index(
            "uq_business_analysis_active_idea",
            "tenant_id",
            "source_idea_id",
            unique=True,
            postgresql_where=text("status IN ('DRAFT','SUBMITTED','IN_REVIEW','RETURNED')"),
            sqlite_where=text("status IN ('DRAFT','SUBMITTED','IN_REVIEW','RETURNED')"),
        ),
    )
    __mapper_args__ = {"version_id_col": revision_version}


class BusinessAnalysisRevision(Base):
    __tablename__ = "business_analysis_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    business_analysis_id: Mapped[int] = mapped_column(ForeignKey("business_analyses.id"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    lifecycle_status: Mapped[str] = mapped_column(String(40))
    source_idea_hash: Mapped[str] = mapped_column(String(64))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    content_json: Mapped[dict] = mapped_column(JSON, default=dict)
    readiness_json: Mapped[dict] = mapped_column(JSON, default=dict)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "business_analysis_id",
            "revision_number",
            name="uq_business_analysis_revision_number",
        ),
    )


@event.listens_for(BusinessAnalysisRevision, "before_update")
def _protect_revision_update(_mapper, _connection, target: BusinessAnalysisRevision) -> None:
    if any(attribute.history.has_changes() for attribute in inspect(target).attrs):
        raise ValueError("Business Analysis revisions are immutable snapshots")


@event.listens_for(BusinessAnalysisRevision, "before_delete")
def _protect_revision_delete(_mapper, _connection, _target: BusinessAnalysisRevision) -> None:
    raise ValueError("Business Analysis revisions cannot be physically deleted")


@event.listens_for(BusinessAnalysis, "before_update")
def _protect_completed_analysis(_mapper, _connection, target: BusinessAnalysis) -> None:
    state = inspect(target)
    state_history = state.attrs.status.history
    previous = state_history.deleted[0] if state_history.deleted else target.status
    if previous != "COMPLETED":
        return
    changed = {attribute.key for attribute in state.attrs if attribute.history.has_changes()}
    supersede_metadata = {"status", "updated_by_user_id", "updated_at"}
    if target.status == "SUPERSEDED" and changed <= supersede_metadata:
        return
    if changed:
        raise ValueError("Completed Business Analysis records are immutable; create a new version")


@event.listens_for(BusinessAnalysis, "before_delete")
def _protect_analysis_delete(_mapper, _connection, _target: BusinessAnalysis) -> None:
    raise ValueError("Business Analysis records cannot be physically deleted; use a governed lifecycle state")
