from __future__ import annotations

import hashlib
import hmac
import json
import io
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select


SIGNING_KEY = b"recovery-ledger-signing-key-with-independent-entropy"


def _resign(document):
    unsigned = {key: value for key, value in document.items() if key != "signature"}
    encoded = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    document["signature"] = hmac.new(SIGNING_KEY, encoded, hashlib.sha256).hexdigest()


def _manifest(candidate_id, *, candidate_version=3, policy_version=2):
    return {
        "schema_version": 1,
        "candidate_id": str(candidate_id),
        "candidate_version": candidate_version,
        "policy_version": policy_version,
        "backup_window_ends_at": "2026-08-14T08:30:00Z",
        "row_ids": {
            "contacts": [],
            "resumes": [],
            "applications": [],
            "screening_items": [],
            "screening_results": [],
            "interviews": [],
            "feedback": [],
            "feedback_revisions": [],
            "talent_memberships": [],
        },
        "objects": {
            "resume_objects": [],
            "temporary_exports": [],
        },
        "counts": {
            "contacts": 0,
            "resumes": 0,
            "applications": 0,
            "screening_records": 0,
            "interviews": 0,
            "feedback_records": 0,
            "talent_memberships": 0,
            "resume_objects": 0,
            "temporary_exports": 0,
        },
    }


def _v2_entry():
    from server.app.governance.storage import LedgerArtifact, LedgerEntryV2

    organization_id = uuid4()
    candidate_id = uuid4()
    manifest = _manifest(candidate_id)
    resume_row_id = uuid4()
    export_row_id = uuid4()
    manifest["objects"] = {
        "resume_objects": [
            {"row_id": str(resume_row_id), "storage_key": "clean/a.pdf"}
        ],
        "temporary_exports": [
            {"row_id": str(export_row_id), "storage_key": "exports/b.csv"}
        ],
    }
    manifest["counts"]["resume_objects"] = 1
    manifest["counts"]["temporary_exports"] = 1
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return LedgerEntryV2(
        organization_id=organization_id,
        deletion_request_id=uuid4(),
        candidate_id=candidate_id,
        completed_request_version=4,
        completed_at=datetime(2026, 7, 15, 8, 30, tzinfo=timezone.utc),
        requested_at=datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
        reason_code="retention_expired",
        impact_manifest=manifest,
        manifest_hash=manifest_hash,
        recovery_generation=0,
        artifacts=(
            LedgerArtifact("report_export_object", "resumes", "exports/b.csv"),
            LedgerArtifact("resume_object", "resumes", "clean/a.pdf"),
        ),
        database_redaction_checksum="b" * 64,
    )


def test_ledger_v2_is_exact_canonical_and_round_trips() -> None:
    from server.app.governance.storage import LedgerEntryV2

    entry = _v2_entry()
    document = entry.signed_document(SIGNING_KEY)

    assert set(document) == {
        "schema_version",
        "organization_id",
        "deletion_request_id",
        "candidate_id",
        "completed_request_version",
        "completed_at",
        "requested_at",
        "reason_code",
        "impact_manifest",
        "manifest_hash",
        "recovery_generation",
        "artifacts",
        "database_redaction_checksum",
        "signature",
    }
    assert document["schema_version"] == 2
    assert document["artifacts"] == [
        {"kind": "report_export_object", "bucket": "resumes", "storage_key": "exports/b.csv"},
        {"kind": "resume_object", "bucket": "resumes", "storage_key": "clean/a.pdf"},
    ]
    assert LedgerEntryV2.verify_document(
        document, SIGNING_KEY, allowed_buckets={"resumes"}
    ) == entry


