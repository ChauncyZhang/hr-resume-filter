import asyncio
import uuid
from datetime import datetime,timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from server.app.llm.gateway import GatewayError
from server.app.llm.models import LlmInvocation, LlmProviderConfig, LlmScreeningEvaluation
from server.app.llm.screening import MAX_RESUME_CHARS,ScreeningEvaluation, ScreeningResult
from server.app.queue.models import BackgroundJob
from server.app.queue.service import PermanentJobError, RetryableJobError
from server.app.recruiting.models import Application, ApplicationStageEvent, JobJdVersion, Resume
from server.app.screening.llm_pipeline import LlmScreeningPipeline
from server.app.screening.terminal import finalize_llm_dead_letter
from server.app.screening.models import ScreeningItem, ScreeningResult as RuleResult, ScreeningRun
from server.app.llm.security import ApiKeyCipher
from server.tests.test_screening_pipeline import seeded_pipeline
from server.tests.test_screening_api import login


class Gateway:
    def __init__(self, outcome=None, inspect=None):
        self.outcome = outcome or ScreeningEvaluation(
            ScreeningResult(
                score=91,
                recommendation="优先沟通",
                summary="Strong Python match",
                strengths=["Python services"],
                gaps=[],
                risks=["Confirm availability"],
                questions=["Describe a scaling incident"],
            ),
            17,
            {"total_tokens": 42},
        )
        self.inspect = inspect
        self.calls = []

    async def evaluate(self, provider_id, model, api_key, request):
        if self.inspect:
            self.inspect()
        self.calls.append((provider_id, model, api_key, request))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def prepared(tmp_path, *, allowed_job_ids=None):
    app, rule_pipeline, _storage, _scanner, parse_job, run, item = seeded_pipeline(tmp_path)
    asyncio.run(rule_pipeline.parse_item(parse_job))
    cipher = ApiKeyCipher(b"ICEiIyQlJicoKSorLC0uLzAxMjM0NTY3ODk6Ozw9Pj8=")
    with app.state.identity_store.sync_session() as db:
        stored = db.get(ScreeningItem, uuid.UUID(item["id"]))
        aggregate = db.get(ScreeningRun, uuid.UUID(run["id"]))
        config = LlmProviderConfig(
            organization_id=stored.organization_id,
            provider_id="approved",
            model="model",
            encrypted_api_key=cipher.encrypt("sk-private"),
            enabled=True,
            allowed_job_ids=allowed_job_ids or [],
            version=3,
            created_by=aggregate.created_by,
            updated_by=aggregate.created_by,
        )
        db.add(config)
        db.commit()
        score_job = SimpleNamespace(
            payload={
                "organization_id": str(stored.organization_id),
                "screening_item_id": str(stored.id),
                "jd_version_id": str(aggregate.jd_version_id),
                "rule_version_id": str(aggregate.rule_version_id),
                "rule_engine_version": "rule-v1",
            },
            attempts=1,
            max_attempts=3,
            trace_id="rule-trace",
        )
    asyncio.run(rule_pipeline.score_item(score_job))
    with app.state.identity_store.sync_session() as db:
        queue_job = db.scalar(select(BackgroundJob).where(BackgroundJob.type == "screening.llm_score_item"))
        queue_job_id = queue_job.id
        payload = dict(queue_job.payload)
        organization_id = queue_job.organization_id
    job = SimpleNamespace(
        id=queue_job_id,
        organization_id=organization_id,
        payload=payload,
        attempts=1,
        max_attempts=3,
        trace_id="llm-trace",
    )
    return app, cipher, job


