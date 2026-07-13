from dataclasses import dataclass
from tempfile import SpooledTemporaryFile
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from server.app.core.settings import Settings
from server.app.identity.models import Organization, User, UserRole, UserStatus, Job, JobCollaborator
from server.app.identity.security import PasswordService
from server.app.main import create_app
from server.app.recruiting.models import Application, ApplicationStageEvent, Candidate, CandidateEvent, CandidateNote, DownloadTicket, FileObject, Resume
from server.app.identity.models import AuditLog
from server.app.recruiting.storage import StorageReadFailed


class Probe:
    async def check(self) -> None:
        pass


@dataclass
class FakeStorage:
    preview: str = "private parsed preview"
    last_spool: object | None = None

    def open_download(self, storage_key: str, max_bytes: int):
        assert storage_key == "private/resume"
        assert max_bytes == 10 * 1024 * 1024
        spool = SpooledTemporaryFile(max_size=1024, mode="w+b")
        spool.write(b"private-file"); spool.seek(0)
        self.last_spool = spool
        return spool


def make_app(tmp_path, storage=None):
    app = create_app(
        settings=Settings(
            environment="test",
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'recruiting-api.db'}",
            cors_origins=["https://hr.example.test"],
        ),
        database_probe=Probe(),
        storage_probe=Probe(),
        initialize_identity_schema=True,
        resume_storage=storage or FakeStorage(),
    )
    app.state.identity_store.create_schema()
    return app


class FailingStorage:
    def __init__(self, failure: str): self.failure = failure
    def open_download(self, storage_key: str, max_bytes: int):
        raise StorageReadFailed(self.failure)


def seed_user(app, role: str, email: str):
    with app.state.identity_store.sync_session() as db:
        organization = db.query(Organization).filter_by(slug="acme").one_or_none()
        if organization is None:
            organization = Organization(slug="acme", name="Acme", status="active")
        user = User(
            organization=organization,
            email=email,
            normalized_email=email,
            display_name=role,
            password_hash=PasswordService().hash("correct horse"),
        )
        user.roles.append(UserRole(role=role))
        db.add(user)
        db.commit()
        return user.id


def login(client, email: str):
    response = client.post(
        "/api/v1/auth/login",
        json={"organization_slug": "acme", "email": email, "password": "correct horse"},
        headers={"Origin": "https://hr.example.test"},
    )
    assert response.status_code == 200
    return {"Origin": "https://hr.example.test", "X-CSRF-Token": response.headers["X-CSRF-Token"]}


def seed_same_candidate_cross_job(app, recruiter_id):
    with app.state.identity_store.sync_session() as db:
        recruiter = db.get(User, recruiter_id)
        job_allowed = Job(organization_id=recruiter.organization_id, title="Allowed job", owner_id=recruiter_id)
        job_denied = Job(organization_id=recruiter.organization_id, title="Denied job", owner_id=recruiter_id)
        candidate = Candidate(organization_id=recruiter.organization_id, display_name="Shared candidate", owner_id=recruiter_id)
        allowed_file = FileObject(organization_id=recruiter.organization_id, storage_key="private/resume", original_filename="allowed.pdf", mime_type="application/pdf", size_bytes=12, sha256="1" * 64, uploaded_by=recruiter_id)
        denied_file = FileObject(organization_id=recruiter.organization_id, storage_key="private/denied", original_filename="denied.pdf", mime_type="application/pdf", size_bytes=12, sha256="2" * 64, uploaded_by=recruiter_id)
        db.add_all([job_allowed, job_denied, candidate, allowed_file, denied_file]); db.flush()
        allowed_resume = Resume(organization_id=recruiter.organization_id, candidate_id=candidate.id, file_object_id=allowed_file.id, version_number=1, parsed_text="allowed preview")
        denied_resume = Resume(organization_id=recruiter.organization_id, candidate_id=candidate.id, file_object_id=denied_file.id, version_number=2, parsed_text="denied preview")
        db.add_all([allowed_resume, denied_resume]); db.flush()
        allowed_application = Application(organization_id=recruiter.organization_id, candidate_id=candidate.id, job_id=job_allowed.id, resume_id=allowed_resume.id, owner_id=recruiter_id)
        denied_application = Application(organization_id=recruiter.organization_id, candidate_id=candidate.id, job_id=job_denied.id, resume_id=denied_resume.id, owner_id=recruiter_id)
        db.add_all([allowed_application, denied_application]); db.flush()
        denied_note = CandidateNote(organization_id=recruiter.organization_id, candidate_id=candidate.id, actor_user_id=recruiter_id, event_type="candidate.note", payload={"application_id": str(denied_application.id), "body": "denied job note"})
        denied_event = CandidateEvent(organization_id=recruiter.organization_id, candidate_id=candidate.id, actor_user_id=recruiter_id, event_type="candidate.note_added", payload={"application_id": str(denied_application.id)})
        collaborator = JobCollaborator(organization_id=recruiter.organization_id, job_id=job_allowed.id, user_id=recruiter_id, access_role="job_recruiter")
        db.add_all([denied_note, denied_event, collaborator]); db.commit()
        return {
            "candidate_id": str(candidate.id),
            "allowed_job_id": job_allowed.id,
            "denied_job_id": job_denied.id,
            "allowed_application_id": str(allowed_application.id),
            "denied_application_id": str(denied_application.id),
            "allowed_resume_id": str(allowed_resume.id),
            "denied_resume_id": str(denied_resume.id),
        }


