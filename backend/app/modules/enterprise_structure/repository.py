"""Tenant-scoped persistence queries for Enterprise Structure."""

from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.models import AdminConfiguration, EnterpriseWorkspace
from app.modules.enterprise_structure.models import (
    EnterpriseCoreRelease,
    EnterpriseStrategicObjective,
    EnterpriseWorkspaceClassification,
    EnterpriseWorkspaceLink,
)


class EnterpriseStructureRepository:
    def __init__(self, db: Session, tenant_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id

    def configurations(self, kinds: Iterable[str] | None = None) -> list[AdminConfiguration]:
        statement = select(AdminConfiguration).where(AdminConfiguration.tenant_id == self.tenant_id)
        if kinds:
            statement = statement.where(AdminConfiguration.kind.in_(set(kinds)))
        return list(
            self.db.scalars(
                statement.order_by(
                    AdminConfiguration.kind,
                    AdminConfiguration.code,
                    AdminConfiguration.revision.desc(),
                )
            ).all()
        )

    def latest_configurations(
        self,
        kind: str,
        *,
        prefer_draft: bool = False,
        published_only: bool = False,
    ) -> list[AdminConfiguration]:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == kind,
        )
        if published_only:
            statement = statement.where(AdminConfiguration.status == "published")
        rows = list(
            self.db.scalars(statement.order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())).all()
        )
        selected: dict[str, AdminConfiguration] = {}
        for row in rows:
            current = selected.get(row.code)
            if current is None:
                selected[row.code] = row
            elif prefer_draft and row.status == "draft" and current.status != "draft":
                selected[row.code] = row
        return sorted(selected.values(), key=lambda item: item.name.lower())

    def latest_configuration(
        self,
        kind: str,
        code: str,
        *,
        prefer_draft: bool = False,
        published_only: bool = False,
    ) -> AdminConfiguration | None:
        rows = self.latest_configurations(kind, prefer_draft=prefer_draft, published_only=published_only)
        return next((item for item in rows if item.code == code), None)

    def configuration(self, configuration_id: int) -> AdminConfiguration | None:
        return self.db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.id == configuration_id,
            )
        )

    def latest_core_release(self) -> EnterpriseCoreRelease | None:
        return self.db.scalar(
            select(EnterpriseCoreRelease)
            .where(
                EnterpriseCoreRelease.tenant_id == self.tenant_id,
                EnterpriseCoreRelease.state == "published",
            )
            .order_by(EnterpriseCoreRelease.published_at.desc(), EnterpriseCoreRelease.id.desc())
            .limit(1)
        )

    def core_release(self, release_id: int) -> EnterpriseCoreRelease | None:
        return self.db.scalar(
            select(EnterpriseCoreRelease).where(
                EnterpriseCoreRelease.tenant_id == self.tenant_id,
                EnterpriseCoreRelease.id == release_id,
            )
        )

    def latest_draft_release(self) -> EnterpriseCoreRelease | None:
        return self.db.scalar(
            select(EnterpriseCoreRelease)
            .where(
                EnterpriseCoreRelease.tenant_id == self.tenant_id,
                EnterpriseCoreRelease.state == "draft",
            )
            .order_by(EnterpriseCoreRelease.created_at.desc(), EnterpriseCoreRelease.id.desc())
            .limit(1)
        )

    def release_count(self) -> int:
        return len(
            self.db.scalars(
                select(EnterpriseCoreRelease.id).where(EnterpriseCoreRelease.tenant_id == self.tenant_id)
            ).all()
        )

    def workspaces(self) -> list[EnterpriseWorkspace]:
        return list(
            self.db.scalars(
                select(EnterpriseWorkspace)
                .where(EnterpriseWorkspace.tenant_id == self.tenant_id)
                .order_by(EnterpriseWorkspace.sort_order, EnterpriseWorkspace.name)
            ).all()
        )

    def workspace(self, workspace_id: int) -> EnterpriseWorkspace | None:
        return self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.id == workspace_id,
            )
        )

    def workspace_by_code(self, code: str) -> EnterpriseWorkspace | None:
        return self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.code == code,
            )
        )

    def strategic_objectives(self, *, active_only: bool = False) -> list[EnterpriseStrategicObjective]:
        statement = select(EnterpriseStrategicObjective).where(EnterpriseStrategicObjective.tenant_id == self.tenant_id)
        if active_only:
            statement = statement.where(EnterpriseStrategicObjective.active.is_(True))
        return list(self.db.scalars(statement.order_by(EnterpriseStrategicObjective.code)).all())

    def active_children(self, workspace_id: int) -> list[EnterpriseWorkspace]:
        return list(
            self.db.scalars(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.parent_id == workspace_id,
                    EnterpriseWorkspace.status != "archived",
                )
            ).all()
        )

    def classifications(self, workspace_id: int | None = None) -> list[EnterpriseWorkspaceClassification]:
        statement = select(EnterpriseWorkspaceClassification).where(
            EnterpriseWorkspaceClassification.tenant_id == self.tenant_id
        )
        if workspace_id is not None:
            statement = statement.where(EnterpriseWorkspaceClassification.workspace_id == workspace_id)
        return list(
            self.db.scalars(
                statement.order_by(
                    EnterpriseWorkspaceClassification.category_set_code,
                    EnterpriseWorkspaceClassification.category_item_code,
                )
            ).all()
        )

    def classification(self, classification_id: int) -> EnterpriseWorkspaceClassification | None:
        return self.db.scalar(
            select(EnterpriseWorkspaceClassification).where(
                EnterpriseWorkspaceClassification.tenant_id == self.tenant_id,
                EnterpriseWorkspaceClassification.id == classification_id,
            )
        )

    def links(self, workspace_id: int | None = None) -> list[EnterpriseWorkspaceLink]:
        statement = select(EnterpriseWorkspaceLink).where(EnterpriseWorkspaceLink.tenant_id == self.tenant_id)
        if workspace_id is not None:
            statement = statement.where(
                or_(
                    EnterpriseWorkspaceLink.source_workspace_id == workspace_id,
                    EnterpriseWorkspaceLink.target_workspace_id == workspace_id,
                )
            )
        return list(self.db.scalars(statement.order_by(EnterpriseWorkspaceLink.relationship_type)).all())

    def link(self, link_id: int) -> EnterpriseWorkspaceLink | None:
        return self.db.scalar(
            select(EnterpriseWorkspaceLink).where(
                EnterpriseWorkspaceLink.tenant_id == self.tenant_id,
                EnterpriseWorkspaceLink.id == link_id,
            )
        )