def test_success_commits_running_before_provider_and_is_replay_safe(tmp_path):
    app, cipher, job = prepared(tmp_path)
    observed = []

    def inspect():
        with app.state.identity_store.sync_session() as db:
            item = db.get(ScreeningItem, uuid.UUID(job.payload["screening_item_id"]))
            observed.append((item.llm_status, item.llm_attempts))

    gateway = Gateway(inspect=inspect)
    pipeline = LlmScreeningPipeline(app.state.identity_store.sync_session, gateway, cipher)

    asyncio.run(pipeline.evaluate_item(job))
    job.attempts=2
    asyncio.run(pipeline.evaluate_item(job))

    assert observed == [("running", 1)]
    assert len(gateway.calls) == 1
    request = gateway.calls[0][3]
    assert request.candidate_name is None
    assert "@" not in request.provider_content()
    with app.state.identity_store.sync_session() as db:
        item = db.get(ScreeningItem, uuid.UUID(job.payload["screening_item_id"]))
        run = db.get(ScreeningRun, item.run_id)
        invocation = db.scalar(select(LlmInvocation))
        evaluation = db.scalar(select(LlmScreeningEvaluation))
        assert item.status == "scored" and item.llm_status == "succeeded" and item.llm_finished_at and item.finished_at
        assert run.status == "completed" and run.processed_count == 1 and run.finished_at and run.version>=2
        assert db.scalar(select(func.count(LlmInvocation.id))) == 1
        assert db.scalar(select(func.count(LlmScreeningEvaluation.id))) == 1
        assert invocation.status == "succeeded" and invocation.attempt_no == 1
        assert len(invocation.input_sha256) == 64
        assert invocation.request_field_manifest == ["jd", "resume", "rule_facts"]
        assert evaluation.score == 91 and evaluation.interview_questions == ["Describe a scaling incident"]
        persisted = repr((invocation.usage, invocation.safe_error_code, evaluation.summary, evaluation.strengths))
        assert "sk-private" not in persisted and "Python backend role" not in persisted
        assert db.scalar(select(Application)).stage == "new"
        assert db.scalar(select(func.count(ApplicationStageEvent.id))) == 0


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda config, run: setattr(config, "enabled", False), "llm_config_disabled"),
        (lambda config, run: setattr(config, "version", 4), "llm_config_changed"),
        (lambda config, run: setattr(config, "allowed_job_ids", [str(uuid.uuid4())]), "llm_job_not_allowed"),
    ],
)
def test_changed_disabled_or_nonallowed_config_skips_without_provider(tmp_path, change, code):
    app, cipher, job = prepared(tmp_path)
    with app.state.identity_store.sync_session() as db:
        config = db.get(LlmProviderConfig, uuid.UUID(job.payload["config_id"]))
        item = db.get(ScreeningItem, uuid.UUID(job.payload["screening_item_id"]))
        change(config, db.get(ScreeningRun, item.run_id))
        db.commit()
    gateway = Gateway()

    asyncio.run(LlmScreeningPipeline(app.state.identity_store.sync_session, gateway, cipher).evaluate_item(job))

    assert gateway.calls == []
    with app.state.identity_store.sync_session() as db:
        item = db.get(ScreeningItem, uuid.UUID(job.payload["screening_item_id"]))
        invocation = db.scalar(select(LlmInvocation))
        assert item.status == "scored" and item.llm_status == "skipped" and item.llm_safe_error_code == code and item.finished_at
        assert invocation.status == "failed" and invocation.safe_error_code == code
        assert db.get(ScreeningRun, item.run_id).status == "completed"


def test_deleted_config_revokes_call_and_completes_with_rule_result(tmp_path):
    app,cipher,job=prepared(tmp_path); gateway=Gateway()
    with app.state.identity_store.sync_session() as db:
        db.delete(db.get(LlmProviderConfig,uuid.UUID(job.payload["config_id"]))); db.commit()
    asyncio.run(LlmScreeningPipeline(app.state.identity_store.sync_session,gateway,cipher).evaluate_item(job))
    assert gateway.calls==[]
    with app.state.identity_store.sync_session() as db:
        item=db.get(ScreeningItem,uuid.UUID(job.payload["screening_item_id"])); run=db.get(ScreeningRun,item.run_id)
        assert item.status=="scored" and item.llm_status=="skipped" and item.llm_safe_error_code=="llm_config_deleted" and item.finished_at
        assert run.status=="completed" and db.scalar(select(func.count(LlmInvocation.id)))==0


