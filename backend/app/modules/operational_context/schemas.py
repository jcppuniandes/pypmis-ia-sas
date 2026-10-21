"""Explicit governed command payloads, never generic status PATCH."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CommandIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ActionIn(CommandIn):
    reason: str = Field(min_length=3, max_length=2000)
    notes: str = Field(default="", max_length=4000)


class BindingIn(ActionIn):
    legacy_project_id: int | None = Field(default=None, gt=0)
    source: Literal["AUTHORIZED_ONBOARDING", "VERIFIED_EXISTING_RELATIONSHIP", "CONTROLLED_RECONCILIATION"] = (
        "AUTHORIZED_ONBOARDING"
    )
    expected_binding_version: int | None = Field(default=None, ge=0)


class PeriodOpenIn(ActionIn):
    period_code: str = Field(min_length=1, max_length=80)
    period_start: date
    period_end: date
    cutoff_at: datetime
    timezone: str = Field(min_length=1, max_length=80)
    schedule_data_date: date | None = None


class ProfileCreateIn(CommandIn):
    code: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=180)
    content_json: dict


class ProfileUpdateIn(CommandIn):
    name: str = Field(min_length=1, max_length=180)
    content_json: dict
