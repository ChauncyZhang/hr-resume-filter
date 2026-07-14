from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from server.app.core.settings import Settings
from server.app.identity.models import AuditLog, Job, JobCollaborator, Organization, User, UserRole
from server.app.identity.security import PasswordService
from server.app.main import create_app
from server.app.recruiting.models import (
    Application,
    ApplicationStageEvent,
    CandidateContact,
    CandidateEvent,
    FileObject,
    IdempotencyRecord,
    Resume,
)
from server.app.talent.models import TalentPoolMembership
from server.app.talent.api import _is_active_application_conflict
from server.tests.test_interview_api import seed_application
from server.tests.test_recruiting_api import login, seed_user


class Probe:
    async def check(self) -> None:
        pass


class ConstraintDiagnostic:
    def __init__(self, name):
        self.constraint_name = name


class ConstraintOrigin(Exception):
    def __init__(self, name):
        self.diag = ConstraintDiagnostic(name)


def make_app(tmp_path):
    app = create_app(
        settings=Settings(
            environment="test",
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'talent-api.db'}",
            cors_origins=["https://hr.example.test"],
        ),
        database_probe=Probe(),
        storage_probe=Probe(),
        initialize_identity_schema=True,
    )
    app.state.identity_store.create_schema()
    return app


def pool_payload(owner_id):
    return {
        "name": "AI 技术人才",
        "purpose": "沉淀大模型和 AI 应用人才",
        "visibility": "recruiting_team",
        "owner_id": str(owner_id),
        "suitable_roles": ["AI 工程师", "算法工程师"],
        "retention_days": 730,
        "grants": [],
    }


def membership_payload(seed):
    return {
        "candidate_id": str(seed["candidate_id"]),
        "source_application_id": str(seed["application_id"]),
        "owner_id": str(seed["admin_id"]),
        "suitable_roles": ["AI 工程师"],
        "tags": ["RAG", "Agent"],
        "reason": "技术匹配，等待更合适的机会",
        "next_contact_at": "2026-08-01T02:00:00+00:00",
        "retention_until": "2028-07-31T16:00:00+00:00",
    }


def create_pool_and_membership(client, seed):
    headers = login(client, "interview-admin@example.test")
    pool = client.post(
        "/api/v1/talent-pools",
        json=pool_payload(seed["admin_id"]),
        headers={**headers, "Idempotency-Key": "create-ai-pool"},
    )
    assert pool.status_code == 201
    pool_id = pool.json()["data"]["id"]
    membership = client.post(
        f"/api/v1/talent-pools/{pool_id}/memberships",
        json=membership_payload(seed),
        headers={**headers, "Idempotency-Key": "add-ai-member"},
    )
    assert membership.status_code == 201
    return headers, pool, membership


def test_talent_openapi_registers_phase_5_pool_contract(tmp_path) -> None:
    app = make_app(tmp_path)
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]

    expected = {
        "/api/v1/talent-pools": {"get", "post"},
        "/api/v1/talent-pools/{pool_id}": {"get", "patch"},
        "/api/v1/talent-pools/{pool_id}/memberships": {"get", "post"},
        "/api/v1/talent-pool-memberships/{membership_id}": {"patch", "delete"},
        "/api/v1/talent-pool-memberships/{membership_id}/reactivations": {"post"},
    }
    assert {path: set(paths.get(path, {})) for path in expected} == expected


def test_only_named_active_application_constraint_is_translated() -> None:
    active = IntegrityError("insert", {}, ConstraintOrigin("uq_applications_active"))
    unrelated = IntegrityError("insert", {}, ConstraintOrigin("uq_talent_pool_membership_candidate"))

    assert _is_active_application_conflict(active) is True
    assert _is_active_application_conflict(unrelated) is False


