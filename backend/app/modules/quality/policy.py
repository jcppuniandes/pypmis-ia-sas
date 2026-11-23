"""Versioned Quality policy and checklist templates over the existing ADMIN store."""

from typing import Literal

from pydantic import Field, model_validator

from app.modules.quality.schemas import Code, Identity, Input, Number

PROFILE_KIND = "quality_management_profile"
SOD_KEYS = {
    "plan_author_cannot_approve",
    "itp_author_cannot_approve",
    "requester_cannot_inspect",
    "inspector_cannot_close",
    "control_releaser_cannot_be_inspector",
    "ncr_author_cannot_dispose",
    "ncr_author_cannot_verify",
    "ncr_disposer_cannot_verify",
    "disposition_author_cannot_approve",
    "action_completer_cannot_verify",
    "punch_author_cannot_verify",
    "punch_owner_cannot_verify",
    "acceptance_inspector_cannot_approve",
    "acceptance_itp_author_cannot_approve",
    "acceptance_result_approver_cannot_approve",
}
DEFAULT_PROFILE = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "effective_from": None,
    "effective_to": None,
    "inspection_types": ["GENERAL", "RECEIVING", "IN_PROCESS", "FINAL", "REINSPECTION"],
    "test_types": [
        "CONCRETE_STRENGTH",
        "SOIL_DENSITY",
        "WELD_NDT",
        "COATING_THICKNESS",
        "PRESSURE",
        "ELECTRICAL_INSULATION",
        "ALIGNMENT_SURVEY",
        "OTHER",
    ],
    "control_point_types": [
        {"code": code, "require_release": code in {"HOLD", "WITNESS"}, "allow_waiver": code == "WITNESS"}
        for code in ("HOLD", "WITNESS", "REVIEW", "SURVEILLANCE", "RECORD")
    ],
    "result_codes": ["PASS", "FAIL", "CONDITIONAL", "NOT_APPLICABLE"],
    "ncr_categories": ["WORKMANSHIP", "MATERIAL", "DESIGN_REFERENCE", "DOCUMENTATION", "OTHER"],
    "severities": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
    "dispositions": ["REWORK", "REPAIR", "USE_AS_IS", "REJECT", "RETURN_TO_VENDOR", "OTHER"],
    "corrective_action_types": ["CORRECTIVE", "PREVENTIVE", "IMPROVEMENT"],
    "punch_categories": ["QUALITY", "DOCUMENTATION", "MINOR", "OTHER"],
    "acceptance_profiles": ["COMPLETE_CONTROLS"],
    "acceptance_policy": {
        "require_all_required_controls": True,
        "require_closed_pass_results": True,
        "require_no_open_ncr": True,
        "require_no_open_punch": True,
    },
    "disposition_policy": {
        "require_engineering_approval": ["USE_AS_IS"],
        "require_field_correction": ["REWORK", "REPAIR"],
    },
    "approval_thresholds": {
        "inspection_terminal_requires_review": True,
        "test_terminal_requires_review": True,
        "acceptance_requires_complete_controls": True,
    },
    "separation_of_duties": dict.fromkeys(sorted(SOD_KEYS), True),
    "checklist_templates": [
        {
            "code": "GENERAL",
            "title": "Requirement conformity",
            "items": [
                {
                    "code": "CONFORMITY",
                    "label": "Applicable requirement verified",
                    "response_type": "PASS_FAIL_NA",
                    "required": True,
                    "evidence_required": True,
                    "allow_na": False,
                    "uom": None,
                    "lower_limit": None,
                    "upper_limit": None,
                }
            ],
        }
    ],
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


class ControlPointType(Input):
    code: Code
    require_release: bool
    allow_waiver: bool


class ChecklistItem(Input):
    code: Code
    label: str = Field(min_length=1, max_length=500)
    response_type: Literal["PASS_FAIL_NA", "NUMBER", "TEXT", "BOOLEAN"]
    required: bool
    evidence_required: bool
    allow_na: bool
    uom: str | None = Field(default=None, min_length=1, max_length=40)
    lower_limit: Number | None = None
    upper_limit: Number | None = None

    @model_validator(mode="after")
    def bounds(self):
        if self.response_type == "NUMBER" and not self.uom:
            raise ValueError("Numeric checklist item requires a unit")
        if self.lower_limit is not None and self.upper_limit is not None and self.lower_limit > self.upper_limit:
            raise ValueError("Invalid checklist limits")
        if self.response_type != "NUMBER" and any(
            value is not None for value in (self.uom, self.lower_limit, self.upper_limit)
        ):
            raise ValueError("Non numeric checklist cannot carry numeric criteria")
        return self


