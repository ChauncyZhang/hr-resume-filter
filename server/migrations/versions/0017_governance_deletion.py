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
        CREATE OR REPLACE FUNCTION reject_audit_log_mutation() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
          authorized boolean;
        BEGIN
          SELECT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_auth_members membership
            JOIN pg_catalog.pg_roles member_role
              ON member_role.oid = membership.member
            JOIN pg_catalog.pg_roles granted_role
              ON granted_role.oid = membership.roleid
            WHERE member_role.rolname = session_user
              AND granted_role.rolname = 'ux09_governance_executor'
          ) INTO authorized;
          IF NOT authorized OR TG_OP <> 'UPDATE' THEN
            RAISE EXCEPTION 'audit_logs are append-only' USING ERRCODE = '55000';
          END IF;

          IF TG_TABLE_NAME = 'audit_logs'
             OR TG_TABLE_NAME ~ '^audit_logs_[0-9]{4}_[0-9]{2}$'
             OR TG_TABLE_NAME = 'audit_logs_default' THEN
            IF (to_jsonb(NEW) - ARRAY['resource_id', 'metadata_json'])
                 IS DISTINCT FROM
               (to_jsonb(OLD) - ARRAY['resource_id', 'metadata_json'])
               OR NEW.metadata_json IS DISTINCT FROM
                  (OLD.metadata_json - ARRAY[
                    'candidate_id', 'subject_id', 'left_candidate_id',
                    'right_candidate_id', 'resume_id', 'file_object_id',
                    'application_id', 'screening_result_id', 'interview_id',
                    'feedback_id'
                  ])
               OR NOT (
                 NEW.resource_id IS NOT DISTINCT FROM OLD.resource_id
                 OR (
                   NEW.resource_id IS NULL
                   AND OLD.resource_id IS NOT NULL
                   AND OLD.resource_type IN (
                     'candidate', 'resume', 'file_object', 'application',
                     'screening_result', 'interview', 'interview_feedback'
                   )
                 )
               )
               OR (
                 NEW.resource_id IS NOT DISTINCT FROM OLD.resource_id
                 AND NEW.metadata_json IS NOT DISTINCT FROM OLD.metadata_json
               ) THEN
              RAISE EXCEPTION 'audit_logs are append-only' USING ERRCODE = '55000';
            END IF;
            RETURN NEW;
          END IF;

          IF TG_TABLE_NAME = 'resumes'
             AND (to_jsonb(NEW) - 'parsed_text') IS NOT DISTINCT FROM
                 (to_jsonb(OLD) - 'parsed_text')
             AND to_jsonb(NEW)->'parsed_text' = 'null'::jsonb
             AND to_jsonb(OLD)->'parsed_text' <> 'null'::jsonb THEN
            RETURN NEW;
          END IF;

          IF TG_TABLE_NAME IN (
               'application_stage_events', 'candidate_notes', 'candidate_events'
             )
             AND (to_jsonb(NEW) - 'payload') IS NOT DISTINCT FROM
                 (to_jsonb(OLD) - 'payload')
             AND to_jsonb(NEW)->'payload' = '{}'::jsonb
             AND to_jsonb(OLD)->'payload' <> '{}'::jsonb THEN
            RETURN NEW;
          END IF;

          RAISE EXCEPTION 'audit_logs are append-only' USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_screening_result() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          IF TG_OP = 'UPDATE'
             AND EXISTS (
               SELECT 1 FROM pg_catalog.pg_auth_members membership
               JOIN pg_catalog.pg_roles member_role ON member_role.oid = membership.member
               JOIN pg_catalog.pg_roles granted_role ON granted_role.oid = membership.roleid
               WHERE member_role.rolname = session_user
                 AND granted_role.rolname = 'ux09_governance_executor'
             )
             AND (to_jsonb(NEW) - ARRAY[
               'recommendation', 'required_hits', 'required_missing', 'bonus_hits',
               'estimated_years', 'risks', 'questions',
               'human_override_recommendation', 'human_override_reason_code',
               'human_override_by', 'human_override_at'
             ]) IS NOT DISTINCT FROM
             (to_jsonb(OLD) - ARRAY[
               'recommendation', 'required_hits', 'required_missing', 'bonus_hits',
               'estimated_years', 'risks', 'questions',
               'human_override_recommendation', 'human_override_reason_code',
               'human_override_by', 'human_override_at'
             ])
             AND NEW.recommendation = '需人工复核'
             AND NEW.required_hits = '[]'::jsonb
             AND NEW.required_missing = '[]'::jsonb
             AND NEW.bonus_hits = '[]'::jsonb
             AND NEW.estimated_years = 0
             AND NEW.risks = '[]'::jsonb
             AND NEW.questions = '[]'::jsonb
             AND NEW.human_override_recommendation IS NULL
             AND NEW.human_override_reason_code IS NULL
             AND NEW.human_override_by IS NULL
             AND NEW.human_override_at IS NULL THEN
            RETURN NEW;
          END IF;
          IF TG_OP = 'DELETE'
             OR NEW.id <> OLD.id OR NEW.organization_id <> OLD.organization_id
             OR NEW.item_id <> OLD.item_id
             OR NEW.application_id IS DISTINCT FROM OLD.application_id
             OR NEW.resume_id IS DISTINCT FROM OLD.resume_id
             OR NEW.rule_engine_version <> OLD.rule_engine_version
             OR NEW.rule_score <> OLD.rule_score
             OR NEW.recommendation <> OLD.recommendation
             OR NEW.required_hits <> OLD.required_hits
             OR NEW.required_missing <> OLD.required_missing
             OR NEW.bonus_hits <> OLD.bonus_hits
             OR NEW.estimated_years <> OLD.estimated_years
             OR NEW.risks <> OLD.risks OR NEW.questions <> OLD.questions
             OR NEW.created_at <> OLD.created_at THEN
            RAISE EXCEPTION 'screening result facts are append-only' USING ERRCODE='55000';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_llm_screening_evaluation() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          IF TG_OP = 'UPDATE'
             AND EXISTS (
               SELECT 1 FROM pg_catalog.pg_auth_members membership
               JOIN pg_catalog.pg_roles member_role ON member_role.oid = membership.member
               JOIN pg_catalog.pg_roles granted_role ON granted_role.oid = membership.roleid
               WHERE member_role.rolname = session_user
                 AND granted_role.rolname = 'ux09_governance_executor'
             )
             AND (to_jsonb(NEW) - ARRAY[
               'recommendation', 'summary', 'strengths', 'gaps', 'risks',
               'interview_questions'
             ]) IS NOT DISTINCT FROM
             (to_jsonb(OLD) - ARRAY[
               'recommendation', 'summary', 'strengths', 'gaps', 'risks',
               'interview_questions'
             ])
             AND NEW.recommendation = '需人工复核'
             AND NEW.summary = ''
             AND NEW.strengths = '[]'::jsonb AND NEW.gaps = '[]'::jsonb
             AND NEW.risks = '[]'::jsonb
             AND NEW.interview_questions = '[]'::jsonb THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'LLM screening evaluations are append-only' USING ERRCODE='55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_llm_invocation() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          IF TG_OP = 'UPDATE'
             AND EXISTS (
               SELECT 1 FROM pg_catalog.pg_auth_members membership
               JOIN pg_catalog.pg_roles member_role ON member_role.oid = membership.member
               JOIN pg_catalog.pg_roles granted_role ON granted_role.oid = membership.roleid
               WHERE member_role.rolname = session_user
                 AND granted_role.rolname = 'ux09_governance_executor'
             )
             AND (to_jsonb(NEW) - 'input_sha256') IS NOT DISTINCT FROM
                 (to_jsonb(OLD) - 'input_sha256')
             AND NEW.input_sha256 = encode(
               sha256(convert_to('deleted:' || OLD.id::text, 'UTF8')), 'hex'
             ) THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'LLM invocations are append-only' USING ERRCODE='55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_interview_history() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          IF TG_OP = 'UPDATE'
             AND EXISTS (
               SELECT 1 FROM pg_catalog.pg_auth_members membership
               JOIN pg_catalog.pg_roles member_role ON member_role.oid = membership.member
               JOIN pg_catalog.pg_roles granted_role ON granted_role.oid = membership.roleid
               WHERE member_role.rolname = session_user
                 AND granted_role.rolname = 'ux09_governance_executor'
             ) THEN
            IF TG_TABLE_NAME = 'interview_events'
               AND (to_jsonb(NEW) - 'payload') IS NOT DISTINCT FROM
                   (to_jsonb(OLD) - 'payload')
               AND to_jsonb(NEW)->'payload' = '{}'::jsonb THEN
              RETURN NEW;
            END IF;
            IF TG_TABLE_NAME = 'interview_feedback_revisions'
               AND (to_jsonb(NEW) - ARRAY['previous_payload', 'new_payload', 'reason'])
                   IS NOT DISTINCT FROM
                   (to_jsonb(OLD) - ARRAY['previous_payload', 'new_payload', 'reason'])
               AND to_jsonb(NEW)->'previous_payload' = '{}'::jsonb
               AND to_jsonb(NEW)->'new_payload' = '{}'::jsonb
               AND to_jsonb(NEW)->>'reason' = '' THEN
              RETURN NEW;
            END IF;
          END IF;
          RAISE EXCEPTION 'interview history is append-only' USING ERRCODE='55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION preserve_submitted_feedback() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
          actor_text text;
          revision_reason text;
          next_revision integer;
          previous_document jsonb;
          new_document jsonb;
        BEGIN
          IF TG_OP = 'UPDATE'
             AND EXISTS (
               SELECT 1 FROM pg_catalog.pg_auth_members membership
               JOIN pg_catalog.pg_roles member_role ON member_role.oid = membership.member
               JOIN pg_catalog.pg_roles granted_role ON granted_role.oid = membership.roleid
               WHERE member_role.rolname = session_user
                 AND granted_role.rolname = 'ux09_governance_executor'
             )
             AND (to_jsonb(NEW) - ARRAY[
               'ratings', 'strengths', 'risks', 'conclusion', 'notes'
             ]) IS NOT DISTINCT FROM
             (to_jsonb(OLD) - ARRAY[
               'ratings', 'strengths', 'risks', 'conclusion', 'notes'
             ])
             AND NEW.ratings = '{}'::jsonb AND NEW.strengths IS NULL
             AND NEW.risks IS NULL AND NEW.conclusion IS NULL
             AND NEW.notes IS NULL THEN
            RETURN NEW;
          END IF;
          IF TG_OP = 'DELETE' THEN
            IF OLD.status IN ('submitted', 'amended') THEN
              RAISE EXCEPTION 'submitted feedback cannot be deleted' USING ERRCODE='55000';
            END IF;
            RETURN OLD;
          END IF;
          IF OLD.status IN ('submitted', 'amended') AND NEW IS DISTINCT FROM OLD THEN
            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.interview_id IS DISTINCT FROM OLD.interview_id
               OR NEW.author_id IS DISTINCT FROM OLD.author_id
               OR NEW.created_at IS DISTINCT FROM OLD.created_at
               OR NEW.submitted_at IS DISTINCT FROM OLD.submitted_at THEN
              RAISE EXCEPTION 'submitted feedback identity and original timestamps are immutable' USING ERRCODE='55000';
            END IF;
            actor_text := nullif(current_setting('app.actor_user_id', true), '');
            revision_reason := nullif(current_setting('app.feedback_revision_reason', true), '');
            IF actor_text IS NULL OR revision_reason IS NULL THEN
              RAISE EXCEPTION 'submitted feedback amendment requires actor and reason' USING ERRCODE='55000';
            END IF;
            NEW.status := 'amended';
            NEW.version := OLD.version + 1;
            NEW.updated_at := now();
            previous_document := jsonb_build_object(
              'ratings', OLD.ratings, 'strengths', OLD.strengths,
              'risks', OLD.risks, 'conclusion', OLD.conclusion,
              'notes', OLD.notes, 'status', OLD.status,
              'submitted_at', OLD.submitted_at
            );
            new_document := jsonb_build_object(
              'ratings', NEW.ratings, 'strengths', NEW.strengths,
              'risks', NEW.risks, 'conclusion', NEW.conclusion,
              'notes', NEW.notes, 'status', NEW.status,
              'submitted_at', NEW.submitted_at
            );
            SELECT coalesce(max(revision_number), 0) + 1 INTO next_revision
            FROM public.interview_feedback_revisions
            WHERE organization_id = OLD.organization_id AND feedback_id = OLD.id;
            INSERT INTO public.interview_feedback_revisions(
              id, organization_id, feedback_id, revision_number,
              previous_payload, new_payload, reason, actor_id, created_at
            ) VALUES (
              gen_random_uuid(), OLD.organization_id, OLD.id, next_revision,
              previous_document, new_document, revision_reason,
              actor_text::uuid, now()
            );
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION redact_candidate_data(
          p_organization_id uuid,
          p_request_id uuid,
          p_candidate_id uuid
        ) RETURNS TABLE(
          database_redaction_checksum text,
          contacts bigint,
          resumes bigint,
          applications bigint,
          screening_records bigint,
          interviews bigint,
          feedback_records bigint,
          talent_memberships bigint,
          resume_objects bigint,
          temporary_exports bigint
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
          candidate_row public.candidates%ROWTYPE;
          request_row public.deletion_requests%ROWTYPE;
          resume_ids uuid[];
          file_ids uuid[];
          application_ids uuid[];
          screening_result_ids uuid[];
          interview_ids uuid[];
          feedback_ids uuid[];
          redaction_time timestamptz;
          checksum_payload text;
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_auth_members membership
            JOIN pg_catalog.pg_roles member_role ON member_role.oid = membership.member
            JOIN pg_catalog.pg_roles granted_role ON granted_role.oid = membership.roleid
            WHERE member_role.rolname = session_user
              AND granted_role.rolname = 'ux09_governance_executor'
          ) THEN
            RAISE EXCEPTION 'redaction_not_authorized' USING ERRCODE = '42501';
          END IF;

          SELECT * INTO candidate_row
          FROM public.candidates
          WHERE organization_id = p_organization_id
            AND id = p_candidate_id
          FOR UPDATE;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'redaction_context_invalid' USING ERRCODE = '22023';
          END IF;

          SELECT * INTO request_row
          FROM public.deletion_requests
          WHERE organization_id = p_organization_id
            AND id = p_request_id
            AND candidate_id = p_candidate_id
          FOR UPDATE;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'redaction_context_invalid' USING ERRCODE = '22023';
          END IF;
          IF request_row.status <> 'executing' THEN
            RAISE EXCEPTION 'redaction_state_invalid' USING ERRCODE = '22023';
          END IF;

          contacts := COALESCE((request_row.impact_manifest #>> '{counts,contacts}')::bigint, 0);
          resumes := COALESCE((request_row.impact_manifest #>> '{counts,resumes}')::bigint, 0);
          applications := COALESCE((request_row.impact_manifest #>> '{counts,applications}')::bigint, 0);
          screening_records := COALESCE((request_row.impact_manifest #>> '{counts,screening_records}')::bigint, 0);
          interviews := COALESCE((request_row.impact_manifest #>> '{counts,interviews}')::bigint, 0);
          feedback_records := COALESCE((request_row.impact_manifest #>> '{counts,feedback_records}')::bigint, 0);
          talent_memberships := COALESCE((request_row.impact_manifest #>> '{counts,talent_memberships}')::bigint, 0);
          resume_objects := COALESCE((request_row.impact_manifest #>> '{counts,resume_objects}')::bigint, 0);
          temporary_exports := COALESCE((request_row.impact_manifest #>> '{counts,temporary_exports}')::bigint, 0);

          IF candidate_row.deleted_at IS NOT NULL THEN
            IF candidate_row.version <> request_row.candidate_version + 1 THEN
              RAISE EXCEPTION 'redaction_tombstone_invalid' USING ERRCODE = '22023';
            END IF;
            redaction_time := candidate_row.deleted_at;
          ELSE
            IF candidate_row.version <> request_row.candidate_version THEN
              RAISE EXCEPTION 'redaction_manifest_stale' USING ERRCODE = '22023';
            END IF;
          END IF;

            SELECT COALESCE(array_agg(id ORDER BY id), '{}'::uuid[]),
                   COALESCE(array_agg(file_object_id ORDER BY file_object_id), '{}'::uuid[])
              INTO resume_ids, file_ids
            FROM public.resumes
            WHERE organization_id = p_organization_id
              AND candidate_id = p_candidate_id;
            SELECT COALESCE(array_agg(id ORDER BY id), '{}'::uuid[])
              INTO application_ids
            FROM public.applications
            WHERE organization_id = p_organization_id
              AND candidate_id = p_candidate_id;
            SELECT COALESCE(array_agg(sr.id ORDER BY sr.id), '{}'::uuid[])
              INTO screening_result_ids
            FROM public.screening_results sr
            JOIN public.screening_items si
              ON si.organization_id = sr.organization_id
             AND si.id = sr.item_id
            WHERE si.organization_id = p_organization_id
              AND si.candidate_id = p_candidate_id;
            SELECT COALESCE(array_agg(i.id ORDER BY i.id), '{}'::uuid[])
              INTO interview_ids
            FROM public.interviews i
            WHERE i.organization_id = p_organization_id
              AND i.application_id = ANY(application_ids);
            SELECT COALESCE(array_agg(f.id ORDER BY f.id), '{}'::uuid[])
              INTO feedback_ids
            FROM public.interview_feedbacks f
            WHERE f.organization_id = p_organization_id
              AND f.interview_id = ANY(interview_ids);

            DELETE FROM public.candidate_contacts
            WHERE organization_id = p_organization_id AND candidate_id = p_candidate_id;
            DELETE FROM public.download_tickets
            WHERE organization_id = p_organization_id AND resume_id = ANY(resume_ids);
            DELETE FROM public.talent_pool_memberships
            WHERE organization_id = p_organization_id AND candidate_id = p_candidate_id;
            DELETE FROM public.candidate_duplicate_hints
            WHERE organization_id = p_organization_id
              AND (
                candidate_id = p_candidate_id
                OR left_candidate_id = p_candidate_id
                OR right_candidate_id = p_candidate_id
                OR file_object_id = ANY(file_ids)
              );

            UPDATE public.resumes SET parsed_text = NULL
            WHERE organization_id = p_organization_id
              AND id = ANY(resume_ids)
              AND parsed_text IS NOT NULL;
            UPDATE public.file_objects
            SET storage_key = 'deleted/' || id::text,
                original_filename = 'deleted',
                quarantine_cleanup_key = NULL,
                sha256 = encode(
                  sha256(convert_to('deleted:' || id::text, 'UTF8')), 'hex'
                ),
                storage_state = 'deleted'
            WHERE organization_id = p_organization_id AND id = ANY(file_ids);
            UPDATE public.candidate_notes SET payload = '{}'::jsonb
            WHERE organization_id = p_organization_id
              AND candidate_id = p_candidate_id AND payload <> '{}'::jsonb;
            UPDATE public.candidate_events SET payload = '{}'::jsonb
            WHERE organization_id = p_organization_id
              AND candidate_id = p_candidate_id AND payload <> '{}'::jsonb;
            UPDATE public.application_stage_events SET payload = '{}'::jsonb
            WHERE organization_id = p_organization_id
              AND application_id = ANY(application_ids) AND payload <> '{}'::jsonb;
            UPDATE public.applications
            SET source = 'deleted', human_conclusion = NULL
            WHERE organization_id = p_organization_id AND id = ANY(application_ids);
            UPDATE public.screening_results
            SET recommendation = '需人工复核', required_hits = '[]'::jsonb,
                required_missing = '[]'::jsonb, bonus_hits = '[]'::jsonb,
                estimated_years = 0, risks = '[]'::jsonb, questions = '[]'::jsonb,
                human_override_recommendation = NULL,
                human_override_reason_code = NULL, human_override_by = NULL,
                human_override_at = NULL
            WHERE organization_id = p_organization_id AND id = ANY(screening_result_ids);
            UPDATE public.llm_screening_evaluations
            SET recommendation = '需人工复核', summary = '', strengths = '[]'::jsonb,
                gaps = '[]'::jsonb, risks = '[]'::jsonb,
                interview_questions = '[]'::jsonb
            WHERE organization_id = p_organization_id
              AND screening_result_id = ANY(screening_result_ids);
            UPDATE public.llm_invocations
            SET input_sha256 = encode(
              sha256(convert_to('deleted:' || id::text, 'UTF8')), 'hex'
            )
            WHERE organization_id = p_organization_id
              AND screening_result_id = ANY(screening_result_ids)
              AND input_sha256 IS NOT NULL;
            UPDATE public.interviews
            SET round_name = 'deleted', location = NULL, meeting_url = NULL,
                calendar_organizer = '{}'::jsonb, calendar_attendees = '[]'::jsonb
            WHERE organization_id = p_organization_id AND id = ANY(interview_ids);
            UPDATE public.interview_events SET payload = '{}'::jsonb
            WHERE organization_id = p_organization_id AND interview_id = ANY(interview_ids);
            UPDATE public.interview_feedbacks
            SET ratings = '{}'::jsonb, strengths = NULL, risks = NULL,
                conclusion = NULL, notes = NULL
            WHERE organization_id = p_organization_id AND id = ANY(feedback_ids);
            UPDATE public.interview_feedback_revisions
            SET previous_payload = '{}'::jsonb, new_payload = '{}'::jsonb, reason = ''
            WHERE organization_id = p_organization_id AND feedback_id = ANY(feedback_ids);
            DELETE FROM public.idempotency_records
            WHERE organization_id = p_organization_id
              AND (
                response_json::text LIKE '%' || p_candidate_id::text || '%'
                OR response_json::text LIKE ANY (
                  SELECT '%' || linked_id::text || '%'
                  FROM unnest(
                    resume_ids || application_ids || screening_result_ids ||
                    interview_ids || feedback_ids
                  ) linked_id
                )
              );
            UPDATE public.audit_logs
            SET resource_id = CASE
                  WHEN resource_id = p_candidate_id
                    OR resource_id = ANY(
                      resume_ids || file_ids || application_ids ||
                      screening_result_ids || interview_ids || feedback_ids
                    )
                    THEN NULL ELSE resource_id END,
                metadata_json = metadata_json - ARRAY[
                  'candidate_id', 'subject_id', 'left_candidate_id', 'right_candidate_id',
                  'resume_id', 'file_object_id', 'application_id',
                  'screening_result_id', 'interview_id', 'feedback_id'
                ]
            WHERE organization_id = p_organization_id
              AND (
                resource_id = p_candidate_id
                OR resource_id = ANY(
                  resume_ids || file_ids || application_ids ||
                  screening_result_ids || interview_ids || feedback_ids
                )
                OR metadata_json->>'candidate_id' = p_candidate_id::text
                OR metadata_json->>'subject_id' = p_candidate_id::text
                OR metadata_json->>'left_candidate_id' = p_candidate_id::text
                OR metadata_json->>'right_candidate_id' = p_candidate_id::text
                OR metadata_json->>'resume_id' IN (
                  SELECT linked_id::text FROM unnest(resume_ids) linked_id
                )
                OR metadata_json->>'file_object_id' IN (
                  SELECT linked_id::text FROM unnest(file_ids) linked_id
                )
                OR metadata_json->>'application_id' IN (
                  SELECT linked_id::text FROM unnest(application_ids) linked_id
                )
                OR metadata_json->>'screening_result_id' IN (
                  SELECT linked_id::text FROM unnest(screening_result_ids) linked_id
                )
                OR metadata_json->>'interview_id' IN (
                  SELECT linked_id::text FROM unnest(interview_ids) linked_id
                )
                OR metadata_json->>'feedback_id' IN (
                  SELECT linked_id::text FROM unnest(feedback_ids) linked_id
                )
              );

          IF candidate_row.deleted_at IS NULL THEN
            redaction_time := statement_timestamp();
            UPDATE public.candidates
            SET display_name = '已删除候选人', current_title = NULL,
                location = NULL, owner_id = NULL, deleted_at = redaction_time,
                retention_due_at = NULL, version = version + 1,
                updated_at = redaction_time
            WHERE organization_id = p_organization_id AND id = p_candidate_id;
            candidate_row.version := candidate_row.version + 1;
          ELSE
            UPDATE public.candidates
            SET display_name = '已删除候选人', current_title = NULL,
                location = NULL, owner_id = NULL, retention_due_at = NULL
            WHERE organization_id = p_organization_id
              AND id = p_candidate_id
              AND (
                display_name <> '已删除候选人'
                OR current_title IS NOT NULL OR location IS NOT NULL
                OR owner_id IS NOT NULL OR retention_due_at IS NOT NULL
              );
          END IF;

          checksum_payload := concat_ws('|', request_row.manifest_hash,
            candidate_row.version::text,
            to_char(
              redaction_time AT TIME ZONE 'UTC',
              'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
            ),
            contacts::text,
            resumes::text, applications::text, screening_records::text,
            interviews::text, feedback_records::text, talent_memberships::text,
            resume_objects::text, temporary_exports::text);
          database_redaction_checksum := encode(
            sha256(convert_to(checksum_payload, 'UTF8')), 'hex'
          );
          RETURN NEXT;
        END;
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION redact_candidate_data(uuid, uuid, uuid) FROM PUBLIC"
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

    op.execute("DROP FUNCTION redact_candidate_data(uuid, uuid, uuid)")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_audit_log_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'audit_logs are append-only' USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_screening_result() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' OR NEW.id<>OLD.id
             OR NEW.organization_id<>OLD.organization_id OR NEW.item_id<>OLD.item_id
             OR NEW.application_id IS DISTINCT FROM OLD.application_id
             OR NEW.resume_id IS DISTINCT FROM OLD.resume_id
             OR NEW.rule_engine_version<>OLD.rule_engine_version
             OR NEW.rule_score<>OLD.rule_score OR NEW.recommendation<>OLD.recommendation
             OR NEW.required_hits<>OLD.required_hits
             OR NEW.required_missing<>OLD.required_missing
             OR NEW.bonus_hits<>OLD.bonus_hits
             OR NEW.estimated_years<>OLD.estimated_years OR NEW.risks<>OLD.risks
             OR NEW.questions<>OLD.questions OR NEW.created_at<>OLD.created_at THEN
            RAISE EXCEPTION 'screening result facts are append-only' USING ERRCODE='55000';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_llm_screening_evaluation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'LLM screening evaluations are append-only' USING ERRCODE='55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_llm_invocation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'LLM invocations are append-only' USING ERRCODE='55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_interview_history() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'interview history is append-only' USING ERRCODE='55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION preserve_submitted_feedback() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          actor_text text;
          revision_reason text;
          next_revision integer;
          previous_document jsonb;
          new_document jsonb;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            IF OLD.status IN ('submitted', 'amended') THEN
              RAISE EXCEPTION 'submitted feedback cannot be deleted' USING ERRCODE='55000';
            END IF;
            RETURN OLD;
          END IF;
          IF OLD.status IN ('submitted', 'amended') AND NEW IS DISTINCT FROM OLD THEN
            IF NEW.id IS DISTINCT FROM OLD.id
               OR NEW.organization_id IS DISTINCT FROM OLD.organization_id
               OR NEW.interview_id IS DISTINCT FROM OLD.interview_id
               OR NEW.author_id IS DISTINCT FROM OLD.author_id
               OR NEW.created_at IS DISTINCT FROM OLD.created_at
               OR NEW.submitted_at IS DISTINCT FROM OLD.submitted_at THEN
              RAISE EXCEPTION 'submitted feedback identity and original timestamps are immutable' USING ERRCODE='55000';
            END IF;
            actor_text := nullif(current_setting('app.actor_user_id', true), '');
            revision_reason := nullif(current_setting('app.feedback_revision_reason', true), '');
            IF actor_text IS NULL OR revision_reason IS NULL THEN
              RAISE EXCEPTION 'submitted feedback amendment requires actor and reason' USING ERRCODE='55000';
            END IF;
            NEW.status := 'amended';
            NEW.version := OLD.version + 1;
            NEW.updated_at := now();
            previous_document := jsonb_build_object(
              'ratings', OLD.ratings, 'strengths', OLD.strengths,
              'risks', OLD.risks, 'conclusion', OLD.conclusion,
              'notes', OLD.notes, 'status', OLD.status,
              'submitted_at', OLD.submitted_at
            );
            new_document := jsonb_build_object(
              'ratings', NEW.ratings, 'strengths', NEW.strengths,
              'risks', NEW.risks, 'conclusion', NEW.conclusion,
              'notes', NEW.notes, 'status', NEW.status,
              'submitted_at', NEW.submitted_at
            );
            SELECT coalesce(max(revision_number), 0) + 1 INTO next_revision
            FROM interview_feedback_revisions
            WHERE organization_id = OLD.organization_id AND feedback_id = OLD.id;
            INSERT INTO interview_feedback_revisions(
              id, organization_id, feedback_id, revision_number,
              previous_payload, new_payload, reason, actor_id, created_at
            ) VALUES (
              gen_random_uuid(), OLD.organization_id, OLD.id, next_revision,
              previous_document, new_document, revision_reason,
              actor_text::uuid, now()
            );
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.drop_table("deletion_recovery_runs")
    op.drop_table("legal_holds")
    op.drop_table("deletion_artifacts")
    op.drop_table("deletion_requests")
    op.drop_column("candidates", "deleted_at")
