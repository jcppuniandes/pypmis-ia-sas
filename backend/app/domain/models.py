from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.database.session import Base


class CostSource(StrEnum):
    invoice = "invoice"
    payroll = "payroll"
    equipment = "equipment"
    materials = "materials"
    commitment = "commitment"


class ScheduleSource(StrEnum):
    p6_xer = "p6_xer"
    p6_xml = "p6_xml"
    ms_project_xml = "ms_project_xml"
    ms_project_mpp = "ms_project_mpp"


class ImportStatus(StrEnum):
    received = "received"
    validated = "validated"
    rejected = "rejected"
    imported = "imported"


class RelationshipType(StrEnum):
    fs = "FS"
    ss = "SS"
    ff = "FF"
    sf = "SF"


class AlertSeverity(StrEnum):
    green = "green"
    amber = "amber"
    red = "red"


class WorkflowStatus(StrEnum):
    draft = "draft"
    analyzing = "analyzing"
    approved = "approved"
    rejected = "rejected"
    closed = "closed"


class Tenant(Base):
    __tablename__ = "tenants"

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        if self.base_currency is None:
            self.base_currency = "COP"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(8), default="COP")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    code: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(220))
    phase: Mapped[str] = mapped_column(String(80), default="Execution")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    calendar_base: Mapped[str] = mapped_column(String(120), default="")
    owner: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    authorization_date: Mapped[date | None] = mapped_column(Date)
    authorization_ref: Mapped[str] = mapped_column(String(160), default="")
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    start_date: Mapped[date | None] = mapped_column(Date)
    finish_date: Mapped[date | None] = mapped_column(Date)

    __table_args__ = (UniqueConstraint("tenant_id", "code"),)


class ProjectControlPlan(Base):
    __tablename__ = "project_control_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    execution_strategy: Mapped[str] = mapped_column(Text, default="")
    control_strategy: Mapped[str] = mapped_column(Text, default="")
    progress_measurement_rule: Mapped[str] = mapped_column(Text, default="")
    cost_measurement_rule: Mapped[str] = mapped_column(Text, default="")
    change_management_rule: Mapped[str] = mapped_column(Text, default="")
    risk_management_rule: Mapped[str] = mapped_column(Text, default="")
    procurement_strategy: Mapped[str] = mapped_column(Text, default="")
    document_control_rule: Mapped[str] = mapped_column(Text, default="")
    reporting_cadence: Mapped[str] = mapped_column(String(120), default="Weekly")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id"),)


class ProjectOperationalSetup(Base):
    __tablename__ = "project_operational_setups"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    project_number: Mapped[str] = mapped_column(String(80), default="")
    setup_template: Mapped[str] = mapped_column(String(180), default="")
    attribute_form: Mapped[str] = mapped_column(String(180), default="")
    permissions_configured: Mapped[bool] = mapped_column(default=False)
    modules_configured: Mapped[bool] = mapped_column(default=False)
    cost_sheet_ready: Mapped[bool] = mapped_column(default=False)
    funding_sheet_ready: Mapped[bool] = mapped_column(default=False)
    p6_mapping_ready: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    readiness_status: Mapped[str] = mapped_column(String(40), default="not_ready")
    readiness_notes: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id"),)


class ActivitySheet(Base):
    __tablename__ = "activity_sheets"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    schedule_import_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_imports.id"), index=True)
    source_file_name: Mapped[str] = mapped_column(String(260))
    source: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    data_date: Mapped[date | None] = mapped_column(Date)
    baseline_name: Mapped[str] = mapped_column(String(160), default="")
    validation_summary: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ActivitySheetRow(Base):
    __tablename__ = "activity_sheet_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    activity_sheet_id: Mapped[int] = mapped_column(ForeignKey("activity_sheets.id"), index=True)
    external_activity_id: Mapped[str] = mapped_column(String(120), index=True)
    wbs_code: Mapped[str] = mapped_column(String(120), default="")
    activity_name: Mapped[str] = mapped_column(String(260), default="")
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_finish: Mapped[date | None] = mapped_column(Date)
    total_float_days: Mapped[float] = mapped_column(Float, default=0)
    critical_path: Mapped[bool] = mapped_column(default=False)
    planned_cost: Mapped[float] = mapped_column(Float, default=0)


class QuantityTakeoffRun(Base):
    __tablename__ = "quantity_takeoff_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    bim_model_id: Mapped[int | None] = mapped_column(
        ForeignKey("bim_models.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    source_file_name: Mapped[str] = mapped_column(String(260))
    source_type: Mapped[str] = mapped_column(String(40), default="")
    source_sha256: Mapped[str] = mapped_column(String(64), default="")
    bim_revision_id: Mapped[str] = mapped_column(String(120), default="")
    model_linked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="needs_mapping")
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    mapped_line_count: Mapped[int] = mapped_column(Integer, default=0)
    unmapped_line_count: Mapped[int] = mapped_column(Integer, default=0)
    total_quantity: Mapped[float] = mapped_column(Float, default=0)
    validation_summary: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class BimModel(Base):
    __tablename__ = "bim_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    source_file_name: Mapped[str] = mapped_column(String(260))
    source_type: Mapped[str] = mapped_column(String(40), default="ifc")
    source_sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    revision_id: Mapped[str] = mapped_column(String(120), default="")
    source_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    source_storage_path: Mapped[str] = mapped_column(String(500), default="")
    viewer_artifact_path: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(40), default="uploaded")
    schema: Mapped[str] = mapped_column(String(40), default="")
    units: Mapped[str] = mapped_column(String(80), default="")
    element_count: Mapped[int] = mapped_column(Integer, default=0)
    storey_count: Mapped[int] = mapped_column(Integer, default=0)
    model_identity: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class BimQuantityRule(Base):
    __tablename__ = "bim_quantity_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    ifc_class: Mapped[str] = mapped_column(String(120), index=True)
    element_label: Mapped[str] = mapped_column(String(160), default="")
    expected_measure: Mapped[str] = mapped_column(String(160), default="")
    rule_hint: Mapped[str] = mapped_column(String(220), default="")
    expected_units: Mapped[list] = mapped_column(JSON, default=list)
    allow_fallback_count: Mapped[bool] = mapped_column(default=True)
    source: Mapped[str] = mapped_column(String(40), default="system_default")
    status: Mapped[str] = mapped_column(String(40), default="active")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "ifc_class"),)