def test_recruiting_openapi_registers_complete_task_3b_contract_without_secret_fields(tmp_path) -> None:
    app = create_app(
        settings=Settings(
            environment="test",
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'api.db'}",
            cors_origins=["https://hr.example.test"],
        ),
        database_probe=Probe(),
        storage_probe=Probe(),
        initialize_identity_schema=True,
    )
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    expected = {
        "/api/v1/jobs": {"get", "post"},
        "/api/v1/jobs/{job_id}": {"get", "patch"},
        "/api/v1/jobs/{job_id}/transitions": {"post"},
        "/api/v1/jobs/{job_id}/jd-versions": {"get", "post"},
        "/api/v1/jobs/{job_id}/rule-versions": {"get", "post"},
        "/api/v1/jobs/{job_id}/funnel": {"get"},
        "/api/v1/candidates": {"get", "post"},
        "/api/v1/candidates/{candidate_id}": {"get", "patch"},
        "/api/v1/candidates/{candidate_id}/timeline": {"get"},
        "/api/v1/candidates/{candidate_id}/notes": {"get", "post"},
        "/api/v1/candidates/{candidate_id}/resumes": {"get"},
        "/api/v1/resumes/{resume_id}/preview": {"get"},
        "/api/v1/resumes/{resume_id}/download-tickets": {"post"},
        "/api/v1/download-tickets/consume": {"post"},
        "/api/v1/candidates/{candidate_id}/applications": {"get"},
        "/api/v1/jobs/{job_id}/applications": {"post"},
        "/api/v1/applications/{application_id}": {"patch"},
        "/api/v1/applications/{application_id}/transitions": {"post"},
    }
    assert {path: set(schema["paths"].get(path, {})) for path in expected} == expected
    for path, methods in expected.items():
        for method in methods:
            if path == "/api/v1/download-tickets/consume":
                assert schema["paths"][path][method]["responses"]["200"]["content"]["application/octet-stream"]["schema"]
                continue
            responses = schema["paths"][path][method]["responses"]
            success = responses.get("200") or responses.get("201")
            assert success["content"]["application/json"]["schema"]
    rendered = str(schema).casefold()
    for secret in ("ciphertext", "lookup_hash", "storage_key", "token_hash", "parsed_text"):
        assert secret not in rendered


def test_recruiting_routes_require_an_opaque_session(tmp_path) -> None:
    app = create_app(
        settings=Settings(
            environment="test",
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}",
            cors_origins=["https://hr.example.test"],
        ),
        database_probe=Probe(),
        storage_probe=Probe(),
        initialize_identity_schema=True,
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/jobs")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "authentication_required"


def test_recruiting_validation_is_stable_problem_json_without_echoing_values(tmp_path) -> None:
    app = make_app(tmp_path)
    seed_user(app, "recruiting_admin", "admin@example.test")
    with TestClient(app) as client:
        headers = login(client, "admin@example.test")
        cases = [
            client.get("/api/v1/jobs/not-a-uuid"),
            client.get("/api/v1/jobs?limit=101"),
            client.get("/api/v1/candidates?cursor=raw-secret-value"),
            client.post("/api/v1/candidates", json={"display_name": ""}, headers=headers),
            client.post("/api/v1/download-tickets/consume", json={"token": "raw-secret-value"}, headers=headers),
        ]
    for response in cases:
        assert response.status_code == 422
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["code"] == "validation_failed"
        assert "raw-secret-value" not in response.text


