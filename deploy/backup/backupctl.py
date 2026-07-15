#!/usr/bin/env python3
"""Fail-closed Phase 6C backup and recovery contract helpers.

This module deliberately owns orchestration contracts, not B2B3 recovery logic.
Secrets are consumed only through mounted files and are never added to argv,
logs, manifests, or evidence documents.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlparse


UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{4,127}$")
FORBIDDEN_MANIFEST_KEYS = {
    "access_key",
    "candidate_id",
    "content",
    "credential",
    "filename",
    "object_key",
    "password",
    "request_id",
    "secret",
}
LOCAL_DESTINATION_SCHEMES = {"", "file", "local"}
LOCAL_DESTINATION_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "minio", "app", "ux09"}
DEFAULT_FORBIDDEN_DATA_PATHS = (
    "/var/lib/postgresql/data",
    "/var/lib/minio/data",
    "/data/postgres",
    "/data/minio",
)


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, UTC_FORMAT).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid UTC timestamp: {value!r}") from error
    return parsed


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _require_sha256(value: Any, label: str) -> None:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase sha256")


def _scan_manifest(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in FORBIDDEN_MANIFEST_KEYS:
                raise ValueError(f"forbidden sensitive manifest field: {'.'.join((*path, normalized))}")
            _scan_manifest(child, (*path, normalized))
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _scan_manifest(child, (*path, str(index)))
        return
    if isinstance(value, str):
        lowered = value.lower()
        if "@" in value or "-----begin" in lowered or re.search(r"\b(candidate|request)[-_]?[0-9a-f]{6,}\b", lowered):
            raise ValueError(f"forbidden sensitive or PII value in manifest at {'.'.join(path)}")


def validate_backup_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate the public, non-PII COMPLETE restore-point manifest."""
    root = _require_mapping(manifest, "manifest")
    _scan_manifest(root)
    required = {
        "schema_version",
        "backup_run_id",
        "state",
        "backup_cutoff_utc",
        "schedule_interval_hours",
        "toolchain",
        "database",
        "business_snapshot",
        "reference_validation",
        "ledger_archive",
        "retention",
        "gates",
    }
    missing = required.difference(root)
    if missing:
        raise ValueError(f"manifest missing required fields: {sorted(missing)}")
    if set(root) != required:
        raise ValueError("manifest contains fields outside the non-PII schema allowlist")
    if root["schema_version"] != 1 or root["state"] != "complete":
        raise ValueError("manifest is not a complete schema version 1 restore point")
    if not isinstance(root["backup_run_id"], str) or not RUN_ID_RE.fullmatch(root["backup_run_id"]):
        raise ValueError("invalid backup_run_id")
    _parse_utc(root["backup_cutoff_utc"])
    if root["schedule_interval_hours"] != 12:
        raise ValueError("backup schedule must be exactly 12 hours")

    toolchain = _require_mapping(root["toolchain"], "toolchain")
    if set(toolchain) != {"image", "image_digest", "postgres", "minio_client", "destination_client"}:
        raise ValueError("toolchain contains fields outside the schema allowlist")
    _require_sha256(str(toolchain.get("image_digest", "")).removeprefix("sha256:"), "toolchain.image_digest")
    for field in ("image", "postgres", "minio_client", "destination_client"):
        if not toolchain.get(field):
            raise ValueError(f"toolchain.{field} is required")

    database = _require_mapping(root["database"], "database")
    if set(database) != {"format", "sha256", "size_bytes", "restore_list_entries"}:
        raise ValueError("database evidence contains fields outside the schema allowlist")
    if database.get("format") != "custom" or int(database.get("size_bytes", 0)) <= 0:
        raise ValueError("database must be a non-empty custom-format dump")
    if int(database.get("restore_list_entries", 0)) <= 0:
        raise ValueError("pg_restore --list evidence is empty")
    _require_sha256(database.get("sha256"), "database.sha256")

    business = _require_mapping(root["business_snapshot"], "business_snapshot")
    if set(business) != {"sha256", "size_bytes", "object_count", "inventory_sha256"}:
        raise ValueError("business evidence contains fields outside the schema allowlist")
    if int(business.get("size_bytes", 0)) <= 0 or int(business.get("object_count", -1)) < 0:
        raise ValueError("business snapshot size/object count is invalid")
    _require_sha256(business.get("sha256"), "business_snapshot.sha256")
    _require_sha256(business.get("inventory_sha256"), "business_snapshot.inventory_sha256")

    references = _require_mapping(root["reference_validation"], "reference_validation")
    if set(references) != {"checked", "mismatches"}:
        raise ValueError("reference evidence contains fields outside the schema allowlist")
    if int(references.get("checked", -1)) < 0 or int(references.get("mismatches", -1)) != 0:
        raise ValueError("reference validation must finish with zero mismatches")

    ledger = _require_mapping(root["ledger_archive"], "ledger_archive")
    if set(ledger) != {"archive_run_id", "cutoff_utc", "manifest_sha256", "signing_key_versions"}:
        raise ValueError("ledger evidence contains fields outside the schema allowlist")
    if not RUN_ID_RE.fullmatch(str(ledger.get("archive_run_id", ""))):
        raise ValueError("ledger archive run id is invalid")
    _parse_utc(str(ledger.get("cutoff_utc", "")))
    _require_sha256(ledger.get("manifest_sha256"), "ledger_archive.manifest_sha256")
    versions = ledger.get("signing_key_versions")
    if not isinstance(versions, list) or not versions or not all(isinstance(item, str) and item for item in versions):
        raise ValueError("ledger signing-key versions/history is required")

    retention = _require_mapping(root["retention"], "retention")
    if set(retention) != {"backup_window_days", "policy_version"}:
        raise ValueError("retention evidence contains fields outside the schema allowlist")
    if int(retention.get("backup_window_days", 0)) <= 0 or not retention.get("policy_version"):
        raise ValueError("retention policy evidence is invalid")
    gates = _require_mapping(root["gates"], "gates")
    expected_gates = {"pg_restore_list", "hashes", "object_inventory", "references"}
    if set(gates) != expected_gates or not all(gates.values()):
        raise ValueError("all backup validation gates must pass")


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def atomic_publish_local(
    staging: Path,
    published: Path,
    manifest: Mapping[str, Any],
    final_validator: Callable[[], None],
) -> None:
    """Reference implementation for atomic directory publication in tests/drills."""
    if not staging.is_dir() or published.exists():
        raise ValueError("staging must exist and published destination must not exist")
    final_validator()
    validate_backup_manifest(manifest)
    payload = _canonical_json(manifest)
    manifest_tmp = staging / ".manifest.json.tmp"
    complete_tmp = staging / ".COMPLETE.tmp"
    manifest_tmp.write_bytes(payload)
    complete_tmp.write_text(hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii")
    os.replace(manifest_tmp, staging / "manifest.json")
    os.replace(complete_tmp, staging / "COMPLETE")
    published.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, published)