class ColombiaApuCatalogItem(Base):
    __tablename__ = "colombia_apu_catalog_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(80), default="datacauca_public_apu", index=True)
    external_id: Mapped[str] = mapped_column(String(160), default="", index=True)
    item_code: Mapped[str] = mapped_column(String(80), index=True)
    item_name: Mapped[str] = mapped_column(Text, default="", index=True)
    unit: Mapped[str] = mapped_column(String(40), default="")
    unit_rate: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="COP")
    group_name: Mapped[str] = mapped_column(String(160), default="")
    chapter: Mapped[str] = mapped_column(String(220), default="")
    region: Mapped[str] = mapped_column(String(160), default="")
    source_url: Mapped[str] = mapped_column(String(500), default="")
    license_note: Mapped[str] = mapped_column(Text, default="")
    update_frequency: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(40), default="review")
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "source_key", "external_id"),)


class QuantityTakeoffLine(Base):
    __tablename__ = "quantity_takeoff_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("quantity_takeoff_runs.id"), index=True)
    source_row_id: Mapped[str] = mapped_column(String(120), default="")
    element_id: Mapped[str] = mapped_column(String(120), default="")
    element_guid: Mapped[str] = mapped_column(String(120), default="", index=True)
    ifc_class: Mapped[str] = mapped_column(String(120), default="")
    category: Mapped[str] = mapped_column(String(120), default="")
    family: Mapped[str] = mapped_column(String(160), default="")
    type_name: Mapped[str] = mapped_column(String(160), default="")
    instance_name: Mapped[str] = mapped_column(String(220), default="")
    project_name: Mapped[str] = mapped_column(String(160), default="")
    site_name: Mapped[str] = mapped_column(String(160), default="")
    building_name: Mapped[str] = mapped_column(String(160), default="")
    storey: Mapped[str] = mapped_column(String(160), default="")
    system_name: Mapped[str] = mapped_column(String(160), default="")
    zone_name: Mapped[str] = mapped_column(String(160), default="")
    assembly_name: Mapped[str] = mapped_column(String(160), default="")
    classification_system: Mapped[str] = mapped_column(String(120), default="")
    classification_code: Mapped[str] = mapped_column(String(120), default="")
    quantity: Mapped[float] = mapped_column(Float, default=0)
    unit: Mapped[str] = mapped_column(String(40), default="")
    measurement_rule: Mapped[str] = mapped_column(String(160), default="")
    wbs_code: Mapped[str] = mapped_column(String(120), default="", index=True)
    cbs_code: Mapped[str] = mapped_column(String(120), default="", index=True)
    fbs_code: Mapped[str] = mapped_column(String(120), default="", index=True)
    package_code: Mapped[str] = mapped_column(String(120), default="", index=True)
    wbs_id: Mapped[int | None] = mapped_column(ForeignKey("wbs.id"), index=True)
    cbs_id: Mapped[int | None] = mapped_column(ForeignKey("cost_breakdown_structures.id"), index=True)
    fbs_id: Mapped[int | None] = mapped_column(ForeignKey("funding_sources.id"), index=True)
    work_package_id: Mapped[int | None] = mapped_column(ForeignKey("work_packages.id"), index=True)
    mapping_status: Mapped[str] = mapped_column(String(40), default="needs_mapping")
    validation_notes: Mapped[str] = mapped_column(Text, default="")
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(180), index=True)
    full_name: Mapped[str] = mapped_column(String(180))
    title: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(40), default="active")

    __table_args__ = (UniqueConstraint("tenant_id", "email"),)


class OrganizationUnit(Base):
    __tablename__ = "organization_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("organization_units.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(180))
    unit_type: Mapped[str] = mapped_column(String(80), default="department")
    manager_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "code"),)


class SecurityGroup(Base):
    __tablename__ = "security_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "code"),)


class SecurityGroupMember(Base):
    __tablename__ = "security_group_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("security_groups.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    added_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "group_id", "user_id"),)


class PermissionCatalog(Base):
    __tablename__ = "permission_catalog"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    resource: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(String(40), default="standard")
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)


class SecurityRole(Base):
    __tablename__ = "security_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    is_system: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "code"),)


class SecurityRolePermission(Base):
    __tablename__ = "security_role_permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("security_roles.id"), index=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permission_catalog.id"), index=True)
    granted_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "role_id", "permission_id"),)


class SecurityAccessAssignment(Base):
    __tablename__ = "security_access_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    subject_type: Mapped[str] = mapped_column(String(20), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("security_groups.id"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("security_roles.id"), index=True)
    scope_type: Mapped[str] = mapped_column(String(40), default="organization", index=True)
    scope_unit_id: Mapped[int | None] = mapped_column(ForeignKey("organization_units.id"), index=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    granted_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    outcome: Mapped[str] = mapped_column(String(40), default="success", index=True)
    target_type: Mapped[str] = mapped_column(String(80), default="")
    target_id: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class AdminConfiguration(Base):
    """Tenant-wide reusable configuration with explicit draft/publish revisions."""

    __tablename__ = "admin_configurations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    code: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)
    content_json: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "kind", "code", "revision"),)


class EnterpriseWorkspace(Base):
    __tablename__ = "enterprise_workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    workspace_type_code: Mapped[str] = mapped_column(String(120), index=True)
    code: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    defaults_json: Mapped[dict] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "code"),)


class WorkspaceModuleSetting(Base):
    __tablename__ = "workspace_module_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    module_key: Mapped[str] = mapped_column(String(120), index=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "workspace_id", "module_key"),)


