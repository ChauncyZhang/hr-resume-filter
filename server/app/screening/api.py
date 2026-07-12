import hashlib,re,uuid
from urllib.parse import unquote
from pathlib import PurePath
from tempfile import SpooledTemporaryFile
from uuid import UUID
from fastapi import APIRouter,File,Header,Query,Request,UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import and_,func,or_,select
from server.app.identity.models import AuditLog,Job
from server.app.recruiting.api import AUTH,_denied,_idempotency,_job_scope,_load_job,_principal,_problem_for
from server.app.recruiting.authorization import RecruitingAction
from server.app.recruiting.models import FileObject,IdempotencyRecord,JobJdVersion,ScreeningRuleVersion
from server.app.recruiting.service import IdempotencyConflict,persisted_idempotent
from server.app.screening.models import CandidateDuplicateHint,ScreeningItem,ScreeningRun
from server.app.screening.parsers import ParserError,ParserLimits,validate_upload_preflight
from server.app.screening.schemas import ItemCollection,ItemResource,RunCreate,RunResource
from server.app.screening.storage import StorageWriteFailed

router=APIRouter(prefix="/api/v1"); _SAFE_STATUS={"queued","parsing","parsed","scoring","scored","failed","cancelled"}
def _response(data,status=200):
    response=JSONResponse({"data":data},status_code=status); response.headers["Cache-Control"]="no-store"; return response
def _problem(request,status,code):
    from server.app.identity.api import problem
    response=problem(request,status,code,"The request could not be completed."); response.headers["Cache-Control"]="no-store"; return response
def _not_found(request): return _problem(request,404,"resource_not_found")
def _run_data(run): return {"id":str(run.id),"job_id":str(run.job_id),"jd_version_id":str(run.jd_version_id),"rule_version_id":str(run.rule_version_id),"source":run.source,"status":run.status,"total_count":run.total_count,"processed_count":run.processed_count,"succeeded_count":run.succeeded_count,"failed_count":run.failed_count,"version":run.version,"created_at":run.created_at.isoformat()}
def _item_data(item,file): return {"id":str(item.id),"run_id":str(item.run_id),"filename":file.original_filename,"mime_type":file.mime_type,"size_bytes":file.size_bytes,"status":item.status,"parser_version":item.parser_version,"parse_quality":item.parse_quality,"error_code":item.safe_error_code,"attempts":item.attempts,"created_at":item.created_at.isoformat()}
def _load_run(db,principal,run_id,action=RecruitingAction.READ,lock=False):
    query=select(ScreeningRun).join(Job,and_(Job.organization_id==ScreeningRun.organization_id,Job.id==ScreeningRun.job_id)).where(ScreeningRun.organization_id==principal.organization_id,ScreeningRun.id==run_id,_job_scope(principal,action))
    return db.scalar(query.with_for_update() if lock else query)
def _filename(value,extension):
    name=PurePath(unquote(value or "").replace("\\","/")).name; name=re.sub(r"[\x00-\x1f\x7f]","",name).strip().replace("..",".")
    if not name: name=f"resume{extension}"
    if len(name)>200: name=name[:200-len(extension)].rstrip(".")+extension
    return name
def _limits(settings): return ParserLimits(max_source_bytes=settings.parser_max_source_bytes,max_text_chars=settings.parser_max_text_chars,pdf_max_pages=settings.parser_pdf_max_pages,docx_max_entries=settings.parser_docx_max_entries,docx_max_uncompressed_bytes=settings.parser_docx_max_uncompressed_bytes,docx_max_compression_ratio=settings.parser_docx_max_compression_ratio)
def _audit_rejection(request,principal,run_id,code):
    with request.app.state.identity_store.sync_session() as audit_db:
        run=_load_run(audit_db,principal,run_id,RecruitingAction.MANAGE_JOB)
        if run:
            audit_db.add(AuditLog(organization_id=principal.organization_id,actor_user_id=principal.user_id,event_type="screening.item_rejected",outcome="failure",trace_id=request.state.trace_id,metadata_json={"run_id":str(run_id),"safe_error_code":code})); audit_db.commit()

