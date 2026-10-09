"""Domain service for the governed Project Creation Process (Gate 05B)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import date
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import (
    AdminConfiguration,
    AdminNumberSequence,
    EnterpriseWorkspace,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityRole,
    UserAccount,
    WorkspaceModuleSetting,
)
from app.modules.enterprise_structure.models import (
    EnterpriseStrategicObjective,
    EnterpriseWorkspaceClassification,
)
from app.modules.enterprise_structure.permissions import (
    EnterprisePermissionContext,
    ensure_enterprise_permissions,
)
from app.modules.enterprise_structure.project_configuration import (
    PROJECT_ALLOWED_PARENTS,
    PROJECT_NUMBERING_CODE,
    PROJECT_POLICY_CODE,
    ProjectWorkspaceConfigurationService,
)
from app.modules.enterprise_structure.record_codes import next_record_code
from app.modules.project_creation.governance import (
    GOVERNANCE_LABELS,
    SOURCE_BY_GOVERNANCE,
    EffectiveProjectGovernancePolicy,
    NormalizedProjectCreationSource,
    ProjectGovernanceModel,
    ProjectGovernancePolicyService,
    ProjectSourceContextType,
    activation_authorization_status,
    normalize_project_source,
    source_requirements_status,
)
from app.modules.project_creation.models import ProjectCreationRequest
from app.modules.project_creation.schemas import (
    ProjectCreationOptionsOut,
    ProjectCreationState,
    ProjectLocationOption,
    ProjectManagerOption,
    ProjectMaterializationOut,
    ProjectOverviewOut,
    ProjectRequestCreate,
    ProjectRequestOut,
    ProjectRequestPayload,
    ProjectRequestPreviewOut,
    ProjectRequestUpdate,
    ProjectSourcePreviewOut,
    ProjectTemplateOption,
)
from app.modules.project_workspace_initialization.models import ProjectWorkspaceInitialization

REQUEST_NUMBER_RULE = "project-creation-request"
REQUEST_PRIVILEGED_ROLES = frozenset(
    {"organization_admin", "project_reviewer", "project_approver", "project_materialization_service"}
)


class ProjectCreationService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def ensure_seed(self) -> None:
        """Idempotently install RBAC and the request-number sequence, never a request."""
        ensure_enterprise_permissions(self.db, self.tenant_id, self.actor_id)
        sequence = self.db.scalar(
            select(AdminNumberSequence).where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == REQUEST_NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
        )
        if sequence is None:
            self.db.add(
                AdminNumberSequence(
                    tenant_id=self.tenant_id,
                    rule_code=REQUEST_NUMBER_RULE,
                    scope_key="tenant",
                    next_value=1,
                    version=1,
                )
            )
        ProjectGovernancePolicyService(self.db, self.tenant_id, self.actor_id).ensure_seed()
        self.db.commit()

    def options(
        self,
        parent_workspace_id: int | None = None,
        context: EnterprisePermissionContext | None = None,
    ) -> ProjectCreationOptionsOut:
        location_workspaces = self._eligible_locations()
        locations = []
        for workspace in location_workspaces:
            path = self._workspace_path(workspace)
            locations.append(
                ProjectLocationOption(
                    id=workspace.id,
                    workspace_type_code=workspace.workspace_type_code,
                    name=workspace.name,
                    record_code=workspace.record_code,
                    path=[item.name for item in path],
                )
            )
        templates = [
            ProjectTemplateOption(
                id=item.id,
                code=item.code,
                name=item.name,
                applicable_parent_types=list(item.content_json.get("applicable_parent_types", [])),
                enabled_modules=list(item.content_json.get("enabled_modules", [])),
            )
            for item in self._published_templates()
            if parent_workspace_id is None
            or any(
                workspace.id == parent_workspace_id
                and workspace.workspace_type_code in item.content_json.get("applicable_parent_types", [])
                for workspace in location_workspaces
            )
        ]
        managers = [
            ProjectManagerOption(id=item.id, name=item.full_name, email=item.email)
            for item in self.db.scalars(
                select(UserAccount)
                .where(UserAccount.tenant_id == self.tenant_id, UserAccount.status == "active")
                .order_by(UserAccount.full_name)
            ).all()
        ]
        objectives = [
            {"code": item.code, "label": item.name}
            for item in self.db.scalars(
                select(EnterpriseStrategicObjective)
                .where(
                    EnterpriseStrategicObjective.tenant_id == self.tenant_id,
                    EnterpriseStrategicObjective.active.is_(True),
                )
                .order_by(EnterpriseStrategicObjective.name)
            ).all()
        ]
        classifications: dict[str, list[dict[str, str]]] = {}
        for code in ("project-type", "project-phase", "priority", "region"):
            catalog = self._latest_configuration("catalog", code, published_only=True)
            if catalog is None or "project" not in catalog.content_json.get("applicable_types", []):
                classifications[code] = []
                continue
            classifications[code] = [
                {"code": str(item.get("code", "")), "label": str(item.get("label", ""))}
                for item in catalog.content_json.get("items", [])
            ]
        role_codes = set(context.role_codes) if context else set()
        organization_admin = "organization_admin" in role_codes
        can_create_direct = organization_admin or "project_requestor" in role_codes
        can_create_from_contract = organization_admin or "project_requestor" in role_codes
        can_create_from_strategic_gate = organization_admin or "portfolio_intake_planner" in role_codes
        allowed_models = []
        for model in ProjectGovernanceModel:
            permitted = {
                ProjectGovernanceModel.CAPITAL_OWNER: can_create_from_strategic_gate,
                ProjectGovernanceModel.CONTRACTOR_DELIVERY: can_create_from_contract,
                ProjectGovernanceModel.DIRECT_INTERNAL: can_create_direct,
            }[model]
            if permitted:
                allowed_models.append(
                    {
                        "code": model,
                        "label": GOVERNANCE_LABELS[model],
                        "source_context_type": SOURCE_BY_GOVERNANCE[model],
                        "entry_path": "STRATEGIC_PROJECT_PLANNING_ENTRY"
                        if model == ProjectGovernanceModel.CAPITAL_OWNER
                        else "CREATE_PROJECT",
                    }
                )
        return ProjectCreationOptionsOut(
            locations=locations,
            templates=templates,
            managers=managers,
            strategic_objectives=objectives,
            classifications=classifications,
            allowed_governance_models=allowed_models,
            allowed_source_context_types=sorted({str(item["source_context_type"]) for item in allowed_models}),
            can_create_direct=can_create_direct,
            can_create_from_contract=can_create_from_contract,
            can_create_from_strategic_gate=can_create_from_strategic_gate,
            blocked_reason=None if templates else "NO_PUBLISHED_PROJECT_TEMPLATE",
        )

    def create_request(
        self,
        payload: ProjectRequestCreate,
        *,
        strategic_source: dict[str, Any] | None = None,
    ) -> ProjectRequestOut:
        source_values: dict[str, Any] | None = None
        if strategic_source:
            source_values = {
                **strategic_source,
                "governance_model": ProjectGovernanceModel.CAPITAL_OWNER,
                "source_context_type": ProjectSourceContextType.STRATEGIC_GATE_DECISION,
            }
        elif payload.governance_model:
            source_values = {
                "governance_model": payload.governance_model,
                "source_context_type": payload.source_context_type,
                "source_context_id": payload.source_context_id,
                "source_external_key": payload.source_external_key,
                "idempotency_key": payload.idempotency_key,
                "source_snapshot": payload.source_snapshot,
            }
        normalized_source = normalize_project_source(source_values) if source_values else None
        if normalized_source:
            existing = self._request_by_source(normalized_source)
            if existing is not None:
                return self._out(existing)
        request = ProjectCreationRequest(
            tenant_id=self.tenant_id,
            request_number="PREVIEW",
            state=ProjectCreationState.draft,
            requestor_user_id=self.actor_id,
            revision_version=1,
            last_modified_by_user_id=self.actor_id,
            **self._payload_values(payload),
        )
        if normalized_source:
            self._apply_normalized_source(request, normalized_source)
            effective = ProjectGovernancePolicyService(self.db, self.tenant_id, self.actor_id).resolve(
                normalized_source.governance_model, payload.parent_workspace_id
            )
            request.creation_policy_id = effective.configuration.id
            request.creation_policy_revision = effective.configuration.revision
            request.creation_policy_hash = effective.configuration.content_hash
        issues, _context = self._validate_request(request, require_published=True)
        self._raise_issues(issues)
        request.request_number = self._reserve_request_number()
        self.db.add(request)
        self.db.flush()
        self._event("project_creation.request_created", request, state_before=None, state_after="draft")
        if normalized_source:
            self._event(
                "project_creation.source_validated",
                request,
                state_before=None,
                state_after="draft",
                extra={"source_hash": normalized_source.source_hash},
            )
            self._event(
                "project_creation.governance_model_selected",
                request,
                state_before=None,
                state_after="draft",
                extra={"governance_model": normalized_source.governance_model},
            )
        self.db.commit()
        self.db.refresh(request)
        return self._out(request)

    def source_preview(self, payload: ProjectRequestCreate) -> ProjectSourcePreviewOut:
        if not payload.governance_model:
            raise HTTPException(status_code=422, detail="PROJECT_GOVERNANCE_MODEL_REQUIRED")
        normalized = normalize_project_source(
            {
                "governance_model": payload.governance_model,
                "source_context_type": payload.source_context_type,
                "source_context_id": payload.source_context_id,
                "source_external_key": payload.source_external_key,
                "idempotency_key": payload.idempotency_key,
                "source_snapshot": payload.source_snapshot,
            }
        )
        effective = ProjectGovernancePolicyService(self.db, self.tenant_id, self.actor_id).resolve(
            normalized.governance_model, payload.parent_workspace_id
        )
        probe = ProjectCreationRequest(
            tenant_id=self.tenant_id,
            request_number="PREVIEW",
            state=ProjectCreationState.draft,
            requestor_user_id=self.actor_id,
            revision_version=1,
            last_modified_by_user_id=self.actor_id,
            **self._payload_values(payload),
        )
        self._apply_normalized_source(probe, normalized)
        probe.creation_policy_id = effective.configuration.id
        probe.creation_policy_revision = effective.configuration.revision
        probe.creation_policy_hash = effective.configuration.content_hash
        issues, _governance = self._validate_request(probe, require_published=True)
        source_blockers, warnings = source_requirements_status(
            normalized.governance_model,
            normalized.source_context_type,
            normalized.snapshot,
            effective.content,
            strategic_gate_decision_id=probe.strategic_gate_decision_id,
        )
        policy = effective.content
        return ProjectSourcePreviewOut(
            governance_model=normalized.governance_model,
            source_context_type=normalized.source_context_type,
            source_context_id=normalized.source_context_id,
            source_external_key=normalized.source_external_key,
            source_hash=normalized.source_hash,
            effective_policy=policy,
            source_workspace_id=effective.source_workspace_id,
            resolution_chain=list(effective.resolution_chain),
            required_fields=list(policy.get("required_fields", [])),
            optional_fields=list(policy.get("optional_fields", [])),
            required_source=list(policy.get("required_source_fields", [])),
            initialization_requirements=list(policy.get("initialization_requirements", [])),
            activation_requirements=list(policy.get("activation_requirements", [])),
            warnings=warnings,
            blockers=sorted({*issues, *source_blockers}),
            persisted=False,
        )

    def list_requests(
        self,
        context: EnterprisePermissionContext,
        *,
        state: str = "",
        search: str = "",
        review_queue: bool = False,
    ) -> list[ProjectRequestOut]:
        statement = select(ProjectCreationRequest).where(ProjectCreationRequest.tenant_id == self.tenant_id)
        privileged = bool(context.role_codes & REQUEST_PRIVILEGED_ROLES)
        if review_queue:
            if not privileged:
                return []
            statement = statement.where(
                ProjectCreationRequest.state.in_(["submitted", "under_review", "approved", "failed"])
            )
        elif not privileged:
            statement = statement.where(ProjectCreationRequest.requestor_user_id == self.actor_id)
        if state.strip():
            statement = statement.where(ProjectCreationRequest.state == state.strip().lower())
        if search.strip():
            term = f"%{search.strip().lower()}%"
            statement = statement.where(
                func.lower(ProjectCreationRequest.request_number).like(term)
                | func.lower(ProjectCreationRequest.project_name).like(term)
            )
        rows = self.db.scalars(statement.order_by(ProjectCreationRequest.created_at.desc())).all()
        return [self._out(item) for item in rows]

    def get_request(self, request_id: int, context: EnterprisePermissionContext) -> ProjectRequestOut:
        request = self._request(request_id)
        self._ensure_read_access(request, context)
        return self._out(request)

    def update_request(
        self,
        request_id: int,
        payload: ProjectRequestUpdate,
        expected_version: int,
    ) -> ProjectRequestOut:
        request = self._request(request_id, lock=True)
        self._ensure_owner(request)
        self._require_version(request, expected_version)
        if request.state not in {ProjectCreationState.draft, ProjectCreationState.returned}:
            raise HTTPException(status_code=409, detail="REQUEST_NOT_EDITABLE")
        normalized_source = self._normalized_payload_source(payload)
        if normalized_source:
            existing = self._request_by_source(normalized_source)
            if existing is not None and existing.id != request.id:
                raise HTTPException(status_code=409, detail="PROJECT_SOURCE_ALREADY_HAS_ACTIVE_REQUEST")
        issues, _context = self._validate_payload(payload, require_published=True)
        self._raise_issues(issues)
        before = request.state
        for key, value in self._payload_values(payload).items():
            setattr(request, key, value)
        if normalized_source:
            self._apply_normalized_source(request, normalized_source)
            effective = ProjectGovernancePolicyService(self.db, self.tenant_id, self.actor_id).resolve(
                normalized_source.governance_model, payload.parent_workspace_id
            )
            request.creation_policy_id = effective.configuration.id
            request.creation_policy_revision = effective.configuration.revision
            request.creation_policy_hash = effective.configuration.content_hash
        request.state = ProjectCreationState.draft
        request.submission_snapshot_json = {}
        request.submission_hash = None
        request.approval_hash = None
        request.approved_at = None
        request.approved_by_user_id = None
        request.decision_reason = None
        request.failure_reason = None
        self._touch(request)
        self._event("project_creation.request_updated", request, state_before=before, state_after=request.state)
        self.db.commit()
        self.db.refresh(request)
        return self._out(request)

    def preview(self, request_id: int, context: EnterprisePermissionContext) -> ProjectRequestPreviewOut:
        request = self._request(request_id)
        self._ensure_read_access(request, context)
        issues, governance = self._validate_request(request, require_published=True)
        parent = governance.get("parent")
        template = governance.get("template")
        policy = governance.get("policy")
        numbering = governance.get("numbering")
        if parent is None or template is None or policy is None or numbering is None:
            self._raise_issues(issues)
        sibling_codes = list(
            self.db.scalars(
                select(EnterpriseWorkspace.record_code).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.parent_id == parent.id,
                )
            ).all()
        )
        configuration = ProjectWorkspaceConfigurationService(self.db, self.tenant_id, self.actor_id)
        projected_project_number = configuration._number_preview(numbering)
        inherited = configuration._inherited_classifications(parent.id, template.content_json)
        effective = governance.get("governance_policy")
        effective_policy = dict(effective.content) if effective else dict(policy.content_json)
        warnings = list(governance.get("warnings", []))
        if request.governance_model and not activation_authorization_status(
            request.governance_model, request.source_snapshot_json
        ):
            warnings.append("ACTIVATION_AUTHORIZATION_PENDING")
        return ProjectRequestPreviewOut(
            allowed=not issues,
            issues=issues,
            parent_workspace_id=parent.id,
            parent_name=parent.name,
            parent_record_code=parent.record_code,
            projected_record_code=next_record_code(parent.record_code, sibling_codes),
            projected_project_number=projected_project_number,
            inherited_classifications=inherited,
            selected_classifications=governance.get("selected_classifications", []),
            enabled_modules=governance.get("modules", []),
            initial_workspace_status=str(policy.content_json.get("initial_status", "pending")),
            template={"id": template.id, "code": template.code, "name": template.name},
            creation_policy={"id": policy.id, "code": policy.code, "name": policy.name},
            governance_model=request.governance_model,
            source_context_type=request.source_context_type,
            effective_policy=effective_policy,
            policy_source_workspace_id=effective.source_workspace_id if effective else None,
            policy_resolution_chain=list(effective.resolution_chain) if effective else ["legacy"],
            required_fields=list(effective_policy.get("required_fields", [])),
            optional_fields=list(effective_policy.get("optional_fields", [])),
            warnings=sorted(set(warnings)),
            blockers=sorted(set(issues)),
            activation_readiness="BLOCKED" if issues else "READY_FOR_INITIALIZATION",
            persisted=False,
        )

    def submit(self, request_id: int, expected_version: int) -> ProjectRequestOut:
        request = self._request(request_id, lock=True)
        self._ensure_owner(request)
        self._require_version(request, expected_version)
        if request.state != ProjectCreationState.draft:
            raise HTTPException(status_code=409, detail="REQUEST_MUST_BE_DRAFT")
        issues, governance = self._validate_request(request, require_published=True)
        self._raise_issues(issues)
        snapshot = self._submission_snapshot(request, governance)
        request.submission_snapshot_json = snapshot
        request.submission_hash = _content_hash(snapshot)
        request.submitted_at = utc_now()
        self._transition(request, ProjectCreationState.submitted, "project_creation.request_submitted")
        return self._commit_out(request)

    def cancel(self, request_id: int, expected_version: int) -> ProjectRequestOut:
        request = self._request(request_id, lock=True)
        self._ensure_owner(request)
        self._require_version(request, expected_version)
        if request.state not in {
            ProjectCreationState.draft,
            ProjectCreationState.submitted,
            ProjectCreationState.returned,
        }:
            raise HTTPException(status_code=409, detail="REQUEST_CANNOT_BE_CANCELLED")
        self._transition(request, ProjectCreationState.cancelled, "project_creation.request_cancelled")
        return self._commit_out(request)

    def start_review(self, request_id: int, expected_version: int) -> ProjectRequestOut:
        request = self._request(request_id, lock=True)
        self._require_version(request, expected_version)
        if request.state != ProjectCreationState.submitted:
            raise HTTPException(status_code=409, detail="REQUEST_MUST_BE_SUBMITTED")
        request.reviewed_at = utc_now()
        self._transition(request, ProjectCreationState.under_review, "project_creation.review_started")
        return self._commit_out(request)

    def return_request(self, request_id: int, expected_version: int, reason: str) -> ProjectRequestOut:
        request = self._request(request_id, lock=True)
        self._require_version(request, expected_version)
        if request.state not in {ProjectCreationState.submitted, ProjectCreationState.under_review}:
            raise HTTPException(status_code=409, detail="REQUEST_CANNOT_BE_RETURNED")
        request.decision_reason = reason
        self._transition(request, ProjectCreationState.returned, "project_creation.request_returned")
        return self._commit_out(request)

    def reject(self, request_id: int, expected_version: int, reason: str) -> ProjectRequestOut:
        request = self._request(request_id, lock=True)
        self._require_version(request, expected_version)
        if request.state != ProjectCreationState.under_review:
            raise HTTPException(status_code=409, detail="REQUEST_MUST_BE_UNDER_REVIEW")
        request.decision_reason = reason
        self._transition(request, ProjectCreationState.rejected, "project_creation.request_rejected")
        return self._commit_out(request)

    def approve(self, request_id: int, expected_version: int) -> ProjectRequestOut:
        request = self._request(request_id, lock=True)
        self._require_version(request, expected_version)
        if request.state != ProjectCreationState.under_review:
            raise HTTPException(status_code=409, detail="REQUEST_MUST_BE_UNDER_REVIEW")
        if request.requestor_user_id == self.actor_id or request.last_modified_by_user_id == self.actor_id:
            raise HTTPException(status_code=403, detail="FOUR_EYES_VIOLATION")
        issues, governance = self._validate_request(request, require_published=True)
        self._raise_issues(issues)
        request.approval_hash = self._approval_hash(request, governance)
        request.approved_by_user_id = self.actor_id
        request.approved_at = utc_now()
        self._transition(request, ProjectCreationState.approved, "project_creation.request_approved")
        return self._commit_out(request)

    def materialize(
        self,
        request_id: int,
        *,
        failure_injector: Callable[[EnterpriseWorkspace], None] | None = None,
    ) -> ProjectMaterializationOut:
        try:
            request = self._request(request_id, lock=True)
            if request.state == ProjectCreationState.created and request.materialized_workspace_id is not None:
                planning_status = self._finalize_strategic_materialization(
                    request,
                    self.db.get(EnterpriseWorkspace, request.materialized_workspace_id),
                )
                if planning_status:
                    self.db.commit()
                return ProjectMaterializationOut(
                    result="ALREADY_CREATED",
                    request_id=request.id,
                    request_number=request.request_number,
                    state=ProjectCreationState.created,
                    materialized_workspace_id=request.materialized_workspace_id,
                    project_number=request.materialized_project_number or "",
                    record_code=request.materialized_record_code or "",
                    mutation_count=0,
                    portfolio_planning_status=planning_status,
                )
            if request.state != ProjectCreationState.approved:
                raise HTTPException(status_code=409, detail="REQUEST_MUST_BE_APPROVED")
            issues, governance = self._validate_request(request, require_published=True, lock=True)
            self._raise_issues(issues)
            if request.approval_hash != self._approval_hash(request, governance):
                raise HTTPException(status_code=409, detail="APPROVAL_INVALIDATED")
            parent: EnterpriseWorkspace = governance["parent"]
            template: AdminConfiguration = governance["template"]
            policy: AdminConfiguration = governance["policy"]
            self._event(
                "project_creation.materialization_started",
                request,
                state_before=request.state,
                state_after=ProjectCreationState.materializing,
            )
            request.state = ProjectCreationState.materializing
            project_number = ProjectWorkspaceConfigurationService(
                self.db, self.tenant_id, self.actor_id
            ).reserve_project_number()
            sibling_codes = list(
                self.db.scalars(
                    select(EnterpriseWorkspace.record_code).where(
                        EnterpriseWorkspace.tenant_id == self.tenant_id,
                        EnterpriseWorkspace.parent_id == parent.id,
                    )
                ).all()
            )
            record_code = next_record_code(parent.record_code, sibling_codes)
            metadata = self._project_metadata(request, template, governance.get("modules", []), project_number)
            workspace = EnterpriseWorkspace(
                tenant_id=self.tenant_id,
                parent_id=parent.id,
                workspace_type_code="project",
                code=project_number,
                external_key=f"PRJ-{uuid4()}",
                record_code=record_code,
                name=request.project_name,
                status=str(policy.content_json.get("initial_status", "pending")),
                defaults_json={"_project": metadata},
                sort_order=100,
                version=1,
                created_by_user_id=self.actor_id,
            )
            self.db.add(workspace)
            self.db.flush()
            if failure_injector is not None:
                failure_injector(workspace)
            self._persist_classifications(workspace, governance.get("all_classifications", []))
            self._persist_modules(workspace, governance.get("modules", []))
            self._persist_manager_assignment(workspace, request.project_manager_user_id)
            request.materialized_workspace_id = workspace.id
            request.materialized_project_number = project_number
            request.materialized_record_code = record_code
            request.materialized_at = utc_now()
            request.failure_reason = None
            request.state = ProjectCreationState.created
            self._touch(request)
            self._event(
                "project_creation.workspace_created",
                request,
                state_before=ProjectCreationState.materializing,
                state_after=ProjectCreationState.created,
                project_number=project_number,
                record_code=record_code,
                workspace_id=workspace.id,
            )
            planning_status = self._finalize_strategic_materialization(request, workspace)
            self.db.commit()
            return ProjectMaterializationOut(
                result="CREATED",
                request_id=request.id,
                request_number=request.request_number,
                state=ProjectCreationState.created,
                materialized_workspace_id=workspace.id,
                project_number=project_number,
                record_code=record_code,
                mutation_count=1,
                portfolio_planning_status=planning_status,
            )
        except HTTPException:
            self.db.rollback()
            raise
        except IntegrityError as exc:
            self.db.rollback()
            self._record_materialization_failure(request_id, str(exc), mark_failed=True)
            raise HTTPException(status_code=409, detail="MATERIALIZATION_INTEGRITY_FAILURE") from exc
        except Exception as exc:
            self.db.rollback()
            self._record_materialization_failure(request_id, str(exc), mark_failed=False)
            raise

    def project_overview(
        self,
        workspace_id: int,
        context: EnterprisePermissionContext,
    ) -> ProjectOverviewOut:
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.id == workspace_id,
                EnterpriseWorkspace.workspace_type_code == "project",
            )
        )
        if workspace is None:
            raise HTTPException(status_code=404, detail="Project Workspace not found")
        if not context.organization_wide and workspace.id not in context.workspace_ids:
            raise HTTPException(status_code=404, detail="Project Workspace not found")
        metadata = workspace.defaults_json.get("_project", {})
        parent = self.db.get(EnterpriseWorkspace, workspace.parent_id) if workspace.parent_id else None
        manager = self.db.get(UserAccount, metadata.get("project_manager_user_id"))
        objectives = list(
            self.db.scalars(
                select(EnterpriseWorkspaceClassification.category_item_code).where(
                    EnterpriseWorkspaceClassification.tenant_id == self.tenant_id,
                    EnterpriseWorkspaceClassification.workspace_id == workspace.id,
                    EnterpriseWorkspaceClassification.category_set_code == "strategic-objective",
                )
            ).all()
        )
        modules = list(
            self.db.scalars(
                select(WorkspaceModuleSetting.module_key).where(
                    WorkspaceModuleSetting.tenant_id == self.tenant_id,
                    WorkspaceModuleSetting.workspace_id == workspace.id,
                    WorkspaceModuleSetting.enabled.is_(True),
                )
            ).all()
        )
        initialization = self.db.scalar(
            select(ProjectWorkspaceInitialization).where(
                ProjectWorkspaceInitialization.tenant_id == self.tenant_id,
                ProjectWorkspaceInitialization.workspace_id == workspace.id,
            )
        )
        checklist = initialization.checklist_json if initialization else []
        blockers = [
            str(item.get("message", item.get("code", "")))
            for item in checklist
            if item.get("blocking") and item.get("status") == "FAIL"
        ]
        warnings = [
            str(item.get("message", item.get("code", ""))) for item in checklist if item.get("status") == "WARNING"
        ]
        complete_count = sum(1 for item in checklist if item.get("status") in {"PASS", "WARNING"})
        initialization_state = (
            initialization.state if initialization else ("ACTIVATED" if workspace.status == "active" else "NOT_STARTED")
        )
        governance_model = metadata.get("governance_model")
        source_snapshot = dict(metadata.get("source_snapshot") or {})
        source_reference = metadata.get("source_external_key") or metadata.get("source_context_id")
        activation_readiness = str(metadata.get("activation_readiness") or "NOT_EVALUATED")
        if initialization:
            activation_readiness = str(initialization.state)
        role_codes = set(context.role_codes)
        return ProjectOverviewOut(
            workspace_id=workspace.id,
            project_name=workspace.name,
            project_number=str(metadata.get("project_number", workspace.code)),
            record_code=workspace.record_code,
            status=workspace.status,
            parent_workspace=parent.name if parent else "",
            project_manager=manager.full_name if manager else "",
            template=str(metadata.get("template_code", "")),
            strategic_objectives=objectives,
            governance_model=str(governance_model) if governance_model else None,
            governance_label=GOVERNANCE_LABELS.get(str(governance_model), "Legacy / Not Classified"),
            creation_source=str(metadata.get("source_context_type")) if metadata.get("source_context_type") else None,
            source_reference=str(source_reference) if source_reference is not None else None,
            source_snapshot=source_snapshot,
            creation_policy={
                "id": metadata.get("creation_policy_id"),
                "revision": metadata.get("creation_policy_revision"),
                "hash": metadata.get("creation_policy_hash"),
            },
            pending_reason=metadata.get("pending_reason"),
            planning_stage=metadata.get("planning_stage"),
            activation_readiness=activation_readiness,
            planned_start=_date_value(metadata.get("planned_start")),
            planned_finish=_date_value(metadata.get("planned_finish")),
            currency=str(metadata.get("currency_code", "")),
            estimated_budget=metadata.get("estimated_budget"),
            enabled_modules=modules,
            initialization_state=initialization_state,
            initialization_progress_percent=round(complete_count / len(checklist) * 100)
            if checklist
            else (100 if workspace.status == "active" else 0),
            initialization_blocker_count=len(blockers),
            initialization_warning_count=len(warnings),
            blocking_issues=blockers,
            warnings=warnings,
            template_revision=initialization.template_revision if initialization else metadata.get("template_revision"),
            module_states={
                key: str(value.get("state", "NOT_INITIALIZED"))
                for key, value in (initialization.module_states_json if initialization else {}).items()
            },
            activated_at=initialization.activated_at if initialization else None,
            activated_by_user_id=initialization.activated_by_user_id if initialization else None,
            initialization_revision_version=initialization.revision_version if initialization else workspace.version,
            can_initialize=bool(role_codes & {"organization_admin", "project_workspace_initializer"})
            and workspace.status == "pending",
            can_activate=bool(role_codes & {"organization_admin", "project_workspace_activator"})
            and initialization is not None
            and initialization.state == "READY_FOR_ACTIVATION",
        )

    def _validate_payload(
        self,
        payload: ProjectRequestPayload,
        *,
        require_published: bool,
    ) -> tuple[list[str], dict[str, Any]]:
        probe = ProjectCreationRequest(
            tenant_id=self.tenant_id,
            request_number="PREVIEW",
            state="draft",
            requestor_user_id=self.actor_id,
            revision_version=1,
            last_modified_by_user_id=self.actor_id,
            **self._payload_values(payload),
        )
        normalized_source = self._normalized_payload_source(payload)
        if normalized_source:
            self._apply_normalized_source(probe, normalized_source)
            effective = ProjectGovernancePolicyService(self.db, self.tenant_id, self.actor_id).resolve(
                normalized_source.governance_model, payload.parent_workspace_id
            )
            probe.creation_policy_id = effective.configuration.id
            probe.creation_policy_revision = effective.configuration.revision
            probe.creation_policy_hash = effective.configuration.content_hash
        return self._validate_request(probe, require_published=require_published)

    def _validate_request(
        self,
        request: ProjectCreationRequest,
        *,
        require_published: bool,
        lock: bool = False,
    ) -> tuple[list[str], dict[str, Any]]:
        issues: list[str] = []
        parent_statement = select(EnterpriseWorkspace).where(
            EnterpriseWorkspace.tenant_id == self.tenant_id,
            EnterpriseWorkspace.id == request.parent_workspace_id,
        )
        template_statement = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.id == request.project_template_config_id,
            AdminConfiguration.kind == "project_template",
        )
        if lock:
            parent_statement = parent_statement.with_for_update()
            template_statement = template_statement.with_for_update()
        parent = self.db.scalar(parent_statement)
        template = self.db.scalar(template_statement)
        policy = self._latest_configuration("creation_policy", PROJECT_POLICY_CODE, published_only=True)
        numbering = self._latest_configuration("numbering_rule", PROJECT_NUMBERING_CODE, published_only=True)
        governance_policy = None
        effective_policy: dict[str, Any] = dict(policy.content_json) if policy else {}
        warnings: list[str] = []
        if request.governance_model:
            if request.governance_model not in {str(item) for item in ProjectGovernanceModel}:
                issues.append("PROJECT_GOVERNANCE_MODEL_INVALID")
            else:
                if request.creation_policy_id:
                    configuration = self.db.scalar(
                        select(AdminConfiguration).where(
                            AdminConfiguration.id == request.creation_policy_id,
                            AdminConfiguration.tenant_id == self.tenant_id,
                            AdminConfiguration.kind == "project_governance_policy",
                        )
                    )
                    if configuration is not None:
                        # Historical requests keep the exact approved revision even
                        # when a newer tenant policy is published.
                        governance_policy = EffectiveProjectGovernancePolicy(
                            configuration=configuration,
                            content=dict(configuration.content_json or {}),
                            source_workspace_id=configuration.content_json.get("scope_workspace_id"),
                            resolution_chain=(str(configuration.content_json.get("scope", "tenant")),),
                        )
                        if request.creation_policy_revision not in (None, configuration.revision):
                            issues.append("CREATION_POLICY_REVISION_MISMATCH")
                        if request.creation_policy_hash not in (None, configuration.content_hash):
                            issues.append("CREATION_POLICY_HASH_MISMATCH")
                if governance_policy is None:
                    try:
                        governance_policy = ProjectGovernancePolicyService(
                            self.db, self.tenant_id, self.actor_id
                        ).resolve(request.governance_model, request.parent_workspace_id)
                    except HTTPException:
                        issues.append("PROJECT_GOVERNANCE_POLICY_NOT_PUBLISHED")
                if governance_policy is not None:
                    effective_policy = dict(governance_policy.content)
        if parent is None:
            issues.append("PARENT_WORKSPACE_NOT_FOUND")
        else:
            if parent.workspace_type_code not in PROJECT_ALLOWED_PARENTS:
                issues.append("INVALID_PARENT_WORKSPACE_TYPE")
            if parent.status != "active":
                issues.append("PARENT_WORKSPACE_NOT_ACTIVE")
            parent_type = self._latest_configuration("workspace_type", parent.workspace_type_code, published_only=True)
            if parent_type is None or "project" not in parent_type.content_json.get("allowed_children", []):
                issues.append("COMPOSITION_RULE_BLOCKS_PROJECT")
        if template is None:
            issues.append("PROJECT_TEMPLATE_NOT_FOUND")
        else:
            if require_published and template.status != "published":
                issues.append("NO_PUBLISHED_PROJECT_TEMPLATE")
            if parent is not None and parent.workspace_type_code not in template.content_json.get(
                "applicable_parent_types", []
            ):
                issues.append("PROJECT_TEMPLATE_NOT_APPLICABLE")
        if policy is None:
            issues.append("PROJECT_CREATION_POLICY_NOT_PUBLISHED")
        elif parent is not None and parent.workspace_type_code not in effective_policy.get("allowed_parent_types", []):
            issues.append("PROJECT_CREATION_POLICY_BLOCKS_PARENT")
        if numbering is None:
            issues.append("PROJECT_NUMBERING_NOT_PUBLISHED")
        manager = self.db.scalar(
            select(UserAccount).where(
                UserAccount.tenant_id == self.tenant_id,
                UserAccount.id == request.project_manager_user_id,
                UserAccount.status == "active",
            )
        )
        if effective_policy.get("project_manager_required", True) and manager is None:
            issues.append("PROJECT_MANAGER_REQUIRED")
        if not request.project_name.strip():
            issues.append("PROJECT_NAME_REQUIRED")
        if not request.currency_code.strip():
            issues.append("CURRENCY_REQUIRED")
        if request.planned_start and request.planned_finish and request.planned_finish < request.planned_start:
            issues.append("INVALID_PLANNED_DATES")
        objective_codes = sorted(set(request.strategic_objective_codes or []))
        objectives = list(
            self.db.scalars(
                select(EnterpriseStrategicObjective).where(
                    EnterpriseStrategicObjective.tenant_id == self.tenant_id,
                    EnterpriseStrategicObjective.code.in_(objective_codes or ["__none__"]),
                    EnterpriseStrategicObjective.active.is_(True),
                )
            ).all()
        )
        objective_required = bool(effective_policy.get("strategic_objective_required", True))
        if objective_required and not objective_codes:
            issues.append("STRATEGIC_OBJECTIVE_REQUIRED")
        elif objective_codes and {item.code for item in objectives} != set(objective_codes):
            issues.append("STRATEGIC_OBJECTIVE_INVALID")
        source_blockers, source_warnings = source_requirements_status(
            request.governance_model,
            request.source_context_type,
            request.source_snapshot_json,
            effective_policy,
            strategic_gate_decision_id=request.strategic_gate_decision_id,
        )
        issues.extend(source_blockers)
        warnings.extend(source_warnings)
        selected_classifications = [
            {"category_set_code": "strategic-objective", "category_item_code": code, "source": "request"}
            for code in objective_codes
        ]
        for field_name, catalog_code in (
            ("project_type", "project-type"),
            ("project_phase", "project-phase"),
            ("priority", "priority"),
            ("region", "region"),
        ):
            value = getattr(request, field_name)
            if not value:
                continue
            catalog = self._latest_configuration("catalog", catalog_code, published_only=True)
            valid_items = (
                {str(item.get("code", "")) for item in catalog.content_json.get("items", [])} if catalog else set()
            )
            if (
                catalog is None
                or "project" not in catalog.content_json.get("applicable_types", [])
                or value not in valid_items
            ):
                issues.append(f"CLASSIFICATION_NOT_AVAILABLE:{catalog_code}/{value}")
            else:
                selected_classifications.append(
                    {"category_set_code": catalog_code, "category_item_code": value, "source": "request"}
                )
        modules: list[str] = []
        inherited: list[dict[str, str]] = []
        if template is not None:
            requested_modules = set(template.content_json.get("enabled_modules", []))
            available_modules = set(
                self.db.scalars(
                    select(AdminConfiguration.code).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == "module_definition",
                        AdminConfiguration.status == "published",
                    )
                ).all()
            )
            unknown = sorted(requested_modules - available_modules)
            if unknown:
                issues.append(f"MODULE_DEFINITION_NOT_PUBLISHED:{','.join(unknown)}")
            modules = sorted(requested_modules & available_modules)
            if parent is not None:
                inherited = ProjectWorkspaceConfigurationService(
                    self.db, self.tenant_id, self.actor_id
                )._inherited_classifications(parent.id, template.content_json)
        all_classifications = _deduplicate_classifications([*inherited, *selected_classifications])
        return issues, {
            "parent": parent,
            "template": template,
            "policy": policy,
            "numbering": numbering,
            "manager": manager,
            "objectives": objectives,
            "selected_classifications": selected_classifications,
            "all_classifications": all_classifications,
            "modules": modules,
            "governance_policy": governance_policy,
            "effective_policy": effective_policy,
            "warnings": warnings,
        }

    def _submission_snapshot(self, request: ProjectCreationRequest, governance: dict[str, Any]) -> dict[str, Any]:
        return {
            "request": _json_compatible(self._request_values(request)),
            "source": self._source_values(request),
            "parent": self._workspace_fingerprint(governance["parent"]),
            "template": self._configuration_fingerprint(governance["template"]),
            "policy": self._configuration_fingerprint(governance["policy"]),
            "numbering": self._configuration_fingerprint(governance["numbering"]),
            "modules": governance.get("modules", []),
            "classifications": governance.get("all_classifications", []),
        }

    def _approval_hash(self, request: ProjectCreationRequest, governance: dict[str, Any]) -> str:
        return _content_hash(
            {
                "submission_hash": request.submission_hash,
                "request": _json_compatible(self._request_values(request)),
                "source": self._source_values(request),
                "parent": self._workspace_fingerprint(governance["parent"]),
                "template": self._configuration_fingerprint(governance["template"]),
                "policy": self._configuration_fingerprint(governance["policy"]),
                "numbering": self._configuration_fingerprint(governance["numbering"]),
                "modules": governance.get("modules", []),
                "classifications": governance.get("all_classifications", []),
            }
        )

    @staticmethod
    def _source_values(request: ProjectCreationRequest) -> dict[str, Any]:
        """Fingerprint immutable multi-source lineage protected by submit/approve hashes."""
        return _json_compatible(
            {
                "governance_model": request.governance_model,
                "source_context_type": request.source_context_type,
                "source_context_id": request.source_context_id,
                "source_external_key": request.source_external_key,
                "idempotency_key": request.idempotency_key,
                "source_snapshot": request.source_snapshot_json or {},
                "source_hash": request.source_hash,
                "creation_policy_id": request.creation_policy_id,
                "creation_policy_revision": request.creation_policy_revision,
                "creation_policy_hash": request.creation_policy_hash,
                "strategic_gate_decision_id": request.strategic_gate_decision_id,
                "source_project_proposal_id": request.source_project_proposal_id,
                "source_idea_id": request.source_idea_id,
                "source_decision_hash": request.source_decision_hash,
                "source_readiness_hash": request.source_readiness_hash,
                "strategic_target_portfolio_workspace_id": (request.strategic_target_portfolio_workspace_id),
                "strategic_mapping_configuration_id": request.strategic_mapping_configuration_id,
                "strategic_mapping_revision": request.strategic_mapping_revision,
                "strategic_mapping_hash": request.strategic_mapping_hash,
                "strategic_source_snapshot": request.strategic_source_snapshot_json or {},
            }
        )

    def _project_metadata(
        self,
        request: ProjectCreationRequest,
        template: AdminConfiguration,
        modules: list[str],
        project_number: str,
    ) -> dict[str, Any]:
        governance_policy_record = (
            self.db.get(AdminConfiguration, request.creation_policy_id) if request.creation_policy_id else None
        )
        governance_policy = dict(governance_policy_record.content_json or {}) if governance_policy_record else {}
        source_blockers, _source_warnings = source_requirements_status(
            request.governance_model,
            request.source_context_type,
            request.source_snapshot_json,
            governance_policy,
            strategic_gate_decision_id=request.strategic_gate_decision_id,
        )
        explicit_fields = [
            field
            for field, value in {
                "description": request.description,
                "project_manager_user_id": request.project_manager_user_id,
                "planned_start": request.planned_start,
                "planned_finish": request.planned_finish,
                "currency_code": request.currency_code,
                "estimated_budget": request.estimated_budget,
                "project_type": request.project_type,
                "project_phase": request.project_phase,
                "priority": request.priority,
                "country": request.country,
                "region": request.region,
                "strategic_objective_codes": request.strategic_objective_codes,
            }.items()
            if value not in (None, "", [])
        ]
        metadata = {
            "project_number": project_number,
            "description": request.description,
            "project_manager_user_id": request.project_manager_user_id,
            "planned_start": request.planned_start.isoformat() if request.planned_start else None,
            "planned_finish": request.planned_finish.isoformat() if request.planned_finish else None,
            "currency_code": request.currency_code,
            "estimated_budget": str(request.estimated_budget) if request.estimated_budget is not None else None,
            "project_type": request.project_type,
            "project_phase": request.project_phase,
            "priority": request.priority,
            "country": request.country,
            "region": request.region,
            "strategic_objective_codes": list(request.strategic_objective_codes),
            "template_id": template.id,
            "template_code": template.code,
            "template_revision": template.revision,
            "template_content_hash": template.content_hash,
            "template_defaults_snapshot": dict(template.content_json.get("default_attributes", {})),
            "explicit_fields": explicit_fields,
            "enabled_modules": modules,
            "creation_request_id": request.id,
            "creation_request_number": request.request_number,
            "governance_model": request.governance_model,
            "source_context_type": request.source_context_type,
            "source_context_id": request.source_context_id,
            "source_external_key": request.source_external_key,
            "source_snapshot": dict(request.source_snapshot_json or {}),
            "source_hash": request.source_hash,
            "creation_policy_id": request.creation_policy_id,
            "creation_policy_revision": request.creation_policy_revision,
            "creation_policy_hash": request.creation_policy_hash,
            "governance_policy_snapshot": governance_policy,
            "pending_reason": governance_policy.get("pending_reason") if request.governance_model else None,
            "planning_stage": governance_policy.get("planning_stage") if request.governance_model else None,
            "activation_readiness": (
                "BLOCKED"
                if source_blockers
                or not activation_authorization_status(request.governance_model, request.source_snapshot_json)
                else "READY_FOR_INITIALIZATION"
            ),
        }
        if request.source_context_type == "STRATEGIC_GATE_DECISION":
            metadata.update(
                {
                    "planning_origin": "STRATEGIC_GATE",
                    "planning_stage": "PORTFOLIO_AND_FEL_PLANNING",
                    "source_context_type": request.source_context_type,
                    "strategic_gate_decision_id": request.strategic_gate_decision_id,
                    "source_project_proposal_id": request.source_project_proposal_id,
                    "source_idea_id": request.source_idea_id,
                    "target_portfolio_workspace_id": request.strategic_target_portfolio_workspace_id,
                }
            )
        return metadata

    def _finalize_strategic_materialization(
        self,
        request: ProjectCreationRequest,
        workspace: EnterpriseWorkspace | None,
    ) -> str | None:
        if request.source_context_type != "STRATEGIC_GATE_DECISION":
            return None
        if workspace is None:
            raise HTTPException(status_code=409, detail="STRATEGIC_PROJECT_WORKSPACE_NOT_FOUND")
        # Local import keeps Gate 05B independent while allowing the additive
        # Gate 07D transaction to complete atomically with materialization.
        from app.modules.portfolio_planning.service import PortfolioPlanningService

        return PortfolioPlanningService(
            self.db,
            self.tenant_id,
            self.actor_id,
            context=None,
        ).finalize_materialization(request, workspace)

    def _persist_classifications(
        self,
        workspace: EnterpriseWorkspace,
        classifications: list[dict[str, str]],
    ) -> None:
        for item in classifications:
            category = str(item.get("category_set_code", ""))
            code = str(item.get("category_item_code", ""))
            if not category or not code:
                continue
            self.db.add(
                EnterpriseWorkspaceClassification(
                    tenant_id=self.tenant_id,
                    workspace_id=workspace.id,
                    category_set_code=category,
                    category_item_code=code,
                    created_by_user_id=self.actor_id,
                )
            )

    def _persist_modules(self, workspace: EnterpriseWorkspace, modules: list[str]) -> None:
        for module_key in modules:
            self.db.add(
                WorkspaceModuleSetting(
                    tenant_id=self.tenant_id,
                    workspace_id=workspace.id,
                    module_key=module_key,
                    enabled=True,
                    version=1,
                    updated_by_user_id=self.actor_id,
                )
            )

    def _persist_manager_assignment(self, workspace: EnterpriseWorkspace, manager_id: int) -> None:
        role = self.db.scalar(
            select(SecurityRole).where(
                SecurityRole.tenant_id == self.tenant_id,
                SecurityRole.code == "project_manager",
                SecurityRole.status == "active",
            )
        )
        if role is None:
            raise HTTPException(status_code=409, detail="PROJECT_MANAGER_ROLE_NOT_CONFIGURED")
        self.db.add(
            SecurityAccessAssignment(
                tenant_id=self.tenant_id,
                subject_type="user",
                user_id=manager_id,
                role_id=role.id,
                scope_type="workspace",
                workspace_id=workspace.id,
                status="active",
                granted_by_user_id=self.actor_id,
            )
        )

    def _record_materialization_failure(self, request_id: int, reason: str, *, mark_failed: bool) -> None:
        request = self.db.scalar(
            select(ProjectCreationRequest).where(
                ProjectCreationRequest.tenant_id == self.tenant_id,
                ProjectCreationRequest.id == request_id,
            )
        )
        if request is None:
            return
        before = request.state
        if mark_failed:
            request.state = ProjectCreationState.failed
            request.failure_reason = reason[:2000]
            self._touch(request)
        self._event(
            "project_creation.materialization_failed",
            request,
            state_before=before,
            state_after=request.state,
            outcome="failure",
            extra={"reason": reason[:500]},
        )
        self.db.commit()

    def _reserve_request_number(self) -> str:
        value = self.db.scalar(
            update(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == REQUEST_NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
            .values(
                next_value=AdminNumberSequence.next_value + 1,
                version=AdminNumberSequence.version + 1,
                updated_at=utc_now(),
            )
            .returning(AdminNumberSequence.next_value - 1)
        )
        if value is None:
            raise HTTPException(status_code=409, detail="REQUEST_NUMBER_SEQUENCE_NOT_INITIALIZED")
        return f"PCR-{value:05d}"

    def _eligible_locations(self) -> list[EnterpriseWorkspace]:
        return list(
            self.db.scalars(
                select(EnterpriseWorkspace)
                .where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.workspace_type_code.in_(PROJECT_ALLOWED_PARENTS),
                    EnterpriseWorkspace.status == "active",
                )
                .order_by(EnterpriseWorkspace.record_code)
            ).all()
        )

    def _published_templates(self) -> list[AdminConfiguration]:
        return list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == "project_template",
                    AdminConfiguration.status == "published",
                )
                .order_by(AdminConfiguration.name)
            ).all()
        )

    def _latest_configuration(
        self,
        kind: str,
        code: str,
        *,
        published_only: bool,
    ) -> AdminConfiguration | None:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == kind,
            AdminConfiguration.code == code,
        )
        if published_only:
            statement = statement.where(AdminConfiguration.status == "published")
        return self.db.scalar(statement.order_by(AdminConfiguration.revision.desc()).limit(1))

    def _request_by_source(
        self,
        source: NormalizedProjectCreationSource,
    ) -> ProjectCreationRequest | None:
        statement = select(ProjectCreationRequest).where(
            ProjectCreationRequest.tenant_id == self.tenant_id,
            ProjectCreationRequest.state.notin_([ProjectCreationState.cancelled, ProjectCreationState.rejected]),
        )
        if source.source_context_id is not None:
            statement = statement.where(
                ProjectCreationRequest.source_context_type == source.source_context_type,
                ProjectCreationRequest.source_context_id == source.source_context_id,
            )
        elif source.idempotency_key:
            statement = statement.where(ProjectCreationRequest.idempotency_key == source.idempotency_key)
        elif source.source_external_key:
            statement = statement.where(
                ProjectCreationRequest.source_context_type == source.source_context_type,
                ProjectCreationRequest.source_external_key == source.source_external_key,
            )
        else:
            return None
        return self.db.scalar(statement.order_by(ProjectCreationRequest.id.desc()).limit(1))

    @staticmethod
    def _normalized_payload_source(
        payload: ProjectRequestPayload,
    ) -> NormalizedProjectCreationSource | None:
        if not payload.governance_model:
            return None
        return normalize_project_source(
            {
                "governance_model": payload.governance_model,
                "source_context_type": payload.source_context_type,
                "source_context_id": payload.source_context_id,
                "source_external_key": payload.source_external_key,
                "idempotency_key": payload.idempotency_key,
                "source_snapshot": payload.source_snapshot,
            }
        )

    @staticmethod
    def _apply_normalized_source(
        request: ProjectCreationRequest,
        source: NormalizedProjectCreationSource,
    ) -> None:
        request.governance_model = source.governance_model
        request.source_context_type = source.source_context_type
        request.source_context_id = source.source_context_id
        request.source_external_key = source.source_external_key
        request.idempotency_key = source.idempotency_key
        request.source_snapshot_json = dict(source.snapshot)
        request.source_hash = source.source_hash
        for field, value in source.strategic_fields.items():
            setattr(request, field, value)

    def _request(self, request_id: int, *, lock: bool = False) -> ProjectCreationRequest:
        statement = select(ProjectCreationRequest).where(
            ProjectCreationRequest.tenant_id == self.tenant_id,
            ProjectCreationRequest.id == request_id,
        )
        if lock:
            statement = statement.with_for_update()
        request = self.db.scalar(statement)
        if request is None:
            raise HTTPException(status_code=404, detail="Project Creation Request not found")
        return request

    def _ensure_owner(self, request: ProjectCreationRequest) -> None:
        if request.requestor_user_id != self.actor_id:
            raise HTTPException(status_code=403, detail="Only the requestor may change this request")

    def _ensure_read_access(
        self,
        request: ProjectCreationRequest,
        context: EnterprisePermissionContext,
    ) -> None:
        if request.requestor_user_id != self.actor_id and not context.role_codes & REQUEST_PRIVILEGED_ROLES:
            raise HTTPException(status_code=404, detail="Project Creation Request not found")

    @staticmethod
    def _require_version(request: ProjectCreationRequest, expected: int) -> None:
        if request.revision_version != expected:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "REQUEST_VERSION_CONFLICT",
                    "message": "This request changed since you opened it. Reload the latest version before continuing.",
                    "expected": expected,
                    "observed": request.revision_version,
                },
            )

    def _transition(self, request: ProjectCreationRequest, state: ProjectCreationState, event_type: str) -> None:
        before = request.state
        request.state = state
        self._touch(request)
        self._event(event_type, request, state_before=before, state_after=state)

    def _touch(self, request: ProjectCreationRequest) -> None:
        request.revision_version += 1
        request.last_modified_by_user_id = self.actor_id
        request.updated_at = utc_now()

    def _commit_out(self, request: ProjectCreationRequest) -> ProjectRequestOut:
        self.db.commit()
        self.db.refresh(request)
        return self._out(request)

    def _event(
        self,
        event_type: str,
        request: ProjectCreationRequest,
        *,
        state_before: str | None,
        state_after: str | None,
        outcome: str = "success",
        project_number: str | None = None,
        record_code: str | None = None,
        workspace_id: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        metadata = {
            "tenant_id": self.tenant_id,
            "request_id": request.id,
            "request_number": request.request_number,
            "actor_id": self.actor_id,
            "parent_workspace_id": request.parent_workspace_id,
            "project_template_config_id": request.project_template_config_id,
            "governance_model": request.governance_model,
            "source_context_type": request.source_context_type,
            "source_context_id": request.source_context_id,
            "source_external_key": request.source_external_key,
            "source_hash": request.source_hash,
            "state_before": str(state_before) if state_before is not None else None,
            "state_after": str(state_after) if state_after is not None else None,
            "project_number": project_number,
            "record_code": record_code,
            "workspace_id": workspace_id,
            "timestamp": utc_now().isoformat(),
            "result": outcome,
            **(extra or {}),
        }
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome=outcome,
                target_type="project_creation_request",
                target_id=request.id,
                metadata_json=metadata,
            )
        )

    def _out(self, request: ProjectCreationRequest) -> ProjectRequestOut:
        parent = self.db.get(EnterpriseWorkspace, request.parent_workspace_id)
        template = self.db.get(AdminConfiguration, request.project_template_config_id)
        requestor = self.db.get(UserAccount, request.requestor_user_id)
        manager = self.db.get(UserAccount, request.project_manager_user_id)
        return ProjectRequestOut(
            **self._request_values(request),
            id=request.id,
            request_number=request.request_number,
            state=request.state,
            requestor_user_id=request.requestor_user_id,
            requestor_name=requestor.full_name if requestor else "",
            parent_name=parent.name if parent else "",
            parent_record_code=parent.record_code if parent else "",
            template_code=template.code if template else "",
            template_name=template.name if template else "",
            project_manager_name=manager.full_name if manager else "",
            revision_version=request.revision_version,
            governance_model=request.governance_model,
            source_context_type=request.source_context_type,
            source_context_id=request.source_context_id,
            source_external_key=request.source_external_key,
            idempotency_key=request.idempotency_key,
            source_snapshot=dict(request.source_snapshot_json or {}),
            source_hash=request.source_hash,
            creation_policy_id=request.creation_policy_id,
            creation_policy_revision=request.creation_policy_revision,
            creation_policy_hash=request.creation_policy_hash,
            strategic_gate_decision_id=request.strategic_gate_decision_id,
            source_project_proposal_id=request.source_project_proposal_id,
            source_idea_id=request.source_idea_id,
            source_decision_hash=request.source_decision_hash,
            source_readiness_hash=request.source_readiness_hash,
            strategic_target_portfolio_workspace_id=request.strategic_target_portfolio_workspace_id,
            strategic_mapping_configuration_id=request.strategic_mapping_configuration_id,
            strategic_mapping_revision=request.strategic_mapping_revision,
            strategic_mapping_hash=request.strategic_mapping_hash,
            strategic_source_snapshot=dict(request.strategic_source_snapshot_json or {}),
            decision_reason=request.decision_reason,
            failure_reason=request.failure_reason,
            approved_by_user_id=request.approved_by_user_id,
            approved_at=request.approved_at,
            materialized_workspace_id=request.materialized_workspace_id,
            materialized_project_number=request.materialized_project_number,
            materialized_record_code=request.materialized_record_code,
            created_at=request.created_at,
            updated_at=request.updated_at,
            submitted_at=request.submitted_at,
            reviewed_at=request.reviewed_at,
            materialized_at=request.materialized_at,
        )

    @staticmethod
    def _payload_values(payload: ProjectRequestPayload) -> dict[str, Any]:
        return {
            "parent_workspace_id": payload.parent_workspace_id,
            "project_template_config_id": payload.project_template_config_id,
            "project_name": payload.project_name.strip(),
            "description": payload.description.strip(),
            "project_manager_user_id": payload.project_manager_user_id,
            "planned_start": payload.planned_start,
            "planned_finish": payload.planned_finish,
            "currency_code": payload.currency_code.strip().upper(),
            "estimated_budget": payload.estimated_budget,
            "project_type": payload.project_type or None,
            "project_phase": payload.project_phase or None,
            "priority": payload.priority or None,
            "country": payload.country or None,
            "region": payload.region or None,
            "strategic_objective_codes": list(payload.strategic_objective_codes),
        }

    @staticmethod
    def _request_values(request: ProjectCreationRequest) -> dict[str, Any]:
        return {
            "parent_workspace_id": request.parent_workspace_id,
            "project_template_config_id": request.project_template_config_id,
            "project_name": request.project_name,
            "description": request.description,
            "project_manager_user_id": request.project_manager_user_id,
            "planned_start": request.planned_start,
            "planned_finish": request.planned_finish,
            "currency_code": request.currency_code,
            "estimated_budget": request.estimated_budget,
            "project_type": request.project_type,
            "project_phase": request.project_phase,
            "priority": request.priority,
            "country": request.country,
            "region": request.region,
            "strategic_objective_codes": list(request.strategic_objective_codes or []),
        }

    @staticmethod
    def _workspace_fingerprint(workspace: EnterpriseWorkspace) -> dict[str, Any]:
        return {
            "id": workspace.id,
            "tenant_id": workspace.tenant_id,
            "parent_id": workspace.parent_id,
            "workspace_type_code": workspace.workspace_type_code,
            "record_code": workspace.record_code,
            "status": workspace.status,
            "version": workspace.version,
        }

    @staticmethod
    def _configuration_fingerprint(configuration: AdminConfiguration) -> dict[str, Any]:
        return {
            "id": configuration.id,
            "kind": configuration.kind,
            "code": configuration.code,
            "status": configuration.status,
            "revision": configuration.revision,
            "version": configuration.version,
            "content_hash": configuration.content_hash,
        }

    def _workspace_path(self, workspace: EnterpriseWorkspace) -> list[EnterpriseWorkspace]:
        path = [workspace]
        current = workspace
        visited = {workspace.id}
        while current.parent_id is not None:
            current = self.db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id == current.parent_id,
                )
            )
            if current is None or current.id in visited:
                break
            visited.add(current.id)
            path.append(current)
        return list(reversed(path))

    @staticmethod
    def _raise_issues(issues: list[str]) -> None:
        if issues:
            raise HTTPException(
                status_code=422,
                detail={"code": "PROJECT_CREATION_VALIDATION_FAILED", "issues": sorted(set(issues))},
            )


def _content_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _json_compatible(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _deduplicate_classifications(values: list[dict[str, str]]) -> list[dict[str, str]]:
    selected: dict[tuple[str, str], dict[str, str]] = {}
    for value in values:
        key = (str(value.get("category_set_code", "")), str(value.get("category_item_code", "")))
        if key[0] and key[1]:
            selected[key] = {
                "category_set_code": key[0],
                "category_item_code": key[1],
                "source": str(value.get("source", "configuration")),
            }
    return [selected[key] for key in sorted(selected)]


def _date_value(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
