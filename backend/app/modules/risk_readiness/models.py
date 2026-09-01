"""Tenant-scoped persistence for Project Risk and Risk Readiness."""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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


class ProjectRisk(Base):
    __tablename__ = "project_risks"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    risk_number: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    risk_category: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    identified_date: Mapped[date] = mapped_column(Date)
    risk_owner_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    cause: Mapped[str] = mapped_column(Text, default="")
    event: Mapped[str] = mapped_column(Text, default="")
    impact_description: Mapped[str] = mapped_column(Text, default="")
    likelihood_before: Mapped[int | None] = mapped_column(Integer)
    impact_before: Mapped[int | None] = mapped_column(Integer)
    inherent_rating: Mapped[str | None] = mapped_column(String(20), index=True)
    treatment_required: Mapped[bool] = mapped_column(default=False)
    treatment_strategy: Mapped[str | None] = mapped_column(String(24))
    treatment_description: Mapped[str | None] = mapped_column(Text)
    treatment_owner_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    target_treatment_date: Mapped[date | None] = mapped_column(Date, index=True)
    treatment_status: Mapped[str | None] = mapped_column(String(24))
    likelihood_after: Mapped[int | None] = mapped_column(Integer)
    impact_after: Mapped[int | None] = mapped_column(Integer)
    residual_rating: Mapped[str | None] = mapped_column(String(20), index=True)
    residual_acceptance_required: Mapped[bool] = mapped_column(default=False)
    accepted_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    acceptance_comment: Mapped[str | None] = mapped_column(Text)
    acceptance_authority_level: Mapped[str | None] = mapped_column(String(80))
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    source_reference: Mapped[str | None] = mapped_column(String(300))
    evidence_refs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    acceptance_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "risk_number", name="uq_project_risk_number"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_project_risk_create_key"),
        UniqueConstraint("tenant_id", "acceptance_idempotency_key", name="uq_project_risk_accept_key"),
        CheckConstraint(
            "status IN ('DRAFT','OPEN','UNDER_TREATMENT','MONITORING','CLOSED','VOIDED')",
            name="ck_project_risk_status",
        ),
        CheckConstraint(
            "treatment_strategy IS NULL OR treatment_strategy IN ('AVOID','REDUCE','TRANSFER','ACCEPT')",
            name="ck_project_risk_treatment_strategy",
        ),
        CheckConstraint(
            "treatment_status IS NULL OR treatment_status IN ('OPEN','IN_PROGRESS','COMPLETED','CANCELLED')",
            name="ck_project_risk_treatment_status",
        ),
        CheckConstraint(
            "likelihood_before IS NULL OR likelihood_before BETWEEN 1 AND 5",
            name="ck_project_risk_likelihood_before",
        ),
        CheckConstraint(
            "impact_before IS NULL OR impact_before BETWEEN 1 AND 5",
            name="ck_project_risk_impact_before",
        ),
        CheckConstraint(
            "likelihood_after IS NULL OR likelihood_after BETWEEN 1 AND 5",
            name="ck_project_risk_likelihood_after",
        ),
        CheckConstraint(
            "impact_after IS NULL OR impact_after BETWEEN 1 AND 5",
            name="ck_project_risk_impact_after",
        ),
        CheckConstraint(
            "(accepted_by IS NULL AND accepted_at IS NULL) OR (accepted_by IS NOT NULL AND accepted_at IS NOT NULL)",
            name="ck_project_risk_acceptance_pair",
        ),
        Index("ix_project_risk_tenant_project_status", "tenant_id", "project_workspace_id", "status"),
        Index("ix_project_risk_readiness_scan", "tenant_id", "project_workspace_id", "inherent_rating"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class RiskReadinessAssessment(Base):
    __tablename__ = "risk_readiness_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    assessment_number: Mapped[str] = mapped_column(String(40))
    assessment_version: Mapped[int] = mapped_column(Integer, default=1)
    as_of_date: Mapped[datetime] = mapped_column(DateTime)
    valid_until: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(24), default="IN_PROGRESS", index=True)
    risk_register_hash: Mapped[str] = mapped_column(String(64), index=True)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64), index=True)
    total_active_risks: Mapped[int] = mapped_column(Integer, default=0)
    high_risk_count: Mapped[int] = mapped_column(Integer, default=0)
    critical_risk_count: Mapped[int] = mapped_column(Integer, default=0)
    risks_without_owner: Mapped[int] = mapped_column(Integer, default=0)
    risks_without_treatment: Mapped[int] = mapped_column(Integer, default=0)
    overdue_treatments: Mapped[int] = mapped_column(Integer, default=0)
    residual_high_count: Mapped[int] = mapped_column(Integer, default=0)
    residual_critical_count: Mapped[int] = mapped_column(Integer, default=0)
    risks_requiring_acceptance: Mapped[int] = mapped_column(Integer, default=0)
    risks_without_acceptance: Mapped[int] = mapped_column(Integer, default=0)
    evidence_coverage_percent: Mapped[float] = mapped_column(default=0)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    blockers_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    readiness_status: Mapped[str] = mapped_column(String(16), default="BLOCKED", index=True)
    risk_readiness_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    assessed_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    complete_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    reassessment_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    refresh_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "assessment_number", name="uq_risk_readiness_assessment_number"),
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "assessment_version", name="uq_risk_readiness_project_version"
        ),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_risk_readiness_create_key"),
        UniqueConstraint("tenant_id", "complete_idempotency_key", name="uq_risk_readiness_complete_key"),
        UniqueConstraint("tenant_id", "reassessment_idempotency_key", name="uq_risk_readiness_reassess_key"),
        UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_risk_readiness_refresh_key"),
        CheckConstraint(
            "status IN ('DRAFT','IN_PROGRESS','COMPLETED','SUPERSEDED','VOIDED')",
            name="ck_risk_readiness_assessment_status",
        ),
        CheckConstraint(
            "readiness_status IN ('NOT_STARTED','READY','BLOCKED','STALE','EXPIRED')",
            name="ck_risk_readiness_status",
        ),
        CheckConstraint(
            "status != 'COMPLETED' OR (completed_by IS NOT NULL AND completed_at IS NOT NULL AND risk_readiness_hash IS NOT NULL)",
            name="ck_risk_readiness_completed",
        ),
        CheckConstraint(
            "evidence_coverage_percent >= 0 AND evidence_coverage_percent <= 100",
            name="ck_risk_readiness_coverage",
        ),
        Index("ix_risk_readiness_tenant_project_status", "tenant_id", "project_workspace_id", "status"),
        Index(
            "uq_risk_readiness_active_project",
            "tenant_id",
            "project_workspace_id",
            unique=True,
            postgresql_where=text("status IN ('DRAFT','IN_PROGRESS')"),
            sqlite_where=text("status IN ('DRAFT','IN_PROGRESS')"),
        ),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


@event.listens_for(RiskReadinessAssessment, "before_update")
def _protect_completed_assessment(_mapper, _connection, record: RiskReadinessAssessment) -> None:
    state = inspect(record)
    previous = state.attrs.status.history.deleted[0] if state.attrs.status.history.deleted else record.status
    if previous in {"COMPLETED", "SUPERSEDED", "VOIDED"} and any(
        attribute.history.has_changes() for attribute in state.attrs
    ):
        raise ValueError("Completed, superseded and voided Risk Readiness Assessments are immutable")


@event.listens_for(RiskReadinessAssessment, "before_delete")
def _protect_assessment_delete(_mapper, _connection, record: RiskReadinessAssessment) -> None:
    if record.status in {"COMPLETED", "SUPERSEDED", "VOIDED"}:
        raise ValueError("Completed, superseded and voided Risk Readiness Assessments cannot be deleted")
