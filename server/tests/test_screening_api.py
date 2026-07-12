import io
import uuid
from datetime import datetime,timedelta,timezone
from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from server.app.core.settings import Settings
from server.app.identity.models import Job, JobCollaborator, Organization, User, UserRole
from server.app.identity.security import PasswordService
from server.app.main import create_app
from server.app.recruiting.models import JobJdVersion, ScreeningRuleVersion
from server.app.screening.storage import StorageWriteFailed
from server.app.screening.models import ScreeningItem

class Probe:
    async def check(self): pass

@dataclass
class FakeQuarantineStorage:
    objects: dict[str,bytes]=field(default_factory=dict); writes:int=0; deletes:int=0
    fail:bool=False
    def write(self, stream, storage_key, content_type, max_bytes):
        if self.fail: raise StorageWriteFailed("storage_write_failed")
        data=b""; size=0
        while chunk:=stream.read(3):
            size+=len(chunk)
            if size>max_bytes: raise ValueError("file_too_large")
            data+=chunk
        self.objects[storage_key]=data; self.writes+=1
    def delete(self, storage_key): self.objects.pop(storage_key,None); self.deletes+=1

def app_and_seed(tmp_path):
    storage=FakeQuarantineStorage(); app=create_app(settings=Settings(environment="test",database_url=f"sqlite+aiosqlite:///{tmp_path/'screening.db'}",cors_origins=["https://hr.example.test"]),database_probe=Probe(),storage_probe=Probe(),initialize_identity_schema=True,quarantine_storage=storage)
    app.state.identity_store.create_schema()
    with app.state.identity_store.sync_session() as db:
        org=Organization(slug="acme",name="Acme",status="active"); admin=User(organization=org,email="admin@example.test",normalized_email="admin@example.test",display_name="Admin",password_hash=PasswordService().hash("correct")); admin.roles.append(UserRole(role="recruiting_admin")); system=User(organization=org,email="system@example.test",normalized_email="system@example.test",display_name="System",password_hash=PasswordService().hash("correct")); system.roles.append(UserRole(role="system_admin")); manager=User(organization=org,email="manager@example.test",normalized_email="manager@example.test",display_name="Manager",password_hash=PasswordService().hash("correct")); manager.roles.append(UserRole(role="hiring_manager")); db.add_all([admin,system,manager]); db.flush(); job=Job(organization_id=org.id,title="Engineer",owner_id=admin.id,status="draft"); db.add(job); db.flush(); db.add(JobCollaborator(organization_id=org.id,job_id=job.id,user_id=manager.id,access_role="job_manager")); jd=JobJdVersion(organization_id=org.id,job_id=job.id,version_number=1,content={"text":"required: Python"},created_by=admin.id); rule=ScreeningRuleVersion(organization_id=org.id,job_id=job.id,version_number=1,content={},created_by=admin.id); db.add_all([jd,rule]); db.commit(); return app,storage,job.id

def login(client,email):
    response=client.post("/api/v1/auth/login",json={"organization_slug":"acme","email":email,"password":"correct"},headers={"Origin":"https://hr.example.test"}); assert response.status_code==200; return {"Origin":"https://hr.example.test","X-CSRF-Token":response.headers["X-CSRF-Token"]}

