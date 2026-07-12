import base64
import hashlib
import hmac
from dataclasses import dataclass

from cryptography.fernet import Fernet


@dataclass(frozen=True, repr=False)
class ProtectedContact:
    ciphertext: bytes
    lookup_hash: str
    masked_value: str

    def __repr__(self) -> str:
        return "ProtectedContact(ciphertext=<redacted>, lookup_hash=<redacted>, masked_value=%r)" % self.masked_value


class ContactCipher:
    def __init__(self, encryption_key: bytes, lookup_secret: bytes) -> None:
        key = base64.urlsafe_b64encode(hashlib.sha256(encryption_key).digest())
        self._cipher = Fernet(key)
        self._lookup_secret = lookup_secret

    @staticmethod
    def normalize(kind: str, value: str) -> str:
        value = value.strip()
        if kind.strip().casefold() == "email":
            return value.casefold()
        return "".join(character for character in value if character.isdigit() or character == "+")

    @staticmethod
    def mask(kind: str, value: str) -> str:
        if kind.strip().casefold() == "email":
            local, _, domain = value.partition("@")
            return f"{local[:1].casefold()}***@{domain.casefold()}"
        digits = "".join(character for character in value if character.isdigit())
        return f"***{digits[-4:]}" if digits else "***"

    def protect(self, kind: str, value: str) -> ProtectedContact:
        plaintext = value.strip()
        normalized = self.normalize(kind, plaintext)
        digest = hmac.new(self._lookup_secret, normalized.encode(), hashlib.sha256).hexdigest()
        return ProtectedContact(self._cipher.encrypt(plaintext.encode()), digest, self.mask(kind, plaintext))

    def decrypt(self, ciphertext: bytes) -> str:
        return self._cipher.decrypt(ciphertext).decode()
