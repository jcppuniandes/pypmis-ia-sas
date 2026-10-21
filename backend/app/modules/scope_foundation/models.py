"""Additive canonical Scope records and immutable source/snapshot lineage."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
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
from app.domain.models import AdminConfiguration


class ScopeRecord:
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ScopeModelVersion(ScopeRecord, Base):
    __tablename__ = "scope_model_versions"
    model_code: Mapped[str] = mapped_column(String(120))
    revision: Mapped[int] = mapped_column(default=1)
    source_file_name: Mapped[str] = mapped_column(String(260))
    source_hash: Mapped[str] = mapped_column(String(64))
    source_content: Mapped[bytes] = mapped_column(LargeBinary)
    schema: Mapped[str] = mapped_column(String(40), default="")
    units: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="STAGED")
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    supersedes: Mapped[int | None] = mapped_column(ForeignKey("scope_model_versions.id"))
    validation_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    diff_json: Mapped[dict] = mapped_column(JSON, default=dict)
    object_count: Mapped[int] = mapped_column(default=0)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    accepted_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "model_code", "revision", name="uq_scope_model_revision"),
        CheckConstraint("status IN ('STAGED','REVIEW','ACCEPTED','REJECTED')", name="ck_scope_model_status"),
        Index("ix_scope_model_current", "tenant_id", "project_workspace_id", "model_code", "is_current"),
        Index(
            "uq_scope_model_effective",
            "tenant_id",
            "project_workspace_id",
            "model_code",
            unique=True,
            postgresql_where=text("is_current = true"),
            sqlite_where=text("is_current = 1"),
        ),
    )


class ScopeBimObject(ScopeRecord, Base):
    __tablename__ = "scope_bim_objects"
    model_version_id: Mapped[int] = mapped_column(ForeignKey("scope_model_versions.id"), index=True)
    source_identity: Mapped[str] = mapped_column(String(160))
    guid: Mapped[str] = mapped_column(String(80), default="")
    express_id: Mapped[int] = mapped_column(default=0)
    ifc_class: Mapped[str] = mapped_column(String(120), default="")
    name: Mapped[str] = mapped_column(String(400), default="")
    properties: Mapped[dict] = mapped_column(JSON, default=dict)
    quantities: Mapped[list] = mapped_column(JSON, default=list)
    classification: Mapped[list] = mapped_column(JSON, default=list)
    discipline: Mapped[str] = mapped_column(String(100), default="")
    level: Mapped[str] = mapped_column(String(150), default="")
    area: Mapped[str] = mapped_column(String(150), default="")
    zone: Mapped[str] = mapped_column(String(150), default="")
    system: Mapped[str] = mapped_column(String(150), default="")
    materials: Mapped[list] = mapped_column(JSON, default=list)
    geometry_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("model_version_id", "source_identity", name="uq_scope_bim_source_identity"),)


class ScopeExcelImport(ScopeRecord, Base):
    __tablename__ = "scope_excel_imports"
    source_file_name: Mapped[str] = mapped_column(String(260))
    source_hash: Mapped[str] = mapped_column(String(64))
    source_content: Mapped[bytes] = mapped_column(LargeBinary)
    field_mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    headers: Mapped[list] = mapped_column(JSON, default=list)
    rows_json: Mapped[list] = mapped_column(JSON, default=list)
    validation_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="STAGED")
    candidate_item_ids: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(Text, default="")


class ScopeItem(ScopeRecord, Base):
    __tablename__ = "scope_items"
    scope_item_key: Mapped[str] = mapped_column(String(80), index=True)
    scope_code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    parent_scope_item_id: Mapped[int | None] = mapped_column(ForeignKey("scope_items.id"))
    predecessor_id: Mapped[int | None] = mapped_column(ForeignKey("scope_items.id"))
    revision: Mapped[int] = mapped_column(default=1)
    scope_type: Mapped[str] = mapped_column(String(100), default="DELIVERABLE")
    scope_nature: Mapped[str] = mapped_column(String(24))
    discipline: Mapped[str] = mapped_column(String(100), default="")
    area: Mapped[str] = mapped_column(String(150), default="")
    zone: Mapped[str] = mapped_column(String(150), default="")
    system: Mapped[str] = mapped_column(String(150), default="")
    location: Mapped[str] = mapped_column(String(260), default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    source_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    approved_quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    current_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    unit: Mapped[str] = mapped_column(String(40))
    measurement_method: Mapped[str] = mapped_column(String(260), default="EXPLICIT_NO_CONVERSION")
    source_type: Mapped[str] = mapped_column(String(32))
    source_reference: Mapped[str] = mapped_column(String(500), default="")
    source_revision: Mapped[str] = mapped_column(String(160), default="")
    lineage_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    baseline_reference: Mapped[int | None] = mapped_column(ForeignKey("scope_baselines.id", use_alter=True))
    effective_from: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "scope_code", "revision", name="uq_scope_item_revision"),
        CheckConstraint("scope_nature IN ('INSTALL','REMOVE','TEMPORARY','MAINTENANCE')", name="ck_scope_nature"),
        CheckConstraint("quantity >= 0 AND source_quantity >= 0 AND current_quantity >= 0", name="ck_scope_quantity"),
        CheckConstraint("source_type IN ('IFC','EXCEL','MANUAL','APPROVED_CHANGE')", name="ck_scope_source_type"),
    )


class ScopeModelMapping(ScopeRecord, Base):
    __tablename__ = "scope_model_mappings"
    scope_item_id: Mapped[int] = mapped_column(ForeignKey("scope_items.id"), index=True)
    model_object_id: Mapped[int] = mapped_column(ForeignKey("scope_bim_objects.id"), index=True)
    __table_args__ = (UniqueConstraint("scope_item_id", "model_object_id", name="uq_scope_model_mapping"),)


class ScopeRevision(ScopeRecord, Base):
    __tablename__ = "scope_revisions"
    revision_code: Mapped[str] = mapped_column(String(120))
    revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    reason: Mapped[str] = mapped_column(Text)
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "revision_code", name="uq_scope_revision_code"),
    )


class ScopeBaseline(ScopeRecord, Base):
    __tablename__ = "scope_baselines"
    scope_revision_id: Mapped[int] = mapped_column(ForeignKey("scope_revisions.id"), unique=True)
    revision: Mapped[int] = mapped_column(default=1)
    original_baseline_id: Mapped[int | None] = mapped_column(ForeignKey("scope_baselines.id"))
    previous_baseline_id: Mapped[int | None] = mapped_column(ForeignKey("scope_baselines.id"))
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "revision", name="uq_scope_baseline_revision"),
    )


class ExecutionStrategy(ScopeRecord, Base):
    __tablename__ = "scope_execution_strategies"
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    reason: Mapped[str] = mapped_column(Text)
    predecessor_id: Mapped[int | None] = mapped_column(ForeignKey("scope_execution_strategies.id"))
    paths_json: Mapped[list] = mapped_column(JSON, default=list)
    segmentation_rules: Mapped[list] = mapped_column(JSON, default=list)
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "code", "revision", name="uq_scope_strategy_revision"),
    )


class PlanItem(ScopeRecord, Base):
    __tablename__ = "scope_plan_items"
    code: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(300))
    parent_plan_item_id: Mapped[int | None] = mapped_column(ForeignKey("scope_plan_items.id"))
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("scope_execution_strategies.id"))
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    operation: Mapped[str] = mapped_column(String(30), default="CREATE")
    reason: Mapped[str] = mapped_column(Text)
    supersedes_ids: Mapped[list] = mapped_column(JSON, default=list)
    future_mappings: Mapped[dict] = mapped_column(JSON, default=dict)
    rule_json: Mapped[dict] = mapped_column(JSON, default=dict)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    content_hash: Mapped[str] = mapped_column(String(64), default="")


class PlanItemScopeLink(ScopeRecord, Base):
    __tablename__ = "scope_plan_item_links"
    plan_item_id: Mapped[int] = mapped_column(ForeignKey("scope_plan_items.id"), index=True)
    scope_item_id: Mapped[int] = mapped_column(ForeignKey("scope_items.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    unit: Mapped[str] = mapped_column(String(40))
    __table_args__ = (
        UniqueConstraint("plan_item_id", "scope_item_id", name="uq_scope_plan_allocation"),
        CheckConstraint("quantity > 0", name="ck_scope_plan_allocation_quantity"),
    )


class PlanItemModelLink(ScopeRecord, Base):
    __tablename__ = "scope_plan_model_links"
    plan_item_id: Mapped[int] = mapped_column(ForeignKey("scope_plan_items.id"), index=True)
    model_object_id: Mapped[int] = mapped_column(ForeignKey("scope_bim_objects.id"), index=True)
    __table_args__ = (UniqueConstraint("plan_item_id", "model_object_id", name="uq_scope_plan_model_link"),)


class DerivedModelVersion(ScopeRecord, Base):
    __tablename__ = "scope_derived_model_versions"
    revision: Mapped[int] = mapped_column(default=1)
    predecessor_id: Mapped[int | None] = mapped_column(ForeignKey("scope_derived_model_versions.id"))
    representation_type: Mapped[str] = mapped_column(String(40), default="LOGICAL")
    reason: Mapped[str] = mapped_column(Text)
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))


IMMUTABLE = (
    ScopeBimObject,
    ScopeModelMapping,
    ScopeBaseline,
    PlanItemScopeLink,
    PlanItemModelLink,
    DerivedModelVersion,
)


def _before_status(record):
    history = inspect(record).attrs.status.history
    return history.deleted[0] if history.deleted else record.status


def _immutable(_mapper, _connection, _record):
    raise ValueError("Scope source/snapshot/lineage is immutable")


for _model in IMMUTABLE:
    event.listen(_model, "before_update", _immutable)
    event.listen(_model, "before_delete", _immutable)


@event.listens_for(ScopeModelVersion, "before_update")
@event.listens_for(ScopeExcelImport, "before_update")
def _source_guard(_mapper, _connection, record):
    mutable = {
        "status",
        "version",
        "reason",
        "reviewed_by",
        "accepted_by",
        "accepted_at",
        "is_current",
        "candidate_item_ids",
    }
    if any(a.history.has_changes() for a in inspect(record).attrs if a.key not in mutable):
        raise ValueError("Original source content, hash and parsed objects are immutable")


@event.listens_for(ScopeItem, "before_update")
def _item_guard(_mapper, _connection, record):
    if _before_status(record) == "APPROVED":
        raise ValueError("Approved Scope Item is immutable; create successor revision")


@event.listens_for(ExecutionStrategy, "before_update")
@event.listens_for(ScopeRevision, "before_update")
def _publication_guard(_mapper, _connection, record):
    if _before_status(record) in {"APPROVED", "PUBLISHED"}:
        raise ValueError("Approved/published Scope content is immutable")


@event.listens_for(PlanItem, "before_update")
def _plan_guard(_mapper, _connection, record):
    if _before_status(record) in {"PUBLISHED", "SUPERSEDED"}:
        allowed = {"status", "version"}
        if any(a.history.has_changes() for a in inspect(record).attrs if a.key not in allowed):
            raise ValueError("Published Plan Item content is immutable")


for _model in (ScopeModelVersion, ScopeExcelImport, ScopeItem, ScopeRevision, ExecutionStrategy, PlanItem):
    event.listen(_model, "before_delete", _immutable)


@event.listens_for(AdminConfiguration, "before_update")
@event.listens_for(AdminConfiguration, "before_delete")
def _scope_profile_guard(_mapper, _connection, record):
    if record.kind == "scope_profile" and _before_status(record) == "published":
        raise ValueError("Published Scope Profile is immutable; create successor")
