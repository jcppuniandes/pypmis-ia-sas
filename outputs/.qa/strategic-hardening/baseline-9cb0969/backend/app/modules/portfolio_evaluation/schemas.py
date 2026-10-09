"""API contracts for Gate 07E."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class CriterionRatingIn(BaseModel):
    criterion_code: str = Field(min_length=1, max_length=80)
    rating: Decimal
    evidence: str = Field(default="", max_length=4000)
    comment: str = Field(default="", max_length=4000)

    @field_validator("criterion_code", "evidence", "comment", mode="before")
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value


class EvaluationStartIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class EvaluationUpdateIn(BaseModel):
    ratings: list[CriterionRatingIn] = Field(default_factory=list)
    comments: str = Field(default="", max_length=8000)


class EvaluationCompleteIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class EvaluationReevaluateIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class EvaluationOut(BaseModel):
    id: int
    tenant_id: int
    portfolio_workspace_id: int
    portfolio_name: str
    project_workspace_id: int
    project_number: str
    project_name: str
    portfolio_membership_id: int
    evaluation_version: int
    status: str
    matrix_configuration_id: int
    matrix_revision: int
    matrix_hash: str
    matrix_snapshot: dict
    source_snapshot: dict
    source_snapshot_hash: str
    planning_entry_hash: str
    ratings: list[dict]
    score_components: list[dict]
    normalized_score: Decimal
    strategic_alignment_score: Decimal
    risk_score: Decimal
    comments: str
    evaluator_user_id: int
    revision_version: int
    started_at: datetime
    completed_at: datetime | None
    allowed_actions: list[str]
    blocking_issues: list[str]


class EvaluationQueueItemOut(BaseModel):
    portfolio_workspace_id: int
    project_workspace_id: int
    project_number: str
    project_name: str
    membership_id: int
    queue: str
    eligible: bool
    blocking_issues: list[str]
    allowed_actions: list[str]
    latest_evaluation: EvaluationOut | None


class PrioritizationItemOut(BaseModel):
    rank: int
    portfolio_workspace_id: int
    project_workspace_id: int
    project_number: str
    project_name: str
    evaluation_id: int
    evaluation_version: int
    normalized_score: Decimal
    strategic_alignment_score: Decimal
    risk_score: Decimal
    proposal_score: Decimal | None
    strategic_objectives: list[dict]
    rom_cost: Decimal | None
    evaluation_status: str
    completed_at: datetime
    planned_finish: date | None


class PrioritizationOut(BaseModel):
    portfolio_workspace_id: int
    generated_at: datetime
    ranking_rules: dict
    matrix_hash: str
    items: list[PrioritizationItemOut]


class PrioritizationPreviewIn(BaseModel):
    project_workspace_id: int = Field(gt=0)
    normalized_score: Decimal = Field(ge=0, le=100)
    strategic_alignment_score: Decimal = Field(default=0, ge=0, le=100)
    risk_score: Decimal = Field(default=0, ge=0, le=100)


class PrioritizationReadinessOut(BaseModel):
    portfolio_workspace_id: int
    status: str
    eligible_project_count: int
    completed_evaluation_count: int
    in_progress_evaluation_count: int
    blocked_project_count: int
    coverage_percent: Decimal
    blocking_issues: list[str]
    readiness_hash: str
    can_enter_portfolio_analysis: bool
    final_output: str


class ConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=3000)
    content_json: dict


class ConfigurationPreviewIn(BaseModel):
    workspace_id: int | None = Field(default=None, gt=0)
    configuration_id: int | None = Field(default=None, gt=0)
    content_json: dict | None = None


class ConfigurationPreviewOut(BaseModel):
    workspace_id: int | None
    path: list[dict]
    effective: dict
    source: dict
    publishable: bool
    validation_issues: list[str]
