"""Persistent lifecycle records for enterprise ideas.

An Idea is deliberately a governed process record, not an EnterpriseWorkspace.
Evaluation revisions are immutable child snapshots so re-evaluation preserves
the decision trail without duplicating the Idea.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class Idea(Base):
    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    idea_number: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(220))
    description: Mapped[str] = mapped_column(Text, default="")
    idea_type: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(120), index=True)
    expected_benefit: Mapped[str] = mapped_column(Text, default="")
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency_code: Mapped[str] = mapped_column(String(8), default="COP")
    owning_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    target_portfolio_workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("enterprise_workspaces.id"), index=True
    )
    strategic_objective_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    requestor_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    state: Mapped[str] = mapped_column(String(40), default="DRAFT", index=True)
    screening_json: Mapped[dict] = mapped_column(JSON, default=dict)
    routing_json: Mapped[dict] = mapped_column(JSON, default=dict)
    configuration_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    attachment_refs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    accepted_evaluation_id: Mapped[int | None] = mapped_column(Integer, index=True)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decision_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    readiness_json: Mapped[dict] = mapped_column(JSON, default=dict)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_modified_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    screened_at: Mapped[datetime | None] = mapped_column(DateTime)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("tenant_id", "idea_number", name="uq_idea_tenant_number"),)
    __mapper_args__ = {"version_id_col": revision_version}


class IdeaEvaluation(Base):
    __tablename__ = "idea_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id"), index=True)
    evaluation_version: Mapped[int] = mapped_column(Integer, default=1)
    matrix_configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    matrix_revision: Mapped[int] = mapped_column(Integer)
    matrix_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    ratings_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    total_score: Mapped[Decimal] = mapped_column(Numeric(9, 4), default=0)
    result: Mapped[str] = mapped_column(String(80), default="EVALUATED")
    comments: Mapped[str] = mapped_column(Text, default="")
    evaluator_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "idea_id", "evaluation_version", name="uq_idea_evaluation_version"),)


@event.listens_for(IdeaEvaluation, "before_update")
def _protect_evaluation_update(_mapper, _connection, target: IdeaEvaluation) -> None:
    changed = [attribute.key for attribute in inspect(target).attrs if attribute.history.has_changes()]
    if changed:
        raise ValueError("Idea evaluations are immutable snapshots")


@event.listens_for(IdeaEvaluation, "before_delete")
def _protect_evaluation_delete(_mapper, _connection, _target: IdeaEvaluation) -> None:
    raise ValueError("Idea evaluations cannot be physically deleted")
