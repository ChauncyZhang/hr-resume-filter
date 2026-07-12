from dataclasses import dataclass
from tempfile import SpooledTemporaryFile
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from server.app.core.settings import Settings
from server.app.identity.models import Organization, User, UserRole, Job, JobCollaborator
from server.app.identity.security import PasswordService
from server.app.main import create_app
from server.app.recruiting.models import Candidate, FileObject, Resume
from server.app.recruiting.models import Application, DownloadTicket
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
        created = client.post(f"/api/v1/jobs/{job_id}/applications", json={"candidate_id": candidate_id, "resume_id": resume_id}, headers=app_headers)
        replay = client.post(f"/api/v1/jobs/{job_id}/applications", json={"candidate_id": candidate_id, "resume_id": resume_id}, headers=app_headers)
        assert created.status_code == replay.status_code == 201
        assert created.json() == replay.json()
        conflict = client.post(f"/api/v1/jobs/{job_id}/applications", json={"candidate_id": candidate_id, "resume_id": resume_id, "source": "other"}, headers=app_headers)
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


def test_owning_recruiter_reads_unassigned_timeline_and_comments_via_comment_action(tmp_path) -> None:
    app = make_app(tmp_path)
    seed_user(app, "recruiter", "owner@example.test")
    with TestClient(app) as client:
        headers = login(client, "owner@example.test")
        candidate = client.post("/api/v1/candidates", json={"display_name": "Unassigned"}, headers=headers).json()["data"]
        timeline = client.get(f"/api/v1/candidates/{candidate['id']}/timeline")
        assert timeline.status_code == 200
        assert [event["event_type"] for event in timeline.json()["data"]] == ["candidate.created"]
        note = client.post(f"/api/v1/candidates/{candidate['id']}/notes", json={"body": "Allowed comment"}, headers=headers)
        assert note.status_code == 201


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
        assert client.post(f"/api/v1/candidates/{candidate_id}/notes", json={"body": "Manager comment"}, headers=headers).status_code == 201
        recommendation = client.patch(f"/api/v1/applications/{application_id}", json={"human_conclusion": "recommend"}, headers={**headers, "If-Match": '"1"'})
        assert recommendation.status_code == 200 and recommendation.json()["data"]["human_conclusion"] == "recommend"
        denied = [
            client.patch(f"/api/v1/jobs/{job_id}", json={"title": "Takeover"}, headers={**headers, "If-Match": '"1"'}),
            client.post(f"/api/v1/jobs/{job_id}/transitions", json={"target": "open"}, headers={**headers, "If-Match": '"1"', "Idempotency-Key": "mixed-transition"}),
            client.post(f"/api/v1/jobs/{job_id}/jd-versions", json={"content": {"text": "takeover"}}, headers=headers),
            client.post(f"/api/v1/jobs/{job_id}/applications", json={"candidate_id": candidate_id, "resume_id": resume_id}, headers={**headers, "Idempotency-Key": "mixed-create"}),
            client.post(f"/api/v1/resumes/{resume_id}/download-tickets", headers=headers),
            client.get(f"/api/v1/resumes/{resume_id}/preview"),
            client.post(f"/api/v1/applications/{application_id}/transitions", json={"target": "review"}, headers={**headers, "If-Match": '"1"', "Idempotency-Key": "mixed-app-transition"}),
        ]
        assert all(response.status_code == 404 for response in denied)


@pytest.mark.parametrize("failure", ["open", "mid-read"])
def test_download_storage_failure_leaves_ticket_usable_and_has_no_success_audit(tmp_path, failure) -> None:
    app = make_app(tmp_path, FailingStorage(failure))
    admin_id = seed_user(app, "recruiting_admin", "admin@example.test")
    with TestClient(app) as client:
        headers = login(client, "admin@example.test")
        candidate = client.post("/api/v1/candidates", json={"display_name": "Candidate"}, headers=headers).json()["data"]
        with app.state.identity_store.sync_session() as db:
            user = db.get(User, admin_id)
            file = FileObject(organization_id=user.organization_id, storage_key="private/resume", original_filename="resume.pdf", mime_type="application/pdf", size_bytes=12, sha256="6" * 64, uploaded_by=admin_id)
            db.add(file); db.flush()
            resume = Resume(organization_id=user.organization_id, candidate_id=UUID(candidate["id"]), file_object_id=file.id, version_number=1, parsed_text="preview")
            db.add(resume); db.commit(); resume_id = str(resume.id)
        ticket = client.post(f"/api/v1/resumes/{resume_id}/download-tickets", headers=headers).json()["data"]["token"]
        response = client.post("/api/v1/download-tickets/consume", json={"token": ticket}, headers=headers)
        assert response.status_code == 503 and response.json()["code"] == "attachment_unavailable"
        with app.state.identity_store.sync_session() as db:
            assert db.query(DownloadTicket).one().consumed_at is None
            assert db.query(AuditLog).filter_by(event_type="resume.downloaded").count() == 0
