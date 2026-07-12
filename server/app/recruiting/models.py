import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer, LargeBinary, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from server.app.identity.models import Base


def now(): return datetime.now(timezone.utc)


class Record:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Candidate(Record, Base):
    __tablename__ = "candidates"
    display_name: Mapped[str] = mapped_column(String(200))
    current_title: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (UniqueConstraint("organization_id", "id"), ForeignKeyConstraint(["organization_id", "owner_id"], ["users.organization_id", "users.id"]))


class CandidateContact(Record, Base):
    __tablename__ = "candidate_contacts"
    candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(20))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    lookup_hash: Mapped[str] = mapped_column(String(64))
    masked_value: Mapped[str] = mapped_column(String(320))
    __table_args__ = (UniqueConstraint("organization_id", "kind", "lookup_hash"), ForeignKeyConstraint(["organization_id", "candidate_id"], ["candidates.organization_id", "candidates.id"], ondelete="CASCADE"))


class FileObject(Record, Base):
    __tablename__ = "file_objects"
    storage_key: Mapped[str] = mapped_column(String(512))
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    __table_args__ = (UniqueConstraint("organization_id", "id"), UniqueConstraint("organization_id", "storage_key"), ForeignKeyConstraint(["organization_id", "uploaded_by"], ["users.organization_id", "users.id"]))


class Resume(Record, Base):
    __tablename__ = "resumes"
    candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    file_object_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    version_number: Mapped[int] = mapped_column(Integer)
    parsed_text: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("organization_id", "id"), UniqueConstraint("organization_id", "candidate_id", "version_number"), UniqueConstraint("organization_id", "id", "candidate_id"), ForeignKeyConstraint(["organization_id", "candidate_id"], ["candidates.organization_id", "candidates.id"]), ForeignKeyConstraint(["organization_id", "file_object_id"], ["file_objects.organization_id", "file_objects.id"]))


class VersionRecord(Record):
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    version_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid)


def version_constraints():
    return (UniqueConstraint("organization_id", "job_id", "version_number"), ForeignKeyConstraint(["organization_id", "job_id"], ["jobs.organization_id", "jobs.id"]), ForeignKeyConstraint(["organization_id", "created_by"], ["users.organization_id", "users.id"]))


class JobJdVersion(VersionRecord, Base):
    __tablename__ = "job_jd_versions"
    __table_args__ = version_constraints()


class ScreeningRuleVersion(VersionRecord, Base):
    __tablename__ = "screening_rule_versions"
    __table_args__ = version_constraints()


class Application(Record, Base):
    __tablename__ = "applications"
    candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    resume_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    source_application_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    stage: Mapped[str] = mapped_column(String(32), default="new")
    source: Mapped[str] = mapped_column(String(64), default="manual")
    human_conclusion: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (UniqueConstraint("organization_id", "id"), UniqueConstraint("organization_id", "id", "candidate_id", "job_id"), CheckConstraint("stage in ('new','review','contact','interview_pending','interviewing','decision','passed','hired','rejected','withdrawn')", name="ck_applications_stage"), Index("uq_applications_active", "organization_id", "candidate_id", "job_id", unique=True, postgresql_where=text("stage not in ('hired','rejected','withdrawn')"), sqlite_where=text("stage not in ('hired','rejected','withdrawn')")), ForeignKeyConstraint(["organization_id", "candidate_id"], ["candidates.organization_id", "candidates.id"]), ForeignKeyConstraint(["organization_id", "job_id"], ["jobs.organization_id", "jobs.id"]), ForeignKeyConstraint(["organization_id", "resume_id", "candidate_id"], ["resumes.organization_id", "resumes.id", "resumes.candidate_id"]), ForeignKeyConstraint(["organization_id", "source_application_id", "candidate_id", "job_id"], ["applications.organization_id", "applications.id", "applications.candidate_id", "applications.job_id"]), ForeignKeyConstraint(["organization_id", "owner_id"], ["users.organization_id", "users.id"]))


class EventRecord(Record):
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class ApplicationStageEvent(EventRecord, Base):
    __tablename__ = "application_stage_events"
    application_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    __table_args__ = (ForeignKeyConstraint(["organization_id", "application_id"], ["applications.organization_id", "applications.id"]), ForeignKeyConstraint(["organization_id", "actor_user_id"], ["users.organization_id", "users.id"]))


class CandidateNote(EventRecord, Base):
    __tablename__ = "candidate_notes"
    candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    __table_args__ = (ForeignKeyConstraint(["organization_id", "candidate_id"], ["candidates.organization_id", "candidates.id"]), ForeignKeyConstraint(["organization_id", "actor_user_id"], ["users.organization_id", "users.id"]))


class CandidateEvent(EventRecord, Base):
    __tablename__ = "candidate_events"
    candidate_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    __table_args__ = (ForeignKeyConstraint(["organization_id", "candidate_id"], ["candidates.organization_id", "candidates.id"]), ForeignKeyConstraint(["organization_id", "actor_user_id"], ["users.organization_id", "users.id"]))


class DownloadTicket(Record, Base):
    __tablename__ = "download_tickets"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    resume_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (ForeignKeyConstraint(["organization_id", "user_id"], ["users.organization_id", "users.id"]), ForeignKeyConstraint(["organization_id", "resume_id"], ["resumes.organization_id", "resumes.id"]))


class IdempotencyRecord(Record, Base):
    __tablename__ = "idempotency_records"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    operation: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    response_json: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("organization_id", "user_id", "operation", "idempotency_key"), ForeignKeyConstraint(["organization_id", "user_id"], ["users.organization_id", "users.id"]))
