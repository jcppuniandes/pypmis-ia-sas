"""Gate 07J-EVID policy, provider registry and contextual resolution.

This module is deliberately configuration + registry + validation.  Gate 07J
continues to own Investment Gate Preparation and package readiness; this module
does not create an Investment Decision, FID, or a new business readiness engine.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent
from app.modules.business_case.models import BusinessCaseDecisionSnapshot
from app.modules.business_case.service import BusinessCaseService
from app.modules.commercial_strategy.service import CommercialStrategyService
from app.modules.economic_financial_model.service import EconomicFinancialModelService
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.funds_manager.service import FundsManagerService
from app.modules.investment_evidence_policy.decision_criteria import (
    CONTROLLED_OPERATORS,
    DECISION_CRITERION_TYPES,
    EVIDENCE_QUALITY_STATES,
    decision_criterion_policy,
    validate_criterion_policy,
)
from app.modules.investment_evidence_policy.schemas import (
    PolicyConfigurationOut,
    PolicyOverviewOut,
    PolicyPreviewOut,
    ProviderOut,
)
from app.modules.permit_readiness.service import PermitReadinessService
from app.modules.portfolio_convergence.service import PortfolioConvergenceService
from app.modules.project_definition.service import ProjectDefinitionService
from app.modules.risk_readiness.service import RiskReadinessService
from app.modules.strategic_benefits.service import StrategicBenefitsService

CONFIGURATION_KIND = "investment_evidence_policy"
DEFAULT_CODE = "pyp-investment-decision-evidence-policy"
READY_OUTPUT = "READY_FOR_BUSINESS_CASE_AND_ECONOMIC_FINANCIAL_GATE_EVIDENCE"
VALIDATED_RELEASE = "GATE07M_EVID_POLICY_UPDATE_VALIDATED"
EVID2_READY_OUTPUT = "READY_FOR_GOVERNED_GATE_DECISION_WITH_INTEGRATED_STRATEGIC_EVIDENCE"
EVID2_VALIDATED_RELEASE = "GATE07J_EVID_2_DECISION_CRITERIA_POLICY_RELEASE_VALIDATED"

CLASSIFICATIONS = {"A", "B", "C"}
SCOPES = {"PORTFOLIO", "PROJECT_SET", "EACH_PROJECT", "SELECTED_PROJECTS_ONLY"}
EVIDENCE_TYPES = (
    "PORTFOLIO_RECOMMENDATION",
    "BUDGET_FEASIBILITY",
    "RESOURCE_FEASIBILITY",
    "PROJECT_DEFINITION_READINESS",
    "FEL_STAGE_READINESS",
    "PDRI_OR_DEFINITION_ASSESSMENT",
    "BUSINESS_CASE_READINESS",
    "FUNDING_READINESS",
    "RISK_READINESS",
    "BASIC_DATA_READINESS",
    "OWNER_CAPABILITY_READINESS",
    "COST_SOURCE_READINESS",
    "SCHEDULE_SOURCE_READINESS",
    "PERMIT_READINESS",
    "ECONOMIC_FINANCIAL_READINESS",
    "BENEFITS_PLAN_READINESS",
    "CONTRACTING_STRATEGY_READINESS",
    "COMMERCIAL_READINESS",
    "EXECUTION_PLAN_READINESS",
    "SCHEDULE_MATURITY",
    "COST_ESTIMATE_MATURITY",
    "ENVIRONMENTAL_SOCIAL_READINESS",
    "LAND_ACCESS_READINESS",
    "STAKEHOLDER_READINESS",
    "TECHNICAL_ASSURANCE",
    "OTHER_GOVERNED_EVIDENCE",
)

REQUIRED_PROVIDER_FIELDS = {
    "evidence_type",
    "scope",
    "readiness_status",
    "source_current",
    "evidence_hash",
    "as_of_date",
    "warnings",
    "blockers",
}


def _provider(
    provider_key: str,
    evidence_type: str,
    source_module: str,
    source_contract: str,
    scopes: set[str],
    *,
    status: str = "AVAILABLE",
    notes: str,
) -> dict[str, Any]:
    return {
        "provider_key": provider_key,
        "evidence_type": evidence_type,
        "source_module": source_module,
        "source_contract": source_contract,
        "supports_portfolio_scope": "PORTFOLIO" in scopes,
        "supports_project_scope": bool(scopes & {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"}),
        "supports_project_set_scope": "PROJECT_SET" in scopes,
        "supports_hash": status == "AVAILABLE",
        "supports_current_flag": status == "AVAILABLE",
        "supports_readiness": status == "AVAILABLE",
        "status": status,
        "version": "1.0",
        "notes": notes,
        "availability": status,
        "contract_status": "VALID" if status == "AVAILABLE" else "INVALID",
        "last_validation": "2026-09-03T00:00:00+00:00" if status == "AVAILABLE" else None,
        "contract_fields": sorted(REQUIRED_PROVIDER_FIELDS) if status == "AVAILABLE" else [],
    }


PROVIDER_REGISTRY: dict[str, dict[str, Any]] = {
    "GATE07I_PORTFOLIO_RECOMMENDATION": _provider(
        "GATE07I_PORTFOLIO_RECOMMENDATION",
        "PORTFOLIO_RECOMMENDATION",
        "PORTFOLIO_SCENARIO_CONVERGENCE",
        "InvestmentGatePreparationContractOut",
        {"PORTFOLIO", "PROJECT_SET"},
        notes="Validated Gate 07I recommendation contract.",
    ),
    "GATE07G_BUDGET_FEASIBILITY": _provider(
        "GATE07G_BUDGET_FEASIBILITY",
        "BUDGET_FEASIBILITY",
        "PORTFOLIO_BUDGET",
        "Gate07I budget_scenario_ref + budget_feasibility_summary",
        {"PORTFOLIO", "PROJECT_SET"},
        notes="Reuses Gate 07G/07G-A, including dependency and CAPEX/EXPENSE detail.",
    ),
    "GATE07H_RESOURCE_FEASIBILITY": _provider(
        "GATE07H_RESOURCE_FEASIBILITY",
        "RESOURCE_FEASIBILITY",
        "PORTFOLIO_RESOURCE",
        "Gate07I resource_scenario_ref + resource_feasibility_summary",
        {"PORTFOLIO", "PROJECT_SET"},
        notes="Validated Gate 07H resource recommendation source.",
    ),
    "GATE07J_FEL_PROJECT_DEFINITION": _provider(
        "GATE07J_FEL_PROJECT_DEFINITION",
        "PROJECT_DEFINITION_READINESS",
        "PROJECT_DEFINITION_FEL",
        "InvestmentGateEvidenceOut",
        {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"},
        notes="Reusable provider for definition, FEL, PDRI and estimate maturity evidence.",
    ),
    "GATE07J_FUND_FUNDING_READINESS": _provider(
        "GATE07J_FUND_FUNDING_READINESS",
        "FUNDING_READINESS",
        "FUNDS_MANAGER",
        "InvestmentGateFundingEvidenceOut",
        {"PORTFOLIO", "PROJECT_SET"},
        notes="Validated Gate 07J-FUND funding readiness source.",
    ),
    "RISK_READINESS_PROVIDER": _provider(
        "RISK_READINESS_PROVIDER",
        "RISK_READINESS",
        "RISK_READINESS",
        "InvestmentGateRiskEvidenceOut",
        {"PORTFOLIO", "PROJECT_SET", "EACH_PROJECT"},
        notes="Validated Gate 07J-RISK Project and Project Set Risk Readiness evidence.",
    ),
    "BASIC_DATA_READINESS_PROVIDER": _provider(
        "BASIC_DATA_READINESS_PROVIDER",
        "BASIC_DATA_READINESS",
        "BASIC_DATA_READINESS",
        "BasicDataReadinessEvidence.v1",
        {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"},
        notes=(
            "Wave 2B current COMPLETED READY non-stale Project evidence only. "
            "Registry availability does not add requirements to published Gate policies."
        ),
    ),
    "PERMIT_READINESS_PROVIDER": _provider(
        "PERMIT_READINESS_PROVIDER",
        "PERMIT_READINESS",
        "PERMIT_READINESS",
        "InvestmentGatePermitEvidenceOut",
        {"PROJECT_SET", "EACH_PROJECT", "SELECTED_PROJECTS_ONLY"},
        notes="Validated Gate 07J-PERMIT Project and Project Set Permit Readiness evidence.",
    ),
    "OWNER_CAPABILITY_READINESS_PROVIDER": _provider(
        "OWNER_CAPABILITY_READINESS_PROVIDER",
        "OWNER_CAPABILITY_READINESS",
        "OWNER_CAPABILITY_READINESS",
        "OwnerCapabilityReadinessEvidence.v1",
        {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"},
        notes=(
            "Wave 3B current COMPLETED READY non-stale Project evidence only. "
            "Availability does not alter existing Gate policies, packages or FID decisions."
        ),
    ),
    "COST_SOURCE_READINESS_PROVIDER": _provider(
        "COST_SOURCE_READINESS_PROVIDER",
        "COST_SOURCE_READINESS",
        "QRA_COST_SOURCE_READINESS",
        "CostSourceReadinessEvidence.v1",
        {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"},
        notes="Current COMPLETED READY cost-source evidence only; no QRA simulation or Gate policy mutation.",
    ),
    "SCHEDULE_SOURCE_READINESS_PROVIDER": _provider(
        "SCHEDULE_SOURCE_READINESS_PROVIDER",
        "SCHEDULE_SOURCE_READINESS",
        "QRA_SCHEDULE_SOURCE_READINESS",
        "ScheduleSourceReadinessEvidence.v1",
        {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"},
        notes="Current COMPLETED READY imported schedule-source evidence; no CPM, sampling or result provider.",
    ),
    "QRA_RESULT_PROVIDER": _provider(
        "QRA_RESULT_PROVIDER",
        "QRA_RESULT",
        "QRA_CALCULATION_ENGINE",
        "QraResultEvidence.v1",
        {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"},
        notes="Accepted current governed analytical result only. Availability never changes published Gate policies or approves investment, budget or contingency.",
    ),
    "BUSINESS_CASE_READINESS_PROVIDER": _provider(
        "BUSINESS_CASE_READINESS_PROVIDER",
        "BUSINESS_CASE_READINESS",
        "BUSINESS_CASE_MANAGER",
        "BusinessCaseEvidenceContract.v1",
        {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"},
        notes="Gate 07M-BC governed Business Case revision/readiness adapter; no duplicate Business Case domain.",
    ),
    "ECONOMIC_FINANCIAL_READINESS_PROVIDER": _provider(
        "ECONOMIC_FINANCIAL_READINESS_PROVIDER",
        "ECONOMIC_FINANCIAL_READINESS",
        "ECONOMIC_FINANCIAL_MODEL",
        "ProviderEvidenceOut",
        {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"},
        notes="Validated Gate 07M-FIN Project economic-financial readiness evidence.",
    ),
    "BENEFITS_READINESS_PROVIDER": _provider(
        "BENEFITS_READINESS_PROVIDER",
        "BENEFITS_PLAN_READINESS",
        "STRATEGIC_BENEFITS_PLAN",
        "BenefitsReadinessProviderOut",
        {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"},
        notes=(
            "Gate 07M-BEN governed Project Strategic Benefits Plan readiness. "
            "Registry-only integration; published Gate07J-EVID matrices remain unchanged."
        ),
    ),
    "COMMERCIAL_READINESS_PROVIDER": _provider(
        "COMMERCIAL_READINESS_PROVIDER",
        "COMMERCIAL_READINESS",
        "COMMERCIAL_CONTRACTING_STRATEGY",
        "CommercialReadinessProviderOut",
        {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"},
        notes=(
            "Gate 07M-COMM governed Project commercial-readiness evidence. "
            "Compatible with the legacy CONTRACTING_STRATEGY_READINESS label; "
            "published Gate07J-EVID matrices remain unchanged."
        ),
    ),
}

# Compatibility is registry metadata only.  It does not add or reclassify a
# requirement in any published/default Gate07J-EVID policy.
PROVIDER_REGISTRY["COMMERCIAL_READINESS_PROVIDER"]["compatible_evidence_types"] = ["CONTRACTING_STRATEGY_READINESS"]


def _requirement(
    evidence_type: str,
    classification: str,
    *,
    scope: str,
    blocking: bool,
    provider_key: str | None = None,
    validity: int | None = None,
    coverage: float | None = None,
    rationale: str,
    order: int,
) -> dict[str, Any]:
    required = classification != "C"
    return {
        "requirement_key": evidence_type.lower().replace("_", "-"),
        "evidence_type": evidence_type,
        "classification": classification,
        "required": required,
        "blocking": blocking if required else False,
        "scope": scope,
        "provider_key": provider_key,
        "provider_required": classification == "A",
        "minimum_readiness_status": "READY" if classification == "A" else None,
        "minimum_stage": None,
        "minimum_maturity": None,
        "validity_period_days": validity,
        "coverage_requirement": coverage,
        "allow_manual_reference": classification == "B",
        "manual_validation_required": classification == "B",
        "must_be_current_with_project_set": scope in {"PROJECT_SET", "EACH_PROJECT", "SELECTED_PROJECTS_ONLY"},
        "must_be_current_with_recommendation": evidence_type
        in {"PORTFOLIO_RECOMMENDATION", "BUDGET_FEASIBILITY", "RESOURCE_FEASIBILITY"},
        "must_be_current_with_budget": evidence_type in {"BUDGET_FEASIBILITY", "FUNDING_READINESS"},
        "must_be_current_with_FEL": evidence_type
        in {
            "PROJECT_DEFINITION_READINESS",
            "FEL_STAGE_READINESS",
            "PDRI_OR_DEFINITION_ASSESSMENT",
            "COST_ESTIMATE_MATURITY",
        },
        "project_type_filter": ["*"],
        "governance_model_filter": ["CAPITAL_OWNER"],
        "rationale": rationale,
        "notes": "",
        "order": order,
    }


def _matrix(profile: str) -> list[dict[str, Any]]:
    ffa = profile == "PYP-FFA"
    rows = [
        _requirement(
            "PORTFOLIO_RECOMMENDATION",
            "A",
            scope="PORTFOLIO",
            blocking=True,
            provider_key="GATE07I_PORTFOLIO_RECOMMENDATION",
            rationale="Formal portfolio recommendation is the governed entry source.",
            order=10,
        ),
        _requirement(
            "BUDGET_FEASIBILITY",
            "A",
            scope="PORTFOLIO",
            blocking=True,
            provider_key="GATE07G_BUDGET_FEASIBILITY",
            rationale="Budget feasibility must remain current with the recommended set.",
            order=20,
        ),
        _requirement(
            "RESOURCE_FEASIBILITY",
            "A" if ffa else "B",
            scope="PORTFOLIO",
            blocking=ffa,
            provider_key="GATE07H_RESOURCE_FEASIBILITY",
            rationale="FFA requires structured capacity; selection may accept controlled evidence.",
            order=30,
        ),
        _requirement(
            "PROJECT_DEFINITION_READINESS",
            "A",
            scope="EACH_PROJECT",
            blocking=True,
            provider_key="GATE07J_FEL_PROJECT_DEFINITION",
            validity=365,
            coverage=100,
            rationale="Definition maturity is evaluated per selected project.",
            order=40,
        ),
        _requirement(
            "FEL_STAGE_READINESS",
            "A",
            scope="EACH_PROJECT",
            blocking=True,
            provider_key="GATE07J_FEL_PROJECT_DEFINITION",
            validity=365,
            coverage=100,
            rationale="The existing FEL provider is authoritative for stage readiness.",
            order=50,
        ),
        _requirement(
            "PDRI_OR_DEFINITION_ASSESSMENT",
            "A",
            scope="EACH_PROJECT",
            blocking=True,
            provider_key="GATE07J_FEL_PROJECT_DEFINITION",
            validity=365,
            coverage=100,
            rationale="PDRI or equivalent assessment is reused from FEL; no duplicate scoring engine.",
            order=60,
        ),
        _requirement(
            "BUSINESS_CASE_READINESS",
            "A",
            scope="EACH_PROJECT",
            blocking=True,
            provider_key="BUSINESS_CASE_READINESS_PROVIDER",
            coverage=100,
            rationale="A current, completed and READY governed Business Case is required per applicable Project.",
            order=64,
        ),
        _requirement(
            "ECONOMIC_FINANCIAL_READINESS",
            "A" if ffa else "B",
            scope="EACH_PROJECT",
            blocking=ffa,
            provider_key="ECONOMIC_FINANCIAL_READINESS_PROVIDER",
            coverage=100,
            rationale=(
                "FFA requires the authoritative FIN overall readiness; selection accepts preliminary governed evidence."
                if ffa
                else "Selection accepts governed preliminary economics or controlled Class B evidence by Project Type."
            ),
            order=66,
        ),
        _requirement(
            "FUNDING_READINESS",
            "A" if ffa else "B",
            scope="PORTFOLIO",
            blocking=ffa,
            provider_key="GATE07J_FUND_FUNDING_READINESS",
            validity=180,
            rationale="FFA requires governed funds coverage; selection accepts validated evidence.",
            order=70,
        ),
        _requirement(
            "RISK_READINESS",
            "A" if ffa else "B",
            scope="PROJECT_SET",
            blocking=ffa,
            provider_key="RISK_READINESS_PROVIDER" if ffa else None,
            validity=90,
            coverage=100 if ffa else None,
            rationale="FFA needs structured, current and aggregable risk readiness; selection accepts validated evidence.",
            order=80,
        ),
        _requirement(
            "PERMIT_READINESS",
            "B",
            scope="EACH_PROJECT",
            blocking=ffa,
            validity=180,
            coverage=100 if ffa else 80,
            rationale="A validated permit evidence reference is initially sufficient except explicit overrides.",
            order=90,
        ),
        _requirement(
            "CONTRACTING_STRATEGY_READINESS",
            "B",
            scope="EACH_PROJECT",
            blocking=ffa,
            validity=365,
            coverage=100 if ffa else 80,
            rationale="A governed strategy document is sufficient; no procurement engine is created.",
            order=100,
        ),
        _requirement(
            "EXECUTION_PLAN_READINESS",
            "B",
            scope="EACH_PROJECT",
            blocking=ffa,
            validity=365,
            coverage=100 if ffa else 80,
            rationale="A validated Project Execution Plan reference is initially sufficient.",
            order=110,
        ),
        _requirement(
            "SCHEDULE_MATURITY",
            "B",
            scope="EACH_PROJECT",
            blocking=ffa,
            validity=180,
            coverage=100 if ffa else 80,
            rationale="Controlled maturity evidence is sufficient; no CPM engine is created.",
            order=120,
        ),
        _requirement(
            "COST_ESTIMATE_MATURITY",
            "A" if ffa else "B",
            scope="EACH_PROJECT",
            blocking=ffa,
            provider_key="GATE07J_FEL_PROJECT_DEFINITION",
            validity=180,
            coverage=100 if ffa else 80,
            rationale="FFA reuses estimate maturity from FEL; selection permits validated evidence.",
            order=130,
        ),
        _requirement(
            "ENVIRONMENTAL_SOCIAL_READINESS",
            "B" if ffa else "C",
            scope="EACH_PROJECT",
            blocking=False,
            validity=180,
            coverage=100 if ffa else None,
            rationale="Validated evidence is sufficient at FFA; not required for selection by default.",
            order=140,
        ),
        _requirement(
            "LAND_ACCESS_READINESS",
            "B" if ffa else "C",
            scope="EACH_PROJECT",
            blocking=False,
            validity=180,
            coverage=100 if ffa else None,
            rationale="Validated land-access evidence is sufficient at FFA; not required for selection by default.",
            order=150,
        ),
        _requirement(
            "STAKEHOLDER_READINESS",
            "B" if ffa else "C",
            scope="EACH_PROJECT",
            blocking=False,
            validity=180,
            coverage=100 if ffa else None,
            rationale="Controlled stakeholder evidence is sufficient when applicable.",
            order=160,
        ),
        _requirement(
            "TECHNICAL_ASSURANCE",
            "B" if ffa else "C",
            scope="EACH_PROJECT",
            blocking=False,
            validity=365,
            coverage=100 if ffa else None,
            rationale="Controlled technical assurance is sufficient at this gate.",
            order=170,
        ),
        _requirement(
            "OTHER_GOVERNED_EVIDENCE",
            "C",
            scope="PORTFOLIO",
            blocking=False,
            rationale="No unspecified global evidence is mandatory.",
            order=180,
        ),
    ]
    return rows


DEFAULT_POLICY: dict[str, Any] = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "policy_code": "PYP-INVESTMENT-EVIDENCE",
    "policy_name": "Investment Decision Evidence Policy",
    "effective_from": None,
    "policy_update": "GATE07M_EVID",
    "applicable_governance_models": ["CAPITAL_OWNER"],
    "gate_profiles": {
        "PYP-INV-SELECT": {"allow_valid_with_conditions": True, "requirements": _matrix("PYP-INV-SELECT")},
        "PYP-FFA": {"allow_valid_with_conditions": False, "requirements": _matrix("PYP-FFA")},
    },
    "project_type_overrides": [
        {
            "gate_profile_code": "PYP-FFA",
            "project_type_filter": ["MINING"],
            "governance_model_filter": ["CAPITAL_OWNER"],
            "evidence_type": "PERMIT_READINESS",
            "classification": "A",
            "required": True,
            "blocking": True,
            "provider_key": "PERMIT_READINESS_PROVIDER",
            "provider_required": True,
            "allow_manual_reference": False,
            "manual_validation_required": False,
            "rationale": "Mining FFA requires a structured current permit source; manual evidence cannot substitute it.",
        },
        {
            "gate_profile_code": "PYP-INV-SELECT",
            "project_type_filter": ["INTERNAL", "COMPLIANCE", "INTERNAL_COMPLIANCE"],
            "governance_model_filter": ["CAPITAL_OWNER"],
            "evidence_type": "ECONOMIC_FINANCIAL_READINESS",
            "classification": "C",
            "required": False,
            "blocking": False,
            "provider_key": None,
            "provider_required": False,
            "allow_manual_reference": False,
            "manual_validation_required": False,
            "coverage_requirement": None,
            "rationale": "Internal/compliance selection does not require FIN unless a published override enables it.",
        },
        {
            "gate_profile_code": "PYP-FFA",
            "project_type_filter": ["INTERNAL", "COMPLIANCE", "INTERNAL_COMPLIANCE"],
            "governance_model_filter": ["CAPITAL_OWNER"],
            "evidence_type": "ECONOMIC_FINANCIAL_READINESS",
            "classification": "C",
            "required": False,
            "blocking": False,
            "provider_key": None,
            "provider_required": False,
            "allow_manual_reference": False,
            "manual_validation_required": False,
            "coverage_requirement": None,
            "rationale": "Internal/compliance FFA keeps FIN policy-flexible and does not force commercial metrics.",
        },
        {
            "gate_profile_code": "PYP-FFA",
            "project_type_filter": ["PUBLIC", "NON_REVENUE", "PUBLIC_ECONOMIC_APPRAISAL"],
            "governance_model_filter": ["CAPITAL_OWNER"],
            "evidence_type": "ECONOMIC_FINANCIAL_READINESS",
            "classification": "A",
            "required": True,
            "blocking": True,
            "provider_key": "ECONOMIC_FINANCIAL_READINESS_PROVIDER",
            "provider_required": True,
            "allow_manual_reference": False,
            "manual_validation_required": False,
            "coverage_requirement": 100,
            "required_readiness_dimensions": ["ECONOMIC_READINESS"],
            "rationale": "Public/non-revenue FFA consumes FIN overall readiness with economic appraisal applicability.",
        },
        {
            "gate_profile_code": "PYP-FFA",
            "project_type_filter": ["COMMERCIAL", "REVENUE", "COMMERCIAL_PROJECT"],
            "governance_model_filter": ["CAPITAL_OWNER"],
            "evidence_type": "ECONOMIC_FINANCIAL_READINESS",
            "classification": "A",
            "required": True,
            "blocking": True,
            "provider_key": "ECONOMIC_FINANCIAL_READINESS_PROVIDER",
            "provider_required": True,
            "allow_manual_reference": False,
            "manual_validation_required": False,
            "coverage_requirement": 100,
            "required_readiness_dimensions": ["FINANCIAL_MODEL_READINESS"],
            "rationale": "Commercial/revenue FFA consumes authoritative FIN overall and financial readiness.",
        },
        {
            "gate_profile_code": "PYP-FFA",
            "project_type_filter": ["MIXED", "MIXED_PROJECT"],
            "governance_model_filter": ["CAPITAL_OWNER"],
            "evidence_type": "ECONOMIC_FINANCIAL_READINESS",
            "classification": "A",
            "required": True,
            "blocking": True,
            "provider_key": "ECONOMIC_FINANCIAL_READINESS_PROVIDER",
            "provider_required": True,
            "allow_manual_reference": False,
            "manual_validation_required": False,
            "coverage_requirement": 100,
            "required_readiness_dimensions": ["ECONOMIC_READINESS", "FINANCIAL_MODEL_READINESS"],
            "rationale": "Mixed FFA consumes authoritative FIN overall readiness across economic and financial dimensions.",
        },
    ],
    "blocking_policy": {"class_A_failure": "BLOCK", "class_B_invalid": "BLOCK_WHEN_REQUIREMENT_BLOCKING"},
    "validity_policy": {"no_global_expiration": True},
    "coverage_policy": {"do_not_average_missing_projects": True},
    "conditions_policy": {"supported_status": "VALID_WITH_CONDITIONS", "existing_gate07j_conditions": True},
    "dependency_reuse": "BUDGET_FEASIBILITY_SOURCE_SUMMARY",
    "capex_expense_reuse": "BUDGET_FEASIBILITY_DETAIL",
    "release_status": "DRAFT",
}


def gate07m_evid_policy_update(source: dict[str, Any]) -> dict[str, Any]:
    """Merge the Gate 07M evidence rows into an existing policy without replacing unrelated rules."""

    updated = deepcopy(source)
    updated["policy_update"] = "GATE07M_EVID"
    updated.setdefault("effective_from", None)
    models = list(updated.get("applicable_governance_models", []))
    if "CAPITAL_OWNER" not in models:
        models.append("CAPITAL_OWNER")
    updated["applicable_governance_models"] = models
    for profile_code in ("PYP-INV-SELECT", "PYP-FFA"):
        profile = updated.setdefault("gate_profiles", {}).setdefault(
            profile_code,
            {"allow_valid_with_conditions": profile_code == "PYP-INV-SELECT", "requirements": []},
        )
        rows = [
            deepcopy(item)
            for item in profile.get("requirements", [])
            if item.get("evidence_type") not in {"BUSINESS_CASE_READINESS", "ECONOMIC_FINANCIAL_READINESS"}
        ]
        required_updates = [
            deepcopy(item)
            for item in DEFAULT_POLICY["gate_profiles"][profile_code]["requirements"]
            if item.get("evidence_type") in {"BUSINESS_CASE_READINESS", "ECONOMIC_FINANCIAL_READINESS"}
        ]
        profile["requirements"] = sorted(rows + required_updates, key=lambda item: int(item.get("order", 0)))
    overrides = [
        deepcopy(item)
        for item in updated.get("project_type_overrides", [])
        if item.get("evidence_type") not in {"BUSINESS_CASE_READINESS", "ECONOMIC_FINANCIAL_READINESS"}
    ]
    gate07m_overrides = [
        deepcopy(item)
        for item in DEFAULT_POLICY["project_type_overrides"]
        if item.get("evidence_type") in {"BUSINESS_CASE_READINESS", "ECONOMIC_FINANCIAL_READINESS"}
    ]
    updated["project_type_overrides"] = overrides + gate07m_overrides
    return updated


def gate07j_evid2_policy_update(source: dict[str, Any]) -> dict[str, Any]:
    """Create the additive EVID-2 draft payload without mutating its source.

    Existing published revisions remain byte-for-byte historical.  ADMIN may
    clone a published revision, apply this deterministic transform to the DRAFT,
    preview it, and publish it under the existing ETag lifecycle.
    """

    updated = gate07m_evid_policy_update(source)
    updated["policy_update"] = "GATE07J_EVID_2"
    updated["decision_criterion_policy"] = decision_criterion_policy(updated)
    for profile_code in ("PYP-INV-SELECT", "PYP-FFA"):
        ffa = profile_code == "PYP-FFA"
        profile = updated.setdefault("gate_profiles", {}).setdefault(
            profile_code,
            {"allow_valid_with_conditions": profile_code == "PYP-INV-SELECT", "requirements": []},
        )
        current = {str(item.get("evidence_type")): deepcopy(item) for item in profile.get("requirements", [])}
        desired_rows = [
            deepcopy(item)
            for item in DEFAULT_POLICY["gate_profiles"][profile_code]["requirements"]
            if item.get("evidence_type") in {"BUSINESS_CASE_READINESS", "ECONOMIC_FINANCIAL_READINESS"}
        ]
        desired_rows.extend(
            [
                _requirement(
                    "CONTRACTING_STRATEGY_READINESS",
                    "A" if ffa else "B",
                    scope="EACH_PROJECT",
                    blocking=ffa,
                    provider_key="COMMERCIAL_READINESS_PROVIDER",
                    validity=365,
                    coverage=100 if ffa else 80,
                    rationale=(
                        "FFA consumes the governed Commercial & Contracting Strategy readiness provider."
                        if ffa
                        else "Selection accepts governed or controlled stage-appropriate commercial evidence."
                    ),
                    order=100,
                ),
                _requirement(
                    "BENEFITS_PLAN_READINESS",
                    "A" if ffa else "B",
                    scope="EACH_PROJECT",
                    blocking=ffa,
                    provider_key="BENEFITS_READINESS_PROVIDER",
                    validity=365,
                    coverage=100 if ffa else 80,
                    rationale=(
                        "FFA consumes the governed Benefits Plan readiness and stable BEN-* references."
                        if ffa
                        else "Selection accepts stage-appropriate Benefits readiness without forcing FFA depth."
                    ),
                    order=105,
                ),
            ]
        )
        desired = {str(item.get("evidence_type")): deepcopy(item) for item in desired_rows}
        current.update(desired)
        profile["requirements"] = sorted(current.values(), key=lambda item: int(item.get("order", 0)))
    updated["release_status"] = "DRAFT"
    return updated


class InvestmentEvidencePolicyService:
    def __init__(
        self,
        db: Session,
        tenant_id: int,
        actor_id: int,
        context: EnterprisePermissionContext | None = None,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.context = context

    def ensure_seed(self) -> None:
        exists = self.db.scalar(
            select(AdminConfiguration.id).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.code == DEFAULT_CODE,
            )
        )
        if exists is not None:
            return
        content = deepcopy(DEFAULT_POLICY)
        record = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code=DEFAULT_CODE,
            name="Investment Decision Evidence Policy",
            description="Starter A/B/C evidence matrix. DRAFT only; explicit review and publication required.",
            status="draft",
            revision=1,
            version=1,
            content_json=content,
            content_hash=_hash(content),
            created_by_user_id=self.actor_id,
        )
        self.db.add(record)
        self._event("investment_evidence_policy.seeded_as_draft", "AdminConfiguration", None, {})
        self.db.commit()

    def overview(self) -> PolicyOverviewOut:
        records = self.configurations()
        providers = self.providers()
        effective = self._effective_configuration(None)
        content = effective.content_json if effective else DEFAULT_POLICY
        return PolicyOverviewOut(
            configurations=[PolicyConfigurationOut.model_validate(item) for item in records],
            providers=providers,
            missing_providers=self._missing_provider_analysis(content),
            required_adr_decisions=self.adr_decisions(content),
            allowed_actions=[
                "can_view_evidence_policy",
                "can_clone_evidence_policy",
                "can_edit_evidence_policy",
                "can_preview_evidence_policy",
                "can_publish_evidence_policy",
                "can_view_provider_registry",
                "can_view_missing_provider_analysis",
            ],
            boundaries=[
                "NO_CLASS_A_TO_CLASS_B_FALLBACK",
                "NO_SILENT_POLICY_UPGRADE",
                "NO_BUSINESS_CASE_OR_FIN_RECALCULATION",
                "NO_RISK_PERMIT_CONTRACTING_EXECUTION_OR_SCHEDULE_ENGINE",
                "NO_INVESTMENT_DECISION_OR_FID",
                "NO_PROJECT_INITIALIZATION_ACTIVATION_OR_EXECUTION",
            ],
            release_contract=self._release_contract(effective, content),
        )

    def configurations(self) -> list[AdminConfiguration]:
        self.ensure_seed()
        return list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                )
                .order_by(AdminConfiguration.revision.desc(), AdminConfiguration.id.desc())
            ).all()
        )

    def providers(self) -> list[ProviderOut]:
        return [self._provider_out(value) for value in PROVIDER_REGISTRY.values()]

    def provider(self, provider_key: str) -> ProviderOut:
        value = PROVIDER_REGISTRY.get(provider_key)
        if value is None:
            raise HTTPException(status_code=404, detail="Investment evidence provider not found")
        return self._provider_out(value)

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id, lock=True)
        self._check_version(source.version, expected_version)
        revision = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(AdminConfiguration.revision), 0)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                        AdminConfiguration.code == source.code,
                    )
                )
                or 0
            )
            + 1
        )
        clone = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code=source.code,
            name=f"{source.name} · revision {revision}",
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=deepcopy(source.content_json),
            content_hash=source.content_hash,
            created_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._event("investment_evidence_policy.cloned", "AdminConfiguration", clone.id, {})
        self.db.commit()
        return clone

    def clone_gate07j_evid2_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        """Idempotently clone a source revision into an EVID-2 DRAFT."""

        source = self._configuration(configuration_id, lock=True)
        self._check_version(source.version, expected_version)
        if source.status != "published":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PUBLISHED_POLICY_REQUIRED",
                    "message": (
                        "Gate 07J-EVID-2 revisions must be cloned from an immutable published evidence policy."
                    ),
                },
            )
        marker = {
            "source_policy_id": source.id,
            "source_policy_revision": source.revision,
            "source_policy_hash": source.content_hash,
        }
        records = self.db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.code == source.code,
                AdminConfiguration.status == "draft",
            )
        ).all()
        duplicate = next(
            (item for item in records if dict(item.content_json.get("_gate07j_evid2") or {}) == marker),
            None,
        )
        if duplicate is not None:
            return duplicate
        revision = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(AdminConfiguration.revision), 0)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                        AdminConfiguration.code == source.code,
                    )
                )
                or 0
            )
            + 1
        )
        content = gate07j_evid2_policy_update(source.content_json)
        content["_gate07j_evid2"] = marker
        clone = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code=source.code,
            name=f"{source.name} · Gate 07J-EVID-2 revision {revision}",
            description=(
                "Governed Gate evidence policy with a separate decision-criteria layer; "
                "DRAFT until explicitly previewed and published."
            ),
            status="draft",
            revision=revision,
            version=1,
            content_json=content,
            content_hash=_hash(content),
            created_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._event("investment_evidence_policy.cloned", "AdminConfiguration", clone.id, marker)
        self._event("gate_policy.cloned", "AdminConfiguration", clone.id, marker)
        self._event(
            "gate_criterion.created",
            "AdminConfiguration",
            clone.id,
            {
                "profile_codes": ["PYP-INV-SELECT", "PYP-FFA"],
                "criterion_count": sum(
                    len(items) for items in content["decision_criterion_policy"].get("criteria_by_profile", {}).values()
                ),
            },
        )
        self.db.commit()
        return clone

    def update_configuration(
        self,
        configuration_id: int,
        expected_version: int,
        name: str,
        description: str,
        content: dict,
    ) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_POLICY_IMMUTABLE"})
        self._validate_policy(content)
        record.name = name
        record.description = description
        record.content_json = deepcopy(content)
        record.content_hash = _hash(content)
        record.version += 1
        record.updated_at = utc_now()
        self._event("investment_evidence_policy.updated", "AdminConfiguration", record.id, {})
        if content.get("decision_criterion_policy"):
            self._event(
                "gate_criterion.changed",
                "AdminConfiguration",
                record.id,
                {"criterion_policy_hash": _hash(content["decision_criterion_policy"])},
            )
        self.db.commit()
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        if record.status == "published":
            return record
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "POLICY_NOT_DRAFT"})
        content = deepcopy(record.content_json)
        if not content.get("effective_from"):
            content["effective_from"] = utc_now().isoformat()
        self._validate_policy(content)
        effective_from = _effective_datetime(content)
        scope = dict(record.content_json.get("scope", {}))
        for previous in self.configurations():
            if (
                previous.id != record.id
                and previous.status == "published"
                and previous.code == record.code
                and dict(previous.content_json.get("scope", {})) == scope
                and effective_from <= utc_now()
            ):
                previous.status = "superseded"
                previous.version += 1
                self._event("investment_evidence_policy.superseded", "AdminConfiguration", previous.id, {})
        is_evid2 = content.get("policy_update") == "GATE07J_EVID_2"
        content["release_status"] = EVID2_VALIDATED_RELEASE if is_evid2 else VALIDATED_RELEASE
        record.content_json = content
        record.content_hash = _hash(content)
        record.status = "published"
        record.published_at = utc_now()
        record.version += 1
        self._event(
            "investment_evidence_policy.published",
            "AdminConfiguration",
            record.id,
            {
                "policy_hash": record.content_hash,
                "effective_from": content["effective_from"],
                "evidence_types": sorted(
                    {
                        str(item.get("evidence_type"))
                        for profile in content.get("gate_profiles", {}).values()
                        for item in profile.get("requirements", [])
                        if item.get("evidence_type")
                    }
                ),
            },
        )
        if content.get("decision_criterion_policy"):
            self._event(
                "gate_policy.published",
                "AdminConfiguration",
                record.id,
                {
                    "policy_revision": record.revision,
                    "policy_hash": record.content_hash,
                    "criterion_policy_hash": _hash(content["decision_criterion_policy"]),
                },
            )
        self.db.commit()
        return record

    def preview(
        self,
        *,
        portfolio_id: int | None,
        gate_profile_code: str,
        project_ids: list[int],
        configuration_id: int | None,
        content_override: dict | None,
        project_type_code: str | None = None,
        governance_model: str | None = None,
    ) -> PolicyPreviewOut:
        record = self._configuration(configuration_id) if configuration_id else None
        content = deepcopy(
            content_override if content_override is not None else record.content_json if record else DEFAULT_POLICY
        )
        self._validate_policy(content)
        projects, contract = self._preview_projects(portfolio_id, project_ids)
        matrix = self._effective_matrix(
            content,
            gate_profile_code,
            projects,
            preview_project_type=project_type_code,
            preview_governance_model=governance_model,
        )
        evidence = self._current_evidence(matrix, portfolio_id, contract)
        missing = self._missing_provider_analysis(content, gate_profile_code, projects)
        blockers = sorted(
            {blocker for item in evidence for blocker in item.get("blockers", []) if item.get("blocking")}
            | {
                "SOURCE_PROVIDER_MISSING"
                for item in missing
                if item.get("blocking") and item.get("gap_status") == "PROVIDER_MISSING"
            }
        )
        warnings = sorted({warning for item in evidence for warning in item.get("warnings", [])})
        class_counts = {code: sum(item["classification"] == code for item in matrix) for code in CLASSIFICATIONS}
        blocking_missing = sorted(
            {item["evidence_type"] for item in missing if item.get("blocking") and item["gap_status"] != "NONE"}
        )
        next_step = self._next_development(missing)
        relevant_types = {"BUSINESS_CASE_READINESS", "ECONOMIC_FINANCIAL_READINESS"}
        effective_classifications = {
            evidence_type: sorted(
                {str(item["classification"]) for item in matrix if item["evidence_type"] == evidence_type}
            )
            for evidence_type in relevant_types
        }
        required_coverage = {
            evidence_type: next(
                (
                    float(item["coverage_requirement"])
                    for item in matrix
                    if item["evidence_type"] == evidence_type and item.get("coverage_requirement") is not None
                ),
                None,
            )
            for evidence_type in relevant_types
        }
        source_availability = {
            evidence_type: next(
                (
                    str(item.get("provider_status") or "MISSING")
                    for item in matrix
                    if item["evidence_type"] == evidence_type
                ),
                "NOT_CONFIGURED",
            )
            for evidence_type in relevant_types
        }
        source_readiness = {
            evidence_type: sorted(
                {
                    str(item.get("status") or "NOT_EVALUATED")
                    for item in evidence
                    if item["evidence_type"] == evidence_type
                }
            )
            for evidence_type in relevant_types
        }
        source_current = {
            evidence_type: sorted(
                {
                    bool(item["source_current"])
                    for item in evidence
                    if item["evidence_type"] == evidence_type and item.get("source_current") is not None
                }
            )
            for evidence_type in relevant_types
        }
        would_be_ready = not blockers and all(
            not item.get("blocking") or item.get("status") in {"VALID", "NOT_REQUIRED"} for item in evidence
        )
        criterion_policy = decision_criterion_policy(content) if content.get("decision_criterion_policy") else {}
        decision_criteria = deepcopy(criterion_policy.get("criteria_by_profile", {}).get(gate_profile_code, []))
        criterion_issues = validate_criterion_policy(content, set(EVIDENCE_TYPES)) if criterion_policy else []
        return PolicyPreviewOut(
            policy={
                "id": record.id if record else None,
                "revision": record.revision if record else 1,
                "hash": _hash(content),
                "status": record.status if record else "draft",
                "code": content.get("policy_code"),
                "effective_from": content.get("effective_from"),
            },
            gate_profile_code=gate_profile_code,
            portfolio_workspace_id=portfolio_id,
            project_contexts=[self._project_context(item) for item in projects],
            effective_matrix=matrix,
            provider_registry_snapshot=self.providers(),
            current_evidence_status=evidence,
            missing_providers=missing,
            available_provider_count=sum(
                item.status == "AVAILABLE" and item.contract_valid for item in self.providers()
            ),
            missing_required_provider_count=len(blocking_missing),
            class_A_count=class_counts["A"],
            class_B_count=class_counts["B"],
            class_C_count=class_counts["C"],
            blocking_missing_sources=blocking_missing,
            warnings=warnings,
            blockers=blockers,
            effective_classifications=effective_classifications,
            required_coverage=required_coverage,
            source_availability=source_availability,
            source_readiness=source_readiness,
            source_current=source_current,
            decision_criterion_policy=criterion_policy,
            decision_criteria=decision_criteria,
            criterion_validation_issues=criterion_issues,
            decision_criterion_taxonomy=list(DECISION_CRITERION_TYPES),
            controlled_operators=list(CONTROLLED_OPERATORS),
            evidence_quality_states=list(EVIDENCE_QUALITY_STATES),
            would_gate07j_be_ready=would_be_ready,
            would_be_ready_for_investment_gate=would_be_ready,
            recommended_next_development=next_step,
            can_design_investment_decision_gate=not blocking_missing,
            can_enter_fid=False,
            persisted=False,
            final_output=(
                EVID2_READY_OUTPUT
                if content.get("policy_update") == "GATE07J_EVID_2" and would_be_ready
                else READY_OUTPUT
            ),
        )

    def missing_providers(self, gate_profile_code: str | None = None, portfolio_id: int | None = None) -> list[dict]:
        record = self._effective_configuration(self._portfolio(portfolio_id) if portfolio_id else None)
        content = record.content_json if record else DEFAULT_POLICY
        projects, _ = self._preview_projects(portfolio_id, [])
        return self._missing_provider_analysis(content, gate_profile_code, projects)

    def published_snapshot(
        self, portfolio_id: int, gate_profile_code: str, selected_project_ids: list[int]
    ) -> dict | None:
        workspace = self._portfolio(portfolio_id)
        record = self._effective_configuration(workspace)
        if record is None:
            return None
        projects = self._projects(selected_project_ids)
        matrix = self._effective_matrix(record.content_json, gate_profile_code, projects)
        profile = deepcopy(record.content_json["gate_profiles"][gate_profile_code])
        requirements = deepcopy(profile["requirements"])
        for requirement in requirements:
            resolutions = {
                str(item["project_workspace_id"]): {
                    key: deepcopy(value)
                    for key, value in item.items()
                    if key
                    not in {
                        "gate_profile_code",
                        "project_workspace_id",
                        "project_type",
                        "governance_model",
                        "provider_status",
                        "gap_status",
                    }
                }
                for item in matrix
                if item["evidence_type"] == requirement["evidence_type"]
                and item.get("project_workspace_id") is not None
            }
            if resolutions:
                requirement["resolved_projects"] = resolutions
        raw_criterion_policy = record.content_json.get("decision_criterion_policy")
        criterion_policy = decision_criterion_policy(record.content_json) if raw_criterion_policy else {}
        criteria = deepcopy(criterion_policy.get("criteria_by_profile", {}).get(gate_profile_code, []))
        criterion_policy_hash = (
            _hash(
                {
                    "policy": criterion_policy,
                    "gate_profile_code": gate_profile_code,
                    "criteria": criteria,
                }
            )
            if criterion_policy
            else None
        )
        return {
            "policy_id": record.id,
            "policy_revision": record.revision,
            "policy_hash": record.content_hash,
            "gate_profile_code": gate_profile_code,
            "requirements": requirements,
            "effective_matrix": matrix,
            "provider_registry_snapshot": [item.model_dump(mode="json") for item in self.providers()],
            "project_contexts": [self._project_context(item) for item in projects],
            "decision_criterion_policy": (
                {
                    "policy_id": record.id,
                    "policy_revision": record.revision,
                    "policy_hash": criterion_policy_hash,
                    "effective_from": criterion_policy.get("effective_from"),
                    "criterion_types": deepcopy(criterion_policy.get("criterion_types", [])),
                    "controlled_operators": deepcopy(criterion_policy.get("controlled_operators", [])),
                    "evidence_quality_states": deepcopy(criterion_policy.get("evidence_quality_states", [])),
                    "tailoring_dimensions": deepcopy(criterion_policy.get("tailoring_dimensions", [])),
                    "formal_decision_authority": "GATE07K",
                    "portfolio_rank_authority": "PORTFOLIO",
                    "new_round_policy": criterion_policy.get("new_round_policy"),
                    "criteria": criteria,
                }
                if criterion_policy
                else {}
            ),
            "captured_at": utc_now().isoformat(),
            "final_output": READY_OUTPUT,
            "can_enter_fid": False,
        }

    def resolve_governed_payload(
        self,
        requirement: dict,
        contract: dict,
        scope_id: int | None,
    ) -> tuple[dict | None, str | None]:
        provider_key = requirement.get("provider_key")
        provider = PROVIDER_REGISTRY.get(str(provider_key)) if provider_key else None
        if provider is None or provider.get("status") != "AVAILABLE":
            return None, "SOURCE_PROVIDER_MISSING"
        provider_out = self._provider_out(provider)
        if not provider_out.contract_valid:
            return None, "PROVIDER_CONTRACT_INVALID"
        scope = str(requirement.get("scope"))
        if not self._scope_supported(provider, scope):
            return None, "SCOPE_UNSUPPORTED"
        try:
            payload = self._provider_payload(str(provider_key), contract, scope, scope_id)
        except HTTPException:
            payload = None
        if payload is None:
            return None, "SOURCE_EVIDENCE_UNAVAILABLE"
        # One governed source may expose several explicitly registered evidence
        # aliases (for example FEL also supplies definition, PDRI and estimate
        # maturity).  Normalize the contract to the effective requirement while
        # retaining the original source payload in evidence_refs.
        payload["evidence_type"] = str(requirement["evidence_type"])
        issues = self.validate_provider_contract(payload)
        if issues:
            return None, "PROVIDER_CONTRACT_INVALID"
        if not payload["source_current"]:
            return payload, "SOURCE_STALE"
        minimum = str(requirement.get("minimum_readiness_status") or "").upper()
        if minimum and str(payload["readiness_status"]).upper() not in {minimum, "VALID", "READY"}:
            return payload, "MINIMUM_READINESS_NOT_MET"
        return payload, None

    @staticmethod
    def validate_provider_contract(payload: dict) -> list[str]:
        missing = sorted(field for field in REQUIRED_PROVIDER_FIELDS if field not in payload)
        if not payload.get("evidence_hash"):
            missing.append("evidence_hash:empty")
        if not isinstance(payload.get("source_current"), bool):
            missing.append("source_current:not_boolean")
        if not isinstance(payload.get("warnings"), list) or not isinstance(payload.get("blockers"), list):
            missing.append("warnings_or_blockers:not_list")
        return sorted(set(missing))

    def adr_decisions(self, content: dict) -> list[dict]:
        required = {
            "RISK_READINESS",
            "PERMIT_READINESS",
            "CONTRACTING_STRATEGY_READINESS",
            "EXECUTION_PLAN_READINESS",
            "SCHEDULE_MATURITY",
            "COST_ESTIMATE_MATURITY",
            "ENVIRONMENTAL_SOCIAL_READINESS",
            "LAND_ACCESS_READINESS",
        }
        decisions: list[dict] = []
        for profile_code, profile in content.get("gate_profiles", {}).items():
            for row in profile.get("requirements", []):
                if row.get("evidence_type") not in required:
                    continue
                provider = PROVIDER_REGISTRY.get(str(row.get("provider_key") or ""))
                decisions.append(
                    {
                        "evidence_type": row["evidence_type"],
                        "gate_profile": profile_code,
                        "project_type_applicability": row.get("project_type_filter", ["*"]),
                        "classification": row["classification"],
                        "provider": row.get("provider_key"),
                        "provider_status": provider.get("status") if provider else "NOT_REQUIRED_OR_MANUAL",
                        "scope": row["scope"],
                        "blocking": row["blocking"],
                        "validity": row.get("validity_period_days"),
                        "coverage": row.get("coverage_requirement"),
                        "rationale": row.get("rationale"),
                        "next_action": self._recommended_action(row, provider),
                    }
                )
        return decisions

    def _current_evidence(self, matrix: list[dict], portfolio_id: int | None, contract: dict | None) -> list[dict]:
        output: list[dict] = []
        for requirement in matrix:
            item = {
                "requirement_key": requirement["requirement_key"],
                "evidence_type": requirement["evidence_type"],
                "classification": requirement["classification"],
                "project_workspace_id": requirement.get("project_workspace_id"),
                "blocking": requirement["blocking"],
                "provider_key": requirement.get("provider_key"),
                "warnings": [],
                "blockers": [],
            }
            if requirement["classification"] == "C":
                item.update(status="NOT_REQUIRED", reason="CLASS_C")
            elif requirement["classification"] == "B" and not requirement.get("provider_key"):
                item.update(status="MANUAL_EVIDENCE_REQUIRED", reason="GOVERNED_EVIDENCE_SUFFICIENT")
                if requirement["blocking"]:
                    item["blockers"] = ["MANUAL_EVIDENCE_NOT_VALIDATED"]
                else:
                    item["warnings"] = ["MANUAL_EVIDENCE_NOT_VALIDATED"]
            elif portfolio_id is None or contract is None:
                provider = PROVIDER_REGISTRY.get(str(requirement.get("provider_key") or ""))
                if provider and provider.get("status") == "AVAILABLE":
                    item.update(status="PROVIDER_AVAILABLE", reason="SOURCE_NOT_EVALUATED")
                elif requirement["classification"] == "A":
                    item.update(status="SOURCE_PROVIDER_MISSING", reason="NO_SILENT_FALLBACK")
                    item["blockers"] = ["SOURCE_PROVIDER_MISSING"]
                else:
                    item.update(status="MANUAL_EVIDENCE_REQUIRED", reason="GOVERNED_EVIDENCE_SUFFICIENT")
            else:
                payload, error = self.resolve_governed_payload(
                    requirement, contract, requirement.get("project_workspace_id")
                )
                if payload and not error:
                    item.update(
                        status="VALID",
                        reason="GOVERNED_SOURCE",
                        source_hash=payload["evidence_hash"],
                        source_current=payload["source_current"],
                        as_of_date=payload["as_of_date"],
                    )
                    item["warnings"] = payload["warnings"]
                    item["blockers"] = payload["blockers"]
                elif requirement["classification"] == "B":
                    item.update(status="MANUAL_EVIDENCE_REQUIRED", reason=error or "GOVERNED_EVIDENCE_SUFFICIENT")
                    if requirement["blocking"]:
                        item["blockers"] = ["MANUAL_EVIDENCE_NOT_VALIDATED"]
                    else:
                        item["warnings"] = ["MANUAL_EVIDENCE_NOT_VALIDATED"]
                else:
                    item.update(status=error or "SOURCE_EVIDENCE_UNAVAILABLE", reason="NO_SILENT_FALLBACK")
                    item["blockers"] = [error or "SOURCE_EVIDENCE_UNAVAILABLE"]
            output.append(item)
        return output

    def _provider_payload(self, provider_key: str, contract: dict, scope: str, scope_id: int | None) -> dict | None:
        now = utc_now().isoformat()
        if provider_key == "GATE07I_PORTFOLIO_RECOMMENDATION":
            if not contract.get("portfolio_recommendation_ready"):
                return None
            return self._normalized_provider_payload(
                evidence_type="PORTFOLIO_RECOMMENDATION",
                scope=scope,
                readiness_status="READY",
                source_current=True,
                evidence_hash=str(contract.get("recommendation_hash") or ""),
                as_of_date=now,
                warnings=list(contract.get("warnings", [])),
                blockers=list(contract.get("blockers", [])),
                source_module="PORTFOLIO_SCENARIO_CONVERGENCE",
                source_record_id=str(contract.get("convergence_id")),
                summary="Current governed Gate 07I portfolio recommendation.",
                evidence_refs=[deepcopy(contract)],
            )
        if provider_key == "GATE07G_BUDGET_FEASIBILITY":
            source = contract.get("budget_scenario_ref")
            if not source or not source.get("hash"):
                return None
            return self._normalized_provider_payload(
                evidence_type="BUDGET_FEASIBILITY",
                scope=scope,
                readiness_status="READY",
                source_current=True,
                evidence_hash=str(source["hash"]),
                as_of_date=now,
                warnings=[],
                blockers=[],
                source_module="PORTFOLIO_BUDGET",
                source_record_id=str(source["id"]),
                summary=json.dumps(contract.get("budget_feasibility_summary", {}), default=str),
                evidence_refs=[
                    {"scenario": deepcopy(source), "detail": deepcopy(contract.get("budget_feasibility_summary", {}))}
                ],
            )
        if provider_key == "GATE07H_RESOURCE_FEASIBILITY":
            source = contract.get("resource_scenario_ref")
            if not source or not source.get("hash"):
                return None
            return self._normalized_provider_payload(
                evidence_type="RESOURCE_FEASIBILITY",
                scope=scope,
                readiness_status="READY",
                source_current=True,
                evidence_hash=str(source["hash"]),
                as_of_date=now,
                warnings=[],
                blockers=[],
                source_module="PORTFOLIO_RESOURCE",
                source_record_id=str(source["id"]),
                summary=json.dumps(contract.get("resource_feasibility_summary", {}), default=str),
                evidence_refs=[
                    {"scenario": deepcopy(source), "detail": deepcopy(contract.get("resource_feasibility_summary", {}))}
                ],
            )
        if provider_key == "GATE07J_FEL_PROJECT_DEFINITION" and scope_id is not None:
            governed = ProjectDefinitionService(
                self.db, self.tenant_id, self.actor_id, self.context
            ).investment_gate_evidence(scope_id)
            if not governed.can_supply_investment_gate_evidence:
                return None
            value = governed.model_dump(mode="json")
            return self._normalized_provider_payload(
                evidence_type=str(governed.evidence_type),
                scope=scope,
                readiness_status=str(governed.readiness_status),
                source_current=bool(governed.source_current),
                evidence_hash=str(governed.definition_readiness_hash),
                as_of_date=governed.assessment_date.isoformat() if governed.assessment_date else now,
                warnings=[],
                blockers=[] if governed.minimum_requirement_met else ["MINIMUM_READINESS_NOT_MET"],
                source_module="PROJECT_DEFINITION_FEL",
                source_record_id=str(governed.assessment_id or scope_id),
                summary=f"Governed {governed.FEL_stage_code or 'FEL'} definition evidence.",
                evidence_refs=[
                    value | {"fel_stage": governed.FEL_stage_code, "evidence_hash": governed.definition_readiness_hash}
                ],
            )
        if provider_key == "GATE07J_FUND_FUNDING_READINESS":
            governed = FundsManagerService(
                self.db, self.tenant_id, self.actor_id, self.context
            ).investment_gate_evidence(int(contract["portfolio_workspace_id"]))
            if not governed.can_supply_investment_gate_evidence:
                return None
            value = governed.model_dump(mode="json")
            return self._normalized_provider_payload(
                evidence_type="FUNDING_READINESS",
                scope=scope,
                readiness_status=str(governed.funding_readiness_status),
                source_current=bool(governed.source_current),
                evidence_hash=str(governed.funding_readiness_hash),
                as_of_date=now,
                warnings=[],
                blockers=[] if governed.can_supply_investment_gate_evidence else ["FUNDING_NOT_READY"],
                source_module="FUNDS_MANAGER",
                source_record_id=str(governed.snapshot_id or governed.funding_readiness_hash),
                summary=f"Governed funding readiness with {governed.confirmed_coverage_percent}% confirmed coverage.",
                evidence_refs=[value],
            )
        if provider_key == "RISK_READINESS_PROVIDER":
            governed = RiskReadinessService(
                self.db, self.tenant_id, self.actor_id, self.context
            ).investment_gate_evidence(int(contract["portfolio_workspace_id"]))
            value = governed.model_dump(mode="json")
            return self._normalized_provider_payload(
                evidence_type="RISK_READINESS",
                scope=scope,
                readiness_status=str(governed.readiness_status),
                source_current=bool(governed.source_current),
                evidence_hash=str(governed.risk_readiness_hash),
                as_of_date=governed.assessment_date.isoformat() if governed.assessment_date else now,
                warnings=list(governed.warnings),
                blockers=list(governed.blockers),
                source_module="RISK_READINESS",
                source_record_id=str(governed.aggregate_reference or governed.risk_readiness_hash),
                summary=(
                    "Governed risk readiness: "
                    f"{governed.valid_project_count}/{governed.required_project_count} projects, "
                    f"{governed.coverage_percent}% coverage."
                ),
                evidence_refs=[value],
            )
        if provider_key == "PERMIT_READINESS_PROVIDER":
            service = PermitReadinessService(self.db, self.tenant_id, self.actor_id, self.context)
            governed = (
                service.project_investment_gate_evidence(scope_id)
                if scope_id is not None
                else service.investment_gate_evidence(int(contract["portfolio_workspace_id"]))
            )
            value = governed.model_dump(mode="json")
            return self._normalized_provider_payload(
                evidence_type="PERMIT_READINESS",
                scope=scope,
                readiness_status=str(governed.readiness_status),
                source_current=bool(governed.source_current),
                evidence_hash=str(governed.permit_readiness_hash),
                as_of_date=governed.assessment_date.isoformat() if governed.assessment_date else now,
                warnings=list(governed.warnings),
                blockers=list(governed.blockers),
                source_module="PERMIT_READINESS",
                source_record_id=str(governed.aggregate_reference or governed.assessment_id or scope_id),
                summary=(
                    "Governed permit readiness: "
                    f"{governed.valid_project_count}/{governed.required_project_count} projects, "
                    f"{governed.coverage_percent}% coverage."
                ),
                evidence_refs=[value],
            )
        if provider_key == "BUSINESS_CASE_READINESS_PROVIDER" and scope_id is not None:
            business_service = BusinessCaseService(self.db, self.tenant_id, self.actor_id, self.context)
            case = business_service.by_project(scope_id)
            revision = case.current_revision
            if revision is None:
                return None
            readiness = business_service.readiness(case.id)
            warnings = list(readiness.warnings)
            blockers = list(readiness.blockers)
            source_current = bool(readiness.source_current and getattr(revision, "source_current", True))
            five_case_readiness = deepcopy(getattr(revision, "five_case_readiness_json", {}) or {})
            five_case_status = five_case_readiness.get("overall_business_case_readiness")
            # Legacy and policy-not-applicable revisions retain the v1 provider
            # behavior.  For an applicable BC-5C revision, Five Case overall
            # readiness is authoritative.
            overall_status = readiness.status if five_case_status in {None, "NOT_APPLICABLE"} else five_case_status
            if revision.status != "COMPLETED":
                blockers.append("BUSINESS_CASE_REVISION_NOT_COMPLETED")
            if overall_status != "READY":
                blockers.append(f"BUSINESS_CASE_OVERALL_NOT_READY:{overall_status}")
            if revision.material_change_status == "MATERIAL_CHANGE_REVIEW_REQUIRED":
                blockers.append("MATERIAL_CHANGE_REVIEW_REQUIRED")
            if any(
                bool(item.get("blocking", True))
                and str(item.get("status", "OPEN")).upper() not in {"CLOSED", "RESOLVED"}
                for item in revision.unresolved_concerns_json
            ):
                blockers.append("BUSINESS_CASE_UNRESOLVED_BLOCKING_CONCERN")
            try:
                financial_service = EconomicFinancialModelService(self.db, self.tenant_id, self.actor_id, self.context)
                financial_model = financial_service.by_project(scope_id)
                financial = financial_service.provider_evidence(financial_model.id)
                if revision.economic_financial_model_hash != financial.model_hash:
                    source_current = False
                    blockers.append("BUSINESS_CASE_FIN_REFERENCE_STALE")
            except HTTPException:
                financial = None
            decision_snapshot = self.db.scalar(
                select(BusinessCaseDecisionSnapshot)
                .where(
                    BusinessCaseDecisionSnapshot.tenant_id == self.tenant_id,
                    BusinessCaseDecisionSnapshot.business_case_id == case.id,
                    BusinessCaseDecisionSnapshot.business_case_revision_id == revision.id,
                )
                .order_by(BusinessCaseDecisionSnapshot.created_at.desc())
            )
            status = (
                "STALE"
                if not source_current
                else "READY"
                if (
                    revision.status == "COMPLETED"
                    and readiness.status == "READY"
                    and overall_status == "READY"
                    and not blockers
                )
                else "BLOCKED"
            )
            business_case_hash = str(getattr(revision, "business_case_hash", None) or revision.content_hash)
            source_bundle_hash = str(getattr(revision, "source_bundle_hash", None) or revision.source_snapshot_hash)
            five_case_hash = getattr(revision, "five_case_hash", None)
            can_supply = bool(
                revision.status == "COMPLETED"
                and overall_status == "READY"
                and status == "READY"
                and source_current
                and not blockers
            )
            contract_value = {
                "provider_key": "BUSINESS_CASE_READINESS_PROVIDER",
                "source_module": "BUSINESS_CASE_MANAGER",
                "evidence_type": "BUSINESS_CASE_READINESS",
                "project_workspace_id": scope_id,
                "business_case_id": case.id,
                "business_case_number": case.business_case_number,
                "business_case_revision_id": revision.id,
                "revision_number": revision.revision_number,
                "revision_purpose": revision.purpose,
                "business_case_hash": business_case_hash,
                "business_case_source_hash": revision.source_snapshot_hash,
                "source_bundle_hash": source_bundle_hash,
                "five_case_hash": five_case_hash,
                "five_case_readiness": five_case_readiness,
                "source_references": deepcopy(getattr(revision, "source_references_json", {}) or {}),
                "source_hashes": deepcopy(getattr(revision, "source_hashes_json", {}) or {}),
                "as_of_date": revision.as_of_date.isoformat(),
                "fel_stage_code": revision.fel_stage_code,
                "selected_alternative": dict(revision.recommendation_json or {}).get("selected_alternative"),
                "material_change_status": revision.material_change_status,
                "readiness_status": status,
                "source_current": source_current,
                "decision_snapshot_reference": (
                    {
                        "id": decision_snapshot.id,
                        "type": decision_snapshot.snapshot_type,
                        "hash": decision_snapshot.snapshot_hash,
                    }
                    if decision_snapshot
                    else None
                ),
                "warnings": sorted(set(warnings)),
                "blockers": sorted(set(blockers)),
                "can_supply_investment_gate_evidence": can_supply,
            }
            return self._normalized_provider_payload(
                evidence_type="BUSINESS_CASE_READINESS",
                scope=scope,
                readiness_status=status,
                source_current=source_current,
                evidence_hash=business_case_hash,
                as_of_date=revision.as_of_date.isoformat(),
                warnings=contract_value["warnings"],
                blockers=contract_value["blockers"],
                source_module="BUSINESS_CASE_MANAGER",
                source_record_id=str(revision.id),
                summary=(
                    f"Governed Business Case {case.business_case_number} revision {revision.revision_number}; "
                    f"readiness {status}."
                ),
                evidence_refs=[contract_value],
            )
        if provider_key == "ECONOMIC_FINANCIAL_READINESS_PROVIDER" and scope_id is not None:
            service = EconomicFinancialModelService(self.db, self.tenant_id, self.actor_id, self.context)
            model = service.by_project(scope_id)
            governed = service.provider_evidence(model.id)
            value = governed.model_dump(mode="json")
            return self._normalized_provider_payload(
                evidence_type="ECONOMIC_FINANCIAL_READINESS",
                scope=scope,
                readiness_status=str(governed.overall_readiness),
                source_current=bool(governed.source_current),
                evidence_hash=str(governed.model_hash),
                as_of_date=governed.as_of_date.isoformat(),
                warnings=list(governed.warnings),
                blockers=list(governed.blockers),
                source_module="ECONOMIC_FINANCIAL_MODEL",
                source_record_id=str(governed.model_version_id),
                summary=(
                    f"Governed {governed.model_type} economic-financial model; "
                    f"funding reconciliation {governed.funding_reconciliation_status}."
                ),
                evidence_refs=[value],
            )
        if provider_key == "BENEFITS_READINESS_PROVIDER" and scope_id is not None:
            governed = StrategicBenefitsService(self.db, self.tenant_id, self.actor_id, self.context).provider_evidence(
                scope_id
            )
            value = governed.model_dump(mode="json")
            return self._normalized_provider_payload(
                evidence_type="BENEFITS_PLAN_READINESS",
                scope=scope,
                readiness_status=str(governed.overall_benefits_readiness),
                source_current=bool(governed.source_current),
                evidence_hash=str(governed.benefits_plan_hash),
                as_of_date=governed.as_of_date.isoformat(),
                warnings=list(governed.warnings),
                blockers=list(governed.blockers),
                source_module="STRATEGIC_BENEFITS_PLAN",
                source_record_id=str(governed.plan_version_id),
                summary=(
                    f"Governed Strategic Benefits Plan {governed.plan_number} "
                    f"version {governed.plan_version_number}; readiness "
                    f"{governed.overall_benefits_readiness}."
                ),
                evidence_refs=[value],
            )
        if provider_key == "COMMERCIAL_READINESS_PROVIDER" and scope_id is not None:
            governed = CommercialStrategyService(
                self.db, self.tenant_id, self.actor_id, self.context
            ).provider_evidence(scope_id)
            value = governed.model_dump(mode="json")
            return self._normalized_provider_payload(
                evidence_type="COMMERCIAL_READINESS",
                scope=scope,
                readiness_status=str(governed.overall_commercial_readiness),
                source_current=bool(governed.source_current),
                evidence_hash=str(governed.commercial_strategy_hash),
                as_of_date=governed.as_of_date.isoformat(),
                warnings=list(governed.warnings),
                blockers=list(governed.blockers),
                source_module="COMMERCIAL_CONTRACTING_STRATEGY",
                source_record_id=str(governed.version_id),
                summary=(
                    f"Governed commercial strategy {governed.strategy_number} "
                    f"version {governed.version_number}; readiness "
                    f"{governed.overall_commercial_readiness}."
                ),
                evidence_refs=[value],
            )
        if provider_key == "BASIC_DATA_READINESS_PROVIDER" and scope_id is not None:
            # Keep the dependency lazy: Basic Data consumes the existing FEL
            # service and quality vocabulary, never this Gate's write workflow.
            from app.modules.basic_data.service import BasicDataService

            value = BasicDataService(self.db, self.tenant_id, self.actor_id, self.context).provider_evidence(scope_id)
            if hasattr(value, "model_dump"):
                value = value.model_dump(mode="json")
            if not value or value.get("status") != "AVAILABLE" or not value.get("source_current"):
                return None
            return self._normalized_provider_payload(
                evidence_type="BASIC_DATA_READINESS",
                scope=scope,
                readiness_status=str(value["readiness_status"]),
                source_current=True,
                evidence_hash=str(value["evidence_hash"]),
                as_of_date=str(value["as_of_date"]),
                warnings=list(value.get("warnings", [])),
                blockers=list(value.get("blockers", [])),
                source_module="BASIC_DATA_READINESS",
                source_record_id=str(value["assessment_id"]),
                summary=f"Governed Basic Data assessment {value['assessment_id']}; readiness READY.",
                evidence_refs=[value],
            )
        if provider_key == "OWNER_CAPABILITY_READINESS_PROVIDER" and scope_id is not None:
            from app.modules.owner_capability.service import OwnerCapabilityService

            value = OwnerCapabilityService(self.db, self.tenant_id, self.actor_id, self.context).provider_evidence(
                scope_id
            )
            if hasattr(value, "model_dump"):
                value = value.model_dump(mode="json")
            if not value or value.get("status") != "AVAILABLE" or not value.get("source_current"):
                return None
            return self._normalized_provider_payload(
                evidence_type="OWNER_CAPABILITY_READINESS",
                scope=scope,
                readiness_status=str(value["readiness_status"]),
                source_current=True,
                evidence_hash=str(value["evidence_hash"]),
                as_of_date=str(value["as_of_date"]),
                warnings=list(value.get("warnings", [])),
                blockers=list(value.get("blockers", [])),
                source_module="OWNER_CAPABILITY_READINESS",
                source_record_id=str(value["assessment_id"]),
                summary=f"Governed Owner Capability assessment {value['assessment_id']}; readiness READY.",
                evidence_refs=[value],
            )
        if (
            provider_key in {"COST_SOURCE_READINESS_PROVIDER", "SCHEDULE_SOURCE_READINESS_PROVIDER"}
            and scope_id is not None
        ):
            from app.modules.qra_foundation.service import QraFoundationService

            kind = "cost" if provider_key == "COST_SOURCE_READINESS_PROVIDER" else "schedule"
            value = QraFoundationService(self.db, self.tenant_id, self.actor_id, self.context).provider_evidence(
                scope_id, kind=kind
            )
            if hasattr(value, "model_dump"):
                value = value.model_dump(mode="json")
            if not value or value.get("status") != "AVAILABLE" or not value.get("source_current"):
                return None
            return self._normalized_provider_payload(
                evidence_type=f"{kind.upper()}_SOURCE_READINESS",
                scope=scope,
                readiness_status=str(value["readiness_status"]),
                source_current=True,
                evidence_hash=str(value["evidence_hash"]),
                as_of_date=str(value["as_of_date"]),
                warnings=list(value.get("warnings", [])),
                blockers=list(value.get("blockers", [])),
                source_module=f"QRA_{kind.upper()}_SOURCE_READINESS",
                source_record_id=str(value["assessment_id"]),
                summary=f"Governed {kind} source assessment {value['assessment_id']}; readiness READY, not simulation.",
                evidence_refs=[value],
            )
        if provider_key == "QRA_RESULT_PROVIDER" and scope_id is not None:
            from app.modules.qra_engine.service import QraEngineService

            # Caller has already authorized the Gate evaluation and project scope.
            # This internal adapter reads tenant-scoped evidence, never runs QRA.
            value = QraEngineService(self.db, self.tenant_id, self.actor_id).provider_evidence(scope_id)
            if value.get("status") != "AVAILABLE" or not value.get("source_current"):
                return None
            return self._normalized_provider_payload(
                evidence_type="QRA_RESULT",
                scope=scope,
                readiness_status=str(value["readiness"]),
                source_current=True,
                evidence_hash=str(value["evidence_hash"]),
                as_of_date=str(value["as_of"]).split("T")[0],
                warnings=list(value.get("warnings", [])),
                blockers=list(value.get("blockers", [])),
                source_module="QRA_CALCULATION_ENGINE",
                source_record_id=str(value["run_id"]),
                summary=f"Accepted governed QRA run {value['run_number']}; analytical evidence only.",
                evidence_refs=[value],
            )
        return None

    @staticmethod
    def _normalized_provider_payload(**values: Any) -> dict:
        return values

    def _preview_projects(
        self, portfolio_id: int | None, project_ids: list[int]
    ) -> tuple[list[EnterpriseWorkspace], dict | None]:
        contract = None
        resolved_ids = list(project_ids)
        if portfolio_id:
            self._portfolio(portfolio_id)
            try:
                contract = (
                    PortfolioConvergenceService(self.db, self.tenant_id, self.actor_id, self.context)
                    .preparation_contract(portfolio_id)
                    .model_dump(mode="json")
                )
                if not resolved_ids:
                    resolved_ids = list(contract.get("selected_project_set_reference", []))
            except HTTPException:
                contract = None
        return self._projects(resolved_ids), contract

    def _projects(self, project_ids: list[int]) -> list[EnterpriseWorkspace]:
        if not project_ids:
            return []
        records = list(
            self.db.scalars(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id.in_(project_ids),
                    EnterpriseWorkspace.workspace_type_code == "project",
                )
            ).all()
        )
        by_id = {item.id: item for item in records}
        return [by_id[item] for item in project_ids if item in by_id]

    def _effective_matrix(
        self,
        content: dict,
        gate_profile_code: str,
        projects: list[EnterpriseWorkspace],
        *,
        preview_project_type: str | None = None,
        preview_governance_model: str | None = None,
    ) -> list[dict]:
        profile = content.get("gate_profiles", {}).get(gate_profile_code)
        if profile is None:
            raise HTTPException(status_code=422, detail={"code": "GATE_PROFILE_NOT_CONFIGURED"})
        output: list[dict] = []
        for base in sorted(profile.get("requirements", []), key=lambda item: int(item.get("order", 0))):
            scope = base.get("scope")
            targets: list[EnterpriseWorkspace | None] = (
                projects if scope in {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"} and projects else [None]
            )
            for project in targets:
                effective = deepcopy(base)
                if project is not None:
                    effective = self._apply_override(content, gate_profile_code, effective, project)
                    context = self._project_context(project)
                    if context["governance_model"] not in set(content.get("applicable_governance_models", [])):
                        effective.update(
                            classification="C",
                            required=False,
                            blocking=False,
                            provider_required=False,
                            allow_manual_reference=False,
                            rationale="Governance model is outside the published policy applicability.",
                        )
                else:
                    project_type = str(preview_project_type or "").upper() or None
                    governance_model = str(preview_governance_model or "").upper() or None
                    context = {
                        "project_workspace_id": None,
                        "project_type": project_type,
                        "governance_model": governance_model,
                    }
                    if project_type:
                        effective = self._apply_override_values(
                            content,
                            gate_profile_code,
                            effective,
                            project_type,
                            governance_model or "CAPITAL_OWNER",
                        )
                    applicable_models = set(content.get("applicable_governance_models", []))
                    project_models = {self._governance_model(item) for item in projects}
                    outside_policy = bool(projects and applicable_models and not (project_models & applicable_models))
                    if governance_model and governance_model not in applicable_models:
                        outside_policy = True
                    if outside_policy:
                        effective.update(
                            classification="C",
                            required=False,
                            blocking=False,
                            provider_required=False,
                            allow_manual_reference=False,
                            rationale="Recommended Project Set governance is outside policy applicability.",
                        )
                provider = PROVIDER_REGISTRY.get(str(effective.get("provider_key") or ""))
                effective.update(
                    gate_profile_code=gate_profile_code,
                    **context,
                    provider_status=provider.get("status") if provider else "NOT_REQUIRED_OR_MANUAL",
                    gap_status=self._gap_status(effective, provider),
                )
                output.append(effective)
        return output

    def _apply_override(
        self,
        content: dict,
        gate_profile_code: str,
        requirement: dict,
        project: EnterpriseWorkspace,
    ) -> dict:
        return self._apply_override_values(
            content,
            gate_profile_code,
            requirement,
            self._project_type(project),
            self._governance_model(project),
        )

    @staticmethod
    def _apply_override_values(
        content: dict,
        gate_profile_code: str,
        requirement: dict,
        project_type: str,
        governance: str,
    ) -> dict:
        for override in content.get("project_type_overrides", []):
            types = {str(item).upper() for item in override.get("project_type_filter", [])}
            models = {str(item).upper() for item in override.get("governance_model_filter", [])}
            if (
                override.get("gate_profile_code") == gate_profile_code
                and override.get("evidence_type") == requirement.get("evidence_type")
                and ("*" in types or project_type in types)
                and (not models or "*" in models or governance in models)
            ):
                requirement.update(deepcopy(override))
        return requirement

    def _missing_provider_analysis(
        self,
        content: dict,
        gate_profile_code: str | None = None,
        projects: list[EnterpriseWorkspace] | None = None,
    ) -> list[dict]:
        profiles = [gate_profile_code] if gate_profile_code else list(content.get("gate_profiles", {}))
        output: list[dict] = []
        for profile_code in profiles:
            matrix = self._effective_matrix(content, profile_code, projects or [])
            for item in matrix:
                if item["classification"] != "A":
                    continue
                provider = PROVIDER_REGISTRY.get(str(item.get("provider_key") or ""))
                gap = self._gap_status(item, provider)
                output.append(
                    {
                        "evidence_type": item["evidence_type"],
                        "gate_profile": profile_code,
                        "project_type": item.get("project_type"),
                        "classification": "A",
                        "blocking": item["blocking"],
                        "provider": item.get("provider_key"),
                        "provider_status": provider.get("status") if provider else "MISSING",
                        "gap_status": gap,
                        "recommended_action": self._recommended_action(item, provider),
                    }
                )
        return output

    def gap_analysis(self, content: dict, gate_profile_code: str, projects: list[EnterpriseWorkspace]) -> dict:
        matrix = self._effective_matrix(content, gate_profile_code, projects)
        return {
            "AVAILABLE GOVERNED SOURCES": sorted(
                {
                    item["evidence_type"]
                    for item in matrix
                    if item["classification"] == "A" and item["gap_status"] == "NONE"
                }
            ),
            "MISSING GOVERNED SOURCES": sorted(
                {
                    item["evidence_type"]
                    for item in matrix
                    if item["classification"] == "A" and item["gap_status"] != "NONE"
                }
            ),
            "GOVERNED EVIDENCE SUFFICIENT": sorted(
                {item["evidence_type"] for item in matrix if item["classification"] == "B"}
            ),
            "NOT REQUIRED": sorted({item["evidence_type"] for item in matrix if item["classification"] == "C"}),
        }

    def _release_contract(self, record: AdminConfiguration | None, content: dict) -> dict:
        missing = self._missing_provider_analysis(content)
        is_evid2 = content.get("policy_update") == "GATE07J_EVID_2"
        ready_output = EVID2_READY_OUTPUT if is_evid2 else READY_OUTPUT
        validated_release = EVID2_VALIDATED_RELEASE if is_evid2 else VALIDATED_RELEASE
        rework_output = (
            "GATE07J_EVID_2_DECISION_CRITERIA_POLICY_REWORK_REQUIRED"
            if is_evid2
            else "GATE07M_EVID_POLICY_UPDATE_REWORK_REQUIRED"
        )

        def profile_matrix(profile_code: str) -> list[dict]:
            return [
                {
                    "evidence_type": item["evidence_type"],
                    "classification": item["classification"],
                    "provider_key": item.get("provider_key"),
                    "blocking": item["blocking"],
                    "scope": item["scope"],
                    "coverage_requirement": item.get("coverage_requirement"),
                }
                for item in self._effective_matrix(content, profile_code, [])
            ]

        blockers = sorted(
            {
                item["evidence_type"]
                for item in missing
                if item.get("classification") == "A" and item.get("gap_status") != "NONE"
            }
        )
        return {
            "policy_id": record.id if record else None,
            "policy_revision": record.revision if record else None,
            "policy_hash": record.content_hash if record else _hash(content),
            "effective_from": content.get("effective_from"),
            "business_case_provider_key": "BUSINESS_CASE_READINESS_PROVIDER",
            "business_case_provider_status": PROVIDER_REGISTRY["BUSINESS_CASE_READINESS_PROVIDER"]["status"],
            "economic_financial_provider_key": "ECONOMIC_FINANCIAL_READINESS_PROVIDER",
            "economic_financial_provider_status": PROVIDER_REGISTRY["ECONOMIC_FINANCIAL_READINESS_PROVIDER"]["status"],
            "commercial_provider_key": "COMMERCIAL_READINESS_PROVIDER",
            "commercial_provider_status": PROVIDER_REGISTRY["COMMERCIAL_READINESS_PROVIDER"]["status"],
            "benefits_provider_key": "BENEFITS_READINESS_PROVIDER",
            "benefits_provider_status": PROVIDER_REGISTRY["BENEFITS_READINESS_PROVIDER"]["status"],
            "decision_criterion_policy": deepcopy(content.get("decision_criterion_policy", {})),
            "PYP_INV_SELECT_effective_policy": profile_matrix("PYP-INV-SELECT"),
            "PYP_FFA_effective_policy": profile_matrix("PYP-FFA"),
            "Project_Type_overrides": deepcopy(content.get("project_type_overrides", [])),
            "Governance_Model_applicability": deepcopy(content.get("applicable_governance_models", [])),
            "missing_provider_count": len(blockers),
            "missing_providers": blockers,
            "historical_compatibility_status": "PRESERVED_BY_PREPARATION_AND_DECISION_SNAPSHOTS",
            "Gate07J_integration_status": "AVAILABLE",
            "Gate07K_package_integration_status": "AVAILABLE",
            "warnings": [],
            "blockers": blockers,
            "final_output": ready_output if not blockers else rework_output,
            "exclusive_status": validated_release if not blockers else rework_output,
        }

    @staticmethod
    def _gap_status(requirement: dict, provider: dict | None) -> str:
        if requirement.get("classification") != "A":
            return "NONE"
        if provider is None or provider.get("status") != "AVAILABLE":
            return "PROVIDER_MISSING"
        fields = set(provider.get("contract_fields", []))
        if not REQUIRED_PROVIDER_FIELDS.issubset(fields):
            return "CONTRACT_INVALID"
        scope = str(requirement.get("scope"))
        if not InvestmentEvidencePolicyService._scope_supported(provider, scope):
            return "SCOPE_UNSUPPORTED"
        return "NONE"

    @staticmethod
    def _scope_supported(provider: dict, scope: str) -> bool:
        if scope == "PORTFOLIO":
            return bool(provider.get("supports_portfolio_scope"))
        if scope == "PROJECT_SET":
            return bool(provider.get("supports_project_set_scope"))
        return bool(provider.get("supports_project_scope"))

    @staticmethod
    def _recommended_action(requirement: dict, provider: dict | None) -> str:
        if requirement.get("classification") == "C":
            return "NO_ACTION"
        if requirement.get("classification") == "B":
            return "USE_VALIDATED_GOVERNED_EVIDENCE"
        if provider is None or provider.get("status") != "AVAILABLE":
            return "BUILD_MISSING_GOVERNED_PROVIDER"
        if not REQUIRED_PROVIDER_FIELDS.issubset(set(provider.get("contract_fields", []))):
            return "COMPLETE_PROVIDER_CONTRACT"
        return "REUSE_AVAILABLE_GOVERNED_SOURCE"

    @staticmethod
    def _next_development(missing: list[dict]) -> dict:
        priority = {"RISK_READINESS": 1, "PERMIT_READINESS": 2}
        candidates = [item for item in missing if item.get("blocking") and item.get("gap_status") != "NONE"]
        if not candidates:
            return {"next": "READY_TO_REVALIDATE_NEW_FID_PATH"}
        selected = min(candidates, key=lambda item: (priority.get(item["evidence_type"], 99), item["evidence_type"]))
        return {"next": "BUILD_MISSING_GOVERNED_PROVIDER", "provider": selected["provider"]}

    def _provider_out(self, provider: dict) -> ProviderOut:
        fields = set(provider.get("contract_fields", []))
        issues = (
            sorted(REQUIRED_PROVIDER_FIELDS - fields)
            if provider.get("status") == "AVAILABLE"
            else ["PROVIDER_UNAVAILABLE"]
        )
        return ProviderOut(
            **{key: value for key, value in provider.items() if key != "contract_fields"},
            contract_valid=not issues,
            contract_issues=issues,
        )

    def _validate_policy(self, content: dict) -> None:
        issues: list[str] = []
        if content.get("policy_code") != "PYP-INVESTMENT-EVIDENCE":
            issues.append("INVALID_POLICY_CODE")
        if "CAPITAL_OWNER" not in set(content.get("applicable_governance_models", [])):
            issues.append("CAPITAL_OWNER_POLICY_REQUIRED")
        profiles = content.get("gate_profiles", {})
        try:
            _effective_datetime(content)
        except (TypeError, ValueError):
            issues.append("INVALID_EFFECTIVE_FROM")
        for profile_code in ("PYP-INV-SELECT", "PYP-FFA"):
            profile = profiles.get(profile_code)
            if not profile:
                issues.append(f"MISSING_GATE_PROFILE:{profile_code}")
                continue
            keys: set[str] = set()
            for row in profile.get("requirements", []):
                key = str(row.get("requirement_key") or "")
                if not key or key in keys:
                    issues.append(f"INVALID_REQUIREMENT_KEY:{profile_code}")
                keys.add(key)
                classification = row.get("classification")
                if row.get("evidence_type") not in EVIDENCE_TYPES:
                    issues.append(f"INVALID_EVIDENCE_TYPE:{profile_code}:{key}")
                if classification not in CLASSIFICATIONS:
                    issues.append(f"INVALID_CLASSIFICATION:{profile_code}:{key}")
                if row.get("scope") not in SCOPES:
                    issues.append(f"INVALID_SCOPE:{profile_code}:{key}")
                if classification == "A" and (
                    not row.get("provider_key") or row.get("allow_manual_reference") or not row.get("provider_required")
                ):
                    issues.append(f"CLASS_A_NO_SILENT_FALLBACK:{profile_code}:{key}")
                if classification == "B" and not row.get("allow_manual_reference"):
                    issues.append(f"CLASS_B_MANUAL_EVIDENCE_REQUIRED:{profile_code}:{key}")
                if classification == "C" and (row.get("required") or row.get("blocking")):
                    issues.append(f"CLASS_C_MUST_NOT_BLOCK:{profile_code}:{key}")
                days = row.get("validity_period_days")
                if days is not None and (not isinstance(days, int) or days < 1):
                    issues.append(f"INVALID_VALIDITY:{profile_code}:{key}")
                coverage = row.get("coverage_requirement")
                if coverage is not None and not 0 <= float(coverage) <= 100:
                    issues.append(f"INVALID_COVERAGE:{profile_code}:{key}")
            rows_by_type = {str(row.get("evidence_type")): row for row in profile.get("requirements", [])}
            business_case = rows_by_type.get("BUSINESS_CASE_READINESS")
            financial = rows_by_type.get("ECONOMIC_FINANCIAL_READINESS")
            if business_case is None:
                issues.append(f"MISSING_BUSINESS_CASE_READINESS:{profile_code}")
            if financial is None:
                issues.append(f"MISSING_ECONOMIC_FINANCIAL_READINESS:{profile_code}")
            if business_case and business_case.get("classification") != "A":
                issues.append(f"BUSINESS_CASE_CLASS_A_REQUIRED:{profile_code}")
            if profile_code == "PYP-FFA" and financial and financial.get("classification") != "A":
                issues.append("PYP_FFA_FIN_CLASS_A_REQUIRED")
            if profile_code == "PYP-INV-SELECT" and financial and financial.get("classification") != "B":
                issues.append("PYP_INV_SELECT_FIN_CLASS_B_REQUIRED")
        for override in content.get("project_type_overrides", []):
            if override.get("classification") not in CLASSIFICATIONS:
                issues.append("INVALID_PROJECT_TYPE_OVERRIDE")
            if not override.get("project_type_filter"):
                issues.append("PROJECT_TYPE_FILTER_REQUIRED")
        if content.get("decision_criterion_policy"):
            issues.extend(validate_criterion_policy(content, set(EVIDENCE_TYPES)))
        if issues:
            raise HTTPException(
                status_code=422, detail={"code": "INVALID_EVIDENCE_POLICY", "issues": sorted(set(issues))}
            )

    def _effective_configuration(self, workspace: EnterpriseWorkspace | None) -> AdminConfiguration | None:
        records = list(
            self.db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    AdminConfiguration.status == "published",
                )
            ).all()
        )
        if not records:
            return None
        path_ids = {item.id for item in self._workspace_path(workspace)}
        candidates: list[tuple[int, datetime, int, AdminConfiguration]] = []
        for record in records:
            effective_at = _effective_datetime(record.content_json)
            if effective_at > utc_now():
                continue
            scope = dict(record.content_json.get("scope", {}))
            scope_type = str(scope.get("type") or "tenant")
            scope_id = scope.get("workspace_id")
            specificity = 0
            if scope_type != "tenant":
                if scope_id not in path_ids:
                    continue
                specificity = {"enterprise": 1, "business-unit": 2, "portfolio": 3}.get(scope_type, 0)
            # Within the same scope, the most recently effective policy wins.
            # Revision numbers are local to a configuration identity and cannot
            # order two independently published policy records (for example an
            # old rev 9 versus policy 787 rev 1 at its effective boundary).
            candidates.append((specificity, effective_at, record.revision, record))
        return max(candidates, key=lambda item: item[:3])[3] if candidates else None

    def _configuration(self, configuration_id: int | None, *, lock: bool = False) -> AdminConfiguration:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.id == configuration_id,
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Investment Evidence Policy not found")
        return record

    def _portfolio(self, portfolio_id: int | None) -> EnterpriseWorkspace:
        record = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == portfolio_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.workspace_type_code == "portfolio",
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Portfolio workspace not found")
        self._assert_scope(record.id)
        return record

    def _assert_scope(self, workspace_id: int) -> None:
        if self.context is None or self.context.organization_wide:
            return
        if workspace_id not in self.context.workspace_ids:
            raise HTTPException(status_code=403, detail="Workspace is outside the authorized scope")

    def _workspace_path(self, workspace: EnterpriseWorkspace | None) -> list[EnterpriseWorkspace]:
        if workspace is None:
            return []
        result = [workspace]
        visited = {workspace.id}
        current = workspace
        while current.parent_id is not None:
            parent = self.db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id == current.parent_id,
                )
            )
            if parent is None or parent.id in visited:
                break
            result.append(parent)
            visited.add(parent.id)
            current = parent
        return list(reversed(result))

    @staticmethod
    def _project_type(project: EnterpriseWorkspace) -> str:
        context = dict(dict(project.defaults_json or {}).get("_project", {}))
        return str(context.get("project_type_code") or context.get("project_type") or "UNCLASSIFIED").upper()

    @staticmethod
    def _governance_model(project: EnterpriseWorkspace) -> str:
        context = dict(dict(project.defaults_json or {}).get("_project", {}))
        value = str(context.get("governance_model") or "").upper()
        if not value and context.get("planning_origin") == "STRATEGIC_GATE":
            return "CAPITAL_OWNER"
        return value or "LEGACY"

    def _project_context(self, project: EnterpriseWorkspace) -> dict:
        metadata = dict(dict(project.defaults_json or {}).get("_project", {}))
        return {
            "project_workspace_id": project.id,
            "project_code": project.code,
            "project_name": project.name,
            "project_type": self._project_type(project),
            "governance_model": self._governance_model(project),
            "fel_stage": str(metadata.get("fel_stage") or metadata.get("fel_stage_code") or "UNSPECIFIED").upper(),
            "project_size": str(metadata.get("project_size") or "UNSPECIFIED").upper(),
            "project_risk": str(metadata.get("project_risk") or metadata.get("risk_level") or "UNSPECIFIED").upper(),
            "project_complexity": str(
                metadata.get("project_complexity") or metadata.get("complexity_level") or "UNSPECIFIED"
            ).upper(),
            "uncertainty_level": str(metadata.get("uncertainty_level") or "UNSPECIFIED").upper(),
        }

    @staticmethod
    def _check_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise HTTPException(status_code=412, detail={"code": "ETAG_MISMATCH"})

    def _event(self, event_type: str, entity_type: str, entity_id: int | None, payload: dict) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type=entity_type,
                target_id=entity_id,
                metadata_json=payload,
            )
        )


def _hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default).encode("utf-8")
    ).hexdigest()


def _effective_datetime(content: dict) -> datetime:
    value = content.get("effective_from")
    if value in {None, ""}:
        return datetime.min
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
