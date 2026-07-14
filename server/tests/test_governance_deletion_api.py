import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from server.app.core.settings import Settings
from server.app.governance import deletion_service
from server.app.governance.deletion_models import DeletionRequest, LegalHold
from server.app.identity.models import AuditLog, Organization, User, UserRole
from server.app.main import create_app
from server.app.queue.models import BackgroundJob
from server.app.queue.payloads import DEFAULT_PAYLOAD_POLICIES, UnsafePayload
from server.app.queue.repository import TERMINAL_CALLBACK_TYPES
from server.app.recruiting.models import Candidate, CandidateContact, IdempotencyRecord
from server.tests.test_recruiting_api import login, seed_user


ORIGIN = "https://hr.example.test"
SENSITIVE = re.compile(
    r"candidate_id|organization_id|storage_key|manifest_hash|display_name|email|phone|"
    r"parsed_text|original_filename|meeting_url|feedback_text|credential|idempotency",
    re.IGNORECASE,
)


class Probe:
    async def check(self) -> None:
        pass


class FixedClock:
    def current_time(self) -> datetime:
        return datetime(2026, 7, 15, 8, 0, tzinfo=timezone.utc)


def make_app(tmp_path):
    app = create_app(
        settings=Settings(
            environment="test",
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'deletion-api.db'}",
            cors_origins=[ORIGIN],
        ),
        database_probe=Probe(),
        storage_probe=Probe(),
        initialize_identity_schema=True,
        clock=FixedClock(),
    )
    app.state.identity_store.create_schema()
    return app


def candidate_for(app, owner_id):
    with app.state.identity_store.sync_session() as db:
        owner = db.get(User, owner_id)
        candidate = Candidate(
            organization_id=owner.organization_id,
            display_name="Never expose this candidate",
            current_title="Private title",
            owner_id=owner.id,
        )
        db.add(candidate)
        db.commit()
        return candidate.id


def request_deletion(client, headers, candidate_id, key="request-1", reason="candidate_request"):
    return client.post(
        f"/api/v1/candidates/{candidate_id}/deletion-requests",
        json={"reason_code": reason},
        headers={**headers, "Idempotency-Key": key},
    )


def approve(client, headers, request_id, version, key="approve-1"):
    return client.post(
        f"/api/v1/deletion-requests/{request_id}/transitions",
        json={"target_status": "approved"},
        headers={**headers, "If-Match": f'"{version}"', "Idempotency-Key": key},
    )


def assert_problem(response, status, code):
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Trace-ID"]
    assert not SENSITIVE.search(response.json()["detail"])


def test_openapi_and_queue_contract_are_exact(tmp_path) -> None:
    app = make_app(tmp_path)
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]
    expected = {
        "/api/v1/candidates/{candidate_id}/deletion-requests",
        "/api/v1/deletion-requests",
        "/api/v1/deletion-requests/{request_id}",
        "/api/v1/deletion-requests/{request_id}/transitions",
        "/api/v1/candidates/{candidate_id}/legal-holds",
        "/api/v1/legal-holds/{hold_id}/releases",
        "/api/v1/candidates/{candidate_id}/governance-status",
    }
    assert expected <= set(paths)
    assert not any("recover" in path for path in paths)

    organization_id = str(uuid4())
    request_id = str(uuid4())
    payload = {
        "organization_id": organization_id,
        "deletion_request_id": request_id,
        "request_version": 2,
    }
    assert DEFAULT_PAYLOAD_POLICIES.validate_job("governance.delete_candidate", payload) == payload
    for invalid in (
        {**payload, "storage_key": "private/object"},
        {**payload, "request_version": 0},
        {"organization_id": organization_id, "deletion_request_id": request_id},
    ):
        with pytest.raises(UnsafePayload):
            DEFAULT_PAYLOAD_POLICIES.validate_job("governance.delete_candidate", invalid)
    assert "governance.delete_candidate" in TERMINAL_CALLBACK_TYPES


