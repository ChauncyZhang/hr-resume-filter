from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = ROOT / "deploy" / "backup"
BACKUPCTL = BACKUP_DIR / "backupctl.py"
DRILL_COMPOSE = ROOT / "deploy" / "compose.backup-drill.yaml"
BACKUP_RUNBOOK = ROOT / "deploy" / "backup-recovery-runbook.md"
OPERATIONS_RUNBOOK = ROOT / "deploy" / "production-operations-runbook.md"
FOUNDATION_REPORT = ROOT / ".superpowers" / "sdd" / "task-phase6c-report.md"


def _load_backupctl():
    assert BACKUPCTL.is_file(), "Phase 6C backup contract core is missing"
    spec = importlib.util.spec_from_file_location("phase6c_backupctl", BACKUPCTL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def _manifest(**overrides):
    manifest = {
        "schema_version": 1,
        "backup_run_id": "20260715T000000Z-a1b2c3d4",
        "state": "complete",
        "backup_cutoff_utc": "2026-07-15T00:00:00Z",
        "schedule_interval_hours": 12,
        "toolchain": {
            "image": "ux09-backup:phase6c-foundation",
            "image_digest": "sha256:" + "a" * 64,
            "postgres": "16.9",
            "minio_client": "RELEASE.2025-07-21T05-28-08Z",
            "destination_client": "rclone-1.70.3",
        },
        "database": {
            "format": "custom",
            "sha256": "b" * 64,
            "size_bytes": 4096,
            "restore_list_entries": 23,
        },
        "business_snapshot": {
            "sha256": "c" * 64,
            "size_bytes": 8192,
            "object_count": 7,
            "inventory_sha256": "d" * 64,
        },
        "reference_validation": {"checked": 7, "mismatches": 0},
        "ledger_archive": {
            "archive_run_id": "ledger-20260715T000000Z-e5f6a7b8",
            "cutoff_utc": "2026-07-15T00:00:00Z",
            "manifest_sha256": "e" * 64,
            "signing_key_versions": ["ledger-v1", "ledger-v2"],
        },
        "retention": {"backup_window_days": 30, "policy_version": "rp-v4"},
        "gates": {
            "pg_restore_list": True,
            "hashes": True,
            "object_inventory": True,
            "references": True,
        },
    }
    manifest.update(overrides)
    return manifest


def _catalog_entry(run_id: str, cutoff: str, **overrides):
    item = {
        "backup_run_id": run_id,
        "backup_cutoff_utc": cutoff,
        "complete": True,
        "valid": True,
        "backup_window_days": 30,
    }
    item.update(overrides)
    return item


def test_phase6c_foundation_files_are_new_isolated_contract_surface() -> None:
    required = {
        BACKUPCTL,
        BACKUP_DIR / "Dockerfile",
        BACKUP_DIR / "backup.sh",
        BACKUP_DIR / "ledger-archive.sh",
        BACKUP_DIR / "prune.sh",
        BACKUP_DIR / "restore.sh",
        BACKUP_DIR / "drill.sh",
        BACKUP_DIR / "traffic-gate.sh",
        DRILL_COMPOSE,
        BACKUP_RUNBOOK,
        OPERATIONS_RUNBOOK,
        FOUNDATION_REPORT,
    }
    missing = sorted(path.relative_to(ROOT).as_posix() for path in required if not path.is_file())
    assert not missing, f"missing Phase 6C foundation files: {missing}"


def test_phase6c_scope_rejects_generated_artifacts_and_staged_files_outside_allowlist() -> None:
    generated = sorted(
        path.relative_to(ROOT).as_posix()
        for path in BACKUP_DIR.rglob("*")
        if path.name == "__pycache__" or path.suffix == ".pyc"
    )
    assert not generated, f"generated backup artifacts must not exist or be committed: {generated}"

    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    exact = {
        ".superpowers/sdd/task-phase6c-report.md",
        "deploy/backup-recovery-runbook.md",
        "deploy/compose.backup-drill.yaml",
        "deploy/production-operations-runbook.md",
        "server/tests/test_backup_restore_contract.py",
    }
    unexpected = [
        path for path in staged if path not in exact and not path.startswith("deploy/backup/")
    ]
    assert not unexpected, f"staged files outside the Phase 6C allowlist: {unexpected}"
    assert not any("__pycache__" in path or path.endswith(".pyc") for path in staged)


def test_manifest_schema_accepts_only_complete_non_pii_evidence() -> None:
    backupctl = _load_backupctl()
    backupctl.validate_backup_manifest(_manifest())

    for forbidden_key, value in (
        ("object_key", "clean/candidate-123/resume.pdf"),
        ("candidate_id", "c-123"),
        ("request_id", "r-123"),
        ("filename", "alice-resume.pdf"),
        ("password", "synthetic-secret"),
        ("secret", "synthetic-secret"),
    ):
        tainted = _manifest(**{forbidden_key: value})
        with pytest.raises(ValueError, match="forbidden|sensitive|PII"):
            backupctl.validate_backup_manifest(tainted)

    tainted_value = _manifest(operator_note="alice@example.test")
    with pytest.raises(ValueError, match="forbidden|sensitive|PII"):
        backupctl.validate_backup_manifest(tainted_value)


def test_manifest_rejects_unverified_or_unpaired_restore_points() -> None:
    backupctl = _load_backupctl()
    for broken in (
        _manifest(state="pending"),
        _manifest(database={**_manifest()["database"], "restore_list_entries": 0}),
        _manifest(reference_validation={"checked": 7, "mismatches": 1}),
        _manifest(gates={**_manifest()["gates"], "hashes": False}),
        _manifest(schedule_interval_hours=24),
        _manifest(operator_note="no arbitrary extension fields"),
    ):
        with pytest.raises(ValueError):
            backupctl.validate_backup_manifest(broken)


def test_manifest_signature_verification_rejects_payload_tamper(tmp_path: Path) -> None:
    backupctl = _load_backupctl()
    payload = tmp_path / "manifest.json"
    signature = tmp_path / "manifest.sig"
    key = tmp_path / "manifest-signing-key"
    payload.write_text('{"schema_version":1}\n', encoding="utf-8")
    key.write_bytes(b"k" * 32)

    backupctl.write_hmac_signature(payload, key, signature)
    backupctl.verify_hmac_signature(payload, key, signature)
    payload.write_text('{"schema_version":2}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="signature"):
        backupctl.verify_hmac_signature(payload, key, signature)


def test_atomic_publish_writes_manifest_and_complete_only_after_validation(tmp_path: Path) -> None:
    backupctl = _load_backupctl()
    staging = tmp_path / "pending"
    staging.mkdir()
    (staging / "database.dump").write_bytes(b"not-empty")
    (staging / "business.snapshot").write_bytes(b"not-empty")
    published = tmp_path / "published"

    with pytest.raises(RuntimeError, match="reference validation"):
        backupctl.atomic_publish_local(
            staging,
            published,
            _manifest(),
            lambda: (_ for _ in ()).throw(RuntimeError("reference validation failed")),
        )
    assert not published.exists()
    assert not (staging / "manifest.json").exists()
    assert not (staging / "COMPLETE").exists()

    backupctl.atomic_publish_local(staging, published, _manifest(), lambda: None)
    assert json.loads((published / "manifest.json").read_text(encoding="utf-8")) == _manifest()
    assert (published / "COMPLETE").read_text(encoding="utf-8").strip()
    assert not staging.exists()


@pytest.mark.parametrize(
    ("destination", "app_host", "forbidden_path"),
    [
        ("/srv/backups", "app.example.test", "/srv/backups"),
        ("file:///offhost-looking", "app.example.test", "/var/lib/postgresql/data"),
        ("ssh://app.example.test/vault", "app.example.test", "/var/lib/postgresql/data"),
        ("ssh://backup.example.test/var/lib/postgresql/data", "app.example.test", "/var/lib/postgresql/data"),
        ("s3://postgres/var/lib/minio/data", "app.example.test", "/var/lib/minio/data"),
    ],
)
def test_off_host_destination_fails_closed_for_app_host_and_data_paths(
    destination: str, app_host: str, forbidden_path: str
) -> None:
    backupctl = _load_backupctl()
    with pytest.raises(ValueError, match="off-host|forbidden|application host"):
        backupctl.validate_off_host_destination(destination, app_host, [forbidden_path])
    assert backupctl.validate_off_host_destination(
        "s3://independent-backup-vault/ux09", app_host, [forbidden_path]
    ) == "s3://independent-backup-vault/ux09"


def test_secret_files_are_required_distinct_and_never_serialized(tmp_path: Path) -> None:
    backupctl = _load_backupctl()
    secret_files = []
    for name in (
        "pgpass",
        "business-source.conf",
        "business-destination.conf",
        "business-prune.conf",
        "business-restore.conf",
        "ledger-source.conf",
        "ledger-destination.conf",
        "ledger-restore.conf",
        "manifest-signing-key",
    ):
        path = tmp_path / name
        path.write_text(f"synthetic-{name}-credential", encoding="utf-8")
        secret_files.append(path)

    backupctl.validate_secret_files(secret_files)
    with pytest.raises(ValueError, match="distinct"):
        backupctl.validate_secret_files([secret_files[0], secret_files[0]])

    serialized = json.dumps(_manifest(), sort_keys=True)
    for path in secret_files:
        assert path.read_text(encoding="utf-8") not in serialized


def test_prune_deletes_complete_expired_groups_and_preserves_newest_two() -> None:
    backupctl = _load_backupctl()
    catalog = [
        _catalog_entry("run-1", "2026-05-01T00:00:00Z"),
        _catalog_entry("run-2", "2026-05-15T00:00:00Z"),
        _catalog_entry("run-3", "2026-07-01T00:00:00Z"),
        _catalog_entry("run-4", "2026-07-14T00:00:00Z"),
        _catalog_entry("pending-old", "2026-04-01T00:00:00Z", complete=False, valid=False),
    ]
    assert backupctl.plan_prune(
        catalog,
        retention_days=30,
        now=datetime(2026, 7, 15, tzinfo=timezone.utc),
    ) == ["run-1", "run-2"]


def test_prune_fails_closed_on_policy_mismatch_or_invalid_latest() -> None:
    backupctl = _load_backupctl()
    base = [
        _catalog_entry("run-1", "2026-05-01T00:00:00Z"),
        _catalog_entry("run-2", "2026-07-01T00:00:00Z"),
        _catalog_entry("run-3", "2026-07-14T00:00:00Z"),
    ]
    mismatch = [*base[:-1], {**base[-1], "backup_window_days": 31}]
    invalid_latest = [*base[:-1], {**base[-1], "valid": False}]
    for catalog in (mismatch, invalid_latest):
        with pytest.raises(ValueError, match="policy|latest|valid"):
            backupctl.plan_prune(
                catalog,
                retention_days=30,
                now=datetime(2026, 7, 15, tzinfo=timezone.utc),
            )


def test_ledger_archive_is_separate_and_business_identity_has_no_ledger_mutation() -> None:
    backupctl = _load_backupctl()
    history = {
        "schema_version": 1,
        "active_key_version": "ledger-v2",
        "versions": [
            {"version": "ledger-v1", "status": "retired"},
            {"version": "ledger-v2", "status": "active"},
        ],
    }
    backupctl.validate_ledger_boundary(
        business_buckets=["resumes", "exports"],
        ledger_bucket="governance-ledger",
        business_capabilities={"business:read", "destination:append"},
        business_destination="s3://business-vault/ux09",
        ledger_destination="s3://ledger-vault/ux09",
        key_history=history,
    )
    with pytest.raises(ValueError):
        backupctl.validate_ledger_boundary(
            business_buckets=["resumes", "governance-ledger"],
            ledger_bucket="governance-ledger",
            business_capabilities={"ledger:restore", "ledger:delete"},
            business_destination="s3://same-vault/ux09",
            ledger_destination="s3://same-vault/ux09",
            key_history={"schema_version": 1, "active_key_version": "unversioned", "versions": []},
        )


def test_restore_uses_latest_independent_ledger_not_business_cutoff() -> None:
    source = BACKUPCTL.read_text(encoding="utf-8")
    assert '"restore-latest"' in source
    assert '"restore-latest-before"' not in source


@pytest.mark.parametrize(
    ("project", "volumes", "confirmed"),
    [
        ("ux09", ["ux09_postgres-data"], "1"),
        ("ux09-production", ["ux09-production-postgres-data"], "1"),
        ("ux09-backup-drill-a1", ["ux09_postgres-data"], "1"),
        ("ux09-backup-drill-a1", ["ux09-backup-drill-a1-postgres-data"], "0"),
    ],
)
def test_restore_and_drill_require_disposable_project_and_volumes(
    project: str, volumes: list[str], confirmed: str
) -> None:
    backupctl = _load_backupctl()
    with pytest.raises(ValueError, match="disposable|production|volume"):
        backupctl.validate_disposable_recovery(project, volumes, confirmed)
    backupctl.validate_disposable_recovery(
        "ux09-backup-drill-safe123",
        ["ux09-backup-drill-safe123-postgres-data", "ux09-backup-drill-safe123-minio-data"],
        "1",
    )


def test_traffic_stays_closed_until_real_b2b3_cli_and_worker_evidence() -> None:
    backupctl = _load_backupctl()
    restore = {
        "state": "restored",
        "traffic_open": False,
        "gates": {"database": True, "business_objects": True, "ledger_restored_first": True},
    }
    with pytest.raises(ValueError, match="B2B3|traffic"):
        backupctl.require_traffic_open_evidence(restore, None)

    incomplete = {
        "status": "complete",
        "real_cli": True,
        "real_worker": False,
        "redelete_verified": True,
        "idempotency_verified": True,
        "tamper_failure_verified": True,
        "checkpoint_reclaim_verified": True,
    }
    with pytest.raises(ValueError, match="B2B3|traffic"):
        backupctl.require_traffic_open_evidence(restore, incomplete)

    complete = {**incomplete, "real_worker": True}
    assert backupctl.require_traffic_open_evidence(restore, complete) is True


def test_rpo_rto_evidence_enforces_24h_and_4h_budgets() -> None:
    backupctl = _load_backupctl()
    evidence = backupctl.build_drill_evidence(
        backup_cutoff_utc="2026-07-14T12:00:00Z",
        failure_at_utc="2026-07-15T00:00:00Z",
        recovery_started_utc="2026-07-15T00:05:00Z",
        recovery_finished_utc="2026-07-15T02:05:00Z",
        b2b3_complete=True,
        smoke_complete=True,
    )
    assert evidence["rpo_hours"] == 12
    assert evidence["rto_hours"] == 2
    assert evidence["gates"]["rpo_24h"] is True
    assert evidence["gates"]["rto_4h"] is True

    with pytest.raises(ValueError, match="RPO|RTO"):
        backupctl.build_drill_evidence(
            backup_cutoff_utc="2026-07-13T00:00:00Z",
            failure_at_utc="2026-07-15T00:00:00Z",
            recovery_started_utc="2026-07-15T00:00:00Z",
            recovery_finished_utc="2026-07-15T05:00:00Z",
            b2b3_complete=False,
            smoke_complete=False,
        )


def test_posix_scripts_use_strict_mode_and_expose_no_secret_values() -> None:
    scripts = sorted(BACKUP_DIR.glob("*.sh"))
    assert scripts
    for script in scripts:
        source = script.read_text(encoding="utf-8")
        assert source.startswith("#!/bin/sh\nset -eu\n"), script
        assert "PGPASSWORD=" not in source
        assert "set -x" not in source
        assert re.search(r"(_FILE|CONFIG_FILE)", source), script


def test_backup_image_is_digest_pinned_and_contains_versioned_toolchain() -> None:
    dockerfile = (BACKUP_DIR / "Dockerfile").read_text(encoding="utf-8")
    from_lines = re.findall(r"^FROM\s+(\S+)", dockerfile, flags=re.MULTILINE)
    assert len(from_lines) >= 3
    assert all(re.search(r":[^@\s]+@sha256:[0-9a-f]{64}$", image) for image in from_lines)
    for required in ("postgres:16.9", "minio/mc:RELEASE.2025-07-21T05-28-08Z", "rclone/rclone:1.70.3"):
        assert required in dockerfile


def test_destination_adapter_refuses_to_overwrite_existing_run_id() -> None:
    source = (BACKUP_DIR / "destination-rclone.sh").read_text(encoding="utf-8")
    stage = source.split("stage-group)", 1)[1].split(";;", 1)[0]
    assert '"$complete/COMPLETE"' in stage
    assert "refusing to overwrite" in stage


def test_drill_compose_is_isolated_disposable_and_has_no_traffic_service() -> None:
    result = subprocess.run(
        ["docker", "compose", "-f", str(DRILL_COMPOSE), "config", "--format", "json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    model = json.loads(result.stdout)
    assert model["name"].startswith("ux09-backup-drill-")
    assert set(model["services"]) == {"backup-tool", "minio", "postgres"}
    assert not any(service.get("ports") for service in model["services"].values())
    assert all(network.get("internal") is True for network in model["networks"].values())
    rendered = result.stdout.lower()
    assert "ux09_postgres-data" not in rendered
    assert "ux09_minio-data" not in rendered


def test_runbooks_and_report_state_foundation_limits_and_real_b2b3_dependency() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (BACKUP_RUNBOOK, OPERATIONS_RUNBOOK, FOUNDATION_REPORT)
    )
    for required in (
        "12 hours",
        "24-hour RPO",
        "4-hour RTO",
        "DISPOSABLE_RECOVERY_CONFIRMED=1",
        "B2B3 CLI",
        "B2B3 Worker",
        "traffic",
        "forward-only",
        "rollback",
        "credential",
        "signing-key",
        "Phase 6C foundation",
    ):
        assert required.lower() in combined.lower()
    assert "not production ready" in FOUNDATION_REPORT.read_text(encoding="utf-8").lower()
    assert "complete real restore drill" in FOUNDATION_REPORT.read_text(encoding="utf-8").lower()