@pytest.mark.parametrize("safe_code", ["provider_unavailable", "provider_quota_or_rate_limited"])
def test_transient_provider_failure_retries_then_exhausts_to_partial(tmp_path, safe_code):
    app, cipher, job = prepared(tmp_path)
    pipeline = LlmScreeningPipeline(app.state.identity_store.sync_session, Gateway(GatewayError(safe_code)), cipher)

    with pytest.raises(RetryableJobError) as retry:
        asyncio.run(pipeline.evaluate_item(job))
    assert retry.value.safe_code == safe_code
    with app.state.identity_store.sync_session() as db:
        item = db.get(ScreeningItem, uuid.UUID(job.payload["screening_item_id"]))
        assert item.status == "scored" and item.llm_status == "queued" and item.llm_finished_at is None
        assert db.get(ScreeningRun, item.run_id).status == "llm_scoring"

    job.attempts = job.max_attempts
    with pytest.raises(PermanentJobError) as exhausted:
        asyncio.run(pipeline.evaluate_item(job))
    assert exhausted.value.safe_code == safe_code
    with app.state.identity_store.sync_session() as db:
        item = db.get(ScreeningItem, uuid.UUID(job.payload["screening_item_id"]))
        assert item.status == "scored" and item.llm_status == "failed" and item.llm_finished_at and item.finished_at
        assert db.get(ScreeningRun, item.run_id).status == "partial"
        assert db.scalar(select(func.count(LlmInvocation.id))) == 2


def test_permanent_provider_failure_is_terminal_and_tenant_payload_cannot_cross_load(tmp_path):
    app, cipher, job = prepared(tmp_path)
    gateway=Gateway(GatewayError("provider_auth_failed")); pipeline = LlmScreeningPipeline(app.state.identity_store.sync_session, gateway, cipher)

    with pytest.raises(PermanentJobError) as failed:
        asyncio.run(pipeline.evaluate_item(job))
    assert failed.value.safe_code == "provider_auth_failed"
    with app.state.identity_store.sync_session() as db:
        item = db.get(ScreeningItem, uuid.UUID(job.payload["screening_item_id"]))
        finalize_llm_dead_letter(db,job,"provider_auth_failed",datetime.now(timezone.utc)); db.commit()
        assert item.status == "scored" and item.llm_status == "failed"
        assert item.llm_safe_error_code=="provider_auth_failed"
        assert db.get(ScreeningRun, item.run_id).status == "partial"

    job.attempts=2
    asyncio.run(pipeline.evaluate_item(job))
    assert len(gateway.calls)==1

    other_tenant_job = SimpleNamespace(**vars(job))
    other_tenant_job.payload = {**job.payload, "organization_id": str(uuid.uuid4())}
    with pytest.raises(PermanentJobError) as missing:
        asyncio.run(LlmScreeningPipeline(app.state.identity_store.sync_session, Gateway(), cipher).evaluate_item(other_tenant_job))
    assert missing.value.safe_code == "screening_item_missing"


