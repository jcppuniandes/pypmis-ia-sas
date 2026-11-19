"""Cost-owned append-only decisions about Contracts evidence."""

from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.modules.scope_foundation.models import ScopeRecord

TABLE = "cost_commercial_commitment_adoptions"


class CostCommercialAdoption(ScopeRecord, Base):
    __tablename__ = TABLE
    source_domain: Mapped[str] = mapped_column(String(20))
    source_entity_type: Mapped[str] = mapped_column(String(40))
    source_entity_id: Mapped[int] = mapped_column(ForeignKey("commercial_commitments.id"))
    source_version: Mapped[int] = mapped_column()
    source_hash: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_at: Mapped[date] = mapped_column(Date)
    cbs_id: Mapped[int] = mapped_column(ForeignKey("cost_cbs.id"))
    cost_code_id: Mapped[int] = mapped_column(ForeignKey("cost_code_dictionary.id"))
    control_account_id: Mapped[int] = mapped_column(ForeignKey("cost_control_accounts.id"))
    consumer_status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    source_snapshot: Mapped[dict] = mapped_column(JSON)
    mapping_reference: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "project_workspace_id", "source_entity_id", "version", name="uq_o2c_cost_adoption_stream"
        ),
        Index("ix_o2c_cost_adoption_history", "tenant_id", "project_workspace_id", "id"),
        CheckConstraint(
            "source_domain = 'CONTRACTS' AND source_entity_type = 'COMMERCIAL_COMMITMENT' "
            "AND source_version > 0 AND version > 0",
            name="ck_o2c_cost_adoption_source",
        ),
        CheckConstraint("consumer_status IN ('ADOPTED','NOT_ADOPTED')", name="ck_o2c_cost_adoption_status"),
    )
