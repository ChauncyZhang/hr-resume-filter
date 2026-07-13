import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from server.app.core.settings import Settings
from server.app.identity.models import (
    Department,
    Job,
    JobCollaborator,
    Organization,
    User,
    UserRole,
)
from server.app.identity.policy import Principal
from server.app.identity.security import PasswordService
from server.app.main import create_app
from server.app.recruiting import api as recruiting_api
from server.app.recruiting.models import Application, Candidate, FileObject, Resume


class Probe:
    async def check(self) -> None:
        pass


def make_app(tmp_path):
    app = create_app(
        settings=Settings(
            environment="test",
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'workbench.db'}",
            cors_origins=["https://hr.example.test"],
        ),
        database_probe=Probe(),
        storage_probe=Probe(),
        initialize_identity_schema=True,
    )
    app.state.identity_store.create_schema()
    return app


def seed_user(db, organization, role: str, email: str):
    user = User(
        organization=organization,
        email=email,
        normalized_email=email,
        display_name=role,
        password_hash=PasswordService().hash("correct horse"),
    )
    user.roles.append(UserRole(role=role))
    db.add(user)
    db.flush()
    return user


def seed_application(db, job, owner, index: int, stage: str, updated_at: datetime):
    candidate = Candidate(
        organization_id=job.organization_id,
        display_name=f"Candidate {index}",
        current_title=f"Title {index}",
        location=f"Location {index}",
        owner_id=owner.id,
        updated_at=updated_at,
    )
    file = FileObject(
        organization_id=job.organization_id,
        storage_key=f"private/workbench/{job.id}/{index}",
        original_filename=f"resume-{index}.pdf",
        mime_type="application/pdf",
        size_bytes=1,
        sha256=f"{index + 1:064x}"[-64:],
        uploaded_by=owner.id,
    )
    db.add_all([candidate, file])
    db.flush()
    resume = Resume(
        organization_id=job.organization_id,
        candidate_id=candidate.id,
        file_object_id=file.id,
        version_number=1,
        parsed_text="must not be returned",
    )
    db.add(resume)
    db.flush()
    application = Application(
        organization_id=job.organization_id,
        candidate_id=candidate.id,
        job_id=job.id,
        resume_id=resume.id,
        owner_id=owner.id,
        source=f"source-{index}",
        stage=stage,
        human_conclusion="must not be returned",
        updated_at=updated_at,
    )
    db.add(application)
    db.flush()
    return application


def principal(user, role: str | None = None) -> Principal:
    return Principal(
        user_id=user.id,
        organization_id=user.organization_id,
        roles=frozenset({role or user.roles[0].role}),
        active=True,
    )


