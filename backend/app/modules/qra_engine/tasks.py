"""Celery reuses the existing control-core queue and database claim semantics."""

from sqlalchemy import select

from app.database.session import SessionLocal
from app.modules.qra_engine.models import QraRun
from app.modules.qra_engine.service import QraEngineService
from app.workers.celery_app import celery_app


@celery_app.task(
    name="app.modules.qra_engine.tasks.execute_qra_run",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=3540,
    time_limit=3600,
)
def execute_qra_run(self, tenant_id: int, run_id: int):
    with SessionLocal() as db:
        row = db.scalar(select(QraRun).where(QraRun.tenant_id == tenant_id, QraRun.id == run_id))
        if row is None:
            return {"run_id": run_id, "status": "NOT_FOUND", "claimed": False}
        service = QraEngineService(db, tenant_id, row.execution_actor or row.created_by)
        return service.worker_execute(run_id, self.request.id)


@celery_app.task(name="app.modules.qra_engine.tasks.recover_qra_workers")
def recover_qra_workers():
    """Fail crashed historical attempts; a governed new run is required."""
    with SessionLocal() as db:
        candidates = db.execute(
            select(QraRun.tenant_id, QraRun.execution_actor)
            .where(QraRun.status.in_(["VALIDATING", "RUNNING"]))
            .distinct()
        ).all()
        failed = []
        for tenant_id, actor_id in candidates:
            failed.extend(QraEngineService(db, tenant_id, actor_id).recover_expired_workers()["failed_run_ids"])
        return {"failed_run_ids": failed}
