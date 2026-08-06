"""Read-oriented USER MODE routes for Enterprise Explorer."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext, require_enterprise_permission
from app.modules.enterprise_structure.schemas import (
    CategoryItem,
    ClassificationOut,
    EnterpriseExplorerOut,
    EnterpriseNodeDetailOut,
    EnterpriseNodeOut,
    EnterpriseTreeNodeOut,
    WorkspaceLinkOut,
)
from app.modules.enterprise_structure.service import EnterpriseStructureService

router = APIRouter(prefix="/enterprise-structure")


def _authorized_service(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str = "enterprise_structure.read",
) -> tuple[EnterpriseStructureService, EnterprisePermissionContext]:
    context = require_enterprise_permission(db, tenant_id, user_id, permission)
    service = EnterpriseStructureService(db, tenant_id, context.user.id)
    service.ensure_seed()
    return service, context


def _explorer(
    db: Session,
    tenant_id: int,
    user_id: int,
    search: str,
    workspace_type: str,
    business_unit_id: int | None,
    strategic_objective: str,
    region: str,
    status: str,
) -> EnterpriseExplorerOut:
    service, context = _authorized_service(db, tenant_id, user_id)
    return service.explorer(
        context,
        search=search,
        workspace_type=workspace_type,
        business_unit_id=business_unit_id,
        strategic_objective=strategic_objective,
        region=region,
        status=status,
    )


@router.get("/overview", response_model=EnterpriseExplorerOut)
def overview(
    search: str = Query(default="", max_length=160),
    workspace_type: str = Query(default="", max_length=120),
    business_unit_id: int | None = None,
    strategic_objective: str = Query(default="", max_length=120),
    region: str = Query(default="", max_length=120),
    status: str = Query(default="", max_length=40),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EnterpriseExplorerOut:
    return _explorer(
        db,
        tenant_id,
        user_id,
        search,
        workspace_type,
        business_unit_id,
        strategic_objective,
        region,
        status,
    )


@router.get("/tree", response_model=list[EnterpriseTreeNodeOut])
def tree(
    search: str = Query(default="", max_length=160),
    workspace_type: str = Query(default="", max_length=120),
    business_unit_id: int | None = None,
    strategic_objective: str = Query(default="", max_length=120),
    region: str = Query(default="", max_length=120),
    status: str = Query(default="", max_length=40),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[EnterpriseTreeNodeOut]:
    return _explorer(
        db,
        tenant_id,
        user_id,
        search,
        workspace_type,
        business_unit_id,
        strategic_objective,
        region,
        status,
    ).tree


@router.get("/nodes", response_model=list[EnterpriseNodeOut])
def nodes(
    search: str = Query(default="", max_length=160),
    workspace_type: str = Query(default="", max_length=120),
    business_unit_id: int | None = None,
    strategic_objective: str = Query(default="", max_length=120),
    region: str = Query(default="", max_length=120),
    status: str = Query(default="", max_length=40),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[EnterpriseNodeOut]:
    return _explorer(
        db,
        tenant_id,
        user_id,
        search,
        workspace_type,
        business_unit_id,
        strategic_objective,
        region,
        status,
    ).nodes


@router.get("/nodes/{workspace_id}", response_model=EnterpriseNodeDetailOut)
def node_detail(
    workspace_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EnterpriseNodeDetailOut:
    service, context = _authorized_service(db, tenant_id, user_id)
    return service.node_detail(context, workspace_id)


@router.get("/nodes/{workspace_id}/path", response_model=list[EnterpriseNodeOut])
def node_path(
    workspace_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[EnterpriseNodeOut]:
    return node_detail(workspace_id, db, tenant_id, user_id).path


@router.get("/nodes/{workspace_id}/classifications", response_model=list[ClassificationOut])
def node_classifications(
    workspace_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ClassificationOut]:
    return node_detail(workspace_id, db, tenant_id, user_id).classifications


@router.get("/nodes/{workspace_id}/links", response_model=list[WorkspaceLinkOut])
def node_links(
    workspace_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[WorkspaceLinkOut]:
    return node_detail(workspace_id, db, tenant_id, user_id).links


@router.get("/objectives", response_model=list[CategoryItem])
def objectives(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[CategoryItem]:
    service, _context = _authorized_service(db, tenant_id, user_id)
    category = service.repository.latest_configuration("catalog", "strategic-objective", published_only=True)
    return [CategoryItem.model_validate(item) for item in (category.content_json.get("items", []) if category else [])]
