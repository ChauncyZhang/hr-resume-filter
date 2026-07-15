import asyncio
import io
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from server.app.governance.deletion_models import DeletionArtifact, DeletionRequest, LegalHold
from server.app.governance.deletion_service import DatabaseRedactionResult
from server.app.governance.storage import GovernanceStorageError, LedgerReceipt
from server.app.identity.models import AuditLog, Job
from server.app.queue.service import PermanentJobError, RetryableJobError
from server.app.queue.models import BackgroundJob
from server.app.recruiting.models import (
    Application,
    Candidate,
    FileObject,
    JobJdVersion,
    Resume,
    ScreeningRuleVersion,
)
from server.app.reports.models import ExportCandidateMembership, ExportRecord
from server.app.screening.models import ScreeningItem, ScreeningRun
from server.tests.test_governance_deletion_api import (
    approve,
    candidate_for,
    make_app,
    request_deletion,
)
from server.tests.test_recruiting_api import login, seed_user


def _job(job_organization_id, request_id, version, **changes):
    payload = {
        "organization_id": str(job_organization_id),
        "deletion_request_id": str(request_id),
        "request_version": version,
    }
    payload.update(changes)
    return SimpleNamespace(
        id=uuid4(),
        organization_id=job_organization_id,
        type="governance.delete_candidate",
        payload=payload,
        attempts=1,
        trace_id="governance-delete-test",
    )


@pytest.mark.parametrize(
    "payload_change",
    [
        {"request_version": True},
        {"request_version": 0},
        {"deletion_request_id": "not-a-uuid"},
        {"unexpected": "field"},
    ],
)
def test_deletion_handler_rejects_non_exact_payload_before_dependencies(payload_change) -> None:
    from server.app.governance.worker import DeletionJobHandler

    organization_id = uuid4()
    handler = DeletionJobHandler(
        sessions=None,
        governance_engine=None,
        object_deleter=None,
        ledger=None,
        resume_bucket="resumes",
        export_bucket="resumes",
    )

    with pytest.raises(PermanentJobError) as raised:
        asyncio.run(handler(_job(organization_id, uuid4(), 2, **payload_change)))

    assert raised.value.safe_code == "deletion_payload_invalid"


def test_deletion_handler_rejects_payload_tenant_mismatch_before_dependencies() -> None:
    from server.app.governance.worker import DeletionJobHandler

    handler = DeletionJobHandler(
        sessions=None,
        governance_engine=None,
        object_deleter=None,
        ledger=None,
        resume_bucket="resumes",
        export_bucket="resumes",
    )

    with pytest.raises(PermanentJobError) as raised:
        asyncio.run(handler(_job(uuid4(), uuid4(), 2, organization_id=str(uuid4()))))

    assert raised.value.safe_code == "deletion_payload_invalid"


def test_production_registry_contains_deletion_handler_and_terminal_callback() -> None:
    from server.app.worker.main import build_terminal_callbacks

    assert "governance.delete_candidate" in build_terminal_callbacks()


class RecordingDeleter:
    def __init__(self, events, fail_key=None):
        self.events = events
        self.fail_key = fail_key
        self.failed = False

    def delete(self, bucket, key):
        self.events.append(("delete", bucket, key))
        if key == self.fail_key and not self.failed:
            self.failed = True
            raise GovernanceStorageError("object_delete_failed")


class RecordingLedger:
    def __init__(self, events, fail_first_write=False):
        self.events = events
        self.entry = None
        self.fail_first_write = fail_first_write

    def write(self, entry):
        self.events.append(("ledger_write", entry))
        if self.fail_first_write:
            self.fail_first_write = False
            raise GovernanceStorageError("ledger_write_failed")
        self.entry = entry
        return LedgerReceipt("deletions/test.json", "a" * 64)

    def read(self, object_key):
        self.events.append(("ledger_read", object_key))
        return self.entry


class FakeGovernanceEngine:
    @contextmanager
    def begin(self):
        yield object()


