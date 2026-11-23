"""Bounded Quality commands; no financial, package-release or Field mutations."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Identity = Annotated[int, Field(gt=0)]
Code = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReasonIn(Input):
    reason: str = Field(min_length=8, max_length=3000)


class SourcePinIn(Input):
    source_type: str = Field(pattern=r"^[A-Z_]{2,60}$")
    source_id: Identity
    source_version: Identity
    source_hash: Digest


class DocumentIn(Input):
    document_id: Identity
    attachment_id: Identity
    source_hash: Digest | None = None


class QualityResultPinIn(Input):
    source_entity_type: Literal["INSPECTION", "TEST"]
    source_entity_id: Identity
    source_version: Identity
    source_hash: Digest


class NCRIn(ReasonIn):
    ncr_number: Code
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=3, max_length=5000)
    category: str = Field(min_length=1, max_length=80)
    severity: str = Field(min_length=1, max_length=40)
    responsible_user_id: Identity
    subject_reference: SourcePinIn
    inspection_record_id: Identity | None = None
    test_record_id: Identity | None = None
    requirement_reference: str = Field(min_length=3, max_length=5000)
    detected_at: AwareDatetime
    due_date: date | None = None
    document_reference: DocumentIn

    @model_validator(mode="after")
    def one_result(self):
        if self.inspection_record_id and self.test_record_id:
            raise ValueError("One original Quality result per NCR")
        return self


class NCRActionIn(ReasonIn):
    action: Literal["issue", "review", "disposition", "correct", "verify", "close", "cancel", "reject"]
    disposition_id: Identity | None = None


class DispositionIn(ReasonIn):
    ncr_id: Identity
    disposition_code: Code
    disposition_type: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=3, max_length=5000)
    engineering_decision_reference: SourcePinIn | None = None
    document_reference: DocumentIn


class DispositionActionIn(ReasonIn):
    action: Literal["approve", "reject"]


class CorrectiveActionIn(ReasonIn):
    action_code: Code
    action_kind: Literal["CORRECTIVE", "PREVENTIVE", "IMPROVEMENT"] = "CORRECTIVE"
    ncr_id: Identity | None = None
    description: str = Field(min_length=3, max_length=5000)
    owner_user_id: Identity
    due_date: date
    subject_reference: SourcePinIn
    document_reference: DocumentIn

    @model_validator(mode="after")
    def corrective_requires_ncr(self):
        if self.action_kind == "CORRECTIVE" and self.ncr_id is None:
            raise ValueError("Corrective action requires its NCR")
        return self


class CorrectiveActionActionIn(ReasonIn):
    action: Literal["start", "complete", "verify", "close"]
    completion_field_reference: SourcePinIn | None = None
    verification_reference: QualityResultPinIn | None = None
    document_reference: DocumentIn | None = None


class PunchIn(ReasonIn):
    item_number: Code
    subject_reference: SourcePinIn
    description: str = Field(min_length=3, max_length=5000)
    category: str = Field(min_length=1, max_length=80)
    responsible_user_id: Identity
    due_date: date
    document_reference: DocumentIn


class PunchActionIn(ReasonIn):
    action: Literal["start", "ready", "close"]
    verification_result: Literal["PASS"] | None = None
    document_reference: DocumentIn | None = None


class AcceptanceIn(ReasonIn):
    acceptance_code: Code
    subject_reference: SourcePinIn
    itp_id: Identity
    acceptance_profile_code: str = Field(default="COMPLETE_CONTROLS", min_length=1, max_length=80)
    quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=8)
    uom: str = Field(min_length=1, max_length=40)
    effective_at: AwareDatetime
    document_reference: DocumentIn
    supersedes_id: Identity | None = None
