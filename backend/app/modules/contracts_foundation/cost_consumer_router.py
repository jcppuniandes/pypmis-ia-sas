"""Explicit read and adoption under Cost authority; no financial recognition."""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.core.time import utc_today
from app.database.session import get_db
from app.modules.contracts_foundation.cost_consumer_models import TABLE, CostCommercialAdoption
from app.modules.contracts_foundation.models import CommercialCommitment
from app.modules.cost_foundation.models import ControlAccount, CostCBS, CostCode
from app.modules.cost_foundation.service import CostFoundationService
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match

router = APIRouter()
ROOT = "/projects/{workspace_id}/commercial-commitment-adoptions"


class AdoptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_entity_id: int = Field(gt=0)
    source_version: int = Field(gt=0)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_at: AwareDatetime
    effective_at: date
    cbs_id: int = Field(gt=0)
    cost_code_id: int = Field(gt=0)
    control_account_id: int = Field(gt=0)
    consumer_status: Literal["ADOPTED", "NOT_ADOPTED"]
    reason: str = Field(min_length=3, max_length=1000)


def _expected(value: str = Header(..., alias="If-Match")):
    return 0 if value.strip() in {"0", '"0"'} else _if_match(value)


class AdoptionService:
    def __init__(self, owner):
        self.owner = owner
        self.db = owner.db

    def check(self, workspace, *, write=False):
        project = self.owner._project(workspace)
        self.owner._permission("read", project)
        if not inspect(self.db.connection()).has_table(TABLE):
            self.owner._error(409, "COST_COMMERCIAL_ADOPTION_MIGRATION_REQUIRED")
        if write:
            return self.owner._ready(workspace, "mapping.edit")[1]
        return None

    def query(self, workspace):
        return select(CostCommercialAdoption).where(
            CostCommercialAdoption.tenant_id == self.owner.tenant_id,
            CostCommercialAdoption.project_workspace_id == workspace,
        )

    def latest(self, workspace, identity):
        return self.db.scalar(
            self.query(workspace)
            .where(CostCommercialAdoption.source_entity_id == identity)
            .order_by(CostCommercialAdoption.version.desc())
            .limit(1)
        )

    def source(self, workspace, identity, **pins):
        from app.modules.contracts_foundation.service import read_commercial_commitment

        return read_commercial_commitment(self.db, self.owner.tenant_id, workspace, identity, **pins)

    def lookup(self, workspace, identity):
        self.check(workspace)
        source = self.source(workspace, identity)
        previous = self.latest(workspace, identity)
        return source | {
            "version": previous.version if previous else 0,
            "consumer_status": previous.consumer_status
            if previous and previous.source_hash == source["source_hash"]
            else "NOT_ADOPTED",
        }

    def decide(self, workspace, payload, expected, key):
        self.check(workspace, write=True)

        def apply():
            profile = self.check(workspace, write=True)
            # Serialize decisions on the scoped source row; Cost never mutates that row.
            self.owner._get(CommercialCommitment, workspace, payload.source_entity_id, lock=True)
            source = self.source(
                workspace,
                payload.source_entity_id,
                expected_version=payload.source_version,
                expected_hash=payload.source_hash,
            )
            observed = datetime.fromisoformat(str(source["observed_at"]))
            effective = date.fromisoformat(str(source["effective_at"]))
            if payload.observed_at != observed:
                self.owner._error(409, "COST_COMMERCIAL_OBSERVATION_MISMATCH")
            if not effective <= payload.effective_at <= utc_today():
                self.owner._error(422, "COST_COMMERCIAL_EFFECTIVE_DATE_INVALID")
            mapping = {}
            for model, field in (
                (CostCBS, "cbs_id"),
                (CostCode, "cost_code_id"),
                (ControlAccount, "control_account_id"),
            ):
                target = self.owner._get(model, workspace, getattr(payload, field), lock=True)
                if target.status != "ACTIVE":
                    self.owner._error(409, "COST_COMMERCIAL_MAPPING_INACTIVE")
                mapping[field] = {"id": target.id, "version": target.version, "code": target.code}
            old = self.latest(workspace, payload.source_entity_id)
            version = old.version if old else 0
            self.owner._version(version, expected)
            if (
                old
                and old.source_hash == payload.source_hash
                and old.consumer_status == payload.consumer_status
                and old.mapping_reference == mapping
                and old.effective_at == payload.effective_at
            ):
                self.owner._error(409, "COST_COMMERCIAL_DECISION_ALREADY_RECORDED")
            row = CostCommercialAdoption(
                **(self.owner._base(workspace) | {"version": version + 1}),
                **payload.model_dump(),
                source_domain="CONTRACTS",
                source_entity_type="COMMERCIAL_COMMITMENT",
                source_snapshot=source
                | {
                    "consumer_profile": {
                        "id": profile.id,
                        "revision": profile.revision,
                        "hash": profile.content_hash,
                    }
                },
                mapping_reference=mapping,
            )
            self.db.add(row)
            self.db.flush()
            self.owner._event(
                "commercial_commitment_reference_decided",
                row.id,
                {
                    "project_workspace_id": workspace,
                    "source_entity_id": row.source_entity_id,
                    "source_hash": row.source_hash,
                    "decision": row.consumer_status,
                    "reason": row.reason,
                    "decision_version": row.version,
                    "mapping": mapping,
                },
            )
            return self.owner._out(row)

        return self.owner._write(
            "commercial_commitment_reference.decide", workspace, payload, key, apply, expected=expected
        )


def _service(
    db: Session = Depends(get_db),
    tenant: int = Depends(get_tenant_id),
    actor: int = Depends(get_user_id),
):
    access = require_enterprise_permission(db, tenant, actor, "cost.read", bootstrap=False)
    return AdoptionService(CostFoundationService(db, tenant, actor, access))


@router.get(ROOT + "/lookup")
def lookup(workspace_id: int, response: Response, source_entity_id: int = Query(gt=0), service=Depends(_service)):
    result = service.lookup(workspace_id, source_entity_id)
    _etag(response, result["version"])
    return result


@router.get(ROOT)
def history(
    workspace_id: int,
    before_id: int | None = Query(default=None, gt=0),
    limit: int = Query(50, ge=1, le=200),
    service=Depends(_service),
):
    service.check(workspace_id)
    query = service.query(workspace_id)
    if before_id is not None:
        query = query.where(CostCommercialAdoption.id < before_id)
    rows = list(service.db.scalars(query.order_by(CostCommercialAdoption.id.desc()).limit(limit + 1)))
    return {
        "items": [service.owner._out(row) for row in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }


@router.post(ROOT, status_code=201)
def decide(
    workspace_id: int,
    payload: AdoptionIn,
    response: Response,
    expected=Depends(_expected),
    key=Depends(_idempotency_key),
    service=Depends(_service),
):
    result = service.decide(workspace_id, payload, expected, key)
    _etag(response, result["version"])
    return result
