import json
import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PLACEHOLDERS = {"", "change-me", "changeme", "placeholder", "secret", "password"}


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://app:change-me@postgres/app"
    object_storage_endpoint: str = "minio:9000"
    object_storage_access_key: str = "change-me"
    object_storage_secret_key: str = "change-me"
    object_storage_bucket: str = "resumes"
    object_storage_secure: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost"])
    worker_check_interval_seconds: float = Field(default=30, ge=0)

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        if self.environment != "production":
            return self
        credentials = (
            self.object_storage_access_key.strip().lower(),
            self.object_storage_secret_key.strip().lower(),
        )
        database_url = self.database_url.strip().lower()
        if (
            any(value in PLACEHOLDERS for value in credentials)
            or any(
                marker in database_url
                for marker in (
                    ":change-me@",
                    ":changeme@",
                    ":placeholder@",
                    ":password@",
                )
            )
        ):
            raise ValueError("production credentials must not use placeholders")
        if not database_url or not all(credentials):
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
            "OBJECT_STORAGE_SECURE": "object_storage_secure",
            "WORKER_CHECK_INTERVAL_SECONDS": "worker_check_interval_seconds",
        }
        for env_name, field_name in mapping.items():
            if env_name in os.environ:
                values[field_name] = os.environ[env_name]
        if "CORS_ORIGINS" in os.environ:
            values["cors_origins"] = json.loads(os.environ["CORS_ORIGINS"])
        return cls.model_validate(values)
