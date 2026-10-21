"""Bounded command contracts; unrecognized authority flags are rejected."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class ActionIn(StrictIn):
    reason: str = Field(min_length=3, max_length=3000)


class ItemIn(StrictIn):
    scope_code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=10000)
    parent_scope_item_id: int | None = Field(default=None, gt=0)
    predecessor_id: int | None = Field(default=None, gt=0)
    scope_type: str = Field(default="DELIVERABLE", max_length=100)
    scope_nature: Literal["INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"] = "INSTALL"
    discipline: str = Field(default="", max_length=100)
    area: str = Field(default="", max_length=150)
    zone: str = Field(default="", max_length=150)
    system: str = Field(default="", max_length=150)
    location: str = Field(default="", max_length=260)
    quantity: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    unit: str = Field(min_length=1, max_length=40)
    measurement_method: str = Field(default="EXPLICIT_NO_CONVERSION", max_length=260)
    source_quantity_name: str = Field(default="", max_length=160)
    source_type: Literal["IFC", "EXCEL", "MANUAL", "APPROVED_CHANGE"] = "MANUAL"
    source_reference: str = Field(default="", max_length=500)
    source_revision: str = Field(default="", max_length=160)
    model_object_ids: list[int] = Field(default_factory=list, max_length=5000)
    excel_import_id: int | None = Field(default=None, gt=0)
    excel_row_number: int | None = Field(default=None, gt=0)
    approved_change_id: int | None = Field(default=None, gt=0)
    reason: str = Field(default="Scope definition", min_length=3, max_length=3000)


class RevisionIn(ActionIn):
    revision_code: str = Field(min_length=1, max_length=120)
    item_ids: list[int] | None = Field(default=None, max_length=10000)
    removed_scope_item_ids: list[int] = Field(default_factory=list, max_length=10000)


class ExecutionPathIn(StrictIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    mode: Literal["ORDERED", "PARALLEL", "CONDITIONAL", "AREA", "SYSTEM", "PHASE", "PACKAGE"] = "ORDERED"
    sequence: int = Field(default=0, ge=0)
    area: str = Field(default="", max_length=150)
    zone: str = Field(default="", max_length=150)
    system: str = Field(default="", max_length=150)
    phase: str = Field(default="", max_length=150)
    condition: str = Field(default="", max_length=1500)


class SegmentationIn(StrictIn):
    kind: Literal["AREA", "LEVEL", "ZONE", "SYSTEM", "QUANTITY_RANGE", "WORKFRONT", "PACKAGE", "MODEL_SELECTION"]
    values: list[str] = Field(default_factory=list, max_length=1000)
    quantity: Decimal | None = Field(default=None, gt=0)


class StrategyIn(ActionIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    paths: list[ExecutionPathIn] = Field(default_factory=list, max_length=1000)
    segmentation_rules: list[SegmentationIn] = Field(default_factory=list, max_length=100)
    packaging_strategy: str = Field(default="", max_length=3000)
    workfront_strategy: str = Field(default="", max_length=3000)
    temporary_works_strategy: str = Field(default="", max_length=3000)
    removal_strategy: str = Field(default="", max_length=3000)
    maintenance_strategy: str = Field(default="", max_length=3000)
    milestone_strategy: str = Field(default="", max_length=3000)
    awp_applicability: Literal["NOT_APPLICABLE", "OPTIONAL", "APPLICABLE"] = "OPTIONAL"


class AllocationIn(StrictIn):
    scope_item_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=8)
    unit: str = Field(min_length=1, max_length=40)


class PlanIn(ActionIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    parent_plan_item_id: int | None = Field(default=None, gt=0)
    strategy_id: int | None = Field(default=None, gt=0)
    allocations: list[AllocationIn] = Field(min_length=1, max_length=5000)
    model_object_ids: list[int] = Field(default_factory=list, max_length=5000)


class TransformIn(ActionIn):
    operation: Literal["GROUP", "SPLIT", "RECOMPOSE"]
    source_plan_item_ids: list[int] = Field(min_length=1, max_length=1000)
    expected_versions: dict[str, int]
    outputs: list[PlanIn] = Field(min_length=1, max_length=1000)


class SegmentIn(ActionIn):
    scope_item_ids: list[int] = Field(min_length=1, max_length=1000)
    rule_index: int = Field(default=0, ge=0)
    code_prefix: str = Field(min_length=1, max_length=80)
    assignments: dict[str, str] = Field(default_factory=dict)


class DerivedIn(ActionIn):
    plan_item_ids: list[int] = Field(min_length=1, max_length=1000)
    model_object_ids: list[int] = Field(default_factory=list, max_length=5000)
    split_rule: Literal["LOGICAL"] = "LOGICAL"
    visibility_json: dict[str, bool] = Field(default_factory=dict)
    section_json: dict = Field(default_factory=dict)
    restore_version_id: int | None = Field(default=None, gt=0)


class ProfileIn(StrictIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=260)
    content_json: dict


class ProfileUpdateIn(StrictIn):
    name: str = Field(min_length=1, max_length=260)
    content_json: dict
