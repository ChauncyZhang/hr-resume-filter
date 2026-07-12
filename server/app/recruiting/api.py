import hashlib
import re
from collections import Counter
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import and_, exists, func, or_, select

from server.app.identity.api import problem, session_token
from server.app.identity.models import AuditLog, Job, JobCollaborator
from server.app.identity.policy import Permission, Principal
from server.app.identity.service import InvalidSession
from server.app.recruiting.cursor import CursorCodec, InvalidCursor
from server.app.recruiting.models import (
    Application, Candidate, CandidateContact, CandidateEvent, CandidateNote,
    DownloadTicket, JobJdVersion, Resume, ScreeningRuleVersion,
)
from server.app.recruiting.security import ContactCipher
from server.app.recruiting.service import (
    ActiveApplicationExists, IdempotencyConflict, InvalidAggregateRelationship,
    InvalidStateTransition, ResourceVersionConflict, SystemClock, SystemTokens,
    TicketInvalid, consume_download_ticket_record, create_application_record,
    issue_download_ticket_record, persisted_idempotent, transition_application_record,
    transition_job_record,
)


router = APIRouter(prefix="/api/v1")
ETAG = re.compile(r'^"([1-9][0-9]*)"$')


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JobCreate(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    department_id: UUID | None = None
    headcount: int = Field(default=1, gt=0)
    priority: str = Field(default="normal", max_length=16)
    hiring_owner_id: UUID | None = None


class JobPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    headcount: int | None = Field(default=None, gt=0)
    priority: str | None = Field(default=None, max_length=16)
    hiring_owner_id: UUID | None = None


class Transition(StrictModel):
    target: str = Field(min_length=1, max_length=32)
    reason_code: str | None = Field(default=None, max_length=64)
    reason_text: str | None = Field(default=None, max_length=1000)


class VersionCreate(StrictModel):
    content: dict[str, Any]


class ContactInput(StrictModel):
    kind: str
    value: str = Field(min_length=1, max_length=320)


class CandidateCreate(StrictModel):
    display_name: str = Field(min_length=1, max_length=200)
    current_title: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    owner_id: UUID | None = None
    contacts: list[ContactInput] = Field(default_factory=list, max_length=10)


class CandidatePatch(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    current_title: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    owner_id: UUID | None = None


class NoteCreate(StrictModel):
    body: str = Field(min_length=1, max_length=4000)

    @field_validator("body")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("note must not be blank")
        return value.strip()


class ApplicationCreate(StrictModel):
    candidate_id: UUID
    resume_id: UUID
    owner_id: UUID | None = None
    source: str = Field(default="manual", min_length=1, max_length=64)


class ApplicationPatch(StrictModel):
    owner_id: UUID | None = None
    human_conclusion: str | None = Field(default=None, max_length=4000)


class TicketConsume(StrictModel):
    token: str = Field(min_length=20, max_length=512)


def _principal(request: Request) -> Principal | JSONResponse:
    token = session_token(request)
    if not token:
        return problem(request, 401, "authentication_required", "Authentication is required.")
    try:
        return request.app.state.identity_service.principal(token)
    except InvalidSession:
        return problem(request, 401, "authentication_required", "Authentication is required.")


def _denied(request: Request) -> JSONResponse:
    return problem(request, 404, "resource_not_found", "The requested resource is unavailable.")


def _problem_for(request: Request, error: Exception) -> JSONResponse:
    mapping = {
        ResourceVersionConflict: (409, "resource_version_conflict"),
        InvalidStateTransition: (409, "invalid_state_transition"),
        IdempotencyConflict: (409, "idempotency_conflict"),
        ActiveApplicationExists: (409, "active_application_exists"),
        InvalidAggregateRelationship: (422, "validation_failed"),
        TicketInvalid: (404, "resource_not_found"),
        InvalidCursor: (422, "validation_failed"),
    }
    status, code = mapping.get(type(error), (422, "validation_failed"))
    return problem(request, status, code, "The request could not be completed.")


def _expected_version(request: Request, value: str | None) -> int | JSONResponse:
    if value is None:
        return problem(request, 428, "precondition_required", "A quoted If-Match version is required.")
    match = ETAG.fullmatch(value)
    if not match:
        return problem(request, 422, "validation_failed", "If-Match must be a quoted integer.")
    return int(match.group(1))


def _idempotency(request: Request, value: str | None) -> str | JSONResponse:
    if not value or len(value) > 255:
        return problem(request, 428, "idempotency_key_required", "Idempotency-Key is required.")
    return value


def _admin(principal: Principal) -> bool:
    return principal.active and "recruiting_admin" in principal.roles


def _job_scope(principal: Principal):
    return or_(
        _admin(principal),
        exists().where(
            JobCollaborator.organization_id == Job.organization_id,
            JobCollaborator.job_id == Job.id,
            JobCollaborator.user_id == principal.user_id,
            or_(
                and_("recruiter" in principal.roles, JobCollaborator.access_role.in_(("job_owner", "job_recruiter"))),
                and_("hiring_manager" in principal.roles, JobCollaborator.access_role == "job_manager"),
            ),
        ),
    )


def _candidate_scope(principal: Principal):
    authorized_application = exists().where(
        Application.organization_id == Candidate.organization_id,
        Application.candidate_id == Candidate.id,
        exists().where(
            JobCollaborator.organization_id == Application.organization_id,
            JobCollaborator.job_id == Application.job_id,
            JobCollaborator.user_id == principal.user_id,
            or_(
                and_("recruiter" in principal.roles, JobCollaborator.access_role.in_(("job_owner", "job_recruiter"))),
                and_("hiring_manager" in principal.roles, JobCollaborator.access_role == "job_manager"),
            ),
        ),
    )
    unassigned_owner = and_(
        "recruiter" in principal.roles,
        Candidate.owner_id == principal.user_id,
        ~exists().where(
            Application.organization_id == Candidate.organization_id,
            Application.candidate_id == Candidate.id,
        ),
    )
    return or_(_admin(principal), unassigned_owner, authorized_application)


def _job_data(job: Job) -> dict[str, Any]:
    return {"id": str(job.id), "title": job.title, "department_id": str(job.department_id) if job.department_id else None, "headcount": job.headcount, "priority": job.priority, "hiring_owner_id": str(job.hiring_owner_id) if job.hiring_owner_id else None, "owner_id": str(job.owner_id), "status": job.status, "version": job.version, "updated_at": job.updated_at.isoformat()}


def _candidate_data(db, candidate: Candidate, principal: Principal) -> dict[str, Any]:
    contacts = db.scalars(select(CandidateContact).where(CandidateContact.organization_id == candidate.organization_id, CandidateContact.candidate_id == candidate.id)).all()
    return {"id": str(candidate.id), "display_name": candidate.display_name, "current_title": candidate.current_title, "location": candidate.location, "owner_id": str(candidate.owner_id) if candidate.owner_id else None, "version": candidate.version, "updated_at": candidate.updated_at.isoformat(), "contacts": [{"kind": item.kind, "value": item.masked_value} for item in contacts]}


def _application_data(item: Application) -> dict[str, Any]:
    return {"id": str(item.id), "candidate_id": str(item.candidate_id), "job_id": str(item.job_id), "resume_id": str(item.resume_id), "owner_id": str(item.owner_id), "stage": item.stage, "source": item.source, "source_application_id": str(item.source_application_id) if item.source_application_id else None, "human_conclusion": item.human_conclusion, "version": item.version, "updated_at": item.updated_at.isoformat()}


def _resource(data: dict[str, Any], status: int = 200) -> JSONResponse:
    response = JSONResponse({"data": data}, status_code=status)
    if "version" in data:
        response.headers["ETag"] = f'"{data["version"]}"'
    return response


@router.get("/jobs")
def list_jobs(request: Request, limit: int = Query(50, ge=1, le=100)):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    with request.app.state.identity_store.sync_session() as db:
        rows = db.scalars(select(Job).where(Job.organization_id == principal.organization_id, _job_scope(principal)).order_by(Job.updated_at.desc(), Job.id.desc()).limit(limit)).all()
        return {"data": [_job_data(row) for row in rows], "meta": {"limit": limit, "next_cursor": None}}


@router.post("/jobs", status_code=201)
def create_job(payload: JobCreate, request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    if not (_admin(principal) or "recruiter" in principal.roles): return _denied(request)
    with request.app.state.identity_store.sync_session() as db:
        job = Job(organization_id=principal.organization_id, owner_id=principal.user_id, **payload.model_dump())
        db.add(job); db.flush()
        db.add(JobCollaborator(organization_id=principal.organization_id, job_id=job.id, user_id=principal.user_id, access_role="job_owner"))
        db.commit()
        return _resource(_job_data(job), 201)


def _load_job(db, principal: Principal, job_id: UUID):
    return db.scalar(select(Job).where(Job.organization_id == principal.organization_id, Job.id == job_id, _job_scope(principal)))


@router.get("/jobs/{job_id}")
def get_job(job_id: UUID, request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    with request.app.state.identity_store.sync_session() as db:
        job = _load_job(db, principal, job_id)
        return _denied(request) if job is None else _resource(_job_data(job))


@router.patch("/jobs/{job_id}")
def patch_job(job_id: UUID, payload: JobPatch, request: Request, if_match: str | None = Header(None)):
    principal = _principal(request); expected = _expected_version(request, if_match)
    if isinstance(principal, JSONResponse): return principal
    if isinstance(expected, JSONResponse): return expected
    with request.app.state.identity_store.sync_session() as db:
        job = _load_job(db, principal, job_id)
        if job is None or "hiring_manager" in principal.roles: return _denied(request)
        if job.version != expected: return _problem_for(request, ResourceVersionConflict())
        for key, value in payload.model_dump(exclude_unset=True).items(): setattr(job, key, value)
        job.version += 1; db.commit()
        return _resource(_job_data(job))


@router.post("/jobs/{job_id}/transitions")
def transition_job(job_id: UUID, payload: Transition, request: Request, if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    principal = _principal(request); expected = _expected_version(request, if_match); key = _idempotency(request, idempotency_key)
    for value in (principal, expected, key):
        if isinstance(value, JSONResponse): return value
    with request.app.state.identity_store.sync_session() as db:
        if _load_job(db, principal, job_id) is None or "hiring_manager" in principal.roles: return _denied(request)
        try:
            status, body = persisted_idempotent(db, principal.organization_id, principal.user_id, "job.transition", key, {"job_id": job_id, **payload.model_dump()}, lambda: (200, {"data": _job_data(transition_job_record(db, job_id, payload.target, expected_version=expected, actor_user_id=principal.user_id, trace_id=request.state.trace_id))}))
            db.commit(); response = JSONResponse(body, status_code=status); response.headers["ETag"] = f'"{body["data"]["version"]}"'; return response
        except Exception as error:
            db.rollback(); return _problem_for(request, error)


def _versions(job_id: UUID, request: Request, model, payload: VersionCreate | None = None):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    with request.app.state.identity_store.sync_session() as db:
        if _load_job(db, principal, job_id) is None: return _denied(request)
        if payload is not None:
            if "hiring_manager" in principal.roles: return _denied(request)
            number = (db.scalar(select(func.max(model.version_number)).where(model.organization_id == principal.organization_id, model.job_id == job_id)) or 0) + 1
            row = model(organization_id=principal.organization_id, job_id=job_id, version_number=number, content=payload.content, created_by=principal.user_id); db.add(row); db.commit()
            return _resource({"id": str(row.id), "version_number": row.version_number, "content": row.content}, 201)
        rows = db.scalars(select(model).where(model.organization_id == principal.organization_id, model.job_id == job_id).order_by(model.version_number)).all()
        return {"data": [{"id": str(row.id), "version_number": row.version_number, "content": row.content} for row in rows], "meta": {"count": len(rows)}}


@router.get("/jobs/{job_id}/jd-versions")
def list_jd(job_id: UUID, request: Request): return _versions(job_id, request, JobJdVersion)
@router.post("/jobs/{job_id}/jd-versions", status_code=201)
def create_jd(job_id: UUID, payload: VersionCreate, request: Request): return _versions(job_id, request, JobJdVersion, payload)
@router.get("/jobs/{job_id}/rule-versions")
def list_rules(job_id: UUID, request: Request): return _versions(job_id, request, ScreeningRuleVersion)
@router.post("/jobs/{job_id}/rule-versions", status_code=201)
def create_rules(job_id: UUID, payload: VersionCreate, request: Request): return _versions(job_id, request, ScreeningRuleVersion, payload)


@router.get("/jobs/{job_id}/funnel")
def funnel(job_id: UUID, request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    with request.app.state.identity_store.sync_session() as db:
        if _load_job(db, principal, job_id) is None: return _denied(request)
        counts = Counter(db.scalars(select(Application.stage).where(Application.organization_id == principal.organization_id, Application.job_id == job_id)).all())
        return {"data": {"job_id": str(job_id), "stages": dict(counts), "total": sum(counts.values())}}


@router.get("/candidates")
def list_candidates(request: Request, job_id: UUID | None = None, stage: str | None = None, owner_id: UUID | None = None, source: str | None = None, q: str | None = Query(None, max_length=200), cursor: str | None = None, limit: int = Query(50, ge=1, le=100), sort: str = "-updated_at"):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    if sort != "-updated_at": return problem(request, 422, "validation_failed", "Unsupported sort order.")
    with request.app.state.identity_store.sync_session() as db:
        query = select(Candidate).where(Candidate.organization_id == principal.organization_id, _candidate_scope(principal))
        if owner_id: query = query.where(Candidate.owner_id == owner_id)
        if q: query = query.where(or_(Candidate.display_name.ilike(f"%{q}%"), Candidate.current_title.ilike(f"%{q}%")))
        if any((job_id, stage, source)):
            query = query.join(Application, and_(Application.organization_id == Candidate.organization_id, Application.candidate_id == Candidate.id))
            if job_id: query = query.where(Application.job_id == job_id)
            if stage: query = query.where(Application.stage == stage)
            if source: query = query.where(Application.source == source)
        if cursor:
            try:
                decoded = request.app.state.recruiting_cursor.decode(cursor, str(principal.organization_id), sort)
                updated_at = datetime.fromisoformat(decoded["updated_at"])
                query = query.where(or_(Candidate.updated_at < updated_at, and_(Candidate.updated_at == updated_at, Candidate.id < UUID(decoded["id"]))))
            except Exception as error: return _problem_for(request, InvalidCursor() if not isinstance(error, InvalidCursor) else error)
        rows = db.scalars(query.distinct().order_by(Candidate.updated_at.desc(), Candidate.id.desc()).limit(limit + 1)).all()
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]; next_cursor = request.app.state.recruiting_cursor.encode(str(principal.organization_id), sort, last.updated_at.isoformat(), str(last.id)); rows = rows[:limit]
        return {"data": [_candidate_data(db, row, principal) for row in rows], "meta": {"limit": limit, "next_cursor": next_cursor}}


@router.post("/candidates", status_code=201)
def create_candidate(payload: CandidateCreate, request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    if not (_admin(principal) or "recruiter" in principal.roles): return _denied(request)
    with request.app.state.identity_store.sync_session() as db:
        candidate = Candidate(organization_id=principal.organization_id, display_name=payload.display_name, current_title=payload.current_title, location=payload.location, owner_id=payload.owner_id or principal.user_id); db.add(candidate); db.flush()
        try:
            for contact in payload.contacts:
                protected = request.app.state.contact_cipher.protect(contact.kind, contact.value)
                canonical_kind = contact.kind.strip().casefold()
                db.add(CandidateContact(organization_id=principal.organization_id, candidate_id=candidate.id, kind=canonical_kind, ciphertext=protected.ciphertext, lookup_hash=protected.lookup_hash, masked_value=protected.masked_value))
            db.add(CandidateEvent(organization_id=principal.organization_id, candidate_id=candidate.id, actor_user_id=principal.user_id, event_type="candidate.created", payload={}))
            db.commit(); return _resource(_candidate_data(db, candidate, principal), 201)
        except Exception as error:
            db.rollback(); return _problem_for(request, error)


def _load_candidate(db, principal: Principal, candidate_id: UUID):
    return db.scalar(select(Candidate).where(Candidate.organization_id == principal.organization_id, Candidate.id == candidate_id, _candidate_scope(principal)))


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: UUID, request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    with request.app.state.identity_store.sync_session() as db:
        candidate = _load_candidate(db, principal, candidate_id)
        return _denied(request) if candidate is None else _resource(_candidate_data(db, candidate, principal))


@router.patch("/candidates/{candidate_id}")
def patch_candidate(candidate_id: UUID, payload: CandidatePatch, request: Request, if_match: str | None = Header(None)):
    principal = _principal(request); expected = _expected_version(request, if_match)
    if isinstance(principal, JSONResponse): return principal
    if isinstance(expected, JSONResponse): return expected
    with request.app.state.identity_store.sync_session() as db:
        candidate = _load_candidate(db, principal, candidate_id)
        if candidate is None or "hiring_manager" in principal.roles: return _denied(request)
        if candidate.version != expected: return _problem_for(request, ResourceVersionConflict())
        changes = payload.model_dump(exclude_unset=True)
        for key, value in changes.items(): setattr(candidate, key, value)
        candidate.version += 1
        db.add(CandidateEvent(organization_id=principal.organization_id, candidate_id=candidate.id, actor_user_id=principal.user_id, event_type="candidate.corrected", payload={"fields": sorted(changes)})); db.add(AuditLog(organization_id=principal.organization_id, actor_user_id=principal.user_id, event_type="candidate.corrected", outcome="success", trace_id=request.state.trace_id, metadata_json={"fields": sorted(changes)})); db.commit()
        return _resource(_candidate_data(db, candidate, principal))


@router.get("/candidates/{candidate_id}/timeline")
def timeline(candidate_id: UUID, request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    with request.app.state.identity_store.sync_session() as db:
        if _load_candidate(db, principal, candidate_id) is None: return _denied(request)
        rows = db.scalars(select(CandidateEvent).where(CandidateEvent.organization_id == principal.organization_id, CandidateEvent.candidate_id == candidate_id).order_by(CandidateEvent.created_at.desc())).all()
        return {"data": [{"id": str(row.id), "event_type": row.event_type, "payload": row.payload, "created_at": row.created_at.isoformat()} for row in rows], "meta": {"count": len(rows)}}


@router.get("/candidates/{candidate_id}/notes")
def notes(candidate_id: UUID, request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    with request.app.state.identity_store.sync_session() as db:
        if _load_candidate(db, principal, candidate_id) is None: return _denied(request)
        rows = db.scalars(select(CandidateNote).where(CandidateNote.organization_id == principal.organization_id, CandidateNote.candidate_id == candidate_id).order_by(CandidateNote.created_at)).all()
        return {"data": [{"id": str(row.id), "body": row.payload["body"], "author_id": str(row.actor_user_id), "created_at": row.created_at.isoformat()} for row in rows], "meta": {"count": len(rows)}}


@router.post("/candidates/{candidate_id}/notes", status_code=201)
def add_note(candidate_id: UUID, payload: NoteCreate, request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    with request.app.state.identity_store.sync_session() as db:
        if _load_candidate(db, principal, candidate_id) is None: return _denied(request)
        note = CandidateNote(organization_id=principal.organization_id, candidate_id=candidate_id, actor_user_id=principal.user_id, event_type="candidate.note", payload={"body": payload.body}); db.add(note); db.add(CandidateEvent(organization_id=principal.organization_id, candidate_id=candidate_id, actor_user_id=principal.user_id, event_type="candidate.note_added", payload={})); db.commit()
        return _resource({"id": str(note.id), "body": payload.body, "author_id": str(principal.user_id)}, 201)


@router.get("/candidates/{candidate_id}/resumes")
def resumes(candidate_id: UUID, request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    with request.app.state.identity_store.sync_session() as db:
        if _load_candidate(db, principal, candidate_id) is None: return _denied(request)
        rows = db.scalars(select(Resume).where(Resume.organization_id == principal.organization_id, Resume.candidate_id == candidate_id).order_by(Resume.version_number)).all()
        return {"data": [{"id": str(row.id), "candidate_id": str(row.candidate_id), "version_number": row.version_number, "created_at": row.created_at.isoformat()} for row in rows], "meta": {"count": len(rows)}}


def _load_resume(db, principal: Principal, resume_id: UUID):
    return db.scalar(select(Resume).join(Candidate, and_(Candidate.organization_id == Resume.organization_id, Candidate.id == Resume.candidate_id)).where(Resume.organization_id == principal.organization_id, Resume.id == resume_id, _candidate_scope(principal)))


@router.get("/resumes/{resume_id}/preview")
def preview(resume_id: UUID, request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    with request.app.state.identity_store.sync_session() as db:
        resume = _load_resume(db, principal, resume_id)
        if resume is None: return _denied(request)
        file = resume.__table__.metadata.tables["file_objects"]
        storage_key = db.execute(select(file.c.storage_key).where(file.c.organization_id == principal.organization_id, file.c.id == resume.file_object_id)).scalar_one()
        content = request.app.state.resume_storage.read_preview(storage_key)
        db.add(AuditLog(organization_id=principal.organization_id, actor_user_id=principal.user_id, event_type="resume.previewed", outcome="success", trace_id=request.state.trace_id, metadata_json={"resume_id": str(resume.id)})); db.commit()
        response = JSONResponse({"data": {"resume_id": str(resume.id), "text": content}}); response.headers["Cache-Control"] = "no-store"; return response


@router.post("/resumes/{resume_id}/download-tickets", status_code=201)
def issue_ticket(resume_id: UUID, request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    if "hiring_manager" in principal.roles: return _denied(request)
    with request.app.state.identity_store.sync_session() as db:
        resume = _load_resume(db, principal, resume_id)
        if resume is None: return _denied(request)
        raw = issue_download_ticket_record(db, principal.organization_id, principal.user_id, resume.id, request.app.state.recruiting_clock, request.app.state.recruiting_tokens)
        db.add(AuditLog(organization_id=principal.organization_id, actor_user_id=principal.user_id, event_type="resume.download_ticket_issued", outcome="success", trace_id=request.state.trace_id, metadata_json={"resume_id": str(resume.id)})); db.commit()
        response = _resource({"token": raw, "expires_in": 60}, 201); response.headers["Cache-Control"] = "no-store"; return response


@router.post("/download-tickets/consume")
def consume_ticket(payload: TicketConsume, request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    with request.app.state.identity_store.sync_session() as db:
        ticket = db.scalar(select(DownloadTicket).where(DownloadTicket.token_hash == hashlib.sha256(payload.token.encode()).hexdigest()))
        if ticket is None: return _denied(request)
        resume = _load_resume(db, principal, ticket.resume_id)
        if resume is None or "hiring_manager" in principal.roles: return _denied(request)
        try: consume_download_ticket_record(db, payload.token, principal.organization_id, principal.user_id, resume.id, request.app.state.recruiting_clock)
        except TicketInvalid as error: db.rollback(); return _problem_for(request, error)
        file = resume.__table__.metadata.tables["file_objects"]
        row = db.execute(select(file.c.storage_key, file.c.mime_type, file.c.original_filename).where(file.c.organization_id == principal.organization_id, file.c.id == resume.file_object_id)).one()
        db.add(AuditLog(organization_id=principal.organization_id, actor_user_id=principal.user_id, event_type="resume.downloaded", outcome="success", trace_id=request.state.trace_id, metadata_json={"resume_id": str(resume.id)})); db.commit()
        download = request.app.state.resume_storage.stream_download(row.storage_key, row.mime_type, row.original_filename)
        response = StreamingResponse(download.chunks, media_type=download.content_type); response.headers["Cache-Control"] = "no-store"; response.headers["Content-Disposition"] = f'attachment; filename="{download.filename.replace(chr(34), "")}"'; response.headers["X-Content-Type-Options"] = "nosniff"; return response


@router.get("/candidates/{candidate_id}/applications")
def applications(candidate_id: UUID, request: Request):
    principal = _principal(request)
    if isinstance(principal, JSONResponse): return principal
    with request.app.state.identity_store.sync_session() as db:
        if _load_candidate(db, principal, candidate_id) is None: return _denied(request)
        rows = db.scalars(select(Application).join(Job, and_(Job.organization_id == Application.organization_id, Job.id == Application.job_id)).where(Application.organization_id == principal.organization_id, Application.candidate_id == candidate_id, _job_scope(principal)).order_by(Application.created_at.desc())).all()
        return {"data": [_application_data(row) for row in rows], "meta": {"count": len(rows)}}


@router.post("/jobs/{job_id}/applications", status_code=201)
def create_application(job_id: UUID, payload: ApplicationCreate, request: Request, idempotency_key: str | None = Header(None)):
    principal = _principal(request); key = _idempotency(request, idempotency_key)
    if isinstance(principal, JSONResponse): return principal
    if isinstance(key, JSONResponse): return key
    with request.app.state.identity_store.sync_session() as db:
        if _load_job(db, principal, job_id) is None or "hiring_manager" in principal.roles: return _denied(request)
        try:
            def action():
                item = create_application_record(db, organization_id=principal.organization_id, candidate_id=payload.candidate_id, job_id=job_id, resume_id=payload.resume_id, owner_id=payload.owner_id or principal.user_id, source=payload.source)
                db.add(CandidateEvent(organization_id=principal.organization_id, candidate_id=item.candidate_id, actor_user_id=principal.user_id, event_type="application.created", payload={"application_id": str(item.id), "job_id": str(job_id)})); db.add(AuditLog(organization_id=principal.organization_id, actor_user_id=principal.user_id, event_type="application.created", outcome="success", trace_id=request.state.trace_id, metadata_json={"application_id": str(item.id), "job_id": str(job_id)})); return 201, {"data": _application_data(item)}
            status, body = persisted_idempotent(db, principal.organization_id, principal.user_id, "application.create", key, {"job_id": job_id, **payload.model_dump()}, action); db.commit(); response = JSONResponse(body, status_code=status); response.headers["ETag"] = f'"{body["data"]["version"]}"'; return response
        except Exception as error: db.rollback(); return _problem_for(request, error)


def _load_application(db, principal: Principal, application_id: UUID):
    return db.scalar(select(Application).join(Job, and_(Job.organization_id == Application.organization_id, Job.id == Application.job_id)).where(Application.organization_id == principal.organization_id, Application.id == application_id, _job_scope(principal)))


@router.patch("/applications/{application_id}")
def patch_application(application_id: UUID, payload: ApplicationPatch, request: Request, if_match: str | None = Header(None)):
    principal = _principal(request); expected = _expected_version(request, if_match)
    if isinstance(principal, JSONResponse): return principal
    if isinstance(expected, JSONResponse): return expected
    with request.app.state.identity_store.sync_session() as db:
        item = _load_application(db, principal, application_id)
        if item is None or "hiring_manager" in principal.roles: return _denied(request)
        if item.version != expected: return _problem_for(request, ResourceVersionConflict())
        for key, value in payload.model_dump(exclude_unset=True).items(): setattr(item, key, value)
        item.version += 1; db.commit(); return _resource(_application_data(item))


@router.post("/applications/{application_id}/transitions")
def transition_application(application_id: UUID, payload: Transition, request: Request, if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    principal = _principal(request); expected = _expected_version(request, if_match); key = _idempotency(request, idempotency_key)
    for value in (principal, expected, key):
        if isinstance(value, JSONResponse): return value
    with request.app.state.identity_store.sync_session() as db:
        if _load_application(db, principal, application_id) is None or "hiring_manager" in principal.roles: return _denied(request)
        try:
            status, body = persisted_idempotent(db, principal.organization_id, principal.user_id, "application.transition", key, {"application_id": application_id, **payload.model_dump()}, lambda: (200, {"data": _application_data(transition_application_record(db, application_id, payload.target, expected_version=expected, actor_user_id=principal.user_id, trace_id=request.state.trace_id, reason_code=payload.reason_code, reason_text=payload.reason_text))})); db.commit(); response = JSONResponse(body, status_code=status); response.headers["ETag"] = f'"{body["data"]["version"]}"'; return response
        except Exception as error: db.rollback(); return _problem_for(request, error)
