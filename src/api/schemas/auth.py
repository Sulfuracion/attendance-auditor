"""Pydantic v2 schemas for authentication, tokens, registration, and user profiles.

Enforces boundary validation and ensures password hashes are never serialized.
"""

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.db.models.enums import UserRole


class LoginRequest(BaseModel):
    """Payload for user authentication."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(..., description="User's login email address")
    password: str = Field(..., min_length=8, max_length=128, description="User's password")


class TokenResponse(BaseModel):
    """Bearer access token response format."""

    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(..., description="Ephemeral JWT access token")
    token_type: str = Field(default="bearer", description="Token scheme identifier")
    expires_in: int = Field(..., description="Validity period in seconds")


class UserRegisterRequest(BaseModel):
    """Payload for creating a new user within an organization."""

    model_config = ConfigDict(extra="forbid")

    organization_id: UUID = Field(..., description="Target organization UUID")
    email: EmailStr = Field(..., description="Valid work email address")
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password must include uppercase, lowercase, and a digit",
    )
    role: UserRole = Field(default=UserRole.WORKER, description="RBAC role assigned to the user")

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        """Enforce strong password policy."""
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one numeric digit")
        return v


class OrganizationCreateRequest(BaseModel):
    """Payload for onboarding a new organization tenant."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=2, max_length=255, description="Unique organization name")


class OrganizationResponse(BaseModel):
    """Clean serialization of organization data."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    name: str
    created_at: datetime


class UserResponse(BaseModel):
    """Public user profile DTO.

    Strictly filters out password hashes and internal cryptographic details.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    organization_id: UUID
    organization_name: str | None = None
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    employee_id: UUID | None = None
    employee_code: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    weekly_contract_hours: float | None = None


class UserProfileUpdateRequest(BaseModel):
    """Payload to update personal name details."""

    model_config = ConfigDict(extra="forbid")

    first_name: str = Field(..., min_length=1, max_length=128)
    last_name: str = Field(..., min_length=1, max_length=128)


class PasswordChangeRequest(BaseModel):
    """Payload to securely change user's password."""

    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(..., min_length=8, max_length=128)
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New password must include uppercase, lowercase, and a digit",
    )

    @field_validator("new_password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        """Enforce strong password policy."""
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one numeric digit")
        return v


class AuthenticatedUser(BaseModel):
    """Internal user context extracted from validated JWT for dependency injection."""

    id: UUID
    organization_id: UUID
    role: UserRole
