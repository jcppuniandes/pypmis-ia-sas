from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    code: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(220))
    phase: Mapped[str] = mapped_column(String(80), default="Execution")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id"),)


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(180), index=True)
    full_name: Mapped[str] = mapped_column(String(180))
    title: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(40), default="active")

    __table_args__ = (UniqueConstraint("tenant_id", "email"),)


class AuthCredential(Base):
    __tablename__ = "auth_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="local")
    password_hash: Mapped[str] = mapped_column(String(220))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "version_no"),)


class ControlPeriod(Base):
    __tablename__ = "control_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    period_label: Mapped[str] = mapped_column(String(40), index=True)
    data_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "period_label"),)


class WBS(Base):
    __tablename__ = "wbs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("wbs.id"))
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(220))


class ControlAccount(Base):
    __tablename__ = "control_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    wbs_id: Mapped[int] = mapped_column(ForeignKey("wbs.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(220))
    responsible: Mapped[str] = mapped_column(String(160))
    discipline: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("work_packages.id"), index=True)
    package_type: Mapped[str] = mapped_column(String(20), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(260))
    discipline: Mapped[str] = mapped_column(String(80), default="")
    sequence_no: Mapped[int] = mapped_column(Integer, default=0)
    path_of_construction: Mapped[str] = mapped_column(String(260), default="")
    owner_role: Mapped[str] = mapped_column(String(120), default="Workface Planner")
    readiness_status: Mapped[str] = mapped_column(String(60), default="constraint_review")
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_finish: Mapped[date | None] = mapped_column(Date)
    progress_percent: Mapped[float] = mapped_column(Float, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    blocking: Mapped[bool] = mapped_column(default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    amount: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    status: Mapped[str] = mapped_column(String(40), default="approved")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(220))
    counterparty: Mapped[str] = mapped_column(String(180))
    contract_type: Mapped[str] = mapped_column(String(80), default="EPC")
    value: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(40), default="active")

    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "code"),)


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("control_accounts.id"), index=True)
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"), index=True)
    po_number: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(String(260), default="")
    vendor: Mapped[str] = mapped_column(String(180), default="")
    committed_amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(40), default="issued")
    issued_on: Mapped[date | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
