"""Gate 07J-RISK Project Risk and governed Risk Readiness services.

The module deliberately stops at governed evidence. It does not implement an
enterprise ERM, quantitative risk analysis, an Investment Decision or FID.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, AdminNumberSequence, EnterpriseWorkspace, SecurityEvent
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.portfolio_convergence.service import PortfolioConvergenceService
from app.modules.risk_readiness.models import ProjectRisk, RiskReadinessAssessment
from app.modules.risk_readiness.schemas import (
    AdminPreviewOut,
    InvestmentGateRiskEvidenceOut,
    PortfolioReadinessOut,
    ProjectReadinessOut,
    RefreshPreviewOut,
    RiskReadinessOverviewOut,
)

CONFIGURATION_KIND = "risk_readiness_configuration"
DEFAULT_CODE = "pyp-risk-readiness"
FINAL_OUTPUT = "READY_FOR_GOVERNED_RISK_EVIDENCE"
FINAL_RELEASE_STATUS = "GATE07J_RISK_RELEASE_VALIDATED"
PROVIDER_KEY = "RISK_READINESS_PROVIDER"
SOURCE_MODULE = "RISK_READINESS"
EVIDENCE_TYPE = "RISK_READINESS"

RATING_ORDER = {"LOW": 1, "MODERATE": 2, "HIGH": 3, "CRITICAL": 4}


def _matrix() -> dict[str, str]:
    values: dict[str, str] = {}
    for likelihood in range(1, 6):
        for impact in range(1, 6):
            score = likelihood * impact
            values[f"{likelihood}x{impact}"] = (
                "LOW" if score <= 4 else "MODERATE" if score <= 9 else "HIGH" if score <= 16 else "CRITICAL"
            )
    return values


DEFAULT_CONFIGURATION: dict[str, Any] = {
    "configuration_code": "PYP-RISK-READINESS",
    "applicable_governance_models": ["CAPITAL_OWNER"],
    "risk_categories": [
        "TECHNICAL",
        "SCOPE",
        "SCHEDULE",
        "COST",
        "COMMERCIAL",
        "CONTRACTUAL",
        "PROCUREMENT",
        "CONSTRUCTION",
        "OPERABILITY",
        "ENVIRONMENTAL",
        "SOCIAL",
        "PERMITTING",
        "LAND_ACCESS",
        "FINANCING",
        "MARKET",
        "ORGANIZATIONAL",
        "STAKEHOLDER",
        "HSE",
        "OTHER",
    ],
    "likelihood_scale": [
        {"value": 1, "label": "Rare"},
        {"value": 2, "label": "Unlikely"},
        {"value": 3, "label": "Possible"},
        {"value": 4, "label": "Likely"},
        {"value": 5, "label": "Almost Certain"},
    ],
    "impact_scale": [
        {"value": 1, "label": "Insignificant"},
        {"value": 2, "label": "Minor"},
        {"value": 3, "label": "Moderate"},
        {"value": 4, "label": "Major"},
        {"value": 5, "label": "Severe"},
    ],
    "risk_matrix": _matrix(),
    "rating_bands": ["LOW", "MODERATE", "HIGH", "CRITICAL"],
    "treatment_strategies": ["AVOID", "REDUCE", "TRANSFER", "ACCEPT"],
    "owner_required_threshold": "HIGH",
    "treatment_required_threshold": "HIGH",
    "residual_assessment_threshold": "HIGH",
    "acceptance_threshold": "HIGH",
    "acceptance_authority": {
        "LOW": "NOT_REQUIRED",
        "MODERATE": "PROJECT_MANAGER",
        "HIGH": "SPONSOR_OR_PORTFOLIO_AUTHORITY",
        "CRITICAL": "DESIGNATED_EXECUTIVE_AUTHORITY",
    },
    "overdue_treatment_blocker_ratings": ["HIGH", "CRITICAL"],
    "evidence_coverage_percent": 100.0,
    "validity_days": 90,
    "freshness_flags": [
        "RECOMMENDED_PROJECT_SET",
        "PROJECT_SCOPE_DEFINITION",
        "FEL_ASSESSMENT",
        "RISK_REGISTER",
        "RISK_MATRIX_CONFIGURATION",
        "TREATMENT",
        "RESIDUAL_ASSESSMENT",
        "RISK_ACCEPTANCE",
        "PROJECT_TYPE",
    ],
    "pyp_ffa": {"scope": "PROJECT_SET", "blocking": True, "coverage": 100.0, "validity_days": 90},
    "pyp_inv_select": {"classification": "B", "blocking": False, "validity_days": 90},
    "separation_of_duties": {
        "owner_cannot_accept_high_critical": True,
        "assessment_author_cannot_complete": False,
        "critical_requires_designated_authority": True,
    },
    "inheritance": ["TENANT", "ENTERPRISE", "BUSINESS_UNIT", "PORTFOLIO"],
    "scope_workspace_id": None,
}


class RiskReadinessService:
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
            name="Risk Readiness Configuration",
            description="Starter DRAFT for governed Project and Project Set Risk Readiness.",
            status="draft",
            revision=1,
            version=1,
            content_json=deepcopy(DEFAULT_CONFIGURATION),
            content_hash=_hash(DEFAULT_CONFIGURATION),
            created_by_user_id=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        self._event("risk_readiness.configuration_seeded", "AdminConfiguration", record.id, {"status": "draft"})
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
            "risk_readiness.configuration_cloned",
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
            "risk_readiness.configuration_updated",
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
            "risk_readiness.configuration_published",
            "AdminConfiguration",
            record.id,
            {"revision": record.revision, "hash": record.content_hash},
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    def overview(self) -> RiskReadinessOverviewOut:
        records = self.configurations()
        return RiskReadinessOverviewOut(
            configurations=records,
            allowed_actions=self.allowed_actions(),
            provider={
                "provider_key": PROVIDER_KEY,
                "source_module": SOURCE_MODULE,
                "evidence_type": EVIDENCE_TYPE,
                "status": "AVAILABLE",
                "scopes": ["PORTFOLIO", "PROJECT_SET", "EACH_PROJECT"],
                "validity_days": 90,
            },
            final_output=FINAL_OUTPUT,
            final_release_status=FINAL_RELEASE_STATUS,
            boundaries=[
                "NO_MONTE_CARLO_OR_QRA",
                "NO_PERMIT_PROVIDER",
                "NO_INVESTMENT_DECISION_OR_FID",
                "NO_PROJECT_INITIALIZATION_OR_ACTIVATION",
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
        if portfolio_id and not projects:
            projects, _ = self._portfolio_projects(portfolio_id)
        project_rows = [self._project_readiness(project, content=content) for project in projects]
        portfolio = None
        evidence = None
        if portfolio_id:
            portfolio = self._aggregate(portfolio_id, projects, content=content)
            evidence = self._evidence_from_aggregate(portfolio)
        blockers = sorted({item for row in project_rows for item in row.blockers})
        warnings = sorted({item for row in project_rows for item in row.warnings})
        return AdminPreviewOut(
            configuration={
                "id": record.id,
                "revision": record.revision,
                "status": record.status,
                "hash": _hash(content),
            },
            gate_profile_code=gate_profile_code,
            project_readiness=project_rows,
            portfolio_readiness=portfolio,
            effective_policy=content,
            warnings=warnings,
            blockers=blockers,
            would_be_ready=bool(portfolio and portfolio.readiness_status == "READY"),
            gate07j_evidence_preview=evidence,
            persisted=False,
            can_enter_fid=False,
        )

    # ------------------------------------------------------------------
    # Project Risk register
    # ------------------------------------------------------------------
    def risks(self, project_id: int) -> list[ProjectRisk]:
        self._project(project_id)
        return list(
            self.db.scalars(
                select(ProjectRisk)
                .where(ProjectRisk.tenant_id == self.tenant_id, ProjectRisk.project_workspace_id == project_id)
                .order_by(ProjectRisk.status, ProjectRisk.risk_number)
            ).all()
        )

    def risk(self, risk_id: int) -> ProjectRisk:
        record = self.db.scalar(
            select(ProjectRisk).where(ProjectRisk.tenant_id == self.tenant_id, ProjectRisk.id == risk_id)
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "RISK_NOT_FOUND"})
        self._assert_scope(record.project_workspace_id)
        return record

    def create_risk(self, project_id: int, payload) -> ProjectRisk:
        project = self._project(project_id)
        existing = self.db.scalar(
            select(ProjectRisk).where(
                ProjectRisk.tenant_id == self.tenant_id,
                ProjectRisk.create_idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return existing
        content = self._effective_content(project)
        category = payload.risk_category.strip().upper()
        if category not in set(content["risk_categories"]):
            raise HTTPException(status_code=422, detail={"code": "RISK_CATEGORY_NOT_CONFIGURED"})
        record = ProjectRisk(
            tenant_id=self.tenant_id,
            project_workspace_id=project_id,
            risk_number=self._number("RISK", "RSK"),
            status="OPEN",
            create_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
            **self._risk_values(payload, content),
        )
        self.db.add(record)
        self.db.flush()
        self._event("risk.created", "ProjectRisk", record.id, {"project_workspace_id": project_id})
        self.db.commit()
        self.db.refresh(record)
        return record

    def update_risk(self, risk_id: int, expected_version: int, payload) -> ProjectRisk:
        record = self.risk(risk_id)
        self._check_version(record.revision_version, expected_version)
        if record.status in {"CLOSED", "VOIDED"}:
            raise HTTPException(status_code=409, detail={"code": "CLOSED_OR_VOIDED_RISK_IS_IMMUTABLE"})
        content = self._effective_content(self._project(record.project_workspace_id))
        category = payload.risk_category.strip().upper()
        if category not in set(content["risk_categories"]):
            raise HTTPException(status_code=422, detail={"code": "RISK_CATEGORY_NOT_CONFIGURED"})
        previous_treatment = {
            "description": record.treatment_description,
            "status": record.treatment_status,
            "residual_rating": record.residual_rating,
        }
        for key, value in self._risk_values(payload, content).items():
            setattr(record, key, value)
        self._touch(record)
        self._event("risk.updated", "ProjectRisk", record.id, {"revision_version": record.revision_version})
        treatment_changed = previous_treatment["description"] != record.treatment_description
        treatment_status_changed = previous_treatment["status"] != record.treatment_status
        if treatment_changed:
            self._event(
                "risk.treatment_created" if not previous_treatment["description"] else "risk.treatment_updated",
                "ProjectRisk",
                record.id,
                {"treatment_status": record.treatment_status},
            )
        if treatment_status_changed and record.treatment_status == "COMPLETED":
            self._event("risk.treatment_completed", "ProjectRisk", record.id, {})
        if previous_treatment["residual_rating"] != record.residual_rating:
            self._event(
                "risk.residual_assessed",
                "ProjectRisk",
                record.id,
                {"residual_rating": record.residual_rating},
            )
        self.db.commit()
        self.db.refresh(record)
        return record

    def change_status(self, risk_id: int, expected_version: int, status: str) -> ProjectRisk:
        record = self.risk(risk_id)
        self._check_version(record.revision_version, expected_version)
        transitions = {
            "DRAFT": {"OPEN", "VOIDED"},
            "OPEN": {"UNDER_TREATMENT", "MONITORING", "CLOSED", "VOIDED"},
            "UNDER_TREATMENT": {"MONITORING", "CLOSED", "VOIDED"},
            "MONITORING": {"UNDER_TREATMENT", "CLOSED", "VOIDED"},
            "CLOSED": set(),
            "VOIDED": set(),
        }
        if status not in transitions.get(record.status, set()):
            raise HTTPException(status_code=409, detail={"code": "INVALID_RISK_STATUS_TRANSITION"})
        previous = record.status
        record.status = status
        self._touch(record)
        self._event("risk.status_changed", "ProjectRisk", record.id, {"from": previous, "to": status})
        self.db.commit()
        self.db.refresh(record)
        return record

    def accept_residual(self, risk_id: int, expected_version: int, payload) -> ProjectRisk:
        record = self.risk(risk_id)
        self._check_version(record.revision_version, expected_version)
        existing = self.db.scalar(
            select(ProjectRisk).where(
                ProjectRisk.tenant_id == self.tenant_id,
                ProjectRisk.acceptance_idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return existing
        rating = str(record.residual_rating or "")
        if not record.residual_acceptance_required and not self._at_or_above(rating, "HIGH"):
            raise HTTPException(status_code=409, detail={"code": "RESIDUAL_ACCEPTANCE_NOT_REQUIRED"})
        content = self._effective_content(self._project(record.project_workspace_id))
        sod = dict(content.get("separation_of_duties", {}))
        if (
            sod.get("owner_cannot_accept_high_critical", True)
            and rating in {"HIGH", "CRITICAL"}
            and record.risk_owner_id == self.actor_id
        ):
            raise HTTPException(status_code=409, detail={"code": "RISK_OWNER_CANNOT_ACCEPT_OWN_RESIDUAL"})
        expected = str(dict(content.get("acceptance_authority", {})).get(rating, ""))
        if rating == "CRITICAL" and sod.get("critical_requires_designated_authority", True):
            if payload.acceptance_authority_level != expected:
                raise HTTPException(status_code=403, detail={"code": "CRITICAL_ACCEPTANCE_AUTHORITY_REQUIRED"})
        record.accepted_by = self.actor_id
        record.accepted_at = utc_now()
        record.acceptance_comment = payload.acceptance_comment.strip()
        record.acceptance_authority_level = payload.acceptance_authority_level.strip()
        record.acceptance_idempotency_key = payload.idempotency_key
        self._touch(record)
        self._event(
            "risk.accepted",
            "ProjectRisk",
            record.id,
            {"residual_rating": rating, "authority": record.acceptance_authority_level},
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    # ------------------------------------------------------------------
    # Assessment lifecycle and readiness
    # ------------------------------------------------------------------
    def assessments(self, project_id: int) -> list[RiskReadinessAssessment]:
        self._project(project_id)
        return list(
            self.db.scalars(
                select(RiskReadinessAssessment)
                .where(
                    RiskReadinessAssessment.tenant_id == self.tenant_id,
                    RiskReadinessAssessment.project_workspace_id == project_id,
                )
                .order_by(RiskReadinessAssessment.assessment_version.desc())
            ).all()
        )

    def assessment(self, assessment_id: int) -> RiskReadinessAssessment:
        record = self.db.scalar(
            select(RiskReadinessAssessment).where(
                RiskReadinessAssessment.tenant_id == self.tenant_id,
                RiskReadinessAssessment.id == assessment_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "RISK_READINESS_ASSESSMENT_NOT_FOUND"})
        self._assert_scope(record.project_workspace_id)
        return record

    def create_assessment(self, project_id: int, payload) -> RiskReadinessAssessment:
        project = self._project(project_id)
        existing_key = self.db.scalar(
            select(RiskReadinessAssessment).where(
                RiskReadinessAssessment.tenant_id == self.tenant_id,
                RiskReadinessAssessment.create_idempotency_key == payload.idempotency_key,
            )
        )
        if existing_key:
            return existing_key
        active = self.db.scalar(
            select(RiskReadinessAssessment).where(
                RiskReadinessAssessment.tenant_id == self.tenant_id,
                RiskReadinessAssessment.project_workspace_id == project_id,
                RiskReadinessAssessment.status.in_(["DRAFT", "IN_PROGRESS"]),
            )
        )
        if active:
            return active
        configuration = self._published_configuration(project)
        if configuration is None:
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_RISK_CONFIGURATION_REQUIRED"})
        version = (
            int(
                self.db.scalar(
                    select(func.max(RiskReadinessAssessment.assessment_version)).where(
                        RiskReadinessAssessment.tenant_id == self.tenant_id,
                        RiskReadinessAssessment.project_workspace_id == project_id,
                    )
                )
                or 0
            )
            + 1
        )
        as_of = payload.as_of_date or utc_now()
        computed = self._compute(project_id, configuration.content_json, as_of)
        record = RiskReadinessAssessment(
            tenant_id=self.tenant_id,
            project_workspace_id=project_id,
            assessment_number=self._number("RISK_READINESS_ASSESSMENT", "RRA"),
            assessment_version=version,
            as_of_date=as_of,
            valid_until=as_of + timedelta(days=int(configuration.content_json.get("validity_days", 90))),
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
            "risk_readiness.assessment_created",
            "RiskReadinessAssessment",
            record.id,
            {"project_workspace_id": project_id, "version": version},
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    def update_assessment(self, assessment_id: int, expected_version: int, payload) -> RiskReadinessAssessment:
        record = self.assessment(assessment_id)
        self._check_version(record.revision_version, expected_version)
        if record.status not in {"DRAFT", "IN_PROGRESS"}:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_IS_IMMUTABLE"})
        configuration = self._configuration(record.configuration_id)
        computed = self._compute(record.project_workspace_id, configuration.content_json, payload.as_of_date)
        record.as_of_date = payload.as_of_date
        record.valid_until = payload.as_of_date + timedelta(
            days=int(configuration.content_json.get("validity_days", 90))
        )
        self._apply_computed(record, computed)
        self._touch(record)
        self._event("risk_readiness.assessment_updated", "RiskReadinessAssessment", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def complete_assessment(self, assessment_id: int, expected_version: int, payload) -> RiskReadinessAssessment:
        record = self.assessment(assessment_id)
        self._check_version(record.revision_version, expected_version)
        if record.complete_idempotency_key == payload.idempotency_key:
            return record
        if record.status not in {"DRAFT", "IN_PROGRESS"}:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_IS_IMMUTABLE"})
        configuration = self._configuration(record.configuration_id)
        current = self._published_configuration(self._project(record.project_workspace_id))
        if current is None or current.content_hash != record.configuration_hash:
            raise HTTPException(
                status_code=412, detail={"code": "STALE_RISK_SOURCE", "reason": "CONFIGURATION_CHANGED"}
            )
        computed = self._compute(record.project_workspace_id, configuration.content_json, utc_now())
        if computed["risk_register_hash"] != record.risk_register_hash:
            raise HTTPException(
                status_code=412, detail={"code": "STALE_RISK_SOURCE", "reason": "RISK_REGISTER_CHANGED"}
            )
        if computed["blockers"]:
            raise HTTPException(
                status_code=409,
                detail={"code": "RISK_READINESS_BLOCKED", "blockers": computed["blockers"]},
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
        record.risk_readiness_hash = self._readiness_hash(record, computed)
        self._touch(record)
        self._event(
            "risk_readiness.assessment_completed",
            "RiskReadinessAssessment",
            record.id,
            {"risk_readiness_hash": record.risk_readiness_hash},
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    def reassess(self, assessment_id: int, payload) -> RiskReadinessAssessment:
        source = self.assessment(assessment_id)
        existing = self.db.scalar(
            select(RiskReadinessAssessment).where(
                RiskReadinessAssessment.tenant_id == self.tenant_id,
                RiskReadinessAssessment.reassessment_idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return existing
        if source.status != "COMPLETED":
            raise HTTPException(status_code=409, detail={"code": "ONLY_COMPLETED_ASSESSMENT_CAN_REASSESS"})
        created = self.create_assessment(
            source.project_workspace_id,
            type("ReassessmentPayload", (), {"as_of_date": utc_now(), "idempotency_key": payload.idempotency_key})(),
        )
        created.reassessment_idempotency_key = payload.idempotency_key
        created.create_idempotency_key = None
        self._event(
            "risk_readiness.assessment_reassessed",
            "RiskReadinessAssessment",
            created.id,
            {"source_assessment_id": source.id},
        )
        self.db.commit()
        self.db.refresh(created)
        return created

    def refresh_preview(self, project_id: int) -> RefreshPreviewOut:
        project = self._project(project_id)
        content = self._effective_content(project)
        computed = self._compute(project_id, content, utc_now())
        latest = self._latest_completed(project_id)
        previous = self._project_readiness(project, content=content)
        return RefreshPreviewOut(
            project_workspace_id=project_id,
            assessment_id=latest.id if latest else None,
            previous_source_hash=latest.risk_register_hash if latest else None,
            current_source_hash=computed["risk_register_hash"],
            changes={
                "source_hash_changed": bool(latest and latest.risk_register_hash != computed["risk_register_hash"]),
                "active_risk_delta": computed["total_active_risks"] - (latest.total_active_risks if latest else 0),
                "high_risk_delta": computed["high_risk_count"] - (latest.high_risk_count if latest else 0),
                "critical_risk_delta": computed["critical_risk_count"] - (latest.critical_risk_count if latest else 0),
                "owner_gap_delta": computed["risks_without_owner"] - (latest.risks_without_owner if latest else 0),
                "treatment_gap_delta": computed["risks_without_treatment"]
                - (latest.risks_without_treatment if latest else 0),
                "acceptance_gap_delta": computed["risks_without_acceptance"]
                - (latest.risks_without_acceptance if latest else 0),
            },
            previous_readiness=previous.readiness_status if latest else None,
            current_readiness=computed["readiness_status"],
            warnings=computed["warnings"],
            blockers=computed["blockers"],
            persisted=False,
        )

    def refresh_apply(self, project_id: int, expected_version: int, payload) -> RiskReadinessAssessment:
        active = self.db.scalar(
            select(RiskReadinessAssessment).where(
                RiskReadinessAssessment.tenant_id == self.tenant_id,
                RiskReadinessAssessment.project_workspace_id == project_id,
                RiskReadinessAssessment.status.in_(["DRAFT", "IN_PROGRESS"]),
            )
        )
        if active is None:
            latest = self._latest_completed(project_id)
            if latest is None:
                raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_NOT_FOUND"})
            return self.reassess(latest.id, payload)
        self._check_version(active.revision_version, expected_version)
        if active.refresh_idempotency_key == payload.idempotency_key:
            return active
        configuration = self._configuration(active.configuration_id)
        computed = self._compute(project_id, configuration.content_json, utc_now())
        self._apply_computed(active, computed)
        active.refresh_idempotency_key = payload.idempotency_key
        self._touch(active)
        self._event("risk_readiness.refresh_applied", "RiskReadinessAssessment", active.id, {})
        self.db.commit()
        self.db.refresh(active)
        return active

    def project_readiness(self, project_id: int) -> ProjectReadinessOut:
        project = self._project(project_id)
        return self._project_readiness(project)

    def portfolio_readiness(self, portfolio_id: int) -> PortfolioReadinessOut:
        projects, project_set_hash = self._portfolio_projects(portfolio_id)
        return self._aggregate(portfolio_id, projects, project_set_hash=project_set_hash)

    def portfolio_projects(self, portfolio_id: int) -> list[ProjectReadinessOut]:
        projects, _ = self._portfolio_projects(portfolio_id)
        return [self._project_readiness(project) for project in projects]

    def investment_gate_evidence(self, portfolio_id: int) -> InvestmentGateRiskEvidenceOut:
        return self._evidence_from_aggregate(self.portfolio_readiness(portfolio_id))

    # ------------------------------------------------------------------
    # Calculation helpers
    # ------------------------------------------------------------------
    def _project_readiness(
        self,
        project: EnterpriseWorkspace,
        *,
        content: dict | None = None,
    ) -> ProjectReadinessOut:
        content = content or self._effective_content(project)
        latest = self._latest_completed(project.id)
        if latest is None:
            computed = self._compute(project.id, content, utc_now())
            return ProjectReadinessOut(
                project_workspace_id=project.id,
                assessment_id=None,
                assessment_hash=None,
                as_of_date=None,
                valid_until=None,
                active_risk_count=computed["total_active_risks"],
                high_count=computed["high_risk_count"],
                critical_count=computed["critical_risk_count"],
                unowned_high_critical_count=computed["risks_without_owner"],
                untreated_high_critical_count=computed["risks_without_treatment"],
                overdue_treatment_count=computed["overdue_treatments"],
                unaccepted_residual_count=computed["risks_without_acceptance"],
                evidence_coverage=computed["evidence_coverage_percent"],
                warnings=computed["warnings"],
                blockers=sorted(set(computed["blockers"] + ["RISK_READINESS_ASSESSMENT_REQUIRED"])),
                readiness_status="NOT_STARTED",
                risk_readiness_hash=None,
                source_current=False,
                allowed_actions=self.allowed_actions(),
            )
        current_config = self._published_configuration(project)
        current_hash = self._risk_source_hash(project.id, content)
        source_current = bool(
            current_config
            and current_config.content_hash == latest.configuration_hash
            and current_hash == latest.risk_register_hash
        )
        status = latest.readiness_status
        blockers = list(latest.blockers_json or [])
        warnings = list(latest.warnings_json or [])
        now = utc_now()
        if not source_current:
            status = "STALE"
            blockers = sorted(set(blockers + ["STALE_RISK_SOURCE"]))
        elif now > latest.valid_until:
            status = "EXPIRED"
            blockers = sorted(set(blockers + ["RISK_READINESS_EXPIRED"]))
        return ProjectReadinessOut(
            project_workspace_id=project.id,
            assessment_id=latest.id,
            assessment_hash=latest.risk_readiness_hash,
            as_of_date=latest.as_of_date,
            valid_until=latest.valid_until,
            active_risk_count=latest.total_active_risks,
            high_count=latest.high_risk_count,
            critical_count=latest.critical_risk_count,
            unowned_high_critical_count=latest.risks_without_owner,
            untreated_high_critical_count=latest.risks_without_treatment,
            overdue_treatment_count=latest.overdue_treatments,
            unaccepted_residual_count=latest.risks_without_acceptance,
            evidence_coverage=latest.evidence_coverage_percent,
            warnings=warnings,
            blockers=blockers,
            readiness_status=status,
            risk_readiness_hash=latest.risk_readiness_hash,
            source_current=source_current and status not in {"EXPIRED", "STALE"},
            allowed_actions=self.allowed_actions(),
        )

    def _aggregate(
        self,
        portfolio_id: int,
        projects: list[EnterpriseWorkspace],
        *,
        content: dict | None = None,
        project_set_hash: str | None = None,
    ) -> PortfolioReadinessOut:
        self._portfolio(portfolio_id)
        rows = [self._project_readiness(project, content=content) for project in projects]
        required = len(projects)
        valid = sum(item.readiness_status == "READY" and item.source_current for item in rows)
        blocked = sum(item.readiness_status in {"BLOCKED", "NOT_STARTED"} for item in rows)
        stale = sum(item.readiness_status == "STALE" for item in rows)
        expired = sum(item.readiness_status == "EXPIRED" for item in rows)
        coverage = round(valid / required * 100, 2) if required else 0.0
        blockers = sorted({item for row in rows for item in row.blockers})
        if required == 0:
            blockers = sorted(set(blockers + ["RECOMMENDED_PROJECT_SET_REQUIRED"]))
        if coverage < 100:
            blockers = sorted(set(blockers + ["RISK_READINESS_COVERAGE_BELOW_100"]))
        warnings = sorted({item for row in rows for item in row.warnings})
        set_hash = project_set_hash or _hash([project.id for project in projects])
        readiness_hash = _hash(
            {
                "portfolio": portfolio_id,
                "project_set_hash": set_hash,
                "projects": [
                    {
                        "id": row.project_workspace_id,
                        "status": row.readiness_status,
                        "hash": row.risk_readiness_hash,
                        "current": row.source_current,
                    }
                    for row in rows
                ],
                "coverage": coverage,
                "blockers": blockers,
            }
        )
        return PortfolioReadinessOut(
            portfolio_workspace_id=portfolio_id,
            recommended_project_set_hash=set_hash,
            required_project_count=required,
            valid_project_count=valid,
            blocked_project_count=blocked,
            stale_project_count=stale,
            expired_project_count=expired,
            coverage_percent=coverage,
            aggregate_high_count=sum(item.high_count for item in rows),
            aggregate_critical_count=sum(item.critical_count for item in rows),
            aggregate_unaccepted_residual_count=sum(item.unaccepted_residual_count for item in rows),
            warnings=warnings,
            blockers=blockers,
            readiness_status="READY" if required > 0 and coverage == 100 and not blockers else "BLOCKED",
            risk_readiness_hash=readiness_hash,
            project_readiness=rows,
        )

    def _evidence_from_aggregate(self, aggregate: PortfolioReadinessOut) -> InvestmentGateRiskEvidenceOut:
        dates = [item.as_of_date for item in aggregate.project_readiness if item.as_of_date]
        validities = [item.valid_until for item in aggregate.project_readiness if item.valid_until]
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
                    for item in aggregate.project_readiness
                ],
            }
        )
        current = all(item.source_current for item in aggregate.project_readiness) and bool(aggregate.project_readiness)
        can_supply = (
            aggregate.readiness_status == "READY"
            and current
            and aggregate.coverage_percent == 100
            and not aggregate.blockers
        )
        return InvestmentGateRiskEvidenceOut(
            final_output=FINAL_OUTPUT,
            provider_key=PROVIDER_KEY,
            source_module=SOURCE_MODULE,
            evidence_type=EVIDENCE_TYPE,
            scope="PROJECT_SET",
            portfolio_workspace_id=aggregate.portfolio_workspace_id,
            project_workspace_id=None,
            recommended_project_set_hash=aggregate.recommended_project_set_hash,
            assessment_id=None,
            aggregate_reference=f"RISK-READINESS:{aggregate.risk_readiness_hash}",
            assessment_date=max(dates) if dates else None,
            valid_until=min(validities) if validities else None,
            risk_source_hash=source_hash,
            risk_readiness_hash=aggregate.risk_readiness_hash,
            required_project_count=aggregate.required_project_count,
            valid_project_count=aggregate.valid_project_count,
            coverage_percent=aggregate.coverage_percent,
            active_risk_count=sum(item.active_risk_count for item in aggregate.project_readiness),
            high_risk_count=aggregate.aggregate_high_count,
            critical_risk_count=aggregate.aggregate_critical_count,
            unowned_high_critical_count=sum(item.unowned_high_critical_count for item in aggregate.project_readiness),
            untreated_high_critical_count=sum(
                item.untreated_high_critical_count for item in aggregate.project_readiness
            ),
            overdue_treatment_count=sum(item.overdue_treatment_count for item in aggregate.project_readiness),
            unaccepted_residual_count=aggregate.aggregate_unaccepted_residual_count,
            warnings=aggregate.warnings,
            blockers=aggregate.blockers,
            readiness_status=aggregate.readiness_status,
            source_current=current,
            can_supply_investment_gate_evidence=can_supply,
            can_enter_fid=False,
            project_source_references=[
                {
                    "project_workspace_id": item.project_workspace_id,
                    "assessment_id": item.assessment_id,
                    "assessment_hash": item.assessment_hash,
                    "risk_readiness_hash": item.risk_readiness_hash,
                    "source_current": item.source_current,
                    "readiness_status": item.readiness_status,
                }
                for item in aggregate.project_readiness
            ],
        )

    def _compute(self, project_id: int, content: dict, as_of: datetime) -> dict[str, Any]:
        risks = [item for item in self.risks(project_id) if item.status not in {"CLOSED", "VOIDED"}]
        owner_threshold = str(content.get("owner_required_threshold", "HIGH"))
        treatment_threshold = str(content.get("treatment_required_threshold", "HIGH"))
        residual_threshold = str(content.get("residual_assessment_threshold", "HIGH"))
        acceptance_threshold = str(content.get("acceptance_threshold", "HIGH"))
        overdue_ratings = set(content.get("overdue_treatment_blocker_ratings", ["HIGH", "CRITICAL"]))
        warnings: list[str] = []
        blockers: list[str] = []
        if not risks:
            blockers.append("RISK_REGISTER_REQUIRED")
        high = sum(item.inherent_rating == "HIGH" for item in risks)
        critical = sum(item.inherent_rating == "CRITICAL" for item in risks)
        unowned = 0
        untreated = 0
        overdue = 0
        residual_high = 0
        residual_critical = 0
        requiring_acceptance = 0
        without_acceptance = 0
        covered = 0
        for risk in risks:
            if risk.inherent_rating is None:
                blockers.append(f"RISK_NOT_EVALUATED:{risk.risk_number}")
            if self._at_or_above(risk.inherent_rating, owner_threshold) and risk.risk_owner_id is None:
                unowned += 1
                blockers.append(f"HIGH_CRITICAL_OWNER_REQUIRED:{risk.risk_number}")
            treatment_required = risk.treatment_required or self._at_or_above(risk.inherent_rating, treatment_threshold)
            has_treatment = bool(
                risk.treatment_strategy
                and risk.treatment_description
                and risk.treatment_owner_id
                and risk.target_treatment_date
            )
            if treatment_required and not has_treatment:
                untreated += 1
                blockers.append(f"TREATMENT_REQUIRED:{risk.risk_number}")
            if (
                has_treatment
                and risk.inherent_rating in overdue_ratings
                and risk.target_treatment_date
                and risk.target_treatment_date < as_of.date()
                and risk.treatment_status not in {"COMPLETED", "CANCELLED"}
            ):
                overdue += 1
                blockers.append(f"OVERDUE_TREATMENT:{risk.risk_number}")
            if self._at_or_above(risk.inherent_rating, residual_threshold) and risk.residual_rating is None:
                blockers.append(f"RESIDUAL_ASSESSMENT_REQUIRED:{risk.risk_number}")
            residual_high += risk.residual_rating == "HIGH"
            residual_critical += risk.residual_rating == "CRITICAL"
            acceptance_required = risk.residual_acceptance_required or self._at_or_above(
                risk.residual_rating, acceptance_threshold
            )
            if acceptance_required:
                requiring_acceptance += 1
                if risk.accepted_by is None or risk.accepted_at is None:
                    without_acceptance += 1
                    blockers.append(f"RESIDUAL_ACCEPTANCE_REQUIRED:{risk.risk_number}")
            if risk.evidence_refs_json:
                covered += 1
            if risk.inherent_rating in {"HIGH", "CRITICAL"}:
                warnings.append(f"ACTIVE_{risk.inherent_rating}_RISK:{risk.risk_number}")
        coverage = round(covered / len(risks) * 100, 2) if risks else 0.0
        minimum = float(content.get("evidence_coverage_percent", 100))
        if coverage < minimum:
            blockers.append("RISK_EVIDENCE_COVERAGE_BELOW_THRESHOLD")
        blockers = sorted(set(blockers))
        return {
            "risk_register_hash": self._risk_source_hash(project_id, content),
            "total_active_risks": len(risks),
            "high_risk_count": high,
            "critical_risk_count": critical,
            "risks_without_owner": unowned,
            "risks_without_treatment": untreated,
            "overdue_treatments": overdue,
            "residual_high_count": residual_high,
            "residual_critical_count": residual_critical,
            "risks_requiring_acceptance": requiring_acceptance,
            "risks_without_acceptance": without_acceptance,
            "evidence_coverage_percent": coverage,
            "warnings": sorted(set(warnings)),
            "blockers": blockers,
            "readiness_status": "READY" if not blockers else "BLOCKED",
        }

    def _risk_source_hash(self, project_id: int, content: dict) -> str:
        project = self._project(project_id)
        risks = self.risks(project_id)
        project_context = dict(dict(project.defaults_json or {}).get("_project", {}))
        return _hash(
            {
                "project": {
                    "id": project.id,
                    "code": project.code,
                    "type": project_context.get("project_type"),
                    "governance": project_context.get("governance_model", "CAPITAL_OWNER"),
                    "version": project.version,
                },
                "configuration_hash": _hash(content),
                "risks": [self._risk_hash_payload(item) for item in risks],
            }
        )

    @staticmethod
    def _risk_hash_payload(record: ProjectRisk) -> dict:
        return {
            "id": record.id,
            "number": record.risk_number,
            "status": record.status,
            "category": record.risk_category,
            "owner": record.risk_owner_id,
            "inherent": [record.likelihood_before, record.impact_before, record.inherent_rating],
            "treatment": [
                record.treatment_required,
                record.treatment_strategy,
                record.treatment_description,
                record.treatment_owner_id,
                record.target_treatment_date,
                record.treatment_status,
            ],
            "residual": [record.likelihood_after, record.impact_after, record.residual_rating],
            "acceptance": [
                record.residual_acceptance_required,
                record.accepted_by,
                record.accepted_at,
                record.acceptance_authority_level,
            ],
            "evidence": record.evidence_refs_json,
            "revision": record.revision_version,
        }

    @staticmethod
    def _computed_values(computed: dict) -> dict:
        return {
            "risk_register_hash": computed["risk_register_hash"],
            "total_active_risks": computed["total_active_risks"],
            "high_risk_count": computed["high_risk_count"],
            "critical_risk_count": computed["critical_risk_count"],
            "risks_without_owner": computed["risks_without_owner"],
            "risks_without_treatment": computed["risks_without_treatment"],
            "overdue_treatments": computed["overdue_treatments"],
            "residual_high_count": computed["residual_high_count"],
            "residual_critical_count": computed["residual_critical_count"],
            "risks_requiring_acceptance": computed["risks_requiring_acceptance"],
            "risks_without_acceptance": computed["risks_without_acceptance"],
            "evidence_coverage_percent": computed["evidence_coverage_percent"],
            "warnings_json": computed["warnings"],
            "blockers_json": computed["blockers"],
            "readiness_status": computed["readiness_status"],
        }

    def _apply_computed(self, record: RiskReadinessAssessment, computed: dict) -> None:
        for key, value in self._computed_values(computed).items():
            setattr(record, key, value)

    def _readiness_hash(self, record: RiskReadinessAssessment, computed: dict) -> str:
        return _hash(
            {
                "assessment": [record.assessment_number, record.assessment_version, record.as_of_date],
                "source_hash": computed["risk_register_hash"],
                "configuration": [record.configuration_revision, record.configuration_hash],
                "counts": {
                    key: value for key, value in computed.items() if key.endswith("count") or key.startswith("risks_")
                },
                "coverage": computed["evidence_coverage_percent"],
                "warnings": computed["warnings"],
                "blockers": computed["blockers"],
                "readiness": computed["readiness_status"],
            }
        )

    def _risk_values(self, payload, content: dict) -> dict[str, Any]:
        inherent = self._rating(payload.likelihood_before, payload.impact_before, content)
        residual = self._rating(payload.likelihood_after, payload.impact_after, content)
        return {
            "title": payload.title.strip(),
            "description": payload.description.strip(),
            "risk_category": payload.risk_category.strip().upper(),
            "identified_date": payload.identified_date,
            "risk_owner_id": payload.risk_owner_id,
            "cause": payload.cause.strip(),
            "event": payload.event.strip(),
            "impact_description": payload.impact_description.strip(),
            "likelihood_before": payload.likelihood_before,
            "impact_before": payload.impact_before,
            "inherent_rating": inherent,
            "treatment_required": bool(payload.treatment_required),
            "treatment_strategy": payload.treatment_strategy,
            "treatment_description": payload.treatment_description.strip() if payload.treatment_description else None,
            "treatment_owner_id": payload.treatment_owner_id,
            "target_treatment_date": payload.target_treatment_date,
            "treatment_status": payload.treatment_status,
            "likelihood_after": payload.likelihood_after,
            "impact_after": payload.impact_after,
            "residual_rating": residual,
            "residual_acceptance_required": bool(payload.residual_acceptance_required),
            "due_date": payload.due_date,
            "source_reference": payload.source_reference.strip() if payload.source_reference else None,
            "evidence_refs_json": deepcopy(payload.evidence_refs),
        }

    @staticmethod
    def _rating(likelihood: int | None, impact: int | None, content: dict) -> str | None:
        if likelihood is None or impact is None:
            return None
        value = dict(content.get("risk_matrix", {})).get(f"{likelihood}x{impact}")
        if value not in RATING_ORDER:
            raise HTTPException(status_code=422, detail={"code": "RISK_MATRIX_CELL_NOT_CONFIGURED"})
        return str(value)

    @staticmethod
    def _at_or_above(value: str | None, threshold: str) -> bool:
        return RATING_ORDER.get(str(value or ""), 0) >= RATING_ORDER.get(str(threshold), 99)

    # ------------------------------------------------------------------
    # Shared repository patterns
    # ------------------------------------------------------------------
    def allowed_actions(self) -> dict[str, bool]:
        roles = set(self.context.role_codes if self.context else {"organization_admin"})
        admin = bool(roles & {"organization_admin", "risk_configuration_admin"})
        manager = bool(roles & {"organization_admin", "risk_manager"})
        owner = bool(roles & {"organization_admin", "risk_manager", "risk_owner"})
        assessor = bool(roles & {"organization_admin", "risk_manager", "risk_assessor"})
        reviewer = bool(roles & {"organization_admin", "risk_manager", "risk_reviewer"})
        authority = bool(roles & {"organization_admin", "risk_acceptance_authority"})
        viewer = bool(roles)
        return {
            "can_view_risks": viewer,
            "can_create_risk": manager,
            "can_edit_risk": owner,
            "can_change_risk_status": manager,
            "can_manage_treatment": owner,
            "can_assess_residual_risk": assessor,
            "can_accept_residual_risk": authority,
            "can_start_risk_readiness_assessment": assessor,
            "can_edit_risk_readiness_assessment": assessor,
            "can_complete_risk_readiness_assessment": reviewer,
            "can_start_risk_reassessment": assessor,
            "can_refresh_risk_readiness": assessor,
            "can_view_gate07j_risk_evidence": viewer,
            "can_admin_configure": admin,
            "can_admin_publish": admin,
            "can_enter_fid": False,
        }

    def _configuration(self, configuration_id: int) -> AdminConfiguration:
        record = self.db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.id == configuration_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "RISK_CONFIGURATION_NOT_FOUND"})
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
        if content.get("configuration_code") != "PYP-RISK-READINESS":
            issues.append("INVALID_CONFIGURATION_CODE")
        if "CAPITAL_OWNER" not in set(content.get("applicable_governance_models", [])):
            issues.append("CAPITAL_OWNER_REQUIRED")
        if not set(content.get("rating_bands", [])) == set(RATING_ORDER):
            issues.append("INVALID_RATING_BANDS")
        matrix = dict(content.get("risk_matrix", {}))
        if len(matrix) != 25 or not set(matrix.values()).issubset(RATING_ORDER):
            issues.append("INVALID_RISK_MATRIX")
        for key in (
            "owner_required_threshold",
            "treatment_required_threshold",
            "residual_assessment_threshold",
            "acceptance_threshold",
        ):
            if content.get(key) not in RATING_ORDER:
                issues.append(f"INVALID_THRESHOLD:{key}")
        validity = int(content.get("validity_days", 0) or 0)
        if validity < 1 or validity > 3650:
            issues.append("INVALID_VALIDITY_DAYS")
        coverage = float(content.get("evidence_coverage_percent", -1))
        if coverage < 0 or coverage > 100:
            issues.append("INVALID_EVIDENCE_COVERAGE")
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_RISK_CONFIGURATION", "issues": issues})

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

    def _latest_completed(self, project_id: int) -> RiskReadinessAssessment | None:
        return self.db.scalars(
            select(RiskReadinessAssessment)
            .where(
                RiskReadinessAssessment.tenant_id == self.tenant_id,
                RiskReadinessAssessment.project_workspace_id == project_id,
                RiskReadinessAssessment.status == "COMPLETED",
            )
            .order_by(RiskReadinessAssessment.assessment_version.desc())
        ).first()

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
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