class ChecklistTemplate(Input):
    code: Code
    title: str = Field(min_length=1, max_length=300)
    items: list[ChecklistItem] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def identities(self):
        if len({item.code for item in self.items}) != len(self.items):
            raise ValueError("Distinct checklist item codes required")
        return self


class QualityManagementProfile(Input):
    scope: ProfileScope
    inherit_to_descendants: bool
    effective_from: str | None
    effective_to: str | None
    inspection_types: list[Code] = Field(min_length=1, max_length=100)
    test_types: list[Code] = Field(min_length=1, max_length=100)
    control_point_types: list[ControlPointType] = Field(min_length=5, max_length=100)
    result_codes: list[Code] = Field(min_length=2, max_length=4)
    ncr_categories: list[Code] = Field(min_length=1, max_length=100)
    severities: list[Code] = Field(min_length=1, max_length=100)
    dispositions: list[Code] = Field(min_length=1, max_length=100)
    corrective_action_types: list[Code] = Field(min_length=1, max_length=100)
    punch_categories: list[Code] = Field(min_length=1, max_length=100)
    acceptance_profiles: list[Literal["COMPLETE_CONTROLS"]] = Field(min_length=1, max_length=1)
    acceptance_policy: dict[str, bool]
    disposition_policy: dict[str, list[Code]]
    approval_thresholds: dict[str, bool]
    separation_of_duties: dict[str, bool]
    checklist_templates: list[ChecklistTemplate] = Field(min_length=1, max_length=100)
    lookahead_days: int = Field(ge=1, le=90)

    @model_validator(mode="after")
    def catalogs(self):
        for key in (
            "inspection_types",
            "test_types",
            "result_codes",
            "ncr_categories",
            "severities",
            "dispositions",
            "corrective_action_types",
            "punch_categories",
        ):
            values = getattr(self, key)
            if len(set(values)) != len(values) or any(value != value.upper() for value in values):
                raise ValueError("Distinct uppercase configured codes required")
        if not {"PASS", "FAIL"}.issubset(self.result_codes) or not set(self.result_codes).issubset(
            DEFAULT_PROFILE["result_codes"]
        ):
            raise ValueError("Registered canonical result outcomes required")
        if len({point.code for point in self.control_point_types}) != len(self.control_point_types):
            raise ValueError("Distinct control point types required")
        if not {"HOLD", "WITNESS", "REVIEW", "SURVEILLANCE", "RECORD"}.issubset(
            {point.code for point in self.control_point_types}
        ):
            raise ValueError("Minimum control point types required")
        hold = next(point for point in self.control_point_types if point.code == "HOLD")
        if not hold.require_release or hold.allow_waiver:
            raise ValueError("HOLD requires explicit release and cannot be waived")
        if set(self.separation_of_duties) != SOD_KEYS:
            raise ValueError("Applicable separation rules must be explicit")
        if (
            self.acceptance_policy != DEFAULT_PROFILE["acceptance_policy"]
            or self.approval_thresholds != DEFAULT_PROFILE["approval_thresholds"]
        ):
            raise ValueError("Mandatory v1 acceptance and terminal review thresholds cannot be waived")
        if set(self.disposition_policy) != set(DEFAULT_PROFILE["disposition_policy"]):
            raise ValueError("Explicit disposition prerequisites required")
        if "USE_AS_IS" not in self.disposition_policy["require_engineering_approval"]:
            raise ValueError("Use as is requires an authorized technical disposition")
        if not {"REWORK", "REPAIR"}.issubset(self.disposition_policy["require_field_correction"]):
            raise ValueError("Rework and repair require execution evidence")
        if len({item.code for item in self.checklist_templates}) != len(self.checklist_templates):
            raise ValueError("Distinct checklist template codes required")
        return self
