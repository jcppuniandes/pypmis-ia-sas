"""Consumer routes explicitly resolve and adopt evidence without write-back."""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.core.time import utc_today
from app.database.session import get_db
from app.modules.cost_foundation.service import CostFoundationService
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.forecast_foundation.models import ForecastVersion
from app.modules.forecast_foundation.service import ForecastFoundationService
from app.modules.operational_context.models import ProjectControlsPeriod
from app.modules.portfolio_review.router import _etag, _idempotency_key, _if_match
from app.modules.procurement_consumers.models import TABLE, ProcurementAdoption
from app.modules.procurement_foundation.consumer_sources import resolve_procurement_source
from app.modules.procurement_foundation.service import ProcurementFoundationService
from app.modules.progress_foundation.service import ProgressFoundationService

OWNERS = {
    "COST": (CostFoundationService, "mapping.edit"),
    "PROGRESS": (ProgressFoundationService, "capture"),
    "FORECAST": (ForecastFoundationService, "edit"),
}
ROOT = "/projects/{workspace_id}/procurement-adoptions"


def _decision_if_match(value: str = Header(..., alias="If-Match")):
    # The decision stream has no row until its first explicit decision.
    return 0 if value.strip() in {"0", '"0"'} else _if_match(value)


class AdoptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_entity_type: str = Field(pattern=r"^[A-Z_]{2,40}$")
    source_entity_id: int = Field(gt=0)
    source_package_id: int = Field(gt=0)
    source_version: int = Field(gt=0)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_at: AwareDatetime
    effective_at: date
    consumer_status: Literal["ADOPTED", "NOT_ADOPTED"]
    period_id: int | None = Field(default=None, gt=0)
    consumer_version_id: int | None = Field(default=None, gt=0)
    consumer_version: int | None = Field(default=None, gt=0)
    signal_key: str | None = Field(default=None, pattern=r"^[a-z_]{2,80}$")
    mapping_ids: list[int] = Field(default_factory=list, max_length=3)
    reason: str = Field(min_length=3, max_length=1000)