def test_admin_happy_path_preconditions_idempotency_and_private_download(tmp_path) -> None:
    app = make_app(tmp_path)
    admin_id = seed_user(app, "recruiting_admin", "admin@example.test")
    recruiter_id = seed_user(app, "recruiter", "recruiter@example.test")
    with TestClient(app) as client:
        headers = login(client, "admin@example.test")
        job = client.post("/api/v1/jobs", json={"title": "Engineer"}, headers=headers)
        assert job.status_code == 201 and job.headers["etag"] == '"1"'
        job_id = job.json()["data"]["id"]

        missing = client.patch(f"/api/v1/jobs/{job_id}", json={"title": "Senior Engineer"}, headers=headers)
        assert missing.status_code == 428 and missing.json()["code"] == "precondition_required"
        changed = client.patch(f"/api/v1/jobs/{job_id}", json={"title": "Senior Engineer"}, headers={**headers, "If-Match": '"1"'})
        assert changed.status_code == 200 and changed.headers["etag"] == '"2"'

        candidate = client.post(
            "/api/v1/candidates",
            json={"display_name": "Candidate", "contacts": [{"kind": " Email ", "value": "Person@Example.COM"}]},
            headers=headers,
        )
        assert candidate.status_code == 201
        assert candidate.json()["data"]["contacts"] == [{"kind": "email", "value": "p***@example.com"}]
        assert "Person@Example.COM" not in candidate.text
        candidate_id = candidate.json()["data"]["id"]

        with app.state.identity_store.sync_session() as db:
            file = FileObject(organization_id=db.get(User, admin_id).organization_id, storage_key="private/resume", original_filename="resume.pdf", mime_type="application/pdf", size_bytes=12, sha256="0" * 64, uploaded_by=admin_id)
            db.add(file); db.flush()
            resume = Resume(organization_id=file.organization_id, candidate_id=UUID(candidate_id), file_object_id=file.id, version_number=1, parsed_text="must-not-leak")
            db.add(resume); db.commit(); resume_id = str(resume.id)

        app_headers = {**headers, "Idempotency-Key": "create-application"}
        application_payload = {"candidate_id": candidate_id, "resume_id": resume_id, "owner_id": str(recruiter_id)}
        created = client.post(f"/api/v1/jobs/{job_id}/applications", json=application_payload, headers=app_headers)
        replay = client.post(f"/api/v1/jobs/{job_id}/applications", json=application_payload, headers=app_headers)
        assert created.status_code == replay.status_code == 201
        assert created.json() == replay.json()
        conflict = client.post(f"/api/v1/jobs/{job_id}/applications", json={**application_payload, "source": "other"}, headers=app_headers)
        assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"

        preview = client.get(f"/api/v1/resumes/{resume_id}/preview")
        assert preview.status_code == 200 and preview.headers["cache-control"] == "no-store"
        assert preview.json()["data"]["text"] == "must-not-leak"
        with app.state.identity_store.sync_session() as db:
            stored_resume = db.get(Resume, UUID(resume_id))
            stored_resume.parsed_text = "x" * (1024 * 1024 + 1)
            db.commit()
        oversized = client.get(f"/api/v1/resumes/{resume_id}/preview")
        assert oversized.status_code == 422 and oversized.json()["code"] == "preview_too_large"
        with app.state.identity_store.sync_session() as db:
            db.get(Resume, UUID(resume_id)).parsed_text = "must-not-leak"
            db.commit()
        ticket = client.post(f"/api/v1/resumes/{resume_id}/download-tickets", headers=headers)
        raw = ticket.json()["data"]["token"]
        assert raw not in str(ticket.request.url)
        download = client.post("/api/v1/download-tickets/consume", json={"token": raw}, headers=headers)
        assert download.content == b"private-file"
        assert download.headers["cache-control"] == "no-store"
        assert download.headers["content-disposition"].startswith("attachment;")
        assert download.headers["x-content-type-options"] == "nosniff"
        assert app.state.resume_storage.last_spool.closed
        assert client.post("/api/v1/download-tickets/consume", json={"token": raw}, headers=headers).status_code == 404
        with app.state.identity_store.sync_session() as db:
            assert raw not in repr([row.metadata_json for row in db.query(AuditLog).all()])


def test_system_admin_and_interviewer_have_no_recruiting_access_by_role_alone(tmp_path) -> None:
    app = make_app(tmp_path)
    seed_user(app, "system_admin", "system@example.test")
    seed_user(app, "interviewer", "interviewer@example.test")
    with TestClient(app) as client:
        for email in ("system@example.test", "interviewer@example.test"):
            login(client, email)
            jobs = client.get("/api/v1/jobs").json()
            assert jobs["data"] == [] and jobs["meta"]["limit"] == 50
            denied = client.post("/api/v1/candidates", json={"display_name": "Forbidden"}, headers={"Origin": "https://hr.example.test", "X-CSRF-Token": client.get('/api/v1/me', headers={'Sec-Fetch-Site': 'same-origin'}).headers['X-CSRF-Token']})
            assert denied.status_code == 404 and denied.json()["code"] == "resource_not_found"


