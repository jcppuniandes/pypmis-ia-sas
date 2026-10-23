"""Legacy Cost remains a candidate source after canonical Cost is adopted.

An explicit Cost command is the adoption event; no GET or seed activates it.
Legacy identity is resolved through the existing O1A binding, never ID equality.
"""

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.modules.operational_context.models import OperationalProjectBinding

COST_WRITERS = frozenset(
    {
        "create_control_account",
        "update_control_account",
        "create_cost_record",
        "create_cbs",
        "create_cost_code",
        "create_cbs_wbs_business_process",
        "update_business_process_line_item",
        "recost_activity_sheet",
    }
)


def canonical_cost_project(db, tenant_id, legacy_project_id):
    # Older normal databases deliberately remain supported until an explicit rollout.
    if not inspect(db.get_bind()).has_table("cost_history"):
        return None
    from app.modules.cost_foundation.models import CostHistory

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
            select(CostHistory.id)
            .where(
                CostHistory.tenant_id == tenant_id,
                CostHistory.project_workspace_id == binding.project_workspace_id,
            )
            .limit(1)
        )
        is not None
    ):
        return binding.project_workspace_id
    return None


def guard_legacy_cost_write(db, tenant_id, legacy_project_id, endpoint_name):
    if endpoint_name not in COST_WRITERS:
        return
    workspace_id = canonical_cost_project(db, tenant_id, legacy_project_id)
    if workspace_id is not None:
        raise HTTPException(
            409,
            detail={
                "code": "CANONICAL_COST_AUTHORITY_REQUIRED",
                "project_workspace_id": workspace_id,
                "candidate_only": True,
                "cost_api": f"/api/v1/cost/projects/{workspace_id}",
            },
        )
