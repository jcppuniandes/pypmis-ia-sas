"""Tests for the global exception handler in main.py."""

import asyncio
import json
from unittest.mock import MagicMock

from app.main import unhandled_exception_handler


def test_unhandled_exception_returns_500():
    request = MagicMock()
    request.state = MagicMock(spec=[])
    request.url.path = "/api/v1/test"

    response = asyncio.get_event_loop().run_until_complete(
        unhandled_exception_handler(request, RuntimeError("boom"))
    )

    assert response.status_code == 500
    body = json.loads(response.body)
    assert body["detail"] == "Internal server error"
    assert body["request_id"] == "unknown"


def test_unhandled_exception_includes_request_id():
    request = MagicMock()
    request.state.request_id = "abc-123"
    request.url.path = "/api/v1/test"

    response = asyncio.get_event_loop().run_until_complete(
        unhandled_exception_handler(request, ValueError("oops"))
    )

    body = json.loads(response.body)
    assert body["request_id"] == "abc-123"