class Consumer:
    def __init__(self, domain, owner, procurement):
        self.domain, self.owner, self.procurement = domain, owner, procurement
        self.db = owner.db
        self.duty = OWNERS[domain][1]

    def boundary(self, workspace, *, write=False):
        project = self.owner._project(workspace)
        self.owner._permission("read", project)
        self.procurement._read_project(workspace)
        if not inspect(self.db.connection()).has_table(TABLE):
            self.owner._error(409, "PROCUREMENT_ADOPTION_MIGRATION_REQUIRED")
        if write:
            return self.owner._ready(workspace, self.duty)[1]
        return None

    def resolve(self, workspace, kind, identity, package, **pins):
        return resolve_procurement_source(
            self.db,
            self.owner.tenant_id,
            workspace,
            kind,
            identity,
            consumer=self.domain,
            package_id=package,
            **pins,
        )

    def query(self, workspace):
        return select(ProcurementAdoption).where(
            ProcurementAdoption.tenant_id == self.owner.tenant_id,
            ProcurementAdoption.project_workspace_id == workspace,
            ProcurementAdoption.consumer == self.domain,
        )

    @staticmethod
    def context(package, period=None, version_id=None, signal=None):
        return f"{package}:{period or 0}:{version_id or 0}:{signal or '-'}"

    def latest(self, workspace, kind, identity, context):
        return self.db.scalar(
            self.query(workspace)
            .where(
                ProcurementAdoption.source_entity_type == kind,
                ProcurementAdoption.source_entity_id == identity,
                ProcurementAdoption.context_key == context,
            )
            .order_by(ProcurementAdoption.version.desc())
            .limit(1)
        )

    def lookup(self, workspace, kind, identity, package, period, version_id, signal):
        self.boundary(workspace)
        self.validate_shape(period, version_id, version_id, signal)
        source = self.resolve(workspace, kind, identity, package)
        if period:
            self.owner._get(ProjectControlsPeriod, workspace, period)
        if version_id:
            forecast = self.owner._get(ForecastVersion, workspace, version_id)
            if forecast.period_id != period:
                self.owner._error(409, "PROCUREMENT_ADOPTION_FORECAST_PERIOD_MISMATCH")
            if signal not in source["facts"].get("signals", {}):
                self.owner._error(422, "PROCUREMENT_ADOPTION_SIGNAL_NOT_AVAILABLE")
        else:
            forecast = None
        old = self.latest(workspace, kind, identity, self.context(source["package_id"], period, version_id, signal))
        current = bool(
            old
            and old.source_hash == source["source_hash"]
            and (forecast is None or old.consumer_version == forecast.version)
        )
        return source | {
            "version": old.version if old else 0,
            "consumer_status": old.consumer_status if current else "NOT_ADOPTED",
            "consumer_version": forecast.version if forecast else None,
            "consumer_version_status": forecast.status if forecast else None,
        }

    def validate_shape(self, period, version_id, version, signal, mapping_ids=()):
        good = (
            self.domain == "COST"
            and not any((period, version_id, version, signal))
            or self.domain == "PROGRESS"
            and period
            and not any((version_id, version, signal, mapping_ids))
            or self.domain == "FORECAST"
            and all((period, version_id, version, signal))
            and not mapping_ids
        )
        if not good:
            self.owner._error(422, "PROCUREMENT_ADOPTION_CONTEXT_INVALID")

    def validate_context(self, workspace, payload, source):
        self.validate_shape(
            payload.period_id,
            payload.consumer_version_id,
            payload.consumer_version,
            payload.signal_key,
            payload.mapping_ids,
        )
        source_effective = date.fromisoformat(source["effective_date"])
        if payload.effective_at < source_effective or payload.effective_at > utc_today():
            self.owner._error(422, "PROCUREMENT_ADOPTION_EFFECTIVE_DATE_INVALID")
        if payload.period_id:
            period = self.owner._get(ProjectControlsPeriod, workspace, payload.period_id, lock=True)
            if not period.period_start <= payload.effective_at <= period.period_end:
                self.owner._error(422, "PROCUREMENT_ADOPTION_EFFECTIVE_PERIOD_INVALID")
            if self.domain == "PROGRESS" and period.status != "OPEN":
                self.owner._error(409, "PROCUREMENT_ADOPTION_PROGRESS_PERIOD_NOT_OPEN")
            if self.domain == "FORECAST" and period.status not in {"OPEN", "REVIEW"}:
                self.owner._error(409, "PROCUREMENT_ADOPTION_FORECAST_PERIOD_NOT_EDITABLE")
        if self.domain == "COST":
            candidates = {row["id"]: row for row in source["cost_mappings"]}
            ids = set(payload.mapping_ids)
            if len(payload.mapping_ids) != 3 or len(ids) != 3 or not ids <= candidates.keys():
                self.owner._error(409, "PROCUREMENT_ADOPTION_COST_MAPPING_REQUIRED")
            mappings = [candidates[identity] for identity in sorted(ids)]
            if {row["target_kind"] for row in mappings} != {"CBS", "COST_CODE", "CONTROL_ACCOUNT"}:
                self.owner._error(409, "PROCUREMENT_ADOPTION_COST_MAPPING_REQUIRED")
            return {"cost": mappings}, None
        if self.domain == "PROGRESS":
            return {"related": source["related_mappings"]}, None
        forecast = self.owner._get(ForecastVersion, workspace, payload.consumer_version_id, lock=True)
        if forecast.status != "DRAFT" or forecast.period_id != payload.period_id:
            self.owner._error(409, "PROCUREMENT_ADOPTION_FORECAST_DRAFT_REQUIRED")
        if forecast.version != payload.consumer_version:
            self.owner._error(409, "PROCUREMENT_ADOPTION_FORECAST_VERSION_STALE")
        signal = source["facts"].get("signals", {}).get(payload.signal_key)
        if not signal:
            self.owner._error(422, "PROCUREMENT_ADOPTION_SIGNAL_NOT_AVAILABLE")
        return {}, date.fromisoformat(signal)

    def decide(self, workspace, payload, expected, key):
        self.boundary(workspace, write=True)

        def apply():
            profile = self.boundary(workspace, write=True)
            source = self.resolve(
                workspace,
                payload.source_entity_type,
                payload.source_entity_id,
                payload.source_package_id,
                expected_version=payload.source_version,
                expected_hash=payload.source_hash,
            )
            observed = datetime.fromisoformat(source["observed_at"])
            if payload.observed_at != observed:
                self.owner._error(409, "PROCUREMENT_ADOPTION_OBSERVATION_MISMATCH")
            mapping, signal_date = self.validate_context(workspace, payload, source)
            context = self.context(
                payload.source_package_id, payload.period_id, payload.consumer_version_id, payload.signal_key
            )
            old = self.latest(workspace, payload.source_entity_type, payload.source_entity_id, context)
            version = old.version if old else 0
            self.owner._version(version, expected)
            row = ProcurementAdoption(
                **(self.owner._base(workspace) | {"version": version + 1}),
                consumer=self.domain,
                source_domain="PROCUREMENT",
                source_entity_type=source["source_type"],
                source_entity_id=source["source_id"],
                source_package_id=source["package_id"],
                source_version=source["source_version"],
                source_hash=source["source_hash"],
                observed_at=observed,
                effective_at=payload.effective_at,
                consumer_status=payload.consumer_status,
                period_id=payload.period_id,
                consumer_version_id=payload.consumer_version_id,
                consumer_version=payload.consumer_version,
                signal_key=payload.signal_key,
                source_forecast_date=signal_date,
                context_key=context,
                mapping_reference=mapping,
                source_snapshot=source
                | {"consumer_profile": {"id": profile.id, "revision": profile.revision, "hash": profile.content_hash}},
                reason=payload.reason,
            )
            self.db.add(row)
            self.db.flush()
            self.owner._event(
                "procurement_reference_decided",
                row.id,
                {
                    "project_workspace_id": workspace,
                    "source_entity_type": row.source_entity_type,
                    "source_entity_id": row.source_entity_id,
                    "consumer_status": row.consumer_status,
                    "source_hash": row.source_hash,
                    "version": row.version,
                    "reason": row.reason,
                },
            )
            return self.owner._out(row)

        return self.owner._write("procurement_reference.decide", workspace, payload, key, apply, expected=expected)


