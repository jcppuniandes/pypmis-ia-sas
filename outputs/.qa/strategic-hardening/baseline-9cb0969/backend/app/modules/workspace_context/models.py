"""Minimal persistence for per-user Workspace recency and route continuity."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class RecentWorkspace(Base):
    __tablename__ = "recent_workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    last_route: Mapped[str] = mapped_column(String(320), default="")
    last_opened_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "workspace_id", name="uq_recent_workspace_user_context"),
    )
