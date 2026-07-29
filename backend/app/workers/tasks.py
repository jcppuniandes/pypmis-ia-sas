from datetime import UTC, datetime

from app.database.session import SessionLocal
from app.domain.models import Project
from app.services.control_core import ControlCoreService
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.run_control_cycle")
def run_control_cycle(tenant_id: int, project_id: int) -> int:
    db = SessionLocal()
    try:
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
def run_daily_control_core(self) -> dict:  # type: ignore[override]
    db = SessionLocal()
    results: list[dict] = []
    try:
        service = ControlCoreService(db)
        projects = db.query(Project).all()
        for project in projects:
            try:
                kpi = service.run_project_cycle(project.tenant_id, project.id)
                results.append({"project_id": project.id, "kpi_id": kpi.id, "status": "ok"})
            except Exception as exc:  # noqa: BLE001 — report all failures, don't abort the batch
                results.append({"project_id": project.id, "status": "error", "error": str(exc)})
    finally:
        db.close()
    return {"processed": len(results), "results": results}
