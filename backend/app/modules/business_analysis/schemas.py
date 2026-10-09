"""Typed contracts for Business Analysis transactions and configuration."""

import math
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class BusinessAnalysisState(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    RETURNED = "RETURNED"
    COMPLETED = "COMPLETED"
    SUPERSEDED = "SUPERSEDED"
    VOIDED = "VOIDED"


class BusinessAnalysisRatingIn(BaseModel):
    criterion_code: str = Field(min_length=1, max_length=80)
    rating: float
    weight: float | None = None
    comment: str = Field(default="", max_length=3000)

    @field_validator("criterion_code")
    @classmethod
    def _strip_code(cls, value: str) -> str:
        return value.strip()

    @field_validator("rating", "weight")
    @classmethod
    def _finite_number(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("rating values must be finite")
        return value


class BusinessAnalysisOptionIn(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=220)
    option_type: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=2, max_length=6000)
    scope_concept: str = Field(default="", max_length=6000)
    expected_benefits: str = Field(default="", max_length=6000)
    rough_cost_range: dict | None = None
    rough_timeline: dict | None = None
    major_risks: list[dict] = Field(default_factory=list, max_length=100)
    major_dependencies: list[dict] = Field(default_factory=list, max_length=100)
    feasibility_notes: str = Field(default="", max_length=6000)
    strategic_fit: str = Field(default="", max_length=3000)
    evaluation: list[BusinessAnalysisRatingIn] = Field(default_factory=list, max_length=100)

    @field_validator("id", "name", "option_type", "description")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class BusinessAnalysisPayload(BaseModel):
    analysis_type: str = Field(min_length=2, max_length=80)
    statement: str = Field(min_length=3, max_length=8000)
    background: str = Field(default="", max_length=8000)
    business_context: str = Field(default="", max_length=8000)
    urgency_timing: str = Field(default="", max_length=4000)
    consequences_no_action: str = Field(default="", max_length=8000)
    business_drivers: list[dict] = Field(default_factory=list, max_length=100)
    strategic_alignment: list[dict] = Field(default_factory=list, max_length=50)
    stakeholders: list[dict] = Field(default_factory=list, max_length=200)
    current_state: dict = Field(default_factory=dict)
    desired_outcomes: dict = Field(default_factory=dict)
    expected_value: list[dict] = Field(default_factory=list, max_length=100)
    assumptions: list[dict] = Field(default_factory=list, max_length=100)
    constraints: list[dict] = Field(default_factory=list, max_length=100)
    business_requirements: list[dict] = Field(default_factory=list, max_length=200)
    options: list[BusinessAnalysisOptionIn] = Field(default_factory=list, max_length=30)
    recommended_option_id: str | None = Field(default=None, max_length=80)
    recommendation_rationale: str = Field(default="", max_length=8000)
    key_trade_offs: list[dict] = Field(default_factory=list, max_length=100)
    conditions: list[dict] = Field(default_factory=list, max_length=100)
    unresolved_concerns: list[dict] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _recommended_option_exists(self):
        option_ids = [item.id for item in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("option ids must be unique")
        if self.recommended_option_id and self.recommended_option_id not in option_ids:
            raise ValueError("recommended_option_id must identify an existing option")
        return self


class BusinessAnalysisCreate(BaseModel):
    source_idea_id: int


class BusinessAnalysisReturnIn(BaseModel):
    reason: str = Field(min_length=3, max_length=3000)


class BusinessAnalysisVoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=3000)


class BusinessAnalysisOut(BaseModel):
    id: int
    analysis_number: str
    source_idea_id: int
    source_idea_number: str
    source_idea_title: str
    source_idea_evaluation_id: int
    owning_workspace_id: int
    owning_workspace_name: str
    supersedes_analysis_id: int | None
    status: BusinessAnalysisState
    title: str
    content: dict
    recommended_option_id: str | None
    readiness: dict
    source_idea_hash: str
    configuration_id: int
    configuration_revision: int
    configuration_hash: str
    review: dict
    completion_hash: str
    revision_version: int
    created_by_user_id: int
    reviewer_user_id: int | None
    allowed_actions: list[str]
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    review_started_at: datetime | None
    completed_at: datetime | None


class BusinessAnalysisOptionsOut(BaseModel):
    number_preview: str
    eligible_ideas: list[dict]
    analysis_types: list[dict]
    business_drivers: list[dict]
    strategic_objectives: list[dict]
    option_types: list[dict]
    evaluation_criteria: list[dict]
    evaluation_scale: dict
    stakeholder_categories: list[dict]
    value_dimensions: list[dict]


class BusinessAnalysisReadinessOut(BaseModel):
    business_analysis_id: int
    status: str
    ready: bool
    output: str | None
    blockers: list[str]
    warnings: list[str]
    source_idea_hash: str
    current_source_idea_hash: str
    configuration_hash: str
    readiness_hash: str


class BusinessAnalysisHistoryOut(BaseModel):
    event_type: str
    outcome: str
    actor_user_id: int | None
    metadata: dict
    occurred_at: datetime


class BusinessAnalysisConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=3000)
    content_json: dict


class BusinessAnalysisConfigurationPreviewIn(BaseModel):
    owning_workspace_id: int


class BusinessAnalysisConfigurationPreviewOut(BaseModel):
    owning_workspace_id: int
    path: list[dict]
    effective: dict
    source: dict
    validation: dict
    persisted: bool = False
