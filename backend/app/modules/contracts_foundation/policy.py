"""Published Contracts policy in the shared AdminConfiguration catalog."""

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.modules.contracts_foundation.schemas import Code, Identity, Input

PROFILE_KIND = "contracts_profile"
SOD_KEYS = {
    "contract_author_cannot_approve",
    "contract_approver_cannot_execute",
    "commitment_author_cannot_approve",
    "sov_author_cannot_publish",
    "change_author_cannot_approve",
    "application_author_cannot_review",
    "certificate_author_cannot_approve",
    "claim_author_cannot_decide",
}

DEFAULT_PROFILE = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "effective_from": None,
    "effective_to": None,
    "contract_types": [
        "MAIN_CONTRACT",
        "SUBCONTRACT",
        "CONSULTING_AGREEMENT",
        "SUPPLY_AGREEMENT",
        "SERVICE_AGREEMENT",
        "PURCHASE_ORDER_BASED_AGREEMENT",
        "FRAMEWORK_AGREEMENT",
        "OTHER",
    ],
    "commercial_models": ["LUMP_SUM", "UNIT_RATE", "TIME_AND_MATERIALS", "REIMBURSABLE", "FRAMEWORK"],
    "currencies": ["USD", "COP", "EUR"],
    "contract_statuses": ["DRAFT", "APPROVED", "EXECUTED", "EFFECTIVE"],
    "change_types": ["SCOPE", "TIME", "PRICE", "OTHER"],
    "application_statuses": ["SUBMITTED", "REVIEWED", "REJECTED"],
    "certificate_statuses": ["DRAFT", "APPROVED", "REJECTED"],
    "notice_types": ["CHANGE", "DELAY", "CLAIM", "OTHER"],
    "claim_types": ["TIME", "COST", "TIME_AND_COST", "OTHER"],
    "commitment_policy": {"require_effective_contract": False},
    "separation_of_duties": dict.fromkeys(sorted(SOD_KEYS), True),
    "approval_thresholds": {},
    "retention_rules": {"NONE": "0", "STANDARD": "0.10"},
    "readiness_requirements": {"commitment": True, "sov": True, "insurance": False, "bond": False, "notice": False},
}


class ProfileScope(Input):
    type: Literal["tenant", "workspace"]
    workspace_id: Identity | None = None

    @model_validator(mode="after")
    def consistent(self):
        if (self.type == "workspace") != (self.workspace_id is not None):
            raise ValueError("Workspace scope requires a canonical workspace ID")
        return self


class CommitmentPolicy(Input):
    require_effective_contract: bool


class ReadinessPolicy(Input):
    commitment: bool
    sov: bool
    insurance: bool
    bond: bool
    notice: bool


class ContractsProfile(Input):
    scope: ProfileScope
    inherit_to_descendants: bool
    effective_from: str | None
    effective_to: str | None
    contract_types: list[Code] = Field(min_length=1, max_length=100)
    commercial_models: list[Code] = Field(min_length=1, max_length=100)
    currencies: list[str] = Field(min_length=1, max_length=100)
    contract_statuses: list[Code] = Field(min_length=4, max_length=20)
    change_types: list[Code] = Field(min_length=1, max_length=100)
    application_statuses: list[Code] = Field(min_length=3, max_length=20)
    certificate_statuses: list[Code] = Field(min_length=3, max_length=20)
    notice_types: list[Code] = Field(min_length=1, max_length=100)
    claim_types: list[Code] = Field(min_length=1, max_length=100)
    commitment_policy: CommitmentPolicy
    separation_of_duties: dict[str, bool]
    approval_thresholds: dict[str, Decimal]
    retention_rules: dict[Code, Decimal]
    readiness_requirements: ReadinessPolicy

    @model_validator(mode="after")
    def validate_catalog(self):
        for field in (
            "contract_types",
            "commercial_models",
            "currencies",
            "contract_statuses",
            "change_types",
            "application_statuses",
            "certificate_statuses",
            "notice_types",
            "claim_types",
        ):
            items = getattr(self, field)
            if len(items) != len(set(items)) or any(item != item.upper() for item in items):
                raise ValueError("Catalog values must be distinct uppercase codes")
        for field in ("contract_statuses", "application_statuses", "certificate_statuses"):
            if set(getattr(self, field)) != set(DEFAULT_PROFILE[field]):
                raise ValueError("Workflow invariant statuses cannot be added or removed")
        if any(not (len(code) == 3 and code.isascii() and code.isalpha()) for code in self.currencies):
            raise ValueError("Currency codes require three ASCII letters")
        if set(self.separation_of_duties) != SOD_KEYS:
            raise ValueError("Every applicable duty-separation decision must be explicit")
        if set(self.approval_thresholds) - {
            "contract_approval_limit",
            "commitment_approval_limit",
            "change_approval_limit",
            "certificate_approval_limit",
        } or any(not v.is_finite() or v <= 0 for v in self.approval_thresholds.values()):
            raise ValueError("Approval thresholds must be positive named caps")
        if not self.retention_rules or any(
            k != k.upper() or not v.is_finite() or not 0 <= v <= 1 for k, v in self.retention_rules.items()
        ):
            raise ValueError("Retention rules require codes with fractions between zero and one")
        return self
