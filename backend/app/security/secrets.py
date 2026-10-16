"""Random tokens, token hashing and at-rest encryption of stored secrets."""

import base64
import hashlib
import logging
import os
import secrets
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)


def new_token(nbytes: int = 32) -> str:
    """URL-safe random token (session cookies, invite and reset links)."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Tokens are stored only as SHA-256 hashes, so a database leak can't be replayed as live sessions."""
    return hashlib.sha256(token.encode()).hexdigest()


def write_private_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)


@lru_cache
def _secret_key() -> str:
    settings = get_settings()
    if settings.secret_key:
        return settings.secret_key
    path = settings.data_dir / "secret.key"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    key = new_token(48)
    write_private_file(path, key)
    logger.warning("Generated a new secret key at %s - back it up with your database.", path)
    return key


@lru_cache
def _fernet() -> Fernet:
    digest = hashlib.sha256(b"jacklyn/at-rest-encryption/v1|" + _secret_key().encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Stored secret can't be decrypted - was JACKLYN_SECRET_KEY changed?") from exc
