"""Tests for RuntimeMetrics, RateLimiter, and JsonLogFormatter."""

import json
import logging
from unittest.mock import patch

from app.core.observability import JsonLogFormatter, RateLimiter, RuntimeMetrics


def test_runtime_metrics_records_request():
    m = RuntimeMetrics()
    m.record("GET", "/api/v1/health", 200, 12.5)
    snap = m.snapshot()
    assert snap["request_count"] == 1
    assert snap["error_count"] == 0
    assert snap["status_counts"] == {"2xx": 1}
    assert snap["p95_duration_ms"] == 12.5


def test_runtime_metrics_counts_errors():
    m = RuntimeMetrics()
    m.record("POST", "/api/v1/projects", 500, 100.0)
    m.record("GET", "/api/v1/health", 200, 5.0)
    snap = m.snapshot()
    assert snap["request_count"] == 2
    assert snap["error_count"] == 1
    assert snap["status_counts"] == {"5xx": 1, "2xx": 1}


def test_runtime_metrics_prometheus_output():
    m = RuntimeMetrics()
    m.record("GET", "/api/v1/health", 200, 10.0)
    output = m.prometheus("TestApp", "test", "0.1.0")
    assert 'pypmis_app_info{app="TestApp"' in output
    assert "pypmis_http_requests_total 1" in output
    assert "pypmis_http_errors_total 0" in output
    assert "pypmis_uptime_seconds" in output


def test_rate_limiter_allows_within_limit():
    rl = RateLimiter()
    with patch.object(rl, "_allow_with_redis", return_value=None):
        assert rl.allow("test:ip:1", limit=3, window_seconds=60) is True
        assert rl.allow("test:ip:1", limit=3, window_seconds=60) is True
        assert rl.allow("test:ip:1", limit=3, window_seconds=60) is True
        assert rl.allow("test:ip:1", limit=3, window_seconds=60) is False


def test_rate_limiter_zero_limit_always_allows():
    rl = RateLimiter()
    assert rl.allow("test:key", limit=0, window_seconds=60) is True


def test_json_log_formatter_produces_valid_json():
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    output = formatter.format(record)
    parsed = json.loads(output)
    assert parsed["message"] == "hello world"
    assert parsed["level"] == "INFO"
    assert "timestamp" in parsed