@pytest.mark.parametrize(
    ("role", "owns_candidate", "expected"),
    [
        ("recruiter", True, 201),
        ("recruiting_admin", False, 201),
        ("recruiter", False, 404),
        ("system_admin", True, 404),
        ("hiring_manager", True, 404),
        ("interviewer", True, 404),
    ],
)
def test_request_authorization_is_non_enumerating_for_every_role(
    tmp_path, role, owns_candidate, expected
) -> None:
    app = make_app(tmp_path)
    email = f"{role}-{str(owns_candidate).lower()}@deletion.test"
    actor_id = seed_user(app, role, email)
    owner_id = actor_id if owns_candidate else seed_user(app, "recruiter", f"owner-{role}@deletion.test")
    candidate_id = candidate_for(app, owner_id)
    with TestClient(app) as client:
        headers = login(client, email)
        response = request_deletion(client, headers, candidate_id)
    assert response.status_code == expected
    assert response.headers["Cache-Control"] == "no-store"
    if expected == 404:
        assert_problem(response, 404, "resource_not_found")


def test_request_is_replay_safe_conflict_safe_and_public_projection_is_recursive_safe(tmp_path) -> None:
    app = make_app(tmp_path)
    recruiter_id = seed_user(app, "recruiter", "requester@deletion.test")
    candidate_id = candidate_for(app, recruiter_id)
    with app.state.identity_store.sync_session() as db:
        candidate = db.get(Candidate, candidate_id)
        db.add(
            CandidateContact(
                organization_id=candidate.organization_id,
                candidate_id=candidate.id,
                kind="email",
                ciphertext=b"secret",
                lookup_hash="a" * 64,
                masked_value="s***@example.test",
            )
        )
        db.commit()

    with TestClient(app) as client:
        headers = login(client, "requester@deletion.test")
        missing = client.post(
            f"/api/v1/candidates/{candidate_id}/deletion-requests",
            json={"reason_code": "candidate_request"},
            headers=headers,
        )
        assert_problem(missing, 428, "idempotency_key_required")
        forbidden_reason = request_deletion(client, headers, candidate_id, "retention", "retention_expired")
        assert_problem(forbidden_reason, 422, "validation_failed")

        first = request_deletion(client, headers, candidate_id)
        replay = request_deletion(client, headers, candidate_id)
        conflict = request_deletion(client, headers, candidate_id, reason="administrator_request")
        second = request_deletion(client, headers, candidate_id, key="request-2")

    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    assert first.headers["ETag"] == replay.headers["ETag"] == '"1"'
    assert_problem(conflict, 409, "idempotency_conflict")
    assert_problem(second, 409, "deletion_request_open")
    data = first.json()["data"]
    assert set(data) == {
        "id", "status", "version", "reason_code", "requested_at", "approved_at",
        "safe_error_code", "impact",
    }
    assert set(data["impact"]["counts"]) == {
        "contacts", "resumes", "applications", "screening_records", "interviews",
        "feedback_records", "talent_memberships", "resume_objects", "temporary_exports",
    }
    assert data["impact"]["counts"]["contacts"] == 1
    assert not SENSITIVE.search(str(first.json()))