def validate_off_host_destination(destination: str, application_host: str, forbidden_paths: Iterable[str]) -> str:
    parsed = urlparse(destination)
    if parsed.scheme.lower() in LOCAL_DESTINATION_SCHEMES or not parsed.netloc:
        raise ValueError("backup destination must be an explicit off-host URI")
    host = (parsed.hostname or "").lower().rstrip(".")
    app_host = application_host.lower().rstrip(".")
    if host in LOCAL_DESTINATION_HOSTS or (app_host and host == app_host):
        raise ValueError("backup destination resolves to the application host")
    normalized_path = parsed.path.replace("\\", "/").lower().rstrip("/")
    for forbidden in (*DEFAULT_FORBIDDEN_DATA_PATHS, *forbidden_paths):
        candidate = str(forbidden).replace("\\", "/").lower().rstrip("/")
        if candidate and (normalized_path == candidate or normalized_path.startswith(candidate + "/") or candidate in normalized_path):
            raise ValueError(f"backup destination uses forbidden data-volume path: {forbidden}")
    return destination


def validate_secret_files(paths: Sequence[Path]) -> None:
    if not paths:
        raise ValueError("secret files are required")
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError("all backup, prune, restore, ledger, and signing secret files must be distinct")
    for path in resolved:
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError(f"secret file is missing or empty: {path}")
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise ValueError(f"secret file permissions must be 0600 or stricter: {path}")


