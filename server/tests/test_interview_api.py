from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from server.app.core.settings import Settings
from server.app.identity.models import Job, JobCollaborator, User, UserRole
from server.app.interviews.models import (
    Interview,
    InterviewEvent,
    InterviewFeedback,
    InterviewFeedbackRevision,
    InterviewParticipant,
)
from server.app.main import create_app
from server.app.recruiting.models import Application, Candidate, FileObject, Resume
from server.tests.test_recruiting_api import login, seed_user


class Probe:
    async def check(self) -> None:
        pass


def make_app(tmp_path):
    app = create_app(
        settings=Settings(
            environment="test",
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'interview-api.db'}",
            cors_origins=["https://hr.example.test"],
        ),
        database_probe=Probe(),
        storage_probe=Probe(),
        initialize_identity_schema=True,
    )
    app.state.identity_store.create_schema()
    return app


def test_interview_openapi_registers_the_phase_4_contract(tmp_path) -> None:
    app = make_app(tmp_path)
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    expected = {
        "/api/v1/interviews": {"get", "post"},
        "/api/v1/interviews/{interview_id}": {"get", "patch"},
        "/api/v1/interviews/{interview_id}/conflicts": {"post"},
        "/api/v1/interviews/{interview_id}/transitions": {"post"},
        "/api/v1/interviews/{interview_id}/calendar-file": {"get"},
        "/api/v1/interviews/{interview_id}/my-feedback": {"get", "put"},
        "/api/v1/interviews/{interview_id}/my-feedback/submit": {"post"},
        "/api/v1/interview-feedback/{feedback_id}/amendments": {"post"},
        "/api/v1/me/tasks": {"get"},
    }
    assert {path: set(schema["paths"].get(path, {})) for path in expected} == expected


def seed_application(app):
    admin_id = seed_user(app, "recruiting_admin", "interview-admin@example.test")
    interviewer_id = seed_user(app, "interviewer", "assigned@example.test")
    other_interviewer_id = seed_user(app, "interviewer", "unassigned@example.test")
    with app.state.identity_store.sync_session() as database:
        admin = database.get(User, admin_id)
        job = Job(
            organization_id=admin.organization_id,
            title="AI Engineer",
            owner_id=admin_id,
            status="open",
        )
        candidate = Candidate(
            organization_id=admin.organization_id,
            display_name="李嘉明",
            current_title="AI 算法工程师",
            owner_id=admin_id,
        )
        file_object = FileObject(
            organization_id=admin.organization_id,
            storage_key="interviews/resume.pdf",
            original_filename="李嘉明_简历.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            sha256="a" * 64,
            uploaded_by=admin_id,
        )
        database.add_all([job, candidate, file_object])
        database.flush()
        resume = Resume(
            organization_id=admin.organization_id,
            candidate_id=candidate.id,
            file_object_id=file_object.id,
            version_number=1,
            parsed_text="Python RAG Agent",
        )
        database.add(resume)
        database.flush()
        application = Application(
            organization_id=admin.organization_id,
            candidate_id=candidate.id,
            job_id=job.id,
            resume_id=resume.id,
            owner_id=admin_id,
            stage="interview_pending",
        )
        database.add_all(
            [
                application,
                JobCollaborator(
                    organization_id=admin.organization_id,
                    job_id=job.id,
                    user_id=admin_id,
                    access_role="job_owner",
                ),
            ]
        )
        database.commit()
        return {
            "admin_id": admin_id,
            "interviewer_id": interviewer_id,
            "other_interviewer_id": other_interviewer_id,
            "application_id": application.id,
            "candidate_id": candidate.id,
            "job_id": job.id,
        }


def interview_payload(seed, *, starts_at=None):
    start = starts_at or datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    return {
        "application_id": str(seed["application_id"]),
        "round_name": "一面",
        "method": "video",
        "timezone": "Asia/Shanghai",
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(minutes=45)).isoformat(),
        "meeting_url": "https://meeting.example.test/room",
        "participants": [
            {
                "user_id": str(seed["interviewer_id"]),
                "role": "interviewer",
                "required_feedback": True,
            }
        ],
    }


def create_interview(client, seed, *, key="create-interview", payload=None):
    headers = {
        **login(client, "interview-admin@example.test"),
        "Idempotency-Key": key,
    }
    response = client.post("/api/v1/interviews", json=payload or interview_payload(seed), headers=headers)
    assert response.status_code == 201
    return response, headers


