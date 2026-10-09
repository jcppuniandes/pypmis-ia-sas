"""Tenant-scoped persistence for Gate 07I scenario convergence."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class PortfolioScenarioConvergence(Base):
    __tablename__ = "portfolio_scenario_convergences"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    portfolio_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    logical_code: Mapped[str] = mapped_column(String(100), default="PORTFOLIO-CONVERGENCE")
    convergence_revision: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="DRAFT", index=True)
    required_budget_branch: Mapped[bool] = mapped_column(Boolean, default=True)
    required_resource_branch: Mapped[bool] = mapped_column(Boolean, default=True)
    source_analysis_hash: Mapped[str] = mapped_column(String(64))
    source_membership_set_hash: Mapped[str] = mapped_column(String(64))
    source_evaluation_set_hash: Mapped[str] = mapped_column(String(64))
    budget_planning_hash: Mapped[str | None] = mapped_column(String(64))
    resource_planning_hash: Mapped[str | None] = mapped_column(String(64))
    configuration_id: Mapped[int | None] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    configuration_revision: Mapped[int] = mapped_column(Integer, default=1)
    configuration_hash: Mapped[str] = mapped_column(String(64))
    convergence_source_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    recommended_alternative_id: Mapped[int | None] = mapped_column(Integer, index=True)
    recommendation_reason: Mapped[str | None] = mapped_column(Text)
    conditions_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    risks_acknowledged_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    decision_support_summary: Mapped[str | None] = mapped_column(Text)
    recommendation_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    recommended_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    recommended_at: Mapped[datetime | None] = mapped_column(DateTime)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    blockers_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    refresh_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    submit_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    return_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    recommend_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    clone_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    void_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "portfolio_workspace_id",
            "logical_code",
            "convergence_revision",
            name="uq_portfolio_convergence_revision",
        ),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_convergence_create_key"),
        UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_convergence_refresh_key"),
        UniqueConstraint("tenant_id", "submit_idempotency_key", name="uq_convergence_submit_key"),
        UniqueConstraint("tenant_id", "return_idempotency_key", name="uq_convergence_return_key"),
        UniqueConstraint("tenant_id", "recommend_idempotency_key", name="uq_convergence_recommend_key"),
        UniqueConstraint("tenant_id", "clone_idempotency_key", name="uq_convergence_clone_key"),
        UniqueConstraint("tenant_id", "void_idempotency_key", name="uq_convergence_void_key"),
        CheckConstraint(
            "status IN ('DRAFT','IN_REVIEW','RECOMMENDED','SUPERSEDED','VOIDED')",
            name="ck_portfolio_convergence_status",
        ),
        CheckConstraint(
            "required_budget_branch OR required_resource_branch",
            name="ck_portfolio_convergence_branch_required",
        ),
        CheckConstraint(
            "status != 'RECOMMENDED' OR (recommended_alternative_id IS NOT NULL AND recommendation_hash IS NOT NULL)",
            name="ck_portfolio_convergence_recommended_evidence",
        ),
        Index("ix_convergence_tenant_portfolio", "tenant_id", "portfolio_workspace_id"),
        Index("ix_convergence_tenant_status", "tenant_id", "status"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class PortfolioConvergedAlternative(Base):
    __tablename__ = "portfolio_converged_alternatives"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    convergence_id: Mapped[int] = mapped_column(ForeignKey("portfolio_scenario_convergences.id"), index=True)
    alternative_name: Mapped[str] = mapped_column(String(180))
    budget_scenario_id: Mapped[int | None] = mapped_column(ForeignKey("portfolio_budget_scenarios.id"), index=True)
    budget_scenario_hash: Mapped[str | None] = mapped_column(String(64))
    resource_scenario_id: Mapped[int | None] = mapped_column(ForeignKey("portfolio_resource_scenarios.id"), index=True)
    resource_scenario_hash: Mapped[str | None] = mapped_column(String(64))
    alignment_status: Mapped[str] = mapped_column(String(24), default="ALIGNED", index=True)
    budget_feasibility: Mapped[str] = mapped_column(String(24), default="NOT_REQUIRED")
    resource_feasibility: Mapped[str] = mapped_column(String(24), default="NOT_REQUIRED")
    feasibility_status: Mapped[str] = mapped_column(String(24), default="BLOCKED", index=True)
    selected_project_set_hash: Mapped[str] = mapped_column(String(64))
    budget_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    resource_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    strategic_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    project_matrix_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    forced_conflicts_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    blockers_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    alternative_hash: Mapped[str] = mapped_column(String(64), index=True)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "convergence_id",
            "budget_scenario_id",
            "resource_scenario_id",
            name="uq_converged_alternative_pair",
        ),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_converged_alternative_create_key"),
        CheckConstraint(
            "alignment_status IN ('ALIGNED','PARTIALLY_ALIGNED','MISALIGNED')",
            name="ck_converged_alternative_alignment",
        ),
        CheckConstraint(
            "budget_feasibility IN ('BUDGET_FEASIBLE','CONDITIONAL','INFEASIBLE','NOT_REQUIRED')",
            name="ck_converged_alternative_budget_feasibility",
        ),
        CheckConstraint(
            "resource_feasibility IN ('RESOURCE_FEASIBLE','CONDITIONAL','INFEASIBLE','NOT_REQUIRED')",
            name="ck_converged_alternative_resource_feasibility",
        ),
        CheckConstraint(
            "feasibility_status IN ('FEASIBLE','CONDITIONAL','INFEASIBLE','BLOCKED','STALE')",
            name="ck_converged_alternative_feasibility",
        ),
        Index("ix_converged_alternative_convergence_status", "convergence_id", "feasibility_status"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


@event.listens_for(PortfolioScenarioConvergence, "before_update")
def _protect_recommended_convergence(_mapper, _connection, record: PortfolioScenarioConvergence) -> None:
    state = inspect(record)
    previous = state.attrs.status.history.deleted[0] if state.attrs.status.history.deleted else record.status
    if previous in {"RECOMMENDED", "SUPERSEDED", "VOIDED"} and any(
        attribute.history.has_changes() for attribute in state.attrs
    ):
        raise ValueError("Recommended Portfolio Scenario Convergences are immutable")


@event.listens_for(PortfolioConvergedAlternative, "before_update")
def _protect_recommended_alternative(_mapper, connection, record: PortfolioConvergedAlternative) -> None:
    status = connection.execute(
        PortfolioScenarioConvergence.__table__.select()
        .with_only_columns(PortfolioScenarioConvergence.status)
        .where(PortfolioScenarioConvergence.id == record.convergence_id)
    ).scalar_one_or_none()
    if status in {"RECOMMENDED", "SUPERSEDED", "VOIDED"}:
        raise ValueError("Alternatives of a recommended convergence are immutable")
