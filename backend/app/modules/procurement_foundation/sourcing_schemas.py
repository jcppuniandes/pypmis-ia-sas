"""Typed command payloads for canonical Procurement sourcing."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.engineering_foundation.schemas import ReasonIn

Identity = Annotated[int, Field(gt=0)]
Code = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")]
Currency = Annotated[str, Field(pattern=r"^[A-Za-z]{3}$")]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6)]
Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6)]
UOM = Annotated[str, Field(min_length=1, max_length=24, pattern=r"^[A-Za-z0-9%._/-]+$")]
Priority = Literal["LOW", "NORMAL", "HIGH", "CRITICAL"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReferenceIn(Input):
    target_kind: str = Field(min_length=1, max_length=80)
    target_id: Identity | None = None
    schedule_version_id: Identity | None = None
    external_id: str | None = Field(default=None, min_length=1, max_length=200)
    source_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class DocumentReferenceIn(Input):
    document_id: Identity
    attachment_id: Identity


class VendorIn(ReasonIn):
    vendor_code: Code
    legal_name: str = Field(min_length=1, max_length=240)
    display_name: str = Field(min_length=1, max_length=200)
    business_identifier: str = Field(min_length=1, max_length=120)
    country: str = Field(pattern=r"^[A-Za-z]{2}$")
    contact_reference: str = Field(default="", max_length=400)
    qualification_reference: str = Field(default="", max_length=400)


class PackageIn(ReasonIn):
    package_code: Code
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=4000)
    procurement_type: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=80)
    discipline: str = Field(default="", max_length=80)
    responsible_user_id: Identity | None = None
    procurement_manager_id: Identity | None = None
    strategy: str = Field(default="", max_length=4000)
    sourcing_method: str = Field(min_length=1, max_length=80)
    long_lead_flag: bool = False
    priority: Priority = "NORMAL"
    required_on_site_date: date
    planned_rfq_date: date | None = None
    planned_award_date: date | None = None
    planned_po_date: date | None = None
    forecast_delivery_date: date | None = None


class RequirementIn(ReasonIn):
    requirement_code: Code
    package_id: Identity
    description: str = Field(min_length=1, max_length=4000)
    item_type: str = Field(min_length=1, max_length=80)
    required_quantity: Quantity
    uom: UOM
    required_on_site_date: date
    priority: Priority = "NORMAL"
    source_reference: ReferenceIn | None = None


class PackageItemIn(ReasonIn):
    requirement_id: Identity
    quantity: Quantity
    uom: UOM


class RequisitionLineIn(Input):
    line_number: int = Field(gt=0, le=1000000)
    requirement_id: Identity
    description: str = Field(min_length=1, max_length=4000)
    quantity: Quantity
    uom: UOM
    required_date: date
    technical_specification_reference: str = Field(default="", max_length=400)
    engineering_revision_reference: ReferenceIn | None = None
    destination: str = Field(default="", max_length=240)
    notes: str = Field(default="", max_length=4000)


class RequisitionIn(ReasonIn):
    requisition_number: Code
    package_id: Identity
    requested_by: Identity | None = None
    issue_date: date
    required_date: date
    currency: Currency
    estimated_value: Money | None = None
    technical_reference: ReferenceIn | None = None
    document_reference: DocumentReferenceIn | None = None
    notes: str = Field(default="", max_length=4000)
    lines: list[RequisitionLineIn] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.required_date < self.issue_date or any(line.required_date < self.issue_date for line in self.lines):
            raise ValueError("PROCUREMENT_REQUISITION_DATES_INVALID")
        return self


class RFQIn(ReasonIn):
    rfq_number: Code
    package_id: Identity
    requisition_id: Identity
    issue_date: date
    closing_date: date
    commercial_terms_reference: str = Field(default="", max_length=400)
    technical_package_reference: ReferenceIn | None = None
    document_reference: DocumentReferenceIn | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.closing_date < self.issue_date:
            raise ValueError("PROCUREMENT_RFQ_DATES_INVALID")
        return self


class InvitationIn(ReasonIn):
    vendor_id: Identity


class BidIn(ReasonIn):
    rfq_id: Identity
    vendor_id: Identity
    currency: Currency
    total_bid_value: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6)]
    validity_date: date
    received_at: datetime | None = None
    supersedes_id: Identity | None = None
    document_reference: DocumentReferenceIn | None = None


class EvaluationIn(ReasonIn):
    bid_id: Identity
    evaluation_type: Literal["TECHNICAL", "COMMERCIAL"]
    evaluated_on: date | None = None
    result: Literal["ACCEPTED", "REJECTED", "CONDITIONAL"]
    score: Annotated[Decimal, Field(ge=0, le=100, decimal_places=4)] | None = None
    comments: str = Field(default="", max_length=4000)
    recommendation: Literal["RECOMMEND", "HOLD", "REJECT"]
    engineering_reference: ReferenceIn | None = None
    document_reference: DocumentReferenceIn | None = None


class AwardIn(ReasonIn):
    rfq_id: Identity
    bid_id: Identity
    decision_date: date | None = None
    approval_reference: str = Field(min_length=1, max_length=400)


class PurchaseOrderLineIn(Input):
    line_number: int = Field(gt=0, le=1000000)
    requirement_id: Identity
    description: str = Field(min_length=1, max_length=4000)
    quantity: Quantity
    uom: UOM
    unit_price: Money
    requested_date: date
    promised_date: date | None = None
    forecast_date: date | None = None


class PurchaseOrderIn(ReasonIn):
    po_number: Code
    package_id: Identity
    vendor_id: Identity
    award_id: Identity | None = None
    currency: Currency
    issue_date: date
    effective_date: date
    expected_delivery_date: date
    legacy_purchase_order_id: Identity | None = None
    reference_contract_id: Identity | None = None
    reference_commitment_id: Identity | None = None
    document_reference: DocumentReferenceIn | None = None
    lines: list[PurchaseOrderLineIn] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.expected_delivery_date < self.effective_date or self.effective_date < self.issue_date:
            raise ValueError("PROCUREMENT_PO_DATES_INVALID")
        return self


class PurchaseOrderLineChangeIn(Input):
    line_id: Identity
    quantity: Quantity
    unit_price: Money
    promised_date: date | None = None
    forecast_date: date | None = None


class PurchaseOrderRevisionIn(ReasonIn):
    effective_date: date
    changed_lines: list[PurchaseOrderLineChangeIn] = Field(min_length=1, max_length=100)
    schedule_impact_reference: ReferenceIn | None = None


class PurchaseOrderRevisionApprovalIn(ReasonIn):
    approval_reference: str = Field(min_length=1, max_length=400)


class ActionIn(ReasonIn):
    action: Literal["plan", "activate", "close", "cancel", "submit", "approve", "reject", "issue", "suspend", "retire"]
