from __future__ import annotations

import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.errors import InsufficientPrivilege


ROOT = Path(__file__).resolve().parents[2]
PROVISION_ROLES = ROOT / "deploy" / "observability" / "provision-roles.sh"
DISPOSABLE_DATABASE_NAME = "ux09_observability_test"


def _confirm_disposable_database(database_url: str) -> None:
    if os.environ.get("DISPOSABLE_DATABASE_CONFIRMED") != "1":
        raise RuntimeError("DISPOSABLE_DATABASE_CONFIRMED=1 is required before any DDL")
    with connect(database_url, autocommit=True) as connection:
        database_name = connection.execute("SELECT current_database()").fetchone()[0]
    if database_name != DISPOSABLE_DATABASE_NAME:
        raise RuntimeError(
            f"disposable database must be named {DISPOSABLE_DATABASE_NAME}; got {database_name}"
        )


def _role_url(owner_url: str, user: str, password: str) -> str:
    return make_conninfo(owner_url, user=user, password=password)


def test_role_provisioning_source_separates_queue_and_postgres_exporter_access() -> None:
    source = PROVISION_ROLES.read_text(encoding="utf-8")

    assert "QUEUE_METRICS_DB_USER" in source
    assert "POSTGRES_EXPORTER_DB_USER" in source
    assert "observability.queue_metrics" in source
    assert "GRANT pg_monitor" in source
    assert "GRANT SELECT ON observability.queue_metrics" in source
    assert "GRANT SELECT ON background_jobs" not in source
    assert "GRANT SELECT ON job_attempts" not in source
    assert "GRANT SELECT ON outbox_events" not in source


def test_real_postgres_roles_are_idempotent_and_mutually_least_privileged() -> None:
    owner_url = os.environ.get("POSTGRES_OBSERVABILITY_SMOKE_URL")
    if not owner_url:
        pytest.skip("POSTGRES_OBSERVABILITY_SMOKE_URL is required for the real role gate")

    _confirm_disposable_database(owner_url)
    queue_user = "ux09_queue_metrics_test"
    queue_password = f"queue-{uuid4().hex}"
    postgres_user = "ux09_postgres_exporter_test"
    postgres_password = f"postgres-{uuid4().hex}"
    info = conninfo_to_dict(owner_url)
    environment = os.environ.copy()
    environment.update(
        {
            "PGHOST": info.get("host", "localhost"),
            "PGPORT": info.get("port", "5432"),
            "POSTGRES_DB": info["dbname"],
            "POSTGRES_USER": info["user"],
            "POSTGRES_PASSWORD": info["password"],
            "QUEUE_METRICS_DB_USER": queue_user,
            "QUEUE_METRICS_DB_PASSWORD": queue_password,
            "POSTGRES_EXPORTER_DB_USER": postgres_user,
            "POSTGRES_EXPORTER_DB_PASSWORD": postgres_password,
        }
    )

    canary = "alice.canary@example.test"
    with connect(owner_url, autocommit=True) as connection:
        connection.execute(
            """
            CREATE SCHEMA IF NOT EXISTS observability;
            DROP VIEW IF EXISTS observability.queue_metrics;
            DROP TABLE IF EXISTS job_attempts, outbox_events, background_jobs;
            CREATE TABLE background_jobs (
                id uuid PRIMARY KEY, type text NOT NULL, status text NOT NULL,
                run_after timestamptz NOT NULL, lease_expires_at timestamptz,
                payload jsonb
            );
            CREATE TABLE job_attempts (
                job_id uuid NOT NULL, result text, safe_error_code text,
                duration_ms integer
            );
            CREATE TABLE outbox_events (
                id uuid PRIMARY KEY, topic text NOT NULL, status text NOT NULL,
                available_at timestamptz NOT NULL, lease_expires_at timestamptz,
                payload jsonb
            );
            """
        )
        connection.execute(
            """INSERT INTO background_jobs
               (id, type, status, run_after, lease_expires_at, payload)
               VALUES (gen_random_uuid(), 'screening.parse_item', 'queued',
                       now() - interval '2 minutes', NULL,
                       jsonb_build_object('email', %s::text))""",
            (canary,),
        )

    for _ in range(2):
        result = subprocess.run(
            ["sh", str(PROVISION_ROLES)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    queue_url = _role_url(owner_url, queue_user, queue_password)
    postgres_url = _role_url(owner_url, postgres_user, postgres_password)
    with connect(queue_url, autocommit=True) as connection:
        columns = [
            row[0]
            for row in connection.execute(
                """SELECT column_name FROM information_schema.columns
                   WHERE table_schema = 'observability' AND table_name = 'queue_metrics'
                   ORDER BY ordinal_position"""
            )
        ]
        rows = connection.execute(
            "SELECT metric_name, dimension_a, dimension_b, dimension_c, value "
            "FROM observability.queue_metrics"
        ).fetchall()
        assert columns == [
            "metric_name",
            "dimension_a",
            "dimension_b",
            "dimension_c",
            "value",
        ]
        assert canary not in repr(rows)
        assert connection.execute(
            "SELECT pg_has_role(current_user, 'pg_monitor', 'MEMBER')"
        ).fetchone() == (False,)
        for table in ("background_jobs", "job_attempts", "outbox_events"):
            with pytest.raises(InsufficientPrivilege):
                connection.execute(f"SELECT * FROM {table}").fetchall()

    with connect(postgres_url, autocommit=True) as connection:
        assert connection.execute(
            "SELECT pg_has_role(current_user, 'pg_monitor', 'MEMBER')"
        ).fetchone() == (True,)
        connection.execute("SELECT count(*) FROM pg_catalog.pg_stat_activity").fetchone()
        with pytest.raises(InsufficientPrivilege):
            connection.execute("SELECT * FROM observability.queue_metrics").fetchall()
        for table in ("background_jobs", "job_attempts", "outbox_events"):
            with pytest.raises(InsufficientPrivilege):
                connection.execute(f"SELECT * FROM {table}").fetchall()
