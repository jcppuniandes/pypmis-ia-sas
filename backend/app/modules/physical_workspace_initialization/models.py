"""Persistence for the generic physical Workspace initialization engine."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class PhysicalWorkspaceInitialization(Base):
    """The singleton initialization record for PROPERTY, FACILITY or WAREHOUSE."""

    __tablename__ = "physical_workspace_initializations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    workspace_type_code: Mapped[str] = mapped_column(String(40), index=True)
    state: Mapped[str] = mapped_column(String(40), default="NOT_STARTED", index=True)
    template_config_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    template_code: Mapped[str] = mapped_column(String(120))
    template_revision: Mapped[int] = mapped_column(Integer)
    template_content_hash: Mapped[str] = mapped_column(String(64))
    initialization_version: Mapped[int] = mapped_column(Integer, default=1)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    started_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_modified_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    validated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime)
    activated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime)
    validation_hash: Mapped[str | None] = mapped_column(String(64))
    checklist_hash: Mapped[str | None] = mapped_column(String(64))
    common_checklist_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    type_specific_checklist_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    defaults_applied_json: Mapped[dict] = mapped_column(JSON, default=dict)
    assignments_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    module_states_json: Mapped[dict] = mapped_column(JSON, default=dict)
    failure_code: Mapped[str | None] = mapped_column(String(120))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "workspace_id", name="uq_physical_workspace_initialization"),)
