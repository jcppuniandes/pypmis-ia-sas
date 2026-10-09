"""Tests for the Redis cache helper module."""

from unittest.mock import MagicMock, patch

from app.core.cache import cache_key, get_cached, invalidate, set_cached


def test_cache_key_deterministic():
    k1 = cache_key("prefix", 1, "abc")
    k2 = cache_key("prefix", 1, "abc")
    assert k1 == k2
    assert k1.startswith("pypmis:prefix:")


def test_cache_key_varies_on_input():
    k1 = cache_key("x", 1)
    k2 = cache_key("x", 2)
    assert k1 != k2


@patch("app.core.cache._redis")
def test_get_set_roundtrip(mock_redis_fn):
    store = {}
    mock = MagicMock()
    mock.get.side_effect = lambda k: store.get(k)
    mock.setex.side_effect = lambda k, _ttl, v: store.__setitem__(k, v)
    mock_redis_fn.return_value = mock

    key = cache_key("test", 42)
    assert get_cached(key) is None

    set_cached(key, {"hello": "world"}, ttl=60)
    result = get_cached(key)
    assert result == {"hello": "world"}


@patch("app.core.cache._redis")
def test_invalidate(mock_redis_fn):
    mock = MagicMock()
    mock_redis_fn.return_value = mock

    key = cache_key("test", 99)
    invalidate(key)
    mock.delete.assert_called_once_with(key)


@patch("app.core.cache._redis")
def test_get_cached_returns_none_on_redis_error(mock_redis_fn):
    from redis.exceptions import RedisError

    mock = MagicMock()
    mock.get.side_effect = RedisError("connection refused")
    mock_redis_fn.return_value = mock

    assert get_cached("any_key") is None


@patch("app.core.cache._redis")
def test_set_cached_swallows_redis_error(mock_redis_fn):
    from redis.exceptions import RedisError

    mock = MagicMock()
    mock.setex.side_effect = RedisError("connection refused")
    mock_redis_fn.return_value = mock

    set_cached("any_key", {"data": 1})
