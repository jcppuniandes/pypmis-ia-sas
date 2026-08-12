"""Versioned tenant configuration for P&Pmis ADMIN MODE.

The first delivery keeps configuration generic at the persistence boundary and
typed at the API boundary. This lets new catalogs and declarative processes be
added without replacing the existing organization/security foundation.
"""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.api.v1._helpers import require_current_version, require_tenant_configurator, touch_collaborative_record
from app.core.time import utc_now
from app.database.session import get_db
from app.domain.models import (
    AdminConfiguration,
    AdminNumberSequence,
    EnterpriseWorkspace,
    SecurityEvent,
    WorkspaceModuleSetting,
)
from app.domain.schemas import (
    AdminConfigurationCreate,
    AdminConfigurationOut,
    AdminConfigurationOverviewOut,
    AdminConfigurationUpdate,
    EnterpriseWorkspaceCreate,
    EnterpriseWorkspaceOut,
    EnterpriseWorkspaceUpdate,
    NumberingRequest,
    NumberingResultOut,
    WorkspaceDefaultsUpdate,
    WorkspaceEffectiveConfigurationOut,
    WorkspaceModuleSettingOut,
    WorkspaceModuleSettingUpdate,
)
from app.modules.enterprise_structure.record_codes import next_record_code

router = APIRouter(prefix="/admin-configuration")

CONFIGURATION_KINDS = {
    "workspace_type",
    "module_definition",
    "catalog",
    "numbering_rule",
    "process_definition",
}

CONFIGURATION_SEED = (
    (
        "workspace_type",
        "portfolio",
        "Portfolio",
        "Agrupa programas y proyectos bajo objetivos de inversión comunes.",
        {"allowed_children": ["program", "project"], "required_defaults": ["currency", "timezone"]},
    ),
    (
        "workspace_type",
        "program",
        "Program",
        "Coordina proyectos relacionados y hereda políticas del portafolio.",
        {"allowed_children": ["project"], "required_defaults": ["currency", "timezone"]},
    ),
    (
        "workspace_type",
        "project",
        "Project",
        "Espacio operativo para ejecutar los módulos de USER MODE.",
        {"allowed_children": [], "required_defaults": ["currency", "timezone"]},
    ),
    (
        "module_definition",
        "scope-manager",
        "Scope Manager",
        "Gobierno de alcance BIM y cantidades.",
        {"dependencies": [], "mode": "hybrid"},
    ),
    (
        "module_definition",
        "schedule-manager",
        "Schedule Manager",
        "Planificación y control de cronograma.",
        {"dependencies": [], "mode": "hybrid"},
    ),
    (
        "module_definition",
        "cost-manager",
        "Cost Manager",
        "Control presupuestal y de costos.",
        {"dependencies": ["scope-manager"], "mode": "hybrid"},
    ),
    (
        "catalog",
        "workspace-status",
        "Workspace Status",
        "Estados maestros permitidos para la estructura empresarial.",
        {"items": [{"code": "active", "label": "Active"}, {"code": "inactive", "label": "Inactive"}]},
    ),
    (
        "numbering_rule",
        "workspace",
        "Workspace Numbering",
        "Numeración empresarial por tenant.",
        {"pattern": "{prefix}-{sequence:04d}", "prefix": "WS", "start": 1},
    ),
    (
        "process_definition",
        "configuration-release",
        "Configuration Release",
        "Flujo declarativo para revisión y publicación de configuración.",
        {
            "form": {"fields": [{"key": "release_notes", "type": "textarea", "required": True}]},
            "states": ["draft", "in_review", "published"],
            "transitions": [
                {"from": "draft", "to": "in_review", "permission": "admin.process_definition.manage"},
                {"from": "in_review", "to": "published", "permission": "admin.process_definition.publish"},
            ],
        },
    ),
)


