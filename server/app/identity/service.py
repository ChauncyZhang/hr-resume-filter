from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from server.app.identity.models import (
    AuditLog,
    Department,
    Organization,
    PasswordInvitation,
    User,
    UserSession,
    UserStatus,
)
from server.app.identity.security import PasswordService, hash_token, tokens_match
from server.app.identity.store import IdentityStore


class Clock:
    def current_time(self) -> datetime:
        return datetime.now(timezone.utc)


class TokenSource:
    def new_token(self) -> str:
        return secrets.token_urlsafe(32)


class AuthenticationFailed(Exception):
    pass


class InvalidSession(Exception):
    pass


class CsrfFailed(Exception):
    pass


class InvitationInvalidOrExpired(Exception):
    pass


class CurrentPasswordInvalid(Exception):
    pass


class PasswordUnchanged(Exception):
    pass


class IdentityService:
    def __init__(self, store: IdentityStore, clock: Clock, tokens: TokenSource) -> None:
        self.store = store
        self.clock = clock
        self.tokens = tokens
        self.passwords = PasswordService()
        self._dummy_password_hash = self.passwords.hash("not-a-real-account-password")

    def _safe_network_id(self, value: str | None) -> str | None:
        if not value:
            return None
        first = value.split(",", 1)[0].strip()
        return hashlib.sha256(first.encode()).hexdigest()[:16]

    def _audit(self, db, event: str, outcome: str, *, organization_id=None, user_id=None, trace_id=None, network=None) -> None:
        db.add(AuditLog(
            organization_id=organization_id,
            actor_user_id=user_id,
            event_type=event,
            outcome=outcome,
            trace_id=trace_id,
            metadata_json={"network_id": self._safe_network_id(network)},
        ))

    def login(self, organization_slug: str, email: str, password: str, *, trace_id: str, network: str | None):
        now = self.clock.current_time()
        with self.store.sync_session() as db:
            user = db.scalar(
                select(User)
                .join(Organization)
                .options(selectinload(User.roles), selectinload(User.organization))
                .where(Organization.slug == organization_slug, User.normalized_email == email.strip().casefold())
                .with_for_update(of=User)
            )
            password_valid = self.passwords.verify(
                user.password_hash if user else self._dummy_password_hash, password
            )
            valid = bool(
                user
                and user.status == UserStatus.ACTIVE
                and (user.locked_until is None or self._aware(user.locked_until) <= now)
                and password_valid
            )
            if not valid:
                if user and user.status == UserStatus.ACTIVE and (user.locked_until is None or self._aware(user.locked_until) <= now):
                    window = self._aware(user.failed_login_window_started_at) if user.failed_login_window_started_at else None
                    if window is None or now - window > timedelta(minutes=5):
                        user.failed_login_count = 1
                        user.failed_login_window_started_at = now
                    else:
                        user.failed_login_count += 1
                    if user.failed_login_count >= 5:
                        user.locked_until = now + timedelta(minutes=15)
                self._audit(db, "authentication.login", "denied", organization_id=user.organization_id if user else None, user_id=user.id if user else None, trace_id=trace_id, network=network)
                db.commit()
                raise AuthenticationFailed
            user.failed_login_count = 0
            user.failed_login_window_started_at = None
            user.locked_until = None
            session_token, csrf = self.tokens.new_token(), self.tokens.new_token()
            record = UserSession(
                organization_id=user.organization_id,
                user_id=user.id,
                token_hash=hash_token(session_token),
                csrf_token_hash=hash_token(csrf),
                idle_expires_at=now + timedelta(minutes=30),
                absolute_expires_at=now + timedelta(hours=12),
                authorization_version=user.authorization_version,
            )
            db.add(record)
            self._audit(db, "authentication.login", "success", organization_id=user.organization_id, user_id=user.id, trace_id=trace_id, network=network)
            db.commit()
            return session_token, csrf

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _resolve_session(self, db, token: str, *, trace_id: str | None = None, network: str | None = None) -> UserSession:
        record = db.scalar(
            select(UserSession)
            .options(
                selectinload(UserSession.user).selectinload(User.roles),
                selectinload(UserSession.user).selectinload(User.organization),
            )
            .where(UserSession.token_hash == hash_token(token))
            .with_for_update(of=UserSession)
        )
        if record is None:
            raise InvalidSession
        if record.revoked_at is not None:
            raise InvalidSession
        reason = self._session_invalid_reason(record)
        if reason is None:
            return record
        now = self.clock.current_time()
        record.revoked_at = now
        record.revocation_reason = reason
        self._audit(
            db,
            "session.invalidated",
            "revoked",
            organization_id=record.organization_id,
            user_id=record.user_id,
            trace_id=trace_id,
            network=network,
        )
        db.commit()
        raise InvalidSession

    def _session_invalid_reason(self, record: UserSession) -> str | None:
        now = self.clock.current_time()
        if self._aware(record.absolute_expires_at) <= now:
            return "absolute_expired"
        if self._aware(record.idle_expires_at) <= now:
            return "idle_expired"
        if record.user.status != UserStatus.ACTIVE:
            return "user_disabled"
        if record.authorization_version != record.user.authorization_version:
            return "authorization_version_stale"
        return None

    def me(self, token: str):
        with self.store.sync_session() as db:
            record = self._resolve_session(db, token)
            now = self.clock.current_time()
            csrf = self.tokens.new_token()
            record.csrf_token_hash = hash_token(csrf)
            record.idle_expires_at = min(now + timedelta(minutes=30), self._aware(record.absolute_expires_at))
            user = record.user
            department = (
                db.scalar(
                    select(Department).where(
                        Department.organization_id == user.organization_id,
                        Department.id == user.department_id,
                    )
                )
                if user.department_id is not None
                else None
            )
            data = {
                "id": str(user.id),
                "email": user.email,
                "display_name": user.display_name,
                "organization": {"id": str(user.organization.id), "slug": user.organization.slug, "name": user.organization.name},
                "department": (
                    {"id": str(department.id), "name": department.name}
                    if department is not None
                    else None
                ),
                "roles": sorted(role.role for role in user.roles),
                "permissions": self.permission_summary(role.role for role in user.roles),
            }
            db.commit()
            return data, csrf

    def accept_password_invitation(
        self, token: str, password: str, *, trace_id: str
    ) -> str:
        now = self.clock.current_time()
        with self.store.sync_session() as db:
            invitation = db.scalar(
                select(PasswordInvitation)
                .options(selectinload(PasswordInvitation.user))
                .where(PasswordInvitation.token_hash == hash_token(token))
                .with_for_update(of=PasswordInvitation)
            )
            if (
                invitation is None
                or invitation.used_at is not None
                or self._aware(invitation.expires_at) <= now
                or invitation.user.status != UserStatus.INVITED
            ):
                raise InvitationInvalidOrExpired
            invitation.user.password_hash = self.passwords.hash(password)
            invitation.user.status = UserStatus.ACTIVE
            invitation.used_at = now
            db.add(
                AuditLog(
                    organization_id=invitation.organization_id,
                    actor_user_id=invitation.user_id,
                    category="system",
                    event_type="identity.password_invitation_accepted",
                    outcome="success",
                    resource_type="user",
                    resource_id=invitation.user_id,
                    trace_id=trace_id,
                    metadata_json={},
                )
            )
            email = invitation.user.email
            db.commit()
            return email

    def change_password(
        self,
        token: str,
        current_password: str,
        new_password: str,
        *,
        trace_id: str,
        network: str | None,
    ) -> None:
        now = self.clock.current_time()
        with self.store.sync_session() as db:
            current_session = self._resolve_session(
                db, token, trace_id=trace_id, network=network
            )
            user = db.scalar(
                select(User)
                .where(
                    User.organization_id == current_session.organization_id,
                    User.id == current_session.user_id,
                )
                .with_for_update(of=User)
            )
            if user is None or not self.passwords.verify(
                user.password_hash, current_password
            ):
                raise CurrentPasswordInvalid
            if self.passwords.verify(user.password_hash, new_password):
                raise PasswordUnchanged

            user.password_hash = self.passwords.hash(new_password)
            user.authorization_version += 1
            current_session.authorization_version = user.authorization_version
            db.execute(
                update(UserSession)
                .where(
                    UserSession.organization_id == user.organization_id,
                    UserSession.user_id == user.id,
                    UserSession.id != current_session.id,
                    UserSession.revoked_at.is_(None),
                )
                .values(revoked_at=now, revocation_reason="password_changed")
            )
            self._audit(
                db,
                "authentication.password_changed",
                "success",
                organization_id=user.organization_id,
                user_id=user.id,
                trace_id=trace_id,
                network=network,
            )
            db.commit()

    def principal(self, token: str):
        from server.app.identity.policy import Principal

        with self.store.sync_session() as db:
            record = self._resolve_session(db, token)
            return Principal(
                user_id=record.user_id,
                organization_id=record.organization_id,
                roles=frozenset(role.role for role in record.user.roles),
                active=True,
            )

    def logout(self, token: str, csrf: str, *, trace_id: str, network: str | None) -> None:
        with self.store.sync_session() as db:
            record = self._resolve_session(db, token, trace_id=trace_id, network=network)
            if not tokens_match(record.csrf_token_hash, csrf):
                raise CsrfFailed
            record.revoked_at = self.clock.current_time()
            record.revocation_reason = "logout"
            self._audit(db, "authentication.logout", "success", organization_id=record.organization_id, user_id=record.user_id, trace_id=trace_id, network=network)
            db.commit()

    def validate_csrf(self, token: str, csrf: str, *, trace_id: str, network: str | None) -> bool:
        with self.store.sync_session() as db:
            try:
                record = self._resolve_session(db, token, trace_id=trace_id, network=network)
            except InvalidSession:
                return False
            return tokens_match(record.csrf_token_hash, csrf)

    def audit_denial(self, event: str, *, token: str | None, trace_id: str, network: str | None) -> bool:
        if not token:
            return False
        with self.store.sync_session() as db:
            try:
                record = self._resolve_session(db, token, trace_id=trace_id, network=network)
            except InvalidSession:
                return False
            self._audit(db, event, "denied", organization_id=record.organization_id, user_id=record.user_id, trace_id=trace_id, network=network)
            db.commit()
            return True

    @staticmethod
    def permission_summary(roles) -> list[str]:
        from server.app.identity.policy import GLOBAL_PERMISSIONS
        return sorted({permission.value for role in roles for permission in GLOBAL_PERMISSIONS.get(role, set())})
