"""API contracts for Gate 07M-BC."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreateBusinessCaseIn(BaseModel):
    project_workspace_id: int
    source_project_proposal_id: int | None = None
    owner_user_id: int | None = None
    sponsor_user_id: int | None = None
    idempotency_key: str = Field(min_length=8, max_length=160)


class CreateRevisionIn(BaseModel):
    purpose: str
    idempotency_key: str = Field(min_length=8, max_length=160)


class UpdateRevisionIn(BaseModel):
    title: str | None = None
    executive_summary: str | None = None
    business_need: str | None = None
    strategic_alignment: list[dict[str, Any]] | None = None
    objectives: list[dict[str, Any]] | None = None
    scope: dict[str, Any] | None = None
    alternatives: list[dict[str, Any]] | None = None
    benefits: list[dict[str, Any]] | None = None
    assumptions: list[dict[str, Any]] | None = None
    constraints: list[dict[str, Any]] | None = None
    delivery: dict[str, Any] | None = None
    unresolved_concerns: list[dict[str, Any]] | None = None
    recommendation: dict[str, Any] | None = None
    reviewer_user_id: int | None = None


class IdempotencyIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class CompleteRevisionIn(IdempotencyIn):
    reviewer_user_id: int | None = None


class SnapshotCreateIn(IdempotencyIn):
    business_case_revision_id: int
    snapshot_type: str
    decision_reference_type: str | None = None
    decision_reference_id: int | None = None
    decision_reference_hash: str | None = None


class MaterialChangeReviewIn(IdempotencyIn):
    outcome: str
    rationale: str = Field(min_length=3, max_length=2000)


class BusinessCaseRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_case_id: int
    revision_number: int
    revision_label: str
    purpose: str
    status: str
    as_of_date: datetime
    fel_stage_code: str | None
    title: str
    executive_summary: str
    business_need: str
    strategic_alignment_json: list[dict]
    objectives_json: list[dict]
    scope_json: dict
    alternatives_json: list[dict]
    benefits_json: list[dict]
    assumptions_json: list[dict]
    constraints_json: list[dict]
    delivery_json: dict
    unresolved_concerns_json: list[dict]
    recommendation_json: dict
    source_references_json: dict
    source_hashes_json: dict
    source_snapshot_hash: str
    economic_financial_model_id: int | None
    economic_financial_model_version: int | None
    economic_financial_model_hash: str | None
    financial_model_status: str
    economic_financial_readiness: str | None
    economic_financial_as_of_date: datetime | None
    npv: Decimal | None
    irr: Decimal | None
    payback_period: Decimal | None
    benefit_cost_ratio: Decimal | None
    readiness_status: str
    readiness_warnings_json: list[str]
    readiness_blockers_json: list[str]
    readiness_hash: str
    material_change_status: str
    content_hash: str
    preparer_user_id: int
    reviewer_user_id: int | None
    submitted_at: datetime | None
    completed_at: datetime | None
    completed_by: int | None
    revision_version: int
    created_at: datetime
    updated_at: datetime
    # Gate07M-BC-5C is an additive synthesis contract.  These values are
    # calculated by the Business Case service from the governed source bundle;
    # they deliberately are not ORM columns or duplicate source-owned domains.
    five_case_json: dict[str, Any] = Field(default_factory=dict)
    five_case_readiness_json: dict[str, str] = Field(default_factory=dict)
    source_evidence_matrix_json: list[dict[str, Any]] = Field(default_factory=list)
    gate_context_json: dict[str, Any] = Field(default_factory=dict)
    source_current: bool = True
    five_case_hash: str | None = None
    source_bundle_hash: str | None = None
    business_case_hash: str | None = None
    legacy_layout: bool = False


class BusinessCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_case_number: str
    project_workspace_id: int
    source_project_proposal_id: int | None
    owning_workspace_id: int
    owner_user_id: int
    sponsor_user_id: int | None
    status: str
    current_revision_id: int | None
    material_change_review_json: dict
    configuration_id: int
    configuration_revision: int
    configuration_hash: str
    configuration_source_workspace_id: int | None
    configuration_resolution_chain_json: list[dict]
    revision_version: int
    created_at: datetime
    updated_at: datetime
    current_revision: BusinessCaseRevisionOut | None = None
    final_output: str
    next_process: str


class ReadinessOut(BaseModel):
    business_case_id: int
    revision_id: int
    status: str
    warnings: list[str]
    blockers: list[str]
    source_current: bool
    readiness_hash: str
    final_output: str
    persisted: bool


class RefreshPreviewOut(BaseModel):
    business_case_id: int
    current_revision_id: int
    source_changes: list[dict[str, Any]]
    material_change_status: str
    recommended_purpose: str
    persisted: bool = False
    source_changes_by_case: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    case_readiness_delta: dict[str, dict[str, str]] = Field(default_factory=dict)
    five_case_delta: dict[str, Any] = Field(default_factory=dict)
    new_warnings: list[str] = Field(default_factory=list)
    new_blockers: list[str] = Field(default_factory=list)


class DecisionSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_case_id: int
    business_case_revision_id: int
    snapshot_type: str
    decision_reference_type: str | None
    decision_reference_id: int | None
    decision_reference_hash: str | None
    revision_content_hash: str
    source_snapshot_hash: str
    snapshot_json: dict
    snapshot_hash: str
    created_by: int
    created_at: datetime


class ConfigurationPreviewIn(BaseModel):
    project_workspace_id: int | None = None
    configuration_id: int | None = None
    content_json: dict[str, Any] | None = None


class ConfigurationPreviewOut(BaseModel):
    effective: dict[str, Any]
    resolution_chain: list[dict[str, Any]]
    validation_issues: list[str]
    warnings: list[str]
    publishable: bool
    persisted: bool = False


class ConfigurationUpdateIn(BaseModel):
    name: str
    description: str = ""
    content_json: dict[str, Any]
