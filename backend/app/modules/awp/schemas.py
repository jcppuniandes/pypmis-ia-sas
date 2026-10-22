"""AWP commands never accept CPM dates, progress or schedule mutation fields."""

from typing import Literal

from pydantic import Field

from app.modules.scope_foundation.schemas import ActionIn, ProfileIn, ProfileUpdateIn

__all__ = [
    "ActionIn",
    "ProfileIn",
    "ProfileUpdateIn",
    "CWAIn",
    "PackageIn",
    "PackageTransitionIn",
    "MappingIn",
    "DependencyIn",
    "ConstraintIn",
    "ConstraintTransitionIn",
    "ConstraintMappingIn",
    "AssessmentIn",
]


class CWAIn(ActionIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=10000)
    area: str = Field(default="", max_length=150)
    zone: str = Field(default="", max_length=150)
    location: str = Field(default="", max_length=260)
    parent_cwa_id: int | None = Field(default=None, gt=0)
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"


class PackageIn(ActionIn):
    package_code: str = Field(min_length=1, max_length=120)
    package_type: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=10000)
    cwa_id: int | None = Field(default=None, gt=0)
    owner_user_id: int | None = Field(default=None, gt=0)
    responsible_role: str = Field(default="Workface Planner", max_length=120)


class PackageTransitionIn(ActionIn):
    status: Literal["DRAFT", "PLANNED", "UNDER_REVIEW", "READY", "IN_PROGRESS", "COMPLETED", "CLOSED", "SUPERSEDED"]


class MappingIn(ActionIn):
    target_kind: Literal["SCOPE", "PLAN", "ACTIVITY"]
    target_id: int | None = Field(default=None, gt=0)
    schedule_version_id: int | None = Field(default=None, gt=0)
    activity_external_id: str | None = Field(default=None, min_length=1, max_length=160)
    phase: Literal["EXECUTE", "INSTALL", "USE", "REMOVE"] = "EXECUTE"
    action: Literal["SET", "REMOVE"] = "SET"


class DependencyIn(ActionIn):
    predecessor_package_id: int = Field(gt=0)
    successor_package_id: int = Field(gt=0)
    dependency_type: str = Field(default="DELIVERABLE", min_length=1, max_length=80)
    blocking: bool = True
    evidence_reference: str = Field(default="", max_length=1000)
    status: Literal["ACTIVE", "CLEARED", "CANCELLED"] = "ACTIVE"


class ConstraintIn(ActionIn):
    constraint_type: str = Field(min_length=1, max_length=80)
    code: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=10000)
    blocking: bool = True
    owner_user_id: int | None = Field(default=None, gt=0)
    due_date: str | None = Field(default=None, max_length=80)
    source_domain: str = Field(default="AWP", min_length=1, max_length=120)
    source_reference: str = Field(default="", max_length=1000)
    evidence_reference: str = Field(default="", max_length=1000)


class ConstraintTransitionIn(ActionIn):
    status: Literal["IN_PROGRESS", "CLEARED", "WAIVED", "CANCELLED"]
    evidence_reference: str = Field(default="", max_length=1000)
    waiver_reference: str = Field(default="", max_length=1000)


class ConstraintMappingIn(ActionIn):
    target_kind: Literal["PACKAGE", "PLAN", "SCOPE", "ACTIVITY", "CWA"]
    target_id: int | None = Field(default=None, gt=0)
    schedule_version_id: int | None = Field(default=None, gt=0)
    activity_external_id: str | None = Field(default=None, min_length=1, max_length=160)
    action: Literal["SET", "REMOVE"] = "SET"


class AssessmentIn(ActionIn):
    as_of: str = Field(min_length=10, max_length=80)
    evidence_json: dict[str, str] = Field(default_factory=dict, max_length=100)