def test_screening_api_create_upload_read_replay_and_scope(tmp_path):
    app,storage,job_id=app_and_seed(tmp_path)
    with TestClient(app) as client:
        headers=login(client,"admin@example.test"); headers["Idempotency-Key"]="run-1"
        created=client.post(f"/api/v1/jobs/{job_id}/screening-runs",json={},headers=headers); assert created.status_code==201; run=created.json()["data"]
        assert run["status"]=="queued" and run["total_count"]==0 and run["version"]==1
        upload_headers={**headers,"Idempotency-Key":"item-1"}
        uploaded=client.post(f"/api/v1/screening-runs/{run['id']}/items",files={"file":("../ Candidate\n.txt",b"Python 5\xe5\xb9\xb4","text/plain")},headers=upload_headers); assert uploaded.status_code==201; item=uploaded.json()["data"]
        assert item["filename"]=="Candidate.txt" and item["status"]=="queued" and "storage_key" not in item and "sha256" not in item
        replay=client.post(f"/api/v1/screening-runs/{run['id']}/items",files={"file":("../ Candidate\n.txt",b"Python 5\xe5\xb9\xb4","text/plain")},headers=upload_headers); assert replay.status_code==201 and replay.json()==uploaded.json() and storage.writes==1
        conflict=client.post(f"/api/v1/screening-runs/{run['id']}/items",files={"file":("other.txt",b"Different","text/plain")},headers=upload_headers); assert conflict.status_code==409 and conflict.json()["code"]=="idempotency_conflict"
        assert storage.writes==1
        second=client.post(f"/api/v1/screening-runs/{run['id']}/items",files={"file":(("x"*250)+".txt",b"second","text/plain")},headers={**headers,"Idempotency-Key":"item-2"}); assert second.status_code==201 and len(second.json()["data"]["filename"])<=200
        detail=client.get(f"/api/v1/screening-runs/{run['id']}",headers=headers); assert detail.status_code==200 and detail.json()["data"]["total_count"]==2
        listing=client.get(f"/api/v1/screening-runs/{run['id']}/items?status=queued&limit=1",headers=headers); assert listing.status_code==200 and listing.json()["meta"]["next_cursor"]
        page2=client.get(f"/api/v1/screening-runs/{run['id']}/items?status=queued&limit=1&cursor={listing.json()['meta']['next_cursor']}",headers=headers); assert page2.status_code==200 and page2.json()["data"][0]["id"]!=listing.json()["data"][0]["id"]
        client.post("/api/v1/auth/logout",headers=headers); denied=login(client,"system@example.test"); denied["Idempotency-Key"]="denied"; assert client.post(f"/api/v1/jobs/{job_id}/screening-runs",json={},headers=denied).status_code==404
        client.post("/api/v1/auth/logout",headers=denied); manager=login(client,"manager@example.test"); assert client.get(f"/api/v1/screening-runs/{run['id']}",headers=manager).status_code==200; manager["Idempotency-Key"]="read-only"; unauthorized=client.post(f"/api/v1/screening-runs/{run['id']}/items",files={"file":("x.pdf",b"not-a-pdf","application/pdf")},headers=manager); assert unauthorized.status_code==404 and storage.writes==2

def test_screening_upload_rejects_empty_and_magic_mismatch_without_storage(tmp_path):
    app,storage,job_id=app_and_seed(tmp_path)
    with TestClient(app) as client:
        headers=login(client,"admin@example.test"); headers["Idempotency-Key"]="run"; run=client.post(f"/api/v1/jobs/{job_id}/screening-runs",json={},headers=headers).json()["data"]
        for key,name,data,mime,code in (("empty","x.txt",b"","text/plain","empty_file"),("magic","x.pdf",b"not pdf","application/pdf","file_magic_mismatch")):
            response=client.post(f"/api/v1/screening-runs/{run['id']}/items",files={"file":(name,data,mime)},headers={**headers,"Idempotency-Key":key}); assert response.status_code==422 and response.json()["code"]==code
        assert storage.writes==0

