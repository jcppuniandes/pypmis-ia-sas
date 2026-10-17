"""Read-only exact closed links from completed source domains to their BC.

A later Business Case revision may consume an already approved source version.
That exact reverse link is not a change to the source domain's approved inputs.
Every other captured input remains subject to its ordinary freshness comparison.
"""

from __future__ import annotations

from sqlalchemy import select

from app.modules.business_case.models import BusinessCase, BusinessCaseRevision


def current_bundle_matches_completed_case_link(
    db,
    *,
    tenant_id: int,
    project_id: int,
    source_key: str,
    aggregate_id: int,
    version_id: int,
    version_number: int,
    source_hash: str,
    source_status: str,
    captured_references: dict,
    captured_hashes: dict,
    current_hashes: dict,
) -> bool:
    """Allow only a BC-backreference delta with a completed exact consumer.

    This is not a freshness opt-out: the original BC identity, tenant, Project,
    completed/READY review state and consumed source ID/version/hash must all
    agree. Draft consumers and unrelated material input changes remain stale.
    No record or historical hash is mutated.
    """
    if captured_hashes == current_hashes:
        return True
    if source_status != "COMPLETED" or not source_hash or not captured_hashes.get("business_case"):
        return False
    captured_other = {key: value for key, value in captured_hashes.items() if key != "business_case"}
    current_other = {key: value for key, value in current_hashes.items() if key != "business_case"}
    if captured_other != current_other or not current_hashes.get("business_case"):
        return False
    captured_case = captured_references.get("business_case") or {}
    if not isinstance(captured_case, dict) or type(captured_case.get("id")) is not int or captured_case["id"] <= 0:
        return False
    record = db.execute(
        select(BusinessCase, BusinessCaseRevision)
        .join(
            BusinessCaseRevision,
            (BusinessCaseRevision.id == BusinessCase.current_revision_id)
            & (BusinessCaseRevision.business_case_id == BusinessCase.id)
            & (BusinessCaseRevision.tenant_id == BusinessCase.tenant_id),
        )
        .where(
            BusinessCase.tenant_id == tenant_id,
            BusinessCase.project_workspace_id == project_id,
            BusinessCase.id == captured_case["id"],
            BusinessCaseRevision.status == "COMPLETED",
            BusinessCaseRevision.readiness_status == "READY",
        )
    ).first()
    if record is None:
        return False
    case, revision = record
    # Explicit assertions also keep the semantic predicate fail-closed when
    # exercised with an adapter or a transaction-local identity-map result.
    if not (
        case.tenant_id == tenant_id
        and case.project_workspace_id == project_id
        and case.id == captured_case["id"]
        and case.current_revision_id == revision.id
        and revision.tenant_id == tenant_id
        and revision.business_case_id == case.id
        and revision.status == "COMPLETED"
        and revision.readiness_status == "READY"
        and revision.content_hash == current_hashes["business_case"]
    ):
        return False
    references = revision.source_references_json or {}
    hashes = revision.source_hashes_json or {}
    if not isinstance(references, dict) or not isinstance(hashes, dict):
        return False
    reference = references.get(source_key) or {}
    return bool(
        isinstance(reference, dict)
        and all(type(reference.get(key)) is int for key in ("id", "version_id", "version"))
        and reference.get("id") == aggregate_id
        and reference.get("version_id") == version_id
        and reference.get("version") == version_number
        and reference.get("status") == "COMPLETED"
        and reference.get("readiness") == "READY"
        and reference.get("source_current") is True
        and hashes.get(source_key) == source_hash
    )
