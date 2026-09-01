"""Gate 07J governed Investment Gate Preparation service.

The service evaluates evidence completeness and freezes a decision-ready package.
It intentionally does not implement an Investment Decision, FID, Funds, FEL/PDRI
calculation, Project Initialization, Activation, or Execution.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.funds_manager.service import FundsManagerService
from app.modules.investment_evidence_policy.service import InvestmentEvidencePolicyService
from app.modules.investment_gate_preparation.models import (
    InvestmentGateEvidenceItem,
    InvestmentGatePreparation,
)
from app.modules.investment_gate_preparation.schemas import (
    ConfigurationPreviewOut,
    EvidenceItemOut,
    EvidenceValidationIn,
    HandoffOut,
    InvestmentGatePreparationOut,
    ManualEvidenceIn,
    ManualEvidenceUpdateIn,
    PreparationCreateIn,
    PreparationOverviewOut,
    PreparationReadinessOut,
    PreparationUpdateIn,
    ProjectReadinessOut,
    RefreshPreviewOut,
)
from app.modules.portfolio_convergence.service import (
    READY_OUTPUT as GATE07I_READY_OUTPUT,
)
from app.modules.portfolio_convergence.service import PortfolioConvergenceService
from app.modules.project_definition.service import ProjectDefinitionService

CONFIGURATION_KIND = "investment_gate_preparation_configuration"
READY_OUTPUT = "READY_FOR_INVESTMENT_DECISION"
REWORK_OUTPUT = "GATE07J_REWORK_REQUIRED"

EVIDENCE_TYPES = {
    "PORTFOLIO_RECOMMENDATION",
    "BUDGET_FEASIBILITY",
    "RESOURCE_FEASIBILITY",
    "PROJECT_DEFINITION_READINESS",
    "FEL_STAGE_READINESS",
    "PDRI_OR_DEFINITION_ASSESSMENT",
    "RISK_READINESS",
    "FUNDING_READINESS",
    "PERMIT_READINESS",
    "CONTRACTING_STRATEGY_READINESS",
    "EXECUTION_PLAN_READINESS",
    "SCHEDULE_MATURITY",
    "COST_ESTIMATE_MATURITY",
    "OTHER_GOVERNED_EVIDENCE",
}

MISSING_BLOCKERS = {
    "PORTFOLIO_RECOMMENDATION": "MISSING_PORTFOLIO_RECOMMENDATION",
    "PROJECT_DEFINITION_READINESS": "MISSING_DEFINITION_READINESS",
    "FEL_STAGE_READINESS": "MISSING_DEFINITION_READINESS",
    "PDRI_OR_DEFINITION_ASSESSMENT": "MISSING_PDRI_OR_DEFINITION_ASSESSMENT",
    "RISK_READINESS": "MISSING_RISK_READINESS",
    "FUNDING_READINESS": "MISSING_FUNDING_READINESS",
    "PERMIT_READINESS": "MISSING_PERMIT_READINESS",
    "CONTRACTING_STRATEGY_READINESS": "MISSING_CONTRACTING_READINESS",
    "EXECUTION_PLAN_READINESS": "MISSING_EXECUTION_PLAN_READINESS",
}

BASE_REQUIREMENTS: list[dict[str, Any]] = [
    {
        "requirement_key": "portfolio-recommendation",
        "label": "Portfolio Recommendation",
        "evidence_type": "PORTFOLIO_RECOMMENDATION",
        "required": True,
        "blocking": True,
        "scope": "PORTFOLIO",
        "source_type": "GOVERNED_SOURCE",
        "source_contract": "GATE07I_RECOMMENDATION",
        "minimum_status": "READY",
        "validity_period_days": None,
        "allow_manual_reference": False,
        "manual_reference_requires_approval": True,
        "required_fields": ["recommendation_hash", "recommended_project_set_hash"],
        "order": 10,
    },
    {
        "requirement_key": "budget-feasibility",
        "label": "Budget Feasibility",
        "evidence_type": "BUDGET_FEASIBILITY",
        "required": True,
        "blocking": True,
        "scope": "PORTFOLIO",
        "source_type": "GOVERNED_SOURCE",
        "source_contract": "GATE07G_VIA_GATE07I",
        "minimum_status": "READY",
        "validity_period_days": None,
        "allow_manual_reference": False,
        "manual_reference_requires_approval": True,
        "required_fields": [],
        "order": 20,
    },
    {
        "requirement_key": "resource-feasibility",
        "label": "Resource Feasibility",
        "evidence_type": "RESOURCE_FEASIBILITY",
        "required": True,
        "blocking": True,
        "scope": "PORTFOLIO",
        "source_type": "GOVERNED_SOURCE",
        "source_contract": "GATE07H_VIA_GATE07I",
        "minimum_status": "READY",
        "validity_period_days": None,
        "allow_manual_reference": False,
        "manual_reference_requires_approval": True,
        "required_fields": [],
        "order": 30,
    },
    {
        "requirement_key": "fel-stage-readiness",
        "label": "Project Definition / FEL Readiness",
        "evidence_type": "FEL_STAGE_READINESS",
        "required": True,
        "blocking": True,
        "scope": "EACH_PROJECT",
        "source_type": "GOVERNED_SOURCE",
        "source_contract": "PROJECT_DEFINITION_READINESS",
        "minimum_status": "VALID",
        "validity_period_days": 365,
        "allow_manual_reference": True,
        "manual_reference_requires_approval": True,
        "required_fields": ["fel_stage", "assessment_id", "evidence_hash"],
        "order": 40,
    },
    {
        "requirement_key": "risk-readiness",
        "label": "Risk Readiness",
        "evidence_type": "RISK_READINESS",
        "required": True,
        "blocking": True,
        "scope": "PORTFOLIO",
        "source_type": "GOVERNED_SOURCE",
        "source_contract": "GATE07I_RISK_SUMMARY",
        "minimum_status": "VALID",
        "validity_period_days": None,
        "allow_manual_reference": False,
        "manual_reference_requires_approval": True,
        "required_fields": [],
        "order": 50,
    },
    {
        "requirement_key": "funding-readiness",
        "label": "Funding Readiness",
        "evidence_type": "FUNDING_READINESS",
        "required": False,
        "blocking": False,
        "scope": "PORTFOLIO",
        "source_type": "GOVERNED_SOURCE",
        "source_contract": "FUNDING_READINESS",
        "minimum_status": "VALID",
        "validity_period_days": 180,
        "allow_manual_reference": True,
        "manual_reference_requires_approval": True,
        "required_fields": [],
        "order": 60,
    },
]


def _profile(*, code: str, purpose: str, fel_stage: str, funding: bool) -> dict[str, Any]:
    requirements = deepcopy(BASE_REQUIREMENTS)
    for item in requirements:
        if item["evidence_type"] == "FUNDING_READINESS":
            item["required"] = funding
            item["blocking"] = funding
    return {
        "scope": {"type": "tenant", "workspace_id": None},
        "inherit_to_descendants": True,
        "profile_code": code,
        "profile_name": "Investment Selection Preparation"
        if purpose == "INVESTMENT_SELECTION"
        else "Full Funds Authorization Preparation",
        "gate_purpose": purpose,
        "applicable_governance_models": ["CAPITAL_OWNER"],
        "required_FEL_stage": fel_stage,
        "required_definition_framework": "FEL_OR_EQUIVALENT",
        "required_definition_threshold_rule": "SOURCE_THRESHOLD_RESULT_PASS",
        "requirements": requirements,
        "project_coverage_threshold_percent": 100,
        "conditions_policy": {"open_conditions_block": True, "deferred_allowed": False},
        "blocking_policy": {"required_evidence": "block", "scope_mismatch": "block"},
        "warning_policy": {"optional_missing": "warning"},
        "sod": {
            "preparer_must_differ_from_validator": True,
            "require_distinct_validator_for": ["fel-stage-readiness", "funding-readiness"],
        },
        "readiness_rules": {"require_current_source": True, "require_all_blocking_evidence": True},
    }


DEFAULT_PROFILES = {
    "pyp-inv-select": _profile(code="PYP-INV-SELECT", purpose="INVESTMENT_SELECTION", fel_stage="FEL-2", funding=False),
    "pyp-ffa": _profile(code="PYP-FFA", purpose="FULL_FUNDS_AUTHORIZATION", fel_stage="FEL-3", funding=True),
}


class InvestmentGatePreparationService:
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

    # Configuration bootstrap -------------------------------------
    def ensure_seed(self) -> None:
        changed = False
        for code, content in DEFAULT_PROFILES.items():
            exists = self.db.scalar(
                select(AdminConfiguration.id).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    AdminConfiguration.code == code,
                )
            )
            if exists is not None:
                continue
            self.db.add(
                AdminConfiguration(
                    tenant_id=self.tenant_id,
                    kind=CONFIGURATION_KIND,
                    code=code,
                    name=content["profile_name"],
                    description="Gate 07J starter profile. Review and publish explicitly before USER use.",
                    status="draft",
                    revision=1,
                    version=1,
                    content_json=deepcopy(content),
                    content_hash=_hash(content),
                    created_by_user_id=self.actor_id,
                )
            )
            changed = True
        if changed:
            self._event("investment_gate_configuration.seeded_as_draft", "AdminConfiguration", None, {})
            self.db.commit()

    # USER lifecycle -----------------------------------------------
    def overview(self, portfolio_id: int) -> PreparationOverviewOut:
        workspace = self._portfolio(portfolio_id)
        source_contract = None
        governance_eligible = False
        try:
            source_contract = self._gate07i_contract(portfolio_id)
            governance_eligible = self._assert_capital_owner_projects(source_contract, raise_error=False)
        except HTTPException:
            source_contract = None
        profiles = [self._profile_summary(item) for item in self._applicable_profiles(workspace)]
        return PreparationOverviewOut(
            portfolio_workspace_id=portfolio_id,
            governance_eligible=governance_eligible,
            source_contract=source_contract,
            profiles=profiles,
            preparations=self.preparations(portfolio_id),
            boundaries=[
                "GATE07J_PREPARES_EVIDENCE_AND_DOES_NOT_MAKE_INVESTMENT_DECISIONS",
                "FROZEN_IS_NOT_APPROVED_OR_FID",
                "CAN_ENTER_FID_IS_ALWAYS_FALSE",
                "NO_FUNDS_OR_FINANCING_TRANSACTIONS",
                "NO_FEL_INDEX_OR_PDRI_SCORING",
                "NO_PROJECT_INITIALIZATION_ACTIVATION_OR_EXECUTION",
            ],
        )

    def preparations(self, portfolio_id: int | None = None) -> list[InvestmentGatePreparationOut]:
        statement = select(InvestmentGatePreparation).where(InvestmentGatePreparation.tenant_id == self.tenant_id)
        if portfolio_id is not None:
            self._portfolio(portfolio_id)
            statement = statement.where(InvestmentGatePreparation.portfolio_workspace_id == portfolio_id)
        records = list(self.db.scalars(statement.order_by(InvestmentGatePreparation.id.desc())).all())
        return [
            self._preparation_out(item, historical=item.status in {"FROZEN", "SUPERSEDED", "VOIDED"})
            for item in records
        ]

    def preparation(self, preparation_id: int) -> InvestmentGatePreparationOut:
        return self._preparation_out(self._preparation(preparation_id))

    def create(self, payload: PreparationCreateIn) -> InvestmentGatePreparationOut:
        duplicate = self.db.scalar(
            select(InvestmentGatePreparation).where(
                InvestmentGatePreparation.tenant_id == self.tenant_id,
                InvestmentGatePreparation.create_idempotency_key == payload.idempotency_key,
            )
        )
        if duplicate is not None:
            return self._preparation_out(duplicate)
        workspace = self._portfolio(payload.portfolio_workspace_id)
        profile = self._configuration(payload.investment_gate_profile_id)
        if profile.status != "published" or profile not in self._applicable_profiles(workspace):
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_APPLICABLE_GATE_PROFILE_REQUIRED"})
        self._validate_configuration(profile.content_json)
        contract = self._gate07i_contract(workspace.id)
        self._assert_capital_owner_projects(contract)
        profile_code = str(profile.content_json.get("profile_code") or profile.code).upper()
        evidence_policy = InvestmentEvidencePolicyService(
            self.db, self.tenant_id, self.actor_id, self.context
        ).published_snapshot(
            workspace.id,
            profile_code,
            list(contract.get("selected_project_set_reference", [])),
        )
        effective_profile = self._profile_content_with_policy(profile.content_json, evidence_policy)
        revision = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(InvestmentGatePreparation.revision), 0)).where(
                        InvestmentGatePreparation.tenant_id == self.tenant_id,
                        InvestmentGatePreparation.portfolio_workspace_id == workspace.id,
                        InvestmentGatePreparation.logical_code == "INVESTMENT-GATE-PREPARATION",
                    )
                )
                or 0
            )
            + 1
        )
        snapshot = self._source_snapshot(contract, profile, evidence_policy)
        record = InvestmentGatePreparation(
            tenant_id=self.tenant_id,
            portfolio_workspace_id=workspace.id,
            preparation_number=f"IGP-{workspace.code}-{revision:04d}",
            logical_code="INVESTMENT-GATE-PREPARATION",
            revision=revision,
            name=payload.name,
            description=payload.description,
            investment_gate_profile_id=profile.id,
            profile_code=profile_code,
            profile_revision=profile.revision,
            profile_hash=profile.content_hash,
            source_convergence_id=int(contract["convergence_id"]),
            source_convergence_revision=int(contract["convergence_revision"]),
            source_recommendation_hash=str(contract["recommendation_hash"]),
            recommended_alternative_id=int(contract["recommended_alternative_id"]),
            recommended_project_set_hash=str(contract["selected_project_set_hash"]),
            status="DRAFT",
            readiness_status="BLOCKED",
            source_snapshot_json=snapshot,
            evidence_summary_json={},
            conditions_json=self._condition_records(contract),
            warnings_json=[],
            blockers_json=[],
            preparation_source_hash="0" * 64,
            revision_version=1,
            create_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        self._sync_requirements(record, effective_profile, contract)
        record.preparation_source_hash = self._current_preparation_hash(record, contract, profile.content_hash)
        self._recalculate(record, contract=contract, profile=profile)
        self._event(
            "investment_gate_preparation.created",
            "InvestmentGatePreparation",
            record.id,
            {"profile_code": record.profile_code, "source_convergence_id": record.source_convergence_id},
        )
        self.db.commit()
        return self._preparation_out(record)

    def update(
        self, preparation_id: int, expected_version: int, payload: PreparationUpdateIn
    ) -> InvestmentGatePreparationOut:
        record = self._preparation(preparation_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_editable(record)
        if payload.name is not None:
            record.name = payload.name
        if payload.description is not None:
            record.description = payload.description
        self._touch(record)
        self._event("investment_gate_preparation.updated", "InvestmentGatePreparation", record.id, {})
        self.db.commit()
        return self._preparation_out(record)

    def add_evidence(
        self, preparation_id: int, expected_version: int, payload: ManualEvidenceIn
    ) -> InvestmentGatePreparationOut:
        duplicate = self.db.scalar(
            select(InvestmentGateEvidenceItem).where(
                InvestmentGateEvidenceItem.tenant_id == self.tenant_id,
                InvestmentGateEvidenceItem.add_idempotency_key == payload.idempotency_key,
            )
        )
        if duplicate is not None:
            return self._preparation_out(self._preparation(duplicate.preparation_id))
        record = self._preparation(preparation_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_editable(record)
        profile = self._configuration(record.investment_gate_profile_id)
        profile_content = self._profile_content(record, profile)
        requirement = self._requirement(profile_content, payload.requirement_key, payload.scope_id)
        if not requirement.get("allow_manual_reference"):
            raise HTTPException(status_code=409, detail={"code": "MANUAL_REFERENCE_NOT_ALLOWED"})
        scope_key = self._scope_key(payload.scope_type, payload.scope_id)
        self._validate_evidence_scope(record, requirement, payload.scope_type, payload.scope_id)
        item = self.db.scalar(
            select(InvestmentGateEvidenceItem).where(
                InvestmentGateEvidenceItem.tenant_id == self.tenant_id,
                InvestmentGateEvidenceItem.preparation_id == record.id,
                InvestmentGateEvidenceItem.requirement_key == payload.requirement_key,
                InvestmentGateEvidenceItem.scope_key == scope_key,
            )
        )
        if item is None:
            item = self._new_evidence(record, requirement, payload.scope_type, payload.scope_id)
            self.db.add(item)
        elif item.evidence_origin == "GOVERNED_SOURCE" and item.status == "VALID":
            raise HTTPException(status_code=409, detail={"code": "GOVERNED_SOURCE_EVIDENCE_IS_READ_ONLY"})
        item.evidence_origin = "MANUAL_REFERENCE"
        item.source_module = None
        item.source_record_id = payload.reference_id
        item.evidence_date = payload.evidence_date
        item.valid_until = payload.valid_until or self._default_valid_until(payload.evidence_date, requirement)
        item.issuer = payload.issuer
        item.owner = payload.owner
        item.summary = payload.summary
        item.evidence_refs_json = deepcopy(payload.evidence_refs)
        item.scope_reference_hash = payload.scope_reference_hash or record.recommended_project_set_hash
        item.source_hash = _hash(self._manual_evidence_payload(payload))
        item.status = "SUBMITTED"
        item.submitted_by = self.actor_id
        item.submitted_at = utc_now()
        item.validated_by = None
        item.validated_at = None
        item.validation_note = None
        item.add_idempotency_key = payload.idempotency_key
        item.revision_version += 1
        item.updated_at = utc_now()
        record.status = "IN_PREPARATION" if record.status == "DRAFT" else record.status
        self._refresh_internal_hash_and_readiness(record, profile)
        self._touch(record)
        self._event(
            "investment_gate_evidence.added",
            "InvestmentGateEvidenceItem",
            item.id,
            {"preparation_id": record.id, "requirement_key": item.requirement_key},
        )
        self.db.commit()
        return self._preparation_out(record)

    def update_evidence(
        self, evidence_id: int, expected_version: int, payload: ManualEvidenceUpdateIn
    ) -> InvestmentGatePreparationOut:
        item = self._evidence(evidence_id, lock=True)
        record = self._preparation(item.preparation_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_editable(record)
        if item.evidence_origin != "MANUAL_REFERENCE":
            raise HTTPException(status_code=409, detail={"code": "GOVERNED_SOURCE_EVIDENCE_IS_READ_ONLY"})
        for field in ("evidence_date", "valid_until", "issuer", "owner", "summary", "scope_reference_hash"):
            value = getattr(payload, field)
            if value is not None:
                setattr(item, field, value)
        if payload.evidence_refs is not None:
            item.evidence_refs_json = deepcopy(payload.evidence_refs)
        item.source_hash = _hash(self._evidence_hash_payload(item))
        item.status = "SUBMITTED"
        item.validated_by = None
        item.validated_at = None
        item.validation_note = None
        item.revision_version += 1
        item.updated_at = utc_now()
        self._refresh_internal_hash_and_readiness(record, self._configuration(record.investment_gate_profile_id))
        self._touch(record)
        self._event("investment_gate_evidence.added", "InvestmentGateEvidenceItem", item.id, {"updated": True})
        self.db.commit()
        return self._preparation_out(record)

    def remove_evidence(self, evidence_id: int, expected_version: int) -> InvestmentGatePreparationOut:
        item = self._evidence(evidence_id, lock=True)
        record = self._preparation(item.preparation_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_editable(record)
        if item.evidence_origin != "MANUAL_REFERENCE":
            raise HTTPException(status_code=409, detail={"code": "GOVERNED_SOURCE_EVIDENCE_IS_READ_ONLY"})
        item.source_module = None
        item.source_record_id = None
        item.source_hash = None
        item.evidence_date = None
        item.valid_until = None
        item.issuer = None
        item.owner = None
        item.summary = "Required evidence is not available from a governed source."
        item.evidence_refs_json = []
        item.status = "MISSING"
        item.submitted_by = None
        item.submitted_at = None
        item.validated_by = None
        item.validated_at = None
        item.validation_note = None
        item.add_idempotency_key = None
        item.validate_idempotency_key = None
        item.blockers_json = []
        item.revision_version += 1
        item.updated_at = utc_now()
        self._refresh_internal_hash_and_readiness(record, self._configuration(record.investment_gate_profile_id))
        self._touch(record)
        self._event("investment_gate_evidence.removed", "InvestmentGateEvidenceItem", item.id, {})
        self.db.commit()
        return self._preparation_out(record)

    def validate_evidence(
        self,
        evidence_id: int,
        expected_version: int,
        payload: EvidenceValidationIn,
    ) -> InvestmentGatePreparationOut:
        duplicate = self.db.scalar(
            select(InvestmentGateEvidenceItem).where(
                InvestmentGateEvidenceItem.tenant_id == self.tenant_id,
                InvestmentGateEvidenceItem.validate_idempotency_key == payload.idempotency_key,
            )
        )
        if duplicate is not None:
            return self._preparation_out(self._preparation(duplicate.preparation_id))
        item = self._evidence(evidence_id, lock=True)
        record = self._preparation(item.preparation_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_editable(record)
        profile = self._configuration(record.investment_gate_profile_id)
        profile_content = self._profile_content(record, profile)
        requirement = self._requirement(profile_content, item.requirement_key, item.scope_id)
        sod = dict(profile_content.get("sod", {}))
        if (
            sod.get("preparer_must_differ_from_validator")
            and item.requirement_key in set(sod.get("require_distinct_validator_for", []))
            and item.submitted_by == self.actor_id
        ):
            raise HTTPException(status_code=409, detail={"code": "EVIDENCE_VALIDATION_SOD_VIOLATION"})
        if item.status not in {"SUBMITTED", "VALID", "INVALID", "EXPIRED", "STALE"}:
            raise HTTPException(status_code=409, detail={"code": "EVIDENCE_NOT_SUBMITTED"})
        status = payload.decision
        blockers: list[str] = []
        if status == "VALID" and item.valid_until and item.valid_until < utc_now():
            status = "EXPIRED"
            blockers.append("EVIDENCE_EXPIRED")
        if status == "VALID" and item.scope_reference_hash != record.recommended_project_set_hash:
            status = "INVALID"
            blockers.append("EVIDENCE_SCOPE_MISMATCH")
        if status == "VALID" and not self._minimum_maturity_met(item, requirement, profile_content):
            status = "INVALID"
            blockers.append("INSUFFICIENT_FEL_MATURITY")
        item.status = status
        item.validated_by = self.actor_id
        item.validated_at = utc_now()
        item.validation_note = payload.validation_note
        item.validate_idempotency_key = payload.idempotency_key
        item.blockers_json = blockers
        item.revision_version += 1
        item.updated_at = utc_now()
        self._refresh_internal_hash_and_readiness(record, profile)
        self._touch(record)
        event = "investment_gate_evidence.validated" if status == "VALID" else "investment_gate_evidence.invalidated"
        self._event(event, "InvestmentGateEvidenceItem", item.id, {"status": status})
        self.db.commit()
        return self._preparation_out(record)

    def project_readiness(self, preparation_id: int) -> ProjectReadinessOut:
        record = self._preparation(preparation_id)
        profile = self._configuration(record.investment_gate_profile_id)
        return self._project_readiness(record, self._profile_content(record, profile))

    def readiness(self, preparation_id: int) -> PreparationReadinessOut:
        record = self._preparation(preparation_id)
        profile = self._configuration(record.investment_gate_profile_id)
        return self._readiness(record, profile=profile)

    def refresh_preview(self, preparation_id: int) -> RefreshPreviewOut:
        record = self._preparation(preparation_id)
        self._assert_editable(record)
        profile = self._effective_profile_for_code(self._portfolio(record.portfolio_workspace_id), record.profile_code)
        if profile is None:
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_APPLICABLE_GATE_PROFILE_REQUIRED"})
        contract = self._gate07i_contract(record.portfolio_workspace_id)
        proposed = self._current_preparation_hash(record, contract, profile.content_hash)
        old_projects = set(record.source_snapshot_json.get("selected_project_ids", []))
        new_projects = set(contract.get("selected_project_set_reference", []))
        current_blockers = set(record.blockers_json or [])
        projected = self._projected_blockers(record, contract, profile)
        evidence_changes = []
        for item in self._evidence_records(record.id):
            effective = self._effective_evidence_status(item, record)
            if effective != item.status:
                evidence_changes.append({"evidence_id": item.id, "from": item.status, "to": effective})
        result = RefreshPreviewOut(
            preparation_id=record.id,
            current_source_hash=record.preparation_source_hash,
            proposed_source_hash=proposed,
            source_current=proposed == record.preparation_source_hash,
            source_revision_changes={
                "convergence": [record.source_convergence_revision, contract["convergence_revision"]],
                "recommendation_hash_changed": record.source_recommendation_hash != contract["recommendation_hash"],
                "profile_revision": [record.profile_revision, profile.revision],
            },
            project_set_changes={
                "added": sorted(new_projects - old_projects),
                "removed": sorted(old_projects - new_projects),
            },
            evidence_changes=evidence_changes,
            blockers_added=sorted(projected - current_blockers),
            blockers_removed=sorted(current_blockers - projected),
            persisted=False,
        )
        self._event("investment_gate_preparation.refresh_previewed", "InvestmentGatePreparation", record.id, {})
        return result

    def refresh(
        self,
        preparation_id: int,
        expected_version: int,
        expected_source_hash: str,
        idempotency_key: str,
    ) -> InvestmentGatePreparationOut:
        duplicate = self.db.scalar(
            select(InvestmentGatePreparation).where(
                InvestmentGatePreparation.tenant_id == self.tenant_id,
                InvestmentGatePreparation.refresh_idempotency_key == idempotency_key,
            )
        )
        if duplicate is not None:
            return self._preparation_out(duplicate)
        record = self._preparation(preparation_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_editable(record)
        profile = self._effective_profile_for_code(self._portfolio(record.portfolio_workspace_id), record.profile_code)
        if profile is None:
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_APPLICABLE_GATE_PROFILE_REQUIRED"})
        contract = self._gate07i_contract(record.portfolio_workspace_id)
        proposed = self._current_preparation_hash(record, contract, profile.content_hash)
        if proposed != expected_source_hash:
            raise HTTPException(status_code=412, detail={"code": "STALE_INVESTMENT_GATE_SOURCE"})
        record.investment_gate_profile_id = profile.id
        record.profile_revision = profile.revision
        record.profile_hash = profile.content_hash
        record.source_convergence_id = int(contract["convergence_id"])
        record.source_convergence_revision = int(contract["convergence_revision"])
        record.source_recommendation_hash = str(contract["recommendation_hash"])
        record.recommended_alternative_id = int(contract["recommended_alternative_id"])
        record.recommended_project_set_hash = str(contract["selected_project_set_hash"])
        record.source_snapshot_json = self._source_snapshot(
            contract,
            profile,
            deepcopy(record.source_snapshot_json.get("evidence_policy")),
        )
        record.conditions_json = self._merge_conditions(record.conditions_json, contract)
        self._sync_requirements(record, self._profile_content(record, profile), contract)
        record.preparation_source_hash = self._current_preparation_hash(record, contract, profile.content_hash)
        record.status = "IN_PREPARATION"
        record.refresh_idempotency_key = idempotency_key
        self._recalculate(record, contract=contract, profile=profile)
        self._touch(record)
        self._event("investment_gate_preparation.refresh_applied", "InvestmentGatePreparation", record.id, {})
        self.db.commit()
        return self._preparation_out(record)

    def update_condition(
        self, preparation_id: int, condition_index: int, expected_version: int, values: dict
    ) -> InvestmentGatePreparationOut:
        record = self._preparation(preparation_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_editable(record)
        conditions = deepcopy(record.conditions_json or [])
        if condition_index < 0 or condition_index >= len(conditions):
            raise HTTPException(status_code=404, detail="Recommendation condition not found")
        original = conditions[condition_index].get("original_text")
        conditions[condition_index].update(values)
        conditions[condition_index]["original_text"] = original
        record.conditions_json = conditions
        self._refresh_internal_hash_and_readiness(record, self._configuration(record.investment_gate_profile_id))
        self._touch(record)
        self._event(
            "investment_gate_condition.updated", "InvestmentGatePreparation", record.id, {"index": condition_index}
        )
        self.db.commit()
        return self._preparation_out(record)

    def ready_for_review(
        self, preparation_id: int, expected_version: int, idempotency_key: str
    ) -> InvestmentGatePreparationOut:
        duplicate = self.db.scalar(
            select(InvestmentGatePreparation).where(
                InvestmentGatePreparation.tenant_id == self.tenant_id,
                InvestmentGatePreparation.ready_idempotency_key == idempotency_key,
            )
        )
        if duplicate is not None:
            return self._preparation_out(duplicate)
        record = self._preparation(preparation_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_editable(record)
        profile = self._configuration(record.investment_gate_profile_id)
        readiness = self._readiness(record, profile=profile)
        if readiness.readiness_status != "READY":
            raise HTTPException(
                status_code=409, detail={"code": "PREPARATION_NOT_READY", "blockers": readiness.blockers}
            )
        record.status = "READY_FOR_REVIEW"
        record.ready_idempotency_key = idempotency_key
        self._touch(record)
        self._event("investment_gate_preparation.ready_for_review", "InvestmentGatePreparation", record.id, {})
        self.db.commit()
        return self._preparation_out(record)

    def freeze(self, preparation_id: int, expected_version: int, idempotency_key: str) -> InvestmentGatePreparationOut:
        duplicate = self.db.scalar(
            select(InvestmentGatePreparation).where(
                InvestmentGatePreparation.tenant_id == self.tenant_id,
                InvestmentGatePreparation.freeze_idempotency_key == idempotency_key,
            )
        )
        if duplicate is not None:
            return self._preparation_out(duplicate, historical=True)
        record = self._preparation(preparation_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status != "READY_FOR_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "READY_FOR_REVIEW_REQUIRED"})
        profile = self._configuration(record.investment_gate_profile_id)
        readiness = self._readiness(record, profile=profile)
        if readiness.readiness_status != "READY" or not readiness.source_current:
            raise HTTPException(
                status_code=409, detail={"code": "PREPARATION_NOT_READY", "blockers": readiness.blockers}
            )
        package = self._package_payload(record, readiness)
        record.preparation_hash = _hash(package)
        record.status = "FROZEN"
        record.readiness_status = "READY"
        record.freeze_idempotency_key = idempotency_key
        record.frozen_by = self.actor_id
        record.frozen_at = utc_now()
        self._touch(record)
        self._event(
            "investment_gate_preparation.frozen",
            "InvestmentGatePreparation",
            record.id,
            {"final_output": READY_OUTPUT, "can_enter_fid": False},
        )
        self.db.commit()
        return self._preparation_out(record, historical=True)

    def clone(self, preparation_id: int, expected_version: int, idempotency_key: str) -> InvestmentGatePreparationOut:
        duplicate = self.db.scalar(
            select(InvestmentGatePreparation).where(
                InvestmentGatePreparation.tenant_id == self.tenant_id,
                InvestmentGatePreparation.clone_idempotency_key == idempotency_key,
            )
        )
        if duplicate is not None:
            return self._preparation_out(duplicate)
        source = self._preparation(preparation_id)
        self._check_version(source.revision_version, expected_version)
        payload = PreparationCreateIn(
            portfolio_workspace_id=source.portfolio_workspace_id,
            investment_gate_profile_id=source.investment_gate_profile_id,
            name=f"{source.name} · revision {source.revision + 1}",
            description=source.description,
            idempotency_key=f"clone-create-{idempotency_key}",
        )
        clone = self.create(payload)
        record = self._preparation(clone.id, lock=True)
        record.clone_idempotency_key = idempotency_key
        source_items = [
            item for item in self._evidence_records(source.id) if item.evidence_origin == "MANUAL_REFERENCE"
        ]
        for original in source_items:
            target = self.db.scalar(
                select(InvestmentGateEvidenceItem).where(
                    InvestmentGateEvidenceItem.preparation_id == record.id,
                    InvestmentGateEvidenceItem.requirement_key == original.requirement_key,
                    InvestmentGateEvidenceItem.scope_key == original.scope_key,
                )
            )
            if target is None:
                continue
            target.evidence_origin = "MANUAL_REFERENCE"
            target.source_record_id = original.source_record_id
            target.source_hash = original.source_hash
            target.scope_reference_hash = original.scope_reference_hash
            target.status = "SUBMITTED"
            target.evidence_date = original.evidence_date
            target.valid_until = original.valid_until
            target.issuer = original.issuer
            target.owner = original.owner
            target.summary = original.summary
            target.evidence_refs_json = deepcopy(original.evidence_refs_json or [])
            target.submitted_by = self.actor_id
            target.submitted_at = utc_now()
        self._refresh_internal_hash_and_readiness(record, self._configuration(record.investment_gate_profile_id))
        self._event(
            "investment_gate_preparation.cloned", "InvestmentGatePreparation", record.id, {"source_id": source.id}
        )
        self.db.commit()
        return self._preparation_out(record)

    def void(self, preparation_id: int, expected_version: int, idempotency_key: str) -> InvestmentGatePreparationOut:
        duplicate = self.db.scalar(
            select(InvestmentGatePreparation).where(
                InvestmentGatePreparation.tenant_id == self.tenant_id,
                InvestmentGatePreparation.void_idempotency_key == idempotency_key,
            )
        )
        if duplicate is not None:
            return self._preparation_out(duplicate, historical=True)
        record = self._preparation(preparation_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        self._assert_editable(record)
        record.status = "VOIDED"
        record.void_idempotency_key = idempotency_key
        record.voided_at = utc_now()
        self._touch(record)
        self._event("investment_gate_preparation.voided", "InvestmentGatePreparation", record.id, {})
        self.db.commit()
        return self._preparation_out(record, historical=True)

    def handoff(self, preparation_id: int) -> HandoffOut:
        record = self._preparation(preparation_id)
        if record.status != "FROZEN" or record.readiness_status != "READY" or not record.preparation_hash:
            raise HTTPException(status_code=409, detail={"code": "FROZEN_READY_PREPARATION_REQUIRED"})
        profile = self._configuration(record.investment_gate_profile_id)
        readiness = self._readiness(record, profile=profile, historical=True)
        contract = dict(record.source_snapshot_json.get("gate07i_contract", {}))
        summary = dict(record.evidence_summary_json or {})
        return HandoffOut(
            tenant_id=self.tenant_id,
            portfolio_workspace_id=record.portfolio_workspace_id,
            preparation_id=record.id,
            preparation_number=record.preparation_number,
            preparation_revision=record.revision,
            investment_gate_profile_id=record.investment_gate_profile_id,
            profile_code=record.profile_code,
            profile_revision=record.profile_revision,
            profile_hash=record.profile_hash,
            source_convergence_id=record.source_convergence_id,
            source_recommendation_hash=record.source_recommendation_hash,
            recommended_alternative_id=record.recommended_alternative_id,
            recommended_project_set_hash=record.recommended_project_set_hash,
            budget_scenario_ref=contract.get("budget_scenario_ref"),
            resource_scenario_ref=contract.get("resource_scenario_ref"),
            budget_planning_hash=contract.get("budget_planning_hash"),
            resource_planning_hash=contract.get("resource_planning_hash"),
            portfolio_analysis_hash=str(contract.get("analysis_hash") or ""),
            evidence_package_hash=_hash(self._package_payload(record, readiness)),
            project_evidence_coverage=self._project_readiness(
                record, self._profile_content(record, profile)
            ).model_dump(),
            portfolio_evidence_summary=summary,
            definition_FEL_summary=dict(summary.get("Project Definition / FEL", {})),
            definition_maturity_summary=dict(summary.get("Definition Maturity", {})),
            risk_summary=dict(summary.get("Risk", {})),
            funding_summary=dict(summary.get("Funding", {})),
            permit_summary=dict(summary.get("Permits", {})),
            contracting_summary=dict(summary.get("Contracting", {})),
            execution_plan_summary=dict(summary.get("Execution Planning", {})),
            open_conditions=[item for item in record.conditions_json or [] if item.get("preparation_status") == "OPEN"],
            warnings=list(record.warnings_json or []),
            blockers=[],
            preparation_hash=record.preparation_hash,
        )

    # AdminConfiguration reuse ------------------------------------
    def configurations(self) -> list[AdminConfiguration]:
        self.ensure_seed()
        return list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                )
                .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
            ).all()
        )

    def configuration_preview(
        self,
        portfolio_id: int | None,
        configuration_id: int | None,
        content_override: dict | None,
    ) -> ConfigurationPreviewOut:
        workspace = self._portfolio(portfolio_id) if portfolio_id else None
        record = self._configuration(configuration_id) if configuration_id else None
        effective = deepcopy(
            content_override
            if content_override is not None
            else record.content_json
            if record
            else next(iter(DEFAULT_PROFILES.values()))
        )
        issues = self._configuration_issues(effective)
        warnings: list[str] = []
        blockers: list[str] = []
        projected: dict = {"status": "NOT_EVALUATED", "source_available": False}
        if workspace and not issues:
            try:
                contract = self._gate07i_contract(workspace.id)
                eligible = self._assert_capital_owner_projects(contract, raise_error=False)
                projected = {
                    "status": "BLOCKED",
                    "source_available": True,
                    "governance_eligible": eligible,
                    "selected_project_count": len(contract.get("selected_project_set_reference", [])),
                    "initial_missing_requirements": [
                        item["requirement_key"]
                        for item in effective.get("requirements", [])
                        if item.get("required") and self._governed_payload(item, contract) is None
                    ],
                }
                if not eligible:
                    blockers.append("CAPITAL_OWNER_REQUIRED")
            except HTTPException as exc:
                blockers.append(_detail_code(exc, "PORTFOLIO_RECOMMENDATION_NOT_READY"))
        return ConfigurationPreviewOut(
            portfolio_workspace_id=portfolio_id,
            path=[self._workspace_summary(item) for item in self._workspace_path(workspace)],
            effective=effective,
            source=self._profile_summary(record) if record else {"type": "starter-default", "status": "draft"},
            requirements=sorted(effective.get("requirements", []), key=lambda item: int(item.get("order", 0))),
            projected_readiness=projected,
            validation_issues=issues,
            warnings=warnings,
            blockers=sorted(set(blockers)),
            publishable=not issues,
            persisted=False,
        )

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
        self._event("investment_gate_configuration.cloned", "AdminConfiguration", clone.id, {})
        self.db.commit()
        return clone

    def update_configuration(
        self, configuration_id: int, expected_version: int, name: str, description: str, content: dict
    ) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_IMMUTABLE"})
        self._validate_configuration(content)
        record.name = name
        record.description = description
        record.content_json = deepcopy(content)
        record.content_hash = _hash(content)
        record.version += 1
        record.updated_at = utc_now()
        self._event("investment_gate_configuration.updated", "AdminConfiguration", record.id, {})
        self.db.commit()
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "CONFIGURATION_NOT_DRAFT"})
        self._validate_configuration(record.content_json)
        scope = dict(record.content_json.get("scope", {}))
        for previous in self.configurations():
            if (
                previous.id != record.id
                and previous.status == "published"
                and previous.code == record.code
                and dict(previous.content_json.get("scope", {})) == scope
            ):
                previous.status = "superseded"
                previous.version += 1
        record.status = "published"
        record.published_at = utc_now()
        record.version += 1
        record.content_hash = _hash(record.content_json)
        self._event("investment_gate_configuration.published", "AdminConfiguration", record.id, {})
        self.db.commit()
        return record

    # Source/evidence/readiness -----------------------------------
    def _gate07i_contract(self, portfolio_id: int) -> dict:
        service = PortfolioConvergenceService(self.db, self.tenant_id, self.actor_id, self.context)
        contract = service.preparation_contract(portfolio_id).model_dump(mode="json")
        if contract.get("final_output") != GATE07I_READY_OUTPUT or not contract.get("portfolio_recommendation_ready"):
            raise HTTPException(status_code=409, detail={"code": "MISSING_PORTFOLIO_RECOMMENDATION"})
        if contract.get("can_enter_fid") is not False:
            raise HTTPException(status_code=409, detail={"code": "INVALID_GATE07I_FID_SAFEGUARD"})
        return contract

    def _source_snapshot(
        self,
        contract: dict,
        profile: AdminConfiguration,
        evidence_policy: dict | None = None,
    ) -> dict:
        return {
            "gate07i_contract": deepcopy(contract),
            "selected_project_ids": list(contract.get("selected_project_set_reference", [])),
            "profile": {
                "id": profile.id,
                "code": profile.content_json.get("profile_code"),
                "revision": profile.revision,
                "hash": profile.content_hash,
            },
            "evidence_policy": deepcopy(evidence_policy),
            "captured_at": utc_now().isoformat(),
            "boundaries": {
                "investment_decision_created": False,
                "fid_created": False,
                "funds_created": False,
                "fel_pdri_calculated": False,
            },
        }

    def _sync_requirements(self, record: InvestmentGatePreparation, profile: dict, contract: dict) -> None:
        selected = list(contract.get("selected_project_set_reference", []))
        for requirement in sorted(profile.get("requirements", []), key=lambda item: int(item.get("order", 0))):
            scope = str(requirement.get("scope"))
            targets: list[int | None] = selected if scope in {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"} else [None]
            for scope_id in targets:
                effective_requirement = self._resolved_requirement(requirement, scope_id)
                scope_key = self._scope_key(scope, scope_id)
                item = self.db.scalar(
                    select(InvestmentGateEvidenceItem).where(
                        InvestmentGateEvidenceItem.tenant_id == self.tenant_id,
                        InvestmentGateEvidenceItem.preparation_id == record.id,
                        InvestmentGateEvidenceItem.requirement_key == requirement["requirement_key"],
                        InvestmentGateEvidenceItem.scope_key == scope_key,
                    )
                )
                payload, provider_error = self._policy_governed_payload(effective_requirement, contract, scope_id)
                if effective_requirement.get("classification") is None:
                    payload = self._governed_payload(effective_requirement, contract, scope_id)
                    provider_error = None
                if item is None:
                    item = self._new_evidence(record, effective_requirement, scope, scope_id)
                    self.db.add(item)
                if item.evidence_origin == "MANUAL_REFERENCE" and item.status not in {
                    "MISSING",
                    "NOT_AVAILABLE",
                    "NOT_REQUIRED",
                }:
                    continue
                if effective_requirement.get("classification") == "C" or not effective_requirement.get("required"):
                    item.status = "NOT_REQUIRED"
                    item.evidence_origin = "GOVERNED_SOURCE"
                    item.summary = "Not required by the published Investment Gate Profile."
                    item.blockers_json = []
                elif payload is not None:
                    item.evidence_origin = "GOVERNED_SOURCE"
                    item.source_module = str(payload["source_module"])
                    item.source_record_id = str(payload["source_record_id"])
                    item.source_hash = str(payload["source_hash"])
                    item.scope_reference_hash = str(contract["selected_project_set_hash"])
                    item.status = (
                        "STALE" if provider_error == "SOURCE_STALE" else "INVALID" if provider_error else "VALID"
                    )
                    item.summary = str(payload["summary"])
                    item.evidence_refs_json = deepcopy(payload.get("evidence_refs", []))
                    item.evidence_date = payload.get("evidence_date")
                    item.warnings_json = deepcopy(payload.get("warnings", []))
                    item.blockers_json = deepcopy(payload.get("blockers", []))
                    if provider_error:
                        item.blockers_json = sorted(set(item.blockers_json + [provider_error]))
                    item.validated_at = utc_now()
                else:
                    allow_manual = bool(effective_requirement.get("allow_manual_reference"))
                    item.evidence_origin = "MANUAL_REFERENCE" if allow_manual else "GOVERNED_SOURCE"
                    item.status = "MISSING" if allow_manual else "NOT_AVAILABLE"
                    item.blockers_json = [provider_error] if provider_error else []
                    item.summary = (
                        "Controlled Class B evidence must be submitted and validated."
                        if allow_manual
                        else "Class A governed evidence is unavailable; manual fallback is prohibited."
                    )

    def _policy_governed_payload(
        self, requirement: dict, contract: dict, scope_id: int | None
    ) -> tuple[dict | None, str | None]:
        classification = requirement.get("classification")
        if classification not in {"A", "B", "C"}:
            return None, None
        if classification == "C" or not requirement.get("provider_key"):
            return None, None
        payload, error = InvestmentEvidencePolicyService(
            self.db, self.tenant_id, self.actor_id, self.context
        ).resolve_governed_payload(requirement, contract, scope_id)
        if payload is None:
            return None, error
        return (
            {
                "source_module": payload["source_module"],
                "source_record_id": payload["source_record_id"],
                "source_hash": payload["evidence_hash"],
                "summary": payload["summary"],
                "evidence_refs": payload.get("evidence_refs", []),
                "evidence_date": utc_now(),
                "warnings": payload.get("warnings", []),
                "blockers": payload.get("blockers", []),
            },
            error,
        )

    def _governed_payload(self, requirement: dict, contract: dict, scope_id: int | None = None) -> dict | None:
        evidence_type = requirement.get("evidence_type")
        if evidence_type == "FUNDING_READINESS":
            try:
                governed = FundsManagerService(
                    self.db, self.tenant_id, self.actor_id, self.context
                ).investment_gate_evidence(int(contract["portfolio_workspace_id"]))
            except HTTPException:
                governed = None
            if governed and governed.can_supply_investment_gate_evidence and governed.source_current:
                payload = governed.model_dump(mode="json")
                return {
                    "source_module": "FUNDS_MANAGER",
                    "source_record_id": governed.snapshot_id or governed.funding_readiness_hash,
                    "source_hash": governed.funding_readiness_hash,
                    "summary": (
                        f"Governed Funding Readiness {governed.funding_readiness_status}; "
                        f"confirmed coverage {governed.confirmed_coverage_percent}%."
                    ),
                    "evidence_refs": [payload],
                }
        if (
            evidence_type
            in {
                "PROJECT_DEFINITION_READINESS",
                "FEL_STAGE_READINESS",
                "PDRI_OR_DEFINITION_ASSESSMENT",
            }
            and scope_id is not None
        ):
            try:
                governed = ProjectDefinitionService(
                    self.db, self.tenant_id, self.actor_id, self.context
                ).investment_gate_evidence(scope_id)
            except HTTPException:
                governed = None
            if governed and governed.can_supply_investment_gate_evidence and governed.source_current:
                payload = governed.model_dump(mode="json")
                return {
                    "source_module": "project_definition_fel",
                    "source_record_id": governed.assessment_id,
                    "source_hash": governed.definition_readiness_hash,
                    "summary": (
                        f"Governed {governed.FEL_stage_code} definition evidence; "
                        f"maturity {governed.maturity_level}, threshold {governed.threshold_status}."
                    ),
                    "evidence_refs": [
                        payload
                        | {
                            "fel_stage": governed.FEL_stage_code,
                            "evidence_hash": governed.definition_readiness_hash,
                        }
                    ],
                }
        if evidence_type == "PORTFOLIO_RECOMMENDATION":
            return {
                "source_module": "portfolio_convergence",
                "source_record_id": contract["convergence_id"],
                "source_hash": contract["recommendation_hash"],
                "summary": "Current governed Gate 07I Portfolio recommendation.",
            }
        if evidence_type == "BUDGET_FEASIBILITY" and contract.get("budget_scenario_ref"):
            return {
                "source_module": "portfolio_budget",
                "source_record_id": contract["budget_scenario_ref"]["id"],
                "source_hash": contract["budget_scenario_ref"]["hash"],
                "summary": json.dumps(contract.get("budget_feasibility_summary", {}), default=str),
            }
        if evidence_type == "RESOURCE_FEASIBILITY" and contract.get("resource_scenario_ref"):
            return {
                "source_module": "portfolio_resource",
                "source_record_id": contract["resource_scenario_ref"]["id"],
                "source_hash": contract["resource_scenario_ref"]["hash"],
                "summary": json.dumps(contract.get("resource_feasibility_summary", {}), default=str),
            }
        if evidence_type == "RISK_READINESS" and contract.get("risk_summary") is not None:
            return {
                "source_module": "portfolio_convergence",
                "source_record_id": contract["convergence_id"],
                "source_hash": _hash(contract.get("risk_summary", {})),
                "summary": json.dumps(contract.get("risk_summary", {}), default=str),
            }
        return None

    def _recalculate(
        self,
        record: InvestmentGatePreparation,
        *,
        contract: dict | None = None,
        profile: AdminConfiguration | None = None,
        historical: bool = False,
    ) -> PreparationReadinessOut:
        profile = profile or self._configuration(record.investment_gate_profile_id)
        profile_content = self._profile_content(record, profile)
        source_current = True
        if not historical and record.status != "FROZEN":
            try:
                contract = contract or self._gate07i_contract(record.portfolio_workspace_id)
                current_profile = self._effective_profile_for_code(
                    self._portfolio(record.portfolio_workspace_id), record.profile_code
                )
                source_current = (
                    bool(current_profile)
                    and self._current_preparation_hash(record, contract, current_profile.content_hash)
                    == record.preparation_source_hash
                )
            except HTTPException:
                source_current = False
        items = self._evidence_records(record.id)
        blockers: list[str] = []
        warnings: list[str] = []
        valid_items: set[tuple[str, str]] = set()
        required_items = 0
        categories: dict[str, dict[str, int]] = {}
        for item in items:
            try:
                requirement = self._requirement(profile_content, item.requirement_key, item.scope_id)
            except HTTPException:
                requirement = None
            if requirement and (not requirement.get("required") or requirement.get("classification") == "C"):
                requirement = None
            effective = self._effective_evidence_status(item, record)
            category = self._category(item.evidence_type)
            bucket = categories.setdefault(category, {"required": 0, "valid": 0, "blocked": 0})
            if requirement:
                required_items += 1
                bucket["required"] += 1
                if effective == "VALID":
                    valid_items.add((item.requirement_key, item.scope_key))
                    bucket["valid"] += 1
                else:
                    bucket["blocked"] += 1
                    item_blockers = set(item.blockers_json or [])
                    if "SOURCE_PROVIDER_MISSING" in item_blockers:
                        blockers.append("SOURCE_PROVIDER_MISSING")
                    elif "PROVIDER_CONTRACT_INVALID" in item_blockers:
                        blockers.append("PROVIDER_CONTRACT_INVALID")
                    elif "SCOPE_UNSUPPORTED" in item_blockers:
                        blockers.append("SCOPE_UNSUPPORTED")
                    elif "MINIMUM_READINESS_NOT_MET" in item_blockers:
                        blockers.append("MINIMUM_READINESS_NOT_MET")
                    elif effective == "EXPIRED":
                        blockers.append("EVIDENCE_EXPIRED")
                    elif effective == "STALE":
                        blockers.append("EVIDENCE_STALE")
                    elif "EVIDENCE_SCOPE_MISMATCH" in set(item.blockers_json or []) or (
                        item.scope_reference_hash and item.scope_reference_hash != record.recommended_project_set_hash
                    ):
                        blockers.append("EVIDENCE_SCOPE_MISMATCH")
                    elif "INSUFFICIENT_FEL_MATURITY" in set(item.blockers_json or []):
                        blockers.append("INSUFFICIENT_FEL_MATURITY")
                    else:
                        blockers.append(MISSING_BLOCKERS.get(item.evidence_type, "MISSING_REQUIRED_EVIDENCE"))
            elif effective not in {"VALID", "NOT_REQUIRED"}:
                warnings.append(f"OPTIONAL_EVIDENCE_{item.evidence_type}_{effective}")
        project = self._project_readiness(record, profile_content)
        threshold = float(profile_content.get("project_coverage_threshold_percent", 100))
        if project.coverage_percent < threshold:
            blockers.append("PROJECT_COVERAGE_INCOMPLETE")
        conditions_policy = dict(profile_content.get("conditions_policy", {}))
        if conditions_policy.get("open_conditions_block"):
            allowed = {"RESOLVED_FOR_PREPARATION"}
            if conditions_policy.get("deferred_allowed"):
                allowed.add("DEFERRED")
            if any(item.get("preparation_status") not in allowed for item in record.conditions_json or []):
                blockers.append("OPEN_RECOMMENDATION_CONDITION")
        if not source_current and record.status != "FROZEN":
            blockers.append("STALE_PORTFOLIO_RECOMMENDATION")
            readiness_status = "STALE"
        else:
            readiness_status = "BLOCKED" if blockers else "READY"
        if record.status == "FROZEN":
            readiness_status = "READY"
            blockers = []
        category_summary = {
            key: {**value, "status": "VALID" if value["required"] == value["valid"] else "BLOCKED"}
            for key, value in categories.items()
        }
        final_warnings = sorted(set(warnings))
        final_blockers = sorted(set(blockers))
        if not historical and record.status != "FROZEN":
            record.readiness_status = readiness_status
            record.warnings_json = final_warnings
            record.blockers_json = final_blockers
            record.evidence_summary_json = category_summary
        frozen_ready = record.status == "FROZEN" and readiness_status == "READY"
        return PreparationReadinessOut(
            preparation_id=record.id,
            status=record.status,
            readiness_status=readiness_status,
            source_current=source_current,
            required_requirement_count=required_items,
            valid_requirement_count=len(valid_items),
            required_project_count=project.required_project_count,
            valid_project_count=project.valid_project_count,
            blocked_project_count=project.blocked_project_count,
            coverage_percent=project.coverage_percent,
            category_summary=category_summary,
            warnings=final_warnings,
            blockers=final_blockers,
            investment_gate_preparation_ready=frozen_ready,
            can_enter_investment_decision=frozen_ready,
            can_enter_fid=False,
            final_output=READY_OUTPUT if frozen_ready else REWORK_OUTPUT,
        )

    def _readiness(
        self,
        record: InvestmentGatePreparation,
        *,
        profile: AdminConfiguration,
        historical: bool = False,
    ) -> PreparationReadinessOut:
        return self._recalculate(record, profile=profile, historical=historical)

    def _project_readiness(self, record: InvestmentGatePreparation, profile: dict) -> ProjectReadinessOut:
        selected = list(record.source_snapshot_json.get("selected_project_ids", []))
        evidence = self._evidence_records(record.id)
        projects: list[dict] = []
        for project_id in selected:
            project_requirements = {
                item["requirement_key"]: self._resolved_requirement(item, project_id)
                for item in profile.get("requirements", [])
                if item.get("scope") in {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"}
                and self._resolved_requirement(item, project_id).get("required")
                and self._resolved_requirement(item, project_id).get("classification") != "C"
            }
            rows = [
                item
                for item in evidence
                if item.scope_id == project_id and item.requirement_key in project_requirements
            ]
            valid = [item for item in rows if self._effective_evidence_status(item, record) == "VALID"]
            missing = sorted(set(project_requirements) - {item.requirement_key for item in valid})
            projects.append(
                {
                    "project_id": project_id,
                    "required_count": len(project_requirements),
                    "valid_count": len({item.requirement_key for item in valid}),
                    "missing_requirements": missing,
                    "status": "READY" if not missing else "BLOCKED",
                }
            )
        valid_count = sum(1 for item in projects if item["status"] == "READY")
        required_count = len(projects)
        coverage = round((valid_count / required_count) * 100, 2) if required_count else 100.0
        return ProjectReadinessOut(
            preparation_id=record.id,
            required_project_count=required_count,
            valid_project_count=valid_count,
            blocked_project_count=required_count - valid_count,
            coverage_percent=coverage,
            projects=projects,
        )

    def _current_preparation_hash(self, record: InvestmentGatePreparation, contract: dict, profile_hash: str) -> str:
        evidence_hashes = [
            {
                "requirement_key": item.requirement_key,
                "scope_key": item.scope_key,
                "source_hash": item.source_hash,
                "status": item.status,
            }
            for item in self._evidence_records(record.id)
        ]
        return _hash(
            {
                "recommendation_hash": contract.get("recommendation_hash"),
                "recommended_project_set_hash": contract.get("selected_project_set_hash"),
                "budget_planning_hash": contract.get("budget_planning_hash"),
                "resource_planning_hash": contract.get("resource_planning_hash"),
                "analysis_hash": contract.get("analysis_hash"),
                "profile_hash": profile_hash,
                "evidence_policy_hash": dict(record.source_snapshot_json.get("evidence_policy") or {}).get(
                    "policy_hash"
                ),
                "evidence": evidence_hashes,
            }
        )

    def _refresh_internal_hash_and_readiness(
        self, record: InvestmentGatePreparation, profile: AdminConfiguration
    ) -> None:
        contract = self._gate07i_contract(record.portfolio_workspace_id)
        record.preparation_source_hash = self._current_preparation_hash(record, contract, profile.content_hash)
        self._recalculate(record, contract=contract, profile=profile)

    def _projected_blockers(
        self, record: InvestmentGatePreparation, contract: dict, profile: AdminConfiguration
    ) -> set[str]:
        if record.source_recommendation_hash != contract.get("recommendation_hash"):
            return {"STALE_PORTFOLIO_RECOMMENDATION"}
        if record.profile_hash != profile.content_hash:
            return {"STALE_GATE_PROFILE"}
        return set(record.blockers_json or [])

    # Serialization/actions ---------------------------------------
    def _preparation_out(
        self, record: InvestmentGatePreparation, *, historical: bool = False
    ) -> InvestmentGatePreparationOut:
        profile = self._configuration(record.investment_gate_profile_id)
        readiness = self._readiness(record, profile=profile, historical=historical or record.status == "FROZEN")
        return InvestmentGatePreparationOut(
            id=record.id,
            tenant_id=record.tenant_id,
            portfolio_workspace_id=record.portfolio_workspace_id,
            preparation_number=record.preparation_number,
            logical_code=record.logical_code,
            revision=record.revision,
            name=record.name,
            description=record.description,
            investment_gate_profile_id=record.investment_gate_profile_id,
            profile_code=record.profile_code,
            profile_revision=record.profile_revision,
            profile_hash=record.profile_hash,
            source_convergence_id=record.source_convergence_id,
            source_convergence_revision=record.source_convergence_revision,
            source_recommendation_hash=record.source_recommendation_hash,
            recommended_alternative_id=record.recommended_alternative_id,
            recommended_project_set_hash=record.recommended_project_set_hash,
            status=record.status,
            readiness_status=readiness.readiness_status,
            source_snapshot=deepcopy(record.source_snapshot_json or {}),
            evidence_summary=deepcopy(record.evidence_summary_json or {}),
            conditions=deepcopy(record.conditions_json or []),
            warnings=readiness.warnings,
            blockers=readiness.blockers,
            preparation_source_hash=record.preparation_source_hash,
            preparation_hash=record.preparation_hash,
            revision_version=record.revision_version,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_by=record.updated_by,
            updated_at=record.updated_at,
            frozen_by=record.frozen_by,
            frozen_at=record.frozen_at,
            voided_at=record.voided_at,
            evidence=[self._evidence_out(item, record) for item in self._evidence_records(record.id)],
            readiness=readiness,
            allowed_actions=self._allowed_actions(record, readiness),
        )

    def _evidence_out(self, item: InvestmentGateEvidenceItem, record: InvestmentGatePreparation) -> EvidenceItemOut:
        return EvidenceItemOut(
            id=item.id,
            preparation_id=item.preparation_id,
            requirement_key=item.requirement_key,
            evidence_type=item.evidence_type,
            scope_type=item.scope_type,
            scope_id=item.scope_id,
            evidence_revision=item.evidence_revision,
            evidence_origin=item.evidence_origin,
            source_module=item.source_module,
            source_record_id=item.source_record_id,
            source_hash=item.source_hash,
            scope_reference_hash=item.scope_reference_hash,
            status=self._effective_evidence_status(item, record),
            evidence_date=item.evidence_date,
            valid_until=item.valid_until,
            issuer=item.issuer,
            owner=item.owner,
            summary=item.summary,
            evidence_refs=deepcopy(item.evidence_refs_json or []),
            submitted_by=item.submitted_by,
            submitted_at=item.submitted_at,
            validated_by=item.validated_by,
            validated_at=item.validated_at,
            validation_note=item.validation_note,
            warnings=list(item.warnings_json or []),
            blockers=list(item.blockers_json or []),
            revision_version=item.revision_version,
        )

    @staticmethod
    def _allowed_actions(record: InvestmentGatePreparation, readiness: PreparationReadinessOut) -> list[str]:
        actions = ["can_view_investment_gate_preparation", "can_view_handoff"]
        if record.status in {"DRAFT", "IN_PREPARATION", "READY_FOR_REVIEW"}:
            actions.extend(
                [
                    "can_edit_preparation",
                    "can_add_manual_evidence",
                    "can_remove_manual_evidence",
                    "can_validate_evidence",
                    "can_mark_condition_status",
                    "can_void_preparation",
                ]
            )
            if readiness.source_current:
                actions.append("can_refresh_preparation")
            else:
                actions.append("can_refresh_preparation")
            if readiness.readiness_status == "READY" and record.status != "READY_FOR_REVIEW":
                actions.append("can_submit_for_readiness_review")
            if readiness.readiness_status == "READY" and record.status == "READY_FOR_REVIEW":
                actions.append("can_freeze_preparation")
        actions.append("can_clone_preparation")
        if record.status == "FROZEN" and readiness.readiness_status == "READY":
            actions.append("can_enter_investment_decision")
        return actions

    # Configuration validation/inheritance ------------------------
    def _configuration_issues(self, content: dict) -> list[str]:
        issues: list[str] = []
        if list(content.get("applicable_governance_models", [])) != ["CAPITAL_OWNER"]:
            issues.append("CAPITAL_OWNER_ONLY_REQUIRED")
        if not content.get("profile_code") or content.get("gate_purpose") not in {
            "INVESTMENT_SELECTION",
            "FULL_FUNDS_AUTHORIZATION",
        }:
            issues.append("INVALID_GATE_PROFILE_IDENTITY")
        requirements = list(content.get("requirements", []))
        keys = [str(item.get("requirement_key") or "") for item in requirements]
        if not requirements or len(keys) != len(set(keys)) or any(not key for key in keys):
            issues.append("INVALID_EVIDENCE_REQUIREMENTS")
        for item in requirements:
            if item.get("evidence_type") not in EVIDENCE_TYPES:
                issues.append("INVALID_EVIDENCE_TYPE")
            if item.get("scope") not in {"PORTFOLIO", "PROJECT_SET", "EACH_PROJECT", "SELECTED_PROJECTS_ONLY"}:
                issues.append("INVALID_EVIDENCE_SCOPE")
            if item.get("source_type") not in {"GOVERNED_SOURCE", "MANUAL_REFERENCE"}:
                issues.append("INVALID_EVIDENCE_SOURCE_TYPE")
            days = item.get("validity_period_days")
            if days is not None and (not isinstance(days, int) or days < 1):
                issues.append("INVALID_EVIDENCE_VALIDITY")
        if content.get("required_FEL_stage") and not any(
            item.get("evidence_type") in {"FEL_STAGE_READINESS", "PROJECT_DEFINITION_READINESS"}
            and item.get("required")
            for item in requirements
        ):
            issues.append("FEL_REQUIREMENT_REQUIRED")
        if any(key in content for key in ("formula_language", "pdri_formula", "fel_index_formula")):
            issues.append("GENERIC_SCORING_FORMULA_NOT_ALLOWED")
        return sorted(set(issues))

    def _validate_configuration(self, content: dict) -> None:
        issues = self._configuration_issues(content)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION", "issues": issues})

    def _applicable_profiles(self, workspace: EnterpriseWorkspace) -> list[AdminConfiguration]:
        records = list(
            self.db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    AdminConfiguration.status == "published",
                )
            ).all()
        )
        path = self._workspace_path(workspace)
        path_ids = {item.id: item for item in path}
        candidates: dict[str, tuple[int, int, AdminConfiguration]] = {}
        for record in records:
            scope = dict((record.content_json or {}).get("scope", {}))
            scope_type = str(scope.get("type") or "tenant")
            scope_id = scope.get("workspace_id")
            specificity = 0
            if scope_type != "tenant":
                if scope_id not in path_ids:
                    continue
                expected = {
                    "enterprise": "enterprise",
                    "business-unit": "business-unit",
                    "portfolio": "portfolio",
                }.get(scope_type)
                if expected and path_ids[int(scope_id)].workspace_type_code != expected:
                    continue
                specificity = {"enterprise": 1, "business-unit": 2, "portfolio": 3}.get(scope_type, 0)
            current = candidates.get(record.code)
            candidate = (specificity, record.revision, record)
            if current is None or candidate[:2] > current[:2]:
                candidates[record.code] = candidate
        return [item[2] for item in sorted(candidates.values(), key=lambda value: value[2].code)]

    def _effective_profile_for_code(
        self, workspace: EnterpriseWorkspace, profile_code: str
    ) -> AdminConfiguration | None:
        return next(
            (
                item
                for item in self._applicable_profiles(workspace)
                if str(item.content_json.get("profile_code") or item.code).upper() == profile_code.upper()
            ),
            None,
        )

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
            raise HTTPException(status_code=404, detail="Investment Gate Profile not found")
        return record

    @staticmethod
    def _profile_summary(record: AdminConfiguration | None) -> dict:
        if record is None:
            return {}
        return {
            "id": record.id,
            "code": record.code,
            "profile_code": record.content_json.get("profile_code"),
            "name": record.name,
            "revision": record.revision,
            "version": record.version,
            "status": record.status,
            "content_hash": record.content_hash,
            "gate_purpose": record.content_json.get("gate_purpose"),
            "required_FEL_stage": record.content_json.get("required_FEL_stage"),
        }

    # Persistence/workspace helpers -------------------------------
    def _preparation(self, preparation_id: int | None, *, lock: bool = False) -> InvestmentGatePreparation:
        statement = select(InvestmentGatePreparation).where(
            InvestmentGatePreparation.id == preparation_id,
            InvestmentGatePreparation.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Investment Gate Preparation not found")
        self._assert_scope(record.portfolio_workspace_id)
        return record

    def _evidence(self, evidence_id: int, *, lock: bool = False) -> InvestmentGateEvidenceItem:
        statement = select(InvestmentGateEvidenceItem).where(
            InvestmentGateEvidenceItem.id == evidence_id,
            InvestmentGateEvidenceItem.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Investment Gate Evidence not found")
        return record

    def _evidence_records(self, preparation_id: int) -> list[InvestmentGateEvidenceItem]:
        return list(
            self.db.scalars(
                select(InvestmentGateEvidenceItem)
                .where(
                    InvestmentGateEvidenceItem.tenant_id == self.tenant_id,
                    InvestmentGateEvidenceItem.preparation_id == preparation_id,
                )
                .order_by(
                    InvestmentGateEvidenceItem.requirement_key,
                    InvestmentGateEvidenceItem.scope_key,
                    InvestmentGateEvidenceItem.evidence_revision,
                )
            ).all()
        )

    def _portfolio(self, portfolio_id: int | None) -> EnterpriseWorkspace:
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == portfolio_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
            )
        )
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        if workspace.workspace_type_code != "portfolio":
            raise HTTPException(status_code=422, detail={"code": "WORKSPACE_IS_NOT_PORTFOLIO"})
        self._assert_scope(workspace.id)
        return workspace

    def _assert_capital_owner_projects(self, contract: dict, *, raise_error: bool = True) -> bool:
        project_ids = list(contract.get("selected_project_set_reference", []))
        projects = list(
            self.db.scalars(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id.in_(project_ids or [-1]),
                    EnterpriseWorkspace.workspace_type_code == "project",
                )
            ).all()
        )
        eligible = (
            len(projects) == len(project_ids)
            and bool(project_ids)
            and all(self._governance_model(item) == "CAPITAL_OWNER" for item in projects)
        )
        if not eligible and raise_error:
            raise HTTPException(status_code=409, detail={"code": "CAPITAL_OWNER_INVESTMENT_GATE_REQUIRED"})
        return eligible

    @staticmethod
    def _governance_model(project: EnterpriseWorkspace) -> str:
        context = dict(dict(project.defaults_json or {}).get("_project", {}))
        value = str(context.get("governance_model") or "").upper()
        if not value and context.get("planning_origin") == "STRATEGIC_GATE":
            return "CAPITAL_OWNER"
        return value or "LEGACY"

    def _assert_scope(self, workspace_id: int) -> None:
        if self.context is None or self.context.organization_wide:
            return
        if workspace_id not in self.context.workspace_ids:
            raise HTTPException(status_code=403, detail="Workspace is outside the authorized scope")

    def _workspace_path(self, workspace: EnterpriseWorkspace | None) -> list[EnterpriseWorkspace]:
        if workspace is None:
            return []
        path = [workspace]
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
            path.append(parent)
            visited.add(parent.id)
            current = parent
        return list(reversed(path))

    @staticmethod
    def _workspace_summary(workspace: EnterpriseWorkspace) -> dict:
        return {
            "id": workspace.id,
            "code": workspace.code,
            "name": workspace.name,
            "workspace_type_code": workspace.workspace_type_code,
            "parent_id": workspace.parent_id,
        }

    @staticmethod
    def _check_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise HTTPException(status_code=412, detail={"code": "ETAG_MISMATCH"})

    @staticmethod
    def _assert_editable(record: InvestmentGatePreparation) -> None:
        if record.status not in {"DRAFT", "IN_PREPARATION", "READY_FOR_REVIEW"}:
            raise HTTPException(status_code=409, detail={"code": "FROZEN_PREPARATION_IMMUTABLE"})

    def _touch(self, record: InvestmentGatePreparation) -> None:
        record.revision_version += 1
        record.updated_by = self.actor_id
        record.updated_at = utc_now()

    def _new_evidence(
        self,
        record: InvestmentGatePreparation,
        requirement: dict,
        scope_type: str,
        scope_id: int | None,
    ) -> InvestmentGateEvidenceItem:
        return InvestmentGateEvidenceItem(
            tenant_id=self.tenant_id,
            preparation_id=record.id,
            requirement_key=str(requirement["requirement_key"]),
            evidence_type=str(requirement["evidence_type"]),
            scope_type=scope_type,
            scope_id=scope_id,
            scope_key=self._scope_key(scope_type, scope_id),
            evidence_revision=1,
            evidence_origin=str(requirement.get("source_type") or "GOVERNED_SOURCE"),
            status="MISSING" if requirement.get("required") else "NOT_REQUIRED",
            scope_reference_hash=record.recommended_project_set_hash,
            summary="",
            evidence_refs_json=[],
            warnings_json=[],
            blockers_json=[],
            revision_version=1,
        )

    @staticmethod
    def _profile_content_with_policy(profile: dict, evidence_policy: dict | None) -> dict:
        effective = deepcopy(profile)
        if evidence_policy:
            effective["requirements"] = deepcopy(evidence_policy.get("requirements", []))
            effective["evidence_policy_id"] = evidence_policy.get("policy_id")
            effective["evidence_policy_revision"] = evidence_policy.get("policy_revision")
            effective["evidence_policy_hash"] = evidence_policy.get("policy_hash")
        return effective

    def _profile_content(self, record: InvestmentGatePreparation, profile: AdminConfiguration) -> dict:
        return self._profile_content_with_policy(
            profile.content_json,
            dict(record.source_snapshot_json.get("evidence_policy") or {}) or None,
        )

    @staticmethod
    def _resolved_requirement(requirement: dict, scope_id: int | None) -> dict:
        effective = deepcopy(requirement)
        if scope_id is None:
            return effective
        resolved = dict(requirement.get("resolved_projects", {})).get(str(scope_id))
        if resolved:
            effective.update(deepcopy(resolved))
        return effective

    def _requirement(self, profile: dict, key: str, scope_id: int | None = None) -> dict:
        item = next((value for value in profile.get("requirements", []) if value.get("requirement_key") == key), None)
        if item is None:
            raise HTTPException(status_code=404, detail="Evidence requirement not found")
        return self._resolved_requirement(item, scope_id)

    def _validate_evidence_scope(
        self,
        record: InvestmentGatePreparation,
        requirement: dict,
        scope_type: str,
        scope_id: int | None,
    ) -> None:
        if scope_type != requirement.get("scope"):
            raise HTTPException(status_code=422, detail={"code": "EVIDENCE_SCOPE_MISMATCH"})
        if scope_type in {"EACH_PROJECT", "SELECTED_PROJECTS_ONLY"} and scope_id not in set(
            record.source_snapshot_json.get("selected_project_ids", [])
        ):
            raise HTTPException(status_code=422, detail={"code": "EVIDENCE_SCOPE_MISMATCH"})

    @staticmethod
    def _scope_key(scope_type: str, scope_id: int | None) -> str:
        return f"{scope_type}:{scope_id if scope_id is not None else 'ROOT'}"

    @staticmethod
    def _effective_evidence_status(item: InvestmentGateEvidenceItem, record: InvestmentGatePreparation) -> str:
        if item.status == "VALID" and item.valid_until and item.valid_until < utc_now():
            return "EXPIRED"
        if (
            item.status == "VALID"
            and item.scope_reference_hash
            and item.scope_reference_hash != record.recommended_project_set_hash
        ):
            return "STALE"
        return item.status

    @staticmethod
    def _default_valid_until(evidence_date: datetime, requirement: dict) -> datetime | None:
        days = requirement.get("validity_period_days")
        if not days:
            return None
        from datetime import timedelta

        return evidence_date + timedelta(days=int(days))

    @staticmethod
    def _manual_evidence_payload(payload: ManualEvidenceIn) -> dict:
        return {
            "requirement_key": payload.requirement_key,
            "scope_type": payload.scope_type,
            "scope_id": payload.scope_id,
            "reference_id": payload.reference_id,
            "evidence_date": payload.evidence_date,
            "valid_until": payload.valid_until,
            "issuer": payload.issuer,
            "owner": payload.owner,
            "summary": payload.summary,
            "evidence_refs": payload.evidence_refs,
            "scope_reference_hash": payload.scope_reference_hash,
        }

    @staticmethod
    def _evidence_hash_payload(item: InvestmentGateEvidenceItem) -> dict:
        return {
            "requirement_key": item.requirement_key,
            "scope_key": item.scope_key,
            "source_record_id": item.source_record_id,
            "evidence_date": item.evidence_date,
            "valid_until": item.valid_until,
            "issuer": item.issuer,
            "owner": item.owner,
            "summary": item.summary,
            "evidence_refs": item.evidence_refs_json,
            "scope_reference_hash": item.scope_reference_hash,
        }

    @staticmethod
    def _minimum_maturity_met(item: InvestmentGateEvidenceItem, requirement: dict, profile: dict) -> bool:
        if requirement.get("evidence_type") not in {"FEL_STAGE_READINESS", "PROJECT_DEFINITION_READINESS"}:
            return True
        required = str(profile.get("required_FEL_stage") or "").upper()
        if not required:
            return True
        refs = list(item.evidence_refs_json or [])
        actual = next((str(value.get("fel_stage") or "").upper() for value in refs if value.get("fel_stage")), "")
        levels = {"FEL-1": 1, "FEL-2": 2, "FEL-3": 3}
        return levels.get(actual, 0) >= levels.get(required, 0)

    @staticmethod
    def _condition_records(contract: dict) -> list[dict]:
        return [
            {
                "condition_id": index + 1,
                "original_text": text,
                "condition_owner": None,
                "target_resolution_date": None,
                "preparation_status": "OPEN",
                "evidence_reference": None,
            }
            for index, text in enumerate(contract.get("conditions", []))
        ]

    @staticmethod
    def _merge_conditions(existing: list[dict], contract: dict) -> list[dict]:
        by_text = {item.get("original_text"): item for item in existing or []}
        return [
            deepcopy(
                by_text.get(
                    text,
                    {
                        "condition_id": index + 1,
                        "original_text": text,
                        "condition_owner": None,
                        "target_resolution_date": None,
                        "preparation_status": "OPEN",
                        "evidence_reference": None,
                    },
                )
            )
            for index, text in enumerate(contract.get("conditions", []))
        ]

    @staticmethod
    def _category(evidence_type: str) -> str:
        mapping = {
            "PORTFOLIO_RECOMMENDATION": "Portfolio Recommendation",
            "BUDGET_FEASIBILITY": "Budget / Resource",
            "RESOURCE_FEASIBILITY": "Budget / Resource",
            "PROJECT_DEFINITION_READINESS": "Project Definition / FEL",
            "FEL_STAGE_READINESS": "Project Definition / FEL",
            "PDRI_OR_DEFINITION_ASSESSMENT": "Definition Maturity",
            "RISK_READINESS": "Risk",
            "FUNDING_READINESS": "Funding",
            "PERMIT_READINESS": "Permits",
            "CONTRACTING_STRATEGY_READINESS": "Contracting",
            "EXECUTION_PLAN_READINESS": "Execution Planning",
        }
        return mapping.get(evidence_type, "Other Evidence")

    def _package_payload(self, record: InvestmentGatePreparation, readiness: PreparationReadinessOut) -> dict:
        return {
            "preparation": {
                "id": record.id,
                "number": record.preparation_number,
                "revision": record.revision,
                "profile_hash": record.profile_hash,
                "source_recommendation_hash": record.source_recommendation_hash,
                "recommended_project_set_hash": record.recommended_project_set_hash,
                "source_hash": record.preparation_source_hash,
            },
            "evidence": [
                self._evidence_hash_payload(item) | {"status": item.status}
                for item in self._evidence_records(record.id)
            ],
            "conditions": record.conditions_json,
            "readiness": readiness.model_dump(mode="json"),
            "can_enter_fid": False,
        }

    def _event(self, event_type: str, target_type: str, target_id: int | None, metadata: dict) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type=target_type,
                target_id=target_id,
                metadata_json=metadata,
            )
        )


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _detail_code(exc: HTTPException, fallback: str) -> str:
    return str(exc.detail.get("code", fallback)) if isinstance(exc.detail, dict) else fallback