def test_list_read_cursor_and_requester_scope(tmp_path) -> None:
    app = make_app(tmp_path)
    requester_id = seed_user(app, "recruiter", "reader@deletion.test")
    other_id = seed_user(app, "recruiter", "other@deletion.test")
    admin_id = seed_user(app, "system_admin", "system@deletion.test")
    candidate_id = candidate_for(app, requester_id)
    other_candidate_id = candidate_for(app, other_id)
    with TestClient(app) as client:
        requester = login(client, "reader@deletion.test")
        first = request_deletion(client, requester, candidate_id)
        other = login(client, "other@deletion.test")
        second = request_deletion(client, other, other_candidate_id, key="other-request")
        system = login(client, "system@deletion.test")

        page = client.get("/api/v1/deletion-requests?limit=1", headers=system)
        assert page.status_code == 200
        assert len(page.json()["data"]) == 1
        assert page.json()["meta"]["next_cursor"]
        next_page = client.get(
            "/api/v1/deletion-requests",
            params={"limit": 1, "cursor": page.json()["meta"]["next_cursor"]},
            headers=system,
        )
        assert next_page.status_code == 200
        assert next_page.json()["data"][0]["id"] != page.json()["data"][0]["id"]
        assert_problem(
            client.get("/api/v1/deletion-requests?limit=101", headers=system),
            422,
            "validation_failed",
        )
        assert_problem(
            client.get("/api/v1/deletion-requests?status=unknown", headers=system),
            422,
            "validation_failed",
        )
        assert_problem(
            client.get("/api/v1/deletion-requests?cursor=not-signed", headers=system),
            422,
            "validation_failed",
        )

        requester = login(client, "reader@deletion.test")
        own = client.get(f"/api/v1/deletion-requests/{first.json()['data']['id']}", headers=requester)
        denied = client.get(f"/api/v1/deletion-requests/{second.json()['data']['id']}", headers=requester)
        assert own.status_code == 200
        assert_problem(denied, 404, "resource_not_found")


def test_approval_requires_current_preconditions_and_enqueues_once(tmp_path) -> None:
    app = make_app(tmp_path)
    requester_id = seed_user(app, "recruiter", "approval-requester@deletion.test")
    seed_user(app, "system_admin", "approver@deletion.test")
    candidate_id = candidate_for(app, requester_id)
    with TestClient(app) as client:
        requester = login(client, "approval-requester@deletion.test")
        created = request_deletion(client, requester, candidate_id)
        request_id = created.json()["data"]["id"]
        assert_problem(
            client.post(
                f"/api/v1/deletion-requests/{request_id}/transitions",
                json={"target_status": "approved"},
                headers={**requester, "If-Match": '"1"', "Idempotency-Key": "self"},
            ),
            404,
            "resource_not_found",
        )
        approver = login(client, "approver@deletion.test")
        assert_problem(
            client.post(
                f"/api/v1/deletion-requests/{request_id}/transitions",
                json={"target_status": "approved"},
                headers={**approver, "Idempotency-Key": "missing-match"},
            ),
            428,
            "precondition_required",
        )
        assert_problem(approve(client, approver, request_id, 0, "malformed"), 422, "validation_failed")
        assert_problem(approve(client, approver, request_id, 2, "stale"), 409, "resource_version_conflict")
        approved = approve(client, approver, request_id, 1)
        replay = approve(client, approver, request_id, 1)
        different_precondition = approve(client, approver, request_id, 2)
    assert approved.status_code == replay.status_code == 200
    assert approved.json() == replay.json()
    assert approved.json()["data"]["status"] == "approved"
    assert approved.headers["ETag"] == '"2"'
    assert_problem(different_precondition, 409, "idempotency_conflict")
    with app.state.identity_store.sync_session() as db:
        record = db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.operation == "governance.deletion_request.approve",
                IdempotencyRecord.idempotency_key == "approve-1",
            )
        )
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    with TestClient(app) as client:
        approver = login(client, "approver@deletion.test")
        expired = approve(client, approver, request_id, 2)
    assert_problem(expired, 409, "invalid_deletion_state_transition")
    with app.state.identity_store.sync_session() as db:
        jobs = list(db.scalars(select(BackgroundJob).where(BackgroundJob.type == "governance.delete_candidate")))
        assert len(jobs) == 1
        assert jobs[0].payload == {
            "organization_id": str(jobs[0].organization_id),
            "deletion_request_id": request_id,
            "request_version": 2,
        }


