"""Append-only consumer-owned decisions about operational facts, not Field approvals."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.modules.scope_foundation.models import ScopeRecord


class FieldConsumerDecision(ScopeRecord, Base):
    __tablename__ = "field_consumer_decisions"
    consumer: Mapped[str] = mapped_column(String(20))
    source_domain: Mapped[str] = mapped_column(String(30), default="FIELD_OPERATIONS")
    source_entity_type: Mapped[str] = mapped_column(String(40))
    source_entity_id: Mapped[int] = mapped_column()
    source_root_id: Mapped[int] = mapped_column()
    source_version: Mapped[int] = mapped_column()
    source_hash: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observation_date: Mapped[date] = mapped_column(Date)
    effective_period_id: Mapped[int | None] = mapped_column(ForeignKey("project_controls_periods.id"))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    uom: Mapped[str | None] = mapped_column(String(40))
    decision: Mapped[str] = mapped_column(String(20))
    linked_entity_type: Mapped[str | None] = mapped_column(String(60))
    linked_entity_id: Mapped[int | None] = mapped_column()
    mapping_reference: Mapped[dict] = mapped_column(JSON, default=dict)
    source_snapshot: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "project_workspace_id",
            "consumer",
            "source_entity_type",
            "source_root_id",
            "version",
            name="uq_o3a_consumer_stream",
        ),
        CheckConstraint(
            "source_domain='FIELD_OPERATIONS' AND source_version > 0 AND version > 0", name="ck_o3a_consumer_source"
        ),
        CheckConstraint("consumer IN ('PROGRESS','AWP','COST','CONTRACTS','SCHEDULE')", name="ck_o3a_consumer_domain"),
        CheckConstraint("decision IN ('ADOPT','PARTIAL_ADOPT','REJECT')", name="ck_o3a_consumer_decision"),
        CheckConstraint("quantity IS NULL OR quantity > 0", name="ck_o3a_consumer_quantity"),
        Index("ix_o3a_consumer_history", "tenant_id", "project_workspace_id", "consumer", "id"),
    )
