"""Tests for Settings validation and property helpers."""

import pytest

from app.core.config import Settings


def test_cors_origin_list_splits_correctly():
    s = Settings(cors_origins="http://a.com, http://b.com , http://c.com")
    assert s.cors_origin_list == ["http://a.com", "http://b.com", "http://c.com"]


def test_allowed_host_list_splits_correctly():
    s = Settings(allowed_hosts="a.com,b.com")
    assert s.allowed_host_list == ["a.com", "b.com"]


def test_is_production_detects_variants():
    assert Settings(app_environment="production").is_production is True
    assert Settings(app_environment="prod").is_production is True
    assert Settings(app_environment="Production").is_production is True
    assert Settings(app_environment="local").is_production is False


def test_max_request_body_bytes():
    s = Settings(max_request_body_mb=10)
    assert s.max_request_body_bytes == 10 * 1024 * 1024


def test_document_extension_set():
    s = Settings(document_allowed_extensions=".pdf,.DOC, .xls ")
    assert s.document_allowed_extension_set == {".pdf", ".doc", ".xls"}


def test_validate_for_runtime_rejects_weak_secret():
    s = Settings(
        app_environment="production",
        auth_secret_key="short",
        allowed_hosts="a.com",
        cors_origins="http://a.com",
        docs_enabled=False,
        auto_create_schema=False,
    )
    with pytest.raises(RuntimeError, match="AUTH_SECRET_KEY"):
        s.validate_for_runtime()


def test_validate_for_runtime_rejects_wildcard_hosts():
    s = Settings(
        app_environment="production",
        auth_secret_key="a" * 64,
        allowed_hosts="*",
        cors_origins="http://a.com",
        docs_enabled=False,
        auto_create_schema=False,
    )
    with pytest.raises(RuntimeError, match="ALLOWED_HOSTS"):
        s.validate_for_runtime()


def test_validate_for_runtime_rejects_docs_in_prod():
    s = Settings(
        app_environment="production",
        auth_secret_key="a" * 64,
        allowed_hosts="a.com",
        cors_origins="http://a.com",
        docs_enabled=True,
        auto_create_schema=False,
    )
    with pytest.raises(RuntimeError, match="DOCS_ENABLED"):
        s.validate_for_runtime()


def test_validate_for_runtime_rejects_auto_schema_in_prod():
    s = Settings(
        app_environment="production",
        auth_secret_key="a" * 64,
        allowed_hosts="a.com",
        cors_origins="http://a.com",
        docs_enabled=False,
        auto_create_schema=True,
    )
    with pytest.raises(RuntimeError, match="AUTO_CREATE_SCHEMA"):
        s.validate_for_runtime()


def test_validate_for_runtime_rejects_missing_metrics_token_in_prod():
    s = Settings(
        app_environment="production",
        auth_secret_key="a" * 64,
        allowed_hosts="a.com",
        cors_origins="http://a.com",
        docs_enabled=False,
        auto_create_schema=False,
        metrics_enabled=True,
        metrics_token="",
    )
    with pytest.raises(RuntimeError, match="METRICS_TOKEN"):
        s.validate_for_runtime()


def test_validate_for_runtime_rejects_disabled_operational_hardening():
    s = Settings(
        app_environment="production",
        auth_secret_key="a" * 64,
        allowed_hosts="a.com",
        cors_origins="http://a.com",
        docs_enabled=False,
        auto_create_schema=False,
        metrics_enabled=True,
        metrics_token="m" * 32,
        rate_limit_enabled=False,
        security_headers_enabled=False,
        log_format="plain",
    )
    with pytest.raises(RuntimeError, match="RATE_LIMIT_ENABLED"):
        s.validate_for_runtime()


def test_validate_for_runtime_passes_secure_config():
    s = Settings(
        app_environment="production",
        auth_secret_key="a" * 64,
        allowed_hosts="a.com",
        cors_origins="http://a.com",
        docs_enabled=False,
        auto_create_schema=False,
        metrics_token="m" * 32,
        rate_limit_enabled=True,
        security_headers_enabled=True,
        log_format="json",
    )
    s.validate_for_runtime()


def test_validate_for_runtime_skips_non_production():
    s = Settings(
        app_environment="local",
        auth_secret_key="short",
        allowed_hosts="*",
    )
    s.validate_for_runtime()


def test_allow_insecure_production_bypasses_checks():
    s = Settings(
        app_environment="production",
        auth_secret_key="short",
        allowed_hosts="*",
        allow_insecure_production=True,
    )
    s.validate_for_runtime()