def _approved_request(app):
    requester_id = seed_user(app, "recruiter", "worker-requester@deletion.test")
    seed_user(app, "system_admin", "worker-approver@deletion.test")
    candidate_id = candidate_for(app, requester_id)
    with app.state.identity_store.sync_session() as db:
        candidate = db.get(Candidate, candidate_id)
        for index in (1, 2):
            file = FileObject(
                organization_id=candidate.organization_id,
                storage_key=f"clean/{candidate.organization_id}/{index}.pdf",
                original_filename=f"private-{index}.pdf",
                mime_type="application/pdf",
                size_bytes=10,
                sha256=str(index) * 64,
                uploaded_by=requester_id,
            )
            db.add(file)
            db.flush()
            db.add(
                Resume(
                    organization_id=candidate.organization_id,
                    candidate_id=candidate.id,
                    file_object_id=file.id,
                    version_number=index,
                    parsed_text=f"private resume {index}",
                )
            )
        db.commit()
        organization_id = candidate.organization_id
    with TestClient(app) as client:
        requested = request_deletion(
            client,
            login(client, "worker-requester@deletion.test"),
            candidate_id,
        )
        approved = approve(
            client,
            login(client, "worker-approver@deletion.test"),
            requested.json()["data"]["id"],
            1,
        )
    assert approved.status_code == 200
    return organization_id, candidate_id, UUID(approved.json()["data"]["id"])


def _screening_job_for_candidate(
    app,
    organization_id,
    candidate_id,
    request_id,
    *,
    job_type,
    item_status,
    llm_status="not_requested",
    queue_status="running",
    active_lease=True,
):
    from server.app.governance.deletion_service import (
        build_private_manifest,
        canonical_manifest_hash,
    )

    now = datetime.now(timezone.utc)
    with app.state.identity_store.sync_session.begin() as db:
        candidate = db.get(Candidate, candidate_id)
        request = db.get(DeletionRequest, request_id)
        resume = db.scalar(select(Resume).where(Resume.candidate_id == candidate_id))
        stored = db.get(FileObject, resume.file_object_id)
        recruiting_job = Job(
            organization_id=organization_id,
            title="Deletion screening barrier",
            owner_id=candidate.owner_id,
            status="closed",
        )
        db.add(recruiting_job)
        db.flush()
        jd = JobJdVersion(
            organization_id=organization_id,
            job_id=recruiting_job.id,
            version_number=1,
            content={"text": "Python"},
            created_by=candidate.owner_id,
        )
        rule = ScreeningRuleVersion(
            organization_id=organization_id,
            job_id=recruiting_job.id,
            version_number=1,
            content={},
            created_by=candidate.owner_id,
        )
        db.add_all([jd, rule])
        db.flush()
        run = ScreeningRun(
            organization_id=organization_id,
            job_id=recruiting_job.id,
            jd_version_id=jd.id,
            rule_version_id=rule.id,
            source="upload",
            status="parsing",
            total_count=1,
            processed_count=0,
            succeeded_count=0,
            failed_count=0,
            created_by=candidate.owner_id,
        )
        db.add(run)
        db.flush()
        item = ScreeningItem(
            organization_id=organization_id,
            run_id=run.id,
            file_object_id=stored.id,
            candidate_id=candidate_id,
            resume_id=resume.id,
            status=item_status,
            attempts=1,
            llm_status=llm_status,
        )
        db.add(item)
        db.flush()
        payload = {
            "organization_id": str(organization_id),
            "screening_item_id": str(item.id),
        }
        queued = BackgroundJob(
            organization_id=organization_id,
            type=job_type,
            payload=payload,
            status=queue_status,
            priority=0,
            attempts=1 if queue_status == "running" else 0,
            max_attempts=3,
            run_after=now,
            lease_owner="screening-worker" if queue_status == "running" else None,
            lease_expires_at=(
                now + timedelta(minutes=5)
                if queue_status == "running" and active_lease
                else now - timedelta(minutes=5)
                if queue_status == "running"
                else None
            ),
            heartbeat_at=now if queue_status == "running" else None,
            dedupe_key=f"barrier:{item.id}:{job_type}",
            created_at=now,
            updated_at=now,
        )
        db.add(queued)
        db.flush()
        manifest, policy = build_private_manifest(db, candidate, now=request.requested_at)
        request.impact_manifest = manifest
        request.manifest_hash = canonical_manifest_hash(manifest)
        request.policy_version = policy.version
        return item.id, queued.id


