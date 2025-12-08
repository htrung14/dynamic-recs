"""
Symmetric encryption helpers for sensitive secrets (e.g., Stremio credentials).
"""
import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import settings


def _fernet() -> Fernet:
    """Derive a Fernet instance from the configured credential key.
    Uses SHA-256 of the secret to produce a 32-byte key and urlsafe-base64 encodes it.
    """
    secret = settings.STREMIO_CREDENTIAL_KEY or settings.TOKEN_SALT
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    """Encrypt a plaintext string; returns urlsafe base64 token."""
    f = _fernet()
    token = f.encrypt(value.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(token: str) -> Optional[str]:
    """Decrypt an encrypted token; returns None if invalid."""
    f = _fernet()
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None
    except Exception:
        return None
