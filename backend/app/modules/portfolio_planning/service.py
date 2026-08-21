"""Gate 07D Strategic Project Planning Entry application service.

The service bridges an immutable Gate 07C APPROVE decision to the existing
Gate 05B ProjectCreationRequest. It never creates a second Project identity,
never activates a Project, and never performs Portfolio or FEL scoring.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent, UserAccount
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.enterprise_structure.project_configuration import (
    PROJECT_NUMBERING_CODE,
    ProjectWorkspaceConfigurationService,
)
from app.modules.enterprise_structure.record_codes import next_record_code
from app.modules.portfolio_planning.models import PortfolioProjectMembership
from app.modules.portfolio_planning.schemas import (
    PortfolioMembershipCreateIn,
    PortfolioMembershipOut,
    PortfolioPlanningConfigurationPreviewOut,
    PortfolioProjectRegisterOut,
    ReadinessOut,
    StrategicPlanningCreateIn,
    StrategicPlanningEntryOut,
    StrategicPlanningPreviewOut,
)
from app.modules.project_creation.models import ProjectCreationRequest
from app.modules.project_creation.schemas import ProjectRequestCreate
from app.modules.project_creation.service import ProjectCreationService
from app.modules.project_proposal.models import ProjectProposal
from app.modules.strategic_gate.models import StrategicGateDecision
from app.modules.strategic_gate.service import StrategicGateService

CONFIGURATION_KIND = "portfolio_planning_configuration"
SOURCE_CONTEXT = "STRATEGIC_GATE_DECISION"
FINAL_READY_STATUS = "READY_FOR_PORTFOLIO_PLANNING"
REWORK_STATUS = "GATE07D_REWORK_REQUIRED"

DEFAULT_CONFIGURATION: dict[str, Any] = {
    "workspace_id": None,
    "inherit_to_descendants": True,
    "membership_policy": "STRATEGIC_INTAKE_ONLY",
    "membership_sources": ["STRATEGIC_INTAKE", "RULE_BASED", "MANUAL"],
    "eligible_project_statuses": ["pending"],
    "target_portfolio_required": True,
    "project_manager_required": True,
    "strategic_objective_required": True,
    "mapping": {
        "name": "proposal.name",
        "business_need": "proposal.business_need",
        "preliminary_scope": "proposal.preliminary_scope",
        "expected_benefits": "proposal.expected_benefits",
        "rom_cost": "proposal.rom_cost",
        "target_start": "proposal.target_start_date",
        "target_finish": "proposal.target_finish_date",
        "strategic_objectives": "proposal.strategic_objective_codes",
        "sponsor": "proposal.sponsor_user_id",
        "strategic_conditions": "strategic_gate_decision.conditions",
    },
    "template_recommendations": {},
    "project_type_mapping": {},
    "definition_framework_recommendations": {
        "industrial": "PDRI_INDUSTRIAL_REFERENCE",
        "mining": "PDRI_INDUSTRIAL_REFERENCE",
        "processing": "PDRI_INDUSTRIAL_REFERENCE",
        "infrastructure": "PDRI_INFRASTRUCTURE_REFERENCE",
        "roads": "PDRI_INFRASTRUCTURE_REFERENCE",
        "water": "PDRI_INFRASTRUCTURE_REFERENCE",
        "building": "PDRI_BUILDING_REFERENCE",
        "small-industrial": "SMALL_INDUSTRIAL_PDRI_REFERENCE",
    },
    "portfolio_evaluation_requirements": {
        "strategic_objectives": True,
        "proposal_score": True,
        "rom_cost": False,
        "expected_benefits": False,
        "risk_summary": False,
        "target_dates": False,
    },
    "project_definition_requirements": {
        "project_type": True,
        "project_parent": True,
        "template": True,
        "strategic_context": True,
        "business_need": True,
        "preliminary_scope": True,
        "rom_cost": False,
        "target_dates": False,
        "risk_summary": False,
        "sponsor": True,
        "project_manager": True,
    },
    "membership_filters": {
        "fields": [
            "project_type",
            "strategic_objective",
            "business_unit",
            "region",
            "status",
            "project_phase",
            "rom_cost",
            "sponsor",
            "classification",
        ],
        "operators": ["EQ", "NE", "IN", "NOT_IN", "GT", "GTE", "LT", "LTE"],
    },
}


class PortfolioPlanningService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int, context) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.context = context

    def ensure_seed(self) -> None:
        if self._latest_configuration("default") is None:
            self.db.add(
                AdminConfiguration(
                    tenant_id=self.tenant_id,
                    kind=CONFIGURATION_KIND,
                    code="default",
                    name="Default Portfolio Planning Entry",
                    description="Gate 07D governed stage-entry mapping and membership policy.",
                    status="published",
                    revision=1,
                    version=1,
                    content_json=DEFAULT_CONFIGURATION,
                    content_hash=_hash(DEFAULT_CONFIGURATION),
                    published_at=utc_now(),
                    created_by_user_id=self.actor_id,
                )
            )
        ProjectCreationService(self.db, self.tenant_id, self.actor_id).ensure_seed()
        self.db.commit()

    def eligible_decisions(self) -> list[dict]:
        statement = select(StrategicGateDecision).where(
            StrategicGateDecision.tenant_id == self.tenant_id,
            StrategicGateDecision.state == "DECIDED",
            StrategicGateDecision.outcome == "APPROVE",
        )
        if self.context is not None and not self.context.organization_wide:
            allowed = list(self.context.workspace_ids)
            statement = statement.where(
                StrategicGateDecision.owning_workspace_id.in_(allowed or [-1])
                | StrategicGateDecision.target_portfolio_workspace_id.in_(allowed or [-1])
            )
        rows = self.db.scalars(statement.order_by(StrategicGateDecision.decided_at.desc())).all()
        result = []
        for decision in rows:
            existing = self._request_for_decision(decision.id)
            result.append(
                {
                    "id": decision.id,
                    "decision_number": decision.decision_number,
                    "project_proposal_id": decision.project_proposal_id,
                    "project_name": str(decision.proposal_snapshot_json.get("name", "")),
                    "target_portfolio_workspace_id": decision.target_portfolio_workspace_id,
                    "project_creation_request_id": existing.id if existing else None,
                    "project_creation_request_state": existing.state if existing else None,
                    "can_create": existing is None and decision.target_portfolio_workspace_id is not None,
                }
            )
        return result

    def portfolio_options(self) -> list[dict]:
        rows = self.db.scalars(
            select(EnterpriseWorkspace)
            .where(
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.workspace_type_code == "portfolio",
                EnterpriseWorkspace.status == "active",
            )
            .order_by(EnterpriseWorkspace.record_code)
        ).all()
        return [self._workspace_summary(item) for item in rows]

    def preview(self, decision_id: int) -> StrategicPlanningPreviewOut:
        decision, proposal, intake = self._validated_input(decision_id)
        configuration, source, _path, record = self._effective_configuration(
            self._workspace(decision.owning_workspace_id)
        )
        target = (
            self._workspace(decision.target_portfolio_workspace_id) if decision.target_portfolio_workspace_id else None
        )
        creation = ProjectCreationService(self.db, self.tenant_id, self.actor_id)
        options = creation.options(target.id if target else None)
        parents = [item.model_dump() for item in options.locations]
        default_parent = next((item for item in parents if target and item["id"] == target.id), None)
        templates = [item.model_dump() for item in options.templates]
        suggested_type = self._suggested_project_type(proposal, configuration)
        suggested_template = self._suggested_template(suggested_type, templates, configuration)
        manager = self._suggested_manager(proposal, options.managers)
        mapped = self._mapped_values(decision, proposal)
        source_snapshot = self._source_snapshot(decision, proposal, intake, record, configuration, mapped)
        project_probe = {
            "project_type": suggested_type,
            "parent_workspace_id": default_parent.get("id") if default_parent else None,
            "template_id": suggested_template.get("id") if suggested_template else None,
            "project_manager_user_id": manager.get("id") if manager else None,
        }
        portfolio_readiness = self._portfolio_readiness(source_snapshot, False, configuration)
        definition_readiness = self._definition_readiness(source_snapshot, project_probe, configuration)
        blockers = []
        if target is None or target.workspace_type_code != "portfolio" or target.status != "active":
            blockers.append("TARGET_PORTFOLIO_REQUIRED")
        if not parents:
            blockers.append("NO_ALLOWED_PROJECT_PARENT")
        if not templates:
            blockers.append("NO_PUBLISHED_PROJECT_TEMPLATE")
        if not options.managers:
            blockers.append("PROJECT_MANAGER_REQUIRED")
        existing = self._request_for_decision(decision.id)
        if existing is not None:
            blockers.append("STRATEGIC_PLANNING_ENTRY_ALREADY_EXISTS")
        record_preview = self._record_code_preview(default_parent)
        return StrategicPlanningPreviewOut(
            decision=self._decision_summary(decision),
            proposal=self._proposal_summary(proposal),
            source_idea=dict(decision.source_idea_snapshot_json or {}),
            target_portfolio=self._workspace_summary(target) if target else None,
            project_name=proposal.name,
            project_number_preview=self._project_number_preview(),
            record_code_preview=record_preview,
            allowed_project_parents=parents,
            default_project_parent=default_parent,
            strategic_objectives=list(decision.strategic_objectives_snapshot_json or []),
            suggested_project_type=suggested_type,
            suggested_template=suggested_template,
            template_options=templates,
            project_manager_required=bool(configuration.get("project_manager_required", True)),
            project_manager_candidate=manager,
            project_manager_options=[item.model_dump() for item in options.managers],
            mapped_fields=mapped,
            portfolio_planning_entry_preview={
                "planning_origin": "STRATEGIC_GATE",
                "planning_stage": "PORTFOLIO_AND_FEL_PLANNING",
                "workspace_status": "pending",
                "target_portfolio_workspace_id": decision.target_portfolio_workspace_id,
                "source_snapshot_hash": _hash(source_snapshot),
            },
            portfolio_evaluation_readiness_preview=portfolio_readiness,
            project_definition_readiness_preview=definition_readiness,
            creation_policy={
                "project_creation_process": "GATE_05B",
                "initial_workspace_status": "pending",
                "initialization": False,
                "activation": False,
                "four_eyes_preserved": True,
            },
            source_decision_hash=decision.decision_hash,
            source_readiness_hash=intake.readiness_hash,
            configuration=source,
            blocking_issues=sorted(set(blockers)),
            warnings=["APPROVE authorizes planning and definition only; it is not FID or execution authorization."],
            persisted=False,
        )

    def create(self, payload: StrategicPlanningCreateIn) -> StrategicPlanningEntryOut:
        decision, proposal, intake = self._validated_input(payload.strategic_gate_decision_id)
        if (
            payload.expected_decision_hash != decision.decision_hash
            or payload.expected_readiness_hash != intake.readiness_hash
        ):
            raise HTTPException(
                status_code=412,
                detail={"code": "STALE_STRATEGIC_SOURCE", "message": "Refresh the Gate 07D preview."},
            )
        existing = self._request_for_decision(decision.id)
        if existing is not None:
            return self.entry(decision.id)
        configuration, _source, _path, record = self._effective_configuration(
            self._workspace(decision.owning_workspace_id)
        )
        mapped = self._mapped_values(decision, proposal)
        source_snapshot = self._source_snapshot(decision, proposal, intake, record, configuration, mapped)
        project_payload = ProjectRequestCreate(
            parent_workspace_id=payload.project_parent_workspace_id,
            project_template_config_id=payload.project_template_config_id,
            project_name=proposal.name,
            description=proposal.business_need,
            project_manager_user_id=payload.project_manager_user_id,
            planned_start=proposal.target_start_date,
            planned_finish=proposal.target_finish_date,
            currency_code=proposal.currency_code,
            estimated_budget=proposal.rom_cost,
            project_type=payload.project_type,
            project_phase=payload.project_phase,
            priority=payload.priority,
            country=payload.country,
            region=payload.region,
            strategic_objective_codes=[
                str(item.get("code", ""))
                for item in decision.strategic_objectives_snapshot_json or []
                if item.get("code")
            ],
        )
        try:
            request = ProjectCreationService(self.db, self.tenant_id, self.actor_id).create_request(
                project_payload,
                strategic_source={
                    "source_context_type": SOURCE_CONTEXT,
                    "strategic_gate_decision_id": decision.id,
                    "source_project_proposal_id": decision.project_proposal_id,
                    "source_idea_id": decision.source_idea_id,
                    "source_decision_hash": decision.decision_hash,
                    "source_readiness_hash": intake.readiness_hash,
                    "strategic_target_portfolio_workspace_id": decision.target_portfolio_workspace_id,
                    "strategic_mapping_configuration_id": record.id,
                    "strategic_mapping_revision": record.revision,
                    "strategic_mapping_hash": record.content_hash,
                    "strategic_source_snapshot_json": source_snapshot,
                },
            )
        except IntegrityError as exc:
            self.db.rollback()
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint_name != "uq_project_creation_strategic_decision":
                raise
            # A concurrent transaction won the same immutable Gate 07C
            # decision. Re-read and return the authoritative Gate 05B request;
            # the losing number reservation was rolled back atomically.
            if self._request_for_decision(decision.id) is None:
                raise
            return self.entry(decision.id)
        self._event(
            "strategic_project_planning.request_created",
            "project_creation_request",
            request.id,
            {"strategic_gate_decision_id": decision.id, "request_number": request.request_number},
        )
        self._event(
            "strategic_project_planning.request_linked",
            "StrategicGateDecision",
            decision.id,
            {"project_creation_request_id": request.id},
        )
        self.db.commit()
        return self.entry(decision.id)

    def entry(self, decision_id: int) -> StrategicPlanningEntryOut:
        decision = self._decision(decision_id)
        proposal = self._proposal(decision.project_proposal_id)
        request = self._request_for_decision(decision.id)
        workspace = (
            self._workspace(request.materialized_workspace_id)
            if request and request.materialized_workspace_id
            else None
        )
        memberships = self.project_memberships(workspace.id) if workspace else []
        configuration, _source, _path, _record = self._effective_configuration(
            self._workspace(decision.owning_workspace_id)
        )
        source_snapshot = dict(request.strategic_source_snapshot_json or {}) if request else {}
        planning = dict((workspace.defaults_json or {}).get("_portfolio_planning", {})) if workspace else {}
        active_target = any(item.status == "ACTIVE" and item.is_target_portfolio for item in memberships)
        portfolio_readiness = self._portfolio_readiness(source_snapshot, active_target, configuration)
        project_probe = {
            "project_type": request.project_type if request else None,
            "parent_workspace_id": request.parent_workspace_id if request else None,
            "template_id": request.project_template_config_id if request else None,
            "project_manager_user_id": request.project_manager_user_id if request else None,
        }
        definition_readiness = self._definition_readiness(source_snapshot, project_probe, configuration)
        blockers = []
        if request is None:
            blockers.append("PROJECT_CREATION_REQUEST_NOT_CREATED")
        elif request.state != "created":
            blockers.append("PROJECT_CREATION_REQUEST_NOT_CREATED_STATE")
        if workspace is None:
            blockers.append("PROJECT_WORKSPACE_NOT_MATERIALIZED")
        elif workspace.status != "pending":
            blockers.append("PROJECT_WORKSPACE_MUST_REMAIN_PENDING")
        if not active_target:
            blockers.append("ACTIVE_TARGET_PORTFOLIO_MEMBERSHIP_REQUIRED")
        blockers.extend(portfolio_readiness.blocking_issues)
        blockers.extend(definition_readiness.blocking_issues)
        ready = not blockers
        return StrategicPlanningEntryOut(
            status=FINAL_READY_STATUS if ready else REWORK_STATUS,
            can_enter_portfolio_evaluation=ready and portfolio_readiness.can_enter,
            can_enter_project_definition=ready and definition_readiness.can_enter,
            decision=self._decision_summary(decision),
            proposal=self._proposal_summary(proposal),
            source_idea=dict(decision.source_idea_snapshot_json or {}),
            target_portfolio=(
                self._workspace_summary(self._workspace(decision.target_portfolio_workspace_id))
                if decision.target_portfolio_workspace_id
                else None
            ),
            project_creation_request=(
                ProjectCreationService(self.db, self.tenant_id, self.actor_id)._out(request) if request else None
            ),
            project_workspace=self._workspace_summary(workspace) if workspace else None,
            portfolio_memberships=memberships,
            planning_entry_snapshot=dict(planning.get("snapshot", {})),
            planning_entry_hash=planning.get("planning_entry_hash"),
            portfolio_evaluation_readiness=portfolio_readiness,
            project_definition_readiness=definition_readiness,
            allowed_actions=self._allowed_actions(request, workspace, portfolio_readiness, definition_readiness),
            blocking_issues=sorted(set(blockers)),
            warnings=[
                "PROJECT PENDING is authorized for planning and definition, not execution.",
                "Portfolio Evaluation and PDRI/FEL scoring are outside Gate 07D.",
            ],
        )

    def finalize_materialization(
        self,
        request: ProjectCreationRequest,
        workspace: EnterpriseWorkspace,
    ) -> str:
        decision, _proposal, intake = self._validated_input(request.strategic_gate_decision_id or 0)
        if (
            request.source_decision_hash != decision.decision_hash
            or request.source_readiness_hash != intake.readiness_hash
        ):
            raise HTTPException(
                status_code=412,
                detail={"code": "STALE_STRATEGIC_SOURCE", "message": "Strategic source hashes changed."},
            )
        if workspace.status != "pending":
            raise HTTPException(status_code=409, detail="STRATEGIC_PROJECT_MUST_BE_PENDING")
        target = self._workspace(request.strategic_target_portfolio_workspace_id)
        if target.workspace_type_code != "portfolio" or target.status != "active":
            raise HTTPException(status_code=422, detail="INVALID_TARGET_PORTFOLIO")
        membership = self._active_membership(target.id, workspace.id)
        if membership is None:
            membership = PortfolioProjectMembership(
                tenant_id=self.tenant_id,
                portfolio_workspace_id=target.id,
                project_workspace_id=workspace.id,
                membership_source="STRATEGIC_INTAKE",
                source_strategic_gate_decision_id=decision.id,
                source_project_proposal_id=decision.project_proposal_id,
                is_target_portfolio=True,
                status="ACTIVE",
                effective_from=utc_now(),
                revision_version=1,
                created_by=self.actor_id,
                updated_by=self.actor_id,
            )
            self.db.add(membership)
            self.db.flush()
            self._event(
                "portfolio_membership.created",
                "portfolio_project_membership",
                membership.id,
                {"source": "STRATEGIC_INTAKE", "is_target_portfolio": True},
            )
        source = dict(request.strategic_source_snapshot_json or {})
        snapshot = self._planning_entry_snapshot(request, workspace, target, membership, source)
        planning_hash = _hash(snapshot)
        configuration, _source, _path, _record = self._effective_configuration(
            self._workspace(decision.owning_workspace_id)
        )
        portfolio_readiness = self._portfolio_readiness(source, True, configuration)
        definition_readiness = self._definition_readiness(
            source,
            {
                "project_type": request.project_type,
                "parent_workspace_id": request.parent_workspace_id,
                "template_id": request.project_template_config_id,
                "project_manager_user_id": request.project_manager_user_id,
            },
            configuration,
        )
        final_status = (
            FINAL_READY_STATUS if portfolio_readiness.can_enter and definition_readiness.can_enter else REWORK_STATUS
        )
        defaults = dict(workspace.defaults_json or {})
        project_metadata = dict(defaults.get("_project", {}))
        project_metadata.update(
            {
                "planning_origin": "STRATEGIC_GATE",
                "planning_stage": "PORTFOLIO_AND_FEL_PLANNING",
                "strategic_business_need": source.get("source_values", {}).get("business_need", ""),
                "preliminary_scope": source.get("source_values", {}).get("preliminary_scope", ""),
                "expected_benefits": source.get("source_values", {}).get("expected_benefits", ""),
                "risk_summary": source.get("source_values", {}).get("risk_summary", []),
                "sponsor_user_id": source.get("source_values", {}).get("sponsor_user_id"),
                "strategic_conditions": source.get("source_values", {}).get("strategic_conditions", []),
            }
        )
        defaults["_project"] = project_metadata
        defaults["_portfolio_planning"] = {
            "status": final_status,
            "snapshot": snapshot,
            "planning_entry_hash": planning_hash,
            "blocking_issues": sorted(set(portfolio_readiness.blocking_issues + definition_readiness.blocking_issues)),
            "updated_at": utc_now().isoformat(),
        }
        workspace.defaults_json = defaults
        workspace.version += 1
        workspace.updated_at = utc_now()
        self._event(
            "strategic_project_planning.project_materialized",
            "project_creation_request",
            request.id,
            {"workspace_id": workspace.id, "membership_id": membership.id},
        )
        if final_status == FINAL_READY_STATUS:
            self._event(
                "portfolio_planning.entry_ready",
                "enterprise_workspace",
                workspace.id,
                {"planning_entry_hash": planning_hash},
            )
            self._event(
                "portfolio_project.ready_for_planning",
                "enterprise_workspace",
                workspace.id,
                {"status": FINAL_READY_STATUS},
            )
            self._event("portfolio_project.ready_for_evaluation", "enterprise_workspace", workspace.id, {})
            self._event("project_definition.ready", "enterprise_workspace", workspace.id, {})
        else:
            self._event(
                "portfolio_planning.entry_rework_required",
                "enterprise_workspace",
                workspace.id,
                {
                    "status": REWORK_STATUS,
                    "blocking_issues": defaults["_portfolio_planning"]["blocking_issues"],
                },
            )
        return final_status

    def project_memberships(self, project_id: int) -> list[PortfolioMembershipOut]:
        project = self._workspace(project_id)
        if project.workspace_type_code != "project":
            raise HTTPException(status_code=422, detail="WORKSPACE_IS_NOT_PROJECT")
        rows = self.db.scalars(
            select(PortfolioProjectMembership)
            .where(
                PortfolioProjectMembership.tenant_id == self.tenant_id,
                PortfolioProjectMembership.project_workspace_id == project.id,
            )
            .order_by(PortfolioProjectMembership.is_target_portfolio.desc(), PortfolioProjectMembership.created_at)
        ).all()
        return [self._membership_out(item) for item in rows]

    def create_membership(
        self,
        project_id: int,
        payload: PortfolioMembershipCreateIn,
        expected_workspace_version: int,
    ) -> PortfolioMembershipOut:
        project = self._workspace(project_id, lock=True)
        if project.workspace_type_code != "project" or project.status != "pending":
            raise HTTPException(status_code=422, detail="PROJECT_NOT_ELIGIBLE_FOR_PORTFOLIO_MEMBERSHIP")
        if project.version != expected_workspace_version:
            raise HTTPException(status_code=412, detail={"code": "ETAG_MISMATCH"})
        portfolio = self._workspace(payload.portfolio_workspace_id)
        if portfolio.workspace_type_code != "portfolio" or portfolio.status != "active":
            raise HTTPException(status_code=422, detail="INVALID_PORTFOLIO_WORKSPACE")
        existing = self._active_membership(portfolio.id, project.id)
        if existing is not None:
            return self._membership_out(existing)
        membership = PortfolioProjectMembership(
            tenant_id=self.tenant_id,
            portfolio_workspace_id=portfolio.id,
            project_workspace_id=project.id,
            membership_source=payload.membership_source,
            is_target_portfolio=False,
            status="ACTIVE",
            effective_from=utc_now(),
            revision_version=1,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(membership)
        self.db.flush()
        self._event(
            "portfolio_membership.created",
            "portfolio_project_membership",
            membership.id,
            {"source": payload.membership_source, "is_target_portfolio": False},
        )
        self.db.commit()
        self.db.refresh(membership)
        return self._membership_out(membership)

    def remove_membership(self, project_id: int, membership_id: int, expected_version: int) -> PortfolioMembershipOut:
        self._workspace(project_id)
        membership = self.db.scalar(
            select(PortfolioProjectMembership)
            .where(
                PortfolioProjectMembership.id == membership_id,
                PortfolioProjectMembership.tenant_id == self.tenant_id,
                PortfolioProjectMembership.project_workspace_id == project_id,
            )
            .with_for_update()
        )
        if membership is None:
            raise HTTPException(status_code=404, detail="Portfolio membership not found")
        if membership.revision_version != expected_version:
            raise HTTPException(status_code=412, detail={"code": "ETAG_MISMATCH"})
        if membership.is_target_portfolio and membership.membership_source == "STRATEGIC_INTAKE":
            raise HTTPException(status_code=409, detail="STRATEGIC_TARGET_MEMBERSHIP_CANNOT_BE_REMOVED")
        if membership.status != "ACTIVE":
            return self._membership_out(membership)
        membership.status = "INACTIVE"
        membership.effective_to = utc_now()
        membership.updated_by = self.actor_id
        membership.updated_at = utc_now()
        membership.revision_version += 1
        self._event("portfolio_membership.removed", "portfolio_project_membership", membership.id, {})
        self.db.commit()
        self.db.refresh(membership)
        return self._membership_out(membership)

    def portfolio_projects(self, portfolio_id: int) -> list[PortfolioProjectRegisterOut]:
        portfolio = self._workspace(portfolio_id)
        if portfolio.workspace_type_code != "portfolio":
            raise HTTPException(status_code=422, detail="WORKSPACE_IS_NOT_PORTFOLIO")
        memberships = self.db.scalars(
            select(PortfolioProjectMembership)
            .where(
                PortfolioProjectMembership.tenant_id == self.tenant_id,
                PortfolioProjectMembership.portfolio_workspace_id == portfolio.id,
                PortfolioProjectMembership.status == "ACTIVE",
            )
            .order_by(PortfolioProjectMembership.created_at.desc())
        ).all()
        result = []
        for membership in memberships:
            project = self._workspace(membership.project_workspace_id)
            request = self.db.scalar(
                select(ProjectCreationRequest).where(
                    ProjectCreationRequest.tenant_id == self.tenant_id,
                    ProjectCreationRequest.materialized_workspace_id == project.id,
                )
            )
            if request is None:
                continue
            entry = self.entry(request.strategic_gate_decision_id) if request.strategic_gate_decision_id else None
            source = dict(request.strategic_source_snapshot_json or {})
            values = dict(source.get("source_values", {}))
            result.append(
                PortfolioProjectRegisterOut(
                    project_workspace_id=project.id,
                    project_number=project.code,
                    project_name=project.name,
                    workspace_status=project.status,
                    planning_stage=str((project.defaults_json or {}).get("_project", {}).get("planning_stage", "")),
                    membership=self._membership_out(membership),
                    strategic_gate_decision_id=request.strategic_gate_decision_id,
                    decision_number=source.get("decision", {}).get("decision_number"),
                    project_proposal_id=request.source_project_proposal_id,
                    proposal_number=source.get("proposal", {}).get("proposal_number"),
                    source_idea_id=request.source_idea_id,
                    proposal_score=_decimal(values.get("proposal_score")),
                    strategic_objectives=list(values.get("strategic_objectives", [])),
                    rom_cost=values.get("rom_cost"),
                    target_start=_date(values.get("target_start")),
                    target_finish=_date(values.get("target_finish")),
                    expected_benefits=str(values.get("expected_benefits", "")),
                    risk_summary=list(values.get("risk_summary", [])),
                    sponsor_user_id=values.get("sponsor_user_id"),
                    project_manager_user_id=request.project_manager_user_id,
                    portfolio_evaluation_readiness=(
                        entry.portfolio_evaluation_readiness
                        if entry
                        else self._empty_readiness("PROJECT_NOT_STRATEGIC")
                    ),
                    project_definition_readiness=(
                        entry.project_definition_readiness if entry else self._empty_readiness("PROJECT_NOT_STRATEGIC")
                    ),
                )
            )
        return result

    def project_readiness(self, project_id: int) -> StrategicPlanningEntryOut:
        request = self.db.scalar(
            select(ProjectCreationRequest).where(
                ProjectCreationRequest.tenant_id == self.tenant_id,
                ProjectCreationRequest.materialized_workspace_id == project_id,
                ProjectCreationRequest.source_context_type == SOURCE_CONTEXT,
            )
        )
        if request is None or request.strategic_gate_decision_id is None:
            raise HTTPException(status_code=404, detail="Strategic planning entry not found")
        return self.entry(request.strategic_gate_decision_id)

    def configurations(self) -> list[AdminConfiguration]:
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

    def configuration_preview(self, workspace_id: int) -> PortfolioPlanningConfigurationPreviewOut:
        effective, source, path, _record = self._effective_configuration(self._workspace(workspace_id))
        return PortfolioPlanningConfigurationPreviewOut(
            workspace_id=workspace_id,
            path=[self._workspace_summary(item) for item in path],
            effective=effective,
            source=source,
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id)
        self._check_config_version(source, expected_version)
        if source.status != "published":
            raise HTTPException(status_code=409, detail="Only published configuration can be cloned")
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
            name=source.name,
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=json.loads(json.dumps(source.content_json)),
            content_hash="",
            created_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._event("portfolio_planning.configuration_cloned", "AdminConfiguration", clone.id, {})
        self.db.commit()
        self.db.refresh(clone)
        return clone

    def update_configuration(
        self,
        configuration_id: int,
        expected_version: int,
        name: str,
        description: str,
        content: dict,
    ) -> AdminConfiguration:
        record = self._configuration(configuration_id)
        self._check_config_version(record, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail="Published configuration is immutable")
        self._validate_configuration(content)
        record.name = name.strip()
        record.description = description.strip()
        record.content_json = content
        record.content_hash = _hash(content)
        record.version += 1
        record.updated_at = utc_now()
        self._event("portfolio_planning.configuration_updated", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id)
        self._check_config_version(record, expected_version)
        if record.status == "published":
            return record
        self._validate_configuration(record.content_json)
        record.status = "published"
        record.content_hash = _hash(record.content_json)
        record.version += 1
        record.published_at = utc_now()
        record.updated_at = utc_now()
        self._event("portfolio_planning.configuration_published", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def _validated_input(self, decision_id: int):
        decision = self._decision(decision_id)
        gate_context = self.context
        if gate_context is None:
            actor = self.db.scalar(
                select(UserAccount).where(
                    UserAccount.id == self.actor_id,
                    UserAccount.tenant_id == self.tenant_id,
                    UserAccount.status == "active",
                )
            )
            if actor is None:
                raise HTTPException(status_code=404, detail="User not found")
            # Internal materialization hook: Gate 05B has already authorized the
            # actor, while Gate 07C still requires a concrete access context.
            gate_context = EnterprisePermissionContext(
                user=actor,
                organization_wide=True,
                scope_unit_ids=frozenset(),
                workspace_ids=frozenset(),
                role_codes=frozenset({"project_materialization_service"}),
            )
        intake = StrategicGateService(
            self.db,
            self.tenant_id,
            self.actor_id,
            gate_context,
        ).portfolio_intake_readiness(decision.id)
        if (
            decision.state != "DECIDED"
            or decision.outcome != "APPROVE"
            or intake.status != "READY_FOR_PORTFOLIO_INTAKE"
        ):
            raise HTTPException(
                status_code=422,
                detail={"code": "STRATEGIC_DECISION_NOT_ELIGIBLE", "issues": intake.blockers},
            )
        proposal = self._proposal(decision.project_proposal_id)
        if decision.target_portfolio_workspace_id is None:
            raise HTTPException(status_code=422, detail="TARGET_PORTFOLIO_REQUIRED")
        target = self._workspace(decision.target_portfolio_workspace_id)
        if target.workspace_type_code != "portfolio" or target.status != "active":
            raise HTTPException(status_code=422, detail="INVALID_TARGET_PORTFOLIO")
        return decision, proposal, intake

    def _effective_configuration(self, workspace: EnterpriseWorkspace):
        selected = self._latest_configuration("default")
        if selected is None:
            raise HTTPException(status_code=409, detail="No published Portfolio Planning configuration")
        path = self._workspace_path(workspace)
        for item in path:
            candidate = self._latest_configuration(f"workspace-{item.id}")
            if candidate is not None and (
                item.id == workspace.id or candidate.content_json.get("inherit_to_descendants", True)
            ):
                selected = candidate
        source = {
            "configuration_id": selected.id,
            "code": selected.code,
            "revision": selected.revision,
            "hash": selected.content_hash,
            "source_workspace_id": selected.content_json.get("workspace_id"),
        }
        return dict(selected.content_json), source, path, selected

    def _latest_configuration(self, code: str) -> AdminConfiguration | None:
        return self.db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.code == code,
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
            .limit(1)
        )

    def _configuration(self, configuration_id: int) -> AdminConfiguration:
        record = self.db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.id == configuration_id,
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Portfolio Planning configuration not found")
        return record

    @staticmethod
    def _validate_configuration(content: dict) -> None:
        if content.get("membership_policy") not in {"STRATEGIC_INTAKE_ONLY", "RULE_BASED", "HYBRID"}:
            raise HTTPException(status_code=422, detail="Invalid membership policy")
        sources = set(content.get("membership_sources", []))
        if "STRATEGIC_INTAKE" not in sources:
            raise HTTPException(status_code=422, detail="STRATEGIC_INTAKE source is mandatory")
        filters = content.get("membership_filters", {})
        allowed_operators = {"EQ", "NE", "IN", "NOT_IN", "GT", "GTE", "LT", "LTE"}
        if not set(filters.get("operators", [])).issubset(allowed_operators):
            raise HTTPException(status_code=422, detail="Invalid membership filter operator")
        if "pdri_threshold" in content or "fel_score" in content:
            raise HTTPException(status_code=422, detail="Gate 07D cannot configure PDRI/FEL scoring")

    @staticmethod
    def _check_config_version(record: AdminConfiguration, expected: int) -> None:
        if record.version != expected:
            raise HTTPException(status_code=412, detail={"code": "ETAG_MISMATCH"})

    def _portfolio_readiness(self, source: dict, active_membership: bool, configuration: dict) -> ReadinessOut:
        values = dict(source.get("source_values", {}))
        required = ["active_portfolio_membership"]
        available = ["active_portfolio_membership"] if active_membership else []
        blockers = [] if active_membership else ["ACTIVE_PORTFOLIO_MEMBERSHIP_REQUIRED"]
        requirements = dict(configuration.get("portfolio_evaluation_requirements", {}))
        checks = {
            "strategic_objectives": values.get("strategic_objectives"),
            "proposal_score": values.get("proposal_score"),
            "rom_cost": values.get("rom_cost"),
            "expected_benefits": values.get("expected_benefits"),
            "risk_summary": values.get("risk_summary"),
            "target_dates": values.get("target_start") and values.get("target_finish"),
        }
        for field, is_required in requirements.items():
            if not is_required:
                continue
            required.append(field)
            if checks.get(field) not in (None, "", [], {}):
                available.append(field)
            else:
                blockers.append(f"PORTFOLIO_EVALUATION_{field.upper()}_REQUIRED")
        return ReadinessOut(
            status="READY" if not blockers else "BLOCKED",
            can_enter=not blockers,
            required_source_data=required,
            available_source_data=available,
            blocking_issues=blockers,
            warnings=["No Portfolio score or ranking is calculated by Gate 07D."],
        )

    def _definition_readiness(self, source: dict, project: dict, configuration: dict) -> ReadinessOut:
        values = dict(source.get("source_values", {}))
        requirements = dict(configuration.get("project_definition_requirements", {}))
        checks = {
            "project_type": project.get("project_type"),
            "project_parent": project.get("parent_workspace_id"),
            "template": project.get("template_id"),
            "strategic_context": source.get("decision"),
            "business_need": values.get("business_need"),
            "preliminary_scope": values.get("preliminary_scope"),
            "rom_cost": values.get("rom_cost"),
            "target_dates": values.get("target_start") and values.get("target_finish"),
            "risk_summary": values.get("risk_summary"),
            "sponsor": values.get("sponsor_user_id"),
            "project_manager": project.get("project_manager_user_id"),
        }
        required = []
        available = []
        blockers = []
        for field, is_required in requirements.items():
            if not is_required:
                continue
            required.append(field)
            if checks.get(field) not in (None, "", [], {}):
                available.append(field)
            else:
                blockers.append(f"PROJECT_DEFINITION_{field.upper()}_REQUIRED")
        project_type = str(project.get("project_type") or "") or None
        return ReadinessOut(
            status="READY" if not blockers else "BLOCKED",
            can_enter=not blockers,
            required_source_data=required,
            available_source_data=available,
            blocking_issues=blockers,
            warnings=["No PDRI or FEL assessment is executed by Gate 07D."],
            project_type=project_type,
            suggested_definition_framework=self._definition_framework(project_type, configuration),
        )

    @staticmethod
    def _empty_readiness(blocker: str) -> ReadinessOut:
        return ReadinessOut(
            status="BLOCKED",
            can_enter=False,
            required_source_data=[],
            available_source_data=[],
            blocking_issues=[blocker],
            warnings=[],
        )

    def _source_snapshot(
        self,
        decision: StrategicGateDecision,
        proposal: ProjectProposal,
        intake,
        record: AdminConfiguration,
        configuration: dict,
        mapped: dict,
    ) -> dict:
        source_values = {
            "business_need": proposal.business_need,
            "preliminary_scope": proposal.preliminary_scope,
            "expected_benefits": proposal.expected_benefits,
            "rom_cost": str(proposal.rom_cost) if proposal.rom_cost is not None else None,
            "currency_code": proposal.currency_code,
            "target_start": proposal.target_start_date.isoformat() if proposal.target_start_date else None,
            "target_finish": proposal.target_finish_date.isoformat() if proposal.target_finish_date else None,
            "risk_summary": list(proposal.key_risks_json or []),
            "strategic_objectives": list(decision.strategic_objectives_snapshot_json or []),
            "proposal_score": str(decision.proposal_score) if decision.proposal_score is not None else None,
            "sponsor_user_id": proposal.sponsor_user_id,
            "strategic_conditions": list(decision.conditions_json or []),
        }
        return {
            "decision": self._decision_summary(decision),
            "proposal": self._proposal_summary(proposal),
            "source_idea": dict(decision.source_idea_snapshot_json or {}),
            "gate07c_input_contract": {
                "accepted_idea_evaluation_id": decision.accepted_idea_evaluation_id,
                "proposal_evaluation_id": decision.proposal_evaluation_id,
                "owning_workspace_id": decision.owning_workspace_id,
                "target_portfolio_workspace_id": decision.target_portfolio_workspace_id,
                "decision_hash": decision.decision_hash,
                "readiness_hash": intake.readiness_hash,
            },
            "mapping_configuration": {
                "id": record.id,
                "revision": record.revision,
                "hash": record.content_hash,
                "snapshot": configuration,
            },
            "source_values": source_values,
            "mapped_values": mapped,
        }

    @staticmethod
    def _mapped_values(decision: StrategicGateDecision, proposal: ProjectProposal) -> dict:
        return {
            "project_name": proposal.name,
            "strategic_business_need": proposal.business_need,
            "preliminary_scope": proposal.preliminary_scope,
            "expected_benefits": proposal.expected_benefits,
            "estimated_budget": str(proposal.rom_cost) if proposal.rom_cost is not None else None,
            "planned_start": proposal.target_start_date.isoformat() if proposal.target_start_date else None,
            "planned_finish": proposal.target_finish_date.isoformat() if proposal.target_finish_date else None,
            "strategic_objective_codes": [
                str(item.get("code", "")) for item in decision.strategic_objectives_snapshot_json or []
            ],
            "sponsor_user_id": proposal.sponsor_user_id,
            "strategic_conditions": list(decision.conditions_json or []),
        }

    def _planning_entry_snapshot(
        self,
        request: ProjectCreationRequest,
        project: EnterpriseWorkspace,
        portfolio: EnterpriseWorkspace,
        membership: PortfolioProjectMembership,
        source: dict,
    ) -> dict:
        values = dict(source.get("source_values", {}))
        return {
            "project_workspace_id": project.id,
            "project_number": project.code,
            "project_name": project.name,
            "workspace_status": project.status,
            "planning_origin": "STRATEGIC_GATE",
            "planning_stage": "PORTFOLIO_AND_FEL_PLANNING",
            "strategic_gate_decision": source.get("decision", {}),
            "project_proposal": source.get("proposal", {}),
            "source_idea": source.get("source_idea", {}),
            "target_portfolio": self._workspace_summary(portfolio),
            "portfolio_membership_id": membership.id,
            "strategic_objectives": values.get("strategic_objectives", []),
            "proposal_score": values.get("proposal_score"),
            "rom_cost": values.get("rom_cost"),
            "target_start": values.get("target_start"),
            "target_finish": values.get("target_finish"),
            "expected_benefits": values.get("expected_benefits", ""),
            "risk_summary": values.get("risk_summary", []),
            "sponsor_user_id": values.get("sponsor_user_id"),
            "project_manager_user_id": request.project_manager_user_id,
            "strategic_conditions": values.get("strategic_conditions", []),
            "source_decision_hash": request.source_decision_hash,
            "source_readiness_hash": request.source_readiness_hash,
        }

    def _membership_out(self, item: PortfolioProjectMembership) -> PortfolioMembershipOut:
        portfolio = self._workspace(item.portfolio_workspace_id)
        project = self._workspace(item.project_workspace_id)
        return PortfolioMembershipOut(
            id=item.id,
            tenant_id=item.tenant_id,
            portfolio_workspace_id=item.portfolio_workspace_id,
            portfolio_name=portfolio.name,
            project_workspace_id=item.project_workspace_id,
            project_name=project.name,
            membership_source=item.membership_source,
            source_strategic_gate_decision_id=item.source_strategic_gate_decision_id,
            source_project_proposal_id=item.source_project_proposal_id,
            is_target_portfolio=item.is_target_portfolio,
            status=item.status,
            effective_from=item.effective_from,
            effective_to=item.effective_to,
            revision_version=item.revision_version,
        )

    def _allowed_actions(self, request, workspace, portfolio_readiness, definition_readiness) -> list[str]:
        roles = set(self.context.role_codes) if self.context is not None else set()
        admin = self.context is None or self.context.organization_wide or "organization_admin" in roles
        actions = []
        if request is None and (admin or "portfolio_intake_planner" in roles):
            actions.append("create_project_creation_request")
        if request is not None:
            actions.append("open_project_creation_request")
            if request.state in {"draft", "returned"}:
                actions.append("edit_creation_request")
            if request.state == "draft":
                actions.append("submit_creation_request")
            if request.state == "submitted" and (admin or "project_reviewer" in roles):
                actions.append("review_creation_request")
            if (
                request.state == "under_review"
                and (admin or "project_approver" in roles)
                and request.requestor_user_id != self.actor_id
                and request.last_modified_by_user_id != self.actor_id
            ):
                actions.append("approve_creation_request")
            if request.state == "approved" and (admin or "project_materialization_service" in roles):
                actions.append("materialize")
        if workspace is not None:
            actions.append("open_project")
            if admin or "portfolio_membership_manager" in roles:
                actions.append("establish_membership")
        if portfolio_readiness.can_enter:
            actions.append("enter_portfolio_evaluation")
        if definition_readiness.can_enter:
            actions.append("enter_project_definition")
        return actions

    def _suggested_project_type(self, proposal: ProjectProposal, configuration: dict) -> str | None:
        mapping = dict(configuration.get("project_type_mapping", {}))
        for objective in proposal.strategic_objective_codes or []:
            if objective in mapping:
                return str(mapping[objective])
        return configuration.get("default_project_type")

    @staticmethod
    def _suggested_template(project_type: str | None, templates: list[dict], configuration: dict) -> dict | None:
        recommendation = dict(configuration.get("template_recommendations", {})).get(project_type or "")
        if recommendation:
            found = next((item for item in templates if item.get("code") == recommendation), None)
            if found:
                return found
        return templates[0] if templates else None

    def _suggested_manager(self, proposal: ProjectProposal, managers) -> dict | None:
        # This is a visible recommendation only. Creation still requires an
        # explicit user selection and Gate 05B validates the active account.
        candidate = next((item for item in managers if item.id == proposal.proposal_owner_user_id), None)
        return candidate.model_dump() if candidate else None

    @staticmethod
    def _definition_framework(project_type: str | None, configuration: dict) -> str | None:
        if not project_type:
            return None
        recommendations = dict(configuration.get("definition_framework_recommendations", {}))
        return recommendations.get(project_type.strip().lower()) or recommendations.get("other")

    def _project_number_preview(self) -> str:
        configuration = ProjectWorkspaceConfigurationService(self.db, self.tenant_id, self.actor_id)
        numbering = configuration._latest("numbering_rule", PROJECT_NUMBERING_CODE, published_only=True)
        return configuration._number_preview(numbering) if numbering else ""

    def _record_code_preview(self, parent: dict | None) -> str | None:
        if not parent:
            return None
        siblings = list(
            self.db.scalars(
                select(EnterpriseWorkspace.record_code).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.parent_id == parent["id"],
                )
            ).all()
        )
        return next_record_code(str(parent["record_code"]), siblings)

    def _decision(self, decision_id: int) -> StrategicGateDecision:
        decision = self.db.scalar(
            select(StrategicGateDecision).where(
                StrategicGateDecision.id == decision_id,
                StrategicGateDecision.tenant_id == self.tenant_id,
            )
        )
        if decision is None:
            raise HTTPException(status_code=404, detail="Strategic Gate Decision not found")
        return decision

    def _proposal(self, proposal_id: int) -> ProjectProposal:
        proposal = self.db.scalar(
            select(ProjectProposal).where(
                ProjectProposal.id == proposal_id,
                ProjectProposal.tenant_id == self.tenant_id,
            )
        )
        if proposal is None:
            raise HTTPException(status_code=404, detail="Project Proposal not found")
        return proposal

    def _workspace(self, workspace_id: int | None, *, lock: bool = False) -> EnterpriseWorkspace:
        if workspace_id is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        statement = select(EnterpriseWorkspace).where(
            EnterpriseWorkspace.id == workspace_id,
            EnterpriseWorkspace.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        workspace = self.db.scalar(statement)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return workspace

    def _request_for_decision(self, decision_id: int) -> ProjectCreationRequest | None:
        return self.db.scalar(
            select(ProjectCreationRequest).where(
                ProjectCreationRequest.tenant_id == self.tenant_id,
                ProjectCreationRequest.strategic_gate_decision_id == decision_id,
            )
        )

    def _active_membership(self, portfolio_id: int, project_id: int) -> PortfolioProjectMembership | None:
        return self.db.scalar(
            select(PortfolioProjectMembership).where(
                PortfolioProjectMembership.tenant_id == self.tenant_id,
                PortfolioProjectMembership.portfolio_workspace_id == portfolio_id,
                PortfolioProjectMembership.project_workspace_id == project_id,
                PortfolioProjectMembership.status == "ACTIVE",
            )
        )

    def _workspace_path(self, workspace: EnterpriseWorkspace) -> list[EnterpriseWorkspace]:
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
            visited.add(parent.id)
            path.append(parent)
            current = parent
        return list(reversed(path))

    @staticmethod
    def _workspace_summary(workspace: EnterpriseWorkspace) -> dict:
        return {
            "id": workspace.id,
            "code": workspace.code,
            "name": workspace.name,
            "record_code": workspace.record_code,
            "workspace_type_code": workspace.workspace_type_code,
            "status": workspace.status,
            "parent_id": workspace.parent_id,
            "version": workspace.version,
        }

    @staticmethod
    def _decision_summary(decision: StrategicGateDecision) -> dict:
        return {
            "id": decision.id,
            "decision_number": decision.decision_number,
            "state": decision.state,
            "outcome": decision.outcome,
            "decision_hash": decision.decision_hash,
            "conditions": list(decision.conditions_json or []),
            "decided_at": decision.decided_at.isoformat() if decision.decided_at else None,
        }

    @staticmethod
    def _proposal_summary(proposal: ProjectProposal) -> dict:
        return {
            "id": proposal.id,
            "proposal_number": proposal.proposal_number,
            "name": proposal.name,
            "business_need": proposal.business_need,
            "preliminary_scope": proposal.preliminary_scope,
            "expected_benefits": proposal.expected_benefits,
            "rom_cost": str(proposal.rom_cost) if proposal.rom_cost is not None else None,
            "currency_code": proposal.currency_code,
            "target_start_date": proposal.target_start_date.isoformat() if proposal.target_start_date else None,
            "target_finish_date": proposal.target_finish_date.isoformat() if proposal.target_finish_date else None,
            "risk_summary": list(proposal.key_risks_json or []),
            "sponsor_user_id": proposal.sponsor_user_id,
            "strategic_objective_codes": list(proposal.strategic_objective_codes or []),
        }

    def _event(self, event_type: str, target_type: str, target_id: int, metadata: dict) -> None:
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
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _decimal(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value not in (None, "") else None
