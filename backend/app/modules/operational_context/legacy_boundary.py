"""HTTP compatibility boundary for existing legacy Project material commands.

Only the inventoried legacy routers are included. Strategic routes sometimes use
the same parameter name but are canonical and must not cross this adapter.
Existing query handlers retain their characterized behavior.
"""

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.api.v1._helpers import require_membership
from app.database.session import get_db
from app.modules.operational_context.service import guard_legacy_operational_write

LEGACY_MODULES = frozenset(
    {"app.api.v1.router", "app.api.v1.routers.projects", "app.api.v1.routers.documents", "app.api.v1.routers.rfq"}
)
MATERIAL_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def require_bound_legacy_command(request: Request, db: Session = Depends(get_db)) -> None:
    endpoint = request.scope.get("endpoint")
    if request.method not in MATERIAL_METHODS or getattr(endpoint, "__module__", "") not in LEGACY_MODULES:
        return
    project_id = request.path_params.get("project_id")
    if project_id is None:
        # Explicit legacy creation has no operational context yet. It remains a
        # compatibility creation path, not canonical Project activation.
        return
    principal = get_current_principal(authorization=request.headers.get("authorization", ""), db=db)
    legacy_id = int(project_id)
    require_membership(db, principal.tenant_id, legacy_id, principal.user_id)
    request.state.operational_project_context = guard_legacy_operational_write(
        db, principal.tenant_id, principal.user_id, legacy_id
    )
    from app.modules.cost_foundation.legacy_boundary import guard_legacy_cost_write

    guard_legacy_cost_write(db, principal.tenant_id, legacy_id, getattr(endpoint, "__name__", ""))