def test_stale_manifest_refreshes_without_enqueue_and_increments_version(tmp_path) -> None:
    app = make_app(tmp_path)
    requester_id = seed_user(app, "recruiter", "stale-requester@deletion.test")
    seed_user(app, "system_admin", "stale-approver@deletion.test")
    candidate_id = candidate_for(app, requester_id)
    with TestClient(app) as client:
        requester = login(client, "stale-requester@deletion.test")
        created = request_deletion(client, requester, candidate_id)
        request_id = created.json()["data"]["id"]
        with app.state.identity_store.sync_session() as db:
            candidate = db.get(Candidate, candidate_id)
            candidate.version += 1
            db.commit()
        approver = login(client, "stale-approver@deletion.test")
        stale = approve(client, approver, request_id, 1)
    assert_problem(stale, 409, "stale_manifest")
    assert stale.headers["ETag"] == '"2"'
    assert stale.json()["data"]["impact"]["candidate_version"] == 2
    with app.state.identity_store.sync_session() as db:
        row = db.get(DeletionRequest, UUID(request_id))
        assert row.status == "requested" and row.version == 2
        assert db.scalar(select(func.count()).select_from(BackgroundJob)) == 0


def test_legal_hold_release_and_governance_status_redact_reason_by_role(tmp_path) -> None:
    app = make_app(tmp_path)
    recruiter_id = seed_user(app, "recruiter", "hold-reader@deletion.test")
    seed_user(app, "recruiting_admin", "hold-admin@deletion.test")
    candidate_id = candidate_for(app, recruiter_id)
    with TestClient(app) as client:
        recruiter = login(client, "hold-reader@deletion.test")
        created = request_deletion(client, recruiter, candidate_id)
        admin = login(client, "hold-admin@deletion.test")
        placed = client.post(
            f"/api/v1/candidates/{candidate_id}/legal-holds",
            json={"reason": "Privileged litigation detail"},
            headers={**admin, "Idempotency-Key": "hold-1"},
        )
        assert placed.status_code == 201
        placed_replay = client.post(
            f"/api/v1/candidates/{candidate_id}/legal-holds",
            json={"reason": "Privileged litigation detail"},
            headers={**admin, "Idempotency-Key": "hold-1"},
        )
        placed_conflict = client.post(
            f"/api/v1/candidates/{candidate_id}/legal-holds",
            json={"reason": "Different privileged detail"},
            headers={**admin, "Idempotency-Key": "hold-1"},
        )
        assert placed_replay.status_code == 201 and placed_replay.json() == placed.json()
        assert_problem(placed_conflict, 409, "idempotency_conflict")
        hold_id = placed.json()["data"]["id"]
        assert placed.headers["ETag"] == '"1"'
        admin_status = client.get(f"/api/v1/candidates/{candidate_id}/governance-status", headers=admin)
        recruiter = login(client, "hold-reader@deletion.test")
        recruiter_status = client.get(f"/api/v1/candidates/{candidate_id}/governance-status", headers=recruiter)
        assert admin_status.json()["data"]["legal_hold_reason"] == "Privileged litigation detail"
        assert "legal_hold_reason" not in recruiter_status.json()["data"]
        assert set(recruiter_status.json()["data"]) == {
            "deletion_status", "deletion_request_id", "legal_hold_active"
        }
        admin = login(client, "hold-admin@deletion.test")
        assert_problem(
            client.post(
                f"/api/v1/legal-holds/{hold_id}/releases",
                json={"reason": "Matter closed"},
                headers={**admin, "Idempotency-Key": "release-missing"},
            ),
            428,
            "precondition_required",
        )
        assert_problem(
            client.post(
                f"/api/v1/legal-holds/{hold_id}/releases",
                json={"reason": "Matter closed"},
                headers={**admin, "If-Match": "1", "Idempotency-Key": "release-malformed"},
            ),
            422,
            "validation_failed",
        )
        assert_problem(
            client.post(
                f"/api/v1/legal-holds/{hold_id}/releases",
                json={"reason": "Matter closed"},
                headers={**admin, "If-Match": '"2"', "Idempotency-Key": "release-stale"},
            ),
            409,
            "resource_version_conflict",
        )
        released = client.post(
            f"/api/v1/legal-holds/{hold_id}/releases",
            json={"reason": "Matter closed"},
            headers={**admin, "If-Match": '"1"', "Idempotency-Key": "release-1"},
        )
        replay = client.post(
            f"/api/v1/legal-holds/{hold_id}/releases",
            json={"reason": "Matter closed"},
            headers={**admin, "If-Match": '"1"', "Idempotency-Key": "release-1"},
        )
        conflict = client.post(
            f"/api/v1/legal-holds/{hold_id}/releases",
            json={"reason": "Different release reason"},
            headers={**admin, "If-Match": '"1"', "Idempotency-Key": "release-1"},
        )
    assert released.status_code == replay.status_code == 200
    assert released.json() == replay.json()
    assert released.headers["ETag"] == '"2"'
    assert_problem(conflict, 409, "idempotency_conflict")
    with app.state.identity_store.sync_session() as db:
        assert db.get(LegalHold, UUID(hold_id)).released_at is not None


