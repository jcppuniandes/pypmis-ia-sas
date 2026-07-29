import json
import logging
import time
import uuid
from collections import Counter, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from threading import Lock

from fastapi import Request, Response
from redis import Redis
from redis.exceptions import RedisError
from starlette.responses import JSONResponse

from app.core.config import get_settings

logger = logging.getLogger("pypmis.request")


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status_code", "duration_ms", "client_host"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


@dataclass
class RuntimeMetrics:
    started_at: float = field(default_factory=time.time)
    request_count: int = 0
    error_count: int = 0
    status_counts: Counter[str] = field(default_factory=Counter)
    path_counts: Counter[str] = field(default_factory=Counter)
    durations_ms: deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    lock: Lock = field(default_factory=Lock)

    def record(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        status_class = f"{status_code // 100}xx"
        route_key = _metric_route_key(method, path)
        with self.lock:
            self.request_count += 1
            if status_code >= 500:
                self.error_count += 1
            self.status_counts[status_class] += 1
            self.path_counts[route_key] += 1
            self.durations_ms.append(duration_ms)

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            durations = sorted(self.durations_ms)
            p95 = durations[int(len(durations) * 0.95) - 1] if durations else 0
            return {
                "uptime_seconds": round(time.time() - self.started_at, 3),
                "request_count": self.request_count,
                "error_count": self.error_count,
                "status_counts": dict(self.status_counts),
                "path_counts": dict(self.path_counts),
                "p95_duration_ms": round(p95, 3),
            }

    def prometheus(self, app_name: str, environment: str, version: str) -> str:
        snapshot = self.snapshot()
        lines = [
            "# HELP pypmis_app_info Application metadata.",
            "# TYPE pypmis_app_info gauge",
            f'pypmis_app_info{{app="{app_name}",environment="{environment}",version="{version}"}} 1',
            "# HELP pypmis_uptime_seconds Application uptime in seconds.",
            "# TYPE pypmis_uptime_seconds gauge",
            f"pypmis_uptime_seconds {snapshot['uptime_seconds']}",
            "# HELP pypmis_http_requests_total Total HTTP requests.",
            "# TYPE pypmis_http_requests_total counter",
            f"pypmis_http_requests_total {snapshot['request_count']}",
            "# HELP pypmis_http_errors_total Total HTTP 5xx responses.",
            "# TYPE pypmis_http_errors_total counter",
            f"pypmis_http_errors_total {snapshot['error_count']}",
            "# HELP pypmis_http_request_duration_p95_ms Last-window p95 request duration in ms.",
            "# TYPE pypmis_http_request_duration_p95_ms gauge",
            f"pypmis_http_request_duration_p95_ms {snapshot['p95_duration_ms']}",
        ]
        for status_class, count in sorted(snapshot["status_counts"].items()):
            lines.append(f'pypmis_http_requests_by_status_total{{status_class="{status_class}"}} {count}')
        for route, count in sorted(snapshot["path_counts"].items()):
            lines.append(f'pypmis_http_requests_by_route_total{{route="{route}"}} {count}')
        return "\n".join(lines) + "\n"


class RateLimiter:
    def __init__(self) -> None:
        self._local: dict[str, tuple[int, float]] = {}
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        settings = get_settings()
        if limit <= 0:
            return True
        redis_allowed = self._allow_with_redis(settings.redis_url, key, limit, window_seconds)
        if redis_allowed is not None:
            return redis_allowed
        now = time.time()
        with self._lock:
            count, expires_at = self._local.get(key, (0, now + window_seconds))
            if expires_at <= now:
                count, expires_at = 0, now + window_seconds
            count += 1
            self._local[key] = (count, expires_at)
            return count <= limit

    def _allow_with_redis(self, redis_url: str, key: str, limit: int, window_seconds: int) -> bool | None:
        try:
            redis = Redis.from_url(redis_url, socket_connect_timeout=0.2, socket_timeout=0.2)
            count = redis.incr(key)
            if count == 1:
                redis.expire(key, window_seconds)
            return int(count) <= limit
        except RedisError:
            return None


METRICS = RuntimeMetrics()
RATE_LIMITER = RateLimiter()


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler()
    formatter: logging.Formatter
    if settings.log_format.lower() == "json":
        formatter = JsonLogFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    handler.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=[handler], force=True)


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    settings = get_settings()
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    client_host = _client_host(request)

    body_limit_response = _enforce_body_size(request, settings.max_request_body_bytes)
    if body_limit_response:
        _apply_security_headers(body_limit_response)
        body_limit_response.headers["X-Request-Id"] = request_id
        METRICS.record(request.method, request.url.path, body_limit_response.status_code, 0)
        return body_limit_response

    rate_limit_response = _enforce_rate_limit(request, client_host)
    if rate_limit_response:
        _apply_security_headers(rate_limit_response)
        rate_limit_response.headers["X-Request-Id"] = request_id
        METRICS.record(request.method, request.url.path, rate_limit_response.status_code, 0)
        return rate_limit_response

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.exception(
            "request_failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
                "client_host": client_host,
            },
        )
        raise

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Response-Time-Ms"] = str(duration_ms)
    _apply_security_headers(response)
    METRICS.record(request.method, request.url.path, response.status_code, duration_ms)
    logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client_host": client_host,
        },
    )
    return response


def _enforce_body_size(request: Request, max_bytes: int) -> Response | None:
    content_length = request.headers.get("content-length")
    if not content_length:
        return None
    try:
        if int(content_length) > max_bytes:
            return JSONResponse(status_code=413, content={"detail": "Request body too large"})
    except ValueError:
        return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header"})
    return None


def _enforce_rate_limit(request: Request, client_host: str) -> Response | None:
    settings = get_settings()
    if not settings.rate_limit_enabled or request.url.path.startswith("/api/v1/health"):
        return None
    is_login = request.url.path == "/api/v1/auth/login"
    limit = settings.login_rate_limit_requests if is_login else settings.rate_limit_requests
    key = f"ratelimit:{client_host}:{request.method}:{request.url.path if is_login else 'api'}"
    if RATE_LIMITER.allow(key, limit, settings.rate_limit_window_seconds):
        return None
    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})


def _apply_security_headers(response: Response) -> None:
    settings = get_settings()
    if not settings.security_headers_enabled:
        return
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'; base-uri 'none'; object-src 'none'")
    if settings.hsts_enabled:
        response.headers.setdefault(
            "Strict-Transport-Security", f"max-age={settings.hsts_max_age_seconds}; includeSubDomains"
        )


def _client_host(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _metric_route_key(method: str, path: str) -> str:
    parts = [part for part in path.split("/") if part]
    normalized = []
    for part in parts:
        normalized.append("{id}" if part.isdigit() else part)
    return f"{method} /{'/'.join(normalized)}"
