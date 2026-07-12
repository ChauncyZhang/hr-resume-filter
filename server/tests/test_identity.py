from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from server.app.core.settings import Settings
from server.app.identity.models import Organization, User, UserRole, UserStatus
from server.app.identity.security import PasswordService, hash_token
from server.app.identity.service import Clock, TokenSource
from server.app.main import create_app


class Probe:
    async def check(self) -> None:
        pass


class FrozenClock(Clock):
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 12, 8, tzinfo=timezone.utc)

    def current_time(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now += timedelta(**kwargs)


class SequenceTokens(TokenSource):
    def __init__(self) -> None:
        self.values = iter(f"token-{index:064d}" for index in range(100))

    def new_token(self) -> str:
        return next(self.values)


@pytest.fixture
def identity_app(tmp_path):
    settings = Settings(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}",
        cors_origins=["https://hr.example.test"],
    )
    clock = FrozenClock()
    tokens = SequenceTokens()
    app = create_app(
        settings=settings,
        database_probe=Probe(),
        storage_probe=Probe(),
        clock=clock,
        token_source=tokens,
        initialize_identity_schema=True,
    )
    with TestClient(app) as client:
        yield app, client, clock


def seed_user(app, *, email="admin@example.test", password="correct horse", status=UserStatus.ACTIVE):
    password_service = PasswordService()
    with app.state.identity_store.sync_session() as session:
        organization = Organization(slug="acme", name="Acme", status="active")
        user = User(
            organization=organization,
            email=email,
            normalized_email=email.casefold(),
            display_name="Admin",
            password_hash=password_service.hash(password),
            status=status,
        )
        user.roles.append(UserRole(role="recruiting_admin"))
        session.add(user)
        session.commit()
        return user.id


def login(client, **overrides):
    body = {"organization_slug": "acme", "email": "admin@example.test", "password": "correct horse"}
    body.update(overrides)
    return client.post(
        "/api/v1/auth/login",
        json=body,
        headers={"Origin": "https://hr.example.test"},
    )


def test_passwords_use_argon2id_and_verify() -> None:
    service = PasswordService()
    encoded = service.hash("correct horse")
    assert encoded.startswith("$argon2id$")
    assert service.verify(encoded, "correct horse")
    assert not service.verify(encoded, "wrong")


def test_login_persists_only_hashes_and_sets_host_cookie(identity_app) -> None:
    app, client, _ = identity_app
    seed_user(app)
    response = login(client)
    assert response.status_code == 200
    csrf = response.headers["X-CSRF-Token"]
    cookie = response.headers["set-cookie"]
    assert "__Host-hr_session=" in cookie
    assert "HttpOnly" in cookie and "Path=/" in cookie and "SameSite=lax" in cookie
    assert "Secure" not in cookie
    assert "password" not in response.text.casefold()
    with app.state.identity_store.sync_session() as session:
        stored = session.query(app.state.identity_store.SessionModel).one()
        assert stored.token_hash == hash_token(client.cookies["__Host-hr_session"])
        assert stored.csrf_token_hash == hash_token(csrf)
        assert client.cookies["__Host-hr_session"] not in repr(stored)
        assert csrf not in repr(stored)


@pytest.mark.parametrize(
    "case",
    ["unknown_organization", "unknown_user", "wrong_password", "disabled", "locked"],
)
def test_login_failures_are_generic(identity_app, case) -> None:
    app, client, clock = identity_app
    if case not in {"unknown_organization", "unknown_user"}:
        user_id = seed_user(app, status=UserStatus.DISABLED if case == "disabled" else UserStatus.ACTIVE)
        if case == "locked":
            with app.state.identity_store.sync_session() as session:
                user = session.get(User, user_id)
                user.locked_until = clock.current_time() + timedelta(minutes=10)
                session.commit()
    overrides = {
        "unknown_organization": {"organization_slug": "missing"},
        "unknown_user": {"email": "missing@example.test"},
        "wrong_password": {"password": "wrong"},
    }.get(case, {})
    response = login(client, **overrides)
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_failed"
    assert response.json()["detail"] == "Invalid credentials or account unavailable."


