"""Canonical commercial records. Legacy project-id authorities remain untouched."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.modules.scope_foundation.models import ScopeRecord


class Profiled:
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    source_hash: Mapped[str] = mapped_column(String(64), default="")


class ContractSOV(Profiled, ScopeRecord, Base):
    __tablename__ = "contract_sovs"
    contract_id: Mapped[int] = mapped_column(ForeignKey("operational_contracts.id"), index=True)
    contract_version_id: Mapped[int] = mapped_column(ForeignKey("contract_versions.id"))
    code: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    currency: Mapped[str] = mapped_column(String(8))
    total_value: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    published_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "contract_id", "code", name="uq_o2c_sov_code"),
        CheckConstraint("total_value > 0 AND status IN ('DRAFT','PUBLISHED')", name="ck_o2c_sov_state"),
    )


class ContractSOVLine(ScopeRecord, Base):
    __tablename__ = "contract_sov_lines"
    sov_id: Mapped[int] = mapped_column(ForeignKey("contract_sovs.id"), index=True)
    line_number: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    uom: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    unit_rate: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    original_value: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    current_value: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    retention_rule: Mapped[str | None] = mapped_column(String(80))
    retention_rate: Mapped[Decimal] = mapped_column(Numeric(10, 8), default=0)
    mappings: Mapped[list] = mapped_column(JSON)
    source_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("sov_id", "line_number", name="uq_o2c_sov_line_number"),
        CheckConstraint(
            "quantity > 0 AND unit_rate > 0 AND current_value > 0 AND retention_rate BETWEEN 0 AND 1",
            name="ck_o2c_sov_line_value",
        ),
    )


class ContractChange(Profiled, ScopeRecord, Base):
    __tablename__ = "contract_changes"
    contract_id: Mapped[int] = mapped_column(ForeignKey("operational_contracts.id"), index=True)
    base_version_id: Mapped[int] = mapped_column(ForeignKey("contract_versions.id"))
    resulting_version_id: Mapped[int | None] = mapped_column(ForeignKey("contract_versions.id"))
    change_number: Mapped[str] = mapped_column(String(120))
    change_type: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    value_delta: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    time_delta: Mapped[int] = mapped_column()
    effective_date: Mapped[date] = mapped_column(Date)
    notice_id: Mapped[int | None] = mapped_column(ForeignKey("operational_contract_notices.id"))
    schedule_references: Mapped[list] = mapped_column(JSON)
    document_reference: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="POTENTIAL")
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "contract_id", "change_number", name="uq_o2c_change_number"
        ),
        CheckConstraint(
            "status IN ('POTENTIAL','REQUESTED','UNDER_REVIEW','ORDER_APPROVED','REJECTED') "
            "AND (value_delta <> 0 OR time_delta <> 0)",
            name="ck_o2c_change_state",
        ),
    )


class PaymentApplication(Profiled, ScopeRecord, Base):
    __tablename__ = "payment_applications"
    contract_id: Mapped[int] = mapped_column(ForeignKey("operational_contracts.id"), index=True)
    contract_version_id: Mapped[int] = mapped_column(ForeignKey("contract_versions.id"))
    sov_id: Mapped[int] = mapped_column(ForeignKey("contract_sovs.id"))
    application_number: Mapped[str] = mapped_column(String(120))
    period_id: Mapped[int] = mapped_column(ForeignKey("project_controls_periods.id"))
    effective_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="SUBMITTED")
    currency: Mapped[str] = mapped_column(String(8))
    applied_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    document_reference: Mapped[dict] = mapped_column(JSON)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "contract_id", "application_number", name="uq_o2c_application_number"
        ),
        CheckConstraint(
            "applied_amount > 0 AND status IN ('SUBMITTED','REVIEWED','REJECTED')", name="ck_o2c_application_state"
        ),
    )


class PaymentApplicationLine(ScopeRecord, Base):
    __tablename__ = "payment_application_lines"
    application_id: Mapped[int] = mapped_column(ForeignKey("payment_applications.id"), index=True)
    sov_line_id: Mapped[int] = mapped_column(ForeignKey("contract_sov_lines.id"), index=True)
    progress_measurement_id: Mapped[int] = mapped_column(ForeignKey("progress_measurements.id"), index=True)
    progress_reference: Mapped[dict] = mapped_column(JSON)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    applied_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    __table_args__ = (
        UniqueConstraint("application_id", "sov_line_id", name="uq_o2c_application_sov_line"),
        CheckConstraint("quantity > 0 AND applied_amount > 0", name="ck_o2c_application_line_positive"),
    )


class OperationalPaymentCertificate(Profiled, ScopeRecord, Base):
    __tablename__ = "operational_payment_certificates"
    application_id: Mapped[int] = mapped_column(ForeignKey("payment_applications.id"), index=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("operational_contracts.id"), index=True)
    contract_version_id: Mapped[int] = mapped_column(ForeignKey("contract_versions.id"))
    certificate_number: Mapped[str] = mapped_column(String(120))
    effective_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    currency: Mapped[str] = mapped_column(String(8))
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    document_reference: Mapped[dict] = mapped_column(JSON)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "contract_id", "certificate_number", name="uq_o2c_certificate_number"
        ),
        CheckConstraint(
            "gross_amount > 0 AND net_amount BETWEEN 0 AND gross_amount AND status IN ('DRAFT','APPROVED','REJECTED')",
            name="ck_o2c_certificate_state",
        ),
    )


class PaymentCertificateLine(ScopeRecord, Base):
    __tablename__ = "payment_certificate_lines"
    certificate_id: Mapped[int] = mapped_column(ForeignKey("operational_payment_certificates.id"), index=True)
    application_line_id: Mapped[int] = mapped_column(ForeignKey("payment_application_lines.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    retention: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=0)
    advance_recovery: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=0)
    deductions: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=0)
    withholdings: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=0)
    other_adjustments: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=0)
    net_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    __table_args__ = (
        UniqueConstraint("certificate_id", "application_line_id", name="uq_o2c_certificate_application_line"),
        CheckConstraint(
            "quantity > 0 AND gross_amount > 0 AND net_amount BETWEEN 0 AND gross_amount "
            "AND retention >= 0 AND advance_recovery >= 0 AND deductions >= 0 "
            "AND withholdings >= 0 AND other_adjustments >= 0",
            name="ck_o2c_certificate_line_value",
        ),
    )


class OperationalContractNotice(Profiled, ScopeRecord, Base):
    __tablename__ = "operational_contract_notices"
    contract_id: Mapped[int] = mapped_column(ForeignKey("operational_contracts.id"), index=True)
    notice_number: Mapped[str] = mapped_column(String(120))
    notice_type: Mapped[str] = mapped_column(String(80))
    sender: Mapped[str] = mapped_column(String(240))
    recipient: Mapped[str] = mapped_column(String(240))
    issue_date: Mapped[date] = mapped_column(Date)
    received_date: Mapped[date | None] = mapped_column(Date)
    subject: Mapped[str] = mapped_column(String(300))
    event_reference: Mapped[str | None] = mapped_column(Text)
    response_due_date: Mapped[date | None] = mapped_column(Date)
    document_reference: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="ISSUED")
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "contract_id", "notice_number", name="uq_o2c_notice_number"
        ),
        CheckConstraint("status IN ('ISSUED','RECEIVED','CLOSED')", name="ck_o2c_notice_state"),
    )


class ContractClaim(Profiled, ScopeRecord, Base):
    __tablename__ = "contract_claims"
    contract_id: Mapped[int] = mapped_column(ForeignKey("operational_contracts.id"), index=True)
    claim_number: Mapped[str] = mapped_column(String(120))
    claim_type: Mapped[str] = mapped_column(String(80))
    cause: Mapped[str] = mapped_column(Text)
    notice_id: Mapped[int | None] = mapped_column(ForeignKey("operational_contract_notices.id"))
    claimed_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    claimed_time: Mapped[int] = mapped_column()
    effective_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(8))
    vendor_id: Mapped[int] = mapped_column(ForeignKey("procurement_vendors.id"))
    documents: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="REGISTERED")
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "contract_id", "claim_number", name="uq_o2c_claim_number"
        ),
        CheckConstraint(
            "claimed_amount >= 0 AND claimed_time >= 0 AND status IN ('REGISTERED','ACCEPTED','REJECTED')",
            name="ck_o2c_claim_state",
        ),
    )


class ContractFinanceReference(ScopeRecord, Base):
    __tablename__ = "contract_finance_references"
    certificate_id: Mapped[int] = mapped_column(ForeignKey("operational_payment_certificates.id"), index=True)
    certificate_hash: Mapped[str] = mapped_column(String(64))
    source_system: Mapped[str] = mapped_column(String(120))
    invoice_reference: Mapped[str] = mapped_column(String(260))
    source_version: Mapped[int] = mapped_column()
    source_hash: Mapped[str] = mapped_column(String(64))
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(8))
    status_reference: Mapped[str] = mapped_column(String(120))
    payment_status: Mapped[str | None] = mapped_column(String(120))
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("contract_finance_references.id"))
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "project_workspace_id",
            "source_system",
            "invoice_reference",
            "source_version",
            name="uq_o2c_finance_ref_revision",
        ),
        CheckConstraint("amount > 0 AND source_version > 0", name="ck_o2c_finance_ref_amount"),
    )


class ContractMapping(ScopeRecord, Base):
    __tablename__ = "contract_mappings"
    source_kind: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[int] = mapped_column()
    target_kind: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[int] = mapped_column()
    action: Mapped[str] = mapped_column(String(12))
    effective_date: Mapped[date] = mapped_column(Date)
    target_snapshot: Mapped[dict] = mapped_column(JSON)
    source_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "source_kind", "source_id", "version", name="uq_o2c_mapping_version"
        ),
        Index("ix_o2c_mapping_source", "tenant_id", "project_workspace_id", "source_kind", "source_id"),
        CheckConstraint("action IN ('SET','REMOVE')", name="ck_o2c_mapping_action"),
    )


APPEND_ONLY = (
    ContractSOVLine,
    PaymentApplicationLine,
    PaymentCertificateLine,
    ContractFinanceReference,
    ContractMapping,
)
TERMINAL = {
    ContractSOV: {"PUBLISHED"},
    ContractChange: {"ORDER_APPROVED", "REJECTED"},
    PaymentApplication: {"REVIEWED", "REJECTED"},
    OperationalPaymentCertificate: {"APPROVED", "REJECTED"},
    OperationalContractNotice: {"CLOSED"},
    ContractClaim: {"ACCEPTED", "REJECTED"},
}
MODELS = (*TERMINAL, *APPEND_ONLY)


def _immutable(_mapper, _connection, _row):
    raise ValueError("Commercial evidence is append-only")


def _terminal(_mapper, _connection, row):
    status_history = inspect(row).attrs.status.history
    previous = status_history.deleted[0] if status_history.deleted else row.status
    if previous in TERMINAL[type(row)]:
        _immutable(_mapper, _connection, row)


for _model in MODELS:
    event.listen(_model, "before_delete", _immutable)
    event.listen(_model, "before_update", _immutable if _model in APPEND_ONLY else _terminal)
