"""Authentication and User Profile endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, require_roles
from src.api.schemas.auth import (
    AuthenticatedUser,
    LoginRequest,
    OrganizationCreateRequest,
    OrganizationResponse,
    PasswordChangeRequest,
    TokenResponse,
    UserProfileUpdateRequest,
    UserRegisterRequest,
    UserResponse,
)
from src.core.security.password import hash_password, verify_password
from src.db.models.employee import Employee
from src.db.models.enums import UserRole
from src.db.models.organization import Organization
from src.db.models.user import User
from src.db.session import get_db_session
from src.services.auth_service import (
    AuthenticationError,
    AuthService,
    ResourceConflictError,
    ResourceNotFoundError,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and receive access token",
)
async def login(
    credentials: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """Authenticate with email and password to receive an ephemeral JWT access token."""
    try:
        _user, token, expires_in = await AuthService.authenticate(session, credentials)
        return TokenResponse(
            access_token=token,
            expires_in=expires_in,
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


@router.post(
    "/organizations",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new organization tenant",
)
async def create_organization(
    data: OrganizationCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    _current_user: Annotated[AuthenticatedUser, Depends(require_roles(UserRole.ADMIN))],
) -> OrganizationResponse:
    """Create a new multi-tenant organization boundary (Requires ADMIN role)."""
    try:
        org = await AuthService.create_organization(session, data.name)
        return OrganizationResponse.model_validate(org)
    except ResourceConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user within tenant",
)
async def register(
    data: UserRegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    current_user: Annotated[
        AuthenticatedUser, Depends(require_roles(UserRole.ADMIN, UserRole.SUPERVISOR))
    ],
) -> UserResponse:
    """Register a new user inside an organization.

    IDOR mitigation: Supervisors and Admins can only register users inside their own tenant.
    """
    AuthService.verify_tenant_boundary(data.organization_id, current_user.organization_id)

    # Supervisors cannot create ADMIN users
    if current_user.role == UserRole.SUPERVISOR and data.role == UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supervisors are not authorized to create Administrator accounts",
        )

    try:
        user = await AuthService.register_user(session, data)
        return UserResponse.model_validate(user)
    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except ResourceConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
)
async def get_my_profile(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    """Retrieve profile of the currently authenticated user.

    Never serializes password hash or internal credentials.
    """
    stmt = select(User).where(User.id == current_user.id)
    res = await session.execute(stmt)
    user = res.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User record not found",
        )
    profile = UserResponse.model_validate(user)

    # Fetch organization name
    org_stmt = select(Organization.name).where(Organization.id == user.organization_id)
    profile.organization_name = (await session.execute(org_stmt)).scalar_one_or_none()

    # Fetch employee data if linked
    if user.employee_id is not None:
        emp_stmt = select(Employee).where(
            Employee.id == user.employee_id,
            Employee.organization_id == user.organization_id,
        )
        emp = (await session.execute(emp_stmt)).scalar_one_or_none()
        if emp:
            profile.employee_code = emp.employee_code
            profile.first_name = emp.first_name
            profile.last_name = emp.last_name
            profile.weekly_contract_hours = emp.weekly_contract_hours

    return profile


@router.put(
    "/profile",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update personal profile names",
)
async def update_my_profile(
    data: UserProfileUpdateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserResponse:
    """Update personal first name and last name for the authenticated user."""
    stmt = select(User).where(User.id == current_user.id)
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User record not found")

    if user.employee_id is not None:
        emp_stmt = select(Employee).where(
            Employee.id == user.employee_id,
            Employee.organization_id == user.organization_id,
        )
        emp = (await session.execute(emp_stmt)).scalar_one_or_none()
        if emp:
            emp.first_name = data.first_name
            emp.last_name = data.last_name
            await session.commit()
    else:
        # Create an employee record for this user if one doesn't exist
        from uuid import uuid4

        new_emp = Employee(
            id=uuid4(),
            organization_id=user.organization_id,
            employee_code=user.email.split("@")[0].upper()[:12],
            first_name=data.first_name,
            last_name=data.last_name,
            weekly_contract_hours=40.0,
        )
        session.add(new_emp)
        await session.flush()
        user.employee_id = new_emp.id
        await session.commit()

    return await get_my_profile(current_user=current_user, session=session)


@router.put(
    "/password",
    status_code=status.HTTP_200_OK,
    summary="Change user password with Argon2id validation",
)
async def change_my_password(
    data: PasswordChangeRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    """Change user password after verifying current credentials."""
    stmt = select(User).where(User.id == current_user.id)
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual introducida no es correcta.",
        )

    user.hashed_password = hash_password(data.new_password)
    await session.commit()
    return {"message": "Contraseña actualizada correctamente"}
