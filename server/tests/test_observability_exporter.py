from prometheus_client import generate_latest
from prometheus_client.parser import text_string_to_metric_families
import os
import uuid

import pytest
from psycopg import connect


def test_exporter_emits_generic_job_attempt_lease_and_outbox_metrics() -> None:
    from server.app.observability.collectors import AttemptStats, QueueSnapshot
    from server.app.observability.exporter import build_registry

    snapshot = QueueSnapshot(
        job_counts={
            ("screening.parse_item", "queued"): 2,
            ("screening.llm_score_item", "dead_letter"): 1,
        },
        oldest_ready_age_seconds={"screening.parse_item": 125.0},
        attempt_stats={
            ("screening.parse_item", "failed", "parse"): AttemptStats(
                count=3, duration_seconds=4.5
            )
        },
        expired_leases={"job": 1, "outbox": 2},
        dead_letters={"screening.llm_score_item": 1},
        outbox_counts={("audit.created", "queued"): 4},
        oldest_outbox_age_seconds={"audit.created": 65.0},
    )

    payload = generate_latest(build_registry(lambda: snapshot)).decode("utf-8")

    assert 'ux09_jobs{job_type="screening.parse_item",status="queued"} 2.0' in payload
    assert "ux09_job_oldest_ready_age_seconds" in payload
    assert 'error_class="parse"' in payload
    assert 'queue="job"' in payload
    assert 'queue="outbox"' in payload
    assert "ux09_job_dead_letters" in payload
    assert 'topic="audit.created"' in payload
    assert "ux09_outbox_oldest_ready_age_seconds" in payload


def test_governance_job_metrics_are_disabled() -> None:
    from server.app.observability.collectors import QueueSnapshot
    from server.app.observability.exporter import build_registry

    snapshot = QueueSnapshot(
        job_counts={("governance.delete_candidate", "queued"): 9},
        oldest_ready_age_seconds={"governance.delete_candidate": 99.0},
        dead_letters={"governance.delete_candidate": 2},
    )

    payload = generate_latest(build_registry(lambda: snapshot)).decode("utf-8")

    assert "governance" not in payload


def test_real_postgres_snapshot_exports_queue_metrics_without_private_dimensions() -> None:
    database_url = os.environ.get("POSTGRES_OBSERVABILITY_SMOKE_URL")
    if not database_url:
        pytest.skip("POSTGRES_OBSERVABILITY_SMOKE_URL is required for the real collector gate")

    from server.app.observability.collectors import PostgresQueueSnapshotProvider
    from server.app.observability.exporter import build_registry

    parse_job = uuid.uuid4()
    canary_type = "alice.canary@example.test"
    with connect(database_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DROP TABLE IF EXISTS job_attempts, outbox_events, background_jobs;
                CREATE TABLE background_jobs (
                    id uuid PRIMARY KEY, type text NOT NULL, status text NOT NULL,
                    run_after timestamptz NOT NULL, lease_expires_at timestamptz
                );
                CREATE TABLE job_attempts (
                    job_id uuid NOT NULL, result text, safe_error_code text,
                    duration_ms integer
                );
                CREATE TABLE outbox_events (
                    topic text NOT NULL, status text NOT NULL,
                    available_at timestamptz NOT NULL, lease_expires_at timestamptz
                );
                """
            )
            cursor.execute(
                """
                INSERT INTO background_jobs (id, type, status, run_after, lease_expires_at)
                VALUES (%s, 'screening.parse_item', 'queued', now() - interval '2 minutes', NULL),
                       (%s, 'screening.llm_score_item', 'dead_letter', now(), NULL),
                       (%s, 'governance.delete_candidate', 'queued', now() - interval '1 hour', NULL),
                       (%s, %s, 'queued', now(), NULL)
                """,
                (parse_job, uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), canary_type),
            )
            cursor.execute(
                """INSERT INTO job_attempts (job_id, result, safe_error_code, duration_ms)
                   VALUES (%s, 'failed', 'parser_timeout', 1500)""",
                (parse_job,),
            )
            cursor.execute(
                """INSERT INTO outbox_events (topic, status, available_at, lease_expires_at)
                   VALUES ('audit.created', 'queued', now() - interval '1 minute', NULL)"""
            )

    payload = generate_latest(
        build_registry(PostgresQueueSnapshotProvider(database_url))
    ).decode("utf-8")
    samples = [
        sample
        for family in text_string_to_metric_families(payload)
        for sample in family.samples
    ]

    assert 'job_type="screening.parse_item",status="queued"' in payload
    assert 'job_type="screening.llm_score_item"' in payload
    assert 'error_class="parse"' in payload
    assert any(
        sample.name == "ux09_outbox_events"
        and sample.labels == {"topic": "audit.created", "status": "queued"}
        and sample.value == 1
        for sample in samples
    )
    assert "governance" not in payload
    assert canary_type not in payload
