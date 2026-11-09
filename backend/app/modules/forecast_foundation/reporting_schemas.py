"""Explicit query and publication contracts for governed operational reporting."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NarrativeIn(StrictIn):
    section: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=8000)
    fact_references: list[str] = Field(min_length=1, max_length=100)


class ReportPublishIn(StrictIn):
    forecast_version_id: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=4000)
    evidence_reference: str = Field(min_length=3, max_length=1000)
    narratives: list[NarrativeIn] = Field(default_factory=list, max_length=30)


class LookAheadIn(StrictIn):
    forecast_version_id: int = Field(gt=0)
    horizon_days: int | None = Field(default=None, ge=1, le=366)
    group_by: Literal["PARENT_WBS", "CWA", "PACKAGE", "AREA", "ZONE", "SYSTEM", "DISCIPLINE"] | None = None
    top_n: int | None = Field(default=None, ge=1, le=10000)
    critical_only: bool = False
    near_critical_value: Decimal | None = Field(default=None, ge=0)
    near_critical_unit: Literal["HOUR", "DAY"] | None = None
    wbs_external_id: str | None = Field(default=None, max_length=160)
    work_package_id: int | None = Field(default=None, gt=0)
    exclude_milestones: bool | None = None
    reason: str = Field(default="Controlled Look-Ahead generation", min_length=3, max_length=4000)
