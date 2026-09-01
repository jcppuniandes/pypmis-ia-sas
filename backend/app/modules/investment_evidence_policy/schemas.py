"""Typed API contracts for Gate 07J-EVID governance policy."""

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
    version: str
    notes: str
    contract_valid: bool
    contract_issues: list[str]


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
    would_gate07j_be_ready: bool
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
