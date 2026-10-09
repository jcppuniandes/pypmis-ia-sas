"""API contracts for Gate 07F Portfolio Analysis."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class AnalysisFiltersIn(BaseModel):
    project_type: str | None = Field(default=None, max_length=120)
    strategic_objective: str | None = Field(default=None, max_length=120)
    risk_bucket: str | None = Field(default=None, max_length=80)
    priority_bucket: str | None = Field(default=None, max_length=80)
    membership_source: str | None = Field(default=None, max_length=80)
    planning_stage: str | None = Field(default=None, max_length=80)
    evaluation_score_min: Decimal | None = Field(default=None, ge=0, le=100)
    evaluation_score_max: Decimal | None = Field(default=None, ge=0, le=100)
    rom_cost_min: Decimal | None = Field(default=None, ge=0)
    rom_cost_max: Decimal | None = Field(default=None, ge=0)
    target_start_from: date | None = None
    target_finish_to: date | None = None


class MetricDefinitionOut(BaseModel):
    metric_key: str
    label: str
    category: str
    data_type: str
    allowed_for_x_axis: bool
    allowed_for_y_axis: bool
    allowed_for_size: bool
    allowed_for_color: bool
    allowed_for_filter: bool
    allowed_for_scorecard: bool
    aggregation_support: list[str]
    formatting: str
    null_behavior: str
    non_negative: bool = False
    currency_sensitive: bool = False


class PortfolioAnalysisRowOut(BaseModel):
    portfolio_workspace_id: int
    project_workspace_id: int
    portfolio_membership_id: int
    project_number: str
    project_name: str
    project_type: str | None
    governance_model: str
    workspace_status: str
    planning_stage: str | None
    strategic_objectives: list[dict]
    proposal_score: Decimal | None
    portfolio_evaluation_score: Decimal
    portfolio_rank: int
    strategic_alignment_score: Decimal
    risk_score: Decimal
    risk_bucket: str
    priority_bucket: str
    rom_cost: Decimal | None
    currency: str | None
    target_start: date | None
    target_finish: date | None
    planned_duration_days: int | None
    expected_benefits: str | None
    risk_summary: list[dict]
    sponsor: str | None
    project_manager: str | None
    membership_source: str
    evaluation_id: int
    evaluation_version: int
    evaluation_date: datetime
    planning_entry_hash: str
    evaluation_hash: str
    prioritization_hash: str


class PortfolioAnalysisDatasetOut(BaseModel):
    portfolio_workspace_id: int
    generated_at: datetime
    metric_catalog: list[MetricDefinitionOut]
    rows: list[PortfolioAnalysisRowOut]
    filters_applied: dict
    source_prioritization_hash: str
    membership_set_hash: str
    evaluation_set_hash: str
    configuration_hash: str
    analysis_hash: str
    warnings: list[str]
    blockers: list[str]


class InvestorMapPointOut(BaseModel):
    project_workspace_id: int
    project_number: str
    project_name: str
    portfolio_rank: int
    x: Any | None
    y: Any | None
    bubble_size: Decimal
    bubble_size_source: Any | None
    color: str
    tooltip: dict


class InvestorMapOut(BaseModel):
    portfolio_workspace_id: int
    x_metric: str
    y_metric: str
    size_metric: str | None
    color_metric: str
    size_metric_applied: bool
    reference_lines: list[dict]
    points: list[InvestorMapPointOut]
    analysis_hash: str
    warnings: list[str]


class PortfolioScorecardOut(BaseModel):
    portfolio_workspace_id: int
    columns: list[str]
    default_sort: list[dict]
    rows: list[dict]
    analysis_hash: str
    warnings: list[str]


class PortfolioAnalysisSummaryOut(BaseModel):
    eligible_projects: int
    evaluated_projects: int
    average_portfolio_score: Decimal | None
    high_priority_count: int
    high_risk_count: int
    rom_cost_coverage_percent: Decimal
    rom_cost_total: Decimal | None
    rom_cost_currency: str | None
    distributions: dict[str, list[dict]]


class PortfolioAnalysisReadinessOut(BaseModel):
    portfolio_workspace_id: int
    status: str
    analysis_hash: str
    source_prioritization_hash: str
    membership_set_hash: str
    evaluation_set_hash: str
    configuration_hash: str
    eligible_project_count: int
    metric_coverage: dict[str, Decimal]
    warnings: list[str]
    blockers: list[str]
    allowed_actions: list[str]
    can_enter_budget_planning: bool
    can_enter_resource_planning: bool
    can_enter_portfolio_scenario_planning: bool
    final_output: str


class PortfolioAnalysisOverviewOut(BaseModel):
    dataset: PortfolioAnalysisDatasetOut
    investor_map: InvestorMapOut
    scorecard: PortfolioScorecardOut
    summary: PortfolioAnalysisSummaryOut
    readiness: PortfolioAnalysisReadinessOut


class AnalysisPreviewIn(BaseModel):
    filters: AnalysisFiltersIn = Field(default_factory=AnalysisFiltersIn)
    expected_analysis_hash: str | None = Field(default=None, min_length=64, max_length=64)


class AnalysisPreviewOut(BaseModel):
    persisted: bool = False
    overview: PortfolioAnalysisOverviewOut


class ProjectAnalysisDetailOut(BaseModel):
    row: PortfolioAnalysisRowOut
    evaluation_history: list[dict]
    strategic_context: dict
    membership: dict
    planning_entry: dict


class ConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=3000)
    content_json: dict


class ConfigurationPreviewIn(BaseModel):
    portfolio_workspace_id: int | None = Field(default=None, gt=0)
    configuration_id: int | None = Field(default=None, gt=0)
    content_json: dict | None = None


class ConfigurationPreviewOut(BaseModel):
    portfolio_workspace_id: int | None
    path: list[dict]
    effective: dict
    source: dict
    publishable: bool
    validation_issues: list[str]
    dataset_preview: PortfolioAnalysisDatasetOut | None
    warnings: list[str]
    blockers: list[str]
    persisted: bool = False
