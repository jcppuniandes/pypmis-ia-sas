"""Typed O2B catalogs and state machines. Configuration never grants RBAC."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.engineering_foundation.policy import ProfileScope

PROFILE_KIND = "procurement_profile"
CODE = r"^[A-Z0-9][A-Z0-9_.-]*$"
CatalogCode = Annotated[str, Field(min_length=1, max_length=80, pattern=CODE)]

TRANSITIONS = {
    "package": {
        "plan": ({"DRAFT"}, "PLANNED"),
        "close": ({"PLANNED"}, "CLOSED"),
        "cancel": ({"DRAFT", "PLANNED"}, "CANCELLED"),
    },
    "requirement": {"activate": ({"DRAFT"}, "ACTIVE"), "cancel": ({"DRAFT"}, "CANCELLED")},
    "requisition": {
        "submit": ({"DRAFT"}, "SUBMITTED"),
        "approve": ({"SUBMITTED"}, "APPROVED"),
        "reject": ({"SUBMITTED"}, "REJECTED"),
        "cancel": ({"DRAFT", "SUBMITTED"}, "CANCELLED"),
    },
    "rfq": {"issue": ({"DRAFT"}, "ISSUED"), "close": ({"ISSUED"}, "CLOSED"), "cancel": ({"DRAFT"}, "CANCELLED")},
    "po": {"approve": ({"DRAFT"}, "APPROVED"), "issue": ({"APPROVED"}, "ISSUED"), "cancel": ({"DRAFT"}, "CANCELLED")},
    "vendor": {
        "suspend": ({"ACTIVE"}, "SUSPENDED"),
        "activate": ({"SUSPENDED"}, "ACTIVE"),
        "retire": ({"ACTIVE", "SUSPENDED"}, "RETIRED"),
    },
}

DEFAULT_PROFILE = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "effective_from": None,
    "effective_to": None,
    "procurement_types": ["MATERIAL", "EQUIPMENT", "SERVICE"],
    "categories": ["GENERAL", "BULK", "TAGGED", "SPECIAL"],
    "sourcing_methods": ["RFQ", "DIRECT", "FRAMEWORK"],
    "material_categories": ["GENERAL", "BULK", "TAGGED", "SPECIAL"],
    "inspection_types": ["FACTORY", "SITE", "DOCUMENT", "FAT", "VISUAL"],
    "shipment_modes": ["ROAD", "SEA", "AIR", "RAIL", "MULTIMODAL"],
    "status_profiles": {},
    "permission_profiles": {},
    "separation_of_duties": {
        "requisition_preparer_cannot_approve": True,
        "rfq_preparer_cannot_issue": True,
        "technical_and_commercial_distinct": True,
        "evaluator_cannot_award": True,
        "po_preparer_cannot_approve": True,
        "po_revision_preparer_cannot_approve": True,
        "receiver_cannot_accept": True,
        "inspector_cannot_accept": True,
    },
    "minimum_rfq_vendors": 2,
    "require_engineering_ifc": False,
    "require_technical_evaluation": True,
    "require_commercial_evaluation": True,
    "require_award_for_po": True,
    "require_inspection_for_acceptance": True,
    "receipt_overage_percent": 0,
    "availability_max_age_days": 30,
    "lookahead_days": 28,
    "display_labels": {},
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SoD(StrictModel):
    requisition_preparer_cannot_approve: bool = True
    rfq_preparer_cannot_issue: bool = True
    technical_and_commercial_distinct: bool = True
    evaluator_cannot_award: bool = True
    po_preparer_cannot_approve: bool = True
    po_revision_preparer_cannot_approve: bool = True
    receiver_cannot_accept: bool = True
    inspector_cannot_accept: bool = True


Label = Annotated[str, Field(min_length=1, max_length=120)]


class ProcurementProfile(StrictModel):
    scope: ProfileScope
    inherit_to_descendants: bool = True
    effective_from: str | None = None
    effective_to: str | None = None
    procurement_types: list[CatalogCode] = Field(min_length=1, max_length=100)
    categories: list[CatalogCode] = Field(min_length=1, max_length=100)
    sourcing_methods: list[CatalogCode] = Field(min_length=1, max_length=100)
    material_categories: list[CatalogCode] = Field(min_length=1, max_length=100)
    inspection_types: list[CatalogCode] = Field(min_length=1, max_length=100)
    shipment_modes: list[CatalogCode] = Field(min_length=1, max_length=100)
    status_profiles: dict[CatalogCode, Label] = Field(default_factory=dict, max_length=100)
    permission_profiles: dict[str, list[str]] = Field(default_factory=dict, max_length=100)
    separation_of_duties: SoD = Field(default_factory=SoD)
    minimum_rfq_vendors: int = Field(default=2, ge=1, le=100)
    require_engineering_ifc: bool = False
    require_technical_evaluation: bool = True
    require_commercial_evaluation: bool = True
    require_award_for_po: bool = True
    require_inspection_for_acceptance: bool = True
    receipt_overage_percent: int = Field(default=0, ge=0, le=20)
    availability_max_age_days: int = Field(default=30, ge=1, le=3650)
    lookahead_days: int = Field(default=28, ge=1, le=365)
    display_labels: dict[CatalogCode, Label] = Field(default_factory=dict, max_length=100)

    @field_validator(
        "procurement_types",
        "categories",
        "sourcing_methods",
        "material_categories",
        "inspection_types",
        "shipment_modes",
    )
    @classmethod
    def distinct(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("PROCUREMENT_PROFILE_DUPLICATE_CATALOG_CODE")
        return values


def transition(entity, state, action):
    rule = TRANSITIONS.get(entity, {}).get(action)
    return rule[1] if rule and state in rule[0] else None
