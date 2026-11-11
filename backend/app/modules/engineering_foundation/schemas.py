"""Strict command DTOs for the technical-deliverable aggregate."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=8, max_length=3000)


class DeliverableIn(ReasonIn):
    code: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    discipline: str = Field(min_length=1, max_length=80)
    deliverable_type: str = Field(min_length=1, max_length=80)
    design_package_id: int | None = Field(default=None, gt=0)
    description: str = Field(default="", max_length=4000)
    responsible_party: str = Field(min_length=1, max_length=200)
    area: str = Field(default="", max_length=150)
    planned_issue_date: date | None = None
    current_forecast_date: date | None = None
    source_reference: str = Field(default="", max_length=1000)


class RevisionIn(ReasonIn):
    revision_code: str = Field(min_length=1, max_length=80)
    purpose_of_issue: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=4000)
    planned_issue_date: date | None = None
    forecast_issue_date: date | None = None


class DocumentIn(ReasonIn):
    document_id: int = Field(gt=0)
    attachment_id: int = Field(gt=0)


class ReviewActionIn(ReasonIn):
    action: Literal["submit", "start", "request_changes", "accept", "check", "approve", "reject", "close"]


class CommentIn(ReasonIn):
    discipline: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=80)
    severity: Literal["INFO", "MINOR", "MAJOR", "BLOCKING"]
    text: str = Field(min_length=1, max_length=4000)


class CommentActionIn(ReasonIn):
    action: Literal["respond", "close"]
    response: str | None = Field(default=None, min_length=1, max_length=4000)


class ReleaseIn(ReasonIn):
    effective_date: date
    release_reference: str = Field(min_length=1, max_length=1000)


class DesignPackageIn(ReasonIn):
    code: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=4000)


class DesignPackageActionIn(ReasonIn):
    action: Literal["review", "issue", "cancel"]


class InterfaceIn(ReasonIn):
    code: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    interface_type: Literal["DISCIPLINE", "PROCUREMENT", "CONSTRUCTION", "VENDOR", "OWNER"]
    deliverable_id: int | None = Field(default=None, gt=0)
    source_reference: str = Field(default="", max_length=1000)


class InterfaceActionIn(ReasonIn):
    action: Literal["resolve", "close", "cancel"]
    resolution: str | None = Field(default=None, min_length=1, max_length=4000)


class ProfileIn(ReasonIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=180)
    content_json: dict


class ProfileUpdateIn(ReasonIn):
    name: str = Field(min_length=1, max_length=180)
    content_json: dict
