"""Strict Forecast commands; numeric assumptions are explicit sources, not UI formulas."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=8, max_length=3000)


class AssumptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    kind: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=1000)
    unit: str = Field(min_length=1, max_length=80)
    currency: str | None = Field(default=None, min_length=3, max_length=8)
    source_reference: str = Field(min_length=1, max_length=1000)
    owner_id: int = Field(gt=0)
    effective_date: date
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    status: Literal["DRAFT", "CONFIRMED"] = "DRAFT"
    evidence_ref: str = Field(min_length=1, max_length=1000)
    rationale: str = Field(min_length=1, max_length=3000)


class ComponentIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    method: Literal[
        "BOTTOM_UP",
        "QUANTITY_RATE",
        "ACTIVITY_REMAINING_DURATION",
        "PRODUCTIVITY_BASED",
        "COMMITMENT_BASED",
        "CONTROL_ACCOUNT",
        "TREND_BASED",
        "MANUAL_GOVERNED",
    ]
    assumption_codes: list[str] = Field(default_factory=list, max_length=100)
    scope_item_id: int | None = Field(default=None, gt=0)
    plan_item_id: int | None = Field(default=None, gt=0)
    work_package_id: int | None = Field(default=None, gt=0)
    control_account_id: int | None = Field(default=None, gt=0)
    cbs_id: int | None = Field(default=None, gt=0)
    cost_code_id: int | None = Field(default=None, gt=0)
    schedule_version_id: int | None = Field(default=None, gt=0)
    activity_external_id: str = Field(default="", max_length=160)
    wbs_external_id: str = Field(default="", max_length=160)
    area: str = Field(default="", max_length=150)
    zone: str = Field(default="", max_length=150)
    system: str = Field(default="", max_length=150)
    discipline: str = Field(default="", max_length=150)
    currency: str | None = Field(default=None, min_length=3, max_length=8)
    unit: str = Field(default="", max_length=80)
    inputs: dict[str, Any] = Field(default_factory=dict)


class ForecastIn(ReasonIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    bundle_id: int = Field(gt=0)
    period_id: int = Field(gt=0)
    as_of: date
    schedule_version_id: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=8)
    method: Literal[
        "BOTTOM_UP",
        "QUANTITY_RATE",
        "ACTIVITY_REMAINING_DURATION",
        "PRODUCTIVITY_BASED",
        "COMMITMENT_BASED",
        "CONTROL_ACCOUNT",
        "TREND_BASED",
        "MANUAL_GOVERNED",
    ] = "BOTTOM_UP"
    confidence: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    confidence_rationale: str = Field(min_length=8, max_length=3000)
    data_completeness: str = Field(default="NOT_ASSESSED", min_length=1, max_length=200)
    assumption_maturity: str = Field(default="NOT_ASSESSED", min_length=1, max_length=200)
    evidence_ref: str = Field(min_length=1, max_length=1000)
    assumptions: list[AssumptionIn] = Field(default_factory=list, max_length=500)
    cost_items: list[ComponentIn] = Field(default_factory=list, max_length=1000)
    time_items: list[ComponentIn] = Field(default_factory=list, max_length=1000)
    milestones: list[ComponentIn] = Field(default_factory=list, max_length=1000)
    resource_items: list[ComponentIn] = Field(default_factory=list, max_length=1000)


class ForecastTransitionIn(ReasonIn):
    action: Literal["review", "approve", "reject"]


class ProfileIn(ReasonIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    content_json: dict


class ProfileUpdateIn(ReasonIn):
    name: str = Field(min_length=1, max_length=300)
    content_json: dict
