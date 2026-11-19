"""Versioned administrative policy for operational field observations."""

from typing import Literal

from pydantic import Field, model_validator

from app.modules.field_operations.schemas import Code, Identity, Input

PROFILE_KIND = "field_operations_profile"
SOD_KEYS = {
    "daily_author_cannot_approve",
    "daily_submitter_cannot_approve",
    "shift_author_cannot_approve",
    "production_author_cannot_verify",
    "instruction_author_cannot_issue",
    "rework_author_cannot_approve",
}
DEFAULT_PROFILE = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "effective_from": None,
    "effective_to": None,
    "production_types": [
        "INSTALLED",
        "EXCAVATED",
        "PLACED",
        "POURED",
        "ERECTED",
        "ASSEMBLED",
        "TESTED",
        "COMPLETED",
        "REMOVED",
        "REWORKED",
        "OTHER",
    ],
    "field_event_types": [
        "DELAY",
        "DISRUPTION",
        "ACCESS_ISSUE",
        "SAFETY_INTERRUPTION",
        "EQUIPMENT_BREAKDOWN",
        "WEATHER_IMPACT",
        "DESIGN_ISSUE",
        "MATERIAL_ISSUE",
        "INSTRUCTION",
        "REWORK",
        "UNEXPECTED_CONDITION",
        "INTERFACE_ISSUE",
        "OTHER",
    ],
    "shift_types": ["DAY", "NIGHT", "OTHER"],
    "crew_trades": ["GENERAL", "CIVIL", "MECHANICAL", "ELECTRICAL", "SURVEY", "OTHER"],
    "equipment_types": ["EXTERNAL_EQUIPMENT", "OTHER"],
    "equipment_usage_types": ["PRODUCTION", "SUPPORT", "STANDBY", "OTHER"],
    "weather_conditions": ["CLEAR", "CLOUDY", "RAIN", "WIND", "OTHER"],
    "site_condition_types": ["AVAILABLE", "RESTRICTED", "BLOCKED", "OTHER"],
    "instruction_types": ["GENERAL", "DESIGN", "SAFETY", "REWORK", "OTHER"],
    "constraint_observation_types": ["DESIGN", "MATERIAL", "ACCESS", "RESOURCE", "OTHER"],
    "rework_reasons": ["DESIGN", "QUALITY_REFERENCE", "INSTALLATION", "OTHER"],
    "approval_profiles": {
        "daily_report": ["DRAFT", "SUBMITTED", "REVIEWED", "APPROVED", "CLOSED"],
        "shift": ["OPEN", "SUBMITTED", "APPROVED", "CLOSED"],
    },
    "separation_of_duties": dict.fromkeys(sorted(SOD_KEYS), True),
    "production_policy": {
        "require_released_iwp": True,
        "require_engineering_ifc": True,
        "require_material_ready": False,
        "require_daily_report_approval_for_consumption": True,
        "allowed_non_iwp_reasons": [
            "ENABLING_WORKS",
            "EMERGENCY_WORK",
            "SURVEY",
            "TEMPORARY_WORKS",
            "SUPPORT_ACTIVITY",
            "CORRECTIVE_WORK",
            "NON_IWP_ACTIVITY",
        ],
    },
    "readiness_requirements": {
        "iwp_release": True,
        "engineering_ifc": True,
        "materials": False,
        "crew": True,
        "equipment": False,
        "site_access": True,
        "instructions": False,
    },
    "max_shift_hours": 24,
    "lookahead_days": 14,
}


class ProfileScope(Input):
    type: Literal["tenant", "workspace"]
    workspace_id: Identity | None = None

    @model_validator(mode="after")
    def identity(self):
        if (self.type == "workspace") != (self.workspace_id is not None):
            raise ValueError("Workspace scope requires identity")
        return self


class ProductionPolicy(Input):
    require_released_iwp: bool
    require_engineering_ifc: bool
    require_material_ready: bool
    require_daily_report_approval_for_consumption: bool
    allowed_non_iwp_reasons: list[Code] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def approved_report_required(self):
        if not self.require_daily_report_approval_for_consumption:
            raise ValueError("Approved daily report is an invariant for native consumer adoption")
        return self


class ReadinessPolicy(Input):
    iwp_release: bool
    engineering_ifc: bool
    materials: bool
    crew: bool
    equipment: bool
    site_access: bool
    instructions: bool


class FieldOperationsProfile(Input):
    scope: ProfileScope
    inherit_to_descendants: bool
    effective_from: str | None
    effective_to: str | None
    production_types: list[Code] = Field(min_length=1, max_length=100)
    field_event_types: list[Code] = Field(min_length=1, max_length=100)
    shift_types: list[Code] = Field(min_length=1, max_length=100)
    crew_trades: list[Code] = Field(min_length=1, max_length=100)
    equipment_types: list[Code] = Field(min_length=1, max_length=100)
    equipment_usage_types: list[Code] = Field(min_length=1, max_length=100)
    weather_conditions: list[Code] = Field(min_length=1, max_length=100)
    site_condition_types: list[Code] = Field(min_length=1, max_length=100)
    instruction_types: list[Code] = Field(min_length=1, max_length=100)
    constraint_observation_types: list[Code] = Field(min_length=1, max_length=100)
    rework_reasons: list[Code] = Field(min_length=1, max_length=100)
    approval_profiles: dict[str, list[str]]
    separation_of_duties: dict[str, bool]
    production_policy: ProductionPolicy
    readiness_requirements: ReadinessPolicy
    max_shift_hours: int = Field(ge=1, le=48)
    lookahead_days: int = Field(ge=1, le=366)

    @model_validator(mode="after")
    def catalogs(self):
        fields = (
            "production_types",
            "field_event_types",
            "shift_types",
            "crew_trades",
            "equipment_types",
            "equipment_usage_types",
            "weather_conditions",
            "site_condition_types",
            "instruction_types",
            "constraint_observation_types",
            "rework_reasons",
        )
        for field in fields:
            items = getattr(self, field)
            if len(items) != len(set(items)) or any(item != item.upper() for item in items):
                raise ValueError("Distinct uppercase configured codes required")
        if self.approval_profiles != DEFAULT_PROFILE["approval_profiles"]:
            raise ValueError("Workflow invariants cannot be added or removed")
        if set(self.separation_of_duties) != SOD_KEYS:
            raise ValueError("Applicable separation rules must be explicit")
        reasons = self.production_policy.allowed_non_iwp_reasons
        if len(set(reasons)) != len(reasons) or any(item != item.upper() for item in reasons):
            raise ValueError("Distinct uppercase non-IWP exception codes required")
        return self