@router.post("/jobs/{job_id}/screening-runs",response_model=RunResource,status_code=201)
def create_run(job_id:UUID,payload:RunCreate,request:Request,idempotency_key:str|None=Header(None)):
    principal=_principal(request); key=_idempotency(request,idempotency_key)
    if isinstance(principal,JSONResponse): return principal
    if isinstance(key,JSONResponse): return key
    with request.app.state.identity_store.sync_session() as db:
        if _load_job(db,principal,job_id,RecruitingAction.MANAGE_JOB) is None: return _not_found(request)
        try:
            def action():
                jd=db.scalar(select(JobJdVersion).where(JobJdVersion.organization_id==principal.organization_id,JobJdVersion.job_id==job_id,*( [JobJdVersion.id==UUID(payload.jd_version_id)] if payload.jd_version_id else [])).order_by(JobJdVersion.version_number.desc()))
                rule=db.scalar(select(ScreeningRuleVersion).where(ScreeningRuleVersion.organization_id==principal.organization_id,ScreeningRuleVersion.job_id==job_id,*( [ScreeningRuleVersion.id==UUID(payload.rule_version_id)] if payload.rule_version_id else [])).order_by(ScreeningRuleVersion.version_number.desc()))
                if not jd or not rule: raise ValueError("version_mismatch")
                run=ScreeningRun(organization_id=principal.organization_id,job_id=job_id,jd_version_id=jd.id,rule_version_id=rule.id,source=payload.source,status="queued",total_count=0,processed_count=0,succeeded_count=0,failed_count=0,created_by=principal.user_id); db.add(run); db.flush(); db.add(AuditLog(organization_id=principal.organization_id,actor_user_id=principal.user_id,event_type="screening.run_created",outcome="success",trace_id=request.state.trace_id,metadata_json={"run_id":str(run.id),"job_id":str(job_id)})); return 201,{"data":_run_data(run)}
            status,body=persisted_idempotent(db,principal.organization_id,principal.user_id,"screening.run.create",key,{"job_id":str(job_id),**payload.model_dump()},action); db.commit(); response=JSONResponse(body,status_code=status); response.headers["Cache-Control"]="no-store"; return response
        except IdempotencyConflict: db.rollback(); return _problem(request,409,"idempotency_conflict")
        except Exception: db.rollback(); return _problem(request,422,"version_mismatch")