class AdminNumberSequence(Base):
    __tablename__ = "admin_number_sequences"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    rule_code: Mapped[str] = mapped_column(String(120), index=True)
    scope_key: Mapped[str] = mapped_column(String(180), default="tenant", index=True)
    next_value: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "rule_code", "scope_key"),)


class AuthCredential(Base):
    __tablename__ = "auth_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="local")
    password_hash: Mapped[str] = mapped_column(String(220))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "provider"),)


class IntegrationToken(Base):
    __tablename__ = "integration_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    token_prefix: Mapped[str] = mapped_column(String(40), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    allowed_datasets: Mapped[str] = mapped_column(Text, default="")
    allowed_formats: Mapped[str] = mapped_column(String(80), default="json,csv,both,xlsx")
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "token_hash"),)


class IntegrationExportLog(Base):
    __tablename__ = "integration_export_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    requested_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    integration_token_id: Mapped[int | None] = mapped_column(ForeignKey("integration_tokens.id"), index=True)
    actor: Mapped[str] = mapped_column(String(180), default="")
    artifact_type: Mapped[str] = mapped_column(String(40), index=True)
    datasets: Mapped[str] = mapped_column(Text, default="")
    format: Mapped[str] = mapped_column(String(40), default="")
    file_name: Mapped[str] = mapped_column(String(260), default="")
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="completed", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ProjectMembership(Base):
    __tablename__ = "project_memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    role: Mapped[str] = mapped_column(String(80), index=True)
    can_capture_progress: Mapped[bool] = mapped_column(default=False)
    can_capture_cost: Mapped[bool] = mapped_column(default=False)
    can_approve_workflow: Mapped[bool] = mapped_column(default=False)
    can_manage_contract: Mapped[bool] = mapped_column(default=False)
    can_configure: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "user_id"),)


class ScheduleImport(Base):
    __tablename__ = "schedule_imports"

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.detected_currency = self.detected_currency or ""
        self.currency_confidence = self.currency_confidence or "unknown"
        self.currency_source = self.currency_source or ""
        self.currency_confirmed = bool(self.currency_confirmed)
        self.total_imported_cost = self.total_imported_cost or 0
        self.cost_loaded_activity_count = self.cost_loaded_activity_count or 0
        self.cost_loaded_activity_percent = self.cost_loaded_activity_percent or 0
        self.cost_source_summary = self.cost_source_summary or {}

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    source: Mapped[ScheduleSource] = mapped_column(Enum(ScheduleSource))
    file_name: Mapped[str] = mapped_column(String(260))
    status: Mapped[ImportStatus] = mapped_column(Enum(ImportStatus), default=ImportStatus.received)
    data_date: Mapped[date | None] = mapped_column(Date)
    baseline_name: Mapped[str] = mapped_column(String(160), default="")
    quality_score: Mapped[float] = mapped_column(Float, default=0)
    validation_summary: Mapped[str] = mapped_column(Text, default="")
    detected_currency: Mapped[str] = mapped_column(String(8), default="")
    currency_confidence: Mapped[str] = mapped_column(String(40), default="unknown")
    currency_source: Mapped[str] = mapped_column(String(160), default="")
    currency_confirmed: Mapped[bool] = mapped_column(default=False)
    total_imported_cost: Mapped[float] = mapped_column(Float, default=0)
    cost_loaded_activity_count: Mapped[int] = mapped_column(Integer, default=0)
    cost_loaded_activity_percent: Mapped[float] = mapped_column(Float, default=0)
    cost_source_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ScheduleValidationFinding(Base):
    __tablename__ = "schedule_validation_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    schedule_import_id: Mapped[int] = mapped_column(ForeignKey("schedule_imports.id"), index=True)
    check_code: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(40), default="info")
    message: Mapped[str] = mapped_column(String(360))
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    weight: Mapped[float] = mapped_column(Float, default=0)


class BaselineVersion(Base):
    __tablename__ = "baseline_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    schedule_import_id: Mapped[int] = mapped_column(ForeignKey("schedule_imports.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40), default="in_review")
    data_date: Mapped[date | None] = mapped_column(Date)
    quality_score: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "version_no"),)


class ControlPeriod(Base):
    __tablename__ = "control_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    period_label: Mapped[str] = mapped_column(String(40), index=True)
    data_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "period_label"),)


class WBS(Base):
    __tablename__ = "wbs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("wbs.id"))
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(220))
    level: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(Text, default="")
    dictionary: Mapped[str] = mapped_column(Text, default="")
    responsible: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(40), default="draft")


