"""Typed API contracts for Gate 07K Investment Decision / FID."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class IdempotencyIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class DecisionCreateIn(IdempotencyIn):
    investment_gate_preparation_id: int = Field(gt=0)
    title: str = Field(min_length=3, max_length=240)
    executive_summary: str = Field(default="", max_length=12000)
    configuration_id: int | None = Field(default=None, gt=0)


class DecisionUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=240)
    executive_summary: str | None = Field(default=None, max_length=12000)
    rationale: str | None = Field(default=None, max_length=16000)
    conditions: list[dict] | None = Field(default=None, max_length=100)
    decision_maker_user_id: int | None = Field(default=None, gt=0)
    committee: dict | None = None


class ChecklistAcknowledgement(BaseModel):
    code: str = Field(min_length=2, max_length=120)
    acknowledged: bool
    note: str = Field(default="", max_length=2000)


class DecisionReadyIn(IdempotencyIn):
    checklist: list[ChecklistAcknowledgement] = Field(default_factory=list, max_length=100)


class DecisionVoteIn(IdempotencyIn):
    vote: str = Field(pattern="^(GO|HOLD|RECYCLE|KILL|ABSTAIN)$")
    rationale: str = Field(default="", max_length=6000)


class DecisionDecideIn(IdempotencyIn):
    outcome: str = Field(pattern="^(GO|HOLD|RECYCLE|KILL)$")
    rationale: str = Field(min_length=3, max_length=16000)
    conditions: list[dict] = Field(default_factory=list, max_length=100)
    hold_reason: str | None = Field(default=None, max_length=6000)
    recycle_target: str | None = Field(default=None, max_length=120)
    authorized_amount: Decimal | None = Field(default=None, ge=0)
    authorized_currency: str | None = Field(default=None, min_length=3, max_length=3)
    authorization_valid_until: datetime | None = None

    @model_validator(mode="after")
    def validate_outcome_fields(self):
        if self.outcome == "HOLD" and not self.hold_reason:
            raise ValueError("hold_reason is required for HOLD")
        if self.outcome == "RECYCLE" and not self.recycle_target:
            raise ValueError("recycle_target is required for RECYCLE")
        return self


class DecisionVoteOut(BaseModel):
    id: int
    voter_user_id: int
    vote: str
    rationale: str
    cast_at: datetime
    revision_version: int


class DecisionReadinessOut(BaseModel):
    investment_decision_id: int
    readiness_status: str
    source_current: bool
    package_frozen: bool
    exact_scope: bool
    checklist_complete: bool
    authority_valid: bool
    quorum_met: bool
    voting_rule_met: bool
    segregation_of_duties_valid: bool
    mandatory_criteria_satisfied: bool = True
    decision_hurdles_satisfied: bool = True
    criterion_blockers: list[str] = Field(default_factory=list)
    blockers: list[str]
    warnings: list[str]
    final_output: str


class InvestmentDecisionOut(BaseModel):
    id: int
    tenant_id: int
    decision_number: str
    investment_gate_preparation_id: int
    portfolio_workspace_id: int
    investment_gate_profile_id: int
    profile_code: str
    decision_round: int
    decision_scope_type: str
    decision_scope_hash: str
    status: str
    outcome: str | None
    title: str
    executive_summary: str
    rationale: str
    conditions: list[dict]
    hold_reason: str | None
    recycle_target: str | None
    source_preparation_hash: str
    source_package_hash: str
    source_profile_hash: str
    source_policy_hash: str | None
    decision_package_snapshot: dict
    success_criteria_snapshot: list[dict] = Field(default_factory=list)
    configuration_id: int
    configuration_revision: int
    configuration_hash: str
    configuration_snapshot: dict
    authority_model: str
    authority: dict
    committee: dict
    quorum: dict
    voting_rule: dict
    checklist: list[dict]
    authorized_amount: Decimal | None
    authorized_currency: str | None
    authorization_valid_until: datetime | None
    decision_maker_user_id: int | None
    submitted_at: datetime | None
    review_started_at: datetime | None
    ready_at: datetime | None
    decided_at: datetime | None
    voided_at: datetime | None
    decided_by: int | None
    is_fid: bool
    full_funds_authorized: bool
    investment_authorized: bool
    can_activate_project: bool = False
    decision_hash: str | None
    revision_version: int
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    votes: list[DecisionVoteOut]
    readiness: DecisionReadinessOut
    allowed_actions: list[str]
    authorization_output: dict


class DecisionHistoryItemOut(BaseModel):
    id: int
    event_type: str
    outcome: str
    metadata: dict
    occurred_at: datetime


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
    effective: dict
    validation_issues: list[str]
    warnings: list[str]
    blockers: list[str]
    publishable: bool
    persisted: bool = False
