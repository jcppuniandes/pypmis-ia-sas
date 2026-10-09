"""Governed initialization and activation of materialized Project Workspaces."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import (
    AdminConfiguration,
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
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.project_creation.governance import (
    GOVERNANCE_LABELS,
    activation_authorization_status,
    source_requirements_status,
)
from app.modules.project_creation.models import ProjectCreationRequest
from app.modules.project_workspace_initialization.models import ProjectWorkspaceInitialization
from app.modules.project_workspace_initialization.schemas import (
    ChecklistItemOut,
    InitializationOut,
    InitializationState,
    ModuleInitializationOut,
    ProjectWorkspaceListItemOut,
)

INITIALIZATION_VERSION = 1
INITIALIZER_ROLES = {"organization_admin", "project_workspace_initializer"}
ACTIVATOR_ROLES = {"organization_admin", "project_workspace_activator"}
KNOWN_MODULES = {"scope-manager", "schedule-manager", "cost-manager"}


class ProjectWorkspaceInitializationService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def get(self, workspace_id: int, context: EnterprisePermissionContext) -> InitializationOut:
        workspace = self._workspace(workspace_id, context)
        initialization = self._initialization(workspace.id)
        if initialization is None:
            return self._synthetic(workspace, result="FOUND")
        return self._out(workspace, initialization, result="FOUND", mutation_count=0)

    def preview(self, workspace_id: int, context: EnterprisePermissionContext) -> InitializationOut:
        workspace = self._workspace(workspace_id, context)
        initialization = self._initialization(workspace.id)
        checklist, template, modules = self._evaluate(workspace)
        return self._build_out(
            workspace=workspace,
            initialization=initialization,
            result="PREVIEW",
            persisted=False,
            state=InitializationState(initialization.state)
            if initialization
            else self._state_without_record(workspace),
            checklist=checklist,
            template=template,
            modules=modules,
            revision_version=initialization.revision_version if initialization else workspace.version,
            mutation_count=0,
        )

    def start(
        self,
        workspace_id: int,
        context: EnterprisePermissionContext,
        expected_version: int,
        *,
        failure_injector: Callable[[ProjectWorkspaceInitialization], None] | None = None,
    ) -> InitializationOut:
        try:
            workspace = self._workspace(workspace_id, context, lock=True)
            initialization = self._initialization(workspace.id, lock=True)
            if workspace.status == "active":
                if initialization is None:
                    return self._synthetic(workspace, result="ALREADY_ACTIVE")
                if initialization.state == InitializationState.activated:
                    return self._out(workspace, initialization, result="ALREADY_INITIALIZED", mutation_count=0)
            if workspace.status != "pending":
                raise HTTPException(status_code=409, detail="PROJECT_WORKSPACE_MUST_BE_PENDING")
            current_version = initialization.revision_version if initialization else workspace.version
            self._require_version(current_version, expected_version)
            if initialization and initialization.state in {
                InitializationState.ready,
                InitializationState.activated,
            }:
                return self._out(workspace, initialization, result="ALREADY_INITIALIZED", mutation_count=0)

            metadata = self._metadata(workspace)
            template = self._template_from_metadata(metadata)
            if template is None:
                raise HTTPException(status_code=409, detail="PROJECT_TEMPLATE_SNAPSHOT_NOT_FOUND")
            mutation_count = 0
            before = initialization.state if initialization else InitializationState.not_started
            if initialization is None:
                initialization = ProjectWorkspaceInitialization(
                    tenant_id=self.tenant_id,
                    workspace_id=workspace.id,
                    state=InitializationState.initializing,
                    template_config_id=template.id,
                    template_code=template.code,
                    template_revision=template.revision,
                    initialization_version=INITIALIZATION_VERSION,
                    started_by_user_id=self.actor_id,
                    started_at=utc_now(),
                    last_modified_by_user_id=self.actor_id,
                    revision_version=1,
                )
                self.db.add(initialization)
                self.db.flush()
                mutation_count += 1
            else:
                initialization.state = InitializationState.initializing
                initialization.started_by_user_id = initialization.started_by_user_id or self.actor_id
                initialization.started_at = initialization.started_at or utc_now()
                self._touch(initialization)
                mutation_count += 1
            self._event(
                "project_workspace.initialization_started",
                workspace,
                initialization,
                before,
                InitializationState.initializing,
            )

            defaults = self._apply_defaults(workspace, template)
            if defaults:
                initialization.defaults_applied_json = defaults
                mutation_count += 1
            assignments = self._ensure_manager_access(workspace)
            if assignments:
                initialization.assignments_json = assignments
                mutation_count += len(assignments)

            checklist, checked_template, modules = self._evaluate(workspace)
            initialization.module_states_json = {item.module_key: item.model_dump() for item in modules}
            initialization.checklist_json = [item.model_dump() for item in checklist]
            initialization.validation_hash = self._validation_hash(workspace, checked_template, modules)
            initialization.checklist_hash = _hash([item.model_dump() for item in checklist])
            initialization.validated_by_user_id = self.actor_id
            initialization.validated_at = utc_now()
            initialization.failure_code = None
            initialization.failure_reason = None
            blocking = [item for item in checklist if item.blocking and item.status == "FAIL"]
            initialization.state = InitializationState.blocked if blocking else InitializationState.ready
            initialization.ready_at = None if blocking else utc_now()
            initialization.last_modified_by_user_id = self.actor_id
            initialization.updated_at = utc_now()
            self._event(
                "project_workspace.initialization_validated",
                workspace,
                initialization,
                InitializationState.initializing,
                initialization.state,
                extra={"blocker_count": len(blocking)},
            )
            self._event(
                "project_workspace.initialization_blocked" if blocking else "project_workspace.ready_for_activation",
                workspace,
                initialization,
                InitializationState.initializing,
                initialization.state,
                outcome="blocked" if blocking else "success",
            )
            if failure_injector is not None:
                failure_injector(initialization)
            self.db.commit()
            self.db.refresh(initialization)
            return self._out(
                workspace, initialization, result="BLOCKED" if blocking else "READY", mutation_count=mutation_count
            )
        except HTTPException:
            self.db.rollback()
            raise
        except (IntegrityError, Exception) as exc:
            self.db.rollback()
            self._record_initialization_failure(workspace_id, type(exc).__name__, str(exc))
            if isinstance(exc, IntegrityError):
                raise HTTPException(
                    status_code=409, detail="PROJECT_WORKSPACE_INITIALIZATION_INTEGRITY_FAILURE"
                ) from exc
            raise

    def validate(
        self,
        workspace_id: int,
        context: EnterprisePermissionContext,
        expected_version: int,
    ) -> InitializationOut:
        workspace = self._workspace(workspace_id, context, lock=True)
        initialization = self._initialization(workspace.id, lock=True)
        if initialization is None:
            raise HTTPException(status_code=409, detail="INITIALIZATION_NOT_STARTED")
        self._require_version(initialization.revision_version, expected_version)
        if initialization.state == InitializationState.activated:
            return self._out(workspace, initialization, result="ALREADY_INITIALIZED", mutation_count=0)
        checklist, template, modules = self._evaluate(workspace)
        before = initialization.state
        blocking = [item for item in checklist if item.blocking and item.status == "FAIL"]
        initialization.state = InitializationState.blocked if blocking else InitializationState.ready
        initialization.checklist_json = [item.model_dump() for item in checklist]
        initialization.module_states_json = {item.module_key: item.model_dump() for item in modules}
        initialization.validation_hash = self._validation_hash(workspace, template, modules)
        initialization.checklist_hash = _hash(initialization.checklist_json)
        initialization.validated_by_user_id = self.actor_id
        initialization.validated_at = utc_now()
        initialization.ready_at = None if blocking else utc_now()
        self._touch(initialization)
        self._event(
            "project_workspace.initialization_validated",
            workspace,
            initialization,
            before,
            initialization.state,
            extra={"blocker_count": len(blocking)},
        )
        self._event(
            "project_workspace.initialization_blocked" if blocking else "project_workspace.ready_for_activation",
            workspace,
            initialization,
            before,
            initialization.state,
            outcome="blocked" if blocking else "success",
        )
        self.db.commit()
        self.db.refresh(initialization)
        return self._out(workspace, initialization, result="BLOCKED" if blocking else "READY", mutation_count=1)

    def activate(
        self,
        workspace_id: int,
        context: EnterprisePermissionContext,
        expected_version: int,
        *,
        failure_injector: Callable[[EnterpriseWorkspace], None] | None = None,
    ) -> InitializationOut:
        try:
            workspace = self._workspace(workspace_id, context, lock=True)
            initialization = self._initialization(workspace.id, lock=True)
            if workspace.status == "active":
                if initialization is None:
                    return self._synthetic(workspace, result="ALREADY_ACTIVE")
                if initialization.state == InitializationState.activated:
                    return self._out(workspace, initialization, result="ALREADY_ACTIVE", mutation_count=0)
            if initialization is None:
                raise HTTPException(status_code=409, detail="INITIALIZATION_NOT_STARTED")
            self._require_version(initialization.revision_version, expected_version)
            if workspace.status != "pending" or initialization.state != InitializationState.ready:
                raise HTTPException(status_code=409, detail="PROJECT_WORKSPACE_NOT_READY_FOR_ACTIVATION")
            request = self._creation_request(workspace)
            if (
                initialization.started_by_user_id == self.actor_id
                or initialization.last_modified_by_user_id == self.actor_id
                or (request is not None and request.requestor_user_id == self.actor_id)
            ):
                raise HTTPException(status_code=403, detail="ACTIVATION_SEPARATION_OF_DUTIES_VIOLATION")

            checklist, template, modules = self._evaluate(workspace)
            validation_hash = self._validation_hash(workspace, template, modules)
            checklist_hash = _hash([item.model_dump() for item in checklist])
            blockers = [item for item in checklist if item.blocking and item.status == "FAIL"]
            if (
                blockers
                or validation_hash != initialization.validation_hash
                or checklist_hash != initialization.checklist_hash
            ):
                initialization.state = InitializationState.blocked
                initialization.checklist_json = [item.model_dump() for item in checklist]
                initialization.validation_hash = validation_hash
                initialization.checklist_hash = checklist_hash
                initialization.ready_at = None
                self._touch(initialization)
                self._event(
                    "project_workspace.activation_failed",
                    workspace,
                    initialization,
                    InitializationState.ready,
                    InitializationState.blocked,
                    outcome="failure",
                    extra={"reason": "VALIDATION_CHANGED", "blocker_count": len(blockers)},
                )
                self.db.commit()
                raise HTTPException(status_code=409, detail="PROJECT_WORKSPACE_VALIDATION_CHANGED")

            workspace.status = "active"
            workspace.version += 1
            workspace.updated_at = utc_now()
            if failure_injector is not None:
                failure_injector(workspace)
            initialization.state = InitializationState.activated
            initialization.activated_by_user_id = self.actor_id
            initialization.activated_at = utc_now()
            initialization.failure_code = None
            initialization.failure_reason = None
            self._touch(initialization)
            self._event(
                "project_workspace.activated",
                workspace,
                initialization,
                InitializationState.ready,
                InitializationState.activated,
            )
            self.db.commit()
            self.db.refresh(initialization)
            return self._out(workspace, initialization, result="ACTIVATED", mutation_count=2)
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            self._record_activation_failure(workspace_id, str(exc))
            raise

    def list_workspaces(
        self,
        context: EnterprisePermissionContext,
        *,
        status: str = "",
    ) -> list[ProjectWorkspaceListItemOut]:
        statement = select(EnterpriseWorkspace).where(
            EnterpriseWorkspace.tenant_id == self.tenant_id,
            EnterpriseWorkspace.workspace_type_code == "project",
        )
        if status.strip():
            statement = statement.where(EnterpriseWorkspace.status == status.strip().lower())
        if not context.organization_wide:
            statement = statement.where(EnterpriseWorkspace.id.in_(context.workspace_ids or {-1}))
        rows = list(self.db.scalars(statement.order_by(EnterpriseWorkspace.record_code)).all())
        result = []
        for workspace in rows:
            initialization = self._initialization(workspace.id)
            metadata = self._metadata(workspace)
            manager_id = metadata.get("project_manager_user_id")
            manager = self.db.get(UserAccount, manager_id) if manager_id else None
            checklist = initialization.checklist_json if initialization else []
            role_codes = set(context.role_codes)
            result.append(
                ProjectWorkspaceListItemOut(
                    workspace_id=workspace.id,
                    project_name=workspace.name,
                    project_number=str(metadata.get("project_number", workspace.code)),
                    record_code=workspace.record_code,
                    workspace_status=workspace.status,
                    initialization_state=initialization.state
                    if initialization
                    else self._state_without_record(workspace),
                    template_code=str(metadata.get("template_code", "")),
                    project_manager=manager.full_name if manager else "",
                    blocker_count=sum(1 for item in checklist if item.get("blocking") and item.get("status") == "FAIL"),
                    warning_count=sum(1 for item in checklist if item.get("status") == "WARNING"),
                    revision_version=initialization.revision_version if initialization else workspace.version,
                    can_initialize=bool(role_codes & INITIALIZER_ROLES) and workspace.status == "pending",
                    can_activate=bool(role_codes & ACTIVATOR_ROLES)
                    and initialization is not None
                    and initialization.state == InitializationState.ready,
                )
            )
        return result

    def _evaluate(
        self,
        workspace: EnterpriseWorkspace,
    ) -> tuple[list[ChecklistItemOut], AdminConfiguration | None, list[ModuleInitializationOut]]:
        metadata = self._metadata(workspace)
        parent = self.db.get(EnterpriseWorkspace, workspace.parent_id) if workspace.parent_id else None
        template = self._template_from_metadata(metadata)
        governance_model = metadata.get("governance_model")
        governance_policy = dict(metadata.get("governance_policy_snapshot") or {})
        source_snapshot = dict(metadata.get("source_snapshot") or {})
        source_blockers, _source_warnings = source_requirements_status(
            governance_model,
            metadata.get("source_context_type"),
            source_snapshot,
            governance_policy,
            strategic_gate_decision_id=metadata.get("strategic_gate_decision_id"),
        )
        strategic_objective_required = bool(governance_policy.get("strategic_objective_required", True))
        allowed_parent_types = set(governance_policy.get("allowed_parent_types") or {"portfolio", "program"})
        manager_id = metadata.get("project_manager_user_id")
        manager = self.db.get(UserAccount, manager_id) if manager_id else None
        objective_codes = list(
            self.db.scalars(
                select(EnterpriseWorkspaceClassification.category_item_code).where(
                    EnterpriseWorkspaceClassification.tenant_id == self.tenant_id,
                    EnterpriseWorkspaceClassification.workspace_id == workspace.id,
                    EnterpriseWorkspaceClassification.category_set_code == "strategic-objective",
                )
            ).all()
        )
        active_objective_codes = set(
            self.db.scalars(
                select(EnterpriseStrategicObjective.code).where(
                    EnterpriseStrategicObjective.tenant_id == self.tenant_id,
                    EnterpriseStrategicObjective.code.in_(objective_codes or [""]),
                    EnterpriseStrategicObjective.active.is_(True),
                )
            ).all()
        )
        settings = list(
            self.db.scalars(
                select(WorkspaceModuleSetting).where(
                    WorkspaceModuleSetting.tenant_id == self.tenant_id,
                    WorkspaceModuleSetting.workspace_id == workspace.id,
                )
            ).all()
        )
        enabled_settings = {item.module_key for item in settings if item.enabled}
        template_modules = set(template.content_json.get("enabled_modules", [])) if template else set()
        definitions = {
            item.code: item
            for item in self.db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == "module_definition",
                    AdminConfiguration.code.in_(enabled_settings or {""}),
                    AdminConfiguration.status == "published",
                )
            ).all()
        }
        manager_assignment = None
        if manager is not None:
            manager_assignment = self.db.scalar(
                select(SecurityAccessAssignment)
                .join(SecurityRole, SecurityRole.id == SecurityAccessAssignment.role_id)
                .where(
                    SecurityAccessAssignment.tenant_id == self.tenant_id,
                    SecurityAccessAssignment.workspace_id == workspace.id,
                    SecurityAccessAssignment.user_id == manager.id,
                    SecurityAccessAssignment.status == "active",
                    SecurityRole.code == "project_manager",
                    SecurityRole.status == "active",
                )
            )
        identity_unique = all(
            self.db.scalar(
                select(func.count(EnterpriseWorkspace.id)).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    getattr(EnterpriseWorkspace, field) == value,
                )
            )
            == 1
            for field, value in (
                ("code", workspace.code),
                ("record_code", workspace.record_code),
                ("external_key", workspace.external_key),
            )
            if value
        )
        record_valid = bool(
            parent
            and workspace.record_code.startswith(f"{parent.record_code}.")
            and workspace.record_code.rsplit(".", 1)[-1].isdigit()
        )
        project_number_valid = bool(
            metadata.get("project_number") and metadata.get("project_number") == workspace.code and identity_unique
        )
        template_snapshot_valid = bool(
            template
            and metadata.get("template_revision") == template.revision
            and metadata.get("template_content_hash") == template.content_hash
        )
        required_attributes = {
            "project_name": workspace.name,
            "project_number": metadata.get("project_number"),
            "parent": workspace.parent_id,
            "project_manager": metadata.get("project_manager_user_id"),
            "currency": metadata.get("currency_code"),
            "status": workspace.status,
        }
        if strategic_objective_required:
            required_attributes["strategic_objective"] = objective_codes
        required_classifications = list(template.content_json.get("default_classifications", [])) if template else []
        classifications = {
            (item.category_set_code, item.category_item_code)
            for item in self.db.scalars(
                select(EnterpriseWorkspaceClassification).where(
                    EnterpriseWorkspaceClassification.tenant_id == self.tenant_id,
                    EnterpriseWorkspaceClassification.workspace_id == workspace.id,
                )
            ).all()
        }
        classifications_valid = all(
            (str(item.get("category_set_code", "")), str(item.get("category_item_code", ""))) in classifications
            for item in required_classifications
        )
        modules_valid = enabled_settings == template_modules and all(
            key in definitions and key in KNOWN_MODULES for key in enabled_settings
        )
        module_states = [
            ModuleInitializationOut(
                module_key=key,
                state="INITIALIZED"
                if key in definitions and key in template_modules and key in KNOWN_MODULES
                else "BLOCKED",
                evidence={
                    "definition_revision": definitions[key].revision if key in definitions else None,
                    "template_allowed": key in template_modules,
                    "currency": metadata.get("currency_code") if key == "cost-manager" else None,
                    "deep_configuration_created": False,
                },
            )
            for key in sorted(enabled_settings)
        ]
        active_or_pending = workspace.status in {"pending", "active"}
        checks = [
            self._check(
                "workspace_identity_valid",
                identity_unique and bool(workspace.external_key),
                "Identidad única y estable del workspace.",
                True,
                {"code": workspace.code, "external_key": workspace.external_key},
            ),
            self._check(
                "workspace_type_project",
                workspace.workspace_type_code == "project",
                "El workspace es de tipo Project.",
                True,
                {"workspace_type": workspace.workspace_type_code},
            ),
            self._check(
                "workspace_status_pending",
                active_or_pending and workspace.status == "pending" or workspace.status == "active",
                "El workspace permanece PENDING hasta la activación.",
                True,
                {"status": workspace.status},
            ),
            self._check(
                "parent_valid",
                bool(
                    parent
                    and parent.tenant_id == self.tenant_id
                    and parent.status == "active"
                    and parent.workspace_type_code in allowed_parent_types
                ),
                "El padre pertenece al tenant y admite proyectos.",
                True,
                {"parent_id": workspace.parent_id, "parent_type": parent.workspace_type_code if parent else None},
            ),
            self._check(
                "record_code_valid",
                record_valid and identity_unique,
                "Record Code jerárquico, único e inmutable.",
                True,
                {"record_code": workspace.record_code, "parent_record_code": parent.record_code if parent else None},
            ),
            self._check(
                "project_number_valid",
                project_number_valid,
                "Project Number único y consistente con la identidad.",
                True,
                {"project_number": metadata.get("project_number"), "workspace_code": workspace.code},
            ),
            self._check(
                "template_assigned",
                template is not None,
                "Existe la revisión exacta de plantilla asignada.",
                True,
                {"template_config_id": metadata.get("template_id"), "template_code": metadata.get("template_code")},
            ),
            self._check(
                "template_snapshot_valid",
                template_snapshot_valid,
                "La huella y revisión de la plantilla coinciden con la materialización.",
                True,
                {
                    "expected_revision": metadata.get("template_revision"),
                    "actual_revision": template.revision if template else None,
                },
            ),
            self._check(
                "project_manager_assigned",
                bool(manager and manager.tenant_id == self.tenant_id and manager.status == "active"),
                "Project Manager activo y del mismo tenant.",
                True,
                {"manager_user_id": metadata.get("project_manager_user_id")},
            ),
            self._check(
                "strategic_objective_present",
                (not strategic_objective_required)
                or (bool(objective_codes) and set(objective_codes) == active_objective_codes),
                "La alineación estratégica cumple la política efectiva.",
                strategic_objective_required,
                {
                    "objective_codes": objective_codes,
                    "required": strategic_objective_required,
                },
            ),
            self._check(
                "governance_source_valid",
                not source_blockers,
                "La fuente de creación y su snapshot cumplen la política del modelo de gobierno.",
                bool(governance_model),
                {
                    "governance_model": governance_model,
                    "governance_label": GOVERNANCE_LABELS.get(str(governance_model), "Legacy / Not Classified"),
                    "source_context_type": metadata.get("source_context_type"),
                    "blockers": source_blockers,
                },
            ),
            self._check(
                "governance_activation_authorized",
                activation_authorization_status(governance_model, source_snapshot),
                "La autorización de activación corresponde al modelo de gobierno efectivo.",
                bool(governance_model),
                {
                    "governance_model": governance_model,
                    "activation_requirements": governance_policy.get("activation_requirements", []),
                },
            ),
            self._check(
                "required_classifications_valid",
                classifications_valid,
                "Las clasificaciones obligatorias de la plantilla están presentes.",
                True,
                {"required": required_classifications},
            ),
            self._check(
                "required_attributes_complete",
                all(value not in (None, "", []) for value in required_attributes.values()),
                "Los atributos obligatorios del proyecto están completos.",
                True,
                required_attributes,
            ),
            self._check(
                "module_settings_valid",
                modules_valid and all(item.state == "INITIALIZED" for item in module_states),
                "Los módulos habilitados están publicados, permitidos y listos.",
                True,
                {"enabled": sorted(enabled_settings), "template_modules": sorted(template_modules)},
            ),
            self._check(
                "security_assignments_valid",
                manager_assignment is not None,
                "El Project Manager tiene acceso mínimo y acotado al workspace.",
                True,
                {"assignment_id": manager_assignment.id if manager_assignment else None},
            ),
            self._check(
                "tenant_scope_valid",
                all(
                    item.tenant_id == self.tenant_id
                    for item in (workspace, parent, manager, template)
                    if item is not None
                ),
                "Todas las referencias pertenecen al tenant activo.",
                True,
                {"tenant_id": self.tenant_id},
            ),
            self._check(
                "no_core_revision_required",
                True,
                "La inicialización no requiere ni crea una revisión CORE.",
                False,
                {"core_mutation": False},
            ),
        ]
        optional_missing = [
            key
            for key in (
                "planned_start",
                "planned_finish",
                "estimated_budget",
                "project_phase",
                "priority",
                "country",
                "region",
            )
            if not metadata.get(key)
        ]
        checks.append(
            ChecklistItemOut(
                code="optional_attributes_complete",
                status="PASS" if not optional_missing else "WARNING",
                message="Atributos opcionales completos."
                if not optional_missing
                else "Hay atributos opcionales sin definir.",
                blocking=False,
                evidence={"missing": optional_missing},
            )
        )
        return checks, template, module_states

    @staticmethod
    def _check(code: str, passed: bool, message: str, blocking: bool, evidence: dict[str, Any]) -> ChecklistItemOut:
        return ChecklistItemOut(
            code=code,
            status="PASS" if passed else "FAIL",
            message=message,
            blocking=blocking,
            evidence=evidence,
        )

    def _apply_defaults(self, workspace: EnterpriseWorkspace, template: AdminConfiguration) -> dict[str, Any]:
        metadata = dict(self._metadata(workspace))
        explicit = set(metadata.get("explicit_fields", []))
        template_defaults = dict(template.content_json.get("default_attributes", {}))
        tenant_type = self.db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == "workspace_type",
                AdminConfiguration.code == "project",
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
            .limit(1)
        )
        tenant_defaults = dict((tenant_type.content_json if tenant_type else {}).get("default_attributes", {}))
        aliases = {"currency": "currency_code", "currency_code": "currency_code"}
        applied: dict[str, Any] = {}
        for source, source_name in ((template_defaults, "template"), (tenant_defaults, "tenant")):
            for raw_key, value in source.items():
                key = aliases.get(raw_key, raw_key)
                if key in explicit or metadata.get(key) not in (None, "", []):
                    continue
                metadata[key] = value
                applied[key] = {"value": value, "source": source_name}
        if applied:
            defaults = dict(workspace.defaults_json or {})
            defaults["_project"] = metadata
            workspace.defaults_json = defaults
            workspace.version += 1
            workspace.updated_at = utc_now()
            self.db.flush()
        return applied

    def _ensure_manager_access(self, workspace: EnterpriseWorkspace) -> list[dict[str, Any]]:
        manager_id = self._metadata(workspace).get("project_manager_user_id")
        if not manager_id:
            return []
        role = self.db.scalar(
            select(SecurityRole).where(
                SecurityRole.tenant_id == self.tenant_id,
                SecurityRole.code == "project_manager",
                SecurityRole.status == "active",
            )
        )
        if role is None:
            return []
        existing = self.db.scalar(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.tenant_id == self.tenant_id,
                SecurityAccessAssignment.workspace_id == workspace.id,
                SecurityAccessAssignment.user_id == manager_id,
                SecurityAccessAssignment.role_id == role.id,
                SecurityAccessAssignment.status == "active",
            )
        )
        if existing is not None:
            return []
        assignment = SecurityAccessAssignment(
            tenant_id=self.tenant_id,
            subject_type="user",
            user_id=manager_id,
            role_id=role.id,
            scope_type="workspace",
            workspace_id=workspace.id,
            status="active",
            granted_by_user_id=self.actor_id,
        )
        self.db.add(assignment)
        self.db.flush()
        return [{"assignment_id": assignment.id, "role_code": "project_manager", "user_id": manager_id}]

    def _validation_hash(
        self,
        workspace: EnterpriseWorkspace,
        template: AdminConfiguration | None,
        modules: list[ModuleInitializationOut],
    ) -> str:
        metadata = self._metadata(workspace)
        manager_assignments = list(
            self.db.scalars(
                select(SecurityAccessAssignment.id).where(
                    SecurityAccessAssignment.tenant_id == self.tenant_id,
                    SecurityAccessAssignment.workspace_id == workspace.id,
                    SecurityAccessAssignment.status == "active",
                )
            ).all()
        )
        classifications = list(
            self.db.execute(
                select(
                    EnterpriseWorkspaceClassification.category_set_code,
                    EnterpriseWorkspaceClassification.category_item_code,
                ).where(
                    EnterpriseWorkspaceClassification.tenant_id == self.tenant_id,
                    EnterpriseWorkspaceClassification.workspace_id == workspace.id,
                )
            ).all()
        )
        return _hash(
            {
                "tenant_id": self.tenant_id,
                "workspace": {
                    "id": workspace.id,
                    "parent_id": workspace.parent_id,
                    "type": workspace.workspace_type_code,
                    "code": workspace.code,
                    "external_key": workspace.external_key,
                    "record_code": workspace.record_code,
                    "name": workspace.name,
                    "status": workspace.status,
                },
                "project": metadata,
                "template": {
                    "id": template.id if template else None,
                    "code": template.code if template else None,
                    "revision": template.revision if template else None,
                    "hash": template.content_hash if template else None,
                },
                "modules": [item.model_dump() for item in modules],
                "assignments": sorted(manager_assignments),
                "classifications": sorted([list(item) for item in classifications]),
            }
        )

    def _workspace(
        self,
        workspace_id: int,
        context: EnterprisePermissionContext,
        *,
        lock: bool = False,
    ) -> EnterpriseWorkspace:
        statement = select(EnterpriseWorkspace).where(
            EnterpriseWorkspace.tenant_id == self.tenant_id,
            EnterpriseWorkspace.id == workspace_id,
            EnterpriseWorkspace.workspace_type_code == "project",
        )
        if lock:
            statement = statement.with_for_update()
        workspace = self.db.scalar(statement)
        if workspace is None or (not context.organization_wide and workspace.id not in context.workspace_ids):
            raise HTTPException(status_code=404, detail="Project Workspace not found")
        return workspace

    def _initialization(self, workspace_id: int, *, lock: bool = False) -> ProjectWorkspaceInitialization | None:
        statement = select(ProjectWorkspaceInitialization).where(
            ProjectWorkspaceInitialization.tenant_id == self.tenant_id,
            ProjectWorkspaceInitialization.workspace_id == workspace_id,
        )
        if lock:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def _template_from_metadata(self, metadata: dict[str, Any]) -> AdminConfiguration | None:
        template_id = metadata.get("template_id")
        if not template_id:
            return None
        return self.db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.id == template_id,
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == "project_template",
            )
        )

    def _creation_request(self, workspace: EnterpriseWorkspace) -> ProjectCreationRequest | None:
        request_id = self._metadata(workspace).get("creation_request_id")
        if not request_id:
            return None
        return self.db.scalar(
            select(ProjectCreationRequest).where(
                ProjectCreationRequest.id == request_id,
                ProjectCreationRequest.tenant_id == self.tenant_id,
                ProjectCreationRequest.materialized_workspace_id == workspace.id,
            )
        )

    @staticmethod
    def _metadata(workspace: EnterpriseWorkspace) -> dict[str, Any]:
        return dict((workspace.defaults_json or {}).get("_project", {}))

    @staticmethod
    def _state_without_record(workspace: EnterpriseWorkspace) -> InitializationState:
        return InitializationState.activated if workspace.status == "active" else InitializationState.not_started

    @staticmethod
    def _require_version(current: int, expected: int) -> None:
        if current != expected:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PROJECT_WORKSPACE_VERSION_CONFLICT",
                    "message": "Project Workspace initialization changed; refresh and retry.",
                    "current_version": current,
                },
            )

    @staticmethod
    def _touch(initialization: ProjectWorkspaceInitialization) -> None:
        initialization.revision_version += 1
        initialization.updated_at = utc_now()

    def _synthetic(self, workspace: EnterpriseWorkspace, *, result: str) -> InitializationOut:
        checklist, template, modules = self._evaluate(workspace)
        if workspace.status == "active":
            checklist = []
            modules = [
                ModuleInitializationOut(
                    module_key=item.module_key,
                    state="INITIALIZED",
                    evidence={"legacy_active_workspace": True, "deep_configuration_created": False},
                )
                for item in self.db.scalars(
                    select(WorkspaceModuleSetting).where(
                        WorkspaceModuleSetting.tenant_id == self.tenant_id,
                        WorkspaceModuleSetting.workspace_id == workspace.id,
                        WorkspaceModuleSetting.enabled.is_(True),
                    )
                ).all()
            ]
        return self._build_out(
            workspace=workspace,
            initialization=None,
            result=result,
            persisted=False,
            state=self._state_without_record(workspace),
            checklist=checklist,
            template=template,
            modules=modules,
            revision_version=workspace.version,
            mutation_count=0,
        )

    def _out(
        self,
        workspace: EnterpriseWorkspace,
        initialization: ProjectWorkspaceInitialization,
        *,
        result: str,
        mutation_count: int,
    ) -> InitializationOut:
        checklist = [ChecklistItemOut.model_validate(item) for item in initialization.checklist_json]
        modules = [
            ModuleInitializationOut.model_validate(item)
            for _key, item in sorted(initialization.module_states_json.items())
        ]
        template = self.db.get(AdminConfiguration, initialization.template_config_id)
        return self._build_out(
            workspace=workspace,
            initialization=initialization,
            result=result,
            persisted=True,
            state=InitializationState(initialization.state),
            checklist=checklist,
            template=template,
            modules=modules,
            revision_version=initialization.revision_version,
            mutation_count=mutation_count,
        )

    def _build_out(
        self,
        *,
        workspace: EnterpriseWorkspace,
        initialization: ProjectWorkspaceInitialization | None,
        result: str,
        persisted: bool,
        state: InitializationState,
        checklist: list[ChecklistItemOut],
        template: AdminConfiguration | None,
        modules: list[ModuleInitializationOut],
        revision_version: int,
        mutation_count: int,
    ) -> InitializationOut:
        blockers = sum(1 for item in checklist if item.blocking and item.status == "FAIL")
        warnings = sum(1 for item in checklist if item.status == "WARNING")
        completed = sum(1 for item in checklist if item.status in {"PASS", "WARNING"})
        return InitializationOut(
            result=result,
            persisted=persisted,
            initialization_id=initialization.id if initialization else None,
            workspace_id=workspace.id,
            workspace_status=workspace.status,
            state=state,
            progress_percent=round(completed / len(checklist) * 100)
            if checklist
            else (100 if state == InitializationState.activated else 0),
            blocker_count=blockers,
            warning_count=warnings,
            checklist=checklist,
            template_config_id=template.id if template else None,
            template_code=template.code if template else "",
            template_revision=template.revision if template else None,
            modules=modules,
            defaults_applied=initialization.defaults_applied_json if initialization else {},
            assignments=initialization.assignments_json if initialization else [],
            validation_hash=initialization.validation_hash if initialization else None,
            checklist_hash=initialization.checklist_hash
            if initialization
            else _hash([item.model_dump() for item in checklist]),
            revision_version=revision_version,
            started_at=initialization.started_at if initialization else None,
            ready_at=initialization.ready_at if initialization else None,
            activated_at=initialization.activated_at if initialization else None,
            activated_by_user_id=initialization.activated_by_user_id if initialization else None,
            failure_code=initialization.failure_code if initialization else None,
            failure_reason=initialization.failure_reason if initialization else None,
            mutation_count=mutation_count,
        )

    def _event(
        self,
        event_type: str,
        workspace: EnterpriseWorkspace,
        initialization: ProjectWorkspaceInitialization,
        state_before: str,
        state_after: str,
        *,
        outcome: str = "success",
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome=outcome,
                target_type="project_workspace",
                target_id=workspace.id,
                metadata_json={
                    "tenant_id": self.tenant_id,
                    "workspace_id": workspace.id,
                    "initialization_id": initialization.id,
                    "actor_id": self.actor_id,
                    "actor": self.actor_id,
                    "state_before": str(state_before),
                    "state_after": str(state_after),
                    "project_number": self._metadata(workspace).get("project_number", workspace.code),
                    "record_code": workspace.record_code,
                    "template_code": initialization.template_code,
                    "template_revision": initialization.template_revision,
                    "template": {
                        "code": initialization.template_code,
                        "revision": initialization.template_revision,
                    },
                    "checklist_hash": initialization.checklist_hash,
                    "validation_hash": initialization.validation_hash,
                    "enabled_modules": sorted(initialization.module_states_json),
                    "blocking_issues": [
                        str(item.get("code", ""))
                        for item in initialization.checklist_json
                        if item.get("blocking") and item.get("status") == "FAIL"
                    ],
                    "timestamp": utc_now().isoformat(),
                    "result": outcome,
                    **(extra or {}),
                },
            )
        )

    def _record_initialization_failure(self, workspace_id: int, code: str, reason: str) -> None:
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.id == workspace_id,
                EnterpriseWorkspace.workspace_type_code == "project",
            )
        )
        if workspace is None or workspace.status != "pending":
            return
        initialization = self._initialization(workspace.id)
        template = self._template_from_metadata(self._metadata(workspace))
        if initialization is None and template is not None:
            initialization = ProjectWorkspaceInitialization(
                tenant_id=self.tenant_id,
                workspace_id=workspace.id,
                state=InitializationState.failed,
                template_config_id=template.id,
                template_code=template.code,
                template_revision=template.revision,
                initialization_version=INITIALIZATION_VERSION,
                started_by_user_id=self.actor_id,
                started_at=utc_now(),
                last_modified_by_user_id=self.actor_id,
                revision_version=1,
            )
            self.db.add(initialization)
            self.db.flush()
        if initialization is None:
            return
        before = initialization.state
        initialization.state = InitializationState.failed
        initialization.failure_code = code[:120]
        initialization.failure_reason = reason[:2000]
        initialization.last_modified_by_user_id = self.actor_id
        initialization.updated_at = utc_now()
        self._event(
            "project_workspace.initialization_failed",
            workspace,
            initialization,
            before,
            InitializationState.failed,
            outcome="failure",
            extra={"failure_code": code[:120], "reason": reason[:500]},
        )
        self.db.commit()

    def _record_activation_failure(self, workspace_id: int, reason: str) -> None:
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.id == workspace_id,
            )
        )
        initialization = self._initialization(workspace_id)
        if workspace is None or initialization is None:
            return
        self._event(
            "project_workspace.activation_failed",
            workspace,
            initialization,
            initialization.state,
            initialization.state,
            outcome="failure",
            extra={"reason": reason[:500]},
        )
        self.db.commit()


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
