"""ADMIN MODE routes for Enterprise Structure Configuration."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import (
    require_enterprise_permission,
    require_organization_scope,
)
from app.modules.enterprise_structure.revisions import EnterpriseStructureRevisionService
from app.modules.enterprise_structure.schemas import (
    CategoryUpdate,
    ClassificationCreate,
    ClassificationOut,
    CompositionRuleOut,
    CompositionRuleUpdate,
    ConfigurationValidationOut,
    ConfigurationVersionOut,
    CoreRevisionOut,
    EnterpriseNodeCreate,
    EnterpriseNodeOut,
    EnterpriseNodeUpdate,
    EnterpriseStructureConfigurationOut,
    EnterpriseTreeNodeOut,
    PublicationOut,
    PublicationRequest,
    RevisionApprovalRequest,
    RevisionClassificationsUpdate,
    RevisionDiffOut,
    RevisionMoveRequest,
    RevisionPublishRequest,
    RevisionRecordCodePreviewOut,
    RevisionRecordCodePreviewRequest,
    RevisionReleaseUpdate,
    RevisionRollbackRequest,
    RevisionValidationOut,
    RevisionWorkspaceCreate,
    RevisionWorkspaceUpdate,
    WorkspaceLinkCreate,
    WorkspaceLinkOut,
)
from app.modules.enterprise_structure.service import EnterpriseStructureService

router = APIRouter(prefix="/admin-configuration/enterprise-structure")


def _service(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    *,
    organization_scope: bool = False,
) -> EnterpriseStructureService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission)
    if organization_scope:
        require_organization_scope(context)
    service = EnterpriseStructureService(db, tenant_id, context.user.id)
    service.ensure_seed()
    return service


def _revision_service(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    *,
    organization_scope: bool = True,
) -> EnterpriseStructureRevisionService:
    context = require_enterprise_permission(db, tenant_id, user_id, permission)
    if organization_scope:
        require_organization_scope(context)
    EnterpriseStructureService(db, tenant_id, context.user.id).ensure_seed()
    return EnterpriseStructureRevisionService(db, tenant_id, context.user.id)


@router.get("/configuration", response_model=EnterpriseStructureConfigurationOut)
def configuration(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EnterpriseStructureConfigurationOut:
    return _service(db, tenant_id, user_id, "admin.enterprise_structure.read").configuration_overview()


@router.get("/tree", response_model=list[EnterpriseTreeNodeOut])
def tree(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[EnterpriseTreeNodeOut]:
    service = _service(db, tenant_id, user_id, "admin.enterprise_structure.read")
    return service.build_tree(service.repository.workspaces())


@router.post("/nodes", response_model=EnterpriseNodeOut, status_code=status.HTTP_201_CREATED)
def create_node(
    payload: EnterpriseNodeCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EnterpriseNodeOut:
    return _service(
        db,
        tenant_id,
        user_id,
        "admin.enterprise_structure.manage",
        organization_scope=True,
    ).create_node(payload)


@router.patch("/nodes/{workspace_id}", response_model=EnterpriseNodeOut)
def update_node(
    workspace_id: int,
    payload: EnterpriseNodeUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EnterpriseNodeOut:
    return _service(
        db,
        tenant_id,
        user_id,
        "admin.enterprise_structure.manage",
        organization_scope=True,
    ).update_node(workspace_id, payload)


@router.delete("/nodes/{workspace_id}", response_model=EnterpriseNodeOut)
def archive_node(
    workspace_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EnterpriseNodeOut:
    return _service(
        db,
        tenant_id,
        user_id,
        "admin.enterprise_structure.manage",
        organization_scope=True,
    ).archive_node(workspace_id)


@router.post("/nodes/{workspace_id}/classifications", response_model=ClassificationOut, status_code=201)
def add_classification(
    workspace_id: int,
    payload: ClassificationCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ClassificationOut:
    return _service(
        db,
        tenant_id,
        user_id,
        "admin.enterprise_category.manage",
        organization_scope=True,
    ).add_classification(workspace_id, payload)


@router.delete("/classifications/{classification_id}", status_code=204)
def remove_classification(
    classification_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> Response:
    _service(
        db,
        tenant_id,
        user_id,
        "admin.enterprise_category.manage",
        organization_scope=True,
    ).remove_classification(classification_id)
    return Response(status_code=204)


@router.post("/links", response_model=WorkspaceLinkOut, status_code=201)
def add_link(
    payload: WorkspaceLinkCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> WorkspaceLinkOut:
    return _service(
        db,
        tenant_id,
        user_id,
        "admin.enterprise_structure.manage",
        organization_scope=True,
    ).add_link(payload)


@router.delete("/links/{link_id}", status_code=204)
def remove_link(
    link_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> Response:
    _service(
        db,
        tenant_id,
        user_id,
        "admin.enterprise_structure.manage",
        organization_scope=True,
    ).remove_link(link_id)
    return Response(status_code=204)


@router.get("/types", response_model=list[ConfigurationVersionOut])
def workspace_types(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ConfigurationVersionOut]:
    service = _service(db, tenant_id, user_id, "admin.workspace_type.read")
    return [
        ConfigurationVersionOut.model_validate(item)
        for item in service.repository.latest_configurations("workspace_type", prefer_draft=True)
    ]


@router.post("/types/{type_code}/clone", response_model=ConfigurationVersionOut, status_code=201)
def clone_workspace_type(
    type_code: str,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConfigurationVersionOut:
    return _service(db, tenant_id, user_id, "admin.workspace_type.manage", organization_scope=True).clone_configuration(
        "workspace_type", type_code
    )


@router.get("/categories", response_model=list[ConfigurationVersionOut])
def categories(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ConfigurationVersionOut]:
    return _service(db, tenant_id, user_id, "admin.enterprise_category.read").configuration_overview().categories


@router.post("/categories/{category_code}/clone", response_model=ConfigurationVersionOut, status_code=201)
def clone_category(
    category_code: str,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConfigurationVersionOut:
    return _service(
        db,
        tenant_id,
        user_id,
        "admin.enterprise_category.manage",
        organization_scope=True,
    ).clone_configuration("catalog", category_code)


@router.put("/categories/{configuration_id}", response_model=ConfigurationVersionOut)
def update_category(
    configuration_id: int,
    payload: CategoryUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConfigurationVersionOut:
    return _service(
        db,
        tenant_id,
        user_id,
        "admin.enterprise_category.manage",
        organization_scope=True,
    ).update_category(configuration_id, payload)


@router.get("/composition-rules", response_model=list[CompositionRuleOut])
def composition_rules(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[CompositionRuleOut]:
    return _service(db, tenant_id, user_id, "admin.composition_rule.read").configuration_overview().composition_rules


@router.put("/composition-rules/{parent_type_code}", response_model=CompositionRuleOut)
def update_composition_rule(
    parent_type_code: str,
    payload: CompositionRuleUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CompositionRuleOut:
    return _service(
        db,
        tenant_id,
        user_id,
        "admin.composition_rule.manage",
        organization_scope=True,
    ).update_composition_rule(parent_type_code, payload)


@router.post("/validate", response_model=ConfigurationValidationOut)
def validate_configuration(
    payload: PublicationRequest,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ConfigurationValidationOut:
    return _service(db, tenant_id, user_id, "admin.enterprise_structure.publish").validate_configuration(
        payload.configuration_ids
    )


@router.post("/publish", response_model=PublicationOut)
def publish_configuration(
    payload: PublicationRequest,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PublicationOut:
    return _service(
        db,
        tenant_id,
        user_id,
        "admin.enterprise_structure.publish",
        organization_scope=True,
    ).publish(payload)


@router.post("/clone", response_model=list[ConfigurationVersionOut], status_code=201)
def clone_release(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ConfigurationVersionOut]:
    return _service(
        db,
        tenant_id,
        user_id,
        "admin.enterprise_structure.manage",
        organization_scope=True,
    ).clone_release()


@router.post("/enterprise-core-releases/{published_id}/clone", response_model=CoreRevisionOut, status_code=201)
def create_core_revision(
    published_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CoreRevisionOut:
    return _revision_service(db, tenant_id, user_id, "admin.enterprise_structure.revision.create").create_revision(
        published_id
    )


@router.get("/enterprise-core-releases/{release_id}", response_model=CoreRevisionOut)
def core_revision(
    release_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CoreRevisionOut:
    return _revision_service(
        db,
        tenant_id,
        user_id,
        "admin.enterprise_structure.read",
        organization_scope=False,
    ).get_revision(release_id)


@router.patch("/enterprise-core-releases/{release_id}", response_model=CoreRevisionOut)
def update_core_revision(
    release_id: int,
    payload: RevisionReleaseUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CoreRevisionOut:
    return _revision_service(db, tenant_id, user_id, "admin.enterprise_structure.revision.edit").update_revision(
        release_id, payload
    )


@router.post(
    "/enterprise-core-releases/{release_id}/record-code-preview",
    response_model=RevisionRecordCodePreviewOut,
)
def preview_revision_record_code(
    release_id: int,
    payload: RevisionRecordCodePreviewRequest,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RevisionRecordCodePreviewOut:
    return _revision_service(db, tenant_id, user_id, "admin.enterprise_structure.revision.edit").record_code_preview(
        release_id, payload
    )


@router.post("/enterprise-core-releases/{release_id}/workspaces", response_model=CoreRevisionOut, status_code=201)
def add_revision_workspace(
    release_id: int,
    payload: RevisionWorkspaceCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CoreRevisionOut:
    return _revision_service(db, tenant_id, user_id, "admin.enterprise_structure.revision.edit").add_workspace(
        release_id, payload
    )


@router.patch(
    "/enterprise-core-releases/{release_id}/workspaces/{workspace_key}",
    response_model=CoreRevisionOut,
)
def edit_revision_workspace(
    release_id: int,
    workspace_key: str,
    payload: RevisionWorkspaceUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CoreRevisionOut:
    return _revision_service(db, tenant_id, user_id, "admin.enterprise_structure.revision.edit").edit_workspace(
        release_id, workspace_key, payload
    )


@router.post(
    "/enterprise-core-releases/{release_id}/workspaces/{workspace_key}/move",
    response_model=CoreRevisionOut,
)
def move_revision_workspace(
    release_id: int,
    workspace_key: str,
    payload: RevisionMoveRequest,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CoreRevisionOut:
    return _revision_service(db, tenant_id, user_id, "admin.enterprise_structure.revision.edit").move_workspace(
        release_id, workspace_key, payload
    )


@router.post(
    "/enterprise-core-releases/{release_id}/workspaces/{workspace_key}/archive",
    response_model=CoreRevisionOut,
)
def archive_revision_workspace(
    release_id: int,
    workspace_key: str,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CoreRevisionOut:
    return _revision_service(db, tenant_id, user_id, "admin.enterprise_structure.revision.edit").archive_workspace(
        release_id, workspace_key
    )


@router.put(
    "/enterprise-core-releases/{release_id}/workspaces/{workspace_key}/classifications",
    response_model=CoreRevisionOut,
)
def classify_revision_workspace(
    release_id: int,
    workspace_key: str,
    payload: RevisionClassificationsUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CoreRevisionOut:
    return _revision_service(db, tenant_id, user_id, "admin.enterprise_structure.revision.edit").set_classifications(
        release_id, workspace_key, payload
    )


@router.post("/enterprise-core-releases/{release_id}/validate", response_model=RevisionValidationOut)
def validate_core_revision(
    release_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RevisionValidationOut:
    return _revision_service(db, tenant_id, user_id, "admin.enterprise_structure.revision.validate").validate_revision(
        release_id
    )


@router.get("/enterprise-core-releases/{release_id}/diff", response_model=RevisionDiffOut)
def compare_core_revision(
    release_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RevisionDiffOut:
    return _revision_service(db, tenant_id, user_id, "admin.enterprise_structure.revision.compare").compare_revision(
        release_id
    )


@router.post("/enterprise-core-releases/{release_id}/approve", response_model=CoreRevisionOut)
def approve_core_revision(
    release_id: int,
    payload: RevisionApprovalRequest,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CoreRevisionOut:
    return _revision_service(db, tenant_id, user_id, "admin.enterprise_structure.revision.approve").approve_revision(
        release_id, payload
    )


@router.post("/enterprise-core-releases/{release_id}/publish", response_model=CoreRevisionOut)
def publish_core_revision(
    release_id: int,
    payload: RevisionPublishRequest,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CoreRevisionOut:
    return _revision_service(db, tenant_id, user_id, "admin.enterprise_structure.publish").publish_revision(
        release_id, payload
    )


@router.post("/enterprise-core-releases/{release_id}/rollback", response_model=CoreRevisionOut)
def rollback_core_revision(
    release_id: int,
    payload: RevisionRollbackRequest,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CoreRevisionOut:
    return _revision_service(db, tenant_id, user_id, "admin.enterprise_structure.rollback").rollback_revision(
        release_id, payload
    )