@router.get("/overview", response_model=AdminConfigurationOverviewOut)
def overview(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOverviewOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    _ensure_seed(db, tenant_id, actor.id)
    db.commit()
    configurations = _configurations(db, tenant_id)
    workspaces = _workspaces(db, tenant_id)
    settings = _module_settings(db, tenant_id)
    return AdminConfigurationOverviewOut(
        configurations=[AdminConfigurationOut.model_validate(item) for item in configurations],
        workspaces=[EnterpriseWorkspaceOut.model_validate(item) for item in workspaces],
        module_settings=[WorkspaceModuleSettingOut.model_validate(item) for item in settings],
        summary={
            "published": sum(item.status == "published" for item in configurations),
            "drafts": sum(item.status == "draft" for item in configurations),
            "workspaces": len(workspaces),
            "active_modules": sum(item.enabled for item in settings),
        },
    )


@router.post("/configurations", response_model=AdminConfigurationOut, status_code=status.HTTP_201_CREATED)
def create_configuration(
    payload: AdminConfigurationCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    kind = _normalized_kind(payload.kind)
    code = _normalized_code(payload.code)
    _validate_content(kind, payload.content_json)
    latest_revision = db.scalar(
        select(func.max(AdminConfiguration.revision)).where(
            AdminConfiguration.tenant_id == tenant_id,
            AdminConfiguration.kind == kind,
            AdminConfiguration.code == code,
        )
    )
    if latest_revision is not None:
        raise HTTPException(status_code=409, detail="Configuration code already exists; clone its published revision")
    record = AdminConfiguration(
        tenant_id=tenant_id,
        kind=kind,
        code=code,
        name=_required(payload.name, "Configuration name"),
        description=payload.description.strip(),
        status="draft",
        revision=1,
        version=1,
        content_json=payload.content_json,
        created_by_user_id=actor.id,
    )
    db.add(record)
    _commit_or_conflict(db, "Configuration code already exists")
    db.refresh(record)
    _event(db, tenant_id, actor.id, "admin_configuration.created", record)
    db.commit()
    return AdminConfigurationOut.model_validate(record)


@router.patch("/configurations/{configuration_id}", response_model=AdminConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: AdminConfigurationUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    record = _configuration(db, tenant_id, configuration_id)
    _require_draft(record)
    require_current_version(record, payload.expected_version)
    if payload.name is not None:
        record.name = _required(payload.name, "Configuration name")
    if payload.description is not None:
        record.description = payload.description.strip()
    if payload.content_json is not None:
        _validate_content(record.kind, payload.content_json)
        record.content_json = payload.content_json
    touch_collaborative_record(record)
    _event(db, tenant_id, actor.id, "admin_configuration.updated", record)
    db.commit()
    db.refresh(record)
    return AdminConfigurationOut.model_validate(record)


@router.post("/configurations/{configuration_id}/publish", response_model=AdminConfigurationOut)
def publish_configuration(
    configuration_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    record = _configuration(db, tenant_id, configuration_id)
    _require_draft(record)
    _validate_content(record.kind, record.content_json)
    record.status = "published"
    record.content_hash = _content_hash(record)
    record.published_at = utc_now()
    touch_collaborative_record(record)
    _event(db, tenant_id, actor.id, "admin_configuration.published", record)
    db.commit()
    db.refresh(record)
    return AdminConfigurationOut.model_validate(record)


@router.post(
    "/configurations/{configuration_id}/clone",
    response_model=AdminConfigurationOut,
    status_code=status.HTTP_201_CREATED,
)
def clone_configuration(
    configuration_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    source = _configuration(db, tenant_id, configuration_id)
    if source.status != "published":
        raise HTTPException(status_code=409, detail="Only a published revision can be cloned")
    next_revision = (
        int(
            db.scalar(
                select(func.max(AdminConfiguration.revision)).where(
                    AdminConfiguration.tenant_id == tenant_id,
                    AdminConfiguration.kind == source.kind,
                    AdminConfiguration.code == source.code,
                )
            )
            or 0
        )
        + 1
    )
    clone = AdminConfiguration(
        tenant_id=tenant_id,
        kind=source.kind,
        code=source.code,
        name=source.name,
        description=source.description,
        status="draft",
        revision=next_revision,
        version=1,
        content_json=json.loads(json.dumps(source.content_json)),
        created_by_user_id=actor.id,
    )
    db.add(clone)
    _commit_or_conflict(db, "A draft revision already exists")
    db.refresh(clone)
    _event(db, tenant_id, actor.id, "admin_configuration.cloned", clone, {"source_id": source.id})
    db.commit()
    return AdminConfigurationOut.model_validate(clone)


@router.post("/workspaces", response_model=EnterpriseWorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: EnterpriseWorkspaceCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EnterpriseWorkspaceOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    type_code = _normalized_code(payload.workspace_type_code)
    workspace_code = _normalized_code(payload.code)
    _published_configuration(db, tenant_id, "workspace_type", type_code)
    if payload.parent_id is not None:
        parent = _workspace(db, tenant_id, payload.parent_id)
        parent_type = _published_configuration(db, tenant_id, "workspace_type", parent.workspace_type_code)
        allowed = parent_type.content_json.get("allowed_children", [])
        if type_code not in allowed:
            raise HTTPException(status_code=409, detail=f"{parent.workspace_type_code} cannot contain {type_code}")
    workspace = EnterpriseWorkspace(
        tenant_id=tenant_id,
        parent_id=payload.parent_id,
        workspace_type_code=type_code,
        code=workspace_code,
        external_key=workspace_code,
        record_code=_next_workspace_record_code(db, tenant_id, payload.parent_id),
        name=_required(payload.name, "Workspace name"),
        status="active",
        defaults_json={},
        sort_order=payload.sort_order,
        version=1,
        created_by_user_id=actor.id,
    )
    db.add(workspace)
    _commit_or_conflict(db, "Workspace code already exists")
    db.refresh(workspace)
    _event(db, tenant_id, actor.id, "enterprise_workspace.created", workspace)
    db.commit()
    return EnterpriseWorkspaceOut.model_validate(workspace)


@router.patch("/workspaces/{workspace_id}", response_model=EnterpriseWorkspaceOut)
def update_workspace(
    workspace_id: int,
    payload: EnterpriseWorkspaceUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EnterpriseWorkspaceOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    workspace = _workspace(db, tenant_id, workspace_id)
    require_current_version(workspace, payload.expected_version)
    if payload.parent_id is not None and payload.parent_id != workspace.parent_id:
        _workspace(db, tenant_id, payload.parent_id)
        _ensure_no_workspace_cycle(db, tenant_id, workspace.id, payload.parent_id)
        workspace.parent_id = payload.parent_id
    if payload.name is not None:
        workspace.name = _required(payload.name, "Workspace name")
    if payload.status is not None:
        workspace.status = payload.status.strip().lower()
    if payload.sort_order is not None:
        workspace.sort_order = payload.sort_order
    touch_collaborative_record(workspace)
    _event(db, tenant_id, actor.id, "enterprise_workspace.updated", workspace)
    db.commit()
    db.refresh(workspace)
    return EnterpriseWorkspaceOut.model_validate(workspace)


@router.put("/workspaces/{workspace_id}/defaults", response_model=EnterpriseWorkspaceOut)
def update_workspace_defaults(
    workspace_id: int,
    payload: WorkspaceDefaultsUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EnterpriseWorkspaceOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    workspace = _workspace(db, tenant_id, workspace_id)
    require_current_version(workspace, payload.expected_version)
    workspace.defaults_json = payload.values
    touch_collaborative_record(workspace)
    _event(db, tenant_id, actor.id, "workspace_defaults.updated", workspace)
    db.commit()
    db.refresh(workspace)
    return EnterpriseWorkspaceOut.model_validate(workspace)


@router.put("/workspaces/{workspace_id}/modules/{module_key}", response_model=WorkspaceModuleSettingOut)
def set_workspace_module(
    workspace_id: int,
    module_key: str,
    payload: WorkspaceModuleSettingUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> WorkspaceModuleSettingOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    _workspace(db, tenant_id, workspace_id)
    module_code = _normalized_code(module_key)
    definition = _published_configuration(db, tenant_id, "module_definition", module_code)
    current = db.scalar(
        select(WorkspaceModuleSetting).where(
            WorkspaceModuleSetting.tenant_id == tenant_id,
            WorkspaceModuleSetting.workspace_id == workspace_id,
            WorkspaceModuleSetting.module_key == module_code,
        )
    )
    if current:
        require_current_version(current, payload.expected_version)
    if payload.enabled:
        for dependency in definition.content_json.get("dependencies", []):
            if not _effective_module_enabled(db, tenant_id, workspace_id, dependency):
                raise HTTPException(status_code=409, detail=f"Enable required module first: {dependency}")
    else:
        dependent = _enabled_dependent(db, tenant_id, workspace_id, module_code)
        if dependent:
            raise HTTPException(status_code=409, detail=f"Disable dependent module first: {dependent}")
    if current is None:
        current = WorkspaceModuleSetting(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            module_key=module_code,
            enabled=payload.enabled,
            version=1,
            updated_by_user_id=actor.id,
        )
        db.add(current)
    else:
        current.enabled = payload.enabled
        current.updated_by_user_id = actor.id
        touch_collaborative_record(current)
    _event(db, tenant_id, actor.id, "workspace_module.updated", current, {"enabled": payload.enabled})
    db.commit()
    db.refresh(current)
    return WorkspaceModuleSettingOut.model_validate(current)


@router.get("/workspaces/{workspace_id}/effective", response_model=WorkspaceEffectiveConfigurationOut)
def effective_workspace_configuration(
    workspace_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> WorkspaceEffectiveConfigurationOut:
    require_tenant_configurator(db, tenant_id, user_id)
    path = _workspace_path(db, tenant_id, _workspace(db, tenant_id, workspace_id))
    defaults: dict = {}
    modules: dict[str, bool] = {}
    for workspace in path:
        defaults.update(workspace.defaults_json or {})
        for setting in db.scalars(
            select(WorkspaceModuleSetting).where(
                WorkspaceModuleSetting.tenant_id == tenant_id,
                WorkspaceModuleSetting.workspace_id == workspace.id,
            )
        ).all():
            modules[setting.module_key] = setting.enabled
    return WorkspaceEffectiveConfigurationOut(
        workspace_id=workspace_id,
        inheritance_path=[item.id for item in path],
        defaults=defaults,
        modules=modules,
    )


@router.post("/numbering/{rule_code}/preview", response_model=NumberingResultOut)
def preview_number(
    rule_code: str,
    payload: NumberingRequest,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> NumberingResultOut:
    require_tenant_configurator(db, tenant_id, user_id)
    rule = _published_configuration(db, tenant_id, "numbering_rule", _normalized_code(rule_code))
    sequence = _current_sequence(db, tenant_id, rule.code, payload.scope_key, rule.content_json)
    return _numbering_result(rule, payload, sequence, committed=False)


@router.post("/numbering/{rule_code}/next", response_model=NumberingResultOut)
def issue_number(
    rule_code: str,
    payload: NumberingRequest,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> NumberingResultOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    rule = _published_configuration(db, tenant_id, "numbering_rule", _normalized_code(rule_code))
    scope_key = payload.scope_key.strip() or "tenant"
    counter = db.scalar(
        select(AdminNumberSequence)
        .where(
            AdminNumberSequence.tenant_id == tenant_id,
            AdminNumberSequence.rule_code == rule.code,
            AdminNumberSequence.scope_key == scope_key,
        )
        .with_for_update()
    )
    if counter is None:
        sequence = int(rule.content_json.get("start", 1))
        counter = AdminNumberSequence(
            tenant_id=tenant_id,
            rule_code=rule.code,
            scope_key=scope_key,
            next_value=sequence + 1,
            version=1,
        )
        db.add(counter)
    else:
        sequence = counter.next_value
        counter.next_value += 1
        touch_collaborative_record(counter)
    result = _numbering_result(rule, payload, sequence, committed=True)
    _event(db, tenant_id, actor.id, "numbering.issued", rule, {"value": result.value, "scope": scope_key})
    _commit_or_conflict(db, "Number sequence changed concurrently; retry the request")
    return result


def _ensure_seed(db: Session, tenant_id: int, user_id: int) -> None:
    existing = {
        (item.kind, item.code)
        for item in db.scalars(select(AdminConfiguration).where(AdminConfiguration.tenant_id == tenant_id)).all()
    }
    for kind, code, name, description, content in CONFIGURATION_SEED:
        if (kind, code) in existing:
            continue
        record = AdminConfiguration(
            tenant_id=tenant_id,
            kind=kind,
            code=code,
            name=name,
            description=description,
            status="published",
            revision=1,
            version=1,
            content_json=content,
            created_by_user_id=user_id,
            published_at=utc_now(),
        )
        record.content_hash = _content_hash(record)
        db.add(record)
    db.flush()
    if not db.scalar(select(EnterpriseWorkspace.id).where(EnterpriseWorkspace.tenant_id == tenant_id).limit(1)):
        db.add(
            EnterpriseWorkspace(
                tenant_id=tenant_id,
                parent_id=None,
                workspace_type_code="portfolio",
                code="enterprise",
                external_key="enterprise",
                record_code=_next_workspace_record_code(db, tenant_id, None),
                name="Enterprise Workspace",
                status="active",
                defaults_json={"currency": "COP", "timezone": "America/Bogota", "locale": "es-CO"},
                sort_order=0,
                version=1,
                created_by_user_id=user_id,
            )
        )


def _configurations(db: Session, tenant_id: int) -> list[AdminConfiguration]:
    return list(
        db.scalars(
            select(AdminConfiguration)
            .where(AdminConfiguration.tenant_id == tenant_id)
            .order_by(AdminConfiguration.kind, AdminConfiguration.code, AdminConfiguration.revision.desc())
        ).all()
    )


def _workspaces(db: Session, tenant_id: int) -> list[EnterpriseWorkspace]:
    return list(
        db.scalars(
            select(EnterpriseWorkspace)
            .where(EnterpriseWorkspace.tenant_id == tenant_id)
            .order_by(EnterpriseWorkspace.sort_order, EnterpriseWorkspace.name)
        ).all()
    )


def _module_settings(db: Session, tenant_id: int) -> list[WorkspaceModuleSetting]:
    return list(
        db.scalars(
            select(WorkspaceModuleSetting)
            .where(WorkspaceModuleSetting.tenant_id == tenant_id)
            .order_by(WorkspaceModuleSetting.workspace_id, WorkspaceModuleSetting.module_key)
        ).all()
    )


def _configuration(db: Session, tenant_id: int, configuration_id: int) -> AdminConfiguration:
    record = db.scalar(
        select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == tenant_id,
            AdminConfiguration.id == configuration_id,
        )
    )
    if not record:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return record


def _published_configuration(db: Session, tenant_id: int, kind: str, code: str) -> AdminConfiguration:
    record = db.scalar(
        select(AdminConfiguration)
        .where(
            AdminConfiguration.tenant_id == tenant_id,
            AdminConfiguration.kind == kind,
            AdminConfiguration.code == code,
            AdminConfiguration.status == "published",
        )
        .order_by(AdminConfiguration.revision.desc())
    )
    if not record:
        raise HTTPException(status_code=409, detail=f"Published {kind} not found: {code}")
    return record


def _workspace(db: Session, tenant_id: int, workspace_id: int) -> EnterpriseWorkspace:
    workspace = db.scalar(
        select(EnterpriseWorkspace).where(
            EnterpriseWorkspace.tenant_id == tenant_id,
            EnterpriseWorkspace.id == workspace_id,
        )
    )
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


def _next_workspace_record_code(db: Session, tenant_id: int, parent_id: int | None) -> str:
    parent_code: str | None = None
    if parent_id is not None:
        parent_code = _workspace(db, tenant_id, parent_id).record_code
    parent_filter = (
        EnterpriseWorkspace.parent_id.is_(None) if parent_id is None else EnterpriseWorkspace.parent_id == parent_id
    )
    sibling_codes = db.scalars(
        select(EnterpriseWorkspace.record_code).where(
            EnterpriseWorkspace.tenant_id == tenant_id,
            parent_filter,
        )
    ).all()
    return next_record_code(parent_code, sibling_codes)


def _workspace_path(db: Session, tenant_id: int, workspace: EnterpriseWorkspace) -> list[EnterpriseWorkspace]:
    path = [workspace]
    visited = {workspace.id}
    current = workspace
    while current.parent_id is not None:
        current = _workspace(db, tenant_id, current.parent_id)
        if current.id in visited:
            raise HTTPException(status_code=409, detail="Workspace hierarchy contains a cycle")
        visited.add(current.id)
        path.append(current)
    path.reverse()
    return path


def _ensure_no_workspace_cycle(db: Session, tenant_id: int, workspace_id: int, parent_id: int) -> None:
    current_id: int | None = parent_id
    visited: set[int] = set()
    while current_id is not None:
        if current_id == workspace_id:
            raise HTTPException(status_code=409, detail="Workspace hierarchy cannot contain cycles")
        if current_id in visited:
            raise HTTPException(status_code=409, detail="Existing workspace hierarchy contains a cycle")
        visited.add(current_id)
        current_id = _workspace(db, tenant_id, current_id).parent_id


def _effective_module_enabled(db: Session, tenant_id: int, workspace_id: int, module_key: str) -> bool:
    workspace = _workspace(db, tenant_id, workspace_id)
    result = False
    for item in _workspace_path(db, tenant_id, workspace):
        setting = db.scalar(
            select(WorkspaceModuleSetting).where(
                WorkspaceModuleSetting.tenant_id == tenant_id,
                WorkspaceModuleSetting.workspace_id == item.id,
                WorkspaceModuleSetting.module_key == module_key,
            )
        )
        if setting:
            result = setting.enabled
    return result


def _enabled_dependent(db: Session, tenant_id: int, workspace_id: int, module_key: str) -> str | None:
    definitions = db.scalars(
        select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == tenant_id,
            AdminConfiguration.kind == "module_definition",
            AdminConfiguration.status == "published",
        )
    ).all()
    for definition in definitions:
        if module_key in definition.content_json.get("dependencies", []) and _effective_module_enabled(
            db, tenant_id, workspace_id, definition.code
        ):
            return definition.code
    return None


def _validate_content(kind: str, content: dict) -> None:
    if kind == "workspace_type":
        if not isinstance(content.get("allowed_children", []), list):
            raise HTTPException(status_code=422, detail="allowed_children must be a list")
    elif kind == "module_definition":
        if not isinstance(content.get("dependencies", []), list):
            raise HTTPException(status_code=422, detail="dependencies must be a list")
    elif kind == "catalog":
        items = content.get("items")
        if not isinstance(items, list) or any(not item.get("code") for item in items if isinstance(item, dict)):
            raise HTTPException(status_code=422, detail="Catalog requires items with code")
        codes = [item.get("code") for item in items if isinstance(item, dict)]
        if len(codes) != len(set(codes)):
            raise HTTPException(status_code=422, detail="Catalog item codes must be unique")
    elif kind == "numbering_rule":
        pattern = content.get("pattern", "")
        if "{sequence" not in pattern:
            raise HTTPException(status_code=422, detail="Numbering pattern must contain {sequence}")
    elif kind == "process_definition":
        states = content.get("states")
        transitions = content.get("transitions")
        if not isinstance(content.get("form"), dict) or not isinstance(states, list) or not states:
            raise HTTPException(status_code=422, detail="Process definition requires form and states")
        if not isinstance(transitions, list):
            raise HTTPException(status_code=422, detail="Process definition requires transitions")
        for transition in transitions:
            if transition.get("from") not in states or transition.get("to") not in states:
                raise HTTPException(status_code=422, detail="Process transition references an unknown state")


def _numbering_result(
    rule: AdminConfiguration, payload: NumberingRequest, sequence: int, *, committed: bool
) -> NumberingResultOut:
    values = {"prefix": rule.content_json.get("prefix", rule.code.upper()), "sequence": sequence, **payload.context}
    try:
        value = str(rule.content_json["pattern"]).format(**values)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid numbering context or pattern: {exc}") from exc
    return NumberingResultOut(
        rule_code=rule.code,
        scope_key=payload.scope_key.strip() or "tenant",
        value=value,
        sequence=sequence,
        committed=committed,
    )


def _current_sequence(db: Session, tenant_id: int, rule_code: str, scope_key: str, content: dict) -> int:
    counter = db.scalar(
        select(AdminNumberSequence).where(
            AdminNumberSequence.tenant_id == tenant_id,
            AdminNumberSequence.rule_code == rule_code,
            AdminNumberSequence.scope_key == (scope_key.strip() or "tenant"),
        )
    )
    return counter.next_value if counter else int(content.get("start", 1))


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


def _require_draft(record: AdminConfiguration) -> None:
    if record.status != "draft":
        raise HTTPException(status_code=409, detail="Published configuration is immutable; clone it to create a draft")


def _normalized_kind(value: str) -> str:
    kind = value.strip().lower().replace("-", "_")
    if kind not in CONFIGURATION_KINDS:
        raise HTTPException(status_code=422, detail=f"Unsupported configuration kind: {value}")
    return kind


def _normalized_code(value: str) -> str:
    code = value.strip().lower().replace("_", "-").replace(" ", "-")
    if not code:
        raise HTTPException(status_code=422, detail="Code is required")
    return code


def _required(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail=f"{label} is required")
    return normalized


def _commit_or_conflict(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=message) from exc


def _event(
    db: Session,
    tenant_id: int,
    user_id: int,
    event_type: str,
    target: object,
    metadata: dict | None = None,
) -> None:
    db.add(
        SecurityEvent(
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=event_type,
            outcome="success",
            target_type=target.__class__.__name__,
            target_id=getattr(target, "id", None),
            metadata_json=metadata or {},
        )
    )
