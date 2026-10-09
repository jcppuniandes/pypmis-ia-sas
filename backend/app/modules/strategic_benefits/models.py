"""Persistence for governed Strategic Benefits Plans and stable Benefits.

The Plan and Benefit identities are longitudinal.  Version snapshots and their
measures carry the mutable planning content so completed history can never be
rewritten and future Benefits Realization can keep using the same BEN number.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
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
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class StrategicBenefitsPlan(Base):
    """One stable governed Benefits Plan identity per Project Workspace."""

    __tablename__ = "strategic_benefits_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    plan_number: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    current_version_id: Mapped[int | None] = mapped_column(Integer, index=True)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64), index=True)
    configuration_source_workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("enterprise_workspaces.id"), index=True
    )
    configuration_resolution_chain_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    create_idempotency_key: Mapped[str] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", name="uq_benefits_plan_project"),
        UniqueConstraint("tenant_id", "plan_number", name="uq_benefits_plan_number"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_benefits_plan_create_key"),
        CheckConstraint(
            "status IN ('DRAFT','IN_REVIEW','COMPLETED','SUPERSEDED','VOIDED')",
            name="ck_benefits_plan_status",
        ),
        Index("ix_benefits_plan_queue", "tenant_id", "status", "updated_at", "id"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class StrategicBenefitsPlanVersion(Base):
    """Controlled Plan version; completed content is immutable."""

    __tablename__ = "strategic_benefits_plan_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    benefits_plan_id: Mapped[int] = mapped_column(ForeignKey("strategic_benefits_plans.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    version_purpose: Mapped[str] = mapped_column(String(48), index=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    fel_stage_code: Mapped[str | None] = mapped_column(String(32), index=True)
    overview_json: Mapped[dict] = mapped_column(JSON, default=dict)
    outputs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    outcomes_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    assumptions_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    constraints_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    readiness_json: Mapped[dict] = mapped_column(JSON, default=dict)
    readiness_status: Mapped[str] = mapped_column(String(24), default="NOT_STARTED", index=True)
    readiness_warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    readiness_blockers_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_references_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_hashes_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_bundle_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    benefit_set_hash: Mapped[str] = mapped_column(String(64), index=True)
    traceability_hash: Mapped[str] = mapped_column(String(64), index=True)
    benefits_plan_hash: Mapped[str] = mapped_column(String(64), index=True)
    preparer_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    reviewer_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    return_reason: Mapped[str | None] = mapped_column(Text)
    void_reason: Mapped[str | None] = mapped_column(Text)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    submit_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    review_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    return_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    complete_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    void_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    refresh_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "benefits_plan_id", "version_number", name="uq_benefits_plan_version"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_benefits_version_create_key"),
        UniqueConstraint("tenant_id", "submit_idempotency_key", name="uq_benefits_version_submit_key"),
        UniqueConstraint("tenant_id", "review_idempotency_key", name="uq_benefits_version_review_key"),
        UniqueConstraint("tenant_id", "return_idempotency_key", name="uq_benefits_version_return_key"),
        UniqueConstraint("tenant_id", "complete_idempotency_key", name="uq_benefits_version_complete_key"),
        UniqueConstraint("tenant_id", "void_idempotency_key", name="uq_benefits_version_void_key"),
        UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_benefits_version_refresh_key"),
        CheckConstraint("version_number > 0", name="ck_benefits_version_number"),
        CheckConstraint(
            "status IN ('DRAFT','IN_REVIEW','COMPLETED','SUPERSEDED','VOIDED')",
            name="ck_benefits_version_status",
        ),
        CheckConstraint(
            "readiness_status IN ('NOT_STARTED','IN_PROGRESS','READY','BLOCKED','STALE','NOT_APPLICABLE')",
            name="ck_benefits_version_readiness",
        ),
        Index("ix_benefits_version_history", "tenant_id", "benefits_plan_id", "version_number"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class StrategicBenefit(Base):
    """Stable Benefit identity reused by every Plan version and future BRM."""

    __tablename__ = "strategic_benefits"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    benefits_plan_id: Mapped[int] = mapped_column(ForeignKey("strategic_benefits_plans.id"), index=True)
    benefit_number: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", index=True)
    create_idempotency_key: Mapped[str] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "benefit_number", name="uq_strategic_benefit_number"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_strategic_benefit_create_key"),
        CheckConstraint("status IN ('ACTIVE','RETIRED')", name="ck_strategic_benefit_status"),
        Index("ix_strategic_benefit_plan", "tenant_id", "benefits_plan_id", "id"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class StrategicBenefitVersionSnapshot(Base):
    """Frozen version-specific content for a stable Benefit identity."""

    __tablename__ = "strategic_benefit_version_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    plan_version_id: Mapped[int] = mapped_column(ForeignKey("strategic_benefits_plan_versions.id"), index=True)
    strategic_benefit_id: Mapped[int] = mapped_column(ForeignKey("strategic_benefits.id"), index=True)
    benefit_name: Mapped[str] = mapped_column(String(240))
    benefit_description: Mapped[str] = mapped_column(Text, default="")
    benefit_direction: Mapped[str] = mapped_column(String(24), default="BENEFIT")
    benefit_type: Mapped[str] = mapped_column(String(80), index=True)
    benefit_category: Mapped[str | None] = mapped_column(String(120), index=True)
    strategic_objective_refs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    source_need_reference_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_business_analysis_reference_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_project_proposal_reference_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_business_case_reference_json: Mapped[dict] = mapped_column(JSON, default=dict)
    expected_outputs_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    expected_outcomes_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    benefit_statement: Mapped[str] = mapped_column(Text, default="")
    owner_type: Mapped[str | None] = mapped_column(String(32), index=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    owner_organization_unit_id: Mapped[int | None] = mapped_column(ForeignKey("organization_units.id"), index=True)
    owner_security_role_id: Mapped[int | None] = mapped_column(ForeignKey("security_roles.id"), index=True)
    owner_reference: Mapped[str | None] = mapped_column(String(180))
    owner_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    owner_effective_from: Mapped[date | None] = mapped_column(Date)
    owner_effective_to: Mapped[date | None] = mapped_column(Date)
    accountability_statement: Mapped[str] = mapped_column(Text, default="")
    owner_acceptance_status: Mapped[str | None] = mapped_column(String(32))
    expected_value_json: Mapped[dict] = mapped_column(JSON, default=dict)
    monetizable_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    dependencies_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    assumptions_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    constraints_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    risk_references_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", index=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "plan_version_id", "strategic_benefit_id", name="uq_benefit_snapshot"),
        CheckConstraint("benefit_direction IN ('BENEFIT','DISBENEFIT')", name="ck_benefit_direction"),
        CheckConstraint("status IN ('ACTIVE','REMOVED')", name="ck_benefit_snapshot_status"),
        CheckConstraint(
            "owner_type IS NULL OR owner_type IN ('USER','ORGANIZATION_UNIT','SECURITY_ROLE','EXTERNAL_REFERENCE')",
            name="ck_benefit_owner_type",
        ),
        Index("ix_benefit_snapshot_matrix", "tenant_id", "plan_version_id", "status", "id"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class StrategicBenefitMeasure(Base):
    """Version-specific measure; an UNKNOWN baseline is represented by NULL."""

    __tablename__ = "strategic_benefit_measures"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    benefit_snapshot_id: Mapped[int] = mapped_column(ForeignKey("strategic_benefit_version_snapshots.id"), index=True)
    measure_code: Mapped[str] = mapped_column(String(80))
    measure_name: Mapped[str] = mapped_column(String(180))
    definition: Mapped[str] = mapped_column(Text, default="")
    unit_of_measure: Mapped[str] = mapped_column(String(80))
    direction: Mapped[str] = mapped_column(String(32))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    baseline_status: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    baseline_value_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    baseline_as_of_date: Mapped[date | None] = mapped_column(Date)
    baseline_source: Mapped[str | None] = mapped_column(String(240))
    baseline_evidence_reference: Mapped[str | None] = mapped_column(String(500))
    baseline_confidence: Mapped[str | None] = mapped_column(String(40))
    target_value_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date)
    target_basis: Mapped[str | None] = mapped_column(Text)
    tolerance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    measurement_method: Mapped[str] = mapped_column(Text, default="")
    measurement_frequency: Mapped[str | None] = mapped_column(String(80))
    data_source_description: Mapped[str | None] = mapped_column(Text)
    measurement_owner_reference_json: Mapped[dict] = mapped_column(JSON, default=dict)
    measure_hash: Mapped[str] = mapped_column(String(64), index=True)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "benefit_snapshot_id", "measure_code", name="uq_benefit_measure_code"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_benefit_measure_create_key"),
        CheckConstraint(
            "direction IN ('INCREASE','DECREASE','MAINTAIN_ABOVE','MAINTAIN_BELOW','BINARY_ACHIEVEMENT')",
            name="ck_benefit_measure_direction",
        ),
        CheckConstraint("baseline_status IN ('KNOWN','UNKNOWN')", name="ck_benefit_baseline_status"),
        Index("ix_benefit_measure_snapshot", "tenant_id", "benefit_snapshot_id", "is_primary", "id"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


def _terminal_guard(target, label: str) -> None:
    state = inspect(target)
    previous = state.attrs.status.history.deleted[0] if state.attrs.status.history.deleted else target.status
    if previous not in {"COMPLETED", "SUPERSEDED", "VOIDED"}:
        return
    changed = {attribute.key for attribute in state.attrs if attribute.history.has_changes()}
    if previous == "COMPLETED" and target.status == "SUPERSEDED" and changed <= {"status", "updated_at"}:
        return
    if changed:
        raise ValueError(f"Terminal {label} versions are immutable; create a new DRAFT version")


@event.listens_for(StrategicBenefitsPlanVersion, "before_update")
def _protect_terminal_version(_mapper, _connection, target: StrategicBenefitsPlanVersion) -> None:
    _terminal_guard(target, "Strategic Benefits Plan")


@event.listens_for(StrategicBenefitsPlanVersion, "before_delete")
def _protect_version_delete(_mapper, _connection, _target: StrategicBenefitsPlanVersion) -> None:
    raise ValueError("Strategic Benefits Plan versions cannot be physically deleted")


@event.listens_for(StrategicBenefit, "before_delete")
def _protect_benefit_delete(_mapper, _connection, _target: StrategicBenefit) -> None:
    raise ValueError("Stable Benefit identities cannot be physically deleted")


def _snapshot_version_status(connection, snapshot: StrategicBenefitVersionSnapshot) -> str | None:
    return connection.execute(
        select(StrategicBenefitsPlanVersion.status).where(StrategicBenefitsPlanVersion.id == snapshot.plan_version_id)
    ).scalar_one_or_none()


def _measure_version_status(connection, measure: StrategicBenefitMeasure) -> str | None:
    version_id = connection.execute(
        select(StrategicBenefitVersionSnapshot.plan_version_id).where(
            StrategicBenefitVersionSnapshot.id == measure.benefit_snapshot_id
        )
    ).scalar_one_or_none()
    if version_id is None:
        return None
    return connection.execute(
        select(StrategicBenefitsPlanVersion.status).where(StrategicBenefitsPlanVersion.id == version_id)
    ).scalar_one_or_none()


def _protect_snapshot_write(_mapper, connection, target: StrategicBenefitVersionSnapshot) -> None:
    if _snapshot_version_status(connection, target) in {"COMPLETED", "SUPERSEDED", "VOIDED"}:
        raise ValueError("Terminal Benefits Plan snapshots are immutable; create a new DRAFT version")


def _protect_measure_write(_mapper, connection, target: StrategicBenefitMeasure) -> None:
    if _measure_version_status(connection, target) in {"COMPLETED", "SUPERSEDED", "VOIDED"}:
        raise ValueError("Terminal Benefit measures are immutable; create a new DRAFT version")


for _event_name in ("before_insert", "before_update"):
    event.listen(StrategicBenefitVersionSnapshot, _event_name, _protect_snapshot_write)
    event.listen(StrategicBenefitMeasure, _event_name, _protect_measure_write)


@event.listens_for(StrategicBenefitVersionSnapshot, "before_delete")
@event.listens_for(StrategicBenefitMeasure, "before_delete")
def _protect_versioned_content_delete(_mapper, _connection, _target) -> None:
    raise ValueError("Benefit snapshots and measures cannot be physically deleted")


@event.listens_for(StrategicBenefitsPlan, "before_delete")
def _protect_plan_delete(_mapper, _connection, _target: StrategicBenefitsPlan) -> None:
    raise ValueError("Strategic Benefits Plan identities cannot be physically deleted")
