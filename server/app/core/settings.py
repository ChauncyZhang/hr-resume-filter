import json
import os
import base64
import re
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


PLACEHOLDERS = {
    "",
    "change-me",
    "changeme",
    "example",
    "password",
    "placeholder",
    "secret",
}
PLACEHOLDER_FRAGMENTS = PLACEHOLDERS - {""}


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://app:change-me@postgres/app"
    object_storage_endpoint: str = "minio:9000"
    object_storage_access_key: str = "change-me"
    object_storage_secret_key: str = "change-me"
    object_storage_bucket: str = "resumes"
    contact_encryption_key: SecretStr = SecretStr("change-me")
    contact_lookup_secret: SecretStr = SecretStr("change-me")
    object_storage_secure: bool = False
    object_storage_connect_timeout_seconds: float = Field(default=1, gt=0)
    object_storage_read_timeout_seconds: float = Field(default=3, gt=0)
    object_storage_total_timeout_seconds: float = Field(default=4, gt=0)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost"])
    worker_check_interval_seconds: float = Field(default=30, ge=0)
    readiness_timeout_seconds: float = Field(default=5, gt=0)
    worker_id: str = Field(default="worker", min_length=1, max_length=200)
    worker_lease_seconds: int = Field(default=60, gt=0)
    worker_heartbeat_seconds: int = Field(default=20, gt=0)
    worker_poll_interval_seconds: float = Field(default=1, ge=0)
    worker_shutdown_timeout_seconds: float = Field(default=30, gt=0)
    worker_cancel_timeout_seconds: float = Field(default=5, gt=0, le=30)
    parser_max_source_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    parser_max_text_chars: int = Field(default=500_000, ge=1000, le=5_000_000)
    parser_pdf_max_pages: int = Field(default=100, ge=1, le=1000)
    parser_docx_max_entries: int = Field(default=1000, ge=10, le=10000)
    parser_docx_max_uncompressed_bytes: int = Field(default=50 * 1024 * 1024, ge=1024, le=500 * 1024 * 1024)
    parser_docx_max_compression_ratio: int = Field(default=100, ge=1, le=1000)
    parser_hard_timeout_seconds: float = Field(default=15, gt=0, le=120)
    clamav_host: str = Field(default="clamav", min_length=1, max_length=253)
    clamav_port: int = Field(default=3310, ge=1, le=65535)
    clamav_connect_timeout_seconds: float = Field(default=2, gt=0, le=30)
    clamav_read_timeout_seconds: float = Field(default=10, gt=0, le=60)
    clamav_total_timeout_seconds: float = Field(default=15, gt=0, le=120)

    @model_validator(mode="after")
    def validate_worker_timing(self) -> "Settings":
        if self.worker_heartbeat_seconds * 3 > self.worker_lease_seconds:
            raise ValueError("worker heartbeat must be no more than one-third of lease duration")
        if not 0 < self.worker_poll_interval_seconds <= 60:
            raise ValueError("worker poll interval must be between 0 and 60 seconds")
        if self.worker_shutdown_timeout_seconds > 300:
            raise ValueError("worker shutdown timeout must be at most 300 seconds")
        if self.clamav_total_timeout_seconds < self.clamav_read_timeout_seconds:
            raise ValueError("ClamAV total timeout must cover read timeout")
        return self

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        if self.environment != "production":
            return self
        credentials = (
            self.object_storage_access_key.strip().lower(),
            self.object_storage_secret_key.strip().lower(),
            self.contact_encryption_key.get_secret_value().strip().lower(),
            self.contact_lookup_secret.get_secret_value().strip().lower(),
        )
        database_url = urlsplit(self.database_url)
        if not database_url.scheme or not database_url.hostname:
            raise ValueError("production database URL is invalid")
        if not database_url.password:
            raise ValueError("production database password is required")
        database_password = unquote(database_url.password).strip().lower()
        if (
            any(value in PLACEHOLDERS for value in credentials)
            or any(marker in database_password for marker in PLACEHOLDER_FRAGMENTS)
        ):
            raise ValueError("production credentials must not use placeholders")
        if not all(credentials):
            raise ValueError("production credentials are required")
        contact_values = [self.contact_encryption_key.get_secret_value(), self.contact_lookup_secret.get_secret_value()]
        if any(re.fullmatch(r"[A-Za-z0-9_-]{43}=", value) is None for value in contact_values):
            raise ValueError("contact keys must use padded base64url")
        try:
            decoded = [base64.b64decode(value, altchars=b"-_", validate=True) for value in contact_values]
        except (ValueError, base64.binascii.Error):
            raise ValueError("contact keys must be base64url") from None
        if any(len(value) != 32 for value in decoded):
            raise ValueError("contact keys must decode to 32 bytes")
        if any(len(set(value)) < 16 for value in decoded):
            raise ValueError("contact keys must be high entropy")
        if decoded[0] == decoded[1]:
            raise ValueError("contact keys must be independent")
        if "*" in self.cors_origins:
            raise ValueError("wildcard CORS is forbidden in production")
        if any(not origin.startswith("https://") for origin in self.cors_origins):
            raise ValueError("production CORS origins must use HTTPS")
        return self

    @classmethod
    def from_environment(cls) -> "Settings":
        values: dict[str, object] = {}
        mapping = {
            "APP_ENVIRONMENT": "environment",
            "DATABASE_URL": "database_url",
            "OBJECT_STORAGE_ENDPOINT": "object_storage_endpoint",
            "OBJECT_STORAGE_ACCESS_KEY": "object_storage_access_key",
            "OBJECT_STORAGE_SECRET_KEY": "object_storage_secret_key",
            "OBJECT_STORAGE_BUCKET": "object_storage_bucket",
            "CONTACT_ENCRYPTION_KEY": "contact_encryption_key",
            "CONTACT_LOOKUP_SECRET": "contact_lookup_secret",
            "OBJECT_STORAGE_SECURE": "object_storage_secure",
            "OBJECT_STORAGE_CONNECT_TIMEOUT_SECONDS": "object_storage_connect_timeout_seconds",
            "OBJECT_STORAGE_READ_TIMEOUT_SECONDS": "object_storage_read_timeout_seconds",
            "OBJECT_STORAGE_TOTAL_TIMEOUT_SECONDS": "object_storage_total_timeout_seconds",
            "WORKER_CHECK_INTERVAL_SECONDS": "worker_check_interval_seconds",
            "READINESS_TIMEOUT_SECONDS": "readiness_timeout_seconds",
            "WORKER_ID": "worker_id",
            "WORKER_LEASE_SECONDS": "worker_lease_seconds",
            "WORKER_HEARTBEAT_SECONDS": "worker_heartbeat_seconds",
            "WORKER_POLL_INTERVAL_SECONDS": "worker_poll_interval_seconds",
            "WORKER_SHUTDOWN_TIMEOUT_SECONDS": "worker_shutdown_timeout_seconds",
            "WORKER_CANCEL_TIMEOUT_SECONDS": "worker_cancel_timeout_seconds",
            "PARSER_MAX_SOURCE_BYTES": "parser_max_source_bytes",
            "PARSER_MAX_TEXT_CHARS": "parser_max_text_chars",
            "PARSER_PDF_MAX_PAGES": "parser_pdf_max_pages",
            "PARSER_DOCX_MAX_ENTRIES": "parser_docx_max_entries",
            "PARSER_DOCX_MAX_UNCOMPRESSED_BYTES": "parser_docx_max_uncompressed_bytes",
            "PARSER_DOCX_MAX_COMPRESSION_RATIO": "parser_docx_max_compression_ratio",
            "PARSER_HARD_TIMEOUT_SECONDS": "parser_hard_timeout_seconds",
            "CLAMAV_HOST": "clamav_host",
            "CLAMAV_PORT": "clamav_port",
            "CLAMAV_CONNECT_TIMEOUT_SECONDS": "clamav_connect_timeout_seconds",
            "CLAMAV_READ_TIMEOUT_SECONDS": "clamav_read_timeout_seconds",
            "CLAMAV_TOTAL_TIMEOUT_SECONDS": "clamav_total_timeout_seconds",
        }
        for env_name, field_name in mapping.items():
            if env_name in os.environ:
                values[field_name] = os.environ[env_name]
        if "CORS_ORIGINS" in os.environ:
            values["cors_origins"] = json.loads(os.environ["CORS_ORIGINS"])
        return cls.model_validate(values)
