"""Bounded typed commands; nothing represents simulation output."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.basic_data.schemas import ConfigurationCloneIn, ConfigurationUpdateIn
from app.modules.owner_capability.schemas import ConfigurationPreviewIn

__all__ = [
    "ConfigurationCloneIn",
    "ConfigurationUpdateIn",
    "ConfigurationPreviewIn",
    "SourceCreateIn",
    "SourceUpdateIn",
    "ModelCreateIn",
    "ModelUpdateIn",
    "ActionIn",
]
AnalysisType = Literal["COST_QRA", "SCHEDULE_QRA", "INTEGRATED_COST_SCHEDULE_QRA"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SourceRefIn(StrictModel):
    kind: Literal[
        "FIN_CAPEX",
        "PORTFOLIO_BUDGET",
        "BUSINESS_CASE",
        "CONTROL_ACCOUNTS",
        "SCHEDULE_COST",
        "EXTERNAL_REFERENCE",
        "SCHEDULE_IMPORT",
    ]
    id: int | None = Field(None, gt=0)
    reference: str | None = Field(None, max_length=300)
    version: str | int | None = None
    hash: str | None = Field(None, max_length=128)


class ScopeIn(StrictModel):
    type: Literal[
        "ENTIRE_PROJECT", "SELECTED_WBS", "SELECTED_MILESTONE_PATH", "SELECTED_PHASE", "OTHER_CONFIGURED_SCOPE"
    ] = "ENTIRE_PROJECT"
    refs: list[str] = Field(default_factory=list, max_length=10000)
    reference: str = Field("", max_length=300)


class SourceCreateIn(StrictModel):
    title: str = Field("QRA Source Readiness", min_length=1, max_length=240)
    comments: str = Field("", max_length=10000)


class SourceUpdateIn(SourceCreateIn):
    source_refs: list[SourceRefIn] = Field(default_factory=list, max_length=100)
    basis: dict = Field(default_factory=dict)
    analysis_scope: ScopeIn = Field(default_factory=ScopeIn)
    items: list[dict] = Field(default_factory=list, max_length=10000)
    gaps: list[dict] = Field(default_factory=list, max_length=2000)
    quality: Literal["NOT_AVAILABLE", "UNVERIFIED", "PARTIALLY_VERIFIED", "VERIFIED"] = "NOT_AVAILABLE"
    confidence: Literal["PRELIMINARY", "MODERATE", "HIGH"] = "PRELIMINARY"
    evidence_refs: list[dict] = Field(default_factory=list, max_length=100)


class InputIn(StrictModel):
    source_kind: Literal["COST", "SCHEDULE"]
    source_item_ref: str = Field(min_length=1, max_length=240)
    mode: Literal["UNCERTAIN", "DETERMINISTIC"] = "UNCERTAIN"
    range_type: str | None = Field(None, max_length=80)
    values: dict = Field(default_factory=dict)
    distribution_family: str | None = Field(None, max_length=80)
    parameters: dict = Field(default_factory=dict)
    correlation_group: str | None = Field(None, max_length=120)
    rationale: str = Field("", max_length=10000)
    evidence_refs: list[dict] = Field(default_factory=list, max_length=100)
    range_source: str | None = Field(None, max_length=120)
    quality: Literal["NOT_AVAILABLE", "UNVERIFIED", "PARTIALLY_VERIFIED", "VERIFIED"] = "VERIFIED"
    unit: str = Field("", max_length=80)
    status: Literal["DRAFT", "VALIDATED"] = "VALIDATED"


class ModelCreateIn(StrictModel):
    title: str = Field("QRA Model Definition", min_length=1, max_length=240)
    analysis_type: AnalysisType = "COST_QRA"
    comments: str = Field("", max_length=10000)


class ModelUpdateIn(ModelCreateIn):
    purpose: str = Field("", max_length=10000)
    analysis_scope: ScopeIn = Field(default_factory=ScopeIn)
    cost_source_assessment_id: int | None = Field(None, gt=0)
    schedule_source_assessment_id: int | None = Field(None, gt=0)
    inputs: list[InputIn] = Field(default_factory=list, max_length=20000)
    correlations: dict = Field(
        default_factory=lambda: {"method": "NO_CORRELATION", "pairs": [], "groups": [], "matrix": []}
    )
    valid_from: date | None = None
    valid_until: date | None = None


class ActionIn(StrictModel):
    comments: str = Field("", max_length=10000)
