"""One governed creation engine parameterized by PROPERTY, FACILITY or WAREHOUSE."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
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
from app.modules.enterprise_structure.constants import WORKSPACE_TYPE_SEED
from app.modules.enterprise_structure.models import EnterpriseWorkspaceClassification
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext, ensure_enterprise_permissions
from app.modules.enterprise_structure.physical_configuration import CREATION_TYPES, NUMBERING
from app.modules.enterprise_structure.record_codes import next_record_code
from app.modules.physical_workspace_creation.models import PhysicalWorkspaceCreationRequest
from app.modules.physical_workspace_creation.schemas import (
    PhysicalDynamicAttribute,
    PhysicalLocationOption,
    PhysicalResponsibleOption,
    PhysicalTemplateOption,
    PhysicalWorkspaceCreationOptionsOut,
    PhysicalWorkspaceCreationState,
    PhysicalWorkspaceMaterializationOut,
    PhysicalWorkspaceOverviewOut,
    PhysicalWorkspaceRequestCreate,
    PhysicalWorkspaceRequestOut,
    PhysicalWorkspaceRequestPayload,
    PhysicalWorkspaceRequestPreviewOut,
    PhysicalWorkspaceRequestUpdate,
    PhysicalWorkspaceTypeOption,
)
from app.modules.physical_workspace_initialization.models import PhysicalWorkspaceInitialization

REQUEST_NUMBER_RULE = "physical-workspace-creation-request"
CREATABLE_TYPES = frozenset(CREATION_TYPES)
PRIVILEGED_ROLES = frozenset(
    {
        "organization_admin",
        "physical_workspace_reviewer",
        "physical_workspace_approver",
        "physical_workspace_materialization_service",
    }
)

ATTRIBUTE_DEFINITIONS: dict[str, list[tuple[str, str, str]]] = {
    "property": [
        ("property_type", "Property Type", "classification"),
        ("ownership_tenure", "Ownership / Tenure", "text"),
        ("legal_status", "Legal Status", "text"),
        ("country", "Country", "text"),
        ("state_department", "State / Department", "text"),
        ("municipality_city", "Municipality / City", "text"),
        ("address", "Address", "text"),
        ("postal_code", "Postal Code", "text"),
        ("latitude", "Latitude", "decimal"),
        ("longitude", "Longitude", "decimal"),
        ("land_area", "Land Area", "decimal"),
        ("built_area", "Built Area", "decimal"),
        ("acquisition_date", "Acquisition Date", "date"),
        ("book_value", "Book Value", "decimal"),
        ("market_value", "Market Value", "decimal"),
        ("responsible_area", "Responsible Area", "text"),
        ("operational_status", "Operational Status", "text"),
    ],
    "facility": [
        ("facility_type", "Facility Type", "classification"),
        ("operational_status", "Operational Status", "text"),
        ("commissioning_date", "Commissioning Date", "date"),
        ("gross_area", "Gross Area", "decimal"),
        ("usable_area", "Usable Area", "decimal"),
        ("capacity", "Capacity", "decimal"),
        ("criticality", "Criticality", "text"),
        ("country", "Country", "text"),
        ("state_department", "State / Department", "text"),
        ("municipality_city", "Municipality / City", "text"),
        ("address", "Address", "text"),
        ("postal_code", "Postal Code", "text"),
        ("latitude", "Latitude", "decimal"),
        ("longitude", "Longitude", "decimal"),
    ],
    "warehouse": [
        ("warehouse_type", "Warehouse Type", "classification"),
        ("operational_status", "Operational Status", "text"),
        ("country", "Country", "text"),
        ("state_department", "State / Department", "text"),
        ("municipality_city", "Municipality / City", "text"),
        ("address", "Address", "text"),
        ("postal_code", "Postal Code", "text"),
        ("storage_capacity", "Storage Capacity", "decimal"),
        ("unit_of_capacity", "Unit of Capacity", "text"),
        ("criticality", "Criticality", "text"),
    ],
}


class PhysicalWorkspaceCreationService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def ensure_seed(self) -> None:
        """Install only generic RBAC and the request sequence; never publish Gate 06A drafts."""
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
        self.db.commit()

    def options(
        self,
        workspace_type_code: str | None = None,
        parent_workspace_id: int | None = None,
    ) -> PhysicalWorkspaceCreationOptionsOut:
        selected = self._normalize_optional_type(workspace_type_code)
        types = [
            PhysicalWorkspaceTypeOption(
                code=code,
                name=str(WORKSPACE_TYPE_SEED[code]["name"]),
                domain_description=str(WORKSPACE_TYPE_SEED[code].get("domain_description", "")),
            )
            for code in CREATION_TYPES
        ]
        policy = self._policy(selected) if selected else None
        locations = self._eligible_locations(selected, policy) if selected and policy else []
        parent_type = next(
            (item.workspace_type_code for item in locations if item.id == parent_workspace_id),
            None,
        )
        templates = self._published_templates(selected, parent_type) if selected else []
        responsibles = [
            PhysicalResponsibleOption(id=item.id, name=item.full_name, email=item.email)
            for item in self.db.scalars(
                select(UserAccount)
                .where(UserAccount.tenant_id == self.tenant_id, UserAccount.status == "active")
                .order_by(UserAccount.full_name)
            ).all()
        ]
        classifications = self._classification_options(selected) if selected else {}
        dynamic_attributes = self._dynamic_attributes(selected, classifications) if selected else []
        blocked = None
        if selected and policy is None:
            blocked = "PHYSICAL_CREATION_POLICY_NOT_PUBLISHED"
        elif selected and not templates:
            blocked = "NO_PUBLISHED_PHYSICAL_WORKSPACE_TEMPLATE"
        return PhysicalWorkspaceCreationOptionsOut(
            workspace_types=types,
            selected_workspace_type=selected,
            locations=locations,
            templates=templates,
            responsibles=responsibles,
            dynamic_attributes=dynamic_attributes,
            classifications=classifications,
            creation_policy=self._configuration_view(policy) if policy else None,
            blocked_reason=blocked,
        )

    def create_request(self, payload: PhysicalWorkspaceRequestCreate) -> PhysicalWorkspaceRequestOut:
        self._assert_creatable_type(payload.workspace_type_code)
        issues, _governance = self._validate_payload(payload, require_published=True)
        self._raise_issues(issues)
        request = PhysicalWorkspaceCreationRequest(
            tenant_id=self.tenant_id,
            request_number=self._reserve_request_number(),
            workspace_type_code=payload.workspace_type_code,
            state=PhysicalWorkspaceCreationState.draft,
            requestor_user_id=self.actor_id,
            parent_workspace_id=payload.parent_workspace_id,
            template_config_id=payload.template_config_id,
            workspace_name=payload.workspace_name,
            description=payload.description,
            responsible_user_id=payload.responsible_user_id,
            attributes_json=dict(payload.attributes),
            classification_values_json=[item.model_dump() for item in payload.classifications],
            revision_version=1,
            last_modified_by_user_id=self.actor_id,
        )
        self.db.add(request)
        self.db.flush()
        self._event("physical_workspace_creation.request_created", request, None, "draft")
        self.db.commit()
        self.db.refresh(request)
        return self._out(request)

    def list_requests(
        self,
        context: EnterprisePermissionContext,
        *,
        state: str = "",
        workspace_type: str = "",
        search: str = "",
        review_queue: bool = False,
    ) -> list[PhysicalWorkspaceRequestOut]:
        statement = select(PhysicalWorkspaceCreationRequest).where(
            PhysicalWorkspaceCreationRequest.tenant_id == self.tenant_id
        )
        privileged = bool(context.role_codes & PRIVILEGED_ROLES)
        if review_queue:
            if not privileged:
                return []
            statement = statement.where(
                PhysicalWorkspaceCreationRequest.state.in_(["submitted", "under_review", "approved", "failed"])
            )
        elif not privileged:
            statement = statement.where(PhysicalWorkspaceCreationRequest.requestor_user_id == self.actor_id)
        if state.strip():
            statement = statement.where(PhysicalWorkspaceCreationRequest.state == state.strip().lower())
        if workspace_type.strip():
            normalized = self._normalize_type(workspace_type)
            self._assert_creatable_type(normalized)
            statement = statement.where(PhysicalWorkspaceCreationRequest.workspace_type_code == normalized)
        if search.strip():
            term = f"%{search.strip().lower()}%"
            statement = statement.where(
                func.lower(PhysicalWorkspaceCreationRequest.request_number).like(term)
                | func.lower(PhysicalWorkspaceCreationRequest.workspace_name).like(term)
            )
        rows = self.db.scalars(statement.order_by(PhysicalWorkspaceCreationRequest.created_at.desc())).all()
        return [self._out(item) for item in rows]

    def get_request(self, request_id: int, context: EnterprisePermissionContext) -> PhysicalWorkspaceRequestOut:
        request = self._request(request_id)
        self._ensure_read_access(request, context)
        return self._out(request)

    def update_request(
        self,
        request_id: int,
        payload: PhysicalWorkspaceRequestUpdate,
        expected_version: int,
    ) -> PhysicalWorkspaceRequestOut:
        self._assert_creatable_type(payload.workspace_type_code)
        request = self._request(request_id, lock=True)
        self._ensure_owner(request)
        self._require_version(request, expected_version)
        if request.state not in {PhysicalWorkspaceCreationState.draft, PhysicalWorkspaceCreationState.returned}:
            raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_REQUEST_NOT_EDITABLE")
        issues, _governance = self._validate_payload(payload, require_published=True)
        self._raise_issues(issues)
        before = request.state
        self._apply_payload(request, payload)
        request.state = PhysicalWorkspaceCreationState.draft
        request.submitted_snapshot_json = {}
        request.submitted_hash = None
        request.approval_hash = None
        request.approved_at = None
        request.approved_by_user_id = None
        request.decision_reason = None
        request.failure_reason = None
        self._touch(request)
        self._event("physical_workspace_creation.request_updated", request, before, request.state)
        return self._commit_out(request)

    def preview(self, request_id: int, context: EnterprisePermissionContext) -> PhysicalWorkspaceRequestPreviewOut:
        request = self._request(request_id)
        self._ensure_read_access(request, context)
        issues, governance = self._validate_request(request, require_published=True)
        parent = governance.get("parent")
        template = governance.get("template")
        policy = governance.get("policy")
        numbering = governance.get("numbering")
        if any(item is None for item in (parent, template, policy, numbering)):
            self._raise_issues(issues)
        sibling_codes = list(
            self.db.scalars(
                select(EnterpriseWorkspace.record_code).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.parent_id == parent.id,
                )
            ).all()
        )
        business_number = self._number_preview(numbering)
        record_code = next_record_code(parent.record_code, sibling_codes)
        request.business_number_preview = business_number
        request.record_code_preview = record_code
        return PhysicalWorkspaceRequestPreviewOut(
            allowed=not issues,
            issues=issues,
            warnings=[],
            workspace_type={"code": request.workspace_type_code, "name": request.workspace_type_code.upper()},
            parent=self._workspace_view(parent),
            parent_record_code=parent.record_code,
            projected_record_code=record_code,
            projected_business_number=business_number,
            template=self._configuration_view(template),
            creation_policy=self._configuration_view(policy),
            applicable_classifications=list(governance.get("applicable_classifications", [])),
            selected_classifications=list(governance.get("classifications", [])),
            enabled_modules=list(governance.get("modules", [])),
            planned_modules=list(WORKSPACE_TYPE_SEED[request.workspace_type_code].get("planned_modules", [])),
            initial_workspace_status=str(policy.content_json.get("initial_workspace_status", "pending")),
            persisted=False,
        )

    def submit(self, request_id: int, expected_version: int) -> PhysicalWorkspaceRequestOut:
        request = self._request(request_id, lock=True)
        self._ensure_owner(request)
        self._require_version(request, expected_version)
        if request.state != PhysicalWorkspaceCreationState.draft:
            raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_REQUEST_MUST_BE_DRAFT")
        issues, governance = self._validate_request(request, require_published=True)
        self._raise_issues(issues)
        snapshot = self._snapshot(request, governance)
        request.submitted_snapshot_json = snapshot
        request.submitted_hash = _content_hash(snapshot)
        request.submitted_at = utc_now()
        self._transition(request, PhysicalWorkspaceCreationState.submitted, "physical_workspace_creation.submitted")
        return self._commit_out(request)

    def cancel(self, request_id: int, expected_version: int) -> PhysicalWorkspaceRequestOut:
        request = self._request(request_id, lock=True)
        self._ensure_owner(request)
        self._require_version(request, expected_version)
        if request.state not in {
            PhysicalWorkspaceCreationState.draft,
            PhysicalWorkspaceCreationState.submitted,
            PhysicalWorkspaceCreationState.returned,
        }:
            raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_REQUEST_CANNOT_BE_CANCELLED")
        self._transition(request, PhysicalWorkspaceCreationState.cancelled, "physical_workspace_creation.cancelled")
        return self._commit_out(request)

    def start_review(self, request_id: int, expected_version: int) -> PhysicalWorkspaceRequestOut:
        request = self._request(request_id, lock=True)
        self._require_version(request, expected_version)
        if request.state != PhysicalWorkspaceCreationState.submitted:
            raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_REQUEST_MUST_BE_SUBMITTED")
        request.reviewed_at = utc_now()
        self._transition(
            request,
            PhysicalWorkspaceCreationState.under_review,
            "physical_workspace_creation.review_started",
        )
        return self._commit_out(request)

    def return_request(self, request_id: int, expected_version: int, reason: str) -> PhysicalWorkspaceRequestOut:
        request = self._request(request_id, lock=True)
        self._require_version(request, expected_version)
        if request.state not in {
            PhysicalWorkspaceCreationState.submitted,
            PhysicalWorkspaceCreationState.under_review,
        }:
            raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_REQUEST_CANNOT_BE_RETURNED")
        request.decision_reason = reason
        self._transition(request, PhysicalWorkspaceCreationState.returned, "physical_workspace_creation.returned")
        return self._commit_out(request)

    def reject(self, request_id: int, expected_version: int, reason: str) -> PhysicalWorkspaceRequestOut:
        request = self._request(request_id, lock=True)
        self._require_version(request, expected_version)
        if request.state != PhysicalWorkspaceCreationState.under_review:
            raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_REQUEST_MUST_BE_UNDER_REVIEW")
        request.decision_reason = reason
        self._transition(request, PhysicalWorkspaceCreationState.rejected, "physical_workspace_creation.rejected")
        return self._commit_out(request)

    def approve(self, request_id: int, expected_version: int) -> PhysicalWorkspaceRequestOut:
        request = self._request(request_id, lock=True)
        self._require_version(request, expected_version)
        if request.state != PhysicalWorkspaceCreationState.under_review:
            raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_REQUEST_MUST_BE_UNDER_REVIEW")
        if request.requestor_user_id == self.actor_id or request.last_modified_by_user_id == self.actor_id:
            raise HTTPException(status_code=403, detail="FOUR_EYES_VIOLATION")
        issues, governance = self._validate_request(request, require_published=True)
        self._raise_issues(issues)
        request.approval_hash = self._approval_hash(request, governance)
        request.approved_by_user_id = self.actor_id
        request.approved_at = utc_now()
        self._transition(request, PhysicalWorkspaceCreationState.approved, "physical_workspace_creation.approved")
        return self._commit_out(request)

    def materialize(
        self,
        request_id: int,
        expected_version: int,
        *,
        failure_injector: Callable[[EnterpriseWorkspace], None] | None = None,
    ) -> PhysicalWorkspaceMaterializationOut:
        try:
            request = self._request(request_id, lock=True)
            if request.state == PhysicalWorkspaceCreationState.created and request.materialized_workspace_id:
                return PhysicalWorkspaceMaterializationOut(
                    result="ALREADY_CREATED",
                    request_id=request.id,
                    request_number=request.request_number,
                    state=PhysicalWorkspaceCreationState.created,
                    materialized_workspace_id=request.materialized_workspace_id,
                    business_number=request.materialized_business_number or "",
                    record_code=request.materialized_record_code or "",
                    mutation_count=0,
                )
            self._require_version(request, expected_version)
            if request.state != PhysicalWorkspaceCreationState.approved:
                raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_REQUEST_MUST_BE_APPROVED")
            issues, governance = self._validate_request(request, require_published=True, lock=True)
            self._raise_issues(issues)
            if request.approval_hash != self._approval_hash(request, governance):
                raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_APPROVAL_INVALIDATED")
            parent: EnterpriseWorkspace = governance["parent"]
            template: AdminConfiguration = governance["template"]
            request.state = PhysicalWorkspaceCreationState.materializing
            self._event(
                "physical_workspace_creation.materialization_started",
                request,
                PhysicalWorkspaceCreationState.approved,
                PhysicalWorkspaceCreationState.materializing,
            )
            business_number = self._reserve_business_number(request.workspace_type_code)
            sibling_codes = list(
                self.db.scalars(
                    select(EnterpriseWorkspace.record_code).where(
                        EnterpriseWorkspace.tenant_id == self.tenant_id,
                        EnterpriseWorkspace.parent_id == parent.id,
                    )
                ).all()
            )
            record_code = next_record_code(parent.record_code, sibling_codes)
            metadata = self._physical_metadata(request, template, governance["modules"], business_number)
            workspace = EnterpriseWorkspace(
                tenant_id=self.tenant_id,
                parent_id=parent.id,
                workspace_type_code=request.workspace_type_code,
                code=business_number,
                external_key=f"{request.workspace_type_code.upper()}-{uuid4()}",
                record_code=record_code,
                name=request.workspace_name,
                status="pending",
                defaults_json={"_physical": metadata},
                sort_order=100,
                version=1,
                created_by_user_id=self.actor_id,
            )
            self.db.add(workspace)
            self.db.flush()
            if failure_injector:
                failure_injector(workspace)
            self._persist_classifications(workspace, governance["classifications"])
            self._persist_modules(workspace, governance["modules"])
            self._persist_responsible_assignment(workspace, request.responsible_user_id)
            request.materialized_workspace_id = workspace.id
            request.materialized_business_number = business_number
            request.materialized_record_code = record_code
            request.materialized_at = utc_now()
            request.failure_reason = None
            request.state = PhysicalWorkspaceCreationState.created
            self._touch(request)
            self._event(
                "physical_workspace_creation.workspace_created",
                request,
                PhysicalWorkspaceCreationState.materializing,
                PhysicalWorkspaceCreationState.created,
                {"workspace_id": workspace.id, "business_number": business_number, "record_code": record_code},
            )
            self.db.commit()
            return PhysicalWorkspaceMaterializationOut(
                result="CREATED",
                request_id=request.id,
                request_number=request.request_number,
                state=PhysicalWorkspaceCreationState.created,
                materialized_workspace_id=workspace.id,
                business_number=business_number,
                record_code=record_code,
                mutation_count=1,
            )
        except HTTPException:
            self.db.rollback()
            raise
        except IntegrityError as exc:
            self.db.rollback()
            self._record_failure(request_id, str(exc), mark_failed=True)
            raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_MATERIALIZATION_INTEGRITY_FAILURE") from exc
        except Exception as exc:
            self.db.rollback()
            self._record_failure(request_id, str(exc), mark_failed=False)
            raise

    def overview(self, workspace_id: int, context: EnterprisePermissionContext) -> PhysicalWorkspaceOverviewOut:
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.id == workspace_id,
                EnterpriseWorkspace.workspace_type_code.in_(CREATABLE_TYPES),
            )
        )
        if workspace is None or (not context.organization_wide and workspace.id not in context.workspace_ids):
            raise HTTPException(status_code=404, detail="Physical Workspace not found")
        metadata = workspace.defaults_json.get("_physical", {})
        parent = self.db.get(EnterpriseWorkspace, workspace.parent_id) if workspace.parent_id else None
        responsible = self.db.get(UserAccount, metadata.get("responsible_user_id"))
        classifications = [
            {"category_set_code": item.category_set_code, "category_item_code": item.category_item_code}
            for item in self.db.scalars(
                select(EnterpriseWorkspaceClassification).where(
                    EnterpriseWorkspaceClassification.tenant_id == self.tenant_id,
                    EnterpriseWorkspaceClassification.workspace_id == workspace.id,
                )
            ).all()
        ]
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
            select(PhysicalWorkspaceInitialization).where(
                PhysicalWorkspaceInitialization.tenant_id == self.tenant_id,
                PhysicalWorkspaceInitialization.workspace_id == workspace.id,
            )
        )
        common = list(initialization.common_checklist_json) if initialization else []
        specific = list(initialization.type_specific_checklist_json) if initialization else []
        checklist = [*common, *specific]
        initialization_state = (
            initialization.state if initialization else ("ACTIVATED" if workspace.status == "active" else "NOT_STARTED")
        )
        completed = sum(1 for item in checklist if item.get("status") in {"PASS", "WARNING"})
        progress = (
            round(completed / len(checklist) * 100)
            if checklist
            else (100 if initialization_state == "ACTIVATED" else 0)
        )
        role_codes = set(context.role_codes)
        return PhysicalWorkspaceOverviewOut(
            workspace_id=workspace.id,
            workspace_type_code=workspace.workspace_type_code,
            workspace_name=workspace.name,
            business_number=str(metadata.get("business_number", workspace.code)),
            record_code=workspace.record_code,
            status=workspace.status,
            parent_workspace=parent.name if parent else "",
            responsible=responsible.full_name if responsible else "",
            template=str(metadata.get("template_code", "")),
            creation_request_id=metadata.get("creation_request_id"),
            creation_request_number=str(metadata.get("creation_request_number", "")),
            created_at=workspace.created_at,
            attributes=dict(metadata.get("attributes", {})),
            classifications=classifications,
            enabled_modules=modules,
            planned_modules=list(metadata.get("planned_modules", [])),
            initialization_state=initialization_state,
            initialization_progress_percent=progress,
            initialization_blocker_count=sum(
                1 for item in checklist if item.get("blocking") and item.get("status") == "FAIL"
            ),
            initialization_warning_count=sum(1 for item in checklist if item.get("status") == "WARNING"),
            blocking_issues=[
                str(item.get("code", "")) for item in checklist if item.get("blocking") and item.get("status") == "FAIL"
            ],
            warnings=[str(item.get("code", "")) for item in checklist if item.get("status") == "WARNING"],
            template_revision=metadata.get("template_revision"),
            module_states=dict(initialization.module_states_json) if initialization else {},
            activated_at=initialization.activated_at if initialization else None,
            activated_by_user_id=initialization.activated_by_user_id if initialization else None,
            initialization_revision_version=initialization.revision_version if initialization else workspace.version,
            can_initialize=bool(role_codes & {"organization_admin", "physical_workspace_initializer"})
            and workspace.status == "pending",
            can_activate=bool(role_codes & {"organization_admin", "physical_workspace_activator"})
            and workspace.status == "pending"
            and initialization_state == "READY_FOR_ACTIVATION",
        )

    def _validate_payload(
        self, payload: PhysicalWorkspaceRequestPayload, *, require_published: bool
    ) -> tuple[list[str], dict[str, Any]]:
        probe = PhysicalWorkspaceCreationRequest(
            tenant_id=self.tenant_id,
            request_number="PREVIEW",
            workspace_type_code=payload.workspace_type_code,
            state="draft",
            requestor_user_id=self.actor_id,
            parent_workspace_id=payload.parent_workspace_id,
            template_config_id=payload.template_config_id,
            workspace_name=payload.workspace_name,
            description=payload.description,
            responsible_user_id=payload.responsible_user_id,
            attributes_json=dict(payload.attributes),
            classification_values_json=[item.model_dump() for item in payload.classifications],
            revision_version=1,
            last_modified_by_user_id=self.actor_id,
        )
        return self._validate_request(probe, require_published=require_published)

    def _validate_request(
        self,
        request: PhysicalWorkspaceCreationRequest,
        *,
        require_published: bool,
        lock: bool = False,
    ) -> tuple[list[str], dict[str, Any]]:
        issues: list[str] = []
        type_code = self._normalize_type(request.workspace_type_code)
        if type_code not in CREATABLE_TYPES:
            issues.append(f"WORKSPACE_TYPE_NOT_CREATABLE:{type_code.upper()}")
        parent_stmt = select(EnterpriseWorkspace).where(
            EnterpriseWorkspace.tenant_id == self.tenant_id,
            EnterpriseWorkspace.id == request.parent_workspace_id,
        )
        template_stmt = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.id == request.template_config_id,
            AdminConfiguration.kind == "physical_template",
        )
        if lock:
            parent_stmt = parent_stmt.with_for_update()
            template_stmt = template_stmt.with_for_update()
        parent = self.db.scalar(parent_stmt)
        template = self.db.scalar(template_stmt)
        policy = self._policy(type_code)
        numbering = self._latest_configuration("numbering_rule", NUMBERING.get(type_code, ("", ""))[0], True)
        workspace_type = self._latest_configuration("workspace_type", type_code, True)
        allowed_parents = list(policy.content_json.get("allowed_parent_types", [])) if policy else []
        if parent is None:
            issues.append("PARENT_WORKSPACE_NOT_FOUND")
        else:
            if parent.status != "active":
                issues.append("PARENT_WORKSPACE_NOT_ACTIVE")
            if parent.workspace_type_code not in allowed_parents:
                issues.append("PHYSICAL_CREATION_POLICY_BLOCKS_PARENT")
            parent_type = self._latest_configuration("workspace_type", parent.workspace_type_code, True)
            if parent_type is None or type_code not in parent_type.content_json.get("allowed_children", []):
                issues.append("COMPOSITION_RULE_BLOCKS_PHYSICAL_WORKSPACE")
        if template is None:
            issues.append("PHYSICAL_WORKSPACE_TEMPLATE_NOT_FOUND")
        else:
            if require_published and template.status != "published":
                issues.append("NO_PUBLISHED_PHYSICAL_WORKSPACE_TEMPLATE")
            if template.content_json.get("workspace_type_code") != type_code:
                issues.append("PHYSICAL_TEMPLATE_WRONG_WORKSPACE_TYPE")
            if parent and parent.workspace_type_code not in template.content_json.get("applicable_parent_types", []):
                issues.append("PHYSICAL_TEMPLATE_NOT_APPLICABLE")
        if policy is None:
            issues.append("PHYSICAL_CREATION_POLICY_NOT_PUBLISHED")
        if numbering is None:
            issues.append("PHYSICAL_NUMBERING_NOT_PUBLISHED")
        responsible = self.db.scalar(
            select(UserAccount).where(
                UserAccount.tenant_id == self.tenant_id,
                UserAccount.id == request.responsible_user_id,
                UserAccount.status == "active",
            )
        )
        if responsible is None:
            issues.append("PHYSICAL_WORKSPACE_RESPONSIBLE_REQUIRED")
        if not request.workspace_name.strip():
            issues.append("PHYSICAL_WORKSPACE_NAME_REQUIRED")
        required_attributes = set()
        if workspace_type:
            required_attributes.update(
                self._attribute_code(item)
                for item in workspace_type.content_json.get("required_fields", [])
                if self._attribute_code(item) not in {"code", "name"}
            )
        if template:
            required_attributes.update(map(self._attribute_code, template.content_json.get("required_attributes", [])))
        if policy:
            required_attributes.update(map(self._attribute_code, policy.content_json.get("required_attributes", [])))
        missing = sorted(item for item in required_attributes if request.attributes_json.get(item) in (None, "", []))
        if missing:
            issues.append(f"REQUIRED_ATTRIBUTES_MISSING:{','.join(missing)}")
        classifications = self._normalize_classifications(request.classification_values_json)
        applicable = list(workspace_type.content_json.get("required_categories", [])) if workspace_type else []
        if template:
            classifications = self._merge_classifications(
                list(template.content_json.get("default_classifications", [])), classifications
            )
        selected_sets = {item["category_set_code"] for item in classifications}
        missing_categories = sorted(set(applicable) - selected_sets)
        if missing_categories:
            issues.append(f"REQUIRED_CLASSIFICATIONS_MISSING:{','.join(missing_categories)}")
        for item in classifications:
            options = self._classification_options(type_code).get(item["category_set_code"], [])
            if not any(option["code"] == item["category_item_code"] for option in options):
                issues.append(f"CLASSIFICATION_NOT_AVAILABLE:{item['category_set_code']}/{item['category_item_code']}")
        modules: list[str] = []
        if template:
            requested = set(template.content_json.get("enabled_modules", []))
            available = set(
                self.db.scalars(
                    select(AdminConfiguration.code).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == "module_definition",
                        AdminConfiguration.status == "published",
                    )
                ).all()
            )
            unknown = sorted(requested - available)
            if unknown:
                issues.append(f"MODULE_DEFINITION_NOT_PUBLISHED:{','.join(unknown)}")
            modules = sorted(requested & available)
        return issues, {
            "workspace_type": workspace_type,
            "parent": parent,
            "template": template,
            "policy": policy,
            "numbering": numbering,
            "responsible": responsible,
            "classifications": classifications,
            "applicable_classifications": applicable,
            "modules": modules,
        }

    def _snapshot(self, request: PhysicalWorkspaceCreationRequest, governance: dict[str, Any]) -> dict[str, Any]:
        return {
            "request": self._request_values(request),
            "workspace_type": self._configuration_fingerprint(governance["workspace_type"]),
            "parent": self._workspace_fingerprint(governance["parent"]),
            "template": self._configuration_fingerprint(governance["template"]),
            "policy": self._configuration_fingerprint(governance["policy"]),
            "numbering": self._configuration_fingerprint(governance["numbering"]),
            "classifications": governance["classifications"],
            "modules": governance["modules"],
        }

    def _approval_hash(self, request: PhysicalWorkspaceCreationRequest, governance: dict[str, Any]) -> str:
        return _content_hash({"submitted_hash": request.submitted_hash, **self._snapshot(request, governance)})

    def _physical_metadata(
        self,
        request: PhysicalWorkspaceCreationRequest,
        template: AdminConfiguration,
        modules: list[str],
        business_number: str,
    ) -> dict[str, Any]:
        return {
            "workspace_type_code": request.workspace_type_code,
            "business_number": business_number,
            "description": request.description,
            "responsible_user_id": request.responsible_user_id,
            "attributes": dict(request.attributes_json),
            "template_id": template.id,
            "template_code": template.code,
            "template_revision": template.revision,
            "template_content_hash": template.content_hash,
            "enabled_modules": modules,
            "planned_modules": list(WORKSPACE_TYPE_SEED[request.workspace_type_code].get("planned_modules", [])),
            "creation_request_id": request.id,
            "creation_request_number": request.request_number,
        }

    def _persist_classifications(self, workspace: EnterpriseWorkspace, values: list[dict[str, str]]) -> None:
        for item in values:
            self.db.add(
                EnterpriseWorkspaceClassification(
                    tenant_id=self.tenant_id,
                    workspace_id=workspace.id,
                    category_set_code=item["category_set_code"],
                    category_item_code=item["category_item_code"],
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

    def _persist_responsible_assignment(self, workspace: EnterpriseWorkspace, responsible_id: int) -> None:
        role = self.db.scalar(
            select(SecurityRole).where(
                SecurityRole.tenant_id == self.tenant_id,
                SecurityRole.code == "physical_workspace_responsible",
                SecurityRole.status == "active",
            )
        )
        if role is None:
            raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_RESPONSIBLE_ROLE_NOT_CONFIGURED")
        self.db.add(
            SecurityAccessAssignment(
                tenant_id=self.tenant_id,
                subject_type="user",
                user_id=responsible_id,
                role_id=role.id,
                scope_type="workspace",
                workspace_id=workspace.id,
                status="active",
                granted_by_user_id=self.actor_id,
            )
        )

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
            raise HTTPException(status_code=409, detail="PHYSICAL_REQUEST_SEQUENCE_NOT_INITIALIZED")
        return f"PWR-{value:05d}"

    def _reserve_business_number(self, type_code: str) -> str:
        rule_code = NUMBERING[type_code][0]
        rule = self._latest_configuration("numbering_rule", rule_code, True)
        value = self.db.scalar(
            update(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == rule_code,
                AdminNumberSequence.scope_key == "tenant",
            )
            .values(
                next_value=AdminNumberSequence.next_value + 1,
                version=AdminNumberSequence.version + 1,
                updated_at=utc_now(),
            )
            .returning(AdminNumberSequence.next_value - 1)
        )
        if rule is None or value is None:
            raise HTTPException(status_code=409, detail="PHYSICAL_NUMBER_SEQUENCE_NOT_INITIALIZED")
        return self._format_number(rule, value)

    def _number_preview(self, rule: AdminConfiguration) -> str:
        sequence = self.db.scalar(
            select(AdminNumberSequence).where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == rule.code,
                AdminNumberSequence.scope_key == "tenant",
            )
        )
        return self._format_number(rule, sequence.next_value if sequence else 1)

    @staticmethod
    def _format_number(rule: AdminConfiguration, value: int) -> str:
        content = rule.content_json
        return str(content["pattern"]).format(prefix=content["prefix"], sequence=value)

    def _eligible_locations(self, type_code: str, policy: AdminConfiguration) -> list[PhysicalLocationOption]:
        allowed = list(policy.content_json.get("allowed_parent_types", []))
        rows = list(
            self.db.scalars(
                select(EnterpriseWorkspace)
                .where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.workspace_type_code.in_(allowed),
                    EnterpriseWorkspace.status == "active",
                )
                .order_by(EnterpriseWorkspace.record_code)
            ).all()
        )
        result: list[PhysicalLocationOption] = []
        for item in rows:
            parent_type = self._latest_configuration("workspace_type", item.workspace_type_code, True)
            if parent_type is None or type_code not in parent_type.content_json.get("allowed_children", []):
                continue
            result.append(
                PhysicalLocationOption(
                    id=item.id,
                    workspace_type_code=item.workspace_type_code,
                    name=item.name,
                    record_code=item.record_code,
                    path=[workspace.name for workspace in self._workspace_path(item)],
                )
            )
        return result

    def _published_templates(self, type_code: str, parent_type: str | None) -> list[PhysicalTemplateOption]:
        rows = self.db.scalars(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == "physical_template",
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.name)
        ).all()
        return [
            PhysicalTemplateOption(
                id=item.id,
                code=item.code,
                name=item.name,
                workspace_type_code=type_code,
                applicable_parent_types=list(item.content_json.get("applicable_parent_types", [])),
                enabled_modules=list(item.content_json.get("enabled_modules", [])),
            )
            for item in rows
            if item.content_json.get("workspace_type_code") == type_code
            and (parent_type is None or parent_type in item.content_json.get("applicable_parent_types", []))
        ]

    def _policy(self, type_code: str | None) -> AdminConfiguration | None:
        return (
            self._latest_configuration("creation_policy", f"physical-{type_code}-creation", True)
            if type_code in CREATABLE_TYPES
            else None
        )

    def _classification_options(self, type_code: str) -> dict[str, list[dict[str, str]]]:
        result: dict[str, list[dict[str, str]]] = {}
        for category_code in WORKSPACE_TYPE_SEED[type_code].get("required_categories", []):
            catalog = self._latest_configuration("catalog", category_code, True)
            result[category_code] = (
                [
                    {"code": str(item.get("code", "")), "label": str(item.get("label", ""))}
                    for item in catalog.content_json.get("items", [])
                ]
                if catalog and type_code in catalog.content_json.get("applicable_types", [])
                else []
            )
        return result

    def _dynamic_attributes(
        self, type_code: str, classifications: dict[str, list[dict[str, str]]]
    ) -> list[PhysicalDynamicAttribute]:
        required = {self._attribute_code(item) for item in WORKSPACE_TYPE_SEED[type_code].get("required_fields", [])}
        return [
            PhysicalDynamicAttribute(
                code=code,
                label=label,
                input_type=input_type,
                required=code in required,
                options=classifications.get(f"{type_code}-type", []) if input_type == "classification" else [],
            )
            for code, label, input_type in ATTRIBUTE_DEFINITIONS[type_code]
        ]

    def _latest_configuration(self, kind: str, code: str, published_only: bool) -> AdminConfiguration | None:
        if not code:
            return None
        statement = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == kind,
            AdminConfiguration.code == code,
        )
        if published_only:
            statement = statement.where(AdminConfiguration.status == "published")
        return self.db.scalar(statement.order_by(AdminConfiguration.revision.desc()).limit(1))

    def _request(self, request_id: int, *, lock: bool = False) -> PhysicalWorkspaceCreationRequest:
        statement = select(PhysicalWorkspaceCreationRequest).where(
            PhysicalWorkspaceCreationRequest.tenant_id == self.tenant_id,
            PhysicalWorkspaceCreationRequest.id == request_id,
        )
        if lock:
            statement = statement.with_for_update()
        request = self.db.scalar(statement)
        if request is None:
            raise HTTPException(status_code=404, detail="Physical Workspace Creation Request not found")
        return request

    def _record_failure(self, request_id: int, reason: str, *, mark_failed: bool) -> None:
        request = self.db.scalar(
            select(PhysicalWorkspaceCreationRequest).where(
                PhysicalWorkspaceCreationRequest.tenant_id == self.tenant_id,
                PhysicalWorkspaceCreationRequest.id == request_id,
            )
        )
        if request is None:
            return
        before = request.state
        if mark_failed:
            request.state = PhysicalWorkspaceCreationState.failed
            request.failure_reason = reason[:2000]
            self._touch(request)
        self._event(
            "physical_workspace_creation.materialization_failed",
            request,
            before,
            request.state,
            {"reason": reason[:500], "outcome": "failure"},
        )
        self.db.commit()

    def _out(self, request: PhysicalWorkspaceCreationRequest) -> PhysicalWorkspaceRequestOut:
        parent = self.db.get(EnterpriseWorkspace, request.parent_workspace_id)
        template = self.db.get(AdminConfiguration, request.template_config_id)
        requestor = self.db.get(UserAccount, request.requestor_user_id)
        responsible = self.db.get(UserAccount, request.responsible_user_id)
        return PhysicalWorkspaceRequestOut(
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
            responsible_name=responsible.full_name if responsible else "",
            revision_version=request.revision_version,
            decision_reason=request.decision_reason,
            failure_reason=request.failure_reason,
            approved_by_user_id=request.approved_by_user_id,
            approved_at=request.approved_at,
            materialized_workspace_id=request.materialized_workspace_id,
            materialized_business_number=request.materialized_business_number,
            materialized_record_code=request.materialized_record_code,
            created_at=request.created_at,
            updated_at=request.updated_at,
            submitted_at=request.submitted_at,
            reviewed_at=request.reviewed_at,
            materialized_at=request.materialized_at,
        )

    @staticmethod
    def _request_values(request: PhysicalWorkspaceCreationRequest) -> dict[str, Any]:
        return {
            "workspace_type_code": request.workspace_type_code,
            "parent_workspace_id": request.parent_workspace_id,
            "template_config_id": request.template_config_id,
            "workspace_name": request.workspace_name,
            "description": request.description,
            "responsible_user_id": request.responsible_user_id,
            "attributes": dict(request.attributes_json or {}),
            "classifications": list(request.classification_values_json or []),
        }

    @staticmethod
    def _apply_payload(request: PhysicalWorkspaceCreationRequest, payload: PhysicalWorkspaceRequestPayload) -> None:
        request.workspace_type_code = payload.workspace_type_code
        request.parent_workspace_id = payload.parent_workspace_id
        request.template_config_id = payload.template_config_id
        request.workspace_name = payload.workspace_name
        request.description = payload.description
        request.responsible_user_id = payload.responsible_user_id
        request.attributes_json = dict(payload.attributes)
        request.classification_values_json = [item.model_dump() for item in payload.classifications]

    def _ensure_owner(self, request: PhysicalWorkspaceCreationRequest) -> None:
        if request.requestor_user_id != self.actor_id:
            raise HTTPException(status_code=403, detail="Only the requestor may change this request")

    def _ensure_read_access(
        self, request: PhysicalWorkspaceCreationRequest, context: EnterprisePermissionContext
    ) -> None:
        if request.requestor_user_id != self.actor_id and not context.role_codes & PRIVILEGED_ROLES:
            raise HTTPException(status_code=404, detail="Physical Workspace Creation Request not found")

    @staticmethod
    def _require_version(request: PhysicalWorkspaceCreationRequest, expected: int) -> None:
        if request.revision_version != expected:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PHYSICAL_WORKSPACE_REQUEST_VERSION_CONFLICT",
                    "expected": expected,
                    "observed": request.revision_version,
                },
            )

    def _transition(
        self,
        request: PhysicalWorkspaceCreationRequest,
        state: PhysicalWorkspaceCreationState,
        event_type: str,
    ) -> None:
        before = request.state
        request.state = state
        self._touch(request)
        self._event(event_type, request, before, state)

    def _touch(self, request: PhysicalWorkspaceCreationRequest) -> None:
        request.revision_version += 1
        request.last_modified_by_user_id = self.actor_id
        request.updated_at = utc_now()

    def _commit_out(self, request: PhysicalWorkspaceCreationRequest) -> PhysicalWorkspaceRequestOut:
        self.db.commit()
        self.db.refresh(request)
        return self._out(request)

    def _event(
        self,
        event_type: str,
        request: PhysicalWorkspaceCreationRequest,
        state_before: str | None,
        state_after: str | None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload = dict(extra or {})
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome=str(payload.pop("outcome", "success")),
                target_type="physical_workspace_creation_request",
                target_id=request.id,
                metadata_json={
                    "gate": "06B",
                    "request_number": request.request_number,
                    "workspace_type_code": request.workspace_type_code,
                    "parent_workspace_id": request.parent_workspace_id,
                    "state_before": str(state_before) if state_before is not None else None,
                    "state_after": str(state_after) if state_after is not None else None,
                    **payload,
                },
            )
        )

    def _workspace_path(self, workspace: EnterpriseWorkspace) -> list[EnterpriseWorkspace]:
        path = [workspace]
        current = workspace
        visited = {workspace.id}
        while current.parent_id:
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

    @staticmethod
    def _workspace_view(workspace: EnterpriseWorkspace) -> dict[str, Any]:
        return {
            "id": workspace.id,
            "name": workspace.name,
            "workspace_type_code": workspace.workspace_type_code,
            "record_code": workspace.record_code,
        }

    @staticmethod
    def _configuration_view(configuration: AdminConfiguration) -> dict[str, Any]:
        return {
            "id": configuration.id,
            "code": configuration.code,
            "name": configuration.name,
            "status": configuration.status,
            "revision": configuration.revision,
            "content": dict(configuration.content_json),
        }

    @staticmethod
    def _normalize_type(value: str) -> str:
        return value.strip().lower().replace("_", "-").replace(" ", "-")

    def _normalize_optional_type(self, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = self._normalize_type(value)
        self._assert_creatable_type(normalized)
        return normalized

    def _assert_creatable_type(self, value: str) -> None:
        normalized = self._normalize_type(value)
        if normalized not in CREATABLE_TYPES:
            raise HTTPException(
                status_code=422,
                detail={"code": "WORKSPACE_TYPE_NOT_CREATABLE", "workspace_type_code": normalized},
            )

    @staticmethod
    def _attribute_code(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
        aliases = {
            "property_name": "name",
            "facility_name": "name",
            "warehouse_name": "name",
            "property_number": "code",
            "facility_number": "code",
            "warehouse_number": "code",
            "parent_workspace": "parent_id",
            "property_manager": "responsible_user_id",
            "warehouse_manager": "responsible_user_id",
            "responsible": "responsible_user_id",
        }
        return aliases.get(normalized, normalized)

    @staticmethod
    def _normalize_classifications(values: list[dict[str, Any]]) -> list[dict[str, str]]:
        return PhysicalWorkspaceCreationService._merge_classifications([], values)

    @staticmethod
    def _merge_classifications(*groups: list[dict[str, Any]]) -> list[dict[str, str]]:
        unique: dict[tuple[str, str], dict[str, str]] = {}
        for values in groups:
            for item in values:
                category = str(item.get("category_set_code", "")).strip().lower()
                code = str(item.get("category_item_code", "")).strip().lower()
                if category and code:
                    unique[(category, code)] = {
                        "category_set_code": category,
                        "category_item_code": code,
                    }
        return [unique[key] for key in sorted(unique)]

    @staticmethod
    def _raise_issues(issues: list[str]) -> None:
        if issues:
            raise HTTPException(
                status_code=422,
                detail={"code": "PHYSICAL_WORKSPACE_CREATION_VALIDATION_FAILED", "issues": sorted(set(issues))},
            )


def _content_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