def test_request_is_bounded_hashed_after_redaction_and_contains_only_rule_facts(tmp_path):
    app, cipher, job = prepared(tmp_path)
    secret_email = "private@example.test"
    with app.state.identity_store.sync_session() as db:
        item = db.get(ScreeningItem, uuid.UUID(job.payload["screening_item_id"]))
        db.get(Resume, item.resume_id).parsed_text = "r"*(MAX_RESUME_CHARS-5)+secret_email
        run = db.get(ScreeningRun, item.run_id)
        db.get(JobJdVersion, run.jd_version_id).content = {"text": "j" * 20_000}
        result = db.get(RuleResult, uuid.UUID(job.payload["screening_result_id"]))
        result.required_hits = [("a@b.co "*70),*[f"hit-{index}" for index in range(30)]]
        result.required_missing = ["missing-private@example.test"]
        db.commit()
    gateway = Gateway()

    asyncio.run(LlmScreeningPipeline(app.state.identity_store.sync_session, gateway, cipher).evaluate_item(job))

    request = gateway.calls[0][3]
    assert len(request.jd) == 12_000 and len(request.resume) <= 30_000 and "private" not in request.resume and "[REDACTED_EMAIL]" in request.resume
    assert len(request.rule_facts) == 20
    assert all(len(value)<=500 for value in request.rule_facts) and "[REDACTED_EMAIL]" in request.rule_facts[0]
    assert secret_email not in request.provider_content()
    with app.state.identity_store.sync_session() as db:
        invocation = db.scalar(select(LlmInvocation))
        assert invocation.input_sha256 == __import__("hashlib").sha256(request.provider_content().encode()).hexdigest()


def test_screening_items_api_exposes_only_bounded_llm_result(tmp_path):
    app,cipher,job=prepared(tmp_path)
    asyncio.run(LlmScreeningPipeline(app.state.identity_store.sync_session,Gateway(),cipher).evaluate_item(job))
    with app.state.identity_store.sync_session() as db:
        run_id=db.get(ScreeningItem,uuid.UUID(job.payload["screening_item_id"])).run_id
    with TestClient(app) as client:
        headers=login(client,"admin@example.test"); response=client.get(f"/api/v1/screening-runs/{run_id}/items",headers=headers)
    assert response.status_code==200
    item=response.json()["data"][0]
    assert item["llm_status"]=="succeeded" and item["llm_error_code"] is None and item["llm_attempts"]==1
    assert item["llm_evaluation"]=={"score":91,"recommendation":"优先沟通","summary":"Strong Python match","strengths":["Python services"],"gaps":[],"risks":["Confirm availability"],"questions":["Describe a scaling incident"]}
    assert all(value not in response.text for value in ("input_sha256","prompt_version_id","request_field_manifest","sk-private"))


def test_run_api_includes_safe_llm_degradation_summary(tmp_path):
    app,cipher,job=prepared(tmp_path)
    with pytest.raises(PermanentJobError):
        asyncio.run(LlmScreeningPipeline(app.state.identity_store.sync_session,Gateway(GatewayError("provider_auth_failed")),cipher).evaluate_item(job))
    with app.state.identity_store.sync_session() as db:
        run_id=db.get(ScreeningItem,uuid.UUID(job.payload["screening_item_id"])).run_id
    with TestClient(app) as client:
        headers=login(client,"admin@example.test"); response=client.get(f"/api/v1/screening-runs/{run_id}",headers=headers)
    assert response.status_code==200 and response.json()["data"]["status"]=="partial"
    assert response.json()["data"]["error_summary"]=={"provider_auth_failed":1}


def test_llm_dead_letter_preserves_rule_result_and_is_idempotent(tmp_path):
    app,_cipher,job=prepared(tmp_path); now=datetime.now(timezone.utc)
    with app.state.identity_store.sync_session() as db:
        finalize_llm_dead_letter(db,job,"handler_failed",now); finalize_llm_dead_letter(db,job,"handler_failed",now); db.commit()
    with app.state.identity_store.sync_session() as db:
        item=db.get(ScreeningItem,uuid.UUID(job.payload["screening_item_id"])); run=db.get(ScreeningRun,item.run_id)
        assert item.status=="scored" and item.llm_status=="failed" and item.llm_safe_error_code=="llm_handler_failed" and item.finished_at
        assert run.status=="partial" and run.succeeded_count==1 and run.failed_count==0 and run.finished_at and run.version>=2
        assert db.get(Application,item.application_id).stage=="new" and db.scalar(select(func.count(RuleResult.id)))==1