@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document.update(unexpected="field"),
        lambda document: document.update(completed_request_version=True),
        lambda document: document.update(reason_code="free text"),
        lambda document: document.update(manifest_hash="0" * 64),
        lambda document: document.update(artifacts=document["artifacts"] * 1001),
        lambda document: document["artifacts"].append(document["artifacts"][0]),
        lambda document: document["artifacts"][0].update(kind="unknown"),
        lambda document: document["artifacts"][0].update(bucket="other"),
        lambda document: document["artifacts"][0].update(storage_key="x" * 513),
        lambda document: document["artifacts"][0].update(storage_key="outside/b.csv"),
    ],
)
def test_ledger_v2_rejects_unknown_unbounded_conflicting_or_duplicate_evidence(mutate) -> None:
    from server.app.governance.storage import GovernanceStorageError, LedgerEntryV2

    document = _v2_entry().signed_document(SIGNING_KEY)
    mutate(document)
    _resign(document)

    with pytest.raises(GovernanceStorageError) as raised:
        LedgerEntryV2.verify_document(
            document,
            SIGNING_KEY,
            allowed_buckets={"resumes"},
            allowed_locations={
                "resume_object": ("resumes", "clean/"),
                "report_export_object": ("resumes", "exports/"),
            },
        )

    assert raised.value.code in {"ledger_invalid", "ledger_signature_invalid"}


