"""FastAPI security dependencies for authentication and RBAC enforcement."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api.schemas.auth import AuthenticatedUser
from src.core.security.jwt import TokenExpiredError, TokenInvalidError, decode_access_token
from src.db.models.enums import UserRole

# HTTP Bearer security scheme
bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> AuthenticatedUser:
    """Validate bearer token and extract authenticated user context.

    Raises:
        HTTPException(401): If token is missing, expired, or invalid.
    """
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except TokenExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except TokenInvalidError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    try:
        user_id = UUID(payload["sub"])
        org_id = UUID(payload["org_id"])
        role = UserRole(payload["role"])
    except (ValueError, KeyError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload contains invalid claims structure",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    return AuthenticatedUser(
        id=user_id,
        organization_id=org_id,
        role=role,
    )


def require_roles(*allowed_roles: UserRole) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Dependency factory restricting endpoint access to specific RBAC roles."""

    def role_verifier(
        current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: role '{current_user.role.value}' lacks required permissions",
            )
        return current_user

    return role_verifier
