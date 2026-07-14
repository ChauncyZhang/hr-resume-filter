from __future__ import annotations

import os
import subprocess
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError


pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_SMOKE_URL"), reason="PostgreSQL smoke URL not configured"
)


def _alembic(url: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", "-m", "alembic", "-c", "server/alembic.ini", *args],
        check=check,
        capture_output=not check,
        text=True,
        env={**os.environ, "DATABASE_URL": url},
    )


def _reset_to_0016a(url: str) -> None:
    engine = create_engine(url.replace("+asyncpg", "+psycopg"))
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    _alembic(url, "upgrade", "0016a_audit_category_repair")


def _seed_identity(connection) -> dict[str, uuid.UUID]:
    ids = {name: uuid.uuid4() for name in ("org1", "org2", "user1", "user2", "candidate")}
    connection.execute(
        text(
            """
            INSERT INTO organizations(
              id, slug, name, status, retention_policy_id, created_at, updated_at
            ) VALUES
              (:org1, 'deletion-one', 'Deletion One', 'active',
               md5(CAST(:org1 AS text) || '-retention-policy')::uuid, now(), now()),
              (:org2, 'deletion-two', 'Deletion Two', 'active',
               md5(CAST(:org2 AS text) || '-retention-policy')::uuid, now(), now())
            """
        ),
        ids,
    )
    connection.execute(
        text(
            """
            INSERT INTO users(
              id, organization_id, email, normalized_email, display_name,
              password_hash, status, authorization_version, created_at, updated_at
            ) VALUES
              (:user1, :org1, 'one@deletion.test', 'one@deletion.test', 'One',
               'x', 'active', 1, now(), now()),
              (:user2, :org2, 'two@deletion.test', 'two@deletion.test', 'Two',
               'x', 'active', 1, now(), now())
            """
        ),
        ids,
    )
    connection.execute(
        text(
            """
            INSERT INTO candidates(
              id, organization_id, display_name, version, created_at, updated_at
            ) VALUES (:candidate, :org1, 'Candidate', 3, now(), now())
            """
        ),
        ids,
    )
    return ids


def _insert_request(connection, ids: dict[str, uuid.UUID], **values: object) -> uuid.UUID:
    request_id = values.pop("request_id", uuid.uuid4())
    parameters = {
        **ids,
        "request_id": request_id,
        "organization_id": ids["org1"],
        "candidate_id": ids["candidate"],
        "requested_by": ids["user1"],
        "status": "requested",
        **values,
    }
    connection.execute(
        text(
            """
            INSERT INTO deletion_requests(
              id, organization_id, candidate_id, status, version, reason_code,
              requested_by, requested_at, impact_manifest, manifest_hash,
              manifest_schema_version, policy_version, candidate_version,
              recovery_generation, created_at, updated_at
            ) VALUES (
              :request_id, :organization_id, :candidate_id, :status, 1,
              'administrator_request', :requested_by, now(), '{}'::jsonb,
              repeat('a', 64), 1, 1, 3, 0, now(), now()
            )
            """
        ),
        parameters,
    )
    return request_id


def test_0017_upgrade_registers_additive_deletion_schema() -> None:
    url = os.environ["POSTGRES_SMOKE_URL"]
    _reset_to_0016a(url)
    _alembic(url, "upgrade", "head")
    engine = create_engine(url.replace("+asyncpg", "+psycopg"))
    inspector = inspect(engine)

    assert {
        "deletion_requests",
        "deletion_artifacts",
        "legal_holds",
        "deletion_recovery_runs",
    } <= set(inspector.get_table_names())
    assert "deleted_at" in {column["name"] for column in inspector.get_columns("candidates")}
    assert {
        "uq_deletion_requests_open_candidate",
        "uq_legal_holds_active_candidate",
    } <= {
        index["name"]
        for table in ("deletion_requests", "legal_holds")
        for index in inspector.get_indexes(table)
    }
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT has_function_privilege('public', 'redact_candidate_audit_evidence(uuid, uuid)', 'EXECUTE')")
        ) is False
    engine.dispose()


