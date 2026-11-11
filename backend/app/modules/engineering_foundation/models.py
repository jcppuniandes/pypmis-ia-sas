"""Canonical engineering records; files and cross-domain targets stay external."""

from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base
from app.modules.scope_foundation.models import ScopeRecord


class EngineeringDesignPackage(ScopeRecord, Base):
    __tablename__ = "engineering_design_packages"
    code: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "code", name="uq_eng_design_package_code"),
        CheckConstraint("status IN ('DRAFT','REVIEWED','ISSUED','CANCELLED')", name="ck_eng_design_package_status"),
    )


class EngineeringDeliverable(ScopeRecord, Base):
    __tablename__ = "engineering_deliverables"
    code: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(300))
    discipline: Mapped[str] = mapped_column(String(80))
    deliverable_type: Mapped[str] = mapped_column(String(80))
    design_package_id: Mapped[int | None] = mapped_column(ForeignKey("engineering_design_packages.id"), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    responsible_party: Mapped[str] = mapped_column(String(200))
    area: Mapped[str] = mapped_column(String(150), default="")
    planned_issue_date: Mapped[date | None] = mapped_column(Date)
    current_forecast_date: Mapped[date | None] = mapped_column(Date)
    source_reference: Mapped[str] = mapped_column(String(1000), default="")
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "code", name="uq_eng_deliverable_code"),
        Index("ix_eng_deliverable_register", "tenant_id", "project_workspace_id", "discipline", "id"),
    )


class EngineeringRevision(ScopeRecord, Base):
    __tablename__ = "engineering_revisions"
    deliverable_id: Mapped[int] = mapped_column(ForeignKey("engineering_deliverables.id"), index=True)
    revision_code: Mapped[str] = mapped_column(String(80))
    revision_sequence: Mapped[int] = mapped_column()
    supersedes_revision_id: Mapped[int | None] = mapped_column(ForeignKey("engineering_revisions.id"))
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    purpose_of_issue: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    planned_issue_date: Mapped[date | None] = mapped_column(Date)
    forecast_issue_date: Mapped[date | None] = mapped_column(Date)
    document_ref_json: Mapped[dict] = mapped_column(JSON, default=dict)
    document_hash: Mapped[str] = mapped_column(String(64), default="")
    content_hash: Mapped[str] = mapped_column(String(64))
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"))
    configuration_hash: Mapped[str] = mapped_column(String(64))
    prepared_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    checked_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("deliverable_id", "revision_code", name="uq_eng_revision_code"),
        UniqueConstraint("deliverable_id", "revision_sequence", name="uq_eng_revision_sequence"),
        UniqueConstraint("supersedes_revision_id", name="uq_eng_revision_successor"),
        CheckConstraint("revision_sequence > 0", name="ck_eng_revision_sequence"),
        CheckConstraint(
            "status IN ('DRAFT','UNDER_REVIEW','CHANGES_REQUESTED','APPROVED','REJECTED')",
            name="ck_eng_revision_status",
        ),
    )


class EngineeringReview(ScopeRecord, Base):
    __tablename__ = "engineering_reviews"
    revision_id: Mapped[int] = mapped_column(ForeignKey("engineering_revisions.id"), index=True)
    round_number: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(24), default="SUBMITTED")
    decision: Mapped[str | None] = mapped_column(String(24))
    submitted_hash: Mapped[str] = mapped_column(String(64))
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    decision_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    decision_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        UniqueConstraint("revision_id", "round_number", name="uq_eng_review_round"),
        CheckConstraint("round_number > 0", name="ck_eng_review_round"),
        CheckConstraint(
            "status IN ('SUBMITTED','UNDER_REVIEW','COMMENTS_ISSUED','REVISE_AND_RESUBMIT','ACCEPTED','APPROVED','REJECTED','CLOSED')",
            name="ck_eng_review_status",
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('REVISE_AND_RESUBMIT','APPROVED','REJECTED')",
            name="ck_eng_review_decision",
        ),
    )


class EngineeringReviewComment(ScopeRecord, Base):
    __tablename__ = "engineering_review_comments"
    review_id: Mapped[int] = mapped_column(ForeignKey("engineering_reviews.id"), index=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("engineering_revisions.id"), index=True)
    discipline: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    response: Mapped[str | None] = mapped_column(Text)
    response_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    response_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','RESPONDED','CLOSED')", name="ck_eng_comment_status"),
        CheckConstraint("severity IN ('INFO','MINOR','MAJOR','BLOCKING')", name="ck_eng_comment_severity"),
    )


class EngineeringRelease(ScopeRecord, Base):
    __tablename__ = "engineering_releases"
    revision_id: Mapped[int] = mapped_column(ForeignKey("engineering_revisions.id"))
    deliverable_id: Mapped[int] = mapped_column(ForeignKey("engineering_deliverables.id"), index=True)
    effective_date: Mapped[date] = mapped_column(Date)
    released_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    released_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    release_reference: Mapped[str] = mapped_column(String(1000))
    release_hash: Mapped[str] = mapped_column(String(64))
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("revision_id", name="uq_eng_release_revision"),
        Index("ix_eng_release_cutoff", "tenant_id", "project_workspace_id", "deliverable_id", "effective_date"),
    )


class EngineeringInterface(ScopeRecord, Base):
    __tablename__ = "engineering_interfaces"
    code: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(300))
    interface_type: Mapped[str] = mapped_column(String(32))
    deliverable_id: Mapped[int | None] = mapped_column(ForeignKey("engineering_deliverables.id"))
    source_reference: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    resolution: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    __table_args__ = (
        UniqueConstraint("tenant_id", "project_workspace_id", "code", name="uq_eng_interface_code"),
        CheckConstraint("status IN ('OPEN','RESOLVED','CLOSED','CANCELLED')", name="ck_eng_interface_status"),
        CheckConstraint(
            "interface_type IN ('DISCIPLINE','PROCUREMENT','CONSTRUCTION','VENDOR','OWNER')",
            name="ck_eng_interface_type",
        ),
    )


class EngineeringHistory(ScopeRecord, Base):
    __tablename__ = "engineering_history"
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int] = mapped_column()
    entity_version: Mapped[int] = mapped_column()
    event_type: Mapped[str] = mapped_column(String(100))
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (Index("ix_eng_history_cursor", "tenant_id", "project_workspace_id", "id"),)