@pytest.mark.parametrize(
    ("job_type", "item_status", "llm_status"),
    [
        ("screening.score_item", "parsed", "not_requested"),
        ("screening.llm_score_item", "scored", "queued"),
    ],
)
def test_claim_waits_for_active_screening_lease_before_side_effects(
    tmp_path, job_type, item_status, llm_status
) -> None:
    from server.app.governance.worker import DeletionJobHandler

    app = make_app(tmp_path)
    organization_id, candidate_id, request_id = _approved_request(app)
    _item_id, queue_job_id = _screening_job_for_candidate(
        app,
        organization_id,
        candidate_id,
        request_id,
        job_type=job_type,
        item_status=item_status,
        llm_status=llm_status,
    )
    handler = DeletionJobHandler(
        sessions=app.state.identity_store.sync_session,
        governance_engine=FakeGovernanceEngine(),
        object_deleter=RecordingDeleter([]),
        ledger=RecordingLedger([]),
        resume_bucket="resumes",
        export_bucket="resumes",
    )

    with pytest.raises(RetryableJobError) as raised:
        handler._claim(organization_id, request_id, 2, "screening-order")

    assert raised.value.safe_code == "deletion_screening_inflight"
    with app.state.identity_store.sync_session() as db:
        assert db.get(DeletionRequest, request_id).status == "approved"
        assert db.get(BackgroundJob, queue_job_id).status == "running"
        assert db.scalar(select(DeletionArtifact.id)) is None


@pytest.mark.parametrize(
    "job_type",
    [
        "screening.parse_item",
        "screening.score_item",
        "screening.llm_score_item",
    ],
)
def test_claim_cancels_queued_screening_work_before_executing(
    tmp_path, job_type
) -> None:
    from server.app.governance.worker import DeletionJobHandler

    app = make_app(tmp_path)
    organization_id, candidate_id, request_id = _approved_request(app)
    _item_id, queue_job_id = _screening_job_for_candidate(
        app,
        organization_id,
        candidate_id,
        request_id,
        job_type=job_type,
        item_status="scored" if job_type == "screening.llm_score_item" else "queued",
        llm_status="queued" if job_type == "screening.llm_score_item" else "not_requested",
        queue_status="queued",
    )
    handler = DeletionJobHandler(
        sessions=app.state.identity_store.sync_session,
        governance_engine=FakeGovernanceEngine(),
        object_deleter=RecordingDeleter([]),
        ledger=RecordingLedger([]),
        resume_bucket="resumes",
        export_bucket="resumes",
    )

    assert handler._claim(organization_id, request_id, 2, "screening-cancel") is False

    with app.state.identity_store.sync_session() as db:
        assert db.get(DeletionRequest, request_id).status == "executing"
        assert db.get(BackgroundJob, queue_job_id).status == "cancelled"


def test_expired_screening_lease_does_not_permanently_block_or_get_cancelled(
    tmp_path,
) -> None:
    from server.app.governance.worker import DeletionJobHandler

    app = make_app(tmp_path)
    organization_id, candidate_id, request_id = _approved_request(app)
    _item_id, queue_job_id = _screening_job_for_candidate(
        app,
        organization_id,
        candidate_id,
        request_id,
        job_type="screening.score_item",
        item_status="scoring",
        active_lease=False,
    )
    handler = DeletionJobHandler(
        sessions=app.state.identity_store.sync_session,
        governance_engine=FakeGovernanceEngine(),
        object_deleter=RecordingDeleter([]),
        ledger=RecordingLedger([]),
        resume_bucket="resumes",
        export_bucket="resumes",
    )

    assert handler._claim(organization_id, request_id, 2, "screening-expired") is False

    with app.state.identity_store.sync_session() as db:
        assert db.get(DeletionRequest, request_id).status == "executing"
        assert db.get(BackgroundJob, queue_job_id).status == "running"


