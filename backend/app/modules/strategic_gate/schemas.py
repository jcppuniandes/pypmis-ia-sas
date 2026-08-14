"""Typed API contracts for Gate 07C Strategic Gate Decision."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class StrategicGateState(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    DECIDED = "DECIDED"
    VOIDED = "VOIDED"


class StrategicGateOutcome(StrEnum):
    APPROVE = "APPROVE"
    RETURN = "RETURN"
    REJECT = "REJECT"
    DEFER = "DEFER"


class StrategicGateCreate(BaseModel):
    project_proposal_id: int


class StrategicGateUpdate(BaseModel):
    decision_reason: str = Field(default="", max_length=8000)
    decision_comments: str = Field(default="", max_length=8000)
    decision_maker_user_id: int | None = None
    conditions: list[dict] = Field(default_factory=list, max_length=100)
    evidence_refs: list[dict] = Field(default_factory=list, max_length=100)
    committee: dict | None = None

    @field_validator("decision_reason", "decision_comments")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class StrategicGateReturnIn(BaseModel):
    reason: str = Field(min_length=3, max_length=3000)

    @field_validator("reason")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class StrategicGateDecideIn(BaseModel):
    outcome: StrategicGateOutcome
    reason: str = Field(min_length=3, max_length=8000)
    conditions: list[dict] = Field(default_factory=list, max_length=100)
    comments: str = Field(default="", max_length=8000)
    deferred_until: date | None = None
    committee: dict | None = None
    checklist: list[dict] | None = Field(default=None, max_length=100)

    @field_validator("reason", "comments")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _defer_date(self):
        if self.outcome != StrategicGateOutcome.DEFER and self.deferred_until is not None:
            raise ValueError("deferred_until is only valid for DEFER")
        return self


class StrategicGateDecisionOut(BaseModel):
    id: int
    decision_number: str
    context_type: str
    context_id: int
    project_proposal_id: int
    project_proposal_number: str
    project_proposal_name: str
    gate_type: str
    gate_round: int
    state: StrategicGateState
    outcome: StrategicGateOutcome | None
    proposal_status_at_entry: str
    proposal_readiness_status: str
    proposal_readiness_hash: str
    proposal_readiness_snapshot: dict
    proposal_snapshot: dict
    source_idea_snapshot: dict
    accepted_idea_evaluation_snapshot: dict
    proposal_evaluation_snapshot: dict
    source_idea_id: int
    accepted_idea_evaluation_id: int
    proposal_evaluation_id: int
    owning_workspace_id: int
    owning_workspace_name: str
    target_portfolio_workspace_id: int | None
    target_portfolio_name: str | None
    strategic_objectives_snapshot: list[dict]
    proposal_score: Decimal | None
    proposal_evaluation_revision: int
    configuration_id: int
    configuration_revision: int
    configuration_hash: str
    configuration_snapshot: dict
    decision_criteria_snapshot: list[dict]
    decision_checklist_snapshot: list[dict]
    conditions: list[dict]
    evidence_refs: list[dict]
    decision_reason: str
    decision_comments: str
    decision_maker_user_id: int | None
    decision_maker_name: str | None
    committee_snapshot: dict | None
    decision_hash: str
    prepared_by_user_id: int
    prepared_by_name: str
    prepared_at: datetime
    submitted_at: datetime | None
    review_started_at: datetime | None
    decided_at: datetime | None
    deferred_until: date | None
    voided_at: datetime | None
    allowed_actions: list[str]
    revision_version: int
    created_at: datetime
    updated_at: datetime


class StrategicGatePreviewOut(BaseModel):
    decision_number_preview: str
    project_proposal: dict
    source_idea: dict
    accepted_idea_evaluation: dict
    proposal_evaluation: dict
    readiness: dict
    owning_workspace: dict
    target_portfolio: dict | None
    strategic_objectives: list[dict]
    gate_type: str
    configuration: dict
    decision_checklist: list[dict]
    decision_criteria: list[dict]
    authority: dict
    committee_policy: dict
    blockers: list[str]
    warnings: list[str]
    persisted: bool = False


class StrategicGateOptionsOut(BaseModel):
    decision_number_preview: str
    eligible_proposals: list[dict]
    users: list[dict]
    gate_types: list[str]


class PortfolioIntakeReadinessOut(BaseModel):
    status: str
    can_create_portfolio_candidate: bool = False
    strategic_gate_decision_id: int
    decision_number: str
    outcome: str | None
    project_proposal_id: int
    project_proposal_number: str
    source_idea_id: int
    accepted_idea_evaluation_id: int
    proposal_evaluation_id: int
    owning_workspace_id: int
    target_portfolio_workspace_id: int | None
    strategic_objectives: list[dict]
    proposal_score: Decimal | None
    conditions: list[dict]
    decision_hash: str
    readiness_hash: str
    blockers: list[str]
    warnings: list[str]


class StrategicGateHistoryItemOut(BaseModel):
    event_type: str
    outcome: str
    actor_user_id: int | None
    metadata: dict
    occurred_at: datetime


class StrategicGateConfigurationPreviewIn(BaseModel):
    project_proposal_id: int


class StrategicGateConfigurationPreviewOut(BaseModel):
    project_proposal_id: int
    owning_workspace_id: int
    path: list[dict]
    effective: dict
    sources: dict
    decision_preview: StrategicGatePreviewOut


class StrategicGateConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=3000)
    content_json: dict
