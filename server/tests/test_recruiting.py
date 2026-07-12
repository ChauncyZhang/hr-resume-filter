from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from server.app.identity.models import AuditLog, Base
from server.app.recruiting.cursor import CursorCodec, InvalidCursor
from server.app.recruiting.models import Application, ApplicationStageEvent, Candidate
from server.app.recruiting.security import ContactCipher
from server.app.recruiting.service import (
    ActiveApplicationExists,
    IdempotencyConflict,
    InvalidStateTransition,
    RecruitingService,
    ResourceVersionConflict,
    TicketInvalid,
    transition_application,
    consume_download_ticket_record,
    create_application_record,
    issue_download_ticket_record,
    persisted_idempotent,
)


class FixedClock:
    def __init__(self):
        self.now = datetime(2026, 7, 12, tzinfo=timezone.utc)

    def current_time(self):
        return self.now


class Tokens:
    def __init__(self):
        self.values = iter(["ticket-one", "ticket-two"])

    def new_token(self):
        return next(self.values)


def service():
    clock = FixedClock()
    return RecruitingService(clock=clock, tokens=Tokens()), clock


def test_job_state_machine_accepts_every_legal_edge_and_rejects_illegal_adjacency():
    svc, _ = service()
    legal = {
        "draft": {"open"},
        "open": {"paused", "closed"},
        "paused": {"open", "closed"},
        "closed": {"archived"},
        "archived": set(),
    }
    for source, targets in legal.items():
        for target in targets:
            assert svc.transition_job_state(source, target) == target
        illegal = set(legal) - targets - {source}
        for target in illegal:
            with pytest.raises(InvalidStateTransition):
                svc.transition_job_state(source, target)


def test_application_state_machine_terminal_rules_and_rejection_reason():
    svc, _ = service()
    normal = ["new", "review", "contact", "interview_pending", "interviewing", "decision", "passed", "hired"]
    for source, target in zip(normal, normal[1:]):
        assert svc.transition_application_state(source, target) == target
    for source in normal[:-1]:
        assert svc.transition_application_state(source, "withdrawn") == "withdrawn"
        assert svc.transition_application_state(source, "rejected", reason_code="skills") == "rejected"
    with pytest.raises(InvalidStateTransition):
        svc.transition_application_state("new", "rejected")
    for terminal in ("hired", "rejected", "withdrawn"):
        with pytest.raises(InvalidStateTransition):
            svc.transition_application_state(terminal, "new")


def test_contact_encryption_normalization_masking_and_duplicate_hash():
    cipher = ContactCipher(b"0123456789abcdef0123456789abcdef", b"lookup-secret-not-placeholder")
    first = cipher.protect(" Email ", " Alice.Example@Example.COM ")
    second = cipher.protect("email", "alice.example@example.com")
    assert first.ciphertext != b"Alice.Example@Example.COM"
    assert cipher.decrypt(first.ciphertext) == "Alice.Example@Example.COM"
    assert first.lookup_hash == second.lookup_hash
    assert first.masked_value == "a***@example.com"
    rendered = repr(first)
    assert "Alice.Example" not in rendered and "alice.example" not in rendered


def test_optimistic_concurrency_and_idempotency_contracts():
    svc, _ = service()
    assert svc.require_version('"3"', 3) == 3
    with pytest.raises(ResourceVersionConflict):
        svc.require_version('"2"', 3)
    first = svc.idempotent("org", "user", "create", "key", {"job_id": "j"}, lambda: {"id": "a"})
    replay = svc.idempotent("org", "user", "create", "key", {"job_id": "j"}, lambda: {"id": "other"})
    assert replay == first
    with pytest.raises(IdempotencyConflict):
        svc.idempotent("org", "user", "create", "key", {"job_id": "different"}, lambda: {})


def test_active_duplicate_and_terminal_reapplication_link():
    svc, _ = service()
    original = svc.create_application("org", "candidate", "job", "resume", "owner", "key-1")
    with pytest.raises(ActiveApplicationExists):
        svc.create_application("org", "candidate", "job", "resume", "owner", "key-2")
    svc.applications[original["id"]]["stage"] = "rejected"
    later = svc.create_application("org", "candidate", "job", "resume", "owner", "key-3")
    assert later["source_application_id"] == original["id"]


def test_download_ticket_is_hashed_bound_short_lived_and_single_use():
    svc, clock = service()
    raw = svc.issue_download_ticket("org", "user", "resume")
    stored = next(iter(svc.download_tickets.values()))
    assert raw not in repr(stored)
    assert svc.consume_download_ticket(raw, "org", "user", "resume")["resume_id"] == "resume"
    with pytest.raises(TicketInvalid):
        svc.consume_download_ticket(raw, "org", "user", "resume")
    raw = svc.issue_download_ticket("org", "user", "resume")
    clock.now += timedelta(seconds=61)
    with pytest.raises(TicketInvalid):
        svc.consume_download_ticket(raw, "org", "user", "resume")