def test_object_checkpoint_resume_precedes_redaction_and_ledger(tmp_path, monkeypatch) -> None:
    from server.app.governance import worker as deletion_worker
    from server.app.governance.worker import DeletionJobHandler
    from server.app.queue.service import RetryableJobError

    app = make_app(tmp_path)
    organization_id, candidate_id, request_id = _approved_request(app)
    events = []
    second_key = f"clean/{organization_id}/2.pdf"
    deleter = RecordingDeleter(events, fail_key=second_key)
    ledger = RecordingLedger(events)

    def redact(_connection, *, organization_id, request_id, candidate_id):
        events.append(("redact",))
        with app.state.identity_store.sync_session.begin() as db:
            candidate = db.get(Candidate, candidate_id)
            candidate.deleted_at = datetime(2026, 7, 15, 9, 0, tzinfo=timezone.utc)
            candidate.display_name = "已删除候选人"
            candidate.version += 1
        return DatabaseRedactionResult("b" * 64, (0, 2, 0, 0, 0, 0, 0, 2, 0))

    monkeypatch.setattr(deletion_worker, "execute_database_redaction", redact)
    handler = DeletionJobHandler(
        sessions=app.state.identity_store.sync_session,
        governance_engine=FakeGovernanceEngine(),
        object_deleter=deleter,
        ledger=ledger,
        resume_bucket="resumes",
        export_bucket="resumes",
    )
    job = _job(organization_id, request_id, 2)

    with pytest.raises(RetryableJobError) as first:
        asyncio.run(handler(job))
    assert first.value.safe_code == "deletion_object_unavailable"
    assert not any(event[0] == "redact" for event in events)
    with app.state.identity_store.sync_session() as db:
        request = db.get(DeletionRequest, request_id)
        artifacts = db.scalars(
            select(DeletionArtifact).order_by(DeletionArtifact.storage_key)
        ).all()
        assert request.status == "executing"
        assert [artifact.status for artifact in artifacts] == ["deleted", "pending"]

    asyncio.run(handler(job))

    assert [event[0] for event in events].count("delete") == 3
    assert [event[0] for event in events][-3:] == ["redact", "ledger_write", "ledger_read"]
    with app.state.identity_store.sync_session() as db:
        request = db.get(DeletionRequest, request_id)
        assert request.status == "completed"
        assert request.recovery_generation == 0
        assert all(
            artifact.status == "deleted"
            for artifact in db.scalars(select(DeletionArtifact)).all()
        )

    counts_before_reentry = {
        name: [event[0] for event in events].count(name)
        for name in ("delete", "redact", "ledger_write", "ledger_read")
    }
    asyncio.run(handler(job))
    assert [event[0] for event in events].count("ledger_read") == (
        counts_before_reentry["ledger_read"] + 1
    )
    for name in ("delete", "redact", "ledger_write"):
        assert [event[0] for event in events].count(name) == counts_before_reentry[name]
    with app.state.identity_store.sync_session() as db:
        request = db.get(DeletionRequest, request_id)
        assert request.recovery_generation == 0


def test_terminal_callback_matches_exact_tenant_request_version_and_executing(tmp_path) -> None:
    from server.app.governance.terminal import finalize_deletion_dead_letter

    app = make_app(tmp_path)
    organization_id, _candidate_id, request_id = _approved_request(app)
    with app.state.identity_store.sync_session.begin() as db:
        request = db.get(DeletionRequest, request_id)
        request.status = "executing"

    with app.state.identity_store.sync_session.begin() as db:
        finalize_deletion_dead_letter(
            db,
            _job(organization_id, request_id, 1),
            "handler_failed",
            datetime.now(timezone.utc),
        )
        assert db.get(DeletionRequest, request_id).status == "executing"

    with app.state.identity_store.sync_session.begin() as db:
        finalize_deletion_dead_letter(
            db,
            _job(organization_id, request_id, 2),
            "handler_failed",
            datetime.now(timezone.utc),
        )
        request = db.get(DeletionRequest, request_id)
        assert request.status == "failed"
        assert request.version == 3
        assert request.safe_error_code == "handler_failed"
        audits = db.scalars(
            select(AuditLog).where(AuditLog.event_type == "governance.deletion_failed")
        ).all()
        assert len(audits) == 1


