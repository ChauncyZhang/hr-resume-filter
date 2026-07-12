from server.app.identity.bootstrap import bootstrap_system_admin
from server.app.identity.models import AuditLog, User
from server.app.identity.security import PasswordService
from server.tests.test_identity import identity_app


def test_bootstrap_is_explicit_and_rotates_selected_admin(identity_app) -> None:
    app, _, _ = identity_app
    first = bootstrap_system_admin(app.state.identity_store, "acme", "Acme", "admin@example.test", "Admin", "first-secret")
    second = bootstrap_system_admin(app.state.identity_store, "acme", "Acme", "admin@example.test", "Admin", "second-secret")
    assert first == second
    with app.state.identity_store.sync_session() as session:
        user = session.query(User).one()
        assert PasswordService().verify(user.password_hash, "second-secret")
        assert user.authorization_version == 2
        assert [role.role for role in user.roles] == ["system_admin"]
        assert [audit.event_type for audit in session.query(AuditLog).order_by(AuditLog.created_at)] == [
            "bootstrap.admin_created",
            "bootstrap.admin_rotated",
        ]
