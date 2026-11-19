"""Execution commands and read-only queries in the existing operational API."""

from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.field_operations.execution_schemas import (
    ConstraintIn,
    EventActionIn,
    EventIn,
    InstructionActionIn,
    InstructionIn,
    MappingIn,
    MaterialConsumptionIn,
    ProductionIn,
    VerificationIn,
)
from app.modules.field_operations.execution_service import RESOURCES, ExecutionService
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match

router = APIRouter()
PROJECT = "/projects/{workspace_id}"


def authorized(action):
    def dependency(
        db: Session = Depends(get_db), tenant: int = Depends(get_tenant_id), actor: int = Depends(get_user_id)
    ):
        access = require_enterprise_permission(db, tenant, actor, f"field_operations.{action}", bootstrap=False)
        return ExecutionService(db, tenant, actor, access)

    return dependency


def out(response, value):
    if isinstance(value, dict) and "version" in value:
        _etag(response, value["version"])
    return value


def queries(resource):
    def listing(
        workspace_id: int,
        response: Response,
        limit: int = Query(50, ge=1, le=200),
        after_id: int = Query(0, ge=0),
        workfront_id: int | None = Query(None, gt=0),
        status: str | None = Query(None, max_length=24),
        source_kind: str | None = Query(None, max_length=24),
        source_id: int | None = Query(None, gt=0),
        service=Depends(authorized("read")),
    ):
        return out(
            response,
            service.execution_collection(
                workspace_id,
                resource,
                limit=limit,
                after_id=after_id,
                workfront_id=workfront_id,
                status=status,
                source_kind=source_kind,
                source_id=source_id,
            ),
        )

    def detail(workspace_id: int, identity: int, response: Response, service=Depends(authorized("read"))):
        return out(response, service.execution_detail(workspace_id, resource, identity))

    router.add_api_route(PROJECT + f"/{resource}", listing, methods=["GET"], name=f"field_list_{resource}")
    router.add_api_route(PROJECT + f"/{resource}/{{identity}}", detail, methods=["GET"], name=f"field_get_{resource}")


def create_route(resource, dto, method, duty):
    def create(
        workspace_id: int,
        payload: dto,
        response: Response,
        key=Depends(_idempotency_key),
        service=Depends(authorized(duty)),
    ):
        if resource == "quantity-evidence" and payload.production_type != "INSTALLED":
            raise HTTPException(422, detail={"code": "FIELD_INSTALLED_PRODUCTION_TYPE_REQUIRED"})
        if resource == "rework" and payload.production_type != "REWORKED":
            raise HTTPException(422, detail={"code": "FIELD_REWORK_PRODUCTION_TYPE_REQUIRED"})
        return out(response, getattr(service, method)(workspace_id, payload, key))

    router.add_api_route(
        PROJECT + f"/{resource}", create, methods=["POST"], status_code=201, name=f"field_create_{resource}"
    )


def action_route(resource, dto, method, duty):
    def action(
        workspace_id: int,
        identity: int,
        payload: dto,
        response: Response,
        expected=Depends(_if_match),
        key=Depends(_idempotency_key),
        service=Depends(authorized(duty)),
    ):
        if resource in {"rework", "quantity-evidence"}:
            service.execution_detail(workspace_id, resource, identity)
        return out(response, getattr(service, method)(workspace_id, identity, payload, expected, key))

    router.add_api_route(
        PROJECT + f"/{resource}/{{identity}}/actions", action, methods=["POST"], name=f"field_transition_{resource}"
    )


for _resource in RESOURCES:
    queries(_resource)

for _resource, _dto, _method, _duty in (
    ("production", ProductionIn, "create_production", "production.record"),
    ("quantity-evidence", ProductionIn, "create_production", "production.record"),
    ("rework", ProductionIn, "create_production", "rework.record"),
    ("events", EventIn, "create_event", "event.record"),
    ("instructions", InstructionIn, "create_instruction", "instruction.record"),
    ("constraints", ConstraintIn, "create_constraint", "constraint.record"),
    ("material-consumption", MaterialConsumptionIn, "create_material_consumption", "material.record"),
):
    create_route(_resource, _dto, _method, _duty)

for _resource, _dto, _method, _duty in (
    ("production", VerificationIn, "production_action", "read"),
    ("quantity-evidence", VerificationIn, "production_action", "read"),
    ("rework", VerificationIn, "production_action", "read"),
    ("events", EventActionIn, "event_action", "event.classify"),
    ("instructions", InstructionActionIn, "instruction_action", "instruction.issue"),
    ("constraints", VerificationIn, "constraint_action", "constraint.verify"),
):
    action_route(_resource, _dto, _method, _duty)


def _mapping_expected(value: str = Header(..., alias="If-Match")):
    return 0 if value.strip() in {"0", '"0"'} else _if_match(value)


@router.post(PROJECT + "/mappings", status_code=201)
def mapping(
    workspace_id: int,
    payload: MappingIn,
    response: Response,
    expected=Depends(_mapping_expected),
    key=Depends(_idempotency_key),
    service=Depends(authorized("mapping.edit")),
):
    return out(response, service.record_mapping(workspace_id, payload, expected, key))


@router.get(PROJECT + "/dashboard")
def dashboard(workspace_id: int, service=Depends(authorized("read"))):
    return service.dashboard(workspace_id)


@router.get(PROJECT + "/readiness")
def readiness(
    workspace_id: int, workfront_id: int = Query(gt=0), as_of: date | None = None, service=Depends(authorized("read"))
):
    return service.readiness(workspace_id, workfront_id, as_of)


@router.get(PROJECT + "/lookahead")
def lookahead(
    workspace_id: int,
    horizon_days: int | None = Query(None, ge=1, le=90),
    as_of: date | None = None,
    service=Depends(authorized("read")),
):
    return service.lookahead(workspace_id, horizon_days=horizon_days, as_of=as_of)


@router.get(PROJECT + "/trace")
def trace(
    workspace_id: int,
    entity_type: str = Query(pattern=r"^(WORKFRONT|PRODUCTION|EVENT|INSTRUCTION|CONSTRAINT)$"),
    entity_id: int = Query(gt=0),
    service=Depends(authorized("read")),
):
    return service.trace(workspace_id, entity_type, entity_id)
