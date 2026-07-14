from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_compose_uses_distinct_application_database_identity() -> None:
    compose = (ROOT / "deploy" / "compose.yaml").read_text(encoding="utf-8")

    assert "postgresql+asyncpg://${APP_DB_USER}:${APP_DB_PASSWORD}@postgres:5432/${POSTGRES_DB}" in compose
    assert "postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}" not in compose
    assert "APP_DB_USER: ${APP_DB_USER}" in compose
    assert "APP_DB_PASSWORD: ${APP_DB_PASSWORD}" in compose
    assert "./postgres/provision-app-role.sh:/docker-entrypoint-initdb.d/10-provision-app-role.sh:ro" in compose


def test_example_environment_defines_separate_non_secret_identities() -> None:
    example = (ROOT / "deploy" / ".env.example").read_text(encoding="utf-8")

    assert "POSTGRES_USER=ux09_owner" in example
    assert "APP_DB_USER=ux09_app" in example
    assert "APP_DB_PASSWORD=change-me-app" in example


def test_alembic_does_not_provision_roles_or_passwords() -> None:
    migration = (
        ROOT / "server" / "migrations" / "versions" / "0017_governance_deletion.py"
    ).read_text(encoding="utf-8").upper()

    assert "CREATE ROLE" not in migration
    assert "CREATE USER" not in migration
    assert "ALTER ROLE" not in migration
    assert "PASSWORD" not in migration


@pytest.mark.parametrize(
    ("app_user", "app_password", "message"),
    [
        ("ux09_owner", "app-password", "APP_DB_USER must differ from POSTGRES_USER"),
        ("ux09_app", "owner-password", "APP_DB_PASSWORD must differ from POSTGRES_PASSWORD"),
    ],
)
def test_role_provisioning_rejects_shared_owner_credentials(
    app_user: str,
    app_password: str,
    message: str,
) -> None:
    result = subprocess.run(
        ["sh", "deploy/postgres/provision-app-role.sh"],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={
            **os.environ,
            "POSTGRES_DB": "ux09",
            "POSTGRES_USER": "ux09_owner",
            "POSTGRES_PASSWORD": "owner-password",
            "APP_DB_USER": app_user,
            "APP_DB_PASSWORD": app_password,
        },
    )

    assert result.returncode != 0
    assert message in result.stderr
