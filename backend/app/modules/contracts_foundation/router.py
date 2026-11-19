"""Project-scoped O2C commands, queries and independent ADMIN publication."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.contracts_foundation.schemas import (
    CommitmentIn,
    ContractActionIn,
    ContractIn,
    ContractPackageIn,
    PackageActionIn,
    ProfileIn,
    ProfileUpdateIn,
    ReasonIn,
    SourceType,
)
from app.modules.contracts_foundation.service import COLLECTIONS, ContractsService
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match

router = APIRouter()
PROJECT = "/projects/{workspace_id}"


def authorized(action, service_class=ContractsService):
    def dependency(
        db: Session = Depends(get_db),
        tenant_id: int = Depends(get_tenant_id),
        actor_id: int = Depends(get_user_id),
    ):
        context = require_enterprise_permission(db, tenant_id, actor_id, f"contracts.{action}", bootstrap=False)
        return service_class(db, tenant_id, actor_id, context)

    return dependency


def out(response, result):
    if isinstance(result, dict) and "version" in result:
        _etag(response, result["version"])
    return result


@router.get(PROJECT + "/configuration")
def configuration(workspace_id: int, service=Depends(authorized("read"))):
    return service.configuration(workspace_id)


@router.get(PROJECT + "/procurement-source")
def procurement_source(
    workspace_id: int,
    source_type: SourceType,
    source_id: int = Query(gt=0),
    package_id: int | None = Query(None, gt=0),
    service=Depends(authorized("read")),
):
    return service.procurement_source(workspace_id, source_type, source_id, package_id)


@router.get(PROJECT + "/document-targets")
def document_targets(
    workspace_id: int,
    limit: int = Query(100, ge=1, le=200),
    after: int = Query(0, ge=0),
    service=Depends(authorized("read")),
):
    return service.document_targets(workspace_id, limit, after)


@router.get(PROJECT + "/commitment-source")
def commitment_source(
    workspace_id: int,
    commitment_id: int = Query(gt=0),
    service=Depends(authorized("read")),
):
    return service.commercial_source(workspace_id, commitment_id)


@router.get(PROJECT + "/readiness/{contract_id}")
def readiness(workspace_id: int, contract_id: int, service=Depends(authorized("read"))):
    return service.readiness(workspace_id, contract_id)


@router.get(PROJECT + "/lookahead")
def lookahead(
    workspace_id: int,
    horizon_days: int = Query(30, ge=1, le=366),
    as_of: date | None = None,
    status: str | None = Query(None, max_length=24),
    contract_id: int | None = Query(None, gt=0),
    service=Depends(authorized("read")),
):
    return service.lookahead(workspace_id, horizon_days, as_of, status, contract_id)


@router.get(PROJECT + "/trace/{contract_id}")
def trace(workspace_id: int, contract_id: int, service=Depends(authorized("read"))):
    return service.trace(workspace_id, contract_id)


def _register_queries(collection):
    def list_rows(
        workspace_id: int,
        limit: int = Query(50, ge=1, le=200),
        after_id: int = Query(0, ge=0),
        contract_id: int | None = Query(None, gt=0),
        entity_id: int | None = Query(None, gt=0),
        entity_type: str | None = Query(None, max_length=64),
        service=Depends(authorized("read")),
    ):
        return service.collection(
            workspace_id,
            collection,
            limit=limit,
            after_id=after_id,
            contract_id=contract_id,
            entity_type=entity_type,
            entity_id=entity_id,
        )

    def detail(workspace_id: int, identity: int, response: Response, service=Depends(authorized("read"))):
        return out(response, service.detail(workspace_id, collection, identity))

    router.add_api_route(PROJECT + f"/{collection}", list_rows, methods=["GET"], name=f"contracts_list_{collection}")
    router.add_api_route(
        PROJECT + f"/{collection}/{{identity}}", detail, methods=["GET"], name=f"contracts_get_{collection}"
    )


for _collection in COLLECTIONS:
    _register_queries(_collection)


@router.post(PROJECT + "/packages", status_code=201)
def create_package(
    workspace_id: int,
    payload: ContractPackageIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(authorized("package.prepare")),
):
    return out(response, service.save_package(workspace_id, payload, key))


@router.put(PROJECT + "/packages/{identity}")
def update_package(
    workspace_id: int,
    identity: int,
    payload: ContractPackageIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(authorized("package.prepare")),
):
    return out(response, service.save_package(workspace_id, payload, key, identity, expected))


@router.post(PROJECT + "/packages/{identity}/actions")
def package_action(
    workspace_id: int,
    identity: int,
    payload: PackageActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(authorized("package.prepare")),
):
    return out(response, service.transition_package(workspace_id, identity, payload, expected, key))


@router.post(PROJECT + "/contracts", status_code=201)
def create_contract(
    workspace_id: int,
    payload: ContractIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(authorized("contract.prepare")),
):
    return out(response, service.create_contract(workspace_id, payload, key))


@router.post(PROJECT + "/contracts/{identity}/actions")
def contract_action(
    workspace_id: int,
    identity: int,
    payload: ContractActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(authorized("read")),
):
    return out(response, service.transition_contract(workspace_id, identity, payload, expected, key))


@router.post(PROJECT + "/commitments", status_code=201)
def create_commitment(
    workspace_id: int,
    payload: CommitmentIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(authorized("commitment.prepare")),
):
    return out(response, service.create_commitment(workspace_id, payload, key))


@router.post(PROJECT + "/commitments/{identity}/approve")
def approve_commitment(
    workspace_id: int,
    identity: int,
    payload: ReasonIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(authorized("commitment.approve")),
):
    return out(response, service.approve_commitment(workspace_id, identity, payload, expected, key))


@router.get("/admin/profiles")
def profiles(service=Depends(authorized("admin.configure"))):
    return service.profiles()


@router.post("/admin/profiles", status_code=201)
def create_profile(
    payload: ProfileIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(authorized("admin.configure")),
):
    return out(response, service.create_profile(payload, key))


@router.put("/admin/profiles/{identity}")
def update_profile(
    identity: int,
    payload: ProfileUpdateIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(authorized("admin.configure")),
):
    return out(response, service.update_profile(identity, payload, expected, key))


@router.post("/admin/profiles/{identity}/publish")
def publish_profile(
    identity: int,
    payload: ReasonIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(authorized("admin.publish")),
):
    return out(response, service.publish_profile(identity, payload, expected, key))


@router.post("/admin/profiles/{identity}/successor", status_code=201)
def successor_profile(
    identity: int,
    payload: ReasonIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(authorized("admin.configure")),
):
    return out(response, service.successor_profile(identity, payload, expected, key))