class ControlAccount(Base):
    __tablename__ = "control_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    wbs_id: Mapped[int] = mapped_column(ForeignKey("wbs.id"), index=True)
    awp_package_id: Mapped[int | None] = mapped_column(ForeignKey("work_packages.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(220))
    responsible: Mapped[str] = mapped_column(String(160))
    discipline: Mapped[str] = mapped_column(String(80))
    scope: Mapped[str] = mapped_column(Text, default="")
    budget: Mapped[float] = mapped_column(Float, default=0)
    start_date: Mapped[date | None] = mapped_column(Date)
    finish_date: Mapped[date | None] = mapped_column(Date)
    cbs_code: Mapped[str] = mapped_column(String(80), default="")
    contract_ref: Mapped[str] = mapped_column(String(120), default="")
    measurement_rule: Mapped[str] = mapped_column(String(260), default="")
    earned_value: Mapped[float] = mapped_column(Float, default=0)
    actual_cost: Mapped[float] = mapped_column(Float, default=0)
    forecast: Mapped[float] = mapped_column(Float, default=0)
    lifecycle_status: Mapped[str] = mapped_column(String(40), default="active")
    risk_ref: Mapped[str] = mapped_column(String(120), default="")
    closure_note: Mapped[str] = mapped_column(String(360), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    activities: Mapped[list["Activity"]] = relationship(back_populates="control_account")
    budgets: Mapped[list["Budget"]] = relationship(back_populates="control_account")
    costs: Mapped[list["CostRecord"]] = relationship(back_populates="control_account")
    progress: Mapped[list["ProgressRecord"]] = relationship(back_populates="control_account")


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    control_account_id: Mapped[int] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(260))
    logic_type: Mapped[str] = mapped_column(String(2), default="FS")
    baseline_start: Mapped[date | None] = mapped_column(Date)
    baseline_finish: Mapped[date | None] = mapped_column(Date)
    planned_percent: Mapped[float] = mapped_column(Float, default=0)
    critical_path: Mapped[bool] = mapped_column(default=False)
    lookahead_window: Mapped[str] = mapped_column(String(40), default="6W")

    control_account: Mapped[ControlAccount] = relationship(back_populates="activities")


class ScheduleActivityMap(Base):
    __tablename__ = "schedule_activity_maps"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    schedule_import_id: Mapped[int] = mapped_column(ForeignKey("schedule_imports.id"), index=True)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"), index=True)
    external_activity_id: Mapped[str] = mapped_column(String(120), index=True)
    wbs_code: Mapped[str] = mapped_column(String(120), default="")
    activity_name: Mapped[str] = mapped_column(String(260))
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_finish: Mapped[date | None] = mapped_column(Date)
    total_float_days: Mapped[float] = mapped_column(Float, default=0)
    critical_path: Mapped[bool] = mapped_column(default=False)


class ControlAccountMapping(Base):
    __tablename__ = "control_account_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    schedule_import_id: Mapped[int] = mapped_column(ForeignKey("schedule_imports.id"), index=True)
    schedule_activity_map_id: Mapped[int] = mapped_column(ForeignKey("schedule_activity_maps.id"), index=True)
    activity_id: Mapped[int | None] = mapped_column(ForeignKey("activities.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    wbs_code: Mapped[str] = mapped_column(String(120), default="")
    wbs_name: Mapped[str] = mapped_column(String(220), default="")
    cbs_code: Mapped[str] = mapped_column(String(120), default="")
    mapping_rule: Mapped[str] = mapped_column(String(120), default="WBS")
    planned_cost: Mapped[float] = mapped_column(Float, default=0)
    planned_value: Mapped[float] = mapped_column(Float, default=0)
    planned_percent: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(40), default="mapped")
    review_note: Mapped[str] = mapped_column(String(260), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "schedule_activity_map_id"),)


class ActivityRelationship(Base):
    __tablename__ = "activity_relationships"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    schedule_import_id: Mapped[int] = mapped_column(ForeignKey("schedule_imports.id"), index=True)
    predecessor_external_id: Mapped[str] = mapped_column(String(120), index=True)
    successor_external_id: Mapped[str] = mapped_column(String(120), index=True)
    relationship_type: Mapped[RelationshipType] = mapped_column(Enum(RelationshipType), default=RelationshipType.fs)
    lag_days: Mapped[float] = mapped_column(Float, default=0)


class WorkPackage(Base):
    __tablename__ = "work_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    wbs_id: Mapped[int | None] = mapped_column(ForeignKey("wbs.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("work_packages.id"), index=True)
    package_type: Mapped[str] = mapped_column(String(20), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(260))
    description: Mapped[str] = mapped_column(Text, default="")
    discipline: Mapped[str] = mapped_column(String(80), default="")
    sequence_no: Mapped[int] = mapped_column(Integer, default=0)
    path_of_construction: Mapped[str] = mapped_column(String(260), default="")
    owner_role: Mapped[str] = mapped_column(String(120), default="Workface Planner")
    readiness_status: Mapped[str] = mapped_column(String(60), default="constraint_review")
    planned_release_date: Mapped[date | None] = mapped_column(Date)
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_finish: Mapped[date | None] = mapped_column(Date)
    release_required_on: Mapped[date | None] = mapped_column(Date)
    main_constraints: Mapped[str] = mapped_column(Text, default="")
    progress_percent: Mapped[float] = mapped_column(Float, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "code"),)


class WorkPackageConstraint(Base):
    __tablename__ = "work_package_constraints"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    work_package_id: Mapped[int] = mapped_column(ForeignKey("work_packages.id"), index=True)
    constraint_type: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str] = mapped_column(String(360))
    owner_role: Mapped[str] = mapped_column(String(120), default="Workface Planner")
    required_by: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="open")
    priority: Mapped[str] = mapped_column(String(40), default="medium")
    evidence_ref: Mapped[str] = mapped_column(String(180), default="")
    closure_note: Mapped[str] = mapped_column(String(360), default="")
    exception_ref: Mapped[str] = mapped_column(String(180), default="")
    closed_by: Mapped[str] = mapped_column(String(160), default="")
    closed_on: Mapped[date | None] = mapped_column(Date)
    blocking: Mapped[bool] = mapped_column(default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class BusinessProcessInstance(Base):
    __tablename__ = "business_process_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    trigger_entity_type: Mapped[str] = mapped_column(String(80), default="ScheduleImport")
    trigger_entity_id: Mapped[int] = mapped_column(Integer, index=True)
    process_code: Mapped[str] = mapped_column(String(80), index=True)
    process_name: Mapped[str] = mapped_column(String(160))
    record_no: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(260))
    status: Mapped[str] = mapped_column(String(40), default="in_review")
    current_step: Mapped[str] = mapped_column(String(120))
    ball_in_court: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    version: Mapped[int] = mapped_column(Integer, default=1)

    steps: Mapped[list["WorkflowStepInstance"]] = relationship(back_populates="process_instance")


class WorkflowStepInstance(Base):
    __tablename__ = "workflow_step_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    process_instance_id: Mapped[int] = mapped_column(ForeignKey("business_process_instances.id"), index=True)
    step_order: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120))
    detail: Mapped[str] = mapped_column(String(260))
    owner_role: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40))
    tone: Mapped[str] = mapped_column(String(40))

    process_instance: Mapped[BusinessProcessInstance] = relationship(back_populates="steps")


