"""Password hashing and verification utilities using Argon2id.

Enforces memory-hard, side-channel resistant password hashing compliant
with OWASP recommendations and Directriz 4.
"""

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Initialize Argon2id hasher with recommended security parameters
_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using Argon2id with cryptographically random salt."""
    if not plain_password:
        raise ValueError("Password cannot be empty")
    return _ph.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash in constant time."""
    if not plain_password or not hashed_password:
        return False
    try:
        return _ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Check if the password hash needs to be recomputed with updated parameters."""
    try:
        return _ph.check_needs_rehash(hashed_password)
    except (VerificationError, InvalidHashError):
        return True
