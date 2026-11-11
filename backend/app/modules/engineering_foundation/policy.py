"""Engineering configuration and small, deterministic domain rules."""

import re
from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROFILE_KIND = "engineering_profile"
REVISION_EDITABLE = frozenset({"DRAFT", "CHANGES_REQUESTED"})
REVISION_TERMINAL = frozenset({"APPROVED", "REJECTED"})
REVIEW_ACTIONS = {
    "submit": "review.submit",
    "start": "review.perform",
    "request_changes": "review.perform",
    "accept": "review.perform",
    "check": "review.check",
    "approve": "review.approve",
    "reject": "review.approve",
    "close": "review.close",
}
PROGRESS_METHODS = (
    "DELIVERABLE_MILESTONE",
    "WEIGHTED_DELIVERABLES",
    "RULE_OF_CREDIT",
    "STEP_METHOD",
    "ENGINEERING_HOURS",
)
DEFAULT_PROFILE = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "effective_from": None,
    "effective_to": None,
    "deliverable_types": [
        "DRAWING",
        "CALCULATION",
        "SPECIFICATION",
        "DATASHEET",
        "DESIGN_REPORT",
        "MODEL",
        "BIM_MODEL",
        "MTO_BOM",
        "TECHNICAL_MEMORANDUM",
        "DESIGN_BASIS",
        "PROCEDURE",
        "VENDOR_INTERFACE",
        "OTHER",
    ],
    "disciplines": [
        "CIVIL",
        "STRUCTURAL",
        "ARCHITECTURAL",
        "MECHANICAL",
        "PIPING",
        "ELECTRICAL",
        "INSTRUMENTATION",
        "CONTROLS",
        "PROCESS",
        "GEOTECHNICAL",
        "HYDRAULIC",
        "ROADS",
        "ENVIRONMENTAL",
        "SURVEY",
        "BIM",
        "COMMISSIONING_ENGINEERING",
        "OTHER",
    ],
    "purposes_of_issue": [
        "FOR_INFORMATION",
        "FOR_REVIEW",
        "FOR_APPROVAL",
        "FOR_TENDER",
        "FOR_PROCUREMENT",
        "FOR_CONSTRUCTION",
        "AS_BUILT",
        "OTHER",
    ],
    "revision_code_rule": "ALPHANUMERIC",
    "review_rules": {"require_technical_check": True, "require_document_before_submit": True},
    "ifc_release_rules": {"eligible_purposes": ["FOR_CONSTRUCTION"], "releaser_distinct_from_approver": True},
    "readiness_evidence_rules": {"max_age_days": None},
    "progress_default_method": "DELIVERABLE_MILESTONE",
    "lookahead_days": 28,
    "status_labels": {},
}
_CODE = re.compile(r"[A-Z0-9][A-Z0-9_.-]*")
_STATUS_LABELS = {"DRAFT", "UNDER_REVIEW", "CHANGES_REQUESTED", "APPROVED", "REJECTED", "IFC_RELEASED"}
Code = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[A-Z0-9][A-Z0-9_.-]*$")]


class _PolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProfileScope(_PolicyModel):
    type: Literal["tenant", "workspace"]
    workspace_id: int | None = Field(gt=0)

    @model_validator(mode="after")
    def scope_consistent(self):
        if (self.type == "workspace") != (self.workspace_id is not None):
            raise ValueError("ENGINEERING_PROFILE_SCOPE_INVALID")
        return self


class ReviewRules(_PolicyModel):
    require_technical_check: bool
    require_document_before_submit: bool


class ReleaseRules(_PolicyModel):
    eligible_purposes: list[Code] = Field(min_length=1, max_length=30)
    releaser_distinct_from_approver: bool


class EvidenceRules(_PolicyModel):
    max_age_days: int | None = Field(ge=1, le=3650)


class EngineeringProfile(_PolicyModel):
    scope: ProfileScope
    inherit_to_descendants: bool
    effective_from: str | None = Field(max_length=64)
    effective_to: str | None = Field(max_length=64)
    deliverable_types: list[Code] = Field(min_length=1, max_length=80)
    disciplines: list[Code] = Field(min_length=1, max_length=80)
    purposes_of_issue: list[Code] = Field(min_length=1, max_length=30)
    revision_code_rule: Literal["ALPHANUMERIC", "NUMERIC", "ALPHABETIC"]
    review_rules: ReviewRules
    ifc_release_rules: ReleaseRules
    readiness_evidence_rules: EvidenceRules
    progress_default_method: Literal[
        "DELIVERABLE_MILESTONE", "WEIGHTED_DELIVERABLES", "RULE_OF_CREDIT", "STEP_METHOD", "ENGINEERING_HOURS"
    ]
    lookahead_days: int = Field(ge=1, le=120)
    status_labels: dict[str, Annotated[str, Field(min_length=1, max_length=80)]] = Field(max_length=6)

    @field_validator("deliverable_types", "disciplines", "purposes_of_issue")
    @classmethod
    def unique_codes(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("ENGINEERING_PROFILE_DUPLICATE_CODE")
        return values

    @model_validator(mode="after")
    def cross_rules(self):
        eligible = self.ifc_release_rules.eligible_purposes
        if len(set(eligible)) != len(eligible) or not set(eligible) <= set(self.purposes_of_issue):
            raise ValueError("ENGINEERING_PROFILE_PURPOSE_INVALID")
        if not set(self.status_labels) <= _STATUS_LABELS:
            raise ValueError("ENGINEERING_PROFILE_STATUS_INVALID")
        return self


def normalized_code(value: str) -> str:
    code = value.upper()
    if not _CODE.fullmatch(code):
        raise ValueError("ENGINEERING_CODE_INVALID")
    return code


def revision_code(value: str, rule: str) -> str:
    code = normalized_code(value)
    patterns = {"ALPHANUMERIC": _CODE.pattern, "NUMERIC": "[0-9]+", "ALPHABETIC": "[A-Z]+"}
    if not re.fullmatch(patterns[rule], code):
        raise ValueError("ENGINEERING_REVISION_CODE_RULE")
    return code


def validity_end(effective_date: date, max_age_days: int | None) -> str | None:
    return (effective_date + timedelta(days=max_age_days)).isoformat() if max_age_days is not None else None


def release_status(
    revision_id: int, release, effective_release, as_of: date, *, known_at: datetime | None = None
) -> str:
    if release is None or (known_at is not None and release.released_at > known_at):
        return "NOT_RELEASED"
    if release.effective_date > as_of:
        return "FUTURE_IFC"
    return "CURRENT_IFC" if effective_release and effective_release.revision_id == revision_id else "SUPERSEDED_IFC"
