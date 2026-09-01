"""Immutable tenant-scoped records for Gate 07K Investment Decision / FID."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
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


class InvestmentDecision(Base):
    """Formal decision record; never doubles as a Project or a preparation."""

    __tablename__ = "investment_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    decision_number: Mapped[str] = mapped_column(String(40), index=True)
    investment_gate_preparation_id: Mapped[int] = mapped_column(
        ForeignKey("investment_gate_preparations.id"), index=True
    )
    portfolio_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    investment_gate_profile_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    profile_code: Mapped[str] = mapped_column(String(80), index=True)
    decision_round: Mapped[int] = mapped_column(Integer, default=1)
    decision_scope_type: Mapped[str] = mapped_column(String(32), default="EXACT_PROJECT_SET")
    decision_scope_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    outcome: Mapped[str | None] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(240))
    executive_summary: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    conditions_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    hold_reason: Mapped[str | None] = mapped_column(Text)
    recycle_target: Mapped[str | None] = mapped_column(String(120))
    source_preparation_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_package_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_profile_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_policy_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    decision_package_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64), index=True)
    configuration_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    authority_model: Mapped[str] = mapped_column(String(32), default="SINGLE_DECISION_MAKER")
    authority_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    committee_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    quorum_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    voting_rule_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    checklist_snapshot_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    authorized_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    authorized_currency: Mapped[str | None] = mapped_column(String(3))
    authorization_valid_until: Mapped[datetime | None] = mapped_column(DateTime)
    decision_maker_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    is_fid: Mapped[bool] = mapped_column(Boolean, default=False)
    full_funds_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    investment_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    decision_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    decide_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    decide_payload_hash: Mapped[str | None] = mapped_column(String(64))
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "decision_number", name="uq_investment_decision_number"),
        UniqueConstraint(
            "tenant_id",
            "investment_gate_preparation_id",
            "profile_code",
            "decision_round",
            name="uq_investment_decision_preparation_round",
        ),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_investment_decision_create_key"),
        UniqueConstraint("tenant_id", "decide_idempotency_key", name="uq_investment_decision_decide_key"),
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','IN_REVIEW','READY_FOR_DECISION','DECIDED','VOIDED')",
            name="ck_investment_decision_status",
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('GO','HOLD','RECYCLE','KILL')",
            name="ck_investment_decision_outcome",
        ),
        CheckConstraint(
            "(status = 'DECIDED' AND outcome IS NOT NULL AND decided_at IS NOT NULL AND decision_hash IS NOT NULL) "
            "OR (status != 'DECIDED' AND outcome IS NULL)",
            name="ck_investment_decision_closed_fields",
        ),
        CheckConstraint(
            "is_fid = false OR (profile_code = 'PYP-FFA' AND outcome = 'GO' AND full_funds_authorized = true "
            "AND investment_authorized = true)",
            name="ck_investment_decision_fid_semantics",
        ),
        CheckConstraint(
            "outcome != 'HOLD' OR hold_reason IS NOT NULL",
            name="ck_investment_decision_hold_reason",
        ),
        CheckConstraint(
            "outcome != 'RECYCLE' OR recycle_target IS NOT NULL",
            name="ck_investment_decision_recycle_target",
        ),
        CheckConstraint(
            "outcome != 'KILL' OR length(rationale) > 0",
            name="ck_investment_decision_kill_rationale",
        ),
        Index(
            "uq_investment_decision_active_preparation_profile",
            "tenant_id",
            "investment_gate_preparation_id",
            "profile_code",
            unique=True,
            postgresql_where=text("status IN ('DRAFT','SUBMITTED','IN_REVIEW','READY_FOR_DECISION')"),
            sqlite_where=text("status IN ('DRAFT','SUBMITTED','IN_REVIEW','READY_FOR_DECISION')"),
        ),
        Index("ix_investment_decision_queue", "tenant_id", "status", "profile_code", "updated_at"),
        Index("ix_investment_decision_history", "tenant_id", "portfolio_workspace_id", "decided_at"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class InvestmentDecisionVote(Base):
    __tablename__ = "investment_decision_votes"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    investment_decision_id: Mapped[int] = mapped_column(ForeignKey("investment_decisions.id"), index=True)
    voter_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    vote: Mapped[str] = mapped_column(String(16))
    rationale: Mapped[str] = mapped_column(Text, default="")
    cast_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    idempotency_key: Mapped[str | None] = mapped_column(String(160))
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "investment_decision_id", "voter_user_id", name="uq_investment_vote_member"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_investment_vote_key"),
        CheckConstraint(
            "vote IN ('GO','HOLD','RECYCLE','KILL','ABSTAIN')",
            name="ck_investment_vote_value",
        ),
        Index("ix_investment_vote_decision_cast", "tenant_id", "investment_decision_id", "cast_at"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


@event.listens_for(InvestmentDecision, "before_update")
def _protect_closed_decision(_mapper, _connection, target: InvestmentDecision) -> None:
    state = inspect(target)
    prior = state.attrs.status.history.deleted[0] if state.attrs.status.history.deleted else target.status
    if prior in {"DECIDED", "VOIDED"} and any(item.history.has_changes() for item in state.attrs):
        raise ValueError("Decided and voided Investment Decisions are immutable")


@event.listens_for(InvestmentDecision, "before_delete")
def _protect_decision_delete(_mapper, _connection, _target: InvestmentDecision) -> None:
    raise ValueError("Investment Decisions cannot be physically deleted")


def _protect_vote(_mapper, connection, target: InvestmentDecisionVote) -> None:
    status = connection.execute(
        InvestmentDecision.__table__.select()
        .with_only_columns(InvestmentDecision.status)
        .where(InvestmentDecision.id == target.investment_decision_id)
    ).scalar_one_or_none()
    if status in {"DECIDED", "VOIDED"}:
        raise ValueError("Votes of a closed Investment Decision are immutable")


event.listen(InvestmentDecisionVote, "before_update", _protect_vote)
event.listen(InvestmentDecisionVote, "before_delete", _protect_vote)
