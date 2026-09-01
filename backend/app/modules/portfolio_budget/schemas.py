"""API contracts for Gate 07G Portfolio Budget Planning."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TargetPeriodIn(BaseModel):
    period_key: str = Field(min_length=1, max_length=20)
    period_start: date
    period_end: date
    amount: Decimal = Field(ge=0)
    capex_amount: Decimal | None = Field(default=None, ge=0)
    expense_amount: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_range(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        if (self.capex_amount or 0) + (self.expense_amount or 0) > self.amount:
            raise ValueError("period CAPEX + EXPENSE cannot exceed amount")
        return self


class BudgetTargetCreateIn(BaseModel):
    planning_horizon_start: date
    planning_horizon_end: date
    period_granularity: str = Field(default="YEAR", pattern="^(YEAR|QUARTER|MONTH)$")
    budget_currency: str = Field(min_length=3, max_length=8)
    total_budget_target: Decimal = Field(ge=0)
    capex_budget_target: Decimal | None = Field(default=None, ge=0)
    expense_budget_target: Decimal | None = Field(default=None, ge=0)
    periods: list[TargetPeriodIn] = Field(default_factory=list)
    source_reference: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def valid_range(self):
        if self.planning_horizon_end < self.planning_horizon_start:
            raise ValueError("planning_horizon_end must be on or after planning_horizon_start")
        if (self.capex_budget_target or 0) + (self.expense_budget_target or 0) > self.total_budget_target:
            raise ValueError("CAPEX + EXPENSE targets cannot exceed total Budget Target")
        return self


class BudgetTargetUpdateIn(BaseModel):
    planning_horizon_start: date
    planning_horizon_end: date
    period_granularity: str = Field(pattern="^(YEAR|QUARTER|MONTH)$")
    budget_currency: str = Field(min_length=3, max_length=8)
    total_budget_target: Decimal = Field(ge=0)
    capex_budget_target: Decimal | None = Field(default=None, ge=0)
    expense_budget_target: Decimal | None = Field(default=None, ge=0)
    periods: list[TargetPeriodIn] = Field(default_factory=list)
    source_reference: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def valid_range(self):
        if self.planning_horizon_end < self.planning_horizon_start:
            raise ValueError("planning_horizon_end must be on or after planning_horizon_start")
        if (self.capex_budget_target or 0) + (self.expense_budget_target or 0) > self.total_budget_target:
            raise ValueError("CAPEX + EXPENSE targets cannot exceed total Budget Target")
        return self


class IdempotencyIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class TargetPeriodOut(TargetPeriodIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class BudgetTargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    portfolio_workspace_id: int
    target_code: str
    target_revision: int
    planning_horizon_start: date
    planning_horizon_end: date
    period_granularity: str
    budget_currency: str
    total_budget_target: Decimal
    capex_budget_target: Decimal | None
    expense_budget_target: Decimal | None
    unallocated_budget_target: Decimal
    periods: list[TargetPeriodOut]
    source_reference: str
    notes: str
    status: str
    target_hash: str
    revision_version: int
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    published_at: datetime | None


class BudgetScenarioCreateIn(BaseModel):
    scenario_name: str = Field(min_length=3, max_length=180)
    scenario_code: str | None = Field(default=None, max_length=80)
    description: str = Field(default="", max_length=4000)
    budget_target_id: int = Field(gt=0)
    creation_mode: str = Field(pattern="^(EMPTY|FROM_CURRENT_PRIORITY|COPY_EXISTING_SCENARIO)$")
    source_scenario_id: int | None = Field(default=None, gt=0)
    time_phasing_method: str = Field(
        default="UNPHASED", pattern="^(UNPHASED|LINEAR_BY_PROJECT_DATES|CUSTOM_PERIOD_PROFILE)$"
    )
    expected_analysis_hash: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def copy_source_required(self):
        if self.creation_mode == "COPY_EXISTING_SCENARIO" and self.source_scenario_id is None:
            raise ValueError("source_scenario_id is required for COPY_EXISTING_SCENARIO")
        return self


class BudgetScenarioUpdateIn(BaseModel):
    scenario_name: str = Field(min_length=3, max_length=180)
    scenario_code: str | None = Field(default=None, max_length=80)
    description: str = Field(default="", max_length=4000)
    status: str = Field(default="DRAFT", pattern="^(DRAFT|IN_REVIEW)$")
    time_phasing_method: str = Field(pattern="^(UNPHASED|LINEAR_BY_PROJECT_DATES|CUSTOM_PERIOD_PROFILE)$")


class ScenarioSelectionIn(BaseModel):
    selection_state: str = Field(pattern="^(SELECTED|UNSELECTED|FORCED_IN|FORCED_OUT)$")
    forced_reason: str | None = Field(default=None, max_length=4000)
    authority_reference: str | None = Field(default=None, max_length=300)
    period_profile: list[dict] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def forced_reason_required(self):
        if self.selection_state in {"FORCED_IN", "FORCED_OUT"} and not (self.forced_reason or "").strip():
            raise ValueError("forced_reason is required for forced states")
        return self


class ScenarioProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_workspace_id: int
    portfolio_membership_id: int
    project_number: str
    project_name: str
    portfolio_evaluation_score: Decimal
    portfolio_rank: int
    strategic_alignment_score: Decimal
    risk_score: Decimal
    risk_bucket: str
    gate07f_analysis_hash: str
    cost_source_type: str
    cost_source_reference: str
    cost_source_hash: str
    cost_value: Decimal
    capex_amount: Decimal | None
    expense_amount: Decimal | None
    unclassified_amount: Decimal
    budget_breakdown_source: str
    currency: str
    cost_as_of_date: date
    target_start: date | None
    target_finish: date | None
    strategic_objectives: list[dict]
    risk_summary: list[dict]
    expected_benefits: str
    project_type: str
    planning_stage: str
    selection_state: str
    forced_reason: str | None
    forced_actor_id: int | None
    forced_at: datetime | None
    forced_authority_reference: str | None
    period_profile: list[dict]
    warnings: list[str]
    dependency_status: str = "NOT_APPLICABLE"
    unmet_dependency_count: int = 0
    dependency_details: list[dict] = Field(default_factory=list)
    row_hash: str
    revision_version: int


class ScenarioSummaryOut(BaseModel):
    selected_demand: Decimal
    target_budget: Decimal
    variance: Decimal
    utilization_percent: Decimal
    selected_count: int
    unselected_count: int
    forced_in_count: int
    forced_out_count: int
    average_evaluation_score: Decimal | None
    average_strategic_alignment: Decimal | None
    high_risk_count: int
    analytical_status: str
    selected_capex: Decimal
    selected_expense: Decimal
    selected_unclassified: Decimal
    capex_target: Decimal | None
    expense_target: Decimal | None
    unallocated_target: Decimal
    capex_variance: Decimal | None
    expense_variance: Decimal | None
    mandatory_dependency_count: int = 0
    unmet_mandatory_count: int = 0
    optional_dependency_warning_count: int = 0
    forced_dependency_conflict_count: int = 0


class ScenarioPeriodOut(BaseModel):
    period_key: str
    target: Decimal | None
    selected_demand: Decimal
    variance: Decimal | None
    approximation: bool = False
    capex_demand: Decimal = Decimal("0")
    expense_demand: Decimal = Decimal("0")
    unclassified_demand: Decimal = Decimal("0")
    capex_target: Decimal | None = None
    expense_target: Decimal | None = None
    capex_variance: Decimal | None = None
    expense_variance: Decimal | None = None


class ScenarioReadinessOut(BaseModel):
    status: str
    source_current: bool
    warnings: list[str]
    blockers: list[str]


class BudgetScenarioOut(BaseModel):
    id: int
    tenant_id: int
    portfolio_workspace_id: int
    logical_code: str
    scenario_name: str
    scenario_code: str | None
    description: str
    status: str
    analytical_status: str
    budget_target_id: int
    source_analysis_hash: str
    source_prioritization_hash: str
    membership_set_hash: str
    evaluation_set_hash: str
    source_configuration_hash: str
    budget_target_hash: str
    source_hash: str
    scenario_hash: str
    creation_mode: str
    time_phasing_method: str
    scenario_revision: int
    revision_version: int
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    frozen_at: datetime | None
    voided_at: datetime | None
    projects: list[ScenarioProjectOut]
    summary: ScenarioSummaryOut
    period_view: list[ScenarioPeriodOut]
    strategic_balance: dict
    readiness: ScenarioReadinessOut
    warnings: list[str]
    blockers: list[str]
    allowed_actions: list[str]
    dependency_summary: dict = Field(default_factory=dict)


class ScenarioRefreshPreviewOut(BaseModel):
    scenario_id: int
    current_source_hash: str
    proposed_source_hash: str
    projects_added: list[int]
    projects_removed: list[int]
    rank_changes: list[dict]
    score_changes: list[dict]
    cost_changes: list[dict]
    date_changes: list[dict]
    persisted: bool = False


class ScenarioRefreshApplyIn(IdempotencyIn):
    expected_source_hash: str = Field(min_length=64, max_length=64)


class ScenarioCompareIn(BaseModel):
    scenario_ids: list[int] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def unique_scenarios(self):
        if len(set(self.scenario_ids)) != len(self.scenario_ids):
            raise ValueError("scenario_ids must be unique")
        return self


class ScenarioComparisonOut(BaseModel):
    portfolio_workspace_id: int
    scenarios: list[dict]
    project_matrix: list[dict]
    pairwise_delta: dict
    warnings: list[str]


class WaterlineProjectOut(BaseModel):
    project_workspace_id: int
    project_number: str
    project_name: str
    portfolio_rank: int
    selection_state: str
    budget_demand: Decimal
    cumulative_selected_demand: Decimal
    target_budget: Decimal
    waterline_side: str
    forced_state: str | None
    dependency_status: str
    unmet_dependency_count: int
    capex_amount: Decimal | None
    expense_amount: Decimal | None
    unclassified_amount: Decimal
    project_type: str
    risk_bucket: str
    strategic_objectives: list[dict]


class WaterlineOut(BaseModel):
    scenario_id: int
    period_key: str
    rank_source: str = "GATE07E_CONTEXTUAL_PORTFOLIO_RANK"
    target_budget: Decimal
    selected_demand: Decimal
    variance: Decimal
    analytical_status: str
    alignment_status: str
    waterline_position: int | None
    projects: list[WaterlineProjectOut]
    budget_breakdown: dict
    dependency_summary: dict
    allowed_actions: list[str]


class ProjectDependencyCreateIn(BaseModel):
    predecessor_project_workspace_id: int = Field(gt=0)
    successor_project_workspace_id: int = Field(gt=0)
    dependency_type: str = Field(
        default="PREREQUISITE",
        pattern="^(PREREQUISITE|ENABLING|SEQUENTIAL|SHARED_INFRASTRUCTURE|REGULATORY|FUNDING|OTHER)$",
    )
    dependency_strength: str = Field(default="MANDATORY", pattern="^(MANDATORY|OPTIONAL)$")
    description: str = Field(default="", max_length=4000)
    effective_from: date | None = None
    effective_to: date | None = None
    source_reference: str | None = Field(default=None, max_length=300)
    evidence_refs: list[dict] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def valid_dependency(self):
        if self.predecessor_project_workspace_id == self.successor_project_workspace_id:
            raise ValueError("self dependency is not allowed")
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self


class ProjectDependencyUpdateIn(BaseModel):
    dependency_type: str = Field(
        pattern="^(PREREQUISITE|ENABLING|SEQUENTIAL|SHARED_INFRASTRUCTURE|REGULATORY|FUNDING|OTHER)$"
    )
    dependency_strength: str = Field(pattern="^(MANDATORY|OPTIONAL)$")
    description: str = Field(default="", max_length=4000)
    effective_from: date | None = None
    effective_to: date | None = None
    source_reference: str | None = Field(default=None, max_length=300)
    evidence_refs: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_range(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self


class ProjectDependencyOut(BaseModel):
    id: int
    tenant_id: int
    predecessor_project_workspace_id: int
    predecessor_project_number: str
    predecessor_project_name: str
    successor_project_workspace_id: int
    successor_project_number: str
    successor_project_name: str
    dependency_type: str
    dependency_strength: str
    description: str
    effective_from: date | None
    effective_to: date | None
    status: str
    source_reference: str | None
    evidence_refs: list[dict]
    revision_version: int
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime


class ScenarioDependencyOut(BaseModel):
    scenario_id: int
    summary: dict
    projects: list[dict]
    warnings: list[str]
    blockers: list[str]


class PortfolioBudgetPlanningReadinessOut(BaseModel):
    portfolio_workspace_id: int
    scenario_count: int
    frozen_scenario_count: int
    ready_scenario_count: int
    budget_target_id: int | None
    warnings: list[str]
    blockers: list[str]
    budget_planning_hash: str
    can_enter_budget_recommendation: bool
    allowed_actions: list[str]
    final_output: str


class BudgetPlanningOverviewOut(BaseModel):
    portfolio_workspace_id: int
    gate07f: dict
    active_target: BudgetTargetOut | None
    targets: list[BudgetTargetOut]
    scenarios: list[BudgetScenarioOut]
    readiness: PortfolioBudgetPlanningReadinessOut
    allowed_actions: list[str]
    boundaries: list[str]


class BudgetRecommendationContractOut(BaseModel):
    portfolio_workspace_id: int
    budget_planning_hash: str
    budget_target_snapshot: dict
    ready_frozen_scenario_refs: list[dict]
    scenario_hashes: list[str]
    analysis_hash: str
    membership_set_hash: str
    evaluation_set_hash: str
    warnings: list[str]
    blockers: list[str]
    final_output: str


class ConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=3000)
    content_json: dict


class ConfigurationPreviewIn(BaseModel):
    portfolio_workspace_id: int | None = Field(default=None, gt=0)
    configuration_id: int | None = Field(default=None, gt=0)
    content_json: dict | None = None
    target_assumptions: dict | None = None


class ConfigurationPreviewOut(BaseModel):
    portfolio_workspace_id: int | None
    path: list[dict]
    effective_policy: dict
    source: dict
    eligible_project_count: int
    cost_coverage_percent: Decimal
    currency_status: str
    time_phasing_capability: list[str]
    warnings: list[str]
    blockers: list[str]
    validation_issues: list[str]
    publishable: bool
    persisted: bool = False
    waterline_preview: dict = Field(default_factory=dict)
    dependency_preview: dict = Field(default_factory=dict)
    budget_breakdown_preview: dict = Field(default_factory=dict)
