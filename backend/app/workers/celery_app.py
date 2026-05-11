from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "pypmis",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_default_queue="control-core",
    task_routes={"app.workers.tasks.*": {"queue": "control-core"}},
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    # Daily Control Core snapshot across every project at 11:00 UTC (06:00 Bogotá).
    "daily-control-core-all-projects": {
        "task": "app.workers.tasks.run_daily_control_core",
        "schedule": crontab(hour=11, minute=0),
    },
    # Worker heartbeat every 5 minutes for monitoring/liveness.
    "worker-heartbeat": {
        "task": "app.workers.tasks.heartbeat",
        "schedule": crontab(minute="*/5"),
    },
}
