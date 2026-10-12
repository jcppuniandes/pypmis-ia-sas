"""Approved-model run commands; existing RBAC, ETag and receipts are reused."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match
from app.modules.qra_engine.schemas import RunActionIn, RunCreateIn
from app.modules.qra_engine.service import QraEngineService, audit_denial

router = APIRouter()


def _authorized(permission):
    def dependency(
        db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id), user_id: int = Depends(get_user_id)
    ):
        from fastapi import HTTPException

        try:
            context = require_enterprise_permission(db, tenant_id, user_id, permission, bootstrap=False)
        except HTTPException:
            audit_denial(db, tenant_id, user_id, "MISSING_PERMISSION:" + permission)
            raise
        return QraEngineService(db, tenant_id, user_id, context)

    return dependency


def _out(response, result):
    _etag(response, result["revision_version"])
    return result


@router.get("/projects/{project_id}/options")
def options(project_id: int, service=Depends(_authorized("qra_run.read"))):
    return service.options(project_id)


@router.get("/projects/{project_id}/approved-models")
def approved_models(
    project_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    service=Depends(_authorized("qra_run.read")),
):
    return service.approved_models(project_id, page=page, page_size=page_size)


@router.get("/models/{model_id}/preflight")
def preflight(model_id: int, service=Depends(_authorized("qra_run.read"))):
    return service.preflight(model_id)


@router.post("/models/{model_id}/runs", status_code=201)
def create_run(
    model_id: int,
    payload: RunCreateIn,
    response: Response,
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("qra_run.create")),
):
    return _out(response, service.create_run(model_id, payload, key))


@router.get("/projects/{project_id}/runs")
def runs(
    project_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    service=Depends(_authorized("qra_run.read")),
):
    return service.runs(project_id, page=page, page_size=page_size)


# Static path must precede /runs/{run_id}.
@router.get("/runs/compare")
def compare(left_id: int, right_id: int, service=Depends(_authorized("qra_run.read"))):
    return service.compare(left_id, right_id)


@router.get("/runs/{run_id}")
def run(run_id: int, response: Response, summary: bool = True, service=Depends(_authorized("qra_run.read"))):
    return _out(response, service.run(run_id, summary=summary))


@router.get("/runs/{run_id}/status")
def status(run_id: int, response: Response, service=Depends(_authorized("qra_run.read"))):
    return _out(response, service.status(run_id))


def _result_route(section):
    def endpoint(
        run_id: int,
        page: int = Query(1, ge=1),
        page_size: int = Query(100, ge=1, le=200),
        service=Depends(_authorized("qra_run.read")),
    ):
        return service.result_section(run_id, section, page=page, page_size=page_size)

    router.add_api_route(f"/runs/{{run_id}}/{section}", endpoint, methods=["GET"], name=f"qra_run_{section}")


for _section in (
    "summary",
    "percentiles",
    "convergence",
    "sensitivity",
    "milestones",
    "drivers",
    "histogram",
    "cdf",
    "provenance",
):
    _result_route(_section)


@router.post("/runs/{run_id}/execute")
def execute(
    run_id: int,
    payload: RunActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("qra_run.execute")),
):
    return _out(response, service.execute(run_id, expected, payload, key))


@router.post("/runs/{run_id}/cancel")
def cancel(
    run_id: int,
    payload: RunActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("qra_run.cancel")),
):
    return _out(response, service.cancel(run_id, expected, payload, key))


@router.post("/runs/{run_id}/review")
def review(
    run_id: int,
    payload: RunActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("qra_run.review")),
):
    return _out(response, service.review_action(run_id, expected, payload, key, "review"))


@router.post("/runs/{run_id}/accept")
def accept(
    run_id: int,
    payload: RunActionIn,
    response: Response,
    expected: int = Depends(_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(_authorized("qra_run.accept")),
):
    return _out(response, service.review_action(run_id, expected, payload, key, "accept"))


@router.get("/runs/{run_id}/evidence")
def evidence(run_id: int, service=Depends(_authorized("qra_run.read"))):
    return service.evidence(run_id)


@router.get("/projects/{project_id}/provider-evidence")
def provider(project_id: int, analysis_type: str | None = Query(None), service=Depends(_authorized("qra_run.read"))):
    return service.provider_evidence(project_id, analysis_type)