def test_recruiting_mutations_preserve_central_csrf_boundary(tmp_path) -> None:
    app = make_app(tmp_path)
    seed_user(app, "recruiting_admin", "admin@example.test")
    with TestClient(app) as client:
        headers = login(client, "admin@example.test")
        cases = [
            {},
            {"Origin": "https://hr.example.test", "X-CSRF-Token": "wrong"},
            {"Origin": "https://evil.test", "X-CSRF-Token": headers["X-CSRF-Token"]},
        ]
        for bad_headers in cases:
            response = client.post("/api/v1/jobs", json={"title": "Forbidden"}, headers=bad_headers)
            assert response.status_code == 403 and response.json()["code"] == "csrf_validation_failed"


def test_owning_recruiter_reads_unassigned_timeline_but_cannot_add_unscoped_note(tmp_path) -> None:
    app = make_app(tmp_path)
    seed_user(app, "recruiter", "owner@example.test")
    with TestClient(app) as client:
        headers = login(client, "owner@example.test")
        candidate = client.post("/api/v1/candidates", json={"display_name": "Unassigned"}, headers=headers).json()["data"]
        timeline = client.get(f"/api/v1/candidates/{candidate['id']}/timeline")
        assert timeline.status_code == 200
        assert [event["event_type"] for event in timeline.json()["data"]] == ["candidate.created"]
        note = client.post(f"/api/v1/candidates/{candidate['id']}/notes", json={"body": "Allowed comment"}, headers=headers)
        assert note.status_code == 422 and note.json()["code"] == "validation_failed"


def test_resume_access_is_scoped_to_an_authorized_application_for_the_target_resume(tmp_path) -> None:
    app = make_app(tmp_path)
    recruiter_id = seed_user(app, "recruiter", "scoped-resume@example.test")
    ids = seed_same_candidate_cross_job(app, recruiter_id)

    with TestClient(app) as client:
        headers = login(client, "scoped-resume@example.test")
        listed = client.get(f"/api/v1/candidates/{ids['candidate_id']}/resumes")
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()["data"]] == [ids["allowed_resume_id"]]

        preview = client.get(f"/api/v1/resumes/{ids['allowed_resume_id']}/preview")
        assert preview.status_code == 200 and preview.json()["data"]["text"] == "allowed preview"
        assert client.get(f"/api/v1/resumes/{ids['denied_resume_id']}/preview").status_code == 404
        assert client.post(f"/api/v1/resumes/{ids['denied_resume_id']}/download-tickets", headers=headers).status_code == 404

        first_ticket = client.post(f"/api/v1/resumes/{ids['allowed_resume_id']}/download-tickets", headers=headers)
        assert first_ticket.status_code == 201
        downloaded = client.post("/api/v1/download-tickets/consume", json={"token": first_ticket.json()["data"]["token"]}, headers=headers)
        assert downloaded.status_code == 200 and downloaded.content == b"private-file"

        second_ticket = client.post(f"/api/v1/resumes/{ids['allowed_resume_id']}/download-tickets", headers=headers)
        assert second_ticket.status_code == 201
        with app.state.identity_store.sync_session() as db:
            db.query(JobCollaborator).filter_by(job_id=ids["allowed_job_id"], user_id=recruiter_id).delete()
            db.add(JobCollaborator(organization_id=db.get(User, recruiter_id).organization_id, job_id=ids["denied_job_id"], user_id=recruiter_id, access_role="job_recruiter"))
            db.commit()
        denied_consume = client.post("/api/v1/download-tickets/consume", json={"token": second_ticket.json()["data"]["token"]}, headers=headers)
        assert denied_consume.status_code == 404