def test_workbench_contract_filters_terminal_rows_and_caps_newest_items(tmp_path, monkeypatch) -> None:
    app = make_app(tmp_path)
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    with app.state.identity_store.sync_session() as db:
        organization = Organization(slug="acme", name="Acme", status="active")
        admin = seed_user(db, organization, "recruiting_admin", "admin@example.test")
        department = Department(organization_id=organization.id, name="Engineering")
        db.add(department)
        db.flush()
        jobs = [
            Job(
                organization_id=organization.id,
                title=f"Open {index}",
                department_id=department.id if index == 21 else None,
                owner_id=admin.id,
                status="open",
                updated_at=base + timedelta(days=index),
            )
            for index in range(22)
        ]
        closed = Job(
            organization_id=organization.id,
            title="Closed secret",
            owner_id=admin.id,
            status="closed",
            updated_at=base + timedelta(days=30),
        )
        db.add_all([*jobs, closed])
        db.flush()
        target = jobs[-1]
        second_visible = jobs[-2]
        excluded = jobs[0]
        applications = [
            seed_application(db, target, admin, index, "new", base + timedelta(hours=index))
            for index in range(7)
        ]
        contact_applications = []
        for index, stage in enumerate(
            ("review", "contact", "interview_pending", "interviewing", "decision"),
            start=10,
        ):
            application = seed_application(db, target, admin, index, stage, base + timedelta(hours=index))
            if stage == "contact":
                contact_applications.append(application)
        contact_applications.extend(
            seed_application(db, target, admin, index, "contact", base + timedelta(hours=index))
            for index in range(31, 36)
        )
        contact_applications.extend([
            seed_application(db, second_visible, admin, 41, "contact", base + timedelta(hours=35)),
            seed_application(db, second_visible, admin, 42, "contact", base + timedelta(hours=33)),
        ])
        for index, stage in enumerate(("passed", "hired", "rejected", "withdrawn"), start=20):
            seed_application(db, target, admin, index, stage, base + timedelta(hours=index))
        seed_application(db, closed, admin, 30, "contact", base + timedelta(days=31))
        seed_application(db, excluded, admin, 50, "contact", base + timedelta(days=40))
        db.commit()
        admin_principal = principal(admin)
        expected_new_ids = [str(item.id) for item in reversed(applications[-5:])]
        expected_contact_ids = [
            str(item.id)
            for item in sorted(contact_applications, key=lambda item: (item.updated_at, item.id), reverse=True)[:5]
        ]

    monkeypatch.setattr(recruiting_api, "_principal", lambda request: admin_principal)
    with TestClient(app) as client:
        response = client.get("/api/v1/workbench")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"data"}
    assert datetime.fromisoformat(body["data"]["generated_at"]).tzinfo is not None
    assert len(body["data"]["jobs"]) == 20
    assert [job["title"] for job in body["data"]["jobs"][:2]] == ["Open 21", "Open 20"]
    assert "Closed secret" not in response.text

    job = body["data"]["jobs"][0]
    assert set(job) == {"id", "title", "department_name", "status", "updated_at", "active_count", "stages"}
    assert job["department_name"] == "Engineering"
    assert job["status"] == "open"
    assert job["active_count"] == 17
    assert list(job["stages"]) == [
        "new",
        "review",
        "contact",
        "interview_pending",
        "interviewing",
        "decision",
    ]
    assert job["stages"]["new"]["count"] == 7
    assert [item["application_id"] for item in job["stages"]["new"]["items"]] == expected_new_ids
    assert job["stages"]["contact"]["count"] == 6
    assert all(len(stage["items"]) <= 5 for stage in job["stages"].values())
    candidate_item = job["stages"]["new"]["items"][0]
    assert set(candidate_item) == {
        "application_id",
        "candidate_id",
        "job_id",
        "display_name",
        "current_title",
        "location",
        "source",
        "stage",
        "updated_at",
    }
    assert "must not be returned" not in response.text
    assert "Candidate 50" not in response.text
    assert body["data"]["interviews"] == {
        "available": False,
        "upcoming": [],
        "pending_feedback": [],
    }
    assert list(body["data"]["tasks"]) == ["contact", "interview_pending", "decision"]
    assert body["data"]["tasks"]["contact"]["count"] == 8
    assert [
        item["application_id"] for item in body["data"]["tasks"]["contact"]["items"]
    ] == expected_contact_ids
    assert len(body["data"]["tasks"]["contact"]["items"]) <= 5
    assert body["data"]["tasks"]["interview_pending"]["count"] == 1
    assert body["data"]["tasks"]["decision"]["count"] == 1


def test_workbench_empty_state_is_stable(tmp_path, monkeypatch) -> None:
    app = make_app(tmp_path)
    with app.state.identity_store.sync_session() as db:
        organization = Organization(slug="acme", name="Acme", status="active")
        admin = seed_user(db, organization, "recruiting_admin", "admin@example.test")
        db.commit()
        admin_principal = principal(admin)

    monkeypatch.setattr(recruiting_api, "_principal", lambda request: admin_principal)
    with TestClient(app) as client:
        response = client.get("/api/v1/workbench")

    assert response.status_code == 200
    assert response.json()["data"] | {"generated_at": None} == {
        "generated_at": None,
        "jobs": [],
        "tasks": {
            "contact": {"count": 0, "items": []},
            "interview_pending": {"count": 0, "items": []},
            "decision": {"count": 0, "items": []},
        },
        "interviews": {"available": False, "upcoming": [], "pending_feedback": []},
    }


@pytest.mark.parametrize("role", ["system_admin", "interviewer", "unknown"])
def test_workbench_requires_recruiting_read_role(tmp_path, monkeypatch, role) -> None:
    app = make_app(tmp_path)
    with app.state.identity_store.sync_session() as db:
        organization = Organization(slug="acme", name="Acme", status="active")
        stored_role = role if role != "unknown" else "system_admin"
        user = seed_user(db, organization, stored_role, f"{role}@example.test")
        db.commit()
        denied_principal = principal(user, role)

    monkeypatch.setattr(recruiting_api, "_principal", lambda request: denied_principal)
    with TestClient(app) as client:
        denied = client.get("/api/v1/workbench")
    assert denied.status_code == 404
    assert denied.json()["code"] == "resource_not_found"


def test_workbench_requires_authentication(tmp_path) -> None:
    app = make_app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/v1/workbench")
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


