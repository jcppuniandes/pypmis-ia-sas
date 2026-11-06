"""Legacy input/calculations remain candidate-only after explicit Progress adoption."""

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.modules.operational_context.models import OperationalProjectBinding

PROGRESS_WRITERS = frozenset(
    {
        "create_progress_record",
        "create_work_package",
        "update_work_package_readiness",
        "create_control_account",
        "update_control_account",
        "approve_integrated_baseline",
        "run_control_cycle",
        "enqueue_control_cycle",
    }
)


def canonical_progress_project(db, tenant_id, legacy_project_id):
    if not inspect(db.get_bind()).has_table("progress_history"):
        return None
    from app.modules.progress_foundation.models import ProgressHistory

    binding = db.scalar(
        select(OperationalProjectBinding).where(
            OperationalProjectBinding.tenant_id == tenant_id,
            OperationalProjectBinding.legacy_project_id == legacy_project_id,
            OperationalProjectBinding.status == "ACTIVE",
        )
    )
    if (
        binding is not None
        and db.scalar(
            select(ProgressHistory.id)
            .where(
                ProgressHistory.tenant_id == tenant_id,
                ProgressHistory.project_workspace_id == binding.project_workspace_id,
            )
            .limit(1)
        )
        is not None
    ):
        return binding.project_workspace_id
    return None


def guard_legacy_progress_write(db, tenant_id, legacy_project_id, endpoint_name):
    if endpoint_name not in PROGRESS_WRITERS:
        return
    workspace_id = canonical_progress_project(db, tenant_id, legacy_project_id)
    if workspace_id is not None:
        raise HTTPException(
            409,
            detail={
                "code": "CANONICAL_PROGRESS_AUTHORITY_REQUIRED",
                "project_workspace_id": workspace_id,
                "candidate_only": True,
                "progress_api": f"/api/v1/progress/projects/{workspace_id}",
            },
        )
