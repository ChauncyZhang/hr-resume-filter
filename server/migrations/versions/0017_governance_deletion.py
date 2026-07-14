"""Add deletion governance persistence and a fail-closed audit redaction stub."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0017_governance_deletion"
down_revision = "0016a_audit_category_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "candidates",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "deletion_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="requested"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safe_error_code", sa.String(64), nullable=True),
        sa.Column("impact_manifest", postgresql.JSONB(), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("manifest_schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("candidate_version", sa.Integer(), nullable=False),
        sa.Column("recovery_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "id", name="uq_deletion_requests_tenant_id"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_deletion_requests_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "candidate_id"],
            ["candidates.organization_id", "candidates.id"],
            name="fk_deletion_requests_candidate",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requested_by"],
            ["users.organization_id", "users.id"],
            name="fk_deletion_requests_requested_by",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "approved_by"],
            ["users.organization_id", "users.id"],
            name="fk_deletion_requests_approved_by",
        ),
        sa.CheckConstraint(
            "status in ('requested','approved','executing','completed','failed')",
            name="ck_deletion_requests_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_deletion_requests_version"),
        sa.CheckConstraint(
            "reason_code in ('retention_expired','candidate_request','administrator_request')",
            name="ck_deletion_requests_reason_code",
        ),
        sa.CheckConstraint(
            "requested_by IS NOT NULL OR reason_code = 'retention_expired'",
            name="ck_deletion_requests_requester",
        ),
        sa.CheckConstraint(
            "manifest_schema_version = 1",
            name="ck_deletion_requests_manifest_schema_version",
        ),
        sa.CheckConstraint(
            "manifest_hash ~ '^[0-9a-f]{64}$'",
            name="ck_deletion_requests_manifest_hash",
        ),
        sa.CheckConstraint("policy_version >= 1", name="ck_deletion_requests_policy_version"),
        sa.CheckConstraint(
            "candidate_version >= 1", name="ck_deletion_requests_candidate_version"
        ),
        sa.CheckConstraint(
            "recovery_generation >= 0",
            name="ck_deletion_requests_recovery_generation",
        ),
    )
    op.create_index(
        "uq_deletion_requests_open_candidate",
        "deletion_requests",
        ["organization_id", "candidate_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'completed'"),
    )
    op.create_table(
        "deletion_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("safe_error_code", sa.String(64), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "request_id", "kind", "storage_key", name="uq_deletion_artifacts_request_kind_key"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_deletion_artifacts_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["deletion_requests.organization_id", "deletion_requests.id"],
            name="fk_deletion_artifacts_request",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "kind in ('resume_object','report_export_object')",
            name="ck_deletion_artifacts_kind",
        ),
        sa.CheckConstraint(
            "status in ('pending','deleted')", name="ck_deletion_artifacts_status"
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_deletion_artifacts_attempts"),
    )
    op.create_table(
        "legal_holds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("placed_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("released_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_reason", sa.String(1000), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "id", name="uq_legal_holds_tenant_id"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_legal_holds_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "candidate_id"],
            ["candidates.organization_id", "candidates.id"],
            name="fk_legal_holds_candidate",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "placed_by"],
            ["users.organization_id", "users.id"],
            name="fk_legal_holds_placed_by",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "released_by"],
            ["users.organization_id", "users.id"],
            name="fk_legal_holds_released_by",
        ),
        sa.CheckConstraint("char_length(reason) <= 1000", name="ck_legal_holds_reason"),
        sa.CheckConstraint(
            "released_reason IS NULL OR char_length(released_reason) <= 1000",
            name="ck_legal_holds_released_reason",
        ),
        sa.CheckConstraint("version >= 1", name="ck_legal_holds_version"),
    )
    op.create_index(
        "uq_legal_holds_active_candidate",
        "legal_holds",
        ["organization_id", "candidate_id"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
    )
    op.create_table(
        "deletion_recovery_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("restore_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("restored_candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requeued_request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("safe_error_code", sa.String(64), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queue_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "id", name="uq_deletion_recovery_runs_tenant_id"),
        sa.UniqueConstraint(
            "organization_id", "restore_id", name="uq_deletion_recovery_runs_restore"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_deletion_recovery_runs_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "queue_job_id"],
            ["background_jobs.organization_id", "background_jobs.id"],
            name="fk_deletion_recovery_runs_queue_job",
        ),
        sa.CheckConstraint(
            "status in ('queued','running','completed','failed')",
            name="ck_deletion_recovery_runs_status",
        ),
        sa.CheckConstraint(
            "restored_candidate_count >= 0",
            name="ck_deletion_recovery_runs_restored_count",
        ),
        sa.CheckConstraint(
            "requeued_request_count >= 0",
            name="ck_deletion_recovery_runs_requeued_count",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION redact_candidate_audit_evidence(
          p_organization_id uuid,
          p_candidate_id uuid
        ) RETURNS void
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          RAISE EXCEPTION 'audit redaction unavailable' USING ERRCODE = '0A000';
        END;
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION redact_candidate_audit_evidence(uuid, uuid) FROM PUBLIC"
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            LOCK TABLE
              audit_logs,
              candidates,
              deletion_artifacts,
              deletion_recovery_runs,
              deletion_requests,
              legal_holds
            IN ACCESS EXCLUSIVE MODE
            """
        )
    )
    evidence_exists = connection.scalar(
        sa.text(
            """
            SELECT
              EXISTS (SELECT 1 FROM deletion_requests)
              OR EXISTS (SELECT 1 FROM deletion_artifacts)
              OR EXISTS (SELECT 1 FROM legal_holds)
              OR EXISTS (SELECT 1 FROM deletion_recovery_runs)
              OR EXISTS (
                SELECT 1 FROM audit_logs
                WHERE event_type LIKE 'governance.deletion_%'
                   OR event_type LIKE 'governance.legal_hold_%'
                   OR event_type LIKE 'governance.deletion_recovery_%'
              )
              OR EXISTS (SELECT 1 FROM candidates WHERE deleted_at IS NOT NULL)
            """
        )
    )
    if evidence_exists:
        raise RuntimeError(
            "refusing 0017 downgrade: deletion governance evidence exists"
        )

    op.execute("DROP FUNCTION redact_candidate_audit_evidence(uuid, uuid)")
    op.drop_table("deletion_recovery_runs")
    op.drop_table("legal_holds")
    op.drop_table("deletion_artifacts")
    op.drop_table("deletion_requests")
    op.drop_column("candidates", "deleted_at")
