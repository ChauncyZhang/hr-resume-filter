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
            "GOVERNANCE_DB_USER": "ux09_governance",
            "GOVERNANCE_DB_PASSWORD": "governance-password",
        },
    )

    assert result.returncode != 0
    assert message in result.stderr


def _service_block(compose: str, service: str, next_service: str) -> str:
    return compose.split(f"  {service}:\n", 1)[1].split(f"  {next_service}:\n", 1)[0]


def test_compose_keeps_governance_credentials_worker_only_and_root_credentials_runtime_free() -> None:
    compose = (ROOT / "deploy" / "compose.yaml").read_text(encoding="utf-8")
    api = _service_block(compose, "api", "worker")
    worker = _service_block(compose, "worker", "postgres")

    governance_names = (
        "GOVERNANCE_DATABASE_URL",
        "GOVERNANCE_DELETE_ACCESS_KEY",
        "GOVERNANCE_DELETE_SECRET_KEY",
        "GOVERNANCE_LEDGER_ACCESS_KEY",
        "GOVERNANCE_LEDGER_SECRET_KEY",
        "GOVERNANCE_LEDGER_SIGNING_KEY",
    )
    assert all(name not in api for name in governance_names)
    assert all(name in worker for name in governance_names)
    assert "DATABASE_URL" in worker
    assert "MINIO_ROOT_USER" not in api
    assert "MINIO_ROOT_PASSWORD" not in api
    assert "MINIO_ROOT_USER" not in worker
    assert "MINIO_ROOT_PASSWORD" not in worker
    assert "GOVERNANCE_EXPORT_BUCKET: ${GOVERNANCE_EXPORT_BUCKET:-${OBJECT_STORAGE_BUCKET:-resumes}}" in worker


def test_minio_provisioning_rejects_reused_identities_and_secrets() -> None:
    script = (ROOT / "deploy" / "minio" / "provision.sh").read_text(encoding="utf-8")

    assert "MinIO access keys must be pairwise distinct" in script
    assert "MinIO secret keys must be pairwise distinct" in script
    assert "PREVIOUS_GOVERNANCE_DELETE_ACCESS_KEY" in script
    assert "PREVIOUS_GOVERNANCE_LEDGER_ACCESS_KEY" in script


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"GOVERNANCE_DELETE_ACCESS_KEY": "app-access"},
            "MinIO access keys must be pairwise distinct",
        ),
        (
            {"GOVERNANCE_LEDGER_SECRET_KEY": "delete-secret"},
            "MinIO secret keys must be pairwise distinct",
        ),
        (
            {"PREVIOUS_GOVERNANCE_DELETE_ACCESS_KEY": "app-access"},
            "retired MinIO access key conflicts with an active identity",
        ),
    ],
)
def test_minio_provisioning_fails_before_network_on_reused_credentials(
    overrides: dict[str, str], message: str
) -> None:
    environment = {
        **os.environ,
        "MINIO_ROOT_USER": "root-access",
        "MINIO_ROOT_PASSWORD": "root-secret",
        "APP_OBJECT_STORAGE_ACCESS_KEY": "app-access",
        "APP_OBJECT_STORAGE_SECRET_KEY": "app-secret",
        "OBJECT_STORAGE_BUCKET": "resumes",
        "GOVERNANCE_DELETE_ACCESS_KEY": "delete-access",
        "GOVERNANCE_DELETE_SECRET_KEY": "delete-secret",
        "GOVERNANCE_RESUME_BUCKET": "resumes",
        "GOVERNANCE_RESUME_PREFIX": "clean/",
        "GOVERNANCE_EXPORT_BUCKET": "resumes",
        "GOVERNANCE_EXPORT_PREFIX": "exports/",
        "GOVERNANCE_LEDGER_ACCESS_KEY": "ledger-access",
        "GOVERNANCE_LEDGER_SECRET_KEY": "ledger-secret",
        "GOVERNANCE_LEDGER_BUCKET": "governance-ledger",
        "GOVERNANCE_LEDGER_PREFIX": "deletions/",
        **overrides,
    }
    result = subprocess.run(
        ["sh", "deploy/minio/provision.sh"],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=environment,
    )

    assert result.returncode != 0
    assert message in result.stderr


@pytest.mark.parametrize(
    ("governance_user", "governance_password", "message"),
    [
        ("ux09_owner", "governance-password", "GOVERNANCE_DB_USER must differ from POSTGRES_USER"),
        ("ux09_app", "governance-password", "GOVERNANCE_DB_USER must differ from APP_DB_USER"),
        ("ux09_governance", "owner-password", "GOVERNANCE_DB_PASSWORD must differ from POSTGRES_PASSWORD"),
        ("ux09_governance", "app-password", "GOVERNANCE_DB_PASSWORD must differ from APP_DB_PASSWORD"),
    ],
)
def test_role_provisioning_rejects_shared_governance_credentials(
    governance_user: str, governance_password: str, message: str
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
            "APP_DB_USER": "ux09_app",
            "APP_DB_PASSWORD": "app-password",
            "GOVERNANCE_DB_USER": governance_user,
            "GOVERNANCE_DB_PASSWORD": governance_password,
        },
    )

    assert result.returncode != 0
    assert message in result.stderr
