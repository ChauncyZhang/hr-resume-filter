import uuid
from datetime import datetime,timezone
from pathlib import PurePath
from sqlalchemy import and_,func,select
from server.app.queue.repository import QueueRepository
from server.app.queue.service import PermanentJobError,RetryableJobError
from server.app.recruiting.models import Application,Candidate,FileObject,JobJdVersion,Resume,ScreeningRuleVersion
from server.app.screening.models import ScreeningItem,ScreeningResult,ScreeningRun
from server.app.screening.parsers import ParserLimits
from server.app.screening.isolated_parser import IsolatedParser,IsolatedParserError
from server.app.screening.rules import ENGINE_VERSION,RuleSnapshot,RuleSnapshotError,score_resume
from server.app.screening.scanner import ScanResult
from server.app.screening.storage import StorageWriteFailed

_RETRYABLE={"scanner_unavailable","scanner_error","storage_unavailable"}
def _uuid(item_id,name): return uuid.uuid5(uuid.UUID(str(item_id)),name)

class ScreeningPipeline:
    def __init__(self,sessions,storage,scanner,settings,parser=None): self.sessions,self.storage,self.scanner,self.settings=sessions,storage,scanner,settings; self.parser=parser or IsolatedParser(settings.parser_hard_timeout_seconds)
    def _limits(self):
        s=self.settings; return ParserLimits(s.parser_max_source_bytes,s.parser_max_text_chars,s.parser_pdf_max_pages,s.parser_docx_max_entries,s.parser_docx_max_uncompressed_bytes,s.parser_docx_max_compression_ratio)
    async def parse_item(self,job):
        organization_id=uuid.UUID(str(job.payload["organization_id"])); item_id=uuid.UUID(str(job.payload["screening_item_id"])); limits=self._limits()
        with self.sessions() as db:
            item=db.scalar(select(ScreeningItem).where(ScreeningItem.organization_id==organization_id,ScreeningItem.id==item_id).with_for_update())
            if not item: raise PermanentJobError("screening_item_missing")
            item.attempts=max(item.attempts,getattr(job,"attempts",1)); item.started_at=item.started_at or datetime.now(timezone.utc)
            if item.status in {"parsed","scored","cancelled"} or (item.status=="failed" and item.safe_error_code not in _RETRYABLE): db.commit(); return
            item.status="parsing"; db.commit()
        with self.sessions() as db:
            row=db.execute(select(ScreeningItem,FileObject).join(FileObject,and_(FileObject.organization_id==ScreeningItem.organization_id,FileObject.id==ScreeningItem.file_object_id)).where(ScreeningItem.organization_id==organization_id,ScreeningItem.id==item_id)).one_or_none()
            if not row: raise PermanentJobError("screening_item_missing")
            item,stored=row
            if item.status in {"parsed","scored","cancelled"} or (item.status=="failed" and item.safe_error_code not in _RETRYABLE): return
            key,mime,filename,scan_status=stored.storage_key,stored.mime_type,stored.original_filename,stored.scan_status
        if scan_status!="clean":
            source=None
            try: source=await self.storage.open(key,limits.max_source_bytes); scan=await self.scanner.scan(source,limits.max_source_bytes)
            except StorageWriteFailed as error:
                if error.safe_code=="file_too_large": self._fail_terminal(organization_id,item_id,error.safe_code); return
                return await self._retry_or_finish(job,organization_id,item_id,"storage_unavailable","parse")
            except Exception: return await self._retry_or_finish(job,organization_id,item_id,"storage_unavailable","parse")
            finally:
                if source is not None: source.close()
            if scan==ScanResult.INFECTED:
                self._fail_terminal(organization_id,item_id,"malware_detected",file_state=("rejected","rejected")); await self.storage.delete(key); return
            if scan!=ScanResult.CLEAN: return await self._retry_or_finish(job,organization_id,item_id,"scanner_unavailable" if scan==ScanResult.UNAVAILABLE else "scanner_error","parse")
            clean_key=f"clean/{organization_id}/{stored.id}"
            try: await self.storage.copy(key,clean_key,limits.max_source_bytes)
            except Exception: return await self._retry_or_finish(job,organization_id,item_id,"storage_unavailable","parse")
            with self.sessions() as db:
                current=db.scalar(select(FileObject).where(FileObject.organization_id==organization_id,FileObject.id==stored.id).with_for_update()); current.storage_key=clean_key; current.storage_state="clean"; current.scan_status="clean"; current.quarantine_cleanup_key=key; db.commit()
            deleted=await self.storage.delete(key)
            if deleted:
                with self.sessions() as db:
                    current=db.scalar(select(FileObject).where(FileObject.organization_id==organization_id,FileObject.id==stored.id).with_for_update()); current.quarantine_cleanup_key=None; db.commit()
            key=clean_key
        stream=None
        try:
            stream=await self.storage.open(key,limits.max_source_bytes)
            parsed=await self.parser.parse(stream,extension=PurePath(filename).suffix,mime_type=mime,limits=limits)
        except StorageWriteFailed as error:
            if error.safe_code=="file_too_large": self._fail_terminal(organization_id,item_id,error.safe_code); return
            return await self._retry_or_finish(job,organization_id,item_id,"storage_unavailable","parse")
        except IsolatedParserError as error: self._fail_terminal(organization_id,item_id,error.safe_code); return
        except Exception: return await self._retry_or_finish(job,organization_id,item_id,"storage_unavailable","parse")
        finally:
            if stream is not None: stream.close()
        with self.sessions() as db:
            item=db.scalar(select(ScreeningItem).where(ScreeningItem.organization_id==organization_id,ScreeningItem.id==item_id).with_for_update())
            if item.status in {"parsed","scored"}: return
            run=db.scalar(select(ScreeningRun).where(ScreeningRun.organization_id==organization_id,ScreeningRun.id==item.run_id))
            candidate_id,resume_id,application_id=_uuid(item.id,"candidate"),_uuid(item.id,"resume"),_uuid(item.id,"application")
            candidate=db.get(Candidate,candidate_id) or Candidate(id=candidate_id,organization_id=organization_id,display_name=(PurePath(filename).stem[:200] or "Candidate"),owner_id=run.created_by)
            if candidate not in db: db.add(candidate)
            resume=db.get(Resume,resume_id) or Resume(id=resume_id,organization_id=organization_id,candidate_id=candidate_id,file_object_id=item.file_object_id,version_number=1,parsed_text=parsed.text)
            if resume not in db: db.add(resume)
            application=db.get(Application,application_id) or Application(id=application_id,organization_id=organization_id,candidate_id=candidate_id,job_id=run.job_id,resume_id=resume_id,owner_id=run.created_by,stage="new",source="screening")
            if application not in db: db.add(application)
            item.candidate_id=candidate_id; item.resume_id=resume_id; item.application_id=application_id; item.status="parsed"; item.parser_version=parsed.parser_version; item.parse_quality=parsed.quality; item.safe_error_code=None
            QueueRepository(db).enqueue(organization_id,"screening.score_item",{"organization_id":str(organization_id),"screening_item_id":str(item.id),"jd_version_id":str(run.jd_version_id),"rule_version_id":str(run.rule_version_id),"rule_engine_version":ENGINE_VERSION},dedupe_key=f"score:{item.id}",trace_id=getattr(job,"trace_id",None),max_attempts=3); run.status="rule_scoring"; db.commit()
    async def score_item(self,job):
        organization_id=uuid.UUID(str(job.payload["organization_id"])); item_id=uuid.UUID(str(job.payload["screening_item_id"]))
        with self.sessions() as db:
            item=db.scalar(select(ScreeningItem).where(ScreeningItem.organization_id==organization_id,ScreeningItem.id==item_id).with_for_update())
            if not item: raise PermanentJobError("screening_item_missing")
            if item.status in {"scored","failed","cancelled"}: return
            item.status="scoring"; db.commit()
        with self.sessions() as db:
            row=db.execute(select(ScreeningItem,ScreeningRun,Resume,JobJdVersion,ScreeningRuleVersion).join(ScreeningRun,and_(ScreeningRun.organization_id==ScreeningItem.organization_id,ScreeningRun.id==ScreeningItem.run_id)).join(Resume,and_(Resume.organization_id==ScreeningItem.organization_id,Resume.id==ScreeningItem.resume_id)).join(JobJdVersion,and_(JobJdVersion.organization_id==ScreeningRun.organization_id,JobJdVersion.id==ScreeningRun.jd_version_id)).join(ScreeningRuleVersion,and_(ScreeningRuleVersion.organization_id==ScreeningRun.organization_id,ScreeningRuleVersion.id==ScreeningRun.rule_version_id)).where(ScreeningItem.organization_id==organization_id,ScreeningItem.id==item_id)).one_or_none()
            if not row: raise PermanentJobError("screening_item_missing")
            item,run,resume,jd,rule=row
            text=resume.parsed_text or ""
            try:
                if not isinstance(jd.content,dict): raise RuleSnapshotError
                jd_text=jd.content.get("text",jd.content.get("jd_text","")); snapshot=RuleSnapshot.from_content(jd_text,rule.content)
            except RuleSnapshotError:
                self._fail_terminal(organization_id,item_id,"rule_snapshot_invalid"); raise PermanentJobError("rule_snapshot_invalid") from None
        try: result=score_resume(text,snapshot)
        except Exception: return await self._retry_or_finish(job,organization_id,item_id,"scoring_failed","score")
        with self.sessions() as db:
            item=db.scalar(select(ScreeningItem).where(ScreeningItem.organization_id==organization_id,ScreeningItem.id==item_id).with_for_update()); run=db.scalar(select(ScreeningRun).where(ScreeningRun.organization_id==organization_id,ScreeningRun.id==item.run_id).with_for_update())
            existing=db.scalar(select(ScreeningResult).where(ScreeningResult.organization_id==organization_id,ScreeningResult.item_id==item.id,ScreeningResult.rule_engine_version==result.engine_version))
            if not existing: db.add(ScreeningResult(organization_id=organization_id,item_id=item.id,application_id=item.application_id,resume_id=item.resume_id,rule_engine_version=result.engine_version,rule_score=result.score,recommendation=result.recommendation,required_hits=result.required_hits,required_missing=result.required_missing,bonus_hits=result.bonus_hits,estimated_years=result.estimated_years,risks=result.risks,questions=result.questions))
            item.status="scored"; item.safe_error_code=None; item.finished_at=item.finished_at or datetime.now(timezone.utc); self._aggregate(db,run); db.commit()
    async def _retry_or_finish(self,job,organization_id,item_id,code,stage):
        final=getattr(job,"attempts",1)>=getattr(job,"max_attempts",3)
        with self.sessions() as db:
            item=db.scalar(select(ScreeningItem).where(ScreeningItem.organization_id==organization_id,ScreeningItem.id==item_id).with_for_update()); item.status="failed" if final else "queued" if stage=="parse" else "parsed"; item.safe_error_code=code
            if stage=="parse": item.attempts=max(item.attempts,getattr(job,"attempts",1))
            if final: item.finished_at=item.finished_at or datetime.now(timezone.utc); self._aggregate(db,db.get(ScreeningRun,item.run_id))
            db.commit()
        if final: raise PermanentJobError(code)
        raise RetryableJobError(code)
    def _fail_terminal(self,organization_id,item_id,code,file_state=None):
        with self.sessions() as db:
            item=db.scalar(select(ScreeningItem).where(ScreeningItem.organization_id==organization_id,ScreeningItem.id==item_id).with_for_update()); item.status="failed"; item.safe_error_code=code; item.finished_at=item.finished_at or datetime.now(timezone.utc)
            if file_state:
                stored=db.get(FileObject,item.file_object_id); stored.storage_state,stored.scan_status=file_state
            self._aggregate(db,db.get(ScreeningRun,item.run_id)); db.commit()
    @staticmethod
    def _aggregate(db,run):
        statuses=list(db.scalars(select(ScreeningItem.status).where(ScreeningItem.organization_id==run.organization_id,ScreeningItem.run_id==run.id)))
        succeeded=sum(value=="scored" for value in statuses); failed=sum(value in {"failed","cancelled"} for value in statuses); run.succeeded_count=succeeded; run.failed_count=failed; run.processed_count=succeeded+failed
        if run.processed_count==run.total_count: run.status="completed" if failed==0 else "failed" if succeeded==0 else "partial"
        elif any(value in {"parsed","scoring","scored"} for value in statuses): run.status="rule_scoring"
        else: run.status="parsing"
