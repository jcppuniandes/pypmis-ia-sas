"""Tenant-scoped persistence for Gate 07J Investment Gate Preparation."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class InvestmentGatePreparation(Base):
    __tablename__ = "investment_gate_preparations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    portfolio_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    preparation_number: Mapped[str] = mapped_column(String(120))
    logical_code: Mapped[str] = mapped_column(String(120), default="INVESTMENT-GATE-PREPARATION")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    investment_gate_profile_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    profile_code: Mapped[str] = mapped_column(String(120), index=True)
    profile_revision: Mapped[int] = mapped_column(Integer)
    profile_hash: Mapped[str] = mapped_column(String(64))
    source_convergence_id: Mapped[int] = mapped_column(ForeignKey("portfolio_scenario_convergences.id"), index=True)
    source_convergence_revision: Mapped[int] = mapped_column(Integer)
    source_recommendation_hash: Mapped[str] = mapped_column(String(64), index=True)
    recommended_alternative_id: Mapped[int] = mapped_column(
        ForeignKey("portfolio_converged_alternatives.id"), index=True
    )
    recommended_project_set_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    readiness_status: Mapped[str] = mapped_column(String(16), default="BLOCKED", index=True)
    source_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    conditions_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    blockers_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    preparation_source_hash: Mapped[str] = mapped_column(String(64), index=True)
    preparation_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    refresh_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    ready_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    freeze_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    clone_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    void_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    frozen_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("tenant_id", "preparation_number", name="uq_investment_gate_preparation_number"),
        UniqueConstraint(
            "tenant_id",
            "portfolio_workspace_id",
            "logical_code",
            "revision",
            name="uq_investment_gate_preparation_revision",
        ),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_investment_gate_create_key"),
        UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_investment_gate_refresh_key"),
        UniqueConstraint("tenant_id", "ready_idempotency_key", name="uq_investment_gate_ready_key"),
        UniqueConstraint("tenant_id", "freeze_idempotency_key", name="uq_investment_gate_freeze_key"),
        UniqueConstraint("tenant_id", "clone_idempotency_key", name="uq_investment_gate_clone_key"),
        UniqueConstraint("tenant_id", "void_idempotency_key", name="uq_investment_gate_void_key"),
        CheckConstraint(
            "status IN ('DRAFT','IN_PREPARATION','READY_FOR_REVIEW','FROZEN','SUPERSEDED','VOIDED')",
            name="ck_investment_gate_preparation_status",
        ),
        CheckConstraint(
            "readiness_status IN ('READY','BLOCKED','STALE')",
            name="ck_investment_gate_preparation_readiness",
        ),
        CheckConstraint(
            "status != 'FROZEN' OR (readiness_status = 'READY' AND preparation_hash IS NOT NULL)",
            name="ck_investment_gate_frozen_package",
        ),
        Index("ix_investment_gate_tenant_portfolio", "tenant_id", "portfolio_workspace_id"),
        Index("ix_investment_gate_tenant_status", "tenant_id", "status", "readiness_status"),
        Index(
            "ix_investment_gate_source_profile",
            "tenant_id",
            "source_convergence_id",
            "investment_gate_profile_id",
        ),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class InvestmentGateEvidenceItem(Base):
    __tablename__ = "investment_gate_evidence_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    preparation_id: Mapped[int] = mapped_column(ForeignKey("investment_gate_preparations.id"), index=True)
    requirement_key: Mapped[str] = mapped_column(String(160), index=True)
    evidence_type: Mapped[str] = mapped_column(String(80), index=True)
    scope_type: Mapped[str] = mapped_column(String(40))
    scope_id: Mapped[int | None] = mapped_column(Integer, index=True)
    scope_key: Mapped[str] = mapped_column(String(120))
    evidence_revision: Mapped[int] = mapped_column(Integer, default=1)
    evidence_origin: Mapped[str] = mapped_column(String(32))
    source_module: Mapped[str | None] = mapped_column(String(120))
    source_record_id: Mapped[str | None] = mapped_column(String(180))
    source_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    scope_reference_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), default="MISSING", index=True)
    evidence_date: Mapped[datetime | None] = mapped_column(DateTime)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    issuer: Mapped[str | None] = mapped_column(String(180))
    owner: Mapped[str | None] = mapped_column(String(180))
    summary: Mapped[str] = mapped_column(Text, default="")
    evidence_refs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    submitted_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    validated_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime)
    validation_note: Mapped[str | None] = mapped_column(Text)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    blockers_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    add_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    validate_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "preparation_id",
            "requirement_key",
            "scope_key",
            "evidence_revision",
            name="uq_investment_gate_evidence_revision",
        ),
        UniqueConstraint("tenant_id", "add_idempotency_key", name="uq_investment_gate_evidence_add_key"),
        UniqueConstraint("tenant_id", "validate_idempotency_key", name="uq_investment_gate_evidence_validate_key"),
        CheckConstraint(
            "evidence_origin IN ('GOVERNED_SOURCE','MANUAL_REFERENCE')",
            name="ck_investment_gate_evidence_origin",
        ),
        CheckConstraint(
            "scope_type IN ('PORTFOLIO','PROJECT_SET','EACH_PROJECT','SELECTED_PROJECTS_ONLY')",
            name="ck_investment_gate_evidence_scope",
        ),
        CheckConstraint(
            "status IN ('NOT_AVAILABLE','MISSING','DRAFT','SUBMITTED','VALID','INVALID','EXPIRED','STALE','NOT_REQUIRED')",
            name="ck_investment_gate_evidence_status",
        ),
        Index("ix_investment_gate_evidence_lookup", "tenant_id", "preparation_id", "requirement_key"),
        Index("ix_investment_gate_evidence_status", "tenant_id", "preparation_id", "status"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


@event.listens_for(InvestmentGatePreparation, "before_update")
def _protect_frozen_preparation(_mapper, _connection, record: InvestmentGatePreparation) -> None:
    state = inspect(record)
    previous = state.attrs.status.history.deleted[0] if state.attrs.status.history.deleted else record.status
    if previous in {"FROZEN", "SUPERSEDED", "VOIDED"} and any(
        attribute.history.has_changes() for attribute in state.attrs
    ):
        raise ValueError("Frozen, superseded and voided Investment Gate Preparations are immutable")


def _protect_evidence(_mapper, connection, record: InvestmentGateEvidenceItem) -> None:
    status = connection.execute(
        InvestmentGatePreparation.__table__.select()
        .with_only_columns(InvestmentGatePreparation.status)
        .where(InvestmentGatePreparation.id == record.preparation_id)
    ).scalar_one_or_none()
    if status in {"FROZEN", "SUPERSEDED", "VOIDED"}:
        raise ValueError("Evidence of a frozen, superseded or voided preparation is immutable")


event.listen(InvestmentGateEvidenceItem, "before_update", _protect_evidence)
event.listen(InvestmentGateEvidenceItem, "before_delete", _protect_evidence)
