"""Dedicated Progress integration commands reject downstream authority fields."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=8, max_length=3000)


class BundleIn(ReasonIn):
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=300)
    scope_baseline_id: int = Field(gt=0)
    schedule_baseline_id: int = Field(gt=0)
    cost_baseline_id: int = Field(gt=0)
    effective_date: date


class BundleTransitionIn(ReasonIn):
    action: str = Field(pattern="^(review|approve)$")


class BundleSuccessorIn(BundleIn):
    """Every successor declares all source identities again, never partial rebasing."""


class PeriodTransitionIn(ReasonIn):
    action: str = Field(pattern="^(review|close|publish|reopen)$")
    notes: str = Field(default="", max_length=3000)


class EVMSnapshotIn(ReasonIn):
    bundle_id: int = Field(gt=0)
    period_id: int = Field(gt=0)
    as_of: date
    currency: str | None = Field(default=None, min_length=3, max_length=8)
