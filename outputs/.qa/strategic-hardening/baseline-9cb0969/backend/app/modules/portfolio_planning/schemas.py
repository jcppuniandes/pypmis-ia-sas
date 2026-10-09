"""API contracts for Gate 07D Portfolio Planning stage entry."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.project_creation.schemas import ProjectRequestOut


class StrategicPlanningPreviewIn(BaseModel):
    strategic_gate_decision_id: int = Field(gt=0)


class StrategicPlanningCreateIn(StrategicPlanningPreviewIn):
    project_parent_workspace_id: int = Field(gt=0)
    project_template_config_id: int = Field(gt=0)
    project_manager_user_id: int = Field(gt=0)
    project_type: str = Field(min_length=1, max_length=120)
    project_phase: str | None = Field(default=None, max_length=120)
    priority: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    expected_decision_hash: str = Field(min_length=64, max_length=64)
    expected_readiness_hash: str = Field(min_length=64, max_length=64)

    @field_validator("project_type", "project_phase", "priority", "country", "region", mode="before")
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value


class ReadinessOut(BaseModel):
    status: str
    can_enter: bool
    required_source_data: list[str]
    available_source_data: list[str]
    blocking_issues: list[str]
    warnings: list[str]
    project_type: str | None = None
    suggested_definition_framework: str | None = None


class PortfolioMembershipOut(BaseModel):
    id: int
    tenant_id: int
    portfolio_workspace_id: int
    portfolio_name: str
    project_workspace_id: int
    project_name: str
    membership_source: str
    source_strategic_gate_decision_id: int | None
    source_project_proposal_id: int | None
    is_target_portfolio: bool
    status: str
    effective_from: datetime
    effective_to: datetime | None
    revision_version: int


class PortfolioMembershipCreateIn(BaseModel):
    portfolio_workspace_id: int = Field(gt=0)
    membership_source: str = Field(default="MANUAL", pattern="^(MANUAL|RULE_BASED)$")


class StrategicPlanningEntryOut(BaseModel):
    status: str
    can_enter_portfolio_evaluation: bool
    can_enter_project_definition: bool
    decision: dict
    proposal: dict
    source_idea: dict
    target_portfolio: dict | None
    project_creation_request: ProjectRequestOut | None
    project_workspace: dict | None
    portfolio_memberships: list[PortfolioMembershipOut]
    planning_entry_snapshot: dict
    planning_entry_hash: str | None
    portfolio_evaluation_readiness: ReadinessOut
    project_definition_readiness: ReadinessOut
    allowed_actions: list[str]
    blocking_issues: list[str]
    warnings: list[str]


class StrategicPlanningPreviewOut(BaseModel):
    decision: dict
    proposal: dict
    source_idea: dict
    target_portfolio: dict | None
    project_name: str
    project_number_preview: str
    record_code_preview: str | None
    allowed_project_parents: list[dict]
    default_project_parent: dict | None
    strategic_objectives: list[dict]
    suggested_project_type: str | None
    suggested_template: dict | None
    template_options: list[dict]
    project_manager_required: bool
    project_manager_candidate: dict | None
    project_manager_options: list[dict]
    mapped_fields: dict
    portfolio_planning_entry_preview: dict
    portfolio_evaluation_readiness_preview: ReadinessOut
    project_definition_readiness_preview: ReadinessOut
    creation_policy: dict
    source_decision_hash: str
    source_readiness_hash: str
    configuration: dict
    blocking_issues: list[str]
    warnings: list[str]
    persisted: bool = False


class PortfolioProjectRegisterOut(BaseModel):
    project_workspace_id: int
    project_number: str
    project_name: str
    workspace_status: str
    planning_stage: str
    membership: PortfolioMembershipOut
    strategic_gate_decision_id: int | None
    decision_number: str | None
    project_proposal_id: int | None
    proposal_number: str | None
    source_idea_id: int | None
    proposal_score: Decimal | None
    strategic_objectives: list[dict]
    rom_cost: str | None
    target_start: date | None
    target_finish: date | None
    expected_benefits: str
    risk_summary: list[dict]
    sponsor_user_id: int | None
    project_manager_user_id: int | None
    portfolio_evaluation_readiness: ReadinessOut
    project_definition_readiness: ReadinessOut


class PortfolioPlanningConfigurationUpdateIn(BaseModel):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(default="", max_length=3000)
    content_json: dict


class PortfolioPlanningConfigurationPreviewIn(BaseModel):
    workspace_id: int = Field(gt=0)


class PortfolioPlanningConfigurationPreviewOut(BaseModel):
    workspace_id: int
    path: list[dict]
    effective: dict
    source: dict


class ProjectDates(BaseModel):
    start: date | None = None
    finish: date | None = None

    @model_validator(mode="after")
    def _ordered(self):
        if self.start and self.finish and self.finish < self.start:
            raise ValueError("finish must not be earlier than start")
        return self