def test_ledger_v2_rejects_duplicate_manifest_object_key_with_distinct_rows() -> None:
    from server.app.governance.storage import GovernanceStorageError, LedgerEntryV2

    document = _v2_entry().signed_document(SIGNING_KEY)
    objects = document["impact_manifest"]["objects"]["resume_objects"]
    objects.append({"row_id": str(uuid4()), "storage_key": objects[0]["storage_key"]})
    objects.sort(key=lambda item: (item["storage_key"], item["row_id"]))
    document["impact_manifest"]["counts"]["resume_objects"] = 2
    document["manifest_hash"] = hashlib.sha256(
        json.dumps(
            document["impact_manifest"], sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    _resign(document)

    with pytest.raises(GovernanceStorageError, match="ledger_invalid"):
        LedgerEntryV2.verify_document(
            document, SIGNING_KEY, allowed_buckets={"resumes"}
        )


def test_recovery_parser_rejects_valid_v1_ledger() -> None:
    from server.app.governance.storage import GovernanceStorageError, LedgerEntry

    v1 = LedgerEntry(
        organization_id=uuid4(),
        deletion_request_id=uuid4(),
        candidate_id=uuid4(),
        completed_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        manifest_hash="a" * 64,
        object_keys=(),
        database_redaction_checksum="b" * 64,
    )

    with pytest.raises(GovernanceStorageError) as raised:
        LedgerEntry.verify_recovery_document(
            v1.signed_document(SIGNING_KEY),
            SIGNING_KEY,
            allowed_buckets={"resumes"},
        )

    assert raised.value.code == "recovery_ledger_unsupported"


class DiscoveryLedger:
    def __init__(self, ledgers):
        self.ledgers = ledgers
        self.calls = 0

    def discover_recovery_ledgers(self, restored_at, *, maximum):
        self.calls += 1
        assert maximum > 0
        return self.ledgers


def _database_entry(app, user_id, *, completed_at=None):
    from server.app.governance.deletion_service import build_private_manifest, canonical_manifest_hash
    from server.app.governance.storage import LedgerEntryV2
    from server.app.identity.models import User
    from server.app.recruiting.models import Candidate
    from server.tests.test_governance_deletion_api import candidate_for

    candidate_id = candidate_for(app, user_id)
    with app.state.identity_store.sync_session() as db:
        user = db.get(User, user_id)
        candidate = db.get(Candidate, candidate_id)
        requested_at = datetime(2026, 7, 14, tzinfo=timezone.utc)
        manifest, _ = build_private_manifest(db, candidate, now=requested_at)
        return LedgerEntryV2(
            organization_id=user.organization_id,
            deletion_request_id=uuid4(),
            candidate_id=candidate_id,
            completed_request_version=2,
            completed_at=completed_at or datetime(2026, 7, 15, 8, 30, tzinfo=timezone.utc),
            requested_at=requested_at,
            reason_code="retention_expired",
            impact_manifest=manifest,
            manifest_hash=canonical_manifest_hash(manifest),
            recovery_generation=0,
            artifacts=(),
            database_redaction_checksum="c" * 64,
        )


def test_recovery_prepare_persists_checkpoints_and_jobs_only_after_all_ledgers_validate(
    tmp_path,
) -> None:
    from server.app.governance.deletion_models import (
        DeletionRecoveryCheckpoint,
        DeletionRecoveryRun,
    )
    from server.app.governance.recovery import PreparedLedger, RecoveryCoordinator
    from server.app.queue.models import BackgroundJob
    from server.tests.test_governance_deletion_api import make_app
    from server.tests.test_recruiting_api import seed_user

    app = make_app(tmp_path)
    user_id = seed_user(app, "system_admin", "recovery-prepare@example.test")
    first = _database_entry(app, user_id)
    second = _database_entry(
        app,
        user_id,
        completed_at=datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc),
    )
    ledger = DiscoveryLedger(
        [
            PreparedLedger("deletions/v2/first.json", "a" * 64, first),
            PreparedLedger("deletions/v2/second.json", "b" * 64, second),
        ]
    )
    restore_id = uuid4()
    restored_at = datetime(2026, 7, 14, 12, tzinfo=timezone.utc)

    prepared = RecoveryCoordinator(
        app.state.identity_store.sync_session,
        ledger,
        maximum_ledgers=100,
    ).prepare(restore_id, restored_at)

    assert prepared == 2
    assert ledger.calls == 1
    with app.state.identity_store.sync_session() as db:
        assert db.scalar(select(func.count()).select_from(DeletionRecoveryRun)) == 1
        assert db.scalar(select(func.count()).select_from(DeletionRecoveryCheckpoint)) == 2
        jobs = list(
            db.scalars(
                select(BackgroundJob).where(
                    BackgroundJob.type == "governance.redelete_after_restore"
                )
            )
        )
        assert len(jobs) == 2
        assert all(set(job.payload) == {"organization_id", "recovery_run_id", "checkpoint_id"} for job in jobs)

    assert RecoveryCoordinator(
        app.state.identity_store.sync_session,
        ledger,
        maximum_ledgers=100,
    ).prepare(restore_id, restored_at) == 0
    with app.state.identity_store.sync_session() as db:
        assert db.scalar(select(func.count()).select_from(DeletionRecoveryCheckpoint)) == 2


def test_recovery_prepare_conflicting_restore_timestamp_fails_without_mutation(tmp_path) -> None:
    from server.app.governance.deletion_models import DeletionRecoveryCheckpoint
    from server.app.governance.recovery import PreparedLedger, RecoveryCoordinator, RecoveryError
    from server.tests.test_governance_deletion_api import make_app
    from server.tests.test_recruiting_api import seed_user

    app = make_app(tmp_path)
    user_id = seed_user(app, "system_admin", "recovery-conflict@example.test")
    entry = _database_entry(app, user_id)
    ledger = DiscoveryLedger([PreparedLedger("deletions/v2/one.json", "a" * 64, entry)])
    coordinator = RecoveryCoordinator(
        app.state.identity_store.sync_session,
        ledger,
        maximum_ledgers=100,
    )
    restore_id = uuid4()
    coordinator.prepare(restore_id, datetime(2026, 7, 14, tzinfo=timezone.utc))

    with pytest.raises(RecoveryError) as raised:
        coordinator.prepare(restore_id, datetime(2026, 7, 13, tzinfo=timezone.utc))

    assert raised.value.code == "recovery_restore_conflict"
    assert ledger.calls == 1
    with app.state.identity_store.sync_session() as db:
        assert db.scalar(select(func.count()).select_from(DeletionRecoveryCheckpoint)) == 1


def test_recovery_prepare_records_empty_restore_for_idempotency_and_conflict(tmp_path) -> None:
    from server.app.governance.deletion_models import DeletionRecoveryRun
    from server.app.governance.recovery import RecoveryCoordinator, RecoveryError
    from server.tests.test_governance_deletion_api import make_app
    from server.tests.test_recruiting_api import seed_user

    app = make_app(tmp_path)
    seed_user(app, "system_admin", "recovery-empty@example.test")
    coordinator = RecoveryCoordinator(
        app.state.identity_store.sync_session,
        DiscoveryLedger([]),
        maximum_ledgers=100,
    )
    restore_id = uuid4()
    restored_at = datetime(2026, 7, 14, tzinfo=timezone.utc)

    assert coordinator.prepare(restore_id, restored_at) == 0
    with app.state.identity_store.sync_session() as db:
        run = db.scalar(select(DeletionRecoveryRun))
        assert run is not None
        assert run.status == "completed"

    assert coordinator.prepare(restore_id, restored_at) == 0
    with pytest.raises(RecoveryError, match="recovery_restore_conflict"):
        coordinator.prepare(
            restore_id, restored_at.replace(day=restored_at.day - 1)
        )


def test_openapi_has_no_recovery_route(tmp_path) -> None:
    from fastapi.testclient import TestClient
    from server.tests.test_governance_deletion_api import make_app

    with TestClient(make_app(tmp_path)) as client:
        paths = client.get("/openapi.json").json()["paths"]

    assert not any("recover" in path or "restore" in path or "redelete" in path for path in paths)


class ListingMemoryMinio:
    def __init__(self, objects):
        self.objects = objects
        self.list_calls = []

    def list_objects(self, bucket, *, prefix, recursive):
        self.list_calls.append((bucket, prefix, recursive))
        return [
            type("Object", (), {"object_name": key})()
            for (stored_bucket, key) in sorted(self.objects)
            if stored_bucket == bucket and key.startswith(prefix)
        ]

    def get_object(self, bucket, key):
        return io.BytesIO(self.objects[(bucket, key)])


def test_ledger_discovery_validates_v1_and_v2_before_filtering_applicable_entries() -> None:
    from server.app.governance.storage import LedgerEntry, SignedLedgerAdapter

    current = _v2_entry()
    old_v1 = LedgerEntry(
        organization_id=current.organization_id,
        deletion_request_id=uuid4(),
        candidate_id=current.candidate_id,
        completed_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        manifest_hash="a" * 64,
        object_keys=(),
        database_redaction_checksum="b" * 64,
    )
    documents = {
        ("ledger", f"deletions/v1/{old_v1.organization_id}/{old_v1.deletion_request_id}.json"):
            json.dumps(old_v1.signed_document(SIGNING_KEY), sort_keys=True, separators=(",", ":")).encode(),
        ("ledger", f"deletions/v2/{current.organization_id}/{current.deletion_request_id}.json"):
            json.dumps(current.signed_document(SIGNING_KEY), sort_keys=True, separators=(",", ":")).encode(),
    }
    client = ListingMemoryMinio(documents)
    adapter = SignedLedgerAdapter(
        client,
        "ledger",
        "deletions/",
        SIGNING_KEY,
        allowed_buckets={"resumes"},
    )

    discovered = adapter.discover_recovery_ledgers(
        datetime(2026, 7, 10, tzinfo=timezone.utc), maximum=10
    )

    assert len(discovered) == 1
    assert discovered[0].entry == current
    assert client.list_calls == [
        ("ledger", "deletions/", True),
    ]


def test_ledger_discovery_rejects_unknown_version_or_noncanonical_key() -> None:
    from server.app.governance.storage import GovernanceStorageError, SignedLedgerAdapter

    entry = _v2_entry()
    raw = json.dumps(
        entry.signed_document(SIGNING_KEY), sort_keys=True, separators=(",", ":")
    ).encode()
    adapter = SignedLedgerAdapter(
        ListingMemoryMinio({("ledger", "deletions/v3/unknown.json"): raw}),
        "ledger",
        "deletions/",
        SIGNING_KEY,
        allowed_buckets={"resumes"},
    )

    with pytest.raises(GovernanceStorageError, match="recovery_ledger_invalid"):
        adapter.discover_recovery_ledgers(
            datetime(2026, 7, 10, tzinfo=timezone.utc), maximum=10
        )


def test_ledger_discovery_rejects_applicable_v1_and_limit_before_returning_anything() -> None:
    from server.app.governance.storage import GovernanceStorageError, LedgerEntry, SignedLedgerAdapter

    future_v1 = LedgerEntry(
        organization_id=uuid4(),
        deletion_request_id=uuid4(),
        candidate_id=uuid4(),
        completed_at=datetime(2026, 7, 15, tzinfo=timezone.utc),
        manifest_hash="a" * 64,
        object_keys=(),
        database_redaction_checksum="b" * 64,
    )
    key = f"deletions/v1/{future_v1.organization_id}/{future_v1.deletion_request_id}.json"
    raw = json.dumps(future_v1.signed_document(SIGNING_KEY), sort_keys=True, separators=(",", ":")).encode()
    adapter = SignedLedgerAdapter(
        ListingMemoryMinio({("ledger", key): raw}),
        "ledger",
        "deletions/",
        SIGNING_KEY,
        allowed_buckets={"resumes"},
    )

    with pytest.raises(GovernanceStorageError) as raised:
        adapter.discover_recovery_ledgers(
            datetime(2026, 7, 10, tzinfo=timezone.utc), maximum=10
        )
    assert raised.value.code == "recovery_ledger_unsupported"

    with pytest.raises(GovernanceStorageError) as limited:
        adapter.discover_recovery_ledgers(
            datetime(2026, 7, 20, tzinfo=timezone.utc), maximum=0
        )
    assert limited.value.code == "recovery_ledger_limit_exceeded"


def test_recovery_worker_reconstructs_minimum_evidence_redeletes_and_is_idempotent(
    tmp_path, monkeypatch
) -> None:
    import asyncio
    from contextlib import contextmanager
    from types import SimpleNamespace

    from server.app.governance import recovery as recovery_module
    from server.app.governance.deletion_models import (
        DeletionArtifact,
        DeletionRecoveryCheckpoint,
        DeletionRecoveryRun,
        DeletionRequest,
    )
    from server.app.governance.deletion_service import DatabaseRedactionResult
    from server.app.governance.recovery import PreparedLedger, RecoveryCoordinator, RecoveryJobHandler
    from server.app.governance.storage import LedgerArtifact, LedgerEntryV2
    from server.app.identity.models import User
    from server.app.recruiting.models import Candidate, FileObject, Resume
    from server.tests.test_governance_deletion_api import candidate_for, make_app
    from server.tests.test_recruiting_api import seed_user

    app = make_app(tmp_path)
    user_id = seed_user(app, "system_admin", "recovery-worker@example.test")
    candidate_id = candidate_for(app, user_id)
    with app.state.identity_store.sync_session.begin() as db:
        user = db.get(User, user_id)
        candidate = db.get(Candidate, candidate_id)
        stored = FileObject(
            organization_id=user.organization_id,
            storage_key="clean/recovery.pdf",
            original_filename="private.pdf",
            mime_type="application/pdf",
            size_bytes=7,
            sha256="d" * 64,
            uploaded_by=user_id,
        )
        db.add(stored)
        db.flush()
        db.add(
            Resume(
                organization_id=user.organization_id,
                candidate_id=candidate_id,
                file_object_id=stored.id,
                version_number=1,
                parsed_text="private resume",
            )
        )
        db.flush()
        manifest, _ = __import__(
            "server.app.governance.deletion_service", fromlist=["build_private_manifest"]
        ).build_private_manifest(db, candidate, now=datetime(2026, 7, 14, tzinfo=timezone.utc))
        manifest_hash = __import__(
            "server.app.governance.deletion_service", fromlist=["canonical_manifest_hash"]
        ).canonical_manifest_hash(manifest)
        entry = LedgerEntryV2(
            organization_id=user.organization_id,
            deletion_request_id=uuid4(),
            candidate_id=candidate_id,
            completed_request_version=2,
            completed_at=datetime(2026, 7, 15, 8, 30, tzinfo=timezone.utc),
            requested_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
            reason_code="retention_expired",
            impact_manifest=manifest,
            manifest_hash=manifest_hash,
            recovery_generation=0,
            artifacts=(LedgerArtifact("resume_object", "resumes", "clean/recovery.pdf"),),
            database_redaction_checksum="c" * 64,
        )
        organization_id = user.organization_id

    prepared = PreparedLedger("deletions/v2/recovery.json", "a" * 64, entry)

    class Ledger:
        def discover_recovery_ledgers(self, restored_at, *, maximum):
            return (prepared,)

        def read_recovery(self, object_key, expected_sha256):
            assert (object_key, expected_sha256) == (prepared.object_key, prepared.sha256)
            return entry

    restore_id = uuid4()
    coordinator = RecoveryCoordinator(
        app.state.identity_store.sync_session, Ledger(), maximum_ledgers=10
    )
    assert coordinator.prepare(
        restore_id, datetime(2026, 7, 14, 12, tzinfo=timezone.utc)
    ) == 1
    with app.state.identity_store.sync_session() as db:
        checkpoint = db.scalar(select(DeletionRecoveryCheckpoint))
        run = db.scalar(select(DeletionRecoveryRun))
        assert checkpoint.target_generation == 1
        job = SimpleNamespace(
            organization_id=organization_id,
            payload={
                "organization_id": str(organization_id),
                "recovery_run_id": str(run.id),
                "checkpoint_id": str(checkpoint.id),
            },
            trace_id="recovery-worker-test",
        )

    events = []

    class Deleter:
        def delete(self, bucket, key):
            events.append(("delete", bucket, key))

    class Engine:
        @contextmanager
        def begin(self):
            yield object()

    def redact(_connection, *, organization_id, request_id, candidate_id):
        events.append(("redact",))
        with app.state.identity_store.sync_session.begin() as db:
            candidate = db.get(Candidate, candidate_id)
            candidate.deleted_at = datetime(2026, 7, 15, 10, tzinfo=timezone.utc)
            candidate.display_name = "已删除候选人"
            candidate.version += 1
        return DatabaseRedactionResult("e" * 64, (0, 1, 0, 0, 0, 0, 0, 1, 0))

    monkeypatch.setattr(recovery_module, "execute_database_redaction", redact)
    handler = RecoveryJobHandler(
        app.state.identity_store.sync_session,
        Engine(),
        Deleter(),
        Ledger(),
    )
    asyncio.run(handler(job))
    asyncio.run(handler(job))

    assert events == [("delete", "resumes", "clean/recovery.pdf"), ("redact",)]
    with app.state.identity_store.sync_session() as db:
        request = db.get(DeletionRequest, entry.deletion_request_id)
        checkpoint = db.scalar(select(DeletionRecoveryCheckpoint))
        run = db.scalar(select(DeletionRecoveryRun))
        artifact = db.scalar(select(DeletionArtifact))
        candidate = db.get(Candidate, candidate_id)
        assert request.status == "completed"
        assert request.recovery_generation == 1
        assert request.version == entry.completed_request_version
        assert request.requested_by is None
        assert request.impact_manifest == entry.impact_manifest
        assert request.database_redaction_checksum == entry.database_redaction_checksum
        assert request.ledger_object_key == prepared.object_key
        assert checkpoint.status == "completed"
        assert run.status == "completed"
        assert run.restored_candidate_count == 1
        assert run.requeued_request_count == 1
        assert artifact.status == "deleted"
        assert candidate.deleted_at is not None


def test_recovery_cli_accepts_only_restore_id_and_rfc3339_timestamp() -> None:
    from server.app.governance.redelete_after_restore import parse_args

    restore_id = uuid4()
    parsed = parse_args(
        [
            "--restore-id",
            str(restore_id),
            "--restored-at",
            "2026-07-15T08:30:00Z",
        ]
    )
    assert parsed.restore_id == restore_id
    assert parsed.restored_at == datetime(2026, 7, 15, 8, 30, tzinfo=timezone.utc)

    for invalid in (
        ["--restore-id", str(restore_id)],
        ["--restore-id", str(restore_id), "--restored-at", "2026-07-15"],
        [
            "--restore-id",
            str(restore_id),
            "--restored-at",
            "2026-07-15T08:30:00Z",
            "--organization-id",
            str(uuid4()),
        ],
    ):
        with pytest.raises(SystemExit):
            parse_args(invalid)


def test_recovery_cli_database_preflight_enforces_separate_app_and_executor_identities() -> None:
    from server.app.governance.redelete_after_restore import (
        _validate_application_database_identity,
        _validate_governance_database_identity,
    )
    from server.app.governance.recovery import RecoveryError

    class Result:
        def __init__(self, row):
            self.row = row

        def one(self):
            return self.row

    class Connection:
        dialect = type("Dialect", (), {"name": "postgresql"})()

        def __init__(self, row):
            self.row = row

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _statement):
            return Result(self.row)

    class Engine:
        def __init__(self, row):
            self.row = row

        def connect(self):
            return Connection(self.row)

    _validate_application_database_identity(
        Engine(("app", False)), "postgresql+psycopg://app:secret@postgres/app"
    )
    _validate_governance_database_identity(
        Engine(("governance", True)),
        "postgresql+psycopg://governance:secret@postgres/app",
    )
    with pytest.raises(RecoveryError, match="recovery_database_identity_invalid"):
        _validate_application_database_identity(
            Engine(("app", True)), "postgresql+psycopg://app:secret@postgres/app"
        )
    with pytest.raises(RecoveryError, match="recovery_database_identity_invalid"):
        _validate_governance_database_identity(
            Engine(("governance", False)),
            "postgresql+psycopg://governance:secret@postgres/app",
        )


