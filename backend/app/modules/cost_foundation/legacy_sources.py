"""Read-only legacy Budget and APU candidate evidence, never canonical Cost writes."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.models import Budget, ColombiaApuCatalogItem
from app.modules.cost_foundation.service import CostFoundationService
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.operational_context.models import OperationalProjectBinding

router = APIRouter()


def legacy_candidates(service, workspace):
    service._permission("read", service._project(workspace))
    binding = service.db.scalar(
        select(OperationalProjectBinding).where(
            OperationalProjectBinding.tenant_id == service.tenant_id,
            OperationalProjectBinding.project_workspace_id == workspace,
            OperationalProjectBinding.status == "ACTIVE",
        )
    )
    result = {
        "authority": "CANDIDATE_ONLY_NOT_APPROVED_COST",
        "legacy_project_id": None,
        "budgets": [],
        "apu_catalog": [],
        "approval_automatic": False,
        "budget_currency": "REQUIRED_EXPLICIT_BASIS",
        "limit_per_source": 1000,
    }
    if binding is None:
        return result
    result["legacy_project_id"] = binding.legacy_project_id
    for key, model in (("budgets", Budget), ("apu_catalog", ColombiaApuCatalogItem)):
        rows = service.db.scalars(
            select(model)
            .where(
                model.tenant_id == service.tenant_id,
                model.project_id == binding.legacy_project_id,
            )
            .order_by(model.id)
            .limit(1000)
        ).all()
        result[key] = [service._out(row) for row in rows]
    return result


@router.get("/projects/{workspace_id}/legacy-candidates")
def read_legacy_candidates(
    workspace_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    actor_id: int = Depends(get_user_id),
):
    access = require_enterprise_permission(db, tenant_id, actor_id, "cost.read", bootstrap=False)
    return legacy_candidates(CostFoundationService(db, tenant_id, actor_id, access), workspace_id)