def test_audit_metadata_is_safe_and_expired_idempotency_can_be_reused(tmp_path) -> None:
    app = make_app(tmp_path)
    recruiter_id = seed_user(app, "recruiter", "audit-requester@deletion.test")
    candidate_id = candidate_for(app, recruiter_id)
    with TestClient(app) as client:
        headers = login(client, "audit-requester@deletion.test")
        created = request_deletion(client, headers, candidate_id, key="expiring")
        assert created.status_code == 201
        request_id = created.json()["data"]["id"]
        request_deletion(client, headers, candidate_id, key="conflict", reason="administrator_request")
        with app.state.identity_store.sync_session() as db:
            row = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == "expiring"))
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        reused = request_deletion(client, headers, candidate_id, key="expiring")
        assert_problem(reused, 409, "deletion_request_open")
    with app.state.identity_store.sync_session() as db:
        events = list(db.scalars(select(AuditLog).where(AuditLog.category == "governance")))
        assert events
        assert {event.outcome for event in events} >= {"success", "failure"}
        for event in events:
            assert not SENSITIVE.search(str(event.metadata_json))
        assert db.get(DeletionRequest, UUID(request_id)) is not None


def test_requester_cannot_self_approve_after_gaining_system_role(tmp_path) -> None:
    app = make_app(tmp_path)
    requester_id = seed_user(app, "recruiter", "self-approver@deletion.test")
    candidate_id = candidate_for(app, requester_id)
    with TestClient(app) as client:
        requester = login(client, "self-approver@deletion.test")
        created = request_deletion(client, requester, candidate_id)
        request_id = created.json()["data"]["id"]
        with app.state.identity_store.sync_session() as db:
            db.add(UserRole(user_id=requester_id, role="system_admin"))
            db.commit()
        elevated = login(client, "self-approver@deletion.test")
        response = approve(client, elevated, request_id, 1, "self-elevated")
    assert_problem(response, 409, "self_approval_forbidden")
    with app.state.identity_store.sync_session() as db:
        row = db.get(DeletionRequest, UUID(request_id))
        assert row.status == "requested" and row.version == 1
        assert db.scalar(select(func.count()).select_from(BackgroundJob)) == 0