class BusinessProcessLineItem(Base):
    __tablename__ = "business_process_line_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    process_instance_id: Mapped[int] = mapped_column(ForeignKey("business_process_instances.id"), index=True)
    line_type: Mapped[str] = mapped_column(String(40), index=True)
    wbs_id: Mapped[int | None] = mapped_column(ForeignKey("wbs.id"), index=True)
    cbs_id: Mapped[int] = mapped_column(ForeignKey("cost_breakdown_structures.id"), index=True)
    funding_source_id: Mapped[int | None] = mapped_column(ForeignKey("funding_sources.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    cost_code_id: Mapped[int | None] = mapped_column(ForeignKey("cost_codes.id"), index=True)
    amount: Mapped[float] = mapped_column(Float, default=0)
    quantity: Mapped[float] = mapped_column(Float, default=0)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class BusinessProcessPolicy(Base):
    __tablename__ = "business_process_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    process_code: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    required_role: Mapped[str] = mapped_column(String(120), default="")
    permission_key: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(40), default="active")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "process_code", "action"),)


class BusinessProcessLineItemRevision(Base):
    __tablename__ = "business_process_line_item_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    line_item_id: Mapped[int] = mapped_column(ForeignKey("business_process_line_items.id"), index=True)
    process_instance_id: Mapped[int] = mapped_column(ForeignKey("business_process_instances.id"), index=True)
    previous_version: Mapped[int] = mapped_column(Integer)
    new_version: Mapped[int] = mapped_column(Integer)
    previous_amount: Mapped[float] = mapped_column(Float, default=0)
    new_amount: Mapped[float] = mapped_column(Float, default=0)
    previous_quantity: Mapped[float] = mapped_column(Float, default=0)
    new_quantity: Mapped[float] = mapped_column(Float, default=0)
    previous_description: Mapped[str] = mapped_column(Text, default="")
    new_description: Mapped[str] = mapped_column(Text, default="")
    previous_status: Mapped[str] = mapped_column(String(40), default="")
    new_status: Mapped[str] = mapped_column(String(40), default="")
    change_note: Mapped[str] = mapped_column(Text, default="")
    changed_by: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class BusinessProcessTemplate(Base):
    __tablename__ = "business_process_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    form_schema: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(40), default="Draft")
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    steps: Mapped[list["BusinessProcessStepTemplate"]] = relationship(back_populates="template")
    transitions: Mapped[list["BusinessProcessTransitionTemplate"]] = relationship(back_populates="template")

    __table_args__ = (UniqueConstraint("tenant_id", "code"),)


class BusinessProcessStepTemplate(Base):
    __tablename__ = "business_process_step_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("business_process_templates.id"), index=True)
    step_order: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120))
    detail: Mapped[str] = mapped_column(String(260), default="")
    owner_role: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(40), default="Queued")
    tone: Mapped[str] = mapped_column(String(40), default="queued")

    template: Mapped[BusinessProcessTemplate] = relationship(back_populates="steps")

    __table_args__ = (UniqueConstraint("tenant_id", "template_id", "step_order"),)


class BusinessProcessTransitionTemplate(Base):
    __tablename__ = "business_process_transition_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("business_process_templates.id"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    from_step: Mapped[str] = mapped_column(String(120), default="")
    to_step: Mapped[str] = mapped_column(String(120), default="")
    process_status: Mapped[str] = mapped_column(String(40), default="in_review")
    ball_in_court: Mapped[str] = mapped_column(String(160), default="")
    from_status: Mapped[str] = mapped_column(String(40), default="Complete")
    from_tone: Mapped[str] = mapped_column(String(40), default="complete")
    to_status: Mapped[str] = mapped_column(String(40), default="Active")
    to_tone: Mapped[str] = mapped_column(String(40), default="active")
    requires_approval: Mapped[bool] = mapped_column(default=False)
    permission_key: Mapped[str] = mapped_column(String(80), default="")

    template: Mapped[BusinessProcessTemplate] = relationship(back_populates="transitions")


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(180))
    resource_type: Mapped[str] = mapped_column(String(60))
    unit_of_measure: Mapped[str] = mapped_column(String(30), default="hr")


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    control_account_id: Mapped[int] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    cbs_code: Mapped[str] = mapped_column(String(80))
    bac: Mapped[float] = mapped_column(Float)
    cost_loaded_pv: Mapped[float] = mapped_column(Float)

    control_account: Mapped[ControlAccount] = relationship(back_populates="budgets")


class CostRecord(Base):
    __tablename__ = "cost_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    control_account_id: Mapped[int] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    source: Mapped[CostSource] = mapped_column(Enum(CostSource))
    amount: Mapped[float] = mapped_column(Float)
    incurred_on: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(String(260))

    control_account: Mapped[ControlAccount] = relationship(back_populates="costs")


class FundingSource(Base):
    __tablename__ = "funding_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(180))
    source_of_funds: Mapped[str] = mapped_column(String(180), default="")
    funding_type: Mapped[str] = mapped_column(String(80), default="")
    authorization_ref: Mapped[str] = mapped_column(String(160), default="")
    usage_restrictions: Mapped[str] = mapped_column(Text, default="")
    usage_rules: Mapped[str] = mapped_column(Text, default="")
    amount: Mapped[float] = mapped_column(Float, default=0)
    funds_available: Mapped[float] = mapped_column(Float, default=0)
    funds_committed: Mapped[float] = mapped_column(Float, default=0)
    funds_executed: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    status: Mapped[str] = mapped_column(String(40), default="approved")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "code"),)

    @property
    def approved_amount(self) -> float:
        return float(self.amount or 0)

    @property
    def balance(self) -> float:
        return float(self.funds_available or 0)


