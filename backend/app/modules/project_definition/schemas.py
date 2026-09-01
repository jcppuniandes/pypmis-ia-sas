"""API contracts for Project Definition / FEL Manager."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StartFELIn(BaseModel):
    stage_code: str = "FEL-1"
    framework_configuration_id: int | None = None
    entry_justification: str | None = None
    source_evidence: list[dict[str, Any]] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=8, max_length=160)


class AssessmentCreateIn(BaseModel):
    as_of_date: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=160)


class ElementResultIn(BaseModel):
    element_key: str
    category_key: str
    applicable: bool = True
    score: float | None = None
    maturity_status: str | None = None
    comment: str = ""
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    blocking: bool = False
    action_required: bool = False


class AssessmentUpdateIn(BaseModel):
    status: Literal["DRAFT", "IN_PROGRESS"] = "IN_PROGRESS"
    element_results: list[ElementResultIn]
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class IdempotencyIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class StageReviewIn(IdempotencyIn):
    note: str = ""


class ActionCreateIn(BaseModel):
    assessment_id: int
    element_key: str
    title: str = Field(min_length=3, max_length=220)
    description: str = ""
    owner_id: int | None = None
    target_date: datetime | None = None
    blocking: bool = True
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=8, max_length=160)


class ActionUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=220)
    description: str | None = None
    owner_id: int | None = None
    target_date: datetime | None = None
    status: Literal["OPEN", "IN_PROGRESS", "RESOLVED", "ACCEPTED_RISK", "CANCELLED"] | None = None
    blocking: bool | None = None
    evidence_refs: list[dict[str, Any]] | None = None


class RefreshApplyIn(IdempotencyIn):
    expected_source_hash: str = Field(min_length=64, max_length=64)


class ProjectFELStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    project_workspace_id: int
    current_stage_code: str
    status: str
    stage_started_at: datetime | None
    target_stage_exit_date: datetime | None
    effective_framework_id: int
    effective_framework_revision: int
    effective_framework_hash: str
    current_assessment_id: int | None
    latest_completed_assessment_id: int | None
    readiness_status: str
    definition_source_hash: str
    revision_version: int
    allowed_actions: list[str] = Field(default_factory=list)


class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    project_workspace_id: int
    assessment_number: str
    assessment_version: int
    framework_config_id: int
    framework_code: str
    framework_type: str
    framework_version: str
    framework_hash: str
    fel_stage_code: str
    assessment_date: datetime
    as_of_date: datetime
    status: str
    raw_score: float | None
    normalized_score: float | None
    maturity_level: str | None
    threshold_status: str
    category_results: list[dict[str, Any]] = Field(default_factory=list)
    element_results: list[dict[str, Any]] = Field(default_factory=list)
    blocking_items: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    actions_summary: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    source_snapshot: dict[str, Any] = Field(default_factory=dict)
    definition_source_hash: str
    assessed_by: int
    completed_by: int | None
    completed_at: datetime | None
    assessment_hash: str | None
    revision_version: int
    allowed_actions: list[str] = Field(default_factory=list)


class DefinitionActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_workspace_id: int
    assessment_id: int
    element_key: str
    title: str
    description: str
    owner_id: int | None
    target_date: datetime | None
    status: str
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    blocking: bool
    audit: list[dict[str, Any]] = Field(default_factory=list)
    revision_version: int


class DefinitionReadinessOut(BaseModel):
    status: Literal["READY", "BLOCKED", "STALE", "NOT_STARTED"]
    tenant_id: int
    project_workspace_id: int
    current_FEL_stage: str | None
    latest_completed_assessment_id: int | None
    framework_code: str | None
    framework_version: str | None
    assessment_hash: str | None
    maturity_level: str | None
    threshold_status: str
    required_maturity: str | None
    required_stage: str | None
    required_maturity_met: bool
    blocking_item_count: int
    open_blocking_action_count: int
    evidence_coverage: float
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    definition_readiness_hash: str
    source_current: bool
    can_supply_investment_gate_evidence: bool


class InvestmentGateEvidenceOut(BaseModel):
    evidence_type: str
    source_module: str = "PROJECT_DEFINITION_FEL"
    evidence_origin: str = "GOVERNED_SOURCE"
    project_workspace_id: int
    FEL_stage_code: str | None
    framework_code: str | None
    framework_type: str | None
    framework_version: str | None
    assessment_id: int | None
    assessment_version: int | None
    assessment_hash: str | None
    assessment_date: datetime | None
    raw_score: float | None
    normalized_score: float | None
    maturity_level: str | None
    threshold_status: str
    minimum_requirement_met: bool
    blocking_items_count: int
    open_blocking_actions: int
    evidence_coverage: float
    readiness_status: str
    definition_readiness_hash: str
    source_current: bool
    can_supply_investment_gate_evidence: bool


class DefinitionOverviewOut(BaseModel):
    projects: list[dict[str, Any]]
    selected_project: dict[str, Any] | None
    fel_status: ProjectFELStatusOut | None
    latest_assessment: AssessmentOut | None
    readiness: DefinitionReadinessOut | None
    actions: list[DefinitionActionOut]
    history: list[AssessmentOut]
    maturity_trend: list[dict[str, Any]]
    framework: dict[str, Any] | None
    boundaries: dict[str, bool]


class ConfigurationPreviewIn(BaseModel):
    project_workspace_id: int | None = None
    project_type: str | None = None
    governance_model: str = "CAPITAL_OWNER"
    current_FEL_stage: str = "FEL-1"
    configuration_id: int | None = None
    content_json: dict[str, Any] | None = None


class ConfigurationPreviewOut(BaseModel):
    effective_framework: dict[str, Any]
    stage_structure: list[dict[str, Any]]
    applicable_assessment_elements: list[dict[str, Any]]
    scoring_method: str
    maturity_thresholds: list[dict[str, Any]]
    required_evidence: list[dict[str, Any]]
    blocking_elements: list[str]
    PYP_INV_SELECT_readiness_preview: dict[str, Any]
    PYP_FFA_readiness_preview: dict[str, Any]
    warnings: list[str]
    blockers: list[str]
    resolution_chain: list[dict[str, Any]]
    resolution_hash: str
    persisted: bool = False


class ConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = ""
    content_json: dict[str, Any]
