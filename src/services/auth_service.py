"""Authentication and Authorization Service layer.

Coordinates Argon2id password verification, ephemeral JWT token issuance,
user registration, and IDOR/BOLA multi-tenant boundary enforcement.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.auth import LoginRequest, UserRegisterRequest
from src.config import get_settings
from src.core.security.jwt import create_access_token
from src.core.security.password import hash_password, verify_password
from src.db.models.enums import UserRole
from src.db.models.organization import Organization
from src.db.models.user import User


class AuthenticationError(Exception):
    """Raised when authentication credentials fail validation."""

    pass


class AuthorizationError(Exception):
    """Raised when an authenticated entity attempts unauthorized resource access (BOLA/IDOR)."""

    pass


class ResourceConflictError(Exception):
    """Raised when attempting to create an already existing unique resource."""

    pass


class ResourceNotFoundError(Exception):
    """Raised when a requested resource does not exist."""

    pass


class AuthService:
    """Service handling credential validation, tokens, and multi-tenant authorization."""

    @staticmethod
    async def authenticate(
        session: AsyncSession,
        login_data: LoginRequest,
    ) -> tuple[User, str, int]:
        """Authenticate user by email and password, returning user, token, and expiry.

        Args:
            session: Transactional database session.
            login_data: Validated email and password credentials.

        Returns:
            Tuple of (authenticated User entity, access token string, expiry seconds).

        Raises:
            AuthenticationError: On invalid credentials or inactive account.
        """
        stmt = select(User).where(User.email == login_data.email)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            # Constant-time comparison prevention note: always run verify_password
            # even on missing user to resist timing attacks
            dummy_hash = "$argon2id$v=19$m=65536,t=3,p=4$dummy$dummy"
            verify_password(login_data.password, dummy_hash)
            raise AuthenticationError("Invalid email or password")

        if not user.is_active:
            raise AuthenticationError("User account is inactive")

        if not verify_password(login_data.password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")

        settings = get_settings()
        expires_in = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

        token = create_access_token(
            user_id=user.id,
            organization_id=user.organization_id,
            role=user.role.value,
        )

        return user, token, expires_in

    @staticmethod
    async def register_user(
        session: AsyncSession,
        data: UserRegisterRequest,
    ) -> User:
        """Register a new user within a tenant organization.

        Args:
            session: Transactional database session.
            data: Validated user registration DTO.

        Returns:
            Newly created User entity.

        Raises:
            ResourceNotFoundError: If the target organization does not exist.
            ResourceConflictError: If a user with the given email already exists.
        """
        # Validate that organization exists
        org_stmt = select(Organization).where(Organization.id == data.organization_id)
        org_result = await session.execute(org_stmt)
        if org_result.scalar_one_or_none() is None:
            raise ResourceNotFoundError(f"Organization '{data.organization_id}' not found")

        # Check uniqueness of email
        user_stmt = select(User).where(User.email == data.email)
        user_result = await session.execute(user_stmt)
        if user_result.scalar_one_or_none() is not None:
            raise ResourceConflictError(f"Email '{data.email}' is already registered")

        # Hash password securely with Argon2id
        hashed_pwd = hash_password(data.password)

        new_user = User(
            organization_id=data.organization_id,
            email=data.email,
            hashed_password=hashed_pwd,
            role=data.role,
            is_active=True,
        )

        session.add(new_user)
        await session.flush()
        return new_user

    @staticmethod
    async def create_organization(
        session: AsyncSession,
        name: str,
    ) -> Organization:
        """Create a new multi-tenant organization.

        Args:
            session: Database session.
            name: Unique organization name.

        Returns:
            Created Organization entity.

        Raises:
            ResourceConflictError: If an organization with this name already exists.
        """
        stmt = select(Organization).where(Organization.name == name)
        res = await session.execute(stmt)
        if res.scalar_one_or_none() is not None:
            raise ResourceConflictError(f"Organization '{name}' already exists")

        org = Organization(name=name)
        session.add(org)
        await session.flush()
        return org

    @staticmethod
    def verify_tenant_boundary(
        resource_org_id: UUID,
        current_user_org_id: UUID,
    ) -> None:
        """Enforce strict multi-tenant boundary to mitigate IDOR / BOLA.

        Args:
            resource_org_id: The organization UUID owning the target resource.
            current_user_org_id: The authenticated user's organization UUID.

        Raises:
            AuthorizationError: If tenant IDs do not match.
        """
        if resource_org_id != current_user_org_id:
            raise AuthorizationError("Access denied: Resource belongs to a different tenant")

    @staticmethod
    def verify_role_permission(
        user_role: UserRole,
        allowed_roles: set[UserRole],
    ) -> None:
        """Enforce Role-Based Access Control permissions.

        Args:
            user_role: The role of the authenticated user.
            allowed_roles: Set of roles permitted to perform the action.

        Raises:
            AuthorizationError: If the user's role is not in the permitted set.
        """
        if user_role not in allowed_roles:
            raise AuthorizationError(
                f"Insufficient privileges: role '{user_role.value}' is not authorized"
            )