class ControlAccountFundingAllocation(Base):
    __tablename__ = "control_account_funding_allocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    control_account_id: Mapped[int] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    funding_source_id: Mapped[int] = mapped_column(ForeignKey("funding_sources.id"), index=True)
    allocated_amount: Mapped[float] = mapped_column(Float, default=0)
    committed_amount: Mapped[float] = mapped_column(Float, default=0)
    actual_amount: Mapped[float] = mapped_column(Float, default=0)
    forecast_amount: Mapped[float] = mapped_column(Float, default=0)
    distribution_note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="active")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "control_account_id", "funding_source_id"),)


class CostBreakdownStructure(Base):
    __tablename__ = "cost_breakdown_structures"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("cost_breakdown_structures.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    cost_category: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "code"),)


class CostCode(Base):
    __tablename__ = "cost_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    wbs_id: Mapped[int] = mapped_column(ForeignKey("wbs.id"), index=True)
    control_account_id: Mapped[int] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    cbs_id: Mapped[int] = mapped_column(ForeignKey("cost_breakdown_structures.id"), index=True)
    fbs_id: Mapped[int] = mapped_column(ForeignKey("funding_sources.id"), index=True)
    contract_ref: Mapped[str] = mapped_column(String(120), default="")
    code: Mapped[str] = mapped_column(String(160), index=True)
    budget: Mapped[float] = mapped_column(Float, default=0)
    funds_available: Mapped[float] = mapped_column(Float, default=0)
    commitments: Mapped[float] = mapped_column(Float, default=0)
    actual_costs: Mapped[float] = mapped_column(Float, default=0)
    forecast: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "code"),)


class CashFlowPeriod(Base):
    __tablename__ = "cash_flow_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    period_label: Mapped[str] = mapped_column(String(40), index=True)
    planned_inflow: Mapped[float] = mapped_column(Float, default=0)
    planned_outflow: Mapped[float] = mapped_column(Float, default=0)
    actual_inflow: Mapped[float] = mapped_column(Float, default=0)
    actual_outflow: Mapped[float] = mapped_column(Float, default=0)
    forecast_outflow: Mapped[float] = mapped_column(Float, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "period_label"),)


class ProgressRecord(Base):
    __tablename__ = "progress_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    control_account_id: Mapped[int] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    physical_percent: Mapped[float] = mapped_column(Float)
    quantity_installed: Mapped[float] = mapped_column(Float)
    labor_hours: Mapped[float] = mapped_column(Float)
    reported_on: Mapped[date] = mapped_column(Date)
    evidence_ref: Mapped[str] = mapped_column(String(260), default="")

    control_account: Mapped[ControlAccount] = relationship(back_populates="progress")


class KPI(Base):
    __tablename__ = "kpis"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    period: Mapped[str] = mapped_column(String(40), default="current")
    pv: Mapped[float] = mapped_column(Float)
    ev: Mapped[float] = mapped_column(Float)
    ac: Mapped[float] = mapped_column(Float)
    spi: Mapped[float] = mapped_column(Float)
    cpi: Mapped[float] = mapped_column(Float)
    sv: Mapped[float] = mapped_column(Float)
    cv: Mapped[float] = mapped_column(Float)
    bac: Mapped[float] = mapped_column(Float)
    eac: Mapped[float] = mapped_column(Float)
    etc: Mapped[float] = mapped_column(Float)
    vac: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ControlSnapshot(Base):
    __tablename__ = "control_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    period_label: Mapped[str] = mapped_column(String(40), index=True)
    data_date: Mapped[date | None] = mapped_column(Date)
    pv: Mapped[float] = mapped_column(Float)
    ev: Mapped[float] = mapped_column(Float)
    ac: Mapped[float] = mapped_column(Float)
    spi: Mapped[float] = mapped_column(Float)
    cpi: Mapped[float] = mapped_column(Float)
    sv: Mapped[float] = mapped_column(Float)
    cv: Mapped[float] = mapped_column(Float)
    bac: Mapped[float] = mapped_column(Float)
    eac: Mapped[float] = mapped_column(Float)
    etc: Mapped[float] = mapped_column(Float)
    vac: Mapped[float] = mapped_column(Float)
    productivity_index: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "control_account_id", "period_label"),)


class ForecastScenario(Base):
    __tablename__ = "forecast_scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    period_label: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(120))
    method: Mapped[str] = mapped_column(String(120))
    cpi_factor: Mapped[float] = mapped_column(Float)
    spi_factor: Mapped[float] = mapped_column(Float)
    eac: Mapped[float] = mapped_column(Float)
    etc: Mapped[float] = mapped_column(Float)
    vac: Mapped[float] = mapped_column(Float)
    completion_risk: Mapped[str] = mapped_column(String(40), default="medium")
    summary: Mapped[str] = mapped_column(String(360), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "period_label", "name"),)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    severity: Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity))
    rule: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(String(360))
    recommendation: Mapped[str] = mapped_column(String(360))
    status: Mapped[str] = mapped_column(String(40), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    title: Mapped[str] = mapped_column(String(220))
    deviation: Mapped[str] = mapped_column(Text)
    cost_impact: Mapped[float] = mapped_column(Float, default=0)
    schedule_impact_days: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus), default=WorkflowStatus.analyzing)


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    title: Mapped[str] = mapped_column(String(220))
    causality: Mapped[str] = mapped_column(Text)
    impact: Mapped[str] = mapped_column(Text)
    evidence_summary: Mapped[str] = mapped_column(Text)
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus), default=WorkflowStatus.analyzing)