def test_five_failures_lock_for_fifteen_minutes_and_success_resets(identity_app) -> None:
    app, client, clock = identity_app
    user_id = seed_user(app)
    for _ in range(4):
        assert login(client, password="wrong").status_code == 401
    assert login(client).status_code == 200
    with app.state.identity_store.sync_session() as session:
        user = session.get(User, user_id)
        assert user.failed_login_count == 0 and user.locked_until is None
    for _ in range(5):
        assert login(client, password="wrong").status_code == 401
    assert login(client).status_code == 401
    clock.advance(minutes=15, seconds=1)
    assert login(client).status_code == 200


def test_me_rotates_csrf_refreshes_idle_but_not_absolute(identity_app) -> None:
    app, client, clock = identity_app
    seed_user(app)
    initial = login(client)
    old_csrf = initial.headers["X-CSRF-Token"]
    with app.state.identity_store.sync_session() as session:
        original = session.query(app.state.identity_store.SessionModel).one()
        absolute = original.absolute_expires_at
        idle = original.idle_expires_at
    clock.advance(minutes=5)
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.headers["X-CSRF-Token"] != old_csrf
    assert response.json()["data"]["roles"] == ["recruiting_admin"]
    assert "session" not in response.text.casefold() and "password" not in response.text.casefold()
    with app.state.identity_store.sync_session() as session:
        refreshed = session.query(app.state.identity_store.SessionModel).one()
        assert refreshed.idle_expires_at > idle
        assert refreshed.absolute_expires_at == absolute


def test_idle_absolute_disable_and_authorization_version_revoke(identity_app) -> None:
    app, client, clock = identity_app
    user_id = seed_user(app)
    assert login(client).status_code == 200
    clock.advance(minutes=31)
    assert client.get("/api/v1/me").status_code == 401
    assert login(client).status_code == 200
    with app.state.identity_store.sync_session() as session:
        user = session.get(User, user_id)
        user.authorization_version += 1
        session.commit()
    assert client.get("/api/v1/me").status_code == 401
    assert login(client).status_code == 200
    with app.state.identity_store.sync_session() as session:
        user = session.get(User, user_id)
        user.status = UserStatus.DISABLED
        session.commit()
    assert client.get("/api/v1/me").status_code == 401


def test_absolute_expiry_is_not_extended_by_activity(identity_app) -> None:
    app, client, clock = identity_app
    seed_user(app)
    assert login(client).status_code == 200
    for _ in range(23):
        clock.advance(minutes=29)
        assert client.get("/api/v1/me").status_code == 200
    clock.advance(hours=1)
    assert client.get("/api/v1/me").status_code == 401


def test_logout_requires_origin_and_matching_csrf_then_revokes(identity_app) -> None:
    app, client, _ = identity_app
    seed_user(app)
    csrf = login(client).headers["X-CSRF-Token"]
    for headers in ({}, {"Origin": "https://evil.test", "X-CSRF-Token": csrf}, {"Origin": "https://hr.example.test", "X-CSRF-Token": "wrong"}):
        response = client.post("/api/v1/auth/logout", headers=headers)
        assert response.status_code == 403
        assert response.json()["code"] == "csrf_validation_failed"
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://hr.example.test", "X-CSRF-Token": csrf},
    )
    assert response.status_code == 204
    assert client.get("/api/v1/me").status_code == 401


def test_production_cookie_is_secure(identity_app) -> None:
    app, _, _ = identity_app
    seed_user(app)
    app.state.settings.environment = "production"
    with TestClient(app, base_url="https://hr.example.test") as client:
        response = login(client)
    assert "Secure" in response.headers["set-cookie"]


def test_audit_events_do_not_contain_credentials_tokens_or_full_ip(identity_app) -> None:
    app, client, _ = identity_app
    seed_user(app)
    response = client.post(
        "/api/v1/auth/login",
        json={"organization_slug": "acme", "email": "admin@example.test", "password": "correct horse"},
        headers={"Origin": "https://hr.example.test", "X-Forwarded-For": "203.0.113.9, 10.0.0.1"},
    )
    csrf = response.headers["X-CSRF-Token"]
    token = client.cookies["__Host-hr_session"]
    with app.state.identity_store.sync_session() as session:
        audit = session.query(app.state.identity_store.AuditModel).one()
        rendered = repr(audit.metadata_json)
        assert "correct horse" not in rendered
        assert csrf not in rendered and token not in rendered
        assert "203.0.113.9" not in rendered and "10.0.0.1" not in rendered
