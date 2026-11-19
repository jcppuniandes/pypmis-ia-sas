"""Append-only reference decisions; no financial, physical or forecast projection."""

from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.modules.scope_foundation.models import ScopeRecord

TABLE = "operational_procurement_adoptions"


class ProcurementAdoption(ScopeRecord, Base):
    __tablename__ = TABLE
    consumer: Mapped[str] = mapped_column(String(12))
    source_domain: Mapped[str] = mapped_column(String(20))
    source_entity_type: Mapped[str] = mapped_column(String(40))
    source_entity_id: Mapped[int] = mapped_column()
    source_package_id: Mapped[int] = mapped_column(ForeignKey("procurement_packages.id"))
    source_version: Mapped[int] = mapped_column()
    source_hash: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_at: Mapped[date] = mapped_column(Date)
    consumer_status: Mapped[str] = mapped_column(String(16))
    period_id: Mapped[int | None] = mapped_column(ForeignKey("project_controls_periods.id"))
    consumer_version_id: Mapped[int | None] = mapped_column(ForeignKey("forecast_versions.id"))
    consumer_version: Mapped[int | None] = mapped_column()
    signal_key: Mapped[str | None] = mapped_column(String(80))
    source_forecast_date: Mapped[date | None] = mapped_column(Date)
    context_key: Mapped[str] = mapped_column(String(180))
    mapping_reference: Mapped[dict] = mapped_column(JSON)
    source_snapshot: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("consumer IN ('COST','PROGRESS','FORECAST')", name="ck_op_proc_adoption_consumer"),
        CheckConstraint(
            "source_domain = 'PROCUREMENT' AND source_version > 0 AND version > 0 AND source_entity_id > 0",
            name="ck_op_proc_adoption_source",
        ),
        CheckConstraint("consumer_status IN ('ADOPTED','NOT_ADOPTED')", name="ck_op_proc_adoption_status"),
        CheckConstraint(
            "(consumer='COST' AND period_id IS NULL AND consumer_version_id IS NULL "
            "AND consumer_version IS NULL AND signal_key IS NULL AND source_forecast_date IS NULL) OR "
            "(consumer='PROGRESS' AND period_id IS NOT NULL AND consumer_version_id IS NULL "
            "AND consumer_version IS NULL AND signal_key IS NULL AND source_forecast_date IS NULL) OR "
            "(consumer='FORECAST' AND period_id IS NOT NULL AND consumer_version_id IS NOT NULL "
            "AND consumer_version IS NOT NULL AND consumer_version > 0 AND signal_key IS NOT NULL "
            "AND source_forecast_date IS NOT NULL)",
            name="ck_op_proc_adoption_context",
        ),
        UniqueConstraint(
            "tenant_id",
            "project_workspace_id",
            "consumer",
            "source_entity_type",
            "source_entity_id",
            "context_key",
            "version",
            name="uq_op_proc_adoption_stream",
        ),
        Index("ix_op_proc_adoption_history", "tenant_id", "project_workspace_id", "consumer", "id"),
    )
