from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from server.app.governance.models import RetentionPolicy
from server.app.identity.models import AuditLog, Organization
from server.app.recruiting.models import Candidate, IdempotencyRecord


def test_governance_model_contract_is_registered() -> None:
    table = RetentionPolicy.__table__
    assert table.name == "retention_policies"
    assert {column.name for column in table.columns} == {
        "id",
        "organization_id",
        "terminal_days",
        "talent_pool_days",
        "backup_window_days",
        "version",
        "updated_by",
        "created_at",
        "updated_at",
    }
    assert not table.c.updated_by.nullable
    assert any(
        isinstance(constraint, UniqueConstraint)
        and [column.name for column in constraint.columns] == ["organization_id"]
        for constraint in table.constraints
    )
    checks = {
        str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert {
        "terminal_days BETWEEN 30 AND 3650",
        "talent_pool_days BETWEEN 30 AND 3650",
        "backup_window_days BETWEEN 30 AND 3650",
        "version >= 1",
    } <= checks


def test_existing_models_expose_governance_foundation_columns_and_index() -> None:
    assert not Organization.__table__.c.retention_policy_id.nullable
    assert Candidate.__table__.c.retention_due_at.nullable
    assert not IdempotencyRecord.__table__.c.expires_at.nullable

    audit_columns = AuditLog.__table__.c
    assert {"category", "resource_type", "resource_id", "ip_hash"} <= set(audit_columns.keys())
    assert not audit_columns.category.nullable
    assert audit_columns.resource_type.nullable
    assert audit_columns.resource_id.nullable
    assert audit_columns.ip_hash.nullable

    assert any(
        isinstance(index, Index)
        and index.name == "ix_idempotency_records_expires_at"
        and [column.name for column in index.columns] == ["organization_id", "expires_at"]
        for index in IdempotencyRecord.__table__.indexes
    )
