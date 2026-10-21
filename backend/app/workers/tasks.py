from datetime import UTC, datetime

from fastapi import HTTPException

from app.database.session import SessionLocal
from app.domain.models import Project
from app.services.control_core import ControlCoreService
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.run_control_cycle")
def run_control_cycle(tenant_id: int, project_id: int, actor_id: int | None = None) -> int:
    if actor_id is None:
        raise HTTPException(403, detail={"code": "OPERATIONAL_EXECUTION_ACTOR_REQUIRED"})
    db = SessionLocal()
    try:
        from app.modules.operational_context.service import guard_legacy_operational_write

        guard_legacy_operational_write(db, tenant_id, actor_id, project_id)
        kpi = ControlCoreService(db).run_project_cycle(tenant_id, project_id)
        return kpi.id
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.heartbeat")
def heartbeat() -> dict[str, str]:
    return {"status": "alive", "timestamp": datetime.now(UTC).isoformat()}


@celery_app.task(
    name="app.workers.tasks.run_daily_control_core",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def run_daily_control_core(self, tenant_id: int | None = None, actor_id: int | None = None) -> dict:  # type: ignore[override]
    if tenant_id is None or actor_id is None:
        # Explicit scoped actor required; never fabricate a service principal.
        return {
            "processed": 0,
            "results": [],
            "status": "skipped",
            "reason_code": "OPERATIONAL_EXECUTION_ACTOR_REQUIRED",
        }
    db = SessionLocal()
    results: list[dict] = []
    try:
        service = ControlCoreService(db)
        from app.modules.operational_context.service import guard_legacy_operational_write

        projects = db.query(Project).filter(Project.tenant_id == tenant_id).all()
        for project in projects:
            try:
                guard_legacy_operational_write(db, project.tenant_id, actor_id, project.id)
                kpi = service.run_project_cycle(project.tenant_id, project.id)
                results.append({"project_id": project.id, "kpi_id": kpi.id, "status": "ok"})
            except HTTPException as exc:
                db.rollback()
                detail = exc.detail if isinstance(exc.detail, dict) else {"code": "OPERATIONAL_CONTEXT_DENIED"}
                results.append({"project_id": project.id, "status": "skipped", "reason_code": detail.get("code")})
            except Exception as exc:  # noqa: BLE001 — report all failures, don't abort the batch
                db.rollback()
                results.append(
                    {
                        "project_id": project.id,
                        "status": "error",
                        "reason_code": "OPERATIONAL_CONTROL_CYCLE_FAILED",
                        "error_type": type(exc).__name__,
                    }
                )
    finally:
        db.close()
    return {"processed": len(results), "results": results}
