"""Password hashing (Argon2id) and policy."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_LENGTH = 12
MAX_LENGTH = 128  # bounds hashing cost per request

_hasher = PasswordHasher()  # Argon2id with the library's current recommended parameters
# Verified against when an email is unknown, so failed logins take the same time either way.
_DUMMY_HASH = _hasher.hash("jacklyn-timing-equalizer")


class WeakPasswordError(ValueError):
    pass


def check_policy(password: str, *, email: str | None = None) -> None:
    if len(password) < MIN_LENGTH:
        raise WeakPasswordError(f"Use at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        raise WeakPasswordError(f"Use at most {MAX_LENGTH} characters.")
    if len(set(password)) < 5:
        raise WeakPasswordError("That password is too repetitive.")
    if email and password.strip().lower() == email.strip().lower():
        raise WeakPasswordError("Don't use your email as your password.")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
