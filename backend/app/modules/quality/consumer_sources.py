"""Quality evidence reader. Native callers authorize scope before invoking this facade."""

from datetime import UTC
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.modules.basic_data.service import _hash, _json
from app.modules.field_operations.consumer_models import FieldConsumerDecision
from app.modules.progress_foundation.models import ProgressMeasurement
from app.modules.quality.consumer_models import QualityConsumerDecision, QualityReadinessAssessment
from app.modules.quality.execution_models import QualityAcceptance, QualityNCR
from app.modules.quality.execution_service import QualityExecutionService
from app.modules.quality.models import InspectionRecord, TestRecord

SOURCES = {
    "ACCEPTANCE": QualityAcceptance,
    "READINESS": QualityReadinessAssessment,
    "NCR": QualityNCR,
    "INSPECTION": InspectionRecord,
    "TEST": TestRecord,
}


def read_quality_source(db, tenant, workspace, actor, kind, identity, expected_version=None, expected_hash=None):
    if kind not in SOURCES:
        raise HTTPException(422, detail={"code": "QUALITY_CONSUMER_SOURCE_TYPE_INVALID"})
    quality = QualityExecutionService(db, tenant, actor, None)
    quality._project(workspace)
    row = quality._get(SOURCES[kind], workspace, identity)
    quality._execution_integrity(row)
    if (
        expected_version is not None
        and row.version != expected_version
        or expected_hash is not None
        and row.source_hash != expected_hash
    ):
        quality._error(409, "QUALITY_CONSUMER_SOURCE_PIN_CHANGED")
    state = "CURRENT"
    if kind == "ACCEPTANCE":
        state = quality.acceptance_state(workspace, row)
    elif kind == "READINESS":
        current = quality.readiness(workspace, row.itp_id, row.subject_reference)
        if current["basis_hash"] != row.snapshot_json["basis_hash"] or current["state"] != row.readiness_state:
            state = "BROKEN_REFERENCE" if current["state"] == "BROKEN_REFERENCE" else "STALE"
        newer = db.scalar(
            quality._scoped(QualityReadinessAssessment, workspace)
            .where(
                QualityReadinessAssessment.itp_id == row.itp_id,
                QualityReadinessAssessment.subject_key == row.subject_key,
                QualityReadinessAssessment.version > row.version,
            )
            .limit(1)
        )
        if newer:
            state = "SUPERSEDED"
    elif kind in {"INSPECTION", "TEST"} and row.status != "CLOSED":
        quality._error(409, "QUALITY_CONSUMER_CLOSED_RESULT_REQUIRED")
    elif kind == "NCR" and row.status == "DRAFT":
        quality._error(409, "QUALITY_CONSUMER_ISSUED_NCR_REQUIRED")
    if kind in {"NCR", "INSPECTION", "TEST"}:
        try:
            quality._source_current(workspace, row.subject_reference)
            documents = row.document_references if hasattr(row, "document_references") else [row.document_reference]
            for document in documents:
                quality._check_document(workspace, document)
            if getattr(row, "engineering_reference", None):
                quality._source_current(workspace, row.engineering_reference)
        except HTTPException as error:
            if error.status_code not in {403, 404, 409, 422}:
                raise
            state = "BROKEN_REFERENCE" if error.status_code == 404 else "STALE"
    root = row
    if kind == "READINESS":
        root = db.scalar(
            quality._scoped(QualityReadinessAssessment, workspace)
            .where(
                QualityReadinessAssessment.itp_id == row.itp_id,
                QualityReadinessAssessment.subject_key == row.subject_key,
            )
            .order_by(QualityReadinessAssessment.version, QualityReadinessAssessment.id)
            .limit(1)
        )
    seen = set()
    while getattr(root, "supersedes_id", None):
        if root.id in seen:
            quality._error(409, "QUALITY_CONSUMER_LINEAGE_CYCLE")
        seen.add(root.id)
        root = quality._get(type(row), workspace, root.supersedes_id)
    observed = (
        getattr(row, "effective_at", None)
        or getattr(row, "closed_at", None)
        or getattr(row, "detected_at", None)
        or row.created_at
    )
    facts = quality._out(row)
    # State is live metadata; a source hash always identifies the stored immutable/versioned fact.
    facts.pop("source_state", None)
    return _json(
        {
            "source_domain": "QUALITY",
            "source_entity_type": kind,
            "source_entity_id": row.id,
            "source_root_id": root.id,
            "source_version": row.version,
            "source_hash": row.source_hash,
            "observed_at": observed.replace(tzinfo=UTC).isoformat(),
            "source_state": state,
            "subject_key": row.subject_key,
            "facts": facts,
        }
    )


