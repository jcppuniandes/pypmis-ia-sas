"""Governed Project Definition / FEL service.

This capability produces project-definition evidence. It deliberately does not
approve investments, authorize FID, manage funding, activate projects, or
create operational schedule/cost controls.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent
from app.domain.schemas import AdminConfigurationOut
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.project_definition.models import (
    ProjectDefinitionAction,
    ProjectDefinitionAssessment,
    ProjectFELStatus,
)
from app.modules.project_definition.schemas import (
    ActionCreateIn,
    ActionUpdateIn,
    AssessmentCreateIn,
    AssessmentOut,
    AssessmentUpdateIn,
    ConfigurationPreviewOut,
    DefinitionActionOut,
    DefinitionOverviewOut,
    DefinitionReadinessOut,
    InvestmentGateEvidenceOut,
    ProjectFELStatusOut,
    StartFELIn,
)

CONFIGURATION_KIND = "project_definition_framework"
FRAMEWORK_TYPES = {"CUSTOM", "PDRI_COMPATIBLE", "FEL_INDEX_COMPATIBLE"}
SCORING_METHODS = {"NONE", "WEIGHTED_SCORE", "POINTS", "MATURITY_LEVEL", "CUSTOM_CONFIGURED"}
ACTION_BLOCKING_STATUSES = {"OPEN", "IN_PROGRESS"}

DEFAULT_FRAMEWORK: dict[str, Any] = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "framework_code": "PYP-CUSTOM-DEFINITION",
    "framework_name": "P&Pmis Custom Project Definition",
    "framework_type": "CUSTOM",
    "framework_version": "1.0",
    "description": "Non-proprietary starter metadata for governed Project Definition and FEL evidence.",
    "applicable_project_types": ["*"],
    "applicable_governance_models": ["CAPITAL_OWNER"],
    "stage_structure": [
        {
            "stage_code": "FEL-1",
            "stage_name": "Business Case / Basic Feasibility",
            "sequence": 1,
            "minimum_maturity": "DEVELOPING",
            "threshold": 40,
            "required_assessment": True,
            "required_evidence": ["business-case-reference"],
        },
        {
            "stage_code": "FEL-2",
            "stage_name": "Scope Selection & Development",
            "sequence": 2,
            "minimum_maturity": "ADEQUATE",
            "threshold": 65,
            "required_assessment": True,
            "required_evidence": ["scope-basis-reference"],
        },
        {
            "stage_code": "FEL-3",
            "stage_name": "Execution Definition / FEED / Readiness",
            "sequence": 3,
            "minimum_maturity": "READY",
            "threshold": 80,
            "required_assessment": True,
            "required_evidence": ["execution-definition-reference"],
        },
    ],
    "assessment_categories": [
        {"category_key": "business-basis", "name": "Business basis"},
        {"category_key": "scope-definition", "name": "Scope definition"},
        {"category_key": "delivery-basis", "name": "Delivery basis"},
    ],
    "assessment_elements": [
        {
            "element_key": "business-case-reference",
            "category_key": "business-basis",
            "name": "Business case basis",
            "weight": 1,
            "required": True,
            "evidence_required": True,
            "stages": ["FEL-1", "FEL-2", "FEL-3"],
        },
        {
            "element_key": "scope-basis-reference",
            "category_key": "scope-definition",
            "name": "Scope definition basis",
            "weight": 2,
            "required": True,
            "evidence_required": True,
            "stages": ["FEL-2", "FEL-3"],
        },
        {
            "element_key": "execution-definition-reference",
            "category_key": "delivery-basis",
            "name": "Execution definition basis",
            "weight": 2,
            "required": True,
            "evidence_required": True,
            "stages": ["FEL-3"],
        },
    ],
    "scoring_method": "WEIGHTED_SCORE",
    "score_direction": "HIGHER_IS_BETTER",
    "maturity_levels": [
        {"code": "NOT_READY", "minimum_score": 0},
        {"code": "DEVELOPING", "minimum_score": 40},
        {"code": "ADEQUATE", "minimum_score": 65},
        {"code": "READY", "minimum_score": 80},
    ],
    "thresholds": {"FEL-1": 40, "FEL-2": 65, "FEL-3": 80},
    "blocking_elements": [],
    "required_evidence": [],
    "action_policy": {"blocking_statuses": ["OPEN", "IN_PROGRESS"], "accepted_risk_blocks": False},
    "stage_review": {"mode": "SINGLE_REVIEWER", "author_must_differ_from_reviewer": True},
    "stage_progression": {"allow_imported_bypass": True, "require_justification_and_evidence": True},
    "inheritance": ["tenant", "enterprise", "business-unit", "portfolio", "project-type"],
}


class ProjectDefinitionService:
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

    # Bootstrap and overview --------------------------------------
    def ensure_seed(self) -> None:
        exists = self.db.scalar(
            select(AdminConfiguration.id).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.code == "pyp-custom-definition",
            )
        )
        if exists is not None:
            return
        content = deepcopy(DEFAULT_FRAMEWORK)
        self.db.add(
            AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=CONFIGURATION_KIND,
                code="pyp-custom-definition",
                name="P&Pmis Custom Project Definition",
                description="DRAFT starter; explicit review and publication are required before use.",
                status="draft",
                revision=1,
                version=1,
                content_json=content,
                content_hash=_hash(content),
                created_by_user_id=self.actor_id,
            )
        )
        self._event("project_definition.configuration_seeded_as_draft", "AdminConfiguration", None, {})
        self.db.commit()

    def overview(self, project_workspace_id: int | None = None) -> DefinitionOverviewOut:
        projects = self._projects()
        selected = None
        if project_workspace_id is not None:
            selected = self._project(project_workspace_id)
        elif projects:
            selected = projects[0]
        if selected is None:
            return DefinitionOverviewOut(
                projects=[],
                selected_project=None,
                fel_status=None,
                latest_assessment=None,
                readiness=None,
                actions=[],
                history=[],
                maturity_trend=[],
                framework=None,
                boundaries=self._boundaries(),
            )
        status = self._status(selected.id, required=False)
        history = self.assessments(selected.id) if status else []
        latest = next((item for item in history if item.status == "COMPLETED"), None)
        framework = self._framework_summary(self._effective_framework(selected, published_only=False))
        return DefinitionOverviewOut(
            projects=[self._project_summary(item) for item in projects],
            selected_project=self._project_summary(selected),
            fel_status=self._status_out(status) if status else None,
            latest_assessment=latest,
            readiness=self.readiness(selected.id) if status else None,
            actions=self.actions(selected.id) if status else [],
            history=history,
            maturity_trend=self.maturity_trend(selected.id) if status else [],
            framework=framework,
            boundaries=self._boundaries(),
        )

    # FEL status lifecycle ----------------------------------------
    def start_fel(self, project_id: int, payload: StartFELIn) -> ProjectFELStatusOut:
        prior = self.db.scalar(
            select(ProjectFELStatus).where(
                ProjectFELStatus.tenant_id == self.tenant_id,
                ProjectFELStatus.start_idempotency_key == payload.idempotency_key,
            )
        )
        if prior:
            return self._status_out(prior)
        project = self._project(project_id)
        if self._status(project_id, required=False):
            raise HTTPException(status_code=409, detail={"code": "FEL_ALREADY_STARTED"})
        framework = self._framework(project, payload.framework_configuration_id)
        content = framework.content_json or {}
        self._assert_governance_applicability(project, content)
        stages = self._stages(content)
        stage = self._stage(content, payload.stage_code)
        if stage["sequence"] > stages[0]["sequence"]:
            policy = dict(content.get("stage_progression", {}))
            if (
                not policy.get("allow_imported_bypass")
                or not payload.entry_justification
                or not payload.source_evidence
            ):
                raise HTTPException(status_code=409, detail={"code": "FEL_STAGE_SKIP_REQUIRES_GOVERNED_BYPASS"})
        source_hash = self._definition_source_hash(project, framework, payload.stage_code)
        now = utc_now()
        record = ProjectFELStatus(
            tenant_id=self.tenant_id,
            project_workspace_id=project.id,
            current_stage_code=payload.stage_code,
            status="IN_STAGE",
            stage_started_at=now,
            effective_framework_id=framework.id,
            effective_framework_revision=framework.revision,
            effective_framework_hash=framework.content_hash,
            readiness_status="BLOCKED",
            definition_source_hash=source_hash,
            revision_version=1,
            start_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            created_at=now,
            updated_by=self.actor_id,
            updated_at=now,
        )
        self.db.add(record)
        self.db.flush()
        self._event(
            "project_definition.FEL_started",
            "ProjectFELStatus",
            record.id,
            {
                "stage": payload.stage_code,
                "framework_hash": framework.content_hash,
                "bypass": stage["sequence"] > stages[0]["sequence"],
                "entry_justification": payload.entry_justification,
                "source_evidence": payload.source_evidence,
            },
        )
        self.db.commit()
        self.db.refresh(record)
        return self._status_out(record)

    def fel_status(self, project_id: int) -> ProjectFELStatusOut:
        self._project(project_id)
        return self._status_out(self._status(project_id))

    # Assessments --------------------------------------------------
    def assessments(self, project_id: int) -> list[AssessmentOut]:
        self._project(project_id)
        records = self.db.scalars(
            select(ProjectDefinitionAssessment)
            .where(
                ProjectDefinitionAssessment.tenant_id == self.tenant_id,
                ProjectDefinitionAssessment.project_workspace_id == project_id,
            )
            .order_by(ProjectDefinitionAssessment.assessment_version.desc())
        ).all()
        return [self._assessment_out(record) for record in records]

    def create_assessment(self, project_id: int, payload: AssessmentCreateIn) -> AssessmentOut:
        existing = self.db.scalar(
            select(ProjectDefinitionAssessment).where(
                ProjectDefinitionAssessment.tenant_id == self.tenant_id,
                ProjectDefinitionAssessment.create_idempotency_key == payload.idempotency_key,
            )
        )
        if existing:
            return self._assessment_out(existing)
        project = self._project(project_id)
        status = self._status(project_id, lock=True)
        active = self.db.scalar(
            select(ProjectDefinitionAssessment.id).where(
                ProjectDefinitionAssessment.tenant_id == self.tenant_id,
                ProjectDefinitionAssessment.project_workspace_id == project_id,
                ProjectDefinitionAssessment.status.in_(["DRAFT", "IN_PROGRESS"]),
            )
        )
        if active is not None:
            raise HTTPException(status_code=409, detail={"code": "ACTIVE_ASSESSMENT_EXISTS"})
        framework = self._configuration(status.effective_framework_id)
        record = self._new_assessment(project, status, framework, payload)
        self.db.add(record)
        self.db.flush()
        status.current_assessment_id = record.id
        self._touch_status(status)
        self._event(
            "project_definition.assessment_created",
            "ProjectDefinitionAssessment",
            record.id,
            {"version": record.assessment_version, "stage": record.fel_stage_code},
        )
        self.db.commit()
        self.db.refresh(record)
        return self._assessment_out(record)

    def assessment(self, assessment_id: int) -> AssessmentOut:
        return self._assessment_out(self._assessment(assessment_id))

    def update_assessment(
        self, assessment_id: int, expected_version: int, payload: AssessmentUpdateIn
    ) -> AssessmentOut:
        record = self._assessment(assessment_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status not in {"DRAFT", "IN_PROGRESS"}:
            raise HTTPException(status_code=409, detail={"code": "COMPLETED_ASSESSMENT_IMMUTABLE"})
        record.status = payload.status
        record.element_results_json = [
            item.model_dump(mode="json") | {"assessor": self.actor_id, "timestamp": utc_now().isoformat()}
            for item in payload.element_results
        ]
        record.evidence_refs_json = deepcopy(payload.evidence_refs)
        record.updated_at = utc_now()
        record.revision_version += 1
        self._event("project_definition.assessment_updated", "ProjectDefinitionAssessment", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._assessment_out(record)

    def complete_assessment(self, assessment_id: int, expected_version: int, idempotency_key: str) -> AssessmentOut:
        prior = self.db.scalar(
            select(ProjectDefinitionAssessment).where(
                ProjectDefinitionAssessment.tenant_id == self.tenant_id,
                ProjectDefinitionAssessment.complete_idempotency_key == idempotency_key,
            )
        )
        if prior:
            return self._assessment_out(prior)
        record = self._assessment(assessment_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status not in {"DRAFT", "IN_PROGRESS"}:
            raise HTTPException(status_code=409, detail={"code": "COMPLETED_ASSESSMENT_IMMUTABLE"})
        project = self._project(record.project_workspace_id)
        status = self._status(project.id, lock=True)
        framework = self._configuration(record.framework_config_id)
        current_hash = self._definition_source_hash(project, framework, status.current_stage_code)
        if current_hash != record.definition_source_hash or record.framework_hash != framework.content_hash:
            raise HTTPException(status_code=412, detail={"code": "STALE_PROJECT_DEFINITION_SOURCE"})
        calculated = self._calculate(record, framework.content_json or {})
        record.raw_score = calculated["raw_score"]
        record.normalized_score = calculated["normalized_score"]
        record.maturity_level = calculated["maturity_level"]
        record.threshold_status = calculated["threshold_status"]
        record.category_results_json = calculated["category_results"]
        record.blocking_items_json = calculated["blocking_items"]
        record.warnings_json = calculated["warnings"]
        record.actions_summary_json = self._action_summary(project.id, record.id)
        record.status = "COMPLETED"
        record.completed_by = self.actor_id
        record.completed_at = utc_now()
        record.complete_idempotency_key = idempotency_key
        record.assessment_hash = _hash(self._assessment_hash_payload(record))
        record.updated_at = utc_now()
        record.revision_version += 1
        status.current_assessment_id = record.id
        status.latest_completed_assessment_id = record.id
        status.definition_source_hash = current_hash
        self._touch_status(status)
        self._event(
            "project_definition.assessment_completed",
            "ProjectDefinitionAssessment",
            record.id,
            {"assessment_hash": record.assessment_hash, "threshold_status": record.threshold_status},
        )
        self.db.commit()
        self.db.refresh(record)
        return self._assessment_out(record)

    def reevaluate(self, assessment_id: int, idempotency_key: str) -> AssessmentOut:
        prior = self.db.scalar(
            select(ProjectDefinitionAssessment).where(
                ProjectDefinitionAssessment.tenant_id == self.tenant_id,
                ProjectDefinitionAssessment.reevaluate_idempotency_key == idempotency_key,
            )
        )
        if prior:
            return self._assessment_out(prior)
        source = self._assessment(assessment_id)
        if source.status != "COMPLETED":
            raise HTTPException(status_code=409, detail={"code": "REEVALUATION_REQUIRES_COMPLETED_ASSESSMENT"})
        project = self._project(source.project_workspace_id)
        status = self._status(project.id, lock=True)
        if self.db.scalar(
            select(ProjectDefinitionAssessment.id).where(
                ProjectDefinitionAssessment.tenant_id == self.tenant_id,
                ProjectDefinitionAssessment.project_workspace_id == project.id,
                ProjectDefinitionAssessment.status.in_(["DRAFT", "IN_PROGRESS"]),
            )
        ):
            raise HTTPException(status_code=409, detail={"code": "ACTIVE_ASSESSMENT_EXISTS"})
        framework = self._framework(project)
        record = self._new_assessment(
            project,
            status,
            framework,
            AssessmentCreateIn(idempotency_key=f"reevaluation-create-{idempotency_key}"),
        )
        record.reevaluate_idempotency_key = idempotency_key
        record.source_snapshot_json["supersedes_assessment_id"] = source.id
        self.db.add(record)
        self.db.flush()
        status.current_assessment_id = record.id
        status.readiness_status = "STALE"
        self._touch_status(status)
        self._event(
            "project_definition.reevaluation_started",
            "ProjectDefinitionAssessment",
            record.id,
            {"supersedes_assessment_id": source.id},
        )
        self.db.commit()
        self.db.refresh(record)
        return self._assessment_out(record)

    # Actions ------------------------------------------------------
    def actions(self, project_id: int) -> list[DefinitionActionOut]:
        self._project(project_id)
        records = self.db.scalars(
            select(ProjectDefinitionAction)
            .where(
                ProjectDefinitionAction.tenant_id == self.tenant_id,
                ProjectDefinitionAction.project_workspace_id == project_id,
            )
            .order_by(ProjectDefinitionAction.created_at.desc())
        ).all()
        return [self._action_out(item) for item in records]

    def create_action(self, project_id: int, payload: ActionCreateIn) -> DefinitionActionOut:
        prior = self.db.scalar(
            select(ProjectDefinitionAction).where(
                ProjectDefinitionAction.tenant_id == self.tenant_id,
                ProjectDefinitionAction.create_idempotency_key == payload.idempotency_key,
            )
        )
        if prior:
            return self._action_out(prior)
        self._project(project_id)
        assessment = self._assessment(payload.assessment_id)
        if assessment.project_workspace_id != project_id:
            raise HTTPException(status_code=422, detail={"code": "ACTION_ASSESSMENT_PROJECT_MISMATCH"})
        now = utc_now()
        record = ProjectDefinitionAction(
            tenant_id=self.tenant_id,
            project_workspace_id=project_id,
            assessment_id=assessment.id,
            element_key=payload.element_key,
            title=payload.title,
            description=payload.description,
            owner_id=payload.owner_id,
            target_date=payload.target_date,
            status="OPEN",
            evidence_refs_json=deepcopy(payload.evidence_refs),
            blocking=payload.blocking,
            audit_json=[{"actor": self.actor_id, "action": "created", "timestamp": now.isoformat()}],
            revision_version=1,
            create_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            created_at=now,
            updated_by=self.actor_id,
            updated_at=now,
        )
        self.db.add(record)
        self.db.flush()
        self._event("project_definition.action_created", "ProjectDefinitionAction", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return self._action_out(record)

    def update_action(self, action_id: int, expected_version: int, payload: ActionUpdateIn) -> DefinitionActionOut:
        record = self._action(action_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        for key in ("title", "description", "owner_id", "target_date", "status", "blocking"):
            value = getattr(payload, key)
            if value is not None:
                setattr(record, key, value)
        if payload.evidence_refs is not None:
            record.evidence_refs_json = deepcopy(payload.evidence_refs)
        record.audit_json = [
            *(record.audit_json or []),
            {"actor": self.actor_id, "action": "updated", "status": record.status, "timestamp": utc_now().isoformat()},
        ]
        record.updated_by = self.actor_id
        record.updated_at = utc_now()
        record.revision_version += 1
        self._event(
            "project_definition.action_updated", "ProjectDefinitionAction", record.id, {"status": record.status}
        )
        self.db.commit()
        self.db.refresh(record)
        return self._action_out(record)

    # Readiness and stage governance ------------------------------
    def readiness(self, project_id: int) -> DefinitionReadinessOut:
        project = self._project(project_id)
        status = self._status(project_id, required=False)
        if status is None:
            return self._not_started_readiness(project_id)
        framework = self._configuration(status.effective_framework_id)
        current_hash = self._definition_source_hash(project, framework, status.current_stage_code)
        source_current = (
            current_hash == status.definition_source_hash
            and status.effective_framework_hash == framework.content_hash
            and framework.status == "published"
        )
        assessment = (
            self._assessment(status.latest_completed_assessment_id, required=False)
            if status.latest_completed_assessment_id
            else None
        )
        blockers: list[str] = []
        warnings: list[str] = []
        if not source_current:
            blockers.append("STALE_PROJECT_DEFINITION_SOURCE")
        if assessment is None or assessment.status != "COMPLETED":
            blockers.append("COMPLETED_ASSESSMENT_REQUIRED")
        elif assessment.fel_stage_code != status.current_stage_code:
            blockers.append("CURRENT_STAGE_ASSESSMENT_REQUIRED")
        stage = self._stage(framework.content_json or {}, status.current_stage_code)
        required_maturity = str(stage.get("minimum_maturity") or "") or None
        maturity_met = bool(assessment and assessment.threshold_status in {"MEETS_REQUIRED", "EXCEEDS_REQUIRED"})
        if assessment and not maturity_met:
            blockers.append("MINIMUM_DEFINITION_MATURITY_NOT_MET")
        blocking_items = list(assessment.blocking_items_json or []) if assessment else []
        if blocking_items:
            blockers.append("BLOCKING_DEFINITION_ELEMENTS")
        open_actions = self._open_blocking_actions(project_id)
        if open_actions:
            blockers.append("OPEN_BLOCKING_DEFINITION_ACTIONS")
        evidence_coverage = self._evidence_coverage(assessment, framework.content_json or {}) if assessment else 0.0
        if evidence_coverage < 100:
            blockers.append("REQUIRED_DEFINITION_EVIDENCE_MISSING")
        readiness_status = "STALE" if not source_current else ("READY" if not blockers else "BLOCKED")
        payload = {
            "project_workspace_id": project_id,
            "stage": status.current_stage_code,
            "assessment_hash": assessment.assessment_hash if assessment else None,
            "framework_hash": framework.content_hash,
            "source_hash": current_hash,
            "maturity_level": assessment.maturity_level if assessment else None,
            "threshold_status": assessment.threshold_status if assessment else "NOT_EVALUATED",
            "blocking_items": len(blocking_items),
            "open_actions": len(open_actions),
            "evidence_coverage": evidence_coverage,
            "status": readiness_status,
        }
        return DefinitionReadinessOut(
            status=readiness_status,
            tenant_id=self.tenant_id,
            project_workspace_id=project_id,
            current_FEL_stage=status.current_stage_code,
            latest_completed_assessment_id=assessment.id if assessment else None,
            framework_code=assessment.framework_code
            if assessment
            else str(framework.content_json.get("framework_code")),
            framework_version=(
                assessment.framework_version if assessment else str(framework.content_json.get("framework_version"))
            ),
            assessment_hash=assessment.assessment_hash if assessment else None,
            maturity_level=assessment.maturity_level if assessment else None,
            threshold_status=assessment.threshold_status if assessment else "NOT_EVALUATED",
            required_maturity=required_maturity,
            required_stage=status.current_stage_code,
            required_maturity_met=maturity_met,
            blocking_item_count=len(blocking_items),
            open_blocking_action_count=len(open_actions),
            evidence_coverage=evidence_coverage,
            warnings=warnings,
            blockers=sorted(set(blockers)),
            definition_readiness_hash=_hash(payload),
            source_current=source_current,
            can_supply_investment_gate_evidence=readiness_status == "READY",
            project_source_reference={
                "project_workspace_id": project_id,
                "status_id": status.id,
                "status_revision": status.revision_version,
                "definition_source_hash": status.definition_source_hash,
                "definition_readiness_hash": _hash(payload),
            },
        )

    def submit_stage_review(self, project_id: int, expected_version: int, idempotency_key: str) -> ProjectFELStatusOut:
        prior = self.db.scalar(
            select(ProjectFELStatus).where(
                ProjectFELStatus.tenant_id == self.tenant_id,
                ProjectFELStatus.submit_idempotency_key == idempotency_key,
            )
        )
        if prior:
            return self._status_out(prior)
        record = self._status(project_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        ready = self.readiness(project_id)
        if ready.status != "READY":
            raise HTTPException(
                status_code=409, detail={"code": "PROJECT_DEFINITION_NOT_READY", "blockers": ready.blockers}
            )
        record.status = "READY_FOR_STAGE_REVIEW"
        record.readiness_status = "READY"
        record.submit_idempotency_key = idempotency_key
        record.review_submitted_by = self.actor_id
        record.review_submitted_at = utc_now()
        self._touch_status(record)
        self._event(
            "project_definition.stage_submitted", "ProjectFELStatus", record.id, {"stage": record.current_stage_code}
        )
        self.db.commit()
        self.db.refresh(record)
        return self._status_out(record)

    def complete_stage(self, project_id: int, expected_version: int, idempotency_key: str) -> ProjectFELStatusOut:
        prior = self.db.scalar(
            select(ProjectFELStatus).where(
                ProjectFELStatus.tenant_id == self.tenant_id,
                ProjectFELStatus.complete_stage_idempotency_key == idempotency_key,
            )
        )
        if prior:
            return self._status_out(prior)
        record = self._status(project_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status != "READY_FOR_STAGE_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "FEL_STAGE_NOT_SUBMITTED"})
        assessment = self._assessment(record.latest_completed_assessment_id)
        framework = self._configuration(record.effective_framework_id)
        sod = dict((framework.content_json or {}).get("stage_review", {}))
        if sod.get("author_must_differ_from_reviewer", True) and assessment.assessed_by == self.actor_id:
            raise HTTPException(status_code=409, detail={"code": "FEL_STAGE_REVIEW_SOD_VIOLATION"})
        completed_stage = record.current_stage_code
        stages = self._stages(framework.content_json or {})
        current_index = next(index for index, item in enumerate(stages) if item["stage_code"] == completed_stage)
        record.complete_stage_idempotency_key = idempotency_key
        record.reviewed_by = self.actor_id
        record.reviewed_at = utc_now()
        if current_index + 1 < len(stages):
            record.current_stage_code = str(stages[current_index + 1]["stage_code"])
            record.status = "IN_STAGE"
            record.stage_started_at = utc_now()
            record.current_assessment_id = None
            record.readiness_status = "BLOCKED"
            project = self._project(project_id)
            record.definition_source_hash = self._definition_source_hash(project, framework, record.current_stage_code)
        else:
            record.status = "STAGE_COMPLETED"
            record.readiness_status = "READY"
        self._touch_status(record)
        self._event(
            "project_definition.stage_completed",
            "ProjectFELStatus",
            record.id,
            {"completed_stage": completed_stage, "next_stage": record.current_stage_code, "investment_approved": False},
        )
        self.db.commit()
        self.db.refresh(record)
        return self._status_out(record)

    def return_stage(
        self, project_id: int, expected_version: int, idempotency_key: str, note: str
    ) -> ProjectFELStatusOut:
        record = self._status(project_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status != "READY_FOR_STAGE_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "FEL_STAGE_NOT_SUBMITTED"})
        record.status = "IN_STAGE"
        record.readiness_status = "BLOCKED"
        record.return_stage_idempotency_key = idempotency_key
        record.reviewed_by = self.actor_id
        record.reviewed_at = utc_now()
        self._touch_status(record)
        self._event("project_definition.stage_returned", "ProjectFELStatus", record.id, {"note": note})
        self.db.commit()
        self.db.refresh(record)
        return self._status_out(record)

    # Refresh and evidence contract -------------------------------
    def refresh_preview(self, project_id: int) -> dict[str, Any]:
        project = self._project(project_id)
        status = self._status(project_id)
        current = self._framework(project)
        current_hash = self._definition_source_hash(project, current, status.current_stage_code)
        changes: list[dict[str, Any]] = []
        if status.effective_framework_hash != current.content_hash:
            changes.append(
                {"field": "framework_hash", "before": status.effective_framework_hash, "after": current.content_hash}
            )
        if status.definition_source_hash != current_hash:
            changes.append(
                {"field": "definition_source_hash", "before": status.definition_source_hash, "after": current_hash}
            )
        self._event("project_definition.refresh_previewed", "ProjectFELStatus", status.id, {"changes": changes})
        self.db.commit()
        return {
            "project_workspace_id": project_id,
            "current_source_hash": current_hash,
            "stored_source_hash": status.definition_source_hash,
            "changes": changes,
            "would_create_assessment_version": bool(changes),
            "persisted": False,
        }

    def refresh(
        self, project_id: int, expected_version: int, expected_source_hash: str, idempotency_key: str
    ) -> ProjectFELStatusOut:
        prior = self.db.scalar(
            select(ProjectFELStatus).where(
                ProjectFELStatus.tenant_id == self.tenant_id,
                ProjectFELStatus.refresh_idempotency_key == idempotency_key,
            )
        )
        if prior:
            return self._status_out(prior)
        project = self._project(project_id)
        status = self._status(project_id, lock=True)
        self._check_version(status.revision_version, expected_version)
        framework = self._framework(project)
        current_hash = self._definition_source_hash(project, framework, status.current_stage_code)
        if current_hash != expected_source_hash:
            raise HTTPException(status_code=412, detail={"code": "STALE_PROJECT_DEFINITION_SOURCE"})
        status.effective_framework_id = framework.id
        status.effective_framework_revision = framework.revision
        status.effective_framework_hash = framework.content_hash
        status.definition_source_hash = current_hash
        status.current_assessment_id = None
        status.readiness_status = "STALE"
        status.status = "IN_STAGE"
        status.refresh_idempotency_key = idempotency_key
        self._touch_status(status)
        self._event("project_definition.refresh_applied", "ProjectFELStatus", status.id, {"source_hash": current_hash})
        self.db.commit()
        self.db.refresh(status)
        return self._status_out(status)

    def investment_gate_evidence(self, project_id: int) -> InvestmentGateEvidenceOut:
        readiness = self.readiness(project_id)
        assessment = (
            self._assessment(readiness.latest_completed_assessment_id, required=False)
            if readiness.latest_completed_assessment_id
            else None
        )
        return InvestmentGateEvidenceOut(
            evidence_type="PROJECT_DEFINITION_READINESS",
            project_workspace_id=project_id,
            FEL_stage_code=readiness.current_FEL_stage,
            framework_code=readiness.framework_code,
            framework_type=assessment.framework_type if assessment else None,
            framework_version=readiness.framework_version,
            assessment_id=assessment.id if assessment else None,
            assessment_version=assessment.assessment_version if assessment else None,
            assessment_hash=readiness.assessment_hash,
            assessment_date=assessment.assessment_date if assessment else None,
            raw_score=assessment.raw_score if assessment else None,
            normalized_score=assessment.normalized_score if assessment else None,
            maturity_level=readiness.maturity_level,
            threshold_status=readiness.threshold_status,
            minimum_requirement_met=readiness.required_maturity_met,
            blocking_items_count=readiness.blocking_item_count,
            open_blocking_actions=readiness.open_blocking_action_count,
            evidence_coverage=readiness.evidence_coverage,
            readiness_status=readiness.status,
            definition_readiness_hash=readiness.definition_readiness_hash,
            source_current=readiness.source_current,
            can_supply_investment_gate_evidence=readiness.can_supply_investment_gate_evidence,
            project_source_reference=deepcopy(getattr(readiness, "project_source_reference", {})),
        )

    def maturity_trend(self, project_id: int) -> list[dict[str, Any]]:
        self._project(project_id)
        records = self.db.scalars(
            select(ProjectDefinitionAssessment)
            .where(
                ProjectDefinitionAssessment.tenant_id == self.tenant_id,
                ProjectDefinitionAssessment.project_workspace_id == project_id,
                ProjectDefinitionAssessment.status == "COMPLETED",
            )
            .order_by(ProjectDefinitionAssessment.assessment_date)
        ).all()
        segments: dict[tuple[str, str, str], int] = {}
        output: list[dict[str, Any]] = []
        for record in records:
            key = (record.framework_code, record.framework_version, record.framework_type)
            segment = segments.setdefault(key, len(segments) + 1)
            summary = self._action_summary(project_id, record.id)
            output.append(
                {
                    "assessment_id": record.id,
                    "assessment_date": record.assessment_date,
                    "FEL_stage": record.fel_stage_code,
                    "framework": record.framework_code,
                    "framework_version": record.framework_version,
                    "score": record.normalized_score,
                    "maturity_level": record.maturity_level,
                    "threshold_status": record.threshold_status,
                    "blocking_item_count": len(record.blocking_items_json or []),
                    "open_action_count": summary["open_blocking"],
                    "trend_segment": segment,
                    "cross_framework_comparison_allowed": len(segments) == 1,
                }
            )
        return output

    # ADMIN --------------------------------------------------------
    def configurations(self) -> list[AdminConfigurationOut]:
        records = self.db.scalars(
            select(AdminConfiguration)
            .where(AdminConfiguration.tenant_id == self.tenant_id, AdminConfiguration.kind == CONFIGURATION_KIND)
            .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
        ).all()
        return [AdminConfigurationOut.model_validate(item) for item in records]

    def configuration_preview(
        self,
        project_workspace_id: int | None,
        project_type: str | None,
        governance_model: str,
        current_stage: str,
        configuration_id: int | None,
        content_json: dict[str, Any] | None,
    ) -> ConfigurationPreviewOut:
        project = self._project(project_workspace_id) if project_workspace_id else None
        record = (
            self._configuration(configuration_id)
            if configuration_id
            else self._effective_framework(project, published_only=False)
        )
        content = deepcopy(
            content_json if content_json is not None else (record.content_json if record else DEFAULT_FRAMEWORK)
        )
        issues = self._configuration_issues(content)
        stages = self._stages(content) if not issues else list(content.get("stage_structure", []))
        elements = self._elements(content, current_stage)
        applicable_models = list(content.get("applicable_governance_models", []))
        applicable_types = list(content.get("applicable_project_types", []))
        blockers = list(issues)
        if governance_model not in applicable_models:
            blockers.append("GOVERNANCE_MODEL_NOT_APPLICABLE")
        if project_type and "*" not in applicable_types and project_type not in applicable_types:
            blockers.append("PROJECT_TYPE_NOT_MAPPED")
        chain = self._resolution_chain(project, record)
        stage_codes = [str(item.get("stage_code")) for item in stages]
        return ConfigurationPreviewOut(
            effective_framework=self._framework_summary(record) | {"content": content}
            if record
            else {"content": content},
            stage_structure=stages,
            applicable_assessment_elements=elements,
            scoring_method=str(content.get("scoring_method") or "NONE"),
            maturity_thresholds=list(content.get("maturity_levels", [])),
            required_evidence=[
                deepcopy(item) for item in content.get("required_evidence", []) if isinstance(item, dict)
            ],
            blocking_elements=list(content.get("blocking_elements", [])),
            PYP_INV_SELECT_readiness_preview={"required_stage": "FEL-2", "stage_available": "FEL-2" in stage_codes},
            PYP_FFA_readiness_preview={
                "required_stage": "FEL-3",
                "stage_available": "FEL-3" in stage_codes,
                "funding_is_independent": True,
            },
            warnings=["DRAFT_CONFIGURATION_NOT_PERSISTED"] if record and record.status == "draft" else [],
            blockers=sorted(set(blockers)),
            resolution_chain=chain,
            resolution_hash=_hash(chain),
            persisted=False,
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfigurationOut:
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
        record = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code=source.code,
            name=source.name,
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=deepcopy(source.content_json),
            content_hash=source.content_hash,
            created_by_user_id=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        self._event(
            "project_definition.configuration_cloned", "AdminConfiguration", record.id, {"source_id": source.id}
        )
        self.db.commit()
        self.db.refresh(record)
        return AdminConfigurationOut.model_validate(record)

    def update_configuration(
        self,
        configuration_id: int,
        expected_version: int,
        name: str,
        description: str,
        content_json: dict[str, Any],
    ) -> AdminConfigurationOut:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_IMMUTABLE"})
        self._validate_configuration(content_json)
        record.name = name
        record.description = description
        record.content_json = deepcopy(content_json)
        record.content_hash = _hash(content_json)
        record.version += 1
        record.updated_at = utc_now()
        self._event("project_definition.configuration_updated", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return AdminConfigurationOut.model_validate(record)

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfigurationOut:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "CONFIGURATION_ALREADY_PUBLISHED"})
        self._validate_configuration(record.content_json or {})
        record.status = "published"
        record.published_at = utc_now()
        record.version += 1
        record.updated_at = utc_now()
        self._event("project_definition.configuration_published", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return AdminConfigurationOut.model_validate(record)

    # Internal calculations ---------------------------------------
    def _new_assessment(
        self,
        project: EnterpriseWorkspace,
        status: ProjectFELStatus,
        framework: AdminConfiguration,
        payload: AssessmentCreateIn,
    ) -> ProjectDefinitionAssessment:
        version = (
            int(
                self.db.scalar(
                    select(func.max(ProjectDefinitionAssessment.assessment_version)).where(
                        ProjectDefinitionAssessment.tenant_id == self.tenant_id,
                        ProjectDefinitionAssessment.project_workspace_id == project.id,
                    )
                )
                or 0
            )
            + 1
        )
        now = utc_now()
        content = framework.content_json or {}
        snapshot = {
            "project": self._project_summary(project),
            "project_type": self._project_type(project),
            "governance_model": self._governance_model(project),
            "FEL_stage": status.current_stage_code,
            "framework": self._framework_summary(framework),
            "applicable_elements": self._elements(content, status.current_stage_code),
            "thresholds": deepcopy(content.get("thresholds", {})),
            "planning_entry": deepcopy(dict(project.defaults_json or {}).get("_project", {}).get("planning_entry", {})),
            "assessment_configuration_hash": framework.content_hash,
            "captured_at": now.isoformat(),
        }
        return ProjectDefinitionAssessment(
            tenant_id=self.tenant_id,
            project_workspace_id=project.id,
            assessment_number=f"PDA-{project.code}-{version:03d}",
            assessment_version=version,
            framework_config_id=framework.id,
            framework_code=str(content.get("framework_code")),
            framework_type=str(content.get("framework_type")),
            framework_version=str(content.get("framework_version")),
            framework_hash=framework.content_hash,
            fel_stage_code=status.current_stage_code,
            assessment_date=now,
            as_of_date=payload.as_of_date or now,
            status="DRAFT",
            threshold_status="NOT_EVALUATED",
            category_results_json=[],
            element_results_json=[],
            blocking_items_json=[],
            warnings_json=[],
            actions_summary_json={},
            evidence_refs_json=[],
            source_snapshot_json=snapshot,
            definition_source_hash=self._definition_source_hash(project, framework, status.current_stage_code),
            assessed_by=self.actor_id,
            revision_version=1,
            create_idempotency_key=payload.idempotency_key,
            created_at=now,
            updated_at=now,
        )

    def _calculate(self, record: ProjectDefinitionAssessment, content: dict[str, Any]) -> dict[str, Any]:
        elements = {str(item["element_key"]): item for item in self._elements(content, record.fel_stage_code)}
        results = {str(item.get("element_key")): item for item in record.element_results_json or []}
        missing: list[str] = []
        missing_evidence: list[str] = []
        scored: list[tuple[float, float, str]] = []
        blocking: list[dict[str, Any]] = []
        category_values: dict[str, list[tuple[float, float]]] = {}
        for key, element in elements.items():
            result = results.get(key)
            if element.get("required", True) and (
                result is None
                or not result.get("applicable", True)
                or (result.get("score") is None and not result.get("maturity_status"))
            ):
                missing.append(key)
                continue
            if result is None or not result.get("applicable", True):
                continue
            if element.get("evidence_required") and not result.get("evidence_refs"):
                missing_evidence.append(key)
            if result.get("score") is not None:
                value = float(result["score"])
                weight = float(element.get("weight", 1))
                scored.append((value, weight, str(element.get("category_key") or "uncategorized")))
                category_values.setdefault(str(element.get("category_key") or "uncategorized"), []).append(
                    (value, weight)
                )
            if result.get("blocking") or (
                key in set(content.get("blocking_elements", []))
                and result.get("maturity_status") in {"BLOCKED", "NOT_READY"}
            ):
                blocking.append(
                    {
                        "element_key": key,
                        "category_key": element.get("category_key"),
                        "reason": "BLOCKING_ELEMENT_RESULT",
                    }
                )
        if missing or missing_evidence:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ASSESSMENT_INCOMPLETE",
                    "missing_elements": missing,
                    "missing_evidence": missing_evidence,
                },
            )
        method = str(content.get("scoring_method") or "NONE")
        raw_score: float | None = None
        normalized_score: float | None = None
        if method in {"WEIGHTED_SCORE", "CUSTOM_CONFIGURED", "MATURITY_LEVEL"} and scored:
            total_weight = sum(weight for _, weight, _ in scored)
            raw_score = sum(value * weight for value, weight, _ in scored) / total_weight
            normalized_score = raw_score
        elif method == "POINTS" and scored:
            raw_score = sum(value * weight for value, weight, _ in scored)
            normalized_score = raw_score
        stage_threshold = float(dict(content.get("thresholds", {})).get(record.fel_stage_code, 0))
        direction = str(content.get("score_direction") or "HIGHER_IS_BETTER")
        meets = raw_score is not None and (
            raw_score <= stage_threshold if direction == "LOWER_IS_BETTER" else raw_score >= stage_threshold
        )
        exceeds = raw_score is not None and (
            raw_score <= stage_threshold * 0.8 if direction == "LOWER_IS_BETTER" else raw_score >= stage_threshold * 1.1
        )
        threshold_status = "EXCEEDS_REQUIRED" if exceeds else ("MEETS_REQUIRED" if meets else "BELOW_REQUIRED")
        maturity = self._maturity_level(raw_score, content)
        category_results = [
            {
                "category_key": category,
                "score": sum(value * weight for value, weight in values) / sum(weight for _, weight in values),
            }
            for category, values in sorted(category_values.items())
        ]
        return {
            "raw_score": raw_score,
            "normalized_score": normalized_score,
            "maturity_level": maturity,
            "threshold_status": threshold_status,
            "category_results": category_results,
            "blocking_items": blocking,
            "warnings": [] if method != "NONE" else ["FRAMEWORK_HAS_NO_NUMERIC_SCORE"],
        }

    @staticmethod
    def _maturity_level(score: float | None, content: dict[str, Any]) -> str | None:
        if score is None:
            return None
        levels = list(content.get("maturity_levels", []))
        direction = str(content.get("score_direction") or "HIGHER_IS_BETTER")
        if direction == "LOWER_IS_BETTER":
            eligible = [item for item in levels if score <= float(item.get("maximum_score", float("inf")))]
            return str(eligible[0].get("code")) if eligible else str(levels[-1].get("code")) if levels else None
        eligible = [item for item in levels if score >= float(item.get("minimum_score", 0))]
        return str(eligible[-1].get("code")) if eligible else str(levels[0].get("code")) if levels else None

    def _evidence_coverage(self, assessment: ProjectDefinitionAssessment, content: dict[str, Any]) -> float:
        required = [
            item for item in self._elements(content, assessment.fel_stage_code) if item.get("evidence_required")
        ]
        if not required:
            return 100.0
        results = {str(item.get("element_key")): item for item in assessment.element_results_json or []}
        present = sum(1 for item in required if results.get(str(item["element_key"]), {}).get("evidence_refs"))
        return round(present / len(required) * 100, 2)

    def _definition_source_hash(
        self, project: EnterpriseWorkspace, framework: AdminConfiguration, stage_code: str
    ) -> str:
        context = deepcopy(dict(project.defaults_json or {}).get("_project", {}))
        return _hash(
            {
                "project": {
                    "id": project.id,
                    "code": project.code,
                    "version": project.version,
                    "status": project.status,
                },
                "project_type": self._project_type(project),
                "governance_model": self._governance_model(project),
                "FEL_stage": stage_code,
                "framework": {
                    "code": framework.content_json.get("framework_code"),
                    "version": framework.content_json.get("framework_version"),
                    "hash": framework.content_hash,
                },
                "definition_evidence_hashes": context.get("definition_evidence_hashes", []),
                "planning_entry_hash": context.get("planning_entry_hash"),
                "scope_baseline_hash": context.get("scope_baseline_hash"),
            }
        )

    # Configuration resolution -----------------------------------
    def _effective_framework(
        self, project: EnterpriseWorkspace | None, *, published_only: bool = True
    ) -> AdminConfiguration | None:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
        )
        if published_only:
            statement = statement.where(AdminConfiguration.status == "published")
        records = list(self.db.scalars(statement).all())
        if not records:
            return None
        path_ids = {item.id: index for index, item in enumerate(self._workspace_path(project), start=1)}
        project_type = self._project_type(project) if project else None
        governance = self._governance_model(project) if project else "CAPITAL_OWNER"
        candidates: list[tuple[int, int, AdminConfiguration]] = []
        for record in records:
            content = record.content_json or {}
            if governance not in set(content.get("applicable_governance_models", [])):
                continue
            types = set(content.get("applicable_project_types", []))
            if project_type and "*" not in types and project_type not in types:
                continue
            scope = dict(content.get("scope", {}))
            scope_id = scope.get("workspace_id")
            if scope_id is not None and int(scope_id) not in path_ids:
                continue
            specificity = path_ids.get(int(scope_id), 0) if scope_id is not None else 0
            candidates.append((specificity, record.revision, record))
        return max(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None

    def _framework(self, project: EnterpriseWorkspace, configuration_id: int | None = None) -> AdminConfiguration:
        record = self._configuration(configuration_id) if configuration_id else self._effective_framework(project)
        if record is None or record.status != "published":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_DEFINITION_FRAMEWORK_REQUIRED"})
        self._assert_governance_applicability(project, record.content_json or {})
        return record

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
            raise HTTPException(status_code=404, detail="Project Definition Framework not found")
        return record

    def _configuration_issues(self, content: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        if content.get("framework_type") not in FRAMEWORK_TYPES:
            issues.append("INVALID_FRAMEWORK_TYPE")
        if content.get("scoring_method") not in SCORING_METHODS:
            issues.append("INVALID_SCORING_METHOD")
        if content.get("score_direction") not in {"HIGHER_IS_BETTER", "LOWER_IS_BETTER"}:
            issues.append("INVALID_SCORE_DIRECTION")
        stages = list(content.get("stage_structure", []))
        codes = [str(item.get("stage_code") or "") for item in stages]
        sequences = [item.get("sequence") for item in stages]
        if (
            not stages
            or any(not code for code in codes)
            or len(codes) != len(set(codes))
            or len(sequences) != len(set(sequences))
        ):
            issues.append("INVALID_FEL_STAGE_STRUCTURE")
        elements = list(content.get("assessment_elements", []))
        keys = [str(item.get("element_key") or "") for item in elements]
        if not elements or any(not key for key in keys) or len(keys) != len(set(keys)):
            issues.append("INVALID_ASSESSMENT_ELEMENTS")
        if not content.get("framework_code") or not content.get("framework_version"):
            issues.append("INVALID_FRAMEWORK_IDENTITY")
        if not content.get("applicable_governance_models"):
            issues.append("GOVERNANCE_MODEL_MAPPING_REQUIRED")
        if any(not isinstance(item, dict) for item in content.get("required_evidence", [])):
            issues.append("INVALID_REQUIRED_EVIDENCE")
        forbidden = {"cii_pdri_elements", "ipa_fel_index_content", "executable_formula", "formula_language"}
        if forbidden.intersection(content):
            issues.append("PROPRIETARY_OR_EXECUTABLE_CONTENT_NOT_ALLOWED")
        return sorted(set(issues))

    def _validate_configuration(self, content: dict[str, Any]) -> None:
        issues = self._configuration_issues(content)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION", "issues": issues})

    # Persistence helpers -----------------------------------------
    def _projects(self) -> list[EnterpriseWorkspace]:
        statement = select(EnterpriseWorkspace).where(
            EnterpriseWorkspace.tenant_id == self.tenant_id,
            EnterpriseWorkspace.workspace_type_code == "project",
        )
        if self.context is not None and not self.context.organization_wide:
            statement = statement.where(EnterpriseWorkspace.id.in_(self.context.workspace_ids or {-1}))
        return list(self.db.scalars(statement.order_by(EnterpriseWorkspace.name)).all())

    def _project(self, project_id: int | None) -> EnterpriseWorkspace:
        record = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == project_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.workspace_type_code == "project",
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Project Workspace not found")
        self._assert_scope(record.id)
        return record

    def _status(self, project_id: int, *, lock: bool = False, required: bool = True) -> ProjectFELStatus | None:
        statement = select(ProjectFELStatus).where(
            ProjectFELStatus.tenant_id == self.tenant_id,
            ProjectFELStatus.project_workspace_id == project_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None and required:
            raise HTTPException(status_code=404, detail={"code": "FEL_NOT_STARTED"})
        return record

    def _assessment(
        self, assessment_id: int | None, *, lock: bool = False, required: bool = True
    ) -> ProjectDefinitionAssessment | None:
        statement = select(ProjectDefinitionAssessment).where(
            ProjectDefinitionAssessment.id == assessment_id,
            ProjectDefinitionAssessment.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None and required:
            raise HTTPException(status_code=404, detail="Project Definition Assessment not found")
        if record:
            self._assert_scope(record.project_workspace_id)
        return record

    def _action(self, action_id: int, *, lock: bool = False) -> ProjectDefinitionAction:
        statement = select(ProjectDefinitionAction).where(
            ProjectDefinitionAction.id == action_id,
            ProjectDefinitionAction.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Project Definition Action not found")
        self._assert_scope(record.project_workspace_id)
        return record

    def _open_blocking_actions(self, project_id: int) -> list[ProjectDefinitionAction]:
        return list(
            self.db.scalars(
                select(ProjectDefinitionAction).where(
                    ProjectDefinitionAction.tenant_id == self.tenant_id,
                    ProjectDefinitionAction.project_workspace_id == project_id,
                    ProjectDefinitionAction.blocking.is_(True),
                    ProjectDefinitionAction.status.in_(ACTION_BLOCKING_STATUSES),
                )
            ).all()
        )

    def _action_summary(self, project_id: int, assessment_id: int) -> dict[str, int]:
        records = self.db.scalars(
            select(ProjectDefinitionAction).where(
                ProjectDefinitionAction.tenant_id == self.tenant_id,
                ProjectDefinitionAction.project_workspace_id == project_id,
                ProjectDefinitionAction.assessment_id == assessment_id,
            )
        ).all()
        return {
            "total": len(records),
            "open_blocking": sum(1 for item in records if item.blocking and item.status in ACTION_BLOCKING_STATUSES),
            "resolved": sum(1 for item in records if item.status in {"RESOLVED", "ACCEPTED_RISK"}),
        }

    # Serialization and metadata ---------------------------------
    def _status_out(self, record: ProjectFELStatus) -> ProjectFELStatusOut:
        readiness = self.readiness(record.project_workspace_id)
        actions = ["can_view_project_definition", "can_view_investment_gate_evidence"]
        if record.status in {"IN_STAGE", "BLOCKED"}:
            actions.extend(["can_start_assessment", "can_add_definition_action", "can_refresh_definition_source"])
        if record.status == "READY_FOR_STAGE_REVIEW":
            actions.extend(["can_complete_stage", "can_return_stage"])
        if readiness.status == "READY" and record.status == "IN_STAGE":
            actions.append("can_submit_stage_review")
        return ProjectFELStatusOut.model_validate(record).model_copy(update={"allowed_actions": actions})

    @staticmethod
    def _assessment_out(record: ProjectDefinitionAssessment) -> AssessmentOut:
        actions = ["can_view_project_definition"]
        if record.status in {"DRAFT", "IN_PROGRESS"}:
            actions.extend(["can_edit_assessment", "can_complete_assessment"])
        if record.status == "COMPLETED":
            actions.append("can_start_reevaluation")
        return AssessmentOut.model_validate(record).model_copy(
            update={
                "category_results": deepcopy(record.category_results_json or []),
                "element_results": deepcopy(record.element_results_json or []),
                "blocking_items": deepcopy(record.blocking_items_json or []),
                "warnings": list(record.warnings_json or []),
                "actions_summary": deepcopy(record.actions_summary_json or {}),
                "evidence_refs": deepcopy(record.evidence_refs_json or []),
                "source_snapshot": deepcopy(record.source_snapshot_json or {}),
                "allowed_actions": actions,
            }
        )

    @staticmethod
    def _action_out(record: ProjectDefinitionAction) -> DefinitionActionOut:
        return DefinitionActionOut.model_validate(record).model_copy(
            update={
                "evidence_refs": deepcopy(record.evidence_refs_json or []),
                "audit": deepcopy(record.audit_json or []),
            }
        )

    @staticmethod
    def _assessment_hash_payload(record: ProjectDefinitionAssessment) -> dict[str, Any]:
        return {
            "project_workspace_id": record.project_workspace_id,
            "version": record.assessment_version,
            "framework_hash": record.framework_hash,
            "FEL_stage": record.fel_stage_code,
            "source_hash": record.definition_source_hash,
            "element_results": record.element_results_json,
            "category_results": record.category_results_json,
            "score": record.raw_score,
            "maturity": record.maturity_level,
            "threshold_status": record.threshold_status,
            "blocking_items": record.blocking_items_json,
            "evidence_refs": record.evidence_refs_json,
        }

    @staticmethod
    def _project_summary(project: EnterpriseWorkspace) -> dict[str, Any]:
        context = dict(dict(project.defaults_json or {}).get("_project", {}))
        return {
            "id": project.id,
            "code": project.code,
            "name": project.name,
            "status": project.status,
            "project_type": context.get("project_type"),
            "governance_model": ProjectDefinitionService._governance_model(project),
        }

    @staticmethod
    def _project_type(project: EnterpriseWorkspace | None) -> str | None:
        if project is None:
            return None
        return str(dict(dict(project.defaults_json or {}).get("_project", {})).get("project_type") or "OTHER")

    @staticmethod
    def _governance_model(project: EnterpriseWorkspace | None) -> str:
        if project is None:
            return "CAPITAL_OWNER"
        context = dict(dict(project.defaults_json or {}).get("_project", {}))
        value = str(context.get("governance_model") or "").upper()
        if not value and context.get("planning_origin") == "STRATEGIC_GATE":
            return "CAPITAL_OWNER"
        return value or "LEGACY"

    def _assert_governance_applicability(self, project: EnterpriseWorkspace, content: dict[str, Any]) -> None:
        governance = self._governance_model(project)
        if governance not in set(content.get("applicable_governance_models", [])):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PROJECT_DEFINITION_CAPABILITY_NOT_APPLICABLE",
                    "governance_model": governance,
                    "contractor_delivery_required": False,
                    "direct_internal_required": False,
                },
            )

    @staticmethod
    def _stages(content: dict[str, Any]) -> list[dict[str, Any]]:
        return sorted(content.get("stage_structure", []), key=lambda item: int(item.get("sequence", 0)))

    def _stage(self, content: dict[str, Any], stage_code: str) -> dict[str, Any]:
        stage = next((item for item in self._stages(content) if item.get("stage_code") == stage_code), None)
        if stage is None:
            raise HTTPException(status_code=422, detail={"code": "INVALID_FEL_STAGE"})
        return stage

    @staticmethod
    def _elements(content: dict[str, Any], stage_code: str) -> list[dict[str, Any]]:
        return [
            deepcopy(item)
            for item in content.get("assessment_elements", [])
            if not item.get("stages") or stage_code in item.get("stages", [])
        ]

    @staticmethod
    def _framework_summary(record: AdminConfiguration | None) -> dict[str, Any]:
        if record is None:
            return {}
        content = record.content_json or {}
        return {
            "id": record.id,
            "code": record.code,
            "name": record.name,
            "status": record.status,
            "revision": record.revision,
            "version": record.version,
            "content_hash": record.content_hash,
            "framework_code": content.get("framework_code"),
            "framework_type": content.get("framework_type"),
            "framework_version": content.get("framework_version"),
        }

    def _resolution_chain(
        self, project: EnterpriseWorkspace | None, record: AdminConfiguration | None
    ) -> list[dict[str, Any]]:
        chain = [
            {"workspace_id": item.id, "workspace_type": item.workspace_type_code, "code": item.code}
            for item in self._workspace_path(project)
        ]
        if record:
            chain.append({"configuration_id": record.id, "revision": record.revision, "hash": record.content_hash})
        return chain

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

    def _not_started_readiness(self, project_id: int) -> DefinitionReadinessOut:
        return DefinitionReadinessOut(
            status="NOT_STARTED",
            tenant_id=self.tenant_id,
            project_workspace_id=project_id,
            current_FEL_stage=None,
            latest_completed_assessment_id=None,
            framework_code=None,
            framework_version=None,
            assessment_hash=None,
            maturity_level=None,
            threshold_status="NOT_EVALUATED",
            required_maturity=None,
            required_stage=None,
            required_maturity_met=False,
            blocking_item_count=0,
            open_blocking_action_count=0,
            evidence_coverage=0,
            warnings=[],
            blockers=["FEL_NOT_STARTED"],
            definition_readiness_hash=_hash({"project_workspace_id": project_id, "status": "NOT_STARTED"}),
            source_current=True,
            can_supply_investment_gate_evidence=False,
        )

    @staticmethod
    def _boundaries() -> dict[str, bool]:
        return {
            "investment_decision_created": False,
            "fid_created": False,
            "funds_created": False,
            "project_initialized": False,
            "project_activated": False,
            "operational_schedule_created": False,
            "can_supply_investment_gate_evidence": True,
        }

    def _assert_scope(self, workspace_id: int) -> None:
        if self.context is None or self.context.organization_wide:
            return
        if workspace_id not in self.context.workspace_ids:
            raise HTTPException(status_code=403, detail="Workspace is outside the authorized scope")

    @staticmethod
    def _check_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise HTTPException(status_code=412, detail={"code": "ETAG_MISMATCH", "current_version": actual})

    def _touch_status(self, record: ProjectFELStatus) -> None:
        record.updated_by = self.actor_id
        record.updated_at = utc_now()
        record.revision_version += 1

    def _event(self, event_type: str, target_type: str, target_id: int | None, metadata: dict[str, Any]) -> None:
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