def test_candidate_notes_require_and_isolate_by_authorized_application(tmp_path) -> None:
    app = make_app(tmp_path)
    recruiter_id = seed_user(app, "recruiter", "scoped-note@example.test")
    ids = seed_same_candidate_cross_job(app, recruiter_id)

    with TestClient(app) as client:
        headers = login(client, "scoped-note@example.test")
        missing_read = client.get(f"/api/v1/candidates/{ids['candidate_id']}/notes")
        missing_write = client.post(f"/api/v1/candidates/{ids['candidate_id']}/notes", json={"body": "missing application"}, headers=headers)
        assert missing_read.status_code == missing_write.status_code == 422

        denied_read = client.get(f"/api/v1/candidates/{ids['candidate_id']}/notes", params={"application_id": ids["denied_application_id"]})
        denied_write = client.post(f"/api/v1/candidates/{ids['candidate_id']}/notes", json={"application_id": ids["denied_application_id"], "body": "cross-job note"}, headers=headers)
        assert denied_read.status_code == denied_write.status_code == 404

        created = client.post(f"/api/v1/candidates/{ids['candidate_id']}/notes", json={"application_id": ids["allowed_application_id"], "body": "allowed job note"}, headers=headers)
        assert created.status_code == 201
        assert created.json()["data"]["application_id"] == ids["allowed_application_id"]
        listed = client.get(f"/api/v1/candidates/{ids['candidate_id']}/notes", params={"application_id": ids["allowed_application_id"]})
        assert listed.status_code == 200
        assert [(row["application_id"], row["body"]) for row in listed.json()["data"]] == [(ids["allowed_application_id"], "allowed job note")]

        timeline = client.get(f"/api/v1/candidates/{ids['candidate_id']}/timeline")
        assert timeline.status_code == 200
        assert [row["event_type"] for row in timeline.json()["data"]] == ["candidate.note_added"]

        denied_conclusion = client.patch(
            f"/api/v1/applications/{ids['allowed_application_id']}",
            json={"human_conclusion": "越权结论"},
            headers={**headers, "If-Match": '"1"'},
        )
        assert denied_conclusion.status_code == 404


def test_job_owner_can_save_human_conclusion_for_collaborated_job(tmp_path) -> None:
    app = make_app(tmp_path)
    recruiter_id = seed_user(app, "recruiter", "recruiter@example.test")
    with app.state.identity_store.sync_session() as db:
        user = db.get(User, recruiter_id)
        job = Job(organization_id=user.organization_id, title="Recruiter job", owner_id=recruiter_id)
        candidate = Candidate(organization_id=user.organization_id, display_name="Candidate", owner_id=recruiter_id)
        file = FileObject(organization_id=user.organization_id, storage_key="private/recruiter-resume", original_filename="resume.pdf", mime_type="application/pdf", size_bytes=12, sha256="8" * 64, uploaded_by=recruiter_id)
        db.add_all([job, candidate, file]); db.flush()
        resume = Resume(organization_id=user.organization_id, candidate_id=candidate.id, file_object_id=file.id, version_number=1)
        db.add(resume); db.flush()
        application = Application(organization_id=user.organization_id, candidate_id=candidate.id, job_id=job.id, resume_id=resume.id, owner_id=recruiter_id)
        db.add(application); db.flush()
        db.add_all([
            JobCollaborator(organization_id=user.organization_id, job_id=job.id, user_id=recruiter_id, access_role="job_owner"),
            CandidateEvent(organization_id=user.organization_id, candidate_id=candidate.id, actor_user_id=recruiter_id, event_type="application.created", payload={"application_id": str(application.id), "job_id": str(job.id)}),
        ]); db.commit()
        application_id, candidate_id = str(application.id), str(candidate.id)

    with TestClient(app) as client:
        headers = login(client, "recruiter@example.test")
        response = client.patch(f"/api/v1/applications/{application_id}", json={"human_conclusion": "建议推进"}, headers={**headers, "If-Match": '"1"'})

    assert response.status_code == 200
    assert response.json()["data"]["human_conclusion"] == "建议推进"
    with TestClient(app) as client:
        login(client, "recruiter@example.test")
        timeline = client.get(f"/api/v1/candidates/{candidate_id}/timeline")
    assert [event["event_type"] for event in timeline.json()["data"]] == ["application.updated", "application.created"]
    assert [event["summary"] for event in timeline.json()["data"]] == ["Application updated", "Application created"]
    assert all(event["actor_id"] == str(recruiter_id) for event in timeline.json()["data"])
    assert "建议推进" not in timeline.text


