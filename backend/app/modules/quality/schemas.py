"""Typed Quality commands, structured checklist responses and measurements."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Identity = Annotated[int, Field(gt=0)]
Code = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=24, decimal_places=8)]
Number = Annotated[Decimal, Field(max_digits=24, decimal_places=8)]
Result = Literal["PASS", "FAIL", "CONDITIONAL", "NOT_APPLICABLE"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReasonIn(Input):
    reason: str = Field(min_length=8, max_length=3000)


class SourcePinIn(Input):
    source_type: str = Field(min_length=2, max_length=80)
    source_id: Identity
    source_version: Identity
    source_hash: Digest


class DocumentPinIn(Input):
    document_id: Identity
    attachment_id: Identity
    source_hash: Digest | None = None


class ReferenceIn(Input):
    target_kind: Literal["SCOPE", "PLAN", "CWA", "CWP", "IWP", "WBS", "ACTIVITY", "MILESTONE", "GEOGRAPHIC_WORKSPACE"]
    target_id: Identity | None = None
    schedule_version_id: Identity | None = None
    external_id: str | None = Field(default=None, min_length=1, max_length=160)
    source_hash: Digest | None = None

    @model_validator(mode="after")
    def identity(self):
        if self.target_kind in {"WBS", "ACTIVITY", "MILESTONE"}:
            if self.target_id is not None or not self.schedule_version_id or not self.external_id:
                raise ValueError("Accepted schedule and external identity required")
        elif not self.target_id or self.schedule_version_id or self.external_id:
            raise ValueError("Canonical target identity required")
        return self


class PlanIn(ReasonIn):
    code: Code
    title: str = Field(min_length=1, max_length=300)
    scope: str = Field(min_length=3, max_length=5000)
    responsible_user_id: Identity
    effective_date: date
    source_references: list[ReferenceIn] = Field(default_factory=list, max_length=50)
    document_references: list[DocumentPinIn] = Field(min_length=1, max_length=40)


class ITPIn(ReasonIn):
    code: Code
    title: str = Field(min_length=1, max_length=300)
    quality_plan_id: Identity
    description: str = Field(default="", max_length=5000)
    discipline: Code = "GENERAL"
    effective_date: date
    source_references: list[ReferenceIn] = Field(default_factory=list, max_length=50)
    engineering_reference: SourcePinIn
    document_references: list[DocumentPinIn] = Field(min_length=1, max_length=40)


class VersionActionIn(ReasonIn):
    action: Literal["submit", "return_to_draft", "approve"]


class ITPItemIn(ReasonIn):
    itp_id: Identity
    itp_item_code: Code
    sequence: int = Field(gt=0, le=100000)
    activity: str = Field(min_length=1, max_length=500)
    control_type: Code
    requirement_reference: str = Field(min_length=3, max_length=3000)
    acceptance_criteria: str = Field(min_length=3, max_length=5000)
    responsible_party: str = Field(min_length=1, max_length=300)
    witness_party: str = Field(default="", max_length=300)
    evidence_required: bool = True
    next_step_rule: str = Field(default="", max_length=500)
    required: bool = True
    inspection_required: bool = True
    test_required: bool = False
    test_type: Code | None = None
    test_uom: str | None = Field(default=None, min_length=1, max_length=40)
    test_lower_limit: Number | None = None
    test_upper_limit: Number | None = None
    checklist_template_code: Code = "GENERAL"

    @model_validator(mode="after")
    def controls(self):
        if not self.inspection_required and not self.test_required:
            raise ValueError("At least one operational inspection or test control is required")
        if self.test_required and not self.test_type:
            raise ValueError("Required test type must be explicit")
        if (
            self.test_lower_limit is not None
            and self.test_upper_limit is not None
            and self.test_lower_limit > self.test_upper_limit
        ):
            raise ValueError("Lower limit exceeds upper limit")
        if any(value is not None for value in (self.test_lower_limit, self.test_upper_limit)) and not self.test_uom:
            raise ValueError("Numerical test criteria require a unit")
        return self


class RequestIn(ReasonIn):
    request_number: Code
    itp_item_id: Identity
    subject_reference: SourcePinIn
    quantity: Quantity | None = None
    uom: str | None = Field(default=None, min_length=1, max_length=40)
    requested_at: AwareDatetime
    requested_for: AwareDatetime
    inspector_user_id: Identity
    document_references: list[DocumentPinIn] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def context(self):
        if self.requested_for < self.requested_at:
            raise ValueError("Requested inspection time cannot precede the request")
        if (self.quantity is None) != (self.uom is None):
            raise ValueError("Quantity and unit must be provided together")
        return self


class InspectionRequestIn(RequestIn):
    inspection_type: Code = "GENERAL"
    reinspection_of_id: Identity | None = None
    corrective_action_id: Identity | None = None


class TestRequestIn(RequestIn):
    test_type: Code
    laboratory_vendor_id: Identity | None = None


class RequestActionIn(ReasonIn):
    action: Literal["submit", "schedule", "start", "cancel"]


class ChecklistResponseIn(Input):
    item_code: Code
    response_code: Result | None = None
    numeric_value: Number | None = None
    text_value: str | None = Field(default=None, min_length=1, max_length=3000)
    boolean_value: bool | None = None
    uom: str | None = Field(default=None, min_length=1, max_length=40)
    comment: str = Field(default="", max_length=3000)
    evidence_references: list[DocumentPinIn] = Field(default_factory=list, max_length=20)


class ResultIn(ReasonIn):
    record_number: Code
    request_id: Identity
    engineering_reference: SourcePinIn
    result: Result
    comments: str = Field(default="", max_length=5000)
    document_references: list[DocumentPinIn] = Field(min_length=1, max_length=40)


class InspectionRecordIn(ResultIn):
    inspected_at: AwareDatetime
    checklist_responses: list[ChecklistResponseIn] = Field(min_length=1, max_length=200)


class MeasurementIn(Input):
    code: Code
    numeric_value: Number | None = None
    qualitative_value: str | None = Field(default=None, min_length=1, max_length=3000)
    uom: str | None = Field(default=None, min_length=1, max_length=40)
    lower_limit: Number | None = None
    upper_limit: Number | None = None
    result: Result

    @model_validator(mode="after")
    def value(self):
        if (self.numeric_value is None) == (self.qualitative_value is None):
            raise ValueError("Exactly one numeric or qualitative result is required")
        if self.numeric_value is not None and not self.uom:
            raise ValueError("Numeric measurement requires a unit")
        if self.lower_limit is not None and self.upper_limit is not None and self.lower_limit > self.upper_limit:
            raise ValueError("Invalid measurement limits")
        return self


class EquipmentReferenceIn(Input):
    source_reference: SourcePinIn
    calibration_status: Literal["VALID"]
    valid_from: AwareDatetime
    valid_to: AwareDatetime
    document_reference: DocumentPinIn


class TestRecordIn(ResultIn):
    tested_at: AwareDatetime
    method: str = Field(min_length=1, max_length=500)
    standard: str = Field(min_length=1, max_length=500)
    laboratory_vendor_id: Identity | None = None
    equipment_reference: EquipmentReferenceIn | None = None
    measurements: list[MeasurementIn] = Field(min_length=1, max_length=200)


class ResultActionIn(ReasonIn):
    action: Literal["submit", "return_to_draft", "close"]


class ControlDecisionIn(ReasonIn):
    itp_item_id: Identity
    subject_reference: SourcePinIn
    inspection_record_id: Identity | None = None
    test_record_id: Identity | None = None
    decision: Literal["RELEASED", "WAIVED"]
    document_references: list[DocumentPinIn] = Field(min_length=1, max_length=40)


class ProfileIn(ReasonIn):
    code: Code
    name: str = Field(min_length=1, max_length=240)
    content_json: dict


class ProfileUpdateIn(ReasonIn):
    name: str = Field(min_length=1, max_length=240)
    content_json: dict
