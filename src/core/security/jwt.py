"""JSON Web Token (JWT) handling module.

Generates and validates ephemeral tokens signed cryptographically with HS256,
including mandatory verification of expiration ('exp'), issued-at ('iat'),
and subject ('sub').
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from src.config import get_settings


class TokenSecurityError(Exception):
    """Base exception for JWT security validation failures."""

    pass


class TokenExpiredError(TokenSecurityError):
    """Raised when the provided JWT token has expired."""

    pass


class TokenInvalidError(TokenSecurityError):
    """Raised when the JWT token signature or payload is invalid."""

    pass


def create_access_token(
    user_id: UUID | str,
    organization_id: UUID | str,
    role: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Generate an ephemeral, cryptographically signed JWT access token.

    Args:
        user_id: Subject (sub) identifier of the authenticated user.
        organization_id: Multi-tenant boundary identifier.
        role: RBAC role assigned to the user.
        expires_delta: Optional custom duration; defaults to settings duration.
        extra_claims: Optional non-sensitive additional claims.

    Returns:
        Encoded and signed JWT string.
    """
    settings = get_settings()
    now = datetime.now(UTC)

    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org_id": str(organization_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    if extra_claims:
        # Prevent overriding critical security claims
        reserved_claims = {"sub", "org_id", "role", "iat", "exp"}
        for k, v in extra_claims.items():
            if k not in reserved_claims:
                payload[k] = v

    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Verifies signature, expiration, and presence of mandatory claims.

    Args:
        token: The encoded JWT token string.

    Returns:
        The decoded claims payload dictionary.

    Raises:
        TokenExpiredError: If the token expiration time is in the past.
        TokenInvalidError: If the signature is invalid or required claims are missing.
    """
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={
                "require": ["exp", "iat", "sub"],
                "verify_exp": True,
                "verify_iat": True,
                "verify_signature": True,
            },
        )
    except ExpiredSignatureError as e:
        raise TokenExpiredError("Access token has expired") from e
    except InvalidTokenError as e:
        raise TokenInvalidError("Invalid token signature or structure") from e

    # Validate essential tenant and identity claims
    if "org_id" not in payload or "role" not in payload:
        raise TokenInvalidError("Token is missing mandatory authorization claims")

    return payload
