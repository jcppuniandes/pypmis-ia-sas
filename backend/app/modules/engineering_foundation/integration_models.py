"""Engineering-owned append-only links; target records retain their authorities."""

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text, event, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base
from app.modules.scope_foundation.models import ScopeRecord


class EngineeringMapping(ScopeRecord, Base):
    __tablename__ = "engineering_mappings"

    revision_id: Mapped[int | None] = mapped_column(ForeignKey("engineering_revisions.id"))
    design_package_id: Mapped[int | None] = mapped_column(ForeignKey("engineering_design_packages.id"))
    target_kind: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[int | None] = mapped_column()
    schedule_version_id: Mapped[int | None] = mapped_column(ForeignKey("schedule_versions.id"))
    external_id: Mapped[str | None] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(12))
    target_snapshot_json: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "((revision_id IS NOT NULL AND design_package_id IS NULL) OR "
            "(revision_id IS NULL AND design_package_id IS NOT NULL AND target_kind='EWP'))",
            name="ck_engineering_mapping_owner",
        ),
        CheckConstraint(
            "target_kind IN ('EWP','CWP','IWP','CWA','SCOPE','PLAN','WBS','ACTIVITY','MILESTONE',"
            "'CBS','COST_CODE','CONTROL_ACCOUNT')",
            name="ck_engineering_mapping_kind",
        ),
        CheckConstraint(
            "((target_kind IN ('WBS','ACTIVITY','MILESTONE') AND target_id IS NULL "
            "AND schedule_version_id IS NOT NULL AND external_id IS NOT NULL AND length(external_id)>0) "
            "OR (target_kind NOT IN ('WBS','ACTIVITY','MILESTONE') AND target_id IS NOT NULL "
            "AND schedule_version_id IS NULL AND external_id IS NULL))",
            name="ck_engineering_mapping_target",
        ),
        CheckConstraint("action IN ('SET','REMOVE') AND version > 1", name="ck_engineering_mapping_action"),
        Index(
            "uq_engineering_revision_mapping_version",
            "revision_id",
            "version",
            unique=True,
            postgresql_where=text("revision_id IS NOT NULL"),
            sqlite_where=text("revision_id IS NOT NULL"),
        ),
        Index(
            "uq_engineering_package_mapping_version",
            "design_package_id",
            "version",
            unique=True,
            postgresql_where=text("design_package_id IS NOT NULL"),
            sqlite_where=text("design_package_id IS NOT NULL"),
        ),
        Index(
            "ix_engineering_mapping_reverse",
            "tenant_id",
            "project_workspace_id",
            "target_kind",
            "target_id",
            "id",
        ),
    )


def _immutable(_mapper, _connection, _row):
    raise ValueError("ENGINEERING_MAPPING_APPEND_ONLY")


event.listen(EngineeringMapping, "before_update", _immutable)
event.listen(EngineeringMapping, "before_delete", _immutable)
