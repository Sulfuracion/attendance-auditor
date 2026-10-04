"""User ORM model for credentials, RBAC, and access control."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.models.enums import UserRole
from src.db.session import Base

if TYPE_CHECKING:
    from src.db.models.attendance import AttendanceFile, Incident
    from src.db.models.employee import Employee
    from src.db.models.organization import Organization


class User(Base):
    """User accounts with RBAC roles and multi-tenant scoping."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", native_enum=False),
        nullable=False,
        default=UserRole.WORKER,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    employee_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="users")
    employee: Mapped["Employee | None"] = relationship("Employee")
    uploaded_files: Mapped[list["AttendanceFile"]] = relationship(
        "AttendanceFile", back_populates="uploaded_by_user"
    )
    reviewed_incidents: Mapped[list["Incident"]] = relationship(
        "Incident", back_populates="supervisor"
    )

    __table_args__ = (
        Index("ix_users_organization_id", "organization_id"),
        Index("ix_users_email", "email"),
        Index("ix_users_org_role", "organization_id", "role"),
    )
