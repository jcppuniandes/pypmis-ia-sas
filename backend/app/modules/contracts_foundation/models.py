"""Contract aggregates and independent commercial obligations."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base
from app.modules.scope_foundation.models import ScopeRecord

MONEY = Numeric(24, 8)


class CommercialRecord(ScopeRecord):
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))


class ContractPackage(CommercialRecord, Base):
    __tablename__ = "contract_packages"
    package_code: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text)
    contract_strategy: Mapped[str] = mapped_column(Text)
    contract_type: Mapped[str] = mapped_column(String(80))
    commercial_model: Mapped[str] = mapped_column(String(80))
    responsible_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    planned_award_date: Mapped[date | None] = mapped_column(Date)
    planned_execution_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(8))
    estimated_value: Mapped[Decimal] = mapped_column(MONEY)
    procurement_sources: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "package_code", name="uq_o2c_package_code"),
        CheckConstraint("estimated_value >= 0", name="ck_o2c_package_estimate"),
        CheckConstraint("status IN ('DRAFT','PLANNED','CANCELLED')", name="ck_o2c_package_state"),
    )


class OperationalContract(CommercialRecord, Base):
    """Canonical authority; the legacy project Contract is not imported or overwritten."""

    __tablename__ = "operational_contracts"
    contract_number: Mapped[str] = mapped_column(String(120))
    contract_package_id: Mapped[int] = mapped_column(ForeignKey("contract_packages.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text)
    contract_type: Mapped[str] = mapped_column(String(80))
    commercial_model: Mapped[str] = mapped_column(String(80))
    vendor_id: Mapped[int] = mapped_column(ForeignKey("procurement_vendors.id"))
    counterparty: Mapped[dict] = mapped_column(JSON)
    currency: Mapped[str] = mapped_column(String(8))
    original_contract_value: Mapped[Decimal] = mapped_column(MONEY)
    effective_date: Mapped[date] = mapped_column(Date)
    commencement_date: Mapped[date] = mapped_column(Date)
    planned_completion_date: Mapped[date] = mapped_column(Date)
    governing_reference: Mapped[str] = mapped_column(Text)
    source_instrument_type: Mapped[str | None] = mapped_column(String(40))
    source_instrument_id: Mapped[int | None] = mapped_column()
    source_version: Mapped[int | None] = mapped_column()
    source_hash: Mapped[str | None] = mapped_column(String(64))
    source_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("contract_versions.id", use_alter=True, name="fk_o2c_contract_current_version")
    )
    executed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime)
    execution_date: Mapped[date | None] = mapped_column(Date)
    execution_document: Mapped[dict] = mapped_column(JSON, default=dict)
    supporting_documents: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "contract_number", name="uq_o2c_contract_number"),
        CheckConstraint("original_contract_value >= 0", name="ck_o2c_contract_value"),
        CheckConstraint(
            "effective_date <= commencement_date AND commencement_date <= planned_completion_date",
            name="ck_o2c_contract_dates",
        ),
        CheckConstraint("status IN ('DRAFT','APPROVED','EXECUTED','EFFECTIVE')", name="ck_o2c_contract_state"),
    )


class ContractVersion(CommercialRecord, Base):
    __tablename__ = "contract_versions"
    contract_id: Mapped[int] = mapped_column(ForeignKey("operational_contracts.id"), index=True)
    revision: Mapped[int] = mapped_column()
    effective_date: Mapped[date] = mapped_column(Date)
    value: Mapped[Decimal] = mapped_column(MONEY)
    completion_date: Mapped[date] = mapped_column(Date)
    terms_reference: Mapped[str] = mapped_column(Text)
    document_reference: Mapped[dict] = mapped_column(JSON)
    source_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    supersedes_version_id: Mapped[int | None] = mapped_column(ForeignKey("contract_versions.id"), unique=True)
    source_change_id: Mapped[int | None] = mapped_column()
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "contract_id", "revision", name="uq_o2c_contract_revision"
        ),
        CheckConstraint(
            "value >= 0 AND revision > 0 AND effective_date <= completion_date", name="ck_o2c_version_content"
        ),
        CheckConstraint(
            "(status = 'DRAFT' AND approved_by IS NULL AND approved_at IS NULL) OR "
            "(status = 'APPROVED' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_o2c_version_approval",
        ),
    )


class CommercialCommitment(CommercialRecord, Base):
    """Each approved row is an immutable revision; a successor has its own row."""

    __tablename__ = "commercial_commitments"
    commitment_code: Mapped[str] = mapped_column(String(120))
    revision: Mapped[int] = mapped_column()
    contract_id: Mapped[int] = mapped_column(ForeignKey("operational_contracts.id"), index=True)
    contract_version_id: Mapped[int] = mapped_column(ForeignKey("contract_versions.id"))
    vendor_id: Mapped[int] = mapped_column(ForeignKey("procurement_vendors.id"))
    currency: Mapped[str] = mapped_column(String(8))
    committed_amount: Mapped[Decimal] = mapped_column(MONEY)
    effective_date: Mapped[date] = mapped_column(Date)
    commercial_basis: Mapped[str] = mapped_column(Text)
    source_hash: Mapped[str] = mapped_column(String(64))
    contract_version_hash: Mapped[str] = mapped_column(String(64))
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("commercial_commitments.id"), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "commitment_code", "revision", name="uq_o2c_commitment_revision"
        ),
        CheckConstraint("committed_amount > 0 AND revision > 0", name="ck_o2c_commitment_content"),
        CheckConstraint(
            "(status = 'DRAFT' AND approved_by IS NULL AND approved_at IS NULL) OR "
            "(status = 'APPROVED' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_o2c_commitment_approval",
        ),
    )


class ContractHistory(ScopeRecord, Base):
    __tablename__ = "contract_history"
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int] = mapped_column()
    entity_version: Mapped[int] = mapped_column()
    previous_version: Mapped[int | None] = mapped_column()
    event_type: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(Text)
    effective_date: Mapped[date | None] = mapped_column(Date)
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (Index("ix_o2c_history_entity", "tenant_id", "project_workspace_id", "entity_type", "entity_id"),)


CORE_MODELS = (ContractPackage, OperationalContract, ContractVersion, CommercialCommitment, ContractHistory)
