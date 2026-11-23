"""Append-only lot trace and explicit readiness assessments; GET never creates facts."""

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import Field, model_validator

from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match
from app.modules.quality.consumer_models import QualityMapping, QualityReadinessAssessment
from app.modules.quality.execution_router import authorized
from app.modules.quality.execution_service import QualityExecutionService
from app.modules.quality.schemas import DocumentPinIn, Input, Quantity, ReasonIn, SourcePinIn


class LotIdentifiers(Input):
    # An identity reference, not a new inventory, batch or asset master.
    lot: str | None = Field(None, min_length=1, max_length=120)
    batch: str | None = Field(None, min_length=1, max_length=120)
    heat: str | None = Field(None, min_length=1, max_length=120)
    serial: str | None = Field(None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def present(self):
        if not any((self.lot, self.batch, self.heat, self.serial)):
            raise ValueError("At least one typed lot/batch/heat/serial identity is required")
        return self


class LotLinkIn(ReasonIn):
    receipt_reference: SourcePinIn
    production_reference: SourcePinIn
    lot_identifiers: LotIdentifiers
    quantity: Quantity | None = None
    uom: str | None = Field(None, min_length=1, max_length=40)
    document_reference: DocumentPinIn
    action: Literal["SET", "REMOVE"] = "SET"
    supersedes_id: int | None = Field(None, gt=0)


class AssessmentIn(ReasonIn):
    itp_id: int = Field(gt=0)
    subject_reference: SourcePinIn


def expected_stream(value: str = Header(..., alias="If-Match")):
    return 0 if value.strip() in {"0", '"0"'} else _if_match(value)


class QualitySupportService(QualityExecutionService):
    def support_list(self, workspace, model, limit, after_id, **filters):
        self._read_project(workspace)
        query = self._scoped(model, workspace)
        for field, value in filters.items():
            if value is not None:
                query = query.where(getattr(model, field) == value)
        latest = (
            self.db.scalar(query.order_by(model.version.desc()).limit(1))
            if all(value is not None for value in filters.values())
            else None
        )
        values = list(self.db.scalars(query.where(model.id > after_id).order_by(model.id).limit(limit + 1)))
        return {
            "items": [self._out(row) for row in values[:limit]],
            "next_cursor": values[limit - 1].id if len(values) > limit else None,
            "version": latest.version if latest else 0,
            "latest_id": latest.id if latest else None,
        }

    def lot_link(self, workspace, payload, expected, key):
        self._ready(workspace, "mapping.edit")

        def apply():
            _, profile = self._ready(workspace, "mapping.edit")
            self.db.refresh(self._project(workspace), with_for_update=True)
            if (
                payload.receipt_reference.source_type != "MATERIAL_RECEIPT_LINE"
                or payload.production_reference.source_type not in {"FIELD_PRODUCTION", "FIELD_REWORK"}
            ):
                self._error(422, "QUALITY_LOT_LINK_SOURCE_TYPE_INVALID")
            receipt = self._subject(workspace, payload.receipt_reference)
            production = self._subject(workspace, payload.production_reference)
            subject = f"RECEIPT:{receipt['source_root_id']}:PRODUCTION:{production['source_root_id']}"
            previous = self.db.scalar(
                self._scoped(QualityMapping, workspace)
                .where(QualityMapping.subject_key == subject)
                .order_by(QualityMapping.version.desc())
                .limit(1)
                .with_for_update()
            )
            self._version(previous.version if previous else 0, expected)
            if (
                (previous.id if previous else None) != payload.supersedes_id
                or payload.action == "REMOVE"
                and previous is None
            ):
                self._error(409, "QUALITY_LOT_LINK_EXPLICIT_PREDECESSOR_REQUIRED")
            if payload.quantity is not None:
                facts = receipt["facts"]
                if payload.uom != facts["uom"] or payload.quantity > Decimal(str(facts["quantity"])):
                    self._error(422, "QUALITY_LOT_LINK_QUANTITY_UOM_INVALID")
            elif payload.uom is not None:
                self._error(422, "QUALITY_LOT_LINK_QUANTITY_REQUIRED")
            row = self._new(
                QualityMapping,
                workspace,
                version=(previous.version + 1 if previous else 1),
                receipt_line_id=receipt["source_id"],
                production_record_id=production["source_id"],
                subject_key=subject,
                receipt_reference=receipt,
                production_reference=production,
                lot_identifiers=payload.lot_identifiers.model_dump(exclude={"reason"}, exclude_none=True),
                quantity=payload.quantity,
                uom=payload.uom,
                document_reference=self._document(workspace, payload.document_reference),
                action=payload.action,
                supersedes_id=payload.supersedes_id,
                reason=payload.reason,
                **self._profile_pin(profile),
            )
            return self._record(row, "QUALITY_LOT_LINK_RECORDED", payload.reason)

        return self._write("lot_link", workspace, payload, key, apply, expected=expected)

    def assess_readiness(self, workspace, payload, expected, key):
        self._ready(workspace, "readiness.assess")

        def apply():
            _, profile = self._ready(workspace, "readiness.assess")
            self.db.refresh(self._project(workspace), with_for_update=True)
            snapshot = self.readiness(workspace, payload.itp_id, payload.subject_reference)
            subject = snapshot["subject_reference"]
            previous = self.db.scalar(
                self._scoped(QualityReadinessAssessment, workspace)
                .where(
                    QualityReadinessAssessment.itp_id == payload.itp_id,
                    QualityReadinessAssessment.subject_key == subject["subject_key"],
                )
                .order_by(QualityReadinessAssessment.version.desc())
                .limit(1)
                .with_for_update()
            )
            self._version(previous.version if previous else 0, expected)
            row = self._new(
                QualityReadinessAssessment,
                workspace,
                version=(previous.version + 1 if previous else 1),
                itp_id=payload.itp_id,
                subject_key=subject["subject_key"],
                subject_reference=subject,
                as_of=self._assessment_time(None),
                readiness_state=snapshot["state"],
                snapshot_json=snapshot,
                reason=payload.reason,
                **self._profile_pin(profile),
            )
            return self._record(row, "QUALITY_READINESS_ASSESSED", payload.reason)

        return self._write("readiness.assess", workspace, payload, key, apply, expected=expected)


router = APIRouter()
ROOT = "/projects/{workspace_id}"


def service(action):
    def dependency(base=Depends(authorized(action))):
        return QualitySupportService(base.db, base.tenant_id, base.actor_id, base.access_context)

    return dependency


@router.get(ROOT + "/lot-links")
def lot_links(
    workspace_id: int,
    limit: int = Query(50, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    receipt_line_id: int | None = Query(None, gt=0),
    production_id: int | None = Query(None, gt=0),
    owner=Depends(service("read")),
):
    return owner.support_list(
        workspace_id,
        QualityMapping,
        limit,
        after_id,
        receipt_line_id=receipt_line_id,
        production_record_id=production_id,
    )


@router.post(ROOT + "/lot-links", status_code=201)
def link(
    workspace_id: int,
    payload: LotLinkIn,
    response: Response,
    expected=Depends(expected_stream),
    key=Depends(_idempotency_key),
    owner=Depends(service("mapping.edit")),
):
    result = owner.lot_link(workspace_id, payload, expected, key)
    _etag(response, result["version"])
    return result


@router.get(ROOT + "/readiness/assessments")
def assessments(
    workspace_id: int,
    limit: int = Query(50, ge=1, le=200),
    after_id: int = Query(0, ge=0),
    itp_id: int | None = Query(None, gt=0),
    subject_key: str | None = Query(None, max_length=500),
    owner=Depends(service("read")),
):
    return owner.support_list(
        workspace_id, QualityReadinessAssessment, limit, after_id, itp_id=itp_id, subject_key=subject_key
    )


@router.post(ROOT + "/readiness/assess", status_code=201)
def assess(
    workspace_id: int,
    payload: AssessmentIn,
    response: Response,
    expected=Depends(expected_stream),
    key=Depends(_idempotency_key),
    owner=Depends(service("readiness.assess")),
):
    result = owner.assess_readiness(workspace_id, payload, expected, key)
    _etag(response, result["version"])
    return result