@pytest.mark.parametrize(
    ("guard", "error_type", "safe_code"),
    [
        ("stale", PermanentJobError, "deletion_manifest_stale"),
        ("hold", RetryableJobError, "deletion_legal_hold_active"),
        ("active", RetryableJobError, "deletion_active_application"),
    ],
)
def test_claim_guards_have_no_deletion_side_effects(
    tmp_path, guard, error_type, safe_code
) -> None:
    from server.app.governance.worker import DeletionJobHandler

    app = make_app(tmp_path)
    organization_id, candidate_id, request_id = _approved_request(app)
    admin_id = (
        seed_user(app, "recruiting_admin", "worker-hold@deletion.test")
        if guard == "hold"
        else None
    )
    with app.state.identity_store.sync_session.begin() as db:
        candidate = db.get(Candidate, candidate_id)
        if guard == "stale":
            candidate.version += 1
        elif guard == "hold":
            db.add(
                LegalHold(
                    organization_id=organization_id,
                    candidate_id=candidate_id,
                    reason="active hold",
                    placed_by=admin_id,
                )
            )
        else:
            resume = db.scalar(select(Resume).where(Resume.candidate_id == candidate_id))
            job = Job(
                organization_id=organization_id,
                title="Active",
                owner_id=candidate.owner_id,
                status="open",
            )
            db.add(job)
            db.flush()
            db.add(
                Application(
                    organization_id=organization_id,
                    candidate_id=candidate_id,
                    job_id=job.id,
                    resume_id=resume.id,
                    owner_id=candidate.owner_id,
                    stage="new",
                )
            )
    events = []
    handler = DeletionJobHandler(
        sessions=app.state.identity_store.sync_session,
        governance_engine=FakeGovernanceEngine(),
        object_deleter=RecordingDeleter(events),
        ledger=RecordingLedger(events),
        resume_bucket="resumes",
        export_bucket="resumes",
    )

    with pytest.raises(error_type) as raised:
        asyncio.run(handler(_job(organization_id, request_id, 2)))

    assert raised.value.safe_code == safe_code
    assert events == []
    with app.state.identity_store.sync_session() as db:
        assert db.get(DeletionRequest, request_id).status == "approved"
        assert db.scalar(select(DeletionArtifact.id)) is None


def test_redaction_success_then_ledger_failure_retries_identical_entry(
    tmp_path, monkeypatch
) -> None:
    from server.app.governance import worker as deletion_worker
    from server.app.governance.worker import DeletionJobHandler

    app = make_app(tmp_path)
    organization_id, candidate_id, request_id = _approved_request(app)
    events = []
    ledger = RecordingLedger(events, fail_first_write=True)

    def redact(_connection, *, organization_id, request_id, candidate_id):
        events.append(("redact",))
        with app.state.identity_store.sync_session.begin() as db:
            candidate = db.get(Candidate, candidate_id)
            if candidate.deleted_at is None:
                candidate.deleted_at = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
                candidate.display_name = "已删除候选人"
                candidate.version += 1
        return DatabaseRedactionResult("c" * 64, (0, 2, 0, 0, 0, 0, 0, 2, 0))

    monkeypatch.setattr(deletion_worker, "execute_database_redaction", redact)
    handler = DeletionJobHandler(
        sessions=app.state.identity_store.sync_session,
        governance_engine=FakeGovernanceEngine(),
        object_deleter=RecordingDeleter(events),
        ledger=ledger,
        resume_bucket="resumes",
        export_bucket="resumes",
    )
    job = _job(organization_id, request_id, 2)

    with pytest.raises(RetryableJobError) as failed:
        asyncio.run(handler(job))
    assert failed.value.safe_code == "deletion_ledger_unavailable"
    first_entry = next(event[1] for event in events if event[0] == "ledger_write")
    with app.state.identity_store.sync_session() as db:
        request = db.get(DeletionRequest, request_id)
        assert request.status == "executing"
        assert request.database_redaction_checksum == "c" * 64
        assert request.ledger_completed_at is not None

    asyncio.run(handler(job))

    entries = [event[1] for event in events if event[0] == "ledger_write"]
    assert entries == [first_entry, first_entry]
    with app.state.identity_store.sync_session() as db:
        request = db.get(DeletionRequest, request_id)
        candidate = db.get(Candidate, candidate_id)
        assert request.status == "completed"
        assert request.recovery_generation == 0
        assert candidate.version == request.candidate_version + 1


