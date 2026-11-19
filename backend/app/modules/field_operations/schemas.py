"""Strict command contracts for observed field facts."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Identity = Annotated[int, Field(gt=0)]
Code = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")]
Amount = Annotated[Decimal, Field(ge=0, max_digits=24, decimal_places=8)]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReasonIn(Input):
    reason: str = Field(min_length=8, max_length=3000)


class DocumentPinIn(Input):
    document_id: Identity
    attachment_id: Identity
    source_hash: Digest | None = None


class ReferenceIn(Input):
    target_kind: Literal[
        "SCOPE",
        "PLAN",
        "CWA",
        "CWP",
        "IWP",
        "PWP",
        "EWP",
        "GEOGRAPHIC_WORKSPACE",
        "WBS",
        "ACTIVITY",
        "MILESTONE",
        "CBS",
        "COST_CODE",
        "CONTROL_ACCOUNT",
    ]
    target_id: Identity | None = None
    schedule_version_id: Identity | None = None
    external_id: str | None = Field(default=None, min_length=1, max_length=160)
    source_hash: Digest | None = None

    @model_validator(mode="after")
    def identity(self):
        if self.target_kind in {"WBS", "ACTIVITY", "MILESTONE"}:
            if not self.schedule_version_id or not self.external_id or self.target_id:
                raise ValueError("Accepted schedule version and external identity required")
        elif self.target_id is None or self.schedule_version_id or self.external_id:
            raise ValueError("Canonical target identity required")
        return self


class WorkfrontIn(ReasonIn):
    workfront_code: Code
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=5000)
    location_reference: ReferenceIn
    cwa_id: Identity | None = None
    cwp_id: Identity | None = None
    iwp_id: Identity | None = None
    responsible_user_id: Identity | None = None
    planned_start: date
    planned_finish: date


class WorkfrontActionIn(ReasonIn):
    action: Literal["activate", "suspend", "resume", "complete"]
    actual_date: date | None = None


class ShiftIn(ReasonIn):
    shift_code: Code
    shift_type: Code
    shift_date: date
    start_time: AwareDatetime
    end_time: AwareDatetime
    workfront_id: Identity
    supervisor_user_id: Identity | None = None
    weather_reference: str = Field(default="", max_length=2000)


class ShiftActionIn(ReasonIn):
    action: Literal["submit", "approve", "close"]


class DailyReportIn(ReasonIn):
    report_number: Code
    report_date: date
    shift_id: Identity
    workfront_ids: list[Identity] = Field(default_factory=list, max_length=50)
    reporting_party: str = Field(min_length=1, max_length=240)
    weather: dict = Field(default_factory=dict)
    work_conditions: str = Field(default="", max_length=5000)
    comments: str = Field(default="", max_length=5000)
    document_references: list[DocumentPinIn] = Field(default_factory=list, max_length=40)


class DailyReportActionIn(ReasonIn):
    action: Literal["submit", "review", "approve", "close"]


class CrewIn(ReasonIn):
    crew_code: Code
    description: str = Field(min_length=1, max_length=4000)
    trade: Code
    vendor_id: Identity | None = None
    supervisor_user_id: Identity | None = None


class CrewActionIn(ReasonIn):
    action: Literal["activate", "inactivate"]


class EquipmentReferenceIn(ReasonIn):
    source_system: Code
    external_id: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=4000)
    equipment_type: Code


class EquipmentReferenceActionIn(ReasonIn):
    action: Literal["available", "unavailable"]


class UsageIn(ReasonIn):
    record_code: Code
    shift_id: Identity
    workfront_id: Identity
    activity_reference: ReferenceIn | None = None
    document_references: list[DocumentPinIn] = Field(default_factory=list, max_length=30)
    supersedes_id: Identity | None = None


class LaborIn(UsageIn):
    crew_id: Identity
    trade: Code
    headcount: int = Field(gt=0, le=100000)
    regular_hours: Amount
    overtime_hours: Amount = Decimal(0)
    productive_hours: Amount | None = None
    nonproductive_hours: Amount | None = None


class EquipmentUsageIn(UsageIn):
    equipment_id: Identity
    usage_type: Code
    operating_hours: Amount
    idle_hours: Amount = Decimal(0)
    standby_hours: Amount = Decimal(0)
    downtime_hours: Amount = Decimal(0)


class ConditionIn(ReasonIn):
    condition_code: Code
    condition_date: date
    shift_id: Identity
    workfront_id: Identity
    location_reference: ReferenceIn
    weather_condition: Code
    temperature: Decimal | None = Field(default=None, ge=-100, le=100)
    rainfall: Amount | None = None
    wind: Amount | None = None
    access_condition: Code
    site_condition: str = Field(min_length=1, max_length=5000)
    source: str = Field(min_length=1, max_length=2000)
    document_references: list[DocumentPinIn] = Field(default_factory=list, max_length=30)


class ProfileIn(ReasonIn):
    code: Code
    name: str = Field(min_length=1, max_length=240)
    content_json: dict


class ProfileUpdateIn(ReasonIn):
    name: str = Field(min_length=1, max_length=240)
    content_json: dict
