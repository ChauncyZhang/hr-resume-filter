from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Meta(ApiModel):
    limit: int | None = None
    count: int | None = None
    next_cursor: str | None = None


class ContactOut(ApiModel):
    kind: str
    value: str


class JobOut(ApiModel):
    id: str
    title: str
    department_id: str | None
    headcount: int
    priority: str
    hiring_owner_id: str | None
    owner_id: str
    status: str
    version: int
    updated_at: str


class CandidateOut(ApiModel):
    id: str
    display_name: str
    current_title: str | None
    location: str | None
    owner_id: str | None
    version: int
    updated_at: str
    contacts: list[ContactOut]


class ApplicationOut(ApiModel):
    id: str
    candidate_id: str
    job_id: str
    resume_id: str
    owner_id: str
    stage: str
    source: str
    source_application_id: str | None
    human_conclusion: str | None
    version: int
    updated_at: str


class VersionOut(ApiModel):
    id: str
    version_number: int
    content: dict[str, Any]


class NoteOut(ApiModel):
    id: str
    application_id: str
    body: str
    author_id: str
    created_at: str | None = None


class ResumeOut(ApiModel):
    id: str
    candidate_id: str
    version_number: int
    created_at: str


class TimelineEventOut(ApiModel):
    id: str
    event_type: str
    summary: str
    actor_id: str
    created_at: str


class FunnelOut(ApiModel):
    job_id: str
    stages: dict[str, int]
    total: int


class TicketOut(ApiModel):
    token: str
    expires_in: int


class PreviewOut(ApiModel):
    resume_id: str
    text: str


class JobResource(ApiModel): data: JobOut
class JobCollection(ApiModel): data: list[JobOut]; meta: Meta
class CandidateResource(ApiModel): data: CandidateOut
class CandidateCollection(ApiModel): data: list[CandidateOut]; meta: Meta
class ApplicationResource(ApiModel): data: ApplicationOut
class ApplicationCollection(ApiModel): data: list[ApplicationOut]; meta: Meta
class VersionResource(ApiModel): data: VersionOut
class VersionCollection(ApiModel): data: list[VersionOut]; meta: Meta
class NoteResource(ApiModel): data: NoteOut
class NoteCollection(ApiModel): data: list[NoteOut]; meta: Meta
class ResumeCollection(ApiModel): data: list[ResumeOut]; meta: Meta
class TimelineCollection(ApiModel): data: list[TimelineEventOut]; meta: Meta
class FunnelResource(ApiModel): data: FunnelOut
class TicketResource(ApiModel): data: TicketOut
class PreviewResource(ApiModel): data: PreviewOut


class Problem(ApiModel):
    type: str
    title: str
    status: int
    detail: str
    code: str
    trace_id: str
    errors: list[dict[str, str]] = Field(default_factory=list)
