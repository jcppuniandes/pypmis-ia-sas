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
NEXT_PROCESS = "BUILD_GATE07M_FIN"
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
        "tracked_sources": ["proposal", "fel", "budget", "resource", "funding", "risk", "permit"],
        "recommendation_only_after_selection_or_fid": True,
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
            BusinessCaseRevisionOut.model_validate(item)
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
            return BusinessCaseRevisionOut.model_validate(duplicate)
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
        return BusinessCaseRevisionOut.model_validate(revision)

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
        return BusinessCaseRevisionOut.model_validate(revision)

    def submit_review(self, revision_id: int, expected_version: int, idempotency_key: str) -> BusinessCaseRevisionOut:
        revision = self._revision(revision_id, lock=True)
        self._check_version(revision.revision_version, expected_version)
        if revision.status == "IN_REVIEW" and revision.create_idempotency_key == idempotency_key:
            return BusinessCaseRevisionOut.model_validate(revision)
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
        return BusinessCaseRevisionOut.model_validate(revision)

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
            return BusinessCaseRevisionOut.model_validate(duplicate)
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
        return BusinessCaseRevisionOut.model_validate(revision)

    def readiness(self, business_case_id: int) -> ReadinessOut:
        case = self._case(business_case_id)
        revision = self._current_revision(case)
        return self._evaluate_readiness(case, revision, self._configuration(case.configuration_id))

    def refresh_preview(self, business_case_id: int, *, audit: bool = True) -> RefreshPreviewOut:
        case = self._case(business_case_id)
        current = self._current_revision(case)
        refs, hashes = self._source_bundle(case.project_workspace_id, case.source_project_proposal_id)
        changes = [
            {"source": key, "from": current.source_hashes_json.get(key), "to": value}
            for key, value in hashes.items()
            if current.source_hashes_json.get(key) != value
        ]
        material = "MATERIAL_CHANGE_REVIEW_REQUIRED" if changes and self._snapshots(case.id) else "NO_MATERIAL_CHANGE"
        result = RefreshPreviewOut(
            business_case_id=case.id,
            current_revision_id=current.id,
            source_changes=changes,
            material_change_status=material,
            recommended_purpose="MATERIAL_CHANGE_UPDATE" if material != "NO_MATERIAL_CHANGE" else "REVALIDATION",
            persisted=False,
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
            return BusinessCaseRevisionOut.model_validate(duplicate)
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
        return BusinessCaseRevisionOut.model_validate(revision)

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
            as_of_date=utc_now(),
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
        refs["proposal"] = {"id": proposal.id, "number": proposal.proposal_number, "status": proposal.status}
        hashes["proposal"] = _hash(
            {
                "id": proposal.id,
                "version": proposal.revision_version,
                "mapping_hash": proposal.mapping_hash,
                "updated_at": proposal.updated_at,
            }
        )
        fel = self.db.scalar(
            select(ProjectFELStatus).where(
                ProjectFELStatus.tenant_id == self.tenant_id,
                ProjectFELStatus.project_workspace_id == project_id,
            )
        )
        if fel:
            refs["fel"] = {"id": fel.id, "stage": fel.current_stage_code, "readiness": fel.readiness_status}
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
            refs["funding"] = {"id": funding.id, "status": funding.status, "source_current": funding.source_current}
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
                    "financial_model_status": "AVAILABLE",
                    "as_of_date": financial_version.as_of_date.isoformat(),
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
                "valid_until": risk.valid_until.isoformat() if risk.valid_until else None,
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
                "valid_until": permit.valid_until.isoformat() if permit.valid_until else None,
            }
            hashes["permit"] = permit.permit_readiness_hash or permit.permit_source_hash
        return refs, hashes

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
        status = "EXPIRED" if expired_sources else ("STALE" if stale else ("BLOCKED" if blockers else "READY"))
        readiness_hash = _hash({"revision": revision.content_hash, "sources": current_hashes, "blockers": blockers})
        output = READY_OUTPUT if status == "READY" and revision.status in {"IN_REVIEW", "COMPLETED"} else status
        return ReadinessOut(
            business_case_id=case.id,
            revision_id=revision.id,
            status=status,
            warnings=warnings,
            blockers=sorted(set(blockers)),
            source_current=not stale,
            readiness_hash=readiness_hash,
            final_output=output,
            persisted=revision.status == "COMPLETED",
        )

    def _case_out(self, record: BusinessCase) -> BusinessCaseOut:
        revision = self._current_revision(record, required=False)
        ready = bool(revision and revision.status == "COMPLETED" and revision.readiness_status == "READY")
        return BusinessCaseOut(
            **{key: getattr(record, key) for key in BusinessCaseOut.model_fields if hasattr(record, key)},
            current_revision=BusinessCaseRevisionOut.model_validate(revision) if revision else None,
            final_output=READY_OUTPUT if ready else "BUSINESS_CASE_IN_PROGRESS",
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
