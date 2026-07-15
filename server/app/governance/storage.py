from __future__ import annotations

import hashlib
import hmac
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from minio.error import S3Error


LEDGER_FIELDS = frozenset(
    {
        "schema_version",
        "organization_id",
        "deletion_request_id",
        "candidate_id",
        "completed_at",
        "manifest_hash",
        "object_keys",
        "database_redaction_checksum",
    }
)


class GovernanceStorageError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("ledger completion time must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class LedgerEntry:
    organization_id: UUID
    deletion_request_id: UUID
    candidate_id: UUID
    completed_at: datetime
    manifest_hash: str
    object_keys: tuple[str, ...]
    database_redaction_checksum: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("ledger schema version is unsupported")
        if any(
            len(value) != 64
            or value.lower() != value
            or any(char not in "0123456789abcdef" for char in value)
            for value in (self.manifest_hash, self.database_redaction_checksum)
        ):
            raise ValueError("ledger checksums must be lowercase sha256")
        normalized = tuple(sorted(set(self.object_keys)))
        if len(normalized) != len(self.object_keys) or any(not key for key in normalized):
            raise ValueError("ledger object keys must be unique and non-empty")
        object.__setattr__(self, "object_keys", normalized)
        _utc(self.completed_at)

    def unsigned_document(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "organization_id": str(self.organization_id),
            "deletion_request_id": str(self.deletion_request_id),
            "candidate_id": str(self.candidate_id),
            "completed_at": _utc(self.completed_at),
            "manifest_hash": self.manifest_hash,
            "object_keys": list(self.object_keys),
            "database_redaction_checksum": self.database_redaction_checksum,
        }

    def signed_document(self, signing_key: bytes) -> dict[str, Any]:
        unsigned = self.unsigned_document()
        return {
            **unsigned,
            "signature": hmac.new(signing_key, _canonical(unsigned), hashlib.sha256).hexdigest(),
        }

    @classmethod
    def verify_document(cls, document: dict[str, Any], signing_key: bytes) -> "LedgerEntry":
        try:
            if not isinstance(document, dict) or set(document) != LEDGER_FIELDS | {"signature"}:
                raise ValueError
            signature = document["signature"]
            if not isinstance(signature, str) or len(signature) != 64:
                raise ValueError
            unsigned = {key: document[key] for key in LEDGER_FIELDS}
            expected = hmac.new(signing_key, _canonical(unsigned), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise GovernanceStorageError("ledger_signature_invalid")
            if document["schema_version"] != 1 or not isinstance(document["object_keys"], list):
                raise ValueError
            completed_at = datetime.fromisoformat(document["completed_at"].replace("Z", "+00:00"))
            return cls(
                organization_id=UUID(document["organization_id"]),
                deletion_request_id=UUID(document["deletion_request_id"]),
                candidate_id=UUID(document["candidate_id"]),
                completed_at=completed_at,
                manifest_hash=document["manifest_hash"],
                object_keys=tuple(document["object_keys"]),
                database_redaction_checksum=document["database_redaction_checksum"],
            )
        except GovernanceStorageError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError):
            raise GovernanceStorageError("ledger_invalid") from None


@dataclass(frozen=True)
class LedgerReceipt:
    object_key: str
    sha256: str


def _read_object(response) -> bytes:
    try:
        return response.read()
    finally:
        close = getattr(response, "close", None)
        if close is not None:
            close()
        release = getattr(response, "release_conn", None)
        if release is not None:
            release()


class SignedLedgerAdapter:
    def __init__(self, client, bucket: str, prefix: str, signing_key: bytes) -> None:
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.rstrip("/") + "/"
        self.signing_key = bytes(signing_key)

    def object_key(self, entry: LedgerEntry) -> str:
        return (
            f"{self.prefix}v1/{entry.organization_id}/"
            f"{entry.deletion_request_id}.json"
        )

    def _encoded(self, entry: LedgerEntry) -> bytes:
        return _canonical(entry.signed_document(self.signing_key))

    def _put_if_absent(self, object_key: str, encoded: bytes) -> None:
        conditional = getattr(self.client, "_execute", None)
        if conditional is None:
            raise GovernanceStorageError("ledger_conditional_create_unsupported")
        response = conditional(
            "PUT",
            self.bucket,
            object_key,
            body=encoded,
            headers={
                "Content-Type": "application/json",
                "If-None-Match": "*",
            },
        )
        close = getattr(response, "close", None)
        if close is not None:
            close()
        release = getattr(response, "release_conn", None)
        if release is not None:
            release()

    def read(self, object_key: str) -> LedgerEntry | None:
        try:
            raw = _read_object(self.client.get_object(self.bucket, object_key))
        except S3Error as error:
            if error.code in {"NoSuchKey", "NoSuchObject"}:
                return None
            raise GovernanceStorageError("ledger_read_failed") from None
        except Exception:
            raise GovernanceStorageError("ledger_read_failed") from None
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GovernanceStorageError("ledger_invalid") from None
        return LedgerEntry.verify_document(document, self.signing_key)

    def write(self, entry: LedgerEntry) -> LedgerReceipt:
        object_key = self.object_key(entry)
        encoded = self._encoded(entry)
        try:
            existing = self.read(object_key)
        except GovernanceStorageError as error:
            if error.code in {"ledger_invalid", "ledger_signature_invalid"}:
                raise GovernanceStorageError("ledger_existing_mismatch") from None
            raise
        if existing is not None:
            if existing != entry:
                raise GovernanceStorageError("ledger_existing_mismatch")
        else:
            try:
                self._put_if_absent(object_key, encoded)
            except S3Error as error:
                if error.code not in {"PreconditionFailed", "ConditionalRequestConflict"}:
                    raise GovernanceStorageError("ledger_write_failed") from None
                try:
                    if self.read(object_key) != entry:
                        raise GovernanceStorageError("ledger_existing_mismatch")
                except GovernanceStorageError:
                    raise GovernanceStorageError("ledger_existing_mismatch") from None
            except GovernanceStorageError:
                raise
            except Exception:
                raise GovernanceStorageError("ledger_write_failed") from None
            try:
                if self.read(object_key) != entry:
                    raise GovernanceStorageError("ledger_existing_mismatch")
            except GovernanceStorageError as error:
                if error.code in {
                    "ledger_invalid",
                    "ledger_signature_invalid",
                    "ledger_existing_mismatch",
                }:
                    raise GovernanceStorageError("ledger_existing_mismatch") from None
                raise
        return LedgerReceipt(object_key, hashlib.sha256(encoded).hexdigest())


class DeleteOnlyObjectAdapter:
    def __init__(self, client) -> None:
        self.client = client

    def delete(self, bucket: str, object_key: str) -> None:
        if not bucket or not object_key:
            raise GovernanceStorageError("object_reference_invalid")
        try:
            self.client.remove_object(bucket, object_key)
        except Exception:
            raise GovernanceStorageError("object_delete_failed") from None
