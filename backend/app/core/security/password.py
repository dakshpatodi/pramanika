"""
Password hashing utilities.

Bcrypt via passlib. The plaintext password is never stored, logged, or
returned anywhere in this codebase - only the output of `hash_password`
(see `User.password_hash`) is ever persisted.
"""

from passlib.context import CryptContext

# bcrypt only for now. `deprecated="auto"` matters once a second scheme is
# ever added here: existing hashes would still verify, but `verify_password`
# would flag them so the caller can transparently re-hash on next login.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt silently ignores any bytes past the 72nd - two different long
# passwords that share the same first 72 bytes would hash identically.
# Rejecting overlong passwords explicitly (rather than fixing this
# silently) also gives Milestone 3's registration validation something
# concrete to check for and message back to the user.
_MAX_PASSWORD_BYTES = 72


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password for storage.

    Raises:
        ValueError: if the password exceeds bcrypt's 72-byte input limit.
    """
    if len(plain_password.encode("utf-8")) > _MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must not exceed {_MAX_PASSWORD_BYTES} bytes.")
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a plaintext password attempt against a stored bcrypt hash."""
    if len(plain_password.encode("utf-8")) > _MAX_PASSWORD_BYTES:
        return False
    return _pwd_context.verify(plain_password, password_hash)