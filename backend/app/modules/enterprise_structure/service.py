"""Application service for the shared enterprise hierarchy and its configuration."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import (
    AdminConfiguration,
    EnterpriseWorkspace,
    SecurityEvent,
    Tenant,
    UserAccount,
)
from app.modules.enterprise_structure.classifications import validate_classification
from app.modules.enterprise_structure.composition_rules import (
    validate_parent_child,
    validate_rule_definition,
)
from app.modules.enterprise_structure.constants import (
    CATEGORY_SEED,
    WORKSPACE_STATUSES,
    WORKSPACE_TYPE_SEED,
)
from app.modules.enterprise_structure.links import validate_workspace_link
from app.modules.enterprise_structure.models import (
    EnterpriseWorkspaceClassification,
    EnterpriseWorkspaceLink,
)
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.enterprise_structure.record_codes import next_record_code
from app.modules.enterprise_structure.repository import EnterpriseStructureRepository
from app.modules.enterprise_structure.schemas import (
    CategoryItem,
    CategoryUpdate,
    ClassificationCreate,
    ClassificationOut,
    CompositionRuleOut,
    CompositionRuleUpdate,
    ConfigurationValidationOut,
    ConfigurationVersionOut,
    CoreReleaseOut,
    EnterpriseExplorerOut,
    EnterpriseNodeCreate,
    EnterpriseNodeDetailOut,
    EnterpriseNodeOut,
    EnterpriseNodeUpdate,
    EnterpriseStructureConfigurationOut,
    EnterpriseTreeNodeOut,
    PublicationOut,
    PublicationRequest,
    WorkspaceLinkCreate,
    WorkspaceLinkOut,
)

SEED_VERSION = "gate-05a-project-workspace-v1.0"


class EnterpriseStructureService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.repository = EnterpriseStructureRepository(db, tenant_id)

    def ensure_seed(self) -> None:
        self._seed_workspace_types()
        self._seed_categories()
        self.db.flush()
        roots = [item for item in self.repository.workspaces() if item.parent_id is None and item.status != "archived"]
        if roots:
            root = roots[0]
            if root.workspace_type_code != "enterprise":
                root.workspace_type_code = "enterprise"
                root.version += 1
                root.updated_at = utc_now()
        else:
            self.db.add(
                EnterpriseWorkspace(
                    tenant_id=self.tenant_id,
                    parent_id=None,
                    workspace_type_code="enterprise",
                    code="enterprise",
                    record_code=self._next_record_code(None),
                    name="Enterprise Workspace",
                    status="active",
                    defaults_json={
                        "currency": "COP",
                        "timezone": "America/Bogota",
                        "locale": "es-CO",
                        "_enterprise": {"description": "Enterprise root"},
                    },
                    sort_order=0,
                    version=1,
                    created_by_user_id=self.actor_id,
                )
            )
        self.db.commit()

    def configuration_overview(self) -> EnterpriseStructureConfigurationOut:
        from app.modules.enterprise_structure.revisions import EnterpriseStructureRevisionService

        types = self.repository.latest_configurations("workspace_type", prefer_draft=True)
        categories = self.repository.latest_configurations("catalog", prefer_draft=True)
        enterprise_categories = [item for item in categories if item.code in CATEGORY_SEED]
        drafts = [
            item
            for item in self.repository.configurations({"workspace_type", "catalog"})
            if item.status == "draft" and (item.kind == "workspace_type" or item.code in CATEGORY_SEED)
        ]
        workspaces = self.repository.workspaces()
        classifications = self.repository.classifications()
        links = self.repository.links()
        draft_release = self.repository.latest_draft_release()
        return EnterpriseStructureConfigurationOut(
            workspace_types=[_configuration_out(item) for item in types],
            categories=[_configuration_out(item) for item in enterprise_categories],
            composition_rules=[self._composition_rule(item) for item in types],
            drafts=[_configuration_out(item) for item in drafts],
            tree=self.build_tree(workspaces),
            classifications=[ClassificationOut.model_validate(item) for item in classifications],
            links=[WorkspaceLinkOut.model_validate(item) for item in links],
            summary={
                "nodes": len(workspaces),
                "active_nodes": sum(item.status == "active" for item in workspaces),
                "types": len(types),
                "categories": len(enterprise_categories),
                "drafts": len(drafts),
                "classifications": len(classifications),
                "links": len(links),
            },
            published_release=self._published_release_out(),
            draft_release=(
                EnterpriseStructureRevisionService(self.db, self.tenant_id, self.actor_id).revision_out(draft_release)
                if draft_release
                else None
            ),
        )

    def create_node(self, payload: EnterpriseNodeCreate) -> EnterpriseNodeOut:
        self._ensure_core_editable()
        type_code = _configuration_code(payload.workspace_type_code)
        node_code = _workspace_code(payload.code)
        if self.repository.workspace_by_code(node_code):
            raise HTTPException(status_code=409, detail="Workspace code already exists")
        workspace_type = self._published_type(type_code)
        self._validate_status(payload.status)
        if payload.valid_from and payload.valid_to and payload.valid_to <= payload.valid_from:
            raise HTTPException(status_code=422, detail="valid_to must be after valid_from")
        parent = None
        if payload.parent_id is None:
            if not workspace_type.content_json.get("can_be_root", False):
                raise HTTPException(status_code=409, detail=f"{type_code} cannot be a root workspace")
            active_enterprise = next(
                (
                    item
                    for item in self.repository.workspaces()
                    if item.parent_id is None and item.workspace_type_code == "enterprise" and item.status != "archived"
                ),
                None,
            )
            if active_enterprise:
                raise HTTPException(status_code=409, detail="Only one active Enterprise root is allowed")
        else:
            parent = self._workspace(payload.parent_id)
            parent_type = self._published_type(parent.workspace_type_code)
            validate_parent_child(parent, type_code, parent_type)
            self._validate_depth(parent, workspace_type)
        workspace = EnterpriseWorkspace(
            tenant_id=self.tenant_id,
            parent_id=parent.id if parent else None,
            workspace_type_code=type_code,
            code=node_code,
            record_code=self._next_record_code(parent),
            name=_required(payload.name, "Workspace name"),
            status=payload.status.strip().lower(),
            defaults_json={"_enterprise": _metadata_from_payload(payload)},
            sort_order=payload.sort_order,
            version=1,
            created_by_user_id=self.actor_id,
        )
        self.db.add(workspace)
        self._commit("Workspace code or hierarchy record code already exists")
        self.db.refresh(workspace)
        self._event("enterprise_structure.node_created", workspace)
        self.db.commit()
        return self.node_out(workspace)

    def update_node(self, workspace_id: int, payload: EnterpriseNodeUpdate) -> EnterpriseNodeOut:
        self._ensure_core_editable()
        workspace = self._workspace(workspace_id)
        self._require_version(workspace, payload.expected_version)
        move_metadata: dict[str, Any] | None = None
        if "parent_id" in payload.model_fields_set and payload.parent_id != workspace.parent_id:
            old_record_code = workspace.record_code
            descendants = self._descendant_workspaces(workspace.id)
            if payload.parent_id is None:
                workspace_type = self._published_type(workspace.workspace_type_code)
                if not workspace_type.content_json.get("can_be_root", False):
                    raise HTTPException(status_code=409, detail=f"{workspace.workspace_type_code} cannot be a root")
                if any(
                    item.id != workspace.id
                    and item.parent_id is None
                    and item.workspace_type_code == "enterprise"
                    and item.status != "archived"
                    for item in self.repository.workspaces()
                ):
                    raise HTTPException(status_code=409, detail="Only one active Enterprise root is allowed")
                new_parent = None
            else:
                parent = self._workspace(payload.parent_id)
                self._ensure_no_cycle(workspace.id, parent.id)
                validate_parent_child(
                    parent, workspace.workspace_type_code, self._published_type(parent.workspace_type_code)
                )
                self._validate_depth(parent, self._published_type(workspace.workspace_type_code))
                new_parent = parent
            new_record_code = self._next_record_code(new_parent, exclude_workspace_id=workspace.id)
            workspace.parent_id = new_parent.id if new_parent else None
            workspace.record_code = new_record_code
            for descendant in descendants:
                if not descendant.record_code.startswith(f"{old_record_code}."):
                    raise HTTPException(status_code=409, detail="Descendant hierarchy code is inconsistent")
                descendant.record_code = f"{new_record_code}{descendant.record_code[len(old_record_code) :]}"
                descendant.version += 1
                descendant.updated_at = utc_now()
            move_metadata = {
                "old_record_code": old_record_code,
                "new_record_code": new_record_code,
                "descendant_count": len(descendants),
            }
        if payload.name is not None:
            workspace.name = _required(payload.name, "Workspace name")
        if payload.status is not None:
            self._validate_status(payload.status)
            if payload.status.strip().lower() == "archived" and self.repository.active_children(workspace.id):
                raise HTTPException(status_code=409, detail="Cannot archive a workspace with active children")
            workspace.status = payload.status.strip().lower()
        if payload.sort_order is not None:
            workspace.sort_order = payload.sort_order
        metadata = dict(_workspace_metadata(workspace))
        for field in (
            "description",
            "organization_unit_id",
            "responsible_user_id",
            "region_code",
            "valid_from",
            "valid_to",
        ):
            if field in payload.model_fields_set:
                value = getattr(payload, field)
                metadata[field] = value.isoformat() if isinstance(value, datetime) else value
        valid_from = _datetime_value(metadata.get("valid_from"))
        valid_to = _datetime_value(metadata.get("valid_to"))
        if valid_from and valid_to and valid_to <= valid_from:
            raise HTTPException(status_code=422, detail="valid_to must be after valid_from")
        defaults = dict(workspace.defaults_json or {})
        defaults["_enterprise"] = metadata
        workspace.defaults_json = defaults
        workspace.version += 1
        workspace.updated_at = utc_now()
        if move_metadata:
            self._event("enterprise_structure.node_moved", workspace, move_metadata)
        self._event("enterprise_structure.node_updated", workspace)
        self.db.commit()
        self.db.refresh(workspace)
        return self.node_out(workspace)

    def archive_node(self, workspace_id: int) -> EnterpriseNodeOut:
        self._ensure_core_editable()
        workspace = self._workspace(workspace_id)
        if self.repository.active_children(workspace.id):
            raise HTTPException(status_code=409, detail="Cannot archive a workspace with active children")
        workspace.status = "archived"
        workspace.version += 1
        workspace.updated_at = utc_now()
        self._event("enterprise_structure.node_archived", workspace)
        self.db.commit()
        self.db.refresh(workspace)
        return self.node_out(workspace)

    def add_classification(self, workspace_id: int, payload: ClassificationCreate) -> ClassificationOut:
        self._ensure_core_editable()
        workspace = self._workspace(workspace_id)
        category_code = _configuration_code(payload.category_set_code)
        item_code = _configuration_code(payload.category_item_code)
        category = self._published_category(category_code)
        validate_classification(workspace, category, item_code)
        record = EnterpriseWorkspaceClassification(
            tenant_id=self.tenant_id,
            workspace_id=workspace.id,
            category_set_code=category_code,
            category_item_code=item_code,
            created_by_user_id=self.actor_id,
        )
        self.db.add(record)
        self._commit("Classification already exists")
        self.db.refresh(record)
        self._event("enterprise_structure.classification_added", record)
        self.db.commit()
        return ClassificationOut.model_validate(record)

    def remove_classification(self, classification_id: int) -> None:
        self._ensure_core_editable()
        record = self.repository.classification(classification_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Classification not found")
        self._event("enterprise_structure.classification_removed", record)
        self.db.delete(record)
        self.db.commit()

    def add_link(self, payload: WorkspaceLinkCreate) -> WorkspaceLinkOut:
        self._ensure_core_editable()
        source = self._workspace(payload.source_workspace_id)
        target = self._workspace(payload.target_workspace_id)
        relationship_type = payload.relationship_type.strip().upper()
        validate_workspace_link(source, target, relationship_type)
        if payload.valid_from and payload.valid_to and payload.valid_to <= payload.valid_from:
            raise HTTPException(status_code=422, detail="valid_to must be after valid_from")
        record = EnterpriseWorkspaceLink(
            tenant_id=self.tenant_id,
            source_workspace_id=source.id,
            target_workspace_id=target.id,
            relationship_type=relationship_type,
            valid_from=payload.valid_from,
            valid_to=payload.valid_to,
            status=payload.status.strip().lower(),
            created_by_user_id=self.actor_id,
        )
        self.db.add(record)
        self._commit("Workspace link already exists")
        self.db.refresh(record)
        self._event("enterprise_structure.link_added", record)
        self.db.commit()
        return WorkspaceLinkOut.model_validate(record)

    def remove_link(self, link_id: int) -> None:
        self._ensure_core_editable()
        record = self.repository.link(link_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Workspace link not found")
        self._event("enterprise_structure.link_removed", record)
        self.db.delete(record)
        self.db.commit()

    def clone_configuration(self, kind: str, code: str) -> ConfigurationVersionOut:
        normalized_code = _configuration_code(code)
        existing_draft = self.repository.latest_configuration(kind, normalized_code, prefer_draft=True)
        if existing_draft and existing_draft.status == "draft":
            return _configuration_out(existing_draft)
        source = self.repository.latest_configuration(kind, normalized_code, published_only=True)
        if source is None:
            raise HTTPException(status_code=404, detail="Published configuration not found")
        clone = self._clone(source)
        self.db.commit()
        self.db.refresh(clone)
        return _configuration_out(clone)

    def update_category(self, configuration_id: int, payload: CategoryUpdate) -> ConfigurationVersionOut:
        record = self._draft_configuration(configuration_id, "catalog")
        if record.code not in CATEGORY_SEED:
            raise HTTPException(status_code=422, detail="Configuration is not an enterprise category")
        known_types = set(WORKSPACE_TYPE_SEED)
        applicable_types = [_configuration_code(item) for item in payload.applicable_types]
        unknown_types = sorted(set(applicable_types) - known_types)
        if unknown_types:
            raise HTTPException(status_code=422, detail=f"Unknown applicable types: {', '.join(unknown_types)}")
        items = [
            {"code": _configuration_code(item.code), "label": _required(item.label, "Item label")}
            for item in payload.items
        ]
        codes = [item["code"] for item in items]
        if len(codes) != len(set(codes)):
            raise HTTPException(status_code=422, detail="Category item codes must be unique")
        record.name = _required(payload.name, "Category name")
        record.description = payload.description.strip()
        record.content_json = {"applicable_types": applicable_types, "items": items, "seed_version": SEED_VERSION}
        record.version += 1
        record.updated_at = utc_now()
        self._event("enterprise_structure.category_updated", record)
        self.db.commit()
        self.db.refresh(record)
        return _configuration_out(record)

    def update_composition_rule(self, parent_type_code: str, payload: CompositionRuleUpdate) -> CompositionRuleOut:
        code = _configuration_code(parent_type_code)
        selected = self.repository.latest_configuration("workspace_type", code, prefer_draft=True)
        if selected is None:
            raise HTTPException(status_code=404, detail="Workspace type not found")
        if selected.status != "draft":
            selected = self._clone(selected)
        content = dict(selected.content_json)
        content.update(
            {
                "allowed_children": [_configuration_code(item) for item in payload.allowed_children],
                "max_depth": payload.max_depth,
                "can_be_root": payload.can_be_root,
                "required_categories": [_configuration_code(item) for item in payload.required_categories],
                "required_fields": [item.strip() for item in payload.required_fields if item.strip()],
                "seed_version": SEED_VERSION,
            }
        )
        issues = validate_rule_definition(code, content, set(WORKSPACE_TYPE_SEED), set(CATEGORY_SEED))
        if issues:
            raise HTTPException(status_code=422, detail=issues)
        selected.content_json = content
        selected.version += 1
        selected.updated_at = utc_now()
        self._event("enterprise_structure.composition_rule_updated", selected)
        self.db.commit()
        self.db.refresh(selected)
        return self._composition_rule(selected)

    def validate_configuration(self, configuration_ids: list[int] | None = None) -> ConfigurationValidationOut:
        selected_types = self.repository.latest_configurations("workspace_type", prefer_draft=True)
        selected_categories = [
            item
            for item in self.repository.latest_configurations("catalog", prefer_draft=True)
            if item.code in CATEGORY_SEED
        ]
        issues: list[str] = []
        warnings: list[str] = []
        type_codes = {item.code for item in selected_types}
        category_codes = {item.code for item in selected_categories}
        missing_types = sorted(set(WORKSPACE_TYPE_SEED) - type_codes)
        if missing_types:
            issues.append(f"Missing workspace types: {', '.join(missing_types)}")
        missing_categories = sorted(set(CATEGORY_SEED) - category_codes)
        if missing_categories:
            issues.append(f"Missing enterprise categories: {', '.join(missing_categories)}")
        for workspace_type in selected_types:
            issues.extend(
                validate_rule_definition(
                    workspace_type.code,
                    workspace_type.content_json,
                    type_codes,
                    category_codes,
                )
            )
        roots = [
            item
            for item in self.repository.workspaces()
            if item.parent_id is None and item.workspace_type_code == "enterprise" and item.status != "archived"
        ]
        if len(roots) != 1:
            issues.append("Exactly one active Enterprise root is required")
        for node in self.repository.workspaces():
            if node.parent_id is None:
                continue
            parent = self.repository.workspace(node.parent_id)
            parent_type = (
                next((item for item in selected_types if item.code == parent.workspace_type_code), None)
                if parent
                else None
            )
            if parent is None:
                issues.append(f"{node.code}: parent does not exist")
            elif parent_type is None or node.workspace_type_code not in parent_type.content_json.get(
                "allowed_children", []
            ):
                issues.append(f"{node.code}: incompatible parent-child composition")
            try:
                self._ensure_no_cycle(node.id, node.parent_id)
            except HTTPException:
                issues.append(f"{node.code}: hierarchy contains a cycle")
        drafts = [
            item
            for item in self.repository.configurations({"workspace_type", "catalog"})
            if item.status == "draft" and (item.kind == "workspace_type" or item.code in CATEGORY_SEED)
        ]
        selected_ids = configuration_ids or [item.id for item in drafts]
        if not selected_ids:
            warnings.append("There are no draft configurations to publish")
        return ConfigurationValidationOut(
            valid=not issues,
            issues=issues,
            warnings=warnings,
            configuration_ids=selected_ids,
        )

    def publish(self, payload: PublicationRequest) -> PublicationOut:
        validation = self.validate_configuration(payload.configuration_ids)
        if not validation.valid:
            raise HTTPException(status_code=409, detail=validation.issues)
        records: list[AdminConfiguration] = []
        for configuration_id in validation.configuration_ids:
            record = self._draft_configuration(configuration_id)
            if record.kind not in {"workspace_type", "catalog"} or (
                record.kind == "catalog" and record.code not in CATEGORY_SEED
            ):
                raise HTTPException(status_code=422, detail=f"Configuration {configuration_id} is outside Nivel 2A")
            observed_hash = _content_hash(record)
            expected_hash = payload.expected_hashes.get(configuration_id, "")
            if expected_hash != observed_hash:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Draft content changed or expected hash was not supplied",
                        "configuration_id": configuration_id,
                        "expected_hash": expected_hash,
                        "observed_hash": observed_hash,
                    },
                )
            records.append(record)
        for record in records:
            record.status = "published"
            record.published_at = utc_now()
            record.content_hash = _content_hash(record)
            record.version += 1
            record.updated_at = utc_now()
            self._event("enterprise_structure.configuration_published", record)
        self.db.commit()
        return PublicationOut(
            **validation.model_dump(),
            published=[_configuration_out(item) for item in records],
        )

    def clone_release(self) -> list[ConfigurationVersionOut]:
        clones: list[AdminConfiguration] = []
        for kind in ("workspace_type", "catalog"):
            for source in self.repository.latest_configurations(kind, published_only=True):
                if kind == "catalog" and source.code not in CATEGORY_SEED:
                    continue
                selected = self.repository.latest_configuration(kind, source.code, prefer_draft=True)
                if selected and selected.status == "draft":
                    clones.append(selected)
                else:
                    clones.append(self._clone(source))
        self.db.commit()
        return [_configuration_out(item) for item in clones]

    def explorer(
        self,
        context: EnterprisePermissionContext,
        *,
        search: str = "",
        workspace_type: str = "",
        business_unit_id: int | None = None,
        strategic_objective: str = "",
        region: str = "",
        status: str = "",
    ) -> EnterpriseExplorerOut:
        all_nodes = self._authorized_nodes(context)
        node_ids = {item.id for item in all_nodes}
        classifications = [item for item in self.repository.classifications() if item.workspace_id in node_ids]
        links = [
            item
            for item in self.repository.links()
            if item.source_workspace_id in node_ids and item.target_workspace_id in node_ids
        ]
        matched = list(all_nodes)
        if search.strip():
            term = search.strip().lower()
            matched = [item for item in matched if term in item.code.lower() or term in item.name.lower()]
        if workspace_type.strip():
            normalized_type = _configuration_code(workspace_type)
            matched = [item for item in matched if item.workspace_type_code == normalized_type]
        if business_unit_id is not None:
            allowed_descendants = self._descendant_ids(business_unit_id, all_nodes)
            matched = [item for item in matched if item.id in allowed_descendants]
        if strategic_objective.strip():
            objective = _configuration_code(strategic_objective)
            classified_ids = {
                item.workspace_id
                for item in classifications
                if item.category_set_code == "strategic-objective" and item.category_item_code == objective
            }
            matched = [item for item in matched if item.id in classified_ids]
        if region.strip():
            region_code = region.strip().lower()
            matched = [item for item in matched if self.node_out(item).region_code.lower() == region_code]
        if status.strip():
            normalized_status = status.strip().lower()
            matched = [item for item in matched if item.status == normalized_status]
        visible_ids = {item.id for item in matched}
        parent_map = {item.id: item.parent_id for item in all_nodes}
        for node_id in list(visible_ids):
            parent_id = parent_map.get(node_id)
            while parent_id is not None and parent_id in node_ids:
                visible_ids.add(parent_id)
                parent_id = parent_map.get(parent_id)
        tree_nodes = [item for item in all_nodes if item.id in visible_ids]
        types = self.repository.latest_configurations("workspace_type", published_only=True)
        objectives = self.strategic_objective_items()
        return EnterpriseExplorerOut(
            tree=self.build_tree(tree_nodes),
            nodes=[self.node_out(item) for item in matched],
            workspace_types=[_configuration_out(item) for item in types],
            objectives=objectives,
            classifications=[ClassificationOut.model_validate(item) for item in classifications],
            links=[WorkspaceLinkOut.model_validate(item) for item in links],
            summary={
                "nodes": len(matched),
                "active": sum(item.status == "active" for item in matched),
                "properties": sum(item.workspace_type_code == "property" for item in matched),
                "facilities": sum(item.workspace_type_code == "facility" for item in matched),
                "projects": sum(item.workspace_type_code == "project" for item in matched),
            },
            published_release=self._published_release_out(),
        )

    def node_detail(self, context: EnterprisePermissionContext, workspace_id: int) -> EnterpriseNodeDetailOut:
        workspace = self._workspace(workspace_id)
        authorized = {item.id for item in self._authorized_nodes(context)}
        if workspace.id not in authorized:
            raise HTTPException(status_code=404, detail="Workspace not found")
        path = self.workspace_path(workspace)
        return EnterpriseNodeDetailOut(
            node=self.node_out(workspace),
            path=[self.node_out(item) for item in path if item.id in authorized],
            classifications=[
                ClassificationOut.model_validate(item) for item in self.repository.classifications(workspace.id)
            ],
            links=[WorkspaceLinkOut.model_validate(item) for item in self.repository.links(workspace.id)],
        )

    def workspace_path(self, workspace: EnterpriseWorkspace) -> list[EnterpriseWorkspace]:
        path = [workspace]
        visited = {workspace.id}
        current = workspace
        while current.parent_id is not None:
            current = self._workspace(current.parent_id)
            if current.id in visited:
                raise HTTPException(status_code=409, detail="Workspace hierarchy contains a cycle")
            visited.add(current.id)
            path.append(current)
        path.reverse()
        return path

    def build_tree(self, workspaces: list[EnterpriseWorkspace]) -> list[EnterpriseTreeNodeOut]:
        included_ids = {item.id for item in workspaces}
        children: dict[int | None, list[EnterpriseWorkspace]] = {}
        for workspace in workspaces:
            parent_key = workspace.parent_id if workspace.parent_id in included_ids else None
            children.setdefault(parent_key, []).append(workspace)

        def build(parent_id: int | None) -> list[EnterpriseTreeNodeOut]:
            rows = sorted(children.get(parent_id, []), key=lambda item: (item.sort_order, item.name.lower()))
            return [EnterpriseTreeNodeOut(**self.node_out(item).model_dump(), children=build(item.id)) for item in rows]

        return build(None)

    def node_out(self, workspace: EnterpriseWorkspace) -> EnterpriseNodeOut:
        metadata = _workspace_metadata(workspace)
        return EnterpriseNodeOut(
            id=workspace.id,
            parent_id=workspace.parent_id,
            workspace_type_code=workspace.workspace_type_code,
            code=workspace.code,
            external_key=workspace.external_key or str(metadata.get("external_key") or "") or None,
            record_code=workspace.record_code,
            depth=len(self.workspace_path(workspace)) - 1,
            name=workspace.name,
            description=str(metadata.get("description") or ""),
            organization_unit_id=_optional_int(metadata.get("organization_unit_id")),
            responsible_user_id=_optional_int(metadata.get("responsible_user_id")),
            region_code=str(metadata.get("region_code") or ""),
            valid_from=_datetime_value(metadata.get("valid_from")),
            valid_to=_datetime_value(metadata.get("valid_to")),
            status=workspace.status,
            sort_order=workspace.sort_order,
            version=workspace.version,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
        )

    def strategic_objective_items(self) -> list[CategoryItem]:
        objectives = self.repository.strategic_objectives(active_only=True)
        if objectives:
            return [CategoryItem(code=item.code, label=item.name) for item in objectives]
        category = self._published_category("strategic-objective")
        return [CategoryItem.model_validate(item) for item in category.content_json.get("items", [])]

    def _seed_workspace_types(self) -> None:
        for code, definition in WORKSPACE_TYPE_SEED.items():
            latest = self.repository.latest_configuration("workspace_type", code, prefer_draft=True)
            content = {
                "allowed_children": definition["allowed_children"],
                "max_depth": None,
                "can_be_root": definition["can_be_root"],
                "required_categories": definition["required_categories"],
                "required_fields": definition["required_fields"],
                "required_defaults": ["currency", "timezone"],
                "seed_version": SEED_VERSION,
                **{
                    key: value
                    for key, value in definition.items()
                    if key
                    not in {
                        "name",
                        "description",
                        "allowed_children",
                        "can_be_root",
                        "required_categories",
                        "required_fields",
                    }
                },
            }
            if latest is not None and latest.status == "draft":
                continue
            if latest is not None:
                current = {key: value for key, value in latest.content_json.items() if key != "seed_version"}
                desired = {key: value for key, value in content.items() if key != "seed_version"}
                if current == desired:
                    continue
            revision = self._next_revision("workspace_type", code)
            record = self._add_published_configuration(
                "workspace_type",
                code,
                definition["name"],
                definition["description"],
                content,
                revision,
            )
            if code == "project":
                self.db.flush()
                self._event(
                    "enterprise_structure.project_type.configured",
                    record,
                    {"seed_version": SEED_VERSION, "allowed_parent_types": ["portfolio", "program"]},
                )

    def _seed_categories(self) -> None:
        for code, definition in CATEGORY_SEED.items():
            if self.repository.latest_configuration("catalog", code, prefer_draft=True):
                continue
            content = {
                "applicable_types": definition["applicable_types"],
                "items": definition["items"],
                "seed_version": SEED_VERSION,
            }
            self._add_published_configuration(
                "catalog",
                code,
                definition["name"],
                definition["description"],
                content,
                1,
            )

    def _add_published_configuration(
        self,
        kind: str,
        code: str,
        name: str,
        description: str,
        content: dict[str, Any],
        revision: int,
    ) -> AdminConfiguration:
        record = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=kind,
            code=code,
            name=name,
            description=description,
            status="published",
            revision=revision,
            version=1,
            content_json=content,
            published_at=utc_now(),
            created_by_user_id=self.actor_id,
        )
        record.content_hash = _content_hash(record)
        self.db.add(record)
        return record

    def _next_revision(self, kind: str, code: str) -> int:
        maximum = self.db.scalar(
            select(func.max(AdminConfiguration.revision)).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == kind,
                AdminConfiguration.code == code,
            )
        )
        return int(maximum or 0) + 1

    def _clone(self, source: AdminConfiguration) -> AdminConfiguration:
        clone = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=source.kind,
            code=source.code,
            name=source.name,
            description=source.description,
            status="draft",
            revision=self._next_revision(source.kind, source.code),
            version=1,
            content_json=json.loads(json.dumps(source.content_json)),
            created_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._event("enterprise_structure.configuration_cloned", clone, {"source_id": source.id})
        return clone

    def _composition_rule(self, configuration: AdminConfiguration) -> CompositionRuleOut:
        content = configuration.content_json
        return CompositionRuleOut(
            parent_type_code=configuration.code,
            parent_type_name=configuration.name,
            configuration_id=configuration.id,
            revision=configuration.revision,
            status=configuration.status,
            allowed_children=list(content.get("allowed_children", [])),
            max_depth=content.get("max_depth"),
            can_be_root=bool(content.get("can_be_root", False)),
            required_categories=list(content.get("required_categories", [])),
            required_fields=list(content.get("required_fields", [])),
        )

    def _published_type(self, code: str) -> AdminConfiguration:
        record = self.repository.latest_configuration("workspace_type", code, published_only=True)
        if record is None:
            raise HTTPException(status_code=409, detail=f"Published workspace type not found: {code}")
        return record

    def _published_category(self, code: str) -> AdminConfiguration:
        record = self.repository.latest_configuration("catalog", code, published_only=True)
        if record is None or code not in CATEGORY_SEED:
            raise HTTPException(status_code=409, detail=f"Published enterprise category not found: {code}")
        return record

    def _draft_configuration(self, configuration_id: int, expected_kind: str | None = None) -> AdminConfiguration:
        record = self.repository.configuration(configuration_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Configuration not found")
        if record.status != "draft":
            raise HTTPException(
                status_code=409, detail="Published configuration is immutable; clone it to create a draft"
            )
        if expected_kind and record.kind != expected_kind:
            raise HTTPException(status_code=422, detail=f"Expected {expected_kind} configuration")
        return record

    def _workspace(self, workspace_id: int) -> EnterpriseWorkspace:
        workspace = self.repository.workspace(workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return workspace

    def _published_release_out(self) -> CoreReleaseOut | None:
        release = self.repository.latest_core_release()
        if release is None:
            return None
        actor_email = self.db.scalar(select(UserAccount.email).where(UserAccount.id == release.published_by_user_id))
        return CoreReleaseOut(
            id=release.id,
            release_code=release.release_code,
            release_name=release.release_name,
            revision_number=release.revision_number,
            revision_version=release.revision_version,
            state=release.state,
            previous_release_id=release.previous_release_id,
            source_hash=release.source_hash,
            canonical_hash=release.canonical_hash,
            content_fingerprint=release.content_fingerprint,
            workspace_count=release.workspace_count,
            objective_count=release.objective_count,
            classification_count=release.classification_count,
            link_count=release.link_count,
            published_at=release.published_at,
            published_by=actor_email,
        )

    def _ensure_core_editable(self) -> None:
        release = self.repository.latest_core_release()
        if release is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "The published CORE release is immutable; create an approved new revision before editing",
                    "release_code": release.release_code,
                },
            )

    def _ensure_no_cycle(self, workspace_id: int, parent_id: int) -> None:
        current_id: int | None = parent_id
        visited: set[int] = set()
        while current_id is not None:
            if current_id == workspace_id:
                raise HTTPException(status_code=409, detail="Workspace hierarchy cannot contain cycles")
            if current_id in visited:
                raise HTTPException(status_code=409, detail="Workspace hierarchy contains an existing cycle")
            visited.add(current_id)
            current_id = self._workspace(current_id).parent_id

    def _validate_depth(self, parent: EnterpriseWorkspace, child_type: AdminConfiguration) -> None:
        max_depth = child_type.content_json.get("max_depth")
        if max_depth is not None and len(self.workspace_path(parent)) + 1 > int(max_depth):
            raise HTTPException(status_code=409, detail=f"Maximum depth exceeded for {child_type.code}")

    def _validate_status(self, status: str) -> None:
        normalized = status.strip().lower()
        if normalized not in WORKSPACE_STATUSES:
            raise HTTPException(status_code=422, detail=f"Unsupported workspace status: {status}")

    def _require_version(self, workspace: EnterpriseWorkspace, expected_version: int | None) -> None:
        if expected_version is not None and workspace.version != expected_version:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Record was updated by another user. Refresh before retrying.",
                    "current_version": workspace.version,
                    "expected_version": expected_version,
                },
            )

    def _authorized_nodes(self, context: EnterprisePermissionContext) -> list[EnterpriseWorkspace]:
        nodes = self.repository.workspaces()
        if context.organization_wide:
            return nodes
        visible_ids = {
            item.id
            for item in nodes
            if self.node_out(item).organization_unit_id in context.scope_unit_ids or item.id in context.workspace_ids
        }
        by_id = {item.id: item for item in nodes}
        for node_id in list(visible_ids):
            parent_id = by_id[node_id].parent_id
            while parent_id is not None and parent_id in by_id:
                visible_ids.add(parent_id)
                parent_id = by_id[parent_id].parent_id
        return [item for item in nodes if item.id in visible_ids]

    def _descendant_ids(self, root_id: int, nodes: list[EnterpriseWorkspace]) -> set[int]:
        by_parent: dict[int | None, list[int]] = {}
        for item in nodes:
            by_parent.setdefault(item.parent_id, []).append(item.id)
        descendants: set[int] = set()
        pending = [root_id]
        while pending:
            current = pending.pop()
            if current in descendants:
                continue
            descendants.add(current)
            pending.extend(by_parent.get(current, []))
        return descendants

    def _descendant_workspaces(self, root_id: int) -> list[EnterpriseWorkspace]:
        nodes = self.repository.workspaces()
        descendant_ids = self._descendant_ids(root_id, nodes) - {root_id}
        return [item for item in nodes if item.id in descendant_ids]

    def _next_record_code(
        self,
        parent: EnterpriseWorkspace | None,
        *,
        exclude_workspace_id: int | None = None,
    ) -> str:
        if parent is None:
            self.db.execute(select(Tenant.id).where(Tenant.id == self.tenant_id).with_for_update()).scalar_one()
            statement = select(EnterpriseWorkspace.record_code).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.parent_id.is_(None),
            )
            parent_code = None
        else:
            locked_parent = self.db.execute(
                select(EnterpriseWorkspace)
                .where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id == parent.id,
                )
                .with_for_update()
            ).scalar_one()
            statement = select(EnterpriseWorkspace.record_code).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.parent_id == locked_parent.id,
            )
            parent_code = locked_parent.record_code
        if exclude_workspace_id is not None:
            statement = statement.where(EnterpriseWorkspace.id != exclude_workspace_id)
        sibling_codes = self.db.scalars(statement).all()
        return next_record_code(parent_code, sibling_codes)

    def _event(self, event_type: str, target: object, metadata: dict[str, Any] | None = None) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type=target.__class__.__name__,
                target_id=getattr(target, "id", None),
                metadata_json=metadata or {},
            )
        )

    def _commit(self, conflict_message: str) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(status_code=409, detail=conflict_message) from exc


def _workspace_metadata(workspace: EnterpriseWorkspace) -> dict[str, Any]:
    defaults = workspace.defaults_json or {}
    metadata = defaults.get("_enterprise", {})
    return metadata if isinstance(metadata, dict) else {}


def _metadata_from_payload(payload: EnterpriseNodeCreate) -> dict[str, Any]:
    return {
        "description": payload.description.strip(),
        "organization_unit_id": payload.organization_unit_id,
        "responsible_user_id": payload.responsible_user_id,
        "region_code": payload.region_code.strip(),
        "valid_from": payload.valid_from.isoformat() if payload.valid_from else None,
        "valid_to": payload.valid_to.isoformat() if payload.valid_to else None,
    }


def _datetime_value(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _configuration_code(value: str) -> str:
    code = value.strip().lower().replace("_", "-").replace(" ", "-")
    if not code:
        raise HTTPException(status_code=422, detail="Code is required")
    return code


def _workspace_code(value: str) -> str:
    code = value.strip().upper().replace(" ", "-")
    if not code:
        raise HTTPException(status_code=422, detail="Workspace code is required")
    return code


def _required(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail=f"{label} is required")
    return normalized


def _content_hash(record: AdminConfiguration) -> str:
    payload = {
        "kind": record.kind,
        "code": record.code,
        "revision": record.revision,
        "name": record.name,
        "description": record.description,
        "content": record.content_json,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _configuration_out(record: AdminConfiguration) -> ConfigurationVersionOut:
    output = ConfigurationVersionOut.model_validate(record)
    if record.status == "draft":
        return output.model_copy(update={"content_hash": _content_hash(record)})
    return output
