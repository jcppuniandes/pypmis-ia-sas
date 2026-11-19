"""Typed field facts and explicit transitions, never consumer approvals."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

Identity = Annotated[int, Field(gt=0)]
Code = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=24, decimal_places=8)]
Nonnegative = Annotated[Decimal, Field(ge=0, max_digits=24, decimal_places=8)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReasonIn(Input):
    reason: str = Field(min_length=8, max_length=3000)


class DocumentReferenceIn(Input):
    document_id: Identity
    attachment_id: Identity
    source_hash: Digest | None = None


class CanonicalReferenceIn(Input):
    target_kind: Literal[
        "SCOPE", "PLAN", "CWA", "CWP", "IWP", "WBS", "ACTIVITY", "MILESTONE", "GEOGRAPHIC_WORKSPACE", "IFC_RELEASE"
    ]
    target_id: Identity | None = None
    schedule_version_id: Identity | None = None
    external_id: str | None = Field(default=None, min_length=1, max_length=160)
    source_hash: Digest | None = None

    @model_validator(mode="after")
    def typed(self):
        if self.target_kind in {"WBS", "ACTIVITY", "MILESTONE"}:
            if self.target_id is not None or self.schedule_version_id is None or self.external_id is None:
                raise ValueError("FIELD_ACCEPTED_SCHEDULE_AND_EXTERNAL_ID_REQUIRED")
        elif self.target_id is None or self.schedule_version_id is not None or self.external_id is not None:
            raise ValueError("FIELD_CANONICAL_TARGET_REQUIRED")
        return self


class ProviderReferenceIn(Input):
    source_type: Literal["IFC_RELEASE", "MATERIAL_ITEM", "MATERIAL_ALLOCATION"]
    source_id: Identity
    source_version: Identity
    source_hash: Digest


class ProductionIn(ReasonIn):
    production_code: Code
    workfront_id: Identity
    shift_id: Identity
    report_id: Identity | None = None
    scope_item_id: Identity
    plan_item_id: Identity | None = None
    iwp_id: Identity | None = None
    quantity: Quantity
    planned_quantity: Nonnegative | None = None
    uom: str = Field(min_length=1, max_length=40)
    production_type: str = Field(default="INSTALLED", min_length=1, max_length=80)
    observed_at: AwareDatetime
    source_reference: str = Field(min_length=3, max_length=500)
    location_reference: CanonicalReferenceIn | None = None
    engineering_reference: ProviderReferenceIn | None = None
    material_reference: ProviderReferenceIn | None = None
    document_reference: DocumentReferenceIn
    execution_condition: str = Field(default="IWP_RELEASED", min_length=1, max_length=80)
    exception_reason: str | None = Field(default=None, min_length=8, max_length=3000)
    variance_reason: str | None = Field(default=None, min_length=3, max_length=3000)
    supersedes_id: Identity | None = None
    original_production_id: Identity | None = None
    rework_reason: str | None = Field(default=None, min_length=3, max_length=3000)
    responsible_party: str | None = Field(default=None, min_length=1, max_length=300)

    @field_validator("production_type", "execution_condition")
    @classmethod
    def normalized(cls, value):
        return value.upper()

    @model_validator(mode="after")
    def origin(self):
        if self.production_type == "REWORKED":
            if not self.original_production_id or not self.rework_reason:
                raise ValueError("FIELD_REWORK_ORIGINAL_AND_REASON_REQUIRED")
        elif any((self.original_production_id, self.rework_reason, self.responsible_party)):
            raise ValueError("FIELD_REWORK_FIELDS_REQUIRE_REWORK_TYPE")
        if self.execution_condition != "IWP_RELEASED" and not self.exception_reason:
            raise ValueError("FIELD_EXCEPTION_REASON_REQUIRED")
        return self


class VerificationIn(ReasonIn):
    action: Literal["verify", "reject"]


class EventIn(ReasonIn):
    event_code: Code
    workfront_id: Identity
    shift_id: Identity | None = None
    event_type: str = Field(min_length=1, max_length=80)
    observed_at: AwareDatetime
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=3, max_length=5000)
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    duration_hours: Nonnegative | None = None
    document_reference: DocumentReferenceIn


class EventActionIn(ReasonIn):
    action: Literal["review", "close"]


class InstructionIn(ReasonIn):
    instruction_number: Code
    instruction_type: str = Field(min_length=1, max_length=80)
    instruction_date: date
    issuer: str = Field(min_length=1, max_length=300)
    recipient: str = Field(min_length=1, max_length=300)
    workfront_id: Identity
    scope_item_id: Identity | None = None
    iwp_id: Identity | None = None
    description: str = Field(min_length=3, max_length=5000)
    document_reference: DocumentReferenceIn


class InstructionActionIn(ReasonIn):
    action: Literal["issue", "acknowledge", "close"]


class ConstraintIn(ReasonIn):
    observation_code: Code
    constraint_type: str = Field(min_length=1, max_length=80)
    workfront_id: Identity
    iwp_id: Identity | None = None
    observation_date: date
    description: str = Field(min_length=3, max_length=5000)
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    document_reference: DocumentReferenceIn


class MaterialConsumptionIn(ReasonIn):
    consumption_code: Code
    production_record_id: Identity
    material_item_id: Identity
    allocation_reference: ProviderReferenceIn
    consumption_date: date
    quantity: Quantity
    uom: str = Field(min_length=1, max_length=40)
    document_reference: DocumentReferenceIn


class MappingIn(ReasonIn):
    source_kind: Literal["WORKFRONT", "PRODUCTION", "EVENT", "INSTRUCTION", "CONSTRAINT"]
    source_id: Identity
    target_reference: CanonicalReferenceIn
    action: Literal["SET", "REMOVE"] = "SET"
