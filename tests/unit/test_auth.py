"""Unit tests for authentication, Argon2id password hashing, and JWT tokens."""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.api.schemas.auth import (
    UserRegisterRequest,
    UserResponse,
)
from src.core.security.jwt import (
    TokenExpiredError,
    TokenInvalidError,
    create_access_token,
    decode_access_token,
)
from src.core.security.password import (
    hash_password,
    needs_rehash,
    verify_password,
)
from src.db.models.enums import UserRole
from src.services.auth_service import AuthorizationError, AuthService


def test_argon2id_hashing_and_verification() -> None:
    """Test Argon2id password hashing and successful verification."""
    password = "SuperSecurePassword123!"
    hashed = hash_password(password)

    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword456!", hashed) is False
    assert needs_rehash(hashed) is False


def test_argon2id_empty_password_rejection() -> None:
    """Test that empty passwords cannot be hashed."""
    with pytest.raises(ValueError, match="Password cannot be empty"):
        hash_password("")


def test_argon2id_invalid_hash_verification() -> None:
    """Test that corrupted hashes safely return False without exceptions."""
    assert verify_password("Password123!", "corrupted_hash_string") is False
    assert verify_password("", "valid_or_invalid_hash") is False


def test_jwt_create_and_decode_valid_token() -> None:
    """Test creating and decoding a valid JWT access token."""
    user_id = uuid4()
    org_id = uuid4()
    role = UserRole.ADMIN.value

    token = create_access_token(
        user_id=user_id,
        organization_id=org_id,
        role=role,
        expires_delta=timedelta(minutes=10),
    )

    claims = decode_access_token(token)
    assert claims["sub"] == str(user_id)
    assert claims["org_id"] == str(org_id)
    assert claims["role"] == role
    assert "exp" in claims
    assert "iat" in claims


def test_jwt_token_expiration() -> None:
    """Test that expired tokens raise TokenExpiredError."""
    user_id = uuid4()
    org_id = uuid4()

    # Create a token that expired 5 seconds ago
    token = create_access_token(
        user_id=user_id,
        organization_id=org_id,
        role=UserRole.WORKER.value,
        expires_delta=timedelta(seconds=-5),
    )

    with pytest.raises(TokenExpiredError, match="Access token has expired"):
        decode_access_token(token)


def test_jwt_tampered_token_rejection() -> None:
    """Test that tampered tokens raise TokenInvalidError."""
    user_id = uuid4()
    org_id = uuid4()

    token = create_access_token(
        user_id=user_id,
        organization_id=org_id,
        role=UserRole.SUPERVISOR.value,
    )

    # Tamper with the token payload
    parts = token.split(".")
    tampered_payload = parts[1] + "tampered"
    tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"

    with pytest.raises(TokenInvalidError):
        decode_access_token(tampered_token)


def test_user_register_request_password_complexity() -> None:
    """Test password complexity enforcement in UserRegisterRequest."""
    org_id = uuid4()

    # Valid password (upper, lower, digit)
    valid_req = UserRegisterRequest(
        organization_id=org_id,
        email="worker@tenant.com",
        password="ValidPassword123",
        role=UserRole.WORKER,
    )
    assert valid_req.password == "ValidPassword123"

    # Missing uppercase
    with pytest.raises(ValidationError, match="uppercase"):
        UserRegisterRequest(
            organization_id=org_id,
            email="worker@tenant.com",
            password="lowercase12345",
            role=UserRole.WORKER,
        )

    # Missing digit
    with pytest.raises(ValidationError, match="numeric digit"):
        UserRegisterRequest(
            organization_id=org_id,
            email="worker@tenant.com",
            password="NoDigitPassword",
            role=UserRole.WORKER,
        )


def test_user_response_excludes_password_hash() -> None:
    """Ensure UserResponse schema never contains or accepts hashed_password."""
    schema_fields = UserResponse.model_fields.keys()
    assert "hashed_password" not in schema_fields
    assert "password" not in schema_fields


def test_auth_service_tenant_boundary_idor_prevention() -> None:
    """Test that cross-tenant access is immediately blocked with AuthorizationError."""
    org_a = uuid4()
    org_b = uuid4()

    # Same tenant passes
    AuthService.verify_tenant_boundary(org_a, org_a)

    # Different tenant raises AuthorizationError
    with pytest.raises(AuthorizationError, match="different tenant"):
        AuthService.verify_tenant_boundary(org_a, org_b)


def test_auth_service_role_permission() -> None:
    """Test role-based access control checks in AuthService."""
    # Worker accessing Supervisor endpoint
    with pytest.raises(AuthorizationError, match="Insufficient privileges"):
        AuthService.verify_role_permission(
            UserRole.WORKER,
            {UserRole.SUPERVISOR, UserRole.ADMIN},
        )

    # Admin accessing Supervisor endpoint
    AuthService.verify_role_permission(
        UserRole.ADMIN,
        {UserRole.SUPERVISOR, UserRole.ADMIN},
    )
