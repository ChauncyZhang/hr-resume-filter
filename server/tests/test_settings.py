import pytest
from pydantic import ValidationError
from pydantic import SecretStr

from server.app.core.settings import Settings


def production_settings(**overrides: object) -> Settings:
    values = {
        "environment": "production",
        "database_url": "postgresql+asyncpg://app:S3cureValue%21@postgres/app",
        "object_storage_endpoint": "minio:9000",
        "object_storage_access_key": "real-access-key",
        "object_storage_secret_key": "real-secret-key",
        "object_storage_bucket": "resumes",
        "contact_encryption_key": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
        "contact_lookup_secret": "ICEiIyQlJicoKSorLC0uLzAxMjM0NTY3ODk6Ozw9Pj8=",
        "cors_origins": ["https://hr.example.com"],
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_url", "postgresql+asyncpg://app:change-me@postgres/app"),
        ("object_storage_access_key", "change-me"),
        ("object_storage_secret_key", "placeholder"),
    ],
)
def test_production_rejects_placeholder_secrets(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        production_settings(**{field: value})


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+asyncpg://app@postgres/app",
        "postgresql+asyncpg://app:@postgres/app",
    ],
)
def test_production_rejects_database_url_without_password(database_url: str) -> None:
    with pytest.raises(ValidationError):
        production_settings(database_url=database_url)


@pytest.mark.parametrize(
    "password",
    [
        "secret",
        "safe-secret-value",
        "password",
        "safe-password-value",
        "change-me",
        "safe-change%2Dme-value",
        "example",
        "%73ecret",
    ],
)
def test_production_rejects_decoded_placeholder_database_password(
    password: str,
) -> None:
    with pytest.raises(ValidationError):
        production_settings(
            database_url=f"postgresql+asyncpg://app:{password}@postgres/app"
        )


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError):
        production_settings(cors_origins=["*"])


def test_production_rejects_insecure_cors_origin() -> None:
    with pytest.raises(ValidationError):
        production_settings(cors_origins=["http://hr.example.com"])


def test_production_accepts_explicit_origins_and_non_placeholder_secrets() -> None:
    settings = production_settings()

    assert settings.environment == "production"
    assert settings.cors_origins == ["https://hr.example.com"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("contact_encryption_key", "change-me"), ("contact_lookup_secret", "placeholder")],
)
def test_production_rejects_placeholder_contact_secrets(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        production_settings(**{field: value})


def test_production_accepts_deployment_supplied_contact_secrets() -> None:
    settings = production_settings()
    assert isinstance(settings.contact_encryption_key, SecretStr)
    assert "AAECAw" not in repr(settings)


@pytest.mark.parametrize("value", ["short", "not base64!", "+" * 43 + "=", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=", "Y2hhbmdlLW1l", "MDEyMzQ1Njc4OWFiY2RlZg=="])
def test_production_rejects_malformed_or_short_contact_keys(value: str) -> None:
    with pytest.raises(ValidationError):
        production_settings(contact_encryption_key=value)


def test_production_rejects_equal_contact_keys() -> None:
    key = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
    with pytest.raises(ValidationError):
        production_settings(contact_encryption_key=key, contact_lookup_secret=key)
