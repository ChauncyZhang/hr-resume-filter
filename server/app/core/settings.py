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
        }
        for env_name, field_name in mapping.items():
            if env_name in os.environ:
                values[field_name] = os.environ[env_name]
        if "CORS_ORIGINS" in os.environ:
            values["cors_origins"] = json.loads(os.environ["CORS_ORIGINS"])
        return cls.model_validate(values)
