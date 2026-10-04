"""Employee ORM model representing company workers."""

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Float, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base

if TYPE_CHECKING:
    from src.db.models.attendance import AttendanceRecord
    from src.db.models.organization import Organization


class Employee(Base):
    """Employee record associated with an organization."""

    __tablename__ = "employees"

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
    employee_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    first_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    last_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    weekly_contract_hours: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=40.0,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="employees")
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship(
        "AttendanceRecord", back_populates="employee", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "employee_code", name="uq_org_employee_code"),
        Index("ix_employees_organization_id", "organization_id"),
        Index("ix_employees_name", "last_name", "first_name"),
    )