@pytest.mark.parametrize("job_status", ["queued", "running"])
def test_matching_export_is_cancelled_only_when_queued(tmp_path, job_status) -> None:
    from server.app.governance.worker import DeletionJobHandler

    app = make_app(tmp_path)
    organization_id, candidate_id, request_id = _approved_request(app)
    with app.state.identity_store.sync_session.begin() as db:
        request = db.get(DeletionRequest, request_id)
        export_id = uuid4()
        now = datetime.now(timezone.utc)
        job = BackgroundJob(
            organization_id=organization_id,
            type="reports.export",
            payload={"organization_id": str(organization_id), "export_id": str(export_id)},
            status="queued",
            priority=0,
            attempts=0,
            max_attempts=3,
            run_after=now,
            created_at=now,
            updated_at=now,
        )
        db.add(job)
        db.flush()
        db.add(
            ExportRecord(
                id=export_id,
                organization_id=organization_id,
                requested_by=request.requested_by,
                background_job_id=job.id,
                filters={},
            )
        )
        db.flush()
        db.add(
            ExportCandidateMembership(
                organization_id=organization_id,
                export_id=export_id,
                candidate_id=candidate_id,
            )
        )
        db.flush()
        if job_status == "running":
            job.status = "running"
    handler = DeletionJobHandler(
        sessions=app.state.identity_store.sync_session,
        governance_engine=FakeGovernanceEngine(),
        object_deleter=RecordingDeleter([]),
        ledger=RecordingLedger([]),
        resume_bucket="resumes",
        export_bucket="resumes",
    )
    assert handler._claim(organization_id, request_id, 2, "export-order") is False

    if job_status == "running":
        with pytest.raises(RetryableJobError) as raised:
            handler._settle_exports(organization_id, request_id)
        assert raised.value.safe_code == "deletion_export_inflight"
    else:
        handler._settle_exports(organization_id, request_id)

    with app.state.identity_store.sync_session() as db:
        export = db.get(ExportRecord, export_id)
        stored_job = db.get(BackgroundJob, job.id)
        if job_status == "running":
            assert export.status == "queued"
            assert stored_job.status == "running"
        else:
            assert export.status == "failed"
            assert export.safe_error_code == "deletion_in_progress"
            assert stored_job.status == "cancelled"