def test_candidate_schema_has_no_job_or_stage_and_all_recruiting_tables_are_mapped():
    assert {"job_id", "stage"}.isdisjoint(Candidate.__table__.columns.keys())
    required = {"job_jd_versions", "screening_rule_versions", "candidates", "candidate_contacts", "file_objects", "resumes", "applications", "application_stage_events", "candidate_notes", "candidate_events", "download_tickets", "idempotency_records"}
    assert required <= set(Base.metadata.tables)


def test_cursor_is_opaque_tenant_and_sort_bound_and_rejects_tampering():
    codec = CursorCodec(b"cursor-signing-secret")
    token = codec.encode("org-a", "-updated_at", "2026-07-12T00:00:00Z", "candidate-id")
    assert "candidate-id" not in token
    assert codec.decode(token, "org-a", "-updated_at")["id"] == "candidate-id"
    for organization, sort, cursor in (("org-b", "-updated_at", token), ("org-a", "name", token), ("org-a", "-updated_at", token[:-1] + "x")):
        with pytest.raises(InvalidCursor):
            codec.decode(cursor, organization, sort)


def test_persisted_transition_increments_version_and_writes_timeline_and_audit_atomically():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        application = Application(organization_id=UUID(int=1), candidate_id=UUID(int=2), job_id=UUID(int=3), resume_id=UUID(int=4), owner_id=UUID(int=5), stage="new", source="manual")
        db.add(application)
        db.flush()
        transition_application(db, application, "review", actor_user_id=application.owner_id, trace_id="trace")
        db.commit()
        assert application.stage == "review" and application.version == 2
        assert db.query(ApplicationStageEvent).count() == 1
        assert db.query(Base.metadata.tables["audit_logs"]).count() == 1


def test_transition_rolls_back_aggregate_and_timeline_when_audit_insert_fails():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        application = Application(organization_id=UUID(int=1), candidate_id=UUID(int=2), job_id=UUID(int=3), resume_id=UUID(int=4), owner_id=UUID(int=5), stage="new", source="manual")
        db.add(application)
        db.commit()

        def reject_audit(*_):
            raise RuntimeError("injected audit failure")

        event.listen(AuditLog, "before_insert", reject_audit)
        try:
            with pytest.raises(RuntimeError, match="injected audit failure"):
                transition_application(db, application, "review", actor_user_id=application.owner_id, trace_id="trace")
            db.rollback()
        finally:
            event.remove(AuditLog, "before_insert", reject_audit)
        assert db.get(Application, application.id).stage == "new"
        assert db.query(ApplicationStageEvent).count() == 0


def test_persisted_application_duplicate_and_linked_reapplication():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        args = dict(organization_id=UUID(int=1), candidate_id=UUID(int=2), job_id=UUID(int=3), resume_id=UUID(int=4), owner_id=UUID(int=5))
        first = create_application_record(db, **args)
        db.commit()
        with pytest.raises(ActiveApplicationExists):
            create_application_record(db, **args)
        first.stage = "rejected"
        db.commit()
        later = create_application_record(db, **args)
        assert later.source_application_id == first.id


def test_persisted_ticket_never_stores_raw_value_and_is_bound_single_use():
    svc, clock = service()
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        raw = issue_download_ticket_record(db, UUID(int=1), UUID(int=2), UUID(int=3), clock, svc.tokens)
        db.commit()
        assert raw not in repr(db.query(Base.metadata.tables["download_tickets"]).first())
        consume_download_ticket_record(db, raw, UUID(int=1), UUID(int=2), UUID(int=3), clock)
        db.commit()
        with pytest.raises(TicketInvalid):
            consume_download_ticket_record(db, raw, UUID(int=1), UUID(int=2), UUID(int=3), clock)


def test_persisted_idempotency_replays_and_rejects_same_key_different_body():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    calls = []
    with Session(engine) as db:
        args = (UUID(int=1), UUID(int=2), "application.create", "stable-key")
        first = persisted_idempotent(db, *args, {"candidate_id": "one"}, lambda: calls.append(1) or (201, {"id": "application"}))
        db.commit()
        replay = persisted_idempotent(db, *args, {"candidate_id": "one"}, lambda: calls.append(2) or (500, {}))
        assert first == replay == (201, {"id": "application"}) and calls == [1]
        with pytest.raises(IdempotencyConflict):
            persisted_idempotent(db, *args, {"candidate_id": "two"}, lambda: (201, {}))
