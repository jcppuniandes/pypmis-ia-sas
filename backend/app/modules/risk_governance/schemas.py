"""Typed Risk Governance policy and read-only contextual contracts."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.enterprise_structure.schemas import ConfigurationVersionOut


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PolicyScope(StrictModel):
    type: Literal["tenant", "workspace"] = "tenant"
    workspace_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def consistent_scope(self):
        if (self.type == "workspace") != (self.workspace_id is not None):
            raise ValueError("workspace scope requires a workspace_id; tenant scope must have none")
        return self


class Applicability(StrictModel):
    project_types: list[str] = Field(default_factory=list, max_length=250)
    governance_models: list[str] = Field(default_factory=list, max_length=250)
    strategic_themes: list[str] = Field(default_factory=list, max_length=250)
    investment_categories: list[str] = Field(default_factory=list, max_length=250)


class Dimension(StrictModel):
    code: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=180)
    active: bool = True


class RiskStatement(StrictModel):
    code: str = Field(min_length=1, max_length=120)
    dimension_code: str = Field(min_length=1, max_length=120)
    statement: str = Field(min_length=1, max_length=4000)
    rationale: str = Field(default="", max_length=4000)
    applicability: Applicability = Field(default_factory=Applicability)


class RiskThreshold(StrictModel):
    code: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=180)
    dimension_code: str = Field(min_length=1, max_length=120)
    type: Literal["QUALITATIVE", "QUANTITATIVE", "RANGE", "BOOLEAN", "CATEGORY", "PERCENTAGE", "CURRENCY", "DURATION"]
    operator: str = Field(min_length=1, max_length=50)
    value: Any = None
    unit: str = Field(default="", max_length=80)
    currency_code: str | None = Field(default=None, min_length=3, max_length=8)
    rationale: str = Field(default="", max_length=4000)
    escalation_rule_code: str | None = Field(default=None, max_length=120)
    applicability: Applicability = Field(default_factory=Applicability)


class EscalationRule(StrictModel):
    code: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=180)
    attention: str = Field(default="", max_length=4000)
    rationale: str = Field(default="", max_length=4000)


class SeparationOfDuties(StrictModel):
    preparer_cannot_publish: bool = True


class RiskGovernancePolicy(StrictModel):
    scope: PolicyScope
    inherit_to_descendants: bool = True
    effective_from: date
    effective_to: date | None = None
    dimensions: list[Dimension] = Field(default_factory=list, max_length=250)
    applicability: Applicability
    capacity_statements: list[RiskStatement] = Field(default_factory=list, max_length=1000)
    appetite_statements: list[RiskStatement] = Field(default_factory=list, max_length=1000)
    thresholds: list[RiskThreshold] = Field(default_factory=list, max_length=1000)
    escalation_rules: list[EscalationRule] = Field(default_factory=list, max_length=250)
    separation_of_duties: SeparationOfDuties = Field(default_factory=SeparationOfDuties)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self


class ConfigurationCloneIn(StrictModel):
    target_workspace_id: int | None = Field(default=None, gt=0)


class ConfigurationUpdateIn(StrictModel):
    name: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=8000)
    content_json: dict[str, Any]


class EffectiveContextIn(StrictModel):
    workspace_id: int | None = Field(default=None, gt=0)
    effective_date: date | None = None
    project_type: str | None = Field(default=None, max_length=120)
    governance_model: str | None = Field(default=None, max_length=120)
    strategic_theme: str | None = Field(default=None, max_length=120)
    investment_category: str | None = Field(default=None, max_length=120)


class ConfigurationPreviewIn(EffectiveContextIn):
    configuration_id: int | None = Field(default=None, gt=0)
    content_json: dict[str, Any] | None = None


class EffectiveContextOut(BaseModel):
    persisted: Literal[False] = False
    status: Literal["AVAILABLE", "NOT_CONFIGURED", "NOT_APPLICABLE"]
    workspace_id: int | None
    effective_date: date
    context: dict[str, Any]
    policy: dict[str, Any] | None = None
    source: dict[str, Any] | None = None
    resolution_path: list[dict[str, Any]] = Field(default_factory=list)
    capacity_statements: list[dict[str, Any]] = Field(default_factory=list)
    appetite_statements: list[dict[str, Any]] = Field(default_factory=list)
    thresholds: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RiskConfigurationOut(ConfigurationVersionOut):
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime
    allowed_actions: list[str] = Field(default_factory=list)


class ThresholdEvaluationIn(EffectiveContextIn):
    threshold_code: str = Field(min_length=1, max_length=120)
    source_value: Any = None
    unit: str | None = Field(default=None, max_length=80)
    currency_code: str | None = Field(default=None, max_length=8)


class ThresholdEvaluationOut(BaseModel):
    persisted: Literal[False] = False
    threshold_code: str
    status: Literal["WITHIN_APPETITE", "AT_THRESHOLD", "OUTSIDE_APPETITE", "NOT_EVALUABLE"]
    source: dict[str, Any] | None = None
    threshold: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    decision_generated: Literal[False] = False
