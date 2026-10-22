"""Bounded Schedule commands; no implicit Scope or CPM authority flags."""

from typing import Literal

from pydantic import Field

from app.modules.scope_foundation.schemas import ActionIn, ProfileIn, ProfileUpdateIn

__all__ = [
    "ActionIn",
    "ProfileIn",
    "ProfileUpdateIn",
    "RegisterIn",
    "VersionIn",
    "MappingIn",
    "BaselineIn",
    "ExportIn",
    "PeriodAssociationIn",
]


class RegisterIn(ActionIn):
    schedule_code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    schedule_type: str = Field(default="CONTROL", min_length=1, max_length=100)
    purpose: str = Field(default="", max_length=3000)
    calendar_basis: str = Field(default="EXPLICIT_SOURCE", min_length=1, max_length=120)
    timezone: str = Field(default="America/Bogota", max_length=80)


class VersionIn(ActionIn):
    snapshot_json: dict
    predecessor_version_id: int | None = Field(default=None, gt=0)
    kind: Literal["INITIAL", "UPDATE", "CORRECTION", "FORECAST", "SCENARIO", "APPROVED_CHANGE"] = "UPDATE"


class MappingIn(ActionIn):
    target_kind: Literal["WBS", "ACTIVITY"]
    target_external_id: str = Field(min_length=1, max_length=160)
    plan_item_ids: list[int] = Field(default_factory=list, max_length=5000)
    scope_item_ids: list[int] = Field(default_factory=list, max_length=5000)
    action: Literal["SET", "REMOVE"] = "SET"


class BaselineIn(ActionIn):
    baseline_type: str = Field(default="CONTROL", min_length=1, max_length=80)
    previous_baseline_id: int | None = Field(default=None, gt=0)


class ExportIn(ActionIn):
    format: Literal["XML", "XER"] = "XML"
    purpose: Literal["CURRENT", "BASELINE", "DRAFT_FOR_P6"] = "CURRENT"
    baseline_id: int | None = Field(default=None, gt=0)


class PeriodAssociationIn(ActionIn):
    period_id: int = Field(gt=0)