def test_application_stage_timeline_summary_includes_safe_transition_reason(tmp_path) -> None:
    app = make_app(tmp_path)
    admin_id = seed_user(app, "recruiting_admin", "admin@example.test")
    recruiter_id = seed_user(app, "recruiter", "recruiter@example.test")
    with app.state.identity_store.sync_session() as db:
        admin = db.get(User, admin_id)
        job = Job(organization_id=admin.organization_id, title="Engineer", owner_id=admin_id)
        candidate = Candidate(organization_id=admin.organization_id, display_name="Candidate", owner_id=recruiter_id)
        file = FileObject(organization_id=admin.organization_id, storage_key="private/stage-resume", original_filename="resume.pdf", mime_type="application/pdf", size_bytes=12, sha256="a" * 64, uploaded_by=admin_id)
        db.add_all([job, candidate, file]); db.flush()
        resume = Resume(organization_id=admin.organization_id, candidate_id=candidate.id, file_object_id=file.id, version_number=1)
        db.add(resume); db.flush()
        application = Application(organization_id=admin.organization_id, candidate_id=candidate.id, job_id=job.id, resume_id=resume.id, owner_id=recruiter_id, human_conclusion="建议推进：技术能力符合")
        db.add(application); db.commit()
        application_id, candidate_id = str(application.id), str(candidate.id)

    reason = "岗位核心经验不足"
    with TestClient(app) as client:
        headers = login(client, "admin@example.test")
        changed = client.post(
            f"/api/v1/applications/{application_id}/transitions",
            json={"target": "rejected", "reason_text": reason},
            headers={**headers, "If-Match": '"1"', "Idempotency-Key": "reject-with-reason"},
        )
        assert changed.status_code == 200
        timeline = client.get(f"/api/v1/candidates/{candidate_id}/timeline")

    assert timeline.status_code == 200
    stage_event = next(event for event in timeline.json()["data"] if event["event_type"] == "application.stage_changed")
    assert stage_event["summary"] == f"Application stage changed from new to rejected: {reason}"
    with app.state.identity_store.sync_session() as db:
        assert db.query(ApplicationStageEvent).one().payload["reason_text"] == reason
        assert db.get(Application, UUID(application_id)).human_conclusion == "建议推进：技术能力符合"


def test_multi_role_manager_grant_cannot_be_crossed_with_recruiter_actions(tmp_path) -> None:
    app = make_app(tmp_path)
    user_id = seed_user(app, "recruiter", "mixed@example.test")
    with app.state.identity_store.sync_session() as db:
        user = db.get(User, user_id)
        user.roles.append(UserRole(role="hiring_manager"))
        job = Job(organization_id=user.organization_id, title="Managed", owner_id=user_id)
        candidate = Candidate(organization_id=user.organization_id, display_name="Attached", owner_id=None)
        file = FileObject(organization_id=user.organization_id, storage_key="private/resume", original_filename="resume.pdf", mime_type="application/pdf", size_bytes=12, sha256="7" * 64, uploaded_by=user_id)
        db.add_all([job, candidate, file]); db.flush()
        resume = Resume(organization_id=user.organization_id, candidate_id=candidate.id, file_object_id=file.id, version_number=1, parsed_text="preview")
        db.add(resume); db.flush()
        application = Application(organization_id=user.organization_id, candidate_id=candidate.id, job_id=job.id, resume_id=resume.id, owner_id=user_id)
        db.add_all([application, JobCollaborator(organization_id=user.organization_id, job_id=job.id, user_id=user_id, access_role="job_manager")]); db.commit()
        ids = str(job.id), str(candidate.id), str(resume.id), str(application.id)
    job_id, candidate_id, resume_id, application_id = ids

    with TestClient(app) as client:
        headers = login(client, "mixed@example.test")
        assert client.get(f"/api/v1/jobs/{job_id}").status_code == 200
        assert client.get(f"/api/v1/candidates/{candidate_id}").status_code == 200
        preview = client.get(f"/api/v1/resumes/{resume_id}/preview")
        assert preview.status_code == 200 and preview.json()["data"]["text"] == "preview"
        assert client.post(f"/api/v1/candidates/{candidate_id}/notes", json={"application_id": application_id, "body": "Manager comment"}, headers=headers).status_code == 201
        recommendation = client.patch(f"/api/v1/applications/{application_id}", json={"human_conclusion": "recommend"}, headers={**headers, "If-Match": '"1"'})
        assert recommendation.status_code == 200 and recommendation.json()["data"]["human_conclusion"] == "recommend"
        mixed = client.patch(f"/api/v1/applications/{application_id}", json={"owner_id": str(user_id), "human_conclusion": "mixed"}, headers={**headers, "If-Match": '"2"'})
        assert mixed.status_code == 404 and mixed.json()["code"] == "resource_not_found"
        denied = [
            client.patch(f"/api/v1/jobs/{job_id}", json={"title": "Takeover"}, headers={**headers, "If-Match": '"1"'}),
            client.post(f"/api/v1/jobs/{job_id}/transitions", json={"target": "open"}, headers={**headers, "If-Match": '"1"', "Idempotency-Key": "mixed-transition"}),
            client.post(f"/api/v1/jobs/{job_id}/jd-versions", json={"content": {"text": "takeover"}}, headers=headers),
            client.post(f"/api/v1/jobs/{job_id}/applications", json={"candidate_id": candidate_id, "resume_id": resume_id}, headers={**headers, "Idempotency-Key": "mixed-create"}),
            client.post(f"/api/v1/resumes/{resume_id}/download-tickets", headers=headers),
            client.post(f"/api/v1/applications/{application_id}/transitions", json={"target": "review"}, headers={**headers, "If-Match": '"1"', "Idempotency-Key": "mixed-app-transition"}),
        ]
        assert all(response.status_code == 404 for response in denied)


