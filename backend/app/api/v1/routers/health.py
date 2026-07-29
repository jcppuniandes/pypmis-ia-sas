"""Health, readiness, liveness, and metrics endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import PlainTextResponse
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.observability import METRICS
from app.database.session import get_db

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
def liveness() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "live",
        "environment": settings.app_environment,
        "version": settings.app_version,
        "commit": settings.commit_sha,
        "uptime_seconds": METRICS.snapshot()["uptime_seconds"],
    }


@router.get("/health/ready")
def readiness(db: Session = Depends(get_db)) -> dict[str, object]:
    checks: dict[str, object] = {"api": "ok"}
    latency: dict[str, float] = {}

    t0 = time.monotonic()
    try:
        db.execute(text("SELECT 1")).scalar_one()
        checks["database"] = "ok"
    except SQLAlchemyError:
        checks["database"] = "error"
    latency["database_ms"] = round((time.monotonic() - t0) * 1000, 1)

    t0 = time.monotonic()
    try:
        redis = Redis.from_url(get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1)
        redis.ping()
        checks["redis"] = "ok"
    except RedisError:
        checks["redis"] = "error"
    latency["redis_ms"] = round((time.monotonic() - t0) * 1000, 1)

    status = "ready" if all(v == "ok" for v in checks.values()) else "degraded"
    if status != "ready":
        raise HTTPException(status_code=503, detail={"status": status, "checks": checks, "latency": latency})
    settings = get_settings()
    return {
        "status": status,
        "checks": checks,
        "latency": latency,
        "environment": settings.app_environment,
        "version": settings.app_version,
        "commit": settings.commit_sha,
    }


@router.get("/ops/metrics", response_class=PlainTextResponse)
def metrics(x_metrics_token: str = Header(default="", alias="X-Metrics-Token")) -> PlainTextResponse:
    settings = get_settings()
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Metrics endpoint disabled")
    if settings.metrics_token and not x_metrics_token:
        raise HTTPException(status_code=401, detail="Metrics token is required")
    if settings.metrics_token and x_metrics_token != settings.metrics_token:
        raise HTTPException(status_code=403, detail="Invalid metrics token")
    payload = METRICS.prometheus(settings.app_name, settings.app_environment, settings.app_version)
    return PlainTextResponse(payload, media_type="text/plain; version=0.0.4")