def _decisions(owner, workspace, consumer, linked_type, linked_id):
    if not inspect(owner.db.connection()).has_table(QualityConsumerDecision.__tablename__):
        return []
    rows = list(
        owner.db.scalars(
            select(QualityConsumerDecision)
            .where(
                QualityConsumerDecision.tenant_id == owner.tenant_id,
                QualityConsumerDecision.project_workspace_id == workspace,
                QualityConsumerDecision.consumer == consumer,
                QualityConsumerDecision.linked_entity_type == linked_type,
                QualityConsumerDecision.linked_entity_id == linked_id,
            )
            .order_by(QualityConsumerDecision.id)
        )
    )
    latest = {}
    for row in rows:
        latest[(row.source_entity_type, row.source_root_id)] = row
    return list(latest.values())


def progress_quality_gate(owner, workspace, measurement, *, required=False):
    decisions = _decisions(owner, workspace, "PROGRESS", "ProgressMeasurement", measurement.id)
    active = [row for row in decisions if row.decision in {"ADOPT", "RECONCILE"}]
    if required and not active:
        owner._error(409, "PROGRESS_QUALITY_ACCEPTANCE_REQUIRED")
    for row in active:
        source = read_quality_source(
            owner.db,
            owner.tenant_id,
            workspace,
            owner.actor_id,
            row.source_entity_type,
            row.source_entity_id,
            row.source_version,
            row.source_hash,
        )
        if (
            source["source_state"] != "CURRENT"
            or source != row.source_snapshot
            or row.source_root_id != source["source_root_id"]
            or row.subject_key != source["subject_key"]
        ):
            owner._error(409, "PROGRESS_QUALITY_EVIDENCE_REQUIRES_RECONCILIATION")
        validate_progress_binding(owner, measurement, source)
    if active:
        _progress_quantity_coverage(owner, workspace, measurement, active)
    return active


def _progress_quantity_coverage(owner, workspace, measurement, active):
    """Cover native Field reservations, not pre-existing cumulative Progress.

    The Field ledger is append-only and creates one native draft/successor per
    adoption. Quality never creates, changes or reserves an additional quantity.
    Exact source pins keep surplus on one production from covering another.
    """

    def invalid():
        owner._error(409, "PROGRESS_QUALITY_GRANULAR_COVERAGE_INCOMPLETE")

    def number(value):
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            invalid()
        if not result.is_finite():
            invalid()
        return result

    def pin_key(pin, *, quality=False):
        kind = pin.get("source_type" if quality else "source_entity_type")
        if kind != ("FIELD_PRODUCTION" if quality else "PRODUCTION"):
            invalid()
        fields = (
            ("source_id", "source_version", "source_hash")
            if quality
            else ("source_entity_id", "source_version", "source_hash")
        )
        values = tuple(pin.get(name) for name in fields)
        if any(value is None for value in values):
            invalid()
        return values

    field = measurement.source_snapshot.get("field_operations", [])
    pins = field if isinstance(field, list) else [field]
    if not pins or any(not isinstance(pin, dict) for pin in pins):
        invalid()
    retained = {pin_key(pin) for pin in pins}
    lineage, current = {}, measurement
    while current is not None:
        if current.id in lineage:
            owner._error(409, "PROGRESS_QUALITY_NATIVE_LINEAGE_CYCLE")
        if (
            current.subject_key != measurement.subject_key
            or current.scope_item_id != measurement.scope_item_id
            or current.unit != measurement.unit
        ):
            invalid()
        lineage[current.id] = current
        current = owner._get(ProgressMeasurement, workspace, current.supersedes_id) if current.supersedes_id else None
    reservations = list(
        owner.db.scalars(
            select(FieldConsumerDecision).where(
                FieldConsumerDecision.tenant_id == owner.tenant_id,
                FieldConsumerDecision.project_workspace_id == workspace,
                FieldConsumerDecision.consumer == "PROGRESS",
                FieldConsumerDecision.source_entity_type == "PRODUCTION",
                FieldConsumerDecision.linked_entity_type == "ProgressMeasurement",
                FieldConsumerDecision.linked_entity_id.in_(lineage),
                FieldConsumerDecision.decision.in_(("ADOPT", "PARTIAL_ADOPT")),
            )
        )
    )
    required, current_quantity = {}, Decimal(0)
    for row in reservations:
        key = (row.source_entity_id, row.source_version, row.source_hash)
        if key not in retained:
            invalid()
        quantity = number(row.quantity)
        if quantity <= 0 or row.uom != measurement.unit:
            invalid()
        required[key] = required.get(key, Decimal(0)) + quantity
        if row.linked_entity_id == measurement.id:
            current_quantity += quantity
    if set(required) != retained or current_quantity <= 0:
        invalid()
    input_quantity = number(measurement.input_json.get("numerator"))
    mode = measurement.input_json.get("input_mode")
    if mode == "CUMULATIVE":
        predecessor = lineage.get(measurement.supersedes_id)
        if (
            predecessor is None
            or input_quantity != number(predecessor.numerator) + current_quantity
            or number(measurement.numerator) != input_quantity
        ):
            invalid()
    elif mode == "PERIOD_DELTA":
        if input_quantity != current_quantity:
            invalid()
        previous_pin = measurement.source_snapshot.get("previous_measurement")
        previous_quantity = Decimal(0)
        if previous_pin:
            previous = owner._get(ProgressMeasurement, workspace, previous_pin["id"])
            if (
                previous.content_hash != previous_pin["content_hash"]
                or previous.subject_key != measurement.subject_key
                or previous.unit != measurement.unit
            ):
                invalid()
            previous_quantity = number(previous.numerator)
        if number(measurement.numerator) != previous_quantity + current_quantity:
            invalid()
    else:
        invalid()
    accepted = {}
    for row in active:
        facts = row.source_snapshot["facts"]
        key = pin_key(facts["subject_reference"], quality=True)
        quantity = number(facts["quantity"])
        if key not in retained or quantity <= 0 or facts["uom"] != measurement.unit:
            invalid()
        # Multiple ITP acceptances for the same indivisible source are not
        # independent production portions. Do not double-count their quantities.
        accepted[key] = max(accepted.get(key, Decimal(0)), quantity)
    if any(accepted.get(key, Decimal(0)) < quantity for key, quantity in required.items()):
        invalid()


