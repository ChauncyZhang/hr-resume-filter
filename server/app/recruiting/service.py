import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select


class InvalidStateTransition(Exception): pass
class ResourceVersionConflict(Exception): pass
class IdempotencyConflict(Exception): pass
class ActiveApplicationExists(Exception): pass
class TicketInvalid(Exception): pass


class SystemClock:
    def current_time(self):
        return datetime.now(timezone.utc)


class SystemTokens:
    def new_token(self):
        return secrets.token_urlsafe(32)


class RecruitingService:
    JOB_EDGES = {"draft": {"open"}, "open": {"paused", "closed"}, "paused": {"open", "closed"}, "closed": {"archived"}, "archived": set()}
    APPLICATION_PATH = ["new", "review", "contact", "interview_pending", "interviewing", "decision", "passed", "hired"]
    TERMINAL = {"hired", "rejected", "withdrawn"}

    def __init__(self, clock=None, tokens=None):
        self.clock = clock or SystemClock()
        self.tokens = tokens or SystemTokens()
        self.idempotency = {}
        self.applications = {}
        self.download_tickets = {}

    def transition_job_state(self, source, target):
        if target not in self.JOB_EDGES.get(source, set()):
            raise InvalidStateTransition
        return target

    def transition_application_state(self, source, target, *, reason_code=None, reason_text=None):
        allowed = set()
        if source not in self.TERMINAL and source in self.APPLICATION_PATH:
            index = self.APPLICATION_PATH.index(source)
            if index + 1 < len(self.APPLICATION_PATH):
                allowed.add(self.APPLICATION_PATH[index + 1])
            allowed.update({"rejected", "withdrawn"})
        if target not in allowed or (target == "rejected" and not (reason_code or (reason_text and reason_text.strip()))):
            raise InvalidStateTransition
        return target

    def require_version(self, if_match, current):
        if if_match != f'"{current}"':
            raise ResourceVersionConflict
        return current

    def idempotent(self, organization_id, user_id, operation, key, body, action: Callable):
        identity = (organization_id, user_id, operation, key)
        fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        previous = self.idempotency.get(identity)
        if previous:
            if previous[0] != fingerprint:
                raise IdempotencyConflict
            return previous[1]
        result = action()
        self.idempotency[identity] = (fingerprint, result)
        return result

    def create_application(self, organization_id, candidate_id, job_id, resume_id, owner_id, idempotency_key):
        def create():
            related = [a for a in self.applications.values() if a["organization_id"] == organization_id and a["candidate_id"] == candidate_id and a["job_id"] == job_id]
            if any(a["stage"] not in self.TERMINAL for a in related):
                raise ActiveApplicationExists
            source = related[-1]["id"] if related else None
            record = {"id": str(uuid.uuid4()), "organization_id": organization_id, "candidate_id": candidate_id, "job_id": job_id, "resume_id": resume_id, "owner_id": owner_id, "stage": "new", "version": 1, "source_application_id": source}
            self.applications[record["id"]] = record
            return record
        return self.idempotent(organization_id, owner_id, "application.create", idempotency_key, {"candidate_id": candidate_id, "job_id": job_id, "resume_id": resume_id}, create)

    def issue_download_ticket(self, organization_id, user_id, resume_id):
        raw = self.tokens.new_token()
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        self.download_tickets[token_hash] = {"organization_id": organization_id, "user_id": user_id, "resume_id": resume_id, "expires_at": self.clock.current_time() + timedelta(seconds=60), "consumed_at": None}
        return raw

    def consume_download_ticket(self, raw, organization_id, user_id, resume_id):
        stored = self.download_tickets.get(hashlib.sha256(raw.encode()).hexdigest())
        if not stored or stored["consumed_at"] or stored["expires_at"] <= self.clock.current_time() or any(stored[key] != value for key, value in (("organization_id", organization_id), ("user_id", user_id), ("resume_id", resume_id))):
            raise TicketInvalid
        stored["consumed_at"] = self.clock.current_time()
        return stored


def transition_application(db, application, target, *, actor_user_id, trace_id, reason_code=None, reason_text=None):
    from server.app.identity.models import AuditLog
    from server.app.recruiting.models import ApplicationStageEvent

    source = application.stage
    RecruitingService().transition_application_state(source, target, reason_code=reason_code, reason_text=reason_text)
    application.stage = target
    application.version += 1
    application.updated_at = datetime.now(timezone.utc)
    safe_payload = {"from_stage": source, "to_stage": target}
    if reason_code:
        safe_payload["reason_code"] = reason_code
    db.add(ApplicationStageEvent(organization_id=application.organization_id, application_id=application.id, actor_user_id=actor_user_id, event_type="application.stage_changed", payload=safe_payload))
    db.add(AuditLog(organization_id=application.organization_id, actor_user_id=actor_user_id, event_type="application.stage_changed", outcome="success", trace_id=trace_id, metadata_json=safe_payload))
    db.flush()
    return application


def create_application_record(db, *, organization_id, candidate_id, job_id, resume_id, owner_id, source="manual"):
    from server.app.recruiting.models import Application

    related = list(db.scalars(select(Application).where(Application.organization_id == organization_id, Application.candidate_id == candidate_id, Application.job_id == job_id).order_by(Application.created_at.desc())))
    if any(item.stage not in RecruitingService.TERMINAL for item in related):
        raise ActiveApplicationExists
    application = Application(organization_id=organization_id, candidate_id=candidate_id, job_id=job_id, resume_id=resume_id, owner_id=owner_id, source=source, stage="new", source_application_id=related[0].id if related else None)
    db.add(application)
    db.flush()
    return application


def issue_download_ticket_record(db, organization_id, user_id, resume_id, clock, tokens):
    from server.app.recruiting.models import DownloadTicket

    raw = tokens.new_token()
    db.add(DownloadTicket(organization_id=organization_id, user_id=user_id, resume_id=resume_id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=clock.current_time() + timedelta(seconds=60)))
    db.flush()
    return raw


def consume_download_ticket_record(db, raw, organization_id, user_id, resume_id, clock):
    from server.app.recruiting.models import DownloadTicket

    ticket = db.scalar(select(DownloadTicket).where(DownloadTicket.token_hash == hashlib.sha256(raw.encode()).hexdigest()).with_for_update())
    if ticket is None or ticket.consumed_at is not None or ticket.expires_at.replace(tzinfo=ticket.expires_at.tzinfo or timezone.utc) <= clock.current_time() or ticket.organization_id != organization_id or ticket.user_id != user_id or ticket.resume_id != resume_id:
        raise TicketInvalid
    ticket.consumed_at = clock.current_time()
    db.flush()
    return ticket


def persisted_idempotent(db, organization_id, user_id, operation, key, body, action):
    from server.app.recruiting.models import IdempotencyRecord

    request_hash = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    record = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.organization_id == organization_id, IdempotencyRecord.user_id == user_id, IdempotencyRecord.operation == operation, IdempotencyRecord.idempotency_key == key).with_for_update())
    if record:
        if record.request_hash != request_hash:
            raise IdempotencyConflict
        return record.status_code, record.response_json
    status_code, response = action()
    db.add(IdempotencyRecord(organization_id=organization_id, user_id=user_id, operation=operation, idempotency_key=key, request_hash=request_hash, status_code=status_code, response_json=response))
    db.flush()
    return status_code, response
