"""Typed API contracts for Gate 07B Project Proposal."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProjectProposalState(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    RETURNED = "RETURNED"
    UNDER_EVALUATION = "UNDER_EVALUATION"
    EVALUATED = "EVALUATED"
    READY_FOR_STRATEGIC_GATE_DECISION = "READY_FOR_STRATEGIC_GATE_DECISION"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class ProjectProposalCreate(BaseModel):
    source_idea_id: int


class ProjectProposalUpdate(BaseModel):
    name: str = Field(min_length=3, max_length=220)
    business_need: str = Field(min_length=3, max_length=8000)
    business_justification: str = Field(min_length=3, max_length=8000)
    project_objectives: list[dict] = Field(default_factory=list, max_length=30)
    preliminary_scope: str = Field(min_length=3, max_length=12000)
    out_of_scope: str = Field(default="", max_length=8000)
    expected_benefits: str = Field(min_length=3, max_length=8000)
    benefit_owner_user_id: int | None = None
    rom_cost: Decimal | None = Field(default=None, ge=0)
    currency_code: str = Field(default="COP", min_length=3, max_length=8)
    preliminary_duration_days: int | None = Field(default=None, ge=1, le=36500)
    target_start_date: date | None = None
    target_finish_date: date | None = None
    key_risks: list[dict] = Field(default_factory=list, max_length=100)
    assumptions: list[dict] = Field(default_factory=list, max_length=100)
    constraints: list[dict] = Field(default_factory=list, max_length=100)
    strategic_objective_codes: list[str] = Field(default_factory=list, max_length=30)
    target_portfolio_workspace_id: int | None = None
    sponsor_user_id: int
    proposal_owner_user_id: int
    attachment_refs: list[dict] = Field(default_factory=list, max_length=50)

    @field_validator(
        "name",
        "business_need",
        "business_justification",
        "preliminary_scope",
        "out_of_scope",
        "expected_benefits",
        "currency_code",
    )
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("strategic_objective_codes")
    @classmethod
    def _objectives(cls, values: list[str]) -> list[str]:
        return sorted({value.strip().lower() for value in values if value.strip()})

    @model_validator(mode="after")
    def _dates(self):
        if self.target_start_date and self.target_finish_date and self.target_finish_date < self.target_start_date:
            raise ValueError("target_finish_date cannot be before target_start_date")
        return self


class ProposalReturnIn(BaseModel):
    reason: str = Field(min_length=3, max_length=3000)


class ProposalEvaluationIn(BaseModel):
    ratings: list[dict] = Field(min_length=1, max_length=50)
    comments: str = Field(default="", max_length=4000)


class ProjectProposalEvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    evaluation_version: int
    matrix_configuration_id: int
    matrix_revision: int
    matrix_hash: str
    criteria_snapshot_json: list[dict]
    ratings_json: list[dict]
    total_score: Decimal
    recommendation: str
    comments: str
    evaluator_user_id: int
    created_at: datetime


class ProjectProposalOut(BaseModel):
    id: int
    proposal_number: str
    source_idea_id: int
    source_idea_number: str
    source_idea_title: str
    accepted_idea_evaluation_id: int
    owning_workspace_id: int
    owning_workspace_name: str
    target_portfolio_workspace_id: int | None
    name: str
    business_need: str
    business_justification: str
    project_objectives: list[dict]
    preliminary_scope: str
    out_of_scope: str
    expected_benefits: str
    benefit_owner_user_id: int | None
    rom_cost: Decimal | None
    currency_code: str
    preliminary_duration_days: int | None
    target_start_date: date | None
    target_finish_date: date | None
    key_risks: list[dict]
    assumptions: list[dict]
    constraints: list[dict]
    strategic_objective_codes: list[str]
    sponsor_user_id: int
    sponsor_name: str
    proposal_owner_user_id: int
    proposal_owner_name: str
    origin_idea_score: Decimal | None
    status: ProjectProposalState
    mapping_configuration_id: int
    mapping_revision: int
    mapping_hash: str
    source_values_snapshot: dict
    mapped_values_snapshot: dict
    review: dict
    attachment_refs: list[dict]
    return_reason: str | None
    returned_stage: str | None
    evaluations: list[ProjectProposalEvaluationOut]
    allowed_actions: list[str]
    revision_version: int
    created_at: datetime
    updated_at: datetime


class ProposalPreviewOut(BaseModel):
    proposal_number_preview: str
    source_idea: dict
    accepted_evaluation: dict
    mapping: dict
    mapped_fields: dict
    owning_workspace: dict
    target_portfolio: dict | None
    strategic_objectives: list[dict]
    required_fields: list[str]
    review_checklist: list[dict]
    policy: dict
    evaluation_matrix: dict
    blockers: list[str]
    warnings: list[str]
    persisted: bool = False


class ProposalOptionsOut(BaseModel):
    number_preview: str
    eligible_ideas: list[dict]
    owning_workspaces: list[dict]
    target_portfolios: list[dict]
    strategic_objectives: list[dict]
    users: list[dict]


class GateReadinessOut(BaseModel):
    project_proposal_id: int
    status: str
    can_enter_strategic_gate: bool
    source_idea_id: int
    accepted_idea_evaluation_id: int
    proposal_evaluation_id: int | None
    proposal_score: Decimal | None
    owning_workspace_id: int
    target_portfolio_workspace_id: int | None
    strategic_objectives: list[str]
    sponsor: dict
    proposal_owner: dict
    blockers: list[str]
    warnings: list[str]
    readiness_hash: str


class ProposalHistoryItemOut(BaseModel):
    event_type: str
    outcome: str
    actor_user_id: int | None
    metadata: dict
    occurred_at: datetime


class ProposalConfigurationPreviewIn(BaseModel):
    source_idea_id: int


class ProposalConfigurationPreviewOut(BaseModel):
    source_idea_id: int
    owning_workspace_id: int
    path: list[dict]
    effective: dict
    sources: dict
    proposal_preview: ProposalPreviewOut


class ProposalConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=3000)
    content_json: dict
