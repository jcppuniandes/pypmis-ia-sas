"""API contracts for Gate 07H Portfolio Resource Planning."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CapacityPeriodIn(BaseModel):
    resource_role_key: str = Field(min_length=1, max_length=100)
    resource_role_name: str = Field(min_length=1, max_length=180)
    role_category: str = Field(default="OTHER", max_length=40)
    period_key: str = Field(min_length=1, max_length=20)
    period_start: date
    period_end: date
    capacity_value: Decimal = Field(ge=0)
    unit: str = Field(default="FTE", pattern="^(FTE|HOURS|CREW_EQUIVALENT)$")
    source_reference: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def valid_range(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class CapacityPlanCreateIn(BaseModel):
    plan_name: str = Field(min_length=3, max_length=180)
    planning_horizon_start: date
    planning_horizon_end: date
    period_granularity: str = Field(default="MONTH", pattern="^(YEAR|QUARTER|MONTH)$")
    source_reference: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=4000)
    periods: list[CapacityPeriodIn] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def valid_range(self):
        if self.planning_horizon_end < self.planning_horizon_start:
            raise ValueError("planning_horizon_end must be on or after planning_horizon_start")
        return self


class CapacityPlanUpdateIn(BaseModel):
    plan_name: str = Field(min_length=3, max_length=180)
    planning_horizon_start: date
    planning_horizon_end: date
    period_granularity: str = Field(pattern="^(YEAR|QUARTER|MONTH)$")
    source_reference: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=4000)
    periods: list[CapacityPeriodIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_range(self):
        if self.planning_horizon_end < self.planning_horizon_start:
            raise ValueError("planning_horizon_end must be on or after planning_horizon_start")
        return self


class IdempotencyIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class CapacityPeriodOut(CapacityPeriodIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class CapacityPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    portfolio_workspace_id: int
    logical_code: str
    plan_name: str
    planning_horizon_start: date
    planning_horizon_end: date
    period_granularity: str
    status: str
    plan_revision: int
    source_reference: str
    notes: str
    capacity_hash: str
    revision_version: int
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    published_at: datetime | None
    periods: list[CapacityPeriodOut]


class DemandPeriodIn(BaseModel):
    resource_role_key: str = Field(min_length=1, max_length=100)
    resource_role_name: str = Field(min_length=1, max_length=180)
    role_category: str = Field(default="OTHER", max_length=40)
    period_key: str = Field(min_length=1, max_length=20)
    period_start: date
    period_end: date
    demand_value: Decimal = Field(ge=0)
    unit: str = Field(default="FTE", pattern="^(FTE|HOURS|CREW_EQUIVALENT)$")
    source_reference: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def valid_range(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class DemandProfileCreateIn(BaseModel):
    profile_name: str = Field(min_length=3, max_length=180)
    source_type: str = Field(
        pattern=(
            "^(PROJECT_RESOURCE_DEMAND_PROFILE|PROJECT_DEFINITION_RESOURCE_ESTIMATE|"
            "TEMPLATE_RESOURCE_PROFILE|MANUAL_PORTFOLIO_PLANNING_PROFILE)$"
        )
    )
    source_reference: str = Field(default="", max_length=300)
    as_of_date: date
    planning_start: date
    planning_finish: date
    generation_method: str = Field(
        default="EXPLICIT_PERIOD_PROFILE",
        pattern="^(EXPLICIT_PERIOD_PROFILE|LINEAR_BY_PROJECT_DATES|TEMPLATE_BASED)$",
    )
    periods: list[DemandPeriodIn] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def valid_range(self):
        if self.planning_finish < self.planning_start:
            raise ValueError("planning_finish must be on or after planning_start")
        return self


class DemandProfileUpdateIn(BaseModel):
    profile_name: str = Field(min_length=3, max_length=180)
    source_type: str = Field(
        pattern=(
            "^(PROJECT_RESOURCE_DEMAND_PROFILE|PROJECT_DEFINITION_RESOURCE_ESTIMATE|"
            "TEMPLATE_RESOURCE_PROFILE|MANUAL_PORTFOLIO_PLANNING_PROFILE)$"
        )
    )
    source_reference: str = Field(default="", max_length=300)
    as_of_date: date
    planning_start: date
    planning_finish: date
    generation_method: str = Field(pattern="^(EXPLICIT_PERIOD_PROFILE|LINEAR_BY_PROJECT_DATES|TEMPLATE_BASED)$")
    periods: list[DemandPeriodIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_range(self):
        if self.planning_finish < self.planning_start:
            raise ValueError("planning_finish must be on or after planning_start")
        return self


class DemandPeriodOut(DemandPeriodIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class DemandProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    project_workspace_id: int
    logical_code: str
    profile_name: str
    status: str
    profile_revision: int
    source_type: str
    source_reference: str
    source_hash: str
    as_of_date: date
    planning_start: date
    planning_finish: date
    generation_method: str
    approximation: bool
    demand_hash: str
    revision_version: int
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    published_at: datetime | None
    periods: list[DemandPeriodOut]


class ResourceScenarioCreateIn(BaseModel):
    scenario_name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=4000)
    capacity_plan_id: int = Field(gt=0)
    creation_mode: str = Field(pattern="^(EMPTY|FROM_CURRENT_PRIORITY|COPY_EXISTING_SCENARIO)$")
    source_scenario_id: int | None = Field(default=None, gt=0)
    expected_analysis_hash: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def copy_source_required(self):
        if self.creation_mode == "COPY_EXISTING_SCENARIO" and self.source_scenario_id is None:
            raise ValueError("source_scenario_id is required for COPY_EXISTING_SCENARIO")
        return self


class ResourceScenarioUpdateIn(BaseModel):
    scenario_name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=4000)
    status: str = Field(default="DRAFT", pattern="^(DRAFT|IN_REVIEW)$")


class ScenarioSelectionIn(BaseModel):
    selection_state: str = Field(pattern="^(SELECTED|UNSELECTED|FORCED_IN|FORCED_OUT)$")
    forced_reason: str | None = Field(default=None, max_length=4000)
    authority_reference: str | None = Field(default=None, max_length=300)
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def forced_reason_required(self):
        if self.selection_state in {"FORCED_IN", "FORCED_OUT"} and not (self.forced_reason or "").strip():
            raise ValueError("forced_reason is required for forced states")
        return self


class ScenarioTimingIn(BaseModel):
    timing_method: str = Field(pattern="^(NO_SHIFT|SHIFT_START_KEEP_DURATION|CUSTOM_SCENARIO_DATES)$")
    scenario_start: date | None = None
    scenario_finish: date | None = None
    idempotency_key: str = Field(min_length=8, max_length=160)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.timing_method == "CUSTOM_SCENARIO_DATES" and (not self.scenario_start or not self.scenario_finish):
            raise ValueError("scenario_start and scenario_finish are required for custom dates")
        if self.scenario_start and self.scenario_finish and self.scenario_finish < self.scenario_start:
            raise ValueError("scenario_finish must be on or after scenario_start")
        if self.timing_method == "SHIFT_START_KEEP_DURATION" and not self.scenario_start:
            raise ValueError("scenario_start is required for SHIFT_START_KEEP_DURATION")
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
    resource_demand_profile_id: int | None
    resource_demand_hash: str
    source_project_start: date | None
    source_project_finish: date | None
    scenario_start: date | None
    scenario_finish: date | None
    schedule_shift_days: int
    timing_method: str
    selection_state: str
    forced_reason: str | None
    forced_actor_id: int | None
    forced_at: datetime | None
    forced_authority_reference: str | None
    demand_covered: bool
    revision_version: int


class CapacityDemandCellOut(BaseModel):
    resource_role_key: str
    resource_role_name: str
    role_category: str
    period_key: str
    period_start: date
    period_end: date
    unit: str
    capacity: Decimal
    selected_demand: Decimal
    variance: Decimal
    utilization_percent: Decimal | None
    status: str


class ResourceHistogramBarOut(BaseModel):
    period_key: str
    unit: str
    capacity: Decimal
    selected_demand: Decimal
    variance: Decimal


class ResourceScenarioSummaryOut(BaseModel):
    selected_count: int
    unselected_count: int
    forced_in_count: int
    forced_out_count: int
    average_score: Decimal | None
    high_risk_count: int
    overloaded_role_count: int
    overloaded_period_count: int
    peak_overload: Decimal
    peak_utilization: Decimal | None
    average_utilization: Decimal | None
    demand_coverage_percent: Decimal


class ResourceScenarioReadinessOut(BaseModel):
    status: str
    source_current: bool
    demand_coverage_percent: Decimal
    warnings: list[str]
    blockers: list[str]


class ResourceScenarioOut(BaseModel):
    id: int
    tenant_id: int
    portfolio_workspace_id: int
    logical_code: str
    scenario_name: str
    description: str
    status: str
    capacity_plan_id: int
    capacity_plan_hash: str
    source_analysis_hash: str
    source_hash: str
    scenario_hash: str
    creation_mode: str
    overload_policy: str
    scenario_revision: int
    revision_version: int
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    frozen_at: datetime | None
    voided_at: datetime | None
    projects: list[ScenarioProjectOut]
    heatmap: list[CapacityDemandCellOut]
    summary: ResourceScenarioSummaryOut
    readiness: ResourceScenarioReadinessOut
    warnings: list[str]
    blockers: list[str]
    allowed_actions: list[str]


class ScenarioRefreshPreviewOut(BaseModel):
    scenario_id: int
    current_source_hash: str
    proposed_source_hash: str
    projects_added: list[int]
    projects_removed: list[int]
    demand_profile_changes: list[dict]
    date_changes: list[dict]
    persisted: bool = False


class ScenarioRefreshApplyIn(IdempotencyIn):
    expected_source_hash: str = Field(min_length=64, max_length=64)


class ScenarioCompareIn(BaseModel):
    scenario_ids: list[int] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def unique_ids(self):
        if len(set(self.scenario_ids)) != len(self.scenario_ids):
            raise ValueError("scenario_ids must be unique")
        return self


class ScenarioComparisonOut(BaseModel):
    portfolio_workspace_id: int
    scenarios: list[dict]
    project_matrix: list[dict]
    pairwise_delta: dict
    role_demand_delta: list[dict]
    warnings: list[str]


class PortfolioResourcePlanningReadinessOut(BaseModel):
    portfolio_workspace_id: int
    capacity_plan_id: int | None
    scenario_count: int
    frozen_scenario_count: int
    ready_scenario_count: int
    demand_coverage: Decimal
    overloaded_scenario_count: int
    warnings: list[str]
    blockers: list[str]
    resource_planning_hash: str
    can_enter_resource_recommendation: bool
    allowed_actions: list[str]
    final_output: str


class ResourcePlanningOverviewOut(BaseModel):
    portfolio_workspace_id: int
    gate07f: dict
    active_capacity_plan: CapacityPlanOut | None
    capacity_plans: list[CapacityPlanOut]
    demand_profiles: list[DemandProfileOut]
    scenarios: list[ResourceScenarioOut]
    readiness: PortfolioResourcePlanningReadinessOut
    allowed_actions: list[str]
    boundaries: list[str]


class ResourceRecommendationContractOut(BaseModel):
    portfolio_workspace_id: int
    resource_planning_hash: str
    capacity_plan_snapshot: dict
    ready_frozen_scenario_refs: list[dict]
    scenario_hashes: list[str]
    gate07f_analysis_hash: str
    membership_set_hash: str
    evaluation_set_hash: str
    demand_coverage: Decimal
    overload_summary: dict
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


class ConfigurationPreviewOut(BaseModel):
    portfolio_workspace_id: int | None
    path: list[dict]
    effective: dict
    source: dict
    publishable: bool
    validation_issues: list[str]
    readiness_preview: dict | None
    warnings: list[str]
    blockers: list[str]
    persisted: bool = False
