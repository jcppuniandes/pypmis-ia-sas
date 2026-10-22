"""Separate AWP and readiness contracts; no P6 constraint or schedule writes."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.awp.models import (
    CWA,
    ConstraintMapping,
    ExecutionConstraint,
    PackageDependency,
    PackageMapping,
    ReadinessAssessment,
    WorkPackage,
)
from app.modules.awp.schemas import (
    ActionIn,
    AssessmentIn,
    ConstraintIn,
    ConstraintMappingIn,
    ConstraintTransitionIn,
    CWAIn,
    DependencyIn,
    MappingIn,
    PackageIn,
    PackageTransitionIn,
    ProfileIn,
    ProfileUpdateIn,
)
from app.modules.awp.service import AWPService
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match

router, readiness_router = APIRouter(), APIRouter()


def _authorized(action):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), actor_id: int = Depends(get_user_id)
    ):
        access = require_enterprise_permission(db, tenant_id, actor_id, f"awp.{action}", bootstrap=False)
        return AWPService(db, tenant_id, actor_id, access)

    return dependency


def _out(response, result):
    _etag(response, result.get("version", 1))
    return result


@router.get("/projects/{workspace_id}/overview")
def overview(workspace_id: int, service=Depends(_authorized("read"))):
    return service.overview(workspace_id)


@readiness_router.get("/projects/{workspace_id}/workfront")
def workfront(workspace_id: int, service=Depends(_authorized("read"))):
    model = service.read_model(workspace_id)
    return {
        "items": list(model["current_readiness"].values()),
        "cwas": model["cwas"],
        "packages": model["packages"],
        "constraints": model["constraints"],
        "authority": "NON_CPM_EXECUTION_READINESS",
        "scheduled_is_ready": False,
    }


def _listing(field):
    def query(workspace_id: int, service=Depends(_authorized("read"))):
        service._permission("read", service._project(workspace_id))
        model = {
            "cwas": CWA,
            "packages": WorkPackage,
            "mappings": PackageMapping,
            "dependencies": PackageDependency,
            "constraints": ExecutionConstraint,
            "constraint_mappings": ConstraintMapping,
            "assessments": ReadinessAssessment,
        }[field]
        items = [service._out(row) for row in service._rows(model, workspace_id)]
        return {"items": items, "total": len(items)}

    query.__name__ = f"awp_list_{field}"
    return query


for _field in ("cwas", "packages", "mappings", "dependencies", "constraints", "constraint_mappings", "assessments"):
    router.add_api_route(f"/projects/{{workspace_id}}/{_field.replace('_', '-')}", _listing(_field), methods=["GET"])


@router.get("/projects/{workspace_id}/history/{entity_type}/{identity}")
def history(workspace_id: int, entity_type: str, identity: int, service=Depends(_authorized("read"))):
    return service.history(workspace_id, entity_type, identity)


@router.get("/projects/{workspace_id}/packages/{identity}")
def package_detail(workspace_id: int, identity: int, response: Response, service=Depends(_authorized("read"))):
    service._permission("read", service._project(workspace_id))
    return _out(response, service._out(service._get(WorkPackage, workspace_id, identity)))


@router.get("/projects/{workspace_id}/cwas/{identity}")
def cwa_detail(workspace_id: int, identity: int, response: Response, service=Depends(_authorized("read"))):
    service._permission("read", service._project(workspace_id))
    return _out(response, service._out(service._get(CWA, workspace_id, identity)))


@router.get("/projects/{workspace_id}/constraints/{identity}")
def constraint_detail(workspace_id: int, identity: int, response: Response, service=Depends(_authorized("read"))):
    service._permission("read", service._project(workspace_id))
    return _out(response, service._out(service._get(ExecutionConstraint, workspace_id, identity)))


@router.post("/projects/{workspace_id}/cwas", status_code=201)
def create_cwa(
    workspace_id: int,
    payload: CWAIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("cwa.manage")),
):
    return _out(response, service.save_cwa(workspace_id, payload, key))


@router.put("/projects/{workspace_id}/cwas/{identity}")
def update_cwa(
    workspace_id: int,
    identity: int,
    payload: CWAIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("cwa.manage")),
):
    return _out(response, service.save_cwa(workspace_id, payload, key, identity, expected))


@router.post("/projects/{workspace_id}/packages", status_code=201)
def create_package(
    workspace_id: int,
    payload: PackageIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("package.edit")),
):
    return _out(response, service.save_package(workspace_id, payload, key))


@router.put("/projects/{workspace_id}/packages/{identity}")
def update_package(
    workspace_id: int,
    identity: int,
    payload: PackageIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("package.edit")),
):
    return _out(response, service.save_package(workspace_id, payload, key, identity, expected))


@router.post("/projects/{workspace_id}/packages/{identity}/transition")
def package_transition(
    workspace_id: int,
    identity: int,
    payload: PackageTransitionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("read")),
):
    return _out(response, service.transition_package(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/packages/{identity}/mappings", status_code=201)
def package_mapping(
    workspace_id: int,
    identity: int,
    payload: MappingIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("mapping.edit")),
):
    return _out(response, service.map_package(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/dependencies", status_code=201)
def create_dependency(
    workspace_id: int,
    payload: DependencyIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("dependency.edit")),
):
    return _out(response, service.save_dependency(workspace_id, payload, key))


@router.put("/projects/{workspace_id}/dependencies/{identity}")
def update_dependency(
    workspace_id: int,
    identity: int,
    payload: DependencyIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("dependency.edit")),
):
    return _out(response, service.save_dependency(workspace_id, payload, key, identity, expected))


@router.post("/projects/{workspace_id}/constraints", status_code=201)
def create_constraint(
    workspace_id: int,
    payload: ConstraintIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("constraint.raise")),
):
    return _out(response, service.save_constraint(workspace_id, payload, key))


@router.put("/projects/{workspace_id}/constraints/{identity}")
def update_constraint(
    workspace_id: int,
    identity: int,
    payload: ConstraintIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("constraint.raise")),
):
    return _out(response, service.save_constraint(workspace_id, payload, key, identity, expected))


@router.post("/projects/{workspace_id}/constraints/{identity}/transition")
def constraint_transition(
    workspace_id: int,
    identity: int,
    payload: ConstraintTransitionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("read")),
):
    return _out(response, service.transition_constraint(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/constraints/{identity}/mappings", status_code=201)
def constraint_mapping(
    workspace_id: int,
    identity: int,
    payload: ConstraintMappingIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("constraint.raise")),
):
    return _out(response, service.map_constraint(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/packages/{identity}/assess", status_code=201)
@readiness_router.post("/projects/{workspace_id}/packages/{identity}/assess", status_code=201)
def assess(
    workspace_id: int,
    identity: int,
    payload: AssessmentIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("readiness.assess")),
):
    return _out(response, service.assess(workspace_id, identity, payload, expected, key))


@router.post("/projects/{workspace_id}/packages/{identity}/release")
@readiness_router.post("/projects/{workspace_id}/packages/{identity}/release")
def release(
    workspace_id: int,
    identity: int,
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("package.release")),
):
    return _out(response, service.release(workspace_id, identity, payload, expected, key))


@router.get("/admin/profiles")
def profiles(service=Depends(_authorized("admin.configure"))):
    return service.profiles()


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
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.publish")),
):
    return _out(response, service.publish_profile(identity, payload, expected, key))


@router.post("/admin/profiles/{identity}/successor", status_code=201)
def successor_profile(
    identity: int,
    payload: ActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("admin.configure")),
):
    return _out(response, service.successor_profile(identity, payload, expected, key))
