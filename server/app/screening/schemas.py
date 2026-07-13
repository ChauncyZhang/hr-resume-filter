from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,model_validator
class ApiModel(BaseModel): model_config=ConfigDict(extra="forbid")
class RunCreate(ApiModel): jd_version_id:UUID|None=None; rule_version_id:UUID|None=None; source:Literal["upload","manual"]="upload"
class RunOut(ApiModel): id:str; job_id:str; jd_version_id:str; rule_version_id:str; source:str; status:str; total_count:int; processed_count:int; succeeded_count:int; failed_count:int; version:int; created_at:str; error_summary:dict[str,int]=Field(default_factory=dict)
class LlmEvaluationOut(ApiModel): score:int; recommendation:str; summary:str; strengths:list[str]; gaps:list[str]; risks:list[str]; questions:list[str]
class RuleResultOut(ApiModel): score:int; recommendation:str; required_hits:list[str]; required_missing:list[str]; bonus_hits:list[str]; risks:list[str]
class ItemOut(ApiModel): id:str; run_id:str; filename:str; mime_type:str; size_bytes:int; status:str; parser_version:str|None; parse_quality:str|None; error_code:str|None; attempts:int; created_at:str; retryable:bool=False; candidate_id:str|None=None; candidate_name:str|None=None; rule_result:RuleResultOut|None=None; application_stage:str|None=None; application_version:int|None=None; llm_status:str; llm_error_code:str|None; llm_attempts:int; llm_evaluation:LlmEvaluationOut|None=None
class Meta(ApiModel): limit:int; next_cursor:str|None=None
class RunResource(ApiModel): data:RunOut
class ItemResource(ApiModel): data:ItemOut
class ItemCollection(ApiModel): data:list[ItemOut]; meta:Meta
class RetryOut(ApiModel): item:ItemOut; run:RunOut
class RetryResource(ApiModel): data:RetryOut
class BulkItem(ApiModel): item_id:UUID; expected_application_version:int=Field(ge=1)
class BulkAction(ApiModel):
    command:Literal["advance_to_review","reject"]; items:list[BulkItem]=Field(min_length=1,max_length=100); reason_code:str|None=Field(default=None,pattern=r"^[a-z][a-z0-9_]{0,63}$"); reason_text:str|None=Field(default=None,max_length=1000)
    @model_validator(mode="after")
    def validate_action(self):
        if len({item.item_id for item in self.items})!=len(self.items): raise ValueError("duplicate item IDs")
        if self.command=="reject" and not self.reason_code: raise ValueError("rejection reason required")
        if self.command!="reject" and (self.reason_code is not None or self.reason_text is not None): raise ValueError("reason is only valid for rejection")
        return self
class BulkApplicationOut(ApiModel): id:str; stage:str; version:int; result:Literal["applied","already_applied"]
class BulkOut(ApiModel): command:str; applied_count:int; already_applied_count:int; applications:list[BulkApplicationOut]
class BulkResource(ApiModel): data:BulkOut
