"""Typed live commands; configured scales intentionally do not reuse confidence labels."""

from datetime import date
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.modules.basic_data.schemas import ConfigurationCloneIn, ConfigurationUpdateIn

__all__ = [
    "ConfigurationCloneIn",
    "ConfigurationUpdateIn",
    "ConfigurationPreviewIn",
    "AssessmentCreateIn",
    "AssessmentUpdateIn",
    "AssessmentActionIn",
    "CapabilityItemIn",
    "GapIn",
    "MitigationIn",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CapabilityItemIn(StrictModel):
    requirement_code: str = Field(min_length=1, max_length=120)
    current_maturity: str | None = Field(default=None, max_length=80)
    evidence_quality: str = Field(default="NOT_AVAILABLE", max_length=80)
    confidence: Literal["PRELIMINARY", "MODERATE", "HIGH"] = "PRELIMINARY"
    capability_source: Literal["INTERNAL", "EXTERNAL_CONTRACTED", "HYBRID"] = "INTERNAL"
    rationale: str = Field(default="", max_length=10000)
    evidence_refs: list[dict] = Field(default_factory=list, max_length=100)
    source_current: bool = True
    source_date: date | None = None
    expires_on: date | None = None
    source_hash: str | None = Field(default=None, max_length=128)
    source_version: str | None = Field(default=None, max_length=120)
    responsible_function: str = Field(default="", max_length=240)
    role_refs: list[dict] = Field(default_factory=list, max_length=100)
    related_risk_ids: list[int] = Field(default_factory=list, max_length=100)
    review_notes: str = Field(default="", max_length=10000)


class GapIn(StrictModel):
    requirement_code: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=10000)
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    blocking: bool = False
    owner: str = Field(default="", max_length=240)
    target_date: date | None = None
    status: Literal["OPEN", "IN_PROGRESS", "CLOSED"] = "OPEN"
    closure_evidence: list[dict] = Field(default_factory=list, max_length=100)


class MitigationIn(StrictModel):
    requirement_code: str = Field(min_length=1, max_length=120)
    approach: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=10000)
    owner: str = Field(default="", max_length=240)
    target_date: date | None = None
    status: Literal["PROPOSED", "ACCEPTED", "IMPLEMENTED", "CLOSED", "REJECTED"] = "PROPOSED"
    closure_evidence: list[dict] = Field(default_factory=list, max_length=100)
    evidence_refs: list[dict] = Field(default_factory=list, max_length=100)


class AssessmentCreateIn(StrictModel):
    title: str = Field(default="Owner Capability Readiness", min_length=1, max_length=240)
    comments: str = Field(default="", max_length=10000)


class AssessmentUpdateIn(AssessmentCreateIn):
    items: list[CapabilityItemIn] = Field(default_factory=list, max_length=2000)
    gaps: list[GapIn] = Field(default_factory=list, max_length=2000)
    mitigations: list[MitigationIn] = Field(default_factory=list, max_length=2000)


class AssessmentActionIn(StrictModel):
    comments: str = Field(default="", max_length=10000)


class ConfigurationPreviewIn(StrictModel):
    configuration_id: int | None = Field(default=None, gt=0)
    project_id: int | None = Field(default=None, gt=0, validation_alias=AliasChoices("project_id", "workspace_id"))
    content_json: dict | None = None
