"""Persistent records for Gate 07B Project Proposal lifecycle.

A Project Proposal is a strategic pre-project record. It is deliberately not
an EnterpriseWorkspace and it cannot materialize a Project Workspace.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class ProjectProposal(Base):
    __tablename__ = "project_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    proposal_number: Mapped[str] = mapped_column(String(40), index=True)
    source_idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id"), index=True)
    accepted_idea_evaluation_id: Mapped[int] = mapped_column(ForeignKey("idea_evaluations.id"), index=True)
    owning_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    target_portfolio_workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("enterprise_workspaces.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(220))
    business_need: Mapped[str] = mapped_column(Text, default="")
    business_justification: Mapped[str] = mapped_column(Text, default="")
    project_objectives_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    preliminary_scope: Mapped[str] = mapped_column(Text, default="")
    out_of_scope: Mapped[str] = mapped_column(Text, default="")
    expected_benefits: Mapped[str] = mapped_column(Text, default="")
    benefit_owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    rom_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency_code: Mapped[str] = mapped_column(String(8), default="COP")
    preliminary_duration_days: Mapped[int | None] = mapped_column(Integer)
    target_start_date: Mapped[date | None] = mapped_column(Date)
    target_finish_date: Mapped[date | None] = mapped_column(Date)
    key_risks_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    assumptions_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    constraints_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    strategic_objective_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    sponsor_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    proposal_owner_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    origin_idea_score: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    status: Mapped[str] = mapped_column(String(48), default="DRAFT", index=True)
    mapping_configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    mapping_revision: Mapped[int] = mapped_column(Integer)
    mapping_hash: Mapped[str] = mapped_column(String(64))
    source_values_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    mapped_values_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    configuration_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    review_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    attachment_refs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    return_reason: Mapped[str | None] = mapped_column(Text)
    returned_stage: Mapped[str | None] = mapped_column(String(48))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    evaluation_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    evaluation_completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    ready_for_gate_at: Mapped[datetime | None] = mapped_column(DateTime)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "proposal_number", name="uq_project_proposal_tenant_number"),)
    __mapper_args__ = {"version_id_col": revision_version}


class ProjectProposalEvaluation(Base):
    __tablename__ = "project_proposal_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_proposal_id: Mapped[int] = mapped_column(ForeignKey("project_proposals.id"), index=True)
    evaluation_version: Mapped[int] = mapped_column(Integer)
    matrix_configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    matrix_revision: Mapped[int] = mapped_column(Integer)
    matrix_hash: Mapped[str] = mapped_column(String(64))
    criteria_snapshot_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    ratings_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    total_score: Mapped[Decimal] = mapped_column(Numeric(9, 4), default=0)
    recommendation: Mapped[str] = mapped_column(String(80), default="PROCEED_TO_GATE")
    comments: Mapped[str] = mapped_column(Text, default="")
    evaluator_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "project_proposal_id",
            "evaluation_version",
            name="uq_project_proposal_evaluation_version",
        ),
    )


@event.listens_for(ProjectProposalEvaluation, "before_update")
def _protect_evaluation_update(_mapper, _connection, target: ProjectProposalEvaluation) -> None:
    if any(attribute.history.has_changes() for attribute in inspect(target).attrs):
        raise ValueError("Project Proposal evaluations are immutable snapshots")


@event.listens_for(ProjectProposalEvaluation, "before_delete")
def _protect_evaluation_delete(_mapper, _connection, _target: ProjectProposalEvaluation) -> None:
    raise ValueError("Project Proposal evaluations cannot be physically deleted")