@pytest.mark.parametrize("role", ["hiring_manager", "system_admin", "interviewer"])
def test_non_recruiter_owner_id_never_grants_unassigned_candidate_access(tmp_path, role) -> None:
    app = make_app(tmp_path)
    user_id = seed_user(app, role, f"{role}@example.test")
    with app.state.identity_store.sync_session() as db:
        user = db.get(User, user_id)
        candidate = Candidate(organization_id=user.organization_id, display_name="Legacy owner collision", owner_id=user_id)
        db.add(candidate); db.commit(); candidate_id = str(candidate.id)
    with TestClient(app) as client:
        login(client, f"{role}@example.test")
        response = client.get(f"/api/v1/candidates/{candidate_id}")
        assert response.status_code == 404 and response.json()["code"] == "resource_not_found"


def test_candidate_owner_assignment_requires_active_same_org_recruiter_on_create_and_patch(tmp_path) -> None:
    app = make_app(tmp_path)
    admin_id = seed_user(app, "recruiting_admin", "admin@example.test")
    eligible_id = seed_user(app, "recruiter", "eligible@example.test")
    second_id = seed_user(app, "recruiter", "second@example.test")
    disabled_id = seed_user(app, "recruiter", "disabled@example.test")
    non_recruiter_id = seed_user(app, "hiring_manager", "manager@example.test")
    with app.state.identity_store.sync_session() as db:
        db.get(User, disabled_id).status = UserStatus.DISABLED
        other_org = Organization(slug="other-owner-org", name="Other", status="active")
        cross_org = User(organization=other_org, email="cross@example.test", normalized_email="cross@example.test", display_name="Cross", password_hash=PasswordService().hash("correct horse"))
        cross_org.roles.append(UserRole(role="recruiter")); db.add(cross_org); db.commit(); cross_org_id = cross_org.id
    invalid = [str(disabled_id), str(non_recruiter_id), str(cross_org_id), "00000000-0000-0000-0000-000000000099"]
    with TestClient(app) as client:
        headers = login(client, "admin@example.test")
        for owner_id in invalid:
            denied = client.post("/api/v1/candidates", json={"display_name": "Denied", "owner_id": owner_id}, headers=headers)
            assert denied.status_code == 404 and denied.json()["code"] == "resource_not_found"
        created = client.post("/api/v1/candidates", json={"display_name": "Allowed", "owner_id": str(eligible_id)}, headers=headers)
        assert created.status_code == 201 and created.json()["data"]["owner_id"] == str(eligible_id)
        candidate_id = created.json()["data"]["id"]
        for owner_id in invalid:
            denied = client.patch(f"/api/v1/candidates/{candidate_id}", json={"owner_id": owner_id}, headers={**headers, "If-Match": '"1"'})
            assert denied.status_code == 404 and denied.json()["code"] == "resource_not_found"
        changed = client.patch(f"/api/v1/candidates/{candidate_id}", json={"owner_id": str(second_id)}, headers={**headers, "If-Match": '"1"'})
        assert changed.status_code == 200 and changed.json()["data"]["owner_id"] == str(second_id)