@pytest.mark.skipif(
    not os.getenv("GOVERNANCE_MINIO_ENDPOINT"),
    reason="governance MinIO smoke not configured",
)
def test_real_minio_deletes_resume_and_export_before_redaction_and_writes_ledger_last(
    tmp_path, monkeypatch
) -> None:
    from minio import Minio
    from minio.error import S3Error

    from server.app.governance import worker as deletion_worker
    from server.app.governance.deletion_service import (
        build_private_manifest,
        canonical_manifest_hash,
    )
    from server.app.governance.storage import (
        DeleteOnlyObjectAdapter,
        SignedLedgerAdapter,
    )
    from server.app.governance.worker import DeletionJobHandler

    endpoint = os.environ["GOVERNANCE_MINIO_ENDPOINT"]
    root = Minio(
        endpoint,
        access_key=os.environ["MINIO_SMOKE_ROOT_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SMOKE_ROOT_SECRET_KEY"],
        secure=False,
    )
    delete_client = Minio(
        endpoint,
        access_key=os.environ["GOVERNANCE_DELETE_ACCESS_KEY"],
        secret_key=os.environ["GOVERNANCE_DELETE_SECRET_KEY"],
        secure=False,
    )
    ledger_client = Minio(
        endpoint,
        access_key=os.environ["GOVERNANCE_LEDGER_ACCESS_KEY"],
        secret_key=os.environ["GOVERNANCE_LEDGER_SECRET_KEY"],
        secure=False,
    )
    resume_bucket = os.environ["GOVERNANCE_RESUME_BUCKET"]
    export_bucket = os.environ["GOVERNANCE_EXPORT_BUCKET"]
    ledger_bucket = os.environ["GOVERNANCE_LEDGER_BUCKET"]
    app = make_app(tmp_path)
    organization_id, candidate_id, request_id = _approved_request(app)
    export_key = f"exports/{organization_id}/{uuid4()}.csv"
    with app.state.identity_store.sync_session.begin() as db:
        request = db.get(DeletionRequest, request_id)
        now = datetime.now(timezone.utc)
        export_id = uuid4()
        job = BackgroundJob(
            organization_id=organization_id,
            type="reports.export",
            payload={"organization_id": str(organization_id), "export_id": str(export_id)},
            status="succeeded",
            priority=0,
            attempts=1,
            max_attempts=3,
            run_after=now,
            created_at=now,
            updated_at=now,
        )
        db.add(job)
        db.flush()
        db.add(
            ExportRecord(
                id=export_id,
                organization_id=organization_id,
                requested_by=request.requested_by,
                background_job_id=job.id,
                status="succeeded",
                filters={},
                object_key=export_key,
                completed_at=now,
            )
        )
        db.flush()
        db.add(
            ExportCandidateMembership(
                organization_id=organization_id,
                export_id=export_id,
                candidate_id=candidate_id,
            )
        )
        db.flush()
        candidate = db.get(Candidate, candidate_id)
        manifest, policy = build_private_manifest(db, candidate, now=request.requested_at)
        request.impact_manifest = manifest
        request.manifest_hash = canonical_manifest_hash(manifest)
        request.policy_version = policy.version
        resume_keys = tuple(
            item["storage_key"] for item in manifest["objects"]["resume_objects"]
        )
    for bucket, key in [*( (resume_bucket, key) for key in resume_keys ), (export_bucket, export_key)]:
        root.put_object(bucket, key, io.BytesIO(b"private"), 7)

    real_ledger = SignedLedgerAdapter(
        ledger_client, ledger_bucket, "deletions/", b"b2b2-independent-signing-key-32-bytes"
    )

    class FailFirstLedger:
        def __init__(self):
            self.failed = False
            self.entry = None

        def write(self, entry):
            self.entry = entry
            if not self.failed:
                self.failed = True
                raise GovernanceStorageError("ledger_write_failed")
            return real_ledger.write(entry)

        def read(self, key):
            return real_ledger.read(key)

    ledger = FailFirstLedger()

    def redact(_connection, *, organization_id, request_id, candidate_id):
        for bucket, key in [*( (resume_bucket, key) for key in resume_keys ), (export_bucket, export_key)]:
            with pytest.raises(S3Error) as missing:
                root.stat_object(bucket, key)
            assert missing.value.code in {"NoSuchKey", "NoSuchObject"}
        with app.state.identity_store.sync_session.begin() as db:
            candidate = db.get(Candidate, candidate_id)
            if candidate.deleted_at is None:
                candidate.deleted_at = datetime(2026, 7, 15, 11, 0, tzinfo=timezone.utc)
                candidate.display_name = "已删除候选人"
                candidate.version += 1
        return DatabaseRedactionResult("d" * 64, (0, 2, 0, 0, 0, 0, 0, 2, 1))

    monkeypatch.setattr(deletion_worker, "execute_database_redaction", redact)
    handler = DeletionJobHandler(
        app.state.identity_store.sync_session,
        FakeGovernanceEngine(),
        DeleteOnlyObjectAdapter(delete_client),
        ledger,
        resume_bucket=resume_bucket,
        export_bucket=export_bucket,
    )
    job = _job(organization_id, request_id, 2)
    with pytest.raises(RetryableJobError):
        asyncio.run(handler(job))
    ledger_key = real_ledger.object_key(ledger.entry)
    with pytest.raises(S3Error):
        root.stat_object(ledger_bucket, ledger_key)

    asyncio.run(handler(job))
    assert root.stat_object(ledger_bucket, ledger_key).size > 0
    root.put_object(ledger_bucket, ledger_key, io.BytesIO(b"{}"), 2)
    with pytest.raises(PermanentJobError) as tampered:
        asyncio.run(handler(job))
    assert tampered.value.safe_code == "deletion_ledger_invalid"
