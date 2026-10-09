"""Persistence for Project Workspace initialization and activation."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class ProjectWorkspaceInitialization(Base):
    """The one governed initialization record associated with a Project Workspace."""

    __tablename__ = "project_workspace_initializations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    state: Mapped[str] = mapped_column(String(40), default="NOT_STARTED", index=True)
    template_config_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    template_code: Mapped[str] = mapped_column(String(120))
    template_revision: Mapped[int] = mapped_column(Integer)
    initialization_version: Mapped[int] = mapped_column(Integer, default=1)
    started_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_modified_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    validated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime)
    activated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime)
    validation_hash: Mapped[str | None] = mapped_column(String(64))
    checklist_hash: Mapped[str | None] = mapped_column(String(64))
    checklist_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    module_states_json: Mapped[dict] = mapped_column(JSON, default=dict)
    defaults_applied_json: Mapped[dict] = mapped_column(JSON, default=dict)
    assignments_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    failure_code: Mapped[str | None] = mapped_column(String(120))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "workspace_id", name="uq_project_workspace_initialization"),)
