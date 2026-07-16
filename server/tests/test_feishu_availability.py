from datetime import datetime, timedelta, timezone

import pytest

from server.app.integrations.feishu.availability import FeishuAwareAvailabilityProvider
from server.app.integrations.feishu.models import FeishuIdentityBinding, FeishuOrganizationConfig
from server.app.integrations.feishu.provider import BusyWindow, FakeFeishuProvider, FeishuProviderError
from server.app.identity.models import User
from server.app.interviews.availability import INTERNAL_AVAILABILITY_PROVIDER
from server.tests.test_interview_api import make_app, seed_application


def configured_provider(app, seed, *, bind=True):
    provider = FakeFeishuProvider()
    with app.state.identity_store.sync_session() as db:
        organization_id = db.get(User, seed["admin_id"]).organization_id
        db.add(FeishuOrganizationConfig(
            organization_id=organization_id,
            app_id="cli_test",
            encrypted_app_secret=app.state.feishu_secret_cipher.encrypt("secret"),
            redirect_uri="https://hr.example.test/api/v1/auth/feishu/callback",
            calendar_id="primary",
            enabled=True,
            created_by=seed["admin_id"],
            updated_by=seed["admin_id"],
        ))
        if bind:
            db.add(FeishuIdentityBinding(
                organization_id=organization_id,
                user_id=seed["interviewer_id"],
                union_id="on_interviewer",
                open_id="ou_interviewer",
                tenant_key="tenant",
            ))
        db.commit()
    return provider, FeishuAwareAvailabilityProvider(
        INTERNAL_AVAILABILITY_PROVIDER, provider, app.state.feishu_secret_cipher
    )


def organization_id(app, seed):
    with app.state.identity_store.sync_session() as db:
        return db.get(User, seed["admin_id"]).organization_id


def test_disabled_feishu_keeps_internal_availability(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    tenant_id = organization_id(app, seed)
    starts_at = datetime(2026, 7, 20, 8, tzinfo=timezone.utc)
    with app.state.identity_store.sync_session() as db:
        rows = app.state.interview_availability_provider.availability(
            db=db, organization_id=tenant_id, participant_ids=[seed["interviewer_id"]],
            starts_at=starts_at, ends_at=starts_at + timedelta(days=7), buffer_minutes=15,
            exclude_interview_id=None,
        )
    assert rows == [{"participant_id": str(seed["interviewer_id"]), "status": "confirmed", "busy": []}]


def test_enabled_feishu_merges_external_busy_and_chunks_long_ranges(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    tenant_id = organization_id(app, seed)
    provider, adapter = configured_provider(app, seed)
    starts_at = datetime(2026, 7, 20, 8, tzinfo=timezone.utc)
    provider.busy_windows = (BusyWindow("ou_interviewer", starts_at + timedelta(hours=2), starts_at + timedelta(hours=3)),)
    with app.state.identity_store.sync_session() as db:
        rows = adapter.availability(
            db=db, organization_id=tenant_id, participant_ids=[seed["interviewer_id"]],
            starts_at=starts_at, ends_at=starts_at + timedelta(days=30), buffer_minutes=15,
            exclude_interview_id=None,
        )
    assert rows[0]["status"] == "confirmed"
    assert rows[0]["busy"] == [{
        "starts_at": (starts_at + timedelta(hours=2)).isoformat(),
        "ends_at": (starts_at + timedelta(hours=3)).isoformat(),
    }]
    assert len(provider.freebusy_requests) == 3
    assert all(request.time_max - request.time_min <= timedelta(days=14) for request in provider.freebusy_requests)


def test_enabled_feishu_never_reports_unbound_or_failed_calendar_as_free(tmp_path) -> None:
    app = make_app(tmp_path)
    seed = seed_application(app)
    tenant_id = organization_id(app, seed)
    _, unbound_adapter = configured_provider(app, seed, bind=False)
    starts_at = datetime(2026, 7, 20, 8, tzinfo=timezone.utc)
    with app.state.identity_store.sync_session() as db:
        rows = unbound_adapter.availability(
            db=db, organization_id=tenant_id, participant_ids=[seed["interviewer_id"]],
            starts_at=starts_at, ends_at=starts_at + timedelta(days=7), buffer_minutes=15,
            exclude_interview_id=None,
        )
    assert rows == [{"participant_id": str(seed["interviewer_id"]), "status": "unknown", "busy": []}]

    failing_path = tmp_path / "failing"
    failing_path.mkdir()
    failing_app = make_app(failing_path)
    failing_seed = seed_application(failing_app)
    failing_tenant_id = organization_id(failing_app, failing_seed)
    provider, failing_adapter = configured_provider(failing_app, failing_seed)
    provider.failure = FeishuProviderError()
    with failing_app.state.identity_store.sync_session() as db:
        with pytest.raises(FeishuProviderError):
            failing_adapter.availability(
                db=db, organization_id=failing_tenant_id,
                participant_ids=[failing_seed["interviewer_id"]], starts_at=starts_at,
                ends_at=starts_at + timedelta(days=7), buffer_minutes=15, exclude_interview_id=None,
            )
