from pydantic import BaseModel,ConfigDict,Field
class ApiModel(BaseModel): model_config=ConfigDict(extra="forbid")
class RunCreate(ApiModel): jd_version_id:str|None=None; rule_version_id:str|None=None; source:str="upload"
class RunOut(ApiModel): id:str; job_id:str; jd_version_id:str; rule_version_id:str; source:str; status:str; total_count:int; processed_count:int; succeeded_count:int; failed_count:int; version:int; created_at:str
class ItemOut(ApiModel): id:str; run_id:str; filename:str; mime_type:str; size_bytes:int; status:str; parser_version:str|None; parse_quality:str|None; error_code:str|None; attempts:int; created_at:str
class Meta(ApiModel): limit:int; next_cursor:str|None=None
class RunResource(ApiModel): data:RunOut
class ItemResource(ApiModel): data:ItemOut
class ItemCollection(ApiModel): data:list[ItemOut]; meta:Meta