def plan_prune(catalog: Sequence[Mapping[str, Any]], retention_days: int, now: datetime) -> list[str]:
    if retention_days <= 0 or now.tzinfo is None:
        raise ValueError("retention policy and timezone-aware current time are required")
    if not catalog:
        raise ValueError("cannot prune an empty backup catalog")
    ordered = sorted(catalog, key=lambda item: _parse_utc(str(item.get("backup_cutoff_utc", ""))))
    latest = ordered[-1]
    if latest.get("complete") is not True or latest.get("valid") is not True:
        raise ValueError("latest backup is incomplete or invalid; prune fails closed")
    complete = [item for item in ordered if item.get("complete") is True]
    if any(item.get("backup_window_days") != retention_days for item in complete):
        raise ValueError("retention policy mismatch; prune fails closed")
    valid = [item for item in complete if item.get("valid") is True]
    if len(valid) < 2:
        raise ValueError("at least two valid restore points must remain")
    protected = {str(item["backup_run_id"]) for item in valid[-2:]}
    cutoff = now - timedelta(days=retention_days)
    deletions = []
    for item in valid:
        run_id = str(item.get("backup_run_id", ""))
        if not RUN_ID_RE.fullmatch(run_id):
            raise ValueError("invalid backup_run_id in catalog")
        if run_id not in protected and _parse_utc(str(item["backup_cutoff_utc"])) < cutoff:
            deletions.append(run_id)
    return deletions


def validate_ledger_boundary(
    *,
    business_buckets: Sequence[str],
    ledger_bucket: str,
    business_capabilities: set[str],
    business_destination: str,
    ledger_destination: str,
    key_history: Mapping[str, Any],
) -> None:
    if ledger_bucket in business_buckets:
        raise ValueError("live ledger bucket must be excluded from business snapshots")
    if {"ledger:restore", "ledger:delete"}.intersection(business_capabilities):
        raise ValueError("business identities cannot restore or delete ledger archives")
    if business_destination.rstrip("/") == ledger_destination.rstrip("/"):
        raise ValueError("ledger archive requires an independent destination/failure domain")
    if key_history.get("schema_version") != 1:
        raise ValueError("ledger signing-key history schema is invalid")
    versions = key_history.get("versions")
    active = key_history.get("active_key_version")
    if not isinstance(versions, list) or len(versions) < 2:
        raise ValueError("versioned ledger signing-key history is required")
    version_names = [item.get("version") for item in versions if isinstance(item, Mapping)]
    active_items = [item for item in versions if isinstance(item, Mapping) and item.get("status") == "active"]
    if active not in version_names or len(active_items) != 1 or active_items[0].get("version") != active:
        raise ValueError("ledger active signing-key version/history mismatch")
    _scan_manifest(key_history)


def validate_disposable_recovery(project: str, volumes: Sequence[str], confirmed: str) -> None:
    if confirmed != "1":
        raise ValueError("disposable recovery requires DISPOSABLE_RECOVERY_CONFIRMED=1")
    if not re.fullmatch(r"ux09-backup-drill-[a-z0-9][a-z0-9-]{2,48}", project):
        raise ValueError("recovery project is not a disposable backup-drill project")
    if not volumes or any(not volume.startswith(project + "-") for volume in volumes):
        raise ValueError("recovery volume is not isolated to the disposable project")
    if any(re.search(r"(^|[-_])(prod|production)([-_]|$)", volume, re.IGNORECASE) for volume in volumes):
        raise ValueError("production volumes are forbidden")


def require_traffic_open_evidence(restore: Mapping[str, Any], b2b3: Mapping[str, Any] | None) -> bool:
    restore_gates = restore.get("gates") if isinstance(restore, Mapping) else None
    if restore.get("state") != "restored" or restore.get("traffic_open") is not False:
        raise ValueError("restore evidence must leave traffic closed")
    if not isinstance(restore_gates, Mapping) or not all(
        restore_gates.get(name) is True for name in ("database", "business_objects", "ledger_restored_first")
    ):
        raise ValueError("restore gates are incomplete; traffic remains closed")
    required = (
        "real_cli",
        "real_worker",
        "redelete_verified",
        "idempotency_verified",
        "tamper_failure_verified",
        "checkpoint_reclaim_verified",
    )
    if not isinstance(b2b3, Mapping) or b2b3.get("status") != "complete" or not all(b2b3.get(name) is True for name in required):
        raise ValueError("real B2B3 CLI and Worker recovery evidence is incomplete; traffic remains closed")
    return True


def build_drill_evidence(
    *,
    backup_cutoff_utc: str,
    failure_at_utc: str,
    recovery_started_utc: str,
    recovery_finished_utc: str,
    b2b3_complete: bool,
    smoke_complete: bool,
) -> dict[str, Any]:
    backup_cutoff = _parse_utc(backup_cutoff_utc)
    failure_at = _parse_utc(failure_at_utc)
    started = _parse_utc(recovery_started_utc)
    finished = _parse_utc(recovery_finished_utc)
    rpo_hours = (failure_at - backup_cutoff).total_seconds() / 3600
    rto_hours = (finished - started).total_seconds() / 3600
    gates = {
        "rpo_24h": 0 <= rpo_hours <= 24,
        "rto_4h": 0 <= rto_hours <= 4,
        "b2b3": b2b3_complete,
        "read_only_smoke": smoke_complete,
    }
    if not all(gates.values()):
        raise ValueError("RPO/RTO, real B2B3, and read-only smoke gates must all pass")
    return {
        "schema_version": 1,
        "rpo_hours": round(rpo_hours, 6),
        "rto_hours": round(rto_hours, 6),
        "gates": gates,
        "traffic_open": False,
    }


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json(value))