def test_screening_upload_exact_size_boundary_and_storage_failure(tmp_path):
    app,storage,job_id=app_and_seed(tmp_path); app.state.settings.parser_max_source_bytes=1024
    with TestClient(app) as client:
        headers=login(client,"admin@example.test"); headers["Idempotency-Key"]="run"; run=client.post(f"/api/v1/jobs/{job_id}/screening-runs",json={},headers=headers).json()["data"]
        exact=client.post(f"/api/v1/screening-runs/{run['id']}/items",files={"file":("x.txt",b"x"*1024,"text/plain")},headers={**headers,"Idempotency-Key":"exact"}); assert exact.status_code==201
        over=client.post(f"/api/v1/screening-runs/{run['id']}/items",files={"file":("x.txt",b"x"*1025,"text/plain")},headers={**headers,"Idempotency-Key":"over"}); assert over.status_code==422 and over.json()["code"]=="file_too_large"
        storage.fail=True; failed=client.post(f"/api/v1/screening-runs/{run['id']}/items",files={"file":("y.txt",b"safe","text/plain")},headers={**headers,"Idempotency-Key":"storage"}); assert failed.status_code==503 and failed.json()["code"]=="storage_write_failed" and storage.deletes==1

def test_database_failure_deletes_new_quarantine_object(tmp_path,monkeypatch):
    app,storage,job_id=app_and_seed(tmp_path)
    with TestClient(app) as client:
        headers=login(client,"admin@example.test"); run=client.post(f"/api/v1/jobs/{job_id}/screening-runs",json={},headers={**headers,"Idempotency-Key":"run"}).json()["data"]
        monkeypatch.setattr("server.app.screening.api.ScreeningItem",lambda **_: (_ for _ in ()).throw(RuntimeError("db failed with resume text")))
        response=client.post(f"/api/v1/screening-runs/{run['id']}/items",files={"file":("x.txt",b"private resume","text/plain")},headers={**headers,"Idempotency-Key":"db-fail"})
        assert response.status_code==503 and response.json()["code"]=="persistence_failed" and storage.writes==1 and storage.deletes==1 and storage.objects=={}

def test_run_create_schema_rejects_bad_uuid_and_source(tmp_path):
    app,_,job_id=app_and_seed(tmp_path)
    with TestClient(app) as client:
        headers=login(client,"admin@example.test"); headers["Idempotency-Key"]="bad"
        for body in ({"jd_version_id":"not-a-uuid"},{"source":"worker"}):
            assert client.post(f"/api/v1/jobs/{job_id}/screening-runs",json=body,headers=headers).status_code==422

def test_screening_item_cursor_is_created_at_id_keyset_with_between_page_insert(tmp_path):
    app,_,job_id=app_and_seed(tmp_path)
    with TestClient(app) as client:
        headers=login(client,"admin@example.test"); run=client.post(f"/api/v1/jobs/{job_id}/screening-runs",json={},headers={**headers,"Idempotency-Key":"run"}).json()["data"]
        ids=[]
        for key in ("first","second"):
            ids.append(client.post(f"/api/v1/screening-runs/{run['id']}/items",files={"file":(f"{key}.txt",key.encode(),"text/plain")},headers={**headers,"Idempotency-Key":key}).json()["data"]["id"])
        with app.state.identity_store.sync_session() as db:
            first=db.get(ScreeningItem,uuid.UUID(ids[0])); second=db.get(ScreeningItem,uuid.UUID(ids[1])); first.id=uuid.UUID(int=2**128-2); second.id=uuid.UUID(int=1); first.created_at=datetime.now(timezone.utc)-timedelta(seconds=2); second.created_at=first.created_at+timedelta(seconds=1); db.commit(); ids=[str(first.id),str(second.id)]
        page1=client.get(f"/api/v1/screening-runs/{run['id']}/items?limit=1",headers=headers); assert page1.json()["data"][0]["id"]==ids[0]
        inserted=client.post(f"/api/v1/screening-runs/{run['id']}/items",files={"file":("third.txt",b"third","text/plain")},headers={**headers,"Idempotency-Key":"third"}).json()["data"]["id"]
        cursor=page1.json()["meta"]["next_cursor"]; page2=client.get(f"/api/v1/screening-runs/{run['id']}/items?limit=10&cursor={cursor}",headers=headers)
        assert [row["id"] for row in page2.json()["data"]]==[ids[1],inserted]
