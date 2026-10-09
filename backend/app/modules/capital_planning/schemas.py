"""Typed contracts for Strategic Capital Planning and Demand Wave 1."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CycleStatus(StrEnum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    CLOSED = "CLOSED"


class DemandStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    RETURNED = "RETURNED"
    ENDORSED = "ENDORSED"
    DEFERRED = "DEFERRED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class CyclePayload(BaseModel):
    name: str = Field(min_length=3, max_length=220)
    planning_horizon_start: date
    planning_horizon_end: date
    scope_workspace_id: int | None = None
    responsible_organization_workspace_id: int | None = None
    applicable_theme_codes: list[str] = Field(default_factory=list, max_length=100)
    capital_basis_currency: str | None = Field(default=None, min_length=3, max_length=8)
    description: str = Field(default="", max_length=8000)

    @field_validator("name", "description")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("capital_basis_currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @field_validator("applicable_theme_codes")
    @classmethod
    def _codes(cls, values: list[str]) -> list[str]:
        return sorted({value.strip().lower() for value in values if value.strip()})

    @model_validator(mode="after")
    def _dates(self):
        if self.planning_horizon_end < self.planning_horizon_start:
            raise ValueError("planning_horizon_end must be on or after planning_horizon_start")
        return self


class CycleCreate(CyclePayload):
    pass


class CycleUpdate(CyclePayload):
    pass


class CycleOut(BaseModel):
    id: int
    cycle_number: str
    name: str
    planning_horizon_start: date
    planning_horizon_end: date
    status: CycleStatus
    scope_workspace_id: int | None
    responsible_organization_workspace_id: int | None
    applicable_theme_codes: list[str]
    capital_basis_currency: str | None
    description: str
    configuration_hash: str
    demand_count: int
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime
    opened_at: datetime | None
    review_started_at: datetime | None
    closed_at: datetime | None
    revision_version: int


class DemandPayload(BaseModel):
    name: str = Field(min_length=3, max_length=220)
    description: str = Field(default="", max_length=8000)
    planning_cycle_id: int
    theme_codes: list[str] = Field(default_factory=list, max_length=20)
    strategic_objective_codes: list[str] = Field(default_factory=list, max_length=50)
    business_or_asset_need: str = Field(min_length=3, max_length=12000)
    strategic_driver: str = Field(min_length=1, max_length=120)
    demand_category: str | None = Field(default=None, max_length=120)
    urgency: str | None = Field(default=None, max_length=40)
    target_horizon: str = Field(min_length=1, max_length=80)
    sponsor_user_id: int
    owning_workspace_id: int
    location_context: str | None = Field(default=None, max_length=300)
    indicative_capital_need: Decimal | None = Field(default=None, ge=0)
    currency_code: str | None = Field(default=None, min_length=3, max_length=8)
    indicative_capital_range_low: Decimal | None = Field(default=None, ge=0)
    indicative_capital_range_high: Decimal | None = Field(default=None, ge=0)
    uncertainty_level: str | None = Field(default=None, max_length=80)
    potential_portfolio_id: int | None = None
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    constraints: list[str] = Field(default_factory=list, max_length=100)
    dependencies: list[str] = Field(default_factory=list, max_length=100)

    @field_validator(
        "name",
        "description",
        "business_or_asset_need",
        "strategic_driver",
        "target_horizon",
    )
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("theme_codes", "strategic_objective_codes")
    @classmethod
    def _codes(cls, values: list[str]) -> list[str]:
        return sorted({value.strip().lower() for value in values if value.strip()})

    @field_validator("assumptions", "constraints", "dependencies")
    @classmethod
    def _statements(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]

    @field_validator("currency_code")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @model_validator(mode="after")
    def _capital_semantics(self):
        if self.indicative_capital_need is not None and not self.currency_code:
            raise ValueError("currency_code is required when indicative_capital_need is supplied")
        if self.indicative_capital_range_low is not None or self.indicative_capital_range_high is not None:
            if not self.currency_code:
                raise ValueError("currency_code is required for an indicative capital range")
        if (
            self.indicative_capital_range_low is not None
            and self.indicative_capital_range_high is not None
            and self.indicative_capital_range_high < self.indicative_capital_range_low
        ):
            raise ValueError("indicative_capital_range_high must be at least the low value")
        return self


class DemandCreate(DemandPayload):
    pass


class DemandUpdate(DemandPayload):
    pass


class DemandOut(BaseModel):
    id: int
    demand_number: str
    name: str
    description: str
    planning_cycle_id: int
    planning_cycle_number: str
    planning_cycle_name: str
    theme_codes: list[str]
    strategic_objective_codes: list[str]
    business_or_asset_need: str
    strategic_driver: str
    demand_category: str | None
    urgency: str | None
    target_horizon: str
    sponsor_user_id: int
    sponsor_name: str
    owning_workspace_id: int
    owning_workspace_name: str
    location_context: str | None
    indicative_capital_need: Decimal | None
    indicative_capital_semantics: str = "INDICATIVE_CAPITAL_NEED"
    currency_code: str | None
    indicative_capital_range_low: Decimal | None
    indicative_capital_range_high: Decimal | None
    uncertainty_level: str | None
    potential_portfolio_id: int | None
    potential_portfolio_name: str | None
    assumptions: list[str]
    constraints: list[str]
    dependencies: list[str]
    status: DemandStatus
    readiness: dict
    ideas_originated: int
    configuration_hash: str
    demand_hash: str
    endorsed_snapshot_hash: str | None
    created_by_user_id: int
    reviewer_user_id: int | None
    endorser_user_id: int | None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    review_started_at: datetime | None
    endorsed_at: datetime | None
    revision_version: int
    allowed_actions: list[str]
    resolved_bucket_code: str | None = None
    resolved_bucket_name: str | None = None
    resolved_bucket_source: str | None = None


class DemandPageOut(BaseModel):
    items: list[DemandOut]
    total: int
    page: int
    page_size: int


class CyclePageOut(BaseModel):
    items: list[CycleOut]
    total: int
    page: int
    page_size: int


class IdempotencyIn(BaseModel):
    reason: str = Field(default="", max_length=3000)


class OriginateIdeaIn(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=220)
    description: str | None = Field(default=None, min_length=3, max_length=8000)
    idea_type: str | None = Field(default=None, max_length=80)
    category: str | None = Field(default=None, max_length=120)
    expected_benefit: str = Field(default="", max_length=4000)


class IdeaOriginOut(BaseModel):
    id: int
    source_capital_demand_id: int
    idea_id: int
    idea_number: str
    source_demand_version: int
    source_snapshot_hash: str
    source_configuration_hash: str
    originated_by: int
    originated_at: datetime
    created: bool


class DemandHistoryItemOut(BaseModel):
    event_type: str
    outcome: str
    actor_user_id: int | None
    metadata: dict
    occurred_at: datetime


class CycleSummaryOut(BaseModel):
    cycle_id: int
    demand_count: int
    status_counts: dict[str, int]
    theme_counts: dict[str, int]
    driver_counts: dict[str, int]
    horizon_counts: dict[str, int]
    uncertainty_counts: dict[str, int]
    indicative_capital_totals_by_currency: dict[str, Decimal]
    unpriced_demand_count: int
    normalization_warning: str | None


class CapitalPlanningOptionsOut(BaseModel):
    cycle_number_preview: str
    demand_number_preview: str
    themes: list[dict]
    demand_drivers: list[dict]
    demand_categories: list[dict]
    planning_horizons: list[dict]
    urgency_levels: list[dict]
    uncertainty_levels: list[dict]
    strategic_objectives: list[dict]
    owning_workspaces: list[dict]
    potential_portfolios: list[dict]
    sponsors: list[dict]
    idea_types: list[dict]
    idea_categories: list[dict]
    effective_configuration: dict
    configuration_source: dict


class ConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=3000)
    content_json: dict


class ConfigurationCloneIn(BaseModel):
    """Optional target for an explicit workspace-scoped override."""

    target_workspace_id: int | None = Field(default=None, ge=1)


class ConfigurationPreviewIn(BaseModel):
    owning_workspace_id: int | None = None


class ConfigurationRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    code: str
    name: str
    description: str
    status: str
    revision: int
    version: int
    content_json: dict
    content_hash: str
    published_at: datetime | None
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime


class ConfigurationPreviewOut(BaseModel):
    owning_workspace_id: int | None
    persisted: bool = False
    effective: dict
    source: dict
    resolution_path: list[dict]


class AllocationPlanStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    RETURNED = "RETURNED"
    ENDORSED = "ENDORSED"
    SUPERSEDED = "SUPERSEDED"
    CANCELLED = "CANCELLED"


class AllocationBasis(StrEnum):
    PERCENTAGE = "PERCENTAGE"
    INDICATIVE_AMOUNT = "INDICATIVE_AMOUNT"
    PERCENTAGE_AND_AMOUNT = "PERCENTAGE_AND_AMOUNT"


class AllocationPlanPayload(BaseModel):
    name: str = Field(min_length=3, max_length=220)
    description: str = Field(default="", max_length=8000)
    planning_cycle_id: int = Field(gt=0)
    scope_workspace_id: int = Field(gt=0)
    portfolio_workspace_id: int | None = Field(default=None, gt=0)
    base_currency: str | None = Field(default=None, min_length=3, max_length=8)
    allocation_basis: AllocationBasis
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    constraints: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("name", "description")
    @classmethod
    def _allocation_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("base_currency")
    @classmethod
    def _allocation_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @field_validator("assumptions", "constraints")
    @classmethod
    def _allocation_statements(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]

    @model_validator(mode="after")
    def _basis_currency(self):
        if (
            self.allocation_basis
            in {
                AllocationBasis.INDICATIVE_AMOUNT,
                AllocationBasis.PERCENTAGE_AND_AMOUNT,
            }
            and not self.base_currency
        ):
            raise ValueError("base_currency is required for amount-based strategic allocation")
        return self


class AllocationPlanCreate(AllocationPlanPayload):
    pass


class AllocationPlanUpdate(AllocationPlanPayload):
    pass


class AllocationLineIn(BaseModel):
    bucket_code: str = Field(min_length=1, max_length=120)
    target_percentage: Decimal | None = Field(default=None, ge=0, le=100)
    target_amount: Decimal | None = Field(default=None, ge=0)
    minimum_percentage: Decimal | None = Field(default=None, ge=0, le=100)
    maximum_percentage: Decimal | None = Field(default=None, ge=0, le=100)
    minimum_amount: Decimal | None = Field(default=None, ge=0)
    maximum_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=8)
    rationale: str = Field(default="", max_length=8000)
    strategic_objective_codes: list[str] = Field(default_factory=list, max_length=50)
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    constraints: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("bucket_code")
    @classmethod
    def _allocation_bucket(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("currency")
    @classmethod
    def _line_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @field_validator("strategic_objective_codes")
    @classmethod
    def _line_objectives(cls, values: list[str]) -> list[str]:
        return sorted({value.strip().lower() for value in values if value.strip()})

    @field_validator("assumptions", "constraints")
    @classmethod
    def _line_statements(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]

    @model_validator(mode="after")
    def _ranges(self):
        if (
            self.minimum_percentage is not None
            and self.target_percentage is not None
            and self.minimum_percentage > self.target_percentage
        ):
            raise ValueError("minimum_percentage cannot exceed target_percentage")
        if (
            self.maximum_percentage is not None
            and self.target_percentage is not None
            and self.maximum_percentage < self.target_percentage
        ):
            raise ValueError("maximum_percentage cannot be below target_percentage")
        if (
            self.minimum_amount is not None
            and self.target_amount is not None
            and self.minimum_amount > self.target_amount
        ):
            raise ValueError("minimum_amount cannot exceed target_amount")
        if (
            self.maximum_amount is not None
            and self.target_amount is not None
            and self.maximum_amount < self.target_amount
        ):
            raise ValueError("maximum_amount cannot be below target_amount")
        return self


class AllocationLinesReplaceIn(BaseModel):
    lines: list[AllocationLineIn] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _unique_buckets(self):
        codes = [item.bucket_code for item in self.lines]
        if len(codes) != len(set(codes)):
            raise ValueError("bucket_code must be unique within an Allocation Plan")
        return self


class AllocationLineOut(AllocationLineIn):
    id: int
    line_hash: str


class AllocationPlanOut(BaseModel):
    id: int
    allocation_plan_number: str
    logical_code: str
    plan_revision: int
    name: str
    description: str
    planning_cycle_id: int
    planning_cycle_number: str
    planning_cycle_name: str
    scope_workspace_id: int
    scope_workspace_name: str
    scope_type: str
    portfolio_workspace_id: int | None
    portfolio_workspace_name: str | None
    base_currency: str | None
    allocation_basis: AllocationBasis
    allocation_semantics: str = "STRATEGIC_PLANNING_ENVELOPE_NOT_APPROVED_BUDGET"
    status: AllocationPlanStatus
    assumptions: list[str]
    constraints: list[str]
    configuration_revision: int
    configuration_hash: str
    plan_hash: str
    endorsed_snapshot_hash: str | None
    lines: list[AllocationLineOut]
    readiness: dict
    source_current: bool
    created_by_user_id: int
    reviewer_user_id: int | None
    endorser_user_id: int | None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    review_started_at: datetime | None
    endorsed_at: datetime | None
    revision_version: int
    allowed_actions: list[str]


class AllocationPlanPageOut(BaseModel):
    items: list[AllocationPlanOut]
    total: int
    page: int
    page_size: int


class BucketClassificationIn(BaseModel):
    target_type: str = Field(pattern="^(DEMAND|PROJECT|PORTFOLIO_MEMBERSHIP)$")
    target_id: int = Field(gt=0)
    bucket_code: str = Field(min_length=1, max_length=120)
    rationale: str = Field(default="", max_length=8000)

    @field_validator("bucket_code")
    @classmethod
    def _classification_bucket(cls, value: str) -> str:
        return value.strip().lower()


class BucketClassificationOut(BaseModel):
    id: int
    allocation_plan_id: int
    target_type: str
    target_id: int
    bucket_code: str
    classification_source: str
    rationale: str
    classification_hash: str
    classified_by_user_id: int
    classified_at: datetime
    revision_version: int


class BucketClassificationsReplaceIn(BaseModel):
    classifications: list[BucketClassificationIn] = Field(default_factory=list, max_length=5000)

    @model_validator(mode="after")
    def _one_primary_per_target(self):
        keys = [(item.target_type, item.target_id) for item in self.classifications]
        if len(keys) != len(set(keys)):
            raise ValueError("only one primary Bucket is allowed per target")
        return self


class BucketClassificationBatchOut(BaseModel):
    allocation_plan: AllocationPlanOut
    classifications: list[BucketClassificationOut]


class AllocationPositionOut(BaseModel):
    amount_by_currency: dict[str, Decimal] = Field(default_factory=dict)
    percentage: Decimal | None = None
    item_count: int = 0
    evaluable: bool = True
    source: str
    drilldown: list[dict] = Field(default_factory=list)


class BucketComparisonOut(BaseModel):
    bucket_code: str
    bucket_name: str
    minimum_percentage: Decimal | None = None
    target_percentage: Decimal | None = None
    maximum_percentage: Decimal | None = None
    minimum_amount: Decimal | None = None
    target_amount: Decimal | None = None
    maximum_amount: Decimal | None = None
    target_currency: str | None = None
    current_demand: AllocationPositionOut
    current_portfolio: AllocationPositionOut
    recommended: AllocationPositionOut
    approved: AllocationPositionOut
    variance_vs_target_percentage: Decimal | None = None
    variance_vs_target_amount: Decimal | None = None
    status: str


class AllocationComparisonOut(BaseModel):
    allocation_plan_id: int
    allocation_plan_version: int
    allocation_plan_hash: str
    configuration_hash: str
    population_definition: dict
    classification_precedence: list[str]
    positions: list[BucketComparisonOut]
    unclassified: dict
    classification_coverage_percentage: Decimal
    multi_currency: bool
    normalization_warning: str | None
    source_hash: str
    generated_at: datetime


class AllocationPlanHistoryItemOut(BaseModel):
    event_type: str
    outcome: str
    actor_user_id: int | None
    metadata: dict
    occurred_at: datetime


class AllocationOptionsOut(BaseModel):
    allocation_plan_number_preview: str
    planning_cycles: list[dict]
    scope_workspaces: list[dict]
    portfolios: list[dict]
    strategic_capital_buckets: list[dict]
    allocation_basis_options: list[str]
    scope_types: list[str]
    effective_configuration: dict
    configuration_source: dict