class ClaimEntitlementItem(Base):
    __tablename__ = "claim_entitlement_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    practice_source: Mapped[str] = mapped_column(String(40), default="RP120R-21")
    category: Mapped[str] = mapped_column(String(120), index=True)
    element: Mapped[str] = mapped_column(String(220))
    requirement: Mapped[str] = mapped_column(Text)
    assessment: Mapped[str] = mapped_column(Text, default="")
    evidence_ref: Mapped[str] = mapped_column(String(260), default="")
    status: Mapped[str] = mapped_column(String(40), default="gap")
    weight: Mapped[float] = mapped_column(Float, default=1)
    score: Mapped[float] = mapped_column(Float, default=0)
    sequence_no: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ContractNotice(Base):
    __tablename__ = "contract_notices"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), index=True)
    claim_id: Mapped[int | None] = mapped_column(ForeignKey("claims.id"), index=True)
    change_request_id: Mapped[int | None] = mapped_column(ForeignKey("change_requests.id"), index=True)
    notice_type: Mapped[str] = mapped_column(String(80), default="notice")
    subject: Mapped[str] = mapped_column(String(260))
    reference: Mapped[str] = mapped_column(String(120), default="")
    event_date: Mapped[date | None] = mapped_column(Date)
    notice_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    days_late: Mapped[int] = mapped_column(Integer, default=0)
    compliance_status: Mapped[str] = mapped_column(String(40), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ClaimImpactAnalysis(Base):
    __tablename__ = "claim_impact_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    method: Mapped[str] = mapped_column(String(120))
    impacted_activity: Mapped[str] = mapped_column(String(160), default="")
    cause: Mapped[str] = mapped_column(Text, default="")
    effect: Mapped[str] = mapped_column(Text, default="")
    schedule_impact_days: Mapped[int] = mapped_column(Integer, default=0)
    cost_impact: Mapped[float] = mapped_column(Float, default=0)
    productivity_loss_percent: Mapped[float] = mapped_column(Float, default=0)
    evidence_ref: Mapped[str] = mapped_column(String(260), default="")
    confidence_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(220))
    occurred_on: Mapped[date] = mapped_column(Date)
    contractual_notice_required: Mapped[bool] = mapped_column(default=False)


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    funding_source_id: Mapped[int | None] = mapped_column(ForeignKey("funding_sources.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(220))
    counterparty: Mapped[str] = mapped_column(String(180))
    contract_type: Mapped[str] = mapped_column(String(80), default="EPC")
    value: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(40), default="active")

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "code"),)


class ScheduleOfValueLine(Base):
    __tablename__ = "schedule_of_value_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    line_no: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    amount: Mapped[float] = mapped_column(Float, default=0)
    cbs_id: Mapped[int] = mapped_column(ForeignKey("cost_breakdown_structures.id"), index=True)
    wbs_id: Mapped[int | None] = mapped_column(ForeignKey("wbs.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="active")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "contract_id", "line_no"),)


class CommitmentFundingLine(Base):
    __tablename__ = "commitment_funding_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id"), index=True)
    sov_line_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_of_value_lines.id"), index=True)
    funding_source_id: Mapped[int] = mapped_column(ForeignKey("funding_sources.id"), index=True)
    amount: Mapped[float] = mapped_column(Float, default=0)
    consumed_amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(40), default="active")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class RateSheet(Base):
    __tablename__ = "rate_sheets"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(180), default="")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "code"),)


class RateSheetLine(Base):
    __tablename__ = "rate_sheet_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    rate_sheet_id: Mapped[int] = mapped_column(ForeignKey("rate_sheets.id"), index=True)
    cbs_code: Mapped[str] = mapped_column(String(120), index=True)
    unit_rate: Mapped[float] = mapped_column(Float, default=0)
    multiplier: Mapped[float] = mapped_column(Float, default=1)
    status: Mapped[str] = mapped_column(String(40), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "rate_sheet_id", "cbs_code"),)


class ActivitySheetRecostRun(Base):
    __tablename__ = "activity_sheet_recost_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    activity_sheet_id: Mapped[int] = mapped_column(ForeignKey("activity_sheets.id"), index=True)
    rate_sheet_id: Mapped[int] = mapped_column(ForeignKey("rate_sheets.id"), index=True)
    run_no: Mapped[int] = mapped_column(Integer, default=1)
    updated_rows: Mapped[int] = mapped_column(Integer, default=0)
    total_planned_cost: Mapped[float] = mapped_column(Float, default=0)
    total_planned_value: Mapped[float] = mapped_column(Float, default=0)
    created_by: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "activity_sheet_id", "run_no"),)


class ActivitySheetRecostRunLine(Base):
    __tablename__ = "activity_sheet_recost_run_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    recost_run_id: Mapped[int] = mapped_column(ForeignKey("activity_sheet_recost_runs.id"), index=True)
    activity_sheet_row_id: Mapped[int] = mapped_column(ForeignKey("activity_sheet_rows.id"), index=True)
    external_activity_id: Mapped[str] = mapped_column(String(120), default="")
    cbs_code: Mapped[str] = mapped_column(String(120), default="")
    previous_planned_cost: Mapped[float] = mapped_column(Float, default=0)
    new_planned_cost: Mapped[float] = mapped_column(Float, default=0)
    previous_planned_value: Mapped[float] = mapped_column(Float, default=0)
    new_planned_value: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    funding_source_id: Mapped[int | None] = mapped_column(ForeignKey("funding_sources.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), index=True)
    po_number: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(String(260), default="")
    vendor: Mapped[str] = mapped_column(String(180), default="")
    committed_amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(40), default="issued")
    issued_on: Mapped[date | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "po_number"),)


class PaymentCertificate(Base):
    __tablename__ = "payment_certificates"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), index=True)
    purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    certificate_no: Mapped[str] = mapped_column(String(120), index=True)
    period_label: Mapped[str] = mapped_column(String(40), default="")
    certified_amount: Mapped[float] = mapped_column(Float, default=0)
    retained_amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(40), default="certified")
    certified_on: Mapped[date | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "certificate_no"),)


class WarehouseReceipt(Base):
    __tablename__ = "warehouse_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), index=True)
    purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    receipt_no: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(String(260), default="")
    received_quantity: Mapped[float] = mapped_column(Float, default=0)
    unit_cost: Mapped[float] = mapped_column(Float, default=0)
    received_value: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(40), default="accepted")
    received_on: Mapped[date | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "receipt_no"),)