def test_application_owner_assignment_requires_active_same_org_recruiter_on_create_and_patch(tmp_path) -> None:
    app = make_app(tmp_path)
    admin_id = seed_user(app, "recruiting_admin", "admin@example.test")
    eligible_id = seed_user(app, "recruiter", "eligible@example.test")
    second_id = seed_user(app, "recruiter", "second@example.test")
    disabled_id = seed_user(app, "recruiter", "disabled@example.test")
    non_recruiter_id = seed_user(app, "hiring_manager", "manager@example.test")
    with app.state.identity_store.sync_session() as db:
        admin = db.get(User, admin_id)
        db.get(User, disabled_id).status = UserStatus.DISABLED
        other_org = Organization(slug="other-application-owner-org", name="Other", status="active")
        cross_org = User(organization=other_org, email="cross@example.test", normalized_email="cross@example.test", display_name="Cross", password_hash=PasswordService().hash("correct horse"))
        cross_org.roles.append(UserRole(role="recruiter"))
        job = Job(organization_id=admin.organization_id, title="Engineer", owner_id=admin_id)
        candidate = Candidate(organization_id=admin.organization_id, display_name="Candidate", owner_id=eligible_id)
        file = FileObject(organization_id=admin.organization_id, storage_key="private/application-owner", original_filename="resume.pdf", mime_type="application/pdf", size_bytes=12, sha256="9" * 64, uploaded_by=admin_id)
        db.add_all([cross_org, job, candidate, file]); db.flush()
        resume = Resume(organization_id=admin.organization_id, candidate_id=candidate.id, file_object_id=file.id, version_number=1)
        db.add_all([resume, JobCollaborator(organization_id=admin.organization_id, job_id=job.id, user_id=admin_id, access_role="job_owner")]); db.commit()
        job_id, candidate_id, resume_id, cross_org_id = map(str, (job.id, candidate.id, resume.id, cross_org.id))

    with TestClient(app) as client:
        headers = login(client, "admin@example.test")
        payload = {"candidate_id": candidate_id, "resume_id": resume_id, "owner_id": str(disabled_id)}
        denied_create = client.post(f"/api/v1/jobs/{job_id}/applications", json=payload, headers={**headers, "Idempotency-Key": "invalid-application-owner"})
        assert denied_create.status_code == 404 and denied_create.json()["code"] == "resource_not_found"

        payload["owner_id"] = str(eligible_id)
        created = client.post(f"/api/v1/jobs/{job_id}/applications", json=payload, headers={**headers, "Idempotency-Key": "valid-application-owner"})
        assert created.status_code == 201 and created.json()["data"]["owner_id"] == str(eligible_id)
        application_id = created.json()["data"]["id"]

        for owner_id in (str(disabled_id), str(non_recruiter_id), cross_org_id, "00000000-0000-0000-0000-000000000099"):
            denied_patch = client.patch(f"/api/v1/applications/{application_id}", json={"owner_id": owner_id}, headers={**headers, "If-Match": '"1"'})
            assert denied_patch.status_code == 404 and denied_patch.json()["code"] == "resource_not_found"

        changed = client.patch(f"/api/v1/applications/{application_id}", json={"owner_id": str(second_id)}, headers={**headers, "If-Match": '"1"'})
        assert changed.status_code == 200 and changed.json()["data"]["owner_id"] == str(second_id)


@pytest.mark.parametrize("failure", ["open", "mid-read"])
def test_download_storage_failure_leaves_ticket_usable_and_has_no_success_audit(tmp_path, failure) -> None:
    app = make_app(tmp_path, FailingStorage(failure))
    admin_id = seed_user(app, "recruiting_admin", "admin@example.test")
    with TestClient(app) as client:
        headers = login(client, "admin@example.test")
        candidate = client.post("/api/v1/candidates", json={"display_name": "Candidate"}, headers=headers).json()["data"]
        with app.state.identity_store.sync_session() as db:
            user = db.get(User, admin_id)
            job = Job(organization_id=user.organization_id, title="Storage failure job", owner_id=admin_id)
            file = FileObject(organization_id=user.organization_id, storage_key="private/resume", original_filename="resume.pdf", mime_type="application/pdf", size_bytes=12, sha256="6" * 64, uploaded_by=admin_id)
            db.add_all([job, file]); db.flush()
            resume = Resume(organization_id=user.organization_id, candidate_id=UUID(candidate["id"]), file_object_id=file.id, version_number=1, parsed_text="preview")
            db.add(resume); db.flush()
            db.add(Application(organization_id=user.organization_id, candidate_id=UUID(candidate["id"]), job_id=job.id, resume_id=resume.id, owner_id=admin_id))
            db.commit(); resume_id = str(resume.id)
        ticket = client.post(f"/api/v1/resumes/{resume_id}/download-tickets", headers=headers).json()["data"]["token"]
        response = client.post("/api/v1/download-tickets/consume", json={"token": ticket}, headers=headers)
        assert response.status_code == 503 and response.json()["code"] == "attachment_unavailable"
        with app.state.identity_store.sync_session() as db:
            assert db.query(DownloadTicket).one().consumed_at is None
            assert db.query(AuditLog).filter_by(event_type="resume.downloaded").count() == 0
