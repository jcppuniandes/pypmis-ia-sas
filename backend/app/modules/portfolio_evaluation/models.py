"""Tenant-scoped persistence for Gate 07E.

An evaluation belongs directly to the Project + Portfolio membership context.
There is deliberately no global candidate or persisted global rank entity.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class PortfolioProjectEvaluation(Base):
    __tablename__ = "portfolio_project_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    portfolio_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    portfolio_membership_id: Mapped[int] = mapped_column(ForeignKey("portfolio_project_memberships.id"), index=True)
    evaluation_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    matrix_configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    matrix_revision: Mapped[int] = mapped_column(Integer)
    matrix_hash: Mapped[str] = mapped_column(String(64))
    matrix_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_snapshot_hash: Mapped[str] = mapped_column(String(64))
    planning_entry_hash: Mapped[str] = mapped_column(String(64))
    ratings_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    score_components_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    normalized_score: Mapped[Decimal] = mapped_column(Numeric(9, 4), default=0)
    strategic_alignment_score: Mapped[Decimal] = mapped_column(Numeric(9, 4), default=0)
    risk_score: Mapped[Decimal] = mapped_column(Numeric(9, 4), default=0)
    comments: Mapped[str] = mapped_column(Text, default="")
    evaluator_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    start_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    complete_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    reevaluation_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "portfolio_workspace_id",
            "project_workspace_id",
            "evaluation_version",
            name="uq_portfolio_project_evaluation_version",
        ),
        UniqueConstraint("tenant_id", "start_idempotency_key", name="uq_portfolio_evaluation_start_key"),
        UniqueConstraint("tenant_id", "complete_idempotency_key", name="uq_portfolio_evaluation_complete_key"),
        UniqueConstraint("tenant_id", "reevaluation_idempotency_key", name="uq_portfolio_evaluation_reeval_key"),
    )
    __mapper_args__ = {"version_id_col": revision_version}


@event.listens_for(PortfolioProjectEvaluation, "before_update")
def _protect_completed_evaluation(_mapper, _connection, target: PortfolioProjectEvaluation) -> None:
    state = inspect(target)
    changed = {attribute.key for attribute in state.attrs if attribute.history.has_changes()}
    history = state.attrs.status.history
    previous = history.deleted[0] if history.deleted else target.status
    if previous == "COMPLETED" and target.status == "SUPERSEDED" and changed <= {"status", "updated_at"}:
        return
    if previous in {"COMPLETED", "SUPERSEDED", "VOIDED"} and changed:
        raise ValueError("Completed Portfolio evaluations are immutable snapshots")


@event.listens_for(PortfolioProjectEvaluation, "before_delete")
def _protect_evaluation_delete(_mapper, _connection, _target: PortfolioProjectEvaluation) -> None:
    raise ValueError("Portfolio evaluations cannot be physically deleted")