@pytest.mark.parametrize(
    ("role", "access_role"),
    [("recruiter", "job_recruiter"), ("hiring_manager", "job_manager")],
)
def test_workbench_is_collaborator_scoped_and_cross_tenant_non_disclosing(
    tmp_path, monkeypatch, role, access_role
) -> None:
    app = make_app(tmp_path)
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    with app.state.identity_store.sync_session() as db:
        acme = Organization(slug="acme", name="Acme", status="active")
        other = Organization(slug="other", name="Other", status="active")
        actor = seed_user(db, acme, role, f"{role}@example.test")
        owner = seed_user(db, acme, "recruiting_admin", "owner@example.test")
        other_owner = seed_user(db, other, "recruiting_admin", "other@example.test")
        allowed = Job(organization_id=acme.id, title="Allowed", owner_id=owner.id, status="open", updated_at=base)
        hidden = Job(organization_id=acme.id, title="Hidden same tenant", owner_id=owner.id, status="open", updated_at=base)
        cross_tenant = Job(organization_id=other.id, title="Hidden other tenant", owner_id=other_owner.id, status="open", updated_at=base)
        db.add_all([allowed, hidden, cross_tenant])
        db.flush()
        db.add(JobCollaborator(
            organization_id=acme.id,
            job_id=allowed.id,
            user_id=actor.id,
            access_role=access_role,
        ))
        seed_application(db, allowed, owner, 1, "contact", base)
        seed_application(db, hidden, owner, 2, "contact", base + timedelta(hours=1))
        seed_application(db, cross_tenant, other_owner, 3, "contact", base + timedelta(hours=2))
        db.commit()
        actor_principal = principal(actor, role)

    monkeypatch.setattr(recruiting_api, "_principal", lambda request: actor_principal)
    with TestClient(app) as client:
        response = client.get("/api/v1/workbench")

    assert response.status_code == 200
    assert [job["title"] for job in response.json()["data"]["jobs"]] == ["Allowed"]
    assert response.json()["data"]["tasks"]["contact"]["count"] == 1
    assert len(response.json()["data"]["tasks"]["contact"]["items"]) == 1
    assert "Hidden" not in response.text


def test_workbench_query_count_is_bounded(tmp_path, monkeypatch) -> None:
    app = make_app(tmp_path)
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    with app.state.identity_store.sync_session() as db:
        organization = Organization(slug="acme", name="Acme", status="active")
        admin = seed_user(db, organization, "recruiting_admin", "admin@example.test")
        jobs = [
            Job(organization_id=organization.id, title=f"Job {index}", owner_id=admin.id, status="open")
            for index in range(8)
        ]
        db.add_all(jobs)
        db.flush()
        for job_index, job in enumerate(jobs):
            for application_index in range(3):
                seed_application(
                    db,
                    job,
                    admin,
                    job_index * 10 + application_index,
                    "new",
                    base + timedelta(minutes=application_index),
                )
        db.commit()
        admin_principal = principal(admin)

    monkeypatch.setattr(recruiting_api, "_principal", lambda request: admin_principal)
    statements = []
    engine = app.state.identity_store.engine
    def record_statement(*args):
        statements.append(args[2])

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/workbench")
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert response.status_code == 200
    selects = [statement for statement in statements if statement.lstrip().upper().startswith("SELECT")]
    assert len(selects) <= 2


def test_workbench_openapi_enforces_bounded_non_sensitive_contract(tmp_path) -> None:
    app = make_app(tmp_path)
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    operation = schema["paths"]["/api/v1/workbench"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/WorkbenchResource"
    }
    components = {
        name: value
        for name, value in schema["components"]["schemas"].items()
        if name.startswith("Workbench")
    }
    rendered = json.dumps(components).casefold()
    for forbidden in ("contact", "resume", "human_conclusion", "parsed_text", "screening"):
        if forbidden == "contact":
            assert '"contacts"' not in rendered
        else:
            assert forbidden not in rendered

    candidate = components["WorkbenchCandidateOut"]["properties"]
    assert candidate["stage"]["enum"] == [
        "new", "review", "contact", "interview_pending", "interviewing", "decision"
    ]
    assert components["WorkbenchStageOut"]["properties"]["count"]["minimum"] == 0
    assert components["WorkbenchStageOut"]["properties"]["items"]["maxItems"] == 5
    assert components["WorkbenchOut"]["properties"]["jobs"]["maxItems"] == 20
    assert components["WorkbenchJobOut"]["properties"]["status"]["const"] == "open"
    interviews = components["WorkbenchInterviewsOut"]["properties"]
    assert interviews["upcoming"]["maxItems"] == 0
    assert interviews["pending_feedback"]["maxItems"] == 0
