"""Typed API contracts for Gate 07L Post-FID Project Governance."""

from datetime import datetime

from pydantic import BaseModel, Field


class IdempotencyIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class EligibilityOut(BaseModel):
    id: int | None = None
    investment_decision_id: int
    project_workspace_id: int
    project_number: str
    project_name: str
    project_type: str
    governance_model: str
    project_state: str
    workspace_status: str
    initialization_state: str
    fid_current: bool
    eligibility_round: int
    snapshot_eligibility_status: str
    eligibility_status: str
    final_output: str
    warnings: list[str]
    blockers: list[str]
    post_fid_conditions: list[dict]
    open_activation_blockers: int
    open_commitment_conditions_count: int
    can_initialize: bool
    can_activate: bool
    next_allowed_process: str
    allowed_actions: list[str]
    fid_decision_hash: str
    decision_package_hash: str
    condition_snapshot_hash: str
    eligibility_hash: str
    source_current: bool
    stale: bool
    persisted: bool
    evaluated_at: datetime | None = None
    evaluated_by: int | None = None
    revision_version: int


class PostFIDDecisionOut(BaseModel):
    investment_decision_id: int
    decision_number: str
    title: str
    gate_profile: str
    status: str
    outcome: str | None
    is_fid: bool
    post_fid_handoff: str | None
    final_output: str
    project_count: int
    projects: list[EligibilityOut]
    next: str


class RefreshDeltaOut(BaseModel):
    project_workspace_id: int
    old_project_state: str | None
    new_project_state: str
    condition_changes: bool
    fid_validity_changes: bool
    scope_changes: bool
    old_eligibility: str | None
    new_eligibility: str
    old_source_hash: str | None
    new_source_hash: str


class RefreshPreviewOut(BaseModel):
    investment_decision_id: int
    deltas: list[RefreshDeltaOut]
    projects: list[EligibilityOut]
    persisted: bool = False


class HandoffOut(BaseModel):
    project_workspace_id: int
    investment_decision_id: int
    fid_decision_hash: str
    eligibility_id: int
    eligibility_hash: str
    eligibility_status: str
    post_fid_conditions: list[dict]
    can_initialize: bool
    can_activate: bool
    delegated_service: str
    delegated_endpoint: str
    delegated_revision_version: int
    idempotency_required: bool = True


class HistoryItemOut(BaseModel):
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
    investment_decision_id: int | None = Field(default=None, gt=0)
    project_workspace_ids: list[int] = Field(default_factory=list, max_length=200)
    configuration_id: int | None = Field(default=None, gt=0)
    content_json: dict | None = None


class ConfigurationPreviewOut(BaseModel):
    investment_decision_id: int | None
    effective: dict
    validation_issues: list[str]
    warnings: list[str]
    blockers: list[str]
    project_eligibility: list[EligibilityOut]
    publishable: bool
    persisted: bool = False
