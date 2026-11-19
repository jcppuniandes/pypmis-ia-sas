"""Procurement owns the links, not the referenced authority or its lifecycle."""

from datetime import date

from sqlalchemy import JSON, CheckConstraint, Date, ForeignKey, Index, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.modules.scope_foundation.models import ScopeRecord


class ProcurementMapping(ScopeRecord, Base):
    __tablename__ = "procurement_mappings"

    source_kind: Mapped[str] = mapped_column(String(32))
    source_id: Mapped[int]
    target_kind: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[int | None]
    schedule_version_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_versions.id"))
    external_id: Mapped[str | None] = mapped_column(String(160))
    effective_date: Mapped[date] = mapped_column(Date)
    action: Mapped[str] = mapped_column(String(8))
    target_snapshot_json: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "source_kind", "source_id", "version"),
        Index("ix_procurement_mapping_reverse", "tenant_id", "project_workspace_id", "target_kind", "target_id", "id"),
        CheckConstraint(
            "source_id > 0 AND version > 1 AND action IN ('SET','REMOVE')", name="ck_procurement_mapping_action"
        ),
        CheckConstraint(
            "(target_kind IN ('WBS','ACTIVITY','MILESTONE') AND target_id IS NULL AND schedule_version_id IS NOT NULL "
            "AND external_id IS NOT NULL AND length(external_id)>0) OR (target_kind NOT IN ('WBS','ACTIVITY','MILESTONE') "
            "AND target_id > 0 AND target_id IS NOT NULL AND schedule_version_id IS NULL AND external_id IS NULL)",
            name="ck_procurement_mapping_target",
        ),
    )


@event.listens_for(ProcurementMapping, "before_update")
@event.listens_for(ProcurementMapping, "before_delete")
def immutable(_mapper, _connection, _record):
    raise ValueError("PROCUREMENT_MAPPING_APPEND_ONLY")