def consumer_router(domain):
    router = APIRouter()
    service_type, _ = OWNERS[domain]

    def consumer(
        db: Session = Depends(get_db),
        tenant: int = Depends(get_tenant_id),
        actor: int = Depends(get_user_id),
    ):
        owner_access = require_enterprise_permission(db, tenant, actor, f"{domain.lower()}.read", bootstrap=False)
        procurement_access = require_enterprise_permission(db, tenant, actor, "procurement.read", bootstrap=False)
        return Consumer(
            domain,
            service_type(db, tenant, actor, owner_access),
            ProcurementFoundationService(db, tenant, actor, procurement_access),
        )

    @router.get(ROOT + "/lookup", name=f"{domain.lower()}_procurement_lookup")
    def lookup(
        workspace_id: int,
        response: Response,
        source_entity_type: str = Query(pattern=r"^[A-Z_]{2,40}$"),
        source_entity_id: int = Query(gt=0),
        source_package_id: int | None = Query(default=None, gt=0),
        period_id: int | None = Query(default=None, gt=0),
        consumer_version_id: int | None = Query(default=None, gt=0),
        signal_key: str | None = Query(default=None, pattern=r"^[a-z_]{2,80}$"),
        service=Depends(consumer),
    ):
        result = service.lookup(
            workspace_id,
            source_entity_type,
            source_entity_id,
            source_package_id,
            period_id,
            consumer_version_id,
            signal_key,
        )
        _etag(response, result["version"])
        return result

    @router.get(ROOT, name=f"{domain.lower()}_procurement_history")
    def history(
        workspace_id: int,
        before_id: int | None = Query(default=None, gt=0),
        limit: int = Query(50, ge=1, le=200),
        service=Depends(consumer),
    ):
        service.boundary(workspace_id)
        query = service.query(workspace_id)
        if before_id is not None:
            query = query.where(ProcurementAdoption.id < before_id)
        rows = list(service.db.scalars(query.order_by(ProcurementAdoption.id.desc()).limit(limit + 1)))
        return {
            "items": [service.owner._out(row) for row in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
        }

    @router.post(ROOT, status_code=201, name=f"{domain.lower()}_procurement_decide")
    def decide(
        workspace_id: int,
        payload: AdoptionIn,
        response: Response,
        expected=Depends(_decision_if_match),
        key=Depends(_idempotency_key),
        service=Depends(consumer),
    ):
        result = service.decide(workspace_id, payload, expected, key)
        _etag(response, result["version"])
        return result

    return router
