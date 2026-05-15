"""Shared pytest configuration for API tests."""

import os

from app.core.config import get_settings


os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
get_settings.cache_clear()
