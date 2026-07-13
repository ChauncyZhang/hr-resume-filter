from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,model_validator

class ApiModel(BaseModel): model_config=ConfigDict(extra="forbid")
class LlmConfigUpdate(ApiModel):
    provider_id:str=Field(min_length=2,max_length=64); model:str=Field(min_length=1,max_length=128); enabled:bool=False; api_key:str|None=Field(default=None,min_length=1,max_length=4096); allowed_job_ids:list[UUID]=Field(default_factory=list,max_length=100)
    @model_validator(mode="after")
    def unique_jobs(self):
        if len(set(self.allowed_job_ids))!=len(self.allowed_job_ids): raise ValueError("duplicate job IDs")
        return self
class LlmConfigOut(ApiModel):
    configured:bool; enabled:bool; provider_id:str|None; model:str|None; version:int; last_test_status:str|None; last_test_error_code:str|None; last_test_latency_ms:int|None; last_tested_at:str|None; key_configured:bool|None=None; allowed_job_ids:list[str]|None=None; available_providers:dict[str,list[str]]|None=None
class LlmConfigResource(ApiModel): data:LlmConfigOut
class LlmTestOut(ApiModel): status:str; safe_error_code:str|None; latency_ms:int|None
class LlmTestResource(ApiModel): data:LlmTestOut
