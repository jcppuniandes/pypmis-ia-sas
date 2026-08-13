"""Application service for Active Workspace Context, Home and switching."""

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import (
    AdminConfiguration,
    EnterpriseWorkspace,
    PermissionCatalog,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityGroupMember,
    SecurityRolePermission,
    UserAccount,
    WorkspaceModuleSetting,
)
from app.modules.enterprise_structure.models import EnterpriseWorkspaceLink
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.workspace_context.models import RecentWorkspace
from app.modules.workspace_context.navigator import SUPPORTED_WORKSPACE_TYPES, WorkspaceNavigatorService
from app.modules.workspace_context.schemas import (
    ActiveWorkspaceContextOut,
    MyWorkspaceOut,
    RecentWorkspaceOut,
    WorkspaceContextOut,
    WorkspaceHomeOut,
    WorkspaceIdentityOut,
    WorkspaceModuleAccessOut,
    WorkspaceNavigatorItemOut,
    WorkspaceReferenceOut,
    WorkspaceResponsibleOut,
    WorkspaceTemplateOut,
)


class WorkspaceOperationalContextService:
    def __init__(
        self,
        db: Session,
        tenant_id: int,
        actor_id: int,
        permission_context: EnterprisePermissionContext,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.permission_context = permission_context
        self.navigator_service = WorkspaceNavigatorService(db, tenant_id)

    def context(self, workspace_id: int, *, audit: bool = True) -> WorkspaceContextOut:
        workspace = self._workspace(workspace_id)
        context = self._context_out(workspace)
        if audit:
            self._event("workspace.context_loaded", workspace)
            self.db.commit()
        return context

    def open(self, workspace_id: int, route: str = "") -> WorkspaceContextOut:
        workspace = self._workspace(workspace_id)
        context = self._context_out(workspace)
        default_route = f"/workspaces/{workspace.id}/home"
        chosen_route = route.strip() or default_route
        self._validate_route(workspace, context.navigator, chosen_route)
        previous = self.db.scalar(
            select(RecentWorkspace)
            .where(RecentWorkspace.tenant_id == self.tenant_id, RecentWorkspace.user_id == self.actor_id)
            .order_by(RecentWorkspace.last_opened_at.desc())
            .limit(1)
        )
        recent = self._recent(workspace.id)
        if recent is None:
            recent = RecentWorkspace(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                workspace_id=workspace.id,
                last_route=chosen_route,
                last_opened_at=utc_now(),
            )
            self.db.add(recent)
        else:
            recent.last_route = chosen_route
            recent.last_opened_at = utc_now()
            recent.version += 1
        if previous is not None and previous.workspace_id != workspace.id:
            self._event(
                "workspace.context_switched",
                workspace,
                {"previous_workspace_id": previous.workspace_id},
            )
        self._event("workspace.opened", workspace, {"route": chosen_route})
        self.db.commit()
        return self._context_out(workspace)

    def home(self, workspace_id: int) -> WorkspaceHomeOut:
        workspace = self._workspace(workspace_id)
        context = self._context_out(workspace)
        links = self.db.scalars(
            select(EnterpriseWorkspaceLink).where(
                EnterpriseWorkspaceLink.tenant_id == self.tenant_id,
                EnterpriseWorkspaceLink.status == "active",
                or_(
                    EnterpriseWorkspaceLink.source_workspace_id == workspace.id,
                    EnterpriseWorkspaceLink.target_workspace_id == workspace.id,
                ),
            )
        ).all()
        related_ids = {
            item.target_workspace_id if item.source_workspace_id == workspace.id else item.source_workspace_id
            for item in links
        }
        related = list(
            self.db.scalars(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id.in_(related_ids or {-1}),
                )
            ).all()
        )
        return WorkspaceHomeOut(
            workspace=context.identity,
            breadcrumb=context.breadcrumb,
            responsible=context.responsible,
            status=context.identity.workspace_status,
            enabled_modules=context.enabled_modules,
            planned_modules=context.planned_modules,
            recent_activity=[],
            recent_documents=[],
            my_tasks=[],
            related_workspaces=[self._reference(item) for item in related if self._has_workspace_access(item.id)],
            allowed_actions=context.allowed_actions,
            capability_flags={
                "recent_activity": False,
                "recent_documents": False,
                "my_tasks": False,
                "related_workspaces": True,
            },
        )

    def navigator(self, workspace_id: int) -> list[WorkspaceNavigatorItemOut]:
        return self._context_out(self._workspace(workspace_id)).navigator

    def module_access(self, workspace_id: int, module_code: str) -> WorkspaceModuleAccessOut:
        workspace = self._workspace(workspace_id)
        context = self._context_out(workspace)
        normalized = self._slug(module_code)
        module = next((item for item in context.navigator if item.code == normalized), None)
        if module is None:
            raise HTTPException(status_code=403, detail="MODULE_DISABLED_OR_PERMISSION_DENIED")
        if module.state == "PLANNED":
            raise HTTPException(status_code=409, detail="PLANNED_MODULE_IS_NOT_OPERATIONAL")
        if workspace.status not in {"active", "archived"} and normalized not in {"home", "overview"}:
            raise HTTPException(status_code=409, detail="WORKSPACE_NOT_ACTIVE")
        self._event("workspace.module_opened", workspace, {"module_code": normalized})
        self.db.commit()
        return WorkspaceModuleAccessOut(
            workspace_id=workspace.id,
            module=module,
            data_scope={"tenant_id": self.tenant_id, "workspace_id": workspace.id},
        )

    def recent(self) -> list[RecentWorkspaceOut]:
        rows = self.db.scalars(
            select(RecentWorkspace)
            .where(RecentWorkspace.tenant_id == self.tenant_id, RecentWorkspace.user_id == self.actor_id)
            .order_by(RecentWorkspace.last_opened_at.desc())
            .limit(12)
        ).all()
        workspaces = {
            item.id: item
            for item in self.db.scalars(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id.in_({row.workspace_id for row in rows} or {-1}),
                )
            ).all()
        }
        return [
            RecentWorkspaceOut(
                workspace_id=workspace.id,
                workspace_name=workspace.name,
                workspace_type=workspace.workspace_type_code.upper(),
                business_number=self._business_number(workspace),
                status=workspace.status.upper(),
                last_opened_at=row.last_opened_at,
                last_route=row.last_route,
            )
            for row in rows
            if (workspace := workspaces.get(row.workspace_id)) is not None and self._has_workspace_access(workspace.id)
        ]

    def update_last_route(self, workspace_id: int, route: str) -> RecentWorkspaceOut:
        workspace = self._workspace(workspace_id)
        context = self._context_out(workspace)
        self._validate_route(workspace, context.navigator, route)
        recent = self._recent(workspace.id)
        if recent is None:
            recent = RecentWorkspace(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                workspace_id=workspace.id,
                last_route=route,
                last_opened_at=utc_now(),
            )
            self.db.add(recent)
        else:
            recent.last_route = route
            recent.version += 1
        self.db.commit()
        self.db.refresh(recent)
        return RecentWorkspaceOut(
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            workspace_type=workspace.workspace_type_code.upper(),
            business_number=self._business_number(workspace),
            status=workspace.status.upper(),
            last_opened_at=recent.last_opened_at,
            last_route=recent.last_route,
        )

    def my_workspaces(
        self,
        *,
        workspace_type: str = "",
        status: str = "",
        responsible: str = "",
        parent: str = "",
        business_number: str = "",
        name: str = "",
    ) -> list[MyWorkspaceOut]:
        statement = select(EnterpriseWorkspace).where(
            EnterpriseWorkspace.tenant_id == self.tenant_id,
            EnterpriseWorkspace.workspace_type_code.in_(SUPPORTED_WORKSPACE_TYPES),
        )
        if not self.permission_context.organization_wide:
            statement = statement.where(EnterpriseWorkspace.id.in_(self.permission_context.workspace_ids or {-1}))
        if workspace_type.strip():
            statement = statement.where(EnterpriseWorkspace.workspace_type_code == self._slug(workspace_type))
        if status.strip():
            statement = statement.where(EnterpriseWorkspace.status == status.strip().lower())
        if name.strip():
            statement = statement.where(EnterpriseWorkspace.name.ilike(f"%{name.strip()}%"))
        rows = list(self.db.scalars(statement.order_by(EnterpriseWorkspace.name)).all())
        result: list[MyWorkspaceOut] = []
        for workspace in rows:
            responsible_user = self._responsible(workspace)
            parent_workspace = self.db.get(EnterpriseWorkspace, workspace.parent_id) if workspace.parent_id else None
            number = self._business_number(workspace)
            if responsible.strip() and responsible.strip().lower() not in responsible_user.name.lower():
                continue
            if parent.strip() and parent.strip().lower() not in (parent_workspace.name.lower() if parent_workspace else ""):
                continue
            if business_number.strip() and business_number.strip().lower() not in number.lower():
                continue
            recent = self._recent(workspace.id)
            result.append(
                MyWorkspaceOut(
                    workspace_id=workspace.id,
                    workspace_name=workspace.name,
                    workspace_type=workspace.workspace_type_code.upper(),
                    business_number=number,
                    record_code=workspace.record_code,
                    status=workspace.status.upper(),
                    responsible=responsible_user.name,
                    parent=parent_workspace.name if parent_workspace else "",
                    last_route=recent.last_route if recent else f"/workspaces/{workspace.id}/home",
                )
            )
        return result

    def _context_out(self, workspace: EnterpriseWorkspace) -> WorkspaceContextOut:
        path = self._path(workspace)
        permissions = self._permission_keys()
        navigator, enabled, planned = self.navigator_service.resolve(workspace, user_permissions=permissions)
        template = self._template(workspace)
        responsible = self._responsible(workspace)
        recent = self._recent(workspace.id)
        etag = self._etag(workspace, navigator, template)
        workspace_permissions = sorted(
            key
            for key in permissions
            if key.startswith("workspace.") or key in {item.permission_key for item in navigator if item.permission_key}
        )
        allowed_actions = ["open", "read_home", "read_navigator"]
        if workspace.status == "active":
            allowed_actions.append("open_operational_module")
        elif workspace.status == "pending":
            allowed_actions.append("view_lifecycle")
        if workspace.status == "archived":
            allowed_actions.append("read_only")
        identity = self._identity(workspace)
        breadcrumb = [self._reference(item) for item in path]
        active = ActiveWorkspaceContextOut(
            tenant_id=self.tenant_id,
            workspace_id=workspace.id,
            workspace_type=workspace.workspace_type_code.upper(),
            workspace_name=workspace.name,
            workspace_status=workspace.status.upper(),
            business_number=identity.business_number,
            record_code=workspace.record_code,
            external_key=identity.external_key,
            parent_workspace_id=workspace.parent_id,
            parent_path=[item.id for item in path[:-1]],
            template_code=template.code,
            template_revision=template.revision,
            responsible_user_id=responsible.user_id,
            enabled_modules=enabled,
            planned_modules=planned,
            workspace_permissions=workspace_permissions,
            opened_at=recent.last_opened_at if recent else None,
            last_route=recent.last_route if recent else f"/workspaces/{workspace.id}/home",
        )
        return WorkspaceContextOut(
            active_context=active,
            identity=identity,
            parent=self._reference(path[-2]) if len(path) > 1 else None,
            breadcrumb=breadcrumb,
            template=template,
            responsible=responsible,
            enabled_modules=enabled,
            planned_modules=planned,
            navigator=navigator,
            permissions=dict.fromkeys(workspace_permissions, True),
            allowed_actions=allowed_actions,
            home_configuration=self._home_configuration(workspace.workspace_type_code),
            version=workspace.version,
            etag=etag,
        )

    def _workspace(self, workspace_id: int) -> EnterpriseWorkspace:
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.id == workspace_id,
            )
        )
        if workspace is None:
            self._denied(workspace_id, "WORKSPACE_NOT_FOUND_OR_CROSS_TENANT")
            raise HTTPException(status_code=404, detail="Workspace not found")
        if workspace.workspace_type_code not in SUPPORTED_WORKSPACE_TYPES:
            self._denied(workspace_id, "UNSUPPORTED_WORKSPACE_TYPE")
            raise HTTPException(status_code=422, detail="UNSUPPORTED_WORKSPACE_TYPE")
        if workspace.status not in {"active", "pending", "archived"}:
            self._denied(workspace_id, "WORKSPACE_STATUS_NOT_OPERATIONAL")
            raise HTTPException(status_code=409, detail="WORKSPACE_STATUS_NOT_OPERATIONAL")
        if not self._has_workspace_access(workspace.id):
            self._denied(workspace_id, "WORKSPACE_ACCESS_DENIED")
            raise HTTPException(status_code=403, detail="WORKSPACE_ACCESS_DENIED")
        return workspace

    def _has_workspace_access(self, workspace_id: int) -> bool:
        return self.permission_context.organization_wide or workspace_id in self.permission_context.workspace_ids

    def _path(self, workspace: EnterpriseWorkspace) -> list[EnterpriseWorkspace]:
        path = [workspace]
        seen = {workspace.id}
        current = workspace
        while current.parent_id is not None:
            current = self.db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id == current.parent_id,
                )
            )
            if current is None or current.id in seen:
                raise HTTPException(status_code=409, detail="INVALID_WORKSPACE_HIERARCHY")
            seen.add(current.id)
            path.append(current)
        return list(reversed(path))

    def _identity(self, workspace: EnterpriseWorkspace) -> WorkspaceIdentityOut:
        return WorkspaceIdentityOut(
            tenant_id=self.tenant_id,
            workspace_id=workspace.id,
            workspace_type=workspace.workspace_type_code.upper(),
            workspace_name=workspace.name,
            workspace_status=workspace.status.upper(),
            business_number=self._business_number(workspace),
            record_code=workspace.record_code,
            external_key=workspace.external_key or str(self._metadata(workspace).get("external_key", "")),
        )

    def _reference(self, workspace: EnterpriseWorkspace) -> WorkspaceReferenceOut:
        return WorkspaceReferenceOut(
            workspace_id=workspace.id,
            workspace_type=workspace.workspace_type_code.upper(),
            workspace_name=workspace.name,
            business_number=self._business_number(workspace),
            record_code=workspace.record_code,
            status=workspace.status.upper(),
            navigable=workspace.workspace_type_code in SUPPORTED_WORKSPACE_TYPES and self._has_workspace_access(workspace.id),
        )

    def _responsible(self, workspace: EnterpriseWorkspace) -> WorkspaceResponsibleOut:
        metadata = self._metadata(workspace)
        user_id = metadata.get("project_manager_user_id") or metadata.get("responsible_user_id")
        user = self.db.get(UserAccount, user_id) if user_id else None
        return WorkspaceResponsibleOut(
            user_id=user.id if user else None,
            name=user.full_name if user else str(metadata.get("responsible_name") or ""),
            email=user.email if user else str(metadata.get("responsible_email") or ""),
        )

    def _template(self, workspace: EnterpriseWorkspace) -> WorkspaceTemplateOut:
        metadata = self._metadata(workspace)
        config_id = metadata.get("template_id") or metadata.get("template_config_id")
        configuration = self.db.get(AdminConfiguration, config_id) if config_id else None
        return WorkspaceTemplateOut(
            code=str(metadata.get("template_code") or (configuration.code if configuration else "")),
            revision=metadata.get("template_revision") or (configuration.revision if configuration else None),
            content_hash=str(metadata.get("template_content_hash") or (configuration.content_hash if configuration else "")),
        )

    def _permission_keys(self) -> set[str]:
        group_ids = set(
            self.db.scalars(
                select(SecurityGroupMember.group_id).where(
                    SecurityGroupMember.tenant_id == self.tenant_id,
                    SecurityGroupMember.user_id == self.actor_id,
                )
            ).all()
        )
        assignments = self.db.scalars(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.tenant_id == self.tenant_id,
                SecurityAccessAssignment.status == "active",
                or_(
                    SecurityAccessAssignment.user_id == self.actor_id,
                    SecurityAccessAssignment.group_id.in_(group_ids or {-1}),
                ),
            )
        ).all()
        role_ids = {item.role_id for item in assignments}
        if not role_ids:
            return set()
        return set(
            self.db.scalars(
                select(PermissionCatalog.key)
                .join(SecurityRolePermission, SecurityRolePermission.permission_id == PermissionCatalog.id)
                .where(
                    SecurityRolePermission.tenant_id == self.tenant_id,
                    SecurityRolePermission.role_id.in_(role_ids),
                    PermissionCatalog.status == "active",
                )
            ).all()
        )

    def _home_configuration(self, type_code: str) -> dict:
        profile = self.db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == "workspace_navigation_profile",
                AdminConfiguration.code == type_code,
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
            .limit(1)
        )
        if profile:
            return dict(profile.content_json)
        return {
            "default_home_route": "home",
            "sections": [
                "overview",
                "key_information",
                "status",
                "responsible",
                "recent_activity",
                "recent_documents",
                "my_tasks",
                "related_workspaces",
                "enabled_modules",
                "planned_modules",
            ],
            "show_planned_modules": True,
            "source": "AdminConfiguration-compatible default",
        }

    def _recent(self, workspace_id: int) -> RecentWorkspace | None:
        return self.db.scalar(
            select(RecentWorkspace).where(
                RecentWorkspace.tenant_id == self.tenant_id,
                RecentWorkspace.user_id == self.actor_id,
                RecentWorkspace.workspace_id == workspace_id,
            )
        )

    def _validate_route(
        self,
        workspace: EnterpriseWorkspace,
        navigator: list[WorkspaceNavigatorItemOut],
        route: str,
    ) -> None:
        normalized = route.strip().rstrip("/")
        prefix = f"/workspaces/{workspace.id}"
        if normalized == prefix:
            return
        if not normalized.startswith(f"{prefix}/"):
            raise HTTPException(status_code=422, detail="INVALID_WORKSPACE_ROUTE")
        module_code = normalized[len(prefix) + 1 :].split("/", 1)[0]
        module = next((item for item in navigator if item.code == module_code), None)
        if module is None or module.state != "READY":
            raise HTTPException(status_code=409, detail="WORKSPACE_ROUTE_NOT_OPERATIONAL")

    def _etag(
        self,
        workspace: EnterpriseWorkspace,
        navigator: list[WorkspaceNavigatorItemOut],
        template: WorkspaceTemplateOut,
    ) -> str:
        settings_version = int(
            sum(
                self.db.scalars(
                    select(WorkspaceModuleSetting.version).where(
                        WorkspaceModuleSetting.tenant_id == self.tenant_id,
                        WorkspaceModuleSetting.workspace_id == workspace.id,
                    )
                ).all()
            )
        )
        payload = {
            "tenant_id": self.tenant_id,
            "user_id": self.actor_id,
            "workspace_id": workspace.id,
            "workspace_version": workspace.version,
            "settings_version": settings_version,
            "template": template.model_dump(),
            "navigator": [item.model_dump() for item in navigator],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    def _event(self, event_type: str, workspace: EnterpriseWorkspace, metadata: dict | None = None) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type="workspace",
                target_id=workspace.id,
                metadata_json={"workspace_type": workspace.workspace_type_code, **(metadata or {})},
            )
        )

    def _denied(self, workspace_id: int, reason: str) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type="workspace.context_denied",
                outcome="denied",
                target_type="workspace",
                target_id=workspace_id,
                metadata_json={"reason": reason},
            )
        )
        self.db.commit()

    @staticmethod
    def _metadata(workspace: EnterpriseWorkspace) -> dict:
        defaults = dict(workspace.defaults_json or {})
        return {**defaults, **dict(defaults.get("_enterprise") or {})}

    @classmethod
    def _business_number(cls, workspace: EnterpriseWorkspace) -> str:
        metadata = cls._metadata(workspace)
        return str(metadata.get("business_number") or metadata.get("project_number") or workspace.code)

    @staticmethod
    def _slug(value: str) -> str:
        return "-".join(value.strip().lower().replace("_", "-").split())
