"""Organization ORM model for multi-tenant isolation and IDOR mitigation."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base

if TYPE_CHECKING:
    from src.db.models.attendance import AttendanceFile
    from src.db.models.employee import Employee
    from src.db.models.holiday import Holiday
    from src.db.models.user import User


class Organization(Base):
    """Tenant boundary entity to strictly isolate all tenant records."""

    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="organization", cascade="all, delete-orphan"
    )
    employees: Mapped[list["Employee"]] = relationship(
        "Employee", back_populates="organization", cascade="all, delete-orphan"
    )
    holidays: Mapped[list["Holiday"]] = relationship(
        "Holiday", back_populates="organization", cascade="all, delete-orphan"
    )
    attendance_files: Mapped[list["AttendanceFile"]] = relationship(
        "AttendanceFile", back_populates="organization", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_organizations_name", "name"),
        Index("ix_organizations_created_at", "created_at"),
    )
