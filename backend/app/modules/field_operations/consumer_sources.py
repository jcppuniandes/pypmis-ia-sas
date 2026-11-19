"""Typed Field fact projection; the caller enforces its native domain permissions."""

from datetime import UTC
from hmac import compare_digest

from fastapi import HTTPException
from sqlalchemy import select

from app.modules.basic_data.service import _json
from app.modules.field_operations.execution_models import (
    FieldConstraintObservation,
    FieldEvent,
    ProductionRecord,
    SiteInstruction,
)
from app.modules.field_operations.models import DailyConstructionReport, EquipmentUsage, LaborUsage, Workfront

SOURCES = {
    "PRODUCTION": ProductionRecord,
    "CONSTRAINT": FieldConstraintObservation,
    "EVENT": FieldEvent,
    "INSTRUCTION": SiteInstruction,
    "LABOR": LaborUsage,
    "EQUIPMENT": EquipmentUsage,
    "DAILY_REPORT": DailyConstructionReport,
    "WORKFRONT": Workfront,
}


def _error(status, code):
    raise HTTPException(status, detail={"code": "FIELD_CONSUMER_" + code})


def scoped(db, model, tenant, workspace, identity):
    row = db.scalar(
        select(model).where(model.tenant_id == tenant, model.project_workspace_id == workspace, model.id == identity)
    )
    if row is None:
        _error(404, "SOURCE_NOT_FOUND")
    return row


def _report(db, tenant, workspace, row):
    if isinstance(row, DailyConstructionReport):
        report = row
    elif getattr(row, "report_id", None):
        report = scoped(db, DailyConstructionReport, tenant, workspace, row.report_id)
    elif getattr(row, "shift_id", None):
        report = db.scalar(
            select(DailyConstructionReport)
            .where(
                DailyConstructionReport.tenant_id == tenant,
                DailyConstructionReport.project_workspace_id == workspace,
                DailyConstructionReport.shift_id == row.shift_id,
                DailyConstructionReport.status == "APPROVED",
            )
            .order_by(DailyConstructionReport.id.desc())
            .limit(1)
        )
    else:
        report = None
    if report is None or report.status != "APPROVED":
        _error(409, "APPROVED_DAILY_REPORT_REQUIRED")
    seen = set()
    while True:
        if report.id in seen:
            _error(409, "DAILY_REPORT_LINEAGE_CYCLE")
        seen.add(report.id)
        successor = db.scalar(
            select(DailyConstructionReport)
            .where(
                DailyConstructionReport.tenant_id == tenant,
                DailyConstructionReport.project_workspace_id == workspace,
                DailyConstructionReport.supersedes_id == report.id,
                DailyConstructionReport.status == "APPROVED",
            )
            .order_by(DailyConstructionReport.id.desc())
            .limit(1)
        )
        if successor is None:
            break
        if isinstance(row, DailyConstructionReport):
            _error(409, "DAILY_REPORT_SUPERSEDED")
        report = successor
    from app.modules.field_operations.service import record_hash

    if report.source_hash != record_hash(report):
        _error(409, "DAILY_REPORT_INTEGRITY_INVALID")
    if row is not report:
        kinds = (
            {"PRODUCTION"}
            if isinstance(row, ProductionRecord)
            else ({"LABOR", "LABOR_USAGE"} if isinstance(row, LaborUsage) else {"EQUIPMENT", "EQUIPMENT_USAGE"})
        )
        if not any(
            pin.get("source_entity_type") in kinds
            and pin.get("source_entity_id") == row.id
            and pin.get("source_version") == row.version
            and pin.get("source_hash") == row.source_hash
            for pin in report.source_references
        ):
            _error(409, "SOURCE_NOT_INCLUDED_IN_APPROVED_DAILY_REPORT")
    return report


