from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from sqlalchemy import func, select

from server.app.governance.models import RetentionPolicy
from server.app.identity.models import Job
from server.app.recruiting.models import Application, Candidate
from server.app.screening.models import ScreeningRun
from server.app.talent.models import TalentPool, TalentPoolMembership
from server.app.talent.service import DEFERRED_POOL_SYSTEM_KEY, ensure_deferred_membership
from server.tests.test_recruiting_api import make_app
from server.tests.test_screening_routing import seed_routing_case


def test_deferred_membership_uses_system_pool_admin_and_retention_policy(tmp_path):
    app = make_app(tmp_path)
    case = seed_routing_case(app, suffix="deferred")
    with app.state.identity_store.sync_session() as db:
        policy = db.scalar(
            select(RetentionPolicy).where(
                RetentionPolicy.organization_id == case.organization_id
            )
        )
        policy.talent_pool_days = 365
        application = db.get(Application, case.application_id)
        candidate = db.get(Candidate, case.candidate_id)
        job = db.get(Job, case.job_id)
        run = db.get(ScreeningRun, case.run_id)
        before = datetime.now(timezone.utc)
        membership = ensure_deferred_membership(
            db,
            application=application,
            candidate=candidate,
            job=job,
            run=run,
            score=59,
            transferable_capabilities=["Distributed systems", "Python", "SQL"],
        )
        db.flush()
        pool = db.get(TalentPool, membership.pool_id)
        assert pool.system_key == DEFERRED_POOL_SYSTEM_KEY
        assert pool.visibility == "recruiting_team"
        assert pool.owner_id == case.admin_id
        assert pool.retention_days == 365
        assert membership.source_application_id == case.application_id
        assert membership.owner_id == case.creator_id
        assert membership.reason == "LLM 初筛分低于 60"
        assert membership.tags == [
            "Platform Engineer deferred",
            "LLM 59分",
            "Distributed systems",
            "Python",
            "SQL",
        ]
        assert membership.retention_until >= before


def test_deferred_membership_upsert_does_not_duplicate_pool_or_membership(tmp_path):
    app = make_app(tmp_path)
    case = seed_routing_case(app, suffix="upsert", with_admin=False)
    with app.state.identity_store.sync_session() as db:
        policy = db.scalar(
            select(RetentionPolicy).where(
                RetentionPolicy.organization_id == case.organization_id
            )
        )
        policy.talent_pool_days = 365
        application = db.get(Application, case.application_id)
        candidate = db.get(Candidate, case.candidate_id)
        job = db.get(Job, case.job_id)
        run = db.get(ScreeningRun, case.run_id)
        first = ensure_deferred_membership(
            db,
            application=application,
            candidate=candidate,
            job=job,
            run=run,
            score=10,
            transferable_capabilities=["A", "B", "C", "D", "E", "ignored"],
        )
        db.flush()
        policy.talent_pool_days = 400
        second = ensure_deferred_membership(
            db,
            application=application,
            candidate=candidate,
            job=job,
            run=run,
            score=20,
            transferable_capabilities=["Updated"],
        )
        assert first.id == second.id
        assert second.tags == ["Platform Engineer upsert", "LLM 20分", "Updated"]
        pool = db.get(TalentPool, second.pool_id)
        assert pool.owner_id == case.creator_id
        assert pool.retention_days == 400
        assert db.scalar(select(func.count(TalentPool.id))) == 1
        assert db.scalar(select(func.count(TalentPoolMembership.id))) == 1


def test_deferred_membership_rejects_cross_tenant_run_context(tmp_path):
    app = make_app(tmp_path)
    case = seed_routing_case(app, suffix="deferred-tenant")
    with app.state.identity_store.sync_session() as db:
        application = db.get(Application, case.application_id)
        candidate = db.get(Candidate, case.candidate_id)
        job = db.get(Job, case.job_id)
        wrong_run = SimpleNamespace(
            organization_id=uuid4(),
            job_id=case.job_id,
            created_by=case.creator_id,
        )
        with pytest.raises(ValueError, match="deferred_membership_context_mismatch"):
            ensure_deferred_membership(
                db,
                application=application,
                candidate=candidate,
                job=job,
                run=wrong_run,
                score=59,
            )