def test_recovery_cli_storage_preflight_consumes_delete_only_list_permissions() -> None:
    from server.app.governance.redelete_after_restore import _validate_storage_permissions
    from server.app.governance.recovery import RecoveryError

    class Client:
        def __init__(self, *, fail=False):
            self.fail = fail
            self.calls = []

        def list_objects(self, bucket, *, prefix, recursive):
            self.calls.append(("list", bucket, prefix, recursive))
            if self.fail:
                raise RuntimeError("policy rejected")
            yield object()

    delete = Client()
    ledger = Client()
    _validate_storage_permissions(
        delete,
        ledger,
        resume_bucket="resumes",
        resume_prefix="clean/",
        export_bucket="exports",
        export_prefix="exports/",
        ledger_bucket="ledger",
        ledger_prefix="deletions/",
    )
    assert delete.calls == [
        ("list", "resumes", "clean/", True),
        ("list", "exports", "exports/", True),
    ]
    assert ledger.calls == [
        ("list", "ledger", "deletions/", True),
    ]
    with pytest.raises(RecoveryError, match="recovery_storage_permission_invalid"):
        _validate_storage_permissions(
            Client(fail=True),
            Client(),
            resume_bucket="resumes",
            resume_prefix="clean/",
            export_bucket="exports",
            export_prefix="exports/",
            ledger_bucket="ledger",
            ledger_prefix="deletions/",
        )
