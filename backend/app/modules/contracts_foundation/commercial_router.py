"""Contract commercial registers, payment evidence and controlled mappings."""

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

from app.modules.contracts_foundation.commercial_schemas import (
    ApplicationActionIn,
    CertificateActionIn,
    ChangeActionIn,
    ChangeIn,
    ClaimActionIn,
    ClaimIn,
    FinanceReferenceIn,
    MappingIn,
    NoticeActionIn,
    NoticeIn,
    PaymentApplicationIn,
    PaymentCertificateIn,
    ReasonIn,
    SOVIn,
)
from app.modules.contracts_foundation.commercial_service import RESOURCES, CommercialWorkflows
from app.modules.contracts_foundation.router import PROJECT, authorized, out
from app.modules.portfolio_review.router import _idempotency_key, _if_match

router = APIRouter()


def commercial(action):
    return authorized(action, CommercialWorkflows)


def _queries(resource):
    def list_rows(
        workspace_id: int,
        limit: int = Query(50, ge=1, le=200),
        after_id: int = Query(0, ge=0),
        contract_id: int | None = Query(None, gt=0),
        status: str | None = Query(None, max_length=32),
        service=Depends(commercial("read")),
    ):
        return service.commercial_list(
            workspace_id,
            resource,
            limit=limit,
            after_id=after_id,
            contract_id=contract_id,
            status=status,
        )

    def detail(workspace_id: int, identity: int, response: Response, service=Depends(commercial("read"))):
        return out(response, service.commercial_detail(workspace_id, resource, identity))

    if resource != "mappings":
        router.add_api_route(PROJECT + f"/{resource}", list_rows, methods=["GET"], name=f"contracts_list_{resource}")
    router.add_api_route(
        PROJECT + f"/{resource}/{{identity}}", detail, methods=["GET"], name=f"contracts_get_{resource}"
    )


def _create(resource, dto, method, duty):
    def create(
        workspace_id: int,
        payload: dto,
        response: Response,
        key: str = Depends(_idempotency_key),
        service=Depends(commercial(duty)),
    ):
        return out(response, getattr(service, method)(workspace_id, payload, key))

    router.add_api_route(
        PROJECT + f"/{resource}",
        create,
        methods=["POST"],
        status_code=201,
        name=f"contracts_create_{resource}",
    )


def _transition(resource, operation, dto, method, duty):
    def transition(
        workspace_id: int,
        identity: int,
        payload: dto,
        response: Response,
        expected: int = Depends(_if_match),
        key: str = Depends(_idempotency_key),
        service=Depends(commercial(duty)),
    ):
        return out(response, getattr(service, method)(workspace_id, identity, payload, expected, key))

    router.add_api_route(
        PROJECT + f"/{resource}/{{identity}}/{operation}",
        transition,
        methods=["POST"],
        name=f"contracts_transition_{resource}_{operation}",
    )


for _resource in RESOURCES:
    _queries(_resource)

for _resource, _dto, _method, _duty in (
    ("sovs", SOVIn, "create_sov", "sov.edit"),
    ("changes", ChangeIn, "create_change", "change.prepare"),
    ("payment-applications", PaymentApplicationIn, "create_application", "application.prepare"),
    ("payment-certificates", PaymentCertificateIn, "create_certificate", "certificate.prepare"),
    ("notices", NoticeIn, "create_notice", "notice.record"),
    ("claims", ClaimIn, "create_claim", "claim.prepare"),
):
    _create(_resource, _dto, _method, _duty)

for _resource, _operation, _dto, _method, _duty in (
    ("sovs", "publish", ReasonIn, "publish_sov", "sov.publish"),
    ("changes", "actions", ChangeActionIn, "change_action", "read"),
    ("payment-applications", "actions", ApplicationActionIn, "application_action", "application.review"),
    ("payment-certificates", "actions", CertificateActionIn, "certificate_action", "certificate.approve"),
    ("notices", "actions", NoticeActionIn, "notice_action", "notice.record"),
    ("claims", "actions", ClaimActionIn, "claim_action", "claim.decide"),
    ("payment-certificates", "finance-references", FinanceReferenceIn, "add_finance_reference", "invoice.reference"),
):
    _transition(_resource, _operation, _dto, _method, _duty)


@router.get(PROJECT + "/progress-sources")
def progress_sources(
    workspace_id: int,
    period_id: int = Query(gt=0),
    sov_line_id: int = Query(gt=0),
    limit: int = Query(50, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    service=Depends(commercial("read")),
):
    return service.progress_sources(workspace_id, period_id, sov_line_id, limit=limit, after_id=after_id)


MappingKind = Literal["CONTRACT_PACKAGE", "CONTRACT"]


@router.get(PROJECT + "/mappings")
def mapping_history(
    workspace_id: int,
    response: Response,
    source_kind: MappingKind | None = None,
    source_id: int | None = Query(None, gt=0),
    limit: int = Query(50, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    service=Depends(commercial("read")),
):
    if (source_kind is None) != (source_id is None):
        raise HTTPException(422, detail={"code": "CONTRACTS_MAPPING_SOURCE_INCOMPLETE"})
    if source_kind is None:
        return service.commercial_list(workspace_id, "mappings", limit=limit, after_id=after_id)
    return out(response, service.mapping_history(workspace_id, source_kind, source_id, limit=limit, after_id=after_id))


def _mapping_if_match(value: str = Header(..., alias="If-Match")) -> int:
    if value.strip() in {"0", '"0"', 'W/"0"'}:
        return 0
    return _if_match(value)


@router.post(PROJECT + "/mappings", status_code=201)
def record_mapping(
    workspace_id: int,
    payload: MappingIn,
    response: Response,
    expected: int = Depends(_mapping_if_match),
    key: str = Depends(_idempotency_key),
    service=Depends(commercial("mapping.edit")),
):
    return out(response, service.record_mapping(workspace_id, payload, expected, key))
