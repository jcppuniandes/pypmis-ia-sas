"""Gate 07M-BC orchestration without duplicating upstream calculations."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, AdminNumberSequence, EnterpriseWorkspace, SecurityEvent
from app.modules.business_case.models import BusinessCase, BusinessCaseDecisionSnapshot, BusinessCaseRevision
from app.modules.business_case.schemas import (
    BusinessCaseOut,
    BusinessCaseRevisionOut,
    ConfigurationPreviewOut,
    ReadinessOut,
    RefreshPreviewOut,
)
from app.modules.funds_manager.models import FundingReadinessSnapshot
from app.modules.permit_readiness.models import PermitReadinessAssessment
from app.modules.portfolio_budget.models import PortfolioBudgetScenario, PortfolioBudgetScenarioProject
from app.modules.portfolio_resource.models import PortfolioResourceScenario, PortfolioResourceScenarioProject
from app.modules.project_creation.models import ProjectCreationRequest
from app.modules.project_definition.models import ProjectFELStatus
from app.modules.project_proposal.models import ProjectProposal
from app.modules.risk_readiness.models import RiskReadinessAssessment

CONFIGURATION_KIND = "business_case_governance_configuration"
READY_OUTPUT = "READY_FOR_GOVERNED_BUSINESS_CASE_EVIDENCE"
FIVE_CASE_READY_OUTPUT = "READY_FOR_GOVERNED_FIVE_CASE_BUSINESS_CASE_EVIDENCE"
NEXT_PROCESS = "BUILD_GATE07M_FIN"
FIVE_CASE_SCHEMA_VERSION = "1.0"
FIVE_CASE_KEYS = (
    "strategic_case",
    "economic_case",
    "commercial_case",
    "financial_case",
    "management_case",
)
CASE_SOURCE_MAP: dict[str, tuple[str, ...]] = {
    "strategic_case": ("idea", "business_analysis", "proposal", "benefits"),
    "economic_case": ("business_analysis", "proposal", "benefits", "economic_financial_model", "risk"),
    "commercial_case": ("commercial_strategy",),
    "financial_case": ("budget", "funding", "economic_financial_model", "benefits"),
    "management_case": ("fel", "resource", "risk", "permit", "benefits", "commercial_strategy"),
}
QRA_CASE_SOURCE_MAP = {
    "economic_case": ("cost_qra_result",),
    "financial_case": ("cost_qra_result",),
    "management_case": ("schedule_qra_result",),
}


def _case_sources(case_key: str, references: dict) -> tuple[str, ...]:
    # Only revisions which explicitly captured this increment receive the new
    # projection. Adding empty rows globally would change historical 5C hashes.
    return CASE_SOURCE_MAP[case_key] + (
        QRA_CASE_SOURCE_MAP.get(case_key, ()) if references.get("_qra_evidence") else ()
    )


CASE_QUESTIONS = {
    "strategic_case": "Why should the organization intervene and how does the investment align with strategy?",
    "economic_case": "Which option provides the best overall value?",
    "commercial_case": "Can the preferred option be procured and commercially structured?",
    "financial_case": "Can the organization afford and finance the investment?",
    "management_case": "Can the organization deliver and govern the investment successfully?",
}
REVISION_PURPOSES = {
    "INITIAL_PROPOSAL",
    "FEL_1_UPDATE",
    "FEL_2_UPDATE",
    "INVESTMENT_SELECTION_UPDATE",
    "FEL_3_UPDATE",
    "FFA_UPDATE",
    "MATERIAL_CHANGE_UPDATE",
    "REVALIDATION",
    "OTHER",
}
SNAPSHOT_TYPES = {
    "INVESTMENT_SELECTION",
    "FULL_FUNDS_AUTHORIZATION",
    "OTHER_CONFIGURED_GATE",
}


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


DEFAULT_CONFIGURATION: dict[str, Any] = {
    "applicable_project_types": ["*"],
    "applicable_governance_models": ["CAPITAL_OWNER", "PYP", "*"],
    "applicable_gate_profiles": ["PYP-FFA", "*"],
    "applicable_fel_stages": ["FEL-1", "FEL-2", "FEL-3", "FFA", "*"],
    "mapping": {
        "title": "proposal.name",
        "business_need": "proposal.business_need",
        "executive_summary": "proposal.business_justification",
        "objectives": "proposal.project_objectives_json",
        "scope": ["proposal.preliminary_scope", "proposal.out_of_scope"],
        "benefits": "proposal.expected_benefits",
    },
    "required_sections": ["title", "business_need", "objectives", "scope"],
    "required_sources_by_stage": {
        "FEL-1": ["proposal"],
        "FEL-2": ["proposal", "fel"],
        "FEL-3": ["proposal", "fel", "budget", "resource", "risk", "permit"],
        "FFA": ["proposal", "fel", "budget", "resource", "funding", "risk", "permit"],
    },
    "separation_of_duties": {"reviewer_must_differ_from_preparer": True, "pyp_ffa_strict": True},
    "freshness": {"require_current_sources": True},
    "material_change": {
        "tracked_sources": [
            "idea",
            "business_analysis",
            "proposal",
            "benefits",
            "commercial_strategy",
            "fel",
            "budget",
            "resource",
            "funding",
            "economic_financial_model",
            "risk",
            "permit",
        ],
        "recommendation_only_after_selection_or_fid": True,
    },
    "five_case": {
        "schema_version": FIVE_CASE_SCHEMA_VERSION,
        "enabled_governance_models": ["CAPITAL_OWNER"],
        "enforce_readiness": True,
        "required_cases_by_stage": {
            "FEL-1": ["strategic_case"],
            "FEL-2": ["strategic_case", "economic_case", "commercial_case", "management_case"],
            "INVESTMENT_SELECTION": [
                "strategic_case",
                "economic_case",
                "commercial_case",
                "management_case",
            ],
            "FEL-3": list(FIVE_CASE_KEYS),
            "FFA": list(FIVE_CASE_KEYS),
        },
        "source_requirements_by_stage": {
            "FEL-1": {"strategic_case": ["proposal"]},
            "FEL-2": {
                "strategic_case": ["proposal", "business_analysis", "benefits"],
                "economic_case": ["business_analysis"],
                "commercial_case": ["commercial_strategy"],
                "management_case": ["fel"],
            },
            "INVESTMENT_SELECTION": {
                "strategic_case": ["proposal", "business_analysis", "benefits"],
                "economic_case": ["business_analysis", "economic_financial_model", "risk"],
                "commercial_case": ["commercial_strategy"],
                "management_case": ["fel", "benefits", "commercial_strategy"],
            },
            "FEL-3": {
                "strategic_case": ["proposal", "business_analysis", "benefits"],
                "economic_case": ["business_analysis", "economic_financial_model", "risk"],
                "commercial_case": ["commercial_strategy"],
                "financial_case": ["budget", "economic_financial_model"],
                "management_case": ["fel", "resource", "risk", "permit", "benefits", "commercial_strategy"],
            },
            "FFA": {
                "strategic_case": ["proposal", "business_analysis", "benefits"],
                "economic_case": ["business_analysis", "economic_financial_model", "risk"],
                "commercial_case": ["commercial_strategy"],
                "financial_case": ["budget", "funding", "economic_financial_model"],
                "management_case": ["fel", "resource", "risk", "permit", "benefits", "commercial_strategy"],
            },
        },
        "future_sources": {
            "qra_confidence": "NOT_AVAILABLE",
            "basic_data_readiness": "NOT_AVAILABLE",
            "owner_capability_readiness": "NOT_AVAILABLE",
        },
    },
    "scope": {"workspace_id": None, "inherit_to_descendants": True},
}


class BusinessCaseService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int, context=None) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.context = context

    # Configuration ---------------------------------------------------------
    def ensure_seed(self) -> None:
        existing = self.db.scalar(
            select(AdminConfiguration.id).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.status == "published",
            )
        )
        if existing is not None:
            return
        content = deepcopy(DEFAULT_CONFIGURATION)
        self.db.add(
            AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=CONFIGURATION_KIND,
                code="default",
                name="Default Governed Business Case Policy",
                description="Gate 07M-BC mapping, readiness, SoD, freshness and material-change policy.",
                status="published",
                revision=1,
                version=1,
                content_json=content,
                content_hash=_hash(content),
                published_at=utc_now(),
                created_by_user_id=self.actor_id,
            )
        )
        self._event("business_case.configuration_published", "AdminConfiguration", None, {"seed": True})
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()

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
        self, project_workspace_id: int | None, configuration_id: int | None, content_json: dict | None
    ) -> ConfigurationPreviewOut:
        base = self._configuration(configuration_id) if configuration_id else self._published_configuration()
        content = deepcopy(content_json if content_json is not None else base.content_json)
        issues = self._configuration_issues(content)
        chain: list[dict] = []
        warnings: list[str] = []
        if project_workspace_id:
            project = self._project(project_workspace_id)
            _, chain = self._resolve_configuration(project, override=base if configuration_id else None)
        else:
            warnings.append("NO_PROJECT_SELECTED_FOR_RESOLUTION_PREVIEW")
        return ConfigurationPreviewOut(
            effective=content,
            resolution_chain=chain,
            validation_issues=issues,
            warnings=warnings,
            publishable=not issues,
            persisted=False,
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id, lock=True)
        self._check_version(source.version, expected_version)
        revision = (
            int(
                self.db.scalar(
                    select(func.max(AdminConfiguration.revision)).where(
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
            name=f"{source.name} R{revision}",
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=deepcopy(source.content_json),
            content_hash=source.content_hash,
            created_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self._event(
            "business_case.configuration_cloned",
            "AdminConfiguration",
            source.id,
            {"revision": revision},
        )
        self.db.commit()
        self.db.refresh(clone)
        return clone

    def update_configuration(
        self, configuration_id: int, expected_version: int, *, name: str, description: str, content_json: dict
    ) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_IMMUTABLE"})
        issues = self._configuration_issues(content_json)
        if issues:
            raise HTTPException(
                status_code=422, detail={"code": "INVALID_BUSINESS_CASE_CONFIGURATION", "issues": issues}
            )
        record.name = name
        record.description = description
        record.content_json = deepcopy(content_json)
        record.content_hash = _hash(content_json)
        record.version += 1
        record.updated_at = utc_now()
        self._event(
            "business_case.configuration_updated",
            "AdminConfiguration",
            record.id,
            {"revision": record.revision},
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version)
        if record.status == "published":
            return record
        issues = self._configuration_issues(record.content_json)
        if issues:
            raise HTTPException(
                status_code=422, detail={"code": "INVALID_BUSINESS_CASE_CONFIGURATION", "issues": issues}
            )
        record.status = "published"
        record.published_at = utc_now()
        record.version += 1
        record.updated_at = utc_now()
        self._event(
            "business_case.configuration_published", "AdminConfiguration", record.id, {"revision": record.revision}
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    # Aggregate -------------------------------------------------------------
    def list(self, project_workspace_id: int | None = None) -> list[BusinessCaseOut]:
        statement = select(BusinessCase).where(BusinessCase.tenant_id == self.tenant_id)
        if project_workspace_id is not None:
            statement = statement.where(BusinessCase.project_workspace_id == project_workspace_id)
        records = list(self.db.scalars(statement.order_by(BusinessCase.updated_at.desc())).all())
        return [self._case_out(record) for record in records]

    def get(self, business_case_id: int) -> BusinessCaseOut:
        return self._case_out(self._case(business_case_id))

    def by_project(self, project_workspace_id: int) -> BusinessCaseOut:
        record = self.db.scalar(
            select(BusinessCase).where(
                BusinessCase.tenant_id == self.tenant_id,
                BusinessCase.project_workspace_id == project_workspace_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "BUSINESS_CASE_NOT_FOUND"})
        return self._case_out(record)

    def create(
        self,
        project_workspace_id: int,
        source_project_proposal_id: int | None,
        owner_user_id: int | None,
        sponsor_user_id: int | None,
        idempotency_key: str,
    ) -> BusinessCaseOut:
        duplicate = self.db.scalar(
            select(BusinessCase).where(
                BusinessCase.tenant_id == self.tenant_id,
                BusinessCase.create_idempotency_key == idempotency_key,
            )
        )
        if duplicate:
            return self._case_out(duplicate)
        project = self._project(project_workspace_id)
        existing = self.db.scalar(
            select(BusinessCase).where(
                BusinessCase.tenant_id == self.tenant_id,
                BusinessCase.project_workspace_id == project.id,
            )
        )
        if existing:
            raise HTTPException(status_code=409, detail={"code": "BUSINESS_CASE_ALREADY_EXISTS_FOR_PROJECT"})
        proposal = self._proposal_for_project(project.id, source_project_proposal_id)
        config, chain = self._resolve_configuration(project)
        number = self._next_number()
        record = BusinessCase(
            tenant_id=self.tenant_id,
            business_case_number=number,
            project_workspace_id=project.id,
            source_project_proposal_id=proposal.id,
            owning_workspace_id=proposal.owning_workspace_id,
            owner_user_id=owner_user_id or proposal.proposal_owner_user_id,
            sponsor_user_id=sponsor_user_id or proposal.sponsor_user_id,
            status="DRAFT",
            configuration_id=config.id,
            configuration_revision=config.revision,
            configuration_hash=config.content_hash,
            configuration_source_workspace_id=self._chain_source_id(chain),
            configuration_resolution_chain_json=chain,
            create_idempotency_key=idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        revision = self._new_revision(
            record, "INITIAL_PROPOSAL", idempotency_key=f"{idempotency_key}:R1", proposal=proposal
        )
        record.current_revision_id = revision.id
        self._event("business_case.created", "BusinessCase", record.id, {"project_workspace_id": project.id})
        self.db.commit()
        return self._case_out(record)

    def revisions(self, business_case_id: int) -> list[BusinessCaseRevisionOut]:
        self._case(business_case_id)
        return [
            self._revision_out(item)
            for item in self.db.scalars(
                select(BusinessCaseRevision)
                .where(
                    BusinessCaseRevision.tenant_id == self.tenant_id,
                    BusinessCaseRevision.business_case_id == business_case_id,
                )
                .order_by(BusinessCaseRevision.revision_number.desc())
            ).all()
        ]

    def create_revision(self, business_case_id: int, purpose: str, idempotency_key: str) -> BusinessCaseRevisionOut:
        if purpose not in REVISION_PURPOSES or purpose == "INITIAL_PROPOSAL":
            raise HTTPException(status_code=422, detail={"code": "INVALID_BUSINESS_CASE_REVISION_PURPOSE"})
        duplicate = self.db.scalar(
            select(BusinessCaseRevision).where(
                BusinessCaseRevision.tenant_id == self.tenant_id,
                BusinessCaseRevision.create_idempotency_key == idempotency_key,
            )
        )
        if duplicate:
            return self._revision_out(duplicate)
        case = self._case(business_case_id, lock=True)
        current = self._current_revision(case)
        if current.status not in {"COMPLETED", "VOIDED"}:
            raise HTTPException(status_code=409, detail={"code": "OPEN_BUSINESS_CASE_REVISION_EXISTS"})
        revision = self._new_revision(case, purpose, idempotency_key=idempotency_key, source=current)
        case.current_revision_id = revision.id
        case.status = "ACTIVE"
        case.updated_by = self.actor_id
        case.updated_at = utc_now()
        case.revision_version += 1
        self._event("business_case.revision_created", "BusinessCaseRevision", revision.id, {"purpose": purpose})
        self.db.commit()
        self.db.refresh(revision)
        return self._revision_out(revision)

    def update_revision(
        self, revision_id: int, expected_version: int, values: dict[str, Any]
    ) -> BusinessCaseRevisionOut:
        revision = self._revision(revision_id, lock=True)
        self._check_version(revision.revision_version, expected_version)
        if revision.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "BUSINESS_CASE_REVISION_NOT_EDITABLE"})
        mapping = {
            "strategic_alignment": "strategic_alignment_json",
            "objectives": "objectives_json",
            "scope": "scope_json",
            "alternatives": "alternatives_json",
            "benefits": "benefits_json",
            "assumptions": "assumptions_json",
            "constraints": "constraints_json",
            "delivery": "delivery_json",
            "unresolved_concerns": "unresolved_concerns_json",
            "recommendation": "recommendation_json",
        }
        for key, value in values.items():
            if value is not None:
                setattr(revision, mapping.get(key, key), value)
        revision.content_hash = self._content_hash(revision)
        revision.updated_by = self.actor_id
        revision.updated_at = utc_now()
        revision.revision_version += 1
        self._event("business_case.revision_updated", "BusinessCaseRevision", revision.id, {})
        self.db.commit()
        self.db.refresh(revision)
        return self._revision_out(revision)

    def submit_review(self, revision_id: int, expected_version: int, idempotency_key: str) -> BusinessCaseRevisionOut:
        revision = self._revision(revision_id, lock=True)
        self._check_version(revision.revision_version, expected_version)
        if revision.status == "IN_REVIEW" and revision.create_idempotency_key == idempotency_key:
            return self._revision_out(revision)
        if revision.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "BUSINESS_CASE_REVISION_NOT_DRAFT"})
        revision.status = "IN_REVIEW"
        revision.submitted_at = utc_now()
        revision.updated_by = self.actor_id
        revision.updated_at = utc_now()
        revision.revision_version += 1
        self._event("business_case.review_submitted", "BusinessCaseRevision", revision.id, {})
        self.db.commit()
        self.db.refresh(revision)
        return self._revision_out(revision)

    def complete_revision(
        self, revision_id: int, expected_version: int, idempotency_key: str, reviewer_user_id: int | None
    ) -> BusinessCaseRevisionOut:
        duplicate = self.db.scalar(
            select(BusinessCaseRevision).where(
                BusinessCaseRevision.tenant_id == self.tenant_id,
                BusinessCaseRevision.complete_idempotency_key == idempotency_key,
            )
        )
        if duplicate:
            return self._revision_out(duplicate)
        revision = self._revision(revision_id, lock=True)
        self._check_version(revision.revision_version, expected_version)
        if revision.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "BUSINESS_CASE_REVISION_NOT_IN_REVIEW"})
        reviewer = reviewer_user_id or self.actor_id
        case = self._case(revision.business_case_id)
        config = self._configuration(case.configuration_id)
        sod = dict(config.content_json.get("separation_of_duties", {}))
        if sod.get("reviewer_must_differ_from_preparer", True) and reviewer == revision.preparer_user_id:
            raise HTTPException(status_code=409, detail={"code": "BUSINESS_CASE_REVIEWER_PREPARER_SOD"})
        readiness = self._evaluate_readiness(case, revision, config)
        if readiness.status != "READY":
            raise HTTPException(
                status_code=409,
                detail={"code": "BUSINESS_CASE_NOT_READY", "blockers": readiness.blockers},
            )
        revision.reviewer_user_id = reviewer
        revision.completed_by = reviewer
        revision.completed_at = utc_now()
        revision.complete_idempotency_key = idempotency_key
        revision.readiness_status = readiness.status
        revision.readiness_warnings_json = readiness.warnings
        revision.readiness_blockers_json = readiness.blockers
        revision.readiness_hash = readiness.readiness_hash
        revision.status = "COMPLETED"
        revision.updated_by = reviewer
        revision.updated_at = utc_now()
        revision.revision_version += 1
        case.status = "ACTIVE"
        case.updated_by = reviewer
        case.updated_at = utc_now()
        case.revision_version += 1
        self._event("business_case.review_completed", "BusinessCaseRevision", revision.id, {})
        self._event("business_case.revision_completed", "BusinessCaseRevision", revision.id, {})
        self.db.commit()
        self.db.refresh(revision)
        return self._revision_out(revision)

    def readiness(self, business_case_id: int) -> ReadinessOut:
        case = self._case(business_case_id)
        revision = self._current_revision(case)
        return self._evaluate_readiness(case, revision, self._configuration(case.configuration_id))

    def refresh_preview(self, business_case_id: int, *, audit: bool = True) -> RefreshPreviewOut:
        case = self._case(business_case_id)
        current = self._current_revision(case)
        refs, hashes = self._source_bundle(case.project_workspace_id, case.source_project_proposal_id)
        previous_hashes = dict(current.source_hashes_json or {})
        changes = []
        for key in sorted(set(previous_hashes) | set(hashes)):
            before = previous_hashes.get(key)
            after = hashes.get(key)
            if before == after:
                continue
            change_type = "ADDED" if before is None else "REMOVED" if after is None else "CHANGED"
            changes.append({"source": key, "from": before, "to": after, "change_type": change_type})
        material = "MATERIAL_CHANGE_REVIEW_REQUIRED" if changes and self._snapshots(case.id) else "NO_MATERIAL_CHANGE"
        recommended_purpose = "MATERIAL_CHANGE_UPDATE" if material != "NO_MATERIAL_CHANGE" else "REVALIDATION"

        previous_contract = self._five_case_contract(case, current)
        preview_refs = deepcopy(refs)
        previous_marker = dict((current.source_references_json or {}).get("_five_case") or {})
        if previous_marker:
            preview_marker = deepcopy(previous_marker)
            preview_context = dict(preview_marker.get("gate_context") or {})
            preview_context["fel_stage"] = (preview_refs.get("fel") or {}).get("stage") or preview_context.get(
                "fel_stage", current.fel_stage_code or "FEL-1"
            )
            preview_context["policy_stage"] = self._five_case_stage(
                recommended_purpose, str(preview_context["fel_stage"])
            )
            preview_context["decision_gate"] = (
                "INVESTMENT_SELECTION" if preview_context["policy_stage"] == "INVESTMENT_SELECTION" else None
            )
            preview_marker["gate_context"] = preview_context
            preview_refs["_five_case"] = preview_marker
        else:
            preview_refs["_five_case"] = self._five_case_marker(
                case,
                purpose=recommended_purpose,
                as_of_date=current.as_of_date,
                references=preview_refs,
            )
        prospective_contract = self._five_case_contract(
            case,
            current,
            references=preview_refs,
            hashes=hashes,
            force_five_case=True,
        )
        changes_by_case = {
            case_key: [deepcopy(item) for item in changes if item["source"] in _case_sources(case_key, preview_refs)]
            for case_key in FIVE_CASE_KEYS
        }
        readiness_keys = (*FIVE_CASE_KEYS, "overall_business_case_readiness")
        readiness_delta = {
            key: {
                "from": previous_contract["five_case_readiness_json"].get(key, "LEGACY"),
                "to": prospective_contract["five_case_readiness_json"].get(key, "LEGACY"),
            }
            for key in readiness_keys
        }
        previous_warnings = set(previous_contract["warnings"])
        previous_blockers = set(previous_contract["blockers"])
        result = RefreshPreviewOut(
            business_case_id=case.id,
            current_revision_id=current.id,
            source_changes=changes,
            material_change_status=material,
            recommended_purpose=recommended_purpose,
            persisted=False,
            source_changes_by_case=changes_by_case,
            case_readiness_delta=readiness_delta,
            five_case_delta={
                "changed": previous_contract["five_case_hash"] != prospective_contract["five_case_hash"],
                "from_five_case_hash": previous_contract["five_case_hash"],
                "to_five_case_hash": prospective_contract["five_case_hash"],
                "from_source_bundle_hash": previous_contract["source_bundle_hash"],
                "to_source_bundle_hash": prospective_contract["source_bundle_hash"],
            },
            new_warnings=sorted(set(prospective_contract["warnings"]) - previous_warnings),
            new_blockers=sorted(set(prospective_contract["blockers"]) - previous_blockers),
        )
        if audit:
            self._event(
                "business_case.refresh_previewed",
                "BusinessCase",
                case.id,
                {"source_changes": changes, "material_change_status": material},
            )
            if changes:
                self._event(
                    "business_case.source_stale_detected",
                    "BusinessCase",
                    case.id,
                    {"source_changes": changes},
                )
            if material == "MATERIAL_CHANGE_REVIEW_REQUIRED":
                self._event(
                    "business_case.material_change_detected",
                    "BusinessCase",
                    case.id,
                    {"source_changes": changes},
                )
            self.db.commit()
        return result

    def refresh(self, business_case_id: int, expected_version: int, idempotency_key: str) -> BusinessCaseRevisionOut:
        duplicate = self.db.scalar(
            select(BusinessCaseRevision).where(
                BusinessCaseRevision.tenant_id == self.tenant_id,
                BusinessCaseRevision.refresh_idempotency_key == idempotency_key,
            )
        )
        if duplicate:
            return self._revision_out(duplicate)
        case = self._case(business_case_id, lock=True)
        self._check_version(case.revision_version, expected_version)
        current = self._current_revision(case)
        if current.status not in {"COMPLETED", "VOIDED"}:
            raise HTTPException(status_code=409, detail={"code": "OPEN_BUSINESS_CASE_REVISION_EXISTS"})
        preview = self.refresh_preview(case.id, audit=False)
        revision = self._new_revision(case, preview.recommended_purpose, idempotency_key=None, source=current)
        revision.refresh_idempotency_key = idempotency_key
        revision.material_change_status = preview.material_change_status
        case.current_revision_id = revision.id
        case.updated_by = self.actor_id
        case.updated_at = utc_now()
        case.revision_version += 1
        self._event(
            "business_case.refresh_applied",
            "BusinessCaseRevision",
            revision.id,
            {"source_changes": preview.source_changes, "new_revision": revision.revision_label},
        )
        self.db.commit()
        self.db.refresh(revision)
        return self._revision_out(revision)

    def snapshots(self, business_case_id: int) -> list[BusinessCaseDecisionSnapshot]:
        self._case(business_case_id)
        return self._snapshots(business_case_id)

    def create_snapshot(
        self,
        business_case_id: int,
        revision_id: int,
        snapshot_type: str,
        decision_reference_type: str | None,
        decision_reference_id: int | None,
        decision_reference_hash: str | None,
        idempotency_key: str,
    ) -> BusinessCaseDecisionSnapshot:
        if snapshot_type not in SNAPSHOT_TYPES:
            raise HTTPException(status_code=422, detail={"code": "INVALID_BUSINESS_CASE_SNAPSHOT_TYPE"})
        duplicate = self.db.scalar(
            select(BusinessCaseDecisionSnapshot).where(
                BusinessCaseDecisionSnapshot.tenant_id == self.tenant_id,
                BusinessCaseDecisionSnapshot.idempotency_key == idempotency_key,
            )
        )
        if duplicate:
            return duplicate
        case = self._case(business_case_id)
        revision = self._revision(revision_id)
        if revision.business_case_id != case.id or revision.status != "COMPLETED":
            raise HTTPException(status_code=409, detail={"code": "COMPLETED_BUSINESS_CASE_REVISION_REQUIRED"})
        five_case_contract = self._five_case_contract(case, revision)
        payload = {
            "business_case_number": case.business_case_number,
            "business_case_id": case.id,
            "project_workspace_id": case.project_workspace_id,
            "revision": revision.revision_label,
            "purpose": revision.purpose,
            "as_of_date": revision.as_of_date.isoformat(),
            "fel_stage_code": revision.fel_stage_code,
            "content_hash": revision.content_hash,
            "strategic_case": {
                "title": revision.title,
                "executive_summary": revision.executive_summary,
                "business_need": revision.business_need,
                "strategic_alignment": revision.strategic_alignment_json,
                "objectives": revision.objectives_json,
            },
            "alternatives": revision.alternatives_json,
            "scope": revision.scope_json,
            "benefits": revision.benefits_json,
            "execution": revision.delivery_json,
            "assumptions": revision.assumptions_json,
            "constraints": revision.constraints_json,
            "unresolved_concerns": revision.unresolved_concerns_json,
            "source_references": revision.source_references_json,
            "source_hashes": revision.source_hashes_json,
            "source_evidence_matrix": five_case_contract["source_evidence_matrix_json"],
            "gate_context": five_case_contract["gate_context_json"],
            "five_case": five_case_contract["five_case_json"],
            "five_case_readiness": five_case_contract["five_case_readiness_json"],
            "five_case_hash": five_case_contract["five_case_hash"],
            "source_bundle_hash": five_case_contract["source_bundle_hash"],
            "business_case_hash": five_case_contract["business_case_hash"],
            "source_current": five_case_contract["source_current"],
            "legacy_layout": five_case_contract["legacy_layout"],
            "readiness_hash": revision.readiness_hash,
            "recommendation": revision.recommendation_json,
            "economic_financial_model_reference": {
                "id": revision.economic_financial_model_id,
                "version": revision.economic_financial_model_version,
                "hash": revision.economic_financial_model_hash,
                "status": revision.financial_model_status,
                "readiness": revision.economic_financial_readiness,
                "as_of_date": (
                    revision.economic_financial_as_of_date.isoformat()
                    if revision.economic_financial_as_of_date
                    else None
                ),
            },
        }
        record = BusinessCaseDecisionSnapshot(
            tenant_id=self.tenant_id,
            business_case_id=case.id,
            business_case_revision_id=revision.id,
            snapshot_type=snapshot_type,
            decision_reference_type=decision_reference_type,
            decision_reference_id=decision_reference_id,
            decision_reference_hash=decision_reference_hash,
            revision_content_hash=revision.content_hash,
            source_snapshot_hash=revision.source_snapshot_hash,
            snapshot_json=payload,
            snapshot_hash=_hash(payload),
            idempotency_key=idempotency_key,
            created_by=self.actor_id,
        )
        self.db.add(record)
        self._event("business_case.snapshot_created", "BusinessCaseDecisionSnapshot", None, {"type": snapshot_type})
        self.db.commit()
        self.db.refresh(record)
        return record

    def material_change(self, business_case_id: int) -> RefreshPreviewOut:
        return self.refresh_preview(business_case_id)

    def review_material_change(
        self, business_case_id: int, expected_version: int, outcome: str, rationale: str, idempotency_key: str
    ) -> BusinessCaseOut:
        case = self._case(business_case_id, lock=True)
        self._check_version(case.revision_version, expected_version)
        prior = dict(case.material_change_review_json or {})
        if prior.get("idempotency_key") == idempotency_key:
            return self._case_out(case)
        if outcome not in {"ACKNOWLEDGED", "REVISION_REQUIRED", "NO_ACTION"}:
            raise HTTPException(status_code=422, detail={"code": "INVALID_MATERIAL_CHANGE_REVIEW_OUTCOME"})
        case.material_change_review_json = {
            "outcome": outcome,
            "rationale": rationale,
            "reviewed_by": self.actor_id,
            "reviewed_at": utc_now().isoformat(),
            "idempotency_key": idempotency_key,
            "recommendation_only": True,
        }
        case.updated_by = self.actor_id
        case.updated_at = utc_now()
        case.revision_version += 1
        self._event("business_case.material_change_reviewed", "BusinessCase", case.id, {"outcome": outcome})
        self.db.commit()
        return self._case_out(case)

    # Internal --------------------------------------------------------------
    def _new_revision(
        self,
        case: BusinessCase,
        purpose: str,
        *,
        idempotency_key: str | None,
        proposal: ProjectProposal | None = None,
        source: BusinessCaseRevision | None = None,
    ) -> BusinessCaseRevision:
        number = (
            int(
                self.db.scalar(
                    select(func.max(BusinessCaseRevision.revision_number)).where(
                        BusinessCaseRevision.tenant_id == self.tenant_id,
                        BusinessCaseRevision.business_case_id == case.id,
                    )
                )
                or 0
            )
            + 1
        )
        proposal = proposal or self._proposal(case.source_project_proposal_id)
        refs, hashes = self._source_bundle(case.project_workspace_id, proposal.id)
        as_of_date = utc_now()
        # An explicit marker lets old rows remain genuinely legacy-readable.
        # It is metadata, not an external evidence source, and therefore is not
        # included in ``source_hashes_json`` or current/stale comparisons.
        refs["_five_case"] = self._five_case_marker(
            case,
            purpose=purpose,
            as_of_date=as_of_date,
            references=refs,
        )
        financial_ref = refs.get("economic_financial_model") or {}
        financial_as_of_date = financial_ref.get("as_of_date")
        if isinstance(financial_as_of_date, str):
            financial_as_of_date = datetime.fromisoformat(financial_as_of_date)
        if source:
            narrative = {
                "title": source.title,
                "executive_summary": source.executive_summary,
                "business_need": source.business_need,
                "strategic_alignment_json": deepcopy(source.strategic_alignment_json),
                "objectives_json": deepcopy(source.objectives_json),
                "scope_json": deepcopy(source.scope_json),
                "alternatives_json": deepcopy(source.alternatives_json),
                "benefits_json": deepcopy(source.benefits_json),
                "assumptions_json": deepcopy(source.assumptions_json),
                "constraints_json": deepcopy(source.constraints_json),
                "delivery_json": deepcopy(source.delivery_json),
                "unresolved_concerns_json": deepcopy(source.unresolved_concerns_json),
                "recommendation_json": deepcopy(source.recommendation_json),
            }
        else:
            narrative = {
                "title": proposal.name,
                "executive_summary": proposal.business_justification,
                "business_need": proposal.business_need,
                "strategic_alignment_json": [{"code": code} for code in (proposal.strategic_objective_codes or [])],
                "objectives_json": deepcopy(proposal.project_objectives_json or []),
                "scope_json": {"in_scope": proposal.preliminary_scope, "out_of_scope": proposal.out_of_scope},
                "alternatives_json": [],
                "benefits_json": ([{"description": proposal.expected_benefits}] if proposal.expected_benefits else []),
                "assumptions_json": deepcopy(proposal.assumptions_json or []),
                "constraints_json": deepcopy(proposal.constraints_json or []),
                "delivery_json": {
                    "rom_cost": str(proposal.rom_cost) if proposal.rom_cost is not None else None,
                    "currency": proposal.currency_code,
                    "target_start": str(proposal.target_start_date) if proposal.target_start_date else None,
                    "target_finish": str(proposal.target_finish_date) if proposal.target_finish_date else None,
                },
                "unresolved_concerns_json": deepcopy(proposal.key_risks_json or []),
                "recommendation_json": {"status": "NOT_PREPARED", "is_decision": False},
            }
        record = BusinessCaseRevision(
            tenant_id=self.tenant_id,
            business_case_id=case.id,
            revision_number=number,
            revision_label=f"R{number}",
            purpose=purpose,
            status="DRAFT",
            as_of_date=as_of_date,
            fel_stage_code=(refs.get("fel") or {}).get("stage"),
            source_references_json=refs,
            source_hashes_json=hashes,
            source_snapshot_hash=_hash({"references": refs, "hashes": hashes}),
            economic_financial_model_id=financial_ref.get("id", source.economic_financial_model_id if source else None),
            economic_financial_model_version=financial_ref.get(
                "version", source.economic_financial_model_version if source else None
            ),
            economic_financial_model_hash=hashes.get(
                "economic_financial_model", source.economic_financial_model_hash if source else None
            ),
            financial_model_status=financial_ref.get(
                "financial_model_status", source.financial_model_status if source else "NOT_AVAILABLE"
            ),
            economic_financial_readiness=financial_ref.get(
                "readiness", source.economic_financial_readiness if source else None
            ),
            economic_financial_as_of_date=(
                financial_as_of_date
                if financial_as_of_date is not None
                else (source.economic_financial_as_of_date if source else None)
            ),
            readiness_status="NOT_STARTED",
            readiness_hash=_hash({"status": "NOT_STARTED", "sources": hashes}),
            material_change_status="NO_MATERIAL_CHANGE",
            preparer_user_id=self.actor_id,
            create_idempotency_key=idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
            **narrative,
        )
        record.content_hash = self._content_hash(record)
        self.db.add(record)
        self.db.flush()
        return record

    def _source_bundle(self, project_id: int, proposal_id: int | None) -> tuple[dict, dict]:
        refs: dict[str, Any] = {}
        hashes: dict[str, str] = {}
        proposal = self._proposal(proposal_id)
        refs["proposal"] = {
            "id": proposal.id,
            "number": proposal.proposal_number,
            "status": proposal.status,
            "readiness": proposal.status,
            "source_current": True,
            "as_of_date": proposal.updated_at.isoformat(),
        }
        hashes["proposal"] = _hash(
            {
                "id": proposal.id,
                "version": proposal.revision_version,
                "mapping_hash": proposal.mapping_hash,
                "updated_at": proposal.updated_at,
            }
        )
        # Five Case consumes, but never owns, these governed sources.  Imports
        # remain local because Benefits and Commercial also reference the
        # Business Case aggregate and must not form an import cycle.
        from app.modules.business_analysis.models import BusinessAnalysis
        from app.modules.commercial_strategy.models import (
            CommercialContractingStrategy,
            CommercialStrategyVersion,
        )
        from app.modules.idea_demand.models import Idea
        from app.modules.strategic_benefits.models import (
            StrategicBenefitsPlan,
            StrategicBenefitsPlanVersion,
        )

        idea = self.db.scalar(
            select(Idea).where(
                Idea.tenant_id == self.tenant_id,
                Idea.id == proposal.source_idea_id,
            )
        )
        if idea:
            refs["idea"] = {
                "id": idea.id,
                "number": idea.idea_number,
                "status": idea.state,
                "title": idea.title,
                "as_of_date": idea.updated_at.isoformat(),
                "source_current": True,
            }
            hashes["idea"] = _hash(
                {
                    "id": idea.id,
                    "version": idea.revision_version,
                    "state": idea.state,
                    "updated_at": idea.updated_at,
                }
            )

        # The Proposal carries the governed BA lineage.  Never choose a
        # different Analysis merely because it shares the same Idea.
        analysis = (
            self.db.scalar(
                select(BusinessAnalysis).where(
                    BusinessAnalysis.tenant_id == self.tenant_id,
                    BusinessAnalysis.id == proposal.source_business_analysis_id,
                    BusinessAnalysis.source_idea_id == proposal.source_idea_id,
                )
            )
            if proposal.source_business_analysis_id is not None
            else None
        )
        if analysis:
            hash_matches_proposal = bool(
                proposal.source_business_analysis_hash
                and proposal.source_business_analysis_hash == analysis.completion_hash
            )
            analysis_content = dict(analysis.content_json or {})
            content_recommended_option_id = analysis_content.get("recommended_option_id")
            proposal_recommended_option_id = dict(proposal.source_values_snapshot_json or {}).get(
                "recommended_option_id"
            )
            option_ids = {
                str(item.get("id"))
                for item in list(analysis_content.get("options") or [])
                if item.get("id") is not None
            }
            recommended_option_current = bool(
                analysis.recommended_option_id
                and str(analysis.recommended_option_id) == str(content_recommended_option_id)
                and str(analysis.recommended_option_id) == str(proposal_recommended_option_id)
                and str(analysis.recommended_option_id) in option_ids
            )
            refs["business_analysis"] = {
                "id": analysis.id,
                "number": analysis.analysis_number,
                "status": analysis.status,
                "readiness": (analysis.readiness_json or {}).get("status", "READY"),
                "recommended_option_id": analysis.recommended_option_id,
                "content_recommended_option_id": content_recommended_option_id,
                "proposal_recommended_option_id": proposal_recommended_option_id,
                "recommended_option_current": recommended_option_current,
                "as_of_date": (analysis.completed_at or analysis.updated_at).isoformat(),
                "source_current": (
                    analysis.status == "COMPLETED" and hash_matches_proposal and recommended_option_current
                ),
                "proposal_source_hash": proposal.source_business_analysis_hash,
                "lineage_hash_match": hash_matches_proposal,
            }
            hashes["business_analysis"] = analysis.completion_hash or _hash(
                {
                    "id": analysis.id,
                    "version": analysis.revision_version,
                    "content": analysis.content_json,
                    "recommended_option_id": analysis.recommended_option_id,
                }
            )

        benefits_plan = self.db.scalar(
            select(StrategicBenefitsPlan).where(
                StrategicBenefitsPlan.tenant_id == self.tenant_id,
                StrategicBenefitsPlan.project_workspace_id == project_id,
            )
        )
        benefits_version = (
            self.db.scalar(
                select(StrategicBenefitsPlanVersion).where(
                    StrategicBenefitsPlanVersion.tenant_id == self.tenant_id,
                    StrategicBenefitsPlanVersion.id == benefits_plan.current_version_id,
                    StrategicBenefitsPlanVersion.benefits_plan_id == benefits_plan.id,
                )
            )
            if benefits_plan and benefits_plan.current_version_id
            else None
        )
        if benefits_plan and benefits_version:
            readiness = benefits_version.readiness_status
            refs["benefits"] = {
                "id": benefits_plan.id,
                "number": benefits_plan.plan_number,
                "version_id": benefits_version.id,
                "version": benefits_version.version_number,
                "status": benefits_version.status,
                "readiness": readiness,
                "source_current": bool(benefits_version.source_current),
                "as_of_date": (benefits_version.completed_at or benefits_version.updated_at).isoformat(),
                "warnings": list(benefits_version.readiness_warnings_json or []),
                "blockers": list(benefits_version.readiness_blockers_json or []),
            }
            hashes["benefits"] = benefits_version.benefits_plan_hash

        commercial_strategy = self.db.scalar(
            select(CommercialContractingStrategy).where(
                CommercialContractingStrategy.tenant_id == self.tenant_id,
                CommercialContractingStrategy.project_workspace_id == project_id,
            )
        )
        commercial_version = (
            self.db.scalar(
                select(CommercialStrategyVersion).where(
                    CommercialStrategyVersion.tenant_id == self.tenant_id,
                    CommercialStrategyVersion.id == commercial_strategy.current_version_id,
                    CommercialStrategyVersion.commercial_strategy_id == commercial_strategy.id,
                )
            )
            if commercial_strategy and commercial_strategy.current_version_id
            else None
        )
        if commercial_strategy and commercial_version:
            commercial_content = dict(commercial_version.content_json or {})
            refs["commercial_strategy"] = {
                "id": commercial_strategy.id,
                "number": commercial_strategy.strategy_number,
                "version_id": commercial_version.id,
                "version": commercial_version.version_number,
                "status": commercial_version.status,
                "readiness": commercial_version.readiness_status,
                "source_current": bool(commercial_version.source_current),
                "as_of_date": (commercial_version.completed_at or commercial_version.updated_at).isoformat(),
                "procurement_approach": commercial_content.get("procurement_approach"),
                "contracting_model": commercial_content.get("contracting_model"),
                "warnings": list(commercial_version.readiness_warnings_json or []),
                "blockers": list(commercial_version.readiness_blockers_json or []),
            }
            hashes["commercial_strategy"] = commercial_version.commercial_strategy_hash
        fel = self.db.scalar(
            select(ProjectFELStatus).where(
                ProjectFELStatus.tenant_id == self.tenant_id,
                ProjectFELStatus.project_workspace_id == project_id,
            )
        )
        if fel:
            refs["fel"] = {
                "id": fel.id,
                "stage": fel.current_stage_code,
                "status": fel.status,
                "readiness": fel.readiness_status,
                "source_current": fel.readiness_status != "STALE",
                "as_of_date": fel.updated_at.isoformat(),
            }
            hashes["fel"] = fel.definition_source_hash
        budget_row = self.db.scalar(
            select(PortfolioBudgetScenarioProject)
            .join(PortfolioBudgetScenario, PortfolioBudgetScenario.id == PortfolioBudgetScenarioProject.scenario_id)
            .where(
                PortfolioBudgetScenarioProject.tenant_id == self.tenant_id,
                PortfolioBudgetScenarioProject.project_workspace_id == project_id,
                PortfolioBudgetScenario.status == "FROZEN",
            )
            .order_by(PortfolioBudgetScenario.frozen_at.desc())
        )
        if budget_row:
            refs["budget"] = {
                "id": budget_row.id,
                "scenario_id": budget_row.scenario_id,
                "selection_state": budget_row.selection_state,
                "capex": str(budget_row.capex_amount) if budget_row.capex_amount is not None else None,
                "currency": budget_row.currency,
                "status": "FROZEN",
                "readiness": "READY",
                "source_current": True,
            }
            hashes["budget"] = budget_row.row_hash
        resource_row = self.db.scalar(
            select(PortfolioResourceScenarioProject)
            .join(
                PortfolioResourceScenario, PortfolioResourceScenario.id == PortfolioResourceScenarioProject.scenario_id
            )
            .where(
                PortfolioResourceScenarioProject.tenant_id == self.tenant_id,
                PortfolioResourceScenarioProject.project_workspace_id == project_id,
                PortfolioResourceScenario.status == "FROZEN",
            )
            .order_by(PortfolioResourceScenario.frozen_at.desc())
        )
        if resource_row:
            refs["resource"] = {
                "id": resource_row.id,
                "scenario_id": resource_row.scenario_id,
                "selection_state": resource_row.selection_state,
                "status": "FROZEN",
                "readiness": "READY",
                "source_current": True,
            }
            hashes["resource"] = resource_row.row_hash
        funding = self.db.scalar(
            select(FundingReadinessSnapshot)
            .where(
                FundingReadinessSnapshot.tenant_id == self.tenant_id,
                FundingReadinessSnapshot.project_workspace_id == project_id,
            )
            .order_by(FundingReadinessSnapshot.generated_at.desc())
        )
        if funding:
            refs["funding"] = {
                "id": funding.id,
                "status": funding.status,
                "readiness": funding.status,
                "source_current": funding.source_current,
                "as_of_date": funding.generated_at.isoformat(),
            }
            hashes["funding"] = funding.funding_readiness_hash
        # Gate 07M-FIN is an optional governed successor source. Historical
        # completed Business Case revisions stay immutable; only a new DRAFT
        # revision resolves the latest completed/current model evidence.
        from app.modules.economic_financial_model.models import (
            EconomicFinancialModel,
            EconomicFinancialModelVersion,
        )

        financial_model = self.db.scalar(
            select(EconomicFinancialModel).where(
                EconomicFinancialModel.tenant_id == self.tenant_id,
                EconomicFinancialModel.project_workspace_id == project_id,
            )
        )
        if financial_model:
            financial_version = self.db.scalar(
                select(EconomicFinancialModelVersion)
                .where(
                    EconomicFinancialModelVersion.tenant_id == self.tenant_id,
                    EconomicFinancialModelVersion.model_id == financial_model.id,
                    EconomicFinancialModelVersion.status == "COMPLETED",
                    EconomicFinancialModelVersion.overall_readiness == "READY",
                    EconomicFinancialModelVersion.source_current.is_(True),
                )
                .order_by(EconomicFinancialModelVersion.version_number.desc())
            )
            if financial_version:
                refs["economic_financial_model"] = {
                    "id": financial_model.id,
                    "version_id": financial_version.id,
                    "version": financial_version.version_number,
                    "readiness": financial_version.overall_readiness,
                    "status": financial_version.status,
                    "financial_model_status": "AVAILABLE",
                    "as_of_date": financial_version.as_of_date.isoformat(),
                    "source_current": bool(financial_version.source_current),
                    "model_type": financial_version.model_type,
                    "base_currency": financial_version.base_currency,
                    "project_financial_npv": (
                        str(financial_version.project_financial_npv)
                        if financial_version.project_financial_npv is not None
                        else None
                    ),
                    "project_irr": (
                        str(financial_version.project_irr) if financial_version.project_irr is not None else None
                    ),
                    "economic_npv": (
                        str(financial_version.economic_npv) if financial_version.economic_npv is not None else None
                    ),
                    "economic_irr": (
                        str(financial_version.economic_irr) if financial_version.economic_irr is not None else None
                    ),
                    "benefit_cost_ratio": (
                        str(financial_version.benefit_cost_ratio)
                        if financial_version.benefit_cost_ratio is not None
                        else None
                    ),
                    "funding_reconciliation_status": financial_version.funding_reconciliation_status,
                }
                hashes["economic_financial_model"] = financial_version.model_hash
        risk = self.db.scalar(
            select(RiskReadinessAssessment)
            .where(
                RiskReadinessAssessment.tenant_id == self.tenant_id,
                RiskReadinessAssessment.project_workspace_id == project_id,
                RiskReadinessAssessment.status == "COMPLETED",
            )
            .order_by(RiskReadinessAssessment.completed_at.desc())
        )
        if risk:
            refs["risk"] = {
                "id": risk.id,
                "status": risk.readiness_status,
                "readiness": risk.readiness_status,
                "valid_until": risk.valid_until.isoformat() if risk.valid_until else None,
                "source_current": risk.readiness_status not in {"STALE", "EXPIRED"},
                "as_of_date": risk.completed_at.isoformat() if risk.completed_at else None,
                "blockers": list(risk.blockers_json or []),
            }
            hashes["risk"] = risk.risk_readiness_hash or risk.risk_register_hash
        permit = self.db.scalar(
            select(PermitReadinessAssessment)
            .where(
                PermitReadinessAssessment.tenant_id == self.tenant_id,
                PermitReadinessAssessment.project_workspace_id == project_id,
                PermitReadinessAssessment.status == "COMPLETED",
            )
            .order_by(PermitReadinessAssessment.completed_at.desc())
        )
        if permit:
            refs["permit"] = {
                "id": permit.id,
                "status": permit.readiness_status,
                "readiness": permit.readiness_status,
                "valid_until": permit.valid_until.isoformat() if permit.valid_until else None,
                "source_current": permit.readiness_status not in {"STALE", "EXPIRED"},
                "as_of_date": permit.completed_at.isoformat() if permit.completed_at else None,
                "blockers": list(permit.blockers_json or []),
            }
            hashes["permit"] = permit.permit_readiness_hash or permit.permit_source_hash
        qra_refs, qra_hashes = self._qra_source_bundle(project_id, portfolio_id=proposal.target_portfolio_workspace_id)
        refs.update(qra_refs)
        hashes.update(qra_hashes)
        return refs, hashes

    def _qra_source_bundle(self, project_id: int, *, portfolio_id: int | None = None) -> tuple[dict, dict]:
        """Consume the same qualified provider and applicability as Gate07J.

        No BC/Gate refresh performs a calculation. A published context must opt
        in; absent/nonapplicable policy leaves legacy source bundles unchanged.
        """
        from app.modules.investment_evidence_policy.service import InvestmentEvidencePolicyService

        resolver = InvestmentEvidencePolicyService(self.db, self.tenant_id, self.actor_id, self.context)
        # Portfolio is an N:M analytical membership, not necessarily a parent
        # workspace. The captured Proposal supplies the explicit decision
        # context; the policy resolver verifies that membership, never picks a
        # different portfolio merely because it has a newer policy.
        contract = (
            resolver.qra_requirements_for_project(project_id, portfolio_id=portfolio_id)
            if portfolio_id is not None
            else resolver.qra_requirements_for_project(project_id)
        )
        requirements = [r for r in contract["requirements"] if r.get("classification") != "C"]
        if not requirements:
            return {}, {}
        refs, hashes = {}, {}
        marker = {"schema_version": "1.0", "policy_ref": contract["policy_ref"], "requirements": []}
        for requirement in requirements:
            source = "cost_qra_result" if requirement["evidence_type"] == "COST_QRA_RESULT" else "schedule_qra_result"
            payload, error = resolver.resolve_governed_payload(requirement, {}, project_id)
            summary = deepcopy((payload or {}).get("qra_summary") or {})
            mandatory = requirement.get("classification") == "A" or bool(requirement.get("blocking"))
            marker["requirements"].append(
                {
                    "source": source,
                    "classification": requirement["classification"],
                    "blocking": mandatory,
                    "applicability": deepcopy(requirement.get("qra_applicability", {})),
                    "policy": deepcopy(requirement.get("qra_policy", {})),
                    "resolution_error": error,
                }
            )
            # Optional unavailable evidence is disclosed in the policy marker,
            # not fabricated as a current source nor made universally blocking.
            if (not summary or error) and not mandatory:
                continue
            current = bool(payload and payload.get("source_current") and not error)
            refs[source] = {
                **summary,
                "id": summary.get("run_id"),
                "version": summary.get("model_version"),
                "status": "AVAILABLE" if current else "BLOCKED",
                "readiness": summary.get("analytical_readiness") or summary.get("readiness") or "NOT_AVAILABLE",
                "source_current": current,
                "as_of_date": summary.get("as_of"),
                "warnings": sorted(set((payload or {}).get("warnings", []))),
                "blockers": sorted(set((payload or {}).get("blockers", []) + ([error] if error else []))),
                "policy_ref": deepcopy(contract["policy_ref"]),
                "classification": requirement["classification"],
                "qra_applicability": deepcopy(
                    (payload or {}).get("qra_applicability") or requirement.get("qra_applicability", {})
                ),
                "not_probabilistic_fin": True,
                "not_investment_approval": True,
            }
            hashes[source] = str((payload or {}).get("evidence_hash") or _hash(refs[source]))
        refs["_qra_evidence"] = marker
        # The marker is frozen policy provenance in the existing JSON bundle;
        # changing applicability requires a successor, never editing completion.
        hashes["_qra_evidence"] = _hash(marker)
        return refs, hashes

    def _five_case_marker(
        self,
        case: BusinessCase,
        *,
        purpose: str,
        as_of_date: datetime,
        references: dict[str, Any],
    ) -> dict[str, Any]:
        """Freeze the additive policy/context in an existing JSON column."""

        project = self._project(case.project_workspace_id)
        metadata = dict((project.defaults_json or {}).get("_project", {}))
        config = self._configuration(case.configuration_id)
        fel_stage = (references.get("fel") or {}).get("stage") or metadata.get("fel_stage") or "FEL-1"
        policy_stage = self._five_case_stage(purpose, str(fel_stage))
        return {
            "schema_version": FIVE_CASE_SCHEMA_VERSION,
            "integration_layer": True,
            "source_authority_preserved": True,
            "configuration_id": case.configuration_id,
            "configuration_hash": case.configuration_hash,
            "policy": self._five_case_policy(config.content_json),
            "gate_context": {
                "project_workspace_id": project.id,
                "project_type": metadata.get("project_type"),
                "governance_model": metadata.get("governance_model"),
                "gate_profile": metadata.get("gate_profile"),
                "fel_stage": fel_stage,
                "policy_stage": policy_stage,
                "decision_gate": "INVESTMENT_SELECTION" if policy_stage == "INVESTMENT_SELECTION" else None,
                "revision_purpose": purpose,
                "as_of_date": as_of_date.isoformat(),
            },
        }

    def _five_case_contract(
        self,
        case: BusinessCase,
        revision: BusinessCaseRevision,
        *,
        references: dict[str, Any] | None = None,
        hashes: dict[str, str] | None = None,
        compare_current: bool = False,
        force_five_case: bool = False,
    ) -> dict[str, Any]:
        """Build the additive Five Case synthesis without owning source data.

        The marker is persisted inside the pre-existing structured reference
        payload.  This lets historical revisions remain honest: an old row is
        readable as legacy rather than receiving a fabricated Five Case view.
        """

        # ``compare_current`` is retained as a call-compatible argument only.
        # A read contract is exclusively a projection of the frozen revision;
        # live-source comparison belongs to readiness/refresh operations.
        _ = compare_current
        custom_bundle = references is not None or hashes is not None
        stored_refs = deepcopy(references if references is not None else (revision.source_references_json or {}))
        stored_hashes = deepcopy(hashes if hashes is not None else (revision.source_hashes_json or {}))
        marker = dict(stored_refs.get("_five_case") or {})
        enhanced = force_five_case or marker.get("schema_version") == FIVE_CASE_SCHEMA_VERSION
        calculated_source_bundle_hash = _hash({"references": stored_refs, "hashes": stored_hashes})
        source_bundle_hash = (
            calculated_source_bundle_hash
            if custom_bundle
            else (revision.source_snapshot_hash or calculated_source_bundle_hash)
        )
        if not enhanced:
            return {
                "five_case_json": {},
                "five_case_readiness_json": {},
                "source_evidence_matrix_json": [],
                "gate_context_json": self._gate_context(case, revision, stored_refs),
                "source_current": True,
                "five_case_hash": None,
                "source_bundle_hash": source_bundle_hash,
                "business_case_hash": revision.content_hash,
                "legacy_layout": True,
                "warnings": [],
                "blockers": [],
            }

        gate_context = self._gate_context(case, revision, stored_refs)
        frozen_policy = marker.get("policy")
        policy = (
            deepcopy(frozen_policy) if isinstance(frozen_policy, dict) else deepcopy(DEFAULT_CONFIGURATION["five_case"])
        )
        governance_model = str(gate_context.get("governance_model") or "")
        enabled_models = {str(value).upper() for value in policy.get("enabled_governance_models", ["CAPITAL_OWNER"])}
        enabled = "*" in enabled_models or governance_model.upper() in enabled_models
        stage = str(gate_context.get("policy_stage") or gate_context.get("fel_stage") or "FEL-1").upper()
        required_cases_by_stage = dict(policy.get("required_cases_by_stage") or {})
        required_cases = set(
            required_cases_by_stage.get(stage) or required_cases_by_stage.get("FEL-1") or ["strategic_case"]
        )
        source_rules_by_stage = dict(policy.get("source_requirements_by_stage") or {})
        source_rules = dict(
            source_rules_by_stage.get(stage) or source_rules_by_stage.get("FEL-1") or {"strategic_case": ["proposal"]}
        )
        matrix: list[dict[str, Any]] = []
        five_case: dict[str, Any] = {}
        readiness_map: dict[str, str] = {}
        aggregate_warnings: list[str] = []
        aggregate_blockers: list[str] = []

        for case_key in FIVE_CASE_KEYS:
            required_sources = set(source_rules.get(case_key, [])) if enabled and case_key in required_cases else set()
            rows: list[dict[str, Any]] = []
            blockers: list[str] = []
            warnings: list[str] = []
            stale = False
            relevant_sources = _case_sources(case_key, stored_refs)
            for rule in (stored_refs.get("_qra_evidence") or {}).get("requirements", []):
                if rule.get("blocking") and rule.get("source") in relevant_sources:
                    required_sources.add(rule["source"])
            for source_key in relevant_sources:
                ref = deepcopy(stored_refs.get(source_key) or {})
                stored_hash = stored_hashes.get(source_key)
                required = source_key in required_sources
                source_current = bool(stored_hash and ref and ref.get("source_current", True) is not False)
                readiness = str(ref.get("readiness") or ref.get("status") or "NOT_AVAILABLE").upper()
                row = {
                    "case": case_key,
                    "source_key": source_key,
                    "source_module": self._source_module(source_key),
                    "source_id": ref.get("id"),
                    "version": ref.get("version") or ref.get("version_id"),
                    "hash": stored_hash,
                    "readiness": readiness,
                    "source_current": source_current,
                    "as_of_date": ref.get("as_of_date"),
                    "blocking": required,
                    "available": bool(ref and stored_hash),
                    "view_source": {
                        "module": self._source_module(source_key),
                        "source_id": ref.get("id"),
                    },
                }
                if source_key in {"cost_qra_result", "schedule_qra_result"}:
                    row["qra_summary"] = deepcopy(ref)
                rows.append(row)
                matrix.append(deepcopy(row))
                if not required:
                    continue
                if not ref or not stored_hash:
                    blockers.append(f"{case_key.upper()}:REQUIRED_SOURCE_MISSING:{source_key}")
                    continue
                if not source_current:
                    stale = True
                    blockers.append(f"{case_key.upper()}:SOURCE_STALE:{source_key}")
                if readiness in {"BLOCKED", "STALE", "EXPIRED", "NOT_STARTED", "IN_PROGRESS", "DRAFT", "VOIDED"}:
                    blockers.append(f"{case_key.upper()}:SOURCE_NOT_READY:{source_key}:{readiness}")
                warnings.extend(str(value) for value in list(ref.get("warnings") or []))
                blockers.extend(str(value) for value in list(ref.get("blockers") or []))

            if (
                enabled
                and case_key in required_cases
                and case_key == "economic_case"
                and not (stored_refs.get("cost_qra_result") or {}).get("source_current")
            ):
                warnings.append("QRA_CONFIDENCE_NOT_AVAILABLE")
            if enabled and case_key in required_cases and case_key == "management_case":
                warnings.extend(["OWNER_CAPABILITY_READINESS_NOT_AVAILABLE", "BASIC_DATA_READINESS_NOT_AVAILABLE"])
            if not enabled:
                status = "NOT_APPLICABLE"
            elif case_key not in required_cases:
                status = "IN_PROGRESS" if any(row["available"] for row in rows) else "NOT_STARTED"
            elif stale:
                status = "STALE"
            elif blockers:
                status = "BLOCKED"
            else:
                status = "READY"
            readiness_map[case_key] = status
            conclusion = {
                "READY": "CASE_READY_FOR_GOVERNED_DECISION_EVIDENCE",
                "STALE": "CASE_REVALIDATION_REQUIRED",
                "BLOCKED": "CASE_BLOCKED_BY_REQUIRED_EVIDENCE",
                "IN_PROGRESS": "CASE_MATURITY_IN_PROGRESS",
                "NOT_STARTED": "CASE_NOT_STARTED",
                "NOT_APPLICABLE": "CASE_NOT_APPLICABLE_BY_POLICY",
            }[status]
            case_payload = {
                "question": CASE_QUESTIONS[case_key],
                "summary": self._case_summary(case_key, revision, stored_refs),
                "source_references": {
                    key: deepcopy(stored_refs[key]) for key in relevant_sources if key in stored_refs
                },
                "source_hashes": {key: stored_hashes[key] for key in relevant_sources if key in stored_hashes},
                "source_readiness": {row["source_key"]: row["readiness"] for row in rows},
                "findings": self._case_findings(case_key, revision, stored_refs),
                "assumptions": deepcopy(revision.assumptions_json or []),
                "warnings": sorted(set(warnings)),
                "blockers": sorted(set(blockers)),
                "conclusion": conclusion,
                "readiness": status,
                "required_by_policy": enabled and case_key in required_cases,
            }
            five_case[case_key] = case_payload
            aggregate_warnings.extend(f"{case_key}:{value}" for value in case_payload["warnings"])
            aggregate_blockers.extend(case_payload["blockers"])

        required_statuses = [readiness_map[key] for key in required_cases if key in readiness_map]
        if not enabled:
            overall = "NOT_APPLICABLE"
        elif any(value == "STALE" for value in required_statuses):
            overall = "STALE"
        elif any(value == "BLOCKED" for value in required_statuses):
            overall = "BLOCKED"
        elif required_statuses and all(value == "READY" for value in required_statuses):
            overall = "READY"
        elif any(value == "IN_PROGRESS" for value in required_statuses):
            overall = "IN_PROGRESS"
        else:
            overall = "NOT_STARTED"
        readiness_map["overall_business_case_readiness"] = overall
        effective_required_cases = sorted(required_cases) if enabled else []
        frozen_payload = {
            "schema_version": FIVE_CASE_SCHEMA_VERSION,
            "gate_context": gate_context,
            "cases": five_case,
            "required_cases": effective_required_cases,
        }
        five_case_hash = _hash(frozen_payload)
        business_case_hash = _hash(
            {
                "content_hash": revision.content_hash,
                "five_case_hash": five_case_hash,
                "source_bundle_hash": source_bundle_hash,
                "configuration_hash": case.configuration_hash,
            }
        )
        return {
            "five_case_json": {
                "schema_version": FIVE_CASE_SCHEMA_VERSION,
                "integration_layer": True,
                "required_cases": effective_required_cases,
                **five_case,
            },
            "five_case_readiness_json": readiness_map,
            "source_evidence_matrix_json": matrix,
            "gate_context_json": gate_context,
            "source_current": all(
                bool(stored_refs.get(key)) and dict(stored_refs.get(key) or {}).get("source_current", True) is not False
                for key in stored_hashes
            ),
            "five_case_hash": five_case_hash,
            "source_bundle_hash": source_bundle_hash,
            "business_case_hash": business_case_hash,
            "legacy_layout": False,
            "warnings": sorted(set(aggregate_warnings)),
            "blockers": sorted(set(aggregate_blockers)),
        }

    def _revision_out(self, revision: BusinessCaseRevision) -> BusinessCaseRevisionOut:
        base = BusinessCaseRevisionOut.model_validate(revision)
        case = self._case(revision.business_case_id)
        contract = self._five_case_contract(case, revision)
        return base.model_copy(
            update={
                key: contract[key]
                for key in (
                    "five_case_json",
                    "five_case_readiness_json",
                    "source_evidence_matrix_json",
                    "gate_context_json",
                    "source_current",
                    "five_case_hash",
                    "source_bundle_hash",
                    "business_case_hash",
                    "legacy_layout",
                )
            }
        )

    def revision_out(self, revision_id: int) -> BusinessCaseRevisionOut:
        return self._revision_out(self._revision(revision_id))

    def _gate_context(
        self, case: BusinessCase, revision: BusinessCaseRevision, references: dict[str, Any]
    ) -> dict[str, Any]:
        marker = dict(references.get("_five_case") or {})
        frozen = marker.get("gate_context")
        if isinstance(frozen, dict) and frozen:
            return deepcopy(frozen)
        # Rows predating BC-5C intentionally remain legacy-compatible.  Do not
        # reinterpret their historical context from mutable Project metadata.
        return {
            "project_workspace_id": case.project_workspace_id,
            "project_type": None,
            "governance_model": None,
            "gate_profile": None,
            "fel_stage": (references.get("fel") or {}).get("stage") or revision.fel_stage_code or "FEL-1",
            "revision_purpose": revision.purpose,
            "as_of_date": revision.as_of_date.isoformat(),
        }

    @staticmethod
    def _five_case_policy(content: dict[str, Any]) -> dict[str, Any]:
        policy = deepcopy(DEFAULT_CONFIGURATION["five_case"])
        supplied = dict(content.get("five_case") or {})
        for key, value in supplied.items():
            if isinstance(value, dict) and isinstance(policy.get(key), dict):
                policy[key].update(deepcopy(value))
            else:
                policy[key] = deepcopy(value)
        return policy

    @staticmethod
    def _five_case_stage(purpose: str, fel_stage: str) -> str:
        return {
            "FEL_1_UPDATE": "FEL-1",
            "FEL_2_UPDATE": "FEL-2",
            "INVESTMENT_SELECTION_UPDATE": "INVESTMENT_SELECTION",
            "FEL_3_UPDATE": "FEL-3",
            "FFA_UPDATE": "FFA",
        }.get(purpose, fel_stage.upper())

    @staticmethod
    def _source_module(source_key: str) -> str:
        return {
            "idea": "IDEA_DEMAND_MANAGER",
            "business_analysis": "BUSINESS_ANALYSIS",
            "proposal": "PROJECT_PROPOSAL",
            "benefits": "STRATEGIC_BENEFITS_PLAN",
            "commercial_strategy": "COMMERCIAL_CONTRACTING_STRATEGY",
            "fel": "PROJECT_DEFINITION_FEL",
            "budget": "PORTFOLIO_BUDGET_SCENARIO",
            "resource": "PORTFOLIO_RESOURCE_SCENARIO",
            "funding": "FUNDING_READINESS",
            "economic_financial_model": "ECONOMIC_FINANCIAL_MODEL",
            "risk": "RISK_READINESS",
            "permit": "PERMIT_READINESS",
            "cost_qra_result": "QRA_CALCULATION_ENGINE",
            "schedule_qra_result": "QRA_CALCULATION_ENGINE",
        }.get(source_key, source_key.upper())

    @staticmethod
    def _case_summary(case_key: str, revision: BusinessCaseRevision, references: dict[str, Any]) -> str:
        if case_key == "strategic_case":
            return revision.executive_summary or revision.business_need
        if case_key == "economic_case":
            recommendation = dict(revision.recommendation_json or {})
            selected = recommendation.get("selected_alternative") or (references.get("business_analysis") or {}).get(
                "recommended_option_id"
            )
            return f"Preferred option: {selected}." if selected else "Preferred option remains to be governed."
        if case_key == "commercial_case":
            commercial = dict(references.get("commercial_strategy") or {})
            return (
                f"Procurement approach {commercial.get('procurement_approach') or 'not available'}; "
                f"contracting model {commercial.get('contracting_model') or 'not available'}."
            )
        if case_key == "financial_case":
            financial = dict(references.get("economic_financial_model") or {})
            return (
                f"Governed financial model {financial.get('model_type') or 'not available'}; "
                f"funding reconciliation {financial.get('funding_reconciliation_status') or 'not available'}."
            )
        fel = dict(references.get("fel") or {})
        return f"Delivery context at {fel.get('stage') or revision.fel_stage_code or 'FEL-1'}."

    @staticmethod
    def _case_findings(
        case_key: str, revision: BusinessCaseRevision, references: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if case_key == "strategic_case":
            return [
                {"finding": "strategic_alignment_items", "value": len(revision.strategic_alignment_json or [])},
                {"finding": "objectives", "value": len(revision.objectives_json or [])},
                {"finding": "benefit_items", "value": len(revision.benefits_json or [])},
            ]
        if case_key == "economic_case":
            financial = dict(references.get("economic_financial_model") or {})
            return [
                {"finding": "alternatives_considered", "value": len(revision.alternatives_json or [])},
                {"finding": "preferred_option", "value": dict(revision.recommendation_json or {})},
                {
                    "finding": "governed_financial_metrics",
                    "value": {
                        key: financial.get(key) for key in ("economic_npv", "economic_irr", "benefit_cost_ratio")
                    },
                },
            ]
        if case_key == "commercial_case":
            commercial = dict(references.get("commercial_strategy") or {})
            return [{"finding": "commercial_source_summary", "value": commercial}]
        if case_key == "financial_case":
            return [
                {"finding": "budget", "value": deepcopy(references.get("budget") or {})},
                {"finding": "funding", "value": deepcopy(references.get("funding") or {})},
                {
                    "finding": "financial_metrics",
                    "value": deepcopy(references.get("economic_financial_model") or {}),
                },
            ]
        return [
            {"finding": "delivery", "value": deepcopy(revision.delivery_json or {})},
            {"finding": "fel", "value": deepcopy(references.get("fel") or {})},
            {"finding": "resource", "value": deepcopy(references.get("resource") or {})},
            {"finding": "risk", "value": deepcopy(references.get("risk") or {})},
            {"finding": "permit", "value": deepcopy(references.get("permit") or {})},
        ]

    def _evaluate_readiness(
        self, case: BusinessCase, revision: BusinessCaseRevision, config: AdminConfiguration
    ) -> ReadinessOut:
        blockers: list[str] = []
        warnings: list[str] = []
        for section in config.content_json.get("required_sections", []):
            value = {
                "title": revision.title,
                "business_need": revision.business_need,
                "objectives": revision.objectives_json,
                "scope": revision.scope_json,
            }.get(section)
            if not value:
                blockers.append(f"REQUIRED_SECTION_MISSING:{section}")
        fel_ref = dict(revision.source_references_json or {}).get("fel", {})
        stage = str(fel_ref.get("stage") or "FEL-1")
        required_sources = config.content_json.get("required_sources_by_stage", {}).get(stage, ["proposal"])
        for source in required_sources:
            if source not in revision.source_hashes_json:
                blockers.append(f"REQUIRED_SOURCE_MISSING:{source}")
        current_refs, current_hashes = self._source_bundle(case.project_workspace_id, case.source_project_proposal_id)
        stale = current_hashes != revision.source_hashes_json
        if stale:
            blockers.append("BUSINESS_CASE_SOURCE_STALE")
        expired_sources: list[str] = []
        now_iso = utc_now().isoformat()
        for key, ref in current_refs.items():
            if ref.get("source_current") is False:
                blockers.append(f"SOURCE_NOT_CURRENT:{key}")
            if ref.get("status") in {"BLOCKED", "STALE", "EXPIRED"}:
                blockers.append(f"SOURCE_NOT_READY:{key}")
            if ref.get("valid_until") and str(ref["valid_until"]) < now_iso:
                expired_sources.append(key)
                blockers.append(f"SOURCE_EXPIRED:{key}")

        five_case = self._five_case_contract(case, revision)
        five_case_status = five_case["five_case_readiness_json"].get("overall_business_case_readiness")
        marker = dict((revision.source_references_json or {}).get("_five_case") or {})
        frozen_policy = marker.get("policy")
        policy = frozen_policy if isinstance(frozen_policy, dict) else DEFAULT_CONFIGURATION["five_case"]
        strict_five_case = bool(
            not five_case["legacy_layout"]
            and five_case_status != "NOT_APPLICABLE"
            and policy.get("enforce_readiness", True)
        )
        if strict_five_case:
            warnings.extend(five_case["warnings"])
            blockers.extend(five_case["blockers"])
            if five_case_status != "READY":
                blockers.append(f"FIVE_CASE_NOT_READY:{five_case_status or 'NOT_STARTED'}")
            if not five_case["source_current"]:
                stale = True

        status = "EXPIRED" if expired_sources else ("STALE" if stale else ("BLOCKED" if blockers else "READY"))
        readiness_hash = _hash(
            {
                "revision": revision.content_hash,
                "sources": current_hashes,
                "five_case_hash": five_case["five_case_hash"],
                "blockers": sorted(set(blockers)),
            }
        )
        if status == "READY" and revision.status in {"IN_REVIEW", "COMPLETED"}:
            output = FIVE_CASE_READY_OUTPUT if strict_five_case else READY_OUTPUT
        else:
            output = status
        return ReadinessOut(
            business_case_id=case.id,
            revision_id=revision.id,
            status=status,
            warnings=sorted(set(warnings)),
            blockers=sorted(set(blockers)),
            source_current=not stale,
            readiness_hash=readiness_hash,
            final_output=output,
            persisted=revision.status == "COMPLETED",
        )

    def _case_out(self, record: BusinessCase) -> BusinessCaseOut:
        revision = self._current_revision(record, required=False)
        ready = bool(revision and revision.status == "COMPLETED" and revision.readiness_status == "READY")
        revision_out = self._revision_out(revision) if revision else None
        five_case_ready = bool(
            revision_out and revision_out.five_case_readiness_json.get("overall_business_case_readiness") == "READY"
        )
        return BusinessCaseOut(
            **{key: getattr(record, key) for key in BusinessCaseOut.model_fields if hasattr(record, key)},
            current_revision=revision_out,
            final_output=(FIVE_CASE_READY_OUTPUT if ready and five_case_ready else READY_OUTPUT)
            if ready
            else "BUSINESS_CASE_IN_PROGRESS",
            next_process=NEXT_PROCESS if ready else "COMPLETE_GOVERNED_BUSINESS_CASE",
        )

    def _content_hash(self, revision: BusinessCaseRevision) -> str:
        return _hash(
            {
                "title": revision.title,
                "executive_summary": revision.executive_summary,
                "business_need": revision.business_need,
                "strategic_alignment": revision.strategic_alignment_json,
                "objectives": revision.objectives_json,
                "scope": revision.scope_json,
                "alternatives": revision.alternatives_json,
                "benefits": revision.benefits_json,
                "assumptions": revision.assumptions_json,
                "constraints": revision.constraints_json,
                "delivery": revision.delivery_json,
                "unresolved_concerns": revision.unresolved_concerns_json,
                "recommendation": revision.recommendation_json,
                "source_snapshot_hash": revision.source_snapshot_hash,
                "economic_financial_model_id": revision.economic_financial_model_id,
                "economic_financial_model_version": revision.economic_financial_model_version,
                "economic_financial_model_hash": revision.economic_financial_model_hash,
                "financial_model_status": revision.financial_model_status,
                "economic_financial_readiness": revision.economic_financial_readiness,
                "economic_financial_as_of_date": revision.economic_financial_as_of_date,
            }
        )

    def _next_number(self) -> str:
        sequence = self.db.scalar(
            select(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == "BUSINESS_CASE",
                AdminNumberSequence.scope_key == "tenant",
            )
            .with_for_update()
        )
        if sequence is None:
            sequence = AdminNumberSequence(
                tenant_id=self.tenant_id,
                rule_code="BUSINESS_CASE",
                scope_key="tenant",
                next_value=2,
                version=1,
            )
            self.db.add(sequence)
            return "BC-00001"
        value = sequence.next_value
        sequence.next_value += 1
        sequence.version += 1
        sequence.updated_at = utc_now()
        return f"BC-{value:05d}"

    def _resolve_configuration(
        self, project: EnterpriseWorkspace, override: AdminConfiguration | None = None
    ) -> tuple[AdminConfiguration, list[dict]]:
        candidates = (
            [override]
            if override
            else list(
                self.db.scalars(
                    select(AdminConfiguration)
                    .where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                        AdminConfiguration.status == "published",
                    )
                    .order_by(AdminConfiguration.revision.desc())
                ).all()
            )
        )
        metadata = dict((project.defaults_json or {}).get("_project", {}))
        ancestors: list[int] = []
        cursor: EnterpriseWorkspace | None = project
        while cursor is not None:
            ancestors.append(cursor.id)
            cursor = self.db.get(EnterpriseWorkspace, cursor.parent_id) if cursor.parent_id else None
        chain: list[dict] = []
        ranked: list[tuple[int, AdminConfiguration]] = []
        for item in candidates:
            scope = dict(item.content_json.get("scope", {}))
            workspace_id = scope.get("workspace_id")
            applicable = workspace_id is None or workspace_id in ancestors
            if not applicable:
                continue
            filters = {
                "project_type": item.content_json.get("applicable_project_types", ["*"]),
                "governance_model": item.content_json.get("applicable_governance_models", ["*"]),
                "gate_profile": item.content_json.get("applicable_gate_profiles", ["*"]),
                "fel_stage": item.content_json.get("applicable_fel_stages", ["*"]),
            }
            actual = {
                "project_type": metadata.get("project_type", ""),
                "governance_model": metadata.get("governance_model", ""),
                "gate_profile": metadata.get("gate_profile", ""),
                "fel_stage": metadata.get("fel_stage", ""),
            }
            if any("*" not in filters[key] and actual[key] not in filters[key] for key in filters):
                continue
            distance = ancestors.index(workspace_id) if workspace_id in ancestors else len(ancestors) + 1
            ranked.append((distance, item))
            chain.append({"configuration_id": item.id, "workspace_id": workspace_id, "distance": distance})
        if not ranked:
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_BUSINESS_CASE_CONFIGURATION_REQUIRED"})
        ranked.sort(key=lambda value: (value[0], -value[1].revision))
        return ranked[0][1], sorted(chain, key=lambda item: item["distance"])

    def _case(self, business_case_id: int, *, lock: bool = False) -> BusinessCase:
        statement = select(BusinessCase).where(
            BusinessCase.id == business_case_id,
            BusinessCase.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "BUSINESS_CASE_NOT_FOUND"})
        return record

    def _revision(self, revision_id: int, *, lock: bool = False) -> BusinessCaseRevision:
        statement = select(BusinessCaseRevision).where(
            BusinessCaseRevision.id == revision_id,
            BusinessCaseRevision.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "BUSINESS_CASE_REVISION_NOT_FOUND"})
        return record

    def _current_revision(self, case: BusinessCase, *, required: bool = True) -> BusinessCaseRevision | None:
        record = self.db.scalar(
            select(BusinessCaseRevision).where(
                BusinessCaseRevision.id == case.current_revision_id,
                BusinessCaseRevision.tenant_id == self.tenant_id,
                BusinessCaseRevision.business_case_id == case.id,
            )
        )
        if record is None and required:
            raise HTTPException(status_code=409, detail={"code": "CURRENT_BUSINESS_CASE_REVISION_REQUIRED"})
        return record

    def _project(self, project_id: int) -> EnterpriseWorkspace:
        record = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == project_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.workspace_type_code == "project",
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "PROJECT_WORKSPACE_NOT_FOUND"})
        return record

    def _proposal_for_project(self, project_id: int, explicit_id: int | None) -> ProjectProposal:
        proposal_id = explicit_id
        if proposal_id is None:
            request = self.db.scalar(
                select(ProjectCreationRequest).where(
                    ProjectCreationRequest.tenant_id == self.tenant_id,
                    ProjectCreationRequest.materialized_workspace_id == project_id,
                )
            )
            proposal_id = request.source_project_proposal_id if request else None
        if proposal_id is None:
            raise HTTPException(status_code=409, detail={"code": "SOURCE_PROJECT_PROPOSAL_REQUIRED"})
        return self._proposal(proposal_id)

    def _proposal(self, proposal_id: int | None) -> ProjectProposal:
        record = self.db.scalar(
            select(ProjectProposal).where(
                ProjectProposal.id == proposal_id,
                ProjectProposal.tenant_id == self.tenant_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "PROJECT_PROPOSAL_NOT_FOUND"})
        return record

    def _configuration(self, configuration_id: int | None, *, lock: bool = False) -> AdminConfiguration:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.id == configuration_id,
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "BUSINESS_CASE_CONFIGURATION_NOT_FOUND"})
        return record

    def _published_configuration(self) -> AdminConfiguration:
        record = self.db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
        )
        if record is None:
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_BUSINESS_CASE_CONFIGURATION_REQUIRED"})
        return record

    def _snapshots(self, business_case_id: int) -> list[BusinessCaseDecisionSnapshot]:
        return list(
            self.db.scalars(
                select(BusinessCaseDecisionSnapshot)
                .where(
                    BusinessCaseDecisionSnapshot.tenant_id == self.tenant_id,
                    BusinessCaseDecisionSnapshot.business_case_id == business_case_id,
                )
                .order_by(BusinessCaseDecisionSnapshot.created_at.desc())
            ).all()
        )

    @staticmethod
    def _chain_source_id(chain: list[dict]) -> int | None:
        return chain[0].get("workspace_id") if chain else None

    @staticmethod
    def _configuration_issues(content: dict) -> list[str]:
        issues: list[str] = []
        required = set(content.get("required_sections", []))
        if not {"title", "business_need", "objectives", "scope"}.issubset(required):
            issues.append("CORE_BUSINESS_CASE_SECTIONS_REQUIRED")
        sod = dict(content.get("separation_of_duties", {}))
        if not sod.get("reviewer_must_differ_from_preparer", False):
            issues.append("PREPARER_REVIEWER_SOD_REQUIRED")
        if "mapping" not in content:
            issues.append("PROJECT_PROPOSAL_MAPPING_REQUIRED")
        return issues

    @staticmethod
    def _check_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise HTTPException(
                status_code=412,
                detail={"code": "ETAG_MISMATCH", "expected": expected, "actual": actual},
            )

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
