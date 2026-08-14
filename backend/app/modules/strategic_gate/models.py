"""Persistent strategic decision records for Gate 07C.

A Strategic Gate Decision is an immutable strategic record after closure. It
is not a Workspace, Project, Portfolio Candidate, or a field on Proposal.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class StrategicGateDecision(Base):
    __tablename__ = "strategic_gate_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    decision_number: Mapped[str] = mapped_column(String(40), index=True)
    context_type: Mapped[str] = mapped_column(String(48), default="PROJECT_PROPOSAL", index=True)
    context_id: Mapped[int] = mapped_column(Integer, index=True)
    project_proposal_id: Mapped[int] = mapped_column(ForeignKey("project_proposals.id"), index=True)
    gate_type: Mapped[str] = mapped_column(String(80), default="PROJECT_PROPOSAL_GATE", index=True)
    gate_round: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    outcome: Mapped[str | None] = mapped_column(String(24), index=True)
    proposal_status_at_entry: Mapped[str] = mapped_column(String(48))
    proposal_readiness_status: Mapped[str] = mapped_column(String(64))
    proposal_readiness_hash: Mapped[str] = mapped_column(String(64))
    proposal_readiness_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    proposal_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_idea_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    accepted_idea_evaluation_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    proposal_evaluation_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id"), index=True)
    accepted_idea_evaluation_id: Mapped[int] = mapped_column(ForeignKey("idea_evaluations.id"), index=True)
    proposal_evaluation_id: Mapped[int] = mapped_column(ForeignKey("project_proposal_evaluations.id"), index=True)
    owning_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    target_portfolio_workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("enterprise_workspaces.id"), index=True
    )
    strategic_objectives_snapshot_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    proposal_score: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    proposal_evaluation_revision: Mapped[int] = mapped_column(Integer)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64))
    configuration_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    decision_criteria_snapshot_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    decision_checklist_snapshot_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    conditions_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    evidence_refs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    decision_comments: Mapped[str] = mapped_column(Text, default="")
    decision_maker_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    committee_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    decision_hash: Mapped[str] = mapped_column(String(64), default="")
    prepared_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    prepared_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    deferred_until: Mapped[date | None] = mapped_column(Date)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "decision_number", name="uq_sgd_tenant_number"),
        UniqueConstraint(
            "tenant_id",
            "project_proposal_id",
            "gate_type",
            "gate_round",
            name="uq_sgd_proposal_gate_round",
        ),
        Index(
            "uq_sgd_one_active_per_proposal_gate",
            "tenant_id",
            "project_proposal_id",
            "gate_type",
            unique=True,
            postgresql_where=text("state IN ('DRAFT','SUBMITTED','IN_REVIEW')"),
            sqlite_where=text("state IN ('DRAFT','SUBMITTED','IN_REVIEW')"),
        ),
    )
    __mapper_args__ = {"version_id_col": revision_version}


@event.listens_for(StrategicGateDecision, "before_update")
def _protect_closed_decision(_mapper, _connection, target: StrategicGateDecision) -> None:
    state_history = inspect(target).attrs.state.history
    prior = state_history.deleted[0] if state_history.deleted else target.state
    if prior in {"DECIDED", "VOIDED"}:
        raise ValueError("Closed Strategic Gate Decisions are immutable snapshots")


@event.listens_for(StrategicGateDecision, "before_delete")
def _protect_decision_delete(_mapper, _connection, _target: StrategicGateDecision) -> None:
    raise ValueError("Strategic Gate Decisions cannot be physically deleted")