def test_create_interview_is_idempotent_checks_conflicts_and_scopes_interviewer_reads(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    payload = interview_payload(seed)
    with TestClient(app) as client:
        created, headers = create_interview(
            client,
            seed,
            key="create-first-interview",
            payload=payload,
        )
        interview = created.json()["data"]
        assert interview["status"] == "scheduled"
        assert interview["notification_status"] == "not_sent"
        assert interview["candidate"]["display_name"] == "李嘉明"
        assert created.headers["ETag"] == '"1"'

        replay = client.post("/api/v1/interviews", json=payload, headers=headers)
        assert replay.status_code == 201
        assert replay.json()["data"]["id"] == interview["id"]

        conflict = client.post(
            "/api/v1/interviews",
            json=payload,
            headers={**headers, "Idempotency-Key": "overlapping-interview"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "schedule_hard_conflict"

        assigned_headers = login(client, "assigned@example.test")
        assigned = client.get(f"/api/v1/interviews/{interview['id']}", headers=assigned_headers)
        assert assigned.status_code == 200
        assert assigned.json()["data"]["candidate"] == {
            "id": str(seed["candidate_id"]),
            "display_name": "李嘉明",
            "current_title": "AI 算法工程师",
        }

        unassigned_headers = login(client, "unassigned@example.test")
        denied = client.get(f"/api/v1/interviews/{interview['id']}", headers=unassigned_headers)
        assert denied.status_code == 404
        assert denied.json()["code"] == "resource_not_found"

    with app.state.identity_store.sync_session() as database:
        application = database.get(Application, seed["application_id"])
        assert application.stage == "interviewing"
        interview_id = UUID(interview["id"])
        assert database.scalar(select(Interview).where(Interview.id == interview_id)) is not None
        assert database.scalar(select(InterviewParticipant).where(InterviewParticipant.interview_id == interview_id)) is not None


def test_revoked_recruiting_role_removes_historical_assignment_access(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    with TestClient(app) as client:
        created, _ = create_interview(client, seed, key="role-revocation-create")
        interview_id = created.json()["data"]["id"]

    with app.state.identity_store.sync_session() as database:
        database.execute(delete(UserRole).where(UserRole.user_id == seed["interviewer_id"]))
        database.add(UserRole(user_id=seed["interviewer_id"], role="system_admin"))
        database.commit()

    with TestClient(app) as client:
        headers = login(client, "assigned@example.test")
        assert client.get(f"/api/v1/interviews/{interview_id}", headers=headers).status_code == 404
        assert client.get(f"/api/v1/interviews/{interview_id}/calendar-file", headers=headers).status_code == 404
        assert client.get(f"/api/v1/interviews/{interview_id}/my-feedback", headers=headers).status_code == 404
        assert client.put(
            f"/api/v1/interviews/{interview_id}/my-feedback",
            json=feedback_payload(),
            headers={**headers, "If-Match": '"0"'},
        ).status_code == 404
        assert client.get("/api/v1/interviews", headers=headers).json() == {"data": [], "meta": {"count": 0}}
        assert client.get("/api/v1/me/tasks", headers=headers).json() == {"data": [], "meta": {"count": 0}}


def test_create_rejects_same_candidate_overlap_with_different_interviewer(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    start = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    with TestClient(app) as client:
        create_interview(client, seed, key="candidate-conflict-first", payload=interview_payload(seed, starts_at=start))
        overlapping = interview_payload(seed, starts_at=start)
        overlapping["participants"] = [
            {
                "user_id": str(seed["other_interviewer_id"]),
                "role": "interviewer",
                "required_feedback": True,
            }
        ]
        response = client.post(
            "/api/v1/interviews",
            json=overlapping,
            headers={
                **login(client, "interview-admin@example.test"),
                "Idempotency-Key": "candidate-conflict-second",
            },
        )

    assert response.status_code == 409
    assert response.json()["code"] == "schedule_hard_conflict"


def test_reschedule_rejects_same_candidate_overlap_with_different_interviewer(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    first_start = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    second_start = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    second_payload = interview_payload(seed, starts_at=second_start)
    second_payload["participants"] = [
        {
            "user_id": str(seed["other_interviewer_id"]),
            "role": "interviewer",
            "required_feedback": True,
        }
    ]
    with TestClient(app) as client:
        create_interview(client, seed, key="candidate-reschedule-first", payload=interview_payload(seed, starts_at=first_start))
        second, admin_headers = create_interview(
            client,
            seed,
            key="candidate-reschedule-second",
            payload=second_payload,
        )
        response = client.patch(
            f"/api/v1/interviews/{second.json()['data']['id']}",
            json={
                "starts_at": first_start.isoformat(),
                "ends_at": (first_start + timedelta(minutes=45)).isoformat(),
            },
            headers={**admin_headers, "If-Match": '"1"'},
        )

    assert response.status_code == 409
    assert response.json()["code"] == "schedule_hard_conflict"


def test_reschedule_preserves_history_and_transition_calendar_versions(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    with TestClient(app) as client:
        created, headers = create_interview(client, seed)
        interview = created.json()["data"]
        interview_id = interview["id"]
        new_start = datetime(2026, 7, 21, 9, 30, tzinfo=timezone.utc)

        stale = client.patch(
            f"/api/v1/interviews/{interview_id}",
            json={"starts_at": new_start.isoformat(), "ends_at": (new_start + timedelta(minutes=60)).isoformat()},
            headers={**headers, "If-Match": '"9"'},
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "resource_version_conflict"

        rescheduled = client.patch(
            f"/api/v1/interviews/{interview_id}",
            json={"starts_at": new_start.isoformat(), "ends_at": (new_start + timedelta(minutes=60)).isoformat()},
            headers={**headers, "If-Match": '"1"'},
        )
        assert rescheduled.status_code == 200
        assert rescheduled.json()["data"]["status"] == "rescheduled"
        assert rescheduled.json()["data"]["version"] == 2
        assert rescheduled.json()["data"]["calendar_sequence"] == 1

        calendar = client.get(f"/api/v1/interviews/{interview_id}/calendar-file", headers=headers)
        assert calendar.status_code == 200
        assert calendar.headers["content-type"].startswith("text/calendar")
        assert b"SEQUENCE:1\r\n" in calendar.content
        assert b"DTSTART:20260721T093000Z\r\n" in calendar.content
        assert b"mailto:interview-admin@example.test\r\n" in calendar.content
        assert b"mailto:assigned@example.test\r\n" in calendar.content

        confirmed = client.post(
            f"/api/v1/interviews/{interview_id}/transitions",
            json={"target": "confirmed"},
            headers={**headers, "If-Match": '"2"', "Idempotency-Key": "confirm-interview"},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["data"]["status"] == "confirmed"
        assert confirmed.json()["data"]["version"] == 3

        completed = client.post(
            f"/api/v1/interviews/{interview_id}/transitions",
            json={"target": "completed"},
            headers={**headers, "If-Match": '"3"', "Idempotency-Key": "complete-interview"},
        )
        assert completed.status_code == 200
        assert completed.json()["data"]["status"] == "pending_feedback"

    with app.state.identity_store.sync_session() as database:
        events = database.scalars(
            select(InterviewEvent)
            .where(InterviewEvent.interview_id == UUID(interview_id))
            .order_by(InterviewEvent.created_at)
        ).all()
        reschedule_event = next(item for item in events if item.event_type == "interview.rescheduled")
        assert reschedule_event.payload["previous"]["starts_at"] == interview["starts_at"]
        assert reschedule_event.payload["current"]["starts_at"] == new_start.isoformat()


def test_calendar_cancel_reuses_persisted_request_contacts_after_user_changes(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    with TestClient(app) as client:
        created, admin_headers = create_interview(client, seed, key="calendar-contact-create")
        interview_id = created.json()["data"]["id"]
        invitation = client.get(f"/api/v1/interviews/{interview_id}/calendar-file", headers=admin_headers)
        assert invitation.status_code == 200

        with app.state.identity_store.sync_session() as database:
            admin = database.get(User, seed["admin_id"])
            admin.email = "renamed-admin@example.test"
            admin.normalized_email = admin.email
            admin.display_name = "Renamed recruiter"
            interviewer = database.get(User, seed["interviewer_id"])
            interviewer.email = "renamed-interviewer@example.test"
            interviewer.normalized_email = interviewer.email
            interviewer.display_name = "Renamed interviewer"
            database.commit()

        cancelled = client.post(
            f"/api/v1/interviews/{interview_id}/transitions",
            json={"target": "cancelled", "reason": "Role closed"},
            headers={**admin_headers, "If-Match": '"1"', "Idempotency-Key": "calendar-contact-cancel"},
        )
        assert cancelled.status_code == 200
        cancellation = client.get(f"/api/v1/interviews/{interview_id}/calendar-file", headers=admin_headers)
        assert cancellation.status_code == 200

    def contacts(payload):
        return {
            line
            for line in payload.content.decode("utf-8").split("\r\n")
            if line.startswith(("ORGANIZER", "ATTENDEE"))
        }

    assert contacts(invitation) == contacts(cancellation)
    assert b"METHOD:REQUEST\r\n" in invitation.content
    assert b"METHOD:CANCEL\r\n" in cancellation.content


def feedback_payload(conclusion="recommend"):
    return {
        "ratings": {
            "professional_ability": 4,
            "problem_solving": 3,
            "communication": 4,
            "role_fit": 4,
        },
        "strengths": "RAG 与 Agent 项目经验完整",
        "risks": "大规模推理成本经验需要确认",
        "conclusion": conclusion,
        "notes": "建议进入下一轮",
    }


def test_application_waits_for_all_active_interview_rounds_before_decision(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    with TestClient(app) as client:
        first, admin_headers = create_interview(
            client,
            seed,
            key="decision-gate-first",
            payload=interview_payload(
                seed,
                starts_at=datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc),
            ),
        )
        second, _ = create_interview(
            client,
            seed,
            key="decision-gate-second",
            payload=interview_payload(
                seed,
                starts_at=datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc),
            ),
        )
        first_id = first.json()["data"]["id"]
        second_id = second.json()["data"]["id"]
        admin_headers = login(client, "interview-admin@example.test")
        assert client.post(
            f"/api/v1/interviews/{first_id}/transitions",
            json={"target": "confirmed"},
            headers={**admin_headers, "If-Match": '"1"', "Idempotency-Key": "decision-gate-confirm"},
        ).status_code == 200
        assert client.post(
            f"/api/v1/interviews/{first_id}/transitions",
            json={"target": "completed"},
            headers={**admin_headers, "If-Match": '"2"', "Idempotency-Key": "decision-gate-complete"},
        ).status_code == 200
        interviewer_headers = login(client, "assigned@example.test")
        assert client.put(
            f"/api/v1/interviews/{first_id}/my-feedback",
            json=feedback_payload(),
            headers={**interviewer_headers, "If-Match": '"0"'},
        ).status_code == 200
        assert client.post(
            f"/api/v1/interviews/{first_id}/my-feedback/submit",
            headers={**interviewer_headers, "Idempotency-Key": "decision-gate-submit"},
        ).status_code == 200

        with app.state.identity_store.sync_session() as database:
            assert database.get(Application, seed["application_id"]).stage == "interviewing"

        admin_headers = login(client, "interview-admin@example.test")
        cancelled = client.post(
            f"/api/v1/interviews/{second_id}/transitions",
            json={"target": "cancelled", "reason": "Second round no longer required"},
            headers={**admin_headers, "If-Match": '"1"', "Idempotency-Key": "decision-gate-cancel"},
        )
        assert cancelled.status_code == 200

    with app.state.identity_store.sync_session() as database:
        assert database.get(Application, seed["application_id"]).stage == "decision"


def test_interview_without_required_feedback_advances_application_on_completion(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    payload = interview_payload(seed)
    payload["participants"][0]["required_feedback"] = False
    with TestClient(app) as client:
        created, admin_headers = create_interview(client, seed, key="zero-feedback-create", payload=payload)
        interview_id = created.json()["data"]["id"]
        assert client.post(
            f"/api/v1/interviews/{interview_id}/transitions",
            json={"target": "confirmed"},
            headers={**admin_headers, "If-Match": '"1"', "Idempotency-Key": "zero-feedback-confirm"},
        ).status_code == 200
        completed = client.post(
            f"/api/v1/interviews/{interview_id}/transitions",
            json={"target": "completed"},
            headers={**admin_headers, "If-Match": '"2"', "Idempotency-Key": "zero-feedback-complete"},
        )
        assert completed.status_code == 200
        assert completed.json()["data"]["status"] == "feedback_completed"

    with app.state.identity_store.sync_session() as database:
        assert database.get(Application, seed["application_id"]).stage == "decision"


def test_feedback_is_private_idempotent_and_advances_only_after_all_required_submit(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    payload = interview_payload(seed)
    payload["participants"].append(
        {
            "user_id": str(seed["other_interviewer_id"]),
            "role": "interviewer",
            "required_feedback": True,
        }
    )
    with TestClient(app) as client:
        created, admin_headers = create_interview(client, seed, payload=payload)
        interview = created.json()["data"]
        interview_id = interview["id"]
        confirmed = client.post(
            f"/api/v1/interviews/{interview_id}/transitions",
            json={"target": "confirmed"},
            headers={**admin_headers, "If-Match": '"1"', "Idempotency-Key": "feedback-confirm"},
        )
        assert confirmed.status_code == 200
        completed = client.post(
            f"/api/v1/interviews/{interview_id}/transitions",
            json={"target": "completed"},
            headers={**admin_headers, "If-Match": '"2"', "Idempotency-Key": "feedback-complete"},
        )
        assert completed.status_code == 200
        assert completed.json()["data"]["status"] == "pending_feedback"

        first_headers = login(client, "assigned@example.test")
        empty = client.get(f"/api/v1/interviews/{interview_id}/my-feedback", headers=first_headers)
        assert empty.status_code == 200
        assert empty.json()["data"] == {"status": "draft", "version": 0}

        saved = client.put(
            f"/api/v1/interviews/{interview_id}/my-feedback",
            json=feedback_payload(),
            headers={**first_headers, "If-Match": '"0"'},
        )
        assert saved.status_code == 200
        assert saved.json()["data"]["status"] == "draft"
        assert saved.headers["ETag"] == '"1"'

        submit_headers = {**first_headers, "Idempotency-Key": "first-feedback-submit"}
        submitted = client.post(
            f"/api/v1/interviews/{interview_id}/my-feedback/submit",
            headers=submit_headers,
        )
        assert submitted.status_code == 200
        assert submitted.json()["data"]["status"] == "submitted"
        replay = client.post(
            f"/api/v1/interviews/{interview_id}/my-feedback/submit",
            headers=submit_headers,
        )
        assert replay.status_code == 200
        assert replay.json()["data"]["id"] == submitted.json()["data"]["id"]

        second_headers = login(client, "unassigned@example.test")
        second_saved = client.put(
            f"/api/v1/interviews/{interview_id}/my-feedback",
            json=feedback_payload("strong_recommend"),
            headers={**second_headers, "If-Match": '"0"'},
        )
        assert second_saved.status_code == 200
        second_submitted = client.post(
            f"/api/v1/interviews/{interview_id}/my-feedback/submit",
            headers={**second_headers, "Idempotency-Key": "second-feedback-submit"},
        )
        assert second_submitted.status_code == 200

    with app.state.identity_store.sync_session() as database:
        application = database.get(Application, seed["application_id"])
        stored_interview = database.get(Interview, UUID(interview_id))
        feedbacks = database.scalars(
            select(InterviewFeedback).where(InterviewFeedback.interview_id == UUID(interview_id))
        ).all()
        assert application.stage == "decision"
        assert stored_interview.status == "feedback_completed"
        assert len(feedbacks) == 2
        assert all(item.status == "submitted" for item in feedbacks)


def test_submitted_feedback_amendment_requires_its_author_reason_and_version(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    with TestClient(app) as client:
        created, admin_headers = create_interview(client, seed)
        interview_id = created.json()["data"]["id"]
        assert client.post(
            f"/api/v1/interviews/{interview_id}/transitions",
            json={"target": "confirmed"},
            headers={**admin_headers, "If-Match": '"1"', "Idempotency-Key": "amend-confirm"},
        ).status_code == 200
        assert client.post(
            f"/api/v1/interviews/{interview_id}/transitions",
            json={"target": "completed"},
            headers={**admin_headers, "If-Match": '"2"', "Idempotency-Key": "amend-complete"},
        ).status_code == 200

        author_headers = login(client, "assigned@example.test")
        saved = client.put(
            f"/api/v1/interviews/{interview_id}/my-feedback",
            json=feedback_payload(),
            headers={**author_headers, "If-Match": '"0"'},
        )
        submitted = client.post(
            f"/api/v1/interviews/{interview_id}/my-feedback/submit",
            headers={**author_headers, "Idempotency-Key": "amend-submit"},
        )
        feedback = submitted.json()["data"]
        assert feedback["version"] == 2

        outsider_headers = login(client, "unassigned@example.test")
        denied = client.post(
            f"/api/v1/interview-feedback/{feedback['id']}/amendments",
            json={**feedback_payload(), "reason": "Not my feedback"},
            headers={**outsider_headers, "If-Match": '"2"'},
        )
        assert denied.status_code == 404

        author_headers = login(client, "assigned@example.test")
        amendment_payload = {
            **feedback_payload("strong_recommend"),
            "notes": "补充核实了线上吞吐数据",
            "reason": "候选人补充了量化证据",
        }
        amended = client.post(
            f"/api/v1/interview-feedback/{feedback['id']}/amendments",
            json=amendment_payload,
            headers={**author_headers, "If-Match": '"2"'},
        )
        assert amended.status_code == 200
        assert amended.json()["data"]["status"] == "amended"
        assert amended.json()["data"]["version"] == 3
        assert amended.headers["ETag"] == '"3"'

        stale = client.post(
            f"/api/v1/interview-feedback/{feedback['id']}/amendments",
            json=amendment_payload,
            headers={**author_headers, "If-Match": '"2"'},
        )
        assert stale.status_code == 409

    with app.state.identity_store.sync_session() as database:
        revision = database.scalar(
            select(InterviewFeedbackRevision).where(
                InterviewFeedbackRevision.feedback_id == UUID(feedback["id"])
            )
        )
        assert revision.reason == "候选人补充了量化证据"
        assert revision.previous_payload["notes"] == "建议进入下一轮"
        assert revision.new_payload["notes"] == "补充核实了线上吞吐数据"


def test_interview_list_conflicts_and_my_tasks_share_assignment_scope(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    first_start = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    second_start = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    with TestClient(app) as client:
        first, admin_headers = create_interview(
            client,
            seed,
            key="scope-first",
            payload=interview_payload(seed, starts_at=first_start),
        )
        second, admin_headers = create_interview(
            client,
            seed,
            key="scope-second",
            payload=interview_payload(seed, starts_at=second_start),
        )
        first_id = first.json()["data"]["id"]
        second_id = second.json()["data"]["id"]

        conflict = client.post(
            f"/api/v1/interviews/{first_id}/conflicts",
            json={
                "starts_at": second_start.isoformat(),
                "ends_at": (second_start + timedelta(minutes=30)).isoformat(),
                "participant_ids": [str(seed["interviewer_id"])],
                "buffer_minutes": 15,
            },
            headers=admin_headers,
        )
        assert conflict.status_code == 200
        assert conflict.json()["data"] == {"hard": [second_id], "soft": []}

        admin_list = client.get("/api/v1/interviews", headers=admin_headers)
        assert admin_list.status_code == 200
        assert admin_list.json()["meta"]["count"] == 2

        assigned_headers = login(client, "assigned@example.test")
        assigned_list = client.get("/api/v1/interviews", headers=assigned_headers)
        assert assigned_list.status_code == 200
        assert assigned_list.json()["meta"]["count"] == 2

        outsider_headers = login(client, "unassigned@example.test")
        outsider_list = client.get("/api/v1/interviews", headers=outsider_headers)
        assert outsider_list.status_code == 200
        assert outsider_list.json() == {"data": [], "meta": {"count": 0}}

        admin_headers = login(client, "interview-admin@example.test")
        assert client.post(
            f"/api/v1/interviews/{first_id}/transitions",
            json={"target": "confirmed"},
            headers={**admin_headers, "If-Match": '"1"', "Idempotency-Key": "scope-confirm"},
        ).status_code == 200
        assert client.post(
            f"/api/v1/interviews/{first_id}/transitions",
            json={"target": "completed"},
            headers={**admin_headers, "If-Match": '"2"', "Idempotency-Key": "scope-complete"},
        ).status_code == 200

        assigned_headers = login(client, "assigned@example.test")
        tasks = client.get("/api/v1/me/tasks", headers=assigned_headers)
        assert tasks.status_code == 200
        feedback_task = next(item for item in tasks.json()["data"] if item["type"] == "interview_feedback")
        assert feedback_task["interview_id"] == first_id
        assert feedback_task["candidate"]["display_name"] == "李嘉明"
