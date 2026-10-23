"""Explicit recognition/FX/projection input contracts, not accounting or legal award."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FinancialInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=8, max_length=2000)


class FXRateIn(FinancialInput):
    code: str = Field(min_length=1, max_length=120)
    from_currency: str = Field(min_length=3, max_length=8)
    to_currency: str = Field(min_length=3, max_length=8)
    rate: Decimal = Field(gt=0, max_digits=24, decimal_places=8)
    effective_from: date
    effective_to: date | None = None
    conversion_basis: str = Field(min_length=3, max_length=1000)
    source_reference: str = Field(min_length=3, max_length=1000)
    supersedes_id: int | None = None


class ActualIn(FinancialInput):
    source_system: str = Field(min_length=1, max_length=120)
    source_reference: str = Field(min_length=1, max_length=260)
    source_type: str = Field(default="CONTROLLED_MANUAL", max_length=80)
    posting_date: date
    recognition_date: date
    period_id: int
    amount: Decimal = Field(gt=0, max_digits=24, decimal_places=8)
    currency: str = Field(min_length=3, max_length=8)
    cbs_id: int | None = None
    cost_code_id: int | None = None
    control_account_id: int | None = None
    evidence_ref: str = Field(min_length=3, max_length=1000)
    description: str = Field(default="", max_length=4000)
    fx_rate_id: int | None = None


class ActualAdjustmentIn(ActualIn):
    amount: Decimal = Field(max_digits=24, decimal_places=8)


class ActualDecisionIn(FinancialInput):
    status: Literal["RECOGNIZED", "REJECTED"] = "RECOGNIZED"


class CommitmentIn(FinancialInput):
    source_system: str = Field(min_length=1, max_length=120)
    source_type: Literal["CONTRACT", "PO", "SUBCONTRACT", "CONTRACT_CHANGE_ORDER"]
    source_reference: str = Field(min_length=1, max_length=260)
    source_revision: str = Field(min_length=1, max_length=120)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_record_id: int | None = None
    supersedes_id: int | None = None
    source_document: str = Field(min_length=3, max_length=1000)
    source_approval_status: str = Field(min_length=1, max_length=40)
    economic_origin: str = Field(min_length=1, max_length=260)
    parent_economic_origin: str | None = Field(default=None, max_length=260)
    inclusion_mode: Literal["INCLUDED", "CALL_OFF", "ADDITIVE", "REFERENCE_ONLY"]
    amount: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    currency: str = Field(min_length=3, max_length=8)
    effective_date: date
    cbs_id: int | None = None
    cost_code_id: int | None = None
    control_account_id: int | None = None
    fx_rate_id: int | None = None


class CommitmentDecisionIn(FinancialInput):
    status: Literal["VERIFIED", "REJECTED"] = "VERIFIED"


class EACReferenceIn(BaseModel):
    """Non-persisted integration contract; no Forecast approval workflow."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    etc_amount: Decimal = Field(ge=0, max_digits=24, decimal_places=8)
    currency: str = Field(min_length=3, max_length=8)
    method: Literal["BOTTOM_UP", "QUANTITY_RATE", "COMMITMENT_BASED", "PRODUCTIVITY_BASED", "STATISTICAL", "MANUAL"]
    acceptance_reference: str = Field(min_length=3, max_length=1000)
    includes_commitments: bool
    as_of: date
