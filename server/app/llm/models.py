import uuid
from datetime import datetime,timezone
from sqlalchemy import JSON,Boolean,CheckConstraint,DateTime,ForeignKeyConstraint,Integer,LargeBinary,String,UniqueConstraint,Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from server.app.identity.models import Base

JSON_DOCUMENT=JSON().with_variant(JSONB(),"postgresql")
def now(): return datetime.now(timezone.utc)

class LlmProviderConfig(Base):
    __tablename__="llm_provider_configs"
    id:Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4); organization_id:Mapped[uuid.UUID]=mapped_column(Uuid,nullable=False)
    provider_id:Mapped[str]=mapped_column(String(64)); model:Mapped[str]=mapped_column(String(128)); encrypted_api_key:Mapped[bytes|None]=mapped_column(LargeBinary)
    enabled:Mapped[bool]=mapped_column(Boolean,default=False); allowed_job_ids:Mapped[list]=mapped_column(JSON_DOCUMENT,default=list); version:Mapped[int]=mapped_column(Integer,default=1)
    created_by:Mapped[uuid.UUID]=mapped_column(Uuid); updated_by:Mapped[uuid.UUID]=mapped_column(Uuid); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,onupdate=now)
    last_test_status:Mapped[str|None]=mapped_column(String(20)); last_test_error_code:Mapped[str|None]=mapped_column(String(64)); last_test_latency_ms:Mapped[int|None]=mapped_column(Integer); last_tested_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    __table_args__=(UniqueConstraint("organization_id"),UniqueConstraint("organization_id","id"),ForeignKeyConstraint(["organization_id","created_by"],["users.organization_id","users.id"]),ForeignKeyConstraint(["organization_id","updated_by"],["users.organization_id","users.id"]),CheckConstraint("version>=1",name="ck_llm_provider_configs_version"),CheckConstraint("not enabled or encrypted_api_key is not null",name="ck_llm_provider_configs_enabled_key"),CheckConstraint("last_test_status is null or last_test_status in ('succeeded','failed')",name="ck_llm_provider_configs_test_status"),CheckConstraint("last_test_latency_ms is null or last_test_latency_ms>=0",name="ck_llm_provider_configs_latency"))

class PromptVersion(Base):
    __tablename__="prompt_versions"
    id:Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4); organization_id:Mapped[uuid.UUID]=mapped_column(Uuid,nullable=False); name:Mapped[str]=mapped_column(String(100)); version_number:Mapped[int]=mapped_column(Integer); content:Mapped[dict]=mapped_column(JSON_DOCUMENT); content_hash:Mapped[str]=mapped_column(String(64)); created_by:Mapped[uuid.UUID]=mapped_column(Uuid); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(UniqueConstraint("organization_id","id"),UniqueConstraint("organization_id","name","version_number"),ForeignKeyConstraint(["organization_id","created_by"],["users.organization_id","users.id"]),CheckConstraint("version_number>=1",name="ck_prompt_versions_number"))

class LlmInvocation(Base):
    __tablename__="llm_invocations"
    id:Mapped[uuid.UUID]=mapped_column(Uuid,primary_key=True,default=uuid.uuid4); organization_id:Mapped[uuid.UUID]=mapped_column(Uuid,nullable=False); config_id:Mapped[uuid.UUID]=mapped_column(Uuid); prompt_version_id:Mapped[uuid.UUID|None]=mapped_column(Uuid); screening_result_id:Mapped[uuid.UUID|None]=mapped_column(Uuid); provider_id:Mapped[str]=mapped_column(String(64)); model:Mapped[str]=mapped_column(String(128)); request_field_manifest:Mapped[list]=mapped_column(JSON_DOCUMENT); status:Mapped[str]=mapped_column(String(20)); latency_ms:Mapped[int|None]=mapped_column(Integer); usage:Mapped[dict]=mapped_column(JSON_DOCUMENT,default=dict); safe_error_code:Mapped[str|None]=mapped_column(String(64)); trace_id:Mapped[str|None]=mapped_column(String(100)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(ForeignKeyConstraint(["organization_id","config_id"],["llm_provider_configs.organization_id","llm_provider_configs.id"]),ForeignKeyConstraint(["organization_id","prompt_version_id"],["prompt_versions.organization_id","prompt_versions.id"]),ForeignKeyConstraint(["organization_id","screening_result_id"],["screening_results.organization_id","screening_results.id"]),CheckConstraint("status in ('queued','succeeded','failed')",name="ck_llm_invocations_status"),CheckConstraint("latency_ms is null or latency_ms>=0",name="ck_llm_invocations_latency"))
