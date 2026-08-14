"""Backend-derived Workspace Navigator.

The profile defines ordering only. Operational truth still comes from the
Workspace snapshot, WorkspaceModuleSetting, published Module Definitions,
status, RBAC and access resolved by the caller.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import AdminConfiguration, EnterpriseWorkspace, WorkspaceModuleSetting
from app.modules.workspace_context.schemas import WorkspaceNavigatorItemOut

SUPPORTED_WORKSPACE_TYPES = frozenset(
    {"enterprise", "business-unit", "portfolio", "project", "property", "facility", "warehouse"}
)


@dataclass(frozen=True)
class NavigationDefinition:
    code: str
    label: str
    default_state: str = "READY"
    definition_code: str = ""
    permission_key: str = ""


DEFAULT_PROFILES: dict[str, tuple[NavigationDefinition, ...]] = {
    "enterprise": (
        NavigationDefinition("home", "Home"),
        NavigationDefinition("overview", "Overview"),
        NavigationDefinition("ideas", "Ideas", permission_key="idea.read"),
    ),
    "business-unit": (
        NavigationDefinition("home", "Home"),
        NavigationDefinition("overview", "Overview"),
        NavigationDefinition("ideas", "Ideas", permission_key="idea.read"),
    ),
    "portfolio": (
        NavigationDefinition("home", "Home"),
        NavigationDefinition("overview", "Overview"),
        NavigationDefinition("ideas", "Ideas", permission_key="idea.read"),
    ),
    "project": (
        NavigationDefinition("home", "Home"),
        NavigationDefinition("overview", "Overview"),
        NavigationDefinition("scope", "Scope", definition_code="scope-manager"),
        NavigationDefinition("schedule", "Schedule", definition_code="schedule-manager"),
        NavigationDefinition("cost", "Cost", definition_code="cost-manager"),
        NavigationDefinition("documents", "Documents"),
        NavigationDefinition("reports", "Reports"),
    ),
    "property": (
        NavigationDefinition("home", "Home"),
        NavigationDefinition("overview", "Overview"),
        NavigationDefinition("real-estate-information", "Real Estate Information"),
        NavigationDefinition("documents", "Documents"),
        NavigationDefinition("related-workspaces", "Related Workspaces"),
    ),
    "facility": (
        NavigationDefinition("home", "Home"),
        NavigationDefinition("overview", "Overview"),
        NavigationDefinition("documents", "Documents"),
        NavigationDefinition("asset-manager", "Asset Manager", "PLANNED"),
        NavigationDefinition("maintenance", "Maintenance", "PLANNED"),
        NavigationDefinition("space", "Space", "PLANNED"),
        NavigationDefinition("utilities", "Utilities", "PLANNED"),
    ),
    "warehouse": (
        NavigationDefinition("home", "Home"),
        NavigationDefinition("overview", "Overview"),
        NavigationDefinition("documents", "Documents"),
        NavigationDefinition("inventory", "Inventory", "PLANNED"),
        NavigationDefinition("receipts", "Receipts", "PLANNED"),
        NavigationDefinition("issues", "Issues", "PLANNED"),
        NavigationDefinition("transfers", "Transfers", "PLANNED"),
    ),
}


class WorkspaceNavigatorService:
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    def resolve(
        self,
        workspace: EnterpriseWorkspace,
        *,
        user_permissions: set[str],
    ) -> tuple[list[WorkspaceNavigatorItemOut], list[str], list[str]]:
        metadata = self._metadata(workspace)
        definitions = self._module_definitions()
        settings = {
            row.module_key: row.enabled
            for row in self.db.scalars(
                select(WorkspaceModuleSetting).where(
                    WorkspaceModuleSetting.tenant_id == self.tenant_id,
                    WorkspaceModuleSetting.workspace_id == workspace.id,
                )
            ).all()
        }
        enabled = {str(code) for code in metadata.get("enabled_modules", []) if str(code)}
        if workspace.workspace_type_code == "project" and not enabled and not settings:
            enabled = {code for code in ("scope-manager", "schedule-manager", "cost-manager") if code in definitions}
        enabled.update(code for code, value in settings.items() if value)
        enabled.difference_update(code for code, value in settings.items() if not value)

        planned = {self._slug(str(code)) for code in metadata.get("planned_modules", []) if str(code)}
        profile, show_planned = self._profile(workspace.workspace_type_code)
        items: list[WorkspaceNavigatorItemOut] = []
        for item in profile:
            definition = definitions.get(item.definition_code) if item.definition_code else None
            state = item.default_state
            permission_key = item.permission_key
            reason = ""
            if item.definition_code:
                if item.definition_code not in enabled or definition is None:
                    state = "DISABLED"
                    reason = "Module is not enabled for this Workspace"
                elif definition is not None:
                    permission_key = str(definition.content_json.get("permission_key", ""))
            if item.default_state == "PLANNED":
                state = "PLANNED"
                planned.add(item.code)
                reason = "Planned capability; no operational Module Definition exists"
            if workspace.status in {"pending", "draft", "inactive"} and item.code not in {"home", "overview"}:
                state = "HIDDEN"
                reason = "Operational modules require an ACTIVE Workspace"
            if permission_key and permission_key not in user_permissions:
                state = "HIDDEN"
                reason = "Module permission is not granted"
            if state in {"DISABLED", "HIDDEN"} or (state == "PLANNED" and not show_planned):
                continue
            items.append(
                WorkspaceNavigatorItemOut(
                    code=item.code,
                    label=item.label,
                    route=f"/workspaces/{workspace.id}/{item.code}",
                    state=state,
                    permission_key=permission_key,
                    read_only=workspace.status == "archived",
                    reason=reason,
                )
            )
        return items, sorted(enabled), sorted(planned)

    def _profile(self, type_code: str) -> tuple[tuple[NavigationDefinition, ...], bool]:
        profile = DEFAULT_PROFILES[type_code]
        configuration = self.db.scalar(
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
        if configuration is None:
            return profile, True
        order = [self._slug(str(item)) for item in configuration.content_json.get("module_order", [])]
        by_code = {item.code: item for item in profile}
        ordered = [by_code.pop(code) for code in order if code in by_code]
        ordered.extend(item for item in profile if item.code in by_code)
        return tuple(ordered), bool(configuration.content_json.get("show_planned_modules", True))

    def _module_definitions(self) -> dict[str, AdminConfiguration]:
        rows = self.db.scalars(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == "module_definition",
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
        ).all()
        result: dict[str, AdminConfiguration] = {}
        for row in rows:
            result.setdefault(row.code, row)
        return result

    @staticmethod
    def _metadata(workspace: EnterpriseWorkspace) -> dict:
        defaults = dict(workspace.defaults_json or {})
        enterprise = dict(defaults.get("_enterprise") or {})
        return {**defaults, **enterprise}

    @staticmethod
    def _slug(value: str) -> str:
        return "-".join(value.strip().lower().replace("_", "-").split())
