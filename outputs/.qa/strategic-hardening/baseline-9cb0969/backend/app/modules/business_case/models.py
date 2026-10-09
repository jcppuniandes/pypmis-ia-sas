"""Persistence for the governed longitudinal Business Case aggregate.

Only the aggregate root, its revisions and immutable decision snapshots are
owned here.  Evidence remains owned by the upstream Gate 07F-07L providers.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class BusinessCase(Base):
    __tablename__ = "business_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    business_case_number: Mapped[str] = mapped_column(String(40), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    source_project_proposal_id: Mapped[int | None] = mapped_column(ForeignKey("project_proposals.id"), index=True)
    owning_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    sponsor_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    current_revision_id: Mapped[int | None] = mapped_column(Integer, index=True)
    material_change_review_json: Mapped[dict] = mapped_column(JSON, default=dict)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64), index=True)
    configuration_source_workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("enterprise_workspaces.id"), index=True
    )
    configuration_resolution_chain_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "business_case_number", name="uq_business_case_number"),
        UniqueConstraint("tenant_id", "project_workspace_id", name="uq_business_case_project"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_business_case_create_key"),
        CheckConstraint(
            "status IN ('DRAFT','ACTIVE','ON_HOLD','CLOSED','ARCHIVED')",
            name="ck_business_case_status",
        ),
        Index("ix_business_case_queue", "tenant_id", "status", "updated_at"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class BusinessCaseRevision(Base):
    __tablename__ = "business_case_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    business_case_id: Mapped[int] = mapped_column(ForeignKey("business_cases.id"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    revision_label: Mapped[str] = mapped_column(String(20))
    purpose: Mapped[str] = mapped_column(String(48), index=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    as_of_date: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    fel_stage_code: Mapped[str | None] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(240))
    executive_summary: Mapped[str] = mapped_column(Text, default="")
    business_need: Mapped[str] = mapped_column(Text, default="")
    strategic_alignment_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    objectives_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    scope_json: Mapped[dict] = mapped_column(JSON, default=dict)
    alternatives_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    benefits_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    assumptions_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    constraints_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    delivery_json: Mapped[dict] = mapped_column(JSON, default=dict)
    unresolved_concerns_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    recommendation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_references_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_hashes_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    economic_financial_model_id: Mapped[int | None] = mapped_column(Integer, index=True)
    economic_financial_model_version: Mapped[int | None] = mapped_column(Integer)
    economic_financial_model_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    financial_model_status: Mapped[str] = mapped_column(String(24), default="NOT_AVAILABLE")
    economic_financial_readiness: Mapped[str | None] = mapped_column(String(32))
    economic_financial_as_of_date: Mapped[datetime | None] = mapped_column(DateTime)
    npv: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    irr: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    payback_period: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    benefit_cost_ratio: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    readiness_status: Mapped[str] = mapped_column(String(20), default="NOT_STARTED", index=True)
    readiness_warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    readiness_blockers_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    readiness_hash: Mapped[str] = mapped_column(String(64), index=True)
    material_change_status: Mapped[str] = mapped_column(String(40), default="NO_MATERIAL_CHANGE", index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    preparer_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    reviewer_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    complete_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    refresh_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "business_case_id", "revision_number", name="uq_business_case_revision"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_business_case_revision_create_key"),
        UniqueConstraint("tenant_id", "complete_idempotency_key", name="uq_business_case_revision_complete_key"),
        UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_business_case_revision_refresh_key"),
        CheckConstraint("revision_number > 0", name="ck_business_case_revision_number"),
        CheckConstraint(
            "status IN ('DRAFT','IN_REVIEW','COMPLETED','SUPERSEDED','VOIDED')",
            name="ck_business_case_revision_status",
        ),
        CheckConstraint(
            "purpose IN ('INITIAL_PROPOSAL','FEL_1_UPDATE','FEL_2_UPDATE','INVESTMENT_SELECTION_UPDATE',"
            "'FEL_3_UPDATE','FFA_UPDATE','MATERIAL_CHANGE_UPDATE','REVALIDATION','OTHER')",
            name="ck_business_case_revision_purpose",
        ),
        CheckConstraint(
            "readiness_status IN ('NOT_STARTED','READY','BLOCKED','STALE','EXPIRED')",
            name="ck_business_case_revision_readiness",
        ),
        CheckConstraint(
            "material_change_status IN ('NO_MATERIAL_CHANGE','MATERIAL_CHANGE_REVIEW_REQUIRED')",
            name="ck_business_case_material_change",
        ),
        CheckConstraint(
            "financial_model_status IN ('NOT_AVAILABLE','AVAILABLE','STALE')",
            name="ck_business_case_financial_status",
        ),
        Index("ix_business_case_revision_latest", "tenant_id", "business_case_id", "revision_number"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class BusinessCaseDecisionSnapshot(Base):
    __tablename__ = "business_case_decision_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    business_case_id: Mapped[int] = mapped_column(ForeignKey("business_cases.id"), index=True)
    business_case_revision_id: Mapped[int] = mapped_column(ForeignKey("business_case_revisions.id"), index=True)
    snapshot_type: Mapped[str] = mapped_column(String(48), index=True)
    decision_reference_type: Mapped[str | None] = mapped_column(String(80))
    decision_reference_id: Mapped[int | None] = mapped_column(Integer, index=True)
    decision_reference_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    revision_content_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_business_case_snapshot_key"),
        UniqueConstraint(
            "tenant_id", "business_case_revision_id", "snapshot_type", name="uq_business_case_revision_snapshot_type"
        ),
        CheckConstraint(
            "snapshot_type IN ('INVESTMENT_SELECTION','FULL_FUNDS_AUTHORIZATION','OTHER_CONFIGURED_GATE')",
            name="ck_business_case_snapshot_type",
        ),
        Index("ix_business_case_snapshot_history", "tenant_id", "business_case_id", "created_at"),
    )


def _protect_terminal_revision(_mapper, _connection, target: BusinessCaseRevision) -> None:
    state = inspect(target)
    previous = state.attrs.status.history.deleted
    original_status = previous[0] if previous else target.status
    if original_status in {"COMPLETED", "SUPERSEDED", "VOIDED"}:
        raise ValueError("Terminal Business Case revisions are immutable")


def _immutable_snapshot(_mapper, _connection, _target: BusinessCaseDecisionSnapshot) -> None:
    raise ValueError("Business Case decision snapshots are immutable")


event.listen(BusinessCaseRevision, "before_update", _protect_terminal_revision)
event.listen(BusinessCaseDecisionSnapshot, "before_update", _immutable_snapshot)
event.listen(BusinessCaseDecisionSnapshot, "before_delete", _immutable_snapshot)
