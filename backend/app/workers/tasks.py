from app.database.session import SessionLocal
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
