"""Lightweight Redis cache for semi-static API responses."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 300


def _redis() -> Redis:
    return Redis.from_url(
        get_settings().redis_url,
        socket_connect_timeout=0.3,
        socket_timeout=0.3,
        decode_responses=True,
    )


def cache_key(prefix: str, *parts: Any) -> str:
    raw = ":".join(str(p) for p in parts)
    digest = hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()[:12]
    return f"pypmis:{prefix}:{digest}"


def get_cached(key: str) -> Any | None:
    try:
        data = _redis().get(key)
        if data is not None:
            return json.loads(data)
    except (RedisError, json.JSONDecodeError):
        pass
    return None


def set_cached(key: str, value: Any, ttl: int = _DEFAULT_TTL) -> None:
    try:
        _redis().setex(key, ttl, json.dumps(value, default=str))
    except RedisError:
        logger.debug("Cache write failed for %s", key)


def invalidate(key: str) -> None:
    try:
        _redis().delete(key)
    except RedisError:
        pass
