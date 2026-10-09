"""Typed command boundary; configuration uses the canonical AdminConfiguration."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Availability = Literal["NOT_AVAILABLE", "PARTIALLY_AVAILABLE", "AVAILABLE"]
Validation = Literal["NOT_VALIDATED", "UNDER_VALIDATION", "VALIDATED", "REJECTED"]


class ItemUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    availability: Availability = "NOT_AVAILABLE"
    quality: str = Field(default="NOT_VALIDATED", min_length=1, max_length=40)
    confidence: str = Field(default="PRELIMINARY", min_length=1, max_length=40)
    source_type: str = Field(default="REFERENCE", min_length=1, max_length=80)
    source_reference: str | None = Field(default=None, max_length=500)
    source_version: str | None = Field(default=None, max_length=120)
    source_hash: str | None = Field(default=None, max_length=128)
    source_date: date | None = None
    expires_on: date | None = None
    source_current: bool = True
    evidence_refs: list[dict] = Field(default_factory=list, max_length=100)
    limitations: str = Field(default="", max_length=10000)
    assumptions: str = Field(default="", max_length=10000)
    gaps: str = Field(default="", max_length=10000)
    comments: str = Field(default="", max_length=10000)


class ItemCreateIn(ItemUpdateIn):
    requirement_code: str = Field(min_length=1, max_length=120)
    validation_state: Literal["NOT_VALIDATED"] = "NOT_VALIDATED"


class ItemValidateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    validation_state: Literal["UNDER_VALIDATION", "VALIDATED", "REJECTED"]
    comments: str = Field(default="", max_length=10000)


class AssessmentCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="Basic Data Readiness", min_length=1, max_length=240)
    comments: str = Field(default="", max_length=10000)


class AssessmentActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comments: str = Field(default="", max_length=10000)


class ConfigurationUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=10000)
    content_json: dict


class ConfigurationCloneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str | None = Field(default=None, min_length=1, max_length=120)
    target_workspace_id: int | None = Field(default=None, gt=0)


class ConfigurationPreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    configuration_id: int | None = Field(default=None, gt=0)
    project_id: int | None = Field(default=None, gt=0)
    content_json: dict | None = None