def validate_progress_binding(owner, measurement, source):
    facts = source["facts"]
    subject = facts["subject_reference"]
    field = measurement.source_snapshot.get("field_operations", [])
    pins = field if isinstance(field, list) else [field]
    if subject["source_type"] != "FIELD_PRODUCTION" or not any(
        pin
        and pin["source_entity_type"] == "PRODUCTION"
        and pin["source_entity_id"] == subject["source_id"]
        and pin["source_version"] == subject["source_version"]
        and pin["source_hash"] == subject["source_hash"]
        for pin in pins
    ):
        owner._error(409, "QUALITY_PROGRESS_EXACT_PRODUCTION_PIN_REQUIRED")
    if measurement.scope_item_id != subject["facts"].get("scope_item_id") or measurement.unit != facts["uom"]:
        owner._error(422, "QUALITY_PROGRESS_GRANULAR_QUANTITY_UOM_MISMATCH")


def awp_quality_evidence(owner, workspace, package, as_of=None):
    rows = _decisions(owner, workspace, "AWP", "WorkPackage", package.id)
    if not rows:
        return None
    # Each subject needs its own current adopted evidence; one passed lot cannot cover another.
    active = [row for row in rows if row.decision in {"ADOPT", "RECONCILE"}]
    state, material = "READY" if active and all(row.decision != "REJECT" for row in rows) else "NOT_READY", []
    for row in active:
        try:
            source = read_quality_source(
                owner.db,
                owner.tenant_id,
                workspace,
                owner.actor_id,
                row.source_entity_type,
                row.source_entity_id,
                row.source_version,
                row.source_hash,
            )
            valid = source["source_state"] == "CURRENT" and source == row.source_snapshot
            if as_of and (
                row.created_at > owner._instant(as_of)
                or source["observed_at"] > owner._instant(as_of).replace(tzinfo=UTC).isoformat()
            ):
                valid = False
            if row.source_entity_type == "READINESS":
                valid = valid and source["facts"]["readiness_state"] == "READY"
            elif row.source_entity_type != "ACCEPTANCE":
                valid = False
            state = state if valid else "NOT_READY"
            material.append({"decision": row.id, "version": row.version, "source": source})
        except HTTPException as error:
            if error.status_code not in {403, 404, 409, 422}:
                raise
            state = "NOT_READY"
            material.append({"decision": row.id, "source_state": "BROKEN_OR_STALE"})
    material.extend({"decision": row.id, "rejected": True} for row in rows if row.decision == "REJECT")
    return {
        "state": state,
        "evidence_hash": _hash(material),
        "decisions": material,
        "authority": "AWP_EXPLICIT_QUALITY_EVIDENCE_NOT_RELEASE",
    }


def apply_awp_quality(result, provider):
    if provider is None:
        return result
    result = {
        **result,
        "dimensions": dict(result["dimensions"]),
        "evidence_state": dict(result["evidence_state"]),
    }
    result["evidence_state"]["quality_provider"] = provider
    dimension = dict(result["dimensions"]["QUALITY"])
    dimension["state"] = "READY" if provider["state"] == "READY" and not dimension["blocking_ids"] else "BLOCKED"
    result["dimensions"]["QUALITY"] = dimension
    missing = list(result["evidence_state"]["missing_dimensions"])
    if dimension["state"] == "READY":
        missing = [item for item in missing if item != "QUALITY"]
        if result["readiness_state"] == "PARTIALLY_READY" and not missing:
            result["readiness_state"] = "READY"
    else:
        if "QUALITY" not in missing:
            missing.append("QUALITY")
        result["readiness_state"] = "NOT_READY"
    result["evidence_state"]["missing_dimensions"] = missing
    return result
