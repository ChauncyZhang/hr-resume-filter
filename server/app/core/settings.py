import json
import os
from typing import Literal
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    contact_encryption_key: str = "change-me"
    contact_lookup_secret: str = "change-me"
    object_storage_secure: bool = False
    object_storage_connect_timeout_seconds: float = Field(default=1, gt=0)
    object_storage_read_timeout_seconds: float = Field(default=3, gt=0)
    object_storage_total_timeout_seconds: float = Field(default=4, gt=0)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost"])
    worker_check_interval_seconds: float = Field(default=30, ge=0)
    readiness_timeout_seconds: float = Field(default=5, gt=0)

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        if self.environment != "production":
            return self
        credentials = (
            self.object_storage_access_key.strip().lower(),
            self.object_storage_secret_key.strip().lower(),
            self.contact_encryption_key.strip().lower(),
            self.contact_lookup_secret.strip().lower(),
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
        }
        for env_name, field_name in mapping.items():
            if env_name in os.environ:
                values[field_name] = os.environ[env_name]
        if "CORS_ORIGINS" in os.environ:
            values["cors_origins"] = json.loads(os.environ["CORS_ORIGINS"])
        return cls.model_validate(values)
