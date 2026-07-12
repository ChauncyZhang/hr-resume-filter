from dataclasses import dataclass
from uuid import UUID

from fastapi.testclient import TestClient

from server.app.core.settings import Settings
from server.app.identity.models import Organization, User, UserRole
from server.app.identity.security import PasswordService
from server.app.main import create_app
from server.app.recruiting.models import FileObject, Resume
from server.app.recruiting.storage import StoredDownload


class Probe:
    async def check(self) -> None:
        pass


@dataclass
class FakeStorage:
    preview: str = "private parsed preview"

    def read_preview(self, storage_key: str) -> str:
        assert storage_key == "private/resume"
        return self.preview

    def stream_download(self, storage_key: str, content_type: str, filename: str) -> StoredDownload:
        assert storage_key == "private/resume"
        return StoredDownload([b"private-file"], content_type, filename)


def make_app(tmp_path):
    app = create_app(
        settings=Settings(
            environment="test",
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'recruiting-api.db'}",
            cors_origins=["https://hr.example.test"],
        ),
        database_probe=Probe(),
        storage_probe=Probe(),
        initialize_identity_schema=True,
        resume_storage=FakeStorage(),
    )
    app.state.identity_store.create_schema()
    return app


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
        ticket = client.post(f"/api/v1/resumes/{resume_id}/download-tickets", headers=headers)
        raw = ticket.json()["data"]["token"]
        assert raw not in str(ticket.request.url)
        download = client.post("/api/v1/download-tickets/consume", json={"token": raw}, headers=headers)
        assert download.content == b"private-file"
        assert download.headers["cache-control"] == "no-store"
        assert download.headers["content-disposition"].startswith("attachment;")
        assert download.headers["x-content-type-options"] == "nosniff"
        assert client.post("/api/v1/download-tickets/consume", json={"token": raw}, headers=headers).status_code == 404


def test_system_admin_and_interviewer_have_no_recruiting_access_by_role_alone(tmp_path) -> None:
    app = make_app(tmp_path)
    seed_user(app, "system_admin", "system@example.test")
    seed_user(app, "interviewer", "interviewer@example.test")
    with TestClient(app) as client:
        for email in ("system@example.test", "interviewer@example.test"):
            login(client, email)
            assert client.get("/api/v1/jobs").json() == {"data": [], "meta": {"limit": 50, "next_cursor": None}}
            denied = client.post("/api/v1/candidates", json={"display_name": "Forbidden"}, headers={"Origin": "https://hr.example.test", "X-CSRF-Token": client.get('/api/v1/me', headers={'Sec-Fetch-Site': 'same-origin'}).headers['X-CSRF-Token']})
            assert denied.status_code == 404 and denied.json()["code"] == "resource_not_found"