def _require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _secret_paths(*names: str) -> list[Path]:
    return [Path(_require_env(name)) for name in names]


def _run(command: Sequence[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _client(env_name: str, *arguments: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    executable = _require_env(env_name)
    if any(character.isspace() for character in executable):
        raise ValueError(f"{env_name} must be one executable path, not a shell command")
    return _run([executable, *arguments], capture=capture)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_hmac_signature(payload_path: Path, key_path: Path, output_path: Path) -> None:
    key = key_path.read_bytes()
    if len(key) < 32:
        raise ValueError("manifest signing key must contain at least 32 bytes")
    signature = hmac.new(key, payload_path.read_bytes(), hashlib.sha256).hexdigest()
    output_path.write_text(signature + "\n", encoding="ascii")


def verify_hmac_signature(payload_path: Path, key_path: Path, signature_path: Path) -> None:
    key = key_path.read_bytes()
    if len(key) < 32:
        raise ValueError("manifest signing key must contain at least 32 bytes")
    supplied = signature_path.read_text(encoding="ascii").strip()
    if not SHA256_RE.fullmatch(supplied):
        raise ValueError("manifest signature encoding is invalid")
    expected = hmac.new(key, payload_path.read_bytes(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise ValueError("manifest signature verification failed")


def _validate_business_inventory(path: Path) -> tuple[int, str]:
    inventory = _load_json(path)
    if not isinstance(inventory, Mapping) or inventory.get("schema_version") != 1:
        raise ValueError("business inventory schema is invalid")
    objects = inventory.get("objects")
    if not isinstance(objects, list):
        raise ValueError("business inventory must enumerate objects")
    for item in objects:
        if not isinstance(item, Mapping) or set(item) != {"key_hash", "sha256", "size_bytes"}:
            raise ValueError("business inventory entries must contain only key hash, content hash, and size")
        _require_sha256(item["key_hash"], "inventory.key_hash")
        _require_sha256(item["sha256"], "inventory.sha256")
        if int(item["size_bytes"]) < 0:
            raise ValueError("inventory size is invalid")
    return len(objects), _sha256_file(path)


def command_guard_disposable(_: argparse.Namespace) -> None:
    volumes = [item for item in _require_env("RECOVERY_VOLUME_NAMES").split(",") if item]
    validate_disposable_recovery(
        _require_env("COMPOSE_PROJECT_NAME"), volumes, os.environ.get("DISPOSABLE_RECOVERY_CONFIRMED", "")
    )


def command_validate_manifest(args: argparse.Namespace) -> None:
    validate_backup_manifest(_load_json(Path(args.path)))


def command_prune_plan(args: argparse.Namespace) -> None:
    catalog = _load_json(Path(args.catalog))
    if not isinstance(catalog, list):
        raise ValueError("catalog must be an array")
    for run_id in plan_prune(catalog, args.retention_days, datetime.now(timezone.utc)):
        print(run_id)


def command_inventory(args: argparse.Namespace) -> None:
    root = Path(args.root)
    if not root.is_dir():
        raise ValueError("inventory root must be a directory")
    objects = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        objects.append(
            {
                "key_hash": hashlib.sha256(relative).hexdigest(),
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    _write_json(Path(args.output), {"schema_version": 1, "objects": objects})


def command_catalog_local(args: argparse.Namespace) -> None:
    root = Path(args.root)
    catalog = []
    if not root.is_dir():
        raise ValueError("catalog root must be a directory")
    for manifest_path in sorted(root.rglob("manifest.json")):
        group = manifest_path.parent
        try:
            manifest = _load_json(manifest_path)
            complete = (group / "COMPLETE").is_file()
            valid = False
            if complete:
                marker = (group / "COMPLETE").read_text(encoding="ascii").strip()
                valid = marker == hashlib.sha256(_canonical_json(manifest)).hexdigest()
                if valid:
                    validate_backup_manifest(manifest)
                    dump = group / "database.dump"
                    snapshot = group / "business.snapshot"
                    inventory = group / "business.inventory.json"
                    valid = (
                        dump.is_file()
                        and snapshot.is_file()
                        and inventory.is_file()
                        and _sha256_file(dump) == manifest["database"]["sha256"]
                        and _sha256_file(snapshot) == manifest["business_snapshot"]["sha256"]
                        and _sha256_file(inventory) == manifest["business_snapshot"]["inventory_sha256"]
                    )
                    if valid:
                        object_count, _ = _validate_business_inventory(inventory)
                        valid = object_count == manifest["business_snapshot"]["object_count"]
                    if valid:
                        listed = _run([os.environ.get("PG_RESTORE_BIN", "pg_restore"), "--list", str(dump)], capture=True)
                        entries = sum(1 for line in listed.stdout.splitlines() if line and not line.startswith(";"))
                        valid = entries == manifest["database"]["restore_list_entries"]
            catalog.append(
                {
                    "backup_run_id": str(manifest.get("backup_run_id", group.name)),
                    "backup_cutoff_utc": str(manifest.get("backup_cutoff_utc", "")),
                    "complete": complete,
                    "valid": valid,
                    "backup_window_days": manifest.get("retention", {}).get("backup_window_days"),
                }
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            catalog.append(
                {
                    "backup_run_id": group.name,
                    "backup_cutoff_utc": "1970-01-01T00:00:00Z",
                    "complete": (group / "COMPLETE").is_file(),
                    "valid": False,
                    "backup_window_days": None,
                }
            )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(catalog, sort_keys=True) + "\n", encoding="utf-8")


def command_traffic_gate(args: argparse.Namespace) -> None:
    restore = _load_json(Path(args.restore_evidence))
    b2b3 = _load_json(Path(args.b2b3_evidence))
    require_traffic_open_evidence(restore, b2b3)
    marker = Path(args.marker)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("B2B3_COMPLETE_TRAFFIC_MAY_OPEN\n", encoding="ascii")


def command_backup(_: argparse.Namespace) -> None:
    run_id = _require_env("BACKUP_RUN_ID")
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("BACKUP_RUN_ID is invalid")
    destination = validate_off_host_destination(
        _require_env("BACKUP_DESTINATION"),
        _require_env("APPLICATION_HOST"),
        os.environ.get("FORBIDDEN_DATA_PATHS", "").split(os.pathsep),
    )
    pgpass, source_config, destination_config, signing_key = _secret_paths(
        "PGPASSFILE", "BUSINESS_SOURCE_CONFIG_FILE", "BACKUP_DESTINATION_CONFIG_FILE", "BACKUP_MANIFEST_SIGNING_KEY_FILE"
    )
    validate_secret_files([pgpass, source_config, destination_config, signing_key])
    ledger_manifest_path = Path(_require_env("LEDGER_ARCHIVE_MANIFEST_FILE"))
    staging_root = Path(_require_env("BACKUP_STAGING_ROOT"))
    staging = staging_root / f".pending-{run_id}"
    if staging.exists():
        raise ValueError("backup staging run already exists")
    staging.mkdir(parents=True, mode=0o700)
    try:
        dump = staging / "database.dump"
        restore_list = staging / "database.restore-list"
        snapshot = staging / "business.snapshot"
        inventory = staging / "business.inventory.json"
        references_path = staging / "reference-validation.json"
        _run([
            os.environ.get("PG_DUMP_BIN", "pg_dump"), "--format=custom", "--file", str(dump),
            "--host", _require_env("PGHOST"), "--port", os.environ.get("PGPORT", "5432"),
            "--username", _require_env("PGUSER"), "--dbname", _require_env("PGDATABASE"), "--no-password",
        ])
        if not dump.is_file() or dump.stat().st_size <= 0:
            raise ValueError("pg_dump produced an empty custom-format dump")
        listed = _run([os.environ.get("PG_RESTORE_BIN", "pg_restore"), "--list", str(dump)], capture=True)
        restore_list.write_text(listed.stdout, encoding="utf-8")
        list_entries = sum(1 for line in listed.stdout.splitlines() if line and not line.startswith(";"))
        if list_entries <= 0:
            raise ValueError("pg_restore --list produced no archive entries")
        buckets = [item for item in _require_env("BUSINESS_BUCKETS").split(",") if item]
        ledger_bucket = _require_env("LEDGER_BUCKET")
        if ledger_bucket in buckets:
            raise ValueError("ledger bucket is forbidden in business snapshot")
        _client(
            "BUSINESS_SNAPSHOT_CLIENT", "snapshot", "--config-file", str(source_config), "--buckets", ",".join(buckets),
            "--output", str(snapshot), "--inventory", str(inventory),
        )
        if not snapshot.is_file() or snapshot.stat().st_size <= 0:
            raise ValueError("business snapshot is empty")
        object_count, inventory_hash = _validate_business_inventory(inventory)
        _client(
            "REFERENCE_VALIDATOR", "validate", "--inventory", str(inventory), "--result", str(references_path)
        )
        references = _require_mapping(_load_json(references_path), "reference validation")
        if int(references.get("mismatches", -1)) != 0:
            raise ValueError("reference validation failed")
        ledger = _require_mapping(_load_json(ledger_manifest_path), "ledger archive manifest")
        manifest = {
            "schema_version": 1,
            "backup_run_id": run_id,
            "state": "complete",
            "backup_cutoff_utc": _require_env("BACKUP_CUTOFF_UTC"),
            "schedule_interval_hours": 12,
            "toolchain": {
                "image": _require_env("BACKUP_IMAGE"),
                "image_digest": _require_env("BACKUP_IMAGE_DIGEST"),
                "postgres": "16.9",
                "minio_client": "RELEASE.2025-07-21T05-28-08Z",
                "destination_client": "rclone-1.70.3",
            },
            "database": {
                "format": "custom", "sha256": _sha256_file(dump), "size_bytes": dump.stat().st_size,
                "restore_list_entries": list_entries,
            },
            "business_snapshot": {
                "sha256": _sha256_file(snapshot), "size_bytes": snapshot.stat().st_size,
                "object_count": object_count, "inventory_sha256": inventory_hash,
            },
            "reference_validation": {"checked": int(references.get("checked", 0)), "mismatches": 0},
            "ledger_archive": {
                "archive_run_id": ledger["archive_run_id"], "cutoff_utc": ledger["cutoff_utc"],
                "manifest_sha256": _sha256_file(ledger_manifest_path),
                "signing_key_versions": ledger["signing_key_versions"],
            },
            "retention": {
                "backup_window_days": int(_require_env("BACKUP_WINDOW_DAYS")),
                "policy_version": _require_env("RETENTION_POLICY_VERSION"),
            },
            "gates": {"pg_restore_list": True, "hashes": True, "object_inventory": True, "references": True},
        }
        validate_backup_manifest(manifest)
        payload = _canonical_json(manifest)
        (staging / "manifest.json").write_bytes(payload)
        write_hmac_signature(staging / "manifest.json", signing_key, staging / "manifest.sig")
        (staging / "COMPLETE").write_text(hashlib.sha256(payload).hexdigest() + "\n", encoding="ascii")
        try:
            _client(
                "BACKUP_DESTINATION_CLIENT", "stage-group", "--config-file", str(destination_config),
                "--destination", destination, "--run-id", run_id, "--source", str(staging),
            )
            _client(
                "BACKUP_DESTINATION_CLIENT", "publish-group", "--config-file", str(destination_config),
                "--destination", destination, "--run-id", run_id,
            )
        except Exception:
            try:
                _client(
                    "BACKUP_DESTINATION_CLIENT", "abort-group", "--config-file", str(destination_config),
                    "--destination", destination, "--run-id", run_id,
                )
            except Exception:
                pass
            raise
        print(f"backup complete: run_id={run_id}")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def command_prune(_: argparse.Namespace) -> None:
    destination = validate_off_host_destination(
        _require_env("BACKUP_DESTINATION"), _require_env("APPLICATION_HOST"),
        os.environ.get("FORBIDDEN_DATA_PATHS", "").split(os.pathsep),
    )
    prune_config = Path(_require_env("BACKUP_PRUNE_CONFIG_FILE"))
    validate_secret_files([prune_config])
    catalog_path = Path(_require_env("BACKUP_CATALOG_FILE"))
    _client(
        "BACKUP_DESTINATION_CLIENT", "catalog", "--config-file", str(prune_config),
        "--destination", destination, "--output", str(catalog_path),
    )
    catalog = _load_json(catalog_path)
    if not isinstance(catalog, list):
        raise ValueError("backup catalog must be an array")
    deletions = plan_prune(catalog, int(_require_env("BACKUP_WINDOW_DAYS")), datetime.now(timezone.utc))
    for run_id in deletions:
        _client(
            "BACKUP_DESTINATION_CLIENT", "delete-complete-group", "--config-file", str(prune_config),
            "--destination", destination, "--run-id", run_id,
        )
    print(f"prune complete: deleted_groups={len(deletions)}")


def command_restore(_: argparse.Namespace) -> None:
    command_guard_disposable(argparse.Namespace())
    business_destination = validate_off_host_destination(
        _require_env("BACKUP_DESTINATION"), _require_env("APPLICATION_HOST"),
        os.environ.get("FORBIDDEN_DATA_PATHS", "").split(os.pathsep),
    )
    ledger_destination = validate_off_host_destination(
        _require_env("LEDGER_ARCHIVE_DESTINATION"), _require_env("APPLICATION_HOST"),
        os.environ.get("FORBIDDEN_DATA_PATHS", "").split(os.pathsep),
    )
    if business_destination.rstrip("/") == ledger_destination.rstrip("/"):
        raise ValueError("ledger and business restore destinations must be independent")
    pgpass, business_restore, destination_restore, ledger_restore, manifest_signing_key = _secret_paths(
        "PGPASSFILE", "BUSINESS_RESTORE_CONFIG_FILE", "BACKUP_RESTORE_CONFIG_FILE", "LEDGER_RESTORE_CONFIG_FILE",
        "BACKUP_MANIFEST_SIGNING_KEY_FILE",
    )
    validate_secret_files([pgpass, business_restore, destination_restore, ledger_restore, manifest_signing_key])
    run_id = _require_env("RESTORE_BACKUP_RUN_ID")
    workspace = Path(_require_env("RESTORE_STAGING_ROOT")) / run_id
    if workspace.exists():
        raise ValueError("restore staging path already exists")
    workspace.mkdir(parents=True, mode=0o700)
    try:
        _client(
            "LEDGER_ARCHIVE_CLIENT", "restore-latest", "--config-file", str(ledger_restore),
            "--destination", ledger_destination,
        )
        _client(
            "BACKUP_DESTINATION_CLIENT", "fetch-complete-group", "--config-file", str(destination_restore),
            "--destination", business_destination, "--run-id", run_id, "--output", str(workspace),
        )
        manifest = _load_json(workspace / "manifest.json")
        validate_backup_manifest(manifest)
        verify_hmac_signature(
            workspace / "manifest.json", manifest_signing_key, workspace / "manifest.sig"
        )
        marker = (workspace / "COMPLETE").read_text(encoding="ascii").strip()
        if marker != hashlib.sha256(_canonical_json(manifest)).hexdigest():
            raise ValueError("COMPLETE marker does not match manifest")
        dump = workspace / "database.dump"
        snapshot = workspace / "business.snapshot"
        if _sha256_file(dump) != manifest["database"]["sha256"] or _sha256_file(snapshot) != manifest["business_snapshot"]["sha256"]:
            raise ValueError("restore-point hashes do not match manifest")
        inventory = workspace / "business.inventory.json"
        object_count, inventory_hash = _validate_business_inventory(inventory)
        if inventory_hash != manifest["business_snapshot"]["inventory_sha256"] or object_count != manifest["business_snapshot"]["object_count"]:
            raise ValueError("business inventory does not match manifest")
        _run([os.environ.get("PG_RESTORE_BIN", "pg_restore"), "--list", str(dump)])
        _run([
            os.environ.get("PG_RESTORE_BIN", "pg_restore"), "--exit-on-error", "--clean", "--if-exists",
            "--no-owner", "--host", _require_env("PGHOST"), "--port", os.environ.get("PGPORT", "5432"),
            "--username", _require_env("PGUSER"), "--dbname", _require_env("PGDATABASE"), str(dump),
        ])
        _client(
            "BUSINESS_RESTORE_CLIENT", "restore", "--config-file", str(business_restore),
            "--snapshot", str(snapshot),
        )
        evidence = {
            "schema_version": 1,
            "state": "restored",
            "traffic_open": False,
            "b2b3_status": "pending_external_cli_and_worker",
            "gates": {"database": True, "business_objects": True, "ledger_restored_first": True},
        }
        _write_json(Path(_require_env("RESTORE_EVIDENCE_FILE")), evidence)
        print(f"restore complete with traffic closed: run_id={run_id}")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def command_ledger_archive(_: argparse.Namespace) -> None:
    destination = validate_off_host_destination(
        _require_env("LEDGER_ARCHIVE_DESTINATION"), _require_env("APPLICATION_HOST"),
        os.environ.get("FORBIDDEN_DATA_PATHS", "").split(os.pathsep),
    )
    source, append, signing_key = _secret_paths(
        "LEDGER_SOURCE_CONFIG_FILE", "LEDGER_ARCHIVE_CONFIG_FILE", "LEDGER_MANIFEST_SIGNING_KEY_FILE"
    )
    validate_secret_files([source, append, signing_key])
    history = _load_json(Path(_require_env("LEDGER_SIGNING_KEY_HISTORY_FILE")))
    validate_ledger_boundary(
        business_buckets=[item for item in _require_env("BUSINESS_BUCKETS").split(",") if item],
        ledger_bucket=_require_env("LEDGER_BUCKET"),
        business_capabilities={"business:read", "destination:append"},
        business_destination=_require_env("BACKUP_DESTINATION"),
        ledger_destination=destination,
        key_history=history,
    )
    archive_run_id = _require_env("LEDGER_ARCHIVE_RUN_ID")
    work = Path(_require_env("LEDGER_STAGING_ROOT")) / f".pending-{archive_run_id}"
    work.mkdir(parents=True, mode=0o700)
    try:
        archive = work / "ledger.snapshot"
        summary = work / "ledger-summary.json"
        _client(
            "LEDGER_ARCHIVE_CLIENT", "snapshot", "--config-file", str(source), "--bucket", _require_env("LEDGER_BUCKET"),
            "--output", str(archive), "--summary", str(summary),
        )
        if not archive.is_file() or archive.stat().st_size <= 0:
            raise ValueError("ledger archive is empty")
        summary_value = _require_mapping(_load_json(summary), "ledger summary")
        manifest = {
            "schema_version": 1,
            "archive_run_id": archive_run_id,
            "cutoff_utc": _require_env("LEDGER_ARCHIVE_CUTOFF_UTC"),
            "archive_sha256": _sha256_file(archive),
            "size_bytes": archive.stat().st_size,
            "entry_count": int(summary_value.get("entry_count", -1)),
            "signing_key_versions": [item["version"] for item in history["versions"]],
            "signing_key_version": history["active_key_version"],
            "lifecycle_policy_version": _require_env("LEDGER_LIFECYCLE_POLICY_VERSION"),
        }
        if manifest["entry_count"] < 0:
            raise ValueError("ledger archive entry count is invalid")
        _scan_manifest(manifest)
        _write_json(work / "ledger-manifest.json", manifest)
        write_hmac_signature(work / "ledger-manifest.json", signing_key, work / "ledger-manifest.sig")
        (work / "COMPLETE").write_text(_sha256_file(work / "ledger-manifest.json") + "\n", encoding="ascii")
        _client(
            "LEDGER_ARCHIVE_CLIENT", "publish", "--config-file", str(append), "--destination", destination,
            "--run-id", archive_run_id, "--source", str(work),
        )
        output = Path(_require_env("LEDGER_ARCHIVE_MANIFEST_FILE"))
        _write_json(output, manifest)
        print(f"ledger archive complete: run_id={archive_run_id}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def command_drill(_: argparse.Namespace) -> None:
    command_guard_disposable(argparse.Namespace())
    _require_env("B2B3_CLI_COMMAND")
    _require_env("B2B3_WORKER_COMMAND")
    raise ValueError(
        "Phase 6C foundation exposes B2B3_CLI_COMMAND and B2B3_WORKER_COMMAND but does not implement B2B3; "
        "the complete real restore drill and traffic-open gate remain unavailable"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-manifest")
    validate.add_argument("path")
    validate.set_defaults(handler=command_validate_manifest)
    prune_plan = subparsers.add_parser("prune-plan")
    prune_plan.add_argument("catalog")
    prune_plan.add_argument("retention_days", type=int)
    prune_plan.set_defaults(handler=command_prune_plan)
    inventory = subparsers.add_parser("inventory")
    inventory.add_argument("root")
    inventory.add_argument("output")
    inventory.set_defaults(handler=command_inventory)
    catalog = subparsers.add_parser("catalog-local")
    catalog.add_argument("root")
    catalog.add_argument("output")
    catalog.set_defaults(handler=command_catalog_local)
    disposable = subparsers.add_parser("guard-disposable")
    disposable.set_defaults(handler=command_guard_disposable)
    traffic = subparsers.add_parser("traffic-gate")
    traffic.add_argument("restore_evidence")
    traffic.add_argument("b2b3_evidence")
    traffic.add_argument("marker")
    traffic.set_defaults(handler=command_traffic_gate)
    for name, handler in (
        ("backup", command_backup),
        ("prune", command_prune),
        ("restore", command_restore),
        ("ledger-archive", command_ledger_archive),
        ("drill", command_drill),
    ):
        subparser = subparsers.add_parser(name)
        subparser.set_defaults(handler=handler)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        args.handler(args)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        print(f"backup contract failed closed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
