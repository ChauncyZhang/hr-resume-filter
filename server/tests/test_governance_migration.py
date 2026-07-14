import os
import subprocess
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text


pytestmark = pytest.mark.skipif(
    not os.getenv("POSTGRES_SMOKE_URL"), reason="PostgreSQL smoke URL not configured"
)


def _alembic(url: str, *args: str) -> None:
    subprocess.run(
        ["python", "-m", "alembic", "-c", "server/alembic.ini", *args],
        check=True,
        env={**os.environ, "DATABASE_URL": url},
    )


def test_0016_empty_upgrade_and_downgrade() -> None:
    url = os.environ["POSTGRES_SMOKE_URL"]
    engine = create_engine(url.replace("+asyncpg", "+psycopg"))
    _alembic(url, "downgrade", "base")
    _alembic(url, "upgrade", "0015_reports_exports")
    _alembic(url, "upgrade", "0016_governance_audit_retention")

    inspector = inspect(engine)
    assert "retention_policies" in inspector.get_table_names()
    assert {"category", "resource_type", "resource_id", "ip_hash"} <= {
        column["name"] for column in inspector.get_columns("audit_logs")
    }

    _alembic(url, "downgrade", "0015_reports_exports")
    inspector.clear_cache()
    assert "retention_policies" not in inspector.get_table_names()
    assert "category" not in {
        column["name"] for column in inspector.get_columns("audit_logs")
    }
    _alembic(url, "upgrade", "head")
    engine.dispose()


def test_0016_backfills_populated_0015_and_preserves_audit_on_downgrade() -> None:
    url = os.environ["POSTGRES_SMOKE_URL"]
    engine = create_engine(url.replace("+asyncpg", "+psycopg"))
    _alembic(url, "downgrade", "base")
    _alembic(url, "upgrade", "0015_reports_exports")
    ids = {name: uuid.uuid4() for name in ("org", "user", "candidate", "audit", "idem")}

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO organizations(id, slug, name, status, created_at, updated_at)
                VALUES (:org, 'governance-migration', 'Governance migration', 'active', now(), now())
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
                ) VALUES (
                  :user, :org, 'governance@test', 'governance@test', 'Governance',
                  'x', 'active', 1, now(), now()
                )
                """
            ),
            ids,
        )
        connection.execute(
            text(
                """
                INSERT INTO candidates(
                  id, organization_id, display_name, version, created_at, updated_at
                ) VALUES (:candidate, :org, 'Candidate', 1, now(), now())
                """
            ),
            ids,
        )
        connection.execute(
            text(
                """
                INSERT INTO idempotency_records(
                  id, organization_id, user_id, operation, idempotency_key,
                  request_hash, status_code, response_json, created_at
                ) VALUES (
                  :idem, :org, :user, 'candidate.create', 'migration-key',
                  repeat('a', 64), 201, '{}', now() - interval '1 hour'
                )
                """
            ),
            ids,
        )
        connection.execute(
            text(
                """
                INSERT INTO audit_logs(
                  id, organization_id, actor_user_id, event_type, outcome,
                  trace_id, metadata_json, created_at
                ) VALUES (
                  :audit, :org, :user, 'candidate.created', 'success',
                  'trace-migration', jsonb_build_object('candidate_id', CAST(:candidate AS text)), now()
                )
                """
            ),
            ids,
        )

    _alembic(url, "upgrade", "0016_governance_audit_retention")
    with engine.connect() as connection:
        policy = connection.execute(
            text(
                """
                SELECT p.id, p.terminal_days, p.talent_pool_days, p.backup_window_days,
                       p.version, p.updated_by, o.retention_policy_id
                FROM retention_policies p
                JOIN organizations o ON o.id = p.organization_id
                WHERE p.organization_id = :org
                """
            ),
            ids,
        ).one()
        assert policy[1:5] == (365, 730, 90, 1)
        assert policy.updated_by == ids["user"]
        assert policy.id == policy.retention_policy_id
        assert connection.scalar(
            text("SELECT retention_due_at IS NULL FROM candidates WHERE id = :candidate"), ids
        )
        assert connection.scalar(
            text(
                """
                SELECT expires_at = created_at + interval '24 hours'
                FROM idempotency_records WHERE id = :idem
                """
            ),
            ids,
        )
        audit = connection.execute(
            text(
                """
                SELECT category, resource_type, resource_id,
                       metadata_json ? 'candidate_id', tableoid::regclass::text
                FROM audit_logs WHERE id = :audit
                """
            ),
            ids,
        ).one()
        assert audit[:4] == ("recruiting", "candidate", ids["candidate"], False)
        assert audit[4].startswith("audit_logs_") and audit[4] != "audit_logs_default"

    with pytest.raises(Exception, match="append-only"):
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE audit_logs SET outcome = 'failure' WHERE id = :audit"), ids
            )
    with pytest.raises(Exception, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM audit_logs WHERE id = :audit"), ids)

    _alembic(url, "downgrade", "0015_reports_exports")
    with engine.connect() as connection:
        legacy = connection.execute(
            text(
                """
                SELECT event_type, metadata_json ->> 'candidate_id'
                FROM audit_logs WHERE id = :audit
                """
            ),
            ids,
        ).one()
        assert legacy == ("candidate.created", str(ids["candidate"]))
        assert connection.scalar(
            text("SELECT count(*) FROM candidates WHERE id = :candidate"), ids
        ) == 1
        assert connection.scalar(
            text("SELECT count(*) FROM idempotency_records WHERE id = :idem"), ids
        ) == 1

    with pytest.raises(Exception, match="append-only"):
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM audit_logs WHERE id = :audit"), ids)

    _alembic(url, "upgrade", "head")
    engine.dispose()
