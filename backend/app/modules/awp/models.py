"""Small canonical execution aggregates. Sources stay in Scope and Schedule."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base
from app.domain.models import AdminConfiguration
from app.modules.scope_foundation.models import ScopeRecord


class MutableExecution:
    revision: Mapped[int] = mapped_column(default=1)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class CWA(MutableExecution, ScopeRecord, Base):
    __tablename__ = "awp_cwas"
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    area: Mapped[str] = mapped_column(String(150), default="")
    zone: Mapped[str] = mapped_column(String(150), default="")
    location: Mapped[str] = mapped_column(String(260), default="")
    parent_cwa_id: Mapped[int | None] = mapped_column(ForeignKey("awp_cwas.id"))
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE")
    __table_args__ = (UniqueConstraint("tenant_id", "project_workspace_id", "code", name="uq_awp_cwa_code"),)


class WorkPackage(MutableExecution, ScopeRecord, Base):
    __tablename__ = "awp_work_packages"
    package_code: Mapped[str] = mapped_column(String(120))
    package_type: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    cwa_id: Mapped[int | None] = mapped_column(ForeignKey("awp_cwas.id"))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    responsible_role: Mapped[str] = mapped_column(String(120), default="Workface Planner")
    readiness_state: Mapped[str] = mapped_column(String(30), default="NOT_ASSESSED")
    release_state: Mapped[str] = mapped_column(String(30), default="NOT_RELEASED")
    released_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    released_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "package_code", name="uq_awp_package_code"),
    )


class PackageMapping(ScopeRecord, Base):
    __tablename__ = "awp_package_mappings"
    work_package_id: Mapped[int] = mapped_column(ForeignKey("awp_work_packages.id"), index=True)
    target_kind: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[int | None] = mapped_column()
    schedule_version_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_versions.id"))
    activity_external_id: Mapped[str | None] = mapped_column(String(160))
    phase: Mapped[str] = mapped_column(String(20), default="EXECUTE")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    revision: Mapped[int] = mapped_column(default=1)
    lineage_json: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text)


class PackageDependency(MutableExecution, ScopeRecord, Base):
    __tablename__ = "awp_package_dependencies"
    predecessor_package_id: Mapped[int] = mapped_column(ForeignKey("awp_work_packages.id"), index=True)
    successor_package_id: Mapped[int] = mapped_column(ForeignKey("awp_work_packages.id"), index=True)
    dependency_type: Mapped[str] = mapped_column(String(80))
    blocking: Mapped[bool] = mapped_column(Boolean, default=True)
    evidence_reference: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    reason: Mapped[str] = mapped_column(Text)


class ExecutionConstraint(MutableExecution, ScopeRecord, Base):
    __tablename__ = "awp_execution_constraints"
    constraint_type: Mapped[str] = mapped_column(String(80))
    code: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="OPEN")
    blocking: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    due_date: Mapped[str | None] = mapped_column(String(80))
    source_domain: Mapped[str] = mapped_column(String(120), default="AWP")
    source_reference: Mapped[str] = mapped_column(String(1000), default="")
    evidence_reference: Mapped[str] = mapped_column(String(1000), default="")
    waiver_reference: Mapped[str] = mapped_column(String(1000), default="")
    cleared_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (UniqueConstraint("tenant_id", "project_workspace_id", "code", name="uq_awp_constraint_code"),)


class ConstraintMapping(ScopeRecord, Base):
    __tablename__ = "awp_constraint_mappings"
    constraint_id: Mapped[int] = mapped_column(ForeignKey("awp_execution_constraints.id"), index=True)
    target_kind: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[int | None] = mapped_column()
    schedule_version_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_versions.id"))
    activity_external_id: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    revision: Mapped[int] = mapped_column(default=1)
    reason: Mapped[str] = mapped_column(Text)


class ReadinessAssessment(ScopeRecord, Base):
    __tablename__ = "awp_readiness_assessments"
    work_package_id: Mapped[int] = mapped_column(ForeignKey("awp_work_packages.id"), index=True)
    as_of: Mapped[str] = mapped_column(String(80))
    readiness_state: Mapped[str] = mapped_column(String(30))
    blocking_constraints: Mapped[list] = mapped_column(JSON)
    open_nonblocking_constraints: Mapped[list] = mapped_column(JSON)
    dependency_state: Mapped[dict] = mapped_column(JSON)
    evidence_state: Mapped[dict] = mapped_column(JSON)
    dimensions: Mapped[dict] = mapped_column(JSON)
    source_hashes: Mapped[dict] = mapped_column(JSON)
    policy_revision: Mapped[int] = mapped_column()
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    reason: Mapped[str] = mapped_column(Text)


class AWPHistory(ScopeRecord, Base):
    __tablename__ = "awp_history"
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int] = mapped_column(index=True)
    revision: Mapped[int] = mapped_column()
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    event_type: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(Text)


def _immutable(_mapper, _connection, _row):
    raise ValueError("AWP mapping, assessment and history are append-only")


for _model in (PackageMapping, ConstraintMapping, ReadinessAssessment, AWPHistory):
    event.listen(_model, "before_update", _immutable)
    event.listen(_model, "before_delete", _immutable)


@event.listens_for(AdminConfiguration, "before_update")
@event.listens_for(AdminConfiguration, "before_delete")
def _profile_guard(_mapper, _connection, row):
    if row.kind == "awp_profile":
        history = inspect(row).attrs.status.history
        if (history.deleted[0] if history.deleted else row.status) == "published":
            _immutable(_mapper, _connection, row)
