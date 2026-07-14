from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID


class DeletionDomainError(ValueError):
    """A non-disclosing deletion-domain rejection."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_ALLOWED_TRANSITIONS = {
    "requested": frozenset({"approved"}),
    "approved": frozenset({"executing"}),
    "executing": frozenset({"completed", "failed"}),
    "failed": frozenset({"approved"}),
    "completed": frozenset({"completed"}),
}

_IMPACT_COUNT_KEYS = (
    "contacts",
    "resumes",
    "applications",
    "screening_records",
    "interviews",
    "feedback_records",
    "talent_memberships",
    "resume_objects",
    "temporary_exports",
)
_MAX_IMPACT_COUNT = 2_147_483_647


def advance_deletion_status(current: str, target: str) -> str:
    if target not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise DeletionDomainError("invalid_deletion_state_transition")
    return target


def validate_new_request(*, has_completed_request: bool) -> None:
    if has_completed_request:
        raise DeletionDomainError("candidate_deletion_completed")


def validate_approval(
    *,
    requester_id: object,
    approver_id: object,
    has_active_application: bool,
    has_active_hold: bool,
    candidate_version: int,
    expected_candidate_version: int,
    request_version: int,
    expected_request_version: int,
    manifest_hash: str,
    expected_manifest_hash: str,
) -> None:
    if requester_id == approver_id:
        raise DeletionDomainError("self_approval_forbidden")
    if has_active_application:
        raise DeletionDomainError("active_application_exists")
    if has_active_hold:
        raise DeletionDomainError("legal_hold_active")
    if candidate_version != expected_candidate_version:
        raise DeletionDomainError("stale_candidate_version")
    if request_version != expected_request_version:
        raise DeletionDomainError("stale_request_version")
    if not hmac.compare_digest(manifest_hash, expected_manifest_hash):
        raise DeletionDomainError("stale_manifest_hash")


def hold_placement_outcome(status: str) -> tuple[str, str | None]:
    if status == "requested":
        return status, None
    if status == "approved":
        return "failed", "legal_hold_active"
    if status == "executing":
        raise DeletionDomainError("deletion_already_executing")
    raise DeletionDomainError("invalid_deletion_state_transition")


def _utc_isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def impact_manifest_projection(
    private_manifest: dict[str, Any],
    *,
    request_id: UUID,
    candidate_version: int,
    policy_version: int,
    backup_window_ends_at: datetime,
) -> dict[str, Any]:
    private_counts = private_manifest.get("counts")
    if not isinstance(private_counts, dict):
        private_counts = {}
    counts: dict[str, int] = {}
    for key in _IMPACT_COUNT_KEYS:
        value = private_counts.get(key, 0)
        if type(value) is not int or not 0 <= value <= _MAX_IMPACT_COUNT:
            raise DeletionDomainError("invalid_impact_manifest")
        counts[key] = value
    return {
        "schema_version": 1,
        "candidate_ref": str(request_id),
        "candidate_version": candidate_version,
        "policy_version": policy_version,
        "counts": counts,
        "backup_window_ends_at": _utc_isoformat(backup_window_ends_at),
    }


def canonical_manifest_hash(private_manifest: dict[str, Any]) -> str:
    try:
        canonical = json.dumps(
            private_manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        raise DeletionDomainError("invalid_impact_manifest") from None
    return hashlib.sha256(canonical).hexdigest()


def validate_recovery_generation(generation: object) -> int:
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
        raise DeletionDomainError("invalid_recovery_generation")
    return generation