@router.post("/screening-runs/{run_id}/items",response_model=ItemResource,status_code=201)
def upload_item(run_id:UUID,request:Request,file:UploadFile=File(...),idempotency_key:str|None=Header(None)):
    principal=_principal(request); key=_idempotency(request,idempotency_key)
    if isinstance(principal,JSONResponse): return principal
    if isinstance(key,JSONResponse): return key
    extension=PurePath(file.filename or "").suffix.lower(); limits=_limits(request.app.state.settings); spool=SpooledTemporaryFile(max_size=min(limits.max_source_bytes,1024*1024),mode="w+b"); digest=hashlib.sha256(); size=0
    try:
        while chunk:=file.file.read(64*1024):
            size+=len(chunk)
            if size>limits.max_source_bytes: raise ParserError("file_too_large")
            digest.update(chunk); spool.write(chunk)
        spool.seek(0); detected=validate_upload_preflight(spool,extension=extension,mime_type=file.content_type or "",limits=limits); display=_filename(file.filename,extension); sha=digest.hexdigest()
    except ParserError as error: spool.close(); _audit_rejection(request,principal,run_id,error.safe_code); return _problem(request,422,error.safe_code)
    storage_key=None
    with request.app.state.identity_store.sync_session() as db:
        run=_load_run(db,principal,run_id,RecruitingAction.MANAGE_JOB,lock=True)
        if run is None: spool.close(); return _not_found(request)
        try:
            fingerprint={"run_id":str(run_id),"filename":display,"mime":file.content_type,"size":size,"sha256":sha}
            def action():
                nonlocal storage_key
                if run.status!="queued": raise ValueError("run_not_queued")
                if run.total_count>=100: raise OverflowError("item_limit")
                object_id=uuid.uuid4(); storage_key=f"quarantine/{principal.organization_id}/{run_id}/{object_id}"
                spool.seek(0); request.app.state.quarantine_storage.write(spool,storage_key,file.content_type,limits.max_source_bytes)
                duplicate=db.scalar(select(FileObject.id).where(FileObject.organization_id==principal.organization_id,FileObject.sha256==sha).limit(1))
                stored=FileObject(id=object_id,organization_id=principal.organization_id,storage_key=storage_key,original_filename=display,mime_type=file.content_type,size_bytes=size,sha256=sha,uploaded_by=principal.user_id,storage_state="quarantine",detected_type=detected,scan_status="pending"); db.add(stored); db.flush(); item=ScreeningItem(organization_id=principal.organization_id,run_id=run.id,file_object_id=stored.id,status="queued",attempts=0); db.add(item); run.total_count+=1; run.version+=1; db.flush()
                if duplicate: db.add(CandidateDuplicateHint(organization_id=principal.organization_id,file_object_id=stored.id,signals={"same_sha":True},status="pending"))
                db.add(AuditLog(organization_id=principal.organization_id,actor_user_id=principal.user_id,event_type="screening.item_accepted",outcome="success",trace_id=request.state.trace_id,metadata_json={"run_id":str(run.id),"item_id":str(item.id)})); return 201,{"data":_item_data(item,stored)}
            status,body=persisted_idempotent(db,principal.organization_id,principal.user_id,"screening.item.upload",key,fingerprint,action); db.commit(); response=JSONResponse(body,status_code=status); response.headers["Cache-Control"]="no-store"; return response
        except IdempotencyConflict: db.rollback(); return _problem(request,409,"idempotency_conflict")
        except OverflowError: db.rollback(); return _problem(request,409,"screening_item_limit")
        except StorageWriteFailed: db.rollback(); _audit_rejection(request,principal,run_id,"storage_write_failed"); return _problem(request,503,"storage_write_failed")
        except Exception:
            db.rollback()
            if storage_key: request.app.state.quarantine_storage.delete(storage_key)
            return _problem(request,409,"invalid_state_transition")
        finally: spool.close()

@router.get("/screening-runs/{run_id}",response_model=RunResource)
def get_run(run_id:UUID,request:Request):
    principal=_principal(request)
    if isinstance(principal,JSONResponse): return principal
    with request.app.state.identity_store.sync_session() as db:
        run=_load_run(db,principal,run_id); return _not_found(request) if run is None else _response(_run_data(run))

@router.get("/screening-runs/{run_id}/items",response_model=ItemCollection)
def list_items(run_id:UUID,request:Request,status:str|None=None,cursor:str|None=None,limit:int=Query(50,ge=1,le=100)):
    principal=_principal(request)
    if isinstance(principal,JSONResponse): return principal
    if status and status not in _SAFE_STATUS: return _problem(request,422,"validation_failed")
    with request.app.state.identity_store.sync_session() as db:
        run=_load_run(db,principal,run_id)
        if run is None: return _not_found(request)
        query=select(ScreeningItem,FileObject).join(FileObject,and_(FileObject.organization_id==ScreeningItem.organization_id,FileObject.id==ScreeningItem.file_object_id)).where(ScreeningItem.organization_id==principal.organization_id,ScreeningItem.run_id==run.id)
        if status: query=query.where(ScreeningItem.status==status)
        if cursor:
            try:
                decoded=request.app.state.recruiting_cursor.decode(cursor,str(principal.organization_id),f"screening-items:{run_id}"); query=query.where(ScreeningItem.id>UUID(decoded["id"]))
            except Exception: return _problem(request,422,"validation_failed")
        rows=db.execute(query.order_by(ScreeningItem.id).limit(limit+1)).all(); next_cursor=None
        if len(rows)>limit: next_cursor=request.app.state.recruiting_cursor.encode(str(principal.organization_id),f"screening-items:{run_id}","0",str(rows[limit-1][0].id)); rows=rows[:limit]
        response=JSONResponse({"data":[_item_data(item,stored) for item,stored in rows],"meta":{"limit":limit,"next_cursor":next_cursor}}); response.headers["Cache-Control"]="no-store"; return response
