"""HTTP contracts for Wave 3A Periodic Portfolio Review."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ReviewStatus(StrEnum):
    DRAFT = "DRAFT"
    PREPARING = "PREPARING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    IN_REVIEW = "IN_REVIEW"
    STALE = "STALE"
    RETURNED = "RETURNED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class ReviewActionStatus(StrEnum):
    OPEN = "OPEN"
    ACCEPTED = "ACCEPTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


def _upper(value: str) -> str:
    return value.strip().upper()


class AgendaSectionIn(BaseModel):
    code: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=220)
    status: str = Field(default="NOT_STARTED", max_length=40)
    notes: str = Field(default="", max_length=8000)
    evidence_references: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("code", "status")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return _upper(value)


class PortfolioReviewCreate(BaseModel):
    portfolio_workspace_id: int = Field(gt=0)
    scope_workspace_id: int | None = Field(default=None, gt=0)
    planning_cycle_id: int | None = Field(default=None, gt=0)
    allocation_plan_id: int | None = Field(default=None, gt=0)
    review_type: str = Field(default="SCHEDULED", min_length=1, max_length=80)
    review_date: date
    review_period_start: date | None = None
    review_period_end: date | None = None
    next_planned_review_date: date | None = None
    title: str = Field(default="", max_length=240)
    description: str = Field(default="", max_length=8000)
    chair_user_id: int | None = Field(default=None, gt=0)
    secretary_user_id: int | None = Field(default=None, gt=0)
    agenda: list[AgendaSectionIn] = Field(default_factory=list)

    @field_validator("review_type")
    @classmethod
    def normalize_review_type(cls, value: str) -> str:
        return _upper(value)

    @model_validator(mode="after")
    def validate_dates(self) -> "PortfolioReviewCreate":
        if self.review_period_start and self.review_period_end and self.review_period_end < self.review_period_start:
            raise ValueError("review_period_end must be on or after review_period_start")
        return self


class PortfolioReviewUpdate(BaseModel):
    allocation_plan_id: int | None = Field(default=None, gt=0)
    review_type: str | None = Field(default=None, min_length=1, max_length=80)
    review_date: date | None = None
    review_period_start: date | None = None
    review_period_end: date | None = None
    next_planned_review_date: date | None = None
    title: str | None = Field(default=None, min_length=3, max_length=240)
    description: str | None = Field(default=None, max_length=8000)
    chair_user_id: int | None = Field(default=None, gt=0)
    secretary_user_id: int | None = Field(default=None, gt=0)
    agenda: list[AgendaSectionIn] | None = None

    @field_validator("review_type")
    @classmethod
    def normalize_review_type(cls, value: str | None) -> str | None:
        return _upper(value) if value is not None else None

    @model_validator(mode="after")
    def reject_required_nulls(self) -> "PortfolioReviewUpdate":
        for field in ("review_type", "review_date", "title", "description", "chair_user_id", "agenda"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class SnapshotCommandIn(BaseModel):
    reason: str = Field(default="", max_length=2000)


class CompleteReviewIn(BaseModel):
    actual_review_date: date | None = None
    next_planned_review_date: date | None = None
    completion_note: str = Field(default="", max_length=4000)


class ReviewTransitionIn(BaseModel):
    reason: str = Field(min_length=3, max_length=4000)
    replacement_review_session_id: int | None = Field(default=None, gt=0)


class PortfolioReviewConclusionCreate(BaseModel):
    conclusion_type: str = Field(min_length=1, max_length=120)
    rationale: str = Field(min_length=3, max_length=12000)
    conditions: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("conclusion_type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return _upper(value)


class PortfolioReviewConclusionUpdate(PortfolioReviewConclusionCreate):
    pass


class PortfolioReviewActionCreate(BaseModel):
    subject_type: str = Field(default="PORTFOLIO", min_length=1, max_length=40)
    subject_id: int | None = Field(default=None, gt=0)
    subject_key: str | None = Field(default=None, min_length=1, max_length=120)
    action_type: str = Field(min_length=1, max_length=120)
    rationale: str = Field(min_length=3, max_length=12000)
    priority: str = Field(default="MEDIUM", min_length=1, max_length=24)
    owner_user_id: int = Field(gt=0)
    due_date: date | None = None
    source_evidence_references: list[dict[str, Any]] = Field(default_factory=list)
    requested_source_authority: str | None = Field(default=None, max_length=120)

    @field_validator("subject_type", "action_type", "priority")
    @classmethod
    def normalize_codes(cls, value: str) -> str:
        return _upper(value)

    @field_validator("requested_source_authority")
    @classmethod
    def normalize_authority(cls, value: str | None) -> str | None:
        return _upper(value) if value else None


class PortfolioReviewActionUpdate(BaseModel):
    rationale: str | None = Field(default=None, min_length=3, max_length=12000)
    priority: str | None = Field(default=None, min_length=1, max_length=24)
    owner_user_id: int | None = Field(default=None, gt=0)
    due_date: date | None = None
    status: ReviewActionStatus | None = None
    source_evidence_references: list[dict[str, Any]] | None = None

    @field_validator("priority")
    @classmethod
    def normalize_priority(cls, value: str | None) -> str | None:
        return _upper(value) if value else None


class ActionApprovalIn(BaseModel):
    approval_note: str = Field(default="", max_length=4000)


class ActionDispatchIn(BaseModel):
    dispatch_note: str = Field(default="", max_length=4000)


class PortfolioReviewConclusionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    review_session_id: int
    conclusion_type: str
    rationale: str
    conditions_json: list[dict[str, Any]]
    created_by_user_id: int
    created_at: datetime
    updated_by_user_id: int
    updated_at: datetime
    revision_version: int


class PortfolioReviewActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action_number: str
    review_session_id: int
    subject_type: str
    subject_id: int | None
    subject_key: str | None = None
    action_type: str
    rationale: str
    priority: str
    owner_user_id: int
    due_date: date | None
    status: str
    source_evidence_references_json: list[dict[str, Any]]
    requested_source_authority: str | None
    dispatch_status: str
    execution_reference: str | None
    source_mutation_performed: bool = False
    authority_effect: str = "GOVERNANCE_REQUEST_ONLY"
    created_by_user_id: int
    approved_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    dispatched_at: datetime | None
    completed_at: datetime | None
    revision_version: int
    overdue: bool = False
    allowed_actions: list[str] = Field(default_factory=list)


class PortfolioReviewSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    review_number: str
    portfolio_workspace_id: int
    portfolio_code: str
    portfolio_name: str
    scope_workspace_id: int
    planning_cycle_id: int | None
    allocation_plan_id: int | None
    review_type: str
    review_date: date
    review_period_start: date | None
    review_period_end: date | None
    actual_review_date: date | None
    next_planned_review_date: date | None
    status: str
    effective_status: str
    title: str
    description: str
    chair_user_id: int
    secretary_user_id: int | None
    agenda: list[dict[str, Any]]
    configuration_id: int
    configuration_revision: int
    configuration_hash: str
    current_snapshot_id: int | None
    current_snapshot_hash: str | None
    snapshot_status: str
    snapshot_stale: bool
    source_current: bool
    readiness: dict[str, Any]
    conclusions: list[PortfolioReviewConclusionOut]
    action_summary: dict[str, int]
    snapshot: dict[str, Any] | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    actions: list[PortfolioReviewActionOut] = Field(default_factory=list)
    cadence: dict[str, Any] = Field(default_factory=dict)
    created_by_user_id: int
    prepared_by_user_id: int | None
    review_authority_user_id: int | None
    created_at: datetime
    updated_at: datetime
    prepared_at: datetime | None
    review_started_at: datetime | None
    completed_at: datetime | None
    revision_version: int
    allowed_actions: list[str]


class PortfolioReviewPageOut(BaseModel):
    items: list[PortfolioReviewSessionOut]
    total: int
    page: int
    page_size: int


class SnapshotPreviewOut(BaseModel):
    review_session_id: int
    persisted: bool = False
    candidate_snapshot_hash: str
    current_snapshot_id: int | None
    current_snapshot_hash: str | None
    source_current: bool
    stale: bool
    changes: list[dict[str, Any]]
    readiness: dict[str, Any]
    warnings: list[str]
    blockers: list[str]
    source_index: dict[str, Any]
    snapshot: dict[str, Any]
    generated_at: datetime


class PortfolioReviewSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    review_session_id: int
    snapshot_version: int
    snapshot_json: dict[str, Any]
    source_index_json: dict[str, Any]
    readiness_json: dict[str, Any]
    warnings_json: list[str]
    blockers_json: list[str]
    snapshot_hash: str
    frozen_by_user_id: int
    frozen_at: datetime


class ProjectMatrixRowOut(BaseModel):
    project_workspace_id: int
    membership_id: int
    project_code: str
    project_name: str
    project_status: str
    project_type: str = ""
    portfolio_rank: int | None
    evaluation_id: int | None
    evaluation_version: int | None
    evaluation_hash: str | None
    strategic_bucket: str
    allocation_variance_contribution: dict[str, Any]
    budget_status: str
    budget_context: dict[str, Any]
    resource_status: str
    resource_context: dict[str, Any]
    gate_stage: str
    gate_readiness: str
    investment_decision: str
    fid_status: str
    risk_readiness: str
    risk_summary: dict[str, Any]
    recommended_status: str
    approved_amount_context: dict[str, Any]
    review_actions: list[dict[str, Any]]
    blocked: bool
    stale: bool


class ProjectMatrixPageOut(BaseModel):
    items: list[ProjectMatrixRowOut]
    total: int
    page: int
    page_size: int
    snapshot_hash: str
    source: str = "FROZEN_REVIEW_SNAPSHOT"


class PortfolioAllocationOut(BaseModel):
    review_session_id: int
    snapshot_hash: str
    allocation_plan: dict[str, Any]
    comparison: dict[str, Any]
    multi_currency: bool
    normalization_warning: str | None
    source: str = "WAVE2A_FROZEN_REFERENCE"


class PortfolioBudgetResourcesOut(BaseModel):
    review_session_id: int
    snapshot_hash: str
    budget: dict[str, Any]
    resources: dict[str, Any]
    source: str = "FROZEN_REVIEW_SNAPSHOT"


class PortfolioGateStatusOut(BaseModel):
    review_session_id: int
    snapshot_hash: str
    gate_preparation: dict[str, Any]
    investment_decisions: list[dict[str, Any]]
    distribution: dict[str, Any]
    semantic_boundary: str = "GATE07K_HOLD_IS_NOT_PORTFOLIO_HOLD_FOR_CAPACITY"


class PortfolioReviewHistoryItemOut(BaseModel):
    event_type: str
    outcome: str
    actor_user_id: int | None
    target_type: str
    target_id: int | None
    metadata: dict[str, Any]
    occurred_at: datetime


class PortfolioReviewComparisonOut(BaseModel):
    current_review_id: int
    other_review_id: int
    current_snapshot_hash: str
    other_snapshot_hash: str
    deltas: dict[str, Any]
    historical_only: bool = True


class PortfolioReviewTrendPointOut(BaseModel):
    review_session_id: int
    review_number: str
    review_date: date
    snapshot_hash: str
    portfolio_project_count: int
    unclassified_exposure: dict[str, Any]
    allocation_variance: dict[str, Any]
    budget_feasibility: str
    resource_feasibility: str
    blocked_project_count: int
    open_action_count_at_close: int
    fid_count: int


class PortfolioReviewTrendsOut(BaseModel):
    portfolio_workspace_id: int
    points: list[PortfolioReviewTrendPointOut]
    interpolation_applied: bool = False


class PortfolioReviewActionPageOut(BaseModel):
    items: list[PortfolioReviewActionOut]
    total: int
    page: int
    page_size: int


class ReviewConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=4000)
    content_json: dict[str, Any]


class ReviewConfigurationCloneIn(BaseModel):
    target_workspace_id: int | None = Field(default=None, gt=0)


class ReviewConfigurationPreviewIn(BaseModel):
    portfolio_workspace_id: int | None = Field(default=None, gt=0)
    configuration_id: int | None = Field(default=None, gt=0)
    content_json: dict[str, Any] | None = None


class ReviewConfigurationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    code: str
    name: str
    description: str
    status: str
    revision: int
    version: int
    content_json: dict[str, Any]
    content_hash: str
    published_at: datetime | None
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime


class ReviewConfigurationPreviewOut(BaseModel):
    portfolio_workspace_id: int | None
    persisted: bool = False
    effective: dict[str, Any]
    source: dict[str, Any]
    resolution_path: list[dict[str, Any]]


class PortfolioReviewOptionsOut(BaseModel):
    review_types: list[dict[str, Any]]
    conclusion_types: list[dict[str, Any]]
    action_types: list[dict[str, Any]]
    agenda_template: list[dict[str, Any]]
    portfolios: list[dict[str, Any]]
    allocation_plans: list[dict[str, Any]]
    users: list[dict[str, Any]]
    effective_configuration: dict[str, Any]
    configuration_source: dict[str, Any]
