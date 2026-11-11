"""Dedicated, scoped Engineering Manager API and governed profile commands."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.engineering_foundation.integration import EngineeringMappingIn, TargetKind
from app.modules.engineering_foundation.schemas import (
    CommentActionIn,
    CommentIn,
    DeliverableIn,
    DesignPackageActionIn,
    DesignPackageIn,
    DocumentIn,
    InterfaceActionIn,
    InterfaceIn,
    ProfileIn,
    ProfileUpdateIn,
    ReasonIn,
    ReleaseIn,
    ReviewActionIn,
    RevisionIn,
)
from app.modules.engineering_foundation.service import EngineeringFoundationService
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match

router = APIRouter()


def _authorized(action):
    def dependency(
        db: Session = Depends(get_db),
        tenant_id: int = Depends(get_tenant_id),
        actor_id: int = Depends(get_user_id),
    ):
        access = require_enterprise_permission(db, tenant_id, actor_id, f"engineering.{action}", bootstrap=False)
        return EngineeringFoundationService(db, tenant_id, actor_id, access)

    return dependency


def _out(response, result):
    _etag(response, result.get("version", 1))
    return result


@router.get("/projects/{workspace_id}/configuration")
def configuration(
    workspace_id: int,
    service=Depends(_authorized("read")),
):
    return service.configuration(workspace_id)


@router.get("/projects/{workspace_id}/deliverables")
def deliverables(
    workspace_id: int,
    limit: int = Query(50, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    service=Depends(_authorized("read")),
):
    return service.deliverables(workspace_id, limit=limit, after_id=after_id)


@router.get("/projects/{workspace_id}/deliverables/{identity}")
def deliverable(
    workspace_id: int,
    identity: int,
    response: Response,
    service=Depends(_authorized("read")),
):
    return _out(response, service.deliverable(workspace_id, identity))


@router.get("/projects/{workspace_id}/deliverables/{identity}/revisions")
def revisions(
    workspace_id: int,
    identity: int,
    limit: int = Query(50, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    service=Depends(_authorized("read")),
):
    return service.revisions(workspace_id, identity, limit=limit, after_id=after_id)


@router.get("/projects/{workspace_id}/revisions/{identity}")
def revision(
    workspace_id: int,
    identity: int,
    response: Response,
    service=Depends(_authorized("read")),
):
    return _out(response, service.revision(workspace_id, identity))


@router.get("/projects/{workspace_id}/revisions/{identity}/reviews")
def reviews(
    workspace_id: int,
    identity: int,
    service=Depends(_authorized("read")),
):
    return service.reviews(workspace_id, identity)


@router.get("/projects/{workspace_id}/design-packages")
def design_packages(
    workspace_id: int,
    service=Depends(_authorized("read")),
):
    return service.design_packages(workspace_id)


@router.get("/projects/{workspace_id}/interfaces")
def interfaces(
    workspace_id: int,
    service=Depends(_authorized("read")),
):
    return service.interfaces(workspace_id)


@router.get("/projects/{workspace_id}/history")
def history(
    workspace_id: int,
    limit: int = Query(50, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    service=Depends(_authorized("read")),
):
    return service.history(workspace_id, limit=limit, after_id=after_id)


@router.get("/projects/{workspace_id}/revisions/{identity}/mappings")
def revision_mappings(
    workspace_id: int,
    identity: int,
    response: Response,
    service=Depends(_authorized("read")),
):
    return _out(response, service.mappings(workspace_id, identity))


@router.get("/projects/{workspace_id}/design-packages/{identity}/mappings")
def design_package_mappings(
    workspace_id: int,
    identity: int,
    response: Response,
    service=Depends(_authorized("read")),
):
    return _out(response, service.mappings(workspace_id, identity, design_package=True))


@router.get("/projects/{workspace_id}/mapping-targets")
def mapping_targets(
    workspace_id: int,
    target_kind: TargetKind,
    limit: int = Query(100, ge=1, le=200),
    after: int = Query(0, ge=0),
    service=Depends(_authorized("read")),
):
    return service.mapping_targets(workspace_id, target_kind, limit=limit, after=after)


@router.get("/projects/{workspace_id}/document-targets")
def document_targets(
    workspace_id: int,
    limit: int = Query(100, ge=1, le=200),
    after: int = Query(0, ge=0),
    service=Depends(_authorized("read")),
):
    return service.document_targets(workspace_id, limit=limit, after=after)


@router.get("/projects/{workspace_id}/readiness")
def readiness(
    workspace_id: int,
    work_package_id: int = Query(gt=0),
    as_of: date | None = None,
    service=Depends(_authorized("read")),
):
    return service.readiness(workspace_id, work_package_id, as_of)


@router.get("/projects/{workspace_id}/status")
def status(
    workspace_id: int,
    as_of: date | None = None,
    group_by: str | None = Query(None, pattern="^(discipline|ewp|area|cwa|project)$"),
    service=Depends(_authorized("read")),
):
    return service.status_metrics(workspace_id, as_of, group_by)


@router.get("/projects/{workspace_id}/lookahead")
def lookahead(
    workspace_id: int,
    as_of: date | None = None,
    horizon_days: int | None = Query(None, ge=1, le=120),
    service=Depends(_authorized("read")),
):
    return service.lookahead(workspace_id, as_of, horizon_days)


@router.get("/projects/{workspace_id}/source-facts")
def source_facts(
    workspace_id: int,
    as_of: date | None = None,
    service=Depends(_authorized("read")),
):
    return service.source_facts(workspace_id, as_of)


@router.get("/admin/profiles")
def profiles(
    service=Depends(_authorized("admin.configure")),
):
    return service.profiles()


@router.post("/projects/{workspace_id}/deliverables", status_code=201)
def create_deliverable(
    workspace_id: int,
    payload: DeliverableIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("deliverable.create")),
):
    return _out(response, service.save_deliverable(workspace_id, payload, key))


@router.put("/projects/{workspace_id}/deliverables/{identity}")
def update_deliverable(
    workspace_id: int,
    identity: int,
    payload: DeliverableIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("deliverable.edit")),
):
    return _out(response, service.save_deliverable(workspace_id, payload, key, identity, expected))


@router.post("/projects/{workspace_id}/deliverables/{identity}/revisions", status_code=201)
def create_revision(
    workspace_id: int,
    identity: int,
    payload: RevisionIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("revision.create")),
):
    return _out(response, service.save_revision(workspace_id, identity, payload, key))


@router.put("/projects/{workspace_id}/revisions/{identity}")
def update_revision(
    workspace_id: int,
    identity: int,
    payload: RevisionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("revision.edit")),
):
    return _out(response, service.update_revision(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/revisions/{identity}/successor", status_code=201)
def successor_revision(
    workspace_id: int,
    identity: int,
    payload: RevisionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("revision.supersede")),
):
    return _out(response, service.successor_revision(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/revisions/{identity}/document")
def link_document(
    workspace_id: int,
    identity: int,
    payload: DocumentIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("document.link")),
):
    return _out(response, service.link_document(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/revisions/{identity}/review-action")
def review_action(
    workspace_id: int,
    identity: int,
    payload: ReviewActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("read")),
):
    return _out(response, service.review_action(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/revisions/{identity}/comments", status_code=201)
def add_comment(
    workspace_id: int,
    identity: int,
    payload: CommentIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("review.comment")),
):
    return _out(response, service.add_comment(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/review-comments/{identity}/transition")
def comment_action(
    workspace_id: int,
    identity: int,
    payload: CommentActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("read")),
):
    return _out(response, service.comment_action(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/revisions/{identity}/ifc-release", status_code=201)
def release_ifc(
    workspace_id: int,
    identity: int,
    payload: ReleaseIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("ifc.release")),
):
    return _out(response, service.release_ifc(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/design-packages", status_code=201)
def create_design_package(
    workspace_id: int,
    payload: DesignPackageIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("design_package.manage")),
):
    return _out(response, service.save_design_package(workspace_id, payload, key))


@router.put("/projects/{workspace_id}/design-packages/{identity}")
def update_design_package(
    workspace_id: int,
    identity: int,
    payload: DesignPackageIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("design_package.manage")),
):
    return _out(response, service.save_design_package(workspace_id, payload, key, identity, expected))


@router.post("/projects/{workspace_id}/design-packages/{identity}/transition")
def design_package_action(
    workspace_id: int,
    identity: int,
    payload: DesignPackageActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("design_package.manage")),
):
    return _out(response, service.design_package_action(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/interfaces", status_code=201)
def create_interface(
    workspace_id: int,
    payload: InterfaceIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("interface.manage")),
):
    return _out(response, service.save_interface(workspace_id, payload, key))


@router.post("/projects/{workspace_id}/interfaces/{identity}/transition")
def interface_action(
    workspace_id: int,
    identity: int,
    payload: InterfaceActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("interface.manage")),
):
    return _out(response, service.interface_action(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/revisions/{identity}/mappings", status_code=201)
def map_revision(
    workspace_id: int,
    identity: int,
    payload: EngineeringMappingIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("mapping.edit")),
):
    return _out(response, service.map_target(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/design-packages/{identity}/mappings", status_code=201)
def map_design_package(
    workspace_id: int,
    identity: int,
    payload: EngineeringMappingIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("mapping.edit")),
):
    return _out(response, service.map_target(workspace_id, identity, payload, expected, key, design_package=True))


@router.post("/admin/profiles", status_code=201)
def create_profile(
    payload: ProfileIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.configure")),
):
    return _out(response, service.create_profile(payload, key))


@router.put("/admin/profiles/{identity}")
def update_profile(
    identity: int,
    payload: ProfileUpdateIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.configure")),
):
    return _out(response, service.update_profile(identity, payload, expected, key))


@router.post("/admin/profiles/{identity}/publish")
def publish_profile(
    identity: int,
    payload: ReasonIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.publish")),
):
    return _out(response, service.publish_profile(identity, payload, expected, key))


@router.post("/admin/profiles/{identity}/successor", status_code=201)
def successor_profile(
    identity: int,
    payload: ReasonIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.configure")),
):
    return _out(response, service.successor_profile(identity, payload, expected, key))
