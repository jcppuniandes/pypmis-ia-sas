"""Persistence for governed, reproducible Project economic-financial models."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.database.session import Base


class EconomicFinancialModel(Base):
    __tablename__ = "economic_financial_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    model_number: Mapped[str] = mapped_column(String(40), index=True)
    project_workspace_id: Mapped[int] = mapped_column(ForeignKey("enterprise_workspaces.id"), index=True)
    business_case_id: Mapped[int] = mapped_column(ForeignKey("business_cases.id"), index=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    sponsor_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    current_version_id: Mapped[int | None] = mapped_column(Integer, index=True)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("admin_configurations.id"), index=True)
    configuration_revision: Mapped[int] = mapped_column(Integer)
    configuration_hash: Mapped[str] = mapped_column(String(64), index=True)
    configuration_source_workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("enterprise_workspaces.id"), index=True
    )
    configuration_resolution_chain_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    create_idempotency_key: Mapped[str] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "model_number", name="uq_economic_financial_model_number"),
        UniqueConstraint("tenant_id", "project_workspace_id", name="uq_economic_financial_model_project"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_economic_financial_model_create_key"),
        CheckConstraint(
            "status IN ('DRAFT','ACTIVE','ON_HOLD','CLOSED','ARCHIVED')",
            name="ck_economic_financial_model_status",
        ),
        Index("ix_economic_financial_model_queue", "tenant_id", "status", "updated_at"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class EconomicFinancialModelVersion(Base):
    __tablename__ = "economic_financial_model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("economic_financial_models.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    version_label: Mapped[str] = mapped_column(String(24))
    purpose: Mapped[str] = mapped_column(String(48), index=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    model_type: Mapped[str] = mapped_column(String(40), index=True)
    base_currency: Mapped[str] = mapped_column(String(8), index=True)
    cash_flow_basis: Mapped[str] = mapped_column(String(12), default="NOMINAL")
    periodicity: Mapped[str] = mapped_column(String(12), default="MONTHLY")
    model_start_date: Mapped[date] = mapped_column(Date)
    model_end_date: Mapped[date] = mapped_column(Date)
    construction_start: Mapped[date] = mapped_column(Date)
    operations_start: Mapped[date | None] = mapped_column(Date)
    operations_end: Mapped[date | None] = mapped_column(Date)
    terminal_date: Mapped[date | None] = mapped_column(Date)
    as_of_date: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    business_case_revision_id: Mapped[int] = mapped_column(ForeignKey("business_case_revisions.id"), index=True)
    business_case_hash: Mapped[str] = mapped_column(String(64), index=True)
    budget_scenario_id: Mapped[int | None] = mapped_column(ForeignKey("portfolio_budget_scenarios.id"), index=True)
    budget_scenario_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    funding_readiness_id: Mapped[int | None] = mapped_column(ForeignKey("funding_readiness_snapshots.id"), index=True)
    funding_readiness_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    source_references_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_hashes_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    total_investment_requirement: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    total_model_financing: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    governed_funding_assigned: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    funding_gap: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=0)
    funding_reconciliation_status: Mapped[str] = mapped_column(String(32), default="NOT_STARTED")
    project_financial_npv: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    project_irr: Mapped[Decimal | None] = mapped_column(Numeric(16, 10))
    economic_npv: Mapped[Decimal | None] = mapped_column(Numeric(24, 6))
    economic_irr: Mapped[Decimal | None] = mapped_column(Numeric(16, 10))
    benefit_cost_ratio: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    simple_payback: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    discounted_payback: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    equity_irr: Mapped[Decimal | None] = mapped_column(Numeric(16, 10))
    moic: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    minimum_dscr: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    average_dscr: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    llcr: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    debt_to_equity: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    economic_readiness: Mapped[str] = mapped_column(String(24), default="NOT_STARTED")
    financial_model_readiness: Mapped[str] = mapped_column(String(24), default="NOT_STARTED")
    funding_reconciliation_readiness: Mapped[str] = mapped_column(String(24), default="NOT_STARTED")
    debt_readiness: Mapped[str] = mapped_column(String(24), default="NOT_APPLICABLE")
    equity_readiness: Mapped[str] = mapped_column(String(24), default="NOT_APPLICABLE")
    covenant_readiness: Mapped[str] = mapped_column(String(24), default="NOT_APPLICABLE")
    scenario_readiness: Mapped[str] = mapped_column(String(24), default="NOT_STARTED")
    overall_readiness: Mapped[str] = mapped_column(String(24), default="NOT_STARTED", index=True)
    warnings_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    blockers_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_current: Mapped[bool] = mapped_column(Boolean, default=True)
    readiness_hash: Mapped[str] = mapped_column(String(64), index=True)
    model_hash: Mapped[str] = mapped_column(String(64), index=True)
    calculation_engine_version: Mapped[str] = mapped_column(String(40), default="PPMIS-FIN-1.0")
    calculation_trace_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    preparer_user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    reviewer_user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    create_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    calculate_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    complete_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    refresh_idempotency_key: Mapped[str | None] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    revision_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "model_id", "version_number", name="uq_economic_financial_model_version"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_fin_model_version_create_key"),
        UniqueConstraint("tenant_id", "calculate_idempotency_key", name="uq_fin_model_version_calculate_key"),
        UniqueConstraint("tenant_id", "complete_idempotency_key", name="uq_fin_model_version_complete_key"),
        UniqueConstraint("tenant_id", "refresh_idempotency_key", name="uq_fin_model_version_refresh_key"),
        CheckConstraint("version_number > 0", name="ck_fin_model_version_number"),
        CheckConstraint(
            "status IN ('DRAFT','IN_REVIEW','COMPLETED','SUPERSEDED','VOIDED')",
            name="ck_fin_model_version_status",
        ),
        CheckConstraint(
            "model_type IN ('COMMERCIAL_PROJECT','NON_REVENUE_PROJECT','PUBLIC_ECONOMIC_APPRAISAL','MIXED')",
            name="ck_fin_model_version_type",
        ),
        CheckConstraint("cash_flow_basis IN ('NOMINAL','REAL')", name="ck_fin_model_version_basis"),
        CheckConstraint("periodicity IN ('MONTHLY','QUARTERLY','ANNUAL')", name="ck_fin_model_periodicity"),
        CheckConstraint("model_end_date >= model_start_date", name="ck_fin_model_horizon"),
        CheckConstraint(
            "overall_readiness IN ('NOT_STARTED','READY','BLOCKED','STALE','EXPIRED','NOT_APPLICABLE')",
            name="ck_fin_model_readiness",
        ),
        Index("ix_fin_model_version_latest", "tenant_id", "model_id", "version_number"),
    )
    __mapper_args__ = {"version_id_col": revision_version, "version_id_generator": False}


class FinancialModelAssumption(Base):
    __tablename__ = "financial_model_assumptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("economic_financial_model_versions.id"), index=True)
    assumption_key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(180))
    category: Mapped[str] = mapped_column(String(40), index=True)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    text_value: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(40), default="")
    periodicity: Mapped[str | None] = mapped_column(String(12))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(80), default="MANUAL")
    source_reference: Mapped[str | None] = mapped_column(String(300))
    rationale: Mapped[str] = mapped_column(Text, default="")
    is_override: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "model_version_id", "assumption_key", name="uq_fin_model_assumption_key"),
        CheckConstraint(
            "category IN ('GENERAL','MACROECONOMIC','REVENUE','OPEX','CAPEX','TAX','WORKING_CAPITAL',"
            "'DISCOUNT_RATE','INFLATION','FX','DEBT','EQUITY','TERMINAL_VALUE','ECONOMIC_BENEFIT','OTHER')",
            name="ck_fin_model_assumption_category",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from",
            name="ck_fin_model_assumption_dates",
        ),
    )


class FinancialModelPeriod(Base):
    __tablename__ = "financial_model_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("economic_financial_model_versions.id"), index=True)
    period_index: Mapped[int] = mapped_column(Integer)
    period_label: Mapped[str] = mapped_column(String(40))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(8))
    revenue: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    economic_benefits: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    opex: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    taxes: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    working_capital_change: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    capex: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    debt_drawdown: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    interest: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    principal: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    equity_contribution: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    distribution: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    source_reference: Mapped[str | None] = mapped_column(String(300))
    source_hash: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("tenant_id", "model_version_id", "period_index", name="uq_fin_model_period_index"),
        UniqueConstraint("tenant_id", "model_version_id", "period_label", name="uq_fin_model_period_label"),
        CheckConstraint("period_index >= 0", name="ck_fin_model_period_index"),
        CheckConstraint("period_end >= period_start", name="ck_fin_model_period_dates"),
        CheckConstraint(
            "revenue >= 0 AND economic_benefits >= 0 AND opex >= 0 AND taxes >= 0 AND capex >= 0 "
            "AND debt_drawdown >= 0 AND interest >= 0 AND principal >= 0 AND equity_contribution >= 0 "
            "AND distribution >= 0",
            name="ck_fin_model_period_non_negative",
        ),
    )


class FinancialModelFinancingInstrument(Base):
    __tablename__ = "financial_model_financing_instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("economic_financial_model_versions.id"), index=True)
    instrument_key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(180))
    instrument_type: Mapped[str] = mapped_column(String(48), index=True)
    currency: Mapped[str] = mapped_column(String(8), index=True)
    committed_amount: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    drawn_amount: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    funding_source_id: Mapped[int | None] = mapped_column(ForeignKey("strategic_funding_sources.id"), index=True)
    fund_id: Mapped[int | None] = mapped_column(ForeignKey("funds.id"), index=True)
    funding_assignment_id: Mapped[int | None] = mapped_column(ForeignKey("funding_assignments.id"), index=True)
    funding_assignment_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    funding_readiness_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    interest_basis: Mapped[str | None] = mapped_column(String(48))
    fixed_rate: Mapped[Decimal | None] = mapped_column(Numeric(16, 10))
    reference_rate_key: Mapped[str | None] = mapped_column(String(100))
    spread_rate: Mapped[Decimal | None] = mapped_column(Numeric(16, 10))
    commitment_fee: Mapped[Decimal | None] = mapped_column(Numeric(16, 10))
    upfront_fee: Mapped[Decimal | None] = mapped_column(Numeric(16, 10))
    other_fee: Mapped[Decimal | None] = mapped_column(Numeric(16, 10))
    principal_grace_periods: Mapped[int] = mapped_column(Integer, default=0)
    interest_grace_periods: Mapped[int] = mapped_column(Integer, default=0)
    tenor_periods: Mapped[int | None] = mapped_column(Integer)
    maturity_date: Mapped[date | None] = mapped_column(Date)
    drawdown_method: Mapped[str] = mapped_column(String(48), default="CUSTOM")
    amortization_method: Mapped[str] = mapped_column(String(48), default="CUSTOM")
    interest_during_construction: Mapped[str] = mapped_column(String(24), default="CASH_PAY")
    minimum_dscr: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    minimum_llcr: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    covenants_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    readiness_status: Mapped[str] = mapped_column(String(24), default="NOT_STARTED")
    create_idempotency_key: Mapped[str] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "model_version_id", "instrument_key", name="uq_fin_model_instrument_key"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_fin_model_instrument_create_key"),
        CheckConstraint("committed_amount >= 0", name="ck_fin_model_instrument_commitment"),
        CheckConstraint("drawn_amount >= 0 AND drawn_amount <= committed_amount", name="ck_fin_model_instrument_drawn"),
    )


class FinancialModelInvestor(Base):
    __tablename__ = "financial_model_investors"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("economic_financial_model_versions.id"), index=True)
    financing_instrument_id: Mapped[int] = mapped_column(
        ForeignKey("financial_model_financing_instruments.id"), index=True
    )
    investor_key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(180))
    investor_type: Mapped[str] = mapped_column(String(40), index=True)
    committed_equity: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    ownership_percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    preferred_return: Mapped[Decimal | None] = mapped_column(Numeric(16, 10))
    distribution_priority: Mapped[int | None] = mapped_column(Integer)
    capital_call_profile_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    distribution_profile_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    hurdle_rate: Mapped[Decimal | None] = mapped_column(Numeric(16, 10))
    total_contributions: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    total_distributions: Mapped[Decimal] = mapped_column(Numeric(24, 6), default=0)
    equity_irr: Mapped[Decimal | None] = mapped_column(Numeric(16, 10))
    moic: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE")
    create_idempotency_key: Mapped[str] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "model_version_id", "investor_key", name="uq_fin_model_investor_key"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_fin_model_investor_create_key"),
        CheckConstraint("committed_equity >= 0", name="ck_fin_model_investor_commitment"),
        CheckConstraint(
            "ownership_percent IS NULL OR (ownership_percent >= 0 AND ownership_percent <= 100)",
            name="ck_fin_model_investor_ownership",
        ),
    )


class FinancialModelScenario(Base):
    __tablename__ = "financial_model_scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("economic_financial_model_versions.id"), index=True)
    scenario_key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(180))
    scenario_type: Mapped[str] = mapped_column(String(16), index=True)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    output_summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    scenario_hash: Mapped[str] = mapped_column(String(64), index=True)
    create_idempotency_key: Mapped[str] = mapped_column(String(160))
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "model_version_id", "scenario_key", name="uq_fin_model_scenario_key"),
        UniqueConstraint("tenant_id", "model_version_id", "name", name="uq_fin_model_scenario_name"),
        UniqueConstraint("tenant_id", "create_idempotency_key", name="uq_fin_model_scenario_create_key"),
        CheckConstraint("scenario_type IN ('BASE','UPSIDE','DOWNSIDE','CUSTOM')", name="ck_fin_model_scenario_type"),
        Index(
            "uq_fin_model_official_base",
            "tenant_id",
            "model_version_id",
            unique=True,
            postgresql_where=text("scenario_type = 'BASE' AND is_official"),
            sqlite_where=text("scenario_type = 'BASE' AND is_official"),
        ),
    )


class FinancialModelScenarioOverride(Base):
    __tablename__ = "financial_model_scenario_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("financial_model_scenarios.id"), index=True)
    target_key: Mapped[str] = mapped_column(String(100))
    period_label: Mapped[str | None] = mapped_column(String(40))
    operation: Mapped[str] = mapped_column(String(16), default="MULTIPLY")
    numeric_value: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    rationale: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (
        UniqueConstraint("tenant_id", "scenario_id", "target_key", "period_label", name="uq_fin_model_override"),
        CheckConstraint("operation IN ('SET','ADD','MULTIPLY')", name="ck_fin_model_override_operation"),
    )


class FinancialModelCashFlow(Base):
    __tablename__ = "financial_model_cash_flows"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("economic_financial_model_versions.id"), index=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("financial_model_scenarios.id"), index=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("financial_model_periods.id"), index=True)
    period_index: Mapped[int] = mapped_column(Integer)
    revenue: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    economic_benefits: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    opex: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    taxes: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    working_capital_change: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    capex: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    unlevered_project_cf: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    cfads: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    debt_drawdown: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    interest: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    principal: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    equity_contribution: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    distribution: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    cash_flow_to_equity: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    row_hash: Mapped[str] = mapped_column(String(64), index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "scenario_id", "period_id", name="uq_fin_model_cash_flow_period"),
        Index("ix_fin_model_cash_flow_history", "tenant_id", "model_version_id", "scenario_id", "period_index"),
    )


class FinancialModelDebtSchedule(Base):
    __tablename__ = "financial_model_debt_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("economic_financial_model_versions.id"), index=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("financial_model_scenarios.id"), index=True)
    financing_instrument_id: Mapped[int] = mapped_column(
        ForeignKey("financial_model_financing_instruments.id"), index=True
    )
    period_id: Mapped[int] = mapped_column(ForeignKey("financial_model_periods.id"), index=True)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    drawdown: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    interest: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    fees: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    principal: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    closing_balance: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    debt_service: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    dscr: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    llcr: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))
    covenant_status: Mapped[str] = mapped_column(String(24), default="NOT_APPLICABLE")
    row_hash: Mapped[str] = mapped_column(String(64), index=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "scenario_id", "financing_instrument_id", "period_id", name="uq_fin_model_debt_period"
        ),
    )


class FinancialModelMetricResult(Base):
    __tablename__ = "financial_model_metric_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("economic_financial_model_versions.id"), index=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("financial_model_scenarios.id"), index=True)
    metric_key: Mapped[str] = mapped_column(String(100), index=True)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    status_value: Mapped[str | None] = mapped_column(String(40))
    unit: Mapped[str] = mapped_column(String(40), default="")
    formula_version: Mapped[str] = mapped_column(String(40))
    input_references_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    trace_hash: Mapped[str] = mapped_column(String(64), index=True)

    __table_args__ = (UniqueConstraint("tenant_id", "scenario_id", "metric_key", name="uq_fin_model_metric"),)


class FinancialModelSensitivityResult(Base):
    __tablename__ = "financial_model_sensitivity_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("economic_financial_model_versions.id"), index=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("financial_model_scenarios.id"), index=True)
    variable_key: Mapped[str] = mapped_column(String(100), index=True)
    shock_value: Mapped[Decimal] = mapped_column(Numeric(16, 8))
    target_metric: Mapped[str] = mapped_column(String(100))
    result_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    break_even_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 10))
    result_status: Mapped[str] = mapped_column(String(40), default="CALCULATED")
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


def _protect_terminal_version(_mapper, _connection, target: EconomicFinancialModelVersion) -> None:
    state = inspect(target)
    previous = state.attrs.status.history.deleted
    original_status = previous[0] if previous else target.status
    if original_status in {"COMPLETED", "SUPERSEDED", "VOIDED"}:
        raise ValueError("Terminal Economic & Financial Model versions are immutable")


def _immutable_output(_mapper, _connection, _target) -> None:
    raise ValueError("Completed financial calculation evidence is immutable")


event.listen(EconomicFinancialModelVersion, "before_update", _protect_terminal_version)
for _model in (
    FinancialModelCashFlow,
    FinancialModelDebtSchedule,
    FinancialModelMetricResult,
    FinancialModelSensitivityResult,
):
    event.listen(_model, "before_update", _immutable_output)
    event.listen(_model, "before_delete", _immutable_output)
