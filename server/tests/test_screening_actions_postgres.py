import hashlib
import os
import subprocess

from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select, text

from server.app.core.settings import Settings
from server.app.identity.models import Job, Organization, User, UserRole
from server.app.identity.security import PasswordService
from server.app.main import create_app
from server.app.queue.models import BackgroundJob
from server.app.queue.repository import QueueRepository
from server.app.recruiting.models import FileObject, JobJdVersion, ScreeningRuleVersion
from server.app.screening.models import ScreeningItem, ScreeningRun
from server.tests.test_screening_api import Probe, login


pytestmark = pytest.mark.skipif(not os.getenv("POSTGRES_SMOKE_URL"), reason="PostgreSQL smoke URL not configured")


def test_postgres_concurrent_retry_preserves_history_and_restores_progress_once():
    url = os.environ["POSTGRES_SMOKE_URL"]
    subprocess.run(["python", "-m", "alembic", "-c", "server/alembic.ini", "upgrade", "head"], check=True, env={**os.environ, "DATABASE_URL": url})
    app = create_app(settings=Settings(environment="test", database_url=url, cors_origins=["https://hr.example.test"]), database_probe=Probe(), storage_probe=Probe(), quarantine_storage=object())
    with app.state.identity_store.sync_session() as db:
        db.execute(text("TRUNCATE organizations CASCADE"))
        org = Organization(slug="acme", name="Retry", status="active")
        user = User(organization=org, email="retry@pg.test", normalized_email="retry@pg.test", display_name="Retry", password_hash=PasswordService().hash("correct"))
        user.roles.append(UserRole(role="recruiting_admin")); db.add(user); db.flush()
        job = Job(organization_id=org.id, title="Retry", owner_id=user.id, status="draft"); db.add(job); db.flush()
        jd = JobJdVersion(organization_id=org.id, job_id=job.id, version_number=1, content={}, created_by=user.id)
        rule = ScreeningRuleVersion(organization_id=org.id, job_id=job.id, version_number=1, content={}, created_by=user.id); db.add_all([jd, rule]); db.flush()
        run = ScreeningRun(organization_id=org.id, job_id=job.id, jd_version_id=jd.id, rule_version_id=rule.id, source="upload", status="failed", total_count=1, processed_count=1, succeeded_count=0, failed_count=1, created_by=user.id); db.add(run); db.flush()
        data = b"candidate"
        stored_file = FileObject(organization_id=org.id, storage_key="quarantine/retry", original_filename="candidate.txt", mime_type="text/plain", size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), uploaded_by=user.id, storage_state="quarantine", detected_type="txt", scan_status="pending"); db.add(stored_file); db.flush()
        item = ScreeningItem(organization_id=org.id, run_id=run.id, file_object_id=stored_file.id, status="failed", safe_error_code="scanner_unavailable", attempts=3, finished_at=run.created_at); db.add(item); db.flush()
        prior = QueueRepository(db).enqueue(org.id, "screening.parse_item", {"organization_id": str(org.id), "screening_item_id": str(item.id), "parser_version": "parser-v1"}, dedupe_key=f"parse:{item.id}", max_attempts=3)
        prior.status = "dead_letter"; prior.attempts = 3; db.commit(); item_id, run_id, prior_id = item.id, run.id, prior.id

    with TestClient(app) as client:
        headers = login(client, "retry@pg.test")
        def retry(key):
            return client.post(f"/api/v1/screening-items/{item_id}/retry", headers={**headers, "Idempotency-Key": key})
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(retry, ("retry-a", "retry-b")))
        assert sorted(response.status_code for response in responses) == [200, 409]

    with app.state.identity_store.sync_session() as db:
        aggregate = db.get(ScreeningRun, run_id); retried = db.get(ScreeningItem, item_id)
        assert aggregate.processed_count == 0 and aggregate.failed_count == 0
        assert retried.status == "queued" and retried.safe_error_code is None and retried.attempts == 3
        assert db.get(BackgroundJob, prior_id).status == "dead_letter"
        assert db.scalar(select(func.count(BackgroundJob.id)).where(BackgroundJob.dedupe_key == f"parse:{item_id}")) == 2
        assert db.scalar(select(func.count(BackgroundJob.id)).where(BackgroundJob.dedupe_key == f"parse:{item_id}", BackgroundJob.status == "queued")) == 1
