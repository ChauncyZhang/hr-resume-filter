from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from server.app.integrations.feishu.provider import (
    CalendarEvent,
    CalendarEventRequest,
    FakeFeishuProvider,
    FeishuCredentials,
    OAuthIdentity,
    chunk_freebusy_requests,
)
from server.app.integrations.feishu.service import public_config, stable_identity_key


def test_public_config_never_serializes_secret_material() -> None:
    class Config:
        app_id = "cli_test"
        redirect_uri = "https://hr.example.test/api/v1/auth/feishu/callback"
        calendar_id = "primary"
        enabled = False
        encrypted_app_secret = b"encrypted-secret"
        encrypted_verification_token = b"encrypted-token"
        encrypted_encrypt_key = b"encrypted-key"
        version = 3
        last_test_status = "failed"
        last_tested_at = None
        last_test_error_code = "feishu_unavailable"

    view = public_config(Config())

    assert view == {
        "app_id": "cli_test",
        "redirect_uri": "https://hr.example.test/api/v1/auth/feishu/callback",
        "calendar_id": "primary",
        "enabled": False,
        "app_secret_configured": True,
        "verification_token_configured": True,
        "encrypt_key_configured": True,
        "version": 3,
        "last_test_status": "failed",
        "last_tested_at": None,
        "last_test_error_code": "feishu_unavailable",
    }
    assert "secret" not in repr(view).lower().replace("app_secret_configured", "")
    assert b"encrypted" not in repr(view).encode()


def test_stable_identity_prefers_union_id_and_requires_provider_id() -> None:
    assert stable_identity_key(OAuthIdentity("on_123", "ou_123", None, "tenant")) == (
        "union_id",
        "on_123",
    )
    assert stable_identity_key(OAuthIdentity(None, "ou_123", None, "tenant")) == (
        "open_id",
        "ou_123",
    )
    with pytest.raises(ValueError, match="stable identity"):
        stable_identity_key(OAuthIdentity(None, None, None, "tenant"))


def test_freebusy_is_split_by_ten_users_and_fourteen_days() -> None:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    requests = chunk_freebusy_requests(
        [f"ou_{index}" for index in range(21)], start, start + timedelta(days=29)
    )

    assert len(requests) == 9
    assert {len(item.user_ids) for item in requests} == {1, 10}
    assert all(item.time_max - item.time_min <= timedelta(days=14) for item in requests)
    assert requests[-1].time_max == start + timedelta(days=29)


def test_fake_provider_contract_is_idempotent_and_records_attendees() -> None:
    provider = FakeFeishuProvider(
        identity=OAuthIdentity("on_123", "ou_123", "invited@example.test", "tenant")
    )
    credentials = FeishuCredentials(
        app_id="cli_test",
        app_secret="app-secret",
        redirect_uri="https://hr.example.test/callback",
        calendar_id="primary",
    )
    request = CalendarEventRequest(
        interview_id=uuid4(),
        summary="Backend interview",
        starts_at=datetime(2026, 7, 20, 1, tzinfo=timezone.utc),
        ends_at=datetime(2026, 7, 20, 2, tzinfo=timezone.utc),
        timezone="Asia/Shanghai",
        description="Interview",
        location="Room 1",
        attendee_emails=("one@example.test", "two@example.test"),
    )

    first = provider.create_event(credentials, request, idempotency_key="event-key")
    second = provider.create_event(credentials, request, idempotency_key="event-key")
    assert first == second
    assert first.attendee_emails == request.attendee_emails

    updated = provider.update_event(
        credentials,
        first.event_id,
        request,
        idempotency_key="update-key",
    )
    assert isinstance(updated, CalendarEvent)
    provider.cancel_event(credentials, first.event_id, idempotency_key="cancel-key")
    provider.cancel_event(credentials, first.event_id, idempotency_key="cancel-key")
    assert provider.events[first.event_id].cancelled is True


def test_fake_provider_does_not_make_network_calls_and_exposes_oauth_identity() -> None:
    identity = OAuthIdentity("on_123", "ou_123", "existing@example.test", "tenant")
    provider = FakeFeishuProvider(identity=identity)
    credentials = FeishuCredentials("cli", "secret", "https://example.test/callback")

    assert provider.test_connection(credentials).ok is True
    assert provider.exchange_code(credentials, "single-use-code") == identity
    assert provider.exchanged_codes == ["single-use-code"]