def read_field_source(db, tenant_id, workspace_id, kind, identity, expected_version=None, expected_hash=None):
    from app.modules.field_operations.service import record_hash

    model = SOURCES.get(kind)
    if model is None:
        _error(422, "TYPE_NOT_SUPPORTED")
    with db.no_autoflush:
        row = scoped(db, model, tenant_id, workspace_id, identity)
        if not row.source_hash or row.source_hash != record_hash(row):
            _error(409, "SOURCE_INTEGRITY_INVALID")
        if hasattr(model, "supersedes_id"):
            successor_states = (
                ["VERIFIED"] if kind == "PRODUCTION" else (["APPROVED"] if kind == "DAILY_REPORT" else ["RECORDED"])
            )
            newer = db.scalar(
                select(model.id)
                .where(
                    model.tenant_id == tenant_id,
                    model.project_workspace_id == workspace_id,
                    model.supersedes_id == row.id,
                    model.status.in_(successor_states),
                )
                .limit(1)
            )
            if newer:
                _error(409, "SOURCE_SUPERSEDED")
        report = None
        if kind == "PRODUCTION":
            if row.status != "VERIFIED" or row.production_type.lower() == "reworked":
                _error(409, "VERIFIED_INSTALLATION_REQUIRED")
            report = _report(db, tenant_id, workspace_id, row)
            if row.production_type.lower() != "installed":
                _error(409, "INSTALLATION_EVIDENCE_REQUIRED")
        elif kind in {"LABOR", "EQUIPMENT", "DAILY_REPORT"}:
            report = _report(db, tenant_id, workspace_id, row)
        elif kind == "INSTRUCTION" and row.status not in {"ISSUED", "ACKNOWLEDGED", "CLOSED"}:
            _error(409, "ISSUED_INSTRUCTION_REQUIRED")
        elif kind == "CONSTRAINT" and row.status != "VERIFIED":
            _error(409, "VERIFIED_CONSTRAINT_REQUIRED")
        elif kind == "WORKFRONT" and row.status not in {"ACTIVE", "COMPLETE"}:
            _error(409, "ACTIVE_WORKFRONT_REQUIRED")
        if expected_version is not None and expected_version != row.version:
            _error(409, "SOURCE_VERSION_MISMATCH")
        if expected_hash and not compare_digest(expected_hash, row.source_hash):
            _error(409, "SOURCE_HASH_MISMATCH")
        root, seen = row, set()
        while getattr(root, "supersedes_id", None):
            if root.id in seen:
                _error(409, "SOURCE_LINEAGE_CYCLE")
            seen.add(root.id)
            root = scoped(db, model, tenant_id, workspace_id, root.supersedes_id)
        observed = getattr(row, "observed_at", None) or row.created_at
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        facts = {
            "status": row.status,
            "source_root_id": root.id,
            "workfront_id": getattr(row, "workfront_id", row.id if kind == "WORKFRONT" else None),
            "shift_id": getattr(row, "shift_id", None),
        }
        if report:
            facts["approved_report"] = {"id": report.id, "version": report.version, "hash": report.source_hash}
        for field in (
            "scope_item_id",
            "plan_item_id",
            "iwp_id",
            "quantity",
            "uom",
            "production_type",
            "regular_hours",
            "overtime_hours",
            "operating_hours",
            "idle_hours",
            "standby_hours",
            "downtime_hours",
            "headcount",
            "constraint_type",
            "severity",
            "description",
            "actual_start",
            "actual_finish",
            "location_reference",
        ):
            if hasattr(row, field):
                facts[field] = getattr(row, field)
        return _json(
            {
                "source_domain": "FIELD_OPERATIONS",
                "source_entity_type": kind,
                "source_entity_id": row.id,
                "source_root_id": root.id,
                "source_version": row.version,
                "source_hash": row.source_hash,
                "observed_at": observed.isoformat(),
                "observation_date": (report.report_date if report else observed.date()).isoformat(),
                "facts": facts,
            }
        )
