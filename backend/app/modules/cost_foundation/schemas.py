"""Bounded Cost commands cannot alter Scope, Schedule, contracts or funding."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.modules.scope_foundation.schemas import ActionIn, ProfileIn, ProfileUpdateIn, StrictIn

__all__ = ["ActionIn", "ProfileIn", "ProfileUpdateIn"]
Money = Decimal


class CBSIn(ActionIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    parent_id: int | None = Field(default=None, gt=0)
    sort_order: int = 0
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"


class CostCodeIn(ActionIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    category: str = Field(min_length=1, max_length=80)
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"


class AccountIn(ActionIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    owner_user_id: int = Field(gt=0)
    responsible_role: str = Field(min_length=1, max_length=120)
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"


class MappingIn(ActionIn):
    source_kind: Literal["SCOPE", "PLAN", "PACKAGE", "WBS", "ACTIVITY"]
    source_id: int | None = Field(default=None, gt=0)
    schedule_version_id: int | None = Field(default=None, gt=0)
    source_external_id: str = Field(default="", max_length=160)
    cbs_id: int | None = Field(default=None, gt=0)
    cost_code_id: int | None = Field(default=None, gt=0)
    control_account_id: int | None = Field(default=None, gt=0)
    allocation_basis: str = Field(min_length=1, max_length=100)
    quantity_basis: str = Field(min_length=1, max_length=100)
    quantity: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=8)
    unit: str = Field(default="", max_length=40)
    percentage: Decimal | None = Field(default=None, ge=0, le=100, max_digits=24, decimal_places=8)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=8)
    currency: str | None = Field(default=None, min_length=3, max_length=8)
    effective_revision: str = Field(min_length=1, max_length=120)
    source_reference: str = Field(min_length=1, max_length=1000)
    status: Literal["ACTIVE", "REMOVED"] = "ACTIVE"
    supersedes_id: int | None = Field(default=None, gt=0)


class RateIn(ActionIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    resource_type: Literal["LABOR", "MATERIAL", "EQUIPMENT", "SUBCONTRACT", "OTHER"]
    unit: str = Field(min_length=1, max_length=40)
    amount: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    currency: str = Field(min_length=3, max_length=8)
    effective_from: date
    effective_to: date | None = None
    source_reference: str = Field(min_length=1, max_length=1000)
    source_snapshot: dict = Field(default_factory=dict)
    supersedes_id: int | None = Field(default=None, gt=0)


class ComponentIn(StrictIn):
    rate_id: int = Field(gt=0)
    category: Literal["LABOR", "MATERIAL", "EQUIPMENT", "SUBCONTRACT", "OTHER"]
    quantity_per_unit: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    unit: str = Field(min_length=1, max_length=40)


class FactorIn(StrictIn):
    name: str = Field(min_length=1, max_length=120)
    percentage: Decimal = Field(ge=0, le=1000, max_digits=24, decimal_places=8)
    basis: Literal["DIRECT_COST"] = "DIRECT_COST"


class APUIn(ActionIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    unit: str = Field(min_length=1, max_length=40)
    currency: str = Field(min_length=3, max_length=8)
    effective_from: date
    effective_to: date | None = None
    source_reference: str = Field(min_length=1, max_length=1000)
    components: list[ComponentIn] = Field(min_length=1, max_length=1000)
    factors: list[FactorIn] = Field(default_factory=list, max_length=30)
    supersedes_id: int | None = Field(default=None, gt=0)


class BudgetIn(ActionIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    budget_type: Literal["ORIGINAL", "CURRENT", "APPROVED_CHANGE"] = "ORIGINAL"
    currency: str = Field(min_length=3, max_length=8)
    predecessor_id: int | None = Field(default=None, gt=0)
    source_references: dict = Field(default_factory=dict)


class BudgetLineIn(ActionIn):
    line_code: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    cbs_id: int | None = Field(default=None, gt=0)
    cost_code_id: int | None = Field(default=None, gt=0)
    control_account_id: int | None = Field(default=None, gt=0)
    scope_item_id: int | None = Field(default=None, gt=0)
    plan_item_id: int | None = Field(default=None, gt=0)
    work_package_id: int | None = Field(default=None, gt=0)
    apu_id: int | None = Field(default=None, gt=0)
    quantity: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    unit: str = Field(min_length=1, max_length=40)
    rate: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    currency: str = Field(min_length=3, max_length=8)
    cost_class: Literal["DIRECT", "INDIRECT", "CONTINGENCY", "MANAGEMENT_RESERVE"] = "DIRECT"
    time_phasing_basis: str = Field(default="UNPHASED", max_length=100)
    source_json: dict = Field(default_factory=dict)


class ScopeCandidateIn(ActionIn):
    scope_item_id: int = Field(gt=0)
    apu_id: int = Field(gt=0)
    line_code: str = Field(min_length=1, max_length=120)
    cbs_id: int | None = Field(default=None, gt=0)
    cost_code_id: int | None = Field(default=None, gt=0)
    control_account_id: int | None = Field(default=None, gt=0)
    plan_item_id: int | None = Field(default=None, gt=0)
    work_package_id: int | None = Field(default=None, gt=0)


class BudgetTransitionIn(ActionIn):
    status: Literal["SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED"]


class BaselineIn(ActionIn):
    code: str = Field(min_length=1, max_length=120)
    budget_version_id: int = Field(gt=0)
    previous_baseline_id: int | None = Field(default=None, gt=0)


class SpreadIn(StrictIn):
    date: date
    amount: Decimal = Field(ge=0, max_digits=24, decimal_places=8)


class PhasingIn(ActionIn):
    budget_line_id: int = Field(gt=0)
    method: Literal[
        "LINEAR", "FRONT_LOADED", "BACK_LOADED", "MILESTONE_BASED", "ACTIVITY_BASED", "MANUAL", "CURVE_BASED"
    ]
    start_date: date | None = None
    finish_date: date | None = None
    schedule_version_id: int | None = Field(default=None, gt=0)
    source_external_id: str = Field(default="", max_length=160)
    period_id: int | None = Field(default=None, gt=0)
    manual_spread: list[SpreadIn] = Field(default_factory=list, max_length=10000)
    curve_weights: list[Decimal] = Field(default_factory=list, max_length=10000)
