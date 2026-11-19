"""Strict contracts and commitments command payloads."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Identity = Annotated[int, Field(gt=0)]
Code = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Money = Annotated[Decimal, Field(ge=0, max_digits=24, decimal_places=8)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=24, decimal_places=8)]
SourceType = Literal["PACKAGE", "AWARD", "PO", "PURCHASE_ORDER", "PO_REVISION", "VENDOR"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReasonIn(Input):
    reason: str = Field(min_length=8, max_length=3000)


class SourceIn(Input):
    source_type: SourceType
    source_id: Identity
    source_version: Identity
    source_hash: Digest
    package_id: Identity | None = None


class DocumentPinIn(Input):
    document_id: Identity
    attachment_id: Identity
    source_hash: Digest | None = None


class ContractPackageIn(ReasonIn):
    package_code: Code
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=5000)
    contract_strategy: str = Field(default="", max_length=4000)
    contract_type: Code
    commercial_model: Code
    responsible_user_id: Identity | None = None
    planned_award_date: date | None = None
    planned_execution_date: date | None = None
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    estimated_value: Money
    procurement_sources: list[SourceIn] = Field(default_factory=list, max_length=40)


class PackageActionIn(ReasonIn):
    action: Literal["plan", "cancel"]


class ContractIn(ReasonIn):
    contract_number: Code
    contract_package_id: Identity
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=5000)
    contract_type: Code | None = None
    commercial_model: Code | None = None
    vendor_id: Identity
    governing_reference: str = Field(min_length=1, max_length=4000)
    original_contract_value: Money
    effective_date: date
    commencement_date: date
    planned_completion_date: date
    terms_reference: str = Field(min_length=1, max_length=4000)
    document_reference: DocumentPinIn
    insurance_reference: DocumentPinIn | None = None
    bond_reference: DocumentPinIn | None = None
    source_instrument: SourceIn | None = None


class ContractActionIn(ReasonIn):
    action: Literal["approve", "execute", "effect"]
    execution_date: date | None = None
    document_reference: DocumentPinIn | None = None


class CommitmentIn(ReasonIn):
    commitment_code: Code
    contract_id: Identity
    contract_version_id: Identity
    committed_amount: PositiveMoney
    effective_date: date
    commercial_basis: str = Field(min_length=1, max_length=4000)
    supersedes_id: Identity | None = None


class ProfileIn(ReasonIn):
    code: Code
    name: str = Field(min_length=1, max_length=240)
    content_json: dict


class ProfileUpdateIn(ReasonIn):
    name: str = Field(min_length=1, max_length=240)
    content_json: dict
