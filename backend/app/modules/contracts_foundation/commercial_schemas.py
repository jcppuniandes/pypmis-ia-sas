"""Typed command boundaries for contractual evidence and commercial governance."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identity = Annotated[int, Field(gt=0)]
Code = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Positive = Annotated[Decimal, Field(gt=0, max_digits=24, decimal_places=8)]
Nonnegative = Annotated[Decimal, Field(ge=0, max_digits=24, decimal_places=8)]
Signed = Annotated[Decimal, Field(max_digits=24, decimal_places=8)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReasonIn(Input):
    reason: str = Field(min_length=3, max_length=1000)


class DocumentReferenceIn(Input):
    document_id: Identity
    attachment_id: Identity
    source_hash: Hash | None = None


class TargetReferenceIn(Input):
    target_kind: Literal[
        "SCOPE",
        "PLAN",
        "CWA",
        "CWP",
        "PWP",
        "IWP",
        "CBS",
        "COST_CODE",
        "CONTROL_ACCOUNT",
        "WBS",
        "ACTIVITY",
        "MILESTONE",
    ]
    target_id: Identity | None = None
    schedule_version_id: Identity | None = None
    external_id: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    source_hash: Hash | None = None

    @model_validator(mode="after")
    def typed_id(self):
        scheduled = self.target_kind in {"WBS", "ACTIVITY", "MILESTONE"}
        if scheduled and (self.target_id is not None or not self.schedule_version_id or not self.external_id):
            raise ValueError("CONTRACTS_ACCEPTED_SCHEDULE_AND_EXTERNAL_ID_REQUIRED")
        if not scheduled and (not self.target_id or self.schedule_version_id or self.external_id):
            raise ValueError("CONTRACTS_CANONICAL_TARGET_ID_REQUIRED")
        return self


class SOVLineIn(Input):
    line_number: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=2000)
    quantity: Positive
    unit_rate: Positive
    uom: str = Field(min_length=1, max_length=40)
    mappings: list[TargetReferenceIn] = Field(default_factory=list, max_length=24)
    retention_rule: str | None = Field(default=None, min_length=1, max_length=80)


class SOVIn(ReasonIn):
    contract_id: Identity
    contract_version_id: Identity
    code: Code
    lines: list[SOVLineIn] = Field(min_length=1, max_length=200)


class ChangeIn(ReasonIn):
    contract_id: Identity
    base_version_id: Identity
    change_number: Code
    change_type: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=3, max_length=4000)
    value_delta: Signed = Decimal(0)
    time_delta: int = Field(default=0, ge=-3650, le=3650)
    effective_date: date
    notice_id: Identity | None = None
    schedule_references: list[TargetReferenceIn] = Field(default_factory=list, max_length=24)
    document_reference: DocumentReferenceIn | None = None

    @model_validator(mode="after")
    def impact(self):
        if not (self.value_delta or self.time_delta):
            raise ValueError("CONTRACTS_CHANGE_IMPACT_REQUIRED")
        if any(ref.target_kind not in {"WBS", "ACTIVITY", "MILESTONE"} for ref in self.schedule_references):
            raise ValueError("CONTRACTS_CHANGE_SCHEDULE_REFERENCE_TYPE_INVALID")
        return self


class ChangeActionIn(ReasonIn):
    action: Literal["request", "review", "approve", "reject"]
    document_reference: DocumentReferenceIn | None = None


class ProgressReferenceIn(Input):
    measurement_id: Identity
    version: Identity
    source_hash: Hash


class PaymentApplicationLineIn(Input):
    sov_line_id: Identity
    progress: ProgressReferenceIn
    quantity: Positive


class PaymentApplicationIn(ReasonIn):
    contract_id: Identity
    sov_id: Identity
    application_number: Code
    period_id: Identity
    effective_date: date
    document_reference: DocumentReferenceIn
    lines: list[PaymentApplicationLineIn] = Field(min_length=1, max_length=200)


class ApplicationActionIn(ReasonIn):
    action: Literal["review", "reject"]


class PaymentCertificateLineIn(Input):
    application_line_id: Identity
    quantity: Positive
    retention: Nonnegative | None = None
    advance_recovery: Nonnegative = Decimal(0)
    deductions: Nonnegative = Decimal(0)
    withholdings: Nonnegative = Decimal(0)
    other_adjustments: Nonnegative = Decimal(0)


class PaymentCertificateIn(ReasonIn):
    application_id: Identity
    certificate_number: Code
    effective_date: date
    document_reference: DocumentReferenceIn
    lines: list[PaymentCertificateLineIn] = Field(min_length=1, max_length=200)


class CertificateActionIn(ReasonIn):
    action: Literal["approve", "reject"]


class NoticeIn(ReasonIn):
    contract_id: Identity
    notice_number: Code
    notice_type: str = Field(min_length=1, max_length=80)
    sender: str = Field(min_length=1, max_length=240)
    recipient: str = Field(min_length=1, max_length=240)
    issue_date: date
    received_date: date | None = None
    subject: str = Field(min_length=1, max_length=300)
    event_reference: str | None = Field(default=None, min_length=1, max_length=1000)
    response_due_date: date | None = None
    document_reference: DocumentReferenceIn


class NoticeActionIn(ReasonIn):
    action: Literal["receive", "close"]
    received_date: date | None = None


class ClaimIn(ReasonIn):
    contract_id: Identity
    claim_number: Code
    claim_type: str = Field(min_length=1, max_length=80)
    cause: str = Field(min_length=3, max_length=4000)
    notice_id: Identity | None = None
    claimed_amount: Nonnegative = Decimal(0)
    claimed_time: int = Field(default=0, ge=0, le=3650)
    effective_date: date
    documents: list[DocumentReferenceIn] = Field(min_length=1, max_length=15)

    @model_validator(mode="after")
    def claim_basis(self):
        if not (self.claimed_amount or self.claimed_time):
            raise ValueError("CONTRACTS_CLAIM_IMPACT_REQUIRED")
        return self


class ClaimActionIn(ReasonIn):
    action: Literal["accept", "reject"]


class FinanceReferenceIn(ReasonIn):
    source_system: Code
    invoice_reference: str = Field(min_length=1, max_length=260)
    source_version: Identity
    source_hash: Hash
    amount: Positive
    status_reference: Code
    payment_status: Code | None = None


class MappingIn(ReasonIn):
    source_kind: Literal["CONTRACT_PACKAGE", "CONTRACT"]
    source_id: Identity
    target_kind: Literal["PROCUREMENT_PACKAGE", "CWA", "CWP", "PWP"]
    target_id: Identity
    source_hash: Hash | None = None
    effective_date: date | None = None
    action: Literal["SET", "REMOVE"] = "SET"
