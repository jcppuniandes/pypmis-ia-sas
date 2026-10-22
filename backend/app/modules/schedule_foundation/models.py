"""Additive Schedule aggregates with immutable source snapshots and mapping history."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base
from app.domain.models import AdminConfiguration


class ScheduleRecord:
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ScheduleRegister(ScheduleRecord, Base):
    __tablename__ = "schedule_registers"
    schedule_code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    schedule_type: Mapped[str] = mapped_column(String(100))
    purpose: Mapped[str] = mapped_column(Text, default="")
    source_system: Mapped[str] = mapped_column(String(80), default="P6_MANUAL_EXCHANGE")
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE")
    calendar_basis: Mapped[str] = mapped_column(String(120), default="EXPLICIT_SOURCE")
    timezone: Mapped[str] = mapped_column(String(80))
    current_version_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_versions.id", use_alter=True))
    baseline_version_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_versions.id", use_alter=True))
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "schedule_code", name="uq_schedule_register_code"),
    )


class ScheduleVersion(ScheduleRecord, Base):
    __tablename__ = "schedule_versions"
    register_id: Mapped[int] = mapped_column(ForeignKey("schedule_registers.id"), index=True)
    revision: Mapped[int] = mapped_column()
    predecessor_version_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_versions.id"))
    scope_baseline_id: Mapped[int] = mapped_column(ForeignKey("scope_baselines.id"))
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(40), default="UPDATE")
    status: Mapped[str] = mapped_column(String(32), default="STAGED")
    data_date: Mapped[str] = mapped_column(String(80), default="")
    source_file_name: Mapped[str] = mapped_column(String(260))
    source_format: Mapped[str] = mapped_column(String(40))
    source_hash: Mapped[str] = mapped_column(String(64))
    source_content: Mapped[bytes] = mapped_column(LargeBinary)
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    import_manifest_json: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    diff_json: Mapped[dict] = mapped_column(JSON, default=dict)
    health_json: Mapped[dict] = mapped_column(JSON, default=dict)
    accepted_mapping_hash: Mapped[str | None] = mapped_column(String(64))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    accepted_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_material_editor: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("register_id", "revision", name="uq_schedule_version_revision"),
        CheckConstraint(
            "status IN ('DRAFT','STAGED','VALIDATED','UNDER_REVIEW','ACCEPTED_CURRENT','SUPERSEDED','REJECTED')",
            name="ck_schedule_version_status",
        ),
    )


class ScheduleMapping(ScheduleRecord, Base):
    __tablename__ = "schedule_scope_plan_mappings"
    schedule_version_id: Mapped[int] = mapped_column(ForeignKey("schedule_versions.id"), index=True)
    target_kind: Mapped[str] = mapped_column(String(20))
    target_external_id: Mapped[str] = mapped_column(String(160))
    revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(30), default="VALID")
    plan_item_ids: Mapped[list] = mapped_column(JSON, default=list)
    scope_item_ids: Mapped[list] = mapped_column(JSON, default=list)
    lineage_json: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint(
            "schedule_version_id", "target_kind", "target_external_id", "revision", name="uq_schedule_mapping_revision"
        ),
        CheckConstraint("target_kind IN ('WBS','ACTIVITY')", name="ck_schedule_mapping_target"),
        CheckConstraint(
            "status IN ('VALID','STALE','BROKEN','REQUIRES_REVIEW','REMOVED')", name="ck_schedule_mapping_status"
        ),
    )


class ScheduleBaseline(ScheduleRecord, Base):
    __tablename__ = "schedule_baselines"
    register_id: Mapped[int] = mapped_column(ForeignKey("schedule_registers.id"), index=True)
    schedule_version_id: Mapped[int] = mapped_column(ForeignKey("schedule_versions.id"), index=True)
    baseline_type: Mapped[str] = mapped_column(String(80))
    revision: Mapped[int] = mapped_column()
    previous_baseline_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_baselines.id"))
    status: Mapped[str] = mapped_column(String(32), default="BASELINE_CANDIDATE")
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("register_id", "revision", name="uq_schedule_baseline_revision"),
        CheckConstraint(
            "status IN ('BASELINE_CANDIDATE','SUBMITTED','UNDER_REVIEW','APPROVED_BASELINE','REJECTED')",
            name="ck_schedule_baseline_status",
        ),
    )


class ScheduleExportManifest(ScheduleRecord, Base):
    __tablename__ = "schedule_export_manifests"
    schedule_version_id: Mapped[int] = mapped_column(ForeignKey("schedule_versions.id"), index=True)
    baseline_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_baselines.id"))
    purpose: Mapped[str] = mapped_column(String(30))
    source_file_name: Mapped[str] = mapped_column(String(260))
    source_hash: Mapped[str] = mapped_column(String(64))
    source_content: Mapped[bytes] = mapped_column(LargeBinary)
    manifest_json: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)


class SchedulePeriodAssociation(ScheduleRecord, Base):
    __tablename__ = "schedule_period_associations"
    schedule_version_id: Mapped[int] = mapped_column(ForeignKey("schedule_versions.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("project_controls_periods.id"), index=True)
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("schedule_version_id", "period_id", name="uq_schedule_period_association"),)


def _immutable(_mapper, _connection, _record):
    raise ValueError("Schedule immutable source, mapping history or accepted snapshot")


for _model in (ScheduleMapping, ScheduleExportManifest, SchedulePeriodAssociation):
    event.listen(_model, "before_update", _immutable)
    event.listen(_model, "before_delete", _immutable)


@event.listens_for(ScheduleVersion, "before_update")
def _version_guard(_mapper, _connection, record):
    state = inspect(record)
    history = state.attrs.status.history
    old = history.deleted[0] if history.deleted else record.status
    if old in {"SUPERSEDED", "REJECTED"} or old == "ACCEPTED_CURRENT" and record.status != "SUPERSEDED":
        _immutable(_mapper, _connection, record)
    allowed = (
        {"status", "version"}
        if old in {"ACCEPTED_CURRENT", "SUPERSEDED", "REJECTED"}
        else {
            "status",
            "version",
            "validation_json",
            "diff_json",
            "health_json",
            "accepted_mapping_hash",
            "reviewed_by",
            "reviewed_at",
            "accepted_by",
            "accepted_at",
            "last_material_editor",
        }
    )
    if any(attribute.history.has_changes() for attribute in state.attrs if attribute.key not in allowed):
        _immutable(_mapper, _connection, record)


@event.listens_for(ScheduleBaseline, "before_update")
def _baseline_guard(_mapper, _connection, record):
    state = inspect(record)
    history = state.attrs.status.history
    old = history.deleted[0] if history.deleted else record.status
    allowed = {"status", "version", "reviewed_by", "approved_by", "approved_at"}
    if old == "APPROVED_BASELINE" or any(a.history.has_changes() for a in state.attrs if a.key not in allowed):
        _immutable(_mapper, _connection, record)


for _model in (ScheduleVersion, ScheduleBaseline, ScheduleRegister):
    event.listen(_model, "before_delete", _immutable)


@event.listens_for(AdminConfiguration, "before_update")
@event.listens_for(AdminConfiguration, "before_delete")
def _profile_guard(_mapper, _connection, record):
    if record.kind == "schedule_profile":
        history = inspect(record).attrs.status.history
        if (history.deleted[0] if history.deleted else record.status) == "published":
            _immutable(_mapper, _connection, record)
