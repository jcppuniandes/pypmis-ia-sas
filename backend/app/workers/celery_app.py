from celery import Celery

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
)
