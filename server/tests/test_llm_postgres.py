import os,subprocess,uuid
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.exc import DBAPIError,IntegrityError

pytestmark=pytest.mark.skipif(not os.getenv("POSTGRES_SMOKE_URL"),reason="PostgreSQL smoke URL not configured")
def test_llm_tables_are_tenant_scoped_and_evidence_is_append_only():
    url=os.environ["POSTGRES_SMOKE_URL"]; subprocess.run(["python","-m","alembic","-c","server/alembic.ini","upgrade","head"],check=True,env={**os.environ,"DATABASE_URL":url}); engine=create_engine(url.replace("+asyncpg","+psycopg")); ids={name:uuid.uuid4() for name in ("o1","o2","u1","u2","config","prompt","invocation")}
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE organizations CASCADE")); connection.execute(text("INSERT INTO organizations(id,slug,name,status,created_at,updated_at) VALUES(:o1,'one','One','active',now(),now()),(:o2,'two','Two','active',now(),now())"),ids); connection.execute(text("INSERT INTO users(id,organization_id,email,normalized_email,display_name,password_hash,status,authorization_version,created_at,updated_at) VALUES(:u1,:o1,'a@x','a@x','A','x','active',1,now(),now()),(:u2,:o2,'b@x','b@x','B','x','active',1,now(),now())"),ids)
        connection.execute(text("INSERT INTO llm_provider_configs(id,organization_id,provider_id,model,encrypted_api_key,enabled,allowed_job_ids,version,created_by,updated_by,created_at,updated_at) VALUES(:config,:o1,'approved','model',decode('00','hex'),false,'[]',1,:u1,:u1,now(),now())"),ids)
        connection.execute(text("INSERT INTO prompt_versions(id,organization_id,name,version_number,content,content_hash,created_by,created_at) VALUES(:prompt,:o1,'screen',1,'{}',repeat('0',64),:u1,now())"),ids)
        connection.execute(text("INSERT INTO llm_invocations(id,organization_id,config_id,prompt_version_id,provider_id,model,request_field_manifest,status,usage,created_at) VALUES(:invocation,:o1,:config,:prompt,'approved','model','[]','queued','{}',now())"),ids)
    for statement,error in (("INSERT INTO llm_invocations(id,organization_id,config_id,provider_id,model,request_field_manifest,status,usage,created_at) VALUES(gen_random_uuid(),:o2,:config,'approved','model','[]','queued','{}',now())",IntegrityError),("UPDATE prompt_versions SET content='{}' WHERE id=:prompt",DBAPIError),("DELETE FROM llm_invocations WHERE id=:invocation",DBAPIError)):
        with engine.connect() as connection:
            transaction=connection.begin()
            with pytest.raises(error): connection.execute(text(statement),ids)
            transaction.rollback()
    engine.dispose()
