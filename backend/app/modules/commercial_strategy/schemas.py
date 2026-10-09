"""API contracts for Gate 07M-COMM."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CommercialStrategyCreateIn(BaseModel):
    project_workspace_id: int = Field(gt=0)
    version_purpose: str = "INITIAL_COMMERCIAL_ASSESSMENT"


class CommercialStrategyUpdateIn(BaseModel):
    content_json: dict[str, Any]
    fel_stage_code: str | None = Field(default=None, max_length=32)
    reviewer_user_id: int | None = Field(default=None, gt=0)


class CommercialStrategyReturnIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class CommercialStrategyVoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class CommercialStrategyRevisionIn(BaseModel):
    version_purpose: str = "MATERIAL_CHANGE_UPDATE"


class CommercialStrategyVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    commercial_strategy_id: int
    version_number: int
    version_purpose: str
    status: str
    fel_stage_code: str | None
    content_json: dict[str, Any]
    readiness_json: dict[str, Any]
    readiness_status: str
    overall_commercial_readiness: str
    readiness_warnings_json: list[str]
    readiness_blockers_json: list[str]
    source_references_json: dict[str, Any]
    source_hashes_json: dict[str, Any]
    source_bundle_hash: str
    source_current: bool
    configuration_id: int
    configuration_revision: int
    configuration_hash: str
    content_hash: str
    commercial_strategy_hash: str
    preparer_user_id: int
    reviewer_user_id: int | None
    return_reason: str | None
    void_reason: str | None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    review_started_at: datetime | None
    returned_at: datetime | None
    completed_at: datetime | None
    completed_by: int | None
    voided_at: datetime | None
    revision_version: int
    can_supply_investment_gate_evidence: bool = False
    allowed_actions: dict[str, bool] = Field(default_factory=dict)


class CommercialStrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_workspace_id: int
    project_workspace_name: str
    strategy_number: str
    status: str
    current_version_id: int | None
    configuration_id: int
    configuration_revision: int
    configuration_hash: str
    configuration_source_workspace_id: int | None
    configuration_resolution_chain_json: list[dict[str, Any]]
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    revision_version: int
    current_version: CommercialStrategyVersionOut | None = None
    allowed_actions: dict[str, bool] = Field(default_factory=dict)
    final_output: str
    next_process: str


class CommercialStrategyReadinessOut(BaseModel):
    commercial_strategy_id: int
    version_id: int
    dimensions: dict[str, str]
    status: str
    overall_commercial_readiness: str
    warnings: list[str]
    blockers: list[str]
    source_current: bool
    configuration_current: bool
    commercial_strategy_hash: str
    source_bundle_hash: str
    configuration_hash: str
    can_supply_investment_gate_evidence: bool
    persisted: bool


class CommercialStrategyHistoryOut(BaseModel):
    version: CommercialStrategyVersionOut
    lifecycle_events: list[dict[str, Any]] = Field(default_factory=list)


class CommercialStrategyRefreshPreviewOut(BaseModel):
    commercial_strategy_id: int
    current_version_id: int
    source_delta: list[dict[str, Any]]
    policy_delta: list[dict[str, Any]]
    readiness_delta: dict[str, Any]
    warnings: list[str]
    blockers: list[str]
    recommended_version_purpose: str
    persisted: bool = False


class CommercialReadinessProviderOut(BaseModel):
    provider_key: str
    source_module: str
    evidence_type: str
    status: str
    project_workspace_id: int
    commercial_strategy_id: int
    strategy_number: str
    version_id: int
    version_number: int
    version_purpose: str
    fel_stage_code: str | None
    procurement_approach: str | None
    contracting_model: str | None
    market_readiness: str
    risk_allocation_readiness: str
    payment_mechanism_readiness: str
    overall_commercial_readiness: str
    commercial_strategy_hash: str
    source_bundle_hash: str
    configuration_hash: str
    as_of_date: datetime
    warnings: list[str]
    blockers: list[str]
    source_current: bool
    can_supply_investment_gate_evidence: bool


class CommercialStrategyOptionsOut(BaseModel):
    version_purposes: list[str]
    readiness_states: list[str]
    queues: list[str]
    provider_key: str
    provider_status: str
    configuration_id: int
    configuration_revision: int
    configuration_hash: str
    procurement_approaches: list[str] = Field(default_factory=list)
    contracting_models: list[str] = Field(default_factory=list)
    package_types: list[str] = Field(default_factory=list)
    risk_allocation_categories: list[str] = Field(default_factory=list)
    payment_mechanisms: list[str] = Field(default_factory=list)
    incentive_mechanisms: list[str] = Field(default_factory=list)
    market_assessment_criteria: list[str] = Field(default_factory=list)
    supply_chain_criteria: list[str] = Field(default_factory=list)
    operational_procurement_excluded: bool = True


class CommercialConfigurationPreviewIn(BaseModel):
    project_workspace_id: int | None = Field(default=None, gt=0)
    configuration_id: int | None = Field(default=None, gt=0)
    content_json: dict[str, Any] | None = None


class CommercialConfigurationPreviewOut(BaseModel):
    effective: dict[str, Any]
    resolution_chain: list[dict[str, Any]]
    validation_issues: list[str]
    warnings: list[str]
    publishable: bool
    persisted: bool = False


class CommercialConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=4000)
    content_json: dict[str, Any]
