from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Meta(ApiModel):
    limit: int | None = None
    count: int | None = None
    next_cursor: str | None = None


class OwnerFacetOut(ApiModel):
    id: str
    name: str


class CandidateMeta(Meta):
    owners: list[OwnerFacetOut]


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


RuleItem = Annotated[str, Field(min_length=1, max_length=500)]


class JobDefinitionCommand(ApiModel):
    title: str = Field(min_length=1, max_length=200)
    department_id: UUID | None = None
    headcount: int = Field(ge=1, le=1000)
    priority: Literal["high", "normal", "low"]
    hiring_owner_id: UUID | None = None
    description: str = Field(min_length=1, max_length=50_000)
    location: str = Field(max_length=200)
    process_template: str = Field(min_length=1, max_length=100)
    llm_enabled: bool
    must_have: list[RuleItem] = Field(max_length=100)
    nice_to_have: list[RuleItem] = Field(max_length=100)
    publish: bool

    @field_validator("title", "description", "process_template")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()

    @field_validator("must_have", "nice_to_have")
    @classmethod
    def nonblank_rules(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("rule items must not be blank")
        return [value.strip() for value in values]


class JobJdDefinitionOut(ApiModel):
    id: str
    version_number: int
    description: str
    location: str
    process_template: str
    llm_enabled: bool


class ScreeningRulesDefinitionOut(ApiModel):
    id: str
    version_number: int
    must_have: list[str]
    nice_to_have: list[str]


class JobDefinitionOut(ApiModel):
    job: JobOut
    jd: JobJdDefinitionOut | None
    rules: ScreeningRulesDefinitionOut | None


class CandidateOut(ApiModel):
    id: str
    display_name: str
    current_title: str | None
    location: str | None
    owner_id: str | None
    version: int
    updated_at: str
    contacts: list[ContactOut]


class CandidateApplicationSummaryOut(ApiModel):
    id: str
    job_id: str
    job_title: str
    resume_id: str
    owner_id: str
    owner_name: str
    stage: str
    source: str
    human_conclusion: str | None
    version: int
    updated_at: str
    rule_score: int | None
    recommendation: str | None


class CandidateListOut(CandidateOut):
    application: CandidateApplicationSummaryOut | None


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
class JobDefinitionResource(ApiModel): data: JobDefinitionOut
class JobCollection(ApiModel): data: list[JobOut]; meta: Meta
class CandidateResource(ApiModel): data: CandidateOut
class CandidateCollection(ApiModel): data: list[CandidateListOut]; meta: CandidateMeta
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