def test_0017_enforces_tenant_fks_partial_uniqueness_and_privileged_boundaries() -> None:
    url = os.environ["POSTGRES_SMOKE_URL"]
    _reset_to_0016a(url)
    _alembic(url, "upgrade", "0017_governance_deletion")
    engine = create_engine(url.replace("+asyncpg", "+psycopg"))

    with engine.begin() as connection:
        ids = _seed_identity(connection)

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            _insert_request(
                connection,
                ids,
                organization_id=ids["org2"],
                requested_by=ids["user2"],
            )

    with engine.begin() as connection:
        first_request = _insert_request(connection, ids)
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            _insert_request(connection, ids)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE deletion_requests SET status = 'completed', completed_at = now() WHERE id = :id"
            ),
            {"id": first_request},
        )
        _insert_request(connection, ids)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO legal_holds(
                  id, organization_id, candidate_id, reason, placed_by, placed_at,
                  version, created_at, updated_at
                ) VALUES (gen_random_uuid(), :org1, :candidate, 'First', :user1, now(), 1, now(), now())
                """
            ),
            ids,
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO legal_holds(
                      id, organization_id, candidate_id, reason, placed_by, placed_at,
                      version, created_at, updated_at
                    ) VALUES (gen_random_uuid(), :org1, :candidate, 'Second', :user1, now(), 1, now(), now())
                    """
                ),
                ids,
            )

    audit_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO audit_logs(
                  id, organization_id, actor_user_id, category, event_type, outcome,
                  resource_type, resource_id, trace_id, metadata_json, created_at
                ) VALUES (
                  :audit, :org1, :user1, 'governance', 'governance.deletion_requested',
                  'success', 'candidate', :candidate, 'task-b1', '{}'::jsonb, now()
                )
                """
            ),
            {**ids, "audit": audit_id},
        )
        connection.execute(
            text(
                """
                DO $$ BEGIN
                  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'task_b1_app') THEN
                    CREATE ROLE task_b1_app NOLOGIN;
                  END IF;
                END $$;
                GRANT USAGE ON SCHEMA public TO task_b1_app;
                GRANT SELECT, UPDATE ON audit_logs TO task_b1_app;
                """
            )
        )

    with pytest.raises(DBAPIError, match="permission denied"):
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL ROLE task_b1_app"))
            connection.execute(
                text("SELECT redact_candidate_audit_evidence(:org1, :candidate)"), ids
            )
    with pytest.raises(DBAPIError, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL ROLE task_b1_app"))
            connection.execute(
                text("UPDATE audit_logs SET outcome = 'failure' WHERE id = :audit"),
                {"audit": audit_id},
            )
    with pytest.raises(DBAPIError, match="audit redaction unavailable"):
        with engine.begin() as connection:
            connection.execute(
                text("SELECT redact_candidate_audit_evidence(:org1, :candidate)"), ids
            )

    engine.dispose()


def test_0017_empty_downgrade_removes_additive_schema() -> None:
    url = os.environ["POSTGRES_SMOKE_URL"]
    _reset_to_0016a(url)
    _alembic(url, "upgrade", "0017_governance_deletion")
    _alembic(url, "downgrade", "0016a_audit_category_repair")
    engine = create_engine(url.replace("+asyncpg", "+psycopg"))
    inspector = inspect(engine)

    assert not (
        {
            "deletion_requests",
            "deletion_artifacts",
            "legal_holds",
            "deletion_recovery_runs",
        }
        & set(inspector.get_table_names())
    )
    assert "deleted_at" not in {
        column["name"] for column in inspector.get_columns("candidates")
    }
    with engine.connect() as connection:
        assert connection.scalar(
            text("SELECT to_regprocedure('redact_candidate_audit_evidence(uuid, uuid)')")
        ) is None
    engine.dispose()


@pytest.mark.parametrize(
    "evidence",
    ["request_and_artifact", "hold", "recovery", "ledger", "tombstone"],
)
def test_0017_downgrade_refuses_when_deletion_evidence_exists(evidence: str) -> None:
    url = os.environ["POSTGRES_SMOKE_URL"]
    _reset_to_0016a(url)
    _alembic(url, "upgrade", "0017_governance_deletion")
    engine = create_engine(url.replace("+asyncpg", "+psycopg"))
    with engine.begin() as connection:
        ids = _seed_identity(connection)
        if evidence == "request_and_artifact":
            request_id = _insert_request(connection, ids)
            connection.execute(
                text(
                    """
                    INSERT INTO deletion_artifacts(
                      id, organization_id, request_id, kind, storage_key, status,
                      attempts, created_at, updated_at
                    ) VALUES (
                      gen_random_uuid(), :org1, :request, 'resume_object',
                      'private/key', 'pending', 0, now(), now()
                    )
                    """
                ),
                {**ids, "request": request_id},
            )
        elif evidence == "hold":
            connection.execute(
                text(
                    """
                    INSERT INTO legal_holds(
                      id, organization_id, candidate_id, reason, placed_by, placed_at,
                      version, created_at, updated_at
                    ) VALUES (gen_random_uuid(), :org1, :candidate, 'Hold', :user1, now(), 1, now(), now())
                    """
                ),
                ids,
            )
        elif evidence == "recovery":
            connection.execute(
                text(
                    """
                    INSERT INTO deletion_recovery_runs(
                      id, organization_id, restore_id, restored_at, status,
                      restored_candidate_count, requeued_request_count, queued_at,
                      created_at, updated_at
                    ) VALUES (
                      gen_random_uuid(), :org1, gen_random_uuid(), now(), 'queued',
                      0, 0, now(), now(), now()
                    )
                    """
                ),
                ids,
            )
        elif evidence == "ledger":
            connection.execute(
                text(
                    """
                    INSERT INTO audit_logs(
                      id, organization_id, actor_user_id, category, event_type, outcome,
                      resource_type, resource_id, trace_id, metadata_json, created_at
                    ) VALUES (
                      gen_random_uuid(), :org1, :user1, 'governance',
                      'governance.deletion_completed', 'success', 'candidate',
                      :candidate, 'task-b1-ledger', '{}'::jsonb, now()
                    )
                    """
                ),
                ids,
            )
        else:
            connection.execute(
                text("UPDATE candidates SET deleted_at = now() WHERE id = :candidate"), ids
            )

    result = _alembic(
        url, "downgrade", "0016a_audit_category_repair", check=False
    )
    try:
        assert result.returncode != 0
        assert "refusing 0017 downgrade: deletion governance evidence exists" in (
            result.stdout + result.stderr
        )
    finally:
        engine.dispose()
        _reset_to_0016a(url)
        _alembic(url, "upgrade", "head")
