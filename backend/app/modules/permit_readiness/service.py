"""Gate 07J-PERMIT governed Permit Readiness services.

The module owns a small permit register, conditions and immutable readiness
snapshots. It deliberately excludes regulatory filing, legal interpretation,
environmental compliance workflow, Investment Decision and FID.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, AdminNumberSequence, EnterpriseWorkspace, SecurityEvent
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.permit_readiness.models import PermitCondition, PermitReadinessAssessment, ProjectPermit
from app.modules.permit_readiness.schemas import (
    AdminPreviewOut,
    InvestmentGatePermitEvidenceOut,
    PermitReadinessOverviewOut,
    ProjectPermitReadinessOut,
    ProjectSetPermitReadinessOut,
    RefreshPreviewOut,
)
from app.modules.portfolio_convergence.service import PortfolioConvergenceService

CONFIGURATION_KIND = "permit_readiness_configuration"
DEFAULT_CODE = "pyp-permit-readiness"
FINAL_OUTPUT = "READY_FOR_GOVERNED_PERMIT_EVIDENCE"
FINAL_RELEASE_STATUS = "GATE07J_PERMIT_RELEASE_VALIDATED"
PROVIDER_KEY = "PERMIT_READINESS_PROVIDER"
SOURCE_MODULE = "PERMIT_READINESS"
EVIDENCE_TYPE = "PERMIT_READINESS"

PERMIT_TYPES = [
    "ENVIRONMENTAL_LICENSE",
    "ENVIRONMENTAL_PERMIT",
    "CONSTRUCTION_PERMIT",
    "LAND_USE_APPROVAL",
    "WATER_USE_PERMIT",
    "WATER_DISCHARGE_PERMIT",
    "FORESTRY_PERMIT",
    "MINING_TITLE_OR_RIGHT",
    "EXPLOSIVES_PERMIT",
    "OCCUPATIONAL_OR_HSE_APPROVAL",
    "UTILITY_CONNECTION_APPROVAL",
    "ROAD_ACCESS_APPROVAL",
    "HERITAGE_APPROVAL",
    "AVIATION_HEIGHT_APPROVAL",
    "OPERATING_LICENSE",
    "COMMISSIONING_APPROVAL",
    "OTHER",
]

DEFAULT_CONFIGURATION: dict[str, Any] = {
    "configuration_code": "PYP-PERMIT-READINESS",
    "applicable_governance_models": ["CAPITAL_OWNER"],
    "permit_types": [
        {"code": code, "name": code.replace("_", " ").title(), "authority_type": "CONFIGURED"} for code in PERMIT_TYPES
    ],
    "requirements": [
        {
            "requirement_key": "MINING_ENVIRONMENTAL_LICENSE",
            "permit_type_code": "ENVIRONMENTAL_LICENSE",
            "description": "Configured environmental licence requirement for Mining FFA contexts.",
            "applicable_project_types": ["MINING"],
            "applicable_geographies": ["*"],
            "applicable_gate_profiles": ["PYP-FFA"],
            "required": True,
            "blocking": True,
            "evidence_required": True,
        },
        {
            "requirement_key": "MINING_TITLE_OR_RIGHT",
            "permit_type_code": "MINING_TITLE_OR_RIGHT",
            "description": "Configured title or right requirement for Mining FFA contexts.",
            "applicable_project_types": ["MINING"],
            "applicable_geographies": ["*"],
            "applicable_gate_profiles": ["PYP-FFA"],
            "required": True,
            "blocking": True,
            "evidence_required": True,
        },
        {
            "requirement_key": "MINING_WATER_USE_PERMIT",
            "permit_type_code": "WATER_USE_PERMIT",
            "description": "Configured water-use requirement for Mining FFA contexts.",
            "applicable_project_types": ["MINING"],
            "applicable_geographies": ["*"],
            "applicable_gate_profiles": ["PYP-FFA"],
            "required": True,
            "blocking": True,
            "evidence_required": True,
        },
    ],
    "qualifying_statuses": {
        "PYP-FFA": ["APPROVED", "APPROVED_WITH_CONDITIONS"],
        "PYP-INV-SELECT": ["SUBMITTED", "UNDER_REVIEW", "APPROVED", "APPROVED_WITH_CONDITIONS"],
    },
    "condition_policy": "BLOCK_ONLY_ON_BLOCKING_CONDITIONS",
    "evidence_coverage_percent": 100.0,
    "class_a_project_coverage_percent": 100.0,
    "validity_days": 180,
    "source_freshness": [
        "GATE_PROFILE_POLICY",
        "PROJECT_TYPE",
        "REQUIREMENT_CATALOG",
        "PROJECT_SCOPE",
        "PROJECT_GEOGRAPHY",
        "PERMIT_STATUS",
        "PERMIT_VALIDITY",
        "PERMIT_CONDITIONS",
        "PERMIT_EVIDENCE",
        "RECOMMENDED_PROJECT_SET",
    ],
    "separation_of_duties": {
        "permit_preparer_cannot_complete": False,
        "assessment_author_cannot_complete": False,
    },
    "inheritance": ["TENANT", "ENTERPRISE", "BUSINESS_UNIT", "PORTFOLIO"],
    "scope_workspace_id": None,
}


class PermitReadinessService:
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

    # ------------------------------------------------------------------
    # Configuration governance
    # ------------------------------------------------------------------
    def ensure_seed(self) -> AdminConfiguration:
        existing = self.db.scalars(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
            )
            .order_by(AdminConfiguration.revision.desc())
        ).first()
        if existing:
            return existing
        record = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code=DEFAULT_CODE,
            name="Permit Readiness Configuration",
            description="Starter DRAFT; no permit requirements are auto-published.",
            status="draft",
            revision=1,
            version=1,
            content_json=deepcopy(DEFAULT_CONFIGURATION),
            content_hash=_hash(DEFAULT_CONFIGURATION),
            created_by_user_id=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        self._event("permit_readiness.configuration.seeded", "AdminConfiguration", record.id, {"status": "draft"})
        self.db.commit()
        self.db.refresh(record)
        return record

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

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id)
        self._check_version(source.version, expected_version)
        existing = self.db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.status == "draft",
            )
        )
        if existing:
            return existing
        revision = (
            int(
                self.db.scalar(
                    select(func.max(AdminConfiguration.revision)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                    )
                )
                or 0
            )
            + 1
        )
        record = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code=DEFAULT_CODE,
            name=source.name,
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=deepcopy(source.content_json),
            content_hash=_hash(source.content_json),
            created_by_user_id=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        self._event(
            "permit_readiness.configuration.cloned",
            "AdminConfiguration",
            record.id,
            {"source_id": source.id, "revision": revision},
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    def update_configuration(
        self,
        configuration_id: int,
        expected_version: int,
        name: str,
        description: str,
        content: dict,
    ) -> AdminConfiguration:
        record = self._configuration(configuration_id)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "ONLY_DRAFT_CONFIGURATION_IS_MUTABLE"})
        self._validate_configuration(content)
        record.name = name.strip()
        record.description = description.strip()
        record.content_json = deepcopy(content)
        record.content_hash = _hash(content)
        record.version += 1
        record.updated_at = utc_now()
        self._event(
            "permit_readiness.configuration.updated",
            "AdminConfiguration",
            record.id,
            {"revision": record.revision, "hash": record.content_hash},
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "ONLY_DRAFT_CONFIGURATION_CAN_PUBLISH"})
        self._validate_configuration(record.content_json)
        for current in self.db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.status == "published",
            )
        ).all():
            current.status = "superseded"
            current.version += 1
            current.updated_at = utc_now()
        record.status = "published"
        record.published_at = utc_now()
        record.content_hash = _hash(record.content_json)
        record.version += 1
        record.updated_at = utc_now()
        self._event(
            "permit_readiness.configuration.published",
            "AdminConfiguration",
            record.id,
            {"revision": record.revision, "hash": record.content_hash},
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    def overview(self) -> PermitReadinessOverviewOut:
        self.ensure_seed()
        return PermitReadinessOverviewOut(
            final_output=FINAL_OUTPUT,
            provider_key=PROVIDER_KEY,
            provider_status="AVAILABLE",
            final_release_status=FINAL_RELEASE_STATUS,
            configuration_count=int(
                self.db.scalar(
                    select(func.count(AdminConfiguration.id)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                    )
                )
                or 0
            ),
            project_permit_count=int(
                self.db.scalar(select(func.count(ProjectPermit.id)).where(ProjectPermit.tenant_id == self.tenant_id))
                or 0
            ),
            assessment_count=int(
                self.db.scalar(
                    select(func.count(PermitReadinessAssessment.id)).where(
                        PermitReadinessAssessment.tenant_id == self.tenant_id
                    )
                )
                or 0
            ),
            allowed_actions=self.allowed_actions(),
            safeguards=[
                "NO_AUTOMATIC_REGULATORY_DETERMINATION_OR_FILING",
                "NO_GOVERNMENT_PORTAL_OR_GIS_ENGINE",
                "NO_ENVIRONMENTAL_COMPLIANCE_ENGINE",
                "NO_INVESTMENT_DECISION_OR_FID",
                "NO_PROJECT_INITIALIZATION_ACTIVATION_OR_EXECUTION",
            ],
        )

    def admin_preview(
        self,
        *,
        portfolio_id: int | None,
        project_ids: list[int],
        gate_profile_code: str,
        configuration_id: int | None,
        content_override: dict | None,
    ) -> AdminPreviewOut:
        record = self._configuration(configuration_id) if configuration_id else self.ensure_seed()
        content = deepcopy(content_override or record.content_json)
        self._validate_configuration(content)
        projects = self._projects(project_ids)
        project_set_hash = _hash(project_ids)
        if portfolio_id and not projects:
            projects, project_set_hash = self._portfolio_projects(portfolio_id)
        rows = [self._project_readiness(project, gate_profile_code, content=content) for project in projects]
        aggregate = None
        evidence = None
        if portfolio_id:
            aggregate = self._aggregate(
                portfolio_id,
                projects,
                gate_profile_code=gate_profile_code,
                content=content,
                project_set_hash=project_set_hash,
            )
            evidence = self._evidence_from_aggregate(aggregate, gate_profile_code)
        return AdminPreviewOut(
            portfolio_workspace_id=portfolio_id,
            project_workspace_ids=[project.id for project in projects],
            gate_profile_code=gate_profile_code,
            configuration_id=record.id,
            configuration_hash=_hash(content),
            effective_requirements={
                str(project.id): self._effective_requirements(project, gate_profile_code, content)
                for project in projects
            },
            project_readiness=rows,
            aggregate=aggregate,
            gate07j_evidence=evidence,
            persisted=False,
            can_enter_fid=False,
        )

    # ------------------------------------------------------------------
    # Permit register and normalized conditions
    # ------------------------------------------------------------------
    def permits(self, project_id: int) -> list[ProjectPermit]:
        self._project(project_id)
        return list(
            self.db.scalars(
                select(ProjectPermit)
                .where(
                    ProjectPermit.tenant_id == self.tenant_id,
                    ProjectPermit.project_workspace_id == project_id,
                )
                .order_by(ProjectPermit.status, ProjectPermit.permit_number)
            ).all()
        )

    def permit(self, permit_id: int) -> ProjectPermit:
        record = self.db.scalar(
            select(ProjectPermit).where(
                ProjectPermit.tenant_id == self.tenant_id,
                ProjectPermit.id == permit_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "PROJECT_PERMIT_NOT_FOUND"})
        self._assert_scope(record.project_workspace_id)
        return record

    def create_permit(self, project_id: int, payload) -> ProjectPermit:
        project = self._project(project_id)
        existing = self.db.scalar(
            select(ProjectPermit).where(
                ProjectPermit.tenant_id == self.tenant_id,
                ProjectPermit.create_idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return existing
        content = self._effective_content(project)
        self._validate_permit_input(project, payload, content)
        if payload.renewal_of_permit_id is not None:
            source = self.permit(payload.renewal_of_permit_id)
            if source.project_workspace_id != project_id:
                raise HTTPException(status_code=422, detail={"code": "RENEWAL_PROJECT_MISMATCH"})
        record = ProjectPermit(
            tenant_id=self.tenant_id,
            project_workspace_id=project_id,
            permit_number=self._number("PROJECT_PERMIT", "PRM"),
            permit_type_code=payload.permit_type_code,
            requirement_key=payload.requirement_key,
            title=payload.title.strip(),
            description=payload.description.strip(),
            issuing_authority=payload.issuing_authority.strip(),
            jurisdiction=payload.jurisdiction,
            status=payload.status,
            application_reference=payload.application_reference,
            application_date=payload.application_date,
            approval_date=payload.approval_date,
            effective_from=payload.effective_from,
            valid_until=payload.valid_until,
            permit_identifier=payload.permit_identifier,
            evidence_refs_json=deepcopy(payload.evidence_refs),
            source_reference=payload.source_reference,
            responsible_user_id=payload.responsible_user_id,
            next_action=payload.next_action,
            target_date=payload.target_date,
            renewal_of_permit_id=payload.renewal_of_permit_id,
            create_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        self._event(
            "permit.created",
            "ProjectPermit",
            record.id,
            {"project_workspace_id": project_id, "permit_type_code": record.permit_type_code},
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    def update_permit(self, permit_id: int, expected_version: int, payload) -> ProjectPermit:
        record = self.permit(permit_id)
        self._check_version(record.revision_version, expected_version)
        project = self._project(record.project_workspace_id)
        self._validate_permit_input(project, payload, self._effective_content(project))
        for key in (
            "permit_type_code",
            "requirement_key",
            "title",
            "description",
            "issuing_authority",
            "jurisdiction",
            "application_reference",
            "application_date",
            "approval_date",
            "effective_from",
            "valid_until",
            "permit_identifier",
            "source_reference",
            "responsible_user_id",
            "next_action",
            "target_date",
        ):
            value = getattr(payload, key)
            setattr(record, key, value.strip() if isinstance(value, str) else value)
        record.evidence_refs_json = deepcopy(payload.evidence_refs)
        self._touch(record)
        self._event("permit.updated", "ProjectPermit", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def change_permit_status(self, permit_id: int, expected_version: int, payload) -> ProjectPermit:
        record = self.permit(permit_id)
        self._check_version(record.revision_version, expected_version)
        if record.status_idempotency_key == payload.idempotency_key:
            return record
        allowed = {
            "NOT_STARTED": {"IN_PREPARATION", "NOT_REQUIRED", "CANCELLED"},
            "IN_PREPARATION": {"SUBMITTED", "CANCELLED"},
            "SUBMITTED": {"UNDER_REVIEW", "APPROVED", "APPROVED_WITH_CONDITIONS", "REJECTED", "CANCELLED"},
            "UNDER_REVIEW": {"APPROVED", "APPROVED_WITH_CONDITIONS", "REJECTED", "CANCELLED"},
            "APPROVED": {"SUSPENDED", "EXPIRED", "CANCELLED"},
            "APPROVED_WITH_CONDITIONS": {"APPROVED", "SUSPENDED", "EXPIRED", "CANCELLED"},
            "SUSPENDED": {"APPROVED", "APPROVED_WITH_CONDITIONS", "EXPIRED", "CANCELLED"},
            "REJECTED": {"IN_PREPARATION", "CANCELLED"},
            "EXPIRED": set(),
            "CANCELLED": set(),
            "NOT_REQUIRED": set(),
        }
        if payload.status not in allowed.get(record.status, set()):
            raise HTTPException(
                status_code=409,
                detail={"code": "INVALID_PERMIT_STATUS_TRANSITION", "from": record.status, "to": payload.status},
            )
        record.status = payload.status
        record.status_idempotency_key = payload.idempotency_key
        self._touch(record)
        self._event("permit.status_changed", "ProjectPermit", record.id, {"status": record.status})
        self.db.commit()
        self.db.refresh(record)
        return record

    def conditions(self, permit_id: int) -> list[PermitCondition]:
        self.permit(permit_id)
        return list(
            self.db.scalars(
                select(PermitCondition)
                .where(PermitCondition.tenant_id == self.tenant_id, PermitCondition.permit_id == permit_id)
                .order_by(PermitCondition.blocking.desc(), PermitCondition.condition_key)
            ).all()
        )

    def condition(self, condition_id: int) -> PermitCondition:
        record = self.db.scalar(
            select(PermitCondition).where(
                PermitCondition.tenant_id == self.tenant_id,
                PermitCondition.id == condition_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "PERMIT_CONDITION_NOT_FOUND"})
        self.permit(record.permit_id)
        return record

    def create_condition(self, permit_id: int, payload) -> PermitCondition:
        self.permit(permit_id)
        existing = self.db.scalar(
            select(PermitCondition).where(
                PermitCondition.tenant_id == self.tenant_id,
                PermitCondition.create_idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return existing
        record = PermitCondition(
            tenant_id=self.tenant_id,
            permit_id=permit_id,
            condition_key=payload.condition_key,
            description=payload.description,
            condition_type=payload.condition_type,
            blocking=payload.blocking,
            owner_id=payload.owner_id,
            target_date=payload.target_date,
            status=payload.status,
            evidence_refs_json=deepcopy(payload.evidence_refs),
            source_reference=payload.source_reference,
            create_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        self._event("permit.condition_created", "PermitCondition", record.id, {"permit_id": permit_id})
        self.db.commit()
        self.db.refresh(record)
        return record

    def update_condition(self, condition_id: int, expected_version: int, payload) -> PermitCondition:
        record = self.condition(condition_id)
        self._check_version(record.revision_version, expected_version)
        previous = record.status
        for key in (
            "description",
            "condition_type",
            "blocking",
            "owner_id",
            "target_date",
            "status",
            "source_reference",
        ):
            setattr(record, key, getattr(payload, key))
        record.evidence_refs_json = deepcopy(payload.evidence_refs)
        self._touch(record)
        event_type = (
            "permit.condition_satisfied"
            if previous != "SATISFIED" and record.status == "SATISFIED"
            else "permit.condition_updated"
        )
        self._event(event_type, "PermitCondition", record.id, {"permit_id": record.permit_id})
        self.db.commit()
        self.db.refresh(record)
        return record

    # ------------------------------------------------------------------
    # Assessment lifecycle
    # ------------------------------------------------------------------
    def assessments(self, project_id: int) -> list[PermitReadinessAssessment]:
        self._project(project_id)
        return list(
            self.db.scalars(
                select(PermitReadinessAssessment)
                .where(
                    PermitReadinessAssessment.tenant_id == self.tenant_id,
                    PermitReadinessAssessment.project_workspace_id == project_id,
                )
                .order_by(
                    PermitReadinessAssessment.gate_profile_code,
                    PermitReadinessAssessment.assessment_version.desc(),
                )
            ).all()
        )

    def assessment(self, assessment_id: int) -> PermitReadinessAssessment:
        record = self.db.scalar(
            select(PermitReadinessAssessment).where(
                PermitReadinessAssessment.tenant_id == self.tenant_id,
                PermitReadinessAssessment.id == assessment_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "PERMIT_READINESS_ASSESSMENT_NOT_FOUND"})
        self._assert_scope(record.project_workspace_id)
        return record

    def create_assessment(self, project_id: int, payload) -> PermitReadinessAssessment:
        project = self._project(project_id)
        existing = self.db.scalar(
            select(PermitReadinessAssessment).where(
                PermitReadinessAssessment.tenant_id == self.tenant_id,
                PermitReadinessAssessment.create_idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return existing
        active = self.db.scalar(
            select(PermitReadinessAssessment).where(
                PermitReadinessAssessment.tenant_id == self.tenant_id,
                PermitReadinessAssessment.project_workspace_id == project_id,
                PermitReadinessAssessment.gate_profile_code == payload.gate_profile_code,
                PermitReadinessAssessment.status.in_(["DRAFT", "IN_PROGRESS"]),
            )
        )
        if active:
            return active
        configuration = self._published_configuration(project)
        if configuration is None:
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_PERMIT_CONFIGURATION_REQUIRED"})
        version = (
            int(
                self.db.scalar(
                    select(func.max(PermitReadinessAssessment.assessment_version)).where(
                        PermitReadinessAssessment.tenant_id == self.tenant_id,
                        PermitReadinessAssessment.project_workspace_id == project_id,
                        PermitReadinessAssessment.gate_profile_code == payload.gate_profile_code,
                    )
                )
                or 0
            )
            + 1
        )
        as_of = payload.as_of_date or utc_now()
        computed = self._compute(project, configuration.content_json, as_of, payload.gate_profile_code)
        record = PermitReadinessAssessment(
            tenant_id=self.tenant_id,
            project_workspace_id=project_id,
            assessment_number=self._number("PERMIT_READINESS_ASSESSMENT", "PRA"),
            assessment_version=version,
            as_of_date=as_of,
            valid_until=self._assessment_valid_until(as_of, computed, configuration.content_json),
            gate_profile_code=payload.gate_profile_code,
            project_type_code=self._project_type(project),
            status="IN_PROGRESS",
            configuration_id=configuration.id,
            configuration_revision=configuration.revision,
            configuration_hash=configuration.content_hash,
            assessed_by=self.actor_id,
            create_idempotency_key=payload.idempotency_key,
            **self._computed_values(computed),
        )
        self.db.add(record)
        self.db.flush()
        self._event(
            "permit_readiness.assessment_created",
            "PermitReadinessAssessment",
            record.id,
            {"project_workspace_id": project_id, "gate_profile": payload.gate_profile_code, "version": version},
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    def update_assessment(self, assessment_id: int, expected_version: int, payload) -> PermitReadinessAssessment:
        record = self.assessment(assessment_id)
        self._check_version(record.revision_version, expected_version)
        if record.status not in {"DRAFT", "IN_PROGRESS"}:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_IS_IMMUTABLE"})
        configuration = self._configuration(record.configuration_id)
        project = self._project(record.project_workspace_id)
        computed = self._compute(project, configuration.content_json, payload.as_of_date, record.gate_profile_code)
        record.as_of_date = payload.as_of_date
        record.valid_until = self._assessment_valid_until(payload.as_of_date, computed, configuration.content_json)
        self._apply_computed(record, computed)
        self._touch(record)
        self._event("permit_readiness.assessment_updated", "PermitReadinessAssessment", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def complete_assessment(self, assessment_id: int, expected_version: int, payload) -> PermitReadinessAssessment:
        record = self.assessment(assessment_id)
        self._check_version(record.revision_version, expected_version)
        if record.complete_idempotency_key == payload.idempotency_key:
            return record
        if record.status not in {"DRAFT", "IN_PROGRESS"}:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_IS_IMMUTABLE"})
        project = self._project(record.project_workspace_id)
        configuration = self._published_configuration(project)
        if configuration is None or configuration.content_hash != record.configuration_hash:
            raise HTTPException(
                status_code=412,
                detail={"code": "STALE_PERMIT_SOURCE", "reason": "CONFIGURATION_CHANGED"},
            )
        computed = self._compute(project, configuration.content_json, utc_now(), record.gate_profile_code)
        if computed["permit_source_hash"] != record.permit_source_hash:
            raise HTTPException(
                status_code=412,
                detail={"code": "STALE_PERMIT_SOURCE", "reason": "PERMIT_REGISTER_CHANGED"},
            )
        if computed["blockers"]:
            raise HTTPException(
                status_code=409,
                detail={"code": "PERMIT_READINESS_BLOCKED", "blockers": computed["blockers"]},
            )
        sod = dict(configuration.content_json.get("separation_of_duties", {}))
        if sod.get("assessment_author_cannot_complete") and record.assessed_by == self.actor_id:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_AUTHOR_CANNOT_COMPLETE"})
        self._apply_computed(record, computed)
        record.status = "COMPLETED"
        record.readiness_status = "READY"
        record.completed_by = self.actor_id
        record.completed_at = utc_now()
        record.complete_idempotency_key = payload.idempotency_key
        record.permit_readiness_hash = self._readiness_hash(record, computed)
        self._touch(record)
        self._event(
            "permit_readiness.assessment_completed",
            "PermitReadinessAssessment",
            record.id,
            {"permit_readiness_hash": record.permit_readiness_hash},
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    def reassess(self, assessment_id: int, payload) -> PermitReadinessAssessment:
        source = self.assessment(assessment_id)
        existing = self.db.scalar(
            select(PermitReadinessAssessment).where(
                PermitReadinessAssessment.tenant_id == self.tenant_id,
                PermitReadinessAssessment.reassessment_idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return existing
        if source.status != "COMPLETED":
            raise HTTPException(status_code=409, detail={"code": "ONLY_COMPLETED_ASSESSMENT_CAN_REASSESS"})
        created = self.create_assessment(
            source.project_workspace_id,
            type(
                "ReassessmentPayload",
                (),
                {
                    "gate_profile_code": source.gate_profile_code,
                    "as_of_date": utc_now(),
                    "idempotency_key": payload.idempotency_key,
                },
            )(),
        )
        created.reassessment_idempotency_key = payload.idempotency_key
        created.create_idempotency_key = None
        self._event(
            "permit_readiness.assessment_reassessed",
            "PermitReadinessAssessment",
            created.id,
            {"source_assessment_id": source.id},
        )
        self.db.commit()
        self.db.refresh(created)
        return created

    def refresh_preview(self, project_id: int, gate_profile_code: str = "PYP-FFA") -> RefreshPreviewOut:
        project = self._project(project_id)
        content = self._effective_content(project)
        computed = self._compute(project, content, utc_now(), gate_profile_code)
        latest = self._latest_completed(project_id, gate_profile_code)
        previous = self._project_readiness(project, gate_profile_code, content=content)
        return RefreshPreviewOut(
            project_workspace_id=project_id,
            assessment_id=latest.id if latest else None,
            previous_source_hash=latest.permit_source_hash if latest else None,
            current_source_hash=computed["permit_source_hash"],
            changes={
                "source_hash_changed": bool(latest and latest.permit_source_hash != computed["permit_source_hash"]),
                "required_permit_delta": computed["required_permit_count"]
                - (latest.required_permit_count if latest else 0),
                "approved_delta": computed["approved_count"] - (latest.approved_count if latest else 0),
                "missing_delta": computed["missing_count"] - (latest.missing_count if latest else 0),
                "expired_delta": computed["expired_count"] - (latest.expired_count if latest else 0),
                "blocking_condition_delta": computed["open_blocking_conditions_count"]
                - (latest.open_blocking_conditions_count if latest else 0),
            },
            previous_readiness=previous.readiness_status if latest else None,
            current_readiness=computed["readiness_status"],
            warnings=computed["warnings"],
            blockers=computed["blockers"],
            persisted=False,
        )

    def refresh_apply(
        self,
        project_id: int,
        expected_version: int,
        payload,
        gate_profile_code: str = "PYP-FFA",
    ) -> PermitReadinessAssessment:
        active = self.db.scalar(
            select(PermitReadinessAssessment).where(
                PermitReadinessAssessment.tenant_id == self.tenant_id,
                PermitReadinessAssessment.project_workspace_id == project_id,
                PermitReadinessAssessment.gate_profile_code == gate_profile_code,
                PermitReadinessAssessment.status.in_(["DRAFT", "IN_PROGRESS"]),
            )
        )
        if active is None:
            latest = self._latest_completed(project_id, gate_profile_code)
            if latest is None:
                raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_NOT_FOUND"})
            return self.reassess(latest.id, payload)
        self._check_version(active.revision_version, expected_version)
        if active.refresh_idempotency_key == payload.idempotency_key:
            return active
        configuration = self._configuration(active.configuration_id)
        project = self._project(project_id)
        computed = self._compute(project, configuration.content_json, utc_now(), gate_profile_code)
        self._apply_computed(active, computed)
        active.refresh_idempotency_key = payload.idempotency_key
        self._touch(active)
        self._event("permit_readiness.refresh_applied", "PermitReadinessAssessment", active.id, {})
        self.db.commit()
        self.db.refresh(active)
        return active

    # ------------------------------------------------------------------
    # Project and Project Set readiness
    # ------------------------------------------------------------------
    def project_readiness(
        self,
        project_id: int,
        gate_profile_code: str = "PYP-FFA",
    ) -> ProjectPermitReadinessOut:
        return self._project_readiness(self._project(project_id), gate_profile_code)

    def portfolio_readiness(
        self,
        portfolio_id: int,
        gate_profile_code: str = "PYP-FFA",
    ) -> ProjectSetPermitReadinessOut:
        projects, project_set_hash = self._portfolio_projects(portfolio_id)
        return self._aggregate(
            portfolio_id,
            projects,
            gate_profile_code=gate_profile_code,
            project_set_hash=project_set_hash,
        )

    def portfolio_projects(
        self,
        portfolio_id: int,
        gate_profile_code: str = "PYP-FFA",
    ) -> list[ProjectPermitReadinessOut]:
        projects, _ = self._portfolio_projects(portfolio_id)
        return [self._project_readiness(project, gate_profile_code) for project in projects]

    def investment_gate_evidence(
        self,
        portfolio_id: int,
        gate_profile_code: str = "PYP-FFA",
    ) -> InvestmentGatePermitEvidenceOut:
        return self._evidence_from_aggregate(
            self.portfolio_readiness(portfolio_id, gate_profile_code), gate_profile_code
        )

    def project_investment_gate_evidence(
        self,
        project_id: int,
        gate_profile_code: str = "PYP-FFA",
    ) -> InvestmentGatePermitEvidenceOut:
        project = self._project(project_id)
        readiness = self._project_readiness(project, gate_profile_code)
        aggregate = ProjectSetPermitReadinessOut(
            portfolio_workspace_id=project.parent_id or project.id,
            recommended_project_set_hash=_hash([project.id]),
            required_project_count=1 if readiness.permit_classification == "A" else 0,
            valid_project_count=1
            if readiness.permit_classification == "A" and readiness.readiness_status == "READY"
            else 0,
            blocked_project_count=1 if readiness.readiness_status in {"BLOCKED", "NOT_STARTED"} else 0,
            stale_project_count=1 if readiness.readiness_status == "STALE" else 0,
            expired_project_count=1 if readiness.readiness_status == "EXPIRED" else 0,
            coverage_percent=100.0
            if readiness.permit_classification == "A" and readiness.readiness_status == "READY"
            else 0.0,
            aggregate_required_permit_count=readiness.required_count,
            aggregate_approved_count=readiness.approved_count,
            aggregate_conditional_count=readiness.conditional_count,
            aggregate_missing_count=readiness.missing_count,
            aggregate_rejected_count=readiness.rejected_count,
            aggregate_suspended_count=readiness.suspended_count,
            aggregate_expired_count=readiness.expired_count,
            aggregate_blocking_condition_count=readiness.open_blocking_conditions,
            warnings=readiness.warnings,
            blockers=readiness.blockers,
            readiness_status=readiness.readiness_status,
            permit_readiness_hash=readiness.permit_readiness_hash or _hash({"project": project.id, "empty": True}),
            project_readiness=[readiness],
        )
        return self._evidence_from_aggregate(aggregate, gate_profile_code, project_scope=project.id)

    def _project_readiness(
        self,
        project: EnterpriseWorkspace,
        gate_profile_code: str,
        *,
        content: dict | None = None,
        latest: PermitReadinessAssessment | None = None,
        permits: list[ProjectPermit] | None = None,
        conditions: list[PermitCondition] | None = None,
    ) -> ProjectPermitReadinessOut:
        content = content or self._effective_content(project)
        classification = self._permit_classification(project, gate_profile_code)
        latest = latest or self._latest_completed(project.id, gate_profile_code)
        computed = self._compute(
            project,
            content,
            utc_now(),
            gate_profile_code,
            permits=permits,
            conditions=conditions,
        )
        if latest is None:
            blockers = list(computed["blockers"])
            if classification == "A":
                blockers.append("PERMIT_READINESS_ASSESSMENT_REQUIRED")
            return ProjectPermitReadinessOut(
                project_workspace_id=project.id,
                project_type_code=self._project_type(project),
                permit_classification=classification,
                gate_profile=gate_profile_code,
                assessment_id=None,
                assessment_hash=None,
                as_of_date=None,
                valid_until=None,
                required_count=computed["required_permit_count"],
                approved_count=computed["approved_count"],
                conditional_count=computed["approved_with_conditions_count"],
                missing_count=computed["missing_count"],
                rejected_count=computed["rejected_count"],
                suspended_count=computed["suspended_count"],
                expired_count=computed["expired_count"],
                open_blocking_conditions=computed["open_blocking_conditions_count"],
                evidence_coverage_percent=computed["evidence_coverage_percent"],
                warnings=computed["warnings"],
                blockers=sorted(set(blockers)),
                readiness_status="NOT_STARTED" if classification == "A" else computed["readiness_status"],
                permit_readiness_hash=None,
                source_current=False,
                allowed_actions=self.allowed_actions(),
            )
        current_config = self._published_configuration(project)
        source_current = bool(
            current_config
            and current_config.content_hash == latest.configuration_hash
            and computed["permit_source_hash"] == latest.permit_source_hash
        )
        status = latest.readiness_status
        blockers = list(latest.blockers_json or [])
        warnings = list(latest.warnings_json or [])
        if not source_current:
            status = "STALE"
            blockers = sorted(set(blockers + ["STALE_PERMIT_SOURCE"]))
        elif utc_now() > latest.valid_until:
            status = "EXPIRED"
            blockers = sorted(set(blockers + ["PERMIT_READINESS_EXPIRED"]))
        return ProjectPermitReadinessOut(
            project_workspace_id=project.id,
            project_type_code=latest.project_type_code,
            permit_classification=classification,
            gate_profile=latest.gate_profile_code,
            assessment_id=latest.id,
            assessment_hash=latest.permit_readiness_hash,
            as_of_date=latest.as_of_date,
            valid_until=latest.valid_until,
            required_count=latest.required_permit_count,
            approved_count=latest.approved_count,
            conditional_count=latest.approved_with_conditions_count,
            missing_count=latest.missing_count,
            rejected_count=latest.rejected_count,
            suspended_count=latest.suspended_count,
            expired_count=latest.expired_count,
            open_blocking_conditions=latest.open_blocking_conditions_count,
            evidence_coverage_percent=latest.evidence_coverage_percent,
            warnings=warnings,
            blockers=blockers,
            readiness_status=status,
            permit_readiness_hash=latest.permit_readiness_hash,
            source_current=source_current and status not in {"STALE", "EXPIRED"},
            allowed_actions=self.allowed_actions(),
        )

    def _aggregate(
        self,
        portfolio_id: int,
        projects: list[EnterpriseWorkspace],
        *,
        gate_profile_code: str,
        content: dict | None = None,
        project_set_hash: str | None = None,
    ) -> ProjectSetPermitReadinessOut:
        self._portfolio(portfolio_id)
        project_ids = [project.id for project in projects]
        permits = list(
            self.db.scalars(
                select(ProjectPermit).where(
                    ProjectPermit.tenant_id == self.tenant_id,
                    ProjectPermit.project_workspace_id.in_(project_ids or [-1]),
                )
            ).all()
        )
        conditions = list(
            self.db.scalars(
                select(PermitCondition).where(
                    PermitCondition.tenant_id == self.tenant_id,
                    PermitCondition.permit_id.in_([item.id for item in permits] or [-1]),
                )
            ).all()
        )
        latest_rows = list(
            self.db.scalars(
                select(PermitReadinessAssessment)
                .where(
                    PermitReadinessAssessment.tenant_id == self.tenant_id,
                    PermitReadinessAssessment.project_workspace_id.in_(project_ids or [-1]),
                    PermitReadinessAssessment.gate_profile_code == gate_profile_code,
                    PermitReadinessAssessment.status == "COMPLETED",
                )
                .order_by(
                    PermitReadinessAssessment.project_workspace_id,
                    PermitReadinessAssessment.assessment_version.desc(),
                )
            ).all()
        )
        permits_by_project: dict[int, list[ProjectPermit]] = defaultdict(list)
        for item in permits:
            permits_by_project[item.project_workspace_id].append(item)
        conditions_by_permit: dict[int, list[PermitCondition]] = defaultdict(list)
        for item in conditions:
            conditions_by_permit[item.permit_id].append(item)
        latest_by_project: dict[int, PermitReadinessAssessment] = {}
        for item in latest_rows:
            latest_by_project.setdefault(item.project_workspace_id, item)
        rows = []
        for project in projects:
            project_permits = permits_by_project.get(project.id, [])
            project_conditions = [
                condition for permit in project_permits for condition in conditions_by_permit.get(permit.id, [])
            ]
            rows.append(
                self._project_readiness(
                    project,
                    gate_profile_code,
                    content=content,
                    latest=latest_by_project.get(project.id),
                    permits=project_permits,
                    conditions=project_conditions,
                )
            )
        required_rows = [item for item in rows if item.permit_classification == "A"]
        required = len(required_rows)
        valid = sum(item.readiness_status == "READY" and item.source_current for item in required_rows)
        blocked = sum(item.readiness_status in {"BLOCKED", "NOT_STARTED"} for item in required_rows)
        stale = sum(item.readiness_status == "STALE" for item in required_rows)
        expired = sum(item.readiness_status == "EXPIRED" for item in required_rows)
        coverage = round(valid / required * 100, 2) if required else 100.0
        blockers = sorted({value for row in required_rows for value in row.blockers})
        if required and coverage < 100:
            blockers = sorted(set(blockers + ["PERMIT_READINESS_COVERAGE_BELOW_100"]))
        warnings = sorted({value for row in rows for value in row.warnings})
        set_hash = project_set_hash or _hash(project_ids)
        readiness_hash = _hash(
            {
                "portfolio": portfolio_id,
                "project_set_hash": set_hash,
                "gate_profile": gate_profile_code,
                "projects": [
                    {
                        "id": row.project_workspace_id,
                        "class": row.permit_classification,
                        "status": row.readiness_status,
                        "hash": row.permit_readiness_hash,
                        "current": row.source_current,
                    }
                    for row in rows
                ],
                "coverage": coverage,
                "blockers": blockers,
            }
        )
        return ProjectSetPermitReadinessOut(
            portfolio_workspace_id=portfolio_id,
            recommended_project_set_hash=set_hash,
            required_project_count=required,
            valid_project_count=valid,
            blocked_project_count=blocked,
            stale_project_count=stale,
            expired_project_count=expired,
            coverage_percent=coverage,
            aggregate_required_permit_count=sum(item.required_count for item in required_rows),
            aggregate_approved_count=sum(item.approved_count for item in required_rows),
            aggregate_conditional_count=sum(item.conditional_count for item in required_rows),
            aggregate_missing_count=sum(item.missing_count for item in required_rows),
            aggregate_rejected_count=sum(item.rejected_count for item in required_rows),
            aggregate_suspended_count=sum(item.suspended_count for item in required_rows),
            aggregate_expired_count=sum(item.expired_count for item in required_rows),
            aggregate_blocking_condition_count=sum(item.open_blocking_conditions for item in required_rows),
            warnings=warnings,
            blockers=blockers,
            readiness_status="READY" if coverage == 100 and not blockers else "BLOCKED",
            permit_readiness_hash=readiness_hash,
            project_readiness=rows,
        )

    def _evidence_from_aggregate(
        self,
        aggregate: ProjectSetPermitReadinessOut,
        gate_profile_code: str,
        *,
        project_scope: int | None = None,
    ) -> InvestmentGatePermitEvidenceOut:
        relevant = [
            item
            for item in aggregate.project_readiness
            if item.permit_classification == "A" or project_scope == item.project_workspace_id
        ]
        dates = [item.as_of_date for item in relevant if item.as_of_date]
        validities = [item.valid_until for item in relevant if item.valid_until]
        source_hash = _hash(
            {
                "project_set_hash": aggregate.recommended_project_set_hash,
                "projects": [
                    {
                        "id": item.project_workspace_id,
                        "assessment": item.assessment_id,
                        "hash": item.assessment_hash,
                        "status": item.readiness_status,
                        "current": item.source_current,
                    }
                    for item in relevant
                ],
            }
        )
        current = bool(relevant) and all(item.source_current for item in relevant)
        can_supply = (
            aggregate.required_project_count > 0
            and aggregate.readiness_status == "READY"
            and current
            and aggregate.coverage_percent == 100
            and not aggregate.blockers
        )
        evidence_coverage = (
            round(
                sum(item.evidence_coverage_percent for item in relevant) / len(relevant),
                2,
            )
            if relevant
            else 0.0
        )
        return InvestmentGatePermitEvidenceOut(
            final_output=FINAL_OUTPUT,
            provider_key=PROVIDER_KEY,
            source_module=SOURCE_MODULE,
            evidence_type=EVIDENCE_TYPE,
            scope="EACH_PROJECT" if project_scope else "PROJECT_SET",
            portfolio_workspace_id=None if project_scope else aggregate.portfolio_workspace_id,
            project_workspace_id=project_scope,
            recommended_project_set_hash=None if project_scope else aggregate.recommended_project_set_hash,
            gate_profile=gate_profile_code,
            assessment_id=relevant[0].assessment_id if project_scope and relevant else None,
            aggregate_reference=None if project_scope else f"PERMIT-READINESS:{aggregate.permit_readiness_hash}",
            assessment_date=max(dates) if dates else None,
            valid_until=min(validities) if validities else None,
            permit_source_hash=source_hash,
            permit_readiness_hash=aggregate.permit_readiness_hash,
            required_project_count=aggregate.required_project_count,
            valid_project_count=aggregate.valid_project_count,
            coverage_percent=aggregate.coverage_percent,
            required_permit_count=aggregate.aggregate_required_permit_count,
            approved_permit_count=aggregate.aggregate_approved_count,
            approved_with_conditions_count=aggregate.aggregate_conditional_count,
            missing_permit_count=aggregate.aggregate_missing_count,
            rejected_permit_count=aggregate.aggregate_rejected_count,
            suspended_permit_count=aggregate.aggregate_suspended_count,
            expired_permit_count=aggregate.aggregate_expired_count,
            open_blocking_conditions_count=aggregate.aggregate_blocking_condition_count,
            evidence_coverage_percent=evidence_coverage,
            warnings=aggregate.warnings,
            blockers=aggregate.blockers,
            readiness_status=aggregate.readiness_status,
            source_current=current,
            can_supply_investment_gate_evidence=can_supply,
            can_enter_fid=False,
        )

    # ------------------------------------------------------------------
    # Deterministic readiness calculation
    # ------------------------------------------------------------------
    def _compute(
        self,
        project: EnterpriseWorkspace,
        content: dict,
        as_of: datetime,
        gate_profile_code: str,
        *,
        permits: list[ProjectPermit] | None = None,
        conditions: list[PermitCondition] | None = None,
    ) -> dict[str, Any]:
        requirements = self._effective_requirements(project, gate_profile_code, content)
        permits = permits if permits is not None else self.permits(project.id)
        permit_ids = [item.id for item in permits]
        conditions = (
            conditions
            if conditions is not None
            else list(
                self.db.scalars(
                    select(PermitCondition).where(
                        PermitCondition.tenant_id == self.tenant_id,
                        PermitCondition.permit_id.in_(permit_ids or [-1]),
                    )
                ).all()
            )
        )
        condition_map: dict[int, list[PermitCondition]] = defaultdict(list)
        for item in conditions:
            condition_map[item.permit_id].append(item)
        permit_map: dict[str, list[ProjectPermit]] = defaultdict(list)
        for item in permits:
            if item.requirement_key:
                permit_map[item.requirement_key].append(item)
        selected: dict[str, ProjectPermit | None] = {}
        for requirement in requirements:
            candidates = permit_map.get(str(requirement["requirement_key"]), [])
            selected[str(requirement["requirement_key"])] = max(
                candidates,
                default=None,
                key=lambda item: (item.created_at, item.revision_version, item.id),
            )
        qualifying = set(
            dict(content.get("qualifying_statuses", {})).get(
                gate_profile_code,
                ["APPROVED", "APPROVED_WITH_CONDITIONS"],
            )
        )
        condition_policy = str(content.get("condition_policy", "BLOCK_ONLY_ON_BLOCKING_CONDITIONS"))
        counts = defaultdict(int)
        warnings: list[str] = []
        blockers: list[str] = []
        evidence_complete = 0
        permit_validities: list[date] = []
        for requirement in requirements:
            key = str(requirement["requirement_key"])
            permit = selected[key]
            if permit is None:
                counts["missing"] += 1
                blockers.append(f"MISSING_REQUIRED_PERMIT:{key}")
                continue
            effective_status = permit.status
            if permit.valid_until and permit.valid_until < as_of.date():
                effective_status = "EXPIRED"
                if permit.status != "EXPIRED":
                    warnings.append(f"PERMIT_EXPIRY_DETECTED:{permit.permit_number}")
            counts[effective_status] += 1
            if permit.valid_until:
                permit_validities.append(permit.valid_until)
            if permit.evidence_refs_json:
                evidence_complete += 1
            else:
                blockers.append(f"PERMIT_EVIDENCE_REQUIRED:{permit.permit_number}")
            permit_conditions = condition_map.get(permit.id, [])
            open_conditions = [item for item in permit_conditions if item.status not in {"SATISFIED", "WAIVED"}]
            blocking_conditions = [item for item in open_conditions if item.blocking]
            open_blocking_for_permit = 0
            if condition_policy == "BLOCK_ON_ANY_OPEN_CONDITION":
                open_blocking_for_permit = len(open_conditions)
            elif condition_policy == "BLOCK_ONLY_ON_BLOCKING_CONDITIONS":
                open_blocking_for_permit = len(blocking_conditions)
            counts["open_blocking_conditions"] += open_blocking_for_permit
            if effective_status == "REJECTED":
                blockers.append(f"PERMIT_REJECTED:{permit.permit_number}")
            elif effective_status == "SUSPENDED":
                blockers.append(f"PERMIT_SUSPENDED:{permit.permit_number}")
            elif effective_status == "EXPIRED":
                blockers.append(f"PERMIT_EXPIRED:{permit.permit_number}")
            elif effective_status not in qualifying:
                blockers.append(f"PERMIT_NOT_APPROVED:{permit.permit_number}")
            elif effective_status == "APPROVED_WITH_CONDITIONS" and open_blocking_for_permit:
                blockers.extend(f"OPEN_BLOCKING_CONDITION:{item.condition_key}" for item in blocking_conditions)
        required_count = len(requirements)
        coverage = round(evidence_complete / required_count * 100, 2) if required_count else 0.0
        threshold = float(content.get("evidence_coverage_percent", 100.0))
        if required_count == 0:
            blockers.append("PERMIT_REQUIREMENT_SET_EMPTY")
        if coverage < threshold:
            blockers.append("PERMIT_EVIDENCE_COVERAGE_BELOW_THRESHOLD")
        if counts["open_blocking_conditions"]:
            blockers.append("OPEN_BLOCKING_PERMIT_CONDITIONS")
        requirement_hash = _hash(requirements)
        register_hash = _hash(
            [
                self._permit_hash_payload(item, condition_map.get(item.id, []))
                for item in sorted(permits, key=lambda value: value.id)
            ]
        )
        source_hash = _hash(
            {
                "project": self._project_context(project),
                "gate_profile": gate_profile_code,
                "requirements": requirements,
                "requirement_set_hash": requirement_hash,
                "permit_register_hash": register_hash,
                "configuration_hash": _hash(content),
            }
        )
        return {
            "requirement_set_hash": requirement_hash,
            "permit_register_hash": register_hash,
            "permit_source_hash": source_hash,
            "required_permit_count": required_count,
            "approved_count": counts["APPROVED"],
            "approved_with_conditions_count": counts["APPROVED_WITH_CONDITIONS"],
            "submitted_count": counts["SUBMITTED"],
            "under_review_count": counts["UNDER_REVIEW"],
            "missing_count": counts["missing"],
            "rejected_count": counts["REJECTED"],
            "suspended_count": counts["SUSPENDED"],
            "expired_count": counts["EXPIRED"],
            "open_blocking_conditions_count": counts["open_blocking_conditions"],
            "evidence_coverage_percent": coverage,
            "warnings": sorted(set(warnings)),
            "blockers": sorted(set(blockers)),
            "readiness_status": "READY" if not blockers else "BLOCKED",
            "permit_validities": permit_validities,
        }

    def _effective_requirements(
        self,
        project: EnterpriseWorkspace,
        gate_profile_code: str,
        content: dict,
    ) -> list[dict[str, Any]]:
        context = self._project_context(project)
        if context["governance_model"] not in set(content.get("applicable_governance_models", [])):
            return []
        output: list[dict[str, Any]] = []
        for source in content.get("requirements", []):
            rule = deepcopy(source)
            project_types = {str(value).upper() for value in rule.get("applicable_project_types", ["*"])}
            profiles = {str(value).upper() for value in rule.get("applicable_gate_profiles", ["*"])}
            geographies = {str(value).upper() for value in rule.get("applicable_geographies", ["*"])}
            if "*" not in project_types and context["project_type"] not in project_types:
                continue
            if "*" not in profiles and gate_profile_code.upper() not in profiles:
                continue
            if "*" not in geographies and not (set(context["geographies"]) & geographies):
                continue
            if not rule.get("required", True):
                continue
            rule["resolved_project_type"] = context["project_type"]
            rule["resolved_geography"] = context["geographies"]
            rule["resolved_gate_profile"] = gate_profile_code
            output.append(rule)
        return sorted(output, key=lambda item: str(item.get("requirement_key")))

    @staticmethod
    def _permit_hash_payload(record: ProjectPermit, conditions: list[PermitCondition]) -> dict[str, Any]:
        return {
            "id": record.id,
            "project_workspace_id": record.project_workspace_id,
            "permit_number": record.permit_number,
            "permit_type_code": record.permit_type_code,
            "requirement_key": record.requirement_key,
            "status": record.status,
            "application_date": record.application_date,
            "approval_date": record.approval_date,
            "effective_from": record.effective_from,
            "valid_until": record.valid_until,
            "permit_identifier": record.permit_identifier,
            "evidence_refs": record.evidence_refs_json,
            "renewal_of_permit_id": record.renewal_of_permit_id,
            "revision_version": record.revision_version,
            "conditions": [
                {
                    "id": item.id,
                    "key": item.condition_key,
                    "blocking": item.blocking,
                    "status": item.status,
                    "evidence": item.evidence_refs_json,
                    "revision_version": item.revision_version,
                }
                for item in sorted(conditions, key=lambda value: value.id)
            ],
        }

    @staticmethod
    def _computed_values(computed: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "requirement_set_hash",
            "permit_register_hash",
            "permit_source_hash",
            "required_permit_count",
            "approved_count",
            "approved_with_conditions_count",
            "submitted_count",
            "under_review_count",
            "missing_count",
            "rejected_count",
            "suspended_count",
            "expired_count",
            "open_blocking_conditions_count",
            "evidence_coverage_percent",
            "readiness_status",
        )
        values = {key: computed[key] for key in keys}
        values["warnings_json"] = computed["warnings"]
        values["blockers_json"] = computed["blockers"]
        return values

    def _apply_computed(self, record: PermitReadinessAssessment, computed: dict[str, Any]) -> None:
        for key, value in self._computed_values(computed).items():
            setattr(record, key, value)

    @staticmethod
    def _assessment_valid_until(as_of: datetime, computed: dict, content: dict) -> datetime:
        configured = as_of + timedelta(days=int(content.get("validity_days", 180)))
        permit_dates = [
            datetime.combine(value, datetime.min.time()) for value in computed.get("permit_validities", []) if value
        ]
        return min([configured, *permit_dates]) if permit_dates else configured

    @staticmethod
    def _readiness_hash(record: PermitReadinessAssessment, computed: dict[str, Any]) -> str:
        return _hash(
            {
                "assessment_number": record.assessment_number,
                "assessment_version": record.assessment_version,
                "project": record.project_workspace_id,
                "gate_profile": record.gate_profile_code,
                "source_hash": computed["permit_source_hash"],
                "configuration_hash": record.configuration_hash,
                "counts": PermitReadinessService._computed_values(computed),
            }
        )

    # ------------------------------------------------------------------
    # Gate policy, permissions and shared repository helpers
    # ------------------------------------------------------------------
    def _permit_classification(self, project: EnterpriseWorkspace, gate_profile_code: str) -> str:
        from app.modules.investment_evidence_policy.service import (
            DEFAULT_POLICY,
            InvestmentEvidencePolicyService,
        )

        policy = InvestmentEvidencePolicyService(self.db, self.tenant_id, self.actor_id, self.context)
        configuration = policy._effective_configuration(project)
        content = deepcopy(configuration.content_json if configuration else DEFAULT_POLICY)
        rows = policy._effective_matrix(content, gate_profile_code, [project])
        row = next(
            (
                item
                for item in rows
                if item.get("evidence_type") == "PERMIT_READINESS" and item.get("project_workspace_id") == project.id
            ),
            None,
        )
        if row is None:
            row = next((item for item in rows if item.get("evidence_type") == "PERMIT_READINESS"), None)
        return str((row or {}).get("classification") or "C")

    def allowed_actions(self) -> dict[str, bool]:
        roles = set(self.context.role_codes if self.context else {"organization_admin"})
        admin = bool(roles & {"organization_admin", "permit_configuration_admin"})
        manager = bool(roles & {"organization_admin", "permit_manager"})
        owner = bool(roles & {"organization_admin", "permit_manager", "permit_owner"})
        assessor = bool(roles & {"organization_admin", "permit_manager", "permit_assessor"})
        reviewer = bool(roles & {"organization_admin", "permit_manager", "permit_reviewer"})
        viewer = bool(roles)
        return {
            "can_view_permits": viewer,
            "can_create_permit": manager,
            "can_edit_permit": owner,
            "can_change_permit_status": manager,
            "can_manage_permit_conditions": owner,
            "can_start_permit_readiness_assessment": assessor,
            "can_edit_permit_readiness_assessment": assessor,
            "can_complete_permit_readiness_assessment": reviewer,
            "can_start_permit_reassessment": assessor,
            "can_refresh_permit_readiness": assessor,
            "can_view_gate07j_permit_evidence": viewer,
            "can_admin_configure": admin,
            "can_admin_publish": admin,
            "can_enter_fid": False,
        }

    def _validate_permit_input(self, project: EnterpriseWorkspace, payload, content: dict) -> None:
        codes = {str(item.get("code")) for item in content.get("permit_types", [])}
        if payload.permit_type_code not in codes:
            raise HTTPException(status_code=422, detail={"code": "PERMIT_TYPE_NOT_CONFIGURED"})
        if payload.requirement_key:
            keys = {
                str(item.get("requirement_key"))
                for profile in ("PYP-FFA", "PYP-INV-SELECT")
                for item in self._effective_requirements(project, profile, content)
            }
            if payload.requirement_key not in keys:
                raise HTTPException(status_code=422, detail={"code": "PERMIT_REQUIREMENT_NOT_APPLICABLE"})

    def _configuration(self, configuration_id: int) -> AdminConfiguration:
        record = self.db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.id == configuration_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "PERMIT_CONFIGURATION_NOT_FOUND"})
        return record

    def _published_configuration(self, workspace: EnterpriseWorkspace) -> AdminConfiguration | None:
        records = list(
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
        if not records:
            return None
        ancestors = self._ancestor_ids(workspace)
        ranked = []
        for record in records:
            scope_id = dict(record.content_json or {}).get("scope_workspace_id")
            rank = (
                len(ancestors) - ancestors.index(scope_id) if scope_id in ancestors else 0 if scope_id is None else -1
            )
            if rank >= 0:
                ranked.append((rank, record.revision, record))
        return max(ranked, default=(0, 0, None), key=lambda item: (item[0], item[1]))[2]

    def _effective_content(self, workspace: EnterpriseWorkspace) -> dict:
        record = self._published_configuration(workspace)
        return deepcopy(record.content_json if record else DEFAULT_CONFIGURATION)

    def _validate_configuration(self, content: dict) -> None:
        issues: list[str] = []
        if content.get("configuration_code") != "PYP-PERMIT-READINESS":
            issues.append("INVALID_CONFIGURATION_CODE")
        if "CAPITAL_OWNER" not in set(content.get("applicable_governance_models", [])):
            issues.append("CAPITAL_OWNER_REQUIRED")
        types = [str(item.get("code")) for item in content.get("permit_types", [])]
        if not types or len(types) != len(set(types)):
            issues.append("INVALID_PERMIT_TYPES")
        type_set = set(types)
        requirement_keys: set[str] = set()
        for item in content.get("requirements", []):
            key = str(item.get("requirement_key") or "")
            if not key or key in requirement_keys:
                issues.append("INVALID_REQUIREMENT_KEY")
            requirement_keys.add(key)
            if item.get("permit_type_code") not in type_set:
                issues.append(f"PERMIT_TYPE_NOT_CONFIGURED:{key}")
            if not item.get("applicable_project_types") or not item.get("applicable_gate_profiles"):
                issues.append(f"APPLICABILITY_REQUIRED:{key}")
        if content.get("condition_policy") not in {
            "ALLOW_NON_BLOCKING_CONDITIONS",
            "BLOCK_ON_ANY_OPEN_CONDITION",
            "BLOCK_ONLY_ON_BLOCKING_CONDITIONS",
        }:
            issues.append("INVALID_CONDITION_POLICY")
        for key in ("evidence_coverage_percent", "class_a_project_coverage_percent"):
            value = float(content.get(key, -1))
            if value < 0 or value > 100:
                issues.append(f"INVALID_COVERAGE:{key}")
        validity = int(content.get("validity_days", 0) or 0)
        if validity < 1 or validity > 3650:
            issues.append("INVALID_VALIDITY_DAYS")
        if issues:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_PERMIT_CONFIGURATION", "issues": sorted(set(issues))},
            )

    def _project(self, project_id: int) -> EnterpriseWorkspace:
        record = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.id == project_id,
                EnterpriseWorkspace.workspace_type_code == "project",
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "PROJECT_WORKSPACE_NOT_FOUND"})
        self._assert_scope(record.id)
        return record

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

    def _portfolio(self, portfolio_id: int) -> EnterpriseWorkspace:
        record = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.id == portfolio_id,
                EnterpriseWorkspace.workspace_type_code == "portfolio",
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "PORTFOLIO_WORKSPACE_NOT_FOUND"})
        self._assert_scope(record.id)
        return record

    def _portfolio_projects(self, portfolio_id: int) -> tuple[list[EnterpriseWorkspace], str]:
        self._portfolio(portfolio_id)
        try:
            contract = (
                PortfolioConvergenceService(self.db, self.tenant_id, self.actor_id, self.context)
                .preparation_contract(portfolio_id)
                .model_dump(mode="json")
            )
            project_ids = [int(item) for item in contract.get("selected_project_set_reference", [])]
            return self._projects(project_ids), str(contract.get("selected_project_set_hash") or _hash(project_ids))
        except HTTPException:
            projects = list(
                self.db.scalars(
                    select(EnterpriseWorkspace).where(
                        EnterpriseWorkspace.tenant_id == self.tenant_id,
                        EnterpriseWorkspace.parent_id == portfolio_id,
                        EnterpriseWorkspace.workspace_type_code == "project",
                    )
                ).all()
            )
            return projects, _hash([item.id for item in projects])

    def _latest_completed(self, project_id: int, gate_profile_code: str) -> PermitReadinessAssessment | None:
        return self.db.scalars(
            select(PermitReadinessAssessment)
            .where(
                PermitReadinessAssessment.tenant_id == self.tenant_id,
                PermitReadinessAssessment.project_workspace_id == project_id,
                PermitReadinessAssessment.gate_profile_code == gate_profile_code,
                PermitReadinessAssessment.status == "COMPLETED",
            )
            .order_by(PermitReadinessAssessment.assessment_version.desc())
        ).first()

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

    def _project_context(self, project: EnterpriseWorkspace) -> dict[str, Any]:
        project_context = dict(dict(project.defaults_json or {}).get("_project", {}))
        enterprise_context = dict(dict(project.defaults_json or {}).get("_enterprise", {}))
        geographies = {
            str(value).upper()
            for value in (
                project_context.get("country_code"),
                project_context.get("region_code"),
                project_context.get("municipality_code"),
                enterprise_context.get("region_code"),
            )
            if value
        }
        return {
            "project_workspace_id": project.id,
            "project_code": project.code,
            "project_name": project.name,
            "project_type": self._project_type(project),
            "governance_model": self._governance_model(project),
            "geographies": sorted(geographies) or ["UNSPECIFIED"],
        }

    def _ancestor_ids(self, workspace: EnterpriseWorkspace) -> list[int]:
        ids = [workspace.id]
        current = workspace
        while current.parent_id is not None:
            current = self.db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id == current.parent_id,
                )
            )
            if current is None or current.id in ids:
                break
            ids.append(current.id)
        return ids

    def _number(self, rule_code: str, prefix: str) -> str:
        sequence = self.db.scalar(
            select(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == rule_code,
                AdminNumberSequence.scope_key == "tenant",
            )
            .with_for_update()
        )
        if sequence is None:
            sequence = AdminNumberSequence(
                tenant_id=self.tenant_id,
                rule_code=rule_code,
                scope_key="tenant",
                next_value=1,
                version=1,
            )
            self.db.add(sequence)
            self.db.flush()
        value = sequence.next_value
        sequence.next_value += 1
        sequence.version += 1
        sequence.updated_at = utc_now()
        return f"{prefix}-{value:05d}"

    def _assert_scope(self, workspace_id: int) -> None:
        if self.context is None or self.context.organization_wide:
            return
        if workspace_id not in self.context.workspace_ids:
            raise HTTPException(status_code=403, detail={"code": "WORKSPACE_OUTSIDE_AUTHORIZED_SCOPE"})

    @staticmethod
    def _check_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise HTTPException(
                status_code=412,
                detail={"code": "ETAG_MISMATCH", "current": actual, "provided": expected},
            )

    def _touch(self, record) -> None:
        record.updated_at = utc_now()
        if hasattr(record, "updated_by"):
            record.updated_by = self.actor_id
        record.revision_version += 1

    def _event(self, event_type: str, target_type: str, target_id: int | None, metadata: dict) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type=target_type,
                target_id=target_id,
                metadata_json=_jsonable(metadata),
            )
        )


def _hash(value: Any) -> str:
    payload = json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
