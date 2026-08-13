"""Persistence for governed Project Workspace creation requests."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class ProjectCreationRequest(Base):
    """A process record; it is never the Project Workspace identity."""

    __tablename__ = "project_creation_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    request_number: Mapped[str] = mapped_column(String(40), index=True)
    state: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    requestor_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    parent_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    project_template_config_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    project_name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    project_manager_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_finish: Mapped[date | None] = mapped_column(Date)
    currency_code: Mapped[str] = mapped_column(String(8), default="COP")
    estimated_budget: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    project_type: Mapped[str | None] = mapped_column(String(120))
    project_phase: Mapped[str | None] = mapped_column(String(120))
    priority: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(120))
    strategic_objective_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    preview_record_code: Mapped[str | None] = mapped_column(String(255))
    preview_project_number: Mapped[str | None] = mapped_column(String(80))
    submission_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    submission_hash: Mapped[str | None] = mapped_column(String(64))
    approval_hash: Mapped[str | None] = mapped_column(String(64))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    materialized_workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("enterprise_workspaces.id"), index=True, unique=True
    )
    materialized_project_number: Mapped[str | None] = mapped_column(String(80))
    materialized_record_code: Mapped[str | None] = mapped_column(String(255))
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_modified_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    materialized_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("tenant_id", "request_number", name="uq_project_creation_request_number"),)
