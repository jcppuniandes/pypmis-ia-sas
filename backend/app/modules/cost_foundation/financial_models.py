"""Cost recognition and reconciliation only; never contractual or ledger authority."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.modules.cost_foundation.models import MutableCost
from app.modules.scope_foundation.models import ScopeRecord


class CostFXRate(MutableCost, ScopeRecord, Base):
    __tablename__ = "cost_fx_rates"
    code: Mapped[str] = mapped_column(String(120))
    from_currency: Mapped[str] = mapped_column(String(8))
    to_currency: Mapped[str] = mapped_column(String(8))
    rate: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    conversion_basis: Mapped[str] = mapped_column(String(1000))
    source_reference: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    content_hash: Mapped[str] = mapped_column(String(64))
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("cost_fx_rates.id"))
    published_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "code", "revision", name="uq_cost_fx_revision"),
        CheckConstraint("rate > 0 AND from_currency <> to_currency", name="ck_cost_fx_rate"),
        CheckConstraint("status IN ('DRAFT','PUBLISHED')", name="ck_cost_fx_status"),
        CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="ck_cost_fx_dates"),
    )


class CostActualEntry(MutableCost, ScopeRecord, Base):
    __tablename__ = "cost_actual_entries"
    entry_kind: Mapped[str] = mapped_column(String(24), default="ORIGINAL")
    adjusts_entry_id: Mapped[int | None] = mapped_column(ForeignKey("cost_actual_entries.id"))
    source_system: Mapped[str] = mapped_column(String(120))
    source_reference: Mapped[str] = mapped_column(String(260))
    source_type: Mapped[str] = mapped_column(String(80))
    posting_date: Mapped[date] = mapped_column(Date)
    recognition_date: Mapped[date] = mapped_column(Date)
    period_id: Mapped[int] = mapped_column(ForeignKey("project_controls_periods.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(8))
    cbs_id: Mapped[int | None] = mapped_column(ForeignKey("cost_cbs.id"))
    cost_code_id: Mapped[int | None] = mapped_column(ForeignKey("cost_code_dictionary.id"))
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("cost_control_accounts.id"))
    evidence_ref: Mapped[str] = mapped_column(String(1000))
    description: Mapped[str] = mapped_column(Text, default="")
    fx_rate_id: Mapped[int | None] = mapped_column(ForeignKey("cost_fx_rates.id"))
    status: Mapped[str] = mapped_column(String(24), default="IMPORTED")
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "source_system", "source_reference", name="uq_cost_actual_source"
        ),
        CheckConstraint("status IN ('IMPORTED','RECOGNIZED','REJECTED')", name="ck_cost_actual_status"),
        CheckConstraint(
            "(entry_kind = 'ORIGINAL' AND adjusts_entry_id IS NULL AND amount > 0) OR (entry_kind = 'ADJUSTMENT' AND adjusts_entry_id IS NOT NULL AND amount <> 0)",
            name="ck_cost_actual_kind",
        ),
    )


class CostCommitmentReference(MutableCost, ScopeRecord, Base):
    __tablename__ = "cost_commitment_references"
    source_system: Mapped[str] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(String(40))
    source_reference: Mapped[str] = mapped_column(String(260))
    source_revision: Mapped[str] = mapped_column(String(120))
    source_hash: Mapped[str] = mapped_column(String(64))
    source_record_id: Mapped[int | None] = mapped_column()
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("cost_commitment_references.id"))
    source_document: Mapped[str] = mapped_column(String(1000))
    source_approval_status: Mapped[str] = mapped_column(String(40))
    economic_origin: Mapped[str] = mapped_column(String(260))
    parent_economic_origin: Mapped[str | None] = mapped_column(String(260))
    inclusion_mode: Mapped[str] = mapped_column(String(24))
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    currency: Mapped[str] = mapped_column(String(8))
    effective_date: Mapped[date] = mapped_column(Date)
    cbs_id: Mapped[int | None] = mapped_column(ForeignKey("cost_cbs.id"))
    cost_code_id: Mapped[int | None] = mapped_column(ForeignKey("cost_code_dictionary.id"))
    control_account_id: Mapped[int | None] = mapped_column(ForeignKey("cost_control_accounts.id"))
    fx_rate_id: Mapped[int | None] = mapped_column(ForeignKey("cost_fx_rates.id"))
    status: Mapped[str] = mapped_column(String(24), default="PROPOSED")
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "project_workspace_id",
            "source_system",
            "source_type",
            "source_reference",
            "source_revision",
            name="uq_cost_commitment_source",
        ),
        CheckConstraint("status IN ('PROPOSED','VERIFIED','REJECTED')", name="ck_cost_commitment_status"),
        CheckConstraint(
            "inclusion_mode IN ('INCLUDED','CALL_OFF','ADDITIVE','REFERENCE_ONLY')", name="ck_cost_commitment_inclusion"
        ),
        CheckConstraint("amount >= 0", name="ck_cost_commitment_amount"),
    )


def _financial_guard(_mapper, _connection, record):
    state = inspect(record)
    previous = state.attrs.status.history.deleted
    prior_status = previous[0] if previous else record.status
    if prior_status in {"PUBLISHED", "RECOGNIZED", "VERIFIED", "REJECTED"}:
        raise ValueError("Published FX, recognized Actual and verified obligation projection are immutable")
    allowed = {
        "status",
        "version",
        "revision",
        "updated_by",
        "updated_at",
        "published_by",
        "published_at",
        "approved_by",
        "approved_at",
        "verified_by",
        "verified_at",
    }
    if any(attr.history.has_changes() for attr in state.attrs if attr.key not in allowed):
        raise ValueError("Financial source inputs are immutable; create a successor or adjustment")


def _financial_delete(_mapper, _connection, _record):
    raise ValueError("Cost financial source history cannot be deleted")


for _model in (CostFXRate, CostActualEntry, CostCommitmentReference):
    event.listen(_model, "before_update", _financial_guard)
    event.listen(_model, "before_delete", _financial_delete)
