"""Bounded Progress commands; clients cannot submit computed or upstream authority fields."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.modules.scope_foundation.schemas import ActionIn, StrictIn
from app.modules.scope_foundation.schemas import ProfileIn as ScopeProfileIn
from app.modules.scope_foundation.schemas import ProfileUpdateIn as ScopeProfileUpdateIn

__all__ = ["ActionIn", "ProfileIn", "ProfileUpdateIn"]


class ProfileIn(ScopeProfileIn):
    reason: str = Field(default="Progress Profile authoring", min_length=3, max_length=3000)


class ProfileUpdateIn(ScopeProfileUpdateIn):
    reason: str = Field(default="Progress Profile revision", min_length=3, max_length=3000)


class EvidenceIn(StrictIn):
    kind: Literal[
        "FIELD_REPORT",
        "QUANTITY_SHEET",
        "INSPECTION",
        "SURVEY",
        "PHOTO",
        "BIM_CONFIRMATION",
        "QA_RELEASE",
        "DOCUMENT",
        "MANUAL_CERTIFICATION",
    ]
    reference: str = Field(min_length=1, max_length=1000)
    content_hash: str = Field(default="", max_length=64)


class StepIn(StrictIn):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=300)
    weight: Decimal = Field(gt=0, le=100, max_digits=24, decimal_places=8)


class RuleIn(ActionIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    method: Literal["RULE_OF_CREDIT", "STEP_METHOD", "MILESTONE_BASED"]
    steps: list[StepIn] = Field(min_length=1, max_length=100)
    ordered: bool = True
    scope_natures: list[Literal["INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"]] = Field(
        default_factory=lambda: ["INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"], min_length=1
    )
    package_types: list[str] = Field(
        default_factory=lambda: ["EWP", "PWP", "CWP", "IWP", "TWP", "SUPPORT", "LOGISTICS", "TEMPORARY_WORKS"],
        min_length=1,
        max_length=30,
    )
    measurement_basis: dict = Field(default_factory=dict)


class ComponentIn(StrictIn):
    measurement_id: int = Field(gt=0)
    weight: Decimal = Field(gt=0, max_digits=24, decimal_places=8)


class MeasurementIn(ActionIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    progress_type: Literal["QUANTITY", "PHYSICAL", "WEIGHTED", "MILESTONE"]
    method: Literal[
        "QUANTITY_BASED",
        "WEIGHTED_COMPONENTS",
        "MILESTONE_BASED",
        "STEP_METHOD",
        "RULE_OF_CREDIT",
        "MANUAL_EXPERT_ASSESSMENT",
    ]
    source_reference: str = Field(min_length=1, max_length=1000)
    scope_item_id: int | None = Field(default=None, gt=0)
    plan_item_id: int | None = Field(default=None, gt=0)
    work_package_id: int | None = Field(default=None, gt=0)
    activity_external_id: str = Field(default="", max_length=160)
    schedule_version_id: int | None = Field(default=None, gt=0)
    control_account_id: int | None = Field(default=None, gt=0)
    wbs_external_id: str = Field(default="", max_length=160)
    area: str = Field(default="", max_length=150)
    system: str = Field(default="", max_length=150)
    discipline: str = Field(default="", max_length=150)
    scope_nature: Literal["INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"] = "INSTALL"
    phase: Literal["INSTALL", "REMOVE", "USE", "INTERVENTION", "RESTORATION", "EXECUTE"] = "EXECUTE"
    period_id: int = Field(gt=0)
    measurement_date: date
    as_of: date
    numerator: Decimal = Field(default=Decimal("0"), max_digits=24, decimal_places=8)
    unit: str = Field(min_length=1, max_length=40)
    input_mode: Literal["CUMULATIVE", "PERIOD_DELTA"] = "CUMULATIVE"
    denominator_basis: Literal["AUTO", "SCOPE", "PLAN", "PACKAGE", "APPROVED_RULE"] = "AUTO"
    weight: Decimal = Field(default=Decimal("1"), gt=0, max_digits=24, decimal_places=8)
    weighting_basis: Literal[
        "QUANTITY", "BUDGET", "LABOR_HOURS", "ENGINEERING_HOURS", "CONTRACT_VALUE", "MANUAL_APPROVED_WEIGHT"
    ] = "MANUAL_APPROVED_WEIGHT"
    rule_id: int | None = Field(default=None, gt=0)
    completed_steps: list[str] = Field(default_factory=list, max_length=100)
    components: list[ComponentIn] = Field(default_factory=list, max_length=1000)
    evidence_refs: list[EvidenceIn] = Field(default_factory=list, max_length=100)
    correction_kind: Literal["NONE", "REWORK", "REVERSAL", "QUANTITY_CORRECTION", "REJECTED_WORK", "DEMOLITION"] = (
        "NONE"
    )


class TransitionIn(ActionIn):
    status: Literal["SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED"]


class CertificationIn(ActionIn):
    evidence_reference: str = Field(min_length=1, max_length=1000)
