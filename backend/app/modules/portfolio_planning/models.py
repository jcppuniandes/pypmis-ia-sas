"""Minimal persistence for Gate 07D Portfolio membership.

Portfolio membership is an analytical N:M relation. It deliberately does not
alter the canonical Enterprise Workspace parent hierarchy.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class PortfolioProjectMembership(Base):
    __tablename__ = "portfolio_project_memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    portfolio_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    membership_source: Mapped[str] = mapped_column(String(40), default="STRATEGIC_INTAKE", index=True)
    source_strategic_gate_decision_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategic_gate_decisions.id"), index=True
    )
    source_project_proposal_id: Mapped[int | None] = mapped_column(ForeignKey("project_proposals.id"), index=True)
    is_target_portfolio: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", index=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        Index(
            "uq_portfolio_project_membership_active",
            "tenant_id",
            "portfolio_workspace_id",
            "project_workspace_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )
    __mapper_args__ = {"version_id_col": revision_version}
