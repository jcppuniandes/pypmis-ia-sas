"""Persistence for the generic PROPERTY/FACILITY/WAREHOUSE creation process."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class PhysicalWorkspaceCreationRequest(Base):
    """Governed process record; the canonical Workspace remains enterprise_workspaces."""

    __tablename__ = "physical_workspace_creation_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    request_number: Mapped[str] = mapped_column(String(40), index=True)
    workspace_type_code: Mapped[str] = mapped_column(String(40), index=True)
    state: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    requestor_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    parent_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    template_config_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    workspace_name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    responsible_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    business_number_preview: Mapped[str | None] = mapped_column(String(80))
    record_code_preview: Mapped[str | None] = mapped_column(String(255))
    attributes_json: Mapped[dict] = mapped_column(JSON, default=dict)
    classification_values_json: Mapped[list] = mapped_column(JSON, default=list)
    submitted_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    submitted_hash: Mapped[str | None] = mapped_column(String(64))
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    approval_hash: Mapped[str | None] = mapped_column(String(64))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    materialized_workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("enterprise_workspaces.id"), index=True, unique=True
    )
    materialized_business_number: Mapped[str | None] = mapped_column(String(80))
    materialized_record_code: Mapped[str | None] = mapped_column(String(255))
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_modified_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    materialized_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("tenant_id", "request_number", name="uq_physical_workspace_request_number"),)
