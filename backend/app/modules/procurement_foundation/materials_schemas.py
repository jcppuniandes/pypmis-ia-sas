"""Constrained, scoped inputs for the separate physical facts in O2B."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Identity = Annotated[int, Field(gt=0)]
Code = Annotated[str, Field(min_length=1, max_length=120)]
Kind = Annotated[str, Field(min_length=1, max_length=80)]
Location = Annotated[str, Field(min_length=1, max_length=240)]
Uom = Annotated[str, Field(min_length=1, max_length=24)]
Qty = Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=6, allow_inf_nan=False)]
NonnegativeQty = Annotated[Decimal, Field(ge=0, max_digits=20, decimal_places=6, allow_inf_nan=False)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReasonIn(Input):
    reason: str = Field(min_length=3, max_length=1000)


class EvidenceIn(Input):
    document_id: Identity
    attachment_id: Identity


class MaterialItemIn(ReasonIn):
    material_code: Code
    description: str = Field(min_length=1, max_length=300)
    specification: str = Field(default="", max_length=3000)
    uom: Uom
    category: Kind


class MaterialRequirementIn(ReasonIn):
    requirement_code: Code
    material_item_id: Identity
    procurement_requirement_id: Identity | None = None
    required_quantity: Qty
    uom: Uom
    required_on_site_date: date | None = None
    source_type: Literal["MTO", "BOM"] | None = None
    evidence: EvidenceIn | None = None


class MaterialRequirementLinkIn(ReasonIn):
    procurement_requirement_id: Identity


class VendorMilestoneIn(ReasonIn):
    po_line_id: Identity
    code: Kind
    planned_date: date
    forecast_date: date | None = None
    actual_date: date | None = None


class VendorMilestoneSuccessorIn(ReasonIn):
    forecast_date: date | None = None
    actual_date: date | None = None


class ExpeditingEventIn(ReasonIn):
    po_line_id: Identity
    event_type: Literal[
        "MANUFACTURING_STARTED",
        "FABRICATION_PROGRESS",
        "VENDOR_DELAY",
        "RECOVERY_ACTION",
        "INSPECTION_PLANNED",
        "INSPECTION_COMPLETED",
        "DISPATCH_FORECAST",
        "DELIVERY_FORECAST",
    ]
    observation_date: date
    forecast_date: date | None = None
    progress_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=7, decimal_places=3)
    detail: str = Field(min_length=1, max_length=3000)


class InspectionIn(ReasonIn):
    po_line_id: Identity
    inspection_type: Kind
    inspection_date: date


class InspectionDecisionIn(ReasonIn):
    result: Literal["ACCEPTED", "REJECTED", "CONDITIONAL"]
    detail: str = Field(default="", max_length=3000)
    ncr_reference: str = Field(default="", max_length=240)
    evidence: EvidenceIn | None = None


class ShipmentLineIn(Input):
    po_line_id: Identity
    material_requirement_id: Identity
    quantity: Qty
    uom: Uom


class ShipmentIn(ReasonIn):
    shipment_number: Code
    vendor_id: Identity
    origin: Location
    destination: Location
    transport_mode: Kind
    carrier_reference: str = Field(default="", max_length=240)
    customs_reference: str = Field(default="", max_length=240)
    planned_arrival: date | None = None
    forecast_arrival: date | None = None
    evidence: EvidenceIn | None = None
    lines: list[ShipmentLineIn] = Field(min_length=1, max_length=100)


class ShipmentTransitionIn(ReasonIn):
    status: Literal["READY_FOR_DISPATCH", "DISPATCHED", "IN_TRANSIT", "ARRIVED", "CANCELLED"]
    event_date: date
    reference: str = Field(default="", max_length=240)


class ReceiptLineIn(Input):
    shipment_line_id: Identity
    quantity: Qty
    uom: Uom


class ReceiptIn(ReasonIn):
    receipt_number: Code
    shipment_id: Identity
    location: Location
    received_at: datetime
    evidence: EvidenceIn | None = None
    lines: list[ReceiptLineIn] = Field(min_length=1, max_length=100)


class MaterialAcceptanceIn(ReasonIn):
    receipt_line_id: Identity
    inspection_id: Identity | None = None
    accepted_quantity: NonnegativeQty
    rejected_quantity: NonnegativeQty
    quarantine_quantity: NonnegativeQty
    detail: str = Field(default="", max_length=3000)


class MaterialAllocationIn(ReasonIn):
    receipt_line_id: Identity
    material_requirement_id: Identity
    work_package_id: Identity
    quantity: Qty
    uom: Uom
    allocation_date: date
    source_location: Location
