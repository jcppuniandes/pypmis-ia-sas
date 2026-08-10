"""Additive persistence for objectives, classifications and non-hierarchical links."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class EnterpriseStrategicObjective(Base):
    __tablename__ = "enterprise_strategic_objectives"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    code: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(220))
    strategic_line: Mapped[str | None] = mapped_column(String(180))
    priority: Mapped[str | None] = mapped_column(String(80))
    horizon: Mapped[str | None] = mapped_column(String(80))
    responsible_area: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    source_release_code: Mapped[str] = mapped_column(String(160), index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_enterprise_strategic_objective_code"),)


class EnterpriseCoreRelease(Base):
    __tablename__ = "enterprise_core_releases"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    release_code: Mapped[str] = mapped_column(String(160), index=True)
    release_name: Mapped[str] = mapped_column(String(220))
    revision_number: Mapped[int] = mapped_column(default=1)
    state: Mapped[str] = mapped_column(String(40), default="published", index=True)
    source_hash: Mapped[str] = mapped_column(String(64))
    canonical_hash: Mapped[str] = mapped_column(String(64))
    content_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    source_release_code: Mapped[str | None] = mapped_column(String(160))
    previous_release_id: Mapped[int | None] = mapped_column(ForeignKey("enterprise_core_releases.id"))
    base_content_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    workspace_count: Mapped[int]
    objective_count: Mapped[int]
    classification_count: Mapped[int]
    link_count: Mapped[int]
    validation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime)
    validated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    validated_draft_hash: Mapped[str | None] = mapped_column(String(64))
    diff_hash: Mapped[str] = mapped_column(String(64), default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_draft_hash: Mapped[str | None] = mapped_column(String(64))
    approved_diff_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    published_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    unpublished_at: Mapped[datetime | None] = mapped_column(DateTime)
    unpublished_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    rollback_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("tenant_id", "release_code", name="uq_enterprise_core_release_code"),)


_IMMUTABLE_RELEASE_FIELDS = {
    "tenant_id",
    "release_code",
    "release_name",
    "revision_number",
    "source_hash",
    "canonical_hash",
    "content_fingerprint",
    "source_release_code",
    "previous_release_id",
    "base_content_fingerprint",
    "snapshot_json",
    "workspace_count",
    "objective_count",
    "classification_count",
    "link_count",
    "created_at",
    "created_by_user_id",
    "published_at",
    "published_by_user_id",
}


@event.listens_for(EnterpriseCoreRelease, "before_update")
def _protect_release_update(_mapper, _connection, target: EnterpriseCoreRelease) -> None:
    state = inspect(target)
    state_history = state.attrs.state.history
    original_state = state_history.deleted[0] if state_history.deleted else target.state
    if original_state == "draft":
        return
    changed = sorted(name for name in _IMMUTABLE_RELEASE_FIELDS if state.attrs[name].history.has_changes())
    if changed:
        raise ValueError(f"Published CORE release is immutable: {', '.join(changed)}")


@event.listens_for(EnterpriseCoreRelease, "before_delete")
def _protect_release_delete(_mapper, _connection, _target: EnterpriseCoreRelease) -> None:
    raise ValueError("Published CORE releases cannot be physically deleted")


class EnterpriseWorkspaceClassification(Base):
    __tablename__ = "enterprise_workspace_classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    category_set_code: Mapped[str] = mapped_column(String(120), index=True)
    category_item_code: Mapped[str] = mapped_column(String(120), index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "workspace_id", "category_set_code", "category_item_code"),)


class EnterpriseWorkspaceLink(Base):
    __tablename__ = "enterprise_workspace_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    source_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    target_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(60), index=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (UniqueConstraint("tenant_id", "source_workspace_id", "target_workspace_id", "relationship_type"),)
