from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "P&Pmis Ai SaaS"
    app_environment: str = "local"
    app_version: str = "0.1.0"
    commit_sha: str = "dev"
    database_url: str = "sqlite:///./pypmis.db"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:5173"
    allowed_hosts: str = "*"
    auto_create_schema: bool = True
    seed_demo_data: bool = True
    auth_secret_key: str = "change-me-before-production"
    access_token_expire_minutes: int = 480
    demo_user_password: str = "1234"
    demo_admin_username: str = "admin"
    demo_admin_email: str = "ana.control@demo.local"
    docs_enabled: bool = True
    security_headers_enabled: bool = True
    hsts_enabled: bool = False
    hsts_max_age_seconds: int = 31_536_000
    max_request_body_mb: int = 25
    document_storage_path: str = "/app/storage/documents"
    document_allowed_extensions: str = ".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip,.jpg,.jpeg,.png,.csv,.txt,.xml,.xer"
    document_max_upload_mb: int = 50
    document_max_zip_files: int = 200
    document_max_zip_uncompressed_mb: int = 250
    document_scan_mode: str = "local"
    document_clamav_host: str = "clamav"
    document_clamav_port: int = 3310
    oidc_enabled: bool = False
    oidc_issuer_url: str = ""
    oidc_client_id: str = ""
    oidc_authorization_url: str = ""
    oidc_token_url: str = ""
    oidc_jwks_url: str = ""
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 600
    rate_limit_window_seconds: int = 60
    login_rate_limit_requests: int = 50
    metrics_enabled: bool = True
    metrics_token: str = ""
    log_level: str = "INFO"
    log_format: str = "plain"
    allow_insecure_production: bool = False
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.1
    ai_provider: str = "disabled"
    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-4-5-20251001"
    ai_max_tokens: int = 1024
    ai_timeout_seconds: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def allowed_host_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_environment.lower() in {"prod", "production"}

    @property
    def max_request_body_bytes(self) -> int:
        return max(self.max_request_body_mb, 1) * 1024 * 1024

    @property
    def document_allowed_extension_set(self) -> set[str]:
        return {
            extension.strip().lower() for extension in self.document_allowed_extensions.split(",") if extension.strip()
        }

    @property
    def document_max_upload_bytes(self) -> int:
        return max(self.document_max_upload_mb, 1) * 1024 * 1024

    @property
    def document_max_zip_uncompressed_bytes(self) -> int:
        return max(self.document_max_zip_uncompressed_mb, 1) * 1024 * 1024

    def validate_for_runtime(self) -> None:
        if not self.is_production or self.allow_insecure_production:
            return
        insecure_secrets = {"change-me-before-production", "dev-local-change-before-production"}
        if self.auth_secret_key in insecure_secrets or len(self.auth_secret_key) < 32:
            raise RuntimeError("AUTH_SECRET_KEY must be a non-default value with at least 32 characters in production")
        if "*" in self.allowed_host_list:
            raise RuntimeError("ALLOWED_HOSTS must be explicit in production")
        if any(origin == "*" for origin in self.cors_origin_list):
            raise RuntimeError("CORS_ORIGINS cannot contain '*' in production")
        if self.docs_enabled:
            raise RuntimeError("DOCS_ENABLED must be false in production")
        if self.oidc_enabled and (not self.oidc_issuer_url or not self.oidc_client_id):
            raise RuntimeError("OIDC_ISSUER_URL and OIDC_CLIENT_ID are required when OIDC is enabled")
        if self.auto_create_schema:
            raise RuntimeError(
                "AUTO_CREATE_SCHEMA must be false in production. "
                "Run 'alembic upgrade head' to manage schema changes."
            )
        if self.metrics_enabled and not self.metrics_token:
            raise RuntimeError("METRICS_TOKEN is required when METRICS_ENABLED=true in production")
        if not self.rate_limit_enabled:
            raise RuntimeError("RATE_LIMIT_ENABLED must be true in production")
        if not self.security_headers_enabled:
            raise RuntimeError("SECURITY_HEADERS_ENABLED must be true in production")
        if self.log_format.lower() != "json":
            raise RuntimeError("LOG_FORMAT must be json in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
