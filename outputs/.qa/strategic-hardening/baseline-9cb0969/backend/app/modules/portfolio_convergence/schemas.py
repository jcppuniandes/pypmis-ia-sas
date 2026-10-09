"""Typed API contracts for Gate 07I Portfolio Scenario Convergence."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IdempotencyIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class ConvergenceCreateIn(IdempotencyIn):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=4000)
    logical_code: str = Field(default="PORTFOLIO-CONVERGENCE", min_length=3, max_length=100)
    required_budget_branch: bool | None = None
    required_resource_branch: bool | None = None

    @model_validator(mode="after")
    def at_least_one_branch(self):
        if self.required_budget_branch is False and self.required_resource_branch is False:
            raise ValueError("At least one source branch is required")
        return self


class ConvergenceUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=180)
    description: str | None = Field(default=None, max_length=4000)


class AlternativeCreateIn(IdempotencyIn):
    alternative_name: str = Field(min_length=3, max_length=180)
    budget_scenario_id: int | None = Field(default=None, gt=0)
    resource_scenario_id: int | None = Field(default=None, gt=0)


class AlternativeCompareIn(BaseModel):
    alternative_ids: list[int] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def unique_alternatives(self):
        if len(set(self.alternative_ids)) != len(self.alternative_ids):
            raise ValueError("alternative_ids must be unique")
        return self


class RefreshApplyIn(IdempotencyIn):
    expected_source_hash: str = Field(min_length=64, max_length=64)


class RecommendationIn(IdempotencyIn):
    recommended_alternative_id: int = Field(gt=0)
    recommendation_reason: str = Field(min_length=10, max_length=6000)
    conditions: list[str] = Field(default_factory=list, max_length=50)
    risks_acknowledged: list[str] = Field(default_factory=list, max_length=50)
    decision_support_summary: str = Field(min_length=10, max_length=10000)


class ConvergedAlternativeOut(BaseModel):
    id: int
    convergence_id: int
    alternative_name: str
    budget_scenario_id: int | None
    budget_scenario_hash: str | None
    resource_scenario_id: int | None
    resource_scenario_hash: str | None
    alignment_status: str
    budget_feasibility: str
    resource_feasibility: str
    feasibility_status: str
    selected_project_set_hash: str
    budget_summary: dict
    resource_summary: dict
    strategic_summary: dict
    risk_summary: dict
    project_matrix: list[dict]
    forced_conflicts: list[dict]
    warnings: list[str]
    blockers: list[str]
    alternative_hash: str
    revision_version: int
    created_by: int
    created_at: datetime
    updated_at: datetime


class PortfolioScenarioConvergenceOut(BaseModel):
    id: int
    tenant_id: int
    portfolio_workspace_id: int
    logical_code: str
    convergence_revision: int
    name: str
    description: str
    status: str
    required_budget_branch: bool
    required_resource_branch: bool
    source_analysis_hash: str
    source_membership_set_hash: str
    source_evaluation_set_hash: str
    budget_planning_hash: str | None
    resource_planning_hash: str | None
    configuration_id: int | None
    configuration_revision: int
    configuration_hash: str
    convergence_source_hash: str
    source_current: bool
    recommended_alternative_id: int | None
    recommendation_reason: str | None
    conditions: list[str]
    risks_acknowledged: list[str]
    decision_support_summary: str | None
    recommendation_hash: str | None
    recommended_by: int | None
    recommended_at: datetime | None
    warnings: list[str]
    blockers: list[str]
    revision_version: int
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    voided_at: datetime | None
    alternatives: list[ConvergedAlternativeOut]
    allowed_actions: list[str]


class ConvergenceComparisonOut(BaseModel):
    convergence_id: int
    alternatives: list[dict]
    feasibility_matrix: list[dict]
    project_matrix: list[dict]
    pairwise_delta: dict
    warnings: list[str]


class ConvergenceRefreshPreviewOut(BaseModel):
    convergence_id: int
    current_source_hash: str
    proposed_source_hash: str
    source_current: bool
    budget_scenarios_added: list[int]
    budget_scenarios_removed: list[int]
    resource_scenarios_added: list[int]
    resource_scenarios_removed: list[int]
    alternatives_to_rebuild: list[int]
    warnings: list[str]
    blockers: list[str]
    persisted: bool = False


class PortfolioRecommendationReadinessOut(BaseModel):
    portfolio_workspace_id: int
    convergence_id: int | None
    convergence_revision: int | None
    status: str
    alternative_count: int
    recommended_alternative_id: int | None
    source_current: bool
    warnings: list[str]
    blockers: list[str]
    recommendation_hash: str | None
    portfolio_recommendation_ready: bool
    can_enter_investment_gate_preparation: bool
    can_enter_fid: bool = False
    allowed_actions: list[str]
    final_output: str


class PortfolioConvergenceOverviewOut(BaseModel):
    portfolio_workspace_id: int
    required_branches: dict
    budget_contract: dict | None
    resource_contract: dict | None
    source_compatibility: dict
    candidate_budget_scenarios: list[dict]
    candidate_resource_scenarios: list[dict]
    convergences: list[PortfolioScenarioConvergenceOut]
    readiness: PortfolioRecommendationReadinessOut
    boundaries: list[str]


class InvestmentGatePreparationContractOut(BaseModel):
    portfolio_workspace_id: int
    convergence_id: int
    convergence_revision: int
    recommended_alternative_id: int
    recommendation_hash: str
    budget_scenario_ref: dict | None
    resource_scenario_ref: dict | None
    budget_planning_hash: str | None
    resource_planning_hash: str | None
    analysis_hash: str
    membership_set_hash: str
    evaluation_set_hash: str
    selected_project_set_reference: list[int]
    selected_project_set_hash: str
    budget_feasibility_summary: dict
    resource_feasibility_summary: dict
    strategic_summary: dict
    risk_summary: dict
    conditions: list[str]
    warnings: list[str]
    blockers: list[str]
    portfolio_recommendation_ready: bool = True
    can_enter_fid: bool = False
    final_output: str


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
    path: list[dict]
    effective: dict
    source: dict
    source_readiness: dict | None
    candidate_budget_scenarios: int
    candidate_resource_scenarios: int
    possible_pair_count: int
    validation_issues: list[str]
    warnings: list[str]
    blockers: list[str]
    publishable: bool
    persisted: bool = False


class AdminConfigurationRecordOut(BaseModel):
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
    published_at: datetime | None
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime
