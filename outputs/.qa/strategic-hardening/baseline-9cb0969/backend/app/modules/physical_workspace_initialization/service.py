"""Generic initialization and activation for materialized physical Workspaces."""

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
from app.modules.enterprise_structure.models import EnterpriseCoreRelease, EnterpriseWorkspaceClassification
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.physical_workspace_creation.models import PhysicalWorkspaceCreationRequest
from app.modules.physical_workspace_initialization.models import PhysicalWorkspaceInitialization
from app.modules.physical_workspace_initialization.schemas import (
    PhysicalChecklistItemOut,
    PhysicalInitializationOut,
    PhysicalInitializationState,
    PhysicalModuleReadinessOut,
    PhysicalWorkspaceListItemOut,
)

SUPPORTED_TYPES = {"property", "facility", "warehouse"}
INITIALIZATION_VERSION = 1
INITIALIZER_ROLES = {"organization_admin", "physical_workspace_initializer"}
ACTIVATOR_ROLES = {"organization_admin", "physical_workspace_activator"}
RESPONSIBLE_ROLE = "physical_workspace_responsible"

TYPE_CHECKS = {
    "property": (
        "property_type_valid",
        "property_manager_valid",
        "ownership_tenure_consistent",
        "legal_status_consistent",
        "geographic_information_valid",
        "property_area_values_valid",
        "property_value_fields_valid",
    ),
    "facility": (
        "facility_type_valid",
        "facility_responsible_valid",
        "operational_status_valid",
        "geographic_information_valid",
        "capacity_consistent",
        "area_values_consistent",
        "criticality_valid",
        "commissioning_data_consistent",
    ),
    "warehouse": (
        "warehouse_type_valid",
        "warehouse_manager_valid",
        "geographic_information_valid",
        "storage_capacity_consistent",
        "capacity_unit_valid",
        "criticality_valid",
        "parent_context_valid",
    ),
}


