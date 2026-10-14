"""Typed API contracts for Gate 07J-EVID governance policy."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PolicyUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=3000)
    content_json: dict


class EffectivePreviewIn(BaseModel):
    portfolio_workspace_id: int | None = Field(default=None, gt=0)
    gate_profile_code: str = Field(pattern="^(PYP-INV-SELECT|PYP-FFA)$")
    project_workspace_ids: list[int] = Field(default_factory=list, max_length=1000)
    configuration_id: int | None = Field(default=None, gt=0)
    content_json: dict | None = None
    project_type_code: str | None = Field(default=None, max_length=80)
    governance_model: str | None = Field(default=None, max_length=80)


class PolicyConfigurationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    kind: str
    code: str
    name: str
    description: str
    status: str
    revision: int
    version: int
    content_json: dict
    content_hash: str
    published_at: datetime | None = None


class ProviderOut(BaseModel):
    provider_key: str
    evidence_type: str
    source_module: str
    source_contract: str
    supports_portfolio_scope: bool
    supports_project_scope: bool
    supports_project_set_scope: bool
    supports_hash: bool
    supports_current_flag: bool
    supports_readiness: bool
    status: str
    availability: str
    contract_status: str
    last_validation: datetime | None
    version: str
    notes: str
    contract_valid: bool
    contract_issues: list[str]
    compatible_evidence_types: list[str] = Field(default_factory=list)
    analysis_types: list[str] = Field(default_factory=list)


class PolicyPreviewOut(BaseModel):
    policy: dict
    gate_profile_code: str
    portfolio_workspace_id: int | None
    project_contexts: list[dict]
    effective_matrix: list[dict]
    provider_registry_snapshot: list[ProviderOut]
    current_evidence_status: list[dict]
    missing_providers: list[dict]
    available_provider_count: int
    missing_required_provider_count: int
    class_A_count: int
    class_B_count: int
    class_C_count: int
    blocking_missing_sources: list[str]
    warnings: list[str]
    blockers: list[str]
    effective_classifications: dict[str, list[str]] = Field(default_factory=dict)
    required_coverage: dict[str, float | None] = Field(default_factory=dict)
    source_availability: dict[str, str] = Field(default_factory=dict)
    source_readiness: dict[str, list[str]] = Field(default_factory=dict)
    source_current: dict[str, list[bool]] = Field(default_factory=dict)
    decision_criterion_policy: dict = Field(default_factory=dict)
    decision_criteria: list[dict] = Field(default_factory=list)
    criterion_validation_issues: list[str] = Field(default_factory=list)
    decision_criterion_taxonomy: list[str] = Field(default_factory=list)
    controlled_operators: list[str] = Field(default_factory=list)
    evidence_quality_states: list[str] = Field(default_factory=list)
    would_gate07j_be_ready: bool
    would_be_ready_for_investment_gate: bool = False
    recommended_next_development: dict
    can_design_investment_decision_gate: bool
    can_enter_fid: bool = False
    persisted: bool = False
    final_output: str


class PolicyOverviewOut(BaseModel):
    configurations: list[PolicyConfigurationOut]
    providers: list[ProviderOut]
    missing_providers: list[dict]
    required_adr_decisions: list[dict]
    allowed_actions: list[str]
    boundaries: list[str]
    release_contract: dict = Field(default_factory=dict)