def test_hold_fails_approved_request_cancels_job_and_rejects_executing(tmp_path) -> None:
    app = make_app(tmp_path)
    requester_id = seed_user(app, "recruiter", "hold-race-requester@deletion.test")
    seed_user(app, "system_admin", "hold-race-system@deletion.test")
    seed_user(app, "recruiting_admin", "hold-race-admin@deletion.test")
    candidate_id = candidate_for(app, requester_id)
    with TestClient(app) as client:
        requester = login(client, "hold-race-requester@deletion.test")
        created = request_deletion(client, requester, candidate_id)
        request_id = created.json()["data"]["id"]
        system = login(client, "hold-race-system@deletion.test")
        assert approve(client, system, request_id, 1).status_code == 200
        admin = login(client, "hold-race-admin@deletion.test")
        held = client.post(
            f"/api/v1/candidates/{candidate_id}/legal-holds",
            json={"reason": "Preserve evidence"},
            headers={**admin, "Idempotency-Key": "approved-hold"},
        )
        assert held.status_code == 201
    with app.state.identity_store.sync_session() as db:
        row = db.get(DeletionRequest, UUID(request_id))
        job = db.scalar(select(BackgroundJob).where(BackgroundJob.type == "governance.delete_candidate"))
        assert row.status == "failed" and row.safe_error_code == "legal_hold_active"
        assert row.version == 3 and job.status == "cancelled"

    second_path = tmp_path / "second"
    second_path.mkdir()
    second_app = make_app(second_path)
    requester_id = seed_user(second_app, "recruiter", "executing-requester@deletion.test")
    seed_user(second_app, "recruiting_admin", "executing-admin@deletion.test")
    candidate_id = candidate_for(second_app, requester_id)
    with TestClient(second_app) as client:
        requester = login(client, "executing-requester@deletion.test")
        created = request_deletion(client, requester, candidate_id)
        request_id = created.json()["data"]["id"]
        with second_app.state.identity_store.sync_session() as db:
            row = db.get(DeletionRequest, UUID(request_id))
            row.status = "executing"
            db.commit()
        admin = login(client, "executing-admin@deletion.test")
        rejected = client.post(
            f"/api/v1/candidates/{candidate_id}/legal-holds",
            json={"reason": "Too late"},
            headers={**admin, "Idempotency-Key": "executing-hold"},
        )
    assert_problem(rejected, 409, "deletion_already_executing")
    with second_app.state.identity_store.sync_session() as db:
        assert db.scalar(select(func.count()).select_from(LegalHold)) == 0


def test_audit_and_queue_failures_roll_back_request_job_and_idempotency(
    tmp_path, monkeypatch
) -> None:
    app = make_app(tmp_path)
    requester_id = seed_user(app, "recruiter", "rollback-requester@deletion.test")
    candidate_id = candidate_for(app, requester_id)

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(deletion_service, "append_audit", fail_audit)
    with TestClient(app) as client:
        requester = login(client, "rollback-requester@deletion.test")
        response = request_deletion(client, requester, candidate_id, "rollback-request")
    assert_problem(response, 500, "internal_error")
    with app.state.identity_store.sync_session() as db:
        assert db.scalar(select(func.count()).select_from(DeletionRequest)) == 0
        assert db.scalar(
            select(func.count()).select_from(IdempotencyRecord).where(
                IdempotencyRecord.operation == "governance.deletion_request.create"
            )
        ) == 0

    monkeypatch.undo()
    seed_user(app, "system_admin", "rollback-system@deletion.test")
    with TestClient(app) as client:
        requester = login(client, "rollback-requester@deletion.test")
        created = request_deletion(client, requester, candidate_id, "rollback-created")
        request_id = created.json()["data"]["id"]

        def fail_enqueue(*args, **kwargs):
            raise RuntimeError("queue unavailable")

        monkeypatch.setattr(deletion_service.QueueRepository, "enqueue", fail_enqueue)
        system = login(client, "rollback-system@deletion.test")
        failed = approve(client, system, request_id, 1, "rollback-approval")
    assert_problem(failed, 500, "internal_error")
    with app.state.identity_store.sync_session() as db:
        row = db.get(DeletionRequest, UUID(request_id))
        assert row.status == "requested" and row.version == 1
        assert db.scalar(select(func.count()).select_from(BackgroundJob)) == 0
        assert db.scalar(
            select(func.count()).select_from(IdempotencyRecord).where(
                IdempotencyRecord.operation == "governance.deletion_request.approve"
            )
        ) == 0