class PhysicalWorkspaceInitializationService:
    """A single backend source of truth parameterized by workspace_type_code."""

    def __init__(self, db: Session, tenant_id: int, actor_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def get(self, workspace_id: int, context: EnterprisePermissionContext) -> PhysicalInitializationOut:
        workspace = self._workspace(workspace_id, context)
        initialization = self._initialization(workspace.id)
        if initialization is None:
            return self._synthetic(workspace, result="FOUND")
        return self._out(workspace, initialization, result="FOUND", mutation_count=0)

    def preview(self, workspace_id: int, context: EnterprisePermissionContext) -> PhysicalInitializationOut:
        workspace = self._workspace(workspace_id, context)
        initialization = self._initialization(workspace.id)
        common, specific, template, modules = self._evaluate(workspace)
        return self._build_out(
            workspace,
            initialization,
            result="PREVIEW",
            persisted=False,
            state=PhysicalInitializationState(initialization.state)
            if initialization
            else self._state_without_record(workspace),
            common=common,
            specific=specific,
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
        failure_injector: Callable[[PhysicalWorkspaceInitialization], None] | None = None,
    ) -> PhysicalInitializationOut:
        try:
            workspace = self._workspace(workspace_id, context, lock=True)
            initialization = self._initialization(workspace.id, lock=True)
            if workspace.status == "active":
                if initialization and initialization.state == PhysicalInitializationState.activated:
                    return self._out(workspace, initialization, result="ALREADY_INITIALIZED", mutation_count=0)
                return self._synthetic(workspace, result="ALREADY_ACTIVE")
            if workspace.status != "pending":
                raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_MUST_BE_PENDING")
            current_version = initialization.revision_version if initialization else workspace.version
            self._require_version(current_version, expected_version)
            if initialization and initialization.state in {
                PhysicalInitializationState.ready,
                PhysicalInitializationState.activated,
            }:
                return self._out(workspace, initialization, result="ALREADY_INITIALIZED", mutation_count=0)

            metadata = self._metadata(workspace)
            template = self._template_from_metadata(metadata)
            if template is None:
                raise HTTPException(status_code=409, detail="PHYSICAL_TEMPLATE_SNAPSHOT_NOT_FOUND")
            before = initialization.state if initialization else PhysicalInitializationState.not_started
            mutation_count = 0
            if initialization is None:
                initialization = PhysicalWorkspaceInitialization(
                    tenant_id=self.tenant_id,
                    workspace_id=workspace.id,
                    workspace_type_code=workspace.workspace_type_code,
                    state=PhysicalInitializationState.initializing,
                    template_config_id=template.id,
                    template_code=str(metadata.get("template_code", template.code)),
                    template_revision=int(metadata.get("template_revision", template.revision)),
                    template_content_hash=str(metadata.get("template_content_hash", template.content_hash)),
                    initialization_version=INITIALIZATION_VERSION,
                    revision_version=1,
                    started_by_user_id=self.actor_id,
                    started_at=utc_now(),
                    last_modified_by_user_id=self.actor_id,
                )
                self.db.add(initialization)
                self.db.flush()
                mutation_count += 1
            else:
                initialization.state = PhysicalInitializationState.initializing
                initialization.started_by_user_id = initialization.started_by_user_id or self.actor_id
                initialization.started_at = initialization.started_at or utc_now()
                self._touch(initialization)
                mutation_count += 1
            self._event(
                "physical_workspace.initialization_started",
                workspace,
                initialization,
                before,
                PhysicalInitializationState.initializing,
            )

            defaults = self._apply_defaults(workspace, template)
            if defaults:
                initialization.defaults_applied_json = defaults
                mutation_count += len(defaults)
            assignments = self._ensure_responsible_access(workspace)
            if assignments:
                initialization.assignments_json = assignments
                mutation_count += len(assignments)

            common, specific, checked_template, modules = self._evaluate(workspace)
            self._store_validation(initialization, workspace, common, specific, checked_template, modules)
            blocking = self._blockers(common, specific)
            initialization.state = (
                PhysicalInitializationState.blocked if blocking else PhysicalInitializationState.ready
            )
            initialization.ready_at = None if blocking else utc_now()
            initialization.failure_code = None
            initialization.failure_reason = None
            initialization.last_modified_by_user_id = self.actor_id
            initialization.updated_at = utc_now()
            self._event(
                "physical_workspace.initialization_validated",
                workspace,
                initialization,
                PhysicalInitializationState.initializing,
                initialization.state,
                extra={"blocker_count": len(blocking)},
            )
            self._event(
                "physical_workspace.initialization_blocked" if blocking else "physical_workspace.ready_for_activation",
                workspace,
                initialization,
                PhysicalInitializationState.initializing,
                initialization.state,
                outcome="blocked" if blocking else "success",
            )
            if failure_injector:
                failure_injector(initialization)
            self.db.commit()
            self.db.refresh(initialization)
            return self._out(
                workspace,
                initialization,
                result="BLOCKED" if blocking else "READY",
                mutation_count=mutation_count,
            )
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            if isinstance(exc, IntegrityError):
                workspace = self._workspace(workspace_id, context)
                concurrent = self._initialization(workspace_id)
                if concurrent is not None:
                    return self._out(workspace, concurrent, result="ALREADY_INITIALIZED", mutation_count=0)
            self._record_initialization_failure(workspace_id, type(exc).__name__, str(exc))
            raise

    def validate(
        self,
        workspace_id: int,
        context: EnterprisePermissionContext,
        expected_version: int,
    ) -> PhysicalInitializationOut:
        workspace = self._workspace(workspace_id, context, lock=True)
        initialization = self._initialization(workspace.id, lock=True)
        if initialization is None:
            raise HTTPException(status_code=409, detail="PHYSICAL_INITIALIZATION_NOT_STARTED")
        self._require_version(initialization.revision_version, expected_version)
        if initialization.state == PhysicalInitializationState.activated:
            return self._out(workspace, initialization, result="ALREADY_INITIALIZED", mutation_count=0)
        if workspace.status != "pending":
            raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_MUST_BE_PENDING")
        common, specific, template, modules = self._evaluate(workspace)
        before = initialization.state
        self._store_validation(initialization, workspace, common, specific, template, modules)
        blocking = self._blockers(common, specific)
        initialization.state = PhysicalInitializationState.blocked if blocking else PhysicalInitializationState.ready
        initialization.ready_at = None if blocking else utc_now()
        initialization.failure_code = None
        initialization.failure_reason = None
        self._touch(initialization)
        self._event(
            "physical_workspace.initialization_validated",
            workspace,
            initialization,
            before,
            initialization.state,
            extra={"blocker_count": len(blocking)},
        )
        self._event(
            "physical_workspace.initialization_blocked" if blocking else "physical_workspace.ready_for_activation",
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
    ) -> PhysicalInitializationOut:
        try:
            workspace = self._workspace(workspace_id, context, lock=True)
            initialization = self._initialization(workspace.id, lock=True)
            if workspace.status == "active":
                if initialization and initialization.state == PhysicalInitializationState.activated:
                    return self._out(workspace, initialization, result="ALREADY_ACTIVE", mutation_count=0)
                return self._synthetic(workspace, result="ALREADY_ACTIVE")
            if initialization is None:
                raise HTTPException(status_code=409, detail="PHYSICAL_INITIALIZATION_NOT_STARTED")
            self._require_version(initialization.revision_version, expected_version)
            if workspace.status != "pending" or initialization.state != PhysicalInitializationState.ready:
                raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_NOT_READY_FOR_ACTIVATION")
            request = self._creation_request(workspace)
            if (
                initialization.started_by_user_id == self.actor_id
                or initialization.last_modified_by_user_id == self.actor_id
                or (request and request.requestor_user_id == self.actor_id)
            ):
                raise HTTPException(status_code=403, detail="PHYSICAL_ACTIVATION_SEPARATION_OF_DUTIES_VIOLATION")

            common, specific, template, modules = self._evaluate(workspace)
            validation_hash = self._validation_hash(workspace, template, modules)
            checklist_hash = _hash(
                {
                    "common": [item.model_dump() for item in common],
                    "type_specific": [item.model_dump() for item in specific],
                }
            )
            blockers = self._blockers(common, specific)
            if (
                blockers
                or validation_hash != initialization.validation_hash
                or checklist_hash != initialization.checklist_hash
            ):
                raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_VALIDATION_CHANGED")
            if not self._responsible_access_valid(workspace):
                raise HTTPException(status_code=409, detail="PHYSICAL_WORKSPACE_RESPONSIBLE_ACCESS_INVALID")

            workspace.status = "active"
            workspace.version += 1
            workspace.updated_at = utc_now()
            if failure_injector:
                failure_injector(workspace)
            initialization.state = PhysicalInitializationState.activated
            initialization.activated_by_user_id = self.actor_id
            initialization.activated_at = utc_now()
            initialization.failure_code = None
            initialization.failure_reason = None
            self._touch(initialization)
            self._event(
                "physical_workspace.activated",
                workspace,
                initialization,
                PhysicalInitializationState.ready,
                PhysicalInitializationState.activated,
            )
            self.db.commit()
            self.db.refresh(initialization)
            return self._out(workspace, initialization, result="ACTIVATED", mutation_count=2)
        except HTTPException as exc:
            self.db.rollback()
            self._record_activation_failure(workspace_id, str(exc.detail))
            raise
        except Exception as exc:
            self.db.rollback()
            self._record_activation_failure(workspace_id, str(exc))
            raise

    def list_workspaces(
        self,
        context: EnterprisePermissionContext,
        *,
        workspace_type: str = "",
        business_number: str = "",
        workspace_name: str = "",
        workspace_status: str = "",
        initialization_status: str = "",
        parent: str = "",
        responsible: str = "",
        template: str = "",
    ) -> list[PhysicalWorkspaceListItemOut]:
        statement = select(EnterpriseWorkspace).where(
            EnterpriseWorkspace.tenant_id == self.tenant_id,
            EnterpriseWorkspace.workspace_type_code.in_(SUPPORTED_TYPES),
        )
        if workspace_type.strip():
            normalized = workspace_type.strip().lower().replace("_", "-")
            if normalized not in SUPPORTED_TYPES:
                return []
            statement = statement.where(EnterpriseWorkspace.workspace_type_code == normalized)
        if workspace_status.strip():
            statement = statement.where(EnterpriseWorkspace.status == workspace_status.strip().lower())
        if business_number.strip():
            statement = statement.where(EnterpriseWorkspace.code.ilike(f"%{business_number.strip()}%"))
        if workspace_name.strip():
            statement = statement.where(EnterpriseWorkspace.name.ilike(f"%{workspace_name.strip()}%"))
        if not context.organization_wide:
            statement = statement.where(EnterpriseWorkspace.id.in_(context.workspace_ids or {-1}))
        rows = list(self.db.scalars(statement.order_by(EnterpriseWorkspace.record_code)).all())
        role_codes = set(context.role_codes)
        result: list[PhysicalWorkspaceListItemOut] = []
        for workspace in rows:
            metadata = self._metadata(workspace)
            initialization = self._initialization(workspace.id)
            state = (
                PhysicalInitializationState(initialization.state)
                if initialization
                else self._state_without_record(workspace)
            )
            if initialization_status.strip() and state != initialization_status.strip().upper():
                continue
            parent_workspace = self.db.get(EnterpriseWorkspace, workspace.parent_id) if workspace.parent_id else None
            responsible_user = self.db.get(UserAccount, metadata.get("responsible_user_id"))
            parent_name = parent_workspace.name if parent_workspace else ""
            responsible_name = responsible_user.full_name if responsible_user else ""
            template_code = str(metadata.get("template_code", ""))
            if parent.strip() and parent.strip().lower() not in parent_name.lower():
                continue
            if responsible.strip() and responsible.strip().lower() not in responsible_name.lower():
                continue
            if template.strip() and template.strip().lower() not in template_code.lower():
                continue
            checklist = (
                [*initialization.common_checklist_json, *initialization.type_specific_checklist_json]
                if initialization
                else []
            )
            result.append(
                PhysicalWorkspaceListItemOut(
                    workspace_id=workspace.id,
                    workspace_type_code=workspace.workspace_type_code,
                    workspace_name=workspace.name,
                    business_number=str(metadata.get("business_number", workspace.code)),
                    record_code=workspace.record_code,
                    workspace_status=workspace.status,
                    initialization_state=state,
                    parent=parent_name,
                    responsible=responsible_name,
                    template_code=template_code,
                    blocker_count=sum(1 for item in checklist if item.get("blocking") and item.get("status") == "FAIL"),
                    warning_count=sum(1 for item in checklist if item.get("status") == "WARNING"),
                    revision_version=initialization.revision_version if initialization else workspace.version,
                    can_initialize=bool(role_codes & INITIALIZER_ROLES)
                    and workspace.status == "pending"
                    and state
                    in {
                        PhysicalInitializationState.not_started,
                        PhysicalInitializationState.blocked,
                        PhysicalInitializationState.failed,
                    },
                    can_activate=bool(role_codes & ACTIVATOR_ROLES)
                    and workspace.status == "pending"
                    and state == PhysicalInitializationState.ready,
                )
            )
        return result

    def _evaluate(
        self, workspace: EnterpriseWorkspace
    ) -> tuple[
        list[PhysicalChecklistItemOut],
        list[PhysicalChecklistItemOut],
        AdminConfiguration | None,
        list[PhysicalModuleReadinessOut],
    ]:
        metadata = self._metadata(workspace)
        attributes = dict(metadata.get("attributes", {}))
        parent = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == workspace.parent_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
            )
        )
        template = self._template_from_metadata(metadata)
        responsible_user = self.db.scalar(
            select(UserAccount).where(
                UserAccount.id == metadata.get("responsible_user_id"),
                UserAccount.tenant_id == self.tenant_id,
                UserAccount.status == "active",
            )
        )
        classifications = list(
            self.db.scalars(
                select(EnterpriseWorkspaceClassification).where(
                    EnterpriseWorkspaceClassification.tenant_id == self.tenant_id,
                    EnterpriseWorkspaceClassification.workspace_id == workspace.id,
                )
            ).all()
        )
        classification_pairs = {(item.category_set_code, item.category_item_code) for item in classifications}
        workspace_type = self._latest_configuration("workspace_type", workspace.workspace_type_code)
        required_attributes = {
            self._attribute_code(item)
            for item in (template.content_json.get("required_attributes", []) if template else [])
            if self._attribute_code(item)
        }
        required_attributes.update(
            self._attribute_code(item)
            for item in ((workspace_type.content_json if workspace_type else {}).get("required_attributes", []))
            if self._attribute_code(item)
        )
        required_categories = set(
            (workspace_type.content_json if workspace_type else {}).get("required_categories", [])
        )
        required_categories.update(
            str(item.get("category_set_code", ""))
            for item in (template.content_json.get("default_classifications", []) if template else [])
        )
        selected_category_sets = {item[0] for item in classification_pairs}
        classifications_valid = required_categories.issubset(selected_category_sets) and all(
            self._classification_exists(category_set, item_code) for category_set, item_code in classification_pairs
        )
        modules = self._module_readiness(workspace, metadata)
        enabled_modules = set(metadata.get("enabled_modules", []))
        settings = {
            item.module_key
            for item in self.db.scalars(
                select(WorkspaceModuleSetting).where(
                    WorkspaceModuleSetting.tenant_id == self.tenant_id,
                    WorkspaceModuleSetting.workspace_id == workspace.id,
                    WorkspaceModuleSetting.enabled.is_(True),
                )
            ).all()
        }
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
        allowed_parent_types = set((template.content_json if template else {}).get("applicable_parent_types", []))
        parent_valid = bool(
            parent
            and parent.status == "active"
            and record_valid
            and (not allowed_parent_types or parent.workspace_type_code in allowed_parent_types)
        )
        template_snapshot_valid = bool(
            template
            and metadata.get("template_revision") == template.revision
            and metadata.get("template_content_hash") == template.content_hash
        )
        request = self._creation_request(workspace)
        tenant_scope_valid = all(
            item.tenant_id == self.tenant_id
            for item in (workspace, parent, template, responsible_user, request)
            if item is not None
        )
        common = [
            self._check(
                "workspace_identity_valid",
                identity_unique and bool(workspace.code and workspace.record_code and workspace.external_key),
                "La identidad canónica es completa, única e inmutable.",
                True,
                {"workspace_id": workspace.id},
            ),
            self._check(
                "workspace_type_supported",
                workspace.workspace_type_code in SUPPORTED_TYPES,
                "El Workspace Type pertenece al motor físico permitido.",
                True,
                {"workspace_type": workspace.workspace_type_code},
            ),
            self._check(
                "workspace_status_pending",
                workspace.status == "pending",
                "El Workspace permanece PENDING hasta una activación separada.",
                True,
                {"status": workspace.status},
            ),
            self._check(
                "parent_valid",
                parent_valid,
                "El parent pertenece al tenant, está ACTIVE y es consistente con la jerarquía.",
                True,
                {
                    "parent_id": workspace.parent_id,
                    "parent_type": parent.workspace_type_code if parent else None,
                    "allowed_parent_types": sorted(allowed_parent_types),
                },
            ),
            self._check(
                "business_number_valid",
                bool(workspace.code and metadata.get("business_number") == workspace.code and identity_unique),
                "Business Number tenant-scoped, único e inmutable.",
                True,
                {"business_number": metadata.get("business_number"), "workspace_code": workspace.code},
            ),
            self._check(
                "record_code_valid",
                record_valid and identity_unique,
                "Record Code tenant-scoped y consistente con el parent.",
                True,
                {"record_code": workspace.record_code, "parent_record_code": parent.record_code if parent else None},
            ),
            self._check(
                "external_key_valid",
                bool(workspace.external_key and identity_unique),
                "external_key estable y único.",
                True,
                {"external_key": workspace.external_key},
            ),
            self._check(
                "template_assigned",
                template is not None,
                "Existe el template exacto usado en Materialization.",
                True,
                {"template_config_id": metadata.get("template_id")},
            ),
            self._check(
                "template_snapshot_valid",
                template_snapshot_valid,
                "La revisión y huella del template coinciden; no hay auto-upgrade.",
                True,
                {
                    "expected_revision": metadata.get("template_revision"),
                    "actual_revision": template.revision if template else None,
                    "expected_hash": metadata.get("template_content_hash"),
                    "actual_hash": template.content_hash if template else None,
                },
            ),
            self._check(
                "responsible_assigned",
                responsible_user is not None,
                "Responsible activo y del mismo tenant.",
                True,
                {"responsible_user_id": metadata.get("responsible_user_id")},
            ),
            self._check(
                "responsible_access_valid",
                self._responsible_access_valid(workspace),
                "Responsible con asignación mínima Workspace-scoped.",
                True,
                {"role_code": RESPONSIBLE_ROLE},
            ),
            self._check(
                "required_attributes_complete",
                all(attributes.get(code) not in (None, "", []) for code in required_attributes),
                "Los atributos configurados como obligatorios están completos.",
                True,
                {"required": sorted(required_attributes)},
            ),
            self._check(
                "required_classifications_valid",
                classifications_valid,
                "Las clasificaciones obligatorias existen y son válidas.",
                True,
                {"required": sorted(required_categories), "selected": sorted(selected_category_sets)},
            ),
            self._check(
                "module_settings_valid",
                settings == enabled_modules and all(item.state == "READY" for item in modules if not item.planned),
                "Los módulos existentes habilitados tienen definition publicada y setting válido.",
                True,
                {"enabled": sorted(enabled_modules), "settings": sorted(settings)},
            ),
            self._check(
                "tenant_scope_valid",
                tenant_scope_valid,
                "Workspace, parent, template, responsible y request pertenecen al tenant.",
                True,
                {"tenant_id": self.tenant_id},
            ),
            self._check(
                "no_core_revision_required",
                True,
                "La inicialización no crea ni modifica revisiones CORE.",
                True,
                {"core_mutation": False, "published_release_id": self._published_release_id()},
            ),
        ]
        specific = self._type_specific_checks(
            workspace,
            metadata,
            attributes,
            classification_pairs,
            parent,
            responsible_user,
            required_attributes,
            template,
        )
        return common, specific, template, modules

    def _type_specific_checks(
        self,
        workspace: EnterpriseWorkspace,
        metadata: dict[str, Any],
        attributes: dict[str, Any],
        classifications: set[tuple[str, str]],
        parent: EnterpriseWorkspace | None,
        responsible: UserAccount | None,
        required_attributes: set[str],
        template: AdminConfiguration | None,
    ) -> list[PhysicalChecklistItemOut]:
        type_code = workspace.workspace_type_code
        manager_code = {
            "property": "property_manager_valid",
            "facility": "facility_responsible_valid",
            "warehouse": "warehouse_manager_valid",
        }[type_code]
        type_check = f"{type_code}_type_valid"
        result: list[PhysicalChecklistItemOut] = []
        for code in TYPE_CHECKS[type_code]:
            passed = True
            evidence: dict[str, Any] = {}
            if code == type_check:
                value = self._first_value(
                    attributes,
                    f"{type_code}_type",
                    f"{type_code}-type",
                    "type",
                )
                classified = any(category_set == f"{type_code}-type" for category_set, _item in classifications)
                passed = bool(value or classified)
                evidence = {"attribute": value, "classification_present": classified}
            elif code == manager_code:
                passed = responsible is not None and self._responsible_access_valid(workspace)
                evidence = {"responsible_user_id": metadata.get("responsible_user_id")}
            elif code in {"ownership_tenure_consistent", "legal_status_consistent", "operational_status_valid"}:
                value = self._first_value(attributes, code.replace("_consistent", ""), code.replace("_valid", ""))
                passed = value not in (None, "", [])
                evidence = {"value": value}
            elif code == "geographic_information_valid":
                geographic = {
                    key: self._first_value(attributes, key)
                    for key in (
                        "country",
                        "state",
                        "department",
                        "city",
                        "municipality",
                        "address",
                        "latitude",
                        "longitude",
                    )
                }
                passed = any(value not in (None, "", []) for value in geographic.values())
                evidence = geographic
            elif code in {"property_area_values_valid", "area_values_consistent"}:
                values = [
                    self._number(attributes, key) for key in ("land_area", "built_area", "gross_area", "usable_area")
                ]
                present = [value for value in values if value is not None]
                passed = bool(present) and all(value >= 0 for value in present)
                evidence = {"values": present}
            elif code == "property_value_fields_valid":
                values = [self._number(attributes, key) for key in ("book_value", "market_value")]
                present = [value for value in values if value is not None]
                passed = bool(present) and all(value >= 0 for value in present)
                evidence = {"values": present}
            elif code in {"capacity_consistent", "storage_capacity_consistent"}:
                value = self._number(attributes, "capacity", "storage_capacity")
                passed = value is not None and value >= 0
                evidence = {"value": value}
            elif code == "capacity_unit_valid":
                value = self._first_value(attributes, "capacity_unit", "unit_of_capacity", "storage_capacity_unit")
                passed = value not in (None, "", [])
                evidence = {"value": value}
            elif code == "criticality_valid":
                value = self._first_value(attributes, "criticality")
                passed = value not in (None, "", [])
                evidence = {"value": value}
            elif code == "commissioning_data_consistent":
                value = self._first_value(attributes, "commissioning_date", "commissioning_status")
                passed = value not in (None, "", [])
                evidence = {"value": value}
            elif code == "parent_context_valid":
                allowed = set((template.content_json if template else {}).get("applicable_parent_types", []))
                passed = bool(parent and (not allowed or parent.workspace_type_code in allowed))
                evidence = {"parent_type": parent.workspace_type_code if parent else None, "allowed": sorted(allowed)}

            blocking = self._specific_blocking(code, required_attributes, template)
            if passed:
                status = "PASS"
            elif blocking:
                status = "FAIL"
            else:
                status = "WARNING"
            result.append(
                PhysicalChecklistItemOut(
                    code=code,
                    status=status,
                    message=self._specific_message(code, passed, blocking),
                    blocking=blocking,
                    evidence=evidence,
                )
            )
        return result

    @staticmethod
    def _specific_blocking(code: str, required_attributes: set[str], template: AdminConfiguration | None) -> bool:
        configured = dict((template.content_json if template else {}).get("initialization_check_severity", {}))
        if code in configured:
            return str(configured[code]).lower() == "blocking"
        if code.endswith(("_type_valid", "_manager_valid")) or code == "facility_responsible_valid":
            return True
        aliases = {
            "ownership_tenure_consistent": {"ownership_tenure", "ownership", "tenure"},
            "legal_status_consistent": {"legal_status"},
            "operational_status_valid": {"operational_status"},
            "property_area_values_valid": {"land_area", "built_area"},
            "property_value_fields_valid": {"book_value", "market_value"},
            "capacity_consistent": {"capacity"},
            "area_values_consistent": {"gross_area", "usable_area"},
            "criticality_valid": {"criticality"},
            "commissioning_data_consistent": {"commissioning_date"},
            "storage_capacity_consistent": {"storage_capacity"},
            "capacity_unit_valid": {"capacity_unit", "unit_of_capacity"},
            "parent_context_valid": {"parent"},
        }
        return bool(aliases.get(code, set()) & required_attributes)

    @staticmethod
    def _specific_message(code: str, passed: bool, blocking: bool) -> str:
        label = code.replace("_", " ")
        if passed:
            return f"{label}: validación satisfactoria."
        if blocking:
            return f"{label}: falta o es inconsistente según configuración obligatoria."
        return f"{label}: información opcional incompleta; se registra como advertencia."

    def _module_readiness(
        self, workspace: EnterpriseWorkspace, metadata: dict[str, Any]
    ) -> list[PhysicalModuleReadinessOut]:
        enabled = set(metadata.get("enabled_modules", []))
        planned = set(metadata.get("planned_modules", [])) - enabled
        settings = {
            item.module_key: item
            for item in self.db.scalars(
                select(WorkspaceModuleSetting).where(
                    WorkspaceModuleSetting.tenant_id == self.tenant_id,
                    WorkspaceModuleSetting.workspace_id == workspace.id,
                )
            ).all()
        }
        definitions = {
            item.code: item
            for item in self.db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == "module_definition",
                    AdminConfiguration.code.in_(enabled or {""}),
                    AdminConfiguration.status == "published",
                )
            ).all()
        }
        result = [
            PhysicalModuleReadinessOut(
                module_key=key,
                state="READY" if key in settings and settings[key].enabled and key in definitions else "BLOCKED",
                operational_module_created=False,
                planned=False,
                evidence={
                    "setting_id": settings[key].id if key in settings else None,
                    "definition_revision": definitions[key].revision if key in definitions else None,
                },
            )
            for key in sorted(enabled)
        ]
        result.extend(
            PhysicalModuleReadinessOut(
                module_key=key,
                state="PLANNED",
                operational_module_created=False,
                planned=True,
                evidence={"workspace_module_setting_created": key in settings},
            )
            for key in sorted(planned)
        )
        return result

    def _apply_defaults(self, workspace: EnterpriseWorkspace, template: AdminConfiguration) -> dict[str, Any]:
        physical = dict(self._metadata(workspace))
        attributes = dict(physical.get("attributes", {}))
        explicit = set(physical.get("explicit_attribute_codes", attributes.keys()))
        template_defaults = dict(template.content_json.get("default_attributes", {}))
        workspace_type = self._latest_configuration("workspace_type", workspace.workspace_type_code)
        tenant_defaults = dict((workspace_type.content_json if workspace_type else {}).get("default_attributes", {}))
        applied: dict[str, Any] = {}
        for source, source_name in ((template_defaults, "template"), (tenant_defaults, "tenant_workspace_type")):
            for key, value in source.items():
                if key in explicit or attributes.get(key) not in (None, "", []):
                    continue
                attributes[key] = value
                applied[key] = {"value": value, "source": source_name}
        if applied:
            physical["attributes"] = attributes
            defaults = dict(workspace.defaults_json or {})
            defaults["_physical"] = physical
            workspace.defaults_json = defaults
            workspace.version += 1
            workspace.updated_at = utc_now()
            self.db.flush()
        return applied

    def _ensure_responsible_access(self, workspace: EnterpriseWorkspace) -> list[dict[str, Any]]:
        responsible_id = self._metadata(workspace).get("responsible_user_id")
        if not responsible_id:
            return []
        role = self.db.scalar(
            select(SecurityRole).where(
                SecurityRole.tenant_id == self.tenant_id,
                SecurityRole.code == RESPONSIBLE_ROLE,
                SecurityRole.status == "active",
            )
        )
        user = self.db.scalar(
            select(UserAccount).where(
                UserAccount.id == responsible_id,
                UserAccount.tenant_id == self.tenant_id,
                UserAccount.status == "active",
            )
        )
        if role is None or user is None:
            return []
        existing = self.db.scalar(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.tenant_id == self.tenant_id,
                SecurityAccessAssignment.workspace_id == workspace.id,
                SecurityAccessAssignment.user_id == responsible_id,
                SecurityAccessAssignment.role_id == role.id,
                SecurityAccessAssignment.status == "active",
            )
        )
        if existing:
            return []
        assignment = SecurityAccessAssignment(
            tenant_id=self.tenant_id,
            subject_type="user",
            user_id=responsible_id,
            role_id=role.id,
            scope_type="workspace",
            workspace_id=workspace.id,
            status="active",
            granted_by_user_id=self.actor_id,
        )
        self.db.add(assignment)
        self.db.flush()
        return [{"assignment_id": assignment.id, "role_code": RESPONSIBLE_ROLE, "user_id": responsible_id}]

    def _responsible_access_valid(self, workspace: EnterpriseWorkspace) -> bool:
        responsible_id = self._metadata(workspace).get("responsible_user_id")
        if not responsible_id:
            return False
        return (
            self.db.scalar(
                select(SecurityAccessAssignment.id)
                .join(SecurityRole, SecurityRole.id == SecurityAccessAssignment.role_id)
                .join(UserAccount, UserAccount.id == SecurityAccessAssignment.user_id)
                .where(
                    SecurityAccessAssignment.tenant_id == self.tenant_id,
                    SecurityAccessAssignment.workspace_id == workspace.id,
                    SecurityAccessAssignment.user_id == responsible_id,
                    SecurityAccessAssignment.status == "active",
                    SecurityAccessAssignment.scope_type == "workspace",
                    SecurityRole.code == RESPONSIBLE_ROLE,
                    SecurityRole.status == "active",
                    UserAccount.tenant_id == self.tenant_id,
                    UserAccount.status == "active",
                )
            )
            is not None
        )

    def _store_validation(
        self,
        initialization: PhysicalWorkspaceInitialization,
        workspace: EnterpriseWorkspace,
        common: list[PhysicalChecklistItemOut],
        specific: list[PhysicalChecklistItemOut],
        template: AdminConfiguration | None,
        modules: list[PhysicalModuleReadinessOut],
    ) -> None:
        initialization.common_checklist_json = [item.model_dump() for item in common]
        initialization.type_specific_checklist_json = [item.model_dump() for item in specific]
        initialization.module_states_json = {item.module_key: item.model_dump() for item in modules}
        initialization.validation_hash = self._validation_hash(workspace, template, modules)
        initialization.checklist_hash = _hash(
            {
                "common": initialization.common_checklist_json,
                "type_specific": initialization.type_specific_checklist_json,
            }
        )
        initialization.validated_by_user_id = self.actor_id
        initialization.validated_at = utc_now()

    def _validation_hash(
        self,
        workspace: EnterpriseWorkspace,
        template: AdminConfiguration | None,
        modules: list[PhysicalModuleReadinessOut],
    ) -> str:
        metadata = self._metadata(workspace)
        classifications = sorted(
            [
                [item.category_set_code, item.category_item_code]
                for item in self.db.scalars(
                    select(EnterpriseWorkspaceClassification).where(
                        EnterpriseWorkspaceClassification.tenant_id == self.tenant_id,
                        EnterpriseWorkspaceClassification.workspace_id == workspace.id,
                    )
                ).all()
            ]
        )
        assignments = sorted(
            self.db.scalars(
                select(SecurityAccessAssignment.id).where(
                    SecurityAccessAssignment.tenant_id == self.tenant_id,
                    SecurityAccessAssignment.workspace_id == workspace.id,
                    SecurityAccessAssignment.status == "active",
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
                "physical": metadata,
                "template": {
                    "id": template.id if template else None,
                    "code": template.code if template else None,
                    "revision": template.revision if template else None,
                    "hash": template.content_hash if template else None,
                },
                "modules": [item.model_dump() for item in modules],
                "assignments": assignments,
                "classifications": classifications,
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
        )
        if lock:
            statement = statement.with_for_update()
        workspace = self.db.scalar(statement)
        if workspace is None or (not context.organization_wide and workspace.id not in context.workspace_ids):
            raise HTTPException(status_code=404, detail="Physical Workspace not found")
        if workspace.workspace_type_code not in SUPPORTED_TYPES:
            raise HTTPException(status_code=409, detail="WORKSPACE_TYPE_NOT_ELIGIBLE_FOR_PHYSICAL_INITIALIZATION")
        return workspace

    def _initialization(self, workspace_id: int, *, lock: bool = False) -> PhysicalWorkspaceInitialization | None:
        statement = select(PhysicalWorkspaceInitialization).where(
            PhysicalWorkspaceInitialization.tenant_id == self.tenant_id,
            PhysicalWorkspaceInitialization.workspace_id == workspace_id,
        )
        if lock:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def _creation_request(self, workspace: EnterpriseWorkspace) -> PhysicalWorkspaceCreationRequest | None:
        request_id = self._metadata(workspace).get("creation_request_id")
        if not request_id:
            return None
        return self.db.scalar(
            select(PhysicalWorkspaceCreationRequest).where(
                PhysicalWorkspaceCreationRequest.id == request_id,
                PhysicalWorkspaceCreationRequest.tenant_id == self.tenant_id,
                PhysicalWorkspaceCreationRequest.materialized_workspace_id == workspace.id,
            )
        )

    def _template_from_metadata(self, metadata: dict[str, Any]) -> AdminConfiguration | None:
        template_id = metadata.get("template_id")
        if not template_id:
            return None
        return self.db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.id == template_id,
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == "physical_template",
            )
        )

    def _latest_configuration(self, kind: str, code: str) -> AdminConfiguration | None:
        return self.db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == kind,
                AdminConfiguration.code == code,
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
            .limit(1)
        )

    def _classification_exists(self, category_set: str, item_code: str) -> bool:
        catalog = self._latest_configuration("catalog", category_set)
        if catalog is None:
            return False
        return any(str(item.get("code", "")) == item_code for item in catalog.content_json.get("items", []))

    def _published_release_id(self) -> int | None:
        return self.db.scalar(
            select(EnterpriseCoreRelease.id).where(
                EnterpriseCoreRelease.tenant_id == self.tenant_id,
                EnterpriseCoreRelease.state == "published",
            )
        )

    def _synthetic(self, workspace: EnterpriseWorkspace, *, result: str) -> PhysicalInitializationOut:
        common, specific, template, modules = (
            self._evaluate(workspace) if workspace.status != "active" else ([], [], None, [])
        )
        return self._build_out(
            workspace,
            None,
            result=result,
            persisted=False,
            state=self._state_without_record(workspace),
            common=common,
            specific=specific,
            template=template,
            modules=modules,
            revision_version=workspace.version,
            mutation_count=0,
        )

    def _out(
        self,
        workspace: EnterpriseWorkspace,
        initialization: PhysicalWorkspaceInitialization,
        *,
        result: str,
        mutation_count: int,
    ) -> PhysicalInitializationOut:
        return self._build_out(
            workspace,
            initialization,
            result=result,
            persisted=True,
            state=PhysicalInitializationState(initialization.state),
            common=[PhysicalChecklistItemOut.model_validate(item) for item in initialization.common_checklist_json],
            specific=[
                PhysicalChecklistItemOut.model_validate(item) for item in initialization.type_specific_checklist_json
            ],
            template=self.db.get(AdminConfiguration, initialization.template_config_id),
            modules=[
                PhysicalModuleReadinessOut.model_validate(item)
                for _key, item in sorted(initialization.module_states_json.items())
            ],
            revision_version=initialization.revision_version,
            mutation_count=mutation_count,
        )

    def _build_out(
        self,
        workspace: EnterpriseWorkspace,
        initialization: PhysicalWorkspaceInitialization | None,
        *,
        result: str,
        persisted: bool,
        state: PhysicalInitializationState,
        common: list[PhysicalChecklistItemOut],
        specific: list[PhysicalChecklistItemOut],
        template: AdminConfiguration | None,
        modules: list[PhysicalModuleReadinessOut],
        revision_version: int,
        mutation_count: int,
    ) -> PhysicalInitializationOut:
        metadata = self._metadata(workspace)
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
        checklist = [*common, *specific]
        blockers = sum(1 for item in checklist if item.blocking and item.status == "FAIL")
        warnings = sum(1 for item in checklist if item.status == "WARNING")
        completed = sum(1 for item in checklist if item.status in {"PASS", "WARNING"})
        return PhysicalInitializationOut(
            result=result,
            persisted=persisted,
            initialization_id=initialization.id if initialization else None,
            workspace_id=workspace.id,
            workspace_type_code=workspace.workspace_type_code,
            workspace_name=workspace.name,
            workspace_status=workspace.status,
            business_number=str(metadata.get("business_number", workspace.code)),
            record_code=workspace.record_code,
            external_key=str(workspace.external_key or ""),
            parent=parent.name if parent else "",
            responsible=responsible.full_name if responsible else "",
            state=state,
            progress_percent=round(completed / len(checklist) * 100)
            if checklist
            else (100 if state == PhysicalInitializationState.activated else 0),
            blocker_count=blockers,
            warning_count=warnings,
            common_checklist=common,
            type_specific_checklist=specific,
            template_config_id=template.id if template else None,
            template_code=str(metadata.get("template_code", template.code if template else "")),
            template_revision=metadata.get("template_revision"),
            template_content_hash=str(metadata.get("template_content_hash", "")),
            attributes=dict(metadata.get("attributes", {})),
            classifications=classifications,
            enabled_modules=list(metadata.get("enabled_modules", [])),
            planned_modules=list(metadata.get("planned_modules", [])),
            modules=modules,
            defaults_applied=initialization.defaults_applied_json if initialization else {},
            assignments=initialization.assignments_json if initialization else [],
            validation_hash=initialization.validation_hash if initialization else None,
            checklist_hash=initialization.checklist_hash
            if initialization
            else _hash(
                {
                    "common": [item.model_dump() for item in common],
                    "type_specific": [item.model_dump() for item in specific],
                }
            ),
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
        initialization: PhysicalWorkspaceInitialization,
        state_before: str,
        state_after: str,
        *,
        outcome: str = "success",
        extra: dict[str, Any] | None = None,
    ) -> None:
        metadata = self._metadata(workspace)
        common_hash = _hash(initialization.common_checklist_json)
        specific_hash = _hash(initialization.type_specific_checklist_json)
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome=outcome,
                target_type="physical_workspace",
                target_id=workspace.id,
                metadata_json={
                    "tenant_id": self.tenant_id,
                    "workspace_id": workspace.id,
                    "workspace_type": workspace.workspace_type_code,
                    "business_number": metadata.get("business_number", workspace.code),
                    "record_code": workspace.record_code,
                    "actor": self.actor_id,
                    "responsible": metadata.get("responsible_user_id"),
                    "template": initialization.template_code,
                    "template_revision": initialization.template_revision,
                    "state_before": str(state_before),
                    "state_after": str(state_after),
                    "common_checklist_hash": common_hash,
                    "type_specific_checklist_hash": specific_hash,
                    "validation_hash": initialization.validation_hash,
                    "blocking_issues": [item.code for item in self._blockers_from_json(initialization)],
                    "warnings": [
                        item.get("code")
                        for item in [
                            *initialization.common_checklist_json,
                            *initialization.type_specific_checklist_json,
                        ]
                        if item.get("status") == "WARNING"
                    ],
                    "enabled_modules": metadata.get("enabled_modules", []),
                    "planned_modules": metadata.get("planned_modules", []),
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
                EnterpriseWorkspace.workspace_type_code.in_(SUPPORTED_TYPES),
            )
        )
        if workspace is None or workspace.status != "pending":
            return
        initialization = self._initialization(workspace.id)
        metadata = self._metadata(workspace)
        template = self._template_from_metadata(metadata)
        if initialization is None and template is not None:
            initialization = PhysicalWorkspaceInitialization(
                tenant_id=self.tenant_id,
                workspace_id=workspace.id,
                workspace_type_code=workspace.workspace_type_code,
                state=PhysicalInitializationState.failed,
                template_config_id=template.id,
                template_code=str(metadata.get("template_code", template.code)),
                template_revision=int(metadata.get("template_revision", template.revision)),
                template_content_hash=str(metadata.get("template_content_hash", template.content_hash)),
                initialization_version=INITIALIZATION_VERSION,
                revision_version=1,
                started_by_user_id=self.actor_id,
                started_at=utc_now(),
                last_modified_by_user_id=self.actor_id,
            )
            self.db.add(initialization)
            self.db.flush()
        if initialization is None:
            return
        before = initialization.state
        initialization.state = PhysicalInitializationState.failed
        initialization.failure_code = code[:120]
        initialization.failure_reason = reason[:2000]
        initialization.last_modified_by_user_id = self.actor_id
        initialization.updated_at = utc_now()
        self._event(
            "physical_workspace.initialization_failed",
            workspace,
            initialization,
            before,
            PhysicalInitializationState.failed,
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
            "physical_workspace.activation_failed",
            workspace,
            initialization,
            initialization.state,
            initialization.state,
            outcome="failure",
            extra={"reason": reason[:500]},
        )
        self.db.commit()

    @staticmethod
    def _metadata(workspace: EnterpriseWorkspace) -> dict[str, Any]:
        return dict((workspace.defaults_json or {}).get("_physical", {}))

    @staticmethod
    def _state_without_record(workspace: EnterpriseWorkspace) -> PhysicalInitializationState:
        return (
            PhysicalInitializationState.activated
            if workspace.status == "active"
            else PhysicalInitializationState.not_started
        )

    @staticmethod
    def _require_version(current: int, expected: int) -> None:
        if current != expected:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PHYSICAL_WORKSPACE_VERSION_CONFLICT",
                    "message": "Physical Workspace initialization changed; refresh and retry.",
                    "current_version": current,
                },
            )

    @staticmethod
    def _touch(initialization: PhysicalWorkspaceInitialization) -> None:
        initialization.revision_version += 1
        initialization.updated_at = utc_now()

    @staticmethod
    def _blockers(
        common: list[PhysicalChecklistItemOut], specific: list[PhysicalChecklistItemOut]
    ) -> list[PhysicalChecklistItemOut]:
        return [item for item in [*common, *specific] if item.blocking and item.status == "FAIL"]

    @staticmethod
    def _blockers_from_json(initialization: PhysicalWorkspaceInitialization) -> list[PhysicalChecklistItemOut]:
        return [
            PhysicalChecklistItemOut.model_validate(item)
            for item in [*initialization.common_checklist_json, *initialization.type_specific_checklist_json]
            if item.get("blocking") and item.get("status") == "FAIL"
        ]

    @staticmethod
    def _check(
        code: str, passed: bool, message: str, blocking: bool, evidence: dict[str, Any]
    ) -> PhysicalChecklistItemOut:
        return PhysicalChecklistItemOut(
            code=code,
            status="PASS" if passed else "FAIL",
            message=message,
            blocking=blocking,
            evidence=evidence,
        )

    @staticmethod
    def _attribute_code(value: Any) -> str:
        if isinstance(value, dict):
            value = value.get("code", "")
        return str(value).strip().lower().replace(" ", "_").replace("-", "_")

    @staticmethod
    def _first_value(attributes: dict[str, Any], *keys: str) -> Any:
        normalized = {
            str(key).strip().lower().replace(" ", "_").replace("-", "_"): value for key, value in attributes.items()
        }
        for key in keys:
            value = normalized.get(key.strip().lower().replace(" ", "_").replace("-", "_"))
            if value not in (None, "", []):
                return value
        return None

    @classmethod
    def _number(cls, attributes: dict[str, Any], *keys: str) -> float | None:
        value = cls._first_value(attributes, *keys)
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
