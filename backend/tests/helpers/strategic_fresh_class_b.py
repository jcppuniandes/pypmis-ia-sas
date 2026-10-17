"""Representative, explicitly non-production controlled Class B UAT references.

Documents are immutable files, not fabricated provider records.  The normal
Gate evidence commands remain the only authority for submission and validation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.core.time import utc_now
from app.modules.investment_gate_preparation.schemas import EvidenceValidationIn, ManualEvidenceIn

CONTROLLED_REFERENCES = (
    ("permit-readiness", "PERMIT_READINESS", 180, "Representative permit readiness dossier"),
    (
        "contracting-strategy-readiness",
        "CONTRACTING_STRATEGY_READINESS",
        365,
        "Representative contracting strategy review package",
    ),
    ("execution-plan-readiness", "EXECUTION_PLAN_READINESS", 365, "Representative Project Execution Plan"),
    ("schedule-maturity", "SCHEDULE_MATURITY", 180, "Representative schedule maturity assessment"),
)


def _key(action: str) -> str:
    return f"controlled-class-b-{action}-{uuid4().hex}"


def effective_requirement(preparation, requirement_key: str, project_id: int) -> dict:
    snapshot = preparation.source_snapshot.get("evidence_policy") or {}
    requirement = next(item for item in snapshot["requirements"] if item["requirement_key"] == requirement_key)
    return {**requirement, **requirement.get("resolved_projects", {}).get(str(project_id), {})}


def controlled_document_payload(
    artifact_root: Path,
    setup: dict,
    preparation,
    specification: tuple,
    *,
    supporting_source: dict | None = None,
    as_of: datetime | None = None,
) -> tuple[ManualEvidenceIn, dict]:
    """Create once, or verify and reuse, the same representative UAT document.

    Execution/schedule references describe test review criteria explicitly;
    they never claim to be an approved operating plan, P6 model or certificate.
    Permit/commercial source snapshots are supporting material only, not an
    automatic substitute for the separate independent Gate evidence review.
    """
    requirement_key, evidence_type, days, title = specification
    project_id = setup["project_id"]
    assert preparation.tenant_id == setup["tenant_id"]
    assert preparation.portfolio_workspace_id == setup["portfolio_id"]
    assert preparation.source_snapshot["selected_project_ids"] == [project_id]
    requirement = effective_requirement(preparation, requirement_key, project_id)
    assert requirement["classification"] == "B" and requirement["provider_key"] is None
    assert requirement["scope"] == "EACH_PROJECT" and requirement["coverage_requirement"] == 100
    assert requirement["allow_manual_reference"] and requirement["manual_validation_required"]
    assert requirement["validity_period_days"] == days
    root = artifact_root.resolve()
    destination = (root / "controlled-class-b" / f"tenant-{setup['tenant_id']}" / f"project-{project_id}").resolve()
    assert destination.is_relative_to(root) and destination != root
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"preparation-{preparation.id}-{requirement_key}-r1.json"
    as_of = as_of or utc_now()
    assert as_of <= utc_now(), "Future-dated evidence is prohibited"
    reference_id = f"UAT-T{setup['tenant_id']}-P{project_id}-G{preparation.id}-{requirement_key}-R1"
    if path.exists():
        document_bytes = path.read_bytes()
        document = json.loads(document_bytes)
        assert document["reference_id"] == reference_id
        assert document["tenant_id"] == setup["tenant_id"] and document["project_id"] == project_id
        assert document["scope_reference_hash"] == preparation.recommended_project_set_hash
        assert document["supporting_governed_source"] == supporting_source
        as_of = datetime.fromisoformat(document["as_of"])
        assert as_of <= utc_now(), "Future-dated evidence is prohibited"
    else:
        document = {
            "classification_label": "UAT CONTROLLED EVIDENCE",
            "representative_only": True,
            "not_a_real_permit_contract_approved_plan_or_schedule_certificate": True,
            "reference_id": reference_id,
            "title": f"UAT CONTROLLED EVIDENCE — {title}",
            "revision": "1",
            "tenant_id": setup["tenant_id"],
            "tenant_slug": setup["tenant_slug"],
            "project_id": project_id,
            "portfolio_id": setup["portfolio_id"],
            "requirement_key": requirement_key,
            "evidence_type": evidence_type,
            "scope_type": "EACH_PROJECT",
            "scope_reference_hash": preparation.recommended_project_set_hash,
            "as_of": as_of.isoformat(),
            "valid_until": (as_of + timedelta(days=days)).isoformat(),
            "owner": "UAT Capital Owner Governance",
            "issuer": "P&Pmis UAT representative evidence author",
            "author_user_id": setup["actor_id"],
            "intended_independent_reviewer_user_id": setup["reviewer_id"],
            "review_status_at_document_creation": "PRESENTED_FOR_INDEPENDENT_UAT_VALIDATION",
            "test_scope": {
                "covered_project_ids": [project_id],
                "purpose": "Test controlled-reference submission, independent review, validity, coverage and freeze",
                "acceptance_checks": [
                    "Verify this exact tenant, Project, revision and immutable document SHA-256",
                    "Verify EACH_PROJECT project-set hash and published policy validity",
                    "Verify supporting material without treating it as automatic Gate validation",
                    "Record independent reviewer decision via the existing Gate evidence command",
                ],
                "execution_plan_test_content": {
                    "delivery_scope": "Representative USD100M capital expansion; strategic readiness UAT only",
                    "workstreams": ["engineering definition", "procurement preparation", "construction preparation"],
                    "controls": ["stage review", "change governance", "interface responsibility", "handover planning"],
                    "not_authorization_for_project_delivery": True,
                }
                if evidence_type == "EXECUTION_PLAN_READINESS"
                else None,
                "schedule_maturity_test_content": {
                    "schedule_reference": f"UAT-P{project_id}-SCHEDULE-REPRESENTATION-R1",
                    "data_date": as_of.date().isoformat(),
                    "assessment_dimensions": [
                        "scope coverage",
                        "logic review",
                        "milestone definition",
                        "risk interfaces",
                    ],
                    "review_authority": "Independent UAT investment evidence reviewer",
                    "not_a_cpm_or_p6_assurance_certificate": True,
                }
                if evidence_type == "SCHEDULE_MATURITY"
                else None,
            },
            "supporting_governed_source": supporting_source,
        }
        document_bytes = (
            json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False, default=str) + "\n"
        ).encode("utf-8")
        # Exclusive creation makes retry history immutable rather than silently
        # replacing a reference with newer source content under the same ID.
        with path.open("xb") as stream:
            stream.write(document_bytes)
    assert as_of <= utc_now(), "Future-dated evidence is prohibited"
    digest = hashlib.sha256(document_bytes).hexdigest()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    document_ref = {
        "classification_label": "UAT CONTROLLED EVIDENCE",
        "representative_only": True,
        "reference_id": reference_id,
        "document_uri": f"artifact://{path.relative_to(root).as_posix()}",
        "document_sha256": digest,
        "evidence_hash": digest,
        "title": document["title"],
        "revision": "1",
        "version": "1",
        "as_of_date": document["as_of"],
        "project_id": project_id,
        "scope_reference_hash": preparation.recommended_project_set_hash,
        "source_current": True,  # Exact immutable reference was rehashed above.
        "owner": document["owner"],
    }
    return (
        ManualEvidenceIn(
            requirement_key=requirement_key,
            scope_type="EACH_PROJECT",
            scope_id=project_id,
            reference_id=reference_id,
            evidence_date=as_of,
            valid_until=datetime.fromisoformat(document["valid_until"]),
            issuer=document["issuer"],
            owner=document["owner"],
            summary=(
                f"UAT CONTROLLED EVIDENCE — {title}, revision 1. Representative test reference only; "
                "not a real permit, contract, approved execution plan or schedule certificate."
            ),
            evidence_refs=[document_ref],
            scope_reference_hash=preparation.recommended_project_set_hash,
            idempotency_key=_key(f"submit-{requirement_key}"),
        ),
        document_ref,
    )


def complete_controlled_references(
    preparer, validator, preparation, setup, artifact_root, supporting_sources, checkpoint
):
    """Execute existing add/independent validate commands; never seed final states."""
    assert preparer.actor_id == setup["actor_id"] and validator.actor_id == setup["reviewer_id"]
    assert preparer.actor_id != validator.actor_id
    policy_before = json.dumps(preparation.source_snapshot["evidence_policy"], sort_keys=True, default=str)
    for specification in CONTROLLED_REFERENCES:
        requirement_key = specification[0]
        item = next(
            item
            for item in preparation.evidence
            if item.requirement_key == requirement_key and item.scope_id == setup["project_id"]
        )
        payload, document_ref = controlled_document_payload(
            artifact_root, setup, preparation, specification, supporting_source=supporting_sources.get(requirement_key)
        )
        if item.status == "VALID":
            assert item.source_record_id == payload.reference_id
            assert item.evidence_refs == payload.evidence_refs
            assert item.submitted_by == preparer.actor_id and item.validated_by == validator.actor_id
        else:
            if item.status != "SUBMITTED":
                preparation = preparer.add_evidence(preparation.id, preparation.revision_version, payload)
                item = next(value for value in preparation.evidence if value.id == item.id)
            assert item.status == "SUBMITTED" and item.submitted_by == preparer.actor_id
            assert item.evidence_refs == payload.evidence_refs and item.validated_by is None
            checkpoint(
                f"CLASS_B_SUBMITTED_{requirement_key}",
                {"reference": document_ref, "evidence": item.model_dump(mode="json")},
            )
            preparation = validator.validate_evidence(
                item.id,
                preparation.revision_version,
                EvidenceValidationIn(
                    decision="VALID",
                    validation_note=(
                        "Independent UAT review: verified exact document SHA-256, representative-only label, "
                        "Project scope, policy validity and supporting source. Not a real-world approval."
                    ),
                    idempotency_key=_key(f"validate-{requirement_key}"),
                ),
            )
            item = next(value for value in preparation.evidence if value.id == item.id)
        assert item.status == "VALID", item.model_dump(mode="json")
        assert item.classification == "B" and item.provider_key is None
        assert item.submitted_by != item.validated_by and item.validated_at is not None
        assert item.source_hash and item.scope_reference_hash == preparation.recommended_project_set_hash
        checkpoint(
            f"CLASS_B_VALIDATED_{requirement_key}",
            {"reference": document_ref, "evidence": item.model_dump(mode="json")},
        )
    assert json.dumps(preparation.source_snapshot["evidence_policy"], sort_keys=True, default=str) == policy_before
    return preparation


def reconcile_requirements(preparation) -> list[dict]:
    """Report every captured row, including non-blocking omissions, without averaging."""
    rows = []
    for item in preparation.evidence:
        requirement = effective_requirement(preparation, item.requirement_key, item.scope_id)
        rows.append(
            {
                "requirement_key": item.requirement_key,
                "evidence_type": item.evidence_type,
                "classification": item.classification,
                "required": bool(requirement.get("required")),
                "provider_key": item.provider_key,
                "evidence_origin": item.evidence_origin,
                "status": item.status,
                "resolution_status": item.resolution_status,
                "source_current": item.source_current,
                "scope_type": item.scope_type,
                "scope_id": item.scope_id,
                "coverage_requirement": item.coverage_requirement,
                "coverage_percent": 100 if item.status in {"VALID", "NOT_REQUIRED"} else 0,
                "blocking": item.blocking,
                "blockers": item.blockers,
                "warnings": item.warnings,
                "source_record_id": item.source_record_id,
                "source_hash": item.source_hash,
                "valid_until": item.valid_until.isoformat() if item.valid_until else None,
                "submitted_by": item.submitted_by,
                "validated_by": item.validated_by,
            }
        )
    return rows