class RFQPackage(Base):
    __tablename__ = "rfq_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    package_no: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(220))
    scope_summary: Mapped[str] = mapped_column(Text, default="")
    procurement_method: Mapped[str] = mapped_column(String(80), default="RFQ")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    budget_amount: Mapped[float] = mapped_column(Float, default=0)
    issue_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "package_no"),)


class RFQBid(Base):
    __tablename__ = "rfq_bids"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    rfq_package_id: Mapped[int] = mapped_column(ForeignKey("rfq_packages.id"), index=True)
    bidder_name: Mapped[str] = mapped_column(String(180))
    bid_amount: Mapped[float] = mapped_column(Float, default=0)
    technical_score: Mapped[float] = mapped_column(Float, default=0)
    commercial_score: Mapped[float] = mapped_column(Float, default=0)
    schedule_score: Mapped[float] = mapped_column(Float, default=0)
    risk_score: Mapped[float] = mapped_column(Float, default=0)
    weighted_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(40), default="received")
    submitted_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "rfq_package_id", "bidder_name"),)


class ContractCommunication(Base):
    __tablename__ = "contract_communications"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), index=True)
    communication_type: Mapped[str] = mapped_column(String(80), default="letter")
    subject: Mapped[str] = mapped_column(String(260))
    reference: Mapped[str] = mapped_column(String(160), default="")
    sent_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="issued")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    document_number: Mapped[str] = mapped_column(String(120), default="", index=True)
    revision: Mapped[str] = mapped_column(String(40), default="A")
    revision_date: Mapped[date | None] = mapped_column(Date)
    linked_entity_type: Mapped[str] = mapped_column(String(80))
    linked_entity_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(220))
    doc_type: Mapped[str] = mapped_column(String(80))
    discipline: Mapped[str] = mapped_column(String(80), default="")
    organization: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(40), default="current")
    review_status: Mapped[str] = mapped_column(String(40), default="not_started")
    confidentiality: Mapped[str] = mapped_column(String(40), default="project")
    file_name: Mapped[str] = mapped_column(String(260), default="")
    uri: Mapped[str] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class DocumentAttachment(Base):
    __tablename__ = "document_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    original_file_name: Mapped[str] = mapped_column(String(260))
    stored_file_name: Mapped[str] = mapped_column(String(260))
    storage_path: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(160), default="application/octet-stream")
    extension: Mapped[str] = mapped_column(String(20), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(40), default="upload")
    uploaded_by: Mapped[str] = mapped_column(String(160), default="system")
    scan_status: Mapped[str] = mapped_column(String(40), default="not_scanned")
    validation_message: Mapped[str] = mapped_column(String(360), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class DocumentTransmittal(Base):
    __tablename__ = "document_transmittals"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    transmittal_no: Mapped[str] = mapped_column(String(120), index=True)
    subject: Mapped[str] = mapped_column(String(260))
    purpose: Mapped[str] = mapped_column(String(80), default="for_review")
    recipient_org: Mapped[str] = mapped_column(String(160), default="")
    recipient_contact: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(40), default="sent")
    sent_on: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[str] = mapped_column(String(160), default="system")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "transmittal_no"),)


class DocumentTransmittalItem(Base):
    __tablename__ = "document_transmittal_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    transmittal_id: Mapped[int] = mapped_column(ForeignKey("document_transmittals.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    document_number: Mapped[str] = mapped_column(String(120), default="")
    revision: Mapped[str] = mapped_column(String(40), default="")
    action_required: Mapped[str] = mapped_column(String(80), default="review")
    response_status: Mapped[str] = mapped_column(String(40), default="outstanding")

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "transmittal_id", "document_id"),)


class DocumentReview(Base):
    __tablename__ = "document_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    reviewer_role: Mapped[str] = mapped_column(String(120), default="Document Control")
    review_status: Mapped[str] = mapped_column(String(40), default="outstanding")
    comments: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[date | None] = mapped_column(Date)
    closed_on: Mapped[date | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ProjectMail(Base):
    __tablename__ = "project_mail"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    mail_no: Mapped[str] = mapped_column(String(120), index=True)
    mail_type: Mapped[str] = mapped_column(String(80), default="letter")
    subject: Mapped[str] = mapped_column(String(260))
    from_role: Mapped[str] = mapped_column(String(120), default="")
    to_role: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(40), default="outstanding")
    response_required: Mapped[bool] = mapped_column(default=True)
    sent_on: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    closed_on: Mapped[date | None] = mapped_column(Date)
    body: Mapped[str] = mapped_column(Text, default="")
    linked_entity_type: Mapped[str] = mapped_column(String(80), default="")
    linked_entity_id: Mapped[int | None] = mapped_column(Integer)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "mail_no"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), index=True)
    actor: Mapped[str] = mapped_column(String(160), default="system")
    action: Mapped[str] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ControlAgentRun(Base):
    __tablename__ = "control_agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    agent_code: Mapped[str] = mapped_column(String(80), index=True)
    agent_name: Mapped[str] = mapped_column(String(160))
    run_mode: Mapped[str] = mapped_column(String(40), default="deterministic")
    model_name: Mapped[str] = mapped_column(String(120), default="deterministic-control-audit-v1")
    status: Mapped[str] = mapped_column(String(40), default="completed")
    score: Mapped[int] = mapped_column(Integer, default=100)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    findings: Mapped[list["ControlAgentFinding"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class ControlAgentFinding(Base):
    __tablename__ = "control_agent_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("control_agent_runs.id"), index=True)
    severity: Mapped[str] = mapped_column(String(40), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(220))
    evidence: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[str] = mapped_column(Text, default="")
    owner_role: Mapped[str] = mapped_column(String(120), default="")
    entity_type: Mapped[str] = mapped_column(String(80), default="")
    entity_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    run: Mapped[ControlAgentRun] = relationship(back_populates="findings")
