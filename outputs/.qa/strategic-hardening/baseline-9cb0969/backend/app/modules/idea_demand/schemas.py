"""Typed API contracts for Gate 07A Idea Lifecycle."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IdeaState(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    SCREENING = "SCREENING"
    RETURNED = "RETURNED"
    OWNER_ASSIGNED = "OWNER_ASSIGNED"
    UNDER_EVALUATION = "UNDER_EVALUATION"
    EVALUATED = "EVALUATED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class IdeaPayload(BaseModel):
    title: str = Field(min_length=3, max_length=220)
    description: str = Field(min_length=3, max_length=8000)
    idea_type: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=120)
    expected_benefit: str = Field(default="", max_length=4000)
    estimated_value: Decimal | None = Field(default=None, ge=0)
    currency_code: str = Field(default="COP", min_length=3, max_length=8)
    owning_workspace_id: int
    target_portfolio_workspace_id: int | None = None
    strategic_objective_codes: list[str] = Field(default_factory=list, max_length=20)
    attachment_refs: list[dict] = Field(default_factory=list, max_length=50)

    @field_validator("title", "description", "idea_type", "category", "expected_benefit", "currency_code")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("strategic_objective_codes")
    @classmethod
    def _objectives(cls, values: list[str]) -> list[str]:
        return sorted({value.strip().lower() for value in values if value.strip()})


class IdeaCreate(IdeaPayload):
    pass


class IdeaUpdate(IdeaPayload):
    pass


class ScreeningIn(BaseModel):
    checklist: dict[str, bool] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=3000)


class RoutingIn(BaseModel):
    target_portfolio_workspace_id: int | None = None
    route_code: str = Field(default="default", min_length=1, max_length=120)
    notes: str = Field(default="", max_length=2000)


class OwnerAssignmentIn(BaseModel):
    owner_user_id: int


class EvaluationIn(BaseModel):
    ratings: list[dict] = Field(min_length=1, max_length=50)
    comments: str = Field(default="", max_length=4000)


class DecisionIn(BaseModel):
    reason: str = Field(min_length=3, max_length=3000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return value.strip()


class IdeaEvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    evaluation_version: int
    matrix_configuration_id: int
    matrix_revision: int
    matrix_snapshot_json: dict
    ratings_json: list[dict]
    total_score: Decimal
    result: str
    comments: str
    evaluator_user_id: int
    created_at: datetime


class IdeaOut(BaseModel):
    id: int
    idea_number: str
    title: str
    description: str
    idea_type: str
    category: str
    expected_benefit: str
    estimated_value: Decimal | None
    currency_code: str
    owning_workspace_id: int
    owning_workspace_name: str
    target_portfolio_workspace_id: int | None
    strategic_objective_codes: list[str]
    requestor_user_id: int
    requestor_name: str
    owner_user_id: int | None
    owner_name: str | None
    state: IdeaState
    screening: dict
    routing: dict
    attachment_refs: list[dict]
    accepted_evaluation_id: int | None
    decision_reason: str | None
    readiness: dict
    evaluations: list[IdeaEvaluationOut]
    allowed_actions: list[str]
    revision_version: int
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    evaluated_at: datetime | None
    decided_at: datetime | None


class IdeaOptionsOut(BaseModel):
    number_preview: str
    owning_workspaces: list[dict]
    target_portfolios: list[dict]
    strategic_objectives: list[dict]
    users: list[dict]
    idea_types: list[dict]
    categories: list[dict]
    screening_checklist: list[dict]
    objective_selection: str
    configuration_source: dict


class ProposalReadinessOut(BaseModel):
    idea_id: int
    idea_number: str
    ready: bool
    status: str
    blocking_issues: list[str]
    mapping_preview: dict
    can_create_project_proposal: bool = False


class IdeaConfigurationPreviewIn(BaseModel):
    owning_workspace_id: int


class IdeaConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=3000)
    content_json: dict


class IdeaConfigurationPreviewOut(BaseModel):
    owning_workspace_id: int
    path: list[dict]
    effective: dict
    sources: dict


class IdeaHistoryItemOut(BaseModel):
    event_type: str
    outcome: str
    actor_user_id: int | None
    metadata: dict
    occurred_at: datetime