def test_pool_membership_round_trip_is_tenant_scoped_and_does_not_mutate_application(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    with app.state.identity_store.sync_session() as database:
        source = database.get(Application, seed["application_id"])
        source.stage = "rejected"
        source.version += 1
        database.commit()
        source_version = source.version

    with TestClient(app) as client:
        headers, pool, membership = create_pool_and_membership(client, seed)
        pool_id = pool.json()["data"]["id"]
        listed = client.get("/api/v1/talent-pools", headers=headers)
        members = client.get(f"/api/v1/talent-pools/{pool_id}/memberships", headers=headers)

    assert listed.status_code == members.status_code == 200
    assert listed.headers["Cache-Control"] == members.headers["Cache-Control"] == "no-store"
    assert listed.json()["data"][0]["member_count"] == 1
    member = members.json()["data"][0]
    assert member["candidate"]["display_name"] == "李嘉明"
    assert member["source_application"]["id"] == str(seed["application_id"])
    assert member["tags"] == ["RAG", "Agent"]
    assert "email" not in members.text
    assert "phone" not in members.text

    with app.state.identity_store.sync_session() as database:
        source = database.get(Application, seed["application_id"])
        assert source.stage == "rejected"
        assert source.version == source_version


def test_private_pool_is_hidden_from_other_recruiters_and_cross_tenant_admins(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    with app.state.identity_store.sync_session() as database:
        admin = database.get(User, seed["admin_id"])
        recruiter = User(
            organization_id=admin.organization_id,
            email="pool-recruiter@example.test",
            normalized_email="pool-recruiter@example.test",
            display_name="Pool Recruiter",
            password_hash=PasswordService().hash("correct horse"),
        )
        recruiter.roles.append(UserRole(role="recruiter"))
        other_org = Organization(slug="pool-other", name="Pool Other", status="active")
        other_admin = User(
            organization=other_org,
            email="pool-other@example.test",
            normalized_email="pool-other@example.test",
            display_name="Other Admin",
            password_hash=PasswordService().hash("correct horse"),
        )
        other_admin.roles.append(UserRole(role="recruiting_admin"))
        database.add_all([recruiter, other_admin])
        database.commit()

    payload = {**pool_payload(seed["admin_id"]), "name": "仅负责人可见", "visibility": "private"}
    with TestClient(app) as client:
        owner_headers = login(client, "interview-admin@example.test")
        created = client.post(
            "/api/v1/talent-pools",
            json=payload,
            headers={**owner_headers, "Idempotency-Key": "private-pool"},
        )
        pool_id = created.json()["data"]["id"]
        recruiter_headers = login(client, "pool-recruiter@example.test")
        assert client.get("/api/v1/talent-pools", headers=recruiter_headers).json()["data"] == []
        denied = client.get(f"/api/v1/talent-pools/{pool_id}", headers=recruiter_headers)

        other_login = client.post(
            "/api/v1/auth/login",
            json={"organization_slug": "pool-other", "email": "pool-other@example.test", "password": "correct horse"},
            headers={"Origin": "https://hr.example.test"},
        )
        cross_tenant = client.get(
            f"/api/v1/talent-pools/{pool_id}",
            headers={"Origin": "https://hr.example.test", "X-CSRF-Token": other_login.headers["X-CSRF-Token"]},
        )

    assert denied.status_code == cross_tenant.status_code == 404
    assert denied.json()["code"] == cross_tenant.json()["code"] == "resource_not_found"


def test_reactivation_creates_linked_application_preserves_history_and_rejects_active_duplicate(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    with app.state.identity_store.sync_session() as database:
        source = database.get(Application, seed["application_id"])
        source.stage = "rejected"
        source.version += 1
        target = Job(
            organization_id=source.organization_id,
            title="RAG Engineer",
            owner_id=seed["admin_id"],
            status="open",
        )
        database.add(target)
        database.flush()
        database.add(
            JobCollaborator(
                organization_id=source.organization_id,
                job_id=target.id,
                user_id=seed["admin_id"],
                access_role="job_owner",
            )
        )
        database.commit()
        target_id = target.id
        source_version = source.version

    with TestClient(app) as client:
        headers, _, membership = create_pool_and_membership(client, seed)
        membership_id = membership.json()["data"]["id"]
        with app.state.identity_store.sync_session() as database:
            pii_counts = {
                "contacts": database.query(CandidateContact).count(),
                "files": database.query(FileObject).count(),
                "resumes": database.query(Resume).count(),
            }
        first = client.post(
            f"/api/v1/talent-pool-memberships/{membership_id}/reactivations",
            json={"job_id": str(target_id)},
            headers={**headers, "Idempotency-Key": "reactivate-rag"},
        )
        replay = client.post(
            f"/api/v1/talent-pool-memberships/{membership_id}/reactivations",
            json={"job_id": str(target_id)},
            headers={**headers, "Idempotency-Key": "reactivate-rag"},
        )
        duplicate = client.post(
            f"/api/v1/talent-pool-memberships/{membership_id}/reactivations",
            json={"job_id": str(target_id)},
            headers={**headers, "Idempotency-Key": "reactivate-rag-again"},
        )
        timeline = client.get(
            f"/api/v1/candidates/{seed['candidate_id']}/timeline",
            headers=headers,
        )

    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "active_application_exists"
    assert timeline.status_code == 200
    assert any(
        event["event_type"] == "application.reactivated"
        and event["summary"] == "Application reactivated from talent pool"
        for event in timeline.json()["data"]
    )
    created_id = first.json()["data"]["id"]
    assert first.json()["data"]["source_application_id"] == str(seed["application_id"])
    assert first.json()["data"]["source"] == "talent_pool_reactivation"

    with app.state.identity_store.sync_session() as database:
        source = database.get(Application, seed["application_id"])
        created = database.get(Application, UUID(created_id))
        membership_row = database.get(TalentPoolMembership, UUID(membership_id))
        assert source.stage == "rejected"
        assert source.version == source_version
        assert created.candidate_id == source.candidate_id
        assert created.job_id == target_id
        assert created.resume_id == source.resume_id
        assert created.source_application_id == source.id
        assert membership_row.status == "active"
        assert database.query(ApplicationStageEvent).filter(
            ApplicationStageEvent.event_type == "application.reactivated"
        ).count() == 1
        assert database.query(CandidateEvent).filter(
            CandidateEvent.event_type == "candidate.reactivated"
        ).count() == 1
        assert database.query(AuditLog).filter(
            AuditLog.event_type == "talent_pool.member_reactivated"
        ).count() == 1
        assert database.query(IdempotencyRecord).filter(
            IdempotencyRecord.operation == "talent_pool.reactivate"
        ).count() == 1
        assert database.query(CandidateContact).count() == pii_counts["contacts"]
        assert database.query(FileObject).count() == pii_counts["files"]
        assert database.query(Resume).count() == pii_counts["resumes"]


def test_source_application_requires_job_access_and_is_redacted_after_access_is_lost(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    recruiter_id = seed_user(app, "recruiter", "talent-scoped@example.test")
    with app.state.identity_store.sync_session() as database:
        source = database.get(Application, seed["application_id"])
        source.stage = "rejected"
        source.version += 1
        denied_job = Job(
            organization_id=source.organization_id,
            title="Restricted source",
            owner_id=seed["admin_id"],
            status="open",
        )
        target_job = Job(
            organization_id=source.organization_id,
            title="Authorized target",
            owner_id=recruiter_id,
            status="open",
        )
        denied_file = FileObject(
            organization_id=source.organization_id,
            storage_key="talent/restricted-resume.pdf",
            original_filename="restricted.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            sha256="b" * 64,
            uploaded_by=seed["admin_id"],
        )
        database.add_all([denied_job, target_job, denied_file])
        database.flush()
        denied_resume = Resume(
            organization_id=source.organization_id,
            candidate_id=source.candidate_id,
            file_object_id=denied_file.id,
            version_number=2,
            parsed_text="restricted resume contents",
        )
        database.add(denied_resume)
        database.flush()
        denied_application = Application(
            organization_id=source.organization_id,
            candidate_id=source.candidate_id,
            job_id=denied_job.id,
            resume_id=denied_resume.id,
            owner_id=seed["admin_id"],
            stage="rejected",
        )
        source_grant = JobCollaborator(
            organization_id=source.organization_id,
            job_id=source.job_id,
            user_id=recruiter_id,
            access_role="job_recruiter",
        )
        target_grant = JobCollaborator(
            organization_id=source.organization_id,
            job_id=target_job.id,
            user_id=recruiter_id,
            access_role="job_owner",
        )
        database.add_all([denied_application, source_grant, target_grant])
        database.commit()
        denied_application_id = denied_application.id
        denied_resume_id = denied_resume.id
        target_job_id = target_job.id
        source_resume_id = source.resume_id

    with TestClient(app) as client:
        admin_headers = login(client, "interview-admin@example.test")
        pool = client.post(
            "/api/v1/talent-pools",
            json={**pool_payload(recruiter_id), "name": "Scoped talent", "visibility": "private"},
            headers={**admin_headers, "Idempotency-Key": "scoped-talent-pool"},
        )
        assert pool.status_code == 201
        pool_id = pool.json()["data"]["id"]
        recruiter_headers = login(client, "talent-scoped@example.test")
        denied_membership = client.post(
            f"/api/v1/talent-pools/{pool_id}/memberships",
            json={**membership_payload(seed), "source_application_id": str(denied_application_id), "owner_id": str(recruiter_id)},
            headers={**recruiter_headers, "Idempotency-Key": "denied-source-membership"},
        )
        assert denied_membership.status_code == 404
        membership = client.post(
            f"/api/v1/talent-pools/{pool_id}/memberships",
            json={**membership_payload(seed), "owner_id": str(recruiter_id)},
            headers={**recruiter_headers, "Idempotency-Key": "allowed-source-membership"},
        )
        assert membership.status_code == 201
        membership_id = membership.json()["data"]["id"]

        with app.state.identity_store.sync_session() as database:
            database.delete(database.get(JobCollaborator, source_grant.id))
            database.commit()

        listed = client.get(f"/api/v1/talent-pools/{pool_id}/memberships", headers=recruiter_headers)
        default_resume = client.post(
            f"/api/v1/talent-pool-memberships/{membership_id}/reactivations",
            json={"job_id": str(target_job_id)},
            headers={**recruiter_headers, "Idempotency-Key": "default-source-resume"},
        )
        override_resume = client.post(
            f"/api/v1/talent-pool-memberships/{membership_id}/reactivations",
            json={"job_id": str(target_job_id), "resume_id": str(denied_resume_id)},
            headers={**recruiter_headers, "Idempotency-Key": "override-source-resume"},
        )
        source_preview = client.get(f"/api/v1/resumes/{source_resume_id}/preview", headers=recruiter_headers)
        override_preview = client.get(f"/api/v1/resumes/{denied_resume_id}/preview", headers=recruiter_headers)

    assert listed.status_code == 200
    assert listed.json()["data"][0]["source_application"] == {
        "id": str(seed["application_id"]),
        "redacted": True,
    }
    assert default_resume.status_code == override_resume.status_code == 404
    assert source_preview.status_code == override_preview.status_code == 404
    with app.state.identity_store.sync_session() as database:
        assert database.query(Application).filter(
            Application.organization_id == source.organization_id,
            Application.candidate_id == seed["candidate_id"],
            Application.job_id == target_job_id,
        ).count() == 0


def test_membership_removal_audit_does_not_store_user_reason(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    removal_reason = "候选人要求停止联系，内部备注不得进入审计元数据"

    with TestClient(app) as client:
        headers, _, membership = create_pool_and_membership(client, seed)
        member = membership.json()["data"]
        removed = client.request(
            "DELETE",
            f"/api/v1/talent-pool-memberships/{member['id']}",
            json={"reason": removal_reason},
            headers={**headers, "If-Match": f'"{member["version"]}"'},
        )

    assert removed.status_code == 204
    with app.state.identity_store.sync_session() as database:
        audit = database.scalar(
            select(AuditLog).where(AuditLog.event_type == "talent_pool.member_removed")
        )
        assert audit is not None
        assert audit.metadata_json["reason_provided"] is True
        assert removal_reason not in str(audit.metadata_json)
