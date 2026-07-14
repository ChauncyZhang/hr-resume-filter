from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActorOut(StrictModel):
    id: UUID | None
    display_name: str


class AuditResourceOut(StrictModel):
    type: str
    id: UUID
    label: str | None


class AuditLogOut(StrictModel):
    id: UUID
    created_at: datetime
    actor: ActorOut
    category: str
    event_type: str
    resource: AuditResourceOut | None
    outcome: str
    network_ref: str | None
    trace_id: str | None
    summary: str


class AuditMeta(StrictModel):
    next_cursor: str | None
    limit: int


class AuditCollection(StrictModel):
    data: list[AuditLogOut]
    meta: AuditMeta


class RetentionValues(StrictModel):
    terminal_days: int = Field(ge=30, le=3650)
    talent_pool_days: int = Field(ge=30, le=3650)
    backup_window_days: int = Field(ge=30, le=3650)


class RetentionPolicyPatch(RetentionValues):
    impact_token: str | None = Field(default=None, min_length=40, max_length=4096)


class RetentionPolicyOut(RetentionValues):
    id: UUID
    version: int
    updated_at: datetime
    updated_by: ActorOut


class RetentionPolicyResource(StrictModel):
    data: RetentionPolicyOut


class RetentionPreviewOut(StrictModel):
    current_version: int
    shortening: bool
    affected_candidate_count: int
    impact_token: str
    expires_at: datetime


class RetentionPreviewResource(StrictModel):
    data: RetentionPreviewOut
